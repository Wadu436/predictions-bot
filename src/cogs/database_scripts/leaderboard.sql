-- WITH tournament AS (SELECT tournaments.id FROM tournaments WHERE channel = 838762583762141214 AND running = 1),
WITH tournament AS (
    SELECT tournaments.id
    FROM tournaments
    WHERE tournaments.id = :tournament
),
finished_matches AS (
    SELECT matches.name,
        matches.tournament,
        matches.result,
        matches.games,
        (
            CASE
                WHEN matches.bestof = 1 THEN :bo1_team
                WHEN matches.bestof = 3 THEN :bo3_team
                WHEN matches.bestof = 5 THEN :bo5_team
                ELSE 0
            END
        ) as team_score,
        (
            CASE
                WHEN matches.bestof = 1 THEN 0
                WHEN matches.bestof = 3 THEN :bo3_games
                WHEN matches.bestof = 5 THEN :bo5_games
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
        team_score * (users_matches.team = finished_matches.result) as team_score,
        game_score * (users_matches.games = finished_matches.games) as game_score,
        users_matches.team = finished_matches.result as team_correct
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
GROUP BY id
ORDER BY score DESC,
    name;
--GROUP BY users.id