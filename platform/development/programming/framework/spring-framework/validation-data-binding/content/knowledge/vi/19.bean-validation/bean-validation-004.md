# ValidatorFactory, Validator và vòng đời tài nguyên

> **Bối cảnh:** Jakarta Bean Validation (Hibernate Validator là một provider phổ biến) trong ứng dụng Java và Spring Framework. Bài này phân biệt vai trò của `ValidatorFactory`, `Validator`, `ConstraintValidatorFactory` và `ConstraintValidator`, cách quản lý tài nguyên, tính an toàn khi dùng nhiều luồng, cũng như điểm khác nhau giữa việc tự bootstrap và để Spring quản lý. Ví dụ sử dụng Java 17+ và Spring Boot 3.3.x / Spring Framework 6.x.

## 1. Tại sao cần phân biệt factory và validator?

Bean Validation cho phép khai báo ràng buộc trên model bằng annotation, như `@NotNull`, `@NotBlank`, `@Min`, `@Size` và constraint tùy chỉnh. Annotation chỉ là **metadata**; cần một implementation của Jakarta Validation API (gọi là *provider*, ví dụ Hibernate Validator) để đọc metadata, chọn logic kiểm tra và tạo kết quả.

Trong API `jakarta.validation`:

- **`ValidatorFactory`** là đối tượng được tạo khi **bootstrap** provider. Nó giữ cấu hình chung, có thể chuẩn bị/cache metadata và tạo hoặc cung cấp các `Validator`. Việc tạo factory thường tốn chi phí hơn việc lấy validator. Factory được thiết kế để chia sẻ và phải được đóng khi hết vòng đời sử dụng.
- **`Validator`** là điểm gọi nghiệp vụ, thực thi `validate(...)`, `validateProperty(...)` và `validateValue(...)`, trả về `Set<ConstraintViolation<T>>`. Validator nhẹ, theo hợp đồng API là *thread-safe*, và **không có `close()`**.
- **`ConstraintValidatorFactory`** là thành phần được provider sử dụng để tạo/giải phóng **implementation của từng constraint**, chẳng hạn lớp kiểm tra annotation `@ValidSku`. Nó **không đồng nghĩa** với `ValidatorFactory`.
- **`ConstraintValidator<A,T>`** chứa logic `initialize(A)` (nếu cần) và `isValid(T, ConstraintValidatorContext)` để kiểm tra một giá trị. Việc tạo, cache và release instance thuộc provider cùng `ConstraintValidatorFactory`.

Sơ đồ quan hệ:

```text
Application / Spring container
          │
          ▼
  ValidatorFactory  ────── cấu hình, metadata, cache (tùy provider)
          │
          ├──── getValidator() ────► Validator
          │                              │
          │                              └── validate(order) ───► Set<ConstraintViolation>
          │
          └──── ConstraintValidatorFactory ──► ConstraintValidator instances
                        tạo / release              initialize / isValid

  Chủ sở hữu factory ─────► close() khi hết vòng đời
```

Điều cốt lõi: **tạo factory theo vòng đời ứng dụng hoặc đơn vị triển khai, lấy/reuse validator để xử lý các lần kiểm tra, chỉ đóng factory do mình sở hữu**.

## 2. So sánh cụ thể các đối tượng

| Đối tượng | Tạo ở đâu | Dùng làm gì | Phạm vi/vòng đời nên dùng | Trách nhiệm đóng |
| --- | --- | --- | --- | --- |
| `jakarta.validation.ValidatorFactory` | `Validation.buildDefaultValidatorFactory()`, builder provider, hoặc do Spring khởi tạo | Khởi tạo/cấp `Validator`, cấu hình chung, chia sẻ metadata | Một instance dùng lại trong đơn vị triển khai hoặc một cấu hình chuyên biệt | **Người/container tạo factory** gọi `close()` đúng lúc |
| `jakarta.validation.Validator` | `factory.getValidator()` hoặc `factory.usingContext().getValidator()`; cũng có thể được Spring inject | Kiểm tra bean/property/value, lấy metadata, trả về violations | Dùng lại ở nhiều request và nhiều luồng theo API | Không có `close()`; không dùng tiếp sau khi factory cha đóng |
| `jakarta.validation.ValidatorContext` | `factory.usingContext()` | Tùy chỉnh cấu hình cho validator cụ thể (ví dụ clock, interpolator) | Context để xây một validator từ factory hiện tại | Không đóng riêng; factory vẫn là chủ sở hữu tài nguyên |
| `jakarta.validation.ConstraintValidatorFactory` | Provider hoặc integration/container cấu hình | Tạo và release instance kiểm tra constraint | Phụ thuộc cấu hình provider và DI | Provider gọi `releaseInstance` theo đúng hợp đồng; không tự giải phóng instance đang được provider quản lý |
| `jakarta.validation.ConstraintValidator` | Provider yêu cầu `ConstraintValidatorFactory` tạo | Thực hiện logic ràng buộc | Do provider quyết định cache/tái sử dụng | Không tự tạo/đóng trong từng request; viết `isValid` an toàn đa luồng |

**Đừng nhầm API cùng tên:** Spring còn có `org.springframework.validation.Validator` với `supports(Class<?>)` và `validate(Object, Errors)`. Đây là giao diện của Spring cho cơ chế `Errors`/`BindingResult`, khác với `jakarta.validation.Validator` trả về `ConstraintViolation`. `LocalValidatorFactoryBean` của Spring là cầu nối có thể phục vụ cả hai giao diện.

## 3. Vòng đời đúng khi tự sử dụng Jakarta Validation

### 3.1. Bootstrap một lần, sử dụng nhiều lần, close một lần

```text
Khởi động / mở một đơn vị công việc dài hạn
    │
    ▼
Validation.buildDefaultValidatorFactory()
    │
    ├─► getValidator() ─► validate(bean A)
    │                  ├► validate(bean B)
    │                  └► validate(bean C)
    │
    └─► usingContext() ─► getValidator() ─► validate(bean D)
    │
Kết thúc vòng đời do chính mình sở hữu
    ▼
factory.close()
    └─► không tiếp tục sử dụng factory hoặc các Validator do nó tạo
```

Theo đặc tả Jakarta Validation, `ValidatorFactory` và `Validator` đều **thread-safe**; một factory có thể phục vụ nhiều luồng và validator có thể được chia sẻ. Provider có thể cache metadata và validator. Không có yêu cầu tạo factory mỗi request, mỗi lần gọi `validate` hoặc mỗi lần gặp một DTO khác.

`ValidatorFactory` mở rộng `AutoCloseable`; trong code tự quản lý nên dùng `try-with-resources` nếu thời gian sống của factory có điểm bắt đầu/kết thúc rõ. Nếu là ứng dụng chạy dài hạn, tạo factory khi startup và đóng ở shutdown. Gọi `close()` khiến factory không còn sử dụng được; **mọi validator được tạo từ factory đó cũng không được tiếp tục dùng**. Hành vi dùng tiếp là không portable/không được đặc tả bảo đảm.

### 3.2. Ví dụ Java 17+ chạy được

Tạo Maven project:

```text
validation-lifecycle/
├── pom.xml
└── src/main/java/demo/ValidatorLifecycleDemo.java
```

**`pom.xml`** — `spring-boot-starter-validation` đưa Jakarta Validation API và provider Hibernate Validator vào classpath. Chương trình là một Java `main` độc lập, **không khởi tạo Spring ApplicationContext**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>validation-lifecycle</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

**`src/main/java/demo/ValidatorLifecycleDemo.java`**:

```java
package demo;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import java.util.List;

public class ValidatorLifecycleDemo {

    static final class Order {
        @NotBlank
        private final String customer;

        @Min(1)
        private final int quantity;

        Order(String customer, int quantity) {
            this.customer = customer;
            this.quantity = quantity;
        }
    }

    public static void main(String[] args) {
        // Đây là factory do main() tạo, nên main() có trách nhiệm đóng.
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            List<String> errors = validator
                    .validate(new Order("", 0))
                    .stream()
                    .map(ValidatorLifecycleDemo::describe)
                    .sorted()
                    .toList();

            System.out.println("violations=" + errors.size());
            errors.forEach(System.out::println);

            boolean valid = validator
                    .validate(new Order("Mai", 2))
                    .isEmpty();
            System.out.println("valid=" + valid);

        } // Gọi factory.close(), kể cả khi có exception.
    }

    private static String describe(ConstraintViolation<?> violation) {
        String field = violation.getPropertyPath().toString();
        String constraint = violation.getConstraintDescriptor()
                .getAnnotation()
                .annotationType()
                .getSimpleName();
        return field + ":" + constraint;
    }
}
```

Dùng JDK 17+ và Maven, chạy từ thư mục chứa `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ValidatorLifecycleDemo
```

Các dòng **do chương trình in ra**, không tính log nếu Maven/provider in thêm:

```text
violations=2
customer:NotBlank
quantity:Min
valid=true
```

Giải thích: `@NotBlank` thất bại với chuỗi rỗng; `@Min(1)` thất bại với số `0`. `ConstraintViolation` được chuyển thành chuỗi `field:ConstraintName` và **sắp xếp** để output không phụ thuộc thứ tự duyệt `Set`; không in message đã dịch nên kết quả cũng không phụ thuộc locale. Với `Order("Mai", 2)`, không có vi phạm. Các `Validator` không tự tạo/đóng tài nguyên riêng; `try-with-resources` đảm bảo factory do `main()` tạo được đóng.

**Tại sao không dùng `try (Validator v = ...)`?** `Validator` không phải tài nguyên `AutoCloseable`. Chỉ `ValidatorFactory` ở ví dụ này cần `close()`. Đừng đóng factory ngay sau `getValidator()` rồi trả validator cho code bên ngoài: validator ấy sẽ có vòng đời không hợp lệ.

### 3.3. Khi cần cấu hình validator riêng

Factory có thể tạo validator với cấu hình riêng mà không phải bootstrap một factory mới. Ví dụ dưới đây là **đoạn code minh họa đặt bên trong scope của factory còn mở** (cần import `java.time.Clock`):

```java
Validator utcValidator = factory.usingContext()
        .clockProvider(Clock::systemUTC)
        .getValidator();
```

`ClockProvider` là thành phần giúp các constraint thời gian như `@Future`/`@Past` lấy thời điểm tham chiếu. `utcValidator` thuộc cùng factory, chịu vòng đời đóng của factory đó. Hãy dùng `usingContext()` cho khác biệt cục bộ về clock, interpolator hoặc các thành phần hỗ trợ khác; nếu cần một cấu hình chung toàn ứng dụng, cấu hình ở lúc xây factory (hoặc qua Spring).

## 4. Spring quản lý `ValidatorFactory` và `Validator` như thế nào?

Trong một ứng dụng Spring có Jakarta Validation provider trên classpath, Spring có thể khởi tạo `LocalValidatorFactoryBean`. Lớp này:

1. Bootstrap provider lúc Spring khởi tạo bean (qua lifecycle của bean và `afterPropertiesSet()`).
2. Đóng vai trò adapter cho `jakarta.validation.ValidatorFactory` và `jakarta.validation.Validator`.
3. Cũng hỗ trợ `org.springframework.validation.Validator` và `SmartValidator` để tích hợp với `DataBinder`, `BindingResult`, `@Valid`, `@Validated`.
4. Tích hợp `SpringConstraintValidatorFactory` để constraint validator tùy chỉnh có thể được Spring hỗ trợ tiêm dependency.
5. Thực thi `destroy()`/`close()` khi bean bị hủy, đóng validator factory mà nó sở hữu.

Với **Spring Boot 3.x** đã có `spring-boot-starter-validation` và auto-configuration phù hợp, thường chỉ cần **inject `jakarta.validation.Validator`**; Boot quản lý bean và vòng đời. Không tạo thêm `Validation.buildDefaultValidatorFactory()` trong service/controller và không gọi `close()` trên bean được inject.

Ví dụ **đoạn service đặt trong một dự án Spring Boot đang chạy** (không phải chương trình độc lập):

```java
package demo;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import jakarta.validation.constraints.NotBlank;
import org.springframework.stereotype.Service;

import java.util.Set;

@Service
public class RegistrationService {
    private final Validator validator;

    public RegistrationService(Validator validator) {
        this.validator = validator; // do Spring container sở hữu
    }

    public Set<ConstraintViolation<Registration>> check(Registration item) {
        return validator.validate(item);
    }

    public record Registration(@NotBlank String username) { }
}
```

`RegistrationService` có thể được Spring dùng qua nhiều request; injected validator theo hợp đồng là thread-safe. Đối tượng `Registration` chứa dữ liệu request riêng, **không cần và không nên** dùng lại giữa các request. Nếu muốn trả lỗi HTTP, hãy thiết kế lớp xử lý `ConstraintViolation` rõ ràng; gọi `validate(...)` chỉ **trả về các vi phạm**, không tự ném lỗi HTTP.

**Tạo bean khi cấu hình Spring Framework thủ công:** Khi chưa có bean validator tương đương, cấu hình sau để Spring sở hữu factory:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;

@Configuration
public class ValidationConfiguration {
    @Bean
    public LocalValidatorFactoryBean validator() {
        return new LocalValidatorFactoryBean();
    }
}
```

Spring gọi các lifecycle callback để khởi tạo và hủy bean. **Trong Spring Boot đã auto-configure validator, đừng thêm đoạn cấu hình này một cách máy móc**: nó có thể tạo bean khác hoặc ảnh hưởng lựa chọn validator. Chỉ tự định nghĩa khi cần override/cấu hình cụ thể và đã kiểm tra bean hiện hữu.

### 4.1. Ranh giới sở hữu: ai tạo thì người đó đóng

| Tình huống | Chủ sở hữu | Cách kết thúc |
| --- | --- | --- |
| Java `main` tự gọi `Validation.buildDefaultValidatorFactory()` | Chính ứng dụng/đoạn code đó | `try-with-resources` hoặc gọi `close()` ở shutdown |
| Spring Boot cung cấp `jakarta.validation.Validator` qua DI | Spring application context | Để context hủy bean/factory theo lifecycle; **không đóng thủ công** trong service |
| Cấu hình `@Bean LocalValidatorFactoryBean` riêng | Spring context quản lý bean | Spring gọi `destroy()`/`close()` khi hủy |
| Bài test tạo riêng factory ngoài Spring | Test đó hoặc fixture dùng chung | Đóng trong `@AfterAll` hoặc `try-with-resources` tương ứng scope |
| Validator lấy từ factory đã được đóng | Factory không còn hợp lệ | **Không dùng tiếp**; tạo/lấy validator từ factory còn sống |

Nếu code tự tạo một `ValidatorFactory` rồi truyền `Validator` của nó vào singleton Spring mà đóng factory ngay sau startup, singleton có tham chiếu đến validator không còn vòng đời hợp lệ. Ngược lại, nếu cứ tạo factory trong mỗi lần gọi API mà không đóng, có nguy cơ giữ lại metadata/cache và các tài nguyên provider cho đến khi process kết thúc.

### 4.2. `jakarta.validation.Validator` và Spring `Validator`

| Jakarta Validation | Spring Validation |
| --- | --- |
| `jakarta.validation.Validator#validate(bean, groups...)` | `org.springframework.validation.Validator#validate(target, Errors)` |
| Trả `Set<ConstraintViolation<T>>` | Ghi `FieldError`/`ObjectError` vào `Errors`/`BindingResult` |
| Dùng trực tiếp khi kiểm tra DTO/domain, service, batch job | Dùng trong data binding, validation kiểu Spring MVC, custom validator |
| Không có `supports(Class<?>)` | Có `supports(Class<?>)` |
| Thường được gọi bởi provider Jakarta | Có thể được bridge bởi `LocalValidatorFactoryBean` |

Khi import `Validator` vào Java, ghi rõ package nếu có nguy cơ nhầm. `@Valid` trên tham số controller cùng cấu hình MVC có thể kích hoạt Bean Validation khi Spring bind và kiểm tra dữ liệu; việc gọi trực tiếp `validator.validate(bean)` trong service chỉ trả kết quả, trừ khi code tự quyết định ném exception.

## 5. Chi tiết vòng đời của `ConstraintValidator`

Với ràng buộc tùy chỉnh, ví dụ annotation `@ValidSku` trỏ tới `SkuValidator implements ConstraintValidator<ValidSku,String>`, chu trình điển hình là:

```text
Provider chọn constraint descriptor
      │
      ▼
ConstraintValidatorFactory.getInstance(SkuValidator.class)
      │
      ▼
SkuValidator.initialize(annotation)   (nếu có thông số annotation)
      │
      ▼
SkuValidator.isValid(value, context)   (có thể được gọi nhiều lần / nhiều luồng)
      │
      ▼
Provider giữ lại hoặc giải phóng theo chiến lược triển khai
      │
      ▼
ConstraintValidatorFactory.releaseInstance(instance)
```

Đặc tả yêu cầu provider giải phóng các instance mà factory đã cung cấp. Instance phải được **release bởi chính `ConstraintValidatorFactory` đã tạo ra nó**. Với các instance do factory cấp ở phạm vi `ValidatorFactory`, việc release có thể diễn ra khi đóng `ValidatorFactory`. Vì thế, **không suy rằng mỗi lần gọi `validate` đều có một instance mới**, hoặc instance sẽ bị hủy ngay sau một request.

Điều này ảnh hưởng thiết kế custom constraint:

- `initialize(...)` có thể nạp **cấu hình theo annotation** vào field. Cấu hình đó nên ổn định sau khi khởi tạo.
- `isValid(...)` **phải thread-safe** theo Jakarta Validation. Không lưu “giá trị đang validate”, “request hiện tại”, hoặc “kết quả lần gọi trước” vào mutable instance fields mà nhiều luồng có thể ghi.
- Dùng biến cục bộ cho trạng thái của từng lần validate. Dependency được inject vào constraint validator (ví dụ repository/service tra cứu) cũng phải đáp ứng vòng đời và tính an toàn phù hợp.
- `ConstraintValidatorFactory` tự viết **không nên cache instance tùy tiện**: provider có thể khởi tạo/cấu hình validator qua `initialize`; cache sai có thể giữ state của constraint này cho constraint khác.
- Khi tích hợp Spring, `SpringConstraintValidatorFactory` cho phép tạo đối tượng qua `AutowireCapableBeanFactory` rồi release theo hợp đồng. Không nên vừa tạo instance thủ công, vừa trông chờ Spring quản lý/tiêm dependency cho instance đó.
- Đừng nhầm cleanup của `ConstraintValidator` với cleanup của `ValidatorFactory`. Provider quyết định lúc gọi `releaseInstance`; **chủ sở hữu factory** quyết định lúc gọi `close()`.

Ví dụ **minh họa phần implementation custom constraint** (annotation `ValidSku` được giả định đã định nghĩa riêng; không phải chương trình độc lập):

```java
public final class SkuValidator
        implements ConstraintValidator<ValidSku, String> {

    private String prefix;

    @Override
    public void initialize(ValidSku rule) {
        this.prefix = rule.prefix(); // cấu hình cố định cho instance
    }

    @Override
    public boolean isValid(String sku,
                           ConstraintValidatorContext context) {
        return sku == null || sku.startsWith(prefix);
        // Biến sku là đối số của lần gọi, không lưu trong field.
    }
}
```

Quy tắc xử lý `null` là lựa chọn theo contract của constraint: nhiều constraint để `null` hợp lệ và kết hợp `@NotNull` nếu field bắt buộc, như ví dụ trên. Không dùng biến field tăng counter cho từng request trong `isValid` trừ khi đã thiết kế đồng bộ hóa có lý do rõ ràng.

## 6. Độ an toàn đa luồng và chi phí hiệu năng

### 6.1. Những gì API bảo đảm

- `ValidatorFactory` implementations phải thread-safe.
- `Validator` implementations phải thread-safe.
- `ConstraintValidator#isValid(...)` implementations phải thread-safe.
- Provider có thể dùng chung/cache metadata, `Validator` và một số `ConstraintValidator`. **Không dựa vào danh tính của instance hoặc số lần constructor được gọi** làm logic nghiệp vụ.
- Việc lấy `Validator` từ factory thường rẻ hơn bootstrap factory mới. Tái sử dụng factory giúp tránh khởi tạo metadata/configuration lặp lại.

### 6.2. Những điều **không** được suy ra từ thread safety

- `@NotNull` trên đối tượng không biến đối tượng được validate thành thread-safe. Hai request vẫn phải dùng DTO hoặc trạng thái riêng.
- Một `ConstraintValidator` có mutable fields thay đổi trong `isValid` có thể gây data race, dù `Validator` phía trên là thread-safe.
- Kết quả `Set<ConstraintViolation<T>>` thuộc mỗi lần gọi; không chia sẻ và chỉnh sửa kết quả giữa các request như state dùng chung.
- Dùng cùng một `Validator` không có nghĩa mọi dependency bên dưới đều thread-safe; custom provider, message interpolator, resolver và collaborator phải tuân thủ hợp đồng tương ứng.
- Không phải mọi annotation đều được kiểm tra tự động ở mọi nơi: đối tượng phải đi qua cơ chế trigger, ví dụ gọi `validate(...)`, Spring MVC `@Valid`, hoặc method validation được cấu hình.

**Ví dụ lỗi hiệu năng/cleanup:** Trong controller mỗi request tạo một factory bằng `buildDefaultValidatorFactory()`, gọi validate rồi quên close. Điều đó có thể tạo ra nhiều factory/cache không cần thiết và khó quản lý lifecycle. Sửa bằng inject một `Validator` từ Spring hoặc dùng một factory do ứng dụng sở hữu, được đóng khi shutdown.

## 7. Khi nào kết quả validation xảy ra trong Spring?

Một `Validator` không chủ động theo dõi mọi lần setter hoặc mọi lần tạo object. Validation xảy ra tại **điểm kích hoạt**:

1. **Gọi thủ công** `validator.validate(obj)`: nhận về một `Set<ConstraintViolation>`; người gọi quyết định xử lý lỗi.
2. **Spring MVC data binding + `@Valid` / `@Validated`**: MVC xác thực argument theo cấu hình; với controller method phù hợp, lỗi binding/validation có thể được chuyển thành `BindingResult` hoặc exception do Spring xử lý.
3. **Method validation ở service**: khi cấu hình method validation và bean được proxy/intercept phù hợp (thường dùng `@Validated` ở class trong Spring Boot 3.x), các constraint ở tham số/return value có thể được kiểm tra. **Self-invocation** trong cùng object thường không đi qua proxy.
4. **Batch/job/test**: gọi validator trực tiếp bằng code, không cần HTTP hoặc Spring MVC.

Việc `@Valid` có mặt trong DTO **không có nghĩa** một lời gọi `new MyDto(...)` sẽ tự chạy validation. `@Valid` chủ yếu đánh dấu *cascaded validation* hoặc điểm kiểm tra khi framework tích hợp yêu cầu; vẫn cần một trigger.

## 8. Lỗi thường gặp và cách sửa

| Lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| `Validation.buildDefaultValidatorFactory()` mỗi request | Tốn bootstrap và có thể giữ tài nguyên lâu không cần thiết | Bootstrap một lần theo vòng đời chủ sở hữu, hoặc inject validator do Spring quản lý |
| Không gọi `close()` cho factory tự tạo | Tài nguyên/cache của provider không được giải phóng có chủ đích | `try-with-resources` hoặc cleanup ở shutdown |
| Đóng factory do Spring/container cung cấp trong service | Các thành phần khác giữ validator có thể bị ảnh hưởng | Chỉ container đóng factory nó quản lý |
| Giữ `Validator` sau khi factory đóng | Sử dụng ngoài vòng đời, hành vi không được bảo đảm | Giữ factory còn sống trong suốt thời gian sử dụng |
| Gọi `validator.close()` | API `Validator` không có phương thức này | Đóng `ValidatorFactory` khi cần |
| Tạo `ConstraintValidator` bằng `new` để mong Spring inject dependency | Instance không đi qua Spring factory | Dùng provider và Spring `ConstraintValidatorFactory` phù hợp |
| `isValid` sửa field trạng thái theo request | Race condition hoặc kết quả sai khi nhiều luồng | Dùng biến cục bộ, cấu hình bất biến, collaborator thread-safe |
| Custom `ConstraintValidatorFactory` cache mọi instance | State từ `initialize` có thể bị sử dụng sai | Tuân thủ get/release và để provider quản lý cache |
| Dùng nhầm hai lớp `Validator` | Sai API và cách nhận lỗi | Kiểm tra package `jakarta.validation` hay `org.springframework.validation` |
| Nghĩ `@Valid` tự chạy khi gọi constructor | Không có trigger, lỗi bị bỏ qua | Gọi `validate` hoặc dùng integration ở boundary |
| Dùng `javax.validation.*` với Spring Boot 3.x | Trộn hệ API Jakarta và thư viện cũ | Dùng `jakarta.validation.*` và provider tương thích |
| Dựa vào thứ tự của `Set<ConstraintViolation>` để tạo output chuẩn | Thứ tự trả về không phải contract ổn định | Sắp xếp theo thuộc tính/vi phạm trước khi in hoặc so sánh |

## 9. Checklist rà soát một ứng dụng

**Khởi tạo và sở hữu**

- [ ] Có provider thật trong classpath (ví dụ `spring-boot-starter-validation`) thay vì chỉ có annotation API?
- [ ] Factory được bootstrap theo vòng đời ứng dụng/fixture, không ở đường nóng mỗi request?
- [ ] Xác định được chủ sở hữu factory và thời điểm `close()`?
- [ ] Có tách bạch factory tự tạo với factory/validator Spring quản lý?

**Sử dụng và luồng**

- [ ] `Validator` có được dùng lại một cách hợp lý, không cố đóng riêng?
- [ ] Không sử dụng validator khi factory gốc đã đóng?
- [ ] Custom `ConstraintValidator#isValid` có an toàn khi được gọi đồng thời?
- [ ] Custom `ConstraintValidatorFactory` có tuân thủ đúng cặp tạo/release?

**Hành vi và kiểm thử**

- [ ] Có trigger validation tại HTTP/service/batch/test đúng nơi cần?
- [ ] Kiểm thử cùng một DTO hợp lệ và không hợp lệ, bao gồm violations mong đợi?
- [ ] Có kiểm thử lifecycle cho factory do ứng dụng tự sở hữu, ít nhất xác nhận nhánh cleanup được chạy khi dừng hoặc khi lỗi?
- [ ] Không phụ thuộc vào thứ tự `Set`, thông điệp đã địa phương hóa, hoặc số lần provider tạo `ConstraintValidator` trong assertion?

## 10. Tổng kết tư duy thiết kế

`ValidatorFactory` là **tài nguyên cấu hình và khởi tạo** với vòng đời có điểm kết thúc. `Validator` là **API dùng để xác thực**, nhẹ và an toàn để chia sẻ theo hợp đồng; nó không có hàm `close()` riêng. `ConstraintValidatorFactory` quản lý instance của logic ràng buộc theo yêu cầu provider. Trong Spring, `LocalValidatorFactoryBean` nối các API này với dependency injection và lifecycle của application context. Hãy để đối tượng **tạo/sở hữu factory** chịu trách nhiệm đóng, và giữ validator sống đúng trong khoảng thời gian factory còn hoạt động.

### Tài liệu tham khảo chính thức

- [Jakarta Bean Validation 3.0 Specification — ValidatorFactory, Validator và ConstraintValidatorFactory](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Jakarta Validation 3.1 Specification — Bootstrap, lifecycle và thread safety](https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html)
- [Jakarta ValidatorFactory API — AutoCloseable và close()](https://jakarta.ee/specifications/platform/10/apidocs/jakarta/validation/validatorfactory)
- [Spring Framework — Java Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Boot — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html)
