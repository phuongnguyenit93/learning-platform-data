# `@ApplicationModule(allowedDependencies = …)` là hợp đồng phụ thuộc

Trong một modular monolith, mỗi application module nên biết rõ nó được phép sử dụng những module nào và những API nào của họ. Nếu không đặt giới hạn, code có thể dần phụ thuộc vào nhiều module hơn mức cần thiết. Một thay đổi nhỏ ở module này khi đó dễ lan sang những module khác, còn dependency graph ngày càng khó kiểm soát.

Spring Modulith cung cấp thuộc tính `allowedDependencies` của annotation `@ApplicationModule` để diễn đạt allowlist phụ thuộc. Khai báo này nói rõ module hiện tại được phép phụ thuộc trực tiếp vào module nào hoặc Named Interface nào. Khi chạy kiểm tra kiến trúc bằng `ApplicationModules.verify()`, Spring Modulith đối chiếu các dependency thực tế với danh sách cho phép.

`allowedDependencies` là hợp đồng kiến trúc có thể kiểm tra. Nó không tự tạo ra lời gọi giữa hai module, không thêm bean hay event listener và cũng không thay đổi cách Java biên dịch import. Nó định nghĩa giới hạn mà cấu trúc code phải tuân thủ.

## 1. Dependency được phát hiện từ code, allowlist được khai báo tại module

Giả sử ứng dụng có package gốc `com.acme.shop` và ba module:

```text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── package-info.java
│   ├── OrderManagement.java
│   └── internal
│       └── OrderService.java
├── inventory
│   ├── InventoryManagement.java
│   └── internal
│       └── InventoryService.java
└── customer
    ├── api
    │   ├── package-info.java
    │   └── CustomerLookup.java
    └── internal
        └── CustomerRepository.java
```

Theo cách phát hiện module mặc định, `order`, `inventory` và `customer` là các application module. Một dependency có thể được tạo ra khi `order` tham chiếu type API của `inventory`, inject bean do `inventory` cung cấp hoặc đăng ký listener cho event được `inventory` công bố.

Ví dụ, module `order` gọi API của `inventory`:

```java
package com.acme.shop.inventory;

public interface InventoryManagement {

    boolean hasAvailableStock(Sku sku, int quantity);
}
```

```java
package com.acme.shop.order.internal;

import com.acme.shop.inventory.InventoryManagement;
import org.springframework.stereotype.Service;

@Service
class OrderService {

    private final InventoryManagement inventory;

    OrderService(InventoryManagement inventory) {
        this.inventory = inventory;
    }
}
```

Từ tham chiếu này, mô hình kiến trúc ghi nhận dependency theo hướng `order -> inventory`. Dependency được suy ra từ code và các hợp đồng module mà Spring Modulith nhận diện. Ta không cần thêm một dòng khai báo dependency để tạo ra quan hệ đó.

`allowedDependencies` đặt giới hạn cho các quan hệ như vậy. Ví dụ, module `order` chỉ được phép phụ thuộc vào `inventory`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory"
)
package com.acme.shop.order;
```

Annotation được đặt trong `package-info.java` của root package module. Khi kiểm tra, dependency trực tiếp của `order` đến module khác mà không có trong allowlist sẽ bị xem là vi phạm.

## 2. `allowedDependencies` là allowlist, không phải danh sách module tự động được thêm vào

Có hai việc cần phân biệt:

- **Dependency thực tế:** được tạo ra bởi quan hệ giữa các type, Spring component, event listener hoặc các hợp đồng mà Spring Modulith nhận diện trong code.
- **Dependency được phép:** được liệt kê trong `allowedDependencies` của module tiêu thụ.

Ví dụ:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = { "inventory", "customer" }
)
package com.acme.shop.order;
```

Khai báo này cho biết `order` được phép phụ thuộc trực tiếp vào `inventory` và `customer`. Nó không làm cho `order` tự động gọi hai module đó. Nếu code không sử dụng chúng, việc liệt kê vẫn chỉ là một giới hạn cho phép, không phải dependency được phát sinh.

Ngược lại, nếu `order` thực tế phụ thuộc vào `shipping` nhưng allowlist không có `shipping`, kiểm tra kiến trúc sẽ báo vi phạm. Đây là cách allowlist giúp nhóm phát hiện một dependency mới xuất hiện ngoài thiết kế đã thống nhất.

Khi không khai báo `allowedDependencies`, module không có allowlist tường minh để giới hạn các module được phép sử dụng. Những quy tắc kiến trúc khác của Spring Modulith, như không truy cập package nội bộ và không tạo chu trình dependency, vẫn có thể được kiểm tra. Khi muốn kiểm soát chặt module nào được phép dùng, hãy khai báo danh sách rõ ràng.

## 3. Cho phép phụ thuộc vào Named Interface cụ thể

Đôi khi module không cần toàn bộ API được công bố của module khác. Nó chỉ cần một hợp đồng nhỏ, chẳng hạn event hoặc SPI. Spring Modulith cho phép chỉ định Named Interface bằng cú pháp:

```text
<module-name> :: <named-interface>
```

Giả sử module `customer` công bố package `api`:

```java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.customer.api;
```

Package này chứa hợp đồng mà module khác được phép sử dụng:

```java
package com.acme.shop.customer.api;

public interface CustomerLookup {

    CustomerSummary findById(CustomerId customerId);
}
```

Module `order` chỉ cần truy vấn thông tin khách hàng qua `CustomerLookup`. Ta có thể giới hạn dependency vào Named Interface `api`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "customer :: api"
)
package com.acme.shop.order;
```

Khai báo này thể hiện rõ `order` phụ thuộc vào hợp đồng `customer :: api`. Nó không cấp quyền truy cập vào `customer.internal` hoặc các package nội bộ khác.

Nếu module cần cả package gốc và một Named Interface của cùng module khác, có thể liệt kê từng dependency được phép theo nhu cầu thực tế:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "inventory",
        "customer :: api"
    }
)
package com.acme.shop.order;
```

Trong ví dụ, `inventory` là dependency đến API package mặc định của module `inventory`; `customer :: api` là dependency đến Named Interface `api` của module `customer`.

## 4. Package nội bộ vẫn là nội bộ

`allowedDependencies` không phải cách mở mọi package của module khác. Một module đóng mặc định công bố API qua package gốc và các Named Interface được khai báo. Những package con không được công bố vẫn là phần triển khai nội bộ.

Ví dụ, `order` có thể được phép phụ thuộc vào `inventory`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory"
)
package com.acme.shop.order;
```

Code như sau vẫn vi phạm ranh giới nếu `OrderService` import repository nội bộ:

```java
package com.acme.shop.order.internal;

import com.acme.shop.inventory.internal.StockRepository;
```

Allowlist module không biến `inventory.internal` thành API công khai. Nếu module `order` cần một thao tác nghiệp vụ của inventory, hãy công bố một abstraction ở package gốc. Nếu cần một hợp đồng riêng trong package con, hãy cân nhắc Named Interface có mục đích rõ ràng.

Điểm này quan trọng vì Java có thể cho phép import một lớp `public` ở package khác. Việc biên dịch thành công không chứng minh rằng import tuân thủ kiến trúc. Spring Modulith kiểm tra package boundary ở cấp kiến trúc để phát hiện loại truy cập này.

## 5. Dependency trực tiếp và dependency bắc cầu

Allowlist mô tả những dependency mà module hiện tại được phép có trực tiếp. Quyền sử dụng một module không tự động truyền qua các module khác.

Giả sử:

```text
order -> inventory -> catalog
```

Nếu `order` được phép phụ thuộc vào `inventory`, điều đó không có nghĩa `order` được phép import trực tiếp API của `catalog`. Nếu `order` cần dùng `catalog`, dependency trực tiếp đó phải được thiết kế và cho phép rõ ràng.

Không nên dựa vào việc một module khác đã sử dụng một dependency để coi dependency ấy là API gián tiếp của module mình. Hãy xác định module sở hữu hợp đồng và khai báo dependency trực tiếp đến module hoặc Named Interface tương ứng.

Quy tắc này giúp dependency graph thể hiện chính xác các mối liên hệ thực tế. Nó cũng tránh việc một module trở nên phụ thuộc vào chi tiết triển khai hoặc lựa chọn kiến trúc của một module trung gian.

## 6. Kết hợp allowlist với dependency event listener

Dependency không chỉ được tạo ra bởi lời gọi bean. Một module có thể phụ thuộc vào Named Interface chỉ để nhận application event.

Ví dụ, `order` công bố event trong package `order.events`:

```java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.order.events;
```

Module `shipping` lắng nghe event `OrderPlaced`:

```java
package com.acme.shop.shipping;

import com.acme.shop.order.events.OrderPlaced;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class ShippingOrderEvents {

    @ApplicationModuleListener
    void on(OrderPlaced event) {
        // Chuẩn bị giao hàng theo mã đơn hàng.
    }
}
```

Khai báo allowlist của `shipping`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "order :: events"
)
package com.acme.shop.shipping;
```

Dependency được ghi nhận theo hướng `shipping -> order :: events`. Module `shipping` được phép sử dụng hợp đồng event này. Module `order` không cần liệt kê `shipping` chỉ vì có listener tiêu thụ event; quan hệ phụ thuộc xuất phát từ module tiêu thụ hợp đồng.

Nếu sau này `shipping` bắt đầu inject thêm bean `OrderManagement` ở package gốc của `order`, cần xem xét và bổ sung quyền phụ thuộc đến API package tương ứng. Việc allowlist Named Interface `events` không tự cho phép mọi API khác của `order`.

## 7. Kiểm chứng hợp đồng bằng `ApplicationModules.verify()`

Khai báo allowlist chỉ có giá trị khi nhóm thường xuyên chạy kiểm tra kiến trúc. `ApplicationModules.verify()` xây dựng mô hình module và kiểm tra dependency thực tế theo các quy tắc đã khai báo.

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

Nếu `order` có dependency đến module không nằm trong `allowedDependencies`, test sẽ thất bại và báo vi phạm. Kiểm tra cũng phát hiện các vấn đề kiến trúc khác mà `verify()` hỗ trợ, chẳng hạn chu trình giữa các module hoặc truy cập package nội bộ.

Nên chạy bài test này trong test suite và CI. Nhờ đó, một import mới hoặc listener mới không vô tình mở rộng dependency graph mà không được xem xét.

Lưu ý rằng `verify()` là kiểm tra kiến trúc tĩnh trên mô hình code đã biên dịch. Nó không chặn Java compiler, không phải cơ chế bảo mật runtime và không tự thay thế review thiết kế. Nếu không chạy kiểm tra, annotation vẫn nằm trong source nhưng vi phạm có thể không được phát hiện trong quy trình build.

## 8. Cách thiết kế allowlist dễ duy trì

Khi thêm `allowedDependencies`, hãy thực hiện theo trình tự:

1. **Xác định trách nhiệm module:** ghi rõ module hiện tại sở hữu nghiệp vụ nào.
2. **Liệt kê dependency thực tế:** tìm bean được inject, type được import và event listener đang đăng ký.
3. **Chọn API cần dùng:** ưu tiên package gốc nếu đó là API chính; chọn Named Interface nếu chỉ cần một hợp đồng chuyên biệt.
4. **Khai báo allowlist nhỏ nhất:** chỉ liệt kê module và Named Interface mà module thực sự cần.
5. **Chạy `ApplicationModules.verify()`:** xử lý các vi phạm trước khi hợp nhất thay đổi.
6. **Đưa kiểm tra vào CI:** bảo đảm các thay đổi sau này tiếp tục tuân thủ hợp đồng.

Khi một dependency mới làm test thất bại, đừng vội thêm tên module vào allowlist để làm test xanh. Trước tiên hãy xác định vì sao dependency xuất hiện, module tiêu thụ có thực sự cần hợp đồng đó không và API hiện tại có đúng phạm vi không. Nếu dependency là hợp lý, cập nhật allowlist là một quyết định kiến trúc cần được phản ánh trong thay đổi code.

## 9. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu chính xác |
| --- | --- |
| `allowedDependencies` tạo ra dependency giữa hai module. | Dependency được phát hiện từ code và hợp đồng; annotation chỉ xác định dependency nào được phép. |
| Không khai báo allowlist nghĩa là module không được phụ thuộc vào module nào. | Khi không khai báo, không có allowlist tường minh; các quy tắc kiến trúc khác vẫn được kiểm tra. |
| Cho phép module `inventory` nghĩa là được import mọi package của nó. | Package nội bộ vẫn bị bảo vệ; module khác chỉ dùng API được công bố. |
| Cho phép `customer :: api` cũng cho phép toàn bộ module `customer`. | Khai báo chỉ cấp quyền phụ thuộc vào Named Interface được chỉ định. |
| Dependency bắc cầu tự động được kế thừa. | Mỗi module phải khai báo dependency trực tiếp mà nó thực sự sử dụng. |
| Annotation khiến Java compiler từ chối import sai. | Cần chạy `ApplicationModules.verify()` để kiểm tra ranh giới kiến trúc. |
| Thêm mọi module vào allowlist giúp giảm lỗi. | Allowlist rộng làm mất ý nghĩa kiểm soát và khiến coupling tăng khó nhận biết. |

## 10. Ghi nhớ

`@ApplicationModule(allowedDependencies = …)` là hợp đồng mô tả những module hoặc Named Interface mà một application module được phép phụ thuộc trực tiếp. Spring Modulith phát hiện dependency từ cấu trúc code, bean wiring và event listener; allowlist được dùng để xác nhận các quan hệ đó có nằm trong giới hạn đã thống nhất hay không.

Hãy dùng tên module khi cần phụ thuộc vào API package mặc định, dùng cú pháp `module :: interface` khi chỉ cần một Named Interface, và giữ package nội bộ ngoài hợp đồng. Dependency trực tiếp phải được khai báo rõ; quyền phụ thuộc không tự truyền qua module trung gian. Cuối cùng, chạy `ApplicationModules.verify()` trong CI để hợp đồng kiến trúc tiếp tục được thực thi khi code thay đổi.

## Tài liệu tham khảo

- [Spring Modulith Reference — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith API — `ApplicationModule`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
