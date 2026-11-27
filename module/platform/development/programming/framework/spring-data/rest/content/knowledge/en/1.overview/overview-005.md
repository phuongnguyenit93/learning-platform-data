# REST, HATEOAS, and Link-Driven API Discoverability

REST describes an architectural style in which systems exchange information through resources and resource representations. HATEOAS adds the principle that API responses carry links indicating how a client can navigate to the next resource or action. As a result, clients discover the API from a known entry point instead of assembling every URL from internal server conventions.

Spring Data REST applies this approach by exporting Spring Data repositories as REST resources and representing them by default with HAL (Hypertext Application Language).

## 1. REST views an API as a set of resources

A **resource** is a concept the system exposes to clients, such as a book, order, or customer. A URI identifies the resource; a representation is the data describing the resource's state at a point in time.

For example:

- **/books** identifies the collection of books.
- **/books/42** identifies a single book.
- **/orders/91** identifies a single order.

URIs do not have to mirror table names or database structures. The server can change how data is stored while keeping the resource contract for clients intact.

REST is an **architectural style**, not synonymous with creating an endpoint for every CRUD operation. Full REST is built from architectural constraints:

1. **Client–server:** the client interface and server-side processing/storage can evolve independently through a clear exchange contract.
2. **Stateless:** each request contains enough information for the server to process it; the server does not rely on implicit conversational session state kept between requests.
3. **Cacheable:** responses indicate whether data can be cached and under what conditions.
4. **Uniform interface:** components interact through a uniform interface. This constraint includes resource identification, manipulation through representations, self-descriptive messages, and hypermedia.
5. **Layered system:** the client does not need to know which proxies, gateways, or intermediate layers a request passes through.
6. **Code on demand (optional):** the server may send executable code to the client, though REST does not require using this capability.

HTTP is commonly used to implement REST APIs. Some key HTTP conventions:

| Method | Common meaning | Safe | Idempotent |
|---|---|---:|---:|
| GET | Read a representation | Yes | Yes |
| HEAD | Read response metadata | Yes | Yes |
| POST | Create a resource or submit a processing request | No | Not guaranteed |
| PUT | Replace the state of the target resource | No | Yes |
| PATCH | Partially update a resource | No | Not guaranteed |
| DELETE | Delete the target resource | No | Yes regarding intended effect |

**Safe** means the request is designed not to request any state change on the resource. **Idempotent** means sending the same request multiple times has the same intended effect as sending it once; HTTP responses across calls may still differ.

REST also uses status codes to describe outcomes: `200 OK`, `201 Created`, `204 No Content`, `400 Bad Request`, `404 Not Found`, and `405 Method Not Allowed` are common codes. Specific statuses depend on the endpoint and framework configuration.

## 2. HATEOAS: letting responses guide the client

HATEOAS stands for **Hypermedia as the Engine of Application State**. Clients receive links inside representations and use them to discover the next steps the server offers.

A link typically has two important parts:

- **href:** the URI the client can access.
- **rel (relation):** the meaning of the link, such as **self**, **next**, **search**, **profile**, or an application-defined relation.

Example response:

~~~json
{
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/books/42"
    },
    "author": {
      "href": "http://localhost:8080/api/books/42/author"
    }
  }
}
~~~

The client understands that the response describes a book and has a link bearing the **author** relation. The client does not have to guess the author's endpoint by concatenating strings from IDs or class names.

A typical API discovery flow:

1. The client knows the API entry point URL, such as **http://localhost:8080/api**.
2. The client sends `GET` to the entry point and reads the links in the response.
3. The client looks up the appropriate relation, such as **books**, and accesses the URI in **href**.
4. From the collection, the client reads links to individual items, pagination links, or the **search** link.
5. From an item, the client continues following relationship links such as **author**, **publisher**, or actions published by the server.

In a hypermedia system, links can reflect current state. For example, an unpaid order may include a payment link; after payment, that link may disappear and another link may appear. The client relies on actions advertised in the response to decide the next step.

Clients still need to understand relation meanings and media types. HATEOAS does not completely eliminate domain knowledge on the client; it reduces coupling to URL structures and lets the server govern valid transitions via hypermedia.

## 3. HAL represents links in JSON

**HAL** is a popular hypermedia format for JSON. Spring Data REST uses HAL by default to represent resources.

Common fields:

- **_links:** links of the current resource. Property names are typically relations; values contain **href** and may include additional metadata.
- **_embedded:** resources embedded directly inside the representation, commonly used for collection elements.
- **templated:** indicates that **href** is a URI template with variables to fill in, such as `page`, `size`, or `q`.
- **page:** pagination metadata in Spring Data REST collection responses.

The common media type is **application/hal+json**. Clients can send the **Accept: application/hal+json** header to explicitly request a HAL representation.

### Root resource example

Suppose the application has a repository for books. A `GET` to the entry point may return links like:

~~~json
{
  "_links": {
    "books": {
      "href": "http://localhost:8080/api/books"
    }
  }
}
~~~

The **books** relation leads to the book collection. Some configurations also provide metadata/profile links. Clients should follow the actual links in responses rather than assuming metadata endpoints.

### Collection resource example

~~~json
{
  "_embedded": {
    "books": [
      {
        "title": "Spring in Action",
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/books/1"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/books{?page,size,sort}",
      "templated": true
    },
    "search": {
      "href": "http://localhost:8080/api/books/search"
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

This is an illustrative representation. Actual host, URI, relations, and metadata may differ based on configuration. Clients should read **href** from the response. The **self** link has a URI template because the collection supports pagination and sorting parameters.

### Item resource example

~~~json
{
  "title": "Spring in Action",
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/books/1"
    }
  }
}
~~~

If a domain object has an association, Spring Data REST may expose a link named after the association property. Clients follow that link to read or manipulate the association instead of constructing the path manually.

**Distinguishing links from embedded resources:** a link points to the location to access a resource; an embedded resource places a resource's representation inside the current response. Embedding data can reduce request count, while links preserve independent navigation and fetching.

## 4. Spring Data REST turns repositories into REST resources

Spring Data REST exports Spring Data repositories as HTTP resources. With a repository managing the **Book** entity, the framework typically creates:

- **Collection resource**, such as **/books**.
- **Item resource** for each record, such as **/books/1**.
- **Search resource** if the repository has exported query methods.
- **Association resources** for entity relationships.

Default collection names are derived from the domain class name following Spring Data REST rules. Paths and relations can be customized with **@RepositoryRestResource**.

HTTP operations typically mapped from a repository:

- Collection: `GET` to read the list, `POST` to create an element.
- Item: `GET` to read, `PUT` to replace, `PATCH` to partially update, and `DELETE` to delete.
- Association: links allowing clients to access relationships between resources.
- Search: `GET` on the search resource to discover published query methods.

Methods that do not exist or are marked **exported = false** will not be exported accordingly. Do not assume every repository exposes all HTTP methods.

### Discovering query methods

Spring Data REST provides a search resource for exported query methods. Clients send `GET` to the **search** link to obtain a list of links to individual queries. A query link may be a URI template containing parameters to supply.

For example, a repository declares a method to search books by title. The client discovers the **by-title** relation from the search resource, then calls the link with parameter **q**. This enables clients to find search functionality via hypermedia without knowing full URLs beforehand.

### Association resources

Suppose **Book** has an **author** property. Spring Data REST may provide an **author** link relation in the item resource. The client follows the link to read the association. Linking or unlinking is performed using the HTTP methods and media types supported by the association resource; some linking operations use **text/uri-list**.

Association names and paths can be customized with **@RestResource** on the property. Expose only the relationships clients actually need to use.

## 5. Spring Data REST example with Java 17+

The following example creates a book management API. Spring Data REST automatically exports the repository as resources; there is no need to write a separate CRUD controller.

### Dependencies

In a Spring Boot 3.x project using Java 17+, add the following dependencies and let Spring Boot dependency management select compatible versions:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-rest</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-jpa</artifactId>
    </dependency>
    <dependency>
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>
</dependencies>
~~~

### Book entity

File **src/main/java/com/example/library/Book.java**:

~~~java
package com.example.library;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;

@Entity
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String title;

    protected Book() {
    }

    public Book(String title) {
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }
}
~~~

The entity has a no-arg constructor so JPA can instantiate the object. The ID is automatically generated by the database. The REST representation does not necessarily have to expose the ID as a JSON field because clients can use the **self** link.

### Repository

File **src/main/java/com/example/library/BookRepository.java**:

~~~java
package com.example.library;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(
    path = "books",
    collectionResourceRel = "books"
)
public interface BookRepository extends JpaRepository<Book, Long> {

    @RestResource(path = "by-title", rel = "by-title")
    List<Book> findByTitleContainingIgnoreCase(@Param("q") String q);
}
~~~

**JpaRepository** provides persistence operations. **@RepositoryRestResource** sets the path and relation for the collection. The query method is exported as a search resource; **@RestResource** sets a client-friendly path and relation. **@Param("q")** specifies the query parameter name.

### Application

File **src/main/java/com/example/library/LibraryApplication.java**:

~~~java
package com.example.library;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LibraryApplication {

    public static void main(String[] args) {
        SpringApplication.run(LibraryApplication.class, args);
    }

    @Bean
    CommandLineRunner seed(BookRepository books) {
        return args -> books.saveAll(List.of(
            new Book("Spring in Action"),
            new Book("Effective Java")
        ));
    }
}
~~~

### Configuration

File **src/main/resources/application.properties**:

~~~properties
spring.datasource.url=jdbc:h2:mem:library
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.data.rest.base-path=/api
~~~

Configuring the base path places Spring Data REST's entry point at **/api**. H2 runs in memory so the example starts without installing a separate database.

### Running the application

In the project directory, run:

~~~bash
./mvnw spring-boot:run
~~~

On Windows:

~~~powershell
mvnw.cmd spring-boot:run
~~~

The example assumes the Maven wrapper and dependencies are configured in the Spring Boot project. When the application runs, the repository is exported under base path **/api**.

## 6. Hands-on API discovery over HTTP

The commands below illustrate requests you can make. In a real hypermedia client, take URLs from links in the previous response rather than assembling paths manually.

### Step 1: read the entry point

~~~bash
curl -H "Accept: application/hal+json" http://localhost:8080/api
~~~

Read the **books** relation inside **_links**, then use the **href** value to access the collection.

### Step 2: read the collection

~~~bash
curl -H "Accept: application/hal+json" http://localhost:8080/api/books
~~~

The response contains elements under **_embedded.books**, a **self** link, a **search** link, and pagination metadata. When there are multiple pages, clients follow the returned pagination links instead of calculating the next URL manually.

### Step 3: discover search capabilities

~~~bash
curl -H "Accept: application/hal+json" http://localhost:8080/api/books/search
~~~

The search resource lists links for query methods. With the example above, the **by-title** relation leads to the endpoint searching books by title. The URI template may contain the **q** variable.

You can invoke the query with the corresponding URL:

~~~bash
curl -H "Accept: application/hal+json" "http://localhost:8080/api/books/search/by-title?q=spring"
~~~

In a hypermedia application, the client retrieves the **by-title** link from the search resource response and fills the `q` value into the URI template.

### Step 4: create a resource

~~~bash
curl -i -X POST -H "Content-Type: application/json" -H "Accept: application/hal+json" -d '{"title":"Designing Data-Intensive Applications"}' http://localhost:8080/api/books
~~~

The collection resource accepts `POST` to create a book. The response typically has status `201 Created`; depending on headers and configuration, it may contain a representation or provide the new URI via the `Location` header. Clients use the URI/link returned by the server to read the newly created resource.

## 7. Designing clients to genuinely use HATEOAS

A hypermedia client should:

1. Configure only the entry point and media types supported by the API.
2. Read links by business-meaningful relations.
3. Access the URI in **href**; do not concatenate strings from resource names, IDs, or pluralization rules.
4. Recognize URI templates and fill in the advertised variables properly.
5. Follow pagination links provided by the server.
6. Handle relations that may be absent when an action is unavailable.
7. Handle status codes, network errors, and representation changes according to the media type contract.

For example, if a client needs to view a book's author, it looks up the **author** relation in the book's representation and calls the corresponding URI. The client should not assume the endpoint always has the form **/books/{id}/author**, because the server can change the path while keeping the relation intact.

Relations are part of the API contract. Choose meaningful names and maintain stable semantics. If a relation changes its meaning, clients may misinterpret the action even if the URI remains reachable.

## 8. Security and controlling repository export scope

Automatically exporting repositories reduces CRUD code, but you must carefully review which repositories are exposed. Never assume every repository in an application is suitable to become an API.

Ways to control exposure:

- Use Spring Security to authenticate and authorize on the server. Hiding a link does not replace permission checks on the endpoint.
- Use **@RepositoryRestResource(exported = false)** to avoid exporting repositories not intended for clients.
- Use **@RestResource(exported = false)** for methods or associations that should not be exposed.
- Use projections or DTOs when you need to restrict returned fields.
- Check validation, error handling, and access permissions for both read and write operations.
- Do not let clients directly modify internal fields just because an entity has setters.

If business logic involves multi-step workflows, complex precondition checks, or custom orchestration, consider a custom controller and Spring HATEOAS. You can then use **EntityModel**, **CollectionModel**, and link-building APIs to design hypermedia representations.

## 9. Common misconceptions

**Confusing HATEOAS with adding a `_links` object.** Having a **_links** field is not enough. Clients need to actually use relations to discover next steps.

**Confusing HAL with HATEOAS.** HATEOAS is an architectural constraint; HAL is a hypermedia representation format. Hypermedia can be implemented using other formats.

**Hard-coding every URL.** When a client constructs paths from IDs or entity names, it couples to URL structure and misses discoverability benefits.

**Assuming every repository method is automatically exported.** Exporting depends on repository type, available methods, configuration, and the **exported** attribute.

**Assuming a missing link means protected.** Access permissions must always be enforced on the server. Clients cannot rely on a link's absence as a security mechanism.

**Confusing embedded data with links.** Embedded data is a representation included in the current response; a link is a pointer to access a resource.

**Ignoring URI templates and pagination.** Clients need to read template variables and follow pagination links, not assume a collection always fits in a single response.

**Assuming Spring Data REST fits every API.** It fits when resources and repository mappings reflect business needs well. APIs with specialized workflows may require custom-designed endpoints and representations.

## 10. Checklist when designing or consuming a hypermedia API

- [ ] There is a clear entry point for clients.
- [ ] Every resource has appropriate relations and links.
- [ ] Clients follow **href** from responses instead of assembling URLs manually.
- [ ] Relations have stable names and meanings.
- [ ] URI templates, pagination, and search links are handled properly.
- [ ] Media types and representation structures are consistent.
- [ ] HTTP methods and status codes accurately reflect outcomes.
- [ ] Repositories, methods, and fields are exported intentionally.
- [ ] Authentication and authorization are enforced on the server.
- [ ] Integration tests verify both data and navigation links.

## 11. Conclusion

REST organizes an API around resources and representations. HATEOAS embeds navigation links into representations so clients can discover next resources and actions. HAL represents those links in JSON via **_links** and **_embedded**. Spring Data REST combines these ideas by exporting Spring Data repositories as collection, item, search, and association resources.

When using Spring Data REST, start from the root resource, follow relations to collection, item, and search resources, and continue following links provided by the server. The more clients rely on the API's relations and media types, the less coupled they are to internal URL details.

## References

- [Spring Data REST Reference — Introduction](https://docs.spring.io/spring-data/rest/reference/intro.html)
- [Spring Data REST Reference — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html)
- [Spring Boot Reference — Spring HATEOAS](https://docs.spring.io/spring-boot/reference/web/spring-hateoas.html)
- [Spring HATEOAS API — EntityModel](https://docs.spring.io/spring-hateoas/docs/current/api/org/springframework/hateoas/EntityModel.html)
