# Documenting Local Setup, Troubleshooting, and Recovery

A solid local setup guide lets new team members spin up a project without asking around, lets developers reproduce issues before pushing code, and helps the team distinguish application bugs from environment discrepancies. Within a CI/CD workflow, this documentation also bridges developer machines and runners: matching toolchain versions, required configurations, verification commands, and evidence collection practices.

Documentation should never just list a single command to launch the app. It must explain prerequisites, how to start dependent services, environment-specific configurations, startup order, how to run tests, where logs live, how to diagnose common failures, and recovery steps when a process or local data enters an unknown state.

This guide explains how to build repeatable local development documentation for a CI/CD project—especially suited to Java applications using Gradle or Maven with containerized dependencies. The same principles apply to projects using other languages or build systems.

## 1. Goals of Local Development Documentation

A new team member should be able to follow the documentation to:

- Verify their machine has all required tools and versions.
- Check out the right source code and branch.
- Prepare local configuration without leaking secrets.
- Start the database, message broker, or other dependent services.
- Build and run the application.
- Run unit tests, integration tests, and quality checks.
- Inspect logs and identify failing requests or jobs.
- Reproduce bugs with describable data and conditions.
- Stop processes, recover the environment, and resume work.
- Produce a context-rich report so others can assist.

Documentation must also distinguish safe operations from data-destructive ones. For example, restarting the app typically preserves database volumes; removing volumes can wipe all local data. Readers need to know the impact before running a command.

## 2. Structure of a Local Development Guide

An easy-to-follow document should match the order in which a reader executes steps:

1. Purpose, scope, and owner.
2. Local architecture and dependencies.
3. Software, version, and resource requirements.
4. How to clone/check out source code.
5. How to configure environment variables and secrets.
6. How to start dependent services.
7. How to build, run, and test.
8. How to verify the application is ready.
9. Locations of logs, metrics, and traces.
10. How to troubleshoot common errors.
11. How to stop, recover, and reset the environment.
12. How to collect evidence and request help.

Each step should provide concrete commands, expected outputs, and what to do when outcomes diverge from expectations. Avoid writing "configure the database as usual" or "run tests normally," because newcomers do not know what "normal" looks like.

### Document Header Template

| Field | Information to Document |
|---|---|
| Service/repository | Service name and repository |
| Owner | Responsible team |
| Supported OS | Windows, macOS, Linux, or supported scope |
| Toolchain | JDK, Gradle/Maven, Docker, and versions |
| Local ports | Application and dependency ports |
| Required services | Databases, brokers, mock services |
| Startup command | Standard launch command |
| Test command | Standard verification command |
| Health endpoint | How to verify readiness |
| Documentation owner | Person responsible for updates |

Documentation should include a verification date or version. Whenever toolchains or run commands change, owners must update the guide alongside the code change.

## 3. Verifying Toolchains and Versions

Local failures frequently stem from version drift. A developer's laptop may run a newer JDK than CI runners, an older Docker Compose, or a globally installed build tool that differs from the project.

Prefer repository-managed wrappers and version files:

- Gradle Wrapper instead of relying on a global Gradle install.
- Maven Wrapper instead of relying on a global Maven install.
- Toolchain declarations to select the compile/test JDK.
- `.java-version`, `.tool-versions`, or equivalent config if used by the project.
- Supported Docker Compose plugin version.
- Node/Python version files if pipelines include frontend steps or helper scripts.

Verification example:

~~~powershell
java -version
.\gradlew.bat --version
docker version
docker compose version
git --version
~~~

On macOS/Linux:

~~~bash
java -version
./gradlew --version
docker version
docker compose version
git --version
~~~

If the project uses the Maven Wrapper:

~~~powershell
.\mvnw.cmd -version
~~~

~~~bash
./mvnw -version
~~~

Never write only "requires Java 21." Specify the supported JDK distribution/version and how to verify the wrapper picks up the right toolchain. When multiple JDKs are installed, show how to check `JAVA_HOME` and `PATH` without forcing readers to alter global settings recklessly.

## 4. Checking Out Source and Identifying the Exact Revision

The first step is working on the right repository, branch, and commit.

~~~bash
git clone <repository-url>
cd <repository-directory>
git status --short
git branch --show-current
git rev-parse HEAD
~~~

Before debugging, record:

- Current branch.
- Commit SHA.
- Whether uncommitted files or local changes exist.
- Whether submodules or generated sources need initialization.
- Whether any local patches or overrides are active.

When comparing against CI, use the exact commit SHA from the workflow run. Never compare local results on edited source against a pipeline run on an older commit and conclude the two environments differ.

When testing an isolated change, use a worktree to preserve your current working tree:

~~~bash
git worktree add ../service-debug-worktree <commit-or-branch>
~~~

Once finished, check the worktree path before removing it. Never run `reset` or `clean` to "tidy up" a repository before confirming you aren't wiping someone else's or uncommitted work.

## 5. Local Configuration and Precedence Order

Applications often load configuration from multiple sources:

- Hardcoded defaults in code.
- Shared configuration files.
- Local profile files.
- Environment variables.
- Secret managers or runtime-injected secrets.
- Command-line arguments.

Documentation must explain which source takes precedence. For example, an environment variable may override values in `application-local.yml`. Without stating this, a reader might edit the file only to see the app keep using shell values.

### Using Template Files Instead of Committing Personal Configs

Provide `.env.example` or `application-local.example.yml` with illustrative placeholders:

~~~dotenv
APP_PROFILE=local
SERVER_PORT=8080
DB_HOST=localhost
DB_PORT=5432
DB_NAME=app_local
DB_USER=app
DB_PASSWORD=local-only-change-me
~~~

These are disposable placeholders for local use only; real projects should instruct developers to generate their own local secrets. Files containing real credentials must be git-ignored and excluded from artifacts and logs.

Never put production passwords or shared tokens in examples. If access to a shared service is required, document how to fetch scoped credentials from the secret manager.

### Validating Configuration Before Startup

The application should validate required variables at startup and report missing names without printing secret values. For example:

~~~text
Configuration error:
- DB_HOST is missing
- APP_PROFILE must be one of: local, test
No credentials were printed.
~~~

Documentation should include an environment variable reference table:

| Variable | Required | Local Example | Description |
|---|---|---|---|
| APP_PROFILE | Yes | local | Configuration profile |
| SERVER_PORT | No | 8080 | HTTP port |
| DB_HOST | Yes | localhost | Database host |
| DB_PORT | Yes | 5432 | Database port |
| DB_NAME | Yes | app_local | Local database name |
| DB_USER | Yes | app | Local database user |
| DB_PASSWORD | Yes | Obtained from local secret | Never commit to Git |

## 6. Managing Secrets in Development Environments

Local secrets still require protection. A test token may still grant access to real cloud resources or internal services.

Document explicit rules:

- Never commit `.env`, private keys, tokens, or credential files.
- Never paste secrets into issues, chats, or logs.
- Use dedicated local credentials; never reuse production credentials.
- Grant least-privilege scopes and set expiration dates.
- Rotate or revoke credentials immediately if exposure is suspected.
- Never embed real secrets in test fixtures.
- Check `git status` before committing.
- Redact `Authorization` headers, cookies, and connection strings before sharing logs.

Check for accidentally tracked files:

~~~bash
git status --short
git check-ignore -v .env
~~~

If a secret file was already committed, deleting it in a later commit does not make the old secret safe. Revoke/rotate the secret immediately and follow your organization's repository history remediation process.

## 7. Starting Dependencies with Docker Compose

Many services depend on a database, Redis, Kafka, or mock servers. Docker Compose standardizes local dependencies without forcing every developer to install each service natively.

Minimal Compose example for PostgreSQL:

~~~yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: app_local
      POSTGRES_USER: app
      POSTGRES_PASSWORD: local-only-change-me
    ports:
      - "5432:5432"
    volumes:
      - app-db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $$POSTGRES_USER -d $$POSTGRES_DB"]
      interval: 5s
      timeout: 3s
      retries: 10

volumes:
  app-db-data:
~~~

This is a local sample only; never use this password in shared environments. Projects should pin image tags or digests per policy and pick appropriate volumes and ports.

Start and inspect status:

~~~bash
docker compose up -d --wait
docker compose ps
docker compose logs --tail=100 db
~~~

Depending on the Docker Compose version, `--wait` may not be supported. If that flag errors out, run `docker compose up -d`, then inspect health via `docker compose ps` and wait until the service reports healthy before starting the application.

Stop containers:

~~~bash
docker compose stop
~~~

Stop and remove containers/networks while keeping named volumes:

~~~bash
docker compose down
~~~

The following command deletes named volumes and all local data inside them:

~~~bash
docker compose down -v
~~~

Use `down -v` only after confirming local volume data is disposable or backed up/exported. Documentation must flag data-reset commands clearly and keep them out of standard startup steps.

## 8. Startup Order and Readiness

A container in `running` state does not guarantee the service inside is ready for requests. The database may still be recovering, the broker may be building metadata, or migrations may still be running.

Standard startup flow should be:

1. Start dependencies.
2. Wait for health checks to pass.
3. Test connectivity from host or application container.
4. Run migrations if required locally.
5. Start the application.
6. Verify health/readiness endpoints.
7. Run a quick smoke test.

Do not rely on a long fixed `sleep` as the sole wait mechanism. Use health checks or bounded retries with a deadline. If readiness fails, print container status and relevant logs so users know what is blocking startup.

Example checking PostgreSQL from the host:

~~~bash
pg_isready -h localhost -p 5432 -U app -d app_local
~~~

If no client is installed locally, run the check inside a container or rely on Compose's health status.

## 9. Building and Running the Java Application

Prefer wrapper commands so everyone uses the repository's exact build tool version.

### Gradle

Build and run unit tests:

~~~bash
./gradlew clean test
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat clean test
~~~

Build the artifact:

~~~bash
./gradlew build
~~~

Run the application if the project uses the Spring Boot Gradle plugin:

~~~bash
./gradlew bootRun
~~~

For multi-module projects, documentation must state exact task paths such as `:service-api:test` or `:service-api:bootRun`. Never expect readers to guess module names from directory structures.

### Maven

Run verification:

~~~bash
./mvnw -B verify
~~~

On Windows:

~~~powershell
.\mvnw.cmd -B verify
~~~

Run the Spring Boot application if the plugin is configured:

~~~bash
./mvnw spring-boot:run
~~~

Do not assume every Java project uses Spring Boot. Actual commands must match the build files and plugins declared in the repository.

### Separating Build and Run

Documentation should clearly separate commands that compile/test, commands that launch the app, and commands that package release artifacts. This prevents developers from accidentally running publish/deploy tasks when they only intend to test locally.

## 10. Running the Application with a Local Profile

A local profile should emulate necessary dependencies and behaviors without ever granting production permissions.

Spring Boot example:

~~~bash
./gradlew bootRun --args='--spring.profiles.active=local'
~~~

Or via environment variable:

~~~bash
SPRING_PROFILES_ACTIVE=local ./gradlew bootRun
~~~

On PowerShell:

~~~powershell
$env:SPRING_PROFILES_ACTIVE = "local"
.\gradlew.bat bootRun
~~~

The local profile may point to local databases, mock external services, and use suitable log levels. Do not automatically disable authentication or authorization if doing so prevents tests from exercising critical behavior.

When mock services are needed, document their endpoints, how to launch them, and how they differ from real environments.

## 11. Running Test Tiers

Local documentation must distinguish fast checks from full suites:

| Test Type | Purpose | Dependencies |
|---|---|---|
| Unit test | Verify isolated logic | Typically no external services |
| Component test | Verify a component with isolated dependencies | Mocks or dedicated containers |
| Integration test | Verify interaction across components | Database/broker/service |
| Contract test | Verify API/message contracts | Provider/consumer contracts |
| End-to-end test | Verify cross-system business flows | Multiple services |
| Smoke test | Verify newly started app handles basic operations | App and core dependencies |

Run fast unit tests before kicking off heavy integration suites. When a failure occurs only with a database present, start the required dependencies and run the matching test suite.

With Gradle, run specific tasks if declared by the project:

~~~bash
./gradlew test
./gradlew integrationTest
~~~

With Maven, use profiles or configured plugins in the project:

~~~bash
./mvnw -B test
./mvnw -B verify
~~~

Never invent task or profile names in documentation if the repository does not define them. Owners must verify all commands before publishing.

## 12. Ensuring Local and CI Have Equivalent Check Semantics

The goal is not making laptops identical to CI runners in every detail, but ensuring the same verification command carries equivalent semantics.

Compare:

- JDK and build tool versions.
- Dependency locks and repository configuration.
- Required environment variables.
- Test profiles and test selection.
- Database/broker versions.
- Locale, timezone, and character encoding.
- Container image and CPU architecture.
- Feature flags and config revisions.
- Artifact packaging steps.
- Quality/security check commands.

If CI executes `./gradlew --no-daemon clean verify`, local docs should show the matching command and explain any intentional differences. Never label a local script "same as CI" if it only runs a subset of tests.

### Sharing Scripts When Possible

Provide task-level scripts invoked identically by local users and CI, for example:

~~~bash
./scripts/verify.sh
~~~

Such scripts should:

- Validate prerequisites.
- Invoke the build wrapper.
- Run the exact intended tests/checks.
- Return a non-zero exit code on failure.
- Avoid depending on machine-specific shell state.
- Never print secrets.
- Clearly state where output reports are written.

If Windows support is required, provide an equivalent PowerShell script or a suitable portable script.

## 13. Checking Health Endpoints and Connectivity

After starting the application, verify readiness instead of trusting a "Started" log line.

Example:

~~~bash
curl -fsS http://localhost:8080/actuator/health
~~~

If the endpoint requires authentication or is disabled locally, document how to check it properly. Never expose sensitive management endpoints on public interfaces just for debugging convenience.

Check listening ports:

PowerShell:

~~~powershell
Get-NetTCPConnection -LocalPort 8080 -State Listen
~~~

macOS/Linux:

~~~bash
lsof -iTCP:8080 -sTCP:LISTEN
~~~

If a port is already bound, identify the owning process before terminating it. Never kill a process by PID without confirming you launched it.

## 14. Where Logs Live and How to Read Them

Documentation must specify where logs can be found:

- The terminal running the application.
- Local log files if file appenders are configured.
- Docker Compose service logs.
- Test reports and build outputs.
- IDE run console.
- Local observability collector if present.

Example:

~~~bash
docker compose logs --since=10m db
docker compose logs -f db
~~~

For directly launched apps, inspect the launch terminal or configured log file. For Gradle, test reports usually reside under `build/reports/tests` or a build-script-defined path.

### Structured Logs

Where possible, logs should include:

- Timestamp with explicit timezone.
- Log level.
- Service and environment.
- Request/correlation ID.
- Trace ID.
- Pipeline run/job ID if triggered from CI.
- Operation ID.
- Event name and error code.

Never log passwords, tokens, authorization headers, or sensitive payloads. Scrub secrets and personal data before sharing logs with others.

## 15. Systematic Troubleshooting Workflow

When troubleshooting, avoid changing multiple variables at once. Follow a sequence:

1. Record the exact action and command just executed.
2. Capture the commit SHA and working tree status.
3. Locate the *first* error in the logs, not just the final error.
4. Identify the component involved: build tool, app, database, broker, network, or credentials.
5. Compare actual configuration against expected configuration.
6. Reproduce with the smallest possible command.
7. Change one factor at a time.
8. Re-verify using tests or health checks.
9. Document root cause and recovery steps.
10. Update documentation if a missing step was uncovered.

### Separating Root Errors from Cascading Errors

For instance, a database failing to start can cascade into:

- Connection refused.
- Repository initialization failed.
- Application context failed.
- Health endpoint unavailable.
- Integration test timeout.

The root fault is that the database is not ready. Do not treat five downstream application stack traces as five separate bugs.

Find the earliest error chronologically and verify upstream dependencies first.

## 16. Classifying Common Failures

| Failure Category | Symptoms | First Check |
|---|---|---|
| Toolchain | Unsupported class version, missing task | JDK, wrapper, and build plugins |
| Dependency | Could not resolve artifact, checksum mismatch | Repositories, proxies, lockfiles, and network |
| Configuration | Missing property, invalid profile | Environment variables and config precedence |
| Port/network | Connection refused, address already in use | Service health, ports, and DNS |
| Database | Authentication failed, missing schema, migration error | Host/port/user, database state, and migration history |
| Container | Image pull failed, container unhealthy | Registry access, image tag, and container logs |
| Test | Assertion failure, flaky timeout | Test data, isolation, clocks, and dependencies |
| Permission | 401/403, access denied | Identity, token scope, and roles |
| Resource | Out of memory, disk full, process killed | Heap, container limits, disk, and concurrency |
| Runtime | Deadlock, thread starvation, high latency | Thread dumps, pool metrics, and dependencies |
| CI/local drift | Passes locally, fails in CI | Toolchain, OS, env, architecture, and test selection |

Each documented failure in internal runbooks should include symptoms, common causes, inspection commands, remediation steps, and recovery verification criteria.

## 17. Troubleshooting Build and Dependency Errors

When a build fails:

1. Verify the wrapper and JDK.
2. Read the first failure, not just the trailing summary.
3. Identify the failing task or module.
4. Check repository/proxy access and dependency locks.
5. Re-run the smallest task to reproduce.
6. Refresh dependencies only when evidence shows stale caches or repositories.

Gradle:

~~~bash
./gradlew test --stacktrace
./gradlew test --info
./gradlew --stop
~~~

Maven:

~~~bash
./mvnw -B -e test
~~~

Avoid enabling full debug logging immediately in environments containing secrets. Some build plugins print URLs, headers, or sensitive properties. If deeper logs are required, inspect and redact before sharing.

Do not wipe the entire cache at the first sign of a dependency error. Caches can be large; nuking them wastes download time and obscures repository or proxy root causes. Test the specific task, inspect dependency metadata, and use targeted refreshes.

## 18. Troubleshooting Databases and Migrations

When the application cannot connect to the database, check in order:

1. Is the container/service running?
2. Is the health check passing?
3. Are host and port correct from the application process's perspective?
4. Do the database name and user exist?
5. Are local credentials valid?
6. Does the database accept connections from that interface?
7. Does the schema/migration version match expectations?
8. Is the connection pool exhausted or holding stale connections?

Never assume `localhost` means the same thing on the host and inside a container. From the host, `localhost` targets Compose's published port; from an app container, the database is normally addressed by its service name such as `db` on the Docker network.

### Migration Failures

If a migration fails:

- Read the migration ID and the very first error.
- Inspect the migration history table.
- Determine whether a transaction partially committed.
- Inspect the live schema state.
- Never manually delete migration history rows to force a re-run.
- Never edit a migration already applied in shared environments.
- Create a new migration or follow an appropriate recovery procedure.
- Back up data before risky repair operations.

If you are unsure how far a migration progressed, stop write operations and reconcile schema vs. history before rerunning.

## 19. Troubleshooting Containers, Networking, and Ports

Common issues:

- Container fails to start due to image pull or config error.
- Host port is already occupied by another process.
- App container cannot resolve a dependency hostname.
- Service is healthy, yet the app uses wrong credentials.
- Container restarts due to OOM.
- DNS/proxy/firewall blocks a dependency.
- Host architecture does not match image architecture.

Diagnostic commands:

~~~bash
docker compose ps
docker compose logs --tail=200 <service>
docker inspect <container-id>
docker stats
docker network ls
~~~

Test networking from inside the app container if the image includes appropriate tools. Otherwise, launch an ephemeral debug container on the same network per project policy.

`docker inspect` can reveal environment variables, mount paths, and configuration details. View its output only in authorized environments, and redact secrets before sending to teammates or attaching to tickets.

Never conclude "the database is down" solely from a connection refused error in the app. Verify port mappings, hostnames, and network namespaces first.

## 20. Troubleshooting Java Runtime Issues

When the app starts but responds slowly or hangs, distinguish high CPU, blocked threads, exhausted connection pools, deadlocks, and slow downstream dependencies.

Useful tools:

~~~bash
jcmd <pid> Thread.print
jcmd <pid> GC.heap_info
jcmd <pid> VM.system_properties
~~~

System properties can contain URLs, usernames, or sensitive configuration values. Collect them only when needed, inspect them, and redact output before sharing. Thread dumps should also be reviewed to avoid exposing request details or business data.

Metrics and states to examine:

- Thread states and stack traces.
- Thread pool active/queued/rejected counts.
- Database connection pool active/idle/pending counts.
- HTTP client connection pools.
- Heap usage and garbage collection pauses.
- Request latency and error rates.
- Downstream dependency latency.
- Deadlock detection output.
- Container memory/CPU limits.

Capture heap dumps only when sufficient disk space and access controls exist; heap dumps can contain sensitive in-memory data. Never attach dump files to public tickets.

## 21. Reproducing Failures Repeatably

A useful bug report documents exact reproduction conditions:

- Commit SHA.
- OS and architecture.
- JDK/build tool versions.
- Profile/config revision.
- Dependency versions.
- Fixture data or test case.
- Exact command executed.
- Timestamp and timezone if relevant.
- Expected outcome.
- Actual outcome.
- Reproduction frequency.
- Redacted logs/traces.

Shrink reproduction scope:

- Run a single test instead of the entire suite.
- Use a single fixture record instead of a huge dataset.
- Hit a single endpoint instead of an end-to-end workflow.
- Isolate unrelated dependencies with mocks or test containers.
- Pin clocks, timezones, or random seeds where appropriate.

Never change code and configuration simultaneously while investigating. If the failure disappears, you will not know which change resolved it.

## 22. Recovery Procedure When the Local Environment Breaks

Recovery should progress from least invasive to most invasive:

1. Identify the failing process or service.
2. Save logs and state before making changes.
3. Stop only the processes you own.
4. Check dependencies and health status.
5. Restart the application.
6. If necessary, restart only the failing dependency.
7. Verify configuration and credentials.
8. Check checkpoints or migration states if a task was interrupted.
9. Reset local data only after confirming it is safe to discard.
10. Run smoke tests and relevant test suites.
11. Record final state and root cause.

Example restarting a single Compose service:

~~~bash
docker compose stop db
docker compose up -d db
docker compose ps
~~~

If the app ran directly, stop it from the terminal or process manager that launched it. Avoid killing all Java processes indiscriminately, as that can kill your IDE or unrelated tools.

### When Is a Reset Needed?

A reset may make sense when a local volume is corrupted or fixtures are inconsistent. Before resetting:

- Confirm the exact Compose project and volume name.
- Check whether any data must be kept.
- Export or back up if needed.
- Confirm this is a disposable local environment.
- Record the reset command and its impact.
- After resetting, re-run migrations/seeds and verify health.

Never run local volume deletion commands against staging or production.

## 23. Recovering When a CI Job or Runner Is Interrupted

When using a local run to investigate a CI failure, align closely with the workflow run:

- Commit SHA and branch.
- Job name and attempt number.
- Runner OS/image/architecture.
- Toolchain versions.
- Environment variables and profile.
- Artifact digest.
- Test report.
- Exit code and failure classification.
- Dependent service versions.

If a job was interrupted mid-operation with external side effects, check external state before rerunning. For instance, a publish may have completed even though the response dropped; a deployment may still be rolling out even though the runner terminated.

Never treat a timeout as proof that an action did not happen. Look up operation IDs, package versions/digests, or live resource states before retrying.

If the error occurs solely due to the runner environment, reproduce using an equivalent runner image or container. If tests pass locally yet fail in CI, compare every input systematically rather than blindly tweaking code until tests turn green.

## 24. Collecting Evidence for Handoff

When asking a teammate for help, send an inspectable context bundle:

| Component | Content |
|---|---|
| Summary | One-sentence description of the error |
| Commit | SHA and branch |
| Environment | OS, JDK, build tool, profile |
| Command | Exact command executed |
| Expected | Expected result |
| Actual | Actual result and exit code |
| First failure | Chronologically earliest error |
| Logs | Redacted log excerpts |
| Dependencies | Status of DB/broker/containers |
| Reproduction | Shortest reproduction steps |
| Attempts | Attempt count and result of each |
| Changes tried | Fixes attempted and outcomes |
| Current state | Current state of service, process, and data |

Attach links to the pipeline run or test report if available. Never share secrets, tokens, personal data, or unreviewed dumps.

A strong handoff ends with a specific question—for example, "Can we confirm whether migration V12 can safely resume after this duplicate-index error on the local database?"—rather than simply posting "the app won't run."

## 25. Updating Documentation After Finding the Root Cause

Solving a bug once does not automatically create reusable knowledge. After investigating, update documentation:

- Add any missing prerequisite.
- Fix OS-specific command discrepancies.
- Clarify exact ports and service names.
- Add expected outputs.
- Add pre-reset checks.
- Update toolchain versions.
- Document errors specific to a single profile.
- Add a test or health check to prevent recurrence.
- Update the owner and verification date.

If a workflow changed, remove outdated instructions or mark them deprecated. Two conflicting setup paths cause readers to pick the wrong one and reintroduce errors.

Documentation should be reviewed alongside pull requests that change builds, Compose files, configurations, or developer scripts. You can add smoke checks for documented commands to catch stale instructions automatically.

## 26. Runbook Template for a Common Error

Use the following structure to standardize troubleshooting entries:

~~~markdown
### Error: Application cannot connect to local database

**Symptoms**
- Startup logs report connection refused or authentication failed.
- Health endpoint fails readiness.

**Scope**
- Applies only to the `local` profile.
- Database runs via Docker Compose.

**Checks**
1. Run `docker compose ps`.
2. Inspect health status of the `db` service.
3. Verify `DB_HOST` and `DB_PORT` in the app environment.
4. Check local database/user and credentials.
5. Read `docker compose logs --tail=100 db`.

**Remediation**
1. If the container is stopped, start the `db` service.
2. If credentials mismatch, update local secrets per the setup guide.
3. If a port conflicts, identify the owning process before changing ports.
4. Reset the volume only if local data can be discarded.

**Verification**
- Database health check passes.
- Application connects successfully.
- Smoke test passes.

**Evidence**
- Commit SHA, command, timestamp, and redacted logs.

**Owner**
- Team/service owner and last review date.
~~~

Each runbook entry should address one specific problem. If an entry branches too widely, split it into smaller entries so readers can follow easily.

## 27. Anti-Patterns in Writing Local and Troubleshooting Guides

| Anti-Pattern | Consequence | How to Improve |
|---|---|---|
| Listing only one start command | Newcomers miss prerequisites and config | Document end-to-end from toolchain checks to readiness |
| Using `latest` versions | Local and CI drift easily | Pin versions or state supported ranges |
| Committing real `.env` files | Leaks credentials | Use template files and local secrets |
| Omitting profile instructions | Wrong config loaded or hits real environments | Specify profiles and config precedence |
| Fixed sleep waiting on database | Flaky across machine speeds | Use health checks and bounded deadlines |
| Deleting caches/volumes on first error | Loses data and masks root cause | Diagnose first, reset only deliberately |
| Reading only the bottom stack trace | Misses the initial root error | Build a timeline and locate the first failure |
| Killing all Java processes | Terminates IDEs or other services | Verify PID and owning process |
| Sharing raw debug logs verbatim | Risks exposing secrets | Use structured logs and redaction |
| Local commands differ silently from CI | Results are incomparable | Share scripts and document differences explicitly |
| Not recording commit/config revision | Failures cannot be reproduced | Record source and environment identity |
| Guides lack owner/review date | Documentation goes stale | Assign an owner and review with code changes |

## 28. Pre-Publication Documentation Checklist

### Setup and Execution

- [ ] OS, JDK, build tool, and Docker versions are explicitly stated.
- [ ] Wrappers or pinned tool versions are used.
- [ ] Clone/checkout and commit verification steps are included.
- [ ] Sample config files exist with zero secrets.
- [ ] Profiles and configuration precedence are documented.
- [ ] Dependency startup and health checks are included.
- [ ] Build, run, unit test, and integration test commands are provided.
- [ ] Expected outputs or readiness checks are documented.

### Troubleshooting and Recovery

- [ ] Log/report locations and redaction instructions are clear.
- [ ] Guidance for finding the first failure is included.
- [ ] Common errors table and diagnostic steps are documented.
- [ ] Port, network, and dependency check commands are included.
- [ ] Safe process/service shutdown by owner is documented.
- [ ] `restart`, `down`, and volume deletion are clearly distinguished.
- [ ] Checkpoint/migration recovery steps are included where relevant.
- [ ] Recovery success criteria are defined.

### Handoff and Maintenance

- [ ] Report template captures commit, command, environment, and evidence.
- [ ] No secrets or sensitive data appear in documentation.
- [ ] Local commands carry equivalent semantics to CI.
- [ ] Owner and last review date are listed.
- [ ] Runbooks update alongside build/config changes.
- [ ] Key commands have been verified on supported OS platforms.

## Conclusion

Documenting local setup, troubleshooting, and recovery is an integral part of CI/CD quality. Specify pinned toolchains, secret-safe local configuration, health-checked dependencies, clear build/test commands, and readiness verification. When errors strike, isolate the first failure, reproduce with deterministic inputs, vary one factor at a time, and reset data only after understanding the impact. Capture the commit, environment, command, redacted logs, and recovery state so teammates can pick up investigations seamlessly. When documentation is reviewed alongside code and pipelines, local development stays consistent with CI and teammate support relies far less on tribal knowledge.
