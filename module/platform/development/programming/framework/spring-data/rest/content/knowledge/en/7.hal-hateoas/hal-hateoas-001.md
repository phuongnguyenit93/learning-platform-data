# HAL Representation Structure with _links, _embedded, and Business Data

## Objectives

Spring Data REST typically returns resources as HAL JSON. When reading a response, you need to recognize three groups of components:

- `_links` describes the URIs that a client can navigate to, along with the relation of each link.
- `_embedded` contains representations of other resources embedded in the current response.
- The remaining properties represent the business data of the domain object, such as `id`, `name`, `status`, or `createdAt`.

These three groups combine to form a representation that provides both data and navigability. A client can display the data immediately while using the links to discover subsequent operations or resources.

## 1. HATEOAS and HAL Are Related but Distinct Concepts

**HATEOAS** (Hypertext As The Engine Of Application State) is a REST architectural constraint: responses provide hypermedia controls so the client knows where it can go next and what steps it can take. The client starts from a known entry point, reads the links, and follows the link matching its goal; the client does not need to assemble every URL manually according to internal server conventions.

**HAL** (Hypertext Application Language) is a hypermedia representation format for JSON. HAL defines two special properties:

- `_links`: a collection of links grouped by link relation.
- `_embedded`: resources embedded within the current representation, also grouped by relation.

You can think of it as:

- HATEOAS answers **how an API should provide navigability**.
- HAL answers **how links and embedded resources are structured in JSON**.

HAL is one implementation of hypermedia, not the entirety of HATEOAS. An API can use another hypermedia format; conversely, JSON that includes a `_links` field while the client still ignores the links and hard-codes URLs does not fully leverage the HATEOAS idea.

## 2. General Structure of a HAL Representation

A HAL representation can contain links, embedded resources, and the resource's own data:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/people/42"
    },
    "orders": {
      "href": "https://api.example.com/people/42/orders"
    }
  },
  "id": 42,
  "name": "Nguyen An",
  "status": "ACTIVE",
  "_embedded": {
    "department": {
      "id": 7,
      "name": "Engineering",
      "_links": {
        "self": {
          "href": "https://api.example.com/departments/7"
        }
      }
    }
  }
}
~~~

Reading the response above part by part:

1. `_links.self.href` identifies the URI of the Person resource itself.
2. `_links.orders.href` points to the related orders resource. This is a navigation link; the client can call that URI when needed.
3. `id`, `name`, `status` are the business data of Person.
4. `_embedded.department` is the Department representation embedded directly in the response. It has its own data and can have its own `_links`.

The names `_links` and `_embedded` are reserved properties of HAL. Business properties usually sit at the same level alongside them, without needing to be wrapped in a `data` object mandated by HAL. HAL does not require every API to share the same business schema; the schema of fields like `name` and `status` is still defined by the application.

## 3. Structure of _links

`_links` is a JSON object. Each key is a **link relation** (relation name); its value describes one link or multiple links sharing the same relation.

### 3.1. A link object

A link object must have `href`. Other properties may appear depending on the case:

| Property | Meaning |
|---|---|
| `href` | The URI or URI reference that the client can access |
| `templated` | `true` when href is a URI template with variables to substitute; otherwise defaults to false if omitted |
| `type` | Expected media type of the representation at the target link |
| `deprecation` | URI providing information about the link relation being deprecated |
| `name` | Name distinguishing a link when there are multiple links with the same relation |
| `profile` | URI describing the profile of the resource or link |
| `title` | Human-friendly label for presentation to the user |
| `hreflang` | Language of the target resource |

Example:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/people/42",
      "type": "application/hal+json",
      "title": "Person 42"
    }
  }
}
~~~

Clients should treat `href` as a URI published by the server. Do not replace segments manually, guess IDs, or assemble URLs from the relation name. URIs can change when the server changes configuration; the relation is the semantic label indicating what the link is for.

### 3.2. Link relation

A relation indicates the meaning of a link. Some common relations:

| Relation | Common meaning |
|---|---|
| `self` | Current resource |
| `next` | Next page of the collection |
| `prev` | Previous page |
| `first` | First page |
| `last` | Last page |
| `profile` | Related profile/schema descriptive information |
| `search` | Discovery point for search queries |
| `collection` | The collection containing the resource, if the API advertises this relation |

The relation name is a key part of the hypermedia contract. For example, a client can look up the `next` relation to advance without calculating the next page URL itself. An API may use standard relations or domain-specific extension relations.

### 3.3. Multiple links with the same relation

When a relation has multiple links, the value of the relation can be an array:

~~~json
{
  "_links": {
    "alternate": [
      {
        "href": "https://api.example.com/people/42",
        "type": "application/hal+json"
      },
      {
        "href": "https://api.example.com/people/42.csv",
        "type": "text/csv"
      }
    ]
  }
}
~~~

Therefore, clients should not assume every value in `_links` is always a single object. If the API returns an array, the client needs to iterate through the links and can use `type` or `name` to select the appropriate representation.

### 3.4. URI templates and the templated property

Collection endpoints often support query parameters for pagination or sorting. The server may publish a URI template:

~~~json
{
  "_links": {
    "self": {
      "href": "https://api.example.com/people{?page,size,sort}",
      "templated": true
    }
  }
}
~~~

`templated: true` informs the client that href contains template variables. The client needs to expand the template according to URI Template rules before sending the request, for example filling in `page=0` and `size=20`. If `templated` is not true, use href as a complete URI.

### 3.5. CURIEs for extension relations

HAL supports CURIEs (Compact URIs) to shorten extension relation names. Example:

~~~json
{
  "_links": {
    "curies": [
      {
        "name": "ex",
        "href": "https://api.example.com/rels/{rel}",
        "templated": true
      }
    ],
    "ex:manager": {
      "href": "https://api.example.com/people/42/manager"
    }
  }
}
~~~

The `ex:manager` relation is explained through the CURIE named `ex`. Clients can use this relation name as a semantic identifier; do not treat it as a URL path itself.

## 4. Structure of _embedded

`_embedded` contains representations of other resources included in the current response. Each key in `_embedded` is the relation of the embedded resource.

The value can be a single resource object:

~~~json
{
  "_embedded": {
    "department": {
      "id": 7,
      "name": "Engineering",
      "_links": {
        "self": {
          "href": "https://api.example.com/departments/7"
        }
      }
    }
  }
}
~~~

Or an array of resources, commonly seen when embedding a collection:

~~~json
{
  "_embedded": {
    "people": [
      {
        "id": 42,
        "name": "Nguyen An",
        "_links": {
          "self": {
            "href": "https://api.example.com/people/42"
          }
        }
      },
      {
        "id": 43,
        "name": "Tran Binh",
        "_links": {
          "self": {
            "href": "https://api.example.com/people/43"
          }
        }
      }
    ]
  }
}
~~~

Each embedded resource can contain its own business data, its own `_links`, and even nested `_embedded`. This allows clients to display part of a relationship directly from the response without sending extra requests for each item.

### 4.1. How do links and embedded differ?

| Criterion | `_links` | `_embedded` |
|---|---|---|
| Purpose | Advertises URIs for navigation | Includes representations of related resources in the response |
| Content | Link object containing href and metadata | Resource object or array of resources |
| Business data | Usually does not contain data of the target resource | May contain business fields of the embedded resource |
| Request cost | Client sends a separate request when following the link | Data is already present in the current response |
| Presence | Only contains relations advertised by the server | Only contains resources the server chooses to embed |

An association link does not mean the target resource has been embedded. For example, Person has a `department` link pointing to Department, yet the response has no `_embedded.department`. In that case, the client must follow the link if it needs Department data.

Conversely, a resource can appear in `_embedded` for quick client display while still having a `self` link for direct access later. Embedded data is a representation at the time the response was generated; clients should not treat it as an always-synchronized copy.

### 4.2. _embedded is optional

Not every HAL response has `_embedded`. If the server only returns links, the client can still navigate using those links. Clients should also not assume every association is embedded, or that every collection always returns the same embedded structure when projections, configuration, or resource types change.

## 5. Where Does Business Data Live?

Business fields describing the current resource usually live at the top level of the representation, alongside `_links` and `_embedded`.

Example of a Person resource:

~~~json
{
  "id": 42,
  "firstName": "An",
  "lastName": "Nguyen",
  "email": "an@example.com",
  "active": true,
  "_links": {
    "self": {
      "href": "https://api.example.com/people/42"
    },
    "department": {
      "href": "https://api.example.com/people/42/department"
    }
  }
}
~~~

In this example:

- `id`, `firstName`, `lastName`, `email`, `active` are business data.
- `_links.self` points to the current Person.
- `_links.department` points to the Department association.

HAL does not define the meaning or data types of `firstName`, `email`, or `active`; that belongs to the API/domain model. HAL only reserves special names such as `_links` and `_embedded` for representing hypermedia.

Avoid naming business fields the same as HAL's reserved properties. If you need a nested business object, design it according to your application's domain schema rather than confusing that object with an embedded resource keyed by a relation in `_embedded`.

## 6. How Does Spring Data REST Typically Represent Resources?

Spring Data REST uses Spring HATEOAS to build representations with links. When working with a Spring Data REST API, you can start from the root resource, then follow collection, item, search, or association links.

The example responses below are illustrative; actual relation names, base paths, pagination metadata, and embedded content depend on application configuration.

### 6.1. Root resource

Request:

~~~http
GET /api
Accept: application/hal+json
~~~

The response may advertise collections:

~~~json
{
  "_links": {
    "people": {
      "href": "https://api.example.com/api/people"
    },
    "departments": {
      "href": "https://api.example.com/api/departments"
    },
    "profile": {
      "href": "https://api.example.com/api/profile"
    }
  }
}
~~~

The client reads the `people` relation to find where the Person collection is located. If the server changes the base path or collection path, the client can still start from the root and use the new link.

### 6.2. Collection resource

Request:

~~~http
GET /api/people?page=0&size=20
Accept: application/hal+json
~~~

A typical collection response:

~~~json
{
  "_embedded": {
    "people": [
      {
        "firstName": "An",
        "lastName": "Nguyen",
        "_links": {
          "self": {
            "href": "https://api.example.com/api/people/42"
          }
        }
      },
      {
        "firstName": "Binh",
        "lastName": "Tran",
        "_links": {
          "self": {
            "href": "https://api.example.com/api/people/43"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.com/api/people{?page,size,sort}",
      "templated": true
    },
    "profile": {
      "href": "https://api.example.com/api/profile/people"
    },
    "search": {
      "href": "https://api.example.com/api/people/search"
    },
    "next": {
      "href": "https://api.example.com/api/people?page=1&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 37,
    "totalPages": 2,
    "number": 0
  }
}
~~~

In this response:

- `_embedded.people` contains the Person resources for the current page.
- Each Person has its own `self` link to open the item.
- `_links.self` points to the collection and indicates the query parameters that can be varied.
- `_links.search` helps clients discover query resources.
- `_links.next` indicates the next page.
- `page` is pagination metadata that Spring Data REST typically provides for paged collections.

Clients should not calculate the next page path manually if the response already provides the `next` relation. When `next` is absent, the client understands that the server is not advertising a next page in the current state.

### 6.3. Item resource

Request:

~~~http
GET /api/people/42
Accept: application/hal+json
~~~

Illustrative response:

~~~json
{
  "firstName": "An",
  "lastName": "Nguyen",
  "email": "an@example.com",
  "_links": {
    "self": {
      "href": "https://api.example.com/api/people/42"
    },
    "department": {
      "href": "https://api.example.com/api/people/42/department"
    }
  }
}
~~~

Person fields sit at the root; the Department association link is advertised in `_links`. If the server does not embed Department, the client calls the `department` link when related information is needed. If a projection or configuration enables embedding, the representation may additionally contain `_embedded.department`.

### 6.4. Media type

HAL JSON is commonly exchanged with the media type:

~~~http
Accept: application/hal+json
~~~

The corresponding HAL response usually has:

~~~http
Content-Type: application/hal+json
~~~

The media type helps client and server agree on the representation format. When debugging, check both the JSON body and the Content-Type header; plain JSON does not necessarily follow the HAL structure.

## 7. Customizing Relations in Spring Data REST

The relation name seen by clients can be controlled with annotations. Example:

~~~java
@RepositoryRestResource(
    path = "people",
    collectionResourceRel = "people"
)
public interface PersonRepository
        extends JpaRepository<Person, Long> {
}
~~~

Here:

- `path = "people"` defines the collection path.
- `collectionResourceRel = "people"` sets the collection relation advertised in hypermedia.

For query methods, `@RestResource` can set the path and relation:

~~~java
@RestResource(path = "by-last-name", rel = "byLastName")
Page<Person> findByLastName(
        @Param("lastName") String lastName,
        Pageable pageable);
~~~

Clients will discover the query via the search resource and follow the relation/path published by the server. When changing a relation, treat it as a change to the hypermedia contract used by clients; update clients to the new relation or maintain compatibility if versioning is required.

Projections and excerpts can also alter which fields are serialized or how associations are presented. Therefore, do not assume every entity always has the exact same list of business fields or the exact same `_embedded` structure.

## 8. How Clients Should Read and Navigate HAL

A HATEOAS client should follow this workflow:

1. Call a known entry point, such as `/api`.
2. Read `_links` and find the relation corresponding to the goal, such as `people`.
3. Send a request to that relation's `href`.
4. Read the business fields to display the data.
5. If related resources are needed, check `_embedded` first; if the data is not there, look up the corresponding relation in `_links` and follow href.
6. For collections, follow `next`, `prev`, `first`, or `last` if provided.
7. For query resources, follow the `search` link and the query links advertised by the server.

Example navigation logic:

~~~text
GET /api
   |
   +-- _links.people.href
             |
             v
       GET collection
             |
             +-- _embedded.people -> display list
             |
             +-- _links.next -> next page
             |
             +-- _links.search -> discover queries
~~~

Clients should rely on the returned relations and hrefs, not on URL-building conventions like `/people/{id}/department`. This allows the server to change paths without forcing clients to know internal route structures.

When reading a templated link, clients must check `templated`. When a relation returns an array, clients must handle multiple links. When `_embedded` is absent, clients can still use links to fetch resources.

## 9. Common Mistakes When Reading HAL

| Misconception | Correct understanding |
|---|---|
| Treating `_links` as business data | These are navigation metadata; business fields reside in the resource's properties |
| Treating `href` as a fixed route name | Use the URI published by the server; do not construct paths manually |
| Assuming every relation has a single link object | A relation can contain an array of multiple links |
| Assuming all related resources are in `_embedded` | Embedding is optional; a resource may only be advertised via a link |
| Treating `_embedded` as a live synchronized copy of the database | It is a representation embedded at the time of the response |
| Ignoring `templated` | URI templates must be expanded before calling |
| Treating HAL as a business schema | HAL defines hypermedia structure; domain fields are decided by the application |
| Hard-coding URLs and ignoring relations | Clients will easily break when the server changes paths or base paths |

## 10. Response Debugging Checklist

When a client does not read a Spring Data REST response as expected, check:

1. Did the request use an appropriate Accept header, such as `application/hal+json`?
2. Is the response Content-Type HAL JSON?
3. Does the body contain `_links`? What is the target relation named?
4. Is the relation's value an object or an array?
5. Does the link have `templated: true`? If so, did the client expand the URI template?
6. Is the related resource in `_embedded` or only linked in `_links`?
7. Does the collection relation match the configured `collectionResourceRel`?
8. Does a projection/excerpt alter the fields or embedded associations?
9. Is the client hard-coding URLs instead of following href from the response?

A quick check is to send a request with the header:

~~~bash
curl -H "Accept: application/hal+json" https://api.example.com/api/people
~~~

Then inspect the business fields, `_links`, `_embedded`, media type, and pagination metadata together.

## 11. Key Takeaways

- **HATEOAS** is the principle of driving application navigation through hypermedia controls.
- **HAL** is a JSON format standardizing how links and embedded resources are represented.
- **`_links`** indicates where you can go and the relation of each link.
- **`_embedded`** contains representations of embedded related resources.
- **Business fields** describe the current resource and are defined by the domain/API.
- Clients should start from an entry point, read relations, follow hrefs, and handle URI templates; they should not rely on manually constructed URLs.

## References

- [HAL — Hypertext Application Language](https://datatracker.ietf.org/doc/html/draft-kelly-json-hal)
- [Spring HATEOAS Reference](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [Spring Data REST Reference](https://docs.spring.io/spring-data/rest/reference/)
