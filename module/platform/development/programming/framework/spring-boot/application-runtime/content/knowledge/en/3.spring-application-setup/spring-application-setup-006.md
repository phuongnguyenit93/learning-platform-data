# Customizing the Spring Boot Startup Banner with banner.txt, Banner, and Banner.Mode

## 1. Where Does the Banner Fit in the Startup Process?

When `SpringApplication.run(...)` is called, Spring Boot typically prints a block of text or ASCII art at the beginning of startup output, before messages such as `Starting ...` and `Started ...`. This block is called the **startup banner**. The banner helps identify the application, release, or branding when viewing terminals and logs, but it is **not** a web UI, an application readiness signal, a business logging mechanism, or a health check.

The three tools in this lesson address three distinct needs:

| Tool | Responsibility | When to Use It? |
| --- | --- | --- |
| `banner.txt` | Declares banner **content** using a text resource on the classpath or at a configured location | Static banners, ASCII art, version/application name placeholders |
| `org.springframework.boot.Banner` | Programmatically **generates banner content** in Java inside `printBanner(...)` | Banners with formatting rules or computed conditions in code |
| `Banner.Mode` | Selects **how the banner is emitted**: console, logger, or off | Adjusting per runtime environment and log collection requirements |

Picture it as follows:

```text
SpringApplication.run(args)
    |
    v
Prepare Environment and spring.main.* configuration
    |
    v
Choose banner content: text resource / custom Banner / default banner
    |
    v
Banner.Mode
    +--> CONSOLE: print to System.out
    +--> LOG:     send to configured logger
    +--> OFF:     do not print banner
    |
    v
Continue preparing, refreshing ApplicationContext, and starting the application
```

The banner appears during startup once `Environment` has been prepared. It can display configuration values that `Environment` already knows about, but it must not require a business bean to be initialized in order to print.

## 2. Simplest Approach: Placing banner.txt on the Classpath

In a Spring Boot project using Gradle or Maven, place the file at the exact path:

```text
banner-demo/
  src/
    main/
      java/
        demo/banner/BannerDemoApplication.java
      resources/
        application.properties
        banner.txt
```

Contents of `src/main/resources/banner.txt`:

```text
====================================
          BANNER DEMO
====================================
Application: ${spring.application.name}
Spring Boot: ${spring-boot.version}
====================================
```

`src/main/resources/application.properties`:

```properties
spring.application.name=banner-demo
```

Basic launcher class at `src/main/java/demo/banner/BannerDemoApplication.java`:

```java
package demo.banner;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BannerDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BannerDemoApplication.class, args);
    }
}
```

This is a standalone Java class inside a **Spring Boot project with the appropriate plugin and dependencies**; it is not a plain Java program run with `javac` alone without libraries. The `spring-boot-starter` dependency is sufficient for an example that starts without a web server; web projects can use `spring-boot-starter-web`.

Run using the project's Gradle wrapper:

```bash
./gradlew bootRun
```

Or package and run the actual JAR file produced by the build:

```bash
./gradlew bootJar
java -jar build/libs/actual-jar-filename.jar
```

With a Spring Boot version assumed to be `3.3.x`, the banner lines look like:

```text
====================================
          BANNER DEMO
====================================
Application: banner-demo
Spring Boot: 3.3.x
====================================
```

`3.3.x` in the block above **is only an illustrative placeholder**; the actual value depends on the Spring Boot version in use. Other startup log lines still appear after the banner.

**Why place it in `src/main/resources`?** The build tool copies files into the output resources and packages them with the application. When building an executable Spring Boot JAR, the file normally resides at `BOOT-INF/classes/banner.txt`. Spring Boot can read that resource from the classpath; there is no need to keep the `src/main/resources` folder on the machine running the JAR.

Do not place it in `src/test/resources` by mistake if the banner must appear in releases; test resources are normally not packaged into the application JAR.

## 3. Moving or Renaming the File with spring.banner.location

The default filename is `banner.txt` at the classpath root. If you want to group resources by folder, create:

```text
src/main/resources/branding/welcome.txt
```

Then set:

```properties
spring.banner.location=classpath:branding/welcome.txt
```

You can also pass the location directly at runtime:

```bash
java -jar app.jar --spring.banner.location=classpath:branding/welcome.txt
```

If you want operations to manage the banner independently of the artifact, you can point to the filesystem, for example on Linux:

```properties
spring.banner.location=file:/opt/demo/branding/welcome.txt
```

Distinction:

- `classpath:branding/welcome.txt`: looks for a resource on the **runtime classpath**; suitable when the file is already packaged.
- `file:/opt/demo/branding/welcome.txt`: reads a **physical file** from an absolute path on Linux.
- `file:./branding/welcome.txt`: looks up an external file relative to the **process working directory**; changing how you launch can change which file is found.

Do not use `src/main/resources/banner.txt` as a relative filesystem path for configuring releases. Source directory layouts may not exist at deployment time.

Set `spring.banner.charset=UTF-8` if you need to specify explicitly how the text file is decoded. UTF-8 is the default in modern Spring Boot; use UTF-8 when writing Vietnamese and other Unicode characters. If the terminal displays broken diacritics or misaligned ASCII columns, check the file encoding, output encoding/locale, and terminal font. Not every Unicode character has a display width of one column.

## 4. Placeholder Variables in banner.txt

Spring Boot can substitute placeholders in the file with data already in `Environment` and several special banner variables.

| Variable in Banner File | Meaning |
| --- | --- |
| `${spring.application.name}` | Reads `spring.application.name` from `Environment` |
| `${spring-boot.version}` | Spring Boot library version at runtime |
| `${spring-boot.formatted-version}` | Spring Boot version formatted for display, e.g., `(v3.3.x)` |
| `${application.title}` | Application name from `Implementation-Title` in the manifest, if provided |
| `${application.version}` | Application version from `Implementation-Version` in the manifest, if provided |
| `${application.formatted-version}` | Application version variable formatted for display |
| `${AnsiColor.GREEN}`, `${AnsiColor.DEFAULT}` | ANSI text color control codes when supported by the environment |

Example of a file that does not depend on the application's own version value:

```text
${AnsiColor.GREEN}=== ${spring.application.name} ===${AnsiColor.DEFAULT}
Powered by Spring Boot ${spring-boot.version}
```

If you want to use `${application.version}`, understand its source. Spring Boot retrieves the application version from manifest metadata and supporting launcher mechanisms. When running from an IDE or launching classes directly from output directories, the value may **not appear the same as when running an executable JAR**. Likewise, in native images, the `application.*` variables are not guaranteed in the same way as with the Spring Boot launcher. Do not treat these variables as inputs controlling business logic.

Configuration placeholders also depend on property sources available when the banner is printed. To avoid blank lines or unresolved placeholders, declare the keys you want to display explicitly or test with the actual launch method.

**ANSI colors** can be enabled/disabled automatically depending on the environment and terminal capabilities. To test colors on a development machine:

```properties
spring.output.ansi.enabled=always
```

Check the log collection system before forcing colors in production, because escape sequences may appear as unreadable characters in stored logs. `spring.output.ansi.enabled` controls output colors; it does not select `Banner.Mode`.

## 5. Banner.Mode: CONSOLE, LOG, and OFF

`Banner.Mode` is an enum nested in `org.springframework.boot.Banner`. Three values to know:

| Mode | Where Is the Banner Sent? | Observable Consequence |
| --- | --- | --- |
| `Banner.Mode.CONSOLE` | `System.out` | Usually seen directly on terminal/stdout, not necessarily passing through logger patterns/levels/filters |
| `Banner.Mode.LOG` | The logger system used by Spring Boot | Depends on log level configuration, appenders/handlers, and where logs are collected |
| `Banner.Mode.OFF` | No banner emitted | Hides only the banner; the application still starts and other log lines can still appear |

Configure via `application.properties`:

```properties
# Choose exactly one value: console, log, or off.
spring.main.banner-mode=console
```

Switch mode via command-line argument without modifying the artifact:

```bash
java -jar app.jar --spring.main.banner-mode=off
```

Or:

```bash
java -jar app.jar --spring.main.banner-mode=log
```

Equivalent YAML format:

```yaml
spring:
  main:
    banner-mode: log
```

**Setting the mode does not change the banner content.** If `banner.txt` contains `BANNER DEMO`, switching `console` to `log` only changes the output route; switching to `off` skips printing the banner. Do not confuse `off` with disabling all logging, stopping the application, or changing health/readiness.

**Note on LOG:** the banner is sent through a logger, so it might not appear if log levels or appenders filter out the message. Not seeing the banner in a log file does not by itself prove that Spring Boot failed to start. With `CONSOLE`, container or service stdout redirection determines where operators see it.

## 6. Configuring Banner.Mode Directly in Java

When you want to decide the mode in startup code, replace the static `SpringApplication.run(...)` call with an instance:

```java
package demo.banner;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BannerDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(BannerDemoApplication.class);

        application.setBannerMode(Banner.Mode.CONSOLE);
        application.run(args);
    }
}
```

Options:

```java
application.setBannerMode(Banner.Mode.OFF);     // Do not print banner
application.setBannerMode(Banner.Mode.CONSOLE); // Print to stdout
application.setBannerMode(Banner.Mode.LOG);     // Send via logger
```

These three lines are **three alternative choices**; do not put them sequentially in a real program because the last line replaces the previous ones.

You can also configure using `SpringApplicationBuilder`:

```java
new SpringApplicationBuilder(BannerDemoApplication.class)
        .bannerMode(Banner.Mode.OFF)
        .run(args);
```

The snippet above requires importing `org.springframework.boot.builder.SpringApplicationBuilder` and belongs inside an appropriate startup method; this is an alternative to instantiating `new SpringApplication(...)`.

**Relationship between code and external configuration:** `spring.main.banner-mode` is a property that Spring Boot binds onto `SpringApplication` during startup. External configuration can override the mode set in Java. For example, if code calls `setBannerMode(OFF)` while the loaded `application.properties` sets `spring.main.banner-mode=console`, the result may still print the banner according to configuration. Pick one primary place to configure it and check active property sources before concluding that the setter was ignored.

## 7. When Custom Logic Is Needed: Implementing org.springframework.boot.Banner

`banner.txt` is sufficient for static content and placeholders. If you need conditional formatting based on the environment, deployment group, or a simple rule, implement the `Banner` interface.

Create `src/main/java/demo/banner/RuntimeBanner.java`:

```java
package demo.banner;

import java.io.PrintStream;
import org.springframework.boot.Banner;
import org.springframework.core.env.Environment;

public final class RuntimeBanner implements Banner {

    @Override
    public void printBanner(
            Environment environment,
            Class<?> sourceClass,
            PrintStream out) {

        String name = environment.getProperty(
                "spring.application.name", "banner-demo");
        String stage = environment.getProperty(
                "app.stage", "local");

        out.println("====================================");
        out.println(" Application: " + name);
        out.println(" Stage: " + stage);
        out.println("====================================");
    }
}
```

In `BannerDemoApplication`, register it with `setBanner(...)`:

```java
package demo.banner;

import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BannerDemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(BannerDemoApplication.class);

        application.setBanner(new RuntimeBanner());
        application.setBannerMode(Banner.Mode.CONSOLE);
        application.run(args);
    }
}
```

Example configuration:

```properties
spring.application.name=banner-demo
app.stage=development
```

If the program selects `RuntimeBanner` (and no higher-priority text banner resource exists), the banner output from `printBanner` is:

```text
====================================
 Application: banner-demo
 Stage: development
====================================
```

**Three parameters in `printBanner`:**

- `Environment environment` lets you read configuration already available when the banner is generated. Use `getProperty(key, defaultValue)` for optional values.
- `Class<?> sourceClass` provides information about the application's source class when applicable; handle the case where no source class is provided. The example above does not need this parameter.
- `PrintStream out` is the stream **provided by Spring Boot** to print the banner. Use `out.print(...)` / `out.println(...)`, and do not arbitrarily switch to `System.out`. When the mode is `LOG`, Spring Boot can render the banner into a buffer before forwarding it to the logger; printing directly to `System.out` defeats the configuration intent.

`Banner` is a callback invoked during early startup. Do not build a banner that depends on `@Autowired`, business beans, database connections, or network calls because those components may not be ready yet. A banner should produce fast, stable, and safe output.

In particular, **`setBanner(new RuntimeBanner())` does not mean `banner.txt` is always ignored**. In Spring Boot's banner printing mechanism, a text banner resource found via `spring.banner.location` can take precedence over a `Banner` registered as a fallback. If you are testing the Java example and still see ASCII art from a file, remove or rename the `banner.txt` resource accordingly, or stick to a single consistent customization approach. Do not conclude that `printBanner` is broken simply because it was not called.

## 8. Content Selection Model: File, Code, and Default

Distinguish **choosing content** from **choosing output destination**. A practical mental model for text banners is:

```text
Is there banner.txt or a resource from spring.banner.location?
   |
   +-- Yes ---> Content from the text resource
   |
   +-- No  ---> Is there a custom Banner via setBanner(...)?
                   |
                   +-- Yes ---> Content generated by printBanner(...)
                   |
                   +-- No  ---> Default Spring Boot banner
                                           |
                                           v
                                  Check Banner.Mode
```

This diagram reflects the basic precedence among text banner resources, a programmatic fallback banner, and the default banner. If a project uses other banner resource types supported by its Spring Boot version, check the exact supported behavior in that version.

Scenarios:

1. Only `src/main/resources/banner.txt` exists and mode is `CONSOLE`: prints the banner from the file.
2. No custom banner file, no `setBanner(...)` call, and mode is `CONSOLE`: displays the default Spring Boot banner.
3. No banner file, `setBanner(new RuntimeBanner())` is set, and mode is `LOG`: the Java-generated content is sent to the logger.
4. Both `banner.txt` and `setBanner(new RuntimeBanner())` exist: the text banner resource is normally chosen before the fallback in the mechanism above.
5. Regardless of content source, `Banner.Mode.OFF`: skips displaying the banner.

A common mistake is pointing `spring.banner.location` to the wrong path and expecting to see that file's content. Verify that the file actually exists on the runtime classpath or filesystem and check whether a fallback banner was selected instead.

## 9. Hands-On: Running the Same Application in All Three Modes

Keep the project from section 2, with `banner.txt` and `spring.application.name=banner-demo`. Try each mode one by one, each as **a separate execution**:

```bash
./gradlew bootRun --args='--spring.main.banner-mode=console'
./gradlew bootRun --args='--spring.main.banner-mode=log'
./gradlew bootRun --args='--spring.main.banner-mode=off'
```

These commands illustrate shells that understand single quotes such as Bash; if PowerShell or another plugin parses arguments differently, use the corresponding quoting syntax.

Expected results:

| Run | What to Check |
| --- | --- |
| `console` | The `BANNER DEMO` block appears directly on stdout before or alongside startup log lines |
| `log` | The banner block is sent via the logger; inspect the corresponding output/appender and INFO level |
| `off` | The banner block does not appear, yet the application still starts normally and startup log lines may still remain |

If running via executable JAR:

```bash
java -jar app.jar --spring.main.banner-mode=console
java -jar app.jar --spring.main.banner-mode=log
java -jar app.jar --spring.main.banner-mode=off
```

Replace `app.jar` with the path to your built artifact. For an application without a web server, the process may exit automatically after startup completes if nothing keeps it alive; this does not invalidate the banner experiment.

**Next experiment:** remove `banner.txt` from build resources, configure `setBanner(new RuntimeBanner())`, and observe the output. Then put `banner.txt` back and compare. When changing resources, rebuild the artifact to avoid running an outdated JAR.

## 10. Banner and Logging: Easy-to-Make Misconceptions

**CONSOLE is not the same as LOG.** `CONSOLE` prints directly to stdout via Spring Boot's mechanism; `LOG` passes the content into the logger. When a container routes both stdout and application logs to the same destination, an observer might think they are the same mechanism. The difference surfaces when log patterns, level filtering, appenders, or log retention policies exist.

**The banner does not prove the application is ready.** It is generated early in startup, before there is any guarantee that all beans initialized successfully or that the application is ready to handle requests. Use health checks, `ApplicationReadyEvent`, or readiness mechanisms to determine serving status—do not grep for banner text.

**OFF does not turn off logging.** `spring.main.banner-mode=off` only controls the banner. Reducing startup informational messages requires a separate Spring Boot or logging setting, such as `spring.main.log-startup-info`. Do not conflate them into a single toggle.

**ANSI does not guarantee color everywhere.** Some terminals support colors, whereas log viewers or plain text files may preserve raw escape codes. For banners destined for log files or centralized logging systems, prefer clean plain text.

**Do not print secrets in the banner.** Even though `Environment` allows property access, the banner can be sent to terminals or log systems visible to many people. Never print passwords, API keys, sensitive connection strings, or tokens—even in test environments.

**Do not turn the banner into business logic.** Avoid relying on the banner to run migrations, call APIs, or initialize application state. If the banner throws an exception, startup can be unnecessarily disrupted.

## 11. Troubleshooting Common Issues

| Symptom | Cause to Check | How to Fix |
| --- | --- | --- |
| Still seeing the default Spring Boot banner | `banner.txt` is not on the classpath or `spring.banner.location` is wrong | Check `src/main/resources/banner.txt`, rebuild, and inspect JAR contents |
| No banner appears at all | `spring.main.banner-mode=off`, external config overrides the mode, or logger filtered it in LOG mode | Check effective mode, runtime arguments, and logging config |
| Called `setBanner(...)` yet Java content does not appear | A text banner resource was chosen ahead of the fallback | Remove/relocate the text banner or use a single mechanism |
| Application name not substituted in file | Missing `spring.application.name` in `Environment` or placeholder syntax error | Declare the property, keep `${spring.application.name}` syntax |
| `${application.version}` has unexpected/missing value | No `Implementation-Version` in manifest or run via a launcher that does not supply it | Inspect manifest and retry via an executable Spring Boot JAR |
| Vietnamese characters or ASCII art are garbled | Mismatched file/terminal encoding, variable-width display font | Save file as UTF-8, check `spring.banner.charset`, font, and output encoding |
| Colors missing or strange escape sequences appear | Terminal lacks ANSI support, improper ANSI setting, or log sink does not process escapes | Check `spring.output.ansi.enabled`; prefer a colorless banner in log pipelines |
| Same application shows different banners across environments | Different profiles, external config, `spring.banner.location` args, or working directories | Determine actual location via runtime classpath or absolute path |
| Banner appears yet service still fails to start | Banner prints before application ready | Check stack trace, error logs, and readiness independently |

You can verify banner packaging with the following command, using the real JAR name:

```bash
jar tf build/libs/app.jar
```

In the listing, look for `BOOT-INF/classes/banner.txt` or your configured path under `BOOT-INF/classes/branding/`. The name `app.jar` is just an example.

If `LOG` does not appear while `CONSOLE` does, inspect logging configuration, log levels, and appenders before editing the banner file. If `CONSOLE` does not appear because `OFF` is set in an external configuration source, changing `setBannerMode(...)` in code alone may not be enough.

## 12. Choosing an Approach in Real Projects

For small projects or releases with fixed ASCII art, choose **`banner.txt`**. It is simple, easy to review, and designers can update content without touching Java code.

For banners requiring conditional formatting from configuration while still relying only on data available at startup, choose a custom **`Banner`**. Avoid side effects and print only to `PrintStream out`.

For applications running in log aggregation systems, consider **`Banner.Mode.LOG`** when the banner needs to flow through the log pipeline; choose **`OFF`** if the banner only adds noise. Choose **`CONSOLE`** when watching stdout directly is the primary goal. This is an operational choice, not a business feature change.

An easy-to-maintain policy:

- Keep one primary banner source: a text file **or** a Java callback.
- Use `spring.main.banner-mode` to adjust emission per environment.
- Use properly published application names/versions; never print secrets.
- Test both `bootRun` and the executable JAR, especially when using `application.version` or external file paths.
- Never treat banner output as a signal that the application is ready.

## 13. Self-Check Questions

1. Why does placing `banner.txt` in `src/main/resources` work after `java -jar`, whereas pointing to the filesystem path `src/main/resources/banner.txt` can fail?
2. If you want the banner to go through a logger appender, what value should `spring.main.banner-mode` be set to? Why can `CONSOLE` behave differently even when both outputs appear in the terminal?
3. Does `spring.main.banner-mode=off` mean disabling all logging and health checks?
4. Why is `${spring-boot.version}` usually more consistent than `${application.version}` between IDE runs and executable JAR runs?
5. When you set `application.setBanner(new RuntimeBanner())` yet still see the contents of `banner.txt`, what should you check?
6. Why should you use `out.println(...)` inside `Banner#printBanner(...)` instead of calling `System.out.println(...)` directly?
7. Does the banner appearing prove that the entire `ApplicationContext` initialized successfully and the application is accepting requests?

This practice is complete when you can create a static banner, replace it with Java, switch between all three modes without editing content, verify differences between `bootRun` and JAR execution, and explain which configuration source determines the result.

**Official references:** [Spring Boot 3.3 — SpringApplication: Customizing the Banner](https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html) and [Spring Boot — Externalize the Configuration of SpringApplication](https://docs.spring.io/spring-boot/how-to/properties-and-configuration.html).
