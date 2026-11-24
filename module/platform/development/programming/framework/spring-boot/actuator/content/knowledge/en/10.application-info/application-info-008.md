# Tracing Running Versions Without Exposing Secrets or Personal Data

## 1. What Do You Need to Know When Asking "Which Build Is This Machine Running?"

Right after deploying a patch, operators need to confirm that the process serving requests has received the right release. A branch name like `main` or a "deployment succeeded" message is not a complete answer: the branch may have moved forward, one machine may not have been replaced yet, or the same commit may have been built multiple times with different inputs.

In Spring Boot Actuator's application info chapter, `/actuator/info` can provide a small set of metadata to link a running process to a release record. The goal is to answer:

1. Which service is this?
2. Which release version does the service report it is running?
3. Which commit does the source code correspond to?
4. Which build did the running package come from?

Data used for correlation must be chosen up front. You do not need to attach committer names, emails, commit messages, repository URLs, environment variables, or user information to answer those four questions.

### Related Identifiers That Do Not Replace Each Other

| Field | Meaning | Limitations when used for correlation |
| --- | --- | --- |
| Release version, e.g. `2.4.1` | Version name managed by the release process | Can be reused if the process allows overwrite builds |
| Full commit | Identifies a source snapshot in the repository | Does not capture all dependencies, build config, or uncommitted changes |
| Build identifier, e.g. `7318` | Lookup key for one packaging run in CI | Meaningful only within the agreed CI system |
| Package SHA-256 or container image digest | Verifies package/image contents stored in the release registry | Must come from a trusted record and identify the exact hashed object |
| Build timestamp | Aids ordering and investigation | Not startup or deployment time; does not guarantee uniqueness |

Abbreviated commits are easy to read yet can have prefix collisions. When exact lookup is needed, use the full commit in a controlled operational channel or look up by build identifier. Examples in this lesson use 40-character Git SHA-1 hashes; repositories using another format require a corresponding validation contract.

A useful reasoning chain is:

```text
Running process
  -> metadata packaged with the application
  -> service + version + revision + buildId
  -> release record in CI/artifact repository
  -> commit, locked dependencies, checksum/digest, and deployment history
```

This is a recommended traceability design. An HTTP response by itself does not prove package authenticity: an application could report wrong metadata. For stronger provenance verification, cross-check checksums, release signatures/attestations, and deployment state from trusted systems.

## 2. Where Does Actuator Get Information From?

`InfoEndpoint` aggregates information contributed by `InfoContributor` beans. A contributor can add an entry to the JSON object, such as `release`. Therefore, you must control both the set of participating contributors and the data each contributor emits. The aggregation mechanism is directly visible in [Spring Boot 3.3.13 InfoEndpoint source code](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/info/InfoEndpoint.java).

Common sources:

- `META-INF/build-info.properties`: package metadata generated at build time; Spring Boot can load it into `BuildProperties`.
- `git.properties` at the classpath root: pre-packaged Git metadata; it does not mean the application queries a live Git repository on every HTTP request.
- `info.*` in configuration: can be emitted by `EnvironmentInfoContributor` when that contributor is enabled.
- Custom `InfoContributor` beans written by the application: decide their own output content.

In Spring Boot 3.3, an endpoint being enabled and an endpoint being exposed over HTTP are two separate conditions. By default only `health` is exposed over HTTP; to read `info`, configure appropriate exposure. The `build` and `git` contributors can be auto-configured when matching metadata exists; `env` is not enabled by default. See [Spring Boot 3.3 endpoints documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.info).

### Three Leak Paths Easily Overlooked

**Build metadata with extra fields.** `BuildInfoContributor` in the 3.3 line uses `FULL` mode. If you add an extra field to build-info and let this contributor emit it automatically, that field can become part of the JSON. Never treat the build-info file as a place to store secrets. See [BuildInfoContributor 3.3.13](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/info/BuildInfoContributor.java).

**Git in full mode.** `simple` mode picks branch, short commit, and commit time if present; `full` uses all provided Git properties. Files generated by build tools may include extra identities, build machine details, or remote URLs. Even branch names can contain people's names, customer codes, or incident details. See [GitInfoContributor](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/info/GitInfoContributor.java) and [how FULL/SIMPLE is chosen](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/info/InfoPropertiesInfoContributor.java).

**`info.*` configuration.** When the environment contributor is enabled, properties under `info` can enter the response. Renaming `DB_PASSWORD` to `info.database.password` does not make the value safer; interpolating a secret into `info.*` still creates sensitive output. See [EnvironmentInfoContributor](https://github.com/spring-projects/spring-boot/blob/v3.3.13/spring-boot-project/spring-boot-actuator/src/main/java/org/springframework/boot/actuate/info/EnvironmentInfoContributor.java).

Do not generalize the value-masking mechanism of `/env` and `/configprops` to `/info`. Documentation describes value masking for the endpoints that have that mechanism; for data contributed into `info`, design from the start assuming values will be returned. There is no shared `show-values` property that automatically filters every contributor's JSON.

## 3. Designing the Data Contract Before Writing Code

This example selects a single object:

```json
{
  "release": {
    "service": "order-service",
    "version": "2.4.1",
    "revision": "8f0c2a17e4b9d6c83a12f0e5b7d93c4a6e1f205b",
    "buildId": "7318"
  }
}
```

All values above are illustrative data. The four fields are the example's allowlist, not a universally safe list for every organization. If source code is private or policy forbids exposing commits, you can expose only an opaque release ID and look up the mapping in an internal system.

| Chosen for output in the example | Kept in CI/release records |
| --- | --- |
| Agreed service identifier | Builder name, committer, email |
| Release version | Commit message, branch names containing personal data |
| Full commit approved for this channel | Remote URLs with credentials/tokens, build machine paths |
| Numeric build identifier | Environment variables, system properties, connection configs |
| No user data | Customer profiles, session IDs, business requests/responses |

Do not follow an "emit everything then delete keys named `password`" approach. Denylists easily miss new names like `credential` or nested structures. Selecting only needed fields keeps the contract stable when metadata sources gain new fields.

A random or numeric build ID can still be linked to identities in other systems. Audience restrictions and lookup scope must still fit the usage context.

## 4. Integration Example with Spring Boot 3.3.x, Java 21

The snippets below are for a Spring Boot 3.3.x application already equipped with Java 21, Gradle wrapper, the Spring Boot Gradle plugin, `spring-boot-starter-web`, and `spring-boot-starter-actuator`. The application already has a `@SpringBootApplication` class. This code integrates with Spring and its libraries; the contributor file is not a standalone program run via `java ReleaseInfoContributor`.

In the standalone practice exercise, name the Gradle project `order-service`. If integrating into another project, preserve that project's artifact convention and update expected values accordingly.

### 4.1. Packaging Metadata from the Build

Additional configuration in `build.gradle`, using Groovy DSL:

```groovy
version = '2.4.1'

springBoot {
    buildInfo {
        excludes = ['group', 'name', 'time']
        properties {
            additional = [
                'revision': providers.gradleProperty('sourceRevision').get(),
                'buildId': providers.gradleProperty('buildId').get()
            ]
        }
    }
}
```

`buildInfo` creates the `bootBuildInfo` task to generate `META-INF/build-info.properties`. The example excludes unused fields and takes two identifiers from required build parameters; if parameters are missing, Gradle does not substitute stale data. Generating, adding, and excluding fields are described in the [Gradle plugin 3.3 documentation](https://docs.spring.io/spring-boot/3.3/gradle-plugin/integrating-with-actuator.html).

Run at the practice application root in PowerShell:

```powershell
.\gradlew.bat clean bootJar -PsourceRevision=8f0c2a17e4b9d6c83a12f0e5b7d93c4a6e1f205b -PbuildId=7318
java -jar build/libs/order-service-2.4.1.jar
```

Here `order-service` is the default artifact name of the practice project. If you customized the JAR name, use the exact file produced by `bootJar`.

With the configuration and data above, the metadata content in terms of key/value pairs consists of:

```properties
build.artifact=order-service
build.version=2.4.1
build.revision=8f0c2a17e4b9d6c83a12f0e5b7d93c4a6e1f205b
build.buildId=7318
```

Line order and comments in the Gradle-generated file may differ. Once loaded into `BuildProperties`, access `artifact`, `version`, `revision`, and `buildId` without repeating the `build.` prefix.

In real CI, take the commit from the actual checkout that was built, control parameter sources, and reject source trees with uncommitted changes per release policy. Do not grab "latest commit on main" at deployment time and attach it to a previously built JAR. Once built, promote that same package across environments; CI records store the mapping from buildId to checksum/digest, build configuration, and locked inputs.

Do not write the checksum of the entire JAR into a file inside that JAR expecting it to be the JAR's final checksum: adding the field changes the package contents. Store the final checksum in external release records or use appropriate attestation mechanisms.

### 4.2. Allowing Only One Contributor to Emit the Defined Contract

File `src/main/java/com/example/info/ReleaseInfoContributor.java`; placed within the application's component scan scope:

```java
package com.example.info;

import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

import org.springframework.boot.actuate.info.Info;
import org.springframework.boot.actuate.info.InfoContributor;
import org.springframework.boot.info.BuildProperties;
import org.springframework.stereotype.Component;

@Component
public final class ReleaseInfoContributor implements InfoContributor {

    private final Map<String, Object> release;

    public ReleaseInfoContributor(BuildProperties build) {
        Map<String, Object> selected = new LinkedHashMap<>();
        selected.put("service", required(
                "artifact", build.getArtifact(), "[a-z][a-z0-9-]{0,62}"));
        selected.put("version", required(
                "version", build.getVersion(),
                "[0-9]+\\.[0-9]+\\.[0-9]+(?:-[A-Za-z0-9.-]+)?"));
        selected.put("revision", required(
                "revision", build.get("revision"), "[0-9a-f]{40}"));
        selected.put("buildId", required(
                "buildId", build.get("buildId"), "[0-9]{1,18}"));
        this.release = Collections.unmodifiableMap(selected);
    }

    private static String required(String field, String value, String pattern) {
        if (value == null || !value.matches(pattern)) {
            throw new IllegalStateException("Invalid release field: " + field);
        }
        return value;
    }

    @Override
    public void contribute(Info.Builder builder) {
        builder.withDetail("release", this.release);
    }
}
```

The four `selected.put` calls are the allowlist. The contributor does not iterate over all properties in `BuildProperties`, does not call `System.getenv()`, and does not read JVM properties or user objects. A new extra key in build-info does not automatically enter the `release` object.

The regular expressions represent this example's narrow contract: three-number version with optional suffix, lowercase Git SHA-1 commit, and numeric buildId up to 18 digits. If the project uses versions with `+...` metadata, Git SHA-256, or another build identifier format, intentionally update both the contract and checks. Matching a regex only validates syntax; CI must still ensure values come from the right source and are permitted for exposure.

Validation happens at bean creation time. Missing or malformed metadata causes application startup to fail under this sample contract instead of returning a guessed version. This is an intentional choice for release packages. If you need a development mode without metadata, design explicit configuration and checks; never silently fall back to an old version.

Error messages name only the field without interpolating the input value into the exception. `Collections.unmodifiableMap` keeps the field set fixed after initialization.

### 4.3. Controlling Contributors and HTTP Separately

`application.yml` for the local practice exercise:

```yaml
server:
  address: 127.0.0.1

management:
  endpoints:
    web:
      exposure:
        include: health,info
  info:
    defaults:
      enabled: false
    build:
      enabled: false
    git:
      enabled: false
    env:
      enabled: false
```

`management.info.defaults.enabled=false` disables auto-configured contributors enabled by default. The `build/git/env.enabled=false` lines make intent explicit for the three sources discussed. This configuration does not disable the `ReleaseInfoContributor` bean registered by the application; that bean still contributes the `release` section.

Disabling the build contributor does not delete metadata or disable loading the `BuildProperties` bean. The sample code still needs that bean to select the four fields. If the build-info file or corresponding bean is absent, the constructor cannot be satisfied and the application fails to start.

Also do not treat `defaults.enabled=false` as a blanket ban on all contributors: a source explicitly enabled in other config, or another custom bean, still needs to be inventoried. Add new contributors only after reviewing what data they emit and updating contract tests.

In the example, HTTP exposure includes only `health` and `info`. There is no need to add `env`, `configprops`, or `include: "*"` to trace versions.

### 4.4. Observing Results

If the practice application has no extra authentication layer and uses the default port and default path:

```powershell
curl.exe --fail --silent --show-error http://127.0.0.1:8080/actuator/info
```

The JSON body contains data matching the contract in section 3; key order and whitespace are not HTTP guarantees. JVM/Spring startup logs are a separate stream, not JSON content.

In PowerShell, you can inspect the keys of the parsed object:

```powershell
$info = Invoke-RestMethod 'http://127.0.0.1:8080/actuator/info'
$info.PSObject.Properties.Name | Sort-Object
$info.release.PSObject.Properties.Name | Sort-Object
```

With the sample configuration and no other contributors, the outputs of the two listing commands respectively are:

```text
release
buildId
revision
service
version
```

If the project uses Spring Security or a gateway, preserve existing authentication mechanisms and call with an appropriate operational account. `exposure.include` does not grant access permission. Do not disable protection layers just to make the illustrative command return `200`.

## 5. Testing Both Approved Data and Non-Exposed Data

One successful `curl` call does not prove the data contract is airtight. You must verify the exact key set and cases where the source contains extra properties.

The unit test example below uses JUnit Jupiter with Spring Boot Actuator on the test classpath; place it in the same `com.example.info` package under `src/test/java`:

```java
package com.example.info;

import java.util.Map;
import java.util.Properties;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.boot.actuate.info.Info;
import org.springframework.boot.info.BuildProperties;

import static org.junit.jupiter.api.Assertions.*;

class ReleaseInfoContributorTest {

    private static Properties metadata() {
        Properties properties = new Properties();
        properties.setProperty("artifact", "order-service");
        properties.setProperty("version", "2.4.1");
        properties.setProperty(
                "revision", "8f0c2a17e4b9d6c83a12f0e5b7d93c4a6e1f205b");
        properties.setProperty("buildId", "7318");
        return properties;
    }

    @Test
    void publishesOnlyApprovedFieldsEvenWhenSourceHasMore() {
        Properties properties = metadata();
        properties.setProperty("password", "FAKE_SECRET_FOR_TEST");
        properties.setProperty("commit.user.email", "person@example.invalid");

        ReleaseInfoContributor contributor =
                new ReleaseInfoContributor(new BuildProperties(properties));
        Info.Builder builder = new Info.Builder();
        contributor.contribute(builder);
        Map<String, Object> details = builder.build().getDetails();

        assertEquals(Set.of("release"), details.keySet());
        Map<?, ?> release = (Map<?, ?>) details.get("release");
        assertEquals(
                Set.of("service", "version", "revision", "buildId"),
                release.keySet());
        assertEquals("order-service", release.get("service"));
        assertEquals("2.4.1", release.get("version"));
        assertEquals(properties.getProperty("revision"), release.get("revision"));
        assertEquals("7318", release.get("buildId"));
    }

    @Test
    void refusesMissingRevisionWithoutEchoingItsValue() {
        Properties properties = metadata();
        properties.remove("revision");

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> new ReleaseInfoContributor(new BuildProperties(properties)));
        assertEquals("Invalid release field: revision", error.getMessage());
    }

    @Test
    void refusesSensitiveTextInRevision() {
        Properties properties = metadata();
        properties.setProperty("revision", "FAKE_SECRET_FOR_TEST");

        IllegalStateException error = assertThrows(
                IllegalStateException.class,
                () -> new ReleaseInfoContributor(new BuildProperties(properties)));
        assertEquals("Invalid release field: revision", error.getMessage());
    }
}
```

In the test, `Properties` passed to `BuildProperties` uses key names with the `build.` prefix already stripped. All secret-like or email-like values here are dummy data.

This test verifies the contributor's field-selection logic, yet does not prove the entire application registers only this contributor. After running `.\gradlew.bat test`, also verify HTTP on the built package with the real release configuration:

- The root key set is strictly `release`; the inner key set has strictly the four fields, not merely checking "no password".
- Values for version/revision/buildId match the release record; no data from a previous build remains.
- External configuration and deployment profiles do not re-enable broader contributors.
- Authorized operational roles can read it; unauthorized users cannot, per the chosen policy.
- Packaged files, logs, log aggregation systems, and CI history also contain no sensitive data outside each channel's contract.

The contributor only filters the response. If a secret was already written into build-info or `git.properties`, not seeing it over HTTP does not erase that secret from the JAR. Prevent secrets from entering build inputs and inspect artifacts before release.

## 6. Putting into Operations

### Placing Lookups on the Right Channel

For internal operational metadata, restrict management routes via private networks, gateways, or application authentication/authorization mechanisms. A separate management port can be used if the deployment architecture supports it. A separate port only splits the listening endpoint; bind address, firewalls, proxies, and access permissions decide who can reach it.

The sample config binds the application to loopback for local practice. That is not a deployment configuration to copy verbatim into every container: loopback inside a container belongs to the container's network namespace. When changing addresses/ports, test the actual external access path and use HTTPS over networks needing protection.

Do not pass tokens in query strings to read metadata. Avoid logging raw authorization headers or publishing returned data on public pages when the contract permits only internal access.

### Correlating the Right Process in Multi-Replica Deployments

Suppose version `2.4.1` corresponds to build `7318`. During a rolling update, some replicas may still be running `2.4.0`. Calling through a load balancer twice can return two different sets of identifiers; this may be a transient state to investigate rather than an `InfoContributor` bug.

Verification procedure:

1. Obtain the target release record from CI/release registry.
2. Call each replica over a controlled management channel or inspect through the deployment platform.
3. Compare service/version/revision/buildId against the deployed package's record.
4. If mismatched, inspect the actual image/JAR, rollout, override config, and HTTP caches.
5. Only conclude the full update is complete when every replica in scope reaches the expected state.

There is no need to add hostnames containing personal names or customer IDs to `/info` to do this. Replica identifiers can be looked up in the internal orchestration platform. If a proxy caches responses, configure appropriate caching policies and ensure reads reach the intended backend.

On rollback, identifiers must revert to the exact previously released package. Never edit only the version in configuration to make it look like a new patch is running. Distinguish "currently running package" from "current deployment configuration"; the same package can run with different configuration while its build metadata stays unchanged.

## 7. Common Errors and Remedies

| Observation | What to check |
| --- | --- |
| `404` at `/actuator/info` | Exposure, whether the endpoint is disabled, base path, context path, management port, and proxy routing; the HTTP code may come from a proxy |
| `401/403` | Authentication/authorization mechanism and proxy layer; do not fix by removing protection |
| Empty JSON `{}` | No contributor is contributing or the sample contributor was not scanned; check config/beans |
| Fails to start, missing `BuildProperties` | Did the metadata-generation task run, is the resource inside the running package; the IDE may not have run the Gradle task |
| `Invalid release field: revision` | Build parameter missing/violates contract; fix metadata source and rebuild |
| JSON emits extra `build`, `git`, or other keys | Another contributor or external configuration was enabled; inspect the full application |
| Commit matches yet behavior differs | Compare artifact/digest, dependencies, and config; a commit alone does not identify all inputs |
| Two calls return two versions | Check backends behind the load balancer, rollout, and caching before concluding |

Avoid hardcoding versions in Java and forgetting to update them on future releases. Avoid reading mutable deployment labels to impersonate package metadata. Generating metadata from the build itself and using the build ID as a record lookup key reduces both classes of drift.

## 8. Practice

1. Build the application with the sample identifiers; call `/actuator/info` and match all four fields against packaged metadata.
2. Add an unapproved dummy property to the build-info source; confirm `release` still has strictly four keys. After testing, remove the dummy data from build configuration.
3. Omit `sourceRevision` from the build command: the build must fail due to the missing required parameter. Base conclusions only on the new build, avoiding accidentally running an old JAR left in the directory.
4. Provide a malformed revision: if the build produces a package, that package must be rejected at startup by the contributor's contract.
5. Run two packages with different identifiers on two local ports, read each one, and explain why reading through a single load-balanced address is insufficient to confirm all replicas are updated.
6. For any newly proposed field, answer: what lookup does this field help with, does it contain personal data/secrets, who may view it, and can it remain solely in internal records?

The desired outcome is the ability to link a process to the exact release record using a small, testable metadata contract with a well-defined access scope.
