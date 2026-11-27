# Đọc vị trí nguyên nhân của access violation

Khi chạy **ApplicationModules.verify()**, Spring Modulith có thể báo một module đang truy cập type không được module khác công bố. Đây là access violation ở ranh giới Application Module. Để sửa đúng, cần lần theo **type đang bị tham chiếu**, xác định **module sở hữu type**, kiểm tra **package chứa type** có thuộc API package hoặc Named Interface hay không, rồi mới quyết định thay đổi import hoặc expose hợp đồng.

Không phải mọi lỗi verification đều là access violation. Một dependency có thể bị từ chối vì không nằm trong **allowedDependencies**, hoặc dependency graph có thể chứa chu trình. Bài học này hướng dẫn cách đọc thông báo, tìm vị trí gây ra vi phạm và phân biệt các nguyên nhân để chọn cách xử lý phù hợp.

## 1. Access violation trong Spring Modulith có nghĩa gì?

Một Application Module đóng chỉ cho module khác tham chiếu các type nằm trong những giao diện được công bố:

- **API package mặc định**: package gốc (base package) của module.
- **Named Interface**: subpackage được công bố tường minh bằng **@NamedInterface**.

Các subpackage còn lại là phần triển khai nội bộ. Ví dụ:

~~~text
com.acme.shop
├── orders
│   ├── OrderManagement.java
│   ├── OrderId.java
│   ├── spi
│   │   ├── package-info.java
│   │   └── OrderPricingPolicy.java
│   └── internal
│       ├── JpaOrderRepository.java
│       └── OrderEntity.java
└── inventory
    └── internal
        └── InventoryService.java
~~~

Trong cấu trúc này:

- **orders** là module sở hữu các type trong package gốc.
- **orders.spi** là API bổ sung nếu package được khai báo Named Interface.
- **orders.internal** là chi tiết triển khai của module orders.
- **inventory** không được tham chiếu **JpaOrderRepository** hoặc **OrderEntity** chỉ vì các class đó có modifier public.

Access violation xảy ra khi mã nguồn của một module tham chiếu type thuộc package nội bộ của module khác. Spring Modulith phát hiện điều đó khi phân tích quan hệ type và kiểm chứng ranh giới module.

## 2. Đọc thông báo để tìm module và type liên quan

Khi verification thất bại, bắt đầu từ thông báo vi phạm đầy đủ. Một thông báo access violation thường cho biết:

1. Module đang tạo tham chiếu (consumer).
2. Type mà consumer đang tham chiếu.
3. Module sở hữu type đó (provider).
4. Lý do type không được expose theo mô hình hiện tại.

Ví dụ minh họa:

~~~text
Module 'inventory' depends on non-exposed type
'com.acme.shop.orders.internal.JpaOrderRepository'
within module 'orders'!
~~~

Đọc thông báo theo từng phần:

| Thành phần | Giá trị trong ví dụ | Cần làm rõ |
|---|---|---|
| Consumer | inventory | Package nào trong inventory tạo tham chiếu? |
| Type được tham chiếu | JpaOrderRepository | Type nào đang bị dùng? |
| Package của type | orders.internal | Package này có được công bố không? |
| Provider | orders | Module nào sở hữu type? |

Thông báo thực tế có thể khác theo phiên bản hoặc loại verification. Hãy dùng tên module, tên type và nội dung vi phạm mà kết quả cung cấp để lần theo mã nguồn; không phụ thuộc vào một chuỗi thông báo cố định.

## 3. Lần từ type về package và module sở hữu

Giả sử consumer có import:

~~~java
package com.acme.shop.inventory.internal;

import com.acme.shop.orders.internal.JpaOrderRepository;

class InventoryService {

    private final JpaOrderRepository repository;
}
~~~

Hãy phân tích import theo thứ tự:

1. Lấy tên đầy đủ của type: **com.acme.shop.orders.internal.JpaOrderRepository**.
2. Bỏ tên class để xác định package: **com.acme.shop.orders.internal**.
3. Xác định package gốc của module: **com.acme.shop.orders**.
4. So sánh package chứa type với API package mặc định và các Named Interface của module.
5. Nếu package là **internal** và không được công bố, đây là access violation.

Một type có thể được tham chiếu qua import tường minh, kiểu field, tham số constructor, kiểu trả về, generic type, kiểu cha hoặc interface triển khai. Nếu thông báo không trỏ trực tiếp tới dòng import, hãy tìm tất cả nơi consumer sử dụng type đó.

Không nên chỉ tìm tên class trong file đang báo lỗi. Một type nội bộ có thể được tham chiếu gián tiếp qua chữ ký public của một type khác; hãy kiểm tra cả chữ ký API mà consumer đang gọi.

## 4. Dùng detectViolations() để xem toàn bộ lỗi

Thay vì chỉ dừng ở exception đầu tiên, có thể lấy danh sách vi phạm:

~~~java
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.core.Violations;

class ModularityDiagnostics {

    void printViolations() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        Violations violations = modules.detectViolations();

        if (violations.hasViolations()) {
            violations.getMessages().forEach(System.out::println);
        }
    }
}
~~~

**detectViolations()** thực thi các kiểm tra và trả về đối tượng **Violations** nếu phát hiện vấn đề. **getMessages()** cho phép in từng thông báo để nhóm các lỗi theo module hoặc type. **hasViolations()** cho biết tập kết quả có lỗi hay không.

Nếu cần lọc một nhóm thông báo để phân tích:

~~~java
var internalAccessViolations = violations
    .filter(violation ->
        violation.hasMessageContaining("non-exposed type"));

internalAccessViolations.getMessages()
    .forEach(System.out::println);
~~~

Đây là bước hỗ trợ điều tra. Sau khi xác định nguyên nhân, bài test bảo vệ kiến trúc vẫn nên gọi **ApplicationModules.of(ShopApplication.class).verify()** để build thất bại khi có vi phạm mới.

## 5. Xác định module sở hữu type bằng ApplicationModule

Có thể kiểm tra module nào chứa một class và class đó có được expose hay không bằng API mô hình:

~~~java
import org.springframework.modulith.core.ApplicationModule;
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

ApplicationModule owner = modules.stream()
    .filter(module -> module.contains(JpaOrderRepository.class))
    .findFirst()
    .orElseThrow(() ->
        new IllegalStateException("Không tìm thấy module sở hữu type"));

System.out.println("Module: " + owner.getBasePackage().getName());
System.out.println("Exposed: " + owner.isExposed(JpaOrderRepository.class));
~~~

Đoạn mã thực hiện ba việc:

- **modules.stream()** duyệt các Application Module được phát hiện.
- **module.contains(Class)** tìm module chứa type đang điều tra.
- **module.isExposed(Class)** kiểm tra type có thuộc một trong các giao diện được công bố của module hay không.

Nếu **isExposed(…)** trả về false, hãy kiểm tra package và metadata expose của module sở hữu. Nếu không tìm thấy module chứa type, kiểm tra lại module detection, package gốc ứng dụng và việc type có thực sự thuộc mô hình inspection hay không.

## 6. Phân biệt access violation với dependency không được phép

Hai lỗi này có thể xuất hiện gần nhau nhưng nguyên nhân khác nhau.

**Access violation**: consumer tham chiếu một type thuộc package nội bộ của provider. Cách xử lý là chuyển consumer sang API được công bố hoặc công bố một Named Interface nếu type thực sự là hợp đồng liên module.

**Disallowed dependency**: type có thể thuộc API package hoặc Named Interface hợp lệ, nhưng consumer chưa được phép phụ thuộc vào module/interface đó theo allowlist.

Ví dụ:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders"
)
package com.acme.shop.inventory;
~~~

Khai báo trên cho phép **inventory** phụ thuộc API package mặc định của **orders**. Nếu inventory import type trong **orders.spi**, allowlist cần cấp quyền cho Named Interface tương ứng:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders :: spi"
)
package com.acme.shop.inventory;
~~~

Nếu consumer cần cả API gốc và SPI, khai báo cả hai:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = { "orders", "orders :: spi" }
)
package com.acme.shop.inventory;
~~~

Không nên thêm allowlist để chữa access violation vào package nội bộ. Allowlist giới hạn module và giao diện được phép dùng; nó không tự công bố **orders.internal** thành API.

## 7. Kiểm tra Named Interface có được khai báo đúng không

Nếu type nằm trong subpackage cần được dùng liên module, kiểm tra metadata của chính package đó.

Ví dụ, file **com.acme.shop.orders.spi/package-info.java**:

~~~java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.orders.spi;
~~~

Các lỗi thường gặp:

- Annotation nằm ở package khác với package chứa type.
- Tên Named Interface khai báo khác với tên được dùng trong **allowedDependencies**.
- Chỉ đổi tên package thành **api** hoặc **spi** nhưng quên khai báo **@NamedInterface**.
- Consumer dùng một type ở subpackage chưa được expose.
- Consumer khai báo allowlist cho API gốc nhưng lại import type trong Named Interface, hoặc ngược lại.

Tên package không tự tạo ra Named Interface. Hãy kiểm tra annotation hoặc metadata package thực tế trước khi thay đổi allowlist.

## 8. Kiểm tra Java visibility riêng với module exposure

Java visibility và Spring Modulith exposure là hai lớp quy tắc khác nhau.

| Trường hợp | Java compiler | Spring Modulith |
|---|---|---|
| Public type trong API package | Có thể truy cập nếu module trên classpath | Được expose theo API package mặc định |
| Public type trong subpackage nội bộ | Có thể import và biên dịch | Bị từ chối nếu module đóng và package chưa được công bố |
| Package-private type ở package khác | Không thể truy cập trực tiếp | Không thể trở thành API liên module chỉ bằng Named Interface |
| Public type trong Named Interface | Có thể truy cập | Được expose qua Named Interface |

Vì vậy, sửa modifier từ package-private thành public chỉ có thể giải quyết lỗi biên dịch Java. Nó không tự giải quyết access violation của Spring Modulith.

Ngược lại, thêm **@NamedInterface** cũng không thể làm một class package-private trở thành public đối với package khác. Hợp đồng liên module thường cần type public và package được công bố đúng.

## 9. Kiểm tra ngoại lệ do Open Module

Một module được đánh dấu **Type.OPEN** cho phép module khác truy cập các type nội bộ theo quy tắc verification của Spring Modulith. Các type trong subpackage thường được đưa vào unnamed interface, trừ type đã được gán Named Interface riêng.

Vì vậy, khi một import nội bộ không còn bị báo lỗi, hãy kiểm tra provider có đang là Open Module hay không. Kết quả không báo access violation trong trường hợp này không chứng minh rằng package nội bộ đã được thiết kế thành API ổn định.

**Type.OPEN** chủ yếu hữu ích khi chuyển đổi codebase legacy. Với module đã được modularize rõ ràng, nên ưu tiên API package và Named Interface có chủ đích để giữ ranh giới dễ hiểu.

## 10. Kiểm tra module detection và inspection scope

Đôi khi type bị báo lỗi thuộc một module khác với điều bạn dự đoán. Khi đó, hãy kiểm tra:

- Package của class **@SpringBootApplication** và application root.
- Package nào đang được phát hiện làm base package của module.
- Custom **ApplicationModuleDetectionStrategy** có chọn nhầm package hoặc bỏ sót module không.
- Có predicate exclusion nào loại class khỏi mô hình inspection không.

Nếu một package được nhận diện thành module riêng, type có thể thuộc provider khác với dự kiến. Nếu class bị exclusion, một số dependency hoặc access violation có thể không còn xuất hiện trong kết quả kiểm tra.

Hãy xác minh module sở hữu type trước khi sửa **@NamedInterface** hoặc **allowedDependencies**. Nếu xác định sai module, thay đổi metadata ở module không sở hữu type sẽ không giải quyết được nguyên nhân.

## 11. Chọn cách sửa theo nguyên nhân

Sau khi lần ra provider và package, chọn cách sửa phù hợp:

| Nguyên nhân | Hướng xử lý |
|---|---|
| Consumer dùng repository, entity hoặc service nội bộ | Chuyển consumer sang API nghiệp vụ công khai |
| Type cần được nhiều module sử dụng nhưng nằm trong subpackage | Công bố subpackage bằng **@NamedInterface** |
| Named Interface đã đúng nhưng consumer chưa được cấp quyền | Bổ sung đúng entry **module :: interface** vào allowlist của consumer |
| Hai module cùng gọi trực tiếp nhau | Xem lại quyền sở hữu use case; cân nhắc event, SPI hoặc module điều phối |
| Package bị phát hiện thành module ngoài ý muốn | Sửa package layout hoặc detection strategy |
| Module legacy đang mở quá rộng | Chuyển dần consumer sang API/Named Interface rồi đóng module |

Ví dụ, nếu **inventory** chỉ cần tra cứu đơn hàng, hãy công bố một hợp đồng nghiệp vụ:

~~~java
package com.acme.shop.orders;

public interface OrderLookup {

    boolean exists(String orderId);
}
~~~

Implementation và repository vẫn nằm trong **orders.internal**:

~~~java
package com.acme.shop.orders.internal;

public class JpaOrderRepository {
    // Chi tiết truy cập dữ liệu chỉ thuộc module orders.
}
~~~

Consumer dùng hợp đồng:

~~~java
package com.acme.shop.inventory.internal;

import com.acme.shop.orders.OrderLookup;

class InventoryService {

    private final OrderLookup orderLookup;

    InventoryService(OrderLookup orderLookup) {
        this.orderLookup = orderLookup;
    }
}
~~~

Sau thay đổi, consumer không còn biết repository hoặc cấu trúc lưu trữ của provider. Module **orders** có thể thay đổi persistence implementation mà không làm inventory phụ thuộc vào chi tiết đó.

## 12. Quy trình điều tra một access violation

Khi test kiến trúc báo access violation, hãy làm lần lượt:

1. Chạy **detectViolations()** và đọc toàn bộ thông báo.
2. Ghi lại consumer, provider và fully qualified name của type bị tham chiếu.
3. Tìm nơi consumer sử dụng type đó trong import, field, constructor, method signature hoặc generic type.
4. Dùng mô hình **ApplicationModules** để xác định module sở hữu type và kiểm tra **isExposed(…)**.
5. Kiểm tra type nằm trong root package, Named Interface hay package nội bộ.
6. Phân biệt access violation với disallowed dependency và cycle.
7. Kiểm tra **allowedDependencies**, **@NamedInterface**, **Type.OPEN**, module detection và exclusion nếu kết quả chưa khớp với mã nguồn.
8. Chọn sửa API, Named Interface, consumer dependency hoặc package ownership theo nguyên nhân.
9. Chạy lại **ApplicationModules.verify()** và kiểm thử hành vi của consumer bị ảnh hưởng.

Đọc vị trí nguyên nhân giúp tránh sửa nhầm lớp metadata. Một access violation thường là tín hiệu rằng consumer đang biết quá nhiều về cách provider triển khai. Khi consumer chuyển sang hợp đồng được công bố đúng, module provider có thể giữ quyền kiểm soát implementation và ranh giới kiến trúc trở nên rõ ràng hơn.

## Tài liệu tham khảo

- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): các quy tắc verification và cách lấy danh sách vi phạm bằng **detectViolations()**.
- [Spring Modulith Reference — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html): API package mặc định, Named Interface, Open Module và **allowedDependencies**.
- [Javadoc — ApplicationModules](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html): **detectViolations()**, **stream()** và các API mô hình.
- [Javadoc — ApplicationModule](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html): **contains()**, **isExposed()**, base package và allowed dependencies.
- [Javadoc — Violations](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/Violations.html): **getMessages()**, **hasViolations()**, **filter()** và **throwIfPresent()**.
- [Javadoc — Violation](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/Violation.html): **getMessage()** và **hasMessageContaining()**.
