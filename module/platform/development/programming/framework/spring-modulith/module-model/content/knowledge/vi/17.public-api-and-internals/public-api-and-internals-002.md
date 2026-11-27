# Internal sub-package bị chặn trong module đóng

Trong Spring Modulith, một application module mặc định được đóng (closed). Package gốc của module là API package mà module khác có thể sử dụng; các package con thuộc phần triển khai nội bộ, trừ khi được công bố rõ ràng bằng named interface. Vì vậy, một lớp `public` nằm trong `inventory.internal` vẫn có thể bị chặn khi module `order` tham chiếu trực tiếp nó.

Đây là quy tắc encapsulation ở cấp kiến trúc của Spring Modulith. Nó bổ sung cho quyền truy cập của Java: Java quyết định mã có thể biên dịch và truy cập kiểu hay không, còn Spring Modulith kiểm tra module có đang phụ thuộc đúng bề mặt API được công bố hay không.

Trong `SPRING_MODULITH_MODULE_MODEL`, ranh giới này giúp module giữ quyền thay đổi repository, service triển khai và cấu trúc package bên trong mà không buộc consumer phụ thuộc vào các chi tiết đó. Bài học này giải thích quy tắc closed module, cách nhận diện lỗi truy cập internal sub-package và cách sửa bằng API công khai hoặc named interface.

## 1. Quy tắc API và internal package

Giả sử ứng dụng có package gốc `com.example.shop` và module `inventory`:

```text
com.example.shop
├── ShopApplication.java
├── inventory
│   ├── InventoryAvailability.java
│   └── internal
│       ├── DefaultInventoryAvailability.java
│       └── InventoryRepository.java
└── order
    └── internal
        └── PlaceOrderService.java
```

Theo quy ước module mặc định của Spring Modulith:

- `com.example.shop.inventory` là package gốc của module `inventory`, tạo thành API package mặc định.
- `com.example.shop.inventory.internal` là package con, thuộc phần nội bộ của module `inventory`.
- `com.example.shop.order` là API package mặc định của module `order`.
- `com.example.shop.order.internal` là phần nội bộ của module `order`.

Module `order` có thể sử dụng kiểu được công bố trong package gốc `inventory`. Nó không được tham chiếu trực tiếp các kiểu thuộc `inventory.internal` khi `inventory` là closed và package đó chưa được expose.

Quy tắc áp dụng theo vị trí package, không phụ thuộc tên package con. `internal`, `persistence`, `repository`, `application` hay `adapter` đều là package nội bộ nếu chúng nằm dưới package gốc module và chưa được công bố theo cách phù hợp.

## 2. Closed là trạng thái mặc định

Một application module mặc định có kiểu `CLOSED`. Có thể để Spring Modulith sử dụng mặc định hoặc khai báo tường minh trong `package-info.java` của package gốc:

```java
@org.springframework.modulith.ApplicationModule(
    type = org.springframework.modulith.ApplicationModule.Type.CLOSED
)
package com.example.shop.inventory;
```

Khai báo trên đặt tại:

```text
src/main/java/com/example/shop/inventory/package-info.java
```

Với module closed, các module khác chỉ được tham chiếu API package gốc và những named interface mà module chủ động expose. Các package con còn lại được giữ nội bộ.

Không cần tạo `package-info.java` chỉ để lặp lại giá trị mặc định `CLOSED` nếu module không có metadata khác. Khai báo tường minh hữu ích khi muốn tài liệu hóa quyết định encapsulation hoặc kết hợp với `allowedDependencies`.

## 3. Ví dụ truy cập internal sub-package bị chặn

Giả sử `inventory` có một repository triển khai được khai báo `public`:

```java
package com.example.shop.inventory.internal;

public class InventoryRepository {

    public int availableQuantity(String sku) {
        // Truy vấn dữ liệu tồn kho.
        return 10;
    }
}
```

Module `order` import trực tiếp repository:

```java
package com.example.shop.order.internal;

import com.example.shop.inventory.internal.InventoryRepository;
import org.springframework.stereotype.Service;

@Service
class PlaceOrderService {

    private final InventoryRepository repository;

    PlaceOrderService(InventoryRepository repository) {
        this.repository = repository;
    }

    boolean canPlace(String sku, int quantity) {
        return repository.availableQuantity(sku) >= quantity;
    }
}
```

Java có thể biên dịch đoạn mã này vì `InventoryRepository` và phương thức của nó là `public`. Tuy nhiên, tham chiếu kiểu từ `order` sang `inventory.internal` vi phạm encapsulation của module `inventory`.

Khi chạy kiểm tra kiến trúc:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Spring Modulith phát hiện dependency tới package nội bộ và báo lỗi kiến trúc. Thông báo cụ thể có thể khác nhau theo phiên bản, nhưng nguyên nhân là module tiêu thụ đã truy cập một package chưa được expose.

Nếu lớp nội bộ là package-private thay vì `public`, Java có thể từ chối biên dịch trước khi kiểm tra kiến trúc được chạy. Trong ví dụ trên, dùng lớp `public` để thấy rõ rằng vượt qua kiểm tra visibility của Java vẫn chưa đồng nghĩa với việc tuân thủ module boundary.

## 4. Vì sao `public` không đồng nghĩa với public API của module?

Java visibility và Spring Modulith encapsulation là hai lớp quy tắc khác nhau.

| Câu hỏi | Java visibility | Spring Modulith module boundary |
|---|---|---|
| Phạm vi kiểm soát | Class, constructor, field, method và package | Quan hệ tham chiếu giữa application module |
| `public` có ý nghĩa gì? | Cho phép mã ở package khác truy cập theo quy tắc Java | Không tự công bố package con thành API module |
| Package-private có ý nghĩa gì? | Chỉ mã trong cùng package truy cập được | Không thay đổi việc package thuộc API hay internal của module |
| Kiểm tra bằng gì? | Java compiler | `ApplicationModules.verify()` và các kiểm tra kiến trúc |

Một lớp `public` trong `inventory.internal` có thể được Java import, nhưng Spring Modulith vẫn xem nó là chi tiết nội bộ của `inventory`. Ngược lại, một kiểu trong package gốc có thể thuộc bề mặt API module, nhưng nếu kiểu đó package-private thì mã Java ở package khác vẫn không thể truy cập.

Do đó, khi thiết kế public API, cần đồng thời chọn đúng package và modifier Java phù hợp. Không nên dùng `public` trên mọi lớp nội bộ với suy nghĩ rằng như vậy đã công bố API.

## 5. Sửa bằng API công khai ở package gốc

Nếu `order` chỉ cần khả năng kiểm tra số lượng tồn kho, module `inventory` nên công bố một hợp đồng thể hiện đúng capability đó thay vì expose repository.

Interface API trong package gốc `inventory`:

```java
package com.example.shop.inventory;

public interface InventoryAvailability {

    boolean hasAvailableStock(String sku, int quantity);
}
```

Implementation nằm trong package nội bộ:

```java
package com.example.shop.inventory.internal;

import com.example.shop.inventory.InventoryAvailability;
import org.springframework.stereotype.Service;

@Service
class DefaultInventoryAvailability implements InventoryAvailability {

    private final InventoryRepository repository;

    DefaultInventoryAvailability(InventoryRepository repository) {
        this.repository = repository;
    }

    @Override
    public boolean hasAvailableStock(String sku, int quantity) {
        return repository.availableQuantity(sku) >= quantity;
    }
}
```

Module `order` chỉ phụ thuộc vào API:

```java
package com.example.shop.order.internal;

import com.example.shop.inventory.InventoryAvailability;
import org.springframework.stereotype.Service;

@Service
class PlaceOrderService {

    private final InventoryAvailability inventory;

    PlaceOrderService(InventoryAvailability inventory) {
        this.inventory = inventory;
    }

    boolean canPlace(String sku, int quantity) {
        return inventory.hasAvailableStock(sku, quantity);
    }
}
```

Spring có thể inject bean `DefaultInventoryAvailability` vào constructor thông qua kiểu interface `InventoryAvailability`. Module `order` không cần biết implementation nằm ở package nào, repository được tạo ra sao hoặc dữ liệu được lưu trữ bằng công nghệ gì.

Đây là lợi ích quan trọng của encapsulation: module cung cấp kiểm soát hợp đồng, còn consumer chỉ phụ thuộc vào khả năng nghiệp vụ ổn định.

## 6. `allowedDependencies` không mở internal package

`allowedDependencies` xác định module nào hoặc named interface nào consumer được phép phụ thuộc. Thuộc tính này không biến package nội bộ của provider thành API.

Ví dụ, module `order` khai báo:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory"
)
package com.example.shop.order;
```

Khai báo này cho phép `order` phụ thuộc vào module `inventory` theo phạm vi API được công bố của module đó. Nó không cho phép import tùy ý `inventory.internal.InventoryRepository`.

Hai câu hỏi phải được trả lời riêng:

1. **Dependency tới module nào được phép?** Xem `allowedDependencies` của module tiêu thụ.
2. **Package nào của module cung cấp được expose?** Xem package gốc, `@NamedInterface` và kiểu module (`CLOSED` hoặc `OPEN`).

Một dependency có thể được liệt kê trong whitelist nhưng vẫn vi phạm encapsulation nếu consumer truy cập package con chưa được expose.

## 7. Khi cần chia sẻ một package con, dùng Named Interface

Đôi khi module khác thực sự cần một nhóm kiểu trong package con. Khi đó, có thể công bố đúng package bằng `@NamedInterface` thay vì mở toàn bộ module.

Ví dụ module `inventory` có package `spi`:

```java
@org.springframework.modulith.NamedInterface("spi")
package com.example.shop.inventory.spi;
```

Hợp đồng được công bố trong package đó:

```java
package com.example.shop.inventory.spi;

public interface StockReservation {

    boolean reserve(String sku, int quantity);
}
```

Module `order` khai báo dependency đúng named interface:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::spi"
)
package com.example.shop.order;
```

Lúc này, `order` được phép tham chiếu các kiểu thuộc `inventory.spi`. Các package con khác như `inventory.internal` vẫn bị chặn vì module `inventory` tiếp tục là closed.

Nếu `order` cần cả API package gốc và named interface `spi`, khai báo cả hai phạm vi:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = { "inventory", "inventory::spi" }
)
package com.example.shop.order;
```

Hãy expose đúng nhóm hợp đồng cần chia sẻ. Không đánh dấu `internal` thành named interface chỉ để làm cho lỗi verify biến mất.

## 8. So sánh Closed, Named Interface và Open module

Ba lựa chọn này tạo ra phạm vi truy cập khác nhau:

| Cách tổ chức | Package gốc | Package con được chọn | Các package con còn lại |
|---|---|---|---|
| Closed mặc định | Được expose | Không có, trừ khi khai báo named interface | Internal |
| Closed + Named Interface | Được expose | Được expose theo tên | Internal |
| Open module | Được expose | Được expose | Được expose |

Open module được khai báo tại package gốc:

```java
@org.springframework.modulith.ApplicationModule(
    type = org.springframework.modulith.ApplicationModule.Type.OPEN
)
package com.example.shop.legacyinventory;
```

Khi module open, mọi package thuộc module đều nằm trong bề mặt được expose theo mô hình Spring Modulith. Điều này làm mất sự phân biệt internal package đối với module consumer. Chỉ nên chọn khi toàn bộ package thực sự được thiết kế để chia sẻ hoặc trong một giai đoạn chuyển đổi có chủ đích.

Nếu chỉ cần một package con, named interface giữ phạm vi công bố nhỏ và dễ quản lý hơn.

## 9. Package tên `internal` không phải yếu tố duy nhất

Spring Modulith không yêu cầu package nội bộ phải có tên `internal`. Quy tắc closed áp dụng cho các package con của module chưa được expose, bất kể tên gọi.

Ví dụ các package sau đều là internal theo vị trí nếu không có metadata công bố:

```text
com.example.shop.inventory
├── InventoryAvailability.java
├── application
├── domain
├── persistence
├── repository
└── adapter
```

Nếu module khác tham chiếu `com.example.shop.inventory.persistence.JpaInventoryRepository`, dependency đó cũng vi phạm encapsulation như tham chiếu `inventory.internal.JpaInventoryRepository`.

Tên package giúp con người hiểu ý định tổ chức mã. Quy tắc kiến trúc được quyết định bởi vị trí package và metadata expose, không chỉ bởi từ `internal`.

## 10. Cách đọc lỗi encapsulation

Khi `ApplicationModules.verify()` báo một module truy cập internal package, hãy lần theo các thông tin sau:

1. **Consumer:** module nào chứa lớp đang import hoặc tham chiếu kiểu bị báo lỗi?
2. **Provider:** kiểu được tham chiếu thuộc module nào?
3. **Package của kiểu đích:** kiểu nằm trong package gốc hay package con?
4. **Metadata expose:** package con đã được đánh dấu `@NamedInterface` chưa, hoặc provider có phải open module không?
5. **Whitelist:** consumer có khai báo dependency phù hợp trong `allowedDependencies` không?
6. **Ý định nghiệp vụ:** consumer có thực sự cần kiểu đó, hay chỉ cần một capability có thể cung cấp qua API gốc?

Ví dụ, nếu lỗi chỉ ra `order` truy cập `InventoryRepository` trong `inventory.internal`, hướng xử lý thường là thay dependency bằng `InventoryAvailability` ở package gốc. Nếu repository thực sự là một hợp đồng tích hợp cần chia sẻ, hãy thiết kế một named interface chuyên biệt với kiểu API phù hợp, thay vì expose repository triển khai.

## 11. Kiểm tra module boundary tự động

Đưa `ApplicationModules.verify()` vào test suite để kiểm tra các module trong toàn ứng dụng:

```java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleEncapsulation() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Khi một module closed bị tham chiếu qua package con chưa expose, kiểm thử kiến trúc sẽ thất bại. Sau khi chuyển consumer sang API package gốc hoặc named interface, chạy lại test để xác nhận dependency phù hợp.

Kiểm tra kiến trúc này khác với Spring context test:

- `ApplicationModules.verify()` kiểm tra tham chiếu giữa module, encapsulation và các quy tắc dependency.
- `@SpringBootTest` hoặc context test xác nhận bean được đăng ký, dependency injection hoạt động và ứng dụng có thể khởi tạo.

Một bean implementation nội bộ vẫn có thể được component scan và inject qua interface công khai. Điều đó không yêu cầu consumer import implementation class.

## 12. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| Lớp `public` có thể được module khác sử dụng tự do | Java cho phép truy cập kiểu, nhưng Spring Modulith vẫn chặn tham chiếu tới internal sub-package của closed module. |
| Chỉ package tên `internal` bị chặn | Mọi package con chưa expose đều là internal theo mô hình, kể cả `persistence`, `domain` hoặc `repository`. |
| Thêm module vào `allowedDependencies` sẽ mở mọi package của module đó | Whitelist cho phép dependency tới module; encapsulation vẫn giới hạn package được tham chiếu. |
| `@NamedInterface` tạo một module mới | Nó công bố package con như một nhóm API thuộc module hiện tại. |
| Đổi tên package `internal` thành `api` tự làm nó public | Cần metadata expose phù hợp; đổi tên folder không thay đổi module boundary. |
| Component scan đăng ký bean nghĩa là module khác được phép import lớp đó | Bean registration và module encapsulation là hai cơ chế riêng. |
| Dùng Open module luôn là cách sửa đúng | Open expose toàn bộ package; nếu chỉ cần một nhóm API, Named Interface giữ phạm vi hẹp hơn. |

## 13. Checklist giữ internal sub-package được đóng

- [ ] Xác định package gốc và các package con của từng module.
- [ ] Giữ module ở trạng thái `CLOSED` trừ khi có lý do kiến trúc rõ ràng để mở.
- [ ] Đặt hợp đồng consumer cần dùng trong package gốc hoặc named interface phù hợp.
- [ ] Giữ repository, adapter và implementation trong package con nội bộ.
- [ ] Không xem modifier `public` là cách công bố API module.
- [ ] Khai báo `allowedDependencies` ở consumer khi cần whitelist.
- [ ] Nếu expose package con, dùng `@NamedInterface` và dependency `module::interface`.
- [ ] Không dùng `OPEN` chỉ để bỏ qua một lỗi truy cập internal.
- [ ] Chạy `ApplicationModules.verify()` trong kiểm thử kiến trúc.
- [ ] Chạy context test để xác nhận bean implementation được inject qua API.

## 14. Kết luận

Trong Spring Modulith, internal sub-package của một closed module bị chặn khi module khác tham chiếu trực tiếp các kiểu trong đó, kể cả khi các kiểu được khai báo `public`. Quy tắc này dựa trên ranh giới package và metadata expose của module, bổ sung cho Java visibility. Tên `internal` chỉ là quy ước dễ đọc; mọi package con chưa được công bố đều thuộc phần nội bộ.

Khi consumer cần một khả năng nghiệp vụ, hãy đưa hợp đồng ổn định vào package gốc và để implementation cùng repository ở bên trong module sở hữu. Nếu cần chia sẻ một package con, expose đúng package bằng `@NamedInterface` và khai báo dependency tương ứng. `allowedDependencies` kiểm soát module consumer được phép phụ thuộc, còn `ApplicationModules.verify()` giúp phát hiện truy cập internal trái phép. Nhờ vậy, module có thể thay đổi phần triển khai mà không làm lộ chi tiết nội bộ cho các module khác.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Application Modules and Module Structure](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith — `@ApplicationModule` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith — `@NamedInterface` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/NamedInterface.html)
