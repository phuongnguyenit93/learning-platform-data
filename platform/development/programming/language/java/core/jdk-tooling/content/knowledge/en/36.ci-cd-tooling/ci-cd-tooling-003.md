# JDK Caching in CI/CD

**JDK caching** is the practice of saving a downloaded Java Development Kit installer/installation so subsequent CI/CD runs can reuse it without downloading and extracting it from scratch. This reduces runner preparation time, especially when pipelines run on fresh machines, ephemeral runners, or require multiple JDK versions.

JDK caching is strictly an environment initialization optimization. The pipeline must still run on the declared JDK, verify its vendor, version, and architecture, and be able to re-download the installer on a cache miss. A missing, evicted, or incompatible cache must never alter the build result.

## 1. Distinguishing Java-related cache types

In CI/CD, several storage layers are often loosely referred to as "Java cache," even though they store different data:

| Type | Contents | Purpose |
|---|---|---|
| **Runner tool cache** | JDK pre-installed on the runner or installed during a job | Reuse the toolchain directly on the runner |
| **JDK installation cache** | Downloaded and extracted JDK persisted across runs | Skip download/extract when a fresh runner needs the same JDK |
| **Dependency cache** | Maven local repository, Gradle dependency cache, sbt/Ivy cache | Avoid re-downloading project libraries |
| **Build cache** | Reusable task/compilation outputs | Avoid re-executing build tasks that already have valid results |
| **Container image layers** | OS, JDK, and tools packaged in an image | Standardize the toolchain and reuse image layers |
| **Artifacts** | JARs, WARs, test reports, output binaries | Pass build outputs between jobs/stages or store final outputs |

Do not merge the JDK into the Maven/Gradle dependency cache. The JDK is a runner toolchain; Maven/Gradle libraries are project inputs. The two layers have different lifecycles, sizes, cache keys, and verification mechanisms.

For example, **actions/setup-java** can manage both the JDK cache and the dependency cache. When dependency caching is enabled, JDK caching is also enabled by default in current versions of the action unless **cache-jdk: false** is configured. This does not mean the two caches are the same: they are stored as separate cache entries.

## 2. When is JDK caching useful?

JDK caching is typically beneficial in the following scenarios:

- GitHub Actions uses a fresh hosted runner for every job and must install a JDK not available in the tool cache.
- Self-hosted runners or autoscaled runners are frequently recreated.
- The pipeline uses multiple JDKs/vendors/architectures and has to download large installers each time.
- A custom JDK is distributed from an internal repository.
- Matrix jobs require the exact same JDK identity across multiple runs.

Caching may offer little benefit when the runner already has the exact JDK pre-installed in its tool cache, the container image already includes the JDK, or download/extraction time is negligible compared to total build time. Caching also incurs upload, download, storage, and eviction overhead. Measure cold runs and warm runs before adding another cache layer.

## 3. GitHub Actions: using actions/setup-java

**actions/setup-java** installs the requested JDK, sets `JAVA_HOME`, and adds Java to `PATH`. The action checks the runner tool cache first. If the runner already has a matching JDK for the version, distribution, package type, and architecture, the action can use the pre-installed version without re-downloading.

GitHub-hosted runners come with several Eclipse Temurin versions pre-installed. The action only needs to download the JDK when requesting a distribution or version not present in the tool cache. For downloaded JDKs, the `cache-jdk` option saves the installation so subsequent runs can restore it.

### 3.1. Cache only the JDK, without caching dependencies

Example workflow that only caches Eclipse Temurin JDK 21:

~~~yaml
name: Java CI

on:
  push:
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: temurin
          java-version: '21'
          cache-jdk: true

      - name: Verify selected JDK
        run: |
          java -version
          javac -version

      - name: Build
        run: mvn --batch-mode verify
~~~

In this example:

- `distribution: temurin` selects Eclipse Temurin.
- `java-version: '21'` requests the Java 21 line.
- `cache-jdk: true` enables caching for the downloaded JDK.
- `cache: maven` is omitted, so Maven dependency caching is not enabled by `setup-java`.

### 3.2. Cache both the JDK and Maven dependencies

If the project uses Maven, you can enable dependency caching:

~~~yaml
steps:
  - uses: actions/checkout@v7

  - uses: actions/setup-java@v6
    with:
      distribution: temurin
      java-version: '21'
      cache: maven

  - run: mvn --batch-mode verify
~~~

In `setup-java@v6`, `cache: maven` enables both the Maven dependency cache and the JDK cache by default. The two caches remain separate entries. The Maven cache stores downloaded libraries, while the JDK cache stores the Java installation.

If you want to keep the Maven cache but not cache the JDK:

~~~yaml
- uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: '21'
    cache: maven
    cache-jdk: false
~~~

If you want to cache only the JDK without caching dependencies, omit `cache` and set `cache-jdk: true`.

### 3.3. Behavior matrix of cache-jdk

| cache | cache-jdk | Dependency/wrapper cache | JDK cache |
|---|---|---|---|
| Not set | Not set | Disabled | Disabled |
| Not set | true | Disabled | Enabled |
| Not set | false | Disabled | Disabled |
| maven / gradle / sbt | Not set | Enabled | Enabled |
| Set | true | Enabled | Enabled |
| Set | false | Enabled | Disabled |

`cache-jdk: false` only disables the JDK cache; it does not disable the dependency cache enabled by `cache: maven` or `cache: gradle`.

### 3.4. How is the JDK cache key partitioned?

`setup-java` builds the cache identity from multiple attributes to avoid using the wrong JDK:

- Runner operating system.
- Normalized architecture.
- Java distribution/vendor.
- Package type, such as JDK or JRE.
- Exact resolved Java version.
- Release identity, typically an authoritative checksum if provided by the vendor.
- Signature verification mode identity.

Therefore, JDK 21 Temurin Linux x64 differs from JDK 21 Temurin Windows x64, Zulu Linux x64, or another JDK package type. A build matrix running across multiple operating systems, architectures, vendors, or versions creates multiple separate cache entries and consumes more cache storage.

The dependency cache uses a different key. For Maven/Gradle, the action builds the key from the OS, architecture, package manager, and hashes of dependency descriptor files. For example, the default Maven key considers `pom.xml`, Maven wrapper properties, and extensions; the Gradle key considers build files, wrapper properties, `gradle.properties`, and relevant version catalogs.

### 3.5. Fixed version or latest version?

`java-version: '21'` selects the Java 21 line; the patch/build is resolved according to metadata and the runner's tool cache. When strictly reproducible builds are required, pin a specific version instead of relying solely on a major version or `latest`.

`check-latest: true` instructs the action to check the latest metadata matching the version spec before selecting an installation. `java-version: latest` is also a floating option. These are useful when you want to pick up new patches regularly, but they can cause the same commit to use different JDK patch versions at different points in time.

`force-download: true` forces a fresh download instead of using the runner tool cache or restoring from the JDK cache. Use this only when you need to re-verify an archive or when a custom archive's contents change without changing its version label; it is not an optimization option for regular builds.

### 3.6. Using read-only cache for untrusted jobs

For pull requests from forks or matrix jobs that only need to read the cache, you can enable:

~~~yaml
- uses: actions/setup-java@v6
  with:
    distribution: temurin
    java-version: '21'
    cache: maven
    cache-read-only: true
~~~

`cache-read-only: true` allows restoring the cache but does not save changes during the post-job step. This is useful for short-lived test jobs, pull requests, or multiple parallel jobs reading from a pre-seeded cache.

In a workflow with one cache-preparation job and multiple test jobs, the seed job can download the required dependencies, while the fan-out jobs use `cache-read-only` to prevent multiple jobs from trying to write to the same key concurrently. Cache misses must still be handled by the normal download/install step.

### 3.7. Verifying the actual JDK after setup

Do not rely solely on the input names in YAML. Check the JDK that the build step actually uses:

~~~sh
java -version
javac -version
java -XshowSettings:properties -version
~~~

Useful properties to inspect:

- `java.version`: currently running version.
- `java.vendor`: vendor.
- `os.arch`: architecture.
- `java.home`: selected JDK/JRE directory.

On Linux, you can check the executable paths:

~~~sh
command -v java
command -v javac
echo "$JAVA_HOME"
~~~

On Windows PowerShell:

~~~powershell
Get-Command java
Get-Command javac
$env:JAVA_HOME
~~~

If `java` runs the expected version but `javac` does not exist, the runner may be using a JRE instead of a JDK, or `PATH` may not point to the right installation.

## 4. GitLab CI/CD: how to cache the JDK?

GitLab CI cache consists of files or directories downloaded by a job and saved for subsequent jobs/pipelines. Paths in `cache:paths` must reside inside the project directory; caches and artifacts cannot point directly to a directory outside the workspace such as `/opt/jdk`.

Therefore, there are three common approaches in GitLab:

1. Pre-install the JDK on the runner and keep the runner/tool directory persistent.
2. Use a container image packaged with the exact JDK, pinned by version or digest.
3. If runners are ephemeral and need to download the archive repeatedly, cache the archive file inside the project directory, verify its checksum, and extract it into the job's workspace.

The second approach is usually the simplest when runners use the Docker executor: the image pre-defines the JDK and toolchain. GitLab cache continues to handle Maven/Gradle dependencies. There is no need to repackage the entire JDK into the cache every time if the image layers are already cached at the registry/runner.

### 4.1. GitLab example: using an image with JDK, caching Maven dependencies

Example of an internal image built with JDK 21:

~~~yaml
image: registry.example.com/ci/temurin-21:21.0.6_7-jdk

variables:
  MAVEN_OPTS: "-Dmaven.repo.local=$CI_PROJECT_DIR/.m2/repository"

cache:
  key:
    files:
      - pom.xml
      - .mvn/wrapper/maven-wrapper.properties
  paths:
    - .m2/repository/
  policy: pull-push

build:
  stage: build
  script:
    - java -version
    - javac -version
    - ./mvnw --batch-mode verify
~~~

The image contains the JDK; the cache only holds the Maven repository. The image tag in the example illustrates an image managed in an organization's registry. For production environments, pin the image by digest or an immutable tag and update it in a controlled manner.

### 4.2. GitLab example: caching the JDK archive inside the project directory

If you are not using an image with a pre-installed JDK and runners are frequently recreated, you can cache the JDK archive inside the workspace. The example below is for Linux x64 only; `JDK_URL` and `JDK_SHA256` must be declared as CI/CD variables from a trusted release source.

~~~yaml
variables:
  JDK_ARCHIVE: ".cache/jdk/temurin-21.0.6_7-linux-x64.tar.gz"

cache:
  key: "jdk-linux-amd64-temurin-21.0.6_7"
  paths:
    - .cache/jdk/temurin-21.0.6_7-linux-x64.tar.gz
  policy: pull-push

build:
  image: ubuntu:24.04
  stage: build
  script:
    - mkdir -p .cache/jdk
    - if [ ! -f "$JDK_ARCHIVE" ]; then curl --fail --location "$JDK_URL" --output "$JDK_ARCHIVE"; fi
    - echo "$JDK_SHA256  $JDK_ARCHIVE" | sha256sum --check -
    - mkdir -p .jdk
    - tar -xzf "$JDK_ARCHIVE" -C .jdk --strip-components=1
    - export JAVA_HOME="$CI_PROJECT_DIR/.jdk"
    - export PATH="$JAVA_HOME/bin:$PATH"
    - java -version
    - javac -version
    - ./mvnw --batch-mode verify
~~~

How it works:

1. The runner restores the archive if the cache key is available.
2. If the archive is not present, the job downloads the file from the configured URL.
3. `sha256sum --check` verifies the archive contents before extraction.
4. The JDK is extracted into `.jdk` inside the workspace.
5. `JAVA_HOME` and `PATH` are set for subsequent commands.
6. GitLab saves the archive under the cache key when the job completes.

This example caches the **archive**, not an installation directory outside the workspace. Each job still extracts the archive into `.jdk`. This avoids relying on an installation path outside the project directory and ensures the cache key clearly reflects the OS, architecture, vendor, and version.

If the checksum changes, update the cache key or version so the new archive does not reuse the old entry. Do not skip checksum verification just to avoid a cache miss.

### 4.3. Cache sharing limitations across runners

GitLab cache is not guaranteed to always be available. If the next job runs on a different runner, the previous runner's local cache may not exist on the new runner. To share caches across multiple runners, configure a distributed cache (e.g., object storage) or use runners that share the same cache storage and architecture.

By default, GitLab separates caches between protected and non-protected branches. This is a security boundary; do not disable this separation if untrusted users have permission to run pipelines on branches.

Cache keys can be file-based using `cache:key:files`. For dependency caches, use `pom.xml` or a lockfile so the key changes when dependencies change. For a JDK archive, the key should include the version and platform; if the archive is replaced with different contents, change the key or version.

## 5. Jenkins: reusing the JDK on agents

Jenkins manages the JDK as a build tool. Administrators declare JDKs under **Manage Jenkins → Tools** and assign a logical name, such as `temurin-21`. An agent can use a pre-installed JDK or auto-install an archive the first time a job requires the tool.

With auto-install, Jenkins places the tool under `<remote-fs-root>/tools/` on the agent. Subsequent builds on the same agent can reuse the existing installation as long as the archive has not changed. Specific JDK installers may require plugins; Jenkins core does not provide built-in downloaders for every distribution.

### 5.1. Declaring a JDK in a Declarative Pipeline

Once an administrator has configured the tool named `temurin-21`:

~~~groovy
pipeline {
    agent any

    tools {
        jdk 'temurin-21'
    }

    stages {
        stage('Verify JDK') {
            steps {
                sh 'java -version'
                sh 'javac -version'
            }
        }

        stage('Build') {
            steps {
                sh './mvnw --batch-mode verify'
            }
        }
    }
}
~~~

The Declarative `tools` directive sets `JAVA_HOME` and adds the `bin` directory to `PATH`. On Windows agents, use `bat` instead of `sh`.

If the agent is a persistent machine, the tool installation is reused across builds. If the agent is provisioned fresh and destroyed after each job, the tool cache directory disappears as well. In that case, use an image with the JDK pre-installed or a persistent tool volume rather than expecting a local cache to persist on its own.

### 5.2. Jenkins with ephemeral container agents

When Jenkins runs agents as ephemeral containers, you can build an agent image containing the required JDK and Maven/Gradle. Pin the image version/digest so jobs use the same toolchain. Registry and node image caches will reuse image layers; dependency caches are still managed separately.

Do not share a pre-installed JDK directory across agents with different operating systems or architectures. Each agent needs a tool home valid for its own environment.

## 6. Designing proper cache keys

The JDK is a platform-dependent binary. A cache key must be specific enough so that a job never restores an archive or installation from a different environment.

A good key should capture:

| Component | Why it is needed |
|---|---|
| OS | Linux, Windows, and macOS have different layouts and binaries |
| Architecture | x64 and aarch64 cannot share binaries |
| Distribution/vendor | Temurin, Zulu, Corretto, Oracle, and other vendors have different releases |
| Java version/build | Avoid accidentally using an older or newer patch/build than intended |
| Package type | JDK and JRE are not identical; builds needing `javac` require a JDK |
| Archive checksum/release identity | Detect when an archive's contents change even if the filename stays the same |
| Signature verification mode | Do not restore an installation from a cache with a weaker verification level than required |

Example of a meaningful key:

~~~text
jdk-linux-x64-temurin-jdk-21.0.6_7-sha256-<digest>
~~~

This is an illustrative pattern. With `setup-java`, these identity dimensions are managed automatically by the action. With a custom GitLab cache, include the appropriate dimensions in `cache:key` and update the key whenever the version or checksum changes.

Do not use a generic key like `jdk-cache` across all runners, vendors, and versions. An overly broad key can cause a job to restore a binary for the wrong platform or wrong toolchain.

## 7. Security and integrity of the JDK cache

The JDK is executable code run inside the pipeline. If the archive or cache is tampered with, a job could execute untrusted binaries. You must protect the download source, the verification step, and cache write permissions.

Recommended practices:

- Download the JDK from an approved vendor or internal repository.
- Verify the SHA-256 checksum against an independent, trusted source.
- Verify package signatures when supported by the vendor and tooling.
- Pin the version and architecture in the workflow.
- Allow only trusted branches/jobs to create or update shared caches.
- Use read-only caches for pull requests or consumer-only jobs.
- Never store tokens, credentials, private keys, or secret configuration files in the cache.
- Never disable integrity checks just to force a cache hit.
- Have a process to update and purge caches when a JDK is revoked or has a known vulnerability.

`setup-java` automatically verifies archive checksums when the distribution publishes authoritative checksums. The action also supports signature verification for certain distributions such as Temurin and Microsoft; if mandatory verification is required, configure the corresponding enforce mode and inspect the action logs.

One distinction to keep in mind: `setup-java` may find a JDK in the runner tool cache before downloading. A pre-existing installation in the tool cache is not re-downloaded and does not have an archive verification history stored alongside that cache. If your process requires re-downloading and re-verifying the archive, consider `force-download: true` while understanding the re-download cost.

Do not share caches between trusted and untrusted branches unless security policy explicitly allows it. A cache is an input source that can be restored into the workspace; cache write permissions should be restricted just like artifact write permissions.

## 8. Cache miss, invalidation, and cleanup

A cache miss is a normal event. The job must be able to proceed by downloading/installing the JDK from the configured source. Never make a build strictly depend on a cache entry already existing.

Common causes of cache misses:

- The job changes OS or architecture.
- The vendor or package type changes.
- A new JDK version/build produces a different key.
- The checksum or release identity changes.
- The cache has expired or been evicted.
- A different runner does not share the same cache storage.
- The cache path or cache key in the workflow changes.
- Cache restoration fails or the archive is invalid.

When invalidation is needed:

1. Identify the exact JDK version, vendor, OS, and architecture to replace.
2. Update the version or checksum in the configuration.
3. Generate a new cache key so jobs do not restore the old entry.
4. Run a seed job to download, verify, and save the new JDK.
5. Verify the version/vendor/architecture after setup.
6. Monitor old caches and delete them according to the platform's retention policy if needed.

Do not wipe the entire cache just because a single job experiences a cache miss. A cache miss may be the expected result of a new key. Only clear caches when an old entry is confirmed to be corrupted, contains invalid data, or consumes excessive storage.

In GitHub Actions, cache entries may be evicted if unused within the platform's retention period. In GitLab, administrators can apply lifecycle policies to object storage. Jenkins tool installations are managed according to agent lifecycle and the agent's `tools` directory.

## 9. Distinguishing JDK cache from dependency cache in practice

| Symptom | Layer to inspect |
|---|---|
| Job spends time downloading Temurin/Corretto/Oracle JDK | Runner tool cache or JDK installation cache |
| Maven downloads many artifacts from Maven Central | Maven local repository cache |
| Gradle downloads plugins/dependencies repeatedly | Gradle dependency/build cache |
| Re-installs JDK every time a new Jenkins agent is created | Jenkins tool installation or container image |
| GitLab job on a different runner cannot find the archive | Distributed cache/shared runner cache |
| Wrong Java version despite cache hit | `JAVA_HOME`, `PATH`, version resolution, and runner tool cache |
| `javac` does not exist | Using a JRE or wrong package type selected |
| Cache restore is fast but extraction is slow | Archive size, disk speed, and number of small files |
| Incorrect build after changing JDK | Cache key missing version/vendor/architecture or toolchain not pinned |

When a build behaves unexpectedly, check the actual JDK before clearing the cache. Run `java -version` and `javac -version` to identify the toolchain the job is using.

## 10. Java 17+ example to verify the toolchain in a pipeline

The following small program prints the running Java version, vendor, architecture, and directory. It helps detect when a workflow selects the wrong JDK after restoring a cache or modifying `PATH`.

Create `JdkProbe.java`:

~~~java
public class JdkProbe {
    public static void main(String[] args) {
        System.out.println("java.version=" + System.getProperty("java.version"));
        System.out.println("java.vendor=" + System.getProperty("java.vendor"));
        System.out.println("os.arch=" + System.getProperty("os.arch"));
        System.out.println("java.home=" + System.getProperty("java.home"));
    }
}
~~~

Compile with JDK 17 or later:

~~~sh
javac --release 17 JdkProbe.java
~~~

Run:

~~~sh
java JdkProbe
~~~

Example output on JDK 24.0.2 Azul x64:

~~~text
java.version=24.0.2
java.vendor=Azul Systems, Inc.
os.arch=amd64
java.home=C:\Users\Phuong PC\.jdks\azul-24.0.2
~~~

`java.home` depends on the machine/runner and will vary across environments. The version, vendor, and architecture lines are the values to cross-check against what the workflow declared.

In a pipeline, you can run this program right after the JDK setup step and capture stdout in the job log. If a cache hit occurs but the version/vendor is wrong, inspect `JAVA_HOME`, `PATH` ordering, the tool cache, and the cache identity before modifying build scripts.

## 11. Measuring effectiveness and troubleshooting

To determine whether caching actually speeds up the pipeline, record the duration of each step:

| Metric | Meaning |
|---|---|
| JDK setup duration | Time to set up the JDK on cold runs and warm runs |
| Cache restore duration | Time to download the cache from storage |
| JDK download duration | Time to download the archive from the vendor/repository |
| Extraction duration | Time to extract the JDK |
| Cache save duration | Time to package/upload after the job |
| Cache hit/miss rate | Frequency of entry reuse |
| Cache storage growth | Number of entries and accumulated storage size |

If cache restore and extraction take longer than downloading the JDK, caching may not provide a net benefit. On hosted runners that already have a matching Temurin build, the runner tool cache can be faster than restoring a JDK archive remotely.

| Symptom | Common cause | Resolution |
|---|---|---|
| JDK is always re-downloaded on GitHub Actions | `cache-jdk` not enabled, different cache key, or runner tool cache lacks the matching version | Check action version, cache settings, version/vendor/architecture, and setup logs |
| `cache: maven` is set, but JDK cache grows unexpectedly | `setup-java` enables JDK cache by default when dependency caching is enabled | Set `cache-jdk: false` if you only want to keep the dependency cache |
| JDK cache hit, but wrong Java version | Using a major/floating version, or `JAVA_HOME`/`PATH` points to another JDK | Pin the patch version when needed and run `java -version`/`javac -version` |
| GitLab cache missing in the next job | Job runs on a different runner without a shared/distributed cache | Use a distributed cache, shared runners, or a JDK image |
| GitLab reports an invalid cache path | Using a path outside the project directory | Cache the archive inside the workspace or install the JDK via image/runner tool |
| Cache archive restored, but fails to extract | Corrupted file, wrong archive format, or overly broad key | Verify SHA-256, change the key, and re-download from a trusted source |
| `javac` not found | Only a JRE was installed or `PATH` is misconfigured | Select the `jdk` package and check `JAVA_HOME` |
| Jenkins downloads the JDK on every build | Ephemeral agent or installer does not persist the installation | Use a persistent agent/tool volume or a container image |
| Build matrix uses the wrong cache | Key does not separate OS/architecture/version/vendor | Add these dimensions to the key or use `setup-java`'s automatic key |
| Cache hit, but build is not reproducible | JDK version, build tool, or dependencies use floating versions | Pin the JDK, Maven/Gradle wrapper, and dependency versions |

## 12. JDK caching implementation workflow

1. Identify the CI platform, runner type, and whether runners have persistent storage.
2. Choose the JDK vendor, package type, version/build, and architecture.
3. Check whether the runner tool cache or base image already has the required JDK.
4. Choose the mechanism: `setup-java` `cache-jdk`, GitLab archive/image, or Jenkins tool installation.
5. Design a key containing OS, architecture, vendor, version, and checksum/release identity.
6. Enable checksum/signature verification according to distribution support.
7. Configure cache write permissions for trusted jobs and read-only access for consumer-only jobs.
8. Verify with `java -version`, `javac -version`, and `JdkProbe`.
9. Run a cold run to populate the cache and a warm run to confirm a hit.
10. Compare setup duration, restore/save duration, and total pipeline duration.
11. Define invalidation, retention, and cleanup policies.
12. Ensure a cache miss can still install a valid JDK from a trusted source.

### Checklist

- [ ] Distinguished between runner tool cache, JDK cache, dependency cache, build cache, and artifacts.
- [ ] Selected the right JDK distribution, package type, and version.
- [ ] Partitioned the cache key by OS and architecture.
- [ ] Pinned the version or understood the behavior of version ranges/`latest`.
- [ ] Verified the JDK archive checksum/signature where supported.
- [ ] Controlled which jobs/branches have cache write permissions.
- [ ] Verified `JAVA_HOME`, `PATH`, and `javac`.
- [ ] Tested both cache hit and cache miss scenarios.
- [ ] Confirmed the pipeline still runs when the cache is evicted.
- [ ] Measured cold/warm runs including restore/save overhead.
- [ ] Established a process to rotate keys when the version or checksum changes.
- [ ] Set retention/cleanup policies for old caches.

JDK caching is effective when it lets runners reuse the right JDK without compromising build reproducibility or integrity. Check the runner tool cache first, choose the right mechanism for your platform, separate the JDK from the dependency cache, pin versions/architectures, and verify the binaries after setup. A cache miss must always have a safe fallback installation path.

## References

- [GitHub — actions/setup-java README and cache options](https://github.com/actions/setup-java)
- [GitHub — actions/setup-java advanced usage: Caching JDK installations](https://github.com/actions/setup-java/blob/main/docs/advanced-usage.md#caching-jdk-installations)
- [GitLab — Caching in GitLab CI/CD](https://docs.gitlab.com/ci/caching/)
- [GitLab — CI/CD YAML cache reference](https://docs.gitlab.com/ci/yaml/#cache)
- [Jenkins — Managing Tools and JDK installations](https://www.jenkins.io/doc/book/managing/tools/)
