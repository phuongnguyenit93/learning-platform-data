# Phân biệt compile dependency với dependency nghiệp vụ

Khi thiết kế modular monolith bằng Spring Modulith, cần phân biệt quan hệ phụ thuộc mà mã nguồn tạo ra với nhu cầu cộng tác giữa các năng lực nghiệp vụ. Compile dependency mô tả type hoặc mã của module này tham chiếu đến module khác. Dependency nghiệp vụ mô tả một module cần một khả năng, dữ liệu hoặc kết quả do một phần nghiệp vụ khác cung cấp.

Hai quan hệ thường liên quan nhưng không đồng nhất. Một yêu cầu nghiệp vụ có thể được triển khai bằng một phụ thuộc mã nguồn hợp lý qua API công khai; cũng có thể bị triển khai thành phụ thuộc trực tiếp vào lớp nội bộ. Ngược lại, một compile dependency có thể chỉ là tiện ích kỹ thuật và không thể hiện quan hệ nghiệp vụ đáng kể. Spring Modulith giúp phân tích và kiểm chứng cấu trúc phụ thuộc trong mã nguồn, còn ý nghĩa nghiệp vụ cần được nhóm phát triển xác định.

## 1. Compile dependency là gì?

Compile dependency là quan hệ hình thành khi mã nguồn của một thành phần sử dụng type hoặc thành phần mã được định nghĩa ở thành phần khác. Trong Java, các trường hợp thường gặp gồm:

- Khai báo field hoặc constructor parameter bằng một type của module khác.
- Gọi method hoặc truy cập thành viên của type thuộc module khác.
- Kế thừa class hoặc triển khai interface từ module khác.
- Dùng type trong kiểu trả về, tham số, generic, annotation hoặc chữ ký API.

Ví dụ, `OrderPlacementService` tham chiếu trực tiếp `InventoryService`:

```java
package com.acme.shop.order.internal;

import com.acme.shop.inventory.internal.InventoryService;
import org.springframework.stereotype.Service;

@Service
public class OrderPlacementService {

    private final InventoryService inventoryService;

    public OrderPlacementService(InventoryService inventoryService) {
        this.inventoryService = inventoryService;
    }

    public void placeOrder(String sku, int quantity) {
        inventoryService.reserve(sku, quantity);
    }
}
```

Mã trong module `order` cần biết type `InventoryService` để biên dịch. Đây là compile dependency từ `order` đến type trong module `inventory`. Việc dependency injection diễn ra lúc runtime không xóa quan hệ type đã xuất hiện trong mã nguồn.

Trong bài học này, compile dependency nói về quan hệ tham chiếu giữa các type trong mã nguồn được phân tích. Khái niệm này không đồng nghĩa với khai báo dependency của Gradle hoặc Maven giữa các subproject/artifact. Một ứng dụng có thể chỉ có một build module nhưng vẫn có nhiều application module theo package và quy ước Spring Modulith.

## 2. Dependency nghiệp vụ là gì?

Dependency nghiệp vụ xuất hiện khi một năng lực nghiệp vụ cần sử dụng khả năng hoặc thông tin do năng lực khác sở hữu. Nó mô tả lý do hai phần nghiệp vụ cần cộng tác.

Ví dụ trong hệ thống bán hàng:

- `order` cần kiểm tra và giữ hàng trước khi xác nhận đơn.
- `inventory` sở hữu nghiệp vụ quản lý tồn kho và giữ hàng.
- Vì vậy, `order` có dependency nghiệp vụ đến khả năng giữ hàng của `inventory`.

Quan hệ này có thể mô tả ở mức năng lực:

```mermaid
flowchart LR
    Order["Nghiệp vụ đơn hàng"] -->|"Cần giữ hàng"| Inventory["Nghiệp vụ kho"]
```

Dependency nghiệp vụ trả lời câu hỏi: *Vì sao module này cần cộng tác với module kia?* Compile dependency trả lời câu hỏi: *Mã nguồn đang tham chiếu đến type nào của module kia?*

Nếu `order` gọi thẳng `InventoryService`, compile dependency đang hướng vào implementation. Nhu cầu nghiệp vụ thực tế chỉ là sử dụng khả năng giữ hàng. Hai quan hệ đã bị gắn chặt vào nhau theo cách làm lộ chi tiết triển khai.

## 3. Khi compile dependency và dependency nghiệp vụ trùng khớp

Một thiết kế tốt thể hiện nhu cầu nghiệp vụ qua hợp đồng công khai. Module `inventory` công bố interface tại module base package:

```java
package com.acme.shop.inventory;

public interface StockReservation {

    void reserve(String sku, int quantity);
}
```

Implementation nằm trong package nội bộ của module `inventory`:

```java
package com.acme.shop.inventory.internal;

import com.acme.shop.inventory.StockReservation;
import org.springframework.stereotype.Service;

@Service
public class StockReservationService implements StockReservation {

    @Override
    public void reserve(String sku, int quantity) {
        // Kiểm tra và cập nhật số lượng có thể giữ.
    }
}
```

Module `order` phụ thuộc vào hợp đồng:

```java
package com.acme.shop.order.internal;

import com.acme.shop.inventory.StockReservation;
import org.springframework.stereotype.Service;

@Service
public class OrderPlacementService {

    private final StockReservation stockReservation;

    public OrderPlacementService(StockReservation stockReservation) {
        this.stockReservation = stockReservation;
    }

    public void placeOrder(String sku, int quantity) {
        stockReservation.reserve(sku, quantity);
        // Tiếp tục xử lý đơn hàng.
    }
}
```

Ở đây có compile dependency từ `order` đến `StockReservation`, đồng thời có dependency nghiệp vụ từ đơn hàng đến khả năng giữ hàng của kho. Hai quan hệ được kết nối qua API công khai. Module `order` không cần biết `StockReservationService`, repository hoặc cách lưu trữ tồn kho.

Đây là sự tương ứng mong muốn: compile dependency thể hiện đúng hợp đồng cần cho nghiệp vụ, còn implementation được giữ trong module sở hữu khả năng đó.

## 4. Compile dependency không phù hợp với ranh giới nghiệp vụ

Hãy xem lại ví dụ phụ thuộc trực tiếp vào `InventoryService` trong package `inventory.internal`. Nhu cầu nghiệp vụ là giữ hàng, nhưng compile dependency buộc `order` biết một lớp triển khai cụ thể.

Điều này tạo ra một số hệ quả:

1. Module `order` phụ thuộc vào chi tiết có thể thay đổi trong module `inventory`.
2. Thay đổi constructor, tên lớp hoặc package nội bộ có thể ảnh hưởng đến module gọi.
3. Người đọc mã khó phân biệt hợp đồng nghiệp vụ với cơ chế triển khai.
4. Spring Modulith có thể phát hiện module `order` đang truy cập package nội bộ của `inventory`.

Hãy chuyển điểm phụ thuộc sang interface công khai `StockReservation`. Nếu module cần công bố nhiều nhóm hợp đồng, có thể đặt interface trong một named interface và khai báo rõ phụ thuộc đó.

## 5. Compile dependency không phải lúc nào cũng là dependency nghiệp vụ

Không phải mọi tham chiếu giữa các type đều thể hiện một quan hệ nghiệp vụ. Ví dụ, nhiều module có thể sử dụng một annotation kỹ thuật, một kiểu tiện ích hoặc một thư viện dùng chung. Compile dependency tồn tại, nhưng nó không nhất thiết có nghĩa module này cần năng lực nghiệp vụ của module kia.

Ngược lại, nếu một module sử dụng một tiện ích kỹ thuật đặt trong package gốc của module nghiệp vụ khác, Spring Modulith có thể nhìn thấy một module dependency dù ý định ban đầu chỉ là tái sử dụng helper. Đây là dấu hiệu cần xem lại vị trí sở hữu của type dùng chung và ranh giới package.

Một số tình huống thường gặp:

| Tình huống | Compile dependency | Dependency nghiệp vụ |
|---|---|---|
| `order` gọi API `StockReservation` của `inventory` | Có, tới interface công khai | Có, cần khả năng giữ hàng |
| `order` gọi trực tiếp `InventoryRepository` nội bộ | Có, tới implementation nội bộ | Có thể có nhu cầu nghiệp vụ, nhưng hợp đồng được chọn không phù hợp |
| `order` dùng một helper định dạng chuỗi chung | Có thể có | Thường không có quan hệ nghiệp vụ giữa hai module |
| Một module nhận sự kiện qua hạ tầng messaging mà không tham chiếu trực tiếp implementation của module phát | Có thể có dependency tới event contract hoặc không có type dependency trực tiếp tùy cách tích hợp | Có, module nhận cần phản ứng với sự kiện nghiệp vụ |

Ví dụ event cần được hiểu chính xác: nếu event type được khai báo trong một package API của module phát và module nhận import type đó, compile dependency vẫn tồn tại tới hợp đồng sự kiện. Event giúp giảm phụ thuộc gọi trực tiếp service đồng bộ; nó không tự động xóa mọi compile dependency.

## 6. Spring Modulith nhìn thấy quan hệ nào?

Spring Modulith khám phá application module từ package và phân tích các tham chiếu type để xây dựng mô hình phụ thuộc. Nó có thể kiểm tra các quy tắc như module có truy cập package nội bộ của module khác hay không, hoặc phụ thuộc có nằm trong danh sách được cho phép hay không.

Ví dụ, module `order` có thể khai báo chỉ được phụ thuộc vào module `inventory` trong `package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
        displayName = "Quản lý đơn hàng",
        allowedDependencies = "inventory"
)
package com.acme.shop.order;
```

Nếu `inventory` công bố named interface `spi`, module tiêu thụ có thể khai báo phụ thuộc cụ thể hơn:

```java
@org.springframework.modulith.ApplicationModule(
        displayName = "Quản lý đơn hàng",
        allowedDependencies = "inventory :: spi"
)
package com.acme.shop.order;
```

Khi đó, các type được tham chiếu cần nằm trong module base package hoặc named interface được công bố phù hợp với quy tắc đã khai báo. Implementation ở package nội bộ không trở thành API chỉ vì type Java là `public` hoặc Spring có thể tạo bean cho nó.

## 7. Kiểm chứng compile dependency bằng ApplicationModules.verify()

Bạn có thể tạo kiểm thử kiến trúc để kiểm tra các quy tắc module:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Hãy thử hai biến thể của `OrderPlacementService`:

1. Inject `InventoryService` từ `inventory.internal` và gọi trực tiếp implementation.
2. Inject `StockReservation` từ module base package hoặc named interface đã công bố.

Chạy `verify()` để xem mô hình phát hiện truy cập nội bộ và áp dụng quy tắc phụ thuộc như thế nào. Thông báo lỗi giúp xác định module nguồn, module đích và type/package gây ra vi phạm.

Điều cần nhớ là `verify()` kiểm tra cấu trúc phụ thuộc mà Spring Modulith có thể phân tích. Nó không thể tự kết luận rằng một dependency có ý nghĩa nghiệp vụ hợp lý hay không. Ví dụ, việc cho phép `order` phụ thuộc `inventory` không chứng minh rằng mọi type trong `inventory` đều nên xuất hiện trong hợp đồng của `order`.

## 8. Xác định và xử lý hai loại phụ thuộc

Khi xem xét một quan hệ giữa hai module, hãy đi theo các bước sau:

1. **Xác định nhu cầu nghiệp vụ.** Module gọi cần khả năng, dữ liệu hay kết quả nào từ module đích?
2. **Tìm compile dependency thực tế.** Xem type được import, constructor injection, method signature hoặc lời gọi đang tạo quan hệ mã nguồn.
3. **So sánh hai quan hệ.** Type đang được tham chiếu có đại diện đúng cho hợp đồng nghiệp vụ hay chỉ là implementation/tiện ích?
4. **Đặt hợp đồng đúng nơi.** Công bố hợp đồng trong module base package hoặc named interface phù hợp.
5. **Giới hạn module được phép phụ thuộc.** Dùng `allowedDependencies` để thể hiện chính sách kiến trúc.
6. **Kiểm chứng tự động.** Chạy `ApplicationModules.verify()` và bổ sung kiểm thử nghiệp vụ cho hành vi cộng tác.

Kiểm thử kiến trúc và kiểm thử nghiệp vụ có vai trò khác nhau. Kiểm thử kiến trúc xác nhận code tuân theo ranh giới đã khai báo; kiểm thử nghiệp vụ xác nhận luồng cộng tác tạo ra kết quả đúng, chẳng hạn đơn hàng chỉ được xác nhận sau khi hàng đã được giữ thành công.

## 9. Bài tập thực hành

Xây dựng hai module `order` và `inventory` trong ứng dụng `com.acme.shop`.

1. Mô tả dependency nghiệp vụ: đơn hàng cần khả năng giữ hàng của kho.
2. Viết `OrderPlacementService` phụ thuộc trực tiếp `InventoryService` trong `inventory.internal`.
3. Chỉ ra compile dependency xuất hiện ở constructor và lời gọi method nào.
4. Tạo interface `StockReservation` trong module base package `inventory` và chuyển implementation sang package `inventory.internal`.
5. Đổi constructor của `OrderPlacementService` sang nhận `StockReservation`.
6. Khai báo `allowedDependencies = "inventory"` cho module `order` và chạy `ApplicationModules.verify()`.
7. Thử chuyển hợp đồng sang named interface `spi` và cập nhật quy tắc thành `inventory :: spi`.
8. Viết một kiểm thử nghiệp vụ xác nhận đơn hàng không được tiếp tục nếu giữ hàng thất bại.
9. So sánh compile dependency trước và sau khi chuyển sang API công khai; giải thích vì sao dependency nghiệp vụ vẫn tồn tại.

Sau bài tập, hãy trả lời: compile dependency cho biết điều gì về mã nguồn, dependency nghiệp vụ cho biết điều gì về trách nhiệm, và vì sao hai loại phụ thuộc cần được xem xét cùng nhau?

## 10. Ghi nhớ

- Compile dependency là quan hệ tham chiếu type hoặc mã nguồn giữa các thành phần; Spring Modulith có thể phân tích các quan hệ này để xây dựng mô hình module.
- Dependency nghiệp vụ mô tả nhu cầu một năng lực nghiệp vụ sử dụng khả năng hoặc kết quả của năng lực khác.
- Một dependency nghiệp vụ có thể được thể hiện bằng compile dependency tới API công khai; nên tránh phụ thuộc trực tiếp vào implementation nội bộ.
- Compile dependency kỹ thuật không nhất thiết là dependency nghiệp vụ; cần xem xét ý nghĩa và quyền sở hữu của type được chia sẻ.
- Event integration có thể giảm phụ thuộc gọi service trực tiếp nhưng vẫn có compile dependency tới event contract nếu hai module dùng chung type sự kiện.
- `allowedDependencies` và named interface mô tả ranh giới được phép; `ApplicationModules.verify()` kiểm tra các quy tắc đó.
- Kiểm thử kiến trúc không thay thế kiểm thử nghiệp vụ và không tự quyết định dependency có đúng về mặt domain hay không.

Khi phân biệt rõ compile dependency với dependency nghiệp vụ, bạn có thể thiết kế API phản ánh đúng nhu cầu cộng tác, giữ implementation trong module sở hữu và dùng Spring Modulith để kiểm chứng cấu trúc modular monolith.
