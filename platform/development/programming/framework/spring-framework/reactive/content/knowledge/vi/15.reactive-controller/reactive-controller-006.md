# Đọc `@RequestBody` dưới dạng đối tượng hoặc publisher trong Spring WebFlux

## 1. Vai trò của @RequestBody trong WebFlux

Trong Spring WebFlux, annotation `@RequestBody` yêu cầu framework đọc HTTP request body và chuyển nội dung đó thành kiểu Java mà controller khai báo. Việc chuyển đổi được thực hiện bởi các **`HttpMessageReader`** (thường được gọi thông qua các codec như Jackson JSON decoder). Reader chọn cách giải mã dựa trên kiểu đích, `Content-Type`, cấu hình codec và dữ liệu nhận được.

Khác biệt quan trọng giữa WebFlux và Spring MVC là WebFlux cho phép tham số `@RequestBody` là **reactive type** như `Mono<T>` hoặc `Flux<T>`. Điều này cho phép đọc body theo mô hình Reactive Streams, không chặn để chờ toàn bộ nội dung trước khi có thể compose với pipeline reactive; WebFlux hỗ trợ cả client-to-server streaming.

Có ba cách khai báo thường gặp:

~~~java
// Một đối tượng được bind trực tiếp:
@PostMapping("/accounts")
public Account handle(@RequestBody Account account) {
    return account;
}

// Một body chứa tối đa một đối tượng:
@PostMapping("/accounts/mono")
public Mono<Account> handle(@RequestBody Mono<Account> account) {
    return account;
}

// Một body chứa nhiều đối tượng:
@PostMapping("/accounts/stream")
public Mono<Long> handle(@RequestBody Flux<Account> accounts) {
    return accounts.count();
}
~~~

Đây là các chữ ký minh họa; controller thật cần annotation, import và kiểu `Account` phù hợp. Chọn kiểu dựa vào **số lượng dữ liệu và cách xử lý**, không chỉ dựa vào việc ứng dụng có dùng WebFlux.

## 2. Đọc body thành một đối tượng Java trực tiếp

Nếu endpoint nhận một JSON object nhỏ, có thể khai báo tham số trực tiếp:

~~~java
@PostMapping(path = "/accounts", consumes = MediaType.APPLICATION_JSON_VALUE)
public AccountView create(@Valid @RequestBody CreateAccountRequest request) {
    return new AccountView(request.name(), request.email());
}
~~~

Với request:

~~~http
POST /accounts
Content-Type: application/json

{"name":"An","email":"an@example.com"}
~~~

Spring WebFlux dùng message reader để giải mã JSON thành `CreateAccountRequest`, sau đó truyền đối tượng vào controller method. Phương thức controller không cần nhận `Mono` chỉ vì ứng dụng đang chạy trên WebFlux.

Đặc điểm:

- Cách khai báo đơn giản, dễ đọc khi nghiệp vụ cần một DTO duy nhất.
- Body được resolve thành đối tượng trước khi controller method được gọi.
- Phù hợp với request có kích thước hữu hạn, được giới hạn hợp lý.
- Có thể dùng `@Valid` hoặc `@Validated` để kích hoạt Bean Validation.
- Nếu cần truy cập lỗi validation trực tiếp qua `Errors` hoặc `BindingResult`, khai báo tham số đó ngay sau tham số body đã được validate.

**Không nên suy luận rằng tham số Java trực tiếp làm WebFlux chuyển sang Servlet blocking I/O.** WebFlux vẫn sử dụng hạ tầng reactive để đọc body; chỉ là chữ ký controller nhận kết quả đã giải mã thành một object thay vì nhận publisher để tiếp tục compose.

## 3. Dùng Mono<T> khi body chứa tối đa một giá trị

Khi muốn giữ việc đọc body trong pipeline reactive, dùng `Mono<T>`:

~~~java
@PostMapping(path = "/accounts/mono", consumes = MediaType.APPLICATION_JSON_VALUE)
public Mono<AccountView> create(@Valid @RequestBody Mono<CreateAccountRequest> body) {
    return body.map(request ->
        new AccountView(request.name(), request.email())
    );
}
~~~

`Mono<CreateAccountRequest>` thể hiện hợp đồng **0 hoặc 1 phần tử** cho mỗi subscription. Đây là lựa chọn tự nhiên cho một JSON object đơn lẻ khi service cần kết hợp thêm các publisher:

~~~java
// Các method service dưới đây là ví dụ giả định.
public Mono<AccountView> create(Mono<CreateAccountRequest> body) {
    return body.flatMap(request ->
        accountService.save(request)
            .map(saved -> new AccountView(saved.id(), saved.name()))
    );
}
~~~

Lợi ích:

- Có thể dùng `map`, `flatMap`, `switchIfEmpty`, `onErrorResume` và các operator khác.
- Có thể phối hợp với reactive repository, `WebClient` hoặc các thao tác bất đồng bộ.
- Không cần gọi `subscribe()` thủ công trong controller; trả publisher để WebFlux quản lý subscription.
- Việc decode và xử lý body nằm trong một chuỗi có thể truyền cancellation và error downstream/upstream.

Một request có body rỗng, body không hợp lệ hoặc không được giải mã thành kiểu yêu cầu không phải lúc nào cũng có cùng ý nghĩa. Hãy xác định rõ endpoint có cho phép body vắng mặt không, kiểu dữ liệu có thể empty không và chính sách HTTP tương ứng. Không dùng `null` làm phần tử reactive; absence được biểu diễn bằng publisher empty.

## 4. Dùng Flux<T> khi body chứa nhiều đối tượng

Nếu client gửi một chuỗi nhiều bản ghi, khai báo `Flux<T>`:

~~~java
@PostMapping("/accounts/import")
public Mono<Long> importAccounts(@RequestBody Flux<CreateAccountRequest> requests) {
    return requests
        .map(request -> new Account(request.name(), request.email()))
        .count();
}
~~~

`Flux<CreateAccountRequest>` thể hiện **0 đến nhiều đối tượng**. Khi dữ liệu được giải mã, các phần tử có thể đi qua pipeline lần lượt. Controller có thể xử lý từng phần tử, áp dụng giới hạn concurrency hoặc truyền từng bản ghi sang service reactive.

Ví dụ xử lý từng bản ghi:

~~~java
// accountService.save(...) trả Mono<Account> trong ứng dụng thật.
@PostMapping("/accounts/import")
public Mono<Long> importAccounts(@RequestBody Flux<CreateAccountRequest> requests) {
    return requests
        .concatMap(accountService::save)
        .count();
}
~~~

`concatMap` xử lý tuần tự và giữ thứ tự nguồn. Nếu nghiệp vụ cho phép xử lý đồng thời, có thể dùng `flatMap(accountService::save, concurrency)` với mức concurrency có giới hạn; thứ tự kết quả khi đó không được bảo đảm giống thứ tự request. Không đặt concurrency quá cao nếu database hoặc dịch vụ downstream có giới hạn kết nối.

**Không gom toàn bộ Flux thành List nếu mục tiêu là streaming dữ liệu lớn.** `collectList()` giữ mọi phần tử trong bộ nhớ rồi mới phát một `Mono<List<T>>`. Chỉ dùng khi batch có giới hạn kích thước và nghiệp vụ thật sự cần toàn bộ danh sách trước khi xử lý.

## 5. JSON object, JSON array và NDJSON

Kiểu Java chỉ nói về cardinality của publisher; định dạng HTTP thực tế còn phụ thuộc `Content-Type` và message reader.

### Một JSON object

Body:

~~~json
{"name":"An","email":"an@example.com"}
~~~

Thông thường dùng `Content-Type: application/json` với `@RequestBody CreateAccountRequest` hoặc `Mono<CreateAccountRequest>`.

### Một JSON array

Body:

~~~json
[
  {"name":"An","email":"an@example.com"},
  {"name":"Binh","email":"binh@example.com"}
]
~~~

Với Jackson decoder trong WebFlux, có thể đọc nhiều đối tượng từ JSON array vào `Flux<CreateAccountRequest>` khi codec và media type được hỗ trợ. Reader giải mã từng JSON object khi nhận đủ dữ liệu cho object đó. Nếu endpoint cần một collection hữu hạn và xử lý toàn bộ như một đơn vị, cũng có thể dùng `Mono<List<CreateAccountRequest>>` hoặc một DTO chứa danh sách.

### NDJSON (Newline Delimited JSON)

NDJSON đặt mỗi JSON object trên một dòng:

~~~text
{"name":"An","email":"an@example.com"}
{"name":"Binh","email":"binh@example.com"}
{"name":"Chi","email":"chi@example.com"}
~~~

Client gửi với:

~~~http
Content-Type: application/x-ndjson
~~~

Đây là định dạng tiện cho streaming nhiều bản ghi: decoder có thể phát mỗi object khi nhận đủ một dòng JSON, thay vì chờ toàn bộ batch kết thúc. Trong Spring Framework, Jackson decoder hỗ trợ các định dạng line-delimited JSON như NDJSON; kiểm tra codec cụ thể nếu thay Jackson bằng thư viện khác.

Bảng chọn nhanh:

| Nội dung HTTP | Kiểu tham số thường dùng | Ghi chú |
| --- | --- | --- |
| Một JSON object | `Account` hoặc `Mono<Account>` | DTO trực tiếp đơn giản; Mono tiện compose reactive |
| JSON array hữu hạn | `Flux<Account>` hoặc `Mono<List<Account>>` | Flux xử lý từng phần tử; List giữ toàn bộ trong RAM |
| NDJSON nhiều dòng | `Flux<Account>` | Phù hợp client-to-server streaming |
| Form URL encoded | Dùng cơ chế form data / `@ModelAttribute` hoặc API tương ứng | Không phải JSON DTO |
| Multipart upload | `@RequestPart`, `Flux<Part>` hoặc API multipart | Cần xử lý lifecycle của file/part |

Không nhầm `application/json` với NDJSON. Cùng là JSON, nhưng JSON array là một document có cấu trúc mảng, còn NDJSON là chuỗi các JSON document độc lập được phân cách bằng newline. Chọn đúng media type giúp client và server thống nhất cách framing dữ liệu.

## 6. Ví dụ hoàn chỉnh Java 17+ với Spring Boot WebFlux

Ví dụ dưới đây có ba endpoint:

- `POST /api/accounts/plain`: đọc một DTO trực tiếp.
- `POST /api/accounts/mono`: đọc một DTO qua `Mono<T>` và dùng Bean Validation.
- `POST /api/accounts/stream`: đọc nhiều DTO qua `Flux<T>` từ NDJSON và xử lý theo luồng.

Tạo cấu trúc:

~~~text
request-body-demo/
├── pom.xml
└── src/main/java/com/example/requestbody/
    ├── RequestBodyApplication.java
    └── AccountController.java
~~~

File `pom.xml` (Spring Boot 3.5.0, Java 17+):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>request-body-demo</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

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
~~~

File `src/main/java/com/example/requestbody/RequestBodyApplication.java`:

~~~java
package com.example.requestbody;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RequestBodyApplication {
    public static void main(String[] args) {
        SpringApplication.run(RequestBodyApplication.class, args);
    }
}
~~~

File `src/main/java/com/example/requestbody/AccountController.java`:

~~~java
package com.example.requestbody;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.*;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/accounts")
public class AccountController {

    public record CreateAccountRequest(
        @NotBlank String name,
        @NotBlank @Email String email
    ) {}

    public record AccountView(String name, String email) {}

    private AccountView toView(CreateAccountRequest request) {
        return new AccountView(request.name(), request.email());
    }

    // 1. Một DTO được bind trực tiếp.
    @PostMapping(
        path = "/plain",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public AccountView plain(@Valid @RequestBody CreateAccountRequest request) {
        return toView(request);
    }

    // 2. Một DTO trong publisher 0..1.
    @PostMapping(
        path = "/mono",
        consumes = MediaType.APPLICATION_JSON_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<AccountView> mono(
            @Valid @RequestBody Mono<CreateAccountRequest> body) {
        return body.map(this::toView);
    }

    // 3. Nhiều DTO trong NDJSON stream.
    @PostMapping(
        path = "/stream",
        consumes = "application/x-ndjson",
        produces = MediaType.TEXT_PLAIN_VALUE
    )
    public Mono<String> stream(
            @RequestBody Flux<CreateAccountRequest> body) {
        return body
            .map(this::toView)
            .count()
            .map(count -> "accepted=" + count);
    }
}
~~~

Chạy từ thư mục `request-body-demo` với JDK 17+ và Maven:

~~~bash
mvn spring-boot:run
~~~

### Thử endpoint nhận object trực tiếp

~~~bash
curl -i -X POST http://localhost:8080/api/accounts/plain ^
  -H "Content-Type: application/json" ^
  -d "{"name":"An","email":"an@example.com"}"
~~~

Body JSON dự kiến:

~~~json
{"name":"An","email":"an@example.com"}
~~~

### Thử endpoint nhận Mono

~~~bash
curl -i -X POST http://localhost:8080/api/accounts/mono ^
  -H "Content-Type: application/json" ^
  -d "{"name":"Binh","email":"binh@example.com"}"
~~~

Body JSON dự kiến:

~~~json
{"name":"Binh","email":"binh@example.com"}
~~~

### Thử endpoint nhận Flux từ NDJSON

Tạo file `accounts.ndjson` với nội dung, mỗi JSON object trên một dòng:

~~~text
{"name":"An","email":"an@example.com"}
{"name":"Binh","email":"binh@example.com"}
{"name":"Chi","email":"chi@example.com"}
~~~

Gửi file:

~~~bash
curl -i -X POST http://localhost:8080/api/accounts/stream ^
  -H "Content-Type: application/x-ndjson" ^
  --data-binary "@accounts.ndjson"
~~~

Body response:

~~~text
accepted=3
~~~

Các lệnh trên dùng dấu nối dòng kiểu Windows CMD (`^`). Nếu chạy Bash hoặc shell khác, có thể viết lệnh trên một dòng hoặc thay ký tự nối dòng phù hợp.

**Điều ví dụ chứng minh:**

1. Cùng một DTO có thể nhận dưới dạng object trực tiếp hoặc `Mono<CreateAccountRequest>`.
2. `Mono` cho phép dùng `map` để biến đổi kết quả giải mã mà không subscribe thủ công.
3. `Flux` nhận nhiều record; endpoint stream chỉ đếm số record sau khi nguồn hoàn tất, không cần gom tất cả vào một List.
4. Với endpoint stream, `Content-Type` phải khớp media type mà mapping và codec hỗ trợ.
5. Ví dụ không lưu database; trong ứng dụng thật, thay `toView` bằng service reactive và chọn `concatMap` hoặc `flatMap` theo yêu cầu thứ tự/concurrency.

## 7. Validation khi dùng @RequestBody

Spring WebFlux hỗ trợ `@Valid` và `@Validated` trên `@RequestBody`. Với một DTO trực tiếp:

~~~java
@PostMapping("/accounts")
public AccountView create(@Valid @RequestBody CreateAccountRequest request) {
    return toView(request);
}
~~~

Nếu `name` rỗng hoặc `email` không đúng định dạng, Bean Validation báo lỗi. Mặc định lỗi bind/validation của request body được thể hiện bằng `WebExchangeBindException` và ánh xạ thành HTTP **400 Bad Request**.

Với reactive wrapper, có thể khai báo:

~~~java
@PostMapping("/accounts")
public Mono<AccountView> create(
        @Valid @RequestBody Mono<CreateAccountRequest> body) {
    return body.map(this::toView)
        .onErrorResume(WebExchangeBindException.class, error -> {
            // Có thể chuyển thành response domain-specific hoặc để
            // exception handler toàn cục xử lý.
            return Mono.error(error);
        });
}
~~~

Đoạn này minh họa nơi lỗi validation có thể đi qua reactive chain. Nếu không cần xử lý riêng, không cần thêm `onErrorResume`; để exception handler mặc định hoặc `@ControllerAdvice` quản lý lỗi là đủ.

Nếu khai báo `Errors` hoặc `BindingResult` để đọc lỗi ngay trong method, tham số đó phải nằm ngay sau DTO đã validate. Theo hợp đồng WebFlux, khi dùng cách này body **không được khai báo là `Mono`** và được resolve trước khi method được gọi.

Với `Flux<T>` nhiều bản ghi, cần xác định rõ chính sách validation theo từng record. Có thể inject `jakarta.validation.Validator` và gọi `validator.validate(record)` bên trong pipeline, sau đó chuyển vi phạm thành lỗi domain. Nếu muốn bỏ qua một record không hợp lệ, phải thể hiện chính sách đó rõ ràng; không tự động nuốt mọi lỗi vì có thể làm mất dữ liệu.

## 8. Content-Type, codec và các lỗi HTTP

`@RequestBody` không tự phân tích mọi định dạng. Framework chọn `HttpMessageReader` tương thích với target type và media type. Những lỗi phổ biến:

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra |
| --- | --- | --- |
| HTTP 415 Unsupported Media Type | Client gửi `Content-Type` không có reader phù hợp hoặc không khớp mapping `consumes` | Kiểm tra header, `consumes` và codec đã đăng ký |
| HTTP 400 Bad Request | JSON sai cú pháp, kiểu dữ liệu không chuyển đổi được hoặc validation thất bại | Kiểm tra body, DTO, enum/date format và BindingResult |
| Body empty / không có kết quả | Client không gửi body, publisher hoàn tất rỗng hoặc endpoint cho phép absence | Xác định hợp đồng body bắt buộc hay tùy chọn |
| `Flux<T>` không giải mã như kỳ vọng | Sai framing/media type hoặc decoder không hỗ trợ kiểu dữ liệu | Thử JSON array/NDJSON và kiểm tra codec cụ thể |
| Lỗi bộ nhớ với body lớn | Gom dữ liệu vào collection hoặc giới hạn codec không phù hợp | Xử lý theo stream, đặt giới hạn kích thước và concurrency |
| Dữ liệu bị đọc hai lần | Nhiều thành phần cùng tiêu thụ request body one-shot | Chỉ định một nơi sở hữu body hoặc cache có giới hạn theo thiết kế |

`Content-Type` mô tả định dạng body client **đang gửi**; `Accept` mô tả định dạng response client **muốn nhận**. Không dùng `Accept` để thay thế `Content-Type` khi gửi JSON hoặc NDJSON.

Các codec mặc định của WebFlux hỗ trợ nhiều loại như JSON, text, byte array, form và multipart tùy dependency. Có thể cấu hình qua `ServerCodecConfigurer`, ví dụ giới hạn bộ nhớ giải mã JSON hoặc đăng ký reader riêng. Khi tăng `maxInMemorySize`, cần cân nhắc kích thước request và số request đồng thời, vì một giới hạn lớn có thể làm tăng áp lực RAM.

## 9. Request body là stream một lần: không subscribe hoặc block thủ công

Body reactive được framework cấp cho controller theo vòng đời request. Tránh các mẫu:

~~~java
// Sai: tự subscribe, tách công việc khỏi lifecycle của HTTP request.
@PostMapping("/bad")
public Mono<Void> bad(@RequestBody Flux<CreateAccountRequest> body) {
    body.subscribe(this::save);
    return Mono.empty();
}

// Sai: block để lấy giá trị đồng bộ trong đường xử lý WebFlux.
@PostMapping("/also-bad")
public AccountView alsoBad(@RequestBody Mono<CreateAccountRequest> body) {
    CreateAccountRequest request = body.block();
    return toView(request);
}
~~~

Các ví dụ trên cố ý minh họa anti-pattern. `subscribe()` tạo subscription riêng và có thể khiến controller trả response trước khi công việc xong; cancellation/error của request không còn quản lý đúng pipeline tự tạo. `block()` chờ đồng bộ, có thể chặn event-loop và làm giảm khả năng phục vụ các request khác.

Cách đúng là **compose và trả publisher**:

~~~java
@PostMapping("/good")
public Mono<Void> good(@RequestBody Flux<CreateAccountRequest> body) {
    return body.concatMap(accountService::save).then();
}
~~~

Nếu cần kiểm tra request body ở filter, logging middleware hoặc nhiều component, không nên mỗi nơi tự đọc raw body. Hãy thiết kế một nơi sở hữu body, dùng request decorator/cache có giới hạn khi thực sự cần, và giữ nguyên semantics backpressure/cancellation. Với form data, dùng API `ServerWebExchange.getFormData()` nhất quán; sau khi parse/cache form, không chuyển sang đọc raw body lần nữa như một nguồn độc lập.

## 10. Backpressure và xử lý body lớn

Khi dùng `Flux<T>`, downstream có thể yêu cầu dữ liệu theo nhu cầu thông qua Reactive Streams. Điều này giúp pipeline điều tiết việc đọc và xử lý body, nhưng không có nghĩa mọi codec, proxy hoặc client đều không buffer. Cần thiết kế toàn bộ đường đi:

- Giới hạn kích thước request ở server/gateway và giới hạn bộ nhớ của codec.
- Tránh `collectList()` với batch không giới hạn.
- Chọn concurrency hữu hạn nếu lưu/gọi downstream cho từng record.
- Xử lý cancellation khi client ngắt kết nối.
- Có timeout, giới hạn tốc độ và phản hồi lỗi rõ ràng.
- Theo dõi memory, connection pool, latency, số record nhận được và số record lưu thành công.

Nếu cần xử lý theo thứ tự:

~~~java
return body.concatMap(accountService::save).then();
~~~

Nếu cho phép xử lý đồng thời có giới hạn:

~~~java
return body.flatMap(accountService::save, 8).then();
~~~

Số `8` chỉ là ví dụ concurrency; chọn theo connection pool và khả năng downstream, không coi là giá trị mặc định tối ưu. `flatMap` có thể hoàn thành inner publisher theo thứ tự khác với thứ tự nhận body.

### Khi nào cần xử lý DataBuffer trực tiếp?

Thông thường hãy để codec giải mã JSON thành DTO. Không cần tự giữ hoặc release `DataBuffer` trong controller dùng `@RequestBody Mono<DTO>` hoặc `Flux<DTO>`.

Chỉ khi xử lý raw `Flux<DataBuffer>`, viết custom codec hoặc tự giữ buffer, mới cần chú ý lifecycle. Trên một số server như Reactor Netty, buffer có thể được pool và reference-counted. Nếu ứng dụng tự tiêu thụ/giữ buffer, phải release đúng lúc bằng `DataBufferUtils.release(...)`; khi dùng operator có thể discard buffer, cần xử lý discard đúng cách, ví dụ `doOnDiscard(DataBuffer.class, DataBufferUtils::release)` trong pipeline phù hợp. Nếu dùng codec chuẩn, việc quản lý buffer thường do framework thực hiện.

## 11. So sánh @RequestBody với @RequestPart và WebClient

Đừng dùng `@RequestBody` cho mọi kiểu request:

- **JSON/XML body**: thường dùng `@RequestBody` và DTO hoặc reactive wrapper.
- **Multipart form**: dùng `@RequestPart` cho từng part, hoặc API multipart của `ServerWebExchange`; file part có lifecycle riêng.
- **Query/form parameters**: dùng `@RequestParam`, `@ModelAttribute` hoặc `getFormData()` phù hợp.
- **Raw byte stream**: có thể dùng `Flux<DataBuffer>` khi thật sự cần tự xử lý byte, nhưng phải quản lý release.
- **Client gửi request**: `WebClient.bodyValue(object)` cho giá trị đã có; `WebClient.body(publisher, Type.class)` cho `Mono`/`Flux` đang phát dữ liệu.

Ví dụ phía client:

~~~java
// Gửi một DTO có sẵn.
webClient.post()
    .uri("/api/accounts/plain")
    .contentType(MediaType.APPLICATION_JSON)
    .bodyValue(account)
    .retrieve()
    .bodyToMono(AccountView.class);

// Gửi một publisher nhiều DTO.
webClient.post()
    .uri("/api/accounts/stream")
    .contentType(MediaType.APPLICATION_NDJSON)
    .body(accountFlux, CreateAccountRequest.class)
    .retrieve()
    .bodyToMono(String.class);
~~~

Đây là đoạn minh họa trong service có `WebClient`, `account` và `accountFlux` được định nghĩa. `bodyValue` dành cho object có sẵn; `body` nhận publisher. Media type của client phải khớp `consumes` phía server.

## 12. Các lỗi thường gặp và cách tránh

1. **Dùng `Mono<T>` cho một body nhiều bản ghi:** hợp đồng cardinality không khớp. Dùng `Flux<T>` hoặc `Mono<List<T>>` nếu thật sự cần danh sách đầy đủ.
2. **Dùng `Flux<T>` rồi `collectList()` cho stream không giới hạn:** vô hiệu lợi ích xử lý từng phần tử và có thể tăng RAM không giới hạn. Xử lý theo dòng hoặc chia batch hữu hạn.
3. **Cho rằng DTO trực tiếp trong WebFlux là blocking:** body vẫn được đọc qua hạ tầng reactive; chọn DTO trực tiếp khi method cần một object, chọn Mono khi muốn compose.
4. **Gửi NDJSON nhưng đặt `Content-Type: application/json`:** client và server có thể hiểu framing khác nhau. Dùng media type tương ứng với format đã chọn.
5. **Gửi JSON object vào endpoint mong đợi `Flux<T>` của nhiều phần tử:** payload không đáp ứng schema/framing của endpoint. Thống nhất object, array hay NDJSON.
6. **Quên `consumes`:** endpoint có thể nhận nhầm hoặc từ chối media type không mong đợi. Khai báo `consumes` và gửi header đúng.
7. **Tự `subscribe()` trong controller:** tách pipeline khỏi request lifecycle, làm cancellation và lỗi khó quản lý. Trả publisher.
8. **Gọi `block()` trên event-loop:** chặn thread chia sẻ. Dùng `map`/`flatMap` và trả `Mono`/`Flux`.
9. **Đọc body từ nhiều nơi:** request body là stream one-shot. Thiết kế một nơi tiêu thụ hoặc cache có giới hạn.
10. **Cho rằng `@Valid` tự xử lý mọi validation của từng item Flux theo cùng cách với DTO đơn:** cần xác định rõ cách validate mỗi record và cách chuyển lỗi trong pipeline.
11. **Nuốt lỗi giải mã/validation:** có thể trả thành công dù request không hợp lệ. Giữ error signal hoặc chuyển thành response domain-specific.
12. **Không xử lý client cancel khi stream lớn:** công việc upstream có thể tiếp tục nếu nguồn ngoài không hỗ trợ cancellation. Gắn cleanup cho resource và dùng API reactive có thể hủy.
13. **Tự giữ DataBuffer nhưng quên release:** có thể gây memory leak, đặc biệt với pooled buffer. Ưu tiên DTO codec; nếu tự quản lý buffer, tuân thủ lifecycle.
14. **Tăng maxInMemorySize vô điều kiện:** có thể làm tăng RAM khi nhiều request lớn chạy đồng thời. Đặt giới hạn theo workload và gateway/server policy.
15. **Dùng flatMap mà giả định thứ tự:** inner publisher có thể hoàn tất không theo thứ tự đầu vào. Dùng concatMap nếu nghiệp vụ yêu cầu tuần tự.

## 13. Checklist thiết kế endpoint nhận body

Trước khi viết controller, trả lời các câu hỏi sau:

- Body chứa **một object**, một **collection hữu hạn**, hay một **stream nhiều record**?
- Client gửi `application/json`, JSON array hay `application/x-ndjson`?
- Controller cần DTO trực tiếp, `Mono<T>`, `Flux<T>` hay `Mono<List<T>>`?
- Có cần Bean Validation? Lỗi validation sẽ trả 400 theo mặc định hay cần mapping riêng?
- Nếu body rỗng, endpoint coi đó là lỗi, absence hay danh sách rỗng?
- Có cần giữ thứ tự xử lý? Nếu có, dùng `concatMap`; nếu xử lý đồng thời, giới hạn concurrency.
- Có giới hạn payload, memory codec, batch size và tốc độ gửi không?
- Khi client hủy request, upstream và resource có dừng/dọn không?
- Có đang đọc body nhiều lần hoặc tự subscribe/block không?
- Có thật sự cần `DataBuffer` raw hay codec có thể giải mã thẳng DTO?

## 14. Câu hỏi tự kiểm tra

**1.** `@RequestBody Account account` có dùng được trong WebFlux không? **Có.** WebFlux có thể giải mã body thành object trực tiếp qua `HttpMessageReader`.

**2.** Khi nào chọn `Mono<Account>`? Khi body chứa tối đa một Account và muốn giữ việc đọc/biến đổi trong reactive pipeline.

**3.** Khi nào chọn `Flux<Account>`? Khi body có nhiều Account và cần xử lý theo stream, chẳng hạn NDJSON hoặc JSON array với codec hỗ trợ.

**4.** `Mono<List<Account>>` khác `Flux<Account>` ở điểm nào? Mono phát một List sau khi gom; Flux phát từng Account. List cần giữ toàn bộ phần tử trong bộ nhớ.

**5.** `@RequestBody` dùng thành phần nào để giải mã? Các `HttpMessageReader` và codec phù hợp với target type và Content-Type.

**6.** WebFlux xử lý validation lỗi trên `@Valid @RequestBody` thế nào? Thông thường phát `WebExchangeBindException`, được ánh xạ thành HTTP 400 Bad Request.

**7.** Vì sao không tự subscribe vào `Flux` body trong controller? Vì sẽ tách công việc khỏi subscription do WebFlux quản lý và làm sai cancellation/error lifecycle.

**8.** Khi gửi NDJSON, Content-Type nên là gì? `application/x-ndjson` theo media type NDJSON được Spring hỗ trợ.

**9.** Khi nào phải tự release DataBuffer? Khi tự xử lý/giữ raw buffer hoặc xây custom codec; với DTO được codec chuẩn giải mã, framework thường quản lý.

**10.** Muốn xử lý stream tuần tự thì dùng operator nào? `concatMap`; `flatMap` phù hợp khi cho phép inner publisher chạy đồng thời với concurrency được kiểm soát.

**Ghi nhớ:** `@RequestBody` trong WebFlux có thể nhận **object trực tiếp**, **`Mono<T>` cho một giá trị**, hoặc **`Flux<T>` cho nhiều giá trị**. Message reader/codec giải mã body theo kiểu đích và `Content-Type`. Dùng Mono/Flux khi muốn compose non-blocking và streaming; chọn JSON/NDJSON đúng hợp đồng, giữ body trong một pipeline do WebFlux quản lý, và kiểm soát validation, backpressure, kích thước request cùng cancellation.

**Tài liệu chính thức:** [Spring Framework 6.2 — @RequestBody trong WebFlux](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html); [Spring Framework 6.2 — Reactive Core, Jackson codecs](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/reactive-spring.html); [Spring Framework 6.2 — Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/6.2/core/databuffer-codec.html).