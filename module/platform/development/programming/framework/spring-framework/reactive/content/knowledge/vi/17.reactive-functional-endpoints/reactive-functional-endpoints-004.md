# Đọc body và tham số bằng `ServerRequest` trong Spring WebFlux

## 1. `ServerRequest` thuộc mô hình functional endpoint

Spring WebFlux có hai cách phổ biến để xây dựng HTTP endpoint:

- **Annotated controller:** dùng `@RestController`, `@GetMapping`, `@RequestParam`, `@RequestBody` và các annotation tương tự.
- **Functional endpoint (WebFlux.fn):** khai báo route bằng `RouterFunction` và xử lý request bằng `HandlerFunction`.

Trong functional endpoint, handler nhận một đối tượng **`ServerRequest`**. Đây là abstraction của Spring đại diện cho HTTP request hiện tại, cung cấp API để đọc:

- Body JSON, text hoặc stream dữ liệu.
- Path variable trong URL.
- Query parameter, kể cả parameter lặp.
- Header và cookie.
- Form URL-encoded và multipart data.
- Principal, session, request attributes và `ServerWebExchange`.

Handler thường có chữ ký:

```java
HandlerFunction<ServerResponse> handler = request -> {
    // Đọc request và trả về ServerResponse.
    return ServerResponse.ok().build();
};
```

Về kiểu dữ liệu, `HandlerFunction<ServerResponse>` nhận `ServerRequest` và trả `Mono<ServerResponse>`. `ServerRequest` không phải servlet request và không cung cấp API đọc body đồng bộ. Các thao tác đọc body trả về `Mono` hoặc `Flux`, vì vậy ta kết hợp chúng bằng operator reactive.

Luồng xử lý:

```text
HTTP client
    |
    | HTTP request
    v
RouterFunction
    |
    | chọn route phù hợp
    v
HandlerFunction<ServerResponse>
    |
    | nhận ServerRequest
    +---- path/query/header/cookie
    |
    +---- bodyToMono / bodyToFlux
    |
    v
Mono<ServerResponse>
    |
    | ghi status, headers và body
    v
HTTP response
```

`ServerRequest` là đầu vào để handler đọc request; `ServerResponse` là abstraction để xây dựng response. Không cần tự gọi `.subscribe()` trong handler. Hãy trả Publisher để WebFlux quản lý subscription, lỗi, cancellation và quá trình ghi response.

## 2. Các API đọc request thường dùng

| Nhu cầu | API của `ServerRequest` | Kiểu trả về |
|---|---|---|
| Đọc path variable | `pathVariable("id")` | `String` |
| Đọc tất cả path variables | `pathVariables()` | `Map<String, String>` |
| Đọc query parameter đầu tiên | `queryParam("status")` | `Optional<String>` |
| Đọc toàn bộ query parameters | `queryParams()` | `MultiValueMap<String, String>` |
| Đọc header đầu tiên | `headers().firstHeader("X-Trace-Id")` | `String` hoặc `null` |
| Đọc các giá trị header | `headers().header("Accept")` | `List<String>` |
| Đọc cookie | `cookies()` | `MultiValueMap<String, HttpCookie>` |
| Đọc body thành một object | `bodyToMono(MyDto.class)` | `Mono<MyDto>` |
| Đọc body thành nhiều object | `bodyToFlux(MyDto.class)` | `Flux<MyDto>` |
| Đọc form URL-encoded | `formData()` | `Mono<MultiValueMap<String, String>>` |
| Đọc multipart | `multipartData()` | `Mono<MultiValueMap<String, Part>>` |
| Đọc principal | `principal()` | `Mono<Principal>` |
| Đọc WebSession | `session()` | `Mono<WebSession>` |
| Đọc request attributes | `attributes()` | `Map<String, Object>` |
| Truy cập API cấp thấp | `exchange()` | `ServerWebExchange` |

Các giá trị trong path, query và header vẫn là chuỗi. Nếu cần `Long`, `UUID`, `LocalDate` hoặc enum, hãy parse/convert có kiểm soát hoặc dùng conversion service phù hợp. Với functional endpoint, không có bước tự động bind tham số vào method argument như annotated controller; handler chủ động gọi API cần thiết trên `ServerRequest`.

## 3. Đọc path variable

Path variable là một phần của route URL, ví dụ:

```text
GET /customers/42
```

Khai báo route và đọc giá trị:

```java
RouterFunction<ServerResponse> routes =
        RouterFunctions.route()
                .GET("/customers/{customerId}", request -> {
                    String rawId = request.pathVariable("customerId");
                    return ServerResponse.ok().bodyValue("customer=" + rawId);
                })
                .build();
```

`pathVariable("customerId")` trả về `String`. Nếu cần số, chuyển đổi rõ ràng:

```java
long customerId;
try {
    customerId = Long.parseLong(request.pathVariable("customerId"));
} catch (NumberFormatException ex) {
    return ServerResponse.badRequest()
            .bodyValue("customerId must be a number");
}
```

Đây là đoạn minh họa bên trong handler, trả về `Mono<ServerResponse>`. Không để lỗi parse biến thành lỗi server 500 nếu đó chỉ là input không hợp lệ của client; hãy trả 400 hoặc ánh xạ exception bằng error handler.

Có thể lấy toàn bộ path variables:

```java
Map<String, String> variables = request.pathVariables();
```

Tên key phải trùng tên đặt trong route template. Ví dụ `/teams/{teamId}/members/{memberId}` cung cấp hai key `teamId` và `memberId`.

## 4. Đọc query parameter

Query parameter nằm sau dấu `?`:

```text
GET /orders?status=PAID&page=2
```

Dùng `queryParam` khi chỉ cần một giá trị:

```java
Optional<String> status = request.queryParam("status");
String selectedStatus = status.orElse("ALL");
```

Kết quả là `Optional<String>` vì parameter có thể không được gửi. Với dữ liệu tùy chọn, xác định default rõ ràng. Với dữ liệu bắt buộc, trả lỗi 400 nếu thiếu:

```java
Optional<String> customer = request.queryParam("customer");
if (customer.isEmpty() || customer.get().isBlank()) {
    return ServerResponse.badRequest()
            .bodyValue("query parameter 'customer' is required");
}
```

### Query parameter có nhiều giá trị

Client có thể gửi cùng một key nhiều lần:

```text
GET /orders?tag=urgent&tag=export&tag=paid
```

`queryParam("tag")` chỉ cung cấp một giá trị; dùng `queryParams()` nếu cần tất cả:

```java
List<String> tags = request.queryParams().getOrDefault(
        "tag", List.of()
);
```

`queryParams()` là `MultiValueMap<String, String>`, vì vậy mỗi key có thể chứa một danh sách giá trị. Không dùng `Map<String, String>` nếu API cho phép lặp parameter.

### Parse kiểu số và ngày

```java
int page;
try {
    page = Integer.parseInt(
            request.queryParam("page").orElse("1")
    );
    if (page < 1) {
        return ServerResponse.badRequest()
                .bodyValue("page must be positive");
    }
} catch (NumberFormatException ex) {
    return ServerResponse.badRequest()
            .bodyValue("page must be an integer");
}
```

Nếu có nhiều kiểu cần chuyển đổi, quy tắc locale hoặc value object, có thể dùng `ConversionService`/`Formatter` đã cấu hình. Đừng lặp lại logic parse phức tạp ở nhiều handler.

## 5. Đọc header và cookie

Header thường dùng cho trace ID, ngôn ngữ, content negotiation hoặc metadata giao thức:

```java
String traceId = request.headers().firstHeader("X-Trace-Id");
String accept = request.headers().firstHeader("Accept");

if (traceId == null || traceId.isBlank()) {
    traceId = "not-provided";
}
```

Nếu header có nhiều giá trị, dùng:

```java
List<String> accepts = request.headers().header("Accept");
```

Header do client gửi không mặc nhiên đáng tin. Không dùng `X-User-Id`, `X-Role` hoặc `X-Tenant-Id` làm bằng chứng xác thực/ủy quyền nếu hệ thống chưa có proxy đáng tin xác thực và ghi đè chúng. Với người dùng đã đăng nhập, lấy danh tính từ cơ chế Spring Security và `request.principal()` hoặc API bảo mật reactive tương ứng.

Cookie có thể được đọc bằng:

```java
HttpCookie sessionCookie =
        request.cookies().getFirst("SESSION");
```

`getFirst` trả cookie đầu tiên hoặc `null`. Không log giá trị session cookie hoặc token thô; chúng có thể cho phép người khác chiếm phiên đăng nhập.

## 6. Đọc body thành một object bằng `bodyToMono`

Với request JSON chỉ chứa một object, dùng `bodyToMono`:

```java
public record CreateOrderRequest(
        String product,
        int quantity
) {}

Mono<CreateOrderRequest> body =
        request.bodyToMono(CreateOrderRequest.class);
```

Spring dùng `HttpMessageReader`/codec phù hợp với `Content-Type` của request để decode byte thành object Java. Trong ứng dụng WebFlux thông thường, Jackson codec có thể đọc JSON khi dependency tương ứng có trên classpath.

Một handler có thể kết hợp body và query parameter:

```java
Mono<ServerResponse> create(ServerRequest request) {
    return request.bodyToMono(CreateOrderRequest.class)
            .flatMap(body -> {
                String source = request.queryParam("source")
                        .orElse("web");

                return ServerResponse.ok().bodyValue(
                        "created " + body.product()
                                + ", quantity=" + body.quantity()
                                + ", source=" + source
                );
            });
}
```

`bodyToMono` chỉ phát tối đa một object. Nếu body không có dữ liệu, Mono có thể hoàn tất rỗng. Khi body bắt buộc, xử lý trường hợp đó bằng `switchIfEmpty`:

```java
return request.bodyToMono(CreateOrderRequest.class)
        .flatMap(this::saveOrder)
        .switchIfEmpty(
                ServerResponse.badRequest()
                        .bodyValue("request body is required")
        );
```

`saveOrder` ở đây là hàm minh họa trả `Mono<ServerResponse>`. Trong code thực tế, hãy kiểm tra kiểu trả về để `flatMap` ghép đúng Publisher.

## 7. Đọc body generic hoặc collection

Nếu body là một collection như `List<LineItem>`, chỉ truyền `List.class` sẽ làm mất thông tin kiểu phần tử ở runtime. Dùng `ParameterizedTypeReference`:

```java
private static final ParameterizedTypeReference<List<LineItem>>
        LINE_ITEMS_TYPE = new ParameterizedTypeReference<>() {};

Mono<List<LineItem>> lines =
        request.bodyToMono(LINE_ITEMS_TYPE);
```

Với `LineItem` là record hoặc class DTO của ứng dụng. `ParameterizedTypeReference` giữ thông tin generic để codec biết cần decode từng phần tử thành `LineItem`.

Nếu body thực sự là một stream gồm nhiều object, không nhất thiết phải đọc thành một List lớn. Dùng `bodyToFlux` khi media type và codec hỗ trợ định dạng streaming phù hợp.

## 8. Đọc body nhiều phần tử bằng `bodyToFlux`

`bodyToFlux` phù hợp với body stream có nhiều phần tử, ví dụ JSON Lines/NDJSON:

```java
Flux<EventInput> events =
        request.bodyToFlux(EventInput.class);
```

Nếu request dùng `application/x-ndjson`, mỗi dòng JSON có thể được decode thành một `EventInput` khi codec hỗ trợ. Handler có thể xử lý từng phần tử:

```java
return request.bodyToFlux(EventInput.class)
        .concatMap(event -> eventService.accept(event))
        .then(ServerResponse.accepted().build());
```

`eventService.accept(event)` là hàm minh họa trả `Mono<?>`; trong ứng dụng thật cần chọn kiểu kết quả phù hợp. `concatMap` xử lý lần lượt và giữ thứ tự. Nếu dùng `flatMap`, nhiều phần tử có thể được xử lý đồng thời; cần đặt giới hạn concurrency khi tải lớn và chấp nhận rằng thứ tự hoàn thành có thể khác thứ tự đầu vào.

`Flux` cho phép xử lý theo luồng và tôn trọng demand ở các operator reactive. Tránh `.collectList()` cho body không giới hạn hoặc rất lớn nếu không cần lưu toàn bộ vào RAM.

## 9. Body chỉ nên được tiêu thụ một lần

HTTP request body là luồng dữ liệu. Trong functional handler, không nên gọi `bodyToMono` hai lần cho cùng request:

```java
// PHẢN VÍ DỤ: cố đọc cùng body hai lần.
Mono<CreateOrderRequest> first =
        request.bodyToMono(CreateOrderRequest.class);

Mono<CreateOrderRequest> second =
        request.bodyToMono(CreateOrderRequest.class);
```

Body thường không thể được replay tự động; lần đọc sau có thể nhận body rỗng, lỗi hoặc hành vi phụ thuộc nguồn. Hãy decode một lần rồi truyền object đã đọc qua các bước xử lý:

```java
return request.bodyToMono(CreateOrderRequest.class)
        .flatMap(body ->
                validate(body)
                        .then(save(body))
        );
```

`validate` và `save` là hàm minh họa. Nếu thật sự cần cache/replay body để nhiều thành phần cùng đọc, phải có thiết kế buffering có giới hạn, xử lý DataBuffer đúng ownership và cân nhắc kích thước tối đa. Không buffer toàn bộ body tùy tiện vì request lớn có thể gây cạn bộ nhớ.

## 10. Đọc form URL-encoded

Form HTML kiểu `application/x-www-form-urlencoded` không phải JSON. Dùng `formData()`:

```java
Mono<ServerResponse> submitForm(ServerRequest request) {
    return request.formData()
            .flatMap(form -> {
                String email = form.getFirst("email");
                String note = form.getFirst("note");

                if (email == null || email.isBlank()) {
                    return ServerResponse.badRequest()
                            .bodyValue("email is required");
                }

                return ServerResponse.ok()
                        .bodyValue("received " + email);
            });
}
```

`formData()` trả `Mono<MultiValueMap<String, String>>`; mỗi field có thể có nhiều giá trị. Chỉ gọi API này khi request gửi đúng loại form data. Với JSON body, dùng `bodyToMono`/`bodyToFlux`.

## 11. Đọc multipart và upload file

Request `multipart/form-data` có thể chứa text field và file. Dùng `multipartData()`:

```java
Mono<MultiValueMap<String, Part>> multipart =
        request.multipartData();
```

Ví dụ đọc một file part:

```java
return request.multipartData()
        .flatMap(parts -> {
            Part part = parts.getFirst("document");

            if (!(part instanceof FilePart file)) {
                return ServerResponse.badRequest()
                        .bodyValue("document file is required");
            }

            String originalFilename = file.filename();

            // Chuyển file.content() tới service upload đã được ứng dụng định nghĩa.
            return uploadService.store(file.content(), originalFilename)
                    .then(ServerResponse.accepted().build());
        });
```

`uploadService.store(...)` là hàm minh họa; ứng dụng cần tự triển khai việc lưu file và trả `Mono<?>`. Với file upload, cần:

- Giới hạn kích thước request và từng file.
- Kiểm tra loại nội dung thực tế, không tin hoàn toàn filename hoặc `Content-Type` do client gửi.
- Tạo tên file đích ở phía server; không nối trực tiếp đường dẫn do client gửi vào filesystem.
- Xử lý stream và cleanup đúng cách khi lỗi hoặc client hủy.
- Không gọi `collectList()`/đọc toàn bộ file vào RAM nếu file có thể lớn.
- Thiết lập giới hạn multipart và memory buffer phù hợp với phiên bản/configuration WebFlux.

`Part` đại diện cho một phần multipart; `FilePart` là phần chứa file. Với file lớn, xử lý `file.content()` theo stream hoặc dùng `transferTo(Path)` với đường dẫn do server kiểm soát.

## 12. Principal, session và attributes

Ngoài dữ liệu HTTP trực tiếp, `ServerRequest` còn cho phép truy cập thông tin trong runtime:

```java
Mono<Principal> principal = request.principal();

Mono<WebSession> session = request.session();

Map<String, Object> attributes = request.attributes();
```

- `principal()` trả danh tính đã được security layer thiết lập nếu có; không tự xác thực user chỉ vì method này tồn tại.
- `session()` trả `WebSession` reactive. Việc đọc/ghi session phải được ghép trong chain, tránh block.
- `attributes()` cung cấp các attribute gắn với request/exchange bởi framework hoặc filter.
- `exchange()` cho phép truy cập `ServerWebExchange` khi cần API thấp hơn mà `ServerRequest` không trực tiếp cung cấp.

Không lưu dữ liệu request nhạy cảm vào attribute hoặc log toàn bộ map. Với xác thực và phân quyền, dùng Spring Security reactive APIs và kiểm tra quyền ở service/domain layer.

## 13. Content-Type, codec và lỗi decode

`bodyToMono` và `bodyToFlux` không tự parse mọi định dạng. Spring chọn `HttpMessageReader` dựa trên target type và media type.

Ví dụ:

| Content-Type | Cách đọc thường gặp |
|---|---|
| `application/json` | `bodyToMono(Dto.class)` hoặc `bodyToFlux(Dto.class)` |
| `application/x-ndjson` | `bodyToFlux(Dto.class)` cho JSON Lines |
| `text/plain` | `bodyToMono(String.class)` |
| `application/x-www-form-urlencoded` | `formData()` |
| `multipart/form-data` | `multipartData()` |

Nếu client gửi JSON nhưng thiếu hoặc gửi sai `Content-Type`, server có thể không chọn được codec tương ứng. Nếu JSON sai cú pháp hoặc không thể chuyển thành DTO, quá trình decode phát lỗi reactive; handler hoặc error handler toàn cục cần ánh xạ thành HTTP 400. Media type không được hỗ trợ thường dẫn đến HTTP 415.

Khi cần codec tùy chỉnh, cấu hình `ServerCodecConfigurer` qua `WebFluxConfigurer.configureHttpMessageCodecs(...)` hoặc `HandlerStrategies` nếu tự xây WebFlux.fn server. Đừng dùng `Converter`/`Formatter` để thay thế JSON codec: conversion service xử lý chuyển đổi kiểu trong binding, còn message reader/writer xử lý HTTP body.

Đặt giới hạn kích thước body và in-memory buffering. Với request JSON lớn hoặc upload file, cân nhắc stream bằng `Flux`, không gom dữ liệu không giới hạn vào một object.

## 14. Ví dụ hoàn chỉnh Java 17+ với Spring Boot WebFlux

Ví dụ này có hai route functional:

- `POST /customers/{customerId}/orders?source=web`: đọc path variable, query parameter và JSON body, sau đó kiểm tra dữ liệu.
- `GET /orders?status=PAID&tag=urgent&tag=export`: đọc query parameter lặp và header `X-Trace-Id`.

Cấu trúc:

```text
server-request-demo/
├── pom.xml
└── src/main/java/demo/Main.java
└── src/main/java/demo/OrderHandler.java
```

### File `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>server-request-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

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
            <artifactId>spring-boot-starter-validation</artifactId>
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

### File `src/main/java/demo/Main.java`

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerResponse;

@SpringBootApplication
public class Main {

    public static void main(String[] args) {
        SpringApplication.run(Main.class, args);
    }

    @Bean
    RouterFunction<ServerResponse> routes(OrderHandler handler) {
        return RouterFunctions.route()
                .POST("/customers/{customerId}/orders", handler::create)
                .GET("/orders", handler::search)
                .build();
    }
}
```

### File `src/main/java/demo/OrderHandler.java`

```java
package demo;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

import org.springframework.core.codec.DecodingException;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

import reactor.core.publisher.Mono;

@Component
public class OrderHandler {

    private final Validator validator;

    public OrderHandler(Validator validator) {
        this.validator = validator;
    }

    public Mono<ServerResponse> create(ServerRequest request) {
        final long customerId;

        try {
            customerId = Long.parseLong(
                    request.pathVariable("customerId")
            );
        } catch (NumberFormatException ex) {
            return ServerResponse.badRequest()
                    .bodyValue("customerId must be a number");
        }

        return request.bodyToMono(CreateOrderRequest.class)
                .flatMap(body -> {
                    Set<ConstraintViolation<CreateOrderRequest>> violations =
                            validator.validate(body);

                    if (!violations.isEmpty()) {
                        String message = violations.stream()
                                .map(v -> v.getPropertyPath()
                                        + ": " + v.getMessage())
                                .collect(Collectors.joining("; "));

                        return ServerResponse.badRequest()
                                .bodyValue(message);
                    }

                    String source = request.queryParam("source")
                            .filter(value -> !value.isBlank())
                            .orElse("web");

                    CreateOrderResponse response =
                            new CreateOrderResponse(
                                    customerId,
                                    body.product(),
                                    body.quantity(),
                                    source
                            );

                    return ServerResponse.status(HttpStatus.CREATED)
                            .contentType(MediaType.APPLICATION_JSON)
                            .bodyValue(response);
                })
                .switchIfEmpty(
                        ServerResponse.badRequest()
                                .bodyValue("JSON request body is required")
                )
                .onErrorResume(DecodingException.class, error ->
                        ServerResponse.badRequest()
                                .bodyValue("Request JSON is invalid")
                );
    }

    public Mono<ServerResponse> search(ServerRequest request) {
        String status = request.queryParam("status").orElse("ALL");

        List<String> tags = request.queryParams().getOrDefault(
                "tag", List.of()
        );

        String traceId = request.headers().firstHeader("X-Trace-Id");
        if (traceId == null) {
            traceId = "";
        }

        SearchResponse response =
                new SearchResponse(status, tags, traceId);

        return ServerResponse.ok()
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(response);
    }

    public record CreateOrderRequest(
            @NotBlank String product,
            @Positive int quantity
    ) {}

    public record CreateOrderResponse(
            long customerId,
            String product,
            int quantity,
            String source
    ) {}

    public record SearchResponse(
            String status,
            List<String> tags,
            String traceId
    ) {}
}
```

Chạy từ thư mục dự án bằng JDK 17+ và Maven:

```bash
mvn spring-boot:run
```

### Thử route POST

```bash
curl -i -X POST "http://localhost:8080/customers/42/orders?source=web" \
  -H "Content-Type: application/json" \
  -d '{"product":"book","quantity":2}'
```

Response body JSON:

```json
{"customerId":42,"product":"book","quantity":2,"source":"web"}
```

Trong request này:

- `42` được lấy từ `request.pathVariable("customerId")`.
- `{"product":"book","quantity":2}` được decode bằng `bodyToMono(CreateOrderRequest.class)`.
- `source=web` được đọc bằng `queryParam("source")`.
- `Validator` kiểm tra `@NotBlank` và `@Positive` sau khi decode.

### Thử route GET

```bash
curl -i \
  -H "X-Trace-Id: req-17" \
  "http://localhost:8080/orders?status=PAID&tag=urgent&tag=export"
```

Response body JSON:

```json
{"status":"PAID","tags":["urgent","export"],"traceId":"req-17"}
```

Trong request này, `status` là query đơn, `tag` là query lặp và `X-Trace-Id` được đọc từ header.

Nếu gửi quantity bằng `0` hoặc product rỗng, validator trả lỗi 400. Nếu gửi body không có dữ liệu, handler trả 400 với thông báo body bắt buộc. JSON sai cú pháp được ánh xạ thành 400 qua `DecodingException` trong ví dụ; lỗi media type không hỗ trợ được xử lý theo cơ chế exception của WebFlux (thường là 415).

Đây là ứng dụng Spring Boot WebFlux chạy độc lập. Không cần tự tạo `HttpServer`, `HttpHandler` hay gọi `.subscribe()` trong handler; Boot quản lý server và functional route.

## 15. Phân biệt `ServerRequest` với annotated controller

| Tác vụ | Functional endpoint | Annotated controller |
|---|---|---|
| Lấy path variable | `request.pathVariable("id")` | `@PathVariable long id` |
| Lấy query parameter | `request.queryParam("page")` | `@RequestParam int page` |
| Lấy header | `request.headers().firstHeader("X-Trace-Id")` | `@RequestHeader("X-Trace-Id") String traceId` |
| Lấy cookie | `request.cookies().getFirst("SESSION")` | `@CookieValue("SESSION") String session` |
| Đọc JSON body | `request.bodyToMono(Dto.class)` | `@RequestBody Mono<Dto>` hoặc `Dto` |
| Đọc body stream | `request.bodyToFlux(Event.class)` | `@RequestBody Flux<Event>` |
| Trả response | `ServerResponse.ok().bodyValue(value)` | Trả `Mono<T>`/`Flux<T>` hoặc `ResponseEntity` |

Cả hai mô hình đều dùng WebFlux reactive runtime và message codecs. Sự khác biệt nằm ở cách khai báo route và lấy dữ liệu đầu vào. Dùng `ServerRequest` khi chọn functional endpoint và cần điều khiển rõ cách đọc request trong handler; dùng annotated controller nếu muốn Spring bind trực tiếp tham số vào method signature.

Không trộn hai cách chỉ để đọc cùng một request. Chọn một mô hình endpoint nhất quán theo cấu trúc ứng dụng.

## 16. Validation và xử lý lỗi

**Decode thành công không có nghĩa dữ liệu hợp lệ.** Có ba bước khác nhau:

1. **Đọc body:** codec chuyển byte thành object Java.
2. **Conversion/decoding:** nếu JSON sai hoặc kiểu dữ liệu không tương thích, phát lỗi decode.
3. **Validation nghiệp vụ:** kiểm tra product không rỗng, quantity dương, quyền sở hữu hoặc quy tắc domain.

Trong functional handler, có thể dùng Jakarta `Validator` như ví dụ trên. Với annotated controller, `@Valid`/`@Validated` được tích hợp vào argument binding theo cấu hình Spring.

Không bắt mọi exception rồi trả 400. Lỗi database, lỗi lập trình và lỗi hệ thống không phải lúc nào cũng là lỗi input của client. Hãy ánh xạ lỗi theo loại:

- Body sai cú pháp hoặc field không thể decode: thường 400.
- `Content-Type` không hỗ trợ: thường 415.
- Query/path value không hợp lệ: 400.
- Không xác thực: 401.
- Không đủ quyền: 403.
- Tài nguyên không tồn tại: 404.
- Lỗi nội bộ không dự kiến: 500.

Dùng `WebExceptionHandler` hoặc cơ chế error handling của ứng dụng để thống nhất response lỗi trên nhiều route. Handler riêng chỉ phục hồi các lỗi mà nó hiểu và có thể xử lý đúng.

## 17. Các lỗi phổ biến và cách khắc phục

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Coi query parameter là request body | Đọc sai nguồn dữ liệu hoặc nhận empty | Dùng `queryParam` cho URL query và `bodyToMono` cho body |
| Chỉ dùng `queryParam` khi key có thể lặp | Mất các giá trị thứ hai trở đi | Dùng `queryParams()` và lấy danh sách |
| Ép path variable sang số mà không bắt lỗi | Input sai có thể thành lỗi 500 | Parse có kiểm soát và trả 400 |
| Gọi `bodyToMono` nhiều lần | Body có thể đã bị tiêu thụ | Decode một lần rồi truyền object qua pipeline |
| Gom toàn bộ stream lớn bằng `collectList()` | Tăng memory, mất lợi ích streaming | Dùng `bodyToFlux` và xử lý từng phần tử |
| Dùng `bodyToMono(List.class)` | Mất generic element type | Dùng `ParameterizedTypeReference<List<T>>` |
| Dùng `formData()` cho JSON | Không có dữ liệu form đúng định dạng | Chọn API theo `Content-Type` |
| Dùng `bodyToMono` để đọc multipart | Bỏ qua cấu trúc part/file | Dùng `multipartData()` |
| Tin header do client gửi là danh tính | Có nguy cơ giả mạo user/tenant | Dùng Spring Security và proxy tin cậy |
| Log toàn bộ body/cookie | Có thể lộ password, token hoặc dữ liệu cá nhân | Log metadata an toàn, che dữ liệu nhạy cảm |
| Bỏ qua giới hạn body/upload | Có thể gây cạn bộ nhớ hoặc tài nguyên | Cấu hình codec/multipart limits và streaming |
| Gọi `.block()`/`.subscribe()` trong handler | Tách lifecycle hoặc chặn event loop | Trả `Mono<ServerResponse>`/`Flux` để WebFlux quản lý |
| Dùng converter thay codec JSON | JSON body không được decode như mong muốn | Cấu hình `HttpMessageReader`/codec phù hợp |
| Nghĩ functional endpoint tự validation mọi DTO | Dữ liệu sai nghiệp vụ vẫn lọt vào service | Gọi Jakarta Validator hoặc domain validation tường minh |

## 18. Kiểm thử functional endpoint

Có thể kiểm thử `RouterFunction` bằng `WebTestClient` mà không mở cổng TCP thật:

```java
WebTestClient client = WebTestClient
        .bindToRouterFunction(routes)
        .build();

client.post()
        .uri("/customers/42/orders?source=web")
        .contentType(MediaType.APPLICATION_JSON)
        .bodyValue(new CreateOrderRequest("book", 2))
        .exchange()
        .expectStatus().isCreated()
        .expectBody()
        .jsonPath("$.customerId").isEqualTo(42)
        .jsonPath("$.product").isEqualTo("book")
        .jsonPath("$.quantity").isEqualTo(2);
```

Đây là đoạn test minh họa, cần các kiểu `WebTestClient`, `MediaType`, `CreateOrderRequest` và route đã được tạo. `bindToRouterFunction` phù hợp để kiểm tra functional routing và handler. Nếu cần kiểm tra codec/server thực tế, TLS, multipart limits hoặc network behavior, bổ sung integration test chạy server trên cổng test.

Nên có test cho:

- Body JSON hợp lệ và body rỗng.
- JSON sai cú pháp hoặc Content-Type không hỗ trợ.
- Path variable không parse được.
- Query parameter thiếu, lặp và có giá trị rỗng.
- Header/cookie thiếu hoặc không hợp lệ.
- Form URL-encoded và multipart upload.
- DTO decode được nhưng validation thất bại.
- Client hủy khi đang gửi body stream.

## 19. Checklist khi viết handler

1. Xác định route và nguồn dữ liệu: path, query, header, cookie, form, multipart hay body.
2. Dùng API tương ứng của `ServerRequest`; không tự parse raw HTTP nếu không cần.
3. Với body, chọn `bodyToMono` cho một object và `bodyToFlux` cho stream.
4. Decode body một lần; truyền object đã đọc cho các bước sau.
5. Xử lý `Optional`, query lặp, body rỗng và lỗi parse có chủ đích.
6. Kiểm tra `Content-Type`, codec và giới hạn kích thước.
7. Tách decode, validation và nghiệp vụ.
8. Không tin metadata xác thực do client tự gửi.
9. Giữ reactive chain; không block hoặc subscribe thủ công trong handler.
10. Test route, body, tham số, lỗi và cancellation bằng `WebTestClient`.

**Ghi nhớ:** `ServerRequest` là cổng đọc HTTP request trong functional endpoint. Dùng `pathVariable` và `queryParam` cho dữ liệu URL, `headers()`/`cookies()` cho metadata, `formData()`/`multipartData()` cho form và `bodyToMono`/`bodyToFlux` cho body. Sau khi decode, validation và nghiệp vụ vẫn cần được xử lý rõ ràng trong reactive pipeline.

## 20. Tài liệu tham khảo chính thức

- [Spring Framework — Functional Endpoints (WebFlux.fn)](https://docs.spring.io/spring-framework/reference/web/webflux-functional.html)
- [Spring Framework — ServerRequest Javadoc 6.1](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/reactive/function/server/ServerRequest.html)
- [Spring Framework — ServerResponse Javadoc 6.1](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/reactive/function/server/ServerResponse.html)
- [Spring Framework — BodyExtractors Javadoc 6.1](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/web/reactive/function/BodyExtractors.html)
- [Spring Framework — WebFlux HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/config.html)
- [Spring Framework — WebFlux Validation](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html)
