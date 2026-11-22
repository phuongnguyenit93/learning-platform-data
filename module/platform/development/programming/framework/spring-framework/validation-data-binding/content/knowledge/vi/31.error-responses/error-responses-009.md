# Không phụ thuộc thứ tự duyệt của Set<ConstraintViolation> khi tạo phản hồi lỗi

## 1. Bản chất của vấn đề

Trong Jakarta Validation, khi kiểm tra một đối tượng:

```java
Set<ConstraintViolation<OrderInput>> violations =
        validator.validate(input);
```

kết quả là **`Set<ConstraintViolation<T>>`**, không phải `List`. `Set` biểu diễn **tập** vi phạm được tìm thấy; API không hứa rằng phần tử đầu là field được khai báo đầu tiên, constraint quan trọng nhất, hay field đứng đầu form.

Đặt trong chủ đề **phản hồi lỗi** của Spring Framework, điều này quan trọng vì JSON error thường là một array có thứ tự. Ví dụ request:

```json
{
  "sku": " ",
  "quantity": 0,
  "customerEmail": "not-an-email"
}
```

Có thể tạo ba lỗi từ `@NotBlank`, `@Min(1)` và `@Email`. Nếu ứng dụng lặp trực tiếp qua `Set` để tạo response, thứ tự JSON có thể trở thành chi tiết phụ thuộc provider/runtime:

```json
{
  "code": "VALIDATION_ERROR",
  "errors": [
    {"field": "sku", "code": "NotBlank"},
    {"field": "customerEmail", "code": "Email"},
    {"field": "quantity", "code": "Min"}
  ]
}
```

Một lần chạy khác có thể cho array với cùng ba lỗi nhưng đổi vị trí. Không nhất thiết thứ tự **thực tế** sẽ thay đổi qua mỗi request: provider có thể tình cờ giữ nguyên nhiều lần. Song sự ổn định quan sát được **không phải bảo đảm theo hợp đồng**.

Hệ quả:

- Snapshot test JSON có nguy cơ flaky khi nâng provider/JDK hoặc thay metadata.
- Frontend hiển thị lỗi không nhất quán.
- Việc chọn “lỗi đầu tiên” có thể chọn lỗi không đúng ưu tiên UX.
- Hệ thống so sánh payload, caching, hashing hoặc logging có thể xem hai array cùng ý nghĩa là khác nhau.
- Client vô tình phụ thuộc vào chi tiết implementation của Hibernate Validator.

**Nguyên tắc trọng tâm:** xem `Set<ConstraintViolation>` là dữ liệu **không có thứ tự presentation**, chuẩn hóa thành DTO lỗi, **sort bằng comparator tường minh**, rồi serialize một `List`.

**Phạm vi:** Jakarta Validation 3.x, Java 17+, Spring Framework 6.1–6.2, Spring Boot 3.x và Spring MVC. Ví dụ dùng Spring Boot 3.3.6 với `spring-boot-starter-validation`. Ngoài `ConstraintViolation` thuần Jakarta, bài còn chỉ ra nơi Spring MVC tạo `BindingResult`/`FieldError` thay vì trả Set.

## 2. Không có ba bảo đảm thường bị tưởng nhầm

### 2.1. Thứ tự khai báo field không bảo đảm thứ tự kết quả

```java
public record OrderInput(
        @NotBlank String sku,
        @NotNull @Min(1) Integer quantity,
        @Email String customerEmail
) {}
```

Không được kết luận provider sẽ phát hiện `sku` trước `quantity` và `customerEmail`. Annotation metadata, caching, object graph traversal và provider-specific optimizations không tạo một hợp đồng thứ tự. Jakarta Validation chú trọng constraints được đánh giá và violations tương ứng, không đảm bảo thứ tự duyệt Set cho mục đích UI.

### 2.2. Các Set có tính chất khác nhau nhưng không giải quyết được nguồn dữ liệu

| Cấu trúc | Thuộc tính | Có bảo đảm thứ tự API errors không? |
| --- | --- | --- |
| `HashSet` | Không bảo đảm iteration order | Không |
| `LinkedHashSet` | Giữ thứ tự **chèn** | Chỉ nếu thứ tự chèn ban đầu có contract |
| `TreeSet` | Sắp theo comparator, đồng thời coi comparator bằng 0 là phần tử trùng | Có nguy cơ mất violations |
| `new ArrayList<>(set)` | Copy đúng thứ tự iterator tại thời điểm copy | Không, nếu chưa sort |
| `stream().sorted(comparator).toList()` | List được sort theo comparator | Có, với khóa được thiết kế đúng |

Không chữa lỗi bằng cách bọc kết quả trong `LinkedHashSet`; nó chỉ bảo tồn thứ tự chèn vốn đã phụ thuộc thứ tự duyệt của Set đầu vào.

### 2.3. Thứ tự **đánh giá** khác thứ tự **hiển thị**

Jakarta Validation có `@GroupSequence` để kiểm soát trình tự đánh giá **nhóm constraints**. Đó không phải cơ chế yêu cầu `Set` trả về được duyệt theo thứ tự field. Nếu mục tiêu chỉ là JSON errors luôn theo tên field hoặc thứ tự UI, việc sắp xếp response **sau** validation mới là giải pháp phù hợp.

## 3. Anti-pattern làm response phụ thuộc vào Set

### 3.1. Lấy phần tử đầu

```java
ConstraintViolation<OrderInput> first =
        violations.iterator().next();
```

Nếu `violations` trống, dòng trên còn gây `NoSuchElementException`. Nếu khác rỗng, nó chỉ lấy phần tử đầu theo iterator hiện tại, **không phải** lỗi có độ ưu tiên cao nhất.

Những cách sau cũng không có bảo đảm ưu tiên:

```java
violations.stream().findFirst();
violations.toArray()[0];
new ArrayList<>(violations).get(0);
```

Nếu API chỉ cần một lỗi, hãy sort theo ưu tiên tường minh rồi mới gọi `findFirst()`. Nếu cần nhiều lỗi, đừng bỏ các phần tử chỉ vì UI muốn trình bày gọn.

### 3.2. Map thẳng sang List nhưng không sort

```java
List<String> messages = violations.stream()
        .map(ConstraintViolation::getMessage)
        .toList();
```

`toList()` chỉ giữ encounter order của stream; nó không tự tạo ordering. Ngoài ra, chỉ lấy message còn làm mất field và machine-readable code.

### 3.3. Sort rồi gom lại thành Set

```java
Set<String> fields = violations.stream()
        .map(v -> v.getPropertyPath().toString())
        .sorted()
        .collect(java.util.stream.Collectors.toSet());
```

`Collectors.toSet()` không cam kết thứ tự. Nó còn có thể loại những violations khác nhau trên **cùng một field**.

Đúng hướng:

```java
List<String> fields = violations.stream()
        .map(v -> v.getPropertyPath().toString())
        .sorted()
        .toList();
```

Đây chỉ là snippet minh họa field sorting; adapter đầy đủ sẽ giữ cả code và message.

### 3.4. Sort theo thông báo đã dịch làm khóa chính

```java
violations.stream()
        .sorted(Comparator.comparing(
                ConstraintViolation::getMessage))
        .toList();
```

Code có thể biên dịch nhưng không thích hợp làm contract presentation: `getMessage()` bị ảnh hưởng bởi `Locale`, message bundle, provider và copywriting. Đổi bản dịch có thể làm thứ tự lỗi đảo nhau.

Nên ưu tiên **canonical field path**, **error code**, **annotation type** hoặc một **priority** do API sở hữu. Có thể dùng message làm tie-break cuối cùng nếu muốn thứ tự xác định trong **một locale**, nhưng cần ghi rõ rằng thứ tự tuyệt đối giữa các locale có thể khác khi các khóa trước trùng nhau.

### 3.5. TreeSet có thể vô tình xóa lỗi

Không nên dùng comparator chỉ theo field để tạo `TreeSet`:

```java
Comparator<ConstraintViolation<?>> byField =
        Comparator.comparing(v ->
                v.getPropertyPath().toString());
```

Một field có thể vi phạm cả `@NotBlank` và `@Size`. Nếu comparator cho hai phần tử cùng field kết quả `0`, `TreeSet` có thể chỉ giữ một phần tử. **Sắp xếp** và **loại trùng** phải là hai quyết định tách biệt.

## 4. Thiết kế một hợp đồng JSON lỗi ổn định

Không nên serialize trực tiếp `ConstraintViolation` vì nó chứa thông tin như invalid value, root bean và provider metadata. Hãy tạo DTO public:

```java
public record ApiViolation(
        String field,
        String code,
        String message
) {}
```

Một phản hồi hợp lý:

```json
{
  "code": "VALIDATION_ERROR",
  "errors": [
    {
      "field": "customerEmail",
      "code": "Email",
      "message": "must be a well-formed email address"
    },
    {
      "field": "quantity",
      "code": "Min",
      "message": "must be greater than or equal to 1"
    },
    {
      "field": "sku",
      "code": "NotBlank",
      "message": "must not be blank"
    }
  ]
}
```

Đây là ví dụ với messages tiếng Anh thường gặp của Hibernate Validator; văn bản có thể thay đổi theo bản dịch, provider và version. **Thứ tự array** do ứng dụng quyết định: `customerEmail`, `quantity`, `sku`.

### 4.1. Khóa sort

Một comparator thực dụng có bốn cấp:

1. `ConstraintViolation#getPropertyPath().toString()`.
2. Tên đầy đủ annotation type từ `getConstraintDescriptor().getAnnotation().annotationType().getName()`.
3. `ConstraintViolation#getMessageTemplate()`.
4. `ConstraintViolation#getMessage()` làm tie-break cuối, chỉ khi cần.

Vì sao?

- Path xác định trường/điểm lỗi.
- Annotation full name tránh hai custom annotations cùng simple name ở hai package.
- Message template chưa nội suy thường ổn định hơn text đã dịch.
- Message cuối giúp phân biệt những entries vẫn cùng khóa trước trong cùng locale.
- Không lấy `getInvalidValue()` làm key: có thể là password, token hoặc một object không có chuỗi ổn định.
- Không dùng `System.identityHashCode` hay hashCode của instance: lệ thuộc object identity/JVM.

Nếu hai violations khác nhau có mọi sort key trùng nhưng **public DTO cũng giống nhau**, đổi thứ tự không làm đổi JSON. Nếu chúng có public DTO khác nhau, phải bổ sung một tie-break ổn định thuộc domain; đừng tùy tiện lấy iteration order.

### 4.2. Thứ tự từ điển không phải thứ tự UX

Ví dụ alphabet cho `customerEmail` trước `quantity` trước `sku`. Nếu form thực tế muốn `sku` đứng đầu, định nghĩa priority map:

```java
Map<String, Integer> priority = Map.of(
        "sku", 0,
        "quantity", 1,
        "customerEmail", 2
);

Comparator<ApiViolation> uxOrder =
        Comparator.comparingInt((ApiViolation e) ->
                priority.getOrDefault(e.field(), 100))
                .thenComparing(ApiViolation::field)
                .thenComparing(ApiViolation::code)
                .thenComparing(ApiViolation::message);
```

Đây là snippet minh họa, cần imports `Map` và `Comparator`. Tất cả trường chưa định nghĩa có rank 100 và được sort ổn định bằng các khóa phụ. Nếu priority mang ý nghĩa hợp đồng của frontend, hãy version/document và test nó.

## 5. Dự án Spring Boot chạy được

Ứng dụng minh họa hai con đường:

- `POST /api/orders/manual`: gọi trực tiếp `Validator#validate`, nhận `Set<ConstraintViolation<OrderInput>>`, chuẩn hóa thành `List`.
- `POST /api/orders/automatic`: dùng `@Valid @RequestBody` theo Spring MVC; `MethodArgumentNotValidException` có `BindingResult`, cũng cần sort nếu muốn response order do ứng dụng quy định.
- `MockMvc` kiểm tra thứ tự JSON.
- JUnit kiểm tra normalizer với **các hoán vị khác nhau** của cùng `Set`, không dựa vào provider tình cờ giữ một thứ tự.

### 5.1. Cấu trúc

```text
ordered-errors-demo/
  settings.gradle
  build.gradle
  src/
    main/java/com/example/orderederrors/
      OrderedErrorsApplication.java
      OrderInput.java
      ApiViolation.java
      ApiError.java
      ViolationNormalizer.java
      OrderController.java
      ValidationAdvice.java
    test/java/com/example/orderederrors/
      OrderValidationTest.java
```

### 5.2. Gradle

`settings.gradle`:

```groovy
rootProject.name = 'ordered-errors-demo'
```

`build.gradle`:

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

`spring-boot-starter-validation` mang Jakarta API và provider thường là Hibernate Validator. Không cần Hibernate Validator proprietary API cho normalizer: `ConstraintViolation`, `Validator` và `ConstraintDescriptor` thuộc Jakarta Validation.

### 5.3. Main application

`src/main/java/com/example/orderederrors/OrderedErrorsApplication.java`:

```java
package com.example.orderederrors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrderedErrorsApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrderedErrorsApplication.class, args);
    }
}
```

### 5.4. DTO dữ liệu

`src/main/java/com/example/orderederrors/OrderInput.java`:

```java
package com.example.orderederrors;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public record OrderInput(
        @NotBlank String sku,
        @NotNull @Min(1) Integer quantity,
        @Email String customerEmail
) {}
```

`sku=" "` vi phạm `NotBlank`; `quantity=0` vi phạm `Min`; `customerEmail="not-an-email"` vi phạm `Email`. Thêm `@NotNull` cho `quantity` vì `@Min` tự nó coi null hợp lệ. `@Email` trong demo cho phép null: nếu email bắt buộc, thêm `@NotBlank` hoặc `@NotNull` theo domain.

### 5.5. DTO phản hồi

`src/main/java/com/example/orderederrors/ApiViolation.java`:

```java
package com.example.orderederrors;

public record ApiViolation(
        String field,
        String code,
        String message
) {}
```

`src/main/java/com/example/orderederrors/ApiError.java`:

```java
package com.example.orderederrors;

import java.util.List;

public record ApiError(
        String code,
        List<ApiViolation> errors
) {}
```

`ApiError.code` là `VALIDATION_ERROR` hoặc `OK`. `ApiViolation.code` trong demo lấy simple annotation name như `Min`; nếu API là public contract lâu dài, nên ánh xạ về business codes ổn định (ví dụ `MIN_QUANTITY`), tránh ràng buộc frontend vào annotation implementation.

### 5.6. ViolationNormalizer.java

`src/main/java/com/example/orderederrors/ViolationNormalizer.java`:

```java
package com.example.orderederrors;

import jakarta.validation.ConstraintViolation;
import java.util.Comparator;
import java.util.List;
import java.util.Set;

public final class ViolationNormalizer {

    private ViolationNormalizer() {}

    public static <T> List<ApiViolation> normalize(
            Set<ConstraintViolation<T>> violations) {

        return violations.stream()
                .map(v -> new SortEntry(
                        v.getPropertyPath().toString(),
                        v.getConstraintDescriptor()
                                .getAnnotation()
                                .annotationType()
                                .getName(),
                        v.getConstraintDescriptor()
                                .getAnnotation()
                                .annotationType()
                                .getSimpleName(),
                        v.getMessageTemplate(),
                        v.getMessage()
                ))
                .sorted(
                        Comparator.comparing(SortEntry::field)
                                .thenComparing(SortEntry::annotationType)
                                .thenComparing(SortEntry::messageTemplate)
                                .thenComparing(SortEntry::message)
                )
                .map(e -> new ApiViolation(
                        e.field(), e.code(), e.message()
                ))
                .toList();
    }

    private record SortEntry(
            String field,
            String annotationType,
            String code,
            String messageTemplate,
            String message
    ) {}
}
```

Các bước quan trọng:

1. Nhận đúng `Set<ConstraintViolation<T>>` từ `validator.validate(input)`.
2. Chuyển sang một DTO nội bộ `SortEntry` chỉ có metadata cần thiết, không chứa invalidValue/rootBean.
3. Sắp xếp theo `field`, tên annotation đầy đủ, `messageTemplate` và `message`.
4. Map sang public DTO **sau khi sort**.
5. Giữ kết quả là `List`; không gọi `distinct()` và không gom lại thành `Set`.
6. Nếu project cần thứ tự bất biến giữa mọi locale, thay `message` tie-break bằng một ID/priority không phụ thuộc bản dịch.

`getPropertyPath().toString()` phù hợp minh họa đối với các field đơn giản. Với nested list/map và API cần portability cao, nên thiết kế canonical path bằng `jakarta.validation.Path.Node`, xét `getKind()`, `getIndex()` và `getKey()`.

### 5.7. Controller: Jakarta manual validation và Spring MVC validation

`src/main/java/com/example/orderederrors/OrderController.java`:

```java
package com.example.orderederrors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Valid;
import jakarta.validation.Validator;
import java.util.List;
import java.util.Set;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/orders")
public class OrderController {

    private final Validator validator;

    public OrderController(Validator validator) {
        this.validator = validator;
    }

    @PostMapping("/manual")
    public ResponseEntity<ApiError> manual(
            @RequestBody OrderInput input) {

        // Không đặt @Valid ở argument này để tự gọi Validator.
        Set<ConstraintViolation<OrderInput>> violations =
                validator.validate(input);

        if (!violations.isEmpty()) {
            return ResponseEntity.badRequest().body(
                    new ApiError(
                            "VALIDATION_ERROR",
                            ViolationNormalizer.normalize(violations)
                    )
            );
        }

        return ResponseEntity.ok(
                new ApiError("OK", List.of())
        );
    }

    @PostMapping("/automatic")
    public ResponseEntity<ApiError> automatic(
            @Valid @RequestBody OrderInput input) {

        // Lỗi @Valid được Spring xử lý trước khi method chạy.
        return ResponseEntity.ok(
                new ApiError("OK", List.of())
        );
    }
}
```

Điểm chính: `/manual` kiểm tra một DTO đã deserialize được; `/automatic` giao việc cho Spring MVC argument validation. JSON malformed là lỗi chuyển đổi ở cả hai đường, không phải `ConstraintViolation`.

### 5.8. ValidationAdvice.java cho Spring MVC argument errors

`src/main/java/com/example/orderederrors/ValidationAdvice.java`:

```java
package com.example.orderederrors;

import java.util.Comparator;
import java.util.List;
import java.util.Objects;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ValidationAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> invalid(
            MethodArgumentNotValidException exception) {

        List<ApiViolation> errors = exception.getBindingResult()
                .getAllErrors()
                .stream()
                .map(this::toViolation)
                .sorted(
                        Comparator.comparing(ApiViolation::field)
                                .thenComparing(ApiViolation::code)
                                .thenComparing(ApiViolation::message)
                )
                .toList();

        return ResponseEntity.badRequest()
                .body(new ApiError("VALIDATION_ERROR", errors));
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ApiError> unreadable(
            HttpMessageNotReadableException exception) {

        return ResponseEntity.badRequest()
                .body(new ApiError("INVALID_JSON", List.of()));
    }

    private ApiViolation toViolation(ObjectError error) {
        String field = error instanceof FieldError fieldError
                ? fieldError.getField()
                : "";

        String code = Objects.toString(error.getCode(), "invalid");
        String message = Objects.toString(
                error.getDefaultMessage(), "Invalid value"
        );

        return new ApiViolation(field, code, message);
    }
}
```

`BindingResult#getAllErrors()` bao gồm `FieldError` và `ObjectError`, tránh bỏ class-level constraints. Nó trả Spring errors, **không phải** Set<ConstraintViolation>. Nhưng nếu muốn chuẩn hóa thứ tự HTTP JSON, advice vẫn nên sort tường minh.

Trong ứng dụng dùng `MessageSource` để dịch thông báo, `FieldError`/`ObjectError` là `MessageSourceResolvable` và có thể dùng `messageSource.getMessage(error, locale)`. Đừng coi text từ `getDefaultMessage()` là một stable sort key xuyên mọi ngôn ngữ. Ở demo, không yêu cầu locale bất biến vì chỉ cần sort field và code cho ba lỗi khác field.

## 6. Kiểm thử bằng MockMvc và phép hoán vị đầu vào

Tệp `src/test/java/com/example/orderederrors/OrderValidationTest.java`:

```java
package com.example.orderederrors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Random;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class OrderValidationTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    Validator validator;

    private static final String INVALID = """
            {
              "sku": " ",
              "quantity": 0,
              "customerEmail": "not-an-email"
            }
            """;

    private static final String VALID = """
            {
              "sku": "SKU-17",
              "quantity": 2,
              "customerEmail": "lan@example.org"
            }
            """;

    @Test
    void manualResponseHasDefinedFieldOrder() throws Exception {
        mvc.perform(post("/api/orders/manual")
                .contentType(MediaType.APPLICATION_JSON)
                .content(INVALID))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.errors.length()").value(3))
            .andExpect(jsonPath("$.errors[0].field")
                    .value("customerEmail"))
            .andExpect(jsonPath("$.errors[0].code").value("Email"))
            .andExpect(jsonPath("$.errors[1].field")
                    .value("quantity"))
            .andExpect(jsonPath("$.errors[1].code").value("Min"))
            .andExpect(jsonPath("$.errors[2].field").value("sku"))
            .andExpect(jsonPath("$.errors[2].code")
                    .value("NotBlank"));
    }

    @Test
    void springMvcResponseHasDefinedFieldOrder() throws Exception {
        mvc.perform(post("/api/orders/automatic")
                .contentType(MediaType.APPLICATION_JSON)
                .content(INVALID))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.errors.length()").value(3))
            .andExpect(jsonPath("$.errors[0].field")
                    .value("customerEmail"))
            .andExpect(jsonPath("$.errors[1].field")
                    .value("quantity"))
            .andExpect(jsonPath("$.errors[2].field")
                    .value("sku"));
    }

    @Test
    void permutationsOfSetProduceExactlyTheSameList() {
        OrderInput input = new OrderInput(
                " ", 0, "not-an-email"
        );

        Set<ConstraintViolation<OrderInput>> raw =
                validator.validate(input);

        assertEquals(3, raw.size());
        List<ApiViolation> expected =
                ViolationNormalizer.normalize(raw);

        List<ConstraintViolation<OrderInput>> items =
                new ArrayList<>(raw);

        for (int seed = 0; seed < 20; seed++) {
            Collections.shuffle(items, new Random(seed));

            Set<ConstraintViolation<OrderInput>> permuted =
                    new LinkedHashSet<>(items);

            assertEquals(
                    expected,
                    ViolationNormalizer.normalize(permuted),
                    "Changed order for seed " + seed
            );
        }
    }

    @Test
    void reverseOrderDoesNotAffectOutput() {
        Set<ConstraintViolation<OrderInput>> raw =
                validator.validate(
                        new OrderInput(" ", 0, "not-an-email")
                );

        List<ConstraintViolation<OrderInput>> reversed =
                new ArrayList<>(raw);
        Collections.reverse(reversed);

        assertEquals(
                ViolationNormalizer.normalize(raw),
                ViolationNormalizer.normalize(
                        new LinkedHashSet<>(reversed))
        );
    }

    @Test
    void validManualRequestReturnsEmptyErrors() throws Exception {
        mvc.perform(post("/api/orders/manual")
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value("OK"))
            .andExpect(jsonPath("$.errors.length()").value(0));
    }

    @Test
    void validAutomaticRequestReturnsEmptyErrors()
            throws Exception {

        mvc.perform(post("/api/orders/automatic")
                .contentType(MediaType.APPLICATION_JSON)
                .content(VALID))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.code").value("OK"))
            .andExpect(jsonPath("$.errors.length()").value(0));
    }

    @Test
    void malformedJsonIsNotAConstraintViolation()
            throws Exception {

        mvc.perform(post("/api/orders/manual")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"sku\":\"S1\",\"quantity\":"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("INVALID_JSON"))
            .andExpect(jsonPath("$.errors.length()").value(0));
    }

    @Test
    void missingQuantityIsNotNullViolation() {
        Set<ConstraintViolation<OrderInput>> raw =
                validator.validate(new OrderInput(
                        "SKU-17", null, "lan@example.org"
                ));

        assertEquals(1, raw.size());
        ApiViolation error =
                ViolationNormalizer.normalize(raw).get(0);

        assertEquals("quantity", error.field());
        assertEquals("NotNull", error.code());
    }
}
```

Chạy:

```bash
./gradlew test
```

Windows PowerShell:

```powershell
.\gradlew.bat test
```

Nếu project chưa có Gradle wrapper, dùng Gradle cài sẵn để tạo wrapper hoặc chạy `gradle test`. **Kỳ vọng tám test PASS** với cấu hình tương ứng. Đây là expected outcome của bài mẫu; không phải tuyên bố đã thực sự chạy JUnit/Gradle trong bước biên soạn.

### 6.1. Tại sao test hoán vị mạnh hơn gọi endpoint lặp đi lặp lại?

Một test gọi cùng request 100 lần và thấy response giống nhau chưa chứng minh code độc lập khỏi Set order; Hibernate Validator có thể tình cờ trả cùng iteration order trên một JVM. Test `permutationsOfSetProduceExactlyTheSameList` chủ động:

1. Lấy cùng một tập violations thực.
2. Tạo nhiều `LinkedHashSet` chứa cùng phần tử nhưng với thứ tự chèn khác nhau.
3. Chạy normalizer cho từng permutation.
4. Assert `List<ApiViolation>` bằng nhau.

Đây là một **metamorphic test**: yếu tố không được ảnh hưởng kết quả (thứ tự chèn) được biến đổi có chủ ý, còn output contract phải giữ nguyên. Test sẽ bắt việc ai đó xóa `sorted(...)` dù provider không tự đảo thứ tự trong một lần chạy.

### 6.2. Test trực tiếp Set membership khi thứ tự không phải contract

Nếu test tầng Jakarta thuần chỉ muốn xác định ba trường sai:

```java
Set<String> fields = validator.validate(
        new OrderInput(" ", 0, "not-an-email")
).stream()
 .map(v -> v.getPropertyPath().toString())
 .collect(java.util.stream.Collectors.toSet());

assertEquals(
        Set.of("sku", "quantity", "customerEmail"),
        fields
);
```

Đoạn snippet giả sử có biến `validator` và static import `assertEquals`. So sánh `Set` khi không cần order. Chỉ assert JSON array index khi ứng dụng **đã định nghĩa và thực thi** ordering policy.

## 7. Một ví dụ console Java sử dụng cùng normalizer

Ngoài HTTP, `ViolationNormalizer` cũng dùng được trong ứng dụng Java thông thường. Với provider Jakarta Validation tương thích:

```java
try (ValidatorFactory factory =
             Validation.buildDefaultValidatorFactory()) {

    Validator validator = factory.getValidator();

    Set<ConstraintViolation<OrderInput>> violations =
            validator.validate(
                    new OrderInput(" ", 0, "not-an-email")
            );

    ViolationNormalizer.normalize(violations)
            .forEach(e -> System.out.println(
                    e.field() + " -> " + e.code()
            ));
}
```

Đây là snippet sử dụng các class trong dự án, cần imports `jakarta.validation.Validation`, `ValidatorFactory`, `Validator`, `ConstraintViolation` và `java.util.Set`. `ValidatorFactory` cần được đóng sau khi dùng; trong Spring Boot thường để container quản lý validator, không tạo factory mới cho từng request.

Expected stdout của phần field/code **sau khi sort**:

```text
customerEmail -> Email
quantity -> Min
sku -> NotBlank
```

Không in message trong expected stdout vì message mặc định phụ thuộc locale/bundle/provider. **Không** lấy `violations.iterator().next()` để quyết định dòng đầu.

## 8. Fail-fast và GroupSequence không biến Set thành danh sách ổn định

### 8.1. @GroupSequence định nghĩa thứ tự nhóm được đánh giá

Ví dụ minh họa:

```java
public interface BasicChecks {}

public interface DetailedChecks {}

@GroupSequence({BasicChecks.class, DetailedChecks.class})
public interface OrderedChecks {}
```

Khi validate bằng `OrderedChecks.class`, các constraints của `BasicChecks` được xét trước; nếu nhóm này có violation, provider không cần đánh giá các constraints thuộc `DetailedChecks` tiếp theo theo semantics group sequence.

Tuy nhiên:

- Điều này **không** định nghĩa thứ tự duyệt từng violation trong một nhóm.
- `@GroupSequence` không yêu cầu Set returned sorted.
- Group sequence thay đổi tập constraints được đánh giá, không phải chỉ thay cách trình bày JSON.
- Nếu chỉ muốn alphabetic field order, **sort response**; đừng tự ý thay nghiệp vụ validation groups.

### 8.2. Hibernate Validator fail-fast

Hibernate Validator có tính năng fail-fast (provider extension) để dừng sau vi phạm đầu tiên. Theo reference guide, khi có nhiều constraint cùng sai, **không bảo đảm lỗi nào được phát hiện trước**. Vì vậy:

- Bật fail-fast và sort một list chỉ có một phần tử **không làm lỗi được chọn thành deterministic**.
- Nếu API cần trả tất cả lỗi, không bật fail-fast trên validator dùng tạo response.
- Nếu muốn chỉ trả một lỗi ưu tiên, phải định nghĩa chính sách: group sequence hoặc các bước validation có thứ tự được thiết kế rõ.
- Đừng dựa vào thứ tự annotation hay `iterator().next()` làm error priority.

## 9. Nested paths, collection indexes và so sánh theo chuỗi

Với nested DTO:

```java
public record Address(@NotBlank String city) {}

public record DeliveryInput(
        @NotBlank String sku,
        @NotNull @Valid Address address
) {}
```

Violation của `address.city` thường có path biểu diễn dạng:

```text
address.city
```

Với collection:

```java
public record OrderLine(@NotBlank String sku) {}

public record BatchInput(
        @NotEmpty List<@Valid OrderLine> lines
) {}
```

Có thể có:

```text
lines[0].sku
lines[2].sku
lines[10].sku
```

`Path#toString()` không phải một **JSON Pointer canonical** do API mặc định công bố. Nếu cần mapping bền vững giữa nhiều provider, nên duyệt `jakarta.validation.Path.Node` và biểu diễn riêng:

- `node.getKind()`: `PROPERTY`, `BEAN`, `CONTAINER_ELEMENT`, `PARAMETER`, `RETURN_VALUE`...
- `node.isInIterable()`: node có nằm trong collection/map không.
- `node.getIndex()` và `node.getKey()`: vị trí index/key.
- Schema public chọn dạng `field`, `location` hoặc JSON Pointer có escaping.

Một hạn chế của sort từ điển: `lines[10].sku` có thể đứng trước `lines[2].sku`. Nó vẫn **deterministic** nhưng không đúng thứ tự số tự nhiên mà UI mong muốn. Nếu API cần thứ tự index tăng dần, hãy so sánh `Path.Node#getIndex()` như một con số, không chỉ `toString()`.

### 9.1. Lỗi cấp lớp và method validation

Class-level constraint có thể tạo path rỗng hoặc node bean, không nhất thiết chỉ vào một property. Đối với Jakarta `ExecutableValidator`, violations trên method parameters/return values có thể chứa thêm method/parameter/return-value nodes.

Nếu đây là **return-value contract violation** của server, không được vì đang dùng chung normalization layer mà biến thành HTTP 400. Spring MVC 6.1+ có `HandlerMethodValidationException#isForReturnValue()`; input method violations thường là 400, return-value violations thường 500. Cần phân loại trách nhiệm trước khi dựng response.

## 10. Nhiều constraints cùng field: đừng làm mất lỗi

```java
@NotBlank
@Size(min = 5)
String sku;
```

Nếu `sku=" "`, có thể vi phạm cả `NotBlank` và `Size`. Nếu adapter dùng:

```java
Map<String, String> errors = new HashMap<>();
for (ConstraintViolation<?> v : violations) {
    errors.put(v.getPropertyPath().toString(), v.getMessage());
}
```

thì lỗi sau cùng có thể ghi đè lỗi trước, và “lỗi sau cùng” lại phụ thuộc thứ tự Set. Không chỉ mất deterministic order, API còn mất dữ liệu.

Nếu muốn **một lỗi mỗi field**, hãy định nghĩa priority cho các loại rule, ví dụ Required trước Format trước Length, rồi lấy một lỗi theo comparator có thứ tự rõ. Nếu cần **tất cả**, giữ List và để nhiều entries có cùng `field`.

**Lưu ý về equals/comparator:** `TreeSet` coi comparator bằng 0 là phần tử trùng, vì thế chỉ dùng TreeSet nếu comparator định nghĩa chính xác cả identity/deduplication semantics. Trong đa số error APIs, `List` sau sort đơn giản và an toàn hơn.

## 11. Tính ổn định xuyên locale và provider

`ConstraintViolation#getMessage()` thường là text đã nội suy; `getMessageTemplate()` là template ban đầu. Nếu dùng `MessageSource` của Spring để dịch `FieldError`, thông báo cuối còn phụ thuộc `Locale` được resolve từ request.

Để response đúng hướng:

- `code` nên là machine-readable identifier ổn định theo business.
- `field` nên là canonical path do API định nghĩa.
- `message` là nội dung có thể thay theo locale.
- Comparator nên dựa chủ yếu trên code/path/priority không phụ thuộc ngôn ngữ.
- Nếu cùng field/code/template có nhiều entries với messages khác nhau, một tie-break theo message làm order ổn định **trong cùng locale**, chưa chắc y hệt giữa hai locale.
- Nếu contract yêu cầu order bất biến xuyên locales, tạo **error ID hoặc sort rank không phụ thuộc bản dịch**, đủ phân biệt mọi trường hợp.

Provider khác nhau hoặc config khác nhau có thể tạo **tập violations** khác nhau (ví dụ custom constraints, groups, fail-fast). Normalization không thể đảm bảo hai tập khác nhau sẽ cho cùng response; nó chỉ làm thứ tự của **cùng tập lỗi** không phụ thuộc traversal order.

## 12. Checklist và lỗi thường gặp

| Lỗi thường gặp | Hậu quả | Cách đúng |
| --- | --- | --- |
| Dùng `iterator().next()` | Lấy lỗi không rõ ưu tiên | Sort rồi mới lấy đầu |
| Tin thứ tự field trong record được giữ | Phụ thuộc provider | Dựa vào comparator |
| Copy sang `ArrayList` rồi dùng ngay | Sao chép thứ tự không cam kết | Sort list |
| Bọc trong `LinkedHashSet` | Giữ thứ tự chèn tùy ý | Sort rõ ràng |
| Dùng `TreeSet` comparator chỉ theo path | Mất lỗi khác cùng field | List sort, không dedup |
| Sort rồi collect `toSet()` | Không còn presentation order | Giữ `List` |
| Sort theo message | Thay locale làm đổi thứ tự | Code/path/priority trước |
| Dùng hashCode làm tie-break | Thứ tự không ổn định giữa JVM | Metadata/ID ổn định |
| Dùng invalid value để sort | Dễ lộ dữ liệu, null/toString khó đoán | Không dùng invalidValue |
| Map theo field một cách âm thầm | Ghi đè nhiều constraints | List hoặc policy chọn một lỗi rõ |
| Chỉ test status 400 | Không phát hiện regression của error order | Assert sorted JSON array |
| Test chỉ một violation | Không phát hiện vấn đề thứ tự | Test >=2 violations |
| Test gọi lặp cùng request | Có thể pass vì provider ổn định ngẫu nhiên | Chủ động đảo insertion order |
| Nghĩ `@GroupSequence` sắp Set | Nhầm validation evaluation với presentation | Sort response riêng |
| Bật fail-fast và mong lỗi đầu tiên cố định | Lỗi được chọn có thể thay đổi | Tắt fail-fast hoặc kiểm soát group |
| Dùng `Path#toString()` làm JSON Pointer mặc định | Rủi ro khác nhau giữa node/provider | Canonicalize Path.Node |
| Sort `items[10]` như text | Sai numeric ordering | Parse index/sort cấu trúc |
| Serialize raw ConstraintViolation | Lộ bean/invalid values/provider metadata | DTO public tối giản |
| Bỏ `ObjectError` | Mất class-level violation | `getAllErrors()` |
| Gộp mọi ConstraintViolationException thành 400 | Che lỗi server return contract | Phân loại input/return |

### Checklist code review

1. Mọi nơi nhận `Set<ConstraintViolation<T>>` có xác định việc dùng order hay không?
2. Có đoạn `iterator().next()`, `findFirst()`, `toArray()[0]` chưa định nghĩa priority không?
3. Có map thẳng `Set` sang JSON array không?
4. Comparator có dùng stable path/code/template và tie-break phù hợp không?
5. Có tránh invalidValue, rootBean và raw exception trong payload không?
6. Có giữ toàn bộ violations khi một field có nhiều constraints không?
7. Có test hoán vị đầu vào Set và test multiple violations không?
8. Có tách parse/conversion errors khỏi Bean Validation không?
9. Với `@Valid @RequestBody`, có xử lý `BindingResult`/`MethodArgumentNotValidException` đúng loại không?
10. Với direct method validation, có phân biệt `HandlerMethodValidationException` input/return không?
11. Có fallback policy cho localized message và stable error codes không?
12. Nếu cần UI rank, map rank đã được document/test chưa?
13. Nested lists có cần sort numeric index thay vì lexicographic không?
14. Khi nâng Spring/Hibernate Validator, có chạy lại tests order độc lập provider không?

**Kết luận:** `Set<ConstraintViolation>` chứa một **tập lỗi**, không phải danh sách đã được sắp cho frontend. Không lấy thứ tự duyệt làm ưu tiên nghiệp vụ. Chuyển mỗi violation sang DTO an toàn, **sort bằng comparator tường minh**, giữ ở `List` khi serialize và test bằng hoán vị của cùng Set. Cách này loại một nguồn bất ổn trong API phản hồi lỗi, đồng thời tránh phụ thuộc vào provider hoặc thứ tự khai báo constraints.

## Tài liệu tham khảo chính thức

- [Jakarta Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): Set returned by Validator, constraint evaluation, groups và property paths.
- [Jakarta Validation — Validator API](https://javadoc.io/static/jakarta.validation/jakarta.validation-api/3.1.1/jakarta/validation/Validator.html): `validate(...)` trả `Set<ConstraintViolation<T>>`.
- [Hibernate Validator 8.0 Reference Guide](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/): validation groups, group sequence, fail-fast và lưu ý thứ tự constraint không được bảo đảm.
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html): phân biệt argument validation và method validation.
- [Spring Framework — BindingResult](https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/validation/BindingResult.html): field errors, global errors và binding metadata.
- [Spring Framework — Error Responses](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-ann-rest-exceptions.html): MethodArgumentNotValidException, HandlerMethodValidationException và API error handling.
