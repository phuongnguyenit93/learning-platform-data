# Tracking Provenance, Ownership, and Versioning of Published Documentation

An OpenAPI file generated from a Spring Boot application can be used in many places: Swagger UI, developer portals, SDK generators, contract tests, artifact repositories, or partner integration systems. When a consumer receives a JSON/YAML file, they need to know **which API the document belongs to, who is responsible for it, which source revision produced it, under which environment, and which release it corresponds to**.

`springdoc-openapi` is responsible for generating the OpenAPI document from application endpoints and metadata. Tracking documentation provenance and distribution requires an additional build/release workflow: recording the source commit, tool versions, exported group, checksums, owner details, and published artifact location. Together, these form the document's provenance.

## 1. Distinguishing the OpenAPI document, the API, and the release artifact

Several version values often appear side by side yet carry different meanings:

| Value | Where It Lives | Meaning |
| --- | --- | --- |
| OpenAPI Specification version | Root `openapi` field, e.g. `3.1.0` | Version of the specification syntax the document follows |
| OpenAPI document version | `info.version` | Version of the OpenAPI document itself |
| API runtime version | System API convention, e.g. `/api/v1` or version header | Version of the API behavior served by the server |
| `springdoc-openapi` version | Application dependency | Version of the documentation generation library |
| Artifact release version | Package name, tag, or publish path | Immutable version of the published document file |
| Source revision | Git commit SHA | Exact source revision used to build the document |
| Build run ID | CI pipeline | Pipeline run that produced the artifact |

Do not collapse these values into one string. For example, a document may declare `openapi: 3.1.0`, `info.version: 1.4.2`, describe runtime API `/api/v1`, be generated with `springdoc-openapi` `2.x`, from Git commit `8f2a...`, and be published as artifact `shop-openapi-public:1.4.2`.

The OpenAPI Specification defines `info.version` as the version of the OpenAPI document and distinguishes it from both the OpenAPI Specification version and the API implementation version. An organization may choose to align `info.version` with the API release for operational simplicity, but must document that as a project convention. If the document version and API version differ, record both in the release manifest.

## 2. Identifying the provenance of a document

Provenance answers: where, when, and by what process was this file created? For OpenAPI generated from Spring Boot, at minimum link the following data:

- Exact repository and source revision.
- Release tag or branch used to generate the document.
- Working tree state at build time.
- CI workflow, build run ID, and build platform.
- Versions of JDK, Spring Boot, `springdoc-openapi`, and build plugins.
- Spring profile, OpenAPI group, and configuration affecting the document.
- File path, format, size, and SHA-256 digest.
- Artifact version, publication location, and publication timestamp.

Recording only a branch name such as `main` is insufficient. Branches move over time. A commit SHA is the immutable identifier pinpointing the exact source revision. Similarly, recording only `springdoc-openapi 2.x` is insufficient for reproducibility; record the exact resolved version from a dependency lockfile or dependency report.

A release build should run from a reviewed and tagged commit. If built from a working tree with uncommitted changes, explicitly record that state and avoid publishing it as an official release.

## 3. Distinguishing source provenance and build provenance

Two types of provenance complement each other:

| Type | Question Answered | Typical Evidence |
| --- | --- | --- |
| Source provenance | Under what process was the source revision created and reviewed? | Git commit, pull request, reviewers, branch protection, signed commits/tags |
| Build provenance | From which source, by which system, and through what process was the artifact built? | CI run, build definition, tool versions, dependency inputs, artifact digest, attestation |

For example, a Git commit may have been properly reviewed and merged, yet the published artifact was built from another commit or on a developer's personal machine. Strong source provenance alone does not prove the distributed artifact came from that source. Build provenance binds the specific artifact to the actual source revision and build process.

SLSA defines build provenance as verifiable information about how an artifact was produced. This model links output artifacts to build definitions, dependencies, and build platforms. For OpenAPI documentation, the same principles apply to JSON/YAML files and their sidecar manifests.

## 4. Establishing clear documentation ownership

Every published document needs a team accountable for content and a team accountable for distribution. Both roles may belong to the same team, yet responsibilities must be clear:

| Role | Responsibilities |
| --- | --- |
| API owner | Confirms endpoints, schemas, security, and semantics are accurately described |
| Documentation owner | Maintains descriptions, contact info, examples, and change history |
| Build/release owner | Maintains export pipeline, validation, checksums, and publication |
| Consumer/integration owner | Confirms compatibility and reports consumer-side issues |

Do not list only the individual who created the file. Individuals may change teams or leave projects while API accountability persists. Use team names or service owners as the primary contact; individual contacts can supplement review workflows.

For Git repositories, define review rules covering controller sources, OpenAPI configuration, pipelines, and documentation directories using `CODEOWNERS` or equivalent mechanisms. Pull requests altering contracts should require API owner review; changes to publication workflows should require release/platform owner review.

Ownership also needs a handover process. When an API transfers teams, update contacts, reviewer rules, runbooks, and artifact repository permissions. Never leave documentation pointing to defunct support emails or URLs.

## 5. Recording owner metadata in the OpenAPI document

The OpenAPI Info Object provides standard metadata fields such as `title`, `description`, `contact`, `license`, and `version`. Use `contact` to point to API support channels and `externalDocs` to link to comprehensive guides.

Example `OpenAPI` bean configuration in Spring Boot:

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiMetadataConfiguration {

    @Bean
    OpenAPI shopOpenApi(
            @Value("${api.document.version}") String documentVersion) {
        return new OpenAPI()
            .info(new Info()
                .title("Shop API")
                .description("API for managing orders and customers")
                .version(documentVersion)
                .contact(new Contact()
                    .name("Shop API Team")
                    .email("api-team@example.org")
                    .url("https://docs.example.org/shop/support")));
    }
}
~~~

Values with `example.org` are placeholders to replace with your organization's real contacts and URLs. Do not place personal details or sensitive internal addresses in public documents.

You can use `@OpenAPIDefinition` and `@Info` to declare metadata via annotations. When reading versions from build/environment config, an `OpenAPI` bean is often more convenient because properties can be injected. Whichever method you choose, ensure versions and contacts do not vary unintentionally across environments.

`contact` provides API support details. It does not prove who reviewed a release or who executed a build. Reviewers and build actors must be recorded in source/CI systems or a provenance manifest.

## 6. Using extensions for organization-specific metadata

OpenAPI allows Specification Extensions prefixed with `x-`. You can include owning team, service ID, or runbook links if consuming tools understand them:

~~~yaml
info:
  title: Shop API
  version: 1.4.2
  contact:
    name: Shop API Team
    email: api-team@example.org
  x-owner-team: commerce-platform
  x-support-url: https://docs.example.org/shop/support
~~~

Extensions such as `x-owner-team` are organization-specific metadata, not mandatory standard OpenAPI fields. Tools unfamiliar with them may ignore them. Therefore:

- Keep standard support metadata inside `info.contact`.
- Use extensions for supplemental details valuable to internal tooling.
- Never place tokens, passwords, private keys, or secrets in extensions.
- Never use extensions as substitutes for access control or provenance signatures.
- Never assume `x-owner-team` proves that team approved the artifact.

Per-build values such as commit SHA, build run ID, timestamp, and digest usually belong in a sidecar manifest/attestation. This keeps the document focused on describing the API and lets pipelines record provenance after generating the file.

## 7. Creating a release manifest alongside the OpenAPI file

A separate manifest can link the document to its source and build. The example below is a project-managed illustrative schema, not a mandatory `springdoc` format:

~~~json
{
  "manifestVersion": 1,
  "artifact": {
    "name": "shop-openapi-public",
    "version": "1.4.2",
    "file": "shop-api-public.json",
    "mediaType": "application/vnd.oai.openapi+json",
    "sha256": "REPLACE_WITH_REAL_SHA256"
  },
  "document": {
    "title": "Shop API",
    "documentVersion": "1.4.2",
    "apiVersion": "v1",
    "openApiSpecification": "3.1.0",
    "group": "public"
  },
  "source": {
    "repository": "https://example.org/commerce/shop-service",
    "revision": "8f2a6d4c...",
    "releaseTag": "shop-api-1.4.2",
    "workingTreeClean": true
  },
  "build": {
    "runId": "ci-18452",
    "workflow": "publish-openapi",
    "builder": "company-ci",
    "jdk": "21",
    "springBoot": "3.x.y",
    "springdocOpenApi": "2.x.y",
    "generatedAt": "2026-11-20T10:30:00Z"
  },
  "ownership": {
    "team": "commerce-platform",
    "contact": "https://docs.example.org/shop/support"
  },
  "publication": {
    "uri": "https://artifacts.example.org/openapi/shop-api/1.4.2/",
    "publishedAt": "2026-11-20T10:31:00Z"
  }
}
~~~

Replace all illustrative placeholders with real values in the pipeline. Never let `REPLACE_WITH_REAL_SHA256`, placeholder versions, or unverified abbreviated commits appear in release manifests.

The manifest should specify the `group` because an application may export multiple OpenAPI documents such as `public`, `admin`, and `partner`. Each file must have its own digest. If the same release produces both JSON and YAML, record each artifact separately or use an artifacts array where each item has its own filename, media type, and digest.

## 8. Generating checksums for generated documents

Checksums verify that a downloaded file matches the published bytes identically. Compute the digest after exporting and after any final normalization/transformation steps.

On Linux/macOS:

~~~bash
sha256sum build/contracts/shop-api-public.json
~~~

On Windows PowerShell:

~~~powershell
Get-FileHash .\build\contracts\shop-api-public.json -Algorithm SHA256
~~~

Example writing the result to a checksum file:

~~~bash
sha256sum build/contracts/shop-api-public.json \
  > build/contracts/shop-api-public.json.sha256
~~~

When consumers download the file, they recompute SHA-256 and compare it against the digest distributed via a trusted channel. If the two values differ, the file was modified or download/storage failed; do not proceed with SDK generation or contract deployment from that file.

A checksum only proves two copies share identical bytes when digests match. If an attacker can alter both the file and the checksum in the same location, a standalone checksum does not prove origin. For releases needing stronger assurances, sign the manifest or issue an attestation authenticated by the build platform's identity.

## 9. Linking checksums to the exact source revision

A digest alone does not reveal which source code generated the file. The manifest must connect at least three elements:

1. Source revision: checked-out commit SHA.
2. Build invocation: workflow, run ID, builder, and dependency/tool versions.
3. Artifact subject: filename and SHA-256 digest.

The build process should read the commit from the CI checkout rather than manually entered commit hashes. Example:

~~~bash
git rev-parse HEAD
git status --porcelain
git describe --tags --always
java -version
~~~

If `git status --porcelain` produces output, the working tree is dirty. The release pipeline should halt or explicitly record additional modifications and their origin. Never apply a release tag to a document generated from uncommitted source changes without recording it.

When building from pull requests, record the PR number/URL and commit SHA so internal consumers can trace back to the review. When building releases, record the release tag alongside the commit SHA; tags help humans recognize releases, while commit SHAs pinpoint exact source contents.

## 10. Recording the OpenAPI generation environment

Two builds from the same source can produce different documents if profiles, configs, dependencies, or runtime endpoints differ. The manifest should capture inputs that can alter output:

| Input | Why Record It |
| --- | --- |
| Spring Boot version | Affects runtime, MVC/WebFlux, and introspected metadata |
| `springdoc-openapi` version | Affects annotation scanning and OpenAPI model generation |
| Resolved `swagger-core` version | Affects annotations/models and serialization |
| JDK version | Helps reproduce the build environment |
| Maven/Gradle version | Helps reproduce lifecycle/tasks and dependency resolution |
| Active Spring profile | May enable/disable controllers, beans, or configurations |
| OpenAPI group | Determines the exported operation subset |
| API docs URL/path | Determines which endpoint the plugin fetches |
| Feature flags/environment config | May alter beans or routes |

Never record secrets or credential values in manifests. If sensitive configuration affects the build, record only the secret reference name or environment variable name and managed config version, never secret values.

For multi-profile environments, generate documentation using a standardized export profile. Avoid letting output depend on environment variables omitted from the build definition.

## 11. Organizing document versioning

Choose versioning rules before publishing. You can apply semantic versioning to OpenAPI artifacts if the project clearly defines each component:

| Change Level | Suggested Release Rule | Example |
| --- | --- | --- |
| Major | Contract has breaking changes or consumers must migrate | `1.4.2` → `2.0.0` |
| Minor | Compatible contract additions per project policy | `1.4.2` → `1.5.0` |
| Patch | Description fixes, typos, or metadata not changing the contract | `1.4.2` → `1.4.3` |

This is an organizational policy, not an automatic rule of OpenAPI. A seemingly additive change can still break consumers relying on enum exhaustiveness, strict schema validation, or generated code. Before bumping minor, run compatibility checkers and review consumer impact.

If `info.version` is synchronized with the artifact version, document that rule in the release policy. Otherwise, the manifest must carry `documentVersion`, `apiVersion`, and `artifactVersion` to prevent confusion.

Do not use `latest` as the sole version. A `latest` alias can point to the newest release for browsing convenience, yet consumers and production systems must pin an immutable version.

## 12. Artifact naming and publication paths

Filenames should let recipients identify the service, group, and version:

~~~text
shop-api-public-1.4.2.json
shop-api-admin-1.4.2.json
shop-api-public-1.4.2.yaml
~~~

Publication paths can be organized by service and version:

~~~text
openapi/
  shop-api/
    1.4.1/
      shop-api-public.json
      shop-api-public.json.sha256
      provenance.json
    1.4.2/
      shop-api-public.json
      shop-api-public.json.sha256
      provenance.json
    latest/
      shop-api-public.json
~~~

Versioned release directories hold immutable artifacts. `latest` is a mutable alias and should be updated only after the versioned release is published, verified, and approved.

With Maven repositories, you can publish OpenAPI files as classifiers or standalone artifacts. With generic package registries, object storage, or developer portals, apply the same principle: embed versions in coordinates or paths, accompany files with metadata and checksums, and enforce access control.

## 13. Never overwrite published release artifacts

A release version must always point to identical content. If a bug is discovered in document `1.4.2`:

1. Fix the source or document-generation configuration.
2. Create a new build from a reviewed commit.
3. Run validation and compatibility checks.
4. Release a new version, such as `1.4.3`, or mark the old release withdrawn per policy.
5. Write release notes explaining the reason and impact.

Do not silently upload new content overwriting `1.4.2`. Once consumers have downloaded a version, changing content under that same version invalidates checksums, caches, generated SDKs, and audit trails.

If urgent remediation is required, mark the entry `withdrawn` or `deprecated` in the catalog/registry, preserve the old artifact's metadata, and publish a replacement version. Exact mechanics depend on the artifact repository.

## 14. Distinguishing release artifacts from preview artifacts

Documents generated from pull requests or unreleased branches help reviewers, yet should never sit alongside stable releases without clear labeling.

| Type | Source | Distribution Approach |
| --- | --- | --- |
| PR preview | Pull request commit | URL includes PR number and commit SHA; expires per retention policy |
| Branch snapshot | Development branch | Path/manifest includes branch and commit; not treated as a release |
| Release candidate | Pre-release tag or commit | Tagged RC, never overwrites stable releases |
| Stable release | Approved commit/tag | Immutable version, full checksums, and provenance |

Examples:

~~~text
previews/pr-482/8f2a6d4c/shop-api-public.json
snapshots/develop/4c9b21e0/shop-api-public.json
releases/1.4.2/shop-api-public.json
~~~

Previews can be purged per retention policy. Stable releases should be archived according to organizational support and audit policies.

## 15. Publishing workflow with provenance

A document publishing pipeline can be structured as follows:

~~~mermaid
flowchart TD
    A[Checkout reviewed commit] --> B[Start Spring Boot with export profile]
    B --> C[Springdoc generates OpenAPI per group]
    C --> D[Validate JSON/YAML and contract]
    D --> E[Compute SHA-256 per artifact]
    E --> F[Generate release manifest]
    F --> G[Sign manifest or create provenance attestation]
    G --> H[Publish to immutable version path]
    H --> I[Consumers download and verify digest/attestation]
    I --> J[Generate SDK or update developer portal]
~~~

Ordering matters:

- Generate documents from the exact reviewed source revision.
- Validate before publishing to avoid releasing empty or misgrouped files.
- Compute digests after all file transformations finish.
- Build manifests from actual computed digests, not manual entry.
- Attestations must reference the digest of the specific artifact.
- Publish the artifact, manifest, and attestation under one release version.
- Update the `latest` alias only after release verification succeeds.

If the pipeline emits both JSON and YAML, each artifact needs its own digest. If exporting multiple groups, never share one digest or filename across different documents.

## 16. Signing and verifying provenance

Pipeline-written JSON manifests aid traceability yet can be tampered with if someone has write access to the same artifact store. For stronger verification, use digital signatures or attestations bound to build platform identity.

SLSA/in-toto provenance can describe:

- Subject: the artifact and its digest.
- Build definition: workflow and build parameters.
- Resolved dependencies: source revision and resolved dependency inputs.
- Builder: identity of the build platform.
- Run details: metadata of the build execution.

Consumers must verify both the signature/builder identity and the provenance contents. Simply seeing a file named `provenance.json` does not mean it is a trustworthy attestation.

When using GitHub Actions, GitHub Artifact Attestations can generate attestations binding artifacts to repository, commit SHA, and workflow. This is one platform-specific option; other CI platforms offer equivalent signing/attestation mechanisms.

Do not claim a document meets a SLSA Build Level solely because checksums or manifests were generated. Assurance levels depend on the full build platform, attestation generation, workflow integrity, and verification process.

## 17. Verifying artifacts before publication

Before publishing, pipelines should check:

- File exists, is non-empty, and parses cleanly.
- `openapi`, `info.title`, and `info.version` contain valid values.
- Document belongs to the intended service and group.
- `paths`, `components`, and `$ref` pointers are valid.
- Contact/owner links and external documentation are valid.
- No internal endpoints or sensitive schemas entered the public build.
- Operation, schema, and security metadata match the release.
- Checksum was computed from the final file.
- Manifest points to the right commit, build run, artifact name, and digest.
- Publication URI targets the right version path.

Example checking JSON metadata with `jq`:

~~~bash
jq -e '
  .openapi and
  .info.title == "Shop API" and
  .info.version == "1.4.2" and
  (.paths | type == "object")
' build/contracts/shop-api-public.json
~~~

Verify checksum after download:

~~~bash
sha256sum --check shop-api-public.json.sha256
~~~

This command assumes the checksum file lists the matching filename in the same directory. On Windows, use `Get-FileHash` and compare against the digest in the manifest.

Structural validation does not replace security review. An OpenAPI document can parse cleanly while still mistakenly exposing admin endpoints or internal headers.

## 18. Managing document access permissions

Not every OpenAPI document is public. Public, partner, and internal documents can contain different endpoints, hostnames, schemas, or security flows.

Enforce access control by group and audience:

| Audience | Document Scope | Distribution Method |
| --- | --- | --- |
| Public developer | Operations permitted for public disclosure | Public portal/CDN |
| Partner | Contracts under integration agreements | Authenticated portal or private artifact registry |
| Internal engineering | Internal and operational endpoints | Internal portal, SSO, or private registry |

`@Hidden` or group filters decide which operations appear in a document. They do not replace authorization on HTTP endpoints. Unauthorized callers must still be rejected by Spring Security/gateways even if endpoints are absent from documentation.

Public manifests should not contain internal hostnames, filesystem paths, tokens, secrets, logs with sensitive data, or unnecessary build-environment details. Emit a filtered public manifest when needed while retaining detailed provenance in internal systems.

## 19. Tracking changes and release history

Every release should carry concise release notes:

~~~markdown
## Shop API 1.4.2

- Source revision: 8f2a6d4c...
- OpenAPI document: 1.4.2
- Group: public
- Artifact: shop-api-public-1.4.2.json
- SHA-256: <digest>
- Owner: commerce-platform

### Changes
- Added response field estimatedDeliveryAt.
- Updated validation error descriptions.
- No changes to existing endpoints or request schemas.
~~~

Release notes tell consumers why they should upgrade and help reviewers understand differences. For breaking changes, specify affected endpoints/fields/responses, migration steps, and the old version's end-of-support date.

Archive each release's OpenAPI snapshot alongside its manifest and release notes. During incident investigations, you can verify exactly which document a consumer downloaded and match digests instead of relying on whatever `latest` currently holds.

## 20. Handling documents with unknown provenance

If you receive an OpenAPI file lacking a manifest or clear owner:

1. Do not guess the source revision from the filename.
2. Inspect `info`, contact details, server URLs, and any metadata extensions.
3. Search registries for matching artifact coordinates, release tags, or CI runs.
4. Compute a digest to pin the exact file under investigation.
5. Contact the API owner through verified support channels.
6. Only feed the file into SDK generation or deployment workflows after confirming its origin and compatibility.

If the commit or build cannot be traced, record provenance as unknown. Never fabricate guessed commit SHAs or release versions in a manifest merely to make records look complete.

## 21. Common mistakes

**Recording only `info.version` and assuming provenance is complete.** This value does not identify the source commit, builder, dependencies, or group. Add a manifest and digest.

**Recording only the `main` branch.** Branches move. Store commit SHAs and release tags.

**Using a single version for OpenAPI Specification, API, and `springdoc`.** These are separate versions. Record each value with its exact meaning.

**Listing the individual file creator as owner.** Creators may change roles while ownership persists. Record the accountable team and a maintained contact channel.

**Manifest has a digest without a signature.** Digests detect byte changes when compared against a trusted reference; signatures/attestations verify who published the artifact and how it was built.

**Computing checksums before normalizing the file.** Digests break once the file changes. Compute hashes after the final processing step.

**Republishing a modified file under the same release version.** Consumers can receive different bytes for the same version. Publish a new version or mark the old release withdrawn.

**Using `latest` in production integrations.** Aliases shift. Pin explicit immutable versions and reserve `latest` for discovery.

**Putting secrets or internal details in public manifests.** Publish only necessary metadata; keep detailed provenance in private systems.

**Assuming `@Hidden` protects endpoints.** The annotation affects documentation only. Use Spring Security/gateways to protect actual routes.

## 22. Checklist for publishing traceable documentation

- [ ] Active API owner and team contact are maintained.
- [ ] `info.title`, `info.version`, and `info.contact` accurately describe the document.
- [ ] OpenAPI Specification version, document version, and API runtime version are distinguished.
- [ ] Release was built from a reviewed commit SHA and clear tag.
- [ ] Working tree was clean or any extra changes were documented.
- [ ] Manifest records source repository, revision, build run, tool versions, and group.
- [ ] Manifest records artifact filename, media type, publication URI, and SHA-256.
- [ ] Digest was computed after the final export/normalization step.
- [ ] JSON/YAML parses cleanly and all `$ref` pointers are valid.
- [ ] Correct group and audience; no internal endpoints/schemas leaked.
- [ ] Release artifact is published at an immutable version path.
- [ ] Manifest/release notes accompany the artifact.
- [ ] Attestation/signature is generated and verified if required by organizational assurance levels.
- [ ] `latest` alias is updated only after release verification passes.
- [ ] Snapshots, manifests, and release notes are archived under retention policy.
- [ ] Deprecation/withdrawal and ownership transfer procedures exist.

## 23. Conclusion

To make an OpenAPI document verifiable and maintainable over the long term, link it to its owner, source revision, build environment, artifact version, and publication location. Use `info.contact` for support contacts; store commit SHA, CI run, tool versions, group, and digest in a manifest; use checksums to detect byte tampering and signatures/attestations when origin verification is needed. Publish releases under immutable versions, keep snapshots alongside release notes, and use `latest` solely as an alias. Consumers can then trace exactly which document was published, who owns it, and which source produced it.

## 24. References

- [OpenAPI Specification 3.1 — Info Object](https://spec.openapis.org/oas/v3.1.1.html#info-object): meaning of `info.version`, contact, description, and OpenAPI document metadata.
- [OpenAPI Specification 3.1 — Specification Extensions](https://spec.openapis.org/oas/v3.1.1.html#specification-extensions): extending documents with `x-` prefixed fields.
- [SLSA — Build Provenance](https://slsa.dev/spec/v1.2/build-provenance): linking artifacts to build definitions, dependencies, builders, and run details.
- [SLSA — Provenance](https://slsa.dev/spec/v1.2/provenance): provenance concepts and tracing artifacts back to their build origin.
- [GitHub Docs — Artifact attestations](https://docs.github.com/en/actions/concepts/security/artifact-attestations): provenance and integrity guarantees for artifacts.
- [GitHub Docs — Using artifact attestations to establish provenance](https://docs.github.com/en/actions/how-tos/secure-your-work/use-artifact-attestations/use-artifact-attestations): generating artifact attestations from workflows and subject paths.
- [springdoc-openapi — Getting Started](https://springdoc.org/getting-started.html): how `springdoc` integrates with Spring Boot and generates OpenAPI documents from applications.
