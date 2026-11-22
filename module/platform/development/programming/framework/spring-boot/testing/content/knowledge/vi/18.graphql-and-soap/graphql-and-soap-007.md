# Kiểm thử GraphQL resolver phụ thuộc service, DataLoader và ngữ cảnh

> **Module:** Spring Boot – testing  
> **Nhóm:** GraphQL và SOAP  
> **Đề bài:** Kiểm thử resolver phụ thuộc service, DataLoader và ngữ cảnh  
> **Phạm vi chính:** GraphQL resolver trong Spring for GraphQL, service được inject, DataLoader theo request, GraphQLContext, kiểm tra N+1, ranh giới authorization, test slice và test HTTP. SOAP có mô hình endpoint riêng và chỉ được đối chiếu khi cần phân biệt công cụ.

## 1. Vì sao GraphQL resolver phải được kiểm tra ở nhiều lớp?

Trong REST, một controller thường trả về một DTO đã có các trường được chuẩn bị sẵn. Trong GraphQL, client **chọn các field** trong một document; hệ thống thực hiện một tập data fetchers/resolvers tương ứng, có thể đi qua nhiều service và DataLoader:

```graphql
query {
  books {
    id
    title
    author {
      id
      displayName
    }
  }
}
```

Để trả lời document này, ứng dụng có thể:

1. Chạy `@QueryMapping` cho field `Query.books`.
2. Gọi `BookService` để lấy danh sách sách có thể xem.
3. Với từng sách, chạy `@SchemaMapping(typeName="Book", field="author")`.
4. Resolver `Book.author` gọi `DataLoader.load(authorId)` thay vì gọi database một lần cho từng sách.
5. DataLoader gom các key, truy vấn `AuthorService` theo batch, trả kết quả ứng với đúng key.
6. Context của request chứa thông tin người dùng/tenant **đã được xác thực** hoặc những metadata khác để service phân quyền.
7. GraphQL engine xây response `data` và, nếu có lỗi, có thể trả thêm `errors` thay vì bắt buộc toàn bộ HTTP request thất bại.

Một test chỉ gọi trực tiếp `bookController.books(...)` sẽ **không** kiểm tra Schema, GraphQL Java field execution, DataLoader dispatch, path của response hoặc error semantics. Một test chỉ thấy JSON trả ra đúng có thể **không** chứng minh đã batch thay vì phát sinh N+1 truy vấn. Một test chỉ đếm service calls nhưng không kiểm tra tenant/context có thể bỏ sót việc trả dữ liệu của người dùng khác.

**Mục tiêu là phối hợp ít nhất ba loại bằng chứng:**

- **Dữ liệu:** `GraphQlTester` trả đúng field/path, value, nullability và errors theo schema.
- **Sự cộng tác:** Resolver gọi service đúng argument, DataLoader gom đúng tập key và gắn kết quả theo đúng id.
- **Ranh giới request:** Tenant/principal/context của từng request được truyền tới loader, không rò cache giữa hai người dùng; thiếu context quan trọng phải fail rõ.

## 2. Mô hình thực thi và vị trí các công cụ

```text
   GraphQL client / document
              │
              ▼
 HTTP / WebSocket / RSocket transport  ── chỉ ở test qua transport
              │
              ▼
 WebGraphQlInterceptor chain           ── thêm authenticated context
              │
              ▼
 ExecutionGraphQlService
              │
              ▼
 GraphQL Java execution
              │
       @QueryMapping books
              │
       BookService.visibleBooks(tenant)
              │
              ├── Book b1 ── @SchemaMapping author ──┐
              ├── Book b2 ── @SchemaMapping author ──┤ load(authorId)
              └── Book b3 ── @SchemaMapping author ──┘
                                                     │
                                      per-request DataLoaderRegistry
                                                     │
                           one or more batched dispatches of unique keys
                                                     │
                              AuthorService.findByIds(keys, tenant)
                                                     │
                                      Map<authorId, Author>
                                                     │
                                     GraphQL data / errors
```

**Phân biệt:**

| Thành phần | Trách nhiệm | Test quan trọng |
| --- | --- | --- |
| `@QueryMapping` | Resolve root field của `Query` | Query document → đúng list/argument/tenant |
| `@SchemaMapping` | Resolve field lồng trong source/parent object | Đúng field parent, đúng key và path |
| `@BatchMapping` | Tự đăng ký batch resolver + DataLoader dưới lớp vỏ Spring | Không tạo N+1, đúng kết quả cho từng parent |
| `BatchLoaderRegistry` | Đăng ký mapped/ordered batch loader theo tên hoặc cặp type | Đúng loader name, set key, context, cache |
| `DataLoader<K,V>` | Hoãn, gom, dispatch và cache lời gọi `load(key)` trong một request | Một batch cho các key ở cùng dispatch, key/result association |
| `GraphQLContext` | Metadata gắn với một GraphQL execution | Không tin dữ liệu client chưa xác thực; tách request |
| `@ContextValue` | Nhận một key từ `GraphQLContext` vào controller | Presence, type, policy với missing context |
| `WebGraphQlInterceptor` | Can thiệp request từ transport, cấu hình `ExecutionInput`/context | Header/auth → context, thứ tự interceptor |
| `GraphQlTester` | Kiểm thử GraphQL document và response data/errors | Value paths, errors, variables, list/null fields |

**Lưu ý:** GraphQL schema resolver là phương thức `@QueryMapping`/`@SchemaMapping` được gọi qua GraphQL execution. SOAP endpoint là cơ chế khác (`@Endpoint`, `@PayloadRoot`, XML/SOAP Envelope); không dùng `GraphQlTester` để test SOAP. Bài này tập trung đúng đề bài trực tiếp: GraphQL resolver và DataLoader.

## 3. Vì sao gọi từng author là N+1?

Giả sử `books` trả 100 sách. Một implementation ngây thơ:

```java
@SchemaMapping(typeName = "Book", field = "author")
public Author author(Book book) {
    return authorService.findOne(book.authorId());
}
```

Đây là **mã minh họa**, không nằm trong project chạy được bên dưới. Nếu `BookService` tốn một truy vấn để lấy 100 sách và resolver gọi `AuthorService` 100 lần, tổng có thể thành **1 + 100** round-trips (N+1). Không phải mọi lời gọi service đều tương ứng một SQL statement; đây là mô hình rủi ro khi service đi tới database/remote API.

Dùng DataLoader:

```java
@SchemaMapping(typeName = "Book", field = "author")
public CompletableFuture<Author> author(
        Book book,
        DataLoader<String, Author> loader) {
    return loader.load(book.authorId());
}
```

Spring for GraphQL phối hợp GraphQL Java để các calls `load(...)` cùng nhịp execution có thể được **batch**. Thay vì hàng trăm lời gọi đơn lẻ, loader gom các key độc nhất và gửi `Set<String>` tới một batch function.

**Không được khẳng định “DataLoader luôn chỉ gọi service một lần cho mọi GraphQL query”.** Số batch còn phụ thuộc GraphQL execution levels, lồng field, thời điểm dispatch, `maxBatchSize`, query complexity, scheduler, cache settings và số request. Một test tập trung vào **một query shape cụ thể** có thể bảo vệ “với 3 sách và 2 author id, chỉ 1 batch”; điều đó không đồng nghĩa mọi document của ứng dụng chỉ tạo 1 batch.

### 3.1. Key ↔ value phải được ghép đúng

Ví dụ key cần tải:

```text
load("a-1")  ─┐
load("a-2")   ├── batch Set{"a-1","a-2"} → Map{"a-1":AuthorA,"a-2":AuthorB}
load("a-1")  ─┘

  Hai lời gọi load("a-1") trong một request
  có thể chia sẻ cached future/result nếu cache bật.
```

Với mapped loader, batch function trả `Map<K,V>` nên framework dựa vào key để ghép lại; **thứ tự iteration của Set/Map không được dùng làm thứ tự GraphQL output**. Với ordered loader trả `List<V>`, thứ tự trong list phải khớp thứ tự keys đầu vào. Test phải bắt lỗi “a-1 trả nhầm AuthorB”, không chỉ đếm số phần tử.

### 3.2. DataLoader cache không phải global application cache

GraphQL Java DataLoader thường cache loaded values theo key **trong một `DataLoaderRegistry` của request**. Spring for GraphQL và `BatchLoaderRegistry` đảm nhận đăng ký các DataLoader phù hợp cho mỗi execution.

Nếu tự giữ một `DataLoader` singleton/global hoặc chia sẻ `DataLoaderRegistry` giữa các request, key như `"a-1"` có thể trả dữ liệu user A cho user B khi output còn phụ thuộc tenant/permission. **Không chia sẻ per-request loader cache qua ranh giới bảo mật.** Nếu cố tình sử dụng cache chung, cache key phải bao gồm tất cả chiều phân quyền và phải có cơ chế invalidation/TTL thích hợp.

## 4. Service, DataLoader và context là ba ranh giới khác nhau

### 4.1. Test resolver với service mock

`@GraphQlTest(BookGraphQlController.class)` là Spring Boot slice cho GraphQL controllers. Nó chọn GraphQL infrastructure và một tập bean phù hợp nhưng không quét mọi `@Service`, `@Repository`. Để controller khởi tạo, dùng `@MockitoBean` cung cấp service collaborators.

Điều test chứng minh: schema mapping, GraphQL field paths, argument resolution, việc resolver chuyển đúng input sang service.

Điều test **không** chứng minh: BookService thật có truy vấn database đúng, endpoint HTTP thật có security filter, production loader có thể kết nối external service, nếu chính chúng đã được mock.

### 4.2. Test DataLoader với service mock

DataLoader thuộc graph execution; cách đúng để bắt N+1 thường là:

- Giữ DataLoader registration/configuration **thật**.
- Mock `AuthorService` ở ranh giới dữ liệu.
- Thực thi GraphQL document yêu cầu field lồng cho nhiều parent.
- Assert **đúng giá trị theo từng parent** và `verify(authorService, times(1)).findByIds(expectedKeys, expectedTenant)` cho query shape cụ thể.
- Lặp lại với hai tenant request để xác nhận context được truyền và cache tách nhau.

Nếu mock chính DataLoader trong test, bạn bỏ qua dispatch/batching/caching thực, vì thế không thể dùng nó để khẳng định đã giải quyết N+1.

### 4.3. Test context ở hai cấp độ

- **Execution context test:** tạo một `ExecutionGraphQlServiceTester` và cấu hình `ExecutionInput.graphQLContext` theo test. Cách này kiểm tra resolver và loader có nhận đúng context **sau khi đã được đặt vào execution** không; **không** đi qua HTTP/WebGraphQlInterceptor.
- **Transport context test:** dùng `HttpGraphQlTester` qua Spring MVC/WebFlux test client hoặc server thật, gửi header/cookie/token giả. `WebGraphQlInterceptor` chuyển metadata an toàn vào GraphQLContext rồi chạy resolver/loader. Cách này kiểm tra cả dây truyền **transport → interceptor → context → service**.

Đừng dùng test execution-direct rồi tuyên bố một HTTP request thiếu header sẽ bị reject: test đó đã **bỏ qua** transport/interceptor.

### 4.4. Context không tự đồng nghĩa authorization

`GraphQLContext` có thể chứa traceId, locale, feature flag, tenant hoặc principal. **Một header `X-Demo-Tenant` do client tự điền không chứng minh caller có quyền xem tenant đó.** Trong production:

- Đọc identity từ Spring Security `Authentication`, validated JWT claims/session hoặc service-to-service authentication được tin cậy.
- Kiểm tra membership/quyền trên tenant ở service/DB layer, không chỉ trong resolver.
- Không để client chọn tenant tự do rồi dùng nó làm filter dữ liệu mà không kiểm chứng.
- Với async/`CompletableFuture`/reactive code, hiểu propagation của SecurityContext/ThreadLocal/Reactor Context; không dựa vào `ThreadLocal` thuần giữa threads.
- Không đặt access token hoặc PII nhạy cảm vào log GraphQL request, DataLoader keys, metrics labels hay test failure output.

**Toàn bộ project mẫu dùng `X-Demo-Tenant` chỉ để mô phỏng cách truyền context**, không phải triển khai authentication/authorization.

## 5. Dự án Maven chạy được với Spring GraphQL

Dùng **Java 17, Maven, Spring Boot 3.5.0**, Spring for GraphQL do Spring Boot quản lý phiên bản. Ví dụ chạy trên in-memory services, không cần database, API ngoài hay secret. Có một query nhiều books, mỗi book có author được resolve qua DataLoader.

### 5.1. Cấu trúc thư mục

```text
graphql-resolver-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/graphqltest/
    │   │   ├── GraphQlLabApplication.java
    │   │   ├── Book.java
    │   │   ├── Author.java
    │   │   ├── BookService.java
    │   │   ├── AuthorService.java
    │   │   ├── BookGraphQlController.java
    │   │   ├── AuthorLoaderConfiguration.java
    │   │   └── DemoTenantInterceptor.java
    │   └── resources/graphql/
    │       └── schema.graphqls
    └── test/
        └── java/com/example/graphqltest/
            ├── BookResolverSliceTest.java
            └── BookGraphQlHttpTest.java
```

Mỗi `public` class/record được đặt trong tệp trùng tên và `package com.example.graphqltest`. Không đổi tên `graphql/schema.graphqls` thành `schema.json`: Spring GraphQL tải SDL từ resource dưới `classpath:graphql/**` theo cấu hình mặc định phù hợp.

### 5.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>graphql-resolver-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-graphql</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.graphql</groupId>
            <artifactId>spring-graphql-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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
```

**Vì sao có các dependencies ấy?**

- `spring-boot-starter-graphql`: GraphQL Java, annotated controllers, `BatchLoaderRegistry`.
- `spring-boot-starter-web`: ứng dụng dùng Spring MVC HTTP transport.
- `spring-boot-starter-test`: JUnit Jupiter, Mockito, AssertJ, Spring Test/Boot testing.
- `spring-graphql-test`: `GraphQlTester`, `ExecutionGraphQlServiceTester`, `HttpGraphQlTester`.
- `spring-boot-starter-webflux` ở `scope=test`: có `WebTestClient` để `HttpGraphQlTester` kiểm tra MVC HTTP endpoint qua mock client. **Không chủ động biến app production thành WebFlux**; với cả MVC và WebFlux trên test classpath, Boot thông thường ưu tiên Servlet MVC.

Spring Boot parent quản lý phiên bản dependencies tương thích; không thêm riêng GraphQL Java/DataLoader versions vào POM mẫu để tránh xung đột.

### 5.3. GraphQL SDL contract

```graphql
# src/main/resources/graphql/schema.graphqls

type Query {
  books: [Book!]!
}

type Book {
  id: ID!
  title: String!
  author: Author
}

type Author {
  id: ID!
  displayName: String!
}
```

**Contract:**

- Query `books` trả một list không-null của các `Book` không-null.
- `Book.author` có thể null: một author không thấy/không tồn tại **không nhất thiết** khiến cả list books null. Nếu đổi schema thành `Author!`, lỗi/null có thể propagate lên parent.
- `id` có GraphQL type `ID!` và Java sample dùng `String`.
- `Book` có field nội bộ `authorId` nhưng **không** khai báo nó trong schema; nó là key dành cho DataLoader chứ không phải field public client luôn được xem.
- Không có field SOAP/XML trong schema; GraphQL SDL dùng type/field riêng.

### 5.4. Spring Boot application và records

```java
// src/main/java/com/example/graphqltest/GraphQlLabApplication.java
package com.example.graphqltest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GraphQlLabApplication {
    public static void main(String[] args) {
        SpringApplication.run(GraphQlLabApplication.class, args);
    }
}
```

```java
// src/main/java/com/example/graphqltest/Book.java
package com.example.graphqltest;

public record Book(String id, String title, String authorId) {}
```

```java
// src/main/java/com/example/graphqltest/Author.java
package com.example.graphqltest;

public record Author(String id, String displayName) {}
```

Java records ở đây có `equals`/`hashCode` xác định và dễ test. Chúng không phải JPA entities. Dữ liệu giả `team-a`/`team-b` chỉ dùng để minh họa tenant context.

### 5.5. Hai services thật cho demo

```java
// src/main/java/com/example/graphqltest/BookService.java
package com.example.graphqltest;

import java.util.List;

import org.springframework.stereotype.Service;

@Service
public class BookService {

    public List<Book> visibleBooks(String tenant) {
        if (tenant == null || tenant.isBlank()) {
            throw new IllegalArgumentException("Tenant is required");
        }
        return List.of(
                new Book("b-1", "GraphQL Essentials", "a-1"),
                new Book("b-2", "Spring Testing", "a-2"),
                new Book("b-3", "DataLoader Patterns", "a-1"));
    }
}
```

```java
// src/main/java/com/example/graphqltest/AuthorService.java
package com.example.graphqltest;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;

import org.springframework.stereotype.Service;

@Service
public class AuthorService {

    public Map<String, Author> findByIds(
            Set<String> ids, String tenant) {
        if (tenant == null || tenant.isBlank()) {
            throw new IllegalArgumentException("Tenant is required");
        }
        Map<String, Author> result = new LinkedHashMap<>();
        for (String id : ids) {
            if (id.equals("a-1") || id.equals("a-2")) {
                result.put(id,
                        new Author(id, tenant + ":" + id));
            }
        }
        return result;
    }
}
```

Hai services cố ý **không gọi external dependencies** nên full context test chạy offline. Author name chứa tenant trong chuỗi để test quan sát được context từng request.

Trong ứng dụng thật, `visibleBooks(tenant)` và `findByIds(ids,tenant)` phải enforce authorization của principal, giới hạn tenant/resource và dùng query có điều kiện; **chỉ thêm tiền tố tên hiển thị không phải data isolation**. Không đưa implementation demo này vào production như cơ chế bảo mật.

### 5.6. Resolver root và field lồng

```java
// src/main/java/com/example/graphqltest/BookGraphQlController.java
package com.example.graphqltest;

import java.util.List;
import java.util.concurrent.CompletableFuture;

import org.dataloader.DataLoader;
import org.springframework.graphql.data.method.annotation.ContextValue;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
public class BookGraphQlController {

    private final BookService bookService;

    public BookGraphQlController(BookService bookService) {
        this.bookService = bookService;
    }

    @QueryMapping
    public List<Book> books(@ContextValue("tenant") String tenant) {
        return bookService.visibleBooks(tenant);
    }

    @SchemaMapping(typeName = "Book", field = "author")
    public CompletableFuture<Author> author(
            Book book,
            DataLoader<String, Author> loader) {
        return loader.load(book.authorId());
    }
}
```

**Cơ chế:**

- `@QueryMapping` ánh xạ phương thức `books` đến GraphQL root field `Query.books`.
- `@ContextValue("tenant")` lấy giá trị từ `GraphQLContext` của execution; nếu không có value trong tình huống cần thiết, method resolution có thể tạo GraphQL error.
- `@SchemaMapping(typeName="Book", field="author")` xác định field resolver, tham số `Book` là source/parent object.
- `DataLoader<String,Author>` được Spring GraphQL tìm và inject theo type/value type với registry; với `forTypePair(String.class, Author.class)` dưới đây, tên đăng ký mặc định tương ứng `Author.class.getName()`.
- Resolver trả `CompletableFuture<Author>`, không tự gọi `AuthorService.findByIds` từng sách. GraphQL Java sẽ phối hợp batch dispatch.
- `Book.authorId` là key. Hai sách b-1/b-3 dùng cùng a-1 nên DataLoader có thể tận dụng per-request cache.

**Không gọi `future.join()` trong chính resolver**: việc chặn chờ trên một DataLoader future trước dispatch có thể dẫn tới deadlock hoặc phá batching. Trả future cho GraphQL engine xử lý.

### 5.7. Đăng ký mapped DataLoader có truy cập request context

```java
// src/main/java/com/example/graphqltest/AuthorLoaderConfiguration.java
package com.example.graphqltest;

import graphql.GraphQLContext;

import org.springframework.context.annotation.Configuration;
import org.springframework.graphql.execution.BatchLoaderRegistry;
import reactor.core.publisher.Mono;

@Configuration(proxyBeanMethods = false)
public class AuthorLoaderConfiguration {

    public AuthorLoaderConfiguration(
            BatchLoaderRegistry registry,
            AuthorService authorService) {

        registry.forTypePair(String.class, Author.class)
                .registerMappedBatchLoader((authorIds, env) -> {
                    GraphQLContext context = env.getContext();
                    String tenant = context.get("tenant");

                    if (tenant == null || tenant.isBlank()) {
                        return Mono.error(
                                new IllegalStateException(
                                        "Missing tenant context"));
                    }

                    return Mono.just(
                            authorService.findByIds(authorIds, tenant));
                });
    }
}
```

**Điểm then chốt:**

1. `BatchLoaderRegistry` là bean do Spring for GraphQL starter cung cấp. Cấu hình đăng ký loader **một lần ở startup**, nhưng Spring GraphQL tạo/đăng ký DataLoader instances phù hợp **cho mỗi GraphQL request**.
2. `forTypePair(String.class, Author.class)` dùng key type `String` và result type `Author`. Theo mặc định, loader name có thể được suy từ full class name của value type; `@SchemaMapping` nhận `DataLoader<String,Author>` tương ứng.
3. `registerMappedBatchLoader` nhận các key (tập `Set<String>`) và `BatchLoaderEnvironment`. Nó trả `Mono<Map<String,Author>>` để ghép key → value.
4. `env.getContext()` được Spring GraphQL cung cấp cùng `GraphQLContext` của execution qua cơ chế registry. Lấy `tenant` **khi dispatch batch**, không chốt tenant ở singleton config constructor.
5. Kiểm tra context null để fail rõ ràng; không fallback sang một tenant mặc định khác.
6. Không lưu `GraphQLContext` hoặc `DataLoader` vào static field hay singleton cache; có thể gây dữ liệu giữa requests bị trộn.

**Không nhầm bối cảnh:** `BatchLoaderEnvironment#getContext()` từ Java DataLoader có thể chứa context object do registry wiring truyền vào. Với cơ chế `BatchLoaderRegistry` của Spring for GraphQL, cùng GraphQLContext được dùng ở GraphQL execution và batch loader. Nếu tự tạo DataLoaderRegistry thủ công, phải tự cấu hình context provider; điều đó không tự xảy ra chỉ vì có một `GraphQLContext` trong controller.

### 5.8. Transport interceptor mô phỏng cách tạo context

Để test đường HTTP → GraphQLContext, dự án khai báo một interceptor nhận `X-Demo-Tenant`. Nó chỉ mô phỏng context propagation trong test/demo, **không dùng làm bảo mật**.

```java
// src/main/java/com/example/graphqltest/DemoTenantInterceptor.java
package com.example.graphqltest;

import org.springframework.graphql.server.WebGraphQlInterceptor;
import org.springframework.graphql.server.WebGraphQlRequest;
import org.springframework.graphql.server.WebGraphQlResponse;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class DemoTenantInterceptor
        implements WebGraphQlInterceptor {

    @Override
    public Mono<WebGraphQlResponse> intercept(
            WebGraphQlRequest request, Chain chain) {

        String tenant = request.getHeaders()
                .getFirst("X-Demo-Tenant");

        if (tenant == null || tenant.isBlank()) {
            return Mono.error(new IllegalArgumentException(
                    "X-Demo-Tenant is required for demo"));
        }

        request.configureExecutionInput(
                (executionInput, builder) ->
                        builder.graphQLContext(context ->
                                context.put("tenant", tenant))
                                .build());

        return chain.next(request);
    }
}
```

**Trong full HTTP test**, header được set trên mock HTTP client, interceptor đưa `tenant` vào `GraphQLContext`, controller và loader nhận cùng giá trị.

**Trong `@GraphQlTest` qua `ExecutionGraphQlServiceTester`**, không có transport, interceptor không chạy. Test phải đặt context vào `ExecutionInput` trực tiếp; đó không phải workaround sai mà chính là tách phạm vi theo mục đích.

Một HTTP request thiếu header trong demo có thể bị chặn ở transport qua `Mono.error`, nhưng ví dụ không định nghĩa HTTP exception handler/status contract cho lỗi đó. **Không assert 401/403** từ interceptor giả này. Trong ứng dụng thật, Spring Security phải xác thực request, rồi WebGraphQlInterceptor lấy principal/claims đã tin cậy và chuyển vào context có kiểm soát.

## 6. Test slice: resolver thật, service mock, loader registration thật

Đây là phần trọng tâm của bài: `@GraphQlTest` không dựng HTTP server; ta test GraphQL execution thực với service mocks và **DataLoader registration thật**, đồng thời tự đặt GraphQL context cho từng request.

### 6.1. Tại sao phải import loader configuration?

`@GraphQlTest(BookGraphQlController.class)` là slice: nó không tự nạp mọi `@Configuration` hoặc `@Service` trong ứng dụng.

Do đó trong test:

- `@MockitoBean BookService` tạo collaborator cho `@QueryMapping`.
- `@MockitoBean AuthorService` tạo collaborator cho batch loader.
- `@Import(AuthorLoaderConfiguration.class)` nạp config đăng ký DataLoader vào registry của test.
- `ExecutionGraphQlService` là GraphQL execution infrastructure do slice cấu hình.
- `ExecutionGraphQlServiceTester.builder(service).configureExecutionInput(...)` cho phép test cung cấp `GraphQLContext` mà không phải gửi HTTP.

Nếu bỏ `@Import`, resolver nhận `DataLoader<String,Author>` có thể không tìm thấy loader phù hợp. Nếu mock chính DataLoader hoặc chỉ gọi Java controller method trực tiếp, test không còn kiểm tra dispatch/mapping như mục tiêu.

### 6.2. `BookResolverSliceTest.java` — các case chính

```java
// src/test/java/com/example/graphqltest/BookResolverSliceTest.java
package com.example.graphqltest;

import java.util.List;
import java.util.Map;
import java.util.Set;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.context.annotation.Import;
import org.springframework.graphql.ExecutionGraphQlService;
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@GraphQlTest(BookGraphQlController.class)
@Import(AuthorLoaderConfiguration.class)
class BookResolverSliceTest {

    @Autowired
    ExecutionGraphQlService executionService;

    @MockitoBean
    BookService bookService;

    @MockitoBean
    AuthorService authorService;

    private ExecutionGraphQlServiceTester asTenant(String tenant) {
        return ExecutionGraphQlServiceTester
                .builder(executionService)
                .configureExecutionInput((input, builder) ->
                        builder.graphQLContext(context ->
                                context.put("tenant", tenant))
                                .build())
                .build();
    }

    private List<Book> books() {
        return List.of(
                new Book("b-1", "GraphQL Essentials", "a-1"),
                new Book("b-2", "Spring Testing", "a-2"),
                new Book("b-3", "DataLoader Patterns", "a-1"));
    }

    @Test
    void nestedAuthorResolverBatchesAndMapsByKey() {
        when(bookService.visibleBooks("team-a")).thenReturn(books());

        when(authorService.findByIds(
                Set.of("a-1", "a-2"), "team-a"))
                .thenReturn(Map.of(
                        "a-1", new Author("a-1", "team-a:Ada"),
                        "a-2", new Author("a-2", "team-a:Grace")));

        asTenant("team-a").document("""
                query {
                  books {
                    id
                    title
                    author { id displayName }
                  }
                }
                """)
                .execute()
                .path("books[0].title")
                .entity(String.class).isEqualTo("GraphQL Essentials")
                .path("books[0].author.displayName")
                .entity(String.class).isEqualTo("team-a:Ada")
                .path("books[1].author.id")
                .entity(String.class).isEqualTo("a-2")
                .path("books[1].author.displayName")
                .entity(String.class).isEqualTo("team-a:Grace")
                .path("books[2].author.displayName")
                .entity(String.class).isEqualTo("team-a:Ada");

        verify(bookService).visibleBooks("team-a");
        verify(authorService, times(1)).findByIds(
                Set.of("a-1", "a-2"), "team-a");
    }

    @Test
    void notSelectingAuthorDoesNotInvokeAuthorService() {
        when(bookService.visibleBooks("team-a")).thenReturn(books());

        asTenant("team-a").document("""
                { books { id title } }
                """)
                .execute()
                .path("books")
                .entityList(Map.class)
                .hasSize(3);

        verify(bookService).visibleBooks("team-a");
        verifyNoInteractions(authorService);
    }

    @Test
    void independentRequestsReceiveIndependentTenantContext() {
        when(bookService.visibleBooks("team-a")).thenReturn(books());
        when(bookService.visibleBooks("team-b")).thenReturn(books());

        when(authorService.findByIds(
                Set.of("a-1", "a-2"), "team-a"))
                .thenReturn(Map.of(
                        "a-1", new Author("a-1", "team-a:Ada"),
                        "a-2", new Author("a-2", "team-a:Grace")));

        when(authorService.findByIds(
                Set.of("a-1", "a-2"), "team-b"))
                .thenReturn(Map.of(
                        "a-1", new Author("a-1", "team-b:Ada"),
                        "a-2", new Author("a-2", "team-b:Grace")));

        String query = """
                { books { author { displayName } } }
                """;

        asTenant("team-a").document(query)
                .execute()
                .path("books[0].author.displayName")
                .entity(String.class).isEqualTo("team-a:Ada");

        asTenant("team-b").document(query)
                .execute()
                .path("books[0].author.displayName")
                .entity(String.class).isEqualTo("team-b:Ada");

        verify(authorService, times(1)).findByIds(
                Set.of("a-1", "a-2"), "team-a");
        verify(authorService, times(1)).findByIds(
                Set.of("a-1", "a-2"), "team-b");
    }

    @Test
    void missingContextMustNotSilentlyUseAnotherTenant() {
        ExecutionGraphQlServiceTester noTenant =
                ExecutionGraphQlServiceTester.create(
                        executionService);

        noTenant.document("""
                { books { id author { id } } }
                """)
                .execute()
                .errors()
                .satisfy(errors ->
                        assertThat(errors).isNotEmpty());

        verifyNoInteractions(bookService, authorService);
    }
}
```

**Bản chất của các test:**

1. `nestedAuthorResolverBatchesAndMapsByKey` bảo vệ **một query có 3 books, 2 distinct author IDs**, đúng output từng path và **một lần batch service call** với `Set.of("a-1","a-2")`. Đây là signal mạnh hơn việc chỉ đếm số lần resolver method được gọi.
2. `notSelectingAuthorDoesNotInvokeAuthorService` bảo vệ selection-set semantics: khi client không yêu cầu author, không cần tốn I/O author.
3. `independentRequestsReceiveIndependentTenantContext` bảo vệ việc hai GraphQL executions nối tiếp với key giống nhau không lấy nhầm cached author của tenant trước.
4. `missingContextMustNotSilentlyUseAnotherTenant` yêu cầu GraphQL execution trả lỗi khi `tenant` bắt buộc vắng, **không** fallback tenant khác. Dùng `errors().satisfy(...)` để assert có errors thay vì dùng `execute()` rồi lấy data path và kỳ vọng không có lỗi.

**Một số chi tiết API dễ nhầm:**

- `@GraphQlTest` trong Spring Boot 3.5 dùng import `org.springframework.boot.test.autoconfigure.graphql.GraphQlTest`.
- `ExecutionGraphQlService` nằm ở `org.springframework.graphql.ExecutionGraphQlService`, còn `ExecutionGraphQlServiceTester` ở `org.springframework.graphql.test.tester`.
- `@MockitoBean` là annotation override bean của Spring TestContext; `@Mock` của Mockito **không tự** tạo bean trong context.
- `GraphQlTester#path` sử dụng path **tương đối với `data`**, vì vậy `"books[0].author.displayName"` không thêm tiền tố `"data."`.
- `errors().satisfy(...)` dùng để xác minh lỗi có mặt. Nếu error là điều ngoài dự kiến, test bình thường nên fail, không filter hết mọi lỗi mặc định.
- Mockito mock reset giữa test methods theo cấu hình test mặc định; đừng cố giữ static mocks/counters qua nhiều tests.

### 6.3. Một giới hạn quan trọng của assertion “một lần batch”

Khi document trả nhiều books, GraphQL engine có thể dispatch theo execution level. Ở query mẫu có một level `Book.author` và 2 keys distinct nên thường có một mapped batch call. Tuy nhiên:

- Nếu thay query bằng nhiều nested levels, alias, fragments có đường execution khác nhau, số dispatch có thể tăng.
- Nếu đặt `maxBatchSize` nhỏ, một dispatch được chia ra nhiều calls.
- Nếu batch function bị duplicate registration hoặc cùng key bị `clear` cache, service có thể được gọi lại.
- Nếu authorService tự chia thành nhiều SQL queries, một mapped batch call vẫn không chứng minh DB chỉ nhận một query.

Vì vậy assertion `times(1)` là **hợp đồng hiệu năng có giới hạn cho scenario hiện tại**, không phải định lý về mọi workload. Nên có observability/metrics SQL hoặc traced downstream calls nếu đếm database round trips thực sự.

## 7. HTTP integration test: từ header qua interceptor tới loader

Test slice vừa rồi **không** chạy `DemoTenantInterceptor` vì không có transport. Để kiểm tra thêm việc tạo context từ header, dùng full Spring Boot test với `HttpGraphQlTester` và môi trường mock HTTP (không cần cổng TCP).

### 7.1. `BookGraphQlHttpTest.java`

```java
// src/test/java/com/example/graphqltest/BookGraphQlHttpTest.java
package com.example.graphqltest;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.tester.AutoConfigureHttpGraphQlTester;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.HttpGraphQlTester;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureHttpGraphQlTester
class BookGraphQlHttpTest {

    @Autowired
    HttpGraphQlTester graphQlTester;

    private HttpGraphQlTester tenant(String name) {
        return graphQlTester.mutate()
                .webTestClient(client ->
                        client.defaultHeader(
                                "X-Demo-Tenant", name))
                .build();
    }

    @Test
    void httpHeaderReachesRootResolverAndBatchLoader() {
        tenant("team-a").document("""
                {
                  books {
                    id
                    title
                    author { id displayName }
                  }
                }
                """)
                .execute()
                .path("books[0].author.displayName")
                .entity(String.class).isEqualTo("team-a:a-1")
                .path("books[1].author.displayName")
                .entity(String.class).isEqualTo("team-a:a-2")
                .path("books[2].author.displayName")
                .entity(String.class).isEqualTo("team-a:a-1");
    }

    @Test
    void httpRequestsDoNotShareTenantCache() {
        String document = """
                { books { id author { displayName } } }
                """;

        tenant("team-a").document(document)
                .execute()
                .path("books[0].author.displayName")
                .entity(String.class).isEqualTo("team-a:a-1");

        tenant("team-b").document(document)
                .execute()
                .path("books[0].author.displayName")
                .entity(String.class).isEqualTo("team-b:a-1");
    }
}
```

**Điểm kiểm tra:**

- Spring Boot nạp `BookService` và `AuthorService` **thật**, không dùng Mockito mocks.
- HTTP test client gửi `X-Demo-Tenant` qua mock HTTP layer.
- `DemoTenantInterceptor` được áp dụng vì có transport handler.
- `@ContextValue("tenant")` và mapped loader đọc tenant đúng từ GraphQLContext.
- `books[0]`/`books[2]` cùng author a-1 và không bị gắn với dữ liệu tenant khác.
- Hai requests dùng cùng author ids nhưng tên hiển thị chứa tenant đúng từng request.

**Đây không phải network E2E:** `@SpringBootTest(MOCK)` và `@AutoConfigureHttpGraphQlTester` kiểm tra HTTP handler trong mock server context, **không mở embedded HTTP listener**. Muốn kiểm thử socket thật có thể dùng `RANDOM_PORT` và tester phù hợp; khi đó test cũng cần quản lý port, security, credentials và hạ tầng.

### 7.2. Số test và lệnh chạy

Trong project chính có **6 JUnit test methods**: `BookResolverSliceTest` gồm **4**, `BookGraphQlHttpTest` gồm **2**. Chạy:

```bash
java -version
mvn -version

# Kiểm tra cả resolver slice và transport context:
mvn test

# Chạy riêng từng mức:
mvn -Dtest=BookResolverSliceTest test
mvn -Dtest=BookGraphQlHttpTest test
```

Cần JDK 17+ và Maven, có thể cần Internet để tải dependencies ban đầu. **Không có stdout cố định**: test count/port/log tùy môi trường. Điều cần bảo đảm là test methods pass theo assertion và Maven báo build thành công. Không có external database, broker hay cloud service được sử dụng trong project này.

**Một lưu ý vận hành:** Nếu môi trường không có `spring-graphql-test` hoặc WebFlux test client dependency, các tester sẽ không compile/autoconfigure. Đọc `pom.xml` và dependency tree trước khi sửa test thành HTTP socket test.

## 8. DataLoader nâng cao: cache, dispatch và batch mapping

### 8.1. Phân biệt batching với caching

**Batching** gom nhiều keys *đang chờ trong một execution dispatch* rồi gọi downstream theo lô. **Caching** lưu future/result theo key trong request để các lần `load("a-1")` tiếp theo tái sử dụng. Hai cơ chế thường phối hợp, nhưng có thể được cấu hình riêng.

Trong dữ liệu mẫu:

```text
Books:
  b-1 → a-1
  b-2 → a-2
  b-3 → a-1

Resolver calls:
  loader.load("a-1")
  loader.load("a-2")
  loader.load("a-1")

Unique batch keys:
  {"a-1", "a-2"}

GraphQL output:
  b-1.author = Author a-1
  b-2.author = Author a-2
  b-3.author = Author a-1
```

Nếu tắt DataLoader caching, loader có thể dispatch duplicate keys hoặc có behavior khác theo loader implementation. Đừng test “exactly two keys” mà bỏ qua cấu hình cache. Nếu dùng key là mutable object không có equals/hashCode ổn định, cache và mapped results có thể khó dự đoán.

### 8.2. Vì sao `@BatchMapping` thường đơn giản hơn?

Với case liên kết `Book.author` đơn thuần, Spring for GraphQL hỗ trợ:

```java
@Controller
class AlternativeBookController {
    private final AuthorService authorService;

    AlternativeBookController(AuthorService authorService) {
        this.authorService = authorService;
    }

    @BatchMapping(typeName = "Book", field = "author")
    public Map<Book, Author> author(
            List<Book> books,
            @ContextValue("tenant") String tenant) {

        Set<String> ids = books.stream()
                .map(Book::authorId)
                .collect(Collectors.toSet());

        Map<String, Author> byId =
                authorService.findByIds(ids, tenant);

        Map<Book, Author> result = new HashMap<>();
        for (Book book : books) {
            result.put(book, byId.get(book.authorId()));
        }
        return result;
    }
}
```

**Đây là biến thể minh họa, không phải file thêm vào project chính**. Nếu dùng nó thay cho DataLoader explicit, cần import `Controller`, `BatchMapping`, `ContextValue`, `List`, `Map`, `Set`, `Collectors` và `HashMap`. Đừng đăng ký cả `@BatchMapping(Book.author)` và `@SchemaMapping(Book.author)` đồng thời trong cùng một ứng dụng, vì chúng cùng nhận trách nhiệm cho một GraphQL field.

`@BatchMapping` tự xây một mapped batch loader và field data fetcher, giúp bỏ boilerplate `BatchLoaderRegistry`/`DataLoader.load` trong nhiều trường hợp. Có thể khai báo `@ContextValue` trực tiếp trên batch method. Nó thích hợp khi mỗi field chỉ cần gom parent objects và lấy related entities. Nếu cần keyContexts, cache configuration riêng, loader name custom, selection set phức tạp hoặc policy nâng cao, `BatchLoaderRegistry` có thể linh hoạt hơn.

### 8.3. Khi nào dùng ordered loader thay mapped loader?

Một batch service có thể trả `List<Author>` cho `List<String> keys`. Khi đó thứ tự trả về **phải khớp thứ tự keys**; một bản ghi không tồn tại cần vị trí null tương ứng. Với mapped batch loader `Set<K> → Map<K,V>`, dữ liệu được ghép theo key nên thường an toàn hơn khi backend không bảo đảm order.

Trong test của ordered loader, **đừng chỉ** assert `list.size()==n`. Hãy cố ý trả kết quả backend theo thứ tự khác và xác nhận adaptation/lookup đúng hợp đồng. Với mapped loader, test ba books ở phần 6 kiểm tra sự ghép chính xác qua `author.id`/`displayName`.

### 8.4. Test một loader trực tiếp khi không muốn chạy GraphQL document

Spring for GraphQL còn cho phép đăng ký `DefaultBatchLoaderRegistry` vào một `DataLoaderRegistry` test, rồi lấy loader theo tên để gọi `load(...)` và `dispatchAndJoin()`. Mẫu quy trình:

```text
DefaultBatchLoaderRegistry registry
   │
   ├── forTypePair(...).registerMappedBatchLoader(...)
   │
   └── registerDataLoaders(dataLoaderRegistry, graphQLContext)
              │
              ▼
DataLoader<String, Author> loader
   │
   ├── load("a-1")
   ├── load("a-2")
   └── dispatchAndJoin()
              │
              ▼
Verify returned list/futures + authorService batch arguments
```

Đây là sơ đồ minh họa API, không phải chương trình Java độc lập. Nó phù hợp khi cần kiểm tra **batch loader function**, cache, result mapping và batch errors tách khỏi SDL/field resolver.

**Nhưng:** một unit test loader pass chưa chứng minh GraphQL controller thực sự inject đúng loader name/type. Giữ một integration test qua `GraphQlTester` để xác nhận registration và field mapping.

### 8.5. Batch key phải mang đủ thông tin trong cùng request

Không chỉ cross-request leakage mới nguy hiểm. Ngay trong **một** GraphQL request, nếu cùng `authorId` được load dưới hai quyền/view khác nhau, DataLoader cache chỉ theo `authorId` có thể trả nhầm kết quả. Khi context phụ thuộc từng parent/field, cân nhắc:

- Dùng composite key `(tenantId,authorId,visibility)` và stable equality/hashCode.
- Dùng per-key context với `DataLoader.load(key, keyContext)` khi cần, nhưng **nhớ rằng keyContext không tự trở thành một phần của cache key**.
- Phân vùng loaders theo từng policy phù hợp hoặc tắt cache có chủ ý khi không thể có key an toàn.
- Không dùng per-request context chung như một giấy phép trả tất cả dữ liệu; service vẫn phải kiểm tra permissions theo resource.

## 9. GraphQL context: global context khác local context

### 9.1. `GraphQLContext`

`GraphQLContext` là context của một execution, được đọc bởi data fetchers và batch loaders. `@ContextValue("tenant")` lấy key trong context đó. Một `WebGraphQlInterceptor` có thể đưa thuộc tính vào `ExecutionInput` bằng `configureExecutionInput`.

Ví dụ ở project:

```java
request.configureExecutionInput(
        (executionInput, builder) ->
                builder.graphQLContext(context ->
                        context.put("tenant", tenant))
                        .build());
```

Trong test không có transport:

```java
ExecutionGraphQlServiceTester.builder(executionService)
        .configureExecutionInput((input, builder) ->
                builder.graphQLContext(context ->
                        context.put("tenant", "team-a"))
                        .build())
        .build();
```

**Không dùng `ThreadLocal` làm nguồn duy nhất của tenant** nếu resolvers, DataLoaders hoặc security checks có thể chuyển thread.

### 9.2. Local context

GraphQL Java có `localContext` gắn với một nhánh/field thay vì toàn request. Spring for GraphQL có `@LocalContextValue` để lấy thông tin của parent field khi dùng controller methods phù hợp.

Khi một query có nhiều nhánh cần quyền/locale khác nhau, không nên đẩy tất cả dữ liệu nhánh đó vào một key global rồi ghi đè liên tục. Hãy đọc tài liệu `DataFetchingEnvironment`, local context và per-key context. Test phải dùng document có **hai sibling branches** để bắt lỗi trộn context, không chỉ một query một field.

**Lưu ý:** local context không phải cơ chế authentication tự động. Nó chỉ là vật chứa dữ liệu, cần được khởi tạo từ nguồn được tin cậy.

### 9.3. Context trên HTTP khác trên WebSocket/subscription

HTTP GraphQL request thường có các header/cookies gắn với một HTTP exchange. WebSocket GraphQL subscriptions tồn tại lâu hơn; có handshake và `connection_init` payload, nhiều operations multiplexed trên một connection. Cơ chế truyền authentication context và vòng đời refresh/revoke có thể khác. Test qua `WebGraphQlInterceptor`/HTTP không đủ để khẳng định WebSocket auth đúng.

Nếu application có subscription, dùng `WebSocketGraphQlTester` và test cả connect/auth/subscribe/stop/cancellation theo contract, không đoán rằng `HttpGraphQlTester` sẽ kiểm tra subscription qua HTTP giống query thường.

## 10. GraphQL errors không giống HTTP status codes

GraphQL response thường có hình dạng:

```json
{
  "data": {
    "books": [
      {
        "id": "b-1",
        "author": null
      }
    ]
  },
  "errors": [
    {
      "message": "Access denied",
      "path": ["books", 0, "author"]
    }
  ]
}
```

Đây là **minh họa** về partial data/error response. Error text, classification, path và HTTP status thật phụ thuộc GraphQL schema, handler, Spring GraphQL version và error resolver; không khẳng định một lỗi permission phải cho đúng response này.

**Những quy tắc QA:**

- GraphQL field error có thể để lại dữ liệu khác trong `data`; đừng assert HTTP 500 là điều kiện duy nhất của lỗi.
- Với non-null field (`!`), lỗi/null có thể propagate lên parent và làm null toàn bộ một phần graph.
- `GraphQlTester` theo mặc định kiểm tra errors không mong đợi; khi test happy path, không được filter/suppress hết errors.
- Khi test lỗi có chủ đích, dùng `errors().expect(...)` hoặc `errors().satisfy(...)`; phân biệt “đã có lỗi đúng loại” và “bỏ qua lỗi để tiếp tục đọc data”.
- Không để exception raw từ JDBC/token/stack trace lộ qua GraphQL error message trong production; xây `DataFetcherExceptionResolver`/`@GraphQlExceptionHandler` phù hợp.
- Kiểm tra GraphQL error path/classification khi chúng thuộc contract; không khóa vào câu chữ nội bộ của framework không được cam kết ổn định.

**Lưu ý trong test thiếu context ở phần 6:** chúng ta assert có errors và service không bị gọi, không assert chính xác message do phiên bản framework có thể khác. Khi triển khai chính sách 401/403 qua HTTP, nên test riêng ở Spring Security/transport layer.

## 11. Những dạng test nên có trong dự án thật

| Test case | Công cụ | Assertion cốt lõi |
| --- | --- | --- |
| Root query gọi business service | `@GraphQlTest + @MockitoBean` | Đúng arguments và data path |
| Field resolver trả nested entity | `GraphQlTester` | Mỗi parent nối đúng child key/value |
| N+1/batching | Registry thật, service mock | Batch calls/keys đúng cho query shape |
| Cache reuse cùng key trong một request | GraphQL document có duplicate author ids | Không gọi downstream lặp vô ích; đúng output |
| Cache isolation giữa hai requests | Hai executions có context khác | Không dùng lại value giữa tenant A và B |
| Context missing/malformed | Execution tester/transport tester | Error, không fallback tenant khác |
| Root field không chọn child | GraphQL selection set đơn giản | Không gọi AuthorService |
| Authorization theo principal/resource | Security + service policy | User không được xem dữ liệu tenant khác |
| Loader trả map thiếu key | GraphQL response + nullable contract | Null/error đúng schema |
| Batch service lỗi | GraphQlTester errors | Không leak nội dung nhạy cảm; partial data/nullability đúng |
| Selection set lớn/complexity | Integration/performance test | Guard max depth/complexity, latency, batch sizing |
| HTTP header → context | `HttpGraphQlTester` | Interceptor đã chạy, tenant/trace id được truyền |
| DataLoader keyContexts/localContext | Tình huống hai sibling branches | Không trộn quyền hoặc filters |
| SOAP endpoint trong cùng module | Spring-WS `MockWebServiceClient` | XML/SOAP payload, namespace, fault contract |

### 11.1. Kiểm tra đúng behavior thay vì chỉ đếm calls

`verify(authorService, times(1)).findByIds(...)` hữu ích khi kiểm tra batch performance, nhưng **không đủ** nếu map trả sai hoặc tenant không đúng. Vì vậy kết hợp:

- Test response `books[0].author.id` và `books[1].author.id`/`displayName`.
- Verify exact keys (distinct IDs) và tenant/context.
- Assert không gọi author service nếu field không được chọn.
- Test hai requests có cùng author key nhưng khác tenant.
- Test negative cases (missing context, missing author, service error).

Tập assertion này xác nhận cả **đúng dữ liệu** lẫn **đúng cách lấy dữ liệu** trong phạm vi query được test.

## 12. Lỗi thường gặp và cách khắc phục

### Lỗi 1. `@GraphQlTest` không tạo `BookService`

**Nguyên nhân:** Đây là GraphQL slice, không tự scan mọi `@Service`. **Sửa:** khai báo `@MockitoBean BookService` hoặc import bean/config cần thiết một cách chủ đích. Đừng bật `@SpringBootTest` chỉ để chữa một collaborator thiếu.

### Lỗi 2. Có loader bean nhưng test báo thiếu DataLoader

**Nguyên nhân:** Bạn import `BookGraphQlController` nhưng không import cấu hình đã đăng ký `BatchLoaderRegistry`, hoặc loader được đặt tên khác. **Sửa:** `@Import(AuthorLoaderConfiguration.class)`; xem loader name/type `Author.class.getName()` và generic `DataLoader<String,Author>`.

### Lỗi 3. Tạo một DataLoader singleton rồi dùng cho mọi request

**Hệ quả:** cache cross-request có thể lộ dữ liệu, đặc biệt nếu cùng ID được nhìn qua tenant/permission khác. **Sửa:** đăng ký loader factory qua `BatchLoaderRegistry` để có lifecycle request phù hợp; không giữ DataLoader instance global.

### Lỗi 4. Resolver gọi `join()`/`block()` ngay sau `load`

**Hệ quả:** chặn trước dispatch, tiềm ẩn deadlock, mất batching và blocking thread. **Sửa:** trả `CompletableFuture`/reactive type cho GraphQL engine; không block trong data fetcher khi có thể tránh.

### Lỗi 5. Batch trả kết quả theo thứ tự database cho ordered loader

**Hệ quả:** `a-1` có thể nhận dữ liệu `a-2`. **Sửa:** ordered loader phải trả list theo thứ tự keys; mapped loader trả Map keyed by ID. Test field data cụ thể chứ không chỉ count.

### Lỗi 6. Dùng `@ContextValue` nhưng không cấp context cho execution-direct test

**Hệ quả:** GraphQL error dù Spring Boot beans đã nạp đúng. **Sửa:** `ExecutionGraphQlServiceTester.builder(...).configureExecutionInput(...)`. Không nhầm cơ chế tự thêm context của WebGraphQlInterceptor vì direct tester **không** chạy qua interceptor.

### Lỗi 7. Test slice pass, production HTTP vẫn không nhận context

**Hệ quả:** `@QueryMapping` lỗi missing context khi chạy HTTP thật. **Sửa:** có thêm `HttpGraphQlTester`/transport test với `WebGraphQlInterceptor` và auth thật. Slice chứng minh resolver hiểu context, không chứng minh header/token propagation.

### Lỗi 8. Dùng request header như quyền truy cập tenant

**Hệ quả:** User tự đặt header để đọc dữ liệu tenant khác. **Sửa:** authenticated identity, verified membership và service-level authorization. Header `X-Demo-Tenant` của ví dụ chỉ dành cho mô phỏng.

### Lỗi 9. Chỉ kiểm tra GraphQL JSON data mà bỏ qua errors

**Hệ quả:** Response có partial data + errors nhưng test vẫn đọc một field và tưởng hợp đồng thành công. **Sửa:** để `GraphQlTester` fail trên unexpected errors; chỉ `filter/expect/satisfy` khi lỗi được dự liệu và có assertion rõ.

### Lỗi 10. Mapped loader trả thiếu author nhưng schema khai báo `Author!`

**Hệ quả:** Nullability propagation làm `Book`/`books` null rộng hơn dự kiến. **Sửa:** xác định “author bắt buộc?” là contract; test missing key và error path. Không mặc định mọi related object tồn tại.

### Lỗi 11. Test chậm/N+1 dù có DataLoader

**Nguyên nhân:** Loader dispatch theo nhiều execution levels, maxBatchSize nhỏ, cache bị tắt, custom scheduler hoặc service chia nhiều DB calls. **Sửa:** kiểm tra traces/observations, captured SQL queries, batch sizes, keys và query shape; không chỉ nhìn thấy class DataLoader rồi coi N+1 được xử lý.

### Lỗi 12. Dùng alias/fragment làm cache sai

**Nguyên nhân:** Một key cache chỉ mang entity ID nhưng output khác theo field arguments, filter, locale hay auth visibility. **Sửa:** đưa dimensions ảnh hưởng result vào composite key hoặc thiết kế loader tách phạm vi phù hợp; test hai branches có cùng ID với context/arguments khác nhau.

### Lỗi 13. Mocks trả null ngoài dự kiến

**Nguyên nhân:** Mockito chưa stub đúng `Set` keys/tenant, hoặc custom code gọi service bằng argument khác. **Sửa:** capture arguments/logical IDs, stub theo contract, assert errors và expected paths. Không dùng `any()` quá rộng khi cần bảo vệ tenant/key correctness.

### Lỗi 14. Autoconfigure HTTP tester nhưng thiếu WebFlux test client

**Nguyên nhân:** `HttpGraphQlTester` sử dụng `WebTestClient`, MVC project thường cần `spring-boot-starter-webflux` ở test scope. **Sửa:** thêm dependencies theo tài liệu Spring Boot 3.5, kiểm tra test context. Không bật production WebFlux server chỉ để có client.

### Lỗi 15. Thử test SOAP bằng `GraphQlTester`

**Nguyên nhân:** Nhầm hai cơ chế đều gọi là “resolver/endpoint”. SOAP dùng XML envelope, WSDL/XSD, `@Endpoint`, payload mapping, faults. **Sửa:** dùng Spring Web Services test `MockWebServiceClient` và XML/XPath assertions cho SOAP, giữ `GraphQlTester` cho GraphQL document/data/errors.

## 13. So sánh nhanh với SOAP ở cùng nhóm kiến thức

Nhóm cha của bài là “GraphQL và SOAP”, nhưng đề bài “resolver phụ thuộc service, DataLoader và ngữ cảnh” thuộc **GraphQL**. Để không dùng sai công cụ:

| Khía cạnh | GraphQL | SOAP/Spring-WS |
| --- | --- | --- |
| Mô tả giao diện | GraphQL SDL (`.graphqls`) | WSDL/XSD |
| Đơn vị thực thi | `@QueryMapping`, `@SchemaMapping`, field resolvers | `@Endpoint`, `@PayloadRoot`, `@RequestPayload` |
| Tải dữ liệu liên quan | `DataLoader`, `@BatchMapping` | Service calls theo SOAP operation; không có DataLoader mặc định theo GraphQL |
| Context | `GraphQLContext`, `@ContextValue`, Spring Security | SOAP headers, MessageContext, WS-Security/principal |
| Test trực tiếp | `GraphQlTester`, `ExecutionGraphQlServiceTester` | `MockWebServiceClient` |
| Lỗi | `errors` trong GraphQL response, có thể partial data | SOAP Fault trong SOAP Envelope |
| N+1 | Một query nested có thể kích nhiều resolvers | Tùy cách thiết kế service/operations, không đồng nhất GraphQL field execution |

Nếu hệ thống thật có cả SOAP và GraphQL, kiểm tra adapter chuyển đổi giữa chúng ở **service boundary**: GraphQL resolver gọi SOAP client giả bằng mock HTTP/SOAP server; chỉ khi kiểm tra SOAP XML contract mới dùng Spring-WS testing. Không trộn WSDL/SDL vào một bộ assertion không đúng protocol.

## 14. Mở rộng: exception, performance, security và concurrency

### 14.1. Lỗi batch service và partial data

Giả sử `AuthorService` thất bại do timeout. Có thể chọn:

- Đổi thành GraphQL error tại path `books[*].author`; nếu field nullable, giữ được các field books khác.
- Có fallback/cached author theo policy nhưng phải bộc lộ trạng thái nếu business contract yêu cầu.
- Fail cả query khi dữ liệu author bắt buộc và schema/contract yêu cầu.

**Test phải cố định policy.** Đừng viết `errors().filter(error -> true)` trên mọi query; nó che mất regression. Có thể dùng `@GraphQlExceptionHandler` hoặc `DataFetcherExceptionResolver` để mã hóa errors đúng classification, bỏ stack trace/secret.

### 14.2. Query complexity và resource budgeting

N+1 là một mặt của GraphQL denial-of-service risk. Nested query sâu, aliases nhiều và list pagination không giới hạn có thể tạo quá nhiều load keys, CPU hoặc memory. Về production nên:

- Giới hạn depth/complexity, pagination size, total requested nodes.
- Cấu hình DataLoader maxBatchSize nếu service/backend có limit.
- Đặt timeout và circuit breaker ở downstream boundary.
- Theo dõi batch count/size và latency bằng Micrometer Observations, traces hoặc structured logs.
- Phân biệt request-bound cache với distributed cache.
- Test một số queries lớn có giới hạn bằng performance/integration tests; không biến test unit thành benchmark dựa CPU time quá nhạy.

### 14.3. Security phải đi qua lớp service

Một GraphQL resolver có thể dùng `@PreAuthorize`, principal hoặc authenticated context, nhưng field-level authorization đặc biệt quan trọng khi một query có nhiều nested objects. **Không cho rằng root query đã được phép thì mọi nested field đều được phép**. AuthorService phải kiểm tra những author IDs caller được xem, hoặc resolver phải áp dụng policy phù hợp.

Khi test denial:

- Identity A có thể xem book b-1, nhưng không xem author a-2.
- GraphQL response phải trả null/redacted/error đúng policy, không lộ displayName.
- DataLoader batch vẫn cần giữ key/result association đúng khi một số IDs bị từ chối.
- Query lặp cùng key dưới hai quyền/view trong một request phải tránh cache contamination.

### 14.4. ThreadLocal/Reactor Context khác GraphQLContext

Ở Web MVC, security context có thể bắt đầu bằng ThreadLocal trong request thread nhưng GraphQL execution/async loader chuyển threads. Spring for GraphQL có context propagation support, nhưng custom executors/SDK không phải lúc nào cũng tự giữ mọi context. Trong WebFlux, Reactor Context khác với GraphQLContext nhưng có thể được tích hợp/propagate.

**Đừng** lấy một static `RequestContextHolder` trong batch loader ở thread khác rồi mặc định luôn có tenant. Hãy dùng contract context đã chọn, identity/authorization phù hợp và test qua asynchronous boundary nếu đó là tính năng của ứng dụng thật.

### 14.5. Quan sát đúng một request trong cùng lúc

Hai HTTP requests có thể thực thi đồng thời, mỗi request có DataLoaderRegistry/cache riêng. Nếu service thật dùng shared mutable map không thread-safe, lỗi ở service có thể bị quy nhầm cho DataLoader. Test concurrency nên dùng latches/coordination cụ thể, không lạm dụng `Thread.sleep`; kiểm tra hai users/tenants trả đúng và không phụ thuộc thứ tự hoàn tất.

Mỗi `GraphQlTester`/HTTP tester là một test client; dùng `mutate()` để thay headers có thể tạo một client khác. Điều này **không** thay thế authentication thực hoặc bảo đảm isolation của backend caches; phải kiểm tra quyền tại đúng lớp.

## 15. Checklist QA cho một resolver có DataLoader

- [ ] GraphQL SDL mô tả đúng root field, nested field, nullability và types.
- [ ] `@QueryMapping` lấy đúng argument/context và gọi đúng service.
- [ ] `@SchemaMapping` nhận đúng parent object và tải đúng key.
- [ ] `DataLoader` được đăng ký qua `BatchLoaderRegistry` và có tên/type khớp resolver.
- [ ] Trong slice, `@Import` loader configuration nếu nó nằm ngoài bean scan; service mock nhưng loader thật.
- [ ] Query test dùng nhiều parent và duplicate child keys để kiểm tra batching/caching.
- [ ] Assertion bảo vệ đúng child id/value theo từng parent, không chỉ số phần tử.
- [ ] Verify batch key set và context; không chỉ `times(1)`.
- [ ] Query không chọn child thì không gọi downstream service của child.
- [ ] Hai GraphQL executions với cùng key và tenant khác phải cho kết quả phân tách.
- [ ] Missing context không fallback sang tenant mặc định ngoài ý muốn.
- [ ] HTTP test xác minh interceptor đưa trusted request metadata vào context.
- [ ] Không tin header giả làm authorization production.
- [ ] DataLoader cache không là singleton/global hoặc thiếu chiều visibility trong key.
- [ ] Có test missing author, service failure, nullability/error path khi business cần.
- [ ] Không leak production secret, token hoặc PII trong GraphQL errors/log/test fixture.
- [ ] Nếu test HTTP socket thật, chọn `RANDOM_PORT` và tách test resources/profiles.
- [ ] Nếu backend là SOAP, dùng công cụ SOAP-specific cho XML/WSDL/faults.

## 16. Câu hỏi tự kiểm tra

**Câu 1.** Test gọi trực tiếp `BookGraphQlController.author(book, mockDataLoader)` đã chứng minh N+1 được giải quyết chưa?

**Đáp án:** Chưa. Nó có thể chỉ chứng minh resolver gọi `load(key)`. Cần chạy GraphQL execution với loader thật và nhiều books, rồi assert batch keys/calls và JSON output.

**Câu 2.** `@GraphQlTest` có tự tạo `BookService` thật không?

**Đáp án:** Không theo mặc định với một service thông thường nằm ngoài slice. Dùng `@MockitoBean` hoặc import collaborator rõ ràng.

**Câu 3.** Vì sao test cần `@Import(AuthorLoaderConfiguration.class)`?

**Đáp án:** Cấu hình loader là `@Configuration` ngoài tập component scan mặc định của một GraphQL slice; muốn kiểm tra DataLoader thật thì phải bảo đảm nó được nạp.

**Câu 4.** Test có 3 books với author IDs `a-1,a-2,a-1`. Có bao nhiêu key độc nhất?

**Đáp án:** Hai: `a-1` và `a-2`. Với DataLoader cache và batching theo scenario này, downstream batch thường nhận một tập hai key.

**Câu 5.** Vì sao `GraphQlTester.path("books[0].author.id")` không cần `data.`?

**Đáp án:** GraphQlTester path mặc định tương đối với `data` section trong GraphQL response.

**Câu 6.** Một `ExecutionGraphQlServiceTester` có chạy `WebGraphQlInterceptor` không?

**Đáp án:** Không. Nó chạy execution service trực tiếp, bỏ qua transport handler/interceptor. Để test interceptor, dùng `WebGraphQlTester`/`HttpGraphQlTester` qua handler phù hợp.

**Câu 7.** Có nên đưa raw `X-Tenant` client header thẳng vào service rồi coi đã authorization?

**Đáp án:** Không. Cần identity đáng tin, policy kiểm tra quyền trên tenant/resource và test denial cases.

**Câu 8.** Nếu `author` nullable trong SDL, batch loader không tìm được một key thì toàn list `books` luôn phải null?

**Đáp án:** Không. Field `Author` nullable có thể được trả null cho parent tương ứng. Nếu schema là non-null, GraphQL null propagation mới có thể lan lên parent/list theo cấu trúc `!`.

**Câu 9.** DataLoader name dựa trên `Author.class.getName()` khác `BookService` như thế nào?

**Đáp án:** DataLoader là lookup/caching/batching facility cho field author; BookService cung cấp root books. Tên/type loader phải khớp value type mà resolver yêu cầu.

**Câu 10.** Vì sao test SOAP không dùng `GraphQlTester` dù cùng một module chủ đề?

**Đáp án:** SOAP có XML Envelope/WSDL/WS-Security/SOAP Fault, test bằng Spring-WS `MockWebServiceClient`; GraphQlTester thực thi GraphQL documents theo SDL.

## 17. Tài liệu chính thức

- [Spring Boot 3.5 – Auto-configured Spring GraphQL Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.autoconfigured-graphql-tests): `@GraphQlTest`, Mockito bean, `GraphQlTester`, transport vs direct execution.
- [Spring for GraphQL – Annotated Controllers](https://docs.spring.io/spring-graphql/reference/controllers.html): `@QueryMapping`, `@SchemaMapping`, `@BatchMapping`, `@ContextValue`, `DataLoader` arguments.
- [Spring for GraphQL – Request Execution & Batch Loading](https://docs.spring.io/spring-graphql/reference/request-execution.html): `BatchLoaderRegistry`, per-request registry, context propagation, DataLoader batch tests.
- [Spring for GraphQL – Testing](https://docs.spring.io/spring-graphql/reference/testing.html): `GraphQlTester` variants, `ExecutionGraphQlServiceTester`, HTTP tester, errors/path assertions.
- [Spring for GraphQL – Server Transports and Interceptors](https://docs.spring.io/spring-graphql/reference/transports.html): `WebGraphQlInterceptor`, `ExecutionInput` context.
- [GraphQL Java – DataLoader/Batching](https://graphql-java.com/documentation/batching/): dispatch, batching, per-request caching, key contexts.
- [Spring Web Services – Testing](https://docs.spring.io/spring-ws/docs/current/reference/html/#testing): `MockWebServiceClient` cho SOAP endpoints (không áp dụng cho GraphQL).

**Kết luận:** Một resolver đúng không chỉ trả đúng JSON. Khi phụ thuộc service, DataLoader và context, bộ test nên chứng minh **cả dữ liệu từng field, các key batch, số lần downstream gọi trong một query cụ thể, và cô lập context giữa requests**. Dùng `@GraphQlTest` + mock service + loader registration thật cho resolver logic; dùng `HttpGraphQlTester` khi cần bảo vệ đường HTTP/interceptor/context; dùng service/security integration tests để chứng minh authorization và data isolation thực.