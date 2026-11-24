# Storing Contracts Alongside Release Versions and Source Provenance

## 1. Why store OpenAPI alongside release versions?

Springdoc OpenAPI can generate specifications directly from a running application via endpoints such as /v3/api-docs and /v3/api-docs.yaml. This is convenient during development, yet a runtime URL is not always enough to identify the exact contract released alongside a specific application version.

During an incident, operations and integration teams need to answer:

- Which specification describes the running application?
- Which commit produced that specification?
- What is the API contract version?
- Which version was the Spring Boot artifact built with?
- Which pipeline validated and released the specification?
- Is the JSON/YAML file clients are using the exact reviewed file?

If you only access the latest OpenAPI document in production, its content may already have changed since the release a client integrates against. If you only store the file in a repository without linking it to the artifact, it is hard to prove that file was generated from the exact deployed source and configuration.

Therefore, the OpenAPI document should be managed as a release artifact. The pipeline must export the document from the right build, validate it, attach version and source revision metadata, and then store it alongside the release or in a traceable artifact repository.

## 2. Distinguishing version types

Three types of versions often appear together while carrying different meanings:

| Version type | Example | Meaning |
|---|---|---|
| OpenAPI Specification version | 3.1.0 | Standard version describing document structure |
| API contract version | 1.4.0 | Version of the API contract intended for clients |
| Application version | 2.8.3 | Version of the Spring Boot application artifact |

Example top section of a document:

~~~yaml
openapi: 3.1.0
info:
  title: Catalog API
  version: "1.4.0"
~~~

The openapi field indicates the document conforms to OpenAPI Specification 3.1.0. The info.version field indicates the API contract version being described.

The application version can be 2.8.3 while the API contract stays 1.4.0. A new build may fix internal bugs, update libraries, or improve performance without changing the HTTP contract.

Do not auto-increment info.version on every build number. Update the API contract version when deciding to release a new contract according to the organization's versioning policy.

## 3. Tying the contract to source and artifacts

A released OpenAPI version should be traceable back to:

- Service or artifact name.
- API contract version.
- Application version.
- OpenAPI Specification version.
- Git commit SHA.
- Build number or pipeline run ID.
- Artifact creation timestamp if needed.
- Checksum of the OpenAPI file.
- Versions of the tools that generated and validated the document.

Example release manifest:

~~~yaml
service: catalog-api
apiContractVersion: 1.4.0
applicationVersion: 2.8.3
openApiSpecificationVersion: 3.1.0
sourceRevision: a1b2c3d4e5f6
buildRun: catalog-api-1842
openApiArtifact: catalog-api-openapi-1.4.0.yaml
sha256: 4a8f...example
~~~

This manifest is release metadata, not a mandatory part of the OpenAPI document. It can be stored alongside the OpenAPI file in a release bundle or artifact repository.

You do not need to publish the entire manifest to API consumers. Commit SHA, pipeline URL, branch name, or build host may be internal information. Distinguish metadata meant for internal traceability from metadata that actually belongs in a public document.

## 4. Exporting OpenAPI JSON and YAML from Springdoc

Springdoc typically exposes two endpoints:

~~~http
GET /v3/api-docs
GET /v3/api-docs.yaml
~~~

JSON fits automation tools and script processing. YAML is often easier to read when reviewing pull requests or storing alongside release documentation.

If the application enables document groups, each group can have its own endpoint, for example:

~~~http
GET /v3/api-docs/partner
GET /v3/api-docs/partner.yaml
~~~

Define clearly whether the release exports the default document or individual groups. If public, partner, and internal APIs have different contracts, each document needs its own artifact name and metadata to avoid overwrites or releasing to the wrong audience.

Do not download a document from an arbitrary environment and call it the release contract. Launch the exact artifact under test with the defined profile and configuration, then export the document from that instance.

## 5. Preparing configuration for a reproducible export

For two exports from the same source and configuration to yield equivalent contracts, the pipeline must pin:

- Checked-out source commit.
- JDK and build tool versions.
- Dependency lock or pinned dependency versions.
- Spring profile used when generating documentation.
- Environment variables affecting API metadata.
- Feature flags affecting controllers, mappings, or schemas.
- Document groups and filters.
- Springdoc and Swagger Core versions.
- Customizers and plugins involved in export.

Do not derive the server URL from arbitrary request headers in the pipeline. Use a contract profile configuration with a stable public base URL or an agreed canonical configuration.

If metadata contains a build timestamp that changes on every run, the OpenAPI file may differ even when the contract has not changed. Include timestamps in the document only if there is an explicit operational requirement; otherwise, store build timestamps in a separate manifest to keep the contract artifact stable.

## 6. Configuring Maven to export the document

Springdoc provides a dedicated Maven plugin to fetch the OpenAPI document from a running application. This plugin does not start the Spring Boot application itself; the pipeline must ensure the api-docs endpoint is ready before the generate goal runs.

Example plugin configuration:

~~~xml
<plugin>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-maven-plugin</artifactId>
    <version>1.5</version>
    <executions>
        <execution>
            <id>export-openapi</id>
            <phase>integration-test</phase>
            <goals>
                <goal>generate</goal>
            </goals>
        </execution>
    </executions>
    <configuration>
        <apiDocsUrl>http://localhost:8080/v3/api-docs</apiDocsUrl>
        <outputFileName>openapi.json</outputFileName>
        <outputDir>target/openapi</outputDir>
    </configuration>
</plugin>
~~~

The plugin version in the example must be pinned and checked for compatibility with the project's Springdoc/Spring Boot versions. Do not use dynamic versions in release pipelines.

You can combine with the Spring Boot Maven Plugin to start the application before integration-test and stop it after export:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <id>start-application</id>
            <phase>pre-integration-test</phase>
            <goals>
                <goal>start</goal>
            </goals>
        </execution>
        <execution>
            <id>stop-application</id>
            <phase>post-integration-test</phase>
            <goals>
                <goal>stop</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

The Maven lifecycle must be configured consistently with the integration-test framework in use. If the pipeline starts the application via a separate container or service, this start/stop mechanism is unnecessary; just ensure the endpoint is ready before the export step. If you need both build-info and start/stop, combine the executions into a single Spring Boot Maven Plugin declaration in the POM.

## 7. Exporting the document with curl or PowerShell

You can download the document directly once the application is running:

~~~bash
mkdir -p target/openapi

curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  --output target/openapi/openapi.json

curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs.yaml \
  --output target/openapi/openapi.yaml
~~~

On Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path target/openapi | Out-Null
Invoke-WebRequest -Uri http://localhost:8080/v3/api-docs -OutFile target/openapi/openapi.json
Invoke-WebRequest -Uri http://localhost:8080/v3/api-docs.yaml -OutFile target/openapi/openapi.yaml
~~~

Use fail-fast so the pipeline stops when the endpoint returns an error. After downloading, verify the file is non-empty and the response is genuinely OpenAPI JSON/YAML. An HTML login page returned with status 200 is not a valid document.

If API docs are protected by authentication, the pipeline needs dedicated credentials authorized to read documentation. Do not print tokens or passwords to command logs; use the CI secret store.

## 8. Exporting from the exact artifact being released

A common mistake is exporting documentation from the current source tree, then releasing a JAR built in another step or from a different commit. In that case, the OpenAPI artifact and application artifact no longer share the same provenance.

The workflow should link them in one chain:

~~~text
Git commit
    |
    v
Build application artifact
    |
    v
Run tests and start that artifact
    |
    v
Export OpenAPI JSON/YAML
    |
    v
Validate and compare contract
    |
    v
Create release manifest and checksums
    |
    v
Publish application + OpenAPI artifacts
~~~

If rebuilding the application after export, verify the new build still uses the exact same source revision, dependencies, and configuration. Best practice is exporting from the exact JAR/container image that passed verification steps and will be released.

Do not use a document generated from a local developer environment as a substitute for a release artifact. A local machine may have different profiles, environment variables, dependency caches, or feature flags than the pipeline.

## 9. Linking API contract version to the application build

The application version is typically managed in the Maven POM or Gradle project version. The API contract version should be managed separately, for example via a property:

~~~yaml
app:
  api:
    contract-version: "1.4.0"
~~~

Springdoc can use this value when creating the Info Object:

~~~java
@ConfigurationProperties(prefix = "app.api")
public record ApiContractProperties(
    String contractVersion
) {
}
~~~

~~~java
@Bean
OpenAPI catalogOpenAPI(ApiContractProperties properties) {
    return new OpenAPI()
        .info(new Info()
            .title("Catalog API")
            .version(properties.contractVersion()));
}
~~~

In the release pipeline, set the contract version from an approved release configuration. Do not infer the contract version from the application version if the two versioning policies are independent.

If a build contains multiple document groups, each group may have its own API contract version. In that case, name artifacts by service and group to avoid confusion.

## 10. Adding build version via Spring Boot BuildProperties

Spring Boot can generate build metadata inside the artifact so the application can read back the packaged version.

With Maven, configure the build-info goal of the Spring Boot Maven Plugin:

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <executions>
        <execution>
            <goals>
                <goal>build-info</goal>
            </goals>
        </execution>
    </executions>
</plugin>
~~~

With Gradle:

~~~groovy
springBoot {
    buildInfo()
}
~~~

When the artifact contains META-INF/build-info.properties, Spring Boot can provide a BuildProperties bean with information such as artifact, group, name, version, and time.

This bean may not exist if build-info was not generated. If the application has test or local profiles that do not generate build metadata, use ObjectProvider or conditional configuration instead of unconditionally injecting BuildProperties in every environment.

BuildProperties helps the document or manifest reflect the version of the artifact actually running, rather than a manually re-entered value.

## 11. Attaching source revision via Git metadata

For source traceability, the pipeline should record the full or short Git commit SHA. Spring Boot can read git.properties via GitProperties if the build is configured to generate that file.

Example retrieving the revision in code:

~~~java
GitProperties git = gitPropertiesProvider.getIfAvailable();

if (git != null && StringUtils.hasText(git.getShortCommitId())) {
    openApi.addExtension(
        "x-source-revision",
        git.getShortCommitId()
    );
}
~~~

The bean method should accept ObjectProvider<GitProperties> gitPropertiesProvider. The git.properties file can be generated using the appropriate Git metadata plugin for Maven or Gradle.

Do not assume GitProperties always exists. Source archives, shallow clones, or pipelines that omit the .git directory can prevent the plugin from generating metadata as expected.

The commit SHA is useful traceability information. Branch names, repository URLs, build agent hostnames, and internal pipeline details do not necessarily belong in public OpenAPI.

## 12. Adding build metadata to OpenAPI in a controlled way

You can add vendor extensions to the OpenAPI model:

~~~java
@Bean
OpenApiCustomizer releaseMetadataCustomizer(
        ObjectProvider<BuildProperties> buildProvider,
        ObjectProvider<GitProperties> gitProvider) {

    return openApi -> {
        BuildProperties build = buildProvider.getIfAvailable();
        GitProperties git = gitProvider.getIfAvailable();

        if (build != null && StringUtils.hasText(build.getVersion())) {
            openApi.addExtension(
                "x-application-version",
                build.getVersion()
            );
        }

        if (git != null && StringUtils.hasText(git.getShortCommitId())) {
            openApi.addExtension(
                "x-source-revision",
                git.getShortCommitId()
            );
        }
    };
}
~~~

Extensions starting with x- are custom metadata, not standard fields that every client generator is required to understand.

If the document is distributed externally, consider publishing only the application version. Source revision can be kept in the internal release manifest. Do not add branch names, commit messages, or private repository URLs without reason.

Never put secrets, access tokens, connection strings, database hostnames, or internal configuration into extensions. OpenAPI documents may be downloaded and stored long-term by clients.

## 13. Naming and organizing OpenAPI artifacts

Artifact names should identify the service, group, and API contract version. For example:

~~~text
release/
  catalog-api/
    1.4.0/
      openapi.json
      openapi.yaml
      manifest.yaml
      SHA256SUMS
~~~

With multiple groups:

~~~text
release/
  catalog-api/
    1.4.0/
      public-openapi.yaml
      partner-openapi.yaml
      internal-openapi.yaml
      manifest.yaml
~~~

Never overwrite files of an already released version. If contract version 1.4.0 has been published, a new document with different content should not silently replace the same path. Create a new version or follow a release-correction process with auditing and clear policies.

Artifacts can be stored in:

- Maven repository or package registry.
- Generic artifact repository.
- Versioned object storage.
- Release assets attached to a Git tag.
- Developer portal or API catalog.
- OCI artifact registry if the platform supports distributing documentation as OCI artifacts.

Choose one authoritative source of truth and document ownership, retention, and access policies clearly.

## 14. Generating checksums to verify files

Checksums help verify whether a downloaded file matches the published artifact.

On Linux/macOS:

~~~bash
sha256sum openapi.json openapi.yaml > SHA256SUMS
~~~

On Windows PowerShell:

~~~powershell
Get-FileHash target/openapi/openapi.json -Algorithm SHA256
Get-FileHash target/openapi/openapi.yaml -Algorithm SHA256
~~~

Store checksums in the release manifest or a SHA256SUMS file next to the artifact. When consumers download the document, they can verify the hash before using it.

A checksum only proves file content matches a known hash. If you need to verify the publisher's identity, sign the manifest or artifact using your organization's signing mechanism and protect the signing key in a CI secret store or KMS.

Never store private signing keys in the repository or inside the OpenAPI document.

## 15. Validating the document before release

The pipeline must verify at least these layers:

| Validation layer | Content |
|---|---|
| File | File exists, non-empty, right encoding |
| Structure | JSON/YAML is parseable |
| OpenAPI | Document conforms to the right specification version |
| References | Local/external $refs resolve |
| Schema | Schemas are valid with appropriate types/constraints |
| Operation | Paths, methods, operationIds, and responses are complete |
| Security | Schemes and requirements match runtime API |
| Environment | Server URLs do not point to wrong or internal hostnames |
| Policy | No leaked secrets or unpublished data |
| Compatibility | No unintended breaking changes |

A parseable file is not necessarily valid OpenAPI. A specification-valid document is not necessarily compliant with internal conventions such as operationId naming, error responses, pagination, or security policies.

Use dedicated validators and linters. Pin tool versions in CI so the same commit does not get different results just because a tool auto-updated.

## 16. Validating with OpenAPI Generator CLI

OpenAPI Generator CLI provides a validate command to inspect the document:

~~~bash
openapi-generator-cli validate -i target/openapi/openapi.yaml
~~~

This command is useful for catching invalid OpenAPI structures or errors recognized by the generator's parser. However, results depend on the CLI version and support for OpenAPI versions/features.

If using OpenAPI 3.1, choose a validator and generator version that supports 3.1. Do not downgrade the document to 3.0 solely to make an older tool run without evaluating semantic loss.

Besides validation, you can generate client/server stubs in a separate job to catch compatibility issues early. Successful code generation does not replace contract linting or breaking-change diffs.

## 17. Linting against organizational conventions

Spectral is one option for checking OpenAPI style and governance rules. Example:

~~~bash
spectral lint target/openapi/openapi.yaml
~~~

A rule set can require:

- Every operation has a summary and operationId.
- Error responses use a standard schema.
- Every API requiring protection has a security requirement.
- No internal server URLs in public documents.
- Pagination query parameters have descriptions.
- Schemas have descriptions or examples per convention.
- Tags and operationIds follow naming conventions.

Rule sets must be versioned alongside the pipeline. If changing rules, review it as a CI policy change to avoid suddenly failing older APIs without a migration path.

Do not set rules so strict that developers are forced to add meaningless metadata. The goal is creating consistent contracts useful to clients.

## 18. Detecting breaking changes against the previous release

A new document can be valid yet still break existing clients. Examples:

- Removing a path or HTTP method.
- Removing a response property currently used by clients.
- Changing a property's data type.
- Changing a parameter from optional to required.
- Adding an enum value in systems where clients use closed enum handling.
- Changing security requirements so clients need new credentials.
- Changing response statuses or media types.
- Narrowing request ranges or constraints.

You can use oasdiff to compare old and new documents:

~~~bash
oasdiff breaking previous/openapi.yaml candidate/openapi.yaml
~~~

The breaking command focuses on detecting changes likely to impact clients. Pin the oasdiff version and define the exit codes/policies used by the pipeline.

Not every change is breaking for every client. For example, adding an optional response field is usually compatible with clients that ignore unknown fields, yet may impact clients using strict deserialization. Combine diff tools with the system's compatibility policy.

If the pipeline detects a breaking change, require review or approval per the release process instead of automatically ignoring warnings.

## 19. Comparing the right two contracts

When comparing contracts, the two files must represent comparable versions of the API:

- The baseline is the document from the latest published release for the same API audience.
- The candidate is the document generated from the commit under test.
- The same document group must be compared against itself.
- The same normalization of server URLs and environment metadata must be applied.
- The same validator/diff tool version or a planned tool upgrade path must be used.

Do not compare a public API against an internal API or a document from a different group. Do not compare a staging file with its own server URL against a production file if the only difference is the environment and the pipeline has not normalized metadata.

You can strip or normalize deployment-specific fields before diffing if policy permits. Normalization must leave paths, operations, schemas, security, and actual contract elements intact.

Store baselines by release artifact instead of using an untraced "latest" OpenAPI file.

## 20. Sample CI pipeline

An OpenAPI export and verification pipeline can include these steps:

~~~bash
set -euo pipefail

# 1. Build and test the exact source revision
./mvnw -B clean verify

# 2. Ensure the application is running with the contract profile
# The application must use the artifact built by this pipeline.

# 3. Export the document
mkdir -p target/openapi
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs.yaml \
  --output target/openapi/openapi.yaml

# 4. Validate and lint
openapi-generator-cli validate -i target/openapi/openapi.yaml
spectral lint target/openapi/openapi.yaml

# 5. Compare with the previous published contract
oasdiff breaking previous/openapi.yaml target/openapi/openapi.yaml

# 6. Create a checksum
sha256sum target/openapi/openapi.yaml \
  > target/openapi/SHA256SUMS
~~~

This is a pipeline skeleton. Starting the application, readiness checks, fetching the baseline, handling exit codes, and publishing artifacts must be wired into your organization's CI platform.

If using the Maven Springdoc plugin to export, replace the curl step with the configured generate goal. Either way, ensure the running application is the freshly built artifact using the defined contract profile.

Do not let the pipeline proceed to publishing when validation or breaking-change checks fail, unless there is explicit approval and a release record documenting the exception.

## 21. Attaching source metadata to the release manifest

The manifest can be generated after export:

~~~yaml
service: catalog-api
apiContractVersion: "1.4.0"
applicationVersion: "2.8.3"
openApiSpecificationVersion: "3.1.0"
source:
  repository: catalog-api
  revision: a1b2c3d4e5f6
build:
  runId: "1842"
  profile: contract
artifacts:
  - name: openapi.yaml
    sha256: 4a8f...example
  - name: catalog-api.jar
    sha256: 9b2d...example
~~~

The manifest links the OpenAPI document to the tested JAR or container image. If there are multiple groups, list each file alongside its group name and checksum.

You do not need to embed all of this metadata inside the OpenAPI document. A separate manifest keeps the public document cleaner while the release system retains full provenance.

Keep the manifest alongside the artifacts and ensure artifact paths are immutable.

## 22. Protecting information during export and publishing

An OpenAPI document can expose:

- Internal hostnames and network paths.
- Administrative endpoints or operations not intended for public release.
- Names of dependent systems.
- Schemas containing internal data.
- Request/response examples containing real data.
- Security schemes or OAuth URLs from an inappropriate environment.
- Source revisions, branches, or internal build metadata.

Before publishing:

1. Select the exact document group meant for the target audience.
2. Inspect server URLs and paths.
3. Use synthetic data in examples.
4. Put no real secrets/tokens in descriptions or examples.
5. Check security schemes contain no credentials.
6. Do not publish internal hosts, database endpoints, or actuator routes.
7. Manage read permissions on the artifact repository.
8. Scan documents with policy or secret scanners if required.

Protecting the /v3/api-docs endpoint at runtime and controlling access to published artifacts are two separate layers. Disabling Swagger UI does not mean published OpenAPI files are protected.

## 23. Publishing immutable artifacts and supporting rollbacks

After validation and approval, publish the OpenAPI document alongside the release:

- Use a path containing the API contract version.
- Store the manifest and checksums.
- Link artifacts to source revision and application artifact.
- Retain older releases per the retention policy.
- Never overwrite already-released contracts.
- Be able to re-download the exact document of any past release.

When rolling back an application, operations teams need to know which document corresponds to the rolled-back application artifact. Do not grab the document from the latest main branch if the application is running an older release.

If the API contract version does not change between two builds, you can store multiple build provenances under the same contract version in release history, but define clear rules to avoid overwriting the canonical file—for example using build-specific subfolders in the manifest or artifact metadata.

## 24. Common mistakes when storing and publishing contracts

| Symptom | Cause to check |
|---|---|
| OpenAPI artifact does not match deployed JAR | Exported from different source/build than released artifact |
| info.version changes on every build | Used application version instead of API contract version |
| Missing source revision | Build did not generate git.properties or manifest omitted commit |
| JSON/YAML file is empty | Endpoint not ready, authentication issue, or export failed |
| File contains HTML instead of OpenAPI | Redirect to login page or proxy error page |
| Staging URL leaked into public document | Wrong profile or environment-derived server URL |
| Group documents overwritten | All groups share the same output filename |
| Diff always reports changes | Unnormalized timestamps, server URLs, or dynamic metadata |
| Breaking change went undetected | Compared wrong baseline, wrong group, or tool lacks support |
| Local and CI validators disagree | Unpinned tool or dependency versions |
| Old artifact content changed | Publish overwrote an existing versioned path |
| Checksum mismatch | File modified after hashing or publishing |
| Source metadata leaks internal details | Published branch, repository URL, or unnecessary commit info |

When investigating, cross-check the source SHA, application artifact checksum, OpenAPI checksum, and pipeline run ID. Looking only at the filename or info.version is not enough to prove two artifacts came from the same release.

## 25. Checklist before publishing OpenAPI

Before publishing contract artifacts:

1. Build the application from an identified commit.
2. Run tests and start the exact freshly built artifact.
3. Activate the contract profile with stable server configuration.
4. Export the right JSON/YAML and every document group to be released.
5. Verify files are non-empty and parseable.
6. Validate against the declared OpenAPI Specification version.
7. Lint against governance rules.
8. Resolve $refs and inspect component schemas.
9. Compare against the baseline for the same API audience to detect breaking changes.
10. Verify API contract version is independent of application version.
11. Record source revision and build run in the manifest.
12. Generate checksums and sign artifacts if required by process.
13. Scan for sensitive information and server URLs.
14. Publish artifacts to an immutable versioned path.
15. Retain baselines and release metadata to support rollbacks.

An OpenAPI document is a contract with its own lifecycle and must be tied to the release that created it. When the pipeline exports documentation from the exact application artifact, validates correctness and compatibility, stores source revision and checksums, and publishes immutably, the development team can pinpoint exactly which contract clients use and restore the documentation matching any release.

