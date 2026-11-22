# `ExecutionGraphQlServiceTester` so với kiểm thử GraphQL qua HTTP

Trong Spring Boot, một truy vấn GraphQL có thể được kiểm thử ở **nhiều ranh giới khác nhau**. Ta có thể gọi trực tiếp bộ thực thi GraphQL trong Spring, hoặc gửi một **HTTP POST /graphql** để kiểm đường web. Hai cách đều có thể sử dụng cú pháp `GraphQlTester.document(...).execute().path(...)`, nhưng **một test PASS không chứng minh cùng một điều**.

- **`ExecutionGraphQlServiceTester`** chạy qua **`ExecutionGraphQlService`**, không cần HTTP client, router, Servlet/Netty server, HTTP headers hoặc socket. Phù hợp để kiểm GraphQL schema, field mapping, `@QueryMapping`/`@MutationMapping`, argument binding, `DataFetcher` và dữ liệu/lỗi do GraphQL execution trả về.
- **`HttpGraphQlTester`** sử dụng **`WebTestClient`** để gửi request ở lớp **HTTP**. Tuy nhiên `WebTestClient` có thể được bind **vào mock web context không dùng socket** hoặc **vào server thật**. Vì vậy, có `HttpGraphQlTester` trong test chưa đủ để khẳng định đã test network.
- **`WebGraphQlTester`** là bước trung gian: chạy qua **`WebGraphQlHandler` và chuỗi `WebGraphQlInterceptor`** với thông tin transport mô phỏng, nhưng **không cần HTTP client/server thật**.

Bài này giải thích lựa chọn theo mục tiêu, cấu hình `@GraphQlTest`/ `@SpringBootTest`, khác biệt giữa **HTTP status** và **GraphQL errors**, cùng dự án mẫu **Java 17 + Spring Boot 3.5 + JUnit Jupiter**, gồm cả unit-of-GraphQL execution, HTTP mock và HTTP server thật.

## 1. Kiến trúc Spring GraphQL: các tầng đi qua

```text
GraphQL document: query { greeting(name: "Mai") }
      |
      +--- ExecutionGraphQlServiceTester --------------------+
      |                                                       |
      |     (không client, không HTTP, không socket)           |
      |                                                       v
      |                                            ExecutionGraphQlService
      |                                                       |
      +--- WebGraphQlTester --> WebGraphQlHandler ------------+
      |                        + WebGraphQlInterceptor         |
      |                                                       |
      +--- HttpGraphQlTester --> WebTestClient --> HTTP ------+
                               |                  |           |
                               |                  +-- mock ---+
                               |                  |           |
                               |                  +-- server TCP
                               |
                               +-- request encoding, status,
                                   headers, transport route
                                                       |
                                                       v
                                             GraphQlSource / GraphQL Java
                                                       |
                                                       v
                                           Schema, @QueryMapping, DataFetcher
                                                       |
                                                       v
                                             ExecutionResult (data/errors)
```

Sơ đồ thể hiện **ranh giới** chứ không phải mọi đối tượng Spring phải đi qua đúng một thứ tự của hình. Ở server thật, HTTP request thường được tiếp nhận bởi Spring MVC hoặc WebFlux transport, rồi chuyển tới `WebGraphQlHandler` và `ExecutionGraphQlService`; ở test trực tiếp, đường transport bị bỏ qua.

**`ExecutionGraphQlService`** là abstraction của Spring GraphQL cho việc thực thi GraphQL Java. `DefaultExecutionGraphQlService` dùng một `GraphQlSource` để truy cập GraphQL schema và runtime wiring. Test ở lớp này vẫn có thể phát hiện lỗi schema, resolver/argument mapping và exception resolution — nó **không phải** unit test thuần gọi một method Java bằng `new` rồi assert string.

### Cùng API assertion, khác đối tượng được kiểm

```java
tester.document("""
        query Greeting($who: String!) {
            greeting(name: $who)
        }
        """)
    .variable("who", "Mai")
    .execute()
    .path("greeting")
    .entity(String.class)
    .isEqualTo("Xin chào, Mai!");
```

Đây là **snippet dùng trong test class** đã có biến `tester` với kiểu `GraphQlTester` hoặc subtype phù hợp; file runnable ở phần 6. Điểm quan trọng: phương thức `document`, `variable`, `execute`, `path`, `entity` **không tiết lộ test có dùng HTTP hay không**. Cần xem tester được **tạo/bind** như thế nào.

## 2. Ma trận so sánh để chọn đúng cấp kiểm thử

| Mục tiêu / thuộc tính | `ExecutionGraphQlServiceTester` | `WebGraphQlTester` | `HttpGraphQlTester` bind mock | `HttpGraphQlTester` bind server thật |
|---|---|---|---|---|
| Thực thi GraphQL schema, field và resolver | **Có** | **Có** | **Có** | **Có** |
| `@QueryMapping`, arguments, query variables | Có, nếu context có controller và wiring | Có, nếu context có controller và wiring | Có | Có |
| `GraphQL data/errors` | **Có** | **Có** | **Có** | **Có** |
| Chuỗi `WebGraphQlInterceptor` | **Không tự đi qua** | **Có** | Có qua web transport khi cấu hình | Có qua web transport |
| HTTP endpoint `/graphql` được đăng ký | **Không** | **Không** | **Có trong mock HTTP context** | **Có trên server thật** |
| HTTP method, Content-Type, Accept, status, headers | **Không** | Có thể mô phỏng thông tin headers cho interceptor nhưng không kiểm HTTP encoding/status | **Có, ở lớp HTTP mock** | **Có, qua HTTP thật** |
| Servlet/WebFlux filter/security chain | **Không tự kiểm** | **Không tự chạy toàn bộ filter chain** | Có nếu web context/filter được cấu hình | Có nếu server/filter được cấu hình |
| Socket/TCP/embedded server startup | **Không** | **Không** | **Không** | **Có** |
| CORS/preflight browser, TLS/proxy, triển khai production | Không | Không | Chỉ một phần cấu hình HTTP mock | Không đầy đủ nếu chỉ gọi localhost |
| Tốc độ tương đối | Thường nhanh nhất trong nhóm có Spring GraphQL | Không cần server | Không cần server | Chậm hơn vì khởi động/bind server |
| Tình huống sử dụng | GraphQL execution contract | Request context/interceptor | Spring HTTP mapping/encoding, không socket | End-to-end HTTP của app trên loopback |

Đọc bảng đúng cách: mọi ô “Có” chỉ đúng khi **assertion thực sự kiểm điều đó** và context có các bean cấu hình cần thiết. `HttpGraphQlTester` thường tập trung vào **GraphQL payload**, không trực tiếp cho bạn assertion raw HTTP status theo cùng API `GraphQlTester`; muốn kiểm status và header transport chính xác, dùng `WebTestClient` hoặc HTTP client tại cùng boundary.

## 3. `ExecutionGraphQlServiceTester`: tester server-side không cần transport

Spring GraphQL cung cấp factory:

```java
import org.springframework.graphql.execution.ExecutionGraphQlService;
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;

ExecutionGraphQlService executionService = /* bean từ Spring context */ null;
ExecutionGraphQlServiceTester tester =
        ExecutionGraphQlServiceTester.create(executionService);
```

Đoạn trên **minh họa chữ ký API**; không chạy độc lập vì biến `executionService` chưa được lấy từ Spring context. Trong test thật, dùng `@Autowired ExecutionGraphQlService` hoặc nhận bean qua constructor. Cách tạo trên sử dụng **GraphQL server execution** trực tiếp, không cần `WebTestClient`.

Khi cần tùy chỉnh `ExecutionInput`, có thể dùng builder:

```java
ExecutionGraphQlServiceTester customized =
        ExecutionGraphQlServiceTester.builder(executionService)
                .configureExecutionInput((input, builder) ->
                        builder.graphQLContext(java.util.Map.of(
                                "requestSource", "test"))
                                .build())
                .build();
```

Đoạn này là snippet trong test có `executionService` thật; tùy chỉnh `ExecutionInput` có thể hữu ích khi resolver đọc GraphQL context hoặc cần đặt `ExecutionId`. Tuy nhiên **không thay thế kiểm tra HTTP header → GraphQL context**: nếu production dựa vào `WebGraphQlInterceptor` trích `X-Tenant` từ header, test direct không chứng minh bước trích header ấy chạy.

**Khi phù hợp:**

- Kiểm schema SDL, type/field, argument, data fetcher, resolver.
- Kiểm logic GraphQL query/mutation, field projection, nullability, validation error và mapped exceptions.
- Test `DataLoader`/resolver integration **nếu** chúng được cấu hình thực sự trong test context.
- Tách lỗi GraphQL execution khỏi web transport khi debug.
- Phát hiện lỗi nhanh trên PR trước khi chạy các bài HTTP integration nặng hơn.

**Không dùng nó để tuyên bố:** `POST /graphql` được route đúng, content-type JSON được chấp nhận, authorization filter đang hoạt động, CORS preflight được phép, cổng HTTP mở hoặc client từ ngoài mạng có thể truy cập.

## 4. `@GraphQlTest` tạo tester và scope như thế nào?

Với **Spring Boot 3.5**, `@GraphQlTest` tập trung vào GraphQL execution, không cần HTTP transport. Nó nạp các loại bean Spring GraphQL quan trọng: `@Controller`, `@ControllerAdvice`, `RuntimeWiringConfigurer`, `DataFetcherExceptionResolver`, `GraphQlSourceBuilderCustomizer`, `Instrumentation` và một số component conversion/JSON liên quan.

```java
@GraphQlTest(GreetingGraphQlController.class)
class GreetingGraphQlSliceTest {
    @Autowired
    GraphQlTester graphQlTester;
}
```

Đây là khung cấu hình, ví dụ runnable nằm ở phần 6. `@GraphQlTest` có thể tự cấu hình **`GraphQlTester`** để test ngay. Nếu muốn nhấn mạnh tầng execution, có thể autowire `ExecutionGraphQlService` và tạo **`ExecutionGraphQlServiceTester`** theo factory như bài thực hành.

**Slice cố tình không tự quét** `@Service`, `@Repository` và nhiều `@Component` bình thường. Khi controller cần `GreetingService`, trong slice có thể dùng `@MockitoBean` trên test field để cấp collaborator. `@MockitoBean` đến từ **Spring Framework 6.2+**; Spring Boot 3.5 tương thích. Với test chỉ cần kiểm GraphQL mapping/response, mock service là ranh giới đúng; nếu muốn chứng minh service thật tích hợp với repository, dùng `@SpringBootTest` hoặc test nhiều tầng thích hợp.

Nếu schema không tìm được, kiểm file `src/main/resources/graphql/*.graphqls` hoặc `*.gqls` và `spring.graphql.schema.locations`. **Schema là bắt buộc**: annotation `@QueryMapping` trên method không tự tạo SDL field tương ứng. Không nên viết test GraphQl slice chỉ bằng controller class mà quên schema rồi cho rằng framework sẽ suy diễn tất cả fields.

## 5. HTTP GraphQL: cùng tester nhưng hai kiểu transport

### 5.1. Mock HTTP với `@AutoConfigureHttpGraphQlTester`

Với Spring Boot 3.5:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureHttpGraphQlTester
class MockHttpGraphQlTest {
    @Autowired
    HttpGraphQlTester tester;
}
```

Đây là snippet cấu hình, cần imports và `@Test` như file hoàn chỉnh. Dù tester có chữ **Http**, môi trường `MOCK` **không mở port TCP**. Spring Boot cấu hình `HttpGraphQlTester` qua `WebTestClient` phù hợp (MVC mock qua MockMvc bridge, hoặc WebFlux mock), giúp exercise web endpoint routing/serialization mà không cần server thật.

**Bằng chứng:** GraphQL query đi vào GraphQL HTTP endpoint trong **web test context**, có thể bắt lỗi route/configuration ở tầng này. **Chưa chứng minh:** port bind, network, TLS và nhiều điều kiện deploy.

### 5.2. Live HTTP với `@SpringBootTest(RANDOM_PORT)`

Với `RANDOM_PORT`, Spring Boot chạy web server embedded thật trên port ngẫu nhiên. Khi `spring-graphql-test` và HTTP test client dependencies có mặt, Boot có thể **tự cấu hình `HttpGraphQlTester`** cho server này:

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class RealGraphQlHttpTest {
    @Autowired
    HttpGraphQlTester tester;
}
```

Trong trường hợp này `HttpGraphQlTester` gửi HTTP thật qua loopback tới server. Không cần tự đoán `8080`; nếu cần kiểm status/header raw, có thể lấy `@LocalServerPort` và tạo `WebTestClient.bindToServer().baseUrl("http://127.0.0.1:" + port)`.

**Cảnh báo:** việc **inject** được `HttpGraphQlTester` không đủ để tự nhận là real HTTP integration: phải nhìn `@SpringBootTest(webEnvironment=RANDOM_PORT/DEFINED_PORT)` hoặc cách tester được bind. `HttpGraphQlTester.create(WebTestClient.bindToApplicationContext(...))` vẫn là in-process/mock.

### 5.3. Cách xây thủ công không cần Spring Boot autoconfigure

Đây là hai cấu hình **đối lập**:

```java
// WebTestClient mock WebFlux ApplicationContext:
WebTestClient mock = WebTestClient.bindToApplicationContext(context)
        .configureClient()
        .baseUrl("/graphql")
        .build();
HttpGraphQlTester mockTester = HttpGraphQlTester.create(mock);

// WebTestClient thật tới server đã start:
WebTestClient real = WebTestClient.bindToServer()
        .baseUrl("http://127.0.0.1:" + port + "/graphql")
        .build();
HttpGraphQlTester realTester = HttpGraphQlTester.create(real);
```

Các snippet này giả định có `context` (Reactive `WebApplicationContext`) hoặc `port` server thật. Với Servlet MVC mock, dùng **`MockMvcWebTestClient.bindToApplicationContext(...)`** thay vì binding WebFlux application context. Cùng `HttpGraphQlTester.create(...)`, nhưng test boundary khác nhau hoàn toàn.

## 6. Ví dụ hoàn chỉnh Java 17 + Spring Boot 3.5 + GraphQL

Ứng dụng expose một GraphQL field:

```graphql
type Query {
    greeting(name: String!): String!
}
```

Query hợp lệ:

```graphql
query Greeting($who: String!) {
    greeting(name: $who)
}
```

Với `who = "Mai"`, expected GraphQL data là `{"greeting":"Xin chào, Mai!"}`. Ta viết ba nhóm test để phân biệt:

1. **GraphQL execution slice** — `@GraphQlTest` + `ExecutionGraphQlServiceTester`, mock collaborator.
2. **HTTP mock transport** — `@SpringBootTest(MOCK)` + `@AutoConfigureHttpGraphQlTester`, service thật, không socket.
3. **HTTP server thật** — `@SpringBootTest(RANDOM_PORT)` + `HttpGraphQlTester`; dùng `WebTestClient` trực tiếp để assert **HTTP status, header và JSON envelope**.

Không có database, authentication hoặc external API. Điều này giúp tách bản chất tester khỏi những phụ thuộc ngoài phạm vi.

### 6.1. Cây thư mục

```text
graphql-test-levels/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/graphql/
    │   │   ├── GraphQlDemoApplication.java
    │   │   ├── GreetingService.java
    │   │   └── GreetingGraphQlController.java
    │   └── resources/graphql/
    │       └── schema.graphqls
    └── test/java/com/example/graphql/
        ├── GreetingExecutionTest.java
        ├── GreetingMockHttpTest.java
        └── GreetingRealHttpTest.java
```

### 6.2. `pom.xml`: hai transport scopes khác nhau

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>graphql-test-levels</artifactId>
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

**Vì sao có `spring-boot-starter-webflux` trong scope test?** Trong ứng dụng runtime này ta chọn **Spring MVC** với `spring-boot-starter-web`, còn `WebTestClient` của HTTP GraphQL test phụ thuộc thư viện reactive client/test; Spring Boot 3.5 hướng dẫn thêm WebFlux test dependency nếu chưa có. Đặt nó ở **test scope** để không biến cả ứng dụng production sang WebFlux; khi cả MVC/WebFlux cùng có trên classpath, Boot thông thường vẫn ưu tiên Servlet MVC.

`spring-graphql-test` cung cấp `ExecutionGraphQlServiceTester` và `HttpGraphQlTester`; `spring-boot-starter-test` cung cấp JUnit Jupiter và Mockito. Spring Boot BOM quản lý các version đồng bộ; không tự pin một bản GraphQL Java hoặc Spring Test khác dòng khi chưa có nhu cầu và bằng chứng tương thích.

### 6.3. Khai báo schema GraphQL

File **`src/main/resources/graphql/schema.graphqls`**:

```graphql
type Query {
    greeting(name: String!): String!
}
```

Spring Boot tự tìm `*.graphqls`/`*.gqls` trong `classpath:graphql/**/` (cấu hình mặc định). `String!` sau `name` nghĩa argument bắt buộc không null. `String!` sau field nghĩa kết quả non-null; nếu resolver trả null/throw mà không được xử lý thành giá trị, GraphQL có thể phát lỗi và thực hiện **null propagation** theo schema, khác với HTTP 404/500 thông thường.

### 6.4. Application và service

File **`src/main/java/com/example/graphql/GraphQlDemoApplication.java`**:

```java
package com.example.graphql;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class GraphQlDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(GraphQlDemoApplication.class, args);
    }
}
```

File **`src/main/java/com/example/graphql/GreetingService.java`**:

```java
package com.example.graphql;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
```

Business logic cố ý đơn giản để tập trung vào GraphQL execution/HTTP transport. Nếu service thật truy cập database hoặc remote system, không thể cho rằng test execution với `@MockitoBean` đã chứng minh integration đó.

### 6.5. Resolver từ `@Controller` và `@QueryMapping`

File **`src/main/java/com/example/graphql/GreetingGraphQlController.java`**:

```java
package com.example.graphql;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
public class GreetingGraphQlController {
    private final GreetingService service;

    public GreetingGraphQlController(GreetingService service) {
        this.service = service;
    }

    @QueryMapping
    public String greeting(@Argument String name) {
        return service.greet(name);
    }
}
```

`@QueryMapping` không phải HTTP `@GetMapping`; nó ánh xạ method vào field `greeting` của type `Query` trong GraphQL schema. `@Argument` bind GraphQL argument `name`. HTTP endpoint **`/graphql`** được framework đăng ký khi thêm GraphQL + web starter; controller không cần tự định nghĩa `@PostMapping("/graphql")`.

## 7. Test A: `@GraphQlTest` + `ExecutionGraphQlServiceTester`

File **`src/test/java/com/example/graphql/GreetingExecutionTest.java`**:

```java
package com.example.graphql;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.graphql.execution.ExecutionGraphQlService;
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@GraphQlTest(GreetingGraphQlController.class)
class GreetingExecutionTest {
    @Autowired
    private ExecutionGraphQlService executionService;

    @MockitoBean
    private GreetingService greetingService;

    private ExecutionGraphQlServiceTester tester;

    @BeforeEach
    void createTester() {
        tester = ExecutionGraphQlServiceTester.create(executionService);
    }

    @Test
    void resolvesDataThroughGraphQlExecutionWithoutHttp() {
        when(greetingService.greet("Mai")).thenReturn("Xin chào, Mai!");

        tester.document("{ greeting(name: \"Mai\") }")
                .execute()
                .path("greeting")
                .entity(String.class)
                .isEqualTo("Xin chào, Mai!");

        verify(greetingService).greet("Mai");
    }

    @Test
    void bindsVariablesAndResolvesSelectedField() {
        when(greetingService.greet("An")).thenReturn("Xin chào, An!");

        tester.document("""
                    query Greeting($who: String!) {
                        greeting(name: $who)
                    }
                    """)
                .variable("who", "An")
                .execute()
                .path("greeting")
                .entity(String.class)
                .isEqualTo("Xin chào, An!");

        verify(greetingService).greet("An");
    }

    @Test
    void reportsGraphQlSchemaValidationError() {
        tester.document("{ fieldThatDoesNotExist }")
                .execute()
                .errors()
                .satisfy(errors -> assertThat(errors).isNotEmpty());

        verifyNoInteractions(greetingService);
    }
}
```

**Giải thích kết quả:**

- Test 1 và 2 chứng minh schema, resolver `@QueryMapping`, argument binding và GraphQL data field khi collaborator được mock trả dữ liệu. Không có HTTP client.
- Test 3 gửi **GraphQL document sai schema**. GraphQL execution trả danh sách `errors`; nó không có lý do phải gọi service. `.errors().satisfy(...)` cho phép khẳng định lỗi hiện diện, thay vì tester tự báo fail vì lỗi không được mong đợi.
- `@MockitoBean` là bean override của Spring Framework 6.2+, phù hợp Boot 3.5. Service không được tự scan trong GraphQL slice, nên mock được dùng có chủ đích.
- Test **không xác minh** `POST /graphql` được route, HTTP status 200/400, Content-Type, auth filter hay cổng server.

Nếu chỉ muốn dùng auto-configured tester mà không cần factory trực tiếp, `@GraphQlTest` cũng hỗ trợ **`@Autowired GraphQlTester graphQlTester`**. Ví dụ này cố ý autowire `ExecutionGraphQlService` rồi tạo `ExecutionGraphQlServiceTester` để thể hiện rõ tester đang hoạt động **ở tầng nào**.

## 8. Test B: `HttpGraphQlTester` trong MOCK web environment

File **`src/test/java/com/example/graphql/GreetingMockHttpTest.java`**:

```java
package com.example.graphql;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.graphql.tester.AutoConfigureHttpGraphQlTester;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.graphql.test.tester.HttpGraphQlTester;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureHttpGraphQlTester
class GreetingMockHttpTest {
    @Autowired
    private HttpGraphQlTester tester;

    @Test
    void routesGraphQlDocumentThroughMockHttpTransport() {
        tester.document("{ greeting(name: \"Mai\") }")
                .execute()
                .path("greeting")
                .entity(String.class)
                .isEqualTo("Xin chào, Mai!");
    }
}
```

Test dùng **toàn bộ Spring Boot context** với service thật, cấu hình web MVC và endpoint GraphQL được framework tạo; `@AutoConfigureHttpGraphQlTester` cung cấp HTTP-oriented tester. Tuy nhiên vì `WebEnvironment.MOCK`, request vẫn được xử lý **trong tiến trình**, không có embedded server lắng nghe TCP.

Điểm hơn so với Test A: nó kiểm việc đăng ký HTTP endpoint trong mock web stack và dùng **service thật** thay vì mock. Điểm còn thiếu: không biết cổng socket/embedded server có bind thành công trong môi trường runtime thực hay không.

## 9. Test C: `HttpGraphQlTester` qua HTTP server thật, kèm raw HTTP assertions

File **`src/test/java/com/example/graphql/GreetingRealHttpTest.java`**:

```java
package com.example.graphql;

import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.graphql.test.tester.HttpGraphQlTester;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class GreetingRealHttpTest {
    @Autowired
    private HttpGraphQlTester tester;

    @LocalServerPort
    private int port;

    @Test
    void graphQlTesterVerifiesDataOverRealHttpServer() {
        tester.document("""
                    query Greeting($who: String!) {
                        greeting(name: $who)
                    }
                    """)
                .variable("who", "Mai")
                .execute()
                .path("greeting")
                .entity(String.class)
                .isEqualTo("Xin chào, Mai!");
    }

    @Test
    void webTestClientVerifiesHttpStatusHeadersAndGraphQlEnvelope() {
        WebTestClient rawHttp = WebTestClient.bindToServer()
                .baseUrl("http://127.0.0.1:" + port)
                .build();

        rawHttp.post()
                .uri("/graphql")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of(
                        "query", "{ greeting(name: \"Mai\") }"))
                .exchange()
                .expectStatus().isOk()
                .expectHeader()
                    .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.data.greeting").isEqualTo("Xin chào, Mai!");
    }
}
```

Test thứ nhất dùng **`HttpGraphQlTester`** đã được Spring Boot cấu hình tới server chạy RANDOM_PORT để assert GraphQL data. Test thứ hai dùng **raw `WebTestClient.bindToServer()`** với `@LocalServerPort` để kiểm rõ **HTTP POST /graphql**, HTTP **200**, JSON response media type và envelope `$.data.greeting`. Đây là hai loại bằng chứng bổ sung nhau, không mâu thuẫn.

**Điều kiện chạy:** loopback network được phép bind socket; các dependency test như WebTestClient/reactor client sẵn có. Với ví dụ không có authentication và không có DB, request hợp lệ trả 200. Nếu ứng dụng thật thêm Spring Security, CSRF policy, gateway hoặc profile riêng, phải bổ sung test/authentication tương ứng thay vì copy expected 200 một cách mù quáng.

## 10. Chạy ví dụ và đọc kết quả

Ví dụ có **6 phương thức `@Test`**: 3 execution tests + 1 mock HTTP + 2 real HTTP. Với cấu hình Maven ở phần 6 và môi trường cho phép socket loopback, kết quả kỳ vọng **6 tests pass, 0 failures**.

Tại thư mục có `pom.xml`, nếu đã cài Maven:

```bash
mvn test
```

Nếu dự án có Maven Wrapper:

```bash
./mvnw test
```

Hoặc chạy riêng theo ranh giới:

```bash
mvn -Dtest=GreetingExecutionTest test
mvn -Dtest=GreetingMockHttpTest test
mvn -Dtest=GreetingRealHttpTest test
```

Trên Windows, dùng `mvnw.cmd` khi có wrapper hoặc `mvn` nếu đã cài Maven. `@SpringBootTest(RANDOM_PORT)` sẽ khởi động embedded HTTP server; không hardcode port cố định nên ít gặp xung đột trên CI.

`GreetingExecutionTest` thường nhẹ nhất vì không khởi động web context/server. `GreetingMockHttpTest` khởi động full context nhưng không mở socket. `GreetingRealHttpTest` mở server và thực hiện HTTP thực. Đây là **phân cấp phạm vi**, không nên ép mọi test dùng server thật chỉ để tăng độ “integration”.

## 11. GraphQL errors khác HTTP errors: phải assert cả hai tầng

GraphQL response có envelope:

```json
{
  "data": {
    "greeting": "Xin chào, Mai!"
  }
}
```

Khi GraphQL execution gặp lỗi, response có thể chứa `errors`:

```json
{
  "data": {
    "greeting": null
  },
  "errors": [
    {
      "message": "Example error",
      "path": ["greeting"]
    }
  ]
}
```

JSON phía trên chỉ **minh họa cấu trúc partial-data**; với schema ví dụ `greeting: String!`, lỗi field non-null có thể làm **null propagate lên `data: null`**, nên không dùng mẫu partial-data đó làm expected cụ thể cho bài thực hành.

**Không đồng nhất hai tầng lỗi:**

| Tình huống | GraphQL response | HTTP response |
|---|---|---|
| Query hợp lệ, resolver thành công | `data` có giá trị, thường không có `errors` | Thông thường **200** |
| Resolver throw, GraphQL execution vẫn tạo response | Có thể có `data` một phần/null và `errors` | **Có thể vẫn 200**; không mặc định 500 |
| Document không hợp lệ theo schema | `errors` validation, `data` thường vắng/null | Có thể là **400** hoặc status khác tùy media type/spec/framework |
| JSON HTTP body sai cú pháp, Content-Type sai | Có thể bị từ chối **trước GraphQL execution** | HTTP **400/415** hoặc policy tương ứng |
| Thiếu authentication/authorization HTTP | Request có thể bị security filter từ chối trước resolver | HTTP **401/403** tùy policy |
| Không tồn tại `/graphql` | Không có GraphQL response mong đợi | HTTP **404** |

**Điểm mấu chốt:** `GraphQlTester` thường mặc định báo lỗi khi GraphQL response có unexpected `errors`. Để assert lỗi dự kiến, dùng:

```java
tester.document("{ notARealField }")
        .execute()
        .errors()
        .satisfy(errors -> assertThat(errors).isNotEmpty());
```

Đây là snippet trong test đã có `tester` và AssertJ import, tương tự bài Test A. Khi cần kiểm một lỗi cụ thể, dùng `.errors().expect(predicate).verify()`, hoặc `satisfy` để kiểm `message`, `path`, `extensions.classification` tùy schema/error resolver.

Nhưng **GraphQlTester không phải công cụ kiểm mọi raw HTTP status/header**. Khi HTTP status itself là requirement, dùng `WebTestClient` (như Test C) hoặc HTTP client thật. Đừng chỉ assert `path("greeting")` rồi viết kết luận “API trả 200 và Content-Type đúng” nếu chưa thực sự kiểm HTTP.

## 12. Header, security, interceptor và GraphQL context

Một API GraphQL thực tế có thể dùng `Authorization`, `X-Tenant`, locale hoặc correlation ID. Dữ liệu đó đi qua HTTP filter/security và `WebGraphQlInterceptor`, sau đó có thể đưa vào **GraphQL context** để resolver truy cập.

```text
HTTP header X-Tenant: shop-a
      |
      v
Security / Servlet or WebFlux filters
      |
      v
WebGraphQlInterceptor
      |
      v
GraphQL context / ExecutionInput
      |
      v
DataFetcher / @SchemaMapping
```

`ExecutionGraphQlServiceTester` bỏ qua **phần đầu** của đường này. Nếu tự inject `graphQLContext` vào `ExecutionInput`, test chỉ chứng minh resolver dùng context được đưa vào, **không** chứng minh server đọc đúng HTTP header và áp tenant authorization.

`WebGraphQlTester` chạy qua `WebGraphQlHandler` và interceptor chain với headers mô phỏng. Nó phù hợp cho test `X-Tenant` → GraphQL context **mà không khởi động web transport**, nhưng vẫn chưa kiểm HTTP filter, CORS hoặc socket.

`HttpGraphQlTester` cho phép cấu hình headers:

```java
HttpGraphQlTester tenantTester = tester.mutate()
        .headers(headers -> headers.set("X-Tenant", "shop-a"))
        .build();
```

Đây là snippet trong class có `HttpGraphQlTester tester`; API builder phụ thuộc phiên bản Spring GraphQL đang dùng. Khi tester bind tới mock HTTP, header đi qua **mock web context**; khi bind tới server thật, nó đi qua **HTTP request thật**. Nếu test authentication, cần cấp credentials theo test fixtures và assert quyền truy cập; không dùng token production hoặc vô tình bỏ qua security filter.

Đối với CORS `OPTIONS` preflight, `Content-Type`, `Accept`, size limit và proxy behavior, hãy viết **HTTP-focused tests**. GraphQL execution tester không thể chứng minh những policy đó.

## 13. Query, mutation và subscription có cùng tester hay không?

### Queries và mutations

Cả execution tester và HTTP tester đều dùng `.document(...).execute()` để gọi query/mutation. Khi mutation trả dữ liệu, kiểm `path`/entity; nếu response không có `data` cần kiểm, dùng `executeAndVerify()` theo API của Spring GraphQL để xác nhận không có GraphQL errors.

**Lưu ý transaction:** ở `@SpringBootTest(RANDOM_PORT)`, client test và server xử lý mutation thường ở **khác thread và transaction boundary**. `@Transactional` trên test method **không tự rollback** database commits của server-side request. Dùng DB test riêng, cleanup/fixture rõ; không dùng `@DirtiesContext` thay cho dọn dữ liệu.

### Subscriptions và streaming

Với subscriptions, GraphQL Java có thể trả một Publisher; `ExecutionGraphQlServiceTester` và `WebGraphQlTester` hỗ trợ kiểm subscription trực tiếp bằng `executeSubscription()`. `WebSocketGraphQlTester` dùng transport WebSocket, thích hợp khi cần kiểm session/connection/GraphQL-over-WebSocket.

```java
Flux<String> events = executionTester
        .document("subscription { notifications }")
        .executeSubscription()
        .toFlux("notifications", String.class);

StepVerifier.create(events)
        .expectNext("one", "two")
        .thenCancel()
        .verify();
```

Đây là **snippet về API**, giả định schema có subscription `notifications`, executionTester và publisher được cung cấp; không phải test độc lập. Với HTTP GraphQL **request/response thông thường**, không mặc định dùng `HttpGraphQlTester` để kiểm subscription vô hạn. Một số phiên bản/transport hỗ trợ SSE, nhưng cần test tool và `Accept: text/event-stream` đúng; nếu yêu cầu WebSocket protocol, phải kiểm thật bằng WebSocket client và server config.

## 14. Cách chọn trong dự án thực tế

| Rủi ro cần phát hiện | Bài test khuyến nghị |
|---|---|
| SDL `String!`, argument `name`, `@QueryMapping` bind đúng | **`@GraphQlTest` + `ExecutionGraphQlServiceTester`** |
| Resolver và Spring GraphQL exception resolver tạo `errors` đúng | Execution tester, context có exception resolver |
| Header `X-Tenant` được GraphQL interceptor đưa vào context | **`WebGraphQlTester`**, hoặc HTTP tester khi cần kiểm toàn HTTP |
| `POST /graphql` route/JSON body đúng nhưng không cần socket | **`@SpringBootTest(MOCK)` + `@AutoConfigureHttpGraphQlTester`** |
| Security, HTTP status, cookies/headers trong web stack | **`HttpGraphQlTester` + raw WebTestClient** ở mock/full HTTP tùy mục tiêu |
| Embedded server thật mở cổng và nhận HTTP POST | **`@SpringBootTest(RANDOM_PORT)` + `HttpGraphQlTester`** |
| DB query, transaction, DataLoader và nhiều service thật | Integration test với DB test tương thích; mock ít nhất có thể |
| GraphQL subscription over WebSocket | **`WebSocketGraphQlTester`**, có server và protocol config |
| CORS, TLS termination, gateway, deployment networking | HTTP/deployment-level test tại môi trường chứa các thành phần đó |
| Chỉ logic service Java | JUnit/Mockito thuần, **không cần GraphQL tester** |

Một chiến lược hữu ích là **nhiều execution tests nhanh** cho các GraphQL schema/resolver cases, **một số HTTP mock tests** cho web integration, và **một vài live HTTP tests** cho đường critical. Không có tỷ lệ cố định cho mọi dự án; chọn theo rủi ro sản phẩm.

## 15. Khác biệt phiên bản Spring Boot / Spring GraphQL

Ví dụ ở trên chọn **Spring Boot 3.5.0** để cố định imports:

```java
// Spring Boot 3.5:
import org.springframework.boot.test.autoconfigure.graphql.GraphQlTest;
import org.springframework.boot.test.autoconfigure.graphql.tester.AutoConfigureHttpGraphQlTester;

// Spring for GraphQL test:
import org.springframework.graphql.test.tester.ExecutionGraphQlServiceTester;
import org.springframework.graphql.test.tester.HttpGraphQlTester;
```

Đây là **các dòng import minh họa**, không phải file Java độc lập. `spring-graphql-test` là dependency test riêng. `spring-boot-starter-graphql` ở runtime cung cấp GraphQL service/schema, nhưng **không tự biến một app không có web starter thành HTTP API**. Muốn expose qua Servlet MVC cần web starter, và muốn test HTTP client cần test client classpath tương ứng.

Trong **Spring Boot 4.x**, các test module/starter đã được tách theo công nghệ, ví dụ module **`spring-boot-graphql-test`**, và **package của các annotation auto-configuration đã đổi** so với Boot 3.5. Spring GraphQL cũng có các phiên bản riêng; luôn tra Javadoc và dependency tree **theo version thực sự đang chạy** thay vì copy import Boot 3.5 vào Boot 4 và chỉ đổi `pom.xml` parent.

Với Spring Boot 3.5, cấu hình đường dẫn HTTP GraphQL là **`spring.graphql.http.path`** (mặc định `/graphql`). Nếu bạn thấy `spring.graphql.path` trong tài liệu Boot cũ, đừng mặc định nó còn là property chính ở 3.5/4.x. Test execution không bị ảnh hưởng bởi đổi URL transport; live HTTP test cần dùng đúng path cấu hình.

## 16. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân có khả năng | Cách xử lý |
|---|---|---|
| `ExecutionGraphQlServiceTester` pass nhưng HTTP 404 | Schema/resolver đúng nhưng HTTP transport không được đăng ký hoặc path thay đổi | Kiểm web starter, `spring.graphql.http.path`, raw HTTP test |
| Test GraphQL execution không inject được service | `@GraphQlTest` cố ý exclude `@Service` | `@MockitoBean` hoặc `@Import` dependency nhỏ; full test nếu cần service thật |
| `HttpGraphQlTester` không inject được | Thiếu `spring-graphql-test`, WebTestClient test dependency hoặc auto-config đúng mode | Kiểm starter-graphql, web/webflux test classpath, annotation cấu hình |
| `HttpGraphQlTester` pass mà server thật không start | Tester đang bind vào mock context | Chạy RANDOM_PORT và kiểm port/HTTP request thật |
| HTTP trả 200 nhưng GraphQL query lỗi | GraphQL execution error trong `errors`, status không nhất thiết 500 | Kiểm `.errors()` và raw response `errors` |
| `GraphQlTester.execute()` fail khi kỳ vọng error | Mặc định tester coi unexpected errors là failure | `.errors().expect(...)` hoặc `.satisfy(...)` |
| Raw HTTP test 401/403 | Security filter hoặc CSRF policy chặn | Setup credentials/CSRF theo context và kiểm policy |
| Header tenant không có trong resolver | Chưa chạy `WebGraphQlInterceptor` hoặc header không được propagate | `WebGraphQlTester` hoặc HTTP tester, kiểm interceptor |
| `@QueryMapping` tồn tại nhưng field không query được | GraphQL SDL thiếu field, type/name không khớp | Cập nhật `schema.graphqls`, assert validation error |
| Test execution đúng, CORS preflight thất bại | Execution tester không chạy HTTP CORS layer | Kiểm HTTP OPTIONS, origin, allowed headers/methods |
| JSON parser sai HTTP request | Document GraphQL hợp lệ nhưng HTTP body/Content-Type không đúng | Kiểm POST body `{"query": "..."}`, Accept/Content-Type |
| Subscription test bị treo | Stream không bao giờ hoàn tất, chưa cancel/timeout | `StepVerifier.thenCancel()` và timeout; dùng tester subscription phù hợp |
| Live mutation làm dữ liệu rò sang test khác | Server transaction khác test transaction | DB test riêng, cleanup/fixture độc lập |
| Boot 4 compile lỗi annotation tester | Module/package đã đổi | Đối chiếu import và dependency đúng dòng Boot/Spring GraphQL |

## 17. Checklist trước khi hoàn thành

- [ ] Tôi phát biểu được test đang chứng minh **GraphQL execution, WebGraphQlInterceptor hay HTTP transport**.
- [ ] Tôi không cho rằng tên `HttpGraphQlTester` đồng nghĩa đã có socket thật.
- [ ] Với resolver/schema logic, tôi dùng `@GraphQlTest` và tester execution khi phù hợp.
- [ ] Tôi biết `@GraphQlTest` không tự nạp service/repository bình thường.
- [ ] Tôi phân biệt test mock collaborator và test service/DB thật.
- [ ] Nếu cần header → GraphQL context, tôi đã test `WebGraphQlInterceptor` hoặc HTTP layer, không chỉ tự đặt context vào `ExecutionInput`.
- [ ] Nếu cần HTTP status, headers, Content-Type, route, tôi dùng raw HTTP client assertion.
- [ ] Nếu cần socket/server thật, tôi dùng RANDOM_PORT và không hardcode port.
- [ ] GraphQL `data` và `errors` đều có assertions theo contract; không suy ra GraphQL error từ status.
- [ ] Với non-null fields, tôi hiểu null propagation khi resolver thất bại.
- [ ] Schema `*.graphqls` có mặt và field/argument name đúng resolver.
- [ ] Subscription chọn tester/transport phù hợp và có cơ chế cancel/timeouts.
- [ ] Tôi không kỳ vọng transaction của test thread rollback HTTP mutation được server commit.
- [ ] Tôi kiểm classpath/test modules, imports và property names theo version Spring Boot thực tế.
- [ ] Đã chạy test bằng build tool, so sánh kết quả với **ranh giới đã kiểm** thay vì chỉ nhìn “Tests passed”.

**Kết luận:** **`ExecutionGraphQlServiceTester` chứng minh thực thi GraphQL trong Spring, không chứng minh HTTP.** `WebGraphQlTester` bổ sung phần web handler/interceptors; `HttpGraphQlTester` kiểm HTTP transport **nhưng phải xem nó bind mock hay server thật**. Khi mục tiêu là GraphQL data/errors, `GraphQlTester` có API thống nhất; khi mục tiêu là HTTP status/headers/security/network, hãy kiểm thêm **HTTP layer tương ứng**.

### Tài liệu chính thức

- [Spring GraphQL — Testing: ExecutionGraphQlServiceTester, WebGraphQlTester và HttpGraphQlTester](https://docs.spring.io/spring-graphql/reference/testing.html)
- [Spring GraphQL — Request Execution và GraphQlSource](https://docs.spring.io/spring-graphql/reference/request-execution.html)
- [Spring Boot 3.5 — Auto-configured Spring GraphQL Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — Spring GraphQL HTTP transport và schema](https://docs.spring.io/spring-boot/3.5/reference/web/spring-graphql.html)
- [Spring Boot 3.5 — Common Application Properties: `spring.graphql.http.path`](https://docs.spring.io/spring-boot/3.5/appendix/application-properties/index.html)
- [Spring Boot 4.x — Testing Spring GraphQL](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
