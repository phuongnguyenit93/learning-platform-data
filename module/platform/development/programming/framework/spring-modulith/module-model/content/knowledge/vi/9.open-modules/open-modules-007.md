# Rủi ro dùng open module trong ứng dụng mới

Spring Modulith cho phép đánh dấu một application module là `OPEN` để các mô-đun khác có thể truy cập cả những kiểu nằm trong package triển khai nội bộ. Cơ chế này hữu ích khi đưa một codebase cũ vào cấu trúc modular từng bước, vì việc đóng gói toàn bộ package con ngay từ đầu có thể đòi hỏi quá nhiều thay đổi. Với một ứng dụng mới, dùng `OPEN` ngay từ đầu thường tạo ra một bề mặt API quá rộng và làm mất một phần giá trị của việc mô-đun hóa.

Trong phạm vi **SPRING_MODULITH_MODULE_MODEL**, mục tiêu là xác định ranh giới nghiệp vụ, API công khai và phụ thuộc giữa các package trong ứng dụng Spring Boot. Ranh giới chỉ có ý nghĩa khi nhóm biết mô-đun nào được phép sử dụng hợp đồng nào. Vì vậy, cần hiểu chính xác `OPEN` thay đổi cách Spring Modulith kiểm tra và mô hình hóa khả năng truy cập trước khi chọn dùng nó.

## 1. Open module thay đổi điều gì?

Theo mặc định, application module được xem là đóng (`CLOSED`). Package gốc của mô-đun tạo thành API mặc định; các package con là phần triển khai nội bộ, trừ khi được công khai qua `NamedInterface`.

Ví dụ, mô-đun `inventory` có cấu trúc:

```text
com.acme.shop.inventory
├── InventoryOperations.java       // API mặc định
├── api
│   ├── package-info.java           // Named Interface "api"
│   └── ReservationResult.java
└── internal
    ├── InventoryRepository.java
    ├── InventoryPolicy.java
    └── InventoryEntity.java
```

Trong trạng thái đóng, mô-đun khác có thể sử dụng API ở package gốc và named interface đã công khai. Các kiểu trong `internal` được giữ lại cho chính mô-đun `inventory` sử dụng.

Nếu đánh dấu mô-đun là mở trong `inventory/package-info.java`:

```java
@org.springframework.modulith.ApplicationModule(
    type = org.springframework.modulith.ApplicationModule.Type.OPEN
)
package com.acme.shop.inventory;
```

Spring Modulith thay đổi mô hình và việc kiểm chứng theo hai điểm chính:

- Việc truy cập các kiểu nội bộ của mô-đun từ mô-đun khác nhìn chung được cho phép.
- Tất cả các kiểu trong mô-đun, bao gồm kiểu nằm trong package con, được đưa vào unnamed interface, trừ kiểu đã được gán vào một named interface riêng.

Do đó, `InventoryRepository`, `InventoryPolicy` hoặc `InventoryEntity` có thể trở thành những kiểu mà mô-đun khác tham chiếu. Các consumer có thể phụ thuộc vào chúng dù ban đầu nhóm chỉ định chúng là chi tiết triển khai.

## 2. Rủi ro đầu tiên: package nội bộ trở thành API ngoài ý muốn

Giả sử `InventoryRepository` được khai báo `public` để Java cho phép mã ở package khác tham chiếu tới nó:

```java
package com.acme.shop.inventory.internal;

import org.springframework.stereotype.Repository;

@Repository
public class InventoryRepository {
    // Chi tiết truy cập dữ liệu của inventory.
}
```

Mô-đun `orders` inject trực tiếp repository này:

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
}
```

Với mô-đun đóng, dependency vào `inventory.internal` vi phạm ranh giới và có thể bị `ApplicationModules.verify()` phát hiện. Khi `inventory` là open module, truy cập nội bộ này được chấp nhận trong mô hình kiến trúc.

Điều đó khiến ranh giới giữa API và implementation trở nên mờ. Một class repository, entity, mapper hoặc helper được viết để phục vụ nội bộ có thể nhanh chóng trở thành hợp đồng không chính thức cho nhiều consumer. Nhóm sở hữu mô-đun sẽ khó biết kiểu nào có thể đổi an toàn và kiểu nào đã bị code bên ngoài sử dụng.

## 3. Rủi ro thứ hai: thay đổi nội bộ lan sang nhiều mô-đun

Khi consumer phụ thuộc vào implementation, một refactor cục bộ có thể trở thành thay đổi xuyên hệ thống.

Ví dụ, `inventory` đổi từ JPA sang JDBC:

```text
Trước:
inventory.internal.InventoryRepository
inventory.internal.InventoryEntity

Sau:
inventory.internal.JdbcInventoryRepository
inventory.internal.InventoryRow
```

Nếu `orders`, `reports` hoặc `shipping` đang tham chiếu repository hay entity cũ, các mô-đun đó cũng phải sửa theo. Thay đổi công nghệ lưu trữ của một mô-đun vì thế có thể tạo ra nhiều công việc ngoài phạm vi trách nhiệm của nó.

Chi phí tương tự xuất hiện khi đổi tên package, chia nhỏ service, thay thuật toán hoặc điều chỉnh mô hình dữ liệu. Khi không có hợp đồng công khai nhỏ và ổn định, nhóm phải xem xét nhiều consumer trước khi thay một class tưởng như nội bộ.

## 4. Rủi ro thứ ba: kiểm chứng kiến trúc mất một phần hiệu lực

`ApplicationModules.verify()` hữu ích khi các mô-đun có ranh giới đóng và API được công khai có chủ đích. Với open module, truy cập vào package nội bộ không còn được xem là vi phạm theo quy tắc đóng gói đó. Ngoài ra, open module bị loại khỏi thuật toán phát hiện dependency cycle của Spring Modulith.

Điều này tạo ra hai điểm mù:

- Một mô-đun có thể phụ thuộc vào repository hoặc entity nội bộ mà kiểm tra ranh giới không báo lỗi.
- Chu trình phụ thuộc liên quan đến open module có thể không được thuật toán phát hiện cycle báo cáo.

Vì vậy, kết quả `verify()` thành công khi có open module không chứng minh rằng các consumer chỉ dùng API nghiệp vụ hoặc đồ thị phụ thuộc đã hoàn toàn không có chu trình. Nhóm cần hiểu giới hạn này khi đọc kết quả kiểm tra.

## 5. Rủi ro thứ tư: khó xác định quyền sở hữu và trách nhiệm thay đổi

Một mô-đun nghiệp vụ nên sở hữu các quy tắc và dữ liệu của nó, đồng thời công khai các thao tác mà mô-đun khác cần. Khi mọi package con đều có thể được tham chiếu, các mô-đun consumer có thể bắt đầu:

- Đọc hoặc cập nhật dữ liệu thông qua repository nội bộ.
- Tạo object hoặc gọi service triển khai thay vì sử dụng API nghiệp vụ.
- Dựa vào entity và cấu trúc persistence của mô-đun khác.
- Tái sử dụng helper chỉ được thiết kế cho một luồng xử lý cụ thể.

Những phụ thuộc này làm cho ownership không còn rõ ràng. Consumer có thể vô tình bỏ qua validation, authorization, audit, transaction hoặc bất biến mà mô-đun sở hữu cần duy trì. `OPEN` không tự tạo ra lỗi nghiệp vụ, nhưng nó làm giảm cơ chế ngăn chặn các phụ thuộc kiểu này.

## 6. Rủi ro thứ năm: cấu trúc mới hình thành quanh sự tiện lợi ngắn hạn

Trong ứng dụng mới, nhóm chưa có nhiều code cũ cần tương thích. Nếu đánh dấu một mô-đun là open chỉ vì một consumer cần thêm một class, nhóm có thể bỏ qua câu hỏi quan trọng: class đó có thực sự là hợp đồng nghiệp vụ cần công khai không?

Một quyết định tiện lợi ban đầu có thể tạo thành thói quen. Consumer tiếp theo tiếp tục import một class nội bộ khác vì mô-đun đã mở. Sau một thời gian, package `internal` chỉ còn là tên gọi, không còn biểu thị một ranh giới có thể bảo vệ.

Khi số consumer tăng, việc đóng mô-đun trở nên tốn kém hơn vì phải tìm và thay thế mọi tham chiếu nội bộ đã hình thành. Chi phí tái cấu trúc thường tăng theo số lượng consumer và mức độ phụ thuộc vào chi tiết triển khai.

## 7. Open module không phải cơ chế bảo mật hoặc Java module openness

Tên `OPEN` dễ gây nhầm với cơ chế mở reflection của Java Platform Module System hoặc cấu hình component scanning của Spring. Trong Spring Modulith, đây là thuộc tính của mô hình application module, dùng để xác định mức độ đóng gói và quy tắc kiểm chứng phụ thuộc giữa các mô-đun.

`OPEN` không tự:

- Thay đổi modifier `public`, `protected`, package-private hoặc `private` trong Java.
- Cấp quyền database hoặc mở quyền truy cập mạng.
- Tạo bean Spring cho một class chưa được component scanning hoặc cấu hình.
- Tạo ranh giới triển khai hay tiến trình riêng.
- Thay thế authorization, security policy hoặc kiểm soát truy cập dữ liệu.

Một class package-private vẫn chịu quy tắc truy cập của Java. Spring Modulith không thể làm cho mọi class trở nên truy cập được ở cấp ngôn ngữ; `OPEN` chủ yếu nới lỏng ranh giới mà mô hình kiến trúc kiểm tra.

## 8. Khi nào open module có thể hợp lý?

Spring Modulith chủ yếu hướng tính năng này tới các codebase hiện có đang được chuyển dần sang cấu trúc package được khuyến nghị. Trong một hệ thống cũ, có thể đã tồn tại nhiều tham chiếu xuyên package và việc đóng tất cả mô-đun ngay lập tức sẽ tạo ra một đợt refactor lớn.

Trong tình huống đó, `OPEN` có thể là bước chuyển tiếp có kiểm soát:

1. Đánh dấu tạm thời một mô-đun cũ là open để bắt đầu mô hình hóa ứng dụng.
2. Kiểm kê các tham chiếu từ mô-đun khác vào package con của nó.
3. Phân loại tham chiếu nào là nhu cầu nghiệp vụ thật và tham chiếu nào chỉ dùng chi tiết triển khai.
4. Tạo API mặc định hoặc named interface cho các hợp đồng cần giữ.
5. Chuyển consumer sang hợp đồng công khai theo từng nhóm.
6. Đóng lại mô-đun và chạy kiểm chứng kiến trúc.

Nếu buộc phải giữ open trong một giai đoạn, hãy ghi rõ lý do, người chịu trách nhiệm, các consumer hiện tại và điều kiện kết thúc. Không nên để trạng thái chuyển tiếp tồn tại vô thời hạn.

## 9. Cách tổ chức an toàn hơn cho ứng dụng mới

Với một ứng dụng mới, bắt đầu bằng mô-đun đóng và chỉ công khai hợp đồng thực sự cần thiết:

```text
com.acme.shop.inventory
├── InventoryOperations.java       // API mặc định nếu cần
├── api
│   ├── package-info.java           // Named Interface "api"
│   ├── ReservationResult.java
│   └── InventoryQuery.java
└── internal
    ├── InventoryOperationsImpl.java
    ├── InventoryRepository.java
    ├── InventoryEntity.java
    └── InventoryPolicy.java
```

Khai báo package `api` là named interface:

```java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.inventory.api;
```

Mô-đun consumer khai báo đúng dependency cần thiết:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::api"
)
package com.acme.shop.orders;
```

Với cách này, `orders` có thể dùng `ReservationResult` hoặc `InventoryQuery` qua hợp đồng `api`, nhưng không được phụ thuộc trực tiếp vào `InventoryRepository`, `InventoryEntity` hoặc `InventoryPolicy` trong `internal`.

Nếu API nhỏ chỉ gồm một vài kiểu, có thể đặt chúng ở package gốc của mô-đun mà không cần tạo named interface riêng. Hãy chọn cấu trúc ít phức tạp nhất vẫn diễn đạt rõ hợp đồng.

## 10. Quy trình chuyển một open module về closed

Khi một mô-đun đã mở và nhóm muốn khôi phục encapsulation, hãy thực hiện theo từng bước:

1. **Liệt kê consumer.** Tìm tất cả mô-đun đang import hoặc tham chiếu package con của mô-đun open.
2. **Phân loại kiểu được sử dụng.** Xác định kiểu nào là API nghiệp vụ cần công khai và kiểu nào là chi tiết triển khai.
3. **Thiết kế hợp đồng.** Tạo facade, service contract, DTO hoặc named interface theo nhu cầu consumer.
4. **Di chuyển và ẩn implementation.** Đặt repository, entity, mapper và helper trong package nội bộ; tránh để consumer sử dụng trực tiếp.
5. **Cập nhật consumer.** Thay import và dependency để chúng chỉ dùng package gốc hoặc named interface được công khai.
6. **Khai báo allowedDependencies.** Giới hạn mô-đun consumer vào đúng API mà nó cần.
7. **Bỏ `type = Type.OPEN`.** Đưa mô-đun về trạng thái đóng sau khi các tham chiếu nội bộ đã được xử lý.
8. **Chạy kiểm chứng và test.** Dùng `ApplicationModules.verify()` để phát hiện truy cập nội bộ còn sót và kiểm tra lại dependency cycles cùng hành vi nghiệp vụ.

Ví dụ kiểm tra mô hình sau khi đóng:

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

Khi package được tổ chức đúng, có thể bỏ annotation `@ApplicationModule` nếu không cần khai báo metadata khác, vì mô-đun đóng là mặc định. Nếu cần giữ annotation cho `allowedDependencies` hoặc metadata khác, chỉ cần bỏ thuộc tính `type = Type.OPEN`.

## 11. Bảng quyết định: OPEN hay CLOSED?

| Tình huống | Lựa chọn phù hợp | Lý do |
|---|---|---|
| Ứng dụng mới, package được thiết kế theo nghiệp vụ | `CLOSED` | Bảo vệ API nhỏ và giữ chi tiết triển khai nội bộ |
| Chỉ cần công khai một package API bổ sung | `CLOSED` + `NamedInterface` | Chỉ mở đúng hợp đồng consumer cần |
| Codebase cũ có nhiều tham chiếu xuyên package cần chuyển đổi dần | Có thể tạm dùng `OPEN` | Tránh phải refactor toàn bộ trong một bước |
| Một mô-đun được đánh dấu open chỉ để consumer gọi repository | Không nên dùng `OPEN` | Nên công khai thao tác nghiệp vụ qua API |
| Hệ thống đã modularize nhưng nhiều module vẫn phải mở | Xem lại ranh giới và package | Đây thường là dấu hiệu mô hình hóa chưa tốt |

## 12. Những ngộ nhận cần tránh

- **“Open chỉ là công khai thêm một API nhỏ.”** Nó đưa tất cả kiểu trong mô-đun vào unnamed interface, trừ kiểu đã được gán named interface riêng.
- **“Open giúp kiểm tra kiến trúc chặt hơn.”** Nó nới lỏng kiểm tra truy cập nội bộ và loại mô-đun khỏi thuật toán phát hiện dependency cycle.
- **“Chỉ cần đặt tên package là internal.”** Tên package không tạo ra ranh giới nếu mô-đun được khai báo `OPEN`.
- **“Open module chỉ ảnh hưởng compile-time.”** Nó ảnh hưởng mô hình kiến trúc và kết quả verification; code có thể tiếp tục tích lũy phụ thuộc nội bộ.
- **“Open module làm class package-private thành public.”** Java access modifier vẫn có hiệu lực riêng.
- **“Ứng dụng mới nên mở module để linh hoạt.”** Sự linh hoạt ngắn hạn có thể làm tăng chi phí thay đổi và tái cấu trúc về sau.

## Kết luận

`OPEN` là công cụ hỗ trợ chuyển đổi các codebase cũ, nơi việc đóng gói ngay lập tức chưa khả thi. Nó làm cho kiểu nội bộ có thể được truy cập từ mô-đun khác trong mô hình Spring Modulith, đưa các kiểu trong package con vào unnamed interface và loại mô-đun khỏi thuật toán phát hiện dependency cycle. Với ứng dụng mới, hãy bắt đầu bằng `CLOSED`, dùng package gốc hoặc `NamedInterface` để công khai hợp đồng nghiệp vụ, và giữ repository, entity cùng helper trong `internal`. Nếu cần `OPEN` trong giai đoạn chuyển đổi, hãy đặt mục tiêu và lộ trình đóng lại cụ thể.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Open Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html#modules.advanced.open)
- [Spring Modulith — ApplicationModule.Type API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.Type.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
