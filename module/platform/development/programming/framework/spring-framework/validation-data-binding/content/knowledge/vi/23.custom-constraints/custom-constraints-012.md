# An toàn đồng thời và tránh trạng thái của từng lần gọi trong validator

## 1. Vì sao custom validator cần thread-safe?

Trong Jakarta Bean Validation, lớp triển khai `ConstraintValidator<A, T>` thực hiện logic của một custom constraint. Cấu trúc cơ bản:

~~~java
public final class MyConstraintValidator
        implements ConstraintValidator<MyConstraint, String> {

    @Override
    public void initialize(MyConstraint annotation) {
        // Chuẩn bị cấu hình từ annotation.
    }

    @Override
    public boolean isValid(String value,
                           ConstraintValidatorContext context) {
        // Kiểm tra dữ liệu của lần gọi hiện tại.
        return true;
    }
}
~~~

Theo hợp đồng API, **`isValid(...)` có thể bị gọi đồng thời từ nhiều thread trên cùng một đối tượng validator**, và chính implementation phải bảo đảm thread-safety. Bean Validation provider (ví dụ Hibernate Validator trong Spring Boot) có thể **cache `ConstraintValidator` instance**. Vòng đời của instance không được xác định là "một instance cho một request" hoặc "mỗi lần validate một instance mới".

Trong ứng dụng Spring MVC, hai HTTP request xử lý cùng loại DTO có thể đến cùng lúc. Nếu validator lưu input của request A vào field rồi request B ghi đè field đó, A có thể kiểm tra sai input hoặc dùng nhầm dữ liệu của B.

**Quy tắc cốt lõi:** `isValid` hoạt động độc lập theo từng lời gọi. Các dữ liệu của request, bộ nhớ tạm và lỗi phát sinh chỉ nằm ở **tham số hoặc biến local**, không nằm ở shared mutable field của validator.

### Race condition đơn giản

Đoạn code sau **cố ý sai**, là minh họa một phần thân validator:

~~~java
// SAI: currentCode là field dùng chung giữa các lời gọi.
private String currentCode;

@Override
public boolean isValid(String value, ConstraintValidatorContext context) {
    currentCode = value; // Thread A và B cùng có thể ghi field này.
    return currentCode != null && currentCode.startsWith("PRD-");
}
~~~

Giả sử A truyền `"PRD-123"`, B truyền `"BAD"`. A vừa gán `currentCode` thì B ghi đè `"BAD"`; A đọc lại sẽ trả `false` dù input A hợp lệ. Đây là lỗi dữ liệu không ổn định theo lịch chạy, có thể không tái hiện trong test một thread.

Sửa bằng cách sử dụng tham số trực tiếp:

~~~java
@Override
public boolean isValid(String value, ConstraintValidatorContext context) {
    return value == null || value.startsWith("PRD-");
}
~~~

Mỗi invocation có `value` của riêng mình. `String` immutable; không cần lock.

## 2. Vòng đời `ConstraintValidator` và hai loại trạng thái

Hợp đồng Jakarta Validation có ba điểm quan trọng:

1. `initialize(A annotation)` được provider gọi **trước khi một instance được sử dụng để validate**. Đây là nơi đọc cấu hình của constraint, ví dụ regex hoặc giá trị giới hạn. Không xem `initialize` là callback cho mỗi request.
2. `isValid(T value, ConstraintValidatorContext context)` được gọi khi cần kiểm tra giá trị; **có thể chạy đồng thời** trên một instance. Không được thay đổi trạng thái của đối tượng `value`.
3. Vòng đời instance do provider quyết định. Provider có quyền tái sử dụng/caching; vì vậy mã đúng phải không phụ thuộc vào số lần khởi tạo, thread hay request.

Phân loại trạng thái khi thiết kế:

| Dữ liệu | Lưu trong instance validator? | Lý do |
| --- | --- | --- |
| Regex đã compile từ annotation | **Có**, khi chỉ gán trong `initialize` và không sửa sau đó | `Pattern` immutable, thread-safe, phù hợp chia sẻ. |
| Số `min/max`, flag, rule cấu hình | **Có**, nếu là cấu hình không đổi sau khởi tạo | Chỉ đọc khi `isValid` chạy. |
| Input/DTO/username/password của request | **Không** | Dễ bị thread khác ghi đè và lộ dữ liệu giữa request. |
| `Matcher`, `StringBuilder`, danh sách lỗi tạm | **Không** | Là đối tượng mutable thuộc từng invocation. |
| `ConstraintValidatorContext` hoặc violation builder | **Không** | Ngữ cảnh tạo lỗi dành cho lần gọi hiện tại. |
| Bộ đếm lỗi, map tạm, cache mutable | Chỉ khi có nhu cầu rõ ràng và cơ chế đồng thời đúng | Nên chuyển sang dịch vụ metrics/cache chuyên trách. |
| Dependency được Spring inject | **Tùy** thread-safety và scope của dependency | Đối tượng được chia sẻ có thể mang state riêng. |

Một field không tự động nguy hiểm. Vấn đề là **nó có bị thay đổi khi các invocation `isValid` chạy hay không**. Ví dụ `private Pattern pattern;` được gán một lần trong `initialize` rồi chỉ đọc là mẫu thiết kế hợp lệ. Ngược lại, `private String currentValue;` được gán mỗi lần `isValid` là state theo lời gọi, cần loại bỏ.

Cẩn thận với việc "khóa để an toàn" bằng `synchronized`. Nếu dữ liệu tạm có thể chuyển thành local, đó thường là thiết kế vừa đơn giản vừa cho phép chạy đồng thời tốt hơn.

## 3. `Pattern` có thể chia sẻ, `Matcher` không thể

`java.util.regex.Pattern` là pattern regex **immutable và thread-safe**. `Matcher` giữ vị trí và trạng thái trong quá trình so khớp, nên **không thread-safe**. Cách đúng:

~~~java
private Pattern compiledPattern;

@Override
public void initialize(CodePattern constraint) {
    compiledPattern = Pattern.compile(constraint.regexp());
}

@Override
public boolean isValid(String value, ConstraintValidatorContext context) {
    if (value == null || value.isBlank()) {
        return true; // Để @NotBlank xử lý dữ liệu thiếu.
    }
    Matcher localMatcher = compiledPattern.matcher(value);
    return localMatcher.matches();
}
~~~

Mỗi invocation tạo `localMatcher` của chính nó. Đối tượng `Pattern` chỉ đọc được chia sẻ an toàn.

Cách sai:

~~~java
// SAI: Matcher mutable được giữ ở field của validator.
private Matcher matcher;

@Override
public void initialize(CodePattern constraint) {
    matcher = Pattern.compile(constraint.regexp()).matcher("");
}

@Override
public boolean isValid(String value, ConstraintValidatorContext context) {
    return matcher.reset(value).matches();
}
~~~

Hai thread có thể xen kẽ giữa `reset(...)` và `matches()`, khiến kết quả của A phụ thuộc input B. Việc viết một dòng code không khiến nhiều thao tác trên mutable object trở thành một hành động nguyên tử.

Quy tắc tương tự áp dụng cho ngày giờ: `java.time.format.DateTimeFormatter` immutable, dùng chung được; `java.text.SimpleDateFormat` mutable, không nên để thành shared field của validator rồi gọi đồng thời. Với collection, `ArrayList`/`HashMap` lưu trạng thái tạm ở field cũng dễ xảy ra lỗi; hãy tạo collection local.

## 4. Ví dụ Java 17+ với Spring Boot: validator stateless theo request

Ví dụ chạy trong một dự án **Spring Boot 3+** có Java 17+ và Jakarta Validation (`jakarta.validation.*`). Nếu chưa có, thêm vào `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Tạo file **`src/main/java/com/example/validation/ConcurrentValidationApplication.java`**:

~~~java
package com.example.validation;

import jakarta.validation.Constraint;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.Payload;
import jakarta.validation.Validator;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

@SpringBootApplication
public class ConcurrentValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConcurrentValidationApplication.class, args);
    }

    @Bean
    ApplicationRunner runDemo(Validator validator) {
        return args -> {
            String[] codes = {
                    "PRD-AB-1234",
                    "PRD-ab-1234",
                    "INV-AB-1234"
            };
            for (String code : codes) {
                var violations = validator.validate(new Product(code));
                String result = violations.isEmpty()
                        ? "VALID"
                        : violations.iterator().next().getMessage();
                System.out.println(code + " -> " + result);
            }
        };
    }

    @Target(ElementType.FIELD)
    @Retention(RetentionPolicy.RUNTIME)
    @Constraint(validatedBy = CodePatternValidator.class)
    public @interface CodePattern {
        String regexp() default "PRD-[A-Z]{2}-[0-9]{4}";
        String message() default "Mã phải có dạng PRD-AA-0000";
        Class<?>[] groups() default {};
        Class<? extends Payload>[] payload() default {};
    }

    public static final class CodePatternValidator
            implements ConstraintValidator<CodePattern, String> {

        // Cấu hình theo annotation: thiết lập trong initialize.
        private Pattern compiledPattern;

        @Override
        public void initialize(CodePattern annotation) {
            compiledPattern = Pattern.compile(annotation.regexp());
        }

        @Override
        public boolean isValid(String value,
                               ConstraintValidatorContext context) {
            // Không báo lỗi lặp với @NotBlank.
            if (value == null || value.isBlank()) {
                return true;
            }

            // Matcher thuộc riêng invocation đang chạy.
            Matcher matcher = compiledPattern.matcher(value);
            return matcher.matches();
        }
    }

    public static final class Product {
        @NotBlank
        @CodePattern
        private final String code;

        public Product(String code) {
            this.code = code;
        }

        public String getCode() {
            return code;
        }
    }
}
~~~

Chạy trong dự án đã cấu hình Maven và Spring Boot plugin:

~~~bash
./mvnw spring-boot:run
~~~

Windows: `mvnw.cmd spring-boot:run`; hoặc `mvn spring-boot:run` nếu Maven đã được cài. Bên cạnh log Spring Boot, chương trình in:

~~~text
PRD-AB-1234 -> VALID
PRD-ab-1234 -> Mã phải có dạng PRD-AA-0000
INV-AB-1234 -> Mã phải có dạng PRD-AA-0000
~~~

Tính đúng đắn của ví dụ:

- Annotation `@CodePattern` cấu hình regex và message. Validator có ba thành phần chuẩn của constraint: `message`, `groups` và `payload`.
- `initialize` compile regex một lần cho cấu hình constraint của instance. `compiledPattern` không bị đổi bởi request.
- `isValid` chỉ đọc pattern; mọi input và `Matcher` đều local. Không có `lastCode` hay `lastResult` mutable field.
- `@NotBlank` xử lý null/chuỗi trắng, còn constraint regex kiểm tra chuỗi có nội dung. Đây là lựa chọn chủ động để tránh hai thông báo cho cùng lỗi thiếu dữ liệu.
- `Validator#validate(...)` trả một `Set<ConstraintViolation<Product>>`; thứ tự Set không được cam kết. Với từng input không rỗng ở ví dụ chỉ có tối đa một vi phạm.
- Spring có thể tái sử dụng validator giữa các lượt kiểm tra; logic vẫn đúng do không có trạng thái invocation được giữ trên instance.

Nếu một field có nhiều annotation với thông số khác nhau, hãy để provider cung cấp đúng cấu hình khi gọi `initialize` cho mỗi constraint declaration. Không sử dụng `static Pattern CURRENT_PATTERN` rồi thay đổi nó mỗi lần gặp annotation mới: cấu hình của constraint này sẽ ảnh hưởng constraint khác.

## 5. `ConstraintValidatorContext` là dữ liệu của invocation

`ConstraintValidatorContext` dùng để tạo thông báo lỗi tùy chỉnh, xây đường dẫn lỗi và chọn có giữ violation mặc định hay không. **Không lưu `context` hoặc builder vào instance field**, không dùng chúng sau khi `isValid` kết thúc.

Ví dụ thay thế **riêng phương thức `isValid`** trong lớp `CodePatternValidator` trên, tạo lỗi tùy chỉnh bằng chính message từ annotation:

~~~java
@Override
public boolean isValid(String value,
                       ConstraintValidatorContext context) {
    if (value == null || value.isBlank()) {
        return true;
    }

    Matcher matcher = compiledPattern.matcher(value);
    if (matcher.matches()) {
        return true;
    }

    context.disableDefaultConstraintViolation();
    context.buildConstraintViolationWithTemplate(
            context.getDefaultConstraintMessageTemplate())
            .addConstraintViolation();
    return false;
}
~~~

Một số lưu ý:

1. `disableDefaultConstraintViolation()` chỉ tắt việc tạo lỗi mặc định; sau đó khi trả `false`, cần hoàn tất ít nhất một custom violation bằng `addConstraintViolation()`.
2. Builder phải được tạo, sử dụng và kết thúc ngay trong invocation. Không cần field `currentMessage` hay `lastContext`.
3. Trong ví dụ constraint đặt tại field `code` nên violation tự gắn tại path `code`. Với constraint cấp class so sánh hai trường, có thể thêm `addPropertyNode("fieldName")` để gắn vào đúng field.

Minh họa đoạn thân `isValid` của constraint class-level kiểm tra ngày bắt đầu/kết thúc cho một DTO có các getter `start()` và `end()` trả về `LocalDate` (đây là đoạn logic, không phải chương trình đầy đủ):

~~~java
@Override
public boolean isValid(PeriodRequest value,
                       ConstraintValidatorContext context) {
    if (value == null || value.start() == null
            || value.end() == null) {
        return true; // @NotNull trên từng field xử lý thiếu dữ liệu.
    }
    if (!value.start().isAfter(value.end())) {
        return true;
    }

    context.disableDefaultConstraintViolation();
    context.buildConstraintViolationWithTemplate(
            "Ngày kết thúc không thể trước ngày bắt đầu")
            .addPropertyNode("end")
            .addConstraintViolation();
    return false;
}
~~~

Lỗi được gắn vào `end` của đúng DTO đang validate. Mỗi invocation độc lập; không có field `lastStart`/`lastEnd`/`lastError`. Trong Spring MVC, nếu DTO được kiểm tra bằng `@Valid @RequestBody` và controller nhận `BindingResult`, lỗi field có thể lấy bằng `getFieldErrors()`. Không tự giữ `BindingResult` ở validator vì đó là trách nhiệm của tầng xử lý request.

## 6. Spring dependency injection, `ConstraintValidatorFactory` và cache

Spring Boot thường tích hợp `jakarta.validation.Validator` và cung cấp khả năng dependency injection cho custom constraint validator. Tuy vậy, không nên suy ra rằng lifecycle của validator sẽ trùng với lifecycle của HTTP request hoặc mỗi invocation sẽ có một object mới.

Phân biệt:

- **`jakarta.validation.Validator`** là API thực hiện validation, có hợp đồng thread-safe; có thể dùng để validate nhiều bean ở các thread khác nhau.
- **`ConstraintValidator<A,T>`** là logic do ứng dụng viết. Provider được phép cache và gọi `isValid` đồng thời, nên implementation cũng phải thread-safe.
- **`ConstraintValidatorFactory`** cung cấp instance cho provider. Theo Jakarta Validation, factory **không nên tự cache instances**, vì `initialize` có thể cấu hình cùng một lớp validator khác nhau ở từng constraint declaration. Việc cache sau đó thuộc chiến lược của provider.
- **Spring service/repository được inject** có thread-safety và scope riêng. Validator không có shared mutable field vẫn có thể sai nếu gọi một collaborator không thread-safe.

Cách thiết kế dependency an toàn là dùng service stateless hoặc một API có contract đồng thời rõ ràng. Không lưu `HttpServletRequest`, thông tin user hiện tại, tenant ID, DTO hay transaction của request vào field của validator. Nếu cần dữ liệu ngữ cảnh, lấy từ tầng có scope đúng và tránh phụ thuộc vào một state được giữ lại sau lần gọi.

**Cache và synchronization:** cache thực sự cần thiết nên có key đầy đủ, vòng đời, kích thước/TTL và cơ chế đồng thời thích hợp; có thể dùng `ConcurrentHashMap` hoặc service cache chuyên biệt. Không dùng `HashMap` mutable field cho request đồng thời. Chỉ thêm `synchronized` khi có dữ liệu chia sẻ thật sự và lý do rõ ràng, thay vì biến mọi invocation thành truy cập tuần tự.

**ThreadLocal không phải request-local.** Với thread pool, thread có thể được dùng lại cho request khác. Nếu không xóa đúng lúc, `ThreadLocal` giữ dữ liệu cũ; trong xử lý async/reactive, một request có thể chuyển thread. Tránh dùng `ThreadLocal` để giữ `ConstraintValidatorContext`, input hoặc danh sách lỗi. Biến local là lựa chọn trực tiếp và dễ kiểm chứng hơn.

## 7. Kiểm thử validation trên nhiều thread

Test một thread chỉ kiểm tra nghiệp vụ cơ bản. Để tăng khả năng phát hiện race condition, hãy gọi **cùng một `Validator`** từ nhiều thread với input hợp lệ/không hợp lệ xen kẽ. Với ví dụ `ConcurrentValidationApplication`, thêm dependency sau vào `pom.xml` nếu dự án chưa có:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Tạo file **`src/test/java/com/example/validation/ConcurrentValidationApplicationTest.java`**:

~~~java
package com.example.validation;

import jakarta.validation.Validator;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class ConcurrentValidationApplicationTest {

    @Autowired
    Validator validator;

    @Test
    void validatesIndependentInputsAcrossThreads() throws Exception {
        int total = 400;
        var start = new CountDownLatch(1);
        var pool = Executors.newFixedThreadPool(8);

        try {
            List<Future<Boolean>> results = new ArrayList<>();

            for (int i = 0; i < total; i++) {
                final int index = i;

                results.add(pool.submit(() -> {
                    start.await();
                    boolean expectedValid = index % 2 == 0;
                    String code = expectedValid
                            ? "PRD-AB-1234"
                            : "PRD-ab-1234";

                    var violations = validator.validate(
                            new ConcurrentValidationApplication.Product(code));

                    if (expectedValid) {
                        return violations.isEmpty();
                    }

                    return violations.size() == 1
                            && "code".equals(
                                    violations.iterator().next()
                                            .getPropertyPath().toString());
                }));
            }

            // Cho các worker đang chờ cùng tiếp tục.
            start.countDown();

            for (Future<Boolean> result : results) {
                assertTrue(result.get(10, TimeUnit.SECONDS));
            }
        } finally {
            start.countDown();
            pool.shutdownNow();
        }
    }
}
~~~

Chạy bằng `./mvnw test`, hoặc `mvnw.cmd test` trên Windows. Test gửi 400 tác vụ qua pool 8 thread; một nửa dữ liệu hợp lệ, một nửa vi phạm `@CodePattern`. `CountDownLatch` giúp các thread đã chờ bắt đầu gần nhau; `Future#get` đưa kết quả/exception của mỗi tác vụ về thread test để assert. Test kiểm tra rằng kết quả của mỗi invocation thuộc đúng dữ liệu của invocation đó.

**Cần hiểu giới hạn test:** test pass không chứng minh không thể có race condition; chỉ cho thấy không phát hiện lỗi trong các interleaving thực sự xảy ra. Kết hợp test với review ownership của từng object mutable, test boundary cases, và kiểm tra dependency dùng chung.

Các case đáng kiểm tra thêm:

| Case | Kỳ vọng |
| --- | --- |
| Hai input hợp lệ khác nhau song song | Cả hai hợp lệ, không đọc nhầm field. |
| Input hợp lệ xen input không hợp lệ | Kết quả gắn đúng input và property path. |
| `null` và blank đồng thời | Chỉ `@NotBlank` báo lỗi thiếu dữ liệu, không có lỗi regex nhân đôi. |
| Hai annotation cùng validator class nhưng khác cấu hình | Không lẫn rule cấu hình giữa constraints. |
| Constraint cấp class tạo nhiều field errors | Đường dẫn mỗi lỗi thuộc đúng DTO. |
| Có dependency/caching ở trong validator | Không rò rỉ dữ liệu người dùng hoặc gây kết quả thiếu nhất quán. |

## 8. Lỗi thường gặp và hướng khắc phục

1. **Lưu giá trị hiện tại vào field** như `lastInput`, `currentUser`, `currentDto`: có thể bị request khác ghi đè. **Sửa:** dùng tham số và biến local.
2. **Chia sẻ `Matcher`** giữa invocation: matcher mutable, không thread-safe. **Sửa:** chia sẻ `Pattern`, tạo `Matcher` mới cho từng invocation.
3. **Tích lũy lỗi vào `ArrayList`/`HashMap` field**: vừa có race vừa có nguy cơ giữ lỗi từ request cũ. **Sửa:** collection local hoặc tạo custom violations trên context của lần gọi.
4. **Lưu `ConstraintValidatorContext`/builder làm field**: một lời gọi có thể dùng context của lời gọi khác. **Sửa:** xây lỗi hoàn chỉnh ngay trong `isValid`.
5. **Ghi lại pattern/rule trong `isValid`**: cấu hình của request A ảnh hưởng request B. **Sửa:** thiết lập rule trong `initialize`, sau đó chỉ đọc.
6. **Tưởng `initialize` chạy trước mỗi request**: provider có quyền tái sử dụng instance. **Sửa:** xem đó là bước khởi tạo instance.
7. **Dùng `SimpleDateFormat` hoặc parser mutable dùng chung**: trạng thái parser bị thay đổi đồng thời. **Sửa:** formatter immutable như `DateTimeFormatter` hoặc parser local.
8. **Dùng `ThreadLocal` như bộ nhớ request**: thread pool có thể giữ giá trị cũ. **Sửa:** tránh state theo request trong validator.
9. **Một collaborator không thread-safe**: bản thân validator stateless vẫn có lỗi khi gọi service có state không an toàn. **Sửa:** audit dependency graph và hợp đồng đồng thời.
10. **Sửa DTO trong khi validate**: vi phạm contract và có nguy cơ race với tầng nghiệp vụ. **Sửa:** chỉ đọc, không normalize bằng mutation trong `isValid`.
11. **Bỏ qua các trường hợp null/blank**: có thể tạo nhiều lỗi chồng nhau hoặc NullPointerException. **Sửa:** xác định rõ trách nhiệm của từng constraint; dùng `@NotNull`/`@NotBlank` cho dữ liệu thiếu.
12. **Chỉ chạy test một thread**: không kích thích race. **Sửa:** test kết hợp đa luồng và review mô hình sở hữu state.

## 9. Checklist trước khi đưa validator vào production

- [ ] Tất cả field trong validator đều là cấu hình không đổi sau `initialize` hoặc dependency dùng chung có hợp đồng thread-safe.
- [ ] `isValid` không ghi vào field để lưu input, lỗi, context, builder hoặc biến tạm của lần gọi.
- [ ] Với regex, `Pattern` được dùng chung; `Matcher` được tạo local.
- [ ] Không sửa `value` hoặc đối tượng con của nó khi validation.
- [ ] Lỗi tùy chỉnh gọi đầy đủ `addConstraintViolation()` và không giữ context quá thời gian invocation.
- [ ] Không dựa vào một instance/request, thứ tự của `ConstraintViolation` Set, hay `ThreadLocal` để định danh request.
- [ ] Review thread-safety của dependency, cache, parser và logic đọc dữ liệu bên ngoài.
- [ ] Test dữ liệu đúng/sai/thiếu, property path và các invocation đồng thời.

**Ghi nhớ:** provider có thể gọi `isValid` đồng thời trên cùng một `ConstraintValidator`. Giữ **configuration immutable sau khởi tạo** và **invocation data trong tham số/biến local** giúp validation chính xác, an toàn và mở rộng tốt trong ứng dụng Spring.

## Tài liệu tham khảo

- Jakarta Validation API 3.1 — `ConstraintValidator` (thread-safety, `initialize`): https://javadoc.io/static/jakarta.validation/jakarta.validation-api/3.1.1/jakarta/validation/ConstraintValidator.html
- Jakarta Bean Validation specification 3.0 — lifecycle và caching: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.pdf
- Hibernate Validator Reference Guide — custom constraints, `ConstraintValidatorFactory`: https://docs.hibernate.org/stable/validator/reference/en-US/html_single/
- JDK 17 — `Pattern` (thread-safe): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html
- JDK 17 — `Matcher` (non-thread-safe): https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Matcher.html
