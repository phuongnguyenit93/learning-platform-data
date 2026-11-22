# MethodValidationPostProcessor và bean có @Validated trong Spring Framework

## 1. Tại sao phải kiểm tra ở ranh giới phương thức?

Bean Validation không chỉ kiểm tra thuộc tính của một DTO/entity. Nó còn có **executable validation**: kiểm tra tham số mà một phương thức nhận vào và giá trị phương thức trả về. Điều này đặc biệt hữu ích ở lớp service, nơi nhiều caller khác nhau có thể gọi cùng một nghiệp vụ: controller HTTP, message consumer, job định kỳ hoặc một service khác.

Ví dụ, hợp đồng của một phương thức có thể là:

```java
@NotBlank
public String reserve(@NotBlank String productCode, @Min(1) int quantity) {
    return "reserved:" + productCode + ":" + quantity;
}
```

Ba ràng buộc độc lập ở đây là: `productCode` phải có nội dung, `quantity` ít nhất bằng 1, và kết quả trả về không được là chuỗi trống/trắng. Những annotation này mô tả hợp đồng, nhưng **chúng không tự động làm mọi lời gọi Java được kiểm tra**.

Trong một bean do Spring quản lý, `org.springframework.validation.beanvalidation.MethodValidationPostProcessor` là thành phần hạ tầng kết nối Jakarta Bean Validation với **Spring AOP proxy**. Bean được đánh dấu `org.springframework.validation.annotation.Validated` ở cấp lớp sẽ đủ điều kiện để Spring tạo advice kiểm tra đầu vào/đầu ra khi lời gọi đi qua proxy.

Đây là trọng tâm của bài: **cách post-processor chọn bean có `@Validated`, tạo proxy và thực thi method validation, cùng giới hạn của cơ chế ấy**.

## 2. Các vai trò cần phân biệt

| Thành phần | Trách nhiệm |
| --- | --- |
| `@Validated` của Spring | Ở cấp lớp, đánh dấu bean đủ điều kiện để method-validation advice áp dụng; có thể chỉ định validation groups. |
| `MethodValidationPostProcessor` | BeanPostProcessor hạ tầng tìm bean phù hợp, gắn advisor/interceptor và giúp tạo AOP proxy. |
| `MethodValidationInterceptor` | Chạy logic kiểm tra tham số trước lời gọi, và kết quả trả về sau lời gọi, thông qua Bean Validation. |
| `jakarta.validation.Validator`/`ExecutableValidator` | Engine/provider thực sự thực thi constraint (thường Hibernate Validator). |
| `@NotNull`, `@Min`, `@NotBlank`, ... | Constraint trực tiếp trên tham số hoặc giá trị trả về. |
| `@Valid` của Jakarta | Đánh dấu cascade vào các thuộc tính bên trong đối tượng tham số/giá trị trả về. |
| `@Validated` ở cấp phương thức | Có thể thay đổi nhóm validation cho phương thức đã thuộc bean đủ điều kiện; **không tự tạo pointcut cho một bean thiếu `@Validated` cấp lớp**. |

Trong Spring Framework 6.x/Spring Boot 3.x, import tương ứng là `jakarta.validation.*`. Tránh trộn với namespace `javax.validation.*` của các phiên bản cũ.

Một `@Validated` đơn độc cũng **không phải** một constraint; nó không cấm `null`, không kiểm tra độ dài chuỗi. Constraint cụ thể hoặc cascade metadata mới xác định điều cần kiểm tra.

## 3. Điều kiện để bean được kiểm tra

Để method validation theo cơ chế AOP hoạt động đúng, cần đồng thời có:

1. Một **Jakarta Bean Validation provider** trong classpath, ví dụ Hibernate Validator; chỉ có annotation API mà thiếu provider không đủ.
2. `MethodValidationPostProcessor` được đăng ký và khởi tạo trong Spring ApplicationContext. Trong ứng dụng Spring Boot thông thường, `spring-boot-starter-validation` cung cấp provider và Boot có auto-configuration cho method validation. Với ứng dụng Spring Framework thuần, bạn có thể tự khai báo post-processor.
3. Bean mục tiêu thuộc Spring container, được đánh dấu `@Validated` ở cấp kiểu (hoặc annotation tương đương được cấu hình làm pointcut), và có constraint hợp lệ.
4. Phương thức được gọi **qua Spring AOP proxy** và có thể được proxy áp dụng advice. Lệnh `new MyService()`, gọi trực tiếp trên target hoặc `this.otherMethod()` không đi qua proxy.
5. Phạm vi public/method có thể được proxy và kiểu proxy phù hợp với cách gọi.

Sơ đồ luồng tổng quát:

```text
Một bean khác / controller / runner
        │
        ▼
Spring bean reference (AOP proxy)
        │
        ├── validateParameters(...)  ── lỗi: ném exception, không gọi target
        │
        ▼
Target.method(arguments)
        │
        ├── phương thức ném exception? trả exception gốc theo luồng gọi
        │
        ▼
validateReturnValue(...) ── lỗi: ném exception sau khi target đã chạy
        │
        ▼
Trả kết quả cho caller
```

**Điểm quan trọng:** constraint của tham số được kiểm tra **trước** khi vào thân phương thức. Constraint trên kết quả được kiểm tra **sau** khi phương thức đã chạy. Do đó, nếu hậu điều kiện trả về bị vi phạm, side effect trong thân phương thức có thể đã xảy ra. Có transaction rollback hay không còn phụ thuộc thứ tự advice, chính sách rollback và loại exception; không nên giả định lúc nào cũng được tự động hoàn tác.

## 4. Đăng ký MethodValidationPostProcessor

### 4.1. Dùng Spring Boot

Với ứng dụng Spring Boot có provider Bean Validation, hỗ trợ method validation thường được **tự động bật**. Khi có `spring-boot-starter-validation`, không cần tự khai báo thêm `MethodValidationPostProcessor` chỉ để dùng `@Validated` cho service.

Đối với ứng dụng cần AOP đầy đủ, thêm `spring-boot-starter-aop` giúp có bộ phụ thuộc proxy/advice liên quan. Tránh định nghĩa trùng một post-processor với cấu hình Boot sẵn có nếu không có yêu cầu tùy biến.

### 4.2. Dùng Spring Framework không có auto-configuration của Boot

Trong cấu hình Spring thông thường, có thể đăng ký hạ tầng như tài liệu Spring:

```java
@Configuration
public class ValidationConfiguration {

    @Bean
    public static MethodValidationPostProcessor methodValidationPostProcessor() {
        return new MethodValidationPostProcessor();
    }
}
```

*Đây là một đoạn cấu hình tích hợp, không phải chương trình độc lập:* cần import `@Configuration`, `@Bean`, `MethodValidationPostProcessor` và một Jakarta Bean Validation provider. Phương thức `@Bean static` phù hợp vì đối tượng là BeanPostProcessor; Spring có thể đăng ký nó sớm trong vòng đời tạo các bean khác.

Theo mặc định, post-processor sử dụng loại annotation `@Validated` làm pointcut và dựa vào validator mặc định nếu không được cấu hình riêng. Các điểm tùy biến đáng biết:

- `setValidator(jakarta.validation.Validator)` hoặc `setValidatorFactory(...)` để chọn bộ máy validation.
- `setAdaptConstraintViolations(true)` để chuyển violation thành kết quả kiểu Spring `MethodValidationResult` và ném `MethodValidationException` thay vì `ConstraintViolationException`.
- `setValidatedAnnotationType(...)` nếu ứng dụng cố ý thay annotation marker mặc định.
- `setProxyTargetClass(true)` trong cấu hình liên quan nếu cần proxy theo lớp; phải xét giới hạn của class/method `final`.

Chỉ tùy biến khi có nhu cầu cụ thể. Ví dụ Java chạy ở phần sau dùng auto-configuration của Boot và hành vi exception mặc định, không tự khai báo post-processor.

## 5. Ví dụ đầy đủ chạy với Java 17 và Spring Boot 3.5.x

Ví dụ dùng **Spring Boot 3.5.6, Java 17 và Maven 3.x**. Nó không mở HTTP server, vì chủ đề cần chứng minh là method validation trên **Spring service bean**. Bốn trường hợp lần lượt minh họa tham số hợp lệ, tham số sai, kết quả sai và cascade vào DTO qua `@Valid`.

Tạo các file:

```text
method-validation-demo/
├── pom.xml
└── src/main/java/demo/
    ├── ValidationApp.java
    ├── CheckoutService.java
    └── DeliveryAddress.java
```

### `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>
    <groupId>demo</groupId>
    <artifactId>method-validation-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
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

### `DeliveryAddress.java`

```java
package demo;

import jakarta.validation.constraints.NotBlank;

public record DeliveryAddress(@NotBlank String street) {
}
```

Record này có constraint trên thành phần `street`. Khi method parameter được đánh dấu `@Valid`, provider cascade vào record và phát hiện vi phạm nếu `street` rỗng.

### `CheckoutService.java`

```java
package demo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class CheckoutService {

    @NotBlank
    public String confirm(@NotBlank String sku, @Min(1) int quantity) {
        return "receipt:" + sku + ":" + quantity;
    }

    @NotBlank
    public String badReceipt(@NotBlank String sku) {
        return ""; // Cố ý vi phạm constraint trên kết quả trả về
    }

    public String ship(@Valid DeliveryAddress address) {
        return "shipping:" + address.street();
    }
}
```

`@Service` biến class thành Spring bean. `@Validated` ở **cấp class** cho phép hạ tầng method validation chọn bean này. `confirm` có cả ràng buộc tham số lẫn kết quả; `badReceipt` có kết quả luôn sai để làm ví dụ; `ship` có cascading validation qua `@Valid`.

### `ValidationApp.java`

```java
package demo;

import java.util.List;
import java.util.function.Supplier;

import jakarta.validation.ConstraintViolationException;

import org.springframework.boot.Banner;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ValidationApp {

    public static void main(String[] args) {
        SpringApplication application = new SpringApplication(ValidationApp.class);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        try (ConfigurableApplicationContext context = application.run(args)) {
            // CommandLineRunner đã được gọi trong quá trình context khởi động.
        }
    }

    @Bean
    CommandLineRunner demo(CheckoutService service) {
        // service được Spring inject, nên đây là proxy nếu được advice.
        return args -> {
            check("VALID", () -> service.confirm("SKU-100", 2));
            check("INVALID_INPUT", () -> service.confirm("", 0));
            check("INVALID_RETURN", () -> service.badReceipt("SKU-100"));
            check("INVALID_NESTED",
                  () -> service.ship(new DeliveryAddress("")));
        };
    }

    private static void check(String label, Supplier<String> action) {
        try {
            System.out.println(label + " => " + action.get());
        } catch (ConstraintViolationException ex) {
            List<String> violated = ex.getConstraintViolations().stream()
                .map(v -> v.getConstraintDescriptor()
                    .getAnnotation().annotationType().getSimpleName())
                .sorted()
                .toList();

            System.out.println(label + " => " + String.join(", ", violated));
        }
    }
}
```

Chạy tại thư mục có `pom.xml`:

```bash
mvn -q clean package
mvn -q spring-boot:run
```

Các dòng **do ứng dụng tự in** theo thứ tự, không tính log riêng của Spring Boot/Maven/provider nếu môi trường có log:

```text
VALID => receipt:SKU-100:2
INVALID_INPUT => Min, NotBlank
INVALID_RETURN => NotBlank
INVALID_NESTED => NotBlank
```

Giải thích:

- `VALID`: tham số hợp lệ; thân `confirm` được chạy; kết quả cũng không rỗng.
- `INVALID_INPUT`: `sku=""` vi phạm `@NotBlank`, `quantity=0` vi phạm `@Min(1)`. Proxy ném `ConstraintViolationException` **trước khi** gọi thân `confirm`.
- `INVALID_RETURN`: đầu vào `"SKU-100"` hợp lệ, nhưng `badReceipt` trả về `""` nên vi phạm `@NotBlank` ở vị trí return value. Lỗi được phát hiện **sau** khi thân phương thức thực thi.
- `INVALID_NESTED`: đối tượng `DeliveryAddress` được chuyển vào `ship`; `@Valid` yêu cầu cascade vào constraint `@NotBlank` của record. Giá trị `street=""` bị từ chối trước khi thân `ship` dùng `address.street()`.

Ví dụ in tên loại annotation và sắp xếp chuỗi để kết quả không phụ thuộc thứ tự của tập violation hoặc văn bản lỗi theo locale. Nếu bỏ `@Validated` trên `CheckoutService` hoặc dùng `new CheckoutService()` trực tiếp, cơ chế AOP method validation **không còn tự chặn** các lời gọi như ví dụ. Việc khai báo annotation trên phương thức không tự biến mọi object Java thành Spring proxy.

## 6. Cách proxy hoạt động và những giới hạn thường gặp

Spring AOP thường tạo một trong hai kiểu proxy:

- **JDK dynamic proxy:** dựa trên interface, chỉ expose các method có trong interface được proxy. Caller nên inject/call qua interface.
- **Class-based proxy (CGLIB):** tạo subclass của target. Không thể advise `final` method, `private` method hoặc subclass một `final` class. Đừng kỳ vọng method không thể override sẽ được kiểm tra qua loại proxy này.

Cách chọn proxy còn phụ thuộc cấu hình Spring/Boot và các advisor khác; không suy luận kiểu proxy chỉ từ việc class có interface.

### 6.1. Self-invocation bỏ qua advice

```java
@Service
@Validated
public class OrderService {

    public void outer() {
        inner(""); // this.inner("") không đi qua proxy
    }

    public void inner(@NotBlank String code) {
        // Khi gọi trực tiếp trên target, constraint không được AOP đánh giá.
    }
}
```

Đây là **đoạn minh họa độc lập về self-invocation**, không phải một phần của ứng dụng mẫu. Gọi `orderService.outer()` từ bean khác đi qua proxy, nhưng lời gọi `inner("")` nằm trong cùng target lại bỏ qua proxy và không được method-validation advice riêng cho `inner` xử lý. Để có validation tại ranh giới ấy, hãy chuyển logic cần kiểm tra sang **bean khác** và inject bean đó, hoặc thiết kế API sao cho caller đi qua proxy.

### 6.2. Tạo object bằng `new` bỏ qua Spring

```java
CheckoutService direct = new CheckoutService();
direct.confirm("", 0); // thân method chạy bình thường; không có AOP proxy
```

Ở ví dụ trên, mã Java vẫn biên dịch; hai annotation trên tham số không tự động gọi `ExecutableValidator`. Nếu thực sự cần kiểm tra ngoài container, có thể chủ động dùng `jakarta.validation.executable.ExecutableValidator` thay vì kỳ vọng proxy hoạt động.

### 6.3. Private/final, factory lifecycle và vòng phụ thuộc

BeanPostProcessor có tác dụng khi Spring tạo bean và gắn advisor; bean được khởi tạo ngoài container hoặc quá sớm so với hạ tầng post-processor có thể không được proxy như mong muốn. Tránh kiểm thử thông qua `this.method()`, khởi tạo `@Validated` class thành `final` khi dựa trên class-based proxy, hoặc đặt constraint quan trọng ở private method. Đối với method không public, khả năng advise phụ thuộc proxy và cách method được gọi; public service method là lựa chọn ít bất ngờ nhất.

## 7. @Validated cấp lớp, cấp phương thức và validation groups

`@Validated` hỗ trợ nhóm validation. Nếu không chỉ định group, Bean Validation thông thường đánh giá nhóm `jakarta.validation.groups.Default`.

- `@Validated` trên **class** là marker để `MethodValidationPostProcessor` chọn bean áp dụng method validation; có thể đi kèm danh sách group mặc định của bean đó.
- `@Validated(SpecialChecks.class)` trên **một method của bean đã đủ điều kiện** có thể thay đổi group áp dụng riêng cho method.
- Chỉ đặt `@Validated` trên một method của class không có marker cấp kiểu **không** khiến `MethodValidationPostProcessor` tự chọn class ấy.
- Một constraint thuộc group khác sẽ không tự động chạy khi chỉ validate group `Default`, và ngược lại. Phải thiết kế group theo đúng quy tắc nghiệp vụ.

Ví dụ về group (mã minh họa, không phải phần của ứng dụng chạy trên):

```java
interface ApprovalChecks {}

@Validated
public class ApprovalService {

    @Validated(ApprovalChecks.class)
    public void approve(
            @NotNull(groups = ApprovalChecks.class) String approvalCode) {
        // ...
    }
}
```

Trong một lượt method validation dùng group `ApprovalChecks`, constraint được gán đúng group đó sẽ được kiểm tra. Nếu thêm constraint mặc định mà không đưa vào group đang kích hoạt, nó có thể không chạy như kỳ vọng.

Cũng lưu ý rằng method constraint có quy định kế thừa từ Jakarta Bean Validation: khi override hoặc implement interface, **không tự ý tăng cường điều kiện tiền đề của tham số** trong phương thức ghi đè so với hợp đồng cấp cha/interface. Provider có thể báo lỗi khai báo constraint không hợp lệ (ví dụ `ConstraintDeclarationException`). Hãy đặt constraint tham số tại hợp đồng phù hợp và kiểm tra tính nhất quán giữa interface với implementation.

## 8. Phân biệt method validation qua AOP với Spring MVC

Đây là chỗ rất dễ nhầm nếu cùng một dự án vừa có service `@Validated` vừa có controller `@RestController`.

### 8.1. Trên service/component bean

Cơ chế trong bài này là:

```text
@Validated trên type + MethodValidationPostProcessor
    → Spring AOP proxy → kiểm tra method parameter/return
    → mặc định ConstraintViolationException
```

Thích hợp cho hợp đồng đầu vào/đầu ra ở service, message handler, scheduled job được gọi qua Spring bean proxy.

### 8.2. Trên Spring MVC controller từ Spring Framework 6.1

Spring MVC có **method validation tích hợp trực tiếp** trong hạ tầng xử lý handler, không nhất thiết dùng `MethodValidationPostProcessor`. Khi controller có constraint trực tiếp như `@Min` trên `@RequestParam` hoặc constraint trên return value, MVC có thể thực hiện method validation và sinh `HandlerMethodValidationException`.

```java
// Đoạn minh họa trong @RestController, không phải chương trình độc lập:
@GetMapping("/items")
public List<ItemDto> list(@RequestParam @Min(1) int page) {
    return service.find(page);
}
```

Cũng cần phân biệt `@Valid @RequestBody MyDto` khi DTO có constraint nội bộ. Nếu chỉ kiểm tra từng command object ở tham số và không cần method validation, Spring MVC thường phát ra `MethodArgumentNotValidException`. Nếu có constraint trực tiếp trên method parameter/return, method validation bao phủ cả constraint trực tiếp và việc cascade của `@Valid`, với cơ chế lỗi có thể là `HandlerMethodValidationException`.

**Đặc biệt:** tài liệu Spring MVC từ 6.1 khuyến nghị **bỏ `@Validated` ở cấp class của controller** nếu muốn sử dụng cơ chế built-in của Spring MVC. Nếu giữ class-level `@Validated`, validation có thể đi theo đường AOP proxy, kéo theo kiểu exception và đặc tính interception khác. Vì thế không sao chép máy móc quy tắc “service phải có `@Validated`” sang tất cả controller.

`@Valid` của Jakarta **không phải constraint trực tiếp**. Nó đánh dấu cascade; riêng `@Valid` không khiến Spring MVC bật whole-method validation theo trường hợp constraint trực tiếp. `@NotNull @Valid` thì có constraint trực tiếp, nên hành vi method validation có thể khác.

Khi viết `@ControllerAdvice`, thiết kế xử lý lỗi theo đường validation thực tế. Không mặc định mọi lỗi từ `@Valid` đều là `ConstraintViolationException` hoặc luôn là mã HTTP 400 như nhau trong mọi bối cảnh.

## 9. Loại exception và vị trí quan sát lỗi

### Chế độ mặc định của MethodValidationPostProcessor

Khi `setAdaptConstraintViolations(false)` (mặc định), lỗi từ executable validation làm interceptor ném:

```java
jakarta.validation.ConstraintViolationException
```

Exception chứa tập `getConstraintViolations()` với đường dẫn tới parameter/return value, thông báo và metadata constraint. Tên parameter trong path có thể phụ thuộc metadata compile/parameter-name provider; để log/kiểm thử ổn định, không nên chỉ phụ thuộc chuỗi hiển thị của path.

### Chế độ chuyển sang Spring MethodValidationResult

Nếu bật:

```java
@Bean
public static MethodValidationPostProcessor methodValidationPostProcessor() {
    MethodValidationPostProcessor postProcessor =
        new MethodValidationPostProcessor();
    postProcessor.setAdaptConstraintViolations(true);
    return postProcessor;
}
```

Đây là đoạn cấu hình cho ứng dụng **chủ động cung cấp** post-processor riêng; không đặt thêm tùy tiện cạnh một bean auto-configured khác. Khi `true`, Spring có thể ném `org.springframework.validation.method.MethodValidationException`, mang các `ParameterValidationResult` và thông tin lỗi thuận tiện cho tích hợp `MessageSource`; lỗi trên nested bean có thể được biểu diễn qua `ParameterErrors`.

Đừng viết `catch (ConstraintViolationException)` trong ví dụ rồi bật `setAdaptConstraintViolations(true)` mà không sửa xử lý exception. Các kiểu exception là hai hợp đồng khác nhau.

### Hiểu đúng thứ tự before/after

| Vị trí vi phạm | Method body có chạy chưa? | Ý nghĩa |
| --- | --- | --- |
| Tham số có `@NotBlank`/`@Min` sai | Chưa | Chặn lời gọi trước khi thực thi |
| DTO tham số có `@Valid` và field con sai | Chưa, nếu cascade được kích hoạt | Chặn theo constraint lồng nhau |
| Giá trị trả về vi phạm `@NotNull`/`@NotBlank` | Đã chạy | Phát hiện hậu điều kiện sau khi thực thi |
| Method tự ném exception nghiệp vụ | Có thể đã chạy một phần | Không có return value thành công để post-validate theo cách thông thường |

Trong các ứng dụng có `@Transactional`, thứ tự advice và quy tắc transaction rollback phải được kiểm tra riêng; method validation không phải cơ chế quản lý transaction.

## 10. Kiểm thử hành vi thật qua Spring proxy

Khi kiểm thử logic service, nên có hai loại test với mục tiêu khác nhau:

1. **Unit test trực tiếp** `new CheckoutService()` để kiểm thử nghiệp vụ thuần; không dùng nó làm bằng chứng method validation AOP đang hoạt động.
2. **Integration test qua Spring context**, inject bean `@Validated` thật và assert exception từ lần gọi qua proxy. Như vậy mới kiểm tra được marker, BeanPostProcessor, provider, advice và method signature trong môi trường thực.

Ví dụ test minh họa nếu đã có `spring-boot-starter-test` (mã cần đặt trong dự án test có cấu hình/annotation tương ứng):

```java
@SpringBootTest
class CheckoutServiceMethodValidationTest {

    @Autowired
    CheckoutService service;

    @Test
    void rejectsInvalidParametersThroughProxy() {
        assertThrows(
            ConstraintViolationException.class,
            () -> service.confirm("", 0)
        );
    }

    @Test
    void rejectsInvalidReturnValue() {
        assertThrows(
            ConstraintViolationException.class,
            () -> service.badReceipt("SKU-100")
        );
    }
}
```

Đoạn test trên chỉ minh họa phương pháp kiểm thử, chưa bao gồm file dependency/import; ví dụ chạy độc lập ở mục 5 đã đủ để quan sát hiệu quả AOP. Một bước chẩn đoán khác là dùng `AopUtils.isAopProxy(service)` trong môi trường có Spring AOP để xác nhận reference đã được proxy. Điều đó chứng minh có proxy, nhưng vẫn nên assert kết quả validation để chứng minh advice chính xác được áp dụng.

### Checklist khi “có @Validated nhưng không thấy lỗi”

- Đã có Bean Validation provider và post-processor chưa?
- `@Validated` có thực sự nằm ở type được pointcut nhận diện?
- Đang inject Spring bean hay tự gọi `new`?
- Lời gọi có đi qua proxy không, hay là `this.method()`?
- Method có thể advise không (interface/JDK proxy, class-based proxy, `final`/`private`)?
- Constraint nằm trên tham số, return value hay object con qua `@Valid`?
- Group đang kích hoạt có khớp `groups=...` của constraint không?
- Có annotation ở interface và implementation tạo ra hợp đồng Bean Validation không hợp lệ?
- Exception được xử lý/catch theo loại nào? Có bật `setAdaptConstraintViolations(true)` không?
- Đây là service bean qua AOP hay Spring MVC controller dùng built-in validation?

## 11. Những nhầm lẫn thường gặp

- **“Đặt `@NotNull` lên tham số là đủ”:** Annotation chỉ khai báo constraint; cần cơ chế gọi validator, chẳng hạn interceptor qua Spring proxy hoặc lời gọi `ExecutableValidator` chủ động.
- **“`@Validated` trên một method tự bật cho cả class”:** Trong AOP method-validation mặc định, pointcut dựa trên type; đánh dấu class mới là bước cần thiết.
- **“`@Valid` và `@Validated` luôn giống nhau”:** `@Valid` của Jakarta chủ yếu để cascade, còn `@Validated` của Spring chọn nhóm và đánh dấu bean cho method validation.
- **“Mọi lời gọi tới bean đều qua proxy”:** Self-invocation, instance tự tạo và method không thể advise có thể bỏ qua interceptor.
- **“Validation kết quả trả về bảo đảm không có side effect”:** Kiểm tra hậu điều kiện xảy ra sau khi method body chạy.
- **“Controller luôn cần class-level `@Validated`”:** Spring MVC 6.1+ có phương thức validation tích hợp; class-level `@Validated` có thể thay đổi đường xử lý.
- **“Bật `setAdaptConstraintViolations(true)` không đổi gì”:** Nó thay đổi loại exception và cấu trúc dữ liệu lỗi mà caller cần xử lý.

## 12. Tổng kết

`MethodValidationPostProcessor` đăng ký advice kiểm tra **tham số trước** và **kết quả sau** lời gọi phương thức của bean Spring được đánh dấu `@Validated` ở cấp type. Đây là cơ chế **proxy-based**: tính đúng đắn phụ thuộc việc bean được Spring quản lý, lời gọi đi qua proxy, phương thức có thể advise và provider Bean Validation có mặt.

Khi xây dựng service API, hãy đặt constraint vào chữ ký, đánh dấu bean đủ điều kiện, gọi qua bean được inject và kiểm thử qua Spring context. Khi xử lý controller MVC, phân biệt cơ chế built-in từ Spring Framework 6.1 với cơ chế AOP để chọn annotation và exception handler đúng.

## Tham khảo

- Spring Framework — Java Bean Validation, mục *Spring-driven Method Validation*: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring Boot — Validation và method validation auto-configuration: https://docs.spring.io/spring-boot/reference/io/validation.html
- Spring Framework — `MethodValidationPostProcessor` Javadoc: https://docs.spring.io/spring-framework/docs/6.2.1/javadoc-api/org/springframework/validation/beanvalidation/MethodValidationPostProcessor.html
- Spring Framework — Spring MVC validation và `@Validated` trên controller: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework — AOP proxying, self-invocation và final method: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — `@Validated` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/validation/annotation/Validated.html