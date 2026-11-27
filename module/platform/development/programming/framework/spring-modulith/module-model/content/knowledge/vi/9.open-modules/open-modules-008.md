# Đọc ảnh hưởng của Type.OPEN lên verification

Trong Spring Modulith, một Application Module đóng (closed) chỉ công bố package gốc và những Named Interface được khai báo. Các subpackage còn lại là nội bộ. Khi đánh dấu module bằng **Type.OPEN**, quy tắc truy cập thay đổi đáng kể: các type trong subpackage cũng được đưa vào giao diện không tên (unnamed interface), trừ những type đã được gán rõ vào Named Interface. Vì thế, module khác có thể tham chiếu phần lớn các type nội bộ mà kiểm chứng kiến trúc vốn sẽ từ chối ở module đóng.

Thay đổi này ảnh hưởng trực tiếp đến kết quả của **ApplicationModules.verify()**. Bài học này giải thích chính xác những quy tắc được nới lỏng, những kiểm tra vẫn còn hiệu lực, cách đọc dependency graph và cách dùng module mở như một bước chuyển tiếp khi cải tổ hệ thống cũ.

## 1. Mặc định, Application Module là closed

Giả sử ứng dụng có package gốc **com.acme.shop** và module **catalog**:

~~~text
com.acme.shop
├── ShopApplication.java
├── catalog
│   ├── ProductCatalog.java
│   ├── ProductId.java
│   ├── internal
│   │   ├── JpaProductRepository.java
│   │   └── ProductEntity.java
│   └── pricing
│       └── PriceCalculator.java
└── checkout
    └── CheckoutService.java
~~~

Theo quy tắc mặc định:

- **com.acme.shop.catalog** là base package của module **catalog** và là API package mặc định.
- **com.acme.shop.catalog.internal** và **com.acme.shop.catalog.pricing** là subpackage nội bộ.
- Module **checkout** có thể tham chiếu các type được công bố ở API package mặc định.
- Module **checkout** không được tham chiếu trực tiếp **JpaProductRepository**, **ProductEntity** hoặc **PriceCalculator** nếu các type đó chỉ nằm trong subpackage nội bộ.

Một class trong subpackage có thể cần modifier **public** để các package bên trong cùng module gọi được. Modifier này cho phép Java biên dịch lời gọi, nhưng không làm class trở thành API liên module. Spring Modulith kiểm tra ranh giới kiến trúc bổ sung cho quy tắc truy cập của Java.

## 2. Khai báo module mở bằng Type.OPEN

Để đánh dấu **catalog** là Open Application Module, thêm annotation vào **package-info.java** trong package gốc:

~~~java
@org.springframework.modulith.ApplicationModule(
    type = org.springframework.modulith.ApplicationModule.Type.OPEN
)
package com.acme.shop.catalog;
~~~

Với Kotlin, dùng một class metadata được đánh dấu **@PackageInfo**:

~~~kotlin
package com.acme.shop.catalog

import org.springframework.modulith.ApplicationModule
import org.springframework.modulith.PackageInfo

@ApplicationModule(type = ApplicationModule.Type.OPEN)
@PackageInfo
class ModuleMetadata
~~~

**Type.OPEN** là metadata mô tả loại Application Module cho Spring Modulith. Đây không phải cấu hình component scan, không thay đổi modifier của class và không khiến type package-private trở thành public theo quy tắc của Java.

## 3. Type.OPEN thay đổi những gì trong mô hình expose?

Khi module là open, Spring Modulith thay đổi cách xây dựng giao diện và cách kiểm chứng quyền truy cập:

1. Các type nằm trong subpackage của module được đưa vào unnamed interface, cùng với type ở base package.
2. Type đã được gán tường minh vào một Named Interface vẫn thuộc Named Interface đó.
3. Module khác nhìn chung được phép tham chiếu type nội bộ của Open Application Module.

Với cấu trúc ở phần trước, **ProductCatalog**, **JpaProductRepository**, **ProductEntity** và **PriceCalculator** đều thuộc unnamed interface nếu không có khai báo Named Interface riêng. Vì vậy, tham chiếu đến các type đó không còn bị xem là truy cập nội bộ trái phép chỉ vì chúng nằm trong subpackage.

| Thành phần | Module closed | Module open |
|---|---|---|
| Type trong base package | Thuộc API mặc định | Thuộc unnamed interface |
| Type trong subpackage không khai báo Named Interface | Nội bộ | Được đưa vào unnamed interface |
| Type được gán Named Interface tường minh | Thuộc Named Interface tương ứng | Vẫn thuộc Named Interface tương ứng |
| Module khác tham chiếu type nội bộ | Vi phạm quy tắc expose | Thông thường được cho phép |

Điểm quan trọng là **Type.OPEN không chỉ bỏ qua một cảnh báo**. Nó làm thay đổi tập hợp type mà module công bố trong mô hình Spring Modulith. Các subpackage chưa được phân loại riêng được xem là một phần của unnamed interface.

## 4. Ảnh hưởng trực tiếp đến ApplicationModules.verify()

Ta thường kiểm tra cấu trúc ứng dụng bằng:

~~~java
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @org.junit.jupiter.api.Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Với module closed, một tham chiếu từ **checkout** đến **catalog.internal.JpaProductRepository** bị phát hiện là truy cập package nội bộ.

Khi **catalog** chuyển sang **Type.OPEN**, tham chiếu đó nhìn chung không còn vi phạm quy tắc truy cập API package. Lý do là type nội bộ đã được đưa vào unnamed interface của module mở.

Điều này có thể khiến **verify()** chuyển từ thất bại sang thành công dù mã nguồn consumer vẫn import trực tiếp repository hoặc entity nội bộ. Vì vậy, nếu một vi phạm biến mất sau khi đổi module sang OPEN, cần xem đó là hệ quả của việc nới lỏng ranh giới, không phải bằng chứng rằng thiết kế phụ thuộc đã tốt hơn.

## 5. Những kiểm tra vẫn còn hiệu lực

**Type.OPEN không tắt toàn bộ verification.** Các quy tắc độc lập vẫn cần được hiểu và kiểm tra:

- Danh sách **allowedDependencies** ở module tiêu thụ vẫn giới hạn module mà nó được phép phụ thuộc.
- Một type được expose không đồng nghĩa mọi module đều được phép tham chiếu nó khi consumer đã khai báo allowlist.
- Các quy tắc kiến trúc khác được cấu hình cho ứng dụng vẫn có thể được thực thi.

Ví dụ, **checkout** chỉ được phép phụ thuộc vào **catalog**:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "catalog"
)
package com.acme.shop.checkout;
~~~

Do **catalog** là open, các type không được gán Named Interface tường minh trong các subpackage của nó thuộc unnamed interface. Dependency **catalog** cho phép consumer sử dụng giao diện không tên đó.

Nếu một subpackage được gán Named Interface tường minh, nó vẫn được phân biệt khỏi unnamed interface. Khi consumer chỉ được phép dùng Named Interface **spi**, hãy khai báo chính xác:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "catalog :: spi"
)
package com.acme.shop.integration;
~~~

Nếu consumer cần cả unnamed interface và Named Interface **spi**, khai báo cả hai:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = { "catalog", "catalog :: spi" }
)
package com.acme.shop.integration;
~~~

Do đó, hãy đọc hai cơ chế riêng biệt:

1. **Type.OPEN** quyết định module cung cấp công bố những type nào theo unnamed interface.
2. **allowedDependencies** quyết định module tiêu thụ được phép phụ thuộc vào module và interface nào.

## 6. Ảnh hưởng đến kiểm tra dependency cycle

Một khác biệt quan trọng khác là Open Application Module được loại khỏi thuật toán phát hiện chu trình phụ thuộc theo mô tả của **ApplicationModule.Type.OPEN**.

Với các module đóng, Spring Modulith kiểm tra dependency graph để phát hiện chu trình ở cấp Application Module. Khi một module là OPEN, không nên dựa vào quy tắc cycle detection đó để phát hiện mọi chu trình có liên quan đến module mở.

Ví dụ:

~~~text
orders ─────> catalog (OPEN)
   ^              |
   └──────────────┘
~~~

Nếu module mở nằm trên một chu trình, việc kiểm tra chu trình có thể không phát hiện được vấn đề đó theo cùng cách như với các module đóng. Vì vậy, chuyển một module sang OPEN có thể làm giảm khả năng kiểm chứng dependency graph, bên cạnh việc cho phép truy cập rộng vào type nội bộ.

Khi cần đánh giá module mở đang được kết nối như thế nào, hãy xem dependency graph thực tế và rà soát các import hai chiều. Mục tiêu của quá trình chuyển đổi là thu hẹp dần các phụ thuộc, sau đó đưa module về trạng thái closed để khôi phục ranh giới và kiểm tra chu trình đầy đủ.

## 7. Ví dụ trước và sau khi chuyển sang OPEN

Giả sử **checkout** đang import repository của **catalog**:

~~~java
package com.acme.shop.checkout;

import com.acme.shop.catalog.internal.JpaProductRepository;
import org.springframework.stereotype.Service;

@Service
class CheckoutService {

    private final JpaProductRepository repository;

    CheckoutService(JpaProductRepository repository) {
        this.repository = repository;
    }
}
~~~

Khi **catalog** là closed, tham chiếu này vi phạm ranh giới module vì consumer truy cập package nội bộ. Khi **catalog** là OPEN, tham chiếu có thể vượt qua kiểm tra expose vì repository thuộc unnamed interface của module mở.

Tuy nhiên, **CheckoutService** đang phụ thuộc trực tiếp vào cách **catalog** lưu dữ liệu. Nếu repository đổi sang JDBC, đổi tên entity hoặc thay chiến lược truy vấn, module **checkout** có thể phải sửa theo. Việc verification chấp nhận import không loại bỏ rủi ro coupling đó.

Một thiết kế tốt hơn là để **catalog** công bố hợp đồng nghiệp vụ:

~~~java
package com.acme.shop.catalog;

public interface ProductCatalog {

    ProductDetails findProduct(String productId);
}
~~~

Module **checkout** chỉ tham chiếu **ProductCatalog**. Implementation và repository nằm trong **catalog.internal**. Khi consumer đã chuyển sang hợp đồng công khai, có thể đóng module lại và để **verify()** xác nhận không còn import vào internals.

## 8. Type.OPEN hữu ích trong giai đoạn nào?

Spring Modulith định hướng Open Application Module chủ yếu cho codebase cũ đang chuyển dần sang cách tổ chức module chặt chẽ hơn. Trong hệ thống legacy, các package con có thể đã được nhiều phần khác của ứng dụng sử dụng trực tiếp. Nếu chuyển ngay sang module closed, hàng loạt vi phạm có thể xuất hiện cùng lúc.

Có thể dùng OPEN như một bước chuyển tiếp:

1. Bắt đầu mô hình hóa module hiện tại và đánh dấu OPEN để ghi nhận phạm vi module trong khi các phụ thuộc cũ vẫn tồn tại.
2. Rà soát các module đang tham chiếu subpackage nội bộ.
3. Nhóm các type cần chia sẻ thành API nghiệp vụ hoặc Named Interface có trách nhiệm rõ ràng.
4. Chuyển consumer sang hợp đồng được công bố.
5. Thu hẹp **allowedDependencies** để mỗi consumer chỉ được dùng interface cần thiết.
6. Bỏ **Type.OPEN** hoặc chuyển module về CLOSED.
7. Chạy lại **ApplicationModules.verify()** để phát hiện các tham chiếu nội bộ và chu trình còn sót.

Trong ứng dụng đã được modularize đầy đủ, việc duy trì nhiều module OPEN thường là dấu hiệu cấu trúc package hoặc ranh giới nghiệp vụ chưa được phân chia hợp lý. Không nên dùng OPEN như cách mặc định để làm cho mọi import hợp lệ.

## 9. Những điều Type.OPEN không làm

Để tránh hiểu sai, cần phân biệt rõ:

| Type.OPEN làm | Type.OPEN không làm |
|---|---|
| Đưa type trong subpackage chưa gán Named Interface vào unnamed interface | Không biến class package-private thành public trong Java |
| Cho phép module khác tham chiếu type nội bộ theo quy tắc expose | Không tự tạo Spring bean hoặc thay đổi component scan |
| Làm thay đổi kết quả kiểm tra truy cập nội bộ | Không thay thế dependency allowlist của consumer |
| Loại module mở khỏi thuật toán cycle detection | Không bảo đảm dependency graph không có chu trình |
| Hữu ích cho chuyển đổi codebase legacy | Không tự tái cấu trúc package hoặc thiết kế lại API |

**Type.OPEN** là một quyết định về ranh giới kiến trúc trong mô hình Spring Modulith. Nó không phải công cụ sửa lỗi biên dịch hoặc cơ chế tự động modularize mã nguồn.

## 10. Quy trình đọc kết quả verification

Khi **ApplicationModules.verify()** thay đổi kết quả sau khi một module được chuyển sang OPEN, hãy phân tích theo trình tự:

1. Xác định vi phạm ban đầu là truy cập package nội bộ, dependency ngoài allowlist hay chu trình.
2. Kiểm tra type được tham chiếu nằm ở base package, subpackage thông thường hay Named Interface tường minh.
3. Xác định module cung cấp có đang là OPEN hay không.
4. Kiểm tra consumer có khai báo **allowedDependencies** và có được phép dùng đúng interface hay không.
5. Nếu vi phạm truy cập nội bộ biến mất, ghi nhận rằng OPEN đã đưa type vào unnamed interface.
6. Nếu nghi ngờ chu trình, kiểm tra riêng các cạnh đi qua module OPEN vì module này bị loại khỏi cycle detection.
7. Quyết định có thể chuyển consumer sang API/Named Interface để đóng module lại hay chưa.

Không nên chỉ nhìn kết quả cuối cùng là PASS. Hãy so sánh mô hình module trước và sau khi đổi loại module để hiểu chính xác quy tắc nào đã được nới lỏng.

## 11. Kiểm thử quá trình đóng lại module

Khi đã chuyển consumer khỏi các package nội bộ, bỏ khai báo OPEN để module trở lại closed. Sau đó, chạy bài test kiến trúc:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesClosedModuleBoundaries() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Nếu test thất bại, đọc từng vi phạm và xử lý ở đúng hợp đồng:

- Chuyển type dùng chung về API package nếu đó là API chính của module.
- Công bố một subpackage bằng **@NamedInterface** nếu đó là một nhóm hợp đồng riêng.
- Cập nhật **allowedDependencies** ở consumer để cấp đúng quyền phụ thuộc.
- Xóa import vào repository, entity hoặc adapter nội bộ nếu consumer không nên biết chi tiết đó.

Chỉ đóng module khi các consumer đã dùng đúng hợp đồng. Khi đó, verification sẽ có thể bảo vệ ranh giới chặt hơn và việc thay đổi implementation của module ít gây ảnh hưởng lan truyền.

## Tài liệu tham khảo

- [Spring Modulith Reference — Fundamentals, Open Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html): cách khai báo module mở, ảnh hưởng đến expose và khuyến nghị cho codebase legacy.
- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): các quy tắc được kiểm tra bởi **ApplicationModules.verify()** và ngoại lệ truy cập internals của module mở.
- [Spring Modulith Javadoc — ApplicationModule.Type](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.Type.html): ý nghĩa của **OPEN**, **CLOSED** và ảnh hưởng tới cycle detection.
