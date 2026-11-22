# ConstraintViolationException và MethodValidationException trong kiểm tra phương thức

## Mục tiêu

Khi một tham số phương thức vi phạm `@NotNull`, `@Min`, hoặc một đối tượng tham số `@Valid` chứa field sai, Spring có thể dừng lời gọi bằng exception. Hai tên dễ gây nhầm là:

- `jakarta.validation.ConstraintViolationException`: exception chuẩn Jakarta Validation mang tập `ConstraintViolation<?>`.
- `org.springframework.validation.method.MethodValidationException`: exception Spring Framework 6.1+ mang kết quả kiểm tra phương thức đã được chuyển thành `MethodValidationResult`.

**Trong Spring AOP method validation**, cùng một lỗi có thể phát sinh một trong hai exception tùy cấu hình `MethodValidationPostProcessor.setAdaptConstraintViolations(boolean)`. Tuy nhiên, Spring MVC có những exception riêng cho việc kiểm tra controller; không nên đồng nhất tất cả thành một loại.

Bài học hướng dẫn đọc dữ liệu lỗi, bật chế độ chuyển đổi, xử lý riêng input và return value, tích hợp Spring MVC/service, và kiểm thử hành vi thực tế bằng Java 17+.

## 1. Tình huống: một lời gọi, hai cách biểu diễn vi phạm

Giả sử có service:

~~~java
@Validated
public class BookingService {
    public String reserve(
            @Valid @NotNull BookingRequest request,
            @Min(1) int seats) {
        return "BOOKED";
    }
}
~~~

`BookingRequest` có field `code` với `@NotBlank`. Lời gọi:

~~~java
service.reserve(new BookingRequest(""), 0);
~~~

sai ở hai vị trí:

1. `request.code` là chuỗi rỗng, vi phạm `@NotBlank` qua cascading `@Valid`.
2. `seats` là `0`, vi phạm `@Min(1)` trực tiếp trên tham số.

Nếu lời gọi đi qua Spring method-validation interceptor:

~~~text
caller
  -> Spring AOP proxy của BookingService
      -> kiểm tra method arguments bằng Jakarta Validation
          -> hai ConstraintViolation
              |
              +-- adaptConstraintViolations = false (mặc định)
              |      -> ConstraintViolationException
              |         chứa Set<ConstraintViolation<?>>
              |
              +-- adaptConstraintViolations = true
                     -> MethodValidationException
                        chứa MethodValidationResult
                        và ParameterValidationResult/ParameterErrors
~~~

Về mặt ràng buộc, không có sự khác nhau: cả hai nhánh báo cùng dữ liệu sai. Khác biệt nằm ở **kiểu exception và API trình bày lỗi**, từ đó ảnh hưởng cách controller/service, logger, test và bộ chuyển thông điệp đọc kết quả.

**Điều kiện quan trọng:** annotation trên method tự nó chưa tạo AOP validation; cần tích hợp method validation, chẳng hạn Spring bean có `@Validated` và `MethodValidationPostProcessor`, rồi được gọi qua proxy. Gọi `new BookingService().reserve(...)` trực tiếp không tự phát sinh một trong hai exception.

## 2. So sánh hai exception

| Khía cạnh | ConstraintViolationException | MethodValidationException |
| --- | --- | --- |
| Package | `jakarta.validation` | `org.springframework.validation.method` |
| Hệ sinh thái | Jakarta Bean Validation | Spring Framework 6.1+ |
| Lớp cha | `ValidationException` | `RuntimeException` |
| Dữ liệu chính | `Set<ConstraintViolation<?>>` | `MethodValidationResult` nhóm theo parameter |
| Cách đọc | `getConstraintViolations()` | `getParameterValidationResults()` (Spring 6.2+) |
| Nội dung một lỗi | `getPropertyPath()`, `getMessage()`, `getConstraintDescriptor()`, `getInvalidValue()` | `MessageSourceResolvable` và, với lỗi bean lồng, `ParameterErrors` / `FieldError` |
| Vị trí method | đọc `Path` của violation | `getMethod()`, `getTarget()`, `getMethodParameter()` |
| Input hay return value | nhận biết từ `Path.Node.getKind()` | `isForReturnValue()` |
| Phát sinh mặc định bởi Spring AOP method validation | Có | Không; cần bật adaptation |
| Khả năng i18n kiểu Spring | Có message nội suy chuẩn Jakarta, muốn map Spring message codes phải tự làm | Error codes/arguments dạng `MessageSourceResolvable` để dùng `MessageSource` |
| Thứ tự lỗi | `Set` không đảm bảo thứ tự | Danh sách theo kết quả nhóm; vẫn nên tạo thứ tự API response có chủ đích |

**Chú ý về phiên bản:** Spring Framework 6.1 giới thiệu `MethodValidationException` và `MethodValidationResult`. Từ Spring **6.2**, dùng `getParameterValidationResults()`; phương thức cũ `getAllValidationResults()` bị đánh dấu deprecated trong 6.2. Nếu dự án còn ở 6.1, phải kiểm tra API phiên bản đó; nếu ở 6.0 hoặc trước, không thể giả định `MethodValidationException` đã có.

Hai loại exception không phải quan hệ cha-con với nhau. Bắt `ConstraintViolationException` **không** bắt được `MethodValidationException`, và ngược lại.

## 3. ConstraintViolationException: báo cáo vi phạm dạng Jakarta

Jakarta Validation cung cấp exception:

~~~java
public class ConstraintViolationException
        extends ValidationException {

    // Constructor nhận Set<? extends ConstraintViolation<?>>
    // API đọc dữ liệu:
    public Set<ConstraintViolation<?>> getConstraintViolations();
}
~~~

Đây là phác họa API để giải thích, không phải source được biên dịch độc lập; không cần định nghĩa lại class thư viện.

Mỗi `ConstraintViolation<?>` mang thông tin về một ràng buộc không đạt:

- `getPropertyPath()`: đường dẫn có cấu trúc `Path` từ root đến vị trí lỗi; có thể có node `METHOD`, `PARAMETER`, `RETURN_VALUE`, `PROPERTY`, `CONTAINER_ELEMENT`.
- `getMessage()`: thông điệp đã nội suy theo Jakarta Validation.
- `getMessageTemplate()`: mẫu thông điệp trước nội suy, ví dụ `"{jakarta.validation.constraints.Min.message}"`.
- `getConstraintDescriptor()`: metadata annotation constraint và các thuộc tính.
- `getInvalidValue()`: giá trị cụ thể không đạt; cần tránh phản chiếu vào log/API nếu có dữ liệu nhạy cảm.
- `getExecutableParameters()` / `getExecutableReturnValue()`: ngữ cảnh đối số/kết quả trong validation executable khi phù hợp.

Đọc lỗi an toàn:

~~~java
catch (ConstraintViolationException ex) {
    var entries = ex.getConstraintViolations().stream()
            .map(v -> v.getPropertyPath()
                    + " : " + v.getMessage())
            .sorted()
            .toList();

    entries.forEach(System.out::println);
}
~~~

Đây là đoạn trích đặt vào mã xử lý exception, không phải một file độc lập. Việc gọi `sorted()` giúp output ổn định vì không nên phụ thuộc thứ tự `Set`. Trong hệ thống thật, nếu cần phân biệt parameter với property ở nhiều tầng, duyệt từng `Path.Node` và kiểm tra `ElementKind` thay vì tách chuỗi path thủ công.

### 3.1. Bản thân Validator có tự ném exception này không?

**Không.** Các API Jakarta như:

~~~java
Set<ConstraintViolation<BookingRequest>> errors =
        validator.validate(request);
~~~

trả về một `Set` chứa các vi phạm; tương tự, `validator.forExecutables().validateParameters(...)` trả `Set<ConstraintViolation<T>>`. Nếu cần biến tập lỗi thành exception, framework/interceptor hoặc code ứng dụng sẽ quyết định ném.

Ví dụ thủ công:

~~~java
Set<ConstraintViolation<BookingRequest>> errors =
        validator.validate(request);

if (!errors.isEmpty()) {
    throw new ConstraintViolationException(errors);
}
~~~

Hai đoạn trên chỉ minh họa kiểu thao tác với các biến `validator` và `request` đã tồn tại. Jakarta Validation specification nhấn mạnh `ConstraintViolationException` là cách chuẩn để **báo cáo** violation; bản thân việc gọi `validate()` không tự động chuyển lỗi dữ liệu thành exception này.

Phân biệt lỗi người dùng thông thường (`ConstraintViolationException` do interceptor ném với các violations) và **lỗi cấu hình/khai báo constraint** (`ConstraintDefinitionException`, `UnexpectedTypeException`, `ConstraintDeclarationException`...). Không được xử lý mọi `ValidationException` như lỗi input 400.

## 4. MethodValidationException: lỗi đã được Spring phân nhóm

Trong Spring 6.1+, `MethodValidationException` là `RuntimeException` và triển khai `MethodValidationResult`. Thay vì thao tác trực tiếp với `Set<ConstraintViolation<?>>`, ứng dụng đọc các kết quả đã được Spring chuyển đổi.

Các API có ích trong Spring 6.2:

~~~java
catch (MethodValidationException ex) {
    boolean returnValueProblem = ex.isForReturnValue();

    var method = ex.getMethod();
    var target = ex.getTarget();

    for (var result : ex.getParameterValidationResults()) {
        var parameter = result.getMethodParameter();
        int position = parameter.getParameterIndex();

        for (var error : result.getResolvableErrors()) {
            String defaultText = error.getDefaultMessage();
            // Ghi nhận position, method, defaultText...
        }
    }
}
~~~

Đây là snippet của một handler đã bắt được exception, không phải chương trình độc lập. Nếu là lỗi **return value**, Spring biểu diễn return value bằng `MethodParameter` của kiểu return, với index quy ước `-1`; để xác định loại lỗi cấp method, dùng `isForReturnValue()` thay vì chỉ suy luận từ index.

### 4.1. ParameterValidationResult và ParameterErrors

Spring chuyển một tập violation thành những kết quả phù hợp với từng tham số:

- **Constraint trực tiếp trên đối số** (ví dụ `@Min(1) int seats`): thường có `ParameterValidationResult` với `getResolvableErrors()`; error là `MessageSourceResolvable` có codes/arguments/default message.
- **Constraint trong đối tượng `@Valid`** (ví dụ `BookingRequest.code`): Spring tạo `ParameterErrors` (một loại `ParameterValidationResult` triển khai `Errors`). Nó cung cấp `getFieldErrors()`, `getFieldError(...)` và các API của `Errors`.
- **Ràng buộc trên container element** có thể tạo nhiều kết quả theo từng phần tử; `ParameterValidationResult` có `getContainer()`, `getContainerIndex()`, `getContainerKey()`.
- **Cross-parameter constraint:** từ Spring 6.2, `getCrossParameterValidationResults()` cung cấp tập lỗi riêng; không giả định mọi lỗi đều nằm trong `getParameterValidationResults()`.

Mã minh họa xử lý cả hai nhóm:

~~~java
for (var result : ex.getParameterValidationResults()) {
    int parameterIndex =
            result.getMethodParameter().getParameterIndex();

    if (result instanceof
            org.springframework.validation.method.ParameterErrors nested) {
        for (var field : nested.getFieldErrors()) {
            System.out.println(
                    parameterIndex + "." + field.getField()
                    + " => " + field.getDefaultMessage());
        }
    } else {
        for (var error : result.getResolvableErrors()) {
            System.out.println(
                    parameterIndex + " => "
                    + error.getDefaultMessage());
        }
    }
}
~~~

Snippet giả định biến `ex` kiểu `MethodValidationException` đã có; không thể chạy độc lập. Các method cụ thể của `ParameterValidationResult` hữu ích khi ứng dụng cần phát triển một HTTP error schema ổn định theo vị trí tham số và field lồng.

Trong Spring 6.2, `MethodValidationResult` còn hỗ trợ:

| Phương thức | Tác dụng |
| --- | --- |
| `getParameterValidationResults()` | Tất cả kết quả nhóm theo parameter hoặc return value |
| `getValueResults()` | Những lỗi ràng buộc trực tiếp trên giá trị đối số/return |
| `getBeanResults()` | Những lỗi lồng trong bean `@Valid`, dưới dạng `ParameterErrors` |
| `getAllErrors()` | Danh sách các lỗi đã thích ứng thành `MessageSourceResolvable` |
| `getCrossParameterValidationResults()` | Lỗi constraint cần phối hợp nhiều tham số |
| `getMethod()`, `getTarget()` | Method và target của validation |
| `isForReturnValue()` | Kiểm tra này xảy ra sau khi method trả giá trị hay không |

### 4.2. Error codes và bản địa hóa thông điệp

Spring tạo `MessageSourceResolvable` để cho phép tìm message theo `MessageSource`. Với một `@Min(1)` ở parameter `seats`, error code có thể bao gồm dạng cụ thể cho object/method/parameter, rồi dạng chung `"Min.seats"`, `"Min.int"` và `"Min"`.

Ví dụ đoạn xử lý message:

~~~java
String localized = messageSource.getMessage(
        error, locale);
~~~

`messageSource` là Spring `MessageSource` đã cấu hình, `error` là một `MessageSourceResolvable` từ `getResolvableErrors()`, và `locale` là `java.util.Locale`. Đoạn này không phải class độc lập.

Với bean nested `@Valid`, `ParameterErrors` cho phép dùng `FieldError` và cơ chế resolve message quen thuộc của Spring validation. Error code của Spring có thể chứa nhiều mức ưu tiên nên có thể ghi thông điệp trong resource bundles, ví dụ:

~~~properties
NotBlank.bookingRequest.code=Mã đặt chỗ không được để trống
Min.seats=Số ghế phải ít nhất là {1}
~~~

Các key trên là **ví dụ minh họa**; error code thực tế phụ thuộc object name, method, parameter naming và metadata constraint. Hãy in `error.getCodes()` trong môi trường thật và tạo resource bundles theo các mã thực tế trước khi khẳng định key nào sẽ match. Việc dùng `{1}` là phong cách tham số kiểu Spring `MessageFormat`; cần đối chiếu thứ tự message arguments do Spring adapter tạo.

## 5. Cấu hình lựa chọn exception trong Spring AOP

Spring Framework cung cấp `MethodValidationPostProcessor` để phát hiện bean có `@Validated` và gắn AOP advice kiểm tra constraint trên method. Về cơ bản:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.MethodValidationPostProcessor;

@Configuration
public class ValidationConfiguration {

    @Bean
    public static MethodValidationPostProcessor
    methodValidationPostProcessor() {

        MethodValidationPostProcessor processor =
                new MethodValidationPostProcessor();

        processor.setAdaptConstraintViolations(true);
        return processor;
    }
}
~~~

Đây là cấu hình Spring độc lập về cú pháp nhưng chỉ hoạt động trong ứng dụng có provider Jakarta Validation và các bean service thích hợp. Dùng `true` nghĩa là interceptor sẽ chuyển `ConstraintViolation` thành `MethodValidationResult` rồi ném `MethodValidationException`; dùng `false` là chế độ mặc định để ném `ConstraintViolationException`.

**Quan trọng trong Spring Boot:** dự án thường đã có infrastructure method validation. Không tạo thêm `MethodValidationPostProcessor` thứ hai một cách tùy tiện; kiểm tra bean/auto-configuration đang được dùng, và tùy chỉnh đúng bean đó để tránh nhiều proxy hoặc cấu hình khó theo dõi.

Những điều kiện khi dùng Spring AOP method validation:

1. Bean được Spring quản lý và được đánh dấu `@Validated` ở cấp class (trong trường hợp cơ chế `MethodValidationPostProcessor` mặc định).
2. Có Jakarta Validation provider, ví dụ Hibernate Validator; riêng Spring Boot 3 thường dùng dependency `spring-boot-starter-validation`.
3. Caller gọi qua **Spring proxy**, không đi vòng qua proxy bằng `this.method(...)`.
4. Method/parameter/return có constraint phù hợp, ví dụ `@NotBlank`, `@Min`, `@NotNull` và `@Valid` ở cạnh cascade.
5. Policy `setAdaptConstraintViolations(...)` được đặt trước khi post-processor tạo advice/proxy.

Cả hai chế độ đều thực hiện **precondition validation** trên parameters và **postcondition validation** trên return value. Chế độ exception chỉ quyết định cách báo cáo lỗi.

## 6. Ví dụ thực thi Java 17+: so sánh trực tiếp hai chế độ

Ví dụ sau dùng Jakarta Validation provider cùng Spring AOP `ProxyFactory` + `MethodValidationInterceptor`. Ta gắn advice **thủ công vào proxy** để chạy cả hai cấu hình trong một process và so sánh kết quả. Đây là cùng cơ chế advice mà `MethodValidationPostProcessor` dùng trong các Spring bean, nhưng ví dụ không cần khởi động Spring application context.

Tạo file `src/main/java/com/example/validation/Demo.java`:

~~~java
package com.example.validation;

import jakarta.validation.ConstraintViolationException;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.aop.framework.ProxyFactory;
import org.springframework.validation.annotation.Validated;
import org.springframework.validation.beanvalidation.MethodValidationInterceptor;
import org.springframework.validation.method.MethodValidationException;

public final class Demo {

    public record BookingRequest(
            @NotBlank String code) {
    }

    @Validated
    public static class BookingService {

        public String reserve(
                @NotNull @Valid BookingRequest request,
                @Min(1) int seats) {
            return "BOOKED";
        }

        @NotBlank
        public String makeEmptyReceipt() {
            return "";
        }
    }

    private static BookingService proxy(
            Validator validator,
            boolean adaptViolations) {

        ProxyFactory factory =
                new ProxyFactory(new BookingService());

        factory.setProxyTargetClass(true);

        factory.addAdvice(
                new MethodValidationInterceptor(
                        () -> validator, adaptViolations));

        return (BookingService) factory.getProxy();
    }

    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            BookingService raw = proxy(validator, false);
            BookingService adapted = proxy(validator, true);

            try {
                raw.reserve(new BookingRequest(""), 0);
            } catch (ConstraintViolationException ex) {
                System.out.println(
                        "raw input violations="
                        + ex.getConstraintViolations().size());
            }

            try {
                raw.makeEmptyReceipt();
            } catch (ConstraintViolationException ex) {
                System.out.println(
                        "raw output violations="
                        + ex.getConstraintViolations().size());
            }

            try {
                adapted.reserve(new BookingRequest(""), 0);
            } catch (MethodValidationException ex) {
                System.out.println(
                        "adapted input errors="
                        + ex.getAllErrors().size()
                        + ", return=" + ex.isForReturnValue());
            }

            try {
                adapted.makeEmptyReceipt();
            } catch (MethodValidationException ex) {
                System.out.println(
                        "adapted output errors="
                        + ex.getAllErrors().size()
                        + ", return=" + ex.isForReturnValue());
            }
        }
    }
}
~~~

Để test riêng logic, hãy lưu ý:

- `BookingService` không `final`, các method `public` và không `final` để Spring AOP tạo class proxy.
- `@NotBlank` trên record component `code` kiểm tra giá trị lồng thông qua `@Valid` ở tham số `request`.
- `@Min(1)` kiểm tra `seats`. Hai lỗi input độc lập xuất hiện khi `reserve(new BookingRequest(""), 0)` đi qua proxy.
- `@NotBlank` trên phương thức `makeEmptyReceipt()` là **constraint trên return value**; vì method trả chuỗi rỗng, validation sau lời gọi phát hiện một lỗi.
- `ProxyFactory` chủ động gắn `MethodValidationInterceptor` với `adaptViolations` bằng `false` và `true`. Với proxy thủ công, `@Validated` không phải điều kiện để quyết định advice có được gắn hay không; ta giữ annotation để gần với cách cấu hình Spring bean thực tế.
- Không dựa vào thứ tự duyệt `Set<ConstraintViolation<?>>`; chương trình chỉ in **số lượng** lỗi nên có stdout xác định.

### 6.1. Maven dependencies và lệnh chạy

Tạo `pom.xml` cạnh thư mục `src`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>method-exception-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.16</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.16</version>
        </dependency>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.3.Final</version>
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
                <configuration>
                    <release>17</release>
                    <parameters>true</parameters>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Chạy bằng JDK 17+ và Maven:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=com.example.validation.Demo
~~~

**Bốn dòng stdout do `Demo` tạo** (không kể thông báo/log Maven hoặc Hibernate Validator):

~~~text
raw input violations=2
raw output violations=1
adapted input errors=2, return=false
adapted output errors=1, return=true
~~~

Nếu thiếu dependency Jakarta provider, `Validation.buildDefaultValidatorFactory()` không xây dựng được validator. Nếu bỏ proxy hoặc gọi thẳng `new BookingService()`, method body sẽ chạy mà không ném hai exception của ví dụ: đây là bằng chứng phân biệt validation metadata với validation trigger.

Ở project Spring Boot thực tế, nên dùng BOM/dependency management của Spring Boot và `spring-boot-starter-validation`; `pom.xml` ở đây cố định Spring Framework 6.2.16, Hibernate Validator 8 và Jakarta EL để minh họa môi trường chạy độc lập.

### 6.2. Đọc sâu dữ liệu hai nhánh

Với `raw.reserve(...)`, một lỗi có path dạng `reserve.request.code`, lỗi còn lại có path `reserve.seats` nếu compiler lưu tên parameter Java. Nếu thiếu `-parameters`, phần tên parameter có thể là `arg0`, `arg1`. Kết quả thực tế có thể phụ thuộc provider và metadata, nên khi viết code chịu nhiều runtime, hãy đọc `Path.Node` với `ElementKind.PARAMETER` và `getParameterIndex()`.

Với `adapted.reserve(...)`, một `ParameterErrors` biểu diễn `request.code` và một `ParameterValidationResult` biểu diễn constraint trực tiếp trên `seats`. Trong Spring 6.2, có thể phân tích:

~~~java
catch (MethodValidationException ex) {
    System.out.println(
            "bean groups=" + ex.getBeanResults().size());
    System.out.println(
            "direct groups=" + ex.getValueResults().size());

    for (var group : ex.getParameterValidationResults()) {
        int index =
                group.getMethodParameter().getParameterIndex();
        System.out.println("index=" + index);

        for (var error : group.getResolvableErrors()) {
            System.out.println(
                    error.getDefaultMessage());
        }
    }
}
~~~

Đây là đoạn **thay thế** catch của nhánh adapted trong `Demo`, không phải một class độc lập. Dữ liệu đã nhóm thường có một group cho bean nested `request` và một group cho direct constraint `seats`. Khi đưa ra UI, nên quyết định thứ tự field/error phù hợp và sử dụng `MessageSource` để bản địa hóa, thay vì trả toàn bộ Throwable ra API.

## 7. Spring MVC: đừng nhầm MethodValidationException với HandlerMethodValidationException

Câu hỏi hay gặp: “Controller có `@Valid` thì sẽ ném `MethodValidationException` chứ?” — **Không nhất thiết**.

Spring MVC có thể thực hiện validation ngay khi resolve HTTP arguments, hoặc dùng hạ tầng method validation riêng của controller.

### 7.1. Chỉ kiểm tra DTO từ @RequestBody

~~~java
@RestController
class BookingController {

    @PostMapping("/bookings")
    String create(
            @Valid @RequestBody BookingRequest request) {
        return "ok";
    }
}
~~~

Trong Spring MVC, khi validate riêng đối tượng `@RequestBody` đã bind và phát hiện lỗi, thông thường exception là `MethodArgumentNotValidException` (khi không có `BindingResult` xử lý ngay sau tham số). `@Valid` **không phải constraint trực tiếp**, do đó chỉ một `@Valid` trên đối tượng không tự yêu cầu native method validation cho toàn bộ method.

Snippet trên giả định import các annotation Spring MVC và DTO đã được định nghĩa; không phải một chương trình Java độc lập.

### 7.2. Constraint trực tiếp trên controller method

~~~java
@RestController
class BookingController {

    @GetMapping("/bookings/search")
    String search(@RequestParam @Min(1) int seats) {
        return "ok";
    }
}
~~~

Với Spring Framework 6.1+, native controller method validation có thể được dùng vì `@Min` là một constraint trực tiếp trên argument. Khi method validation thất bại, exception của Spring MVC là **`org.springframework.web.method.annotation.HandlerMethodValidationException`**.

Đây là **lớp khác** với `org.springframework.validation.method.MethodValidationException` của service/AOP. Dù cả hai có thể triển khai `MethodValidationResult`, chúng được ném tại các điểm tích hợp khác nhau.

| Tình huống thường gặp | Exception thường gặp |
| --- | --- |
| Spring service `@Validated` qua AOP, adaptation mặc định `false` | `ConstraintViolationException` |
| Spring service `@Validated` qua AOP, adaptation `true` | `MethodValidationException` |
| Spring MVC validate riêng `@Valid @RequestBody` DTO | `MethodArgumentNotValidException` |
| Spring MVC 6.1+ native method validation khi controller có direct constraint | `HandlerMethodValidationException` |
| Code chủ động gọi `jakarta.validation.Validator.validate(bean)` | Trả `Set<ConstraintViolation<T>>`, không tự ném exception |

Với `HandlerMethodValidationException`, Spring MVC có quy tắc trạng thái: lỗi input/parameter thường HTTP **400**; lỗi return value thường HTTP **500**. Khi `MethodValidationException` đến từ service phía dưới controller, Spring MVC mặc định xem đó là vấn đề server và có xử lý mặc định HTTP **500**; không tự map mọi service exception thành 400.

Lưu ý class-level `@Validated` trên controller có thể khiến validation chạy qua AOP proxy thay vì native support. Tài liệu Spring 6.1+ khuyến nghị bỏ class-level `@Validated` nếu bạn muốn sử dụng cơ chế native method validation của Spring MVC. Hãy xác định ranh giới thật sự của ứng dụng thay vì dựa vào tên annotation để đoán exception.

## 8. Input và return value phải có chính sách xử lý khác nhau

Ràng buộc trên parameter nói về **precondition**: dữ liệu caller cung cấp cần đạt điều kiện trước khi service chạy. Ràng buộc trên return value nói về **postcondition**: dữ liệu service trả phải đáp ứng lời hứa của method.

Ví dụ:

~~~java
@Validated
class PriceService {

    @NotNull
    public String quote(@NotBlank String sku) {
        return null; // Vi phạm hậu điều kiện.
    }
}
~~~

Nếu caller gọi `quote("")` qua Spring proxy, lỗi xảy ra **trước khi body chạy**. Nếu gọi `quote("ABC")`, body trả `null` rồi mới xảy ra lỗi return value. Exception mode có thể là raw hoặc adapted, nhưng **nguồn lỗi** vẫn khác.

Với `MethodValidationException`:

~~~java
if (ex.isForReturnValue()) {
    // Lỗi hậu điều kiện: xử lý như bug hoặc vấn đề dữ liệu server.
} else {
    // Lỗi precondition: xác định caller và tầng phát sinh.
}
~~~

Đây là snippet minh họa xử lý một biến `ex` đã tồn tại. Không nên mặc định mọi lỗi precondition từ service đều là lỗi HTTP request: service cũng có thể được gọi bởi scheduler, message consumer, background job, hoặc một service khác truyền dữ liệu không hợp lệ. Quyết định trả 400/422 hay 500 dựa vào **ranh giới tin cậy và API contract**, không chỉ dựa trên loại exception.

Với `ConstraintViolationException`, để phân loại nguồn, có thể duyệt `getPropertyPath()` và kiểm tra các loại node `PARAMETER` hoặc `RETURN_VALUE`. Không dựa vào thông điệp `"must not be blank"` vì cùng constraint có thể áp dụng ở cả input và output.

## 9. Thiết kế Error Response rõ ràng và an toàn

Khi đưa validation lỗi ra HTTP, frontend thường cần những trường ổn định như:

~~~json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "location": "request.code",
      "message": "Mã không được để trống"
    },
    {
      "location": "seats",
      "message": "Số ghế phải từ 1"
    }
  ]
}
~~~

Đây chỉ là schema minh họa, không phải output do Spring tự sinh. Trong thực tế cần:

1. Phân biệt nguồn: path của HTTP parameter/body khác path phương thức/service; không tự động trả `reserve.request.code` cho client nếu API công khai dùng field `code`.
2. Chọn thứ tự lỗi ổn định: sắp theo index tham số, field path hoặc quy tắc domain; `Set` không đảm bảo thứ tự.
3. Chỉ tiết lộ tên field/constraint và thông điệp cần thiết. Tránh serialise nguyên `ConstraintViolation`, `Throwable`, `getInvalidValue()`, target bean hoặc arguments, vì có thể chứa mật khẩu, token và dữ liệu cá nhân.
4. Dùng Spring `MessageSource` khi muốn i18n từ `MessageSourceResolvable`; tránh hard-code mọi message.
5. Với lỗi ở **return value** hoặc lỗi service nội bộ, không phản chiếu object server bị lỗi cho client; log có kiểm soát và trả thông báo phía server phù hợp.
6. Tại API boundary, xử lý các exception thực tế của controller, đồng thời có policy rõ cho exception phát sinh từ service. Tránh bắt và biến mọi `RuntimeException` thành validation error.

Ví dụ mapping `MethodValidationException` ở tầng xử lý (chỉ là **đoạn minh họa**, cần gắn vào handler/framework cụ thể):

~~~java
List<String> messages = ex.getParameterValidationResults()
        .stream()
        .flatMap(r -> r.getResolvableErrors().stream())
        .map(org.springframework.context.MessageSourceResolvable::
                getDefaultMessage)
        .filter(java.util.Objects::nonNull)
        .sorted()
        .toList();
~~~

Với HTTP layer, có thể dùng `@ControllerAdvice` và những handler riêng cho `MethodArgumentNotValidException`, `HandlerMethodValidationException` và lỗi service nếu ứng dụng thật sự muốn ánh xạ. Riêng `MethodValidationException` không phải mặc định 400; cần cân nhắc nguồn phát sinh.

## 10. Liên hệ @Valid, validation groups và message source

### 10.1. @Valid có thể tạo lỗi lồng và ParameterErrors

~~~java
record BookingRequest(@NotBlank String code) {}

public void reserve(@Valid BookingRequest request) {
    // ...
}
~~~

Khi method validation chạy và `request.code` rỗng, raw mode có violation với path qua parameter rồi property `code`. Adapted mode dùng `ParameterErrors` và `FieldError` để đại diện cho field lồng. Cần khai báo đúng cascading trên parameter; chỉ có `@NotBlank` trong DTO chưa đủ để interceptor đi vào DTO qua method parameter khi không đánh dấu `@Valid`.

**Null:** `@Valid` cho qua reference null; nếu yêu cầu bắt buộc, viết `@NotNull @Valid BookingRequest request`. Tương tự với return value cần kết hợp `@NotNull` và `@Valid` khi muốn bắt buộc có object và kiểm tra object lồng.

### 10.2. Groups quyết định ràng buộc nào được kiểm tra

Spring `@Validated(Group.class)` có thể chọn các validation groups để method validation sử dụng. Nếu một field chỉ có constraint thuộc group `Detailed`, thì validation theo group `Default` sẽ không tạo violation cho field đó. Điều này không phải lỗi của exception adaptation.

Nếu gặp dữ liệu sai mà không có lỗi, trước tiên xác minh: có điểm kích hoạt, đúng bean/proxy, constraint nằm trong nhóm đang kiểm tra, có `@Valid` trên các cạnh lồng, và provider đã phát hiện metadata.

### 10.3. Thông điệp Jakarta và Spring là hai tầng

Raw `ConstraintViolation.getMessage()` là message đã được Jakarta provider nội suy theo message interpolator. Adapted `MessageSourceResolvable` có **danh sách codes, arguments và default message** để Spring `MessageSource` tiếp tục chọn thông điệp phù hợp với locale. Điều này không có nghĩa mọi câu tiếng Anh của Jakarta sẽ tự được dịch: cần resource bundles và mapping chuẩn xác.

Ví dụ dùng một `MessageSource`:

~~~java
for (var result : ex.getParameterValidationResults()) {
    for (var error : result.getResolvableErrors()) {
        String text = messageSource.getMessage(
                error, java.util.Locale.forLanguageTag("vi"));
    }
}
~~~

Đoạn này giả định `ex` và `messageSource` đã được cung cấp. Nếu ứng dụng muốn hiển thị lỗi field lồng, các `FieldError` trong `ParameterErrors` cũng là `MessageSourceResolvable` nên có thể resolve theo cùng cách.

## 11. Những nhầm lẫn phổ biến và nguyên nhân

| Hiện tượng | Nguyên nhân cần kiểm tra | Cách giải quyết |
| --- | --- | --- |
| Catch `ConstraintViolationException` không chạy | Post-processor bật `adaptConstraintViolations=true` hoặc lỗi đến từ Spring MVC native validation | Xác minh exception runtime, bắt đúng loại |
| Catch `MethodValidationException` không chạy | Adaptation đang `false` (mặc định), Spring dưới 6.1, hoặc integration khác | Kiểm tra Spring version, bean post-processor và cơ chế gọi |
| `getAllValidationResults()` báo deprecated | Dự án đã dùng Spring 6.2 | Chuyển sang `getParameterValidationResults()` |
| Lỗi lồng không hiện trong adapted result | Thiếu `@Valid` trên parameter/quan hệ con hoặc group không khớp | Bổ sung cascade đúng chỗ, kiểm tra groups |
| Gọi `validator.validate(bean)` không ném exception | API Jakarta trả Set theo thiết kế | Chủ động xử lý Set hoặc dùng interceptor/framework |
| Method có annotation nhưng gọi không bị chặn | Bean không qua Spring proxy, self-invocation, thiếu provider/post-processor | Gọi qua bean được quản lý và kiểm tra bean configuration |
| Hai lỗi xuất hiện với thứ tự khác nhau | `ConstraintViolation` nằm trong `Set` | Chuyển thành dạng có thứ tự trước khi so/output |
| Không thấy message localized | `MessageSource` không có code tương ứng hoặc chưa resolve errors | Kiểm tra `getCodes()`, message bundles, locale |
| HTTP trả 500 khi nghĩ là input 400 | Lỗi phát sinh từ service hoặc từ return value | Phân biệt nguồn lỗi và policy API |
| Controller ném `HandlerMethodValidationException` | Spring MVC 6.1+ native controller method validation | Xử lý loại exception của MVC, không đổi nhầm AOP flag |
| Adapter không thể map field nested | Có container/nested path phức tạp hoặc metadata không như dự kiến | Xem `ParameterErrors`, containerIndex/containerKey và path gốc |
| Bắt mọi `ValidationException` thành 400 | Gộp lỗi metadata/configuration/provider với lỗi dữ liệu | Chỉ xử lý loại lỗi và nguồn phù hợp |
| Chạy với `javax.validation` lẫn `jakarta.validation` | Phụ thuộc phiên bản Spring Boot/Spring Framework không tương thích | Spring 6/Boot 3 dùng `jakarta.validation`, kiểm tra dependency tree |

## 12. Checklist kiểm thử thực tế

Có thể triển khai những bài test sau, mỗi bài kiểm tra một contract có ý nghĩa:

**Test 1 — Raw precondition:** gọi bean `@Validated` qua proxy với `BookingRequest.code=""` và `seats=0` khi adaptation `false`. Khẳng định có `ConstraintViolationException` và tập violation chứa hai lỗi. Không phụ thuộc thứ tự.

**Test 2 — Adapted precondition:** chạy cùng input với adaptation `true`. Khẳng định có `MethodValidationException`, `isForReturnValue()==false`, có kết quả cho cả lỗi direct parameter và nested field; `getBeanResults()` chứa field error `code`.

**Test 3 — Raw postcondition:** gọi method có `@NotBlank` trên return value nhưng trả `""`. Khẳng định raw exception có path chứa `RETURN_VALUE`, thay vì chỉ test message.

**Test 4 — Adapted postcondition:** khẳng định `MethodValidationException.isForReturnValue()==true`; kiểm tra lỗi return value được group đúng.

**Test 5 — Hành vi không có proxy:** gọi method trực tiếp trên object được tạo bằng `new`. Kết quả có thể không bị AOP validation chặn; điều này phân biệt "annotation đã khai báo" với "runtime validation đã chạy".

**Test 6 — Spring Boot integration:** dùng Spring context thật, xác minh chỉ có một `MethodValidationPostProcessor` hiệu lực; nếu bật adaptation thì exception đúng chế độ. Tách method ở hai bean để tránh self-invocation.

**Test 7 — Controller:** thử riêng `@Valid @RequestBody` và direct constraint (ví dụ `@Min` trên `@RequestParam`), xác minh loại exception, HTTP status và body theo phiên bản Spring MVC. Test thêm return-value violation để tránh lẫn lỗi server với input.

**Test 8 — Thông điệp:** cung cấp `MessageSource` cho locale tiếng Việt, xác minh `getResolvableErrors()` có codes mong đợi và resolve ra message phù hợp. Dùng message mặc định làm fallback.

Có thể viết test trên `@Validated` service được Spring quản lý bằng JUnit và `assertThrows(...)`, nhưng cần chạy qua proxy thật. Các test bắt được `MethodValidationException` chỉ hợp lệ khi phiên bản Spring và cấu hình adaptation có mặt.

## 13. Câu hỏi tự kiểm tra

**1. Vì sao cùng một lỗi `@Min(1)` có thể cho hai exception khác nhau?**  
Vì AOP method validation của Spring có hai chế độ báo cáo: raw `ConstraintViolationException` và adapted `MethodValidationException`. Cấu hình quyết định biểu diễn lỗi, không thay đổi điều kiện `@Min`.

**2. `ConstraintViolationException` và `MethodValidationException` có quan hệ thừa kế không?**  
Không. Một class thuộc Jakarta Validation và class còn lại thuộc Spring; cả hai là runtime exception nhưng có API dữ liệu khác nhau.

**3. `validator.validate(bean)` có tự ném `ConstraintViolationException` không?**  
Không. Nó trả `Set<ConstraintViolation<T>>`. Interceptor/framework hoặc code ứng dụng mới ném nếu muốn.

**4. Vì sao `MethodValidationException` tiện khi báo lỗi từng field con?**  
Vì adapted result cung cấp `ParameterErrors`, `FieldError` và `MessageSourceResolvable`, phù hợp với Spring message codes, i18n và mapping theo parameter.

**5. Khi controller trả lỗi HTTP 400 do constraint trực tiếp trên `@RequestParam`, có chắc đó là `MethodValidationException` không?**  
Không. Spring MVC 6.1+ dùng `HandlerMethodValidationException` cho native controller method validation; xử lý riêng với exception AOP service.

**6. Khi service có constraint trên return value bị vi phạm, nên trả thông báo gì cho client?**  
Xem đây là hậu điều kiện không được đáp ứng; ứng dụng cần xử lý như lỗi server hoặc contract nội bộ phù hợp, không tự động quy trách nhiệm cho input client.

**7. API nào đọc method và phân biệt input/return khi dùng adapted exception?**  
`ex.getMethod()`, `ex.getTarget()` và `ex.isForReturnValue()`; đọc từng group bằng `ex.getParameterValidationResults()` (Spring 6.2+).

## Tài liệu tham khảo

- [Jakarta Validation 3.0 specification — Error report: ConstraintViolationException](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html#constraintviolationexception)
- [Jakarta ConstraintViolationException API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ConstraintViolationException.html)
- [Jakarta ConstraintViolation API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ConstraintViolation.html)
- [Spring Framework 6.2 — Spring-driven method validation và exception adaptation](https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html)
- [Spring Framework 6.2 — MethodValidationException API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/method/MethodValidationException.html)
- [Spring Framework 6.2 — MethodValidationResult API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/method/MethodValidationResult.html)
- [Spring Framework 6.2 — ParameterValidationResult API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/method/ParameterValidationResult.html)
- [Spring Framework 6.2 — MethodValidationPostProcessor API](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationPostProcessor.html)
- [Spring MVC — Validation and related exception types](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
