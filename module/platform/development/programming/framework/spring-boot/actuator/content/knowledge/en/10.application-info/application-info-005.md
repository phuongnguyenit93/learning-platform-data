# Reading Commit Information from git.properties and Choosing Exposure Modes

## 1. From Source Revision to Running Application Information

When two machines both run application version `1.0.0` yet only one has the new bug fix, the version name is not enough to identify the deployed source code. The commit ID helps correlate the running instance with changes in Git; commit time and branch add context during incident investigation.

In Spring Boot Actuator, `git.properties` is the resource containing Git information captured at application build time. The typical flow is:

```text
Git repository at build time
    -> build tool generates git.properties
    -> resource is packaged into the application
    -> Spring Boot creates GitProperties
    -> GitInfoContributor selects information to expose
    -> /actuator/info returns the git section
```

This is build-time information, not a live query to the Git repository on every HTTP request. A container carrying only the JAR can still expose the commit even without a `.git` directory. Conversely, having `.git` next to the process does not automatically produce the `git` section if the application cannot load the corresponding resource.

The goal of this lesson is to read packaged information accurately, distinguish available data from exposed data, and choose the right mode for endpoint consumers. Examples use Spring Boot 3.3.x and Java 17 or later; the illustrative APIs also work with Java 21.

## 2. Three Decisions That Must Be Separated

| Decision | Responsible component | Question to answer |
| --- | --- | --- |
| Collection | Build tool or CI pipeline | Which Git properties are included in the build? |
| Content selection | `GitInfoContributor` | Use `simple`, `full`, or disable the contributor? |
| Access control | Endpoint configuration and HTTP security layer | Who is allowed to call `/actuator/info`? |

`management.info.git.mode=full` does not generate `git.properties`, does not automatically expose the endpoint over HTTP, and does not grant access rights. Likewise, adding `info` to the exposed endpoints list does not guarantee the Git resource exists.

In Spring Boot 3.3 auto-configuration, the Git contributor requires an eligible `GitProperties`; if the application declares its own `GitInfoContributor`, auto-configuration backs off. In that case you must inspect the constructor and logic of the custom bean rather than assuming `management.info.git.mode` still controls it. [Spring Boot 3.3.0 contributor auto-configuration code](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator-autoconfigure/src/main/java/org/springframework/boot/actuate/autoconfigure/info/InfoContributorAutoConfiguration.java).

## 3. Where Is the File Loaded From, and How Do Key Names Change?

The default location is `classpath:git.properties`. In a typical Java project, a resource placed at `src/main/resources/git.properties` ends up at the classpath root. With a Spring Boot executable JAR, the corresponding location is `BOOT-INF/classes/git.properties`.

You can change the location with the following property, for example when a build pipeline uses a custom resource name:

```properties
spring.info.git.location=classpath:metadata/git.properties
```

When loading, auto-configuration takes only keys starting with `git.` and strips this prefix to build `GitProperties`. Therefore:

| In file | When read from `GitProperties` | Typical path in JSON |
| --- | --- | --- |
| `git.branch` | `getBranch()` or `get("branch")` | `git.branch` |
| `git.commit.id` | `getCommitId()` | Depends on mode, see section 5 |
| `git.commit.id.abbrev` | `getShortCommitId()` | `git.commit.id` in simple |
| `git.commit.time` | `getCommitTime()` | `git.commit.time` |
| `git.commit.user.email` | `get("commit.user.email")` | May appear in full |

Calling `gitProperties.get("git.branch")` uses the wrong key name after loading. Putting a line `git.commit.id=...` in `application.properties` also does not replace the `git.properties` resource: those are two different loading paths. [Prefix loading and stripping mechanism in Spring Boot](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/info/ProjectInfoAutoConfiguration.java).

If calling `new GitProperties(properties)` yourself in Java, the input `Properties` object must contain keys with `git.` already stripped. The constructor does not perform prefix selection on behalf of auto-configuration.

## 4. A Fixed Dataset for Observing the Mechanism

To prevent results from depending on the learner's current commit, use the following file as practice data:

```properties
git.branch=main
git.commit.id=0123456789abcdef0123456789abcdef01234567
git.commit.id.abbrev=0123456789
git.commit.time=2024-06-01T09:15:00+0000
git.commit.user.email=demo@example.invalid
git.remote.origin.url=https://example.invalid/team/demo.git
git.dirty=false
```

The commit ID and addresses in the example are dummy data for testing. Do not ship this static file in a real release: when source code changes, a manually copied file will continue reporting the old commit.

Meaning of the properties:

- `branch`: branch label collected by the build tool. The branch may change or carry an unfamiliar name in CI environments.
- `commit.id`: full commit ID of the recorded source revision.
- `commit.id.abbrev`: abbreviated form provided by the generator tool; the example intentionally uses 10 characters.
- `commit.time`: commit timestamp, not JVM startup time or deployment time.
- `commit.user.email`, `remote.origin.url`: details helpful for internal investigation that require consideration before exposure.
- `dirty`: information about uncommitted changes at collection time, if the build tool generates this field.

A matching commit ID does not prove the build contains no uncommitted changes. When release traceability is needed, you must combine the commit ID, repository state at build time, and evidence from the CI pipeline; the `info` section only reflects data the build brought along.

## 5. Simple, Full, and Disabling the Contributor

### 5.1. Simple: Selecting Only Core Properties

`simple` is the default mode of `GitInfoContributor`. It selects the branch, abbreviated commit ID, and commit timestamp if corresponding data is present; fields such as email, repository URL, or `dirty` are not selected merely because they exist in the file. [GitInfoContributor data selection mechanism](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/info/GitInfoContributor.java).

Explicit configuration:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: [health, info]
  info:
    git:
      enabled: true
      mode: simple
```

With the dataset in section 4 and Spring Boot's default JSON configuration, the Git section has the following content; key ordering is not a contract:

```json
{
  "git": {
    "branch": "main",
    "commit": {
      "id": "0123456789",
      "time": "2024-06-01T09:15:00Z"
    }
  }
}
```

`getShortCommitId()` prefers `commit.id.abbrev`. If this key is missing, it takes up to the first 7 characters of `commit.id`; if neither exists, there is no commit ID to expose. Hence do not assume `simple` always returns exactly 7 characters. `getCommitTime()` provides an `Instant` when the timestamp is parseable; code must handle missing or unparseable data rather than assuming a value is always present. [API and data handling in GitProperties](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot/src/main/java/org/springframework/boot/info/GitProperties.java).

### 5.2. Full: Exposing Loaded Data with Nested Structure

Change only the mode:

```properties
management.info.git.mode=full
```

With the same dataset, the Git section looks like:

```json
{
  "git": {
    "branch": "main",
    "commit": {
      "id": {
        "abbrev": "0123456789",
        "full": "0123456789abcdef0123456789abcdef01234567"
      },
      "time": "2024-06-01T09:15:00Z",
      "user": {
        "email": "demo@example.invalid"
      }
    },
    "remote": {
      "origin": {
        "url": "https://example.invalid/team/demo.git"
      }
    },
    "dirty": "false"
  }
}
```

Here `git.commit.id` is an object, whereas in `simple` it is a string. With this dataset, the full ID lives at `git.commit.id.full`. JSON consumers must know which contract is in use; switching to `full` can break programs reading `git.commit.id` as a string.

`full` feeds the loaded set of properties through structural transformation; it does not read additional Git history or fill in missing fields. `.properties` values such as `dirty=false` can still appear as the JSON string `"false"`, not boolean `false`. Furthermore, this is a structured representation, not a byte-for-byte copy of the file: dotted keys are grouped, and valid timestamps are processed as temporal types. [Mechanism converting properties to contributor data](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.0/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/info/InfoPropertiesInfoContributor.java).

### 5.3. Not Exposing Git via the Auto-Configured Contributor

```properties
management.info.git.enabled=false
```

This setting disables the auto-configured Git contributor. It does not delete the resource from the JAR and does not prevent other Java code from reading `GitProperties` or a custom contributor from re-exposing that data. The `info` endpoint can also continue returning other data groups.

The two supported modes are `simple` and `full`; do not use `mode=none` in place of `enabled=false`. Also do not confuse `management.info.git.enabled` with `management.endpoint.info.enabled`: the latter controls the entire endpoint. [Spring Boot 3.3 Application Information configuration](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.info).

## 6. HTTP Practice in a Spring Boot Application

Assume you already have a Spring Boot 3.3.x project using Java 17+ and Gradle Wrapper. Add two dependencies to the existing `dependencies` block:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-web'
implementation 'org.springframework.boot:spring-boot-starter-actuator'
```

The lines above are an additional configuration snippet, not an entire `build.gradle`; the project must already have Spring Boot dependency version management. If the application already includes the web starter, do not declare it again.

A minimal startup class at `src/main/java/example/gitinfo/GitInfoApplication.java`:

```java
package example.gitinfo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GitInfoApplication {
    public static void main(String[] args) {
        SpringApplication.run(GitInfoApplication.class, args);
    }
}
```

Place the file from section 4 at `src/main/resources/git.properties`, then use the `simple` configuration from section 5.1 in `application.yml`. Specifically for local hands-on practice, add:

```yaml
server:
  address: 127.0.0.1
  port: 8080
```

Run the application:

```bash
./gradlew bootRun
```

On Windows PowerShell, the corresponding command is `.\gradlew.bat bootRun`. In another terminal:

```bash
curl -i http://127.0.0.1:8080/actuator/info
```

With the minimal application having no Spring Security installed and no other contributors, expect HTTP 200 along with the `simple` JSON from section 5.1. On Windows you can use `curl.exe` to avoid alias differences. If the project has Spring Security, you must use the project's credentials and access rules; do not infer a broken endpoint solely from HTTP 401/403.

Stop the process, change the mode to `full`, restart, and call the same URL again. The result should match section 5.2. Editing the configuration file does not guarantee a running process swaps contributors automatically; in this lesson, restart after each mode change.

Then test `enabled=false`: with no other contributors, the exposed endpoint returns `{}` instead of switching to HTTP 404.

In Spring Boot 3.3, only `health` is exposed over HTTP by default. `include: [health, info]` is an endpoint exposure choice, while authentication and authorization are decided by the application's security layer. [Endpoint exposure and security rules](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

## 7. Running Java to Observe Data Before and After Selecting a Mode

The following example tests `GitProperties` and `GitInfoContributor` directly without starting a web server. Manually loading and stripping prefixes is solely to clarify the mechanism; in normal applications use the bean created by Spring Boot.

Create `src/main/java/example/gitinfo/GitModesDemo.java`:

```java
package example.gitinfo;

import java.io.InputStream;
import java.util.Map;
import java.util.Properties;

import org.springframework.boot.actuate.info.GitInfoContributor;
import org.springframework.boot.actuate.info.Info;
import org.springframework.boot.actuate.info.InfoPropertiesInfoContributor.Mode;
import org.springframework.boot.info.GitProperties;

public class GitModesDemo {
    public static void main(String[] args) throws Exception {
        Properties raw = new Properties();
        try (InputStream input = GitModesDemo.class.getClassLoader()
                .getResourceAsStream("git.properties")) {
            if (input == null) {
                throw new IllegalStateException("Missing classpath:git.properties");
            }
            raw.load(input);
        }

        Properties entries = new Properties();
        for (String key : raw.stringPropertyNames()) {
            if (key.startsWith("git.")) {
                entries.setProperty(key.substring(4), raw.getProperty(key));
            }
        }
        GitProperties properties = new GitProperties(entries);
        Map<String, Object> simple = content(properties, Mode.SIMPLE);
        Map<String, Object> full = content(properties, Mode.FULL);
        Map<String, Object> simpleCommit = map(simple.get("commit"));
        Map<String, Object> fullCommit = map(full.get("commit"));

        System.out.println("branch=" + properties.getBranch());
        System.out.println("commit.full=" + properties.getCommitId());
        System.out.println("commit.short=" + properties.getShortCommitId());
        System.out.println("commit.time=" + properties.getCommitTime());
        System.out.println("simple.id=" + simpleCommit.get("id"));
        System.out.println("simple.hasUser=" + simpleCommit.containsKey("user"));
        System.out.println("full.id=" + map(fullCommit.get("id")).get("full"));
        System.out.println("full.email=" + map(fullCommit.get("user")).get("email"));
        System.out.println("full.dirtyType=" + full.get("dirty").getClass().getSimpleName());

        Properties fallbackEntries = new Properties();
        fallbackEntries.setProperty("commit.id", properties.getCommitId());
        GitProperties withoutAbbreviation = new GitProperties(fallbackEntries);
        System.out.println("fallback.short=" + withoutAbbreviation.getShortCommitId());
    }

    private static Map<String, Object> content(GitProperties properties, Mode mode) {
        Info.Builder builder = new Info.Builder();
        new GitInfoContributor(properties, mode).contribute(builder);
        return map(builder.build().get("git"));
    }

    @SuppressWarnings("unchecked")
    private static Map<String, Object> map(Object value) {
        return (Map<String, Object>) value;
    }
}
```

Add the following task to the practice project's `build.gradle`:

```groovy
tasks.register('runGitModesDemo', JavaExec) {
    dependsOn tasks.named('classes')
    classpath = sourceSets.main.runtimeClasspath
    mainClass = 'example.gitinfo.GitModesDemo'
}
```

Run `./gradlew --quiet runGitModesDemo` or `.\gradlew.bat --quiet runGitModesDemo`. With the exact file from section 4, the program's stdout is:

```text
branch=main
commit.full=0123456789abcdef0123456789abcdef01234567
commit.short=0123456789
commit.time=2024-06-01T09:15:00Z
simple.id=0123456789
simple.hasUser=false
full.id=0123456789abcdef0123456789abcdef01234567
full.email=demo@example.invalid
full.dirtyType=String
fallback.short=0123456
```

Read the output in two layers: Java can still read the email from the raw data, yet `simple` does not include the `commit.user` branch in exposed content. Switching to `full` changes the data selection, not by adding extra data from Git.

In a real application, you can receive `GitProperties` through a bean's constructor instead of loading the file yourself. If the resource may be absent in development environments, use `ObjectProvider<GitProperties>` or appropriate bean conditions; required injection when the bean is missing can prevent the application from starting. There is no need to write a separate REST controller just to read Git when `info` already meets the requirement.

## 8. Generating Real Data Instead of the Practice File

Once you understand the mechanism, remove the dummy data file and let the build tool generate information from the Git repository. Spring Boot recommends using a dedicated Git plugin; `springBoot { buildInfo() }` generates build metadata and does not replace generating Git metadata. [Spring Boot 3.3 guide to generating Git information](https://docs.spring.io/spring-boot/3.3/how-to/build.html#howto.build.generate-git-info).

Example configuration for a standalone Gradle project, using plugin version `2.4.1` illustrated in Spring Boot 3.3 documentation. This is a snippet to merge into existing configuration, not a requirement to change a plugin version already managed by the project:

```groovy
// Merge the id line into the existing plugins block.
plugins {
    id 'com.gorylenko.gradle-git-properties' version '2.4.1'
}

gitProperties {
    keys = ['git.branch', 'git.commit.id', 'git.commit.time']
    dateFormat = "yyyy-MM-dd'T'HH:mm:ssZ"
    dateFormatTimeZone = 'UTC'
}
```

The `keys` list limits what data goes into the resource. This example keeps email and repository URL out of the JAR. If you need `simple` mode to return a plugin-defined short ID, add `git.commit.id.abbrev` to the list; when absent, Spring Boot uses the fallback branch tested in section 7. Key-selection and timestamp-format options belong to the generator plugin, not `management.info.git.mode`. [gradle-git-properties plugin documentation](https://github.com/n0mer/gradle-git-properties#configuration).

Build and verify the final resource inside the JAR, not only by looking at files in the source directory:

```bash
./gradlew clean bootJar
```

For example, if the artifact is `build/libs/demo-1.0.0.jar`:

```bash
jar tf build/libs/demo-1.0.0.jar
```

The listing must include `BOOT-INF/classes/git.properties`. The JAR name in the command must match the actual artifact. You can open the JAR with a ZIP tool to inspect the resource, match the commit ID against the commit CI intended to build, and run that exact JAR.

Do not keep both a dummy file in `src/main/resources` and an auto-generated file at the same output location. There must be one clear source of data generation; if multiple copies with the same name exist on the classpath, resolve the duplication before trusting results.

In CI, watch out for empty repositories, shallow checkouts missing history, detached HEAD, and steps reusing old artifacts. These conditions can affect the properties the tool generates. Do not set fake branch names to mask traceability issues; match the artifact's commit ID against build inputs.

## 9. Choosing Exposure Level by Need

| Need | Suitable configuration to consider | What still must be checked |
| --- | --- | --- |
| Quick identification of running build | `simple` with minimal data | Are the branch name and short ID permitted for exposure? |
| Detailed investigation within management network | `full` with an approved key set | Are emails, repo URLs, commit messages, or build hostnames inside the data? |
| Do not provide Git info through info | `management.info.git.enabled=false` | Is any custom contributor re-exposing it? |
| Operators-only visibility | Content selection and endpoint protection | Are HTTP access rules actually enforced on info? |

Choosing `simple` does not remove data from the resource inside the JAR; anyone who receives the JAR can still read the file. When information must never leave the build system, strip it at the data-generation step. When only restricting HTTP callers, apply authentication, authorization, and access path limits.

`full` is also not a mechanism that automatically masks sensitive values. Do not assume a custom property named like a password will be masked as on certain other endpoints. Reliable control means never putting secrets into Git metadata and verifying the actual returned fields.

If you need to expose the full commit ID without other details, you can generate a very narrow set of keys and evaluate the `full` JSON of that set. If you need a separate stable JSON contract, design a custom contributor with an allowlist of fields; that is an extension requiring independent testing, not a built-in feature of `simple`.

## 10. Layer-by-Layer Troubleshooting

| Symptom | Check first | How to resolve |
| --- | --- | --- |
| `/actuator/info` returns 404 | Is the endpoint enabled and exposed over HTTP; did base path/port change? | Fix the request target or endpoint config before touching the Git file |
| HTTP 401 or 403 | Authentication mechanism and access permissions | Call with appropriate credentials and inspect protection rules |
| HTTP 200 without `git` | Final resource, `GitProperties`, contributor state | Check the exact running JAR, resource location, and `enabled` |
| `git` present yet missing email | Is `simple` active; does the file have email? | This may be the intended outcome of data selection |
| `full` set yet no extra fields | Generated property set and actual contributor bean | `full` does not invent new data; check custom config |
| Commit ID stays unchanged after new build | Dummy file, generator task, stale artifact or image | Compare the resource inside the exact newly deployed artifact |
| Timestamp remains an odd string or Java reads null | Input value and timestamp format | Use a supported offset format and check raw data |
| JSON consumer fails after enabling full | Type of `git.commit.id` | Update consumer contract and test missing-data cases too |
| Java reads `branch` as null | Key name passed to `GitProperties.get(...)` | Use `branch`, not `git.branch` |

If you disabled default contributors via `management.info.defaults.enabled=false`, verify the individual `management.info.git.enabled=true` setting before concluding the resource is broken. Diagnosis must rely on the effective runtime configuration, since profiles or command-line arguments can override config files.

## 11. Self-Check with Small Predictable Changes

1. Using the file in section 4, run both HTTP and the Java program. Explain why `simple.id` is 10 characters long.
2. Delete only the `git.commit.id.abbrev` line, rebuild or reload, and run the Java program. Predict that the short ID becomes `0123456`; the full ID stays unchanged.
3. Restore the file, remove email and repository URL. Enable `full` and verify those fields no longer appear. Switching modes cannot recreate removed data.
4. Disable the Git contributor, restart the application, and call info. Distinguish a missing `git` section from a non-existent endpoint.
5. Switch from the static file to auto-generated data. Pick a known commit, build the JAR, and prove the ID in the resource, JSON, and CI input all point to that commit.

Tests 1–3 use dummy data so values can be predicted accurately. Test 5 uses a real repository so specific results depend on the commit being built; do not copy the lesson's dummy values into operational reports.

## 12. Key Points to Remember When Applying

To trust commit information from a running instance, verify from the resource-generation source to the deployed artifact, and only then to endpoint output. `GitProperties` is the loaded data; `GitInfoContributor` decides what goes out; HTTP configuration decides the access path.

A sound exposure choice must simultaneously match the data, match the JSON structure consumers expect, and match the intended audience. Increasing fields with `full` only makes sense after confirming those fields are genuinely needed and present in the build.
