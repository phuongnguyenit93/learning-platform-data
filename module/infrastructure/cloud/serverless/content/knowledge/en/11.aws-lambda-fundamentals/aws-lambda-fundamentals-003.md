# Packaging Lambda with ZIP, JAR, Layers, and Container Images

In the **AWS Lambda Fundamentals** chapter, packaging is the step that turns Java code and its dependencies into an artifact that Lambda can download, initialize, and execute. The artifact must contain the right classes, libraries, configuration resources, and handler details. If a dependency is missing, the directory structure is wrong, or the runtime/CPU architecture is incompatible, the function may deploy successfully yet fail immediately at initialization.

AWS Lambda supports two main deployment package types: **ZIP deployment package** and **container image**. With Java, a ZIP package can be organized as a standalone JAR or classes plus dependency JARs; a **Lambda layer** supplements a ZIP package with shared libraries or components. A container image packages both the runtime and the application in OCI/Docker format. JARs and layers are therefore ways to organize content or reuse libraries within the ZIP ecosystem, whereas a container image is a distinct deployment package type.

This lesson belongs to the **CLOUD_SERVERLESS** module and focuses on developing and deploying serverless applications, especially Java functions triggered by HTTP, messages, or events. When choosing a packaging approach, consider build time, artifact size, dependencies, cold starts, security, registry access permissions, updatability, and operational cost.

## 1. Components of a Java Lambda Package

A Java function typically requires the following components:

- **Application classes:** compiled classes containing handlers, use cases, domain models, and adapters.
- **Dependencies:** external libraries such as Jackson, JDBC drivers, SDKs, or frameworks.
- **Resources:** configuration files, templates, schemas, or static data needed at runtime.
- **Handler configuration:** the class and method names invoked by the Lambda runtime.
- **Runtime:** the Java environment and corresponding Lambda Runtime Interface.
- **Native libraries:** binary libraries if the application depends on native code; must be compatible with Linux and the function's CPU architecture.

The process can be visualized as follows:

~~~mermaid
flowchart LR
    SRC["Java source"] --> BUILD["Maven / Gradle"]
    BUILD --> CLS["Compiled classes"]
    BUILD --> DEP["Runtime dependencies"]
    CLS --> PKG["Package assembly"]
    DEP --> PKG
    RES["Resources / config"] --> PKG
    PKG --> ZIP["ZIP / JAR artifact"]
    PKG --> IMG["Container image"]
    ZIP --> LAMBDA["AWS Lambda"]
    IMG --> LAMBDA
~~~

The Lambda runtime downloads the artifact, sets up the classpath, and initializes the handler. When the function is invoked, the runtime passes the event to the handler. Packaging must therefore ensure that the handler and all classes it uses can be located on the classpath.

## 2. Distinguishing ZIP, JAR, Lambda Layers, and Container Images

| Packaging approach | Main contents | Best suited for |
|---|---|---|
| ZIP deployment package | Classes, resources, dependency JARs, and directory structure | Common approach for Java Lambda; easy to deploy with AWS tools |
| JAR deployment package | Java archive containing classes, resources, and possibly dependencies | Convenient for compact Java apps or uber JARs |
| Lambda layer | Separate ZIP containing shared libraries or components | Sharing dependencies across multiple ZIP functions |
| Container image | Linux image containing runtime, application, and dependencies | Need for custom packaging environment, container tooling, or large dependencies |

**ZIP and JAR** are archives based on the ZIP format. JAR follows Java conventions such as manifests and class hierarchy. You can deploy a Java Lambda using a JAR or ZIP; if using ZIP, ensure classes and libraries sit where the runtime can load them.

A **Lambda layer** is not a standalone deployment package type replacing ZIP. A layer is attached to a ZIP function to supply additional libraries or shared components. The function still has its own deployment package.

A **container image** is a different package type. Lambda pulls the image from Amazon Elastic Container Registry (Amazon ECR), launches the container via the Lambda Runtime API, and executes the configured handler.

Be sure to distinguish a **Lambda layer** from a **Docker image layer**. A Lambda layer is an archive attached to the function configuration and extracted into `/opt`. A Docker image layer is an immutable filesystem layer created during image builds under the OCI/Docker mechanism.

## 3. Choosing a Java Handler and Runtime

The handler is the entry point the Lambda runtime invokes when the function receives an invocation. With Java, you can implement a handler using an interface or method signature supported by the runtime.

Example handler using RequestHandler:

~~~java
package com.example.orders;

import com.amazonaws.services.lambda.runtime.Context;
import com.amazonaws.services.lambda.runtime.RequestHandler;

public class OrderHandler
        implements RequestHandler<OrderEvent, OrderResult> {

    @Override
    public OrderResult handleRequest(
            OrderEvent event,
            Context context) {

        context.getLogger().log(
                "Processing order " + event.orderId());

        return new OrderResult(event.orderId(), "ACCEPTED");
    }
}
~~~

Illustrative DTOs:

~~~java
package com.example.orders;

public record OrderEvent(String orderId, String customerId) {
}

public record OrderResult(String orderId, String status) {
}
~~~

For a handler implementing RequestHandler, the handler configuration is usually the fully qualified class name, for example **com.example.orders.OrderHandler**. For POJO-style handler methods, you can configure **package.Class::method**. Follow the exact convention used by your Java runtime and framework.

When creating a function, choose a Java runtime supported by AWS Lambda at deployment time. The list of runtimes is updated according to AWS's support lifecycle; do not copy an old Java version from an example without verifying its current support status. The runtime must be compatible with the application's bytecode, libraries, and native dependencies.

## 4. Packaging Java Lambda with JAR

### 4.1. Thin JAR and Uber JAR

There are two common ways to organize a JAR:

- **Thin JAR:** contains only the application's classes and resources. Dependencies are placed separately, for example in a `lib` directory.
- **Uber JAR / fat JAR:** contains the application's classes along with dependency contents merged into a single archive.

A thin JAR yields a smaller application artifact and keeps dependencies separate. An uber JAR is convenient for single-file deployment, but duplicate-named resources, service providers, and library signatures must be handled carefully.

If uploading a JAR directly as the deployment package, that JAR must contain all required dependencies (typically an uber JAR), or the function must receive dependencies via a compatible layer. A standalone thin JAR does not carry external Maven/Gradle libraries by itself.

Do not assume every JAR produced by Maven or Gradle contains all dependencies. The default JAR may contain only project classes. Inspect the archive contents before uploading.

### 4.2. Creating an Uber JAR with the Maven Shade Plugin

Example plugin configuration in `pom.xml`:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-shade-plugin</artifactId>
      <version>3.6.0</version>
      <executions>
        <execution>
          <phase>package</phase>
          <goals>
            <goal>shade</goal>
          </goals>
          <configuration>
            <createDependencyReducedPom>false</createDependencyReducedPom>
            <transformers>
              <transformer implementation=
                "org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
            </transformers>
            <filters>
              <filter>
                <artifact>*:*</artifact>
                <excludes>
                  <exclude>META-INF/*.SF</exclude>
                  <exclude>META-INF/*.DSA</exclude>
                  <exclude>META-INF/*.RSA</exclude>
                </excludes>
              </filter>
            </filters>
          </configuration>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
~~~

Build:

~~~bash
mvn clean package
~~~

The Maven Shade Plugin produces a dependency-merged JAR in the `target` directory according to the project's artifact configuration. The services resource transformer merges Service Provider Interface (SPI) registration files when multiple dependencies declare providers. The signature filter excludes old signature files because the JAR contents have been repackaged; do not remove or bypass signature verification mechanisms required by other project security policies.

If using libraries with overlapping configuration or resource filenames, check how the plugin merges them. Merging JARs does not automatically resolve every dependency conflict.

### 4.3. Creating a JAR with Gradle

With Gradle, you can use the Shadow plugin to create an uber JAR. Declare the plugin and configure its version according to your project's dependency policy, then run:

~~~bash
./gradlew clean shadowJar
~~~

The artifact is typically generated under `build/libs`. Verify the filename, manifest if needed by the application, service resources, and configuration files before deploying.

### 4.4. When to Use a JAR?

A JAR is suitable when:

- The Java function has a straightforward structure.
- You want a single artifact that is easy to store, sign, inspect, and promote across environments.
- Dependencies are not overly large or can be merged into an uber JAR.
- OS-level control via a container image is unnecessary.

A JAR does not reduce dependency size automatically. An uber JAR can be larger than a thin JAR because it bundles all libraries. Measure size and verify the classpath instead of relying solely on the file extension.

## 5. Packaging ZIP with Separate Classes and Dependencies

A Java ZIP package can hold application classes at the root directory and dependency JARs in the `lib` directory.

Illustrative structure:

~~~text
function.zip
├── com/
│   └── example/
│       └── orders/
│           ├── OrderHandler.class
│           ├── OrderEvent.class
│           └── OrderResult.class
├── application.properties
└── lib/
    ├── jackson-databind.jar
    ├── jackson-core.jar
    ├── jackson-annotations.jar
    └── aws-lambda-java-core.jar
~~~

The Lambda Java runtime looks for classes in packages and dependency JARs at prescribed classpath locations. For a standard Java ZIP, place dependency JARs in a `lib` folder at the root of the archive.

A general Maven workflow:

~~~bash
mvn clean package
mvn dependency:copy-dependencies \
  -DincludeScope=runtime \
  -DoutputDirectory=target/dependency

mkdir -p target/lambda/lib
cp -R target/classes/. target/lambda/
cp target/dependency/*.jar target/lambda/lib/
(cd target/lambda && zip -r ../function.zip .)
~~~

The copy and zip commands above use Unix-style shell syntax. On Windows PowerShell, substitute the corresponding directory creation and copy commands; the internal structure of the ZIP must remain identical.

If using an uber JAR, you can deploy the JAR archive as a Java package or place the JAR under `lib` inside a ZIP package. Do not create a ZIP with an extra unnecessary parent folder, such as an archive containing the whole `target/function` directory rather than the function contents. The runtime needs to see the classpath at the right directory level.

### 5.1. Inspecting ZIP Contents

Before uploading, verify:

- The handler class exists in the right package.
- Dependencies needed at runtime are inside the archive.
- Resources are packaged at the path the application reads from.
- Test files, source code, or unnecessary build caches are not accidentally packaged.
- No credentials, secrets, or local environment files are included.
- No conflicting dependency versions exist.
- The ZIP does not have an unintended extra root folder layer.

You can list the files with:

~~~bash
unzip -l target/function.zip
~~~

If `unzip` is unavailable, use the `jar` command or an equivalent archive tool to inspect the contents. Being able to open the archive does not prove the handler can load; include a classpath verification step or smoke test.

## 6. Deploying ZIP/JAR to AWS Lambda

When creating a function, select package type Zip, an appropriate Java runtime, handler, execution role, and archive file. Illustrative AWS CLI example:

~~~bash
aws lambda create-function \
  --function-name order-handler \
  --runtime java21 \
  --handler com.example.orders.OrderHandler \
  --role arn:aws:iam::123456789012:role/lambda-execution-role \
  --zip-file fileb://target/function.zip
~~~

The runtime name in the example must be confirmed as still supported by AWS at deployment time. The role ARN is an illustrative value; replace it with the actual execution role carrying least-privilege permissions.

With Java, you can directly upload a fully packaged JAR via `--zip-file`, for example replacing the `function.zip` path with `target/order-function.jar`. Lambda still uses package type Zip; a JAR is a Java archive that the service can read. Only use this approach when the JAR contains all classes and dependencies, or any missing dependencies are provided via attached layers.

To update an existing function's code:

~~~bash
aws lambda update-function-code \
  --function-name order-handler \
  --zip-file fileb://target/function.zip
~~~

If the archive exceeds the direct upload limit, upload the artifact to Amazon S3 and use an S3 reference in the create or update function command. The bucket must be in the Region matching the function as required by the deployment API.

For production systems, deploy using AWS SAM, AWS CDK, CloudFormation, or an equivalent IaC tool to keep runtime, handler, memory, timeout, environment variables, layers, role, and concurrency alongside the source code.

## 7. What Are Lambda Layers?

A Lambda layer is a ZIP archive containing libraries, runtime components, or shared data. When a layer is attached to a function, Lambda extracts the layer contents into `/opt` inside the execution environment.

Layers are useful when multiple functions need the same library or extension. For example, multiple Java functions in the same system share an internal library, certificate bundle, or monitoring component.

A Java layer typically has this structure:

~~~text
shared-java-layer.zip
└── java/
    └── lib/
        ├── company-common.jar
        ├── jackson-databind.jar
        └── shared-security.jar
~~~

For Java, place libraries under `java/lib` at the root of the layer so the runtime can add them to the classpath. Layer contents are extracted under `/opt`; thus libraries appear under `/opt/java/lib`.

By common convention, a function's own handler belongs in the function's deployment package; layers are for shared libraries and components. Technically, classes in a layer can also sit on the classpath, but putting function-specific handlers inside a layer usually makes deployment boundaries and reuse harder to manage.

### 7.1. Creating and Publishing a Layer

After building the archive with the proper structure, publish a layer version via the AWS CLI:

~~~bash
aws lambda publish-layer-version \
  --layer-name shared-java-dependencies \
  --zip-file fileb://shared-java-layer.zip \
  --compatible-runtimes java21 \
  --compatible-architectures x86_64 arm64
~~~

The example runtime must be verified against the current supported list. Only declare architectures that the libraries inside the layer actually support. If the layer contains native libraries, do not mark it compatible with both `x86_64` and `arm64` when binaries are built for only one architecture.

Publishing returns an ARN with a version number. Attach that exact version to the function:

~~~bash
aws lambda update-function-configuration \
  --function-name order-handler \
  --layers arn:aws:lambda:ap-southeast-1:123456789012:layer:shared-java-dependencies:3
~~~

A layer version is immutable once published. When updating libraries, publish a new version and update the function to reference the new version. This makes deployments reproducible and allows rolling back to an older layer version.

### 7.2. Layer Limits and Trade-offs

A function can attach up to 5 layers. The total unzipped size of the deployment package plus all layers must not exceed Lambda's unzipped package size limit.

Layers avoid duplicating the same libraries across multiple ZIPs, but they also introduce version dependencies. If a layer changes and a function is not updated to the matching version, environment drift can arise. If two layers contain the same library or same classes, classpath conflicts can occur.

Do not split every dependency into a layer just to make the ZIP smaller. Only create a layer when multiple functions genuinely share components and there is a clear versioning process.

### 7.3. When to Use a Layer?

Consider a layer when:

- Multiple functions use the same internal library.
- There are shared observability components, certificates, or helper tools.
- You want controlled updates for shared dependencies.
- You need to decouple the library lifecycle from business code lifecycles.

Do not use a layer if only one function needs the dependency, if splitting increases complexity, or if a container image is already a better deployment model.

## 8. Packaging Lambda with Container Images

Container images let you package a Java application together with its runtime, OS libraries, and required tools. Lambda pulls the image from Amazon ECR and runs it according to the Lambda Runtime API contract.

Container images are suitable when:

- The application needs specific OS libraries or native dependencies.
- The current build pipeline already uses Docker/OCI as the standard artifact.
- You want control over the runtime environment and accompanying tools.
- Application dependencies or assets make the ZIP approach hard to manage.
- The development team already has an image build, scan, push, and deploy workflow.

A Lambda image must be Linux-based and support a CPU architecture compatible with the function configuration. Lambda supports one architecture per function configuration at a time, such as `x86_64` or `arm64`; do not assume a multi-architecture manifest means the function picks an architecture automatically at runtime.

### 8.1. Using the AWS Lambda Base Image for Java

AWS provides base images corresponding to Lambda runtimes. The base image includes the runtime components and the appropriate Runtime Interface Client to receive invocations from the Lambda service.

Example Dockerfile using the Java base image:

~~~dockerfile
FROM public.ecr.aws/lambda/java:21

COPY target/order-function.jar $LAMBDA_TASK_ROOT/lib/

CMD ["com.example.orders.OrderHandler::handleRequest"]
~~~

The example assumes the JAR already contains application code and required dependencies. If using a thin JAR, also copy dependency JARs into the appropriate `lib` directory. Check the classpath used by the Java base image and ensure the handler name matches the artifact.

Do not use the runtime tag from the example without verifying that the runtime is currently supported. You can pin the base image by digest to improve build reproducibility while updating the digest periodically for security patches.

### 8.2. Building the Image

Example building an image for `x86_64` architecture:

~~~bash
docker buildx build \
  --platform linux/amd64 \
  -t order-handler:1.0.0 \
  .
~~~

For `arm64` architecture, use platform `linux/arm64` and ensure native dependencies are built for the right architecture. Do not build an image on Windows or macOS using the host architecture and assume it is compatible with Lambda; explicitly specify the target platform.

### 8.3. Pushing the Image to Amazon ECR

Create the repository if it does not exist:

~~~bash
aws ecr create-repository \
  --repository-name order-handler \
  --image-scanning-configuration scanOnPush=true
~~~

Log Docker in to ECR:

~~~bash
aws ecr get-login-password --region ap-southeast-1 |
  docker login --username AWS --password-stdin \
  123456789012.dkr.ecr.ap-southeast-1.amazonaws.com
~~~

Tag and push:

~~~bash
docker tag order-handler:1.0.0 \
  123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/order-handler:1.0.0

docker push \
  123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/order-handler:1.0.0
~~~

The example uses an illustrative Region and account ID. The ECR repository must satisfy the Lambda function's Region requirements. For cross-account images, configure repository permissions so the Lambda service can pull the image.

### 8.4. Creating or Updating a Function Using an Image

Create a function with package type Image:

~~~bash
aws lambda create-function \
  --function-name order-handler-image \
  --package-type Image \
  --code ImageUri=123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/order-handler:1.0.0 \
  --role arn:aws:iam::123456789012:role/lambda-execution-role
~~~

With an image package, do not configure runtime and handler the ZIP-package way if the handler is already specified in the image CMD or image configuration. You can override the command in the Lambda configuration if needed.

When releasing a new image, update the function code so Lambda uses the new digest:

~~~bash
aws lambda update-function-code \
  --function-name order-handler-image \
  --image-uri 123456789012.dkr.ecr.ap-southeast-1.amazonaws.com/order-handler:1.0.1
~~~

Lambda resolves a tag to an image digest when creating or updating a function. If you simply push a new image to the same tag without updating the function, the existing function does not automatically switch to the new digest. Use immutable tags by version or commit and run `update-function-code` in your pipeline.

## 9. Using a Custom Base Image

You can use another Linux image instead of an AWS Lambda base image. In that case, the image must include the **Lambda Runtime Interface Client (RIC)** to communicate with the Lambda Runtime API and dispatch invocations to the handler. RIC is a required component in container environments that do not use a Lambda base image with the client built in.

With Java, add the appropriate Runtime Interface Client dependency and configure the entrypoint to launch the client. Ensure runtime, classpath, handler, and operating system are compatible. You cannot simply drop a JAR into any Java image and expect Lambda to know how to invoke the handler.

AWS provides the Runtime Interface Emulator (RIE) to support testing Lambda containers locally. RIE simulates part of the invocation interface for integration testing; it does not replace the real Lambda environment and does not verify that IAM permissions, VPC, ECR, or AWS services are configured properly.

## 10. Packaging Size and Resource Limits

Artifact size affects upload, download time, storage capacity, and initialization performance. Distinguish compressed size from uncompressed size.

Common Lambda quotas to verify in AWS documentation at deployment time:

| Limit type | Commonly applicable value | Meaning |
|---|---:|---|
| Direct ZIP upload via API/console | 50 MB | Larger packages must be uploaded via S3 |
| Total unzipped package, including layers | 250 MB | Includes code, dependencies, and layers |
| Uncompressed container image | 10 GB | Image size limit |
| Number of layers attached to one function | 5 | Total package must still stay within unzipped quota |

Service quotas can change. Check official AWS Lambda quotas before designing production artifacts or pipelines. When using a ZIP larger than the direct upload limit, S3 is the transfer mechanism for the deployment package; it does not raise the unzipped package limit.

Optimize size by:

- Packaging only dependencies needed at runtime.
- Excluding test frameworks, source code, build caches, or unused documentation from the artifact.
- Removing duplicate dependencies and inspecting the dependency tree.
- Using thin JAR plus `lib` when libraries need separate management.
- Using layers for genuinely shared dependencies.
- Including only necessary OS files in container images.
- Using multi-stage builds so compilers and build caches do not enter the runtime image.

Do not delete files simply because their names look unnecessary. Some libraries require resources, service descriptors, native libraries, or metadata in `META-INF` to function properly.

## 11. Native Dependencies and CPU Architecture

Java bytecode generally runs across multiple JVM architectures, but native dependencies are not as portable. Libraries using JNI, Netty native transport, image processing, or database drivers may contain binaries specific to Linux `x86_64` or `arm64`.

When packaging, check:

- Whether the function uses `x86_64` or `arm64` architecture.
- That native binaries are built for Linux, not Windows or macOS.
- Whether `libc` and OS libraries are compatible with the runtime image.
- Whether layers and container images match the function's architecture.
- Whether a dependency has a pure-Java fallback or requires a native library.

A JAR can bundle native libraries for multiple platforms, but the runtime can only load binaries matching the current OS and architecture. If a library lacks a compatible binary, the function may fail when loading classes or calling native methods.

## 12. Dependency and Classpath Management

The classpath is the list of locations where the JVM searches for classes and resources. Classpath errors typically manifest as `ClassNotFoundException`, `NoClassDefFoundError`, or service provider initialization failures.

Principles:

- Declare dependencies with explicit versions.
- Use the dependency tree to detect multiple versions of the same library.
- Avoid duplicating dependencies between the application JAR and layers unnecessarily.
- Check `META-INF/services` when using SPI.
- Check for identically named resources across JARs after shading.
- Do not rely on incidental libraries happening to be present in the runtime.
- Package the exact AWS SDK or library versions required by the application to control behavior.

When using Lambda layers, define which libraries live in the function package and which live in layers. If the same class appears in multiple locations, loading behavior may depend on classpath order and runtime. The safe approach is having a single clear version source for each dependency.

## 13. Cold Starts and Initialization Time

Cold start is the time Lambda spends preparing a new execution environment before handling an invocation. Artifact size and packaging style can impact download, extraction, or initialization times, though there is no simple rule that ZIP is always faster than container or vice versa.

Factors to consider:

- Archive or image size.
- Number of dependencies and class-loading time.
- Static initialization work.
- Framework, dependency injection, and client initialization.
- Database or external service connections during init.
- Native libraries and filesystem operations.

Ways to reduce initialization overhead:

- Remove unused dependencies.
- Reuse clients and `ObjectMapper` after configuration.
- Avoid overly broad classpath scanning if the framework supports narrowing it.
- Do not open database connections or load large datasets if an invocation does not need them.
- Measure init duration and invocation duration separately in telemetry.
- Consider Lambda startup optimization features if supported by the runtime and package type.

Do not trade maintainability or security to shave a few kilobytes. Measure cold starts on realistic artifacts and note that results depend on runtime, memory, CPU architecture, configuration, and load state.

## 14. Artifact Security and Software Supply Chain

Deployment packages and images are part of the software supply chain. If an artifact contains secrets or vulnerable dependencies, risk is introduced straight into the runtime environment.

Measures to apply:

- Do not package passwords, API keys, private keys, or real `.env` files.
- Retrieve secrets at runtime from AWS Secrets Manager, Systems Manager Parameter Store, or an appropriate mechanism.
- Scan dependencies and images for known vulnerabilities.
- Manage third-party library licenses.
- Generate a Software Bill of Materials (SBOM) if required by organizational policy.
- Pin dependencies and base images by controlled versions/digests.
- Sign and verify artifacts according to deployment policy.
- Restrict permissions to read ECR, update functions, and publish layers.
- Use IAM execution roles with least privilege.
- Do not pass sensitive data into Docker build arguments or image layers.

For ZIP packages, AWS Lambda supports code signing configurations to allow only packages signed by configured trusted profiles. Container images require corresponding image controls, ECR scanning, signing policies, and approval workflows. Do not assume ZIP code signing automatically protects container images.

## 15. Integrating Build and Deploy with CI/CD

A Java Lambda deployment pipeline should have reproducible steps:

~~~mermaid
flowchart TD
    A["Commit source"] --> B["Compile and unit test"]
    B --> C["Resolve dependencies"]
    C --> D["Build ZIP/JAR or image"]
    D --> E["Inspect package and scan"]
    E --> F["Publish artifact / push ECR"]
    F --> G["Deploy Lambda"]
    G --> H["Smoke test"]
    H --> I["Promote version / alias"]
~~~

For ZIP/JAR, the pipeline builds the archive, verifies the classpath, scans dependencies, and uploads the artifact to S3 or deploys via SAM/CDK.

For container images, the pipeline builds for the exact target architecture, scans the image, pushes to ECR, and then updates Lambda using the image URI or digest. Do not use the `latest` tag as the sole mechanism to identify a release in production.

Separate artifact building from environment deployment. The same verified artifact can be promoted through dev, staging, and production; only runtime configuration, environment variables, roles, VPC, and aliases change per environment.

## 16. Rollback and Version Management

A deployment must be able to roll back to a known-good artifact. For ZIP/JAR, store versioned or checksummed artifacts and retain previous builds. For layers, the function references the ARN of a specific layer version. For images, use immutable tags and record digests.

Lambda versions and aliases help manage releases. A published version is a snapshot of the function's configuration and code at publish time; an alias can point to a specific version and support traffic shifting under an appropriate deployment strategy.

Rollbacks must align code, layers, environment configuration, and schema compatibility. If new code has written data using a new schema, rolling back to older code may be unsafe. Design migrations to remain backward-compatible during transition periods.

## 17. Choosing ZIP/JAR, Layer, or Container Image?

| Criterion | ZIP/JAR | ZIP + layer | Container image |
|---|---|---|---|
| Simplicity | High for typical Java functions | Medium, adds layer version management | Requires Docker and ECR |
| Shared dependencies | May be duplicated per package | Suits multiple functions sharing libraries | Can share a common base image |
| OS control | Limited by managed runtime | Limited by managed runtime | Higher |
| Size | Suits small to medium packages | Total package/layer quota still applies | Suits larger images, within image quota |
| Build workflow | Maven/Gradle and archive | Also build layer archive | Docker build, scan, and push |
| Reproducibility | Based on archive and pinned dependencies | Must pin layer version | Can pin base image and digest |
| Use case | Standard Java handlers | Multiple functions sharing libraries | Native dependencies or custom environment |

You can start with ZIP/JAR when using a managed Java runtime with moderate dependencies. Add layers when multiple functions need the same libraries. Choose container images when environment control is needed or a mature container workflow is already in place.

Do not choose a container image merely because a project has a Dockerfile, and do not use layers just to split up a single function. Evaluate practical benefits in reuse, runtime control, size, security, and operations.

## 18. Example Packaging Workflow for an Order Lambda

Suppose an Order Lambda receives HTTP requests to create orders, uses Jackson to parse JSON, and uses the AWS SDK to emit events after persisting data.

Packaging workflow with ZIP/JAR:

1. Write the handler following `RequestHandler` or a runtime-supported signature.
2. Declare DTOs, use cases, and adapters in source code.
3. Declare runtime dependencies in Maven or Gradle.
4. Build an uber JAR or ZIP containing classes and dependencies.
5. Inspect the handler class, resources, and dependencies.
6. Verify the artifact contains no secrets.
7. Deploy the ZIP package with a supported Java runtime and the right handler.
8. Configure execution role, timeout, memory, environment variables, and triggers.
9. Run smoke tests via HTTP or test events.
10. Publish a version and point the alias after passing checks.

If multiple functions share internal libraries, extract those libraries into a shared versioned layer. If the application requires native libraries or specific OS packages, build a container image from a Lambda base image or a custom image with RIC.

## 19. Common Packaging Mistakes

**Missing runtime dependencies:** JAR contains only application classes so the function fails with `NoClassDefFoundError`. Check dependency scopes and archive contents.

**Incorrect ZIP structure:** ZIP has an extra parent folder so the runtime cannot find classes. Package contents from the staging directory at the root of the archive.

**Wrong handler name:** Class or method in configuration does not match the artifact. Verify package, class, method, and signature.

**Using a non-uber JAR:** Assuming the default JAR contains dependencies. Inspect contents and choose thin JAR + `lib` or uber JAR.

**Dependency conflicts:** Multiple library versions or overwritten service descriptors. Inspect the dependency tree and shade transformers.

**Wrong paths in layer:** Java libraries are not placed under `java/lib`, preventing proper loading. Check archive structure before publishing.

**Layer version not updated:** Published a new version while the function still points to the old version. Update the function configuration with the new version ARN.

**Exceeding size limits:** Looking only at compressed ZIP size and forgetting total unzipped size plus layers. Check both before deploying.

**Wrong image architecture:** Built on an ARM machine while the function runs `x86_64`, or vice versa. Specify the platform during build and match the Lambda configuration.

**Container image missing RIC:** Using a custom base image without adding the Runtime Interface Client. Use an AWS base image or configure RIC properly.

**Pushing image without updating function:** Overwriting an ECR tag without calling `update-function-code`. Deploy using immutable tags or digests and update the function.

**Packaging secrets:** `.env` files or credentials included in the archive/image. Scan artifacts and fetch secrets at runtime.

## 20. Pre-Deployment Checklist

- [ ] Chosen ZIP/JAR or container image based on runtime and dependencies.
- [ ] Handler class/method matches the Lambda configuration.
- [ ] Java runtime is supported by AWS and compatible with bytecode.
- [ ] Artifact contains all runtime classes, dependencies, and resources.
- [ ] Dependency scopes, versions, and service descriptors have been checked.
- [ ] ZIP has no extra parent directory.
- [ ] If using layers, Java structure is `java/lib` and function references the right layer version.
- [ ] Total unzipped package and layers stay within quota.
- [ ] If using an image, it is Linux-based and has the proper runtime interface.
- [ ] Image is built only for the architecture the function uses.
- [ ] Image is pushed to ECR in the right Region with proper access permissions.
- [ ] After pushing a new image, the pipeline updates Lambda with the new image URI/digest.
- [ ] Artifact/image contains no secrets or unnecessary local files.
- [ ] Dependencies and images have been scanned per policy.
- [ ] Checksum, version, or digest exists for reproducibility and rollback.
- [ ] Smoke tests have run in the Lambda environment.
- [ ] Artifact size, init duration, cold start, and invocation duration have been measured.

## Conclusion

A Java Lambda can be packaged as a ZIP or JAR when using a managed Java runtime. ZIP holds classes, resources, and dependencies in a structure the runtime can load; JAR can be a thin JAR or an uber JAR depending on how the classpath is managed. Lambda layers supply shared libraries under `/opt` and are versioned. Container images package the runtime alongside the application, are stored in ECR, and fit when a custom Linux environment or custom dependencies are needed.

Your choice should depend on size, dependencies, native libraries, reusability, cold starts, security, and CI/CD capabilities. Regardless of approach, verify handler, classpath, runtime, CPU architecture, quotas, and artifact contents before deploying. A build pipeline with versioning, scanning, smoke tests, and clear rollbacks helps Lambda run consistently across environments.
