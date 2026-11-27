# Kiểm thử model sau khi đổi package

Đổi package của một application module là một thao tác refactor mã nguồn, nhưng nó cũng có thể làm thay đổi module model mà Spring Modulith phát hiện. Sau khi di chuyển package, cần xác nhận module vẫn được phát hiện dưới đúng root, logical identifier vẫn giữ nguyên, named interface còn được công khai và dependency graph vẫn hợp lệ.

Trong bài thực hành này, bạn sẽ chuyển module đơn hàng từ `com.acme.shop.order` sang `com.acme.shop.orders`. Module đã có logical identifier tường minh `order-management`, vì vậy consumer tiếp tục tham chiếu `order-management::events`. Bạn sẽ viết architecture test bằng `ApplicationModules` để kiểm tra module model sau refactor.

Sau khi hoàn thành, bạn có thể:

- Di chuyển package module và cập nhật package declaration, imports.
- Giữ logical identifier ổn định trong lúc đổi package.
- Kiểm tra module detection và base package mới.
- Tra cứu module bằng identifier và bằng type.
- Kiểm tra named interface và `allowedDependencies` thông qua `verify()`.
- Nhận diện lỗi do package metadata cũ hoặc dependency reference sai.
- Đưa architecture test vào bộ kiểm thử để bảo vệ các lần refactor sau.

## 1. Kịch bản thực hành

Ứng dụng bán hàng có ba module:

| Module | Trách nhiệm | Hợp đồng liên module |
|---|---|---|
| `catalog` | Quản lý sản phẩm | `catalog::api` |
| `order` / `orders` | Tạo đơn và phát sự kiện đơn hàng | `order-management::events` |
| `inventory` | Theo dõi tồn kho và giữ hàng | Sử dụng event từ `order-management::events` |

Nhóm phát triển muốn đổi tên package `com.acme.shop.order` thành `com.acme.shop.orders` để thống nhất quy ước số nhiều với các module khác. Module đã có identifier tường minh `order-management`.

Trước refactor:

~~~text
com.acme.shop
├── ShopApplication.java
├── catalog
│   └── api
├── order
│   ├── package-info.java
│   ├── OrderService.java
│   └── events
│       ├── package-info.java
│       └── OrderPlaced.java
└── inventory
    ├── package-info.java
    └── InventoryListener.java
~~~

Sau refactor:

~~~text
com.acme.shop
├── ShopApplication.java
├── catalog
│   └── api
├── orders
│   ├── package-info.java
│   ├── OrderService.java
│   └── events
│       ├── package-info.java
│       └── OrderPlaced.java
└── inventory
    ├── package-info.java
    └── InventoryListener.java
~~~

Package thay đổi từ `com.acme.shop.order` sang `com.acme.shop.orders`. Logical identifier vẫn là `order-management`, named interface vẫn là `events`, và module inventory tiếp tục sử dụng `order-management::events`.

Dependency graph theo hướng code:

~~~mermaid
flowchart LR
    inventory["inventory"] -->|"order-management::events"| orders["orders"]
    orders -->|"catalog::api"| catalog["catalog"]
~~~

Đồ thị này không có chu trình. `inventory` phụ thuộc kiểu event do `orders` sở hữu; `orders` phụ thuộc API sản phẩm do `catalog` công khai.

## 2. Chuẩn bị dependency kiểm thử

Ví dụ dùng Maven. Import Spring Modulith BOM và khai báo core cùng test starter:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.modulith</groupId>
            <artifactId>spring-modulith-bom</artifactId>
            <version>2.2.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-core</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springframework.modulith</groupId>
        <artifactId>spring-modulith-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

Trong đó:

- `spring-modulith-starter-core` cung cấp module model và API phân tích cấu trúc.
- `spring-modulith-starter-test` cung cấp các tiện ích kiểm thử module nếu bài tập mở rộng dùng `@ApplicationModuleTest`.
- `spring-boot-starter-test` cung cấp JUnit và AssertJ cho architecture test.

Nếu dự án đã quản lý BOM ở parent POM hoặc build convention, giữ cấu hình hiện có và chỉ bảo đảm các dependency Modulith cùng version train.

## 3. Xác nhận application root

Lớp Spring Boot application nằm ở package gốc `com.acme.shop`:

~~~java
package com.acme.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Với detection strategy mặc định `direct-subpackages`, Spring Modulith phát hiện các package con trực tiếp `catalog`, `order` hoặc `orders`, và `inventory` thành module. Khi di chuyển package, giữ nó dưới root này để không làm thay đổi phạm vi detection.

Nếu bạn đồng thời di chuyển module sang một root package khác, cần xem lại `@Modulithic(additionalPackages = ...)`, detection strategy và lớp được truyền vào `ApplicationModules.of(...)`. Bài thực hành này chỉ thay package của một module bên trong cùng application root.

## 4. Ghi nhận metadata trước khi di chuyển

Giả sử package cũ `com.acme.shop.order` đã khai báo identifier ổn định:

~~~java
@org.springframework.modulith.ApplicationModule(
        id = "order-management"
)
package com.acme.shop.order;
~~~

Named interface chứa event:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.order.events;
~~~

Module inventory tham chiếu event contract:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "order-management::events"
)
package com.acme.shop.inventory;
~~~

Module orders sử dụng public API của catalog:

~~~java
@org.springframework.modulith.ApplicationModule(
        id = "order-management",
        allowedDependencies = "catalog::api"
)
package com.acme.shop.order;
~~~

Package API của catalog được công khai bằng named interface:

~~~java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.catalog.api;
~~~

Hợp đồng tối thiểu mà orders sử dụng:

~~~java
package com.acme.shop.catalog.api;

import java.util.Optional;

public interface ProductCatalog {

    Optional<String> findById(String productId);
}
~~~

Ghi nhận các giá trị trước refactor:

| Thuộc tính | Trước refactor |
|---|---|
| Base package | `com.acme.shop.order` |
| Identifier | `order-management` |
| Named interface | `events` |
| Consumer | `inventory` |
| Dependency reference | `order-management::events` |

Nếu module chưa có `id` tường minh, hãy quyết định identifier ổn định trước khi di chuyển package. Nếu giữ identifier mặc định, package rename có thể làm tên module thay đổi và buộc consumer cập nhật dependency reference. Việc thêm `id` là một quyết định metadata; nó không tự di chuyển source file.

## 5. Di chuyển package và cập nhật metadata

Di chuyển toàn bộ nội dung của module từ:

~~~text
src/main/java/com/acme/shop/order/
~~~

sang:

~~~text
src/main/java/com/acme/shop/orders/
~~~

Bao gồm:

- `package-info.java` của module.
- `OrderService.java` và các type trong package gốc.
- Package con `events` cùng `package-info.java` của named interface.
- Các package con khác thuộc module nếu có.

Sau khi di chuyển, cập nhật package declaration của module:

~~~java
@org.springframework.modulith.ApplicationModule(
        id = "order-management",
        allowedDependencies = "catalog::api"
)
package com.acme.shop.orders;
~~~

Cập nhật named interface:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.orders.events;
~~~

Giữ nguyên package metadata của inventory:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "order-management::events"
)
package com.acme.shop.inventory;
~~~

Lý do không cần sửa dependency reference là inventory sử dụng logical identifier `order-management`, không sử dụng package name `com.acme.shop.order`. Tên package của event class thay đổi nên Java imports trong consumer vẫn phải được cập nhật.

## 6. Cập nhật type và imports sau khi di chuyển

Event `OrderPlaced` nằm trong package mới:

~~~java
package com.acme.shop.orders.events;

public record OrderPlaced(
        String orderId,
        String productId,
        int quantity
) {
}
~~~

Service của orders dùng API công khai của catalog:

~~~java
package com.acme.shop.orders;

import com.acme.shop.catalog.api.ProductCatalog;
import com.acme.shop.orders.events.OrderPlaced;
import org.springframework.context.ApplicationEventPublisher;

public class OrderService {

    private final ProductCatalog catalog;
    private final ApplicationEventPublisher events;

    public OrderService(
            ProductCatalog catalog,
            ApplicationEventPublisher events
    ) {
        this.catalog = catalog;
        this.events = events;
    }

    public void placeOrder(String productId, int quantity) {
        catalog.findById(productId)
                .orElseThrow();

        events.publishEvent(
                new OrderPlaced("order-100", productId, quantity)
        );
    }
}
~~~

Listener trong inventory phải import event từ package mới:

~~~java
package com.acme.shop.inventory;

import com.acme.shop.orders.events.OrderPlaced;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
class InventoryListener {

    @EventListener
    void on(OrderPlaced event) {
        // Cập nhật reservation của inventory.
    }
}
~~~

Các imports tới `com.acme.shop.order...` cũ cần được chuyển sang `com.acme.shop.orders...`. IDE refactor có thể cập nhật imports tự động, nhưng hãy kiểm tra cả `package-info.java`, test sources, configuration class và các type reference bằng tên đầy đủ.

## 7. Viết architecture test cho module model sau refactor

Tạo file `src/test/java/com/acme/shop/architecture/ModuleModelAfterPackageChangeTests.java`:

~~~java
package com.acme.shop.architecture;

import com.acme.shop.ShopApplication;
import com.acme.shop.orders.OrderService;
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

import static org.assertj.core.api.Assertions.assertThat;

class ModuleModelAfterPackageChangeTests {

    @Test
    void detectsModulesAfterOrderPackageRename() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        assertThat(modules.getModuleByName("catalog")).isPresent();
        assertThat(modules.getModuleByName("order-management")).isPresent();
        assertThat(modules.getModuleByName("inventory")).isPresent();
    }

    @Test
    void keepsOrderIdentifierAndUsesNewBasePackage() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        ApplicationModule orders = modules
                .getModuleByName("order-management")
                .orElseThrow();

        assertThat(orders.getIdentifier().toString())
                .isEqualTo("order-management");
        assertThat(orders.getBasePackage().getName())
                .isEqualTo("com.acme.shop.orders");
    }

    @Test
    void assignsOrderServiceToTheRenamedModule() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        ApplicationModule module = modules
                .getModuleByType(OrderService.class)
                .orElseThrow();

        assertThat(module.getIdentifier().toString())
                .isEqualTo("order-management");
        assertThat(module.getBasePackage().getName())
                .isEqualTo("com.acme.shop.orders");
    }

    @Test
    void verifiesTheDependencyGraphAndPackageBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Các test kiểm tra bốn khía cạnh:

1. `catalog`, `order-management` và `inventory` đều được phát hiện.
2. Identifier của orders giữ nguyên, trong khi base package phản ánh package mới.
3. Type `OrderService` được gán vào đúng module sau khi di chuyển.
4. `verify()` kiểm tra dependency graph, package visibility và `allowedDependencies`.

`ApplicationModules` phân tích cấu trúc bytecode và package mà không cần khởi động toàn bộ Spring ApplicationContext. Vì vậy, architecture test này có thể chạy nhanh và phù hợp để khóa module model trong CI.

## 8. Đọc kết quả module model

Có thể thêm một đoạn inspection tạm thời trong test hoặc một phương thức hỗ trợ để in module model:

~~~java
ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
modules.forEach(System.out::println);
~~~

Sau refactor, module orders cần thể hiện:

| Thuộc tính | Giá trị mong đợi |
|---|---|
| Logical identifier | `order-management` |
| Base package | `com.acme.shop.orders` |
| Named interface | `events` |
| Consumer event | `inventory` |
| Dependency đi ra | `catalog::api` |

Module inventory cần phụ thuộc vào `order-management::events`. Nếu output vẫn hiển thị base package cũ `com.acme.shop.order`, hãy kiểm tra file `package-info.java`, package declaration và source path. Nếu module mới không xuất hiện, kiểm tra module có còn nằm dưới application root và có type được biên dịch trong classpath hay không.

## 9. Kiểm tra dependency reference sau package rename

Sau khi đổi package, dependency graph dự kiến:

~~~mermaid
flowchart LR
    inventory["inventory"] -->|"order-management::events"| orders["orders"]
    orders -->|"catalog::api"| catalog["catalog"]
~~~

Hãy xác nhận:

| Consumer | Provider | Type được tham chiếu | Allowlist |
|---|---|---|---|
| orders | catalog | `ProductCatalog` | `catalog::api` |
| inventory | orders | `OrderPlaced` | `order-management::events` |

Không dùng package path mới làm module identifier trong `allowedDependencies`. Package path và identifier có thể khác nhau khi module khai báo `id` tường minh.

`verify()` sẽ phát hiện khi:

- Consumer import type từ package nội bộ không được công khai.
- Consumer dùng named interface nhưng allowlist không cho phép.
- Dependency reference không khớp identifier của provider.
- Package move vô tình tạo ra dependency cycle.

## 10. Thử tạo một vi phạm để kiểm tra test có bắt được không

Một architecture test chỉ hữu ích khi nó phát hiện được thay đổi boundary không mong muốn. Thực hiện thử nghiệm âm tính sau:

1. Tạo một type implementation có `public` visibility trong `com.acme.shop.catalog.internal` để consumer có thể biên dịch khi thử import trực tiếp.
2. Cho `OrderService` import type đó trực tiếp.
3. Chạy architecture test.
4. Đọc lỗi do `modules.verify()` báo ra.
5. Xóa import vi phạm và chuyển `OrderService` về `ProductCatalog` trong `catalog::api`.
6. Chạy lại architecture test và xác nhận thành công.

Ví dụ import không được phép:

~~~java
import com.acme.shop.catalog.internal.JpaProductCatalog;
~~~

Orders chỉ cần hợp đồng `ProductCatalog`. Khi truy cập implementation `JpaProductCatalog`, module orders bị phụ thuộc vào chi tiết nội bộ của catalog. Đây là loại lỗi mà module verification cần ngăn chặn.

Không thêm dependency vào allowlist chỉ để làm test xanh. Hãy xem consumer có thực sự cần một hợp đồng mới hay đang truy cập sai implementation.

## 11. Phân biệt lỗi compile với lỗi module verification

Sau package rename, có hai nhóm lỗi cần phân biệt:

| Nhóm lỗi | Ví dụ | Cách xử lý |
|---|---|---|
| Compile/refactor | Import `com.acme.shop.order.OrderService` vẫn còn | Cập nhật package declaration và Java/Kotlin imports |
| Module detection | `getModuleByName("order-management")` trả về empty | Kiểm tra root package, detection strategy và `@ApplicationModule` |
| Identifier | Tra cứu bằng `orders` trong khi module dùng id `order-management` | Dùng đúng logical identifier |
| Visibility | Consumer import `catalog.internal` | Chuyển sang named interface `catalog::api` |
| Allowed dependency | Inventory dùng event nhưng allowlist thiếu `order-management::events` | Cập nhật metadata theo hợp đồng được duyệt |
| Dependency cycle | Package move làm lộ một tham chiếu ngược | Xem lại dependency direction và contract |

Compile test xác nhận code references còn hợp lệ. Architecture test xác nhận module model và boundary vẫn đúng. Hai bước bổ sung cho nhau.

## 12. Khi package move làm thay đổi module identifier

Nếu module trước đây không khai báo `id`, identifier mặc định thường dựa trên tên package tương đối với root package. Ví dụ, package `com.acme.shop.order` có thể tạo identifier `order`. Sau khi chuyển sang `com.acme.shop.orders`, identifier mặc định có thể trở thành `orders`.

Khi đó có hai lựa chọn:

- Chấp nhận identifier mới và cập nhật tất cả dependency reference, lookup, shared module configuration và test.
- Khai báo `id` tường minh để giữ logical identity, sau đó cập nhật package path và imports.

Ví dụ giữ identifier:

~~~java
@org.springframework.modulith.ApplicationModule(
        id = "order-management",
        allowedDependencies = "catalog::api"
)
package com.acme.shop.orders;
~~~

Consumer tiếp tục tham chiếu:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "order-management::events"
)
package com.acme.shop.inventory;
~~~

Nếu quyết định đổi identifier, hãy coi đó là một thay đổi contract có ảnh hưởng tới consumer. Tạo một thay đổi có kiểm soát để cập nhật provider, consumer và test cùng lúc.

## 13. Bài tập mở rộng

Sau khi các test cơ bản thành công, thử các tình huống sau:

1. **Đổi tên thêm package con:** chuyển `com.acme.shop.orders.events` sang `com.acme.shop.orders.integration.events`, cập nhật named interface và kiểm tra named interface discovery.
2. **Bật fully qualified module names:** cấu hình `useFullyQualifiedModuleNames = true`, quan sát identifier mặc định và điều chỉnh test lookup phù hợp.
3. **Bỏ id tường minh:** xóa `id = "order-management"`, quan sát identifier thay đổi theo package, sau đó quyết định có nên giữ tên mặc định hay khôi phục id.
4. **Đổi named interface:** đổi `events` thành `integration-events`, cập nhật consumer reference và kiểm tra verification.
5. **Đưa test về package mới:** di chuyển các test thuộc orders sang `src/test/java/com/acme/shop/orders`, cập nhật imports và chạy lại module tests.
6. **Tạo dependency cycle có chủ đích:** thêm một tham chiếu từ catalog về orders, quan sát lỗi cycle, sau đó loại bỏ cạnh ngược.
7. **Di chuyển module sang root khác:** dùng `additionalPackages` hoặc detection strategy thích hợp, rồi kiểm tra root packages và module identifiers.

## 14. Tiêu chí hoàn thành

- [ ] Package module đã chuyển từ `com.acme.shop.order` sang `com.acme.shop.orders`.
- [ ] `package-info.java` đã được di chuyển và khai báo đúng package mới.
- [ ] Logical identifier `order-management` được giữ nguyên.
- [ ] Named interface `events` vẫn được phát hiện.
- [ ] Imports trong inventory trỏ tới `com.acme.shop.orders.events.OrderPlaced`.
- [ ] Module orders vẫn phụ thuộc `catalog::api`.
- [ ] Module inventory vẫn phụ thuộc `order-management::events`.
- [ ] `getModuleByName("order-management")` tìm thấy module.
- [ ] `getModuleByType(OrderService.class)` trả về đúng module.
- [ ] Base package được xác nhận là `com.acme.shop.orders`.
- [ ] `ApplicationModules.verify()` hoàn tất mà không có vi phạm.
- [ ] Architecture test được giữ trong source test để bảo vệ refactor tương lai.

## 15. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không tìm thấy module sau khi move | `package-info.java` chưa được chuyển hoặc package declaration sai | Đặt metadata ở package gốc mới và kiểm tra source path |
| Identifier thay đổi ngoài dự kiến | Module không có `id` tường minh | Khai báo id ổn định hoặc cập nhật consumer theo identifier mới |
| Test tra cứu module bằng tên cũ | Test chưa được cập nhật theo identifier mới | Dùng logical identifier hiện tại |
| Inventory không compile | Import event vẫn trỏ tới package cũ | Cập nhật import sang `com.acme.shop.orders.events` |
| `verify()` báo named interface không hợp lệ | `@NamedInterface` chưa được chuyển hoặc tên interface đổi | Kiểm tra `package-info.java` của package events |
| `verify()` báo dependency không được phép | `allowedDependencies` không khớp provider id/interface | Dùng `order-management::events` |
| Module orders không được phát hiện | Package mới nằm ngoài root hoặc detection strategy | Kiểm tra `ShopApplication` và module detection |
| Dependency cycle xuất hiện | Refactor làm lộ tham chiếu ngược giữa hai module | Chọn một chiều dependency và công khai contract phù hợp |
| Architecture test qua nhưng ứng dụng không khởi động | Package scanning hoặc cấu hình runtime chưa được cập nhật | Kiểm tra Spring component scan, persistence scan và cấu hình runtime |

## 16. Ghi nhớ

Package refactor có thể làm thay đổi module model nên cần được kiểm tra bằng architecture test. Sau khi chuyển package, hãy xác nhận module được phát hiện dưới base package mới, identifier vẫn đúng, named interface được giữ và dependency graph không có vi phạm. `ApplicationModules.getModuleByName()` kiểm tra logical identifier; `getModuleByType()` kiểm tra type được gán vào module nào; `getBasePackage()` xác nhận package mới; `verify()` kiểm tra dependency và visibility rule. Giữ các assertion này trong CI để những lần di chuyển package sau không âm thầm làm thay đổi ranh giới kiến trúc.

## Tài liệu tham khảo

- [Spring Modulith – Fundamentals and Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith – Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith API – `ApplicationModules`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [Spring Modulith API – `ApplicationModule`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html)
- [Spring Modulith API – `@ApplicationModule`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
