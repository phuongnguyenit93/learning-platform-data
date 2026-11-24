# Fixed and Import-Relative Locations in Spring Boot Config Data Import

## 1. The problem: the same import line, but where is the file searched?

As Spring Boot configuration grows, a single `application.yaml` can end up holding too many settings. We often split them into dedicated files: `database.yaml`, `messaging.yaml`, `feature-flags.properties`, or shared configuration blocks reused across multiple applications.

Spring Boot supports the `spring.config.import` directive to import additional configuration data:

~~~properties
spring.config.import=common/database.properties
~~~

An easy point of confusion is that the path `common/database.properties` is resolved **relative to the location of the file declaring the import**, not automatically from the directory where you opened your terminal. However, if you write:

~~~properties
spring.config.import=file:./common/database.properties
~~~

this becomes a **fixed import location** under Spring Boot's classification. `file:./...` uses a file path evaluated against the process's working directory, not rooted at the declaring file's directory.

A difference of a single `file:` prefix can make Spring Boot load a different file—or fail to find the file—even though the trailing name looks identical.

After this lesson, you will be able to:

- Distinguish **fixed** and **import-relative** import locations.
- Accurately predict which file is loaded when configuration imports are nested.
- Understand the roles of `optional:`, `file:`, `classpath:`, and a leading slash `/`.
- Know how to choose appropriate paths when running a JAR, packaging configuration on the classpath, or mounting external files in a container.
- Understand precedence rules for imported files and how to inspect configuration when values differ from expectations.

## 2. How does spring.config.import work?

In Spring Boot, `spring.config.import` is part of the **Config Data** mechanism. One configuration document can declare the location of one or more other documents:

~~~yaml
spring:
  config:
    import: "shared/common.yaml"
~~~

When reading the declaring document, Spring Boot determines the locations to import, loads the discovered documents, and adds their properties to `Environment`. Keys in an imported document can **override matching keys** in the document declaring the import.

Example:

~~~properties
# application.properties
app.mode=default
app.retries=2
spring.config.import=shared/override.properties
~~~

~~~properties
# shared/override.properties
app.mode=production
~~~

If the import succeeds and no higher-precedence source exists, the result is:

| Key | Effective value | Reason |
| --- | --- | --- |
| `app.mode` | `production` | The imported file overrides the value in the declaring file. |
| `app.retries` | `2` | The imported file does not define this key. |

Spring Boot merges sources property by property; it does not have to pick an entire file as the sole winner.

**Key point:** before evaluating precedence, Spring Boot must know **where the imported file actually lives**. That is why we must distinguish the two path types.

## 3. Two types of import locations

According to Spring Boot documentation, `spring.config.import` supports two ways of resolving locations:

### 3.1. Fixed location

A location is treated as **fixed** when it starts with:

- A forward slash `/`.
- A URL-style or resource protocol prefix, such as `file:` or `classpath:`.

Example:

~~~properties
spring.config.import=classpath:/shared/defaults.properties
~~~

Or:

~~~properties
spring.config.import=file:./deployment/overrides.properties
~~~

Or an absolute file system path:

~~~properties
spring.config.import=file:/etc/myapp/settings.properties
~~~

Fixed locations are resolved **independently of the file containing the import directive**. Moving the declaration line from one configuration file to another does not change *any resolution base provided by the declaring file*.

However, the word **fixed** does not mean "an absolute path in every case." For example, `file:./deployment/overrides.properties` still contains `./`. That dot relates to **the process's current working directory**, so the actual file location can change if the same JAR is launched from a different working directory.

Keep these distinct:

| Example | Core meaning |
| --- | --- |
| `classpath:/shared/defaults.properties` | Searches for the resource at that path on the classpath. |
| `file:/etc/myapp/settings.properties` | Searches for the file at the absolute path on the corresponding host machine. |
| `file:./deployment/overrides.properties` | Searches via the `file:` mechanism, with `./` tied to the process's working directory. |
| `/shared/defaults.properties` | Starts with `/`, so it is classified as fixed under Config Data rules. |

In real applications, write `classpath:` or `file:` explicitly so readers know whether a resource comes from the **classpath** or the **file system**. This also avoids mixing up the JAR's location, the declaring document's location, and the working directory.

### 3.2. Import-relative location

If a location **does not start with** `/` and **has no URL-style prefix** such as `file:` or `classpath:`, Spring Boot treats it as **import relative**:

~~~properties
spring.config.import=shared/defaults.properties
~~~

The value `shared/defaults.properties` is combined with **the location containing the document declaring the import**.

For example, if the declaring file is at:

~~~text
/demo/config/application.properties
~~~

then the relative path:

~~~properties
spring.config.import=shared/defaults.properties
~~~

is resolved to:

~~~text
/demo/config/shared/defaults.properties
~~~

If you move `application.properties` itself to another directory, the path targeted by the import directive changes along with it. This is intentional behavior: a group of configurations can be moved as a whole directory while preserving its internal relative references.

### 3.3. Quick identification table

| Value of `spring.config.import` | Classification | Resolution anchor |
| --- | --- | --- |
| `common.properties` | Relative | Directory/location of the declaring document. |
| `common/feature.yaml` | Relative | Directory/location of the declaring document. |
| `../shared/feature.yaml` | Relative | Declaring document's location stepping up to parent directory, when supported by the resource. |
| `file:./common.properties` | Fixed | `file:` mechanism, not anchored to the declaring document's directory. |
| `file:/opt/app/common.yaml` | Fixed | Explicitly specified file location. |
| `classpath:/common.yaml` | Fixed | Classpath. |
| `/common.yaml` | Fixed | Location starting with `/`. |
| `optional:common.yaml` | Relative | `optional:` is ignored when classifying; the remainder is `common.yaml`. |
| `optional:file:./common.yaml` | Fixed | `optional:` is ignored when classifying; the remainder starts with `file:`. |

The last rule in the table is especially important: **`optional:` does not determine whether a location is fixed or import relative**.

## 4. End-to-end example with files on the filesystem

Suppose we run the application with the directory structure:

~~~text
/demo/
├── application.jar
├── application.properties
└── core/
    ├── core.properties
    └── extra/
        └── extra.properties
~~~

The working directory when running the application is `/demo`, and Spring Boot loads `/demo/application.properties` from the external configuration search location outside the JAR.

Root file:

~~~properties
# /demo/application.properties
spring.application.name=config-demo
app.layer=application
spring.config.import=optional:core/core.properties
~~~

First imported file:

~~~properties
# /demo/core/core.properties
app.layer=core
app.timeout=20s
spring.config.import=optional:extra/extra.properties
~~~

Second imported file:

~~~properties
# /demo/core/extra/extra.properties
app.layer=extra
app.message=Hello
~~~

Step-by-step resolution:

1. `/demo/application.properties` declares `core/core.properties`. Without `file:` or `classpath:`, this is import relative. The target file is `/demo/core/core.properties`.

2. `/demo/core/core.properties` declares `extra/extra.properties`. This path is also import relative, but the **new anchor** is the `/demo/core` directory. The target file is `/demo/core/extra/extra.properties`.

3. Spring Boot loads properties from the discovered documents using the Config Data mechanism. When keys collide, properties in the imported file can override properties in the declaring document.

~~~text
/demo/application.properties
       |
       | spring.config.import=core/core.properties
       v
/demo/core/core.properties
       |
       | spring.config.import=extra/extra.properties
       v
/demo/core/extra/extra.properties
~~~

Assuming no other source overrides them, the effective keys are:

| Key | Value | Source |
| --- | --- | --- |
| `spring.application.name` | `config-demo` | `application.properties` |
| `app.layer` | `extra` | `extra.properties`, due to the deeper import. |
| `app.timeout` | `20s` | `core.properties` |
| `app.message` | `Hello` | `extra.properties` |

The point to remember is that the second import step **does not go back to `/demo` to look for `extra/extra.properties`**. It searches beneath the directory of `core.properties` itself.

## 5. Simply adding `file:` can change what a path means

Keep the directory structure from the previous example. Now replace the content of `/demo/core/core.properties` with:

~~~properties
spring.config.import=optional:file:./extra/extra.properties
~~~

This is a **fixed location**, because `optional:` is followed by the `file:` prefix. If the process runs from `/demo`, the path `./extra/extra.properties` points to:

~~~text
/demo/extra/extra.properties
~~~

It **does not point to**:

~~~text
/demo/core/extra/extra.properties
~~~

Consequently, if `/demo/extra/extra.properties` does not exist, Spring Boot skips this import location because of `optional:`. The `app.message` property is not added from the original file in `/demo/core/extra`.

Now remove `optional:`:

~~~properties
spring.config.import=file:./extra/extra.properties
~~~

If the location does not exist, normal startup will fail with an error in the `ConfigDataLocationNotFoundException` family.

The lesson here is not that `file:` is always wrong. That prefix is a valid choice **when you intentionally want to reference a location independent of where the declaring document lives**. The key is knowing clearly which base it uses.

### Comparing the same filename

Suppose the declaring file is at `/demo/core/core.properties`, and the working directory is `/demo`:

| Import | Expected file |
| --- | --- |
| `extra/extra.properties` | `/demo/core/extra/extra.properties` |
| `optional:extra/extra.properties` | `/demo/core/extra/extra.properties` if present |
| `file:./extra/extra.properties` | `/demo/extra/extra.properties` |
| `file:./core/extra/extra.properties` | `/demo/core/extra/extra.properties` |
| `file:/demo/core/extra/extra.properties` | `/demo/core/extra/extra.properties` |

The table above assumes a Unix filesystem environment and the stated working directory. When deploying on Windows or in a container, replace the example paths with paths suitable for the actual environment.

## 6. Importing from classpath: choosing paths by resource location

Not all configurations are files sitting beside the JAR. Many `.properties` and `.yaml` files are packaged in `src/main/resources` and become resources on the classpath.

Example:

~~~text
src/main/resources/
├── application.yaml
└── config/
    ├── defaults.yaml
    └── feature/
        └── flags.yaml
~~~

In `application.yaml` at the **classpath root**, we can declare an explicit fixed location:

~~~yaml
spring:
  config:
    import: "classpath:/config/defaults.yaml"
~~~

This path points to `config/defaults.yaml` on the classpath, regardless of which configuration file contains the declaration line.

Suppose `config/defaults.yaml` contains:

~~~yaml
spring:
  config:
    import: "feature/flags.yaml"

app:
  retries: 3
~~~

Because `feature/flags.yaml` has no URL prefix and does not begin with `/`, it is interpreted as a path **relative to the `config/defaults.yaml` document**. The target resource lies at:

~~~text
classpath:/config/feature/flags.yaml
~~~

Whereas if `defaults.yaml` declared:

~~~yaml
spring:
  config:
    import: "classpath:/feature/flags.yaml"
~~~

then Spring Boot would search for the resource at the **classpath root**:

~~~text
classpath:/feature/flags.yaml
~~~

This is a completely different location from `classpath:/config/feature/flags.yaml`. A single prefix changes how the path is resolved, even though the `feature/flags.yaml` portion remains identical.

### When to use `classpath:`?

`classpath:` suits default files packaged with the application, such as sample feature lists, shared in-JAR defaults, or parameters independent of environment secrets.

However, a file on the classpath once packaged inside a JAR is usually not convenient to edit operationally. Environment-specific configurations and secrets should be managed with suitable deployment sources, such as external files outside the JAR, environment variables, or a secret management system.

## 7. Does importing differ between application.yaml and application.properties?

Fixed vs. import-relative resolution belongs to **Config Data**; it does not change just because the declaring file is written in YAML or Java Properties.

Properties form:

~~~properties
spring.config.import=optional:shared/mail.properties
~~~

Equivalent YAML form:

~~~yaml
spring:
  config:
    import: "optional:shared/mail.properties"
~~~

Both declare an import-relative location.

Fixed form in properties:

~~~properties
spring.config.import=optional:classpath:/shared/mail.properties
~~~

Fixed form in YAML:

~~~yaml
spring:
  config:
    import: "optional:classpath:/shared/mail.properties"
~~~

To avoid trouble from how YAML interprets special characters, you can wrap the import string in quotes as shown in the examples.

**Do not confuse:** `spring.config.import` is the configuration property name; the part after the equals sign or after the colon is the location classified as fixed or import relative.

## 8. Does the `optional:` keyword make a path fixed?

No. Spring Boot strips the `optional:` prefix before evaluating whether a location is fixed or import relative.

Example:

~~~properties
spring.config.import=optional:secrets/local.properties
~~~

This location is still resolved **relative to the declaring file**.

Whereas:

~~~properties
spring.config.import=optional:file:./secrets/local.properties
~~~

remains fixed because of the `file:` prefix following `optional:`.

The real difference `optional:` provides is **the policy when the location is not found**:

- Without `optional:`: a specified location that does not exist usually prevents Spring Boot from starting.
- With `optional:`: Spring Boot can continue starting even if that location does not exist.

However, `optional:` **does not guarantee ignoring every error**. A file that exists but has invalid YAML/Properties syntax can still cause application startup to fail. Likewise, errors from external configuration systems or additional loaders may have their own behavior.

### Choosing `optional` based on file intent

Suppose `local.properties` is intended only for developer workstations:

~~~properties
spring.config.import=optional:local.properties
~~~

Skipping when the file is missing makes sense.

However, if the service cannot operate without a critical configuration file, placing `optional:` may hide a deployment mistake where that source was forgotten. In this case, import without `optional` and let startup report a clear error.

Do not use `optional:` merely to "silence an error" before determining the actual path.

## 9. Import order and value precedence

Understanding the right path is only the first step. When multiple files define the same key, you need to know which value takes effect.

### 9.1. Imported file beats the declaring file on colliding keys

~~~properties
# application.properties
app.label=base
spring.config.import=feature.properties
~~~

~~~properties
# feature.properties
app.label=imported
~~~

If the import succeeds, the effective value of `app.label` is `imported`, unless overridden by another higher-precedence source.

Whether the `spring.config.import` line is declared before or after `app.label` **does not affect** this precedence rule:

~~~properties
spring.config.import=feature.properties
app.label=base
~~~

and:

~~~properties
app.label=base
spring.config.import=feature.properties
~~~

produce the same result for this document pair.

### 9.2. Multiple imports: later locations can beat earlier ones

~~~properties
spring.config.import=one.properties,two.properties
~~~

Suppose:

~~~properties
# one.properties
app.color=blue
~~~

~~~properties
# two.properties
app.color=green
~~~

When both files are loaded and no higher-precedence source exists, `app.color` is `green`. Spring Boot processes locations in the order declared; a file imported later can override one imported earlier.

Choosing fixed vs. import relative **determines which file is found**; **loading order rules** determine which value wins among the sources actually found. These are two independent questions that should be solved one after the other.

### 9.3. An import location is loaded only once

If the same resource is declared for import multiple times during Config Data processing, Spring Boot avoids repeatedly importing that resource just because it appears in multiple declarations. You should not rely on writing the same import multiple times to boost precedence.

### 9.4. Profiles can add corresponding variants

With an import such as:

~~~properties
spring.config.import=feature.properties
~~~

when the `prod` profile is active, Spring Boot can also consider matching profile-specific variant documents such as `feature-prod.properties`. Thus, an effective value may come from a profile variant rather than the `feature.properties` file you noticed first.

Check active profiles and related variants before concluding an import is picking the wrong file.

## 10. Distinguishing import from spring.config.location

The following three properties are commonly confused:

| Property | Purpose | Typical usage |
| --- | --- | --- |
| `spring.config.import` | A Config Data document declares that it wants to import additional documents. | Placed inside `application.properties` or `application.yaml`. |
| `spring.config.location` | Specifies configuration search locations, **replacing** default locations. | Supplied early enough via CLI, JVM system property, or environment variable. |
| `spring.config.additional-location` | **Adds** configuration search locations to the default set. | Supplied early enough before Config Data loading takes place. |

Example:

~~~bash
java -jar app.jar --spring.config.location=optional:file:./deploy/
~~~

`spring.config.location` is an early startup setting; Spring Boot uses it to determine where to look for configuration files. If pointing to a directory, the directory path must end with `/` so Spring Boot looks for matching configuration filenames.

Meanwhile, in `application.properties`:

~~~properties
spring.config.import=shared/settings.properties
~~~

is a directive to import additional data from the document currently being read.

**Do not treat the two approaches as interchangeable.** If you want a configuration group to move together with its root directory, import relative usually expresses that intent better. If operators need to decide the entire search location before the application starts, `spring.config.location` or `spring.config.additional-location` is more appropriate.

## 11. Real-world scenario: packaged application and external configuration files

An application can be deployed with the layout:

~~~text
/opt/shop/
├── shop.jar
├── config/
│   ├── application.yaml
│   └── common/
│       └── limits.yaml
└── overrides/
    └── prod.yaml
~~~

Suppose the process runs from `/opt/shop` and Spring Boot loads `/opt/shop/config/application.yaml`.

~~~yaml
# /opt/shop/config/application.yaml
spring:
  config:
    import:
      - "common/limits.yaml"
      - "optional:file:./overrides/prod.yaml"

shop:
  mode: base
~~~

Two adjacent imports are resolved differently:

| Import | Type | Target location |
| --- | --- | --- |
| `common/limits.yaml` | Import relative | `/opt/shop/config/common/limits.yaml` |
| `optional:file:./overrides/prod.yaml` | Fixed | `/opt/shop/overrides/prod.yaml` if present |

`common/limits.yaml` is tied to the structure of the `config` directory. `overrides/prod.yaml` depends on the `/opt/shop` working directory when the application runs.

If you change the launch command to:

~~~bash
cd /tmp
java -jar /opt/shop/shop.jar
~~~

then the fixed path `file:./overrides/prod.yaml` now uses `/tmp` as its base and no longer points to `/opt/shop/overrides/prod.yaml`. Meanwhile, the import-relative path `common/limits.yaml` still resolves based on **the loaded `application.yaml` file**.

To avoid depending on the working directory in deployments, you can use an absolute fixed path, for example:

~~~yaml
spring:
  config:
    import: "optional:file:/opt/shop/overrides/prod.yaml"
~~~

This is predictable on machines matching that exact structure, but in return couples configuration to a specific infrastructure path. Across multiple environments, choose a clear directory convention consistent between configuration and launch commands.

## 12. Importing data from volume mounts and configuration trees

In Docker or Kubernetes, configuration can be mounted as files inside the container. Two common styles exist:

1. A `.properties` or `.yaml` file containing many keys and values.
2. A directory containing many small files, where the filename becomes the key and the file content becomes the value (*configuration tree*).

For the first style:

~~~properties
spring.config.import=optional:file:/run/config/shop.yaml
~~~

This is a **fixed** location because of `file:`.

For the second style:

~~~properties
spring.config.import=optional:configtree:/run/secrets/
~~~

`configtree:` is the prefix identifying the configuration tree loader. Where the declaring document sits does not alter the `/run/secrets/` path in this case.

Suppose you have:

~~~text
/run/secrets/
└── db.password
~~~

then `db.password` can become a property in `Environment`. You must protect access permissions and secret distribution; `spring.config.import` itself does not encrypt data.

Do not mechanically apply relative path concatenation from a YAML file to `configtree:` as if it were an ordinary relative import: this is syntax specifying a distinct data-loading location type.

## 13. Diagnosing when Spring Boot cannot find a file

When encountering an error such as `ConfigDataLocationNotFoundException`, inspect in the following order.

### Step 1: read the literal import value

Example:

~~~properties
spring.config.import=optional:file:./extras/settings.properties
~~~

Break it apart:

- `optional:`: allows the location to be missing.
- `file:`: makes the location fixed.
- `./extras/settings.properties`: file path relative to the process's working directory.

If the value were `optional:extras/settings.properties`, it would belong to the import-relative type instead.

### Step 2: identify the file **actually declaring** the import

Do not look only at `application.yaml`. A previously imported file can itself declare further imports. With:

~~~text
config/application.yaml
config/shared/base.yaml
config/shared/local/dev.yaml
~~~

if `base.yaml` imports `local/dev.yaml`, that path is searched from `config/shared`, not from the directory containing `application.yaml`.

### Step 3: determine the working directory when using `file:./`

On Unix systems, you can run:

~~~bash
pwd
~~~

Or log the working directory in a development program. Relative paths inside `file:./...` can change when running via an IDE, Gradle, Docker, systemd, or a deployment script because each tool may set a different working directory.

Do not infer the working directory merely from where the JAR is located.

### Step 4: distinguish classpath files from external files

A resource in `src/main/resources` normally goes onto the classpath when the application is packaged. `classpath:/...` searches on the classpath; `file:...` searches on the file system. Identical names do not guarantee both point to the same resource.

### Step 5: verify names, extensions, and profiles

Check case sensitivity, directory paths, `.properties` or `.yaml` extensions, and active profiles. When applicable, Spring Boot also considers profile-specific variants of imported documents.

If the path is right yet the file is not loaded, check file syntax and Config Data rules before toggling `optional:`.

### Step 6: inspect actual documents via Environment

During development, you can create a component that prints illustrative keys:

~~~java
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class ConfigProbe implements ApplicationRunner {
    private final Environment environment;

    public ConfigProbe(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("app.mode=" +
                environment.getProperty("app.mode", "(missing)"));
        System.out.println("app.layer=" +
                environment.getProperty("app.layer", "(missing)"));
    }
}
~~~

Reading out values shows that the properties have entered `Environment`, though a key could still be overridden by an environment variable, Java System property, or CLI argument. If you need source names, you can iterate over the `PropertySource` list of `ConfigurableEnvironment` in a development environment. Do not print the entire configuration or secret values to logs.

When analyzing Config Data loading, you can enable TRACE logging for `org.springframework.boot.context.config` in a test environment for more clues about document discovery.

## 14. Common misconceptions

**Misconception 1 — "Without `file:`, Spring always searches from the current directory."**

Incorrect. Import-relative locations use **the document declaring the import** as the anchor. If that document lives in another directory, the search location differs as well.

**Misconception 2 — "Having `file:` means it is an absolute path."**

Incorrect. `file:./a.properties` is a fixed location under Config Data classification, yet `./` can still depend on the working directory. Only `file:/etc/a.properties` specifies a Unix-style absolute path.

**Misconception 3 — "`optional:` turns any import into a relative path."**

Incorrect. `optional:` only affects whether a missing location is allowed; it does not change fixed vs. import-relative classification.

**Misconception 4 — "All nested imports are resolved from the initial `application.yaml`."**

Incorrect. Each import-relative path must be resolved based on **the document directly containing that declaration line**.

**Misconception 5 — "The declaring file always has higher precedence than the imported file."**

Incorrect. For colliding keys in Config Data, the imported file can override the declaring file's value. Sources such as CLI or environment variables can in turn override the final value.

**Misconception 6 — "Adding an import twice forces higher precedence."**

Incorrect. Spring Boot only imports a given resource once. If you need precedence among multiple imported documents, use proper declaration order and clean configuration structure.

**Misconception 7 — "A missing file and a file with invalid syntax are the same error."**

Incorrect. `optional:` allows handling **a missing location**; it does not mean accepting malformed contents.

## 15. Practice exercises with answers

### Exercise 1: choose the right path

Structure:

~~~text
/app/
├── application.properties
└── config/
    ├── group.properties
    └── details/
        └── rules.properties
~~~

`/app/application.properties`:

~~~properties
spring.config.import=config/group.properties
~~~

Inside `/app/config/group.properties`, to import `/app/config/details/rules.properties`, choose:

A. `spring.config.import=details/rules.properties`

B. `spring.config.import=file:./details/rules.properties`

**Answer: A.** This is an import-relative location anchored at the directory of `group.properties`. Option B is fixed and, when the process runs from `/app`, points to `/app/details/rules.properties`.

### Exercise 2: moving the declaring file to another directory

Previously `/app/config/a.properties` had:

~~~properties
spring.config.import=common.properties
~~~

After moving `a.properties` to `/app/config/new/a.properties` while keeping the same statement, where does Spring Boot look for `common.properties`?

**Answer:** at `/app/config/new/common.properties`, because the import location resolves relative to the declaring file after the move.

If the requirement is to always point to `/app/config/common.properties` regardless of where the declaring file lives, on this system you can use `file:/app/config/common.properties`.

### Exercise 3: classifying `optional`

Classify:

~~~properties
spring.config.import=optional:defaults.yaml,optional:classpath:/shared/global.yaml
~~~

**Answer:** `optional:defaults.yaml` is import relative; `optional:classpath:/shared/global.yaml` is fixed. Both allow skipping the location if it does not exist.

### Exercise 4: predicting precedence

`application.properties`:

~~~properties
app.status=base
spring.config.import=one.properties,two.properties
~~~

`one.properties`:

~~~properties
app.status=one
~~~

`two.properties`:

~~~properties
app.status=two
~~~

**Answer:** if both files are loaded from the expected locations and there is no higher-precedence source, `app.status=two` because the later import location overrides the earlier import location.

### Exercise 5: computing the destination in a multi-layered config app

Structure:

~~~text
/opt/demo/
├── app.jar
├── application.properties
├── local/
│   └── secrets.properties
└── layers/
    ├── layer.properties
    └── local/
        └── secrets.properties
~~~

`/opt/demo/application.properties` imports `layers/layer.properties`; `layer.properties` imports `local/secrets.properties`. Which file is loaded in the second import?

**Answer:** `/opt/demo/layers/local/secrets.properties`.

If you change the second import to `file:./local/secrets.properties` and the working directory is `/opt/demo`, the loaded file will be `/opt/demo/local/secrets.properties`.

## 16. Decision rules when writing real configurations

| Purpose | Consider using | Why |
| --- | --- | --- |
| Keep related files in the same directory tree and move the whole tree | `spring.config.import=shared/common.yaml` | The reference travels with the declaring file. |
| Import default resources packaged inside the JAR | `spring.config.import=classpath:/shared/common.yaml` | The resource root on the classpath is clearly defined. |
| Import a file outside the JAR at an infrastructure-defined path | `spring.config.import=file:/etc/app/config.yaml` | Independent of the declaring file's directory. |
| Import a file at a path relative to the working directory | `spring.config.import=file:./runtime/config.yaml` | Intentionally depends on where the process runs. |
| Allow an additional file to be absent | Add `optional:` before the location | The application continues when only that location is missing. |
| Load keys from an externally mounted secrets directory | `spring.config.import=configtree:/run/secrets/` | Uses the configuration tree mechanism. |

**Remember:** when reading `spring.config.import`, first strip `optional:` if present and then look at the beginning of what remains. If it starts with `/` or a prefix like `file:` or `classpath:`, it is a **fixed location**. Otherwise, it is an **import relative location**, resolved relative to the file declaring the import itself. Only after identifying the exact resource should you evaluate import order, profiles, and configuration source precedence.

**Reference:** [Spring Boot 3.3 — Externalized Configuration, Importing Additional Data and Using Fixed and Import Relative Locations](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html).
