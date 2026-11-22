# bindToController cho controller WebFlux

`WebTestClient` có thể kiểm thử một controller WebFlux trực tiếp mà không cần khởi động server. Với `WebTestClient.bindToController(...)`, test truyền vào các controller instance cần kiểm thử; Spring dựng hạ tầng WebFlux mock để request đi qua cơ chế xử lý annotated controller, argument resolver và HTTP message reader/writer.

Cách này phù hợp khi muốn kiểm tra mapping, binding dữ liệu, xử lý reactive return type và response của một nhóm controller với cấu hình gọn. Test không cần nạp toàn bộ ứng dụng hoặc mở cổng HTTP. Vì controller được truyền trực tiếp, test cũng chủ động kiểm soát instance và các dependency được đưa vào controller.

## 1. bindToController hoạt động như thế nào?

`WebTestClient` là HTTP client dùng cho kiểm thử. Nó có thể gửi request đến một server đang chạy hoặc gửi request vào một server mock được dựng trong bộ nhớ.

Trong dự án dùng Spring Boot, `spring-boot-starter-webflux` cung cấp WebFlux và Reactor cho ứng dụng; `spring-boot-starter-test` cung cấp các thư viện kiểm thử. `WebTestClient` nằm trong `spring-test`. Nếu kiểm tra publisher bằng `StepVerifier`, cần có `reactor-test` trên test classpath. Với request/response JSON, ứng dụng cũng cần một JSON codec phù hợp, thường là Jackson trong cấu hình Spring Boot WebFlux.

Với `bindToController(...)`, Spring tạo môi trường WebFlux mock quanh controller được cung cấp. Luồng xử lý khái quát:

```text
WebTestClient
    |
    | HTTP request giả lập
    v
WebFlux mock infrastructure
    |
    v
HandlerMapping / HandlerAdapter
    |
    v
WebFlux Controller
    |
    v
Mono / Flux / ResponseEntity
    |
    v
HTTP response giả lập
    |
    v
WebTestClient assertions
```

Các bước cơ bản:

1. Tạo controller instance.
2. Gọi `WebTestClient.bindToController(controller).build()`.
3. Dùng client tạo request với method, URI, headers và body.
4. Gọi `exchange()` để thực thi request qua WebFlux.
5. Kiểm tra status, headers và body bằng các assertion API.

Ví dụ tối thiểu:

```java
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient client = WebTestClient
    .bindToController(new GreetingController())
    .build();
```

`bindToController` nhận một hoặc nhiều controller instance. Khi có nhiều controller, có thể truyền chúng cùng lúc:

```java
WebTestClient client = WebTestClient
    .bindToController(
        new GreetingController(),
        new OrderController()
    )
    .build();
```

## 2. Viết controller WebFlux trả về Mono

WebFlux controller thường trả về kiểu reactive như `Mono<T>` hoặc `Flux<T>`. Ví dụ controller sau nhận một query parameter và trả lời bằng `Mono<String>`:

```java
import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
class GreetingController {

    @GetMapping("/greeting")
    Mono<String> greeting(
            @RequestParam(defaultValue = "friend") String name) {
        return Mono.just("Hello " + name);
    }
}
```

Test dùng `bindToController` để dựng client và gửi request:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

class GreetingControllerTests {

    private final WebTestClient client = WebTestClient
        .bindToController(new GreetingController())
        .build();

    @Test
    void returnsGreeting() {
        client.get()
            .uri(uriBuilder -> uriBuilder
                .path("/greeting")
                .queryParam("name", "Mai")
                .build())
            .accept(MediaType.TEXT_PLAIN)
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(MediaType.TEXT_PLAIN)
            .expectBody(String.class)
            .isEqualTo("Hello Mai");
    }
}
```

Trong test:

- `client.get()` tạo request GET.
- `uri(...)` đặt đường dẫn và query parameter.
- `accept(...)` khai báo kiểu response client chấp nhận.
- `exchange()` gửi request qua WebFlux mock infrastructure.
- `expectStatus()` kiểm tra HTTP status.
- `expectHeader()` kiểm tra response header.
- `expectBody(String.class)` đọc body thành chuỗi để so sánh.

`exchange()` là ranh giới thực thi request. Các assertion sau đó kiểm tra response đã được tạo ra từ quá trình xử lý controller.

## 3. Kiểm tra JSON request và response

Với endpoint nhận JSON, test cần đặt `Content-Type` và cung cấp body đúng định dạng. WebFlux sử dụng HTTP message reader để chuyển JSON thành đối tượng Java, sau đó message writer chuyển kết quả trả về thành JSON response.

Ví dụ controller:

```java
import reactor.core.publisher.Mono;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @PostMapping("/orders")
    @ResponseStatus(HttpStatus.CREATED)
    Mono<OrderResponse> create(@RequestBody CreateOrderRequest request) {
        return Mono.just(
            new OrderResponse("ORD-284", request.customerId())
        );
    }
}

record CreateOrderRequest(String customerId) {
}

record OrderResponse(String id, String customerId) {
}
```

Test gửi JSON và kiểm tra response bằng JSONPath:

```java
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

class OrderControllerTests {

    private final WebTestClient client = WebTestClient
        .bindToController(new OrderController())
        .build();

    @Test
    void createsOrderFromJson() {
        client.post()
            .uri("/orders")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .bodyValue(new CreateOrderRequest("C-208"))
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.id").isEqualTo("ORD-284")
            .jsonPath("$.customerId").isEqualTo("C-208");
    }
}
```

`bodyValue(...)` gửi một object để message writer mã hóa theo `Content-Type`; `expectBody()` cho phép kiểm tra response JSON bằng JSONPath. Cách này giúp test đi qua chính message codec mà ứng dụng dùng để đọc request và ghi response.

## 4. Kiểm tra nhiều phần tử từ Flux

Controller có thể trả về `Flux<T>` khi response chứa một luồng nhiều phần tử. Với response hữu hạn, `expectBodyList(...)` có thể thu thập body thành danh sách để kiểm tra:

```java
import reactor.core.publisher.Flux;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class ProductController {

    @GetMapping("/products")
    Flux<String> products() {
        return Flux.just("book", "pen", "notebook");
    }
}
```

```java
client.get()
    .uri("/products")
    .exchange()
    .expectStatus().isOk()
    .expectBodyList(String.class)
    .contains("book", "pen", "notebook");
```

`expectBodyList` phù hợp với response hữu hạn có thể được buffer trong test. Với luồng liên tục hoặc streaming response, không nên chờ toàn bộ body kết thúc. Hãy dùng `returnResult(...)` để lấy publisher và kiểm tra các phần tử bằng Reactor Test `StepVerifier`:

```java
import reactor.test.StepVerifier;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.FluxExchangeResult;

FluxExchangeResult<String> result = client.get()
    .uri("/events")
    .accept(MediaType.TEXT_EVENT_STREAM)
    .exchange()
    .expectStatus().isOk()
    .returnResult(String.class);

StepVerifier.create(result.getResponseBody())
    .expectNext("created", "updated")
    .thenCancel()
    .verify();
```

Với streaming response, cần chủ động xác định số phần tử mong đợi hoặc điều kiện kết thúc. `thenCancel()` thể hiện test chủ động hủy subscription sau khi đã nhận các phần tử cần xác nhận.

## 5. Thêm ControllerAdvice cho controller test

`bindToController` cho phép đăng ký `@ControllerAdvice` riêng bằng `controllerAdvice(...)`. Điều này hữu ích khi muốn kiểm tra cách controller chuyển exception thành HTTP response mà không cần nạp toàn bộ application context.

Ví dụ controller phát sinh lỗi:

```java
import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class AccountController {

    @GetMapping("/accounts/unknown")
    Mono<String> missingAccount() {
        return Mono.error(new IllegalArgumentException("Account not found"));
    }
}
```

Advice chuẩn hóa exception thành response:

```java
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
class ApiExceptionHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    @ResponseStatus(HttpStatus.NOT_FOUND)
    Map<String, String> handleMissingAccount(IllegalArgumentException ex) {
        return Map.of("code", "ACCOUNT_NOT_FOUND");
    }
}
```

Đưa cả controller và advice vào cấu hình test:

```java
WebTestClient client = WebTestClient
    .bindToController(new AccountController())
    .controllerAdvice(new ApiExceptionHandler())
    .build();

client.get()
    .uri("/accounts/unknown")
    .exchange()
    .expectStatus().isNotFound()
    .expectBody()
    .jsonPath("$.code").isEqualTo("ACCOUNT_NOT_FOUND");
```

Test xác nhận response cuối cùng mà client nhận được: status 404 và error code trong JSON. Nếu không đăng ký advice, test có thể quan sát hành vi exception khác với ứng dụng thực tế đang sử dụng global exception handler.

## 6. Tùy chỉnh client và WebFlux mock infrastructure

Có thể cấu hình phần server mock trước khi gọi `build()`, sau đó cấu hình HTTP client bằng `configureClient()`.

```java
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

WebTestClient client = WebTestClient
    .bindToController(new GreetingController())
    .configureClient()
    .baseUrl("http://localhost")
    .defaultHeader("X-Test-Client", "webflux-test")
    .defaultHeader("Accept", MediaType.TEXT_PLAIN_VALUE)
    .build();
```

`configureClient()` mở phần cấu hình client, ví dụ base URL, default headers, filters và timeout. Những thiết lập phía client không thay đổi cách controller được khởi tạo.

Nếu cần tùy chỉnh hạ tầng server mock, `ControllerSpec` còn cho phép cấu hình controller advice và HTTP message codecs. Ví dụ, có thể đăng ký codec tùy chỉnh để kiểm tra cách ứng dụng đọc hoặc ghi một định dạng dữ liệu riêng. Chỉ nên thêm cấu hình khi test cần xác nhận chính hành vi đó; cấu hình quá nhiều sẽ làm test khó xác định thành phần nào gây ra kết quả.

## 7. Controller có dependency

`bindToController(...)` nhận controller instance. Nó không tự thực hiện component scan toàn ứng dụng và cũng không tự tìm các service bean như khi khởi động application context.

Nếu controller có constructor dependency, test cần cung cấp dependency khi tạo instance. Ví dụ có thể dùng mock của service:

```java
import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CustomerController {

    private final CustomerService customerService;

    CustomerController(CustomerService customerService) {
        this.customerService = customerService;
    }

    @GetMapping("/customers/{id}")
    Mono<Customer> find(@PathVariable String id) {
        return customerService.findById(id);
    }
}
```

```java
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.mock;

CustomerService customerService = mock(CustomerService.class);
given(customerService.findById("C-208"))
    .willReturn(Mono.just(new Customer("C-208", "Mai")));

WebTestClient client = WebTestClient
    .bindToController(new CustomerController(customerService))
    .build();
```

Trong ví dụ này, test chủ động tạo service mock rồi truyền vào constructor. Có thể dùng Mockito hoặc một fake implementation tùy theo nhu cầu. Nếu muốn Spring tự tiêm dependency, dùng test dựa trên application context thay vì mong `bindToController` tự quét và khởi tạo toàn bộ bean.

## 8. bindToController khác với các cách bind khác

`WebTestClient` có nhiều cách tạo client tùy phạm vi kiểm thử:

| Cách bind | Đối tượng đầu vào | Phạm vi kiểm thử |
|---|---|---|
| `bindToController(...)` | Một hoặc nhiều controller instance | Kiểm thử controller với WebFlux mock infrastructure và cấu hình tối thiểu |
| `bindToApplicationContext(...)` | Application context WebFlux đã nạp | Kiểm thử các bean và cấu hình WebFlux của ứng dụng |
| `bindToRouterFunction(...)` | `RouterFunction` | Kiểm thử functional endpoint của WebFlux |
| `bindToServer()` | Kết nối đến server đang chạy | Kiểm thử qua HTTP thật, bao gồm phần server đã khởi động |

Chọn `bindToController` khi mục tiêu tập trung vào một controller hoặc một nhóm controller và test có thể tự cung cấp dependency. Chọn `bindToApplicationContext` khi cần xác nhận cấu hình bean, filter, codec hoặc các thành phần WebFlux đã được đăng ký trong context. Dùng `bindToServer` khi cần kiểm tra server thật và giao tiếp qua mạng.

## 9. Giới hạn và lỗi thường gặp

`bindToController` giúp test nhanh và cô lập, nhưng phạm vi của nó cũng có giới hạn:

- Không khởi động server thật, không mở cổng mạng và không kiểm tra TLS hoặc reverse proxy.
- Không tự nạp toàn bộ application context, component scan hoặc cấu hình triển khai.
- Không tự tìm và tiêm các service bean; controller instance phải có dependency phù hợp ngay khi được tạo.
- Chỉ những controller và advice được truyền vào mới tham gia cấu hình kiểm thử.
- Cấu hình WebFlux mặc định của mock setup có thể khác cấu hình codec, filter hoặc customizer mà ứng dụng thực tế đăng ký trong context.

| Hiện tượng | Nguyên nhân cần kiểm tra |
|---|---|
| Controller không được tìm thấy | Controller chưa được truyền vào `bindToController(...)` hoặc URI/method không khớp mapping |
| Dependency trong controller là `null` | Test tự tạo controller nhưng chưa truyền dependency qua constructor |
| Exception trả status hoặc body không như mong đợi | Chưa đăng ký `controllerAdvice(...)` hoặc exception handler không xử lý đúng loại exception |
| JSON không được đọc hoặc ghi | Kiểm tra `Content-Type`, `Accept`, codec và dependency JSON tương ứng |
| Test không kiểm tra được filter/cấu hình toàn ứng dụng | Chuyển sang bind với application context nếu cấu hình đó là một phần của hợp đồng cần test |
| Response stream khiến test chờ mãi | Response là luồng không kết thúc; dùng `returnResult(...)` và `StepVerifier` với điều kiện nhận/hủy phù hợp |

## 10. Quy trình viết test bằng bindToController

1. Chọn controller WebFlux và xác định dependency mà controller cần.
2. Tạo controller instance cùng các dependency thật, fake hoặc mock phù hợp.
3. Dựng `WebTestClient` bằng `bindToController(...)`; đăng ký `controllerAdvice(...)` nếu cần.
4. Gửi request với method, URI, headers, content type và body đúng với endpoint.
5. Gọi `exchange()` để chạy request qua WebFlux mock infrastructure.
6. Kiểm tra status, headers và body; với `Flux` hữu hạn dùng `expectBodyList`, với streaming dùng `returnResult` và `StepVerifier`.
7. Nếu test cần cấu hình hoặc bean của toàn ứng dụng, chuyển phạm vi sang `bindToApplicationContext(...)`.

`bindToController` phù hợp với kiểm thử controller WebFlux có phạm vi rõ ràng: test chủ động cung cấp controller và dependency, còn WebTestClient mô phỏng request/response qua hạ tầng WebFlux. Phân biệt đúng phạm vi này giúp test nhanh, dễ đọc và không kết luận rằng một controller test riêng lẻ đã xác nhận toàn bộ ứng dụng được cấu hình đúng.
