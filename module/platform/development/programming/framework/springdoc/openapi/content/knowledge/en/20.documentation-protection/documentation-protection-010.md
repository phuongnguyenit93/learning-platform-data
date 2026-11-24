# Removing Tokens, Personal Data, and Infrastructure Addresses from Published Content

OpenAPI specifications and Swagger UI help clients understand how to call an API, yet these same documents can leak sensitive information if examples, descriptions, server URLs, or metadata are written from real data. An access token copied into a cURL example, a personal email in a sample response, an internal hostname in `servers`, or an administrative address in `externalDocs` can all become public information once documentation is published.

With springdoc-openapi, documentation content is assembled from annotations on controllers/DTOs, OpenAPI configuration, customizers, and application-provided metadata. Therefore, protecting documentation must happen both where data is produced and where it is published. Never simply delete a string in Swagger UI and assume `/v3/api-docs` or the OpenAPI JSON/YAML output is safe.

This lesson guides you through identifying data that needs protection, replacing real data with synthetic examples, controlling infrastructure addresses, protecting documentation endpoints, and inspecting artifacts before publishing.

## Objectives

After this lesson, you will be able to:

- Identify tokens, credentials, personal data, and infrastructure details that can appear in OpenAPI.
- Locate leaks in descriptions, examples, defaults, enums, schemas, responses, servers, and extensions.
- Write synthetic examples containing no real data or usable secrets.
- Publish accurate public server URLs while stripping internal hostnames, IPs, and ports.
- Distinguish hiding fields in documentation from protecting data at runtime.
- Organize public and internal documentation using groups or separate configurations.
- Protect both Swagger UI and `/v3/api-docs` endpoints.
- Inspect OpenAPI files before placing them into artifacts, CDNs, portals, or public repositories.
- Respond and remediate when documentation has already exposed a token or sensitive data.

## 1. Why Is API Documentation Also a Data Leak Surface?

OpenAPI is often viewed purely as technical documentation, yet it can carry far more data than endpoint names and JSON types. Components that can hold human-entered or application-generated content include:

- `info.description`, `contact`, `license`, and `termsOfService`.
- `servers` and server variables.
- Paths, query parameters, headers, cookies, and request descriptions.
- Schema properties, `description`, `example`, `default`, `enum`, and `format`.
- Request body and response examples.
- Response headers, links, and callbacks.
- OAuth2 `authorizationUrl`, `tokenUrl`, OpenID Connect `openIdConnectUrl`, and security metadata.
- `externalDocs`, tags, operation descriptions, and operation IDs.
- Custom `x-...` extensions added by the application.

Swagger UI is only an interface for reading and testing APIs. The JSON/YAML specification is usually served separately, such as at `/v3/api-docs`, or exported as a downloadable artifact. Hiding an element in the UI does not remove data from the OpenAPI document.

### Common Leak Scenarios

| Scenario | Information Exposed | Common Location |
|---|---|---|
| Copying real requests into examples | Bearer tokens, cookies, API keys | `@ExampleObject`, descriptions, cURL |
| Copying production responses | Names, emails, phone numbers, addresses, customer IDs | Schema examples, response examples |
| Using deployment config as server | Internal hostnames, private IPs, ports, context paths | `servers` |
| Documenting how to call internal APIs | Namespace names, clusters, service discovery, admin endpoints | Descriptions, external docs, extensions |
| Pasting errors from logs into docs | Stack traces, SQL, file paths, request IDs, user data | Response descriptions, examples |
| Putting tokens in query strings | Tokens can appear in URLs, history, or access logs | Parameters and cURL examples |
| Publishing Swagger UI openly | Lists of admin endpoints or internal operations | `/swagger-ui/**`, `/v3/api-docs/**` |
| Storing OpenAPI files in public artifacts | Entire unfiltered metadata | CI artifacts, static hosting, CDNs |

A document containing no tokens can still increase risk if it reveals topology, administrative endpoints, or internal system names. Evaluate content according to the publishing context: public APIs, partner-facing docs, or employee-only docs.

## 2. Classifying Data Before Publishing

Before writing examples or configuring customizers, determine which kinds of data are permitted in each documentation group.

### Authentication Secrets and Credentials

Never include values usable for authentication or granting access in OpenAPI:

- Access tokens, refresh tokens, ID tokens.
- Full JWTs, even expired ones if they still expose claims or structure.
- API keys, client secrets, passwords, private keys, and private certificates.
- Session IDs, authentication cookies, CSRF tokens.
- Signed URLs or URLs with query parameters containing credentials.
- Temporary authorization codes, reset tokens, or invitation tokens.

Never use real tokens in the `Authorization` header of cURL examples. Never put tokens into `default`, `example`, `enum`, descriptions, or extensions. OpenAPI only needs to describe the scheme and security requirements; users supply their own valid credentials when testing the API.

### Personal Data

Check both directly identifying data and data that can be combined to identify an individual:

- Full names, emails, phone numbers.
- Home addresses, dates of birth, photos, and identity documents.
- Customer IDs, account IDs, order IDs tied to individuals.
- Location coordinates, device details, or online identifiers.
- Payment, banking, insurance, or account information.
- Free-form text that may contain user information.

A numeric ID or UUID is not inherently anonymous data. If an ID can be traced back to a person in the system or combined with another source to identify them, treat it as data requiring protection.

### Infrastructure and Operational Details

Do not publish infrastructure details meant solely for internal operations:

- Internal hostnames, DNS suffixes, namespace names, or service discovery names.
- Private, loopback, link-local, or management IP addresses.
- Internal ports, admin paths, actuator paths, or debug endpoints.
- Internal database, queue, bucket, topic, cluster, and region names.
- Filesystem paths, mount points, host machines, container IDs.
- Operator usernames, proxy settings, internal gateways, or topology.
- Stack traces, SQL, shell commands, internal class names, and source paths.

A public hostname or support contact address may be published if it is approved information. Classify by purpose and access scope; do not automatically assume every URL/IP is secret or every URL/IP is safe.

### Sensitive Business Data

Some information is neither credentials nor personal data yet still should not be published:

- Names of undisclosed customers, partners, or projects.
- Pricing rules, limits, anti-fraud thresholds, and internal policies.
- Feature flag names and unreleased product codes.
- Beta endpoints, administrative operations, or unannounced workflows.
- Details of third-party systems and integration contracts.

Distinguish documentation for public developers from documentation for partners under NDA and internal documentation.

## 3. Locating Sensitive Data in OpenAPI

Do not search only for fields named `password` or `token`. Sensitive content can appear in any free-text string.

### Descriptions and Summaries

Text fields are often overlooked during review:

~~~java
@Operation(
    summary = "Look up account",
    description = "Use customer X's real account in the internal system to check..."
)
~~~

Descriptions are exported into OpenAPI. Never copy internal notes, tickets, logs, or email threads into summaries/descriptions. Rewrite them into general guidance explaining the API behavior clients need to know.

### Schema Examples, Defaults, and Enums

Unsafe example:

~~~java
@Schema(
    description = "Bearer token of the test session",
    example = "TOKEN_VALUE_MUST_NOT_BE_PUBLISHED"
)
private String accessToken;
~~~

The snippet above can export a token into the schema even if the endpoint does not return tokens in responses. Never use fake tokens formatted like usable tokens; a string that looks like a JWT can easily be copied into real environments and cause confusion.

`default` is also published data in the schema. Never place default passwords, API keys, internal hostnames, or real account IDs into defaults. `enum` values can leak tenant names, customers, internal statuses, or undisclosed configuration values.

### Request and Response Examples

`@ExampleObject`, `@Content`, `@ApiResponse`, and DTO annotations can generate examples shown in Swagger UI and OpenAPI JSON. Treat examples as published content needing review just like official documentation.

Never take raw requests/responses from production or logs as examples. Build synthetic fixtures, check every nested field, and replace even traceable IDs.

### Servers, URLs, and External Documentation

Check all URLs, not just `servers`:

- OAuth2 `authorizationUrl` and `tokenUrl`.
- OpenID Connect `openIdConnectUrl`.
- `externalDocs.url`.
- Callback URLs and links in responses.
- Server variables and their defaults.
- URLs inside descriptions, examples, extensions, and contact fields.

A URL can contain a signed query string, API key, tenant ID, or internal path. Use approved public endpoints or placeholder URLs reserved for documentation.

### Custom Extensions and Metadata

`x-...` extensions are often added by customizers or build systems. They can contain service names, internal routes, build metadata, commit URLs, cluster names, request traces, or deployment details. Include extensions in your review checklist alongside standard OpenAPI properties.

## 4. Writing Synthetic Examples Instead of Copying Real Data

Safe examples should illustrate structure and data types without representing any real individual, credential, or live system.

### Rules for Creating Sample Data

1. Use example-reserved domains such as `example.com` or `.invalid`; never use customer or production domains.
2. Use synthetic IDs, such as `sample-001` or UUIDs generated specifically for documentation.
3. Use data not tied to any real person.
4. Never use phone numbers, emails, or addresses taken from tickets, databases, or logs.
5. Never use real JWTs, API keys, or passwords; ideally omit credentials from examples altogether.
6. Keep data consistent between requests and responses without copying production records.
7. Check nested objects, attachments, URLs, metadata, and headers.

Synthetic response example:

~~~json
{
  "id": "sample-product-001",
  "name": "Sample keyboard",
  "status": "ACTIVE",
  "contactEmail": "developer@example.com"
}
~~~

`example.com` is a domain reserved for examples. `sample-product-001` is an illustrative identifier referencing no production record.

### Request Examples Without Tokens

Avoid writing:

~~~bash
curl -H "Authorization: Bearer REDACTED_VALUE" \
  https://api.example.com/api/products
~~~

You can write guidance using an environment variable:

~~~bash
curl \
  -H "Authorization: Bearer ${ACCESS_TOKEN}" \
  https://api.example.com/api/products
~~~

This is a placeholder for a token users supply in their own environment. Never put real token values into examples, sample `.env` files, or published scripts.

### Avoid Placeholders That Look Like Credentials

A string carrying a provider credential prefix, even truncated, can still be flagged by scanners as a secret. In documentation, use clear placeholders such as `${ACCESS_TOKEN}` or descriptive text like "Supply a valid access token at call time".

If illustrating JWT structure is necessary, use an unsigned synthetic payload or clearly mark the token as a dummy string incapable of validation. Never sign an illustrative token with a real secret.

### Synthetic Data vs. Anonymized Data

Masking part of an email, phone number, or name does not guarantee data is anonymized. For example, `n***@company.com` can still identify a person when the domain and context are narrow enough. For public documentation, prefer generating synthetic data from scratch instead of obfuscating production data.

If transformed data must be used, assess re-identification risk and inspect combined fields. Removing a name while leaving exact email, customer ID, address, and timestamps can still expose an identity.

## 5. Describing Sensitive Fields in Schemas

Not every sensitive field needs to appear in documentation. First determine whether clients need to know the field exists and whether they need to send or receive it.

### Do Not Expose Unnecessary Internal Fields

If a DTO contains internal-only fields, consider separating public DTOs from entities or internal models. This is the clearest way to control the contract:

~~~java
public record PublicUserResponse(
    String id,
    String displayName
) {}
~~~

Do not include password hashes, internal notes, moderation flags, database keys, or operational fields in a response DTO only to try hiding them from OpenAPI afterward.

### @Schema(hidden = true) Is Not Access Control

You can hide a property from a schema:

~~~java
@Schema(hidden = true)
private String internalRiskScore;
~~~

This affects OpenAPI documentation. It does not prevent Jackson from serializing the field to JSON, does not protect endpoints, and does not replace permission checks. If a field must never appear in responses, remove it from the response DTO or configure serialization appropriately, then write runtime JSON tests.

Similarly, `@Parameter(hidden = true)` or `@Hidden` only affects documentation within the scope of that annotation; it does not make an endpoint or parameter secure. If clients actually must send a header or parameter, do not hide it just to avoid leaking sensitive values. Describe the field's name and purpose without putting real credentials in examples/defaults.

### readOnly and writeOnly

OpenAPI supports `readOnly` and `writeOnly` to describe data direction:

- `readOnly: true`: property is returned in responses, and clients should not send it when creating/updating.
- `writeOnly: true`: property is sent in requests, and is not returned in responses.

For instance, a password can be described as write-only if the API actually accepts passwords:

~~~yaml
password:
  type: string
  format: password
  writeOnly: true
  description: New password provided by the user
~~~

Do not add examples or defaults for passwords. `writeOnly` is contract metadata; the application must still ensure passwords are never serialized into responses, logs, or exceptions.

### Separating Request DTOs and Response DTOs

Sharing a single DTO across both requests and responses easily causes internal or write-only fields to appear in the wrong place. For sensitive data, splitting types is usually easier to control:

~~~java
public record ChangePasswordRequest(
    @Schema(format = "password", writeOnly = true)
    String newPassword
) {}

public record PublicProfileResponse(
    String id,
    String displayName
) {}
~~~

Do not include passwords in response DTOs. When placing annotations on record components, check both OpenAPI JSON and runtime JSON to verify metadata and serialization behave as expected.

## 6. Using Customizers to Enforce Publishing Policies

OpenApiCustomizer lets you inspect and shape documentation after springdoc builds the OpenAPI model. It is useful for applying consistent policies, such as setting public server URLs from approved configuration, normalizing contacts to a public support address, removing well-identified internal extensions, or rejecting documents with server hosts outside an allowlist.

A customizer should not be the sole place handling all sensitive data. Safe data must start at annotations, DTOs, and fixtures; customizers serve as an extra control layer and can hold per-group logic.

### Normalizing Public Contact Info

If source metadata contains internal contacts, a customizer dedicated to public docs can set an approved contact:

~~~java
import io.swagger.v3.oas.models.info.Contact;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
OpenApiCustomizer publicContactCustomizer() {
    return openApi -> {
        if (openApi.getInfo() != null) {
            openApi.getInfo().setContact(
                new Contact()
                    .name("API Support")
                    .url("https://developers.example.com/support")
                    .email("support@example.com")
            );
        }
    };
}
~~~

This intentionally replaces the contact for public documentation. Use an organization-approved support address; never substitute personal emails or internal aliases.

### Do Not Use Regex to Replace Arbitrary Strings in OpenAPI

Never serialize the entire OpenAPI document to text and run a series of regex replacements for hostnames, tokens, or emails. That approach can accidentally corrupt legitimate content in examples or descriptions, miss data in other JSON/YAML structures, break URLs or schema references, and create a false sense of security since some secret formats will not match the regex.

Fix annotations, DTOs, server configuration, and examples at the source first. In customizers, operate on specific model properties/nodes with clear ownership. If a general filter is needed, traverse the structure using an OpenAPI parser and write tests per node type; never run global text replacement on serialized strings.

### Rejecting Documents When Non-Allowlisted Hosts Appear

For public specs, you can validate server URLs prior to release:

~~~java
private static final Set<String> ALLOWED_HOSTS =
    Set.of("api.example.com", "sandbox.example.com");

private void validatePublicServers(OpenAPI openApi) {
    if (openApi.getServers() == null) {
        throw new IllegalStateException("Public server is missing");
    }

    for (Server server : openApi.getServers()) {
        URI uri = URI.create(server.getUrl());
        if (uri.getHost() != null && !ALLOWED_HOSTS.contains(uri.getHost())) {
            throw new IllegalStateException(
                "OpenAPI contains a server outside the public allowlist"
            );
        }
    }
}
~~~

This is an illustrative helper; import java.net.URI, java.util.Set, OpenAPI, and Server. Relative URLs like / have no host, so allow them per your policy. Never include the full rejected URL in exceptions/logs if it could contain credentials or query secrets.

An allowlist check like this only validates server URLs. It does not detect PII in examples, tokens in descriptions, or internal addresses in extensions; other checks are needed for those fields.

## 7. Preventing Data Leaks Through Responses and Logging

OpenAPI is one part of the API lifecycle, yet sensitive data can also leak through real responses, errors, and logs. Even if schemas are scrubbed, if an endpoint returns password hashes or stack traces, documentation cannot protect that data.

### Error Responses Must Be Safe

Never include internal details in error responses:

~~~json
{
  "message": "Connection failed to database-host.internal.invalid:5432",
  "sql": "select * from customer_account where id = ...",
  "stackTrace": "..."
}
~~~

Replace with a generic error and non-sensitive reference code:

~~~json
{
  "code": "INTERNAL_ERROR",
  "message": "An error occurred. Please try again later.",
  "traceId": "sample-trace-001"
}
~~~

Trace IDs in examples must be synthetic values. At runtime, trace IDs can help support locate logs, yet logs must remain protected and users should never be able to use that ID to read internal information.

OpenAPI response examples and descriptions should document standardized errors. Never copy stack traces, SQL, hostnames, filesystem paths, or real request payloads into response examples.

### Never Log Credentials or Sensitive Data

Audit logging across controllers, filters, interceptors, gateways, and HTTP clients:

- Never log Authorization, Cookie, Set-Cookie, or client secrets.
- Never log full request/response bodies if they contain passwords, payment info, or personal data.
- Never record query strings containing signed URLs or tokens.
- Never record full JWTs; use a dedicated request ID for correlation.
- Never include stack traces or internal configuration in client-facing responses.
- Restrict log read access, and set retention and masking policies.

Log masking only reduces displayed data; it does not replace avoiding logging credentials in the first place. Also inspect logs produced by HTTP libraries, proxies, ingress controllers, and tracing agents.

### Documentation and Responses Must Be Consistent

If OpenAPI documents traceId while real responses return requestId, clients will struggle to correlate errors. If a schema marks password as write-only yet the serializer still returns password, that is a runtime bug. Test both sides:

- OpenAPI JSON contains no sensitive data.
- Real JSON responses contain no forbidden fields or values.
- Error responses contain no stack traces or infrastructure details.
- Logs do not record credentials or sensitive bodies under the active configuration.

## 8. Checking OpenAPI Before Creating Artifacts

A static OpenAPI file can be stored in build artifacts, packages, repositories, developer portals, or CDNs. Once published, revoking older copies can be harder than changing a dynamic endpoint. Add content checks into the artifact-generation pipeline.

### Safe Publishing Workflow

1. Identify the audience: public, partner, or internal.
2. Select the matching OpenAPI source and group for that audience.
3. Generate JSON/YAML from the right application version.
4. Parse the file with an OpenAPI parser to ensure valid structure.
5. Check servers, OAuth URLs, externalDocs, and callbacks against allowlists.
6. Scan for tokens, API keys, private keys, and credential patterns.
7. Scan for PII in examples, descriptions, defaults, enums, and extensions.
8. Check for internal endpoints/paths and operational metadata.
9. Manually review free-text sections, response examples, and extensions.
10. Store the artifact in a location with permissions matching the audience.
11. Attach non-sensitive version/build metadata and retain release history.
12. Publish only after all required checks pass.

### Classifying Artifacts

| Artifact | Appropriate Storage | Controls |
|---|---|---|
| Public OpenAPI | Public portal or approved static hosting | Contains only public operations and servers |
| Partner OpenAPI | Partner-authenticated portal | Scoped by partner and version |
| Internal OpenAPI | Internal artifact repository or portal | SSO/RBAC, network policy, retention |
| Raw generated OpenAPI | Build workspace or temporary internal artifact | Never auto-published externally |

Do not reuse the same OpenAPI file for both public and internal audiences if it contains out-of-scope operations, schemas, or servers. Produce separate artifacts and verify their contents before uploading.

### Managing Caches and Copies

When sensitive content is found in published documentation, deleting the source file does not necessarily delete all copies:

- CDN caches and reverse proxy caches.
- Browser caches and user downloads.
- Build artifacts, package registries, and release attachments.
- Git history, branches, forks, and mirrors.
- Developer portals or documentation indexing systems.
- Backups and archives under retention.

Identify everywhere the file was distributed and the revocation procedure for each location. Never republish an old artifact just because the current source has been fixed.

## 9. Automating Secret and PII Checks

Automated checks catch mistakes early, though they cannot replace content reviews. Combine secret scanning, PII scanning, schema validation, and policy assertions.

### Secret Scanning

Secret scanners can detect:

- JWTs or high-entropy strings.
- Provider-patterned API keys.
- PEM private keys.
- Authorization headers or cookies with values.
- URLs containing credentials in query strings.

Do not rely solely on a generic pattern like eyJ; that sequence can appear in non-token examples, and tokens can use other formats. Use scanners tailored to your credential formats and handle false positives carefully.

If a scanner detects a secret, never print the raw matched value to CI logs. Report the filename, location, or rule type with a masked snippet; only authorized personnel should access the artifact for investigation.

### PII Scanning

PII scanners can catch pattern-based emails, phone numbers, addresses, or identifiers. Yet person names, business IDs, and free-form text are harder to detect automatically. Supplement with:

- An allowlist of approved example domains.
- A list of sensitive schema fields.
- Manual review of examples and descriptions.
- Checks for fields that could combine to re-identify individuals.
- Checks for IDs traceable back to production systems.

Never treat a "no findings" scanner result as absolute proof that a document is anonymized.

### Asserting Public Servers

A simple test can verify the public server:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class PublicOpenApiTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void publishesOnlyApprovedServer() throws Exception {
        mockMvc.perform(get("/v3/api-docs/public"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.servers[0].url")
                .value("https://api.example.com"));
    }
}
~~~

Values must match test configuration. Add assertions for all servers, not just the first element if the document lists multiple servers.

### Checking Absence of Known Internal Strings

You can assert the document body contains no known internal hostnames or markers:

~~~java
mockMvc.perform(get("/v3/api-docs/public"))
    .andExpect(status().isOk())
    .andExpect(content().string(not(containsString(".svc.cluster.local"))))
    .andExpect(content().string(not(containsString("db-prod-"))));
~~~

The example uses Hamcrest not and containsString; add static imports for those matchers and content(). This is only a supplemental check for known markers. It does not replace parsers, allowlists, or secret scanners.

### Checking Documentation and Runtime Together

Write dedicated tests to ensure:

- OpenAPI does not contain internalRiskScore if that field is unpublished.
- Runtime responses do not contain internalRiskScore if returning that field is forbidden.
- The password schema has writeOnly: true and no example/default.
- Public servers contain no internal hostnames.
- The public group contains no admin/internal paths.
- Swagger UI and /v3/api-docs require proper permissions if documentation is not public.

## 10. Responding When Documentation Leaks Data

If tokens, PII, or internal addresses are discovered in published documentation, respond according to the data severity and distribution scope.

### When Credentials Are Exposed

1. Identify the credential type, where it appeared, when, and related artifacts.
2. Revoke or rotate the affected token, API key, password, certificate, or secret per system procedure.
3. Check access, download, CDN, and portal logs to assess potential usage.
4. Remove or replace affected artifacts, purge caches, and update portals.
5. Inspect repository history, release attachments, and distributed copies.
6. Fix the source annotation/configuration/example so the mistake does not recur.
7. Add tests or scanner rules to block republishing similar content.

Deleting a string from a file does not invalidate the old credential. If a credential is usable, revoke/rotate it promptly; never rely solely on the fact that the documentation was edited.

### When Personal Data Is Exposed

1. Identify the data types, affected individuals/groups, and publication scope.
2. Restrict access or take down the documentation per incident response procedures.
3. Revoke controllable copies, caches, and artifacts.
4. Notify your data protection contact or incident response team per organizational policy and applicable regulations.
5. Assess re-identification risk from any remaining fields.
6. Replace examples with synthetic data and add review gates.

Never copy leaked personal data into new tickets or investigation logs unnecessarily. When reporting, use reference codes and describe data categories instead of proliferating sensitive values.

### When Internal Infrastructure Is Exposed

1. Strip internal hostnames, IPs, ports, routes, and topology from public documentation.
2. Check whether exposed endpoints are reachable from the Internet or untrusted networks.
3. Review firewalls, gateways, DNS, and network policies if the exposure increases discoverability.
4. Inspect access logs and security alerts.
5. Fix server URLs, externalDocs, examples, extensions, and metadata sources.
6. Add host allowlists and regression tests against re-publication.

Not every exposed internal hostname requires infrastructure changes. Assess actual reachability and risk, then apply proportionate controls.

## 11. Pre-Publication Checklist

### Content and Schemas

- [ ] No real access tokens, refresh tokens, ID tokens, API keys, client secrets, or passwords.
- [ ] No private keys, cookies, session IDs, CSRF tokens, or signed URLs.
- [ ] Examples use synthetic data and example-reserved domains.
- [ ] No emails, phone numbers, addresses, names, or IDs tied to real individuals.
- [ ] No information capable of re-identifying individuals when combining fields.
- [ ] No password hashes, internal notes, risk scores, or unnecessary internal fields.
- [ ] Descriptions and response examples contain no logs, stack traces, SQL, or machine paths.
- [ ] Defaults and enums do not leak credentials, tenants, or internal configuration.
- [ ] x-... extensions have been reviewed.

### URLs and Infrastructure

- [ ] Server URLs contain only approved public hostnames or policy-compliant relative URLs.
- [ ] No private IPs, loopback addresses, internal DNS suffixes, namespaces, or admin ports.
- [ ] OAuth2 and OpenID Connect URLs match the audience.
- [ ] External docs, callbacks, webhooks, and response links have been reviewed.
- [ ] Contact uses only an approved public support address.

### Access and Publishing

- [ ] Public group contains only approved operations.
- [ ] Internal/admin documentation is protected separately.
- [ ] Swagger UI and /v3/api-docs are both protected or disabled when unneeded.
- [ ] @Hidden is not mistaken for runtime access control.
- [ ] Artifacts are parsed, scanned for secrets/PII, and reviewed before publishing.
- [ ] Public and internal artifacts are stored with appropriate access permissions.
- [ ] Caches and older copies have a revocation procedure.
- [ ] Tests verify servers, schemas, paths, and docs endpoint protection.

## 12. Comprehensive Practice Lab

Prepare a Spring Boot application with both public and internal APIs. Generate OpenAPI documentation and complete the following steps:

1. Create a response DTO with a public field and an internal field; split a public DTO or omit the internal field from the response.
2. Create a request DTO with a write-only password and omit example/default on the password.
3. Create response examples using synthetic data, the example.com domain, and sample IDs.
4. Verify no tokens, cookies, API keys, or signed URLs exist in examples or descriptions.
5. Configure the public server URL via application properties.
6. Create a GroupedOpenApi containing only public paths.
7. Exclude internal operations from public docs while still protecting their endpoints with Spring Security.
8. Protect /swagger-ui/** and /v3/api-docs/** with a dedicated authority or disable docs in the production profile.
9. Check OAuth2/OIDC URLs, contact, externalDocs, server variables, and extensions.
10. Generate OpenAPI JSON, parse it, and scan for secrets/PII prior to packaging the artifact.
11. Write MockMvc tests verifying public servers, public paths, and docs endpoint protection.
12. Write runtime response tests ensuring internal fields and credentials never appear.
13. Simulate discovering a token in an artifact; establish steps to revoke, purge caches, and replace the artifact.
14. Record the data source, reviewer, and audience for every published artifact.

### Completion Criteria

- [ ] Documentation contains no usable credentials or tokens.
- [ ] Examples contain no production PII and cannot be traced back to individuals.
- [ ] Public OpenAPI does not expose internal hostnames, IPs, ports, or topology.
- [ ] Server URLs and OAuth/OIDC URLs match the audience.
- [ ] Public DTOs expose no unnecessary internal fields.
- [ ] Schema hidden is not used in place of serialization controls or authorization.
- [ ] Public/internal groups are properly separated.
- [ ] Swagger UI and OpenAPI endpoints are protected or disabled per policy.
- [ ] Secret/PII scans and OpenAPI validation run before publishing.
- [ ] Tests verify both OpenAPI content and runtime responses.
- [ ] A procedure exists to revoke credentials and artifacts when leaks occur.

## 13. Publishing Server URLs Without Exposing Internal Topology

Springdoc can infer servers from the current request or use servers declared in OpenAPI configuration. Behind a reverse proxy, ingress, or API gateway, internal requests reaching the application may carry a hostname and port different from the address external clients use.

Example of accidentally published documentation:

~~~yaml
servers:
  - url: http://product-api.namespace.svc.internal.invalid:8080
~~~

This URL exposes the service name, namespace, and port inside the cluster. External clients cannot reach that address directly either.

Publish the approved public gateway address instead:

~~~yaml
servers:
  - url: https://api.example.com
    description: Public API
~~~

If the API is served under the same origin as the client application, you can use a relative server URL matching the deployment setup:

~~~yaml
servers:
  - url: /
    description: Current host
~~~

Never use real production URLs in lessons, fixtures, or tests unless necessary. `example.com` is an illustrative domain; when releasing, replace it with the official public hostname approved by the API owner.

### Configuring Public URLs Per Environment

Supply the public base URL via deployment configuration instead of inferring it from internal hostnames:

~~~yaml
app:
  public-api-url: https://api.example.com
~~~

A customizer can set the server list for public documentation:

~~~java
import io.swagger.v3.oas.models.servers.Server;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.List;

@Configuration
class PublicOpenApiServerConfiguration {

    @Bean
    OpenApiCustomizer publicServerCustomizer(
            @Value("${app.public-api-url:/}") String publicApiUrl) {

        return openApi -> openApi.setServers(List.of(
            new Server()
                .url(publicApiUrl)
                .description("Public API")
        ));
    }
}
~~~

This snippet replaces all `servers` with the configured public URL. Attach this customizer only to public documentation; internal documentation may need different servers and must be protected separately. If the application requires multiple public servers, build the list from vetted configuration rather than collecting addresses from requests or service discovery.

If the public spec is created with GroupedOpenApi, attach the customizer to that group's builder via addOpenApiCustomizer. Do not apply the public customizer to internal or partner documentation if those audiences have different base URLs.

Validate configuration at startup or in the pipeline: accept only approved schemes/hosts/paths. If a URL is missing, uses the wrong scheme, or points to an internal hostname, never silently publish it into public documentation.

### Checking Server Variables

Server variables can hold hostnames or default paths:

~~~yaml
servers:
  - url: https://{environment}.example.com/{basePath}
    variables:
      environment:
        default: api
        enum:
          - api
          - sandbox
      basePath:
        default: v1
~~~

Publish only enum values and defaults clients are permitted to use. Never put cluster names, namespaces, internal DNS suffixes, or admin ports into server variables.

### Checking All Other URLs

Beyond `servers`, review:

- OAuth2 `authorizationUrl` and `tokenUrl`: use public endpoints of the authorization server.
- OpenID Connect `openIdConnectUrl`: do not expose internal discovery addresses if public clients cannot reach them.
- `externalDocs`: link only to portals or docs cleared for publication.
- Callback and webhook URLs: use public hostnames or placeholders in examples.
- Response links: never contain signed URLs or query parameters carrying credentials.
- Contact: use a public support email, not personal emails or internal operations aliases.

Never use query parameters to pass bearer tokens or API keys. URLs are frequently recorded in browser history, proxy logs, analytics, and access logs. Use the `Authorization` header or an authentication mechanism designed for APIs.

## 14. Separating Public and Internal Documentation

Not every endpoint in an application is meant for everyone to read. An API may have:

- Public operations for external developers.
- Partner operations strictly for authorized partners.
- Internal operations for service-to-service calls.
- Admin, support, actuator, or diagnostic endpoints.

A single document containing every path can expose internal operations. Create documentation groups by audience and include only approved operations in each group.

### Using GroupedOpenApi for Public APIs

Example of a public group containing only paths with a public prefix:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupsConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/public/**")
            .build();
    }
}
~~~

Group documents are served at endpoints like `/v3/api-docs/public`. Publish only the public group to external audiences. If internal or admin groups exist, protect their documentation endpoints with proper authentication and authorization.

Groups filter paths at the documentation level; they do not protect runtime endpoints. If an internal endpoint remains accessible without permission, excluding it from public OpenAPI does not fix the authorization bug.

### @Hidden Only Hides from Documentation

You can exclude a controller or operation from OpenAPI using `@Hidden`:

~~~java
@Hidden
@RestController
@RequestMapping("/internal/maintenance")
class InternalMaintenanceController {
    // ...
}
~~~

Or hide a specific operation you do not want in documentation:

~~~java
@Hidden
@PostMapping("/internal/reindex")
public void reindex() {
    // ...
}
~~~

`@Hidden` affects documentation generation. It does not block HTTP requests and does not replace Spring Security, gateway policies, or network controls. Endpoints must still be protected independently at runtime.

### Do Not Rely on Changing Swagger UI URLs

Changing `/swagger-ui.html` to a hard-to-guess path or changing `/v3/api-docs` is not an authorization measure. Paths can be discovered through JavaScript, network requests, logs, or client configuration. Protect endpoints with authentication, authorization, network policies, or disable them completely when unneeded.

## 15. Protecting Swagger UI and OpenAPI Endpoints

Swagger UI and OpenAPI JSON are two separate resources. Protecting only the UI page leaves users able to call the documentation endpoint directly. Protecting only `/v3/api-docs` allows a public Swagger UI page to still expose HTML, assets, group names, or other metadata.

### Protecting Both Paths

A Spring Security example can require a dedicated authority to read documentation:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class DocumentationSecurityConfiguration {

    @Bean
    SecurityFilterChain documentationSecurity(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(authorize -> authorize
            .requestMatchers(
                "/swagger-ui.html",
                "/swagger-ui/**",
                "/v3/api-docs/**"
            ).hasAuthority("SCOPE_api-docs:read")
            .anyRequest().authenticated()
        );

        return http.build();
    }
}
~~~

This is an example authorization rule; integrate it into your application's actual `SecurityFilterChain` and verify filter chain ordering, matchers, CSRF, CORS, and the login mechanism. If APIs have their own chain, ensure documentation matchers are handled by the intended chain. Avoid creating an overly broad chain that alters existing API protection rules unexpectedly.

You do not have to use the same OAuth2 mechanism as the API for the documentation page. Swagger UI can use SSO, gateway authentication, VPN, or an internal network to load documentation, while API operations use dedicated OAuth2 scopes. Choose authentication suited to the documentation's audience.

### Disabling Documentation When Not Needed

If production does not need to serve dynamic documentation, disable API docs and Swagger UI via Springdoc configuration:

~~~yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
~~~

Set this configuration per profile/environment and verify endpoints are genuinely no longer served in production. If static OpenAPI artifacts are needed, generate them in a controlled pipeline and store them in a location with proper access permissions while disabling dynamic endpoints on the application.

Changing `springdoc.api-docs.path` only changes the endpoint path; it does not replace disabling or protecting endpoints.

### Swagger UI Try It Out and Authorization Persistence

Swagger UI can send real requests from the browser. Consider:

- Enable Try it out only for audiences permitted to call APIs from that interface.
- Never put tokens into examples or query strings.
- Never enable long-lived authorization persistence on shared browsers without clear justification and policy.
- Use HTTPS and configure CORS for allowed origins.
- Avoid putting real data into sample responses or prefilled requests.
- Check whether tokens are kept in memory/local storage according to your Swagger UI configuration and version.

The `persistAuthorization` option can preserve authorization state across page reloads. Do not enable this option by default on shared machines or kiosks; evaluate the behavior of your embedded Swagger UI version and organizational browser policies.

## Continuing Further

After this lesson, combine documentation protection with authentication, authorization, grouped documentation, customizers, and CI contract testing. Every time schemas, examples, servers, or security metadata change, review published content for the target audience and verify both OpenAPI artifacts and runtime behavior.
