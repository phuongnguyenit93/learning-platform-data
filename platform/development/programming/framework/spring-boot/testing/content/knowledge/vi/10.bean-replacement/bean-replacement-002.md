# `@MockitoBean`, `@MockitoSpyBean` và phiên bản Spring Framework hỗ trợ

Khi viết test cho Spring Boot, ta thường muốn nạp một phần **Spring ApplicationContext thật** nhưng thay một dependency bằng đối tượng Mockito có thể điều khiển. Ví dụ, service tính tiền là bean thật, còn catalog ngoài mạng được thay bằng mock để test không gọi HTTP. Ở tình huống khác, ta muốn **giữ logic thật** của một bean nhưng theo dõi lời gọi hoặc ghi đè một hành vi cụ thể bằng spy.

Spring TestContext Framework cung cấp hai annotation cho việc **thay thế bean trong test context**:

- **`@MockitoBean`**: đưa **Mockito mock** vào Spring ApplicationContext, thay bean được chọn hoặc (mặc định) tạo mock bean nếu chưa tồn tại.
- **`@MockitoSpyBean`**: **bọc một bean thật đã có** bằng Mockito spy; hành vi thực được gọi theo mặc định, trừ những lời gọi được stub.

Hai annotation thuộc **Spring Framework 6.2 trở lên**, không phải tên alias của `@Mock`/`@Spy` trong Mockito và cũng không phải cùng package với `@MockBean`/`@SpyBean` cũ của Spring Boot. Bài này giải thích chính xác version/import, cách chọn bean, chiến lược REPLACE_OR_CREATE và WRAP, ví dụ JUnit Jupiter Java 17+ chạy được, migration và các lỗi dễ gặp.

## 1. Phân biệt Mockito thông thường với Spring bean override

Có ba cách tạo đối tượng giả trong kiểm thử, phục vụ các phạm vi khác nhau:

| Công cụ | Đối tượng được tạo/quản lý ở đâu? | Khi nào nên dùng? |
|---|---|---|
| `Mockito.mock(Catalog.class)` hoặc `@Mock` | Test/JUnit/Mockito thuần; **không tự thay Spring bean** | Unit test khởi tạo service bằng `new`, không cần context |
| `@MockitoBean` | Spring TestContext **thay hoặc đăng ký bean trong ApplicationContext** bằng mock | Slice/integration-style test cần service/controller thật nhưng kiểm soát collaborator |
| `@MockitoSpyBean` | Spring TestContext **bọc bean thật trong ApplicationContext** bằng spy | Cần giữ hành vi thật, quan sát invocation hoặc stub chọn lọc |

Ví dụ `@Mock PriceCatalog catalog;` của Mockito **không tự khiến `@Autowired OrderService` nhận mock ấy**. Nếu `OrderService` được Spring tạo với bean catalog khác, việc stub `@Mock` sẽ chẳng ảnh hưởng đến `OrderService`. `@MockitoBean` can thiệp vào cấu hình bean của test context để các bean khác được inject theo cấu hình override.

Ngược lại, nếu test chỉ kiểm thuật toán thuần Java và có thể tự tạo `new OrderService(mockCatalog)`, hãy ưu tiên Mockito/JUnit thuần: nhanh hơn, rõ phạm vi hơn và không cần `@SpringBootTest`.

## 2. Phiên bản nào hỗ trợ?

**Điểm mốc của Spring Framework là 6.2.** Tên annotation chính xác và import:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
```

Đừng nhầm với các annotation cũ:

```java
// API cũ của Spring Boot, không phải các annotation Spring Framework 6.2:
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.boot.test.mock.mockito.SpyBean;
```

Bảng định hướng về các dòng phiên bản phổ biến:

| Dòng thư viện | Tình trạng |
|---|---|
| **Spring Framework 6.0 / 6.1** | Chưa có `org.springframework.test.context.bean.override.mockito.MockitoBean` và `MockitoSpyBean`. Muốn dùng chúng phải nâng Spring Framework lên phiên bản tương thích; không chỉ đổi import. |
| **Spring Framework 6.2.x** | **Có** cả hai annotation trong `spring-test`. Đường dùng ở **field** là cách minh họa tương thích với bản 6.2.0. |
| **Spring Framework 7.0.x** | **Tiếp tục hỗ trợ** cơ chế bean override Mockito của TestContext. Một số hành vi chi tiết có thể khác dòng 6.2; kiểm tra tài liệu đúng version đang dùng. |
| **Spring Boot 3.0–3.3 thông thường** | Quản lý Spring Framework trước 6.2. Thường sử dụng `@MockBean` / `@SpyBean` của Boot hoặc test Mockito thuần. |
| **Spring Boot 3.4 / 3.5** | Thông thường quản lý Spring Framework 6.2, có thể chuyển sang `@MockitoBean` / `@MockitoSpyBean`. `@MockBean` và `@SpyBean` của Boot **deprecated từ 3.4.0**, dự kiến gỡ ở Boot 4.0. |
| **Spring Boot 4.0** | Spring Boot **đã loại bỏ** `@MockBean`/`@SpyBean` cũ, dùng annotation bean override của Spring Framework. Dòng Boot 4 đi với Spring Framework 7 và bộ dependency tương thích. |

Đừng suy luận phiên bản từ việc thấy tên package `org.springframework.boot` trong mã nguồn. Hãy kiểm tra **dependency tree thực tế** của module. Trong dự án có Maven/Gradle Wrapper, lệnh tham khảo:

```bash
# Maven: kiểm tra Spring Framework test dependency thực sự được chọn
./mvnw dependency:tree -Dincludes=org.springframework:spring-test

# Gradle: kiểm tra dependency trên test runtime classpath
./gradlew dependencyInsight --dependency spring-test --configuration testRuntimeClasspath
```

Đây là lệnh công cụ build, không phải lệnh chạy một file Java độc lập; ở multi-module cần chọn đúng module. Nếu compile báo `package org.springframework.test.context.bean.override.mockito does not exist`, trước tiên xác minh module có `spring-test` **6.2+** chứ không “chữa” bằng import tự tạo hoặc ép version đơn lẻ gây xung đột với Spring Boot BOM.

**Lưu ý tương thích theo patch:** Javadoc **Spring Framework 6.2.0** giới thiệu `@MockitoBean`/`@MockitoSpyBean` cho **field**. Tài liệu dòng 6.2 mới hơn còn mô tả cấu hình ở **cấp type** với `types` và meta-annotation; khi muốn dùng những khả năng mở rộng, hãy kiểm tra đúng API của **phiên bản 6.2.x thực sự cài đặt**, không mặc định bản patch đầu có mọi thuộc tính của bản patch cuối. Các ví dụ chạy được trong bài cố ý dùng **field-level annotations**.

## 3. Cơ chế override: mock khác spy về bản chất

### `@MockitoBean` — REPLACE_OR_CREATE

Ở chế độ mặc định, Spring TestContext sẽ tìm bean phù hợp và dùng **mock** để thay. Nếu không tìm được bean, cơ chế **REPLACE_OR_CREATE** có thể **tạo một mock bean mới**. Điều này hữu ích trong một số slice test, nhưng cũng nguy hiểm: thiếu bean thật do import/cấu hình sai mà test vẫn xanh vì mock đã được tạo.

Khi **bắt buộc phải tồn tại bean gốc**, dùng:

```java
@MockitoBean(enforceOverride = true)
PriceCatalog catalog;
```

`enforceOverride = true` chuyển sang **REPLACE**: nếu không tìm được bean để thay thì việc tạo test context thất bại, thay vì âm thầm tạo mock mới. Đoạn này là một **field bên trong test class có Spring TestContext**, không phải chương trình độc lập.

Mock tạo bởi Mockito thường trả default value khi chưa stub: số là 0, boolean `false`, reference có thể `null` tùy kiểu và Mockito defaults. Vì vậy **đừng xem dữ liệu mock chưa được stub là hành vi business thực**. Khi code thực sự cần trả sản phẩm/giá, stub điều kiện cụ thể bằng `when(...).thenReturn(...)`.

### `@MockitoSpyBean` — WRAP

Spy giữ bean thật rồi tạo Mockito spy bọc bean đó. Với lời gọi chưa stub, spy **gọi logic thật**. Cách này có ích để xác nhận service method có được gọi hoặc để ghi đè một hàm trong tình huống test khó dựng, nhưng cũng giữ nguyên các side effect có trong bean thật.

```java
@MockitoSpyBean
OrderPricingService pricingService;
```

`@MockitoSpyBean` yêu cầu **đúng một bean ứng viên tồn tại**; nó không có ý nghĩa “không có thì tạo một spy rỗng”. Nếu thiếu bean, có nhiều bean không phân giải được hoặc bean không hỗ trợ theo phiên bản, context sẽ không khởi tạo được. `@MockitoBean` và `@MockitoSpyBean` vì thế **không thể thay thế nhau bằng đổi tên annotation**.

| Tiêu chí | `@MockitoBean` | `@MockitoSpyBean` |
|---|---|---|
| Đối tượng trong context | Mockito mock | Mockito spy bọc bean gốc |
| Khi chưa stub | Hành vi mặc định của Mockito, **không gọi logic thật** | **Gọi logic thật** của bean |
| Chiến lược | `REPLACE_OR_CREATE`; `enforceOverride=true` thành `REPLACE` | `WRAP` |
| Bean gốc không tồn tại | Mặc định có thể tạo mock mới | **Báo lỗi** vì không có bean để wrap |
| Side effect | Tránh thực thi behavior thật của bean bị thay | Có thể thực thi I/O, cập nhật state, log hoặc transaction thực |
| Điểm mạnh | Cô lập collaborator, mô phỏng kết quả/lỗi | Kiểm hành vi thật và verify lời gọi |
| Rủi ro chính | Mock quá nhiều, kết quả sai nhưng test vẫn xanh | Stub sai cách làm chạy logic thật, test bị side effect |

## 4. Ví dụ hoàn chỉnh Java 17+ và Spring TestContext

Ta xây dựng một dịch vụ báo giá. Bean `OrderPricingService` là code thật; nó phụ thuộc vào port `PriceCatalog`. Trong test mock, Spring thay catalog bean bằng mock. Trong test spy, Spring bọc **service bean thật** bằng spy, trong khi catalog vẫn được mock để tránh I/O không cần thiết.

Cấu trúc tệp:

```text
src/
├── main/java/com/example/shop/pricing/
│   ├── PriceCatalog.java
│   └── OrderPricingService.java
└── test/java/com/example/shop/pricing/
    ├── PricingTestConfig.java
    ├── PriceCatalogMockTest.java
    └── OrderPricingServiceSpyTest.java
```

### 4.1. Interface dependency production

File **`src/main/java/com/example/shop/pricing/PriceCatalog.java`**:

```java
package com.example.shop.pricing;

@FunctionalInterface
public interface PriceCatalog {
    long unitPriceVnd(String sku);
}
```

Đây là một **port** đơn giản. Trong ứng dụng thật, adapter có thể tra DB hoặc gọi catalog API. Trong bài kiểm thử dưới đây ta không cần remote service thật.

### 4.2. Service cần được kiểm

File **`src/main/java/com/example/shop/pricing/OrderPricingService.java`**:

```java
package com.example.shop.pricing;

import java.util.Objects;

public class OrderPricingService {
    private final PriceCatalog catalog;

    public record Quote(String sku, int quantity, long totalVnd) {
    }

    public OrderPricingService(PriceCatalog catalog) {
        this.catalog = Objects.requireNonNull(catalog, "catalog");
    }

    public Quote quote(String sku, int quantity) {
        if (sku == null || sku.isBlank()) {
            throw new IllegalArgumentException("sku must not be blank");
        }
        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        long unitPrice = catalog.unitPriceVnd(sku);
        if (unitPrice < 0) {
            throw new IllegalStateException("negative price from catalog");
        }
        long total = Math.multiplyExact(unitPrice, quantity);
        return new Quote(sku, quantity, total);
    }
}
```

Service kiểm input trước khi gọi catalog, tính total bằng `Math.multiplyExact` để không im lặng khi tràn số nguyên và trả một `record` có equality theo nội dung. Ví dụ không thực hiện lưu DB hay gửi HTTP; mục tiêu là chứng minh **một bean thật dùng một dependency được Spring thay bằng mock**.

### 4.3. Spring test configuration nhỏ, rõ ranh giới

File **`src/test/java/com/example/shop/pricing/PricingTestConfig.java`**:

```java
package com.example.shop.pricing;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
class PricingTestConfig {
    @Bean
    PriceCatalog priceCatalog() {
        return sku -> 90_000L; // Bean thật được thay bằng mock trong các test.
    }

    @Bean
    OrderPricingService orderPricingService(PriceCatalog catalog) {
        return new OrderPricingService(catalog);
    }
}
```

Cấu hình tạo hai bean singleton. `PriceCatalog` được đăng ký thật để test có thể dùng `enforceOverride=true` và chứng minh cơ chế **REPLACE**, chứ không vô tình tạo bean mới. `OrderPricingService` vẫn lấy `PriceCatalog` theo DI; khi Spring tạo context kiểm thử, nó áp dụng bean override theo cấu hình test trước khi service được inject dùng catalog.

### 4.4. Mock một dependency, giữ service thật

File **`src/test/java/com/example/shop/pricing/PriceCatalogMockTest.java`**:

```java
package com.example.shop.pricing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@SpringJUnitConfig(PricingTestConfig.class)
class PriceCatalogMockTest {
    @MockitoBean(enforceOverride = true)
    PriceCatalog catalog;

    @Autowired
    OrderPricingService pricingService;

    @Test
    void returnsQuoteUsingTheMockedCatalog() {
        when(catalog.unitPriceVnd("BOOK-1")).thenReturn(125_000L);

        OrderPricingService.Quote quote =
                pricingService.quote("BOOK-1", 2);

        assertEquals(new OrderPricingService.Quote(
                "BOOK-1", 2, 250_000L), quote);
        verify(catalog).unitPriceVnd("BOOK-1");
    }

    @Test
    void invalidQuantityDoesNotCallTheCatalog() {
        assertThrows(IllegalArgumentException.class,
                () -> pricingService.quote("BOOK-1", 0));
        verifyNoInteractions(catalog);
    }
}
```

Hai assertion có ý nghĩa khác nhau: test thứ nhất xác minh bean service thật tính kết quả với giá từ **mock bean**; test thứ hai xác minh input sai không dẫn đến gọi dependency. Nếu đặt `@Mock PriceCatalog catalog` thuần vào class nhưng vẫn autowire service từ context, test này có thể đang stub **đối tượng khác** với dependency mà service dùng.

### 4.5. Spy bean thật, theo dõi và stub có chọn lọc

File **`src/test/java/com/example/shop/pricing/OrderPricingServiceSpyTest.java`**:

```java
package com.example.shop.pricing;

import org.junit.jupiter.api.Test;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;

@SpringJUnitConfig(PricingTestConfig.class)
class OrderPricingServiceSpyTest {
    @MockitoBean(enforceOverride = true)
    PriceCatalog catalog;

    @MockitoSpyBean
    OrderPricingService pricingService;

    @Test
    void spyCallsTheRealMethodByDefault() {
        when(catalog.unitPriceVnd("BOOK-1")).thenReturn(125_000L);

        OrderPricingService.Quote quote =
                pricingService.quote("BOOK-1", 2);

        assertEquals(new OrderPricingService.Quote(
                "BOOK-1", 2, 250_000L), quote);
        verify(pricingService).quote("BOOK-1", 2);
        verify(catalog).unitPriceVnd("BOOK-1");
    }

    @Test
    void doReturnStubsSpyWithoutCallingTheRealMethod() {
        OrderPricingService.Quote controlled =
                new OrderPricingService.Quote("BOOK-2", 1, 999L);

        doReturn(controlled).when(pricingService).quote("BOOK-2", 1);

        assertEquals(controlled, pricingService.quote("BOOK-2", 1));
        verify(pricingService).quote("BOOK-2", 1);
        verifyNoInteractions(catalog);
    }
}
```

Trong test đầu, spy chạy logic thật và có thể verify cả lời gọi service lẫn lời gọi catalog mock. Trong test sau, `doReturn(...).when(spy)...` stub trực tiếp method của spy **mà không gọi logic thật khi đang thiết lập stub**; kết quả 999 VND chỉ là giá trị chủ động dùng để chứng minh cơ chế spy, không phải business rule sản xuất. `verifyNoInteractions(catalog)` khẳng định real method không bị chạy ngoài ý muốn trong ca này.

**Vì sao không dùng `when(pricingService.quote(...)).thenReturn(...)` với spy?** Mockito phải đánh giá biểu thức `pricingService.quote(...)` trong lúc dựng stub; điều đó có thể gọi logic thật trước khi `thenReturn` được áp dụng, gây I/O, thay đổi dữ liệu hoặc lỗi do chưa stub dependency. Với spy, ưu tiên `doReturn`, `doThrow`, `doNothing` khi muốn tránh gọi real method trong lúc stub.

### 4.6. Kết quả và lệnh chạy

Năm file nêu trên là ví dụ **Java 17+ hoàn chỉnh ở mức source**, cần Spring Framework `spring-test` **6.2+**, Spring Context, JUnit Jupiter/Platform và Mockito trên test classpath. Một dự án Spring Boot 3.4+ hoặc 4.x có `spring-boot-starter-test` và phiên bản phù hợp thường đáp ứng các dependency này. Không cần `@SpringBootTest`, web server hay DB; `@SpringJUnitConfig` nạp context gọn đúng hai bean của ví dụ.

Trong module có Maven Wrapper:

```bash
./mvnw -Dtest=PriceCatalogMockTest,OrderPricingServiceSpyTest test
```

Hoặc Gradle Wrapper với task `test` bật JUnit Platform:

```bash
./gradlew test --tests "com.example.shop.pricing.PriceCatalogMockTest" --tests "com.example.shop.pricing.OrderPricingServiceSpyTest"
```

Trên Windows dùng `mvnw.cmd` hoặc `gradlew.bat`; chỉ chạy lệnh ứng với build tool của dự án. Với đúng các class và config trên, **4 phương thức test dự kiến PASS, 0 FAIL**. Không có stdout nghiệp vụ cố định: báo cáo JUnit/Surefire/Gradle có thể khác theo phiên bản plugin.

**Phạm vi chứng minh:** test verify cơ chế bean override và logic của `OrderPricingService` trong một **Spring test context**. Nó không chứng minh adapter catalog ngoài mạng hoạt động, transaction thật an toàn hoặc cấu hình toàn ứng dụng chạy được. Các câu hỏi đó cần integration/contract test tương ứng.

## 5. Cách chọn bean: type, name và qualifier

Theo mặc định, Spring tìm bean theo **type của field được annotate**. Nếu chỉ có một `PriceCatalog`, `@MockitoBean PriceCatalog catalog` có thể xác định bean mà không cần tên. Nếu có **hai bean cùng type**, việc chọn theo type có thể mơ hồ; sử dụng `@Qualifier` hoặc `name` rõ ràng.

Ví dụ minh họa, giả định context có bean tên `primaryCatalog`:

```java
@MockitoBean(name = "primaryCatalog", enforceOverride = true)
PriceCatalog catalog;
```

Hoặc:

```java
@MockitoBean(enforceOverride = true)
@Qualifier("primaryCatalog")
PriceCatalog catalog;
```

Cần import `org.springframework.beans.factory.annotation.Qualifier` nếu dùng cách thứ hai. Đây là các **field snippet** thay thế cho field mock trong test, không phải file Java độc lập. `name` chỉ một bean cụ thể; `@Qualifier` hỗ trợ phân biệt ứng viên khi có nhiều bean tương thích.

Nếu không khai báo `@Qualifier`, **tên field** có thể được dùng như fallback qualifier. Điều này dẫn đến một lưu ý dễ bỏ qua: **tên field và qualifier là một phần của cách Spring TestContext xác định context cache key**. Hai test mock cùng bean nhưng đặt tên field khác nhau có thể tạo các context khác nhau không cần thiết. Với nhiều test class cùng cấu hình, nên đặt tên field mock nhất quán để tăng khả năng tái sử dụng context.

Khi dùng class-level annotation trong các patch hỗ trợ, có thể thấy cú pháp như:

```java
@MockitoBean(types = {PaymentGateway.class, EmailClient.class})
class PaymentFlowTest {
    // Test methods...
}
```

Đoạn này **chỉ minh họa cho các phiên bản Spring Framework đã hỗ trợ `types` ở cấp class** và các kiểu giả định; **không dùng nó như API chắc chắn có trên Spring Framework 6.2.0**. Nếu chỉ định `name` ở cấp type, cần đúng một `types` ứng với bean đó theo quy tắc của API. Tái dùng nhiều mock có thể áp dụng meta-annotation khi phiên bản hỗ trợ, nhưng đừng dùng chúng để biến mọi test thành context quá rộng.

## 6. Scope, AOP proxy, FactoryBean và context hierarchy

### Scope của bean

**Spring Framework 6.2 ban đầu** chỉ cho bean override Mockito trên **singleton**; cố override prototype/request/session-scoped bean có thể làm test context thất bại. Một số dòng/phiên bản Framework về sau có thay đổi cách xử lý non-singleton, nên không suy đoán hành vi scope của dự án khác version từ một tài liệu mới nhất. Trong ví dụ, cả hai bean đều singleton nên không có vấn đề này.

Hãy kiểm tra tài liệu theo **version đã pin** nếu cần mock/spy bean không phải singleton hoặc scoped proxy. Đặc biệt, đổi prototype thành mock singleton (nếu phiên bản cho phép) cũng **thay đổi ngữ nghĩa scope**, nên kết quả test không còn chứng minh cách production xử lý nhiều instance.

### Spring AOP và proxy

Mock bean do `@MockitoBean` thay thế không phải là bean gốc thực thi logic; test không nên dùng mock này để chứng minh `@Transactional`, `@Cacheable` hay `@Retryable` trên bean thực. Khi bọc spy, interaction với AOP proxy có thể phức tạp: proxy của Spring có thể bọc spy hoặc ảnh hưởng việc verify/stub. Cần kiểm tra lớp đang verify có phải proxy hay target, và khi thực sự muốn kiểm transaction/cache, ưu tiên test tích hợp có infrastructure liên quan.

### Bean do `FactoryBean` tạo

Với `@MockitoBean`, khi override đối tượng sản phẩm của `FactoryBean`, Spring có thể thay definition bằng mock của **loại đối tượng mà factory tạo ra**. Với `@MockitoSpyBean`, spy nhắm tới **đối tượng do factory tạo**, không nhất thiết là chính `FactoryBean`. Đây là chi tiết quan trọng khi test bean được tạo qua factory hoặc auto-configuration.

### `@ContextHierarchy`

Nếu test dùng nhiều ApplicationContext cha/con, bean override Mockito có thể áp dụng **đến nhiều tầng** theo mặc định, gây thiếu bean hoặc thay bean ngoài ý muốn. Sử dụng `contextName` trùng với tên cấp `@ContextConfiguration` muốn nhắm tới:

```java
@MockitoBean(contextName = "app-config")
PriceCatalog catalog;
```

Đoạn này là field snippet dành cho một test thật sự dùng `@ContextHierarchy` và có context cấp `app-config`. Đừng thêm `contextName` khi chỉ có một context thông thường.

## 7. Mockito reset, cô lập và context cache

Spring TestContext có cơ chế reset mock/spy theo lifecycle. Với những version phổ biến của API `@MockitoBean`/`@MockitoSpyBean`, `reset` mặc định là **`MockReset.AFTER`**, tức Mockito interactions/stubbings được reset sau mỗi test method. Có thể chọn mode khác bằng attribute `reset` khi có lý do, nhưng không nên chia sẻ trạng thái mock giữa test.

**Lưu ý ba loại state khác nhau:**

1. **Mockito state**: các lời gọi được ghi nhận và stub; reset có thể xóa các thông tin này.
2. **Spring ApplicationContext**: có thể được cache và dùng lại giữa test class có cấu hình tương đương; context cache không phải là cách reset database.
3. **State thật trong bean spy**: reset Mockito **không đảo ngược side effect thực** đã xảy ra, không rollback DB, không hoàn tác file/network, và không tự reset mọi field mutable trong target bean.

Do đó, khi spy một service có state hoặc thực hiện I/O, test phải có fixture/cleanup phù hợp. Khi có parallel test execution, cần quan tâm shared context, mock state và race condition; việc reset mock trong một test có thể ảnh hưởng test đang dùng cùng mock nếu chạy đồng thời. Đừng dùng `@DirtiesContext` tùy tiện chỉ để “xóa lịch sử Mockito”, vì làm mất context cache và tăng thời gian chạy.

## 8. Migration từ Spring Boot `@MockBean`/`@SpyBean`

Ví dụ trong Spring Boot cũ:

```java
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.boot.test.mock.mockito.SpyBean;

// Field trong test:
@MockBean
PriceCatalog catalog;

@SpyBean
OrderPricingService pricingService;
```

Với Spring Framework 6.2+ và Boot version hỗ trợ, cách viết mới:

```java
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.context.bean.override.mockito.MockitoSpyBean;

// Field trong test:
@MockitoBean
PriceCatalog catalog;

@MockitoSpyBean
OrderPricingService pricingService;
```

Các đoạn trên chỉ minh họa **imports/field trong test class**, không phải chương trình Java độc lập. Với Spring Boot 3.4/3.5, API cũ deprecated; với Boot 4.0, API cũ **đã bị loại bỏ**. Không phải mọi dự án đều thay trực tiếp hai import là xong: cần xem phiên bản Framework, cách chọn bean, scope, xem class có bean thực để spy không, các test cấu hình bean bằng annotation cũ trên **`@Configuration` class**, và các attribute legacy không ánh xạ 1:1 sang API mới.

**Lưu ý migration quan trọng:** annotation mới của Framework được áp dụng trên **test field hoặc test type** theo khả năng version; **không đặt `@MockitoBean` trên field của một `@Configuration` class rồi mặc định đó là cách tương đương với `@MockBean` cũ**. Muốn tái dùng cấu hình mock, cân nhắc meta-annotation dùng đúng version hoặc dùng `@TestConfiguration`/`@Bean` với chủ ý rõ.

Quy trình nâng cấp khuyến nghị:

1. Kiểm phiên bản `spring-test` được chọn thực tế, tránh tự nâng đơn lẻ không tương thích với Spring Boot BOM.
2. Đổi imports sang `org.springframework.test.context.bean.override.mockito` tại những test dùng Spring context.
3. Với bean **bắt buộc có thật**, dùng `enforceOverride=true` để lộ lỗi cấu hình thiếu bean.
4. Kiểm các test có **nhiều ứng viên cùng type**, bean tên cụ thể và `@Qualifier`; thống nhất tên field để tránh làm vỡ cache key.
5. Đối với spy, kiểm bean thực sự tồn tại và lựa chọn `doReturn`/`doThrow` khi không muốn real method chạy ở bước stub.
6. Chạy các test ở class level, suite và CI; xác nhận bean bị thay **đúng** và verify thật sự chạy trên object mà service/controller sử dụng.
7. Chỉ sau khi test pass và assertion còn đúng, loại bỏ API Boot legacy; đừng coi việc code compile thành công là bằng chứng migration giữ nguyên behavior.

## 9. Lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `Cannot resolve symbol MockitoBean` | `spring-test` dưới 6.2 hoặc import sai package | Kiểm dependency tree, dùng đúng import của Framework, chọn bộ version tương thích |
| Context vẫn nạp client thật khi test cần mock | Dùng `@Mock` Mockito thuần chứ không phải bean override | Dùng `@MockitoBean` trên Spring test class đã đăng ký SpringExtension |
| Test xanh dù bean cần mock không hề tồn tại | `@MockitoBean` mặc định có thể **create** mock mới | Dùng `enforceOverride=true` nếu phải thay bean có thật |
| `@MockitoSpyBean` thất bại lúc bootstrap | Không có bean gốc, nhiều ứng viên hoặc scope không tương thích | Nạp đúng config, chọn đúng `name`/`@Qualifier`, kiểm scope và version |
| Spy vô tình gọi DB/HTTP khi khai báo stub | `when(spy.realMethod())` có thể thực thi real method | Dùng `doReturn(...).when(spy)...` hoặc `doThrow(...).when(spy)...` |
| `verify(mock)` không thấy lời gọi | Bean được inject không phải mock đang stub hoặc code không đi qua nhánh đó | Kiểm override thực sự nằm trong context của service, qualifier và test config |
| Một số test class khởi động context lặp lại | Tên field/qualifier khác nhau ảnh hưởng cache key | Dùng cách đặt tên và cấu hình mock nhất quán |
| Spy chạy thật nhưng trạng thái rò sang test khác | Spy wrap bean có state, reset Mockito không khôi phục business state | Fixture và cleanup đúng; hạn chế spy mutable singleton |
| Verify spy bị khó hiểu khi có transaction/cache proxy | Spring AOP bọc đối tượng được spy | Hiểu tầng proxy, dùng test tích hợp phù hợp nếu kiểm AOP |
| Chuyển Boot 4 bị lỗi import `MockBean` | API cũ Boot đã bị loại bỏ | Chuyển `@MockitoBean`/`@MockitoSpyBean` và kiểm khác biệt hành vi |
| Mock trong `@Configuration` không được Framework nhận diện | Annotation mới không hỗ trợ theo mô hình field config cũ | Đặt annotation trên test class hoặc dùng composed annotation đúng version |
| Test cần DB thật nhưng đang mock repository | Override làm mất ranh giới đang cần chứng minh | Tách unit/slice test và integration test thật, không mock dependency cốt lõi |

## 10. Checklist trước khi dùng hoặc nâng cấp

- [ ] Tôi biết test đang dùng Spring Framework **6.2+** hoặc dòng mới hơn có annotation.
- [ ] Imports là `org.springframework.test.context.bean.override.mockito.MockitoBean` / `MockitoSpyBean`.
- [ ] Tôi dùng **JUnit/Mockito thuần** khi không cần Spring context.
- [ ] Nếu dùng `@MockitoBean`, tôi quyết định rõ có cần **`enforceOverride=true`** hay cho phép tạo mới.
- [ ] Nếu dùng `@MockitoSpyBean`, bean gốc tồn tại **đúng một ứng viên** và side effect thật được kiểm soát.
- [ ] Khi có nhiều bean cùng type, tôi dùng `name` hoặc qualifier rõ ràng và thống nhất.
- [ ] Tôi đã cân nhắc scope, AOP proxy, `FactoryBean` và context hierarchy nếu hệ thống có chúng.
- [ ] Tôi hiểu `doReturn` khác `when` trên spy; không gọi real method ngoài ý muốn lúc stub.
- [ ] Các mock/spy được reset đúng lifecycle, nhưng state thật trong bean/DB vẫn phải dọn.
- [ ] Test có assertion **kết quả và tương tác** đúng mục tiêu, không chỉ `assertNotNull`.
- [ ] Trước khi chuyển Boot 4, tôi đã kiểm và loại API legacy `@MockBean`/`@SpyBean`.
- [ ] Đã chạy test bằng Maven/Gradle trên bộ Spring/JUnit/Mockito version của dự án.

**Kết luận:** dùng `@MockitoBean` để **thay một Spring bean bằng mock** và `@MockitoSpyBean` để **bọc bean thật bằng spy** trong test ApplicationContext. Ranh giới version tối thiểu là **Spring Framework 6.2**; trong quá trình chuyển từ Spring Boot 3.4/3.5 sang Boot 4, cần đổi annotation cũ, nhưng cũng phải kiểm **bean selection, scope, proxy và hành vi thực** chứ không chỉ sửa imports.

### Tài liệu chính thức để kiểm theo phiên bản

- [Spring Framework 6.2 — `@MockitoBean` và `@MockitoSpyBean`](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html)
- [Spring Framework 6.2.0 — Javadoc `@MockitoBean`](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/test/context/bean/override/mockito/MockitoBean.html)
- [Spring Framework 6.2.0 — Javadoc `@MockitoSpyBean`](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/test/context/bean/override/mockito/MockitoSpyBean.html)
- [Spring Boot 3.4 — deprecated `@MockBean`](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/mock/mockito/MockBean.html)
- [Spring Boot 4.0 — Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide)
