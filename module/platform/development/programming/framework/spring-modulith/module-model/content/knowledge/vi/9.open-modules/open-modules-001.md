# `@ApplicationModule(type = Type.OPEN)` dùng khi nào?

Spring Modulith mặc định xem một application module là **closed module**: module công khai API ở base package và giữ các sub-package làm phần triển khai nội bộ. Module khác không được tham chiếu trực tiếp type trong các package nội bộ đó. Với một codebase cũ có nhiều package con đang được sử dụng xuyên module, việc đóng gói lại ngay có thể đòi hỏi nhiều thay đổi.

Trong trường hợp chuyển đổi như vậy, ta có thể đánh dấu module là **open** bằng `@ApplicationModule(type = Type.OPEN)`. Cấu hình này nới lỏng quy tắc truy cập nội bộ để hỗ trợ quá trình chuyển đổi dần sang cấu trúc module rõ ràng hơn.

## 1. Closed module bảo vệ ranh giới như thế nào?

Giả sử ứng dụng có hai module `inventory` và `orders`:

```text
com.example.shop
├── ShopApplication.java
├── inventory
│   ├── InventoryManagement.java
│   └── internal
│       └── StockRepository.java
└── orders
    └── OrderService.java
```

Theo quy ước mặc định của một closed module:

- `com.example.shop.inventory` là API package của module `inventory`.
- `com.example.shop.inventory.internal` là package nội bộ.
- Module `orders` có thể sử dụng type công khai trong API package, nhưng không được phụ thuộc vào `StockRepository` trong `internal`.

Ví dụ, đoạn code sau tạo ra một tham chiếu đến implementation nội bộ:

```java
package com.example.shop.orders;

import com.example.shop.inventory.internal.StockRepository;

class OrderService {

    private final StockRepository stockRepository;

    OrderService(StockRepository stockRepository) {
        this.stockRepository = stockRepository;
    }
}
```

Nếu `StockRepository` là type có thể truy cập từ package khác, Java compiler có thể biên dịch tham chiếu này. Tuy nhiên, Spring Modulith sẽ xem đó là vi phạm ranh giới kiến trúc khi chạy `ApplicationModules.verify()` vì `orders` đang truy cập sub-package nội bộ của `inventory`.

## 2. Open module thay đổi quy tắc truy cập ra sao?

Ta có thể khai báo `inventory` là open trong file `package-info.java` của module:

```java
@org.springframework.modulith.ApplicationModule(
    type = org.springframework.modulith.ApplicationModule.Type.OPEN
)
package com.example.shop.inventory;
```

Khi module ở trạng thái `OPEN`, Spring Modulith thay đổi cách kiểm tra như sau:

- Việc module khác truy cập các type nội bộ của open module nhìn chung được cho phép.
- Các type trong sub-package cũng được đưa vào **unnamed interface** của module, trừ những type hoặc package được gán rõ ràng vào named interface khác.
- Open module được loại khỏi thuật toán phát hiện chu trình phụ thuộc giữa các module.

Với ví dụ trên, `StockRepository` có thể được module khác tham chiếu mà không bị quy tắc đóng gói nội bộ của `inventory` từ chối. Điều này giúp một ứng dụng cũ tiếp tục hoạt động trong khi nhóm đang di chuyển các lời gọi xuyên module về API công khai.

## 3. Open không có nghĩa là Java tự mở quyền truy cập

`Type.OPEN` thay đổi mô hình và quy tắc kiểm tra của Spring Modulith. Nó không thay đổi visibility của Java, không biến một lớp package-private thành `public`, không tự đăng ký bean và không thay thế cấu hình dependency injection.

Ví dụ, nếu `StockRepository` là lớp package-private trong `com.example.shop.inventory.internal`, code ở `com.example.shop.orders` vẫn không thể import lớp đó. Muốn truy cập từ package khác, type vẫn phải có mức truy cập phù hợp theo Java, thường là `public`.

Tương tự, việc một type được xem là thuộc unnamed interface của open module không tự tạo Spring bean. Bean vẫn cần được đăng ký theo cơ chế Spring như `@Component`, `@Repository` hoặc `@Bean` nếu cần dependency injection.

## 4. Open module không vô hiệu hóa mọi quy tắc phụ thuộc

Open module nới lỏng quy tắc truy cập các package nội bộ của chính module đó. Nó không có nghĩa mọi module trong ứng dụng được phép phụ thuộc lẫn nhau.

Ví dụ, `orders` vẫn có thể khai báo danh sách module được phép phụ thuộc:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory"
)
package com.example.shop.orders;
```

Danh sách `allowedDependencies` tiếp tục kiểm soát module đích mà `orders` được phép sử dụng. Nếu `orders` không được phép phụ thuộc vào `inventory`, việc `inventory` được đánh dấu `OPEN` không tự thêm `inventory` vào allow-list của `orders`.

Nếu module có sử dụng named interface, hãy khai báo dependency theo đúng tên module và interface mà code cần truy cập. Open module đưa các type chưa được gán named interface riêng vào unnamed interface; những type đã được gán named interface vẫn thuộc nhóm interface tương ứng.

## 5. Cái giá của việc mở module

`Type.OPEN` tiện cho codebase legacy, nhưng nó làm giảm khả năng bảo vệ ranh giới:

| Khía cạnh | Closed module | Open module |
|---|---|---|
| Type ở base package | API mặc định | API mặc định |
| Type ở sub-package | Nội bộ theo mặc định | Được đưa vào unnamed interface, trừ type/package đã gán named interface |
| Module khác truy cập internal type | Bị từ chối khi kiểm tra kiến trúc | Nhìn chung được cho phép |
| Phát hiện chu trình module | Được kiểm tra | Module open bị loại khỏi thuật toán phát hiện chu trình |
| Mức độ bảo vệ ranh giới | Rõ ràng và chặt chẽ hơn | Lỏng hơn, phụ thuộc nhiều vào quy ước của nhóm |

Đặc biệt, vì open module không tham gia thuật toán phát hiện chu trình, việc mở module có thể che khuất những quan hệ phụ thuộc vòng mà ta muốn phát hiện trong một kiến trúc modular monolith. Do đó, không nên đánh dấu mọi module là `OPEN` chỉ để làm cho `verify()` hết báo lỗi.

## 6. Khi nào nên dùng Type.OPEN?

Open module phù hợp nhất khi đang đưa một hệ thống hiện hữu vào Spring Modulith theo từng bước. Một số dấu hiệu thực tế:

- Nhiều module đang gọi trực tiếp các type trong sub-package của nhau.
- Việc tạo API công khai hoặc named interface cho tất cả các type đang được sử dụng sẽ cần một đợt refactor lớn.
- Nhóm muốn bắt đầu kiểm tra cấu trúc module ngay, rồi từng bước thu hẹp phần được công khai.

Với module mới hoặc module đã có ranh giới rõ ràng, nên giữ kiểu `CLOSED` mặc định. Hãy công khai những hợp đồng cần thiết ở base package hoặc bằng `@NamedInterface`, còn implementation để trong sub-package nội bộ.

## 7. Lộ trình chuyển từ OPEN về CLOSED

Có thể xem `OPEN` là một bước chuyển tiếp trong kế hoạch modular hóa:

1. **Bắt đầu bằng open module:** đánh dấu module legacy bằng `@ApplicationModule(type = Type.OPEN)` để có thể lập mô hình và kiểm tra phần còn lại của ứng dụng.
2. **Tìm các truy cập xuyên module:** rà soát những type trong sub-package đang được module khác sử dụng.
3. **Thiết kế API phù hợp:** chuyển các hợp đồng cần dùng ra base package hoặc gom thành named interface bằng `@NamedInterface`.
4. **Chuyển bên gọi:** cập nhật module phụ thuộc để dùng API đã công khai thay cho implementation nội bộ.
5. **Đóng module lại:** bỏ cấu hình `Type.OPEN` hoặc đặt về `Type.CLOSED`, rồi chạy `ApplicationModules.of(ShopApplication.class).verify()` để phát hiện các tham chiếu nội bộ còn sót.

Ví dụ, nếu `orders` cần kiểm tra tồn kho, thay vì truy cập `inventory.internal.StockRepository`, module `inventory` có thể công khai `StockAvailability` ở base package. `orders` chỉ phụ thuộc vào hợp đồng đó; repository và cách lưu trữ tồn kho vẫn nằm trong `inventory.internal`.

```java
package com.example.shop.inventory;

public interface StockAvailability {

    boolean isAvailable(String sku, int quantity);
}
```

Sau khi các module gọi đã chuyển sang hợp đồng công khai, `inventory` có thể trở lại trạng thái closed và Spring Modulith sẽ tiếp tục bảo vệ package nội bộ.

## 8. Kiểm chứng cấu trúc module

Sau mỗi bước chuyển đổi, hãy chạy kiểm thử kiến trúc:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Khi module vẫn `OPEN`, kiểm tra cho phép truy cập internal theo quy tắc open module và không dùng module đó trong thuật toán phát hiện chu trình. Khi module đã chuyển về `CLOSED`, các tham chiếu từ module khác tới sub-package nội bộ sẽ bị phát hiện. Điều này giúp nhóm có một tiêu chí rõ ràng để biết khi nào module đã sẵn sàng đóng lại.

Tài liệu tham khảo: [Open Application Modules trong Spring Modulith Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html#modules.advanced.open) và [Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html).
