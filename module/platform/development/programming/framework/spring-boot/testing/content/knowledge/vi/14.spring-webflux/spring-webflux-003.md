# Kiểm thử annotated Controller và functional endpoint trong Spring WebFlux

Spring WebFlux hỗ trợ **hai cách khai báo HTTP endpoint**. Với **annotated Controller**, lập trình viên dùng `@RestController`, `@GetMapping`, `@RequestParam` và các annotation quen thuộc để ánh xạ request tới method. Với **functional endpoint**, lập trình viên ghép `RouterFunction<ServerResponse>` để định tuyến tới `HandlerFunction` nhận `ServerRequest` và trả `Mono<ServerResponse>`.

Hai cách tiếp cận cùng thuộc **reactive web stack**, đều đi qua cơ chế xử lý request/response của WebFlux, nhưng **phạm vi test setup không giống nhau**. `@WebFluxTest` chuyên cho annotated controllers; nó **không tự khám phá các RouterFunction của functional endpoint**. Muốn test functional routing, nên dùng `WebTestClient.bindToRouterFunction(...)`, chủ động `@Import` router/handler vào context test, hoặc chạy `@SpringBootTest` với application context.

Mục tiêu của bài là trả lời: **cần kiểm điều gì, nên bind WebTestClient vào đâu, mock dependency nào, khi nào cần HTTP server thật, và kết quả PASS chứng minh được đến ranh giới nào?** Các ví dụ dùng **Java 17, Spring Boot 3.5, JUnit Jupiter và WebTestClient**, kèm cả test không có Spring context, test slice và test HTTP tích hợp.

## 1. Annotated Controller và functional endpoint: khác biệt chính

| Tiêu chí | Annotated Controller | Functional endpoint |
|---|---|---|
| Khai báo route | `@GetMapping`, `@PostMapping`, `@RequestMapping` trên class/method | `RouterFunction` kết hợp `RequestPredicates`, `RouterFunctions.route` |
| Thành phần xử lý | Method của `@Controller` / `@RestController` | `HandlerFunction` hoặc method handler nhận `ServerRequest` |
| Đọc input | `@PathVariable`, `@RequestParam`, `@RequestBody`, argument resolvers | `ServerRequest.pathVariable`, `queryParam`, `bodyToMono`, v.v. |
| Tạo response | Return value `Mono<T>`, `Flux<T>`, `ResponseEntity<...>`; WebFlux xử lý status/body | `ServerResponse.ok()`, `badRequest()`, `bodyValue`, `body(...)` |
| Định tuyến trong Spring | RequestMappingHandlerMapping / annotated handler adapter | RouterFunctionMapping / HandlerFunctionAdapter |
| Test nhỏ không cần server | `WebTestClient.bindToController(controller)` | `WebTestClient.bindToRouterFunction(router)` |
| Test slice Boot | `@WebFluxTest(Controller.class)` | `@WebFluxTest` **và `@Import` router/handler cần thiết**, hoặc test router trực tiếp |
| Test full HTTP | `@SpringBootTest(RANDOM_PORT)` | `@SpringBootTest(RANDOM_PORT)` |

**Điểm chung:** cả hai có thể nhận/trả `Mono`, `Flux`; `WebTestClient` đều có thể kiểm **status, header, JSON, error response và hợp đồng reactive**. **Điểm khác:** cách phát hiện route, cách bind test và API dùng để chuyển request thành response.

Không trộn **Spring MVC functional endpoints** (`org.springframework.web.servlet.function`) với **Spring WebFlux functional endpoints** (`org.springframework.web.reactive.function.server`). Bài này chỉ dùng **WebFlux**. Nếu dự án có cả `spring-boot-starter-web` và `spring-boot-starter-webflux`, Spring Boot thông thường ưu tiên MVC Servlet stack; cần xác minh web application type trước khi cho rằng test đang chạy WebFlux.

## 2. Chọn kiểu test theo bằng chứng cần thu

| Mục tiêu | Công cụ / kiểu test | Có HTTP socket thật? | Điều chưa chứng minh |
|---|---|---|---|
| Kiểm method controller với cấu hình WebFlux tối thiểu | `WebTestClient.bindToController(new Controller(...))` | **Không** | Context Spring Boot, component scan, bean injection và server thật |
| Kiểm RouterFunction + handler được ghép chính xác | `WebTestClient.bindToRouterFunction(router)` | **Không** | Router có được Spring Boot đăng ký thành bean trong app hay không |
| Kiểm annotated controller, binding, JSON và exception handler trong WebFlux slice | `@WebFluxTest(Controller.class)` + `WebTestClient` | **Không** | Business service thật nếu đã dùng mock; không kiểm TCP |
| Kiểm functional route trong Spring TestContext slice | `@WebFluxTest` + `@Import` router/handler + mock collaborator | **Không** | Toàn bộ ứng dụng và socket; các bean không import không tự xuất hiện |
| Kiểm cả annotated + functional route với bean thật, không cần socket | `@SpringBootTest(MOCK)` + `@AutoConfigureWebTestClient` | **Không** | HTTP connector/TLS/port thật |
| Kiểm hai loại endpoint qua HTTP server embedded và DI thực | `@SpringBootTest(RANDOM_PORT)` + `WebTestClient` | **Có** | Hạ tầng production ngoài test như gateway, proxy, DB thật nếu chưa được cấu hình |
| Kiểm riêng logic tạo Mono/Flux, lỗi và completion | `StepVerifier` trong unit test | Không áp dụng | HTTP mapping, serialization và router |

**Quy tắc chọn:** nếu muốn chứng minh “`GET /functional/greet` có được định tuyến đến handler không”, `bindToRouterFunction` đủ; nếu muốn chứng minh **Spring Boot thật sự đăng ký bean RouterFunction** vào context, cần test có Spring context; nếu muốn chứng minh **server HTTP thật** có thể nhận route đó, cần RANDOM_PORT hoặc hệ thống test có server thật.

## 3. `WebTestClient` có nhiều kiểu bind, không phải lúc nào cũng gọi mạng

`WebTestClient` cung cấp fluent API thống nhất, ví dụ `get().uri(...).exchange().expectStatus().isOk().expectBody().jsonPath(...)`, nhưng **phần server setup quyết định ranh giới kiểm thử**:

```java
// Snippet 1: WebFlux controller được tạo thủ công, không cần Spring Boot server.
WebTestClient a = WebTestClient.bindToController(controller).build();

// Snippet 2: Một WebFlux RouterFunction, không cần server hay Spring Boot.
WebTestClient b = WebTestClient.bindToRouterFunction(router).build();

// Snippet 3: WebFlux ApplicationContext đã tạo sẵn, không cần socket.
WebTestClient c = WebTestClient.bindToApplicationContext(context).build();

// Snippet 4: Server thực sự đang nghe HTTP ở URL chỉ định.
WebTestClient d = WebTestClient.bindToServer()
        .baseUrl("http://127.0.0.1:8081").build();
```

**Đây là các đoạn minh họa API**, giả định có biến `controller`, `router`, `context`, và server tại 8081; chúng không phải file biên dịch độc lập. `bindToServer` có thể vô tình gọi server không thuộc test nếu hardcode nhầm URL. Với `@SpringBootTest(RANDOM_PORT)`, ưu tiên inject `WebTestClient` được Boot cấu hình trỏ đúng embedded server.

Các cách bind mock tạo request/response trong tiến trình, **không dùng TCP socket**, nhưng vẫn có thể kiểm nhiều phần WebFlux stack. Khi dùng `bindToRouterFunction`, WebFlux sử dụng cơ chế tương đương `RouterFunctions.toWebHandler`. `WebTestClient.bindToController` nạp hạ tầng WebFlux cần thiết cho annotated controller, không tự nạp mọi Spring bean của ứng dụng.

### Đường đi khi có router và controller

```text
HTTP request / WebTestClient mock request
           |
           v
       WebFlux WebHandler
           |
           +--> Annotated mapping --> @RestController method --> Mono/Flux
           |
           +--> Functional routing --> RouterFunction --> HandlerFunction
           |
           v
  WebFlux codecs / response handling --> status, headers, body
```

Sơ đồ là khái niệm, không biểu diễn thứ tự ưu tiên giữa mọi `HandlerMapping`. **Không nên tạo hai endpoint cùng method + path** rồi giả định annotation luôn thắng router (hoặc ngược lại); phải xem thứ tự mapping cụ thể. Ví dụ bên dưới dùng **hai URL khác nhau** để test rõ ràng.

## 4. Ví dụ hoàn chỉnh Java 17 + Spring Boot 3.5

Ứng dụng trả thông điệp `Hello, Linh!` khi nhận query parameter `name=Linh`, với hai endpoint:

- **Annotated:** `GET /api/annotated/greet?name=Linh`.
- **Functional:** `GET /api/functional/greet?name=Linh`.

Cả hai trả HTTP **200** và JSON body `{"message":"Hello, Linh!"}`. Nếu không truyền `name`, cả hai trả **400**: annotated endpoint nhờ `@RequestParam` bắt buộc; functional handler phải **tự kiểm tra** và xây `ServerResponse.badRequest()`.

Ví dụ không có database, security starter hoặc external API. `GreetingService` chỉ xử lý một chuỗi trong bộ nhớ; điều này giúp tập trung vào **route và test boundary**. Trường hợp `name` là chuỗi rỗng không được mô hình hóa như một quy tắc validation trong ví dụ; nếu contract yêu cầu không cho phép rỗng, cần thêm validation rõ ràng và test cho **cả hai kiểu endpoint**.

### 4.1. Cây thư mục

```text
webflux-endpoint-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/webflux/
    │   ├── DemoApplication.java
    │   ├── GreetingResponse.java
    │   ├── GreetingService.java
    │   ├── GreetingController.java
    │   ├── GreetingHandler.java
    │   └── GreetingRouter.java
    └── test/java/com/example/webflux/
        ├── GreetingControllerSliceTest.java
        ├── GreetingRouterDirectTest.java
        ├── GreetingRouterSliceTest.java
        └── GreetingHttpIntegrationTest.java
```

### 4.2. `pom.xml`: reactive stack, không có MVC

File **`pom.xml`**:

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
    <artifactId>webflux-endpoint-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
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
```

`spring-boot-starter-webflux` đưa reactive WebFlux và embedded Reactor Netty server vào ứng dụng mẫu. Không thêm `spring-boot-starter-web` để tránh ưu tiên MVC khi cả hai stack cùng có mặt. `spring-boot-starter-test` cung cấp JUnit Jupiter, Mockito và Spring test support trong bộ phiên bản Boot 3.5 được quản lý. `@MockitoBean` dùng trong test thuộc Spring Framework **6.2+**, phù hợp với Spring Boot 3.5.0.

### 4.3. Các source file của ứng dụng

File **`src/main/java/com/example/webflux/DemoApplication.java`**:

```java
package com.example.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

File **`src/main/java/com/example/webflux/GreetingResponse.java`**:

```java
package com.example.webflux;

public record GreetingResponse(String message) {
}
```

File **`src/main/java/com/example/webflux/GreetingService.java`**:

```java
package com.example.webflux;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public GreetingResponse greet(String name) {
        return new GreetingResponse("Hello, " + name + "!");
    }
}
```

Đây là service đồng bộ **chỉ tính toán trong bộ nhớ**; nó không gọi JDBC hoặc I/O blocking. Trong ứng dụng reactive thật, **không** dùng `Mono.fromSupplier` để che các lời gọi blocking database/HTTP rồi nghĩ chúng tự trở thành non-blocking: cần dùng reactive driver/client phù hợp hoặc tách blocking work ra scheduler được quản lý.

### 4.4. Annotated Controller trả `Mono<GreetingResponse>`

File **`src/main/java/com/example/webflux/GreetingController.java`**:

```java
package com.example.webflux;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class GreetingController {
    private final GreetingService service;

    public GreetingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping(
            path = "/api/annotated/greet",
            produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<GreetingResponse> greet(@RequestParam("name") String name) {
        return Mono.fromSupplier(() -> service.greet(name));
    }
}
```

Ở đây `@RequestParam("name")` mặc định **bắt buộc**. Nếu thiếu query parameter, WebFlux trả HTTP 400 trước khi method được gọi; nếu có, method trả `Mono<GreetingResponse>` và WebFlux serialize `record` thành JSON. `Mono.fromSupplier` trì hoãn việc tạo giá trị tới khi publisher được subscribe, **không** có nghĩa tác vụ trong supplier tự chạy trên thread khác.

### 4.5. Functional Handler nhận `ServerRequest`

File **`src/main/java/com/example/webflux/GreetingHandler.java`**:

```java
package com.example.webflux;

import java.util.Map;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;

@Component
public class GreetingHandler {
    private final GreetingService service;

    public GreetingHandler(GreetingService service) {
        this.service = service;
    }

    public Mono<ServerResponse> greet(ServerRequest request) {
        var name = request.queryParam("name");
        if (name.isEmpty()) {
            return ServerResponse.badRequest()
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(Map.of("error", "name is required"));
        }

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(service.greet(name.orElseThrow()));
    }
}
```

Functional handler tự lấy query parameter từ `ServerRequest`; `queryParam` trả `Optional`. Khi thiếu `name`, handler **chủ động** tạo HTTP 400 với body JSON có `error`. Khi có tên, handler tạo `ServerResponse.ok()` và body từ service. Vì `bodyValue` trả `Mono<ServerResponse>`, chữ ký method hợp lệ.

**Điểm đối chiếu quan trọng:** annotated controller nhận `@RequestParam` qua framework argument resolver, còn functional handler đọc từ `ServerRequest` và tự xử lý thiếu tham số. Do đó khi test hai implementation cùng một contract, phải xác minh cả **status** và các khác biệt **error body** mà API cho phép.

### 4.6. Functional RouterFunction đăng ký route

File **`src/main/java/com/example/webflux/GreetingRouter.java`**:

```java
package com.example.webflux;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

import static org.springframework.web.reactive.function.server.RequestPredicates.GET;
import static org.springframework.web.reactive.function.server.RouterFunctions.route;

@Configuration(proxyBeanMethods = false)
public class GreetingRouter {

    @Bean
    RouterFunction<ServerResponse> greetingRoute(GreetingHandler handler) {
        return route(GET("/api/functional/greet"), handler::greet);
    }
}
```

Spring đăng ký `RouterFunction<ServerResponse>` từ phương thức `@Bean`. `RequestPredicates.GET` chọn HTTP method và path; `handler::greet` đưa request vào `GreetingHandler`. Test ở phần sau chứng minh **route được tạo** và **route được Spring Boot thực sự nạp** — hai điều khác nhau.

## 5. Test annotated Controller với `@WebFluxTest`

File **`src/test/java/com/example/webflux/GreetingControllerSliceTest.java`**:

```java
package com.example.webflux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@WebFluxTest(GreetingController.class)
class GreetingControllerSliceTest {

    @Autowired
    private WebTestClient client;

    @MockitoBean
    private GreetingService service;

    @Test
    void annotatedRouteReturnsJsonFromMockedService() {
        when(service.greet("Linh"))
                .thenReturn(new GreetingResponse("Hello, Linh!"));

        client.get()
                .uri("/api/annotated/greet?name=Linh")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello, Linh!");

        verify(service).greet("Linh");
    }

    @Test
    void missingQueryParameterReturns400BeforeCallingService() {
        client.get()
                .uri("/api/annotated/greet")
                .exchange()
                .expectStatus().isBadRequest();

        verifyNoInteractions(service);
    }
}
```

**`@WebFluxTest(GreetingController.class)`** tạo Spring WebFlux slice với annotated controller và hạ tầng cần thiết; **`WebTestClient` đã được auto-configure**, không cần tự tạo HTTP server. `GreetingService` là service bình thường nên **không được scan vào slice**; `@MockitoBean` cung cấp mock trong Spring context để constructor của controller có dependency. Trong Framework 6.2, `@MockitoBean` mặc định có thể tạo mock mới nếu bean gốc không có — điều này là có chủ đích ở web slice.

Test đầu xác minh **route, query parameter, JSON và invocation** với service mock. Test sau xác minh missing `@RequestParam` gây 400 và controller không gọi service. **Không thể suy ra logic thật của `GreetingService` đã được kiểm**, vì service được mock.

Nếu code bật Spring Security, các `WebFilter` và security configuration có thể khiến request bị 401/403 trước controller. Khi đó cần cấu hình test authentication hoặc import đúng `SecurityWebFilterChain` cần kiểm. Không tắt bảo mật tùy tiện chỉ để test pass nếu security là phạm vi bằng chứng mong muốn.

## 6. Test functional endpoint trực tiếp bằng `bindToRouterFunction`

File **`src/test/java/com/example/webflux/GreetingRouterDirectTest.java`**:

```java
package com.example.webflux;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.ServerResponse;

class GreetingRouterDirectTest {
    private WebTestClient client;

    @BeforeEach
    void createClientFromRouter() {
        GreetingHandler handler =
                new GreetingHandler(new GreetingService());
        RouterFunction<ServerResponse> router =
                new GreetingRouter().greetingRoute(handler);

        client = WebTestClient.bindToRouterFunction(router).build();
    }

    @Test
    void functionalRouterMatchesGetAndReturnsJson() {
        client.get()
                .uri("/api/functional/greet?name=Linh")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello, Linh!");
    }

    @Test
    void functionalHandlerReturns400ForMissingName() {
        client.get()
                .uri("/api/functional/greet")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.error").isEqualTo("name is required");
    }
}
```

Ở đây ta **tạo router và handler bằng Java thuần**, sau đó bind WebTestClient vào RouterFunction. Test khẳng định `GET` được route đúng tới handler và hai nhánh response hoạt động. Không có Spring Boot `ApplicationContext` hoặc server TCP; cấu hình `@Component`/`@Bean` **chưa được chứng minh** là Spring thực sự scan và inject đúng.

Đây là lợi thế của test trực tiếp: nhanh, rõ và rất phù hợp cho route predicate, path/query parameter, mapping response hoặc handler behavior cô lập. Nhưng nếu production quên đăng ký `GreetingRouter`, bài test này **vẫn có thể pass** vì tự tạo router.

## 7. Test functional endpoint trong WebFlux slice: phải import router

**Cạm bẫy:** `@WebFluxTest` được thiết kế để chọn annotated `@Controller` và các thành phần WebFlux liên quan. Nó **không tự phát hiện các `RouterFunction` bean** được đăng ký qua functional routing. Nếu chỉ gắn `@WebFluxTest` rồi gửi GET tới `/api/functional/greet`, test có thể trả 404 vì router không được nạp vào slice, không phải vì handler code sai.

Khi muốn giữ Spring TestContext nhưng vẫn test RouterFunction, hãy chủ động import cấu hình router và handler:

File **`src/test/java/com/example/webflux/GreetingRouterSliceTest.java`**:

```java
package com.example.webflux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@WebFluxTest(GreetingController.class)
@Import({GreetingRouter.class, GreetingHandler.class})
class GreetingRouterSliceTest {

    @Autowired
    private WebTestClient client;

    @MockitoBean
    private GreetingService service;

    @Test
    void importedFunctionalRouteUsesMockedService() {
        when(service.greet("Linh"))
                .thenReturn(new GreetingResponse("Hello, Linh!"));

        client.get()
                .uri("/api/functional/greet?name=Linh")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello, Linh!");

        verify(service).greet("Linh");
    }

    @Test
    void importedHandlerRejectsMissingNameWithoutServiceCall() {
        client.get()
                .uri("/api/functional/greet")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.error").isEqualTo("name is required");

        verifyNoInteractions(service);
    }
}
```

`@Import({GreetingRouter.class, GreetingHandler.class})` bổ sung **đúng bean cần thiết**: bean `RouterFunction` do config tạo và `GreetingHandler` có dependency `GreetingService` từ `@MockitoBean`. `@WebFluxTest(GreetingController.class)` ở đây còn nạp annotated controller, nhưng hai test đang **nhắm tới functional path riêng**; nếu chỉ quan tâm router đơn thuần, `bindToRouterFunction` ở phần 6 gọn hơn.

Khác với test trực tiếp, cách này xác minh router **được đăng ký trong test ApplicationContext theo cấu hình import đã chọn**. Nó vẫn **không chứng minh** toàn bộ production context tự scan/import router đúng nếu test đặc biệt nhập config mà production lại quên. Để kiểm startup wiring như production, bổ sung integration test tiếp theo.

## 8. Test hai endpoint trong full Spring Boot context và HTTP server thật

File **`src/test/java/com/example/webflux/GreetingHttpIntegrationTest.java`**:

```java
package com.example.webflux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.SpringBootTest.WebEnvironment;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(webEnvironment = WebEnvironment.RANDOM_PORT)
class GreetingHttpIntegrationTest {

    @Autowired
    private WebTestClient client;

    @Test
    void annotatedControllerWorksOverRealHttp() {
        client.get()
                .uri("/api/annotated/greet?name=Linh")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello, Linh!");
    }

    @Test
    void functionalRouterWorksOverRealHttp() {
        client.get()
                .uri("/api/functional/greet?name=Linh")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.message").isEqualTo("Hello, Linh!");
    }
}
```

Trong Spring Boot 3.5 và ứng dụng WebFlux có server embedded, `RANDOM_PORT` khởi động **Reactor Netty HTTP server thật** tại port do hệ điều hành cấp. Boot có thể inject `WebTestClient` với base URL trỏ tới server đó, nên hai request dùng relative URI là HTTP request **qua socket thật**. Không cần hardcode `8080`; không phải gọi trực tiếp vào mock DispatcherServlet.

Đây là test **rộng hơn slice**: nó chứng minh annotated controller, functional `RouterFunction`, handler/service, DI, codecs và HTTP server cùng hoạt động trong context ứng dụng được Spring Boot phát hiện. Nó **không tự chứng minh** production TLS, reverse proxy, gateway, DB hoặc remote service nếu chúng không có mặt trong môi trường ví dụ.

Nếu muốn full context nhưng **không cần socket**, có thể dùng `@SpringBootTest(webEnvironment = WebEnvironment.MOCK)` với `@AutoConfigureWebTestClient` của Spring Boot 3.5 để bind `WebTestClient` vào mock WebFlux environment. Hai cấu hình full-context này có ranh giới khác nhau, đừng đánh đồng.

## 9. Lệnh chạy và kết quả kỳ vọng

Tại thư mục có `pom.xml`, cần Java 17+ và Maven. Chạy toàn bộ:

```bash
mvn test
```

Nếu dự án có Maven Wrapper, có thể dùng:

```bash
./mvnw test
```

Hoặc chạy riêng từng class:

```bash
mvn -Dtest=GreetingControllerSliceTest test
mvn -Dtest=GreetingRouterDirectTest test
mvn -Dtest=GreetingRouterSliceTest test
mvn -Dtest=GreetingHttpIntegrationTest test
```

Trên Windows, dùng `mvn` khi Maven đã được cài hoặc `mvnw.cmd` nếu dự án có wrapper. Không cần chạy `javac` riêng: đây là test JUnit/Boot cần dependency và Maven test runner; class không có `main`.

Với đúng các file ở trên, tổng cộng **8 phương thức `@Test`**: annotated slice 2, router direct 2, router slice 2 và HTTP integration 2. Kỳ vọng **8 test pass, 0 fail**, với điều kiện test dependencies đã tải được và môi trường cho phép mở kết nối HTTP loopback cho test RANDOM_PORT. Không có một stdout nghiệp vụ bắt buộc; Maven Surefire và JUnit có định dạng report tùy phiên bản.

Để debug, chạy test riêng trước rồi mới chạy cả suite. Một test `bindToRouterFunction` pass nhưng `@SpringBootTest` trả 404 ở functional URL thường báo hiệu **router không được đăng ký trong application context thật**, chứ không phải logic handler luôn sai.

## 10. Input, response và negative-path cần kiểm khác nhau thế nào?

Trong ví dụ:

| Trường hợp | Annotated endpoint | Functional endpoint |
|---|---|---|
| `?name=Linh` | `@RequestParam` bind tên → service → `Mono<GreetingResponse>` | `ServerRequest.queryParam` → service → `Mono<ServerResponse>` |
| Thiếu `name` | Framework `@RequestParam` required trả **400** | Handler tự kiểm tra `Optional.isEmpty()`, trả **400** |
| Response hợp lệ | WebFlux serialize record thành JSON | `bodyValue(record)` tạo JSON qua codecs |
| Mã lỗi/body | Framework error response mặc định theo cấu hình | Error JSON `{"error":"name is required"}` được handler định nghĩa |
| Service thật/mock | Tùy test slice hoặc integration | Tùy test bind trực tiếp, slice/import hoặc integration |

Không nên chỉ assert `isOk()` mà bỏ response body. Có thể dùng `expectBody().jsonPath("$.message").isEqualTo(...)`; khi cần contract chính xác hơn, kiểm `contentTypeCompatibleWith(MediaType.APPLICATION_JSON)`, các field required, các error codes và body schema.

Để kiểm `@RequestBody` hoặc functional `request.bodyToMono(MyRequest.class)`, cần thêm các ca: body JSON hợp lệ, body rỗng, JSON sai format, validation fail, unsupported media type, business exception và response serialization. **Status mặc định khác nhau** tùy cơ chế framework/controller advice/filter; đừng cố áp cùng message lỗi mà chưa chủ động thiết kế error contract thống nhất.

Nếu muốn test **dữ liệu đến từ route variable**, dùng `@PathVariable` ở annotated và `ServerRequest.pathVariable(...)` ở functional; kiểm path hợp lệ/không match. Nếu muốn test content negotiation, thêm header `Accept` hoặc `Content-Type` và assert phản hồi theo hợp đồng. Test nhóm nào nạp đúng encoder/decoder liên quan là quan trọng hơn tên annotation.

## 11. Reactive đặc thù: Mono, Flux, StepVerifier, streaming và thread

`WebTestClient` kiểm HTTP contract rất tốt: status, headers, body. `StepVerifier` của Reactor Test lại phù hợp khi muốn kiểm **chuỗi tín hiệu Publisher** độc lập với HTTP, ví dụ `onNext`, `onError`, `onComplete`, yêu cầu/cancel và thời gian ảo.

Đoạn minh họa **đặt trong unit test khi có `reactor-test` trên test classpath**:

```java
Flux<String> values = Flux.just("alpha", "beta");

StepVerifier.create(values)
        .expectNext("alpha", "beta")
        .verifyComplete();
```

Cần import `reactor.core.publisher.Flux` và `reactor.test.StepVerifier`; khi dự án chưa có `reactor-test`, bổ sung dependency test tương thích do Spring Boot BOM quản lý. Snippet không phải file độc lập. Đừng dùng StepVerifier như thay thế kiểm routing/JSON ở `WebTestClient`.

### Streaming và SSE khác JSON thường

Với endpoint trả `Flux<T>` vô hạn hoặc **Server-Sent Events** (`text/event-stream`), test không nên gọi `expectBodyList` rồi chờ stream hoàn tất mãi mãi. Có thể nhận stream qua `returnResult(T.class).getResponseBody()`, dùng StepVerifier để kiểm vài `onNext` rồi **cancel**, hoặc đặt timeout/cơ chế virtual time phù hợp. Với stream hữu hạn, `expectBodyList(T.class)` có thể đủ.

**Không viết `Thread.sleep` để “đợi reactive test chạy xong”** nếu đã có operator/test utility phù hợp. Không biến code blocking thành non-blocking chỉ bằng cách wrap vào Mono; gọi `block()` trên event-loop của WebFlux là sai phạm vi và có thể khiến test treo hoặc runtime phản ứng khác mong đợi.

### Transaction qua server thật

Khi dùng `@SpringBootTest(RANDOM_PORT)` và client gửi HTTP thật, request được xử lý trên server thread/transaction khác test thread. `@Transactional` ở test **không tự rollback** dữ liệu được commit bên server. Với test WebFlux + R2DBC, còn phải hiểu cơ chế **reactive transaction context** khác transaction ThreadLocal của JPA. Dùng test DB riêng và cleanup rõ ràng; đừng suy luận từ test controller mock rằng persistence thật đã an toàn.

## 12. Spring Security và filters: nguồn khác biệt giữa slice và full context

Ứng dụng WebFlux có thể dùng `SecurityWebFilterChain`, `WebFilter`, global exception handlers và codecs tùy chỉnh.

- `@WebFluxTest` nạp tập bean WebFlux giới hạn; **custom SecurityWebFilterChain bean không được tự động tìm thấy** nếu nằm ngoài slice. Khi mục tiêu là security behavior, cần import cấu hình security hoặc dùng `@SpringBootTest` phù hợp.
- Một test WebFlux trả **401/403** thay vì 200 không chắc do route sai; có thể request bị filter chặn trước handler.
- `@Import` quá nhiều cấu hình vào slice có thể làm bài test gần thành full-context nhưng vẫn không chứng minh startup wiring thực. Chỉ import những bean phục vụ rủi ro đang kiểm.
- Khi mock service bằng `@MockitoBean`, bạn chỉ chứng minh controller/router mapping và cách dùng collaborator, **không** chứng minh service thật hoặc remote client.
- Filter chain của `bindToRouterFunction` được dựng theo mock WebFlux setup; **không tự bao gồm mọi filter Security của Spring Boot production**. Nếu filter/security là trọng tâm, tạo Spring context có filter chain được cấu hình phù hợp.

Trong các bài có cả annotated và functional routes, cùng một security policy có thể được áp cho hai endpoint. Hãy tạo test contract cho cả hai đường, không giả định test một endpoint là đủ cho endpoint còn lại.

## 13. Phiên bản Spring Boot 3.5 so với Boot 4.x

Các file runnable trong bài đã chọn **Spring Boot 3.5.0** để cố định import `@WebFluxTest`:

```java
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;
```

`@MockitoBean` là annotation từ **Spring Framework 6.2**, phù hợp Boot 3.5; annotation cũ `@MockBean` của Boot bị deprecated ở Boot 3.4 và bị loại bỏ ở Boot 4.0.

Trong **Spring Boot 4.x**, công cụ WebFlux test được tách vào module riêng như `spring-boot-webflux-test`, và package của `WebFluxTest` đã chuyển sang **`org.springframework.boot.webflux.test.autoconfigure.WebFluxTest`**. Dự án Boot 4 cần chọn test starter/module đúng dòng và đối chiếu JUnit/Reactive/JSON dependencies được quản lý; không copy nguyên import Boot 3.5 rồi chỉ đổi version parent.

**Cốt lõi API vẫn giữ nguyên:** annotated controller, RouterFunction, HandlerFunction, WebTestClient bind methods và yêu cầu phải import functional router vào `@WebFluxTest` khi cần. Khi nâng version, luôn kiểm dependency tree, official docs và response/error behavior theo version đang cài.

## 14. Bảng lỗi thường gặp

| Hiện tượng | Nguyên nhân có khả năng | Hướng sửa |
|---|---|---|
| `@WebFluxTest` trả 404 ở functional URL | RouterFunction không tự được quét vào slice | `@Import` router/handler hoặc dùng `bindToRouterFunction`/`@SpringBootTest` |
| `@WebFluxTest` không inject được service | Business `@Service` nằm ngoài slice | Cấp `@MockitoBean` hoặc bean nhỏ phù hợp mục tiêu |
| Test 200 nhưng production endpoint lỗi | Test bind controller/router trực tiếp, chưa chứng minh production wiring | Bổ sung full-context/HTTP integration test |
| Test trả 401/403 | Spring Security filter đang chặn hoặc test authentication thiếu | Cấu hình security test rõ, không tắt filter thiếu chủ đích |
| JSON body khác kỳ vọng | Record serialization, codecs, mapping/headers khác | Kiểm message converters/codecs và API response contract |
| HTTP test lỗi connect/refused | Server chưa start, dùng sai URL, gọi cổng ngoài | RANDOM_PORT, inject WebTestClient trỏ server thật |
| Functional handler không map request | Predicate GET/path sai, handler không đăng ký | Assert đúng method+path, kiểm RouterFunction bean trong context |
| `@WebFluxTest` compile lỗi khi lên Boot 4 | `WebFluxTest` đổi package/module | Dùng test module và import đúng Boot version |
| Test reactive chậm hoặc treo | Flux vô hạn, block()/sleep(), chưa cancel publisher | StepVerifier, timeout/cancel, không block event-loop |
| Hai implementation trả mã lỗi khác nhau | Annotated dùng framework resolver, functional tự tạo ServerResponse | Chuẩn hóa error contract, test cả hai nhánh |
| Mock service trả null/empty Mono bất ngờ | Stub chưa đúng lời gọi hoặc bị cache state | Stub input cụ thể, verify tương tác, cô lập mock từng test |
| Test giao dịch xanh nhưng data vẫn lưu | Request HTTP thật chạy ở server transaction khác | DB test + cleanup, không dựa vào test @Transactional |
| Dự án có MVC và WebFlux nhưng test chạy sai stack | Boot ưu tiên Servlet MVC khi cả hai starter hiện diện | Tách starter/classpath hoặc cấu hình web-application-type có chủ đích |

## 15. Checklist trước khi hoàn tất test WebFlux endpoint

- [ ] Tôi biết endpoint là **annotated controller** hay **RouterFunction/HandlerFunction**.
- [ ] Tôi chỉ rõ mục tiêu: route/handler đơn lẻ, WebFlux slice, full context hay HTTP socket thật.
- [ ] Tôi nhớ **`@WebFluxTest` không tự phát hiện RouterFunction**; cần import nếu kiểm trong slice.
- [ ] Với annotated slice, tôi dùng `@WebFluxTest(Controller.class)` và `WebTestClient` đúng.
- [ ] Với functional direct test, tôi dùng `WebTestClient.bindToRouterFunction(router)` và hiểu nó không kiểm Spring bean registration.
- [ ] Với functional slice, router/handler và collaborator được cung cấp chính xác bằng `@Import`/`@MockitoBean` hoặc config tương ứng.
- [ ] Với full HTTP integration, tôi dùng `@SpringBootTest(RANDOM_PORT)` và client được bind tới server của test, không hardcode port.
- [ ] Tôi kiểm status, JSON fields, missing input và ít nhất một negative path.
- [ ] Tôi biết assertion nào chỉ chứng minh mock response, assertion nào chứng minh service/DI thật.
- [ ] Nếu có security/filter, chúng được nạp và test đúng khi là phạm vi cần chứng minh.
- [ ] Với Flux/SSE, tôi quản lý hoàn tất/cancel/timeouts; không chờ vô hạn.
- [ ] Tôi không dùng WebTestClient thay cho StepVerifier khi phải kiểm tín hiệu reactive, và ngược lại.
- [ ] Tôi kiểm đúng package/module của **Spring Boot 3.5 hoặc Boot 4.x**.
- [ ] Đã chạy các test bằng build tool và phân biệt lỗi route/context, lỗi HTTP network và lỗi nghiệp vụ.

**Ghi nhớ:** annotated `@RestController` và functional `RouterFunction` cùng tạo HTTP endpoint WebFlux nhưng **được đăng ký khác nhau và cần test setup khác nhau**. `@WebFluxTest` thích hợp với controller annotations; `bindToRouterFunction` thích hợp với router trực tiếp; `@Import` cho phép router xuất hiện trong slice; `@SpringBootTest(RANDOM_PORT)` kiểm hai đường thật qua embedded server. **Luôn nêu rõ ranh giới mà mỗi test đã chứng minh.**

### Tài liệu chính thức

- [Spring Boot 3.5 — Testing Spring Boot Applications, Auto-configured Spring WebFlux Tests](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — `@WebFluxTest` Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/reactive/WebFluxTest.html)
- [Spring Framework — WebTestClient: Bind to Controller, Router Function, ApplicationContext, Server](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Spring Framework — WebFlux Functional Endpoints](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Boot 4 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
