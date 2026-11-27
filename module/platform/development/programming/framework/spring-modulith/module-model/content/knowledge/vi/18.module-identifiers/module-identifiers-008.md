# Tránh identifier trùng hoặc mơ hồ

Spring Modulith gán một logical identifier cho mỗi Application Module để tham chiếu module trong dependency rule, metadata và các công cụ hỗ trợ. Theo mặc định, identifier được suy ra từ vị trí package của module trong cấu trúc được phát hiện. Cách đặt tên này thuận tiện khi ứng dụng có một package root rõ ràng, nhưng có thể gây trùng hoặc khó hiểu khi ứng dụng quét nhiều root package, có module lồng nhau hoặc thay đổi cấu trúc package.

Để tránh nhầm lẫn, cần phân biệt **module identifier**, **base package** và **display name**. Khi tên mặc định không đủ rõ, có thể đặt identifier bằng **@ApplicationModule(id = "...")** hoặc bật chế độ dùng fully qualified module names ở cấp ứng dụng. Bài học này trình bày cách chọn phương án, cập nhật dependency reference và kiểm tra tính duy nhất của identifier.

## 1. Identifier, base package và display name là ba khái niệm khác nhau

Một Application Module có ít nhất ba thông tin cần phân biệt:

| Khái niệm | Ý nghĩa | Ví dụ |
|---|---|---|
| Base package | Package gốc chứa mã nguồn của module | **com.acme.shop.orders** |
| Identifier | Tên logic để Spring Modulith nhận diện và tham chiếu module | **shop-orders** |
| Display name | Tên dễ đọc dùng khi hiển thị hoặc tạo tài liệu | **Shop Orders** |

Identifier không phải tên class, tên Maven artifact hay tên hiển thị. Nó là khóa logic của module trong mô hình Spring Modulith. Ví dụ, module có thể được đặt tại **com.acme.shop.orders**, có identifier **shop-orders** và display name **Shop Orders**.

**displayName** chủ yếu phục vụ hiển thị và tài liệu. Đổi display name không phải cách xử lý xung đột identifier. Ngược lại, đổi identifier có thể ảnh hưởng đến các nơi đang tham chiếu module bằng tên logic đó, chẳng hạn **allowedDependencies** hoặc **sharedModules**.

## 2. Identifier mặc định được suy ra như thế nào?

Spring Modulith phát hiện module dựa trên package structure và application root. Identifier mặc định được tạo từ vị trí tương đối của module dưới root package được quét. Với một module đơn giản nằm trực tiếp dưới root, identifier thường trùng với tên package cuối.

Ví dụ:

~~~text
com.acme.shop                 <- application root
├── orders                    <- module identifier: orders
├── inventory                 <- module identifier: inventory
└── payments                  <- module identifier: payments
~~~

Với module nằm sâu hơn trong một root được quét, tên logic có thể chứa phần package tương đối. Chẳng hạn, nếu root được quét là **com.acme** và module nằm tại **com.acme.shop.orders**, tên mặc định có thể là **shop.orders**.

Điều này giúp tránh một số trùng lặp trong cùng một cây package. Tuy nhiên, khi một ứng dụng có nhiều root package được quét, các module có cùng local name dưới những root khác nhau vẫn có thể tạo ra identifier cục bộ giống nhau.

## 3. Tình huống gây identifier trùng hoặc mơ hồ

Giả sử một ứng dụng tổng hợp hai vùng package:

~~~text
com.acme.shop
└── orders
    └── OrderManagement.java

com.acme.billing
└── orders
    └── InvoiceOrderManagement.java
~~~

Ứng dụng chính có thể dùng **@Modulithic(additionalPackages = "com.acme.billing")** để Spring Modulith phát hiện module dưới cả hai root. Nếu dùng tên module cục bộ, cả hai package **orders** có thể cùng được tham chiếu bằng identifier **orders**.

Khi đó, một khai báo như:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders"
)
package com.acme.shop.shipping;
~~~

không thể hiện rõ consumer muốn phụ thuộc vào **shop.orders** hay **billing.orders**. Tên module trở nên mơ hồ đối với người đọc và có thể gây xung đột trong mô hình.

Các dấu hiệu nên rà soát:

- Nhiều **additionalPackages** hoặc nhiều root package cùng được quét.
- Các root khác nhau có package con cùng tên như **orders**, **users**, **catalog** hoặc **shared**.
- Module lồng nhau có tên ngắn giống module ở nhánh khác.
- Dependency rule chỉ dùng tên quá chung như **core**, **common**, **api** hoặc **service**.
- Tên module được dùng trong cấu hình, test hoặc tài liệu nhưng không thể truy ngược dễ dàng về base package.

## 4. Cách 1: Đặt identifier tường minh bằng @ApplicationModule(id)

Khi muốn identifier ổn định và có ý nghĩa nghiệp vụ, hãy đặt **id** trong metadata của package gốc module:

~~~java
@org.springframework.modulith.ApplicationModule(
    id = "shop-orders",
    displayName = "Shop Orders"
)
package com.acme.shop.orders;
~~~

Module còn lại có thể dùng một identifier riêng:

~~~java
@org.springframework.modulith.ApplicationModule(
    id = "billing-orders",
    displayName = "Billing Orders"
)
package com.acme.billing.orders;
~~~

Giờ đây, dependency reference có thể chỉ rõ module cần dùng:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "shop-orders"
)
package com.acme.shop.shipping;
~~~

Nếu consumer cần một Named Interface, kết hợp identifier với tên interface:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "shop-orders :: events"
)
package com.acme.shop.shipping;
~~~

Trong ví dụ, **shop-orders** là identifier của module còn **events** là tên Named Interface được công bố bên trong module đó.

### Quy tắc đặt id

Javadoc của **@ApplicationModule.id** quy định identifier không được chứa dấu phân cách **::**. **ApplicationModuleIdentifier.of(…)** cũng yêu cầu chuỗi không null, không rỗng và không chứa **::**.

Ngoài ràng buộc của framework, nên áp dụng quy ước dễ đọc:

- Dùng chữ thường và dấu gạch nối, ví dụ **shop-orders**, **billing-orders**.
- Đặt tên theo capability hoặc bounded context, không chỉ theo tầng kỹ thuật.
- Giữ identifier ổn định khi refactor package nếu danh tính nghiệp vụ của module không đổi.
- Đảm bảo mỗi module trong cùng application model có một identifier riêng.
- Tránh nhúng tên team, tên cá nhân, phiên bản triển khai hoặc thông tin tạm thời vào identifier.

Tính duy nhất là quy tắc thiết kế cần được kiểm tra trong application model. Không nên dựa vào việc một tên trùng sẽ được tự động phân giải theo ý muốn.

## 5. Khai báo id trong Kotlin

Kotlin không dùng **package-info.java**. Có thể đặt **@ApplicationModule** trên một type metadata nằm trong root package và đánh dấu type đó bằng **@PackageInfo**:

~~~kotlin
package com.acme.shop.orders

import org.springframework.modulith.ApplicationModule
import org.springframework.modulith.PackageInfo

@ApplicationModule(
    id = "shop-orders",
    displayName = "Shop Orders"
)
@PackageInfo
class ModuleMetadata
~~~

Đặt metadata class trong đúng package gốc của module. Nếu đặt ở package con, Spring Modulith có thể đọc metadata cho một package khác với module mà bạn định cấu hình.

## 6. Cách 2: Dùng fully qualified module names

Nếu vấn đề đến từ nhiều root package có module con trùng local name, có thể cấu hình ứng dụng sử dụng fully qualified module names:

~~~java
package com.acme.shop;

import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.modulith.Modulithic;

@Modulithic(
    additionalPackages = "com.acme.billing",
    useFullyQualifiedModuleNames = true
)
@SpringBootApplication
public class ShopApplication {
}
~~~

Với cấu hình này, tên module mặc định sử dụng package đầy đủ thay vì tên cục bộ. Hai module ở ví dụ trước sẽ được tham chiếu bằng:

~~~text
com.acme.shop.orders
com.acme.billing.orders
~~~

Dependency rule có thể ghi rõ package đầy đủ:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "com.acme.shop.orders"
)
package com.acme.shop.shipping;
~~~

Nếu dùng Named Interface:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "com.acme.shop.orders :: events"
)
package com.acme.shop.shipping;
~~~

Chế độ fully qualified names đặc biệt hữu ích khi các root package bổ sung có thể chứa module cùng local name. Đổi chế độ này là thay đổi quy ước định danh của toàn application model; cần rà soát các khai báo **allowedDependencies**, **sharedModules** và các cấu hình đang dùng tên cục bộ.

## 7. Nên chọn explicit id hay fully qualified names?

Hai cách giải quyết những nhu cầu hơi khác nhau:

| Nhu cầu | Lựa chọn phù hợp |
|---|---|
| Muốn identifier ổn định qua thay đổi package | **@ApplicationModule(id = "...")** |
| Nhiều root package có local module name trùng nhau | **useFullyQualifiedModuleNames = true** |
| Muốn tên module ngắn, thể hiện capability nghiệp vụ | Explicit id |
| Muốn identifier phản ánh chính xác vị trí package | Fully qualified names |
| Có nhiều module từ package ngoài được bổ sung | Cân nhắc fully qualified names hoặc explicit id |
| Chỉ cần tên thân thiện trong tài liệu | **displayName** |

Không cần đặt explicit id cho mọi module nếu tên mặc định đã duy nhất và đủ rõ. Hãy bổ sung id tường minh cho các module có nguy cơ xung đột hoặc cần giữ danh tính ổn định qua refactor. Nếu bật fully qualified names, hãy dùng cùng một quy ước nhất quán cho dependency references.

## 8. Identifier ảnh hưởng đến allowedDependencies và Named Interface

**allowedDependencies** tham chiếu module bằng logical identifier. Khi một module có explicit id, consumer cần dùng id đó:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "shop-orders",
        "shop-orders :: events"
    }
)
package com.acme.shop.shipping;
~~~

Không nên tiếp tục dùng tên package cũ hoặc local name cũ sau khi đổi id. Các tham chiếu sau có thể trở thành sai hoặc mơ hồ:

~~~java
// Tên cũ hoặc tên quá chung, không còn phù hợp sau khi đổi identifier.
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "orders"
)
package com.acme.shop.shipping;
~~~

Khi đổi identifier, hãy tìm và cập nhật tất cả nơi tham chiếu:

- **allowedDependencies** của các consumer.
- **sharedModules** trong metadata **@Modulithic** hoặc **@Modulith**.
- Cấu hình hoặc mã test gọi module bằng tên.
- Tài liệu kiến trúc và sơ đồ dependency được duy trì thủ công.
- Các cấu hình runtime hoặc công cụ nội bộ dùng module identifier làm khóa.

Named Interface vẫn được phân biệt bằng **::**. Identifier module không được chứa **::** vì framework dùng dấu phân cách này để tách module name khỏi interface name.

## 9. Không dùng displayName để xử lý identifier collision

Ví dụ sau chỉ đổi tên hiển thị:

~~~java
@org.springframework.modulith.ApplicationModule(
    displayName = "Shop Orders"
)
package com.acme.shop.orders;
~~~

**displayName** không thay thế logical identifier. Nếu hai module đều có tên logic **orders**, đặt display name thành **Shop Orders** và **Billing Orders** không giải quyết được xung đột khi tham chiếu dependency.

Khi cần phân biệt module trong cấu hình, hãy dùng **id** hoặc fully qualified module names. Dùng **displayName** cho người đọc trong tài liệu, sơ đồ và báo cáo.

## 10. Kiểm tra identifier của toàn bộ application model

Sau khi đặt id hoặc đổi naming strategy, hãy in ra identifier, base package và display name của từng module:

~~~java
import org.springframework.modulith.core.ApplicationModules;

class ModuleIdentifierInspection {

    void printModules() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        modules.stream().forEach(module ->
            System.out.printf(
                "id=%s | package=%s | displayName=%s%n",
                module.getIdentifier(),
                module.getBasePackage().getName(),
                module.getDisplayName()
            )
        );
    }
}
~~~

**ApplicationModule.getIdentifier()** trả về logical identifier. **getBasePackage()** cho biết package sở hữu module và **getDisplayName()** cho biết tên dùng để hiển thị. So sánh ba giá trị này giúp phát hiện:

- Hai package khác nhau nhưng có identifier giống nhau.
- Identifier quá chung khiến dependency rule khó đọc.
- Identifier bị đổi ngoài dự kiến sau khi thêm root package.
- Display name bị nhầm với identifier trong cấu hình.

Có thể thêm assertion bảo vệ tính duy nhất:

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModuleIdentifierTests {

    @Test
    void moduleIdentifiersAreUnique() {
        ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

        List<String> identifiers = modules.stream()
            .map(module -> module.getIdentifier().toString())
            .toList();

        Set<String> uniqueIdentifiers = identifiers.stream()
            .collect(Collectors.toSet());

        assertThat(uniqueIdentifiers).hasSize(identifiers.size());
    }
}
~~~

Assertion này biến quy tắc duy nhất thành một điều kiện kiểm tra rõ ràng. Nếu danh sách module thay đổi sau khi thêm root package hoặc refactor, test sẽ nhắc đội ngũ xem lại naming convention.

Có thể kiểm tra một identifier được phân giải đúng module:

~~~java
var shopOrders = modules.getModuleByName("shop-orders");

assertThat(shopOrders).isPresent();
assertThat(shopOrders.get().getBasePackage().getName())
    .isEqualTo("com.acme.shop.orders");
~~~

**getModuleByName(…)** trả về **Optional<ApplicationModule>**. Dùng nó trong test để xác nhận identifier đang trỏ tới đúng base package mong muốn, thay vì chỉ xác nhận tên đó tồn tại.

## 11. Kiểm chứng dependency sau khi đổi identifier

Sau khi cập nhật id hoặc bật fully qualified names, chạy verification:

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

Verification giúp phát hiện các dependency reference không còn khớp với module/interface được công bố, bên cạnh những quy tắc cấu trúc khác như access vào package nội bộ và dependency cycle.

Tuy nhiên, **verify()** không thể biết một identifier ngắn có dễ hiểu với đội ngũ hay không. Hãy kết hợp test tính duy nhất, test phân giải identifier về đúng base package và review các dependency declaration.

## 12. Các lỗi thường gặp

**Dùng cùng một explicit id cho nhiều module.** Identifier phải đại diện rõ một module trong application model. Hãy chọn id khác nhau và kiểm tra bằng test uniqueness.

**Đổi package rồi nghĩ identifier sẽ tự ổn định.** Nếu dùng tên mặc định, refactor package hoặc thay đổi root package có thể làm thay đổi logical name. Đặt explicit id nếu danh tính module cần giữ nguyên.

**Chỉ đổi displayName.** Tên hiển thị không thay đổi logical identifier và không sửa được dependency reference bị trùng.

**Đưa :: vào id.** Đây là dấu phân cách dành cho Named Interface. Identifier không được chứa chuỗi này.

**Bật fully qualified names nhưng giữ allowlist theo local name.** Sau khi đổi naming strategy, rà soát và cập nhật các dependency reference theo tên đầy đủ.

**Chỉ kiểm tra identifier tồn tại.** Một tên có thể phân giải nhưng vẫn trỏ tới module không đúng ý định. Hãy kiểm tra cả base package của module được trả về.

**Đặt id theo tầng kỹ thuật.** Tên như **service**, **repository** hoặc **common** thường không thể hiện capability và dễ trở nên mơ hồ khi ứng dụng mở rộng.

## 13. Quy trình chọn và duy trì module identifier

Khi thiết kế hoặc rà soát identifier, hãy làm theo trình tự:

1. Tạo **ApplicationModules** từ class ứng dụng và liệt kê toàn bộ module được phát hiện.
2. Ghi lại identifier, base package và display name của từng module.
3. Kiểm tra có nhiều root package hoặc module có local name trùng nhau hay không.
4. Nếu chỉ xung đột do nhiều root package, cân nhắc **useFullyQualifiedModuleNames = true**.
5. Nếu cần tên ngắn và ổn định qua refactor, đặt **@ApplicationModule(id = "...")** tường minh.
6. Đảm bảo id không rỗng, không chứa **::** và duy nhất trong application model.
7. Cập nhật **allowedDependencies**, **sharedModules** và các nơi tham chiếu module.
8. Viết test kiểm tra uniqueness và ánh xạ identifier về đúng base package.
9. Chạy **ApplicationModules.verify()** để xác nhận dependency graph vẫn hợp lệ.

Một identifier tốt giúp người đọc biết module nào đang được tham chiếu mà không phải đoán từ một tên package chung chung. Khi logical identity được quản lý rõ ràng, dependency rules, module tests, tài liệu kiến trúc và công cụ runtime có thể cùng sử dụng một quy ước nhất quán.

## Tài liệu tham khảo

- [Spring Modulith Reference — Fundamentals](https://docs.spring.io/spring-modulith/reference/fundamentals.html): cách phát hiện Application Module, module arrangement và các cấu hình ở cấp ứng dụng.
- [Spring Modulith Javadoc — ApplicationModule](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html): thuộc tính **id**, **displayName** và **allowedDependencies**.
- [Spring Modulith Javadoc — ApplicationModuleIdentifier](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModuleIdentifier.html): tạo và ràng buộc của logical identifier.
- [Spring Modulith Javadoc — ApplicationModule](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModule.html): **getIdentifier()**, **getBasePackage()** và **getDisplayName()**.
- [Spring Modulith Javadoc — Modulithic](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/Modulithic.html): **useFullyQualifiedModuleNames** và **additionalPackages**.
- [Spring Modulith Javadoc — ApplicationModules](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html): **stream()** và **getModuleByName()**.
