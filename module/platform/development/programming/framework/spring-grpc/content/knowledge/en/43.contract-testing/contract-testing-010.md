# Breaking Change Checks in CI

## 1. Why Check for Breaking Changes?

In **Spring gRPC**, Protocol Buffers defines the contract between client and server: package, service, RPC methods, request/response messages, field numbers, data types, and enums. Many clients can be deployed independently of the server. When a schema change is merged without compatibility checks, older clients may fail to call the new server, or older messages may be misinterpreted.

Breaking change checks in CI compare the changing branch's schema against a chosen baseline. If a change violates compatibility rules, the pipeline stops before the schema is merged or released.

The goal is not to block every change. The goal is to catch dangerous changes early, requiring developers to choose a safe contract evolution path or proactively plan a migration.

## 2. Distinguishing Wire Compatibility from Source/API Compatibility

Protobuf has multiple layers of compatibility:

- **Wire compatibility:** bytes serialized under the new schema can be parsed under the old schema or vice versa without altering the meaning of existing data.
- **JSON compatibility:** field names, enums, and JSON mapping rules remain compatible with clients using ProtoJSON or gateways.
- **Generated source compatibility:** generated Java code retains the APIs that client/server source code currently uses.
- **Behavioral compatibility:** the service preserves business semantics, access permissions, validation, and response meaning.

A change can be wire-compatible yet still break source code or behavior. For example, adding an enum value usually does not break the wire format, but Java code using exhaustive switches or clients assuming a fixed set of enums may need updating.

Therefore, CI needs at least two check layers: schema breaking checks and build/tests on generated code. For critical APIs, add compatibility tests between clients and servers at different versions.

## 3. Protobuf Changes That Commonly Cause Breaking Changes

| Change | Risk | Safe Approach |
| --- | --- | --- |
| Change field number | Old parsers read wrong or skip data | Never change already-released field numbers |
| Reuse deleted field number | Old data can be interpreted as the new field | Reserve both removed number and name |
| Change wire type | Old parsers fail to decode properly | Add a new field, migrate, then retire the old field |
| Change service package | Full RPC method path changes | Keep the package; if a new API is needed, create a new service/version |
| Delete or rename RPC | Old clients call a non-existent method | Keep the old method during the migration period |
| Change request/response type | Generated API and wire contract can change | Create a new method or message with a plan |
| Change unary to streaming or vice versa | RPC shape and generated stubs change | Create a new RPC |
| Rename field | Can break generated Java API and ProtoJSON names | Keep the name or create a new field with migration |
| Change Java package option | Generated Java package changes | Change only when accepting a source migration |
| Change field semantics without changing schema | Clients interpret data differently than before | Version the contract or add a field with clear semantics |

### 3.1. Field Numbers Are Wire Identifiers

Field numbers are encoded in Protobuf tags. Never change the number of an already-released field:

~~~proto
message GetOrderRequest {
  string order_id = 1;
}
~~~

If `order_id` is changed from number 1 to 2, older clients sending field 1 and a new server reading only field 2 will not receive the expected value.

When removing a field, reserve its number and name:

~~~proto
message GetOrderRequest {
  reserved 1;
  reserved "order_id";

  string resource_id = 2;
}
~~~

This example illustrates retiring the old `order_id` field and adding `resource_id` with new semantics. Number 2 must never have been used before. If the goal were merely changing the number of the same `order_id` field, do not do that; keep the old field at number 1 or design a migration with a new field and clear semantics.

### 3.2. Changing Types Can Be Dangerous Even with the Same Wire Type

Some Protobuf types share a wire type yet still have different semantics. For example, `int32` and `sint32` both use varint, yet `sint32` uses ZigZag encoding. Switching between them can cause old values to be misinterpreted.

Do not conclude compatibility simply because two types share a wire type. Check encoding, value range, signedness, default/presence, and how generated code represents the data.

### 3.3. Enums and Unknown Values

Never change the numeric value of an already-released enum. When adding an enum value, the wire format usually stays compatible, yet older clients may lack a branch handling the new value. Java code, ProtoJSON gateways, and database mappings must have a strategy for handling unknown values.

~~~proto
enum OrderState {
  ORDER_STATE_UNSPECIFIED = 0;
  ORDER_STATE_PENDING = 1;
  ORDER_STATE_CONFIRMED = 2;
  ORDER_STATE_CANCELLED = 3;
}
~~~

Keep value 0 as unspecified/default per API convention. When deleting an enum value, reserve both its number and name to prevent reuse.

## 4. Service and RPC Method Changes

A gRPC RPC address is formed from package, service, and method, for example:

~~~text
/orders.v1.OrderService/GetOrder
~~~

Changing the package from `orders.v1` to `orders.v2` or renaming `OrderService`/`GetOrder` alters the full method name. Older clients continue calling the old path and may receive `UNIMPLEMENTED`.

When a new API with incompatible semantics is required:

- Create a new package/version such as `orders.v2`.
- Or add a new RPC to the existing service if the contract and versioning policy permit it.
- Maintain the old RPC during the client migration period.
- Monitor usage per method to know when the old method can be retired.

Never change a unary RPC into server-streaming just because you want to send more results. Generated stubs, flow control, terminal semantics, and client code all differ. Create a new method with an appropriate response contract.

## 5. Configuring Buf for Schema Checks

Buf provides linting and breaking-change detection for Protobuf. Example Buf v2 workspace configuration:

~~~yaml
version: v2

modules:
  - path: proto

lint:
  use:
    - STANDARD

breaking:
  use:
    - FILE
~~~

With the configuration above:

- The schema module lives in the `proto` directory.
- Lint checks conventions and common schema mistakes.
- Breaking check uses the `FILE` rule set to detect incompatible changes at file scope.

The rule set must be chosen according to API policy. `FILE` is usually stricter than `WIRE` and can catch source-level changes too. If the organization only wants to guarantee binary wire compatibility, `WIRE` may be chosen; if clients use ProtoJSON, consider `WIRE_JSON` or a stricter rule set. Read the Buf documentation for your pinned version to understand the exact scope of each rule.

Do not pick a rule set just to keep the pipeline green. Decisions must be based on actual client types: Java gRPC stubs, ProtoJSON gateways, mobile apps, or consumers generating code from the schema.

## 6. Running Breaking Checks on Developer Machines

After installing and pinning the Buf version in the project toolchain, run:

~~~bash
buf lint
buf breaking --against '.git#branch=main'
~~~

The second command compares the current schema against the schema on branch `main`. When running in CI, checkout must include enough Git history/refs for Buf to read the baseline. If using a shallow checkout with only one commit, fetch the baseline branch before running.

For multi-module repositories, run the command at the workspace root and clearly specify which module is being compared. Do not allow one module's schema changes to accidentally be compared against another module's baseline.

In projects using Buf Schema Registry, the baseline can be a published commit/schema version rather than a Git branch. The essential point is that the baseline must represent a released contract or one accepted by the target branch.

## 7. Integrating into the CI Pipeline

A suggested pipeline:

~~~mermaid
flowchart TD
    A[Pull request] --> B[Checkout with baseline history]
    B --> C[Pin and install Buf]
    C --> D[buf lint]
    D --> E[buf breaking against target baseline]
    E --> F[Generate Java sources]
    F --> G[Check generated diff]
    G --> H[Compile and unit tests]
    H --> I[Client/server compatibility tests]
    I --> J[Merge allowed]
~~~

Breaking checks should run early, before time-consuming build/test steps. However, passing a breaking check does not replace compilation, generated code checks, or integration tests.

Illustrative GitHub Actions example:

~~~yaml
name: protobuf-contract

on:
  pull_request:
    paths:
      - "proto/**"
      - "buf.yaml"
      - "buf.lock"
      - "build.gradle"
      - ".github/workflows/protobuf-contract.yml"

jobs:
  contract:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Install pinned Buf CLI
        run: |
          # Install the Buf version pinned by this repository.
          buf --version

      - name: Lint Protobuf
        run: buf lint

      - name: Check breaking changes
        run: buf breaking --against '.git#branch=main'

      - name: Build and test
        run: ./gradlew test
~~~

This is a workflow skeleton: the Buf installation step must be replaced with an action or installation script pinned to a version in the repository. Do not use a floating latest version in CI because the same schema could get different results when rule sets or tool versions change.

If a pull request targets a release branch other than `main`, the baseline must be the actual target branch. The pipeline needs to resolve the proper base ref rather than always comparing against `main`.

## 8. Generated Java Code Must Also Be Checked

Schema checks passing does not guarantee Java code compiles. Changes such as `java_package`, `java_multiple_files`, outer class name, or plugin options can alter the generated API even when the wire format does not change.

CI should:

1. Generate Java sources from the schema using the exact pinned `protoc` and plugin versions.
2. If generated code is committed, verify the working tree has no unexpected diffs after generation.
3. Compile server and client modules.
4. Run unit tests for mappers, enum handling, and validation.
5. Verify code using new fields handles defaults/presence properly.

Never hand-edit generated Java sources. Edit `.proto` files or generator configuration and regenerate.

## 9. Compatibility Testing Between Client and Server

Breaking checks verify schema structure. Compatibility tests verify the real application can communicate across versions.

A basic matrix:

| Client | Server | Question |
| --- | --- | --- |
| Old client | New server | Can the new server still serve currently deployed clients? |
| New client | Old server | Does the new client send fields/methods the old server does not understand in a way that causes errors? |
| New client | New server | Do versions from the same release work together? |
| Old client | Old server | Does the pre-change baseline still run as before? |

Not every combination has to be supported indefinitely. Policy must define the compatibility window clearly, such as the new server supporting old clients for at least two release cycles.

With Protobuf, unknown fields are typically ignored or preserved by parsers depending on the API/runtime and how messages are handled. Thus adding an optional field can often be wire-compatible, yet application code must never assume older servers understand the new field.

## 10. Adding Fields Safely with an Expand-Contract Strategy

When needing to add information to a request:

~~~proto
message CreateOrderRequest {
  string customer_id = 1;
  repeated OrderLine lines = 2;
  string idempotency_key = 3;
}
~~~

Before releasing a new field:

1. Pick a field number never used before and outside any reserved range.
2. Choose clear semantics; define optional/default behavior.
3. Deploy servers accepting both old requests without the field and new requests with the field.
4. Release compatible servers first if new clients will send the field.
5. Release new clients after servers support it.
6. Remove old fields only after all clients have migrated and policy permits.

For fields with important presence, use `optional` or an appropriate message wrapper instead of relying on default values. Distinguish "not sent" from "default value sent" if business logic needs those two states to differ.

## 11. When Are Breaking Checks Not Enough?

Buf cannot understand all business semantics. The following changes may not be flagged as schema-breaking yet still break clients:

- Keeping the same field while changing units from milliseconds to seconds.
- Keeping an enum value while changing its business meaning.
- Starting to require a previously optional field.
- Tightening validation so previously valid requests receive `INVALID_ARGUMENT`.
- Changing authorization policy or tenant scope.
- Changing ordering, consistency, or side effects of a method.
- Lowering internal deadlines so RPCs frequently return `DEADLINE_EXCEEDED`.

These changes require contract tests, consumer-driven tests, integration tests, or behavioral tests. For critical APIs, retain test cases representing deployed clients and run them against server candidates.

## 12. Handling Intentional Breaking Changes

Sometimes breaking changes are necessary, such as changing a data model or retiring an unsuitable API. Never bypass CI by disabling rules or deleting the baseline.

A controlled process:

1. Document the rationale and impacted clients/consumers.
2. Create a new API version or new method.
3. Deploy servers supporting both old and new APIs.
4. Migrate clients in waves, monitoring usage and error rates of the old method.
5. Announce deprecation and sunset dates.
6. Remove the old API only once usage reaches zero or owners approve.
7. Keep breaking checks enabled; if an exception is needed, require API owner review and record scope/expiry.

An approved breaking change still needs a rollout plan and compatibility evidence. Approval alone does not make older clients compatible.

## 13. Reading Buf Breaking Results

When CI reports a breaking change:

- Inspect the file, message, field, or RPC flagged by the rule.
- Determine whether it is a wire, JSON, or source-level incompatibility per the rule set.
- Verify the baseline being compared against is the right branch/release schema.
- If the change was unintended, restore the old contract.
- If the change is needed, add a new field/method/version and execute expand-contract.
- If you believe a rule is inappropriate, ask the API owner to review the rule set; do not delete rules just to turn the pipeline green.

Do not resolve it by updating the baseline to the new schema itself within the same pull request. Doing so renders the comparison meaningless and can mask breaking changes before review.

## 14. Common Mistakes

1. **Only compiling generated code.** Compiling code does not prove older clients are compatible with the new server.
2. **Only running Buf lint.** Lint checks style/schema quality and does not replace breaking checks.
3. **Changing or reusing field numbers.** This can cause old data to be misinterpreted.
4. **Checking only wire compatibility.** Java source or ProtoJSON clients can still be affected.
5. **Not pinning Buf/protoc/plugin versions.** CI results and generated code can drift unexpectedly.
6. **Comparing against the wrong baseline.** Pull request targets a release branch yet compares against `main`.
7. **Not fetching Git history in CI.** The breaking command cannot access the baseline branch.
8. **Assuming adding enum values is always safe.** Older clients may fail to handle unknown values.
9. **Skipping behavioral tests.** Unchanged schemas with altered semantics or validation can still break clients.
10. **Disabling breaking checks to merge.** Removes a vital safeguard for published contracts.

## 15. Practice Exercises

Using the `orders.v1.OrderService` contract:

1. Configure Buf v2 for the `proto` directory and choose a breaking rule set suited for Java gRPC clients and a ProtoJSON gateway.
2. Establish a baseline schema on the `main` branch or a release tag.
3. Try adding an optional field with a new number and verify CI accepts it.
4. Try changing a field number, deleting an RPC, and changing the package; verify CI rejects them.
5. Try deleting a field and reserving both its number and name; verify the rule set and review policy yield the expected outcome.
6. Try adding an enum value and write a test proving older clients handle unknown values safely.
7. Generate Java code with the pinned toolchain, check the diff, and compile client/server.
8. Run compatibility tests between older clients and the new server.
9. Write a migration plan for an intentional breaking change while keeping the CI gate active.

**Completion criteria:** learners can configure Buf breaking checks in CI, choose the right baseline, distinguish wire/JSON/source/behavioral compatibility, recognize risky Protobuf/gRPC changes, and design verified migrations instead of bypassing gates.

### References

- [Buf Breaking](https://buf.build/docs/breaking/): detecting incompatible changes in Protobuf schemas.
- [Buf Configuration](https://buf.build/docs/configuration/v2/buf-yaml/): configuring modules, lint, and breaking rule sets.
- [Buf CLI Reference](https://buf.build/docs/reference/cli/buf/breaking/): breaking command and baseline inputs.
- [Protocol Buffers Editions and Language Guide](https://protobuf.dev/programming-guides/proto3/): field numbers, presence, enums, and schema evolution.
- [Protocol Buffers Best Practices](https://protobuf.dev/best-practices/dos-donts/): never changing/reusing field numbers and how to reserve fields.
- [gRPC Documentation](https://grpc.io/docs/): service definitions, generated code, and RPC contracts.
- [Spring gRPC Reference](https://docs.spring.io/spring-grpc/reference/): gRPC client/server integration in Spring.
