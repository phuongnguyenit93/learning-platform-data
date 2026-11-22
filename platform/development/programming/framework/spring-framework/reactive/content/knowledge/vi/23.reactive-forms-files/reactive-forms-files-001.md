# Đọc application/x-www-form-urlencoded qua exchange

Trong **Spring WebFlux**, một biểu mẫu HTML có thể được gửi trong HTTP request body dưới dạng URL-encoded form. Với media type `application/x-www-form-urlencoded`, các trường được biểu diễn thành những cặp tên–giá trị như `username=alice&remember=true`. Spring WebFlux cung cấp API `ServerWebExchange.getFormData()` để đọc body này thành một `MultiValueMap<String, String>` reactive.

API này hữu ích khi controller cần truy cập trực tiếp toàn bộ form, xử lý trường lặp, đọc các trường động hoặc phối hợp dữ liệu form với request context. Nó không đọc query string: query parameter nằm trong `exchange.getRequest().getQueryParams()`, còn form body nằm trong `exchange.getFormData()`.

Bài này giải thích cách WebFlux giải mã form, cách đọc nhiều giá trị cùng tên, vòng đời body, giới hạn bộ nhớ, kiểm tra dữ liệu và cách kiểm thử bằng `WebTestClient`.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nhận biết cấu trúc và media type của URL-encoded form.
2. Dùng `ServerWebExchange.getFormData()` để đọc form theo kiểu reactive.
3. Hiểu kiểu trả về `Mono<MultiValueMap<String, String>>` và cách lấy giá trị.
4. Xử lý field bị thiếu, field rỗng, field lặp và dữ liệu Unicode.
5. Phân biệt form body với query parameter và HTTP header.
6. Hiểu cách `FormHttpMessageReader` giải mã body và cách cấu hình codec.
7. Tránh đọc request body nhiều lần hoặc parse thủ công chuỗi form.
8. Giới hạn kích thước form, xử lý lỗi và bảo vệ dữ liệu nhạy cảm.
9. Viết controller Java 17 chạy được và kiểm thử bằng `WebTestClient`.

## 2. application/x-www-form-urlencoded là gì?

`application/x-www-form-urlencoded` là định dạng thường dùng khi trình duyệt gửi form HTML không có file upload. Body chứa các cặp key-value nối với nhau bằng dấu `&`; tên và giá trị được phân cách bằng dấu `=`.

Ví dụ body:

~~~text
username=alice&displayName=Alice+Nguyen&remember=true
~~~

Một form có nhiều giá trị cùng tên có thể gửi:

~~~text
tag=reactive&tag=webflux&tag=spring
~~~

Quy tắc mã hóa quan trọng:

- Ký tự `&` phân cách các cặp; ký tự `=` phân cách tên và giá trị.
- Dấu cộng `+` trong form encoding biểu diễn dấu cách.
- Dấu cộng thực sự phải được percent-encode thành `%2B`.
- Ký tự ngoài tập ASCII được mã hóa theo charset, thông thường là UTF-8.
- Ký tự đặc biệt được biểu diễn bằng percent encoding, ví dụ `%26` là `&`.
- Một key có thể xuất hiện nhiều lần; không nên giả định mỗi key chỉ có một giá trị.

Ví dụ:

~~~http
POST /api/forms/submit HTTP/1.1
Content-Type: application/x-www-form-urlencoded; charset=UTF-8

username=alice&displayName=Nguy%E1%BB%85n+V%C4%83n+A&tag=reactive&tag=webflux
~~~

Spring giải mã các cặp trên thành dữ liệu Java. Controller không cần tự tách chuỗi theo `&` hoặc `=`.

## 3. Đọc form bằng ServerWebExchange.getFormData()

Trong WebFlux, `ServerWebExchange` đại diện cho một HTTP request/response. Phương thức:

~~~java
Mono<MultiValueMap<String, String>> getFormData()
~~~

trả về một `Mono` chứa các trường form. `MultiValueMap` là map mà mỗi key có thể chứa nhiều giá trị.

Ví dụ đọc form:

~~~java
@PostMapping(
    path = "/submit",
    consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
)
Mono<String> submit(ServerWebExchange exchange) {
    return exchange.getFormData()
        .map(form -> {
            String username = form.getFirst("username");
            return "username=" + username;
        });
}
~~~

Đây là snippet minh họa, cần import các kiểu Spring tương ứng. Controller nhận exchange trực tiếp, gọi `getFormData()` và xử lý kết quả trong `map`. Việc đọc body diễn ra reactive; không cần chặn thread bằng `block()`.

### 3.1. Kiểu dữ liệu trả về

`getFormData()` trả về:

~~~java
Mono<MultiValueMap<String, String>>
~~~

Có hai tầng cần hiểu:

- `Mono` biểu diễn kết quả giải mã form sẽ được cung cấp bất đồng bộ.
- `MultiValueMap<String, String>` chứa tên field và danh sách các giá trị dạng String.

Một form có thể không có field nào; khi đó map có thể rỗng. Nếu field bắt buộc, controller phải kiểm tra sự tồn tại và giá trị của field thay vì giả định dữ liệu luôn có.

### 3.2. Lấy một giá trị với getFirst

Khi field chỉ nên có một giá trị, dùng `getFirst`:

~~~java
String username = form.getFirst("username");
~~~

`getFirst` trả về giá trị đầu tiên hoặc `null` nếu key không tồn tại. Nếu form gửi nhiều giá trị cho cùng key, phương thức này chỉ lấy giá trị đầu; ứng dụng phải quyết định có chấp nhận trường lặp hay không.

Kiểm tra field bắt buộc:

~~~java
String username = form.getFirst("username");

if (username == null || username.isBlank()) {
    // Trả lỗi validation cho field username.
}
~~~

Phân biệt ba tình huống:

| Tình huống | Ví dụ | Cách nhận biết |
| --- | --- | --- |
| Field không có | Không gửi username | `form.getFirst("username") == null` |
| Field có nhưng rỗng | `username=` | Giá trị là chuỗi rỗng |
| Field có giá trị | `username=alice` | Giá trị là `alice` |

Không dùng một phép kiểm tra duy nhất cho mọi field. Một checkbox không được chọn có thể vắng mặt; một text input có thể có chuỗi rỗng; mỗi loại field cần quy tắc nghiệp vụ riêng.

### 3.3. Lấy tất cả giá trị với get

Khi một key có thể xuất hiện nhiều lần, dùng `get`:

~~~java
List<String> tags = form.get("tag");
~~~

Với body:

~~~text
tag=reactive&tag=webflux&tag=spring
~~~

danh sách nhận được gồm ba phần tử theo thứ tự xuất hiện. Để xử lý trường hợp key không có:

~~~java
List<String> tags = form.getOrDefault("tag", List.of());
~~~

Nếu cần lưu hoặc chuyển danh sách sang tầng nghiệp vụ, có thể tạo bản sao bất biến:

~~~java
List<String> tags = List.copyOf(
    form.getOrDefault("tag", List.of())
);
~~~

Không gọi `toSingleValueMap()` nếu cần giữ các giá trị lặp, vì map một giá trị sẽ làm mất thông tin nhiều giá trị của cùng key.

## 4. Form body khác query parameter

Đây là điểm dễ nhầm nhất khi chuyển từ Spring MVC sang WebFlux.

- Form body được đọc bằng `exchange.getFormData()`.
- Query string được đọc bằng `exchange.getRequest().getQueryParams()`.
- Header được đọc bằng `exchange.getRequest().getHeaders()`.

Ví dụ request:

~~~http
POST /api/forms/submit?source=newsletter
Content-Type: application/x-www-form-urlencoded

username=alice&tag=reactive
~~~

Đọc riêng từng nguồn:

~~~java
Mono<String> handle(ServerWebExchange exchange) {
    return exchange.getFormData().map(form -> {
        String username = form.getFirst("username");
        String source = exchange.getRequest()
            .getQueryParams()
            .getFirst("source");

        return "username=" + username + ", source=" + source;
    });
}
~~~

`username` lấy từ body; `source` lấy từ query string. Nếu cả query và form cùng có key `username`, hai giá trị vẫn thuộc hai nguồn riêng. Không tự gộp chúng thành một giá trị duy nhất.

Trong Spring WebFlux, `@RequestParam` tập trung vào query parameter. Nếu muốn đọc URL-encoded form body một cách trực tiếp và tường minh, dùng `getFormData()`. Với form có cấu trúc DTO cố định, `@ModelAttribute` cũng là một lựa chọn data binding; còn exchange API hữu ích khi cần xử lý map động, field lặp hoặc nhiều phần của request.

## 5. FormHttpMessageReader và quá trình giải mã

`ServerWebExchange.getFormData()` dựa trên cơ chế message reader của WebFlux. Reader chuyên biệt `FormHttpMessageReader` đọc body URL-encoded và chuyển nó thành `MultiValueMap<String, String>`.

Luồng xử lý khái quát:

~~~text
HTTP request body
Content-Type: application/x-www-form-urlencoded
        |
        v
ServerWebExchange.getFormData()
        |
        v
FormHttpMessageReader
        |
        v
Giải mã charset và percent encoding
        |
        v
MultiValueMap<String, String>
        |
        v
Controller xử lý dữ liệu
~~~

Reader thực hiện công việc mà code ứng dụng không nên tự viết lại:

- Tách các cặp tên và giá trị.
- Giải mã percent encoding.
- Xử lý dấu cộng theo quy tắc form encoding.
- Giải mã byte theo charset được hỗ trợ.
- Giữ nhiều giá trị cho một key.
- Áp dụng giới hạn buffering được cấu hình.

### 5.1. Content-Type phải đúng

Endpoint nên khai báo:

~~~java
consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
~~~

Client gửi:

~~~http
Content-Type: application/x-www-form-urlencoded
~~~

Nếu endpoint chỉ nhận form URL-encoded nhưng client gửi `application/json` hoặc `multipart/form-data`, mapping có thể bị từ chối với `415 Unsupported Media Type`.

Đừng nhầm ba định dạng:

| Content-Type | Nội dung | API đọc phù hợp |
| --- | --- | --- |
| `application/x-www-form-urlencoded` | Các cặp key-value đã URL encode | `exchange.getFormData()` |
| `multipart/form-data` | Các part riêng biệt, có thể chứa file | `exchange.getMultipartData()` hoặc `@RequestPart` |
| `application/json` | JSON object/array | `@RequestBody` hoặc reader JSON |

### 5.2. Charset và Unicode

Form URL-encoded thường dùng UTF-8. Có thể gửi rõ charset:

~~~http
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
~~~

Ví dụ field tiếng Việt:

~~~text
displayName=Nguy%E1%BB%85n+V%C4%83n+A
~~~

Sau khi giải mã, giá trị là `Nguyễn Văn A`. Khi test hoặc gửi bằng curl, dùng `--data-urlencode` để công cụ mã hóa ký tự đúng cách.

Không tự gọi URLDecoder trên giá trị đã được Spring giải mã. Làm vậy có thể giải mã hai lần và biến dữ liệu như dấu cộng hoặc percent sequence thành nội dung khác với ý định ban đầu.

## 6. Vòng đời request body và việc đọc form nhiều lần

HTTP request body là một luồng dữ liệu. Trong reactive server, body không nên được coi là một chuỗi có thể đọc tùy ý nhiều lần.

`ServerWebExchange.getFormData()` lưu kết quả form đã giải mã trong exchange để những lần gọi tiếp theo có thể dùng lại kết quả đã cache. Tuy nhiên, điều này không có nghĩa mọi API đọc body đều có thể chạy độc lập sau đó.

Các nguyên tắc:

1. Gọi `getFormData()` khi cần đọc URL-encoded form.
2. Không gọi `exchange.getRequest().getBody()` rồi kỳ vọng vẫn có thể đọc lại raw body sau khi form reader đã tiêu thụ body.
3. Không tự subscribe vào body trong controller hoặc filter.
4. Nếu nhiều thành phần cần cùng dữ liệu, đọc form một lần và truyền các giá trị cần thiết.
5. Không lưu exchange hoặc body publisher vào singleton/cache để dùng cho request khác.

Ví dụ không nên làm:

~~~java
exchange.getFormData().subscribe(form -> log.info("{}", form));
return chain.filter(exchange);
~~~

Đoạn này tạo subscription phụ và có thể tiêu thụ body tách khỏi lifecycle request. Hãy trả publisher hoặc ghép các thao tác vào publisher chính. Ngoài ra, tuyệt đối không log toàn bộ form nếu có password, token hoặc thông tin cá nhân.

## 7. Kiểm tra và chuẩn hóa dữ liệu form

Dữ liệu form là input từ client. Việc reader giải mã thành String không có nghĩa dữ liệu đã hợp lệ hoặc đáng tin cậy.

Một quy trình xử lý thường gồm:

1. Đọc field.
2. Kiểm tra field bắt buộc.
3. Trim hoặc chuẩn hóa theo quy tắc nghiệp vụ.
4. Kiểm tra độ dài và định dạng.
5. Kiểm tra số lượng giá trị cho field lặp.
6. Chuyển sang command/DTO có kiểu rõ ràng.
7. Kiểm tra authorization trước khi thực hiện hành động.

Ví dụ kiểm tra username:

~~~java
String username = form.getFirst("username");

if (username == null || username.isBlank()) {
    return badRequest("username is required");
}

username = username.trim();

if (username.length() > 80) {
    return badRequest("username is too long");
}
~~~

Đây là pseudocode minh họa cho phần validation; `badRequest` cần được thay bằng response/exception phù hợp của ứng dụng.

### 7.1. Kiểm tra field lặp

Với field được kỳ vọng chỉ có một giá trị, kiểm tra số lượng:

~~~java
List<String> values = form.get("role");

if (values != null && values.size() != 1) {
    // Từ chối request có role lặp.
}
~~~

Không mặc định lấy giá trị đầu tiên cho field bảo mật như role, accountId hoặc redirect URL. Kẻ tấn công có thể gửi nhiều giá trị cùng tên để khai thác khác biệt giữa parser ở proxy, framework và ứng dụng.

### 7.2. Chuyển đổi kiểu

Giá trị form luôn được giải mã thành String. Nếu cần số nguyên:

~~~java
String rawAge = form.getFirst("age");

Integer age = null;
if (rawAge != null && !rawAge.isBlank()) {
    try {
        age = Integer.valueOf(rawAge);
    }
    catch (NumberFormatException ex) {
        // Trả lỗi age phải là số nguyên.
    }
}
~~~

Với ngày tháng, enum hoặc kiểu custom, nên dùng Converter/Formatter hoặc một lớp mapper tập trung. Không lặp lại logic parse phức tạp trong từng controller.

### 7.3. Binding sang DTO

Nếu form có cấu trúc ổn định, tạo command DTO:

~~~java
record RegistrationCommand(
    String username,
    String displayName,
    List<String> tags
) {}
~~~

Sau khi đọc form, tạo DTO từ các field đã kiểm tra:

~~~java
RegistrationCommand command = new RegistrationCommand(
    username,
    displayName,
    List.copyOf(tags)
);
~~~

DTO nên chỉ chứa field client được phép gửi. Không bind trực tiếp entity persistence có thuộc tính nhạy cảm như role, balance, ownerId hoặc audit metadata.

## 8. Cấu hình giới hạn bộ nhớ

URL-encoded form được giải mã thành một map, vì vậy reader cần buffer dữ liệu body để phân tích các cặp key-value. Form body rất lớn có thể tiêu thụ nhiều memory.

Default codec của Spring WebFlux có giới hạn buffering; mức mặc định thường là 256 KiB cho các codec áp dụng giới hạn này. Khi vượt quá ngưỡng, request có thể thất bại với `DataBufferLimitException`.

Có thể cấu hình ở server:

~~~java
@Configuration
class WebConfig implements WebFluxConfigurer {

    @Override
    public void configureHttpMessageCodecs(
            ServerCodecConfigurer configurer) {

        configurer.defaultCodecs()
            .maxInMemorySize(512 * 1024);
    }
}
~~~

Ví dụ trên đặt giới hạn 512 KiB cho các default codec có hỗ trợ cấu hình đó. Đây không phải giới hạn tổng dung lượng upload multipart hoặc giới hạn request của mọi tầng mạng. Multipart có các giới hạn riêng về memory, disk và số lượng part.

### 8.1. Chọn giới hạn theo nhu cầu

Khi quyết định maxInMemorySize, cân nhắc:

- Số field tối đa của form.
- Chiều dài tối đa của tên và giá trị.
- Số request đồng thời.
- Dung lượng heap/direct memory của ứng dụng.
- Giới hạn request body tại reverse proxy/gateway.
- Việc form có nên chứa dữ liệu lớn hay không.

Không tăng giới hạn lên hàng chục hoặc hàng trăm MB chỉ để xử lý một form bất thường. URL-encoded form phù hợp với dữ liệu biểu mẫu nhỏ; file upload nên dùng multipart hoặc API upload streaming phù hợp.

### 8.2. Xử lý DataBufferLimitException

Có thể chuẩn hóa lỗi vượt giới hạn bằng exception handler:

~~~java
@RestControllerAdvice
class FormExceptionHandler {

    @ExceptionHandler(DataBufferLimitException.class)
    ResponseEntity<Map<String, String>> handleLimit(
            DataBufferLimitException exception) {

        return ResponseEntity
            .status(HttpStatus.PAYLOAD_TOO_LARGE)
            .body(Map.of(
                "error", "form body exceeds the configured limit"
            ));
    }
}
~~~

Đây là snippet tích hợp, cần import các kiểu tương ứng. Việc ánh xạ sang 413 là chính sách API của ví dụ; ứng dụng nên thống nhất status và error schema với gateway cũng như các endpoint khác. Một lỗi decode khác có thể được ánh xạ thành 400 Bad Request.

## 9. Ví dụ Java 17 chạy được với Spring Boot WebFlux

Ví dụ dưới đây tạo endpoint nhận form URL-encoded và trả JSON. Controller đọc body bằng `ServerWebExchange.getFormData()`, giữ các tag lặp, đồng thời đọc query parameter `source` riêng biệt.

### 9.1. Cấu trúc dự án

~~~text
form-exchange-demo/
├── build.gradle
└── src/
    ├── main/java/demo/FormExchangeApplication.java
    ├── main/java/demo/FormController.java
    └── test/java/demo/FormControllerTest.java
~~~

### 9.2. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Spring Boot quản lý các phiên bản Spring Framework, Reactor, Jackson và test dependency tương thích. Ví dụ dùng Java 17 và Spring Boot 3.3.5 để có một baseline dễ tái hiện; với dự án mới, chọn patch Spring Boot còn được hỗ trợ và để BOM quản lý phiên bản Spring modules.

### 9.3. FormExchangeApplication.java

~~~java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormExchangeApplication {

    public static void main(String[] args) {
        SpringApplication.run(FormExchangeApplication.class, args);
    }
}
~~~

### 9.4. FormController.java

~~~java
package demo;

import java.util.List;
import java.util.Optional;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ServerWebExchange;

import org.springframework.util.MultiValueMap;

import reactor.core.publisher.Mono;

record FormResult(
    boolean accepted,
    String username,
    String displayName,
    List<String> tags,
    String source,
    String error
) {}

@RestController
class FormController {

    @PostMapping(
        path = "/api/forms/submit",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    Mono<ResponseEntity<FormResult>> submit(
            ServerWebExchange exchange) {

        return exchange.getFormData().map(form -> {
            String username = Optional
                .ofNullable(form.getFirst("username"))
                .orElse("")
                .trim();

            String displayName = Optional
                .ofNullable(form.getFirst("displayName"))
                .orElse("");

            List<String> tags = List.copyOf(
                form.getOrDefault("tag", List.of())
            );

            String source = exchange.getRequest()
                .getQueryParams()
                .getFirst("source");

            if (username.isBlank()) {
                FormResult error = new FormResult(
                    false,
                    null,
                    displayName,
                    tags,
                    source,
                    "username is required"
                );
                return ResponseEntity.badRequest().body(error);
            }

            FormResult result = new FormResult(
                true,
                username,
                displayName,
                tags,
                source,
                null
            );

            return ResponseEntity.ok(result);
        });
    }
}
~~~

Điểm cần chú ý:

- Mapping chỉ nhận `application/x-www-form-urlencoded`.
- `getFormData()` đọc body thành `MultiValueMap`.
- `getFirst("username")` lấy một giá trị; `getOrDefault("tag", List.of())` giữ mọi tag lặp.
- `getQueryParams()` đọc query string riêng, vì vậy `source` không bị trộn với form body.
- `List.copyOf` tạo danh sách không thể sửa từ bên ngoài.
- Handler trả `Mono<ResponseEntity<FormResult>>`; không gọi `block()` hoặc `subscribe()`.

Ví dụ không xử lý xác thực người dùng hoặc lưu database. Trong ứng dụng thật, không trả lại password/token, không tin các field quyền hạn từ client và phải kiểm tra authorization trước khi thực hiện nghiệp vụ.

### 9.5. FormControllerTest.java

~~~java
package demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureWebTestClient
class FormControllerTest {

    @Autowired
    WebTestClient client;

    @Test
    void readsFormFieldsAndRepeatedValues() {
        client.post()
            .uri("/api/forms/submit?source=newsletter")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                    "username", "alice"
                )
                .with("displayName", "Nguyễn Văn A")
                .with("tag", "reactive")
                .with("tag", "webflux"))
            .exchange()
            .expectStatus().isOk()
            .expectHeader()
                .contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.username").isEqualTo("alice")
            .jsonPath("$.displayName").isEqualTo("Nguyễn Văn A")
            .jsonPath("$.tags[0]").isEqualTo("reactive")
            .jsonPath("$.tags[1]").isEqualTo("webflux")
            .jsonPath("$.source").isEqualTo("newsletter")
            .jsonPath("$.accepted").isEqualTo(true);
    }

    @Test
    void rejectsMissingRequiredUsername() {
        client.post()
            .uri("/api/forms/submit")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                "displayName", "Alice"
            ))
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.accepted").isEqualTo(false)
            .jsonPath("$.error").isEqualTo("username is required");
    }

    @Test
    void queryParameterIsNotTreatedAsFormField() {
        client.post()
            .uri("/api/forms/submit?username=query-user")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .body(BodyInserters.fromFormData(
                "displayName", "Alice"
            ))
            .exchange()
            .expectStatus().isBadRequest()
            .expectBody()
            .jsonPath("$.error").isEqualTo("username is required");
    }

    @Test
    void rejectsJsonWhenEndpointRequiresUrlEncodedForm() {
        client.post()
            .uri("/api/forms/submit")
            .contentType(MediaType.APPLICATION_JSON)
            .bodyValue("{\"username\":\"alice\"}")
            .exchange()
            .expectStatus().is4xxClientError();
    }
}
~~~

Các test dùng WebTestClient và body inserter của Spring để gửi form thực sự. Test đầu kiểm tra Unicode, query parameter và field lặp; test thứ hai kiểm tra field bắt buộc; test thứ ba chứng minh query parameter không tự trở thành form field; test cuối kiểm tra media type không phù hợp bị từ chối.

### 9.6. Chạy test và ứng dụng

Chạy test:

~~~bash
./gradlew test
~~~

Trên Windows:

~~~powershell
.\gradlew.bat test
~~~

Chạy ứng dụng:

~~~bash
./gradlew bootRun
~~~

Trên Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Nếu chưa có Gradle Wrapper, có thể dùng `gradle test` và `gradle bootRun` khi Gradle đã được cài đặt.

## 10. Gọi endpoint bằng curl

Gửi một form có Unicode và nhiều tag:

~~~bash
curl -i -X POST \
  'http://localhost:8080/api/forms/submit?source=newsletter' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'username=alice' \
  --data-urlencode 'displayName=Nguyễn Văn A' \
  --data-urlencode 'tag=reactive' \
  --data-urlencode 'tag=webflux'
~~~

Body JSON dự kiến:

~~~json
{
  "accepted": true,
  "username": "alice",
  "displayName": "Nguyễn Văn A",
  "tags": ["reactive", "webflux"],
  "source": "newsletter",
  "error": null
}
~~~

Gửi form thiếu username:

~~~bash
curl -i -X POST \
  http://localhost:8080/api/forms/submit \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'displayName=Alice'
~~~

Request bị từ chối với status 400 Bad Request và body có error `username is required`.

Gửi sai media type:

~~~bash
curl -i -X POST \
  http://localhost:8080/api/forms/submit \
  -H 'Content-Type: application/json' \
  -d '{"username":"alice"}'
~~~

Endpoint chỉ nhận form URL-encoded nên request JSON không khớp consumes condition và bị từ chối. Trong test, kiểm tra nhóm 4xx để không phụ thuộc cách cấu hình exception handling cụ thể.

## 11. Bảo mật khi xử lý form

Form thường chứa dữ liệu do người dùng nhập; một số form còn mang thông tin nhạy cảm.

### 11.1. Không tin dữ liệu client

Mọi giá trị trong form đều là input chưa tin cậy. Kiểm tra kiểu, độ dài, định dạng, số lượng giá trị và quyền trước khi dùng. Một field tên role, admin hoặc tenant không tự cấp quyền cho người gửi.

### 11.2. Không ghi log password hoặc token

Tránh log toàn bộ MultiValueMap. Nếu cần debug, chỉ ghi tên field đã cho phép và loại bỏ hoặc che các field nhạy cảm như password, access_token, csrf token, email hoặc số điện thoại.

### 11.3. Bảo vệ CSRF cho browser form

Nếu form được gửi từ browser và ứng dụng dùng session/cookie authentication, cấu hình CSRF protection của Spring Security phù hợp. Không tắt CSRF chỉ vì endpoint dùng POST hoặc Content-Type URL-encoded. Content-Type không thay thế kiểm tra CSRF.

### 11.4. Dùng HTTPS

URL encoding chỉ là cách biểu diễn dữ liệu, không mã hóa bí mật. Không gửi password hoặc token qua HTTP không mã hóa. Dùng HTTPS/TLS và chính sách cookie phù hợp.

### 11.5. Tránh parameter pollution

Một key có thể lặp nhiều lần. Đối với field cần duy nhất, hãy từ chối nếu có nhiều hơn một giá trị. Không để reverse proxy, security layer và controller diễn giải field trùng theo các cách khác nhau.

## 12. Những lỗi thường gặp và cách sửa

| Sai lầm | Hậu quả | Cách xử lý |
| --- | --- | --- |
| Dùng `getQueryParams()` để đọc form body | Không lấy được field trong body | Dùng `getFormData()` |
| Dùng `@RequestParam` như trong Spring MVC để mong đọc form body | Không khớp mô hình WebFlux query parameter | Dùng exchange API hoặc `@ModelAttribute` |
| Không khai báo consumes | Endpoint có thể nhận nhầm định dạng hoặc lỗi khó hiểu | Khai báo `application/x-www-form-urlencoded` |
| Tự split body theo `&` và `=` | Sai với percent encoding, dấu cộng, Unicode và field lặp | Dùng `FormHttpMessageReader` qua exchange |
| Chỉ dùng getFirst cho mọi field | Mất các giá trị lặp | Dùng get và kiểm tra cardinality |
| Không phân biệt field thiếu và field rỗng | Validation sai hoặc bypass | Kiểm tra null, blank và quy tắc field |
| Đọc raw body rồi gọi getFormData | Body đã bị tiêu thụ hoặc không còn đọc được như mong đợi | Chọn một cơ chế đọc và truyền kết quả |
| Gọi block/subscribe trong controller | Chặn event loop hoặc tạo subscription phụ | Ghép logic trong Mono/Flux và trả publisher |
| Tăng maxInMemorySize quá cao | Nhiều request đồng thời có thể gây áp lực bộ nhớ | Giới hạn form và xử lý dữ liệu lớn bằng streaming |
| Log toàn bộ form | Lộ password, token và dữ liệu cá nhân | Log metadata đã lọc/che |
| Tin role/tenant từ form | Người dùng có thể tự nâng quyền | Xác thực principal và authorization phía server |
| Nhầm URL-encoded với multipart | Không xử lý đúng file upload | Dùng multipart reader, FilePart hoặc PartEvent |
| Gọi URLDecoder thêm lần nữa | Giải mã kép, thay đổi dấu cộng/percent sequence | Dùng giá trị đã được FormHttpMessageReader giải mã |
| Coi form URL-encoded là mã hóa an toàn | Dữ liệu vẫn có thể bị đọc trên kết nối không bảo mật | Dùng HTTPS/TLS |

## 13. Checklist khi dùng getFormData()

Trước khi triển khai endpoint, hãy kiểm tra:

1. **Media type:** client gửi `application/x-www-form-urlencoded` và mapping khai báo consumes đúng chưa?
2. **Nguồn dữ liệu:** field nằm trong body hay query string? Có đọc từ đúng API không?
3. **Cardinality:** field là đơn trị hay đa trị? Có cần từ chối key bị lặp?
4. **Giá trị thiếu:** phân biệt null, chuỗi rỗng và giá trị hợp lệ chưa?
5. **Encoding:** UTF-8 và percent encoding có được xử lý đúng không?
6. **Body lifecycle:** có thành phần nào đọc raw body trước getFormData không?
7. **Memory:** maxInMemorySize và giới hạn body có phù hợp kích thước form không?
8. **Validation:** có kiểm tra độ dài, định dạng và quy tắc nghiệp vụ không?
9. **Security:** có bảo vệ CSRF, authorization, HTTPS và che dữ liệu nhạy cảm không?
10. **Test:** WebTestClient đã kiểm tra Unicode, field lặp, field thiếu, query/body tách biệt và media type sai chưa?

**Ghi nhớ:** `ServerWebExchange.getFormData()` là cách trực tiếp và reactive để đọc `application/x-www-form-urlencoded` trong WebFlux. Kết quả là `Mono<MultiValueMap<String, String>>`, cho phép lấy giá trị đơn bằng getFirst hoặc giữ các giá trị lặp bằng get. Form body và query parameter là hai nguồn riêng; hãy để `FormHttpMessageReader` xử lý encoding, kiểm soát kích thước body, xác thực dữ liệu và giữ request body trong đúng một lifecycle.

## Tài liệu tham khảo

- Spring Framework — WebFlux Form Data: https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/form-data.html
- Spring Framework — ServerWebExchange API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/web/server/ServerWebExchange.html
- Spring Framework — FormHttpMessageReader API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/http/codec/FormHttpMessageReader.html
- Spring Framework — WebFlux HTTP Message Codecs: https://docs.spring.io/spring-framework/reference/web/webflux/config.html
- Spring Framework — Data Buffers and Codecs: https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html
- Spring Security — CSRF Protection: https://docs.spring.io/spring-security/reference/reactive/exploits/csrf.html
