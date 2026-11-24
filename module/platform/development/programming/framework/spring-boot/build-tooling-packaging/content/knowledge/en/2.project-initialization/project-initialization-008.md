# Distinguishing Source Files, Git-Tracked Configuration, and Generated Outputs When Initializing a Spring Boot Project

## 1. Why Classify Files Right at Project Creation?

After downloading a project from **Spring Initializr**, the project folder already contains sample source code, Maven or Gradle configuration files, wrapper scripts, and supporting files. When you run the first build, Maven/Gradle generates many new directories and files. If you put everything into Git, the repository quickly fills with JARs, compiled classes, test reports, caches, and sometimes sensitive information. If you omit essential configuration, teammates or CI may not be able to reproduce the build.

Separate files by **role and reproducibility**, rather than solely by file extension:

1. **Source files**: authored and edited by humans, or serving as a long-term source of truth.
2. **Configuration to manage in Git**: describes how to compile, run, test, package, and deploy; values must be safe to share.
3. **Generated outputs**: results produced from source + configuration + tools, which can be regenerated via build commands or corresponding tasks.

This classification applies to both Maven and Gradle. A file can be **source configuration** in `src/main/resources` and then appear as an **output copy** in the build directory; those two copies have different Git policies.

## 2. Group 1 — Source Files to Track in Git

In a standard Java Spring Boot project, the following files are development inputs:

| Location/File | Role | Usually Commit? |
|---|---|---|
| `src/main/java/**/*.java` | Application Java code: `@SpringBootApplication`, controllers, services, repositories, models | Yes |
| `src/test/java/**/*.java` | Unit tests, integration tests, Java test fixtures | Yes |
| `src/main/resources/**` | Original resources such as templates, static assets, SQL migrations, shareable runtime config | Yes, after removing secrets |
| `src/test/resources/**` | Test input data, properties, and fixtures | Yes, if safe |
| `api/openapi.yaml`, `src/main/proto/*.proto` | Specifications serving as code-generation inputs or interface contracts | Yes |
| `README.md`, design docs, custom scripts | Instructions for reproducing, operating, and developing the project | Yes |

For Kotlin, sources usually live in `src/main/kotlin` and `src/test/kotlin`; the principle is unchanged. For integrated web UIs, original JavaScript/CSS sources should also be committed, while compiler-generated bundles should be classified according to the specific pipeline.

**Note on `resources`:** `src/main/resources/application.yml` is the source configuration file; its copy in `target/classes/application.yml` (Maven) or `build/resources/main/application.yml` (Gradle) is only a build output. Do not commit both.

## 3. Group 2 — Configuration to Manage in Git for Reproducible Builds

These configuration files are not necessarily Java code, yet omitting them can cause other team members to produce different artifacts or fail to run the project:

| File/Directory | What Is It For? | Recommendation |
|---|---|---|
| `pom.xml` | Maven coordinates, dependencies, plugins, lifecycle, packaging | Commit |
| `build.gradle` or `build.gradle.kts` | Gradle plugins, dependencies, tasks, and build configuration | Commit |
| `settings.gradle` / `settings.gradle.kts` | Gradle project name and module list | Commit |
| Project `gradle.properties` | Shared build properties, when free of tokens or passwords | Commit safe portions |
| `mvnw`, `mvnw.cmd`, `.mvn/wrapper/**` | Maven Wrapper and configuration for downloading/using Maven | Commit required wrapper files |
| `gradlew`, `gradlew.bat`, `gradle/wrapper/gradle-wrapper.properties`, `gradle/wrapper/gradle-wrapper.jar` | Gradle Wrapper, distribution, and wrapper bootstrapper | Normally commit |
| `.gitignore`, `.gitattributes` | Git tracking and attribute rules | Commit |
| `.github/workflows/*.yml` or equivalent CI files | Automated build/test/publish | Commit |
| `Dockerfile`, `compose.yaml`, deployment config | Defines packaging/operations, if free of secrets | Commit |
| `src/main/resources/application.yml` | Shared environment-friendly Spring Boot configuration values | Commit **if free of secrets** |

**Wrappers are an easy edge case to get wrong:** `gradle-wrapper.jar` is a binary file, yet it is tracked in Git so the team can use the defined wrapper version without installing Gradle globally. Do not add a blanket `*.jar` rule that accidentally ignores the wrapper. In Maven Wrapper, actual files depend on the generated wrapper type: some projects include `.mvn/wrapper/maven-wrapper.jar`, others do not. Keep the required wrapper files created by the tool; do **not** ignore all of `.mvn/`.

**Build configuration and runtime configuration differ.** `pom.xml` determines how the artifact is built; `application.yml` supplies application properties at runtime. `spring.application.name`, HTTP port, and non-sensitive defaults can be tracked in Git; passwords, private keys, and access tokens must come from an appropriate secure source.

## 4. Group 3 — Generated Outputs That Should Not Be Committed

When building the project, the tool creates intermediate and final artifacts from the managed inputs:

| Maven | Gradle | Contents |
|---|---|---|
| `target/classes/` | `build/classes/` | Compiled `.class` bytecode |
| `target/test-classes/` | `build/classes/java/test/` | Test bytecode |
| `target/*.jar`, `target/*.war` | `build/libs/*.jar`, `build/libs/*.war` | Packaged artifacts |
| `target/generated-sources/` | `build/generated/` | Java/Kotlin code auto-generated by plugins or annotation processors |
| `target/surefire-reports/` | `build/test-results/`, `build/reports/` | Test results and reports |
| `target/` temporary files | `build/tmp/` | Intermediate working files |

In addition, `.gradle/` inside the project is local build cache/state and usually should not go into Git. `*.log` logs, IDE temporary files, and `.env` files holding secrets or machine-specific settings are also normally uncommitted. User-level dependency caches like `~/.m2/repository` and `~/.gradle/caches` are not repository sources.

**The application JAR is an output, not an input:** in a Spring Boot project with an appropriate packaging plugin, an executable JAR can contain application classes and required dependencies, regenerated on each build. Typically CI builds the artifact and stores it in an artifact registry or release system; the Git repository holds the source and recipe to produce that artifact.

## 5. Example Directory Structure After Initialization and Build

Suppose Spring Initializr generates an `order-service` with Maven:

```text
order-service/
├── .gitignore                         # Git: tracking rules
├── .mvn/
│   └── wrapper/
│       └── maven-wrapper.properties    # Git: wrapper configuration
├── mvnw                                # Git: Unix wrapper script
├── mvnw.cmd                            # Git: Windows wrapper script
├── pom.xml                             # Git: build definition
├── README.md                           # Git: documentation
├── src/
│   ├── main/
│   │   ├── java/com/acme/orders/
│   │   │   ├── OrdersApplication.java  # Git: Java source code
│   │   │   └── web/OrderController.java
│   │   └── resources/
│   │       └── application.yml         # Git: safe configuration
│   └── test/
│       └── java/com/acme/orders/
│           └── OrdersApplicationTests.java
└── target/                             # IGNORE: generated by Maven after build
    ├── classes/
    ├── generated-sources/
    ├── surefire-reports/
    └── order-service-0.1.0-SNAPSHOT.jar
```

This is an **illustrative diagram**: a freshly generated project may not yet have a controller, README, or some folders; `target/` does not exist before the first build. A Gradle project will have `build.gradle[.kts]`, `settings.gradle[.kts]`, `gradlew`, `gradle/wrapper/`, and output directory `build/`.

Output generation flow:

```text
Source code + resources + build configuration
                    |
                    v
         Maven / Gradle Wrapper
                    |
            compile + test
                    |
                    v
          target/ or build/
                    |
          JAR / WAR / reports
```

Git stores **reproducible inputs**; the build pipeline and artifact registry receive **outputs**. When verifying a release, record the Git commit, version, toolchain version, and artifact details in CI/release.

## 6. Writing a Minimal, Intentional `.gitignore`

A common template for repositories buildable with Maven or Gradle:

```gitignore
# Build output: Maven and Gradle
target/
build/
.gradle/

# Logs and local configuration
*.log
.env
.env.*
!.env.example
```

This template is only a starting point. You can add OS/IDE files based on actual needs; do not automatically exclude every IDE directory if the team intentionally shares certain formatting or run configurations.

- `target/` and `build/` in this template ignore directories of those names at nested levels as well, useful in multi-module builds too.
- `.gradle/` is local state. Do **not** confuse it with `gradle/wrapper/`, which is a required input to commit.
- `.env` and `.env.*` prevent accidentally staging local environment files; `!.env.example` allows committing a template **without secrets**.
- Avoid overly broad rules like `*.jar`, `*.yml`, `src/main/resources/`, or `.mvn/` because they can block essential sources/configuration.
- `.gitignore` only prevents Git from automatically listing **untracked files**; it does not untrack files already committed.

Verification examples after building:

```bash
git status --short
git check-ignore -v target/classes/
git ls-files target/
```

`git status --short` lists changes; `git check-ignore -v` shows which rule ignores a path; `git ls-files target/` shows whether any outputs under `target/` are already tracked by Git. For Gradle, replace `target/` with `build/`. A directory not yet created or empty may yield no useful output from ignore checks; run a build before verifying.

If outputs were already committed previously, adding `.gitignore` alone is not enough. After checking the exact paths and deciding to remove them from the repository, you can run `git rm -r --cached target/` to **untrack them in Git while keeping files in the working tree**, then inspect `git diff --cached` before committing. This creates a Git change that needs review; do not run it carelessly on source directories.

## 7. Spring Boot Configuration: Which Files to Commit, Which to Keep Secret?

Example `src/main/resources/application.yml` that is safe to commit if it only holds the application name and environment variable references:

```yaml
spring:
  application:
    name: order-service
  datasource:
    url: ${DB_URL}
    username: ${DB_USERNAME}
    password: ${DB_PASSWORD}
```

When running the application with a datasource, the system must supply `DB_URL`, `DB_USERNAME`, and `DB_PASSWORD` (or equivalent external configuration). This is a **configuration example**, not a guide for an empty Spring Boot app to connect to a database automatically; it also requires JDBC/JPA dependencies and the matching driver.

Normal values safe to manage in Git: `spring.application.name`, general logging settings, default timeouts, non-secret feature flags, and environment configuration templates. Values that must be protected: real passwords, API keys, private keys, tokens, connection strings with credentials, and personal certificates. For secrets, use environment variables, a secret manager, or your infrastructure's secret injection mechanism. Do not hardcode real secrets in `application-prod.yml`, `gradle.properties`, or GitHub Actions YAML.

An `.env.example` can list **variable names and harmless sample values**; never copy a real `.env` file into the repository. `.gitignore` does not protect history if a secret was ever committed: when a secret is exposed, revoke/rotate it, handle history per organizational policy, and check where artifacts/logs were distributed.

Also watch out for **resources copied into the JAR**: if `src/main/resources/application.yml` contains secrets, packaging can embed secrets inside the JAR. Not committing `target/` does not fix this.

## 8. Special Cases: Generated Source Code and Binary Files

**Auto-generated source code** such as Java from OpenAPI, Protocol Buffers, or annotation processors may appear in `target/generated-sources/` or `build/generated/`. If code generation is part of a reproducible build, normally commit the **input spec + generator version + generation config**, and ignore the generated output. This avoids merge conflicts and reduces noisy diffs upon regeneration.

However, there is no absolute rule that "generated files must always be ignored." Some systems intentionally commit generated SDKs/clients so consumers do not need the generator, or commit artifacts required by a release workflow. In such cases, establish a clear policy on who regenerates them, generator versions, how to review diffs, and when to refresh files. **File location, reproducibility, and distribution contracts** are the deciding factors.

Similarly, `gradle-wrapper.jar` is a tool-generated binary yet is normally committed to bootstrap builds. Conversely, `build/libs/order-service.jar` is a build product and is usually published to a registry. Do not classify files based solely on the `.jar` extension.

Some "auto-generated" IDE files (for example, workspace-specific metadata or indexes) do not serve build reproducibility; avoid committing them unless the team agrees they are valuable shared settings.

## 9. Practical Workflow After Downloading from Spring Initializr

**Step 1 — Identify sources and configuration.** Open `src/`, `pom.xml` or `build.gradle`, wrapper files, and `.gitignore`; verify `application.properties` / `application.yml` and profile files contain no secrets.

**Step 2 — Run a build using the generated wrapper.** Pick **one** command matching your build tool:

```bash
# Maven on macOS/Linux
./mvnw clean package

# Gradle on macOS/Linux
./gradlew clean build
```

On Windows, run `mvnw.cmd clean package` or `gradlew.bat clean build` from the project directory. Build success depends on the JDK, connectivity to dependency repositories, and project/test configuration.

**Step 3 — Observe outputs.** Maven typically generates `target/`, and Gradle generates `build/`; confirm they do not appear as new files to commit in `git status --short`. If you just initialized a repository with no commits yet, Git may list all source/config files as untracked, which is normal.

**Step 4 — Review before staging.** Use `git status --short` and verify `.gitignore` against sensitive files. After staging intentional files, `git diff --cached --name-only` lists files about to be committed; `git diff --cached` displays textual diffs. Do not run `git add .` without reviewing if the repository has local environment configs.

**Step 5 — Verify reproducibility.** Teammates or CI should be able to check out the commit, use the right JDK and wrapper, download dependencies, run tests, and build the JAR without copying `target/` or `build/` from another machine. For environments requiring private dependencies, configure repository/credentials in the proper place without putting credentials into Git.

## 10. Common Errors and Troubleshooting

| Symptom | Common Cause | How to Fix |
|---|---|---|
| Commit contains thousands of `.class` files | Added `target/` or `build/` to Git | Untrack outputs, add ignore rules, and review diffs |
| Cloned project cannot build | Missing `pom.xml`, wrapper, plugin config, or dependency declarations | Commit complete sources/config, use wrapper, and test a clean build |
| Gradle Wrapper fails on a new machine | Forgot `gradle-wrapper.jar` or `gradle-wrapper.properties` | Check all wrapper files that must be distributed |
| Secret appears in Git/JAR | Put passwords/tokens in resources or config | Move to external secrets, revoke exposed secrets, inspect artifacts |
| `git status` still shows outputs after updating ignore | Outputs were already tracked previously | Run `git ls-files`, untrack intentionally |
| Generated files keep changing during builds | Generator/plugin version or inputs not pinned | Pin versions, configuration, inputs, and regeneration workflow |
| Edited a file in `target/classes` and lost it after clean | Edited an output file directly | Edit the corresponding source in `src/main` and rebuild |

## 11. Checklist Before the First Commit

- **Sources:** Has `src/main`, `src/test`, specs, and required docs; never edits files directly inside output directories.
- **Configuration:** Has Maven/Gradle build files, wrapper, `.gitignore`, safe CI/runtime config, and example files so newcomers know how to run it.
- **Outputs:** `target/`, `build/`, `.gradle/`, reports, logs, and local caches are excluded from commits, barring explicitly documented exceptions.
- **Security:** No real passwords, tokens, or private keys in sources/config, sample files, recent history, or packaged artifacts.
- **Reproducibility:** A fresh checkout + right JDK + wrapper + dependencies can run a clean build and regenerate the expected artifact.

**Remember:** Git should store **source code along with the recipe to build the application**. Maven/Gradle executes that recipe and produces **classes, reports, and JAR/WAR files**. Whether a file should be committed depends on its role in the reproducibility and release workflow, not merely on whether it is a config file, binary, or tool-generated file.