# Validation, codec và xử lý lỗi của WebFlux

## 1. Bức tranh tổng thể

Spring WebFlux là web stack reactive của Spring Framework: request/response có thể được xử lý bất đồng bộ, tương tác với luồng dữ liệu qua Reactor `Mono<T>` và `Flux<T>`. Khi kiểm thử một WebFlux API, ba lớp quan trọng thường bị nhầm với nhau:

1. **Validation:** dữ liệu đã decode thành object Java nhưng không đáp ứng constraint nghiệp vụ/đầu vào như `@NotBlank`, `@Min`, `@Valid`.
2. **Codec (message reader/writer):** chuyển đổi byte/JSON/chuỗi/stream trong HTTP thành object Java rồi chuyển response trở lại. Có thể lỗi trước khi validation chạy, ví dụ JSON sai cú pháp, `Content-Type` không tương thích hoặc quá giới hạn buffer.
3. **Error handling:** chọn HTTP status và error body khi một bước routing, binding, validation, service hoặc publisher reactive phát ra lỗi.

Ví dụ:

```http
POST /api/notes HTTP/1.1
Content-Type: application/json
Accept: application/json
X-Tenant-Id: tenant-a

{"title":"Học WebFlux","priority":2}
```

Đường xử lý:

```text
HTTP request
  └─ Router / HandlerMapping: POST /api/notes?
      └─ HandlerAdapter / argument resolvers
          └─ HttpMessageReader + Jackson JSON decoder
              ├─ JSON sai cú pháp          -> 400
              ├─ Content-Type không hỗ trợ -> 415 (có thể ở bước mapping)
              ├─ Chuyển thành CreateNote
              │    └─ Bean Validation
              │        ├─ title trống      -> 400
              │        └─ dữ liệu hợp lệ
              └─ Controller
                   └─ NoteService.create(...) -> Mono<NoteView>
                        ├─ emit NoteView     -> HttpMessageWriter -> JSON, 201
                        └─ error signal     -> error handler -> HTTP status + body
```

WebFlux **không tự bảo đảm** rằng mọi lỗi đều tạo cùng một JSON schema. Muốn API có hợp đồng lỗi nhất quán, cần thiết kế `@RestControllerAdvice`, error mapping hoặc `WebExceptionHandler` phù hợp. Bài học đi từ khái niệm tới ví dụ chạy được, test dương/âm và các giới hạn thực tế.

**Nền tảng minh họa:** Java 17+, Gradle, Spring Boot **3.3.5** (Spring Framework 6.1). Không coi những phiên bản này là mới nhất; chúng giúp cố định import/API khi học. Với Boot 3.3.x, dùng `@MockBean` cho WebFlux slice test; khi nâng sang Spring Framework 6.2+ / Boot 3.4+, cân nhắc `@MockitoBean` theo BOM thực tế.

## 2. WebFlux dùng codec, không phải HTTP message converter kiểu MVC

| Khía cạnh | Spring MVC | Spring WebFlux |
| --- | --- | --- |
| Nền tảng web chính | Servlet | Reactive Streams / Reactor |
| Đọc request body | `HttpMessageConverter` | `HttpMessageReader` và `Decoder` |
| Viết response | `HttpMessageConverter` | `HttpMessageWriter` và `Encoder` |
| Controller trả về | Object, `ResponseEntity`, async types... | Object, `Mono<T>`, `Flux<T>`, `ResponseEntity<Mono<T>>`... |
| Test web layer thường dùng | `MockMvc` | `WebTestClient` |
| Lỗi validation đối tượng `@RequestBody` | Thường `MethodArgumentNotValidException` | Thường `WebExchangeBindException` |

Các codecs được quản lý qua `ServerCodecConfigurer` và cấu hình WebFlux/Boot. Jackson thường xử lý `application/json` khi có dependency tương ứng. WebFlux có thể decode body kiểu thông thường, đồng thời hỗ trợ reactive publisher cho request body và response body.

**Ba khái niệm phải tách riêng:**

- **Routing/mapping:** `@PostMapping(consumes = "application/json", produces = "application/json")` quyết định endpoint có nhận/đáp ứng media type không.
- **Decoding:** codec có đọc body và tạo object Java hợp lệ về **cú pháp/kiểu** không?
- **Bean Validation:** object sau decode có thỏa `@NotBlank`, `@Size`, `@Min`, custom constraint... không?

Nếu JSON có giá trị `priority` là chữ `"abc"` nhưng DTO yêu cầu `int`, Jackson/codec có thể thất bại **trước khi** ràng buộc `@Min(1)` được xét. Nếu JSON có `priority:0`, decode thành `int` thành công rồi **validation** từ chối.

## 3. Hai đường validation trong Spring WebFlux (Spring Framework 6.1+)

### 3.1. Validation một đối tượng đầu vào

```java
@PostMapping("/notes")
public Mono<NoteView> create(
        @Valid @RequestBody CreateNote request) {
    return service.create(request);
}
```

Đây là **snippet không độc lập**; ví dụ đầy đủ ở các mục sau dùng class và method rõ ràng. Với `@Valid` trên một command object như `CreateNote`, Bean Validation kiểm tra constraint của DTO. Nếu không hợp lệ, Spring WebFlux thường phát `WebExchangeBindException`, chứa `BindingResult` và thông tin field errors.

`@Valid` **không phải** bản thân một constraint trên tham số; nó yêu cầu validate các ràng buộc trong object. Cần có Bean Validation implementation, thường thông qua `spring-boot-starter-validation`.

### 3.2. Validation ở mức phương thức (method validation)

Nếu đặt constraint trực tiếp lên tham số controller như:

```java
@GetMapping("/search")
public Flux<NoteView> search(
        @RequestParam @Min(1) int page) {
    return service.search(page);
}
```

Spring Framework 6.1+ có built-in method validation cho tham số có `@Constraint` trực tiếp. Lỗi thường là `HandlerMethodValidationException`, không phải `WebExchangeBindException`. Method validation có thể bao gồm nested `@Valid` cho các tham số khác của cùng method. Vì vậy **một API lớn cần sẵn sàng xử lý cả hai exception**, tùy chữ ký controller.

**Chú ý:** thêm `@Validated` ở **cấp class** controller có thể kích hoạt AOP-based method validation, khác với cơ chế built-in của Spring 6.1. Khi dùng cơ chế tích hợp mới, tài liệu Spring khuyến nghị không dùng class-level `@Validated` chỉ để kích hoạt method validation. Không kết luận rằng mọi `@Valid` luôn phát đúng một loại exception.

### 3.3. Reactive request body: @RequestBody Mono<T>

WebFlux có thể nhận:

```java
@PostMapping("/notes/async")
public Mono<NoteView> createAsync(
        @Valid @RequestBody Mono<CreateNote> input) {
    return input.flatMap(service::create);
}
```

Đây là **ví dụ cú pháp**; `service::create` giả định service có chữ ký nhận `CreateNote`. Lợi ích là đọc và validate có thể tiếp tục thông qua publisher; lỗi validation/decode đi vào reactive error signal. Controller có thể xử lý bằng `onErrorResume` khi thực sự cần. Với tham số body kiểu reactive, `Errors`/`BindingResult` đặt ngay sau tham số không phải cùng cách dùng như object thông thường.

Bài thực hành bên dưới chọn `@Valid @RequestBody CreateNote` **không bọc Mono** để test validation dễ hiểu, còn service vẫn trả về `Mono<NoteView>`. Cách này hợp lệ trong WebFlux: lựa chọn kiểu tham số phụ thuộc yêu cầu asynchronous/streaming, không phải mọi method WebFlux bắt buộc nhận `Mono<DTO>`.

## 4. Những HTTP status thường gặp

| Tình huống | Status phổ biến | Nguồn lỗi |
| --- | --- | --- |
| JSON hợp lệ, validation PASS | 200/201 theo hợp đồng | Controller và response |
| `@Valid` DTO vi phạm constraint | 400 Bad Request | `WebExchangeBindException` |
| Constraint trực tiếp `@Min` trên tham số | 400 Bad Request cho input lỗi | `HandlerMethodValidationException` |
| JSON sai cú pháp, sai type field | 400 Bad Request | Codec / `ServerWebInputException` (thường có nguyên nhân decode) |
| Thiếu body bắt buộc | 400 Bad Request | Argument resolving / input error |
| `Content-Type` không hỗ trợ | 415 Unsupported Media Type | Mapping/codec |
| `Accept` không tương thích `produces` | 406 Not Acceptable | Content negotiation |
| Domain item không tồn tại | 404 Not Found **nếu được map rõ** | Error handler / `ResponseStatusException` |
| Domain conflict | 409 Conflict **nếu có mapping** | Domain/service và error handler |
| Lỗi không được xử lý | Thường 500 | Global WebFlux/Boot error handling |

**Không đồng nhất mọi `DataBufferLimitException` với HTTP 413.** Giới hạn buffering có thể làm decoder ném `DataBufferLimitException`, nhưng status cuối cùng phụ thuộc cách exception được bọc và các error handler. Muốn trả 413 có chủ đích, thiết kế mapping rõ và test trong ngữ cảnh HTTP thực.

`401`/`403` thuộc cơ chế security riêng nếu ứng dụng tích hợp Spring Security. Một yêu cầu không qua authentication/authorization có thể bị chặn trước khi chạm validation hoặc controller.

## 5. Dự án thực hành Java 17+, Spring Boot 3.3.5

Ta sẽ dựng một ứng dụng ghi chú rất nhỏ, không truy cập DB hay network ngoài. Lớp WebFlux controller thực hiện JSON binding, validation và mapping exception. Lớp service mẫu trả `Mono` ngay lập tức; mục đích là kiểm thử HTTP contract, **không** mô phỏng persistence production.

Cấu trúc:

```text
webflux-errors-demo/
├── settings.gradle
├── build.gradle
├── src/main/java/com/example/webflux/
│   ├── WebFluxErrorsApplication.java
│   ├── CreateNote.java
│   ├── NoteView.java
│   ├── ApiError.java
│   ├── NoteService.java
│   ├── SimpleNoteService.java
│   ├── NoteNotFoundException.java
│   ├── NoteController.java
│   └── ApiErrorAdvice.java
└── src/test/java/com/example/webflux/
    ├── NoteControllerWebTest.java
    ├── NoteServiceReactiveTest.java
    └── NoteHttpIntegrationTest.java
```

### 5.1. Gradle build

`settings.gradle`:

```groovy
rootProject.name = 'webflux-errors-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
```

Chỉ dùng `spring-boot-starter-webflux`, **không** thêm `spring-boot-starter-web`. Nếu cả hai starter web MVC và WebFlux cùng có mặt, Boot thường ưu tiên MVC trừ khi chọn `spring.main.web-application-type=reactive` có chủ đích. Điều này quan trọng vì annotation/controller có thể giống nhau nhưng test context thực tế lại là MVC.

`spring-boot-starter-validation` cung cấp validation implementation; `reactor-test` cung cấp `StepVerifier` để kiểm tra tín hiệu của `Mono`/`Flux`. Các phiên bản chi tiết do BOM Boot quản lý.

### 5.2. Application root

`src/main/java/com/example/webflux/WebFluxErrorsApplication.java`:

```java
package com.example.webflux;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class WebFluxErrorsApplication {
    public static void main(String[] args) {
        SpringApplication.run(WebFluxErrorsApplication.class, args);
    }
}
```

### 5.3. DTO với Bean Validation

`src/main/java/com/example/webflux/CreateNote.java`:

```java
package com.example.webflux;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateNote(
        @NotBlank @Size(max = 80) String title,
        @Min(1) int priority
) {
}
```

`src/main/java/com/example/webflux/NoteView.java`:

```java
package com.example.webflux;

public record NoteView(
        long id,
        String title,
        int priority,
        String language,
        String tenantId
) {
}
```

`src/main/java/com/example/webflux/ApiError.java`:

```java
package com.example.webflux;

public record ApiError(String code, String message) {
}
```

Điều gì được validate?

- `title = ""`, `null` hoặc chỉ khoảng trắng vi phạm `@NotBlank`.
- `title` dài hơn 80 ký tự vi phạm `@Size(max=80)`.
- `priority = 0` hoặc âm vi phạm `@Min(1)`.
- `priority = "high"` trong JSON chưa chuyển được thành Java `int`, nên có thể fail **trong codec** trước validation.

Java record dùng được với Jackson do Boot 3.3.x quản lý. Ví dụ không dùng Lombok hoặc annotation processor.

### 5.4. Reactive service và domain exception

`src/main/java/com/example/webflux/NoteService.java`:

```java
package com.example.webflux;

import reactor.core.publisher.Mono;

public interface NoteService {
    Mono<NoteView> create(String tenantId, CreateNote input);
    Mono<NoteView> find(long id, String language, String tenantId);
}
```

`src/main/java/com/example/webflux/NoteNotFoundException.java`:

```java
package com.example.webflux;

public class NoteNotFoundException extends RuntimeException {
    public NoteNotFoundException(long id) {
        super("Note " + id + " not found");
    }
}
```

`src/main/java/com/example/webflux/SimpleNoteService.java`:

```java
package com.example.webflux;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class SimpleNoteService implements NoteService {

    @Override
    public Mono<NoteView> create(String tenantId, CreateNote input) {
        return Mono.just(new NoteView(
                100L,
                input.title(),
                input.priority(),
                "vi",
                tenantId
        ));
    }

    @Override
    public Mono<NoteView> find(
            long id, String language, String tenantId) {
        if (id != 100L) {
            return Mono.error(new NoteNotFoundException(id));
        }
        return Mono.just(new NoteView(
                100L, "Ghi chú demo", 2, language, tenantId
        ));
    }
}
```

`Mono.just(...)` trả một tín hiệu giá trị rồi hoàn tất; `Mono.error(...)` phát error signal khi subscriber đăng ký. Đây không phải database thật: `create` luôn trả id 100, `find(100)` trả một fixture cố định. Không dùng cách này để suy ra việc lưu ghi chú production hay đảm bảo idempotency.

### 5.5. Controller WebFlux: JSON in, Mono out

`src/main/java/com/example/webflux/NoteController.java`:

```java
package com.example.webflux;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestHeader;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/notes")
public class NoteController {

    private final NoteService service;

    public NoteController(NoteService service) {
        this.service = service;
    }

    @PostMapping(
            consumes = MediaType.APPLICATION_JSON_VALUE,
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<ResponseEntity<NoteView>> create(
            @RequestHeader("X-Tenant-Id") String tenantId,
            @Valid @RequestBody CreateNote input) {
        return service.create(tenantId, input)
                .map(note -> ResponseEntity
                        .status(HttpStatus.CREATED)
                        .body(note));
    }

    @GetMapping(
            value = "/{id}",
            produces = MediaType.APPLICATION_JSON_VALUE
    )
    public Mono<NoteView> get(
            @PathVariable("id") long id,
            @RequestParam(name = "lang", defaultValue = "vi")
                    String language,
            @RequestHeader("X-Tenant-Id") String tenantId) {
        return service.find(id, language, tenantId);
    }
}
```

Đường POST có các thành phần rõ ràng:

- `consumes=application/json` chỉ định request body media type được hỗ trợ.
- `@Valid @RequestBody CreateNote` để codec đọc JSON và validator kiểm tra object.
- `@RequestHeader` bắt buộc; thiếu header có thể bị từ chối trước method body.
- Service trả `Mono<NoteView>`; controller map thành `ResponseEntity` với status 201.
- `produces=application/json` dùng content negotiation cho response.

Đường GET minh họa path conversion (`id` sang `long`), query default (`lang=vi`) và một error signal từ service (`NoteNotFoundException`) được handler toàn cục xử lý.

**Về tenant:** header `X-Tenant-Id` ở đây là fixture học binding, **không phải bằng chứng xác thực/ủy quyền**. Trong ứng dụng thật phải đối chiếu tenant từ security context hoặc trusted infrastructure.

## 6. Thiết kế error body thống nhất với @RestControllerAdvice

Ta đặt một error contract nhỏ:

```json
{"code":"VALIDATION_ERROR","message":"Request body violates constraints"}
```

Ý nghĩa:

- `code` là mã lỗi ổn định để client phân nhánh.
- `message` là mô tả an toàn để trả cho client; không lộ stack trace, SQL, password hoặc dữ liệu cá nhân.
- HTTP status vẫn quan trọng: code giống nhau với status khác nhau không phải cùng hợp đồng.

`src/main/java/com/example/webflux/ApiErrorAdvice.java`:

```java
package com.example.webflux;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;
import org.springframework.web.server.ServerWebInputException;

@RestControllerAdvice
public class ApiErrorAdvice {

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ApiError> onValidation(
            WebExchangeBindException exception) {
        return ResponseEntity.badRequest().body(
                new ApiError(
                        "VALIDATION_ERROR",
                        "Request body violates constraints"
                )
        );
    }

    @ExceptionHandler(ServerWebInputException.class)
    public ResponseEntity<ApiError> onBadInput(
            ServerWebInputException exception) {
        return ResponseEntity.badRequest().body(
                new ApiError(
                        "INPUT_ERROR",
                        "Request could not be read"
                )
        );
    }

    @ExceptionHandler(NoteNotFoundException.class)
    public ResponseEntity<ApiError> onNotFound(
            NoteNotFoundException exception) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(
                new ApiError("NOT_FOUND", exception.getMessage())
        );
    }
}
```

Với WebFlux, một `@ExceptionHandler` có thể trả một object đồng bộ như `ResponseEntity<ApiError>`; framework sẽ serialize nó như response HTTP. Cũng có thể trả `Mono<ResponseEntity<...>>` nếu error handling cần thao tác reactive.

**Vì sao có hai handler cho lỗi đầu vào?**

- `WebExchangeBindException` chứa `BindingResult` của validation một object; ưu tiên mã `VALIDATION_ERROR`.
- `ServerWebInputException` bao quát nhiều lỗi đọc/chuyển đổi request khác, ví dụ path id sai kiểu, JSON malformed hoặc thiếu input bắt buộc. Không đánh đồng nó với lỗi Bean Validation.
- Có thể các exception có quan hệ kế thừa; Spring chọn method xử lý phù hợp nhất theo loại exception, nên handler chuyên biệt cho `WebExchangeBindException` không bị một handler tổng quát che mất.

**Phạm vi:** advice này không tự chuẩn hóa status 406/415 hoặc mọi lỗi server. Chúng vẫn do WebFlux/Boot error infrastructure xử lý theo mặc định trừ khi có mapping khác. Muốn mọi lỗi chung schema phải mở rộng thiết kế và kiểm thử riêng, không khẳng định ba handler trên đã giải quyết toàn bộ.

## 7. Kiểm thử WebFlux slice bằng @WebFluxTest và WebTestClient

`@WebFluxTest(NoteController.class)` chỉ dựng MVC-independent **WebFlux** infrastructure và các bean phù hợp với web slice (controller, advice, JSON components, converter/configurer). Bean `@Service` thông thường như `SimpleNoteService` không tự được scan vào slice; vì vậy test đăng ký `@MockBean NoteService` làm dependency để inject vào controller.

`WebTestClient` gửi request vào test context mà **không cần mở cổng HTTP**. Nó cho phép assert status, header, JSON body. Dùng Mockito `verify` thêm khi việc truyền đúng đối số đến service là một phần contract.

### 7.1. Test class đầy đủ (10 test)

`src/test/java/com/example/webflux/NoteControllerWebTest.java`:

```java
package com.example.webflux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.WebFluxTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@WebFluxTest(NoteController.class)
class NoteControllerWebTest {

    @Autowired
    WebTestClient client;

    @MockBean
    NoteService service;

    @Test
    void postValidJsonReturns201AndDecodedBody() {
        CreateNote input = new CreateNote("WebFlux", 2);
        NoteView created = new NoteView(
                25L, "WebFlux", 2, "vi", "tenant-a");

        when(service.create("tenant-a", input))
                .thenReturn(Mono.just(created));

        client.post()
                .uri("/api/notes")
                .header("X-Tenant-Id", "tenant-a")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(input)
                .exchange()
                .expectStatus().isCreated()
                .expectHeader().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.id").isEqualTo(25)
                .jsonPath("$.title").isEqualTo("WebFlux")
                .jsonPath("$.priority").isEqualTo(2);

        verify(service).create("tenant-a", input);
    }

    @Test
    void blankTitleFailsBeanValidation() {
        client.post().uri("/api/notes")
                .header("X-Tenant-Id", "tenant-a")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateNote("  ", 2))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("VALIDATION_ERROR");

        verifyNoInteractions(service);
    }

    @Test
    void nonPositivePriorityFailsBeanValidation() {
        client.post().uri("/api/notes")
                .header("X-Tenant-Id", "tenant-a")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateNote("Ok", 0))
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("VALIDATION_ERROR");

        verifyNoInteractions(service);
    }

    @Test
    void malformedJsonFailsDuringDecoding() {
        client.post().uri("/api/notes")
                .header("X-Tenant-Id", "tenant-a")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"title\":")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INPUT_ERROR");

        verifyNoInteractions(service);
    }

    @Test
    void unsupportedContentTypeReturns415() {
        client.post().uri("/api/notes")
                .header("X-Tenant-Id", "tenant-a")
                .contentType(MediaType.TEXT_PLAIN)
                .bodyValue("title=WebFlux")
                .exchange()
                .expectStatus().isUnsupportedMediaType();

        verifyNoInteractions(service);
    }

    @Test
    void getBindsPathQueryAndHeader() {
        NoteView note = new NoteView(
                100L, "Item", 2, "en", "tenant-a");

        when(service.find(100L, "en", "tenant-a"))
                .thenReturn(Mono.just(note));

        client.get()
                .uri("/api/notes/{id}?lang={lang}", 100L, "en")
                .header("X-Tenant-Id", "tenant-a")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.id").isEqualTo(100)
                .jsonPath("$.language").isEqualTo("en");

        verify(service).find(100L, "en", "tenant-a");
    }

    @Test
    void invalidPathIdReturns400() {
        client.get()
                .uri("/api/notes/not-a-number")
                .header("X-Tenant-Id", "tenant-a")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INPUT_ERROR");

        verifyNoInteractions(service);
    }

    @Test
    void missingTenantHeaderReturns400() {
        client.get()
                .uri("/api/notes/100")
                .exchange()
                .expectStatus().isBadRequest()
                .expectBody()
                .jsonPath("$.code").isEqualTo("INPUT_ERROR");

        verifyNoInteractions(service);
    }

    @Test
    void domainErrorSignalMapsTo404() {
        when(service.find(999L, "vi", "tenant-a"))
                .thenReturn(Mono.error(
                        new NoteNotFoundException(999L)));

        client.get()
                .uri("/api/notes/999")
                .header("X-Tenant-Id", "tenant-a")
                .accept(MediaType.APPLICATION_JSON)
                .exchange()
                .expectStatus().isNotFound()
                .expectBody()
                .jsonPath("$.code").isEqualTo("NOT_FOUND");

        verify(service).find(999L, "vi", "tenant-a");
    }

    @Test
    void unacceptableResponseMediaTypeReturns406() {
        client.get()
                .uri("/api/notes/100")
                .header("X-Tenant-Id", "tenant-a")
                .accept(MediaType.APPLICATION_XML)
                .exchange()
                .expectStatus().isNotAcceptable();

        verifyNoInteractions(service);
    }
}
```

**Kỳ vọng theo mã ví dụ: 10 phương thức test**. Các phương thức chưa được thực thi trong môi trường của bài viết, vì vậy đây là mục tiêu tái hiện chứ không phải báo cáo CI đã chạy. Khi triển khai vào project riêng, cần chạy Gradle và kiểm tra báo cáo thật.

### 7.2. Vì sao test nên xác nhận cả status, JSON và service?

Test POST hợp lệ kiểm tra ba thứ:

- Codec đọc JSON thành `CreateNote` đúng nội dung.
- Controller gọi `service.create("tenant-a", input)` đúng một lần theo default `verify`.
- Response phản ánh `201 Created` và những trường dữ liệu từ `NoteView` được serialize thành JSON.

Test POST title rỗng và priority 0 kiểm tra cả `400` và `VALIDATION_ERROR`; `verifyNoInteractions(service)` chứng minh validation chặn request trước khi chạm service. Một test chỉ kiểm tra 400 không phân biệt được việc Spring tự validate hay controller/service gọi rồi mới ném exception.

Test 415/406 chỉ assert status mặc định và không giả định body JSON theo `ApiError`, vì advice mẫu không định nghĩa schema cho những lỗi đó.

### 7.3. Lưu ý riêng cho JSON malformed trong WebTestClient

Với test chuỗi JSON cố tình hỏng, `bodyValue("{\"title\":")` được dùng để gửi dữ liệu request theo `Content-Type: application/json`. Trong các stack/codec tùy biến, writer của test client có thể xử lý `String` khác cách người học kỳ vọng. Nếu test kiểm tra **chính xác byte body** trở thành flaky do codec phía client, có thể dùng `BodyInserters`/`DataBuffer` hoặc client HTTP raw để gửi byte JSON tùy ý. Không thay đổi mục tiêu: server phải nhận một payload không thể parse thành DTO và trả lỗi phù hợp.

## 8. Kiểm thử publisher bằng StepVerifier

`WebTestClient` rất tốt cho HTTP contract; `StepVerifier` giúp kiểm tra trực tiếp các **Reactor signals** của service và error propagation mà không cần Spring context.

`src/test/java/com/example/webflux/NoteServiceReactiveTest.java`:

```java
package com.example.webflux;

import org.junit.jupiter.api.Test;
import reactor.test.StepVerifier;

class NoteServiceReactiveTest {

    private final NoteService service = new SimpleNoteService();

    @Test
    void createEmitsOneNoteThenCompletes() {
        CreateNote request = new CreateNote("Reactor", 3);

        StepVerifier.create(service.create("tenant-a", request))
                .expectNext(new NoteView(
                        100L, "Reactor", 3, "vi", "tenant-a"))
                .verifyComplete();
    }

    @Test
    void missingNoteProducesErrorSignal() {
        StepVerifier.create(
                    service.find(999L, "vi", "tenant-a"))
                .expectErrorMatches(error ->
                        error instanceof NoteNotFoundException
                        && error.getMessage()
                                .equals("Note 999 not found"))
                .verify();
    }
}
```

**Kỳ vọng: 2 test**. Với publisher, khác biệt quan trọng là `Mono.error(...)` **không đồng nghĩa ném exception ngay khi gọi method**. Nó phát error signal khi được subscribe. Ví dụ sau thường sai về mục đích:

```java
assertThrows(
        NoteNotFoundException.class,
        () -> service.find(999L, "vi", "tenant-a")
);
```

`find(...)` chỉ trả về một `Mono`; exception chưa được phát trực tiếp tại thời điểm đó. Dùng `StepVerifier.expectErrorMatches` hoặc gọi reactive stream theo API phù hợp để kiểm tra error signal. Không viết `block()` trên event-loop trong logic WebFlux chỉ để “chờ exception”; trong unit test `block()` đôi khi dùng được nhưng `StepVerifier` rõ ý định hơn.

## 9. HTTP integration test qua cổng ngẫu nhiên

Test MVC slice không mở socket. Khi cần xác minh server WebFlux thực sự nhận HTTP, có thể dùng `@SpringBootTest(webEnvironment = RANDOM_PORT)` và `WebTestClient` được cấu hình cho server.

`src/test/java/com/example/webflux/NoteHttpIntegrationTest.java`:

```java
package com.example.webflux;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class NoteHttpIntegrationTest {

    @Autowired
    WebTestClient client;

    @Test
    void sendsJsonOverRealHttpAndReceivesCreatedResponse() {
        client.post()
                .uri("/api/notes")
                .header("X-Tenant-Id", "tenant-http")
                .contentType(MediaType.APPLICATION_JSON)
                .accept(MediaType.APPLICATION_JSON)
                .bodyValue(new CreateNote("HTTP demo", 2))
                .exchange()
                .expectStatus().isCreated()
                .expectBody()
                .jsonPath("$.id").isEqualTo(100)
                .jsonPath("$.title").isEqualTo("HTTP demo")
                .jsonPath("$.tenantId").isEqualTo("tenant-http");
    }
}
```

**Kỳ vọng: 1 test** khi có quyền mở loopback port. `WebTestClient` lúc này gọi embedded server thật trên port động, nên kiểm tra được phần ingress/codec ở mức HTTP. Không có database hoặc service bên ngoài trong ứng dụng mẫu, do đó test không đụng tài nguyên production.

Tổng các file chạy được:

| Class | Số method | Kiểu test |
| --- | ---: | --- |
| `NoteControllerWebTest` | 10 | WebFlux slice, Mock HTTP, validation/codec/error |
| `NoteServiceReactiveTest` | 2 | Unit test Reactor `Mono` bằng StepVerifier |
| `NoteHttpIntegrationTest` | 1 | HTTP integration RANDOM_PORT |

**Tổng cộng 13 test method theo source**. Lệnh chạy với Gradle Wrapper:

```bash
./gradlew test --tests 'com.example.webflux.NoteControllerWebTest'
./gradlew test --tests 'com.example.webflux.NoteServiceReactiveTest'
./gradlew test --tests 'com.example.webflux.NoteHttpIntegrationTest'
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Nếu chưa có Wrapper và máy đã cài Gradle tương thích, dùng `gradle test`. Khi chạy, kiểm tra `build/reports/tests/test/index.html`. Số test, status và exception thực tế phải được lấy từ báo cáo chạy, không chỉ từ số phương thức dự kiến.

## 10. HandlerMethodValidationException và cách mở rộng advice

Khi một controller vừa có `@Valid` cho body vừa dùng constraint trực tiếp trên một tham số khác như `@Min`, Spring Framework 6.1 có thể dùng **method validation** cho chữ ký đó. Vì vậy một lớp advice của API production nên định nghĩa cách xử lý `HandlerMethodValidationException`.

Snippet minh họa cho một method trong `@RestControllerAdvice`, **không phải phần của 13 test mẫu**:

```java
@ExceptionHandler(HandlerMethodValidationException.class)
public ResponseEntity<ApiError> onMethodValidation(
        HandlerMethodValidationException exception) {
    return ResponseEntity
            .status(exception.getStatusCode())
            .body(new ApiError(
                    "METHOD_VALIDATION_ERROR",
                    "Request parameters violate constraints"
            ));
}
```

Cần import `org.springframework.web.method.annotation.HandlerMethodValidationException`, `ExceptionHandler`, `ResponseEntity` và domain `ApiError`. `exception.getStatusCode()` có ý nghĩa vì lỗi tham số input thường là 400, trong khi một lỗi validation **giá trị trả về** có thể cần xử lý như lỗi server chứ không trả cùng status input.

Đừng viết handler catch mọi `Exception` rồi trả `400`: lỗi kết nối DB, lỗi lập trình hoặc timeout không phải input validation. Handler tổng quát quá rộng có thể ẩn lỗi server và gây khó debug. Khi thiết kế error schema lớn, xem xét `ResponseEntityExceptionHandler` dành cho WebFlux, `ProblemDetail` và các cơ chế Boot Problem Details phù hợp với phiên bản.

## 11. Codecs: cách WebFlux đọc và ghi dữ liệu

### 11.1. Reader và writer được chọn theo media type

Một WebFlux request `Content-Type: application/json` thường được đọc bằng Jackson-based JSON decoder khi `CreateNote` là target type phù hợp. Response `NoteView` được encode thành JSON nhờ writer/encoder tương ứng. `Content-Type` mô tả body **đang gửi**, `Accept` mô tả representation client **muốn nhận**.

- **415 Unsupported Media Type:** endpoint không nhận body media type mà client gửi, ví dụ POST body `text/plain` khi `consumes=application/json`.
- **406 Not Acceptable:** endpoint không thể trả representation phù hợp `Accept`, ví dụ client chỉ chấp nhận XML còn route `produces=application/json`.
- **400 Bad Request:** body đã có media type phù hợp nhưng decode/binding/validation thất bại (ví dụ JSON hỏng).

Không nhất thiết mọi lỗi decoder được bọc thành cùng exception ở mọi phiên bản; tách test theo **HTTP contract** là cách ổn định hơn assert message nội bộ của Jackson.

### 11.2. JSON array, Flux và streaming

WebFlux có thể xử lý các publisher `Mono<T>`, `Flux<T>`. Ví dụ một response stream:

```java
@GetMapping(
        value = "/events",
        produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<NoteView> events() {
    return Flux.just(
            new NoteView(1L, "First", 1, "vi", "tenant-a"),
            new NoteView(2L, "Second", 2, "vi", "tenant-a")
    );
}
```

Đây là **đoạn minh họa**, cần đặt trong controller và import `GetMapping`, `MediaType`, `Flux`, `NoteView`. Với SSE, client có thể nhận các event dần dần, thay vì đợi toàn bộ stream. Khi test streaming, `WebTestClient.returnResult(...)` và `StepVerifier` hữu ích để kiểm tra thứ tự/tín hiệu và hủy subscription.

Một JSON array thông thường trả từ `Flux<NoteView>` có thể được serialize theo chiến lược không giống SSE. **Streaming support phụ thuộc codec và media type**, không chỉ vì return type là `Flux`.

### 11.3. Buffer limit và DataBufferLimitException

Một số decoder cần gom dữ liệu vào bộ nhớ. Để hạn chế tiêu thụ RAM, nhiều codec có default max-in-memory-size khoảng **256 KiB**, tùy codec và phiên bản. Khi request hoặc một item của stream vượt giới hạn, có thể gặp:

```text
org.springframework.core.io.buffer.DataBufferLimitException:
Exceeded limit on max bytes to buffer
```

Spring Boot 3.3.x hỗ trợ property:

```properties
spring.codec.max-in-memory-size=1MB
```

Đây là cấu hình cho các codec được Boot auto-configure ở WebFlux server và `WebClient` tương ứng; không nên kết luận nó tự áp dụng cho mọi client custom `ExchangeStrategies` đã dựng thủ công.

Ví dụ tùy chỉnh riêng WebClient:

```java
WebClient client = WebClient.builder()
        .codecs(configurer -> configurer.defaultCodecs()
                .maxInMemorySize(1024 * 1024))
        .build();
```

Cần import `org.springframework.web.reactive.function.client.WebClient`. Đây là snippet, không thuộc project runnable của mục 5–9.

**Không tăng limit vô hạn để sửa mọi lỗi.** Với file lớn hoặc streaming, cân nhắc `Flux<DataBuffer>`, multipart streaming, bảo vệ kích thước payload ở gateway/proxy, và giải phóng buffer đúng quy tắc khi tự quản lý `DataBuffer`. Giới hạn codec không thay thế HTTP server/nginx/WAF size limits.

### 11.4. Test codec boundary đúng cách

Để kiểm tra giới hạn bộ nhớ, cấu hình **một test context riêng** với `spring.codec.max-in-memory-size=...` thấp, gửi payload có số byte được tính thực tế, và kiểm tra HTTP status/error mapping mà ứng dụng **đã chủ động định nghĩa**. Tránh assert mặc định 413 chỉ vì có `DataBufferLimitException`: việc convert sang HTTP status cần error-handling policy cụ thể.

Một test khác có thể kiểm tra `Content-Type: text/plain` và `Accept: application/xml`, như hai test slice ở mục 7. Đó là cách kiểm tra selection codec/route mà không phải đưa payload cực lớn vào bộ test hằng ngày.

## 12. Functional endpoints: validation không tự giống annotated controller

WebFlux có hai kiểu khai báo endpoint: annotation-based `@RestController` và functional routing với `RouterFunction<ServerResponse>` / `HandlerFunction`.

Ví dụ một handler functional:

```java
public Mono<ServerResponse> create(ServerRequest request) {
    return request.bodyToMono(CreateNote.class)
            .flatMap(input -> service.create("tenant-a", input))
            .flatMap(saved -> ServerResponse.status(201)
                    .contentType(MediaType.APPLICATION_JSON)
                    .bodyValue(saved));
}
```

Đây là **snippet minh họa**, chưa có class/import/route đầy đủ. `bodyToMono(CreateNote.class)` thực hiện **decode**, nhưng **không tự bảo đảm Bean Validation chạy giống `@Valid @RequestBody`** của annotated controller. Nếu dùng functional endpoint, phải gọi Validator hoặc một abstraction validation rõ ràng rồi chuyển các lỗi thành HTTP response theo contract.

Một mẫu kiểm tra thủ công:

```java
Set<ConstraintViolation<CreateNote>> violations =
        validator.validate(input);

if (!violations.isEmpty()) {
    return Mono.error(
            new ResponseStatusException(
                    HttpStatus.BAD_REQUEST, "invalid note"));
}
```

Cần `jakarta.validation.Validator`, `ConstraintViolation`, `Set`, `ResponseStatusException`, `HttpStatus`. Đây là đoạn xử lý trong một function, không phải project độc lập. Nếu endpoint dùng functional routing, `@WebFluxTest` không tự dò và đăng ký mọi `RouterFunction`; dùng `@Import` route cần test hoặc `@SpringBootTest` phù hợp.

## 13. Cách xử lý lỗi ở các tầng và ranh giới trách nhiệm

```text
A. Route chưa match / method không được hỗ trợ / media type sai
     -> HTTP 404 / 405 / 415 / 406 qua WebFlux infrastructure

B. Đọc body hoặc tham số thất bại
     -> WebFlux input exception (thường 400)

C. Bean Validation hoặc method validation thất bại
     -> WebExchangeBindException / HandlerMethodValidationException

D. Service Publisher phát domain error
     -> @ExceptionHandler hoặc onErrorMap/ResponseStatusException
     -> 404/409/422... theo contract

E. Server lỗi không được xử lý
     -> Global WebExceptionHandler / Boot error handling (thường 500)
```

### 13.1. @RestControllerAdvice

Phù hợp để chuẩn hóa lỗi từ **annotated controllers**, sử dụng `@ExceptionHandler`, có thể trả `ResponseEntity<ApiError>` hay `Mono<...>`. Nếu nhiều advice, xem thứ tự `@Order` và phạm vi áp dụng để tránh bắt nhầm exception.

### 13.2. ResponseStatusException

Có thể dùng trong service/handler khi muốn gắn status rõ:

```java
return Mono.error(new ResponseStatusException(
        HttpStatus.NOT_FOUND, "note missing"));
```

Đoạn này là snippet và cần import `ResponseStatusException`, `HttpStatus`, `Mono`. Tuy nhiên response body có thể phụ thuộc Spring/Boot error configuration; nếu API cần `{"code":"NOT_FOUND"}` nhất quán, dùng error mapping đã thiết kế và test body.

### 13.3. onErrorResume và onErrorMap

`onErrorResume` có thể biến một loại error signal thành response/phản hồi dự phòng; `onErrorMap` chuyển sang exception khác; `doOnError` chỉ quan sát/log, **không xử lý** lỗi. Ví dụ:

```java
return service.find(id)
        .onErrorMap(
                ExternalClientTimeoutException.class,
                error -> new NoteUnavailableException(error));
```

Đây là snippet kiến trúc, không thuộc project runnable, và giả định hai exception/service đã tồn tại. Đừng `onErrorResume(error -> Mono.empty())` cho mọi lỗi nếu response rỗng sẽ khiến bug biến thành 200/204 thành công giả. Với HTTP API, cần xác định lỗi nào là retryable, lỗi nào là 4xx và lỗi nào phải giữ 5xx.

### 13.4. WebExceptionHandler

`WebExceptionHandler` là tầng thấp hơn trong WebFlux `WebHandler` chain, hữu ích khi cần xử lý lỗi ngoài cơ chế annotated controller, filter hoặc routing. Nhưng nếu đã có `@RestControllerAdvice` cho lỗi controller thì không cần viết một global WebExceptionHandler chỉ để bắt lại các exception đó. Khi tự viết, phải giữ đúng event-loop, trạng thái response đã commit và quy tắc không ghi body hai lần.

### 13.5. ProblemDetail trong Spring Boot

Spring Framework hỗ trợ biểu diễn lỗi dạng `ProblemDetail` (RFC 9457). Spring Boot 3.3.x có lựa chọn như:

```properties
spring.webflux.problemdetails.enabled=true
```

Nếu bật, error response của infrastructure có thể chuyển sang dạng Problem Details theo khả năng/version. Không trộn một cách mù quáng giữa JSON `ApiError` tự định nghĩa và Problem Details rồi giả định tất cả endpoint trả cùng schema. Cần quyết định contract, cấu hình handlers và test từng nhóm lỗi.

## 14. Đừng chặn event loop khi xử lý validation/error

WebFlux dùng non-blocking architecture, nhưng **không phải mọi code trong controller đều tự động non-blocking**. Ví dụ:

```java
@PostMapping("/heavy")
public Mono<NoteView> heavy(
        @Valid @RequestBody CreateNote request) {
    slowJdbcRepository.save(request); // Blocking!
    return service.create("tenant-a", request);
}
```

Đây là **phản ví dụ**, không phải code project chạy được. Nếu gọi JDBC/file I/O đồng bộ trên event-loop, request khác có thể bị ảnh hưởng bởi độ trễ. Việc method trả `Mono` sau đó không xóa blocking đã diễn ra.

Với blocking dependency chưa thay thế được, có thể dùng:

```java
Mono.fromCallable(() -> legacyRepository.load(id))
        .subscribeOn(Schedulers.boundedElastic());
```

Đây là snippet minh họa, cần `reactor.core.scheduler.Schedulers` và dependency phù hợp; boundedElastic là cách cô lập một số blocking operation khỏi event-loop, **không phải** giải pháp vô hạn cho việc chạy mọi truy vấn/blocking task. Ưu tiên client reactive như R2DBC, `WebClient` hoặc driver reactive nơi thực sự phù hợp.

**Đối với validation custom:** validator không nên gọi HTTP/database/blocking nặng trong một constraint validator chạy ngay lúc decoding/argument resolving. Nếu cần nghiệp vụ bất đồng bộ (như kiểm tra uniqueness DB), nên chuyển thành bước reactive của service và mapping lỗi rõ ràng, không nhồi vào `@NotBlank`/`ConstraintValidator` sync.

## 15. Những cạm bẫy phổ biến

### 15.1. Viết WebFlux test nhưng ứng dụng thực đang chạy MVC

Nếu có cả `spring-boot-starter-web` lẫn `spring-boot-starter-webflux` trên classpath, Spring Boot thường ưu tiên MVC. Đừng dùng `@WebFluxTest` rồi kết luận runtime thực cũng là WebFlux. Kiểm tra dependency và web-application-type.

### 15.2. Dùng MockMvc cho WebFlux

`MockMvc` chủ yếu dùng cho Spring MVC servlet stack. WebFlux controller tests dùng `WebTestClient`, hỗ trợ cả mock context và running server. Không nhầm hai test client có API giống nhau về mức HTTP assertion.

### 15.3. Trông chờ @Valid hoạt động khi thiếu validator

Không có Bean Validation implementation thì `@Valid` có thể không thực thi constraint như mong đợi. Thêm `spring-boot-starter-validation` và viết negative test với body invalid.

### 15.4. Chỉ xem lỗi 400 là đủ

`400` có thể đến từ JSON malformed, conversion lỗi hoặc Bean Validation. Nếu contract cần phân biệt lỗi, assertion phải kiểm tra response `code`, không chỉ status.

### 15.5. Bắt mọi lỗi bằng @ExceptionHandler(Exception.class) rồi trả 400

Cách này che lỗi server thành lỗi client, gây khó theo dõi và làm API retry sai. Phân nhóm lỗi client/server và giữ một fallback 500 đúng nghĩa khi cần.

### 15.6. Đọc Servlet/MVC exception và áp vào WebFlux

`MethodArgumentNotValidException` là tên rất thường gặp ở MVC; WebFlux validation một đối tượng thường dùng `WebExchangeBindException`. Với Spring 6.1+ còn có `HandlerMethodValidationException`. Bám đúng stack và phiên bản.

### 15.7. Tăng max-in-memory-size không giới hạn

Sửa `DataBufferLimitException` bằng mức buffer quá lớn có thể tăng tiêu thụ RAM dưới tải. Thiết kế giới hạn payload hợp lý, streaming nếu cần và bộ test kiểm tra boundary.

### 15.8. Không phân biệt Accept và Content-Type

`Content-Type` nói **body client gửi thuộc media type nào**. `Accept` nói **client muốn nhận loại response nào**. Lỗi 415 và 406 xuất phát từ hai ràng buộc khác nhau.

### 15.9. Khẳng định Mono.error đã ném trước khi subscribe

Sai với nhiều publisher: lỗi được phát khi subscribe. `StepVerifier` giúp kiểm tra terminal error signal đúng semantics.

### 15.10. Custom errors nhưng không test body schema

Chỉ kiểm tra `expectStatus().isBadRequest()` chưa chứng minh code/message đã được chuẩn hóa; kiểm tra `jsonPath("$.code")` và tránh phụ thuộc stack trace/message nội bộ dễ đổi.

### 15.11. Thực hiện I/O trong validation

Constraint validator đồng bộ mà gọi DB/network có thể chặn event loop. Giữ Bean Validation cho constraint cục bộ, còn business async check để service reactive xử lý.

### 15.12. Lưu state test qua Spring context cache

`@WebFluxTest` và `@SpringBootTest` có context cache; mock được reset theo Boot, nhưng cache thật/dữ liệu DB/queue không tự được dọn. Cần fixture cleanup và test isolation đúng.

## 16. Checklist QA theo tình huống

Trước khi merge một WebFlux test suite:

1. Test có thực sự dùng WebFlux (`spring-boot-starter-webflux`/reactive type), không vô tình MVC?
2. Validation DTO đã có `@Valid`/`@Validated` và Bean Validation dependency chưa?
3. Đã phân biệt validation một đối tượng và method validation chưa?
4. Test JSON hỏng, sai type, body thiếu và body vi phạm constraint có tách nguyên nhân không?
5. `Content-Type` và `Accept` có được gửi đúng để kiểm tra 415/406 không?
6. `@RestControllerAdvice` có trả HTTP status và error code ổn định không?
7. Domain `Mono.error(...)` có được map 404/409/5xx theo contract thay vì biến thành 200 rỗng không?
8. `@WebFluxTest` có mock đúng service và load advice cần test không?
9. `WebTestClient` có assert status + JSON body, và `verifyNoInteractions` cho input lỗi khi cần không?
10. Với publisher logic, `StepVerifier` có kiểm tra value/complete/error signal không?
11. Với request cần streaming/large payload, đã kiểm tra codec buffer limits và memory strategy chưa?
12. Nếu có custom codec, test cả đúng media type lẫn unsupported/unknown media type chưa?
13. Có dùng blocking JDBC/HTTP hoặc `block()` ngay trên event-loop không?
14. Nếu Spring Security bật, test có setup authentication/authorization/CSRF phù hợp không?
15. Test context, data fixture và resources có cô lập để chạy song song/CI ổn định không?
16. Có test RANDOM_PORT khi cần HTTP integration qua socket thật, thay vì chỉ WebFlux mock context?
17. Có kiểm tra rõ số test method dự kiến và kết quả thực tế trong Gradle report không?

## 17. Bài tập thực hành

Với project ở mục 5–9:

1. Bỏ `spring-boot-starter-validation` và chạy lại test body invalid: giải thích khác biệt giữa decode thành công và constraint có được thực thi hay không.
2. Đổi `CreateNote.title` thành chuỗi rỗng, chạy WebTestClient; xác nhận `400` và `VALIDATION_ERROR`, service không được gọi.
3. Gửi `priority:"high"` thay vì số; vì sao đây là **codec/conversion error** chứ không phải `@Min`?
4. Gửi JSON hợp lệ với `Content-Type: text/plain`; kiểm tra `415` và lý do `consumes` không match.
5. Gửi `Accept: application/xml` cho GET chỉ trả JSON; kiểm tra `406`.
6. Thêm `@RequestParam @Min(1) int page` vào một endpoint mới; xử lý `HandlerMethodValidationException` và viết test riêng cho `page=0`.
7. Đổi service find thành `Mono.error(new NoteNotFoundException(999))`; quan sát `@RestControllerAdvice` trả `404`.
8. Đổi handler not-found thành `onErrorResume(ex -> Mono.empty())` rồi so sánh kết quả; giải thích vì sao nó có thể che lỗi.
9. Dùng `StepVerifier` kiểm tra publisher phát một value rồi complete, và một publisher phát error mà không cần `block()`.
10. Tạo test riêng cho `spring.codec.max-in-memory-size=8KB`, gửi body lớn hơn giới hạn; tìm exception/status thực tế trước khi thiết kế mapping 413 theo yêu cầu.
11. Viết một functional route đọc `CreateNote` bằng `bodyToMono` và gọi Validator thủ công; so sánh với `@Valid @RequestBody` trong annotated controller.
12. Đặt một blocking sleep trong controller chỉ ở sandbox, quan sát độ trễ/BlockHound nếu cấu hình, sau đó thay bằng luồng reactive phù hợp.

## 18. Tài liệu tham khảo

- [Spring Framework — WebFlux Validation](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-validation.html): `WebExchangeBindException` và `HandlerMethodValidationException`.
- [Spring Framework — WebFlux @RequestBody](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/requestbody.html): `HttpMessageReader`, reactive wrappers, `@Valid`.
- [Spring Framework — WebFlux WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): web testing không cần hoặc có HTTP server.
- [Spring Framework — WebFlux HTTP Message Codecs](https://docs.spring.io/spring-framework/reference/web/webflux/reactive-spring.html): codecs, buffer limits, reactive HTTP.
- [Spring Boot 3.3 — Testing WebFlux](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `@WebFluxTest`, `@MockBean`, `WebTestClient`, RANDOM_PORT.
- [Spring Boot 3.3 — Common Application Properties](https://docs.spring.io/spring-boot/3.3/appendix/application-properties/): `spring.codec.max-in-memory-size` và `spring.webflux.problemdetails.enabled`.

## 19. Kết luận

Để kiểm thử WebFlux đáng tin, cần **tách đường lỗi validation, codec và domain** thay vì chỉ dựa vào một assertion `400`. `@Valid @RequestBody` và Bean Validation kiểm tra DTO sau khi decode; constraint đặt trực tiếp trên method có thể kích hoạt method validation; codec chọn cách đọc/ghi theo media type và giới hạn buffering; còn `@RestControllerAdvice` hoặc cơ chế handler tương ứng biến exception/error signal thành HTTP status và error body theo hợp đồng.

Dùng `@WebFluxTest` + `WebTestClient` để kiểm tra validation, JSON và error mapping nhanh; dùng `StepVerifier` để kiểm tra Reactor signals; thêm `@SpringBootTest(RANDOM_PORT)` khi cần chứng minh HTTP ingress thực. Tránh blocking trên event-loop, không tăng buffer vô hạn và không biến lỗi server thành lỗi client một cách tùy tiện.
