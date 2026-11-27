# Thu hẹp open module theo từng bước

`@ApplicationModule(type = Type.OPEN)` giúp đưa một codebase cũ vào Spring Modulith mà chưa cần đóng gói lại toàn bộ các package con. Tuy nhiên, open module cho phép các module khác truy cập nhiều type nội bộ và đưa các type đó vào unnamed interface. Nếu giữ trạng thái này lâu dài, ranh giới kiến trúc sẽ khó được bảo vệ.

Vì vậy, hãy xem `OPEN` là một trạng thái chuyển tiếp. Ta có thể thu hẹp phạm vi API qua từng đợt: kiểm kê các truy cập hiện có, xác định hợp đồng cần duy trì, gom chúng vào base package hoặc named interface, chuyển từng caller sang hợp đồng đó, rồi đóng module và chạy kiểm tra kiến trúc.

## 1. Hiểu chính xác phạm vi của open module

Giả sử module `inventory` có cấu trúc:

```text
com.example.shop.inventory
├── InventoryManagement.java
├── api
│   └── StockReservation.java
├── service
│   └── StockService.java
└── persistence
    ├── StockRepository.java
    └── StockEntity.java
```

Khi `inventory` là open module:

- Các type ở base package tiếp tục thuộc unnamed interface mặc định.
- Các type ở sub-package cũng được đưa vào unnamed interface, trừ những type hoặc package được gán rõ ràng vào named interface.
- Module khác nhìn chung có thể truy cập type nội bộ của `inventory`.
- `inventory` bị loại khỏi thuật toán phát hiện chu trình phụ thuộc.

Khai báo open module trong `inventory/package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
    type = org.springframework.modulith.ApplicationModule.Type.OPEN
)
package com.example.shop.inventory;
```

Điều này giải thích vì sao chỉ thêm `@NamedInterface` hoặc chỉ chuyển một vài lớp ra base package chưa đủ để kết thúc quá trình. Khi module còn `OPEN`, những type nội bộ chưa được gán named interface vẫn nằm trong unnamed interface và có thể tiếp tục được caller sử dụng.

## 2. Bước đầu tiên: lập danh sách truy cập xuyên module

Trước khi thay đổi package, hãy tìm các module đang tham chiếu vào sub-package của `inventory`. Tập trung vào các import và chữ ký method có type thuộc `inventory.internal`, `inventory.persistence`, `inventory.service` hoặc các package con tương tự.

Có thể dùng tìm kiếm toàn workspace hoặc chức năng Find Usages của IDE. Mục tiêu là ghi lại quan hệ caller, type đang được dùng và mục đích nghiệp vụ của từng lần sử dụng.

Ví dụ bảng kiểm kê:

| Caller | Type đang dùng từ `inventory` | Mục đích | Hướng xử lý |
|---|---|---|---|
| `orders` | `StockRepository` | Đọc tồn kho trực tiếp | Thay bằng API kiểm tra tồn kho |
| `shipping` | `StockEntity` | Đọc số lượng và kho lưu trữ | Trả về DTO nghiệp vụ phù hợp |
| `reporting` | `StockService` | Lấy dữ liệu báo cáo | Tạo API truy vấn báo cáo có phạm vi rõ |
| `inventory` | `StockRepository` | Triển khai nội bộ | Giữ trong module |

Phân biệt caller bên ngoài module với code nội bộ của chính `inventory`. Mục tiêu là di chuyển dependency xuyên module; các lớp nội bộ vẫn có thể gọi repository và service nội bộ như trước.

## 3. Phân loại type thành API, SPI và implementation

Không phải mọi type đang bị sử dụng đều cần được công khai. Với mỗi type trong danh sách, hãy xác định vai trò của nó:

- **API nghiệp vụ:** thao tác mà module khác cần yêu cầu, chẳng hạn kiểm tra tồn kho hoặc giữ chỗ.
- **DTO/giá trị trả về:** dữ liệu ổn định mà caller cần để hoàn tất use case.
- **SPI:** hợp đồng mà module sở hữu muốn module khác triển khai hoặc cung cấp, nếu có nhu cầu thực tế.
- **Implementation:** entity, repository, adapter, service nội bộ và chi tiết framework; caller không nên phụ thuộc trực tiếp.

Ví dụ, `orders` cần biết một SKU có đủ hàng hay không. Nó không cần biết tồn kho được lưu trong bảng nào hoặc repository dùng JPA ra sao. Ta có thể đưa hợp đồng nghiệp vụ vào base package:

```java
package com.example.shop.inventory;

public interface StockAvailability {

    boolean isAvailable(String sku, int quantity);
}
```

Nếu caller cần thêm dữ liệu, hãy trả về một kiểu dữ liệu ổn định và có ý nghĩa nghiệp vụ thay vì đưa `StockEntity` ra ngoài:

```java
package com.example.shop.inventory;

public record StockPosition(
        String sku,
        int availableQuantity) {
}
```

Implementation vẫn nằm trong module:

```java
package com.example.shop.inventory.persistence;

import com.example.shop.inventory.StockAvailability;
import org.springframework.stereotype.Service;

@Service
class DefaultStockAvailability implements StockAvailability {

    private final StockRepository repository;

    DefaultStockAvailability(StockRepository repository) {
        this.repository = repository;
    }

    @Override
    public boolean isAvailable(String sku, int quantity) {
        return repository.findAvailableQuantityBySku(sku)
                .orElse(0) >= quantity;
    }
}
```

Ví dụ minh họa ranh giới hợp đồng. Trong dự án thực tế, kiểu trả về và tên method cần phản ánh use case, chính sách tồn kho và lỗi nghiệp vụ mà module muốn công bố.

## 4. Gom các hợp đồng theo named interface

Nếu module có nhiều nhóm API, không cần đặt tất cả vào base package. Hãy gom các hợp đồng liên quan vào sub-package và đánh dấu bằng `@NamedInterface`.

Ví dụ, module `inventory` có một nhóm API dành cho thao tác giữ chỗ:

```text
com.example.shop.inventory
├── InventoryManagement.java
├── reservation
│   ├── package-info.java
│   ├── StockReservation.java
│   └── ReservationResult.java
└── internal
    ├── StockRepository.java
    └── DefaultStockReservation.java
```

Nội dung `reservation/package-info.java`:

```java
@org.springframework.modulith.NamedInterface("reservation")
package com.example.shop.inventory.reservation;
```

Caller có thể khai báo dependency vào đúng hợp đồng:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::reservation"
)
package com.example.shop.orders;
```

Named interface chỉ nên chứa type thực sự là hợp đồng. Không đưa repository, entity hoặc service triển khai vào đó chỉ để làm cho kiểm thử qua. Khi module còn `OPEN`, các type chưa được gán named interface riêng vẫn nằm trong unnamed interface; việc chuyển type hợp đồng sang named interface giúp xác định rõ nhóm API cần giữ lại và cho phép caller giới hạn dependency bằng tên interface.

## 5. Chuyển caller theo từng nhóm nhỏ

Sau khi xác định API, hãy chuyển từng caller thay vì sửa tất cả cùng lúc. Với mỗi caller:

1. Thay import type nội bộ bằng interface hoặc DTO công khai.
2. Thay lời gọi repository/service nội bộ bằng method nghiệp vụ tương ứng.
3. Cập nhật dependency declaration của caller để chỉ cho phép module hoặc named interface cần dùng.
4. Chạy unit test và integration test liên quan đến use case của caller.
5. Tìm lại các import cũ để chắc chắn caller không còn phụ thuộc vào implementation.

Ví dụ, `orders` không còn inject `StockRepository` mà chỉ inject `StockAvailability`:

```java
package com.example.shop.orders.internal;

import com.example.shop.inventory.StockAvailability;
import org.springframework.stereotype.Service;

@Service
class OrderService {

    private final StockAvailability stockAvailability;

    OrderService(StockAvailability stockAvailability) {
        this.stockAvailability = stockAvailability;
    }

    void validateOrder(String sku, int quantity) {
        if (!stockAvailability.isAvailable(sku, quantity)) {
            throw new IllegalStateException("Không đủ hàng trong kho");
        }
    }
}
```

Khi một nhóm caller đã chuyển xong, có thể tiếp tục với nhóm kế tiếp. Điều này giúp mỗi đợt refactor có phạm vi nhỏ, dễ review và dễ xác định nguyên nhân nếu kiểm thử thất bại.

## 6. Thu hẹp allow-list khi caller đã chuyển

Nếu caller chưa khai báo `allowedDependencies`, Spring Modulith không áp dụng allow-list tường minh cho caller đó. Khi muốn kiểm soát chặt hơn, hãy khai báo module và named interface cụ thể mà caller được phép dùng.

Ví dụ, `orders` chỉ cần API giữ chỗ của `inventory`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::reservation"
)
package com.example.shop.orders;
```

Nếu caller cần cả base package API lẫn tất cả named interface của module đích, cú pháp dependency có thể khác; hãy chỉ cấp đúng phạm vi cần thiết. Không dùng `inventory` hoặc wildcard rộng hơn nếu caller chỉ cần `inventory::reservation`.

Trong giai đoạn module đích vẫn `OPEN`, hãy nhớ rằng những type nội bộ chưa được gán named interface riêng vẫn thuộc unnamed interface. Allow-list của caller cần được cấu hình nhất quán để chỉ cho phép hợp đồng caller thực sự cần. `OPEN` không tự thay thế allow-list của module sử dụng.

## 7. Đóng module và xử lý các vi phạm còn lại

Khi các caller đã chuyển khỏi implementation nội bộ, hãy bỏ `type = Type.OPEN` khỏi `@ApplicationModule` hoặc đặt module về `Type.CLOSED`:

```java
@org.springframework.modulith.ApplicationModule
package com.example.shop.inventory;
```

`CLOSED` là trạng thái mặc định nên annotation có thể chỉ giữ lại metadata khác nếu cần. Sau khi đóng, base package là API mặc định; các sub-package trở lại nội bộ trừ những package được công khai bằng `@NamedInterface`.

Chạy kiểm tra kiến trúc:

```java
package com.example.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Nếu kiểm thử báo một dependency đến `inventory.persistence.StockRepository`, hãy xem đó là danh sách công việc còn lại. Xác định caller nào còn dùng type đó, đưa hợp đồng phù hợp ra API, chuyển caller, rồi chạy lại kiểm thử. Đừng mở module trở lại chỉ để bỏ qua vi phạm mà chưa hiểu nguyên nhân.

## 8. Đo tiến độ thu hẹp module

Để biết module đã sẵn sàng đóng chưa, có thể theo dõi các chỉ số đơn giản:

| Chỉ số | Trước chuyển đổi | Mục tiêu trước khi đóng |
|---|---|---|
| Caller bên ngoài import sub-package implementation | Nhiều | Không còn |
| Caller phụ thuộc entity/repository nội bộ | Có | Không còn |
| API công khai có hợp đồng rõ ràng | Chưa đầy đủ | Đủ cho các use case bên ngoài |
| `allowedDependencies` của caller | Rộng hoặc chưa khai báo | Chỉ rõ module/interface cần thiết |
| `ApplicationModules.verify()` khi module đóng | Có thể thất bại | PASS |

Có thể lưu kết quả kiểm kê cùng pull request hoặc issue của từng đợt refactor để nhóm biết caller nào đã chuyển, caller nào còn lại và API nào đã ổn định. Khi không còn caller bên ngoài sử dụng implementation, việc chuyển về `CLOSED` trở thành một thay đổi có thể kiểm chứng.

## 9. Những điều cần tránh

- Không mở toàn bộ module chỉ vì một vài type nội bộ đang được dùng xuyên module.
- Không công khai repository hoặc entity chỉ để tránh sửa caller.
- Không tạo named interface quá rộng chứa cả API lẫn implementation.
- Không bỏ qua `allowedDependencies` nếu mục tiêu là kiểm soát hướng phụ thuộc giữa các module.
- Không coi `verify()` PASS khi module còn `OPEN` là bằng chứng rằng module đã đóng gói tốt; module open được miễn một số kiểm tra ranh giới và cycle detection.

Một lộ trình tốt kết thúc bằng module `CLOSED`, API nhỏ và có chủ đích, các caller phụ thuộc vào hợp đồng ổn định, và kiểm thử kiến trúc bảo vệ được ranh giới. `OPEN` giúp bắt đầu quá trình; việc chuyển caller và thu hẹp hợp đồng mới tạo ra modular monolith có thể duy trì lâu dài.

Tài liệu tham khảo: [Open Application Modules trong Spring Modulith Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html#modules.advanced.open) và [Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html).
