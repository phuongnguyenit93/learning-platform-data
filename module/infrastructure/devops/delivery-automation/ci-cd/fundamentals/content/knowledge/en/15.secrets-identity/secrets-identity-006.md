# Preventing Secrets from Appearing in Source Code, Logs, Caches, and Artifacts

Secrets in CI/CD can include passwords, access tokens, private keys, signing keys, certificates, registry credentials, database login credentials, or webhook tokens. These values are often required to build, publish packages, sign artifacts, or deploy applications. If a secret appears in source code, logs, caches, or artifacts, anyone with read access to those resources can use it outside its intended purpose.

Secret leaks do not happen solely when a developer accidentally commits `.env`. A workflow can print environment variables when debug mode is enabled, write credentials into a config file that gets uploaded by mistake, bake tokens into a Docker layer, or cache an entire working directory. Therefore, secret protection must be designed across the entire CI/CD lifecycle: issuance, usage, passing between steps, logging, storage, revocation, and investigation.

The goal is for secrets to be supplied only to the exact job and step that need them, exist for the shortest possible duration, never enter shareable outputs, and be rapidly revocable if exposure is suspected. Combine centralized secrets management, least privilege, secret scanning, log hygiene, cache/artifact allowlists, and an incident response process.

## 1. Identifying Where Secrets Can Leak

In a pipeline, data flows through many components: repository, runner, shell processes, build tools, container builders, caches, artifact stores, logging services, and deployment systems. Secrets can be copied from one place to another without the workflow author noticing.

| Location | Common Leak Vector | Consequence |
|---|---|---|
| Source code and Git history | Committing `.env`, tokens in YAML, private keys in scripts | Secret persists in repository history and clones |
| Local config files | Writing credentials into `gradle.properties`, `settings.xml`, `.npmrc` | Files may be committed, cached, or uploaded |
| CI logs | `echo`, `printenv`, `set -x`, debug logs, exceptions | Anyone with log read access can harvest credentials |
| Process arguments | Putting tokens on the command line or in URLs | Can appear in process lists, audit logs, or shell traces |
| Caches | Caching entire home, config, or workspace directories | Other jobs can restore data containing secrets |
| Artifacts | Uploading the entire workspace, test reports, dumps, or configs | Secrets outlive the job run and can be downloaded |
| Container images | Using `ARG`, `ENV`, `COPY` to embed secrets in images | Secrets may remain in layers, metadata, or image history |
| Inter-job outputs | Writing tokens to `GITHUB_OUTPUT`, artifacts, or intermediate files | Downstream jobs or artifact downloaders can read them |
| Notifications and reports | Attaching logs to issues, chats, emails, or tickets | Secrets spread into systems with different access scopes |

A secret may still be exposed even when displayed values in logs are masked with `***`. For instance, a portion of a token that is concatenated, Base64-encoded, or split into segments may not match what the masking filter detects. Masking reduces accidental exposure, but it does not replace designing pipelines to avoid logging secrets.

## 2. Managing Secrets in a Controlled Source

Never store long-lived secrets in source code or committed configuration files. Use the CI/CD platform's secret manager, a vault, or a cloud identity and credential management service. The repository should hold only reference names and retrieval logic—never the values themselves.

For example, a configuration file can reference the environment variable names required by the application:

```yaml
repository:
  url: https://packages.example.com/releases
  username: ${MAVEN_USERNAME}
  password: ${MAVEN_PASSWORD}
```

This is an illustrative structure; the application or configuration loader must support the corresponding environment variable substitution. Never commit real values into YAML files.

### Classification and Least Privilege

Every secret needs a purpose, owner, scope, and expiration. Do not use a single shared administrative credential across all workflows. For example:

- A unit test job that only reads source and public dependencies needs no deploy secrets.
- A job downloading private dependencies needs only a package-read credential.
- A package publish job needs write permission only for the exact package/repository.
- A staging deploy job needs a staging identity, never production credentials.
- A release signing job needs dedicated signing permissions and should run only on approved revisions.

Secrets should be scoped to the narrowest possible job or step. Avoid placing all secrets at the workflow level or passing them across multiple jobs unnecessarily.

### Preferring Short-Lived Credentials

For cloud providers or services supporting workload identity, prefer OIDC or an equivalent mechanism to exchange workflow identity for short-lived credentials. This reduces the number of long-lived access keys that must be stored and revoked.

Trust policies must constrain issuer, audience, repository, branch/tag, environment, or workflow identity strictly to what is needed. Enable OIDC token requests only on jobs that require them. `id-token: write` permits a job to request a token; it does not restrict the cloud identity's privileges by itself. Actual permissions must be enforced further via trust policies and roles on the target service.

If long-lived credentials cannot yet be retired, enforce an appropriate TTL, limit scope, store them in a secret manager, rotate periodically, and maintain an emergency revocation procedure.

## 3. Preventing Secrets from Entering Source Code and Git History

### Do Not Commit Configuration Files Containing Credentials

Common files to watch out for include `.env`, `.env.local`, `application-local.yml`, personal `gradle.properties`, Maven `settings.xml`, `.npmrc`, `.pypirc`, cloud credentials files, kubeconfigs, and private keys.

Add local files to `.gitignore`:

```gitignore
# Local environment files
.env
.env.*
!.env.example

# Local application configuration
application-local.yml
application-local.yaml

# Private keys and certificates with private material
*.key
*.pem
*.p12
*.pfx

# Local credential directories
.aws/
.kube/
secrets/
```

`.gitignore` only prevents Git from automatically tracking untracked files. It does not remove previously committed files and does not stop a user from intentionally running `git add -f`. Therefore, combine it with repository conventions, code reviews, and secret scanning.

You can commit an example file containing no real values:

```dotenv
MAVEN_USERNAME=replace-with-local-username
MAVEN_PASSWORD=replace-with-local-password
```

Name it clearly, such as `.env.example`, and document how to fetch values from the secret manager. Do not use realistic-looking dummy tokens in example files, as scanners or users might mistake them for valid credentials.

### Checking Before Committing

Before committing, inspect staged files:

```bash
git status --short
git diff --cached --stat
git diff --cached
```

Review newly added, renamed, and binary files as well. A configuration file may have been staged during earlier work even if the current task does not touch it.

Local pre-commit hooks can run a secret scanner for early warnings, but developer-machine hooks can be bypassed or left uninstalled. CI checks and push protection on the Git platform must serve as mandatory controls.

### Scanning Source Code and Git History

Secret scanners look for strings resembling credentials, private keys, or known token patterns. You can use Gitleaks, TruffleHog, or platform-provided scanners. Example with the Gitleaks CLI:

```bash
# Scan current directory tree
gitleaks dir --redact .

# Scan repository and Git history
gitleaks git --redact .
```

Command names and flags can change across scanner versions; pin tool versions in CI and check the documentation for the version in use. Scanning the working tree and scanning history cover different scopes. A secret deleted from current files can still persist in older commits.

Enable secret scanning and push protection if supported by your repository platform. Push protection can block recognized credentials before a commit reaches the remote. Scanners can still miss custom secrets or non-standard formats, so never treat a clean scan as absolute proof.

### Do Not Treat Deleting a Commit as Revoking a Secret

If a secret has already been pushed, removing that line in a subsequent commit does not invalidate the old credential. History may still exist on remotes, forks, clones, pull requests, caches, or other people's copies.

Response order when a committed secret is discovered:

1. Revoke or rotate the credential immediately; prioritize blocking usability first.
2. Identify the secret type, permission scope, exposure duration, and systems it could have accessed.
3. Inspect access logs and anomalous activity during the period the credential was valid.
4. Remove the secret from current source and, when necessary, scrub Git history per repository governance procedures.
5. Coordinate updates across clones, forks, branches, and pipelines that may retain old history.
6. Re-scan repositories, artifacts, logs, and caches to locate any remaining copies.
7. Document the root cause and add controls to prevent recurrence.

Rewriting history may require force-pushing and disrupt existing clones. Perform it only under your team's repository procedure, coordinating with affected users and teams. Rewriting history does not replace rotating the credential.

## 4. Avoiding Secrets on the Command Line and in Shell History

Never put tokens directly into commands, URLs, or logged arguments. The following example risks leaking credentials via shell history, process lists, or logs:

```bash
curl -H "Authorization: Bearer REAL_TOKEN_VALUE" https://api.example.com/deploy
```

Avoid URLs of the form `https://user:password@host/...` because URLs can appear in proxy logs, exceptions, or telemetry.

Prefer letting programs read credentials from short-lived environment variables or secret files. For tools supporting stdin, file descriptors, or secret mounts, use those mechanisms to keep values out of command arguments. Even when using environment variables, never print the full environment or enable shell tracing while secrets are present.

Example in GitHub Actions, passing secrets only to the exact step:

```yaml
- name: Publish package
  env:
    MAVEN_USERNAME: ${{ secrets.MAVEN_USERNAME }}
    MAVEN_PASSWORD: ${{ secrets.MAVEN_PASSWORD }}
  run: ./gradlew --no-daemon publish
```

Gradle can read environment variables to authenticate with the repository:

```kotlin
publishing {
    repositories {
        maven {
            name = "internalReleases"
            url = uri("https://packages.example.com/releases")
            credentials {
                username = providers.environmentVariable("MAVEN_USERNAME").orNull
                password = providers.environmentVariable("MAVEN_PASSWORD").orNull
            }
        }
    }
}
```

This example assumes the repository supports username/password authentication and the Gradle Maven Publish plugin is configured. Do not write these values into `gradle.properties` or logs. If a plugin or build script might print credentials, fix its logging behavior and test with dummy values before using real ones.

Environment variables can still be read by child processes running under the same user or printed during debugging. Scope them to the narrowest step, use dedicated runners for sensitive jobs, and terminate the job immediately after the operation completes.

## 5. Preventing Secrets from Appearing in CI Logs

Logs are often retained long-term, indexed, and shared with more people than have access to the original secret. Therefore, a single accidental `echo` can create a credential copy that is difficult to fully retract.

### Commands Prone to Leaking Data

Avoid these commands or debug modes in jobs that hold secrets:

```bash
set -x
env
printenv
set
curl -v ...
./gradlew --debug publish
```

`set -x` prints commands after shell variable expansion. `env`, `printenv`, and `set` can dump environment values. Verbose/debug modes in HTTP clients, build tools, or SDKs can log headers, URLs, request bodies, and authentication details.

Enable debug mode only when genuinely necessary, restrict log viewers and retention, use revocable test credentials, and inspect logs before sharing. Never use production secrets to reproduce bugs in an uncontrolled debug session.

### Never Include Secrets in Error Messages

Exceptions can include full URLs, request headers, connection strings, or configuration contents. When handling errors, log status codes, service names, correlation IDs, and sanitized details. Never log entire configuration objects if they contain password or token fields.

Example of a safe log message:

```text
Package publish failed: HTTP 401 from internal package registry.
Repository: internalReleases
Request ID: <correlation-id>
Credential value: [redacted]
```

Do not log raw response bodies or request headers unless verified to contain no secrets or sensitive data.

### Masking Is Only an Additional Defense Layer

CI platforms often auto-mask declared secrets when exact strings are detected in logs. For runtime-generated values, some platforms allow registering a value for masking before it can appear in output. For example, GitHub Actions supports the `add-mask` workflow command:

```bash
printf '::add-mask::%s\n' "$GENERATED_TOKEN"
```

This command must execute before any output that could contain the value. However, masking may fail to recognize encoded, truncated, concatenated, or transformed variants. Never print a secret just to "test whether it gets masked." The right practice is not logging secrets at all.

Do not pass secrets via job outputs or `GITHUB_OUTPUT` purely for convenience. If a downstream job needs credentials, have it retrieve credentials directly from the secret manager or request its own short-lived token.

## 6. Preventing Secrets from Entering Caches

Caches exist to speed up builds, not to store configuration or secrets. When caching overly broad directories, authentication files can be saved alongside dependencies and restored on subsequent runs.

Paths requiring close scrutiny:

- `$HOME`, `~/.gradle`, `~/.m2`, `~/.npm`, `~/.config`.
- `.aws/`, `.kube/`, `.docker/`, and cloud SDK credential directories.
- `.env`, `.npmrc`, `.pypirc`, Maven `settings.xml`, kubeconfig.
- `gradle.properties` or repository config files containing passwords.
- Workspaces containing temporary files created during deployment or artifact signing.
- Build outputs, test reports, or generated configs that may embed environment variables.

Do not cache the entire home directory or workspace just to save time. Select only the exact dependency directories needed for reuse and exclude credential-bearing configs.

### Example of a Narrowly Scoped Gradle Cache

In GitHub Actions, you can cache Gradle via a dedicated setup action or explicit cache path configuration. The example below illustrates caching Gradle dependencies:

```yaml
- name: Set up Gradle
  uses: gradle/actions/setup-gradle@v4

- name: Build and test
  run: ./gradlew --no-daemon clean check
```

This action manages Gradle caching via its own mechanism. Read the configuration and permissions of your pinned action before adopting it. Do not arbitrarily add a step caching `$HOME` or all of `.gradle` without knowing which files may hold credentials or sensitive data.

If configuring caching manually, store only explicitly identified dependency/artifact cache directories—never personal `gradle.properties`, credential-bearing `init.gradle`, or `credentials` files.

### Separating Caches Along Trust Boundaries

Caches can be poisoned if an untrusted job writes data that a privileged job later restores and executes. For example, a pull request from a fork may run build scripts controlled by an external contributor. Never let untrusted jobs write caches into a namespace used by trusted release jobs.

Principles:

- Scope cache keys by operating system, runtime, lockfile, and trust tier.
- Avoid overly broad restore keys that pull in data of uncertain origin.
- Never allow jobs running untrusted code to write to caches reused by deployment or artifact-signing jobs.
- Never store secrets, tokens, auth config files, or release artifacts in caches.
- Treat caches as mutable and disposable data; verify dependencies after restoration.
- For release jobs, consider dedicated caches or clean runs if cache trustworthiness cannot be proven.

Cache scopes and read/write permissions vary by CI platform. Verify actual branch-scoping, pull-request scoping, and restore/save rules rather than assuming every platform behaves identically.

## 7. Preventing Secrets from Entering Artifacts and Reports

Artifacts are often shared between jobs, stored on servers, or downloaded for investigation. Upload only the exact required files rather than the entire workspace.

### Use an Allowlist Instead of Uploading the Whole Directory

Risky configuration example:

```yaml
- uses: actions/upload-artifact@v4
  with:
    name: everything
    path: .
```

This can pull `.env`, config files, logs, caches, temporary credentials, and unrelated files into the artifact. Specify only the exact outputs to preserve:

```yaml
- uses: actions/upload-artifact@v4
  with:
    name: application-release
    path: |
      build/libs/application.jar
      build/reports/tests/test/index.html
    if-no-files-found: error
    retention-days: 7
```

This example is appropriate only if test reports contain no sensitive data. If reports include request/response payloads, real test data, or tokens, sanitize them or do not upload those reports. Allowlisted paths should be reviewed whenever the build changes output structure.

### Inspecting Contents Before Uploading

Before saving artifacts, verify the file list and file types. You can generate a manifest, run a secret scan on the staging directory, and upload only if the scan passes.

Example shell check on a staging directory:

```bash
find release-staging -type f -print
gitleaks dir --redact release-staging
```

Scanners may miss custom credentials or sensitive data that do not match token patterns. Combine path allowlists, content checks, and review of newly introduced artifact files.

### Limiting Permissions and Retention

Artifacts containing logs or test reports should have retention suited to their purpose. Restrict download permissions by role, repository, and environment. Never use an artifact store as a team credential-sharing mechanism. If an artifact contains a secret, treat it as an exposure incident: revoke the credential, delete or quarantine the artifact per policy, and audit downloads if possible.

## 8. Protecting Secrets in Docker Builds and Container Images

A common mistake is passing credentials via Docker `ARG` or `ENV`:

```dockerfile
ARG REPOSITORY_TOKEN
ENV REPOSITORY_TOKEN=$REPOSITORY_TOKEN
RUN ./gradlew publish
```

`ENV` persists in the image configuration; `ARG` can appear in metadata or build history depending on build method and tool version. Never use them as channels for secrets.

### Using BuildKit Secret Mounts

BuildKit allows temporarily mounting a secret into a build step. Secret mounts are not automatically saved into the final layer unless the script copies or writes the value out.

Example Dockerfile:

```dockerfile
# syntax=docker/dockerfile:1.7
FROM eclipse-temurin:21-jdk AS build
WORKDIR /workspace
COPY . .

RUN --mount=type=secret,id=maven_settings,target=/root/.m2/settings.xml,required=true \\
    ./mvnw --batch-mode --settings /root/.m2/settings.xml package

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /workspace/target/application.jar /app/application.jar
ENTRYPOINT ["java", "-jar", "/app/application.jar"]
```

Building with a secret file:

```bash
docker buildx build \\
  --secret id=maven_settings,src="$HOME/.m2/settings.xml" \\
  --tag registry.example.com/team/application:1.0.0 .
```

`settings.xml` must be generated from a secret manager or temporary credential file with restricted permissions. Do not copy that file into the build context. Add it to `.dockerignore` if there is any chance it resides inside the context.

Example `.dockerignore`:

```dockerignore
.env
.env.*
!.env.example
**/settings.xml
**/.npmrc
**/gradle.properties
**/*.pem
**/*.key
.aws/
.kube/
.docker/
secrets/
```

Adjust `.dockerignore` to fit your project layout. Do not exclude legitimate build config files that contain no secrets; the goal is keeping credentials and local files out of the build context.

Even when using secret mounts, build commands can still leak secrets if they print the file, enable shell tracing, write decrypted configs into directories copied to later stages, or emit secrets into output. Inspect build scripts and generated layers.

### Never Copy Credentials into the Final Image

Multi-stage builds help copy only needed outputs from build stages into the runtime stage. However, they do not automatically guarantee secrets vanish if a secret was written into an output file or copied layer. Copy only the application artifact—never the home directory, Maven/Gradle configs, or the full workspace.

Inspect images using appropriate inspection tools and scanners. If credentials are found in an image, rebuild the image after rotating credentials; deleting an old tag does not remove copies already pulled by other hosts.

## 9. Designing Workflows That Grant Secrets Only to Trusted Jobs

Not all triggers carry the same trust level. Pull requests from forks can run code controlled by external contributors. Workflows must separate untrusted code validation from publish/deploy jobs that access secrets.

### Separating Test Jobs and Release Jobs

The following example runs tests on pull requests and pushes, but publishes only on pushes to the main branch:

```yaml
name: Verify and publish

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

permissions:
  contents: read

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - run: ./gradlew --no-daemon clean check

  publish:
    if: github.event_name == 'push' && github.ref == 'refs/heads/main'
    needs: test
    runs-on: ubuntu-latest
    environment: package-publishing
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
      - name: Publish package
        env:
          MAVEN_USERNAME: ${{ secrets.MAVEN_USERNAME }}
          MAVEN_PASSWORD: ${{ secrets.MAVEN_PASSWORD }}
        run: ./gradlew --no-daemon publish
```

The `test` job receives no publish secrets. The `publish` job runs only on pushes to `main`, and only the publish step receives the credentials. The `package-publishing` environment must be configured with protection rules, branch policies, and appropriate approver permissions. This is a baseline example; pin actions to full commit SHAs in repositories requiring strict supply-chain controls.

Never use `pull_request_target` to check out and execute scripts from the pull request head in a job holding secrets or write permissions. That event runs in the context of the target branch and can carry elevated permissions. If needed for labeling or metadata management, never run untrusted code from the pull request inside that privileged context.

### Using OIDC Instead of Long-Lived Cloud Access Keys

For cloud deployments, a job can request an OIDC token and exchange it for short-lived credentials. Example job-level permission configuration:

```yaml
deploy-staging:
  runs-on: ubuntu-latest
  permissions:
    contents: read
    id-token: write
  steps:
    - uses: actions/checkout@v4
    - name: Authenticate to cloud
      run: ./scripts/ci/authenticate-with-oidc.sh
    - name: Deploy
      run: ./scripts/ci/deploy-staging.sh
```

The authentication script should use the cloud provider's SDK to fetch the OIDC token from the runner environment and exchange it for short-lived credentials. Cloud-side trust policies must validate issuer, audience, repository, ref, and environment. Never write OIDC tokens or returned credentials to logs, artifacts, or caches.

## 10. Checking for Secrets Before and After Builds

Secret scanning should be placed at multiple checkpoints, because one layer may miss data that another layer catches.

| Stage | Check | Goal |
|---|---|---|
| On developer machine | Pre-commit scan and staged diff review | Prevent secrets before committing |
| On push | Secret scanning/push protection | Block recognized credentials before reaching remote |
| In pull request | Scan diff and new files | Detect secrets in changes under review |
| On Git history | Scheduled full-history scan | Detect legacy secrets still present |
| Before cache save | Check paths and cached contents | Avoid saving credentials or sensitive outputs |
| Before artifact upload | Allowlist and secret scan staging directory | Avoid uploading secrets, logs, or configs |
| Before image publish | Scan layers, metadata, and image filesystem | Detect credentials baked into images |
| After an incident | Re-scan repositories, caches, artifacts, and logs | Identify remaining copy scope |

Scanners should be configured to redact reports. Restrict access to secret detection reports; never paste verbatim findings into issues or chats. For false positives, use narrow allowlists by file or rule with documented justification and expiration dates. Never create broad allowlists that ignore entire config directories.

Secret scanners do not replace DLP or PII checks. A file may contain customer information, production data, or certificates that do not match token patterns recognized by scanners. Therefore, path controls and upload permissions remain essential.

## 11. Rotating and Responding When a Secret Leaks

When a secret is suspected of appearing in source, logs, caches, or artifacts, treat the credential as compromised until scope is verified. Do not wait for a complete investigation before revoking a high-privilege token.

### Incident Response Procedure

1. **Block usability:** revoke tokens, disable keys, or rotate passwords/certificates. Where supported, restrict scope or lock the credential immediately.
2. **Determine scope:** locate commits, workflow runs, logs, artifacts, cache keys, image digests, and systems that received the credential.
3. **Inspect activity:** examine audit logs, API access, registry pulls/pushes, deployments, and anomalous access while the secret was valid.
4. **Replace the credential:** issue a new credential with narrower scope, update the secret manager, and verify workflows operate properly.
5. **Remove copies:** scrub source/history per procedure, remove affected artifacts or images, purge related caches, and restrict log access.
6. **Notify the right teams:** alert system owners, security, and operators per internal process; avoid sending the secret inside notifications.
7. **Prevent recurrence:** add scanners, fix allowlists, tighten permissions, shorten retention, or change how secrets are passed.

Deleting an artifact or log from the UI does not prove all copies are gone. Downloads, mirrors, caches, backups, or exports may still exist. Revoking the credential is the most important measure to render old copies unusable.

### Assessing Impact

When assessing an incident, record the secret type, its permissions, target systems, exposure window, who had read access to the leak location, and any signs of unauthorized usage. Never include the secret value in incident reports; use the fingerprint or credential identifier assigned by the management system.

If a private signing key leaks, consider revoking the key/certificate, evaluating artifacts signed during the exposure window, and re-issuing with a new key. If a registry credential leaks, inspect both read and write access for packages and images.

## 12. Practices That Create a False Sense of Security

| Practice | Why It Is Insufficient | How to Improve |
|---|---|---|
| Only adding `.env` to `.gitignore` | Already tracked or committed files remain | Secret scanning, staged diff reviews, and push protection |
| Deleting a secret in a new commit | Old credential still works and history retains copies | Revoke/rotate first, then address history |
| Relying entirely on log masking | Transformed secret variants may bypass detection | Never log secrets; disable sensitive traces and debug modes |
| Passing tokens on the command line | Exposed via process lists, shell history, or logs | Secret manager, env/file descriptors, or secret mounts |
| Caching all of `$HOME` | May save personal configs and credentials | Allowlist-based caching of dependency directories |
| Uploading the entire workspace | May include `.env`, logs, and temp files | Artifact allowlists and pre-upload scanning |
| Using Docker `ARG`/`ENV` for tokens | Secrets can persist in metadata or layers | BuildKit secret mounts or workload identity |
| Sharing one production secret across all jobs | Expands blast radius if an untrusted job is compromised | Dedicated credentials, least privilege, and short TTLs |
| Running scanners only once | Secrets can appear later in history, logs, or new outputs | Scan at multiple points in the lifecycle |
| Letting PR caches be used by release jobs | Risks consuming data produced by untrusted code | Separate trust scopes and verify inputs |
| Storing secrets in artifacts for downstream jobs | Artifacts often have broad download access and long retention | Downstream jobs fetch credentials directly from secret manager |

## 13. Checklist for Protecting Secrets in CI/CD

Before merging or operating a pipeline, verify:

- [ ] No real secrets exist in source code, example files, scripts, YAML, or recent Git history.
- [ ] `.gitignore` and `.dockerignore` properly exclude local credential files.
- [ ] Secrets are stored in a secret manager or controlled credential system.
- [ ] Each job/step receives only needed secrets; test jobs never receive publish/deploy credentials.
- [ ] OIDC or short-lived credentials are preferred for cloud and registries where supported.
- [ ] Tokens never appear in command lines, URLs, shell history, or process arguments.
- [ ] `set -x`, `env`, `printenv`, and verbose/debug logging are disabled in steps handling secrets.
- [ ] Exceptions, request headers, and response bodies are sanitized before logging.
- [ ] Dynamic secrets are masked before output if supported, without relying on masking alone for protection.
- [ ] Secrets are never written to job outputs, caches, artifacts, or shared intermediate files.
- [ ] Caches contain only required dependency paths; untrusted job caches are never used as inputs for privileged jobs.
- [ ] Artifacts use allowlists with appropriate retention and download permissions.
- [ ] Docker builds use secret mounts; `ARG`/`ENV` and copying credentials into images are avoided.
- [ ] Secret scanning runs on diffs, repositories, and necessary ranges of Git history.
- [ ] False positives are handled with narrow allowlists carrying justification and expiration.
- [ ] Procedures exist for revocation/rotation, log investigation, and cleaning up copies when secrets leak.
- [ ] Artifact signing and production deployment permissions are restricted to approved workflows and identities.

Protecting secrets is not simply masking strings in logs. It is controlling where credentials are created, who can read them, which processes can use them, and which outputs can retain data. When source code, logs, caches, artifacts, and images are all managed under least-privilege principles, pipelines can build and release without turning shared resources into unintended credential stores.
