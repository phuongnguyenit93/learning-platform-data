# Roles, Default Roles, and Effective Session Privileges

In MySQL, a **role** is a named collection of privileges. Administrators can grant roles to multiple accounts, enable or disable roles per connection, and choose which roles automatically take effect when a user logs in. To verify whether an account can actually execute a statement, you must check its direct privileges, its granted roles, and the role activation state of the connection session itself.

This lesson uses MySQL 8.0 and later syntax, compatible with MySQL 8.4. MySQL 5.7 does not support the role system described here. The examples assume the person running administrative statements holds sufficient privileges; replace sample passwords with securely managed secrets in real environments.

## Objectives

After this lesson, you will be able to:

- Distinguish between an account, a role, a granted role, a default role, and an active role.
- Create roles, grant privileges to roles, and grant roles to accounts or other roles.
- Configure default roles for login and change roles within the current session using `SET ROLE`.
- Determine the effective privileges in a session and explain why a SQL statement is denied.
- Design roles under least privilege while safely handling roles in connection pools and stored programs.

## 1. The Role Model and Effective Privileges

A MySQL account has the form `'user_name'@'host_name'`. The `host_name` portion participates in identifying the account used for authentication; the same username with different hosts can be two distinct accounts. Roles also have names in user/host form. If you omit the host part of a role, MySQL defaults the host to `%`.

A role is an identifier containing privileges granted via `GRANT`. For instance, `r_sales_read` can represent read privileges on sales data, while `r_sales_write` represents write privileges. A role can be granted to an account or to another role, enabling nested role hierarchies. Newly created roles are locked by default and cannot be used to log in like ordinary application accounts.

Distinguish the following four concepts:

| Concept | Meaning |
|---|---|
| Direct privileges | Privileges `GRANT`ed directly to the account. These do not depend on enabling or disabling roles. |
| Granted roles | Roles granted to the account or inherited through another role. Being granted does not imply the role is currently active. |
| Default roles | Roles selected to activate automatically when the account logs in successfully. |
| Active roles | Roles currently in effect in the active connection session. Their privileges participate in access checks. |

You can think of the privilege set evaluated in a session as:

```text
Session effective privileges
  = direct privileges granted to the account
  + privileges from active roles
  + privileges from roles nested inside active roles
```

Roles listed in `mandatory_roles` are treated by MySQL as granted to every account. Those roles still follow the role activation mechanism: they only take effect when activated as default roles or under automatic activation of all roles. `SET ROLE` changes only the set of active roles; direct privileges granted to the account remain intact.

## 2. Creating Roles and Granting Privileges

Suppose an application uses the `sales_db` database. A reporting account only needs to read data; an order-processing account needs to read and update certain tables. Group privileges by task instead of repeating privilege lists across individual accounts.

```sql
-- Create two task-based roles.
CREATE ROLE 'r_sales_read'@'%', 'r_sales_write'@'%';

-- Attach data privileges to each role.
GRANT SELECT ON sales_db.*
TO 'r_sales_read'@'%';

GRANT INSERT, UPDATE ON sales_db.orders
TO 'r_sales_write'@'%';

-- Create a service account.
CREATE USER 'svc_report'@'localhost'
IDENTIFIED BY 'replace_with_secret';

-- Grant the role to the account.
GRANT 'r_sales_read'@'%'
TO 'svc_report'@'localhost';
```

The two forms of `GRANT` have different meanings:

```sql
-- With ON: grants object privileges to a role or account.
GRANT SELECT ON sales_db.* TO 'r_sales_read'@'%';

-- Without ON: grants a role to an account or another role.
GRANT 'r_sales_read'@'%' TO 'svc_report'@'localhost';
```

A single `GRANT` statement cannot mix object privilege grants and role grants at the same time. If both are needed, issue two separate statements. To grant roles to others, an administrator needs `ROLE_ADMIN` (or the legacy `SUPER` privilege); a grantee who receives a role with `WITH ADMIN OPTION` can also pass that role on while the role is active. `WITH ADMIN OPTION` governs role delegation, unlike `WITH GRANT OPTION`, which governs object-privilege delegation.

## 3. Default Roles and Active Roles

### 3.1. Choosing Roles That Activate Automatically at Login

`SET DEFAULT ROLE` saves the default role selection for one or more accounts. For example, the reporting account always needs read privileges when opening a connection:

```sql
SET DEFAULT ROLE 'r_sales_read'@'%'
TO 'svc_report'@'localhost';
```

Common forms:

```sql
-- Automatically activate all roles granted to the account.
SET DEFAULT ROLE ALL TO 'svc_report'@'localhost';

-- Do not automatically activate any roles at login.
SET DEFAULT ROLE NONE TO 'svc_report'@'localhost';

-- Activate only the specified list of roles.
SET DEFAULT ROLE 'r_sales_read'@'%'
TO 'svc_report'@'localhost';
```

Default roles are applied when a user logs in and authenticates successfully. Changing default roles does not automatically alter the active roles in already-open sessions. Within an existing session, you can run `SET ROLE DEFAULT` to reload the newly saved default selection.

### 3.2. Changing Roles in the Current Session

`SET ROLE` immediately changes the active role set of the current connection:

| Statement | Effect in Session |
|---|---|
| `SET ROLE DEFAULT` | Activates the account's default roles. |
| `SET ROLE NONE` | Deactivates all roles; direct privileges remain in effect. |
| `SET ROLE ALL` | Activates all roles granted to the account, including mandatory roles. |
| `SET ROLE 'r_sales_read'@'%'` | Activates only the specified role; that role must be granted to the account. |
| `SET ROLE ALL EXCEPT 'r_sales_write'@'%'` | Activates all granted roles except the listed role(s). |

Example:

```sql
-- View currently active roles.
SELECT CURRENT_ROLE();

-- Temporarily disable all roles in this connection.
SET ROLE NONE;
SELECT CURRENT_ROLE();

-- Enable only read privileges.
SET ROLE 'r_sales_read'@'%';
SELECT CURRENT_ROLE();

-- Return to the account's default roles.
SET ROLE DEFAULT;
SELECT CURRENT_ROLE();
```

Two statement names are easily confused:

- `SET DEFAULT ROLE ... TO user` **defines the account's default policy** for login and for future `SET ROLE DEFAULT` calls.
- `SET ROLE DEFAULT` **changes the current session's state** to apply the defined default policy.

### 3.3. Automatically Activating All Roles

The global variable `activate_all_roles_on_login` controls how MySQL activates roles at login. Its default value is `OFF`:

```sql
SHOW VARIABLES LIKE 'activate_all_roles_on_login';
```

- When `OFF`, MySQL activates the default roles configured via `SET DEFAULT ROLE`.
- When `ON`, MySQL activates all roles granted to the account at login; this setting overrides the default role list.

This is a server-wide setting, not a per-account option. Do not enable it globally just to fix one account missing privileges: doing so can cause broader roles to become active simultaneously across many accounts. Configure default roles tailored to each account's task unless a clear operational policy requires activating all roles.

## 4. Inspecting Effective Privileges

Do not conclude an account has a privilege merely because a role appears in its granted list. Check both active roles and the privileges granted inside those roles.

```sql
-- Identify the account MySQL matched and the session's active roles.
SELECT CURRENT_USER() AS authenticated_account,
       CURRENT_ROLE() AS active_roles;

-- View privileges and roles granted directly to the account.
SHOW GRANTS FOR 'svc_report'@'localhost';

-- Expand privileges from the specified role to inspect what it grants.
SHOW GRANTS FOR 'svc_report'@'localhost'
USING 'r_sales_read'@'%';

-- For the current account, you can use:
SHOW GRANTS;
```

`SHOW GRANTS FOR account` displays direct privileges and granted roles, but usually lists role names without expanding all privileges inside each role. The `USING` clause tells MySQL to include privileges originating from the named role(s). When multiple roles are involved, list all relevant roles to inspect.

`CURRENT_ROLE()` answers the question "which roles are active in this session?". `SHOW GRANTS ... USING ...` answers the question "which privileges do the selected roles provide?". These two checks complement each other; neither replaces testing statements against the target objects.

## 5. Practice: Demonstrating Session-Scoped Privilege Changes

After creating the roles in section 2 and setting `r_sales_read` as the default role in section 3, log in as `svc_report` and execute:

```sql
-- Verify the role activated at login.
SELECT CURRENT_USER(), CURRENT_ROLE();

-- If the table exists, this query should succeed via the read role.
SELECT * FROM sales_db.orders LIMIT 5;

-- Disable roles: read privileges from r_sales_read are no longer active.
SET ROLE NONE;
SELECT CURRENT_ROLE();

-- Without direct SELECT privileges, the following query is denied.
SELECT * FROM sales_db.orders LIMIT 5;

-- Reload default roles in the same connection.
SET ROLE DEFAULT;
SELECT CURRENT_ROLE();

-- Read privileges from the default role take effect again.
SELECT * FROM sales_db.orders LIMIT 5;
```

Expected outcome: the read query succeeds while `r_sales_read` is active; after `SET ROLE NONE`, the query is denied unless direct `SELECT` or another active privilege source exists; after `SET ROLE DEFAULT`, the read query succeeds again. Exact error messages may vary by version and configuration, but the cause to inspect is that `SELECT` is no longer in the session's effective privilege set.

This experiment also highlights an important point: `SET ROLE NONE` does not revoke privileges from the account. If an administrator granted `SELECT` directly to `svc_report`, the query will still succeed after disabling roles. Removing direct privileges requires running `REVOKE` on the account itself.

## 6. Nested Roles and Mandatory Roles

### 6.1. Nested Roles

MySQL allows granting a role to another role. For example, an application role can combine read and reporting privileges:

```sql
CREATE ROLE 'r_sales_base'@'%', 'r_sales_analyst'@'%';
GRANT SELECT ON sales_db.* TO 'r_sales_base'@'%';
GRANT 'r_sales_base'@'%' TO 'r_sales_analyst'@'%';
GRANT 'r_sales_analyst'@'%' TO 'svc_report'@'localhost';

SET DEFAULT ROLE 'r_sales_analyst'@'%'
TO 'svc_report'@'localhost';
```

Granting a role to another role creates privilege inheritance. When computing privileges from an active role, nested roles within that structure must also be considered. Nested roles aid reuse, but overly deep or heavily branched role trees are hard to audit. Keep the hierarchy simple and inspect with `SHOW GRANTS ... USING` for the relevant roles.

### 6.2. Mandatory Roles

The global variable `mandatory_roles` tells the server to treat one or more roles as granted to every account. Example configuring a shared auditing role:

```sql
-- Administrative example; requires ROLE_ADMIN and system variable privilege.
SET PERSIST mandatory_roles = 'r_audit@%';
```

`SET PERSIST` applies the value to the running server and persists it across restarts. Mandatory roles still must be activated via MySQL's role mechanism: default roles or `activate_all_roles_on_login`. A role listed in `mandatory_roles` cannot be revoked or dropped with `REVOKE`/`DROP ROLE` while it remains configured as mandatory. Because this setting affects the entire server, use it only for foundational privileges genuinely needed everywhere; avoid placing powerful administrative privileges in mandatory roles.

## 7. Revoking Roles and Managing Session Lifecycles

You can revoke a role from an account or revoke a privilege from a role:

```sql
-- Account no longer holds the read role.
REVOKE 'r_sales_read'@'%'
FROM 'svc_report'@'localhost';

-- Revoke update privilege from the write role.
REVOKE UPDATE ON sales_db.orders
FROM 'r_sales_write'@'%';
```

Revoking a privilege from a role affects every account receiving that privilege through the role. This enables centralized policy changes, yet can also cause wide-ranging impact. Before making changes, check which accounts hold the role and assess applications depending on that privilege. `DROP ROLE` removes the role and strips its grant from all affected accounts.

`SET ROLE` affects the current session immediately. Therefore, applications using connection pools must manage role state just like transaction state, session variables, or the current schema. If a request runs `SET ROLE` and returns the connection to the pool without resetting state, the next request may receive a connection with unexpected active roles. Set the required role when checking out a connection and restore the baseline state before returning it to the pool; do not assume every request gets a fresh login session.

Standard account management statements such as `GRANT` and `REVOKE` automatically update MySQL's privilege state; you do not need to run `FLUSH PRIVILEGES` afterward. `FLUSH PRIVILEGES` is mainly relevant when directly editing grant tables in the `mysql` schema, which should not be done in normal administration. Use `CREATE USER`, `CREATE ROLE`, `GRANT`, `REVOKE`, `SET DEFAULT ROLE`, and `ALTER USER` instead of updating system tables directly.

## 8. Roles in Views and Stored Programs

Privileges used when invoking a view, procedure, or function also depend on its `SQL SECURITY` attribute and `DEFINER`:

- With `SQL SECURITY INVOKER`, operations execute in the caller's security context using the active roles in the caller's session.
- With `SQL SECURITY DEFINER`, operations execute in the definer's security context. MySQL uses the `DEFINER` account's default roles; if `activate_all_roles_on_login` is enabled, roles granted to the `DEFINER` are also activated according to the corresponding rule.

Consequently, a direct `SELECT` may fail while calling a procedure succeeds, or vice versa, depending on the security context. When investigating privilege errors through stored objects, inspect `SQL SECURITY`, `DEFINER`, the definer account's privileges, and related role states rather than looking only at the caller's `CURRENT_ROLE()`.

## 9. Design Principles and Common Mistakes

1. **Design roles by task.** Separate reading, writing, schema deployment, and operational administration. Combine roles only when an account genuinely requires all of those tasks.
2. **Prefer least privilege.** Grant privileges on the needed databases, tables, or columns. Avoid `ALL ON *.*` for application accounts.
3. **Keep direct privileges intentional.** If an account holds directly granted privileges, disabling roles does not remove them. Check both sources when assessing risk.
4. **Do not confuse granted roles with active roles.** If privileges were granted yet queries are still denied, check `CURRENT_ROLE()` and default roles first.
5. **Inspect the exact matched host account.** `SHOW GRANTS` must target the exact authenticating user/host pair; the same username with another host can hold a different privilege set.
6. **Inspect privileges inside roles.** Use `SHOW GRANTS ... USING role` to expand role privileges during audits.
7. **Be cautious with global settings.** `activate_all_roles_on_login` and `mandatory_roles` are server-wide; changing them can affect many applications.
8. **Reset connection pool state.** Do not let active roles from an earlier request leak into a subsequent request.

A troubleshooting workflow for `Access denied` errors can proceed in order: verify `CURRENT_USER()`; check `CURRENT_ROLE()`; inspect `SHOW GRANTS` for the exact account; expand roles with `USING`; confirm privileges at the right database/table scope; and finally check `DEFINER`/`INVOKER` context if accessing through a stored object.

## 10. Self-Check Exercises

1. An account has been granted `r_sales_read`, yet `CURRENT_ROLE()` returns `NONE`. Why does the role not provide read privileges yet? Name two ways to activate the role in the session.
2. After `SET ROLE NONE`, the account can still read a table. Name the privilege sources that could explain this outcome.
3. An administrator runs `SET DEFAULT ROLE NONE TO 'svc_report'@'localhost'`. Does this immediately disable roles in all currently open connections? Which statement applies the new default in an existing session?
4. When revoking `UPDATE` from `r_sales_write`, which accounts are affected? Why can this be simpler than revoking from individual accounts?
5. In an application using a connection pool, Request A executes `SET ROLE NONE`. What must be done so Request B does not inherit unexpected privilege state?

**Answer hints:** (1) The role is granted but not active; run `SET ROLE 'r_sales_read'@'%'` or `SET ROLE DEFAULT` after configuring the default role. (2) The account may hold a direct `SELECT` grant, or another active role provides that privilege. (3) No; default roles primarily govern login and `SET ROLE DEFAULT` calls; run `SET ROLE DEFAULT` in each session that needs updating. (4) Every account receiving `UPDATE` via that role, including accounts inheriting it through nested roles. (5) Set the intended role upon acquiring a connection and restore baseline state before returning the connection to the pool.

## References

- [MySQL 8.4 Reference Manual: Using Roles](https://dev.mysql.com/doc/refman/8.4/en/roles.html)
- [MySQL 8.4 Reference Manual: SET ROLE](https://dev.mysql.com/doc/refman/8.4/en/set-role.html)
- [MySQL 8.4 Reference Manual: SET DEFAULT ROLE](https://dev.mysql.com/doc/refman/8.4/en/set-default-role.html)
- [MySQL 8.4 Reference Manual: GRANT Statement](https://dev.mysql.com/doc/refman/8.4/en/grant.html)
- [MySQL 8.4 Reference Manual: When Privilege Changes Take Effect](https://dev.mysql.com/doc/refman/8.4/en/privilege-changes.html)
