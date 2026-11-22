# setAdaptConstraintViolations và kết quả kiểm tra được thích nghi

## 1. Mục tiêu của tính năng

Trong Spring Framework, method validation cho phép kiểm tra ràng buộc Jakarta Bean Validation ngay trên **tham số và giá trị trả về của phương thức**, đặc biệt là phương thức public trên Spring bean được đánh dấu `@Validated` và được gọi qua proxy. Ví dụ:

```java
@NotBlank
public String create(@NotBlank String code, @Min(1) int count) {
    return "created:" + code + ":" + count;
}
```

Đoạn trên khai báo hai *tiền điều kiện* cho tham số và một *hậu điều kiện* cho giá trị trả về. Với hạ tầng `MethodValidationPostProcessor` và provider Jakarta Validation được thiết lập đúng, Spring AOP có thể từ chối lời gọi trước khi chạy method body nếu tham số sai, hoặc phát hiện kết quả không hợp lệ sau khi method body đã chạy.

Mặc định, khi validation thất bại, interceptor ném `jakarta.validation.ConstraintViolationException` mang các `ConstraintViolation<?>` của provider. Từ Spring Framework **6.1**, có lựa chọn khác: cấu hình `MethodValidationPostProcessor#setAdaptConstraintViolations(true)` để chuyển các violation thành **kết quả có cấu trúc theo mô hình lỗi của Spring** và ném `org.springframework.validation.method.MethodValidationException`.

Mục đích là xử lý lỗi theo **phương thức / tham số / thuộc tính con**, thuận tiện cho `MessageSource`, quốc tế hóa, chuẩn hóa lỗi trong service và tái sử dụng API của Spring Validation. **Bật cờ không sửa quy tắc constraint, không tự tạo validation cho bean chưa được proxy và không tự quyết định HTTP status.**

## 2. So sánh hai chế độ

| Khía cạnh | Mặc định: `false` | Thích nghi: `true` |
| --- | --- | --- |
| Nơi cấu hình | `MethodValidationPostProcessor#setAdaptConstraintViolations(false)` hoặc không đặt | `MethodValidationPostProcessor#setAdaptConstraintViolations(true)` |
| Exception khi có lỗi | `jakarta.validation.ConstraintViolationException` | `org.springframework.validation.method.MethodValidationException` |
| Dạng dữ liệu | `Set<ConstraintViolation<?>>` từ Bean Validation | `MethodValidationResult` và các `ParameterValidationResult` |
| Tổ chức lỗi | Mỗi violation có metadata/path riêng | Gom theo tham số hoặc vị trí giá trị trả về, có lỗi lồng nhau |
| Nguồn mô tả lỗi | `ConstraintViolation#getMessage()`, `getPropertyPath()`, `getConstraintDescriptor()` | `MessageSourceResolvable` với error codes, arguments và default message |
| Lỗi khi `@Valid` duyệt vào DTO | Violation với đường dẫn thuộc tính | `ParameterErrors` triển khai `Errors`, có `FieldError` |
| Mục tiêu phù hợp | Code đã dựa trên Jakarta API hoặc cần chi tiết thô | Tích hợp `MessageSource` và xử lý lỗi nhất quán theo Spring |
| Hợp đồng bắt lỗi | `catch (ConstraintViolationException ex)` | `catch (MethodValidationException ex)` |

**Không có chế độ nào “chính xác hơn” về constraint.** Cả hai đều dựa trên một Bean Validation provider. Khác biệt chủ yếu ở cách các violation được biểu diễn và exception bị ném. Nếu ứng dụng đổi cờ, handler/test đang bắt `ConstraintViolationException` phải được cập nhật để hiểu `MethodValidationException`.

## 3. Bật cờ đúng chỗ trong Spring

### 3.1. Spring Framework thuần: đăng ký post-processor

Trong Spring context đã có Jakarta Bean Validation provider, có thể khai báo:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.MethodValidationPostProcessor;

@Configuration
public class MethodValidationConfiguration {

    @Bean
    public static MethodValidationPostProcessor methodValidationPostProcessor() {
        MethodValidationPostProcessor processor =
                new MethodValidationPostProcessor();
        processor.setAdaptConstraintViolations(true);
        return processor;
    }
}
```

Đây là **đoạn cấu hình cần đặt vào ứng dụng Spring**, không phải một chương trình chạy độc lập. Phương thức `@Bean static` giúp đăng ký `BeanPostProcessor` sớm, không cần khởi tạo config instance trước. Lớp service đích vẫn cần `@Validated` trên type và các constraint phù hợp. Khi Spring tạo bean, `MethodValidationPostProcessor` gắn AOP advisor cho bean đủ điều kiện.

### 3.2. Spring Boot: tránh tạo post-processor trùng

Spring Boot có thể tự cấu hình method validation khi tìm thấy Jakarta Validation provider, ví dụ thông qua `spring-boot-starter-validation`. Nếu cần bật chế độ thích nghi, bạn phải **tùy biến đúng `MethodValidationPostProcessor` đang áp dụng cho các bean**, chẳng hạn cung cấp định nghĩa bean riêng như trên theo cơ chế auto-configuration của phiên bản Boot đang dùng.

Không tạo thêm nhiều post-processor mà không biết bean nào xử lý phương thức: advice có thể bị áp dụng chồng hoặc làm kết quả chẩn đoán khó hiểu. Với ứng dụng đang tùy biến validator/factory, cần giữ đúng provider và các nhóm validation hiện có. Cờ này là cấu hình cho **method-validation interceptor**, không phải thuộc tính của `@Validated` hay từng `@NotNull`.

### 3.3. Điều kiện hạ tầng vẫn giữ nguyên

Cờ chỉ có hiệu lực nếu:

1. Có Jakarta Bean Validation provider (ví dụ Hibernate Validator) cùng hạ tầng Spring Validation.
2. Bean được Spring quản lý và đủ điều kiện theo `@Validated` ở cấp type.
3. Lời gọi đi qua Spring AOP proxy tới phương thức có thể được advise.
4. Có constraint trên tham số/return value hoặc cascade qua `@Valid` đúng ngữ cảnh và group.

Việc gọi `new MyService()`, self-invocation bằng `this.method()` hoặc lời gọi vào private/final method không thể được proxy advise sẽ không trở thành method validation chỉ nhờ cờ `true`.

## 4. Luồng chuyển đổi từ ConstraintViolation sang lỗi Spring

Ở mức ý tưởng, khi method bị gọi qua proxy:

```text
Caller
  │
  ▼
Spring AOP / MethodValidationInterceptor
  │
  ├── Trước method body: validateParameters(...)
  │      ├── không vi phạm → thực thi method
  │      └── có vi phạm:
  │             ├── adapt=false → ConstraintViolationException
  │             └── adapt=true  → MethodValidationResult
  │                                → MethodValidationException
  │
  ├── Method body chạy và trả về
  │
  └── Sau method body: validateReturnValue(...)
         ├── không vi phạm → trả kết quả cho caller
         └── có vi phạm: xử lý lỗi theo cùng cờ cấu hình
```

Khi thích nghi, Spring sử dụng cơ chế như `MethodValidationAdapter` để ánh xạ các `ConstraintViolation` sang lỗi theo mô hình Spring Validation. Những lớp quan trọng nằm ở package `org.springframework.validation.method`:

- **`MethodValidationResult`:** giao diện biểu diễn kết quả cho một lần validation; cung cấp target, method, thông tin đó là lỗi tham số hay return value, các nhóm lỗi và thông tin cross-parameter.
- **`MethodValidationException`:** exception chứa kết quả trên; có thể gọi trực tiếp những API của `MethodValidationResult`.
- **`ParameterValidationResult`:** gom lỗi trực tiếp cho một tham số (hoặc vị trí return value), có metadata `MethodParameter`, giá trị liên quan và danh sách `MessageSourceResolvable`.
- **`ParameterErrors`:** subclass của `ParameterValidationResult` đồng thời triển khai `org.springframework.validation.Errors`; dành cho lỗi thuộc tính lồng nhau khi cascade bằng `@Valid`.
- **`MessageSourceResolvable`:** mang các error code theo mức ưu tiên, arguments và default message để một `MessageSource` chọn thông báo phù hợp với locale.
- **`FieldError`:** lỗi cụ thể trên property của đối tượng bên trong, ví dụ trường `address.street`, có thể truy cập qua `ParameterErrors#getFieldErrors()`.

Một method có hai constraint sai trên cùng một tham số **không nhất thiết tạo hai `ParameterValidationResult`**; có thể là một kết quả với hai `MessageSourceResolvable`. Khi tham số là collection/array/map, provider có thể tạo kết quả riêng theo phần tử lỗi, kèm `getContainerIndex()` hoặc `getContainerKey()`.

## 5. Đọc API kết quả: dùng phương thức nào?

Trong **Spring Framework 6.2**, dùng các API hiện hành sau:

| API | Dùng để làm gì |
| --- | --- |
| `ex.getMethod()` | Method được validate |
| `ex.getTarget()` | Bean đích mà advice gọi |
| `ex.isForReturnValue()` | `false`: lỗi trong đầu vào, `true`: lỗi return value |
| `ex.getParameterValidationResults()` | Danh sách kết quả cho tham số/return value |
| `ex.getValueResults()` | Phần lỗi trực tiếp trên giá trị tham số |
| `ex.getBeanResults()` | Phần lỗi nested bean dạng `ParameterErrors` |
| `ex.getCrossParameterValidationResults()` | Lỗi constraint áp dụng cho tổ hợp tham số (nếu có) |
| `ex.getAllErrors()` | Danh sách lỗi đã gộp, kiểu `MessageSourceResolvable` |
| `result.getMethodParameter()` | Metadata vị trí tham số; chỉ số `-1` thường dùng cho return type |
| `result.getArgument()` | Giá trị tham số/return value liên quan; cân nhắc dữ liệu nhạy cảm khi log |
| `result.getResolvableErrors()` | Các lỗi của vị trí đó |
| `result.getContainerIndex()/getContainerKey()` | Chỉ số/key khi lỗi nằm trong container |

**Lưu ý phiên bản:** `getParameterValidationResults()` có từ Spring Framework 6.2. API cũ `getAllValidationResults()` đã bị đánh dấu deprecated trong 6.2; đừng thiết kế code mới trên tên cũ nếu bạn đang dùng 6.2+. Với Spring 6.1, cần đối chiếu tên API tương ứng phiên bản đó trước khi copy code mẫu.

Lỗi trả về vẫn được biểu diễn theo `MethodParameter`, nhưng ngữ nghĩa khác với tham số đầu vào. Dùng `isForReturnValue()` thay vì chỉ đoán từ tên tham số hay chuỗi đường dẫn.

## 6. Ví dụ Java 17 + Spring Framework 6.2.6 có thể chạy

Bài thực hành dùng Spring Framework thuần, không cần web server. Nó tạo một Spring bean có `@Validated`, đăng ký đúng một `MethodValidationPostProcessor` với `adapt=true`, rồi kiểm tra bốn tình huống:

1. Dữ liệu hợp lệ.
2. Hai constraint trực tiếp của hai tham số cùng thất bại.
3. `@Valid` cascade vào trường của một record.
4. Constraint trên return value thất bại.

### 6.1. Cấu trúc

```text
adapted-method-validation/
├── pom.xml
└── src/main/java/demo/AdaptedValidationDemo.java
```

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>demo</groupId>
  <artifactId>adapted-method-validation</artifactId>
  <version>1.0.0</version>
  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-context</artifactId>
      <version>6.2.6</version>
    </dependency>
    <dependency>
      <groupId>org.springframework</groupId>
      <artifactId>spring-aop</artifactId>
      <version>6.2.6</version>
    </dependency>
    <dependency>
      <groupId>org.hibernate.validator</groupId>
      <artifactId>hibernate-validator</artifactId>
      <version>8.0.2.Final</version>
    </dependency>
    <dependency>
      <groupId>org.glassfish</groupId>
      <artifactId>jakarta.el</artifactId>
      <version>4.0.2</version>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
    </plugins>
  </build>
</project>
```

`spring-context` cung cấp ApplicationContext và Spring Validation, `spring-aop` cung cấp hạ tầng proxy, Hibernate Validator là provider Jakarta Validation, còn `jakarta.el` hỗ trợ message interpolation. Dự án sử dụng Java 17 và không phụ thuộc vào Spring Boot auto-configuration.

### 6.3. `AdaptedValidationDemo.java`

```java
package demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.context.MessageSourceResolvable;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.FieldError;
import org.springframework.validation.annotation.Validated;
import org.springframework.validation.beanvalidation.MethodValidationPostProcessor;
import org.springframework.validation.method.MethodValidationException;
import org.springframework.validation.method.ParameterErrors;
import org.springframework.validation.method.ParameterValidationResult;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.function.Supplier;

@Configuration(proxyBeanMethods = false)
public class AdaptedValidationDemo {

    @Bean
    public static MethodValidationPostProcessor methodValidationPostProcessor() {
        MethodValidationPostProcessor processor =
                new MethodValidationPostProcessor();
        processor.setAdaptConstraintViolations(true);
        processor.setProxyTargetClass(true);
        return processor;
    }

    @Bean
    CheckoutService checkoutService() {
        return new CheckoutService();
    }

    public record Address(@NotBlank String street) {
    }

    @Validated
    public static class CheckoutService {

        @NotBlank
        public String issue(@NotBlank String code, @Min(1) int count) {
            return "issued:" + code + ":" + count;
        }

        public String ship(@Valid Address address) {
            return "sent:" + address.street();
        }

        @NotBlank
        public String brokenReceipt(@NotBlank String code) {
            return "";
        }
    }

    private static String lastCode(MessageSourceResolvable error) {
        String[] codes = error.getCodes();
        return (codes == null || codes.length == 0)
                ? "UNKNOWN" : codes[codes.length - 1];
    }

    private static String describe(MethodValidationException exception) {
        List<String> lines = new ArrayList<>();

        for (ParameterValidationResult result
                : exception.getParameterValidationResults()) {

            int index = result.getMethodParameter().getParameterIndex();
            String place = index < 0 ? "return" : "arg" + index;

            for (MessageSourceResolvable error : result.getResolvableErrors()) {
                if (result instanceof ParameterErrors
                        && error instanceof FieldError fieldError) {
                    lines.add(place + "/field:" + fieldError.getField()
                            + "/" + lastCode(error));
                } else {
                    lines.add(place + "/value/" + lastCode(error));
                }
            }
        }

        Collections.sort(lines);
        return "return=" + exception.isForReturnValue()
                + "; " + String.join(", ", lines);
    }

    private static void run(String label, Supplier<String> action) {
        try {
            System.out.println(label + " => " + action.get());
        } catch (MethodValidationException exception) {
            System.out.println(label + " => " + describe(exception));
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(AdaptedValidationDemo.class)) {

            // Lấy reference qua Spring: phương thức được gọi qua AOP proxy.
            CheckoutService service = context.getBean(CheckoutService.class);

            run("VALID", () -> service.issue("A1", 2));
            run("BAD_INPUT", () -> service.issue("", 0));
            run("BAD_NESTED", () -> service.ship(new Address("")));
            run("BAD_RETURN", () -> service.brokenReceipt("A1"));
        }
    }
}
```

### 6.4. Lệnh chạy và output

Tại thư mục chứa `pom.xml`, cài Java 17+ và Maven 3.x, chạy:

```bash
mvn -q compile
mvn -q org.codehaus.mojo:exec-maven-plugin:3.5.1:java -Dexec.mainClass=demo.AdaptedValidationDemo
```

Những dòng **do chương trình tự in** có dạng (không tính log Maven, Spring hoặc Hibernate Validator nếu môi trường có cấu hình log riêng):

```text
VALID => issued:A1:2
BAD_INPUT => return=false; arg0/value/NotBlank, arg1/value/Min
BAD_NESTED => return=false; arg0/field:street/NotBlank
BAD_RETURN => return=true; return/value/NotBlank
```

Giải thích:

- **VALID:** cả tiền điều kiện và hậu điều kiện hợp lệ; không có exception.
- **BAD_INPUT:** tham số số 0 rỗng, tham số số 1 bằng 0. Spring trả lỗi thích nghi theo từng vị trí; `isForReturnValue()` là `false`. Method `issue` không được chạy.
- **BAD_NESTED:** `Address.street=""` vi phạm `@NotBlank`. Vì tham số `Address` có `@Valid`, kết quả sử dụng `ParameterErrors` và `FieldError` với field `street`.
- **BAD_RETURN:** đầu vào hợp lệ; thân `brokenReceipt` chạy rồi trả chuỗi rỗng, vi phạm `@NotBlank` trên return value; `isForReturnValue()` là `true`.
- Code in **error code cuối cùng** (`NotBlank`, `Min`) và sắp xếp kết quả, thay vì dựa vào tên tham số từ compiler hoặc thông báo phụ thuộc locale. Vị trí `arg0`, `arg1` lấy từ `MethodParameter#getParameterIndex()`.

Ví dụ dùng nested service class `public static` có thể được class-based proxy, không `final`. `MethodValidationPostProcessor` được khai báo `static @Bean` và có `setProxyTargetClass(true)` để chủ động dùng class proxy. Nếu thay vì lấy bean từ context mà tự gọi `new CheckoutService()`, các method vẫn chạy nhưng **không tự được kiểm tra qua advice này**.

### 6.5. Nếu đổi cờ sang `false`

Trong ví dụ trên, thay:

```java
processor.setAdaptConstraintViolations(true);
```

bằng:

```java
processor.setAdaptConstraintViolations(false);
```

Bấy giờ vi phạm vẫn bị phát hiện bởi provider, nhưng phần `catch (MethodValidationException)` **không còn bắt được lỗi**. Bạn phải đổi handler sang `ConstraintViolationException` nếu muốn chương trình tiếp tục in các tình huống. Đây là khác biệt API quan sát được, không có nghĩa cờ `false` đã tắt method validation.

Ví dụ handler cho chế độ mặc định (đoạn riêng, không ghép nguyên xi vào chương trình chính):

```java
catch (jakarta.validation.ConstraintViolationException ex) {
    List<String> codes = ex.getConstraintViolations().stream()
        .map(v -> v.getConstraintDescriptor()
                .getAnnotation().annotationType().getSimpleName())
        .sorted()
        .toList();
    System.out.println("ConstraintViolationException: " + codes);
}
```

## 7. Cách xử lý kết quả thích nghi trong ứng dụng thực tế

### 7.1. Lấy lỗi theo tham số

Thay vì parse chuỗi `exception.getMessage()`, hãy làm việc với API có cấu trúc:

```java
// Đoạn xử lý bên trong catch (MethodValidationException ex),
// đã có import org.springframework.validation.method.*.
for (ParameterValidationResult result : ex.getParameterValidationResults()) {
    int parameterIndex = result.getMethodParameter().getParameterIndex();
    Object rejectedArgument = result.getArgument();

    for (MessageSourceResolvable error : result.getResolvableErrors()) {
        String[] codes = error.getCodes();
        String defaultMessage = error.getDefaultMessage();
        // Chuyển codes/message thành lỗi nghiệp vụ theo hợp đồng ứng dụng.
    }
}
```

Đây là mã minh họa tích hợp, không phải một class chạy độc lập. `rejectedArgument` và nội dung `FieldError#getRejectedValue()` có thể chứa thông tin cá nhân/bí mật. **Không log hoặc trả nguyên giá trị cho client** nếu không được phép; thường chỉ cần trường, mã lỗi và thông báo đã chọn lọc.

Nếu chỉ muốn phân loại trực tiếp/lồng nhau:

```java
List<ParameterValidationResult> direct = ex.getValueResults();
List<ParameterErrors> nested = ex.getBeanResults();

for (ParameterErrors errors : nested) {
    for (FieldError field : errors.getFieldErrors()) {
        // field.getField(), field.getCode(), field.getDefaultMessage()
    }
}
```

Lỗi kiểm tra một tổ hợp tham số (cross-parameter constraint) có thể có trong `getCrossParameterValidationResults()` ở Spring 6.2. Không giả định tổng số lỗi luôn bằng tổng số phần tử trong `getParameterValidationResults()`, vì một tham số có thể có nhiều lỗi và còn có loại cross-parameter.

### 7.2. Chuyển MessageSourceResolvable thành thông báo theo locale

Spring cung cấp `MessageSource` để ánh xạ error code và argument thành câu thông báo. Ví dụ, trong một handler đã được inject `MessageSource messageSource`:

```java
// Đoạn code sử dụng trong handler phù hợp:
Locale locale = Locale.forLanguageTag("vi-VN");

for (ParameterValidationResult result : ex.getParameterValidationResults()) {
    for (MessageSourceResolvable error : result.getResolvableErrors()) {
        String text = messageSource.getMessage(error, locale);
        // Sử dụng text đã được bản địa hóa theo ngữ cảnh/UI của ứng dụng.
    }
}
```

Đối với constraint trực tiếp trên tham số, Spring tạo dãy mã theo thứ tự ưu tiên, ví dụ dạng:

```text
Min.myService#approve.amount
Min.amount
Min.int
Min
```

Đối với field bên trong `@Valid` DTO, có thể là:

```text
NotBlank.address.street
NotBlank.street
NotBlank.java.lang.String
NotBlank
```

Đây là **ví dụ hình dạng** của danh sách mã: tiền tố object/method và tên tham số có thể khác theo provider, compiler và cấu hình. `MessageSource` thử tìm mã phù hợp trong message bundle, từ cụ thể đến tổng quát. Nếu không tìm thấy, thông thường có thể dùng default message tương ứng; lựa chọn chính xác phụ thuộc cấu hình `MessageSource`.

Ví dụ thuộc tính trong `messages_vi.properties` theo mã tổng quát:

```properties
NotBlank=Giá trị không được để trống
Min=Giá trị phải đạt mức tối thiểu
```

Các mã tổng quát có thể ảnh hưởng nhiều trường. Trong ứng dụng lớn, ưu tiên mã cụ thể để nội dung rõ ràng và tránh thông báo không liên quan. Với `Min`, `getArguments()` mang metadata của constraint; phải kiểm tra thứ tự argument trước khi thiết kế mẫu có placeholder `{0}`, `{1}`. Không tự cho rằng danh sách error code hoặc thứ tự argument là hằng số giữa mọi điểm dùng/version.

### 7.3. Lấy lại ConstraintViolation khi thực sự cần

Kết quả đã thích nghi không có API dạng `ConstraintViolationException#getConstraintViolations()` ở cấp exception. Nhưng từ Spring Framework 6.2, `ParameterValidationResult` có thể hỗ trợ truy xuất nguồn phía sau `MessageSourceResolvable` bằng `unwrap(...)`.

```java
// Ví dụ cho Spring Framework 6.2:
for (ParameterValidationResult result : ex.getParameterValidationResults()) {
    for (MessageSourceResolvable error : result.getResolvableErrors()) {
        jakarta.validation.ConstraintViolation<?> original =
            result.unwrap(error, jakarta.validation.ConstraintViolation.class);
        // Dùng metadata gốc khi có lý do chính đáng.
    }
}
```

Chỉ gọi khi biết nguồn được tạo từ Jakarta Bean Validation và API/version hỗ trợ. Thường phần lớn client handler chỉ cần `MessageSourceResolvable` và `FieldError` nên không cần phụ thuộc ngược vào metadata gốc.

## 8. Tác động của lỗi tham số, return value và @Valid

Về thời điểm đánh giá:

| Vị trí vi phạm | Có gọi thân method không? | Có thể có side effect chưa? | `isForReturnValue()` |
| --- | --- | --- | --- |
| Constraint trực tiếp trên tham số | Chưa | Không từ thân method được chặn | `false` |
| Lỗi nested field qua `@Valid` trên tham số | Chưa | Không từ thân method được chặn | `false` |
| Constraint trực tiếp trên return value | Có | Có thể đã xảy ra | `true` |
| Cascade qua `@Valid` trên return value | Có | Có thể đã xảy ra | `true` |

Khi return value sai, việc ném `MethodValidationException` **không tự đảm bảo rollback**. Nếu method có `@Transactional`, cần xem thứ tự advisor và quy tắc rollback. Nếu method đã thực hiện thao tác bên ngoài (gửi message, HTTP call), validation hậu điều kiện cũng không tự thu hồi chúng.

`@Valid` chỉ chỉ đạo cascade, nó không đồng nghĩa `@NotNull`. Nếu một tham số object bằng `null`, cascade vào các thuộc tính con không diễn ra; muốn cấm `null` cần thêm `@NotNull` khi phù hợp.

## 9. Phân biệt với Spring MVC method validation

Spring MVC từ Framework 6.1 có **method validation tích hợp** cho controller handler, có thể phát ra `HandlerMethodValidationException`. Đây là cơ chế hạ tầng web riêng, dù vẫn dùng những abstraction kết quả validation có cấu trúc liên quan.

Cần phân biệt:

- **Spring service với `@Validated` cấp lớp và AOP method validation:** `MethodValidationPostProcessor` quyết định chế độ exception bằng `setAdaptConstraintViolations(...)`.
- **Spring MVC controller dùng built-in method validation:** framework có đường xử lý và loại exception riêng, phổ biến là `HandlerMethodValidationException` cho lỗi method-level; `@Valid @RequestBody` cũng có thể đi vào `MethodArgumentNotValidException` tùy chữ ký và constraint.

Không kết luận rằng bật `setAdaptConstraintViolations(true)` sẽ đổi toàn bộ lỗi MVC thành `MethodValidationException`. Trong Spring MVC 6.1+, tài liệu khuyến nghị bỏ `@Validated` cấp lớp trên controller nếu muốn dùng đường method validation built-in thay vì AOP trên class.

Vì exception của **service** có thể bị ném xuyên qua controller, ứng dụng phải định nghĩa cách dịch nó thành phản hồi HTTP trong `@ControllerAdvice` hoặc tầng biên API. Tránh mặc định “MethodValidationException = HTTP 400”: lỗi return value thường là lỗi lập trình phía server; lỗi tham số có thể phát sinh từ caller nội bộ hoặc API client tùy ngữ cảnh.

## 10. Thiết kế exception handler và hợp đồng lỗi

Một handler tốt thường cần:

1. Chọn rõ lớp ngoại lệ đang xử lý: `ConstraintViolationException` ở chế độ thô, `MethodValidationException` ở chế độ thích nghi, hoặc exception built-in của MVC.
2. Dùng metadata có cấu trúc: tên method, chỉ số tham số, field lồng nhau, error code, locale. Không phân tích chuỗi exception bằng regex.
3. Chỉ tiết lộ thông tin lỗi phù hợp với người gọi. Tránh phản hồi nguyên argument, rejected value hoặc thông tin nội bộ của service.
4. Xác định loại lỗi đầu vào hay hậu điều kiện qua `isForReturnValue()`.
5. Giữ định dạng response ổn định bằng một model lỗi riêng của ứng dụng, không để DTO response phụ thuộc trực tiếp vào object exception framework.
6. Nếu có nhiều constraint/group, quyết định rõ trả một lỗi hay tất cả lỗi; sort nếu client/test cần thứ tự ổn định.

Ví dụ model công khai hóa lỗi (đoạn minh họa, chưa gồm handler hoàn chỉnh):

```java
public record ApiValidationError(
        String location,
        String code,
        String message
) {}
```

Ở đây `location` có thể là `"arg0"` hoặc `"arg0.street"` sau khi bạn ánh xạ chỉ số/field theo contract API. Không nên tùy tiện đưa tên class nội bộ hoặc đường dẫn package Java vào hợp đồng public.

## 11. Kiểm thử và chẩn đoán

Bộ test nên bao phủ cả **đường proxy** và **kiểu exception**:

| Tình huống | Adapt = `false` | Adapt = `true` |
| --- | --- | --- |
| Tham số `@NotBlank` rỗng | `ConstraintViolationException` | `MethodValidationException`, value result |
| Hai tham số sai đồng thời | Tập các `ConstraintViolation` | Nhóm lỗi theo vị trí tham số |
| `@Valid` DTO có field con sai | Violation chứa property path | `ParameterErrors` với `FieldError` |
| Return value vi phạm constraint | `ConstraintViolationException` | `MethodValidationException` và `isForReturnValue=true` |
| Không có constraint sai | Trả bình thường | Trả bình thường |
| Lời gọi qua `this.inner()` | Không được proxy advise ở inner | Tương tự; cờ không khắc phục self-invocation |
| Lỗi binding JSON/HTTP trước service | Tùy hạ tầng web | Tùy hạ tầng web, không chịu tác động trực tiếp của cờ |

Kiểm thử integration qua Spring container mới khẳng định cờ và BeanPostProcessor thực sự có hiệu lực. Unit test gọi trực tiếp `new CheckoutService()` chỉ thử thân phương thức, không thử method validation AOP.

Khi debug:

- Kiểm tra có Bean Validation provider và đúng phiên bản Spring từ 6.1 trở lên.
- Kiểm tra bean có `@Validated` trên class/type; các constraint nằm đúng tham số hoặc return value.
- Xác nhận reference caller đang dùng là Spring proxy, không phải object khởi tạo bằng `new`.
- Xem có post-processor trùng, bị custom auto-configuration ghi đè hoặc sai `ValidatorFactory` không.
- Với Spring 6.2, ưu tiên `getParameterValidationResults()` và `getCrossParameterValidationResults()` khi cần; tránh API deprecated.
- Không dùng `getMessage()` để suy ra field, error code hoặc group.
- Đối với `ParameterErrors`, xác minh `getFieldErrors()` khi xử lý DTO lồng nhau; khi giá trị tham số đơn giản sai, kết quả có thể chỉ là `ParameterValidationResult`.
- Cẩn trọng khi log `getArgument()`, `FieldError#getRejectedValue()` hoặc toàn bộ exception vì chúng có thể chứa dữ liệu nhạy cảm.

## 12. Những lỗi nhận thức thường gặp

**“Cờ bật = bật validation.”** Sai. Cờ chỉ quyết định cách trình bày violation và kiểu exception khi method validation **đã được kích hoạt**.

**“Dùng `@Valid` sẽ luôn tạo `ParameterErrors`.”** Chưa chắc. Cần thực sự có lỗi lồng nhau; `@Valid` trên tham số hợp lệ không tạo lỗi. Constraint đặt trực tiếp trên tham số tạo value result; một chữ ký có thể chứa cả hai loại.

**“Khi dùng `MethodValidationException` thì mất hết thông tin Jakarta.”** Không hoàn toàn. Spring giữ error codes, default message, arguments và có API `unwrap` ở phiên bản hỗ trợ để lấy nguồn của một lỗi thích nghi. Tuy nhiên không được giả định exception trực tiếp cung cấp cùng API với `ConstraintViolationException`.

**“Mọi lỗi adaptation tự trở thành thông báo tiếng Việt.”** Sai. `MessageSourceResolvable` chỉ cung cấp mã và arguments. Muốn thông báo bản địa hóa cần cấu hình message bundle và dùng `MessageSource` với `Locale` phù hợp.

**“MethodValidationException là exception của mọi controller.”** Sai. Spring MVC built-in method validation có đường xử lý riêng; service AOP và MVC controller cần phân biệt.

**“Kết quả bị validate sau khi method chạy nghĩa là không có side effect.”** Sai. Postcondition check không thể tự undo phần thân method đã thực thi.

## 13. Ghi nhớ

`setAdaptConstraintViolations(true)` trên `MethodValidationPostProcessor` chuyển **biểu diễn lỗi method validation** từ tập `ConstraintViolation` thô sang các kết quả `MethodValidationResult`/`ParameterValidationResult` trong `MethodValidationException`. Nhờ đó, ứng dụng phân loại lỗi trực tiếp trên tham số, lỗi nested field qua `ParameterErrors`, lỗi return value và thông báo có thể quốc tế hóa qua `MessageSourceResolvable`.

Khi áp dụng, hãy cấu hình trên đúng post-processor, giữ đường gọi qua proxy, kiểm thử cả hai kiểu exception và xây dựng một contract lỗi riêng, có cấu trúc và không làm lộ dữ liệu không cần thiết.

## Tài liệu tham khảo

- Spring Framework 6.2 Reference — *Spring-driven Method Validation* và *Method Validation Exceptions*: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2 Javadoc — `MethodValidationPostProcessor#setAdaptConstraintViolations`: https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationPostProcessor.html
- Spring Framework 6.2 Javadoc — `MethodValidationResult`: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/method/MethodValidationResult.html
- Spring Framework 6.2 Javadoc — `ParameterValidationResult` và `unwrap`: https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/validation/method/ParameterValidationResult.html
- Spring Framework 6.2 Javadoc — `ParameterErrors`: https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/validation/method/ParameterErrors.html
- Spring MVC Reference — *Validation*, phân biệt controller built-in và AOP: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html