# Passing Build Configuration Without Confusing It with Runtime Environment Variables

When packaging a Spring Boot application into a container image with **Cloud Native Buildpacks (CNB)**, the same workflow can receive configuration at two very different times: when building the image and when launching the container. Confusing these two moments easily causes mistakes such as setting the wrong port during the build, expecting a runtime profile change to recreate beans omitted by AOT, or accidentally baking credentials into the image.

Buildpacks provide environment variables to buildpacks during the image creation stage. With Paketo, many build configuration variables carry the **BP_** prefix. After the image is created, the runtime platform supplies environment variables to the running application process. Paketo also has specific conventions such as **BPL_** for buildpack-provided runtime components and **BPE_** to write launch environment variables into the image via the Environment Variables Buildpack.

This lesson distinguishes those configuration layers, illustrates passing them via Gradle, Maven, and `pack`, and checks what values Spring Boot actually receives inside a native executable.

## 1. Two Configuration Moments in the Buildpacks Lifecycle

A container image is built before the application runs. Buildpacks take source or an artifact, analyze the application, select appropriate buildpacks, execute build steps, and export an OCI image. When the container starts, the runtime platform launches the process declared in the image and provides environment variables, arguments, networking, volumes, and other resources.

~~~mermaid
flowchart TD
    A["Source / executable JAR"] --> B["Build platform: pack or Spring Boot plugin"]
    B --> C["Builder and Buildpacks"]
    D["BP_* / build tool arguments"] --> C
    C --> E["Detect, Analyze, Restore, Build, Export"]
    E --> F["OCI image"]
    G["docker run / Kubernetes / Compose"] --> H["Runtime environment and arguments"]
    F --> H
    H --> I["Native executable and Spring Boot"]
    I --> J["ApplicationContext and business logic"]
~~~

| Question | Build configuration | Runtime configuration |
|---|---|---|
| When is it read? | While Buildpacks builds the image | When the container/process starts |
| Who usually reads it? | Buildpacks, Maven/Gradle invoked during build, native-image compiler | Native executable, Spring Boot, app libraries, and runtime components |
| Example | BP_NATIVE_IMAGE=true, BP_NATIVE_IMAGE_BUILD_ARGUMENTS | SERVER_PORT, SPRING_PROFILES_ACTIVE, SPRING_DATASOURCE_URL |
| Passing mechanism | pack build --env, bootBuildImage.environment, buildpack config | docker run -e, Docker Compose, Kubernetes env/Secret |
| Can it change without rebuilding the image? | Usually no, because it affects image creation | Yes, if the app supports reading that value at runtime |

**Key rule:** environment variables passed to the build container do not automatically become environment variables of the running application container. Only values explicitly written by a buildpack into the launch environment or image metadata can persist in that manner.

## 2. Three Common Prefixes in Paketo

The prefixes below are conventions of Paketo and its corresponding buildpacks; not every Buildpack from every vendor understands them.

| Prefix | Stage | Meaning |
|---|---|---|
| BP_ | Build time | Configures buildpack behavior, e.g., selecting native image or passing compiler flags |
| BPL_ | Launch time | Configures certain runtime components provided by a buildpack, e.g., JVM components or helper processes |
| BPE_ | Declared at build time, takes effect at launch | Requests the Environment Variables Buildpack to create or modify launch environment variables in the image |

For example:

- BP_NATIVE_IMAGE=true: requests the Java Native Image buildpack to build a native executable during the build.
- BP_NATIVE_IMAGE_BUILD_ARGUMENTS=-O2: passes options to the `native-image` command, not Spring Boot arguments.
- BPL_*: can configure certain buildpack runtime features. Once the app is a native executable, do not assume JVM-specific flags such as certain BPL_JVM_* variables will have any effect.
- BPE_DEFAULT_SERVER_PORT=8080: with the Paketo Environment Variables Buildpack, sets a default SERVER_PORT in the image's launch environment. This value is stored in the image and can be overridden when the container starts depending on environment variable precedence.

Beyond these prefixes, some build tools have their own variables such as GRADLE_OPTS, MAVEN_OPTS, HTTP_PROXY, or HTTPS_PROXY. Identify precisely which program reads each variable and at which stage.

## 3. Configuring a Native Image Build with BP_NATIVE_IMAGE

For the Paketo Java Native Image Buildpack, BP_NATIVE_IMAGE is the variable that enables native image mode. The value must be provided **during the build stage** and the builder must include a buildpack set supporting native images alongside a compatible native-image toolkit.

With the pack CLI:

~~~bash
pack build demo-orders:native \
  --builder paketobuildpacks/builder-jammy-tiny \
  --path . \
  --env BP_NATIVE_IMAGE=true
~~~

This is an illustrative example. The builder tag must exist, support the target architecture/stack, and contain or resolve the required buildpacks. Some environments use different builders or pin digests for reproducible builds. Do not assume every builder supports native image simply because it is a Java builder.

If buildpacks fail to detect the application or lack a native-image toolkit, inspect detect/build logs and the builder's buildpack list. Simply setting BP_NATIVE_IMAGE=true will not automatically install missing components into a custom builder.

## 4. Passing Buildpacks Configuration via the Spring Boot Gradle Plugin

The Spring Boot Gradle plugin provides the `bootBuildImage` task. Its `environment` property holds environment variables passed to the **builder during image creation**.

With Groovy DSL in `build.gradle`:

~~~groovy
tasks.named("bootBuildImage") {
    imageName = "example/demo-orders:native"
    builder = "paketobuildpacks/builder-jammy-tiny"

    environment = [
        "BP_NATIVE_IMAGE": "true",
        "BP_NATIVE_IMAGE_BUILD_ARGUMENTS": "-O2"
    ]
}
~~~

With Kotlin DSL in `build.gradle.kts`:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootBuildImage

tasks.named<BootBuildImage>("bootBuildImage") {
    imageName = "example/demo-orders:native"
    builder = "paketobuildpacks/builder-jammy-tiny"

    environment = mapOf(
        "BP_NATIVE_IMAGE" to "true",
        "BP_NATIVE_IMAGE_BUILD_ARGUMENTS" to "-O2"
    )
}
~~~

Then run:

~~~bash
./gradlew bootBuildImage
~~~

In the example above, `BP_NATIVE_IMAGE_BUILD_ARGUMENTS` is forwarded by the buildpack to the `native-image` compiler. The `-O2` option is illustrative; valid options depend on the native-image toolkit and version. Start with defaults, and add flags only for specific reasons after testing the outcome.

In some versions of the Spring Boot Gradle plugin, when the GraalVM Native Image plugin is applied, `bootBuildImage` may automatically set `BP_NATIVE_IMAGE=true` and pick a suitable default builder. Default behavior depends on plugin version and project configuration. When you want builds to be easy to read and reproduce, inspect task logs and actual configuration instead of relying on assumptions.

**Key distinction:** `bootBuildImage.environment` is not `System.getenv()` of the running container application. It is the environment sent to the builder during the build phase. For the app to receive `SERVER_PORT` at runtime, configure it at runtime or deliberately use the `BPE` mechanism to create a launch default.

## 5. Passing Configuration via the Spring Boot Maven Plugin

The Maven plugin has a similar image environment configuration. Example in `pom.xml`:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <image>
            <name>example/demo-orders:native</name>
            <builder>paketobuildpacks/builder-jammy-tiny</builder>
            <env>
                <BP_NATIVE_IMAGE>true</BP_NATIVE_IMAGE>
                <BP_NATIVE_IMAGE_BUILD_ARGUMENTS>-O2</BP_NATIVE_IMAGE_BUILD_ARGUMENTS>
            </env>
        </image>
    </configuration>
</plugin>
~~~

Run:

~~~bash
./mvnw spring-boot:build-image
~~~

Elements inside `env` are passed to the builder during image creation. They are not Spring Boot runtime properties. If you want to change the web port or datasource URL when the container runs, configure them via Docker/Kubernetes or a supported launch environment mechanism.

When a project needs a Maven profile to prepare artifacts or run AOT, distinguish the build-time Maven profile from the application's `SPRING_PROFILES_ACTIVE`. A Maven profile can change dependencies, plugins, and artifact contents; the active Spring Boot profile at runtime controls application configuration within the capabilities of the built image.

## 6. Configuring Directly with `pack build`

`pack` is a common CLI for invoking the CNB lifecycle. The `--env` flag passes an environment variable into the **build container**:

~~~bash
pack build example/demo-orders:native \
  --builder paketobuildpacks/builder-jammy-tiny \
  --path . \
  --env BP_NATIVE_IMAGE=true \
  --env BP_NATIVE_IMAGE_BUILD_ARGUMENTS="-O2"
~~~

Other useful Paketo variables:

| Variable | Purpose |
|---|---|
| BP_NATIVE_IMAGE | Enables native image build |
| BP_NATIVE_IMAGE_BUILD_ARGUMENTS | Passes arguments to `native-image` |
| BP_NATIVE_IMAGE_BUILD_ARGUMENTS_FILE | Points to a file containing arguments in argument-file format |
| BP_NATIVE_IMAGE_BUILT_ARTIFACT | Specifies the input artifact when building from an executable JAR when explicit selection is needed |
| BP_GRADLE_BUILD_ARGUMENTS | Specifies arguments for the Gradle command invoked by the buildpack |
| BP_GRADLE_ADDITIONAL_BUILD_ARGUMENTS | Appends arguments to the Gradle command as supported by the buildpack |
| BP_MAVEN_BUILD_ARGUMENTS | Specifies arguments for the Maven command invoked by the buildpack |
| BP_LOG_LEVEL | Adjusts buildpack log level if supported, e.g., DEBUG |

`BP_GRADLE_*` and `BP_MAVEN_*` variables affect the **build tool process inside the builder**. For example, `BP_GRADLE_BUILD_ARGUMENTS` can control which Gradle task is invoked; it is not a `--server.port` flag for the application after the image runs.

Exact format and support depend on the Paketo buildpack version. For deep customization, consult the reference docs for the component buildpack used by your builder.

## 7. Distinguishing Build Tool Arguments from native-image Compiler Arguments

A native build can involve multiple command layers:

~~~text
CNB platform
   |
   +-- Buildpack configuration: BP_*
          |
          +-- Build tool (Maven/Gradle)
          |      BP_GRADLE_BUILD_ARGUMENTS
          |      BP_MAVEN_BUILD_ARGUMENTS
          |
          +-- Native Image compiler
                 BP_NATIVE_IMAGE_BUILD_ARGUMENTS

Container launch
   |
   +-- Application process
          SERVER_PORT
          SPRING_PROFILES_ACTIVE
          --server.port=...
~~~

For example, these three values mean different things:

| Value | Receiver | Effect |
|---|---|---|
| BP_GRADLE_BUILD_ARGUMENTS=--no-daemon bootJar | Gradle invoked inside the builder | Controls the artifact build command |
| BP_NATIVE_IMAGE_BUILD_ARGUMENTS=-O2 | Native Image compiler | Controls optimization during native compilation |
| SERVER_PORT=8085 at container runtime | Spring Boot inside the application process | Selects the server port at runtime |

Do not put `--server.port=8085` into `BP_NATIVE_IMAGE_BUILD_ARGUMENTS`: the compiler will treat it as an argument to `native-image` itself and likely fail. Likewise, do not put `-O2` into `SERVER_PORT` or application arguments.

A helpful rule of thumb: **the build tool creates the artifact, the native-image compiler creates the executable, and runtime config controls the running application.**

## 8. Which Values Are Saved into the Image?

Not every build environment variable is saved in the image. Buildpacks read configuration variables at build time and may use them to construct layers, metadata, or the launch environment. Whether a variable appears at runtime depends on the buildpack's functionality.

| Source | Present in launch environment by default? | Notes |
|---|---|---|
| BP_NATIVE_IMAGE=true | No | Only requests a native image build |
| BP_NATIVE_IMAGE_BUILD_ARGUMENTS | No | Only serves the compiler |
| BP_GRADLE_BUILD_ARGUMENTS | No | Only controls the Gradle build |
| SERVER_PORT set in shell running pack build | Not automatically | Buildpacks do not automatically promote all build envs into runtime envs |
| BPE_DEFAULT_SERVER_PORT=8080 | Yes, if Environment Variables Buildpack is used and supported | Creates a default value at launch |
| SERVER_PORT set via docker run -e | Present in that container process | Effective only for that container run |

You can inspect image configuration with container tools and Buildpacks metadata, though you should not assume `docker inspect` displays every dynamic variable computed by launcher/profile scripts. Verify by running the application and observing its actual configuration.

## 9. Using `BPE_*` to Embed Default Values into the Launch Environment

The Paketo Environment Variables Buildpack lets you add or modify environment variables set when the image launches. This is a **build-time action whose effect targets runtime**.

For example, `BPE_DEFAULT_SERVER_PORT` sets a default `SERVER_PORT` if no other value is supplied at launch:

~~~bash
pack build example/demo-orders:native \
  --builder paketobuildpacks/builder-jammy-tiny \
  --path . \
  --env BP_NATIVE_IMAGE=true \
  --env BPE_DEFAULT_SERVER_PORT=8080
~~~

This example only works when the builder includes the Paketo Environment Variables Buildpack or an equivalent buildpack supporting `BPE` variables. Common operations:

| Variable | Action at launch |
|---|---|
| BPE_SERVER_PORT | Sets SERVER_PORT to the configured value |
| BPE_OVERRIDE_SERVER_PORT | Overrides SERVER_PORT |
| BPE_DEFAULT_SERVER_PORT | Sets a default only if SERVER_PORT is unset |
| BPE_APPEND_PATH | Appends to PATH |
| BPE_PREPEND_PATH | Prepends to PATH |
| BPE_DELIM_PATH | Chooses delimiter for append/prepend operations, e.g., `:` |

Verify exact syntax against your builder's Environment Variables Buildpack version. `BPE` variables are not a universal convention across all CNB builders.

**Do not use `BPE` to embed passwords, access tokens, private keys, or credentials.** Values are written into image layers or related metadata and can be accessed by anyone permitted to read the image. Use them only for non-sensitive defaults such as ports, display modes, or locale.

## 10. Proper Runtime Configuration with Docker

Once the image is created, use `docker run -e` to pass environment variables into the container. This is runtime configuration:

~~~bash
docker run --rm \
  --name demo-orders \
  --publish 8085:8085 \
  --env SERVER_PORT=8085 \
  --env SPRING_PROFILES_ACTIVE=staging \
  --env DEMO_MESSAGE="runtime-value" \
  example/demo-orders:native
~~~

In this example:

- `SERVER_PORT` is read by Spring Boot to configure the port.
- `SPRING_PROFILES_ACTIVE` selects the Spring profile at startup, provided that profile exists in the configuration supported by the image.
- `DEMO_MESSAGE` is a custom variable; the application must declare binding or read the corresponding property for the value to take effect.
- `--publish 8085:8085` maps host port to container port; it does not set `server.port` by itself.

For a native executable, standard environment variables are still provided to the process by the OS. Spring Boot can read them via `Environment`, `@Value`, or `@ConfigurationProperties`, as long as the property and binding code exist in the image.

### Runtime arguments

Some images allow passing additional command arguments at launch. However, how Docker combines arguments with `ENTRYPOINT` and `CMD` depends on the image configuration. Before adding `--server.port=...`, check the image's default process; if the command is replaced instead of appended, you might accidentally bypass the launcher or startup command generated by Buildpacks.

With a native application, there is no JVM launcher accepting HotSpot flags like `java -jar` does. Use standard Spring Boot application arguments and environment variables, or native runtime options verified for your exact GraalVM version.

## 11. Using Docker Compose for Runtime Configuration

You can manage runtime variables in a Compose file:

~~~yaml
services:
  orders:
    image: example/demo-orders:native
    ports:
      - "8085:8085"
    environment:
      SERVER_PORT: "8085"
      SPRING_PROFILES_ACTIVE: "staging"
      DEMO_MESSAGE: "from-compose"
~~~

Run:

~~~bash
docker compose up
~~~

Values under `environment` are supplied to the container at launch. If you change them, you normally do not need to rebuild the image; just recreate the container with the updated config.

For credentials, use Docker secrets or a secret manager appropriate to your platform. Never place secrets into Dockerfiles, build arguments, `BP_*`, `BPE_*`, committed config files, or image layers. In production environments, Kubernetes Secrets, Vault, or a cloud secret manager are generally more appropriate than writing passwords directly into a Compose file.

## 12. Spring Boot Profiles and Structures Processed by AOT

Changing `SPRING_PROFILES_ACTIVE` at runtime can change properties and runtime configurations supported by the packaged application. However, with native images, **you cannot assume a runtime profile will recreate beans that Spring AOT did not include in the image**.

Example:

~~~java
@Configuration(proxyBeanMethods = false)
class StorageConfiguration {

    @Bean
    @Profile("local")
    StorageClient localStorageClient() {
        return new LocalStorageClient();
    }

    @Bean
    @Profile("production")
    StorageClient productionStorageClient() {
        return new RemoteStorageClient();
    }
}
~~~

Suppose the AOT build created an image under an environment that only recognized the `local` configuration. When the container launches with `SPRING_PROFILES_ACTIVE=production`, the `productionStorageClient` bean may be unavailable because the corresponding class/bean-creation path was not included in the image under that AOT configuration.

Distinguish clearly:

| Configuration type | Example | Changeable at runtime? |
|---|---|---|
| Property values of existing beans | Service URL, timeout, port | Usually yes, if the app reads from Spring Environment |
| Profiles affecting bean structure at AOT | `@Profile` creating different beans | Depends on configuration and support; not changeable by default |
| Native Image build argument | BP_NATIVE_IMAGE_BUILD_ARGUMENTS | No; changing requires rebuilding the image |
| Ordinary launch variables | SERVER_PORT, DEMO_MESSAGE | Yes, when recreating the container with new values |

For differing bean sets across environments, design your AOT/build configuration appropriately and test each image. Do not use runtime environment variables to substitute for a required build step.

## 13. How Can Build Arguments Affect Native Results?

`BP_NATIVE_IMAGE_BUILD_ARGUMENTS` passes options directly to the `native-image` compiler. Parameters like optimization level, analysis reports, or build heap settings can alter build time, resource consumption, executable size, or diagnostic behavior.

Illustrative example:

~~~bash
pack build example/demo-orders:native \
  --builder paketobuildpacks/builder-jammy-tiny \
  --path . \
  --env BP_NATIVE_IMAGE=true \
  --env BP_NATIVE_IMAGE_BUILD_ARGUMENTS="-O2"
~~~

These are compiler flags. Do not use them to configure `server.port`, datasource, or Spring profiles. Likewise, `BP_NATIVE_IMAGE_BUILD_ARGUMENTS_FILE` can point to an arguments file in the format supported by `native-image`; the file must exist in the build context where the buildpack can read it.

Some compiler options may not be supported by your current toolkit or version. Always check build logs, the toolkit version in image/SBOM metadata, and matching documentation. Whenever adding flags, record the configuration alongside benchmark measurements so builds remain reproducible.

## 14. Does Changing Build Config Require Rebuilding the Image?

Use the following decision table:

| Change | Rebuild image required? | Reason |
|---|---|---|
| Change BP_NATIVE_IMAGE_BUILD_ARGUMENTS | Yes | Compiler generates a different executable |
| Change builder or run image | Yes | Base image components change |
| Change BP_GRADLE_BUILD_ARGUMENTS and artifact contents | Yes | Input artifact changes |
| Change SERVER_PORT via docker run -e | No | Value is passed at launch |
| Change SPRING_PROFILES_ACTIVE at runtime | No rebuild operationally, yet only works if the image supports that profile structure | Value is supplied at runtime; AOT structure still has limits |
| Change BPE_DEFAULT_SERVER_PORT | Yes | Default launch environment is written into the image |
| Change secret via runtime platform | No | Secret is supplied when container launches |
| Change resources or application code | Yes | Image contents must be updated |

Useful rule: **if a change alters the executable, dependencies, builder layers, or launch metadata baked into the image, you must build a new image. If it only changes runtime data supplied to the container, you can reuse the existing image.**

## 15. Security: Never Package Secrets into the Image

A serious mistake is passing a database password via build variables and accidentally recording it into layers, build logs, caches, or metadata. Images are often stored in registries and pulled across environments; credentials baked into an image are much harder to revoke than a runtime secret.

Do not do this:

~~~bash
# Do not follow: credentials can leak in shell history/logs/layers.
pack build example/demo-orders:native \
  --env BP_DATABASE_PASSWORD=super-secret \
  --env BPE_DEFAULT_SPRING_DATASOURCE_PASSWORD=super-secret
~~~

Supply secrets at runtime through an appropriate platform mechanism. Illustrative example using environment variables (solely to show the flow, not the optimal production secret-management pattern):

~~~bash
docker run --rm \
  --env SPRING_DATASOURCE_URL \
  --env SPRING_DATASOURCE_USERNAME \
  --env SPRING_DATASOURCE_PASSWORD \
  example/demo-orders:native
~~~

Values must be supplied by the runtime environment or secret manager. Never write real passwords in commands, committed scripts, or learning materials.

If a build genuinely needs a secret to download private dependencies, prefer **CNB bindings** or a CI/build-platform secret mechanism supported by the buildpack. Bindings can supply data to the build process without turning it into default application configuration. Binding declaration and access control depend on the platform and buildpack; do not assume every builder handles the same binding types.

## 16. Diagnosing When Configuration Has No Effect

| Symptom | Possible cause | How to check |
|---|---|---|
| Native image is not created | BP_NATIVE_IMAGE not passed at build time, builder lacks native buildpack | Inspect detect/build logs and builder metadata |
| Buildpack ignores BP_NATIVE_IMAGE_BUILD_ARGUMENTS | Misspelled variable or variable didn't reach the build environment | Check `bootBuildImage` config, `pack --env`, and build logs |
| Compiler fails on -O2 or another flag | Invalid flag for the native-image toolkit/version | Check `native-image` version and syntax |
| Changed SERVER_PORT in terminal before pack build, yet container uses old port | Variable existed only at build time and wasn't saved into the image | Set SERVER_PORT when running the container |
| BP_NATIVE_IMAGE=true passed via docker run -e without producing native image | Variable set at the wrong stage | Pass BP_NATIVE_IMAGE to the builder when rebuilding |
| BPE_DEFAULT_SERVER_PORT has no effect | Builder lacks Environment Variables Buildpack or does not accept BPE | Check buildpack list and launch environment |
| BPL_* has no effect on native app | Variable only controls a buildpack-provided runtime component, possibly JVM | Confirm whether the app is native or JVM and which buildpack reads it |
| New profile causes missing bean | Bean graph was processed at AOT under a different environment | Inspect AOT/build profile and beans present in the image |
| Image contains credentials | Embedded secret via BPE or build layer/logs | Revoke/rotate secret, build a clean image, and audit registry/logs/cache |

When debugging, enable `BP_LOG_LEVEL=DEBUG` at build time if supported by the builder's buildpacks. This log level exposes the buildpack process, not Spring Boot's application log level. Build logs may also expose paths, arguments, and environment details; control access to them accordingly.

## 17. Hands-On: Building One Image and Changing Runtime Configuration

Goal: create a single native image, then change its port and profile at runtime without rebuilding.

### Step 1 — Prepare the application

A Spring Boot app with a `/runtime-info` endpoint returning a non-sensitive property:

~~~java
@RestController
class RuntimeInfoController {
    private final Environment environment;

    RuntimeInfoController(Environment environment) {
        this.environment = environment;
    }

    @GetMapping("/runtime-info")
    Map<String, String> info() {
        return Map.of(
            "message", environment.getProperty("demo.message", "unset"),
            "profile", String.join(",", environment.getActiveProfiles())
        );
    }
}
~~~

Assume the project already includes Spring Web, compatible AOT/native configuration, and the endpoint is compiled into the executable.

### Step 2 — Build the image

~~~bash
pack build example/runtime-lab:native \
  --builder paketobuildpacks/builder-jammy-tiny \
  --path . \
  --env BP_NATIVE_IMAGE=true
~~~

Or configure `bootBuildImage.environment` in Gradle and run `./gradlew bootBuildImage`. Record the builder and buildpack versions used.

### Step 3 — Run the same image with the first runtime config

~~~bash
docker run --rm \
  --publish 8081:8081 \
  --env SERVER_PORT=8081 \
  --env SPRING_PROFILES_ACTIVE=staging \
  --env DEMO_MESSAGE=first-run \
  example/runtime-lab:native
~~~

Call the endpoint:

~~~bash
curl http://localhost:8081/runtime-info
~~~

### Step 4 — Rerun the same image with different values

Stop the first container, then run:

~~~bash
docker run --rm \
  --publish 8082:8082 \
  --env SERVER_PORT=8082 \
  --env SPRING_PROFILES_ACTIVE=production \
  --env DEMO_MESSAGE=second-run \
  example/runtime-lab:native
~~~

Call the endpoint on port 8082. Both runs use the **same image** while receiving different runtime configurations. The second profile is valid only if the image was built with a compatible bean structure and code.

### Step 5 — Intentionally mix up stages to observe the difference

Set `SERVER_PORT=8083` before `pack build`, without configuring `BPE` or writing it into launch metadata. After the image is created, run the container without passing `SERVER_PORT`; do not expect the app to automatically use 8083. Then pass `SERVER_PORT=8083` via `docker run -e` and verify the result.

### Observation Table

| Test | Where is the variable set? | Rebuild required? | Expected result |
|---|---|---|---|
| Enable native image | BP_NATIVE_IMAGE at build | Yes | Buildpack builds native executable |
| Change compiler option | BP_NATIVE_IMAGE_BUILD_ARGUMENTS at build | Yes | Compiler runs with new option |
| Change port | SERVER_PORT when running container | No | Spring Boot picks up new port |
| Change profile | SPRING_PROFILES_ACTIVE when running container | Operationally no; depends on AOT structure | Profile activates if supported by image |
| Set launch default | BPE_DEFAULT_SERVER_PORT at build | Yes | Image carries default for launch |
| Change secret | Runtime/platform secret | No | App receives credentials from runtime environment |

## 18. Pre-Release Verification Checklist

Before publishing a native image, review in order:

1. **Verify builder:** builder supports native image, matches target architecture, and is compatible with the run image.
2. **Verify build configuration:** record BP_NATIVE_IMAGE, native-image arguments, build tool arguments, and toolkit version.
3. **Audit sensitive data:** no passwords/tokens in `BP_*`, `BPE_*`, image labels, logs, or build files.
4. **Verify launch configuration:** non-sensitive defaults embedded deliberately; per-environment values supplied via runtime platform.
5. **Verify AOT structure:** beans/profiles/conditionals needed in the target environment are present in the image.
6. **Run smoke tests:** start the image, check health endpoint, port, profile, datasource, and critical business flows.
7. **Record artifact metadata:** image tag/digest, builder, buildpack versions, commit, and build configuration for reproducibility.

Do not rely on the `latest` tag as sole proof of builder version. For release pipelines, pin builder/run images by explicit tag or digest per organizational policy to reduce unexpected changes.

## 19. Rules to Remember

- **BP_* configures image creation**; `BP_NATIVE_IMAGE` enables native image and `BP_NATIVE_IMAGE_BUILD_ARGUMENTS` targets the compiler.
- **BP_GRADLE_* and BP_MAVEN_* control the build tool** inside the build container, not Spring Boot runtime.
- **Runtime variables** like `SERVER_PORT`, `SPRING_PROFILES_ACTIVE`, and `SPRING_DATASOURCE_URL` should be supplied when the container starts.
- **BPL_* and BPE_* are Paketo conventions with specific roles**; check whether the actual buildpack supports them before using.
- **BPE can bake values into the image**; use it only for non-sensitive default settings.
- **Secrets should be supplied via a runtime secret manager or appropriate binding**, avoiding storage in layers, images, logs, and build arguments.
- **Spring AOT decides part of the bean graph at build time**; changing profiles at runtime does not recreate beans excluded from the native image.

### References

- Paketo — How to Configure Buildpacks: https://paketo.io/docs/howto/configuration/
- Paketo — How to Build Java Apps with Buildpacks: https://paketo.io/docs/howto/java/
- Paketo — Java Native Image Buildpack Reference: https://paketo.io/docs/reference/java-native-image-reference/
- Spring Boot Gradle Plugin Reference: https://docs.spring.io/spring-boot/gradle-plugin/packaging.html#packaging.container-images.buildpacks
- Spring Boot Maven Plugin Reference: https://docs.spring.io/spring-boot/maven-plugin/build-image.html

Variable names, default builders, and plugin configuration syntax can change across versions. When applying to a project, check the reference docs for the exact Spring Boot, CNB platform, and Paketo buildpack versions in use.
