"""Starter lesson library. Loaded once, on first run, if the library is empty.

``solution`` lists acceptable first moves in SAN separated by " / ".
On the board, any move that delivers checkmate is also accepted.
"""

STARTER_LESSONS = [
    {
        "slug": "how-pieces-move",
        "title": "How the pieces move and what they are worth",
        "track": "foundations", "level": 1, "minutes": 20,
        "summary": "Movement, captures, and the point values every player uses to judge a trade.",
        "fen": "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
        "solution": "",
        "body": """Every game starts from this position. White always moves first.

- **Pawn (1)** moves forward one square, two on its first move, and captures diagonally.
- **Knight (3)** jumps in an L shape and is the only piece that can hop over others.
- **Bishop (3)** slides diagonally and stays on one colour all game.
- **Rook (5)** slides along ranks and files.
- **Queen (9)** combines rook and bishop.
- **King** moves one square. It is never captured; trapping it is checkmate.

Point values are a guide, not a law. Before every trade, add up what you give and what you get.""",
    },
    {
        "slug": "checks-captures-threats",
        "title": "The blunder check: checks, captures, threats",
        "track": "foundations", "level": 1, "minutes": 10,
        "summary": "A three-question routine to run before every move. Stops most lost games.",
        "fen": "", "solution": "",
        "body": """Most games below 1500 are decided by a piece left hanging. A short routine fixes that.

Before you move, ask about your opponent's last move:

- What **checks** can they give me now?
- What **captures** can they make?
- What are they **threatening** next move?

Then ask the same three questions about your own candidate move before you play it. It takes ten seconds. Practise it out loud with your coach until it becomes automatic.""",
    },
    {
        "slug": "back-rank-mate",
        "title": "Back-rank mate",
        "track": "tactics", "level": 1, "minutes": 10,
        "summary": "A king walled in by its own pawns can be mated by a single rook.",
        "fen": "6k1/5ppp/8/8/8/8/5PPP/3R2K1 w - - 0 1",
        "solution": "Rd8#",
        "body": """Black castled and never moved a pawn in front of the king. The pawns on f7, g7 and h7 now block every escape square.

White to move and win.

**Defence idea:** when the position is calm, a move like ...h6 gives your king an escape square. Coaches call it "making luft".""",
    },
    {
        "slug": "knight-fork",
        "title": "The knight fork",
        "track": "tactics", "level": 1, "minutes": 10,
        "summary": "One knight, two targets. Learn to spot the squares where it hits king and queen together.",
        "fen": "q3k3/8/8/1N6/8/8/8/4K3 w - - 0 1",
        "solution": "Nc7+",
        "body": """Knights attack in a pattern that is hard to see, which makes them the best forking piece on the board.

White to move. Find the square that attacks the king and the queen at the same time. After the king steps away, the queen falls.

**Pattern to remember:** a knight only ever attacks squares of one colour, so both targets must stand on the same colour. Here they sit four files apart on the back rank, and one square hits both.""",
    },
    {
        "slug": "skewer",
        "title": "The skewer",
        "track": "tactics", "level": 2, "minutes": 10,
        "summary": "Attack the valuable piece first; whatever hides behind it is lost.",
        "fen": "q7/8/8/3k4/8/8/8/4KB2 w - - 0 1",
        "solution": "Bg2+",
        "body": """A skewer is a pin turned inside out. The more valuable piece is in front, so it has to move, exposing the piece behind it.

White to move. The black king and queen are on the same long diagonal.

**Ask yourself:** which line connects the two black pieces, and can I check along it?""",
    },
    {
        "slug": "discovered-check",
        "title": "Discovered check",
        "track": "tactics", "level": 2, "minutes": 12,
        "summary": "Move one piece to unleash another. The moving piece gets a free hit.",
        "fen": "4k3/1q6/8/8/4B3/8/8/4R1K1 w - - 0 1",
        "solution": "Bxb7+",
        "body": """The bishop is standing between the white rook and the black king. When it moves, the rook gives check, and Black has no time to deal with whatever the bishop attacks.

White to move and win the queen.

Discovered attacks are among the most powerful tactics in chess, because your opponent faces two threats from a single move.""",
    },
    {
        "slug": "queen-king-mate",
        "title": "Queen and king checkmate",
        "track": "endgames", "level": 1, "minutes": 15,
        "summary": "The first mate everyone must know cold. Avoid stalemate on the way.",
        "fen": "7k/8/6K1/8/8/8/8/1Q6 w - - 0 1",
        "solution": "Qb8#",
        "body": """The white king has done its job: it covers g7 and h7. Now the queen needs to deliver the final check along the edge.

White to move and mate in one.

**Stalemate warning:** in positions like this, a careless queen move that takes away every square without giving check ends the game in a draw. Always check that the enemy king has a legal move until you deliver mate.""",
    },
    {
        "slug": "opposition",
        "title": "King and pawn: the opposition",
        "track": "endgames", "level": 2, "minutes": 20,
        "summary": "Why kings facing each other decide whether a pawn promotes.",
        "fen": "4k3/8/4K3/4P3/8/8/8/8 w - - 0 1",
        "solution": "Kd6 / Kf6",
        "body": """When two kings stand on the same file with one square between them, the side that does **not** have to move holds the opposition.

Here White's king is on the sixth rank in front of the pawn, which wins whoever is to move. White to move must step aside so the pawn can advance with the king's support.

- 1.Kd6 Kd8 2.e6 Ke8 3.e7 Kf7 4.Kd7 and the pawn promotes.

Set this up with your coach and play it from both sides until you can win it without thinking.""",
    },
    {
        "slug": "rule-of-the-square",
        "title": "The rule of the square",
        "track": "endgames", "level": 1, "minutes": 10,
        "summary": "Decide in two seconds whether a king can catch a passed pawn.",
        "fen": "8/8/8/8/k6P/8/8/K7 w - - 0 1",
        "solution": "h5",
        "body": """Draw an imaginary square from the pawn to its promotion rank. Here that is h4 to h8, so the square runs from d4 to h8.

If the defending king can step into the square on its move, it catches the pawn. If not, the pawn promotes.

White to move. Is the black king inside the square? Push the pawn and check your answer.""",
    },
    {
        "slug": "scholars-mate-defence",
        "title": "Stopping the four-move checkmate",
        "track": "openings", "level": 1, "minutes": 10,
        "summary": "Queen and bishop gang up on f7 early. Here is the calm way to defend.",
        "fen": "r1bqkbnr/pppp1ppp/2n5/4p2Q/2B1P3/8/PPPP1PPP/RNB1K1NR b KQkq - 3 3",
        "solution": "g6 / Qe7",
        "body": """After 1.e4 e5 2.Qh5 Nc6 3.Bc4, White threatens Qxf7, which is checkmate.

Black to move. Find a move that defends f7 or chases the queen away. Note that 3...Nf6?? walks straight into Qxf7#.

Early queen attacks look scary but usually lose time. Defend calmly, then develop with tempo against the queen.""",
    },
    {
        "slug": "italian-game",
        "title": "Opening principles through the Italian Game",
        "track": "openings", "level": 1, "minutes": 20,
        "summary": "Centre, development, king safety, in a real opening you can play tomorrow.",
        "fen": "r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3",
        "solution": "",
        "body": """1.e4 e5 2.Nf3 Nc6 3.Bc4 is one of the oldest openings in chess, and it follows every principle a beginner should learn:

- **Control the centre** with a pawn (e4).
- **Develop with a threat**: Nf3 attacks e5.
- **Aim at the weak point**: the bishop on c4 eyes f7.
- **Castle early**: White is one move away from O-O.

Black's most natural replies are 3...Bc5 and 3...Nf6. Play ten games with this setup and review them with your coach.""",
    },
    {
        "slug": "open-files",
        "title": "Rooks belong on open files",
        "track": "strategy", "level": 2, "minutes": 15,
        "summary": "A file with no pawns is a highway. The first rook there usually owns it.",
        "fen": "r4rk1/pp3ppp/2p5/8/8/2P5/PP3PPP/R4RK1 w - - 0 1",
        "solution": "Rad1 / Rfd1 / Rae1 / Rfe1",
        "body": """The d-file and e-file have no pawns on them. A rook placed there can invade on the seventh rank later.

White to move. Put a rook where it does the most work.

Ask: which files are open, which are half-open, and where can my rook eventually land inside the opponent's camp?""",
    },
    {
        "slug": "using-your-clock",
        "title": "Using your clock",
        "track": "foundations", "level": 2, "minutes": 10,
        "summary": "Budget time like money. Spend it on critical moves, not obvious ones.",
        "fen": "", "solution": "",
        "body": """Losing on time with a winning position is the most painful way to lose. A simple budget prevents it.

- Divide your time by about 40 to get an average per move.
- Play known opening moves quickly to bank time.
- Spend real time when the position changes: a capture, a pawn break, a king in danger.
- With under a minute left, play safe moves and use the increment.

In your next rapid game, write your remaining time every ten moves and review it with your coach.""",
    },
    {
        "slug": "reviewing-your-games",
        "title": "How to review your own games",
        "track": "strategy", "level": 1, "minutes": 15,
        "summary": "Your own losses are the best textbook you will ever own. Here's how to read them.",
        "fen": "", "solution": "",
        "body": """Review every serious game within a day, before an engine tells you anything.

- Find the moment the game turned. Write down what you were thinking then.
- Look for missed checks, captures and threats on both sides.
- Only then turn on an engine, and only to check your conclusions.
- Bring one position per game to your next session.

Your coach can do this with you in a session. The habit matters more than the engine's verdict.""",
    },
]


def ensure_curriculum():
    from ..models import db
    from .models import Lesson

    if Lesson.query.first() is not None:
        return 0
    for data in STARTER_LESSONS:
        db.session.add(Lesson(**data))
    db.session.commit()
    return len(STARTER_LESSONS)
