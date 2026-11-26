# `@Import` trong module test

## 1. Vấn đề cần giải quyết

Khi dùng `@ApplicationModuleTest` trong Spring Modulith, ta thường muốn khởi động phần ứng dụng thuộc một module cụ thể, chẳng hạn `orders`, để kiểm tra logic của module mà không phụ thuộc vào toàn bộ hệ thống. Tuy nhiên, một service của `orders` có thể yêu cầu `PaymentGateway` do module `payments` công bố. Ở chế độ bootstrap mặc định, implementation thật của `payments` không tự được đưa vào context. Khi không có bean thay thế, Spring không thể tạo service cần kiểm thử.

`@Import` của Spring Framework giúp **đưa một hoặc nhiều thành phần cấu hình được chỉ định rõ vào `ApplicationContext` của bài test**. Dùng đúng cách, nó tạo ra một vùng kiểm thử xác định: giữ bean nghiệp vụ của module đích, bổ sung fake hoặc cấu hình hạ tầng đúng nhu cầu và quan sát kết quả. Dùng thiếu kiểm soát, `@Import` có thể kéo theo nhiều bean ngoài module, làm mất mục tiêu cô lập mà `@ApplicationModuleTest` đang phục vụ.

Trong học phần `SPRING_MODULITH_VERIFICATION_TESTING`, kỹ thuật này gắn với ba nhiệm vụ: thực hành module test, xác minh phụ thuộc kiến trúc bằng `ApplicationModules`, và thiết kế quality gate CI để phát hiện lỗi ranh giới, sự kiện, dữ liệu và tích hợp.

Sau bài học, bạn cần hiểu `@Import` nạp gì, đặt ở đâu, phối hợp thế nào với `BootstrapMode`, và khi nào nên dùng fake, mock hay dependency thật.

## 2. `@Import` làm gì trong Spring?

`@Import` thuộc package `org.springframework.context.annotation`. Annotation này cho phép một lớp cấu hình hoặc lớp thành phần nhập trực tiếp các loại cấu hình/bean được chỉ định.

Ví dụ đơn giản:

```java
import org.springframework.context.annotation.Import;

@Import(ExampleTestConfiguration.class)
class ExampleTest {
}
```

Khi Spring xử lý cấu hình của bài test, nó có thể đăng ký những bean được khai báo trong `ExampleTestConfiguration` vào cùng `ApplicationContext` của test. `@Import` có thể nhận nhiều class:

```java
@Import({
    FixedClockTestConfiguration.class,
    FakePaymentTestConfiguration.class
})
class ExampleTest {
}
```

Không chỉ có `@Configuration`: ở mức Spring Framework, `@Import` còn hỗ trợ nhập class thông thường làm bean, `ImportSelector` và `ImportBeanDefinitionRegistrar`. Trong module test, trường hợp dễ đọc và ít bất ngờ nhất là **nhập một lớp `@TestConfiguration` nhỏ, chuyên cung cấp các bean cần thiết cho test**.

Phân biệt các cơ chế sau:

| Cơ chế | Quyết định điều gì? | Ví dụ |
| --- | --- | --- |
| `@ApplicationModuleTest` | Tạo Spring Boot test context theo module chứa test | Test nằm trong package `orders` |
| `BootstrapMode` | Các application module nào được chọn để bootstrap | `STANDALONE`, `DIRECT_DEPENDENCIES`, `ALL_DEPENDENCIES` |
| `@Import` | Những cấu hình/bean nào được bổ sung tường minh vào context | `@Import(FakePaymentsConfiguration.class)` |
| `@MockitoBean` | Bean nào được thay bằng/tạo thành Mockito mock trong context test, theo phiên bản Spring Test | Mock API `PaymentGateway` |
| `ApplicationModules.verify()` | Các quan hệ phụ thuộc giữa module có đúng quy tắc kiến trúc không? | Chặn việc gọi vào package internal của module khác |

**Điểm mấu chốt:** `@Import` thêm cấu hình cho Spring Test; nó không tự thay đổi `BootstrapMode` hoặc biến module được import thành một dependency kiến trúc hợp lệ.

## 3. Bối cảnh ví dụ: `orders` cần API từ `payments`

Xét một ứng dụng bán hàng có package gốc `com.example.shop`:

```text
src/main/java/com/example/shop/
├── ShopApplication.java            // @SpringBootApplication
├── orders/
│   └── OrderService.java           // @Service
├── payments/
│   ├── PaymentGateway.java         // public API của payments
│   └── RemotePaymentGateway.java   // implementation thật
└── notifications/
    └── OrderPlacedListener.java    // xử lý sự kiện đơn hàng

src/test/java/com/example/shop/
├── orders/
│   └── OrdersModuleTest.java
└── testsupport/
    └── FakePaymentsConfiguration.java
```

Với mô hình module theo các package con trực tiếp của package ứng dụng, `orders`, `payments` và `notifications` là các application module. Giả sử `orders` sử dụng API công khai của `payments` nhưng `notifications` không phải dependency của `orders`.

```mermaid
flowchart LR
    O[orders] -->|PaymentGateway API| P[payments]
    N[notifications] -.->|xử lý sự kiện OrderPlaced| O
```

`PaymentGateway` là contract do `payments` công bố:

```java
package com.example.shop.payments;

public interface PaymentGateway {
    boolean authorize(String orderId, long amountInCents);
}
```

Service thật trong module `orders`:

```java
package com.example.shop.orders;

import com.example.shop.payments.PaymentGateway;
import org.springframework.stereotype.Service;

@Service
class OrderService {

    private final PaymentGateway paymentGateway;

    OrderService(PaymentGateway paymentGateway) {
        this.paymentGateway = paymentGateway;
    }

    String place(String orderId, long amountInCents) {
        if (!paymentGateway.authorize(orderId, amountInCents)) {
            throw new IllegalArgumentException(
                "Payment refused for " + orderId);
        }
        return "PLACED:" + orderId;
    }
}
```

Giả sử `RemotePaymentGateway` là bean `@Service` nằm trong module `payments`. Trong bài test `orders` sử dụng `@ApplicationModuleTest` mặc định, bean nghiệp vụ của `payments` không được chọn để bootstrap theo phạm vi `STANDALONE`. Nếu không có bean `PaymentGateway` do test cung cấp, việc tạo `OrderService` thường thất bại với `UnsatisfiedDependencyException` trước khi chạy `@Test`.

Ta có thể giữ `STANDALONE` và dùng `@Import` để cung cấp một fake ở đúng ranh giới API.

## 4. Ví dụ hoàn chỉnh: nhập một `@TestConfiguration` để kiểm thử module

Đầu tiên tạo cấu hình dành riêng cho test, nằm trong `src/test/java`:

```java
// src/test/java/com/example/shop/testsupport/FakePaymentsConfiguration.java
package com.example.shop.testsupport;

import com.example.shop.payments.PaymentGateway;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;

@TestConfiguration(proxyBeanMethods = false)
public class FakePaymentsConfiguration {

    @Bean
    PaymentGateway paymentGateway() {
        return (orderId, amountInCents) ->
            orderId.startsWith("OK-") && amountInCents > 0;
    }
}
```

Cấu hình này tạo đúng một bean `PaymentGateway` là fake, không truy cập mạng hoặc cơ sở dữ liệu. Nó xác nhận giao dịch với mã đơn bắt đầu bằng `OK-` và số tiền dương.

Sau đó import cấu hình ở lớp module test:

```java
// src/test/java/com/example/shop/orders/OrdersModuleTest.java
package com.example.shop.orders;

import com.example.shop.testsupport.FakePaymentsConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Import;
import org.springframework.modulith.test.ApplicationModuleTest;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@ApplicationModuleTest
@Import(FakePaymentsConfiguration.class)
class OrdersModuleTest {

    @Autowired
    OrderService orders;

    @Test
    void acceptsOrderWhenPaymentIsAuthorized() {
        assertThat(orders.place("OK-123", 2_000))
            .isEqualTo("PLACED:OK-123");
    }

    @Test
    void rejectsOrderWhenPaymentIsDenied() {
        assertThatThrownBy(() -> orders.place("FAIL-123", 2_000))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("FAIL-123");
    }
}
```

Cách đoạn test này hoạt động:

1. Spring Modulith xác định module mục tiêu là `orders` từ package chứa `OrdersModuleTest`.
2. `@ApplicationModuleTest` chọn `STANDALONE` vì không chỉ định `mode` khác.
3. `@Import(FakePaymentsConfiguration.class)` đưa cấu hình fake vào cùng test context.
4. Phương thức `@Bean` tạo một `PaymentGateway` đủ để constructor của `OrderService` được thỏa mãn.
5. Hai phép kiểm tra xác minh hành vi chấp nhận/từ chối đơn hàng với `OrderService` thật.

`OrderService` là bean thật của module `orders`; `PaymentGateway` là fake do test cung cấp. Vì vậy, bài kiểm thử **không chứng minh** `RemotePaymentGateway` thật hoặc hệ thống thanh toán bên ngoài hoạt động. Sự phân biệt này cần được ghi rõ khi đặt tên test và thiết kế chất lượng kiểm thử.

### Minh họa cấu trúc context

```mermaid
flowchart TB
    T[OrdersModuleTest] --> M[@ApplicationModuleTest: orders]
    T --> I[@Import FakePaymentsConfiguration]
    M --> C[ApplicationContext của bài test]
    I --> C
    C --> S[OrderService thật]
    C --> F[PaymentGateway fake]
    S -->|constructor injection| F
```

Cả bean nghiệp vụ và bean fake tồn tại trong **một** test context. `@Import` không tạo một container con độc lập.

## 5. Đặt `@Import` ở đâu? Phân biệt nested và top-level

Khi cấu hình chỉ dùng cho một lớp test, có thể định nghĩa `@TestConfiguration` **static nested** ngay trong lớp test:

```java
package com.example.shop.orders;

import com.example.shop.payments.PaymentGateway;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.modulith.test.ApplicationModuleTest;

import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest
class OrdersWithLocalFakeTest {

    @Autowired
    OrderService orders;

    @Test
    void authorizesOrder() {
        assertThat(orders.place("OK-NESTED", 10))
            .isEqualTo("PLACED:OK-NESTED");
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class LocalPaymentsConfiguration {

        @Bean
        PaymentGateway paymentGateway() {
            return (orderId, amountInCents) ->
                orderId.startsWith("OK-") && amountInCents > 0;
        }
    }
}
```

Spring Boot test thường nhận diện lớp `static nested @TestConfiguration` và bổ sung vào cấu hình của test, do đó trường hợp này **không cần thêm `@Import` chỉ để nạp cấu hình lồng**.

Ngược lại, `FakePaymentsConfiguration` là một lớp top-level trong `src/test/java/com/example/shop/testsupport`. Spring Boot thường loại những lớp top-level `@TestConfiguration` khỏi component scanning thông thường. Nếu test muốn dùng nó, cần một cơ chế nhập rõ ràng như `@Import`.

| Vị trí khai báo | Cách nạp thường dùng | Khi nên chọn |
| --- | --- | --- |
| `static nested @TestConfiguration` trong test class | Spring Boot test phát hiện tự động | Fake/fixture nhỏ chỉ phục vụ một lớp |
| Top-level `@TestConfiguration` bên cạnh test | `@Import` | Muốn tách một cấu hình dài khỏi code test |
| Top-level `@TestConfiguration` trong `testsupport` | `@Import` ở từng test sử dụng | Nhiều lớp test cùng cần một fake stateless |
| `@Configuration` trong `src/main/java` | Cơ chế bootstrap/configuration production | Bean phục vụ vận hành thật, không phải fake test |

**Đặt class trong cùng package hoặc trong `src/test/java` chưa đủ để class trở thành bean.** Phải có cơ chế phát hiện hoặc nhập cấu hình tương ứng. Đối với cấu hình test top-level, `@Import` thể hiện rõ nhất ý định dùng cấu hình nào.

Một cấu hình test dùng chung nên ưu tiên bean **không giữ trạng thái thay đổi**. Spring Test có thể cache `ApplicationContext` giữa các test có cấu hình tương thích; singleton fake có trạng thái nếu không reset có thể khiến test bị ảnh hưởng bởi thứ tự chạy.

## 6. `@Import` trực tiếp một class thông thường khác gì import configuration?

`@Import` không giới hạn ở lớp có `@Configuration`. Spring Framework có thể đăng ký một class thông thường được import như một bean. Ví dụ một fake cụ thể đặt trong test source:

```java
// src/test/java/com/example/shop/testsupport/FixedPaymentGateway.java
package com.example.shop.testsupport;

import com.example.shop.payments.PaymentGateway;

public class FixedPaymentGateway implements PaymentGateway {

    @Override
    public boolean authorize(String orderId, long amountInCents) {
        return true;
    }
}
```

Bài test có thể khai báo:

```java
import com.example.shop.testsupport.FixedPaymentGateway;
import org.springframework.context.annotation.Import;
import org.springframework.modulith.test.ApplicationModuleTest;

@ApplicationModuleTest
@Import(FixedPaymentGateway.class)
class OrdersAlwaysAuthorizedTest {
    // Spring có thể đăng ký FixedPaymentGateway làm bean.
}
```

Tuy nhiên, đây thường là lựa chọn ít tường minh hơn `@TestConfiguration` khi cần nhiều bean, cần tên bean riêng hoặc cần điều kiện cấu hình. Một lớp cấu hình test cho phép reviewer nhìn rõ `@Bean` nào được cung cấp và tại sao. Khi sử dụng direct class import, vẫn phải bảo đảm constructor/dependency của class đó có thể được Spring tạo thành công.

`@Import` còn có thể nhận `ImportSelector` và `ImportBeanDefinitionRegistrar`. Hai cơ chế này cho phép đăng ký bean theo logic tự chọn, nhưng phù hợp cấu hình framework hoặc tình huống nâng cao hơn. Với module test cần vài fake hoặc fixture, **tránh thêm tầng đăng ký động không cần thiết**.

## 7. `@Import` không đồng nghĩa mở rộng `BootstrapMode`

Spring Modulith Test cho phép chọn các phạm vi sau:

| `BootstrapMode` | Application module được chọn khi test `orders` | Vai trò của `@Import` |
| --- | --- | --- |
| `STANDALONE` (mặc định) | `orders` | Bổ sung riêng fake hoặc bean test; không tự nạp toàn bộ `payments` |
| `DIRECT_DEPENDENCIES` | `orders` và các module `orders` phụ thuộc trực tiếp | Có thể thêm một số test bean; những dependency thật vẫn được lựa chọn theo đồ thị module |
| `ALL_DEPENDENCIES` | `orders` và các dependency module trực tiếp/bắc cầu | Có thể thêm cấu hình test cho các integration case đặc biệt |

Ví dụ kiểm thử tương tác với module `payments` thật:

```java
package com.example.shop.orders;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.ApplicationModuleTest.BootstrapMode;

@ApplicationModuleTest(
    mode = BootstrapMode.DIRECT_DEPENDENCIES
)
class OrdersPaymentsIntegrationTest {

    @Test
    void placesOrderUsingRealPaymentAdapter() {
        // Chuẩn bị test server/database và các fixture cần thiết.
        // Gọi OrderService; assert kết quả hoặc tác động tích hợp.
    }
}
```

Đây là bộ khung để minh họa lựa chọn context. Nó chưa phải bài integration test hoàn chỉnh khi chưa có setup và assertion cụ thể. Nếu `payments` là dependency trực tiếp được Spring Modulith nhận diện, `DIRECT_DEPENDENCIES` có thể đưa các bean của module này vào context. Nhưng để khởi động thành công adapter thật, vẫn cần các cấu hình phụ thuộc, máy chủ giả lập hoặc database phù hợp.

Phân biệt hai tình huống:

- `@Import(FakePaymentsConfiguration.class)` trong `STANDALONE`: **cung cấp một test bean** đáp ứng interface, giữ phạm vi ứng dụng chủ yếu là `orders`.
- `@ApplicationModuleTest(mode = DIRECT_DEPENDENCIES)`: **mở rộng tập application module** được bootstrap theo dependency graph; bean thật của module liên quan có thể được tạo.

Không nên dùng `@Import` để kéo toàn bộ `PaymentsProductionConfiguration` vào một test `orders` chỉ để tránh `UnsatisfiedDependencyException`. Cấu hình đó có thể đăng ký HTTP client, repository, queue consumer và nhiều dependency bắc cầu mà bài test không cần.

## 8. Vì sao `@Import` có thể làm rò rỉ phạm vi kiểm thử?

Giả sử module `payments` có cấu hình:

```java
package com.example.shop.payments;

import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.ComponentScan;

@Configuration
@ComponentScan("com.example.shop.payments")
public class PaymentsProductionConfiguration {
    // Ví dụ một cấu hình production quét nhiều adapter.
}
```

Nếu test `orders` viết:

```java
@ApplicationModuleTest
@Import(PaymentsProductionConfiguration.class)
class OrdersTest {
}
```

Spring được yêu cầu xử lý **cấu hình production của `payments`**. Nếu cấu hình này quét cả package hoặc import thêm các cấu hình khác, nó có thể đăng ký nhiều bean mà `STANDALONE` vốn không chủ động chọn. Kết quả phụ thuộc cụ thể vào quy tắc lọc, điều kiện bean và cấu hình của phiên bản Spring Modulith/Spring Boot đang dùng, nên phải xác minh context thực tế.

Hệ quả có thể gặp:

1. Context khởi động chậm hơn và phụ thuộc vào dịch vụ bên ngoài.
2. Một bean bất ngờ xuất hiện khiến test trông có vẻ tích hợp thật dù không chủ đích.
3. Hai bean cùng kiểu xung đột với fake do test khai báo.
4. Một listener hoặc scheduled component được đăng ký và có side effect.
5. Test chạy khác nhau giữa máy cá nhân và CI vì profile hoặc hạ tầng chưa đồng nhất.

`@Import` là công cụ cấu hình Spring, **không phải cơ chế tự động bảo vệ ranh giới Spring Modulith**. Nếu mục tiêu là kiểm thử module phụ thuộc thật, chọn `BootstrapMode` phù hợp và kiểm tra behavior của adapter thật sẽ minh bạch hơn.

## 9. Lỗi phổ biến: bean không có, trùng tên, trùng kiểu

### 9.1. Đã tạo `@TestConfiguration` nhưng bean vẫn thiếu

Giả sử cấu hình `FakePaymentsConfiguration` đặt top-level, nhưng test chỉ có:

```java
@ApplicationModuleTest
class OrdersWithoutImportTest {
    // Thiếu @Import(FakePaymentsConfiguration.class)
}
```

Spring Boot không nhất thiết tự phát hiện cấu hình top-level trong `src/test/java`. Nếu không có bean `PaymentGateway` khác, context sẽ không tạo được `OrderService`.

**Cách xử lý:** thêm `@Import` đúng class; kiểm tra package/classpath; xem bean có bị ràng buộc bởi `@Profile`, `@Conditional` hoặc dependency khác không.

### 9.2. Có hai bean `PaymentGateway`

Nếu đã bootstrap `payments` thật, đồng thời import một fake:

```java
@ApplicationModuleTest(
    mode = BootstrapMode.DIRECT_DEPENDENCIES
)
@Import(FakePaymentsConfiguration.class)
class AmbiguousPaymentsTest {
}
```

Khi bean thật và fake đều tồn tại với cùng type `PaymentGateway`, tiêm theo type có thể bị `NoUniqueBeanDefinitionException`. Nếu hai bean dùng cùng tên `paymentGateway`, còn có nguy cơ lỗi trùng bean definition hoặc override không mong muốn.

Các hướng xử lý gồm: chỉ dùng một cách cung cấp dependency; chọn bean bằng `@Qualifier`; dùng `@Primary` cho bean ưu tiên nếu hợp lý; hoặc sử dụng cơ chế override của Spring Test khi thực sự cần thay bean production.

Ví dụ `@Primary` trong một cấu hình test **chỉ ưu tiên lựa chọn khi có nhiều bean hợp lệ theo kiểu**, không xóa bean thật:

```java
import com.example.shop.payments.PaymentGateway;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;

@TestConfiguration(proxyBeanMethods = false)
public class PreferredFakePaymentConfiguration {

    @Bean("preferredFakePaymentGateway")
    @Primary
    PaymentGateway preferredFakePaymentGateway() {
        return (orderId, amountInCents) -> true;
    }
}
```

Đừng dùng `@Primary` để che lỗi một cấu hình import sai phạm vi. Hãy hỏi vì sao có hai bean, test nào cần implementation nào, và tên bean có bị trùng không.

### 9.3. Import thành công nhưng lỗi ở dependency cấp sau

`@Import` của một configuration không tự khởi tạo mọi thứ hoàn chỉnh. Ví dụ bean được import cần `DataSource`, `EntityManager` hoặc một HTTP client nhưng các dependency này chưa được cấu hình. Ngoại lệ gốc có thể chuyển từ thiếu `PaymentGateway` sang thiếu bean hạ tầng khác. Đây là dấu hiệu cần xem lại **độ lớn của cấu hình được import** và mục tiêu kiểm thử.

### 9.4. Annotation đặt sai nơi

`@Import` dùng được trên lớp cấu hình/test theo cơ chế xử lý annotation của Spring; nó không có tác dụng chỉ vì xuất hiện trong một class không được framework nạp. Ví dụ thêm `@Import` trên một helper class mà test không tham chiếu không khiến helper đó tự được phát hiện.

## 10. Dùng mock thay cho `@Import` khi nào?

Nếu chỉ cần định nghĩa kết quả trả về theo từng tình huống, không nhất thiết tạo một fake bằng `@TestConfiguration`. Với Spring Framework 6.2 trở lên, Spring Test hỗ trợ `@MockitoBean`:

```java
package com.example.shop.orders;

import com.example.shop.payments.PaymentGateway;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.BDDMockito.given;

@ApplicationModuleTest
class OrdersWithMockTest {

    @MockitoBean
    PaymentGateway paymentGateway;

    @Autowired
    OrderService orders;

    @Test
    void acceptsPaymentApprovedByMock() {
        given(paymentGateway.authorize("A-100", 5_000L))
            .willReturn(true);

        assertThat(orders.place("A-100", 5_000L))
            .isEqualTo("PLACED:A-100");
    }
}
```

Ở các stack Spring Boot cũ, có thể gặp `@MockBean`. Chọn annotation phù hợp với phiên bản thực tế của dự án.

| Nhu cầu | Cách tiếp cận |
| --- | --- |
| Fake có hành vi ổn định và được dùng lại nhiều bài test | `@Import` một `@TestConfiguration` |
| Muốn stub kết quả theo từng test/verify lời gọi | `@MockitoBean` (hoặc `@MockBean` khi stack yêu cầu) |
| Muốn một clock cố định hoặc adapter in-memory | `@TestConfiguration` và `@Import` |
| Muốn chạy code thật của module phụ thuộc | `BootstrapMode` thích hợp + hạ tầng integration test |
| Muốn kiểm tra tính hợp lệ của chiều phụ thuộc module | `ApplicationModules.verify()` |

Trong cùng một context, không nên vừa import fake vừa mock cùng một API mà không có lý do rõ ràng. Đọc test phải xác định ngay bean thực sự được dùng cho assertion là fake, mock hay adapter production.

## 11. Kiểm chứng `@Import` đã đăng ký đúng bean

Một bài kiểm thử có thể tiêm `ApplicationContext` để quan sát bean được nạp. Dưới đây là test độc lập, vẫn nhập cấu hình fake từ ví dụ ở phần 4:

```java
package com.example.shop.orders;

import com.example.shop.payments.PaymentGateway;
import com.example.shop.testsupport.FakePaymentsConfiguration;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Import;
import org.springframework.modulith.test.ApplicationModuleTest;

import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest
@Import(FakePaymentsConfiguration.class)
class ImportedBeanVisibilityTest {

    @Autowired
    ApplicationContext context;

    @Test
    void importRegistersTestGateway() {
        assertThat(context.getBeanNamesForType(PaymentGateway.class))
            .hasSize(1);

        PaymentGateway gateway = context.getBean(PaymentGateway.class);
        assertThat(gateway.authorize("OK-CHECK", 100L)).isTrue();
        assertThat(gateway.authorize("NO-CHECK", 100L)).isFalse();
    }
}
```

Assertion `hasSize(1)` giả định context chỉ có fake `PaymentGateway`, không có thêm bean cùng kiểu từ các cấu hình khác. Nếu test thực tế có nhiều bean, kiểm tra danh sách bean, `@Import`, profile và qualifier trước khi chốt kỳ vọng.

Có thể truy vấn thêm:

- `context.getBeanNamesForType(PaymentGateway.class)` để xem các bean theo type.
- `context.getBean(PaymentGateway.class).getClass()` để xem runtime class (lưu ý proxy và mock).
- `ConfigurableApplicationContext.getBeanFactory().getBeanDefinition(...)` để truy nguyên nguồn đăng ký nếu cần chẩn đoán nâng cao.

**Không suy chỉ từ kiểu Java của bean** rằng module sở hữu kiểu đó đã được bootstrap. Fake `PaymentGateway` của test có cùng interface với adapter production, nhưng mục đích và nguồn đăng ký khác nhau.

## 12. `@Import` trong kiểm thử sự kiện, dữ liệu và tích hợp

### 12.1. Kiểm thử phát sự kiện từ module

Module `orders` có thể phát `OrderPlaced` khi đặt đơn thành công. Nếu mục tiêu là xác minh payload được phát, Spring Modulith Test cung cấp `PublishedEvents` và các tiện ích `Scenario`. Một `@Import` cung cấp fake `PaymentGateway` có thể giúp đặt đơn thành công theo kịch bản mà không cần hệ thống thanh toán thật.

Nhưng event listener thuộc `notifications` không tự xuất hiện vì ta import fake gateway. Nếu cần xác minh listener thật nhận và xử lý event, hãy tạo một bài tích hợp có listener thật nằm trong context và điều kiện xử lý event phù hợp. `@Import` một fake listener chỉ chứng minh hành vi giả lập đó, không chứng minh listener production hoạt động.

### 12.2. Kiểm thử JPA/database

Một module test có thể import test configuration cung cấp database-related properties hoặc adapter in-memory. Khi kiểm thử Spring Data/JPA thật, cần bảo đảm `DataSource`, migration, transaction, schema, fixture và cleanup phù hợp. `@Import` không tự cung cấp database hay tự cô lập dữ liệu giữa các test.

Nếu import fake repository vào bài test mang tên “database integration”, test có thể chạy xanh dù JPA mapping hoặc SQL thật đang lỗi. Hãy đặt assertion và cấu hình đúng với tầng đang kiểm tra.

### 12.3. Kiểm thử phụ thuộc qua module

Nếu mục tiêu là kiểm tra contract thật giữa `orders` và `payments`, việc thay adapter bằng fake chỉ kiểm chứng cách `orders` sử dụng API. Cần thêm integration test với bean thật theo `BootstrapMode` phù hợp, hoặc contract test cho adapter. Các test này bổ trợ nhau vì chúng kiểm chứng những rủi ro khác nhau.

## 13. Kết hợp với kiểm chứng kiến trúc và quality gate CI

Một module test có `@Import` và fake đúng có thể chạy xanh trong khi code production vẫn truy cập lớp `internal` của một module khác, vi phạm ranh giới kiến trúc. Vì vậy, hãy chạy cả phép xác minh module:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ApplicationArchitectureTest {

    @Test
    void moduleDependenciesAreValid() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Phép kiểm tra này làm việc với mô hình application module và các quy tắc phụ thuộc; nó **không phải** phép khởi động Spring test context. Ngược lại, `@ApplicationModuleTest` có thể xác minh bootstrap, wiring và assertion hành vi trong context được chọn; test xanh không tự động bảo đảm mọi quan hệ module đều hợp lệ.

Một quality gate CI phù hợp gồm:

1. Chạy `ApplicationModules.verify()` để phát hiện phụ thuộc sai chiều hoặc truy cập trái quy tắc module.
2. Chạy các module test ở phạm vi nhỏ với `@Import`/mock hợp lý để kiểm chứng logic cốt lõi.
3. Chạy integration test trọng yếu để kiểm chứng adapter thật, cơ sở dữ liệu, giao dịch và xử lý event.
4. Gắn từng lỗi với tầng cần sửa: sai phụ thuộc kiến trúc, lỗi tạo bean/configuration, hay hồi quy hành vi/tích hợp.

Việc cấu hình CI cụ thể phụ thuộc Maven/Gradle, môi trường test và cách dự án chia test suite. Điều quan trọng là mọi lớp test mang trách nhiệm rõ ràng, tránh để fake che khuất lỗi trong luồng tích hợp thật.

## 14. Quy trình chẩn đoán khi dùng `@Import`

Khi test không khởi động hoặc cho kết quả khác kỳ vọng, lần lượt kiểm tra:

1. **Module đích:** lớp test thuộc package nào? `@ApplicationModuleTest` đang nhận diện module gì?
2. **Bootstrap mode:** có đang dùng `STANDALONE` hay đã thêm module phụ thuộc?
3. **Vị trí cấu hình:** class test configuration là nested `static` hay top-level? Với top-level, `@Import` đã chỉ đúng class chưa?
4. **Các bean được đăng ký:** phương thức `@Bean` có thực sự được kích hoạt không? Có `@Profile`/`@Conditional` ngăn bean xuất hiện không?
5. **Trùng bean:** context có nhiều bean cùng type/tên không? Một `@Primary`, `@Qualifier` hay mock override có đang quyết định bean nào được tiêm?
6. **Phụ thuộc bắc cầu:** bean được import cần thêm database, HTTP client hoặc listener nào?
7. **Mục tiêu test:** assertion đang chạy trên service thật + fake, hay đang yêu cầu tương tác thật giữa các module?
8. **Ranh giới kiến trúc:** `ApplicationModules.verify()` có chạy và phát hiện phụ thuộc production nào sai không?

### Ngộ nhận thường gặp

| Ngộ nhận | Giải thích chính xác |
| --- | --- |
| “`@Import` đổi `STANDALONE` thành `ALL_DEPENDENCIES`.” | `@Import` chỉ đưa cấu hình/bean chỉ định vào test context; mode vẫn do `@ApplicationModuleTest` quyết định. |
| “Class top-level `@TestConfiguration` trong `src/test/java` tự động được nạp.” | Thường cần `@Import` tường minh; khác với nested `static @TestConfiguration`. |
| “Có `PaymentGateway` là đã bootstrap module `payments`.” | Bean có thể là fake hoặc mock được đăng ký từ test. |
| “`@Import` bất kỳ cấu hình production nào cũng an toàn cho module test.” | Một cấu hình production có thể kéo thêm scan, adapter, repository và side effect ngoài dự định. |
| “`@Primary` xóa bean production.” | Nó chỉ ưu tiên candidate cho injection khi phù hợp; không xóa bean cũ. |
| “Module test với fake chạy xanh là chứng minh được toàn bộ kiến trúc.” | Cần kiểm chứng riêng bằng `ApplicationModules.verify()` và integration test cho các luồng thật. |

## 15. Bài tập tự kiểm tra

Với module `orders` phụ thuộc API `PaymentGateway` của `payments`, hãy trả lời:

1. Tại sao `@ApplicationModuleTest` ở `STANDALONE` có thể báo thiếu bean `PaymentGateway` dù project có class `RemotePaymentGateway`?
2. Khi `FakePaymentsConfiguration` là top-level class trong `src/test/java`, thêm annotation nào để module test dùng được fake?
3. Nếu class cấu hình là `static nested @TestConfiguration`, có luôn cần `@Import` không?
4. `@Import(FakePaymentsConfiguration.class)` có làm `orders` được phép truy cập package internal của `payments` không?
5. Nếu chuyển sang `DIRECT_DEPENDENCIES` mà vẫn import fake cùng interface với implementation thật, cần chú ý vấn đề gì?
6. Nếu một bài test cần kiểm chứng listener thật của `notifications` xử lý `OrderPlaced`, import fake `PaymentGateway` đã đủ chưa?
7. Hai nhóm kiểm tra nào nên cùng xuất hiện trong CI để vừa bắt lỗi kiến trúc vừa bắt lỗi runtime/integration?

**Đáp án gợi ý:** (1) `STANDALONE` không tự nạp bean nghiệp vụ của module ngoài, mặc dù class có trên classpath; (2) `@Import(FakePaymentsConfiguration.class)`; (3) thông thường không, Spring Boot test tự nhận diện cấu hình lồng tĩnh; (4) không, quy tắc kiến trúc độc lập với cấu hình bổ sung trong test; (5) có thể xảy ra trùng bean hoặc tiêm nhầm fake, cần xác định rõ bean được dùng; (6) chưa, phải có listener thật trong context và assertion của luồng xử lý; (7) `ApplicationModules.verify()` cùng module test/integration test với assertion rõ ràng.

**Ghi nhớ:** `@Import` là cách **đăng ký tường minh bean/cấu hình bổ trợ trong test context**. `BootstrapMode` chọn **tập application module** mà bài test bootstrap. `ApplicationModules.verify()` kiểm chứng **quy tắc kiến trúc**. Giữ ba tầng này tách bạch giúp kiểm thử module ổn định, dễ chẩn đoán và có giá trị trong quality gate CI.
