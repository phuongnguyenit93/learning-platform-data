# Impact of Changing rels and Representation Structure on Spring Data REST Clients

Spring Data REST publishes repositories as REST resources and uses hypermedia links to guide clients in discovering capabilities. In a HAL representation, a relation name (rel) indicates what a link means; the JSON structure describes how data and related resources are presented.

When a rel or representation structure changes, the API may still return HTTP 200, yet existing clients break because they can no longer find links, read collections, or map properties. Therefore, rels and representations are part of the API contract that clients depend on.

## 1. What Role Does rel Play in HAL?

HAL represents links inside the _links property. Each key in _links is a relation, while its value typically contains href and may include additional metadata such as templated.

Example:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/people"
    },
    "search": {
      "href": "http://localhost:8080/people/search"
    },
    "profile": {
      "href": "http://localhost:8080/profile/people"
    }
  }
}
~~~

In the example:

- self points to the current resource itself.
- search indicates where to discover search methods.
- profile points to the resource's profile description.

Clients can look up links by relation instead of assembling URLs manually. This lets the server change the host, context path, or concrete paths while clients can still discover endpoints from the root resource.

HAL includes standard relations such as self, next, prev, first, and last, as well as application-defined relations. Custom relations should have stable names and clear meanings so clients understand the capability each link provides.

## 2. Where Does Spring Data REST Publish rels?

Spring Data REST uses relations in both the links section and the embedded resources section.

### Relations in _links

Navigation links reside in _links. For example, a query method can be published in a search resource:

~~~java
public interface PersonRepository extends CrudRepository<Person, Long> {

    @RestResource(path = "by-last-name", rel = "byLastName")
    List<Person> findByLastName(@Param("lastName") String lastName);
}
~~~

With the /people collection resource, the search resource may return:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/search"
    },
    "byLastName": {
      "href": "http://localhost:8080/people/search/by-last-name{?lastName}",
      "templated": true
    }
  }
}
~~~

The client looks up the byLastName relation, fills in the lastName variable in the URI template, and calls the endpoint. rel is the link name in HAL; path is the URL segment of the endpoint. Changing rel can alter the key in _links even if href stays unchanged.

### Relations in _embedded

When HAL embeds child resources, the key in _embedded is also a relation. Example:

~~~java
@RepositoryRestResource(
    path = "people",
    collectionResourceRel = "people"
)
public interface PersonRepository extends CrudRepository<Person, Long> {
}
~~~

A collection response may look like:

~~~json
{
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
  "_links": {
    "self": {
      "href": "http://localhost:8080/people"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 1,
    "totalPages": 1,
    "number": 0
  }
}
~~~

Here, collectionResourceRel = "people" determines the relation used to represent the collection in HAL. Clients typically read the list from _embedded.people. If this relation changes to persons, the collection may be presented under _embedded.persons; a client still reading _embedded.people will fail to find the list.

_links and _embedded serve two different purposes: _links provides paths for navigation, whereas _embedded contains representations of related resources directly in the response.

## 3. How Does Changing rel Affect Clients?

Suppose the initial version of the API publishes a finder as follows:

~~~java
@RestResource(path = "by-last-name", rel = "byLastName")
List<Person> findByLastName(@Param("lastName") String lastName);
~~~

Existing clients may look up _links.byLastName to invoke the search feature. Later, the server changes the relation:

~~~java
@RestResource(path = "by-last-name", rel = "peopleByLastName")
List<Person> findByLastName(@Param("lastName") String lastName);
~~~

The endpoint path remains /people/search/by-last-name, but the link key changes from byLastName to peopleByLastName.

Clients depending on the old relation may encounter these issues:

- Failing to find _links.byLastName and skipping the search feature.
- Raising an error when the application requires a mandatory relation.
- Constructing URLs manually from old conventions and calling the wrong endpoint.
- Being unable to discover the feature even though the server is operating normally.

Similarly, changing collectionResourceRel can prevent clients from finding the collection in _embedded. This change directly affects how clients read data.

### Changing rel vs. changing path

| Change | Typical impact |
|---|---|
| Changing a finder's rel | The link key in _links changes |
| Changing collectionResourceRel | The collection's relation in HAL, typically the key in _embedded, changes |
| Changing path | The URL in href changes |
| Changing @Param | The variable/query parameter name in the URI template changes |
| Changing representation shape | The data structure parsed by the client can change |

A single change can affect multiple parts at once. For instance, changing both path and rel forces clients both to look up a new relation and to use a new URI if they were hard-coding URLs.

## 4. How Does Changing Representation Structure Affect Clients?

A representation is the resource content returned by the server. With Spring Data REST and HAL, responses typically combine domain data, links, and metadata.

An item resource may look like:

~~~json
{
  "firstName": "An",
  "lastName": "Nguyen",
  "active": true,
  "_links": {
    "self": {
      "href": "http://localhost:8080/people/1"
    },
    "orders": {
      "href": "http://localhost:8080/people/1/orders"
    }
  }
}
~~~

Clients may depend on field names, data types, nested structures, and how associations are represented. The following changes can break clients:

- Renaming a property: changing lastName to familyName causes clients reading lastName to receive missing values.
- Changing data type: turning a numeric field into a string can cause deserialization or calculations to fail.
- Changing nesting structure: turning a single value into an object or an object into an array alters data access paths.
- Changing how associations are embedded: data previously read directly from _embedded might become only a link in _links, or vice versa.
- Changing projections: responses may add, remove, or alter the properties selected for presentation.
- Changing collection structure: changes to the list relation, item content, or pagination metadata can affect list views and navigation logic.

For example, a client reading:

~~~javascript
const people = response._embedded.people;
const lastName = people[0].lastName;
~~~

If the collection relation switches to persons, or the lastName property is renamed, the code above no longer works as before.

## 5. Projections and Associations Can Alter Representations

Spring Data REST supports projections to restrict which properties appear in a representation. Example:

~~~java
@Projection(name = "personSummary", types = Person.class)
public interface PersonSummary {

    String getFirstName();

    String getLastName();
}
~~~

Clients can request a projection if permitted by the endpoint and configuration:

~~~http
GET /people/1?projection=personSummary
Accept: application/hal+json
~~~

A projected representation may contain only the properties defined in the interface. If the server changes the default projection or alters the projection's getters, clients relying on old fields may no longer be able to read the data.

Associations also require attention. Spring Data REST typically represents relationships between entities as links so clients can navigate to related resources. When using an appropriate projection or embedding configuration, association data may appear directly inside the representation. Clients need to know whether they are receiving a link or an embedded object and handle the corresponding form properly.

For example, an association link:

~~~json
{
  "_links": {
    "address": {
      "href": "http://localhost:8080/people/1/address"
    }
  }
}
~~~

Differs from embedded association data:

~~~json
{
  "_embedded": {
    "address": {
      "city": "Hanoi",
      "country": "Vietnam"
    }
  }
}
~~~

A client accessing address.city directly cannot use the same access pattern when the server returns only the address link. When receiving a link, the client must follow the link to fetch the representation of the related resource.

## 6. Impact on Clients Using HAL and HATEOAS

HATEOAS clients are designed to discover capabilities through links and relations. This approach reduces coupling to concrete URLs, but it does not eliminate the contract between client and server.

Clients still need to know:

- Which relation represents the capability they need to use.
- The media type and representation format provided by the server.
- The data fields required for business logic.
- Data types and handling rules for collections, pagination, and associations.
- How to handle cases where an optional link or property is absent.

For example, a client should discover the next relation to advance pages rather than building a URL by incrementing the page parameter manually:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/people?page=0&size=20"
    },
    "next": {
      "href": "http://localhost:8080/people?page=1&size=20"
    }
  }
}
~~~

If a client constructs URLs itself, it couples to query parameter layout and server conventions. If the client follows the next link, the server can change how pagination URLs are generated without the client needing to know the details.

However, if the next relation is renamed or removed, the client also needs appropriate handling rules. For standard relations, preserve each relation's intended meaning and avoid reusing standard names for unrelated functions.

## 7. Backward-Compatibility Strategies When Changing the API

Before changing a rel or representation, identify which clients are consuming the current contract. A change can impact web apps, mobile apps, integration services, or external consumers.

Several ways to reduce risk:

1. Keep old rels while clients still depend on them. If a new relation name is needed, consider publishing a compatible link during a transition period if design and framework capabilities allow.
2. Keep old paths or provide redirects. When URLs change, consider how to maintain legacy endpoints during a migration window.
3. Add fields additively. Adding optional properties usually has less impact than renaming or removing fields currently used by clients.
4. Avoid abrupt changes to data types and structures. If major changes are needed, consider versioning or a new representation.
5. Clearly document relations and their meanings. API documentation should describe relations, parameters, and corresponding representations.
6. Verify media types. Client and server must agree on how HAL is exchanged, typically using application/hal+json.
7. Verify projections. If clients rely on a specific projection, keep the projection name and required fields stable during the compatibility window.

Not every change can maintain two representations or two relations simultaneously in every configuration. Verify the actual capabilities of Spring Data REST and design versioning if a clear transition phase is needed.

## 8. Designing More Resilient Clients

Clients should process hypermedia flexibly:

- Look up links in _links by relation instead of hard-coding URLs.
- For URI templates, substitute parameters according to the template or use a URI template library.
- Read collections via the relation in _embedded; do not assume every collection always uses the same key name.
- Handle optional fields that may be absent or null.
- Ignore unknown fields during deserialization if the library and contract allow.
- Do not depend on property ordering in JSON.
- Follow association links rather than assuming data is always embedded.
- Distinguish collection responses, item resources, and paged responses.
- Check the media type before applying the corresponding parser.

Example of reading a finder link from HAL:

~~~javascript
const finderLink = response._links?.byLastName;

if (finderLink) {
  const url = finderLink.href;
  // Populate the lastName variable if href is a URI template,
  // then send the request to the completed URL.
}
~~~

This approach lets the client recognize when a feature is not advertised. In a real application, provide an appropriate message or fallback instead of letting property access errors propagate through the entire workflow.

Ignoring unknown fields helps clients tolerate the server adding new properties, but it does not automatically solve cases where the server removes or renames fields the client requires. Similarly, discovering links by rel reduces URL coupling, yet the client still depends on the meaning and stability of relations.

## 9. Contract Testing Between Server and Client

When changing annotations or projections, verify actual responses using integration tests or contract tests.

Scenarios that should be tested:

1. Call the collection endpoint and verify the collection relation in _embedded.
2. Call the search resource and verify the relation of each query method in _links.
3. Check the href, URI template, and query parameters of finders.
4. Call the item endpoint and verify that required properties still have the contracted names, types, and structure.
5. Verify whether associations are represented as links or embedded resources as designed.
6. Verify the projections used by clients.
7. Verify next, prev, first, last links and pagination metadata if the API supports paging.
8. Re-run contract tests for supported clients after changing a rel or representation.

A test that only checks HTTP status 200 is insufficient. A response can succeed while relations or properties have changed, leaving clients unable to perform business workflows.

## 10. Examples of Changes and Their Impact

| Server-side change | Potential client issue |
|---|---|
| rel = "byLastName" changed to rel = "peopleByLastName" | Cannot find the old finder link |
| collectionResourceRel = "people" changed to "persons" | Cannot read _embedded.people |
| path = "by-last-name" changed to "last-name" | Old URL no longer points to the right endpoint |
| @Param("lastName") changed to "familyName" | Query parameter sent by the client no longer matches |
| lastName changed to familyName in JSON | Client deserializes or displays missing last name |
| Association switched from embedded object to link | Client must make an extra request to fetch related data |
| Projection removes firstName | Clients depending on this field lack required data |

## 11. Key Takeaways

- rel names and defines the meaning of a link in HAL; clients typically use relations to discover capabilities.
- _links contains navigation links, while _embedded contains representations of embedded resources.
- Changing a relation can prevent clients from finding finders or collections even when endpoints still respond normally.
- Changing path affects the URL; changing rel affects the link name; changing @Param affects the query parameter name.
- Changing projections, entity properties, or how associations are represented can alter the JSON structure parsed by clients.
- HATEOAS reduces reliance on fixed URLs, but clients still need stable relations and clearly contracted representations.
- Before releasing changes, inspect HAL responses and run contract tests with API consumers.
