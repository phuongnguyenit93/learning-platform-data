# Descriptors, rel, and the SEMANTIC, SAFE, IDEMPOTENT, and UNSAFE Types

## Context

Spring Data REST provides hypermedia-driven REST APIs. Clients not only receive data but can also discover links and metadata advertised by the server. Two key concepts in this area are:

- **Descriptor**: describes the semantics of data or an operation supported by the API. Spring Data REST uses the ALPS format to expose profile metadata.
- **rel** (link relation): the relation name of a hyperlink, indicating what type of resource or action the link points to. In HAL, `rel` is a key inside the `_links` object.

In ALPS, a descriptor can carry one of four common types: `SEMANTIC`, `SAFE`, `IDEMPOTENT`, and `UNSAFE`. These types describe the meaning of data or the characteristics of a transition. They are neither HTTP method names nor link relation names.

To read metadata accurately, separate three layers: descriptors describe data/operations; `rel` identifies a link's relation; and the URI in `href` specifies the target a client can access.

## 1. What Is a Descriptor?

A descriptor is a metadata element describing a concept in the API. In ALPS (Application-Level Profile Semantics), a descriptor can describe:

- A data property, such as `name`, `email`, `status`.
- A representation or a group of properties.
- A transition that a client can perform, such as reading a user, creating a new record, or updating data.
- Input properties of a transition.

An ALPS document can be returned as JSON with the media type:

    application/alps+json

Abridged example:

    {
      "alps": {
        "version": "1.0",
        "descriptor": [
          {
            "id": "person-representation",
            "type": "SEMANTIC",
            "descriptor": [
              {
                "name": "firstName",
                "type": "SEMANTIC"
              },
              {
                "name": "email",
                "type": "SEMANTIC"
              }
            ]
          },
          {
            "id": "get-person",
            "name": "get-person",
            "type": "SAFE",
            "rt": "#person-representation"
          }
        ]
      }
    }

This example illustrates the structure and meaning of the metadata; actual IDs, names, and descriptor lists depend on the application's repositories and configuration.

Common fields:

| Field | Meaning |
| --- | --- |
| `id` | Descriptor identifier within the profile; can be referenced by other descriptors |
| `name` | Name of the property or transition being described |
| `type` | Descriptor classification: `SEMANTIC`, `SAFE`, `IDEMPOTENT`, or `UNSAFE` |
| `doc` | Documentation explaining the meaning of the descriptor |
| `descriptor` | List of child descriptors, often used to describe representation fields or inputs |
| `rt` | Reference to a descriptor describing the returned representation type (return type) |
| `ext` | Extension metadata advertised by the profile |

Not every descriptor needs all of the fields above. For example, a descriptor describing a data field may only need `name` and `type`; a descriptor describing a transition may additionally have `id`, `rt`, or child descriptors describing inputs.

### Distinguishing id and name

`id` and `name` serve different roles:

- `id` identifies the descriptor, especially when another descriptor needs to reference it.
- `name` specifies the name of the property or transition according to the profile semantics.

For example, a descriptor with `id="get-person"` and `name="get-person"` may share the same value in a specific case, but you should not assume the two fields are always synonymous. When reading `rt`, treat it as a reference to a representation descriptor, not an endpoint URL.

## 2. ALPS Profiles in Spring Data REST

Spring Data REST can expose profile metadata so clients understand the resources and operations the API supports. Resources typically provide a `profile` link relation in HAL. Clients follow that link to retrieve the ALPS document.

Example request:

    GET http://localhost:8080/profile
    Accept: application/alps+json

An ALPS response may describe the representation of a `Person` entity, fields such as `firstName` and `email`, and transitions associated with the repository.

A representation descriptor can contain child descriptors:

    {
      "id": "person-representation",
      "type": "SEMANTIC",
      "descriptor": [
        {
          "name": "firstName",
          "type": "SEMANTIC"
        },
        {
          "name": "email",
          "type": "SEMANTIC"
        }
      ]
    }

A transition descriptor can reference the returned representation:

    {
      "id": "get-person",
      "name": "get-person",
      "type": "SAFE",
      "rt": "#person-representation"
    }

In this example, the first descriptor describes the data structure. The second describes a read operation and indicates the representation type returned by the operation. `rt` is a reference within the profile; clients do not call `#person-representation` as an HTTP URL.

ALPS metadata helps clients discover API semantics without having to guess the entire structure from Java class names or database column names.

## 3. What Is rel?

`rel` stands for *link relation*. It describes the relationship between the current resource and the resource pointed to by the hyperlink.

In HAL JSON, a link relation typically appears as a key inside `_links`:

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/people/42"
        },
        "profile": {
          "href": "http://localhost:8080/profile"
        },
        "orders": {
          "href": "http://localhost:8080/people/42/orders"
        }
      }
    }

Here:

- `self` indicates the link points to the current resource itself.
- `profile` indicates the link to profile metadata.
- `orders` indicates the link to related resources, namely this user's orders.
- `href` is the target URI for each link.

`rel` answers the question “what does this link mean in relation to the current resource?”. It does not specify an HTTP method, does not indicate whether the operation is safe or unsafe, and does not contain the target resource's content.

### Standard rels and Custom rels

Several common rels are standardized, for example:

- `self`: the current resource itself.
- `next`: the next resource/page.
- `prev`: the previous resource/page.
- `first`: the first resource/page.
- `last`: the last resource/page.
- `profile`: the profile describing the resource.

An API can also expose business-specific rels, such as `orders`, `customer`, `search`, or another relation name chosen by the application. Clients should use `rel` to find the link with the needed meaning instead of parsing URL strings.

## 4. Customizing rel in Spring Data REST

Spring Data REST lets you customize collection relation names, paths, and relations for finders or associations using annotations.

Example of customizing a collection relation:

    @RepositoryRestResource(
        collectionResourceRel = "people",
        path = "people"
    )
    public interface PersonRepository
            extends JpaRepository<Person, Long> {
    }

The collection resource has path `/people`; HAL can represent the collection link with rel `people`.

For a finder method:

    @RepositoryRestResource(
        collectionResourceRel = "people",
        path = "people"
    )
    public interface PersonRepository
            extends JpaRepository<Person, Long> {

        @RestResource(
            path = "by-email",
            rel = "by-email"
        )
        Optional<Person> findByEmail(String email);
    }

The finder is exposed under the `search` resource; `path` `"by-email"` determines the URL segment, while `rel` `"by-email"` identifies the link clients look up in HAL.

For an association:

    @Entity
    public class PurchaseOrder {

        @ManyToOne
        @RestResource(
            path = "buyer",
            rel = "buyer"
        )
        private Customer customer;
    }

The association link may appear with rel `buyer` and a corresponding URI containing the path `buyer`.

Distinguish clearly:

| Attribute | Effect |
| --- | --- |
| `path` | Customizes the URI path |
| `rel` | Customizes the link relation name |
| `collectionResourceRel` | Customizes the rel of the collection resource |
| `exported` | Controls whether the association or resource is published |

Changing `rel` does not necessarily change the URI. Changing `path` does not necessarily change the `rel` name. If an API already has active clients, treat changing either value as a hypermedia contract change and evaluate compatibility impact.

## 5. The SEMANTIC Type

`SEMANTIC` describes data or the meaning of an element in a representation. It is commonly used for descriptors of entity properties or descriptors representing data structures.

Example:

    {
      "id": "person-representation",
      "type": "SEMANTIC",
      "descriptor": [
        {
          "name": "firstName",
          "type": "SEMANTIC"
        },
        {
          "name": "email",
          "type": "SEMANTIC"
        }
      ]
    }

In this example, `firstName` and `email` are data concepts of the Person representation. They are not transitions for the client to invoke.

Keep in mind:

- `SEMANTIC` describes “what does this data mean?”.
- It does not specify `GET`, `POST`, `PUT`, or `DELETE`.
- It does not assert that the data can be written or edited.
- Read/write permissions are still governed by endpoints, mappings, and Spring Security.

A field appearing in a profile does not mean the client can send that field in every request. To know which inputs are accepted, check the corresponding transition descriptor and the endpoint contract.

## 6. The SAFE Type

`SAFE` describes a transition that does not request changes to resource state on the server. In HTTP, `GET` is the classic example of a safe method.

Example descriptor:

    {
      "id": "get-person",
      "type": "SAFE",
      "rt": "#person-representation"
    }

It describes an operation to read a Person representation. Clients can execute this transition without requesting the server to update business data.

Characteristics:

- `SAFE` is typically associated with query/read operations.
- A safe operation is also idempotent under HTTP semantics.
- Safe does not mean the request creates no logs, metrics, or cache entries; what matters is that the client does not request a change to the resource's business state.
- `SAFE` is not an authorization mechanism. Users can still be denied `GET` by Spring Security.

HTTP example:

    GET /people/42
    Accept: application/hal+json

The request above reads Person resource 42. It does not request an update to Person.

## 7. The IDEMPOTENT Type

`IDEMPOTENT` describes a transition that is safe to repeat with respect to state effects: executing it once or repeating it multiple times with the same request produces the same final effect on the managed state.

This does not mean the request does not modify data. An operation may change state on the first call, while subsequent repetitions produce no further changes.

A common example in HTTP is `PUT`:

    PUT /people/42
    Content-Type: application/json

    {
      "firstName": "An",
      "email": "an@example.com"
    }

If the same representation is `PUT` multiple times to the same resource, the target state remains the specified content. Thus `PUT` has idempotent semantics in HTTP.

`DELETE` is also defined as idempotent: the goal is that the resource no longer exists after the operation. However, the HTTP response of the first delete and subsequent deletes may differ (e.g., `204` the first time, `404` later). Idempotence refers to the intended state effect, and does not require identical responses.

Points to remember:

- `IDEMPOTENT` is not synonymous with `SAFE`.
- An idempotent operation can modify data.
- `PUT` and `DELETE` are classic examples of methods that are idempotent but not safe.
- Do not equate idempotence with the server not re-executing code or not writing logs.

## 8. The UNSAFE Type

`UNSAFE` describes a transition that may modify resource state. An unsafe operation can create, modify, or trigger business processing.

A common example is `POST` creating a resource:

    POST /people
    Content-Type: application/json

    {
      "firstName": "An",
      "email": "an@example.com"
    }

If the same request is sent multiple times, the server may create multiple Person records. Therefore, `POST` is typically neither safe nor idempotent under default HTTP semantics.

Points to remember:

- `UNSAFE` can modify server state.
- Do not automatically retry an unsafe request after a timeout if you do not know whether the previous request was processed.
- An API may design an idempotency key mechanism or custom business rules to control duplicate requests, but that must be clearly documented in the API contract.
- `UNSAFE` does not mean the request is malicious or forbidden; it merely describes the potential to change state.

Another example is a `POST` that triggers a business action such as confirming an order. Even if the endpoint does not create a new record, it can still change the order's state and is therefore an unsafe transition.

## 9. Comparing the Four Descriptor Types

| Type | Meaning | Typical Example | Requests a State Change? |
| --- | --- | --- | --- |
| `SEMANTIC` | Describes data or a concept | `firstName`, `email` | Not a transition; not applicable |
| `SAFE` | Read-only transition that does not request business state changes | `GET` | No |
| `IDEMPOTENT` | Transition with the same state effect when repeating the same request | `PUT`, `DELETE` | Possibly |
| `UNSAFE` | Transition that may change state | `POST` creating a resource or performing a business action | Possibly |

Quick summary to remember:

- `SEMANTIC` is about **data meaning**.
- `SAFE` is about **transitions that do not request state changes**.
- `IDEMPOTENT` is about **state effect when repeating a request**.
- `UNSAFE` is about **transitions that may change state**.

Do not treat these four types as four HTTP methods. They are metadata describing descriptors; HTTP methods are part of the actual request protocol.

## 10. Relationship Between SAFE, IDEMPOTENT, and HTTP Methods

According to standard HTTP semantics:

| HTTP method | Safe | Idempotent | Notes |
| --- | --- | --- | --- |
| GET | Yes | Yes | Reads a representation |
| HEAD | Yes | Yes | Reads response metadata |
| OPTIONS | Yes | Yes | Queries communication capabilities of a resource |
| PUT | No | Yes | Sets resource state according to request content |
| DELETE | No | Yes | Requests resource deletion |
| POST | No | Not by default | Performs processing or creates a resource |
| PATCH | No | Not by default | Applies partial modifications |

The table above describes common HTTP semantics. A specific application may have a more detailed business contract, but standard interpretations of methods should not be changed arbitrarily.

`SAFE` is a stronger property regarding side effects: a safe method is also idempotent, whereas an idempotent method is not necessarily safe. For example, `PUT` can change state on the first request so it is not safe, even though sending the same content again leads toward the same state.

The ALPS descriptor type is metadata for clients to understand transitions. Do not infer the HTTP method solely from a descriptor name; check links, URIs, documentation, and operation metadata. Likewise, do not infer access permissions from `SAFE` or `IDEMPOTENT`.

## 11. Reading rel and Descriptors Together

Both types of metadata complement each other:

- HAL `rel` helps clients find links based on relationship meaning.
- ALPS descriptors help clients understand the data or transitions described in the profile.
- `href` provides the concrete URI to which the client sends requests.
- HTTP methods and representations/bodies define how to execute the request.

For example, a HAL response:

    {
      "_links": {
        "self": {
          "href": "http://localhost:8080/people/42"
        },
        "profile": {
          "href": "http://localhost:8080/profile"
        },
        "orders": {
          "href": "http://localhost:8080/people/42/orders"
        }
      }
    }

A client can follow this workflow:

1. Find the `profile` rel to fetch ALPS metadata.
2. Read the descriptors to understand representations and transitions.
3. Find the `orders` rel if it needs to navigate to orders.
4. Use the URI in `href` and the appropriate method to call the API.

A `rel` does not inherently carry a `SAFE` or `UNSAFE` type. For example, the `orders` rel only states that the link points to the orders relationship. To know which operations are supported and what their effects are, inspect the profile or corresponding endpoint contract.

## 12. Common Misconceptions

| Misconception | Accurate Understanding |
| --- | --- |
| `rel` is an HTTP method | `rel` identifies a hyperlink's relation; the method is in the request |
| A descriptor is a URL | A descriptor is metadata; `href` is the URI to access |
| `SEMANTIC` means the data is writable | `SEMANTIC` describes data meaning, not write permissions |
| `SAFE` and `IDEMPOTENT` are the same | `SAFE` means requesting no state change; `IDEMPOTENT` means repeating the request has the same state effect |
| `IDEMPOTENT` means nothing changes | `PUT`/`DELETE` can change state on the first call |
| `UNSAFE` means a dangerous or forbidden request | `UNSAFE` describes the ability to change state; execution permission is governed by the API and security |
| Having a `rel` guarantees the endpoint can be called | The link may require authentication, proper permissions, or business preconditions |
| Having a descriptor means every client must use it | Descriptors provide metadata; clients must still adhere to the contract and actual server capabilities |

## 13. Hands-On Exercise

Suppose Spring Data REST publishes the `Person` repository at `/people`. Perform the following in a test environment:

1. Call `GET /people/42` with `Accept: application/hal+json`.
2. Inspect `_links` and distinguish `self` and `profile` rels from business rels.
3. Follow the `profile` link and request `Accept: application/alps+json`.
4. Locate the Person representation descriptor and child descriptors such as `firstName` and `email`.
5. Locate the `SAFE` transition descriptor for reading a Person.
6. Compare it with descriptors for create or update operations, if exposed by the profile.
7. Try `PUT`ting the same content twice in test data and observe the final state.
8. Try `POST`ing to create a Person twice and observe whether two separate resources are created.
9. Check how Spring Security handles requests when a user lacks access permissions.

Self-check questions:

- What kinds of information are descriptors used to describe?
- How do `id`, `name`, `type`, and `rt` differ?
- In HAL, what roles do `rel` and `href` fulfill?
- Why does a `SAFE` descriptor also have idempotent semantics?
- Why can `PUT` be `IDEMPOTENT` without being `SAFE`?
- Why should `POST` not be retried automatically after a timeout?
- Does ALPS metadata replace Spring Security authorization?

## References

- [Spring Data REST Reference — Metadata and ALPS](https://docs.spring.io/spring-data/rest/reference/metadata.html)
- [Spring Data REST Reference — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [ALPS Specification](https://alps.io/spec/)
- [RFC 9110 — HTTP Semantics](https://www.rfc-editor.org/rfc/rfc9110)
- [HAL Specification](https://stateless.group/hal_specification.html)
