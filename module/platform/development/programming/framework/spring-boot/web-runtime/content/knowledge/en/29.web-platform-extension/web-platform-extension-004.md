# Spring HATEOAS Support and Resource Links in Responses

**Module:** Spring Boot - web-runtime  
**Parent Topic:** Extending the Web Platform

## 1. What Problem Does HATEOAS Solve?

A REST API has an endpoint **GET /api/books/1** returning JSON describing a book:

~~~json
{
  "id": 1,
  "title": "Java Web Runtime",
  "author": "Nguyen An",
  "available": true
}
~~~

A client that wants to check availability or return to the catalog must already know paths such as **/api/books/1/availability** and **/api/books**. If the server changes routes or reorganizes resources, clients with hardcoded URLs break easily.

**HATEOAS** (*Hypermedia as the Engine of Application State*) is a REST architectural constraint: representations from the server include **hypermedia controls**, such as **links with clear relations/rels**, so clients can discover related resources and valid next steps. The server does not just return data; it also points out valid navigation paths per the API contract.

A **HAL JSON** response can look like this:

~~~json
{
  "id": 1,
  "title": "Java Web Runtime",
  "author": "Nguyen An",
  "available": true,
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/books/1"
    },
    "books": {
      "href": "http://localhost:8080/api/books"
    },
    "availability": {
      "href": "http://localhost:8080/api/books/1/availability"
    }
  }
}
~~~

**self** points to the book itself; **books** points to the collection; **availability** is a domain-specific relation. A client that understands these relations can follow **_links.availability.href** instead of concatenating URL strings. The client still needs to know the **entry point**, media type, and relation semantics; HATEOAS reduces URL-path coupling, rather than eliminating all contracts.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish **resource**, **representation**, **link**, **link relation**, **HAL**, **affordance**, and entry point.
2. Explain how Spring Boot 3.x auto-configures **spring-boot-starter-hateoas** on **Servlet Spring MVC**.
3. Use **Link**, **RepresentationModel**, **EntityModel**, **CollectionModel**, **PagedModel**, and **RepresentationModelAssembler** within their intended scope.
4. Build links from Spring MVC mappings using **WebMvcLinkBuilder.linkTo(...)** and **methodOn(...)**, without hardcoding URLs.
5. Run a Java 17+ demo featuring GET item, collection, sub-resource, state-based links, and HTTP 404.
6. Verify **application/hal+json**, **_links**, **_embedded**, relation names, and hrefs with curl/JUnit.
7. Handle links behind a reverse proxy using **server.forward-headers-strategy**, HTTPS, and trusted Forwarded headers.
8. Understand boundaries with authorization, pagination, WebFlux, Spring Data REST, HTTP caching, and OpenAPI.

## 2. Resource, Representation, and Relation Are Not the Same Thing

A **resource** is a conceptual entity identified by a URI, such as book 1 or the book catalog. A **representation** is how that resource is serialized in an HTTP response, such as JSON or HAL JSON. A **link** contains an `href` (target) and a `rel` (relation). The **rel** explains what that link means in the context of the representation.

Common relations:

| Rel | Meaning | Usage |
| --- | --- | --- |
| **self** | URL to the current resource | Usually present for items/collections with stable URIs. |
| **books** | URL to the book catalog | Domain relation defined by the API. |
| **availability** | URL to book availability status | Can appear conditionally based on state in the representation. |
| **next**, **prev** | Forward/backward pagination | Should appear only when a corresponding page exists. |
| **first**, **last** | First/last page | Depends on pagination policy. |
| **profile** | Schema/semantic profile | Does not replace authorization or OpenAPI. |
| **search** | Search endpoint or URI Template | Client must understand query variables. |

Relations **self/next/prev** are standard; custom relations like **books** or **availability** should be documented or use URIs/CURIEs when stable namespacing is needed. Never change a relation's meaning once clients depend on it.

**A link is not access permission.** Having a link in JSON does not prove a user is authorized to make the request. If the server omits a link because a book is unavailable, the URL may still exist and someone could request it directly. Authentication/authorization must be enforced on the actual endpoint.

A representation can expose different controls depending on state, permissions, or workflow. That is far more meaningful than stuffing arbitrary URL fields into JSON.

## 3. HAL JSON and Media Type

**HAL** (*Hypertext Application Language*) is a simple hypermedia format with media type **application/hal+json**. It uses special keys:

- **_links**: maps `rel` → link object/array containing **href**, and optionally **templated**, **title**, **type**, or other metadata.
- **_embedded**: maps `rel` → embedded resource representations inside the response.
- Remaining fields: ordinary domain/representation data.

Example of a single item:

~~~json
{
  "id": 1,
  "title": "Java Web Runtime",
  "_links": {
    "self": {
      "href": "https://api.example.test/api/books/1"
    },
    "books": {
      "href": "https://api.example.test/api/books"
    }
  }
}
~~~

Example of a collection with two books:

~~~json
{
  "_embedded": {
    "books": [
      {
        "id": 1,
        "title": "Java Web Runtime",
        "_links": {
          "self": {
            "href": "https://api.example.test/api/books/1"
          }
        }
      },
      {
        "id": 2,
        "title": "Designing Web APIs",
        "_links": {
          "self": {
            "href": "https://api.example.test/api/books/2"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.test/api/books"
    }
  }
}
~~~

Not every response is required to have **_embedded**. Empty collections can be represented differently depending on fallback types and the HAL converter. A single relation can have multiple links represented as an array. Clients must handle single vs. multiple links according to the contract.

**HAL differs from plain JSON in its media type and hypermedia representation.** It is not a separate transport protocol: statuses, headers, caching, TLS, authentication, and HTTP methods remain standard HTTP.

### URI Templates

A link with query parameters can be described using a URI Template:

~~~json
{
  "_links": {
    "search": {
      "href": "https://api.example.test/api/books{?q,page,size}",
      "templated": true
    }
  }
}
~~~

This is a **template**, not a concrete URL to send verbatim. Clients must understand RFC 6570 or use a HAL library to expand **q/page/size** and URL-encode properly. A templated link does not create a `@GetMapping` search endpoint automatically; the server still has to implement it.

## 4. What APIs Does Spring HATEOAS Provide?

Spring HATEOAS adds representation models, link builders, and hypermedia serialization support to Spring Framework. Key classes:

| Class / interface | Function | When to use |
| --- | --- | --- |
| **Link** | `href` + `rel` and metadata | Creating self/collection/related links. |
| **RepresentationModel<T>** | Base model holding a collection of links | Building custom representation types or wrappers. |
| **EntityModel<T>** | Wraps an object `T` with links | Returning a single resource. |
| **CollectionModel<T>** | Wraps multiple items with collection links | Returning a collection. |
| **PagedModel<T>** | Collection + `PageMetadata` | Returning a page of data. |
| **RepresentationModelAssembler<T,D>** | Converts domain/DTO `T` into representation `D` | Centralizing link building and conditional logic. |
| **WebMvcLinkBuilder** | Builds URIs from Spring MVC mappings | Avoiding hardcoded hosts/paths. |
| **@Relation** | Specifies item/collection relation names | Controlling `_embedded` keys. |
| **LinkDiscoverers** | Finds links by `rel` in hypermedia representations | Typically supports client-side consumption. |
| **Affordance** | Describes available actions (method, input, etc.) | When workflow/action semantics are needed. |

**Spring HATEOAS does not generate CRUD APIs automatically**, manage databases, authenticate users, or turn arbitrary POJOs into linked HAL models. Controllers and assemblers decide which links appear in responses.

Class names in older blog posts may differ: **ResourceSupport → RepresentationModel**, **Resource → EntityModel**, **Resources → CollectionModel**, **PagedResources → PagedModel**, **ResourceAssembler → RepresentationModelAssembler**, **ControllerLinkBuilder → WebMvcLinkBuilder**. Use the APIs matching Spring Boot 3.x rather than copying Boot 1.x snippets.

## 5. Spring Boot 3.3 Auto-Configuration and Dependencies

Spring Boot provides **spring-boot-starter-hateoas** specifically for **Spring MVC (Servlet)** applications. When auto-configuration runs, Boot sets up HAL support, the Jackson **ObjectMapper**, and beans like **LinkDiscoverers**; you **do not need to add `@EnableHypermediaSupport`** just to turn on the starter.

Per the Spring Boot 3.3 documentation:

- **spring-boot-starter-hateoas** is intended for MVC; **do not combine it with Spring WebFlux** in a reactive application. For WebFlux, add **org.springframework.hateoas:spring-hateoas** directly alongside the WebFlux starter.
- By default, a request with **Accept: application/json** may receive **application/hal+json** when HAL is the default JSON mapping.
- The property **spring.hateoas.use-hal-as-default-json-media-type=false** changes HAL-as-default-JSON behavior; test both `Accept: application/json` and `Accept: application/hal+json` after changing it.
- Adding **@EnableHypermediaSupport** for manual configuration can disable Boot's Jackson customizations; avoid adding it unless needed.

Do not assume auto-config guarantees every app endpoint will have **_links**. If a controller returns a plain DTO without building an `EntityModel`/links, the app cannot invent domain relations on its own.

### Demo Dependencies

This lesson uses **Spring Boot 3.3.13**, **Java 17+**, Maven, and embedded Tomcat for a reproducible demo. This aligns with the Boot 3.3 branch; new production environments should pick a supported Boot version receiving security patches.

Structure:

~~~text
hateoas-books-demo/
  pom.xml
  src/main/java/com/example/hateoas/
    HateoasBooksApplication.java
    BookDto.java
    AvailabilityDto.java
    BookModelAssembler.java
    BookController.java
  src/main/resources/
    application.properties
  src/test/java/com/example/hateoas/
    BookHateoasIntegrationTests.java
~~~

**pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>hateoas-books-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-hateoas</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The HATEOAS starter brings in MVC/HAL support; declaring `starter-web` explicitly in the demo keeps the Servlet model clear. You do not need **spring-boot-starter-data-rest** when writing REST controllers with links you control yourself.

**src/main/resources/application.properties**:

~~~properties
server.port=8080
spring.application.name=hateoas-books-demo

# Spring Boot 3.3 uses HAL as the default JSON hypermedia type.
# @EnableHypermediaSupport is not needed in the demo.
# spring.hateoas.use-hal-as-default-json-media-type=true
~~~

## 6. DTOs: Separating Representation from Persistence Model

Create **src/main/java/com/example/hateoas/BookDto.java**:

~~~java
package com.example.hateoas;

import org.springframework.hateoas.server.core.Relation;

@Relation(itemRelation = "book", collectionRelation = "books")
public record BookDto(long id, String title,
                      String author, boolean available) {
}
~~~

**@Relation** sets item relation **book** and collection relation **books**, telling the HAL converter to place collections under **_embedded.books** instead of an inferred class-derived name.

Create **src/main/java/com/example/hateoas/AvailabilityDto.java**:

~~~java
package com.example.hateoas;

public record AvailabilityDto(long bookId, boolean available) {
}
~~~

**Records** work cleanly with Java 17 and Jackson/Spring Boot 3. Domain data should pass through DTOs rather than exposing raw JPA entities, because persistence models may hold internal IDs, private attributes, lazy relations, or secrets that must never appear in responses.

**AvailabilityDto** does not need to extend `RepresentationModel`. We will wrap it in **EntityModel<AvailabilityDto>** to attach `self` and a link back to the book.

## 7. RepresentationModelAssembler: Centralizing Link Construction

Create **src/main/java/com/example/hateoas/BookModelAssembler.java**:

~~~java
package com.example.hateoas;

import org.springframework.hateoas.EntityModel;
import org.springframework.hateoas.server.RepresentationModelAssembler;
import org.springframework.stereotype.Component;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@Component
public class BookModelAssembler
        implements RepresentationModelAssembler<
                BookDto, EntityModel<BookDto>> {

    @Override
    public EntityModel<BookDto> toModel(BookDto book) {
        EntityModel<BookDto> model = EntityModel.of(
                book,
                linkTo(methodOn(BookController.class)
                        .one(book.id())).withSelfRel(),
                linkTo(methodOn(BookController.class)
                        .all()).withRel("books")
        );

        if (book.available()) {
            model.add(linkTo(methodOn(BookController.class)
                    .availability(book.id())).withRel("availability"));
        }

        return model;
    }
}
~~~

How it works:

- **RepresentationModelAssembler<T,D>** separates converting a DTO into a hypermedia representation from the controller.
- **EntityModel.of(book, ...)** wraps the data and links.
- **linkTo(methodOn(BookController.class).one(book.id()))** constructs a link from the real Spring MVC mapping; **methodOn** is a dummy invocation and does not execute the controller's business method to query data.
- **withSelfRel()** sets the standard `self` relation; **withRel("books")** sets the domain relation to the catalog.
- Available books expose the **availability** relation per presentation policy; unavailable books omit it. That is a state-driven representation change, not access control stopping callers from requesting the URL directly.
- When a route changes in `@RequestMapping`/`@GetMapping`, the link builder generates the updated URL from the mapping, reducing hardcoded path/host bugs.
- Expensive permission checks or repository lookups should not run individually per item inside an assembler over thousands of rows; batch/preload them to avoid N+1 queries.

### methodOn Creates a Proxy, Not a Request

This snippet:

~~~java
Link self = linkTo(
        methodOn(BookController.class).one(1L)
).withSelfRel();
~~~

is an **illustrative snippet**, requiring imports for **org.springframework.hateoas.Link** and the static methods. Spring HATEOAS uses a proxy to record the method invocation/mapping; it **does not query repositories, make HTTP requests, or run business code** inside `one()`. If a method or return type cannot be proxied, choose an appropriate `WebMvcLinkBuilder` overload and test link building.

## 8. Controller: Item, Collection, and Availability Resource

Create **src/main/java/com/example/hateoas/BookController.java**:

~~~java
package com.example.hateoas;

import java.util.Comparator;
import java.util.Map;

import org.springframework.hateoas.CollectionModel;
import org.springframework.hateoas.EntityModel;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.linkTo;
import static org.springframework.hateoas.server.mvc.WebMvcLinkBuilder.methodOn;

@RestController
@RequestMapping("/api/books")
public class BookController {

    private static final Map<Long, BookDto> BOOKS = Map.of(
            1L, new BookDto(1L, "Java Web Runtime",
                    "Nguyen An", true),
            2L, new BookDto(2L, "Designing Web APIs",
                    "Le Binh", false)
    );

    private final BookModelAssembler assembler;

    public BookController(BookModelAssembler assembler) {
        this.assembler = assembler;
    }

    @GetMapping("/{id}")
    public EntityModel<BookDto> one(@PathVariable("id") long id) {
        return assembler.toModel(findBook(id));
    }

    @GetMapping
    public CollectionModel<EntityModel<BookDto>> all() {
        var models = BOOKS.values().stream()
                .sorted(Comparator.comparingLong(BookDto::id))
                .map(assembler::toModel)
                .toList();

        return CollectionModel.of(
                models,
                linkTo(methodOn(BookController.class)
                        .all()).withSelfRel()
        );
    }

    @GetMapping("/{id}/availability")
    public EntityModel<AvailabilityDto> availability(
            @PathVariable("id") long id) {

        BookDto book = findBook(id);
        AvailabilityDto data =
                new AvailabilityDto(book.id(), book.available());

        return EntityModel.of(
                data,
                linkTo(methodOn(BookController.class)
                        .availability(id)).withSelfRel(),
                linkTo(methodOn(BookController.class)
                        .one(id)).withRel("book")
        );
    }

    private BookDto findBook(long id) {
        BookDto book = BOOKS.get(id);
        if (book == null) {
            throw new ResponseStatusException(
                    HttpStatus.NOT_FOUND, "Book not found");
        }
        return book;
    }
}
~~~

This structure intentionally uses a fake **Map** dataset to avoid database setup. In production, replace it with a service/repository enforcing business validation, authentication, and authorization.

**Endpoints that actually exist:**

| Method / route | Representation | Links |
| --- | --- | --- |
| **GET /api/books/1** | `EntityModel<BookDto>` | `self`, `books`, `availability` |
| **GET /api/books/2** | `EntityModel<BookDto>` | `self`, `books`; no `availability` rel |
| **GET /api/books** | `CollectionModel<EntityModel<BookDto>>` | collection `self`; each item has its own links |
| **GET /api/books/1/availability** | `EntityModel<AvailabilityDto>` | `self`, `book` |
| **GET /api/books/999** | 404 Not Found | No model created for missing book |

**Book 2 omits the `availability` link, yet `/api/books/2/availability` still exists** and can return `available=false`. This illustrates the exact difference between hypermedia navigation and route visibility/permission; never infer that a missing link means the endpoint does not exist.

**CollectionModel** holds the catalog's `self` link, not the first item's `self` link. **sorted(Comparator.comparingLong(...))** ensures deterministic ordering for the two demo items; with a real database, perform pagination and sorting at the data source instead of loading an entire table into the JVM.

### Spring Boot Main Class

Create **src/main/java/com/example/hateoas/HateoasBooksApplication.java**:

~~~java
package com.example.hateoas;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class HateoasBooksApplication {
    public static void main(String[] args) {
        SpringApplication.run(HateoasBooksApplication.class, args);
    }
}
~~~

Each public class/record matches its filename, and the unified root package **com.example.hateoas** lets Spring component scan find `BookController` and `BookModelAssembler`. Neither `web.xml`, `@EnableHypermediaSupport`, nor a custom HAL `ObjectMapper` is needed in the demo.

## 9. Running and Inspecting Responses with curl

In a project with Maven and Java 17+, run:

~~~bash
mvn clean test
mvn spring-boot:run
~~~

Open a second terminal after the server starts. Send **Accept: application/hal+json** so the client explicitly requests a HAL representation.

### Item with Multiple Links

~~~bash
curl -si \
  -H 'Accept: application/hal+json' \
  http://localhost:8080/api/books/1
~~~

Typical header:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
~~~

Logical body:

~~~json
{
  "id": 1,
  "title": "Java Web Runtime",
  "author": "Nguyen An",
  "available": true,
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/books/1"
    },
    "books": {
      "href": "http://localhost:8080/api/books"
    },
    "availability": {
      "href": "http://localhost:8080/api/books/1/availability"
    }
  }
}
~~~

Field/relation order is not an immutable contract. The `href` values assume a direct `localhost:8080` request without a reverse proxy.

### Item Without Conditional Link

~~~bash
curl -si \
  -H 'Accept: application/hal+json' \
  http://localhost:8080/api/books/2
~~~

The body still includes the book data and **_links.self/books**, while omitting **_links.availability** per the assembler. Do not enforce business logic merely by checking link presence: the endpoint can still be called directly. Authorization must be enforced on the server.

### Collection with _embedded

~~~bash
curl -si \
  -H 'Accept: application/hal+json' \
  http://localhost:8080/api/books
~~~

Condensed body:

~~~json
{
  "_embedded": {
    "books": [
      {
        "id": 1,
        "title": "Java Web Runtime",
        "author": "Nguyen An",
        "available": true,
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/books/1"
          },
          "books": {
            "href": "http://localhost:8080/api/books"
          },
          "availability": {
            "href": "http://localhost:8080/api/books/1/availability"
          }
        }
      },
      {
        "id": 2,
        "title": "Designing Web APIs",
        "author": "Le Binh",
        "available": false,
        "_links": {
          "self": {
            "href": "http://localhost:8080/api/books/2"
          },
          "books": {
            "href": "http://localhost:8080/api/books"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/books"
    }
  }
}
~~~

**_embedded.books** appears because of the `@Relation` defined on `BookDto`; with other classes or custom relation names, the embedded key can differ. Clients should look up keys by the contracted relation rather than assuming HAL always names collections `data` or `items`.

### Availability Sub-Resource

~~~bash
curl -si \
  -H 'Accept: application/hal+json' \
  http://localhost:8080/api/books/1/availability
~~~

Typical body:

~~~json
{
  "bookId": 1,
  "available": true,
  "_links": {
    "self": {
      "href": "http://localhost:8080/api/books/1/availability"
    },
    "book": {
      "href": "http://localhost:8080/api/books/1"
    }
  }
}
~~~

### Not Found

~~~bash
curl -i \
  -H 'Accept: application/hal+json' \
  http://localhost:8080/api/books/999
~~~

Expected status **404 Not Found**. The error body depends on Spring Boot's error configuration and is not necessarily HAL-serialized like an `EntityModel`. If the project standardizes errors with Problem Details (**application/problem+json**), test error negotiation separately.

### Compare Accept Headers

~~~bash
curl -si -H 'Accept: application/json' \
  http://localhost:8080/api/books/1

curl -si -H 'Accept: application/hal+json' \
  http://localhost:8080/api/books/1
~~~

Per Boot 3.3 docs, HAL is used as the default JSON media type when HATEOAS auto-configuration is active. If you set **spring.hateoas.use-hal-as-default-json-media-type=false**, replace converters, or add `@EnableHypermediaSupport`, test actual `Content-Type` and response schemas instead of assuming behavior stays unchanged.

## 10. Link Builder Instead of Hardcoding Paths

Error-prone approach:

~~~java
// Do not hardcode localhost URLs in production.
String selfUrl = "http://localhost:8080/api/books/" + id;
~~~

When deployed behind HTTPS, a context path, a reverse proxy, or API v2, hardcoded links break. Use Spring MVC mappings instead:

~~~java
Link self = linkTo(
        methodOn(BookController.class).one(id)
).withSelfRel();
~~~

This snippet requires importing **org.springframework.hateoas.Link** and static methods of **WebMvcLinkBuilder**, plus variable **id** in scope. **methodOn(...)** creates a dummy invocation to extract `@RequestMapping`/`@GetMapping` and path variables; it **does not execute repository logic, make HTTP calls, or run the real controller**.

Comparison:

~~~java
Link list = linkTo(BookController.class).withRel("books");
Link one = linkTo(
        methodOn(BookController.class).one(id)
).withSelfRel();
~~~

- **linkTo(BookController.class)** builds a link to the class-level mapping (**/api/books** in the demo).
- **linkTo(methodOn(...).one(id))** builds a link to the method-specific mapping (**/api/books/{id}**).
- If the controller class mapping has path variables or complex overloaded methods, pass the right overloads/parameters and write integration tests.

**Do not call `methodOn` from a background job outside a Servlet request expecting it to know the user's public hostname.** Without an `HttpServletRequest`, obtain a proper base URI from configuration/URI builders or explicit client-facing routes.

### Link with Query Parameters

Example HAL link template:

~~~json
{
  "_links": {
    "search": {
      "href": "https://api.example.test/api/books{?q,page,size}",
      "templated": true
    }
  }
}
~~~

URI Templates let clients expand `q`/`page`/`size` with proper encoding rules. Building query strings by concatenating unencoded user input can produce malformed URLs or leak sensitive info. Spring's URI building APIs and proper Link templating help prevent bugs.

## 11. RepresentationModelAssembler and Extensibility

In a tiny demo you could construct links directly in the controller; however, as endpoints, DTOs, and resource states grow, doing so duplicates self/collection/related link logic everywhere.

**RepresentationModelAssembler** can:

- Convert domain DTOs into linked `EntityModel` instances.
- Apply state- and permission-based conditions to expose appropriate relations.
- Reuse consistent relations across multiple resource implementations.
- Reduce hardcoded URL strings.
- Be unit-tested independently (alongside real HTTP integration tests).
- Support collection mapping via **toCollectionModel(...)** when appropriate.

A typical pipeline:

~~~text
GET /api/books/1
    |
    v
Controller -> Service -> Repository
    |
    v
DTO mapping / authorization context
    |
    v
BookModelAssembler.toModel(book)
    |
    +--> self
    +--> books
    +--> availability (if state allows)
    |
    v
EntityModel<BookDto>
    |
    v
HAL message converter + Jackson
    |
    v
HTTP 200 Content-Type: application/hal+json
~~~

**Do not query the database or authorization service N times for N items just to build links** when you can batch-fetch or pass authorization context into the assembler. HATEOAS can increase CPU/latency overhead and payload sizes; measure under real traffic.

### Empty Collections

For an empty collection, the HAL converter sometimes cannot infer the element type due to Java generic type erasure and may omit **_embedded** differently than expected. Spring HATEOAS provides **CollectionModel.empty(...)** and **withFallbackType(...)** to supply type metadata when needed. Clients should also treat an empty collection without `_embedded` as valid per the API contract.

### Multiple Links with the Same Rel

When one `rel` points to multiple targets, HAL can serialize it as an array. Clients should not assume **_links.<rel>** is always a single object; follow the contract for that relation. Relations like `next`/`prev` usually have one link, whereas domain relations may have several.

## 12. Hypermedia Affordances and Workflows

An order in status **NEW** might return relations **cancel** and **pay**, whereas a shipped order returns **tracking**:

~~~text
Order NEW:
  self -> /orders/42
  pay  -> /orders/42/payment
  cancel -> /orders/42/cancellation

Order SHIPPED:
  self -> /orders/42
  tracking -> /orders/42/tracking
~~~

This is an **illustrative workflow example**, not endpoints present in the book demo. A bare `href` often does not tell clients whether an action requires **POST/DELETE**, a request body, or auth details. Spring HATEOAS supports **affordances** to describe actions derived from controller methods using **afford(...)** and **andAffordance(...)** per its API.

**Keep in mind:**

1. To advertise an action, the backend must actually have an HTTP handler for it.
2. Never emit a link promising an action the endpoint does not support.
3. Never just hide a link when a user lacks permission: the endpoint must still **enforce authorization**.
4. Never embed session IDs, JWTs, or reset tokens in `href`; URLs get logged, cached, and shared.
5. Conditional links must reflect **real** state/permissions, never trusting unverified claims from the client.
6. HATEOAS clients should handle missing relations or multiple links gracefully instead of hardcoding rigid workflow assumptions.

**HATEOAS is not authentication, authorization, CSRF protection, or validation.** Those operate alongside it.

## 13. Pagination with PagedModel

For large collections, **PagedModel<T>** attaches **PageMetadata** for a page of data. This is a **non-standalone illustrative snippet**, assuming `pageContent` is a collection of `EntityModel<BookDto>` already fetched from the database and assembler:

~~~java
PagedModel.PageMetadata metadata =
        new PagedModel.PageMetadata(
                20,    // page size
                0,     // zero-based page number
                133,   // total elements
                7);    // total pages

PagedModel<EntityModel<BookDto>> result =
        PagedModel.of(
                pageContent,
                metadata,
                Link.of("https://api.example.test/api/books?page=0&size=20")
                        .withSelfRel());
~~~

Required imports: **org.springframework.hateoas.PagedModel**, **EntityModel**, **Link**, and **BookDto**. With 133 elements and page size 20, `totalPages` 7 is consistent. **PagedModel** can render **page.size**, **page.totalElements**, **page.totalPages**, and **page.number** depending on HAL mapping.

**Important:** the `PagedModel.of(...)` snippet above passes only a **self link** and **does not automatically generate `next`/`prev`**. To include page navigation links automatically, construct them explicitly or use **PagedResourcesAssembler** with **Spring Data `Page<T>`** when Spring Data web support is configured.

Example representation where the application has added `next`:

~~~json
{
  "_embedded": {
    "books": [
      {
        "id": 1,
        "title": "Java Web Runtime",
        "_links": {
          "self": {
            "href": "https://api.example.test/api/books/1"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "https://api.example.test/api/books?page=0&size=20"
    },
    "next": {
      "href": "https://api.example.test/api/books?page=1&size=20"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 133,
    "totalPages": 7,
    "number": 0
  }
}
~~~

In this JSON example, **next** had to be added by code outside the `PagedModel.of(...)` snippet; do not assume it is the exact output of that snippet alone.

**Do not have clients compute `next` via `page+1` when the server provides `_links.next.href`.** Following server-provided `next` decouples clients from pagination mechanics (offset/page/cursor). `self` should preserve active sort/filter/page and required query parameters.

## 14. Reverse Proxies and Wrong Host/Scheme in Links

Production topology:

~~~text
Browser: https://api.example.test/catalog/api/books/1
    |
    v
Ingress / reverse proxy (TLS termination)
    |
    v
Spring Boot: http://books-service:8080/api/books/1
~~~

The backend receives the request over internal HTTP. If the link builder only sees the internal host/scheme, it can emit:

~~~json
{
  "_links": {
    "self": {
      "href": "http://books-service:8080/api/books/1"
    }
  }
}
~~~

This link is **broken for external clients**. In an HTTPS browser, HTTP links can be blocked by mixed-content policies, and internal hostnames cannot be resolved.

A reverse proxy can supply forwarding metadata:

~~~http
Forwarded: proto=https;host=api.example.test
X-Forwarded-Proto: https
X-Forwarded-Host: api.example.test
X-Forwarded-Prefix: /catalog
~~~

Spring Boot 3.3 supports:

~~~properties
# Uses Spring Framework ForwardedHeaderFilter on the Servlet stack
server.forward-headers-strategy=framework
~~~

or:

~~~properties
# Uses the embedded server's native forwarded-header handling
server.forward-headers-strategy=native
~~~

**FRAMEWORK** uses Spring Framework support; **NATIVE** uses the container; **NONE** ignores the headers. Exact behavior depends on the environment and proxy, so verify against a real public URL.

**Crucial trust boundary:** external Internet clients can forge `Forwarded`/`X-Forwarded-*` headers. Only enable handling these headers when the edge proxy **strips untrusted headers and rewrites authoritative values**, and the backend cannot be reached directly from untrusted sources. Otherwise an attacker can inject a malicious hostname into **_links.self** (link poisoning) or redirects.

With proxy path rewrites, verify **X-Forwarded-Prefix**, context path, TLS scheme, and port — not just hostname. When traffic passes through multiple gateway/mesh hops, establish which layer is authoritative for setting the public origin.

### Testing Behind a Proxy

1. Call the public HTTPS endpoint with `Accept: application/hal+json`.
2. Verify **_links.self.href** starts with the expected **`https://api.example.test/catalog/...`**.
3. Follow the returned `href` to confirm the resource is reachable.
4. Send forged `Host`/`Forwarded` headers at the edge and verify no link poisoning occurs.
5. Verify redirects, errors, collection links, and pagination links, not just a single item.
6. If the proxy alters paths, confirm **linkTo(methodOn(...))** generates accurate URLs from the effective request context.

## 15. HTTP Content Negotiation and Caching

A client requesting HAL should send:

~~~http
GET /api/books/1 HTTP/1.1
Host: localhost:8080
Accept: application/hal+json
~~~

Server HAL response:

~~~http
HTTP/1.1 200 OK
Content-Type: application/hal+json
~~~

When an API supports multiple representations depending on `Accept`, consider **Vary: Accept** and shared cache/CDN configuration so wrong representations are not served. **Do not claim Spring always adds a specific `Vary` header automatically**; inspect actual headers and cache keys.

**`EntityModel.of(...)` does not generate `Cache-Control`, `ETag`, or `Last-Modified`.** If a response includes links personalized by user permissions, be especially cautious with **public caching**. One user must never receive private links or privileged controls from a shared CDN cache intended for another user.

If `ETag` hashes representation bytes, changing links changes the `ETag`. If you hash only the domain object while links vary per user/permissions, evaluate validators and cache policies carefully to avoid stale revalidation.

**Switching to HAL does not change HTTP status semantics:** GET is typically 200, missing resource 404, creation can be 201 with `Location`, validation error 400, access denied 403. Error responses can use **Problem Details**; error responses are not required to contain `_links`.

### Compatibility When Migrating from Plain JSON

- Document **application/hal+json** in API docs and client examples.
- Test clients sending only **Accept: application/json**, because Boot 3.3 defaults JSON responses to HAL.
- If you set **spring.hateoas.use-hal-as-default-json-media-type=false**, test actual negotiation and converters.
- Never rename `rel` or `_embedded` keys without evaluating existing client parsers.
- For empty collections and error responses, clients must handle valid schema variants.
- When representation schemas change significantly, plan migration/versioning carefully; HATEOAS does not eliminate breaking changes.

## 16. Real HTTP Integration Tests with Random Port

The configuration already includes **spring-boot-starter-test**. The following test verifies that HAL serializes properly across the HTTP connector rather than merely checking assembler objects in memory.

Create **src/test/java/com/example/hateoas/BookHateoasIntegrationTests.java**:

~~~java
package com.example.hateoas;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(webEnvironment =
        SpringBootTest.WebEnvironment.RANDOM_PORT)
class BookHateoasIntegrationTests {

    @LocalServerPort
    int port;

    private final HttpClient http = HttpClient.newHttpClient();
    private final ObjectMapper json = new ObjectMapper();

    private HttpResponse<String> get(String path) throws Exception {
        HttpRequest request = HttpRequest.newBuilder(
                    URI.create("http://localhost:" + port + path))
                .header("Accept", "application/hal+json")
                .GET()
                .build();
        return http.send(request,
                HttpResponse.BodyHandlers.ofString());
    }

    @Test
    void itemHasExpectedLinks() throws Exception {
        HttpResponse<String> response = get("/api/books/1");
        assertEquals(200, response.statusCode());

        assertTrue(response.headers()
                .firstValue("content-type")
                .orElse("").startsWith("application/hal+json"));

        JsonNode body = json.readTree(response.body());
        assertEquals(1, body.path("id").asInt());
        assertEquals("Java Web Runtime",
                body.path("title").asText());

        String base = "http://localhost:" + port;
        assertEquals(base + "/api/books/1",
                body.path("_links").path("self")
                        .path("href").asText());
        assertEquals(base + "/api/books",
                body.path("_links").path("books")
                        .path("href").asText());
        assertEquals(base + "/api/books/1/availability",
                body.path("_links").path("availability")
                        .path("href").asText());
    }

    @Test
    void unavailableBookHidesAvailabilityRel()
            throws Exception {
        HttpResponse<String> response = get("/api/books/2");
        assertEquals(200, response.statusCode());

        JsonNode body = json.readTree(response.body());
        assertFalse(body.path("available").asBoolean(true));
        assertFalse(body.path("_links").has("availability"));
    }

    @Test
    void collectionHasBooksAndSelfLink() throws Exception {
        HttpResponse<String> response = get("/api/books");
        assertEquals(200, response.statusCode());

        JsonNode body = json.readTree(response.body());
        JsonNode books = body.path("_embedded").path("books");
        assertTrue(books.isArray());
        assertEquals(2, books.size());
        assertEquals("http://localhost:" + port + "/api/books",
                body.path("_links").path("self")
                        .path("href").asText());
    }

    @Test
    void unknownBookIs404() throws Exception {
        assertEquals(404, get("/api/books/999").statusCode());
    }
}
~~~

Command:

~~~bash
mvn test
~~~

**The JUnit test launches an embedded Spring Boot server on `RANDOM_PORT`**, using Java 17's standard `HttpClient` to send requests and `ObjectMapper` to read JSON. Thus the test verifies `Content-Type`, links, and URLs with the real port, rather than just confirming bean existence.

Things to remember:

- Do not assert strict JSON field order.
- Localhost tests do not verify reverse proxy forwarding; test through the edge for public HTTPS links.
- The demo lacks Spring Security; once security is added, test authenticated, unauthenticated, and permission-specific relations.
- For empty collections, add a dedicated test case if the real project can return empty results.
- For paginated APIs, test **next/prev/self** across page states and filters/sorts.
- When testing larger datasets, avoid only asserting status 200 and skipping `_embedded` item counts or valid `href` assertions.

### Following Links in Tests

A proper hypermedia test can do:

~~~text
GET /api/books/1
    |
    +-- read response -> _links.availability.href
    |
    +-- client GETs href from response (do not hardcode path)
    |
    +-- assert response bookId=1, available=true
~~~

This illustrates the flow; in a real project, write a helper that extracts `href` by `rel` and requests the returned URI while checking that scheme/host stay within trusted bounds before attaching credentials.

## 17. Consuming HAL Responses on the Client

A simple JavaScript client can read relations instead of concatenating paths:

~~~javascript
async function getAvailability(bookUrl) {
  const res = await fetch(bookUrl, {
    headers: { Accept: "application/hal+json" }
  });

  if (!res.ok) {
    throw new Error("Book HTTP " + res.status);
  }

  const book = await res.json();
  const href = book._links?.availability?.href;

  if (!href) {
    return { available: false, reason: "not-offered" };
  }

  const availableRes = await fetch(href, {
    headers: { Accept: "application/hal+json" }
  });

  if (!availableRes.ok) {
    throw new Error("Availability HTTP " + availableRes.status);
  }

  return availableRes.json();
}
~~~

This is an illustrative function meant to be invoked within a frontend/page with appropriate access, CORS, and credentials — not a standalone Java file.

**Key client rules:**

- Never guess a link when a relation is absent; UI/workflows must handle its absence.
- A relation may hold multiple links, so parsers must match the single vs. array contract.
- An `href` may be a URI Template, which must be expanded before calling.
- If an API returns an `href` pointing to a different hostname, never forward API A's Bearer token or cookies to an untrusted host; check trusted origins.
- If the follow-up GET returns 401/403, handle authentication/authorization like normal HTTP.
- Do not treat HATEOAS links as a replacement for OpenAPI schemas or response validation.
- When the frontend runs on a different origin, browser CORS still applies; HATEOAS does not enable CORS automatically.

## 18. Spring Data REST, OpenAPI, and Spring WebFlux

### Spring Data REST Differs from Spring HATEOAS

| Technology | Purpose | Auto-Generates CRUD Endpoints? |
| --- | --- | --- |
| **Spring HATEOAS** | Link/representation/assembler/HAL APIs | **No**. |
| **Spring Data REST** | Exposes Spring Data repositories via REST conventions | **Can**, when configured/exposed. |
| **Spring MVC** | HTTP controller mapping, validation, converters | Does not auto-create HAL links from plain DTOs. |
| **Spring Boot HATEOAS auto-config** | Prepares HAL/Jackson/`LinkDiscoverers` | Does not generate repositories/controllers. |

Do not add **spring-boot-starter-data-rest** just to get `EntityModel`/`CollectionModel`. Exporting repositories automatically carries its own security, serialization, and API surface implications.

### OpenAPI and Hypermedia Complement Each Other

**OpenAPI** describes endpoints, methods, input/output schemas, security schemes, and status codes at the static contract level. **HATEOAS** communicates at runtime which links/relations apply to the current resource state. A system can use both: OpenAPI for SDKs/documentation/testing, HAL links for discoverability/workflows.

HATEOAS does not remove the need for versioning, backward compatibility, authentication, or error models.

### WebFlux Does Not Use the MVC HATEOAS Starter the Same Way

Spring Boot 3.3 documentation advises that **spring-boot-starter-hateoas** is for **Spring MVC** and should not be combined directly with **Spring WebFlux**. For WebFlux, use **spring-boot-starter-webflux** together with a direct dependency on **org.springframework.hateoas:spring-hateoas**, and use the corresponding reactive link/assembler APIs.

Do not copy Servlet-request-based **WebMvcLinkBuilder** into a reactive WebFlux controller expecting it to be the standard approach. Confirm the actual web application type, codecs, and request context. If a project includes both `starter-web` and `starter-webflux`, Boot defaults to Servlet MVC.

## 19. Performance, Security, and Common Pitfalls

| Symptom | Likely Cause | Fix |
| --- | --- | --- |
| DTO JSON has no `_links` | Not using `EntityModel`/assembler | Wrap data and attach links by `rel`. |
| Missing `_embedded.books` | Unexpected relation name, empty collection, different mapping | Check `@Relation`, fallback type, and real HAL output. |
| `Content-Type` is not `application/hal+json` | Different `Accept`/converter/Boot property or overridden auto-config | Test `Accept` and HATEOAS configuration. |
| `self` link points to `localhost`/internal host | Reverse proxy forwarded headers unhandled | Enable strategy safely and test public HTTPS. |
| `methodOn` produces wrong `href` | Mismatched mapping/parameters, or called outside request context | Check annotations, signature, `linkTo` overload, and tests. |
| Client gets 404 following a link | Stale link, missing route, wrong path rewrite | Check endpoint existence and link builder/proxy. |
| Omitting `availability` link still returns 200 on endpoint | Link visibility is not authorization | Design link semantics and enforce ACL on the endpoint. |
| `PagedModel` has `self` but no `next` | `next` not added or paging assembler not used | Generate page links conditionally. |
| Every resource links to unauthorized actions | Assembler ignores state/permissions | Filter links for UX if appropriate; still enforce auth on backend. |
| Unusually large response size | Over-deep embedding or excessive per-item links | Pagination, selective embedding, caching, gzip if appropriate. |
| N+1 queries assembling a collection | Assembler queries DB per relation | Prefetch/batch permissions/data; monitor DB metrics. |
| HAL via CDN leaks another user's links | Shared cache ignores personalization | Set proper `Cache-Control`; never public-cache private representations. |
| Client sends token to foreign `href` host | No hostname/trust-scope validation | Restrict destinations; never forward credentials blindly. |
| MVC HATEOAS starter fails in reactive app | Wrong WebFlux dependency | Use `spring-hateoas` directly with reactive APIs. |
| Spring HATEOAS added yet no CRUD endpoints appear | Confused with Spring Data REST | Write controllers manually or adopt Spring Data REST intentionally. |
| Test asserts status=200 yet links are broken | `_links`/`_embedded`/`href` not checked | Add contract/integration tests. |

**Security:** Relations are only navigation metadata. Users can edit URLs, call APIs directly, spoof `Origin`, or send invalid tokens. The backend must enforce authentication/authorization and business-state checks. For links built from `Host`/`Forwarded` headers, enforce trust boundaries to prevent host-header poisoning. Never put tokens or PII inside URLs.

**Performance:** Link generation can increase payload bytes and CPU cost, especially across thousands of collection items; use pagination, batch-fetched permissions, appropriate caching, and shallow embedding depth. Enabling compression saves bandwidth with a CPU tradeoff; measure p95/p99 and real request volume.

## 20. Production Deployment Checklist

- [ ] Confirm hypermedia requirements and which use cases benefit from discoverability.
- [ ] Use the MVC HATEOAS starter for the right stack; distinguish from Data REST/WebFlux.
- [ ] Test HAL serialization and `Content-Type` with `Accept: application/hal+json`.
- [ ] Use `EntityModel` for items, `CollectionModel` for collections, `PagedModel` for pages.
- [ ] Define clear, stable `rel` semantics; use `@Relation` for embedded collections where needed.
- [ ] Generate links via `WebMvcLinkBuilder` from Spring MVC mappings, never hardcoded `localhost`.
- [ ] Centralize link generation in `RepresentationModelAssembler` or a dedicated service.
- [ ] For state/permission-dependent links, still enforce security on the target endpoint.
- [ ] Never include secrets, private URLs, or sensitive info in `href`.
- [ ] Protect forwarded headers with a trusted proxy; verify HTTPS/hostname/context prefix.
- [ ] Verify self/related/collection links behind proxies and versioned routes.
- [ ] Generate `next`/`prev`/`first`/`last` accurately for paging state and filters/sorts; do not confuse metadata with automatic links.
- [ ] Handle empty collections, multiple links per `rel`, URI templates, and errors.
- [ ] Configure HTTP caching/`ETag`/`Vary` properly when representations vary by user/`Accept`.
- [ ] Verify link structure and follow-link behavior via HTTP tests, not status codes alone.
- [ ] Monitor payload bytes, CPU, latency, and SQL query counts when assembling collections.
- [ ] Plan `rel`/schema compatibility and client migration.
- [ ] Choose a maintained Spring Boot version and keep production patches current.

## 21. Self-Check Knowledge Quiz

**1. What does HATEOAS stand for?**  
Hypermedia as the Engine of Application State: the server returns links/controls guiding clients to discover resources and workflows.

**2. How does `EntityModel` differ from `CollectionModel`?**  
`EntityModel` wraps a single object with links; `CollectionModel` wraps multiple items along with collection-level links.

**3. Does using `starter-hateoas` automatically give every `@RestController` a `self` link?**  
No. The application must explicitly build `EntityModel`/`Link`/assemblers.

**4. Does `methodOn` invoke real business logic?**  
No. It records a dummy method invocation to extract mappings/arguments when building a link.

**5. What does `@Relation(collectionRelation="books")` do?**  
Specifies the embedded collection relation name so HAL uses `_embedded.books` instead of a default inferred name.

**6. Why does a collection's `self` link differ from each item's `self` link?**  
They represent distinct resources with different URIs: `/api/books` versus `/api/books/{id}`.

**7. Does the absence of an `availability` link guarantee the endpoint does not exist?**  
No. Link visibility is a representation policy, not a router or authorization guard.

**8. Does `PagedModel` generate `next` links solely from `PageMetadata`?**  
Not necessarily. You must add `next`/`prev` links explicitly or use an appropriate paging assembler.

**9. When do links get the wrong host/protocol after deployment?**  
When proxy/TLS termination leaves the backend seeing only an internal HTTP host; you need trusted forwarded headers or a public base URI policy.

**10. Can you trust `X-Forwarded-Host` from any incoming request?**  
No. The edge proxy must strip/overwrite untrusted headers.

**11. Are Spring HATEOAS and Spring Data REST the same?**  
No. HATEOAS builds links/models; Data REST can export repository endpoints automatically.

**12. Must a client use hardcoded URIs once it knows a `rel`?**  
No. The client can follow the `href` the server provides for that known `rel`.

**13. In Boot 3.3, can `Accept: application/json` return HAL?**  
Yes. HAL can act as the default JSON media type under auto-configuration; verify properties and actual responses.

**14. Should a client send a Bearer token to every `href` it receives?**  
No. Verify trusted host/scheme and credential scope to avoid leaking secrets.

**15. Should you use the MVC `starter-hateoas` directly with WebFlux?**  
No. Boot docs instruct using the `spring-hateoas` dependency directly with the reactive stack.

## 22. Official Reference Sources

- **Spring Boot 3.3 – Spring HATEOAS:** https://docs.spring.io/spring-boot/3.3/reference/web/spring-hateoas.html — auto-config, HAL media types, MVC starter, WebFlux distinction.
- **Spring HATEOAS – Reference Documentation:** https://docs.spring.io/spring-hateoas/docs/current/reference/html/ — representation models, relation providers, link builders, HAL, and affordances; cross-check with the BOM-managed version.
- **Spring HATEOAS – WebMvcLinkBuilder API:** https://docs.spring.io/spring-hateoas/docs/2.2.x/api/org/springframework/hateoas/server/mvc/WebMvcLinkBuilder.html — `linkTo`, `methodOn`.
- **Spring HATEOAS – PagedModel API:** https://docs.spring.io/spring-hateoas/docs/2.2.x/api/org/springframework/hateoas/PagedModel.html — `PageMetadata`.
- **Spring HATEOAS – CollectionModel API:** https://docs.spring.io/spring-hateoas/docs/2.2.x/api/org/springframework/hateoas/CollectionModel.html — collections and fallback types.
- **Spring Boot 3.3 – Running Behind Proxy:** https://docs.spring.io/spring-boot/3.3/how-to/webserver.html — `server.forward-headers-strategy` and forwarded headers.
- **Spring Framework – MVC Forwarded Headers:** https://docs.spring.io/spring-framework/reference/web/webmvc/filters.html — `ForwardedHeaderFilter` and trust boundaries.
- **Spring – Building a Hypermedia-Driven RESTful Web Service:** https://spring.io/guides/gs/rest-hateoas/
- **HAL specification:** https://stateless.group/hal_specification.html — `_links`/`_embedded`, link relations.
- **RFC 6570 – URI Template:** https://www.rfc-editor.org/rfc/rfc6570