# Reading Repository Metadata, Domain Types, and Available CRUD Methods

## Objective

Spring Data REST generates a REST API from Spring Data repositories. When the application starts, the framework discovers export-eligible repositories, reads repository and domain type metadata, and maps appropriate methods to HTTP resources and operations.

To determine which API actually exists, answer four questions:

1. Which repositories are discovered and exported by Spring Data REST?
2. Which domain type and primary key type does a repository manage?
3. Which read, write, delete, and query methods does the repository have; which methods are hidden?
4. Through which collection resource, item resource, search resource, or association resource are those operations exposed?

Metadata enables discovering the REST contract at runtime. It does not mean every Java method on a repository becomes its own URL.

## 1. Repository metadata and domain types

A Spring Data repository declares its domain type and ID type via two generic parameters. For example:

    public interface PersonRepository extends CrudRepository<Person, Long> {
    }

In this example:

- The repository interface is PersonRepository.
- The domain type is Person: the object type that the repository stores and retrieves.
- The ID type is Long: the identifier type of a Person.
- CrudRepository provides the foundational CRUD operations that Spring Data REST can map to HTTP operations.

Spring Data Commons represents this information through repository metadata. The two most important pieces of information when reading metadata are the domain type and ID type. The domain type describes the object structure represented by the API; the ID type indicates the value type used in each item's URI.

Persistent entity metadata also helps the framework identify properties, the identifier field, and relationships between entities. When returning data, Spring Data REST can represent relationships using hypermedia links instead of always embedding entire related objects in JSON.

Do not confuse these three concepts:

- A repository interface describes how data is accessed.
- A domain type describes the managed business object.
- A REST resource is the HTTP representation that Spring Data REST creates from the repository and domain type.

The repository name does not necessarily dictate the URL. By default, the collection path is derived from the simple name of the domain class, lowercased and pluralized. For example, Person is typically exported as /people, and Order as /orders. Relation names and paths can be changed with annotations.

## 2. Processing flow at application startup

### Step 1 — Discover exported repositories

Spring Data REST locates Spring Data repositories in the application context. Discovery rules are controlled by RepositoryDetectionStrategy.

Common strategies:

| Strategy | Selected repositories |
|---|---|
| DEFAULT | Public repositories or repositories annotated with @RepositoryRestResource, provided exported = false is not set |
| ALL | All Spring Data repositories, regardless of visibility or annotation |
| VISIBILITY | Only public repositories |
| ANNOTATED | Only repositories with @RepositoryRestResource and without exported = false |

By default, a package-private repository is not automatically exported the way a public repository is. Application configuration can alter this detection rule.

You can disable exporting an entire repository with:

    @RepositoryRestResource(exported = false)
    public interface InternalPersonRepository extends CrudRepository<Person, Long> {
    }

### Step 2 — Read metadata and identify the domain type

After selecting a repository, the framework identifies:

- The repository interface and its parent interfaces.
- The domain type, for example Person.
- The ID type, for example Long.
- Available repository methods.
- Persistent entity metadata, including properties and associations that can be represented in the REST resource.

With PersonRepository extends CrudRepository<Person, Long>, the framework knows the collection contains Person and item URIs require an ID of type Long.

### Step 3 — Create resource mappings

From the domain type and repository configuration, Spring Data REST determines the collection resource, item resource, and related resources.

Examples:

- Collection resource: /people
- Item resource: /people/{id}
- Search resource: /people/search
- Association resource: /people/{id}/{association}

Collection names and relations can be customized:

    @RepositoryRestResource(
        path = "people",
        collectionResourceRel = "people"
    )
    public interface PersonRepository extends CrudRepository<Person, Long> {
    }

If path is not declared, the framework uses the default naming rule based on the domain type. Therefore, when checking URLs, rely on returned HAL links instead of guessing paths from the interface name.

### Step 4 — Determine exposable CRUD methods

Spring Data REST inspects the methods provided by the repository and maps them to corresponding REST operations. A repository extending CrudRepository usually has the foundational methods needed to expose CRUD.

An HTTP operation may not appear if the corresponding underlying method does not exist or was disabled via exported = false. For example, if a repository does not expose a delete method supported by Spring Data REST, the item resource will not expose DELETE.

### Step 5 — Handle requests and build responses

When a client sends a request, Spring Data REST selects the matching resource mapping, invokes the corresponding repository method, and converts the result into an HTTP representation. By default, responses use HAL JSON and include links in the _links property.

Clients can use these links to navigate from root to collection, and from collection to item, search, or profile metadata. This is Spring Data REST's hypermedia discovery mechanism.

## 3. Mapping CRUD methods to HTTP

The following table describes common resource mappings. Whether an operation is actually enabled still depends on repository methods, annotations, and exposure configuration.

| Resource | HTTP | Repository method typically used | Meaning |
|---|---|---|---|
| Collection /people | GET | findAll(Pageable), findAll(Sort), findAll() | Read a list of entities |
| Collection /people | POST | save(entity) | Create a new entity |
| Item /people/{id} | GET | findById(id) | Read a single entity |
| Item /people/{id} | PUT | save(entity) | Replace entity state |
| Item /people/{id} | PATCH | save(entity) | Partially update entity |
| Item /people/{id} | DELETE | Corresponding delete method | Delete entity |
| Search /people/search | GET | Exported query methods | List links to queries |
| Query resource | GET | Corresponding query method | Execute query |
| Association resource | GET, PUT, POST, DELETE | Association mapping | Read or modify links between entities |

### Reading a collection

GET on a collection calls the appropriate findAll method. If the repository supports pagination or sorting, Spring Data REST prefers variants in this order:

1. findAll(Pageable)
2. findAll(Sort)
3. findAll()

Common pagination parameters:

- page: page number, zero-based.
- size: number of elements per page.
- sort: property and sort direction, for example sort=lastName,asc.

### Creating an entity

POST on a collection uses the save method to persist a new entity. The request body contains input data in a representation supported by the endpoint. On successful creation, the response typically returns 201 Created; the link to the new entity can be provided via the Location header.

### Reading and updating an item

GET on /people/{id} uses a lookup-by-ID method, typically findById.

PUT replaces the resource state with the submitted data. PATCH updates only part of the state. Both are typically handled via the repository's save method.

### Deleting an item

DELETE on /people/{id} deletes the corresponding entity. Spring Data REST uses an appropriate delete method provided by the repository. Specific method signatures may vary across Spring Data versions; check the actual interface and documentation for the version your project uses.

### Custom queries

Query methods such as findByLastName can be exposed under the search resource. They are read-only endpoints and typically support GET. The search resource returns links to each query method; clients follow a link to invoke the query.

## 4. Discovering metadata over HTTP

You do not need to guess repository names or assemble every URL by hand. Start from the application's root endpoint.

### 4.1 Reading the root HAL resource

Send a GET request to the root URL:

    curl -H "Accept: application/hal+json" http://localhost:8080/

Illustrative response:

    {
      "_links": {
        "people": {
          "href": "http://localhost:8080/people"
        },
        "profile": {
          "href": "http://localhost:8080/profile"
        }
      }
    }

Each key in _links is a relation. href is the actual URL of the resource. In a specific application, relations and URLs may differ due to configuration; use the returned links as the authoritative source.

### 4.2 Reading the profile list

Follow the href of the profile link from the root resource. The profile index contains metadata links for each exported repository.

Example with default configuration:

    curl http://localhost:8080/profile

The response may contain links such as /profile/people and /profile/orders. If the application customizes the profile path, follow the href provided by the root resource.

### 4.3 Reading repository ALPS metadata

Follow a repository's profile link, for example:

    curl -H "Accept: application/alps+json" \
      http://localhost:8080/profile/people

ALPS describes two main groups of information:

- Properties in the domain resource's representation, such as firstName, lastName, id, or associations.
- REST operations exposed by the resource, such as creating in the collection, reading the collection, reading an item, updating an item, and deleting an item.

A descriptor may contain id, name, type, rt, and nested descriptors. In particular:

| Field | Meaning |
|---|---|
| id | Identifier name of the descriptor or operation |
| name | Relation or field name being described |
| type = SEMANTIC | Data element in the representation |
| type = SAFE | Safe state transition, usually corresponding to GET or HEAD |
| type = IDEMPOTENT | Idempotent state-changing operation, usually corresponding to PUT or DELETE |
| type = UNSAFE | Non-idempotent state-changing operation, usually corresponding to POST |
| rt | Resource type returned or referenced by the operation |

For example, a person-representation descriptor may list firstName and lastName. A create-people descriptor may describe the creation operation on the people collection and point to person-representation via rt.

ALPS helps clients understand available REST state transitions and related data fields. If projections exist, metadata may also list valid projections along with the properties each projection returns.

### 4.4 Reading JSON Schema

Spring Data REST can also provide a JSON Schema for a repository's profile. Send a request to the same profile URL with an Accept header:

    curl -H "Accept: application/schema+json" \
      http://localhost:8080/profile/people

JSON Schema describes the data structure in a machine-readable format, for example:

- Domain type name.
- Properties and data types.
- Read-only or writable fields.
- Relationship properties represented as URIs.

ALPS is useful for understanding REST operations and semantics; JSON Schema is useful for understanding data shapes and property types.

## 5. Complete example with PersonRepository

The repository can be declared as follows:

    @RepositoryRestResource(
        path = "people",
        collectionResourceRel = "people"
    )
    public interface PersonRepository extends CrudRepository<Person, Long> {

        @RestResource(path = "by-last-name", rel = "byLastName")
        List<Person> findByLastName(@Param("lastName") String lastName);
    }

Illustrative domain type:

    @Entity
    public class Person {
        @Id
        @GeneratedValue
        private Long id;

        private String firstName;
        private String lastName;
    }

API discovery flow:

1. GET the root URL to find the people and profile links.
2. Follow the people link to read the collection.
3. Follow the people profile link to read ALPS or JSON Schema.
4. Follow the search link in the collection to see exposed query methods.
5. Call the query resource via GET with the lastName parameter.

Example requests:

    curl http://localhost:8080/people
    curl http://localhost:8080/people/search
    curl "http://localhost:8080/people/search/by-last-name?lastName=Nguyen"
    curl http://localhost:8080/people/1

Common write operations:

    curl -X POST http://localhost:8080/people \
      -H "Content-Type: application/json" \
      -d '{"firstName":"An","lastName":"Nguyen"}'

    curl -X PATCH http://localhost:8080/people/1 \
      -H "Content-Type: application/merge-patch+json" \
      -d '{"lastName":"Tran"}'

    curl -X DELETE http://localhost:8080/people/1

These examples assume the application runs at localhost:8080 and the corresponding operations are exported. Payloads and media types must match the domain model, serialization configuration, and the project's Spring Data REST version.

## 6. Controlling exported repositories and methods

Exposure can be adjusted at multiple levels:

- @RepositoryRestResource(exported = false): does not export the repository.
- @RestResource(exported = false): does not expose the corresponding query method, CRUD method, or association.
- @RepositoryRestResource(path = "...", collectionResourceRel = "..."): changes the collection path and relation.
- @RestResource(path = "...", rel = "..."): changes the path and relation of a query method or association.
- RepositoryDetectionStrategy: changes the rule for selecting repositories.
- RepositoryRestConfiguration and RepositoryRestConfigurer: configures exposure at the application, domain type, or resource level.

A Java method can still exist for internal logic even if it is not exposed over HTTP. In particular, save is used for POST on the collection and PUT/PATCH on the item. If you only want to disable one of those HTTP methods, per-resource exposure configuration may be more suitable than hiding the entire save method.

Example disabling PATCH for item resources:

    @Component
    public class RestConfiguration implements RepositoryRestConfigurer {

        @Override
        public void configureRepositoryRestConfiguration(
                RepositoryRestConfiguration config) {

            config.getExposureConfiguration()
                .withItemExposure((metadata, methods) ->
                    methods.disable(HttpMethod.PATCH));
        }
    }

## 7. How to check when an endpoint does not appear

| Symptom | What to check |
|---|---|
| Root lacks repository link | Is the repository discovered; visibility, RepositoryDetectionStrategy, and exported |
| Collection URL differs from expected | Domain type, path in @RepositoryRestResource, and application base path |
| Collection does not support GET | Does the repository have a suitable findAll method and is it exported |
| Collection does not support POST | Does the repository have save and is save hidden |
| Item does not support GET | Does the repository have a suitable findById and is it hidden |
| Item does not support PUT/PATCH | Is save exported; does ExposureConfiguration disable the method |
| Item does not support DELETE | Does the repository have a suitable delete method and is it hidden |
| No search link | Does the repository have exported query methods |
| Property does not appear as expected | ALPS, JSON Schema, projections, and domain type serialization rules |

HTTP 405 Method Not Allowed usually indicates that the resource exists, but the requested HTTP method is not supported. Check the method against the repository interface, annotations, and exposure configuration before changing the URL.

Metadata is an API discovery tool, not a complete description of every business rule or access permission. Actual results are also affected by validation, serialization, projections, security, and application configuration. Check real responses when verifying endpoint behavior.

## 8. Checklist for reading metadata in order

1. Send GET to the root URL and note the relations in _links.
2. Follow the collection link to determine the actual URL and relation.
3. Follow the profile link to find metadata for the right repository.
4. Read ALPS to see exposed fields and REST operations.
5. Read JSON Schema if you need data types and property structures.
6. Open the repository interface to check the domain type, ID type, CRUD methods, and query methods.
7. Check @RepositoryRestResource, @RestResource, and RepositoryRestConfiguration to explain hidden or renamed methods.
8. Test the corresponding GET/POST/PUT/PATCH/DELETE requests and inspect status codes, links, and response bodies.

This order cross-checks three layers of information: Java repository metadata, exposed REST metadata, and actual HTTP behavior.

## References

- [Spring Data REST — Metadata](https://docs.spring.io/spring-data/rest/reference/metadata.html)
- [Spring Data REST — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Data REST — Customizing Spring Data REST](https://docs.spring.io/spring-data/rest/reference/customizing-sdr.html)
- [Spring Data REST — Project overview](https://spring.io/projects/spring-data-rest)