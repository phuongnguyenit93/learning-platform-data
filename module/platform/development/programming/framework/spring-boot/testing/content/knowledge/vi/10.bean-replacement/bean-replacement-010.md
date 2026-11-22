# Ảnh hưởng của khai báo mock tới khóa cache ApplicationContext

## 1. Vấn đề thực tế: vì sao cùng một ứng dụng nhưng test phải nạp context nhiều lần?

Spring Boot sử dụng Spring TestContext Framework để tạo `ApplicationContext` phục vụ các bài kiểm thử tích hợp. Khởi động context có thể tốn thời gian: xử lý cấu hình, tạo bean, auto-configuration, tạo proxy, kết nối hạ tầng giả lập và thực hiện khởi tạo ban đầu.

Spring TestContext có **context cache**: sau khi tạo một context cho một tập cấu hình, framework lưu lại và có thể **tái sử dụng** ở các test class khác có cấu hình tương đương. Nhờ đó, nhiều lớp test không phải khởi động lại mọi bean. Tuy nhiên, một khác biệt nhỏ trong **khai báo bean được mock/spy** có thể tạo **khóa cache khác**, khiến Spring phải tạo thêm context.

Ví dụ hai lớp đều dùng `@SpringBootTest` và cùng cấu hình, nhưng:

~~~java
// Lớp A
@MockitoBean
PaymentGateway paymentGateway;

// Lớp B
@MockitoBean
PaymentGateway mockGateway;
~~~

Cả hai trường đều có kiểu `PaymentGateway`; nếu context chỉ có một bean cùng kiểu, chúng có thể trỏ đến cùng **bean đích về mặt nghiệp vụ**. Nhưng khi không có `@Qualifier` rõ ràng, **tên field** còn có thể đóng vai trò qualifier dự phòng. Spring đưa thông tin qualifier của bean override vào việc phân biệt cấu hình test. Vì vậy hai khai báo trên **có thể không dùng chung cache entry**, dù chỉ đổi tên biến.

Đây không phải lỗi của Mockito và cũng không có nghĩa code nghiệp vụ thay đổi. Nguyên nhân là **mô tả context test khác nhau**.

### Kết quả học tập cần nắm

- Giải thích đúng **khóa cache** của Spring TestContext và phần `contextCustomizers`.
- Phân biệt mock thuần Mockito với **mock thay thế bean trong Spring ApplicationContext**.
- Hiểu vì sao thêm/bớt/đổi tên field `@MockitoBean`, qualifier, bean name hoặc metadata override có thể làm tăng số context.
- Viết test Java 17 + JUnit Jupiter minh họa các test class dùng chung hoặc tách cache.
- Đo bằng log cache và tối ưu số cấu hình context **mà không làm mất ý nghĩa kiểm thử**.

## 2. Khóa cache ApplicationContext được tạo từ những gì?

Framework không đơn giản lấy **tên lớp test** làm key. Theo Spring TestContext, khóa xác định duy nhất một tổ hợp cấu hình, gồm các nhóm thông tin chính:

| Thành phần khóa | Nguồn thường gặp | Vì sao ảnh hưởng tái sử dụng? |
| --- | --- | --- |
| `locations` | `@ContextConfiguration(locations=...)` | Nguồn cấu hình khác thì không thể mặc nhiên dùng chung |
| `classes` | `@ContextConfiguration(classes=...)` và cơ chế tương đương | Lớp cấu hình khác có thể tạo tập bean khác |
| `contextInitializerClasses` | `ApplicationContextInitializer` | Khác bộ khởi tạo context |
| **`contextCustomizers`** | `ContextCustomizerFactory`; bean override và cơ chế test khác | Đây là thành phần liên quan trực tiếp đến khai báo mock/spy |
| `contextLoader` | `ContextLoader` đã chọn | Cách tải context khác |
| `parent` | `@ContextHierarchy` | Context cha khác |
| `activeProfiles` | `@ActiveProfiles` | Profile có thể đổi tập bean và property |
| `propertySourceDescriptors` / `propertySourceProperties` | `@TestPropertySource` | Property nguồn và inline value khác |
| `resourceBasePath` | `@WebAppConfiguration` | Thông số web context khác |

Spring Boot còn có các context customizer cho tính năng kiểm thử của Boot; `@DynamicPropertySource` cũng tham gia thông qua customizer. Do đó, chỉ nhìn mỗi `@SpringBootTest` trên hai lớp rồi kết luận chúng dùng chung context là **không đủ**.

Khái quát:

~~~text
Test class A                      Test class B
  |                                 |
  v                                 v
MergedContextConfiguration   MergedContextConfiguration
  |                                 |
  +-- classes/profiles/...          +-- classes/profiles/...
  +-- contextCustomizers           +-- contextCustomizers
  |                                 |
  v                                 v
     so sánh cấu hình làm khóa cache
             /              \
       key tương đương     key khác nhau
            |                  |
      reuse cached        load context mới
      ApplicationContext  (nếu chưa có entry)
~~~

**Điểm phân biệt:** Hai test có thể cùng kiểm tra một bean, dùng cùng `@ActiveProfiles("test")`, nhưng khác danh sách bean override. Khi đó khóa không còn tương đương. Ngược lại, hai tên lớp test khác nhau **vẫn có thể chia sẻ context** nếu toàn bộ cấu hình mang ý nghĩa đối với key là tương đương và entry còn trong cache.

## 3. Vì sao @MockitoBean ảnh hưởng khóa cache?

Từ Spring Framework 6.2, `@MockitoBean` và `@MockitoSpyBean` hỗ trợ thay bean trong test thông qua **bean overriding infrastructure** của Spring TestContext.

Khi xử lý test class, framework tìm khai báo override và tạo mô tả về bean cần thay/wrap:

1. **Kiểu bean** cần mock, ví dụ `PaymentGateway.class`.
2. **Định danh/qualifier** của bean, nếu có; nếu không có qualifier, **tên field có thể được dùng làm fallback qualifier**.
3. **Chiến lược override** và những thuộc tính cấu hình mock/spy liên quan.
4. **Phạm vi hierarchy**, khi có `@ContextHierarchy` hoặc chỉ định `contextName`.

Hạ tầng tạo `ContextCustomizer` tương ứng để thay bean trong quá trình xây dựng context. Tập customizer đó góp phần vào **cache key**. Nhờ thế, context dùng bean thật không bị nhận nhầm là context có mock.

### Các kiểu khác biệt thường tạo context khác

| Lớp test A | Lớp test B | Nhận xét |
| --- | --- | --- |
| Không mock bean nào | Có `@MockitoBean PaymentGateway` | Định nghĩa context khác: bean thật so với bean giả |
| Mock `PaymentGateway` | Mock `EmailGateway` | Tập bean override khác |
| Mock một bean | Mock hai bean | Tập override khác |
| Cùng kiểu, qualifier/field name khác | Cùng một bean đích về mặt thực tế | Fallback qualifier có thể khiến key khác |
| `@MockitoBean` | `@MockitoSpyBean` | Chiến lược replace so với wrap khác |
| Override bằng tên bean A | Override bằng tên bean B | Đối tượng override khác |
| Cùng mock nhưng `@ActiveProfiles` khác | Ví dụ `test` so với `ci` | Key khác do profile, độc lập mock |
| Cùng mock nhưng test properties khác | Ví dụ endpoint/config khác | Key có thể khác do property source/customizer |

Không nên khẳng định **mọi chỉnh sửa annotation bất kỳ đều chắc chắn tạo khóa mới**: kết quả phụ thuộc những thuộc tính được dùng để xác định cấu hình tương đương trong phiên bản và cơ chế override đang sử dụng. Hãy coi metadata override có ý nghĩa là phần của cấu hình, dùng log cache để kiểm chứng trường hợp cụ thể.

### Fallback qualifier: bẫy rất nhỏ

Với field:

~~~java
@MockitoBean
PaymentGateway gateway;
~~~

Spring suy luận kiểu bean từ kiểu field. Nếu có **nhiều candidate bean cùng kiểu**, có thể cần `@Qualifier` để chỉ rõ bean nào được thay. Nếu không có `@Qualifier`, tên field `gateway` có thể được dùng làm **qualifier dự phòng**. Tài liệu Spring nêu rõ rằng cả qualifier và tên field đều được xem xét để quyết định có cần context riêng hay không.

Vì vậy, khi nhiều test class muốn override **cùng một bean**, hãy đặt field name thống nhất hoặc chỉ định bean name/qualifier rõ ràng theo cách dùng chung. Điều này vừa giảm mơ hồ, vừa tránh những cache key khác nhau ngoài ý muốn.

## 4. Phân biệt ba phạm vi mock: Mockito, Spring TestContext và Spring Boot cũ

| Annotation/cách tạo mock | Đối tượng nhận mock | Tham gia cơ chế bean override trong cache key? |
| --- | --- | --- |
| `@Mock` + `MockitoExtension` | Field/tham số của **test class**; test tự truyền vào SUT | **Không**, nó không tự thay bean của Spring context |
| `Mockito.mock(Foo.class)` | Object Java do test tự tạo | **Không**, nếu không đăng ký bean override/context configuration |
| `@InjectMocks` | Tạo/chuẩn bị SUT thật rồi tiêm các mock Mockito | **Không** tự thay bean Spring |
| `@MockitoBean` | Bean trong `ApplicationContext` được tạo/thay bằng mock | **Có**, qua bean override/context customizer |
| `@MockitoSpyBean` | Bean trong context được wrap bằng spy | **Có**, thuộc cấu hình context |
| `@MockBean` của Spring Boot đời trước | Bean trong Spring context bị thay/đăng ký mock | **Có**, thông qua mock context customizer của Boot |

**Đừng nhầm:** nếu dùng `@Mock PaymentGateway gateway` trong một lớp `@SpringBootTest` thì field đó là mock trong test, nhưng bean `PaymentGateway` thật mà `@Autowired OrderService` đang sử dụng **không tự bị thay**. Muốn service bean thật nhận mock, hãy dùng cơ chế override bean phù hợp, hoặc làm unit test thuần Java với constructor injection.

### Phiên bản Spring rất quan trọng

- **Spring Framework 6.2+ / Spring Boot 3.4+**: có `org.springframework.test.context.bean.override.mockito.MockitoBean` và `MockitoSpyBean`. Các ví dụ chính trong bài chọn đường này.
- **Spring Boot 3.4/3.5**: `org.springframework.boot.test.mock.mockito.MockBean` và `SpyBean` đã bị **deprecated**, hướng tới API của Spring Framework.
- **Spring Boot 4.0**: các annotation `@MockBean`/`@SpyBean` cũ của Spring Boot đã bị **loại bỏ**; chuyển sang `@MockitoBean`/`@MockitoSpyBean`.
- **Spring Boot 3.3 trở về trước**: nhiều dự án dùng `@MockBean` vì API Spring Framework 6.2 chưa được áp dụng. Phải chọn đúng annotation theo dependency hiện có.

Không coi `@MockBean` và `@MockitoBean` là hai alias hoàn toàn tương đương: phạm vi annotation được hỗ trợ và một số hành vi override khác nhau. Cũng không nên trộn hai kiểu trong cùng suite rồi kỳ vọng khóa cache có cùng cấu trúc.

## 5. Ví dụ xuyên suốt: cùng bean nghiệp vụ, khác khai báo mock

Ta tạo một service tính tổng giá nhận dependency `PricingGateway`. Trong ứng dụng, dependency có thể gọi HTTP hoặc database; ở bộ test này, nó có một implementation giả rất đơn giản để test chạy độc lập.

Tệp nguồn:

~~~text
src/main/java/com/example/testing/PricingGateway.java
src/main/java/com/example/testing/PricingService.java
src/test/java/com/example/testing/PricingTestConfig.java
src/test/java/com/example/testing/SharedMockATest.java
src/test/java/com/example/testing/SharedMockBTest.java
src/test/java/com/example/testing/RenamedFieldMockTest.java
src/test/java/com/example/testing/NoOverrideTest.java
~~~

Mỗi class có tệp riêng; các lớp test dùng chung **`PricingTestConfig.class`**. Khi chạy cả nhóm trong một JVM, ta quan sát context instance và thống kê cache thay vì viết assertion phụ thuộc thứ tự class test.

### 5.1. Interface phụ thuộc

**`src/main/java/com/example/testing/PricingGateway.java`**

~~~java
package com.example.testing;

import java.math.BigDecimal;

public interface PricingGateway {
    BigDecimal unitPrice(String sku);
}
~~~

### 5.2. Service nghiệp vụ thật

**`src/main/java/com/example/testing/PricingService.java`**

~~~java
package com.example.testing;

import java.math.BigDecimal;
import java.util.Objects;

public final class PricingService {
    private final PricingGateway pricingGateway;

    public PricingService(PricingGateway pricingGateway) {
        this.pricingGateway =
                Objects.requireNonNull(pricingGateway, "pricingGateway");
    }

    public BigDecimal total(String sku, int quantity) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("SKU is required");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }

        BigDecimal unitPrice = Objects.requireNonNull(
                pricingGateway.unitPrice(sku),
                "Missing unit price"
        );
        return unitPrice.multiply(BigDecimal.valueOf(quantity));
    }
}
~~~

`PricingService` là **đối tượng thật**; logic validate đầu vào và nhân giá phải chạy như Java thật. Bean được thay bằng Mockito chỉ là `PricingGateway`.

### 5.3. Cấu hình Spring TestContext chung cho cả nhóm

**`src/test/java/com/example/testing/PricingTestConfig.java`**

~~~java
package com.example.testing;

import java.math.BigDecimal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class PricingTestConfig {

    @Bean
    PricingGateway pricingGateway() {
        return sku -> new BigDecimal("11.00");
    }

    @Bean
    PricingService pricingService(PricingGateway pricingGateway) {
        return new PricingService(pricingGateway);
    }
}
~~~

Với context **không override**, phương thức `pricingGateway.unitPrice(...)` trả `11.00` cho mọi SKU. Với context có `@MockitoBean`, bean `pricingGateway` được thay bằng mock, nên method thật của lambda không còn được dùng khi `PricingService` gọi dependency.

Tất cả lớp test bên dưới dùng `@SpringJUnitConfig(PricingTestConfig.class)`. Đây là tổ hợp `@ContextConfiguration` và `@ExtendWith(SpringExtension.class)` do Spring cung cấp. Nó tạo **Spring TestContext nhỏ**, đủ để minh họa khóa cache, không cần `@SpringBootTest` nạp toàn ứng dụng.

## 6. Hai lớp khai báo mock giống nhau: có thể dùng chung context

**`src/test/java/com/example/testing/SharedMockATest.java`**

~~~java
package com.example.testing;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringJUnitConfig(PricingTestConfig.class)
class SharedMockATest {
    @MockitoBean
    PricingGateway pricingGateway;

    @Autowired
    PricingService pricingService;

    @Autowired
    ApplicationContext context;

    @Test
    void total_whenMockProvidesPrice_returnsExpectedValue() {
        when(pricingGateway.unitPrice("A-1"))
                .thenReturn(new BigDecimal("4.50"));

        assertEquals(
                new BigDecimal("9.00"),
                pricingService.total("A-1", 2)
        );
        verify(pricingGateway).unitPrice("A-1");

        System.out.println(
                "SharedMockATest context@" + System.identityHashCode(context)
        );
    }
}
~~~

**`src/test/java/com/example/testing/SharedMockBTest.java`**

~~~java
package com.example.testing;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@SpringJUnitConfig(PricingTestConfig.class)
class SharedMockBTest {
    @MockitoBean
    PricingGateway pricingGateway;

    @Autowired
    PricingService pricingService;

    @Autowired
    ApplicationContext context;

    @Test
    void total_whenSecondTestStubsPrice_returnsItsOwnValue() {
        when(pricingGateway.unitPrice("B-2"))
                .thenReturn(new BigDecimal("3.00"));

        assertEquals(
                new BigDecimal("9.00"),
                pricingService.total("B-2", 3)
        );
        verify(pricingGateway).unitPrice("B-2");

        System.out.println(
                "SharedMockBTest context@" + System.identityHashCode(context)
        );
    }
}
~~~

Hai lớp giống nhau ở những thành phần liên quan đến cache key:

- Cùng `@SpringJUnitConfig(PricingTestConfig.class)`.
- Cùng **một override bean** kiểu `PricingGateway`.
- Cùng tên field `pricingGateway` và không thêm qualifier/override metadata khác.
- Không cấu hình profile, property source hoặc context customizer riêng.

**Kỳ vọng:** khi cùng chạy trong một JVM, không bị `@DirtiesContext`/eviction và không có khác biệt ngầm, Spring có thể lấy lại **cùng một ApplicationContext** từ cache cho cả A và B. Hai test vẫn dùng **stubbing khác nhau**: giá `4.50` ở A và `3.00` ở B. Stubbing được thiết lập lúc chạy method, **không phải** một thành phần của cache key.

`System.identityHashCode(context)` chỉ in **dấu hiệu tham khảo** về instance để đối chiếu hai lần chạy. Nó không phải định danh đảm bảo duy nhất về mặt toán học; log cache của Spring mới là bằng chứng phù hợp hơn. Giá trị hash phụ thuộc JVM, vì vậy **không có stdout số cụ thể cố định** để assert.

**Quan trọng:** một context cache được chia sẻ không có nghĩa các test được phép phụ thuộc stubbing từ lớp trước. Spring/Mockito có cơ chế quản lý reset mock theo vòng đời test; test cần tự stub cho điều kiện của mình và không phụ thuộc trạng thái bị bỏ lại từ test khác.

## 7. Chỉ đổi tên field mock: có thể sinh cache key mới

**`src/test/java/com/example/testing/RenamedFieldMockTest.java`**

~~~java
package com.example.testing;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.when;

@SpringJUnitConfig(PricingTestConfig.class)
class RenamedFieldMockTest {
    @MockitoBean
    PricingGateway anotherPricingGateway;

    @Autowired
    PricingService pricingService;

    @Autowired
    ApplicationContext context;

    @Test
    void total_whenMockFieldNameDiffers_stillUsesMock() {
        when(anotherPricingGateway.unitPrice("C-3"))
                .thenReturn(new BigDecimal("6.00"));

        assertEquals(
                new BigDecimal("12.00"),
                pricingService.total("C-3", 2)
        );

        System.out.println(
                "RenamedFieldMockTest context@"
                        + System.identityHashCode(context)
        );
    }
}
~~~

`PricingTestConfig` chỉ có **một bean `PricingGateway`**, nên bean cần override vẫn xác định được theo kiểu. Lớp này vẫn có thể chạy đúng nghiệp vụ, nhưng field `anotherPricingGateway` là **fallback qualifier khác** với `pricingGateway` trong A/B.

Spring lưu ý qualifier, kể cả field name, được sử dụng để quyết định có phải tạo context riêng khi mock/spy bean. Bởi vậy lớp này là ví dụ về **phân mảnh cache do khác khai báo**. Nếu project có nhiều bean cùng kiểu, đổi field name còn có thể thay **bean được chọn để override** hoặc khiến setup thất bại; lúc đó phải xác định rõ `@Qualifier` hay `name`.

Để loại bỏ khác biệt tên field ngoài ý muốn, có thể dùng tên field nhất quán như A/B, hoặc khai báo bean theo tên tường minh:

~~~java
@MockitoBean(name = "pricingGateway")
PricingGateway gateway;
~~~

Đoạn này là **field minh họa** trong test class đã tích hợp Spring TestContext, không phải chương trình độc lập. Khi chọn bean bằng tên, đừng coi một việc rename field ở test khác là thay đổi không đáng kể nếu nó vẫn còn qualifier/annotation khác đi kèm; đối chiếu toàn bộ mô tả override mới là cách chắc chắn.

## 8. Không khai báo override: một cấu hình context khác

**`src/test/java/com/example/testing/NoOverrideTest.java`**

~~~java
package com.example.testing;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringJUnitConfig(PricingTestConfig.class)
class NoOverrideTest {
    @Autowired
    PricingService pricingService;

    @Autowired
    ApplicationContext context;

    @Test
    void total_withoutMock_usesOriginalGatewayBean() {
        assertEquals(
                new BigDecimal("22.00"),
                pricingService.total("ANY-SKU", 2)
        );

        System.out.println(
                "NoOverrideTest context@" + System.identityHashCode(context)
        );
    }
}
~~~

Dù cùng cấu hình lớp `PricingTestConfig`, `NoOverrideTest` **không có** `@MockitoBean`; nó dùng bean `pricingGateway` thực của cấu hình test. Vì tập `contextCustomizers` về bean override khác, context của lớp này không được xem là giống context dùng một mock trong A/B.

Tình huống này cho thấy việc cache tách ra là **đúng đắn về ngữ nghĩa**: nếu nhầm hai context, test yêu cầu gọi bean thật có thể vô tình nhận mock và ngược lại.

### Tổng hợp mong đợi của ví dụ

| Lớp | Cấu hình override | Kết quả nghiệp vụ | Quan hệ cache mong đợi |
| --- | --- | --- | --- |
| `SharedMockATest` | `@MockitoBean PricingGateway pricingGateway` | `9.00` từ stub `4.50 × 2` | Cùng key với B |
| `SharedMockBTest` | Cùng khai báo field A | `9.00` từ stub `3.00 × 3` | Tái sử dụng context A khi đủ điều kiện |
| `RenamedFieldMockTest` | Cùng kiểu nhưng field `anotherPricingGateway` | `12.00` từ stub `6.00 × 2` | Có thể tạo key riêng do fallback qualifier |
| `NoOverrideTest` | Không khai báo mock | `22.00` từ bean thật `11.00 × 2` | Key khác với A/B/C |

Mục tiêu test nghiệp vụ là **các assertion giá tiền**. Mục tiêu khảo sát hiệu năng là **log cache và số context tạo lại**. Không được lấy quan hệ cache dự đoán làm assertion bắt buộc phụ thuộc thứ tự chạy test class, vì JUnit/Gradle không cam kết thứ tự lớp, context cache có thể bị evict hoặc chạy trên JVM khác.

## 9. Chạy ví dụ và kiểm tra cache hit/miss thực sự

### 9.1. Cấu hình dependencies

Ví dụ nhắm đến **Spring Boot 3.4/3.5, Spring Framework 6.2, Java 17+, JUnit Jupiter và Mockito**. Nếu dự án Spring Boot dùng Gradle Groovy DSL đã có plugin Spring Boot, repositories và dependency management tương thích, phần cấu hình có thể như sau:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
    testLogging {
        showStandardStreams = true
    }
}
~~~

Đây là **đoạn của `build.gradle`**, không phải một tệp build hoàn chỉnh. `spring-boot-starter-test` trong dòng Boot 3.4/3.5 mang thư viện JUnit Jupiter, Mockito, Spring Test. Bởi test dùng Spring Framework `@MockitoBean`, phải có dependency Spring Framework **6.2+** tương ứng; một dự án Spring Boot cũ hơn cần cập nhật trước khi copy mã.

### 9.2. Bật DEBUG cho cache

Spring hướng dẫn bật logger category **`org.springframework.test.context.cache`** ở mức `DEBUG`. Trong ứng dụng dùng Logback, có thể tạo tệp sau.

**`src/test/resources/logback-test.xml`:**

~~~xml
<configuration>
    <appender name="STDOUT" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%level %logger{36} - %msg%n</pattern>
        </encoder>
    </appender>

    <logger name="org.springframework.test.context.cache" level="DEBUG"/>

    <root level="INFO">
        <appender-ref ref="STDOUT"/>
    </root>
</configuration>
~~~

Tệp này thay đổi cấu hình logging của **bộ test đang chạy**, không làm thay đổi nội dung cache key. Nếu dự án có logging configuration khác, hãy tích hợp riêng category này thay vì ghi đè toàn bộ file logging hiện hữu.

Với Spring Boot test context thực, cũng thường có thể cấu hình mức log qua property tương ứng; với bài demo `@SpringJUnitConfig` nhỏ, `logback-test.xml` là đường đi rõ ràng khi Logback có trên test classpath.

### 9.3. Chạy các lớp trong cùng test task / JVM

~~~bash
./gradlew test \
  --tests "com.example.testing.SharedMockATest" \
  --tests "com.example.testing.SharedMockBTest" \
  --tests "com.example.testing.RenamedFieldMockTest" \
  --tests "com.example.testing.NoOverrideTest" \
  --rerun-tasks
~~~

Trên Windows PowerShell, viết một dòng:

~~~powershell
.\gradlew.bat test --tests "com.example.testing.SharedMockATest" --tests "com.example.testing.SharedMockBTest" --tests "com.example.testing.RenamedFieldMockTest" --tests "com.example.testing.NoOverrideTest" --rerun-tasks
~~~

Khi mọi assertion đúng, bốn lớp test đều PASS. Output có các dòng dạng `... context@<number>`; **con số phụ thuộc JVM** và không có chuỗi stdout xác định tuyệt đối. Hãy nhìn logger cache để thấy giá trị **hit**, **miss**, **size** và quan hệ với những context được tạo.

**Không đếm mỗi dòng DEBUG là một lần tải context.** Spring gọi cache ở nhiều thời điểm của vòng đời một test, vì vậy chỉ số hit có thể tăng nhiều lần ngay trong một lớp. Hãy xem *chênh lệch* thống kê và cấu hình tương ứng, không suy ra “N hit nghĩa là N lớp dùng chung”.

Một bài kiểm tra tối giản: chạy nhóm A+B rồi xem context được nạp và tái sử dụng trong cùng JVM; chạy thêm C hoặc D và so sánh số miss/size. Số liệu tuyệt đối còn phụ thuộc test khác chạy cùng task, cache đã có entry, eviction và cấu hình Gradle.

### 9.4. Những điều kiện để quan sát cache reuse

- Chạy các lớp trong **cùng JVM test worker**. Spring TestContext cache nằm trong biến `static`, **không chia sẻ qua tiến trình JVM khác**.
- Không bật `@DirtiesContext` nếu không thật sự làm bẩn context; annotation đó có thể loại entry khỏi cache.
- Không thay `@ActiveProfiles`, test properties, dynamic property hoặc lớp cấu hình giữa A và B khi muốn so sánh riêng mock.
- Tránh parallel forks/suite phân tách test ra nhiều process nếu mục tiêu là đo tái sử dụng.
- Cache có giới hạn và có thể loại những context ít được dùng gần đây (LRU); **mặc định tối đa 32 context**, có thể điều chỉnh qua `spring.test.context.cache.maxSize` khi cần.
- Nếu chỉ chạy một test class một mình hoặc chạy lại bằng JVM mới, việc không có hit chia sẻ giữa các class là hoàn toàn bình thường.

Chú ý: `--rerun-tasks` yêu cầu Gradle thực thi lại task thay vì trả kết quả từ build cache/up-to-date; nó **không** ép Spring dùng chung context. Cache Spring chỉ tồn tại trong **tiến trình test hiện tại**.

## 10. Khác biệt giữa khai báo mock và stubbing khi chạy test

Một nhầm lẫn phổ biến là nghĩ hai lớp test có stubbing khác nhau phải có cache key khác nhau:

~~~java
// Lớp A và B: cùng bean mock và cùng cấu hình context.

// Trong @Test của A:
when(pricingGateway.unitPrice("A-1"))
        .thenReturn(new BigDecimal("4.50"));

// Trong @Test của B:
when(pricingGateway.unitPrice("B-2"))
        .thenReturn(new BigDecimal("3.00"));
~~~

Hai lệnh `when(...).thenReturn(...)` diễn ra **sau khi context đã được chọn/tạo**, nên nội dung stub thông thường **không là một thành phần của cache key**.

Ngược lại, thêm annotation ở cấp lớp/field như `@MockitoBean` hoặc đổi target bean được override diễn ra khi framework chuẩn bị **cấu hình context**, nên có thể ảnh hưởng key.

Sự phân biệt này rất hữu ích:

| Khía cạnh | Khai báo bean override | Stubbing trong test method |
| --- | --- | --- |
| Thời điểm | Khi xây dựng metadata của test context | Khi `@Test` đang chuẩn bị chạy |
| Ví dụ | `@MockitoBean PricingGateway pricingGateway;` | `when(pricingGateway.unitPrice(...)).thenReturn(...)` |
| Tác động context | Có thể tạo context customizer/key khác | Không tự thêm bean override vào key |
| Trách nhiệm | Xác định bean thật được thay bằng mock | Điều khiển hành vi của mock ở một tình huống |
| Nguy cơ | Nhiều key → nhiều context startup | State của mock bị rò nếu quản lý reset sai |

Với Spring Framework tích hợp Mockito, mock có cơ chế reset theo lifecycle test và cấu hình `reset`. Không cố tình bật chế độ giữ state để “tận dụng cache”: làm vậy dễ khiến lớp test này phụ thuộc stubbing/interaction của lớp kia, dù chúng dùng chung một context.

### Chỉ thay cấu hình mock mà không thay source class?

Một thay đổi về target bean, qualifier hoặc kiểu mock/spy có thể làm đổi key. Một thay đổi **chỉ ở câu lệnh stub trong thân test** thì không thay mô tả bean override. Nếu test thật sự cần một tập bean khác, context khác là đúng; không nên cố ép hai cấu hình không tương đương dùng cùng context.

## 11. Các cách tối ưu context reuse mà vẫn giữ test đúng

### 11.1. Dùng thống nhất tên field mock

Nếu nhiều lớp đều muốn override `PaymentGateway`, hãy chọn một tên nhất quán như `paymentGateway`. Tránh lớp này gọi `gatewayMock`, lớp khác gọi `mockGateway` khi cùng một mục tiêu và không có lý do qualifier khác biệt. Đây là hướng dẫn được nêu rõ trong tài liệu `@MockitoBean`/`@MockitoSpyBean` của Spring.

### 11.2. Ghi rõ tên bean/qualifier khi cần

Nếu có nhiều bean cùng type, hãy chỉ rõ đích:

~~~java
@MockitoBean(name = "primaryPaymentGateway")
PaymentGateway paymentGateway;
~~~

Đây là **đoạn field minh họa**, cần bean cùng tên, lớp test được tích hợp Spring TestContext và import `@MockitoBean` đúng package. Khi override một bean bắt buộc phải tồn tại, cân nhắc:

~~~java
@MockitoBean(name = "primaryPaymentGateway", enforceOverride = true)
PaymentGateway paymentGateway;
~~~

`enforceOverride = true` đổi chiến lược từ **REPLACE_OR_CREATE** mặc định sang **REPLACE**, giúp test fail nếu bean mong đợi không có. Đây là kiểm tra tính đúng đắn của wiring, **không phải** một mẹo buộc context reuse. Với nhiều class muốn chia sẻ context, hãy thống nhất cả metadata override cần thiết (bao gồm chiến lược được chọn).

### 11.3. Dùng composed annotation cho bộ mock chung

Spring cho phép `@MockitoBean` ở mức **type** và có thể làm meta-annotation để chia sẻ một tập cấu hình mock:

~~~java
package com.example.testing;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import org.springframework.test.context.bean.override.mockito.MockitoBean;

@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@MockitoBean(types = PricingGateway.class)
public @interface UsesMockPricingGateway {
}
~~~

**Tệp minh họa `src/test/java/com/example/testing/UsesMockPricingGateway.java`.** Nó dùng type-level annotation để yêu cầu override `PricingGateway` cho test class gắn `@UsesMockPricingGateway`. Khi cần nhiều mock, có thể khai báo các annotation type-level lặp lại theo API hỗ trợ.

Một lớp test sử dụng:

~~~java
@SpringJUnitConfig(PricingTestConfig.class)
@UsesMockPricingGateway
class PricingByCommonAnnotationTest {
    @Autowired
    PricingGateway pricingGateway;

    @Autowired
    PricingService service;

    @Test
    void stillWorks() {
        when(pricingGateway.unitPrice("X"))
                .thenReturn(new BigDecimal("2.00"));
        assertEquals(new BigDecimal("4.00"), service.total("X", 2));
    }
}
~~~

Đây là **đoạn lớp minh họa**, cần package `com.example.testing`, imports JUnit/Spring/Mockito/BigDecimal thích hợp. `@Autowired` lấy bean đã được override nên test có thể stub nó; **không cần** khai báo thêm `@MockitoBean` tại field và tránh ghi thêm một override riêng nếu không có ý định. Meta-annotation giúp chuẩn hóa cấu hình giữa các lớp, nhưng không thể khiến context khác profile/properties trở thành chung một key.

### 11.4. Đừng mock nhiều bean hơn cần thiết

Một số suite dùng mẫu “tất cả dependency đều `@MockitoBean`” trong hàng chục lớp `@SpringBootTest`. Nếu mỗi lớp chọn một tập mock khác nhau, số **biến thể context** tăng mạnh. Thay vì thế, hãy phân loại:

- Với **unit test business logic**: tạo service thật qua constructor và mock dependency bằng Mockito `@Mock`, không khởi động Spring context.
- Với **web slice test**: dùng cấu hình slice thích hợp (ví dụ `@WebMvcTest` trong Spring Boot 3.x) và chỉ mock những bean boundary cần thiết.
- Với **integration test**: ưu tiên bean thật khi mục tiêu là kiểm tra wiring/integration; chỉ thay những boundary không thể hoặc không nên gọi thật.
- Với các test integration cùng nhu cầu: dùng chung cấu hình và tập override có chủ đích.

Một slice test và một full `@SpringBootTest` thường có context khác nhau là **đúng**; không nên cố gộp chỉ để đẹp số hit.

### 11.5. Không lạm dụng @DirtiesContext

`@DirtiesContext` báo Spring rằng context hiện tại không an toàn để tái sử dụng. Nó làm cache loại context và lần test sau có thể phải tải mới. Hãy dùng khi test thật sự sửa bean definition/global state làm context không còn an toàn, **không dùng như cách thường quy để dọn Mockito stubbing**.

### 11.6. Giữ ổn định profile, properties và JVM

Thống nhất `@ActiveProfiles`, cấu hình test, `@DynamicPropertySource` và context hierarchy nếu các lớp cần cùng môi trường. Đảm bảo runner/Gradle không vô tình tách các lớp sang nhiều JVM, vì cache static không thể xuyên process.

Nếu suite có quá nhiều biến thể hợp lệ, điều chỉnh `spring.test.context.cache.maxSize` sau khi **đã đo** có thể giảm eviction, nhưng đồng thời tăng memory sử dụng. **Tăng cache size không giải quyết các key khác nhau không cần thiết.**

## 12. Phân biệt @MockitoBean và @MockitoSpyBean khi bàn về cache

`@MockitoBean` dùng chiến lược override **REPLACE_OR_CREATE** theo mặc định: có thể thay bean tồn tại hoặc tạo bean mới nếu chưa có. `enforceOverride = true` chuyển sang **REPLACE**, yêu cầu đã có bean phù hợp.

`@MockitoSpyBean` dùng chiến lược **WRAP**: nó yêu cầu một bean phù hợp đã tồn tại và bọc bằng Mockito spy. Đây là cách chạy một phần code thật và có thể can thiệp/quan sát method, nhưng kết quả khác với việc thay toàn bộ bean bằng mock. Hai loại không có một “cấu hình override giống hệt” để tái sử dụng bừa bãi.

Với spy, `when(spy.method())` có thể gọi **method thật ngay khi stubbing**. Nếu method có side effect hoặc cần dữ liệu chưa chuẩn bị, cân nhắc `doReturn(...).when(spy).method()` theo hướng dẫn Mockito/Spring.

Trong môi trường có `@Transactional`, `@Cacheable` hoặc AOP proxy, cách thay bean so với wrap spy còn tác động đến hành vi proxy. Vì thế một sự khác biệt `@MockitoBean`/`@MockitoSpyBean` không chỉ là vấn đề hiệu năng cache mà còn là vấn đề **tính đúng của test**.

## 13. Bối cảnh cache mở rộng: hierarchy, dynamic properties và cạnh tranh

### Context hierarchy

Một project có `@ContextHierarchy` có thể dùng context cha/con. Theo mặc định, khai báo `@MockitoBean`/`@MockitoSpyBean` có thể được áp dụng tới các mức hierarchy. Nếu chỉ muốn override tại một mức, dùng thuộc tính `contextName` khớp với tên của cấu hình hierarchy:

~~~java
@MockitoBean(contextName = "web-config")
PaymentGateway paymentGateway;
~~~

Đây là **đoạn minh họa**, chỉ hợp lệ khi thực sự có `@ContextConfiguration(name = "web-config", ...)` tương ứng. Sai phạm vi hierarchy có thể gây nhiều override ngoài dự định, lỗi context hoặc thay đổi cache key ở nhiều mức.

### DynamicPropertySource

`@DynamicPropertySource` tham gia thông qua context customizer, nên thay đổi method khai báo hoặc cấu hình test nguồn động có thể ảnh hưởng key. Đừng tự cho rằng hai test dùng cùng chữ ký URL nhưng container đang chạy ở cổng khác vẫn an toàn để chia sẻ context. Nếu property động thay đổi giữa các lớp dùng chung base class, đôi khi `@DirtiesContext` là cần thiết để tránh dùng lại bean đã nhận property cũ.

### Song song và giới hạn cache

Cache của Spring là phạm vi một JVM; khi chạy parallel, framework có cơ chế đồng bộ quản lý cache, nhưng **application state và Mockito stubbing** vẫn cần được cô lập theo test. Nhiều test cùng thao tác trên mock/bean trong một cached context có thể gây xung đột nếu chạy song song thiếu kiểm soát.

Khi tìm nguyên nhân suite chậm, đừng chỉ nhìn số lớp: cache **miss**, số lần startup context, eviction, parallel forks và cách reset/đồng bộ state đều có thể ảnh hưởng.

## 14. Những lỗi dễ gặp khi chẩn đoán

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| Hai class dùng cùng `@SpringBootTest` nhưng vẫn load context khác | Khác tập `@MockitoBean`/`@MockBean`, field name, qualifier, profiles hoặc properties | So sánh đầy đủ merged context configuration/customizers |
| Đổi tên field mock làm tăng số context | Fallback qualifier tham gia phân biệt key | Giữ tên field thống nhất hoặc chỉ rõ bean name |
| Thêm `@Mock` rồi tưởng nó thay Spring bean | Mockito mock chỉ nằm trong test | Dùng `@MockitoBean` khi muốn override trong context |
| Mock thiếu nhưng test vẫn khởi động | `@MockitoBean` có thể REPLACE_OR_CREATE | Dùng `enforceOverride = true` nếu bean phải tồn tại |
| Test B phụ thuộc stub của A khi chia sẻ context | Giả định stubbing sống qua test/lỗi reset | Stub độc lập từng test, dùng reset đúng lifecycle |
| Cache DEBUG báo nhiều hit dù một class | Spring tra cache nhiều lần trong lifecycle | Đọc số liệu tổng hợp, không quy hit thành số class |
| Không thấy reuse sau khi chạy bốn class | Gradle dùng nhiều JVM/fork, eviction hoặc `@DirtiesContext` | Chạy cùng test worker/JVM và xét log cache |
| Bộ suite có rất nhiều context | Quá nhiều biến thể mock/profile/property | Chuẩn hóa cấu hình, giảm override khác biệt không cần thiết |
| Context cứ bị tạo lại khi chạy mỗi class riêng | Mỗi lần gọi test chạy JVM mới | Chạy cùng suite/process để quan sát cache |
| Test giả lập thành công nhưng integration thật lỗi | Quá nhiều mock thay bean thật hoặc mất AOP behavior | Phân tầng test, giữ integration test với bean thật |
| Lỗi khi đặt `@MockitoBean` trong lớp cấu hình `@Configuration` | Annotation Spring Framework không áp dụng như `@MockBean` cũ | Đặt trên test class/field được hỗ trợ hoặc dùng composed annotation |
| Đã tăng cache maxSize nhưng startup vẫn nhiều | Key khác nhau chứ không phải eviction | Sửa các khác biệt key thừa trước khi tăng memory |

## 15. Checklist cải thiện tốc độ test một cách có thể đo lường

Trước khi chỉnh hàng chục lớp test, thực hiện:

1. **Chọn phép đo chuẩn:** chạy một nhóm lớp thật trong cùng JVM, ghi nhận thời gian, số cache miss và cache size.
2. **Bật đúng log:** `org.springframework.test.context.cache=DEBUG`; phân biệt hit/miss với startup output.
3. **So sánh key:** classes, profiles, test properties, dynamic properties, context customizers và hierarchy.
4. **So sánh override:** số bean được mock, bean target, qualifier, tên field và kiểu mock/spy.
5. **Ưu tiên tính đúng:** không cố dùng chung context nếu test cần bean/property khác.
6. **Chuẩn hóa phần giống nhau:** tên field, explicit bean name khi cần, composed annotation/base class cho tập mock chung.
7. **Tách unit test thuần Java:** tránh dùng Spring context cho các logic không cần DI/container.
8. **Loại kích hoạt reload thừa:** xem lại `@DirtiesContext` và các thay đổi state không cần thiết.
9. **Kiểm soát runtime:** JVM forks, cache LRU, parallel test và memory.
10. **Chạy lại toàn bộ suite:** xác nhận assertion vẫn đúng, không có rò state/stubbing giữa các test.

Một checklist nhanh cho code review:

- [ ] Có lý do rõ ràng để thay bean bằng mock trong Spring context, thay vì dùng Mockito unit test thuần?
- [ ] Các lớp test cùng mục tiêu dùng nhất quán kiểu bean, field name, bean name và qualifier?
- [ ] Khi bean phải tồn tại, đã cân nhắc `@MockitoBean(enforceOverride = true)`?
- [ ] Khác profile, test properties, context hierarchy có chủ đích?
- [ ] Trạng thái Mockito được thiết lập cho từng test; không kỳ vọng stub từ test trước?
- [ ] Không dùng `@DirtiesContext` để dọn state thông thường?
- [ ] Đã xem log cache DEBUG trước/sau để chứng minh tác động?
- [ ] Đã kiểm tra cùng JVM, không chỉ so sánh các lần chạy rời rạc?
- [ ] Không tối ưu cache bằng cách bỏ những kiểm thử tích hợp thực sự quan trọng?

**Kết luận:** khai báo mock không chỉ ảnh hưởng lời gọi được giả lập. Khi mock/spy được dùng để **thay bean trong Spring TestContext**, thông tin override trở thành một phần cấu hình context, thông qua `contextCustomizers` có thể đổi **khóa cache ApplicationContext**. Giữ nhất quán field name/qualifier và tập override giúp hạn chế tải context không cần thiết; việc tái sử dụng chỉ hợp lệ khi cấu hình thực sự tương đương.

### Tài liệu tham khảo chính thức

- [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html)
- [Spring Framework 6.2 — @MockitoBean và @MockitoSpyBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html)
- [Spring Framework — Bean Overriding in Tests](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/bean-overriding.html)
- [Spring Boot 3.4 API — @MockBean deprecated](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/mock/mockito/MockBean.html)
- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)