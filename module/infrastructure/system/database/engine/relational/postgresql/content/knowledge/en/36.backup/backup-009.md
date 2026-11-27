# Manifests, `pg_verifybackup`, and Verifying PostgreSQL Backups

A PostgreSQL backup only has value when it can restore the needed data at the moment it is needed. A backup command exiting with code 0 proves only that the backup tool finished its creation step; it does not prove every file remained intact after copying, uploading, storing, or transferring over the network.

PostgreSQL provides the **backup manifest** and the **`pg_verifybackup`** utility to verify the integrity of physical base backups created by `pg_basebackup`. The manifest records every file belonging to the backup along with its size and checksum; `pg_verifybackup` reads the manifest, compares it against actual contents, and can also verify required WAL segments and parse WAL records.

Still, checksum verification does not replace an actual test restore. A trustworthy backup pipeline uses multiple layers:

1. Create a consistent base backup.
2. Store the manifest alongside the backup and protect the manifest's integrity.
3. Run `pg_verifybackup` on the copy stored at the destination.
4. Ensure required WAL is present and readable.
5. Test restoring into an isolated environment.
6. Start PostgreSQL, verify recovery, and check data.
7. Run business checks and measure recovery duration.

This lesson explains manifest structure, how to use `pg_verifybackup`, what the tool verifies, limitations to understand, and how to build a repeatable backup verification workflow.

## 1. Learning Objectives

After this lesson, you will be able to:

1. Explain the role of the backup manifest in PostgreSQL physical backups.
2. Describe file, size, checksum, and WAL range details recorded in a manifest.
3. Create base backups with manifests using `pg_basebackup`.
4. Choose an appropriate checksum algorithm and distinguish checksums from digital signatures.
5. Run `pg_verifybackup` and interpret its output/exit status.
6. Use manifest path, WAL directory, progress, and checking-mode options suited to your version.
7. Distinguish file checksum verification, WAL verification, and restorability verification.
8. Understand the implications of plain format, tar format, tablespaces, and separately stored WAL.
9. Detect missing files, extra files, size mismatches, checksum mismatches, and invalid WAL.
10. Understand why modifying both a file and its manifest invalidates checksum verification.
11. Combine `pg_verifybackup` with restore drills, PITR, and application validation.
12. Schedule, archive reports, manage retention, and alert on backup verification.

## 2. What Is a Backup Manifest?

A backup manifest is a file describing the contents of a physical base backup. With `pg_basebackup` on manifest-capable versions, PostgreSQL generates a file named:

```text
backup_manifest
```

The manifest typically sits at the root directory of a plain-format backup. For other backup formats, manifest placement depends on how `pg_basebackup` writes output.

The manifest supplies a structured list of files belonging to the backup along with verification metadata. It also records WAL ranges needed for backup consistency.

### 2.1. Why Is a Manifest Needed?

When a backup passes through multiple stages:

```text
PostgreSQL primary
      |
      v
pg_basebackup
      |
      v
Local staging directory
      |
      v
Compression / encryption / packaging
      |
      v
Object storage / backup repository
      |
      v
Restore staging host
```

Files can go missing, get truncated, get overwritten, or corrupt during any copy step. A manifest lets you verify that files in the backup still match the metadata and checksums recorded when the backup was created.

### 2.2. A Manifest Is Not a Backup

A manifest is purely metadata describing a backup. It holds no database pages and cannot replace data files, WAL, or the base backup.

### 2.3. A Manifest Does Not Protect Itself

If an attacker or buggy process alters both a backup file and the manifest so they match, checksum verification still passes. Therefore, protect the manifest via access control, immutable storage, digital signatures, or independently stored digests.

## 3. Key Information Inside a Manifest

The manifest is JSON. Specific fields and manifest format versions can change across PostgreSQL major versions, but typically cover these groups:

| Group | Meaning |
| --- | --- |
| Manifest version | Manifest format version |
| PostgreSQL version | Server version that created the backup |
| System identifier | Source cluster identifier |
| Files | List of files belonging to the backup |
| File size | File size at manifest creation time |
| File checksum | Content checksum under the selected algorithm |
| WAL ranges | WAL intervals required to bring the backup to consistency |
| Manifest checksum | Checksum verifying the manifest content itself |

### 3.1. File List

Each file entry can record relative path, size, and checksum. Paths tell the tool which files must exist in the backup.

### 3.2. File Size

Size detects truncated or resized files. A file with the exact expected size can still hold altered bytes, which is why checksums are needed.

### 3.3. File Checksum

Checksums are computed over file bytes when the manifest is generated. During verification, the tool reads the current file, recomputes the checksum, and compares.

### 3.4. WAL Ranges

The manifest logs WAL information linked to the backup. This tells `pg_verifybackup` which segments must exist and enables checking WAL readability/parsing.

### 3.5. Manifest Checksum

The manifest itself includes a checksum to detect internal manifest corruption. This checksum is not a digital signature and does not prove the manifest came from a trusted source.

## 4. Checksums in the Manifest

A checksum is a value derived from a file's bytes. If content changes, the checksum changes with high probability.

PostgreSQL supports several checksum algorithms for manifests depending on version. Common options include CRC32C and SHA-2 family algorithms such as SHA256, SHA384, or SHA512.

### 4.1. CRC32C

CRC32C is fast and useful for catching accidental storage/transmission bit errors. It is not a cryptographic hash and is not designed to resist an active attacker crafting colliding contents.

### 4.2. SHA256

SHA256 provides a stronger integrity checksum. It is far better suited than CRC32C when reducing intentional collision risks matters.

### 4.3. Checksums Are Not Encryption

Checksums do not encrypt data or hide backup contents. If backups hold PII or secrets, use encryption at rest/in transit and strict access controls separately.

### 4.4. Checksums Are Not Digital Signatures

SHA256 inside a manifest does not prove who generated the backup. If an attacker can modify both files and the manifest, they can recompute fresh checksums.

To authenticate provenance:

- Compute a digest of the manifest post-backup.
- Sign the digest using a key managed outside the backup repository.
- Store the signature or digest in a system with independent write permissions.
- Protect private signing keys via KMS/HSM or secret management.
- Before restoring, verify the signature/digest first before trusting the manifest.

### 4.5. Selecting the Algorithm During Backup

Example:

```bash
pg_basebackup --pgdata=/backup/staging/base_2026_11_14 --format=plain --wal-method=stream --manifest-checksums=SHA256 --progress --verbose
```

This is a lab example. Verify supported options and algorithms using `pg_basebackup --help` for your exact PostgreSQL version.

### 4.6. Algorithm Compatibility

`pg_verifybackup` must understand the algorithm recorded in the manifest. Use a binary matching the backup version and check help/version before automating.

## 5. Creating a Backup with a Manifest Using `pg_basebackup`

`pg_basebackup` creates a physical base backup from a running PostgreSQL server over the replication protocol.

Example:

```bash
pg_basebackup --host=db-primary.example.internal --port=5432 --username=backup_user --pgdata=/backup/staging/base_2026_11_14 --format=plain --wal-method=stream --manifest-checksums=SHA256 --progress --verbose
```

This requires a role with replication privileges, configured authentication, reachable networking, and adequate destination space. Never place production passwords directly in command history.

### 5.1. Default Manifest

On supported versions, `pg_basebackup` creates a backup manifest by default. `--no-manifest` disables manifest creation; `pg_verifybackup` then has no manifest to verify against.

### 5.2. Choosing Plain Format

With plain format, `pg_basebackup` writes a directory tree structured like `PGDATA`, with the manifest sitting in the backup tree. This is the simplest workflow for running `pg_verifybackup` directly against the directory.

### 5.3. Tar Format

`pg_basebackup` also supports tar format. Manifest handling and whether `pg_verifybackup` can read archives directly depend on version/tooling. A well-controlled workflow extracts tar files into a staging directory following the proper backup layout, places the manifest where expected, and verifies the extracted tree. Never verify a single tar file assuming it is a `PGDATA` directory.

If using a dedicated backup manager or custom archive format, use that tool's verification workflow while still verifying contents restored into staging.

### 5.4. Do Not Omit the Manifest to Save a Few Bytes

Manifests are tiny compared to data files. Omitting the manifest discards a vital verification layer and forces custom metadata tracking.

## 6. WAL Collection Methods During Base Backups

`pg_basebackup` offers three primary WAL methods:

| Method | How It Works | Trade-Off |
| --- | --- | --- |
| `stream` | Streams WAL concurrently during backup | Convenient for self-contained backups; needs enough WAL sender connections |
| `fetch` | Fetches required WAL at backup end | Primary must retain enough WAL throughout backup |
| `none` | Does not collect WAL with backup | Needs a separate archive/recovery path to complete and restore |

### 6.1. `stream`

```bash
pg_basebackup -D /backup/base_stream -Fp -X stream -P
```

WAL is streamed during the backup. The primary normally needs an extra WAL sender for the separate WAL stream, in addition to the connection copying data.

### 6.2. `fetch`

```bash
pg_basebackup -D /backup/base_fetch -Fp -X fetch -P
```

WAL is fetched after the data portion completes. If the primary recycles required segments before fetch runs, the backup fails. Retention must suffice for the entire backup duration.

### 6.3. `none`

```bash
pg_basebackup -D /backup/base_no_wal -Fp -X none -P
```

With `none`, the backup does not bundle WAL like `stream`/`fetch`. You need an archive with full WAL coverage and a matching recovery procedure. Never treat a data-only directory as a standalone recoverable backup.

### 6.4. WAL Ranges and Backup Consistency

Online physical backups need WAL to bring data files to a consistent state on recovery. The manifest records required WAL ranges so verification checks the corresponding WAL.

## 7. Running `pg_verifybackup`

For a plain-format backup directory:

```bash
pg_verifybackup /backup/staging/base_2026_11_14
```

On success, `pg_verifybackup` exits with status 0 and reports the backup verified. If missing files, wrong sizes, checksum mismatches, or invalid WAL are detected, it logs errors and exits non-zero.

### 7.1. Running on the Destination Copy

A solid workflow:

1. Create the backup in staging.
2. Verify staging to catch errors immediately after backup.
3. Copy/upload the backup and manifest to the repository.
4. Download or mount the backup on a verify host.
5. Run `pg_verifybackup` on the destination copy.

The second verification tests the transport and storage layers between staging and repository.

### 7.2. Pass the Right Directory

The primary argument is the backup directory—not a database name, a running `PGDATA`, or a path to an individual data file.

### 7.3. Never Run on a Live Server's `PGDATA`

Verify an immutable backup or staging copy. Never modify files while `pg_verifybackup` is reading them; results will not reflect a consistent snapshot.

### 7.4. Run with Appropriate Privileges

The process must read all backup files, including files inside mapped tablespaces. Grant necessary read-only privileges; avoid running as root unless required.

## 8. `pg_verifybackup` Options

Exact options depend on version. Always check:

```bash
pg_verifybackup --help
pg_verifybackup --version
```

Common options:

| Option | Purpose |
| --- | --- |
| `--manifest-path` | Specify manifest path when not in the default location |
| `--wal-directory` | Specify directory containing WAL to verify if stored separately |
| `--progress` | Display verification progress |
| `--quiet` | Suppress normal output |
| `--exit-on-error` | Stop immediately on the first error |
| `--no-parse-wal` | Skip WAL parsing step |
| `--skip-checksums` | Skip file checksum verification |

Not every option exists in every major version. Check help output of the deployed binary.

### 8.1. Progress

```bash
pg_verifybackup --progress /backup/base_2026_11_14
```

Helpful on large backups to confirm forward progress.

### 8.2. Specifying Manifest Path

```bash
pg_verifybackup --manifest-path=/backup/metadata/backup_manifest /backup/base_2026_11_14
```

Use only when the manifest is stored separately per a valid workflow. The manifest must describe the exact backup directory being verified.

### 8.3. Separate WAL Directory

```bash
pg_verifybackup --wal-directory=/backup/wal/pg_cluster_a /backup/base_2026_11_14
```

Useful when WAL required for the backup is stored outside the backup data directory. Verify the directory holds the exact segments/timelines required by the manifest.

### 8.4. `--no-parse-wal`

```bash
pg_verifybackup --no-parse-wal /backup/base_2026_11_14
```

Skips WAL parsing. It can reduce runtime in certain workflows, at the cost of reduced verification coverage. Avoid as a full verification mode when verifying WAL structural readability matters.

### 8.5. `--skip-checksums`

```bash
pg_verifybackup --skip-checksums /backup/base_2026_11_14
```

Skips file content checksum checks. It is not equivalent to full integrity verification. Use only for targeted diagnostics alongside another verification layer.

### 8.6. `--exit-on-error`

By default the tool may continue to report multiple errors in one pass. `--exit-on-error` fails fast on the first error, fitting pipelines or targeted failure investigations.

## 9. What Does `pg_verifybackup` Check?

Core scope:

1. Reads and validates manifest structure.
2. Resolves listed backup files.
3. Checks file presence and sizes.
4. Recomputes checksums and compares against the manifest, unless skipped.
5. Detects missing files or unexpected files per tool check rules.
6. Identifies required WAL segments from the manifest.
7. Verifies related WAL files and parses WAL records unless parsing is disabled.

### 9.1. Missing Files

If a file listed in the manifest is absent from the backup directory, verification fails.

### 9.2. Truncated Files

If a file is smaller or differs in size from the manifest entry, size checks catch it.

### 9.3. Same Size, Different Content

Checksums catch cases where file size matches yet bytes were corrupted.

### 9.4. Extra Files

Files outside the manifest may indicate a mixed backup directory or post-backup modification. The tool reports unexpected files per its directory traversal rules. Investigate before ignoring; never blindly delete unfamiliar files in the original backup.

### 9.5. Missing or Corrupted WAL

The manifest records required WAL ranges. `pg_verifybackup` detects missing required segments or WAL that fails to parse per format/version.

### 9.6. Does Not Check Business Semantics

Valid checksums do not prove all business rows are present, foreign keys or business invariants hold, extensions load on the restore host, applications connect, or the backup restores within RTO. Those require restore tests and application-level validation.

## 10. File Checksums vs. Data Page Checksums

PostgreSQL has two easily confused concepts:

| Concept | What It Checks | How It Is Used |
| --- | --- | --- |
| Backup manifest checksum | Backup file bytes vs. checksum recorded in manifest | `pg_verifybackup` |
| Data page checksum | Whether database pages carry valid page checksums | Checked when pages are read; `pg_checksums` can check offline |

### 10.1. Manifest Checksums

Verifies whether current backup files match the files at manifest creation time.

### 10.2. Data Checksums

Data page checksums are enabled at cluster initialization or via supported procedures in applicable versions. They detect page corruption when PostgreSQL reads pages.

### 10.3. `pg_checksums`

`pg_checksums` is a separate tool for checking or managing page checksums under supported conditions. Cluster checks normally require a cleanly stopped server; never run offline checksum tools on a data directory actively used by PostgreSQL.

### 10.4. Two Complementary Layers

`pg_verifybackup` verifies copied files match the manifest; page checksums verify integrity at the database page level. After restoring into an isolated cluster and cleanly stopping the server, you can run `pg_checksums` if configured and supported by version.

## 11. WAL Verification and `pg_waldump`

WAL is mandatory to bring an online base backup to consistency. `pg_verifybackup` uses PostgreSQL's WAL parsing capabilities (via matching version tools/libraries) to inspect records inside relevant WAL segments.

### 11.1. Why Parse WAL?

A WAL file that exists with the right size can still hold corrupted bytes. Parsing catches structural corruption or invalid records.

### 11.2. Does Not Equal Successful Replay to Any Target

WAL parsing does not replace restore/recovery. Recovery also depends on base backups, timelines, control files, archive chains, configs, and server replay execution.

### 11.3. WAL Version Compatibility

WAL formats change across PostgreSQL major versions. Use `pg_verifybackup`/`pg_waldump` matching the backup's major version; never use an older binary and treat its result as conclusive.

### 11.4. WAL Directory

If backups keep WAL outside the backup directory, pass the proper directory option. Never point at an empty WAL directory and assume the backup has full WAL.

### 11.5. `--no-parse-wal`

Skipping WAL parsing removes a verification layer. In production workflows, if skipped for speed, document the reduced verification coverage and compensate with restore drills.

## 12. Backup Formats and Tablespaces

A PostgreSQL cluster can span `PGDATA` and multiple tablespaces at different paths.

### 12.1. Plain Format

Plain format writes a directory tree usable as `PGDATA` for restore. This is the most direct layout for `pg_verifybackup` to read files and manifests.

### 12.2. Tar Format

Tar format packs backup components into archive files. Before verifying with a workflow expecting a directory tree, fully extract all archives to proper locations, including manifests and tablespaces, preserving mapping/path semantics.

### 12.3. Tablespaces

If the source uses tablespaces, base backups hold tablespace data outside `PGDATA` or mapped per `pg_basebackup` options. During verification, directories referenced by the manifest must exist at expected paths.

### 12.4. Tablespace Mapping

Example:

```bash
pg_basebackup -D /backup/base -Fp -X stream -T /var/lib/postgresql/tablespace_fast=/backup/tablespaces/fast
```

Paths are illustrative; mappings must match actual source tablespaces. Record mappings in backup metadata so restore hosts recreate the layout accurately.

### 12.5. Symlinks

Tablespaces can be represented by symlinks inside `PGDATA`. When copying/restoring, ensure target directories exist with proper permissions and symlinks never accidentally point to production data directories.

### 12.6. Verify the Entire File Tree

Verifying only `PGDATA` while skipping tablespace directories yields incomplete checks. Verify the entire backup layout per the manifest and how the backup was created.

## 13. Manifests and Backups After Compression/Encryption

A backup repository may store backups as compressed/encrypted objects rather than plain directories.

### 13.1. Verify Before or After Decompression?

`pg_verifybackup` must read a backup file tree in a layout it understands. For compressed/encrypted objects, the typical flow is:

1. Check object metadata and transport checksums if available.
2. Download the object.
3. Decrypt using a securely managed key.
4. Decompress into an isolated staging directory.
5. Run `pg_verifybackup` on the decompressed file tree.

### 13.2. Compression Checksums

Archive containers may have their own container checksums. They verify container integrity, but do not replace file-level manifest verification after extraction.

### 13.3. Encryption Authentication

Use authenticated encryption or equivalent integrity checks to detect ciphertext tampering. Never rely on unauthenticated encryption alone to prove backups are unaltered.

### 13.4. Checking Object Sizes and Metadata

Record object size, storage version ID, ETag/checksum per storage provider semantics, upload timestamp, and backup ID. Some ETags are not SHA256 hashes of object content; read provider documentation carefully.

### 13.5. Never Overwrite Verified Backups

Place each backup under an immutable path/version or unique ID. Never upload a new backup to the same prefix/filename in a way that mutates an already-verified artifact.

## 14. Protecting Manifests and Provenance Chains

Checksums are useful only if the manifest is trustworthy.

### 14.1. Threat Model

Consider two scenarios:

- Accidental errors: disk, network, RAM, or storage corrupts bytes.
- Intentional modification: an actor with write access alters both backup files and the manifest.

Manifest checksums handle accidental corruption well. They do not protect against a privileged actor modifying the manifest itself.

### 14.2. Signing the Manifest

After backup finishes:

1. Read `backup_manifest`.
2. Compute a digest using an organization-approved algorithm.
3. Sign the digest with a private key kept outside the backup repository.
4. Store the signature, key ID, backup ID, and metadata in an independent store.
5. On verification, verify the signature first and then run `pg_verifybackup`.

Conceptual diagram:

```text
backup_manifest
      |
      v
SHA-256 digest
      |
      v
Sign with private key
      |
      v
signature + key_id + backup_id
      |
      v
Store in immutable metadata repository
```

Do not treat this diagram as literal signing commands; use your organization's KMS/signing tools.

### 14.3. Immutable Storage

Object lock, versioning, or WORM retention reduces the chance backups get modified/deleted prematurely. Audit retention modes, bypass permissions, and admin accounts.

### 14.4. Least Privilege

Backup writers can create new objects but should lack permission to delete or overwrite historical backups. Restore operators should have read access without default delete rights.

### 14.5. Provenance Metadata

Link each backup to its backup ID, cluster/system identifier, PostgreSQL major/minor version, start/end timestamps, backup tool version, manifest digest/signature, WAL method, tablespace mappings, encryption key ID, storage object/version ID, and verification result/timestamp.

## 15. A Complete Backup and Verification Pipeline

```text
1. Preflight
   |
2. pg_basebackup creates base backup + manifest
   |
3. Check pg_basebackup exit status
   |
4. pg_verifybackup in staging
   |
5. Sign/hash manifest and record metadata
   |
6. Compress/encrypt/upload
   |
7. Download/restore artifact into verify staging
   |
8. Verify signature + pg_verifybackup
   |
9. Restore drill in isolated environment
   |
10. Application smoke tests
   |
11. Record verification entry
   |
12. Policy-based retention/lifecycle
```

### 15.1. Preflight

Check disk space, network, replication role, available WAL senders, backup destination, encryption keys, and backup schedule.

### 15.2. Backup

Run `pg_basebackup` with manifest, WAL method, and tablespace mappings configured. Capture stdout/stderr and exit status.

### 15.3. Verify Staging

Run `pg_verifybackup` immediately after creation. If it fails, do not promote the artifact as a verified backup.

### 15.4. Publish Artifact

Copy/upload to the repository with object versioning/immutability. Never alter the file tree after signing the manifest without creating a new artifact.

### 15.5. Verify at Destination

Check the artifact after downloading/restoring to staging. This catches transport, storage, or decompression errors.

### 15.6. Restore Drill

Start an isolated PostgreSQL instance from the backup using matching WAL/archive paths and run validation queries.

## 16. Example Creating and Verifying a Plain Backup

Create a fresh, empty destination directory dedicated to one backup:

```bash
pg_basebackup --host=db-primary.example.internal --port=5432 --username=backup_user --pgdata=/backup/staging/pg_2026_11_14T020000Z --format=plain --wal-method=stream --manifest-checksums=SHA256 --progress --verbose
```

After the command succeeds:

```bash
pg_verifybackup --progress /backup/staging/pg_2026_11_14T020000Z
```

Inspect metadata:

```bash
ls -lah /backup/staging/pg_2026_11_14T020000Z
```

The folder typically contains items like `PG_VERSION`, `base`, `global`, `pg_wal`, `pg_tblspc`, `backup_label`, and `backup_manifest`, depending on backup layout/version/tablespaces.

### 16.1. Never Arbitrarily Copy Extra Files into the Backup

To store logs, signatures, or separate metadata, use a sibling directory or repository metadata path. Avoid mixing operational files into the data tree verified by the manifest.

### 16.2. Never Modify Files After Verification

If you compress, encrypt, or copy afterward, re-verify the final artifact post-decryption/decompression. A staging check before upload does not validate bytes after upload.

## 17. Example Verifying When WAL Is Stored Separately

If your workflow stores required WAL in a separate directory:

```bash
pg_verifybackup --wal-directory=/backup/wal/pg_cluster_a /backup/staging/base_2026_11_14
```

Ensure the directory contains the exact WAL segments and timelines required by the manifest. Segment filenames can match across different timelines; recovery metadata and history files still matter.

If using an external WAL archive, fetch/copy required segments into a staging WAL directory before verifying, or use backup tooling supporting archive verification. Never point arbitrarily at an archive root shared by multiple clusters.

## 18. Interpreting `pg_verifybackup` Errors

Common error categories:

| Error | Possible Cause | How to Investigate |
| --- | --- | --- |
| Unreadable manifest | Missing file, malformed JSON, permissions | Check manifest path and copy workflow |
| File missing | Backup copy missed a file | Cross-check manifest paths, storage logs |
| Size mismatch | File truncated or modified | Compare sizes, object versions, transfer logs |
| Checksum mismatch | Bytes altered or manifest mismatch | Compare source/destination digests, disk/network |
| Unexpected file | Extra file added or mixed directory | Trace which step created the file |
| WAL missing | Missing segment in WAL range | Check WAL method, archive, and WAL directory |
| WAL parse error | Corrupted segment, wrong version, truncated bytes | Check segment, timeline, tool version |
| Permission denied | Verify user cannot read file | Fix read-only permissions on staging |
| Unsupported format/version | Incompatible tool | Use matching major/version binary |

### 18.1. Checksum Mismatches Must Never Be Ignored

Never use `--skip-checksums` to turn a corrupted backup into a verified backup. Locate another copy, inspect source and destination, and recreate the backup if root cause is unclear.

### 18.2. Missing Files

A missing file may come from incomplete copy, unmounted tablespace, lifecycle deletion, or incorrect extraction. Never create empty placeholder files to make verify pass.

### 18.3. WAL Parse Errors

Identify segment name, timeline, and tool version. Compare against independent WAL archive copies if available. A corrupted segment can prevent recovery to a consistent state.

### 18.4. Permission Errors

Run verification under an account with read access to all directories, including tablespace symlink targets. Write permission is unnecessary purely for verification.

## 19. What Does `pg_verifybackup` NOT Prove?

Even when verification passes, understand its limits:

- Does not prove the backup can boot on every OS/architecture.
- Does not prove PostgreSQL binaries/extensions are compatible on the restore host.
- Does not prove configs outside `PGDATA` were backed up.
- Does not prove secrets, certificates, service files, or external scripts were saved.
- Does not prove the WAL archive holds every segment beyond the range required by the backup manifest.
- Does not prove PITR to every timestamp in the retention window without checking the archive chain.
- Does not prove applications can connect or function properly.
- Does not prove business data invariants.
- Does not measure actual RTO.
- Does not protect backups from an actor empowered to modify both files and the manifest.

### 19.1. PostgreSQL Configuration

Config files may sit outside `PGDATA` or be managed by automation/secret managers. Backing up the data directory does not guarantee those files were backed up properly.

### 19.2. Roles and Database Objects

Physical base backups contain cluster data files, yet restore runbooks still need awareness of roles, extension binaries, shared libraries, external services, and environment dependencies.

### 19.3. Encryption Keys

If a backup is encrypted, losing the key renders a checksum-perfect backup unreadable. Backup key material and key recovery procedures must be tested independently.

### 19.4. External Dependencies

Applications may depend on object storage, secrets, DNS, certificates, message brokers, or service endpoints. Restoring the database alone does not restore these dependencies.

## 20. Test Restores: The Most Important Verification Layer

A restore drill proves a backup can become a working PostgreSQL instance in the target environment.

### 20.1. Isolated Environment

Restore into a separate VM/container/host:

- Never point at the production primary.
- Use a separate port.
- Block unnecessary outbound networking.
- Prevent production apps from connecting automatically.
- Use separate tablespace paths.
- Use test credentials.

### 20.2. Preparing the Backup

Download the backup artifact, verify signature/digest, decrypt/decompress, and run `pg_verifybackup`.

### 20.3. Preparing Recovery Configuration

Depending on PostgreSQL version and recovery goal, prepare configuration:

- `restore_command` if WAL archive is needed.
- `recovery.signal` for archive recovery/PITR in modern versions.
- `recovery_target_time`/LSN/name when needed.
- `primary_conninfo`/`standby.signal` if the goal is a standby rather than standalone PITR.
- Tablespace mappings and permissions.

Do not use one generic recovery config for every drill type. Standalone base backup restore tests and standby bootstrap tests have different goals.

### 20.4. Starting Up

```bash
pg_ctl -D /restore/lab/pgdata -l /restore/lab/postgres.log start
```

Command is illustrative; your environment's service manager/container runtime may differ.

### 20.5. Inspecting the Server

```sql
SELECT version(), pg_is_in_recovery(), current_timestamp;
```

If a PITR instance has promoted/completed recovery, `pg_is_in_recovery()` normally returns `false`. If the goal is a replaying standby, it returns `true`. Interpret against the drill's expected state.

### 20.6. Inspecting Databases and Tables

```sql
SELECT datname
FROM pg_database
ORDER BY datname;

SELECT schemaname, count(*) AS table_count
FROM pg_tables
WHERE schemaname NOT IN ('pg_catalog', 'information_schema')
GROUP BY schemaname
ORDER BY schemaname;
```

These queries are only initial smoke tests; run domain-specific business queries to validate data.

## 21. Checking Applications and Business Invariants

A backup can start cleanly yet still lack data expected by the business.

Example checks:

- Customer/order counts over time windows.
- Daily transaction totals.
- Total amounts per currency.
- Orphan foreign key counts if custom integrity rules exist.
- Non-negative inventory balances if invariant.
- Tenant counts and partitioned data.
- Sequence/identity values aligned with data.

### 21.1. Row Counts

Compare row counts against baselines or backup metadata, without expecting every table to equal live source counts if the backup came from an earlier point.

### 21.2. Aggregate Checks

Compute sums, min/max timestamps, and counts by status to catch certain missing-data anomalies. Choose checks rooted in domain semantics.

### 21.3. Referential Checks

PostgreSQL maintains declared constraint consistency inside physical backups, yet application-level references outside the database or separately replicated/ETL data need extra validation.

### 21.4. Application Smoke Tests

Start an application instance pointed at the restore host, execute read-only workflows, and verify responses. Never let test apps send emails, process payments, fire webhooks, or trigger side effects against production.

### 21.5. Never Run Destructive Tests on Original Backups

Create disposable restore copies or snapshot clones. Keep original backup artifacts immutable.

## 22. PITR Verification vs. Base Backup Verification

Base backup verification proves the file tree/WAL range described by the manifest is intact. PITR verification also proves the archive chain can replay up to a target.

### 22.1. Checking the Archive Chain

Ensure valid base backup, continuous WAL from the needed point, present timeline history files, working `restore_command`, and functioning archive decryption/decompression.

### 22.2. Restoring to a Target Time

In an isolated environment, configure the recovery target and start the instance. Verify the server stops recovery at the intended target or reaches the expected state per version behavior.

### 22.3. Checking Data Before/After Target

Pick a known transaction marker or timestamped business event. Verify the event prior to target is present and the event after target is absent if required by the test.

### 22.4. Testing Multiple Points in Time

One PITR test at a recent timestamp does not prove older archives are intact. Test across varying backup ages periodically.

## 23. Measuring RTO and RPO in Restore Drills

### 23.1. RPO

Recovery Point Objective is acceptable data loss measured in time. With PITR, measure the newest recoverable point based on actually available WAL archives.

### 23.2. RTO

Recovery Time Objective is the target duration to bring the system back online. Measure from the start of the restore/failover workflow until applications pass smoke tests.

### 23.3. Milestones to Record

| Milestone | Meaning |
| --- | --- |
| Backup start/end | Base backup creation time |
| Upload complete | Artifact reached repository |
| Verify complete | `pg_verifybackup` finished |
| Download/decrypt complete | Backup ready for restore |
| Restore start/end | Data files prepared |
| PostgreSQL ready | Server accepts connections |
| Recovery complete | WAL replay reached target |
| Application ready | Smoke tests passed |

### 23.4. Do Not Use `pg_verifybackup` Time as RTO

Verification is just one step. Downloading, decrypting, extracting, WAL replay, extension setup, and application validation often take most of the time.

## 24. Checking Backups After Copying and Object Storage

An artifact can pass staging verification yet get corrupted after upload.

### 24.1. Double Verification

- Verify before upload: checks `pg_basebackup` output.
- Verify after download: checks the artifact post-storage/transport.

### 24.2. Object Versions

Record immutable object version IDs or generation IDs so restores pull the exact verified version. Never rely solely on mutable object keys.

### 24.3. Multipart Uploads

Ensure uploads finish completely, object sizes match, and multipart ETags are interpreted per provider rules. ETags are not always content MD5s.

### 24.4. Cross-Region Copies

If backups replicate to a DR region, verify objects in the target region via download/verify or trustworthy end-to-end checksums. Never rely solely on replication status metadata.

### 24.5. Restore Credentials

Backup repositories must remain accessible during disasters. Never make restore workflows depend solely on a credential service or region that could be down.

## 25. Checking Tablespaces and External Paths

Tablespace data may live outside `PGDATA`. Backup manifests/verification work properly only when all paths are handled correctly.

### 25.1. Inventory Tablespaces

```sql
SELECT spcname, pg_tablespace_location(oid) AS location
FROM pg_tablespace
ORDER BY spcname;
```

### 25.2. Record Mappings

Record source tablespace paths and destination mappings. Restore hosts may use different paths, provided the layout is reconstructed accurately.

### 25.3. Permissions and Ownership

The PostgreSQL service account needs access to tablespace directories. Verify accounts need read permissions; restore accounts need ownership/write permissions as required by the server.

### 25.4. Missing Mounts

If a tablespace mount is missing during restore, the server may fail to start or miss data. Verify mounts/volumes before `pg_verifybackup` and before restore startup.

## 26. Backup Manifests and PostgreSQL Versions

Manifests have their own format version tied to server version/system identifier. `pg_basebackup` and `pg_verifybackup` binaries can change across major versions.

### 26.1. Use Matching Tool Versions

Record:

```bash
pg_basebackup --version
pg_verifybackup --version
```

Use binaries of the same major version or a version documented by PostgreSQL as compatible with the backup. WAL parsing especially requires exact format alignment.

### 26.2. Do Not Assume the Manifest Format Is Immutable

JSON fields can be added across major versions. Never write custom parsers assuming a rigid schema that breaks on unknown fields.

### 26.3. Backups from Other Clusters

System identifiers distinguish source clusters. Before restoring, verify metadata so staging, production, or unrelated cluster backups are never mixed up.

### 26.4. Minor Versions

Minor updates maintain compatibility within the same major series, yet extensions/binary environments should still be validated during restore tests.

## 27. `pg_verifybackup` in Automation

Shell pipelines should abort if backup or verification fails:

```bash
set -euo pipefail
BACKUP_DIR="/backup/staging/base_20261114T020000Z"
mkdir -p "$BACKUP_DIR"
pg_basebackup --host="$PGHOST" --port="$PGPORT" --username="$PGUSER" --pgdata="$BACKUP_DIR" --format=plain --wal-method=stream --manifest-checksums=SHA256 --progress
pg_verifybackup --progress "$BACKUP_DIR"
```

This is a Bash example. Manage credentials via `.pgpass`/secret managers; never expose passwords on command lines or in logs.

### 27.1. Exit Status

Mark a backup verified only if `pg_basebackup` exits cleanly, the manifest exists and is readable, `pg_verifybackup` exits 0, and backup metadata is durably recorded.

### 27.2. Never Mask Errors Across Pipes

If pipelines pipe output like `pg_basebackup | tee`, use `set -o pipefail` so upstream command failures are not masked by `tee`.

### 27.3. Atomic Promotion

Write backups into uniquely named staging directories. Promote status/metadata to verified or publish immutable paths only after verification passes. Prevent restore consumers from seeing half-written backups.

### 27.4. Never Reuse Old Directories

Use a fresh directory/object ID for every backup. Reusing directories leaves stale files that cause confusion and verification failures.

## 28. Recording Verification Results

Every verification should create an immutable or append-only record:

| Field | Example |
| --- | --- |
| `backup_id` | `pg-prod-a-20261114T020000Z` |
| `cluster_system_id` | System identifier from backup metadata |
| `source_version` | PostgreSQL major/minor |
| `backup_tool_version` | `pg_basebackup` version |
| `verify_tool_version` | `pg_verifybackup` version |
| `manifest_digest` | SHA256 of manifest |
| `checksum_algorithm` | `SHA256` |
| `wal_method` | `stream` |
| `backup_started_at` | UTC timestamp |
| `backup_completed_at` | UTC timestamp |
| `verified_at` | UTC timestamp |
| `verify_status` | `VERIFIED` / `FAILED` |
| `restore_test_status` | `PASSED` / `FAILED` / `NOT_RUN` |
| `restore_duration` | Seconds |
| `restore_target` | Host/isolated environment ID |
| `artifact_version` | Immutable object version |

### 28.1. Separate Verify Status from Restore Status

Do not conflate two distinct statuses:

- `VERIFIED`: `pg_verifybackup` succeeded.
- `RESTORE_TESTED`: backup was restored and tested successfully.

A backup can be verified without ever having been restore-tested.

### 28.2. Log Failure Details

Capture command, tool version, exit status, stderr, failed file path, WAL segment, and timestamp. Keep secrets/credentials out of logs.

### 28.3. Never Record `VERIFIED` Before Command Completion

If a process times out or an agent disconnects, status must stay `UNKNOWN`/`IN_PROGRESS` until the process result is confirmed.

## 29. Verification Frequency

A typical policy layers cadences:

- Verify every backup right after creation.
- Re-verify after uploading/replicating to the repository.
- Run periodic restore tests.
- Run periodic PITR drills to multiple target times.
- Run restore tests before major upgrades or backup tooling changes.

Exact cadence depends on RPO/RTO, data volume, restore cost, and compliance requirements.

### 29.1. Verify Every Backup

`pg_verifybackup` is much cheaper than restoring a full cluster, so run it on every artifact if resource budgets permit.

### 29.2. Purposeful Sampling for Restore Drills

If restoring every backup is too costly, use a sampling policy covering recent/older backups, regions, storage classes, encryption keys, and backup methods.

### 29.3. After System Changes

Run restore drills whenever changing PostgreSQL major versions, backup agents or `pg_basebackup` binaries, compression/encryption formats, object storage providers/regions, tablespace layouts, WAL archive/restore scripts, or KMS/key rotations.

## 30. Checking Retention and Historical Restorability

A backup can pass verification today yet be wiped tomorrow by a misconfigured lifecycle policy.

### 30.1. Retention Chains

List retained base backups and the WAL ranges needed for each backup/PITR window.

### 30.2. WAL Archive Cleanup

Never delete WAL simply because a standby has replayed it. WAL may still be needed by older base backups, PITR windows, or DR regions.

### 30.3. Object Lifecycle

Check expiration, storage class transitions, legal holds, object locks, and version deletions. Policies must retain both base backups and needed WAL.

### 30.4. Restore Point Coverage

Verify recoverability across points throughout the retention window, not just the most recent point.

## 31. Troubleshooting: Manifest Does Not Exist

Causes:

- Backup created with `--no-manifest`.
- Backup created by a tool/version without manifest support.
- Manifest stored elsewhere.
- Manifest omitted during packaging or copy.
- Wrong backup directory.

Remediation:

1. Check the backup command and tool version.
2. Search for the manifest inside the artifact/package per known layout.
3. Without a manifest, `pg_verifybackup` cannot run under standard manifest workflows.
4. Recreate the backup with a manifest or use the backup tool's supported verification mechanism.

Never create an empty manifest just to make `pg_verifybackup` run.

## 32. Troubleshooting: Checksum Mismatch

A file checksum differing from the manifest can stem from copy/upload/download errors, storage corruption, post-backup edits, decompression/decryption faults, mismatched manifests, or tool/format incompatibilities.

Procedure:

1. Record the file path and checksum algorithm.
2. Compare the manifest digest against the independently signed/stored digest.
3. Inspect object versions and transfer logs.
4. Compare against pre-upload verified staging if available.
5. Re-download the object into fresh staging.
6. Re-verify.
7. If mismatch persists, mark the backup `FAILED` and take a fresh backup.

Never edit manifest checksums to match a corrupted file.

## 33. Troubleshooting: Incomplete WAL Range

Possible causes:

- Backup used `wal_method=none` without supplying an archive.
- `-X fetch` missed segments recycled by the primary.
- Separate WAL directory was not mounted/copied.
- Archive cleanup deleted still-needed segments.
- Timeline history file missing.
- Corrupted or incompatible segment.

Remediation:

1. Read the WAL range inside the manifest.
2. Identify start/end segments and timeline.
3. Search inside backup `pg_wal` and the archive repository.
4. Check the archive catalog/backup tool metadata.
5. Restore missing segments into the staging WAL directory.
6. Re-run `pg_verifybackup`.
7. Perform a restore test once the WAL chain is verified.

## 34. Troubleshooting: `pg_verifybackup` Succeeds Yet Restore Fails

This is why verification and restore must never be conflated.

Causes:

- Incompatible PostgreSQL binaries/extensions.
- Wrong tablespace paths or mounts.
- Failing `restore_command`.
- Missing segments in the WAL archive outside the verified portion.
- Misconfigured recovery target.
- Incorrect file permissions or ownership.
- Missing `postgresql.conf`/external configs.
- Inaccessible encryption keys or certificates.
- Storage/architecture differences.

Remediation:

1. Inspect PostgreSQL startup/recovery logs.
2. Determine whether failure occurs pre-recovery, during WAL replay, or post-startup.
3. Check versions, extensions, and shared libraries.
4. Check tablespaces, permissions, and mounts.
5. Check archive fetch and timeline.
6. Check recovery settings.
7. Record RTO impact and update the restore runbook.

## 35. Backup Verification and Logical Backups

`pg_verifybackup` is designed for physical base backups with manifests under PostgreSQL workflows. It is not a universal verification tool for every backup type.

### 35.1. `pg_dump`

`pg_dump` produces logical dumps. Dump files do not contain a physical-backup `backup_manifest`.

### 35.2. `pg_restore`

For custom/directory/tar dumps, validate archive structure with the matching tool and run a test restore into a fresh database. Example:

```bash
pg_restore --list /backup/logical/app.dump
```

This lists archive entries; it does not prove restore succeeds. Run `pg_restore` into a test database.

### 35.3. SQL Dumps

For plain SQL dumps, check file digests, gzip integrity if compressed, and execute with `psql` into a lab database. An actual restore proves far more than checking file existence.

### 35.4. Backup Managers

If using Barman, pgBackRest, or another backup tool, run that tool's verify/check commands alongside restore tests. Never assume `pg_verifybackup` replaces a backup manager's metadata/indexes.

## 36. Comparing Verification Layers

| Layer | Detects | Does Not Prove |
| --- | --- | --- |
| File exists/size | Missing or truncated files | Correct bytes |
| Manifest checksum | Bytes differing from manifest | Trustworthy manifest if tampered |
| Manifest signature | Provenance/integrity per key | Successful restore |
| WAL parse | Certain WAL structural errors | Recovery to every target |
| `pg_verifybackup` | File tree and WAL within tool scope | Business correctness/RTO |
| Restore test | Server starts/recovers in test env | Every production workflow works |
| Application tests | Selected business flows function | All data/business rules |
| PITR drill | Recovery to tested target | All targets across all times |

A mature workflow layers checks proportional to risk rather than relying on one green indicator.

## 37. Operational Checklist for Backup Manifests

### During Backup Creation

- [ ] `pg_basebackup` version matches PostgreSQL server.
- [ ] Backup directory is new and empty.
- [ ] Manifest generated (`--no-manifest` not used unintentionally).
- [ ] Checksum algorithm recorded.
- [ ] WAL method matches recovery design.
- [ ] Tablespaces mapped/backed up completely.
- [ ] Exit code and logs saved.

### During Verification

- [ ] `pg_verifybackup` version matches.
- [ ] Manifest belongs to the right backup ID.
- [ ] All file paths readable.
- [ ] Checksums verified.
- [ ] Required WAL directory/segments present.
- [ ] WAL parsing not skipped when full verification is required.
- [ ] Exit status is 0.
- [ ] Verification report saved.

### In Repository Storage

- [ ] Backup artifact has a unique immutable ID/version.
- [ ] Manifest digest/signature stored independently.
- [ ] Encryption keys and restore credentials accessible in DR.
- [ ] Object size/checksum/version metadata recorded.
- [ ] Backup re-verified after copy/upload.
- [ ] Retention does not purge needed base backups/WAL.

### During Restore Drills

- [ ] Restored into an isolated environment.
- [ ] Tablespaces and external dependencies prepared.
- [ ] PostgreSQL/extension versions match.
- [ ] WAL archive/recovery targets configured properly.
- [ ] Server starts and recovery completes.
- [ ] Query smoke tests pass.
- [ ] Business invariants verified.
- [ ] RTO/RPO measured.

## 38. PostgreSQL Practice Exercises

Perform on lab/staging and simulated repositories. Never intentionally corrupt or delete production backups to test errors.

1. **Manifest:** explain the role of `backup_manifest`.
2. **Manifest path:** locate the manifest inside a plain-format backup.
3. **JSON:** inspect the metadata sections inside the manifest.
4. **System identifier:** explain why recording the source cluster matters.
5. **File list:** identify a file path, size, and checksum entry.
6. **WAL range:** describe why the manifest records WAL ranges.
7. **Checksum:** distinguish CRC32C and SHA256.
8. **Security:** explain how checksums differ from digital signatures.
9. **Base backup:** create a plain-format backup with a manifest.
10. **Checksum option:** create a backup with SHA256 if supported by your version.
11. **No manifest:** explain the consequences of `--no-manifest`.
12. **Verify:** run `pg_verifybackup` on the newly created backup.
13. **Progress:** run verification with `--progress`.
14. **Version:** check `pg_basebackup` and `pg_verifybackup` versions.
15. **Help:** use `--help` to list options of your current binaries.
16. **Plain format:** explain why a directory tree simplifies verification.
17. **Tar format:** design an extract-to-staging workflow before verification.
18. **WAL stream:** create a backup with `-X stream` and inspect WAL files.
19. **WAL fetch:** explain retention requirements when using `-X fetch`.
20. **WAL none:** describe archive requirements when using `-X none`.
21. **Missing file:** create a lab copy missing one file and observe verification failure.
22. **Truncate:** truncate a file in the lab copy and read the error.
23. **Checksum mismatch:** alter bytes while preserving file size and run verify.
24. **Unexpected file:** add a test file and observe tool behavior.
25. **Manifest missing:** move the manifest in the lab copy and read the error.
26. **Manifest path:** use `--manifest-path` to point to the right manifest.
27. **WAL directory:** test `--wal-directory` with separately stored WAL.
28. **WAL parse:** run default verification and explain the parsing step.
29. **No parse:** run `--no-parse-wal` and describe the reduced coverage.
30. **Skip checksum:** run `--skip-checksums` on the lab copy and explain why it cannot be marked fully verified.
31. **Exit status:** write a script that fails if `pg_verifybackup` returns non-zero.
32. **Fail fast:** test `--exit-on-error` and compare output against default behavior.
33. **Tablespaces:** create a lab tablespace and back up a cluster with tablespaces.
34. **Mapping:** use tablespace mapping and record paths.
35. **Symlinks:** inspect `pg_tblspc` and target directories.
36. **Permissions:** run verification as a read-only user.
37. **File integrity:** compare manifest checksums against an independent digest.
38. **Manifest signature:** design a workflow signing the manifest with an external key.
39. **Tampering:** explain why editing a file and manifest together passes checksum checks.
40. **Immutable storage:** design object lock/versioning for backup artifacts.
41. **Compression:** compress a backup, decompress into staging, and verify.
42. **Encryption:** encrypt an artifact, decrypt it, and verify the file tree.
43. **Transport:** copy a backup to another host and verify after download.
44. **Object version:** record the object version ID of a verified backup.
45. **WAL range:** determine required segments from the manifest.
46. **Timelines:** explain why timeline history matters for restores.
47. **`pg_waldump`:** use the appropriate tool to inspect WAL records in the lab.
48. **Tool compatibility:** explain the risks of using a binary from a different major version.
49. **Page checksums:** distinguish manifest checksums from data page checksums.
50. **`pg_checksums`:** research prerequisites for running offline checks.
51. **Restore:** restore a backup into a fresh lab `PGDATA`.
52. **Startup:** confirm PostgreSQL starts cleanly from the backup.
53. **Recovery:** inspect logs and `pg_is_in_recovery()` state.
54. **PITR:** restore to a `recovery_target_time` in the lab.
55. **WAL archive:** verify `restore_command` fetches segments from the archive.
56. **Missing WAL:** simulate missing WAL in the lab and observe recovery failure.
57. **Application test:** run a read-only smoke test on the restored database.
58. **Business invariants:** choose an aggregate to validate data.
59. **Sequences:** check sequence values after restore.
60. **Extensions:** verify extension binaries exist on the restore host.
61. **External configs:** inventory configs/secrets stored outside `PGDATA`.
62. **Tablespace restore:** restore into a different mapped path.
63. **RTO:** measure download, extract, verify, restore, and startup durations.
64. **RPO:** determine the newest recoverable point in the WAL archive.
65. **Restore drill:** write a complete restore runbook.
66. **Backup metadata:** design a record with `backup_id`, `system_id`, version, and `manifest_digest`.
67. **Verify status:** separate `VERIFIED` from `RESTORE_TESTED`.
68. **Automation:** write a shell pipeline with `set -euo pipefail`.
69. **Pipe status:** explain the role of `pipefail` when using `tee`.
70. **Atomic promotion:** publish backups only after verification succeeds.
71. **Retry:** design retries without overwriting verified artifacts.
72. **Archive formats:** distinguish `pg_verifybackup` from `pg_restore --list`.
73. **Logical dumps:** establish how to verify `pg_dump` via test restores.
74. **Backup managers:** research verify/restore checks in Barman or pgBackRest.
75. **Retention:** determine WAL archives to retain for active base backups.
76. **Monitoring:** build a dashboard for verify success/failure and backup age.
77. **Alerting:** alert when the latest backup remains unverified.
78. **Region DR:** download and verify a backup in a secondary DR region.
79. **Key recovery:** rehearse retrieving encryption/signing keys during DR.
80. **Comprehensive design:** build a pipeline with base backup, manifest signing, immutable upload, destination verification, PITR restore drill, business smoke tests, RTO/RPO metrics, and retention for production PostgreSQL.

## 39. Common Anti-Patterns

| Anti-pattern | Consequence | Remediation |
| --- | --- | --- |
| Checking only `pg_basebackup` exit code | Misses post-copy file corruption | Run `pg_verifybackup` |
| Using `--no-manifest` then calling `pg_verifybackup` | No metadata to verify against | Create backups with manifests |
| Treating checksums as signatures | Manifest can be tampered alongside data | Sign/store digests independently |
| Verifying only in staging | Misses upload/storage corruption | Re-verify after download |
| Using `--skip-checksums` to pass pipelines | Bypasses byte verification | Flag reduced coverage and investigate |
| Always using `--no-parse-wal` | Skips WAL structure checks | Parse WAL per policy |
| Verifying `PGDATA` while skipping tablespaces | Misses data files | Verify full backup layout |
| Arbitrarily mixing major-version binaries | WAL/manifest incompatibility | Use matching tool versions |
| Assuming `pg_verifybackup` proves restore | Recovery can still fail | Run restore drills |
| Assuming verify proves business correctness | Business data may be wrong/missing | Run business validation |
| Dropping the manifest | Loses future verification baseline | Store alongside backup |
| Overwriting old backup paths | Destroys verified artifacts | Use unique immutable backup IDs |
| Missing WAL when using `-X none` | Backup cannot finish recovery | Retain WAL archive chain |
| Failing to test encryption keys | Backups cannot be decrypted | Run key recovery drills |
| Restoring on production | Risks data loss/side effects | Restore into isolated environments |
| Skipping tablespace mount tests | Server fails to boot | Verify mappings/volumes |
| Testing only startup | Unknown if app works | Run smoke tests and invariants |
| Merging `VERIFIED` and `RESTORE_TESTED` | Overstates confidence | Track both statuses separately |
| Not measuring RTO/RPO | Unknown SLA compliance | Record durations and recovery points |
| Deleting WAL archives based on current standby | Breaks PITR | Manage retention via backup catalog |

## 40. Backup Verification Checklist

### Artifacts and Manifest

- [ ] Backup ID and source cluster identified.
- [ ] Manifest exists and matches the right backup.
- [ ] Manifest digest/signature verified if required by policy.
- [ ] Tool versions and checksum algorithm recorded.
- [ ] Backup tree and tablespaces complete.

### `pg_verifybackup`

- [ ] Executed on artifacts after copy/upload completes.
- [ ] File presence and size checks pass.
- [ ] Checksum verification enabled.
- [ ] WAL range contains all required segments.
- [ ] WAL parsing performed per policy.
- [ ] Exit status equals 0.
- [ ] Output/report archived.

### Restore

- [ ] Base backup and matching WAL archive paths available.
- [ ] Restored into an isolated environment.
- [ ] PostgreSQL version/extensions/tablespaces match.
- [ ] Server startup/recovery succeeds.
- [ ] Query smoke tests pass.
- [ ] Business invariants verified.
- [ ] RTO/RPO measured.

### Lifecycle

- [ ] Artifact has an immutable version.
- [ ] Backup and WAL retention aligned with PITR policy.
- [ ] Encryption/signing keys have a DR access path.
- [ ] Restore drills scheduled and results logged.
- [ ] Alerts configured for unverified backups or overdue restore tests.

## 41. Summary

Backup manifests and `pg_verifybackup` provide a crucial verification layer for PostgreSQL physical base backups:

```text
pg_basebackup
    |
    +--> Data files
    |
    +--> Required WAL
    |
    +--> backup_manifest
              |
              v
       pg_verifybackup
              |
              v
       File / size / checksum / WAL checks
              |
              v
       Restore drill + PITR + app tests
```

Key principles:

- **The manifest describes the backup**, listing file entries, sizes, checksums, and WAL ranges; it does not replace data files or WAL.
- **`pg_verifybackup` verifies the file tree and WAL within supported scope.** Use a version-matched binary and inspect options that reduce coverage carefully.
- **Checksums are not digital signatures.** Protect manifests with independent digests/signatures, strict permissions, and immutable storage.
- **WAL is part of consistency and recovery.** Backups excluding WAL need complete archive/recovery paths.
- **Tablespaces and files outside `PGDATA` must be accounted for.** Verify the entire layout and mappings.
- **Verified does not mean restore-tested.** Only restore drills validate startup, WAL replay, extensions, tablespaces, and configs.
- **Successful restore does not mean the application works.** Run business checks, smoke tests, and measure RTO/RPO.
- **Re-verify after upload/copy.** A staging check does not prove objects in a DR region remain intact.
- **Retain backups and WAL under the same recovery policy.** Bad cleanup can leave base backups intact yet incapable of PITR.

A reliable backup system does more than generate files cleanly. It proves artifacts are intact, WAL is complete, restores succeed in target-like environments, and recovery meets the timelines committed by the organization.
