# Resource JSON Schema and Media Type Negotiation

## Objectives

Spring Data REST provides metadata so clients can discover the structure and semantics of repository resources. Two important metadata formats are:

- **ALPS (Application-Level Profile Semantics):** describes the properties and REST transitions supported by a resource.
- **JSON Schema:** describes the JSON data structure of a domain resource, including property names, data types, and metadata such as `readOnly` or `format`.

Clients access metadata through the `profile` link. The same profile URI can return ALPS or JSON Schema depending on the HTTP `Accept` header.

In addition, Spring Data REST uses content negotiation to select representations for requests and responses. Clients must distinguish:

- `Accept`: the media types the client wants to receive in the response.
- `Content-Type`: the media type of the request body sent by the client.
- `Content-Type` in the response: the representation the server actually returns.

Understanding these three parts properly helps clients retrieve JSON Schema, read HAL, send JSON on `POST`/`PUT`/`PATCH`, and send association URIs using the right media types.

## 1. Metadata and Profile Links in Spring Data REST

Spring Data REST automatically exports repositories as REST resources. The root resource returns links to collections and a `profile` link for metadata discovery.

Example root response:

    GET /

    {
      "_links": {
        "customers": {
          "href": "http://localhost:8080/customers"
        },
        "orders": {
          "href": "http://localhost:8080/orders"
        },
        "profile": {
          "href": "http://localhost:8080/profile"
        }
      }
    }

The `customers` and `orders` relations and specific URLs depend on the application's repositories, path configuration, and relations. Clients should follow links provided by the server instead of constructing URLs manually.

Next, `GET` the profile index:

    GET /profile

The response may list each repository's profile URI:

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/profile"
        },
        "customers": {
          "href": "http://localhost:8080/profile/customers"
        },
        "orders": {
          "href": "http://localhost:8080/profile/orders"
        }
      }
    }

Each profile URI describes its corresponding repository. For example, `/profile/customers` provides metadata for the `Customer` resource.

Collection responses can also contain a `profile` link in `_links`. Thus, clients can start either from the root or from the collection they are already using.

## 2. ALPS Describes Semantics and REST Operations

ALPS is a metadata format that describes application-level semantics. Spring Data REST provides an ALPS document for every exported repository.

ALPS can describe:

- Representation properties, such as `id`, `firstName`, `lastName`.
- Operations on collections and items.
- The resource type returned by an operation.
- Descriptors related to projections.
- Application-supplied descriptions for resources or properties.

Requesting ALPS:

    curl -i       -H "Accept: application/alps+json"       http://localhost:8080/profile/customers

The response has the media type:

    Content-Type: application/alps+json

Abridged ALPS example:

    {
      "version": "1.0",
      "descriptors": [
        {
          "id": "customer-representation",
          "descriptors": [
            { "name": "firstName", "type": "SEMANTIC" },
            { "name": "lastName", "type": "SEMANTIC" },
            { "name": "address", "type": "SAFE" }
          ]
        },
        {
          "id": "get-customers",
          "name": "customers",
          "type": "SAFE",
          "rt": "#customer-representation"
        }
      ]
    }

Common types in ALPS:

| Type | Meaning |
|---|---|
| SEMANTIC | Meaningful property or data in a representation |
| SAFE | Safe transition that does not alter state, typically GET/HEAD |
| IDEMPOTENT | Transition that may alter state but is idempotent, such as PUT/DELETE |
| UNSAFE | Transition that may alter state and is not idempotent, such as POST |

ALPS helps clients understand which operations a resource provides and their related descriptors. It is not JSON Schema and does not replace API documentation regarding authorization, business rules, or runtime errors.

### 2.1. Adding Custom Descriptions to ALPS

You can add descriptions using a `rest-messages.properties` file on the classpath.

Example:

    rest.description.customer=A collection of customers
    rest.description.customer.id=Customer identifier
    rest.description.customer.firstName=Customer first name
    rest.description.customer.lastName=Customer family name

The `rest.description.*` keys attach descriptions to the corresponding resource or property. Spring Data REST includes this information in ALPS under a `doc` descriptor.

Multiple locale-specific properties files can be used via Spring's message resolution mechanism. This is useful when the API needs metadata descriptions in multiple languages.

Key names must follow Spring Data REST conventions and match actual domain/property names. If descriptions do not appear, check the file location, keys, and the profile URI being accessed.

## 3. JSON Schema Describes Resource Structure

JSON Schema is structured, machine-readable metadata that serves as documentation for clients. Spring Data REST exposes a repository's JSON Schema through the profile URI.

To fetch the schema for `Customer`:

    curl -i       -H "Accept: application/schema+json"       http://localhost:8080/profile/customers

The response has the media type:

    Content-Type: application/schema+json

Abridged JSON Schema example:

    {
      "title": "com.example.Customer",
      "properties": {
        "firstName": {
          "readOnly": false,
          "type": "string"
        },
        "lastName": {
          "readOnly": false,
          "type": "string"
        },
        "createdAt": {
          "readOnly": false,
          "type": "string",
          "format": "date-time"
        },
        "address": {
          "readOnly": false,
          "type": "string",
          "format": "uri"
        }
      },
      "descriptors": {},
      "type": "object",
      "$schema": "https://json-schema.org/draft-04/schema#"
    }

This is an illustrative example. Actual properties, types, formats, titles, and dialect depend on the domain model, mappings, and Spring Data REST version.

Common parts:

- `title`: name of the exported type.
- `properties`: list of properties and their metadata.
- `type`: structural type of the schema, usually `object`.
- `format`: format hint for string types, such as `date-time` or `uri`.
- `readOnly`: indicates whether the property is considered read-only in the schema.
- `$schema`: identifies the JSON Schema dialect used by the document.

### 3.1. Data Types and Associations

JSON Schema can describe scalar properties such as string, integer, or boolean. Associations to other resources can be represented as URI strings, typically accompanied by `format: uri`.

Example:

    {
      "address": {
        "type": "string",
        "format": "uri"
      }
    }

This fits hypermedia principles: clients can link associations using resource URIs provided by the server.

Do not assume every association always has the same schema. The representation depends on the association, repository, projections, serializers, and application configuration.

### 3.2. Schema Is Not Database DDL

JSON Schema describes the JSON representation exposed by the API. It is not a full replica of the database schema.

For example, JSON Schema may describe a property as a string without fully capturing:

- Foreign keys and how the database handles `ON DELETE`.
- Indexes or execution plans.
- Complex unique constraints based on collation.
- Tenant rules or permissions of the current principal.
- Business rules requiring service calls or checking other states.
- Transaction boundaries and concurrency behavior.

Therefore, do not use JSON Schema as sole proof that the database enforces a constraint or that a request will be accepted.

### 3.3. Schema Does Not Replace Server-Side Validation

Clients can use JSON Schema to:

- Generate input forms.
- Validate data types and structure before sending.
- Generate mock payloads.
- Generate parts of client models or documentation.
- Write contract tests for representations.

The server must still validate requests and enforce authorization and database constraints. Clients can be modified or send requests directly without running UI-side validators.

## 4. Same Profile URI, Selecting ALPS or JSON Schema via Accept

The profile URI is the metadata entry point. The media type is selected via the `Accept` header.

Example fetching ALPS:

    curl -i       -H "Accept: application/alps+json"       http://localhost:8080/profile/customers

Example fetching JSON Schema:

    curl -i       -H "Accept: application/schema+json"       http://localhost:8080/profile/customers

Both requests target the same URI while requesting two different representations. Check the `Content-Type` response header to confirm which metadata format the server returned.

Summary overview:

| Request Accept | Expected Response Content-Type | Content |
|---|---|---|
| application/alps+json | application/alps+json | Descriptors and REST operations |
| application/schema+json | application/schema+json | JSON property structure |
| application/hal+json | application/hal+json | HAL hypermedia resource |
| application/json | Depends on configuration | JSON representation, defaults to HAL in modern Spring Data REST |

If `Accept` is omitted, the server uses the configured default media type. Therefore, clients should send an explicit header when a specific metadata format is required.

## 5. Content Negotiation with Accept

`Accept` is a request header describing the media types a client can receive. The server chooses a representation supported by the endpoint and message converters, then writes the actual media type into the response `Content-Type`.

Example reading a collection as HAL:

    curl -i       -H "Accept: application/hal+json"       http://localhost:8080/customers

Illustrative response:

    HTTP/1.1 200 OK
    Content-Type: application/hal+json

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/customers"
        },
        "profile": {
          "href": "http://localhost:8080/profile/customers"
        }
      },
      "_embedded": {
        "customers": [
          {
            "firstName": "An",
            "lastName": "Nguyen"
          }
        ]
      }
    }

HAL provides hypermedia controls in `_links` and collection data in `_embedded`. Clients can follow links to discover items, associations, or profiles.

### 5.1. application/json and Default HAL

In modern Spring Data REST, when a client requests `application/json`, HAL is commonly used as the default representation. This allows the API to continue providing hypermedia links even when clients send a generic JSON `Accept` header.

You can control this behavior via `RepositoryRestConfiguration.useHalAsDefaultJsonMediaType(...)`.

Example keeping HAL as the representation for `application/json` requests:

    @Component
    public class RestConfiguration implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config,
                CorsRegistry cors) {
            config.useHalAsDefaultJsonMediaType(true);
        }
    }

If configured as `false`, Spring Data REST uses the legacy Spring Data representation when clients request `application/json`, according to the corresponding version's behavior.

Do not assume `application/json` always means plain JSON without hypermedia. Check `Content-Type`, the response body, and the actual configuration.

### 5.2. Accept with Multiple Choices and Quality Values

Clients can send multiple media types and specify quality values:

    Accept: application/hal+json;q=1.0, application/json;q=0.8

The `q` value expresses the client's relative preference. The server selects a suitable representation among the media types supported by the endpoint.

Even when sending multiple choices, the client must still check the response `Content-Type`. Do not infer the response solely from the request headers sent.

## 6. Content-Type for Request Bodies

`Content-Type` describes the format of the body the client is sending. Spring uses this header to select a converter capable of deserializing the body into an object or association input.

Example creating a Customer with JSON:

    curl -i -X POST       -H "Content-Type: application/json"       -H "Accept: application/hal+json"       -d '{"firstName":"An","lastName":"Nguyen"}'       http://localhost:8080/customers

Or sending HAL JSON:

    curl -i -X POST       -H "Content-Type: application/hal+json"       -H "Accept: application/hal+json"       -d '{"firstName":"An","lastName":"Nguyen"}'       http://localhost:8080/customers

`PUT` and `PATCH` also require a `Content-Type` appropriate to the body and operation.

Media types supported by repository resources according to current Spring Data REST documentation:

| Operation | Commonly supported request/response media types |
|---|---|
| GET collection | application/hal+json, application/json |
| POST collection | application/hal+json, application/json |
| GET item | application/hal+json, application/json |
| PUT item | application/hal+json, application/json |
| PATCH item | application/hal+json, application/json, application/patch+json, application/merge-patch+json |
| GET association | application/hal+json, application/json |
| PUT association | text/uri-list |
| POST association collection | text/uri-list |

The exact list depends on the resource type and version. In particular, association resources accept URIs via `text/uri-list`, not necessarily a JSON object.

### 6.1. PUT and POST Associations with text/uri-list

Example linking an `Address` to a `Customer`'s `address` association:

    curl -i -X PUT       -H "Content-Type: text/uri-list"       -d "http://localhost:8080/addresses/10"       http://localhost:8080/customers/1001/address

For collection associations, `POST` adds an element:

    curl -i -X POST       -H "Content-Type: text/uri-list"       -d "http://localhost:8080/orders/5001"       http://localhost:8080/customers/1001/orders

These URLs are examples only. Use the association links provided by HAL responses instead of guessing paths.

## 7. PATCH and Patch Document Media Types

`PATCH` describes a partial modification to a resource. Spring Data REST supports several patch media types, including:

- `application/merge-patch+json`: JSON Merge Patch, describing partial state to merge.
- `application/patch+json`: patch media type supported by Spring Data REST; exact semantics depend on the configured converter and implementation.
- `application/json` or `application/hal+json`: depending on the endpoint and version.

Example Merge Patch:

    curl -i -X PATCH       -H "Content-Type: application/merge-patch+json"       -H "Accept: application/hal+json"       -d '{"status":"INACTIVE"}'       http://localhost:8080/customers/1001

Do not change `Content-Type` to `application/merge-patch+json` if the actual body does not conform to JSON Merge Patch. Use the exact patch format agreed upon by client and server.

## 8. Configuring the Default Media Type

Spring Data REST lets you configure a default media type when a request does not specify a representation type.

Example:

    @Component
    public class RestConfiguration implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config,
                CorsRegistry cors) {
            config.setDefaultMediaType(MediaType.APPLICATION_HAL_JSON);
        }
    }

You can choose a default media type suitable for your API and clients. Constant names or configuration APIs may vary across Spring Framework/Spring Data REST versions; verify against your actual compile-time dependencies.

The two settings serve distinct purposes:

- `setDefaultMediaType(...)`: default media type when the request does not specify one.
- `useHalAsDefaultJsonMediaType(...)`: how to handle requests accepting `application/json` when HAL is used as the primary representation.

Do not change the default media type without checking existing clients. Changing the default can alter the response body that clients expect to parse.

## 9. Common Content Negotiation Errors

### 9.1. 406 Not Acceptable

The server cannot find a representation matching the client's `Accept` header.

For example, the client only accepts a media type unsupported by the endpoint:

    Accept: application/xml

If the repository resource has no corresponding XML converter, the server may return:

    HTTP/1.1 406 Not Acceptable

How to resolve:

- Send a media type supported by the endpoint.
- Check custom converters and message converter configuration.
- Check the actual responses of the endpoint rather than assuming all endpoints support the same types.

### 9.2. 415 Unsupported Media Type

The server does not support the `Content-Type` of the request body.

For example, the client sends XML to an endpoint that only accepts JSON:

    Content-Type: application/xml

The server may return:

    HTTP/1.1 415 Unsupported Media Type

How to resolve:

- Use a `Content-Type` supported by the endpoint.
- Verify the body actually conforms to that media type.
- For association `PUT`/`POST`, check whether `text/uri-list` is required.

### 9.3. 400 Bad Request

The request uses a supported media type, but the JSON or URI body is invalid, missing required data, or cannot be deserialized into the domain model.

Check JSON syntax, property names, data types, association URIs, and validation errors.

### 9.4. Receiving JSON Without _links

If a client receives a JSON representation without HAL links, check:

- Whether the `Accept` header is `application/json`.
- How `useHalAsDefaultJsonMediaType` is configured.
- Whether the endpoint is a repository resource or a custom controller.
- What the actual response `Content-Type` is.

Not every controller in the same application automatically follows Spring Data REST's representation configuration.

## 10. Using Metadata in Clients and Contract Testing

Clients can discover the API using this workflow:

1. `GET` the root resource and read the collection links.
2. Follow the `profile` link to the metadata index.
3. Follow the repository's profile link.
4. Send `Accept: application/schema+json` to retrieve JSON Schema.
5. Send `Accept: application/alps+json` to retrieve ALPS.
6. Use JSON Schema to understand property structure and ALPS to understand descriptors/transitions.
7. Send requests with the appropriate `Accept` and `Content-Type`.
8. Check the response `Content-Type` and hypermedia links.

Schemas can be used in contract tests to detect property or type changes. However, schema snapshots must be versioned alongside the API and Spring Data REST. A domain model change can alter the exported metadata.

### 10.1. Example Metadata Checks with curl

Fetch root and profile links:

    curl -i       -H "Accept: application/hal+json"       http://localhost:8080/

    curl -i       -H "Accept: application/hal+json"       http://localhost:8080/profile

Fetch JSON Schema:

    curl -i       -H "Accept: application/schema+json"       http://localhost:8080/profile/customers

Fetch ALPS:

    curl -i       -H "Accept: application/alps+json"       http://localhost:8080/profile/customers

Read the collection as HAL:

    curl -i       -H "Accept: application/hal+json"       http://localhost:8080/customers

When running against a real application, replace host, port, and resource paths with the links returned by the server.

## 11. Limitations to Understand

- JSON Schema describes representation structure, not all business rules.
- ALPS describes semantics and transitions, and does not replace authorization.
- A profile URI can return multiple metadata types depending on `Accept`; check `Content-Type`.
- Supported media types may differ across collection, item, association, and query resources.
- `application/json` may be mapped to HAL depending on default configuration.
- Association writes typically use `text/uri-list`.
- Custom controllers may have content negotiation independent of the repository exporter.
- Custom serializers, projections, or excerpts can make representations differ directly from the domain type.
- Exported JSON Schema does not prove the database has corresponding foreign keys, unique indexes, or constraints.
- Clients must still handle status codes, validation errors, and authorization failures.

## 12. Checklist

1. `GET` the root resource and follow the `profile` link provided by the server.
2. `GET` `/profile` to discover each repository's profile URI.
3. Use `Accept: application/schema+json` to fetch JSON Schema.
4. Use `Accept: application/alps+json` to fetch ALPS.
5. Check `$schema` to determine the exported JSON Schema dialect.
6. Use JSON Schema for property structure and client-side contract checks.
7. Do not treat JSON Schema as a database schema or authorization policy.
8. Use `Accept` to select the response representation.
9. Use a `Content-Type` matching the request body.
10. Check the response `Content-Type` instead of assuming from the request.
11. Check default HAL behavior when clients send `application/json`.
12. Use `text/uri-list` for association `PUT`/`POST` when required by the endpoint.
13. Use the patch media type matching the patch document structure.
14. Investigate `406`, `415`, and `400` responses by inspecting the exact headers and body.
15. Test metadata and content negotiation against the exact Spring Data REST version in use.

## References

- [Spring Data REST — Metadata, ALPS and JSON Schema](https://docs.spring.io/spring-data/rest/reference/metadata.html)
- [Spring Data REST — Repository resources and supported media types](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — RepositoryRestConfiguration API](https://docs.spring.io/spring-data/rest/docs/current/api/org/springframework/data/rest/core/config/RepositoryRestConfiguration.html)
- [Spring Boot — Spring HATEOAS and HAL media type defaults](https://docs.spring.io/spring-boot/reference/web/spring-hateoas.html)
- [JSON Schema — Media type application/schema+json](https://github.com/json-schema-org/json-schema-spec/blob/main/ietf/json-schema-media-types.md)
- [HTTP Semantics — Accept and Content-Type](https://www.rfc-editor.org/rfc/rfc9110.html)
