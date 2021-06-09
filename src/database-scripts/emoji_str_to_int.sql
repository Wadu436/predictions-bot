--SELECT  FROM teams;
--UPDATE teams SET emoji=(regexp_matches(emoji, '<a?:.+:(\d+)>'))[1];
ALTER TABLE teams ALTER COLUMN emoji TYPE bigint USING (substring (emoji FROM '<a?:.+:(\d+)>'))::bigint;
