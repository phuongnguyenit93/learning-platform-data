# RequestBodyAdvice, ResponseBodyAdvice và giới hạn biến đổi nội dung dùng chung trong Spring MVC

## 1. Bối cảnh: vì sao cần can thiệp vào HTTP body?

Khi nhiều endpoint Spring MVC có một yêu cầu biểu diễn giống nhau, ta có thể muốn **chỉnh dữ liệu request vừa được giải mã** hoặc **điều chỉnh response trước khi ghi ra HTTP** mà không lặp cùng một đoạn code ở mỗi controller. Ví dụ:

- Chuẩn hóa khoảng trắng ở một loại request DTO cụ thể trước validation.
- Thêm cấu trúc JSON `{"data": ...}` cho **một nhóm** API có hợp đồng response rõ ràng.
- Bổ sung metadata/header dựa trên chính sách áp dụng cho controller đã chọn.
- Cung cấp xử lý đặc thù cho một loại body mà `HttpMessageConverter` đã đọc được.

Spring Web MVC cung cấp hai extension points:

- **`RequestBodyAdvice`:** can thiệp vào quá trình đọc body thành object Java, trước khi object được chuyển cho controller.
- **`ResponseBodyAdvice<T>`:** can thiệp vào object trả về sau khi converter ghi response đã được chọn, nhưng trước khi object được converter serialize xuống response body.

Đây là các hook của **Spring MVC trên Servlet stack**. Spring WebFlux sử dụng pipeline/reactive codecs khác; không chuyển nguyên các class advice dưới đây sang WebFlux. Ví dụ đầy đủ dùng **Java 17, Spring Boot 3.3.5, Spring Framework 6.1.x**, để các import, phương thức và HTTP kết quả có ngữ cảnh phiên bản rõ ràng.

**Nguyên tắc cốt lõi:** Advice giúp chia sẻ xử lý tại một vị trí của MVC pipeline. Nó không tự biến mọi kiểu response thành JSON, không được thiết kế để đọc tất cả body của mọi loại request, và không phải chỗ thay thế cho authorization, Bean Validation, streaming, error mapping hay logic nghiệp vụ.

## 2. Đặt hai advice vào vòng đời Spring MVC

Một chu kỳ request JSON thông thường:

```text
HTTP request / JSON bytes
       |
       v
Servlet Filter(s) / DispatcherServlet
       |
       v
HandlerMapping chọn controller method
       |
       v
Argument resolver gặp @RequestBody
       |
       v
Chọn HttpMessageConverter đọc JSON
       |
       v
RequestBodyAdvice.supports(...)
       |
       +--> beforeBodyRead(HttpInputMessage) nếu có body
       |         |
       |         v
       |    HttpMessageConverter.read(...)
       |         |
       |         v
       +--> afterBodyRead(Java object)
       |
       +--> handleEmptyBody(...) nếu body rỗng
       |
       v
Bean Validation nếu tham số dùng @Valid/@Validated
       |
       v
Controller method và logic ứng dụng
       |
       v
Return-value handler chọn response media type và converter
       |
       v
ResponseBodyAdvice.supports(...)
       |
       v
ResponseBodyAdvice.beforeBodyWrite(...)
       |
       v
HttpMessageConverter.write(...)
       |
       v
HTTP response / bytes
```

Sơ đồ đơn giản hóa để học: resolver, converter và framework có nhiều nhánh theo media type, kiểu tham số và cách trả về. Với body malformed JSON, converter có thể ném exception **trước** `afterBodyRead`; với body rỗng, `handleEmptyBody` là đường riêng. Khi body không qua converter, advice tương ứng có thể hoàn toàn không chạy. <u>Không suy luận rằng một advice luôn chạy với mọi HTTP request/response.</u>

Ví dụ controller nhận dữ liệu:

```java
@PostMapping("/notes")
@ResponseBody
public NoteView create(@Valid @RequestBody NoteInput input) {
    // ...
}
```

Đây là method minh họa. `RequestBodyAdvice` có thể xử lý `NoteInput` **sau JSON deserialization, trước validation**. `ResponseBodyAdvice` có thể xử lý `NoteView` **trước JSON serialization**. Nếu controller ném exception, luồng xuất response phụ thuộc exception resolver/handler; không mặc định đi theo kết quả return bình thường của method này.

## 3. RequestBodyAdvice: trách nhiệm và thứ tự các hook

Giao diện đầy đủ thuộc package `org.springframework.web.servlet.mvc.method.annotation.RequestBodyAdvice`. Các method tiêu biểu của Spring Framework 6.1:

```java
boolean supports(
    MethodParameter methodParameter,
    Type targetType,
    Class<? extends HttpMessageConverter<?>> converterType);

HttpInputMessage beforeBodyRead(
    HttpInputMessage inputMessage,
    MethodParameter parameter,
    Type targetType,
    Class<? extends HttpMessageConverter<?>> converterType) throws IOException;

Object afterBodyRead(
    Object body,
    HttpInputMessage inputMessage,
    MethodParameter parameter,
    Type targetType,
    Class<? extends HttpMessageConverter<?>> converterType);

Object handleEmptyBody(
    Object body,
    HttpInputMessage inputMessage,
    MethodParameter parameter,
    Type targetType,
    Class<? extends HttpMessageConverter<?>> converterType);
```

Các chữ ký trên là **trích mẫu API**, cần imports và nằm trong class triển khai interface để biên dịch. `RequestBodyAdviceAdapter` đã có implementations mặc định cho ba hook cuối, chỉ cần implement `supports` và override những hook muốn dùng.

### 3.1. supports: bộ lọc phạm vi đầu tiên

`supports(methodParameter, targetType, converterType)` được hỏi trước khi advice áp dụng. Nó cung cấp:

- `methodParameter`: vị trí tham số trong controller, dùng kiểm tra custom annotation hoặc kiểu tham số.
- `targetType`: kiểu Java thực sự được converter đọc; có thể khác parameter type (ví dụ `HttpEntity<NoteInput>`).
- `converterType`: class của converter mà Spring đã chọn.

Nếu trả `false`, advice bỏ qua tham số đó. Nếu trả `true`, các hook thích hợp có cơ hội chạy. Nên **lọc ít nhất theo endpoint/annotation + kiểu dữ liệu + converter** khi định thay đổi object; điều này bảo vệ những API không cùng hợp đồng dữ liệu.

```java
@Override
public boolean supports(
        MethodParameter parameter, Type targetType,
        Class<? extends HttpMessageConverter<?>> converterType) {
    return parameter.hasParameterAnnotation(NormalizeNote.class)
            && targetType == NoteController.NoteInput.class
            && MappingJackson2HttpMessageConverter.class
                    .isAssignableFrom(converterType);
}
```

Đây là đoạn từ ví dụ hoàn chỉnh bên dưới. Nó chỉ opt-in khi có `@NormalizeNote`, kiểu đích đúng `NoteInput`, và converter tương thích Jackson JSON. Không dùng điều kiện `return true` toàn cục rồi ép mọi `Object` sang cùng một DTO.

### 3.2. beforeBodyRead: trước lúc converter đọc bytes

`beforeBodyRead` nhận `HttpInputMessage` chứa headers + `InputStream` request. Hook có thể trả nguyên `inputMessage` hoặc **một wrapper** hợp lệ cung cấp body stream khác. Mọi thay đổi bytes có thể gây hệ quả:

- Nếu chỉnh raw JSON, phải giữ JSON hợp lệ và thống nhất encoding/charset, media type.
- Không thể giả định stream đọc lại được: input stream thường chỉ tiêu thụ một lần.
- Nếu thay byte length, `Content-Length` cũ không còn đúng; headers/content encoding/integrity signature liên quan cũng phải được cân nhắc.
- Giải mã payload bảo mật, giải nén hoặc kiểm tra checksum là vấn đề protocol/security cần thiết kế rõ ràng; không nên thêm bằng advice chỉ vì có sẵn hook.
- Việc đọc toàn bộ body vào RAM để biến đổi có rủi ro về dung lượng/DoS; cần giới hạn request ở tầng phù hợp.

Trong đa số API JSON thông thường, xử lý **object sau conversion** bằng `afterBodyRead` dễ kiểm chứng hơn thao tác lại bytes trước Jackson.

### 3.3. afterBodyRead: sau converter, trước controller

`afterBodyRead` nhận đối tượng đã được converter parse thành công. Bạn có thể trả nguyên object hoặc trả một object khác **tương thích với kiểu tham số controller**. Ví dụ tạo record mới từ một record cũ với `text.strip()`, rồi để Bean Validation kiểm tra giá trị mới.

Điểm mấu chốt: nếu input `"   "`, sau khi trim thành `""`, `@NotBlank` mới báo vi phạm. Điều này là một chính sách **thay đổi nghĩa của input**, vì vậy phải được công khai trong API contract và chỉ áp dụng có chủ đích. Không tự ý thay tất cả các text fields của mọi DTO — khoảng trắng có thể có nghĩa trong mật khẩu, chữ ký, truy vấn tìm kiếm hoặc nội dung người dùng.

Nếu converter không parse được JSON thì không có object hợp lệ để truyền vào `afterBodyRead`. Trường hợp này thường dẫn tới `HttpMessageNotReadableException` và HTTP `400` theo cấu hình phổ biến.

### 3.4. handleEmptyBody: request body thực sự rỗng

`handleEmptyBody` được gọi trên nhánh body rỗng của request được xử lý qua body reader. Default adapter trả nguyên body (thường là `null`). Nếu tham số `@RequestBody` là bắt buộc, kết quả `null` có thể khiến Spring báo thiếu body. Không xem JSON `{}`, JSON `null`, request không có body, và JSON lỗi cú pháp là một tình huống: chúng không nhất thiết kích hoạt cùng hook.

Nếu hợp đồng API quy định body là bắt buộc, giải pháp nhất quán thường là **trả lỗi client**, không bí mật tạo object mặc định từ body rỗng. Chỉ tự cấp default khi endpoint thật sự công bố điều đó, và kiểm chứng interaction với `@RequestBody(required = true/false)`.

### 3.5. Đường dữ liệu được hỗ trợ

Javadoc mô tả `RequestBodyAdvice` cho các tham số được xử lý qua `@RequestBody` hoặc `HttpEntity`. Không mặc định nó xử lý toàn bộ `@ModelAttribute`, query params, form binding, multipart stream hoặc những lần code tự gọi `request.getInputStream()`. `@RequestPart` có phần xử lý riêng; nếu cần chính sách ở multipart phải kiểm tra chính xác resolver và hành vi của phiên bản Spring đang dùng.

## 4. ResponseBodyAdvice<T>: can thiệp trước lúc ghi body

Giao diện `org.springframework.web.servlet.mvc.method.annotation.ResponseBodyAdvice<T>` có hai method chính:

```java
boolean supports(
    MethodParameter returnType,
    Class<? extends HttpMessageConverter<?>> converterType);

T beforeBodyWrite(
    T body,
    MethodParameter returnType,
    MediaType selectedContentType,
    Class<? extends HttpMessageConverter<?>> selectedConverterType,
    ServerHttpRequest request,
    ServerHttpResponse response);
```

Đây là chữ ký minh họa của API Spring MVC 6.1. Advice được dùng cho kết quả `@ResponseBody` và `ResponseEntity` khi MVC dùng converter để viết body; `@RestController` cũng sử dụng semantics `@ResponseBody`.

- `supports` xác định có nên áp dụng cho method return và converter đã chọn hay không.
- `beforeBodyWrite` nhận body và metadata **sau khi Spring chọn converter, trước khi gọi converter.write**. Bạn có thể trả nguyên body hoặc object khác; chỉ nên trả kiểu mà converter đã chọn vẫn serialize được.
- `selectedContentType` đã phản ánh negotiation cho response; advice không nên tùy tiện giả định JSON khi actual response là text/binary.
- `response.getHeaders()` cho phép bổ sung header liên quan response, nhưng việc thay body và headers phải nhất quán.

### Vì sao “wrap mọi response bằng {data: ...}” có thể hỏng?

Giả sử method trả `String`:

```java
@GetMapping(path = "/ping", produces = "text/plain")
public String ping() {
    return "pong";
}
```

Spring có thể chọn `StringHttpMessageConverter`. Nếu `ResponseBodyAdvice<Object>` thay chuỗi bằng `new Envelope<>("pong")`, converter **đã được chọn từ trước** vẫn có thể kỳ vọng nhận `String`. Hậu quả có thể là `ClassCastException`, lỗi ghi response hoặc body sai định dạng. Advice **không tự chạy lại thuật toán chọn converter sau khi bạn đổi object**.

Vì vậy, nên kiểm tra đồng thời:

1. **Hợp đồng endpoint** (annotation, package/controller, return type).
2. **Loại converter** (`MappingJackson2HttpMessageConverter` nếu wrap DTO JSON).
3. **Loại body thực tế** trước khi sửa.
4. **Response media type**; không thay đổi ngoài các representation đã cam kết.
5. **Body null/empty, status và headers** để không phá những response không có nội dung.

Kể cả khi converter hỗ trợ object mới, việc bọc `{"data": ...}` cũng **là thay đổi công khai về JSON schema**. Client và OpenAPI schema phải biết trước.

### Tương quan với ResponseEntity

`ResponseEntity<T>` cho phép controller đặt status/headers/body. `ResponseBodyAdvice` có thể can thiệp body khi return-value handler ghi body qua converter, nhưng điều đó **không có nghĩa** advice được quyền đổi ngầm status `201` thành `200`, thay `Content-Type` sang tùy ý hoặc sinh body trên status `204 No Content`. Các trường hợp `ResponseEntity<Void>`, `HEAD`, `304`, download file, binary streams hay byte ranges cần xem là ngoại lệ rõ ràng đối với một chính sách wrap JSON.

## 5. So sánh hai advice

| Khía cạnh | `RequestBodyAdvice` | `ResponseBodyAdvice` |
| --- | --- | --- |
| Thời điểm | Trước/sau converter **đọc request** | Sau khi chọn converter **ghi response**, trước thao tác ghi |
| Đầu vào chính | `HttpInputMessage` hoặc object đã deserialize | Object controller trả về, headers/selected media type |
| Lọc phạm vi | `supports(MethodParameter, Type, converterType)` | `supports(returnType, converterType)` |
| Hook cần nhớ | `beforeBodyRead`, `afterBodyRead`, `handleEmptyBody` | `beforeBodyWrite` |
| Use case phù hợp | Chuẩn hóa DTO cụ thể đã được parse | Wrap DTO JSON có chủ đích, bổ sung headers |
| Rủi ro tiêu biểu | Đọc stream, thay input trước validation, thay nghĩa dữ liệu | Thay return type sau chọn converter, thay API schema |
| Không thay thế được | Authorization, validation, giải quyết mọi kiểu form/multipart | Exception mapping toàn cục, negotiation, serializer cho mọi format |

**Hai advice hoạt động theo hướng khác nhau.** Request advice không phải “filter mọi inbound bytes”, response advice không phải “filter mọi outbound bytes”. Dùng hook đúng đối tượng giảm rủi ro khó phát hiện.

## 6. Ví dụ chạy được: opt-in normalization và JSON envelope

Ví dụ có ba endpoint:

- `POST /api/notes/normalized`: chỉ endpoint này **opt-in** để strip whitespace ở `NoteInput.text` trước `@Valid`; response được wrap thành `{"data":{"text":"..."}}`.
- `POST /api/notes/plain`: JSON input/output bình thường, không qua chính sách normalization/wrapping của hai advice ví dụ.
- `GET /api/text`: text response qua `StringHttpMessageConverter`, giữ nguyên text; không wrap.

Chính sách cố tình được áp dụng hẹp. Một endpoint mới không nên bỗng thay đổi JSON hay input chỉ vì dùng chung `@RestController`.

### 6.1. Cấu trúc project

```text
mvc-body-advice-demo/
├── pom.xml
└── src/main/java/example/bodyadvice/
    ├── BodyAdviceApplication.java
    ├── NormalizeNote.java
    ├── WrapData.java
    ├── NoteController.java
    ├── NormalizeNoteAdvice.java
    └── WrapDataAdvice.java
```

Các class cùng package `example.bodyadvice`, vì vậy dùng type từ file khác trong package không cần import riêng.

**`pom.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>mvc-body-advice-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

**`src/main/java/example/bodyadvice/BodyAdviceApplication.java`**

```java
package example.bodyadvice;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BodyAdviceApplication {
    public static void main(String[] args) {
        SpringApplication.run(BodyAdviceApplication.class, args);
    }
}
```

### 6.2. Hai annotation chỉ rõ endpoint muốn dùng chính sách nào

**`NormalizeNote.java`**

```java
package example.bodyadvice;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.PARAMETER)
@Retention(RetentionPolicy.RUNTIME)
public @interface NormalizeNote {}
```

**`WrapData.java`**

```java
package example.bodyadvice;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Target(ElementType.METHOD)
@Retention(RetentionPolicy.RUNTIME)
public @interface WrapData {}
```

`@NormalizeNote` đặt trên **tham số** cần biến đổi; `@WrapData` đặt trên **method** cho phép wrap response. Runtime retention cần thiết vì Spring dùng reflection/metadata của handler method để phát hiện các annotation này.

### 6.3. Controller: hai contract JSON khác nhau, một endpoint text

**`NoteController.java`**

```java
package example.bodyadvice;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api")
public class NoteController {

    public record NoteInput(@NotBlank String text) {}

    public record NoteOutput(String text) {}

    @PostMapping(path = "/notes/normalized",
                 consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    @ResponseStatus(HttpStatus.CREATED)
    @WrapData
    public NoteOutput normalized(
            @NormalizeNote @Valid @RequestBody NoteInput request) {
        return new NoteOutput(request.text());
    }

    @PostMapping(path = "/notes/plain",
                 consumes = MediaType.APPLICATION_JSON_VALUE,
                 produces = MediaType.APPLICATION_JSON_VALUE)
    public NoteOutput plain(
            @Valid @RequestBody NoteInput request) {
        return new NoteOutput(request.text());
    }

    @GetMapping(path = "/text",
                produces = MediaType.TEXT_PLAIN_VALUE)
    public String text() {
        return "ready";
    }
}
```

`@NotBlank` kiểm tra chuỗi có nội dung không chỉ là whitespace. Controller không tự trim input. Biến đổi được đặt trong request advice, chỉ kích hoạt khi có `@NormalizeNote`; `@WrapData` cũng chỉ gắn vào endpoint cần envelope. Không có database, authentication hay state: response phản ánh input.

### 6.4. Request advice: sau Jackson, trước validation

**`NormalizeNoteAdvice.java`**

```java
package example.bodyadvice;

import java.lang.reflect.Type;

import org.springframework.core.MethodParameter;
import org.springframework.http.HttpInputMessage;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.servlet.mvc.method.annotation.RequestBodyAdviceAdapter;

@ControllerAdvice(assignableTypes = NoteController.class)
public class NormalizeNoteAdvice extends RequestBodyAdviceAdapter {

    @Override
    public boolean supports(
            MethodParameter parameter,
            Type targetType,
            Class<? extends HttpMessageConverter<?>> converterType) {

        return parameter.hasParameterAnnotation(NormalizeNote.class)
                && targetType == NoteController.NoteInput.class
                && MappingJackson2HttpMessageConverter.class
                        .isAssignableFrom(converterType);
    }

    @Override
    public Object afterBodyRead(
            Object body,
            HttpInputMessage inputMessage,
            MethodParameter parameter,
            Type targetType,
            Class<? extends HttpMessageConverter<?>> converterType) {

        if (body instanceof NoteController.NoteInput note) {
            String text = note.text();
            return new NoteController.NoteInput(
                    text == null ? null : text.strip());
        }
        return body;
    }
}
```

Các chi tiết:

- `@ControllerAdvice(assignableTypes = NoteController.class)` giới hạn controller mà advice nhắm tới. Trong `supports` còn có hai lớp giới hạn: marker annotation và loại converter/DTO.
- `RequestBodyAdviceAdapter` giữ nguyên `beforeBodyRead` và `handleEmptyBody` mặc định; ví dụ chỉ thay đổi object khi Jackson đã deserialize thành công.
- `String.strip()` (Java 11+) loại bỏ các ký tự whitespace ở đầu/cuối theo `Character.isWhitespace`. Nó **không** giải quyết Unicode normalization tổng quát, không sanitize HTML và không thay thế kiểm tra bảo mật.
- Khi `text=null`, giữ nguyên null để `@NotBlank` xử lý; không lặng lẽ gán chuỗi mặc định.
- Advice trả **một `NoteInput` mới**, cùng kiểu controller đang yêu cầu, không trả envelope hoặc object tùy ý gây lỗi ép kiểu.
- Lỗi JSON syntax xảy ra ở converter nên không mong `afterBodyRead` được gọi để “sửa” mọi JSON hỏng.

### 6.5. Response advice: chỉ bọc JSON DTO có marker

**`WrapDataAdvice.java`**

```java
package example.bodyadvice;

import org.springframework.core.MethodParameter;
import org.springframework.http.MediaType;
import org.springframework.http.converter.HttpMessageConverter;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.http.server.ServerHttpRequest;
import org.springframework.http.server.ServerHttpResponse;
import org.springframework.web.bind.annotation.ControllerAdvice;
import org.springframework.web.servlet.mvc.method.annotation.ResponseBodyAdvice;

@ControllerAdvice(assignableTypes = NoteController.class)
public class WrapDataAdvice implements ResponseBodyAdvice<Object> {

    public record Envelope<T>(T data) {}

    @Override
    public boolean supports(
            MethodParameter returnType,
            Class<? extends HttpMessageConverter<?>> converterType) {

        return returnType.hasMethodAnnotation(WrapData.class)
                && MappingJackson2HttpMessageConverter.class
                        .isAssignableFrom(converterType);
    }

    @Override
    public Object beforeBodyWrite(
            Object body,
            MethodParameter returnType,
            MediaType selectedContentType,
            Class<? extends HttpMessageConverter<?>> selectedConverterType,
            ServerHttpRequest request,
            ServerHttpResponse response) {

        if (body == null) {
            return null;
        }
        response.getHeaders().add("X-Envelope-Applied", "true");
        return new Envelope<>(body);
    }
}
```

**Vì sao ví dụ này an toàn trong phạm vi minh họa?** Endpoint đánh dấu `@WrapData` chỉ trả `NoteOutput` được Jackson serialize dưới JSON; body mới là `Envelope<NoteOutput>`, cũng được Jackson xử lý. Chúng ta không bọc text, bytes, `Resource` hoặc response không có body. Trong ứng dụng thật, nên còn kiểm tra rằng kiểu body thuộc một tập DTO/response contract đã duyệt để tránh vô tình bọc loại return mới nếu developer thêm `@WrapData` nhầm chỗ.

`beforeBodyWrite` có thể thay object, nhưng **không thay được kết quả chọn converter đã xảy ra trước đó**. Khi body null, hook giữ nguyên null; nó không cố tạo `{"data":null}` trong trường hợp response có chủ đích không có body. Header `X-Envelope-Applied` chỉ được thêm khi body thực sự được bọc.

### 6.6. Chạy ứng dụng

Mở terminal tại thư mục `mvc-body-advice-demo` có `pom.xml`:

```bash
mvn spring-boot:run
```

Yêu cầu JDK 17+ và Maven hoạt động. Spring Boot mặc định mở `http://localhost:8080` nếu không có cấu hình thay đổi cổng.

**Gửi input JSON với khoảng trắng và marker opt-in:**

```bash
curl -i -X POST http://localhost:8080/api/notes/normalized \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"text":"  Hello MVC  "}'
```

Các phần quan trọng của response:

```http
HTTP/1.1 201
Content-Type: application/json
X-Envelope-Applied: true

{"data":{"text":"Hello MVC"}}
```

Giải thích theo thứ tự:

1. Jackson đọc JSON thành `new NoteInput("  Hello MVC  ")`.
2. `NormalizeNoteAdvice.supports` đúng vì tham số có `@NormalizeNote` và converter JSON phù hợp.
3. `afterBodyRead` trả `new NoteInput("Hello MVC")`.
4. `@Valid` kiểm tra `@NotBlank` trên giá trị đã được strip.
5. Controller trả `new NoteOutput("Hello MVC")` với status `201`.
6. `WrapDataAdvice.supports` đúng vì method có `@WrapData` và converter writer là Jackson.
7. `beforeBodyWrite` trả `new Envelope<>(NoteOutput)` và bổ sung response header.
8. Jackson ghi JSON có field `data`.

**So sánh endpoint không opt-in:**

```bash
curl -i -X POST http://localhost:8080/api/notes/plain \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json' \
  -d '{"text":"  Hello MVC  "}'
```

Kết quả chính:

```http
HTTP/1.1 200
Content-Type: application/json

{"text":"  Hello MVC  "}
```

Không có `X-Envelope-Applied` do advice không bọc response; khoảng trắng được giữ nguyên do tham số không gắn `@NormalizeNote`.

**Endpoint text không bị biến đổi:**

```bash
curl -i http://localhost:8080/api/text -H 'Accept: text/plain'
```

Response body:

```text
ready
```

Ở đây `StringHttpMessageConverter` có thể được chọn. Vì method không có `@WrapData` và media type là text, chương trình không wrap text thành JSON. Đây là kiểm tra quan trọng chống lỗi chọn converter.

**Validation chạy trên dữ liệu đã chuẩn hóa:**

```bash
curl -i -X POST http://localhost:8080/api/notes/normalized \
  -H 'Content-Type: application/json' \
  -d '{"text":"   "}'
```

`afterBodyRead` trả `NoteInput("")`, sau đó `@NotBlank` không đạt; response thường là `400 Bad Request`. Không thể kết luận body lỗi mặc định cũng có `data`: annotation `@WrapData` áp dụng cho return của handler được chọn, còn exception response có pipeline xử lý riêng.

**JSON malformed:**

```bash
curl -i -X POST http://localhost:8080/api/notes/normalized \
  -H 'Content-Type: application/json' \
  --data-binary '{"text":'
```

Converter không thể parse nội dung; thường trả `400`. Advice `afterBodyRead` không có DTO hợp lệ để sửa. Header lỗi/JSON body thực tế tùy cấu hình của Spring Boot và exception handlers.

Trên PowerShell, có thể thử bằng `Invoke-RestMethod`:

```powershell
Invoke-RestMethod -Method Post -Uri 'http://localhost:8080/api/notes/normalized' -ContentType 'application/json' -Body '{"text":"  Hello MVC  "}'
```

PowerShell hiển thị đối tượng JSON đã parse theo kiểu PowerShell; muốn quan sát nguyên status/header/body, dùng công cụ HTTP cho phép xem raw response.

## 7. Những giới hạn quan trọng của biến đổi nội dung dùng chung

### 7.1. Phạm vi không tự động bao trùm mọi request

`RequestBodyAdvice` gắn với body được resolver/converter xử lý như `@RequestBody` và `HttpEntity`. Nó không phải Servlet `Filter` đọc mọi request, không xử lý mặc định query string, path variables, session state, toàn bộ HTML form binding hay body do controller đọc thủ công. Việc có thể dùng advice trong một số resolver khác phải kiểm tra chính xác theo phiên bản và implementation; không lấy một kết quả quan sát được rồi hứa tính toàn cục.

Nếu cần áp dụng cho **raw HTTP requests trước MVC routing**, hãy đánh giá Servlet `Filter`. Nhưng Filter cũng có rủi ro tiêu thụ stream và thứ tự filter; không tự đọc body vô hạn để log/biến đổi.

### 7.2. Response advice không bảo đảm chạy với mọi kiểu return

Response body phải đi qua một MVC return-value handler có message conversion phù hợp. Một controller render Thymeleaf/JSP view theo `ModelAndView` không đi theo cùng tuyến trả JSON. File streaming, `StreamingResponseBody`, `SseEmitter`, `ResponseBodyEmitter`, WebSocket, response bị commit sớm, response không có body và servlet tự ghi output cũng có vòng đời khác.

Nếu contract yêu cầu thống nhất nội dung cho từng loại transport, hãy tạo policy riêng phù hợp transport đó. Đừng ép một `ResponseBodyAdvice<Object>` bao trùm cả tải tệp, SSE, binary và HTML view.

### 7.3. Chọn converter xảy ra trước response advice

`ResponseBodyAdvice.beforeBodyWrite` được gọi **sau khi** Spring đã xác định converter. Khi advice đổi `String` thành `Map` hoặc DTO, converter được chọn từ `String` có thể không serialize được kiểu mới. Lỗi có thể phát sinh ngay cả khi JSON mapper tồn tại trên classpath. Điều kiện `supports` cần kiểm tra converter, return annotation/type, và loại body mới có tương thích không.

Với JSON API muốn một envelope ổn định, cách dễ bảo đảm hợp đồng hơn là **controller/service trả chính kiểu `ApiResponse<T>`** theo contract, hoặc dùng advice chỉ cho endpoints đã khai báo rõ. Nếu dùng streaming/binary, giữ response type và converter ban đầu.

### 7.4. Media type, headers và payload phải nhất quán

Biến đổi bytes hoặc object có thể làm thay đổi representation. Cần xét:

- `Content-Type` và charset có phù hợp body mới?
- `Content-Length` cũ có còn đúng nếu thay bytes? Có phải để framework/container tính lại thay vì giữ một giá trị stale?
- `Content-Encoding`, compression và checksums có cần điều chỉnh?
- `ETag`, `Last-Modified`, cache validators, response caching có còn phản ánh nội dung mới?
- Response chứa chữ ký số hay HMAC trên **raw bytes** thì biến đổi trước/sau ký có phá tính toàn vẹn không?
- Có thay đổi JSON schema mà client, mobile apps, OpenAPI và tests chưa biết?

Một thay đổi “nhỏ” như thêm envelope có thể phá ETag hoặc response clients đang parse các fields ở top-level. Nếu byte transformation là bắt buộc, hãy thiết kế một tầng có trách nhiệm với headers, streaming và integrity; không chỉ sửa body bằng hook.

### 7.5. Security: không dùng advice để thay authorization

Advice có thể normalize/sanitize một tập DTO đã chọn, nhưng không nên âm thầm thay đổi identity, tenant, permission hay ownership mà service không kiểm chứng. Đặc biệt:

- Không tự ghi log body chứa password, access token, session, PII hay thông tin tài chính.
- Đừng trông chờ normalization toàn cục biến dữ liệu nguy hiểm thành an toàn. HTML sanitization, SQL parameterization, path safety và output encoding có quy tắc khác nhau.
- Nếu input cần raw signature verification, việc trim/normalize trước xác minh có thể làm chữ ký sai. Sửa bytes sau xác minh cũng có thể làm khác payload đã được ký.
- Không bọc lỗi authentication/authorization thành HTTP `200 OK` chỉ để hợp một dạng `{"data": ...}`.
- Server vẫn cần input DTO giới hạn field, Bean Validation và authorization trên resource cụ thể.

### 7.6. Validation, exception và error responses

Request advice có thể đổi object **trước validation**, vì vậy validator nhìn thấy giá trị sau biến đổi. Đây là thứ tự quan trọng khi test. Tuy nhiên, advice không thay thế `@Valid`, custom validators hoặc business rules.

`@ControllerAdvice` dùng cho body advice cũng có thể là nơi chứa `@ExceptionHandler`, nhưng đó là **hai cơ chế khác nhau**. Response lỗi do handler/`ProblemDetail`, exception resolver hoặc `/error` sinh ra; không mặc định chịu cùng điều kiện wrap như success body. Nếu muốn error contract thống nhất, thiết kế `@RestControllerAdvice` / `ResponseEntityExceptionHandler` riêng, giữ status đúng và tránh double wrapping.

### 7.7. Performance, memory và concurrency

Các advice thường là Spring singleton beans. Không lưu thông tin request đang xử lý vào mutable instance fields vì nhiều request có thể chạy đồng thời. Nếu cần dữ liệu request-scoped, dùng method arguments, `request.getHeaders()`, scoped components hoặc request attributes phù hợp.

`beforeBodyRead` đọc toàn bộ stream có thể tăng RAM và latency cho mọi request. `ResponseBodyAdvice` tạo cây object mới cho response lớn cũng tăng allocations. Với payload lớn, ưu tiên DTO/streaming/codec phù hợp và đặt size limits. Không tạo wrapper liên tiếp khi nhiều advice có cùng nhiệm vụ, tránh `{"data":{"data":...}}`.

### 7.8. Thứ tự nhiều advice và idempotency

Khi có nhiều `@ControllerAdvice` / `RequestBodyAdvice` / `ResponseBodyAdvice`, thứ tự có thể liên quan `@Order` và cơ chế sorting của Spring. Thiết kế sao cho các biến đổi độc lập hoặc khai báo order rõ ràng khi thật sự cần. Phải test **thứ tự thực tế** trong phiên bản sử dụng; không giả định thứ tự quét classpath cố định.

Nên làm biến đổi **idempotent** nếu có khả năng đi qua cùng policy nhiều lần. Với envelope JSON, trước khi wrap có thể kiểm tra kiểu `ApiEnvelope` hoặc giới hạn chỉ một marker/handler. Với request normalization, `strip` có tính idempotent theo thao tác đó nhưng không có nghĩa chuỗi input ban đầu được bảo toàn — hợp đồng cần nói rõ.

### 7.9. Null body, HEAD, 204 và 304

Nếu trả `null` hoặc một response không có body, việc cố thêm envelope có thể đi ngược ngữ nghĩa HTTP. Đặc biệt `204 No Content` và `304 Not Modified` không phải response dùng để gửi JSON payload; `HEAD` chỉ có metadata như tương ứng GET, không truyền response body. Hãy tôn trọng status/method và các output paths đặc biệt.

Hook advice có thể vẫn được xét trong một vài nhánh `null` tùy implementation, nhưng không nên dựa vào đó để tạo body cho trường hợp không có nội dung. Trong ví dụ, `if (body == null) return null` giúp giữ nguyên hợp đồng không body.

## 8. Khi nào nên dùng cơ chế khác?

| Bài toán cụ thể | Cơ chế thường phù hợp hơn |
| --- | --- |
| Đọc/ghi định dạng body mới (binary/protocol) | `HttpMessageConverter<T>` được giới hạn kiểu và media type |
| Tùy chỉnh cách Jackson serialize/deserialize JSON | Jackson `ObjectMapper`, custom serializer/deserializer, `@Json*` |
| Chỉ thêm chuẩn response cho một endpoint | Trả `ResponseEntity<ApiEnvelope<T>>` hoặc DTO envelope tường minh |
| Chuẩn hóa lỗi từ nhiều controller | `@RestControllerAdvice` + `@ExceptionHandler` / `ResponseEntityExceptionHandler` |
| Authentication, authorization | Spring Security filters và application service/policy |
| Cross-cutting tracing/headers quanh mọi HTTP request | Servlet `Filter` hoặc `HandlerInterceptor` tùy yêu cầu |
| Chỉ đọc request metadata và đặt request attributes | `HandlerInterceptor` hoặc scoped service |
| Binding query/form thành object | `@ModelAttribute` + `WebDataBinder`, converter/formatter/validator |
| Streaming download/upload | `Resource`, multipart support, `StreamingResponseBody` hoặc I/O riêng |
| Áp dụng envelope cho một nhóm JSON API | `ResponseBodyAdvice` với opt-in và converter guard, sau khi định nghĩa schema |
| Đổi object sau JSON parse trước `@Valid` | `RequestBodyAdvice.afterBodyRead`, chỉ với DTO/chính sách rõ ràng |

Quyết định dựa trên **mục đích và thời điểm cần can thiệp**: raw bytes trước routing, object sau conversion, response DTO trước serialization, hay exception response. Mỗi vị trí có metadata và giới hạn riêng.

## 9. Các lỗi thường gặp và cách điều tra

| Hiện tượng | Nguyên nhân khả dĩ | Hướng kiểm tra |
| --- | --- | --- |
| `afterBodyRead` không chạy | `supports=false`, controller không dùng `@RequestBody`/`HttpEntity`, body rỗng hoặc converter ném lỗi | Kiểm tra tham số, converter, marker, nhánh `handleEmptyBody` và exception |
| Advice không được Spring phát hiện | Thiếu `@ControllerAdvice`, package ngoài component scan, scope assignableTypes sai | Kiểm tra annotation, component scan, handler class |
| `ClassCastException` lúc ghi response | `ResponseBodyAdvice` đổi body sang kiểu không phù hợp converter đã chọn | Kiểm tra `selectedConverterType`, `selectedContentType` và return type |
| JSON vẫn bị lỗi `400` trước controller | Jackson không parse được, body thiếu, validation không đạt | Phân biệt conversion exception với constraint violations |
| Text bị wrap thành object | `supports` trả true quá rộng, thiếu filter converter/marker | Giới hạn vào Jackson JSON DTO endpoints |
| Endpoint khác đột nhiên đổi JSON schema | Global advice áp dụng lan rộng | Dùng opt-in annotation, `@ControllerAdvice` scope và contract tests |
| Response đã bị wrap hai lần | Nhiều advice hoặc xử lý ở controller lẫn advice | Chỉ một nơi sở hữu envelope, kiểm tra wrapper type |
| Headers sai sau đổi payload | `Content-Type`, length, encoding, ETag không tương thích | Không thay raw bytes tùy tiện; kiểm chứng response wire format |
| Upload lớn làm server hết bộ nhớ | `readAllBytes()`, buffering body toàn cục | Giới hạn kích thước và chọn streaming/multipart đúng nhu cầu |
| Header advice xuất hiện nhưng response không đúng | Exception/đã commit response hoặc converter write fail | Kiểm tra stack trace và thời điểm write/commit |
| Validation không thấy value gốc | `afterBodyRead` đã mutate/thay DTO | Contract hóa normalization, test dữ liệu trước và sau |
| Response lỗi bị đổi thành HTTP 200 | Global envelope logic can thiệp sai status/exception | Giữ error contract và HTTP status, tách exception handling |

Một quy trình điều tra thực tế:

1. Ghi lại request `method`, URL, `Content-Type`, `Accept` và response status; không log secrets.
2. Xác nhận mapping đã khớp và argument thật sự đi qua converter.
3. Xem `supports` của advice request/response và loại converter được chọn.
4. Xem converter đã parse thành object hay ném lỗi; kiểm tra Bean Validation sau đó.
5. Đối chiếu object controller trả về với object advice giao cho converter.
6. Kiểm tra raw response headers/body, kể cả body rỗng, binary, `204` và error response.
7. Test các endpoint **không opt-in** để phát hiện ảnh hưởng ngoài phạm vi.

## 10. Tiêu chí thiết kế một advice dùng chung

Trước khi đưa một advice vào ứng dụng có nhiều module/controller, xác nhận:

- **Contract:** API nào đã công bố input normalization hoặc output envelope?
- **Scope:** annotation/controller/DTO/media type nào opt-in? Có đủ loại trừ text, HTML, file và streaming?
- **Converter:** body trước và sau biến đổi có còn tương thích converter được chọn?
- **Validation:** thay đổi diễn ra trước hay sau constraint checks; test giá trị rỗng, null, sai định dạng?
- **Error path:** có giữ đúng status và schema của validation errors, authorization errors, server errors?
- **Transport:** có giữ headers, charset, content length, cache validators và chữ ký?
- **Observability:** có đo được lỗi và latency mà không ghi payload nhạy cảm?
- **Concurrency:** advice có stateless hoặc xử lý state an toàn?
- **Regression tests:** có test endpoint nhận/không nhận policy, JSON/string/binary/null, cả success và failure?
- **Ownership:** một nơi chịu trách nhiệm normalize/wrap, tránh controller và advice cùng làm.

Không nhất thiết phải triển khai tất cả các loại hook. Trong nhiều hệ thống, **DTO tường minh + validation + controller trả `ResponseEntity<ApiResponse<T>>`** đã đủ, dễ quan sát và hợp đồng rõ. Dùng advice khi lợi ích tái sử dụng thật sự lớn hơn chi phí thay đổi ngầm ở một bước framework.

## 11. Câu hỏi tự kiểm tra

1. `RequestBodyAdvice.afterBodyRead` chạy trước hay sau JSON deserialization? Trước hay sau `@Valid` thông thường?
2. Body bị thiếu và JSON malformed có luôn gọi `afterBodyRead` không? Vì sao?
3. Vì sao điều kiện `ResponseBodyAdvice.supports` chỉ dựa vào `@RestController` là quá rộng?
4. Spring có chọn lại `HttpMessageConverter` sau khi `beforeBodyWrite` trả về một object loại khác không?
5. Với method trả `String` dùng `StringHttpMessageConverter`, vì sao wrap thành một record `Envelope<String>` có thể thất bại?
6. Khi nào cần `Filter` thay vì `RequestBodyAdvice`?
7. Nếu API trả `204 No Content`, có nên ép `{"data":null}` vào response không?
8. Nếu request chứa chữ ký HMAC cho raw bytes, việc trim trước kiểm tra chữ ký ảnh hưởng thế nào?
9. Vì sao `@ControllerAdvice` dùng cho xử lý body không tự động chuẩn hóa response của tất cả `@ExceptionHandler`?
10. Vì sao phải test cả endpoint không được áp dụng advice khi triển khai chính sách mới?

**Định hướng:** (1) Sau deserialize, trước validation. (2) Body rỗng theo `handleEmptyBody`; malformed JSON có thể fail trước `afterBodyRead`. (3) Vì có JSON, string, binary, streaming với converter/contract khác nhau. (4) Không dựa vào việc chạy lại lựa chọn converter. (5) Converter có thể kỳ vọng `String`. (6) Khi cần xử lý HTTP raw ở tầng Servlet trước pipeline MVC thích hợp. (7) Không, phải tôn trọng status không có body. (8) Raw bytes bị thay nên chữ ký không còn tương ứng. (9) Exception có return handler, status và contract riêng. (10) Để phát hiện việc advice vô tình thay đổi API khác.

## 12. Tài liệu tham khảo

- [Spring Framework 6.1 — RequestBodyAdvice Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/RequestBodyAdvice.html)
- [Spring Framework 6.1 — RequestBodyAdviceAdapter Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/RequestBodyAdviceAdapter.html)
- [Spring Framework 6.1 — ResponseBodyAdvice Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseBodyAdvice.html)
- [Spring Framework 6.1 — RequestResponseBodyMethodProcessor Javadoc](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/RequestResponseBodyMethodProcessor.html)
- [Spring Framework — @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — @ResponseBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/responsebody.html)
- [Spring Framework — @ControllerAdvice](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html)
- [Spring Framework — HTTP Message Converters](https://docs.spring.io/spring-framework/reference/web/webmvc/message-converters.html)

Bài học này mô tả cơ chế cho Spring MVC 6.1 với API chạy ví dụ đã cố định bằng Spring Boot 3.3.5. Khi nâng major version Spring, cần kiểm tra chữ ký và pipeline tương ứng trước khi sao chép advice vào sản phẩm.
