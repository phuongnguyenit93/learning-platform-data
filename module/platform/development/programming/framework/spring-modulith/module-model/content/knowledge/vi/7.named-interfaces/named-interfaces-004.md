# Đặt tên named interface theo capability

Bài này thuộc chương **Named Interfaces** của module **SPRING_MODULITH_MODULE_MODEL**. Spring Modulith giúp xác định ranh giới nghiệp vụ, API công khai và phụ thuộc giữa các package trong một ứng dụng Spring Boot. Khi một application module cần công khai một phần API nằm trong package con, named interface cho phép đặt tên rõ ràng cho phần hợp đồng đó.

Tên named interface nên mô tả **capability mà package cung cấp cho module khác**. Cách đặt tên này giúp người sử dụng hiểu họ đang phụ thuộc vào năng lực nào, đồng thời giúp nhóm giới hạn phụ thuộc theo ý nghĩa nghiệp vụ thay vì theo cấu trúc kỹ thuật bên trong.

## 1. Named interface đặt tên cho phần API được công khai

Theo quy ước mặc định, package gốc của application module là API mặc định của module. Những package con thuộc phần nội bộ, trừ khi được công khai có chủ đích.

Spring Modulith hỗ trợ annotation `@NamedInterface` để công khai một package con dưới một tên xác định. Ví dụ, module inventory có thể công khai khả năng kiểm tra tồn kho trong package:

~~~text
com.acme.shop.inventory
├── InventoryApplicationService.java
├── availability
│   ├── package-info.java
│   └── StockAvailability.java
└── internal
    ├── persistence
    └── reservation
~~~

File `package-info.java` của package availability:

~~~java
@org.springframework.modulith.NamedInterface("availability")
package com.acme.shop.inventory.availability;
~~~

Kiểu hợp đồng được công khai:

~~~java
package com.acme.shop.inventory.availability;

public interface StockAvailability {

    boolean hasAvailableStock(String productCode, int quantity);
}
~~~

Named interface có tên `availability`. Module khác có thể phụ thuộc vào hợp đồng trong package này theo tên đó. Các package nội bộ khác của inventory vẫn được giữ kín theo quy ước module.

## 2. Vì sao tên nên phản ánh capability?

Tên named interface là một phần của ngôn ngữ kiến trúc. Khi một module khai báo phụ thuộc, tên đó xuất hiện trong cấu hình và cho người đọc biết module đang sử dụng năng lực nào.

Ví dụ, module inventory có thể cung cấp nhiều năng lực:

- `availability`: tra cứu khả năng cung ứng hàng.
- `reservation`: giữ một lượng hàng cho đơn hàng.
- `replenishment`: cung cấp thông tin hoặc hợp đồng liên quan đến bổ sung tồn kho.

Các tên này nói về trách nhiệm nghiệp vụ mà bên sử dụng cần đến. Người đọc có thể hiểu ý định của phụ thuộc mà không cần biết package đang chứa controller, service hay adapter nào.

Ngược lại, những tên như `service`, `repository`, `controller`, `impl` hoặc `internal-api` thường mô tả cách triển khai. Chúng không cho biết bên sử dụng đang cần capability gì và có thể thay đổi khi nhóm tổ chức lại technical layer.

Một named interface nên trả lời câu hỏi: **“Module khác được phép sử dụng năng lực nào của module này?”**

## 3. Phân biệt tên module, tên package và tên named interface

Ba khái niệm này có vai trò khác nhau:

| Thành phần | Ví dụ | Ý nghĩa |
|---|---|---|
| Tên module | `inventory` | Định danh application module được khám phá từ package của ứng dụng. |
| Tên package | `com.acme.shop.inventory.availability` | Vị trí Java chứa các kiểu thuộc hợp đồng availability. |
| Tên named interface | `availability` | Tên API có chủ đích mà module inventory công khai. |

Trong khai báo phụ thuộc, Spring Modulith sử dụng dạng `module::named-interface`. Ví dụ `inventory::availability` có nghĩa là module sử dụng được phép phụ thuộc vào named interface availability của module inventory.

Tên named interface được khai báo trong `@NamedInterface` phải khớp với phần tên được tham chiếu. Tên package Java và tên named interface có liên quan đến cùng một phần mã nguồn nhưng không phải là một khái niệm thay thế cho nhau.

## 4. Ví dụ hoàn chỉnh: order chỉ phụ thuộc capability availability

Giả sử module order cần biết có đủ hàng để chấp nhận đơn hay không. Module inventory công khai capability availability.

Ở phía inventory, package được đánh dấu:

~~~java
@org.springframework.modulith.NamedInterface("availability")
package com.acme.shop.inventory.availability;
~~~

Hợp đồng:

~~~java
package com.acme.shop.inventory.availability;

public interface StockAvailability {

    boolean hasAvailableStock(String productCode, int quantity);
}
~~~

Phần triển khai có thể đặt trong package nội bộ của inventory:

~~~java
package com.acme.shop.inventory.internal;

import com.acme.shop.inventory.availability.StockAvailability;
import org.springframework.stereotype.Component;

@Component
class DefaultStockAvailability implements StockAvailability {

    @Override
    public boolean hasAvailableStock(String productCode, int quantity) {
        // Tra cứu tồn kho và áp dụng quy tắc giữ hàng của inventory.
        return true;
    }
}
~~~

Module order sử dụng hợp đồng công khai:

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

Module order khai báo phụ thuộc được phép trong `package-info.java` của package gốc:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {"inventory::availability"}
)
package com.acme.shop.order;
~~~

Cấu hình này thể hiện ý định rằng order được phép sử dụng named interface availability của inventory. Order không cần phụ thuộc vào repository, entity hoặc thuật toán nội bộ để kiểm tra tồn kho.

Ví dụ minh họa hợp đồng và ranh giới kiến trúc. Cách đăng ký bean, cấu hình component scanning và xử lý giao dịch cần phù hợp với cấu trúc ứng dụng thực tế.

## 5. Chọn tên theo capability, không theo lớp triển khai

Một capability có thể được triển khai bằng nhiều lớp hoặc nhiều technical layer. Tên named interface nên ổn định qua những thay đổi triển khai đó.

| Tên nên cân nhắc | Tên nên tránh | Lý do |
|---|---|---|
| `availability` | `stock-service` | Tên capability diễn tả điều bên sử dụng cần; tên service mô tả loại lớp. |
| `reservation` | `reservation-impl` | Hợp đồng giữ hàng có thể có nhiều cách triển khai. |
| `pricing` | `pricing-repository` | Năng lực định giá không đồng nhất với truy cập dữ liệu. |
| `customer-profile` | `customer-dto` | Capability có ý nghĩa nghiệp vụ hơn một định dạng truyền dữ liệu. |
| `fulfillment` | `fulfillment-controller` | Hợp đồng nghiệp vụ không nên phụ thuộc vào giao thức HTTP. |

Tên cụ thể cần phản ánh ngôn ngữ mà nhóm dùng để mô tả nghiệp vụ. Bảng trên chỉ là ví dụ; một capability có thể cần tên khác nếu thuật ngữ miền của ứng dụng khác.

Tránh đặt tên quá chung như `api`, `common` hoặc `shared` nếu module thực sự đang công khai một capability cụ thể. Tên chung làm mờ ý nghĩa của phụ thuộc và khó giúp người review đánh giá module đang sử dụng phần nào.

## 6. Một module có thể công khai nhiều named interface

Một application module có thể cung cấp nhiều capability độc lập cho các module sử dụng khác nhau. Khi đó, có thể đặt các package và tên riêng:

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

Khai báo package availability:

~~~java
@org.springframework.modulith.NamedInterface("availability")
package com.acme.shop.inventory.availability;
~~~

Khai báo package reservation:

~~~java
@org.springframework.modulith.NamedInterface("reservation")
package com.acme.shop.inventory.reservation;
~~~

Một module chỉ cần kiểm tra tồn kho có thể được phép phụ thuộc vào `inventory::availability`. Module xử lý đơn hàng có thể cần cả hai capability nếu nghiệp vụ yêu cầu:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "inventory::availability",
        "inventory::reservation"
    }
)
package com.acme.shop.order;
~~~

Việc chia named interface nên dựa trên những hợp đồng có mục đích sử dụng khác nhau. Không cần tạo một named interface cho từng lớp hoặc từng package con nhỏ nếu chúng cùng thuộc một capability và không có nhu cầu giới hạn phụ thuộc riêng.

## 7. Đặt tên đủ ổn định để hỗ trợ thay đổi

Tên named interface được tham chiếu trong cấu hình phụ thuộc, nên đổi tên có thể ảnh hưởng đến các module sử dụng. Trước khi đặt tên, hãy cân nhắc:

- **Ngữ nghĩa có ổn định không?** Tên nên còn đúng khi module thay đổi framework, adapter hoặc cách lưu trữ.
- **Phạm vi có đủ rõ không?** Một tên như `availability` cần chỉ ra loại khả năng cung ứng nào nếu miền có nhiều khái niệm gần nhau.
- **Bên sử dụng có hiểu được không?** Tên nên quen thuộc với ngôn ngữ nghiệp vụ và dễ giải thích trong review.
- **Có đang công khai quá rộng không?** Một named interface không nên gom nhiều capability chỉ vì chúng cùng nằm trong một package.
- **Có trùng với ý nghĩa khác không?** Nếu cùng một tên được hiểu khác nhau ở nhiều nơi, hãy làm rõ ngữ cảnh hoặc chọn tên cụ thể hơn.

Nếu cần thay đổi tên, hãy cập nhật annotation và các khai báo phụ thuộc liên quan trong cùng một thay đổi có kiểm soát. Với thay đổi API không tương thích, cần xem xét cách chuyển đổi để các module sử dụng không bị hỏng.

## 8. Kiểm chứng tên và phụ thuộc bằng Spring Modulith

Sau khi đánh dấu named interface và khai báo `allowedDependencies`, có thể kiểm tra mô hình ứng dụng:

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

Kiểm tra kiến trúc giúp phát hiện các phụ thuộc không phù hợp với ranh giới đã mô hình hóa, chẳng hạn module order truy cập package nội bộ của inventory hoặc sử dụng một named interface không được cho phép.

Khi kiểm tra thất bại, hãy xem lại cả hai phía:

1. Package cung cấp đã được đánh dấu đúng bằng `@NamedInterface` chưa?
2. Tên trong annotation có khớp với tên được tham chiếu trong `allowedDependencies` không?
3. Tên module trong khai báo có khớp với module được khám phá không?
4. Module sử dụng có thực sự cần capability đó không?
5. Kiểu được import có nằm trong package được công khai hay đang nằm trong package nội bộ?

`verify()` kiểm tra các quy tắc kiến trúc được mô hình biểu diễn. Nó không tự đánh giá một tên có đúng ngôn ngữ nghiệp vụ hay một capability có được phân chia hợp lý hay không. Phần đó cần được nhóm xem xét trong thiết kế và review.

## 9. Quy trình đặt tên trong một lần thiết kế

Có thể thực hiện theo trình tự sau:

1. **Xác định bên cung cấp.** Tìm application module sở hữu hành vi hoặc dữ liệu nghiệp vụ.
2. **Xác định nhu cầu bên sử dụng.** Mô tả hành động hoặc thông tin mà module khác thực sự cần.
3. **Nhóm hợp đồng theo capability.** Đặt những kiểu cùng phục vụ một mục đích vào package con phù hợp.
4. **Chọn tên ngắn, có nghĩa nghiệp vụ.** Ưu tiên tên như availability, reservation hoặc pricing thay cho service, repository hay impl.
5. **Đánh dấu package.** Khai báo `@NamedInterface("tên-capability")` trong `package-info.java`.
6. **Giới hạn phụ thuộc.** Dùng `allowedDependencies` với dạng `module::named-interface` khi muốn khai báo chính xác capability được phép sử dụng.
7. **Kiểm tra và review.** Chạy `ApplicationModules.verify()` và xem xét tên từ góc nhìn của cả bên cung cấp lẫn bên sử dụng.

Nếu một named interface có quá nhiều kiểu không liên quan, hãy tách theo capability thực sự. Nếu có nhiều named interface gần như luôn được sử dụng cùng nhau và không cần kiểm soát riêng, hãy xem lại liệu chúng có nên thuộc cùng một hợp đồng hay không.

## Ghi nhớ

Tên named interface nên diễn tả **capability nghiệp vụ mà module công khai**. Tên như `availability`, `reservation` hoặc `pricing` giúp người đọc hiểu ý nghĩa của phụ thuộc; tên như `service`, `repository` hoặc `impl` chỉ mô tả chi tiết kỹ thuật và dễ trở nên lỗi thời khi triển khai thay đổi.

Kết hợp `@NamedInterface` với `allowedDependencies` giúp module cung cấp công khai đúng phần hợp đồng và module sử dụng khai báo rõ capability mà nó cần. Hãy chọn tên theo ngôn ngữ nghiệp vụ, giữ phạm vi nhỏ, ổn định và kiểm chứng phụ thuộc bằng `ApplicationModules.verify()`.
