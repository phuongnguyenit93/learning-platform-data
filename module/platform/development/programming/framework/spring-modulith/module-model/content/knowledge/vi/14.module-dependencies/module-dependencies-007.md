# Dependency tới root package và named interface

Trong Spring Modulith, một Application Module có thể công bố nhiều nhóm hợp đồng để module khác sử dụng. Nhóm mặc định nằm trong **root package (base package)** của module. Các package con chỉ trở thành API liên module khi được công bố thành **Named Interface**. Ở phía module tiêu thụ, **@ApplicationModule(allowedDependencies = …)** xác định module được phép phụ thuộc và giao diện nào của module đó được phép tham chiếu.

Vì vậy, dependency tới **orders** và dependency tới **orders :: spi** là hai quyền khác nhau. Bài học này giải thích cách phân biệt chúng, cách khai báo allowlist ở đúng module, cách đọc các cú pháp **\*** và **\*\***, và cách kiểm tra dependency thực tế bằng **ApplicationModules.verify()**.

## 1. Root package là API package mặc định

Giả sử ứng dụng có package gốc **com.acme.shop** và module **orders**:

~~~text
com.acme.shop
├── ShopApplication.java
├── orders
│   ├── OrderManagement.java
│   ├── OrderId.java
│   ├── spi
│   │   ├── package-info.java
│   │   └── OrderPricingPolicy.java
│   ├── events
│   │   ├── package-info.java
│   │   └── OrderPlaced.java
│   └── internal
│       └── JpaOrderRepository.java
└── inventory
    └── InventoryService.java
~~~

Theo quy tắc mặc định của một module đóng:

- **com.acme.shop.orders** là root package (base package) của module **orders**.
- Các type public đặt trực tiếp trong root package thuộc API package mặc định, còn gọi là unnamed interface.
- **orders.spi** và **orders.events** là subpackage. Chúng không tự động trở thành API chỉ vì tên package có ý nghĩa.
- **orders.internal** là chi tiết triển khai và không được module khác tham chiếu theo quy tắc expose mặc định.

Ví dụ, module **orders** công bố hợp đồng nghiệp vụ trong root package:

~~~java
package com.acme.shop.orders;

public interface OrderManagement {

    OrderDetails findOrder(String orderId);
}
~~~

Module **inventory** có thể import **OrderManagement** khi được phép phụ thuộc vào API mặc định của **orders**:

~~~java
import com.acme.shop.orders.OrderManagement;
~~~

Root package là giao diện mặc định mà module cung cấp. Module tiêu thụ không cần khai báo Named Interface cho root package này.

## 2. Named Interface công bố một subpackage

Nếu module muốn công bố thêm một nhóm hợp đồng nằm trong subpackage, hãy đánh dấu package đó bằng **@NamedInterface**.

Ví dụ, module **orders** có một SPI để module khác cung cấp chính sách tính giá:

~~~java
package com.acme.shop.orders.spi;

import java.math.BigDecimal;

public interface OrderPricingPolicy {

    BigDecimal calculate(String customerId, BigDecimal subtotal);
}
~~~

Tạo **package-info.java** trong **com.acme.shop.orders.spi**:

~~~java
@org.springframework.modulith.NamedInterface("spi")
package com.acme.shop.orders.spi;
~~~

Sau khai báo này, **orders.spi** trở thành Named Interface có tên **spi**. Module khác được phép tham chiếu type thuộc giao diện này nếu dependency rule của consumer cho phép.

Một package khác có thể được công bố độc lập:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.orders.events;
~~~

Khi đó, module **orders** có hai Named Interface là **spi** và **events**, bên cạnh API package mặc định. Named Interface vẫn thuộc module **orders**; nó không tạo ra Application Module mới.

Với Kotlin, có thể khai báo metadata package bằng class có **@PackageInfo** và **@NamedInterface**:

~~~kotlin
package com.acme.shop.orders.spi

import org.springframework.modulith.NamedInterface
import org.springframework.modulith.PackageInfo

@PackageInfo
@NamedInterface("spi")
class ModuleMetadata
~~~

## 3. allowedDependencies được khai báo ở module tiêu thụ

**allowedDependencies** mô tả outgoing dependency mà module hiện tại được phép có. Vì vậy, annotation phải được đặt ở root package của **module tiêu thụ**, thường trong **package-info.java**.

Ví dụ, **inventory** chỉ cần gọi API mặc định **OrderManagement** của **orders**. Trong **com.acme.shop.inventory/package-info.java**:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders"
)
package com.acme.shop.inventory;
~~~

Với cấu hình này, **inventory** được phép tham chiếu API package mặc định của **orders**. Nếu mã nguồn **inventory** import một type thuộc **orders.spi** hoặc **orders.events**, dependency đó không nằm trong allowlist vừa khai báo.

Nếu **inventory** chỉ cần **OrderPricingPolicy** trong Named Interface **spi**, khai báo:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders :: spi"
)
package com.acme.shop.inventory;
~~~

Khi đó, **inventory** được phép dùng type trong **orders.spi**, nhưng không được dùng **OrderManagement** trong root package chỉ nhờ khai báo này.

Điểm cần nhớ:

- **orders** chọn API package mặc định.
- **orders :: spi** chọn Named Interface **spi**.
- **allowedDependencies** được khai báo ở consumer, không phải module cung cấp.
- Allowlist không tự công bố package nội bộ. Package phải được expose trước bằng vị trí root package hoặc **@NamedInterface**.

## 4. Cú pháp module :: interface

Cú pháp tổng quát để chọn một Named Interface là:

~~~text
<logical-module-name> :: <named-interface-name>
~~~

Ví dụ:

| Khai báo | Phạm vi được phép |
|---|---|
| **"orders"** | API package mặc định của module **orders** |
| **"orders :: spi"** | Named Interface **spi** của **orders** |
| **"orders :: events"** | Named Interface **events** của **orders** |

Phần trước **::** là tên module theo logical name mà Spring Modulith nhận diện. Mặc định, tên này thường là segment cuối của base package, ví dụ **com.acme.shop.orders** có logical name **orders**. Phần sau **::** là tên được khai báo trong **@NamedInterface("…")**.

Không dùng tên class hoặc tên package con tùy ý thay cho tên Named Interface. Ví dụ, **orders :: OrderPricingPolicy** không đúng nếu giao diện được khai báo với tên **spi**. Hãy dùng chính tên **spi** trong metadata.

## 5. Cho phép root package và Named Interface cùng lúc

Một consumer đôi khi cần cả API mặc định lẫn một nhóm hợp đồng được công bố riêng. Có thể khai báo từng quyền:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "orders",
        "orders :: spi"
    }
)
package com.acme.shop.inventory;
~~~

Trong ví dụ này, **inventory** được phép import cả:

~~~java
import com.acme.shop.orders.OrderManagement;
import com.acme.shop.orders.spi.OrderPricingPolicy;
~~~

Nếu consumer cần tất cả giao diện được công bố của module, Spring Modulith hỗ trợ wildcard:

| Khai báo | Phạm vi |
|---|---|
| **"orders :: \*"** | Tất cả Named Interface được khai báo tường minh; không bao gồm root package |
| **"orders :: \*\*"** | Root package mặc định và tất cả Named Interface được khai báo |

**orders :: \*\*** tương đương với việc cho phép root package và toàn bộ Named Interface của module **orders**. Nếu chỉ cần hai giao diện cụ thể, khai báo rõ từng mục thường giúp người đọc hiểu dependency intent dễ hơn.

## 6. Phân biệt không khai báo, allowlist và danh sách rỗng

Ba trường hợp sau có ý nghĩa khác nhau:

| Cấu hình ở module tiêu thụ | Ý nghĩa |
|---|---|
| Không khai báo **allowedDependencies** | Không bật giới hạn allowlist; module có thể tham chiếu các API đã expose của module khác theo quy tắc mặc định |
| **allowedDependencies = "orders"** | Chỉ cho phép dependency tới API package mặc định của **orders** trong danh sách đã khai báo |
| **allowedDependencies = {}** | Không cho phép dependency tới Application Module khác |

Không nên nhầm giá trị mặc định của annotation với một mảng rỗng tường minh. Bỏ thuộc tính **allowedDependencies** nghĩa là không giới hạn dependency bằng allowlist; đặt **{}** nghĩa là không cho phép module dependency nào.

Khi allowlist được khai báo, mọi outgoing dependency liên module cần nằm trong danh sách. Mã nguồn vẫn có thể biên dịch nếu type được khai báo **public**, nhưng Spring Modulith sẽ phát hiện dependency không được phép khi chạy verification.

## 7. Một ví dụ có nhiều consumer và nhiều interface

Giả sử **orders** công bố ba hợp đồng:

~~~text
orders
├── OrderManagement.java       <- root package
├── spi
│   ├── package-info.java       <- @NamedInterface("spi")
│   └── OrderPricingPolicy.java
├── events
│   ├── package-info.java       <- @NamedInterface("events")
│   └── OrderPlaced.java
└── internal
    └── JpaOrderRepository.java
~~~

Các module tiêu thụ cần những quyền khác nhau:

~~~java
// checkout chỉ gọi API nghiệp vụ mặc định.
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders"
)
package com.acme.shop.checkout;
~~~

~~~java
// promotions triển khai SPI do orders sở hữu.
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders :: spi"
)
package com.acme.shop.promotions;
~~~

~~~java
// shipping chỉ lắng nghe event được công bố.
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders :: events"
)
package com.acme.shop.shipping;
~~~

Dependency graph thể hiện rõ từng hợp đồng:

~~~text
checkout ─────────> orders (root API)

promotions ───────> orders :: spi

shipping ─────────> orders :: events
~~~

Nhờ tách quyền theo Named Interface, **checkout** không cần biết SPI, **promotions** không cần quyền gọi toàn bộ API nghiệp vụ và **shipping** chỉ phụ thuộc vào event contract. Module **orders** có thể duy trì từng nhóm hợp đồng theo mục đích sử dụng.

## 8. allowedDependencies không thay thế Java visibility

**allowedDependencies** là quy tắc kiến trúc của Spring Modulith, không phải cơ chế kiểm soát truy cập của ngôn ngữ Java.

Một class **public** trong package **orders.internal** có thể được Java compiler cho phép import. Tuy nhiên:

- Nếu **orders** là module đóng, package **internal** không được công bố mặc định.
- Thêm **"orders"** vào allowlist không làm **orders.internal** trở thành API.
- Thêm **"orders :: spi"** chỉ cấp quyền với Named Interface **spi**, không cấp quyền cho **internal**.
- Muốn công bố một subpackage, hãy đánh dấu nó bằng **@NamedInterface** và chỉ cấp quyền cho consumer cần dùng.

Ví dụ, import sau vẫn sai về ranh giới nếu **JpaOrderRepository** nằm trong package nội bộ:

~~~java
import com.acme.shop.orders.internal.JpaOrderRepository;
~~~

Giải pháp là để module sở hữu dữ liệu cung cấp API hoặc Named Interface phù hợp. Consumer nên phụ thuộc vào hợp đồng nghiệp vụ ổn định thay vì repository hay entity nội bộ.

## 9. Kiểm chứng dependency thực tế

Tạo bài test kiến trúc để Spring Modulith phân tích toàn bộ Application Module:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesAllowedModuleDependencies() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

**verify()** kiểm tra dependency thực tế trong mã nguồn so với các quy tắc module, bao gồm:

1. Consumer có tham chiếu type thuộc package API hoặc Named Interface đã được công bố hay không.
2. Consumer có dependency ngoài danh sách **allowedDependencies** hay không.
3. Dependency graph có chu trình ở cấp Application Module hay không.

Khi test thất bại, đọc module tiêu thụ, module cung cấp và package của type được tham chiếu. Sau đó xác định một trong các cách sửa:

- Chuyển type về root package nếu đó là API mặc định của module.
- Công bố subpackage bằng **@NamedInterface** nếu đó là một nhóm hợp đồng riêng.
- Thêm đúng module hoặc Named Interface vào allowlist của consumer nếu dependency là có chủ đích.
- Xóa import vào package nội bộ nếu consumer đang phụ thuộc vào chi tiết triển khai.

## 10. Quy trình chọn dependency đúng

Khi một module cần sử dụng type từ module khác, hãy thực hiện:

1. Xác định module sở hữu type và base package của module đó.
2. Kiểm tra type nằm trực tiếp trong root package hay trong subpackage.
3. Nếu nằm trong subpackage, xác nhận package đã được công bố bằng Named Interface.
4. Xác định consumer cần API mặc định, một Named Interface hay nhiều giao diện.
5. Khai báo **allowedDependencies** tại root package của consumer.
6. Dùng **\*** hoặc **\*\*** chỉ khi thật sự cần quyền rộng trên các Named Interface.
7. Chạy **ApplicationModules.of(ShopApplication.class).verify()** để xác nhận các import thực tế tuân thủ ranh giới.

Dependency tới root package thể hiện consumer đang sử dụng API chính của module. Dependency tới Named Interface thể hiện consumer chỉ cần một nhóm hợp đồng được công bố riêng. Khi khai báo đúng mức cần thiết, dependency graph trở nên dễ đọc, quyền phụ thuộc rõ ràng và module cung cấp có thể thay đổi phần triển khai nội bộ với ít ảnh hưởng hơn đến consumer.

## Tài liệu tham khảo

- [Spring Modulith Reference — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html): API package mặc định, Named Interfaces và cú pháp **allowedDependencies**.
- [Spring Modulith Javadoc — ApplicationModule](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html): thuộc tính **allowedDependencies**, tên module và tham chiếu Named Interface bằng **::**.
- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html): kiểm tra dependency thực tế và các quy tắc kiến trúc.
