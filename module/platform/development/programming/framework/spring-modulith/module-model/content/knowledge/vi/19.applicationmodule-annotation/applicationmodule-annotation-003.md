# type OPEN và mô hình open module

`@ApplicationModule` cho phép khai báo một application module là `CLOSED` hoặc `OPEN` thông qua thuộc tính `type`. Mặc định, module là `CLOSED`: các module khác chỉ được truy cập API mà module chủ động công khai. Khi đặt `type = ApplicationModule.Type.OPEN`, Spring Modulith xem các kiểu nội bộ của module là có thể được module khác truy cập trong mô hình kiến trúc. Điều này giúp chuyển đổi codebase cũ từng bước, nhưng làm giảm mức độ đóng gói mà Spring Modulith có thể bảo vệ.

Trong phạm vi **SPRING_MODULITH_MODULE_MODEL**, `type OPEN` cần được hiểu như một lựa chọn về ranh giới module và cách kiểm chứng dependency. Nó không thay đổi Java access modifier, không tự đăng ký Spring bean và không cấp quyền bảo mật. Với ứng dụng mới, nên giữ module `CLOSED` và công khai đúng hợp đồng qua package gốc hoặc `NamedInterface`; chỉ dùng `OPEN` khi có lý do chuyển đổi rõ ràng.

## 1. ApplicationModule.Type có hai giá trị

`ApplicationModule.Type` là enum lồng trong annotation `@ApplicationModule`. API hiện hành có hai giá trị:

| Giá trị | Ý nghĩa | Hành vi kiến trúc |
|---|---|---|
| `CLOSED` | Module đóng | Chỉ công khai API được chọn; package nội bộ được bảo vệ khỏi dependency từ module khác |
| `OPEN` | Module mở | Cho phép module khác truy cập các kiểu nội bộ theo mô hình Spring Modulith; các kiểu trong module được đưa vào unnamed interface, trừ kiểu đã được gán vào named interface riêng |

Nếu bỏ thuộc tính `type`, giá trị mặc định là `CLOSED`:

```java
@org.springframework.modulith.ApplicationModule
package com.acme.shop.inventory;
```

Khai báo trên tương đương với:

```java
@org.springframework.modulith.ApplicationModule(
    type = org.springframework.modulith.ApplicationModule.Type.CLOSED
)
package com.acme.shop.inventory;
```

`ApplicationModule.Type` được giới thiệu từ Spring Modulith 1.2. Khi đọc code hoặc Javadoc của phiên bản đang dùng, hãy kiểm tra đúng version dependency của dự án vì các API và quy tắc có thể được mở rộng theo phiên bản.

## 2. Khai báo open module bằng package-info.java

Trong Java, cách phổ biến là đặt annotation trên `package-info.java` của package gốc module. Ví dụ, đánh dấu module `inventory` là open:

```java
@org.springframework.modulith.ApplicationModule(
    type = org.springframework.modulith.ApplicationModule.Type.OPEN
)
package com.acme.shop.inventory;
```

Có thể import annotation và enum để code gọn hơn:

```java
@ApplicationModule(type = ApplicationModule.Type.OPEN)
package com.acme.shop.inventory;

import org.springframework.modulith.ApplicationModule;
```

`@ApplicationModule` cũng có thể mang metadata khác như `id`, `displayName` và `allowedDependencies`. Các thuộc tính đó giải quyết những vấn đề riêng:

- `type` xác định module đóng hay mở.
- `id` xác định logical identifier của module.
- `displayName` cung cấp tên dễ đọc cho tài liệu.
- `allowedDependencies` giới hạn các module mà module hiện tại được phép phụ thuộc.

Ví dụ kết hợp metadata:

```java
@org.springframework.modulith.ApplicationModule(
    id = "inventory",
    displayName = "Inventory Management",
    type = org.springframework.modulith.ApplicationModule.Type.OPEN
)
package com.acme.shop.inventory;
```

Đánh dấu `OPEN` không thay thế việc tổ chức package. Module vẫn cần một package gốc rõ ràng và các package con được sắp xếp theo trách nhiệm.

## 3. CLOSED và OPEN khác nhau ở đâu?

Giả sử module `inventory` có cấu trúc:

```text
com.acme.shop.inventory
├── InventoryOperations.java          // API ở package gốc
├── api
│   ├── package-info.java              // Named Interface "api"
│   └── ReservationResult.java
└── internal
    ├── InventoryRepository.java
    ├── InventoryPolicy.java
    └── InventoryEntity.java
```

Với `CLOSED`, module khác được phép sử dụng API ở package gốc và named interface `api` đã công khai. Các kiểu trong `internal` là chi tiết triển khai; tham chiếu từ module khác vào các kiểu đó bị xem là vi phạm ranh giới.

Với `OPEN`, Spring Modulith đưa các kiểu trong package con vào unnamed interface, trừ những kiểu đã được gán vào named interface riêng. Do đó, `InventoryRepository`, `InventoryPolicy` và `InventoryEntity` có thể được module khác tham chiếu về mặt mô hình kiến trúc.

| Khía cạnh | `CLOSED` | `OPEN` |
|---|---|---|
| API mặc định | Package gốc của module | Unnamed interface bao gồm các kiểu trong module, kể cả subpackage |
| Named interface | Chỉ các package được công khai tường minh | Vẫn được giữ; kiểu thuộc named interface riêng không bị nhập vào unnamed interface |
| Truy cập package nội bộ từ module khác | Bị từ chối trong verification | Được cho phép theo mô hình module |
| Dependency cycle detection | Module tham gia kiểm tra chu kỳ | Open module bị loại khỏi thuật toán phát hiện chu kỳ |
| Mục đích điển hình | Bảo vệ ranh giới của module đã được tổ chức rõ | Hỗ trợ chuyển đổi codebase cũ theo từng bước |

## 4. Open module thay đổi khả năng truy cập theo hướng nào?

Giả sử `orders` cần dùng `InventoryRepository` nằm trong package nội bộ của `inventory`. Khi `inventory` là open module, dependency từ `orders` vào kiểu nội bộ đó được chấp nhận bởi quy tắc đóng gói của Spring Modulith:

```java
package com.acme.shop.inventory.internal;

import org.springframework.stereotype.Repository;

@Repository
public class InventoryRepository {

    public boolean hasAvailableStock(String sku) {
        // Chi tiết truy cập dữ liệu tồn kho.
        return true;
    }
}
```

Module `orders` có thể tham chiếu class này:

```java
package com.acme.shop.orders;

import com.acme.shop.inventory.internal.InventoryRepository;
import org.springframework.stereotype.Service;

@Service
public class OrderPlacement {

    private final InventoryRepository inventoryRepository;

    public OrderPlacement(InventoryRepository inventoryRepository) {
        this.inventoryRepository = inventoryRepository;
    }

    public boolean canPlaceOrder(String sku) {
        return inventoryRepository.hasAvailableStock(sku);
    }
}
```

Mối quan hệ module là:

```mermaid
flowchart LR
    O[orders] -->|uses internal type| I[inventory OPEN]
```

Với `inventory` ở trạng thái `CLOSED`, tham chiếu vào `inventory.internal` sẽ bị verification từ chối. Với `OPEN`, ranh giới này được nới lỏng và dependency được chấp nhận theo mô hình Spring Modulith.

Điểm quan trọng là hướng dependency. `OPEN` cho phép module khác truy cập internals của chính module được đánh dấu mở. Nó không có nghĩa `inventory` được tự do truy cập internals của mọi module khác. Nếu `inventory` tham chiếu package nội bộ của một module `CLOSED`, quy tắc bảo vệ của module đích vẫn được áp dụng.

## 5. OPEN không thay đổi Java access modifier

Spring Modulith kiểm tra cấu trúc và dependency ở cấp kiến trúc. Java compiler vẫn áp dụng các quy tắc truy cập của ngôn ngữ.

Ví dụ:

- Một class `public` trong package `inventory.internal` có thể được Java code ở package khác import nếu module và cấu hình kiến trúc cho phép.
- Một class package-private trong `inventory.internal` vẫn không thể được tham chiếu trực tiếp từ `orders`, vì Java không cho phép truy cập từ package khác.
- Một member `private` vẫn chỉ truy cập được trong phạm vi class chứa nó.

Vì vậy, `OPEN` không biến class package-private thành `public`, không bỏ qua kiểm tra compile và không thay đổi bytecode visibility. Nó chỉ thay đổi cách Spring Modulith xem xét ranh giới package trong mô hình module.

## 6. OPEN ảnh hưởng tới unnamed interface và NamedInterface

Trong module đóng, package gốc là API mặc định; package con chỉ được công khai khi được đánh dấu bằng `@NamedInterface`. Với module mở, tất cả các kiểu trong module, kể cả kiểu ở package con, được đưa vào unnamed interface, trừ các kiểu đã được gán vào named interface riêng.

Ví dụ, `inventory/api/package-info.java`:

```java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.inventory.api;
```

Nếu `inventory` là `OPEN`, các kiểu trong `inventory.internal` được xem là có thể truy cập qua unnamed interface; các kiểu trong `inventory.api` vẫn thuộc named interface `api`. Điều này giúp giữ cách phân nhóm named interface hiện có, nhưng làm cho phần còn lại của module rộng mở hơn.

Không nên hiểu rằng `OPEN` tự tạo một named interface có tên `internal`. Unnamed interface là bề mặt mặc định không có tên riêng. Khi cần khai báo dependency theo named interface, cú pháp qualified dependency vẫn sử dụng tên interface thực sự được đánh dấu.

## 7. allowedDependencies vẫn là một quy tắc riêng

`type = OPEN` và `allowedDependencies` giải quyết hai hướng khác nhau:

- `type = OPEN` quyết định module khác có thể truy cập internals của module được đánh dấu hay không.
- `allowedDependencies` trên module consumer giới hạn những module mà consumer được phép phụ thuộc vào.

Ví dụ, `orders` chỉ cho phép phụ thuộc vào module `inventory`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory"
)
package com.acme.shop.orders;
```

Khai báo này kiểm soát dependency đi ra từ `orders`. Nếu `inventory` là open module, các kiểu nội bộ của `inventory` được mở trong mô hình, nhưng điều đó không tự động cho phép `orders` phụ thuộc vào mọi module khác trong ứng dụng. Nếu `orders` có `allowedDependencies`, các dependency đi ra của nó vẫn phải tuân theo danh sách đó.

Hãy nhớ rằng `allowedDependencies` không sửa dependency cycle và không thay đổi Java access modifier. Nó là một allowlist kiến trúc riêng với thuộc tính `type`.

## 8. Ảnh hưởng tới ApplicationModules.verify()

`ApplicationModules.verify()` kiểm tra các quy tắc kiến trúc của mô hình, bao gồm dependency cycle, truy cập API module và các dependency được cho phép khi có cấu hình `allowedDependencies`.

Khi một module là `OPEN`:

1. Dependency từ module khác vào package nội bộ của module đó được chấp nhận theo quy tắc open module.
2. Các kiểu trong subpackage được đưa vào unnamed interface, trừ kiểu được gán vào named interface riêng.
3. Open module bị loại khỏi thuật toán phát hiện dependency cycle.

Điểm thứ ba cần đặc biệt lưu ý. Khi một module mở tham gia vào đường dependency khép kín, thuật toán cycle detection không xem module đó như một module đóng bình thường. Vì vậy, kết quả `verify()` thành công không chứng minh rằng mọi chu kỳ có liên quan tới open module đều đã được phát hiện.

Ví dụ test verification:

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

Test vẫn hữu ích để kiểm tra các quy tắc còn áp dụng, nhưng khi đọc kết quả cần nhớ giới hạn của open module. Không nên dùng `OPEN` như cách làm cho test pass khi có dependency nội bộ hoặc chu kỳ mà nhóm chưa giải quyết.

## 9. Khi nào nên dùng OPEN?

Spring Modulith chủ yếu định hướng tính năng này cho codebase cũ đang được chuyển dần sang cách tổ chức module khuyến nghị. Một hệ thống legacy có thể đã có nhiều tham chiếu xuyên package; đóng toàn bộ module ngay lập tức có thể yêu cầu một đợt refactor lớn.

`OPEN` có thể là bước chuyển tiếp khi:

- Nhóm mới bắt đầu đưa Spring Modulith vào codebase hiện có.
- Nhiều package con đã được các module khác tham chiếu trực tiếp.
- Chưa thể xác định và công khai tất cả API trong cùng một lần thay đổi.
- Nhóm có kế hoạch kiểm kê dependency và đóng module theo từng giai đoạn.

Với ứng dụng mới hoặc module đã có ranh giới rõ, nên giữ `CLOSED`. Nếu consumer chỉ cần một số kiểu trong package con, hãy công khai đúng package bằng `NamedInterface` thay vì mở toàn bộ module.

## 10. Quy trình chuyển open module về closed

Nếu đang dùng `OPEN` để chuyển đổi legacy, hãy đặt lộ trình đóng lại:

1. **Kiểm kê truy cập nội bộ.** Tìm các module đang tham chiếu package con của open module.
2. **Phân loại kiểu được dùng.** Xác định kiểu nào thực sự là hợp đồng nghiệp vụ và kiểu nào là repository, entity, mapper hoặc helper nội bộ.
3. **Tạo API ổn định.** Đưa hợp đồng cần chia sẻ vào package gốc hoặc named interface phù hợp.
4. **Chuyển consumer.** Thay tham chiếu tới internal type bằng API công khai; giữ implementation bên trong module sở hữu.
5. **Khai báo allowedDependencies.** Giới hạn module consumer vào các module/interface mà nó cần.
6. **Bỏ `type = OPEN`.** Để module trở về `CLOSED` mặc định hoặc khai báo `type = CLOSED` tường minh.
7. **Chạy verification.** Dùng `ApplicationModules.verify()` để phát hiện các tham chiếu nội bộ còn sót.
8. **Rà soát dependency cycle.** Xác nhận đồ thị module không còn chu kỳ sau khi open module được đóng.
9. **Ghi nhận kết quả.** Cập nhật sơ đồ module và tài liệu kiến trúc theo cấu trúc mới.

Sau khi module đã đóng, nếu verification báo một consumer truy cập package nội bộ, hãy xác định xem consumer có thật sự cần kiểu đó hay nên gọi một API nghiệp vụ khác. Không nên mở lại toàn bộ module chỉ để giữ một hoặc hai import cũ.

## 11. Những nhầm lẫn thường gặp

- **“OPEN là mặc định.”** Không đúng. `CLOSED` là giá trị mặc định của thuộc tính `type`.
- **“OPEN làm tất cả class thành public.”** Java access modifier vẫn được áp dụng; Spring Modulith chỉ nới lỏng ranh giới kiến trúc.
- **“OPEN chỉ mở package gốc.”** Các kiểu trong subpackage cũng được đưa vào unnamed interface, trừ kiểu đã thuộc named interface riêng.
- **“OPEN cho module này truy cập mọi module khác.”** Nó chỉ thay đổi khả năng truy cập internals của module được đánh dấu; module đó vẫn chịu quy tắc khi truy cập module khác.
- **“OPEN thay thế allowedDependencies.”** Hai thuộc tính giải quyết hai vấn đề riêng: đóng gói inbound access và giới hạn outgoing dependencies.
- **“verify() vẫn phát hiện mọi chu kỳ khi có OPEN.”** Open module bị loại khỏi thuật toán cycle detection; cần lưu ý giới hạn này khi đọc kết quả.
- **“OPEN là cơ chế bảo mật hoặc reflection của JPMS.”** Đây là metadata kiến trúc của Spring Modulith, không cấp quyền runtime, database hay reflection.
- **“Ứng dụng mới nên mở module để linh hoạt.”** Mở rộng internals làm tăng coupling và khiến việc thay đổi implementation khó kiểm soát hơn.

## Kết luận

`@ApplicationModule(type = ApplicationModule.Type.OPEN)` đánh dấu một application module không che giấu các kiểu nội bộ trong mô hình Spring Modulith. Các kiểu ở subpackage được đưa vào unnamed interface trừ kiểu đã thuộc named interface riêng; dependency từ module khác vào internals được chấp nhận; open module cũng bị loại khỏi thuật toán phát hiện dependency cycle. `CLOSED` vẫn là mặc định và là lựa chọn phù hợp khi muốn bảo vệ API rõ ràng. Hãy dùng `OPEN` như công cụ chuyển đổi legacy có thời hạn, sau đó đưa consumer về API công khai và đóng module lại.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Open Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — ApplicationModule.Type API](https://docs.spring.io/spring-modulith/docs/2.1.1/api/org/springframework/modulith/ApplicationModule.Type.html)
- [Spring Modulith — ApplicationModule annotation API](https://docs.spring.io/spring-modulith/docs/2.1.1/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
