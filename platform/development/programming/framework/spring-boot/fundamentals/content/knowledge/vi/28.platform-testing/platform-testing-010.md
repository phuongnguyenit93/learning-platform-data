# Phân biệt smoke test context với kiểm thử hành vi nghiệp vụ

Khi mới tạo một project Spring Boot, bạn thường thấy lớp test có tên `ApplicationTests` và một method rỗng:

```java
@SpringBootTest
class ApplicationTests {

    @Test
    void contextLoads() {
    }
}
```

Method này không gọi service, không gửi HTTP request và cũng không so sánh kết quả nào. Tuy vậy, nó có giá trị: nếu test chạy thành công, Spring Boot đã khởi tạo được `ApplicationContext` cần thiết trong môi trường test đó.

Vấn đề xuất hiện khi chúng ta hiểu nhầm rằng **context khởi động thành công nghĩa là ứng dụng đã được kiểm thử đúng**. Một service tính sai tiền, một API trả status sai, một repository lưu dữ liệu không đúng hoặc một authorization rule bị bỏ qua vẫn có thể tồn tại dù `contextLoads()` luôn xanh.

Bài học thuộc chương **Kiểm thử nền tảng** của **Spring Boot Fundamentals**. Trọng tâm là phân biệt:

- **Smoke test context:** kiểm tra nhanh khả năng bootstrap và wiring của Spring context theo cấu hình test.
- **Kiểm thử hành vi nghiệp vụ:** đưa input, thực thi hành vi và khẳng định output, side effect hoặc exception thực sự đáp ứng yêu cầu.
- **Kiểm thử tích hợp và HTTP contract:** xác nhận các thành phần phối hợp đúng qua những ranh giới như controller, persistence và hệ thống bên ngoài.

Sau khi học, bạn cần biết mỗi loại test chứng minh điều gì, điều gì **không được chứng minh**, và vì sao một bộ test Spring Boot đáng tin cậy cần nhiều lớp kiểm thử thay vì chỉ một `contextLoads()`.

## 1. Smoke test là gì?

Trong kiểm thử phần mềm, “smoke test” thường là một phép kiểm tra nhanh để xác nhận hệ thống hoặc một phần hệ thống đủ ổn để tiếp tục kiểm tra sâu hơn. Trong ngữ cảnh Spring Boot, **context smoke test** là bài test kiểm tra quá trình tạo `ApplicationContext` có hoàn tất hay không.

Ví dụ:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ShopApplicationTests {

    @Test
    void contextLoads() {
    }
}
```

Chạy lớp test này khiến Spring Test dùng Spring Boot bootstrap để tạo một context cho ứng dụng. Nếu cấu hình thất bại trong quá trình load context, bài test bị đánh dấu failed.

### 1.1. Vì sao method test có thể rỗng?

Bởi vì **việc chuẩn bị Spring context đã diễn ra trước lúc JUnit gọi method**.

Sơ đồ:

```text
JUnit phát hiện test class
           │
           ▼
Spring TestContext Framework
           │
           ▼
Spring Boot test bootstrap
           │
           ▼
Đọc cấu hình test, profiles, properties
           │
           ▼
Xử lý configuration/auto-configuration
           │
           ▼
Tạo và inject các bean cần thiết
           │
           ▼
Refresh ApplicationContext
           │
      ┌────┴─────┐
      │          │
      ▼          ▼
Thành công      Thất bại
      │          │
      ▼          ▼
Gọi method      Báo test failed
contextLoads()
      │
      ▼
Test thành công
```

Method rỗng không phải “không kiểm thử gì”. Nó là một cách kiểm tra gián tiếp rằng quy trình chuẩn bị context của Spring TestContext đã hoàn tất trong điều kiện test.

### 1.2. Một vài lỗi context smoke test có thể phát hiện

Nếu ứng dụng cần các bean sau:

```java
@Service
public class CheckoutService {

    private final InventoryClient inventoryClient;

    public CheckoutService(InventoryClient inventoryClient) {
        this.inventoryClient = inventoryClient;
    }
}
```

nhưng context test không có bean `InventoryClient` phù hợp, việc tạo `CheckoutService` có thể thất bại.

Các tình huống khác:

- Có hai bean cùng type nhưng injection không chỉ rõ candidate.
- Constructor dependency không thể resolve.
- `@Configuration` tạo bean thất bại.
- Một `@ConfigurationProperties` bắt buộc không bind hoặc validate được.
- Auto-configuration cần thành phần hạ tầng nhưng không có.
- Một số lỗi kết nối external service xuất hiện khi bean khởi tạo, nếu ứng dụng thực sự kết nối tại thời điểm đó.
- Classpath hoặc component scan khiến cấu hình không hợp lệ.
- Bean initialization callback ném exception.

Nhưng smoke test chỉ bắt được những vấn đề **thực sự được kích hoạt trong quá trình test context khởi tạo**.

## 2. Vì sao contextLoads không đủ để khẳng định ứng dụng đúng?

Xét service tính giá:

```java
@Service
public class PriceService {

    public BigDecimal total(
            BigDecimal unitPrice,
            int quantity
    ) {
        return unitPrice.add(
                BigDecimal.valueOf(quantity)
        );
    }
}
```

Quy tắc nghiệp vụ cần là:

```text
total = unitPrice × quantity
```

Nhưng code đã dùng phép cộng.

Spring vẫn có thể tạo `PriceService` bình thường. Không thiếu dependency, không lỗi annotation và không exception khi khởi động.

Vì vậy:

```java
@SpringBootTest
class ShopApplicationTests {

    @Test
    void contextLoads() {
    }
}
```

vẫn có thể xanh.

Để phát hiện lỗi, cần **behavior test**:

```java
@Test
void calculatesTotalFromUnitPriceAndQuantity() {
    PriceService service = new PriceService();

    BigDecimal total = service.total(
            new BigDecimal("12.50"),
            2
    );

    assertThat(total)
            .isEqualByComparingTo("25.00");
}
```

Test này sẽ thất bại nếu service dùng phép cộng thay vì phép nhân.

### 2.1. Bảng phân biệt

| Câu hỏi | Context smoke test | Kiểm thử hành vi |
|---|---|---|
| Spring context có thể khởi tạo? | Mục tiêu chính | Không nhất thiết |
| Bean dependency có resolve? | Có thể phát hiện lỗi wiring | Chỉ khi test có sử dụng wiring thật |
| Công thức tính tiền đúng? | Không | Có, nếu có assertions phù hợp |
| Validation từ chối quantity âm? | Không | Có |
| API trả HTTP 201 đúng contract? | Không | Có trong web test |
| Repository truy vấn đúng dữ liệu? | Không đủ | Có trong repository/integration test |
| Security chặn user không đủ quyền? | Không | Có trong security/HTTP tests |
| Tích hợp external system thật hoạt động? | Không chắc chắn | Có nếu integration test thực sự kết nối |
| Ứng dụng đã đạt chất lượng production? | Không | Một vài behavior tests cũng chưa đủ |

**Điểm quan trọng:** Một bộ test có thể chứa cả smoke test và behavior tests. Không cần loại bỏ `contextLoads()`, nhưng không được dùng nó thay thế kiểm thử nghiệp vụ.

## 3. Một test chứng minh điều gì?

Trước khi viết code test, hãy phát biểu mục tiêu kiểm tra bằng một câu cụ thể.

Ví dụ:

**Mục tiêu A:**

> Với profile `test`, ứng dụng tạo được Spring ApplicationContext mà không có lỗi bean wiring.

Đây là mục tiêu của context smoke test.

**Mục tiêu B:**

> Khi người dùng đặt mua 2 sản phẩm giá 12.50, tổng tiền phải là 25.00.

Đây là behavior test về business rule.

**Mục tiêu C:**

> Khi client gửi POST `/purchases` hợp lệ, API trả HTTP 201 cùng JSON receipt.

Đây là HTTP contract test.

**Mục tiêu D:**

> Khi lưu một bản ghi Purchase vào database kiểm thử và đọc lại, giá trị được bảo toàn.

Đây là persistence integration test.

Một test tốt có **input**, **hành động** và **kết quả mong đợi** rõ ràng, trừ những smoke tests mà mục tiêu chính là thao tác bootstrap không ném exception.

## 4. Các lớp kiểm thử trong ứng dụng Spring Boot

Có thể chia bộ test thành những nhóm thực dụng:

| Loại test | Spring context? | Dependency bên ngoài? | Mục tiêu |
|---|---|---|---|
| Unit test Java thuần | Không cần | Thường mock/fake | Kiểm tra thuật toán, rule, xử lý lỗi |
| Context smoke test | Có | Tùy cấu hình | Kiểm tra bootstrap và bean wiring |
| Spring test slice | Context giới hạn | Thường được thay thế/test setup | Kiểm tra một lớp như MVC/JPA |
| Full-context integration test | Có | Real hoặc test double | Kiểm tra nhiều bean phối hợp |
| End-to-end/API integration test | Thường có server thật | Có thể có test dependencies | Kiểm tra HTTP/persistence qua boundary |
| System/E2E test đa dịch vụ | Nhiều process/hệ thống | Thường có | Kiểm tra luồng người dùng xuyên các hệ |

Đây không phải các nhãn chuẩn hóa bắt buộc cho mọi dự án. Quan trọng hơn tên gọi là phạm vi thực tế của test, dependencies nào là thật, và assertions đang kiểm tra hành vi gì.

### 4.1. Có thể có nhiều test dùng @SpringBootTest nhưng mục đích khác nhau

Hai lớp sau đều dùng `@SpringBootTest`:

```java
@SpringBootTest
class ContextSmokeTest {

    @Test
    void contextLoads() {
    }
}
```

```java
@SpringBootTest
class CheckoutIntegrationTest {

    @Autowired
    CheckoutService checkoutService;

    @Test
    void rejectsInvalidQuantity() {
        assertThatThrownBy(
                () -> checkoutService.checkout("SKU-1", 0)
        ).isInstanceOf(IllegalArgumentException.class);
    }
}
```

Test đầu chỉ kiểm tra context. Test thứ hai thực hiện một hành vi rồi khẳng định kết quả, dù nó cũng dùng full Spring context.

Vì vậy, **annotation không tự quyết định giá trị của test**. Giá trị của test phụ thuộc vào điều gì được thực thi và khẳng định.

## 5. @SpringBootTest làm gì?

`@SpringBootTest` là annotation tích hợp của Spring Boot Test để bootstrap một Spring application context dùng cho test.

Thông thường:

```java
import org.springframework.boot.test.context.SpringBootTest;
```

Ví dụ:

```java
@SpringBootTest
class ApplicationContextTest {

    @Test
    void contextLoads() {
    }
}
```

Spring Boot sẽ tìm cấu hình ứng dụng phù hợp, thường là class mang `@SpringBootConfiguration` hoặc `@SpringBootApplication` trong cấu trúc package phù hợp, rồi chuẩn bị context theo môi trường test.

### 5.1. Test context không hoàn toàn giống production process

Khác biệt có thể đến từ:

- Profiles khác nhau.
- System properties/environment variables khác nhau.
- Test-specific properties.
- Test doubles hoặc mock beans.
- Database nhúng hoặc container test thay cho production database.
- `@SpringBootTest` web environment.
- Classpath test chứa dependencies không có trong production.
- Security/test configuration.
- Các external integrations bị thay thế hoặc vô hiệu hóa.

Vì vậy, khi `contextLoads()` xanh, kết luận chính xác là:

> Context trong **điều kiện cấu hình của test này** đã được khởi tạo thành công.

Không phải:

> Mọi deployment production chắc chắn sẽ khởi động và hoạt động đúng.

### 5.2. Test class nằm đúng package

Giả sử main class:

```java
package com.example.shop;

@SpringBootApplication
public class ShopApplication {
}
```

Test class nên đặt trong package tương ứng hoặc con:

```java
package com.example.shop;

@SpringBootTest
class ShopApplicationTests {
}
```

Điều này thường giúp Spring Boot tìm được application configuration và sử dụng component scanning phù hợp.

Nếu test ở một package không liên quan, có thể cần khai báo:

```java
@SpringBootTest(classes = ShopApplication.class)
```

Đừng thêm một `@SpringBootApplication` mới vào test package chỉ để test chạy được nếu nó vô tình đổi phạm vi scan và làm test khác production.

## 6. @SpringBootTest và lựa chọn webEnvironment

`@SpringBootTest` cung cấp thuộc tính `webEnvironment`, trong đó các chế độ thông dụng gồm:

| Giá trị | Ý nghĩa |
|---|---|
| `MOCK` | Tạo web context/mock web environment phù hợp nếu có web stack, không khởi động embedded server thật |
| `RANDOM_PORT` | Khởi động web server trên cổng ngẫu nhiên |
| `DEFINED_PORT` | Khởi động web server trên cổng được cấu hình |
| `NONE` | Tạo context không phải web environment |

### 6.1. Mặc định MOCK không đồng nghĩa có server chạy thật

Ví dụ:

```java
@SpringBootTest
class ShopApplicationTests {
}
```

Mặc định `webEnvironment = MOCK`. Với web stack phù hợp, Spring có thể tạo mock web application context, nhưng không mở embedded server thật trên một network port.

Do đó, `contextLoads()` dạng này không xác nhận rằng một HTTP request qua TCP sẽ được xử lý đúng.

### 6.2. NONE dành cho kiểm thử không cần web

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
class BatchApplicationSmokeTest {

    @Test
    void contextLoads() {
    }
}
```

Phù hợp với batch/CLI application hoặc integration test không cần web server.

Tuy nhiên, nếu ứng dụng production là Servlet web app, lựa chọn `NONE` sẽ thay đổi loại context và có thể bỏ qua một số web-only auto-configuration. Đừng coi smoke test `NONE` là bằng chứng toàn bộ web infrastructure sẽ khởi động đúng.

### 6.3. RANDOM_PORT để kiểm thử giao tiếp HTTP thật

```java
@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ShopHttpIntegrationTest {
}
```

Chế độ này mở web server trên port được chọn tại runtime. Test có thể gửi HTTP request qua network interface phù hợp.

Nhưng **chỉ thêm `RANDOM_PORT` mà method test rỗng** vẫn chưa kiểm thử HTTP behavior. Bạn phải thực sự gửi request và khẳng định response.

### 6.4. Không lạm dụng DEFINED_PORT

`DEFINED_PORT` có thể đụng cổng với một process khác hoặc gây xung đột khi chạy test song song.

Thông thường `RANDOM_PORT` phù hợp hơn cho HTTP integration test tự động, vì mỗi test context có thể sử dụng cổng khả dụng.

## 7. Smoke test context nên viết thế nào?

Một smoke test ngắn, dễ hiểu:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ShopApplicationSmokeTest {

    @Test
    void contextLoads() {
        // Thành công khi ApplicationContext được khởi tạo.
    }
}
```

Không cần viết:

```java
assertThat(true).isTrue();
```

Dòng assertion đó không kiểm tra thêm điều gì có ý nghĩa.

### 7.1. Có nên assert context khác null?

Bạn có thể inject context:

```java
@SpringBootTest
class ShopApplicationSmokeTest {

    @Autowired
    ApplicationContext context;

    @Test
    void contextLoads() {
        assertThat(context).isNotNull();
    }
}
```

Test có assertion tường minh hơn, nhưng phần lớn giá trị vẫn nằm ở thao tác load context. Nếu context không tạo được, test thất bại trước khi assertion chạy.

Không cần biến smoke test thành hàng trăm dòng `getBean(...)` nếu mục tiêu chỉ là khả năng bootstrap.

### 7.2. Đừng làm smoke test phụ thuộc business output tình cờ

Nếu smoke test gọi một API nghiệp vụ, đọc database và kiểm tra business rule, nó không còn chỉ là smoke test. Không có gì sai với integration test, nhưng nên đặt tên và tổ chức rõ mục đích để người đọc hiểu nguyên nhân khi test thất bại.

## 8. Ví dụ có bug nhưng context vẫn load

Giả sử service:

```java
package com.example.shop.pricing;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;

@Service
public class PricingService {

    public BigDecimal calculateTotal(
            BigDecimal unitPrice,
            int quantity
    ) {
        // BUG: cần nhân, không phải cộng.
        return unitPrice.add(
                BigDecimal.valueOf(quantity)
        );
    }
}
```

Mọi dependency hợp lệ nên `contextLoads()` có thể xanh.

Nhưng test hành vi:

```java
package com.example.shop.pricing;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class PricingServiceTest {

    private final PricingService pricingService =
            new PricingService();

    @Test
    void calculatesTotal() {
        BigDecimal actual = pricingService.calculateTotal(
                new BigDecimal("12.50"),
                2
        );

        assertThat(actual)
                .isEqualByComparingTo("25.00");
    }
}
```

sẽ thất bại với implementation trên.

Sửa service:

```java
public BigDecimal calculateTotal(
        BigDecimal unitPrice,
        int quantity
) {
    return unitPrice.multiply(
            BigDecimal.valueOf(quantity)
    );
}
```

Khi đó behavior test xác nhận quy tắc cụ thể, không chỉ xác nhận một class đã được đăng ký vào context.

### 8.1. Vì sao test này không cần Spring?

`PricingService` là một object Java đơn giản không cần dependency injection, transaction hoặc web infrastructure để kiểm tra phép tính.

Do đó, tạo instance bằng `new` trong unit test nhanh và rõ ràng hơn việc khởi tạo cả `ApplicationContext`.

**Không phải mọi class có `@Service` đều bắt buộc test bằng `@SpringBootTest`.**

## 9. Unit test: đầu vào, kết quả và side effects

Một unit test có mục tiêu kiểm tra hành vi của đơn vị code nhỏ trong điều kiện kiểm soát được. Phần lớn trường hợp không cần Spring container.

Một cấu trúc dễ đọc:

1. **Arrange:** chuẩn bị dữ liệu và dependencies.
2. **Act:** gọi method cần kiểm tra.
3. **Assert:** kiểm tra kết quả và side effect.

Ví dụ:

```java
@Test
void rejectsNonPositiveQuantity() {
    PricingService pricingService = new PricingService();

    assertThatThrownBy(
            () -> pricingService.calculateTotal(
                    new BigDecimal("12.50"),
                    0
            )
    )
    .isInstanceOf(IllegalArgumentException.class);
}
```

Test này chỉ đúng nếu implementation thực sự có validation:

```java
public BigDecimal calculateTotal(
        BigDecimal unitPrice,
        int quantity
) {
    if (quantity <= 0) {
        throw new IllegalArgumentException(
                "quantity must be positive"
        );
    }

    if (unitPrice.signum() < 0) {
        throw new IllegalArgumentException(
                "unitPrice must not be negative"
        );
    }

    return unitPrice.multiply(
            BigDecimal.valueOf(quantity)
    );
}
```

Điểm quan trọng là test phải kiểm tra **quy tắc được yêu cầu**. Đừng viết test khẳng định hành vi sai chỉ vì implementation hiện tại đang như vậy.

### 9.1. Các trường hợp nên thử

Với `calculateTotal`, ít nhất cần xem:

| Input | Mong đợi |
|---|---|
| unitPrice = 12.50, quantity = 2 | 25.00 |
| unitPrice = 0, quantity = 3 | 0 |
| quantity = 0 | Exception validation |
| quantity âm | Exception validation |
| unitPrice âm | Exception validation |
| unitPrice lớn, quantity lớn | Kết quả chính xác không tràn do dùng BigDecimal |
| số thập phân như 0.10 | Không mất độ chính xác vì dùng BigDecimal phù hợp |

Một context smoke test không thử bất kỳ trường hợp nào trong bảng này.

## 10. JUnit 5 và AssertJ trong Spring Boot test

Spring Boot thường dùng JUnit Jupiter và AssertJ thông qua `spring-boot-starter-test` ở test scope.

Gradle:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Các thư viện test được quản lý theo BOM/version của project tương ứng.

### 10.1. JUnit xác định phương thức test

```java
import org.junit.jupiter.api.Test;

@Test
void shouldCalculateTotal() {
    // ...
}
```

### 10.2. AssertJ khẳng định behavior

```java
import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
```

Ví dụ:

```java
assertThat(result).isEqualTo(expected);

assertThatThrownBy(() -> service.execute(invalidInput))
        .isInstanceOf(IllegalArgumentException.class);
```

Nếu dùng JUnit assertions:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
```

Cả hai phong cách đều được sử dụng. Hãy theo convention nhất quán của project.

### 10.3. Test nên có tên mô tả behavior

Tên như:

```java
void test1()
```

không nói rõ điều gì được kiểm tra.

Tốt hơn:

```java
void calculatesTotalForMultipleItems()
void rejectsZeroQuantity()
void doesNotPersistWhenPriceLookupFails()
```

Tên cụ thể giúp người đọc hiểu contract và giúp báo lỗi trong CI có ý nghĩa.

## 11. Behavior test với dependency: dùng Mockito

Đa số service không chỉ làm phép tính. Nó gọi repository, HTTP client hoặc các service khác.

Giả sử quy trình mua hàng gồm:

```text
CheckoutService
    │
    ├── ProductCatalog: lấy đơn giá
    │
    └── PurchaseRepository: ghi đơn hàng
```

Nếu unit test `CheckoutService`, bạn có thể thay các dependency bằng Mockito mocks để tập trung vào logic.

### 11.1. Khai báo hợp đồng

```java
package com.example.shop.checkout;

import java.math.BigDecimal;

public interface ProductCatalog {

    BigDecimal unitPrice(String sku);
}
```

```java
package com.example.shop.checkout;

import java.math.BigDecimal;

public interface PurchaseRepository {

    void save(
            String sku,
            int quantity,
            BigDecimal total
    );
}
```

Response kiểu record:

```java
package com.example.shop.checkout;

import java.math.BigDecimal;

public record CheckoutReceipt(
        String sku,
        int quantity,
        BigDecimal total
) {
}
```

Với project dùng Java 17 trở lên, record là lựa chọn gọn cho value object. Ở project Java cũ hơn, có thể dùng class thông thường.

### 11.2. Service thực thi rule

```java
package com.example.shop.checkout;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final ProductCatalog catalog;
    private final PurchaseRepository repository;

    public CheckoutService(
            ProductCatalog catalog,
            PurchaseRepository repository
    ) {
        this.catalog = catalog;
        this.repository = repository;
    }

    public CheckoutReceipt checkout(
            String sku,
            int quantity
    ) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException(
                    "sku must not be blank"
            );
        }

        if (quantity <= 0) {
            throw new IllegalArgumentException(
                    "quantity must be positive"
            );
        }

        BigDecimal price = catalog.unitPrice(sku);

        if (price == null || price.signum() < 0) {
            throw new IllegalStateException(
                    "invalid product price"
            );
        }

        BigDecimal total = price.multiply(
                BigDecimal.valueOf(quantity)
        );

        repository.save(sku, quantity, total);

        return new CheckoutReceipt(
                sku,
                quantity,
                total
        );
    }
}
```

Quy tắc cần kiểm tra:

- SKU không rỗng.
- Số lượng lớn hơn 0.
- Giá được tìm từ catalog.
- Không chấp nhận giá null/âm.
- Tổng tiền = giá × số lượng.
- Chỉ ghi repository khi dữ liệu hợp lệ.
- Receipt phản ánh dữ liệu đã xử lý.

Tạo được bean này mới chỉ là bước đầu; các quy tắc trên cần behavior tests.

## 12. Unit test CheckoutService bằng MockitoExtension

Unit test không cần Spring context:

```java
package com.example.shop.checkout;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.InjectMocks;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verify;

@ExtendWith(MockitoExtension.class)
class CheckoutServiceTest {

    @Mock
    ProductCatalog catalog;

    @Mock
    PurchaseRepository repository;

    @InjectMocks
    CheckoutService service;

    @Test
    void calculatesTotalAndPersistsPurchase() {
        given(catalog.unitPrice("SKU-1"))
                .willReturn(new BigDecimal("12.50"));

        CheckoutReceipt receipt =
                service.checkout("SKU-1", 2);

        assertThat(receipt.sku())
                .isEqualTo("SKU-1");

        assertThat(receipt.quantity())
                .isEqualTo(2);

        assertThat(receipt.total())
                .isEqualByComparingTo("25.00");

        verify(repository).save(
                "SKU-1",
                2,
                new BigDecimal("25.00")
        );
    }
}
```

Ở đây:

- Mockito tạo hai mock.
- `@InjectMocks` tạo và inject `CheckoutService`.
- `given(...).willReturn(...)` mô phỏng catalog.
- Assertion kiểm tra receipt.
- `verify(...)` kiểm tra side effect ghi repository.

**Không có `@SpringBootTest`**. Unit test nhanh vì không phải tải cả context.

### 12.1. Kiểm thử validation và không có side effect

```java
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.verifyNoInteractions;

@Test
void rejectsZeroQuantityBeforeCallingDependencies() {
    assertThatThrownBy(
            () -> service.checkout("SKU-1", 0)
    )
    .isInstanceOf(IllegalArgumentException.class)
    .hasMessageContaining("quantity");

    verifyNoInteractions(catalog, repository);
}
```

Đây là một behavior test có giá trị: nó xác nhận cả exception và việc không gọi dependency khi input không hợp lệ.

### 12.2. Test lỗi từ dependency

```java
import static org.mockito.BDDMockito.given;
import static org.mockito.Mockito.verifyNoInteractions;

@Test
void doesNotPersistWhenCatalogFails() {
    given(catalog.unitPrice("SKU-1"))
            .willThrow(new IllegalStateException(
                    "catalog unavailable"
            ));

    assertThatThrownBy(
            () -> service.checkout("SKU-1", 2)
    )
    .isInstanceOf(IllegalStateException.class)
    .hasMessageContaining("catalog unavailable");

    verifyNoInteractions(repository);
}
```

Test chứng minh service không lưu purchase nếu lookup giá thất bại. `contextLoads()` không thể tự phát hiện quy tắc side effect này.

### 12.3. Không verify mọi chi tiết nội bộ

Mocking hữu ích, nhưng lạm dụng verify từng method call có thể khiến test quá phụ thuộc implementation.

Ưu tiên:

1. Kết quả trả về.
2. Thay đổi trạng thái/side effect quan trọng.
3. Exception/error contract.
4. Những tương tác với dependency thật sự thuộc hợp đồng nghiệp vụ.

Không cần verify mọi getter hoặc internal helper chỉ vì có thể.

## 13. Khi nào behavior test nên dùng Spring context?

Không phải mọi hành vi đều kiểm tra tốt bằng Java thuần.

Có những hành vi do Spring container cung cấp:

- `@Transactional` và transaction propagation.
- Method security với Spring Security.
- Validation/binding dựa vào Spring.
- Serialization và HTTP conversion.
- Conditional configuration.
- Spring Data repositories.
- Caching/async/advice qua proxies.
- Configuration properties binding.
- Event dispatch và infrastructure.

Nếu behavior phụ thuộc hạ tầng này, một unit test chỉ gọi `new Service(...)` có thể không đủ.

Ví dụ:

```java
@Transactional
public void transfer(...) {
    // ...
}
```

Dùng `new TransferService(...)` không tạo transactional proxy của Spring. Test thuần Java vẫn có thể kiểm tra business arithmetic, nhưng không chứng minh transaction thật được mở, rollback đúng hay propagation hoạt động đúng.

### 13.1. Phân biệt business logic với framework behavior

| Cần kiểm tra | Loại test thường hợp lý |
|---|---|
| Công thức tính tổng | Unit test không Spring |
| Không lưu khi input sai | Unit test với mock/fake |
| `@Transactional` rollback trên lỗi | Integration test với Spring/database phù hợp |
| `@ConfigurationProperties` bind và validate | Spring context/configuration test |
| Controller trả JSON và status | MVC slice hoặc HTTP test |
| Security filter chặn request | Security/MVC integration test |
| Database unique constraint | Repository/database integration test |

Điều quan trọng không phải “luôn dùng test nhẹ nhất”, mà là **dùng mức thực thi đủ để chứng minh đúng behavior được yêu cầu**.

## 14. Full-context behavior test với @SpringBootTest

Bạn có thể load context và gọi service qua dependency injection:

```java
@SpringBootTest
class CheckoutServiceIntegrationTest {

    @Autowired
    CheckoutService checkoutService;

    @Test
    void rejectsBlankSku() {
        assertThatThrownBy(
                () -> checkoutService.checkout("", 1)
        )
        .isInstanceOf(IllegalArgumentException.class);
    }
}
```

Test này khẳng định behavior trong một Spring-managed bean. Nhưng nó sẽ chỉ khởi động nếu mọi dependency cần thiết của context được cung cấp.

### 14.1. Thay dependency bằng mock trong Spring context

Trong các dòng Spring Boot hỗ trợ Spring Framework 6.2+ (chẳng hạn Boot 3.4 trở lên), có thể dùng `@MockitoBean`:

```java
package com.example.shop.checkout;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

@SpringBootTest
class CheckoutServiceSpringTest {

    @Autowired
    CheckoutService checkoutService;

    @MockitoBean
    ProductCatalog catalog;

    @MockitoBean
    PurchaseRepository repository;

    @Test
    void calculatesTotalThroughSpringManagedService() {
        given(catalog.unitPrice("SKU-1"))
                .willReturn(new BigDecimal("12.50"));

        CheckoutReceipt receipt =
                checkoutService.checkout("SKU-1", 2);

        assertThat(receipt.total())
                .isEqualByComparingTo("25.00");
    }
}
```

Tại đây, Spring tạo context và inject các mock được đăng ký vào `CheckoutService`. Test vừa kiểm tra behavior vừa sử dụng Spring wiring.

**Lưu ý:** test không chứng minh `ProductCatalog` hoặc `PurchaseRepository` triển khai thật hoạt động, vì chúng đang bị thay bằng mock.

### 14.2. @MockBean và @MockitoBean theo phiên bản

Các project Spring Boot cũ có thể sử dụng:

```java
import org.springframework.boot.test.mock.mockito.MockBean;
```

Từ Spring Boot 3.4, `@MockBean` của Boot đã được đánh dấu deprecated theo hướng chuyển sang `@MockitoBean` từ Spring Framework. API và package có thể khác theo dòng phiên bản.

Đừng copy `@MockitoBean` vào project dùng framework/test libraries quá cũ mà không kiểm tra version. Tương tự, với project hiện đại nên theo cơ chế bean override đang được hỗ trợ của phiên bản thực tế.

### 14.3. Khi nào full context là quá nặng?

Nếu test chỉ cần tính `12.50 × 2`, full context tiêu tốn thêm thời gian bootstrap, dependencies và cơ hội lỗi ngoài phạm vi test.

Nên viết phần lớn behavior tests thuần Java nơi có thể, rồi bổ sung những integration tests thực sự cần Spring wiring hoặc infrastructure.

## 15. Test slice: kiểm tra một lớp mà không tải toàn bộ ứng dụng

Spring Boot cung cấp nhiều test annotations được thiết kế để load phần context liên quan.

Ví dụ:

- `@WebMvcTest`: tập trung vào Spring MVC layer.
- `@DataJpaTest`: tập trung vào JPA/persistence.
- `@JsonTest`: tập trung vào JSON serialization/deserialization.
- `@RestClientTest`: hỗ trợ một số use case kiểm thử HTTP client.

Test slice không có nghĩa “không dùng Spring”. Nó dùng một context hẹp hơn, phù hợp để kiểm tra một nhóm behavior.

### 15.1. Tại sao cần test slice?

Giả sử bạn chỉ muốn kiểm tra:

> POST `/purchases` trả HTTP 201 và JSON đúng.

Bạn không cần khởi động cả database, scheduler, message consumer hoặc tất cả integrations của ứng dụng chỉ để kiểm tra mapping và serialization.

`@WebMvcTest` có thể kiểm tra MVC behavior với các service dependency được mock.

## 16. @WebMvcTest: kiểm thử HTTP contract ở controller layer

Giả sử controller:

```java
package com.example.shop.checkout;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/purchases")
public class CheckoutController {

    private final CheckoutService service;

    public CheckoutController(CheckoutService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<CheckoutReceipt> checkout(
            @RequestBody CheckoutRequest request
    ) {
        CheckoutReceipt receipt = service.checkout(
                request.sku(),
                request.quantity()
        );

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(receipt);
    }

    public record CheckoutRequest(
            String sku,
            int quantity
    ) {
    }
}
```

Cần kiểm tra:

- Route `POST /purchases`.
- JSON request body được deserialize.
- Controller gọi service với dữ liệu phù hợp.
- Response có HTTP 201.
- JSON response chứa receipt.

### 16.1. Test với MockMvc

```java
package com.example.shop.checkout;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(CheckoutController.class)
class CheckoutControllerTest {

    @Autowired
    MockMvc mvc;

    @MockitoBean
    CheckoutService service;

    @Test
    void returnsCreatedReceipt() throws Exception {
        given(service.checkout("SKU-1", 2))
                .willReturn(new CheckoutReceipt(
                        "SKU-1",
                        2,
                        new BigDecimal("25.00")
                ));

        mvc.perform(
                post("/purchases")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content(
                                """
                                {"sku":"SKU-1","quantity":2}
                                """
                        )
        )
        .andExpect(status().isCreated())
        .andExpect(jsonPath("$.sku").value("SKU-1"))
        .andExpect(jsonPath("$.quantity").value(2))
        .andExpect(jsonPath("$.total").value(25.0));
    }
}
```

Ví dụ dùng Java text blocks (Java 15+, thường phù hợp project Boot 3 trở lên). Với Spring Boot cũ, `@MockBean` có thể được sử dụng theo version.

### 16.2. Test này kiểm tra điều gì?

Nó kiểm tra MVC mapping, request decoding, controller handling và JSON response của controller.

Nó **không** xác nhận:

- Công thức total bên trong `CheckoutService` đúng, vì service đã mock.
- Repository lưu dữ liệu.
- HTTP stack thật qua TCP.
- Database có thể kết nối.
- External integration hoạt động.

Đây là một **controller behavior test** có phạm vi giới hạn rõ ràng.

### 16.3. Chú ý Spring Security

Nếu ứng dụng dùng Spring Security, `@WebMvcTest` có thể áp dụng security filters. Request chưa được xác thực hoặc thiếu CSRF token có thể nhận 401/403 thay vì 201.

Không nên xóa security khỏi test chỉ để status thành công. Hãy cấu hình authentication/authorization test phù hợp với HTTP contract thật, hoặc giới hạn phạm vi test nếu bạn đang kiểm tra riêng MVC mapping mà không kiểm tra security.

## 17. HTTP test không đồng nghĩa kiểm thử nghiệp vụ đầy đủ

Bạn có thể viết một test:

```java
mvc.perform(get("/health"))
        .andExpect(status().isOk());
```

Điều này cho biết endpoint trả 200 trong test setup, nhưng không kiểm tra checkout/pricing business rules.

Ngược lại, một unit test tính tiền có thể đúng nhưng controller mapping vẫn sai.

Vì vậy có ít nhất ba lớp câu hỏi:

1. **Logic:** số tiền, quy tắc, validation có đúng?
2. **Web contract:** route, status, JSON, headers, authorization có đúng?
3. **Tích hợp:** HTTP request thật đi qua service/repository và external dependencies đúng không?

Một test duy nhất thường không cần chứng minh cả ba; **bộ test** nên có độ bao phủ phù hợp với rủi ro.

## 18. @DataJpaTest: kiểm thử persistence behavior

Giả sử cần lưu một đơn hàng bằng JPA.

Entity:

```java
package com.example.shop.persistence;

import java.math.BigDecimal;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "purchases")
public class PurchaseEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String sku;

    private int quantity;

    private BigDecimal total;

    protected PurchaseEntity() {
    }

    public PurchaseEntity(
            String sku,
            int quantity,
            BigDecimal total
    ) {
        this.sku = sku;
        this.quantity = quantity;
        this.total = total;
    }

    public Long getId() {
        return id;
    }

    public String getSku() {
        return sku;
    }

    public int getQuantity() {
        return quantity;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
```

Spring Data repository:

```java
package com.example.shop.persistence;

import org.springframework.data.jpa.repository.JpaRepository;

public interface PurchaseJpaRepository
        extends JpaRepository<PurchaseEntity, Long> {
}
```

### 18.1. Test persistence với test slice

```java
package com.example.shop.persistence;

import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

import static org.assertj.core.api.Assertions.assertThat;

@DataJpaTest
class PurchaseJpaRepositoryTest {

    @Autowired
    PurchaseJpaRepository repository;

    @Test
    void savesAndReadsPurchase() {
        PurchaseEntity saved = repository.saveAndFlush(
                new PurchaseEntity(
                        "SKU-1",
                        2,
                        new BigDecimal("25.00")
                )
        );

        PurchaseEntity loaded = repository.findById(
                saved.getId()
        ).orElseThrow();

        assertThat(loaded.getSku())
                .isEqualTo("SKU-1");

        assertThat(loaded.getQuantity())
                .isEqualTo(2);

        assertThat(loaded.getTotal())
                .isEqualByComparingTo("25.00");
    }
}
```

Test này có hành động và assertions trên dữ liệu persistence. Nó chứng minh nhiều hơn việc entity/repository bean chỉ được tạo ra.

### 18.2. Điều kiện của ví dụ

Để chạy test này trong project thực tế, bạn cần:

- Spring Data JPA starter và test dependencies.
- Một database test phù hợp, ví dụ H2 hoặc database qua Testcontainers.
- JPA entity được phát hiện đúng.
- Schema generation/migration tương ứng.
- Dòng Spring Boot/Jakarta imports phù hợp.

`@DataJpaTest` thường cấu hình JPA slice và transaction rollback cho mỗi test, nhưng chi tiết database replacement phụ thuộc setup. Không giả định môi trường production database đã được kiểm tra chỉ vì test chạy bằng H2 thành công.

### 18.3. @DataJpaTest không chứng minh production SQL tương thích

Một test với H2 có thể xanh nhưng query hoặc migration thất bại trên PostgreSQL/MySQL production.

Nếu ứng dụng dùng SQL dialect-specific behavior, JSONB, index/constraint đặc thù hoặc transaction isolation, hãy cân nhắc integration tests với database engine tương thích production.

## 19. Kiểm thử database thật bằng Testcontainers

Testcontainers giúp chạy những service như PostgreSQL, Redis hoặc message brokers trong containers phục vụ integration tests.

Mục tiêu là kiểm tra gần với runtime dependency thật hơn.

Ví dụ khái niệm với PostgreSQL:

```text
JUnit integration test
          │
          ▼
Spring Boot test context
          │
          ▼
DataSource configuration
          │
          ▼
Testcontainers PostgreSQL container
          │
          ▼
Real SQL/schema/transactions
```

Trong một test setup hiện đại, bạn có thể dùng Testcontainers cùng `@ServiceConnection` của Spring Boot test integration, hoặc `@DynamicPropertySource` để truyền JDBC URL, username và password vào Spring Environment.

### 19.1. Điều gì được kiểm tra thêm?

- Database driver/runtime connection.
- SQL dialect behavior.
- Constraints/schema/migrations.
- Transaction semantics trong phạm vi test.
- Repository queries.
- Serialization mapping với database types.

### 19.2. Điều gì vẫn chưa được kiểm tra?

Một container PostgreSQL cục bộ không đồng nghĩa đã kiểm tra:

- Network policy của production.
- Database credentials production.
- Quotas/tải production.
- Tình huống multi-region hoặc failover thật.
- Mọi dữ liệu và volume thực tế.

Testcontainers làm integration test đáng tin cậy hơn với dependencies tương thích, nhưng không biến nó thành bản sao hoàn chỉnh của production.

### 19.3. Giữ test cô lập

Khi dùng test database:

- Không kết nối nhầm tới production.
- Không dùng credentials production.
- Khởi tạo dữ liệu test rõ ràng.
- Dọn dữ liệu giữa tests bằng transaction rollback, cleanup hoặc isolated schema/container.
- Không để thứ tự chạy test làm thay đổi kết quả.

Một bài test xanh chỉ khi chạy đơn lẻ nhưng thất bại khi chạy cả suite là tín hiệu cần kiểm tra shared state.

## 20. End-to-end HTTP test với RANDOM_PORT

Để kiểm tra HTTP thực sự, dùng server test trên cổng ngẫu nhiên và một HTTP client.

Ví dụ:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.ResponseEntity;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
class ShopHttpTest {

    @Autowired
    TestRestTemplate rest;

    @Test
    void healthEndpointResponds() {
        ResponseEntity<String> response =
                rest.getForEntity("/actuator/health", String.class);

        assertThat(response.getStatusCode().is2xxSuccessful())
                .isTrue();
    }
}
```

Đây là ví dụ kiểm tra một HTTP endpoint, giả định `spring-boot-starter-actuator` đã có và `health` được expose đúng trong test.

**Lưu ý:** `TestRestTemplate` là utility của các dòng Spring Boot test nhất định; ở các dòng mới hoặc khi chọn client khác, hãy dùng HTTP test client được version của bạn hỗ trợ, chẳng hạn `RestTestClient` hoặc những test clients tương ứng. Ý tưởng cốt lõi vẫn là gửi request qua server thật và khẳng định response.

### 20.1. Test này vẫn là smoke ở mức HTTP

Một HTTP test chỉ gọi `/actuator/health` có giá trị kiểm tra route/server/health integration ở mức cơ bản. Nhưng nó chưa phải kiểm thử business workflow.

Muốn kiểm tra checkout end-to-end, hãy gửi POST `/purchases` rồi đọc lại dữ liệu hoặc kiểm tra side effect theo contract.

### 20.2. Chú ý vấn đề transaction trong random-port test

Với `RANDOM_PORT`, client test và HTTP request handler thường chạy ở thread khác nhau. Nếu dùng `@Transactional` trên test method, transaction ở test thread **không tự bao phủ** transaction của server request.

Vì vậy, không nên mặc định mong đợi dữ liệu do HTTP endpoint ghi sẽ rollback theo transaction của test. Hãy dùng dữ liệu riêng, cleanup rõ ràng hoặc database isolation phù hợp.

Đây là một khác biệt quan trọng giữa repository test rollback và HTTP integration test qua server thật.

## 21. Bài test có mock phụ thuộc vào loại mock nào?

Cần phân biệt một số khái niệm:

| Công cụ | Mục đích |
|---|---|
| Mockito `@Mock` | Tạo mock Java thuần, thường dùng trong unit test |
| Mockito `@InjectMocks` | Tạo/inject object đang được unit test |
| Spring `@MockitoBean` | Thay hoặc thêm mock bean trong Spring test context theo cơ chế được hỗ trợ |
| `@MockBean` cũ của Boot | Cơ chế mock bean ở các phiên bản cũ |
| Fake implementation | Implementation test có logic đơn giản, ví dụ in-memory repository |
| Real dependency | Database/HTTP service thực hoặc test container tương thích |

### 21.1. @Mock không tự thay bean trong ApplicationContext

Nếu bạn viết:

```java
@Mock
ProductCatalog catalog;
```

trong một test có `@SpringBootTest`, Mockito có thể tạo mock trong test class, nhưng Spring application context không mặc nhiên dùng mock đó làm bean dependency.

Với Spring TestContext, cần cơ chế bean override tương ứng, ví dụ `@MockitoBean` ở phiên bản hỗ trợ.

### 21.2. Mock được thiết lập sai vẫn có thể khiến test xanh giả

Giả sử test chỉ khẳng định:

```java
assertThat(checkoutService).isNotNull();
```

nhưng `ProductCatalog` và `PurchaseRepository` đều là mocks, test chỉ cho thấy Spring inject được service và mocks. Nó không nói gì về behavior hoặc real integrations.

Hãy viết assertions phản ánh rule hoặc contract mong muốn.

### 21.3. Khi nào nên dùng fake?

Một in-memory fake có thể phù hợp khi muốn kiểm tra state transitions mà không cần database thật.

Ví dụ:

```java
public class InMemoryPurchaseRepository
        implements PurchaseRepository {

    private final List<PurchaseRecord> records =
            new ArrayList<>();

    @Override
    public void save(
            String sku,
            int quantity,
            BigDecimal total
    ) {
        records.add(
                new PurchaseRecord(sku, quantity, total)
        );
    }

    public List<PurchaseRecord> records() {
        return List.copyOf(records);
    }
}
```

Giả định `PurchaseRecord` là record do test định nghĩa với ba trường tương ứng.

Fake có thể giúp test state dễ đọc hơn so với nhiều `verify(...)`, nhưng nó vẫn không chứng minh implementation SQL thật hoạt động.

## 22. Test data: ưu tiên dữ liệu rõ ràng, lặp lại được

Một test behavior tốt nên tự chuẩn bị input và expected output.

Ví dụ tốt:

```java
BigDecimal price = new BigDecimal("12.50");
int quantity = 2;
BigDecimal expectedTotal = new BigDecimal("25.00");
```

Ví dụ dễ gây bất ổn:

```java
BigDecimal price = catalog.getLatestPriceFromProduction();
```

Nếu test chạy dựa vào dữ liệu production thay đổi theo thời gian, nó có thể thất bại vì môi trường chứ không phải regression trong code.

### 22.1. Tránh phụ thuộc đồng hồ hệ thống nếu không cần

Một rule như “coupon hết hạn sau 7 ngày” cần test ở nhiều thời điểm.

Thay vì gọi trực tiếp:

```java
LocalDate.now()
```

ở mọi nơi, có thể inject `Clock`:

```java
public class CouponService {

    private final Clock clock;

    public CouponService(Clock clock) {
        this.clock = clock;
    }

    public boolean isExpired(LocalDate expiresOn) {
        return LocalDate.now(clock).isAfter(expiresOn);
    }
}
```

Unit test:

```java
Clock fixed = Clock.fixed(
        Instant.parse("2026-01-15T00:00:00Z"),
        ZoneOffset.UTC
);
```

Việc cố định thời gian làm test deterministic.

### 22.2. Không để test tạo dữ liệu phụ thuộc thứ tự

Không nên:

```text
Test A: tạo user 42
Test B: giả định user 42 đã tồn tại từ Test A
```

Khi chạy riêng Test B hoặc chạy song song, test có thể thất bại.

Mỗi test nên tự thiết lập dữ liệu hoặc dùng fixture có lifecycle rõ ràng.

## 23. @ActiveProfiles và properties trong test

Một context smoke test có thể phụ thuộc rất nhiều vào profile.

Ví dụ:

```java
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
class ShopApplicationSmokeTest {

    @Test
    void contextLoads() {
    }
}
```

Spring Boot có thể nạp file `application-test.yml` cùng những config sources phù hợp.

### 23.1. Dùng test-specific properties

```java
@SpringBootTest(properties = {
        "app.notifications.enabled=false",
        "app.catalog.timeout=1s"
})
class ShopApplicationSmokeTest {
}
```

Cách này giúp kiểm soát một số giá trị test.

Nhưng nếu bạn tắt mọi tích hợp quan trọng, context smoke test có thể bỏ qua đúng những configuration paths cần được kiểm tra trước production.

### 23.2. Có nên dùng H2 trong mọi test?

Không bắt buộc. H2 có thể phù hợp với test cần database nhúng nhanh, nhưng không thay thế mọi kiểm thử dialect và migration của production database.

Chọn test database theo mục tiêu:

- Unit test: không cần database.
- Repository slice: H2 hoặc engine tương thích tùy yêu cầu.
- SQL/dialect/transaction integration: database engine tương thích production.
- E2E: môi trường kiểm soát được nhưng gần với deploy thực tế hơn.

### 23.3. Không sử dụng production credentials trong test

Một bộ test chạy trên CI không nên có quyền ghi vào production database.

Hãy dùng credentials/test environments riêng và thiết kế guardrails để tránh việc một property trỏ nhầm tới hệ thống live.

## 24. Smoke test có thể bị “xanh giả” như thế nào?

Một context load thành công không bảo đảm mọi behavior được kiểm tra. Có những lý do khiến smoke test bỏ sót lỗi.

### 24.1. Bean chỉ được tạo lười

Nếu ứng dụng dùng lazy initialization:

```yaml
spring:
  main:
    lazy-initialization: true
```

một số bean có thể chưa được tạo khi context refresh hoàn tất. Một constructor lỗi hoặc initialization callback ở bean chưa được dùng có thể không xuất hiện trong `contextLoads()`.

Vì vậy, cách nói chính xác là context smoke test phát hiện lỗi của các bean thực sự được tạo theo bootstrap hiện tại, chứ không bảo đảm tất cả bean trong ứng dụng đã được thực thi.

### 24.2. Bean bị loại theo condition

Ví dụ:

```java
@ConditionalOnProperty(
        prefix = "app.payment",
        name = "enabled",
        havingValue = "true"
)
@Bean
PaymentGateway paymentGateway() {
    // ...
}
```

Nếu test profile có `app.payment.enabled=false`, configuration này có thể không được kích hoạt.

Context smoke test xanh không kiểm tra được cấu hình có điều kiện của chế độ production trong trường hợp nó không được bật.

### 24.3. Mock đã che mất lỗi của integration thật

Nếu test thay một DataSource/HTTP client bằng mock, context có thể tạo thành công dù cấu hình integration thật sai.

Mock không phải vấn đề; nó đúng với test được thiết kế để cô lập behavior. Vấn đề là **diễn giải quá phạm vi** kết quả của test đó.

### 24.4. Test không gọi method cần được proxy

Một `@Transactional` method có thể bị gọi nội bộ (self-invocation) khiến advice không áp dụng, nhưng context vẫn khởi tạo.

Để kiểm tra behavior transaction, cần một integration test gọi method theo đúng Spring proxy boundary rồi kiểm tra DB state/rollback.

### 24.5. Test chạy khác production

Các điểm khác nhau có thể gồm:

- JDK version.
- Classpath/test dependencies.
- OS environment.
- Active profiles.
- External config.
- Startup mode.
- Database engine.
- Network policy.
- Security credentials.

Smoke test giúp phát hiện lỗi trong môi trường thử, không thay cho deployment validation.

## 25. Smoke test có thể thất bại nhưng code nghiệp vụ vẫn đúng

Chiều ngược lại cũng quan trọng.

Giả sử unit tests của `PricingService` đều xanh, nhưng `contextLoads()` thất bại vì thiếu `EmailClient` bean.

Điều đó có nghĩa:

- Phép tính tiền có thể đúng theo những cases đã test.
- Nhưng ứng dụng không thể bootstrap trong test configuration hiện tại.

Hai tín hiệu khác nhau đều quan trọng.

### 25.1. Phân biệt lỗi startup và lỗi behavior

| Lỗi | Test dễ phát hiện |
|---|---|
| Không có bean `ProductCatalog` | Context smoke/integration |
| Có hai `PaymentGateway` candidates không rõ qualifier | Context smoke/integration |
| Công thức discount sai | Unit behavior |
| API dùng sai HTTP status | MVC/HTTP behavior |
| DB constraint không được áp dụng | DB integration |
| `@Transactional` không rollback | Spring/DB integration |
| Classpath runtime thiếu dependency khi đóng gói | Artifact/deployment smoke |
| Secret production sai | Deployment/environment validation |

Không nên xóa smoke test chỉ vì unit tests xanh; cũng không nên bỏ unit tests chỉ vì smoke test xanh.

## 26. Context caching và tốc độ bộ test

Spring TestContext Framework có cơ chế cache `ApplicationContext` giữa các test classes khi configuration phù hợp.

Điều này giúp các test cùng context configuration không phải bootstrap lại toàn bộ Spring mỗi lần.

Tuy nhiên, các yếu tố khác nhau có thể tạo context cache key khác nhau:

- Active profiles.
- Test properties.
- Mock bean overrides.
- Configuration classes.
- Web environment.
- Initializers và customizers.
- Dynamic properties/test setup.

### 26.1. Vì sao nhiều @SpringBootTest có thể chậm?

Nếu mỗi test class có một tổ hợp mock/property khác, Spring có thể phải tạo nhiều contexts.

Ví dụ:

```text
Test A -> context profile=test, mock Catalog
Test B -> context profile=test, mock Payment
Test C -> context profile=integration, real database
```

Ba context configurations khác nhau có thể không chia sẻ cache.

### 26.2. Không phải cứ dùng @DirtiesContext là tốt

`@DirtiesContext` yêu cầu Spring coi context bị thay đổi và có thể loại nó khỏi cache.

Có trường hợp thật sự cần, ví dụ test thay đổi trạng thái application context ở mức không thể reset an toàn. Nhưng lạm dụng `@DirtiesContext` khiến test suite chậm và che khuất vấn đề isolation.

Ưu tiên:

- Tránh sửa global application state.
- Reset database/test data đúng cách.
- Không thay đổi logger/config toàn cục mà không khôi phục.
- Dùng test doubles có lifecycle phù hợp.

### 26.3. Cân bằng tốc độ và độ tin cậy

Một cấu trúc thường hợp lý:

- Nhiều unit tests nhanh cho business rules.
- Một số slices cho controller/repository.
- Một tập integration tests có lựa chọn cho framework behavior.
- Một vài context smoke tests có mục đích.
- Một số E2E tests cho critical workflows.

Không cần một full context bootstrap cho mọi branch của business rule.

## 27. Kiểm thử exception và lỗi là behavior

Business behavior không chỉ gồm happy path.

Ví dụ, checkout có thể cần từ chối số lượng không hợp lệ:

```java
@Test
void rejectsNegativeQuantity() {
    assertThatThrownBy(
            () -> service.checkout("SKU-1", -1)
    )
    .isInstanceOf(IllegalArgumentException.class);
}
```

Nhưng còn có một yêu cầu khác:

> Khi checkout bị từ chối, repository không được ghi bản ghi.

```java
verifyNoInteractions(repository);
```

Hai assertions bảo vệ hai phần khác nhau của business contract.

### 27.1. Kiểm thử HTTP error mapping

Nếu service ném `IllegalArgumentException`, controller không tự động biến nó thành HTTP 400 trong mọi cấu hình.

Bạn có thể tạo handler:

```java
@RestControllerAdvice
public class CheckoutExceptionHandler {

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> badRequest(
            IllegalArgumentException ex
    ) {
        return ResponseEntity.badRequest().body(
                Map.of(
                        "code", "INVALID_PURCHASE",
                        "message", "Invalid purchase request"
                )
        );
    }
}
```

Sau đó viết MVC test xác nhận:

```java
.andExpect(status().isBadRequest())
.andExpect(jsonPath("$.code").value("INVALID_PURCHASE"));
```

Đây là hành vi HTTP contract mà `contextLoads()` không tự xác nhận.

### 27.2. Kiểm thử timeout và retry

Nếu ứng dụng cần retry khi remote service timeout:

- Xác nhận số lần retry đúng theo policy.
- Không retry lỗi không được phép retry.
- Không tạo side effect trùng lặp ngoài ý muốn.
- Giữ exception/cause phù hợp khi hết retry.
- Không chờ real timeout lâu trong unit test; dùng fake/mocks/clock hoặc test-specific configuration.

Các case này cần behavior tests có assertions, không chỉ startup smoke.

## 28. Kiểm thử transaction thực sự

Giả sử:

```java
@Service
public class TransferService {

    @Transactional
    public void transfer(...) {
        debit(...);
        credit(...);
    }
}
```

Business requirement:

> Nếu bước credit thất bại, debit trước đó phải rollback.

Để kiểm tra, bạn cần một test thực thi qua Spring-managed transactional boundary và database phù hợp:

1. Chuẩn bị trạng thái hai tài khoản.
2. Gọi `transfer` từ bên ngoài proxy.
3. Gây lỗi có chủ đích sau debit.
4. Kiểm tra số dư không thay đổi sau rollback.
5. Xác nhận exception như contract.

### 28.1. Vì sao unit test không đủ?

Unit test thuần Java có thể xác nhận method gọi debit rồi credit. Nó không chứng minh transaction manager đã bắt đầu transaction hoặc DB rollback.

### 28.2. Vì sao contextLoads không đủ?

Spring có thể tạo `TransferService` và transaction manager bình thường, nhưng method chưa được gọi lần nào. Self-invocation hoặc cấu hình propagation sai vẫn có thể khiến runtime behavior sai.

### 28.3. Đừng để transaction của test che lỗi

Trong một số integration tests, mặc định rollback của chính test có thể khiến dữ liệu trở lại trạng thái cũ, làm bạn tưởng rằng `@Transactional` của service rollback đúng.

Hãy thiết kế test sao cho kết quả đo thật sự phản ánh transaction của **service under test**, không chỉ cơ chế cleanup của test. Khi cần, tách transaction boundaries hoặc dùng các utility của Spring TestContext một cách có chủ đích.

## 29. Kiểm thử bảo mật cũng là hành vi nghiệp vụ và contract

Một API có thể tạo context thành công nhưng vô tình cho phép user thường truy cập endpoint admin.

Ví dụ:

```text
GET /admin/reports
```

Kết quả mong đợi:

- User chưa xác thực: bị từ chối theo security policy.
- User đã xác thực nhưng không có quyền: bị từ chối.
- User có quyền: truy cập thành công.

Những trường hợp này phải được test bằng một setup áp dụng security filters/method security phù hợp.

### 29.1. Context smoke không kiểm tra authorization matrix

Chỉ tạo được `SecurityFilterChain` bean không chứng minh tất cả request paths đã được bảo vệ đúng.

### 29.2. Đừng disable filters rồi kết luận security đúng

Trong test có mục tiêu kiểm tra security, việc tắt toàn bộ filters sẽ khiến test mất ý nghĩa.

Ngược lại, nếu chỉ muốn kiểm tra serialization của controller, một slice test có thể cấu hình security test setup riêng. Hãy ghi rõ phạm vi kiểm thử và tránh diễn giải quá rộng kết quả.

## 30. Kiểm thử configuration properties

Giả sử ứng dụng có:

```yaml
app:
  checkout:
    max-quantity: 20
    timeout: 3s
```

Record:

```java
@ConfigurationProperties(prefix = "app.checkout")
public record CheckoutProperties(
        int maxQuantity,
        Duration timeout
) {
}
```

Có ít nhất hai vấn đề khác nhau:

1. Spring bind config sang object đúng không?
2. Business code có sử dụng max quantity/timeout đúng không?

### 30.1. Context smoke có thể bắt lỗi binding

Nếu Spring thực sự tạo/bind `CheckoutProperties` và validation cần thiết được bật, smoke test có thể bắt lỗi property không hợp lệ.

Nhưng nếu bean không được đăng ký hoặc không được tạo trong test context, test không kiểm tra configuration đó.

### 30.2. Binding test và behavior test

Binding test:

```java
assertThat(properties.maxQuantity()).isEqualTo(20);
assertThat(properties.timeout()).isEqualTo(Duration.ofSeconds(3));
```

Business behavior test:

```java
assertThatThrownBy(
        () -> checkoutService.checkout("SKU-1", 21)
).isInstanceOf(IllegalArgumentException.class);
```

Một test xác nhận giá trị cấu hình; test kia xác nhận rule đang dùng giá trị đó để từ chối quantity vượt giới hạn.

Đây là hai hợp đồng khác nhau.

## 31. Dấu hiệu một bộ test đang quá phụ thuộc contextLoads

Một vài dấu hiệu:

- Project có nhiều service phức tạp nhưng chỉ có một test `contextLoads()`.
- CI xanh dù có thay đổi rõ ràng trong logic tính tiền/validation.
- Không có assertions về expected output.
- Không có tests cho failure paths.
- Không có HTTP tests dù public API là thành phần quan trọng.
- Không có repository tests dù SQL/transaction là rủi ro chính.
- Độ bao phủ chỉ đo số lớp được load, không đo behavior.
- Lỗi production xuất hiện ở những case có thể mô phỏng bằng unit test.

Nếu gặp các dấu hiệu này, không cần xóa smoke test. Hãy bổ sung các behavior tests theo rủi ro nghiệp vụ quan trọng nhất.

### 31.1. Coverage không tự động chứng minh chất lượng

Một test method gọi nhiều dòng code có thể tăng coverage mà không có assertions đủ mạnh.

Ví dụ:

```java
@Test
void checkoutSomething() {
    service.checkout("SKU-1", 2);
}
```

Test này có thể phát hiện exception không mong đợi, nhưng không xác nhận total, persistence hoặc side effects.

Tốt hơn:

```java
CheckoutReceipt receipt =
        service.checkout("SKU-1", 2);

assertThat(receipt.total())
        .isEqualByComparingTo("25.00");

verify(repository).save(
        "SKU-1",
        2,
        new BigDecimal("25.00")
);
```

Hãy ưu tiên độ mạnh của assertions và cases quan trọng hơn con số coverage đơn độc.

## 32. Tổ chức test theo package và mục tiêu

Một cấu trúc ví dụ:

```text
src/
├── main/
│   └── java/com/example/shop/
│       ├── ShopApplication.java
│       ├── checkout/
│       ├── pricing/
│       ├── persistence/
│       └── web/
└── test/
    └── java/com/example/shop/
        ├── ShopApplicationSmokeTest.java
        ├── pricing/
        │   └── PricingServiceTest.java
        ├── checkout/
        │   └── CheckoutServiceTest.java
        ├── web/
        │   └── CheckoutControllerTest.java
        └── persistence/
            └── PurchaseJpaRepositoryTest.java
```

Tên test cho biết phạm vi:

- `ShopApplicationSmokeTest`: kiểm tra bootstrap.
- `PricingServiceTest`: unit tests của rule tính giá.
- `CheckoutServiceTest`: unit tests của quy trình checkout.
- `CheckoutControllerTest`: MVC contract tests.
- `PurchaseJpaRepositoryTest`: persistence integration tests.

Bạn có thể tách integration tests sang source set/task riêng nếu project lớn hoặc có dependencies nặng. Nhưng đừng phức tạp hóa project nhỏ chỉ để có nhiều thư mục.

### 32.1. Có nên đặt tên *IT?

Một số project dùng suffix `IT` để đánh dấu integration tests; có project dùng `IntegrationTest` hoặc packages riêng.

Hãy làm theo build/test conventions của repository. Điều quan trọng là CI biết tests nào cần chạy trong quick checks và tests nào cần môi trường tích hợp.

## 33. Quy trình chọn đúng test cho một yêu cầu mới

Khi nhận yêu cầu:

> “Thêm tính năng áp dụng giảm giá 10% cho đơn hàng trên 1.000.000 đồng.”

Có thể thực hiện như sau.

### Bước 1 — Viết business contract

Ví dụ:

- Total 1.000.000: không giảm nếu điều kiện là “trên”.
- Total 1.000.001: giảm 10%.
- Total âm: từ chối nếu không hợp lệ.
- Rounding: theo chính sách tiền tệ.
- Discount không áp dụng hai lần.

### Bước 2 — Viết unit tests

Kiểm tra từng boundary và rule bằng một pure Java service.

### Bước 3 — Kiểm tra wiring nếu thêm bean/config mới

Context smoke test có thể phát hiện thiếu bean `DiscountPolicy` hoặc conflict injection.

### Bước 4 — Kiểm tra API contract nếu có endpoint mới

Dùng `@WebMvcTest` hoặc HTTP test để xác nhận input JSON, status, response schema và validation.

### Bước 5 — Kiểm tra persistence nếu có dữ liệu mới

Dùng repository integration test để xác nhận discount amount/total được lưu và đọc đúng.

### Bước 6 — Kiểm tra phối hợp quan trọng

Một integration test có thể xác nhận cả service, transaction và repository cùng hoạt động.

### Bước 7 — Đánh giá những rủi ro còn lại

Security, concurrency, idempotency, external services, performance và deployment không tự được kiểm tra bởi các tests ở trên.

Từng lớp test là một phần của bằng chứng, không phải một chứng nhận tuyệt đối.

## 34. Test pyramid: vì sao nên có nhiều unit tests?

Một cách tổ chức phổ biến là ưu tiên nhiều tests nhanh ở tầng dưới, ít tests nặng ở tầng trên:

```text
              /\
             /  \
            / E2E\
           /______\
          /        \
         /Integration\
        /____________\
       /              \
      /   Unit tests   \
     /__________________\
```

Diễn giải:

- **Unit:** nhanh, cô lập, dễ tạo nhiều cases và boundary.
- **Integration/slice:** kiểm tra giao tiếp giữa các thành phần hoặc framework behavior.
- **E2E:** kiểm tra luồng từ ngoài vào qua nhiều tầng, thường tốn thời gian và phụ thuộc môi trường nhiều hơn.

### 34.1. Context smoke nằm ở đâu?

Context smoke test không phải một tầng riêng của pyramid. Nó thường được xem là một loại integration smoke test: bootstrap framework/context và báo sớm nếu wiring/config có lỗi.

Nó có thể là một test rất hữu ích trong CI nhưng không thay thế những layers khác.

### 34.2. Không có tỷ lệ bắt buộc

Không có luật “70% unit, 20% integration, 10% E2E” bắt buộc cho mọi ứng dụng.

Một library chỉ tính toán có thể chủ yếu dùng unit tests. Một application phụ thuộc SQL/protocols có thể cần nhiều integration tests. Điều quan trọng là phân bổ theo rủi ro và chi phí bảo trì.

## 35. Test nào nên chạy ở mỗi giai đoạn CI?

Một pipeline có thể chia:

| Giai đoạn | Các kiểm tra thường gặp | Mục tiêu |
|---|---|---|
| Developer local | Unit tests, một số slices | Phản hồi nhanh |
| Pull request | Unit + slices + context smoke | Chặn regression và wiring failures |
| Integration stage | DB/container/API integration | Kiểm tra tương tác thật |
| Deployment smoke | Kiểm tra app khởi động/health/basic route | Xác nhận artifact và môi trường triển khai |
| Periodic E2E | Critical user journeys | Kiểm tra xuyên hệ thống |

Đây là ví dụ tổ chức, không phải pipeline bắt buộc.

### 35.1. Deployment smoke khác context smoke

**Context smoke trong test:**

```java
@SpringBootTest
void contextLoads() {
}
```

**Deployment smoke:**

```text
Deploy artifact
    │
    ▼
Process khởi động
    │
    ▼
Health/readiness endpoint OK
    │
    ▼
Thử một HTTP operation cơ bản
```

Deployment smoke kiểm tra artifact trong môi trường triển khai thực tế hơn; context smoke kiểm tra Spring context với test classpath/properties.

Cả hai đều hữu ích, nhưng kết luận khác nhau.

### 35.2. Health endpoint không phải business E2E test

`GET /actuator/health` trả UP không xác nhận khả năng đặt hàng, thanh toán hoặc cấp quyền đúng.

Một deployment smoke có thể thêm một safe synthetic operation phù hợp với hệ thống, nhưng không nên thực hiện giao dịch thật gây side effects trên production nếu chưa có thiết kế an toàn.

## 36. Test thất bại thì đọc lỗi thế nào?

Khi `contextLoads()` thất bại, stack trace có thể dài. Hãy tìm phần nguyên nhân gốc:

```text
Failed to load ApplicationContext
...
Caused by: UnsatisfiedDependencyException
...
Caused by: NoSuchBeanDefinitionException
```

Hoặc:

```text
BeanCreationException
ConfigurationPropertiesBindException
...
```

### 36.1. Hướng điều tra context failure

1. Đọc exception cause chain, không chỉ dòng `Failed to load ApplicationContext`.
2. Kiểm tra active profile và properties.
3. Xác nhận class `@SpringBootApplication` được phát hiện.
4. Kiểm tra component scanning và bean definitions.
5. Kiểm tra qualifiers/primary nếu có nhiều bean cùng type.
6. Kiểm tra external dependency có bị gọi ở startup không.
7. Kiểm tra test mocks và cấu hình bean override.
8. Kiểm tra dependency/version của test runtime.

### 36.2. Hướng điều tra behavior failure

Nếu test báo:

```text
Expected: 25.00
Actual: 14.50
```

hãy xem công thức, input và rounding rules. Không có lý do trực tiếp để điều tra component scanning.

Nếu test báo:

```text
Expected: HTTP 201
Actual: HTTP 403
```

hãy xem authentication/authorization/CSRF policy trong test setup trước khi sửa business service.

Nếu repository test fail vì unique constraint, xem schema/data/transaction behavior. Phân loại lỗi theo phạm vi giúp giải quyết đúng chỗ.

## 37. Những hiểu lầm phổ biến

### 37.1. “contextLoads() xanh nghĩa là API hoạt động”

Không. Test không gửi HTTP request hay assert response. Nó chỉ chứng minh context test load được.

### 37.2. “Có @SpringBootTest là integration test đủ sâu”

Không. `@SpringBootTest` chọn bootstrap/context; độ sâu còn phụ thuộc vào method test, dependencies thật/mock, assertions và web environment.

### 37.3. “Method rỗng thì test vô dụng”

Không. Việc tạo context là phép kiểm tra bootstrap có giá trị, nhất là khi thay dependencies hoặc configuration.

### 37.4. “Mọi service đều phải test bằng @SpringBootTest”

Không. Pure Java business logic nên được kiểm thử nhanh bằng unit tests khi có thể.

### 37.5. “Mock tất cả dependencies vẫn là test tích hợp thật”

Không. Mock giúp cô lập behavior và wiring nhưng không chứng minh implementation thật của các dependencies.

### 37.6. “@WebMvcTest kiểm tra database”

Không. MVC slice thường không load đầy đủ persistence infrastructure; database cần test riêng.

### 37.7. “@DataJpaTest chạy H2 xanh thì PostgreSQL production chắc đúng”

Không. SQL dialect, migration và transaction differences có thể cần test với engine tương thích production.

### 37.8. “HTTP 200 từ /health chứng minh business workflow đúng”

Không. Health báo trạng thái theo indicators được cấu hình, không kiểm tra mọi nghiệp vụ.

### 37.9. “Test method gọi service nhưng không assert vẫn đủ”

Nó có thể phát hiện exception không mong đợi, nhưng không chứng minh output/side effects đúng. Hãy thêm assertions cụ thể.

### 37.10. “Unit test có Mockito là không có giá trị”

Không. Mock-based unit tests rất có giá trị khi xác nhận business rules và tương tác quan trọng. Cần bổ sung integration tests tại những boundary có rủi ro, thay vì loại bỏ unit tests.

### 37.11. “Test transaction dùng @Transactional luôn kiểm tra rollback của service”

Không chắc chắn. Transaction của test có thể che behavior của service nếu không thiết kế ranh giới thích hợp.

### 37.12. “Một context smoke test chạy ở CI đảm bảo production startup”

Không. Production có profiles, secrets, infrastructure, classpath/runtime và deployment configuration có thể khác.

## 38. Checklist tư duy trước khi viết test

Không phải checklist QA nội dung bài học; đây là tập câu hỏi **định hướng lựa chọn chiến lược kiểm thử** cho một yêu cầu Spring Boot thực tế:

- Tôi đang kiểm tra bootstrap, business behavior, HTTP contract hay integration?
- Input và expected output cụ thể là gì?
- Có side effect nào cần assert không?
- Có lỗi/edge case quan trọng nào?
- Behavior có phụ thuộc Spring proxy, transaction hoặc serialization không?
- Có thể viết unit test thuần Java không?
- Có cần mock một dependency bên ngoài không?
- Nếu mock, tôi đang bỏ qua behavior integration nào?
- Nếu dùng `@SpringBootTest`, đã thật sự cần full context chưa?
- Nếu dùng `@WebMvcTest`, security filters có đúng phạm vi không?
- Nếu dùng database test, SQL engine có phản ánh rủi ro cần kiểm tra không?
- Test data có độc lập, deterministic và an toàn không?
- Test failure sẽ cho biết loại regression nào?
- Có bao nhiêu configuration variants/profiles quan trọng?
- Có test nào chỉ xanh vì không có assertion không?

Một bộ test đáng tin cậy hình thành từ việc trả lời các câu hỏi này, không phải từ số lượng annotation Spring được dùng.

## 39. Bài thực hành

### Bài 1 — Context smoke test đơn giản

Tạo Spring Boot application với `@SpringBootApplication` và một `@Service`. Viết `@SpringBootTest` có `contextLoads()` rỗng. Chạy test, sau đó cố tình tạo một constructor dependency không có bean để quan sát lỗi bootstrap.

### Bài 2 — Bug nghiệp vụ mà context không phát hiện

Tạo `PricingService` với phép tính sai `unitPrice + quantity`. Xác nhận context smoke vẫn có thể xanh, rồi viết unit test mong đợi `unitPrice × quantity` để bắt bug.

### Bài 3 — Validation behavior

Tạo quy tắc từ chối quantity nhỏ hơn hoặc bằng 0. Viết tests cho quantity = -1, 0, 1. Kiểm tra exception type và message phù hợp.

### Bài 4 — Mockito unit test

Tạo `CheckoutService` với `ProductCatalog` và `PurchaseRepository`. Mock catalog giá 12.50, gọi checkout 2 sản phẩm, assert total 25.00 và verify repository save.

### Bài 5 — Không được ghi repository khi input sai

Dùng Mockito `verifyNoInteractions` để xác nhận checkout quantity 0 không gọi catalog hoặc repository.

### Bài 6 — Full-context Spring behavior test

Dùng `@SpringBootTest` inject `CheckoutService`; thay integration bằng `@MockitoBean` hoặc API tương ứng version. Test một business rule và giải thích dependency thật nào chưa được kiểm tra.

### Bài 7 — MVC slice

Tạo `CheckoutController` nhận JSON và trả receipt. Viết `@WebMvcTest` với MockMvc, kiểm tra status 201 và JSON fields.

### Bài 8 — HTTP error contract

Tạo `@RestControllerAdvice` xử lý quantity sai thành HTTP 400. Viết MockMvc test xác nhận response code và error JSON.

### Bài 9 — Repository test

Tạo `PurchaseEntity`, `JpaRepository` và `@DataJpaTest`. Lưu purchase rồi đọc lại. Giải thích khác biệt giữa JPA behavior test và context smoke.

### Bài 10 — Testcontainers

Dùng Testcontainers với database engine của ứng dụng. So sánh test repository với H2, đặc biệt khi có SQL dialect-specific feature hoặc database constraints.

### Bài 11 — RANDOM_PORT HTTP test

Khởi động server bằng `@SpringBootTest(webEnvironment = RANDOM_PORT)`. Gửi request từ HTTP client test và khẳng định response. Giải thích vì sao test này khác MockMvc.

### Bài 12 — Profiles

Tạo hai profiles `test` và `prod` với một conditional bean. Chạy smoke test dưới `test` và giải thích phần production configuration chưa được kiểm tra.

### Bài 13 — Lazy initialization

Bật lazy initialization và thêm một bean có constructor ném exception khi được tạo. Quan sát trường hợp contextLoads có thể không kích hoạt constructor; sau đó viết test gọi bean để kiểm tra hành vi thật.

### Bài 14 — Transaction rollback

Tạo service có `@Transactional` với hai bước ghi dữ liệu. Gây lỗi ở bước thứ hai; viết integration test chứng minh rollback ở service boundary, tránh để cleanup transaction của test che kết quả.

### Bài 15 — Kiểm thử authorization

Tạo một endpoint chỉ dành cho role admin. Viết test cho anonymous user, user thường và admin. Không disable security filters trong test có mục tiêu kiểm tra security.

### Bài 16 — Test với Clock cố định

Tạo logic kiểm tra coupon expiration dùng `Clock`. Viết deterministic tests trước, đúng và sau ngày hết hạn.

### Bài 17 — Phân loại test failures

Tự tạo ba lỗi: thiếu bean, phép tính sai và HTTP 403 ngoài mong đợi. Xác định loại test nào báo lỗi và cách điều tra phù hợp.

### Bài 18 — Thiết kế test suite

Cho ứng dụng gồm pricing, checkout, PostgreSQL repository và REST API, thiết kế bộ test tối thiểu: unit tests, MVC slice, repository integration, context smoke và một critical end-to-end flow. Giải thích mục tiêu của từng test.

### Bài 19 — Đo tác động của context cache

Tạo nhiều `@SpringBootTest` cùng profile/properties rồi thay đổi một configuration. Quan sát thời gian bootstrap và ý nghĩa của context caching. Tránh lạm dụng `@DirtiesContext`.

### Bài 20 — Deployment smoke khác context smoke

Mô tả cách xác nhận artifact sau deploy bằng readiness/health và một synthetic API operation an toàn. So sánh bằng chứng của phép kiểm tra đó với `contextLoads()` chạy bằng test classpath.

## 40. Tài liệu tham khảo chính thức

- [Spring Boot Reference — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest`, web environments, mock web testing và integration tests.
- [Spring Boot Reference — Test Auto-configuration Annotations](https://docs.spring.io/spring-boot/reference/test-auto-configuration.html): các test slices như `@WebMvcTest` và `@DataJpaTest` theo phiên bản.
- [Spring Framework Reference — TestContext Framework](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html): Spring TestContext, context caching và lifecycle.
- [Spring Framework Reference — Bean Overrides in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html): cơ chế `@MockitoBean` và test bean overrides ở các phiên bản hỗ trợ.
- [Spring Framework Reference — MockMvc](https://docs.spring.io/spring-framework/reference/testing/spring-mvc-test-framework.html): kiểm thử controller layer không cần khởi động server HTTP thật.
- [JUnit 5 User Guide](https://junit.org/junit5/docs/current/user-guide/): `@Test`, assertions và cơ chế chạy tests.
- [Mockito Documentation](https://site.mockito.org/): mocks, stubbing và interaction verification.
- [Testcontainers Documentation](https://java.testcontainers.org/): integration tests với dependencies chạy trong containers.
- [Spring Boot Reference — Testcontainers Support](https://docs.spring.io/spring-boot/reference/testing/testcontainers.html): tích hợp Testcontainers vào Spring Boot tests.

**Điểm cốt lõi:** `contextLoads()` là một **smoke test cho Spring ApplicationContext**, giúp phát hiện lỗi cấu hình hoặc dependency wiring xảy ra trong quá trình bootstrap. Nó không tự gọi business methods, không assert output và không chứng minh HTTP/database/security behavior đúng. Để bảo vệ nghiệp vụ, cần tests có input và assertions cụ thể; để bảo vệ integration, cần tests thực thi đúng framework boundary và dependencies cần thiết. Hãy giữ smoke test như một tín hiệu nền tảng hữu ích, nhưng xây dựng niềm tin vào ứng dụng bằng bộ kiểm thử hành vi đa lớp, có phạm vi và kết quả mong đợi rõ ràng.
