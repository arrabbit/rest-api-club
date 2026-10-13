-- setup_mysql.sql
-- Purpose: Creates the production and test databases and a limited app user
--          that can only connect from the VM itself (localhost).
-- Authors: Anna Running Rabbit
-- Date Created:      2026-10-13
-- Date Last Editted: 2026-10-13
--
-- Run on the VM, from the repo root:  sudo mysql < deploy/setup_mysql.sql
-- Replace CHANGE_ME with the password you put in /etc/campus-events/campus.env.

CREATE DATABASE IF NOT EXISTS campus_events;
CREATE DATABASE IF NOT EXISTS campus_events_test;

-- 'localhost' only: unlike the Sept 17 activity, no '%' user and no remote access.
CREATE USER IF NOT EXISTS 'campus_app'@'localhost'
    IDENTIFIED WITH caching_sha2_password BY 'CHANGE_ME';

-- Only the privileges the app and reset script need, on our two databases only.
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, INDEX, REFERENCES
    ON campus_events.* TO 'campus_app'@'localhost';
GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, ALTER, INDEX, REFERENCES
    ON campus_events_test.* TO 'campus_app'@'localhost';
FLUSH PRIVILEGES;