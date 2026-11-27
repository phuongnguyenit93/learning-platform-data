# Checking Schemas With Lint and Breaking Change Checks

A Protocol Buffers file that compiles cleanly does not automatically mean the gRPC contract is safe to release. The compiler primarily checks syntax and types; it does not warn about every change that could prevent old clients from calling the service, cause payloads to decode incorrectly, or alter field semantics. In **Spring gRPC**, you should add two checks to your schema workflow: **lint** to enforce conventions and spot suspicious structures, and a **breaking change check** to compare the edited schema against an existing version.

This lesson focuses on configuring and running both checks with **Buf**, choosing an appropriate Git baseline, reading results, and integrating them into CI. The examples use the `shop.catalog.v1` protobuf package; the same principles apply to unary request/response messages and messages in streaming RPCs.

## 1. Lint and Breaking Change Checks Solve Two Different Problems

| Check | Question | Required input | Example findings |
| --- | --- | --- | --- |
| **Lint** | Does the current schema follow conventions and sound structure? | Current `.proto` files | Missing enum suffix, missing zero `UNSPECIFIED` value, unused imports, or inconsistent naming |
| **Breaking change check** | Does the current schema break the contract compared to a prior version? | Current schema and an old baseline | Changing a field number, deleting a published field, changing a type, or renaming a service and altering the RPC path |

Lint typically runs during development or when opening a pull request. A breaking check requires a **baseline**, such as the `main` branch or a release tag. Without a baseline, the tool cannot know whether a newly removed field was ever used by clients.

The two steps complement each other:

- A schema can pass lint cleanly yet still be breaking if it changes a package or field number.
- A wire-compatible change can still fail lint by violating naming conventions or enum zero rules.
- Neither replaces testing generated Java code, server behavior, authorization, deadlines, or domain correctness.

## 2. Configuring Buf for a Protobuf Module

Suppose sources live in the `proto` directory of a Spring Boot project. Place `buf.yaml` at the repository root so Buf and Git share the same root:

```yaml
version: v2

modules:
  - path: proto

lint:
  use:
    - STANDARD

breaking:
  use:
    - FILE
```

Explanation of choices:

- `version: v2` uses the Buf v2 configuration format.
- `modules` specifies the directory containing `.proto` files; in this example, `buf.yaml` sits directly inside `proto` so the module path is a dot.
- `STANDARD` enables the standard lint rule set, keeping names, packages, imports, and declarations consistent.
- `FILE` selects a strict breaking-change policy scoped to files and generated APIs. For public contracts, this is a safe starting point; a team can choose another category once it understands the required level of protection.

If the project imports from external modules, declare dependencies under `deps` in the Buf v2 config and run `buf dep update` at the root to generate/update `buf.lock`. Do not copy external dependency `.proto` files into your own source tree just to make lint pass; manage dependencies by version.

### Choosing a Breaking Category by Compatibility Scope

Buf offers categories for different inspection levels. Agree on a policy across the team rather than arbitrarily lowering strictness whenever an error appears:

| Category | Broad scope | When to consider |
| --- | --- | --- |
| `FILE` | Strict level, protecting compatibility at the file and generated-API scope | Public APIs needing tight control over source/descriptor changes |
| `PACKAGE` | Checks at the package scope, less restrictive on certain file-level moves | Schemas governed by package with clear file layout conventions |
| `WIRE_JSON` | Focuses on protobuf wire and JSON compatibility | APIs serving both binary gRPC and ProtoJSON/JSON gateways |
| `WIRE` | Focuses on binary protobuf wire compatibility | Use only when the contract truly has no JSON consumers and the narrower scope is accepted |

Do not pick `WIRE` merely to make CI green if consumers use ProtoJSON, HTTP transcoding, or JSON-encoded enum/field data. For public contracts, using an appropriately strict category is usually easier to maintain than accumulating indefinite exemptions.

## 3. Running Lint and Breaking Checks

Run the commands from the repository root where `buf.yaml` lives:

```bash
buf lint
buf breaking --against '.git#branch=main'
```

`buf lint` analyzes the current schema against your configuration. `buf breaking` compares the working schema against the schema on `main`; when opening a pull request, the baseline branch should be the target branch into which changes will merge.

When cutting an official release, you can compare against a tag:

```bash
buf breaking --against '.git#tag=v1.4.0'
```

The baseline must represent an accepted schema that has consumers. Comparing against a branch that already includes your own changes can hide breaking changes. If a repository uses a shallow clone in CI, fetch sufficient Git history so Buf can access the baseline branch or tag.

### Lint Is Not a Formatter

Lint reports rule violations; it does not mean every change can be applied mechanically. When a rule asks to rename a field or package, assess API impact before editing. Never change field numbers or rename public symbols solely to satisfy lint without a compatibility plan.

## 4. Reading Breaking Check Errors by Example

Suppose the baseline contains:

```proto
syntax = "proto3";

package shop.catalog.v1;

service CatalogService {
  rpc GetProduct(GetProductRequest) returns (GetProductResponse);
}

message GetProductRequest {
  string product_id = 1;
}

message GetProductResponse {
  string product_id = 1;
  string display_name = 2;
}
```

A change like the following is breaking:

```proto
package shop.catalog.v1;

service CatalogService {
  rpc FetchProduct(GetProductRequest) returns (GetProductResponse);
}

message GetProductRequest {
  string product_id = 5;
}
```

There are two independent issues:

1. Renaming the RPC from `GetProduct` to `FetchProduct` changes the full method path. Old client stubs still call `/shop.catalog.v1.CatalogService/GetProduct`; a server registering only the new method can return `UNIMPLEMENTED`.
2. Changing `product_id`'s field number from `1` to `5` prevents old payloads from decoding as before. Keeping the field name does not preserve wire identity.

Other changes to watch closely:

| Change | Why it matters | Typical remedy |
| --- | --- | --- |
| Deleting a published field | Old clients may still send or read the field | Keep the field deprecated during transition; when deleting, reserve both number and name |
| Changing a field type | May change wire type or data semantics | Add a new field or create a new message/API version |
| Changing the protobuf package | Changes full message/service names and RPC paths | Keep `v1` running and publish a `v2` package |
| Renaming a service or method | Old client call paths no longer match | Register the old service in parallel during migration |
| Deleting an enum value or reusing its number | Old values may be misinterpreted as different states | Reserve published numbers and names |
| Adding an enum value | Old clients may not recognize the new value | Verify `UNRECOGNIZED` branches and fallback behavior |

When Buf reports a rule and exact location, treat it as evidence of how the schema changed relative to the baseline. Inspect the rule name, file, and affected message/field, then decide whether to fix the schema or deliberately move to a new version. Never delete rules or downgrade categories merely to silence warnings.

## 5. Breaking Changes That Schema Checkers Cannot Catch for You

Breaking checks inspect descriptors and schemas; they do not understand full business semantics. For example, these changes may not be flagged as wire-breaking:

- `price_minor_units` previously represented dollars and is now interpreted as cents while keeping the same type and field number.
- The server begins requiring `locale` even though the new field can be absent in old requests.
- `false` previously meant feature disabled and is now interpreted as unconfigured.
- A query that previously returned strongly consistent data now reads an asynchronous projection without announcing the change.
- The server adds a new permission filter or accidentally exposes products outside the caller's scope.

Therefore, reviews must combine:

1. Automated lint and breaking checks.
2. Semantic review of requests, responses, statuses, and field presence.
3. Compiling generated Java code and all modules using generated classes.
4. Cross-version testing (old client against new server, new client against old server) when multi-version compatibility is required.
5. Integration tests for validation, authorization, deadlines, retries, and streaming if methods use them.

Buf does not replace `protoc`/plugin builds, Java compilation, or integration tests. A schema that passes breaking checks can still break Java compilation after changing `java_package`, or cause clients to mishandle a default value.

## 6. Putting Checks Into CI

On pull requests, CI should fetch full Git history, install the team-pinned Buf version, and run both commands against the protobuf module. Minimal shell job example:

```yaml
steps:
  - name: Checkout
    uses: actions/checkout@v4
    with:
      fetch-depth: 0

  # Install Buf using the project-approved action/toolchain before this step.

  - name: Lint protobuf
    run: buf lint

  - name: Check breaking changes against main
    run: buf breaking --against '.git#branch=main'
```

This is an illustrative `steps` snippet; a real workflow must include the Buf installation step and ensure the `main` ref exists in the checkout. Because `buf.yaml` sits at the repository root and declares module path `proto`, commands run from the root. For pull requests from forks or CI runners lacking permission to fetch the target branch, configure checkout/baseline fetching properly rather than skipping the breaking check.

### When CI Fails

Handle failures in order:

1. Confirm Buf is reading the right module and the right `buf.yaml`.
2. Confirm the baseline is the pre-change branch or tag, not an already-updated snapshot.
3. For lint failures, update the schema to match conventions if doing so introduces no unintended contract changes.
4. For breaking failures, identify which consumers are affected; preserve compatibility or create a `v2`/new endpoint.
5. If your organization permits exceptions, document the exact rule, rationale, scope, and expiration; never disable an entire category.

A pull request should only be approved once the change is understood and backed by a migration plan, not because warnings were suppressed.

## 7. Schema Review Workflow for Spring gRPC

A `.proto` change can follow a concise workflow:

1. **Edit the schema:** assign new field numbers, preserve old tags, and update messages/services per agreed semantics.
2. **Run `buf lint`:** resolve naming, package, enum, and import rules.
3. **Run `buf breaking`:** compare against the target branch or release tag.
4. **Generate code and compile Java:** verify generated classes, stubs, imports, and Spring gRPC endpoints remain source-compatible.
5. **Run contract/integration tests:** verify legacy requests, new responses, gRPC statuses, and business behavior.
6. **Review rollout:** when multiple client/server versions coexist, plan server-first ordering, feature flags, and `v1` retirement timing.

For streaming RPCs, check the schema of every message in the stream as well as semantics when adding new fields or events. A wire-compatible change can still cause old consumers to misunderstand events or mishandle ordering. Lint and breaking checks do not replace tests for stream cancellation, flow control, or unknown-event handling by consumers.

## 8. Pre-Merge Checklist

- [ ] Buf version is pinned in the project's toolchain.
- [ ] `buf.yaml` specifies the correct module, lint category, and breaking category.
- [ ] `buf lint` passes across all relevant schemas.
- [ ] `buf breaking` runs against the right baseline (target branch or release tag).
- [ ] Published field numbers and enum numbers are neither changed nor reused.
- [ ] Deleted fields and enum values have both numbers and names reserved.
- [ ] Package/service/method renames include a plan to keep legacy RPC paths or introduce a new version.
- [ ] Semantic changes undetectable by descriptors have been manually reviewed.
- [ ] Generated Java code compiles and integration tests pass.
- [ ] Any breaking-rule exceptions are documented, scoped, and time-bounded.

**Self-Check**

**Question 1.** Does `buf lint` passing prove a schema will not break old clients?

*Answer:* No. Lint checks conventions and structure of the current schema. You need `buf breaking` against a baseline to detect incompatible changes.

**Question 2.** Why does `buf breaking` require `--against`?

*Answer:* The tool needs a previous schema as a comparison baseline. Without a baseline, it cannot determine which fields, enums, packages, or RPCs changed relative to the prior contract.

**Question 3.** Can renaming an RPC while keeping request/response messages unchanged break clients?

*Answer:* Yes. The full method path changes based on package, service, and method name; old clients still call the old path.

**Question 4.** Does passing `buf breaking` guarantee semantic changes will not cause business bugs?

*Answer:* No. Descriptors cannot tell that `price_minor_units` changed units or that the server tightened validation rules. You need semantic review and integration tests.

**Question 5.** When should you use a release tag as the baseline instead of `main`?

*Answer:* When verifying that a schema remains compatible with a specific release's contract, such as before cutting a new major/minor release or when validating multiple support branches. The baseline must be an accepted version meaningful to consumers.

Lint keeps schemas consistent; breaking checks guard contracts against incompatible structural changes. Putting both in CI, picking the right baseline, and still verifying generated Java code and business behavior helps Spring gRPC teams catch risks before running clients fail.
