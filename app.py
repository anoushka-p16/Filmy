# Imports and setup _____________________________________________________________
# _______________________________________________________________________________
from flask import Flask, request, jsonify, abort, render_template, url_for, redirect, session, flash, get_flashed_messages
from sqlalchemy import or_
from models import db, MovieModel, ReviewModel
# Login and authentication
from flask_login import UserMixin
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField
from wtforms.validators import InputRequired, Length, ValidationError
from flask_bcrypt import Bcrypt

# App configuration _____________________________________________________________
# _______________________________________________________________________________
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///movies.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your_secret'

db.init_app(app)
bcrypt = Bcrypt(app)

# Login configuration ___________________________________________________________
# _______________________________________________________________________________
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.unauthorized_handler
def unauthorized():
    return redirect(url_for('login'))

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

# Models and Forms ______________________________________________________________
# _______________________________________________________________________________
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(150), nullable=False)

class UserMovieList(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    movie_id = db.Column(db.Integer, db.ForeignKey('movies.id'), nullable=False)
    user = db.relationship('User', backref='movie_list')
    movie = db.relationship('MovieModel', backref='users_added')

class RegisterForm(FlaskForm):
    username = StringField(validators=[InputRequired(), Length(min=4, max=20)], render_kw={"placeholder": "Username"})
    password = PasswordField(validators=[InputRequired(), Length(min=8, max=20)], render_kw={"placeholder": "Password"})
    submit = SubmitField('Register')

    def validate_username(self, username):
        existing_user = User.query.filter_by(username=username.data).first()
        if existing_user:
            raise ValidationError("Username already exists.")

class LoginForm(FlaskForm):
    username = StringField(validators=[InputRequired(), Length(min=4, max=20)], render_kw={"placeholder": "Username"})
    password = PasswordField(validators=[InputRequired(), Length(min=8, max=20)], render_kw={"placeholder": "Password"})
    submit = SubmitField('Login')

# Authentication routes _________________________________________________________
# _______________________________________________________________________________
@app.route("/login", methods=['GET', 'POST'])
def login():
    form = LoginForm()

    if request.method == 'GET' and request.args.get('direct') != 'true':
        return redirect(url_for('signup'))
    
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and bcrypt.check_password_hash(user.password, form.password.data):
            login_user(user)
            flash("Log in successful!", "success")
            return redirect(url_for('view_all_movies'))
    return render_template("login.html", form=form)

@app.route("/signup", methods=['GET', 'POST'])
def signup():
    form = RegisterForm()
    if form.validate_on_submit():
        hashed_password = bcrypt.generate_password_hash(form.password.data).decode('utf-8')
        new_user = User(username=form.username.data, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        flash("Account created! You can log in.", "success")
        return redirect(url_for('login'))
    return render_template("signup.html", form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Log out successful!", "info")
    return redirect(url_for('login'))

@app.route('/dashboard')
@login_required
def dashboard():
    saved = UserMovieList.query.filter_by(user_id=current_user.id).all()
    saved_count = len(saved)

    reviews = ReviewModel.query.join(MovieModel).filter(ReviewModel.user_id == current_user.id).all()

    return render_template('dashboard.html', saved_count=saved_count, reviews=reviews)

# The HTML Routes _______________________________________________________________
# _______________________________________________________________________________
@app.route('/')
def home_redirect():
    return render_template('main.html')

@app.route('/movies')
def view_all_movies():
    q = MovieModel.query

    search = request.args.get('search')
    genre = request.args.get('genre')
    director = request.args.get('director')
    year = request.args.get('year')

    if search:
        q = q.filter(MovieModel.title.ilike(f"%{search}%"))
    if genre:
        q = q.filter(MovieModel.genre.ilike(f"%{genre}%"))
    if director:
        q = q.filter(MovieModel.director == director)
    if year:
        q = q.filter(MovieModel.year == int(year))

    movies = q.order_by(MovieModel.id.asc()).all()

    # Genre dropdown
    raw_genres = db.session.query(MovieModel.genre).filter(MovieModel.genre != None).all()
    genre_set = set()
    for row in raw_genres:
        split_genres = [g.strip() for g in row[0].split(',')]
        genre_set.update(split_genres)
    genres = sorted(genre_set)

    # Same for director and year
    directors = [row[0] for row in db.session.query(MovieModel.director).distinct().order_by(MovieModel.director).all()]
    years = [row[0] for row in db.session.query(MovieModel.year).distinct().order_by(MovieModel.year).all()]

    return render_template("index.html", movies=movies, genres=genres, directors=directors, years=years)

@app.route('/movies/<int:movie_id>')
def movie_detail(movie_id):
    movie = MovieModel.query.get_or_404(movie_id)
    reviews = ReviewModel.query.filter_by(movie_id=movie.id).all()

    if reviews:
        ratings = [r.rating for r in reviews]
        avg_rating = round(sum(ratings) / len(ratings), 1)
    else:
        avg_rating = 0

    return render_template('detail.html', movie=movie, reviews=reviews, avg_rating=avg_rating)

@app.route('/my-list')
def my_list():
    if current_user.is_authenticated:  # 🟦
        movie_ids = db.session.query(UserMovieList.movie_id).filter_by(user_id=current_user.id).all()  # 🟦
        movie_ids = [m[0] for m in movie_ids]  # 🟦
    else:  # 🟦
        movie_ids = session.get('guest_list', [])  # 🟦

    movies = MovieModel.query.filter(MovieModel.id.in_(movie_ids)).order_by(MovieModel.id.asc()).all()
    return render_template('myList.html', movies=movies)

@app.route('/filter-movies')
def filter_movies():
    q = MovieModel.query

    search = request.args.get('search')
    genre = request.args.get('genre')
    director = request.args.get('director')
    year = request.args.get('year')

    if search:
        q = q.filter(MovieModel.title.ilike(f"%{search}%"))
    if genre:
        q = q.filter(MovieModel.genre.ilike(f"%{genre}%"))
    if director:
        q = q.filter(MovieModel.director == director)
    if year:
        q = q.filter(MovieModel.year == int(year))

    movies = q.order_by(MovieModel.id.asc()).all()
    return render_template('_movie_cards.html', movies=movies)

# Manage List ___________________________________________________________________
# _______________________________________________________________________________
@app.route('/movies/<int:movie_id>/add_to_list', methods=['POST'])
def add_to_my_list(movie_id):
    movie = MovieModel.query.get_or_404(movie_id)
    
    if current_user.is_authenticated:
        existing = UserMovieList.query.filter_by(user_id=current_user.id, movie_id=movie.id).first()
        if not existing:
            entry = UserMovieList(user_id=current_user.id, movie_id=movie.id)
            db.session.add(entry)
            db.session.commit()
    else:
        guest_list = session.get('guest_list', [])
        if movie_id not in guest_list:
            guest_list.append(movie_id)
            session['guest_list'] = guest_list
    flash("Movie added to your list!", "success")
    return redirect(url_for('movie_detail', movie_id=movie_id))

@app.route('/movies/<int:movie_id>/remove_from_list', methods=['POST'])
def remove_from_my_list(movie_id):
    if current_user.is_authenticated:  # 🟦
        UserMovieList.query.filter_by(user_id=current_user.id, movie_id=movie_id).delete()  # 🟦
        db.session.commit()  # 🟦
    else:  # 🟦
        guest_list = session.get('guest_list', [])  # 🟦
        if movie_id in guest_list:  # 🟦
            guest_list.remove(movie_id)  # 🟦
            session['guest_list'] = guest_list  # 🟦

    flash("Movie removed from your list!", "warning")
    return redirect(url_for('my_list'))

@app.route('/submit_review/<int:movie_id>', methods=['POST'])
def submit_review(movie_id):
    rating = int(request.form['rating'])
    review_text = request.form['review']

    new_review = ReviewModel(movie_id=movie_id, user_id=current_user.id, rating=rating, text=review_text)
    db.session.add(new_review)
    db.session.commit()
    flash("Thanks for your review!", "success")
    return redirect(url_for('movie_detail', movie_id=movie_id))

# API Routes ____________________________________________________________________
# _______________________________________________________________________________
@app.route('/api/movies', methods=['GET'])
def api_list_movies():
    q = MovieModel.query
    for fld in ('genre','director','year'):
        if v := request.args.get(fld):
            q = q.filter_by(**{fld: v})
    return jsonify([m.json() for m in q.all()])

@app.route('/api/movies/<int:movie_id>', methods=['GET'])
def get_movie(movie_id):
    m = MovieModel.query.get(movie_id)
    if not m:
        abort(404, "Movie not found")
    return jsonify(m.json())

# Entry point ___________________________________________________________________
# _______________________________________________________________________________
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host='localhost', port=5000, debug=True)
