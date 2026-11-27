# Java, Spring, HTTP, JSON, and Search Prerequisites to Prepare

Spring Data Elasticsearch sits at the intersection of Java, Spring Data, HTTP/JSON communication, and search fundamentals. To learn this module smoothly, you should understand how data is modeled in Java applications, how Spring manages components, how applications exchange data over HTTP/JSON, and how a search engine processes text differently from a relational database.

This lesson organizes the foundational knowledge needed before diving into configuration, mappings, repositories, and Elasticsearch queries. You do not need to be an expert in all five areas before starting. The goal is to recognize each component's role, read basic examples, and understand the concepts that will appear in upcoming lessons.

## 1. Where does Spring Data Elasticsearch sit in an application?

Elasticsearch is a distributed engine for storing, searching, and analyzing data. Applications typically send documents and queries to Elasticsearch over an HTTP API. Exchanged payloads are usually formatted as JSON.

Spring Data Elasticsearch provides an integration layer so Java applications can work with Elasticsearch in the familiar Spring Data ecosystem style. It supports mapping Java objects to documents, declaring repositories, executing queries, and using high-level operation APIs.

The processing flow in a Spring Boot application can be visualized as follows:

~~~mermaid
flowchart TD
    A[HTTP request from client] --> B[Spring MVC Controller]
    B --> C[Business Service]
    C --> D[Spring Data Elasticsearch]
    D --> E[Elasticsearch cluster]
    E --> D
    D --> C
    C --> B
    B --> F[HTTP response]
~~~

Each component has a distinct responsibility:

- **Controller** receives HTTP requests, reads parameters, and returns results to the client.
- **Service** executes business logic, coordinates data, and decides how requests are processed.
- **Spring Data Elasticsearch** translates Java object-level operations into Elasticsearch-compatible operations.
- **Elasticsearch** stores documents, builds search structures, and executes queries.
- **JSON** is the standard format representing documents, queries, and responses between systems.

Spring Data Elasticsearch does not replace the Elasticsearch server. This library is the Java application-side integration layer; Elasticsearch remains a separate service that must be started and connected to.

## 2. Java knowledge to master

### 2.1. Classes, objects, and data models

Java models data using classes and objects. A class describes the structure, while an object is a concrete instance of that structure.

For example, a product can have an identifier, name, category, and price:

~~~java
public class Product {
    private String id;
    private String name;
    private String category;
    private BigDecimal price;

    public Product() {
    }

    public Product(String id, String name, String category, BigDecimal price) {
        this.id = id;
        this.name = name;
        this.category = category;
        this.price = price;
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getCategory() {
        return category;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
~~~

When working with Spring Data Elasticsearch, you will encounter classes representing documents stored inside an index. The library needs to know which field serves as the identifier and which fields represent text, dates, or other data types. Spring Data Elasticsearch annotations supply metadata for that mapping.

You should understand:

- Classes, objects, fields, constructors, and methods.
- Primitive types and reference types.
- Encapsulation and property access patterns.
- Interfaces and how classes implement interfaces.
- Generic types, because repositories typically declare both the document type and ID type.
- Annotations, because Spring uses annotations to attach metadata to classes and fields.

### 2.2. Collections and generics

Search results usually contain multiple documents. Therefore, you should be comfortable with collections such as List, Set, and Map.

For example:

~~~java
List<Product> products = new ArrayList<>();
Map<String, Product> productsById = new HashMap<>();
~~~

You should also be able to read generic declarations:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<Product, String> {
}
~~~

In the example above:

- Product is the object type the repository manages.
- String is the type of the identifier.
- ElasticsearchRepository is a generic interface providing standard repository operations.

The ID type must match the document's identifier field. If an application uses UUID or another type, the repository declaration must reflect that type accurately.

### 2.3. Optional, exceptions, and result handling

A lookup by ID might not find a document. Java typically represents potentially absent results using Optional:

~~~java
Optional<Product> product = productRepository.findById(id);

product.ifPresent(found -> {
    System.out.println(found.getName());
});
~~~

You need to distinguish between:

- Finding no results.
- Finding a result where a document field is null.
- Encountering an error while connecting or executing a query.

Do not treat every empty lookup as a system failure. Conversely, connection errors, configuration mistakes, or query errors must be handled and observed separately.

Understanding exceptions, try/catch blocks, and how errors propagate through service and controller layers prepares you for situations where Elasticsearch is unavailable or rejects a request.

### 2.4. Data types and data conversion

Java types to recognize include:

| Java | Common meaning in a document |
|---|---|
| String | Text, codes, or categorical values |
| Integer, Long | Integers |
| Double, BigDecimal | Decimal numbers |
| Boolean | True or false |
| LocalDate, LocalDateTime, Instant | Dates or timestamps |
| List, Set | Lists of values |
| Object or nested class | Nested object inside a document |
| Enum | A finite set of values |

Not every Java type is stored verbatim in Elasticsearch. The application must convert objects into a suitable data representation, usually JSON. Java types and mapping field types must be compatible to avoid conversion failures or incorrect search results.

For monetary data, pay attention to numerical precision. BigDecimal is generally more suitable than double at the business layer. When designing Elasticsearch mappings, select numeric types and storage representations matching the precision, range, and calculations your application requires.

### 2.5. Annotations and serialization

Annotations are metadata attached to classes, fields, or methods. Spring uses them to recognize components and behaviors to apply.

Serialization is the process of converting an object into a transmittable or storable format. Deserialization is converting received data back into an object.

Example of a Spring Data Elasticsearch document:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.elasticsearch.annotations.Document;
import org.springframework.data.elasticsearch.annotations.Field;
import org.springframework.data.elasticsearch.annotations.FieldType;

@Document(indexName = "products")
public class ProductDocument {

    @Id
    private String id;

    @Field(type = FieldType.Text)
    private String name;

    @Field(type = FieldType.Keyword)
    private String category;

    @Field(type = FieldType.Double)
    private BigDecimal price;

    public ProductDocument() {
    }

    // Constructors, getters, and setters are omitted in this example.
}
~~~

Meaning of the annotations above:

- **@Document** marks the class as representing a document in the index named products.
- **@Id** marks the document's identifier field.
- **@Field** describes the field type in Elasticsearch.
- **FieldType.Text** suits text that needs analysis for full-text search.
- **FieldType.Keyword** suits values needing exact matching, such as codes or categories.
- **FieldType.Double** represents decimal numeric values according to the chosen mapping.

This example illustrates mapping metadata only. A production class also needs constructors and property accessors compatible with the active mapping mechanism. Nor do annotations replace designing mappings aligned with query goals.

## 3. Spring and Spring Boot knowledge to master

### 3.1. IoC and Dependency Injection

Spring manages the lifecycle of objects called beans. Instead of instantiating every dependency with the new operator everywhere, a class can declare its dependencies and let Spring supply the right instances. This mechanism is known as Dependency Injection (DI), part of the Inversion of Control (IoC) principle.

For example, a service needing a repository:

~~~java
@Service
public class ProductService {

    private final ProductRepository productRepository;

    public ProductService(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    public Optional<Product> findById(String id) {
        return productRepository.findById(id);
    }
}
~~~

Spring creates and manages the appropriate beans, then passes ProductRepository into ProductService's constructor. This is constructor injection.

You should understand:

- What a bean is and how Spring manages beans.
- Component scanning and annotations such as @Component, @Service, and @Repository.
- Constructor injection.
- Why dependencies should be declared via interfaces when appropriate.
- The application context as the container where Spring manages beans and configuration.

### 3.2. Spring Boot and auto-configuration

Spring Boot reduces manual setup by auto-configuring beans based on dependencies on the classpath and configuration properties.

When you add the Spring Data Elasticsearch starter matching your Spring Boot version, the application can be auto-configured to create the necessary connection and integration components. Connection settings are typically placed in application.yml or application.properties.

Example Elasticsearch URI configuration:

~~~yaml
spring:
  elasticsearch:
    uris: http://localhost:9200
~~~

The address above is merely an example for a development environment running Elasticsearch locally. Other environments require corresponding addresses, authentication credentials, and security settings.

You should distinguish three separate pieces:

1. **Dependency**: the libraries required for the application to use Spring Data Elasticsearch.
2. **Configuration**: addresses and details needed to connect to Elasticsearch.
3. **Elasticsearch service**: the actual server or cluster receiving and processing requests.

Simply adding a dependency to the project does not mean an Elasticsearch server is installed or running.

### 3.3. Spring Data and Repositories

Spring Data provides a repository model to eliminate repetitive data access boilerplate. Rather than manually implementing every find, save, and delete operation, an application can extend a repository interface.

For example:

~~~java
public interface ProductRepository
        extends ElasticsearchRepository<ProductDocument, String> {

    List<ProductDocument> findByCategory(String category);
}
~~~

Spring Data can generate an implementation for the repository based on metadata and method-naming conventions. The findByCategory method is an example of query derivation: the method name describes the search condition.

You need to understand:

- A repository is a data access abstraction layer.
- An interface can extend built-in repository interfaces.
- Generic type parameters specify the document type and ID type.
- Query derivation builds queries from method names within supported rule limits.
- Complex queries may require query annotations, ElasticsearchOperations, or other suitable APIs.

A repository is not where all application business logic belongs. Typically, a service calls repositories, processes results, and enforces business rules.

### 3.4. Repository and ElasticsearchOperations

Spring Data Elasticsearch offers several ways to interact with data. Two common approaches are:

- **ElasticsearchRepository**: suited for familiar repository operations and pre-declared query methods.
- **ElasticsearchOperations**: offers a more flexible API when you need fine-grained control over saving, searching, deleting, or building queries.

You do not need to master both deeply from day one. First understand how repositories handle common data access needs, then explore the lower-level API when requirements demand tighter query control.

## 4. HTTP and REST API knowledge

### 4.1. HTTP is the protocol for exchanging requests and responses

Java applications typically communicate with Elasticsearch over HTTP. An HTTP request includes a method, URL, headers, and optionally a body. The server returns an HTTP response containing a status code, headers, and response body.

Example search request:

~~~http
POST /products/_search
Content-Type: application/json

{
  "query": {
    "match": {
      "name": "wireless keyboard"
    }
  }
}
~~~

In the example:

- POST is the HTTP method.
- /products/_search is the search endpoint on the products index.
- Content-Type indicates the body is sent as JSON.
- The body describes the search condition on the name field.

Common HTTP methods:

| Method | Typical purpose |
|---|---|
| GET | Read a resource or retrieve information |
| POST | Submit data or execute an operation described in the body |
| PUT | Create or replace a resource at a specific address, depending on the API |
| PATCH | Partially update a resource, if supported by the API |
| DELETE | Delete a resource |

Elasticsearch has its own endpoints and API conventions. Read the documentation for the specific API being called instead of assuming every endpoint follows the REST conventions of a typical CRUD application.

### 4.2. HTTP status codes and errors

Status codes to recognize:

| Status code | General meaning |
|---|---|
| 200 OK | The request succeeded |
| 201 Created | The resource was created successfully |
| 400 Bad Request | The request or payload is invalid |
| 401 Unauthorized | Missing or invalid authentication credentials |
| 403 Forbidden | Insufficient permissions to perform the operation |
| 404 Not Found | Resource or endpoint not found |
| 409 Conflict | Conflict with the current state |
| 500 Internal Server Error | Server-side error |
| 503 Service Unavailable | Service is temporarily unavailable |

When integrating Elasticsearch, errors can originate at multiple layers: the application sends a malformed request, a mapping is incompatible, an account lacks permissions, an endpoint does not exist, or the cluster is unavailable.

Never look solely at the status code. Read the response body and logs to pinpoint the exact cause. An HTTP 400 often names the exact field or data type that caused the query to be rejected.

### 4.3. URLs, paths, and query parameters

A URL identifies a resource or endpoint. The path typically indicates the index or operation type; query parameters add options to the request.

Example of a URL containing:

~~~text
/products/_search?pretty=true
~~~

Here products is the index, _search is the search endpoint, and pretty=true asks for formatted, human-readable responses in APIs supporting that option.

You should get comfortable reading URLs, distinguishing paths from query parameters, and reading request bodies. In search APIs, complex conditions normally live in the JSON body rather than being encoded entirely in the URL.

## 5. JSON knowledge to master

### 5.1. JSON structure

JSON is a text format for representing structured data. A JSON object contains key-value pairs; values can be strings, numbers, booleans, null, objects, or arrays.

Example product document:

~~~json
{
  "id": "P1001",
  "name": "Wireless Keyboard",
  "category": "ACCESSORY",
  "price": 49.9,
  "available": true,
  "tags": ["wireless", "keyboard"],
  "brand": {
    "id": "B01",
    "name": "Example"
  },
  "createdAt": "2026-11-13T10:30:00Z"
}
~~~

Structures to recognize:

- Objects use curly braces and hold key-value pairs.
- Arrays use square brackets and hold lists of values.
- Strings are always wrapped in double quotes.
- Numbers are not wrapped in quotes.
- Booleans take the value true or false.
- null represents an explicitly declared empty value.

Field names and data types must match consistently across submitted payloads, mappings, and queries.

### 5.2. JSON and Java objects

When an application sends a ProductDocument to Elasticsearch, the Java object is converted into a JSON representation. When receiving results, JSON data is mapped back into Java objects.

You can picture it as:

~~~text
ProductDocument (Java)
        |
        | serialization / mapping
        v
JSON document
        |
        | HTTP request
        v
Elasticsearch index
        |
        | search response
        v
JSON response
        |
        | deserialization / mapping
        v
ProductDocument (Java)
~~~

Key differences to watch out for:

- Java has many specific numeric types; JSON only represents numbers without distinguishing Integer, Long, or BigDecimal.
- Java has LocalDate, Instant, and various temporal types; JSON typically represents timestamps as strings or numbers by convention.
- Java objects may have unset fields; JSON may omit keys altogether or include keys with a null value.
- Java field names can be customized during JSON serialization or mapping.

An omitted field and a field with a null value represent two distinct states. When designing queries and mappings, know which representation your actual payloads send.

### 5.3. Date and time formats

Dates and times are commonly represented as ISO 8601 strings, for example:

~~~json
{
  "createdAt": "2026-11-13T10:30:00Z"
}
~~~

The Z character denotes UTC time. A string with an offset such as +07:00 also expresses an explicit time zone.

When working with dates and times, standardize:

- Whether the application uses LocalDate, LocalDateTime, or Instant.
- Whether payloads are sent in UTC or with offsets.
- Which formats the Elasticsearch mapping accepts.
- How the application converts time zones when displaying values to users.

Mismatches in time zones or formats can cause time-range queries to return missing or extra results.

## 6. Foundational search and Elasticsearch concepts

### 6.1. Index, document, and field

Elasticsearch stores data as JSON documents.

| Concept | How to understand it |
|---|---|
| Cluster | A group of one or more nodes operating together |
| Node | An Elasticsearch process participating in a cluster |
| Index | A storage and search space for a group of documents |
| Document | A structured JSON record |
| Field | An attribute inside a document |
| Mapping | Rules defining how Elasticsearch interprets and processes fields |
| Shard | A data partition of an index |
| Replica | A copy of a shard providing availability and read capacity |

At an introductory level, you can draw a rough analogy:

- An index is roughly comparable to a table in a relational database.
- A document is roughly comparable to a row of data.
- A field is roughly comparable to a column.

This is only a mental shortcut for intuition. Elasticsearch is a document search engine; its storage, querying, data relationships, and updates differ substantially from relational databases.

A document can contain nested objects or lists of values. Document design generally prioritizes the read and search patterns the application needs, sometimes accepting duplicated data to avoid combining multiple sources at query time.

### 6.2. Mapping and field types

Mappings tell Elasticsearch how to interpret each field. Choosing field types directly impacts how data is indexed, searched, sorted, and aggregated.

Common types:

| Field type | Typical purpose |
|---|---|
| text | Text requiring analysis for full-text search |
| keyword | Strings needing exact matching, filtering, grouping, or sorting |
| long, integer | Integers |
| float, double | Floating-point numbers |
| boolean | True/false values |
| date | Dates or timestamps |
| object | Nested JSON objects |
| nested | Lists of objects needing per-element field relationships preserved during queries |

Two types—text and keyword—are especially important:

- **text** is typically passed through an analyzer before indexing. It suits content such as product names, descriptions, or articles.
- **keyword** is indexed as a single unsplit value without tokenizing into words. It suits product codes, statuses, categories, or emails where whole-value matching is needed.

For instance, a category field with values ACCESSORY, BOOK, and COMPUTER usually fits keyword. A description field containing sentences usually fits text.

Picking the wrong field type can break expected query results. For example, running a term query against an analyzed text field may fail to match the original string because the data was indexed as individual tokens.

Mappings should be designed based on how data is queried. Do not choose field types based solely on the Java type or property name.

### 6.3. Analyzers and the text analysis process

An analyzer is the component that processes text before placing it into the inverted index. An analyzer typically consists of:

1. Character filter: preprocesses the input string before tokenization.
2. Tokenizer: splits text into tokens.
3. Token filter: transforms or drops tokens, such as lowercasing or removing stop words per configuration.

For example, the text:

~~~text
"Wireless Keyboard for Office"
~~~

can be analyzed into the tokens:

~~~text
["wireless", "keyboard", "for", "office"]
~~~

This is only an illustrative example. Actual output depends on the configured analyzer, language, and filters.

Analyzers shape search recall and precision. For English, standard analyzers can tokenize words and normalize casing. For Vietnamese, pay attention to diacritics, compound words, and word boundaries; default analyzers do not necessarily handle every linguistic requirement well. Designing analyzers for Vietnamese must be validated with realistic data and queries.

### 6.4. Exact search and full-text search

There are two fundamental search needs:

**Exact search** matches exact values, typically used for codes, statuses, categories, or business identifiers.

**Full-text search** searches natural-language text by words or phrases, accounting for text analysis and relevance ranking.

Elasticsearch offers many query types. Two queries to distinguish right away are term and match:

- **term query** looks up exact indexed terms/values; it does not analyze the input string like a full-text query.
- **match query** analyzes the query string using the field's analyzer and searches for corresponding tokens.

For example, with a keyword category field, a term query suits finding the exact ACCESSORY category. With a text name field, match suits finding products related to the phrase wireless keyboard.

Never assume term always compares the raw original user string literally. Results depend on the field type and how the data was indexed.

### 6.5. Relevance and score

In full-text search, Elasticsearch can compute a relevance score for each match. This score is commonly called _score.

Higher-scoring results typically rank earlier because they match the query more closely under the active scoring algorithm. However, score is not an absolute business metric and should not be interpreted as a percentage accuracy.

For example, when searching "wireless keyboard", a document containing both words in its product name may rank higher than one mentioning only one word in its description. Actual ranking depends on analyzers, queries, similarity settings, and index contents.

### 6.6. Filters, sorting, and pagination

A search page usually needs more than text matching conditions:

- **Filter** narrows the result set by conditions such as category, available, or price range.
- **Sort** orders results by price, creation date, or score.
- **Pagination** splits results into pages.
- **Aggregation** computes statistics such as product counts per category or price bracket.

Distinguish filters from full-text conditions. Filters generally apply yes/no constraints and do not aim to compute relevance scores. Full-text queries typically participate in calculating _score.

Basic pagination can use a page size and starting offset. For large datasets, fetching very deep pages has performance limits and may require a different pagination mechanism such as search_after. You will explore this when learning specific query APIs.

## 7. Putting the pieces into one processing flow

Suppose an application needs to search products by name and filter by category.

1. The client sends an HTTP request to the Controller.
2. The Controller reads the keyword, category, and pagination details.
3. The Service validates parameters and applies business rules.
4. A Repository or ElasticsearchOperations builds the search operation.
5. Spring Data Elasticsearch translates object/query information into an appropriate request.
6. Elasticsearch analyzes keywords, applies mappings, finds documents, and ranks results.
7. Elasticsearch returns a JSON response.
8. Spring Data maps results back into Java objects.
9. The Service and Controller return data to the client.

This flow connects all the prerequisites covered:

| Prerequisite | Role in the flow |
|---|---|
| Java classes and objects | Represent documents and search results |
| Generics and interfaces | Declare repositories with document and ID types |
| Annotations | Provide metadata for mapping and Spring |
| Spring DI | Inject repositories into services |
| HTTP | Transmit requests and responses between app and Elasticsearch |
| JSON | Represent documents, queries, and results |
| Mapping | Define how Elasticsearch interprets fields |
| Analyzers and queries | Govern how text search works |
| Filters, sorting, pagination | Control the returned result set |

Understanding this flow helps you know where to investigate when results look wrong: Java data, JSON conversion, mapping, analyzers, queries, or connection settings.

## 8. Common pitfalls to avoid

**Assuming Elasticsearch is a relational database.** Elasticsearch supports storing and querying documents, but do not mechanically apply relational joins, transactions, and normalization habits.

**Assuming every string should use text.** Codes, statuses, and categories usually need keyword for filtering or exact matching.

**Assuming term and match are interchangeable.** They process inputs differently. Choose the query based on field type and search intent.

**Assuming adding the starter is enough to run.** The application still needs a reachable Elasticsearch server and valid connection settings.

**Assuming Java field names determine the entire mapping.** Property names, annotations, live mappings, and sent JSON must stay consistent; do not infer field types solely from Java names or types.

**Assuming empty results mean an error.** A valid query can legitimately return an empty list. Distinguish empty results from HTTP errors, mapping errors, or connection failures.

**Ignoring the language of your data.** An analyzer tuned for English may not handle Vietnamese the way users expect. Verify with real keywords and datasets.

**Skipping inspection of actual JSON payloads.** When a query fails to work, inspect the indexed documents and actual responses. Do not guess stored data purely from Java classes.

## 9. Readiness checklist before continuing to the next lessons

You can gauge your readiness with these questions:

- Can I write a Java class representing a document with an ID, strings, numbers, booleans, and lists?
- Do I understand interfaces and generics, and can I read a repository declaration with two type parameters?
- Do I understand constructor injection and the roles of Controller, Service, and Repository in a Spring application?
- Do I know that Spring Boot reads configuration from application.yml and how a dependency differs from a running Elasticsearch service?
- Can I read an HTTP request consisting of a method, URL, headers, and JSON body?
- Can I read JSON objects, arrays, strings, numbers, booleans, and null?
- Can I distinguish index, document, field, and mapping?
- Do I understand why text and keyword serve two different search needs?
- Can I distinguish exact search from full-text search, and term queries from match queries?
- Do I understand filters, sorting, pagination, and relevance scores at a conceptual level?

If anything feels shaky, review the corresponding section beforehand or alongside the hands-on lessons. You do not need to memorize every API upfront; what matters is understanding which layers data passes through and what each layer is responsible for.

Once you have this foundation down, you are ready to learn how to connect Spring Boot to Elasticsearch, declare documents and mappings, use repositories, build queries, and handle search results.
