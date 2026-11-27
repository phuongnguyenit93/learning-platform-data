# Profile Links and Resource Self-Descriptiveness in Spring Data REST

## Objectives

After this lesson, you will be able to explain why Spring Data REST returns hypermedia links alongside a resource representation; explore an API starting from the API root; distinguish between `self`, collection, item, association, `search`, and `profile` links; use `profile` to retrieve ALPS or JSON Schema metadata; and build a client that navigates via server-provided links instead of constructing URLs manually.

## 1. What is a Self-Descriptive Resource?

A self-descriptive REST resource provides enough information for a client to understand which resource a response refers to, what the data means at the representation level, and how to perform the next step. This capability typically comes from a combination of:

- HTTP methods, status codes, and headers.
- Media types in the request and response.
- Hypermedia links along with relations describing each link's purpose.
- Metadata/profiles explaining semantics and data structure.
- The current representation and embedded resources, if any.

For example, a JSON response containing `id`, `name`, and `address` fields without a clear media type or link relations may force a client to know the URLs and field meanings ahead of time. With hypermedia, the server returns a representation accompanied by links such as `self`, `people`, `search`, `profile`, or `next`. The client inspects the relation to understand what a link is for and then follows the actual URI returned by the server.

This concept is closely associated with HATEOAS (Hypermedia as the Engine of Application State): the client discovers possible next actions from hypermedia controls in the response. The client still needs to understand media types and relation semantics; hypermedia does not automatically make a client completely independent of domain knowledge.

## 2. Spring Data REST Uses HAL to Represent Resources

Spring Data REST typically uses HAL (Hypertext Application Language) to represent resources. HAL JSON places links inside the `_links` object and embedded resources inside `_embedded`.

Example collection response:

```json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/people"
    },
    "profile": {
      "href": "http://localhost:8080/profile/people"
    },
    "search": {
      "href": "http://localhost:8080/people/search"
    }
  },
  "_embedded": {
    "people": [
      {
        "firstName": "An",
        "lastName": "Nguyen",
        "_links": {
          "self": {
            "href": "http://localhost:8080/people/1"
          }
        }
      }
    ]
  },
  "page": {
    "size": 20,
    "totalElements": 1,
    "totalPages": 1,
    "number": 0
  }
}
```

This is an abridged illustrative response. Actual relation names, URLs, `page` fields, and embedded content depend on the repository path, configuration, projections, and data.

Important components:

- `_links`: hypermedia links that the client can follow.
- `_embedded`: resources embedded within the current representation.
- `page`: pagination information for the collection.
- `self`: URI of the resource or collection currently being represented.

An item resource also has a `self` link and may have links to associations such as `address`, `orders`, or related resources. Clients should read the URI from the link rather than deriving the URI from an ID.

## 3. Starting Discovery from the API Root

The API root is the entry point where a client begins interacting with Spring Data REST. When an application exports repositories, the root typically provides links to each repository's collection resource along with a `profile` link.

Example:

```http
GET /
Accept: application/hal+json
```

Abridged response:

```json
{
  "_links": {
    "people": {
      "href": "http://localhost:8080/people"
    },
    "orders": {
      "href": "http://localhost:8080/orders"
    },
    "profile": {
      "href": "http://localhost:8080/profile"
    }
  }
}
```

The client starts with the configured or provided entry point URL. From there, the client looks up the `people` relation to open the collection, `orders` to open another collection, or `profile` to discover metadata.

You should not hard-code paths like `/people`, `/orders`, or `/profile` into every client just because the examples use them. An application can change the base path, repository path, or collection relation via configuration. The API root is where the active links are advertised.

Example repository:

```java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String firstName;
    private String lastName;
}
```

```java
@RepositoryRestResource(
    path = "people",
    collectionResourceRel = "people")
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
```

With the configuration above, Spring Data REST exports the repository as a collection resource and advertises the corresponding link relation at the API root.

## 4. Understanding Common Link Types

Links with different relations describe different navigation paths. Some common relations in Spring Data REST/HAL:

| Relation | Purpose | Example |
| --- | --- | --- |
| self | URI of the current resource | Item /people/1 |
| Collection name, e.g. people | Open the collection resource | /people |
| profile | Find metadata/profile describing resource or API semantics | /profile or a specific profile |
| search | Discover exported query resources | /people/search |
| Association name, e.g. address | Access a linked resource | /people/1/address |
| first, prev, next, last | Navigate collection pages | Pagination links |
| related or custom relation | Access a related resource according to API semantics | URI provided by the server |

Specific relation names depend on the media type, configuration, and resource type. Not every response contains all relations in the table. Clients must inspect the actual links present in the response.

### Links Can Be URI Templates

Some links may contain a URI template and the property `templated: true`, for example:

```json
{
  "_links": {
    "findByLastName": {
      "href": "http://localhost:8080/people/search/findByLastName{?name}",
      "templated": true
    }
  }
}
```

Clients need to expand template variables according to URI template rules, such as `name=Nguyen`, instead of concatenating strings manually. Never assume every link is a complete URL without variables.

### Links and Embedded Resources Are Different

A link lets the client navigate to another resource when needed. An embedded resource includes a representation of the related resource directly in the current response. Embedded data can reduce the number of requests, but it does not replace the `self` link or other links needed to continue interacting.

Clients should use links when they need the latest representation or to perform operations on the target resource. Embedded data may be a projection or an abridged representation, so you must not assume it contains all properties of the original resource.

## 5. What Is the Profile Link Used For?

The `profile` relation helps clients locate metadata that further describes the semantics of a resource or API. In Spring Data REST, the API root provides a `profile` link. Clients follow that link to view the list of profiles for the exported repositories.

Example:

```http
GET /profile
Accept: application/hal+json
```

The response may list the profile links:

```json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/profile"
    },
    "people": {
      "href": "http://localhost:8080/profile/people"
    },
    "orders": {
      "href": "http://localhost:8080/profile/orders"
    }
  }
}
```

The client follows the profile link for the target repository, such as `/profile/people`. A specific profile URI can serve different metadata formats depending on the `Accept` header.

A profile is not a CRUD endpoint for the resource. It provides descriptions of the resource and API semantics so clients, documentation, or tooling can better understand the representation.

## 6. Retrieving an ALPS Profile from Spring Data REST

Spring Data REST provides ALPS (Application-Level Profile Semantics) metadata for repositories. ALPS describes descriptors for resource semantics and affordances, such as:

- Properties or semantic descriptors of the representation.
- Safe, idempotent, or unsafe operations.
- The resource type associated with what an operation creates or returns.
- Exported projections, depending on configuration.

The client follows the profile link and requests ALPS:

```http
GET /profile/people
Accept: application/alps+json
```

Example abridged ALPS document:

```json
{
  "version": "1.0",
  "descriptors": [
    {
      "id": "person",
      "descriptors": [
        { "name": "firstName", "type": "SEMANTIC" },
        { "name": "lastName", "type": "SEMANTIC" }
      ]
    },
    {
      "id": "get-people",
      "name": "people",
      "type": "SAFE",
      "rt": "#person"
    },
    {
      "id": "create-people",
      "name": "people",
      "type": "UNSAFE",
      "rt": "#person"
    }
  ]
}
```

This is an illustrative example. The actual descriptors generated by Spring Data REST depend on the domain type, repository, projections, and framework version.

ALPS focuses on semantics and discoverable transitions. It does not replace a detailed data schema or a full HTTP contract specification.

## 7. Retrieving JSON Schema from the Same Profile URI

Spring Data REST can provide JSON Schema for a repository profile. Use the same profile URI and change content negotiation:

```http
GET /profile/people
Accept: application/schema+json
```

Example abridged JSON Schema:

```json
{
  "$schema": "https://json-schema.org/draft-04/schema#",
  "title": "Person",
  "type": "object",
  "properties": {
    "firstName": {
      "type": "string"
    },
    "lastName": {
      "type": "string"
    }
  }
}
```

JSON Schema describes the data shape such as objects, properties, data types, and some constraints. Clients can use it to generate forms, validate JSON, or generate models.

Distinguish clearly:

- ALPS answers questions about resource semantics and affordances.
- JSON Schema answers questions about JSON structure and constraints.
- The profile URI is the endpoint for retrieving metadata; the collection/item URI is the resource endpoint for manipulating data.

Both metadata formats are selected via media types. Read the response `Content-Type` and do not assume the server always returns the requested format simply because the client sent an `Accept` header.

## 8. Search Links and Query Resources

Spring Data REST can expose repository query methods under a `search` resource. Clients discover the `search` link from the collection rather than guessing query URLs.

Example repository:

```java
@RepositoryRestResource(
    path = "people",
    collectionResourceRel = "people")
public interface PersonRepository
        extends JpaRepository<Person, Long> {

    List<Person> findByLastName(@Param("name") String lastName);
}
```

Spring Data REST may provide a link such as:

```json
{
  "_links": {
    "search": {
      "href": "http://localhost:8080/people/search"
    }
  }
}
```

Follow the `search` link:

```http
GET /people/search
Accept: application/hal+json
```

The search resource returns links to query methods. A query link may be a URI template:

```json
{
  "_links": {
    "findByLastName": {
      "href": "http://localhost:8080/people/search/findByLastName{?name}",
      "templated": true
    }
  }
}
```

The client populates the query parameter according to the template:

```http
GET /people/search/findByLastName?name=Nguyen
Accept: application/hal+json
```

Actual query method names, parameters, and URIs depend on repository methods and annotations. If a method is not exported or is hidden with `@RestResource(exported = false)`, the client will not receive a corresponding link.

## 9. Association Links and Navigating Between Resources

Spring Data REST can represent associations between entities using dedicated links. For example, `Person` has an `Address`:

```java
@Entity
public class Person {

    @Id
    @GeneratedValue
    private Long id;

    private String name;

    @ManyToOne
    private Address address;
}
```

An item response may contain:

```json
{
  "name": "An",
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/1"
    },
    "address": {
      "href": "http://localhost:8080/people/1/address"
    }
  }
}
```

The client follows the `address` relation to read the association resource. If the association needs to be modified, use the URI and HTTP method/payload advertised by Spring Data REST for the association endpoint. For a to-one association, the API typically supports `PUT` to link a resource and `DELETE` to unlink it; to-many associations have their own semantics and payloads. Check the actual mappings and response statuses before implementing the client.

For example, updating an association should not be built by guessing a path from the IDs of `Person` and `Address`. Follow the returned link relation and send the target resource's URI in the format required by the association endpoint.

The presence of an association link also does not mean the client is permitted to access or modify it. Authorization and repository exposure still determine which operations are allowed.

## 10. Pagination Links and Collection Navigation

Large collections are usually split into multiple pages. Spring Data REST uses navigation links such as `first`, `prev`, `self`, `next`, and `last`, along with information in the `page` object.

Example:

```json
{
  "_links": {
    "first": { "href": "http://localhost:8080/people?page=0&size=20" },
    "prev": { "href": "http://localhost:8080/people?page=1&size=20" },
    "self": { "href": "http://localhost:8080/people?page=2&size=20" },
    "next": { "href": "http://localhost:8080/people?page=3&size=20" },
    "last": { "href": "http://localhost:8080/people?page=8&size=20" }
  },
  "page": {
    "size": 20,
    "totalElements": 175,
    "totalPages": 9,
    "number": 2
  }
}
```

The URLs in the example are for illustration only. On the first page, the `prev` link may not appear; on the last page, the `next` link may not appear. Clients should not increment `page` manually by assembling query strings. Follow `next` if that link exists, and stop when there is no `next` link.

This approach keeps the client independent of the server's default page size or pagination rules. The server can change the maximum page size while the client continues navigating via advertised links.

## 11. Clients Navigating by Links Instead of Hard-Coding URLs

A hypermedia client typically performs the following sequence of operations:

1. Send `GET` to the API root.
2. Read the required link relation, such as `people`.
3. Follow that link to fetch the collection.
4. Select an item and follow `self` to fetch its details.
5. Follow `profile` if it needs to understand semantics or schema.
6. Follow `search` to discover query methods.
7. Follow association links or pagination links when business logic requires them.

Minimal JavaScript example:

```javascript
async function getHal(url) {
    const response = await fetch(url, {
        headers: { Accept: "application/hal+json" }
    });

    if (!response.ok) {
        throw new Error("HTTP " + response.status);
    }

    return response.json();
}

const root = await getHal("https://api.example.com/");
const peopleUrl = root._links.people.href;

const people = await getHal(peopleUrl);
const firstPerson = people._embedded.people[0];
const personUrl = firstPerson._links.self.href;

const person = await getHal(personUrl);
console.log(person);
```

This example uses links returned by the server at each step. In a real application, you must handle URI templates, missing links, authentication, network errors, media types, and response statuses appropriately.

Never assume a link relation is always present. A repository might not export `search`; an item might have no association; the last page of a collection has no `next` link. Clients must check for the link before using it.

### Using Spring HATEOAS Traverson

If the client is written in Java, Spring HATEOAS provides `Traverson` to navigate REST APIs by relation:

```java
Traverson traverson = new Traverson(
    URI.create("https://api.example.com/"),
    MediaTypes.HAL_JSON);

ParameterizedTypeReference<CollectionModel<EntityModel<Person>>> type =
    new ParameterizedTypeReference<>() {};

CollectionModel<EntityModel<Person>> people =
    traverson
        .follow("people")
        .toObject(type);
```

This example illustrates following the `people` relation; return types and authentication configuration must be adjusted to match the actual client and response.

## 12. Creating Custom Links for Representations

When you need to add business-specific links, you can use Spring HATEOAS and Spring Data REST extension points. A common approach is implementing `RepresentationModelProcessor` to add links to a representation.

Illustrative example:

```java
@Component
public class PersonModelProcessor
        implements RepresentationModelProcessor<EntityModel<Person>> {

    @Override
    public EntityModel<Person> process(EntityModel<Person> model) {
        model.getContent().ifPresent(person -> {
            Link summary = Link.of(
                "/people/" + person.getId() + "/summary",
                "summary");
            model.add(summary);
        });

        return model;
    }
}
```

This is a conceptual example; in a real application, use Spring HATEOAS link builders to generate URIs with accurate context path, base path, and encoding instead of string concatenation. Make sure the target endpoint actually exists and has appropriate authorization.

A custom link should have a clearly meaningful relation. If the relation is application-specific, document it in the profile or API documentation so clients understand its purpose. Do not add links just to display a URL if the client has no semantics to act on it.

## 13. Content Negotiation Makes Representations Self-Descriptive

Clients can use the `Accept` header to request a desired media type. The server returns `Content-Type` indicating the actual representation.

Example:

```http
GET /people
Accept: application/hal+json
```

To retrieve an ALPS profile:

```http
GET /profile/people
Accept: application/alps+json
```

To retrieve JSON Schema:

```http
GET /profile/people
Accept: application/schema+json
```

These media types are not interchangeable. HAL JSON is a resource representation; ALPS is a semantic profile; JSON Schema describes data structure. If a client sends an `Accept` header unsupported by the server, the server may return `406 Not Acceptable`.

Response headers can also carry other important information:

- `Content-Type`: format of the representation.
- `Location`: URI of the newly created resource after `POST`.
- `ETag` or `Last-Modified`: validators supporting caching or conditional requests when configured.
- `Cache-Control`: caching policy.

Clients should retain validators and URIs associated with the exact resource/representation. Do not infer a version or update timestamp solely from the body content when the server already provides dedicated headers.

## 14. Self-Descriptive Does Not Mean Automatically Complete or Always Accessible

Hypermedia helps clients discover capabilities advertised by the server, but it has several limitations:

**Not every relation has globally standardized semantics.** Standard relations like `self` and `next` have widely defined semantics; custom relations like `summary` require a profile or documentation to explain them.

**A link does not guarantee access permission.** The server may return a link, yet the request still requires authentication/authorization. Conversely, links may be hidden from representations depending on the design. Clients must still handle `401`, `403`, and `404`.

**A profile is not complete schema validation.** ALPS describes semantics; JSON Schema describes shape; business rules depending on state or multiple resources still need to be enforced by the server.

**Embedded representations may be abridged.** Clients should not assume an embedded resource is equivalent to a full `GET` item resource.

**URLs can change.** This is precisely why clients should follow links. However, clients still need a stable entry point or initial configuration to find the API root.

**Hypermedia does not eliminate versioning and compatibility.** When semantics or relations change, compatibility must be maintained or changes published in a controlled manner. Clients should handle missing links and unfamiliar new relations gracefully.

## 15. Common Pitfalls When Working with Profiles and Hypermedia Links

**Client builds URLs manually from IDs**

This couples the client to path conventions. Use `self` and association links returned by the server.

**Cannot find the profile link**

Check the API root and follow the `profile` relation. Spring Data REST typically provides a profile index at `/profile`, which then links to each repository's profile.

**Sending the wrong Accept header**

Use `application/hal+json` for HAL resources, `application/alps+json` for ALPS, and `application/schema+json` for JSON Schema. Check the response `Content-Type`.

**Assuming every collection has search**

Only exported query methods appear. Follow the `search` link first, then follow the specific query link.

**Assuming every item has an association**

Association links depend on mappings, export settings, and access permissions. Check the item's `_links` before navigating.

**Building pagination links manually by modifying page numbers**

Use `next` or `prev` links provided by the server to stay independent of page size and pagination rules.

**Not handling URI templates**

Check the `templated` property; expand variables according to the URI template specification and properly encode query values.

**Treating profile links as data endpoints**

Profiles describe semantics/schema; collection and item resources are the endpoints for reading or modifying data.

## Summary

- Spring Data REST uses HAL JSON to return resources with `_links`, `_embedded`, and `page` information.
- The API root is the entry point; clients inspect relations such as collection names and `profile` to discover the API.
- `self`, `search`, association, and pagination links provide navigation paths matching the server's actual state.
- The `profile` link leads to repository metadata; use `application/alps+json` to fetch ALPS and `application/schema+json` to fetch JSON Schema.
- ALPS describes semantics/affordances; JSON Schema describes JSON structure; HAL represents resources and links.
- Clients should follow links returned by the server, handle URI templates, and verify that a relation exists before using it.
- Links do not grant access permissions on their own; authentication, authorization, and validation are still enforced by the server.
- Self-descriptive representations improve discoverability and reduce URL coupling, though clients still need to understand media types and relation semantics.

## References

- [Spring Data REST — Metadata](https://docs.spring.io/spring-data/rest/reference/metadata.html)
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Excerpt projections and projections](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html)
- [Spring HATEOAS — Representation models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [HAL — Hypertext Application Language](https://stateless.group/hal_specification.html)
- [RFC 6906 — The 'profile' Link Relation Type](https://www.rfc-editor.org/rfc/rfc6906)
- [RFC 8288 — Web Linking](https://www.rfc-editor.org/rfc/rfc8288)
