# Named interface tường minh trong open module

Trong Spring Modulith, open module cho phép module khác truy cập rộng vào các kiểu nằm bên trong nó. Cách mở này hữu ích khi đưa một ứng dụng cũ vào quản lý kiến trúc theo từng bước, nhưng cũng khiến ranh giới API trở nên rộng. Named interface giúp đặt tên rõ ràng cho một nhóm package cần được quản lý như một hợp đồng riêng, chẳng hạn SPI mà module khác được phép sử dụng.

Hai khai báo giải quyết hai vấn đề khác nhau. `@ApplicationModule(type = OPEN)` quyết định chính sách mở của toàn module. `@NamedInterface("spi")` gán một package cụ thể vào giao diện có tên. Trong open module, các kiểu ở package gốc và package con được gom vào unnamed interface, ngoại trừ những kiểu đã được gán tường minh vào named interface. Nhờ đó, nhóm có thể giữ module mở để tương thích với code cũ nhưng vẫn mô tả một hợp đồng có tên và giới hạn dependency của module sử dụng hợp đồng đó.

## 1. Open module và named interface

Theo cấu trúc module đóng thông thường, package gốc là API mặc định. Các package con như `internal`, `persistence` hoặc `legacy` được xem là nội bộ. Module khác chỉ nên tham chiếu package gốc hoặc package con được công bố rõ bằng named interface.

Với codebase cũ, quy ước đó đôi khi khó áp dụng ngay vì nhiều module đang tham chiếu các kiểu nằm trong package con của nhau. Spring Modulith cho phép đánh dấu module là open:

~~~java
@org.springframework.modulith.ApplicationModule(
    type = org.springframework.modulith.ApplicationModule.Type.OPEN
)
package com.acme.shop.inventory;
~~~

Khi module mở, việc truy cập các kiểu nội bộ từ module khác nhìn chung được cho phép trong quá trình kiểm chứng. Các kiểu ở package gốc và package con được đưa vào unnamed interface của module, trừ những kiểu đã được gán tường minh vào named interface. Điều đó giúp code cũ tiếp tục hoạt động trong lúc nhóm dần xác định hợp đồng ổn định.

Named interface đặt tên cho một nhóm kiểu được công bố. Ví dụ, package `inventory.spi` có thể chứa các interface mà module `order` cần để tích hợp với năng lực giữ hàng. Khi đánh dấu package bằng `@NamedInterface("spi")`, nhóm có thể khai báo dependency cụ thể đến `inventory::spi`.

Hãy phân biệt:

- Open module mô tả chính sách mở của toàn module.
- Named interface gán một nhóm kiểu vào hợp đồng có tên.
- Named interface không biến package thành application module lồng nhau.
- Named interface không tự đóng module hoặc làm các package khác trở thành nội bộ.
- `allowedDependencies` ở module sử dụng xác định module đó được phép phụ thuộc vào giao diện nào.

## 2. Cấu trúc package minh họa

Giả sử ứng dụng bán hàng có module `inventory` đã tồn tại lâu. Nhiều package con đang được module khác sử dụng. Nhóm muốn chuẩn hóa một SPI để module `order` yêu cầu giữ hàng mà không phụ thuộc vào repository hoặc service nội bộ.

~~~text
com.acme.shop
├── ShopApplication.java
├── inventory
│   ├── package-info.java          // @ApplicationModule(type = OPEN)
│   ├── InventoryManagement.java
│   ├── spi
│   │   ├── package-info.java      // @NamedInterface("spi")
│   │   ├── StockReservation.java
│   │   ├── ReserveStockCommand.java
│   │   └── ReservationResult.java
│   ├── internal
│   │   ├── StockRepository.java
│   │   └── StockReservationService.java
│   └── legacy
│       └── LegacyStockFacade.java
└── order
    ├── package-info.java          // allowedDependencies = "inventory::spi"
    └── internal
        └── PlaceOrderService.java
~~~

Trong ví dụ, `inventory` là application module; `inventory.spi` là named interface tên `spi`; `inventory.internal` và `inventory.legacy` vẫn thuộc module `inventory`; `order` là module sử dụng SPI.

Do `inventory` là open module, các kiểu trong `internal` và `legacy` vẫn thuộc unnamed interface, trừ khi chúng được đánh dấu thành named interface khác. Package `spi` được gán riêng vào named interface `spi` nên không còn nằm trong unnamed interface.

## 3. Đánh dấu open module

Đặt annotation trên `package-info.java` ở package gốc của module:

~~~java
@org.springframework.modulith.ApplicationModule(
    type = org.springframework.modulith.ApplicationModule.Type.OPEN
)
package com.acme.shop.inventory;
~~~

File này nằm trong package `com.acme.shop.inventory`, không phải package gốc ứng dụng `com.acme.shop` và cũng không phải package `inventory.spi`.

Open module semantics có ba hệ quả cần nhớ:

1. Việc truy cập các kiểu nội bộ từ module khác nhìn chung được cho phép trong kiểm chứng.
2. Các kiểu ở package gốc và package con được đưa vào unnamed interface.
3. Package hoặc nhóm kiểu được đánh dấu bằng `@NamedInterface` được tách vào named interface tương ứng.

Nếu chỉ có annotation OPEN ở package gốc, `InventoryManagement`, `StockRepository` và `LegacyStockFacade` đều thuộc unnamed interface và có thể được module khác tham chiếu theo chính sách mở.

Open module chủ yếu hỗ trợ codebase cũ trong giai đoạn chuyển đổi. Trong ứng dụng đã modularize đầy đủ, việc phải mở toàn bộ module thường cho thấy ranh giới package hoặc API chưa rõ. Open module làm giảm khả năng kiểm chứng: các kiểu nội bộ không còn được bảo vệ như ở module đóng và open module bị loại khỏi thuật toán phát hiện dependency cycle. Vì vậy, cần có kế hoạch thu hẹp phạm vi mở.

## 4. Khai báo named interface tường minh

Tạo `package-info.java` bên trong package cần công bố:

~~~java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.inventory.spi;
~~~

Tên `spi` là tên logic của giao diện. Các kiểu trong package `com.acme.shop.inventory.spi` thuộc named interface này.

Ví dụ, SPI giữ hàng có thể khai báo như sau:

~~~java
package com.acme.shop.inventory.spi;

public interface StockReservation {

    ReservationResult reserve(ReserveStockCommand command);
}
~~~

Các kiểu xuất hiện trong chữ ký API cũng cần thuộc phạm vi công bố phù hợp. Chúng có thể được đặt trong các file riêng:

~~~java
// ReserveStockCommand.java
package com.acme.shop.inventory.spi;

public record ReserveStockCommand(String sku, int quantity) {
}
~~~

~~~java
// ReservationResult.java
package com.acme.shop.inventory.spi;

public record ReservationResult(String reservationId, boolean accepted) {
}
~~~

Đây là hợp đồng mà module gọi cần hiểu: yêu cầu giữ một số lượng hàng và nhận kết quả để tiếp tục quy trình. Module sử dụng không cần biết hệ thống lưu kho bằng JPA, JDBC hay cơ chế khác.

Một số tên giao diện thường gặp:

| Tên | Nội dung phù hợp |
| --- | --- |
| `spi` | Interface để module khác tích hợp hoặc cung cấp phần triển khai |
| `api` | Các thao tác nghiệp vụ được công bố cho bên sử dụng |
| `events` | Kiểu sự kiện công khai mà module khác cần tham chiếu |
| `reporting` | Kiểu truy vấn hoặc mô hình đọc dành cho báo cáo |

Tên nên diễn tả mục đích của nhóm kiểu. Không nên tạo named interface cho mọi package con chỉ để thêm annotation; mỗi giao diện cần đại diện cho một hợp đồng mà nhóm muốn quản lý riêng.

## 5. Giới hạn dependency đến named interface

Named interface có giá trị rõ nhất khi module sử dụng khai báo chính xác phần API mà nó được phép phụ thuộc.

Module `order` chỉ cần SPI giữ hàng. Khai báo `package-info.java` của `order` như sau:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::spi"
)
package com.acme.shop.order;
~~~

Cú pháp `inventory::spi` gồm tên module `inventory`, dấu phân cách `::` và tên named interface `spi`. `@NamedInterface` nằm ở phía module cung cấp; `allowedDependencies` nằm ở phía module sử dụng, trên package gốc của module đó.

Mã bên trong `order` có thể tham chiếu các kiểu của SPI:

~~~java
package com.acme.shop.order.internal;

import com.acme.shop.inventory.spi.ReserveStockCommand;
import com.acme.shop.inventory.spi.StockReservation;

class PlaceOrderService {

    private final StockReservation stockReservation;

    PlaceOrderService(StockReservation stockReservation) {
        this.stockReservation = stockReservation;
    }

    void reserveFor(String sku, int quantity) {
        var command = new ReserveStockCommand(sku, quantity);
        var result = stockReservation.reserve(command);

        if (!result.accepted()) {
            throw new IllegalStateException("Không thể giữ hàng cho sản phẩm " + sku);
        }
    }
}
~~~

Khi `order` khai báo `allowedDependencies = "inventory::spi"`, dependency của nó được giới hạn vào named interface `spi` của `inventory`. Import trực tiếp `com.acme.shop.inventory.internal.StockRepository` không thuộc giao diện được cho phép và sẽ bị kiểm tra kiến trúc phát hiện.

Nếu module sử dụng không khai báo dependency tường minh, nó không có allowlist để giới hạn dependency. Với open module, unnamed interface bao gồm cả các package con chưa được gán vào named interface, nên phạm vi truy cập có thể rất rộng. Vì vậy, module mới hoặc module đang được chuẩn hóa nên khai báo dependency cụ thể.

## 6. Unnamed interface và named interface trong open module

Giả sử module `inventory` có các package sau:

| Package | Khai báo | Giao diện Spring Modulith |
| --- | --- | --- |
| `inventory` | Package gốc | Unnamed interface |
| `inventory.internal` | Không có `@NamedInterface` | Unnamed interface của open module |
| `inventory.legacy` | Không có `@NamedInterface` | Unnamed interface của open module |
| `inventory.spi` | `@NamedInterface("spi")` | Named interface `spi` |

Ở module đóng, package gốc là API mặc định; package con không tự được công bố. Ở open module, các package con cũng được đưa vào unnamed interface trừ khi được gán tường minh vào named interface.

~~~text
inventory (OPEN)
│
├── unnamed interface
│   ├── package inventory
│   ├── package inventory.internal
│   └── package inventory.legacy
│
└── named interface: spi
    └── package inventory.spi
~~~

Gán `inventory.spi` vào named interface không làm các package còn lại tự động bị đóng. Nó chỉ tạo một nhóm có tên, có thể được tham chiếu độc lập trong khai báo dependency.

Spring Modulith hỗ trợ hai ký hiệu mở rộng trong `allowedDependencies`:

- `inventory::*` cho phép phụ thuộc vào tất cả named interface được khai báo tường minh của module `inventory`, không bao gồm unnamed interface.
- `inventory::**` cho phép phụ thuộc vào unnamed interface và tất cả named interface của module `inventory`. Với open module, unnamed interface có thể chứa nhiều package nội bộ nên cần dùng ký hiệu này thận trọng.

## 7. Kiểm chứng ranh giới bằng ApplicationModules

Đưa kiểm tra cấu trúc vào test để Spring Modulith phân tích dependency thực tế:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Với cấu hình ví dụ, kết quả mong đợi:

| Tham chiếu từ `order` | Kết quả |
| --- | --- |
| `inventory.spi.StockReservation` | Được phép |
| `inventory.spi.ReserveStockCommand` | Được phép |
| `inventory.internal.StockRepository` | Vi phạm allowlist chỉ cho `inventory::spi` |
| `inventory.legacy.LegacyStockFacade` | Vi phạm allowlist chỉ cho `inventory::spi` |

Nếu bỏ `allowedDependencies` ở `order`, open module có thể cho phép tham chiếu các kiểu trong unnamed interface, bao gồm cả `internal` và `legacy`. Đó là lý do nên khai báo dependency tường minh ở những module mới hoặc module đã bắt đầu được chuẩn hóa.

`ApplicationModules.verify()` kiểm tra quy tắc kiến trúc dựa trên mô hình package và dependency được phát hiện. Nó không thay thế kiểm tra nghiệp vụ, kiểm thử hành vi của SPI hoặc kiểm soát quyền truy cập ở runtime. Các kiểu Java vẫn phải có modifier phù hợp để mã nguồn có thể tham chiếu chúng.

## 8. Chuyển đổi module cũ theo từng bước

Có thể dùng open module như một trạng thái chuyển tiếp:

1. **Giữ tương thích:** đánh dấu module cũ là `OPEN` và ghi nhận các module đang tham chiếu package con của nó.
2. **Xác định hợp đồng:** chọn thao tác nghiệp vụ mà module khác thực sự cần; đưa interface, command, result hoặc event vào package API riêng.
3. **Đánh dấu giao diện:** thêm `@NamedInterface` vào `package-info.java` của package hợp đồng và chọn tên phản ánh mục đích như `spi` hoặc `events`.
4. **Giới hạn bên sử dụng:** khai báo `allowedDependencies` đến named interface cần thiết, ví dụ `inventory::spi`; chuyển các import nội bộ sang hợp đồng đã công bố.
5. **Đóng module:** khi các module sử dụng không còn truy cập package nội bộ, cân nhắc bỏ `type = OPEN` để quay về quy tắc module đóng.

Không cần chuyển tất cả module cùng lúc. Có thể giữ một module legacy ở trạng thái OPEN trong khi các module mới đã đóng và khai báo dependency cụ thể. Hãy theo dõi tiến độ để trạng thái mở không trở thành cấu hình vĩnh viễn.

## 9. Những lỗi thiết kế thường gặp

**Đánh dấu named interface nhưng không giới hạn dependency.** Module sử dụng vẫn có thể phụ thuộc vào phần rộng của open module nếu không có `allowedDependencies`. Hãy thêm allowlist ở phía module sử dụng khi mục tiêu là chỉ dùng SPI.

**Cho rằng named interface tự đóng các package còn lại.** Annotation này chỉ phân nhóm package được đánh dấu. Trong open module, các package khác vẫn nằm trong unnamed interface và tiếp tục được mở theo chính sách của module.

**Đặt repository hoặc entity vào SPI.** Điều đó khiến hợp đồng phụ thuộc vào chi tiết lưu trữ và làm thay đổi persistence ảnh hưởng đến module sử dụng. Hãy công bố thao tác nghiệp vụ cùng các kiểu dữ liệu ổn định.

**Dùng open module cho mọi module mới.** Cách này làm giảm khả năng kiểm chứng ranh giới và có thể che giấu dependency cycle. Hãy ưu tiên module đóng cho phần mới được thiết kế theo ranh giới rõ ràng.

**Nhầm named interface với nested module.** Named interface chỉ là một nhóm kiểu được công bố bên trong module. Nested module có ranh giới module riêng và có thể có API, dependency cùng quy tắc nội bộ riêng.

**Xem kiểm tra kiến trúc như cơ chế bảo mật.** Spring Modulith xác minh cấu trúc mã nguồn trong quá trình phát triển và build. Nó không thay thế Java access control, bảo mật ứng dụng hoặc kiểm soát truy cập dữ liệu.

## 10. Checklist

- [ ] Xác định lý do module cần ở trạng thái OPEN và phạm vi code legacy đang phụ thuộc vào nó.
- [ ] Đặt `@ApplicationModule(type = ApplicationModule.Type.OPEN)` tại package gốc của module.
- [ ] Chọn package chứa hợp đồng ổn định, không chứa implementation hoặc persistence detail.
- [ ] Đánh dấu package hợp đồng bằng `@NamedInterface("<name>")`.
- [ ] Đặt `allowedDependencies = "<module>::<name>"` tại module sử dụng nếu muốn giới hạn dependency vào đúng giao diện đó.
- [ ] Kiểm tra các module sử dụng không còn import package nội bộ ngoài hợp đồng đã cho phép.
- [ ] Chạy `ApplicationModules.of(ShopApplication.class).verify()` trong bộ kiểm thử kiến trúc.
- [ ] Có kế hoạch chuyển module từ OPEN về CLOSED khi dependency cũ đã được xử lý.

## 11. Kết luận

Named interface tường minh trong open module giúp nhóm đặt tên cho một hợp đồng cụ thể ngay cả khi module vẫn đang mở để duy trì tương thích với code cũ. Các kiểu được đánh dấu bằng `@NamedInterface` được tách khỏi unnamed interface; những package còn lại tiếp tục thuộc unnamed interface của open module.

Để giới hạn phụ thuộc thực sự, hãy kết hợp named interface ở module cung cấp với `allowedDependencies` ở module sử dụng, chẳng hạn `inventory::spi`. Sau đó dùng `ApplicationModules.verify()` để kiểm tra các tham chiếu thực tế. Khi quá trình chuyển đổi hoàn tất, đóng module lại để ranh giới API và phần nội bộ được bảo vệ rõ ràng.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Open Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Fundamentals: Named Interfaces](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — `ApplicationModule` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith — `NamedInterface` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/NamedInterface.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
