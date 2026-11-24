# Using the * Character in Configuration and Quoting Rules in YAML

## 1. One Character, Two Processing Layers

When you want to expose all eligible Actuator endpoints over HTTP, you can use the wildcard character `*`. However, that same character has special meaning in YAML syntax. The configuration must be parsed by YAML into valid data before Actuator has a chance to interpret it.

The common way to write this in `application.yml` is:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
```

Here, the quotes instruct YAML to produce a string value containing the single character `*`. Afterward, Actuator's endpoint exposure mechanism interprets that value as selecting all. The quotes do not turn `*` into an ordinary endpoint name, nor do they strip Actuator's select-all meaning.

Conversely, the following snippet is an example of **invalid syntax for this purpose**:

```yaml
management:
  endpoints:
    web:
      exposure:
        include: *
```

The application may fail immediately while parsing YAML. This is not yet a case of an endpoint lacking access permissions or not being selected for exposure.

Spring Boot instructs placing the asterisk inside quotes when using YAML for include/exclude lists. [Boot 3.3 Endpoint Exposure Documentation](https://docs.spring.io/spring-boot/3.3/reference/actuator/endpoints.html#actuator.endpoints.exposing).

## 2. Why Does YAML Need Quotes?

In YAML, `*` can start an alias reference to a node previously named with an anchor. This pair of symbols serves data referencing within a YAML document; they were not invented by Spring Boot.

Therefore, upon encountering `include: *`, the parser does not assume this is a string containing an asterisk. It starts processing alias syntax without receiving a valid name. With the SnakeYAML 2.2 parser used in Boot 3.3.0 experiments, this case is rejected with an error in the `ScannerException` family.

To request a plain string, use single quotes or double quotes:

```yaml
include: '*'
```

```yaml
include: "*"
```

These two short snippets are alternative ways to write the `include` value under the `management.endpoints.web.exposure` branch; they are not a complete configuration for an application.

Both produce the same data after parsing: the string `*`, with length one. The quotes are string-delimiters in syntax, not part of the value. [Indicators, Aliases, and String Styles in the YAML 1.2.2 Specification](https://yaml.org/spec/1.2.2/).

### 2.1. Do Not Add an Escape Character Before the Asterisk

Writing `"*"` directly is sufficient. There is no need to turn it into `"\*"`.

The snippet below is an **incorrect** example:

```yaml
include: "\*"
```

In testing with SnakeYAML 2.2, the parser rejects this notation because `\*` is not an accepted escape sequence in double-quoted strings. Adding a backslash is not the fix for an alias error.

Use straight ASCII quotes `'` or `"` when entering configuration. Curly/typographic quotes substituted by text editors are not valid YAML string delimiters.

### 2.2. Do Not Assume Every String with an Asterisk Is a Valid Wildcard

This snippet can be parsed by YAML into a string:

```yaml
include: "health*"
```

However, passing YAML parsing does not mean Actuator supports name patterns like `health*`. In Boot 3.3.0, that value is rejected when validating endpoint IDs. The special value used to select all is the whole string `*`, not an arbitrary prefix/suffix pattern-matching mechanism.

These are two different error layers:

| Example | Layer that detects the problem in experiments | Fix according to intent |
| --- | --- | --- |
| `include: *` | YAML parser | To select all, write `include: "*"` |
| `include: "\*"` | YAML parser | Remove the backslash, keep the quotes |
| `include: "health*"` | Actuator ID validation after YAML has parsed | Use a specific ID like `health` or use `"*"` alone |

## 3. Writing the Asterisk in YAML List Formats

Exposure properties accept lists of IDs. A single asterisk item can be represented as a string or as a single-element list.

### 3.1. Single String

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude: "env,configprops"
```

In this configuration, include selects all, while exclude removes `env` and `configprops`. A comma-separated string of IDs is converted by Spring Boot into the corresponding set of values.

### 3.2. Block Sequence (Line-by-Line List)

```yaml
management:
  endpoints:
    web:
      exposure:
        include:
          - "*"
        exclude:
          - env
          - configprops
```

Having the asterisk after `-` does not remove the quoting requirement. The element `- "*"` is a valid string; writing `- *` still makes the parser process an incomplete alias symbol.

### 3.3. Flow Sequence (Single-Line List)

```yaml
management:
  endpoints:
    web:
      exposure:
        include: ["*"]
        exclude: [env, configprops]
```

`["*"]` is a list containing one asterisk string. `[*]` is not a valid alternative syntax for this purpose. In testing with SnakeYAML 2.2, `include: [*]` is also rejected during YAML parsing.

The valid forms above share the same endpoint-selection intent. Use one consistent style in a file so readers can review it easily; do not copy multiple duplicate `management` blocks into the same document to combine examples.

## 4. How Is the * Value Interpreted by Actuator?

Only after YAML parses and Spring Boot binds the data into configuration does the asterisk participate in HTTP exposure rules.

```text
YAML file
  → parse syntax and produce data
  → bind data into include/exclude properties
  → Actuator selects or excludes endpoints
  → HTTP requests are still subject to path and access policy
```

### 4.1. include with Asterisk: Selects All Eligible Endpoints

`include: "*"` selects all within the endpoint exposure mechanism, but does not automatically create an endpoint missing required libraries or conditions. Nor does it re-enable an endpoint that has been disabled.

Example:

```yaml
management:
  endpoint:
    info:
      enabled: false
  endpoints:
    web:
      exposure:
        include: "*"
```

`info` remains disabled. Similarly, an application lacking the library that provides the Prometheus endpoint will not gain `/actuator/prometheus` merely from the asterisk.

### 4.2. exclude with Asterisk: Excludes All Endpoints from HTTP

```yaml
management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude: "*"
```

Exclude takes precedence, so this configuration exposes no Actuator endpoints over HTTP. You cannot use include to "override back" an asterisk in exclude.

You can also set only `exclude: "*"` to remove all endpoints from the HTTP channel. That does not mean stopping the web server or deleting business controllers.

### 4.3. Re-evaluating Scope After Using the Asterisk

Suppose today an application has a set of endpoints, and tomorrow a library or a custom management endpoint is added. If the configuration selects all, the newly eligible endpoint can be brought onto the HTTP interface without adding its ID to the config file.

Therefore, the asterisk is convenient for experiments or environments with a clearly defined management scope; whereas an explicit list helps reviews directly point out which capabilities are selected. Quotes only solve YAML syntax; they do not provide authentication, authorization, or network connection restrictions.

## 5. Distinguishing an Asterisk String from a YAML Alias

The following example uses an **intentional** alias:

```yaml
chosen: &ids "health,info"

management:
  endpoints:
    web:
      exposure:
        include: *ids
        exclude: env
```

Within the same document, `&ids` names the value `health,info`; `*ids` references that value again. The resulting include resolves to the two IDs `health` and `info`. It does not carry the select-all meaning.

If there is no anchor named `missing`, the line `include: *missing` is rejected by the parser because the reference is undefined. That is a YAML error, not a message that Actuator is missing an endpoint named `missing`.

The alias example helps recognize why the `*` character has syntactic meaning. For a simple select-all value, writing `include: "*"` directly is usually easier to read than creating an anchor.

## 6. Do Not Copy YAML Quoting Rules Verbatim to Properties or Command Line

### 6.1. application.properties File

The way to select all in properties is:

```properties
management.endpoints.web.exposure.include=*
management.endpoints.web.exposure.exclude=env,configprops
```

Properties files do not treat single/double quotes as YAML string-wrapping syntax. If you write:

```properties
management.endpoints.web.exposure.include="*"
```

then the quotes become part of the configuration value. In Boot 3.3.0 testing, this value containing quotes is rejected during endpoint ID validation.

| Where config is written | Appropriate example | Desired value after parsing |
| --- | --- | --- |
| YAML, double-quoted string | `include: "*"` | `*` |
| YAML, single-quoted string | `include: '*'` | `*` |
| Properties | `management.endpoints.web.exposure.include=*` | `*` |

Therefore, when converting configuration between the two formats, you must convert the representation syntax as well, not just rename the file extension.

### 6.2. Shell Quoting Is Another Layer

When running a command with an argument `--management.endpoints.web.exposure.include=*`, the shell processes command-line syntax before Java receives the argument. Quotes used to wrap command-line arguments follow shell rules, not YAML file quoting rules.

The final goal remains a property value containing exactly the `*` character, without unintended quotes or backslashes. Do not mechanically apply properties-file notation to a string wrapped further by a shell, JSON, or deployment tool.

## 7. Experimenting with a Small Spring Boot Application

The following project uses Java 21, Gradle 8.5, and Boot 3.3.0. The first build needs to download plugins and libraries. The application adds no Spring Security and listens only on loopback to observe HTTP exposure configuration on a personal machine.

### 7.1. Files to Create

```text
actuator-wildcard-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/lab/wildcard/WildcardApplication.java
    └── resources/application.yml
```

File `settings.gradle`:

```groovy
rootProject.name = 'actuator-wildcard-demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
}

tasks.named('bootJar') {
    archiveFileName = 'actuator-wildcard-demo.jar'
}
```

File `src/main/java/lab/wildcard/WildcardApplication.java`:

```java
package lab.wildcard;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WildcardApplication {
    public static void main(String[] args) {
        SpringApplication.run(WildcardApplication.class, args);
    }
}
```

File `src/main/resources/application.yml`:

```yaml
server:
  address: 127.0.0.1
  port: 8080

management:
  endpoints:
    web:
      exposure:
        include: "*"
        exclude:
          - env
          - configprops
```

For this experiment, create only one application config file as above to avoid other sources altering include/exclude. Spring Boot also supports external configuration sources outside files; when results differ from expectations, check higher-precedence sources. [Boot 3.3 External Configuration Mechanism](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).

### 7.2. Running the Valid Configuration

In the directory containing `build.gradle`:

```shell
gradle bootJar
java -jar build/libs/actuator-wildcard-demo.jar
```

Keep the Java window running, open another window, and call:

```shell
curl -i http://127.0.0.1:8080/actuator/health
curl -i http://127.0.0.1:8080/actuator/info
curl -i http://127.0.0.1:8080/actuator/metrics
curl -i http://127.0.0.1:8080/actuator/env
```

On Windows PowerShell, use `curl.exe` if `curl` is an alias.

| Request in sample app | Expected HTTP code | Reason |
| --- | --- | --- |
| GET `/actuator/health` | 200 | Selected by asterisk, not excluded |
| GET `/actuator/info` | 200 | Selected by asterisk, not excluded |
| GET `/actuator/metrics` | 200 | Selected by asterisk, not excluded |
| GET `/actuator/env` | 404 | Excluded by exclude |

Do not assume all metrics JSON or headers are identical across machines. The goal here is to verify endpoint selection.

### 7.3. Testing Case-by-Case Changes

Each test: stop the process with Ctrl+C, edit YAML, run `gradle bootJar` again, and restart the JAR. The file inside the JAR does not change automatically when the source file is edited.

| Change in sample configuration | Result to observe |
| --- | --- |
| Change `include: "*"` to `include: '*'` | Same asterisk value; HTTP results above do not change |
| Change to `include: ["*"]` | Single-element list still selects all |
| Change to `include: *` | Fails while parsing YAML; cannot test HTTP for this startup yet |
| Change to `include: "\*"` | Fails while parsing escape string |
| Keep include with asterisk, change exclude to `"*"` | Actuator endpoints above are no longer exposed over HTTP |
| Change include to `"health*"` | YAML parses, but Actuator rejects invalid ID in Boot 3.3.0 |

When intentionally testing an invalid configuration, stop the valid running instance first. If the old process is still serving port 8080, responses from it do not prove the new configuration started successfully.

## 8. Identifying the Right Error Layer

| Symptom | What to check first |
| --- | --- |
| Fails to start; message mentions scanning alias, undefined alias, or YAML escape | Quotes, characters after `*`, YAML structure of the exact file reported |
| YAML parsed, yet endpoint ID or exposure config error | Actual value: quotes kept in properties, `health*` pattern, or extra characters |
| Application runs, yet an endpoint returns 404 | Whether endpoint is eligible, disabled, or excluded; also check address and path |
| Application with security returns 401/403 | Authentication/authorization policy, rather than only changing quotes |
| Edited config, yet results stay the same | Running JAR, build step, active profile, and overriding config sources |

Only adjust quotes when the issue belongs to value representation. Adding quotes around an invalid ID cannot fix the ID contract; using an asterisk also does not resolve access-permission errors.

## 9. Self-check

**Question 1.** Why is `include: "*"` valid while `include: *` is unsuitable for selecting all?

**Answer:** Double quotes tell YAML to create a string containing an asterisk. An unquoted asterisk in that position starts alias syntax; the parser cannot produce the intended wildcard value.

**Question 2.** After parsing `include: '*'`, does Actuator receive one or three characters?

**Answer:** One character `*`. The two single quotes are YAML string-wrapping syntax, not part of the data.

**Question 3.** Does writing `include: [*]` avoid the error because a list was used?

**Answer:** No. The asterisk item still needs to be represented as a string, such as `["*"]`.

**Question 4.** What endpoints do `include: "*"` and `exclude: "*"` expose?

**Answer:** No Actuator endpoints over HTTP in the standard exposure mechanism, because exclude wins.

**Question 5.** Does `include: *ids` always mean select all?

**Answer:** No. That is alias syntax. The result depends on the value previously named with `&ids`; if the anchor is undefined, YAML cannot parse it.

**Question 6.** When converting `include: "*"` from YAML to properties, should the two quotes be kept?

**Answer:** No. In properties, use `management.endpoints.web.exposure.include=*` so the value contains only the asterisk.
