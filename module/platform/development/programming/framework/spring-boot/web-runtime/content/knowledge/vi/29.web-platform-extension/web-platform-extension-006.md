# Ranh giới giữa HTTP runtime với schema, resolver và mô hình dữ liệu GraphQL trong Spring Boot

## 1. Mục tiêu: hiểu bốn lớp trước khi viết GraphQL API

Một Spring Boot web application có thể cung cấp REST, GraphQL, WebSocket và các kiểu endpoint khác trên cùng một embedded HTTP server. Với REST, developer thường quen mô hình `@GetMapping("/books/{id}")` rồi trả DTO. Với GraphQL, nếu dùng tư duy “mỗi field là một URL”, ứng dụng dễ bị trộn trách nhiệm: một controller tự parse JSON HTTP, tự kiểm tra schema, gọi database, quyết định cả response status lẫn hình dạng dữ liệu. Điều này làm khó bảo trì, kiểm thử và bảo mật.

**GraphQL phân chia công việc thành những lớp riêng**:

1. **HTTP runtime/transport:** nhận request HTTP, TLS, route `/graphql`, CORS, session/security filters, giới hạn request body, headers và trả response.
2. **GraphQL schema/contract:** khai báo kiểu dữ liệu và các operations/fields mà client **được phép yêu cầu**, thông thường dưới dạng SDL (`.graphqls`).
3. **GraphQL execution và resolver/data fetcher:** parse, validate, thực thi operation, lấy từng field theo schema, điều phối biến/contexts, batching và xử lý lỗi GraphQL.
4. **Application service, domain và data model:** kiểm soát quy tắc nghiệp vụ, quyền truy cập dữ liệu, transaction, persistence, DTO và cách kết nối database hoặc API bên ngoài.

Bài học này tập trung **ranh giới và trách nhiệm** giữa các tầng, không dạy lại toàn bộ cú pháp GraphQL hoặc thay thế các bài chuyên sâu về REST, JPA và Spring Security. Các ví dụ minh họa dùng **Spring Boot 3.3.x, Spring for GraphQL 1.3.x, Spring Framework 6.1.x và Java 21** (Java 17+ phù hợp). Các property và package được chọn theo thế hệ Spring Boot 3.3, không trộn với cấu hình Spring Boot 4.x.

**Sơ đồ tổng quát:**

```text
Browser / mobile / GraphQL client
    |
    | POST /graphql
    | {"query": "...", "variables": {...}}
    v
HTTP runtime: Tomcat + Spring MVC / Reactor Netty + WebFlux
    | TLS, CORS, auth, HTTP parsing, route, request size
    v
GraphQL web transport: WebGraphQlHandler / interceptor
    | GraphQL request object, GraphQL context, response metadata
    v
ExecutionGraphQlService + GraphQlSource
    | GraphQL Java: parse -> validate -> select operation -> execute fields
    v
Data fetchers: @QueryMapping / @MutationMapping / @SchemaMapping
    | lấy field, mapping arguments, data loader, authorization
    v
Application services -> domain rules -> repositories / remote APIs
    |
    v
GraphQL ExecutionResult: data, errors, extensions
    |
    v
HTTP response (thường JSON; HTTP status phụ thuộc transport/error)
```

**Phân biệt quan trọng nhất:** `@QueryMapping` là **field resolver cho `Query` trong schema**, không phải `@GetMapping` HTTP. GraphQL schema **không phải** JPA entity schema. Và HTTP status `200` **không tự chứng minh** tất cả GraphQL fields đều thành công.

## 2. Vì sao GraphQL không đồng nghĩa với một HTTP endpoint REST khác?

Với REST, các URL thường biểu diễn tài nguyên/hành động:

```http
GET /api/books/b1
GET /api/books/b1/author
POST /api/books
```

Với GraphQL, nhiều query/mutation được gửi đến **một endpoint HTTP** như `/graphql`; nội dung body chỉ rõ operation và fields muốn lấy:

```http
POST /graphql HTTP/1.1
Content-Type: application/json
Accept: application/json

{
  "query": "query GetBook($id: ID!) { book(id: $id) { id title author { name } } }",
  "variables": {"id": "b1"},
  "operationName": "GetBook"
}
```

Client không yêu cầu một URL riêng cho `author.name`. Server GraphQL engine thực thi field `book`, rồi field `author`, rồi field `name` theo **schema, runtime wiring và dữ liệu trả về**. Hình dạng `data` trong response phản chiếu selection set của client.

Response minh họa:

```json
{
  "data": {
    "book": {
      "id": "b1",
      "title": "Spring Boot",
      "author": {
        "name": "Lan"
      }
    }
  }
}
```

Nếu client chỉ yêu cầu `book { title }`, response không tự thêm `author` như một REST DTO trả toàn bộ fields. **Schema giới hạn quyền truy vấn cấu trúc**, nhưng **không tự giới hạn quyền truy cập một bản ghi cụ thể** — đó là trách nhiệm authorization ở lớp nghiệp vụ/resolver.

GraphQL **không yêu cầu HTTP** về bản chất: GraphQL engine và schema có thể được gọi qua WebSocket, RSocket hoặc trực tiếp trong tests. HTTP chỉ là một transport phổ biến.

## 3. Bản đồ trách nhiệm để tránh trộn tầng

| Câu hỏi | Tầng chịu trách nhiệm chính | Ví dụ |
| --- | --- | --- |
| Request tới cổng nào, có TLS không? | HTTP runtime và hạ tầng | `server.port`, `server.ssl.*`, reverse proxy |
| Endpoint GraphQL HTTP là gì? | Spring Boot GraphQL transport | `spring.graphql.path=/graphql` |
| Browser origin nào được phép gửi/đọc? | CORS/security tại HTTP/gateway | `spring.graphql.cors.*` |
| HTTP request có body JSON hợp lệ không? | Transport/codec | `Content-Type: application/json` |
| `book(id: ID!)` có tồn tại không? | GraphQL schema và validation | SDL type `Query` |
| Client yêu cầu `Book.secretField` có hợp lệ không? | GraphQL validation | Field không được định nghĩa → lỗi validation |
| Tải `book` từ đâu? | Resolver + service/repository | `@QueryMapping` gọi `BookCatalog` |
| `author` của `Book` được tìm thế nào? | Field resolver/batch loader | `@SchemaMapping` hoặc `@BatchMapping` |
| Ai được xem cuốn sách này? | Business authorization | Owner/tenant/ACL check |
| DTO `BookView` tạo ra sao? | Service/DTO mapping | Domain → API view |
| Trường nào có thể `null`? | GraphQL schema, resolver contract | `Book!`, `[Book!]!` |
| Một field lỗi nhưng field khác thành công? | GraphQL execution/error handling | `data` có phần thành công + `errors` |
| Làm sao chống N+1 queries? | Resolver/data loader/repository | `@BatchMapping`, batch fetch |
| Giao dịch mutation? | Application service/data access | `@Transactional` tại boundary phù hợp |
| Dùng HTTP status nào trên transport error? | Web transport/GraphQL-over-HTTP policy | 400/401/403/500/2xx tùy tình huống |

Đừng để `@RestController` tự giải mã `{query: ...}` rồi gán HTTP `200` theo cảm tính cho mọi lỗi. Khi dùng Spring for GraphQL, framework đã có web adapter và execution service. App nên cung cấp schema, resolvers và business services.

## 4. Spring Boot 3.3 nối GraphQL engine vào HTTP như thế nào?

Spring Boot auto-configuration yêu cầu **ít nhất**:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-graphql'
```

Starter này cho Spring GraphQL/GraphQL Java, nhưng muốn nhận HTTP request thì cần thêm web transport:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-web'
```

hoặc:

```groovy
implementation 'org.springframework.boot:spring-boot-starter-webflux'
```

Spring MVC dùng Servlet stack (thường embedded Tomcat); WebFlux có thể dùng Reactor Netty. Với Spring Boot, **GraphQL HTTP POST endpoint mặc định `/graphql`**, và được cung cấp thông qua `RouterFunction` bean có thứ tự ưu tiên theo tài liệu, không phải một method `@PostMapping` do developer tự viết. Đây là một lý do cần cẩn thận khi thêm custom `RouterFunction` trùng route.

Spring Boot tự tạo và cấu hình:

- `GraphQlSource` để xây `graphql.GraphQL` engine.
- Loader đọc schema SDL từ classpath.
- Annotated controller configurer để biến `@QueryMapping`, `@SchemaMapping` thành GraphQL Java `DataFetcher`.
- HTTP transport handler/`ExecutionGraphQlService`.
- Các `RuntimeWiringConfigurer`, `DataFetcherExceptionResolver`, instrumentation beans phù hợp nếu ứng dụng khai báo.

GraphQL **WebSocket endpoint** không tự bật chỉ vì đã có HTTP GraphQL. Trong Boot 3.3, cần đặt `spring.graphql.websocket.path`; với Servlet còn cần WebSocket starter. WebFlux có hỗ trợ transport thích hợp khi cấu hình. Subscription qua SSE cũng được hỗ trợ theo phiên bản, nhưng chúng không thay đổi ranh giới giữa schema và business data.

## 5. Schema SDL: contract của GraphQL, không phải class Java

Schema Definition Language (SDL) biểu diễn những operations, types, fields, arguments và nullability mà GraphQL server công bố. Ví dụ:

```graphql
type Query {
  book(id: ID!): Book
  books: [Book!]!
}

type Mutation {
  addBook(input: NewBookInput!): Book!
}

type Book {
  id: ID!
  title: String!
  author: Author!
}

type Author {
  id: ID!
  name: String!
}

input NewBookInput {
  title: String!
  authorId: ID!
}
```

Ý nghĩa:

- `Query` khai các root fields dùng để **đọc** dữ liệu.
- `Mutation` khai các root fields có thể **thay đổi** trạng thái hệ thống.
- `book(id: ID!): Book` trả `Book` hoặc `null`; đối số `id` bắt buộc.
- `books: [Book!]!` trả danh sách không `null` và từng phần tử không `null`. Danh sách rỗng `[]` vẫn hợp lệ.
- `Book.author: Author!` nói field author không được trả `null` nếu parent `Book` tồn tại; nếu resolver không thỏa, **null propagation** và GraphQL errors xảy ra.
- `input NewBookInput` là **kiểu input riêng**, không phải object output `Book`. GraphQL tách input types khỏi object types.

Schema không nêu **lưu Book ở Postgres, MongoDB hay một API khác**, không nêu Java entity nào được dùng, và không tự định nghĩa một SQL query. Nó chỉ là **hợp đồng dữ liệu mà GraphQL engine dùng để validate và execute**.

`ID` trong SDL là **GraphQL scalar định danh**, thường serialize dưới dạng chuỗi trong JSON. Nó không bắt buộc là database primary key kiểu `long`, cũng không tự cấp authz hoặc bảo đảm UUID. `String!` bắt buộc non-null ở mức GraphQL, nhưng nghiệp vụ còn cần validate độ dài, ký tự và các quy tắc khác.

## 6. Vị trí schema files và cấu hình Boot 3.3

Theo Spring Boot 3.3, schema `.graphqls` hoặc `.gqls` dưới `src/main/resources/graphql/` được tự phát hiện. Ví dụ:

```text
src/main/resources/graphql/
    catalog.graphqls
```

Có thể chia nhỏ schema thành nhiều file cho các modules, nhưng tất cả type/field definitions cuối cùng phải **hợp lệ và nhất quán** sau khi merge/parse. Đặt sai thư mục hoặc extension khiến Boot không thấy schema như dự định.

Cấu hình liên quan:

```properties
spring.graphql.path=/graphql

# Default conventions: schemas under classpath graphql directory.
# spring.graphql.schema.locations=classpath:graphql/
# spring.graphql.schema.file-extensions=.graphqls,.gqls

# Dev-only convenience; default disabled in typical production.
spring.graphql.graphiql.enabled=false
spring.graphql.schema.printer.enabled=false
```

Nếu app có schemas đóng gói từ nhiều modules/JARs, Spring Boot hỗ trợ locations dùng classpath resource pattern thích hợp. Không nghĩ mọi `.graphql` trong source được auto nhận: query documents của client/tests có thể dùng `.graphql`, còn Spring Boot schema mặc định dùng `.graphqls`/`.gqls`.

Cấu hình `spring.graphql.schema.introspection.enabled=false` có thể hạn chế introspection theo yêu cầu vận hành, nhưng **không phải lớp bảo mật thay thế authorization**. Client vẫn có thể gửi các field names đã biết. GraphiQL và schema printer cũng là các tiện ích riêng, nên bật có kiểm soát theo môi trường.

**Cảnh báo phiên bản:** Trong Spring Boot 3.3 property HTTP route là `spring.graphql.path`. Một số bản Boot mới đổi nhóm property cho HTTP transport; không copy tên của Boot 4.x vào app 3.3.

## 7. Resolver là hàm phục vụ field, không phải HTTP controller endpoint

Spring for GraphQL cung cấp annotated controllers:

```java
@Controller
class GreetingGraphQlController {

    @QueryMapping
    String greeting(@Argument String name) {
        return "Hello, " + name;
    }
}
```

Đây là **mẫu code tích hợp**, cần schema tương ứng như `type Query { greeting(name: String!): String! }`, imports Spring và `@SpringBootApplication` scan package. `@QueryMapping` ánh xạ method sang field `Query.greeting`; Spring chuyển method thành một **GraphQL Java DataFetcher**.

Đặt `@Controller`, không cần `@RestController` hoặc `@PostMapping("/graphql")`. `@RestController` thường dành cho Spring MVC HTTP handler methods; nó không có vai trò cần thiết để đăng ký GraphQL annotated methods.

Các annotation chính:

| Annotation | Map sang schema | Vai trò |
| --- | --- | --- |
| `@QueryMapping` | `Query.someField` | Resolver root query |
| `@MutationMapping` | `Mutation.someField` | Resolver root mutation |
| `@SubscriptionMapping` | `Subscription.someField` | Resolver root subscription |
| `@SchemaMapping` | `TypeName.fieldName` | Resolver bất kỳ field object type nào |
| `@Argument` | GraphQL argument của field | Bind scalar/input object vào Java parameter |
| `@BatchMapping` | Field với dữ liệu cần batch load | Batching giảm N+1 |
| `@ContextValue` | `GraphQLContext` | Metadata theo request, không phải raw HTTP |
| `@GraphQlExceptionHandler` | Exceptions khi fetch dữ liệu | Chuyển lỗi sang GraphQL errors theo policy |

Một `@SchemaMapping(typeName="Book",field="author")` không tự tạo route `/graphql/book/author`. Nó chỉ được gọi khi **operation GraphQL đã validate** và execution đi tới field `Book.author` được yêu cầu.

## 8. Đường thực thi của một query lồng nhau

Giả sử client gửi:

```graphql
query {
  book(id: "b1") {
    id
    title
    author {
      id
      name
    }
  }
}
```

GraphQL engine thực hiện ở mức khái niệm:

```text
(1) Parse GraphQL document
(2) Validate field/argument/type theo schema
(3) Resolve root Query.book(id:"b1")
    -> BookGraphQlController.book(...)
    -> BookCatalog.find(...)
    -> BookView("b1", ...)
(4) Resolve Book.id, Book.title
    -> default property fetching từ BookView getters
(5) Resolve Book.author
    -> @SchemaMapping("Book","author")
    -> BookCatalog.findAuthor(book.authorId)
(6) Resolve Author.id, Author.name
    -> default property fetching từ AuthorView getters
(7) Assemble GraphQL ExecutionResult
(8) Serialize JSON qua HTTP web transport
```

Điểm mấu chốt: **không nhất thiết cần một Java resolver method cho mỗi scalar field**. Với các thuộc tính thường như `getId()`, `getTitle()`, `getName()`, GraphQL Java có thể dùng **default property data fetcher**. Với field cần join/lazy fetch/authorization như `Book.author`, resolver riêng làm rõ điều gì xảy ra.

Nếu client chỉ yêu cầu `book { title }`, `author` field resolver không cần chạy. Nhưng không nên hiểu rằng mọi bước nghiệp vụ/DB sẽ tự tối ưu theo selection set: root resolver có thể vẫn load nhiều dữ liệu dư. Muốn tối ưu sâu, cần thiết kế repository/projection/batch fetching.

## 9. DTO GraphQL, domain model và persistence entity có thể khác nhau

Ví dụ hệ thống quản lý sách có ba khái niệm:

```text
Persistence layer
  BookRow(id, title, author_id, internal_cost, deleted_at)
       |
       | mapping + authorization
       v
Domain / application service
  Book business rules: owner, available, canRead...
       |
       | output projection
       v
GraphQL API model
  BookView {id, title, authorId}
       |
       | GraphQL SDL chỉ công bố id, title, author
       v
Client sees Book {id, title, author {id, name}}
```

Không bắt buộc domain object, JPA `@Entity` và GraphQL type có cùng tên hoặc cùng tất cả fields. Tách DTO giúp:

- Không lộ các trường nội bộ (`passwordHash`, `internalCost`, `tenantId`, soft-delete flags).
- Thay đổi cấu trúc database mà không phá schema công khai.
- Ứng dụng kiểm soát field-level authorization và chuyển đổi dữ liệu.
- Tránh N+1 ngoài ý muốn khi dùng JPA lazy relationships.
- Quản lý nullability rõ hơn: `Book.author: Author!` cần được bảo đảm hoặc sửa schema hợp đồng.

`BookView` Java có thể có `getAuthorId()` để resolver dùng, dù GraphQL SDL **không** khai `authorId` là field client truy vấn. GraphQL engine không tự expose mọi Java getters; nó chỉ resolve **fields có trong schema** mà operation yêu cầu. Tuy nhiên nếu schema khai một field nhạy cảm trùng getter thì phải kiểm soát authorization — không coi sự hiện diện của DTO là bảo vệ hoàn chỉnh.

## 10. Dự án mẫu Spring Boot 3.3: cấu trúc và phụ thuộc

Ví dụ hoàn chỉnh bên dưới dùng **Java 21 và Spring Boot 3.3.13**, in-memory data để tập trung vào ranh giới GraphQL/HTTP thay vì cấu hình database. Những đoạn code liên tiếp tạo nên một ứng dụng chạy được trong project Gradle có Wrapper. Mã đặt dưới cùng package `com.example.bookgraphql`.

**Cấu trúc:**

```text
build.gradle
src/main/java/com/example/bookgraphql/
  BookGraphQlApplication.java
  BookView.java
  AuthorView.java
  NewBookInput.java
  BookCatalog.java
  BookGraphQlController.java
src/main/resources/
  application.properties
  graphql/catalog.graphqls
src/test/java/com/example/bookgraphql/
  GraphQlSchemaTest.java
  GraphQlHttpTest.java
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-graphql'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.graphql:spring-graphql-test'
    // Dùng hỗ trợ HTTP GraphQlTester/WebTestClient trong test.
    testImplementation 'org.springframework.boot:spring-boot-starter-webflux'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

- `spring-boot-starter-graphql` mang GraphQL Java và Spring integration.
- `spring-boot-starter-web` cung cấp Spring MVC Servlet HTTP transport.
- Không cần viết servlet handler riêng để expose `/graphql`.
- `spring-graphql-test` cung cấp `GraphQlTester`.
- WebFlux ở **testImplementation** cho HTTP tester; không biến production MVC thành WebFlux app. Khi cả web starters ở runtime, Boot thường ưu tiên Servlet application type theo auto detection.

Đây là cấu hình cho **mục tiêu học tập**, không phải đề xuất nâng Spring Boot production lên một patch version tùy tiện; hãy dùng BOM và version đã được dự án kiểm soát.

## 11. Schema thực tế: `src/main/resources/graphql/catalog.graphqls`

```graphql
type Query {
  book(id: ID!): Book
  books: [Book!]!
}

type Mutation {
  addBook(input: NewBookInput!): Book!
}

type Book {
  id: ID!
  title: String!
  author: Author!
}

type Author {
  id: ID!
  name: String!
}

input NewBookInput {
  title: String!
  authorId: ID!
}
```

`Query.book` nullable vì không tìm thấy `b1` có thể trả `null` hợp lệ. `Mutation.addBook` non-null biểu thị mutation thành công phải trả `Book`; khi lỗi nghiệp vụ, GraphQL execution có thể đưa lỗi vào `errors` theo chính sách và áp dụng null propagation.

Trong schema **không có trường `Book.authorId`**, dù data model nội bộ giữ khóa ngoại đó. Client chỉ có thể yêu cầu `author { id name }`. Đây là ranh giới có chủ đích: một **field công khai** có thể được tính từ nhiều dữ liệu nội bộ.

Nếu client gửi `books { costPrice }` nhưng SDL không khai `costPrice`, GraphQL validation từ chối request trước khi gọi resolver. Tuy vậy điều này chỉ ngăn field không có trong schema; đối với một `Book` được phép truy vấn, **được xem bản ghi nào** vẫn phải kiểm tra ở service.

## 12. Application bootstrap và API DTO: không buộc vào JPA

**`BookGraphQlApplication.java`:**

```java
package com.example.bookgraphql;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BookGraphQlApplication {
    public static void main(String[] args) {
        SpringApplication.run(BookGraphQlApplication.class, args);
    }
}
```

**`BookView.java`:**

```java
package com.example.bookgraphql;

import java.util.Objects;

public final class BookView {
    private final String id;
    private final String title;
    private final String authorId;

    public BookView(String id, String title, String authorId) {
        this.id = Objects.requireNonNull(id);
        this.title = Objects.requireNonNull(title);
        this.authorId = Objects.requireNonNull(authorId);
    }

    public String getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getAuthorId() {
        return authorId;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof BookView book && id.equals(book.id);
    }

    @Override
    public int hashCode() {
        return id.hashCode();
    }
}
```

`BookView` chứa `authorId` để implementation resolver sử dụng, nhưng GraphQL schema chỉ công bố `Book.id`, `Book.title`, `Book.author`. `equals`/`hashCode` theo ID hữu ích nếu sau này dùng `@BatchMapping` với `BookView` làm map key; chỉ áp dụng cách này khi ID là bất biến và đủ định danh theo nghiệp vụ (trong multi-tenant có thể cần `tenantId + id`).

**`AuthorView.java`:**

```java
package com.example.bookgraphql;

import java.util.Objects;

public final class AuthorView {
    private final String id;
    private final String name;

    public AuthorView(String id, String name) {
        this.id = Objects.requireNonNull(id);
        this.name = Objects.requireNonNull(name);
    }

    public String getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
```

GraphQL Java default property fetching có thể đọc các JavaBean getters `getId`, `getTitle`, `getName` khi resolve scalar fields đã có trong schema. Vì vậy demo không cần ba resolver Java tường minh cho `Book.id`, `Book.title`, `Author.name`.

**`NewBookInput.java`:**

```java
package com.example.bookgraphql;

public record NewBookInput(String title, String authorId) {
}
```

Record Java 17+ làm input DTO. Spring GraphQL `@Argument` có thể bind GraphQL input object vào primary data constructor (record canonical constructor). Kiểu input không tự thành entity; application service sẽ validate nội dung và quyết định storage.

## 13. Service nghiệp vụ: `BookCatalog.java`

Tầng này không biết HTTP body, `GraphQLContext`, `@SchemaMapping` hoặc GraphQL selection set. Nó cung cấp các operations có thể dùng lại từ REST, message consumer hoặc batch job.

```java
package com.example.bookgraphql;

import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;

import org.springframework.stereotype.Service;

@Service
public class BookCatalog {
    private record StoredBook(
            String id, String title, String authorId) {
    }

    private final ConcurrentMap<String, StoredBook> store =
            new ConcurrentHashMap<>();

    private final Map<String, AuthorView> authors = Map.of(
            "a1", new AuthorView("a1", "Lan"),
            "a2", new AuthorView("a2", "Minh"));

    private final AtomicInteger nextId = new AtomicInteger(2);

    public BookCatalog() {
        store.put("b1",
                new StoredBook("b1", "Spring Boot", "a1"));
    }

    public BookView book(String id) {
        StoredBook value = store.get(id);
        return value == null ? null : toView(value);
    }

    public List<BookView> books() {
        return store.values().stream()
                .sorted(Comparator.comparing(StoredBook::id))
                .map(BookCatalog::toView)
                .toList();
    }

    public AuthorView author(String authorId) {
        return authors.get(authorId);
    }

    public Map<String, AuthorView> authorsByIds(Set<String> ids) {
        return ids.stream()
                .filter(authors::containsKey)
                .collect(Collectors.toMap(id -> id, authors::get));
    }

    public BookView addBook(NewBookInput input) {
        if (input == null || input.title() == null
                || input.title().isBlank()) {
            throw new IllegalArgumentException(
                    "Title must not be blank");
        }

        if (!authors.containsKey(input.authorId())) {
            throw new IllegalArgumentException(
                    "Author does not exist");
        }

        String id = "b" + nextId.getAndIncrement();
        StoredBook created =
                new StoredBook(id, input.title().trim(), input.authorId());
        store.put(id, created);
        return toView(created);
    }

    private static BookView toView(StoredBook value) {
        return new BookView(
                value.id(), value.title(), value.authorId());
    }
}
```

Ở đây data source là `ConcurrentHashMap` vì demo. Trong ứng dụng thật:

- `BookCatalog` thường gọi repository, domain policy, transaction boundary hoặc external service.
- `@Transactional` nên gắn theo một **operation nghiệp vụ** phù hợp, không bọc toàn bộ HTTP/GraphQL session tùy tiện.
- `author()` trong demo là lookup memory; khi chuyển sang database, phải cân nhắc N+1, batch fetching và authorization theo tenant.
- `IllegalArgumentException` được ném khi input không hợp lệ; khi không có custom `DataFetcherExceptionResolver`, GraphQL errors thường được che thông tin nội bộ thay vì trả nguyên exception message. Production nên có error mapping có kiểm soát.
- Biến `nextId` chỉ tăng trong một instance và **không bền qua restart**. Đây là in-memory exercise, không phải hệ thống persistence hay đảm bảo ID duy nhất trên cluster.

Service không biết endpoint `/graphql`. Nếu sau này chuyển transport từ MVC sang WebFlux, schema và business operations **về nguyên tắc không phải đổi vì URL**, nhưng implementation có blocking I/O cần được cân nhắc lại.

## 14. Resolver: `BookGraphQlController.java`

```java
package com.example.bookgraphql;

import java.util.List;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookGraphQlController {
    private final BookCatalog catalog;

    public BookGraphQlController(BookCatalog catalog) {
        this.catalog = catalog;
    }

    @QueryMapping
    public BookView book(@Argument String id) {
        return catalog.book(id);
    }

    @QueryMapping
    public List<BookView> books() {
        return catalog.books();
    }

    @MutationMapping
    public BookView addBook(@Argument NewBookInput input) {
        return catalog.addBook(input);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public AuthorView author(BookView book) {
        return catalog.author(book.getAuthorId());
    }
}
```

**Đọc từng method theo schema:**

- `@QueryMapping book` map sang `Query.book(id: ID!)`.
- `@QueryMapping books` map sang `Query.books`.
- `@MutationMapping addBook` map sang `Mutation.addBook(input: NewBookInput!)`.
- `@SchemaMapping(typeName="Book", field="author")` map sang `Book.author`. `BookView` parameter là **source/parent object** mà GraphQL engine đã resolve cho field `Book`; nó không đến từ JSON HTTP request.
- `@Argument` trích giá trị argument GraphQL đã được engine/binder xử lý. Đây **không phải** MVC `@RequestParam` hay `@RequestBody`.

Nếu client chỉ hỏi `{ books { title } }`, `Book.author` resolver không cần được gọi. Nếu hỏi nested `author { name }`, GraphQL engine nhận `BookView` làm source và gọi `author(...)`.

**Điểm kiến trúc:** GraphQL controller không phụ thuộc vào `HttpServletRequest` chỉ để biết Book ID. Nó phụ thuộc vào GraphQL arguments và service. Khi cần authentication context, dùng principal/security context hoặc GraphQL context theo contract — không kéo HTTP headers thô vào mọi resolver.

## 15. Cấu hình và chạy HTTP transport

**`src/main/resources/application.properties`:**

```properties
server.address=127.0.0.1
server.port=8080

spring.graphql.path=/graphql

# Dùng khi phát triển cục bộ, không công khai tiện ích mặc định.
spring.graphql.graphiql.enabled=false
spring.graphql.schema.printer.enabled=false
```

Chạy:

```bash
./gradlew bootRun
```

Ứng dụng mẫu có cấu hình loopback để giảm rủi ro khi thử nghiệm; endpoint GraphQL **chưa có Spring Security**, nên không chuyển `server.address` thành public và không publish Internet khi chưa xây authn/authz, complexity limits và rate limiting.

Với schema hợp lệ, ứng dụng tự expose **GraphQL HTTP POST** tại `http://127.0.0.1:8080/graphql`. Không cần thêm một `@PostMapping` ở `BookGraphQlController`.

Gửi request bằng curl:

```bash
curl -i \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  --data '{"query":"{ book(id: \"b1\") { id title author { id name } } }"}' \
  http://127.0.0.1:8080/graphql
```

Body logic khi service mới khởi động:

```json
{
  "data": {
    "book": {
      "id": "b1",
      "title": "Spring Boot",
      "author": {
        "id": "a1",
        "name": "Lan"
      }
    }
  }
}
```

Thứ tự JSON fields, whitespace và HTTP response headers không phải stdout byte-exact. Kết quả mong muốn là **giá trị `data` tương ứng với selection set**, không thêm `authorId` vì schema/operation không yêu cầu.

## 16. Variables, operationName và mutation đi qua cùng endpoint

GraphQL operation có thể dùng variables thay vì ghép trực tiếp dữ liệu người dùng vào query string:

```graphql
query FindBook($id: ID!) {
  book(id: $id) {
    id
    title
  }
}
```

HTTP body:

```json
{
  "operationName": "FindBook",
  "query": "query FindBook($id: ID!) { book(id:$id) { id title } }",
  "variables": {
    "id": "b1"
  }
}
```

Gửi trực tiếp:

```bash
curl -sS \
  -H 'Content-Type: application/json' \
  --data '{"operationName":"FindBook","query":"query FindBook($id:ID!){book(id:$id){id title}}","variables":{"id":"b1"}}' \
  http://127.0.0.1:8080/graphql
```

`operationName` cần thiết khi document chứa nhiều operations và phải chọn đúng một operation; nếu document chỉ có một operation, có thể không bắt buộc tùy giao thức/client.

Mutation:

```bash
curl -sS \
  -H 'Content-Type: application/json' \
  --data '{"query":"mutation Add($input:NewBookInput!){addBook(input:$input){id title author{name}}}","operationName":"Add","variables":{"input":{"title":"GraphQL Design","authorId":"a2"}}}' \
  http://127.0.0.1:8080/graphql
```

Khi mới chạy server, chưa có mutations trước đó, kết quả có thể là:

```json
{
  "data": {
    "addBook": {
      "id": "b2",
      "title": "GraphQL Design",
      "author": {
        "name": "Minh"
      }
    }
  }
}
```

ID này **phụ thuộc trạng thái in-memory**; nếu đã thêm sách khác thì ID sẽ tăng. Không dùng kết quả demo làm cam kết concurrency/persistence.

GraphQL `Mutation` là một operation loại mutation với semantics đặc biệt tại root theo spec; ứng dụng **không tự có database transaction** chỉ vì method gắn `@MutationMapping`. Quy tắc transactional và idempotency khi retry vẫn nằm ở service.

## 17. Định dạng HTTP request khác với GraphQL operation

Một lỗi mô hình thường gặp là đặt toàn bộ GraphQL logic vào HTTP adapter:

```java
// Anti-pattern minh họa, KHÔNG cần khi dùng Spring for GraphQL:
@PostMapping("/graphql")
public Map<String, Object> graphql(@RequestBody Map<String, Object> body) {
    String query = (String) body.get("query");
    // Tự parse, tự tìm field, tự lấy DB và tự tạo JSON trả về ...
    return Map.of();
}
```

Đây chỉ là ví dụ tư duy, không phải source cần chạy. Làm vậy bỏ qua parsing, validation, coercion, execution strategy, fragments, variables, error paths và field semantics mà GraphQL Java đã có.

Phân tách tốt hơn:

```text
HTTP adapter:
  POST route, request body, headers, TLS, CORS, auth
    |
GraphQL transport:
  WebGraphQlRequest / WebGraphQlHandler
    |
GraphQL execution:
  document, operation, variables, schema validation, field selection
    |
Resolver:
  Query.book, Book.author, Mutation.addBook
    |
Service:
  canRead, findBook, addBook, transaction
```

Với `@QueryMapping`, resolver biết `id` và source/arguments, **không bắt buộc** biết HTTP method. Việc mapping HTTP request sang GraphQL execution là trách nhiệm infrastructure.

Nếu muốn một endpoint REST chạy song song GraphQL, có thể viết `@RestController` riêng dùng **cùng service**. Không bắt REST controller giả làm GraphQL parser, cũng không ép schema GraphQL phản chiếu tất cả REST DTO.

## 18. Không nhầm GraphQL schema với Java reflection hoặc JPA schema

Ba đối tượng có thể dùng từ “schema” nhưng khác bản chất:

| Thành phần | Mô tả | Ví dụ |
| --- | --- | --- |
| GraphQL schema | API contract đã public: types, nullability, queries, mutations | `type Book { id: ID!, author: Author! }` |
| Java type model | Classes/records/POJO của implementation | `BookView`, `StoredBook`, `AuthorView` |
| Database schema | Tables, columns, keys, indexes, constraints | `book(id, title, author_id)` |

Không có quy tắc GraphQL field `author` phải là thuộc tính Java `BookView.getAuthor()` hoặc cột SQL `author`. Nó có thể được resolve bằng `@SchemaMapping` gọi tới hệ thống catalog khác.

Java reflection mặc định **không tự tạo GraphQL schema từ mọi class** trong Spring for GraphQL cách schema-first đã trình bày. Các tool code-first/auto-generation khác có thể tồn tại, nhưng chúng thuộc một quyết định kiến trúc khác. Trong bài này, **SDL là nguồn contract**.

Nếu đổi tên database column `author_id` thành `writer_ref` nhưng API vẫn dùng `Book.author`, chỉ repository/mapper cần đổi. Nếu đổi GraphQL field `author` thành `writer`, đó là thay đổi contract ảnh hưởng client, dù database không đổi.

## 19. Nullability và propagation: lỗi field có thể ảnh hưởng data của cha

GraphQL nullability dùng `!`:

```graphql
type Query {
  book(id: ID!): Book
  books: [Book!]!
}

type Book {
  id: ID!
  title: String!
  author: Author!
}
```

Các trường hợp:

- `Query.book` có thể `null` khi sách không tồn tại.
- `Book.author` là non-null. Nếu resolver không tìm thấy author và trả `null`, GraphQL Java tạo lỗi thực thi và **null bubble** lên ancestor nullable gần nhất.
- `[Book!]!` cam kết danh sách không null, phần tử không null; một lỗi làm phần tử null có thể bubble khiến **cả list field** bị null, và xa hơn nữa tùy parent schema.

Ví dụ GraphQL response khi field không nullable thất bại **có thể** chứa:

```json
{
  "data": {
    "book": null
  },
  "errors": [
    {
      "message": "A non-null field failed to resolve",
      "path": ["book", "author"]
    }
  ]
}
```

Đây là **minh họa hình dạng response**, không phải error message byte-exact: engine/version và error resolver có thể tạo thông điệp/vị trí khác. Cần dựa vào `errors[].path` và schema nullability để hiểu root cause.

Nếu có nghiệp vụ “tác giả có thể đã bị xóa”, contract `author: Author!` có thể không đúng. Sửa bằng cách đảm bảo referential integrity hoặc thay schema thành `author: Author` (có chính sách migration tương ứng), **không** che lỗi bằng một object bịa để tránh null.

## 20. HTTP status và GraphQL `errors`: hai loại thất bại khác nhau

Với HTTP transport, có những lỗi xảy ra **trước** khi GraphQL engine thực thi:

- Không thể route `/graphql`.
- Request body không phải JSON hợp lệ/không đọc được.
- Content-Type hoặc method không được endpoint chấp nhận.
- Proxy/WAF chặn, auth trả 401/403 trước GraphQL.
- Request quá lớn (413), gateway timeout (504).

Có những lỗi xảy ra **trong** GraphQL:

- Parse GraphQL document sai cú pháp.
- Validation: field không có trong schema hoặc argument sai kiểu.
- Variable coercion lỗi.
- Resolver ném exception khi lấy Book/Author.
- Nullability violation tại field non-null.

GraphQL response có thể trả `data`, `errors` và `extensions`. Đặc biệt, **HTTP 200 vẫn có thể đi kèm `errors`**, kể cả khi các fields khác trả dữ liệu thành công. Nhưng cũng **không khẳng định mọi lỗi GraphQL luôn trả HTTP 200**: HTTP status phụ thuộc loại lỗi, GraphQL-over-HTTP media type (`application/graphql-response+json` hoặc JSON) và transport implementation/version. Việc client chỉ `if (response.status == 200)` rồi coi là success tuyệt đối là sai.

Ví dụ một response thành công một phần (minh họa):

```json
{
  "data": {
    "book": {
      "id": "b1",
      "title": "Spring Boot",
      "author": null
    }
  },
  "errors": [
    {
      "message": "Not authorized to load author",
      "path": ["book", "author"]
    }
  ]
}
```

Response này chỉ hợp lệ nếu contract **cho phép** `Book.author` là nullable. Nếu schema vẫn là `Author!`, data phải tuân thủ null propagation. Khi viết tests phải kiểm tra cả schema nullability và GraphQL errors, không tự tạo ví dụ trái hợp đồng.

**Hai chiều lỗi cần quan sát:** HTTP method/status/headers cho transport, và GraphQL `errors[].message`, `path`, `locations`, `extensions` cho execution. Không dùng mỗi HTTP status để lập bản đồ lỗi.

## 21. `DataFetcherExceptionResolver`: chuyển lỗi nghiệp vụ thành GraphQL errors

Ở GraphQL execution, lỗi từ `@SchemaMapping`/data fetcher được giải quyết bởi GraphQL Java exception handling. Spring for GraphQL cung cấp `DataFetcherExceptionResolver` và cơ chế `@GraphQlExceptionHandler`.

Ví dụ **mẫu tích hợp tùy chọn**, không cần để chạy demo ở trên:

```java
import graphql.GraphQLError;
import graphql.GraphqlErrorBuilder;
import graphql.schema.DataFetchingEnvironment;

import org.springframework.graphql.execution.DataFetcherExceptionResolverAdapter;
import org.springframework.graphql.execution.ErrorType;
import org.springframework.stereotype.Component;

@Component
public class BookErrorResolver extends DataFetcherExceptionResolverAdapter {

    @Override
    protected GraphQLError resolveToSingleError(
            Throwable error, DataFetchingEnvironment environment) {
        if (error instanceof IllegalArgumentException) {
            return GraphqlErrorBuilder.newError(environment)
                    .errorType(ErrorType.BAD_REQUEST)
                    .message("Invalid book input")
                    .build();
        }
        return null;
    }
}
```

Đây là **class ví dụ tích hợp**, cần package phù hợp, đã có Spring GraphQL dependency và nên chỉ xử lý những exception nghiệp vụ đã xác định, không biến mọi `IllegalArgumentException` của cả app thành một lỗi chung. `return null` cho phép các resolvers khác/framework xử lý. Kiểm tra enum `ErrorType` và API tương ứng version đang chạy.

Lỗi parse/validate GraphQL thường xảy ra **trước** khi data fetcher được gọi, nên không nên mong `DataFetcherExceptionResolver` của field giải quyết toàn bộ request-level syntax errors. Lỗi của subscription stream sau khi đã tạo Publisher cũng có đường xử lý riêng (subscription exception resolution).

Không đưa stack trace, SQL, token, path tệp hoặc thông tin nhạy cảm vào GraphQL `errors.message` cho public clients. Dùng correlation/execution ID trong logs nội bộ và response extensions được kiểm soát khi phù hợp.

## 22. Field resolver có thể gây N+1: `@BatchMapping` và DataLoader

Giả sử query lấy 100 books:

```graphql
{
  books {
    id
    title
    author {
      name
    }
  }
}
```

Nếu `Query.books` gọi database một lần và `Book.author` gọi database **mỗi book một lần**, tổng có thể là **1 + 100 queries**. HTTP vẫn chỉ có **một POST `/graphql`**, nên nhìn số lượng HTTP requests không phát hiện được N+1 ở tầng repository.

GraphQL Java hỗ trợ `DataLoader` và Spring for GraphQL hỗ trợ `@BatchMapping`, gom các parents/keys vào batch. Với app nhiều books, nên có service API `authorsByIds(Set<String>)` dùng một bulk repository call thay vì vòng lặp `findById` trên mỗi key.

Trong demo, `BookCatalog.authorsByIds(...)` đã có. Có thể **thay thế** method `@SchemaMapping(typeName="Book",field="author")` trong `BookGraphQlController` bằng:

```java
@BatchMapping(typeName = "Book", field = "author")
public Map<BookView, AuthorView> author(List<BookView> books) {
    Set<String> ids = books.stream()
            .map(BookView::getAuthorId)
            .collect(Collectors.toSet());

    Map<String, AuthorView> batch = catalog.authorsByIds(ids);
    Map<BookView, AuthorView> result = new LinkedHashMap<>();

    for (BookView book : books) {
        result.put(book, batch.get(book.getAuthorId()));
    }
    return result;
}
```

Đây là **đoạn thay thế tích hợp**: ngoài imports đã có cần `@BatchMapping`, `Map`, `Set`, `Collectors`, `LinkedHashMap`. **Không giữ cả `@SchemaMapping` và `@BatchMapping` cho cùng field** rồi mặc định chúng sẽ phối hợp đúng: cả hai đều cố đăng ký resolver cho `Book.author`.

`BookView` trong demo có `equals`/`hashCode` theo ID để dùng làm key phù hợp. Với dữ liệu đa tenant, phải dùng identity đủ mạnh (kết hợp tenant + ID) để tránh trùng keys. `@BatchMapping` có thể trả `Map<Parent, Child>` hoặc các return types khác theo API được hỗ trợ. Trong production, `authorsByIds` phải thực sự batch ở repository, ví dụ `SELECT ... WHERE id IN (...)`; nếu thực hiện `findById` lần lượt bên trong service thì **hình thức API batch không tự giải quyết N+1**.

DataLoader thường cache theo **một GraphQL request**, không phải cache ứng dụng toàn cục. Việc cache kết quả giữa nhiều users/tenants mà không có key authz đúng có thể làm lộ dữ liệu.

## 23. Tại sao schema không tự bảo đảm an toàn dữ liệu?

Một schema có thể công khai:

```graphql
type Query {
  invoice(id: ID!): Invoice
}

type Invoice {
  id: ID!
  total: Float!
  ownerEmail: String!
}
```

Nếu resolver chỉ `repository.findById(id)` mà không kiểm tra caller có quyền với hóa đơn đó, bất kỳ client được phép gửi GraphQL request có thể dò/đoán IDs và đọc thông tin người khác. GraphQL validation chỉ kiểm tra **field có tồn tại** và **types có hợp lệ**; nó không biết owner/tenant/role nghiệp vụ.

Nên kiểm tra:

- **Transport level:** xác thực request, TLS, CORS, CSRF policy khi dùng cookie sessions, HTTP body limit.
- **Operation/field level:** resolver/method security, role/permissions cho mutations và fields nhạy cảm.
- **Object/data level:** ACL, tenant scope, owner checks trong service/repository. Đặc biệt `Query.book` phải tra trong đúng tenant.
- **Nested field level:** `Book.author`, `Invoice.ownerEmail` cũng phải kiểm tra quyền nếu cần, không dựa vào việc parent đã được đọc.
- **Bulk loader level:** batch loads không được trộn dữ liệu giữa users/tenants; DataLoader cache đúng scope.

Ví dụ chính sách đọc sách:

```java
// Mẫu minh họa nghiệp vụ, chưa độc lập:
BookRecord record = repository.findByIdAndTenant(id, currentTenant)
        .orElseThrow(NotFoundException::new);

authorization.checkCanRead(principal, record);
return mapper.toBookView(record);
```

Các kiểu `BookRecord`, `NotFoundException`, `repository`, `authorization`, `mapper` là thành phần của hệ thống thật; không có trong in-memory demo. Việc kiểm tra access tại **service** giúp REST endpoint, scheduled job và GraphQL resolver đều tuân thủ cùng policy.

Không chỉ dựa vào `@PreAuthorize("isAuthenticated()")` ở URL `/graphql` rồi nghĩ mọi objects/fields đều được phân quyền. Một HTTP endpoint có thể truy vấn nhiều loại resources với yêu cầu quyền rất khác nhau.

## 24. Truyền HTTP metadata vào GraphQL context một cách có kiểm soát

Một số thông tin đến từ transport (trace ID, correlation ID, authenticated principal, tenant đã xác minh) cần được sử dụng khi resolve fields. Spring for GraphQL có **`WebGraphQlInterceptor`**, chạy ở ranh giới transport/execution:

```text
HTTP headers / security principal
        |
        v
WebGraphQlInterceptor
  validate/normalize selected metadata
  add to GraphQLContext
        |
        v
ExecutionGraphQlService
        |
        v
@QueryMapping / @SchemaMapping / DataFetcher
  inject @ContextValue or principal
```

Ví dụ **mẫu tích hợp**, chưa phải source độc lập:

```java
@Bean
WebGraphQlInterceptor correlationInterceptor() {
    return (request, chain) -> {
        String value = request.getHeaders().getFirst("X-Correlation-Id");
        String correlationId = normalizeOrGenerate(value);

        request.configureExecutionInput((input, builder) ->
                builder.graphQLContext(contextBuilder ->
                        contextBuilder.put("correlationId", correlationId))
                        .build());

        return chain.next(request);
    };
}
```

Ở đây `normalizeOrGenerate(...)` là helper do ứng dụng định nghĩa, cần imports/configuration tương ứng. **Không tự tin** vào `X-User-Id` hay `X-Tenant-Id` do public client gửi. Chỉ đưa thông tin authentication/tenant đã được security layer hoặc trusted gateway xác minh vào `GraphQLContext`.

Ở resolver:

```java
@QueryMapping
public String trace(@ContextValue String correlationId) {
    return correlationId;
}
```

Đoạn minh họa cần schema `Query.trace`, annotation imports và context từ interceptor. `GraphQLContext` là **request-scoped execution metadata**, không phải JPA persistence context hay Servlet session. Không biến nó thành singleton global state.

Trong Spring MVC, asynchronous fetchers có thể chạy trên thread khác nên không nên giả định mọi custom `ThreadLocal` hoặc `RequestContextHolder` tự truyền đúng nếu không đăng ký context propagation thích hợp. Với WebFlux, Reactor context và reactive execution cần propagation theo framework. **Context chuẩn hóa** rõ ràng tốt hơn việc mỗi resolver đọc raw HTTP headers.

## 25. Schema evolution và contract compatibility

Vì GraphQL API được định nghĩa bằng schema, client có thể phụ thuộc vào **tên field, kiểu, nullability và arguments**. Một số thay đổi thường tương đối an toàn, số khác dễ phá clients:

| Thay đổi schema | Tác động cần xét |
| --- | --- |
| Thêm field mới vào object type | Thường tương thích với clients cũ |
| Thêm optional argument có default/phù hợp | Thường có thể tương thích |
| Xóa/đổi tên field đang được dùng | Breaking change |
| `Book` nullable → `Book!` | Có thể ảnh hưởng runtime nullability/compatibility |
| `Book!` → `Book` | Có thể ảnh hưởng clients dựa trên non-null |
| Thêm required argument không default | Breaking change với queries cũ |
| Đổi `ID!` thành kiểu không tương thích | Breaking change |
| Thay quyền truy cập/nội dung resolver | Có thể thay behavior ngay khi SDL không đổi |
| Đổi database entity/column, giữ contract | Có thể không ảnh hưởng clients nếu mapping đúng |

GraphQL hỗ trợ `@deprecated(reason: "...")` trong schema để báo field/enum value cũ; đây là bước migration, không tự loại client cũ khỏi sử dụng field. Thông thường cần schema diff, deprecation policy, thống kê usage và contract tests trước khi xóa fields.

**Không coi việc đổi Java class name là thay đổi public GraphQL field** nếu `@SchemaMapping(typeName=...,field=...)` và schema vẫn giữ nguyên. Ngược lại, chỉnh SDL có thể phá query dù Java code và HTTP route `/graphql` không đổi.

GraphQL schema registry/federation/gateway có thể thêm trách nhiệm composition khi có nhiều services, nhưng ranh giới cơ bản vẫn là: public schema → runtime wiring/resolvers → domain/backends.

## 26. Tránh nhầm schema validation với input validation nghiệp vụ

GraphQL engine có thể từ chối một operation trước khi gọi resolver:

```graphql
{
  book(id: 123) {
    nonexistent
  }
}
```

`nonexistent` không có trong `type Book` → **schema validation error**, không có `@QueryMapping`/`@SchemaMapping` nào được gọi cho field đó. Việc một số scalar có coercion (ví dụ `ID` chấp nhận cả string và integer input theo spec) là chuyện khác, không làm field không tồn tại trở nên hợp lệ.

Nhưng GraphQL hợp lệ về schema vẫn có thể không hợp lệ về nghiệp vụ:

```graphql
mutation {
  addBook(input: {title:"", authorId:"a99"}) {
    id
  }
}
```

SDL chấp nhận `title` là `String!` vì chuỗi rỗng **không phải null**, và `authorId` có kiểu `ID`. Service phải kiểm tra title blank, author tồn tại, quyền tạo sách, quota và các ràng buộc domain.

Các tầng validation thường gồm:

1. **HTTP codec:** body có parse được JSON không?
2. **GraphQL parser/validator:** document hợp lệ và operation khớp schema không?
3. **Argument binding:** input object bind vào Java type có thành công không?
4. **Bean Validation/Business validation:** field constraints, existence, permission, uniqueness, state transition?
5. **Persistence constraints:** khóa ngoại, unique index, transaction consistency.

Không làm tất cả bằng một `try/catch` HTTP rồi trả `400` chung. Client GraphQL cần phân biệt lỗi **global request** và lỗi **field với `path`**.

## 27. HTTP caching, method và các giới hạn của endpoint chung

Với REST, caching thường dựa vào URL/HTTP method/status, ETag và cache headers. Với GraphQL, rất nhiều operations gửi vào cùng **POST `/graphql`**, nên **cache theo URL đơn thuần không đủ** để phân biệt data theo query, variables, user hoặc authorization context.

Cần cân nhắc:

- Không cache response private chỉ vì endpoint là `/graphql` và HTTP status 200.
- Nếu dùng persisted queries hoặc CDN caching, cache key phải bao gồm operation/query identity, variables và auth/tenant scope thích hợp.
- Tránh đưa token và dữ liệu nhạy cảm vào query-string URL khi dùng GraphQL over GET ở hạ tầng hỗ trợ.
- Request body size limit không bảo vệ khỏi **GraphQL query depth/cost** rất lớn; một query ngắn về bytes vẫn có thể fan-out hàng nghìn database calls.
- Dùng pagination, bounded list sizes, depth/cost limits, rate limits, time budgets và DataLoader/batching.
- Mutation có side effects phải có authorization, idempotency/retry strategy và audit.

Spring Boot 3.3 mặc định cung cấp **POST `/graphql`**. Không giả định mọi GraphQL over HTTP implementation hỗ trợ GET, multipart upload hoặc streaming theo một cách duy nhất; áp dụng giao thức/client policy đúng version và use case.

GraphQL field selection set giúp tránh **over-fetching ở payload**, nhưng không bảo đảm giảm số backend queries hoặc CPU nếu resolvers tự tải tất cả dữ liệu. Hiệu năng thật phụ thuộc thiết kế resolver/service/repository.

## 28. Spring MVC và WebFlux: vận chuyển khác nhau nhưng GraphQL contract giữ vai trò chung

GraphQL Java execution là transport-agnostic. Spring for GraphQL hỗ trợ cả Spring MVC/Servlet và Spring WebFlux:

| Khía cạnh | MVC | WebFlux |
| --- | --- | --- |
| HTTP runtime | Servlet API, embedded Tomcat thường gặp | Reactive server, Reactor Netty thường gặp |
| Endpoint Boot GraphQL | `/graphql` theo Boot property | `/graphql` theo cùng property |
| GraphQL engine | `GraphQlSource` / GraphQL Java | `GraphQlSource` / GraphQL Java |
| Schema SDL | Giống nhau về contract | Giống nhau |
| Resolver annotations | `@QueryMapping`, `@SchemaMapping`, ... | Cùng annotations |
| Data fetchers | Blocking hoặc async tùy method/service | Reactive `Mono`/`Flux` và async |
| Context propagation | Servlet/ThreadLocal cần chú ý async | Reactor context cần chú ý |
| Streaming/subscription | SSE/WebSocket theo web transport hỗ trợ | SSE/WebSocket theo reactive transport |
| Blocking I/O | Dùng threads phù hợp | Không block event-loop Netty |
| Error contract | GraphQL `data`/`errors` | GraphQL `data`/`errors` |

Có thể chuyển một app từ MVC sang WebFlux mà không thay SDL, nhưng **không có nghĩa mọi blocking JPA repository call tự thành non-blocking**. Nếu resolver gọi JPA blocking trong Reactor Netty event-loop, có thể làm nghẽn server. Cần lựa chọn execution strategy/scheduler hoặc non-blocking data access phù hợp.

`Mono` của reactive resolver có thể được Spring GraphQL chuyển thành async results để GraphQL Java thực thi. Một `Flux` không nằm trong subscription có semantics khác so với `Flux` dùng cho GraphQL subscription; không suy rằng trả `Flux<Book>` ở mọi query tự tạo stream SSE tới browser.

**Chọn transport và data access theo workload**, không vì muốn “GraphQL nhanh hơn” mà tùy tiện thay cả stack.

## 29. GraphQL subscriptions và WebSocket: operation khác HTTP connection

GraphQL schema có thể khai:

```graphql
type Subscription {
  newBooks: Book!
}
```

`Subscription` định nghĩa **operation stream** của GraphQL. Nó không đồng nghĩa một WebSocket endpoint được bật chỉ bằng schema. Để phát events:

1. Có GraphQL schema field `Subscription.newBooks`.
2. Có resolver nguồn events, thường `@SubscriptionMapping` trả `Flux<BookView>` hoặc Publisher.
3. Có **transport streaming** được cấu hình (GraphQL WebSocket, hoặc SSE ở phiên bản hỗ trợ).
4. Có cancellation/cleanup cho per-subscriber resources khi client disconnect.
5. Có policy authn/authz, timeout, rate limits và backpressure/replay nếu cần.

Spring Boot 3.3 mặc định không bật GraphQL WebSocket endpoint; khai `spring.graphql.websocket.path` và dependencies cần thiết theo MVC/WebFlux. WebSocket dùng protocol handshake và GraphQL transport logic riêng; **không phải** cùng một HTTP POST kéo dài mãi.

Khi một GraphQL subscription được gửi qua SSE, HTTP transport có thể sử dụng `text/event-stream` và ngắt kết nối có semantics riêng. Nhưng schema và resolver vẫn ở tầng GraphQL. **Đừng nhét logic kết nối/reconnect vào domain `Book` entity**.

Với streaming thật, lỗi sau khi response đã gửi headers không thể tùy tiện chuyển thành một JSON HTTP status khác. Cần dùng cơ chế error/cancel của GraphQL subscription transport đã chọn.

## 30. GraphQL operations và Spring Security: bảo vệ đúng tầng

Chỉ chặn `POST /graphql` khi caller chưa authenticated là **một bước**, không đủ cho permission theo field. Với một GraphQL endpoint duy nhất, quyền có thể khác:

```text
Query.books                 -> public hoặc user-level
Query.book                  -> theo tenant/owner
Book.author                 -> field-level policy
Mutation.addBook            -> yêu cầu books:write
Mutation.deleteBook         -> có thể cần admin/owner
Subscription.newBooks       -> scope theo tenant/topic
```

Những lựa chọn:

- Web security filter chain: xác thực request, cookie/bearer, CSRF nếu phù hợp, CORS và transport access.
- Service authorization: check tenant/owner và business invariants.
- Method security như `@PreAuthorize`, khi bật và áp dụng đúng proxy/bean boundary.
- Data fetcher-level checks cho field nhạy cảm.
- Batch loaders được scope theo caller và request.

Ví dụ mẫu method security **phải được tích hợp trong app đã cấu hình Spring Security**, không có trong demo không-security:

```java
@PreAuthorize("hasAuthority('SCOPE_books:write')")
@MutationMapping
public BookView addBook(@Argument NewBookInput input) {
    return catalog.addBook(input);
}
```

Không tự suy rằng thêm annotation trên là đủ nếu chưa bật `@EnableMethodSecurity`, chưa có principal authentication và chưa cấu hình JWT scopes/authorities thực tế. Ngoài ra, `@PreAuthorize` ở `Mutation.addBook` không thay thế kiểm tra quyền theo `authorId`, `tenantId` và các policies domain.

**Không dùng header `X-Tenant-Id` trực tiếp từ browser** để chọn tenant rồi cho resolver đọc mọi hàng theo header này; tenant phải được xác minh bởi tầng auth/trust boundary.

## 31. `GraphQlTester`: kiểm thử schema + resolvers không cần HTTP

Spring Boot có **`@GraphQlTest`**, là test slice chỉ tải những thành phần liên quan GraphQL, không khởi động HTTP server thật. Điều này rất quan trọng: có thể kiểm thử **contract/schema/resolver** độc lập với URL, Servlet filters và TLS.

**`src/test/java/com/example/bookgraphql/GraphQlSchemaTest.java`:**

```java
package com.example.bookgraphql;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.test.tester.GraphQlTester;

@GraphQlTest(BookGraphQlController.class)
@Import(BookCatalog.class)
class GraphQlSchemaTest {

    @Autowired
    private GraphQlTester tester;

    @Test
    void nestedAuthorIsResolvedBySchemaMapping() {
        tester.document(
                "{ book(id: \"b1\") { title author { name } } }")
                .execute()
                .path("book.title")
                .entity(String.class)
                .isEqualTo("Spring Boot");

        tester.document(
                "{ book(id: \"b1\") { author { name } } }")
                .execute()
                .path("book.author.name")
                .entity(String.class)
                .isEqualTo("Lan");
    }

    @Test
    void missingBookIsNullableByContract() {
        tester.document("{ book(id: \"missing\") { id } }")
                .execute()
                .path("book")
                .valueIsNull();
    }
}
```

`@GraphQlTest` chỉ auto-configure GraphQL infrastructure, không tự quét mọi `@Service`. Vì demo controller cần `BookCatalog`, test dùng `@Import(BookCatalog.class)` để đăng ký service in-memory. Nếu service thật gọi database, thông thường dùng mocks/fakes thay vì kéo toàn bộ database vào test slice.

`GraphQlTester` kiểm tra response theo **GraphQL path tương đối với `data`**, ví dụ `book.author.name`. Nếu có unexpected GraphQL errors, tester thường báo fail, giúp phát hiện mapping/schema issues. Test này không chứng minh CORS, proxy headers hay actual HTTP route `/graphql` hoạt động — đó là tầng khác.

## 32. Test HTTP thật: `HttpGraphQlTester` kiểm tra transport và execution

Spring Boot 3.3 hỗ trợ `HttpGraphQlTester` khi có `spring-graphql-test` và test WebFlux/WebTestClient dependencies theo tài liệu. Với `@SpringBootTest(webEnvironment=RANDOM_PORT)`, có HTTP server thật và tester gọi endpoint qua web transport.

**`src/test/java/com/example/bookgraphql/GraphQlHttpTest.java`:**

```java
package com.example.bookgraphql;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.HttpGraphQlTester;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GraphQlHttpTest {

    @Autowired
    private HttpGraphQlTester tester;

    @Test
    void queryWorksOverHttpTransport() {
        tester.document(
                "query($id: ID!) { book(id:$id) { id title } }")
                .variable("id", "b1")
                .execute()
                .path("book.id")
                .entity(String.class)
                .isEqualTo("b1");
    }

    @Test
    void mutationBindsGraphQlInputObject() {
        tester.document(
                "mutation { addBook(input: " +
                "{title:\"API Design\", authorId:\"a1\"}) " +
                "{ title author { name } } }")
                .execute()
                .path("addBook.author.name")
                .entity(String.class)
                .isEqualTo("Lan");
    }
}
```

Chạy:

```bash
./gradlew test
```

**Kết quả mong muốn** nếu test dependencies, schema, Java code và runtime phù hợp: các tests **PASS**. Không có stdout cố định cho Gradle vì logs và runtime khác nhau.

Để chứng minh từng ranh giới:

- `GraphQlSchemaTest` PASS nhưng `GraphQlHttpTest` FAIL → xem HTTP transport path, security/filter/codec/server config.
- Cả hai FAIL với lỗi `Query.book` không có trong schema → xem SDL, resolver mapping/`GraphQlSource`.
- Cả hai PASS nhưng query nhiều books chậm → xem application service/data loader/repository và query cost.
- Query PASS với một user nhưng lộ data giữa tenants → lỗi **authorization**, không phải schema syntax.

Không dùng riêng một `@WebMvcTest` REST controller để kết luận GraphQL field resolution đã đúng; `@GraphQlTest` là slice phù hợp hơn cho trường hợp schema/resolver.

## 33. Kiểm tra lỗi thực tế: query validation và dữ liệu nghiệp vụ

Gửi query field không tồn tại:

```bash
curl -i \
  -H 'Content-Type: application/json' \
  --data '{"query":"{ book(id: \"b1\") { hiddenPassword } }"}' \
  http://127.0.0.1:8080/graphql
```

Vì SDL không định nghĩa `Book.hiddenPassword`, GraphQL validation từ chối field. Response sẽ có thông tin `errors` về validation; **HTTP status cụ thể có thể khác tùy GraphQL-over-HTTP media type và implementation**, nên không cố viết một output 200 cố định.

Gửi query một book không tồn tại:

```bash
curl -sS \
  -H 'Content-Type: application/json' \
  --data '{"query":"{ book(id: \"unknown\") { id title } }"}' \
  http://127.0.0.1:8080/graphql
```

Với `BookCatalog.book` trả `null` và schema `Query.book: Book`, kết quả logic:

```json
{"data":{"book":null}}
```

Nếu mutation có `title:""` (chuỗi rỗng), schema input `String!` vẫn cho phép cấu trúc đó, nhưng service ném `IllegalArgumentException`. Với default exception handling, response có GraphQL error theo cơ chế của Spring GraphQL; thông điệp có thể được che và không nhất thiết là `"Title must not be blank"`.

**Phân biệt:** unknown field là **schema validation error trước resolver**; unknown book là **null business result** được schema cho phép; blank title là **business validation failure trong resolver/service**. Chúng không nên bị làm phẳng thành một loại HTTP 500 rồi che mất ngữ nghĩa.

## 34. `GraphQlSource`, wiring thủ công và customized scalars

Annotated controllers là cách thông dụng cho Spring for GraphQL, nhưng GraphQL Java runtime thực chất dùng **data fetchers** được gắn vào schema qua runtime wiring. Khi cần tự tạo field fetcher, custom scalar hoặc type resolver, dùng `RuntimeWiringConfigurer`/`GraphQlSourceBuilderCustomizer` theo API tương ứng.

Ví dụ khái niệm:

```java
@Bean
RuntimeWiringConfigurer wiringConfigurer() {
    return wiring -> wiring.type(
            "Query",
            builder -> builder.dataFetcher(
                    "serverTime",
                    environment -> "2026-01-01T00:00:00Z"));
}
```

Đây là **mẫu tích hợp**, cần schema có `Query.serverTime: String!`, imports `RuntimeWiringConfigurer`, `Bean`, và không nên đăng ký thêm một `@QueryMapping serverTime` trùng binding. Literal timestamp chỉ để minh họa output, không phải system clock.

Thành phần chính:

- `GraphQlSource` xây engine từ SDL cùng wiring.
- `RuntimeWiringConfigurer` thêm custom `DataFetcher` và scalars.
- `AnnotatedControllerConfigurer` đăng ký resolver methods vào runtime wiring.
- `ExecutionGraphQlService` nhận GraphQL request object và gọi GraphQL Java.
- Web transport xử lý HTTP/WebSocket/RSocket cụ thể rồi chuyển vào execution service.

**Một schema field phải có cách fetch hợp lệ**: có thể là annotated resolver, custom DataFetcher hoặc default property fetcher. Việc schema validation thành công không chứng minh business field luôn resolve đúng; tests cần cover các fields quan trọng.

Nếu schema mở custom scalar `DateTime`, cần chỉ rõ coercion/serialization và test values. Không giả định mọi Java `LocalDateTime` được GraphQL Java serialize đúng chỉ vì class tồn tại; SDL scalar và Java runtime coercing phải có wiring tương ứng.

## 35. Quan sát lỗi theo từng tầng trong production

| Triệu chứng | Tầng nghi ngờ | Điểm kiểm tra |
| --- | --- | --- |
| POST `/graphql` 404 | HTTP route/transport | `spring.graphql.path`, dependencies web starter, base/context path |
| Startup báo thiếu schema | SDL resource | `.graphqls`/`.gqls`, `src/main/resources/graphql`, classpath |
| Startup báo field/type mismatch | SDL/wiring | Schema definition, duplicate types, mappings |
| Query field không tồn tại | GraphQL validation | SDL type, selected field, version client |
| Method `@QueryMapping` không được gọi | GraphQL execution/wiring | `@Controller` scan, method name/schema field, request validation |
| Field scalar có giá trị null lạ | Java property fetch/model | JavaBean getter, mapping, nullability |
| Query có `data` và `errors` | GraphQL field execution | `errors.path`, exception resolver, null propagation |
| HTTP 200 nhưng client nghĩ fail | GraphQL error handling ở client | Đọc `errors` và `data`, không chỉ status |
| Books query chậm với nhiều authors | Resolver/data access | N+1, `@BatchMapping`, DB query count |
| GraphQL trả dữ liệu của tenant khác | Authorization/service | Owner/tenant checks, DataLoader cache scope |
| Proxy chặn CORS preflight | HTTP/gateway | Origin policy, OPTIONS handling, Spring Security |
| WebSocket subscription không kết nối | Streaming transport | WebSocket starter/path, handshake/auth/idle timeout |
| Mutation làm DB thay đổi một phần | Business transaction | Service transaction boundaries/rollback |
| Test schema PASS, HTTP test FAIL | Transport | HTTP routing, filters, server port, JSON |
| HTTP endpoint chạy nhưng GraphiQL 404 | Dev tooling | `spring.graphql.graphiql.enabled` mặc định tắt |
| Schema printer không trả nội dung | Dev tooling | `spring.graphql.schema.printer.enabled` mặc định tắt |

Chẩn đoán theo thứ tự: **request public URL → HTTP filter/route → WebGraphQlHandler/interceptor → parse/validate/schema → field resolver → service/repository → GraphQL result → HTTP serialization**. Xác định **tầng đầu tiên sai** trước khi sửa code; không giải quyết lỗi `@SchemaMapping` bằng cách thêm một REST `@PostMapping`.

Metrics/tracing nên tách HTTP route status/latency, GraphQL operation/field timings, data fetcher errors, batch sizes, downstream DB/API latency và query complexity. Tránh đưa raw GraphQL query/user ID làm tag metric có cardinality vô hạn hoặc log toàn bộ variables chứa PII.

## 36. Checklist thiết kế API GraphQL lành mạnh

Trước khi release:

1. Có schema SDL rõ ràng được version-control và test contract.
2. Có transport starter/cấu hình đúng: MVC/WebFlux; HTTP `/graphql` theo Boot 3.3.
3. Không tạo `@PostMapping("/graphql")` trùng endpoint framework nếu không có lý do đặc biệt.
4. Các resolver được map đến GraphQL fields đúng bằng `@QueryMapping`, `@MutationMapping`, `@SchemaMapping`; không nhầm HTTP mappings.
5. Domain/JPA entities không bị expose nguyên vẹn ngoài ý định; dùng DTO/projection có kiểm soát.
6. Input DTO được validate nghiệp vụ, không chỉ dựa vào GraphQL `String!`/`ID!`.
7. Authorization được thực hiện ở object/tenant/field level, kể cả nested resolvers và batch loaders.
8. Query cost/depth, pagination và data loader giới hạn workload độc hại/đắt đỏ.
9. Errors được xử lý theo GraphQL semantics; không coi HTTP 200 là thành công tuyệt đối.
10. Không đưa stack trace, dữ liệu nhạy cảm hoặc SQL details ra `errors.message`.
11. HTTP CORS, CSRF, TLS, size limits, authentication và proxy trust boundaries được thiết kế độc lập với schema.
12. Có test **GraphQL execution không HTTP** (`@GraphQlTest`) và **HTTP transport** (`@SpringBootTest`/`HttpGraphQlTester`).
13. Có schema compatibility review cho non-null, arguments, enum, rename/deprecation.
14. Nếu bật subscriptions, thiết kế transport, auth, cancellation, backpressure và reconnect.
15. Có observability cho execution/field errors, DB query count, request correlation và timeouts.

Khi cần một endpoint REST song song, dùng **cùng service nghiệp vụ** nhưng hai adapters khác nhau: REST `@RestController` và GraphQL `@Controller`/`@QueryMapping`. Tránh copy business rules vào từng adapter vì dễ dẫn tới khác hành vi authorization.

## 37. Tự đánh giá và bài tập

1. Nếu HTTP POST `/graphql` đến server thành công nhưng GraphQL query có field không tồn tại, tầng nào phải báo lỗi đầu tiên? Resolver có được gọi không?
2. `@QueryMapping` và `@GetMapping` khác nhau về route và abstraction như thế nào?
3. Khi dùng `BookView.getAuthorId()` trong resolver, vì sao GraphQL client không tự truy vấn được `authorId`?
4. `Book.author: Author!` có yêu cầu gì với resolver? Nếu author không có, null propagation xảy ra thế nào?
5. Tại sao một HTTP request GraphQL có thể gây N+1 SQL queries?
6. Muốn đổi Postgres sang một API khác mà giữ contract `Book.author`, tầng nào cần đổi và tầng nào có thể giữ?
7. Vì sao schema không thay thế ACL/tenant checks cho `Query.book(id: ID!)`?
8. `GraphQlTester` trong `@GraphQlTest` kiểm thử những gì và không kiểm thử những gì?
9. Vì sao test HTTP thực phải kiểm tra cả `data` lẫn `errors`, không chỉ HTTP status?
10. `GraphQLContext` khác `HttpServletRequest`, JPA persistence context và Singleton cache ra sao?
11. Khi thêm một GraphQL field mới, vì sao không nhất thiết phải viết resolver Java riêng?
12. Nếu backend Servlet MVC dùng repository blocking, có nên chuyển sang WebFlux chỉ vì GraphQL không?
13. Nếu bật GraphiQL và introspection, security risk nào cần xem xét và điều gì **không** được khắc phục bằng cách tắt introspection?
14. Query yêu cầu 10.000 nested objects nhưng HTTP body chỉ vài trăm bytes. Vì sao request body limit chưa đủ?
15. Một resolver mutation ném `IllegalArgumentException` sau khi đã ghi một phần database. SDL, GraphQL exception resolver hay business transaction mới là nơi xử lý rollback?

**Bài tập A:** Chạy demo từ mục 10 đến 16. Gửi query chỉ chọn `title` rồi query chọn `author { name }`; quan sát mỗi response chứa đúng selected fields.

**Bài tập B:** Tạm xóa `@SchemaMapping(typeName="Book",field="author")` rồi gửi query có `author`. Tìm hiểu kết quả default data fetcher và non-null contract; khôi phục resolver. Chỉ làm trong môi trường học tập.

**Bài tập C:** Thay `@SchemaMapping Book.author` bằng `@BatchMapping` của mục 22, thêm ít nhất 20 books, thay in-memory lookup bằng mock bulk repository và đếm số backend calls. Xác nhận số calls không tăng tuyến tính theo số books.

**Bài tập D:** Viết test GraphQlTester cho `book(id:"missing")` trả null; viết test HTTP bằng curl cho query có field không tồn tại và phân loại lỗi theo **transport/validation/business**.

**Bài tập E:** Thêm một REST endpoint đọc `BookCatalog.book` nhưng không nhân đôi logic service; so sánh HTTP routing của REST với GraphQL field routing và cách kiểm tra authorization.

## 38. Kết luận: một endpoint HTTP, nhiều GraphQL fields, một lớp domain độc lập

**Ranh giới dễ nhớ:**

```text
HTTP runtime:
  làm sao request tới ứng dụng và response ra khỏi ứng dụng

GraphQL schema:
  client được phép mô tả operation/field/shape nào

GraphQL execution + resolver:
  field hợp lệ được lấy dữ liệu từ đâu và xử lý lỗi ra sao

Domain/data model:
  dữ liệu thật là gì, ai được dùng và trạng thái thay đổi hợp lệ ra sao
```

Trong Spring Boot 3.3, `spring-boot-starter-graphql` cùng web starter giúp nối HTTP `/graphql` tới GraphQL Java engine. **SDL trong `resources/graphql` là public contract**, còn `@QueryMapping`, `@MutationMapping`, `@SchemaMapping` là field resolvers. Service/domain/repositories nằm phía sau, không nên phụ thuộc vào cách HTTP body đóng gói GraphQL query. Khi nắm đúng ranh giới này, ứng dụng dễ kiểm thử, hạn chế lộ dữ liệu và có thể đổi transport, persistence hoặc tối ưu data loading mà vẫn giữ schema ổn định.

### Tài liệu tham khảo chính thức

- Spring Boot 3.3, Spring for GraphQL — schema, transports, wiring, tests: https://docs.spring.io/spring-boot/3.3/reference/web/spring-graphql.html
- Spring Boot 3.3, Testing Spring Boot Applications — GraphQL tests: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3, Common Application Properties — `spring.graphql.*`: https://docs.spring.io/spring-boot/3.3/appendix/application-properties/
- Spring for GraphQL — Annotated Controllers: https://docs.spring.io/spring-graphql/reference/controllers.html
- Spring for GraphQL — Request Execution and GraphQlSource: https://docs.spring.io/spring-graphql/reference/request-execution.html
- Spring for GraphQL — Testing / GraphQlTester: https://docs.spring.io/spring-graphql/reference/testing.html
- GraphQL Specification — Schema, Execution, Errors, Nullability: https://spec.graphql.org/
- GraphQL over HTTP Working Draft — request/response transport conventions: https://graphql.github.io/graphql-over-http/draft/