# Allowed dependencies được tôn trọng

`allowedDependencies` cho phép một application module khai báo rõ những module hoặc named interface mà nó được phép phụ thuộc vào. Khi chạy `ApplicationModules.verify()`, Spring Modulith đối chiếu dependency thực tế trong code với danh sách được khai báo. Nếu một module sử dụng API của module khác nhưng không có quyền phụ thuộc tương ứng, verification báo vi phạm kiến trúc.

Trong phạm vi **SPRING_MODULITH_MODULE_MODEL**, quy tắc này giúp biến dependency policy thành điều có thể kiểm tra tự động. Nhóm có thể xác định module nào được gọi module nào, giới hạn consumer vào đúng API công khai và phát hiện dependency mới xuất hiện ngoài dự kiến trong quá trình phát triển.

## 1. allowedDependencies là allowlist của module sử dụng

Giả sử ứng dụng có ba module nghiệp vụ:

```text
com.acme.shop
├── ShopApplication.java
├── orders
├── inventory
└── customers
```

Module `orders` cần gọi API tồn kho và đọc một số thông tin khách hàng. Nhóm có thể khai báo các dependency được phép ngay trong `orders/package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "inventory::api",
        "customers::api"
    }
)
package com.acme.shop.orders;
```

Danh sách này được khai báo ở phía module consumer (`orders`), vì nó mô tả những module mà `orders` được phép phụ thuộc vào. Module đích không cần liệt kê các consumer của mình trong `allowedDependencies`.

Nếu `orders` bắt đầu phụ thuộc trực tiếp vào `billing::api` nhưng không thêm dependency đó vào allowlist, `ApplicationModules.verify()` sẽ phát hiện dependency không được cho phép. Điều này giúp nhóm nhận ra khi một thay đổi code tạo thêm coupling ngoài thiết kế.

Khi một module không khai báo `allowedDependencies`, không có allowlist tường minh để giới hạn các module mà nó sử dụng. Các quy tắc khác vẫn có hiệu lực, chẳng hạn quy tắc truy cập API của module `CLOSED` và kiểm tra dependency cycle.

## 2. Khai báo dependency tới module hoặc named interface

Một phần tử trong `allowedDependencies` dùng logical identifier của module đích. Có thể chỉ định module hoặc một named interface cụ thể bằng dấu phân cách `::`.

Ví dụ, module `inventory` có package gốc và một named interface:

```text
com.acme.shop.inventory
├── InventoryFacade.java              // API mặc định ở package gốc
├── api
│   ├── package-info.java              // Named Interface "api"
│   └── InventoryOperations.java
└── internal
    └── InventoryRepository.java
```

Đánh dấu package `api` trong `inventory/api/package-info.java`:

```java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.inventory.api;
```

Interface được công khai trong package đó:

```java
package com.acme.shop.inventory.api;

public interface InventoryOperations {

    boolean isAvailable(String sku);
}
```

Các dạng khai báo dependency:

| Giá trị | Ý nghĩa |
|---|---|
| `"inventory"` | Cho phép phụ thuộc vào API mặc định (unnamed interface) của module `inventory` |
| `"inventory::api"` | Cho phép phụ thuộc vào named interface `api` của module `inventory` |
| `"customers::api"` | Cho phép phụ thuộc vào named interface `api` của module `customers` |

Module identifier phải khớp với identifier mà Spring Modulith nhận diện. Nếu module đích khai báo `@ApplicationModule(id = "stock")`, dependency cần dùng `stock` thay vì tên package cũ `inventory`.

## 3. Module đích phải công khai đúng API

`allowedDependencies` chỉ cho phép một dependency trong phạm vi API mà module đích công khai. Nó không tự công khai package nội bộ.

Ví dụ, `orders` chỉ được phép dùng `inventory::api`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::api"
)
package com.acme.shop.orders;
```

Code trong `orders` sử dụng hợp đồng API:

```java
package com.acme.shop.orders;

import com.acme.shop.inventory.api.InventoryOperations;
import org.springframework.stereotype.Service;

@Service
class OrderPlacement {

    private final InventoryOperations inventory;

    OrderPlacement(InventoryOperations inventory) {
        this.inventory = inventory;
    }

    void place(String sku) {
        if (!inventory.isAvailable(sku)) {
            throw new IllegalStateException("Insufficient stock");
        }
    }
}
```

Nếu `orders` thay import bằng `com.acme.shop.inventory.internal.InventoryRepository`, dependency đó vẫn vi phạm ranh giới của module `inventory` nếu module này là `CLOSED`. Thêm `"inventory::api"` vào allowlist không cấp quyền truy cập `inventory.internal`.

Hãy phân biệt hai câu hỏi:

- `@NamedInterface` xác định package nào là API công khai của module đích.
- `allowedDependencies` xác định module consumer được phép sử dụng API nào.

Hai khai báo bổ sung cho nhau để bảo vệ cả bề mặt API và hướng dependency.

## 4. Verification phát hiện dependency ngoài allowlist

Giả sử `orders` chỉ cho phép `inventory::api`, nhưng một thay đổi mới khiến code tham chiếu `customers.api.CustomerProfile`:

```java
package com.acme.shop.orders;

import com.acme.shop.customers.api.CustomerProfile;

class OrderCustomerView {

    CustomerProfile customerProfile;
}
```

Dependency mới là:

```text
orders ───────> customers::api
```

Trong khi allowlist của `orders` chỉ có `inventory::api`, nên `customers::api` nằm ngoài danh sách được phép. Khi kiểm tra kiến trúc, Spring Modulith báo dependency không hợp lệ.

Đưa kiểm tra vào test:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

`verify()` kiểm tra các dependency được phát hiện từ cấu trúc code và mô hình module, bao gồm các quy tắc `allowedDependencies`. Khi có vi phạm, test thất bại để nhóm xử lý trước khi thay đổi được chấp nhận.

## 5. Dependency trực tiếp và dependency bắc cầu

Allowlist phải phản ánh dependency trực tiếp của module. Nếu `orders` phụ thuộc vào `inventory`, còn `inventory` phụ thuộc vào `catalog`, điều đó không tự động cho phép `orders` sử dụng trực tiếp API của `catalog`.

```text
orders ─────> inventory ─────> catalog
```

Nếu code trong `orders` import trực tiếp một type thuộc `catalog`, nó tạo thêm cạnh:

```text
orders ──────────────────────> catalog
```

Dependency trực tiếp mới này cần được đánh giá và cho phép riêng trong `orders` nếu kiến trúc thực sự yêu cầu. Việc `inventory` đã được phép dùng `catalog` không truyền quyền đó sang `orders`.

Đây là nguyên tắc quan trọng để tránh coupling ẩn. Nếu `orders` cần một dữ liệu hoặc hành động do `catalog` sở hữu, hãy quyết định rõ nó có nên gọi API của `catalog` hay nên nhận thông tin qua hợp đồng do `inventory` cung cấp.

## 6. allowedDependencies không thay thế dependency cycle detection

Một dependency có thể nằm trong allowlist nhưng vẫn góp phần tạo chu kỳ. Ví dụ:

```text
orders ─────> inventory
   ▲             │
   └─────────────┘
```

Nếu `orders` cho phép phụ thuộc vào `inventory` và `inventory` cũng cho phép phụ thuộc vào `orders`, cả hai dependency có thể được chấp nhận theo allowlist riêng. Tuy nhiên, đồ thị module vẫn có chu kỳ và vi phạm yêu cầu DAG của Spring Modulith.

Vì vậy, `ApplicationModules.verify()` kiểm tra nhiều quy tắc khác nhau:

- Dependency có nằm trong `allowedDependencies` khi module khai báo allowlist hay không.
- Dependency có đi qua API được công khai của module đích hay truy cập package nội bộ không được phép hay không.
- Đồ thị module có dependency cycle hay không.

Không nên hiểu việc thêm một dependency vào allowlist là xác nhận rằng kiến trúc tổng thể đã hợp lệ. Nó chỉ xác nhận một loại chính sách; các quy tắc khác vẫn phải được thỏa mãn.

## 7. allowedDependencies và OPEN/CLOSED giải quyết hai việc khác nhau

`allowedDependencies` là quy tắc về module mà consumer được phép phụ thuộc. `ApplicationModule.Type` là quy tắc về mức độ đóng gói của module đích.

| Cơ chế | Kiểm soát |
|---|---|
| `allowedDependencies` | Các module/API mà module hiện tại được phép phụ thuộc vào |
| `type = CLOSED` | Chỉ công khai package gốc và named interface; package nội bộ được giữ kín |
| `type = OPEN` | Nới lỏng truy cập internals của module được đánh dấu mở trong mô hình Spring Modulith |

Ví dụ, nếu `orders` có `allowedDependencies = "inventory::api"`, nó chỉ được phép dùng named interface đó. Nếu `inventory` là `CLOSED`, package `inventory.internal` vẫn bị bảo vệ. Nếu `inventory` là `OPEN`, khả năng truy cập internal types được nới lỏng theo semantics của open module, nhưng allowlist đi ra từ `orders` vẫn là một quy tắc riêng.

Với ứng dụng mới, nên ưu tiên `CLOSED` và khai báo các dependency cụ thể bằng `allowedDependencies`. Dùng `OPEN` chỉ khi có lý do chuyển đổi legacy và hiểu rõ giới hạn verification của open module.

## 8. Tổ chức allowlist theo nhu cầu nghiệp vụ

Không nên thêm tất cả module vào `allowedDependencies` chỉ để làm test pass. Mỗi dependency nên có lý do nghiệp vụ cụ thể.

Ví dụ, `orders` cần:

- `inventory::api` để yêu cầu kiểm tra hoặc giữ hàng.
- `customers::api` để truy vấn thông tin khách hàng được công khai.

Nó không cần phụ thuộc vào `billing.internal`, `inventory.persistence` hoặc `customers.repository`. Các package đó là chi tiết triển khai của module sở hữu.

Một allowlist ngắn giúp reviewer trả lời được câu hỏi: “Module này được phép phối hợp với những năng lực nghiệp vụ nào?” Nếu danh sách tăng nhanh, hãy xem lại trách nhiệm của module, API có đang phơi bày quá nhiều chi tiết hay một use case đang điều phối quá nhiều module hay không.

## 9. Kiểm tra dependency thực tế của một module

Có thể truy vấn dependency trực tiếp từ mô hình `ApplicationModules` để đối chiếu với allowlist:

```java
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

ApplicationModule orders = modules.getModuleByName("orders").orElseThrow();

orders.getDirectDependencies(modules)
    .uniqueModules()
    .forEach(module -> System.out.println(module.getIdentifier()));
```

Đoạn code liệt kê module đích của các dependency trực tiếp mà mô hình phát hiện. Nó giúp nhóm thấy code đang phụ thuộc vào module nào trước khi xem xét có nên thêm dependency vào allowlist hay tái cấu trúc code.

Có thể kết hợp với `verify()` để kiểm tra toàn bộ chính sách:

```java
modules.verify();
```

Nếu muốn kiểm tra một dependency cụ thể trong test, có thể lấy `ApplicationModule` đích rồi assertion trên tập `uniqueModules()` hoặc trên các dependency tương ứng. Hãy ưu tiên test ở cấp kiến trúc cho toàn bộ module, vì một assertion riêng lẻ không thay thế việc kiểm tra toàn bộ graph.

## 10. Quy trình xử lý khi verify báo dependency không được phép

Khi test báo một module phụ thuộc ngoài allowlist, thực hiện theo thứ tự:

1. **Xác định module consumer.** Đọc tên module tạo ra dependency trong thông báo verification.
2. **Xác định module đích và type được tham chiếu.** Kiểm tra package của class, interface hoặc bean tạo dependency.
3. **Kiểm tra API của module đích.** Xác định type nằm ở package gốc, named interface hay package nội bộ.
4. **Xác nhận nhu cầu nghiệp vụ.** Consumer có thực sự cần sử dụng năng lực của module đích không?
5. **Chọn cách xử lý.** Nếu dependency hợp lý, thêm đúng module/interface vào allowlist; nếu không, chuyển logic qua API hiện có, port hoặc event phù hợp.
6. **Không mở rộng quyền quá mức.** Chỉ thêm `module::namedInterface` cần thiết khi consumer không cần toàn bộ API mặc định hoặc các interface khác.
7. **Chạy lại verification.** Xác nhận dependency mới được cho phép và không tạo chu kỳ hoặc vi phạm package boundary khác.
8. **Kiểm thử hành vi.** Chạy test của các module liên quan để bảo đảm thay đổi không làm sai quy tắc nghiệp vụ.

Ví dụ, nếu `orders` thực sự cần `CustomerProfile` trong `customers::api`, hãy thêm dependency đó:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "inventory::api",
        "customers::api"
    }
)
package com.acme.shop.orders;
```

Nếu `orders` chỉ cần biết khách hàng có hợp lệ hay không, có thể API của `customers` nên cung cấp một thao tác nghiệp vụ như `CustomerValidation` thay vì để `orders` truy cập nhiều kiểu dữ liệu của module đó.

## 11. Những ngộ nhận thường gặp

- **“allowedDependencies được khai báo ở module cung cấp.”** Nó được khai báo ở module consumer để mô tả các dependency đi ra mà consumer được phép có.
- **“Chỉ cần thêm tên module là mọi package nội bộ đều được mở.”** Allowlist không thay thế API visibility; module `CLOSED` vẫn giữ package nội bộ.
- **“Module A được phép dùng B thì B cũng được phép dùng A.”** Dependency có hướng; allowlist của A không cấp quyền ngược cho B.
- **“A được phép dùng B nên A được dùng mọi dependency bắc cầu của B.”** Không đúng; dependency trực tiếp của A cần được xem xét riêng.
- **“Dependency được allowlist thì không thể tạo cycle.”** Allowlist và cycle detection là hai kiểm tra độc lập.
- **“Không khai báo allowedDependencies nghĩa là module không được phụ thuộc đâu.”** Khi không có allowlist tường minh, không có giới hạn outgoing dependency theo danh sách này; các quy tắc API và cycle vẫn áp dụng.
- **“allowedDependencies là cơ chế bảo mật runtime.”** Đây là chính sách kiến trúc được kiểm tra bằng Spring Modulith, không phải authorization hoặc kiểm soát truy cập database.
- **“Thêm tất cả module vào allowlist là cách sửa lỗi.”** Cách đó làm mất giá trị của policy; hãy xác định dependency nào thật sự cần thiết.

## Kết luận

`allowedDependencies` biến các dependency mong muốn của một application module thành allowlist có thể kiểm chứng. Khai báo nó ở module consumer, dùng logical identifier của module đích và thêm `::namedInterface` khi cần giới hạn vào một API cụ thể. `ApplicationModules.verify()` sẽ phát hiện dependency ngoài danh sách, nhưng allowlist không mở package nội bộ, không truyền quyền qua dependency bắc cầu và không thay thế cycle detection. Hãy thêm từng dependency theo nhu cầu nghiệp vụ, giữ module đích đóng và công khai API có chủ đích, rồi chạy verification cùng test liên quan để bảo vệ đồ thị module.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith — ApplicationModule annotation API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith — ApplicationModules API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
