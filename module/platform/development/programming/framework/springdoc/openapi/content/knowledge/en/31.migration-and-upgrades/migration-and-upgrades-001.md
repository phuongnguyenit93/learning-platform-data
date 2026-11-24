# Creating a Comparison Baseline Before Changing Libraries or Upgrading Versions

Upgrading springdoc-openapi or underlying libraries can change the OpenAPI document even when controllers and business logic do not change. Versions of Spring Boot, swagger-core, Jackson, Java, and MVC/WebFlux integration can all affect which handlers are discovered, how schemas are generated, how annotations are interpreted, or how documentation endpoints behave.

Before upgrading, save an OpenAPI baseline from the currently released version. After updating dependencies and configuration, generate the new document under the same conditions, compare the two documents, and determine which changes come from the API contract and which come solely from how the library generates documentation. The baseline must be tied to a known release, not an arbitrary file on a developer machine.

This guide explains how to establish a comparison baseline before changing libraries or upgrading versions: inventorying the environment and dependencies, exporting baseline JSON/YAML, normalizing comparisons, classifying diffs, checking compatibility, building a migration plan, and integrating verification steps into CI.

## 1. Why is a baseline needed before upgrading?

springdoc-openapi builds documentation from the Spring application context, handler mappings, annotations, request/response types, and OpenAPI configuration. When upgrading springdoc or Spring Boot, output can change across multiple layers:

- A handler is newly discovered or omitted due to changes in mapping, package scanning, or bean conditions.
- Schema names, component references, or generic handling change.
- Annotations from swagger-core are interpreted differently.
- Jackson modules, naming strategies, or visibility settings alter schema properties.
- The OpenAPI output version changes from 3.0 to 3.1 or vice versa.
- Security schemes, server URLs, response content types, or operation metadata change.
- Swagger UI, JSON/YAML endpoints, or group configurations behave differently.

Without a baseline, the team can hardly tell whether the new documentation drops endpoints or alters a published contract. A successfully generated OpenAPI file only proves that the export process runs; it does not prove that the contract remains compatible.

A baseline helps answer three questions:
1. What did the pre-upgrade documentation publish?
2. Where exactly does the post-upgrade documentation differ?
3. Does each change impact consumers, generated SDKs, or runtime behavior?

## 2. Define the upgrade scope before making changes

First, state the migration goal clearly. Do not bundle multiple independent changes into a single upgrade unless necessary.

Examples of common scopes:

| Scope | Changed components | Risks to verify |
|---|---|---|
| springdoc patch upgrade | springdoc dependency on the same major line | Bug fixes, configuration, and output changes |
| springdoc major upgrade | Artifacts, configuration APIs, or bundled swagger-core | Breaking APIs, annotations, and schema generation |
| Spring Boot upgrade | Framework, auto-configuration, Spring MVC/WebFlux | Handler mapping, security, Jackson, and Jakarta |
| Java upgrade | JDK, compiler, and runtime | Source compatibility, reflection, build plugins |
| Switch MVC to WebFlux or vice versa | Web stack and starter | Handler discovery, functional routes, runtime behavior |
| Switch OpenAPI 3.0 to 3.1 | Specification version and schema dialect | nullable, JSON Schema keywords, and toolchain |
| Swagger UI upgrade | UI assets and configuration | Document URL, authorize, rendering, and Try it out |

Specify which components are allowed to change and which must remain unchanged. If Java, Spring Boot, springdoc, Jackson, and the OpenAPI version are upgraded simultaneously, it becomes difficult to isolate the root cause when diffs appear.

A controllable plan usually splits a large migration into smaller steps: first upgrade compatible dependencies within the current stack, then upgrade Spring Boot or Java, and finally change the OpenAPI dialect if required.

## 3. Inventory the current environment and dependencies

The baseline must be accompanied by information about the environment that produced it. At a minimum, record:

| Category | Information to record |
|---|---|
| Runtime | Java vendor/version, JVM options, OS, or container image |
| Framework | Spring Boot, Spring Framework, Spring Security |
| Web stack | Spring MVC or WebFlux |
| OpenAPI | springdoc artifact/version, OpenAPI output version |
| Swagger | swagger-core/annotations and transitive Swagger UI version |
| Serialization | Jackson core/databind/modules and related configuration |
| Build | Maven/Gradle wrapper and plugin versions |
| Configuration | Active Spring profiles, context path, API-docs path |
| Application | Git commit, release tag, service build/version |
| Documents | Default document and each GroupedOpenApi |

Do not record only the versions in the build file. Transitive dependencies may differ from directly declared versions. Save the dependency tree or dependency lock so changes can be explained later.

With Maven:

~~~bash
mvn -version
mvn dependency:tree -Dincludes=org.springdoc,io.swagger.core.v3
~~~

With Gradle:

~~~bash
./gradlew --version
./gradlew dependencyInsight --dependency springdoc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency swagger-core --configuration runtimeClasspath
~~~

If the project has multiple modules, run the command in the exact module that produces the OpenAPI document. The root module's dependency tree may not reflect the service's runtime classpath.

## 4. Check the compatibility matrix before choosing a target version

Do not choose a springdoc version based solely on the latest version number. Cross-check the release notes and compatibility matrix for that specific version.

Conditions to verify:

- Supported Spring Boot version.
- Java baseline and JDK used for building.
- MVC or WebFlux.
- Spring Framework and Spring Security managed by the Spring Boot BOM.
- Jakarta namespace or javax namespace.
- Bundled swagger-core and swagger-annotations.
- Compatible Jackson version and modules.
- Maven/Gradle plugins and native/AOT support if the application uses them.
- Additional starters or modules the project is using.

Some major migrations change artifact coordinates. For example, when migrating from springdoc 1.x to 2.x for Spring Boot 3, starters typically use separate names for MVC or WebFlux:

| Web stack | springdoc 2.x starter artifact |
|---|---|
| Spring MVC | org.springdoc:springdoc-openapi-starter-webmvc-ui |
| Spring WebFlux | org.springdoc:springdoc-openapi-starter-webflux-ui |

Older projects may use an artifact such as `springdoc-openapi-ui`. Do not keep both the new starter and the old artifact together if they provide overlapping configuration components. Pick the right starter for your web stack and check the migration guide for the target release.

Spring Boot 3 is also a major Jakarta ecosystem migration, not just a springdoc dependency swap. Java EE APIs moved from the `javax.*` namespace to `jakarta.*` in many areas, and Spring Boot 3 requires a newer Java baseline than Spring Boot 2. If the application is still on Spring Boot 2, create a separate checklist for the Boot migration, source imports, validation, servlet container, security, and third-party libraries.

Do not force a specific swagger-core or Jackson version manually to work around compile errors before checking dependency management. The Spring Boot BOM and springdoc starter usually expect a compatible set of versions. Overriding a transitive dependency can break schema generation or serialization at runtime.

## 5. Capture the baseline from the released version

Generate the baseline from a build/release confirmed to be running or already released. Do not use documentation from an unmerged branch as the baseline if the goal is to protect production consumers.

With springdoc's default endpoint:

~~~bash
curl -fsS https://api.example.com/v3/api-docs -o openapi-baseline.json
curl -fsS https://api.example.com/v3/api-docs.yaml -o openapi-baseline.yaml
~~~

If API docs require authentication, use credentials issued for the export workflow and do not log tokens. If documentation is only exported in the pipeline, download the OpenAPI artifact from the corresponding release instead of calling production.

With GroupedOpenApi, save each document group separately:

~~~bash
curl -fsS https://api.example.com/v3/api-docs/public -o openapi-public-baseline.json
curl -fsS https://api.example.com/v3/api-docs/partner -o openapi-partner-baseline.json
~~~

Do not save only the default document if consumers use separate groups. Group names, URLs, and artifacts must be mapped clearly.

The baseline should be immutable and include provenance:
- Release tag or commit that generated the document.
- Service version and export timestamp.
- Java, Spring Boot, springdoc, and OpenAPI versions.
- Active profile and group configuration.
- URL or document group name.
- File hash to verify integrity.

Example checksum generation:

~~~bash
sha256sum openapi-baseline.json
~~~

You can store the checksum in release metadata or an artifact manifest. Do not edit the baseline manually after release; if documentation needs correction, produce a new release artifact with a clear history.

## 6. Make the two exports comparable

To confirm that diffs come from dependencies, keep export conditions consistent.

Keep identical:
- Application source code, except for the migration changes under test.
- Active Spring profile.
- springdoc properties and OpenAPI configuration.
- Exported groups and endpoints.
- Context path and server URL.
- Jackson naming strategy, modules, and serializers.
- Security configuration and customizers.
- Configuration data used by customizers to build metadata.

If documents are generated in two different environments, the server URL or info.version may change even when the operation contract is unchanged. Record fields that intentionally vary by environment and distinguish them from contract changes.

Avoid letting documentation depend on unstable runtime data such as current timestamps, random hosts, the currently logged-in tenant, or non-deterministic collection iteration order. An OpenAPI document should generally be a deterministic artifact for a given build and document group.

If a customizer generates metadata per request or profile, verify whether it causes output differences between the two exports. Do not suppress every difference automatically; a new server URL or changed security scheme may be a real change that needs review.

## 7. Export the new document after upgrading

After updating dependencies and configuration, build the application in an environment equivalent to the baseline. Start the application with the designated export profile and download the corresponding documents.

Example:

The Maven command below assumes the lifecycle is configured to start the application, or that CI started the application in an earlier step. A build command does not open an HTTP server by itself if the project has not configured a start plugin; only call the export endpoint once the application is ready.

~~~bash
mvn -B clean verify
curl -fsS http://localhost:8080/v3/api-docs -o openapi-current.json
curl -fsS http://localhost:8080/v3/api-docs.yaml -o openapi-current.yaml
~~~

If running with Gradle:

~~~bash
./gradlew clean test bootJar
~~~

The Gradle tasks above build and test the artifact; the pipeline still needs a separate step to start the application before calling the OpenAPI endpoint.

Start the application using the CI profile, wait until the docs endpoint is ready, and then export the document. Do not call the endpoint before the application context finishes starting.

Produce the same list of artifacts as the baseline:
- Default document.
- Public/partner/internal groups if present.
- JSON or YAML matching the published formats.
- OpenAPI 3.0 or 3.1 according to current policy.

If the target migration intentionally changes the OpenAPI dialect, track that explicitly as a separate change. A diff between 3.0 and 3.1 can include many syntactic changes such as nullable and exclusive bounds; do not mix them with endpoint changes in an unclassified report.

## 8. Normalize before comparing

JSON objects do not depend on key ordering, so two files can have textual diffs while representing the exact same data. You can sort keys to reduce noise:

~~~bash
jq -S . openapi-baseline.json > openapi-baseline.sorted.json
jq -S . openapi-current.json > openapi-current.sorted.json
diff -u openapi-baseline.sorted.json openapi-current.sorted.json
~~~

Do not blindly sort every array. Element order in servers, tags, security, oneOf, anyOf, examples, or other lists can carry meaning for rendering, selection, or generators. Only normalize arrays when their semantics are understood and a clear convention exists.

Some fields can vary across environments, such as server URLs or build metadata. If you need to exclude them from comparison, create a normalized copy for analysis while preserving the original artifacts. Normalization rules must:
- Be reviewed and stored in the repository.
- Only strip fields explicitly identified as outside the contract under check.
- Never remove paths, methods, schemas, security, or responses just to make the diff cleaner.
- Never overwrite the original baseline or current artifacts.

A raw diff is useful for locating specific changes, but it does not replace a semantic OpenAPI diff. Use a validator to confirm the document is valid and a diff tool to classify changes by OpenAPI structure.

## 9. Run semantic comparison with an OpenAPI diff tool

You can use oasdiff to detect contract changes between baseline and current:

~~~bash
oasdiff diff openapi-baseline.json openapi-current.json
oasdiff breaking openapi-baseline.json openapi-current.json
~~~

Argument order must be consistent: the released document first, and the post-upgrade document in the current position. Pin the tool version in CI because rule sets can change across versions.

A diff tool can detect many structural changes such as:
- Removed paths or operations.
- Changed parameters or newly added required parameters.
- Modified request/response schemas.
- Changed types, required flags, enums, or constraints.
- Removed response codes or media types.
- Changed security requirements.
- Changed operationIds or component references depending on the rule set.

Read the report rather than looking only at the exit code. A tool may classify a change as breaking under general rules while the project has evidence that consumers do not use that part; conversely, the tool cannot know behavioral changes introduced by runtime code.

Do not disable an entire rule because of a single unrelated difference. If an exception is needed, document the exact path, operation, rule, and rationale, time-box it, and require review.

## 10. Check critical contract areas

When reviewing the diff, walk through the following areas:

| Area | Details to compare |
|---|---|
| Paths | Are all old paths still present? Did the base path or version prefix change? |
| Operations | Did HTTP methods, operationId, tags, or deprecation change? |
| Parameters | Name, location, required, type, style, explode, and constraints |
| Request body | Required flag, media type, schema, nullable, and additionalProperties |
| Responses | Status codes, content types, headers, and response schemas |
| Components | Schema names, $ref, enums, discriminators, and composition |
| Security | Schemes, scopes, and operation-level requirements |
| Servers | Base URLs, server variables, and environments |
| Metadata | OpenAPI version, info.version, external docs, and license |

A change may impact only generated SDKs without altering the wire format. For example, changing operationId can change method names in the SDK. Therefore, if the project distributes SDKs, run the generator and compile consumer fixtures to verify source compatibility.

Looking only at path counts or file size can miss major changes. A response property whose type changed may barely affect document size while still breaking clients.

## 11. Distinguish library-induced diffs from contract diffs

After upgrading springdoc, diffs may appear even when controller code has not changed. Investigate the root cause before modifying annotations or accepting the diff.

Common sources of change:

| Symptom | Possible cause | How to verify |
|---|---|---|
| Schema name changed | swagger-core naming/resolution changed | Compare component keys and $ref |
| Properties added/removed | Jackson version, visibility, or annotations | Check JSON serialization and DTOs |
| Different response codes | Annotation resolution or Spring mapping | Check controller annotations and runtime responses |
| Operations disappeared | Package/path scanning or handler mapping | Check Spring handler mappings and springdoc filters |
| Security changed | Security configuration or annotation processing | Compare SecurityFilterChain and OpenAPI security |
| OpenAPI dialect changed | Version configuration or new default | Check the openapi field and properties |
| Server URL changed | Proxy, forwarded headers, or profile | Compare environment and forwarded headers |
| UI fails to load document | UI config, path, or reverse proxy | Check Network tab and docs endpoint |

Do not fix diffs by adding annotations en masse before identifying the cause. Some changes may be library bug fixes or corrections to an inaccurate old contract. Compare output, source mappings, and runtime responses to choose the right action.

## 12. Inspect dependencies and eliminate conflicts

After switching starters, inspect the runtime classpath to ensure only one matching set of dependencies is present.

With Maven:

~~~bash
mvn dependency:tree -Dverbose -Dincludes=org.springdoc,io.swagger.core.v3
~~~

With Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency swagger-annotations --configuration runtimeClasspath
~~~

Verify:
- No legacy artifacts remain that duplicate the new starter's functionality.
- No unintended second web stack starter is present.
- swagger-core and swagger-annotations resolve via compatible dependency management.
- No old version overrides are left behind just to make the build pass.
- Jackson modules and the Spring Boot BOM are consistent.
- No dependency is stripped by an exclusion that causes missing classes at runtime.

If the application pulls in both MVC and WebFlux dependencies via another library, determine which stack actually serves the endpoints. Choose the springdoc starter matching the runtime web application; do not add both starters to see which one works.

Once the dependency tree is stable, compile, run tests, and start the actual application. A passing compile is not enough to confirm Swagger UI and /v3/api-docs work.

## 13. Verify runtime behavior after upgrading

Alongside the diff, run a live verification suite against the application:

1. Application context starts successfully.
2. /v3/api-docs returns valid OpenAPI JSON.
3. /v3/api-docs.yaml returns YAML if the project publishes YAML.
4. Every document group loads properly.
5. Swagger UI loads the document and renders operations.
6. Try it out calls the right server in the test environment.
7. Authentication and authorization preserve their behavior.
8. Critical controllers and functional routes remain registered.
9. Actual request/response serialization matches the schema.
10. Native image/AOT tests pass if the application ships a native executable.

Verify a representative set of operations:
- A GET with a path parameter.
- A POST with a request body and validation.
- An endpoint with a security requirement.
- A response containing an enum or generic wrapper.
- Error responses such as 400, 401, 403, or 404.
- One route belonging to each document group.

Do not merely check that the document contains the path. Invoke the endpoints in a test environment to confirm actual runtime mapping and responses.

## 14. Check OpenAPI 3.0/3.1 if the migration changes the dialect

If the upgrade also switches the OpenAPI version, review schema differences separately:

| Item | OpenAPI 3.0 | OpenAPI 3.1 |
|---|---|---|
| Nullability | nullable: true | type can include null |
| exclusiveMinimum | Boolean paired with minimum | Numeric threshold value |
| exclusiveMaximum | Boolean paired with maximum | Numeric threshold value |
| Schema dialect | Custom Schema Object subset | Full JSON Schema 2020-12 alignment |
| New keywords | Restricted to OAS 3.0 | More JSON Schema keywords supported |

Example of the same nullable property:

~~~yaml
# OpenAPI 3.0
description:
  type: string
  nullable: true
~~~

~~~yaml
# OpenAPI 3.1
description:
  type: [string, 'null']
~~~

Do not switch automatically just by changing the openapi field. Verify whether schemas, validators, API gateways, documentation portals, and code generators support the new dialect.

If you only want to upgrade springdoc without changing the dialect yet, set the OpenAPI version configuration explicitly and verify the output after the upgrade. This separates library impact from specification impact.

## 15. Build a comparison matrix and migration decisions

A migration table gives the review clear evidence:

| Component | Baseline | Post-upgrade | Classification | Action |
|---|---|---|---|---|
| GET /api/orders/{id} | Present | Present | No change | Keep |
| POST /api/orders request | customerId required | Added required source | Breaking | Fix contract or version |
| OrderResponse.total | number | string | Breaking | Restore type or major version |
| OrderStatus response enum | NEW, PAID | Added REFUNDED | Potentially breaking | Check strict consumers |
| Security scope | orders:read | orders:read | No change | Keep |
| Swagger UI URL | /swagger-ui.html | /swagger-ui/index.html | Deployment/UI change | Update links if intended |
| OpenAPI dialect | 3.0.3 | 3.1.0 | Specification migration | Validate toolchain |

Classification should include at least:
- **No change:** no meaningful differences.
- **Documentation-only:** description, summary, or example changed.
- **Additive:** added operation or optional input; consider strict clients.
- **Potentially breaking:** response enum, unknown property, operationId, or generator-dependent behavior.
- **Breaking:** previously valid requests fail, previous responses are no longer guaranteed, or existing routes/security changed.
- **Runtime-only:** code behavior changed without appearing in the OpenAPI document.

Each row needs a reviewer and a decision. Do not leave a large diff report without mapping rules to concrete actions.

## 16. Organize the migration in steps with rollback

An upgrade process can be divided into phases:

1. **Freeze baseline:** save the OpenAPI artifacts and dependency inventory of the current release.
2. **Review compatibility:** check release notes, Spring Boot/Java matrix, and artifact coordinates.
3. **Update dependencies:** swap starters and remove duplicate dependencies.
4. **Build and start:** compile, test, and start the application with the standard profile.
5. **Export current docs:** export JSON/YAML for all groups.
6. **Diff and classify:** run semantic diff, raw diff, and manual review.
7. **Runtime validation:** smoke test Swagger UI, API operations, and security.
8. **Consumer validation:** run contract tests and compile SDK fixtures if applicable.
9. **Release decision:** approve breaking changes, versioning, and the migration plan.
10. **Deploy and monitor:** monitor client errors, 4xx/5xx rates, old endpoint usage, and distributed documentation.

Keep the previous release's artifacts, dependency locks, and build configuration so rollback is reproducible. If the migration includes database or API behavior changes, rollback must consider both data and consumer traffic; reverting dependencies alone does not undo other runtime changes.

Do not publish new documentation to consumers before review is complete. The new artifact must correspond to the same server release so clients do not generate SDKs from an undeployed contract.

## 17. Integrate baseline and diff into CI

CI should generate documentation on every build and compare it against a policy-selected baseline. Example:

~~~mermaid
flowchart TD
    A[Checkout release baseline] --> B[Build current application]
    B --> C[Start with export profile]
    C --> D[Export JSON/YAML per group]
    D --> E[Validate OpenAPI documents]
    E --> F[Compare semantic diff]
    F --> G[Review breaking and potential changes]
    G --> H[Run API and SDK contract tests]
    H --> I[Store artifacts and report]
    I --> J[Approve release]
~~~

A minimal command sequence:

~~~bash
# Export current documentation
curl -fsS http://localhost:8080/v3/api-docs -o openapi-current.json

# Check differences against the released artifact
oasdiff breaking openapi-baseline.json openapi-current.json

# Save diff for reviewer inspection
oasdiff diff openapi-baseline.json openapi-current.json > openapi-diff.txt
~~~

A real pipeline needs to:
- Pin validator and diff tool versions.
- Fetch the baseline by release tag or designated artifact ID.
- Never use a baseline generated from the current build itself.
- Check all document groups.
- Retain current OpenAPI, baseline, and diff report files as build artifacts.
- Fail when unapproved breaking changes exist.
- Allow narrow exceptions with rationale, approver, and expiration.
- Run contract tests after evaluating the diff.

If no baseline exists yet for a new service, create the initial baseline from the approved release and record provenance. Never silently treat the first pull request's documentation as the released baseline.

## 18. Checklist before completing the upgrade

- [ ] Migration scope and changed components are clearly documented.
- [ ] Dependency inventory, Java, and Spring Boot versions are recorded.
- [ ] Target springdoc compatibility matrix is verified.
- [ ] Correct MVC or WebFlux starter is selected.
- [ ] Legacy or duplicate dependencies are removed.
- [ ] OpenAPI baseline from the released version is saved.
- [ ] All document groups used by consumers are saved.
- [ ] Baseline provenance and checksum are recorded.
- [ ] Both exports use the same profile and configuration.
- [ ] Post-upgrade OpenAPI JSON/YAML are exported.
- [ ] Documents are validated and semantic diff is compared.
- [ ] Paths, methods, parameters, request/response schemas, and security are reviewed.
- [ ] operationIds/schema names are checked if SDKs are generated.
- [ ] Swagger UI and documentation endpoints are verified.
- [ ] Appropriate API smoke tests, contract tests, and SDK compile tests have passed.
- [ ] OpenAPI 3.0/3.1 changes are separated from library changes if possible.
- [ ] Every breaking change has a version plan, migration path, and approval.
- [ ] Baseline, current document, and diff report are archived with the build.
- [ ] Rollback plan and post-deploy monitoring are in place.

## References

- [springdoc-openapi – Documentation](https://springdoc.org/): configuration, starters, OpenAPI endpoints, and version-specific guides.
- [springdoc-openapi – Migration guide](https://springdoc.org/): guide for migrating artifacts and configuration across major releases.
- [Spring Boot – Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html): dependency management and build systems.
- [Spring Boot – Supported Versions](https://spring.io/projects/spring-boot#support): lifecycle details and Spring Boot release lines.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html): OpenAPI contract structure.
- [oasdiff](https://github.com/Tufin/oasdiff): semantic diff and breaking change detection.
- [Semantic Versioning](https://semver.org/): major, minor, and patch versioning conventions.
