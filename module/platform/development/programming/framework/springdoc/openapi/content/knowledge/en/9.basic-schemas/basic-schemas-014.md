# Avoiding Schema Name Collisions When Multiple Classes Share the Same Simple Name

In a large Spring Boot application, multiple modules may define different DTOs that happen to share the same class name, such as `User`, `Address`, `Status`, or `ErrorResponse`. For instance, the account module has `com.example.account.api.UserResponse`, while the audit module has `com.example.audit.api.UserResponse`. Java distinguishes the two classes by their full package, whereas schema names in OpenAPI are stored in a single shared namespace—`components.schemas`—per document.

If two different classes are turned into a schema with the same name, the documentation can become ambiguous: a schema may be shared unintentionally, a reference may point to the wrong structure, or client generators may produce hard-to-distinguish data types. The most reliable solution is to assign clear, unique schema names meaningful to the API contract. With Springdoc, you can use `@Schema(name = "...")` on DTOs; when a project-wide convention is needed, consider the option to use fully qualified class names.

## 1. Why Packages Do Not Automatically Create Namespaces in `components.schemas`

In Java code, the following two classes are distinct types:

```java
package com.example.account.api;

public record UserResponse(Long id, String displayName) {
}
```

```java
package com.example.audit.api;

public record UserResponse(String actorId, String action) {
}
```

Their fully qualified class names differ:

- `com.example.account.api.UserResponse`
- `com.example.audit.api.UserResponse`

However, when OpenAPI generators place schemas into `components.schemas`, each schema is referenced by a single unique key in the same object. Example:

```yaml
components:
  schemas:
    UserResponse:
      type: object
      properties:
        id:
          type: integer
          format: int64
        displayName:
          type: string
```

`$ref: '#/components/schemas/UserResponse'` identifies only one schema named `UserResponse` in that document. OpenAPI does not automatically add Java namespaces into this `$ref` syntax. Thus, two packages do not create two separate namespaces under `components.schemas`.

Different versions of Springdoc and Swagger Core may handle model names or collisions differently. Do not rely on the resolver's automatic renaming behavior as a contract convention. Inspect the generated documentation and proactively name public schemas that might collide.

## 2. Explicit Schema Naming with `@Schema(name = ...)`

This is the most direct and review-friendly approach. Attach `@Schema` at the class or record level to specify the desired component schema name.

Account module DTO:

```java
package com.example.account.api;

import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
    name = "AccountUserResponse",
    description = "User information in the Account API"
)
public record UserResponse(
    @Schema(description = "User ID", example = "1001")
    Long id,

    @Schema(description = "Display name", example = "Nguyen An")
    String displayName
) {
}
```

Audit module DTO:

```java
package com.example.audit.api;

import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
    name = "AuditActorResponse",
    description = "Actor information for an audit event"
)
public record UserResponse(
    @Schema(description = "Actor identifier", example = "user-1001")
    String actorId,

    @Schema(description = "Action performed", example = "ORDER_APPROVED")
    String action
) {
}
```

Even though the Java class name remains `UserResponse`, the two component schemas receive different names:

```yaml
components:
  schemas:
    AccountUserResponse:
      type: object
      properties:
        id:
          type: integer
          format: int64
        displayName:
          type: string
    AuditActorResponse:
      type: object
      properties:
        actorId:
          type: string
        action:
          type: string
```

When Springdoc processes these DTO types, the `@Schema(name = ...)` annotation supplies an explicit schema name for the documentation. Responses referencing each class point to the corresponding component instead of relying on the simple name `UserResponse`.

### Naming by API context

Schema names should indicate what data they represent and in what context they are used. Examples:

| Java Class Name | Suggested Schema Name | Reason |
|---|---|---|
| `UserResponse` in account | `AccountUserResponse` | Distinguishes from users in other modules |
| `UserResponse` in audit | `AuditActorResponse` | Expresses that this is the actor of an audit event |
| `Address` in billing | `BillingAddress` | Clarifies billing address role |
| `Address` in shipping | `ShippingAddress` | Distinguishes shipping address |
| `ErrorResponse` of inventory | `InventoryErrorResponse` | Avoids colliding with shared error names |
| `Status` of payment | `PaymentStatus` | Avoids generic, collision-prone names |

Prefer stable names grounded in the business domain or API contract. Avoid naming based solely on internal package names if packages may change frequently.

## 3. Referencing the Right Schema from Requests and Responses

When controllers use named DTOs, Springdoc can generate schemas and reference them from operations. Example:

```java
package com.example.account.web;

import com.example.account.api.UserResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/accounts")
class AccountController {

    @GetMapping("/{id}")
    UserResponse getUser(@PathVariable Long id) {
        return accountService.getUser(id);
    }
}
```

And the audit controller:

```java
package com.example.audit.web;

import com.example.audit.api.UserResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/audit/actors")
class AuditActorController {

    @GetMapping("/{actorId}")
    UserResponse getActor(@PathVariable String actorId) {
        return auditService.getActor(actorId);
    }
}
```

The OpenAPI document can represent both responses using independent references:

```yaml
paths:
  /api/accounts/{id}:
    get:
      responses:
        '200':
          description: Account user information
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AccountUserResponse'
  /api/audit/actors/{actorId}:
    get:
      responses:
        '200':
          description: Audit actor information
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/AuditActorResponse'
```

In a real application, Springdoc generates `$ref` links from parameter types, return types, and annotation metadata. You do not need to hand-edit output JSON/YAML just to rename schemas; name them on DTOs or via supported model customization mechanisms.

## 4. Naming Schemas for Nested DTOs and Generic Types

Name collisions do not only happen with DTOs returned directly by controllers. They can also occur inside nested structures or generic types.

Example of a shared response envelope:

```java
public record ApiEnvelope<T>(
    String requestId,
    T data
) {
}
```

APIs may use the envelope with different data types:

```java
ApiEnvelope<com.example.account.api.UserResponse>
ApiEnvelope<com.example.audit.api.UserResponse>
```

Schema names of generic wrappers may be handled differently by resolvers and library versions; the important thing is that the schema for each `data` type continues to reference its own separate component. Do not force the same fixed name onto all generic variants if they have different structures. After changing DTO names or generic representations, inspect `components.schemas` and generated `$ref` links.

For nested DTOs, also assign clear names to reusable types:

```java
@Schema(name = "ShippingAddress")
public record Address(String street, String city, String postalCode) {
}

@Schema(name = "ShipmentResponse")
public record ShipmentResponse(
    String shipmentId,
    Address destination
) {
}
```

If a nested class is purely internal and does not become a separate component, you do not need to force a name on every type. Prioritize schemas referenced by multiple operations or having public contract significance.

## 5. Using `springdoc.use-fqn` for a Project-Wide Convention

Springdoc provides the `springdoc.use-fqn` property to use a class's fully qualified name when naming schemas. It can be configured as:

```yaml
springdoc:
  use-fqn: true
```

Or:

```properties
springdoc.use-fqn=true
```

When enabled, schema names are constructed from the class's full name instead of relying only on the simple name, reducing the risk of classes in different packages colliding. For example, `com.example.account.api.UserResponse` and `com.example.audit.api.UserResponse` can be represented using names tied to their full packages in the documentation.

This is an application-wide setting, so it can affect many schemas in the document. Before enabling it in an already-published API, check:

- Actual component names generated by your Springdoc version.
- `$ref` syntax and readability in validators, Swagger UI, and client generators.
- Generated class names in SDKs and impact on existing client source code.
- Whether grouped documents and saved OpenAPI files need synchronized updates.

Fully qualified names are longer and expose internal package structure. Some code generators may transform dots or special characters using their own rules. Therefore, `springdoc.use-fqn` fits when a team wants a broad automatic naming policy and has verified downstream tools. For public contracts requiring stable names, `@Schema(name = ...)` is usually easier to control.

This option should also be checked against your exact Springdoc version. If the property is not supported by the version in use, the configuration may not produce the expected effect; verify the actual documentation and results.

## 6. Choosing Between Explicit Names and Fully Qualified Names

| Criterion | `@Schema(name = ...)` | `springdoc.use-fqn: true` |
|---|---|---|
| Scope | Specific individual schemas | Application-wide convention |
| Name in contract | Short, domain-meaningful | Coupled to Java package/class |
| Name control | Intentional per DTO | Automatic from full name |
| Impact of package refactoring | Schema name can remain unchanged | Schema name may change with package |
| Best suited for | Public APIs needing stable schema names | Large projects wanting broad automatic collision avoidance |

You can combine both approaches as needed, but verify how your Springdoc version prioritizes explicit names versus the FQN policy. Do not assume all versions resolve the two settings in the same order. If the contract must stay stable, set explicit names for public schemas and verify the output when the global option is enabled.

## 7. Do Not Use One Schema Name for Two Different Structures

`components.schemas` stores schemas referenced within the same OpenAPI document. One component key should represent only one consistent structure and meaning.

For example, do not name two different classes `UserResponse`:

```java
@Schema(name = "UserResponse")
public record AccountUserResponse(Long id, String displayName) {
}

@Schema(name = "UserResponse")
public record AuditActorResponse(String actorId, String action) {
}
```

Two classes with different meanings and properties are requesting the same component name. Results may depend on resolver order or how the library handles duplicate names; the documentation risks no longer reflecting the right type for an operation. Change them to two distinct names:

```java
@Schema(name = "AccountUserResponse")
public record AccountUserResponse(Long id, String displayName) {
}

@Schema(name = "AuditActorResponse")
public record AuditActorResponse(String actorId, String action) {
}
```

If two classes truly share the same structure and meaning, consider sharing one DTO in an appropriate API module to avoid duplicate definitions. If they share the same structure yet differ in semantics or may evolve independently, keep separate types and give them separate schema names. Do not merge two types merely because they currently share the same list of fields.

## 8. Schema Names Are Part of the Contract for Tooling

Some client generators use names in `components.schemas` to name classes/models in SDKs. For instance, schema `AccountUserResponse` may generate class `AccountUserResponse` in Java or the corresponding name in the target language.

Therefore, renaming a schema may not change the HTTP JSON payload, yet still impacts regenerated client source code. If clients reference the old model, renaming can cause source-level breaking changes or force clients to update imports/type names.

Once an API is published:

1. Choose a component naming convention before publishing documentation.
2. Keep schema names stable across Java package refactorings.
3. If renaming is unavoidable, inspect the OpenAPI diff and regenerated SDK source code.
4. Record the impact in release notes and coordinate with client teams.
5. Do not treat renaming a schema as harmless simply because runtime JSON does not change.

Java class names are implementation details that can be refactored; OpenAPI component names may have become public names that tools and integration teams depend on.

## 9. Multiple OpenAPI Groups Have Separate Schema Namespaces

Springdoc can produce multiple documents via `GroupedOpenApi`, such as groups for account and audit. Each OpenAPI document is a separate specification, so each document has its own `components.schemas` object.

Example:

```java
@Bean
GroupedOpenApi accountApi() {
    return GroupedOpenApi.builder()
        .group("account")
        .pathsToMatch("/api/accounts/**")
        .build();
}

@Bean
GroupedOpenApi auditApi() {
    return GroupedOpenApi.builder()
        .group("audit")
        .pathsToMatch("/api/audit/**")
        .build();
}
```

The two document URLs typically look like `/v3/api-docs/account` and `/v3/api-docs/audit`. A schema named `UserResponse` in the account document does not directly collide with a schema of the same name in the audit document because they belong to two different documents.

However, if a single group includes both controllers and both DTOs with the same simple name, collisions can still happen within that document. Splitting groups only scopes namespaces when types are placed in independent documents; it does not replace a schema naming convention.

## 10. Handling Schemas from External Libraries or Classes Where Annotations Cannot Be Edited

It is not always possible to attach `@Schema(name = ...)` to a class. A DTO may come from a third-party library, a shared module you cannot modify, or generated classes.

Several options:

- Create a dedicated API DTO/wrapper in the application's module and map from the library type to that DTO.
- Use configuration or model converter mechanisms supported by your Swagger Core/Springdoc version to control schema resolution.
- Use `OpenApiCustomizer` to adjust the model after generation when controlled changes to metadata or references are needed.
- Consider `springdoc.use-fqn` if a fully qualified naming policy fits the entire application.

A wrapper DTO is usually easiest to maintain when a library type should not become part of the public contract. A customizer can rename components, but must update all `$ref` links pointing to the old name; renaming only the key without updating references renders the document invalid. For deep changes to model resolution, prefer official mechanisms of your exact library version and test with a validator.

## 11. Inspecting `components.schemas` and `$ref` After Generation

After naming schemas, open the OpenAPI endpoint—typically `/v3/api-docs`—and inspect the `components.schemas` object. You can use `curl` with `jq`:

```bash
curl -s http://localhost:8080/v3/api-docs | jq '.components.schemas | keys'
```

Inspect specific schemas:

```bash
curl -s http://localhost:8080/v3/api-docs | jq '.components.schemas.AccountUserResponse'
curl -s http://localhost:8080/v3/api-docs | jq '.components.schemas.AuditActorResponse'
```

Check that operations reference the right schema:

```bash
curl -s http://localhost:8080/v3/api-docs | jq '.paths["/api/accounts/{id}"].get.responses["200"].content["application/json"].schema'
```

Expected output has the corresponding `$ref`:

```json
{
  "$ref": "#/components/schemas/AccountUserResponse"
}
```

For grouped documents, query the exact URL of each group. Checking only the default document can miss collisions that appear only when a group spans multiple packages.

## 12. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Two DTOs in different packages have the same schema name | Resolver uses simple name or duplicate metadata | Set distinct `@Schema(name = ...)` on each DTO |
| Controller response points to wrong schema | Schema name collision or resolver chose unexpected model | Check Java types, `components.schemas`, and `$ref` |
| Enabling `use-fqn` changes SDK model names | Component name now depends on full name/package | Review OpenAPI diff and test client generator before release |
| Renaming a package changes schema names | Contract depends on FQN | Set explicit names to decouple public names from internal packages |
| Customizer renames schema but document reports unresolved reference | Some `$ref` links still use the old name | Update component key and all references together; run validator |
| One group works while another group has wrong schemas | Latter group includes additional same-named types | Inspect each group and enforce unique names per document |
| External library schema is hard to rename | Cannot place annotations on source class | Use a wrapper DTO or appropriate model converter |

## 13. Safe Schema Naming Checklist

- [ ] Identified DTOs sharing the same simple name across different packages/modules.
- [ ] Every public schema has a unique name in the document's `components.schemas`.
- [ ] Used `@Schema(name = ...)` for collision-prone types.
- [ ] Schema names reflect API semantics rather than relying purely on Java packages.
- [ ] Never assigned the same schema name to two different structures or meanings.
- [ ] Evaluated `springdoc.use-fqn` if applying a global convention.
- [ ] Checked generic wrappers and nested DTOs.
- [ ] Checked grouped documents containing multiple identically named types.
- [ ] All `$ref` links point to existing schemas with accurate structures.
- [ ] Considered the impact of schema renaming on client generators/SDKs.
- [ ] Ran an OpenAPI validator or verified the document with compatible tools.

Schema names in OpenAPI are contract reference keys, not Java namespaces. When multiple classes share the same simple name, assign component names by API semantics using `@Schema(name = ...)`, or apply an FQN convention after checking project-wide impact. Ensuring unique, stable names and accurate `$ref` targets keeps Springdoc documentation clear, prevents confusion, and keeps client SDKs consistent.
