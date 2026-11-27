# Khai báo `allowedDependencies` bằng identifier

Trong Spring Modulith, `allowedDependencies` mô tả những application module mà một module được phép phụ thuộc. Danh sách này dùng logical module identifier, không dùng tên class hay `displayName`. Nếu chỉ cần API mặc định của module đích, khai báo identifier của module. Nếu cần một Named Interface cụ thể, ghép identifier với tên interface bằng dấu phân cách `::`.

Bài thực hành này xây dựng ba module `orders`, `inventory` và `billing`. Module `billing` cần sử dụng API đọc của `orders` và API mặc định của `inventory`. Bạn sẽ đặt logical identifier cho `orders`, khai báo allowlist ở phía `billing`, kiểm tra identifier bằng API Java và chạy module verification để xác nhận dependency hợp lệ.

## 1. Mục tiêu thực hành

Sau bài tập, bạn có thể:

- Phân biệt package name, logical module identifier và display name.
- Khai báo identifier riêng bằng `@ApplicationModule(id = …)`.
- Khai báo `allowedDependencies` bằng module identifier.
- Giới hạn dependency tới một Named Interface theo cú pháp `moduleIdentifier::interfaceName`.
- Dùng `ApplicationModuleIdentifier.of(…)` và `ApplicationModule.getIdentifier()` để kiểm tra identifier trong code.
- Dùng `ApplicationModules.verify()` để phát hiện dependency ngoài allowlist.
- Giải thích ý nghĩa của identifier mặc định, fully-qualified module name và wildcard `*`/`**`.

## 2. Bối cảnh và cấu trúc ban đầu

Xây dựng một ứng dụng bán hàng có cấu trúc sau:

```text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── package-info.java
│   ├── OrderManagement.java
│   └── api
│       ├── package-info.java
│       └── OrderSummary.java
├── inventory
│   ├── InventoryManagement.java
│   └── Sku.java
└── billing
    ├── package-info.java
    └── BillingService.java
```

Các module có trách nhiệm:

| Module | Trách nhiệm | Hợp đồng được `billing` sử dụng |
| --- | --- | --- |
| `order` | Quản lý đơn hàng | Named Interface `api` |
| `inventory` | Kiểm tra tồn kho | API mặc định tại package gốc |
| `billing` | Tính phí và tạo hóa đơn | Consumer của hai module trên |

Mục tiêu là chỉ cho `billing` truy cập `order::api` và package gốc của `inventory`. `billing` không được phép truy cập các module khác hoặc package nội bộ của `order`.

## 3. Phân biệt ba loại tên

Trước khi khai báo allowlist, cần hiểu ba khái niệm sau:

| Khái niệm | Ví dụ | Công dụng |
| --- | --- | --- |
| Package name | `com.acme.shop.order` | Địa chỉ package trong mã nguồn |
| Logical module identifier | `orders` | Định danh module trong module model và trong `allowedDependencies` |
| Display name | `Order Management` | Tên thân thiện dùng khi hiển thị hoặc tạo tài liệu |

Theo mặc định, logical identifier thường lấy từ tên package module cục bộ. Với package `com.acme.shop.order`, identifier mặc định là `order`. Có thể đặt identifier rõ ràng bằng thuộc tính `id` của `@ApplicationModule`.

Trong bài này, module `order` sẽ có identifier `orders`, khác với package name `order` và display name `Order Management`.

## 4. Đặt logical identifier cho module cung cấp

Tạo `src/main/java/com/acme/shop/order/package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
    id = "orders",
    displayName = "Order Management"
)
package com.acme.shop.order;
```

`id` đặt logical identifier của module thành `orders`. `displayName` chỉ phục vụ hiển thị, không phải giá trị để ghi vào `allowedDependencies`.

Identifier module không được chứa dấu `::`, vì chuỗi này được Spring Modulith dùng để phân tách module identifier và Named Interface. Ví dụ `id = "orders::api"` là không hợp lệ. Tên Named Interface phải được khai báo riêng trong phần sau.

Nếu không đặt `id`, module giữ identifier mặc định `order`. Khi đó consumer phải dùng `order` trong allowlist. Không được tự suy ra `orders` chỉ vì display name hoặc tên nghiệp vụ có dạng số nhiều.

## 5. Công bố Named Interface mà consumer cần

Module `order` có API mặc định tại package gốc. Để công bố thêm package `order.api`, tạo `src/main/java/com/acme/shop/order/api/package-info.java`:

```java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.order.api;
```

Tạo DTO công khai `OrderSummary`:

```java
package com.acme.shop.order.api;

import java.math.BigDecimal;
import java.util.UUID;

public record OrderSummary(
        UUID orderId,
        BigDecimal total
) {
}
```

Package `com.acme.shop.order.api` nay được công bố thành Named Interface tên `api`. Module khác có thể phụ thuộc vào hợp đồng `orders::api` mà không được truy cập `order.internal`.

Để so sánh, API mặc định của module `order` vẫn nằm trong package gốc `com.acme.shop.order`:

```java
package com.acme.shop.order;

import com.acme.shop.order.api.OrderSummary;

public interface OrderManagement {

    OrderSummary findSummary(java.util.UUID orderId);
}
```

Trong ví dụ hoàn chỉnh, nếu `OrderManagement` trả về `OrderSummary` từ package con, hãy công bố API theo đúng cách tổ chức mong muốn. Bài tập tập trung vào Named Interface `api`, vì vậy consumer sẽ import DTO từ package đó.

## 6. Chuẩn bị API của `inventory`

Module `inventory` cung cấp API mặc định tại package gốc:

```java
package com.acme.shop.inventory;

public record Sku(String value) {
}
```

```java
package com.acme.shop.inventory;

public interface InventoryManagement {

    boolean isAvailable(Sku sku, int quantity);
}
```

Không cần tạo Named Interface cho package gốc. Package gốc của một application module đã là API mặc định của module đó.

## 7. Khai báo `allowedDependencies` ở module tiêu thụ

Tạo `src/main/java/com/acme/shop/billing/package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "orders::api",
        "inventory"
    }
)
package com.acme.shop.billing;
```

Đọc từng phần của danh sách:

- `orders` là logical identifier của module `order`, được đặt ở bước 4.
- `api` là tên Named Interface được công bố ở bước 5.
- `orders::api` chỉ cho phép dependency tới Named Interface `api` của module `orders`.
- `inventory` cho phép dependency tới API mặc định tại package gốc của module `inventory`.

`allowedDependencies` là `String[]`. Java cho phép truyền một chuỗi trực tiếp nếu chỉ có một phần tử, hoặc dùng mảng khi có nhiều dependency. Có thể khai báo như sau nếu `billing` chỉ cần API của inventory:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory"
)
package com.acme.shop.billing;
```

Allowlist được khai báo ở phía module tiêu thụ. Đặt `allowedDependencies` trên `order` sẽ giới hạn module `order` được phụ thuộc vào đâu; nó không cấp quyền cho `billing` sử dụng `order`.

## 8. Sử dụng các API đã được cho phép

Tạo một service trong `billing` chỉ tham chiếu hai hợp đồng đã khai báo:

```java
package com.acme.shop.billing;

import com.acme.shop.inventory.InventoryManagement;
import com.acme.shop.inventory.Sku;
import com.acme.shop.order.api.OrderSummary;
import org.springframework.stereotype.Service;

import java.util.UUID;

@Service
class BillingService {

    private final InventoryManagement inventory;

    BillingService(InventoryManagement inventory) {
        this.inventory = inventory;
    }

    boolean canBill(Sku sku, int quantity) {
        return inventory.isAvailable(sku, quantity);
    }

    void createInvoice(OrderSummary order) {
        // Tạo hóa đơn từ hợp đồng đọc của order.
    }
}
```

`BillingService` tham chiếu `InventoryManagement` trong API mặc định của `inventory` và `OrderSummary` trong Named Interface `api` của `orders`. Nếu code chỉ dùng hai vùng này, dependency phù hợp với allowlist.

Nếu `billing` import `com.acme.shop.order.internal.OrderRepository`, module verification vẫn phải báo lỗi internal access. Việc cho phép `orders::api` không mở toàn bộ package con của `order`.

## 9. Kiểm tra identifier bằng `ApplicationModuleIdentifier`

Trong code Java, `ApplicationModuleIdentifier` là value object đại diện cho logical identifier của application module. Có thể tạo identifier mong đợi bằng `ApplicationModuleIdentifier.of(…)` và so sánh với identifier trong module model.

```java
package com.acme.shop;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModuleIdentifier;
import org.springframework.modulith.core.ApplicationModules;

class ModuleIdentifierTests {

    @Test
    void exposesExpectedLogicalModuleIdentifier() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        ApplicationModule orders = modules.getModuleByName("orders")
                .orElseThrow();

        ApplicationModuleIdentifier expected =
                ApplicationModuleIdentifier.of("orders");

        assertThat(orders.getIdentifier()).isEqualTo(expected);
    }
}
```

`ApplicationModuleIdentifier.of("orders")` nhận một identifier không rỗng và không chứa `::`. Nó không nhận chuỗi `orders::api`, vì phần `::api` là Named Interface qualifier chứ không thuộc identifier của module.

Điểm cần phân biệt: annotation `@ApplicationModule(allowedDependencies = …)` nhận `String[]`, không nhận trực tiếp `ApplicationModuleIdentifier[]`. Value object `ApplicationModuleIdentifier` được dùng khi thao tác với module model trong Java API; chuỗi trong annotation vẫn phải theo cú pháp identifier mà Spring Modulith quy định.

## 10. Xem allowlist đã được phân tích thành dependency nào

Có thể đọc các dependency được phép từ module model để kiểm tra target module và Named Interface:

```java
package com.acme.shop;

import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.NamedInterface;

class AllowedDependencyInspection {

    void inspect() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        ApplicationModule billing = modules.getModuleByName("billing")
                .orElseThrow();

        billing.getAllowedDependencies(modules).stream().forEach(dependency -> {
            String moduleId = dependency.getTargetModule()
                    .getIdentifier().toString();

            NamedInterface namedInterface = dependency.getTargetNamedInterface();
            String interfaceName = namedInterface == null
                    ? "(base API)"
                    : namedInterface.getName();

            System.out.printf("%s -> %s%n", moduleId, interfaceName);
        });
    }
}
```

Kết quả mong đợi có hai mục tương ứng:

```text
orders -> api
inventory -> (base API)
```

`getAllowedDependencies(modules)` trả về các dependency được khai báo tường minh cùng những dependency được bổ sung do shared module. Đây là allowlist của module, không phải danh sách dependency thực tế đã được code sử dụng. Muốn xem quan hệ thực tế, hãy xem `getDirectDependencies(modules)` hoặc kết quả module arrangement.

## 11. Chạy module verification

Tạo architecture test:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesAllowedModuleDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Khi code trong `billing` chỉ tham chiếu `orders::api` và `inventory`, verification phải chấp nhận các dependency này. Nếu code tham chiếu một module không nằm trong allowlist, test sẽ báo architectural violation.

`verify()` kiểm tra các quy tắc module, bao gồm dependency cycle, truy cập package nội bộ và dependency vượt khỏi allowlist nếu module đã khai báo `allowedDependencies`. Nó không chỉ kiểm tra chuỗi trong annotation có đúng cú pháp; nó còn đối chiếu các dependency thực tế của code với danh sách được phép.

## 12. Thử nghiệm âm: tạo dependency ngoài allowlist

Để xác nhận allowlist đang có tác dụng, tạo module `customer`:

```java
package com.acme.shop.customer;

public interface CustomerManagement {

    String findEmail(java.util.UUID customerId);
}
```

Tạm thời inject `CustomerManagement` vào `BillingService`:

```java
private final CustomerManagement customers;

BillingService(
        InventoryManagement inventory,
        CustomerManagement customers) {
    this.inventory = inventory;
    this.customers = customers;
}
```

Giữ nguyên allowlist:

```java
@ApplicationModule(allowedDependencies = {
    "orders::api",
    "inventory"
})
package com.acme.shop.billing;
```

Chạy lại `ApplicationModules.verify()`. Kết quả mong đợi là verification báo dependency từ `billing` đến `customer` không được cho phép. Lý do là `customer` chưa có trong allowlist của `billing`.

Sau đó chọn một trong hai hướng:

1. Nếu `billing` thực sự cần gọi API của `customer`, thêm `customer` vào `allowedDependencies`.
2. Nếu `billing` không nên phụ thuộc trực tiếp vào `customer`, loại reference và thiết kế lại luồng tích hợp phù hợp.

Sau khi thử nghiệm, xóa reference thử nghiệm hoặc cập nhật allowlist theo quyết định kiến trúc của bài tập.

## 13. Phân biệt module identifier với Named Interface identifier

Chuỗi dependency có thể chứa một hoặc hai phần:

| Identifier expression | Ý nghĩa |
| --- | --- |
| `inventory` | API mặc định của module có identifier `inventory` |
| `orders::api` | Named Interface `api` của module `orders` |
| `orders::*` | Tất cả Named Interface được khai báo tường minh của `orders`, không gồm API package gốc |
| `orders::**` | API package gốc và tất cả Named Interface của `orders` |

`orders::*` hữu ích khi consumer cần nhiều Named Interface nhưng không cần API mặc định. `orders::**` cho phép toàn bộ API mà module `orders` công bố. Hãy dùng identifier cụ thể nếu chỉ cần một hợp đồng để giữ allowlist nhỏ và dễ review.

Không dùng tên class như `OrderManagement`, tên bean, tên bảng database hoặc `displayName` trong `allowedDependencies`. Giá trị trước `::` phải là module identifier; giá trị sau `::` phải là tên Named Interface đã công bố.

## 14. Khi nào dùng fully-qualified module names?

Mặc định, module identifier thường là tên cục bộ của package module. Nếu ứng dụng có nhiều root package hoặc nhiều module trùng local name, có thể cấu hình `@Modulithic(useFullyQualifiedModuleNames = true)` trên application class:

```java
package com.acme.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.modulith.Modulithic;

@Modulithic(useFullyQualifiedModuleNames = true)
@SpringBootApplication
public class ShopApplication {
}
```

Với chế độ này, identifier mặc định của module dựa trên fully-qualified package name thay vì local module name. Ví dụ, dependency tới package `com.acme.shop.order` có thể được ghi bằng:

```java
@ApplicationModule(
    allowedDependencies = "com.acme.shop.order::api"
)
package com.acme.shop.billing;
```

Chỉ bật chế độ này khi có nhu cầu phân biệt module từ nhiều root package hoặc tránh trùng tên. Khi bật, hãy kiểm tra identifier thực tế qua `ApplicationModule.getIdentifier()` rồi cập nhật đồng bộ tất cả allowlist, shared module declaration và tài liệu liên quan.

Nếu đã đặt `id` tường minh cho module, hãy kiểm tra identifier thực tế trong module model thay vì đoán từ package name. Identifier mà model trả về mới là giá trị cần dùng trong allowlist.

## 15. Những trường hợp đặc biệt cần hiểu

### Không khai báo `allowedDependencies`

Nếu module không khai báo allowlist, Spring Modulith không áp dụng giới hạn dependency tường minh cho module đó. Module vẫn phải tuân thủ các quy tắc khác như không truy cập package nội bộ của closed module và không tạo dependency cycle.

### Khai báo mảng rỗng

```java
@ApplicationModule(allowedDependencies = {})
package com.acme.shop.billing;
```

Mảng rỗng có nghĩa allowlist tường minh của module không cho phép dependency tới module khác. Các shared module được khai báo ở cấp ứng dụng vẫn được Spring Modulith tính là dependency được phép. Điều này khác với việc bỏ thuộc tính và để giá trị mặc định, vốn không giới hạn dependency bằng allowlist tường minh.

### Shared module

Module được khai báo qua `@Modulithic(sharedModules = …)` hoặc `@Modulith(sharedModules = …)` cũng được tính là dependency được phép. Khi đọc `getAllowedDependencies(modules)`, có thể thấy cả những module được cho phép thông qua shared module declaration.

### Dependency được phép không làm package internal trở thành API

Allowlist chọn module hoặc Named Interface được phép sử dụng. Nó không mở package nội bộ. Nếu `billing` được phép phụ thuộc `orders::api`, reference tới `orders.internal.OrderRepository` vẫn không hợp lệ.

## 16. Bài tập tự kiểm tra

Thực hiện các thay đổi sau và ghi lại kết quả mong đợi trước khi chạy verification:

1. Đổi `id = "orders"` thành `id = "order-management"`. Bạn cần thay những chuỗi nào trong `allowedDependencies` và test identifier?
2. Đổi `allowedDependencies = { "orders::api", "inventory" }` thành chỉ `"orders::api"`. Reference nào trong `BillingService` sẽ trở thành dependency không được phép?
3. Thay `orders::api` bằng `orders::*`. Module `billing` có được phép truy cập API package gốc của `orders` không?
4. Thay `orders::*` bằng `orders::**`. Phạm vi API được phép thay đổi thế nào?
5. Xóa thuộc tính `allowedDependencies`. Verification còn kiểm tra những quy tắc kiến trúc nào?
6. Khai báo `allowedDependencies = {}`. Những dependency nào của `billing` sẽ bị từ chối?

Đáp án cần dựa trên module identifier và Named Interface thực tế trong module model, không dựa vào tên hiển thị hoặc suy đoán từ package.

## 17. Tiêu chí hoàn thành

Bạn hoàn thành bài thực hành khi đáp ứng tất cả điều kiện:

- [ ] Module `order` có logical identifier `orders`.
- [ ] Package `order.api` được công bố bằng Named Interface tên `api`.
- [ ] Module `billing` khai báo allowlist gồm `orders::api` và `inventory`.
- [ ] `ApplicationModuleIdentifier.of("orders")` bằng identifier lấy từ `orders.getIdentifier()`.
- [ ] Có thể đọc target module và Named Interface từ `billing.getAllowedDependencies(modules)`.
- [ ] `ApplicationModules.verify()` thành công với dependency hợp lệ.
- [ ] Thêm reference tới `customer` khi chưa cho phép làm verification thất bại.
- [ ] Sau khi sửa thử nghiệm, module model lại tuân thủ allowlist đã chọn.

## 18. Ghi nhớ

`allowedDependencies` là danh sách `String[]` khai báo ở module tiêu thụ. Mỗi chuỗi dùng logical module identifier; nếu cần giới hạn tới Named Interface, dùng định dạng `moduleIdentifier::interfaceName`. `@ApplicationModule(id = "…")` cho phép đặt identifier tường minh, còn `displayName` chỉ phục vụ hiển thị. Identifier không được chứa `::` vì đây là dấu phân cách dành cho Named Interface.

Trong Java API, `ApplicationModuleIdentifier.of("orders")` tạo value object để so sánh với `ApplicationModule.getIdentifier()`. Đối tượng này không thay thế chuỗi trong annotation. Hãy xác nhận identifier từ module model, khai báo allowlist ở phía consumer, kiểm tra Named Interface đã được công bố và chạy `ApplicationModules.verify()` để bảo vệ dependency graph.

## Tài liệu tham khảo

- [Spring Modulith 2.2 — Fundamentals: Explicit Application Module Dependencies and Named Interfaces](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith API — `ApplicationModule` annotation](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith API — `ApplicationModuleIdentifier`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleIdentifier.html)
- [Spring Modulith API — `ApplicationModule`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html)
- [Spring Modulith API — `ApplicationModules`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [Spring Modulith 2.2 — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
