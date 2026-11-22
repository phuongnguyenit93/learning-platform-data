# Kiểm tra @RequestBody và @RequestPart sau giải tuần tự hóa trong Spring MVC

## 1. Bài toán: dữ liệu HTTP thành object rồi mới được kiểm tra

Một API Spring MVC có thể nhận JSON trực tiếp bằng `@RequestBody` hoặc nhận một **phần JSON bên trong multipart request** bằng `@RequestPart`. Hai cách nhận input có cấu trúc HTTP khác nhau nhưng có cùng một nguyên tắc rất quan trọng:

> **Spring phải đọc dữ liệu, chọn bộ chuyển đổi và giải tuần tự hóa thành object Java trước khi Bean Validation có thể kiểm tra các ràng buộc trên object đó.**

Ví dụ một endpoint tạo đơn:

```java
@PostMapping("/orders")
public void create(@Valid @RequestBody OrderRequest request) {
    // Chỉ được gọi sau khi JSON đã parse và validation hoàn tất.
}
```

Và một endpoint tải tài liệu cùng metadata:

```java
@PostMapping("/documents")
public void upload(
        @Valid @RequestPart("metadata") DocumentMetadata metadata,
        @RequestPart("attachment") MultipartFile attachment) {
    // Metadata JSON đã được chuyển thành Java object và kiểm tra.
}
```

Hai đoạn trên là **phương thức minh họa trong controller**, chưa phải chương trình hoàn chỉnh. Nội dung học tập ở đây là thời điểm kiểm tra và đường xử lý lỗi, không phải chỉ ghi nhớ cú pháp annotation.

**Phạm vi:** Spring Framework 6.1–6.2, Spring Boot 3.x, Java 17+, Servlet Spring MVC với Jakarta Validation (package `jakarta.validation`). Các phản hồi/exception của Spring WebFlux khác với những gì bài này mô tả.

Kết quả cần phân biệt:

- JSON **sai cú pháp** → chưa tạo được object, Bean Validation chưa được chạy; thường là `HttpMessageNotReadableException` và HTTP 400.
- JSON **đúng cú pháp nhưng vi phạm constraint** → object đã được tạo, `@Valid`/`@Validated` chạy; thường là `MethodArgumentNotValidException` và HTTP 400.
- Multipart **thiếu phần bắt buộc** → resolver không có input để tạo argument; thường là `MissingServletRequestPartException` và HTTP 400.
- Một JSON part có **Content-Type không có converter phù hợp** → có thể là `HttpMediaTypeNotSupportedException` và HTTP 415.
- Multipart metadata được giải tuần tự hóa thành công nhưng **không đạt constraint** → `MethodArgumentNotValidException` và HTTP 400, tương tự `@RequestBody`.
- Controller có **constraint trực tiếp trên tham số phương thức** yêu cầu method validation (Spring MVC 6.1+) → validation có thể đi qua `HandlerMethodValidationException` thay vì đường kiểm tra từng argument riêng biệt.

## 2. Hai tuyến dữ liệu: @RequestBody và @RequestPart

### 2.1. JSON body thuần với @RequestBody

Request:

```http
POST /api/orders HTTP/1.1
Content-Type: application/json

{
  "customer": "Lan",
  "quantity": 2,
  "address": {
    "city": "Huế"
  }
}
```

Luồng:

```text
HTTP application/json
    |
    v
@RequestBody argument resolver
    |
    v
HttpMessageConverter (thường MappingJackson2HttpMessageConverter)
    |
    v
Object Java: OrderRequest(customer="Lan", quantity=2, ...)
    |
    v
@Valid / @Validated -> Jakarta Validation provider
    |
    +-- Có violation -> BindingResult/MethodArgumentNotValidException
    |
    +-- Không có violation -> controller được gọi
```

`@RequestBody` nói với Spring: **đọc nội dung HTTP request body và chuyển thành kiểu argument**. Không nên dùng `@RequestBody` cho HTML form thông thường nếu muốn tận dụng data binding của `@ModelAttribute`, vì quá trình đọc form parameters của Servlet API có thể khiến body không còn sẵn cho converter đọc lại.

### 2.2. Multipart với @RequestPart

Khi upload file có metadata, HTTP request không còn là một JSON object duy nhất; nó là nhiều phần với tên và media type riêng:

```http
POST /api/documents HTTP/1.1
Content-Type: multipart/form-data; boundary=BOUNDARY

--BOUNDARY
Content-Disposition: form-data; name="metadata"
Content-Type: application/json

{"title":"Biên bản","revision":1}
--BOUNDARY
Content-Disposition: form-data; name="attachment"; filename="note.txt"
Content-Type: text/plain

Xin chào
--BOUNDARY--
```

Luồng:

```text
HTTP multipart/form-data
    |
    v
MultipartResolver / servlet multipart parsing
    |
    +-- Part "metadata" (Content-Type: application/json)
    |        |
    |        v
    |   @RequestPart("metadata")
    |        |
    |        v
    |   HttpMessageConverter -> DocumentMetadata
    |        |
    |        v
    |   @Valid -> Jakarta Validation
    |
    +-- Part "attachment" (file bytes)
             |
             v
       @RequestPart("attachment") MultipartFile
             |
             v
       File metadata/stream; chưa tự được kiểm tra nội dung
```

**Điểm quan trọng:** `@RequestPart` có thể dùng `HttpMessageConverter` để đọc từng part như một message body nhỏ. Vì vậy với JSON metadata, cả `@RequestBody` và `@RequestPart` đều có bước deserialize rồi validate. Ngược lại `MultipartFile` là abstraction tải lên file; `@Valid` trên metadata **không kiểm tra** tên file, định dạng thực, dung lượng hay nội dung độc hại của attachment.

### 2.3. @RequestParam, @RequestPart và @RequestBody không hoán đổi tùy ý

| Nhu cầu | Chọn | Vì sao |
| --- | --- | --- |
| Nhận một JSON object làm toàn bộ body | `@RequestBody OrderRequest` | Converter đọc body của request |
| Nhận metadata JSON trong multipart | `@RequestPart("metadata") DocumentMetadata` | Converter đọc **phần** JSON và tạo DTO |
| Nhận giá trị form text đơn giản trong multipart | `@RequestParam String title` | Parameter conversion là đủ, không cần JSON converter |
| Nhận file trong multipart | `@RequestPart MultipartFile` hoặc `@RequestParam MultipartFile` | Spring có hỗ trợ chuyên biệt cho file |
| Nhận form có nhiều property thường | `@ModelAttribute` | DataBinder/constructor/property binding của form |
| Nhận toàn multipart request bằng `@RequestBody` | Thường **không** chọn | Multipart đã có cấu trúc parts và resolver riêng |

Nếu client gửi metadata là một **chuỗi text không có JSON media type**, `@RequestPart DocumentMetadata` sẽ không tự hiểu đó là JSON trong mọi cấu hình. Hãy gửi Content-Type `application/json` cho metadata part, không dựa vào việc file có nội dung giống JSON.

## 3. Hai giai đoạn tách biệt: conversion và validation

### 3.1. Bước chuyển đổi dữ liệu

Spring chọn một `HttpMessageConverter` thích hợp dựa vào **kiểu Java cần tạo** và **Content-Type**. Với dự án Spring Boot Web có Jackson, JSON thường được đọc bằng `MappingJackson2HttpMessageConverter`.

Ví dụ DTO:

```java
public record OrderRequest(String customer, Integer quantity) {}
```

Request:

```json
{
  "customer": "Lan",
  "quantity": 2
}
```

Jackson có thể tạo record `new OrderRequest("Lan", 2)`. Đây **mới là deserialization**; chưa suy ra business rule “quantity phải dương” đã được kiểm tra.

Nếu JSON sai cú pháp:

```text
{"customer":"Lan","quantity":
```

converter không có một `OrderRequest` hợp lệ để bàn giao. Đường xử lý thông thường là `HttpMessageNotReadableException`, không phải violation `@Positive`. Nếu JSON đúng cú pháp nhưng truyền kiểu không thể chuyển (ví dụ object thay vì số nguyên), converter cũng có thể thất bại trước bước Bean Validation; tình huống chi tiết tùy cấu hình Jackson và kiểu DTO.

### 3.2. Bước Bean Validation

Chỉ khi argument đã được tạo và handler argument resolver quyết định áp dụng validation, Spring mới dùng validator để kiểm tra annotation:

```java
public record OrderRequest(
        @NotBlank String customer,
        @NotNull @Positive Integer quantity
) {}
```

- `@NotBlank`: `customer` không được null, rỗng hoặc toàn khoảng trắng.
- `@NotNull`: `quantity` phải có giá trị khác null.
- `@Positive`: số phải dương; bản thân `@Positive` xem null là hợp lệ theo hợp đồng của nó, nên cần `@NotNull` để cấm thiếu field.
- `@Valid` đặt ở **tham số controller** yêu cầu Spring validate DTO; chỉ đặt constraint trên record mà bỏ `@Valid`/`@Validated` ở boundary thì không thể giả định Spring sẽ tự chạy tất cả constraint.
- Khi object hợp lệ, controller mới được gọi; khi không hợp lệ, thông thường bị chặn trước khi vào thân controller, trừ khi dùng `BindingResult` hoặc đường method validation có cách xử lý riêng.

### 3.3. Validation có thể cascade vào đối tượng lồng nhau

```java
public record Address(
        @NotBlank String city
) {}

public record OrderRequest(
        @NotBlank String customer,
        @NotNull @Positive Integer quantity,
        @NotNull @Valid Address address
) {}
```

`@NotNull` kiểm tra `address` có tồn tại, `@Valid` yêu cầu **cascade** vào `Address` để kiểm tra `city`. Nếu chỉ có `@NotNull Address address`, đối tượng `Address` có mặt nhưng `city` rỗng có thể không được kiểm tra.

Tương tự, không nên nghĩ `@Valid` tự cấm null: `@Valid` kích hoạt cascade khi có đối tượng để kiểm tra, còn ràng buộc null là nhiệm vụ của `@NotNull`.

## 4. Khi nào Spring MVC tự kiểm tra argument?

Spring MVC hỗ trợ Jakarta Validation thông qua `@Valid` hoặc Spring `@Validated`, nhưng cần hiểu điều kiện áp dụng.

### 4.1. @Valid @RequestBody

```java
@PostMapping("/orders")
public ResponseEntity<Void> create(
        @Valid @RequestBody OrderRequest request) {
    // ...
}
```

Với **command object thông thường** và không có cơ chế method validation khác ghi đè, Spring dùng argument validation sau khi deserialize. Nếu vi phạm, mặc định sẽ có `MethodArgumentNotValidException`; nếu có `BindingResult`/`Errors` ngay sau argument, controller có thể nhận kết quả và tự xử lý.

### 4.2. @Valid @RequestPart

```java
@PostMapping(
        path = "/documents",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public ResponseEntity<Void> upload(
        @Valid @RequestPart("metadata") DocumentMetadata metadata,
        @RequestPart("attachment") MultipartFile attachment) {
    // ...
}
```

Nếu metadata part có Content-Type JSON phù hợp, converter tạo `DocumentMetadata` và validator kiểm tra các constraint trên nó. Nếu metadata không hợp lệ, có thể phát sinh **cùng loại `MethodArgumentNotValidException`** như `@RequestBody` trong đường argument validation thông thường.

`@RequestPart("attachment")` mặc định yêu cầu part này phải có mặt; tuy nhiên “có mặt” khác với “file có nội dung không rỗng”, “file có type an toàn” hay “tên file hợp lệ”. Các điều kiện đó cần validation chuyên biệt ở tầng upload/service.

### 4.3. @Validated chọn validation group

`@Valid` của Jakarta không mang tham số groups. Khi DTO khai báo constraints thuộc Create/Update, có thể dùng Spring `@Validated`:

```java
public interface Create {}

public record OrderRequest(
        @NotBlank(groups = Create.class) String customer
) {}

@PostMapping("/orders")
public void create(
        @Validated(Create.class) @RequestBody OrderRequest request) {
    // ...
}
```

Đây là các snippet minh họa; type marker và endpoint phải được đặt đúng file/package. Việc chọn `Create` không tự chạy thêm nhóm `Default`, trừ khi có group inheritance/sequence phù hợp. Không dùng `@Validated` ở cấp **controller class** chỉ để thực hiện argument validation; từ Spring MVC 6.1, annotation type-level có thể kích hoạt một đường AOP method validation khác, không cần thiết cho ví dụ argument đơn giản.

### 4.4. Khi @Valid chưa đủ để kích hoạt method validation

Spring MVC 6.1+ phân biệt:

1. **Validation từng argument** cho `@ModelAttribute`, `@RequestBody`, `@RequestPart` là command object có `@Valid`/`@Validated`.
2. **Method validation** khi có constraint trực tiếp trên parameter hoặc return value, ví dụ `@Min`, `@NotBlank`, `@NotNull` đặt trên handler method parameter; cơ chế này kiểm tra cả nested constraints qua `@Valid` khi thích hợp.

Vì vậy, controller như sau có thể dùng **`HandlerMethodValidationException`** thay vì chỉ `MethodArgumentNotValidException` khi tham số trực tiếp `page` không hợp lệ:

```java
@GetMapping("/search")
public String search(@RequestParam @Min(1) int page) {
    return "page=" + page;
}
```

`@Valid` **không phải annotation constraint** và tự nó không buộc toàn bộ handler dùng method validation; còn `@Min` là constraint. Đừng suy từ một controller có `@Valid` rằng mọi lỗi validation đều là `HandlerMethodValidationException`; đường đi phụ thuộc **cấu trúc signature**.

## 5. Dự án thực hành Spring Boot 3.3, Java 17+

Ta triển khai hai endpoint có thể kiểm thử:

- `POST /api/orders`, `application/json`, `@Valid @RequestBody OrderRequest`.
- `POST /api/documents`, `multipart/form-data`, `@Valid @RequestPart("metadata") DocumentMetadata` cùng file `@RequestPart("attachment") MultipartFile`.

Mục tiêu: quan sát được request hợp lệ (201), JSON object/metadata vi phạm constraint (400), JSON malformed (400), multipart thiếu part (400), JSON part sai media type (415 trong cấu hình minh họa).

### 5.1. Cấu hình Gradle

Tệp `settings.gradle`:

```groovy
rootProject.name = 'request-validation-demo'
```

Tệp `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

tasks.named('test') {
    useJUnitPlatform()
}
```

- `spring-boot-starter-web` bao gồm Spring MVC và hỗ trợ Jackson JSON thông dụng.
- `spring-boot-starter-validation` đưa Jakarta Validation API và provider (thông thường Hibernate Validator) vào ứng dụng; chỉ có Jackson sẽ **không** tự kích hoạt các ràng buộc `@NotBlank`/`@Positive`.
- Trong Spring Boot Servlet Web thông thường, multipart support được tự cấu hình khi phù hợp. Nếu tự cấu hình `MultipartResolver` hoặc tắt multipart, hãy kiểm tra lại cơ chế nhận file.

Cấu trúc source:

```text
src/
  main/
    java/com/example/requestvalidation/
      RequestValidationApplication.java
      Address.java
      OrderRequest.java
      DocumentMetadata.java
      ApiController.java
      ApiValidationAdvice.java
  test/
    java/com/example/requestvalidation/
      ApiControllerTest.java
```

### 5.2. Điểm khởi động

Tệp `src/main/java/com/example/requestvalidation/RequestValidationApplication.java`:

```java
package com.example.requestvalidation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RequestValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(RequestValidationApplication.class, args);
    }
}
```

### 5.3. Các DTO và nested constraints

Tệp `src/main/java/com/example/requestvalidation/Address.java`:

```java
package com.example.requestvalidation;

import jakarta.validation.constraints.NotBlank;

public record Address(
        @NotBlank String city
) {}
```

Tệp `src/main/java/com/example/requestvalidation/OrderRequest.java`:

```java
package com.example.requestvalidation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

public record OrderRequest(
        @NotBlank String customer,
        @NotNull @Positive Integer quantity,
        @NotNull @Valid Address address
) {}
```

Tệp `src/main/java/com/example/requestvalidation/DocumentMetadata.java`:

```java
package com.example.requestvalidation;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;

public record DocumentMetadata(
        @NotBlank String title,
        @NotNull @Positive Integer revision
) {}
```

Ba record này đều dùng API Jakarta. DTO riêng cho HTTP giúp tránh deserialize/bind trực tiếp vào JPA entity hoặc object có các trường nội bộ như `ownerId`, `approved`, `admin`.

Đối với record, Jakarta provider đọc constraint trên record component/field/accessor theo metadata hỗ trợ. Record không cần public setter. Hãy dùng đúng các annotation ở những vị trí được spec hỗ trợ và kiểm thử với provider trong dự án.

### 5.4. Controller nhận hai kiểu request

Tệp `src/main/java/com/example/requestvalidation/ApiController.java`:

```java
package com.example.requestvalidation;

import jakarta.validation.Valid;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Objects;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestPart;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
@RequestMapping("/api")
public class ApiController {

    @PostMapping(
        path = "/orders",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<Map<String, Object>> createOrder(
            @Valid @RequestBody OrderRequest request) {

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("customer", request.customer());
        body.put("quantity", request.quantity());
        body.put("city", request.address().city());

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(body);
    }

    @PostMapping(
        path = "/documents",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
    )
    public ResponseEntity<Map<String, Object>> upload(
            @Valid @RequestPart("metadata") DocumentMetadata metadata,
            @RequestPart("attachment") MultipartFile attachment) {

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("title", metadata.title());
        body.put("revision", metadata.revision());
        body.put(
                "filename",
                Objects.toString(attachment.getOriginalFilename(), "")
        );

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(body);
    }
}
```

Đây là **demo**, chưa có lưu order/file. Đặc biệt đừng lấy giá trị `attachment.getOriginalFilename()` để ghép trực tiếp thành đường dẫn ghi file trong production. Tên file là metadata do client cung cấp, không đáng tin. Endpoint này chỉ cho thấy phần JSON được convert + validate; bước kiểm tra file size, magic bytes, malware, quyền upload và lưu trữ thuộc một quy trình riêng.

Không có `@Validated` trên class, không có constraint trực tiếp trên method parameter khác. Nhờ đó ví dụ tập trung vào **argument validation** và `MethodArgumentNotValidException` thay vì ép controller qua AOP/built-in method validation.

### 5.5. Xử lý lỗi phân biệt parse với validation

Tệp `src/main/java/com/example/requestvalidation/ApiValidationAdvice.java`:

```java
package com.example.requestvalidation;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiValidationAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> validationFailed(
            MethodArgumentNotValidException exception) {

        List<Map<String, String>> fields =
                exception.getBindingResult()
                        .getFieldErrors()
                        .stream()
                        .map(this::toFieldError)
                        .toList();

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("code", "VALIDATION_ERROR");
        body.put("errors", fields);

        return ResponseEntity.badRequest().body(body);
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<Map<String, String>> unreadable(
            HttpMessageNotReadableException exception) {

        // Không trả thẳng exception.getMessage() cho client:
        // có thể làm lộ cấu trúc Java/JSON hoặc dữ liệu nội bộ.
        Map<String, String> body = Map.of(
                "code", "INVALID_PAYLOAD",
                "message", "Request body hoặc JSON part không đọc được"
        );
        return ResponseEntity.badRequest().body(body);
    }

    private Map<String, String> toFieldError(FieldError error) {
        return Map.of(
                "field", error.getField(),
                "message", Objects.toString(
                        error.getDefaultMessage(), "Giá trị không hợp lệ"
                )
        );
    }
}
```

Phân biệt hai handler:

- `MethodArgumentNotValidException`: object đã được tạo và Bean Validation trả field violations. Ví dụ `customer=" "`, `quantity=0` hoặc metadata `revision=0`.
- `HttpMessageNotReadableException`: converter không deserialize được input, ví dụ JSON bị cắt giữa chừng hoặc sai hình dạng kiểu dữ liệu. Không nên dựng một `FieldError` giả rồi gọi nó là `@Positive` nếu bước parse chưa thành công.
- Multipart thiếu part và media type không phù hợp đang để cho **default exception handling của Spring MVC** phản hồi trong demo, vì chúng là lỗi của resolver/converter, không phải `ConstraintViolation`. Production có thể bổ sung handler riêng cho `MissingServletRequestPartException` và `HttpMediaTypeNotSupportedException`.

Advice này chỉ trả các `FieldError`. Custom **class-level constraint** có thể tạo `ObjectError` (global error), cần xét `getGlobalErrors()` khi xây dựng contract lỗi hoàn chỉnh. Nếu controller có direct method constraints, còn phải xử lý `HandlerMethodValidationException`. Việc dùng handler chung không thay thế việc hiểu đúng nguyên nhân lỗi.

## 6. Chạy HTTP request và kết quả dự kiến

Khởi động ứng dụng sau khi tạo Gradle wrapper:

```bash
./gradlew bootRun
```

Trên Windows có thể dùng `gradlew.bat bootRun`. Với cấu hình mặc định, server nghe `http://localhost:8080`.

### 6.1. JSON body hợp lệ

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"customer":"Lan","quantity":2,"address":{"city":"Hue"}}'
```

HTTP dự kiến: `201 Created`. Body minh họa:

```json
{
  "customer": "Lan",
  "quantity": 2,
  "city": "Hue"
}
```

Bước đã thực hiện: converter đọc JSON → tạo `OrderRequest` và `Address` → `@Valid` kiểm tra constraints → controller chạy.

### 6.2. JSON đúng cú pháp nhưng vi phạm constraint

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"customer":" ","quantity":0,"address":{"city":""}}'
```

HTTP dự kiến: `400 Bad Request`, mã lỗi `VALIDATION_ERROR`:

```json
{
  "code": "VALIDATION_ERROR",
  "errors": [
    {"field": "customer", "message": "must not be blank"},
    {"field": "quantity", "message": "must be greater than 0"},
    {"field": "address.city", "message": "must not be blank"}
  ]
}
```

**Lưu ý:** thông báo cụ thể trong `message` phụ thuộc provider, locale và bundle; thứ tự phần tử của `errors` cũng không nên coi là hợp đồng. Body JSON trên minh họa **ba đường dẫn lỗi**; test ổn định nên tìm field cần thiết hoặc assert mã lỗi, không assert toàn bộ thứ tự/chuỗi tiếng Anh.

### 6.3. JSON không parse được

```bash
curl -i -X POST http://localhost:8080/api/orders \
  -H "Content-Type: application/json" \
  -d '{"customer":"Lan","quantity":'
```

HTTP dự kiến: `400 Bad Request` với body:

```json
{
  "code": "INVALID_PAYLOAD",
  "message": "Request body hoặc JSON part không đọc được"
}
```

Lúc này **không có** DTO hợp lệ để chạy `@NotBlank`/`@Positive`. Nếu controller log `validation failed` cho tình huống này, cần xem lại đường exception.

### 6.4. Multipart có metadata JSON và file

```bash
curl -i -X POST http://localhost:8080/api/documents \
  -F 'metadata={"title":"Bien ban","revision":1};type=application/json' \
  -F 'attachment=@note.txt;type=text/plain'
```

Lệnh trên giả sử `note.txt` tồn tại trong thư mục chạy. Khi metadata hợp lệ, HTTP dự kiến `201 Created`:

```json
{
  "title": "Bien ban",
  "revision": 1,
  "filename": "note.txt"
}
```

Phần `type=application/json` ở trường metadata **quan trọng**: nó đặt media type của **part**, chứ không phải ép toàn bộ request thành application/json. Toàn bộ request vẫn là `multipart/form-data`.

### 6.5. Metadata JSON không hợp lệ

```bash
curl -i -X POST http://localhost:8080/api/documents \
  -F 'metadata={"title":"","revision":0};type=application/json' \
  -F 'attachment=@note.txt;type=text/plain'
```

Kết quả dự kiến: `400 Bad Request` với `code = VALIDATION_ERROR`, các field vi phạm là `title` và `revision`. File có được gửi hay không không làm hai ràng buộc trong `DocumentMetadata` tự thay đổi.

### 6.6. Metadata part sai Content-Type

Ví dụ thử gửi JSON bytes như text:

```bash
curl -i -X POST http://localhost:8080/api/documents \
  -F 'metadata={"title":"Bien ban","revision":1};type=text/plain' \
  -F 'attachment=@note.txt;type=text/plain'
```

Với converter mặc định và target là `DocumentMetadata`, thường không có converter đọc `text/plain` thành kiểu đó: kết quả **415 Unsupported Media Type**. Đây không phải một `@NotBlank` violation. Chọn converter xảy ra **trước** validation.

### 6.7. Thiếu part

Nếu multipart chỉ có attachment mà thiếu part tên `metadata`, `@RequestPart("metadata")` mặc định có `required=true`; Spring thường báo `MissingServletRequestPartException` → HTTP 400. Khác với metadata JSON hợp lệ có `title=""`: một tình huống là **không có argument**, tình huống còn lại là **argument có nhưng vi phạm constraint**.

## 7. Kiểm thử Spring MVC qua MockMvc

Tệp `src/test/java/com/example/requestvalidation/ApiControllerTest.java`:

```java
package com.example.requestvalidation;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.mock.web.MockMultipartFile;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.multipart;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class ApiControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void validJsonBodyPassesDeserializationAndValidation()
            throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "customer": "Lan",
                          "quantity": 2,
                          "address": {"city": "Hue"}
                        }
                        """))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.customer").value("Lan"))
            .andExpect(jsonPath("$.quantity").value(2))
            .andExpect(jsonPath("$.city").value("Hue"));
    }

    @Test
    void invalidObjectFailsValidationAfterJsonIsRead()
            throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "customer": " ",
                          "quantity": 0,
                          "address": {"city": ""}
                        }
                        """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.errors").isArray());
    }

    @Test
    void malformedJsonIsNotBeanValidationFailure()
            throws Exception {
        mvc.perform(post("/api/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"customer\":\"Lan\",\"quantity\":"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("INVALID_PAYLOAD"));
    }

    @Test
    void validMultipartJsonPartIsValidated() throws Exception {
        MockMultipartFile metadata = jsonPart(
                "{\"title\":\"Bien ban\",\"revision\":1}"
        );
        MockMultipartFile attachment = filePart();

        mvc.perform(multipart("/api/documents")
                .file(metadata)
                .file(attachment))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.title").value("Bien ban"))
            .andExpect(jsonPath("$.revision").value(1))
            .andExpect(jsonPath("$.filename").value("note.txt"));
    }

    @Test
    void invalidMultipartMetadataFailsBeanValidation()
            throws Exception {
        MockMultipartFile metadata = jsonPart(
                "{\"title\":\"\",\"revision\":0}"
        );

        mvc.perform(multipart("/api/documents")
                .file(metadata)
                .file(filePart()))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                    .value("VALIDATION_ERROR"));
    }

    @Test
    void missingMetadataPartIsMissingArgumentNotConstraintError()
            throws Exception {
        mvc.perform(multipart("/api/documents")
                .file(filePart()))
            .andExpect(status().isBadRequest());
    }

    @Test
    void wrongContentTypeForJsonPartIsUnsupported()
            throws Exception {
        MockMultipartFile metadata = new MockMultipartFile(
                "metadata",
                "",
                MediaType.TEXT_PLAIN_VALUE,
                "{\"title\":\"Bien ban\",\"revision\":1}"
                        .getBytes(StandardCharsets.UTF_8)
        );

        mvc.perform(multipart("/api/documents")
                .file(metadata)
                .file(filePart()))
            .andExpect(status().isUnsupportedMediaType());
    }

    private static MockMultipartFile jsonPart(String json) {
        return new MockMultipartFile(
                "metadata",
                "",
                MediaType.APPLICATION_JSON_VALUE,
                json.getBytes(StandardCharsets.UTF_8)
        );
    }

    private static MockMultipartFile filePart() {
        return new MockMultipartFile(
                "attachment",
                "note.txt",
                MediaType.TEXT_PLAIN_VALUE,
                "Xin chao".getBytes(StandardCharsets.UTF_8)
        );
    }
}
```

Chạy:

```bash
./gradlew test
```

**Kỳ vọng:** bảy test PASS trong cấu hình đã mô tả. Chúng kiểm tra **HTTP pipeline** chứ không chỉ gọi `validator.validate(...)` thủ công:

- Request body JSON hợp lệ.
- Constraint vi phạm sau khi JSON đọc thành công.
- JSON malformed khác Bean Validation.
- Multipart JSON metadata hợp lệ.
- Multipart metadata vi phạm constraint.
- Thiếu metadata part.
- Metadata part không có media type converter phù hợp.

`MockMultipartFile` là công cụ của Spring Test: tạo named part gồm content type và byte content; nó không phải file tải từ đĩa và không cần `note.txt` thật. Trong `curl`, ngược lại, `@note.txt` đòi hỏi file local tồn tại. Nhờ vậy test không phụ thuộc filesystem.

Đừng assert thứ tự `FieldError` nếu input cùng lúc vi phạm nhiều constraints. Hãy kiểm tra danh sách field theo tên hoặc dùng predicate để test chặt hơn. Với bài này, test phân tách **loại lỗi** bằng mã `VALIDATION_ERROR` so với `INVALID_PAYLOAD`, còn test multipart media type xác nhận HTTP 415.

## 8. Bắt lỗi tại controller bằng BindingResult

Không phải mọi violation của `@Valid` đều buộc phát sinh exception. Với `@RequestBody` và `@RequestPart` trong đường argument validation, có thể khai báo `Errors` hoặc `BindingResult` **ngay sau argument đang được kiểm tra**:

```java
@PostMapping("/manual")
public ResponseEntity<String> manual(
        @Valid @RequestBody OrderRequest request,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest()
                .body("Dữ liệu không hợp lệ");
    }
    return ResponseEntity.ok("Hợp lệ");
}
```

Tương tự cho JSON part:

```java
@PostMapping(
        path = "/manual-upload",
        consumes = MediaType.MULTIPART_FORM_DATA_VALUE
)
public ResponseEntity<String> manualUpload(
        @Valid @RequestPart("metadata") DocumentMetadata metadata,
        BindingResult errors,
        @RequestPart("attachment") MultipartFile attachment) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest()
                .body("Metadata không hợp lệ");
    }
    return ResponseEntity.ok("Hợp lệ");
}
```

Đây là **các method minh họa**, không nằm trong source runnable ở mục 5. `BindingResult` phải đứng sát ngay sau `OrderRequest` hoặc `DocumentMetadata` tương ứng. Nếu đặt một `@RequestParam` hoặc file parameter chen vào giữa, Spring có thể không liên kết `BindingResult` với argument đúng.

**Giới hạn:** `BindingResult` chủ yếu cho phép kiểm tra **binding/validation errors** khi converter đã tạo được argument. Nó không bảo đảm sẽ nhận được controller method nếu JSON sai cú pháp, thiếu part bắt buộc hoặc không có converter đọc media type. Những lỗi đó xảy ra sớm hơn.

Trong Spring MVC 6.1+ method validation, nếu có direct constraints trên những tham số khác, Spring chỉ gọi controller nếu mọi lỗi validation nằm trên các tham số có `Errors` liền kề; nếu có lỗi không được xử lý theo cách đó, `HandlerMethodValidationException` có thể xảy ra. Do đó khi mở rộng controller signature, nên chạy lại tests về exception route.

## 9. Nhìn sâu vào các loại exception

| Tình huống | Giai đoạn | Exception thường gặp | HTTP thường gặp |
| --- | --- | --- | --- |
| JSON hợp lệ, `@NotBlank` thất bại | Argument Bean Validation | `MethodArgumentNotValidException` | 400 |
| JSON sai cú pháp | JSON deserialize | `HttpMessageNotReadableException` | 400 |
| JSON có kiểu không phù hợp và Jackson không chuyển được | JSON deserialize | `HttpMessageNotReadableException` | 400 |
| Multipart JSON metadata vi phạm `@Positive` | Argument Bean Validation | `MethodArgumentNotValidException` | 400 |
| Multipart thiếu `metadata` hoặc `attachment` cần thiết | Part resolution | `MissingServletRequestPartException` | 400 |
| Metadata part `text/plain` nhưng target chỉ có JSON converter | Message conversion | `HttpMediaTypeNotSupportedException` | 415 |
| HTTP body có Content-Type không khớp `consumes` | Handler mapping/content negotiation | `HttpMediaTypeNotSupportedException` hoặc lỗi tương ứng | 415 |
| Dữ liệu vào vượt hạn mức multipart | Multipart parsing/config | `MaxUploadSizeExceededException` hoặc `MultipartException` | Tùy cấu hình, thường 413 cho quá hạn mức |
| Controller có direct method constraints | MVC built-in method validation | `HandlerMethodValidationException` | 400 cho input không hợp lệ |
| Validator được gọi thủ công bằng `Validator#validate` | Jakarta API | Trả `Set<ConstraintViolation<?>>` | Không tự sinh HTTP response |

Bảng mô tả đường thường gặp trong **Servlet Spring MVC**, không phải cam kết mọi phiên bản/cấu hình tạo cùng exception. Ví dụ một converter khác, custom resolver hay global exception handler có thể thay đổi kết quả. Trong Spring WebFlux, lỗi argument validation thường thuộc hệ loại khác, như `WebExchangeBindException`.

Cũng không nên đồng nhất `@RequestPart` với `@RequestParam` khi nhận JSON: nếu dùng `@RequestParam String metadata` rồi tự gọi Jackson, Spring không tự áp `@Valid` của parameter kiểu String lên object `DocumentMetadata` bạn mới tạo bên trong controller. Bạn phải gọi validator thủ công nếu chọn tự deserialize theo cách này.

## 10. Validation groups và những input có cấu trúc phức tạp

### 10.1. Chọn nhóm thay vì chỉ @Valid

`@Valid` thông thường validate theo group `Default`. Nếu cần kiểm tra các rule riêng theo thao tác Create:

```java
public interface Create {}

public record DocumentMetadata(
        @NotBlank(groups = Create.class) String title,
        @Positive(groups = Create.class) Integer revision
) {}

@PostMapping("/documents")
public void upload(
        @Validated(Create.class)
        @RequestPart("metadata") DocumentMetadata metadata) {
    // ...
}
```

Đây là đoạn **minh họa**, không thuộc dự án runnable phía trên; cần import `org.springframework.validation.annotation.Validated` và các annotation liên quan. Chọn `Create` không mặc nhiên cộng `Default`. Nếu muốn `revision` không được null, cần `@NotNull(groups = Create.class)`.

Chọn groups trên **parameter** giúp thể hiện ý nghĩa endpoint. Không cần đặt `@Validated` lên controller class vì nó có thể chuyển controller sang AOP method validation trên Spring MVC 6.1+, làm đường exception khác với built-in method validation.

### 10.2. Validate object lồng nhau và collection

`@Valid` đặt trên một nested field hoặc collection element giúp cascade constraints:

```java
public record Shipment(
        @NotBlank String reference,
        @NotEmpty
        java.util.List<@Valid PackageItem> items
) {}

public record PackageItem(
        @NotBlank String sku,
        @Positive int quantity
) {}
```

Đoạn này là ví dụ cấu trúc DTO, cần import `jakarta.validation.constraints.NotEmpty` và các annotation tương ứng. Khi controller nhận `@Valid @RequestBody Shipment`, provider có thể đi vào từng `PackageItem` và kiểm tra `sku`/`quantity`.

**Chú ý về top-level collection:** Spring MVC argument validation cho `@RequestBody`/`@RequestPart` tập trung vào **command object**, không tự đồng nhất `@Valid List<Dto>` hay `Map<...>` ở top-level với một wrapper DTO trong mọi đường kiểm tra. Nếu nhận JSON array, cân nhắc dùng wrapper record như `Shipment` hoặc kiểm tra method validation và test rõ ràng; không kết luận rằng `@Valid` trên top-level collection lúc nào cũng chạy giống bean object.

### 10.3. File upload cần quy tắc riêng

Một endpoint multipart production tối thiểu cần kiểm tra:

- `MultipartFile#isEmpty()` và `getSize()` theo hạn mức nghiệp vụ; ngoài ra cấu hình giới hạn upload ở web server/framework.
- Phần mở rộng file **không** chứng minh content type thực. `getContentType()` là giá trị được cung cấp bởi client.
- Không dùng `getOriginalFilename()` làm đường dẫn storage nếu chưa chuẩn hóa và xác minh; phòng traversal/overwrite.
- Scan nội dung nguy hiểm nếu yêu cầu hệ thống.
- Xác thực và phân quyền trước khi ghi file, đặt storage name độc lập với tên client.
- Chỉ lưu metadata sau khi các điều kiện cần thiết được đảm bảo; quản lý transaction/compensation khi kết hợp file storage với database.

`@Valid @RequestPart("metadata")` chỉ bảo đảm **những constraint bạn đặt trên metadata** đã được kiểm tra. File không tự an toàn vì request đi qua cùng một controller.

## 11. Bảo mật, khả năng chịu lỗi và tính ổn định của contract

### 11.1. Đừng trả thông báo parser thô cho client

`HttpMessageNotReadableException#getMessage()` có thể chứa thông tin kỹ thuật về class, field hoặc nội dung dữ liệu. Trả thẳng thông báo này sẽ khiến API lệ thuộc Jackson/Spring version và có thể lộ chi tiết nội bộ. Handler trong demo trả mã `INVALID_PAYLOAD` với thông báo chung, trong khi server có thể ghi log theo chính sách phù hợp (không log mật khẩu/token/raw upload).

### 11.2. Đừng dùng message dịch làm error code duy nhất

Bean Validation message phụ thuộc locale, bundle và provider. Client không nên phải parse chuỗi `"must not be blank"` để biết trường nào sai. Cách ổn định hơn là trả:

```json
{
  "code": "VALIDATION_ERROR",
  "errors": [
    {
      "field": "quantity",
      "message": "must be greater than 0"
    }
  ]
}
```

Trong API lớn, có thể bổ sung `fieldErrorCode` như `POSITIVE_REQUIRED`, request correlation ID, và mapping sang cấu trúc Problem Details (`ProblemDetail`/RFC 9457) theo chính sách tổ chức. Đừng để client dựa vào thứ tự phần tử `errors`.

### 11.3. Không bind trực tiếp input vào entity nhạy cảm

Dù `@RequestBody` dùng Jackson và `@RequestPart` dùng converter cho metadata, object nhận dữ liệu vẫn phải là **DTO đầu vào có tập trường được cho phép**. Không nhận trực tiếp entity có `admin`, `role`, `ownerId` rồi chỉ dựa vào `@Valid`; validation không thay authorization/mass-assignment policy.

### 11.4. Kiểm soát resource

Body lớn, JSON lồng sâu, số lượng multipart parts nhiều hoặc file quá dung lượng có thể gây tiêu hao CPU/RAM/disk trước khi controller được gọi. Giới hạn request size, max upload size, số part và cấu hình Jackson/parser tương thích với rủi ro triển khai. Validation của DTO xảy ra sau deserialization nên không phải tuyến phòng thủ đầu tiên chống payload quá lớn.

### 11.5. Cẩn trọng với Optional/required=false

`@RequestBody(required = false)` hoặc `@RequestPart(required = false)` có thể cho phép argument null khi input vắng mặt. Chỉ gắn `@Valid` không tự tạo ràng buộc non-null cho null argument. Nếu API bắt buộc có dữ liệu, thường nên giữ `required=true` mặc định và dùng `@NotNull` cho **những field bên trong DTO**. Không gộp tình huống “thiếu body” với “field thiếu trong body”.

## 12. Kiểm tra các lỗi phổ biến

**Lỗi 1 — Nghĩ @Valid parse được JSON.** `@Valid` chỉ gọi validator. Jackson/HttpMessageConverter phải tạo được object trước; JSON malformed không thể sửa bằng annotation validation.

**Lỗi 2 — Gửi JSON part nhưng để Content-Type text/plain.** Với `@RequestPart DocumentMetadata`, converter cần media type phù hợp; thiếu Content-Type JSON có thể gây HTTP 415.

**Lỗi 3 — Gắn @Valid lên MultipartFile rồi nghĩ file an toàn.** File content, name, size và type cần kiểm tra/thực thi policy riêng.

**Lỗi 4 — Gộp HttpMessageNotReadableException với MethodArgumentNotValidException.** Một lỗi thuộc deserialization, một lỗi thuộc Bean Validation. Dùng error code khác nhau.

**Lỗi 5 — Quên @Valid ở tham số controller hoặc nested object.** Constraint trên DTO không phải lúc nào cũng tự chạy; với nested object cần cascade đúng chỗ.

**Lỗi 6 — Quên @NotNull khi dùng @Positive/@Min.** Một số constraint cho phép null theo spec; thiếu field có thể bị bỏ qua nếu không có ràng buộc khác.

**Lỗi 7 — Đặt BindingResult sai vị trí.** `BindingResult` phải ngay sau argument liên quan. Nếu input không deserialize được, controller vẫn có thể không chạy để đọc result.

**Lỗi 8 — Dùng @RequestParam String metadata rồi mong validation metadata.** Nếu metadata vẫn là String, Bean Validation chưa thấy các field trong DTO. Dùng `@RequestPart` với converter hoặc tự deserialize/validate có chủ đích.

**Lỗi 9 — Nhầm method validation với argument validation.** Thêm `@Min` trực tiếp lên một handler parameter có thể chuyển sang `HandlerMethodValidationException` (Spring MVC 6.1+). Cần test exception path thực tế.

**Lỗi 10 — Cấu hình @Validated cấp lớp controller như service AOP.** Spring MVC 6.1+ có built-in method validation; type-level `@Validated` có thể khiến đường AOP được dùng. Tránh phối trộn ngoài ý muốn.

**Lỗi 11 — Khẳng định validate luôn xảy ra sau mọi middleware.** Authentication, request filtering, multipart parsing, content negotiation và message conversion có thể từ chối request trước khi DTO tồn tại. Cần quan sát pipeline đúng giai đoạn.

**Lỗi 12 — Không kiểm thử input lỗi theo từng lớp.** Một test “status 400” không phân biệt parse error, missing part, constraint violation. Hãy kiểm tra cả error code và loại request.

**Lỗi 13 — Dùng DTO/Entity chứa field nhạy cảm.** Bean Validation không ngăn client đưa giá trị trái phép vào field có thể deserialize. Kiểm soát DTO, authorization và mapping DTO → domain.

**Lỗi 14 — Tin vào Content-Type của upload.** Đây là metadata từ client; đừng dùng nó làm bằng chứng duy nhất file an toàn.

## 13. Checklist để triển khai endpoint đúng

1. Xác định media type toàn request: `application/json` hay `multipart/form-data`.
2. Với JSON trực tiếp, dùng `@RequestBody`; với JSON metadata trong multipart, dùng `@RequestPart("metadata")` và gửi Content-Type JSON cho part.
3. Dùng DTO riêng, không deserialize trực tiếp domain/JPA entity có trường nhạy cảm.
4. Đặt constraint `@NotBlank`, `@NotNull`, `@Positive` và `@Valid` cho nested object.
5. Gắn `@Valid` hoặc `@Validated(Group.class)` tại argument cần được kiểm tra.
6. Không áp dụng annotation `@Validated` cấp controller class theo thói quen nếu không có chủ đích về AOP.
7. Nếu muốn xử lý violation tại controller, đặt `BindingResult`/`Errors` **ngay sau** argument đó.
8. Xử lý tách biệt `MethodArgumentNotValidException`, `HttpMessageNotReadableException` và các lỗi multipart resolver; xem xét `HandlerMethodValidationException` khi có direct method constraints.
9. Cho lỗi xác thực input một error code ổn định, tên field rõ ràng; tránh rò rỉ parser exception thô.
10. Kiểm tra độc lập file size, extension, MIME thực, nội dung, original filename, quyền truy cập và storage.
11. Dùng `MockMvc` test ít nhất JSON hợp lệ, JSON lỗi rule, JSON malformed, multipart hợp lệ, metadata lỗi rule, thiếu part và media type sai.
12. Rà soát dependency tương thích Jakarta Validation/Spring Boot, cấu hình MultipartResolver và converter thực tế khi deploy.

**Kết luận:** `@RequestBody` đọc **toàn request body**, còn `@RequestPart` đọc **từng part** của multipart; cả hai có thể dùng `HttpMessageConverter` để tạo object Java, sau đó `@Valid`/`@Validated` kích hoạt Jakarta Bean Validation. Hãy phân biệt **deserialize/convert error** với **constraint violation**, và coi kiểm tra file upload là một lớp trách nhiệm riêng. Như vậy API sẽ có phản hồi nhất quán, kiểm thử rõ ràng và giảm những giả định sai về lúc validation thực sự chạy.

## Tài liệu tham khảo

- [Spring Framework 6.2 — @RequestBody](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html): converter, Bean Validation và `BindingResult`.
- [Spring Framework 6.2 — Multipart](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/multipart-forms.html): metadata JSON với `@RequestPart`, `MultipartFile`, validation.
- [Spring Framework 6.2 — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): argument validation vs method validation, hai loại exception.
- [Spring Framework 6.2 — Message Converters](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/message-converters.html): giải tuần tự hóa request theo media type.
- [Jakarta Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): `@Valid`, constraints, cascading và groups.
