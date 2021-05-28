-- $1 = tournament id
-- $2 = bo1_team
-- $3 = bo3_team
-- $4 = bo5_team
-- $5 = bo3_games
-- $6 = bo5_games
-- WITH tournament AS (SELECT tournaments.id FROM tournaments WHERE channel = 838762583762141214 AND running = 1),
WITH tournament AS (
    SELECT tournaments.id
    FROM tournaments
    WHERE tournaments.id = $1
),
finished_matches AS (
    SELECT matches.name,
        matches.tournament,
        matches.result,
        matches.games,
        (
            CASE
                WHEN matches.bestof = 1 THEN $2
                WHEN matches.bestof = 3 THEN $3
                WHEN matches.bestof = 5 THEN $4
                ELSE 0
            END
        ) as team_score,
        (
            CASE
                WHEN matches.bestof = 1 THEN 0
                WHEN matches.bestof = 3 THEN $5
                WHEN matches.bestof = 5 THEN $6
                ELSE 0
            END
        ) as game_score
    FROM tournament
        INNER JOIN matches ON tournament.id = matches.tournament
    WHERE running = 0
),
score_per_match AS (
    SELECT users.id,
        users.name,
        team_score * (users_matches.team = finished_matches.result)::int as team_score,
        game_score * (users_matches.games = finished_matches.games)::int as game_score,
        (users_matches.team = finished_matches.result)::int as team_correct
    FROM finished_matches
        INNER JOIN users_matches ON finished_matches.name = match_name
        AND finished_matches.tournament = match_tournament
        INNER JOIN users ON user_id = users.id
)
SELECT name,
    SUM(team_score + game_score) as score,
    SUM(team_correct) as correct,
    COUNT(*) as total,
    (100.0 * SUM(team_correct)) / COUNT(*) as percent_correct
FROM score_per_match
GROUP BY id,
    name
ORDER BY score DESC,
    name;