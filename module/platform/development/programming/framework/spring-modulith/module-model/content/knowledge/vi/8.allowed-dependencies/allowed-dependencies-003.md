# Dependency tới named interface bằng module :: interface

Bài này thuộc chương **Allowed dependencies** của module **SPRING_MODULITH_MODULE_MODEL**. Spring Modulith giúp mô hình hóa ranh giới nghiệp vụ, API công khai và phụ thuộc giữa các package trong một ứng dụng Spring Boot. Khi một module chỉ cần sử dụng một phần API được công khai của module khác, cú pháp `module::interface` cho phép khai báo phụ thuộc đến đúng named interface đó.

Cú pháp này làm rõ hai điều: module nào cung cấp hợp đồng và module sử dụng được phép phụ thuộc vào phần API nào. Nhờ vậy, nhóm có thể giữ các package nội bộ được đóng kín và giới hạn bề mặt phụ thuộc theo capability.

## 1. Ý nghĩa của cú pháp module :: interface

Một khai báo như:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::availability"
)
package com.acme.shop.order;
~~~

có thể đọc là: module **order** được phép phụ thuộc vào named interface **availability** do module **inventory** công khai.

Hai phần của chuỗi có ý nghĩa riêng:

- **module** là tên application module cung cấp API, thường được suy ra từ package module.
- **interface** là tên named interface được khai báo bằng `@NamedInterface` trong package cung cấp.

Dấu phân cách `::` nối tên module với tên named interface. Trong mã cấu hình, viết liền không có khoảng trắng: `inventory::availability`.

Đây là tên tham chiếu ở cấp mô hình kiến trúc, không phải tên lớp Java và cũng không phải tên đầy đủ của package. Ví dụ, `inventory::availability` không phải `com.acme.shop.inventory.availability`; nó là định danh module cộng với định danh named interface.

## 2. Module cung cấp phải công khai named interface

Giả sử ứng dụng có package gốc `com.acme.shop` và module inventory:

~~~text
com.acme.shop
├── ShopApplication.java
├── inventory
│   ├── availability
│   │   ├── package-info.java
│   │   └── StockAvailability.java
│   └── internal
│       └── persistence
└── order
    └── internal
        └── application
~~~

Trong package `com.acme.shop.inventory.availability`, khai báo named interface bằng `package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("availability")
package com.acme.shop.inventory.availability;
~~~

Sau đó đặt các kiểu thuộc hợp đồng availability trong package đó:

~~~java
package com.acme.shop.inventory.availability;

public interface StockAvailability {

    boolean hasAvailableStock(String productCode, int quantity);
}
~~~

Annotation `@NamedInterface("availability")` đặt tên cho package được công khai. Giá trị `availability` chính là phần sau dấu `::` trong khai báo phụ thuộc.

Các kiểu triển khai nội bộ có thể nằm ở package khác, chẳng hạn `com.acme.shop.inventory.internal`. Module order chỉ cần sử dụng hợp đồng `StockAvailability`; nó không cần import repository, entity hay adapter nội bộ của inventory.

Nếu package chưa được đánh dấu bằng named interface, không nên giả định rằng chỉ cần viết chuỗi `inventory::availability` trong cấu hình là package đó tự động trở thành API. Phía cung cấp phải khai báo tên và phía sử dụng phải tham chiếu đúng tên đã công khai.

## 3. Module sử dụng khai báo dependency được phép

Phía module sử dụng đặt `@ApplicationModule` trong `package-info.java` của package gốc module đó.

Ví dụ, module order được phép sử dụng availability của inventory:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::availability"
)
package com.acme.shop.order;
~~~

Trong phần triển khai use case, order import hợp đồng công khai:

~~~java
package com.acme.shop.order.internal.application;

import com.acme.shop.inventory.availability.StockAvailability;

class PlaceOrderHandler {

    private final StockAvailability stockAvailability;

    PlaceOrderHandler(StockAvailability stockAvailability) {
        this.stockAvailability = stockAvailability;
    }

    boolean canPlace(String productCode, int quantity) {
        return stockAvailability.hasAvailableStock(productCode, quantity);
    }
}
~~~

Hãy chú ý vị trí của hai khai báo:

- `@NamedInterface("availability")` nằm ở package của module cung cấp: `com.acme.shop.inventory.availability`.
- `@ApplicationModule(allowedDependencies = ...)` nằm ở package gốc của module sử dụng: `com.acme.shop.order`.

Đặt annotation đúng vị trí giúp mô hình có đủ thông tin để xác định API được công khai và phụ thuộc được phép. Chuỗi `inventory::availability` phải khớp với tên module và tên named interface thực tế.

## 4. Phân biệt dependency tới module và dependency tới named interface

Một module có thể cung cấp API mặc định ở package gốc và một hoặc nhiều named interface ở package con. Cách khai báo cần thể hiện đúng phạm vi API mà module sử dụng cần.

| Cách khai báo | Ý nghĩa |
|---|---|
| `inventory` | Khai báo phụ thuộc đến module inventory theo tên module. |
| `inventory::availability` | Khai báo phụ thuộc đến named interface availability của inventory. |
| `inventory::reservation` | Khai báo phụ thuộc đến named interface reservation của inventory. |

Khi dùng cú pháp `module::interface`, nhóm có thể chỉ rõ capability được sử dụng. Ví dụ, order cần kiểm tra tồn kho thì phụ thuộc `inventory::availability`; nếu use case cần giữ hàng thì có thể cần thêm `inventory::reservation`.

Đừng nhầm tên named interface với tên lớp. Nếu package availability chứa nhiều hợp đồng như `StockAvailability` và `AvailableQuantity`, chúng vẫn thuộc named interface availability. Tên interface xác định một nhóm API được công khai, không phải từng kiểu riêng lẻ.

## 5. Khai báo nhiều named interface được phép

Một module có thể cần nhiều capability từ cùng một module cung cấp hoặc từ nhiều module khác nhau. Khi đó, dùng mảng trong thuộc tính `allowedDependencies`.

Ví dụ order cần kiểm tra và giữ hàng từ inventory, đồng thời cần thông tin khách hàng:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "inventory::availability",
        "inventory::reservation",
        "customer"
    }
)
package com.acme.shop.order;
~~~

Trong ví dụ này:

- `inventory::availability` cho phép order phụ thuộc vào named interface availability.
- `inventory::reservation` cho phép order phụ thuộc vào named interface reservation.
- `customer` khai báo phụ thuộc đến module customer theo tên module.

Chỉ liệt kê những phụ thuộc mà module thực sự cần. Danh sách ngắn và có chủ đích giúp người review hiểu hướng phối hợp giữa các capability, đồng thời hạn chế việc module sử dụng thêm những API không liên quan.

Khi chỉ cần một dependency, Java cho phép viết trực tiếp một chuỗi như `allowedDependencies = "inventory::availability"`. Khi cần nhiều dependency, dùng cú pháp mảng như ví dụ trên.

## 6. Ví dụ hai named interface trong cùng một module

Module inventory có thể công khai hai capability khác nhau:

~~~text
com.acme.shop.inventory
├── availability
│   ├── package-info.java
│   └── StockAvailability.java
├── reservation
│   ├── package-info.java
│   └── StockReservation.java
└── internal
    ├── persistence
    └── policy
~~~

Package availability:

~~~java
@org.springframework.modulith.NamedInterface("availability")
package com.acme.shop.inventory.availability;
~~~

Package reservation:

~~~java
@org.springframework.modulith.NamedInterface("reservation")
package com.acme.shop.inventory.reservation;
~~~

Hợp đồng reservation:

~~~java
package com.acme.shop.inventory.reservation;

import java.util.UUID;

public interface StockReservation {

    UUID reserve(String productCode, int quantity);
}
~~~

Module order có thể khai báo chỉ phụ thuộc availability nếu chỉ cần kiểm tra khả năng cung ứng:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::availability"
)
package com.acme.shop.order;
~~~

Nếu sau đó use case đặt hàng cần giữ hàng, nhóm phải đánh giá nhu cầu nghiệp vụ và cập nhật danh sách phụ thuộc:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "inventory::availability",
        "inventory::reservation"
    }
)
package com.acme.shop.order;
~~~

Việc thêm dependency là một thay đổi kiến trúc có chủ đích. Hãy xem module order thực sự cần hành vi nào và liệu reservation có phải capability phù hợp để công khai hay không.

## 7. Điều gì xảy ra khi khai báo sai?

Một số lỗi thường gặp:

| Lỗi | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Không tìm thấy module trong dependency | Tên module không khớp với module được khám phá. | Đối chiếu tên module với package module thực tế. |
| Không tìm thấy named interface | Giá trị trong chuỗi không khớp với tên trong `@NamedInterface`. | Kiểm tra annotation ở `package-info.java`. |
| Phụ thuộc vẫn bị báo vi phạm | Module đang import một package nội bộ hoặc API khác ngoài phạm vi được khai báo. | Kiểm tra package của kiểu được import và danh sách allowedDependencies. |
| Dùng tên package thay cho tên interface | Nhầm định danh package Java với định danh named interface. | Dùng dạng `module::interface`, trong đó interface là giá trị annotation. |
| Khai báo ở sai package | Annotation `@ApplicationModule` không nằm ở package gốc module sử dụng. | Đặt `package-info.java` tại package gốc của module consumer. |

Ví dụ, nếu inventory đánh dấu `availability` nhưng order khai báo `inventory::stock`, hai tên không khớp. Hãy sửa một phía để chúng thống nhất theo tên capability đã chọn.

Nếu order khai báo `inventory::availability` nhưng lại import `com.acme.shop.inventory.internal.persistence.StockRepository`, dependency thực tế đang vượt khỏi API được công khai. Hãy chuyển nhu cầu sang hợp đồng availability hoặc một capability phù hợp khác.

## 8. Kiểm chứng bằng ApplicationModules.verify()

Sau khi khai báo named interface và allowed dependencies, có thể kiểm tra mô hình ứng dụng trong một bài test:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Đặt kiểm tra này trong bộ test chạy thường xuyên và CI. Khi có một import mới làm module order phụ thuộc vào package nội bộ của inventory hoặc vào named interface không được cho phép, kiểm tra kiến trúc có thể phát hiện sai lệch.

Khi `verify()` thất bại, hãy xem thông báo để xác định module consumer, module provider và kiểu/package gây ra phụ thuộc. Sau đó kiểm tra:

1. Module provider có khai báo named interface đúng chưa?
2. Tên interface trong annotation có trùng với phần sau `::` không?
3. Tên module trong dependency có chính xác không?
4. Module consumer có khai báo dependency ở package gốc của nó không?
5. Kiểu đang được sử dụng có nằm trong package được công khai không?

`verify()` kiểm tra các quy tắc kiến trúc mà mô hình biểu diễn. Nó không tự quyết định capability nào nên được công khai hoặc một dependency có hợp lý về nghiệp vụ hay không. Nhóm vẫn cần review ý nghĩa và phạm vi của từng hợp đồng.

## 9. Quy trình khai báo dependency tới named interface

Có thể áp dụng trình tự sau khi một module cần sử dụng capability từ module khác:

1. **Xác định module cung cấp.** Tìm module sở hữu hành vi hoặc dữ liệu nghiệp vụ cần dùng.
2. **Chọn capability cần công khai.** Xác định nhóm hợp đồng có ý nghĩa ổn định và phục vụ đúng nhu cầu bên sử dụng.
3. **Đặt package cho hợp đồng.** Gom các kiểu liên quan vào package con của module cung cấp.
4. **Đặt tên named interface.** Chọn tên theo capability, ví dụ availability hoặc reservation.
5. **Khai báo `@NamedInterface`.** Đặt annotation trong `package-info.java` của package cung cấp.
6. **Khai báo `allowedDependencies`.** Ở package gốc module sử dụng, tham chiếu theo dạng `module::interface`.
7. **Sử dụng đúng API.** Import các kiểu từ package được công khai, tránh tham chiếu package nội bộ.
8. **Chạy kiểm tra kiến trúc.** Dùng `ApplicationModules.verify()` để phát hiện phụ thuộc sai quy tắc.

Khi capability thay đổi tên hoặc package, hãy cập nhật annotation và các dependency liên quan như một thay đổi có kiểm soát. Tên named interface là một phần của hợp đồng kiến trúc, vì vậy nên thống nhất trước khi nhiều module phụ thuộc vào nó.

## Ghi nhớ

Cú pháp `module::interface` xác định một dependency từ module sử dụng tới named interface có tên của module cung cấp. Phần trước `::` là tên application module; phần sau là giá trị tên trong `@NamedInterface`. Provider công khai package bằng annotation, còn consumer khai báo phụ thuộc trong `@ApplicationModule(allowedDependencies = ...)` ở package gốc của mình.

Hãy chọn tên interface theo capability nghiệp vụ, tham chiếu đúng tên và chỉ cho phép những dependency cần thiết. Kết hợp khai báo này với `ApplicationModules.verify()` giúp giữ ranh giới API rõ ràng và kiểm soát phụ thuộc giữa các module trong ứng dụng Spring Boot.
