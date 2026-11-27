# PFILE, SPFILE, and Parameter Scopes MEMORY/SPFILE/BOTH

Oracle Database uses initialization parameters to control how an instance starts up and operates. Parameters such as MEMORY_TARGET, SGA_TARGET, PROCESSES, OPEN_CURSORS, DB_CACHE_SIZE, UNDO_TABLESPACE, CONTROL_FILES, or optimizer settings affect memory, processes, transactions, SQL execution, and many other components.

Oracle provides two ways to store initialization parameters:

- **PFILE (parameter file):** a plain text file, often called init.ora. DBAs can read and edit it with a text editor when the instance does not use that file for automatic writes.
- **SPFILE (server parameter file):** a binary file managed by Oracle. DBAs modify its contents using the ALTER SYSTEM statement or supported administrative tools; do not edit it directly with a text editor.

When using an SPFILE, the ALTER SYSTEM SET statement can choose where to store the change using SCOPE:

- **MEMORY:** changes the value in memory of the running instance; does not save it to the SPFILE to persist across restarts.
- **SPFILE:** writes the value only to the SPFILE; the value will be used when the instance restarts.
- **BOTH:** changes both the runtime value and the value stored in the SPFILE.

Understanding these three scopes prevents two common operational mistakes: changing a parameter and losing it on restart because only MEMORY was set, or changing SPFILE and expecting the current instance to change immediately. You must also distinguish dynamic parameters that can be changed while the instance is running from static parameters that only take effect after a restart.

## 1. Initialization Parameters and Instance Startup

### 1.1. What Is an Initialization Parameter?

An initialization parameter is a configuration setting Oracle reads when creating an instance. Some parameters define memory structures, process counts, control files, database name, and undo; others affect the optimizer, parallel execution, auditing, security, or session behavior.

They can be broadly divided into:

- Parameters affecting the entire instance.
- Parameters that can be changed per session.
- Parameters that only take effect at instance startup.
- Parameters that can take effect immediately or apply to new sessions.
- Parameters that can be set individually per instance in RAC.

Not every parameter shares the same modification scope. Before changing one, verify the parameter's attributes in the data dictionary and the documentation for your exact Oracle release.

### 1.2. The Instance Needs a Parameter File at Startup

At startup, Oracle reads initialization parameters to create the SGA, initialize background processes, and prepare the instance. Some parameters must be present right from the NOMOUNT step; others may take default values if not declared.

The startup sequence typically proceeds through:

1. NOMOUNT: read parameter file, create instance, allocate memory, and start background processes.
2. MOUNT: open control files and associate the instance with the database.
3. OPEN: open data files and redo logs so the database serves workloads.

If the parameter file is wrong, missing, or contains invalid values, the instance may fail to start or fail to reach the desired state.

### 1.3. Default Parameter File

If PFILE is not specified in the STARTUP command, Oracle searches for a server parameter file according to the platform/configuration default rules and locations. If no suitable SPFILE is found, Oracle may look for a default PFILE.

Filenames and directories differ across Windows, Unix/Linux, Oracle Home, and ASM configurations. Therefore, do not assume every database uses the same path. You can determine which file is in use after the instance starts with:

```sql
SHOW PARAMETER spfile;
```

Or:

```sql
SELECT value
FROM v$parameter
WHERE name = 'spfile';
```

If VALUE is empty, the instance may have been started using a PFILE or no SPFILE path is reported in the parameter view.

## 2. PFILE: Text Parameter File

### 2.1. Characteristics

A PFILE is a human-readable text file. A PFILE contains parameter lines in the format:

```text
db_name='ORCL'
control_files='/u01/oradata/ORCL/control01.ctl'
memory_target=4G
processes=500
open_cursors=500
```

This is an illustrative example; paths, database name, and values must match the actual environment.

PFILE is typically useful when:

- Needing to start an instance with a manually controlled set of parameters.
- Needing to recover after an SPFILE becomes corrupted or misconfigured.
- Wanting to keep a human-readable configuration copy for review/version control.
- Wanting to create a new SPFILE from a text file.
- Performing static parameter changes during a maintenance window.

### 2.2. Advantages

- Can be opened and viewed in an editor.
- Easy to review changes using diff.
- Easy to store in version control systems once secrets are removed.
- Can be used to start up without relying on a default SPFILE.
- Easy to create a separate lab configuration copy.

### 2.3. Limitations

- Oracle does not automatically write runtime changes back to a PFILE.
- DBAs must manage file contents and ensure the correct path at startup.
- A PFILE can drift from the runtime configuration if changes are made with SCOPE=MEMORY.
- Editing the file while the instance is running does not make the instance reload parameters automatically.
- A syntax or value error can cause startup to fail.

### 2.4. Using a PFILE to Start Up

Example starting with a specific file:

```sql
STARTUP PFILE='/u01/app/oracle/admin/ORCL/pfile/initORCL.ora';
```

The path above is only an illustration for Linux/Unix. On Windows or ASM environments, the path will differ.

If the instance is already running, you cannot simply edit the PFILE and expect parameters in memory to change. You must use ALTER SYSTEM for dynamic parameters or shut down and start up with the edited file to apply parameters that require a restart.

### 2.5. A PFILE Can Point to an SPFILE

In some configurations, a very short text init.ora file contains only an SPFILE directive pointing to a server parameter file in another location, such as an SPFILE in ASM. This helps Oracle locate a shared SPFILE, especially in RAC.

```text
SPFILE='+DATA/ORCL/PARAMETERFILE/spfile.123.456789'
```

This is an example of a pointer, not a fixed filename for every database. Do not edit or move an SPFILE in ASM by treating it like a regular text file.

## 3. SPFILE: Server Parameter File

### 3.1. Characteristics

An SPFILE is a binary file managed by Oracle. The instance can read it at startup, and Oracle can update it via ALTER SYSTEM SET with an appropriate scope.

An SPFILE stores explicitly configured parameter values, which may include:

- Default values applying to all instances.
- SID-specific values in RAC.
- Configuration settings that must persist across restarts.

Do not open an SPFILE with a text editor to edit it directly. The binary content has an internal structure; editing outside Oracle can corrupt the file or cause startup to fail.

### 3.2. Advantages

- Oracle can update it using ALTER SYSTEM.
- Values set with SCOPE=SPFILE or BOTH persist across restarts.
- Can manage shared values and per-instance values in RAC.
- DBAs do not have to manually edit text files for each parameter change.
- Integrates easily with Oracle management tools and ASM configurations.

### 3.3. Limitations

- Cannot be read/edited directly with a text editor like a PFILE.
- If the file is corrupted or contains bad values, it may need restoration from backup/PFILE.
- Requires careful tracking of currently effective values versus stored values.
- Changing the SPFILE does not mean all runtime parameters change immediately.
- In RAC, requires a clear understanding of SID='*' and per-instance overrides.

### 3.4. Determining Whether the Instance Uses an SPFILE

```sql
SHOW PARAMETER spfile;

SELECT name, value, isdefault
FROM v$parameter
WHERE name = 'spfile';
```

If an SPFILE path is displayed, the instance is using the indicated server parameter file. If not, check the startup method and specific PFILE.

### 3.5. Why Not Edit an SPFILE with an Editor?

SPFILE uses a binary format. Modifying bytes or strings inside does not guarantee Oracle can read a valid structure. Use ALTER SYSTEM or export to a PFILE via CREATE PFILE to review/edit following proper procedures.

## 4. PFILE vs. SPFILE: Comparison

| Criterion | PFILE | SPFILE |
|---|---|---|
| Format | Text | Binary |
| Directly readable by DBA | Yes | Should not be |
| Editable with text editor | Yes | No |
| Oracle automatically writes parameter changes | No | Yes, via appropriate ALTER SYSTEM |
| Persists values across restarts | Only when the file is properly edited | Yes with SCOPE=SPFILE/BOTH |
| Runtime changes | Via ALTER SYSTEM if parameter allows | Via ALTER SYSTEM if parameter allows |
| RAC per-instance values | Must be managed via file configuration | Supports values by SID |
| Ease of diff/version control | Easier | Usually exported to PFILE for review |
| Used for startup | STARTUP PFILE=... | Oracle locates SPFILE automatically or uses pointer PFILE |
| Backup/recovery | Copy text file | Export to PFILE or back up file appropriately |

A database can use an SPFILE for daily operations while maintaining a PFILE backup for inspection, comparison, or recovery.

## 5. Converting Between PFILE and SPFILE

### 5.1. Creating a PFILE from an SPFILE

This is a common way to back up an SPFILE configuration as text:

```sql
CREATE PFILE='/u01/backup/initORCL_20261114.ora'
FROM SPFILE;
```

Oracle reads the SPFILE currently used by the instance and writes its contents as a PFILE to the specified path. Ensure the directory exists and the Oracle process has write permissions.

You can also create from a specific SPFILE:

```sql
CREATE PFILE='/u01/backup/initORCL.ora'
FROM SPFILE='/u01/app/oracle/product/19c/dbhome_1/dbs/spfileORCL.ora';
```

Paths are examples only. When using ASM or RAC, the SPFILE may reside in a different location.

### 5.2. Reviewing the PFILE After Export

After creating the PFILE:

1. Read the file in an editor.
2. Verify DB_NAME, CONTROL_FILES, and critical parameters.
3. Check memory, process, undo, archive, and optimizer values.
4. Identify SID-specific lines if the database uses RAC.
5. Save the backup copy with a timestamp and appropriate file permissions.
6. Do not place passwords, secrets, or sensitive information into unprotected version control repositories.

An exported PFILE is a snapshot of the configuration stored in the SPFILE; it does not necessarily include every default value Oracle uses.

### 5.3. Creating an SPFILE from a PFILE

Example:

```sql
CREATE SPFILE='/u01/app/oracle/product/19c/dbhome_1/dbs/spfileORCL.ora'
FROM PFILE='/u01/backup/initORCL.ora';
```

After creating an SPFILE, an instance currently running from a PFILE does not automatically switch to the new SPFILE. To use the new file on the next startup, you must shut down and start up following SPFILE discovery rules or configure an appropriate pointer PFILE.

### 5.4. Creating an SPFILE in the Default Location

You can omit the destination filename so Oracle creates the SPFILE in the platform/database default location:

```sql
CREATE SPFILE FROM PFILE='/u01/backup/initORCL.ora';
```

Before running, check whether the default destination file already exists and verify the naming rules for that Oracle Home. Do not overwrite an SPFILE currently in use without a backup and rollback plan.

### 5.5. Creating a PFILE from an SPFILE in ASM

If the SPFILE resides in ASM, Oracle can read from ASM and export to a PFILE on the filesystem:

```sql
CREATE PFILE='/u01/backup/initORCL.ora'
FROM SPFILE='+DATA/ORCL/PARAMETERFILE/spfile.123.456789';
```

The ASM filename must be obtained from the actual configuration, not guessed. You can inspect database configuration using Oracle Clusterware/ASM tools and appropriate views.

### 5.6. Post-Conversion Checks

After converting:

- Verify the file was created and has a non-zero size.
- Re-read the PFILE if that was the output.
- If creating an SPFILE, inspect V$SPPARAMETER once the instance uses that file.
- Test startup with the new file in a safe environment if possible.
- Confirm SHOW PARAMETER SPFILE after starting up.

Do not treat a successful CREATE SPFILE command as proof that all parameters can start the database in every state.

## 6. SCOPE in ALTER SYSTEM SET

### 6.1. General Syntax

```sql
ALTER SYSTEM SET parameter_name = value
    SCOPE = {MEMORY | SPFILE | BOTH}
    SID = {'*' | 'instance_name'};
```

SID is relevant in RAC. For non-RAC databases, SID can be omitted per release syntax and applicability. Not every parameter allows every combination of SCOPE and SID.

### 6.2. SCOPE=MEMORY

Changes the value only in memory for the running instance:

```sql
ALTER SYSTEM SET open_cursors = 600
    SCOPE = MEMORY;
```

Characteristics:

- The change takes effect immediately if the parameter allows dynamic modification.
- Does not write the value to the SPFILE.
- Upon restart, Oracle reads the value from SPFILE/PFILE and the MEMORY value is lost.
- If the instance started with a PFILE, MEMORY is the scope usable for supported runtime changes.

MEMORY is not an option for static parameters because those parameters cannot be changed in memory while the instance is running.

### 6.3. SCOPE=SPFILE

Writes the value only to the SPFILE:

```sql
ALTER SYSTEM SET processes = 700
    SCOPE = SPFILE;
```

Characteristics:

- The value is saved for the next startup.
- The current runtime value does not change immediately.
- Typically used for static parameters that require a restart.
- Requires the instance to be using an SPFILE so Oracle has a place to write the change.

If the instance was started with a PFILE and no SPFILE is in use, attempting to write to SPFILE may fail with ORA-32001. In that case, create/prepare an SPFILE properly or edit the PFILE and restart.

### 6.4. SCOPE=BOTH

Changes both memory and SPFILE:

```sql
ALTER SYSTEM SET open_cursors = 700
    SCOPE = BOTH;
```

Characteristics:

- The runtime value is changed if the parameter is dynamic and allows immediate application.
- The new value is saved in the SPFILE to persist across restarts.
- Common choice for dynamic parameter changes when both immediate and persistent effects are desired.
- Cannot be used as a way to apply static parameters immediately.

If a parameter cannot be changed at runtime, you must use the SPFILE scope and restart as required; do not assume BOTH can bypass static restrictions.

### 6.5. Comparison Table

| SCOPE | Changes Current Memory | Writes SPFILE | Persists After Restart | Typical Use |
|---|---|---|---|---|
| MEMORY | Yes, if parameter is dynamic | No | No | Temporary testing or runtime adjustment |
| SPFILE | No | Yes | Yes | Static parameters or preparing post-restart changes |
| BOTH | Yes, if parameter is dynamic | Yes | Yes | Dynamic changes that must persist |

### 6.6. Default Value of SCOPE

If SCOPE is omitted, default behavior depends on how the instance was started and Oracle configuration. When using an SPFILE, the default is typically BOTH; when using a PFILE, the default is MEMORY. To avoid context dependence, operational scripts should specify SCOPE explicitly.

### 6.7. SCOPE Is Not SESSION

ALTER SYSTEM operates at the instance/SPFILE scope per policy. If a parameter allows session-level modification, ALTER SESSION is a separate mechanism:

```sql
ALTER SESSION SET optimizer_mode = FIRST_ROWS_10;
```

A session change does not mean the SPFILE or instance-wide value changed. When investigating parameter values, distinguish session values from system values.

## 7. Dynamic, Deferred, and Static Parameters

### 7.1. Dynamic Parameters

Dynamic parameters can be modified while the instance is running. The ISSYS_MODIFIABLE attribute in V$PARAMETER helps determine how they can be changed:

- IMMEDIATE: changes take effect immediately.
- DEFERRED: changes apply to new sessions or per deferred semantics.
- FALSE: cannot be changed dynamically at the system level; requires a restart or documented mechanism.

Not every dynamic parameter allows modification with every SCOPE.

### 7.2. Static Parameters

Parameters with ISSYS_MODIFIABLE = FALSE usually require a restart for the new value to take effect. For example, PROCESSES is a parameter that typically requires restarting after modification.

Typical procedure:

```sql
ALTER SYSTEM SET processes = 700
    SCOPE = SPFILE;
```

Then schedule a restart during a maintenance window and verify the value after startup.

### 7.3. Immediate Parameters

For parameters with ISSYS_MODIFIABLE = IMMEDIATE, the value can be changed right away:

```sql
ALTER SYSTEM SET open_cursors = 600
    SCOPE = BOTH;
```

The example only illustrates syntax; check the specific parameter and privileges before applying.

### 7.4. Deferred Parameters

For parameters with ISSYS_MODIFIABLE = DEFERRED, changes typically apply to new sessions rather than necessarily changing the value already used by existing sessions. ALTER SYSTEM syntax may require the DEFERRED keyword:

```sql
ALTER SYSTEM SET optimizer_mode = FIRST_ROWS_10
    DEFERRED SCOPE = BOTH;
```

Use only when supported by the parameter and Oracle release. Test both old and new sessions to confirm behavior.

### 7.5. Session-Modifiable Parameters

ISSES_MODIFIABLE in V$PARAMETER indicates whether a parameter can be modified using ALTER SESSION. A parameter may be session-modifiable without allowing system-wide changes in the desired way. Read the actual attribute instead of guessing from the parameter name.

### 7.6. Checking Parameter Attributes

```sql
SELECT name,
       value,
       isses_modifiable,
       issys_modifiable,
       isinstance_modifiable,
       isdefault,
       ismodified
FROM v$parameter
WHERE name IN (
    'processes',
    'open_cursors',
    'optimizer_mode',
    'sga_target'
)
ORDER BY name;
```

Columns and values may vary by release. Use this view before deciding on SCOPE and restart timing.

## 8. Reading Runtime and Stored Values

### 8.1. SHOW PARAMETER

In SQL*Plus/SQLcl:

```sql
SHOW PARAMETER processes;
SHOW PARAMETER open_cursors;
SHOW PARAMETER spfile;
```

SHOW PARAMETER is convenient for quickly checking the values displayed to the current tool session.

### 8.2. V$PARAMETER

V$PARAMETER displays parameter values for the current session and related metadata. Some parameters can differ between sessions if session-level modification is allowed.

```sql
SELECT name,
       value,
       display_value,
       isdefault,
       ismodified,
       issys_modifiable,
       isses_modifiable
FROM v$parameter
WHERE name = 'open_cursors';
```

### 8.3. V$SYSTEM_PARAMETER

V$SYSTEM_PARAMETER displays system-wide parameter values for the instance and does not reflect session-specific overrides as V$PARAMETER can.

```sql
SELECT name, value, display_value, isdefault, issys_modifiable
FROM v$system_parameter
WHERE name IN ('open_cursors', 'processes');
```

### 8.4. V$SPPARAMETER

V$SPPARAMETER shows values stored in the SPFILE:

```sql
SELECT sid,
       name,
       value,
       display_value,
       isspecified
FROM v$spparameter
WHERE name IN ('processes', 'open_cursors')
ORDER BY name, sid;
```

ISSPECIFIED indicates whether the parameter is explicitly specified in the SPFILE. If no line is explicitly configured, Oracle may use defaults or derived values per parameter rules.

### 8.5. Comparing Runtime vs. SPFILE

```sql
SELECT p.name,
       p.value AS runtime_value,
       s.value AS spfile_value,
       s.sid,
       s.isspecified
FROM v$system_parameter p
LEFT JOIN v$spparameter s
  ON s.name = p.name
WHERE p.name IN (
    'processes',
    'open_cursors',
    'optimizer_mode',
    'sga_target'
)
ORDER BY p.name, s.sid;
```

This is a simple comparison query. With RAC and SID-specific values, you must properly interpret SID='*' rows and per-instance overrides. The current runtime value may differ from the SPFILE value if SCOPE=MEMORY was used, if the parameter is auto-tuned, or if there are session-level overrides.

### 8.6. ISMODIFIED and ISDEFAULT

ISDEFAULT indicates whether the value is default per metadata. ISMODIFIED indicates whether the parameter was modified in the session/system according to the state reported by the view. These columns aid investigation but do not replace directly comparing V$SYSTEM_PARAMETER and V$SPPARAMETER.

## 9. SCOPE and RAC: SID='*' and Instance-Specific Values

### 9.1. One Shared SPFILE

In Oracle RAC, instances typically share a single SPFILE on ASM or shared storage. The SPFILE may contain:

- Default values with SID='*'.
- Override values for a specific instance, such as ORCL1 or ORCL2.

### 9.2. Setting a Value for All Instances

Example:

```sql
ALTER SYSTEM SET open_cursors = 600
    SCOPE = SPFILE
    SID = '*';
```

The wildcard value is used as the default for instances per SPFILE rules. Changing runtime memory in RAC requires considering SID and command behavior by release; verify on each instance.

### 9.3. Setting a Value for a Specific Instance

Example:

```sql
ALTER SYSTEM SET undo_tablespace = 'UNDOTBS1'
    SCOPE = SPFILE
    SID = 'ORCL1';
```

Instance ORCL1 can have its own value, while ORCL2 continues using the wildcard or its own override. The specific value must match the database structure.

### 9.4. Overrides and Wildcards

When a SID-specific value exists, the instance-specific value can override the wildcard value for that instance. Therefore, checking only the SID='*' row is insufficient to understand the final configuration of each instance.

Inspect all rows for the parameter:

```sql
SELECT sid, name, value, isspecified
FROM v$spparameter
WHERE name = 'undo_tablespace'
ORDER BY sid;
```

### 9.5. MEMORY in RAC

SCOPE=MEMORY affects runtime values, but the instance scope must be clearly understood. In RAC, a command executed on the current instance does not automatically mean all other instances received the same change in memory. If runtime changes across multiple instances are needed, use a cluster-supported method and verify values on each instance.

### 9.6. The SID Clause

SID='*' and SID='instance_name' are primarily important when managing an SPFILE shared by multiple instances. Do not use arbitrary SID names; obtain the exact instance name from cluster/database configuration. A typo can create an entry not used by the intended instance.

## 10. Changing Parameters Safely

### 10.1. Define the Objective

Before making a change, document:

- Which parameter needs to change?
- Which operational issue is it solving?
- What is the current value?
- What documentation, capacity planning, or measurement supports the new value?
- Is the parameter dynamic, deferred, or static?
- Does the change need to take effect immediately or only after restart?
- Is the scope session, instance, or entire RAC?

### 10.2. Check Current State

Collect:

- SHOW PARAMETER.
- V$PARAMETER/V$SYSTEM_PARAMETER.
- V$SPPARAMETER.
- SPFILE path.
- Instance name and database role.
- Startup options if known.
- Current resource usage and alert log if the parameter relates to capacity.

### 10.3. Back Up Configuration

If using an SPFILE, export to a PFILE before making changes:

```sql
CREATE PFILE='/u01/backup/init_before_change.ora'
FROM SPFILE;
```

Name the file with a timestamp/change ticket. For RAC, verify the backup file preserves both wildcard and instance-specific entries.

### 10.4. Choose SCOPE

| Need | Common Choice |
|---|---|
| Test a dynamic parameter temporarily | MEMORY |
| Change a static parameter for the next startup | SPFILE |
| Change a dynamic parameter immediately and persist across restarts | BOTH |
| Using PFILE, need dynamic runtime change | MEMORY or edit PFILE for next startup |
| Using PFILE, need to persist changes in SPFILE | Create appropriate SPFILE and switch startup to SPFILE |

Always verify the specific modifiability of the parameter.

### 10.5. Execute the Change

Dynamic example:

```sql
ALTER SYSTEM SET open_cursors = 700
    SCOPE = BOTH;
```

Static example:

```sql
ALTER SYSTEM SET processes = 700
    SCOPE = SPFILE;
```

Do not run example values on production without evaluating capacity, licensing, OS limits, and application behavior.

### 10.6. Verify After the Change

For dynamic parameters, check V$SYSTEM_PARAMETER and new sessions if deferred. For SPFILE-only changes, check V$SPPARAMETER. After restart, confirm the runtime value reflects the expected setting.

### 10.7. Record the Change

Save:

- The SQL statement or before/after PFILE copies.
- Before and after values.
- SCOPE and SID.
- Timestamp of the change.
- Operator/change ticket.
- Validation results.
- Rollback plan.

## 11. Resetting Parameters and Restoring Values

### 11.1. Why Is RESET Needed?

When a parameter is explicitly configured in the SPFILE, a DBA may want to remove the override so Oracle reverts to the default value or corresponding wildcard value. ALTER SYSTEM RESET is used to remove an entry set in the SPFILE for the appropriate SID scope.

### 11.2. RESET in SPFILE

Example removing an instance-specific setting:

```sql
ALTER SYSTEM RESET open_cursors
    SCOPE = SPFILE
    SID = 'ORCL1';
```

Example removing a wildcard setting:

```sql
ALTER SYSTEM RESET open_cursors
    SCOPE = SPFILE
    SID = '*';
```

Recheck V$SPPARAMETER afterward. RESET does not mean every instance runtime immediately reverts to default; if only SPFILE is reset, the change takes effect at the next startup.

### 11.3. Rolling Back Using the Previous Value

If you know the previous value, you can set it back using ALTER SYSTEM SET with the corresponding SCOPE and SID. This is often the clearest approach when rolling back a specific value.

### 11.4. Rolling Back from a PFILE Backup

If an SPFILE change causes a startup failure:

1. Use a validated PFILE backup.
2. Start the instance with STARTUP PFILE=... if possible.
3. Check the alert log and startup errors.
4. Fix the incorrect value in the PFILE.
5. Create a new SPFILE from the PFILE if needed.
6. Restart using the verified SPFILE.

Do not overwrite the original file before keeping a backup, and do not delete the old SPFILE before confirming the new file works.

## 12. Starting Up with a PFILE When SPFILE Has Issues

### 12.1. When Is This Needed?

Common situations:

- The SPFILE is corrupted or unreadable.
- A static parameter was misconfigured, preventing the instance from starting.
- Needing to test a corrective configuration without destroying the old SPFILE.
- Needing to test a different parameter set in a recovery environment.

### 12.2. Create a PFILE from Backup

If the SPFILE is still readable, export to a PFILE:

```sql
CREATE PFILE='/u01/backup/init_recovery.ora'
FROM SPFILE;
```

If the SPFILE is unreadable, use a previously saved PFILE backup or a safely managed configuration copy.

### 12.3. Edit the PFILE

Fix the specific parameter causing the error. Do not delete parameters en masse because many parameters may be required by the database architecture, control files, RAC, or recovery configuration.

Verify:

- DB_NAME and DB_UNIQUE_NAME.
- CONTROL_FILES.
- MEMORY_TARGET/SGA/PGA settings.
- PROCESSES and related limits.
- UNDO_TABLESPACE.
- ARCHIVELOG/FRA settings if applicable.
- RAC-specific parameters.

### 12.4. Start Up with the PFILE

```sql
STARTUP PFILE='/u01/backup/init_recovery.ora' NOMOUNT;
```

Then mount/open following the appropriate recovery procedure. Do not run OPEN if the database requires recovery or is not ready.

### 12.5. Create a New SPFILE

Once the PFILE configuration has been verified:

```sql
CREATE SPFILE='/u01/app/oracle/product/19c/dbhome_1/dbs/spfileORCL.ora'
FROM PFILE='/u01/backup/init_recovery.ora';
```

Schedule a shutdown/startup so the instance uses the new SPFILE. If using ASM/RAC, create the SPFILE at the shared location designated by the cluster configuration and update pointer PFILEs if necessary.

### 12.6. Post-Recovery Checks

- SHOW PARAMETER SPFILE displays the correct active file.
- V$SPPARAMETER contains the expected values.
- V$SYSTEM_PARAMETER reflects runtime values.
- The instance is in the appropriate state.
- The alert log shows no new parameter/startup errors.
- Other RAC instances start and pick up the proper SID-specific settings.

## 13. Multi-Valued Parameters and Special Characters

### 13.1. List Parameters

Some parameters take multiple values, such as CONTROL_FILES or LOG_ARCHIVE_DEST_n. When changing them, you must keep all required entries:

```sql
ALTER SYSTEM SET control_files =
    '/u01/oradata/ORCL/control01.ctl',
    '/u02/oradata/ORCL/control02.ctl'
    SCOPE = SPFILE;
```

This is illustrative syntax. Confirm actual paths and the exact number of control files before modifying; missing a control file can prevent the database from mounting.

### 13.2. Parameters with Commas or Strings

Some parameters accept strings containing lists or special characters. Use proper SQL quoting and verify the stored value afterward. Avoid concatenating dynamic SQL from untrusted input.

### 13.3. Parameters with Units

Some memory or time parameters support suffixes like K/M/G or time units. Follow the exact format in the parameter documentation. Do not infer that every numeric parameter accepts suffixes.

### 13.4. Boolean Parameters

Boolean parameters typically use TRUE/FALSE or values defined in documentation. Do not use arbitrary strings.

## 14. MEMORY, SPFILE, and PFILE in Real-World Scenarios

### 14.1. Testing a Dynamic Change First

A DBA wants to test increasing OPEN_CURSORS during a check period:

1. Check the current value and ISSYS_MODIFIABLE.
2. Set SCOPE=MEMORY.
3. Observe session/app behavior.
4. If unsuitable, set the old value back in memory.
5. If suitable and worth keeping, apply SCOPE=BOTH via the change process.

This uses MEMORY for temporary testing, though impact and rollback must still be evaluated.

### 14.2. Changing a Static Parameter

A DBA wants to increase PROCESSES:

1. Check current process usage and OS/process limits.
2. Back up the SPFILE.
3. Set SCOPE=SPFILE.
4. Verify V$SPPARAMETER.
5. Schedule a restart.
6. After restart, confirm the runtime value and process capacity.

Do not expect the change to take effect immediately in the running instance.

### 14.3. Preparing a Change Only for the Next Restart

You can prepare SPFILE configurations while the database continues running. This is useful when a restart is planned for a later maintenance window. Clearly document that the change is not yet active at runtime so operations teams do not misread the state.

### 14.4. Instance Started with a PFILE

If SHOW PARAMETER SPFILE has no path, verify whether startup used a PFILE. In that case:

- ALTER SYSTEM SCOPE=MEMORY can still be used for dynamic parameters.
- SCOPE=SPFILE/BOTH requires an SPFILE to be in use per Oracle rules.
- For persistent changes, edit the PFILE or create an SPFILE and switch startup to it.

### 14.5. RAC with Per-Instance Values

If each instance has a different undo tablespace or thread, SID-specific configuration in the SPFILE may be necessary. Check both wildcards and overrides, then verify runtime on each instance.

## 15. Common Data Dictionary Views and Verification Commands

### 15.1. Check Active SPFILE

```sql
SHOW PARAMETER spfile;
```

### 15.2. Check Current Parameters

```sql
SELECT name, value, display_value, isdefault,
       issys_modifiable, isses_modifiable,
       isinstance_modifiable
FROM v$parameter
WHERE name LIKE '%memory%'
   OR name IN ('processes', 'open_cursors', 'undo_tablespace')
ORDER BY name;
```

### 15.3. Check System Parameters

```sql
SELECT name, value, display_value, ismodified
FROM v$system_parameter
WHERE name IN (
    'processes',
    'open_cursors',
    'undo_tablespace',
    'optimizer_mode'
)
ORDER BY name;
```

### 15.4. Check SPFILE Entries

```sql
SELECT sid, name, value, isspecified
FROM v$spparameter
WHERE isspecified = 'TRUE'
ORDER BY name, sid;
```

### 15.5. Check Non-Dynamic Parameters

```sql
SELECT name, value, issys_modifiable
FROM v$parameter
WHERE issys_modifiable = 'FALSE'
ORDER BY name;
```

### 15.6. Check the Instance

```sql
SELECT instance_name,
       host_name,
       version,
       status,
       database_status
FROM v$instance;
```

In RAC, run or query GV$ views to inspect state across multiple instances:

```sql
SELECT inst_id, instance_name, host_name, status
FROM gv$instance
ORDER BY inst_id;
```

### 15.7. Check the Alert Log

When startup fails after a parameter change, the alert log is a vital source of evidence. Check ORA errors, parameter values, file paths, memory allocation, and startup steps completed.

## 16. Managing Parameters in RAC and Clusterware

### 16.1. SPFILE in ASM

RAC typically stores the SPFILE on ASM so all instances can access it. Oracle Clusterware holds information about the SPFILE location used to start the database. Do not move or rename an SPFILE solely with filesystem operations; update the configuration using appropriate Oracle tools.

### 16.2. Shared and Specific Values

A RAC SPFILE can store shared SID='*' values and per-instance overrides. Parameters such as UNDO_TABLESPACE typically require per-instance values; others can use shared values.

### 16.3. Cluster-Wide Changes

When setting SID='*', understand whether the command modifies the SPFILE for all instances and what semantics apply to memory on running instances. Verify values on each instance using GV$SYSTEM_PARAMETER or by connecting directly to each instance.

### 16.4. Single-Instance Changes

If only one instance needs to change, use its specific SID and verify the exact instance name. Ensure the wildcard is not misunderstood as overriding an instance-specific setting.

### 16.5. Using SRVCTL/Clusterware

In RAC, database startup configuration and SPFILE location may be managed by Clusterware. Use SRVCTL and Oracle Clusterware tools to inspect/update database resource configuration per release guidelines. ALTER SYSTEM manages parameters; SRVCTL manages database resources in the cluster. The two layers must remain consistent.

## 17. Common Errors and Misconceptions

| Symptom | Common Cause | Resolution Direction |
|---|---|---|
| Change lost after restart | Used SCOPE=MEMORY | Set SPFILE/BOTH or edit PFILE |
| SHOW PARAMETER does not change immediately | Used SCOPE=SPFILE | Restart if parameter requires it or to load the new value |
| ORA-32001 | Requested writing SPFILE but instance does not use SPFILE | Confirm PFILE startup; create/switch to SPFILE |
| ORA-02095 | Parameter cannot be modified dynamically | Use SCOPE=SPFILE and restart if documentation requires |
| ORA-01078 on startup | Parameter file incorrect/invalid | Read alert log, fix PFILE/restore SPFILE |
| Instance fails to mount | CONTROL_FILES or foundational parameter wrong | Use a validated PFILE backup |
| RAC instances use different values | SID-specific override or wildcard | Check V$SPPARAMETER and GV$SYSTEM_PARAMETER |
| DBA opens SPFILE in editor and sees strange characters | SPFILE is binary | Export PFILE to read |
| PFILE edited but runtime unchanged | Instance is running and does not reload the file | ALTER SYSTEM or restart with PFILE |
| BOTH does not apply static parameter | Parameter is not dynamic | Use SPFILE and restart |
| Runtime differs from SPFILE | SCOPE=MEMORY, session override, auto-adjust, or different SID | Compare V$PARAMETER, V$SYSTEM_PARAMETER, V$SPPARAMETER |

## 18. Recommended Change and Rollback Workflow

### Before the Change

1. Identify the parameter, purpose, and target value.
2. Check ISSYS_MODIFIABLE, ISSES_MODIFIABLE, and ISINSTANCE_MODIFIABLE.
3. Determine whether PFILE or SPFILE is in use.
4. For RAC, check SID wildcards and instance overrides.
5. Back up SPFILE to PFILE and save the current configuration.
6. Check resources, dependencies, and restart requirements.
7. Define the rollback command/file.

### During the Change

1. Choose SCOPE explicitly.
2. Choose the correct SID scope.
3. Execute ALTER SYSTEM or edit the PFILE per plan.
4. Log the command, operator, and timestamp.
5. Check V$SYSTEM_PARAMETER or V$SPPARAMETER accordingly.

### After the Change

1. If dynamic, verify runtime effect.
2. If deferred, verify new sessions.
3. If static, restart within the change window.
4. Check values after startup.
5. Inspect the alert log and database status.
6. Monitor workloads and applications.
7. Update the build/configuration manifest.

### Rollback

1. Use the saved previous value or PFILE backup.
2. Choose the right SCOPE and SID to restore.
3. If static, restart again per plan.
4. Verify both runtime and persistent values.
5. Confirm the database and applications return to a stable state.

## 19. Lab Exercise: PFILE, SPFILE, and SCOPE

Perform in a lab database or staging environment with appropriate SYSDBA privileges. Do not practice restarts or static parameter changes on production outside the change process.

### Step 1 — Identify the Startup File

```sql
SHOW PARAMETER spfile;
SELECT name, value FROM v$parameter WHERE name = 'spfile';
```

Note whether the instance uses an SPFILE or PFILE.

### Step 2 — Inspect Several Parameters

```sql
SELECT name, value, issys_modifiable,
       isses_modifiable, isinstance_modifiable
FROM v$parameter
WHERE name IN ('open_cursors', 'processes', 'optimizer_mode');
```

Record which parameters are dynamic, deferred, or static.

### Step 3 — Export a PFILE

```sql
CREATE PFILE='/u01/backup/init_lab_before.ora'
FROM SPFILE;
```

Read the PFILE and note the configured parameters.

### Step 4 — Test SCOPE=MEMORY

Choose a safe dynamic parameter in the lab. Record its initial value, change it with SCOPE=MEMORY, and check V$SYSTEM_PARAMETER. Then restart the lab and confirm the temporary value is no longer retained if the SPFILE does not hold that value.

### Step 5 — Test SCOPE=SPFILE

Choose an appropriate dynamic or static parameter. Use SCOPE=SPFILE, check V$SPPARAMETER, and confirm the current runtime value has not changed. Restart per plan and recheck runtime.

### Step 6 — Test SCOPE=BOTH

For a safe dynamic parameter, set SCOPE=BOTH. Compare V$SYSTEM_PARAMETER and V$SPPARAMETER before/after, then restart the lab to confirm the value persists.

### Step 7 — Compare PFILE and SPFILE

Export the PFILE again and compare with the previous copy. Note the saved changes. Do not directly edit the binary SPFILE.

### Step 8 — Test a Static Parameter

In the lab, choose a parameter documented as static. Test SCOPE=SPFILE, check the stored value, and plan a restart. Do not attempt to use MEMORY to apply a static parameter.

### Step 9 — Test RESET

Create a test override in the SPFILE, use ALTER SYSTEM RESET with the right SID, then inspect V$SPPARAMETER. Confirm the wildcard/default value is used per rules after restart.

### Step 10 — RAC (if available)

In a RAC lab, set a wildcard value and a SID-specific value. Check V$SPPARAMETER and GV$SYSTEM_PARAMETER on each instance. Confirm the instance override applies as intended.

### Step 11 — Record Results

| Test | Runtime Value Before | SPFILE Value Before | SCOPE | Runtime After | SPFILE After | After Restart |
|---|---|---|---|---|---|---|
| MEMORY |  |  | MEMORY |  |  |  |
| SPFILE |  |  | SPFILE |  |  |  |
| BOTH |  |  | BOTH |  |  |  |
| Static parameter |  |  | SPFILE |  |  |  |
| RESET |  |  | SPFILE |  |  |  |

Fill in actual lab results; do not use illustrative values from documentation as measurements.

## 20. Operational Checklist

- [ ] Identified whether the instance uses a PFILE or SPFILE.
- [ ] Backed up configuration before making changes.
- [ ] Did not directly edit the binary SPFILE.
- [ ] Checked ISSYS_MODIFIABLE and ISSES_MODIFIABLE.
- [ ] Distinguished dynamic, deferred, and static parameters.
- [ ] Selected SCOPE=MEMORY/SPFILE/BOTH explicitly.
- [ ] Determined whether the change requires a restart.
- [ ] Checked V$PARAMETER/V$SYSTEM_PARAMETER for runtime values.
- [ ] Checked V$SPPARAMETER for persistent values.
- [ ] Checked ISDEFAULT/ISSPECIFIED and SID.
- [ ] For RAC, checked wildcards and per-instance overrides.
- [ ] Verified values on each instance after the change.
- [ ] Reviewed the alert log after restart.
- [ ] Have a PFILE backup or recovery plan.
- [ ] Have rollback commands/files and a change record.
- [ ] Verified applications and workloads after the change.
- [ ] Did not confuse SCOPE=MEMORY with ALTER SESSION.
- [ ] Did not assume SPFILE-only changes are already active at runtime.

## 21. Self-Check Questions

1. How do PFILE and SPFILE differ in format and management?
2. At which startup step does Oracle use the parameter file?
3. How do you determine whether an instance is using an SPFILE?
4. Why should you not edit an SPFILE with a text editor?
5. When should a PFILE be used to start up?
6. What is the purpose of CREATE PFILE FROM SPFILE?
7. In what situation is CREATE SPFILE FROM PFILE used?
8. Why does creating a new SPFILE not automatically switch a running instance from PFILE to SPFILE?
9. Where does SCOPE=MEMORY make changes?
10. Why are MEMORY changes lost after a restart?
11. What effect does SCOPE=SPFILE have on the current runtime value?
12. What kind of parameters is SCOPE=BOTH suited for?
13. How does the default value of SCOPE depend on the startup file?
14. How must a parameter with ISSYS_MODIFIABLE=FALSE be handled?
15. How do IMMEDIATE and DEFERRED differ?
16. What does ISSES_MODIFIABLE indicate?
17. How do V$PARAMETER, V$SYSTEM_PARAMETER, and V$SPPARAMETER differ in value sources?
18. What do ISSPECIFIED and ISDEFAULT help determine?
19. What do SID='*' and SID='instance_name' mean in RAC?
20. Why is it necessary to check both wildcards and SID-specific overrides?
21. Under what circumstances does ORA-32001 typically occur?
22. What does ORA-02095 suggest about a parameter?
23. What type of configuration does ALTER SYSTEM RESET remove?
24. How do you recover when an SPFILE contains a value that prevents the instance from starting?
25. Why should you back up a PFILE before changing an SPFILE?
26. When is SCOPE=MEMORY used for testing?
27. How do you confirm a dynamic change has taken effect?
28. Why must you check the alert log after restarting?
29. What role does Resource Manager/Clusterware play when managing an SPFILE in RAC?
30. What information must be recorded in a parameter change record?

**Principle to remember:** PFILE is a text file; SPFILE is a binary file managed by Oracle. SCOPE=MEMORY changes only runtime, SCOPE=SPFILE saves only for the next startup, and SCOPE=BOTH changes both when the parameter allows. Check ISSYS_MODIFIABLE to distinguish immediate, deferred, and static parameters; static parameters require a restart. In RAC, inspect both SID='*' and per-instance overrides. Always back up configurations, specify SCOPE/SID explicitly, verify V$SYSTEM_PARAMETER alongside V$SPPARAMETER, and keep a recovery PFILE before making critical changes.
