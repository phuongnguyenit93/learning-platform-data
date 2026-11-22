# Filter Reactive và cấu hình phụ thuộc của slice

## 1. Vấn đề: test một WebFlux controller có đi qua filter như khi ứng dụng chạy thật không?

Trong Spring WebFlux, một HTTP request không nhất thiết đi thẳng vào `@RestController`. Trước khi handler được gọi, request có thể đi qua các **`WebFilter`** dùng cho correlation ID, phân quyền, kiểm soát tenant, ghi log, giới hạn truy cập hoặc bổ sung HTTP header. Một filter có thể **chặn request**, chỉnh sửa `ServerWebExchange`, gọi filter tiếp theo hoặc xử lý tín hiệu hoàn tất của chuỗi reactive.

Khi viết `@WebFluxTest`, Spring Boot tạo **test slice** với WebFlux infrastructure và những component được phép, thay vì tải toàn bộ application context. Vì vậy một test controller có thể xanh trong khi filter quan trọng bị thiếu, hoặc context không khởi tạo được vì filter có dependency là một `@Service`/configuration-properties bean vốn bị loại khỏi slice.

Ví dụ: ứng dụng yêu cầu header `X-Client-Id` và kiểm tra khách hàng qua `ClientAccessPolicy` trước khi cho phép GET `/api/quotes/Q-1`:

~~~text
HTTP GET /api/quotes/Q-1
  |
  | X-Client-Id: demo
  v
ClientGateWebFilter
  |
  +-- thiếu header ------> 400 Bad Request
  |
  +-- policy từ chối ----> 403 Forbidden
  |
  +-- policy cho phép ---> WebFilterChain.filter(exchange)
                             |
                             v
                         QuoteController
                             |
                             v
                         QuoteCatalog (mock)
                             |
                             v
                         200 + JSON, hoặc 404
~~~

Một bộ test có ý nghĩa phải chứng minh **đúng ranh giới**: filter chặn đúng đầu vào; request hợp lệ đi tới controller; dependency của controller/filter là những mock đã chủ động cung cấp; response thực sự có status/header/body theo contract.

**Bài tập này dùng Java 17, Spring Boot 3.5.x / Spring Framework 6.2, JUnit Jupiter, Reactor và `WebTestClient`.** Spring Boot 4.x đã sắp xếp lại một số module/package test; không copy nguyên import Boot 3.5 sang Boot 4 mà không kiểm tra dependency tương ứng.

## 2. WebFilter, WebFilterChain và Mono<Void>

Spring WebFlux dùng contract:

~~~java
public interface WebFilter {
    Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain
    );
}
~~~

Các kiểu quan trọng:

| Kiểu | Vai trò |
| --- | --- |
| `WebFilter` | Intercept một server-side HTTP exchange |
| `ServerWebExchange` | Request, response, attributes và thông tin ngữ cảnh của một exchange |
| `WebFilterChain` | Đại diện cho các filter tiếp theo và cuối cùng là `WebHandler` |
| `Mono<Void>` | Publisher biểu diễn quá trình xử lý bất đồng bộ và tín hiệu hoàn tất/lỗi/cancel |
| `WebTestClient` | Client dành cho test WebFlux bằng mock server hoặc server thật |
| `@WebFluxTest` | Spring Boot web slice chỉ tải hạ tầng và component liên quan |

Khác với code đồng bộ:

~~~java
// KHÔNG phải cách viết đúng cho filter reactive:
chain.filter(exchange).subscribe();
return Mono.empty();
~~~

Nếu tự gọi `subscribe()` rồi trả `Mono.empty()`, filter mất khả năng truyền tín hiệu hoàn tất, lỗi và cancellation theo chuỗi do framework quản lý; request có thể kết thúc sai thời điểm. **Hãy trả chính publisher từ chuỗi xử lý**, ví dụ `return chain.filter(exchange);`, hoặc compose bằng các toán tử Reactor.

Một WebFilter có ba hành vi chính:

~~~java
// 1. Cho đi tiếp:
return chain.filter(exchange);

// 2. Từ chối ngay (không gọi chain):
exchange.getResponse().setStatusCode(HttpStatus.FORBIDDEN);
return exchange.getResponse().setComplete();

// 3. Kiểm tra bất đồng bộ rồi mới quyết định:
return accessPolicy.isAllowed(clientId)
        .flatMap(allowed -> allowed
                ? chain.filter(exchange)
                : deny(exchange));
~~~

Đây là **các đoạn logic minh họa**, không phải một class Java độc lập. Đoạn cuối giả định `accessPolicy` trả `Mono<Boolean>` và có method `deny`. Nếu publisher có thể rỗng, cần quy định cách xử lý `Mono.empty()` rõ ràng; đừng để request tự kết thúc mà chưa gọi handler lẫn chưa trả status hợp lý.

### Filter có thể chỉnh sửa gì?

- Đọc `exchange.getRequest().getHeaders()` và URI.
- Ghi header vào `exchange.getResponse().getHeaders()` **trước khi response commit**.
- Đặt attribute qua `exchange.getAttributes().put(...)`.
- Chọn gọi `chain.filter(exchange)` một lần, hoặc trả response ngay.
- Dùng `doOnError`/`doFinally` để đo và ghi nhận tín hiệu xử lý; lưu ý `doFinally` được gọi cả khi cancel.
- Với request hoặc response body streaming, cần `ServerHttpRequestDecorator`/`ServerHttpResponseDecorator` và hiểu `DataBuffer` reference-count/lifecycle; không đọc body tùy tiện như String khi chưa có yêu cầu.

**Không lưu request state trong instance field của WebFilter** vì filter là bean singleton thường được nhiều request dùng đồng thời. Dùng biến cục bộ, exchange attributes hoặc Reactor Context để cô lập theo request.

## 3. @WebFluxTest chọn bean nào, bỏ bean nào?

`@WebFluxTest(QuoteController.class)` tập trung vào **annotated reactive controllers** và WebFlux infrastructure. Theo tài liệu Spring Boot 3.5, slice hỗ trợ các component chuyên web như `@Controller`, `@ControllerAdvice`, converter, `WebFluxConfigurer`; Javadoc `@WebFluxTest` còn liệt kê các kiểu hỗ trợ như `WebFilter` và `WebExceptionHandler` trong phạm vi filtered component scanning.

Tuy nhiên **đừng nhầm kiểu được cho phép với “mọi bean loại đó ở bất cứ đâu đều được tải”**:

- Một `@Component` có kiểu được filter quét cho phép có thể được phát hiện qua component scanning khi nó nằm trong package scan hợp lệ.
- Một `@Bean WebFilter` khai báo bên trong **lớp `@Configuration` riêng** không tự động được đưa vào slice chỉ vì return type là `WebFilter`; lớp configuration thường bị loại khỏi scanning slice.
- Service/repository thông thường và `@ConfigurationProperties` thường bị loại khỏi slice; controller hoặc filter phụ thuộc những bean đó có thể gây `UnsatisfiedDependencyException`.
- Custom `SecurityWebFilterChain` bean từ một `@Configuration` cũng **không được `@WebFluxTest` tự phát hiện** theo tài liệu Boot. Khi mục tiêu là kiểm tra security chain thật, import config hoặc dùng `@SpringBootTest`.

Vì những khác biệt theo nguồn bean và phiên bản, ví dụ trong bài **đăng ký filter bằng `@Import(ClientGateWebFilter.class)`**, filter cố ý **không có `@Component`**. Điều này giúp kiểm soát chính xác test slice, tránh đoán Spring có tìm thấy filter hay không.

### Ba phương án phổ biến để đưa dependency vào slice

| Thứ cần cho test | Cách cung cấp | Ý nghĩa |
| --- | --- | --- |
| Bean thật chứa logic đang kiểm tra, ví dụ filter | `@Import(ClientGateWebFilter.class)` | Chạy filter thực và intercept exchange |
| Collaborator bên ngoài slice, ví dụ `ClientAccessPolicy` | `@MockitoBean ClientAccessPolicy policy;` | Thay/đăng ký Spring bean mock để trả quyết định xác định |
| Config nhỏ có `@Bean` cần chạy thật | `@Import(FilterTestConfiguration.class)` | Nạp những bean `@Bean` được khai báo có chủ đích |
| Configuration properties cho filter | `@EnableConfigurationProperties(GateProperties.class)` + test properties | Binder của Boot tạo đúng properties bean |
| Muốn chạy mọi bean, security config và wiring đa tầng | `@SpringBootTest` | Test tích hợp rộng, không còn là web slice hẹp |

`@MockitoBean` là API Spring Framework 6.2+, có trong Spring Boot 3.4/3.5; đừng dùng `@Mock` thuần rồi mong nó thay bean trong Spring context. `@MockBean` đời trước của Spring Boot đã deprecated ở Boot 3.4, và không phải alias hoàn toàn tương đương trong mọi tình huống.

## 4. Ví dụ đầy đủ: kiểm tra filter, controller và các dependency trong một slice

Ta thiết kế một API đơn giản:

- `GET /api/quotes/{id}` tra quote qua `QuoteCatalog` và trả JSON khi tìm thấy.
- `ClientGateWebFilter` yêu cầu `X-Client-Id` trước khi truy cập route.
- Nếu thiếu/blank header: **400**, không gọi policy và không gọi catalog.
- Nếu policy trả `false` hoặc `Mono.empty()`: **403**, không gọi catalog.
- Nếu policy trả `true`: filter thêm `X-Gate-Checked: true` rồi gọi chain.
- Nếu quote không tồn tại: controller trả **404**. Filter **không biến 404 thành 403** chỉ vì service trả empty.

Các test chạy bằng **mock WebFlux server**; không mở cổng TCP, không gọi service mạng, không cần database.

### 4.1. Cấu hình dự án Java 17

Trong dự án Spring Boot **3.5.x** dùng Gradle Groovy DSL, phần dependency và test task liên quan trong `build.gradle` là:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Đây **không phải toàn bộ file build**. Dự án còn cần plugin Spring Boot 3.5.x, dependency management, repositories và JDK/toolchain 17+. **Không** thêm `spring-boot-starter-web` (Servlet MVC) vào demo để tránh nhầm loại web application. Dòng `starter-test` cung cấp JUnit Jupiter, Mockito và Spring Boot Test; `starter-webflux` đưa Reactor/WebFlux lên classpath.

Cấu trúc tệp:

~~~text
src/main/java/com/example/fluxtest/
  FluxTestApplication.java
  QuoteView.java
  QuoteCatalog.java
  ClientAccessPolicy.java
  QuoteController.java
  ClientGateWebFilter.java
src/test/java/com/example/fluxtest/
  QuoteControllerFilterSliceTest.java
~~~

### 4.2. Lớp ứng dụng để Spring Boot tìm cấu hình gốc

**`src/main/java/com/example/fluxtest/FluxTestApplication.java`:**

~~~java
package com.example.fluxtest;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FluxTestApplication {
    public static void main(String[] args) {
        SpringApplication.run(FluxTestApplication.class, args);
    }
}
~~~

`@WebFluxTest` dùng cấu hình ứng dụng gốc để khởi tạo slice, nhưng **không gọi `main`** và không nạp mọi bean như một full `@SpringBootTest`.

### 4.3. Model và hai collaborator

**`src/main/java/com/example/fluxtest/QuoteView.java`:**

~~~java
package com.example.fluxtest;

public record QuoteView(String id, String text) {
}
~~~

**`src/main/java/com/example/fluxtest/QuoteCatalog.java`:**

~~~java
package com.example.fluxtest;

import reactor.core.publisher.Mono;

public interface QuoteCatalog {
    Mono<QuoteView> findById(String id);
}
~~~

**`src/main/java/com/example/fluxtest/ClientAccessPolicy.java`:**

~~~java
package com.example.fluxtest;

import reactor.core.publisher.Mono;

public interface ClientAccessPolicy {
    Mono<Boolean> isAllowed(String clientId);
}
~~~

Hai collaborator là interface vì trong bài này ta muốn test **wiring và hành vi WebFlux controller/filter**, không phải cách truy vấn quote hay xác thực khách hàng từ hệ thống thật. Trong production có thể có các bean implement gọi Redis, database hoặc HTTP nonblocking; trong slice test chúng được cung cấp bằng mock.

### 4.4. Controller thật dùng Mono

**`src/main/java/com/example/fluxtest/QuoteController.java`:**

~~~java
package com.example.fluxtest;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/quotes")
public class QuoteController {
    private final QuoteCatalog catalog;

    public QuoteController(QuoteCatalog catalog) {
        this.catalog = catalog;
    }

    @GetMapping(value = "/{id}", produces = MediaType.APPLICATION_JSON_VALUE)
    public Mono<QuoteView> find(@PathVariable String id) {
        return catalog.findById(id)
                .switchIfEmpty(Mono.error(
                        new ResponseStatusException(
                                HttpStatus.NOT_FOUND, "Quote not found"
                        )
                ));
    }
}
~~~

Controller không biết gì về `X-Client-Id`. Đó là **cross-cutting concern** của filter. Một response 404 chỉ xuất hiện khi request đã tới controller, catalog trả `Mono.empty()` và `switchIfEmpty` chuyển thành lỗi HTTP 404. Đừng mặc định một `Mono.empty()` ở mọi handler tự động có nghĩa HTTP 404: hành vi phải được định nghĩa.

### 4.5. WebFilter thật, không block và không subscribe

**`src/main/java/com/example/fluxtest/ClientGateWebFilter.java`:**

~~~java
package com.example.fluxtest;

import java.util.Objects;

import org.springframework.http.HttpStatus;
import org.springframework.web.server.ServerWebExchange;
import org.springframework.web.server.WebFilter;
import org.springframework.web.server.WebFilterChain;

import reactor.core.publisher.Mono;

public final class ClientGateWebFilter implements WebFilter {
    private final ClientAccessPolicy policy;

    public ClientGateWebFilter(ClientAccessPolicy policy) {
        this.policy = Objects.requireNonNull(policy, "policy");
    }

    @Override
    public Mono<Void> filter(
            ServerWebExchange exchange,
            WebFilterChain chain
    ) {
        String clientId = exchange.getRequest()
                .getHeaders()
                .getFirst("X-Client-Id");

        if (clientId == null || clientId.isBlank()) {
            exchange.getResponse().setStatusCode(HttpStatus.BAD_REQUEST);
            return exchange.getResponse().setComplete();
        }

        return policy.isAllowed(clientId)
                .defaultIfEmpty(false)
                .flatMap(allowed -> {
                    if (!allowed) {
                        exchange.getResponse()
                                .setStatusCode(HttpStatus.FORBIDDEN);
                        return exchange.getResponse().setComplete();
                    }

                    exchange.getResponse()
                            .getHeaders()
                            .set("X-Gate-Checked", "true");

                    return chain.filter(exchange);
                });
    }
}
~~~

Giải thích:

1. Filter đọc header nhưng **không sửa dữ liệu chia sẻ**, chỉ dùng biến `clientId` cục bộ.
2. Thiếu/blank client ID → trả `setComplete()` với status 400, **không gọi `chain.filter`**.
3. `policy.isAllowed(clientId)` trả `Mono<Boolean>`. Dùng `defaultIfEmpty(false)` để tránh trường hợp policy hoàn tất rỗng và filter lặng lẽ không đưa request vào chain.
4. Policy từ chối → status 403, kết thúc exchange.
5. Policy cho phép → set header trước khi downstream có thể commit response, rồi **return** `chain.filter(exchange)`.
6. Không dùng `block()`, `subscribe()` hoặc `Thread.sleep()` trong filter.

Code không gắn `@Component` và cũng không khai báo `@Bean` ở production. **Đây là lựa chọn demo có chủ đích:** test sẽ đăng ký filter bằng `@Import`; khi đưa vào ứng dụng thật, hãy đăng ký bean filter qua `@Component` hoặc một `@Configuration` có `@Bean`, tùy cách tổ chức project. Nếu quên đăng ký khi chạy thật, filter sẽ **không** được áp dụng; web slice test không thể chứng minh wiring production khi khác cấu hình.

### 4.6. Test WebFlux slice: mock dependency, import filter và assert toàn bộ đường đi

**`src/test/java/com/example/fluxtest/QuoteControllerFilterSliceTest.java`:**

~~~java
package com.example.fluxtest;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;

import reactor.core.publisher.Mono;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@WebFluxTest(QuoteController.class)
@Import(ClientGateWebFilter.class)
class QuoteControllerFilterSliceTest {
    @Autowired
    WebTestClient client;

    @MockitoBean
    QuoteCatalog catalog;

    @MockitoBean
    ClientAccessPolicy policy;

    @Test
    void allowedClient_whenQuoteExists_getsJsonAndFilterHeader() {
        when(policy.isAllowed("demo")).thenReturn(Mono.just(true));
        when(catalog.findById("Q-1"))
                .thenReturn(Mono.just(new QuoteView("Q-1", "Hello")));

        client.get()
                .uri("/api/quotes/{id}", "Q-1")
                .header("X-Client-Id", "demo")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals(
                        "X-Gate-Checked", "true"
                )
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON
                )
                .expectBody()
                .jsonPath("$.id").isEqualTo("Q-1")
                .jsonPath("$.text").isEqualTo("Hello");

        verify(policy).isAllowed("demo");
        verify(catalog).findById("Q-1");
    }

    @Test
    void missingClientHeader_isRejectedBeforeDependencies() {
        client.get()
                .uri("/api/quotes/Q-1")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody().isEmpty();

        verifyNoInteractions(policy, catalog);
    }

    @Test
    void deniedClient_isForbiddenBeforeController() {
        when(policy.isAllowed("blocked"))
                .thenReturn(Mono.just(false));

        client.get()
                .uri("/api/quotes/Q-1")
                .header("X-Client-Id", "blocked")
                .exchange()
                .expectStatus().isForbidden()
                .expectBody().isEmpty();

        verify(policy).isAllowed("blocked");
        verifyNoInteractions(catalog);
    }

    @Test
    void emptyPolicyDecision_isRejectedRatherThanBypassingFilter() {
        when(policy.isAllowed("unknown"))
                .thenReturn(Mono.empty());

        client.get()
                .uri("/api/quotes/Q-1")
                .header("X-Client-Id", "unknown")
                .exchange()
                .expectStatus().isForbidden();

        verify(policy).isAllowed("unknown");
        verifyNoInteractions(catalog);
    }

    @Test
    void allowedClient_whenQuoteMissing_stillGets404FromController() {
        when(policy.isAllowed("demo")).thenReturn(Mono.just(true));
        when(catalog.findById("missing")).thenReturn(Mono.empty());

        client.get()
                .uri("/api/quotes/missing")
                .header("X-Client-Id", "demo")
                .exchange()
                .expectStatus().isNotFound()
                .expectHeader().valueEquals(
                        "X-Gate-Checked", "true"
                );

        verify(policy).isAllowed("demo");
        verify(catalog).findById("missing");
    }
}
~~~

Bộ năm test kiểm tra **filter thật chạy trong chuỗi WebFlux**:

| Ca | Filter | Catalog mock | Phản hồi |
| --- | --- | --- | --- |
| Có client hợp lệ, tìm thấy quote | Gọi policy → cho tiếp → thêm header | Được gọi | 200, header và JSON đúng |
| Thiếu header | Chặn ngay | Không được gọi | 400, body rỗng |
| Policy trả false | Chặn sau bước kiểm tra | Không được gọi | 403, body rỗng |
| Policy trả `Mono.empty()` | Mặc định từ chối | Không được gọi | 403 |
| Policy cho phép nhưng quote không có | Cho request đi tiếp | Gọi và trả empty | 404 do controller quyết định |

**Vì sao cần cả `verify`?** Chỉ kiểm tra status 403 chưa chứng minh filter chặn **trước controller**; `verifyNoInteractions(catalog)` ràng buộc đúng hành vi short-circuit. Ngược lại, 200 + JSON + header filter cho thấy request hợp lệ đi qua filter và tới controller.

`@MockitoBean` tạo mock là **bean trong Spring context**, không phải chỉ một field Mockito độc lập. Đăng ký `@Import(ClientGateWebFilter.class)` bảo đảm filter thật có mặt; constructor của nó nhận `ClientAccessPolicy` mock, còn controller nhận `QuoteCatalog` mock.

### 4.7. Chạy test

Từ thư mục dự án có Gradle Wrapper:

~~~bash
./gradlew test --tests "com.example.fluxtest.QuoteControllerFilterSliceTest"
~~~

Trên Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests "com.example.fluxtest.QuoteControllerFilterSliceTest"
~~~

Ví dụ có một lớp test với **năm `@Test`**. Khi dependency Spring Boot 3.5.x, JUnit Jupiter/Mockito và WebFlux đúng như mô tả, năm test được kỳ vọng PASS. Không có `System.out.println`, vì vậy **mã ứng dụng không có stdout cố định**; log Gradle/JUnit/Spring phụ thuộc cấu hình. Không chạy tệp test bằng `javac` thuần nếu không cung cấp classpath Spring/JUnit.

**Giới hạn:** ví dụ minh họa filter được import vào **test**. Nó chứng minh behavior của filter trong WebFlux slice, nhưng không tự chứng minh ứng dụng production đã đăng ký `ClientGateWebFilter`. Để kiểm tra production wiring, thêm một test integration ở phần thích hợp hoặc đăng ký bean thật trong cấu hình production và test cấu hình đó.

## 5. Hai cách đăng ký WebFilter: component và @Bean

Spring WebFlux sử dụng các bean `WebFilter` tồn tại trong `ApplicationContext` để xử lý request. Vì thế, cách tạo bean quyết định liệu filter có sẵn trong slice hay không.

### 5.1. @Component filter

~~~java
@Component
public class ClientGateWebFilter implements WebFilter {
    // filter(...) và constructor như phần 4.
}
~~~

Đây chỉ là **đoạn minh họa annotation**, không phải tệp class hoàn chỉnh; `@Component` cần import từ `org.springframework.stereotype.Component`. Khi filter là component và nằm trong phạm vi scan, `@WebFluxTest` có thể phát hiện theo filter của Boot; tài liệu Javadoc Boot 3.5 liệt kê `WebFilter` trong các kiểu có thể được giữ lại. **Không mặc định mọi @Component nằm trong mọi package đều được nạp**; thành phần vẫn chịu component scan, type exclude filters và các filter include/exclude được chỉ định.

Nếu đã dùng `@Component` và filter thật sự được slice quét, **đừng import cùng filter lần nữa một cách thiếu kiểm soát**, vì nguy cơ định nghĩa bean/instance trùng hoặc trạng thái cấu hình khó hiểu. Hãy quyết định rõ **một** cách cung cấp bean.

### 5.2. @Configuration chứa @Bean

~~~java
@Configuration(proxyBeanMethods = false)
public class GateConfiguration {
    @Bean
    WebFilter clientGateWebFilter(ClientAccessPolicy policy) {
        return new ClientGateWebFilter(policy);
    }
}
~~~

Đây là **đoạn class minh họa**, cần import `@Configuration`, `@Bean`, `WebFilter` và các class cùng package. Một class `@Configuration` tùy biến như `GateConfiguration` thường không được slice scan mặc định. Nếu muốn test cấu hình bean đó thật, dùng:

~~~java
@WebFluxTest(QuoteController.class)
@Import(GateConfiguration.class)
class QuoteWithGateConfigTest {
    // @MockitoBean cho ClientAccessPolicy và QuoteCatalog.
}
~~~

Đây là **skeleton**, chưa phải test chạy độc lập. Khi chọn cách này, **bỏ `@Import(ClientGateWebFilter.class)`** ở ví dụ chính; nếu không, có thể tạo hai filter. Một configuration chứa thêm datasource/client/queue không liên quan cũng có thể kéo theo nhiều dependency; hãy **import cấu hình nhỏ đúng phạm vi**.

### 5.3. Filter dùng cấu hình @ConfigurationProperties

Nếu filter cần cấu hình như chế độ bật/tắt hoặc timeout:

~~~java
@ConfigurationProperties(prefix = "app.gate")
public record GateProperties(boolean enabled) {
}
~~~

Record trên là **tệp riêng** với import `org.springframework.boot.context.properties.ConfigurationProperties`. Slice mặc định không scan mọi `@ConfigurationProperties`. Muốn bean tồn tại trong `@WebFluxTest`:

~~~java
@WebFluxTest(
        controllers = QuoteController.class,
        properties = "app.gate.enabled=true"
)
@EnableConfigurationProperties(GateProperties.class)
@Import(ClientGateWebFilter.class)
class QuoteWithPropertiesTest {
    // Các mock/field/test phù hợp với constructor thực tế.
}
~~~

Ví dụ là skeleton có chủ đích. Với code `ClientGateWebFilter` của phần 4 chưa nhận `GateProperties`, annotation này chỉ minh họa cách **đăng ký properties bean**, không tạo ra behavior bật/tắt mới. Chỉ assert enabled/disabled khi filter đã thực sự sử dụng thuộc tính đó.

**Không dùng `@TestPropertySource` hoặc `@WebFluxTest(properties=...)` rồi cho rằng property bean tự xuất hiện**; có test property source khác với có `@ConfigurationProperties` bean được đăng ký.

## 6. Cấu hình phụ thuộc của slice: mock, import hay full context?

Trước một lỗi kiểu:

~~~text
UnsatisfiedDependencyException:
No qualifying bean of type 'ClientAccessPolicy' available
~~~

hãy xét **đối tượng cần kiểm thử**:

- **Mục tiêu là filter và reactive HTTP boundary:** Giữ filter/controller thật; dùng `@MockitoBean ClientAccessPolicy` cho policy ngoài slice. Đó là cách ví dụ chính sử dụng.
- **Mục tiêu là policy implementation:** Không mock policy; import implementation thật cùng những dependency cần thiết hoặc viết unit test riêng cho policy.
- **Mục tiêu là config chứa một `@Bean` filter:** Import config đúng phạm vi. Không import toàn bộ package/config production ngoài nhu cầu.
- **Mục tiêu là Spring Security wiring thực tế:** Import custom security configuration và dùng `spring-security-test` để tạo principal, JWT/CSRF thích hợp; hoặc full `@SpringBootTest`.
- **Mục tiêu là end-to-end controller → service → repository:** Cân nhắc `@SpringBootTest` thay vì cố biến `@WebFluxTest` thành full integration test bằng hàng chục `@Import`.

| Công cụ | Nhiệm vụ | Rủi ro khi dùng sai |
| --- | --- | --- |
| `@MockitoBean` | Tạo/thay bean mock ở Spring context | Nếu mock chính filter cần test, filter thật sẽ không chạy |
| `@Import(Foo.class)` | Nhập bean/config thật vào context | Có thể kéo thêm dependency ngoài slice |
| `@EnableConfigurationProperties(FooProperties.class)` | Đăng ký type cấu hình cho binder | Không thay thế mock/bean service |
| `@WebFluxTest(includeFilters = ...)` | Nới điều kiện scanning có chọn lọc | Khó hiểu nếu không biết bean được scan theo nguồn nào |
| `@WebFluxTest(excludeFilters = ...)` | Loại component không cần trong slice | Có thể vô tình bỏ filter/security đang cần test |
| `@SpringBootTest` | Nạp tích hợp rộng theo cấu hình ứng dụng | Chậm hơn, phạm vi lớn hơn bài test filter đơn lẻ |

### @Import có nghĩa là filter tự động chạy trong mọi trường hợp?

Không. `@Import` đăng ký bean với context. Filter được dùng khi nó là `WebFilter` bean thuộc **WebFlux server chain thực sự được xây dựng**. Nếu bạn dùng một `WebTestClient.bindToController(new QuoteController(...))` thuần mà không kết nối Spring application context, nó không tự phát hiện các bean filter bạn import vào một test context khác.

Vì vậy để test Spring bean wiring, ví dụ chính inject `WebTestClient` được **`@WebFluxTest` auto-configure theo context**. Nếu tự xây client bằng `bindToController`, cần cấu hình/bind thêm các filter theo API tương ứng, không suy ra bean context được đưa vào tự động.

## 7. Filter order và cách đọc đúng vị trí của Spring Security

Khi nhiều `WebFilter` tồn tại, Spring WebFlux có **thứ tự filter**. Có thể dùng `org.springframework.core.Ordered` hoặc `@Order`:

~~~java
@Order(Ordered.HIGHEST_PRECEDENCE + 100)
public final class RequestTraceWebFilter implements WebFilter {
    @Override
    public Mono<Void> filter(ServerWebExchange exchange,
                             WebFilterChain chain) {
        exchange.getResponse().getHeaders()
                .add("X-Trace", "observed");
        return chain.filter(exchange);
    }
}
~~~

Đây là **class minh họa**, cần đúng imports và đăng ký bean; không phải phần cần thêm vào ví dụ chính. Giá trị order **nhỏ hơn** được ưu tiên chạy trước ở pha vào; sau `chain.filter(...)`, các toán tử completion/termination có thể quan sát pha ra của chuỗi reactive.

Spring Boot WebFlux có một số thứ tự filter hệ thống được định nghĩa. Ví dụ WebFilterChainProxy của Spring Security thường có order `-100` trong cấu hình Boot, nhưng **không lấy số này làm hằng số vĩnh viễn cho mọi phiên bản và mọi custom filter**. Chọn order dựa vào yêu cầu thực tế và kiểm thử tương tác với security nếu có.

### Vì sao filter chạy trước security có thể là vấn đề?

Nếu filter kiểm tra tenant/correlation ID và trả lỗi khác biệt trước Spring Security, người dùng chưa xác thực có thể nhận khác status mong đợi. Ngược lại, nếu authentication phải được thiết lập trước khi filter đọc principal, cần đặt filter **sau** security hoặc sử dụng cơ chế security filter phù hợp. Với authorization, ưu tiên Spring Security `SecurityWebFilterChain` thay vì tự dựng logic security tùy biến trong `WebFilter`.

Test có thể kiểm tra đường đi bằng kết quả HTTP, không nhất thiết assert mỗi lời gọi nội bộ. Nếu order là hợp đồng quan trọng, tạo các filter test có trace có quản lý concurrency hoặc test trực tiếp những ảnh hưởng quan sát được.

### Response header và commit

Header phải được đặt **trước khi response commit**. Trong ví dụ chính, `X-Gate-Checked` được set trước `chain.filter(exchange)`. Nếu dùng `doFinally(...)` để set HTTP header **sau khi downstream hoàn tất**, response có thể đã được commit nên header không có hiệu lực; `doFinally` phù hợp metrics/tracing, không phải nơi an toàn để sửa response headers.

Khi cần hook ngay trước commit, xem `exchange.getResponse().beforeCommit(...)`, nhưng callback phải giữ tính reactive và không block. Không dùng synchronous assumptions cho HTTP body streaming.

## 8. SecurityWebFilterChain khác custom WebFilter ở điểm nào?

Spring Security cho WebFlux xây dựng một `SecurityWebFilterChain` để áp dụng authentication, authorization, CSRF, session, OAuth2... theo cấu hình. Trong WebFlux, hạ tầng Spring Security hoạt động thông qua `WebFilterChainProxy` và nhiều filter chuyên dụng.

**Boot docs nêu rõ:** `@WebFluxTest` không tự phát hiện một custom `@Bean SecurityWebFilterChain` nằm trong cấu hình ứng dụng riêng. Muốn kiểm thử **đúng custom security rule**, phải import configuration định nghĩa bean đó vào slice, hoặc dùng full `@SpringBootTest`.

Một cấu hình security minh họa:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain springSecurityFilterChain(
            ServerHttpSecurity http
    ) {
        return http
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public/**").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
~~~

**Đây là một class minh họa riêng**, yêu cầu dependency `spring-boot-starter-security` và imports: `@Configuration`, `@Bean`, `@EnableWebFluxSecurity`, `SecurityWebFilterChain`, `ServerHttpSecurity`, `Customizer`. Đoạn `csrf(...disable)` chỉ để minh họa API; **không dùng tắt CSRF như cấu hình production mặc định** nếu ứng dụng có browser/session hoặc yêu cầu bảo vệ CSRF.

Trong test có security:

~~~java
@WebFluxTest(QuoteController.class)
@Import(ApiSecurityConfiguration.class)
class QuoteSecuritySliceTest {
    // Mock dependency và assertion về 401/403/auth theo hợp đồng.
}
~~~

Đây là skeleton; nếu cần endpoint chạy trong cả custom filter và security, phải đưa cả hai vào slice theo phạm vi kiểm thử. Không được suy ra “đã có `@WebFluxTest` là đã test toàn bộ security config production”.

### WebTestClient và spring-security-test

Để kiểm tra authenticated request trong WebFlux test, Spring Security cung cấp helper như `SecurityMockServerConfigurers.mockUser(...)` và `mockJwt()`, với dependency:

~~~groovy
testImplementation 'org.springframework.security:spring-security-test'
~~~

Có thể dùng client phù hợp với Spring Security test support, ví dụ:

~~~java
WebTestClient authenticated = client.mutateWith(
        SecurityMockServerConfigurers.mockUser("tester")
);
~~~

Đây là **đoạn test minh họa**, cần import `WebTestClient` và `SecurityMockServerConfigurers`. Nó không chứng minh custom security configuration đã được import; chỉ mô phỏng danh tính trong request test khi hạ tầng tương ứng hiện diện.

Nếu test expect `401` nhưng nhận `400` từ custom filter thiếu header, đó có thể là **hậu quả của order**. Test phải cung cấp đúng request headers, principal và cấu hình filter/security trước khi suy luận lỗi.

## 9. WebFilter, ExchangeFilterFunction và servlet Filter không giống nhau

Những tên này dễ nhầm vì đều chứa “Filter”:

| Loại | Nơi hoạt động | Khi nào dùng |
| --- | --- | --- |
| `org.springframework.web.server.WebFilter` | **Server-side Spring WebFlux** HTTP exchanges | Kiểm tra/biến đổi request hoặc response trước/sau WebHandler |
| `org.springframework.web.reactive.function.client.ExchangeFilterFunction` | **Client-side WebClient** outbound requests | Thêm token/log/retry/tracing cho request do ứng dụng gửi ra |
| `jakarta.servlet.Filter` | Servlet stack / Spring MVC | Intercept HTTP theo Servlet API, không phải WebFlux server chain |
| `SecurityWebFilterChain` | Spring Security WebFlux | Authentication/authorization chain reactive |
| `HandlerFilterFunction` | Functional routing WebFlux | Cross-cutting behavior gắn với RouterFunction/HandlerFunction |

Một `ExchangeFilterFunction` cài trên `WebClient.builder().filter(...)` **không tự intercept** inbound request `WebTestClient.get().uri("/api/...")` vào server. Ngược lại, một `WebFilter` không tự động áp dụng cho HTTP request outbound của `WebClient`.

**Test sai phạm vi thường gặp:** muốn test server-side header filter nhưng chỉ cấu hình filter trong client; response body controller vẫn đúng và tưởng filter server đã được kiểm thử. Hãy assert header do **server** thêm và bảo đảm bean `WebFilter` nằm trong server chain.

## 10. Functional RouterFunction và giới hạn của WebFlux slice

`@WebFluxTest` được thiết kế chủ yếu cho annotated controllers. Spring Boot nêu rõ nó **không tự phát hiện đầy đủ routes được đăng ký bằng functional WebFlux framework**. Nếu ứng dụng dùng `RouterFunction<ServerResponse>`:

- Dùng `WebTestClient.bindToRouterFunction(route).build()` cho test router/handler thuần, khi không cần Spring bean wiring.
- Hoặc `@Import` router/handler config liên quan vào context của `@WebFluxTest` nếu phạm vi hỗ trợ.
- Hoặc chuyển sang `@SpringBootTest` khi route và filter/security phải hoạt động theo cách wiring ứng dụng đầy đủ.

Đừng test `@RestController` rồi kết luận tất cả functional routes đã được bảo vệ bởi cùng filter. Bộ test cần bao phủ **đường request thực tế** mà production sử dụng.

## 11. Đo và kiểm soát độ ổn định của các test reactive

### Không dùng block trong luồng xử lý

`Mono.block()` trong filter/controller đi ngược thiết kế nonblocking và có thể gây lỗi hoặc nghẽn event loop. Với dependency nonblocking, compose kết quả bằng `flatMap`, `map` và `onErrorResume` có kiểm soát.

**Tuy nhiên, không phải mọi lỗi đều nên biến thành status 200/403.** Nếu `policy.isAllowed(...)` ném exception hoặc trả `Mono.error(...)`, contract phải quy định fail-closed, trả 5xx, hoặc do global exception handler xử lý. Ví dụ chính xử lý `Mono.empty()` thành từ chối, nhưng **không âm thầm nuốt `Mono.error()`**. Khi thiết kế production, bổ sung logging/metrics và chính sách lỗi rõ ràng.

### Gắn header khi response còn sửa được

Đừng đặt response header trong callback `doFinally` của publisher nếu đã có khả năng downstream commit response. Đặt trước chain hoặc sử dụng `beforeCommit` theo đúng nhu cầu.

### Không dùng biến static để ghi trạng thái giữa nhiều test

`WebFilter` thường là singleton của Spring context. Nếu ghi một `static List<String> traces` từ nhiều request và chạy JUnit song song, dữ liệu các request dễ trộn, còn listener/MockMvc test khác có thể làm bẩn state. Dùng exchange attributes, Reactor context hoặc recorder thread-safe có scoping rõ.

### Stubbing riêng cho từng test

`@MockitoBean` của Spring TestContext có cơ chế reset mock theo lifecycle test. **Không phụ thuộc** lời gọi hoặc stub do test trước để lại. Các ca trong ví dụ luôn stub riêng và kiểm tra đúng tương tác.

### Context cache không có nghĩa filter được chia sẻ sai cách

Hai lớp `@WebFluxTest` khác `@Import`, `@MockitoBean`, profiles hoặc properties có thể có cache key khác nhau. Điều này là đúng vì WebFlux chain của chúng có thể khác. Đừng xóa filter cần test chỉ để đạt nhiều cache hit hơn.

### Kiểm tra status và header trước khi đi sâu vào nội bộ

Khi test cho phép client, assert 200, header do filter thêm và JSON body; khi từ chối, assert 400/403 và catalog không tương tác. Chỉ assert implementation detail như số lần subscribe nếu đó thực sự là hợp đồng cần bảo vệ.

## 12. Tình huống mở rộng: @Order, exception, CORS và body stream

| Tình huống | Test nên kiểm tra | Cảnh báo |
| --- | --- | --- |
| Nhiều filter | Filter order và status/header quan sát được | Đừng dựa vào thứ tự component scan ngẫu nhiên |
| Security + custom filter | 401/403/200 theo principal và header | Custom SecurityWebFilterChain cần được import nếu muốn kiểm đúng config |
| Exception từ policy | Lỗi được propagate/map đúng hợp đồng | Không để publisher lỗi bị nuốt hoặc request treo |
| CORS preflight (OPTIONS) | `Access-Control-Allow-Origin`/method/header đúng origin hợp lệ | CORS trong Spring Security/WebFlux cần thứ tự thích hợp |
| Request/response streaming body | Không mất buffer, không leak, không block | Có thể cần decorator và test streaming/backpressure riêng |
| Filter ghi metrics | Một exchange tương ứng metric sau complete/error/cancel | `doFinally` có thể chạy cả khi cancellation |
| Data-dependent feature gate | Bật/tắt filter dựa config được bind trong slice | @ConfigurationProperties bean phải được đăng ký |
| Timeout | Request bị giới hạn thời gian theo quy định | Dùng `StepVerifier.withVirtualTime` cho publisher thuần nếu phù hợp, không đồng nhất với full HTTP latency |

Các trường hợp streaming/backpressure và bảo mật lớn hơn một slice controller thông thường. Nếu lỗi nằm ở toàn bộ server connector, TLS/proxy hoặc network socket thực, phải nâng phạm vi test lên integration/end-to-end với server thật.

## 13. Những lỗi thường gặp và cách sửa

1. **Gắn `@WebFluxTest` và nghĩ mọi bean production đều có mặt.** Slice loại phần lớn service/repository/config tùy biến. **Sửa:** mock dependency ngoài slice hoặc import đúng config có chủ đích.
2. **Filter khai báo bằng `@Bean` trong class `@Configuration` nhưng không import.** Controller test chạy mà không đi qua custom filter. **Sửa:** `@Import(GateConfiguration.class)` hoặc kiểm tra đường đăng ký phù hợp.
3. **Đưa filter thật vào test rồi lại `@MockitoBean` chính filter.** Không còn kiểm tra logic filter. **Sửa:** chỉ mock `ClientAccessPolicy`/dependency ngoài phạm vi.
4. **Dùng `@Mock` thay vì `@MockitoBean` cho constructor dependency của Spring bean.** Spring context không có bean mock. **Sửa:** chọn đúng cơ chế bean override.
5. **Không gọi `chain.filter(exchange)` ở nhánh cho phép.** Controller không chạy dù policy cho phép. **Sửa:** return đúng publisher từ chain.
6. **Gọi `subscribe()` bên trong filter.** Chuỗi tín hiệu tách khỏi framework; response/error timing không còn nhất quán. **Sửa:** compose và return `Mono<Void>`.
7. **Không quy định `Mono.empty()` từ policy.** Request có thể kết thúc bất thường hoặc không được xử lý đúng. **Sửa:** áp dụng `defaultIfEmpty(false)` hoặc explicit error rule.
8. **Đặt header sau `chain.filter` trong `doFinally`.** Response có thể đã commit. **Sửa:** set trước chain hoặc `beforeCommit`.
9. **Kiểm tra 403 nhưng không xác nhận controller chưa chạy.** Status có thể đến từ một filter/security khác. **Sửa:** kiểm tra dependency interaction và config test.
10. **Nhầm `@WebFluxTest` với `@WebMvcTest`.** Khác dispatcher, filter type và test infrastructure. **Sửa:** chọn đúng stack, dùng `WebTestClient` cho reactive slice.
11. **Giả định custom `SecurityWebFilterChain` tự được quét.** Boot docs nói cần import hoặc full context. **Sửa:** đưa cấu hình security thực vào test khi cần.
12. **Tắt security chỉ để test xanh.** Che lấp hành vi quan trọng. **Sửa:** dùng spring-security-test và assertions đúng role/CSRF/JWT.
13. **Giữ state mutable trong singleton filter.** Request/test song song gây race hoặc cross-request leakage. **Sửa:** biến cục bộ, exchange attributes, thread-safe recorder.
14. **Import toàn bộ config production vào slice.** Test chậm và thiếu bean khác ngoài ý muốn. **Sửa:** import cấu hình nhỏ hoặc nâng lên `@SpringBootTest` nếu cần tích hợp rộng.
15. **Chỉ test controller được gọi, không test filter.** Thiếu test nhánh reject và header. **Sửa:** có ít nhất một ca allow, một ca reject, một ca thiếu header.
16. **Tưởng `WebTestClient` client-side filter là server `WebFilter`.** Đã lắp nhầm phía. **Sửa:** đặt filter vào Spring WebFlux server context hoặc client outbound tùy mục đích.
17. **Test functional routes bằng annotated controller slice rồi nghĩ đủ.** Functional RouterFunction có quy tắc registration riêng. **Sửa:** bind route/import đúng router hoặc full context.
18. **Assert message lỗi reactive không ổn định theo phiên bản.** Stack trace, reason phrase và JSON error có thể khác. **Sửa:** assert status/header/body chỉ theo hợp đồng đã công bố.

## 14. Checklist xây dựng test slice có WebFilter

Quy trình:

1. **Xác định mục tiêu:** kiểm tra WebFilter, controller, security rule hay tất cả wiring?
2. **Liệt kê filter cần có:** annotation `@Component`, `@Bean` từ config, hay auto-config?
3. **Kiểm tra điểm đăng ký:** slice đã nạp filter chưa? Nếu cần bảo đảm có một filter cụ thể, import class/config có chủ đích.
4. **Liệt kê dependency filter:** policy, config properties, client, repository. Quyết định thứ gì phải là mock, thứ gì thật.
5. **Chọn một web stack:** WebFlux + `WebTestClient`; tránh thêm MVC starter không cần.
6. **Arrange từng test:** stub publisher và kết quả cụ thể; không dùng stub chung giữa các test.
7. **Kiểm tra allow:** status, response header và JSON body cho request hợp lệ.
8. **Kiểm tra deny:** 400/403, body rỗng và không gọi controller dependency.
9. **Kiểm tra lỗi downstream:** cho phép filter đi tiếp nhưng controller trả 404.
10. **Bổ sung security/CORS/parallel khi đúng mục tiêu:** import custom chain và cấu hình test support phù hợp.
11. **Chạy cả suite:** test không phụ thuộc thứ tự, không rò state, không đổi profile/context vô ý.
12. **Đo và tối ưu:** chỉ nạp phạm vi cần thiết; không tối ưu cache bằng cách bỏ filter hoặc bảo mật phải kiểm.

Checklist trước khi chốt:

- [ ] Phân biệt `WebFilter` server-side với `ExchangeFilterFunction` client-side.
- [ ] Filter thật có mặt trong **WebFlux server chain của slice**, không chỉ trong cấu hình production ở nơi khác.
- [ ] `@MockitoBean` đặt vào dependency cần cô lập, không mock logic filter đang kiểm tra.
- [ ] Khi cần `@Bean` từ custom `@Configuration`, đã `@Import` cấu hình đúng phạm vi.
- [ ] Với `@ConfigurationProperties`, đã đăng ký bean và cung cấp property test nếu cần.
- [ ] Không gọi `block()/subscribe()` trong filter.
- [ ] Nhánh cho phép trả `chain.filter(exchange)`, nhánh từ chối trả publisher hoàn tất response.
- [ ] Có ca thiếu header, policy từ chối, policy rỗng và downstream không có dữ liệu nếu thuộc hợp đồng.
- [ ] Kết quả kiểm tra gồm HTTP status, response header, body và interaction quan trọng.
- [ ] Đã cân nhắc `@Order`, Spring Security, CSRF, CORS và thời điểm response commit.
- [ ] Không suy luận rằng custom security config hoặc functional routes tự được phát hiện bởi `@WebFluxTest`.
- [ ] Test độc lập trong môi trường CI, không phụ thuộc database/network thật nếu đó không phải mục tiêu.

**Kết luận:** Khi test Spring WebFlux bằng `@WebFluxTest`, cần kiểm tra đồng thời **filter nào thực sự được đăng ký trong slice** và **các dependency của filter có được cung cấp đúng**. `WebFilter` là một phần của **server-side reactive chain**, không chỉ là một helper Java; nó phải compose và return publisher, giữ request state cô lập. Với bộ test nhỏ, `@Import` filter thật + `@MockitoBean` collaborator + `WebTestClient` giúp chứng minh chính xác hai nhánh **allow/deny** và đường đi tới controller.

### Tài liệu tham khảo

- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — @WebFluxTest Javadoc](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/autoconfigure/web/reactive/WebFluxTest.html)
- [Spring Framework 6.2 — WebFilter API](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/web/server/WebFilter.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Spring Boot — Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html)
- [Spring Security — Testing WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/index.html)