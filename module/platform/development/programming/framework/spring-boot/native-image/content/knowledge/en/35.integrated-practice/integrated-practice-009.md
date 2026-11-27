# Building CI with JVM, AOT, Native Testing, and Final Container Verification

## 1. Practice Objectives

In the **SPRING_BOOT_NATIVE_IMAGE** module, a Spring Boot application is processed by Spring AOT and compiled into a GraalVM Native Image to improve startup time, memory usage, and packaging. A pipeline that runs only JVM unit tests does not prove the native executable can start, execute business logic, or run properly inside the released container.

This practice builds a pipeline with sequential verification gates:

1. Run JVM tests to verify application logic and core API contracts.
2. Run Spring AOT to catch invalid configuration conditions and generated code issues.
3. Compile the Native Image to detect reachability, reflection, resource, and native toolchain problems.
4. Run native tests to verify Spring test contexts in the native environment.
5. Package the executable into the final runtime container.
6. Launch that exact image and verify readiness, API behavior, execution permissions, and shutdown.

The CI outcome must be a verified image. Publish/deploy the image by its verified digest—do not rebuild a different image after testing.

## 2. Pipeline Architecture

~~~mermaid
flowchart TD
    A["Checkout source + pinned toolchain"] --> B["JVM unit / integration tests"]
    B -->|Pass| C["Spring AOT processing"]
    C -->|Pass| C2["AOT mode JVM smoke"]
    C2 -->|Pass| D["Native executable compilation"]
    D -->|Pass| E["Native tests"]
    E -->|Pass| F["Package exact native binary"]
    F --> G["Build final OCI image"]
    G --> H["Inspect image and binary"]
    H --> I["Run final container"]
    I --> J["Readiness + API smoke + dependency checks"]
    J --> K["Graceful shutdown + digest"]
    K --> L["Publish / deploy tested digest"]
~~~

Each step validates a different class of risk:

| Gate | Question to Answer | Examples of Detected Failures |
| --- | --- | --- |
| JVM tests | Are logic and contracts correct? | Broken business logic, invalid validation, regressions |
| AOT | Can the ApplicationContext be analyzed at build time? | Environment-dependent conditions, unrecognized beans, broken generated initializers |
| Native compile | Can GraalVM produce an executable? | Missing reachability metadata, resources, JNI/proxy metadata, toolchain |
| Native tests | Do critical test contexts run in native mode? | Reflection/serialization/proxy errors in native execution |
| Container build | Is the binary packaged with appropriate runtime dependencies? | Missing loader, shared libraries, CA certificates, or config files |
| Container verification | Can the final image actually serve requests? | Port, permissions, health, DNS/TLS, signals/shutdown, or runtime config |

Do not collapse everything into a single build command and only check the exit code. Logs and artifacts from each gate pinpoint which layer failed.

## 3. Prepare the Sample Application

Suppose the project is a billing service with:

- REST APIs to create and query invoices;
- request validation and error handling;
- calling a partner API via an HTTP client;
- database access;
- Actuator health endpoints;
- logging and metrics configuration;
- a few libraries requiring reflection or resource hints.

In this example, the executable name is **billing-service** and the HTTP port is **8080**. Substitute endpoints, dependencies, profiles, and artifact names with those of your real application.

### 3.1. Enable Readiness and Liveness

If the application uses Spring Boot Actuator, enable health probes:

~~~yaml
management:
  endpoint:
    health:
      probes:
        enabled: true
~~~

When Actuator is included as a dependency and health endpoints are exposed per project configuration, Spring Boot provides readiness and liveness groups. CI can call:

~~~text
GET /actuator/health/readiness
GET /actuator/health/liveness
~~~

Readiness reports whether the instance is ready to accept traffic. Liveness helps determine whether the process is still alive. Do not include every external dependency in the liveness check; a temporary database or partner API outage should not cause the orchestrator to continuously restart every instance.

If not using Actuator, provide equivalent health/readiness endpoints and update the URLs in the workflow.

### 3.2. Fix Build-Time Configuration

Spring AOT prepares the ApplicationContext at build time. Conditions such as profiles, properties, and classpath may be evaluated before the executable runs.

Record:

- Spring profiles used during AOT processing;
- properties that alter bean conditions;
- JDK/GraalVM versions;
- Spring Boot and Native Build Tools versions;
- native-image arguments;
- OS, CPU architecture, and libc of the build environment;
- resources/hints contributed by the application and dependencies.

Do not let CI run AOT with one profile while the container runs another profile if those two profiles alter the bean graph. Purely runtime settings such as ports, endpoints, secrets, and connection strings should be passed via environment variables or a secret store when the container runs.

## 4. Configure the Build Tool

Choose one build tool per pipeline run. Do not run both Maven and Gradle on the same source inside the same job if the project maintains only one build definition.

### 4.1. Gradle

Apply the Spring Boot plugin and the GraalVM Native Build Tools plugin:

~~~kotlin
plugins {
    id("org.springframework.boot") version "<spring-boot-version>"
    id("io.spring.dependency-management") version "<dependency-management-version>"
    id("org.graalvm.buildtools.native") version "<native-build-tools-version>"
}

graalvmNative {
    binaries {
        named("main") {
            imageName.set("billing-service")
        }
    }
}

tasks.named<org.springframework.boot.gradle.tasks.bundling.BootJar>("bootJar") {
    archiveFileName.set("billing-service.jar")
}
~~~

Replace placeholders with the project's pinned versions. The Spring Boot Gradle plugin automatically configures AOT tasks when the GraalVM Native Image plugin is applied.

Main tasks:

~~~bash
./gradlew test
./gradlew processAot
./gradlew nativeCompile
./gradlew nativeTest
~~~

- **test:** runs JVM tests.
- **processAot:** runs Spring AOT for the application context.
- **nativeCompile:** builds the native executable; the task consumes AOT output and reachability metadata as configured by the plugin.
- **nativeTest:** processes and runs supported Spring TestContext tests in native mode.

With the binary name configured above, the executable is typically located at:

~~~text
build/native/nativeCompile/billing-service
~~~

Confirm the path from Gradle task output; multi-module projects may have different output directories per module.

### 4.2. Maven

If using Spring Boot Starter Parent, add both plugins to the application module:

~~~xml
<build>
    <finalName>billing-service</finalName>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
        <plugin>
            <groupId>org.graalvm.buildtools</groupId>
            <artifactId>native-maven-plugin</artifactId>
            <configuration>
                <imageName>billing-service</imageName>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

The Starter Parent provides the **native** profile to configure Spring AOT and Native Build Tools, as well as the **nativeTest** profile to process test AOT and run native tests.

Main commands:

~~~bash
./mvnw -B clean verify
./mvnw -B -Pnative spring-boot:process-aot
./mvnw -B -Pnative native:compile
./mvnw -B -PnativeTest test
~~~

The executable typically resides in the module's target directory, following the imageName configured for Native Build Tools.

If not using Starter Parent, you must configure the corresponding executions manually, including at minimum the Spring Boot plugin goals for application/test AOT and Native Build Tools goals for native compilation/testing. Do not assume the **native** or **nativeTest** profiles exist when the project does not inherit from the Parent.

### 4.3. Choose the Right Version Set

Do not pick JDK, Spring Boot, GraalVM, and Native Build Tools versions independently from different examples. Check the compatibility matrix and pin:

| Component | What to Pin |
| --- | --- |
| Java | Major version, vendor, and patch/update policy |
| Spring Boot | Version managing Spring Framework and plugins |
| GraalVM | Distribution, JDK version, and Native Image version |
| Native Build Tools | Compatible Maven/Gradle plugin version |
| OS/architecture | Runner image and target image |
| Native dependencies | Compiler, libc baseline, and system libraries |

If upgrading one component, re-run the entire native pipeline and update artifact provenance.

## 5. Gate 1 — JVM Testing

Run JVM tests first because they provide the fastest feedback loop:

Gradle:

~~~bash
./gradlew clean test
~~~

Maven:

~~~bash
./mvnw -B clean verify
~~~

Organize tests by purpose:

| Test Group | Scope |
| --- | --- |
| Unit tests | Services, mappers, validation, and business logic |
| Web slice | Controllers, serialization, and error responses |
| Data slice | Repositories, queries, and mappings |
| Integration tests | Databases, HTTP clients, message brokers, and external adapters |
| Contract tests | Request/response, status codes, and API schemas |

JVM tests do not replace native tests. However, avoid converting every unit test to native because native tests incur compilation time and specific framework constraints. Keep JVM tests broad, and select a subset of Spring TestContext tests and high-risk flows to run in native.

Archive test reports and fail the pipeline on any test failure. Do not proceed to AOT/native builds if the JVM gate has already failed.

## 6. Gate 2 — Spring AOT

### 6.1. Run AOT Separately

Gradle:

~~~bash
./gradlew processAot
~~~

Maven:

~~~bash
./mvnw -B -Pnative spring-boot:process-aot
~~~

The goal of this gate is to catch errors during ApplicationContext analysis before Native Image compilation begins.

### 6.2. Inspect AOT Output

After the task finishes, inspect generated output in the module's build directory. Confirm:

- AOT processing completed successfully;
- generated initializers and generated sources were produced;
- bean conditions reflect build-time profiles/properties;
- custom RuntimeHintsRegistrars were discovered by Spring AOT;
- resource and proxy hints were included in the output;
- no classes or dependencies were dropped from the classpath.

Do not edit generated files directly in the build directory. Fix source configuration, bean declarations, RuntimeHintsRegistrars, or dependencies, then re-run AOT.

### 6.3. Check Build-Time Conditions

Suppose production uses the production profile to create a PartnerClient bean, while CI runs AOT with the default profile. If the bean graphs differ, the executable may lack the bean needed in production.

Fix:

1. Identify properties/profiles that alter conditions.
2. Choose build-time configuration deliberately.
3. Pass that configuration into the AOT command or plugin configuration.
4. Inspect the generated context.
5. Run the container with valid runtime configuration and verify the required bean works.

Do not supply real secrets to AOT processing. Use dummy values or non-sensitive configuration for conditions that must be evaluated at build time.

### 6.4. Run the AOT-Generated Application on the JVM

Spring Boot allows launching a JAR containing AOT-generated code on the JVM using the `spring.aot.enabled=true` system property. This serves as a fast verification step before native compilation: it tests generated initializers and the AOT ApplicationContext without waiting for native compilation.

Gradle, after building the JAR with the Native Image plugin applied:

~~~bash
./gradlew bootJar
java -Dspring.aot.enabled=true -jar build/libs/billing-service.jar
~~~

Maven, building the package with the native profile to run process-aot:

~~~bash
./mvnw -B -Pnative package
java -Dspring.aot.enabled=true -jar target/billing-service.jar
~~~

In another terminal, call readiness and a business API just as when testing a container. Stop the process with SIGTERM. The JAR must genuinely contain AOT-generated classes/resources; otherwise, that property cannot verify AOT output.

## 7. Gate 3 — Native Image Compilation

### 7.1. Compile with Native Build Tools

Gradle:

~~~bash
./gradlew nativeCompile
~~~

Maven:

~~~bash
./mvnw -B -Pnative native:compile
~~~

Native Image compilation can consume significant CPU and RAM. The runner must be provisioned with adequate resources; if the build is killed, check memory limits and compiler logs before changing source code.

### 7.2. Errors to Resolve at the Native Gate

| Error | Area to Inspect |
| --- | --- |
| Missing reflection registration | RuntimeHints, dependency reachability metadata, and dynamic call sites |
| Missing proxy registration | JDK proxy interface lists or Spring AOT proxy generation |
| Serialization registration | Java serialization metadata or JSON/XML binding hints |
| Missing JNI registration | Native code accessing undeclared classes/members |
| Missing resource | Resource hints and resource patterns |
| Unsupported feature | Libraries using dynamic class loading, threads, or unsupported APIs |
| Native library/linker failure | OS, architecture, libc, compiler, and shared libraries |

Prefer reachability metadata supplied by the framework or dependencies. Only add custom hints once you identify the call site and dynamic access type. The Tracing Agent can help collect metadata, but it must exercise the required business flows and its output must be reviewed.

### 7.3. Inspect the Executable

After building, verify:

~~~bash
file build/native/nativeCompile/billing-service
ldd build/native/nativeCompile/billing-service
~~~

The example above assumes a Linux binary dynamically linked against glibc. If using fully static musl, inspect with appropriate ELF tools; ldd may report that the binary is not dynamically linked.

For a dynamic binary, check:

- matching architecture;
- dynamic loader exists;
- no dependencies report not found;
- glibc symbol versions are compatible with the runtime image;
- CA certificates and external resources outside the executable are provided.

Do not run an x86-64 binary in an ARM64 image or a glibc binary in a musl runtime merely because the Docker build succeeded.

### 7.4. Run the Executable Directly Before Packaging

Start the binary on the runner or a compatible Linux environment:

~~~bash
./build/native/nativeCompile/billing-service
~~~

In another terminal, call readiness and a business API. Stop with SIGTERM and verify the application shuts down cleanly.

This is a quick smoke test for the executable. It still does not replace running inside the final container, because containers have their own filesystem, user, network namespace, and shared libraries.

## 8. Gate 4 — Native Tests

### 8.1. Gradle nativeTest

~~~bash
./gradlew nativeTest
~~~

The Spring Boot Gradle plugin configures AOT test tasks when the GraalVM Native Image plugin is applied. The nativeTest task executes tests using the Spring TestContext Framework in native mode within its supported scope.

### 8.2. Maven nativeTest

~~~bash
./mvnw -B -PnativeTest test
~~~

The nativeTest profile provided by Spring Boot Starter Parent processes test AOT and invokes Native Build Tools to run native tests. Projects not using the Parent must configure the corresponding executions.

### 8.3. Which Tests Should Run in Native?

Prioritize tests covering closed-world analysis risks:

- Spring ApplicationContext initialization with critical profiles;
- controllers serializing/deserializing requests and responses;
- HTTP clients using DTOs or custom codecs;
- reflection, proxies, serialization, and resource lookups;
- security/transaction/async advice;
- database drivers, JNI, or native libraries;
- critical message listeners and scheduled jobs.

Do not assume every JUnit test runs automatically in native. Spring AOT test support focuses on tests using the Spring TestContext Framework; incompatible test frameworks or extensions must be handled separately.

### 8.4. Archive Native Test Results

Keep nativeTest reports/logs and record:

- which test classes underwent AOT processing;
- pass/fail/skip test counts;
- GraalVM/JDK versions;
- native test executable build options;
- compilation time and execution time.

If nativeTest fails while JVM tests pass, preserve the stack trace and determine whether the failure lies in test AOT, native compilation, or test runtime. Never skip native tests simply because JVM tests are green.

## 9. Gate 5 — Package the Container from the Verified Executable

Pipelines have two common ways to build a native image. Choose one approach per release.

### 9.1. Approach A: Package the Built Binary with a Dockerfile

This approach fits when you want explicit control over the runtime image and want to guarantee the binary inside the image is the exact artifact just tested.

After nativeCompile, copy the executable into the build context:

Gradle:

~~~bash
mkdir -p docker/app
cp build/native/nativeCompile/billing-service docker/app/billing-service
chmod 0755 docker/app/billing-service
~~~

Maven, substituting the actual output path from Native Build Tools:

~~~bash
mkdir -p docker/app
cp target/billing-service docker/app/billing-service
chmod 0755 docker/app/billing-service
~~~

Example Dockerfile for a dynamic glibc executable built on an Ubuntu 24.04 runner:

~~~dockerfile
FROM ubuntu:24.04

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       ca-certificates \
       libstdc++6 \
       zlib1g \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY docker/app/billing-service /app/billing-service

USER 10001:10001
EXPOSE 8080
ENTRYPOINT ["/app/billing-service"]
~~~

This example uses the same Ubuntu 24.04 baseline for runner and runtime. Adjust the package list according to the binary's ldd output; do not guess extra libraries. If building on a different baseline, choose a runtime image compatible with the glibc symbol versions and shared libraries required by the executable. For release pipelines, pin the base image by digest rather than solely by tag for image reproducibility.

If the binary is fully static musl and verified to need no shared libraries, you can use a scratch runtime image. In that case, copy any CA bundle, timezone data, or external resources needed by the application. Static linking does not automatically embed those system files.

### 9.2. Check Dependencies Before Building the Image

For a dynamic binary, run:

~~~bash
ldd docker/app/billing-service
~~~

If the output shows not found, add the right runtime package or fix the build environment. Never release an image simply because docker build succeeded; the dynamic loader is only invoked when the container starts.

Inspect further:

~~~bash
file docker/app/billing-service
readelf -l docker/app/billing-service
readelf -d docker/app/billing-service
~~~

PT_INTERP shows the dynamic loader; DT_NEEDED lists required shared libraries. Use that information to pick the runtime image.

### 9.3. Build the Image

~~~bash
docker build --pull -f docker/Dockerfile.native \
  -t billing-service:ci .
~~~

Never embed secrets in Docker build arguments or image layers. Runtime secrets must be injected via a secret manager/orchestrator when the container runs.

### 9.4. Approach B: Use Cloud Native Buildpacks

Spring Boot supports building native OCI images using Buildpacks.

Maven with Spring Boot Starter Parent and Native Build Tools plugin:

~~~bash
./mvnw -B -Pnative spring-boot:build-image
~~~

Gradle with the GraalVM Native Image plugin applied:

~~~bash
./gradlew bootBuildImage
~~~

Spring Boot plugins integrate AOT and Native Image into the buildpack lifecycle. Buildpacks use a builder/run image to produce the OCI image; no custom runtime Dockerfile is needed for standard cases.

With Spring Boot 4.2 and current Buildpacks, the builder uses a GraalVM Native Image matching the JDK used for compilation and requires at least JDK 25. Check the requirements of your pinned Spring Boot/buildpack version; do not infer the buildpack JDK from the container's runtime JDK.

In the Buildpacks branch, build-image/bootBuildImage performs native compilation inside the builder. If you choose this branch, do not also run nativeCompile only to build another executable and discard it. Still keep nativeTest as a separate test gate before building the image.

Pin the builder/run images by project-verified version or digest. In multi-module Maven projects, activate build-image only on the application module and configure the root POM lifecycle to match the project structure.

### 9.5. Comparing the Two Packaging Approaches

| Criterion | Dockerfile with Pre-Built Binary | Buildpacks |
| --- | --- | --- |
| Where native compilation runs | Native Build Tools on CI runner/build container | Inside the builder |
| Runtime image | Chosen and managed by development team | Run image chosen by Buildpack |
| Binary control | Easy to verify binary hash between nativeCompile and image | Buildpack owns lifecycle and layers |
| Toolchain | CI must install compatible GraalVM/compiler | Builder provides toolchain via buildpack |
| OS package customization | Directly in Dockerfile | According to builder/buildpack capabilities |
| Cache | Build tool cache and Docker layer cache | CNB build/launch cache |

Choose the approach matching your organization's container standards. In either case, the final gate must still run the exact image that was built.

## 10. Gate 6 — Final Container Verification

### 10.1. Inspect Image Metadata

After building:

~~~bash
docker image inspect billing-service:ci
~~~

Confirm:

- image architecture matches the target;
- entrypoint invokes the native executable;
- user is non-root;
- ports/container environment are correct;
- image has labels and digest for traceability;
- no secrets or unnecessary build/test files are present.

With the example Dockerfile, check the user:

~~~bash
docker image inspect \
  --format '{{.Config.User}} {{.Config.Entrypoint}}' \
  billing-service:ci
~~~

Expected output has user 10001:10001 and entrypoint /app/billing-service.

### 10.2. Verify the Binary Inside the Image Is the One Just Built

With the Dockerfile approach, you can extract the executable from the image to compare:

~~~bash
docker create --name billing-image-check billing-service:ci
docker cp billing-image-check:/app/billing-service build/container-billing-service
docker rm billing-image-check
cmp docker/app/billing-service build/container-billing-service
~~~

If cmp succeeds, the file in the image is byte-for-byte identical to the staged executable. If using Buildpacks, the executable path depends on the image layout; use a builder-appropriate check or verify the image's provenance/SBOM.

### 10.3. Start the Container

~~~bash
docker run -d \
  --name billing-service-check \
  -p 18080:8080 \
  billing-service:ci
~~~

Wait for readiness:

~~~bash
curl --fail http://127.0.0.1:18080/actuator/health/readiness
~~~

Then invoke at least one business API:

~~~bash
curl --fail \
  -H 'Content-Type: application/json' \
  -d '{"customerId":"customer-001","amount":125000}' \
  http://127.0.0.1:18080/api/invoices
~~~

The payload and endpoint are examples. Substitute the actual contract and verify response body, status code, database writes, or downstream dependency calls.

### 10.4. Verify Liveness, Dependencies, and Runtime Configuration

Check:

- readiness/liveness endpoints;
- database connections and reconnection;
- partner API DNS/TLS/certificates;
- runtime environment variables;
- mounted configuration and secrets;
- logs emitted to stdout/stderr;
- metrics endpoints if enabled;
- timezone/locale if business logic depends on them.

Do not treat container startup alone as sufficient. The container must handle the dependencies and configuration that production will supply.

### 10.5. Verify Graceful Shutdown

Send SIGTERM via Docker:

~~~bash
docker stop --time 30 billing-service-check
docker logs billing-service-check
~~~

Confirm the Spring lifecycle stops cleanly, connection pools close, and message listeners stop consuming according to policy. If the application needs time to drain requests, align the shutdown timeout with the orchestrator's termination grace period.

## 11. Sample GitHub Actions Workflow with Gradle and Dockerfile

The following workflow illustrates Linux x86-64, GraalVM Community JDK 25, Gradle, and Ubuntu 24.04 runtime. Pin versions according to your project's verified matrix; adjust executable names, endpoints, and profiles to match your application. If the project uses a different Spring Boot/GraalVM release, select a JDK supported by that version pair.

~~~yaml
name: Spring Boot Native CI

on:
  push:
    branches: [main]
  pull_request:

permissions:
  contents: read

jobs:
  native-container:
    runs-on: ubuntu-24.04
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-java@v6
        with:
          distribution: graalvm-community
          java-version: '25'

      - uses: gradle/actions/setup-gradle@v6

      - name: Verify toolchain
        run: |
          java --version
          native-image --version
          docker version

      - name: JVM tests
        run: ./gradlew clean test

      - name: Spring AOT
        run: ./gradlew processAot

      - name: AOT mode JVM smoke
        run: |
          set -eu
          ./gradlew bootJar
          java -Dspring.aot.enabled=true -jar build/libs/billing-service.jar > build/aot-jvm.log 2>&1 &
          app_pid=$!
          cleanup() {
            kill -TERM "$app_pid" 2>/dev/null || true
            wait "$app_pid" || true
          }
          trap cleanup EXIT

          ready=false
          for attempt in $(seq 1 60); do
            if curl --fail --silent \
              http://127.0.0.1:8080/actuator/health/readiness >/dev/null; then
              ready=true
              break
            fi
            sleep 2
          done

          if [ "$ready" != true ]; then
            cat build/aot-jvm.log
            exit 1
          fi
          ./scripts/smoke-test.sh http://127.0.0.1:8080

      - name: Native compilation
        run: ./gradlew nativeCompile

      - name: Native tests
        run: ./gradlew nativeTest

      - name: Stage native executable
        run: |
          mkdir -p docker/app
          cp build/native/nativeCompile/billing-service docker/app/billing-service
          chmod 0755 docker/app/billing-service

      - name: Check native dependencies
        run: |
          set -eu
          file docker/app/billing-service
          ldd docker/app/billing-service | tee build/native-dependencies.txt
          if grep -q "not found" build/native-dependencies.txt; then
            echo "A native shared library is missing"
            exit 1
          fi

      - name: Build final container
        run: |
          docker build --pull \
            -f docker/Dockerfile.native \
            -t billing-service:$GITHUB_SHA .

      - name: Verify image user and entrypoint
        run: |
          docker image inspect \
            --format '{{.Config.User}} {{.Config.Entrypoint}}' \
            billing-service:$GITHUB_SHA
          test "$(docker image inspect --format '{{.Config.User}}' billing-service:$GITHUB_SHA)" = "10001:10001"

      - name: Verify binary copied into image
        run: |
          docker create --name billing-image-check billing-service:$GITHUB_SHA
          docker cp billing-image-check:/app/billing-service build/container-billing-service
          docker rm billing-image-check
          cmp docker/app/billing-service build/container-billing-service

      - name: Run final container smoke tests
        run: |
          set -eu
          name=billing-service-check
          image=billing-service:$GITHUB_SHA
          cleanup() {
            docker logs "$name" || true
            docker rm -f "$name" >/dev/null 2>&1 || true
          }
          trap cleanup EXIT

          docker run -d --name "$name" -p 18080:8080 "$image"

          ready=false
          for attempt in $(seq 1 60); do
            if curl --fail --silent \
              http://127.0.0.1:18080/actuator/health/readiness >/dev/null; then
              ready=true
              break
            fi
            sleep 2
          done

          if [ "$ready" != true ]; then
            echo "Container did not become ready"
            exit 1
          fi

          curl --fail http://127.0.0.1:18080/actuator/health/liveness
          ./scripts/smoke-test.sh http://127.0.0.1:18080

          docker stop --time 30 "$name"
~~~

The workflow uses scripts/smoke-test.sh to invoke the project's business APIs. The script must fail if response status/body or side effects are wrong. If this script does not exist yet, create a test command matching the API contract; do not replace it with a single health request.

### 11.1. Why Does the Workflow Check the Binary Hash?

Native tests run their own test executable. NativeCompile builds the application executable. The container build must copy the exact executable from nativeCompile. Comparing the file inside the image catches a Dockerfile accidentally copying a stale binary or a file from another directory.

### 11.2. Maven Variant

Keep the container verification steps unchanged, and replace the setup/build steps with Maven commands:

~~~bash
./mvnw -B clean verify
./mvnw -B -Pnative spring-boot:process-aot
./mvnw -B -Pnative native:compile
./mvnw -B -PnativeTest test
~~~

Stage the executable from the module's target directory:

~~~bash
mkdir -p docker/app
cp target/billing-service docker/app/billing-service
chmod 0755 docker/app/billing-service
~~~

Ensure the native plugin sets imageName to billing-service or adjust the staging path to the actual artifact.

## 12. Alternative Workflow: Use Buildpacks to Create the Native Image

If your organization uses Cloud Native Buildpacks, you can streamline native compilation and container packaging:

Maven:

~~~bash
./mvnw -B clean verify
./mvnw -B -PnativeTest test
./mvnw -B -Pnative spring-boot:build-image \
  -Dspring-boot.build-image.imageName=billing-service:ci
~~~

Gradle:

~~~bash
./gradlew clean test
./gradlew nativeTest
./gradlew bootBuildImage
~~~

Set the Gradle image name explicitly so CI verifies the exact artifact:

~~~kotlin
tasks.named<org.springframework.boot.gradle.tasks.bundling.BootBuildImage>("bootBuildImage") {
    imageName.set("billing-service:ci")
}
~~~

With Gradle, the org.graalvm.buildtools.native plugin must be applied so the Spring Boot plugin builds a native image. With Maven, use Spring Boot Starter Parent and the Native Build Tools plugin so the native/nativeTest profiles are configured.

Buildpacks run AOT/native compilation inside the image build lifecycle. If you want to inspect AOT output beforehand, run processAot as an extra check gate; avoid adding nativeCompile to the same pipeline only to produce an unused executable.

After building the image, run the same container verification steps: inspect image, verify readiness, run API smoke tests, check dependencies, inspect logs, and test shutdown.

## 13. Maven and Gradle in Multi-Module Projects

In a multi-module build, only the module containing the Spring Boot application needs to produce an executable and OCI image. Library modules still need JVM tests and dependency outputs.

Maven:

- run verify at the root to test all modules;
- enable the native profile on the application module or configure the root profile selectively;
- ensure process-aot runs after dependency modules have been compiled/packaged;
- run spring-boot:build-image only on the application module.

Gradle:

- keep the Spring Boot and Native Build Tools plugins in the application module;
- library modules supply classpath and test outputs;
- invoke nativeCompile/nativeTest tasks using the application module path;
- do not apply the native plugin to every library module if no native executable is built there.

If using a task path such as :billing-service:nativeCompile, the artifact resides in that module's build directory. The workflow must stage the exact file from that module.

## 14. Partitioning CI by Architecture and Environment

A native executable is a target-platform-specific artifact. If releasing for x86-64 and ARM64:

- run native builds on runners/VMs of the matching architecture or use GraalVM-supported cross-compilation;
- build an image for each architecture;
- partition build caches by OS, architecture, libc, and toolchain;
- run container tests on the matching runtime architecture;
- create the manifest list after every per-arch image has passed.

Do not take an x86-64 executable and tag it ARM64. Likewise, do not run an image built on glibc inside Alpine/musl without building and testing for that exact ABI.

Separate configurations:

| Environment | Configuration |
| --- | --- |
| Pull request | Tests, AOT, native compile/test, and container smoke; no permission to publish to production |
| Main branch | Re-run gates, produce image with provenance, and record digest |
| Release tag | Use approved source commit, publish image by version and digest |
| Deployment | Pull the exact tested digest; inject secrets/runtime config from the deployment platform |

Do not rebuild an image after testing and publish a new image under the same tag. The digest is the immutable content identifier of the image.

## 15. Analyzing Failures by Gate

| Failing Gate | Evidence to Collect | First Action |
| --- | --- | --- |
| JVM tests | Test reports, stack traces, dependency versions | Fix regressions/logic before proceeding |
| AOT | Generated output, condition evaluation, AOT logs | Check profiles/properties and bean definitions |
| Native compile | Native-image logs, reachability report, toolchain | Classify reflection/proxy/resource/JNI or linker error |
| Native tests | Native test report, runtime exception | Reproduce the exact Spring TestContext and call path |
| Docker build | Build log, Dockerfile, binary dependency list | Check build context, copy paths, and runtime packages |
| Container start | Container logs, exit code, image config | Check loader, shared libraries, permissions, and port |
| Readiness | Health response and application logs | Check startup, profile, and dependency availability |
| API smoke | Request/response, downstream logs, and database state | Check contract, runtime config, and network |
| Shutdown | Exit code, shutdown logs, and timeout | Check SIGTERM handling and lifecycle hooks |

Do not edit reachability metadata if the real failure is a missing shared library or wrong architecture. Do not swap the runtime image when the error is a Spring bean excluded by an AOT condition. Classifying by gate directs you to the true root cause.

## 16. Archiving Pipeline Artifacts and Evidence

Each native build should archive:

- JVM test reports;
- AOT/native build logs;
- native test reports;
- executable checksum;
- GraalVM/JDK/Spring Boot/Native Build Tools versions;
- ldd/ELF dependency report if the binary is dynamic;
- Dockerfile or builder/run image digests;
- OCI image digest and SBOM/provenance if supported by the pipeline;
- readiness/API smoke results;
- container logs and shutdown outcome.

Never archive secrets, tokens, or sensitive runtime config files as artifacts. Apply retention policies matching audit and storage requirements.

## 17. Pipeline Completion Checklist

- [ ] JVM unit/integration tests run before the native build.
- [ ] GraalVM/JDK, Spring Boot, and Native Build Tools versions are pinned.
- [ ] Spring AOT runs with defined build-time profiles/properties.
- [ ] Generated AOT output is inspected when diagnosing issues.
- [ ] Native executable compiles cleanly for the target OS/architecture.
- [ ] Native tests run critical Spring TestContexts.
- [ ] Reflection/proxy/serialization/resource/JNI hints are verified via business flows.
- [ ] Executable is checked with file/ELF tools and shared-library report.
- [ ] Runtime image matches libc and shared library dependencies.
- [ ] CA certificates and required runtime resources are present.
- [ ] Container runs as a non-root user.
- [ ] Image entrypoint invokes the native executable.
- [ ] Binary inside the image matches the staged binary or has matching provenance.
- [ ] Readiness and liveness pass in the final container.
- [ ] API smoke/integration tests pass with required dependencies.
- [ ] Graceful shutdown completes within the timeout.
- [ ] Image digest is recorded and used for publish/deploy.
- [ ] Pull requests lack permissions to write release caches or publish production artifacts.

**Remember:** JVM tests verify logic, AOT verifies the ApplicationContext can be prepared at build time, native compile verifies the executable can be built, native tests verify critical test contexts run in native, and container verification confirms the exact released image starts and processes business traffic in real runtime conditions. Publish the image digest only after all required gates pass.

## References

- [Spring Boot — Testing GraalVM Native Images](https://docs.spring.io/spring-boot/how-to/native-image/testing-native-applications.html): nativeTest with Maven/Gradle and Spring TestContext scope.
- [Spring Boot — Developing Your First GraalVM Native Application](https://docs.spring.io/spring-boot/how-to/native-image/developing-your-first-application.html): native executables and container images with Buildpacks.
- [Spring Boot Maven Plugin — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/maven-plugin/aot.html): process-aot, process-test-aot, and native/nativeTest profiles.
- [Spring Boot Gradle Plugin — Ahead-of-Time Processing](https://docs.spring.io/spring-boot/gradle-plugin/aot.html): processAot, processTestAot, and nativeCompile/nativeTest tasks.
- [GraalVM Native Build Tools — Maven Plugin](https://graalvm.github.io/native-build-tools/latest/maven-plugin.html): imageName, native:compile, native:test, and plugin configuration.
- [Spring Boot Maven Plugin — Packaging OCI Images](https://docs.spring.io/spring-boot/maven-plugin/build-image.html): building images with Cloud Native Buildpacks.
- [Spring Boot Gradle Plugin — Packaging OCI Images](https://docs.spring.io/spring-boot/gradle-plugin/packaging-oci-image.html): bootBuildImage and native image integration.
- [GraalVM — setup-graalvm GitHub Action](https://github.com/graalvm/setup-graalvm): provisioning GraalVM JDK and native-image toolchain in CI.
- [GitHub Actions — setup-java](https://github.com/actions/setup-java): installing JDK/GraalVM distributions and dependency caching in workflows.
