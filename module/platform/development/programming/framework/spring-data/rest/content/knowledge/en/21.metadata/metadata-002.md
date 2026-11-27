# How ALPS Describes Resource Properties and Operations

## Objectives

ALPS (Application-Level Profile Semantics) is a metadata format that describes the application-level semantics of a resource and the operations that can be performed on that resource. Spring Data REST generates an ALPS document for every exported repository. As a result, clients can discover the properties, relationships, and REST state transitions exposed by the API instead of looking at a sample JSON payload and guessing their meaning.

ALPS adds semantics to hypermedia. It does not replace the HAL data returned by endpoints, nor is it a full data validation schema. HAL describes the representation and links in a response; ALPS explains the meaning of the published elements and operations.

## 1. Finding the ALPS Document in Spring Data REST

Spring Data REST exposes metadata via the `profile` link relation.

Suppose an application has two exported repositories: `persons` and `addresses`. The API root document may contain:

~~~json
{
  "_links": {
    "persons": {
      "href": "http://localhost:8080/persons"
    },
    "addresses": {
      "href": "http://localhost:8080/addresses"
    },
    "profile": {
      "href": "http://localhost:8080/profile"
    }
  }
}
~~~

Metadata discovery flow:

1. Call `GET /` to fetch the root document and locate the `profile` link.
2. Call `GET /profile` to view the list of profiles for each repository.
3. Follow the `/profile/persons` link to retrieve the ALPS profile describing the Person resource.
4. Follow a related repository's profile link, such as `/profile/addresses`, when you need to understand an association.

For example, `GET /profile` returns an index of profiles:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/profile"
    },
    "persons": {
      "href": "http://localhost:8080/profile/persons"
    },
    "addresses": {
      "href": "http://localhost:8080/profile/addresses"
    }
  }
}
~~~

At the root level there is only one `profile` link; you must follow `/profile` to find the metadata for each individual resource. A collection resource also includes a `profile` link pointing directly to its corresponding profile, such as `/profile/persons`.

You can request ALPS over HTTP:

~~~bash
curl -H "Accept: application/alps+json" \
  http://localhost:8080/profile/persons
~~~

Profiles are typically served by Spring Data REST at that path. The document's media type is `application/alps+json`, which differs from `application/hal+json` used by HAL representations.

## 2. Basic Structure of an ALPS Profile

An ALPS document typically contains a version and a list of descriptors:

~~~json
{
  "version": "1.0",
  "descriptors": [
    {
      "id": "person-representation",
      "descriptors": [
        {
          "name": "firstName",
          "type": "SEMANTIC"
        },
        {
          "name": "lastName",
          "type": "SEMANTIC"
        }
      ]
    }
  ]
}
~~~

Key components:

| Component | Role |
|---|---|
| `version` | Version of the ALPS format used in the document. |
| `descriptors` | List of descriptors at the current level; may nest child descriptors. |
| `id` | Descriptor identifier, often used as a fragment in `rt`. |
| `name` | Name of the property or hypermedia control described by the descriptor. |
| `type` | Classifies the descriptor by data semantics or state transition type. |
| `rt` | Resource type returned by or linked to by the descriptor; often references a descriptor via a fragment. |
| `doc` | Natural-language description for the descriptor or representation. |

In the example, `person-representation` groups the properties of a Person resource. The child descriptors describe individual elements such as `firstName` and `lastName`.

## 3. How Does ALPS Describe Properties and Relationships?

### Data Properties

Data-bearing properties of a representation are typically marked `SEMANTIC`:

~~~json
{
  "name": "firstName",
  "type": "SEMANTIC"
}
~~~

This descriptor indicates that the representation has an element named `firstName`. ALPS describes the element's meaning and name; looking at this descriptor alone does not reveal the full data type, maximum length, required rules, or all validation constraints for the field.

Some technical properties such as `id` may also appear in the profile. Therefore, treat ALPS as metadata about the semantics of the model and API rather than assuming every descriptor corresponds to a field the client will always see in every response.

### Relationships to Other Resources

An association property can be represented as a hypermedia control. For example, Person has an `address` relationship to an Address resource:

~~~json
{
  "name": "address",
  "type": "SAFE",
  "rt": "http://localhost:8080/profile/addresses#address"
}
~~~

Here:

- `name: address` identifies the exposed relationship.
- `type: SAFE` indicates that the client can follow the link to perform a safe state transition, typically `GET`.
- `rt` references the `address` descriptor in the Address resource's profile, helping the client identify the target resource type.

This distinction is very useful: a simple field like `firstName` describes data, whereas `address` can be a navigational link to another resource. The client can follow the link and continue discovering the target resource's profile.

## 4. How Does ALPS Describe REST Operations?

In addition to the representation, ALPS lists the operations supported by the repository resource. Each operation is a descriptor with an identifier, control name, state transition type, and associated resource type.

Four important `type` values:

| Type | Meaning | HTTP Example |
|---|---|---|
| `SEMANTIC` | Data or state element in a representation. | `firstName` property. |
| `SAFE` | Safe state transition that does not alter server state. | `GET`, `HEAD`. |
| `IDEMPOTENT` | State transition that alters server state, where repeating the same request has the same final effect. | `PUT`, `DELETE`. |
| `UNSAFE` | State transition that is neither safe nor idempotent. | `POST`. |

For example, operations commonly appearing in a Person profile:

~~~json
[
  {
    "id": "create-persons",
    "name": "persons",
    "type": "UNSAFE",
    "rt": "#person-representation"
  },
  {
    "id": "get-persons",
    "name": "persons",
    "type": "SAFE",
    "rt": "#person-representation"
  },
  {
    "id": "delete-person",
    "name": "person",
    "type": "IDEMPOTENT",
    "rt": "#person-representation"
  },
  {
    "id": "patch-person",
    "name": "person",
    "type": "UNSAFE",
    "rt": "#person-representation"
  },
  {
    "id": "update-person",
    "name": "person",
    "type": "IDEMPOTENT",
    "rt": "#person-representation"
  },
  {
    "id": "get-person",
    "name": "person",
    "type": "SAFE",
    "rt": "#person-representation"
  }
]
~~~

How to read them:

- `create-persons` is the operation to create a Person on the `persons` collection. The plural name indicates the operation applies to the collection; `POST` can create a new item.
- `get-persons` reads the collection, while `get-person` reads a single item.
- `update-person` represents an idempotent update, typically corresponding to `PUT`.
- `patch-person` represents a partial representation update in a manner not considered idempotent.
- `delete-person` represents deleting a resource; repeating the same operation causes no further change to the final state.

The `rt` field in these operation descriptors points to `#person-representation`, meaning the result or related resource type is the Person representation. `id` distinguishes each operation; `name` indicates whether the control is attached to the collection or an item.

These descriptors describe the state transitions Spring Data REST exposes for the repository. They are not a list of every Java method in the repository, nor do they replace server-side authorization checks, validation, or business rules.

## 5. How Do Projections Appear in ALPS?

If a repository declares projections, Spring Data REST includes them in the metadata of the relevant `GET` operations. A `projection` descriptor is nested inside the operation descriptor, listing the selectable projections and the properties each projection provides.

Abridged example:

~~~json
{
  "id": "get-persons",
  "name": "persons",
  "type": "SAFE",
  "rt": "#person-representation",
  "descriptors": [
    {
      "name": "projection",
      "type": "SEMANTIC",
      "descriptors": [
        {
          "name": "inlineAddress",
          "type": "SEMANTIC",
          "descriptors": [
            {
              "name": "address",
              "type": "SEMANTIC"
            },
            {
              "name": "firstName",
              "type": "SEMANTIC"
            },
            {
              "name": "lastName",
              "type": "SEMANTIC"
            }
          ]
        },
        {
          "name": "noAddresses",
          "type": "SEMANTIC",
          "descriptors": [
            {
              "name": "firstName",
              "type": "SEMANTIC"
            },
            {
              "name": "lastName",
              "type": "SEMANTIC"
            }
          ]
        }
      ]
    }
  ]
}
~~~

In the example:

- `projection` is the parameter for selecting how the representation is rendered.
- `inlineAddress` provides `address`, `firstName`, and `lastName`.
- `noAddresses` provides only `firstName` and `lastName`.

Clients can read the metadata to learn which projections are supported and which fields each projection includes, then choose the appropriate projection using the API's mechanism.

## 6. Adding Human-Readable Descriptions with rest-messages.properties

Property names such as `firstName` or `address` do not fully explain business meaning. Spring Data REST allows adding descriptive text to ALPS using a `rest-messages.properties` file.

Example placed in classpath resources:

~~~properties
rest.description.person=A collection of people
rest.description.person.id=Primary key used internally to store a person
rest.description.person.firstName=Person's first name
rest.description.person.lastName=Person's last name
rest.description.person.address=Person's address
~~~

Meaning of the keys:

- `rest.description.person` describes the overall Person representation.
- `rest.description.person.firstName` describes the `firstName` property.
- `rest.description.person.address` describes the `address` relationship.
- `rest.description.person.id` adds a description for the identifier property.

Once configured, the corresponding descriptor includes a `doc` section:

~~~json
{
  "name": "firstName",
  "doc": {
    "value": "Person's first name",
    "format": "TEXT"
  },
  "type": "SEMANTIC"
}
~~~

The `doc` section provides explanations for humans and clients; it does not rename properties, alter endpoints, or enforce validation. Spring MVC supports locales, so language-specific message files can be provided to describe metadata appropriately for clients.

## 7. What Can ALPS Help Clients Do?

A client can use ALPS to:

1. **Discover structure:** learn which properties and relationships a representation has.
2. **Understand links:** distinguish ordinary data from safe links leading to other resources.
3. **Discover operations:** recognize whether the API supports read, create, update, or delete operations on collections and items.
4. **Build generic UIs:** use descriptors to render fields, select links, and choose appropriate operations.
5. **Discover projections:** learn about alternative representations advertised by the server.
6. **Display guidance:** use the `doc` section to explain properties and operations to users.

ALPS helps clients reduce reliance on hard-coded endpoint names. However, metadata does not guarantee that an operation will succeed: the server can still reject requests due to authentication, authorization, validation, resource state, or business rules.

## 8. Distinguishing ALPS, HAL, and JSON Schema

| Mechanism | Question It Answers | Role |
|---|---|---|
| HAL (`application/hal+json`) | What data and links does the current resource have? | Hypermedia representation in responses. |
| ALPS (`application/alps+json`) | What do the exposed properties and state transitions mean? | Semantic profile of the API. |
| JSON Schema (`application/schema+json`) | What types and shape constraints does the data structure have? | Structural description, useful for data validation. |

Spring Data REST uses the same profile URI to serve different metadata formats based on the media type. For example:

~~~bash
# ALPS metadata
curl -H "Accept: application/alps+json" \
  http://localhost:8080/profile/persons

# JSON Schema metadata
curl -H "Accept: application/schema+json" \
  http://localhost:8080/profile/persons
~~~

Do not use ALPS in place of JSON Schema when you need data types, formats, or structural constraints. Conversely, JSON Schema does not fully convey the semantics of hypermedia state transitions the way ALPS does.

## 9. How to Troubleshoot When ALPS Is Missing or Incorrect

| Symptom | What to Check |
|---|---|
| `profile` link not found in root document | Whether the repository is detected and exported by Spring Data REST; check base path configuration and the root document. |
| `/profile` does not include the expected repository | Whether the repository has export disabled via `exported = false` or equivalent configuration. |
| `/profile/{rel}` does not return the expected profile | Check the actual relation/path advertised by the repository and follow the exact link from `/profile`. |
| Missing property in representation descriptor | Check the domain type, exported properties, and related serialization/projection configuration. |
| Missing create/update/delete operations | Check exported methods, repository configuration, and methods hidden with `@RestResource(exported = false)`. |
| Relationship does not point to the target profile | Check that the related resource's repository is exported and whether `rt` references the right profile/descriptor. |
| Missing explanation in `doc` | Check key names in `rest-messages.properties`, resource file location, and the locale being used. |
| Client misinterprets descriptor types | Cross-check `type`: `SEMANTIC`, `SAFE`, `IDEMPOTENT`, `UNSAFE`; do not treat them as Java data types. |

When troubleshooting, start from the `profile` link returned by the server, follow the link to the repository profile, and then inspect the specific descriptors. This avoids relying on guessed paths or outdated documentation.

## Key Takeaways

ALPS describes resources across two main layers. The representation layer uses descriptors, typically with `type: SEMANTIC`, to list properties; relationships to other resources can be `SAFE` hypermedia controls pointing to the target profile via `rt`. The operation layer uses descriptors such as `get-persons`, `create-persons`, `update-person`, and `delete-person`, classified as `SAFE`, `UNSAFE`, or `IDEMPOTENT`. Spring Data REST exposes this document via `/profile` and `/profile/{rel}`; projections and custom descriptions can also be reflected in the metadata.

## References

- [Spring Data REST Reference — Metadata and ALPS](https://docs.spring.io/spring-data/rest/reference/metadata.html)
- [Application-Level Profile Semantics (ALPS) Specification](https://alps.io/spec/drafts/draft-00.html)
- [RFC 6906 — The 'profile' Link Relation Type](https://www.rfc-editor.org/rfc/rfc6906)
