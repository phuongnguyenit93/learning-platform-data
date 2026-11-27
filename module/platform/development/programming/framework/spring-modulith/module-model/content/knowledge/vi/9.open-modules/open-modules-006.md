# Open module khác module đóng gói tốt ra sao?

Một application module được thiết kế tốt cần cho các module khác biết chúng được phép sử dụng phần nào. Với Spring Modulith, mô hình mặc định là **closed module**: module công bố API qua package gốc và các Named Interface được chọn; những package con còn lại là phần triển khai nội bộ. **Open module** nới lỏng ranh giới đó để các module khác có thể truy cập cả những type nằm trong package con.

Open module hữu ích khi đưa một hệ thống cũ vào Spring Modulith theo từng bước. Một codebase đã có nhiều module phụ thuộc chéo vào package con có thể chưa sẵn sàng đóng gói ngay. Tuy nhiên, khi một ứng dụng đã được tổ chức mô-đun rõ ràng, việc để module ở trạng thái open thường cho thấy API và ownership chưa được phân định tốt.

## 1. Closed module bảo vệ phần triển khai nội bộ

Theo cách phát hiện mặc định, Spring Modulith xem mỗi package con trực tiếp của package ứng dụng là một application module. Giả sử lớp Spring Boot nằm trong `com.acme.shop`:

```text
com.acme.shop
├── ShopApplication.java
├── inventory
│   ├── InventoryManagement.java
│   └── internal
│       ├── InventoryService.java
│       └── StockRepository.java
└── order
    └── OrderService.java
```

Trong ví dụ này, `inventory` là root package của module `inventory`. Với module đóng mặc định:

- Các type công khai trong `com.acme.shop.inventory` tạo thành API mặc định.
- `com.acme.shop.inventory.internal` là package nội bộ.
- Module `order` có thể tham chiếu `InventoryManagement`.
- Module `order` không được tham chiếu trực tiếp `InventoryService` hoặc `StockRepository` trong package nội bộ.

Ví dụ API được công bố:

```java
package com.acme.shop.inventory;

public interface InventoryManagement {

    boolean hasAvailableStock(Sku sku, int quantity);
}
```

Module `order` sử dụng hợp đồng đó:

```java
package com.acme.shop.order;

import com.acme.shop.inventory.InventoryManagement;

class OrderService {

    private final InventoryManagement inventory;

    OrderService(InventoryManagement inventory) {
        this.inventory = inventory;
    }
}
```

Nếu `order` import `com.acme.shop.inventory.internal.StockRepository`, Java có thể vẫn biên dịch khi lớp đó là `public`. Tuy nhiên, `ApplicationModules.verify()` phát hiện module đang truy cập package nội bộ của module đóng và báo vi phạm kiến trúc.

Đóng gói giúp `inventory` thay đổi repository, cách tính tồn kho hoặc cấu trúc triển khai mà không buộc `order` phải biết những chi tiết đó. API trở thành hợp đồng ổn định giữa hai module.

## 2. Open module cho phép truy cập cả package con

Khi một module được đánh dấu `OPEN`, Spring Modulith nới lỏng việc kiểm tra truy cập vào các type nội bộ. Các type trong package con cũng được xem là có thể truy cập từ module khác. Nếu type chưa được gán rõ ràng vào Named Interface, nó được đưa vào unnamed interface của module.

Để mở module `inventory`, tạo hoặc sửa `package-info.java` ở root package `com.acme.shop.inventory`:

```java
@org.springframework.modulith.ApplicationModule(
    type = org.springframework.modulith.ApplicationModule.Type.OPEN
)
package com.acme.shop.inventory;
```

Sau khai báo này, module khác có thể tham chiếu type trong `inventory.internal` mà không bị quy tắc đóng gói của Spring Modulith từ chối. Ví dụ, một module cũ có thể đang gọi thẳng `StockRepository` hoặc `InventoryService`; trạng thái open giúp đưa cấu trúc hiện tại vào mô hình Modulith trước khi nhóm có thời gian thiết kế lại API.

Open module không làm các lớp `private` hoặc package-private trở thành `public` theo quy tắc Java. Nó thay đổi cách Spring Modulith xem xét boundary ở cấp kiến trúc. Một lớp vẫn phải có mức truy cập Java phù hợp để code ở package khác tham chiếu được nó.

## 3. So sánh Closed và Open

| Khía cạnh | Closed module | Open module |
| --- | --- | --- |
| Phạm vi API | Package gốc và Named Interface được công bố | Các type trong package gốc và package con đều được xem là có thể truy cập; type được gán Named Interface vẫn giữ tên interface đó |
| Truy cập package nội bộ | Bị từ chối khi module khác tham chiếu | Được cho phép trong kiểm tra kiến trúc |
| Encapsulation | Có thể giữ chi tiết triển khai bên trong | Không tạo ranh giới nội bộ đáng tin cậy giữa các package của module |
| Thay đổi implementation | Có thể thay đổi nội bộ mà ít ảnh hưởng consumer | Consumer có thể phụ thuộc vào chi tiết triển khai, làm thay đổi lan rộng |
| Kiểm tra dependency cycle | Tham gia kiểm tra chu trình module | Bị loại khỏi thuật toán phát hiện chu trình |
| Trường hợp thường gặp | Module đã có API và ownership rõ | Module cũ đang chuyển đổi dần sang cấu trúc mô-đun |

Điểm khác biệt quan trọng nhất nằm ở hợp đồng mà module công bố. Closed module yêu cầu consumer sử dụng các điểm vào đã chọn. Open module cho phép consumer nhìn sâu vào cấu trúc bên trong, nên các package con dễ trở thành hợp đồng ngầm.

## 4. Open module được biểu diễn trong mô hình API như thế nào?

Spring Modulith xây dựng mô hình module từ package và metadata. Với module open, các type trong package con được thêm vào unnamed interface, trừ những type/package đã được gán rõ ràng vào Named Interface.

Có thể hình dung cấu trúc như sau:

```text
inventory (OPEN)
├── InventoryManagement.java       -> unnamed interface
├── internal
│   ├── InventoryService.java      -> unnamed interface
│   └── StockRepository.java       -> unnamed interface
└── events
    ├── package-info.java          -> Named Interface: events
    └── StockReserved.java         -> Named Interface: events
```

`InventoryManagement`, `InventoryService` và `StockRepository` đều thuộc unnamed interface trong ví dụ này. Package `events` được gán tên rõ ràng nên vẫn được nhận diện là Named Interface `events`.

Điều đó có nghĩa open module không bắt buộc phải xóa Named Interface. Tuy nhiên, nếu hầu hết package con đã có thể được truy cập, lợi ích của việc phân chia các hợp đồng công khai và nội bộ bị giảm đi đáng kể.

## 5. Open không có nghĩa là bỏ mọi quy tắc kiến trúc

`OPEN` tập trung vào việc module có che giấu các package nội bộ hay không. Nó không biến ứng dụng thành một tập hợp không có ranh giới và không thay đổi quyền truy cập của Java.

Một số điều cần phân biệt:

- **Module detection vẫn tồn tại:** module vẫn được nhận diện theo package và cấu hình Spring Modulith.
- **Java visibility vẫn có hiệu lực:** lớp package-private không thể được tham chiếu từ package khác chỉ vì module được mở.
- **Dependency vẫn cần được thiết kế:** module tiêu thụ vẫn có thể khai báo `allowedDependencies` để giới hạn module mà nó được phép sử dụng.
- **Kiểm tra chu trình bị suy giảm:** open module bị loại khỏi thuật toán phát hiện dependency cycle. Vì vậy, không nên dựa vào kết quả cycle verification để đánh giá đầy đủ các quan hệ đi qua module open.
- **Không phải cơ chế bảo mật runtime:** `OPEN` không phải thiết lập truy cập mạng, reflection hay quyền truy cập tiến trình; nó là metadata phục vụ mô hình và kiểm tra kiến trúc.

Đặc biệt, việc module open bị loại khỏi thuật toán phát hiện chu trình là một lý do nữa để dùng trạng thái này có chủ đích. Nếu module open nằm giữa nhiều quan hệ phụ thuộc, các vòng phụ thuộc đi qua nó có thể không được phát hiện như với những module đóng.

## 6. Vì sao Open module thường phù hợp với hệ thống cũ?

Một hệ thống phát triển lâu năm có thể đã tích lũy nhiều kiểu truy cập trực tiếp giữa các package:

```text
order ------> inventory.internal.StockRepository
shipping ---> inventory.internal.InventoryService
reporting --> inventory.internal.StockRepository
```

Các consumer có thể đã phụ thuộc vào nhiều chi tiết bên trong `inventory`. Nếu ngay lập tức chuyển `inventory` thành closed module, kiểm tra kiến trúc sẽ phát hiện nhiều vi phạm cùng lúc. Nhóm có thể cần một giai đoạn chuyển đổi để xác định consumer, gom các hợp đồng cần thiết và thay các tham chiếu trực tiếp.

Đánh dấu module open là một bước đệm cho phép bắt đầu áp dụng Spring Modulith mà chưa phải tái cấu trúc toàn bộ consumer ngay lập tức. Sau đó, nhóm có thể đóng gói từng phần:

1. Liệt kê các module đang truy cập package con của module open.
2. Phân loại tham chiếu nào là nhu cầu nghiệp vụ thực sự và tham chiếu nào chỉ là tiện lợi kỹ thuật.
3. Đưa các hợp đồng cần thiết vào package gốc hoặc Named Interface.
4. Thay consumer để gọi API hoặc lắng nghe event đã công bố.
5. Đóng module và chạy lại `ApplicationModules.verify()`.

Đây là cách chuyển đổi từng bước: có thể bắt đầu với module đang mở, sau đó thu hẹp API khi từng consumer được sửa.

## 7. Named Interface thường là lựa chọn tốt hơn khi chỉ cần mở một phần

Nếu chỉ một package con cần được module khác sử dụng, không nhất thiết phải mở toàn bộ module. Hãy công bố đúng package đó bằng `@NamedInterface`.

Ví dụ, module `inventory` muốn công bố các event trong package `inventory.events`:

```java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.inventory.events;
```

Module `shipping` có thể phụ thuộc vào đúng hợp đồng event:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory :: events"
)
package com.acme.shop.shipping;
```

Khi `inventory` là closed module, `shipping` được phép tham chiếu type trong `inventory.events` vì package đã được công bố, nhưng vẫn không được truy cập `inventory.internal`. Phạm vi công khai rõ ràng giúp nhóm biết package nào là hợp đồng và package nào có thể thay đổi tự do.

Nếu cần mở nhiều package con, hãy cân nhắc liệu chúng có thực sự là các hợp đồng công khai hay nên được gom vào một API nhỏ hơn. Việc tạo Named Interface cho mọi package cũng có thể làm API quá rộng; mỗi interface nên có mục đích và consumer cụ thể.

## 8. Kiểm chứng module sau khi đóng gói

Spring Modulith cung cấp `ApplicationModules.verify()` để kiểm tra cấu trúc module:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesApplicationModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Khi `inventory` là closed module, test sẽ phát hiện module khác tham chiếu type nội bộ trong `inventory.internal`. Sau khi chuyển tham chiếu sang `InventoryManagement` hoặc Named Interface phù hợp, kiểm tra có thể thành công nếu không còn vi phạm khác.

Nếu `inventory` được đánh dấu open, việc truy cập nội bộ của nó được cho phép trong kiểm tra boundary. Tuy nhiên, nhóm cần nhớ module open không tham gia thuật toán cycle detection. Hãy xem việc chuyển về closed là một phần của mục tiêu hoàn thiện kiến trúc, không chỉ là thay đổi annotation.

## 9. Khi nào nên dùng Open module?

| Tình huống | Lựa chọn nên cân nhắc |
| --- | --- |
| Module mới có API rõ và triển khai nội bộ riêng | Closed module, dùng package gốc và Named Interface |
| Module cũ có nhiều consumer đang truy cập package con | Tạm thời dùng Open trong quá trình chuyển đổi |
| Chỉ cần công bố một package event hoặc SPI | Closed module và Named Interface |
| Một module đã được modularize đầy đủ nhưng vẫn cần Open | Xem lại package structure, ownership và các dependency đang tồn tại |
| Muốn phát hiện đầy đủ dependency cycle liên quan đến module | Ưu tiên Closed để module tham gia cycle detection |

Trước khi mở module, hãy xác định lý do cụ thể: số lượng package con đang bị truy cập, số consumer bị ảnh hưởng và kế hoạch thu hẹp API. Nếu không có kế hoạch đóng lại, trạng thái open có thể trở thành lựa chọn lâu dài chỉ vì việc tái cấu trúc bị trì hoãn.

## 10. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu chính xác |
| --- | --- |
| Open module có nghĩa là mọi lớp Java tự động thành `public`. | `OPEN` thay đổi kiểm tra boundary của Spring Modulith; Java visibility vẫn có hiệu lực. |
| Open module có API rõ hơn closed module. | Open module cho phép truy cập rộng vào package con, nên API và implementation khó phân biệt hơn. |
| Chỉ cần mở module là không còn dependency violation. | Quy tắc truy cập internals được nới lỏng, nhưng các dependency khác và allowlist vẫn cần được thiết kế. |
| Open module vẫn được kiểm tra cycle giống closed module. | Open module bị loại khỏi thuật toán phát hiện dependency cycle. |
| Named Interface không cần thiết khi module open. | Named Interface vẫn có thể phân loại hợp đồng cụ thể, dù module open làm nhiều type khác cũng có thể truy cập. |
| Open module là cách tổ chức tốt nhất cho modular monolith. | Tài liệu Spring Modulith khuyến nghị xem Open chủ yếu như cầu nối cho codebase hiện hữu đang chuyển đổi. |

## 11. Ghi nhớ

Closed module bảo vệ implementation bằng cách chỉ công bố package gốc và các Named Interface đã chọn. Open module cho phép module khác truy cập các type trong package con; các type chưa được gán Named Interface được đưa vào unnamed interface. Vì vậy, Open giúp tích hợp dần một codebase cũ nhưng làm giảm mức đóng gói và khiến dependency đến chi tiết nội bộ trở nên dễ xảy ra.

`@ApplicationModule(type = Type.OPEN)` nên được dùng như một lựa chọn chuyển tiếp có lý do và có kế hoạch thu hẹp. Với module đã được tổ chức rõ, hãy ưu tiên closed module, công bố hợp đồng qua package gốc hoặc Named Interface và kiểm tra bằng `ApplicationModules.verify()`. Cách đó giữ API dễ hiểu, implementation dễ thay đổi và dependency graph có thể được kiểm soát tốt hơn.

## Tài liệu tham khảo

- [Spring Modulith Reference — Open Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html#modules.advanced.open)
- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith API — `ApplicationModule.Type`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.Type.html)
