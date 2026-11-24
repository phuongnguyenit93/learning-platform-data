# @GraphQlTest and the Scope of Resolvers and Controllers Under Test

## 1. What is @GraphQlTest used for?

In Spring Boot, a GraphQL API does not directly map each controller method to a REST URL. A GraphQL document is parsed against a **schema**, type-checked along with its variables, and then GraphQL execution invokes the corresponding **data fetchers/resolvers**: @QueryMapping for root queries, @MutationMapping for mutations, @SchemaMapping for nested fields, and related mappings. A unit test calling controller.bookById("b1") directly does not prove that a GraphQL operation actually invokes the right resolver, or that the schema, fields, arguments, and nullability are configured properly.

**@GraphQlTest** is Spring Boot's test slice for Spring GraphQL. It configures the GraphQL infrastructure and the selected controllers, allowing operations to be sent with **GraphQlTester** **without starting an HTTP server or WebSocket transport**. It tests mappings and schemas faster than a full @SpringBootTest while exercising more of the GraphQL engine than a plain Java unit test.

**Lesson objectives:** you will distinguish between a test slice and full HTTP integration; understand which controllers are selected; provide @MockBean for collaborators outside the slice; test @QueryMapping, @SchemaMapping, @Argument, selection sets, nullable fields, and errors; use GraphQlTester.document/documentName/variable/execute/path; and decide when to move to HttpGraphQlTester with RANDOM_PORT.

**Sample versions:** Java 17, Spring Boot **3.3.5**, Spring for GraphQL/GraphQL Java managed by the Spring Boot BOM, Gradle, JUnit Jupiter, Mockito. In version 3.3, @GraphQlTest is in **org.springframework.boot.test.autoconfigure.graphql**, and @MockBean is in **org.springframework.boot.test.mock.mockito**. In newer versions, especially starting from Spring Boot 3.4, the mocking mechanism shifts to @MockitoBean; do not mix packages from different versions in this project.

**Parent context "GraphQL and SOAP":** @GraphQlTest is a tool for GraphQL; it does **not** automatically test a SOAP @Endpoint, WSDL, or SOAP XML envelope. Those belong to the scope of Spring Web Services/SOAP testing.

## 2. Controller scope and loaded beans

| Component | Included by default in @GraphQlTest? | Significance |
|---|---|---|
| GraphQL schema, GraphQlSource, execution infrastructure | Yes, via test auto-configuration | Can execute GraphQL documents |
| GraphQlTester when spring-graphql-test is present | Yes | Sends operations without HTTP |
| Selected GraphQL @Controller | Yes | @QueryMapping/@SchemaMapping registers resolvers |
| Other controllers if only one class is selected | No | The slice can focus on a single controller |
| RuntimeWiringConfigurer, converters, JsonComponent, Instrumentation, DataFetcherExceptionResolver, GraphQlSourceBuilderCustomizer | Allowed by Boot 3.3's filter | Appropriate GraphQL configuration/wiring |
| Regular **@Service, @Repository** | **Not auto-scanned** | Need to mock or import beans |
| Regular @ConfigurationProperties | Not auto-scanned | May need @EnableConfigurationProperties |
| HTTP server, servlet filters, cookies, auth transport | **No** | Does not prove /graphql is reachable over the network |
| Database/external systems | Not by default | Not a persistence/E2E test |

Declaring an explicit scope:

~~~java
@GraphQlTest(BookGraphQlController.class)
class BookGraphQlControllerSliceTest {
    // Real Book controller, collaborators provided by the test fixture.
}
~~~

If you write **@GraphQlTest** without a class selector, the slice scans GraphQL controllers matching the default filter. Specifying a single controller avoids loading other controllers with unrelated dependencies. However, it **does not automatically strip other fields from schema.graphqls**: the schema and the list of resolver beans are two separate concepts. Having a field in the SDL does not prove that its corresponding @Controller was loaded.

**@GraphQlTest does not replace @WebMvcTest.** Both are slice tests, but @WebMvcTest tests Spring MVC request mapping with MockMvc, whereas @GraphQlTest tests the GraphQL schema and data fetchers with GraphQlTester. A GraphQL @Controller can contain @QueryMapping rather than @GetMapping or @PostMapping on individual fields.

## 3. Schema, resolver, and selection set mechanics

Sample schema:

~~~graphql
type Query {
  bookById(id: ID!): Book
  systemStatus: String!
}

type Book {
  id: ID!
  title: String!
  stock: Int!
  stockLabel: String!
}
~~~

- **Query.bookById** requires an **id: ID!** argument. If it is missing or null, the GraphQL engine can return an error before the resolver runs.
- The **Book** return type has no `!`, so it is nullable: when a Book is not found, it can return null rather than HTTP 404.
- The **stockLabel: String!** field requires a String if selected on an existing Book.
- **systemStatus** is handled by a second controller, convenient for testing selected controller scope.
- The id/title/stock fields have Java getters; stockLabel requires @SchemaMapping.

Resolver example:

~~~java
@Controller
class BookGraphQlController {

    @QueryMapping
    Book bookById(@Argument("id") String id) {
        return catalog.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "stockLabel")
    String stockLabel(Book book) {
        return catalog.labelForStock(book.getStock());
    }
}
~~~

This is a conceptual snippet; the complete file below includes the field and constructor. @QueryMapping maps Query.bookById by method name by default, and @SchemaMapping(typeName="Book",field="stockLabel") handles the nested field and receives the **Book source object**.

**The selection set determines which handlers run.** With the document:

~~~graphql
{
  bookById(id: "b1") {
    id
    title
  }
}
~~~

GraphQL needs the root resolver and the id/title fields, **and does not need to call stockLabel**. A proper test must assert the result and **verify(catalog, never()).labelForStock(anyInt())**. Only when stockLabel is added to the query is the nested resolver invoked. This is the basis for understanding lazy field fetching and N+1 risk; it does not mean the slice verifies actual SQL query counts when the service is mocked.

**GraphQL errors differ from HTTP errors:** parse/validation/coercion failures and data fetching failures can appear in the GraphQL response **errors** array. In @GraphQlTest there is no HTTP request, so HTTP status cannot be asserted. With GraphQL over HTTP, errors in the body do not automatically mean HTTP 404/500; the exact status depends on the scenario and transport contract. Always verify at the appropriate layer.

## 4. Complete Spring Boot 3.3.5 hands-on project

Example:
- Book b1: title **Spring GraphQL Patterns**, stock=5, stockLabel **IN_STOCK**.
- Book b2: title **Testing GraphQL**, stock=0, stockLabel **OUT_OF_STOCK**.
- Non-existent Book: bookById returns null.
- SystemStatusGraphQlController returns **READY** for Query.systemStatus.
- The real service uses an immutable Map.of; slice tests mock the service, while HTTP tests use the real service.

### 4.1. Structure

~~~text
settings.gradle
build.gradle
src/main/resources/graphql/schema.graphqls
src/main/java/demo/graphql/GraphQlApplication.java
src/main/java/demo/graphql/Book.java
src/main/java/demo/graphql/BookCatalogService.java
src/main/java/demo/graphql/BookGraphQlController.java
src/main/java/demo/graphql/SystemStatusGraphQlController.java
src/test/resources/graphql-test/bookById.graphql
src/test/java/demo/graphql/BookGraphQlControllerSliceTest.java
src/test/java/demo/graphql/SystemStatusGraphQlSliceTest.java
src/test/java/demo/graphql/GraphQlFullHttpTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'graphql-test-scope-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.graphql:spring-graphql-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-webflux'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Intentional dependencies:** starter-graphql brings in Spring for GraphQL and GraphQL Java; starter-web provides Spring MVC/embedded Tomcat so full HTTP tests can connect to /graphql. spring-graphql-test contains GraphQlTester. starter-webflux in testImplementation supplies WebTestClient client support for HttpGraphQlTester while the production web server remains MVC by Spring Boot's default preference. starter-test provides JUnit Jupiter, Mockito, and AssertJ. Dependency versions are managed by the BOM, avoiding manual selection of incompatible Spring GraphQL versions.

### 4.2. Schema and query fixture

**src/main/resources/graphql/schema.graphqls**

~~~graphql
type Query {
  bookById(id: ID!): Book
  systemStatus: String!
}

type Book {
  id: ID!
  title: String!
  stock: Int!
  stockLabel: String!
}
~~~

**src/test/resources/graphql-test/bookById.graphql**

~~~graphql
query BookById($id: ID!) {
  bookById(id: $id) {
    id
    title
    stock
    stockLabel
  }
}
~~~

Spring Boot looks for *.graphqls/*.gqls under **src/main/resources/graphql/** by default. GraphQlTester.documentName("bookById") looks for operation fixtures under **classpath:graphql-test/**. These two locations are different; do not put the schema in graphql-test expecting the application to load it, and do not put query fixtures in graphql/ expecting documentName to find them automatically.

### 4.3. Application, model, and service

**src/main/java/demo/graphql/GraphQlApplication.java**

~~~java
package demo.graphql;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GraphQlApplication {

    public static void main(String[] args) {
        SpringApplication.run(GraphQlApplication.class, args);
    }
}
~~~

**src/main/java/demo/graphql/Book.java**

~~~java
package demo.graphql;

public final class Book {

    private final String id;
    private final String title;
    private final int stock;

    public Book(String id, String title, int stock) {
        this.id = id;
        this.title = title;
        this.stock = stock;
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public int getStock() {
        return stock;
    }
}
~~~

Book has getters for GraphQL Java's default property fetching of id/title/stock. There is no stockLabel getter, so that field is only provided by @SchemaMapping. The final Java fields keep the fixture immutable.

**src/main/java/demo/graphql/BookCatalogService.java**

~~~java
package demo.graphql;

import java.util.Map;

import org.springframework.stereotype.Service;

@Service
public class BookCatalogService {

    private final Map<String, Book> books = Map.of(
            "b1", new Book("b1", "Spring GraphQL Patterns", 5),
            "b2", new Book("b2", "Testing GraphQL", 0)
    );

    public Book findById(String id) {
        return books.get(id);
    }

    public String labelForStock(int stock) {
        return stock > 0 ? "IN_STOCK" : "OUT_OF_STOCK";
    }
}
~~~

This is the real service in the full context. It has no database or mutable shared state. In @GraphQlTest, @Service **is not scanned by default**, so @MockBean is needed for the controller to receive its dependency.

### 4.4. Two controllers

**src/main/java/demo/graphql/BookGraphQlController.java**

~~~java
package demo.graphql;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookGraphQlController {

    private final BookCatalogService catalog;

    public BookGraphQlController(BookCatalogService catalog) {
        this.catalog = catalog;
    }

    @QueryMapping
    public Book bookById(@Argument("id") String id) {
        return catalog.findById(id);
    }

    @SchemaMapping(typeName = "Book", field = "stockLabel")
    public String stockLabel(Book book) {
        return catalog.labelForStock(book.getStock());
    }
}
~~~

**src/main/java/demo/graphql/SystemStatusGraphQlController.java**

~~~java
package demo.graphql;

import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class SystemStatusGraphQlController {

    @QueryMapping
    public String systemStatus() {
        return "READY";
    }
}
~~~

These are @Controller classes for the GraphQL engine, not REST controllers. The root Book resolver accepts the GraphQL argument id; the nested resolver accepts the parent Book. The Status controller injects no service, which helps demonstrate that an isolated slice does not need to mock BookCatalogService.

## 5. BookGraphQlControllerSliceTest — 7 @Test methods

**src/test/java/demo/graphql/BookGraphQlControllerSliceTest.java**

~~~java
package demo.graphql;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.ApplicationContext;
import org.springframework.graphql.test.tester.GraphQlTester;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.anyInt;
import static org.mockito.Mockito.mockingDetails;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@GraphQlTest(BookGraphQlController.class)
class BookGraphQlControllerSliceTest {

    @Autowired
    GraphQlTester tester;

    @Autowired
    ApplicationContext context;

    @MockBean
    BookCatalogService catalog;

    @Test
    void loadsSelectedControllerAndMock() {
        assertThat(context.getBeansOfType(
                BookGraphQlController.class)).hasSize(1);
        assertThat(context.getBeansOfType(
                SystemStatusGraphQlController.class)).isEmpty();
        assertThat(mockingDetails(catalog).isMock()).isTrue();
    }

    @Test
    void resolvesRootAndNestedFieldUsingQueryDocument() {
        when(catalog.findById("b1"))
                .thenReturn(new Book(
                        "b1", "Spring GraphQL Patterns", 5));
        when(catalog.labelForStock(5))
                .thenReturn("IN_STOCK");

        tester.documentName("bookById")
                .variable("id", "b1")
                .execute()
                .path("bookById.stockLabel")
                .entity(String.class)
                .isEqualTo("IN_STOCK");

        verify(catalog).findById("b1");
        verify(catalog).labelForStock(5);
    }

    @Test
    void unselectedNestedFieldIsNotFetched() {
        when(catalog.findById("b1"))
                .thenReturn(new Book(
                        "b1", "Spring GraphQL Patterns", 5));

        tester.document("""
                {
                  bookById(id: "b1") {
                    id
                    title
                  }
                }
                """)
                .execute()
                .path("bookById.title")
                .entity(String.class)
                .isEqualTo("Spring GraphQL Patterns");

        verify(catalog).findById("b1");
        verify(catalog, never()).labelForStock(anyInt());
    }

    @Test
    void absentBookIsAValidNullField() {
        tester.document("""
                {
                  bookById(id: "absent") { id }
                }
                """)
                .execute()
                .path("bookById")
                .valueIsNull();

        verify(catalog).findById("absent");
    }

    @Test
    void missingRequiredVariableCreatesGraphqlError() {
        tester.document("""
                query FindBook($id: ID!) {
                  bookById(id: $id) { id }
                }
                """)
                .execute()
                .errors()
                .satisfy(errors -> assertThat(errors).isNotEmpty());

        verifyNoInteractions(catalog);
    }

    @Test
    void outOfStockInvokesFieldResolver() {
        when(catalog.findById("b2"))
                .thenReturn(new Book(
                        "b2", "Testing GraphQL", 0));
        when(catalog.labelForStock(0))
                .thenReturn("OUT_OF_STOCK");

        tester.document("""
                {
                  bookById(id: "b2") {
                    stock
                    stockLabel
                  }
                }
                """)
                .execute()
                .path("bookById.stockLabel")
                .entity(String.class)
                .isEqualTo("OUT_OF_STOCK");

        verify(catalog).findById("b2");
        verify(catalog).labelForStock(0);
    }

    @Test
    void nullParentDoesNotInvokeNestedResolver() {
        tester.document("""
                {
                  bookById(id: "missing") {
                    stockLabel
                  }
                }
                """)
                .execute()
                .path("bookById")
                .valueIsNull();

        verify(catalog).findById("missing");
        verify(catalog, never()).labelForStock(anyInt());
    }
}
~~~

**Why are all seven tests important?**

1. **Bean scope:** Book controller is present, Status controller is absent; BookCatalogService is a Mockito mock provided by @MockBean.
2. **GraphQL document:** documentName reads the query fixture properly, the id variable is bound by @Argument; both root and nested resolvers run and mock interactions are verified.
3. **Selection set:** Not selecting stockLabel ⇒ the nested resolver does not run. The test proves this with never(), not just by inspecting JSON.
4. **Nullable field:** An unstubbed mock for "absent" returns null; the bookById: Book schema allows null, so valueIsNull() is valid.
5. **Required variable:** Missing $id: ID! leads to GraphQL errors before the controller runs; verifyNoInteractions proves the service was not called. Avoid comparing exact error text that may change across GraphQL Java versions.
6. **Out of stock:** b2 has stock=0; the field resolver is called and returns OUT_OF_STOCK.
7. **Null parent:** When Book is null there is no source object for stockLabel; the nested resolver does not run.

**Important note:** An existing Book whose stockLabel: String! resolves to null **differs** from a non-existent nullable Book: GraphQL can report a non-null violation and null bubbling in the first case. When mocking a nested collaborator, stub it properly if the query requests a non-null field.

**@MockBean vs @Mock:** Spring Boot 3.3's @MockBean registers a mock bean in the Spring container so it gets injected into the controller. MockitoExtension's @Mock only creates a test field and does not automatically become a Spring bean. Spring Boot normally resets @MockBean after each method per MockReset.AFTER, so manual Mockito.reset or test ordering is unnecessary.

## 6. SystemStatusGraphQlSliceTest — 2 @Test methods

**src/test/java/demo/graphql/SystemStatusGraphQlSliceTest.java**

~~~java
package demo.graphql;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.context.ApplicationContext;
import org.springframework.graphql.test.tester.GraphQlTester;

import static org.assertj.core.api.Assertions.assertThat;

@GraphQlTest(SystemStatusGraphQlController.class)
class SystemStatusGraphQlSliceTest {

    @Autowired
    GraphQlTester tester;

    @Autowired
    ApplicationContext context;

    @Test
    void excludesBookControllerAndCatalogService() {
        assertThat(context.getBeansOfType(
                SystemStatusGraphQlController.class)).hasSize(1);
        assertThat(context.getBeansOfType(
                BookGraphQlController.class)).isEmpty();
        assertThat(context.getBeansOfType(
                BookCatalogService.class)).isEmpty();
    }

    @Test
    void executesStatusResolver() {
        tester.document("{ systemStatus }")
                .execute()
                .path("systemStatus")
                .entity(String.class)
                .isEqualTo("READY");
    }
}
~~~

Here there is no need to mock BookCatalogService: the controller is selected independently and the Book controller is absent. The schema still contains Book/bookById, but the test operation only selects systemStatus and its resolver exists. A slice does not require executing all schema fields if the query does not select them.

If @GraphQlTest has no controller selector and scans both controllers, Book controller's dependencies must be provided even if you only write status tests. Selecting controllers explicitly usually keeps the context smaller and easier to diagnose.

## 7. GraphQlFullHttpTest — 3 real HTTP test methods

To verify the /graphql transport and the real service, switch to @SpringBootTest(RANDOM_PORT).

**src/test/java/demo/graphql/GraphQlFullHttpTest.java**

~~~java
package demo.graphql;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.HttpGraphQlTester;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GraphQlFullHttpTest {

    @Autowired
    HttpGraphQlTester tester;

    @Test
    void bookQueryUsesActualCatalogService() {
        tester.document("""
                {
                  bookById(id: "b1") {
                    title
                    stockLabel
                  }
                }
                """)
                .execute()
                .path("bookById.stockLabel")
                .entity(String.class)
                .isEqualTo("IN_STOCK");
    }

    @Test
    void fullContextIncludesStatusController() {
        tester.document("{ systemStatus }")
                .execute()
                .path("systemStatus")
                .entity(String.class)
                .isEqualTo("READY");
    }

    @Test
    void missingBookIsNullableOverHttp() {
        tester.document("""
                {
                  bookById(id: "missing") { id }
                }
                """)
                .execute()
                .path("bookById")
                .valueIsNull();
    }
}
~~~

According to Spring Boot 3.3 documentation, when spring-graphql-test and suitable WebTestClient dependencies are on the test classpath, @SpringBootTest(RANDOM_PORT) auto-configures HttpGraphQlTester pointing to the running embedded server. **Unlike @GraphQlTest**, these requests go over the HTTP transport. The full app loads the real BookCatalogService (Map.of) and both controllers.

**Limitations:** There is no database, security, proxy, or WebSocket subscription in this example. Do not treat these three HTTP tests as proof of persistence, login, CSRF, WebSocket handshake, or production deployment. Testing those requirements needs dedicated configuration and tests.

## 8. Running tests, counting, and viewing reports

| Test class | Number of @Test methods | Scope |
|---|---:|---|
| BookGraphQlControllerSliceTest | **7** | Book resolver + mocked service |
| SystemStatusGraphQlSliceTest | **2** | Status controller |
| GraphQlFullHttpTest | **3** | Full HTTP + real service |
| **Total** | **12** | 9 slice tests + 3 HTTP tests |

This is **12 test methods from these exact three source classes**, excluding illustrative snippets outside them. If a project has additional tests, Gradle's total can be higher. No test ordering is needed: each slice test stubs independently, and the real service is immutable.

Use the Gradle Wrapper if available:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

If you created the files manually without a Wrapper, ./gradlew does not exist yet; use a compatible Gradle to generate the wrapper or run gradle test. The HTML report is typically at **build/reports/tests/test/index.html**. Running individually:

~~~bash
./gradlew test --tests demo.graphql.BookGraphQlControllerSliceTest
./gradlew test --tests demo.graphql.SystemStatusGraphQlSliceTest
./gradlew test --tests demo.graphql.GraphQlFullHttpTest
~~~

With different @GraphQlTest controller sets, Spring TestContext can have separate cache keys. With RANDOM_PORT, the full app must start an embedded server. That is an intentional difference, not a test error.

## 9. GraphQlTester API usage to get right

**document(String):** Sends an inline GraphQL operation text:

~~~java
tester.document("""
        {
          bookById(id: "b1") { title }
        }
        """)
    .execute()
    .path("bookById.title")
    .entity(String.class)
    .isEqualTo("Spring GraphQL Patterns");
~~~

This snippet must run inside a test that has stubbed the service or uses the real service; if a mock has not stubbed findById("b1"), Book can be null and cause the assertion to fail.

**documentName(String):** Loads a query file by name from the classpath graphql-test/ directory. The name bookById reads bookById.graphql created in section 4. This is a test operation, not schema.graphqls.

**variable(String,Object):** Passes GraphQL variables matching the schema instead of concatenating input strings:

~~~java
tester.document("""
        query FindBook($id: ID!) {
          bookById(id: $id) { title }
        }
        """)
    .variable("id", "b1")
    .execute()
    .path("bookById.title")
    .entity(String.class)
    .isEqualTo("Spring GraphQL Patterns");
~~~

**path(...):** A path relative to the **data** section of the GraphQL response; path("bookById.title") corresponds to data.bookById.title. **valueIsNull()** differs from **pathDoesNotExist()**: null means the field is present with a null value, whereas a non-existent path can occur because the operation omitted the field or the schema/data shape differs.

**errors():** A GraphQL response can contain errors even when partial data is present. When intentionally testing errors:

~~~java
tester.document("""
        query FindBook($id: ID!) {
          bookById(id: $id) { id }
        }
        """)
    .execute()
    .errors()
    .satisfy(errors -> assertThat(errors).isNotEmpty());
~~~

errors().satisfy(...) receives the list and marks them as checked. **errors().expect(predicate).verify()** requires an error matching the predicate; **filter(predicate).verify()** ignores matching errors if present but does not require them to appear. Do not filter all errors unconditionally as that masks bugs. Never claim every GraphQL error maps to HTTP 400/404/500.

## 10. Other mappings/resolvers and test boundaries

| Mapping or extension | What @GraphQlTest verifies | Not verified |
|---|---|---|
| **@QueryMapping** | Root query, argument binding, output/errors | HTTP auth, real DB |
| **@MutationMapping** | Mutation resolver, mocked collaborators | DB commit/transaction/security |
| **@SchemaMapping** | Nested fields, source object, selection set | SQL N+1 when repository is mocked |
| **@BatchMapping** | Batch field invocation on selected objects | DB performance without real repo |
| **@SubscriptionMapping** | Publisher execution with appropriate tester | WebSocket/RSocket transport |
| **RuntimeWiringConfigurer** | Custom scalar/data fetcher if bean is in slice | Wiring outside the slice |
| **DataFetcherExceptionResolver** | GraphQL error mapping at the execution layer | HTTP status/error page |
| **@GraphQlExceptionHandler** | Handler if controller/advice is loaded | Not identical to MVC REST @ExceptionHandler |

A schema using a custom scalar like DateTime can fail startup if RuntimeWiringConfigurer is not registered in the right place. If this bean lives in a @Configuration excluded by the slice filter, use **@Import** for the needed config or a small @TestConfiguration. Do not reach for @SpringBootTest to "fix every missing bean error" when the goal is only a controller slice.

**ControllerAdvice in GraphQL:** Can contain @GraphQlExceptionHandler depending on the design. Do not assume every REST @ControllerAdvice is scanned and applied by @GraphQlTest. Check whether the handler bean itself is in the slice; @Import an appropriate advice if testing error mapping requires it.

**@MockBean vs @Mock vs @Import:**
- Boot 3.3's @MockBean creates a **Spring mock bean**, used for wiring Spring-created controllers.
- MockitoExtension's @Mock creates a **Mockito field** in the test and is not automatically injected into the Spring ApplicationContext.
- @Import brings a real bean/config into the slice, suitable for formatters or wiring under test; avoid importing the entire app and pulling in unnecessary databases/external services.
- A unit test without a Spring context calls new controller(fakeService) directly; it is fast, **but does not verify schema/mapping**.

## 11. Common errors

| Symptom | Cause | Resolution |
|---|---|---|
| @Autowired GraphQlTester has no bean | Missing spring-graphql-test/auto-config | Add the right test dependency version |
| Context missing BookCatalogService | @Service excluded from slice | @MockBean or @Import |
| Used @Mock but controller still lacks dependency | Mockito field is not a Spring bean | Boot 3.3 @MockBean |
| Schema fails to initialize | schema.graphqls missing/wrong type/custom scalar | Check graphql/** and RuntimeWiringConfigurer |
| Query field not found | SDL and document mismatch | Compare field/argument names |
| documentName not found | File at wrong path/extension | graphql-test/bookById.graphql |
| Another controller is missing | @GraphQlTest selects only one class | Select the right controller or another slice |
| Root field is null | Mock not stubbed or service returned null | Check nullable contract/fixture |
| Nested resolver does not run | Field not in selection set, parent null, or wrong typeName | Check schema, query, and @SchemaMapping |
| Resolver returns null for String! | Non-null violation | Fix stub/logic, test GraphQL errors |
| ID! variable error before service runs | GraphQL coercion/validation | .errors().satisfy, verifyNoInteractions |
| Slice passes but HTTP /graphql fails | @GraphQlTest does not run HTTP transport | RANDOM_PORT + HttpGraphQlTester |
| HttpGraphQlTester fails to autowire | Missing WebTestClient deps or wrong test mode | starter-webflux test + RANDOM_PORT |
| Global advice does not run | Advice not included in bean filter | @Import/check classpath |
| Test passes alone but fails in suite | Unisolated fixture/mock/global state | Create isolated data, avoid order dependence |

**Debugging workflow:** check schema → check @GraphQlTest selector → check controller beans → provide collaborators → send minimal query → inspect GraphQL errors before data paths → check nested field selection → escalate to HTTP/full context only when risk demands it.

## 12. Choosing between slice and full integration

Choose **@GraphQlTest** when you need:
- Schema fields, GraphQL syntax, and argument binding.
- Isolation of specific @Controller beans in a slice.
- @QueryMapping/@SchemaMapping and selection set behavior.
- GraphQL nullability and error mapping.
- Isolated collaborators to test the presentation layer.

Choose **@SpringBootTest(RANDOM_PORT) + HttpGraphQlTester** when you need:
- Verification of HTTP POST /graphql, real port, and codecs/headers.
- Security filters/authentication, sessions/cookies/CSRF.
- Full bean wiring and real services/repositories.
- Error handling over transport, status codes, and content types.
- Integration with external services or persistence using a dedicated test environment.

In particular, **@Transactional on a JUnit test method does not automatically roll back database transactions committed by an HTTP server request**, because the test client and server execute in different threads and transaction scopes. If a mutation writes data, use a dedicated test DB/intentional cleanup or Testcontainers.

## 13. Exercises

1. Write another @GraphQlTest without a class selector; observe why Book controller dependencies must be satisfied even when the query only selects systemStatus.
2. Change the selection set from id/title to id/title/stockLabel and use Mockito.verify to prove the nested resolver runs when selected.
3. Change stockLabel: String! to nullable String; design a test distinguishing a null field from GraphQL errors.
4. Add @MutationMapping createBook with an input type argument; test the slice with mocks and full integration with DB cleanup.
5. Create a custom DateTime scalar. When the slice lacks RuntimeWiringConfigurer, fix the test by @Importing the right bean.
6. Write a test with a missing ID! variable, check errors and verifyNoInteractions.
7. Add Spring Security to the HTTP app and demonstrate why @GraphQlTest cannot replace /graphql transport auth testing.
8. Explain why @GraphQlTest does not test a SOAP @Endpoint/WSDL.

## 14. References

- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): @GraphQlTest, scope, @MockBean, tester variants.
- [Spring Boot 3.3 — Spring for GraphQL](https://docs.spring.io/spring-boot/3.3/reference/web/spring-graphql.html): starter, schema files, and HTTP transport.
- [Spring for GraphQL — Testing](https://docs.spring.io/spring-graphql/reference/testing.html): document, variables, path, and errors.
- [Spring for GraphQL 1.3 — GraphQlTester.Errors](https://docs.spring.io/spring-graphql/docs/1.3.x/api/org/springframework/graphql/test/tester/GraphQlTester.Errors.html): expect/filter/satisfy/verify.
- [Spring for GraphQL 1.3 — GraphQlTester.Path](https://docs.spring.io/spring-graphql/docs/1.3.x/api/org/springframework/graphql/test/tester/GraphQlTester.Path.html): entity/valueIsNull/pathDoesNotExist.
- [Spring for GraphQL — Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html): @QueryMapping, @SchemaMapping, @Argument.
- [Spring Guide — Building a GraphQL Service](https://spring.io/guides/gs/graphql-server): schema, controller, and GraphQlTester.

**Conclusion:** @GraphQlTest is a **GraphQL execution slice**, not an HTTP server test. Specify the controller, use @MockBean for collaborators outside the slice, and use GraphQlTester to verify schema/arguments, root/nested resolvers, selection sets, nulls, and errors. When full bean wiring or HTTP /graphql is needed, use @SpringBootTest(RANDOM_PORT) with HttpGraphQlTester.