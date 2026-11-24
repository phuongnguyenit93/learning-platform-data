# Managing Secrets for Maven Settings, Gradle Credentials, and Registries in CI

## 1. Objective

A Spring Boot project may require credentials to download dependencies from a private Maven repository, resolve internal Gradle plugins, publish artifacts, pull CNB builder/run images, or push OCI application images. Placing usernames, passwords, or tokens directly inside a POM, Gradle build script, Dockerfile, or CI script risks leaking them into Git, logs, caches, build artifacts, or container images.

This lesson covers three independent channels:

1. **Maven settings:** credentials for repositories, mirrors, and deployments placed in settings.xml, matched by server ID.
2. **Gradle credentials:** repositories declare a credential type; Gradle retrieves values from Gradle properties/environment variables via typed APIs.
3. **Spring Boot image registries:** credentials for pulling builder/run images and credentials for publishing application images are configured separately; Docker credential helpers/stores may also be used.

The objective is to classify secrets properly, configure tools without hard-coding passwords, inject secrets from CI secret stores, prevent leaks through command lines/logs/caches, and respond to exposed-credential incidents. Examples use Maven, Gradle Kotlin DSL, Spring Boot 3.5, and GitHub Actions.

## 2. Classifying Secrets

| Credential type | Consumer | Appropriate location | Avoid placing in |
| --- | --- | --- | --- |
| Maven repository read | Maven resolver | User/CI settings.xml | Committed POM |
| Maven artifact publish | Maven Deploy Plugin | settings.xml, server ID matching deployment ID | CLI -Dpassword argument |
| Gradle dependency repo | Gradle resolver | Typed credentials + Gradle properties/env | Literals in build scripts |
| Gradle plugin repo | Gradle plugin resolver | pluginManagement + properties/env | Version catalogs |
| Gradle publishing | Gradle publishing task | Publishing repository + typed credentials | Committed project gradle.properties |
| CNB builder/run registry | Spring Boot plugin/Docker client | builderRegistry or Docker credential helper | Maven servers |
| OCI image publish | Spring Boot plugin/Docker client | publishRegistry or Docker credential helper | Dockerfile/image environment |
| Application runtime secret | Application at runtime | Secret manager/orchestrator | JAR, image layer, application.properties |

These channels do not grant permissions to one another. A Maven server ID does not authenticate to a Docker registry; Docker login does not grant Maven read access to a private Maven repository. Use dedicated credentials per purpose with least privilege: read-only when downloading dependencies, write/push only when releasing.

## 3. Maven: settings.xml and Server IDs

### 3.1. POM Describes Repositories; Settings Holds Credentials

Maven defines download repositories in repositories, plugin repositories in pluginRepositories, and publish repositories in distributionManagement inside the POM. Username/password credentials belong to the environment running the build and therefore belong in settings.xml.

~~~xml
<repositories>
    <repository>
        <id>internal-maven</id>
        <url>${env.MAVEN_REPO_URL}</url>
    </repository>
</repositories>

<distributionManagement>
    <repository>
        <id>internal-releases</id>
        <url>${env.MAVEN_DEPLOY_URL}</url>
    </repository>
</distributionManagement>
~~~

internal-maven is the ID for downloading dependencies; internal-releases is the ID for deploying artifacts. An ID is neither a username nor a URL. Environment variables supply endpoints per environment.

### 3.2. settings.xml with Environment Interpolation

The user settings file is typically located at ~/.m2/settings.xml on Linux/macOS or %USERPROFILE%/.m2/settings.xml on Windows.

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<settings xmlns="http://maven.apache.org/SETTINGS/1.2.0"
          xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
          xsi:schemaLocation="http://maven.apache.org/SETTINGS/1.2.0
          https://maven.apache.org/xsd/settings-1.2.0.xsd">
    <servers>
        <server>
            <id>internal-maven</id>
            <username>${env.MAVEN_REPO_USERNAME}</username>
            <password>${env.MAVEN_REPO_PASSWORD}</password>
        </server>
        <server>
            <id>internal-releases</id>
            <username>${env.MAVEN_PUBLISH_USERNAME}</username>
            <password>${env.MAVEN_PUBLISH_PASSWORD}</password>
        </server>
    </servers>
</settings>
~~~

Maven supports environment interpolation for values in settings. The file stores only variable names; actual values are provided by the environment:

- MAVEN_REPO_USERNAME/MAVEN_REPO_PASSWORD for read access.
- MAVEN_PUBLISH_USERNAME/MAVEN_PUBLISH_PASSWORD for deploy access.
- If a variable is unset, the repository may return an auth error; CI should fail clearly when required variables are missing.
- Never commit personal settings containing real credentials. Actual settings live in user home or a runner's temporary directory.

### 3.3. ID Must Match the Repository, Mirror, or Deployment Target

Maven matches credentials by **ID**, not by hostname:

- Server ID must match the request's repository ID.
- Deployment server ID must match the distributionManagement repository ID.
- If Maven routes via a mirror, credentials are typically looked up by the active mirror's ID.
- Plugin repositories have their own IDs and may require separate server entries.

Mirror example:

~~~xml
<mirrors>
    <mirror>
        <id>company-mirror</id>
        <mirrorOf>*</mirrorOf>
        <url>${env.MAVEN_MIRROR_URL}</url>
    </mirror>
</mirrors>
~~~

If requests are routed through company-mirror, server credentials must carry the ID company-mirror. If the repository ID is internal-maven while settings only has server ID maven-user, Maven will not automatically pair them simply because their URLs share a host.

### 3.4. Using a Separate Settings File in CI

When a project has the Maven Wrapper, specify the settings file with the -s option:

~~~bash
./mvnw -s "$RUNNER_TEMP/maven-settings.xml" -B -ntp clean verify
~~~

PowerShell:

~~~powershell
.\mvnw.cmd -s "$env:RUNNER_TEMP/maven-settings.xml" -B -ntp clean verify
~~~

The temporary file should have restricted read permissions, never be uploaded as an artifact, and be cleaned up per retention policy. If the file contains only environment references, secret values still come from the Maven process environment. Deleting the file after the build does not help if it was previously cached/uploaded or printed to logs.

### 3.5. Maven Password Encryption Is Not a Secret Vault

Maven 3 provides commands to encrypt a master password, settings-security.xml, and store encrypted/obfuscated passwords. However, Maven 3 documentation notes that the master password is encrypted using a **hard-coded key**. Treat this mechanism as obfuscation, not a vault or strong protection against anyone able to read the related files.

Practices:

- Use a CI secret store/Vault to supply credentials at build time.
- If using Maven encryption on developer machines, still protect read permissions on ~/.m2 and the OS account.
- Never commit settings.xml or settings-security.xml containing real data.
- Never pass passwords via -Dpassword or command-line arguments visible in process listings.
- Maven 4 has its own encryption guide; do not mix Maven 3 and Maven 4 instructions/file formats without verifying your version.

## 4. Gradle: Typed Credentials and Gradle Properties

### 4.1. Repository Declares Credential Type

Gradle Kotlin DSL:

~~~kotlin
import org.gradle.api.credentials.PasswordCredentials

dependencyResolutionManagement {
    repositories {
        maven {
            name = "internalRepo"
            url = uri(providers.environmentVariable("INTERNAL_REPO_URL").get())
            credentials(PasswordCredentials::class)
        }
    }
}
~~~

Given repository name internalRepo, Gradle looks up two properties: internalRepoUsername and internalRepoPassword. The typed API tells the build which credential type is needed without placing literal passwords in scripts. URLs are not secrets and can come from separate per-environment variables.

### 4.2. Supplying Gradle Credentials via Environment Variables

Gradle supports project properties supplied from environment variables prefixed with ORG_GRADLE_PROJECT_. For the example above, CI supplies:

~~~bash
ORG_GRADLE_PROJECT_internalRepoUsername
ORG_GRADLE_PROJECT_internalRepoPassword
~~~

GitHub Actions environment:

~~~yaml
env:
  ORG_GRADLE_PROJECT_internalRepoUsername: ${{ secrets.INTERNAL_REPO_USERNAME }}
  ORG_GRADLE_PROJECT_internalRepoPassword: ${{ secrets.INTERNAL_REPO_PASSWORD }}
~~~

Property names must match the repository name. If you rename it to companyMaven, both properties must change to companyMavenUsername and companyMavenPassword. Never pass secrets via -PinternalRepoPassword: command-line arguments can be observed by other processes or recorded in audit logs.

### 4.3. gradle.properties for Developer Workstations

One option is the Gradle User Home file, usually at ~/.gradle/gradle.properties or inside GRADLE_USER_HOME. The file can hold internalRepoUsername and internalRepoPassword; developers populate values locally from the organization's password manager/secret store.

This file stores plaintext:

- Never commit files containing credentials to the project.
- Prefer Gradle User Home over project-root gradle.properties.
- On POSIX, restrict permissions, e.g., chmod 700 ~/.gradle and chmod 600 ~/.gradle/gradle.properties.
- Never share a Gradle User Home holding credentials across users or CI jobs of different trust levels.
- Delete/rotate credentials when a user leaves the team or access is no longer needed.

Project gradle.properties is meant for non-secret build properties such as versions or JVM settings. Never use it as a password store for convenience.

### 4.4. Plugin Repositories and Dependency Repositories Are Separate Configurations

Gradle resolves plugins in pluginManagement, separate from repositories used for application dependencies:

~~~kotlin
import org.gradle.api.credentials.PasswordCredentials

pluginManagement {
    repositories {
        maven {
            name = "companyPlugins"
            url = uri(providers.environmentVariable("PLUGIN_REPO_URL").get())
            credentials(PasswordCredentials::class)
        }
        gradlePluginPortal()
    }
}
~~~

CI supplies ORG_GRADLE_PROJECT_companyPluginsUsername and ORG_GRADLE_PROJECT_companyPluginsPassword. Credentials for internalRepo do not automatically apply to companyPlugins.

### 4.5. Gradle Publishing Repositories

With maven-publish:

~~~kotlin
import org.gradle.api.credentials.PasswordCredentials

publishing {
    repositories {
        maven {
            name = "companyReleases"
            url = uri(providers.environmentVariable("PUBLISH_REPO_URL").get())
            credentials(PasswordCredentials::class)
        }
    }
}
~~~

CI supplies ORG_GRADLE_PROJECT_companyReleasesUsername and ORG_GRADLE_PROJECT_companyReleasesPassword. Separate dependency read permissions from deploy permissions; jobs running only tests/compilation do not need publish tokens.

### 4.6. Configuration Cache, Providers, and Gradle Daemon

Gradle Configuration Cache persists task graphs/state to disk. If a build reads a secret eagerly during configuration and assigns it to custom task fields, the value may be serialized into state. Gradle encrypts the cache, yet you must not treat it as a vault or place caches on world-readable network shares.

- Use the typed repository credentials API so Gradle resolves properties directly.
- For tasks needing env secrets, use lazy Providers such as providers.environmentVariable("TOKEN") and resolve only at execution time.
- Avoid calling System.getenv("TOKEN") eagerly during configuration and writing values to task state/logs.
- Restrict access to .gradle/configuration-cache and Gradle User Home.
- Never commit .gradle/, caches, or credential files.
- Verify Configuration Cache compatibility for plugins/tasks in use.

The Gradle Daemon is a long-lived JVM across builds. On shared runners or when building untrusted code, isolate Gradle User Home/daemons per job and avoid reusing processes across trust boundaries.

## 5. Spring Boot: builderRegistry and publishRegistry

### 5.1. Separating Pull and Push

When running spring-boot:build-image or bootBuildImage, the plugin may need to:

1. Pull the **builder image** containing buildpacks and the CNB lifecycle.
2. Pull the **run image** used as the runtime base.
3. Push the **application image** if publish is enabled.

| Property | Permission | Purpose |
| --- | --- | --- |
| docker.builderRegistry | Pull/read | Auth when builder/run images reside in a private registry |
| docker.publishRegistry | Push/write | Auth when publishing the application image |
| docker.host | Docker Engine API | Daemon address, not a registry password |

Maven settings server credentials and Gradle repository credentials do not automatically become Docker registry credentials.

### 5.2. Maven Plugin: Environment Interpolation

Place the following snippet inside spring-boot-maven-plugin in build/plugins:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <image>
            <name>${env.IMAGE_NAME}</name>
            <publish>true</publish>
        </image>
        <docker>
            <builderRegistry>
                <username>${env.BUILDER_REGISTRY_USERNAME}</username>
                <password>${env.BUILDER_REGISTRY_PASSWORD}</password>
            </builderRegistry>
            <publishRegistry>
                <username>${env.IMAGE_REGISTRY_USERNAME}</username>
                <password>${env.IMAGE_REGISTRY_PASSWORD}</password>
            </publishRegistry>
        </docker>
    </configuration>
</plugin>
~~~

This is a plugin snippet, not a standalone POM. Maven reads values from the process environment.

- builderRegistry is only needed if builder/run images require authentication.
- publishRegistry is only needed if the output image must be pushed.
- publish=true enables publishing; if only building a local image, disable publish and do not supply push tokens.
- IMAGE_NAME must be an image reference with appropriate registry/repository/tag.
- If registries are public or handled by a Docker credential helper, omit the corresponding credentials.

### 5.3. Gradle BootBuildImage: Lazy Providers

In build.gradle.kts with Spring Boot Gradle Plugin applied:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootBuildImage

tasks.named<BootBuildImage>("bootBuildImage") {
    imageName.set(providers.environmentVariable("IMAGE_NAME"))
    publish.set(true)

    docker {
        builderRegistry {
            username.set(
                providers.environmentVariable("BUILDER_REGISTRY_USERNAME")
            )
            password.set(
                providers.environmentVariable("BUILDER_REGISTRY_PASSWORD")
            )
        }
        publishRegistry {
            username.set(
                providers.environmentVariable("IMAGE_REGISTRY_USERNAME")
            )
            password.set(
                providers.environmentVariable("IMAGE_REGISTRY_PASSWORD")
            )
        }
    }
}
~~~

Providers wire directly into Gradle task properties, avoiding hard-coded secrets and eager environment reads in the build script. CI must supply the right variables. If the builder is public or the image is built locally only, omit unnecessary configuration.

### 5.4. Docker Config and Credential Helpers

Spring Boot plugins can read Docker CLI config (typically $HOME/.docker/config.json) for auth if not declared directly. Docker can use a credential helper/store or static auth.

Static auth in config may just be Base64-encoded username/password, **not encryption**. Never commit config.json or upload it as an artifact. On runners, prefer helpers/secret integrations, or temporary configs with restricted permissions cleaned up after the job.

Docker login reads passwords via stdin:

~~~bash
printf '%s' "$REGISTRY_TOKEN" | docker login "$REGISTRY_HOST" --username "$REGISTRY_USERNAME" --password-stdin
~~~

Never use docker login -p TOKEN or pass tokens as command-line arguments. Never echo "$REGISTRY_TOKEN" to the console. Without a credential helper, the Docker config file may hold Base64 auth; protect file read permissions and lifecycle.

### 5.5. Local Build vs. Publish

spring-boot:build-image/bootBuildImage can create an image in the daemon store without publishing. When publishing:

- Image name must include the right registry/repository/tag.
- publishRegistry or Docker credential helper needs push permissions.
- Successfully pulling the builder does not prove push permissions exist.
- Images on a remote daemon do not automatically appear in local Docker Desktop.
- If the local image exists yet the registry lacks it, check the publish flag and push logs rather than changing Docker hosts.

## 6. Build-Time Secrets vs. Runtime Secrets

There are three usage points:

**Dependency resolution:** Maven/Gradle needs credentials to download libraries/plugins. Supply them to the build process via settings/properties. Never put passwords in application source code.

**CNB builder:** Buildpacks may need proxies or credentials to download artifacts during the lifecycle. Spring Boot plugin environment variables are not a generic secret vault; buildpacks may log or write data into outputs. If a buildpack needs a secret during build, use a dedicated secret binding/credential integration supported by the builder, mount read-only when possible, and verify values never enter image layers.

**Application runtime:** Database passwords/API keys must be injected when the container runs from a secret manager/orchestrator, such as Kubernetes Secrets or a cloud secret manager. Never bake them into application.properties, Dockerfile ENV, buildpack image environments, or JARs.

Dependency-download credentials are not runtime credentials; builder-pull credentials are not application-image push credentials.

## 7. CI: Delivering Secrets from the Secret Store to the Right Job

### 7.1. Release Flow

A release job should:

1. Check out a trusted revision.
2. Select a reviewed JDK and Maven/Gradle Wrapper.
3. Obtain secrets from the CI secret store/Vault or OIDC.
4. Create temporary settings/properties/configs with restricted permissions.
5. Run tests/verification before publishing.
6. Build and publish the image with least privilege.
7. Verify the image tag/digest.
8. Clean up temporary settings, Docker configs, and workspaces per retention policy.

Never grant publish secrets to every pull request. Jobs testing unreviewed code should run without release secrets; if private dependencies are needed, use a read-only token or a CI-specific mirror/proxy.

### 7.2. GitHub Actions Maven Snippet

Example release workflow triggered only on tags. Production environments can enforce approval/protection rules:

~~~yaml
name: publish-image

on:
  push:
    tags:
      - "v*"

jobs:
  publish:
    runs-on: ubuntu-latest
    environment: production
    permissions:
      contents: read
      packages: write

    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: "17"

      - name: Verify and publish
        shell: bash
        env:
          MAVEN_REPO_USERNAME: ${{ secrets.MAVEN_REPO_USERNAME }}
          MAVEN_REPO_PASSWORD: ${{ secrets.MAVEN_REPO_PASSWORD }}
          BUILDER_REGISTRY_USERNAME: ${{ secrets.BUILDER_REGISTRY_USERNAME }}
          BUILDER_REGISTRY_PASSWORD: ${{ secrets.BUILDER_REGISTRY_PASSWORD }}
          IMAGE_REGISTRY_USERNAME: ${{ secrets.IMAGE_REGISTRY_USERNAME }}
          IMAGE_REGISTRY_PASSWORD: ${{ secrets.IMAGE_REGISTRY_PASSWORD }}
        run: |
          set -eu
          install -d -m 700 "$RUNNER_TEMP/maven"
          cat > "$RUNNER_TEMP/maven/settings.xml" <<'EOF'
          <settings xmlns="http://maven.apache.org/SETTINGS/1.2.0">
            <servers>
              <server>
                <id>internal-maven</id>
                <username>${env.MAVEN_REPO_USERNAME}</username>
                <password>${env.MAVEN_REPO_PASSWORD}</password>
              </server>
            </servers>
          </settings>
          EOF
          chmod 600 "$RUNNER_TEMP/maven/settings.xml"
          ./mvnw -s "$RUNNER_TEMP/maven/settings.xml" -B -ntp clean verify
          ./mvnw -s "$RUNNER_TEMP/maven/settings.xml" -B -ntp spring-boot:build-image
~~~

The example assumes the POM already configures publish and publishRegistry. If builder/run images are public, omit builder credentials. If only building a local image, omit publish config and do not supply push tokens. The temporary settings file contains environment references, not actual secret values.

### 7.3. GitHub Actions Gradle Environment

For a Gradle repository named internalRepo, supply:

~~~yaml
env:
  ORG_GRADLE_PROJECT_internalRepoUsername: ${{ secrets.INTERNAL_REPO_USERNAME }}
  ORG_GRADLE_PROJECT_internalRepoPassword: ${{ secrets.INTERNAL_REPO_PASSWORD }}
  BUILDER_REGISTRY_USERNAME: ${{ secrets.BUILDER_REGISTRY_USERNAME }}
  BUILDER_REGISTRY_PASSWORD: ${{ secrets.BUILDER_REGISTRY_PASSWORD }}
  IMAGE_REGISTRY_USERNAME: ${{ secrets.IMAGE_REGISTRY_USERNAME }}
  IMAGE_REGISTRY_PASSWORD: ${{ secrets.IMAGE_REGISTRY_PASSWORD }}
~~~

Then:

~~~bash
./gradlew --no-daemon clean test bootBuildImage
~~~

The ORG_GRADLE_PROJECT_... variables provide Gradle properties for the repository; the registry variables are read by BootBuildImage Providers. Never store them in project gradle.properties.

### 7.4. Forked Pull Requests and Workflow Permissions

GitHub Actions does not pass standard repository secrets to workflows triggered from forked pull requests (with separate scoped rules for GITHUB_TOKEN). Therefore:

- Run unit tests/compilation on PRs without publish credentials.
- If private dependencies are needed, supply a policy-approved read-only token or CI mirror.
- Only expose publish secrets in release jobs/protected environments.
- Never use pull_request_target to check out and execute untrusted code with secrets.
- Restrict which branches/tags can deploy and who can create releases.
- Pin action versions/commit SHAs per organizational supply-chain policy.

### 7.5. OIDC and Short-Lived Tokens

If your cloud/registry supports OpenID Connect, CI can prove workflow identity to obtain short-lived credentials instead of static access keys. Trust policies should restrict repository, branch/tag, environment, and audience. Workflows need id-token: write permission when required by the provider.

OIDC does not automatically work with every Maven repository or Docker registry; the provider must support federation. Otherwise, use narrowly scoped short-lived tokens with regular rotation.

## 8. Preventing Secrets from Leaking into Logs, Caches, and Artifacts

### 8.1. Never Dump Environments or Enable Debug Recklessly

Never run these commands in jobs holding secrets:

~~~bash
env
printenv
echo "$MAVEN_REPO_PASSWORD"
set -x
mvn -X
./gradlew --debug
~~~

env/printenv can dump all variables; shell tracing prints expanded commands; Maven -X/Gradle --debug can print sensitive config/metadata. Use set -eu instead of set -x. If a dynamic secret needs masking, call CI's masking mechanism before the value can appear in logs; masking never replaces avoiding logging.

### 8.2. Never Upload Sensitive Files

Never cache or upload these files:

- ~/.m2/settings.xml and settings-security.xml.
- ~/.gradle/gradle.properties containing credentials.
- $DOCKER_CONFIG/config.json.
- Temporary Maven settings/Docker configs.
- Gradle Configuration Cache or Gradle User Home holding sensitive state.
- Logs containing request headers, tokens, or environment dumps.

Use .gitignore/.dockerignore to keep local sensitive files out of repositories/build contexts. Never write secrets into generated sources, application resources, manifests, or build metadata.

### 8.3. Docker Config and Image Layers

Without a credential helper, Docker config can store Base64 auth. Protect the file like plaintext: never commit it, never include it in the Docker context, and never upload it as an artifact. On ephemeral runners, use a temporary DOCKER_CONFIG with restricted permissions and clean it up after the job.

Never put registry tokens into Dockerfile ARG/ENV, image labels, CNB build environments, or image layers. If a buildpack needs access to private artifacts, use the dedicated secret binding/credential mechanism supported by the buildpack.

### 8.4. Gradle Cache and Daemon

Gradle User Home contains credentials, plugin/dependency caches, init scripts, and daemon state. Restrict access to this directory and never share a writable home across CI jobs of differing trust levels. Configuration Cache is encrypted, yet cache directories/keys still need protection. Remote build caches should restrict push permissions to trusted builds; untrusted PR builds should be pull-only or isolated in a separate namespace.

### 8.5. When a Secret Has Leaked

Treat any credential that appeared in logs, artifacts, Git, or images as **compromised**:

1. Revoke/rotate the credential immediately.
2. Inspect audit logs to see which resources may have been accessed.
3. Restrict/purge sensitive logs or artifacts per retention policy.
4. Check caches, Docker images, Git history, and workflow artifacts.
5. Issue new credentials with least privilege.
6. Fix the root cause that logged/packaged the secret; deleting one log line is not enough.

## 9. Troubleshooting

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Maven HTTP 401 on resolve | Server ID does not match repository/mirror | Match the actual request ID with the server ID |
| Maven downloads work yet deploy returns 401 | Missing server ID for distributionManagement | Add dedicated deploy credentials |
| Maven mirror ignores credentials | Server entry uses original repository ID instead of mirror | Match the actual mirror ID |
| Maven env placeholder does not resolve | CI did not supply env var or wrong variable name | Check variable name without printing value; check the right Maven process |
| Maven encrypted password treated as plaintext | Mistook Maven 3 encryption for a vault | Use CI secret store; protect settings/security files |
| Gradle reports missing credentials | Property names do not match repository name | Check name and repoNameUsername/Password |
| Gradle plugin repo fails to resolve | Credentials configured only on dependency repo | Add credentials in pluginManagement |
| Gradle secret appears in Git diff | Literal in build script/project properties | Revoke if committed, move to user home/env, audit Git history |
| Gradle Configuration Cache holds sensitive data | Secret read eagerly during configuration | Use typed API/lazy Providers; restrict cache access |
| Spring Boot fails to pull builder | Missing builderRegistry auth or Docker credential helper | Check builder/run registry credentials |
| Builder pull OK, app push 401 | Builder read credential lacks push permission | Check publishRegistry and publish permissions |
| Docker login OK yet plugin fails auth | Different user/DOCKER_CONFIG/context | Check config for the exact Maven/Gradle process |
| Registry auth fails | Expired token/wrong scope/wrong registry host | Check pull/push rights, tag, and endpoint |
| Secrets empty on fork PR | CI withholds secrets from forks | Do not require release secrets in PR jobs |
| Token appears in logs | Shell trace/debug/echo/command args | Rotate, audit, fix logging and workflow |
| Runtime app missing DB secret | Secret not injected at deploy time | Use orchestrator/secret manager; never bake into image |

Debugging workflow: identify the **phase** (dependency, plugin, builder pull, image push, runtime), identify the **consumer**, check the **ID/property name**, verify secrets are supplied to the right job, confirm read/pull vs. write/push permissions, and only then modify config. Never print passwords/tokens to verify them.

## 10. Exercises and Answers

**Exercise 1.** The POM repository ID is internal-maven while the settings server ID is maven-user. Does Maven match by hostname?

**Answer:** No. Maven matches by ID. The server ID must match the actual repository/mirror ID.

**Exercise 2.** Can you commit settings.xml if passwords were encrypted with Maven 3?

**Answer:** You should not. Maven 3 encryption is not a secret vault; the file must still be protected as if it held plaintext.

**Exercise 3.** A Gradle repository is named internalRepo. Which property names does CI need to supply?

**Answer:** ORG_GRADLE_PROJECT_internalRepoUsername and ORG_GRADLE_PROJECT_internalRepoPassword.

**Exercise 4.** Does PasswordCredentials automatically add dependencies to the classpath?

**Answer:** No. It only declares how to authenticate to the repository; dependencies must be declared separately.

**Exercise 5.** Pulling the builder succeeds, yet pushing the image returns 401. Which property should you check?

**Answer:** docker.publishRegistry and publish permissions. builderRegistry is only for pulling builder/run images.

**Exercise 6.** Maven settings contains server credentials. Does the Spring Boot plugin automatically use them for Docker registries?

**Answer:** Not by default. Use publishRegistry/builderRegistry or Docker credential helpers/config.

**Exercise 7.** Why should docker login -p TOKEN be avoided?

**Answer:** The token appears in command-line arguments. Use --password-stdin or a credential helper.

**Exercise 8.** Gradle reads System.getenv("TOKEN") eagerly while configuring a task. What is the risk?

**Answer:** The secret can leak into task/configuration state/caches. Use lazy Providers and the typed credentials API.

**Exercise 9.** A GitHub fork PR receives empty secrets. Is this a variable-naming bug?

**Answer:** Not necessarily. GitHub does not pass standard repository secrets to fork PR workflows. PR jobs should not require release credentials.

**Exercise 10.** Where should the database password for an app running on Kubernetes reside?

**Answer:** In a secret manager/Kubernetes Secret injected at runtime. Never write it into a JAR, Dockerfile, or image layer.

## 11. Pre-Merge/Release Checklist

- [ ] Every credential has a clear purpose: repository read, artifact publish, builder pull, image publish, or runtime.
- [ ] Maven credentials live in user/CI settings.xml; POM contains no literal passwords.
- [ ] Maven server IDs match actual repository/mirror/deployment IDs.
- [ ] Maven environment variables are supplied to the right process and never logged.
- [ ] Maven 3 password encryption is never treated as a vault.
- [ ] Gradle uses credentials(PasswordCredentials::class) or an appropriate typed API.
- [ ] Gradle repository name and property identities match; CI supplies the exact ORG_GRADLE_PROJECT_... variables.
- [ ] Gradle credentials never reside in committed project gradle.properties.
- [ ] Gradle User Home, Configuration Cache, and Daemon have restricted access.
- [ ] Spring Boot builderRegistry has only required pull permissions.
- [ ] Spring Boot publishRegistry has only push permissions for allowed repositories/tags.
- [ ] Docker credential helpers/stores preferred; static Base64 auth protected like plaintext.
- [ ] Settings files, Gradle properties, Docker configs, and caches are never uploaded/cached.
- [ ] Never use set -x, mvn -X, Gradle --debug, or env in jobs holding secrets.
- [ ] Docker login uses --password-stdin, never passing tokens on the command line.
- [ ] Release secrets are granted only to trusted branches/tags/environments.
- [ ] OIDC/short-lived tokens preferred where supported by providers.
- [ ] Runtime secrets injected at deploy time, never baked into JARs/images.
- [ ] Revoke/rotate/audit procedures in place if a secret leaks.

## 12. Official Documentation

- Apache Maven — Settings Reference: https://maven.apache.org/settings.html
- Apache Maven — Password Encryption (Maven 3): https://maven.apache.org/guides/mini/guide-encryption.html
- Apache Maven — Password Encryption (Maven 4): https://maven.apache.org/guides/mini/guide-encryption-4.html
- Gradle — Supported Protocols / Handling Credentials: https://docs.gradle.org/current/userguide/supported_repository_protocols.html
- Gradle — Securing the Build Tool: https://docs.gradle.org/current/userguide/securing_build_tool.html
- Gradle — Configuration Cache Requirements: https://docs.gradle.org/current/userguide/configuration_cache_requirements.html
- Gradle — Build Environment Configuration: https://docs.gradle.org/current/userguide/build_environment.html
- Spring Boot 3.5 — Maven Packaging OCI Images: https://docs.spring.io/spring-boot/3.5/maven-plugin/build-image.html
- Spring Boot 3.5 — Gradle Packaging OCI Images: https://docs.spring.io/spring-boot/3.5/gradle-plugin/packaging-oci-image.html
- Docker — Login and Password STDIN: https://docs.docker.com/reference/cli/docker/login/
- Docker — Credential Stores: https://docs.docker.com/reference/cli/docker/login/#credential-stores
- GitHub Actions — Using secrets in a workflow: https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets
- GitHub Actions — OpenID Connect: https://docs.github.com/en/actions/concepts/security/openid-connect

**Conclusion:** Maven uses settings.xml with server IDs; Gradle uses typed credentials and Gradle properties; Spring Boot separates credentials for pulling builder/run images from publishing application images. CI should pull secrets from a secret store or OIDC, scope them to trusted jobs, keep them out of command lines/logs/caches/artifacts, and keep application runtime secrets outside JARs and container images.