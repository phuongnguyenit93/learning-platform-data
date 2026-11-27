# Discovering Exported Projections via Metadata

Spring Data REST allows a resource to be represented from multiple perspectives. A projection can return only a required subset of properties, inline a relationship into the response, or compute derived properties. When an API provides multiple projections, clients need to know which options are exposed and how to request each one.

Spring Data REST provides metadata following the Application-Level Profile Semantics (ALPS) standard. Clients can follow hypermedia links to retrieve repository metadata, read the projections listed under the `GET` operation, and pass the projection name as a query parameter. This enables clients to discover the API from server-advertised links instead of guessing projection names.

## 1. What Is a Projection?

A projection is a way of defining a representation of a domain object. Instead of always returning the entire default view, the server can provide a projection tailored to a client's needs.

For example, a `Person` resource has `firstName`, `lastName`, and `address` properties. A list view only needs a person's name and does not need the address. A projection can limit the representation to `firstName` and `lastName`.

A projection is typically declared using a Java interface and the `@Projection` annotation:

~~~java
import org.springframework.data.rest.core.config.Projection;

@Projection(name = "noAddresses", types = { Person.class })
public interface NoAddresses {

    String getFirstName();

    String getLastName();
}
~~~

In the example:

- `@Projection` marks the interface as a projection recognized by Spring Data REST.
- `name` is the public name clients use when requesting the projection.
- `types` specifies the domain types to which the projection applies.
- Getters define the data included in the representation.

The interface name is `NoAddresses`, while the public projection name is `noAddresses`. Clients must use the value of the `name` attribute in the annotation, rather than deriving it from the interface name.

A projection can also add derived data using `@Value` and SpEL, or display a nested relationship inline inside the representation. Therefore, metadata not only indicates that a projection exists, but also describes the properties that the projection declares.

## 2. ALPS Metadata in Spring Data REST

ALPS stands for Application-Level Profile Semantics. It is a compact metadata format used to describe the semantics of a REST application, including representation properties and the REST operations supported by a resource.

Spring Data REST provides one ALPS document for each exported repository. The metadata describes the repository's REST transitions and properties. When projections exist, those options are also advertised in the metadata.

Distinguish two media types:

| Media type | Content |
|---|---|
| `application/hal+json` | HAL representation containing resource data and hypermedia links |
| `application/alps+json` | ALPS metadata describing properties, operations, and projection options |

HAL helps clients find their way through the API. ALPS describes the semantics of the resources and operations that clients can use. A HAL response can contain a `profile` link leading to the ALPS document.

## 3. Discovering Metadata from the Root Resource

Start by calling the root endpoint of the Spring Data REST application:

~~~http
GET / HTTP/1.1
Host: localhost:8080
Accept: application/hal+json
~~~

Example response:

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

The `profile` link is the starting point for metadata discovery. Clients should read the `href` value from the actual response, because base paths, hosts, and repository paths can vary across environments.

Use `curl` to read the root resource:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/
~~~

The root resource only advertises a single general `profile` link. It does not directly contain detailed metadata for all repositories. Follow the `href` of the `profile` link next.

## 4. Listing Profiles for Each Repository

Call the profile endpoint:

~~~http
GET /profile HTTP/1.1
Host: localhost:8080
Accept: application/hal+json
~~~

Example response:

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

Each link in this response leads to the metadata for one repository. In the example, the profile for the `persons` repository is at `/profile/persons`. The profile for `addresses` is at `/profile/addresses`.

The `/profile/{repository}` paths in the example are generated from the repository resources exported by the application. When writing a generic client used across multiple applications, follow the `href` returned by `/profile` rather than hard-coding repository names or assembling URLs manually.

Command to read the profile list:

~~~bash
curl -i -H "Accept: application/hal+json" http://localhost:8080/profile
~~~

Note: `/profile` is a navigational resource pointing to each repository's metadata. It is not yet the ALPS document describing specific properties and projections.

## 5. Reading a Repository's ALPS Document

Follow the `persons` link from the `/profile` response to retrieve the metadata:

~~~http
GET /profile/persons HTTP/1.1
Host: localhost:8080
Accept: application/alps+json
~~~

Example using `curl`:

~~~bash
curl -i -H "Accept: application/alps+json" http://localhost:8080/profile/persons
~~~

The ALPS document has a `descriptors` structure. Part of the document may look like this:

~~~json
{
  "version": "1.0",
  "descriptors": [
    {
      "id": "person-representation",
      "descriptors": [
        { "name": "firstName", "type": "SEMANTIC" },
        { "name": "lastName", "type": "SEMANTIC" },
        { "name": "id", "type": "SEMANTIC" },
        { "name": "address", "type": "SAFE" }
      ]
    },
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
                { "name": "address", "type": "SEMANTIC" },
                { "name": "firstName", "type": "SEMANTIC" },
                { "name": "lastName", "type": "SEMANTIC" }
              ]
            },
            {
              "name": "noAddresses",
              "type": "SEMANTIC",
              "descriptors": [
                { "name": "firstName", "type": "SEMANTIC" },
                { "name": "lastName", "type": "SEMANTIC" }
              ]
            }
          ]
        }
      ]
    }
  ]
}
~~~

This is an abridged illustrative snippet. Actual metadata may include additional descriptors for create, update, delete, item resources, collection resources, and other properties.

Reading the key parts:

- `version` indicates the ALPS structure version.
- `person-representation` describes the properties of the default representation.
- `get-persons` describes the `GET` operation on the `persons` collection.
- `type = SAFE` denotes a safe transition, such as `GET`.
- `rt` references the resource type described by the `person-representation` descriptor.
- `descriptors` inside `get-persons` contains options for the `GET` operation.
- `projection` is a descriptor representing the query option used to select a projection.
- Descriptors nested inside `projection` are the exported projection names.
- Child descriptors of each projection indicate the properties provided by that projection.

In the example, the client finds two projections: `inlineAddress` and `noAddresses`. The `noAddresses` projection provides `firstName` and `lastName`; `inlineAddress` additionally provides `address`.

## 6. Identifying Projections in ALPS

When parsing ALPS, do not simply search for projection name strings anywhere in the document. Identify the corresponding `GET` operation first, then locate the descriptor named `projection` inside that operation.

A generalized structure:

~~~text
descriptors
  └── get-persons
       └── descriptors
            └── projection
                 ├── inlineAddress
                 │    ├── address
                 │    ├── firstName
                 │    └── lastName
                 └── noAddresses
                      ├── firstName
                      └── lastName
~~~

You can read the metadata in the following order:

1. Find the operation descriptor with `id` equal to `get-persons` when discovering a collection resource.
2. Find the child descriptor with `name` equal to `projection`.
3. Extract the list of projections from `projection.descriptors`.
4. Read the `name` of each projection to obtain the query parameter value.
5. Read the `descriptors` inside each projection to understand the properties provided by the representation.

Item resource metadata may contain the `get-person` operation. ALPS can expose projections under both collection `GET` and item `GET`. When looking up projections for a specific resource type, inspect the operation matching the endpoint the client is about to call.

Common types in ALPS:

| Type | Meaning |
|---|---|
| `SEMANTIC` | Data or state element in a representation |
| `SAFE` | Safe transition, typically `GET` or `HEAD` |
| `IDEMPOTENT` | State-changing transition that is idempotent, such as `PUT` or `DELETE` |
| `UNSAFE` | Non-idempotent transition, typically `POST` |

The type helps clients understand the nature of the transition. It does not replace reading business documentation or checking actual access permissions.

## 7. Requesting a Projection After Discovery

After reading the metadata and finding the `noAddresses` projection, the client can append the `projection` query parameter to the resource URI.

For an item resource:

~~~http
GET /persons/1?projection=noAddresses HTTP/1.1
Host: localhost:8080
Accept: application/hal+json
~~~

For a collection resource:

~~~http
GET /persons?projection=noAddresses HTTP/1.1
Host: localhost:8080
Accept: application/hal+json
~~~

You can test with `curl`:

~~~bash
curl -i -H "Accept: application/hal+json" "http://localhost:8080/persons/1?projection=noAddresses"
~~~

The name `noAddresses` must match `name` in `@Projection`. It is not the interface name `NoAddresses`.

When a resource has exported projections, the `self` link may be a URI template:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/persons/1{?projection}",
      "templated": true
    }
  }
}
~~~

The `{?projection}` expression indicates that the URI accepts the `projection` query parameter. A hypermedia client can use this URI template to expand the link instead of concatenating strings arbitrarily.

If a client requests a projection that is not exported or not registered for that resource, the server may fail to apply the selection. Check the ALPS document, the annotation name, and the projection registration configuration before concluding the endpoint is broken.

## 8. Registering Projections So Metadata Can Expose Them

A projection only appears in metadata when Spring Data REST detects and registers it.

There are two common ways:

**Approach 1: Place the interface in the same package or a sub-package of the domain type**

Spring Data REST automatically discovers interfaces annotated with `@Projection` located in the same package as the entity or in a sub-package. For example:

~~~text
com.example.people
  ├── Person.java
  ├── PersonRepository.java
  └── projection
       └── NoAddresses.java
~~~

If `Person` is in `com.example.people`, placing `NoAddresses` in `com.example.people.projection` is a discoverable location.

**Approach 2: Manual registration**

You can register projections via `ProjectionConfiguration` on `RepositoryRestConfiguration`:

~~~java
@Configuration
public class RestConfiguration implements RepositoryRestConfigurer {

    @Override
    public void configureRepositoryRestConfiguration(
            RepositoryRestConfiguration config,
            CorsRegistry cors) {

        config.getProjectionConfiguration()
            .addProjection(NoAddresses.class);
    }
}
~~~

The interface must still carry the `@Projection` annotation. Manual registration is useful when the projection is outside the packages scanned by default discovery.

If a projection does not appear in ALPS:

- Verify the interface has `@Projection`.
- Verify `name` and `types` match the domain type.
- Check that the interface is in the same package or sub-package as the entity, or has been manually registered.
- Check whether the corresponding repository is exported.
- Restart the application after changing configuration and re-read metadata from the running server.
- Ensure the client is accessing the right environment and the right repository profile link.

## 9. How Do ALPS and JSON Schema Differ?

Spring Data REST provides multiple metadata formats. ALPS focuses on resource semantics, REST transitions, and projection choices. JSON Schema focuses on data structure, property types, and constraints usable for validation.

You can request JSON Schema from a repository's profile link using this header:

~~~http
GET /profile/persons HTTP/1.1
Host: localhost:8080
Accept: application/schema+json
~~~

Example:

~~~bash
curl -i -H "Accept: application/schema+json" http://localhost:8080/profile/persons
~~~

Do not confuse JSON Schema with ALPS:

- To discover `GET` operations and projection names, read ALPS.
- To inspect data types and property structures, read JSON Schema.
- To find resource paths and metadata links, read the hypermedia links in HAL responses.

The same profile `href` can serve different metadata representations depending on the `Accept` header. Therefore, set the media type matching the information the client needs.

## 10. Projection vs. Excerpt Projection

A projection is explicitly requested via the `projection` query parameter. Clients can select a representation for a specific request.

An excerpt projection is a projection configured as the default representation when Spring Data REST embeds resources inside a collection or related resource. It is typically configured on the repository via `excerptProjection` on `@RepositoryRestResource`.

Example:

~~~java
@RepositoryRestResource(excerptProjection = NoAddresses.class)
public interface PersonRepository extends CrudRepository<Person, Long> {
}
~~~

An excerpt projection is used for resources embedded inside collections or relationships. It is not automatically applied to an item resource when a client `GET`s a single person directly; to apply a projection to an item resource, the client must request it explicitly.

Understanding this distinction avoids confusion when a collection response contains different properties than a direct `GET` on an item.

## 11. Limitations and Security Considerations When Using Metadata

ALPS is a description of the published API, not a copy of runtime data. Metadata indicates which projections and properties are described, but does not guarantee that every request will be permitted. Authentication, authorization, validation, and business rules remain under server control.

In particular, a projection can include a property in a response even if that property is marked `@JsonIgnore` on the entity. Therefore, never rely on `@JsonIgnore` as the sole security barrier if the application also uses projections.

When designing projections:

- Do not define getters that return passwords, tokens, secrets, or sensitive internal data.
- Review every property included in a projection, including nested properties and derived SpEL properties.
- Enforce access control on the server; do not rely on a client not showing a projection in the UI.
- Expose only projections that consumers actually need.
- Re-read ALPS after changing projections to confirm the metadata reflects the registered choices accurately.

Metadata can also change when repositories, domain models, or REST configurations change. Clients should discover links and metadata from the server rather than hard-coding projection lists in source code when the API may evolve.

## 12. Projection Discovery Workflow for Clients

A client can implement the following general workflow:

1. Call the root resource with `Accept: application/hal+json`.
2. Read `_links.profile` and follow its `href`.
3. Read `/profile` to obtain the metadata link for the target repository.
4. Call the repository profile with `Accept: application/alps+json`.
5. Locate the appropriate `GET` operation for the collection or item resource.
6. Locate the `projection` descriptor inside that operation.
7. Read the projection names and their nested property descriptors.
8. Follow the `self` link or resource link and expand the `projection` query parameter using the exact advertised name.
9. Read the HAL response and process the returned representation.
10. If data types and schema structure are needed, request JSON Schema separately with `Accept: application/schema+json`.

This workflow allows clients to self-discover representation options from server metadata, reducing reliance on hard-coded settings and supporting hypermedia APIs.

## 13. Practical Checklist

- [ ] Root response includes a `profile` link.
- [ ] Followed the profile `href` instead of guessing URLs.
- [ ] `/profile` includes a link to the target repository's metadata.
- [ ] Requested ALPS with `application/alps+json`.
- [ ] Located the right `GET` operation for the collection or item.
- [ ] Located the `projection` descriptor and its child descriptors.
- [ ] Extracted the projection name from metadata.
- [ ] `projection` query parameter uses the exact `@Projection(name = ...)` value.
- [ ] Verified the actual projection response.
- [ ] Reviewed projections to ensure no sensitive data is leaked.

## 14. Conclusion

Spring Data REST advertises projections in the ALPS metadata of each repository. Clients start from the `profile` link at the root, navigate to the repository profile, read the `projection` descriptor inside the `GET` operation, and extract the listed projection names. Clients then pass that name in the `projection` query parameter to receive the desired representation.

Remember three key points: HAL provides discovery paths, ALPS describes projection options, and JSON Schema describes data structure. Metadata helps clients understand the API, while the server remains responsible for enforcing access control and protecting sensitive data.

## References

- [Spring Data REST Reference — Metadata](https://docs.spring.io/spring-data/rest/reference/metadata.html): profile links, ALPS descriptors, projection metadata, and JSON Schema.
- [Spring Data REST Reference — Projections and Excerpts](https://docs.spring.io/spring-data/rest/reference/projections-excerpts.html): `@Projection` declarations, `projection` query parameters, registration methods, and security notes.
- [RFC 6906 — The 'profile' Link Relation Type](https://www.rfc-editor.org/rfc/rfc6906): semantics of the `profile` link relation.
- [ALPS Specification](https://alps.io/spec/): structure and semantics of Application-Level Profile Semantics.
