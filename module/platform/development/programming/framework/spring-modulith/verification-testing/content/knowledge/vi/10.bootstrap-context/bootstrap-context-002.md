# Bean trong module mục tiêu và bean bên ngoài

## 1. Vì sao cần phân biệt hai nhóm bean?

Khi kiểm thử bằng `@ApplicationModuleTest`, một câu hỏi quan trọng hơn “Spring Boot có khởi động được không?” là **bean nào thực sự nằm trong `ApplicationContext` của bài kiểm thử và bean đó đến từ đâu?** Phân biệt được bean thuộc module mục tiêu, bean của module khác và bean hạ tầng sẽ giúp ta phát hiện phụ thuộc ẩn, lựa chọn đúng phạm vi kiểm thử và tránh để một bài module test vô tình trở thành kiểm thử toàn ứng dụng.

Trong Spring Modulith, **module ứng dụng** (application module) là một đơn vị kiến trúc được nhận diện từ cấu trúc package và cấu hình module. **Spring bean** là một đối tượng do IoC container quản lý. Hai khái niệm có liên hệ nhưng không đồng nhất:

- Một module có thể chứa nhiều bean, nhưng cũng có các lớp thông thường như record, enum, entity, event và value object **không phải bean**.
- Một `ApplicationContext` cho module test có thể chứa bean từ module mục tiêu cùng với bean hạ tầng do Spring Boot, Spring Framework hoặc cấu hình kiểm thử đăng ký.
- Bean từ module khác chỉ được đưa vào phạm vi bootstrap khi cấu hình cho phép hoặc được thêm vào qua cơ chế cấu hình/test. Không nên suy từ việc class có trên classpath rằng Spring đã đăng ký nó thành bean.

Trong module học **SPRING_MODULITH_VERIFICATION_TESTING**, hiểu rõ nguồn gốc bean là nền tảng để thực hành `@ApplicationModuleTest`, kiểm thử dữ liệu/sự kiện và ghép kết quả với `ApplicationModules.verify()` thành quality gate CI bảo vệ ranh giới kiến trúc.

## 2. Nhìn vào cấu trúc module trước khi nhìn vào context

Giả sử ứng dụng bán hàng có package gốc `com.example.shop`:

```text
com.example.shop
├── ShopApplication.java                 // @SpringBootApplication
├── orders/                              // module orders: module mục tiêu
│   ├── OrderApplicationService.java     // @Service
│   ├── OrderNumberGenerator.java        // @Component
│   ├── OrderPlaced.java                 // record sự kiện, không phải bean
│   └── OrderConfiguration.java          // @Configuration, cung cấp @Bean
├── inventory/                           // module inventory: module khác
│   ├── ProductCatalog.java              // public API (interface)
│   └── DatabaseProductCatalog.java      // @Service triển khai API
└── notifications/                       // module notifications: module khác
    └── OrderPlacedListener.java         // @ApplicationModuleListener

src/test/java/com/example/shop/orders/
└── OrdersModuleTest.java                // @ApplicationModuleTest
```

Với cách nhận diện module theo các package con trực tiếp của package gốc, `orders`, `inventory` và `notifications` là ba module ứng dụng. Vì `OrdersModuleTest` ở package `com.example.shop.orders`, **`orders` là module mục tiêu**. Giả sử mã trong `orders` tham chiếu API của `inventory`, đồ thị phụ thuộc kiến trúc có thể biểu diễn:

```mermaid
flowchart LR
    O[orders] -->|sử dụng ProductCatalog| I[inventory]
    N[notifications] -.->|nhận OrderPlaced| O
```

Mũi tên liền thể hiện phụ thuộc code từ `orders` đến `inventory`. Mũi tên nét đứt diễn tả ý tưởng xử lý sự kiện ở `notifications`, **không hàm ý rằng `notifications` được nạp vào context của một bài test `orders`**. Một event có thể đi qua nhiều module ở runtime nhưng phạm vi bootstrap của bài test vẫn cần được quyết định rõ ràng.

## 3. Bean thuộc module mục tiêu

Ở chế độ mặc định `STANDALONE`, Spring Modulith hướng việc bootstrap vào **module chứa lớp test**. Những thành phần Spring của `orders` có thể được đăng ký thông qua các cơ chế thông thường: `@Component`, `@Service`, `@Repository`, bean được khai báo từ `@Configuration`/`@Bean`, hoặc các cơ chế đăng ký tương thích với cấu hình hiện hành. Thực tế bean nào có mặt vẫn tùy thuộc điều kiện, profile, auto-configuration, component scanning và các dependency cần thiết để bean khởi tạo thành công.

Ví dụ một bean thuần nội bộ:

```java
package com.example.shop.orders;

import org.springframework.stereotype.Component;

@Component
class OrderNumberGenerator {

    String nextFor(long sequence) {
        return "ORD-" + sequence;
    }
}
```

Và một cấu hình do module `orders` sở hữu:

```java
package com.example.shop.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import java.time.Clock;

@Configuration(proxyBeanMethods = false)
class OrderConfiguration {

    @Bean
    Clock orderClock() {
        return Clock.systemUTC();
    }
}
```

`OrderNumberGenerator` là bean vì có `@Component`. `Clock` là bean vì được tạo bởi `@Bean` trong cấu hình thuộc `orders`. **Bản thân `Clock` thuộc thư viện Java, không có package `orders`; quyền sở hữu bean được xác định từ cấu hình đăng ký nó**, chứ không thể suy đơn giản từ package của kiểu đối tượng trả về.

Ngược lại, một `record OrderPlaced(String orderId)` chỉ là kiểu dữ liệu và **không tự trở thành bean**. Khi được phát ra dưới dạng application event, record đó vẫn là đối tượng sự kiện, không cần Spring quản lý như singleton bean.

Đừng hiểu `STANDALONE` thành “mọi lớp trong package đều được tạo”. Spring chỉ tạo những bean thỏa các điều kiện đăng ký của IoC container; một entity JPA, một POJO hay interface thường không có bean chỉ vì chúng nằm trong package module.

## 4. Bean bên ngoài module mục tiêu có những loại nào?

Nhóm “bên ngoài” cần chia nhỏ trước khi quyết định có phải lỗi ranh giới hay không:

| Loại bean | Ví dụ | Vì sao có thể xuất hiện trong module test? |
| --- | --- | --- |
| Bean nghiệp vụ thuộc **module khác** | `DatabaseProductCatalog` của `inventory` | Được đưa vào khi mở rộng `BootstrapMode` thích hợp, hoặc được đăng ký rõ ràng qua cấu hình bổ sung. |
| Bean **hạ tầng framework** | `ApplicationContext`, transaction infrastructure, các bean auto-configuration của Boot | Là hạ tầng Spring/Test cần cho phần ứng dụng được kiểm thử; không nhất thiết thuộc một application module nghiệp vụ. |
| Bean do **test cung cấp** | Mock `ProductCatalog`, bean của `@TestConfiguration` | Có mặt vì bài test chủ động tạo hoặc thay thế cộng tác viên để cô lập hành vi. |
| Bean của **cấu hình bên ngoài phạm vi mong đợi** | Bean do `@Import` thủ công hoặc cấu hình quét quá rộng | Có thể xuất hiện ngoài ý định và cần kiểm tra lại lựa chọn cấu hình. |

Vì vậy, kết luận “context chứa bean có class ngoài package `orders` nên module test bị hỏng” là **quá vội**. Một `DataSource` hoặc `Clock` được tạo từ cấu hình thích hợp không giống với việc nạp toàn bộ service nghiệp vụ của module `inventory`.

Đồng thời, việc `orders` *được phép* phụ thuộc `inventory` theo quy tắc kiến trúc không có nghĩa mọi test `orders` **tự động** phải nạp bean thật của `inventory`. Quyền phụ thuộc ở mức thiết kế và việc nạp bean ở runtime là hai quyết định khác nhau.

## 5. `BootstrapMode` quyết định module nghiệp vụ nào được nạp

`@ApplicationModuleTest` hỗ trợ ba chế độ bootstrap:

| Chế độ | Các module ứng dụng được chọn khi test `orders` | Tác động đối với bean bên ngoài |
| --- | --- | --- |
| `STANDALONE` (mặc định) | `orders` | Bean nghiệp vụ do `inventory` hoặc `notifications` sở hữu không tự được nạp chỉ vì tồn tại trên classpath. |
| `DIRECT_DEPENDENCIES` | `orders` và các module mà `orders` phụ thuộc trực tiếp | Có thể bao gồm `inventory` nếu `orders → inventory`; không đồng nghĩa nạp cả ứng dụng. |
| `ALL_DEPENDENCIES` | `orders` và mọi module nó phụ thuộc trực tiếp/gián tiếp | Phù hợp khi cần một chuỗi cộng tác viên thật xuyên nhiều module; vẫn không bao gồm module không nằm trong tập phụ thuộc đã chọn. |

```java
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.ApplicationModuleTest.BootstrapMode;

// Chỉ các bean nghiệp vụ của module orders được chọn.
@ApplicationModuleTest
class OrdersIsolatedTest {
}

// Bao gồm orders và các module orders sử dụng trực tiếp.
@ApplicationModuleTest(mode = BootstrapMode.DIRECT_DEPENDENCIES)
class OrdersWithInventoryTest {
}

// Bao gồm cả chuỗi phụ thuộc bắc cầu của orders.
@ApplicationModuleTest(mode = BootstrapMode.ALL_DEPENDENCIES)
class OrdersWithTransitiveDependenciesTest {
}
```

Đây là ba khai báo minh họa **phạm vi bootstrap**, chưa phải test nghiệp vụ hoàn chỉnh. Khái niệm *dependency* ở đây là quan hệ giữa **application module** được Spring Modulith phân tích, không phải thuật toán Spring tùy ý lần theo mọi constructor rồi mở rộng context đến khi hết thiếu bean.

Đặc biệt lưu ý chiều phụ thuộc: nếu `notifications` lắng nghe event từ `orders`, điều đó không mặc định khiến `notifications` trở thành một **module phụ thuộc của `orders`**. Muốn kiểm thử listener thật, cần một phạm vi integration test có nạp listener hoặc một bài module test riêng trong `notifications`.

## 6. Ví dụ: Service của module mục tiêu cần bean từ module khác

Giả sử module `inventory` công bố API như sau:

```java
package com.example.shop.inventory;

public interface ProductCatalog {
    boolean exists(String sku);
}
```

Module `orders` sử dụng API đó qua constructor injection:

```java
package com.example.shop.orders;

import com.example.shop.inventory.ProductCatalog;
import org.springframework.stereotype.Service;

@Service
class OrderApplicationService {

    private final ProductCatalog catalog;

    OrderApplicationService(ProductCatalog catalog) {
        this.catalog = catalog;
    }

    String place(String sku) {
        if (!catalog.exists(sku)) {
            throw new IllegalArgumentException("Unknown SKU: " + sku);
        }
        return "ORDERED:" + sku;
    }
}
```

Giả sử `inventory` có implementation `@Service` tên `DatabaseProductCatalog`. Trong `STANDALONE`, bean `OrderApplicationService` có thể được chọn nhưng implementation thuộc `inventory` lại không. Khi không có bean thay thế nào cho `ProductCatalog`, Spring sẽ không thỏa được constructor của `OrderApplicationService`, thường dẫn tới `UnsatisfiedDependencyException` trong giai đoạn khởi động context, **trước lúc chạy assertion**.

Lỗi này không nhất thiết có nghĩa thiết kế phụ thuộc là sai: nó thường chỉ ra rằng **bài kiểm thử đang cần quyết định rõ cách xử lý ranh giới module**.

### Cách A — Dùng test double cho API bên ngoài khi kiểm thử `orders`

Ví dụ sau áp dụng với các phiên bản Spring Framework hỗ trợ `@MockitoBean` (Spring Framework 6.2 trở lên); các dự án Spring Boot cũ hơn thường dùng `@MockBean`:

```java
package com.example.shop.orders;

import com.example.shop.inventory.ProductCatalog;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.BDDMockito.given;

@ApplicationModuleTest // STANDALONE
class OrdersModuleTest {

    @MockitoBean
    ProductCatalog productCatalog;

    @Autowired
    OrderApplicationService orders;

    @Test
    void acceptsExistingProduct() {
        given(productCatalog.exists("SKU-1")).willReturn(true);

        assertThat(orders.place("SKU-1")).isEqualTo("ORDERED:SKU-1");
    }

    @Test
    void rejectsUnknownProduct() {
        given(productCatalog.exists("SKU-X")).willReturn(false);

        assertThatThrownBy(() -> orders.place("SKU-X"))
            .isInstanceOf(IllegalArgumentException.class)
            .hasMessageContaining("SKU-X");
    }
}
```

Trong ví dụ này:

1. `orders` vẫn là module ứng dụng được bootstrap ở chế độ mặc định.
2. Bean `OrderApplicationService` là đối tượng thật cần kiểm thử.
3. `ProductCatalog` là **bean mock nằm trong context test**, nhưng mock đó không có nghĩa implementation thật `DatabaseProductCatalog` của `inventory` đã được nạp.
4. Assertion kiểm chứng quy tắc xử lý đơn hàng trong điều kiện cụ thể, không đòi hỏi database hay module `inventory` thật.

Đây là lựa chọn phù hợp khi mục đích là kiểm thử **hành vi của module mục tiêu tại ranh giới**. Mock phải mô phỏng những trường hợp có ý nghĩa, tránh chỉ xác nhận test đã được gọi mà không kiểm chứng kết quả.

### Cách B — Dùng bean thật của module phụ thuộc khi kiểm thử tích hợp

Nếu mục tiêu là kiểm chứng `OrderApplicationService` tương tác với implementation của `ProductCatalog`, có thể mở rộng phạm vi:

```java
package com.example.shop.orders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.modulith.test.ApplicationModuleTest;
import org.springframework.modulith.test.ApplicationModuleTest.BootstrapMode;

@ApplicationModuleTest(mode = BootstrapMode.DIRECT_DEPENDENCIES)
class OrdersInventoryIntegrationTest {

    @Autowired
    OrderApplicationService orders;

    @Test
    void integratesWithInventory() {
        // Chuẩn bị dữ liệu inventory bằng fixture/repository/test setup.
        // Sau đó thực thi orders.place(...) và kiểm tra kết quả thật.
    }
}
```

Ví dụ trên có ý nghĩa khi `inventory` thực sự là module phụ thuộc trực tiếp đã được Spring Modulith nhận diện và cấu hình hạ tầng test đủ để các bean trong đó khởi tạo. Nếu `DatabaseProductCatalog` truy cập JPA repository, cần cả DataSource, schema và dữ liệu kiểm thử phù hợp. Dùng `DIRECT_DEPENDENCIES` **không tự chuẩn bị database hoặc fixture**. Phương thức `@Test` ở đây là khung minh họa; bài tích hợp thực tế phải có assertion và chuẩn bị dữ liệu cụ thể.

## 7. Cách quan sát bean thực tế trong `ApplicationContext`

Không cần đoán thành phần nào đã được nạp. Có thể tiêm `ApplicationContext` và hỏi Spring về bean theo kiểu:

```java
package com.example.shop.orders;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.ApplicationContext;
import org.springframework.modulith.test.ApplicationModuleTest;

import static org.assertj.core.api.Assertions.assertThat;

@ApplicationModuleTest
class OrdersBeanInventoryTest {

    @Autowired
    ApplicationContext context;

    @Autowired
    OrderNumberGenerator numbers;

    @Test
    void moduleOwnedBeanIsPresent() {
        assertThat(context.getBeanNamesForType(OrderNumberGenerator.class))
            .isNotEmpty();
        assertThat(numbers.nextFor(7)).isEqualTo("ORD-7");
    }
}
```

Đối với ví dụ `OrderApplicationService` cần `ProductCatalog`, phải cung cấp mock hoặc mở rộng chế độ bootstrap **trước khi** context có thể khởi động; một assertion trong `@Test` không giúp xử lý lỗi thiếu bean xảy ra trước đó.

Khi kiểm tra cụ thể một collaborator, đừng chỉ dùng `containsBean("productCatalog")` rồi kết luận implementation thật đã hiện diện. Bean đó có thể là mock/test double. Cần xác minh nguồn cấu hình và, nếu có mock, có thể dùng `org.mockito.Mockito.mockingDetails(bean).isMock()` để phân biệt. Tương tự, `context.getBeanDefinitionNames().length` chỉ phản ánh tổng bean, **không phải số module**: con số này thường tăng vì auto-configuration hoặc Spring Test.

Những điều cần ghi nhận khi đọc log và kiểm tra context:

| Quan sát | Câu hỏi cần đặt |
| --- | --- |
| Có bean nghiệp vụ `orders` | Bean được chọn từ component scan, `@Bean` hay import nào? Các profile/conditional có đang bật không? |
| Không có bean `inventory` | Context đang `STANDALONE` hay `inventory` chưa được nhận diện là phụ thuộc của `orders`? |
| Có `ProductCatalog` nhưng logic tích hợp không chạy | Bean là mock hay implementation thật? Có cấu hình override ở test không? |
| Có `DataSource` hoặc transaction manager | Đây là hạ tầng test/framework; database/transaction được cấu hình ra sao? |
| Có service ngoài phạm vi dự định | `@Import`, `@TestConfiguration`, component scanning hoặc bootstrap mode có mở rộng phạm vi không? |

## 8. Các tình huống dễ nhầm khi kiểm thử sự kiện, dữ liệu và tích hợp

### Sự kiện được phát ra nhưng listener ở module khác không chạy

`OrderPlaced` chỉ là payload của event. Nếu một bean thuộc `orders` dùng `ApplicationEventPublisher` để phát sự kiện, module test có thể kiểm tra **việc phát sự kiện** bằng các tiện ích trong Spring Modulith Test, chẳng hạn `PublishedEvents`. Tuy nhiên, listener `OrderPlacedListener` của `notifications` chỉ thực thi khi **bean listener đã được đăng ký trong context** (và các điều kiện giao dịch/xử lý sự kiện thỏa mãn). Một event đi qua context không tự động làm xuất hiện listener ở module chưa được bootstrap.

Vì vậy, có thể tách hai cấp kiểm thử: một module test xác nhận `orders` phát `OrderPlaced` đúng dữ liệu; một integration test có listener thật để xác nhận tác động ở `notifications`. Cách tách này giúp định vị lỗi là do nguồn phát, cấu hình listener hay tương tác liên module.

### Module test có JPA repository nhưng database chưa sẵn sàng

Repository của `orders` có thể được tạo thành bean khi cấu hình Spring Data tương ứng hoạt động. Nhưng **bean repository tồn tại** không đồng nghĩa database đã được seed đúng, migration đã chạy hay từng test được cô lập dữ liệu. Profile test, Testcontainers, schema, transaction và cách dọn dữ liệu cần được cấu hình có chủ đích. Nếu chỉ kiểm thử quy tắc tính toán độc lập với lưu trữ, không cần mở rộng context để buộc kéo theo database thật.

### Bean ngoài xuất hiện qua cấu hình kiểm thử

`@TestConfiguration` hoặc `@Import` có thể cố ý cung cấp fake clock, fake gateway hoặc bean phục vụ test. Chúng hữu ích để kiểm soát điều kiện kiểm thử, nhưng nếu import cả một configuration của module khác, bài test có thể phụ thuộc nhiều thành phần hơn dự kiến. Sau khi thêm test configuration, cần xem lại mục tiêu của bài test và lý do từng bean bên ngoài được đưa vào.

## 9. Context khởi động thành công chưa đủ chứng minh kiến trúc đúng

Một module test có thể chạy xanh vì đã mock mọi cộng tác viên, trong khi code thực tế lại có phụ thuộc trái quy tắc vào nội bộ module khác. Ngược lại, `ApplicationModules.verify()` có thể xác nhận các ranh giới kiến trúc hợp lệ nhưng không biết DataSource hay bean test đang cấu hình sai. Hai tầng kiểm chứng giải quyết **hai vấn đề khác nhau**:

```java
import com.example.shop.ShopApplication;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ApplicationArchitectureTest {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

| Tầng kiểm chứng | Chứng minh điều gì? | Không tự chứng minh điều gì? |
| --- | --- | --- |
| `ApplicationModules.verify()` | Các phụ thuộc giữa module tuân thủ ranh giới và quy tắc được mô hình Spring Modulith áp dụng. | Spring bean khởi tạo được, kết nối dữ liệu hoạt động, event listener xử lý đúng. |
| `@ApplicationModuleTest` ở `STANDALONE` | Module mục tiêu có thể bootstrap với cộng tác viên test cần thiết; hành vi nội bộ đúng theo assertion. | Bean thật của module phụ thuộc và toàn bộ luồng tích hợp đều chạy đúng. |
| Module test mở rộng hoặc bài integration test | Wiring và hành vi qua những module có mặt trong context, theo tình huống kiểm thử cụ thể. | Mọi phụ thuộc tĩnh của tất cả module đều tuân thủ quy tắc kiến trúc. |

Trong CI, nên chạy một bài kiểm tra kiến trúc cùng các module test có assertion nghiệp vụ và các kiểm thử tích hợp thiết yếu. Khi CI báo lỗi `ApplicationModules.verify()`, tập trung vào quan hệ phụ thuộc giữa module; khi báo `UnsatisfiedDependencyException` ở module test, kiểm tra **nguồn gốc bean và phạm vi bootstrap**; khi assertion xử lý dữ liệu/sự kiện thất bại, kiểm tra fixture, transaction và listener có mặt trong context hay không.

## 10. Quy trình xử lý sự cố thiếu hoặc thừa bean

1. **Định vị module mục tiêu:** xác nhận package của test và cách ứng dụng định nghĩa application module.
2. **Kiểm tra bootstrap mode:** đọc `@ApplicationModuleTest` xem đang chọn `STANDALONE`, `DIRECT_DEPENDENCIES` hay `ALL_DEPENDENCIES`.
3. **Phân loại bean cần tìm:** nó thuộc module mục tiêu, module phụ thuộc, Spring Boot infrastructure hay cấu hình riêng của test?
4. **Xem constructor và nguyên nhân lỗi gốc:** bean thiếu là một API module khác, bean hạ tầng hay chỉ thiếu fixture/cấu hình?
5. **Chọn cách xử lý có chủ đích:** giữ context cô lập với mock, nạp module phụ thuộc thật, hoặc bổ sung hạ tầng test. Tránh mở rộng toàn bộ ứng dụng chỉ để lấp một lỗi chưa được phân tích.
6. **Khẳng định bằng assertion:** kiểm thử hành vi của bean thật, xác minh mock được cấu hình, kiểm tra sự kiện hoặc tác động dữ liệu khi cần.
7. **Kiểm tra lại ranh giới bằng `ApplicationModules.verify()`:** một cách xử lý lỗi Spring context không được âm thầm hợp thức hóa phụ thuộc code sai kiến trúc.

### Bảng ngộ nhận thường gặp

| Ngộ nhận | Hiểu đúng |
| --- | --- |
| “Class nằm trong module nên chắc chắn có bean.” | Chỉ những class/đối tượng được Spring đăng ký theo cấu hình tương ứng mới là bean. |
| “Class ở ngoài module tức là bean sai ranh giới.” | Bean hạ tầng và bean test có thể hợp lệ; cần xét **nguồn đăng ký và mục đích**. |
| “Có bean `ProductCatalog` nghĩa là `inventory` đã được nạp.” | Bean đó có thể là mock chỉ tồn tại trong test. |
| “`DIRECT_DEPENDENCIES` luôn giải quyết mọi `UnsatisfiedDependencyException`.” | Chỉ thêm module phụ thuộc trực tiếp; lỗi có thể đến từ phụ thuộc bắc cầu, thiếu cấu hình hoặc hạ tầng. |
| “Listener ở module khác sẽ luôn nhận event.” | Bean listener phải nằm trong context và thỏa điều kiện xử lý. |
| “Module test khởi động được thì kiến trúc đã hợp lệ.” | Cần phép kiểm chứng quy tắc riêng bằng `ApplicationModules.verify()`. |

## 11. Câu hỏi tự luyện

Xét ứng dụng mẫu: `orders` sử dụng API `ProductCatalog` từ `inventory`; `notifications` xử lý event `OrderPlaced` từ `orders`; `orders` có `OrderNumberGenerator` và một `@Bean Clock` trong `OrderConfiguration`.

1. Khi test `orders` ở `STANDALONE`, bean `OrderNumberGenerator` và `Clock` có thể có mặt không? Vì sao?
2. `OrderPlaced` là một record không có annotation Spring. Nó có phải bean của context không?
3. Nếu `OrderApplicationService` yêu cầu `ProductCatalog` qua constructor nhưng `inventory` không được bootstrap, điều gì xảy ra khi thiếu mock?
4. Khi cung cấp `@MockitoBean ProductCatalog`, có thể kết luận implementation thật từ `inventory` đã xuất hiện không?
5. Cần loại bài kiểm thử nào để xác nhận `notifications` thật sự xử lý event? `ApplicationModules.verify()` có thay thế được bài đó không?
6. Vì sao một context có `DataSource` không đủ để kết luận module test đã nạp toàn bộ ứng dụng?

**Gợi ý đáp án:** (1) Có nếu Spring đăng ký các bean tương ứng và dependency/conditional cho phép, vì `OrderNumberGenerator` và `OrderConfiguration` thuộc module mục tiêu; (2) không, record chỉ là kiểu dữ liệu/sự kiện; (3) thường lỗi khởi động context do thiếu dependency; (4) không, đó là bean mock trong test; (5) cần test với listener thật nằm trong context, phép kiểm tra kiến trúc không thay assertion hành vi; (6) `DataSource` là bean hạ tầng có thể được Boot cấu hình phục vụ module được chọn.

**Ghi nhớ:** khi đánh giá một bean trong `@ApplicationModuleTest`, luôn hỏi ba điều: **bean do ai sở hữu/đăng ký, module nào đang được bootstrap và bài kiểm thử muốn kiểm chứng ranh giới nào?** Trả lời được ba câu hỏi này sẽ giúp chọn mock, bean thật và quality gate đúng mục đích, tránh cả việc kiểm thử quá cô lập lẫn việc vô tình kéo toàn bộ phụ thuộc vào một module test.
