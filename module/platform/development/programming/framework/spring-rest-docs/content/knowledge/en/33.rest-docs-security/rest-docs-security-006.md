# Distinguishing Synthetic Test Data from Real Data

## 1. Why Must Test Data Be Separated from Real Data?

Spring REST Docs records HTTP requests and responses from tests to generate API documentation. Consequently, test data can appear in `http-request.adoc`, `request-body.adoc`, `http-response.adoc`, field snippets, custom snippets, and CI artifacts. If tests use copies of production data or active credentials, documentation can inadvertently expose personal information, business secrets, or system access privileges.

In **SPRING_REST_DOCS**, HTTP tests using MockMvc, WebTestClient, or REST Assured produce evidence for requests, responses, payloads, parameters, and headers. The **Security** chapter teaches how to protect the data used for testing and documentation. This lesson focuses on distinguishing synthetic test data from real data, creating safe fixtures, understanding the limits of anonymization, and maintaining test representativeness.

After this lesson, you will be able to:

- Distinguish synthetic data, mock data, and production data.
- Select safe fixtures for HTTP documentation tests.
- Avoid using real tokens, passwords, PII, or files in tests.
- Understand why deleting names or replacing emails does not necessarily anonymize data.
- Create deterministic data that remains diverse enough to validate contracts.
- Inspect generated snippets and CI artifacts before sharing.

## 2. Common Data Categories

| Data Type | Definition | Example | Usage |
| --- | --- | --- | --- |
| Synthetic data | Newly generated data not copied from real individuals' records | `user-001`, `user@example.test`, dummy orders | Preferred for tests and documentation |
| Mock/stub data | Values returned by test doubles to control an interaction | Mock service returning `Product(id=42)` | Integration tests at mocked boundaries |
| Anonymized data | Real data transformed to remove identifiability | Dataset processed through an approved anonymization workflow | Use only with an approved process and risk assessment |
| Pseudonymized data | Direct identifiers replaced with another code, still linkable via auxiliary info | Customer ID replaced by tokenized code | Must still be treated as sensitive data |
| Production data | Data collected from real users/systems | Live emails, addresses, active tokens | Never place directly in test fixtures or docs |

Synthetic data is usually the best choice for generated documentation. It allows you to choose meaningful, stable values that carry no real user information. Mock data is useful when isolating services, but mock tests must be distinguished from full HTTP integration tests: mocks do not prove the entire system processes data the same way as production.

Anonymization and pseudonymization are not the same. Pseudonymization replaces direct identifiers, yet records can still be re-linked. Even a dataset with names removed can identify an individual through combinations of birth dates, addresses, transaction histories, or rare attributes.

## 3. Principles for Creating Synthetic Data

A good synthetic fixture must be both safe and useful for tests:

1. **Do not derive from real personal records.** Generate data from rules or generators rather than copying a customer and changing the name.
2. **Use reserved testing domains.** For example, `user@example.test`; never send emails to real people's addresses.
3. **Use credentials that are invalid outside the test environment.** Tokens, API keys, and passwords must be dummy values or valid only inside an isolated sandbox.
4. **Stay deterministic when comparisons are needed.** Deterministic fixtures prevent snippets and snapshots from changing randomly on every run.
5. **Include deliberate diversity.** Cover boundary values, Unicode, long strings, null/optional fields, nested objects, and error cases.
6. **Keep secret data out of filenames and metadata.** Filenames, URLs, comments, and logs can also be recorded in snippets.

Example JSON fixture:

```json
{
  "customerId": "CUST-TEST-0042",
  "email": "linh.nguyen@example.test",
  "displayName": "Nguyen Linh Test",
  "phone": "+12025550142"
}
```

The values above are created for illustration; they are not taken from real customers. For phone numbers, use ranges reserved for examples/testing according to your deployment region to avoid accidentally calling real subscribers.

## 4. Do Not Use Real Credentials in Documentation Tests

Authentication tests do not need production credentials. You can use:

- Mock security principals or test authentication support.
- JWTs signed with a dedicated test key not trusted in production.
- Dummy API keys that exist only in the test profile.
- A dedicated OAuth sandbox with minimal permissions and synthetic data.

Example request with a dummy token:

```java
String testToken = "test-only-token-123";

mockMvc.perform(get("/api/profile")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + testToken)
        .accept(MediaType.APPLICATION_JSON))
    .andExpect(status().isOk())
    .andDo(document("profile-get",
        preprocessRequest(
            modifyHeaders().set(
                HttpHeaders.AUTHORIZATION,
                "Bearer <access-token>"
            )
        )
    ));
```

The test still sends the dummy token to traverse the security layer; the preprocessor replaces the value in the recorded snippet. These two controls serve different purposes: dummy data reduces blast radius if redaction is forgotten, while preprocessing ensures the documentation shows the contract without storing credential values.

Do not pull secrets from production environment variables just because CI can access them. If integration tests need a sandbox secret, provision it per pipeline with restricted permissions, expiration, and restricted log/artifact read access; never put that value into snippets.

## 5. Personal Data and Re-Identifiable Data

PII is not limited to names and emails. The following attributes can identify individuals directly or in combination:

- Phone numbers, street addresses, dates of birth, and identification numbers.
- Coordinates, location histories, or rare timestamps.
- Customer numbers, contract numbers, and transaction IDs.
- Free-form text in notes, filenames, or metadata.
- Attribute combinations such as a small geographic area, occupation, and transaction date.

Replacing `name` with `Customer A` is insufficient if the address, contract number, or traceable notes remain intact. Do not load production data into fixtures and simply strip a few columns.

If the organization needs near-production data for compatibility testing, it must follow an approved process: data classification, re-identification risk assessment, transformation or synthesis, access restrictions, retention limits, and re-verification before publication. Pseudonymized datasets must still be protected as re-linkable data.

## 6. Creating Stable Fixtures for Spring REST Docs

Generated snippets are often reviewed in Git. If fixtures generate random values on each run, documentation diffs become noisy. Use fixed values for key operations:

```java
final class ProductFixtures {

    static CreateProductRequest validRequest() {
        return new CreateProductRequest(
            "Mechanical Keyboard",
            1_290_000,
            "catalog@example.test"
        );
    }

    static ProductResponse response() {
        return new ProductResponse(
            42L,
            "Mechanical Keyboard",
            1_290_000,
            true
        );
    }
}
```

Factories should return dummy, readable data that is stable enough for documentation. For tests covering multiple scenarios, create separate fixtures per case rather than mutating a single large object randomly.

### 6.1. Testing Boundary Values

A single fixture does not cover the entire contract. Create dedicated cases:

| Case | Example | Purpose |
| --- | --- | --- |
| Valid value | `name = "Keyboard"` | Primary documentation example |
| Empty string | `name = ""` | Verify `@NotBlank` |
| Maximum length string | 120 characters | Verify length limits |
| Unicode | `Bàn phím cơ` | Verify encoding and rendering |
| Boundary value | `price = 1` | Verify lower bound |
| Invalid value | `price = -1` | Verify validation error |
| Optional field omitted | Omit `description` | Verify optional semantics |

You do not need to include every fixture on the main documentation page. Multiple tests can verify the contract while only successful requests and representative error responses are selected to generate snippets.

## 7. File Uploads and Binary Fixtures

For multipart APIs, never use profile photos, scanned IDs, contracts, or real customer files as fixtures. Create small synthetic files containing no personal metadata, or use public sample files with appropriate usage rights.

Example:

```java
MockMultipartFile image = new MockMultipartFile(
    "image",
    "sample-product.png",
    MediaType.IMAGE_PNG_VALUE,
    TestFiles.validPngBytes()
);
```

Check file metadata as well: filenames, EXIF data, authors, comments, embedded thumbnails, and document properties can contain personal information. Renaming a file does not remove embedded metadata.

Custom snippets for uploads usually only need part name, media type, and size. Do not put raw bytes or entire file contents into tables. When a sample file is required, use a synthetic fixture stored in test resources and review the fixture's contents before committing.

## 8. Synthetic Data Must Accurately Reflect the Contract

Safe does not mean arbitrary. Overly simplistic fixtures can hide real bugs:

- Using only ASCII can miss Unicode/UTF-8 bugs.
- Using only short strings can miss length constraints.
- Using only sequential IDs can miss UUIDs or real ID formats.
- Using only success responses can miss error contracts.
- Mocking services everywhere can miss serializers, converters, or database constraints.

Design fixtures according to real schemas and rules without copying real records. You can use generators that produce statistically similar distributions, provided they do not generate copies or data linkable to specific individuals. For public documentation, choose representative and understandable values.

## 9. Separating Test and Production Environments

Never allow test configurations to accidentally connect to production:

- Use a dedicated profile, such as `test` or `docs`.
- Use separate databases/schemas and synthetic seed data.
- Use mock servers or sandboxes for external services.
- Disable real email/SMS delivery or route to an internal sink.
- Separate test buckets/object storage from production.
- Use dedicated JWT signing keys; production must not trust test keys.
- Restrict network egress for documentation test jobs when possible.

Example property in a test profile:

```yaml
app:
  storage:
    bucket: spring-rest-docs-test
  notifications:
    delivery-mode: disabled
```

Property names are illustrative; the application must implement the corresponding configuration. Do not rely on the profile name to guarantee safety if a bean or client still points to a production endpoint.

## 10. Verifying Generated Snippets Contain No Real Data

After tests generate snippets, inspect the output directory. Example:

```java
Path operationDir = snippetsDir.resolve("profile-get");

try (Stream<Path> paths = Files.walk(operationDir)) {
    List<String> files = paths
        .filter(Files::isRegularFile)
        .map(path -> {
            try {
                return Files.readString(path);
            } catch (IOException ex) {
                throw new UncheckedIOException(ex);
            }
        })
        .toList();

    assertThat(files)
        .noneMatch(content -> content.contains("production-access-token"))
        .noneMatch(content -> content.contains("real.customer@example.com"));
}
```

This example uses AssertJ; checked strings should be test-only sentinels, not real secrets. With synthetic fixtures, you can assert that expected dummy values appear and forbidden sentinels do not. Do not record sensitive values in assertion failure messages.

Scan custom snippets, `http-request`, headers, bodies, and final output. If Asciidoctor builds complete documentation, also inspect the publish directory because content may be copied or transformed during rendering.

## 11. When Is Anonymized Data Still Unsuitable?

Do not assume masked data is automatically safe to include in documentation. Consider:

1. Is there a mapping table or secondary key that allows identity recovery?
2. Is there a rare combination of attributes that allows an individual to be identified?
3. Does free-form text contain names, emails, account numbers, or confidential information?
4. Do files contain metadata or embedded data?
5. Is the data restricted by contracts, regulations, or internal policies?
6. Do documentation or artifact readers have broader access than the source system?

If you cannot assess the risk, do not include that dataset in generated documentation. Creating a synthetic fixture instead is usually simpler and safer.

## 12. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Real email appears in snippet | Fixture copied from production | Replace with a synthetic address and audit history |
| Test token has production permissions | Reused environment secret | Create dedicated credentials for test/sandbox |
| Name removed yet person still identifiable | Address, timestamps, or rare attributes remain | Assess re-identification risk; prefer synthetic data |
| Snippet changes on every build | Unseeded random fixture generation | Use deterministic fixtures for docs |
| Tests miss Unicode bugs | Used only ASCII data | Add Unicode fixtures and encoding cases |
| File fixture exposes metadata | Only renamed the filename | Inspect EXIF/document properties and create a fresh file |
| Test profile calls production service | Changed profile name while endpoint still points to production | Verify wiring, network, and credentials |
| Custom snippet dumps entire object | Did not limit rendered fields | Use an allowlist model |
| Scanner misses personal data | Pattern scanner cannot recognize all PII | Combine synthetic fixtures, reviews, and specialized checks |

## 13. Asciidoctor and Build/CI

Documentation includes snippets as usual:

```adoc
= Product API
:toc: left

== Create Product

=== Request
include::{snippets}/products-create/http-request.adoc[]

=== Request fields
include::{snippets}/products-create/request-fields.adoc[]

=== Response
include::{snippets}/products-create/http-response.adoc[]
```

With Gradle and the configured Asciidoctor plugin:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
}
```

Recommended pipeline:

```text
Documentation tests
        |
        v
Synthetic fixtures + test credentials
        |
        v
HTTP assertions + Spring REST Docs snippets
        |
        v
Secret/PII checks on generated files
        |
        v
Asciidoctor / Markdown build
        |
        v
Artifact review and publish
```

CI needs to verify that jobs use test profiles and test endpoints, no unintended connections to production occur, fixtures contain no real data, and generated artifacts pass checks. A secret scanner does not replace data classification or fixture review.

## 14. Practice Exercise

For the `POST /api/products` endpoint:

1. Create DTO fixtures via a synthetic factory without reading production data.
2. Use an email under the `.test` domain, dummy IDs, and Unicode data.
3. Create credentials valid only in tests to exercise authentication.
4. Create a valid JSON fixture and separate boundary/invalid cases.
5. Create a synthetic PNG image; inspect its filename and embedded metadata.
6. Run the MockMvc test and generate request/response snippets.
7. Scan the entire operation directory for forbidden sentinels.
8. Verify the custom snippet renders only allowlisted fields.
9. Confirm the docs profile does not connect to production databases, email, storage, or APIs.
10. Run Asciidoctor in CI and inspect artifacts before publishing.

### Self-Assessment Questions

- How does synthetic data differ from pseudonymized data?
- Why is removing names and emails not necessarily enough to anonymize data?
- Why should documentation tests use dedicated test credentials?
- How do you build deterministic fixtures that still test boundary values?
- Where can uploaded files contain sensitive information besides their main bytes?
- Why does mock data not prove full production integration?
- What should CI verify besides a successful Asciidoctor build?
- When is a separate approval workflow required for an anonymized dataset?

**Remember:** Prefer newly generated synthetic data for tests and documentation. Pseudonymized data can still be re-linked; production data with a few stripped fields may still be identifiable. Use deterministic fixtures, dedicated test credentials, isolated environments, and inspect generated artifacts before sharing.

## References

- [Spring REST Docs — Documenting Your API](https://docs.spring.io/spring-restdocs/reference/documenting-your-api.html): workflow for generating snippets from HTTP tests.
- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html): preprocessing requests/responses before writing snippets.
- [NIST Privacy Framework](https://www.nist.gov/privacy-framework): managing privacy risks and identifiable data.
- [NIST SP 800-188 — De-Identifying Government Datasets](https://csrc.nist.gov/pubs/sp/800/188/final): technical considerations and risks in de-identification.
- [OWASP Secrets Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html): managing credentials and secrets.
