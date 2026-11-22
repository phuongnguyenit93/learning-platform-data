# Kiểm tra exception, nguyên nhân và thông điệp phù hợp với JUnit Jupiter và Spring Boot

Một test chỉ kiểm tra rằng “có lỗi xảy ra” thường chưa đủ. Với đường xử lý thất bại, cần biết **lỗi đúng loại không**, **nguyên nhân thực sự có được giữ lại không**, **thông điệp có phản ánh đúng hợp đồng không**, và nếu lỗi đi qua HTTP thì **client nhận đúng status/body không**. Bài học này hướng dẫn viết assertion cho exception bằng JUnit Jupiter, sau đó kiểm tra cách Spring Boot chuyển exception thành phản hồi API.

Nguyên tắc cốt lõi: **tạo đầu vào gây lỗi có chủ đích → gọi đúng thao tác cần kiểm tra → bắt exception cụ thể → xác minh thông điệp, cause và các hiệu ứng quan trọng**. Assertion phải chứng minh đúng hành vi đã quy định; không nên chỉ bắt một loại ngoại lệ quá rộng để test xanh.

## 1. Bốn tầng thông tin cần phân biệt

| Thông tin | Cách quan sát | Nó chứng minh điều gì? | Giới hạn |
| --- | --- | --- | --- |
| **Loại exception** | `assertThrows`, `assertThrowsExactly`, `getClass()` | Code phát ra loại lỗi được kỳ vọng | Chưa chứng minh lý do và thông điệp đúng |
| **Thông điệp** | `exception.getMessage()` | Chi tiết lỗi dành cho người đọc/log hoặc hợp đồng đã cam kết | Message có thể thay đổi theo dữ liệu, thư viện, ngôn ngữ |
| **Nguyên nhân (cause)** | `exception.getCause()`, chuỗi `Caused by` | Lỗi cấp cao có lưu nguồn gây lỗi cấp thấp hay không | Có exception hợp lệ không có cause |
| **Hợp đồng HTTP** | `MockMvc`/HTTP client: status, code, body | Client nhận được lỗi được chuẩn hóa từ tầng web | Không nhất thiết nhìn thấy Java exception trực tiếp |

Ví dụ: chuỗi `"abc"` không chuyển thành số nguyên. `Integer.parseInt("abc")` phát ra `NumberFormatException`. Service có thể bọc lỗi này thành `InvalidQuantityException` với message `"Số lượng phải là số nguyên"` và **cause** là `NumberFormatException`. API lại trả `HTTP 400` cùng mã `INVALID_QUANTITY`. Đây là những bằng chứng khác nhau, mỗi tầng cần assertion phù hợp.

Đừng nhầm **message** với **cause**: `getMessage()` trả chuỗi mô tả; `getCause()` trả một đối tượng `Throwable` khác (hoặc `null`). Cùng một thông điệp không có nghĩa hai exception có cùng nguồn gốc. Một lỗi nghiệp vụ tự phát hiện ở tầng validation đôi khi không cần cause.

## 2. Chọn đúng assertion JUnit Jupiter

JUnit Jupiter cung cấp các API trong `org.junit.jupiter.api.Assertions`. Với lỗi dự kiến phát ra từ mã đang kiểm thử, ba nhóm API sau là nền tảng.

### 2.1. `assertThrows`: chấp nhận exception đúng loại hoặc loại con

```java
InvalidQuantityException error = assertThrows(
        InvalidQuantityException.class,
        () -> service.parse("abc")
);
assertEquals("Số lượng phải là số nguyên", error.getMessage());
```

Tham số thứ hai là một `Executable` (lambda hoặc method reference). JUnit thực thi nó; nếu không có exception hoặc exception khác loại yêu cầu, assertion thất bại. Nếu exception thuộc đúng loại hoặc **một subclass** của loại đó, assertion thành công và **trả về đối tượng exception thực tế** để tiếp tục kiểm tra `getMessage()`, `getCause()` và dữ liệu bổ sung.

Chẳng hạn, `assertThrows(RuntimeException.class, ...)` có thể chấp nhận cả `NullPointerException` lẫn domain exception nếu chúng kế thừa `RuntimeException`. Đây thường là kiểu assertion quá rộng: test có thể xanh vì một bug khác hoàn toàn với lỗi nghiệp vụ muốn xác nhận.

### 2.2. `assertThrowsExactly`: bắt buộc cùng lớp exception

```java
InvalidQuantityException error = assertThrowsExactly(
        InvalidQuantityException.class,
        () -> service.parse("0")
);
assertEquals("Số lượng phải lớn hơn 0", error.getMessage());
```

`assertThrowsExactly` chỉ thành công nếu exception có **chính xác** class được chỉ định; subclass không được chấp nhận. Dùng khi loại exception cụ thể là một phần hợp đồng hoặc cần phát hiện việc vô tình thay bằng loại lỗi khác. Dùng `assertThrows` khi hợp đồng cho phép subclass hợp lệ.

**Chọn theo yêu cầu, không theo mức độ “nghiêm” chung:** nếu thư viện có chủ đích cung cấp một họ exception cùng kế thừa `BusinessException`, cố ép `assertThrowsExactly(BusinessException.class, ...)` sẽ quá cứng. Ngược lại, chỉ yêu cầu `Exception.class` thường quá lỏng.

### 2.3. `assertDoesNotThrow`: đường thành công không phát lỗi

```java
int quantity = assertDoesNotThrow(() -> service.parse("12"));
assertEquals(12, quantity);
```

Kiểm tra không ném exception là hữu ích cho đường hợp lệ, nhưng **chưa đủ để chứng minh kết quả đúng**. Vì vậy kết hợp với assertion trên giá trị hoặc hiệu ứng. Với các ví dụ runnable bên dưới, hai dòng trên khẳng định cả “không phát lỗi” lẫn “trả đúng số lượng”.

### 2.4. Tham số message của *assertion* khác message của *exception*

```java
assertThrows(
        InvalidQuantityException.class,
        () -> service.parse("0"),
        "Đầu vào bằng 0 phải bị từ chối"
);
```

Chuỗi thứ ba ở `assertThrows` là **thông điệp chẩn đoán nếu assertion thất bại**, không phải yêu cầu JUnit so sánh với `exception.getMessage()`. Muốn kiểm tra thông điệp exception, phải nhận biến `error` rồi `assertEquals`, `assertTrue` hoặc assertion phù hợp.

## 3. Kiểm tra message: khớp hợp đồng nhưng tránh test mong manh

Các cách so sánh có mức độ phù hợp khác nhau:

| Cách kiểm tra | Khi nên dùng | Ví dụ |
| --- | --- | --- |
| **Khớp chính xác** | Message là hợp đồng ổn định của logic do nhóm sở hữu | `assertEquals("Số lượng phải lớn hơn 0", error.getMessage())` |
| **Kiểm tra một phần** | Message có dữ liệu động, chỉ một thành phần ổn định quan trọng | `assertTrue(error.getMessage().contains("Số lượng"))` |
| **Kiểm tra cấu trúc/thuộc tính** | API có mã lỗi, trường, tham số riêng | Kiểm tra `errorCode`, `field`, `status` thay vì phụ thuộc toàn bộ câu chữ |
| **Không kiểm tra nội dung message** | Thông điệp do runtime/driver/thư viện tạo, không nằm trong hợp đồng | Chỉ assert type, cause hoặc thông tin ổn định do ứng dụng cung cấp |

Thông điệp của `NumberFormatException`, lỗi JDBC, Hibernate, driver hoặc JDK có thể khác theo phiên bản và implementation. Tránh kiểm tra nguyên văn message của những dependency này, trừ khi chính message đó là hợp đồng cần bảo vệ. Khi thay đổi ngôn ngữ hoặc dùng localization, không nên để mọi unit test phụ thuộc vào một câu chữ không được cam kết; mã lỗi ổn định thường thích hợp hơn cho API.

Ví dụ thông điệp có ID động:

```java
assertNotNull(error.getMessage());
assertTrue(error.getMessage().contains("order-42"));
```

Đây chỉ là **trích đoạn minh họa** cho một exception có chứa `order-42`; không phải kỳ vọng từ dịch vụ lượng hàng bên dưới. Nếu message được định nghĩa cố định, `assertEquals` sẽ phát hiện cả việc vô tình mất dấu, đổi thông điệp hoặc thêm thông tin nhạy cảm không mong muốn.

Thông điệp phù hợp còn phải **không rò rỉ** mật khẩu, token, câu SQL, chi tiết nội bộ hay stack trace vào HTTP response. Test tầng web nên xác minh mã/status/body công khai thay vì sao chép nguyên thông điệp của exception hạ tầng.

## 4. Kiểm tra cause: lỗi cấp cao có giữ được nguồn gốc không?

Java hỗ trợ *exception chaining*: một exception mới có thể lưu exception ban đầu qua constructor `super(message, cause)`. Đây là cách giữ thông tin cho logging và chẩn đoán nhưng vẫn đưa ra domain exception dễ hiểu cho người gọi.

```java
try {
    return Integer.parseInt(raw);
} catch (NumberFormatException cause) {
    throw new InvalidQuantityException(
            "Số lượng phải là số nguyên", cause);
}
```

Đoạn trên là **trích đoạn logic bọc lỗi**; phần 5 có service đầy đủ. Khi `raw="abc"`, lớp bên ngoài là `InvalidQuantityException`, còn `getCause()` của nó là `NumberFormatException`.

Assertion phù hợp:

```java
InvalidQuantityException error = assertThrowsExactly(
        InvalidQuantityException.class,
        () -> service.parse("abc")
);
assertEquals("Số lượng phải là số nguyên", error.getMessage());
assertInstanceOf(NumberFormatException.class, error.getCause());
```

`assertInstanceOf` xác nhận cause có loại mong đợi, kể cả subclass (nếu có). Nếu chính xác class là hợp đồng bắt buộc, có thể so `error.getCause().getClass()` sau khi đã kiểm tra khác `null`. Không nên đòi message nguyên văn của `NumberFormatException`, vì đó là chi tiết của Java runtime.

Một exception có thể có nhiều lớp nguyên nhân:

```text
OrderWorkflowException
    Caused by: QuantityMappingException
        Caused by: NumberFormatException
```

Khi tầng cao bọc lỗi nhiều lần, cần kiểm tra **đúng cấp**. `getCause()` trả cause trực tiếp, không tự tìm đến root cause. Kiểm tra chuỗi cause chỉ khi contract thực sự cam kết việc bọc; không ép test phụ thuộc quá sâu vào tên exception nội bộ của framework.

`getSuppressed()` là một quan hệ khác với `getCause()`: trong một số tình huống `try-with-resources`, lỗi đóng tài nguyên có thể bị ghi dưới dạng *suppressed exception*. Đừng gọi `getCause()` rồi kết luận mọi lỗi phát sinh đã được phản ánh trong đó.

## 5. Ví dụ hoàn chỉnh: kiểm tra lỗi nghiệp vụ và hợp đồng HTTP của Spring Boot

Dự án ví dụ dùng Java 17+, Spring Boot 3.3.5, JUnit Jupiter và Gradle Groovy DSL. Tình huống: endpoint nhận chuỗi `raw` biểu diễn số lượng cần đặt. Quy tắc nghiệp vụ được định nghĩa **trước khi viết test**:

1. `raw` là `null`, rỗng hoặc chỉ gồm khoảng trắng: từ chối với `InvalidQuantityException`, message `Số lượng là bắt buộc`. Lỗi này được phát hiện trực tiếp, **không yêu cầu cause**.
2. `raw` không biểu diễn được số nguyên `int` của Java (như `abc`, `1.5`, số vượt khoảng `int`): từ chối với `InvalidQuantityException`, message `Số lượng phải là số nguyên`, **cause là `NumberFormatException`**.
3. Giá trị parse được nhưng `<= 0`: từ chối với `InvalidQuantityException`, message `Số lượng phải lớn hơn 0`, không yêu cầu cause.
4. Giá trị nguyên dương hợp lệ: trả về đúng số lượng, không phát exception.
5. Với endpoint HTTP, lỗi `InvalidQuantityException` được đổi thành **HTTP 400** với JSON có `code="INVALID_QUANTITY"` và `message` phù hợp. Response không chứa cause hoặc stack trace.

Đây là hợp đồng dành cho bài học, không phải hành vi mặc định của mọi Spring Boot API. Ví dụ dùng `Integer.parseInt` nên chuỗi có khoảng trắng thừa như `" 12 "` bị xem là không đúng định dạng; nếu hệ thống cần chấp nhận, phải bổ sung quy tắc trim và test tương ứng.

### 5.1. Bố cục dự án

```text
settings.gradle
build.gradle
src/main/java/com/example/exceptionassertion/ExceptionAssertionApplication.java
src/main/java/com/example/exceptionassertion/InvalidQuantityException.java
src/main/java/com/example/exceptionassertion/QuantityService.java
src/main/java/com/example/exceptionassertion/QuantityController.java
src/main/java/com/example/exceptionassertion/QuantityExceptionHandler.java
src/test/java/com/example/exceptionassertion/QuantityServiceTest.java
src/test/java/com/example/exceptionassertion/QuantityHttpTest.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'exception-assertion'
```

**`build.gradle`**

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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Cần JDK 17 và Gradle Wrapper tương thích đã được tạo trong dự án; `spring-boot-starter-test` cung cấp các phụ thuộc test cơ bản gồm JUnit Jupiter, Spring Test và các thư viện assertion thường gặp.

**`src/main/java/com/example/exceptionassertion/ExceptionAssertionApplication.java`**

```java
package com.example.exceptionassertion;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ExceptionAssertionApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExceptionAssertionApplication.class, args);
    }
}
```

**`src/main/java/com/example/exceptionassertion/InvalidQuantityException.java`**

```java
package com.example.exceptionassertion;

public class InvalidQuantityException extends RuntimeException {
    public InvalidQuantityException(String message) {
        super(message);
    }

    public InvalidQuantityException(String message, Throwable cause) {
        super(message, cause);
    }
}
```

Constructor một tham số dành cho lỗi được phát hiện trực tiếp. Constructor hai tham số giữ được exception gốc: `super(message, cause)` giúp các assertion về `getCause()` có ý nghĩa. Không nên chỉ đưa `cause.getMessage()` vào message rồi vứt bỏ cause.

**`src/main/java/com/example/exceptionassertion/QuantityService.java`**

```java
package com.example.exceptionassertion;

import org.springframework.stereotype.Service;

@Service
public class QuantityService {
    public int parse(String raw) {
        if (raw == null || raw.isBlank()) {
            throw new InvalidQuantityException("Số lượng là bắt buộc");
        }

        final int quantity;
        try {
            quantity = Integer.parseInt(raw);
        } catch (NumberFormatException cause) {
            throw new InvalidQuantityException(
                    "Số lượng phải là số nguyên", cause);
        }

        if (quantity <= 0) {
            throw new InvalidQuantityException("Số lượng phải lớn hơn 0");
        }

        return quantity;
    }
}
```

`String.isBlank()` có trên Java 11+, vì vậy dùng được với Java 17. Đầu vào `null` được kiểm tra trước nhờ toán tử `||` short-circuit. `Integer.parseInt` phát `NumberFormatException` khi chuỗi không phù hợp hoặc vượt khoảng `int`. Trường hợp `0` hay `-2` vẫn parse được, nên exception của chúng là **lỗi quy tắc nghiệp vụ** chứ không phải lỗi parsing; do đó `cause` là `null`.

**`src/main/java/com/example/exceptionassertion/QuantityController.java`**

```java
package com.example.exceptionassertion;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class QuantityController {
    private final QuantityService service;

    public QuantityController(QuantityService service) {
        this.service = service;
    }

    @GetMapping("/api/quantities/parse")
    public ParsedQuantity parse(@RequestParam("raw") String raw) {
        return new ParsedQuantity(service.parse(raw));
    }

    public record ParsedQuantity(int value) {
    }
}
```

Controller gọi service và trả JSON `{"value":12}` với input hợp lệ. Khi service phát `InvalidQuantityException`, exception đi qua Spring MVC tới handler ở phần tiếp theo.

**`src/main/java/com/example/exceptionassertion/QuantityExceptionHandler.java`**

```java
package com.example.exceptionassertion;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class QuantityExceptionHandler {
    @ExceptionHandler(InvalidQuantityException.class)
    public ResponseEntity<ApiError> handleInvalidQuantity(
            InvalidQuantityException exception) {
        return ResponseEntity.badRequest().body(
                new ApiError("INVALID_QUANTITY", exception.getMessage()));
    }

    public record ApiError(String code, String message) {
    }
}
```

`@RestControllerAdvice` làm cho exception được **xử lý** thành response HTTP. Vì vậy `MockMvc.perform(...)` với `raw=abc` dự kiến nhận status `400` và JSON phù hợp, thay vì tự động ném `InvalidQuantityException` trực tiếp ra cho test. Với lỗi thiếu hẳn query parameter `raw`, Spring MVC có thể xử lý bằng lỗi binding `MissingServletRequestParameterException`; ví dụ này **chỉ** cấu hình handler cho `InvalidQuantityException`, không cam kết JSON `INVALID_QUANTITY` cho mọi lỗi 400.

### 5.2. Unit test kiểm tra đúng loại, message và cause

**`src/test/java/com/example/exceptionassertion/QuantityServiceTest.java`**

```java
package com.example.exceptionassertion;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.NullAndEmptySource;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertThrowsExactly;

class QuantityServiceTest {
    private final QuantityService service = new QuantityService();

    @Test
    void acceptsPositiveInteger() {
        int actual = assertDoesNotThrow(() -> service.parse("12"));
        assertEquals(12, actual);
    }

    @ParameterizedTest
    @ValueSource(strings = {"abc", "1.5", "2147483648"})
    void wrapsInvalidNumberWithOriginalCause(String raw) {
        InvalidQuantityException exception = assertThrowsExactly(
                InvalidQuantityException.class,
                () -> service.parse(raw));

        assertAll(
                "invalid quantity parsing",
                () -> assertEquals(
                        "Số lượng phải là số nguyên", exception.getMessage()),
                () -> assertInstanceOf(
                        NumberFormatException.class, exception.getCause())
        );
    }

    @ParameterizedTest
    @NullAndEmptySource
    @ValueSource(strings = {" ", "   "})
    void rejectsAbsentQuantityWithoutTechnicalCause(String raw) {
        InvalidQuantityException exception = assertThrowsExactly(
                InvalidQuantityException.class,
                () -> service.parse(raw));

        assertEquals("Số lượng là bắt buộc", exception.getMessage());
        assertNull(exception.getCause());
    }

    @ParameterizedTest
    @ValueSource(strings = {"0", "-2"})
    void rejectsNonPositiveQuantityWithoutTechnicalCause(String raw) {
        InvalidQuantityException exception = assertThrowsExactly(
                InvalidQuantityException.class,
                () -> service.parse(raw));

        assertEquals("Số lượng phải lớn hơn 0", exception.getMessage());
        assertNull(exception.getCause());
    }
}
```

Điểm cần đọc trong test:

- `assertThrowsExactly` khóa loại exception theo yêu cầu domain; kết quả trả về được giữ lại để xác minh message/cause.
- `assertAll` gom các assertion liên quan đến **cùng một exception**. Nếu một kiểm tra fail, JUnit vẫn có thể thực thi các kiểm tra còn lại trong nhóm và báo nhiều failure cùng lúc; nó không làm exception “đúng” chỉ nhờ một assertion xanh.
- `assertInstanceOf(NumberFormatException.class, exception.getCause())` chứng minh việc bọc lỗi giữ đúng loại cause, nhưng không phụ thuộc câu chữ có thể thay đổi của JDK.
- `assertNull(exception.getCause())` là yêu cầu **của ví dụ này** đối với lỗi validation được phát hiện trực tiếp; không phải mọi domain exception đều bắt buộc không có cause.
- `@ParameterizedTest` thử nhiều dữ liệu đại diện cho cùng một quy tắc; các input khác nhau như chữ, số thập phân và số vượt `int` đều phải dẫn đến đúng contract.

Từng test tạo `QuantityService` trực tiếp, vì vậy đây là **unit test** cho logic Java, chưa chứng minh Spring wiring, controller mapping hay HTTP exception handling. Việc class service có `@Service` không làm unit test tự khởi tạo Spring context.

### 5.3. Test Spring Boot qua MockMvc: kiểm tra lỗi đã được xử lý thành HTTP

**`src/test/java/com/example/exceptionassertion/QuantityHttpTest.java`**

```java
package com.example.exceptionassertion;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class QuantityHttpTest {
    @Autowired
    private MockMvc mockMvc;

    @Test
    void convertsDomainExceptionIntoClientError() throws Exception {
        mockMvc.perform(get("/api/quantities/parse")
                        .param("raw", "abc"))
                .andExpect(status().isBadRequest())
                .andExpect(content().contentTypeCompatibleWith(
                        MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.code").value("INVALID_QUANTITY"))
                .andExpect(jsonPath("$.message")
                        .value("Số lượng phải là số nguyên"));
    }

    @Test
    void returnsParsedValueOnSuccess() throws Exception {
        mockMvc.perform(get("/api/quantities/parse")
                        .param("raw", "12"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.value").value(12));
    }

    @Test
    void rejectsMissingRequestParameter() throws Exception {
        mockMvc.perform(get("/api/quantities/parse"))
                .andExpect(status().isBadRequest());
    }
}
```

`@SpringBootTest` tải application context của ví dụ; `@AutoConfigureMockMvc` cấp `MockMvc` để thực thi pipeline Spring MVC theo dạng mô phỏng request/response, **không mở HTTP server thực trên một cổng mạng**. Hai test đầu kiểm tra controller, handler và response. Test thứ ba chỉ kiểm tra status 400 từ cơ chế binding khi thiếu `raw`; nó không giả định response đó cũng có `INVALID_QUANTITY`.

Trong một API có chuẩn hóa lỗi riêng (ví dụ `ProblemDetail` theo RFC 9457 hoặc schema doanh nghiệp), assertion phải dựa trên **hợp đồng mà API thực sự công bố**. Khi handler đã chuyển exception thành `ResponseEntity`, một `assertThrows(InvalidQuantityException.class, () -> mockMvc.perform(...))` có thể sai mục tiêu: exception đã được xử lý nên biểu hiện cần kiểm tra ở tầng này là **HTTP response**. Muốn kiểm tra exception Java gốc, dùng unit/service test hoặc truy cập dữ liệu resolved exception nếu đúng mục đích.

### 5.4. Chạy và diễn giải kết quả

Từ thư mục dự án có Gradle Wrapper, dùng:

```bash
./gradlew test
./gradlew test --tests com.example.exceptionassertion.QuantityServiceTest
./gradlew test --tests com.example.exceptionassertion.QuantityHttpTest
./gradlew bootRun
```

Trên Windows, dùng `gradlew.bat` thay `./gradlew`. Lệnh `test` chạy JUnit tests; `bootRun` khởi chạy ứng dụng. Nếu chưa tạo Gradle Wrapper, cần tạo bằng bản Gradle tương thích Spring Boot 3.3.x trước khi dùng các lệnh wrapper.

Với code chưa sửa và cấu hình tương ứng, **kỳ vọng** các test đều PASS. Đây là kỳ vọng suy ra từ code, **không phải log thực thi đã được quan sát**. Không có stdout cố định cho Gradle vì output phụ thuộc bản Gradle, cache và môi trường.

Khi ứng dụng chạy ở cổng 8080 mặc định, có thể quan sát HTTP bằng:

```bash
curl -i "http://localhost:8080/api/quantities/parse?raw=abc"
curl -i "http://localhost:8080/api/quantities/parse?raw=12"
```

Với request lỗi, kỳ vọng **status 400** và body JSON tương đương `{"code":"INVALID_QUANTITY","message":"Số lượng phải là số nguyên"}`; với request hợp lệ, kỳ vọng status 200 và body JSON `{"value":12}`. Header/thứ tự khóa JSON có thể khác theo runtime; không assert toàn bộ response raw text chỉ vì thứ tự serialization khác nhau.

### 5.5. Thí nghiệm để kiểm chứng assertion thật sự bắt được lỗi

Trong **bản thử nghiệm**, bỏ tham số `cause` khi bọc exception:

```java
} catch (NumberFormatException cause) {
    throw new InvalidQuantityException("Số lượng phải là số nguyên");
}
```

Giữ nguyên message. Unit test `wrapsInvalidNumberWithOriginalCause` sẽ FAIL tại assertion về `getCause()`, dù loại exception và message vẫn đúng. Thí nghiệm này chỉ ra vì sao không nên dừng ở `assertThrows`.

Tiếp theo, đổi message domain từ `"Số lượng phải là số nguyên"` thành `"Số lượng không hợp lệ"`. Test so sánh message sẽ FAIL; HTTP test cũng FAIL tại `jsonPath("$.message")`. Nếu thông điệp là hợp đồng được cam kết, đây là lỗi cần phát hiện. Nếu hợp đồng chỉ cam kết `code`, cân nhắc bỏ assertion cố định về câu chữ ở tầng HTTP để tránh test dễ vỡ khi cải tiến nội dung hiển thị. Sau thí nghiệm, hoàn nguyên code.

## 6. Những tình huống dễ viết assertion sai

### 6.1. Bọc nhiều câu lệnh trong cùng `assertThrows`

```java
assertThrows(RuntimeException.class, () -> {
    int value = Integer.parseInt("not-a-number");
    service.parse(Integer.toString(value));
});
```

Test trên **xanh vì `NumberFormatException`** từ bước chuẩn bị input, trước khi `service.parse` được gọi. Assertion rộng và vùng lambda rộng làm test khẳng định nhầm chức năng. Thay vào đó, hãy chuẩn bị input bên ngoài (nếu cần) và chỉ đặt **thao tác mục tiêu** trong lambda:

```java
String input = "0";
InvalidQuantityException error = assertThrowsExactly(
        InvalidQuantityException.class,
        () -> service.parse(input));
assertEquals("Số lượng phải lớn hơn 0", error.getMessage());
```

Hai đoạn trên là **trích đoạn dùng khi đã có biến `service` và import JUnit thích hợp**, không phải chương trình Java độc lập.

### 6.2. Bắt `Exception` hoặc `RuntimeException` quá rộng

```java
assertThrows(RuntimeException.class, () -> service.parse("abc"));
```

Nếu code bị đổi thành truy cập một đối tượng `null` và phát `NullPointerException`, test vẫn có thể xanh. Hãy chọn domain exception được contract công bố. Với framework hoặc driver được phép phát nhiều subclass hợp lệ, chọn superclass **có chủ đích** và kiểm tra dữ liệu phân biệt quan trọng, thay vì khóa exact class tùy tiện.

### 6.3. Chỉ gọi method nhưng không assert lỗi

```java
@Test
void invalidInput() {
    service.parse("abc");
}
```

Đây không phải test chờ đợi exception. Vì không có `assertThrows`, exception sẽ làm test **thất bại**. Tên test không biến lỗi thành expected behavior. Ngược lại, nếu test tự `try/catch` rồi bỏ qua exception, nó có thể xanh mà không kiểm tra đúng loại; dùng JUnit assertion sẽ rõ hơn.

### 6.4. Kiểm tra message của tầng nội bộ quá chi tiết

Với `NumberFormatException`, message có thể chứa chính chuỗi input hoặc cách diễn đạt của JDK. Đừng viết test dựa trên nội dung đó nếu chỉ cần biết parse thất bại; hãy kiểm tra `NumberFormatException` là cause và **thông điệp ứng dụng** do service tự định nghĩa.

Nếu error response đã chuẩn hóa thành `code` và `message`, client nên ưu tiên `code` ổn định để xử lý nhánh chương trình. Câu chữ có thể do UI localization quyết định; assertion exact message chỉ phù hợp khi API thực sự bảo đảm câu chữ ấy.

### 6.5. Nhầm `getCause()` với loại exception đã được ném

Với ví dụ parse `abc`:

```text
Exception được ném ra: InvalidQuantityException
exception.getCause(): NumberFormatException
exception.getMessage(): "Số lượng phải là số nguyên"
```

`assertThrows(NumberFormatException.class, () -> service.parse("abc"))` sẽ **FAIL** vì NumberFormatException đã được bắt và bọc. Phép test đúng thường assert outer exception là `InvalidQuantityException`, rồi assert cause là `NumberFormatException`.

Nếu hệ thống cố ý cho exception hạ tầng đi xuyên lên, đó là hợp đồng khác cần test khác. Không tự suy đoán một exception Java cấp thấp luôn phải là exception cuối cùng người gọi nhìn thấy.

## 7. Exception trong code bất đồng bộ và các lớp wrapper

Với `CompletableFuture`, exception của tác vụ có thể xuất hiện qua một lớp wrapper khi gọi `join()`. Ví dụ **trích đoạn dành cho test có `service`**:

```java
CompletableFuture<Integer> future =
        CompletableFuture.supplyAsync(() -> service.parse("abc"));

CompletionException asyncFailure = assertThrows(
        CompletionException.class,
        future::join);

InvalidQuantityException domainFailure = assertInstanceOf(
        InvalidQuantityException.class,
        asyncFailure.getCause());
assertInstanceOf(
        NumberFormatException.class,
        domainFailure.getCause());
```

Trong trích đoạn trên cần import `java.util.concurrent.CompletableFuture`, `java.util.concurrent.CompletionException` và JUnit assertions; đây là đoạn bổ sung, không phải tệp độc lập. Cần gọi `join()` **bên trong** vùng được assert: chỉ khởi tạo future không bảo đảm exception của tác vụ được phát ra ở thread gọi test. `Future.get()` có thể phát `ExecutionException`; quy tắc wrapper phụ thuộc API đồng bộ hóa đã dùng.

Đối với Spring async, event listener, reactive stream hoặc message consumer, lời gọi tạo tác vụ thành công chưa chứng minh tác vụ bên trong thành công. Test cần **quan sát điểm hoàn tất hoặc tín hiệu lỗi thực tế** theo hợp đồng của cơ chế đó, rồi kiểm tra outer exception và cause ở tầng phù hợp. Không tùy tiện khẳng định mọi framework đều bọc lỗi bằng một loại exception giống nhau.

## 8. Checked exception, custom exception và lớp HTTP

Java phân biệt checked exception (như `IOException`) với unchecked exception (`RuntimeException` và subclass). Cả hai đều có thể được kiểm tra với `assertThrows` vì lambda `Executable` của JUnit được phép ném `Throwable`. Điều quan trọng là hợp đồng thực tế: method có thể khai báo `throws IOException`, còn HTTP controller có thể xử lý lỗi đó rồi trả status thay vì ném nó ra ngoài.

| Vị trí test | Assertion nên ưu tiên | Vì sao |
| --- | --- | --- |
| Java parser/service validation | `assertThrowsExactly`/ `assertThrows`, message, cause, state | Quan sát trực tiếp Java exception |
| Repository/integration service | Loại lỗi đã chuẩn hóa và transaction/data state | Exception wrapper của DB có thể thay đổi; rollback cần được quan sát |
| Spring MVC với `@RestControllerAdvice` | `MockMvc`: status, error code, JSON fields | Exception được handler chuyển thành HTTP |
| HTTP qua web server thật | HTTP client: status, body, side effects | Kiểm tra điểm nhìn của client ngoài tiến trình |
| Async/future | Kết quả `join()`/`get()`, wrapper và cause | Lỗi có thể xảy ra ngoài thời điểm gọi ban đầu |

**Không mặc định mọi exception HTTP nên trả 400.** Validation input thường tương ứng 400; xung đột trạng thái có thể cần 409; không tìm thấy resource có thể cần 404; lỗi server thật sự thường cần 5xx. Quyết định dựa vào API contract. Đối với `InvalidQuantityException` của ví dụ, handler đã định nghĩa rõ 400.

Trong ứng dụng thật, logging nên giữ stack trace và cause cho chẩn đoán nội bộ khi phù hợp, nhưng response gửi client chỉ tiết lộ thông tin cần thiết. Kiểm thử tốt bảo vệ cả hai: **cause không bị mất trong service** và **chi tiết nội bộ không bị lộ ra response**.

## 9. Nên assert những gì và không nên assert những gì?

Có thể dùng ma trận sau khi review một test về lỗi:

| Trường hợp | Assertion tối thiểu có ý nghĩa | Nên bổ sung nếu có trong hợp đồng |
| --- | --- | --- |
| Dữ liệu thiếu | Domain exception chính xác, message hoặc error code | Không có tác động dữ liệu; cause `null` nếu yêu cầu |
| Không parse được input | Domain exception và cause loại `NumberFormatException` | Message hướng dẫn người dùng; giữ input ở nơi an toàn |
| Vi phạm quy tắc nghiệp vụ | Domain exception hoặc subclass được phép | Mã lỗi, field lỗi, giá trị ngưỡng, state không đổi |
| Thất bại hạ tầng được bọc | Exception ứng dụng và cause gốc | Retryability, transaction rollback, logging context |
| Exception đã được Spring MVC xử lý | HTTP status và JSON code | Content-Type, message công khai, không rò stack trace |
| Đường xử lý hợp lệ | `assertDoesNotThrow` và kết quả đúng | Side effects và trạng thái hệ thống |

Khi **một quy tắc có nhiều nhánh lỗi**, nên kiểm thử từng nhánh. `raw=null` khác `raw="abc"`: trường hợp đầu phát exception không có cause, trường hợp sau bắt lỗi parsing có cause. Nếu chỉ viết một test cho “input không hợp lệ”, bạn có thể bỏ sót việc một nhánh ném `NullPointerException` hoặc quên bọc `NumberFormatException`.

### Có nên assert stack trace không?

Thông thường **không nên so sánh toàn bộ stack trace**: dòng nguồn, proxy, JIT, framework và cấu hình có thể thay đổi. Khi cần kiểm tra nguồn gốc, giữ `cause`, class/código error và dữ liệu bền vững. Lỗi tải từ cơ sở dữ liệu có thể khác theo database/driver; test business contract qua mã lỗi nghiệp vụ thay vì so exception vendor chi tiết.

### Có nên assert message chính xác ở mọi nơi không?

Không. Exact message hợp lý khi code và contract do nhóm sở hữu, ví dụ `"Số lượng là bắt buộc"`. Với thư viện bên ngoài hoặc thông điệp đã được localization, hãy chọn type, mã lỗi hoặc các trường cấu trúc ổn định. Nếu đặc tả yêu cầu câu chữ hiển thị chính xác cho người dùng, assert câu chữ đó ở đúng tầng UI/API, có xét ngôn ngữ đang cấu hình.

## 10. Quy trình viết test exception có giá trị

1. **Ghi rõ hợp đồng lỗi.** Với đầu vào nào phải từ chối? Loại exception gì? Message hoặc error code nào? Có giữ cause không? Có thay đổi dữ liệu trước khi thất bại không?
2. **Chuẩn bị dữ liệu bên ngoài lambda.** Đặt đúng lời gọi mục tiêu vào `assertThrows`/ `assertThrowsExactly`, tránh lỗi setup vô tình được tính là thành công.
3. **Chọn độ chặt của loại exception.** Exact class khi quan trọng; subclass khi hợp đồng cho phép. Không dùng loại quá rộng chỉ để xanh.
4. **Kiểm tra ngoại lệ đã bắt.** So `getMessage()` khi ổn định, `getCause()` khi có yêu cầu bảo toàn, và invariant/trạng thái sau thất bại khi phù hợp.
5. **Kiểm tra tầng được phơi bày ra ngoài.** Nếu Spring xử lý exception, dùng `MockMvc` hoặc HTTP client để assert status/code/body, không mặc định exception vẫn được ném trực tiếp.
6. **Thử phản chứng.** Tạm bỏ `cause`, đổi thông điệp hoặc đổi loại exception trong nhánh lỗi; một test thiết kế tốt cần báo đỏ ở assertion tương ứng.
7. **Chạy riêng test và chạy toàn bộ suite.** Phân biệt lỗi setup, dependency, state leak, transaction và assertion. Một lần test xanh không bao phủ mọi trường hợp chưa được thử.

## 11. Bài tập tự kiểm tra

**Bài A:** Với `service.parse("abc")`, `assertThrows(NumberFormatException.class, ...)` có đúng không? **Không**: service đã bọc `NumberFormatException` bên trong `InvalidQuantityException`. Cần assert outer exception rồi kiểm tra cause.

**Bài B:** Với `service.parse("0")`, vì sao assert `getCause() == null` hợp lý trong ví dụ? Vì lỗi là **vi phạm quy tắc số lượng dương** được xác định trực tiếp, không bắt exception hạ tầng. Đây là một phần của hợp đồng ví dụ, không phải quy luật áp cho mọi domain exception.

**Bài C:** Test chỉ viết `assertThrows(RuntimeException.class, () -> service.parse("abc"))` có phát hiện nếu code đổi thành ném `NullPointerException` không? **Không chắc**: `NullPointerException` cũng là `RuntimeException` nên có thể bị chấp nhận. Cần exception cụ thể và kiểm tra cause/message quan trọng.

**Bài D:** `MockMvc` nhận status 400 và JSON `INVALID_QUANTITY`; có nên viết thêm `assertThrows(InvalidQuantityException.class, () -> mockMvc.perform(...))` không? **Không cho kịch bản đã được advice xử lý.** Ở đây hợp đồng được thể hiện ở response. Kiểm tra exception Java trực tiếp tại service test.

**Bài E:** Future chạy `service.parse("abc")` bất đồng bộ; chỉ tạo future rồi test kết thúc có chứng minh lỗi đã được quan sát không? **Không.** Phải chờ và quan sát kết quả thông qua `join()`, `get()` hoặc cơ chế phù hợp, rồi kiểm tra wrapper/cause.

### Checklist trước khi kết luận một test exception đạt yêu cầu

- Đã kiểm tra đúng **loại exception**, có xét chính xác type so với subclass?
- Lambda trong `assertThrows` có chỉ chứa **thao tác phải gây lỗi**, tránh sai từ setup?
- Message được so theo phần nào thực sự là **hợp đồng ổn định**?
- Khi có wrapping, `getCause()` có loại và chuỗi nguyên nhân đúng?
- Với lỗi nghiệp vụ trực tiếp, test có tránh giả định luôn tồn tại cause?
- Có dữ liệu test cho **từng nhánh lỗi** (thiếu, sai định dạng, sai quy tắc, vượt ngưỡng)?
- Có assertion rằng dữ liệu/trạng thái không bị thay đổi sau khi lỗi, nếu nghiệp vụ yêu cầu?
- Với REST API, status, mã lỗi, JSON body và dữ liệu không được lộ đã được kiểm tra ở tầng HTTP?
- Test có báo đỏ nếu cố tình đổi **loại lỗi, cause hoặc thông điệp** mà hợp đồng bảo vệ?

**Điểm cần nhớ:** một assertion về exception tốt kiểm chứng **đúng lỗi, đúng nguyên nhân, đúng thông tin cần công bố**. JUnit Jupiter giúp kiểm tra `Throwable` ở tầng Java; Spring Boot test còn phải kiểm tra cách lỗi được chuyển thành hợp đồng HTTP. Khi kết hợp các phép kiểm đúng phạm vi, test phát hiện được cả lỗi nghiệp vụ lẫn lỗi xử lý/biểu diễn exception.
