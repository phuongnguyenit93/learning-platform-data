# @Valid hoặc @Validated với đối tượng request trong Spring WebFlux

## 1. Bài toán: request đã bind nhưng dữ liệu có hợp lệ?

Với Spring WebFlux, một client có thể gửi JSON để tạo đơn đăng ký:

```http
POST /tickets/sync HTTP/1.1
Content-Type: application/json

{
  "title": "",
  "copies": 0,
  "owner": {"email": ""}
}
```

Đây là JSON có thể giải mã thành đối tượng Java, nhưng **không đạt hợp đồng dữ liệu**: tiêu đề trống, số lượng nhỏ hơn 1 và email của người đăng ký rỗng. Đọc JSON thành công không đồng nghĩa validation thành công.

Spring WebFlux có thể áp dụng **Jakarta Validation** khi controller khai báo:

```java
@PostMapping("/tickets")
public Mono<TicketView> create(
        @Valid @RequestBody TicketRequest request) {
    // ...
}
```

hoặc dùng Spring `@Validated` để chọn validation groups:

```java
@PostMapping("/tickets/publish")
public Mono<TicketView> publish(
        @Validated(Publish.class)
        @RequestBody TicketRequest request) {
    // ...
}
```

Các đoạn trên chỉ minh họa chữ ký; `TicketRequest`, `TicketView` và `Publish` cần được định nghĩa. Chúng giúp trả lời các câu hỏi quan trọng:

- `@Valid` và `@Validated` giống và khác nhau ở đâu?
- Annotation cần đặt **trên request parameter**, trên field/record component hay trên class controller?
- Dùng `@RequestBody TicketRequest` hay `@RequestBody Mono<TicketRequest>` thì thời điểm validation và bắt lỗi thay đổi thế nào?
- Khi nào lỗi là `WebExchangeBindException` và khi nào là `HandlerMethodValidationException`?
- Dùng `@ModelAttribute`, `@RequestPart`, `BindingResult` hoặc groups ra sao?
- Test bằng `WebTestClient` thế nào để phân biệt JSON parse, missing body, field invalid và method constraints?

**Phạm vi:** Spring WebFlux trên reactive stack, Java 17+, Spring Framework 6.1+/6.2.x và Jakarta Validation (`jakarta.validation.*`); ví dụ chạy bằng Spring Boot 3.5.6. `Mono`/`Flux` của Reactor là kiểu publisher; không dùng `MockMvc` hoặc `MultipartFile` của Servlet MVC để thay thế các API WebFlux.

## 2. Ba tầng khác nhau: decode, binding và validation

Một request body đi qua luồng khái niệm:

```text
HTTP request
    |
    v
Router/DispatcherHandler (WebFlux annotated controller)
    |
    v
HttpMessageReader đọc JSON theo Content-Type
    |
    v
Tạo TicketRequest qua Jackson
    |
    v
Jakarta Validation nếu parameter có @Valid/@Validated
    |
    +-- valid --> gọi handler (hoặc phát hành value trên Mono)
    |
    +-- invalid --> WebExchangeBindException (thường HTTP 400)
    |
    v
Handler trả Mono/Flux/giá trị
    |
    v
Response writer
```

Ba loại lỗi cần tách rõ:

1. **Đọc/binding thất bại:** JSON sai cú pháp, type không chuyển được, body thiếu, content type không hỗ trợ. Điều này thường thuộc lỗi decoding / `ServerWebInputException` hoặc nhóm lỗi WebFlux khác; không nhất thiết sinh một `ConstraintViolation`.
2. **Validation request object thất bại:** JSON giải mã được nhưng `@NotBlank`, `@Min`, `@NotNull`, cascade `@Valid`... phát hiện vi phạm. Với individual argument validation thông thường, WebFlux sinh `WebExchangeBindException`.
3. **Method validation thất bại:** Có direct `@Constraint` trên handler parameter hoặc return value, ví dụ `@Min(1) @RequestParam int copies`. WebFlux built-in method validation có thể xử lý toàn bộ method và sinh `HandlerMethodValidationException`.

**Quan trọng:** Cả hai loại exception validation đều có thể tạo status **400** cho input sai, nhưng bộ máy và cấu trúc kết quả khác nhau. Nếu có constraint trên return value của handler, vi phạm hậu điều kiện không nên biến thành lỗi 400 do người dùng.

## 3. `@Valid` và `@Validated`: bản chất, vị trí và groups

### 3.1. `@Valid` thuộc Jakarta Validation

Import chuẩn của Spring Boot 3+:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
```

`@Valid` yêu cầu **cascaded validation** vào object. Spring WebFlux nhận biết `@Valid` trên một request argument để kích hoạt validation sau khi đã deserialize/bind. Các quy tắc cụ thể nằm trên kiểu DTO:

```java
public record CreateUser(
        @NotBlank String name,
        @Min(18) int age) {
}
```

Nếu controller có `@Valid @RequestBody CreateUser request`, provider sẽ đánh giá `name` và `age`. `@Valid` không phải `@NotNull`: bản thân annotation `@Valid` không có message, min/max hay validator kiểm tra “bắt buộc có đối tượng”.

Với DTO lồng nhau:

```java
public record Address(@NotBlank String city) {}

public record CreateUser(
        @NotBlank String name,
        @Valid @NotNull Address address) {}
```

`@NotNull` yêu cầu `address` không null; `@Valid` đi sâu vào `Address.city`. Nếu chỉ đặt `@Valid` mà không có `@NotNull`, một thuộc tính null thường được bỏ qua khi cascade (nếu nghiệp vụ cấm null, cần constraint riêng).

### 3.2. `@Validated` của Spring có thể chọn groups

Import:

```java
import org.springframework.validation.annotation.Validated;
```

`@Validated` trên một **request argument** cũng kích hoạt validation, đồng thời hỗ trợ truyền group/hint:

```java
@PostMapping("/publish")
public Mono<ResponseEntity<?>> publish(
        @Validated(Publish.class)
        @RequestBody ArticleRequest body) {
    // ...
}
```

Ví dụ định nghĩa group riêng:

```java
public interface Publish {}

public record ArticleRequest(
        @NotBlank String title,
        @NotBlank(groups = Publish.class) String reference) {}
```

Nếu chỉ yêu cầu `Publish.class`, constraint `@NotBlank` trên `title` thuộc group `Default` **không tự động chạy**, trừ khi có quan hệ group inheritance/sequence. Điều này rất dễ tạo lỗ hổng kiểm tra khi mới học groups.

Muốn cả quy tắc cơ bản và quy tắc của bước publish:

```java
@Validated({Default.class, Publish.class})
@RequestBody ArticleRequest body
```

với import `jakarta.validation.groups.Default` và `Publish` ở phạm vi phù hợp. `@Validated` không “mạnh hơn” `@Valid` về số lượng constraint; nó giúp **chọn nhóm**.

### 3.3. Không nhầm `@Validated` trên parameter với class-level AOP

```java
@RestController
@Validated
class UserController {
    // ...
}
```

Đặt `@Validated` **trên class controller** có ý nghĩa khác: khi Spring cấu hình `MethodValidationPostProcessor`, controller có thể được method validation qua **AOP proxy**. Trong Spring Framework 6.1+ có built-in method validation cho handler, tài liệu Spring khuyên **bỏ class-level `@Validated` khỏi controller** nếu muốn dùng cơ chế method validation tích hợp của WebFlux.

Ngược lại, `@Validated(Create.class)` **trên riêng `@RequestBody`** là lựa chọn groups của DTO, không đồng nghĩa phải tạo AOP proxy. Đừng lẫn điều này với Spring `@Service @Validated` ở tầng service.

## 4. Chọn request argument đúng trong WebFlux

### 4.1. `@Valid @RequestBody Dto` (đối tượng trực tiếp)

```java
@PostMapping("/sync")
public Mono<String> sync(
        @Valid @RequestBody TicketRequest request) {

    return Mono.just(request.title());
}
```

Spring WebFlux đọc request body bằng `HttpMessageReader` (thường JSON/Jackson), tạo đối tượng, rồi kiểm tra constraint trước khi gọi handler theo cách resolution của non-reactive argument. Với dữ liệu sai, thường nhận `WebExchangeBindException`, mặc định là HTTP 400. Giá trị return `Mono<String>` **không bắt buộc** request parameter phải là `Mono<Dto>`.

Ưu điểm: chữ ký dễ đọc, thuận tiện khi business logic đơn giản. Lưu ý: việc parse/bind để có `Dto` xảy ra trước invocation của handler; controller chưa thể dùng operator trên request body để bắt lỗi xảy ra trước đó.

### 4.2. `@Valid @RequestBody Mono<Dto>` (publisher request)

```java
@PostMapping("/reactive")
public Mono<String> reactive(
        @Valid @RequestBody Mono<TicketRequest> ticketMono) {

    return ticketMono.map(TicketRequest::title)
            .onErrorResume(WebExchangeBindException.class,
                    ex -> Mono.just("invalid"));
}
```

WebFlux hỗ trợ đọc body thành reactive type. Trong kiểu khai báo này, việc decode/validation có thể tạo lỗi **bên trong publisher**; handler có thể xử lý bằng `onErrorResume` hoặc các operator khác, miễn là chain đó **được trả về** và được subscribe đúng bởi runtime.

**Không gọi `.block()`** bên trong WebFlux handler chỉ để lấy DTO: làm vậy có thể chặn event-loop, giảm throughput hoặc gây lỗi runtime. Sử dụng `map`/`flatMap`/`onErrorResume` để kết hợp logic không đồng bộ. `@Valid` vẫn có ý nghĩa trên argument `Mono<Dto>` theo hợp đồng WebFlux request binding; khác biệt lớn là **đường truyền lỗi**.

Lưu ý phạm vi: các ví dụ request-body validation chủ yếu dùng một request DTO. Với `Flux<Dto>`/JSON streaming hoặc constraint trên từng phần tử của collection, cần xem chính xác cấu trúc message reader và validator của version dùng; không suy luận rằng một `List<@Valid Dto>` hoặc mọi phần tử `Flux` đều được validate hệt cách trên trong mọi configuration.

### 4.3. `@Valid @ModelAttribute Dto` (form/query binding)

```java
@PostMapping(path = "/form",
             consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
public Mono<ResponseEntity<?>> form(
        @Valid @ModelAttribute TicketForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return Mono.just(ResponseEntity.badRequest().build());
    }
    return Mono.just(ResponseEntity.ok().build());
}
```

`@ModelAttribute` trong WebFlux bind form fields, query parameters và các giá trị request có liên quan thông qua `WebDataBinder`. `BindingResult` được đặt **ngay sau** đối tượng cần validate, cho phép controller tự xử lý lỗi **thay vì ném exception**. Với `@ModelAttribute Mono<TicketForm>`, phải xử lý lỗi qua publisher thay vì đặt `BindingResult` cạnh một reactive wrapper.

Vì `TicketForm` ở đây chưa định nghĩa, đây là fragment minh họa. Phần ví dụ chạy đầy đủ sẽ có class `TicketForm` thật.

### 4.4. `@Valid @RequestPart Dto` (JSON part của multipart)

```java
@PostMapping(path = "/multipart",
             consumes = MediaType.MULTIPART_FORM_DATA_VALUE)
public Mono<String> multipart(
        @Valid @RequestPart("metadata") Metadata metadata,
        @RequestPart("file") FilePart file) {

    return Mono.just(metadata.label());
}
```

Dùng `@RequestPart` nếu client gửi một part `metadata` với `Content-Type: application/json` và một file part. WebFlux dùng `FilePart`/`Part`, **không phải `MultipartFile` của Servlet MVC**. `@Valid` trên metadata kích hoạt validation sau conversion. Đây là fragment minh họa; `Metadata` phải được định nghĩa và cần import `org.springframework.http.codec.multipart.FilePart`.

Không áp `@NotBlank` trực tiếp lên `FilePart`: `@NotBlank` dành cho `CharSequence`. Nếu cần giới hạn kích thước hoặc kiểm tra nội dung file, thiết kế một bước xác minh riêng theo luồng reactive và giới hạn decoder/upload thích hợp.

## 5. Bảng lựa chọn nhanh

| Dữ liệu vào | Khai báo phù hợp | Cơ chế validation |
| --- | --- | --- |
| Một JSON DTO | `@Valid @RequestBody CreateDto dto` | Bean Validation trên DTO trước invocation |
| Một JSON DTO đọc reactive | `@Valid @RequestBody Mono<CreateDto> dtoMono` | Validation khi publisher được consume; bắt `WebExchangeBindException` bằng operator |
| JSON DTO với groups | `@Validated({Default.class, Publish.class}) @RequestBody CreateDto` | Bean Validation với groups được chọn |
| Form/query object | `@Valid @ModelAttribute FormDto` | WebDataBinder + Bean Validation |
| Form và xử lý lỗi tại handler | `@Valid @ModelAttribute FormDto, BindingResult errors` | Cục bộ; `BindingResult` ngay sau DTO |
| JSON part của multipart | `@Valid @RequestPart("metadata") MetaDto` | Converter cho part + Bean Validation |
| Query scalar có direct constraint | `@RequestParam @Min(1) int count` | WebFlux built-in method validation (6.1+) |
| Chỉ trường DTO có constraint, không có `@Valid` ở argument | `@RequestBody CreateDto dto` | Không nên kỳ vọng tự động Bean Validation chỉ nhờ field annotations |
| Service method được quản lý qua Spring AOP | `@Service @Validated` và method constraints | Proxy method validation, không phải request argument resolver |

Bảng trên mô tả trường hợp không có class-level `@Validated` trên controller và provider Jakarta Validation có mặt. Các trường hợp mixed constraints, `BindingResult` hay lỗi decoding có thể thay đổi exception thực tế.

## 6. Điều gì xảy ra khi request thiếu field hoặc chứa giá trị rỗng?

Xét DTO:

```java
public record TicketRequest(
        @NotBlank String title,
        @Min(1) int copies) {}
```

Các request JSON tương ứng:

| JSON | Dữ liệu Java sau decode | Kết quả |
| --- | --- | --- |
| `{"title":"Book","copies":2}` | title = `"Book"`, copies = `2` | Hợp lệ |
| `{"title":"","copies":2}` | title = `""` | `@NotBlank` sai |
| `{"title":"   ","copies":2}` | title toàn khoảng trắng | `@NotBlank` sai |
| `{"copies":2}` | title = `null` | `@NotBlank` sai |
| `{"title":"Book"}` | copies = `0` với primitive `int` | `@Min(1)` sai |
| `{"title":"Book","copies":0}` | copies = `0` | `@Min(1)` sai |
| `{"title":"Book","copies":"abc"}` | Không chuyển được chuỗi thành `int` | Lỗi decoding/binding, không phải vi phạm `@Min` đơn thuần |
| JSON sai cú pháp | Không tạo được object | Lỗi đọc request, chưa tới constraint |

**Chú ý:** Bảng với primitive `int` diễn tả hành vi JSON binding thông thường khi trường số bị thiếu, nhưng Jackson settings, constructors, primitive-null handling và custom deserializer có thể thay đổi cách báo lỗi. Khi cần phân biệt “không gửi copies” và “gửi copies=0”, nên dùng `Integer` + `@NotNull` và `@Min(1)`, hoặc có chính sách parse rõ ràng.

`@Min`/`@Size` thường coi `null` là hợp lệ: để bắt missing, kết hợp `@NotNull`. `@NotBlank` đã cấm `null` và blank cho chuỗi. Không dùng `@NotEmpty` thay `@NotBlank` nếu nghiệp vụ muốn cấm chuỗi toàn whitespace.

### 6.1. Cascade với nested request DTO

```java
public record Owner(@NotBlank String email) {}

public record TicketRequest(
        @NotBlank String title,
        @NotNull @Valid Owner owner) {}
```

- `@NotNull` trên `owner` bắt thiếu object.
- `@Valid` trên `owner` yêu cầu kiểm tra sâu `Owner.email`.
- `@NotBlank` trên `Owner.email` bắt chuỗi rỗng/trắng.
- Nếu chỉ đặt `@NotBlank` trong class `Owner` mà quên `@Valid` ở property cha, validation khi đi từ `TicketRequest` không tự cascade vào nested object.

### 6.2. Collection và phần tử

```java
public record BulkRequest(
        @NotEmpty List<@Valid TicketRequest> tickets) {}
```

Provider kiểm tra container `tickets` có phần tử (`@NotEmpty`), và nhờ `@Valid` trong type argument, cascade từng `TicketRequest`. Cần extractor phù hợp cho collection (provider Jakarta Validation hiện đại có built-in extractors cho List). Nếu muốn **cấm phần tử null**, thêm `@NotNull` vào type argument: `List<@NotNull @Valid TicketRequest>`.

**Không tự đồng nhất** `@Valid List<TicketRequest>` và mọi tình huống `List<@Valid TicketRequest>`: cách đặt annotation, container extraction, nhóm validation và khả năng framework chọn method validation đều cần kiểm tra theo DTO/source/version. Trong thực tế nên sử dụng một wrapper request DTO rõ ràng, nhất là khi API cần nhiều fields và collection-level constraints.

## 7. Ví dụ chạy độc lập: Spring Boot 3.5.6 + WebFlux + Java 17

Ví dụ sau minh họa bốn kịch bản:

1. **Individual DTO validation:** `POST /tickets/sync` dùng `@Valid @RequestBody TicketRequest`.
2. **Validation groups:** `POST /tickets/publish` dùng `@Validated({Default.class, Publish.class})`.
3. **Reactive body validation:** `POST /tickets/reactive` nhận `Mono<TicketRequest>` và xử lý validation error trong reactive chain.
4. **Direct method constraint:** `GET /tickets/count?n=0` dùng `@Min` trên scalar query parameter, cho thấy khác biệt exception.
5. **Form binding:** `POST /tickets/form` dùng `@ModelAttribute` + `BindingResult`.

Ứng dụng chỉ trả dữ liệu minh họa, không truy cập database hay tạo giao dịch. Mục đích là làm rõ **validation boundary**, không thiết kế một hệ thống đặt vé thật.

### 7.1. Cấu trúc thư mục

```text
webflux-request-validation/
├── pom.xml
├── src/main/java/demo/webflux/
│   ├── WebFluxValidationApplication.java
│   ├── TicketRequest.java
│   ├── TicketForm.java
│   ├── TicketController.java
│   └── ValidationErrorAdvice.java
└── src/test/java/demo/webflux/
    └── TicketControllerTest.java
```

### 7.2. File `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>webflux-request-validation</artifactId>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-test</artifactId>
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

**Giải thích:**
- Chỉ dùng `spring-boot-starter-webflux`, **không** thêm `spring-boot-starter-web` cho cùng demo. Nếu cả MVC và WebFlux starters có mặt, Spring Boot thông thường ưu tiên Servlet MVC application type.
- `spring-boot-starter-validation` cung cấp Jakarta Validation provider (thường Hibernate Validator); thiếu provider, đừng coi các annotation validation là đã được áp dụng đúng.
- `spring-boot-starter-test` và `reactor-test` hỗ trợ JUnit/Spring Test và reactive testing. Tất cả phiên bản transitive được Boot parent quản lý.
- Spring Boot `3.5.6` là phiên bản cụ thể đã phát hành thuộc dòng Boot 3.5 và dùng Spring Framework 6.2.x, không nhất thiết là bản mới nhất tại thời điểm bạn đọc.

### 7.3. File `WebFluxValidationApplication.java`

```java
package demo.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(WebFluxValidationApplication.class, args);
    }
}
```

### 7.4. File `TicketRequest.java`

```java
package demo.webflux;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record TicketRequest(
        @NotBlank(message = "title.blank")
        String title,

        @Min(value = 1, message = "copies.min")
        int copies,

        @NotNull(message = "owner.required")
        @Valid
        Owner owner,

        @NotBlank(
                groups = Publish.class,
                message = "reference.blank")
        String reference) {

    public interface Publish {}

    public record Owner(
            @NotBlank(message = "owner.email.blank")
            String email) {}
}
```

- `title`, `copies` và `owner` thuộc nhóm `Default`.
- `reference` thuộc nhóm `TicketRequest.Publish`, chỉ chạy khi group này được yêu cầu.
- `Owner` là nested DTO; `@Valid` ở parent giúp kiểm tra `email`.
- `@NotNull` trên `owner` buộc object phải tồn tại, còn `@Valid` tự nó không thay `@NotNull`.

### 7.5. File `TicketForm.java`

```java
package demo.webflux;

import jakarta.validation.constraints.NotBlank;

public class TicketForm {

    @NotBlank(message = "title.blank")
    private String title;

    public String getTitle() {
        return title;
    }

    public void setTitle(String title) {
        this.title = title;
    }
}
```

DTO này dành cho `application/x-www-form-urlencoded`; Spring WebFlux có thể tạo object qua default constructor rồi bind form field `title` bằng setter.

### 7.6. File `TicketController.java`

```java
package demo.webflux;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.groups.Default;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.support.WebExchangeBindException;
import reactor.core.publisher.Mono;

import java.util.Map;

@RestController
@RequestMapping("/tickets")
public class TicketController {

    // 1. @Valid: kiểm tra nhóm Default của request DTO.
    @PostMapping(
        path = "/sync",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Map<String, Object>> sync(
            @Valid @RequestBody TicketRequest body) {

        return Mono.just(Map.of(
                "title", body.title(),
                "copies", body.copies()));
    }

    // 2. @Validated: thêm group Publish bên cạnh Default.
    @PostMapping(
        path = "/publish",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<Map<String, Object>> publish(
            @Validated({Default.class, TicketRequest.Publish.class})
            @RequestBody TicketRequest body) {

        return Mono.just(Map.of(
                "reference", body.reference(),
                "title", body.title()));
    }

    // 3. Nhận Mono<DTO>, bắt WebExchangeBindException trong chain.
    @PostMapping(
        path = "/reactive",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ResponseEntity<Map<String, Object>>> reactive(
            @Valid @RequestBody Mono<TicketRequest> bodyMono) {

        return bodyMono
                .map(body -> ResponseEntity.ok(
                        Map.<String, Object>of("title", body.title())))
                .onErrorResume(
                        WebExchangeBindException.class,
                        error -> Mono.just(
                                ResponseEntity.badRequest()
                                        .body(Map.<String, Object>of(
                                                "error", "reactive.invalid"))));
    }

    // 4. Direct constraint @Min: handler method validation.
    @GetMapping("/count")
    public Mono<Map<String, Integer>> count(
            @RequestParam("n") @Min(1) int n) {

        return Mono.just(Map.of("n", n));
    }

    // 5. @ModelAttribute + BindingResult xử lý lỗi cục bộ.
    @PostMapping(
        path = "/form",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public Mono<ResponseEntity<Map<String, Object>>> form(
            @Valid @ModelAttribute TicketForm form,
            BindingResult errors) {

        if (errors.hasErrors()) {
            return Mono.just(ResponseEntity.badRequest()
                    .body(Map.<String, Object>of(
                            "error", "form.invalid")));
        }

        return Mono.just(ResponseEntity.ok(
                Map.<String, Object>of("title", form.getTitle())));
    }
}
```

Mã trên **không gắn `@Validated` lên class controller**, để WebFlux 6.2 tự xử lý method validation trên `count()`. Annotation `@Validated` ở **parameter của `publish()`** chỉ quyết định validation groups của `TicketRequest`.

Ở `reactive()`, `Mono<TicketRequest>` chứa nội dung sau deserialize/validation. Operator `onErrorResume(WebExchangeBindException.class, ...)` được dùng để trả lỗi rõ ràng, không chặn event-loop. Ở `sync()`/`publish()`, việc resolve DTO xảy ra trước khi handler được gọi, nên global exception handler sẽ nhận lỗi.

### 7.7. File `ValidationErrorAdvice.java`

```java
package demo.webflux;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.method.annotation.HandlerMethodValidationException;

import java.util.Map;

@RestControllerAdvice
public class ValidationErrorAdvice {

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<Map<String, String>> invalidRequest(
            WebExchangeBindException error) {

        return ResponseEntity.badRequest()
                .body(Map.of("error", "request.invalid"));
    }

    @ExceptionHandler(HandlerMethodValidationException.class)
    public ResponseEntity<Map<String, String>> invalidMethod(
            HandlerMethodValidationException error) {

        return ResponseEntity.status(error.getStatusCode())
                .body(Map.of("error", "method.invalid"));
    }
}
```

Advice minh họa hai loại validation exception:
- `WebExchangeBindException` cho validation của một request DTO; ví dụ trả `{"error":"request.invalid"}`.
- `HandlerMethodValidationException` khi direct constraint `@Min` kích hoạt built-in method validation; `getStatusCode()` phân biệt invalid input (thường 400) với vi phạm return contract (có thể 500).

Những message `"request.invalid"` và `"method.invalid"` do **ứng dụng tự chọn**, không phải body mặc định Spring bắt buộc tạo. Ứng dụng thật nên trả field errors có cấu trúc/`ProblemDetail` với mã ổn định, nhưng không đưa dữ liệu nhạy cảm vào response.

## 8. Kiểm thử đầy đủ bằng `WebTestClient`

Spring WebFlux dùng `WebTestClient` để gửi request và xác minh response. Có thể test qua một mock application context không mở cổng HTTP thật khi dùng `@SpringBootTest` kết hợp `@AutoConfigureWebTestClient`.

### 8.1. File `TicketControllerTest.java`

```java
package demo.webflux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.BodyInserters;

@SpringBootTest
@AutoConfigureWebTestClient
class TicketControllerTest {

    @Autowired
    WebTestClient client;

    private static final String VALID = """
            {
              "title": "Book",
              "copies": 2,
              "owner": {"email": "a@example.com"}
            }
            """;

    @Test
    void validDtoIsAccepted() {
        client.post().uri("/tickets/sync")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(VALID)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.title").isEqualTo("Book")
                .jsonPath("$.copies").isEqualTo(2);
    }

    @Test
    void blankTitleIsRejected() {
        client.post().uri("/tickets/sync")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"title":"  ","copies":2,
                         "owner":{"email":"a@example.com"}}
                        """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.error").isEqualTo("request.invalid");
    }

    @Test
    void quantityBelowMinimumIsRejected() {
        client.post().uri("/tickets/sync")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"title":"Book","copies":0,
                         "owner":{"email":"a@example.com"}}
                        """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.error").isEqualTo("request.invalid");
    }

    @Test
    void nestedOwnerMustBeValid() {
        client.post().uri("/tickets/sync")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"title":"Book","copies":1,
                         "owner":{"email":""}}
                        """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.error").isEqualTo("request.invalid");
    }

    @Test
    void missingOwnerIsRejected() {
        client.post().uri("/tickets/sync")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"title":"Book","copies":1}
                        """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.error").isEqualTo("request.invalid");
    }

    @Test
    void defaultGroupDoesNotRequirePublishReference() {
        client.post().uri("/tickets/sync")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(VALID)
                .exchange()
                .expectStatus().isOk();
    }

    @Test
    void publishGroupRequiresReference() {
        client.post().uri("/tickets/publish")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(VALID)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.error").isEqualTo("request.invalid");
    }

    @Test
    void publishWithReferenceIsAccepted() {
        client.post().uri("/tickets/publish")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"title":"Book","copies":2,
                         "owner":{"email":"a@example.com"},
                         "reference":"T-100"}
                        """)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.reference").isEqualTo("T-100");
    }

    @Test
    void reactiveBodyHandlesInvalidRequestInPipeline() {
        client.post().uri("/tickets/reactive")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("""
                        {"title":"","copies":2,
                         "owner":{"email":"a@example.com"}}
                        """)
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.error").isEqualTo("reactive.invalid");
    }

    @Test
    void reactiveBodyAcceptsValidRequest() {
        client.post().uri("/tickets/reactive")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(VALID)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.title").isEqualTo("Book");
    }

    @Test
    void methodConstraintUsesDifferentValidationBranch() {
        client.get().uri("/tickets/count?n=0")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.error").isEqualTo("method.invalid");
    }

    @Test
    void methodConstraintAcceptsValidQuery() {
        client.get().uri("/tickets/count?n=2")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.n").isEqualTo(2);
    }

    @Test
    void formBindingResultHandlesBlankTitle() {
        client.post().uri("/tickets/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("title", " "))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.error").isEqualTo("form.invalid");
    }

    @Test
    void formAcceptsValidTitle() {
        client.post().uri("/tickets/form")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .body(BodyInserters.fromFormData("title", "Book"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.title").isEqualTo("Book");
    }
}
```

### 8.2. Chạy test

```bash
mvn test
```

**Kết quả dự kiến:** 14 test passes (trong một môi trường Maven/JDK 17 có thể tải dependencies). Các tên test giải thích trực tiếp mỗi tình huống; thứ tự test không được bảo đảm và không cần kiểm tra bằng một stdout cố định.

| Nhóm test | Điều cần chứng minh |
| --- | --- |
| `validDtoIsAccepted` | `@Valid` trên request object chấp nhận input hợp lệ |
| `blankTitleIsRejected`, `quantityBelowMinimumIsRejected` | Field constraints hoạt động sau JSON decode |
| `nestedOwnerMustBeValid`, `missingOwnerIsRejected` | `@Valid` cascade và `@NotNull` bổ sung đúng vai trò |
| `defaultGroupDoesNotRequirePublishReference` | `Default` không tự chạy constraint thuộc `Publish` |
| `publishGroupRequiresReference`, `publishWithReferenceIsAccepted` | `@Validated` chọn cả Default và Publish |
| Hai test reactive body | Lỗi validation của `Mono<DTO>` có thể xử lý bằng `onErrorResume` |
| Hai test direct `@Min` | Handler method validation có nhánh exception riêng |
| Hai test form | `@ModelAttribute` + `BindingResult` xử lý local errors |

Các mã `request.invalid`, `method.invalid`, `reactive.invalid`, `form.invalid` được thiết kế để phân biệt rõ **đường đi lỗi** khi quan sát response JSON.

### 8.3. Vì sao dùng `WebTestClient` thay `MockMvc`?

`WebTestClient` tương thích reactive WebFlux, hỗ trợ kiểm tra status, headers, JSONPath, body và publisher behavior. `MockMvc` thuộc Spring MVC Servlet test infrastructure. Trong một dự án Spring Boot có cả MVC và WebFlux dependencies, cấu hình application type có thể không còn là reactive; để ví dụ dùng đúng WebFlux, chỉ khai báo `spring-boot-starter-webflux` ở phạm vi ứng dụng.

## 9. Thử request bằng `curl`

Khởi động server:

```bash
mvn spring-boot:run
```

### 9.1. Input hợp lệ với `@Valid`

```bash
curl -i -X POST \
  http://localhost:8080/tickets/sync \
  -H 'Content-Type: application/json' \
  -d '{"title":"Book","copies":2,"owner":{"email":"a@example.com"}}'
```

Dự kiến HTTP **200** và body:

```json
{"title":"Book","copies":2}
```

### 9.2. Title rỗng

```bash
curl -i -X POST \
  http://localhost:8080/tickets/sync \
  -H 'Content-Type: application/json' \
  -d '{"title":"","copies":2,"owner":{"email":"a@example.com"}}'
```

Dự kiến HTTP **400** và JSON:

```json
{"error":"request.invalid"}
```

`@NotBlank` trên `title` không đạt; global advice tiếp nhận `WebExchangeBindException`. Nếu xóa `@Valid` khỏi controller argument, ví dụ đó sẽ không còn bảo đảm field validation được kích hoạt theo nhánh request-object thông thường.

### 9.3. Nhóm `Publish` và `reference` bắt buộc

```bash
curl -i -X POST \
  http://localhost:8080/tickets/publish \
  -H 'Content-Type: application/json' \
  -d '{"title":"Book","copies":2,"owner":{"email":"a@example.com"}}'
```

Dự kiến HTTP **400** vì `@Validated({Default.class, Publish.class})` đánh giá thêm `@NotBlank(groups=Publish.class)` trên `reference`. Cùng body gửi sang `/tickets/sync` thì hợp lệ theo `Default`.

### 9.4. Reactive request body có xử lý lỗi local

```bash
curl -i -X POST \
  http://localhost:8080/tickets/reactive \
  -H 'Content-Type: application/json' \
  -d '{"title":"","copies":2,"owner":{"email":"a@example.com"}}'
```

Dự kiến HTTP **400** nhưng body là:

```json
{"error":"reactive.invalid"}
```

Lý do: `bodyMono.onErrorResume(WebExchangeBindException.class, ...)` xử lý tín hiệu lỗi từ publisher. Đây là ngoại lệ được ứng dụng chủ động ánh xạ lại, **không** phải Spring WebFlux bắt buộc mọi controller trả body đó.

### 9.5. Direct scalar constraint

```bash
curl -i 'http://localhost:8080/tickets/count?n=0'
```

Dự kiến HTTP **400**, JSON:

```json
{"error":"method.invalid"}
```

Với Spring WebFlux 6.2, `@Min(1)` đặt trực tiếp trên parameter `n` kích hoạt **method validation** và nhánh `HandlerMethodValidationException`. Nếu chỉ nhìn status 400 thì không biết được request-object validation hay method validation đã chạy.

## 10. Lỗi và exception: nhận diện đúng nguồn

### 10.1. `WebExchangeBindException`

Spring WebFlux thường báo `org.springframework.web.bind.support.WebExchangeBindException` khi một request DTO được bind thành công nhưng validation thất bại. Exception này mang `BindingResult` với `FieldError` và `ObjectError`.

Ví dụ xử lý lỗi cụ thể trong `@RestControllerAdvice`:

```java
@ExceptionHandler(WebExchangeBindException.class)
public ResponseEntity<Map<String, Object>> errors(
        WebExchangeBindException exception) {

    var fields = exception.getFieldErrors().stream()
            .map(e -> Map.of(
                    "field", e.getField(),
                    "message", String.valueOf(e.getDefaultMessage())))
            .toList();

    return ResponseEntity.badRequest()
            .body(Map.of("errors", fields));
}
```

Đây là đoạn thay thế **minh họa** cho handler `invalidRequest()` ở file `ValidationErrorAdvice.java`; cần import Spring/Java collections như trong context. Không thêm một handler trùng kiểu exception trong cùng controller advice. Đừng đưa raw `rejectedValue` ra response khi nó có thể chứa dữ liệu nhạy cảm.

### 10.2. `HandlerMethodValidationException`

Khi một handler method có `@Constraint` **trực tiếp** trên parameter hoặc return value, Spring Framework 6.1+ built-in method validation có thể **thay thế** validation riêng từng argument, bao phủ cả constraints được cascade qua `@Valid`. Trường hợp này sinh `HandlerMethodValidationException`.

Ví dụ:

```java
@PostMapping("/mixed")
public Mono<String> mixed(
        @RequestParam("n") @Min(1) int n,
        @Valid @RequestBody TicketRequest body) {

    return Mono.just(body.title());
}
```

Nếu `n=0` hoặc DTO sai, method validation có thể phát hiện những lỗi phù hợp cùng lúc. `@Valid` đơn lẻ **không phải** direct constraint; nó không tự chuyển một handler chỉ có request DTO sang method validation.

Ngoại lệ `HandlerMethodValidationException` có kết quả theo method parameters; có thể duyệt `getAllValidationResults()` hoặc dùng visitor theo loại argument. Ứng dụng cần biết input failure (thường 400) khác return value failure (thường 500) để không trả lỗi sai ý nghĩa.

### 10.3. Lỗi decode/parse khác validation

| Dữ liệu đầu vào | Điểm thất bại | Loại lỗi thường gặp |
| --- | --- | --- |
| JSON đúng, field `title=""` | Bean Validation | `WebExchangeBindException` nếu handler chỉ cần argument validation |
| Direct `@Min(1)` trên query parameter, n=0 | Handler method validation | `HandlerMethodValidationException` |
| `@RequestBody` bắt buộc nhưng body trống | Request body resolution | `ServerWebInputException`/đường lỗi input tương ứng |
| JSON có cấu trúc sai | Jackson/HttpMessageReader | Lỗi đọc input, thường thuộc `ServerWebInputException` |
| HTTP `Content-Type` không được hỗ trợ | HTTP message codec/content negotiation | `UnsupportedMediaTypeStatusException`, thường 415 |
| Form thiếu field có `@NotBlank` | DTO binding + validation | `WebExchangeBindException` hoặc `BindingResult` local |
| @RequestParam bắt buộc bị thiếu | Argument resolution | Lỗi missing request value, không phải vi phạm `@Min` |

**Không viết `@ExceptionHandler(ValidationException.class)` rồi trả 400 cho tất cả mọi thứ.** Một số loại `ValidationException` là lỗi cấu hình provider hoặc lỗi hợp đồng backend, không phải lỗi dữ liệu request.

## 11. `BindingResult`/`Errors` trong WebFlux

### 11.1. Với non-reactive DTO argument

```java
@PostMapping("/form")
public Mono<ResponseEntity<?>> create(
        @Valid @ModelAttribute TicketForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return Mono.just(ResponseEntity.badRequest().build());
    }
    return Mono.just(ResponseEntity.ok().build());
}
```

Đây là đoạn minh họa. Đối tượng cần validate phải **đặt ngay trước** `BindingResult`. Controller có thể đọc lỗi locally và chọn response thay vì cho exception đi ra. Việc dùng `@Valid @RequestBody Dto` với `Errors` liền sau cũng được WebFlux hỗ trợ trong các tình huống tương ứng; DTO đó không phải `Mono<Dto>`.

### 11.2. Với reactive wrapper `Mono<Dto>`

Không viết kiểu chữ ký:

```java
public Mono<?> bad(
        @Valid @RequestBody Mono<TicketRequest> ticket,
        BindingResult errors) {
    // Không dùng BindingResult ở đây như cho DTO đã resolve.
}
```

Đây là **anti-pattern minh họa**, không phải code đưa vào project. Với reactive request wrapper, việc decode/validation được phát hành bất đồng bộ; `BindingResult` liền sau không thể đóng vai trò “đã resolve xong lỗi” tại thời điểm phương thức được gọi. Hãy dùng `onErrorResume(WebExchangeBindException.class, ...)` hoặc cho exception nổi lên global handler.

### 11.3. Khi method validation được bật

Nếu handler có direct `@Constraint` ở một hoặc nhiều method parameters, Spring method validation có thể kết hợp với `Errors`/`BindingResult`. Tuy nhiên controller chỉ được gọi khi **tất cả** validation errors thuộc những parameters có `Errors` ngay sau để xử lý. Nếu lỗi xuất hiện ở parameter khác không có kênh local errors tương ứng, `HandlerMethodValidationException` có thể được ném.

Không coi `BindingResult` là một “biến bắt mọi lỗi trong method”, và không dùng kết quả của `BindingResult` trong service AOP như thể nó là hợp đồng dành cho Spring WebFlux argument resolver.

## 12. Custom validation groups có ích khi nào?

Ví dụ workflow của một bài đăng:

- **Draft:** cần tiêu đề, có thể chưa có mã tham chiếu.
- **Publish:** cần thêm mã tham chiếu, nhưng vẫn phải tuân thủ quy tắc cơ bản.

Với `TicketRequest`, field `reference` khai báo:

```java
@NotBlank(
    groups = Publish.class,
    message = "reference.blank")
String reference
```

Trong endpoint `/sync` chỉ có `@Valid`, các constraint `Default` chạy, không yêu cầu reference. Endpoint `/publish` dùng:

```java
@Validated({Default.class, TicketRequest.Publish.class})
@RequestBody TicketRequest body
```

thì cả hai bộ quy tắc cùng có hiệu lực.

Đừng mặc định `@Validated(Publish.class)` bao hàm `Default`. Nếu muốn validate theo thứ tự, bước 1 không đạt thì không chạy bước 2, có thể dùng **group sequence** của Jakarta Validation (và cần hiểu quy tắc cascade nhóm). Với một API nhiều trạng thái, định nghĩa group interface là một phần hợp đồng validation; đặt tên nhóm theo lifecycle có ý nghĩa nghiệp vụ thay vì theo controller class.

### 12.1. Groups và nested objects

Nếu DTO cha có `@Valid Owner owner`, provider cascade groups vào nested object theo cơ chế Jakarta Validation. Trong ví dụ đã chọn cả `Default` và `Publish`. Nếu chỉ chọn `Publish`, các constraints của `Owner` thuộc `Default` không đương nhiên chạy. Có thể dùng group conversion `@ConvertGroup` khi cần đổi group ở cạnh cascade, nhưng chỉ thêm sau khi có yêu cầu rõ và test được.

### 12.2. Groups không thay thế authorization

Chỉ vì request body có `@Validated(Admin.class)` không có nghĩa caller có quyền quản trị. Validation kiểm tra **dữ liệu**, authorization kiểm tra **quyền**. Những quyết định như có thể publish hay không phải được bảo vệ ở security/service layer chứ không phụ thuộc mỗi nhóm validation.

## 13. WebFlux và blocking validation

**Spring WebFlux non-blocking I/O không biến mọi code trong handler thành non-blocking.**

Bean Validation thông thường chạy đồng bộ và phù hợp cho các ràng buộc nhanh như `@NotBlank`, `@Size`, `@Min`, pattern hoặc kiểm tra field trong memory. Nhưng một `ConstraintValidator` custom gọi database hoặc dịch vụ HTTP theo kiểu blocking có thể gây chậm event-loop nếu provider thực thi ngay trên luồng xử lý reactive.

- Giữ các `ConstraintValidator` gắn DTO ở mức **nhanh, không blocking, không side effect**.
- Quy tắc cần I/O bất đồng bộ (trùng email trong DB, kiểm tra quyền qua API, hạn mức còn lại) nên được thực thi ở service reactive bằng `Mono`/`Flux` và các repository/client reactive.
- Không gọi `.block()` trong `ConstraintValidator` hay handler reactive để “lấy kết quả kiểm tra”.
- Không nhầm validation thành công với transaction/business invariant: dữ liệu có thể hợp lệ về dạng nhưng không phù hợp trạng thái thực tế.

Ví dụ minh họa một bước nghiệp vụ async sau request-object validation:

```java
@PostMapping("/create")
public Mono<ResponseEntity<?>> create(
        @Valid @RequestBody Mono<TicketRequest> bodyMono) {

    return bodyMono
            .flatMap(service::checkAndSave)
            .map(saved -> ResponseEntity.ok().build());
}
```

Đây là fragment **không độc lập**, giả sử có reactive `service.checkAndSave(TicketRequest)` trả một `Mono<?>`. Thứ tự đúng là parse → Bean Validation của DTO → kiểm tra nghiệp vụ/authorization → persist. Thêm onErrorResume riêng cho lỗi nghiệp vụ nếu cần, không nuốt toàn bộ error signal thành kết quả thành công.

## 14. Cấu hình provider và custom validators

### 14.1. Phụ thuộc bắt buộc

Trong Spring Boot 3.x, chỉ thêm `spring-boot-starter-webflux` chưa nhất thiết bảo đảm có Bean Validation provider. Vì vậy ví dụ có:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Nó mang theo Hibernate Validator phù hợp. Trong một dự án nâng cấp từ Spring Boot 2.x, chú ý namespace đã chuyển từ `javax.validation.*` sang `jakarta.validation.*`; không nhập nhằng hai loại annotation khi dùng Boot 3+.

### 14.2. Cấu hình global và local

Spring WebFlux hỗ trợ cấu hình `Validator` toàn cục qua WebFlux config hoặc một validator cục bộ bằng `@InitBinder` trong controller/`@ControllerAdvice`. Ví dụ khái niệm:

```java
@InitBinder
public void initBinder(WebDataBinder binder) {
    binder.addValidators(new MyFastTicketValidator());
}
```

Đây là fragment minh họa. `MyFastTicketValidator` phải implement `org.springframework.validation.Validator`, `supports(Class<?>)` trả đúng các kiểu mà validator chấp nhận, và `validate(Object, Errors)` thêm lỗi phù hợp. Nếu áp validator sai kiểu có thể gây exception hoặc validation không như mong đợi.

Không thay provider Jakarta Validation toàn cục chỉ vì một field cần kiểm tra mới; cân nhắc custom `@Constraint`/`ConstraintValidator` nếu nó là quy tắc dữ liệu dùng lại ở nhiều DTO.

### 14.3. Khi nào dùng validation programmatic?

Ngoài annotation ở controller, có thể inject `jakarta.validation.Validator` để kiểm tra DTO tại một lớp không thuộc HTTP boundary:

```java
Set<ConstraintViolation<TicketRequest>> violations =
        validator.validate(request);

if (!violations.isEmpty()) {
    // Đổi thành domain/API error theo chính sách riêng.
}
```

Đây là fragment minh họa; giả sử `validator` và `request` đã được cung cấp. `Validator.validate(...)` trả tập lỗi, **không tự ném `WebExchangeBindException`**. Exception đó được Spring WebFlux request binding integration tạo ra; nó không phải API output của Jakarta Validation.

## 15. Những lỗi thường gặp và cách sửa

| Sai lầm | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Chỉ gắn `@NotBlank` trong DTO và quên `@Valid`/`@Validated` ở argument | Validation của request object có thể không được kích hoạt | Đánh dấu DTO argument đúng chỗ |
| Import `javax.validation.Valid` trong Boot 3+ | Sai namespace API generation | Dùng `jakarta.validation.Valid` |
| Dùng `@Validated(Publish.class)` rồi tưởng `Default` vẫn luôn chạy | Groups không tự bao hàm nhau | Chỉ định `Default.class` lẫn `Publish.class` nếu cần |
| Đặt `@Valid` ở DTO cha nhưng quên `@Valid` trên nested property | Provider không được yêu cầu cascade đến child | Đặt `@Valid` ở cạnh cần cascade |
| Chỉ có `@Valid` trên nested child nhưng mong cấm null | Null được bỏ qua khi cascade | Thêm `@NotNull` |
| Mong `@Valid` tự tạo `HandlerMethodValidationException` | `@Valid` không phải direct `@Constraint` | Phân biệt individual argument và method validation |
| Thêm `@Min` trên `@RequestParam` rồi vẫn chỉ bắt `WebExchangeBindException` | Handler chuyển sang method validation | Xử lý thêm `HandlerMethodValidationException` |
| Gọi `.block()` để lấy body `Mono<T>` trong handler | Có thể chặn event-loop | Dùng `map`/`flatMap`/`onErrorResume` |
| Đặt `BindingResult` sau `Mono<Dto>` | Reactive body chưa được resolve đồng bộ | Bắt lỗi trong reactive pipeline |
| Đặt `@Validated` trên controller class chỉ để chọn groups của DTO | Có thể kích hoạt AOP proxy cho method validation | Đặt `@Validated(groups)` ở đúng request argument |
| Sử dụng `MockMvc` để test WebFlux nhưng app đang chạy reactive | Test sai stack | Dùng `WebTestClient` |
| Thêm cả `spring-boot-starter-web` và `webflux` mà tưởng chạy WebFlux | Boot thường chọn Servlet MVC nếu cả hai có mặt | Chọn WebFlux starter cho ứng dụng reactive thuần |
| Dùng `@NotBlank` trên số hoặc complex DTO | Không có validator cho kiểu target | Dùng `@Min`, `@NotNull` hoặc custom constraint |
| Coi malformed JSON là Bean Validation violation | Decode có thể lỗi trước khi tạo DTO | Phân biệt parsing exception và validation exception |
| Dùng custom `ConstraintValidator` để gọi DB blocking | Có thể làm chậm event-loop | Tách I/O kiểm tra nghiệp vụ sang reactive service |

## 16. Checklist debug request validation WebFlux

1. **Kiểm tra application type:** Có thật đang chạy Spring WebFlux/reactive, hay vô tình đã thêm Servlet MVC starter?
2. **Kiểm tra dependencies:** Có `spring-boot-starter-validation` và provider Jakarta Validation không?
3. **Kiểm tra import:** Các constraint và `@Valid` có đến từ `jakarta.validation` không?
4. **Kiểm tra vị trí annotation:** `@Valid`/`@Validated` có nằm trên request argument không, hay chỉ nằm trong DTO?
5. **Kiểm tra request body:** JSON có hợp lệ, `Content-Type: application/json` đúng và đủ fields để decode không?
6. **Kiểm tra nested constraints:** Có `@Valid` trên property cha và `@NotNull` ở tầng cần cấm null?
7. **Kiểm tra groups:** Bạn đang chạy `Default`, custom group hay cả hai? `@Validated(Group.class)` có bỏ sót `Default`?
8. **Kiểm tra parameter type:** DTO là object trực tiếp hay `Mono<Dto>`? Nếu reactive, lỗi phát ra trong publisher có được subscriber/handler xử lý không?
9. **Kiểm tra direct method constraints:** Có `@Min`, `@NotBlank` hoặc constraint trên return? Nếu có, phải xét `HandlerMethodValidationException`.
10. **Kiểm tra class-level `@Validated`:** Có vô tình dùng AOP method validation ở controller khiến exception khác kỳ vọng?
11. **Kiểm tra BindingResult:** Đối số có phải non-reactive DTO và `BindingResult` có đặt ngay sau?
12. **Kiểm tra exception advice:** Có handler quá rộng che giấu loại exception thật hoặc báo 400 cho lỗi return server không?
13. **Kiểm tra runtime non-blocking:** Custom validators có gọi DB hoặc `.block()` không?
14. **Kiểm tra test:** `WebTestClient` có thực sự đi qua WebFlux controller? Assert status và lỗi được phân loại chứ không chỉ một generic 400?

## 17. Bài tập củng cố

1. Bỏ `@Valid` khỏi `TicketController.sync`, gửi `title=""`. So sánh với trước khi bỏ annotation và giải thích đường validation.
2. Gửi `owner=null`, sau đó `owner={"email":""}`. Giải thích constraint nào phát hiện từng trường hợp.
3. Chỉ dùng `@Validated(TicketRequest.Publish.class)` ở `publish`. Gửi body có `title=""` nhưng `reference="T-1"`; giải thích vì sao constraint `Default` có thể không chạy.
4. Đổi `/reactive` từ `Mono<TicketRequest>` sang `TicketRequest` và giữ `onErrorResume` tương tự. Vì sao bạn không thể xử lý argument resolver error bằng operator trên một publisher đã không còn là argument?
5. Thêm `@NotBlank` trực tiếp trên một `@RequestParam("code") String code` ở `sync` (chữ ký đã điều chỉnh). Gửi JSON DTO sai; exception validation sẽ thuộc nhánh nào?
6. Viết `@RestControllerAdvice` trả `ProblemDetail` và danh sách `FieldError` cho `WebExchangeBindException`, đồng thời phân loại `HandlerMethodValidationException`.
7. Thêm `@ModelAttribute` form với hai trường `title` và `copies`; đặt `@Min(1)` trên field form. Dùng `WebTestClient` thử form hợp lệ và không hợp lệ.
8. Thử đọc JSON có `copies="not-a-number"` để xác định exception parsing/binding thay vì mặc định quy về `@Min`.
9. Chuyển một constraint validator đang gọi repository blocking sang validation ở reactive service và so sánh thời điểm thực thi.
10. Thêm `@RequestPart("metadata")` nhận `Metadata`, cùng `FilePart`. Gửi metadata JSON hợp lệ và không hợp lệ; lưu ý không dùng `MultipartFile` kiểu Servlet.
11. Bổ sung custom group `Draft` và `Publish`, thử `@GroupSequence` hoặc `@ConvertGroup` khi có yêu cầu điều phối kiểm tra theo tầng.
12. Viết test phân biệt hai exception validation của WebFlux: DTO argument sai và direct parameter constraint sai. Tại sao cả hai có thể là HTTP 400 nhưng error contract nên nhận diện từng loại?

**Ghi nhớ:**

- `@Valid` trên request DTO: kích hoạt cascade/Bean Validation của nhóm `Default`.
- `@Validated(groups)` trên request DTO: kích hoạt validation với groups/hints do bạn chọn.
- `@RequestBody Mono<Dto>`: validation có thể phát lỗi trong publisher, nên xử lý bằng reactive operators.
- `@ModelAttribute Dto + BindingResult`: xử lý binding/validation error cục bộ trên argument đã được resolve.
- Direct `@Constraint` trên method parameter/return: có thể kích hoạt **WebFlux method validation** và đổi exception sang `HandlerMethodValidationException`.
- Class-level `@Validated` trên controller: khác với parameter-level groups và có thể chọn **AOP proxy**; không phải điều kiện để WebFlux built-in method validation hoạt động.

## 18. Tài liệu chính thức

- [Spring Framework 6.2 — WebFlux `@RequestBody` và validation](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/requestbody.html)
- [Spring Framework 6.2 — WebFlux validation của handler methods](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-validation.html)
- [Spring Framework 6.2 — WebFlux `@ModelAttribute`](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — WebFlux `@RequestPart` multipart](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/controller/ann-methods/multipart-forms.html)
- [Spring Framework — Reactive WebFlux error responses](https://docs.spring.io/spring-framework/reference/6.2/web/webflux/ann-rest-exceptions.html)
- [Spring Framework — `WebExchangeBindException` JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/bind/support/WebExchangeBindException.html)
- [Spring Framework — `HandlerMethodValidationException` JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/web/method/annotation/HandlerMethodValidationException.html)
- [Spring Boot 3.5 — Testing Spring Boot WebFlux with `WebTestClient`](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [Spring Boot 3.5 — Validation](https://docs.spring.io/spring-boot/3.5/reference/io/validation.html)
- [Jakarta Validation — Specification 3.0](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)