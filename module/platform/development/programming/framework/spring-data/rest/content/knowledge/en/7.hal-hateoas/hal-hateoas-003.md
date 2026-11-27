# Representing Item, Collection, and Paged Results in Spring Data REST

## Objectives

Spring Data REST turns exported Spring Data Repositories into REST resources and represents them using hypermedia. When reading the API, you need to recognize three common response forms:

- **Item resource:** represents a single entity, typically accessed via an identifying URI such as \`/people/42\`.
- **Collection resource:** represents a list of entities belonging to a repository, typically at a URI such as \`/people\`.
- **Paged collection:** represents a single page of a collection, along with metadata about the current page and navigation links.

These responses do not contain only domain data. They also contain links describing the current resource, relationships to related resources, and the next steps the client can take. That is the hypermedia part of HATEOAS.

This article focuses on the HAL structure that Spring Data REST typically returns, the meaning of \`_links\`, \`_embedded\`, \`page\`, how to read pagination links, and how clients should navigate the API.

## 1. From repository to REST resource

Suppose the application exports a repository:

~~~java
@RepositoryRestResource(
    collectionResourceRel = "people",
    path = "people"
)
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

With base path \`/api\`, Spring Data REST provides resources of the form:

| URI | Meaning |
|---|---|
| \`GET /api/people\` | Collection resource of the Person repository. |
| \`GET /api/people/42\` | Item resource of the Person with identifier 42. |
| \`GET /api/people/42/manager\` | Resource representing the manager association of Person 42, if the association is exported. |
| \`GET /api/people/search\` | Search resource containing exported query methods, if any. |

These URLs are illustrative examples. Actual URIs depend on the base path, \`@RepositoryRestResource\`, export configuration, and repository metadata.

A request to an item resource and a request to a collection resource serve different purposes. An item resource describes a specific entity. A collection resource describes a set of entities and provides links for the client to open individual items or navigate to another page.

## 2. HAL and hypermedia structure

Spring Data REST typically uses HAL (Hypertext Application Language) as the hypermedia format for JSON responses. Clients can request the media type:

~~~http
Accept: application/hal+json
~~~

HAL defines several special fields:

| Field | Meaning |
|---|---|
| \`_links\` | Links to the current resource, related resources, or navigation actions. |
| \`_embedded\` | Resources embedded in the current representation, commonly used for collection items. |
| \`page\` | Pagination metadata added by Spring Data REST to paged collection representations. |
| Domain properties | Entity data, such as \`id\`, \`firstName\`, \`lastName\`. |

A HAL link typically has the form:

~~~json
{
  "self": {
    "href": "http://localhost:8080/api/people/42"
  }
}
~~~

Where:

- **Relation (rel)** is the relationship name, in this example \`self\`.
- **href** is the URI that the client can call.
- **templated** may appear with the value \`true\` if the URI is a URI template containing variables that need substitution.

The relation name tells the client what the link represents. Clients should rely on the relation and href returned by the server rather than assembling URLs according to guessed naming conventions.

HAL does not require all domain properties to be placed inside \`_embedded\`. An item's data usually resides directly at the top level of the object; \`_embedded\` is used to hold embedded child resources.

## 3. Representing a single item resource

When a client calls:

~~~http
GET /api/people/42
Accept: application/hal+json
~~~

Spring Data REST may return a representation like the following:

~~~json
{
  "id": 42,
  "firstName": "Ada",
  "lastName": "Lovelace",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people/42"
    },
    "addresses": {
      "href": "http://localhost:8080/api/people/42/addresses"
    }
  }
}
~~~

This is an abbreviated example. Specific properties and association links depend on the entity model, repository metadata, and export configuration.

### How to read the response

- \`id\`, \`firstName\`, \`lastName\` are the domain data of Person.
- \`_links.self.href\` points to the current item resource itself.
- \`_links.addresses.href\` points to the addresses association resource of this Person, if the association is exported.
- An association link allows the client to access related resources without knowing the storage structure or URI construction rules beforehand.

An item resource does not need an \`_embedded\` array just to represent that entity itself. It is a single object containing domain properties and relevant links.

### Why is the self link needed?

The \`self\` link gives the client the canonical URI of the resource. The client can store this URI, call it again to retrieve the latest data, or use it as a reference in subsequent operations. This also allows the server to change its base path or URI rules with minimal impact on the client, as long as the client follows the provided links.

### How are associations represented?

Suppose Person has an association to manager. The representation may contain a link like:

~~~json
{
  "id": 42,
  "firstName": "Ada",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people/42"
    },
    "manager": {
      "href": "http://localhost:8080/api/people/42/manager"
    }
  }
}
~~~

The client follows the \`manager\` link to read the association. Depending on configuration and association type, the response of the related endpoint may be an item resource or a collection resource.

By default, an association link does not mean the entire related object is always embedded in the item's response. This keeps representations compact and lets the client fetch related resources only when needed.

## 4. Representing a collection resource

When a client calls:

~~~http
GET /api/people
Accept: application/hal+json
~~~

Spring Data REST returns a collection representation. Example:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/people"
    },
    "profile": {
      "href": "http://localhost:8080/api/profile/people"
    },
    "search": {
      "href": "http://localhost:8080/api/people/search"
    }
  },
  "_embedded": {
    "people": [
      {
        "id": 42,
        "firstName": "Ada",
        "lastName": "Lovelace",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/people/42"
          }
        }
      },
      {
        "id": 43,
        "firstName": "Grace",
        "lastName": "Hopper",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/people/43"
          }
        }
      }
    ]
  }
}
~~~

### Two levels of links

A collection representation has two levels of links:

1. **Collection-level links:** located in the outer \`_links\`. They describe the current collection, profile, or search endpoint.
2. **Item-level links:** located in the \`_links\` of each object inside the \`_embedded.people\` array. They allow opening each specific Person.

The name \`people\` inside \`_embedded\` is the collection relation. It is usually derived from the domain/repository name and can be customized with \`collectionResourceRel\` on \`@RepositoryRestResource\`.

### Meaning of common relations

| Relation | Meaning |
|---|---|
| \`self\` | URI of the current collection. |
| \`profile\` | Link to the resource's profile/metadata description, typically used to discover semantics and structure. |
| \`search\` | Link to the repository's search resource when exported query methods exist. |
| \`people\` | Relation inside \`_embedded\` containing items belonging to the People collection. |

Do not assume every collection always includes both \`profile\` and \`search\`. Link presence depends on configuration, the repository, and exported search methods.

### Empty collection

If no matching entities exist, the collection is still a valid resource. Clients must accept empty collections: the array in \`_embedded\` may be empty, or the \`_embedded\` section may be omitted depending on the representation and version. Do not treat missing items as a response parsing error.

## 5. Representing a paged collection

For large repositories, Spring Data REST typically returns collections page by page. Clients can specify the page and page size:

~~~http
GET /api/people?page=0&size=2&sort=lastName,asc
Accept: application/hal+json
~~~

An illustrative response:

~~~json
{
  "_links": {
    "first": {
      "href": "http://localhost:8080/api/people?page=0&size=2&sort=lastName,asc"
    },
    "self": {
      "href": "http://localhost:8080/api/people?page=0&size=2&sort=lastName,asc"
    },
    "next": {
      "href": "http://localhost:8080/api/people?page=1&size=2&sort=lastName,asc"
    },
    "last": {
      "href": "http://localhost:8080/api/people?page=2&size=2&sort=lastName,asc"
    }
  },
  "_embedded": {
    "people": [
      {
        "id": 42,
        "firstName": "Ada",
        "lastName": "Lovelace",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/people/42"
          }
        }
      },
      {
        "id": 43,
        "firstName": "Grace",
        "lastName": "Hopper",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/people/43"
          }
        }
      }
    ]
  },
  "page": {
    "size": 2,
    "totalElements": 5,
    "totalPages": 3,
    "number": 0
  }
}
~~~

This is an illustrative response for the first page of a 5-element collection with a page size of 2. Actual links and items are generated by the server based on real data.

### Metadata in page

| Field | Meaning |
|---|---|
| \`size\` | The current page size applied. |
| \`totalElements\` | Total number of elements in the collection matching the current query conditions. |
| \`totalPages\` | Total number of available pages. |
| \`number\` | Current page index, starting from 0 by default. |

In the example above:

- \`size = 2\`: each page contains at most two items.
- \`totalElements = 5\`: the full result set has five items.
- \`totalPages = 3\`: three pages are needed to read all results.
- \`number = 0\`: this is the first page.

The \`page\` metadata describes the pagination state of the collection response. It is not a property of the Person entity and does not appear as metadata of a single item resource.

### Navigation links

| Relation | Role |
|---|---|
| \`first\` | First page. |
| \`prev\` | Page immediately preceding the current page. |
| \`self\` | Current page. |
| \`next\` | Next page. |
| \`last\` | Last page. |

Navigation links appear only when appropriate for the page position and result state. For example, the first page usually has no \`prev\`; the last page usually has no \`next\`. A collection with only one page may omit \`next\` or \`last\` links.

Clients should follow the returned \`next\` link to advance pages. Do not increment page numbers manually and construct URIs if the server already provides navigation links.

## 6. Query parameters for pagination and sorting

Spring Data REST supports common query parameters:

| Parameter | Example | Meaning |
|---|---|---|
| \`page\` | \`page=0\` | Page index to read, defaulting to 0. |
| \`size\` | \`size=20\` | Maximum number of items on one page. |
| \`sort\` | \`sort=lastName,asc\` | Sort by property and ascending/descending direction. |

Example:

~~~http
GET /api/people?page=1&size=10&sort=lastName,asc
~~~

This request asks for the second page (index 1), up to 10 items, sorted by \`lastName\` ascending.

You can request multiple sort criteria by repeating the query parameter:

~~~http
GET /api/people?sort=lastName,asc&sort=firstName,desc
~~~

The server applies the sort order according to the requested criteria and what the repository/store module supports.

### Page size limits

The server can enforce a default page size and a maximum limit to prevent a single request from loading too much data. In Spring Boot, this can be configured:

~~~properties
spring.data.rest.default-page-size=25
spring.data.rest.max-page-size=100
~~~

The values above are example configurations. Set limits according to response payload size, query performance, and client needs. If a client requests a \`size\` larger than the limit, the server may cap the actual size; read the returned metadata and links to know the page state in use.

Default parameter names can be customized in \`RepositoryRestConfiguration\`. When a project changes the names of \`page\`, \`size\`, or \`sort\`, clients must use the names published by the actual API.

## 7. Distinguishing item, collection, and page

| Aspect | Item resource | Collection resource | Paged collection |
|---|---|---|---|
| Purpose | A specific entity. | A set of entities. | One page slice of a collection. |
| Example URI | \`/api/people/42\` | \`/api/people\` | \`/api/people?page=1&size=10\` |
| Domain data | Properties of one entity. | Items inside \`_embedded\`. | Items of the current page inside \`_embedded\`. |
| \`_links\` | Self and association links. | Collection, profile, and search links. | Collection links and page navigation links. |
| \`_embedded\` | May exist if the representation embeds related resources; not a mandatory wrapper for the item itself. | Contains the collection items. | Contains the items belonging to the current page. |
| \`page\` | Not used to describe a single item. | May be omitted if not paged. | Contains page size, total items, total pages, and page index. |

A quick way to tell them apart:

- If the response directly contains an entity's properties and has \`_links.self\`, it is usually an item resource.
- If the response has \`_embedded\` with a relation such as \`people\`, it is a collection representation.
- If the collection response also has a \`page\` object and links such as \`next\`, \`prev\`, it is a paged collection.

## 8. Customizing resource relations and paths

The collection relation name and URI can be customized via \`@RepositoryRestResource\`:

~~~java
@RepositoryRestResource(
    collectionResourceRel = "people",
    path = "people"
)
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

The two attributes serve different roles:

- \`path\` determines the URL segment of the collection resource.
- \`collectionResourceRel\` determines the relation name used to embed items in \`_embedded\`.

For example, if you change \`collectionResourceRel\` to \`members\`, clients may see:

~~~json
{
  "_embedded": {
    "members": [
      {
        "id": 42,
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/people/42"
          }
        }
      }
    ]
  }
}
~~~

The URI can still be \`/api/people\`, while the relation name is \`members\`. Clients should not infer the relation from the URL or the Java interface name.

For associations or query methods, \`@RestResource\` can customize the corresponding rel and path:

~~~java
@RestResource(rel = "manager", path = "manager")
Person getManager();
~~~

This is an example of naming the relation for an exported resource. Annotation placement and method signature must match the actual association or query method in the repository.

## 9. HATEOAS: clients should navigate via links

HATEOAS (Hypermedia as the Engine of Application State) treats links in responses as instructions for the client's next state. Clients do not need to know all resource URLs in advance.

A HAL-based client can follow this sequence:

1. Start from the entry point URI published by the application.
2. Read \`_links\` to find the relation leading to the desired collection.
3. Follow the collection's href to load the list.
4. Read \`_embedded\` to obtain the current items.
5. Follow an item's \`self\` link to open a specific entity.
6. Follow association links to load related resources.
7. Follow \`next\` or \`prev\` to change pages.
8. Follow \`search\` to discover query methods published by the repository.

This approach reduces client coupling to how the server organizes URIs. If the server changes the base path or how links are generated, the client can keep working as long as the relations and entry point remain stable.

### Navigation example

Suppose the client receives:

~~~json
{
  "_links": {
    "people": {
      "href": "http://localhost:8080/api/people"
    }
  }
}
~~~

The client reads the \`people\` relation, extracts href, and calls the collection. Then, if the collection returns a \`next\` link, the client follows that exact href to load the next page.

The client does not need to build \`/api/people?page=1\` manually if the server already supplied the \`next\` link. The link returned by the server may carry sort, filter, page size, or other query parameters that the client needs to preserve.

## 10. Using HAL in an HTTP client

Example using curl to fetch an item:

~~~bash
curl -H "Accept: application/hal+json" \
  http://localhost:8080/api/people/42
~~~

Fetching a paged and sorted collection:

~~~bash
curl -H "Accept: application/hal+json" \
  "http://localhost:8080/api/people?page=0&size=10&sort=lastName,asc"
~~~

When reading a response, the client should:

- Check the HTTP status before parsing the body.
- Choose a parser that supports HAL or read HAL fields according to the JSON structure.
- Treat \`_links\` as the set of navigable relations.
- Treat \`_embedded\` as embedded resource content.
- Never assume a collection always contains items.
- Never assume every relation is always present.
- Never hard-code page size or total page count in navigation logic.
- Follow links returned by the server when paging or opening associations.

If using Java and Spring HATEOAS to write a client or custom controller, abstractions like \`EntityModel\`, \`CollectionModel\`, and \`PagedModel\` help represent entities, collections, and pages alongside links. Spring Data REST automatically creates representations for repository endpoints; an application does not need to wrap repository responses in these types just for default exported endpoints to work.

## 11. Projections and item representations

Returned representations can vary depending on projection configuration. A projection lets you define a view consisting of a selected set of properties or associations for cases where clients do not need the full entity data.

When a projection is used, clients may receive additional or altered properties. Therefore:

- Do not treat the JSON response as a verbatim copy of the database entity.
- Rely on profiles, links, and the API contract to understand the representation.
- Verify which projections are exported and how clients request a projection.
- Do not use projections as an authorization mechanism or to hide sensitive data in place of security.

Projections affect representation content; the concepts of item, collection, links, and pagination retain their distinct roles.

## 12. Common mistakes and misconceptions

1. **Looking for entity properties at the wrong JSON level.** For an item resource, properties are usually at the top level; for a collection, items are inside \`_embedded\`.
2. **Treating \`_embedded.people\` as a fixed name.** The relation can be customized via \`collectionResourceRel\`; read the exact key returned by the server.
3. **Assuming \`page.number\` starts at 1.** By default, Spring Data REST uses 0-based page indexing.
4. **Constructing next-page URLs manually.** Use the \`next\` relation to preserve query parameters and URI rules published by the server.
5. **Assuming every response has \`next\` or \`prev\`.** Navigation links depend on page position; the first page, last page, and single-page collections have different sets of links.
6. **Assuming an empty collection is an error.** An empty collection is still a valid response; clients must handle the zero-item case.
7. **Confusing an association link with an embedded object.** A link tells you where to access the association; the client must call href if it wants to read that resource.
8. **Using \`id\` to build URIs instead of following the self link.** URI structures can change; the self link is the reference provided by the server.
9. **Sending an inappropriate media type.** Check the \`Accept\` header and the media types supported by the API, typically \`application/hal+json\` for HAL.
10. **Assuming \`page.size\` always equals the value requested by the client.** The server may apply a default or maximum page size; read the response metadata.
11. **Assuming \`totalElements\` is always the total records in the entire system.** It is the total matching the current collection query/criteria.
12. **Using relation names as Java field names.** A relation is part of the published hypermedia API contract; it can be customized independently of property or repository names.

## 13. Checklist when reading or debugging responses

When a client does not display Spring Data REST data properly, check:

1. Is the request calling an item URI or a collection URI?
2. Does the \`Accept\` header request an appropriate media type, such as \`application/hal+json\`?
3. For an item, are the domain properties at the top level and are the required links in \`_links\`?
4. For a collection, what is the actual relation name inside \`_embedded\`?
5. If the collection is paged, what are the values of \`page.number\`, \`page.size\`, \`page.totalElements\`, and \`page.totalPages\`?
6. Which of the \`first\`, \`prev\`, \`next\`, \`last\` relations are being returned by the server?
7. Is the client following the link's href or constructing URLs manually?
8. Does the repository configure \`collectionResourceRel\`, \`path\`, projections, or association exports that alter the representation?
9. Are any sort/page/size query parameters modified or capped by server configuration?
10. If an association link is missing, is that association exported or hidden by configuration?

When debugging, save the status code, response headers, and body together. A valid JSON body can still carry a media type or status different from what the client expects.

## 14. Client and API design principles

- Use item resources to work with a specific entity.
- Use collection resources to discover and list entities.
- Use page metadata and navigation links to handle large datasets.
- Keep relation names stable as part of the API contract if clients depend on them.
- Let clients navigate via hrefs published by the server.
- Handle empty collections and optional links gracefully.
- Avoid embedding too many associations in a single response if clients only need partial data.
- Choose a page size suited to network latency, response payload size, and query cost.
- Treat projections as a representation selection mechanism, not a security boundary.

## Summary

An item resource represents a single entity with its domain properties and its own links. A collection resource represents multiple items inside \`_embedded\` while providing collection-level links. When a collection is paged, Spring Data REST adds a \`page\` object and navigation relations such as \`first\`, \`prev\`, \`next\`, and \`last\`.

HAL provides the JSON structure for links and embedded resources; HATEOAS guides clients to use those links to discover the API. Clients should read relations, follow hrefs, inspect pagination metadata, and handle optional links instead of relying on guessed URLs.

## References

- [Spring Data REST — Reference Documentation](https://docs.spring.io/spring-data/rest/reference/)
- [Spring Data REST — Configuring the REST URL Path](https://docs.spring.io/spring-data/rest/reference/customizing/configuring-the-rest-url-path.html)
- [Spring Data REST — Paging and Sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html)
- [Spring HATEOAS — Representation Models](https://docs.spring.io/spring-hateoas/docs/current/reference/html/)
- [HAL — Hypertext Application Language](https://stateless.group/hal_specification.html)
