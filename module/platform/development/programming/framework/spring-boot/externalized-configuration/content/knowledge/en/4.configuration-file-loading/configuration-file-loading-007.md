# Location Groups: Commas, Semicolons, and Their Impact on Overrides

## 1. The Problem: Multiple Configuration Locations Do Not Always Take Precedence the Same Way

Spring Boot allows placing configuration files in multiple locations. For instance, an application might have shared configuration in `classpath:/cfg/` and supplementary configuration in `classpath:/ext/`. Both directories can contain `application.properties` and profile-specific variants such as `application-prod.properties` and `application-live.properties`.

When a property is declared in multiple locations, the application must choose a single effective value. How it chooses depends on **the order in which locations are loaded**, **active profiles**, and **how locations are grouped**.

Two strings that look almost identical have different meanings:

```properties
# Two separate location groups
spring.config.location=classpath:/cfg/,classpath:/ext/

# One group containing two locations at the same level
spring.config.location=classpath:/cfg/;classpath:/ext/
```

- The comma `,` **separates location groups**. In the first example, `cfg` is the earlier group and `ext` is the later group. Spring Boot processes the files in `cfg` and then those in `ext`; files in the later group can override the earlier group.
- The semicolon `;` **combines locations into the same group**. In the second example, `cfg` and `ext` are treated at the same tier when processing profile-specific variants. Profile order can determine which file overrides which across the two locations.

This is the **location groups** mechanism of Config Data in Spring Boot, which applies when using `spring.config.location` or `spring.config.additional-location`. A semicolon is not merely an alternative way of writing a comma.

A group containing multiple locations still has an internal order: if two locations within the same group provide the same key at the same level/profile, the location evaluated later can override the earlier one. "Same level" is especially significant when **multiple profiles are active**; it does not mean all values in the group are equal and Spring picks randomly.

## 2. Three Concepts to Keep Separate

### Load location

A location can be a directory, such as `classpath:/cfg/` or `file:./config/`, or a specific file such as `file:./ops/application.properties`.

- `classpath:` refers to resources on the classpath; in an executable JAR example, resources under `src/main/resources` are packaged into the JAR.
- `file:` refers to resources from the filesystem. A `./` path is resolved relative to the application's working directory at runtime.
- When declaring a **directory** via `spring.config.location`, put a trailing `/` at the end of the path; Spring Boot uses `spring.config.name` (defaulting to `application`) to search for matching file names.
- For a **specific file** location, Spring Boot loads the file at the given address and also considers profile-specific variants where appropriate.

### Profile

A profile such as `prod` or `live` enables Spring Boot to also load `application-prod.properties` or `application-live.properties`. When activating multiple profiles in the order `prod,live`, the rule "a profile evaluated later can override an earlier profile" participates in determining values.

This does not mean every `application-live.properties` beats every `application-prod.properties` across all layouts. **Location group boundaries** can allow an entire group processed later to override a group processed earlier.

### Property overriding

The same key, such as `lab.marker`, may appear in multiple files. Once sources are loaded and ordered, Spring `Environment` looks up the effective value in precedence order; Java code receives that value via `Environment`, `@Value`, or `@ConfigurationProperties`.

We will keep **every file** and **every profile** identical across our two main runs, changing only `,` to `;`. If the result differs, the cause is **how locations are grouped**, not modified file contents.

## 3. Building a Minimal Observation Application

Use a Spring Boot project with Java 17 or higher (for example, Spring Boot 3.x) that can build an executable JAR with Maven or Gradle. Data layout for the experiment:

```text
src/main/
├── java/com/example/locationlab/
│   └── LocationLabApplication.java
└── resources/
    ├── cfg/
    │   ├── application.properties
    │   ├── application-prod.properties
    │   └── application-live.properties
    └── ext/
        ├── application.properties
        ├── application-prod.properties
        └── application-live.properties
```

There is no need to create `src/main/resources/application.properties` at the classpath root: we will use `spring.config.location` to specify the two directories to read explicitly. This also avoids confusion with default locations.

Create `LocationLabApplication.java`:

```java
package com.example.locationlab;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class LocationLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(LocationLabApplication.class, args);
    }

    @Bean
    ApplicationRunner showEffectiveConfig(Environment environment) {
        return args -> {
            String marker = environment.getProperty("lab.marker");
            String note = environment.getProperty("lab.note");

            System.out.println("=== LOCATION GROUP LAB ===");
            System.out.println("lab.marker = " + marker);
            System.out.println("lab.note   = " + note);
            System.out.println("==========================");
        };
    }
}
```

`ApplicationRunner` reads only two test keys once the application finishes starting. `lab.marker` is the key used to demonstrate precedence; `lab.note` is used to confirm that `application-live.properties` in the `ext` directory was actually loaded.

There is no need to read each file manually in Java. The `Environment` object already aggregates the sources prepared by Spring Boot. If external configuration outside the experiment declares `lab.marker` via an environment variable, JVM system property, or command-line argument, that source can override the result. Run in an environment free of `LAB_MARKER`, `-Dlab.marker`, or `--lab.marker` other than the arguments stated.

## 4. Creating an Intentional Dataset

Each file contains the following values. We intentionally leave `lab.marker` **undeclared** in `ext/application-live.properties`; if both `-live` files defined the key and `ext` came second, both runs could produce the same result and hide the difference between commas and semicolons.

### The `cfg` resource group

`src/main/resources/cfg/application.properties`:

```properties
lab.marker=cfg-base
```

`src/main/resources/cfg/application-prod.properties`:

```properties
lab.marker=cfg-prod
```

`src/main/resources/cfg/application-live.properties`:

```properties
lab.marker=cfg-live
```

### The `ext` resource group

`src/main/resources/ext/application.properties`:

```properties
lab.marker=ext-base
```

`src/main/resources/ext/application-prod.properties`:

```properties
lab.marker=ext-prod
```

`src/main/resources/ext/application-live.properties`:

```properties
lab.note=ext-live-loaded
```

All six files are present in the JAR. Only **five** files declare `lab.marker`; the last file has only `lab.note`. That is by design for the experiment.

Summary table:

| Directory | File | `lab.marker` | Extra Key |
| --- | --- | --- | --- |
| `cfg` | `application.properties` | `cfg-base` | — |
| `cfg` | `application-prod.properties` | `cfg-prod` | — |
| `cfg` | `application-live.properties` | `cfg-live` | — |
| `ext` | `application.properties` | `ext-base` | — |
| `ext` | `application-prod.properties` | `ext-prod` | — |
| `ext` | `application-live.properties` | Not present | `lab.note=ext-live-loaded` |

After creating the files, package once—for instance, run `./gradlew bootJar` in an environment with a Gradle Wrapper or `mvn package` in a suitable Maven environment. The illustrative name for the packaged JAR in the following commands is `app.jar`; replace it with your project's actual JAR path.

For the two main runs, always keep the exact same profiles:

```text
spring.profiles.active = prod,live
```

The `prod` profile comes first, and `live` comes second. We will not change this order when comparing separators.

## 5. Experiment A: A Comma Creates Two Independent Groups

Run the application with a comma in `spring.config.location`:

```bash
java -jar app.jar \
  '--spring.config.location=classpath:/cfg/,classpath:/ext/' \
  '--spring.profiles.active=prod,live'
```

On Windows PowerShell, you can use a single line:

```powershell
java -jar app.jar '--spring.config.location=classpath:/cfg/,classpath:/ext/' '--spring.profiles.active=prod,live'
```

Expected output:

```text
=== LOCATION GROUP LAB ===
lab.marker = ext-prod
lab.note   = ext-live-loaded
==========================
```

Why does `ext-prod` beat `cfg-live`, even though profile `live` comes after `prod`?

Because the comma creates two consecutive location groups:

```text
Group 1: classpath:/cfg/
    cfg/application.properties
    cfg/application-prod.properties
    cfg/application-live.properties
               |
               v
Group 2: classpath:/ext/
    ext/application.properties
    ext/application-prod.properties
    ext/application-live.properties
```

Within the `cfg` group, `cfg-live` overrides `cfg-prod` and `cfg-base`. Moving to the **`ext` group processed later**, `ext-base` and then `ext-prod` supply `lab.marker` again and can override values from the earlier group. The file `ext/application-live.properties` does not define `lab.marker`, so it leaves the selected value `ext-prod` unchanged.

Looking at the files that declare `lab.marker`, we can picture the order from first to last:

```text
cfg/base  -> cfg-prod -> cfg-live -> ext-base -> ext-prod
  |            |           |            |           |
cfg-base     cfg-prod    cfg-live     ext-base     ext-prod
                                                       ^
                                              final winning value
```

`ext/application-live.properties` is still loaded: the proof is that `lab.note` receives `ext-live-loaded`. The **absence of `lab.marker`** in this file does not erase the key's value provided by `ext/application-prod.properties`.

Conclusion for the comma-separated syntax: **the rule "later location/group overrides earlier group" can outweigh profile precedence across two groups**. Therefore, across two directories in separate groups, you cannot judge the outcome solely by looking at `-live` and `-prod` suffixes.

## 6. Experiment B: A Semicolon Places Two Locations at the Same Level

Without editing any file, change only the comma between the two locations to a semicolon and keep `prod,live`:

```bash
java -jar app.jar \
  '--spring.config.location=classpath:/cfg/;classpath:/ext/' \
  '--spring.profiles.active=prod,live'
```

In Windows PowerShell:

```powershell
java -jar app.jar '--spring.config.location=classpath:/cfg/;classpath:/ext/' '--spring.profiles.active=prod,live'
```

Expected output:

```text
=== LOCATION GROUP LAB ===
lab.marker = cfg-live
lab.note   = ext-live-loaded
==========================
```

This time both directories are in **one location group**:

```text
                   SAME GROUP
       +-------------------------------+
       | classpath:/cfg/               |
       | classpath:/ext/               |
       +-------------------------------+
               |
               v
           Base files
               |
               v
          -prod files
               |
               v
          -live files
```

This is a conceptual way to describe the order: profile variants are evaluated across locations **within the same group**, instead of finishing all profiles of `cfg` before moving on to all profiles of `ext`.

With `prod,live`, we trace `lab.marker`:

1. Base files contribute `cfg-base` and `ext-base`; at the same tier, `ext` appears later and can override `cfg`.
2. For profile `prod`, `cfg/application-prod.properties` contributes `cfg-prod`, then `ext/application-prod.properties` contributes `ext-prod`.
3. For profile `live`, `cfg/application-live.properties` contributes `cfg-live`. Because `live` is evaluated after `prod` within the same group, `cfg-live` can override `ext-prod`.
4. `ext/application-live.properties` is also loaded, but it provides only `lab.note` and has no `lab.marker` to override `cfg-live`.

The result is `cfg-live`. Across runs A and B, `cfg/application-live.properties` still contains the exact same value; **bringing the two directories into the same profile-precedence tier** changed the result from `ext-prod` to `cfg-live`.

### Head-to-Head Comparison

| Factor | Comma `,` | Semicolon `;` |
| --- | --- | --- |
| Configuration | `classpath:/cfg/,classpath:/ext/` | `classpath:/cfg/;classpath:/ext/` |
| Location groups | Two groups: `cfg` then `ext` | One group: `cfg` and `ext` |
| Profiles | `prod,live` | `prod,live` |
| Created files | Identical | Identical |
| `lab.note` | `ext-live-loaded` | `ext-live-loaded` |
| **`lab.marker`** | **`ext-prod`** | **`cfg-live`** |
| Reason | Group `ext` is processed after group `cfg` | `-live` files are evaluated after `-prod` within the same group |

This is the central takeaway of the lesson: **the location separator can change override outcomes when multiple profiles are active**, even when the location list and file contents do not change.

## 7. Why Can't We Just Say "The Later File Always Wins"?

The statement "the later file wins" is true once you have determined the **actual evaluation order** of sources sharing a key. However, that order is not necessarily the order in which directory names are typed on the command line.

With a comma:

```text
group 1: cfg  [base, prod, live]
group 2: ext  [base, prod, live]
```

Variants in group `cfg` are evaluated before moving to `ext`. Therefore, `ext-prod` can override `cfg-live`.

With a semicolon:

```text
group 1: [cfg, ext]
         [base] -> [prod] -> [live]
```

Both locations share the same profile precedence tier; `cfg-live` is evaluated after `ext-prod` within the same group.

If `ext/application-live.properties` also contained `lab.marker=ext-live`, both approaches might yield `ext-live`: the file for the final profile at the later `ext` location contains that key. In such a case, you **cannot conclude that commas and semicolons are equivalent** from a single identical observation. You must construct the dataset so the two strategies can produce different results, as in the experiment above.

Similarly, if only one profile is active and all colliding files sit in a single location, the effect of grouping can be hard to see. The practical importance of location groups becomes clearest when combining **multiple locations, multiple profiles, and sparsely populated keys**.

## 8. Experiment C: Reversing the Profile Order

Keep the semicolon configuration, but reverse the profile order from `prod,live` to `live,prod`:

```bash
java -jar app.jar \
  '--spring.config.location=classpath:/cfg/;classpath:/ext/' \
  '--spring.profiles.active=live,prod'
```

Expected output:

```text
lab.marker = ext-prod
lab.note   = ext-live-loaded
```

Because within the same location group, profile `prod` is now evaluated after `live`, `ext/application-prod.properties` can override `cfg/application-live.properties` for `lab.marker`.

Comparison:

| Location Group | Profile Order | `lab.marker` Result |
| --- | --- | --- |
| `cfg;ext` | `prod,live` | `cfg-live` |
| `cfg;ext` | `live,prod` | `ext-prod` |
| `cfg,ext` | `prod,live` | `ext-prod` |
| `cfg,ext` | `live,prod` | `ext-prod` |

The two comma-separated rows have the same result in this dataset because group `ext` is processed after group `cfg`, and within `ext` only the `-prod` file contains `lab.marker`. The two semicolon-separated rows differ because the trailing profile changed.

Do not confuse the comma in `spring.profiles.active=prod,live` with the comma in `spring.config.location=...`. They belong to **two different properties**: one lists profiles, while the other separates location groups. Do not replace the comma in `spring.profiles.active` with a semicolon following location-group rules.

## 9. A Configuration with More Groups

In a larger application, you may want some locations at the same tier, while other locations must strictly take higher precedence. In that case, combine both separators:

```text
classpath:/defaults/;classpath:/shared/,
file:./ops/;file:./secrets/
```

You can visualize it as:

```text
Group 1
    classpath:/defaults/
    classpath:/shared/
              |
              v
Group 2
    file:./ops/
    file:./secrets/
```

Semicolons place two locations within one group; the comma separates Group 1 and Group 2. For the same key, a group processed later gets the chance to override an earlier group. Within a group, profile order applies across the locations in that group.

For example, `defaults` and `shared` both hold packaged profile-specific configuration, whereas `ops` and `secrets` represent locations outside the JAR. Grouping clearly expresses intent: operational configuration sources can override the default group, while locations within the same group are evaluated at the same profile tier.

The directory name `secrets` here is purely illustrative of a location; placing `application.properties` in a directory with that name **does not automatically create a secret-protection mechanism**. For sensitive data, apply secret-delivery and access-control mechanisms appropriate for the deployment environment.

## 10. `spring.config.location` and `spring.config.additional-location`

Both properties support declaring locations and grouping, but differ in their relationship to the default search list.

### 10.1. `spring.config.location`: replaces default locations

In our two main experiments, we used:

```properties
spring.config.location=classpath:/cfg/;classpath:/ext/
```

When set, `spring.config.location` **replaces** the default search locations. Thus, the list of Config Data sources is explicitly stated and easier to control. This does not remove other PropertySource types such as system properties or environment variables; it replaces the default application configuration file search list.

Set `spring.config.location` via command-line arguments or environment variables before Spring Boot loads Config Data. Do not expect an ordinary `application.properties` file to redefine the search list used to find itself.

### 10.2. `spring.config.additional-location`: adds to default locations

If you want to keep the locations Spring Boot scans by default and load additional sources, use:

```bash
java -jar app.jar \
  '--spring.config.additional-location=classpath:/cfg/;classpath:/ext/' \
  '--spring.profiles.active=prod,live'
```

When using `spring.config.additional-location`, the added locations are appended **after the default locations** and can override values from the default locations. Semicolons still retain their meaning of grouping the additional locations together.

So that our experiment reflected only `cfg` and `ext`, we chose `spring.config.location`; in real applications, `additional-location` is often more convenient when you need to preserve the application's default `application.yml`.

Avoid changing `spring.config.location` and adding `spring.config.additional-location` at the same time in a beginner experiment unless you document the entire list of sources; otherwise, it is hard to tell where values originate.

### 10.3. `spring.config.import` is a separate mechanism

A configuration file can also declare `spring.config.import` to pull in data from elsewhere. That is an additional import mechanism from **inside a configuration document**; import ordering follows its own rules. Do not take conclusions about `,` / `;` in `spring.config.location` and automatically assume they apply identically to `spring.config.import`.

This lesson focuses on **location groups** through the two location properties so you can clearly see the effect of the separator characters.

## 11. Syntax Rules Easy to Get Wrong in Practice

### 11.1. Quoting arguments containing semicolons

In Bash and PowerShell, `;` acts as a command separator when it appears in the appropriate syntactic position. Therefore, **enclose the entire argument containing a semicolon in quotes**.

Correct for Bash or PowerShell:

```bash
java -jar app.jar '--spring.config.location=classpath:/cfg/;classpath:/ext/'
```

Do not use the following unquoted form to test semicolons:

```text
java -jar app.jar --spring.config.location=classpath:/cfg/;classpath:/ext/
```

In this form, the shell may treat the part after `;` as a new command. The failure happens in the shell **before Spring Boot ever receives the string to parse**, so it is not evidence of location group rules.

With `cmd.exe` on Windows, you can wrap each argument in double quotes:

```bat
java -jar app.jar "--spring.config.location=classpath:/cfg/;classpath:/ext/" "--spring.profiles.active=prod,live"
```

### 11.2. Directory paths ending with `/`

Correct:

```text
classpath:/cfg/
file:./config/
```

Do not declare a directory as `classpath:/cfg` and expect Spring Boot to infer it is a directory. Location syntax rules require a trailing slash for directory locations.

### 11.3. Missing locations

A required location that cannot be found can prevent the application from starting with a Config Data error. If you genuinely want a location to be allowed to be absent, prepend `optional:` to that location:

```text
optional:classpath:/cfg/;optional:file:./ops/
```

Each optional location is declared explicitly. `optional:` changes how missing locations are handled; **it does not change precedence tiers or turn a semicolon into a comma**.

### 11.4. Do not confuse locations with file names

`spring.config.name` defaults to `application`. For a directory location, Spring Boot searches for matching names such as `application.properties`, `application.yml`, and profile variants. If you switch the name to `service` via `spring.config.name=service`, you must prepare files such as `service.properties` and `service-prod.properties`. An experiment with mismatched file names will lead you to misread precedence results.

### 11.5. Avoid overriding sources outside the experiment

Do not simultaneously pass `--lab.marker=something` or `-Dlab.marker=something` when comparing file groups. Under standard PropertySource ordering, those sources have higher precedence than Config Data and will cause both runs to print the same value. Likewise, check for environment variables, test properties, and additional imported configuration that could override the key.

## 12. How to Diagnose When Actual Output Differs from Expectations

If you run Experiment A and see `cfg-live` instead of `ext-prod`, check in sequence:

1. **The argument the application actually received:** does `spring.config.location` contain `,` or `;`? Was the whole string properly quoted in the shell?
2. **Active profiles:** is it really `prod,live`? If `live` is not active, `application-live.properties` will not contribute as designed.
3. **Resources in the JAR:** were the files in `cfg/` and `ext/` actually packaged? Re-run the packaging command after creating resources.
4. **Keys in each file:** does `ext/application-prod.properties` contain `lab.marker=ext-prod`? Did `ext/application-live.properties` accidentally get `lab.marker` added?
5. **Location prefixes:** do both use `classpath:` and end with `/`? If one path uses `file:`, the working directory or source contents may differ.
6. **High-precedence sources:** is there a leftover `LAB_MARKER` environment variable or `-Dlab.marker` / `--lab.marker` option?
7. **Fresh run:** was the application stopped and restarted with the new arguments? The experiment compares startup-time configuration, not live updates to running beans.

`lab.note=ext-live-loaded` is a useful indicator: it confirms that `ext/application-live.properties` was loaded in both main experiments. If `lab.note` is `null`, check profiles, paths, packaged resources, and key names before reasoning about `lab.marker` overrides.

If the project includes Spring Boot Actuator with appropriate endpoints enabled, `env` can help inspect property sources in a test environment. Do not expose real application configuration lists or print sensitive keys while diagnosing.

## 13. Self-Check Exercises

Keep the six standard files unchanged and predict the value before starting the app.

**Exercise 1 — Separating groups with commas:** With `classpath:/cfg/,classpath:/ext/` and profiles `prod,live`, why is the result `ext-prod` instead of `cfg-live`?

**Exercise 2 — Merging into one group:** With `classpath:/cfg/;classpath:/ext/`, why can `cfg-live` override `ext-prod`? What role does the absence of `lab.marker` in `ext/application-live.properties` play?

**Exercise 3 — Adding the key to the external live file:** Add `lab.marker=ext-live` to `ext/application-live.properties`, repackage, and run both grouping styles. Before running, predict both outcomes. Then explain why observing the same result **does not prove** commas and semicolons are identical.

**Exercise 4 — Reversing profiles:** With the semicolon configuration, change `prod,live` to `live,prod`. What is the new `lab.marker` value? What changed in how profiles were evaluated?

**Exercise 5 — Reversing groups:** Try `classpath:/ext/,classpath:/cfg/` with `prod,live`. Why can changing group order let a value from `cfg` win?

**Exercise 6 — Using external files:** Move one configuration group to a directory outside the JAR, such as `file:./ops/`. Determine the working directory yourself, place appropriate `application*.properties` files there, use `optional:` if needed, and compare expressions using `,` and `;`. Change only one factor per run.

For each exercise, you have met the goal if you can explain three facts: **which locations were loaded**, **which location groups they belong to**, and **which profile overrode the key at the final tier**.

## 14. Key Takeaways to Apply

Location groups are how Spring Boot expresses precedence relationships between **sets of configuration locations**.

- `,`: ends the current group and begins the next group; a group appearing later can override values from an earlier group.
- `;`: adds a location to the same group; profile-specific variants are evaluated at the same tier across locations in that group.
- Profiles `prod,live`: a profile appearing later can override an earlier profile **within a location group**, rather than automatically crossing every group boundary.
- `spring.config.location`: replaces default Config Data search locations.
- `spring.config.additional-location`: adds locations, allowing supplementary configuration to override default configuration.

In our six-file example, two commands differed by a single character yet produced different results:

```text
classpath:/cfg/,classpath:/ext/
-> lab.marker = ext-prod

classpath:/cfg/;classpath:/ext/
-> lab.marker = cfg-live
```

Therefore, when profile-specific configuration appears not to take precedence as expected, do not look only at the names `application-prod.properties` or `application-live.properties`. Check **how location groups are declared** before concluding Spring Boot loaded the wrong file.

Reference: [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html), sections *External Application Properties*, *Profile Specific Files*, and *Location Groups*.