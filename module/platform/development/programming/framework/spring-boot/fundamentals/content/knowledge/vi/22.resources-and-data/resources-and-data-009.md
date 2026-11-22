# Method validation và vai trò proxy trong Spring Boot

Một phương thức Java có thể nhận tham số không hợp lệ dù dữ liệu đầu vào ban đầu đã đi qua HTTP validation. Ví dụ, một service thanh toán có thể được gọi từ REST controller, batch job, scheduler, message listener hoặc một service khác. Nếu chỉ đặt ràng buộc trên DTO của REST API, những đường gọi không đi qua controller có thể bỏ qua toàn bộ quy tắc kiểm tra.

**Method validation** cho phép đặt các ràng buộc Bean Validation trực tiếp trên tham số và giá trị trả về của phương thức. Trong ứng dụng Spring Boot sử dụng Spring-managed service, việc kiểm tra này thường được thực thi bằng **AOP proxy**: bên gọi gọi một đối tượng proxy, proxy chặn lời gọi, kiểm tra đầu vào, chuyển tiếp tới phương thức thật rồi kiểm tra giá trị trả về.

Chính vì vậy, không chỉ annotation mà cả **đường đi của lời gọi** quyết định validation có diễn ra hay không. Một phương thức có `@NotNull` hoặc `@Positive` chưa chắc được kiểm tra khi gọi bằng `this.method()` trong cùng class, khi tạo object bằng `new` hay khi phương thức không thể được proxy chặn.

Bài học này giải thích cách hoạt động, các giới hạn của proxy, khác biệt giữa validation ở controller và service, cách dùng cascading/groups, lỗi thường gặp và phương pháp kiểm thử. Ví dụ dùng Java 17+ và namespace `jakarta.validation` của các thế hệ Spring Boot hiện đại; với Spring Boot 2 cũ, nhiều import có dạng `javax.validation`.

## 1. Method validation giải quyết vấn đề gì?

Giả sử có service tính tiền:

~~~java
@Service
public class PricingService {

    public BigDecimal calculateTotal(
            BigDecimal unitPrice,
            int quantity
    ) {
        return unitPrice.multiply(
                BigDecimal.valueOf(quantity)
        );
    }
}
~~~

Nếu `unitPrice == null`, code có thể ném `NullPointerException`. Nếu `unitPrice` âm hoặc `quantity` bằng 0, phép tính vẫn cho kết quả nhưng không đúng quy tắc nghiệp vụ.

Ta muốn quy định hợp đồng đầu vào ngay trên method:

~~~java
@Service
@Validated
public class PricingService {

    public BigDecimal calculateTotal(
            @NotNull @Positive BigDecimal unitPrice,
            @Min(1) int quantity
    ) {
        return unitPrice.multiply(
                BigDecimal.valueOf(quantity)
        );
    }
}
~~~

Các ràng buộc trên tham số biểu đạt:

- `@NotNull`: giá trị không được là `null`.
- `@Positive`: số phải lớn hơn 0.
- `@Min(1)`: số phải lớn hơn hoặc bằng 1.
- `@Validated`: trong cơ chế Spring service method validation, đánh dấu bean là đối tượng cần được áp dụng interceptor kiểm tra phương thức.

Ví dụ gọi qua Spring bean:

~~~java
BigDecimal total =
        pricingService.calculateTotal(
                new BigDecimal("12.50"),
                3
        );
~~~

Kết quả hợp lệ là `37.50`. Nhưng nếu gọi:

~~~java
pricingService.calculateTotal(
        new BigDecimal("-12.50"),
        3
);
~~~

interceptor validation có thể phát hiện constraint violation **trước khi thân phương thức chạy**.

Ý nghĩa lớn nhất không phải thay thế `if` trong mọi trường hợp, mà là làm rõ hợp đồng phương thức và áp dụng nó nhất quán cho những lời gọi đi qua cơ chế Spring method validation.

## 2. Phân biệt Bean Validation, method validation và proxy

Có ba khái niệm thường bị trộn lẫn.

### Bean Validation: tập hợp ràng buộc và bộ kiểm tra

Jakarta Bean Validation cung cấp annotation và API như:

~~~java
@NotNull
@NotBlank
@Size(min = 2, max = 80)
@Positive
@Min(1)
@Valid
~~~

Một implementation như Hibernate Validator kiểm tra những ràng buộc này.

Ví dụ DTO:

~~~java
public record CreateProductRequest(
        @NotBlank String name,
        @NotNull @Positive BigDecimal price
) {}
~~~

Annotation mô tả quy tắc dữ liệu. Tự nó không bảo đảm mọi object Java sẽ được kiểm tra tự động.

### Method validation: kiểm tra tham số và return value

Bean Validation có API dành riêng cho executable validation, thường được truy cập qua `ExecutableValidator`:

~~~java
ExecutableValidator executableValidator =
        validator.forExecutables();
~~~

API này có thể kiểm tra tham số phương thức, giá trị trả về hoặc constructor theo cách tường minh.

### Spring AOP proxy: cơ chế gọi tự động

Thay vì tự gọi `ExecutableValidator` ở mọi nơi, Spring có thể dùng interceptor bao quanh phương thức của bean:

~~~text
Caller
   |
   v
Spring-managed proxy
   |
   +--> Validate method arguments
   |
   +--> Invoke target method
   |
   +--> Validate return value
   |
   v
Return to caller
~~~

Các lớp quan trọng trong cơ chế Spring service method validation gồm `MethodValidationPostProcessor` và `MethodValidationInterceptor`. Bộ post-processor phát hiện bean phù hợp và thiết lập interceptor/proxy; interceptor gọi Bean Validation khi phương thức được thực thi.

**Kết luận của phần này:** constraint là quy tắc, validator là bộ thực thi quy tắc, còn proxy là cách Spring gắn việc kiểm tra vào lời gọi method mà không cần service tự gọi `validator.validate(...)`.

## 3. Dependency cần có trong Spring Boot

Với một ứng dụng Spring Boot dùng Maven, thường thêm:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Với Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-validation")
}
~~~

Starter cung cấp những dependency cần thiết cho Bean Validation implementation thông thường. Trong các phiên bản Spring Boot gần đây, không nên mặc định `spring-boot-starter-web` luôn mang theo đầy đủ Bean Validation provider; hãy khai báo starter validation rõ ràng khi cần tính năng.

Ví dụ import cho service:

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;
~~~

`@Validated` là annotation của **Spring**; còn `@Valid`, `@NotNull`, `@Positive` thuộc **Jakarta Validation**.

### Spring Boot tự cấu hình những gì?

Khi có các điều kiện phù hợp về classpath và bean, Spring Boot có thể tự cấu hình `Validator` và thành phần hỗ trợ method validation cho Spring bean. Trong cấu hình Spring Boot thông thường, `MethodValidationPostProcessor` giúp các bean đánh dấu `@Validated` có thể được proxy.

Nếu một ứng dụng Spring Framework thuần hoặc cấu hình custom không có post-processor, chỉ gắn `@Validated` lên class có thể chưa đủ để tạo validation interceptor. Cần xác định infrastructure được đăng ký thật sự, không chỉ nhìn annotation.

## 4. @Valid và @Validated khác nhau

Hai annotation có tên gần giống nhưng vai trò khác nhau.

| Annotation | Namespace | Vai trò |
|---|---|---|
| `@Valid` | `jakarta.validation.Valid` | Yêu cầu cascade validation vào object/giá trị lồng nhau |
| `@Validated` | `org.springframework.validation.annotation.Validated` | Dấu hiệu Spring dùng cho validation, hỗ trợ validation groups; trên service type thường kích hoạt AOP method validation |
| `@NotNull` | `jakarta.validation.constraints.NotNull` | Constraint kiểm tra không null |
| `@Positive` | `jakarta.validation.constraints.Positive` | Constraint kiểm tra số dương |

Ví dụ:

~~~java
public record Address(
        @NotBlank String city,
        @NotBlank String street
) {}

public record CreateCustomerCommand(
        @NotBlank String name,
        @NotNull @Valid Address address
) {}
~~~

`@Valid` tại field `address` bảo validator đi tiếp vào các constraint bên trong `Address`. Nó không tự chứng minh object `CreateCustomerCommand` đã được đưa qua một điểm gọi validation.

Service:

~~~java
@Service
@Validated
public class CustomerRegistrationService {

    public UUID register(
            @NotNull @Valid CreateCustomerCommand command
    ) {
        // ...
        return UUID.randomUUID();
    }
}
~~~

Khi `register(...)` được gọi qua Spring method-validation proxy, validator có thể:

1. Kiểm tra `command` không null.
2. Đi vào các field của `CreateCustomerCommand` nhờ `@Valid`.
3. Kiểm tra `name` và `address`.
4. Đi tiếp vào `Address` để kiểm tra `city` và `street`.

**Quan trọng:** `@Valid` không có nghĩa giá trị khác null. Nếu `address` bắt buộc, cần `@NotNull @Valid` như ví dụ.

## 5. Ví dụ end-to-end ở tầng service

Giả sử hệ thống có use case đăng ký sản phẩm. Nhiều entry point có thể gọi chung một service.

### 5.1. Command nhận dữ liệu

~~~java
package com.example.catalog.application;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import java.math.BigDecimal;

public record CreateProductCommand(
        @NotBlank String sku,
        @NotBlank String name,
        @NotNull @Positive BigDecimal price
) {}
~~~

`CreateProductCommand` mang ý nghĩa dữ liệu đầu vào cho application service. Nó có thể được tạo từ REST request, message hoặc file import.

### 5.2. Service được method validation

~~~java
package com.example.catalog.application;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class ProductRegistrationService {

    private final ProductRepository repository;

    public ProductRegistrationService(
            ProductRepository repository
    ) {
        this.repository = repository;
    }

    @Transactional
    @NotNull
    public Long create(
            @NotNull @Valid CreateProductCommand command
    ) {
        Product saved = repository.save(
                Product.create(
                        command.sku(),
                        command.name(),
                        command.price()
                )
        );

        return saved.getId();
    }

    @NotNull
    public BigDecimal discountedPrice(
            @NotNull @Positive BigDecimal original,
            @Min(0) int discountPercent
    ) {
        if (discountPercent > 100) {
            throw new IllegalArgumentException(
                    "discountPercent must not exceed 100"
            );
        }

        return original.multiply(
                BigDecimal.valueOf(
                        100 - discountPercent
                )
        ).divide(BigDecimal.valueOf(100));
    }
}
~~~

Các kiểu `Product`, `ProductRepository` là abstraction nghiệp vụ minh họa. Ví dụ `discountedPrice` dùng `@Min(0)` nhưng vẫn cần xử lý giới hạn trên; ta có thể mô tả chính xác hơn bằng `@Max(100)` thay vì kiểm tra thủ công. Điều đó cho thấy annotation cần được chọn theo đầy đủ miền dữ liệu.

Ở đây `@NotNull` trên return value `create(...)` và `discountedPrice(...)` là **return-value constraint**. Nó được kiểm tra sau khi method hoàn thành, nếu lời gọi đi qua proxy.

### 5.3. REST controller gọi service

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductRegistrationService service;

    public ProductController(
            ProductRegistrationService service
    ) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<Map<String, Long>> create(
            @Valid @RequestBody CreateProductCommand command
    ) {
        Long id = service.create(command);

        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(Map.of("id", id));
    }
}
~~~

Controller có `@Valid` để kiểm tra dữ liệu HTTP request. Service có `@Validated` và method constraints để bảo vệ contract **ngay cả khi nơi gọi không phải HTTP controller**.

Hai tầng validation có thể áp dụng cùng quy tắc. Điều này có thể làm lặp chi phí kiểm tra trong một số đường gọi, nhưng cung cấp ranh giới trách nhiệm khác nhau:

- Controller validation bảo vệ **đầu vào HTTP** và thường trả HTTP 400.
- Service method validation bảo vệ **hợp đồng của use case/service** cho mọi caller được proxy chặn.

Với ứng dụng phức tạp, có thể dùng DTO HTTP riêng và command service riêng để tránh làm domain model phụ thuộc trực tiếp API contract.

## 6. MethodValidationPostProcessor và luồng tạo proxy

Trong Spring, `MethodValidationPostProcessor` là một BeanPostProcessor theo cơ chế advisor. Nó có nhiệm vụ tham gia vào quá trình tạo Spring beans và gắn method validation interceptor cho bean phù hợp, thông thường là những bean có `@Validated` ở type level.

Có thể hình dung:

~~~text
Spring Boot chuẩn bị ApplicationContext
                 |
                 v
    Đăng ký Validator và hạ tầng validation
                 |
                 v
  Spring tạo bean ProductRegistrationService
                 |
                 v
       MethodValidationPostProcessor
        nhận diện annotation @Validated
                 |
                 v
         Tạo hoặc kết hợp AOP proxy
                 |
                 v
  Spring inject proxy vào ProductController
                 |
                 v
  controller -> proxy -> validator -> target
~~~

Vì validator được áp dụng bằng interceptor, không cần sửa thân phương thức `create(...)` để gọi validator.

### Proxy không phải bản sao độc lập của nghiệp vụ

Proxy là một đối tượng trung gian có khả năng thêm hành vi trước/sau lời gọi. Phương thức nghiệp vụ vẫn chạy trên target theo cơ chế proxy tương ứng.

Một số bean có thể có **nhiều advice**: method validation, transaction management, caching, security hoặc metrics. Spring có thể tạo/điều phối proxy/advisor tương ứng. Vì vậy, thứ tự interceptor và transaction boundary có thể ảnh hưởng chính xác thời điểm exception xuất hiện.

### @Validated đặt ở class là tín hiệu chủ chốt với Spring AOP method validation

Ví dụ:

~~~java
@Service
@Validated
public class InventoryService {

    public void reserve(
            @NotBlank String sku,
            @Positive int quantity
    ) {
        // ...
    }
}
~~~

Việc đặt constraint trên method arguments cho biết điều cần kiểm tra. `@Validated` ở class là dấu hiệu được Spring method validation infrastructure sử dụng để tạo proxy cho bean này.

Nếu bỏ `@Validated` trong cách cấu hình service phổ biến, constraint vẫn tồn tại trong metadata Bean Validation nhưng **lời gọi tới service có thể không được interceptor tự kiểm tra**.

## 7. Proxy được gọi như thế nào?

Xét bean:

~~~java
@Service
@Validated
public class InventoryService {

    public void reserve(
            @NotBlank String sku,
            @Positive int quantity
    ) {
        // Logic giữ tồn kho.
    }
}
~~~

Một service khác inject nó:

~~~java
@Service
public class CheckoutService {

    private final InventoryService inventoryService;

    public CheckoutService(
            InventoryService inventoryService
    ) {
        this.inventoryService = inventoryService;
    }

    public void checkout() {
        inventoryService.reserve("ABC-123", -3);
    }
}
~~~

Trong cấu hình method validation proxy hoạt động, Spring inject đối tượng proxy phù hợp. Khi `checkout()` gọi `reserve(...)`, lời gọi đi qua interceptor và tham số `-3` vi phạm `@Positive`.

Luồng:

~~~text
CheckoutService
      |
      | inventoryService.reserve("ABC-123", -3)
      v
InventoryService proxy
      |
      +--> ExecutableValidator.validateParameters(...)
      |            |
      |        Violation
      |            |
      v            v
    Target?     Exception
      |
  Không chạy nếu violation
~~~

Khi tham số hợp lệ, interceptor cho phép chuyển tiếp đến target method. Sau khi target trả về, nếu có return-value constraints, interceptor có thể kiểm tra kết quả trả về.

### Điểm then chốt: caller phải đi qua proxy

AOP proxy kiểu thông thường chỉ chặn lời gọi từ bên ngoài đi qua đối tượng proxy. Nếu code gọi trực tiếp target hoặc một method trong cùng object, có thể bỏ qua validation.

## 8. Self-invocation: nguyên nhân phổ biến khiến validation không chạy

Xét service:

~~~java
@Service
@Validated
public class CustomerService {

    public void importMany(List<String> emails) {
        for (String email : emails) {
            registerOne(email);
        }
    }

    public void registerOne(
            @NotBlank @Email String email
    ) {
        // Tạo khách hàng.
    }
}
~~~

Khi một bean khác gọi `customerService.registerOne("bad")` qua proxy, method validation có thể hoạt động.

Nhưng trong `importMany(...)`, dòng:

~~~java
registerOne(email);
~~~

thực chất là lời gọi nội bộ trên `this`. Nó đi trực tiếp đến phương thức target, **không quay lại Spring proxy**. Vì vậy, constraint trên `registerOne(...)` có thể không được kiểm tra trong đường gọi này.

Sơ đồ:

~~~text
Bên ngoài
   |
   v
CustomerService proxy
   |
   v
importMany(...)
   |
   | this.registerOne(email)
   v
registerOne(...) trên target
   |
   X Không đi qua validation interceptor
~~~

### Vì sao @Validated không giải quyết self-invocation?

`@Validated` giúp Spring đặt validation interceptor lên proxy. Nó không biến mọi lời gọi nội bộ trong bytecode Java thành một lời gọi qua proxy.

Cùng một nguyên lý cũng ảnh hưởng các concern dựa trên Spring proxy như `@Transactional`, `@Async` và `@Cacheable` khi self-invocation xảy ra.

### Cách sửa ưu tiên: tách trách nhiệm sang bean khác

~~~java
@Service
@Validated
public class CustomerRegistrationService {

    public void registerOne(
            @NotBlank @Email String email
    ) {
        // Tạo một khách hàng.
    }
}
~~~

~~~java
@Service
public class CustomerImportService {

    private final CustomerRegistrationService registrationService;

    public CustomerImportService(
            CustomerRegistrationService registrationService
    ) {
        this.registrationService = registrationService;
    }

    public void importMany(List<String> emails) {
        for (String email : emails) {
            registrationService.registerOne(email);
        }
    }
}
~~~

Lời gọi từ `CustomerImportService` sang `CustomerRegistrationService` đi qua bean dependency do Spring inject và vì thế có cơ hội đi qua validation proxy.

Cách tách này thường rõ ràng hơn tự inject chính mình hoặc tìm proxy trong ApplicationContext.

### Cách khác: validation tường minh

Nếu method bắt buộc được gọi nội bộ và không muốn tách bean, có thể kiểm tra dữ liệu bằng `Validator` hoặc `ExecutableValidator` một cách tường minh. Đây là một quyết định thiết kế hợp lệ khi cần validation chính xác tại một ranh giới nội bộ.

Không nên dựa vào mẹo `AopContext.currentProxy()` để giải quyết mọi self-invocation. Cách đó làm service phụ thuộc mạnh vào AOP infrastructure, yêu cầu cấu hình expose proxy và thường khó kiểm thử hơn.

## 9. Gọi bằng new thì không có Spring proxy

Ví dụ:

~~~java
CustomerRegistrationService service =
        new CustomerRegistrationService();

service.registerOne("not-an-email");
~~~

Nếu class có `@Validated` nhưng được tạo bằng `new`, Spring không quản lý object này. Không có `MethodValidationPostProcessor` nào tự gắn proxy cho object do code tạo thủ công.

Điều này khác:

~~~java
CustomerRegistrationService service =
        applicationContext.getBean(
                CustomerRegistrationService.class
        );
~~~

Khi lấy một bean từ context, kết quả có thể là proxy nếu bean đủ điều kiện. Trong ứng dụng thông thường, nên inject qua constructor thay vì tìm bean trực tiếp trong context.

### Unit test tạo service bằng new

Unit test chỉ kiểm tra logic Java thuần có thể làm:

~~~java
CustomerRegistrationService service =
        new CustomerRegistrationService(...);
~~~

Nhưng test đó **không chứng minh** method validation của Spring hoạt động. Nếu cần kiểm tra interceptor, phải dùng Spring context có hạ tầng validation hoặc gọi `ExecutableValidator` tường minh.

## 10. JDK dynamic proxy và CGLIB/class-based proxy

Spring AOP có hai nhóm cơ chế proxy phổ biến:

- **JDK dynamic proxy:** proxy các interface mà target triển khai.
- **Class-based proxy (CGLIB):** tạo subclass của class mục tiêu để chặn những phương thức phù hợp.

### Proxy theo interface

~~~java
public interface ShippingService {
    void createShipment(String orderId);
}
~~~

~~~java
@Service
@Validated
public class ShippingServiceImpl
        implements ShippingService {

    @Override
    public void createShipment(
            @NotBlank String orderId
    ) {
        // ...
    }
}
~~~

Nếu dùng JDK proxy, caller thường cần inject/interface type:

~~~java
private final ShippingService shippingService;
~~~

Tuy nhiên, các ràng buộc Bean Validation trên method kế thừa/override phải tuân theo quy tắc method inheritance của Bean Validation. Không tùy ý thêm hoặc thay đổi **parameter constraints** trên method override so với method đã khai báo trong interface; provider có thể báo lỗi cấu hình constraint.

Một cách rõ ràng là đặt parameter contract trên interface:

~~~java
public interface ShippingService {

    void createShipment(
            @NotBlank String orderId
    );
}
~~~

~~~java
@Service
@Validated
public class ShippingServiceImpl
        implements ShippingService {

    @Override
    public void createShipment(String orderId) {
        // ...
    }
}
~~~

Ở đây constraint được khai báo ở hợp đồng public interface, phù hợp với người dùng interface và tránh mâu thuẫn giữa declaration và override.

### Proxy theo class

Nếu dùng class-based proxy, Spring tạo subclass để intercept. Những method không thể override sẽ không có cùng khả năng interception.

Ví dụ cấu hình thường gặp:

~~~properties
spring.aop.proxy-target-class=true
~~~

Property này liên quan lựa chọn proxy type trong cấu hình Spring AOP thông thường. Tuy nhiên, việc tạo proxy còn phụ thuộc hạ tầng, extension point và cách auto-configuration đăng ký post-processor. Không nên coi property này là công tắc có thể ép mọi method private/final trở nên interceptable.

### Class-based proxy không phải lời giải cho mọi visibility

CGLIB không thể override method `final` hoặc `private`. Cũng không thể subclass một class `final` theo cách proxy này. Vì vậy, ngay cả khi có annotation trên method, việc interception có thể không hoạt động hoặc cấu hình proxy thất bại.

## 11. Visibility: public, private, final và static

Để method validation qua Spring AOP proxy dễ dự đoán, **ưu tiên public methods được gọi từ bean khác**.

| Trường hợp | Khả năng interceptor chạy | Khuyến nghị |
|---|---|---|
| Public method trên Spring bean, gọi qua proxy | Thông thường có thể | Cách dùng điển hình |
| Public method gọi nội bộ bằng `this` | Thường bỏ qua proxy | Tách bean hoặc validate tường minh |
| Private method | Không phải join point được proxy override bình thường | Không dựa vào AOP validation |
| Final method với class-based proxy | Không thể override | Dùng method không final hoặc giao diện phù hợp |
| Final class với class-based proxy | Không thể subclass | Thiết kế type có thể proxy hoặc dùng interface |
| Static method | Không được intercept như instance method thông thường | Kiểm tra tường minh nếu cần |
| Object tạo bằng `new` | Không được Spring post-process | Inject bean hoặc validate tường minh |

Một số chi tiết interception đối với protected/package-private methods phụ thuộc proxy type và version Spring. Với service contract public, hạn chế phụ thuộc vào các trường hợp biên đó để giữ hành vi ổn định.

### Annotation trên method private không phải validation tự động

~~~java
@Service
@Validated
public class RegistrationService {

    private void validateInternal(
            @NotBlank String value
    ) {
        // ...
    }
}
~~~

`@NotBlank` vẫn là annotation metadata, nhưng Spring method validation proxy thông thường không tự chặn lời gọi vào private method này. Nếu phải kiểm tra, đặt validation ở public boundary hoặc gọi validator trực tiếp.

## 12. Return-value validation

Method validation không chỉ dành cho input. Nó còn có thể kiểm tra giá trị **trả về**.

~~~java
@Service
@Validated
public class ExchangeRateService {

    @NotNull
    @Positive
    public BigDecimal currentRate(String currency) {
        return fetchRate(currency);
    }

    private BigDecimal fetchRate(String currency) {
        // Ví dụ: dữ liệu lấy từ nguồn ngoài.
        return BigDecimal.ONE;
    }
}
~~~

Khi `currentRate(...)` được gọi qua proxy:

1. Spring kiểm tra parameter constraints.
2. Target method chạy.
3. Spring kiểm tra return value.
4. Nếu return không hợp lệ, interceptor phát exception thay vì trả giá trị cho caller.

### Return-value validation không hoàn tác side effect

Nếu method đã ghi database, gửi HTTP request hoặc thay đổi trạng thái trước khi trả giá trị sai, return-value validation chỉ phát hiện lỗi **sau khi thân method đã chạy**.

Ví dụ:

~~~java
@NotNull
public Receipt createReceipt(Order order) {
    repository.save(order);
    return null; // Vi phạm return constraint.
}
~~~

Nếu có transaction và exception làm transaction rollback theo cấu hình phù hợp, phần ghi database có thể rollback. Nhưng side effect bên ngoài database không tự được hoàn tác.

Do đó, return constraint là hợp đồng hữu ích, không phải công cụ bảo đảm atomicity cho toàn bộ hệ thống.

### Cascading trên return value

Có thể yêu cầu kiểm tra object trả về:

~~~java
@NotNull
@Valid
public InvoiceView createInvoice(...) {
    return new InvoiceView(...);
}
~~~

`@Valid` cho phép cascade vào những constraint của `InvoiceView`. Cần hiểu rằng output validation có thể tốn chi phí và exception từ nó thể hiện lỗi của server/service, không nên tự động quy về lỗi input của client.

## 13. Cascading validation với object lồng nhau

Một method có thể nhận một command lớn:

~~~java
public record CustomerAddress(
        @NotBlank String city,
        @NotBlank String postalCode
) {}
~~~

~~~java
public record RegisterCustomerCommand(
        @NotBlank String email,
        @NotNull @Valid CustomerAddress address
) {}
~~~

Service:

~~~java
@Service
@Validated
public class CustomerService {

    public UUID register(
            @NotNull @Valid RegisterCustomerCommand command
    ) {
        // ...
        return UUID.randomUUID();
    }
}
~~~

Nếu `command.address().city()` rỗng, executable validation có thể phát hiện violation bên trong object lồng nhau.

### @NotNull và @Valid bổ sung cho nhau

| Cấu hình | Null có vi phạm? | Kiểm tra object khi khác null? |
|---|---|---|
| `@Valid Address address` | Không vì chỉ @Valid | Có |
| `@NotNull Address address` | Có | Không tự cascade |
| `@NotNull @Valid Address address` | Có | Có |

Đây là một nguồn lỗi thường gặp: lập trình viên chỉ viết `@Valid` và ngạc nhiên khi field null không bị báo lỗi.

### Collection và container element constraints

Có thể áp dụng constraint lên từng phần tử:

~~~java
public record BulkReserveCommand(
        @NotEmpty
        List<@NotBlank String> skus
) {}
~~~

Ở đây:

- `@NotEmpty` yêu cầu danh sách không rỗng.
- `@NotBlank` kiểm tra từng chuỗi phần tử trong container theo khả năng value extraction của Bean Validation provider.

Nếu phần tử là object lồng nhau:

~~~java
public record CreateBatchCommand(
        @NotEmpty
        List<@Valid CreateProductCommand> products
) {}
~~~

Khi batch command được validate, validator có thể đi vào từng `CreateProductCommand`.

Không nên giả định rằng vì method nhận một danh sách thì Bean Validation sẽ tự quét toàn bộ dữ liệu bên trong mà không có annotation cascade/container element phù hợp.

## 14. Validation groups và @Validated

Một object có thể cần quy tắc khác nhau trong các bối cảnh tạo nháp và xuất bản.

Ví dụ nhóm validation:

~~~java
public interface DraftChecks {}
public interface PublishChecks {}
~~~

Command:

~~~java
public record ArticleCommand(
        @NotBlank(groups = {
                DraftChecks.class,
                PublishChecks.class
        })
        String title,

        @NotBlank(groups = PublishChecks.class)
        String content
) {}
~~~

Trong Spring service, `@Validated` hỗ trợ chọn groups theo contract của annotation và method-validation infrastructure.

Ví dụ hai entry point có thể tách thành service khác nhau:

~~~java
@Service
@Validated(DraftChecks.class)
public class DraftArticleService {

    public void saveDraft(
            @NotNull @Valid ArticleCommand command
    ) {
        // Lưu bản nháp.
    }
}
~~~

~~~java
@Service
@Validated(PublishChecks.class)
public class PublishArticleService {

    public void publish(
            @NotNull @Valid ArticleCommand command
    ) {
        // Xuất bản.
    }
}
~~~

Với nhóm `DraftChecks`, ràng buộc title được kiểm tra. Với `PublishChecks`, cả title và content được kiểm tra.

### Các constraint không khai báo group thuộc Default

Bean Validation sử dụng group `Default` khi không chỉ định groups. Nếu bạn gọi validation chỉ với group tùy chỉnh, các constraint chỉ thuộc `Default` không mặc nhiên được kiểm tra trong lần đánh giá đó, trừ khi bạn bao gồm group cần thiết hoặc thiết kế group inheritance/sequence phù hợp.

Ví dụ:

~~~java
@NotBlank
String title;
~~~

không đồng nghĩa sẽ luôn được kiểm tra khi chỉ yêu cầu `PublishChecks.class`.

Đây là một trong những lỗi tinh vi khi áp dụng validation groups: cấu hình group phải phù hợp với chính sách nghiệp vụ.

### Groups không thay thế phân tách command rõ ràng

Nếu object có quá nhiều group, rule kết hợp phức tạp và một field có ý nghĩa khác nhau giữa các use case, tách thành `CreateDraftCommand` và `PublishArticleCommand` có thể đơn giản hơn. Dùng group khi nhiều bối cảnh thực sự chia sẻ một cấu trúc dữ liệu ổn định.

## 15. ConstraintViolationException xuất hiện khi nào?

Trong cơ chế Spring AOP method validation thông thường, khi có vi phạm trên tham số hoặc return value, interceptor mặc định thường ném `jakarta.validation.ConstraintViolationException`.

Ví dụ:

~~~java
try {
    pricingService.calculateTotal(
            new BigDecimal("-5"),
            2
    );
} catch (ConstraintViolationException ex) {
    for (ConstraintViolation<?> violation
            : ex.getConstraintViolations()) {

        System.out.println(
                violation.getPropertyPath()
                        + " : "
                        + violation.getMessage()
        );
    }
}
~~~

`ConstraintViolation` cung cấp các thông tin như:

- `getPropertyPath()`: đường dẫn method, parameter, field lồng nhau hoặc return value.
- `getMessage()`: thông điệp đã được nội suy.
- `getInvalidValue()`: giá trị không hợp lệ.
- `getConstraintDescriptor()`: metadata constraint.

Không nên ghi toàn bộ `getInvalidValue()` vào production log nếu giá trị có thể chứa password, token hoặc thông tin cá nhân.

### Spring Framework hiện đại có thể dùng exception khác

Một số cấu hình method validation hỗ trợ **adaptation** sang API validation result của Spring, có thể dùng `MethodValidationException` thay vì `ConstraintViolationException`.

Cần phân biệt rõ:

1. Service method validation qua AOP interceptor thông thường có thể ném `ConstraintViolationException`.
2. Method validation được cấu hình để thích ứng với Spring validation API có thể ném `MethodValidationException`.
3. Spring MVC 6.1+ có cơ chế native handler-method validation và exception `HandlerMethodValidationException`.

Không nên viết một global exception handler giả định mọi loại method validation trong ứng dụng luôn ném cùng một exception. Hãy xem đúng tầng và phiên bản framework đang sử dụng.

## 16. Validation tại HTTP controller và service khác nhau

Một REST controller có thể dùng:

~~~java
@PostMapping("/customers")
public ResponseEntity<Void> create(
        @Valid @RequestBody CreateCustomerRequest request
) {
    service.create(request.toCommand());
    return ResponseEntity.accepted().build();
}
~~~

Trong Spring MVC, validation của body được thực hiện trong quá trình giải quyết argument/binding. Với những cấu hình phổ biến, lỗi từ `@Valid @RequestBody` có thể thành `MethodArgumentNotValidException` và được Spring MVC map sang HTTP 400.

Service:

~~~java
@Service
@Validated
public class CustomerService {

    public void create(
            @NotNull @Valid CreateCustomerCommand command
    ) {
        // ...
    }
}
~~~

Service method validation dùng AOP proxy để bảo vệ lời gọi nghiệp vụ dù caller đến từ HTTP, job hay message listener. Exception và cách xử lý thường khác controller argument validation.

### Không phải mọi lỗi service đều là HTTP 400

Nếu server tự tính ra một giá trị sai rồi truyền nó vào service, đó có thể là bug ở server, không phải lỗi client. Việc bắt mọi `ConstraintViolationException` và trả 400 có thể che giấu lỗi nội bộ.

Hãy xác định nguồn dữ liệu và boundary: lỗi input của client cần phản hồi client phù hợp; vi phạm hợp đồng giữa các component nội bộ có thể là HTTP 500 và cần được quan sát như bug.

### Một controller và một service có thể cùng validate

Điều này không làm semantics của hai tầng trở thành giống nhau. Controller xử lý HTTP binding và lỗi nhập liệu; service bảo vệ contract sử dụng lại được. Nếu yêu cầu hiệu năng hoặc kiến trúc khiến double validation không mong muốn, có thể thiết kế ranh giới rõ thay vì xóa method validation một cách tùy tiện.

## 17. Spring MVC 6.1+ có native handler-method validation

Một điểm dễ gây nhầm trong các phiên bản mới: **method validation ở Spring MVC controller không nhất thiết dựa vào cùng một AOP proxy như service validation**.

Spring Framework 6.1 trở lên có hỗ trợ method validation tích hợp trong MVC handler method invocation. Ví dụ:

~~~java
@RestController
@RequestMapping("/api/items")
public class ItemController {

    @GetMapping("/{id}")
    public ItemView find(
            @PathVariable @Positive Long id
    ) {
        return itemService.find(id);
    }
}
~~~

Constraint đặt trực tiếp trên `@PathVariable` có thể được MVC kiểm tra trong quá trình gọi handler method. Khi validation của toàn handler method được yêu cầu, Spring MVC hiện đại có thể phát `HandlerMethodValidationException`.

### Vì sao @Validated trên controller cần xem lại?

Trong Spring MVC 6.1+, tài liệu Spring hướng dẫn **loại bỏ `@Validated` ở cấp controller class nếu muốn sử dụng native MVC method validation**, vì `@Validated` ở type level có thể khiến controller được xử lý bằng phương thức AOP validation cũ.

Điều này không mâu thuẫn với nguyên tắc service cần `@Validated` khi dùng Spring AOP method validation. Hai tầng có infrastructure khác nhau:

~~~text
HTTP request
    |
    v
Spring MVC binding / handler invocation
    |
    +--> Native MVC validation (Spring 6.1+)
    |
    v
Controller method
    |
    v
Service proxy
    |
    +--> AOP method validation nếu service @Validated
    |
    v
Service target
~~~

Với ứng dụng dùng Spring Boot trước thế hệ tương ứng, cơ chế controller method validation có thể khác. Không nên sao chép nguyên xử lý exception từ một bản Boot cũ sang bản Boot mới mà không hiểu tầng đang kiểm tra.

### MethodArgumentNotValidException và HandlerMethodValidationException

Trong Spring MVC hiện đại:

- `MethodArgumentNotValidException` thường xuất hiện khi riêng một argument như `@RequestBody` có `@Valid` được xử lý theo luồng validation của argument resolver.
- `HandlerMethodValidationException` có thể xuất hiện khi validation trực tiếp ở cấp handler method được kích hoạt bởi constraints như `@Min` trên `@RequestParam` hoặc `@Positive` trên `@PathVariable`.

Sự kết hợp annotation và phiên bản Spring quyết định exception cụ thể. Khi xử lý API error, nên dùng Spring MVC exception handling có cấu trúc và map đúng lỗi cho client, đồng thời không vô tình nuốt lỗi của service.

## 18. @Validated và @Transactional cùng xuất hiện

Một service thường đồng thời có transaction và method validation:

~~~java
@Service
@Validated
public class WalletService {

    private final WalletRepository repository;

    public WalletService(WalletRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void transfer(
            @NotNull UUID fromWalletId,
            @NotNull UUID toWalletId,
            @Positive BigDecimal amount
    ) {
        // Debit, credit và lưu thay đổi.
    }
}
~~~

Spring có thể áp dụng cả transaction advice và validation advice lên cùng một bean.

Luồng ý tưởng:

~~~text
Caller
   |
   v
Spring AOP proxy / advisors
   |
   +--> Validation advice
   |
   +--> Transaction advice
   |
   v
WalletService.transfer(...)
~~~

**Thứ tự thực tế của advisors không nên được tự suy đoán từ vị trí annotation.** Nó phụ thuộc ordering và cấu hình infrastructure. Dù validation được kiểm tra trước hay sau khi transaction advice bắt đầu, contract đầu vào vẫn phải được giữ trước khi nghiệp vụ có side effect cần thiết.

### Validation exception có rollback không?

Theo cấu hình transaction kiểu declarative thông dụng, unchecked exception như `ConstraintViolationException` có thể khiến transaction rollback nếu exception xảy ra trong transaction boundary do Spring quản lý.

Nhưng cần phân biệt:

- Nếu validation advice ném exception **trước khi transaction bắt đầu**, không có transaction mới để rollback.
- Nếu một return-value violation xảy ra **bên trong transaction advice**, transaction có thể rollback theo rule.
- Nếu return-value validation được thực hiện **sau khi transaction đã commit**, phát hiện lỗi không thể quay ngược một commit đã hoàn tất.

Do đó, không chỉ annotation mà thứ tự advice và transaction propagation mới quyết định hậu quả chính xác.

### Không dựa vào validation để thay thế business invariant

Constraint như `@Positive amount` kiểm tra shape và giá trị đầu vào, nhưng không bảo đảm ví có đủ số dư hoặc hai thao tác cập nhật được commit nhất quán.

Những invariant cần state dữ liệu, locking hoặc isolation phải được xử lý trong domain/service và transaction. Method validation không tự giải quyết race condition hoặc tính nhất quán database.

## 19. Validation ở tầng dữ liệu và database

Chương “Tài nguyên và dữ liệu” cần phân biệt ba lớp ràng buộc:

1. **Input/application method validation:** kiểm tra contract trước khi service thực hiện công việc.
2. **Entity validation:** kiểm tra một số constraint trên state của entity, có thể tích hợp qua persistence lifecycle tùy provider/cấu hình.
3. **Database constraints:** bảo vệ dữ liệu ở mức lưu trữ, ví dụ `NOT NULL`, `UNIQUE` hoặc `CHECK`.

Ví dụ:

~~~java
@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue
    private Long id;

    @NotBlank
    @Column(nullable = false)
    private String sku;

    @NotNull
    @Positive
    @Column(nullable = false)
    private BigDecimal price;

    // Constructors, getters, domain behavior...
}
~~~

`@NotBlank` và `@Positive` là Bean Validation constraints. `@Column(nullable = false)` là metadata ORM dùng để mô tả column nullability, nhưng nó **không thay thế một database migration** được áp dụng đúng lên schema thật.

### Method validation không bảo vệ mọi đường ghi dữ liệu

Một import script, một công cụ quản trị, SQL thủ công hoặc service khác có thể ghi vào database mà không gọi Spring service method. Vì vậy, dữ liệu trọng yếu cần được bảo vệ bằng database constraints và domain invariants ở nơi thích hợp.

Ví dụ nếu `sku` phải duy nhất, database `UNIQUE` constraint giúp bảo vệ trước race condition mà một lời gọi `repository.existsBySku(...)` đơn thuần không thể loại bỏ hoàn toàn.

### Không để entity trở thành DTO mặc định cho API

Việc gắn validation trên entity có thể hữu ích, nhưng nếu dùng trực tiếp entity cho mọi request thì coupling giữa HTTP contract, domain model và persistence sẽ tăng. Một ứng dụng có thể phân biệt request DTO, service command và entity, mỗi tầng có ràng buộc phù hợp.

## 20. ConstraintViolationException và lỗi persistence không giống nhau

Một `ConstraintViolationException` từ Jakarta Validation nói rằng **một constraint Bean Validation đã bị vi phạm**.

Trong Hibernate ORM và cơ sở dữ liệu, các lỗi cũng có thể dùng tên gần giống “constraint violation” để chỉ vi phạm khóa ngoại, unique index hoặc NOT NULL tại database.

Đừng nhầm:

~~~java
jakarta.validation.ConstraintViolationException
~~~

với những exception của persistence provider, ví dụ:

~~~java
org.hibernate.exception.ConstraintViolationException
~~~

hoặc Spring DataAccessException wrapper.

Dù tên giống nhau, chúng xuất hiện từ những tầng khác:

| Lỗi | Nguồn thường gặp |
|---|---|
| Jakarta `ConstraintViolationException` | Bean Validation, bao gồm AOP method validation |
| Hibernate ORM constraint violation | SQL/database constraint |
| Spring `DataIntegrityViolationException` | Abstraction lỗi toàn vẹn dữ liệu của persistence layer |
| Spring MVC `MethodArgumentNotValidException` | Validation tại argument binding |
| Spring MVC `HandlerMethodValidationException` | Native method validation của MVC hiện đại |

Một exception handler hoặc retry policy cần nhận diện đúng class và ngữ cảnh.

## 21. Programmatic method validation khi không có proxy

Nếu code cần kiểm tra một phương thức không được gọi qua Spring proxy, có thể dùng `ExecutableValidator` trực tiếp.

Ví dụ một class Java thuần:

~~~java
public class ShippingCalculator {

    public BigDecimal calculate(
            @NotNull @Positive BigDecimal weight,
            @Positive int distanceKm
    ) {
        return weight.multiply(
                BigDecimal.valueOf(distanceKm)
        );
    }
}
~~~

Kiểm tra arguments:

~~~java
Validator validator =
        Validation.buildDefaultValidatorFactory()
                .getValidator();

ExecutableValidator executableValidator =
        validator.forExecutables();

ShippingCalculator target =
        new ShippingCalculator();

Method method = ShippingCalculator.class.getMethod(
        "calculate",
        BigDecimal.class,
        int.class
);

Object[] arguments = {
        new BigDecimal("-2"),
        10
};

Set<ConstraintViolation<ShippingCalculator>> violations =
        executableValidator.validateParameters(
                target,
                method,
                arguments
        );
~~~

Để dùng trong ứng dụng Spring Boot, nên **inject `Validator` do Spring quản lý** và gọi `validator.forExecutables()`, thay vì tạo `ValidatorFactory` mới mỗi lần kiểm tra.

Nếu tạo `ValidatorFactory` thủ công như ví dụ standalone, code thực tế cần đóng factory khi không còn sử dụng:

~~~java
try (ValidatorFactory factory =
             Validation.buildDefaultValidatorFactory()) {

    Validator validator = factory.getValidator();
    // ...
}
~~~

Programmatic validation hữu ích khi:

- Đối tượng không phải Spring bean.
- Muốn chủ động kiểm tra ở một bước cụ thể.
- Có self-invocation không muốn tách bean.
- Viết thư viện Java không phụ thuộc Spring AOP.

Nhưng nó yêu cầu code chủ động thực thi kiểm tra; annotation không tự động gọi API này.

### Kiểm tra return value bằng API tường minh

~~~java
BigDecimal value = target.calculate(
        new BigDecimal("2"),
        10
);

Set<ConstraintViolation<ShippingCalculator>> returnViolations =
        executableValidator.validateReturnValue(
                target,
                method,
                value
        );
~~~

Ở đây caller tự quyết định phải làm gì nếu tập violations không rỗng. Spring AOP method validation bình thường làm bước đó tự động qua interceptor.

## 22. Validation trên interface và method inheritance

Nếu service triển khai interface, constraint declaration phải tuân theo quy tắc của Jakarta Bean Validation về method inheritance.

Một interface:

~~~java
public interface PaymentService {

    Receipt charge(
            @NotNull @Positive BigDecimal amount
    );
}
~~~

Implementation:

~~~java
@Service
@Validated
public class DefaultPaymentService implements PaymentService {

    @Override
    public Receipt charge(BigDecimal amount) {
        // ...
        return new Receipt();
    }
}
~~~

Parameter contract nằm trên interface. Đây là cách tương đối rõ ràng vì mọi implementation đều tuân theo cùng một contract.

### Không tùy ý tăng yêu cầu parameter trên override

Ví dụ có thể vi phạm quy tắc Bean Validation:

~~~java
public interface PaymentService {
    Receipt charge(BigDecimal amount);
}
~~~

~~~java
public class DefaultPaymentService implements PaymentService {

    @Override
    public Receipt charge(
            @Positive BigDecimal amount
    ) {
        // ...
        return new Receipt();
    }
}
~~~

Một provider như Hibernate Validator có thể báo lỗi cấu hình executable constraints vì implementation đang bổ sung điều kiện tiên quyết so với hợp đồng method kế thừa.

Quy tắc này liên quan nguyên tắc thay thế kiểu (Liskov substitution): implementation không được bất ngờ đòi hỏi đầu vào khắt khe hơn contract của interface.

Return-value constraints có những quy tắc kế thừa khác, và có thể được tăng cường trong những giới hạn của specification. Khi dùng interface hierarchy phức tạp, nên đặt constraint rõ ràng trên hợp đồng chung và tránh rải annotation xung đột giữa nhiều tầng.

## 23. Annotation nằm trên interface nhưng bean bị proxy theo class?

Spring và Bean Validation có khả năng đọc metadata constraint trong hierarchy/interface theo cơ chế provider. Tuy nhiên, việc **method có được chặn hay không** vẫn phụ thuộc cách Spring tạo proxy và cách caller truy cập bean.

Trong một ứng dụng có nhiều implementation, nên:

1. Đặt executable parameter constraints trên contract interface chung khi phù hợp.
2. Đảm bảo implementation được Spring quản lý.
3. Đánh dấu type phù hợp bằng `@Validated` theo cơ chế method-validation infrastructure được dùng.
4. Inject đúng abstraction mà proxy cung cấp.
5. Kiểm thử một lời gọi thật qua ApplicationContext.

Đừng chỉ suy luận từ việc runtime class có hay không có annotation trực tiếp; Spring AOP và Bean Validation có thể dùng metadata từ nhiều vị trí.

## 24. Groups không làm Spring tự chọn một phương thức khác

Validation groups chọn **tập constraint cần kiểm tra**, không thay thế method overloading hoặc business dispatch.

Ví dụ:

~~~java
@Validated(PublishChecks.class)
public class PublishService {

    public void publish(
            @NotNull @Valid ArticleCommand command
    ) {
        // ...
    }
}
~~~

Nếu constraint không thỏa, interceptor có thể từ chối lời gọi. Nếu thỏa, cùng một method vẫn chạy. Không có việc Spring tự tìm một method dành riêng cho group `PublishChecks`.

Nếu use case draft và publish có workflow khác nhau, nên dùng hai method/service với tên rõ ràng, thay vì dùng groups để giấu sự khác biệt nghiệp vụ.

## 25. Validation exception và cách xử lý API error

Nếu lỗi xảy ra ở controller binding, có thể dùng cơ chế xử lý exception chuẩn của Spring MVC để trả response 400 kèm thông tin field hợp lệ.

Ví dụ khung xử lý:

~~~java
@RestControllerAdvice
public class ApiValidationExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, String>> handleInvalidBody(
            MethodArgumentNotValidException ex
    ) {
        Map<String, String> errors = new LinkedHashMap<>();

        ex.getBindingResult()
                .getFieldErrors()
                .forEach(error ->
                        errors.putIfAbsent(
                                error.getField(),
                                error.getDefaultMessage()
                        )
                );

        return ResponseEntity
                .badRequest()
                .body(errors);
    }
}
~~~

Đây là ví dụ minh họa response ngắn; trong hệ thống thật nên dùng error contract thống nhất, tránh lộ dữ liệu nhạy cảm và cân nhắc trường hợp nhiều lỗi trên cùng field.

Với Spring MVC 6.1+, có thể cần xử lý thêm `HandlerMethodValidationException` cho native method validation. Với AOP service method validation, có thể cần xử lý `ConstraintViolationException` hoặc một loại exception khác tùy cấu hình.

**Không tự động trả 400 cho mọi `ConstraintViolationException` từ service.** Nếu lỗi do service khác lập trình sai hoặc return-value validation thất bại, đó có thể là lỗi server. Phải phân biệt input boundary với invariant nội bộ.

### Message interpolation và quốc tế hóa

Bean Validation hỗ trợ thông điệp mặc định và message template:

~~~java
@NotBlank(message = "SKU không được để trống")
String sku;
~~~

Có thể tích hợp message bundles để quốc tế hóa. Nhưng message hiển thị người dùng không nên chứa dữ liệu nhạy cảm từ `invalidValue`. Một API ổn định thường trả error code riêng ngoài human-readable message.

## 26. Không lạm dụng annotation cho mọi quy tắc nghiệp vụ

Các constraint cơ bản phù hợp với quy tắc **cục bộ, xác định từ dữ liệu đang có**:

- Không null.
- Chuỗi không rỗng.
- Độ dài hợp lệ.
- Giá trị số trong phạm vi.
- Email có định dạng hợp lý.
- Cascading validation trên command.

Những điều kiện như “SKU chưa tồn tại trong database”, “đơn còn đủ hạn mức”, “tài khoản chưa bị khóa” cần truy cập state hệ thống và có thể có race condition. Nếu đưa hết vào custom validator, logic validation dễ phụ thuộc database, transaction và thời điểm tạo bean.

Có thể tạo custom Bean Validation constraint cho trường hợp có giá trị, nhưng phải xem xét:

- Validator có side effect hay không.
- Có phụ thuộc service, repository hoặc giao dịch không.
- Có cần khóa/đảm bảo nhất quán khi nhiều request cạnh tranh không.
- Lỗi nên trả dưới dạng input validation hay domain exception.

Business invariant cần được thực thi trong domain/application service và database khi thích hợp; method validation chỉ là một lớp của hệ thống bảo vệ dữ liệu.

## 27. Kiểm thử method validation qua Spring proxy

Một unit test tạo service trực tiếp có thể bỏ qua proxy. Nếu muốn xác nhận ràng buộc method được Spring thực thi, nên dùng một Spring test context có bean validation infrastructure.

Ví dụ:

~~~java
@SpringBootTest
class PricingServiceMethodValidationTest {

    @Autowired
    PricingService pricingService;

    @Test
    void rejectsNegativePrice() {
        assertThrows(
                ConstraintViolationException.class,
                () -> pricingService.calculateTotal(
                        new BigDecimal("-1"),
                        2
                )
        );
    }

    @Test
    void acceptsValidArguments() {
        BigDecimal total =
                pricingService.calculateTotal(
                        new BigDecimal("12.50"),
                        3
                );

        assertEquals(
                new BigDecimal("37.50"),
                total
        );
    }
}
~~~

Test giả định `PricingService` được đăng ký như Spring bean, có `@Validated`, starter validation và cấu hình mặc định ném `ConstraintViolationException`. Nếu ứng dụng đã bật exception adaptation hoặc thay đổi infrastructure, cần xác nhận loại exception tương ứng.

### Vì sao @SpringBootTest quan trọng ở đây?

Test qua Spring context có cơ hội đi qua đúng proxy và post-processor. Một test chỉ gọi:

~~~java
new PricingService().calculateTotal(
        new BigDecimal("-1"),
        2
);
~~~

không kiểm tra hiệu lực của Spring AOP. Nó chỉ chạy thân method Java.

### Kiểm tra proxy ở mức kỹ thuật

Khi cần chẩn đoán, Spring cung cấp tiện ích:

~~~java
boolean proxied = AopUtils.isAopProxy(pricingService);
~~~

Có thể sử dụng kết quả này để biết reference là AOP proxy. Tuy nhiên, **một bean được proxy không đồng nghĩa mọi method đều có validation advice**: proxy có thể được tạo vì transaction, security hoặc caching; method cụ thể cũng có thể bị loại do visibility hoặc self-invocation.

Cách xác nhận mạnh hơn là gọi phương thức qua injected bean với dữ liệu vi phạm và quan sát exception.

## 28. Kiểm thử self-invocation và cách sửa

Giả sử:

~~~java
@Service
@Validated
public class CouponService {

    public void process(String code) {
        validateCode(code); // Self-invocation.
    }

    public void validateCode(
            @NotBlank String code
    ) {
        // ...
    }
}
~~~

Một test gọi:

~~~java
couponService.validateCode("");
~~~

có thể nhận violation, nhưng:

~~~java
couponService.process("");
~~~

có thể không nhận validation exception từ `validateCode(...)` nếu `process(...)` tự nó không có constraint và lời gọi nội bộ bypass proxy.

Để bảo vệ method `process(...)`, có thể đặt constraint ngay trên public entry point:

~~~java
public void process(@NotBlank String code) {
    validateCode(code);
}
~~~

hoặc tách `validateCode` sang một Spring bean khác như đã trình bày.

**Bài học:** kiểm thử không chỉ “annotation tồn tại” mà còn kiểm tra **đường đi thực tế của caller**.

## 29. Validation trong async, scheduled và message listeners

Spring Boot có nhiều entry point ngoài REST controller:

- `@Scheduled` method.
- `@Async` method.
- Kafka/RabbitMQ message listener.
- `ApplicationRunner` hoặc `CommandLineRunner`.
- Domain event listener.

Nếu một component chuyển dữ liệu sang service `@Validated` qua Spring proxy, method validation có thể bảo vệ service boundary. Nhưng nếu chính method của một bean gọi method validation khác trong cùng class, self-invocation vẫn có thể bỏ qua interceptor.

### @Async và AOP

`@Async` thường cũng phụ thuộc proxy. Nếu method validation và async advice cùng tồn tại, thứ tự advice và thread xử lý có thể ảnh hưởng nơi exception xuất hiện và cách caller nhận kết quả.

Ví dụ:

~~~java
@Service
@Validated
public class ExportService {

    @Async
    public CompletableFuture<String> export(
            @NotBlank String exportId
    ) {
        return CompletableFuture.completedFuture(
                "export-" + exportId
        );
    }
}
~~~

Không nên đoán rằng invalid argument luôn làm caller nhận exception đồng bộ hay luôn xuất hiện trong `CompletableFuture`; hãy xem advice ordering và API async của dự án. Với async method có kiểu trả `void`, exception có thể được xử lý bởi cơ chế async error handler thay vì truyền trực tiếp về caller.

### Scheduled method không nhận tham số từ scheduler thông thường

Một `@Scheduled` method thường không có method parameters do scheduler truyền. Method validation parameter constraints vì thế ít ý nghĩa trực tiếp cho scheduled entry point. Hãy đặt validation trên service mà scheduled job gọi, để giữ hợp đồng có thể tái sử dụng.

### Message consumer cần xử lý lỗi hợp đồng

Nếu message listener gọi một validated service và nhận `ConstraintViolationException`, consumer phải có chính sách reject, retry hoặc dead-letter phù hợp. Đừng để một message dữ liệu sai bị retry vô hạn chỉ vì exception là RuntimeException.

Method validation phát hiện lỗi; **cách phản ứng với lỗi** thuộc messaging infrastructure và nghiệp vụ.

## 30. Khi validation không chạy: quy trình chẩn đoán

Nếu một constraint tồn tại nhưng lời gọi vẫn đi qua bình thường, hãy lần lượt kiểm tra:

~~~text
Method có constraint
       |
       v
Có Bean Validation provider?
       |
       v
Có MethodValidationPostProcessor?
       |
       v
Bean có được Spring quản lý?
       |
       v
Type có @Validated phù hợp?
       |
       v
Reference gọi có phải proxy?
       |
       v
Lời gọi có đi từ ngoài qua proxy?
       |
       v
Method có thể được intercept?
       |
       v
Constraint/group có được chọn?
       |
       v
Lỗi có bị catch/convert ở tầng khác?
~~~

Một số tình huống cụ thể:

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| `@NotNull` không chặn input null | Thiếu method validation infrastructure hoặc `@Validated` | Kiểm tra starter và bean setup |
| Gọi trực tiếp method có lỗi, gọi qua method khác lại không | Self-invocation | Đưa constraint lên public entry point hoặc tách bean |
| Unit test bằng `new` không báo violation | Không có Spring proxy | Test qua context hoặc validate tường minh |
| Bean không tạo được proxy | Final class/method hoặc proxy type không phù hợp | Thiết kế type/method có thể proxy |
| Không tìm thấy bean theo implementation class | Đang dùng JDK interface proxy | Inject interface hoặc cấu hình proxy phù hợp |
| `@Valid` vẫn cho null | `@Valid` chỉ cascade | Thêm `@NotNull` |
| Method nhận object lồng nhau không báo lỗi | Thiếu cascade hoặc container constraints | Thêm `@Valid` đúng chỗ |
| Một constraint không chạy khi dùng group | Constraint thuộc group khác hoặc Default | Xem group declarations |
| Service báo violation nhưng controller không trả 400 | Khác tầng validation/exception mapping | Thiết kế exception handler đúng nguồn |
| Sau khi commit mới phát hiện return violation | Thứ tự advisors khác dự kiến | Kiểm soát transaction/validation boundary |
| Controller Spring 6.1+ báo exception khác dự kiến | MVC native method validation | Phân biệt `HandlerMethodValidationException` với AOP |
| Method trong scheduled/listener bỏ qua constraint | Gọi nội bộ hoặc không qua proxy | Tách validated service |

Cần lưu ý scope của hạ tầng: nếu ứng dụng có nhiều ApplicationContext hoặc custom parent/child setup, bean validation post-processor phải nằm trong context quản lý bean cần proxy.

## 31. Những hiểu nhầm cần tránh

### “Có @Valid thì service method tự được validate”

Không đúng trong mọi trường hợp. `@Valid` mô tả cascade; việc service method được kiểm tra tự động còn phụ thuộc Spring method validation infrastructure và đường gọi qua proxy.

### “@Validated chỉ cần đặt trên parameter”

Không phải cách phổ biến để kích hoạt AOP method validation của một Spring service. Đối với service method-validation proxy, type-level `@Validated` là dấu hiệu quan trọng. `@Validated` trên parameter ở MVC/data binding có những ngữ cảnh khác.

### “Proxy nào cũng chặn mọi method”

Sai. Proxy chỉ chặn những method/call phù hợp. Private/final/static methods hoặc self-invocation có giới hạn riêng, tùy loại proxy.

### “@Transactional và @Validated luôn chạy theo thứ tự annotation”

Sai. Annotation không trực tiếp biểu diễn thứ tự advisor. Transaction boundary chính xác cần xét infrastructure order.

### “Một lỗi ConstraintViolationException luôn đến từ database”

Sai. Jakarta Bean Validation và ORM/database có các exception tên gần giống nhưng thuộc tầng khác.

### “Lỗi validation nào cũng là lỗi client”

Sai. Return-value violation và sai hợp đồng giữa service nội bộ có thể là lỗi server. HTTP 400 phù hợp khi client cung cấp input không hợp lệ, không phải mọi vi phạm method constraint.

### “Validation thay thế database unique constraint”

Sai. Method validation không ngăn được mọi đường ghi dữ liệu hoặc race condition. Data integrity cần cơ chế database và transaction phù hợp.

## 32. Nguyên tắc thiết kế method validation có thể bảo trì

1. **Đặt constraint ở boundary có hợp đồng rõ.** Service public method được dùng bởi nhiều entry point là vị trí phù hợp.
2. **Tách annotation khỏi cơ chế thực thi trong tư duy.** Constraint tồn tại không có nghĩa Spring đã gọi validator.
3. **Dùng `@Validated` cho Spring service AOP method validation** trong cấu hình phổ biến.
4. **Giữ public method có thể được proxy intercept.** Tránh phụ thuộc vào private/final method.
5. **Không kỳ vọng self-invocation được intercept.** Dùng collaborator bean hoặc validate tường minh.
6. **Dùng `@NotNull @Valid` khi object lồng nhau vừa bắt buộc vừa cần cascade.**
7. **Khai báo constraints theo contract inheritance.** Với interface, tránh tăng parameter precondition trong override.
8. **Cân nhắc groups trước khi áp dụng rộng.** Constraint thuộc `Default` có thể không được chọn khi validate chỉ với group riêng.
9. **Phân biệt controller và service validation.** MVC 6.1+ có native handler-method validation; service vẫn có AOP concerns.
10. **Không map mọi lỗi method validation thành HTTP 400.** Phân biệt input của client với bug nội bộ.
11. **Không dùng annotation để bảo đảm bất biến cần transaction/database.** Kiểm tra state và khóa/constraint phù hợp.
12. **Đừng bỏ qua return-value validation.** Nó phát hiện lỗi contract của kết quả nhưng cần lưu ý side effect đã chạy.
13. **Kiểm thử lời gọi qua Spring context.** Unit test bằng `new` không chứng minh proxy hoạt động.
14. **Quan sát proxy và exception đúng tầng.** `ConstraintViolationException`, `MethodValidationException` và `HandlerMethodValidationException` có ngữ cảnh khác nhau.
15. **Thiết kế xử lý lỗi cho async/messaging.** Validation chỉ báo vi phạm, còn retry/dead-letter thuộc policy vận hành.

## 33. Một kịch bản thực tế: REST, batch và message dùng chung service

Giả sử hệ thống quản lý tài nguyên có ba cách tạo yêu cầu cấp phát:

~~~text
HTTP POST /allocations
        |
        v
AllocationController
        |
        +-------------------------------+
                                        |
CSV import -> AllocationBatchRunner ----+--> AllocationService proxy
                                        |          |
Message -> AllocationMessageListener ---+          v
                                               Method validation
                                                    |
                                                Domain checks
                                                    |
                                               Database transaction
~~~

Service contract:

~~~java
@Service
@Validated
public class AllocationService {

    private final AllocationRepository repository;

    public AllocationService(AllocationRepository repository) {
        this.repository = repository;
    }

    @Transactional
    @NotNull
    public UUID allocate(
            @NotNull UUID resourceId,
            @NotNull UUID ownerId,
            @Positive int quantity
    ) {
        Allocation allocation =
                Allocation.create(resourceId, ownerId, quantity);

        repository.save(allocation);

        return allocation.getId();
    }
}
~~~

Nếu HTTP controller đã validate DTO, điều đó giúp trả lỗi nhập liệu sớm. Nhưng batch runner và message listener có thể không đi qua HTTP binding. Khi tất cả inject `AllocationService` do Spring quản lý, cùng một method contract có thể được kiểm tra qua proxy.

Bên trong `allocate(...)` vẫn phải kiểm tra invariant như “tài nguyên còn đủ quota” dựa trên trạng thái database. `@Positive quantity` chỉ ngăn số âm và số 0, không bảo đảm cấp phát hợp lệ khi nhiều request cạnh tranh.

Nếu một listener nhận message không hợp lệ, cần có error handling để không retry mãi một dữ liệu không thể sửa. Nếu một transaction thất bại vì unique constraint, đó là lỗi data integrity khác với method parameter violation.

Tình huống này cho thấy method validation hữu ích nhất khi nó bảo vệ **ranh giới có thể tái sử dụng**, trong khi Spring proxy, database và các entry point phối hợp đúng trách nhiệm.

## Kết luận

Method validation cho phép đặt Bean Validation constraints trực tiếp trên tham số, đối tượng lồng nhau và giá trị trả về của phương thức. Trong Spring Boot, các service `@Validated` thường được xử lý bởi `MethodValidationPostProcessor` và `MethodValidationInterceptor`, thông qua **AOP proxy**. Bên gọi đi qua proxy được kiểm tra trước/sau target method; còn self-invocation, object tự tạo bằng `new` hoặc method không thể được proxy chặn có thể bỏ qua validation.

Phải phân biệt `@Valid` dùng để cascade, `@Validated` là tín hiệu tích hợp Spring và hỗ trợ groups, còn các constraint như `@NotNull`, `@Positive` là chính quy tắc kiểm tra. Trong Spring MVC hiện đại, controller handler-method validation có thể hoạt động bằng cơ chế tích hợp của MVC thay vì cùng đường AOP của service, nên exception và cách xử lý lỗi có thể khác nhau.

Method validation là một lớp bảo vệ hợp đồng giữa các component, không thay thế transaction, domain invariants hoặc database constraints. Khi hiểu đúng đường gọi, loại proxy, validation groups, thứ tự advice và exception boundary, người phát triển có thể áp dụng method validation nhất quán cho REST, batch, scheduler và message consumer mà không bị bất ngờ vì annotation “có nhưng không chạy”.
