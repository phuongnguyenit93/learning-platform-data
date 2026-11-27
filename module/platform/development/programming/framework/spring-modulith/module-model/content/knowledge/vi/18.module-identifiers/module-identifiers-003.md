# Display name và identifier khác nhau ra sao?

Trong Spring Modulith, mỗi application module có một định danh để các module khác tham chiếu đến nó. Module cũng có thể có một tên hiển thị thân thiện với người đọc trong tài liệu kiến trúc. Hai giá trị này phục vụ hai mục đích khác nhau: **identifier** dùng để nhận diện module trong mô hình và các khai báo dependency; **display name** dùng để trình bày module cho con người.

Ví dụ, module có package **com.acme.shop.inventory** có thể dùng identifier **inventory** và display name **Inventory Management**. Khi đổi display name thành **Stock Management**, dependency của module **order** vẫn tham chiếu **inventory**. Ngược lại, nếu đổi identifier thành **stock**, các khai báo dependency dùng identifier cũ cần được xem xét và cập nhật.

Trong SPRING_MODULITH_MODULE_MODEL, phân biệt rõ hai giá trị giúp giữ ổn định dependency graph khi nhóm đổi cách gọi nghiệp vụ, cải thiện tài liệu hoặc tái tổ chức package. Bài học này giải thích cách Spring Modulith nhận diện module, cách cấu hình id và displayName, cách chúng liên quan đến Named Interface và allowedDependencies, cùng quy trình đổi tên an toàn.

## 1. Hai khái niệm, hai trách nhiệm

| Thuộc tính | Module identifier | Display name |
|---|---|---|
| Mục đích | Nhận diện module trong mô hình kiến trúc | Tên thân thiện để người đọc hiểu module |
| Người dùng chính | Spring Modulith, dependency declarations, tooling | Người đọc tài liệu và sơ đồ |
| Ví dụ | inventory | Inventory Management |
| Dạng khuyến nghị | Token ngắn, ổn định, không phụ thuộc cách trình bày | Từ hoặc cụm từ tự nhiên, có thể chứa dấu cách |
| Khi đổi | Có thể ảnh hưởng reference tới module | Thường chỉ ảnh hưởng cách hiển thị |
| Có đổi Java package không? | Không tự đổi package | Không |
| Có thay đổi behavior nghiệp vụ không? | Không tự thay đổi behavior | Không |

Identifier trả lời câu hỏi: “Dependency này trỏ tới module nào?”. Display name trả lời câu hỏi: “Nên gọi module này thế nào để người đọc hiểu?”.

Không dùng display name làm khóa kỹ thuật. Tên hiển thị có thể được chỉnh để phù hợp ngôn ngữ tài liệu, thuật ngữ nghiệp vụ hoặc cách tổ chức nhóm mà không cần đổi các tham chiếu dependency.

## 2. Spring Modulith nhận diện application module như thế nào?

Spring Modulith phát hiện application module từ cấu trúc package bên dưới package gốc của ứng dụng. Theo cấu trúc mặc định, package con trực tiếp của package ứng dụng thường trở thành module riêng.

Ví dụ:

~~~text
com.acme.shop
├── ShopApplication.java
├── inventory
│   ├── package-info.java
│   ├── InventoryAvailability.java
│   └── internal
├── order
│   ├── package-info.java
│   └── PlaceOrderService.java
└── catalog
    ├── package-info.java
    └── ProductCatalog.java
~~~

Trong ví dụ này, **inventory**, **order** và **catalog** là các module được phát hiện theo package. Nếu không cấu hình identifier tường minh, tên module thường được suy ra từ tên package gốc của module. Vì vậy, **com.acme.shop.inventory** có identifier mặc định tương ứng với **inventory**.

Tên package và identifier có quan hệ theo quy ước mặc định, nhưng chúng không phải cùng một khái niệm. Khi cần giữ một định danh ổn định qua thay đổi package, có thể khai báo **id** tường minh bằng **@ApplicationModule** nếu phiên bản Spring Modulith của dự án hỗ trợ thuộc tính đó.

## 3. Cấu hình id và displayName bằng @ApplicationModule

Annotation **@ApplicationModule** được đặt trên package, thường trong **package-info.java**.

~~~java
@org.springframework.modulith.ApplicationModule(
        id = "inventory",
        displayName = "Inventory Management"
)
package com.acme.shop.inventory;
~~~

Ở đây:

- **id = "inventory"** đặt module identifier dùng trong các tham chiếu kiến trúc.
- **displayName = "Inventory Management"** đặt tên trình bày cho người đọc.
- Package Java vẫn là **com.acme.shop.inventory**.
- Tên class và behavior của module không tự thay đổi.

Có thể thêm các thuộc tính khác của **@ApplicationModule**, chẳng hạn **allowedDependencies**, trong cùng khai báo package. Hãy giữ metadata của module tại một vị trí dễ tìm để reviewer có thể hiểu identity và dependency policy cùng nhau.

Ví dụ:

~~~java
@org.springframework.modulith.ApplicationModule(
        id = "inventory",
        displayName = "Inventory Management",
        allowedDependencies = { "catalog" }
)
package com.acme.shop.inventory;
~~~

Ví dụ trên minh họa việc một module khai báo dependency được cho phép. Identifier của module được tham chiếu phải khớp với identity của provider theo mô hình Spring Modulith.

## 4. Identifier được dùng ở đâu?

Identifier là tên kỹ thuật để tham chiếu module trong metadata kiến trúc. Một nơi dễ thấy nhất là **allowedDependencies**.

Giả sử module **order** được phép gọi API của **inventory**:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "inventory"
)
package com.acme.shop.order;
~~~

Ở đây, **inventory** là module identifier. Nó không phải display name **Inventory Management**, cũng không phải tên đầy đủ **com.acme.shop.inventory**.

Nếu provider khai báo:

~~~java
@org.springframework.modulith.ApplicationModule(
        id = "stock",
        displayName = "Inventory Management"
)
package com.acme.shop.inventory;
~~~

thì consumer cần tham chiếu identifier **stock**:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "stock"
)
package com.acme.shop.order;
~~~

Nếu vẫn dùng **inventory** trong dependency declaration, metadata đã tham chiếu một identifier khác với identifier provider công bố. Verification có thể báo dependency không hợp lệ hoặc không được khai báo như dự kiến.

## 5. Display name phục vụ tài liệu và khả năng đọc

Display name là nhãn diễn đạt ý nghĩa nghiệp vụ. Tên này có thể hữu ích khi tạo tài liệu module, sơ đồ hoặc báo cáo kiến trúc để người đọc không phải diễn giải package token.

Ví dụ:

| Package | Identifier | Display name |
|---|---|---|
| com.acme.shop.inventory | inventory | Inventory Management |
| com.acme.shop.order | order | Order Processing |
| com.acme.shop.catalog | catalog | Product Catalog |
| com.acme.shop.customer | customer | Customer Accounts |

Một display name tốt:

- Mô tả capability hoặc trách nhiệm nghiệp vụ.
- Dễ hiểu với developer, architect và người review.
- Không chứa chi tiết implementation như tên repository hoặc framework.
- Có thể đổi khi thuật ngữ nghiệp vụ thay đổi.
- Không được dùng thay identifier trong dependency declaration.

Ví dụ, **Inventory Management** rõ nghĩa hơn **InvMod**, nhưng cả hai không nên trở thành giá trị trong **allowedDependencies**. Ở đó nên dùng identifier ổn định như **inventory**.

## 6. Đổi display name có ảnh hưởng dependency không?

Thông thường, thay đổi riêng **displayName** không làm đổi module identity và không yêu cầu cập nhật **allowedDependencies** hoặc Named Interface references.

Trước:

~~~java
@ApplicationModule(
        id = "inventory",
        displayName = "Inventory Management"
)
package com.acme.shop.inventory;
~~~

Sau:

~~~java
@ApplicationModule(
        id = "inventory",
        displayName = "Stock Management"
)
package com.acme.shop.inventory;
~~~

Consumer vẫn tham chiếu:

~~~java
@ApplicationModule(allowedDependencies = "inventory")
package com.acme.shop.order;
~~~

Đây là thay đổi trình bày. Tuy nhiên, nếu display name được một hệ thống tài liệu, dashboard hoặc công cụ nội bộ dùng làm key thay vì label, hệ thống đó có thể bị ảnh hưởng. Thiết kế tích hợp nên dùng identifier làm khóa và display name làm nội dung hiển thị.

## 7. Đổi identifier có ảnh hưởng gì?

Đổi identifier là thay đổi metadata kỹ thuật. Tất cả consumer hoặc công cụ tham chiếu identifier cũ cần được xem xét.

Ví dụ đổi **inventory** thành **stock**:

Trước:

~~~java
@ApplicationModule(
        id = "inventory",
        displayName = "Inventory Management"
)
package com.acme.shop.inventory;
~~~

Consumer:

~~~java
@ApplicationModule(allowedDependencies = "inventory")
package com.acme.shop.order;
~~~

Sau:

~~~java
@ApplicationModule(
        id = "stock",
        displayName = "Inventory Management"
)
package com.acme.shop.inventory;
~~~

Consumer phải cập nhật:

~~~java
@ApplicationModule(allowedDependencies = "stock")
package com.acme.shop.order;
~~~

Ngoài **allowedDependencies**, hãy tìm mọi tham chiếu tới identifier cũ trong:

- Named Interface dependency, ví dụ **inventory::events**.
- Architecture tests và fixture.
- Công cụ sinh tài liệu hoặc phân tích module.
- Script hoặc báo cáo nội bộ dùng module identifier.
- Tài liệu thiết kế và ví dụ code.

Đổi identifier không tự đổi package Java. Nếu muốn đổi cả package từ **inventory** sang **stock**, đó là một thay đổi riêng có thể ảnh hưởng imports, component scanning, persistence mapping, module detection và consumer source code.

## 8. Identifier và Named Interface

Named Interface công bố một package con như một phần API có tên của module. Khi consumer tham chiếu Named Interface, dependency identifier thường có dạng:

~~~text
<module-identifier>::<named-interface>
~~~

Ví dụ provider:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.inventory.events;
~~~

Module provider có identifier **inventory**. Consumer muốn phụ thuộc vào event API:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "inventory::events"
)
package com.acme.shop.order;
~~~

Ở đây có hai phần độc lập:

- **inventory** là module identifier.
- **events** là tên Named Interface.

Display name **Inventory Management** không xuất hiện trong dependency string.

Nếu đổi display name, **inventory::events** vẫn giữ nguyên. Nếu đổi identifier thành **stock**, dependency reference cần đổi thành **stock::events**. Nếu đổi tên Named Interface từ **events** sang **domain-events**, consumer cần tham chiếu **inventory::domain-events** hoặc identifier mới tương ứng.

## 9. Identifier không phải tên hiển thị của Named Interface

Không nên nhầm ba khái niệm sau:

| Giá trị | Ví dụ | Vai trò |
|---|---|---|
| Module identifier | inventory | Nhận diện module |
| Module display name | Inventory Management | Tên module cho người đọc |
| Named Interface name | events | Nhận diện một nhóm API công bố trong module |

Dependency **inventory::events** kết hợp module identifier và Named Interface name. Nó không phải chuỗi ghép từ display name.

Ví dụ sai về mặt ý nghĩa:

~~~java
@ApplicationModule(
        allowedDependencies = "Inventory Management::events"
)
package com.acme.shop.order;
~~~

Ví dụ đúng khi identifier của provider là **inventory**:

~~~java
@ApplicationModule(
        allowedDependencies = "inventory::events"
)
package com.acme.shop.order;
~~~

## 10. Khi nào nên khai báo id tường minh?

Nếu tên package ổn định và đã phản ánh tốt capability, identifier mặc định thường đủ dùng. Không cần thêm metadata chỉ để lặp lại một giá trị không tạo thêm ý nghĩa.

Nên cân nhắc **id** tường minh khi:

- Package có thể đổi tên nhưng muốn giữ identity logic của module.
- Tên package kỹ thuật không phù hợp với tên module muốn dùng trong dependency graph.
- Có lịch sử migration từ một module/package cũ.
- Nhiều công cụ hoặc tài liệu phụ thuộc vào một token ổn định.
- Muốn tách cấu trúc package khỏi tên kỹ thuật của module.

Ví dụ package mới:

~~~text
com.acme.shop.stock
~~~

Nhưng vẫn giữ identifier **inventory**:

~~~java
@ApplicationModule(
        id = "inventory",
        displayName = "Inventory Management"
)
package com.acme.shop.stock;
~~~

Consumer tiếp tục khai báo:

~~~java
@ApplicationModule(allowedDependencies = "inventory")
package com.acme.shop.order;
~~~

Điều này tách logical module identity khỏi package name. Tuy vậy, package rename vẫn cần được xử lý trong source code và các cơ chế framework khác; **id** không tự sửa imports hay cấu hình component scanning.

## 11. Khi nào không cần id tường minh?

Không cần khai báo **id** nếu:

- Tên package module đã ổn định.
- Identifier mặc định dễ hiểu và phù hợp.
- Không có nhu cầu giữ logical identity khi đổi package.
- Việc khai báo tường minh chỉ tạo thêm metadata phải bảo trì.

Ví dụ package **com.acme.shop.order** có thể dùng identifier mặc định **order**. Nếu không có lý do đặc biệt, không nhất thiết phải thêm **id = "order"** chỉ để lặp lại quy ước.

Nguyên tắc là chỉ tùy chỉnh identity khi có nhu cầu kiến trúc thực tế. Đừng dùng id tường minh như một cách làm mọi package-info.java dài hơn mà không tăng giá trị.

## 12. Chọn identifier ổn định

Identifier nên biểu diễn capability/module identity thay vì implementation detail.

Khuyến nghị:

- Dùng một token ngắn, dễ đọc và nhất quán.
- Ưu tiên tên nghiệp vụ ổn định như **inventory**, **orders**, **catalog**.
- Tránh tên gắn với framework như **jpa**, **spring-data**, **hibernate**.
- Tránh tên gắn với đội hoặc cá nhân như **team-a-stock**.
- Không dùng display name có dấu cách làm dependency key.
- Tránh đổi identifier chỉ vì muốn thay cách viết tiêu đề tài liệu.
- Nếu module có nhiều consumer, xem identifier là một phần của kiến trúc cần review khi đổi.

Identifier không nhất thiết phải trùng tên class chính hoặc tên database schema. Nó định danh application module trong mô hình modular monolith.

## 13. Display name nên diễn đạt capability

Display name nên trả lời module chịu trách nhiệm về điều gì. Tránh dùng tên quá chung hoặc chỉ lặp lại tên kỹ thuật.

| Display name yếu | Display name rõ hơn |
|---|---|
| Common | Shared Reference Data nếu đúng trách nhiệm |
| Module 1 | Order Processing |
| InventoryModule | Inventory Management |
| Data | Product Catalog hoặc capability thực tế |
| Utils | Tên capability mà các thành phần thực sự cung cấp |

Không dùng display name để che giấu module có trách nhiệm quá rộng. Nếu một module chứa nhiều capability độc lập, vấn đề có thể nằm ở ranh giới module chứ không phải cách đặt tên.

## 14. Ví dụ tổng hợp ba module

Giả sử ứng dụng có ba module:

~~~text
com.acme.shop
├── inventory
├── order
└── catalog
~~~

Metadata của inventory:

~~~java
@ApplicationModule(
        id = "inventory",
        displayName = "Inventory Management"
)
package com.acme.shop.inventory;
~~~

Metadata của order:

~~~java
@ApplicationModule(
        id = "order",
        displayName = "Order Processing",
        allowedDependencies = { "inventory", "catalog" }
)
package com.acme.shop.order;
~~~

Metadata của catalog:

~~~java
@ApplicationModule(
        id = "catalog",
        displayName = "Product Catalog"
)
package com.acme.shop.catalog;
~~~

Dependency graph:

~~~mermaid
flowchart LR
    O["order<br/>Order Processing"] --> I["inventory<br/>Inventory Management"]
    O --> C["catalog<br/>Product Catalog"]
~~~

Trong sơ đồ:

- Phần trước hoặc token kỹ thuật là identifier.
- Phần mô tả là display name.
- Mũi tên biểu diễn dependency được khai báo từ consumer **order** tới provider **inventory** và **catalog**.

Đổi display name của inventory không làm thay đổi các mũi tên. Đổi identifier thì các dependency declaration liên quan phải được cập nhật.

## 15. Xác minh identifier bằng module verification

Sau khi cấu hình metadata hoặc đổi identifier, hãy chạy architecture verification trong test:

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

Verification giúp phát hiện dependency không được khai báo, dependency cycle và truy cập package không được expose theo quy tắc module. Nó cũng giúp phát hiện metadata tham chiếu module identifier hoặc Named Interface không phù hợp.

Khi test fail sau khi đổi id:

1. Kiểm tra identifier thực tế của provider.
2. Kiểm tra **allowedDependencies** của consumer.
3. Kiểm tra dependency có dùng cú pháp **module::interface** không.
4. Kiểm tra Named Interface có được khai báo ở package đúng không.
5. Kiểm tra có consumer nào còn dùng identifier cũ không.

Đừng sửa bằng cách mở toàn bộ module nếu nguyên nhân chỉ là dependency declaration còn dùng tên cũ.

## 16. Quy trình đổi display name an toàn

Nếu chỉ muốn đổi tên trình bày:

1. Xác định package và module identifier hiện tại.
2. Thay đổi duy nhất **displayName** trong **package-info.java**.
3. Giữ nguyên **id**, package và Named Interface names.
4. Kiểm tra tài liệu hoặc sơ đồ được sinh ra hiển thị tên mới.
5. Chạy module verification để bảo đảm metadata vẫn hợp lệ.
6. Review các dashboard hoặc tài liệu ngoài hệ thống nếu chúng lưu display name.

Không cần sửa **allowedDependencies** chỉ vì display name đổi. Nếu phải sửa dependency key, hãy kiểm tra xem nhóm có vô tình đổi **id** hoặc tên Named Interface cùng lúc hay không.

## 17. Quy trình đổi identifier an toàn

Đổi identifier có phạm vi ảnh hưởng rộng hơn. Thực hiện theo các bước:

1. **Lập danh sách tham chiếu:** tìm mọi **allowedDependencies**, Named Interface dependency, test và tooling dùng identifier cũ.
2. **Xác nhận identity mới:** bảo đảm token mới duy nhất, ổn định và phản ánh đúng module.
3. **Cập nhật provider:** khai báo **id** mới hoặc điều chỉnh package nếu chủ đích là đổi cả package.
4. **Cập nhật consumer:** thay các dependency reference sang identifier mới.
5. **Cập nhật Named Interface references:** ví dụ **inventory::events** thành **stock::events** nếu module id đổi.
6. **Cập nhật tài liệu:** sửa sơ đồ, báo cáo và hướng dẫn dùng identifier cũ.
7. **Chạy verification:** xác nhận dependency graph và encapsulation hợp lệ.
8. **Review rollout:** nếu metadata được dùng bởi nhiều artifact hoặc công cụ độc lập, xác định cách đồng bộ chúng.

Trong một ứng dụng được build và triển khai đồng bộ, cập nhật provider và consumer trong cùng thay đổi thường đơn giản. Nếu consumer hoặc tooling được phát hành độc lập, identifier có thể là một phần contract cần migration.

## 18. Phân biệt đổi identifier với đổi package

Hai thao tác này có thể đi cùng nhau nhưng không tương đương.

| Thao tác | Tác động chính |
|---|---|
| Đổi display name | Cách tên module được trình bày |
| Đổi identifier tường minh | Metadata và các dependency reference dùng identifier |
| Đổi base package | Java package, imports, module detection và framework scanning |
| Đổi Named Interface name | Các dependency reference dạng **module::interface** |

Ví dụ:

- Giữ package **com.acme.shop.inventory**, đổi id từ **inventory** sang **stock**: package Java không đổi nhưng dependency references đổi.
- Đổi package thành **com.acme.shop.stock**, giữ id **inventory**: package Java đổi nhưng dependency references theo id có thể giữ nguyên.
- Đổi display name thành **Stock Management**: không đổi package, id hoặc Named Interface.

Trước khi review một PR đổi tên, hãy yêu cầu tác giả nêu rõ họ đang đổi giá trị nào trong bốn giá trị này.

## 19. Những lỗi thường gặp

| Lỗi | Hậu quả | Cách xử lý |
|---|---|---|
| Dùng display name trong **allowedDependencies** | Dependency reference không khớp identifier | Dùng module id |
| Nghĩ đổi display name sẽ đổi module identity | Nhầm lẫn giữa label và key | Giữ id riêng và ổn định |
| Đổi id nhưng quên consumer | Dependency metadata tham chiếu tên cũ | Tìm và cập nhật mọi reference |
| Đổi package và nghĩ id tường minh tự sửa imports | Code hoặc framework scanning vẫn lỗi | Xử lý package migration riêng |
| Dùng display name làm key trong tooling | Đổi cách trình bày có thể làm đứt liên kết | Dùng id làm key, display name làm label |
| Đặt id theo tên framework | Identity gắn với implementation detail | Chọn tên capability nghiệp vụ |
| Nhầm Named Interface name với display name | Dependency string sai | Dùng **module-id::interface-name** |
| Mở module để né lỗi identifier | Làm suy yếu encapsulation | Sửa dependency metadata |

## 20. Checklist review metadata module

- [ ] Package gốc của module được xác định đúng.
- [ ] Identifier mặc định hoặc **id** tường minh đã được hiểu rõ.
- [ ] Identifier ngắn, ổn định và không phụ thuộc display name.
- [ ] Display name diễn đạt đúng capability nghiệp vụ.
- [ ] **allowedDependencies** dùng identifier, không dùng display name.
- [ ] Named Interface reference dùng đúng dạng **module-id::interface-name**.
- [ ] Đổi display name không kéo theo thay đổi dependency không cần thiết.
- [ ] Đổi identifier đã cập nhật mọi consumer và tooling liên quan.
- [ ] Package rename được đánh giá như một thay đổi riêng.
- [ ] Application module verification pass sau thay đổi.
- [ ] Tài liệu kiến trúc hiển thị tên mới và giữ liên kết kỹ thuật đúng.

## 21. Kết luận

Module identifier và display name khác nhau về mục đích. Identifier là tên kỹ thuật để Spring Modulith và các consumer tham chiếu application module trong dependency metadata. Display name là nhãn thân thiện giúp người đọc hiểu module chịu trách nhiệm về capability nào. **@ApplicationModule** cho phép cấu hình **id** và **displayName**; nếu không đặt id tường minh, identity thường được suy ra từ tên package của module theo quy ước mặc định.

Hãy dùng identifier ổn định trong **allowedDependencies** và Named Interface references, còn display name dành cho tài liệu và sơ đồ. Đổi display name thường không làm thay đổi dependency graph; đổi identifier đòi hỏi cập nhật các tham chiếu kỹ thuật. Đổi package là một việc khác, ảnh hưởng tới source code và module detection. Phân biệt rõ bốn giá trị này giúp nhóm thay đổi cách trình bày hoặc tổ chức package mà vẫn kiểm soát được module identity và dependency giữa các application module.

## Tài liệu tham khảo

- [Spring Modulith — Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — ApplicationModule API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
