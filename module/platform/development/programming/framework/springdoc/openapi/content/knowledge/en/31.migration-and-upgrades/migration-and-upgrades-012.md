# Separating Library Compatibility Errors from Intentional API Contract Changes

When upgrading Spring Boot, Spring Framework, springdoc-openapi, or another foundational library, an application may encounter build errors, startup failures, runtime errors, or changes to the OpenAPI document. Not every difference shares the same root cause. An incompatible dependency error is an issue with the deployment platform; an intentional API contract change is a product decision affecting consumers.

These two problem classes must be investigated independently. Dependencies can be incompatible even when the HTTP contract does not change—for example, the app fails to start due to NoSuchMethodError. Conversely, all dependencies can be compatible and the app runs normally while the OpenAPI document changes in a breaking way—for example, a request property shifting from optional to required.

A sound investigation process must classify the error layer first, compare the dependency graph and OpenAPI contract, reproduce runtime behavior, and only then decide whether to fix dependencies or release a new API version. Never mask a linkage error by changing the contract, and never treat every change in the OpenAPI document as a library bug.

## 1. Distinguish the two compatibility axes

Library compatibility and API contract compatibility are two separate questions:

| Axis | Question to answer | Primary evidence |
|---|---|---|
| Library compatibility | Can Java/Spring components compile, link, and run together? | Dependency graph, compiler, classpath, startup logs, runtime tests |
| API contract compatibility | Can existing clients continue sending requests and parsing responses as before? | OpenAPI JSON/YAML, HTTP behavior, consumer contract tests |

Four scenarios can occur:

| Libraries | HTTP contract | Example |
|---|---|---|
| Compatible | Unchanged | Dependency patch upgrade; build and contract both hold |
| Incompatible | Unchanged by design | Application fails linkage before serving requests |
| Compatible | Changed | Controller runs normally, yet schema or response changed |
| Incompatible | Changed | Platform upgrade breaks runtime while new document breaks older clients |

Do not use a single result to judge both axes. A passing build does not prove the contract is stable; an OpenAPI diff does not prove the dependency graph is compatible.

## 2. Distinguish source, binary, runtime, and behavioral compatibility

The term "library compatibility" has multiple levels:

| Level | Meaning | Common error signs |
|---|---|---|
| Source compatibility | Old source still compiles against new dependencies | Missing imports, changed method signatures |
| Binary compatibility | Already-compiled classes still link against the new library | NoSuchMethodError, NoSuchFieldError, AbstractMethodError |
| Runtime compatibility | Application starts and integrated components operate | Auto-configuration failures, missing beans, class loading failures |
| Behavioral compatibility | Runtime behavior preserves expected semantics | Different serialization, different validation, different converter chosen |

A library can keep binary compatibility while changing default behavior. For instance, a Jackson upgrade may preserve method signatures while the application's naming/serialization settings change due to a different module or ObjectMapper.

Conversely, source code may require import updates after a major release even though the HTTP contract stays intact. That is an implementation-layer migration, not necessarily an API version change.

## 3. Identify dependency compatibility errors by symptoms

The following errors typically point to dependencies or classpath issues:

| Symptom | Common meaning | First check |
|---|---|---|
| package ... does not exist | Source imports a package missing from compile classpath | Dependency version and API reference |
| cannot find symbol | Class/method/field is missing or signature changed | Javadoc and resolved dependencies |
| ClassNotFoundException | Code requests a class the classloader cannot find | Runtime classpath and packaged artifact |
| NoClassDefFoundError | Required class could not be defined/loaded at runtime | Missing dependency or earlier class initialization failure |
| NoSuchMethodError | Bytecode calls a method missing on the loaded class | Class version at runtime |
| NoSuchFieldError | Bytecode references a field missing on the runtime class | Dependency conflict or binary mismatch |
| AbstractMethodError | Runtime implementation lacks an abstract method expected by caller | Interface/implementation versions |
| IncompatibleClassChangeError | Class/interface structure changed incompatibly | Major versions and class origins |
| ApplicationContext creation error | Incompatible auto-configuration or bean integration | Condition report, stack trace, and dependency graph |

The error name is a clue, not a final diagnosis. NoClassDefFoundError sometimes appears after an earlier class initialization error; always read the first root cause in the logs.

## 4. Identify API contract changes

Contract changes typically manifest in one or more of these elements:

- Path or HTTP method removed/changed.
- Parameter name, location, or type changed.
- New required request property introduced.
- Response property removed or type changed.
- Response enum drops values or adds new values old clients cannot handle.
- Status code or media type changed.
- New security requirement applied.
- Pagination, sorting, filtering, or idempotency behavior changed.
- Error response switched to a different schema.

The application may compile and start cleanly in all of these cases. Consumers can still break because old requests become invalid or parsers fail on the new response.

## 5. Distinguish implementation changes from contract changes

Not every source code change is an API change.

| Source change | Can the contract stay intact? | What to verify |
|---|---|---|
| Rename Java method while keeping mapping | Yes | Path, operationId, and customizers |
| Split controller into multiple classes | Yes | Mappings, tags, groups, and security |
| Move DTO package while keeping JSON intact | Yes | Jackson output and schema |
| Upgrade springdoc while keeping controllers | Yes, though schema generation may change | OpenAPI diff |
| Rename JSON property | Usually breaking | Request/response payloads |
| Rename query parameter | Usually breaking | Request mapping and OpenAPI |
| Add optional response field | Usually additive, check strict clients | Consumer parsers and schemas |
| Add required request field | Breaking for older clients | Request schema and validation |
| Change authentication scheme | Potentially breaking | Security requirements and gateways |

The key is comparing wire-level behavior: HTTP requests/responses and the OpenAPI document. Never treat source code diffs as a proxy for contract diffs.

## 6. Example: springdoc upgrade changes the document while dependencies stay compatible

Suppose an application upgrades springdoc within the same major version. Maven/Gradle resolves cleanly, the application starts, and /v3/api-docs returns 200. Both example documents use OpenAPI 3.0, yet a schema property changes from:

~~~yaml
status:
  type: string
  nullable: true
~~~

to:

~~~yaml
status:
  type: string
~~~

This may stem from how the library infers nullability or Jackson metadata. Dependencies may be completely source/binary/runtime compatible, yet the generated contract changed. If the OpenAPI dialect also switched from 3.0 to 3.1, apply each dialect's null representation before concluding the two schemas differ semantically.

Investigation steps:

1. Compare the OpenAPI document before and after upgrading.
2. Inspect the Java type, @Schema annotations, Jackson, and validation on the property.
3. Confirm whether runtime JSON actually permits null.
4. Read release notes for the upgraded springdoc, Swagger Core, Jackson, and Spring Boot versions.
5. Run consumer tests with null payloads and payloads omitting the property.
6. Accept the change only if the new semantics represent an intentional, published decision.

Do not tweak the dependency graph if dependencies already resolved cleanly and the issue actually lies in schema semantics. Likewise, do not force the old schema via a customizer when runtime behavior already changed without first deciding the desired contract.

## 7. Example: incompatible dependencies without intentional contract changes

Suppose an application uses Spring Boot and a compatible Springdoc module. A dependency override causes swagger-core or a Spring Framework module to load at a mismatched version. The application fails to start with NoSuchMethodError.

In this scenario:

- Consumers cannot send requests because the server does not start.
- There is no evidence that the API contract was changed.
- The OpenAPI document may not even be generated.
- The fault must be fixed in dependency management/classpath.

Workflow:

1. Grab the initial stack trace and identify the failing class/method.
2. Inspect dependency tree or dependencyInsight.
3. Locate the directly or transitively overridden version.
4. Restore the dependency set supported by the Spring Boot BOM and Springdoc compatibility matrix.
5. Build, start up, and fetch the OpenAPI document.
6. Compare the document against the baseline to verify the contract did not drift unintentionally.

Never create an API v2 in response to a classpath error. Changing the API version does not fix a NoSuchMethodError.

## 8. Inspect the dependency graph in Maven

Inspect relevant dependencies:

~~~bash
./mvnw dependency:tree -Dincludes=org.springframework,org.springframework.boot,org.springdoc,io.swagger.core.v3,com.fasterxml.jackson.core
~~~

View the POM configuration after applying parents, profiles, and dependency management:

~~~bash
./mvnw help:effective-pom
~~~

Look for warning signs:

- Multiple major versions of Springdoc coexisting.
- Swagger Core forced to a version different from what the starter manages.
- Spring Framework modules out of sync.
- Mismatched Jackson core/databind/annotations versions.
- Legacy libraries pulling in the javax namespace in Boot 3/4 apps.
- Exclusions stripping a required runtime dependency.

Prefer the Spring Boot parent/BOM and the project's dependency management. Only override a dependency with a concrete reason, known compatibility range, and verifying tests.

## 9. Inspect the dependency graph in Gradle

Use dependencyInsight to see why Gradle chose a version:

~~~bash
./gradlew dependencyInsight --dependency springdoc-openapi --configuration runtimeClasspath
./gradlew dependencyInsight --dependency swagger-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
~~~

View the runtime graph:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

If the project has multiple modules, run the command in the module containing the application or the configuration that actually resolves dependencies. compileClasspath can differ from runtimeClasspath; testRuntimeClasspath can also contain dependencies absent in production.

When using a version catalog or platform, distinguish requested versions from finally resolved versions. Do not look only at libs.versions.toml and conclude the classpath used the right version.

## 10. Use BOMs and constraints to manage a consistent dependency set

The Spring Boot BOM manages a set of versions tested together. In Maven, this typically means using the Spring Boot parent or importing spring-boot-dependencies. In Gradle, use the Spring Boot plugin and dependency management/platform per project structure.

Guidelines:

- Let Spring Boot manage Spring Framework modules.
- Select springdoc per the Boot minor version's compatibility matrix.
- Avoid bumping Swagger Core independently when the springdoc starter already manages it.
- Avoid mixing Jackson modules from different release trains.
- Document the rationale whenever using constraints or forced versions.

A BOM does not guarantee every third-party library is compatible. It manages only dependencies within the BOM's scope. Add-ons, plugins, and internal libraries still require verification.

## 11. Identify the classes actually loaded at runtime

The dependency tree shows build-time resolution, yet production may run a JAR or container image built from another commit.

For an executable JAR:

~~~bash
jar tf application.jar
~~~

Check libraries nested under BOOT-INF/lib. If you suspect duplicate classes or loading from an unexpected location, print the class origin in Java:

~~~java
System.out.println(
        OrderController.class
                .getProtectionDomain()
                .getCodeSource()
                .getLocation()
);
~~~

Substitute the example class with the failing class. On supported JDKs, enable class loading logs to see where classes load from:

~~~bash
java -Xlog:class+load=info -jar application.jar
~~~

Do not inspect only workspace sources. The decisive evidence is the class loaded inside the failing process.

## 12. Create an OpenAPI baseline before upgrading libraries

Before changing dependencies, save the running release's OpenAPI JSON/YAML:

~~~bash
curl -fS http://localhost:8080/v3/api-docs -o openapi-before.json
~~~

After upgrading dependencies and starting the new build:

~~~bash
curl -fS http://localhost:8080/v3/api-docs -o openapi-after.json
~~~

Feed both files into an OpenAPI diff tool to detect changes in:

- Paths and HTTP methods.
- Parameter names, locations, required flags, and schemas.
- Request bodies, media types, and encoding.
- Response statuses, headers, media types, and schemas.
- Required properties, nullability, enums, and formats.
- Security schemes and requirements.
- Servers, tags, and operationIds.

Plain text diffs can report differences from key order or formatting. An OpenAPI-aware tool distinguishes structural shifts from real contract changes.

## 13. Classify OpenAPI changes by impact level

Certain changes are typically considered breaking for consumers:

| Change | Risk to existing clients |
|---|---|
| Remove path or HTTP method | Clients can no longer call the operation |
| Change path or parameter name | Existing requests fail to match |
| Change query parameter to header | Clients send value in the wrong location |
| Add required request property | Existing requests become invalid |
| Change request property to incompatible type | Server may reject payloads |
| Remove response property | Clients relying on the field may fail |
| Change response property type | Client parsers or logic may fail |
| Narrow accepted enum | Existing requests may be rejected |
| Change response media type | Clients fail to parse body |
| Increase security requirements | Existing clients lack required credentials |

Some seemingly additive changes can still break consumers:

- Adding an enum value to a response can break clients using exhaustive switches.
- Adding a response field can cause strict parsers to reject JSON.
- Changing default page size can alter results observed by clients.
- Changing default sorting order can break downstream workflows even with an identical schema.

Therefore, compatibility is not just schema comparison. You must examine semantics and how consumers actually use the API.

## 14. Distinguish breaking changes from additive changes

The following changes generally have better compatibility, though real clients still need checking:

- Adding a new endpoint without modifying old endpoints.
- Adding an optional query parameter with a safe default.
- Adding an optional response property.
- Adding a new response status for an error path consumers already handle.
- Updating descriptions or examples without changing semantics.

There is no rule that "every new field is safe." For response JSON, clients with strict parsers may reject unknown fields. For enums, clients may assume a closed value set. For query parameters, changing a default can alter behavior even while the parameter remains optional.

Identify your consumers' compatibility policy: tolerant reader, strict schema validation, generated client, or direct integration.

## 15. Determine whether a change is intentional or accidental

A contract change is considered intentional when backed by decision evidence:

- A product requirement or ADR explaining the reason.
- API owner confirmation of the new semantics.
- Affected consumers identified.
- A versioning/deprecation plan selected.
- OpenAPI diff reviewed.
- Migration guide or consumer notice with clear content.
- Tests verifying new and old behavior during a transition period if needed.

Without this evidence, treat the difference as an unintended change requiring investigation. Never label something an "intentional breaking change" merely because new code was already merged.

## 16. When should the API version be bumped?

If a change is breaking and consumers cannot migrate immediately, a clear versioning policy is needed. Depending on the product, you can:

- Release a new major API version.
- Keep the old endpoint running in parallel during the migration window.
- Add the new endpoint and then deprecate the old one.
- Version in the path, header, or media type per published conventions.

No single versioning strategy fits every system. What matters is that consumers can tell which contract they are using and its support window.

Changing info.version in OpenAPI does not automatically create new routes or separate runtime behavior. If API versioning uses /v1 and /v2 paths, the application must genuinely implement both corresponding routes/contracts.

## 17. Deprecation requires a roadmap

When replacing an old operation with a new one:

1. Publish the new operation and migration examples.
2. Mark the old operation deprecated in OpenAPI.
3. Notify consumers, owners, and the transition deadline.
4. Monitor traffic still hitting the old operation if telemetry is available.
5. Remove the old operation only after published sunset conditions are met.

Example:

~~~java
@Operation(
        summary = "Look up order by legacy ID",
        deprecated = true,
        description = "Use GET /api/v2/orders/{orderId} for new integrations."
)
~~~

The annotation only marks metadata. Decommissioning the endpoint must happen separately according to the announced schedule and policy.

## 18. Inspect JSON behavior rather than only reading schemas

A dependency update can alter serialization even when DTO sources did not change. Serialize representative objects using the application's actual ObjectMapper:

~~~java
String json = objectMapper.writeValueAsString(orderResponse);
System.out.println(json);
~~~

Check the JSON against:

- Property names.
- Ignored or read-only properties.
- Null inclusion.
- Date/time formats.
- Enum serialization.
- Polymorphic type metadata.
- Custom serializers/deserializers.

For requests, test deserializing old payloads to confirm the new server still accepts them. For responses, test serialization to confirm old clients can still parse them.

OpenAPI schemas and Jackson output must stay consistent. A schema diff cannot be explained without inspecting the actual JSON.

## 19. Use consumer contract tests to verify impact

Contract tests must verify what consumers rely on, such as:

- Older clients sending old requests still receive expected responses.
- Required fields and enum values are handled properly.
- Authentication flows continue working.
- Error responses preserve required schemas and statuses.
- Pagination, sorting, and default behaviors do not shift unexpectedly.

Example checking a legacy request with MockMvc:

~~~java
@Test
void legacyCreateOrderRequestRemainsAccepted() throws Exception {
    mockMvc.perform(post("/api/orders")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "customerCode": "CUS-10025",
                              "items": [
                                {"productCode": "P-01", "quantity": 2}
                              ]
                            }
                            """))
            .andExpect(status().isCreated());
}
~~~

This is only an example; adapt endpoints and payloads to your real contract. If an intentional change invalidates old requests, update tests alongside the migration/versioning plan rather than simply deleting failing tests without recording the impact.

## 20. Check the OpenAPI contract in CI

CI can archive documents generated from the current commit and compare them against the release branch's baseline:

1. Build the application with locked dependencies.
2. Start the test application.
3. Fetch /v3/api-docs.
4. Validate the document against the corresponding OpenAPI version.
5. Run an OpenAPI diff against the baseline.
6. Classify breaking/additive changes.
7. Require API owner review for breaking changes.
8. Run consumer contract tests.

Use OpenAPI diff/lint tools fitting your organization's workflow. Do not treat a diff tool's exit code as the final product decision if the tool cannot understand semantics like defaults, enum handling, or strict client behavior.

## 21. Diagnostic matrix by error type

| Build | Startup/runtime | OpenAPI diff | Initial conclusion |
|---|---|---|---|
| Fail | Not runnable | None | Prioritize source/dependency compatibility |
| Pass | Fails on startup | None | Prioritize runtime classpath/auto-configuration |
| Pass | Pass | Unchanged | Dependency update looks clean; continue behavioral testing |
| Pass | Pass | Changed | Investigate schema/contract drift |
| Pass | Pass | Approved breaking change | Execute versioning and migration plan |
| Pass | Pass | Unapproved breaking change | Treat as unintended regression |
| Pass | Pass | Unchanged yet consumers fail | Inspect semantics, serialization, and runtime behavior |

This matrix guides the investigation direction. Final conclusions must rest on stack traces, the dependency graph, documents, and actual requests/responses.

## 22. End-to-end investigation workflow

1. Record commit, Spring Boot, Java, springdoc, and related dependencies before/after the change.
2. Classify the error as compile, startup, runtime, or consumer behavior.
3. If linkage errors occur, identify the failing class/method and class origin.
4. Compare dependency tree or dependencyInsight against the baseline.
5. Verify BOM, constraints, exclusions, and actually packaged artifacts.
6. If the app runs, fetch before/after OpenAPI JSON and run a semantic diff.
7. Compare schemas against runtime JSON and request binding.
8. Run consumer contract tests.
9. Determine whether contract changes are intentional or accidental based on ADRs/approvals.
10. If accidental, fix dependencies or restore the contract.
11. If intentional and breaking, publish a versioning/migration/deprecation plan.
12. Record evidence and test results in the change review.

## 23. Practices that make problems harder

- Upgrading Spring Boot, springdoc, Jackson, and Swagger Core simultaneously without saving a baseline.
- Adding an old dependency to mask a NoSuchMethodError.
- Forcing transitive versions without checking the BOM and runtime classpath.
- Patching schemas via a customizer before verifying runtime JSON.
- Changing API paths/versions to dodge a dependency-driven startup error.
- Treating every OpenAPI diff as breaking without evaluating semantics.
- Treating every new field as additive without checking strict consumers.
- Deleting a consumer test because it failed after migration without classifying the cause.
- Marking an operation deprecated without a deadline or migration path.

Each fix should address the right layer and be backed by verifying tests.

## 24. Checklist before concluding migration success

- [ ] Source compiles against the new dependencies.
- [ ] Spring Boot and springdoc are within the published compatibility range.
- [ ] No mixed major versions of Springdoc, Spring Framework, or Swagger Core.
- [ ] Runtime classpath matches the reviewed dependency graph.
- [ ] Application starts and OpenAPI endpoints respond normally.
- [ ] OpenAPI document diffed against the baseline.
- [ ] Every breaking change has a clear owner and decision.
- [ ] JSON serialization/deserialization verified.
- [ ] Legacy requests and responses verified via consumer tests.
- [ ] Security, error responses, and pagination semantics verified.
- [ ] API versioning/deprecation plan published if needed.
- [ ] CI archives documents and validates contracts on subsequent changes.

## 25. Design principles

- Separate library compatibility from API contract compatibility.
- Distinguish source, binary, runtime, and behavioral compatibility.
- Use the dependency graph and class origins to prove library errors.
- Use OpenAPI diffs and HTTP tests to prove contract changes.
- Save an OpenAPI baseline before any dependency upgrade affecting generation or serialization.
- Manage Spring Framework through the Spring Boot BOM when appropriate.
- Select springdoc per the Spring Boot minor version's compatibility matrix.
- Never override a dependency just to silence a linkage error.
- Treat a breaking change as intentional only with a decision, owner, and consumer migration plan.
- Use versioning/deprecation to manage intentional changes.
- Integrate dependency checks and contract tests into CI.

## Conclusion

Library compatibility errors and API contract changes can appear together yet must be diagnosed separately. Dependency faults leave evidence in the compiler, classpath, stack traces, or startup; contract drift appears in OpenAPI diffs and runtime requests/responses. Inspect both the dependency graph and actually loaded classes, while capturing and comparing pre- and post-upgrade OpenAPI documents. If a difference is unapproved, treat it as a regression. If a change is intentional and breaking, publish a new version or an appropriate deprecation roadmap. Conclude a migration is successful only when build, runtime, OpenAPI contract, and consumer tests all pass.

## References

- [Spring Boot Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html)
- [Springdoc-openapi documentation and compatibility matrix](https://springdoc.org/)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
- [Maven Dependency Plugin](https://maven.apache.org/plugins/maven-dependency-plugin/)
- [Gradle dependencyInsight](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
- [Java binary compatibility and linkage errors](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/LinkageError.html)
