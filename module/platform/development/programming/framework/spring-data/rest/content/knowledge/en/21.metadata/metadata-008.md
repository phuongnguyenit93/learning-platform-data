# Differences Between ALPS, JSON Schema, and OpenAPI Contract Documentation in Spring Data REST

## Objectives

After this lesson, you will be able to distinguish the three common metadata formats used to describe a REST API: ALPS, JSON Schema, and OpenAPI. You will know what questions each answers, where Spring Data REST exposes ALPS and JSON Schema, which tools add OpenAPI support, and how to combine them to support API discovery, data validation, and endpoint integration.

## 1. Why Are Multiple Types of Metadata Needed?

An API consists of more than URLs and JSON responses. Clients also need to know:

- What properties does a resource have and what does each property mean?
- What operations does the API support on the resource?
- What structure, data types, and constraints apply to request and response bodies?
- Are parameters located in the path, query, or headers?
- Which status codes and media types can an endpoint return?
- What authentication mechanism is required and which hypermedia links exist for further navigation?

No single metadata format answers all of these questions well. ALPS, JSON Schema, and OpenAPI have different scopes:

- **ALPS** describes application-level semantics and hypermedia affordances/transitions.
- **JSON Schema** describes JSON data structure and constraints that can be validated against JSON instances.
- **OpenAPI** describes the HTTP API contract: paths, methods, parameters, request bodies, responses, media types, and security.

In Spring Data REST, ALPS and JSON Schema are supported out of the box. OpenAPI is typically added through an integration library such as `springdoc-openapi`. Thus, all three formats can coexist and serve different client audiences.

## 2. ALPS: Describing Semantics and Hypermedia Operations

ALPS stands for Application-Level Profile Semantics. It is a format for describing application concepts and semantics in a way that is not tightly coupled to a single media type. An ALPS profile helps clients understand property meanings and the transitions supported by a resource.

Spring Data REST generates an ALPS document for every exported repository. The metadata typically includes:

- Representation properties, such as `firstName`, `lastName`, `email`.
- Supported REST operations, such as reading a collection, reading an item, creating, updating, or deleting.
- Hypermedia control types and associated resource types.
- Exported projections, if the repository defines projections.
- Additional descriptions for resources or properties when the application supplies corresponding metadata.

### Discovering ALPS in Spring Data REST

The API root contains a `profile` link. Following that link takes the client to `/profile` to view the list of repository profiles. Abridged example:

```json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/profile"
    },
    "people": {
      "href": "http://localhost:8080/profile/people"
    },
    "addresses": {
      "href": "http://localhost:8080/profile/addresses"
    }
  }
}
```

To fetch ALPS for the `people` repository, the client follows the `/profile/people` link:

```http
GET /profile/people
Accept: application/alps+json
```

Spring Data REST can also serve ALPS by default when a client follows a profile link without specifying a media type. Use the exact link returned by the API rather than constructing paths manually, especially when the application uses a custom base path or custom resource path configuration.

An ALPS document can contain descriptors such as:

```json
{
  "version": "1.0",
  "descriptors": [
    {
      "id": "person-representation",
      "descriptors": [
        { "name": "firstName", "type": "SEMANTIC" },
        { "name": "lastName", "type": "SEMANTIC" },
        { "name": "address", "type": "SAFE" }
      ]
    },
    {
      "id": "create-people",
      "name": "people",
      "type": "UNSAFE",
      "rt": "#person-representation"
    },
    {
      "id": "get-people",
      "name": "people",
      "type": "SAFE",
      "rt": "#person-representation"
    }
  ]
}
```

This is an abridged example illustrating descriptor structure. Actual metadata depends on the domain model, repository methods, and Spring Data REST version.

### Descriptor Types in ALPS

| Type | Meaning | Typical Example |
| --- | --- | --- |
| `SEMANTIC` | Data-bearing property | `firstName`, `email` |
| `SAFE` | Transition that does not alter system state | `GET` or `HEAD` |
| `IDEMPOTENT` | Transition that may alter state, where repeating the same request yields the same final effect | `PUT` or `DELETE` |
| `UNSAFE` | Transition that may alter state and is not guaranteed idempotent | `POST` |

ALPS helps clients understand operations and data meanings at the semantic level. For example, an `UNSAFE` descriptor can indicate an operation creating a resource on a collection; `rt` links the operation to its corresponding representation type.

### ALPS and Projections

If a repository has registered projections, ALPS can describe the `projection` parameter and supported projection names. Clients can discover alternative representation views without hard-coding projection lists from external documentation.

### Adding Descriptions to ALPS

You can add descriptions for resources and properties using message keys following the `rest.description.*` convention in `rest-messages.properties`. Example:

```properties
rest.description.person=A collection of people
rest.description.person.firstName=Person's first name
rest.description.person.lastName=Person's last name
rest.description.person.address=Person's address
```

These values are placed into the `doc` section of descriptors. Spring MVC supports locales, so language-specific resource bundles can be provided to describe the profile appropriately for users.

ALPS is not a byte-by-byte specification of every HTTP request/response. It focuses on semantics and hypermedia controls; detailed data types, structural constraints, response codes, and security schemes should be described using other formats when needed.

## 3. JSON Schema: Describing JSON Structure and Constraints

JSON Schema is a vocabulary for describing the shape of a JSON document. It can define:

- Data types: `object`, `array`, `string`, `number`, `integer`, `boolean`, `null`.
- Properties and their corresponding data types.
- Required properties via `required`.
- Constraints such as `minLength`, `maxLength`, `minimum`, `maximum`, `pattern`.
- Nested structures, array elements, and schema alternatives.
- Annotations such as `title`, `description`, `format`, and `readOnly`.

JSON Schema is useful for client generators, form generators, validators, and automated tests because clients can check whether a JSON instance conforms to the schema.

### Retrieving JSON Schema from Spring Data REST

Spring Data REST uses the same profile URI while selecting the representation via content negotiation. Example:

```http
GET /profile/people
Accept: application/schema+json
```

Or using `curl`:

```bash
curl -i http://localhost:8080/profile/people \
  -H "Accept: application/schema+json"
```

A repository's profile link may still return ALPS by default; the `Accept: application/schema+json` header requests JSON Schema. Follow the `profile` link provided by the API root or collection resource.

Example abridged JSON Schema:

```json
{
  "$schema": "https://json-schema.org/draft-04/schema#",
  "title": "Person",
  "type": "object",
  "properties": {
    "firstName": {
      "type": "string",
      "readOnly": false
    },
    "lastName": {
      "type": "string",
      "readOnly": false
    },
    "address": {
      "type": "string",
      "format": "uri"
    },
    "created": {
      "type": "string",
      "format": "date-time"
    }
  }
}
```

The actual schema emitted by Spring Data REST is determined by the version and application mappings. Current documentation may show a specific draft version; clients should read the `$schema` field instead of assuming all servers use the same draft.

### How Does JSON Schema Help Clients?

Suppose a client needs to send a `Person` object. The schema can indicate that `firstName` is a string, `created` is a `date-time`, and `address` is a URI. Clients can use that information to:

- Build forms with appropriate controls.
- Validate data before sending.
- Generate programming-language types or models.
- Create tests verifying that JSON requests/responses have the expected shape.
- Display basic property metadata.

### Limitations of JSON Schema in Spring Data REST

JSON Schema describes data structure; it does not replace the full HTTP contract:

- It does not fully describe the list of paths and HTTP methods like OpenAPI does.
- It does not automatically describe all status codes, response headers, security schemes, or OAuth flows.
- A single domain schema is not necessarily separate schemas for `POST`, `PUT`, `PATCH`, and `GET` operations.
- Business rules depending on multiple fields, the database, or the current user cannot be fully derived from property types alone.
- Having a schema does not mean the server automatically validates requests against every constraint in the schema.

Distinguish schema metadata from runtime validation enforcement. The server still needs Bean Validation, domain rules, authorization, and database constraints. Client validation only improves user experience; the server must independently verify incoming data.

## 4. OpenAPI: HTTP API Contract Documentation

The OpenAPI Specification (OAS) describes an HTTP API in a machine-readable structure. An OpenAPI document typically includes:

- `openapi`: specification version.
- `info`: API title, description, version, and contact/license information.
- `servers`: base URLs for environments.
- `paths`: endpoints and HTTP operations.
- `parameters`: path, query, header, or cookie parameters.
- `requestBody`: media types and schemas of the input body.
- `responses`: status codes, headers, and response bodies.
- `components`: reusable schemas, responses, parameters, and security schemes.
- `security`: authentication and authorization requirements at the API or operation level.

Abridged OpenAPI example for the `/people` collection:

```yaml
openapi: 3.1.0
info:
  title: People API
  version: 1.0.0
servers:
  - url: https://api.example.com
paths:
  /people:
    get:
      summary: List people
      responses:
        "200":
          description: People collection
          content:
            application/hal+json:
              schema:
                type: object
    post:
      summary: Create a person
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/PersonInput"
      responses:
        "201":
          description: Person created
          headers:
            Location:
              description: URI of the created resource
              schema:
                type: string
                format: uri
  /people/{id}:
    get:
      summary: Get one person
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Person resource
        "404":
          description: Person not found
components:
  schemas:
    PersonInput:
      type: object
      required:
        - firstName
      properties:
        firstName:
          type: string
        lastName:
          type: string
```

This is an illustrative example, not an OpenAPI document emitted verbatim by Spring Data REST. A real API needs to accurately describe HAL representations, response codes, request media types, security, and supported association links.

OpenAPI is especially useful for:

- Swagger UI or Scalar so developers can try out the API.
- Generating client SDKs and server stubs.
- Contract testing between producers and consumers.
- Producing integration documentation with clear paths, methods, requests, responses, and security.
- Diffing contract changes across API versions.

## 5. Does Spring Data REST Provide OpenAPI Out of the Box?

Spring Data REST includes ALPS and JSON Schema metadata in its core. OpenAPI is a separate specification and is typically integrated through external tooling, such as `springdoc-openapi`.

With Spring Boot, `springdoc` provides a module supporting Spring Data REST, including annotations like `@RepositoryRestResource` and related integrations. The library can inspect the application and generate OpenAPI JSON/YAML; when using a UI starter, it can also serve Swagger UI.

Common `springdoc` endpoints:

- `/v3/api-docs`: OpenAPI document in JSON format.
- `/v3/api-docs.yaml`: OpenAPI document in YAML format.
- `/swagger-ui.html`: Swagger UI interface (path is configurable).

Example Maven dependency for a Spring Boot 3 application using Spring MVC with Swagger UI:

```xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version><!-- Choose a version compatible with Spring Boot --></version>
</dependency>
```

Use `springdoc` 2.x for Spring Boot 3; the `springdoc` 3.x branch targets Spring Boot 4. Check the compatibility matrix for your exact project version before adding the dependency. If you only need the OpenAPI document without the UI, choose the corresponding API starter.

After running the application, you can retrieve the document:

```bash
curl -i http://localhost:8080/v3/api-docs
```

And open Swagger UI at the configured path, typically:

```text
http://localhost:8080/swagger-ui.html
```

### Reviewing the Auto-Generated Spring Data REST Output

Do not assume every dynamic detail of repository endpoints is described perfectly in OpenAPI merely because the document generates successfully. Verify:

- Whether repository collection and item paths appear.
- Whether query method resources and query parameters are accurate.
- Whether `POST`/`PUT`/`PATCH`/`DELETE` operations match actual exposure settings.
- Whether request/response media types include HAL or the media types the application uses.
- Whether response schemas reflect `_links`, `_embedded`, pagination, and projections.
- Whether association resources, URI-list payloads, and conditional headers are documented.
- Whether security schemes and error responses match the Spring Security configuration.

For custom controllers, use OpenAPI annotations such as `@Operation`, `@ApiResponse`, `@Parameter`, `@RequestBody`, and `@Schema` to enrich descriptions. For auto-generated parts that are missing or inaccurate, add appropriate customizers or `springdoc` configuration. OpenAPI must be verified as an API artifact rather than blindly trusting auto-scan output.

## 6. Direct Comparison of ALPS, JSON Schema, and OpenAPI

| Criterion | ALPS | JSON Schema | OpenAPI |
| --- | --- | --- | --- |
| Primary question | What does the resource mean and how can it transition? | What structure and constraints does the JSON have? | How do I invoke the HTTP endpoint? |
| Focus | Semantics, descriptors, hypermedia controls | Objects, properties, types, `required`, constraints | Paths, methods, parameters, bodies, responses, security |
| Unit of description | Profile, semantic descriptor, transition | JSON instance/schema | API server, path, operation, component |
| Used for | Semantic and affordance discovery | Validating/generating models or forms | Documentation, SDKs, contract tests, API tooling |
| Spring Data REST core | Yes | Yes | No; integrated via tools like `springdoc` |
| Common content type/endpoint | `application/alps+json`, `/profile/{repository}` | `application/schema+json`, same profile URI | JSON/YAML at the endpoint provided by the OpenAPI tool |
| Main limitation | Not a detailed spec of every HTTP request/response | Does not describe the full protocol and operations | Does not replace runtime hypermedia discovery; document must stay in sync with the API |

You can remember them by three questions:

- ALPS answers: **“What do these elements and operations mean?”**
- JSON Schema answers: **“What shape and constraints does the JSON data have?”**
- OpenAPI answers: **“Which endpoint do I call, with what method and data, and what responses can I receive?”**

## 7. An Example Using All Three Metadata Types

Suppose Spring Data REST exports a `people` repository with the `Person` entity:

```java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;

    // Constructor, getters and setters
}
```

Repository:

```java
@RepositoryRestResource(path = "people")
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
```

A client can discover the API in sequence:

**Step 1 — fetch the API root**

```http
GET /
Accept: application/hal+json
```

Read the `people` link to locate the collection and the `profile` link to locate metadata.

**Step 2 — read the ALPS profile**

```http
GET /profile/people
Accept: application/alps+json
```

The client sees semantic descriptors such as `firstName` and `lastName`, and transitions such as collection `GET`, collection `POST`, and item `GET`.

**Step 3 — read the JSON Schema**

```http
GET /profile/people
Accept: application/schema+json
```

The client learns that `firstName` and `lastName` are strings, other properties have their corresponding types, and can use the schema to power forms or validate JSON.

**Step 4 — read OpenAPI**

```http
GET /v3/api-docs
Accept: application/json
```

The client or developer tools read paths, HTTP methods, parameters, request bodies, responses, and security schemes generated/annotated by `springdoc`.

The three documents do not compete with one another. ALPS supports hypermedia semantics; JSON Schema describes data; OpenAPI serves as the HTTP contract for integration and tooling.

## 8. Combining Metadata Without Creating Three Conflicting Sources of Truth

If an application publishes ALPS, JSON Schema, and OpenAPI, keep them consistent with the runtime API.

Practical principles:

1. Treat the domain model, repository exposure, security configuration, and custom controllers as the source of runtime behavior.
2. Use ALPS to describe the semantics and affordances advertised by Spring Data REST.
3. Use JSON Schema to describe JSON structure; check the actual draft and schema limitations emitted by the server.
4. Use OpenAPI to describe the full HTTP protocol, including HAL media types, status codes, headers, auth, and error responses.
5. Do not hand-write a separate request schema and let it diverge from actual server validation.
6. If using `springdoc` auto-generation, review the document after every change to repository paths, query methods, projections, or security.
7. Use contract tests to compare OpenAPI against live endpoints and validate important JSON payloads.
8. Include profile links and the OpenAPI URL in developer portal documentation so clients can find them easily.

Specifically, OpenAPI can reference JSON Schemas under `components/schemas` or declare inline schemas for requests/responses. However, schemas used in OpenAPI must be compatible with the chosen OpenAPI version; do not copy an older JSON Schema draft verbatim into an OpenAPI document without checking dialect rules and tool support.

## 9. Which Format Should You Choose for Your Needs?

**Choose ALPS when:**

- The API uses hypermedia and you want clients to discover resource semantics.
- You need to describe properties, transitions, and projections advertised by Spring Data REST.
- You want clients to rely less on hard-coded URLs/methods and follow server-provided links.

**Choose JSON Schema when:**

- You need to describe JSON structure for validation or form/model generation.
- You need type constraints, required fields, formats, lengths, or numeric ranges.
- You need to validate payloads against schemas or exchange schemas across systems.

**Choose OpenAPI when:**

- You need endpoint documentation for frontend/mobile/partner teams.
- You need to document HTTP methods, path/query/header parameters, bodies, responses, and auth.
- You need Swagger UI, SDK generation, or contract testing.
- You have custom REST controllers and want to publish a complete integration contract.

In a large Spring Data REST application, publishing both hypermedia metadata and OpenAPI is often beneficial. Hypermedia clients can use ALPS/profile links; integration tools can use OpenAPI; validators or form generators can use JSON Schema.

## 10. Common Mistakes

**Cannot find the profile link**

Check the API root and whether the repository is exported. Use the `profile` link from the root or the collection resource's `profile` link; do not assume paths when the application has a base path.

**Profile returns ALPS when JSON Schema was expected**

Send `Accept: application/schema+json` to the profile URI. `/profile` only lists profiles; a specific repository's URI is `/profile/{repository}`.

**JSON Schema has properties but lacks expected business rules**

Schemas are generated from domain metadata and have limitations. Add server-side validation, appropriate constraints, custom schemas, or OpenAPI docs clearly stating request semantics. Never treat the schema as the server's validation engine.

**OpenAPI document is missing repository endpoints**

Check the `springdoc` version and Spring Data REST support module; verify repository export settings; check filters/hidden configurations; and inspect customizers. You may need configuration or manual descriptions for operations not fully inferred.

**Swagger UI displays JSON but does not show HAL links properly**

Check response media types and OpenAPI schemas. HAL representations include `_links`, `_embedded`, and URI templates; a generic object schema may be insufficient to describe detailed hypermedia controls.

**Stale metadata after API changes**

Regenerate the OpenAPI document, check build-time generation/caching if any, and run contract tests. ALPS/JSON Schema are typically generated from runtime mappings, so verify against the running application version.

## Summary

- ALPS describes semantics, properties, and hypermedia transitions; Spring Data REST provides a profile for each exported repository.
- JSON Schema describes JSON shape and constraints; Spring Data REST serves it at the profile URI when clients send `Accept: application/schema+json`.
- OpenAPI describes the HTTP contract including paths, methods, parameters, requests/responses, media types, and security.
- ALPS and JSON Schema are supported in Spring Data REST core; OpenAPI is typically added with `springdoc` or equivalent tooling.
- `springdoc` supports Spring Data REST, yet generated documents still need inspection to confirm they accurately reflect HAL, projections, associations, security, and error responses.
- The three formats complement one another: semantics, data shape, and HTTP contract.

## References

- [Spring Data REST — Metadata: ALPS and JSON Schema](https://docs.spring.io/spring-data/rest/reference/metadata.html)
- [Spring Data REST — Project overview and features](https://spring.io/projects/spring-data-rest/)
- [ALPS specification](https://alps.io/spec/drafts/draft-00.html)
- [JSON Schema — Specification and documentation](https://json-schema.org/)
- [OpenAPI — Specification explained](https://learn.openapis.org/specification/)
- [OpenAPI — Paths and operations](https://learn.openapis.org/specification/paths.html)
- [OpenAPI — Parameters and payload](https://learn.openapis.org/specification/parameters.html)
- [springdoc-openapi — Spring Data REST support](https://springdoc.org/v2/#spring-data-rest-support)
