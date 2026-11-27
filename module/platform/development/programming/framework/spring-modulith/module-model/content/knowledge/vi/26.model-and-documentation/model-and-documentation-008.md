# Giữ display name ổn định

Trong Spring Modulith, mỗi application module có một tên logic để nhận diện trong mô hình và có thể có một `displayName` để trình bày cho con người. Tên hiển thị xuất hiện trong tài liệu kiến trúc, module canvas hoặc báo cáo mô hình; nó giúp người đọc hiểu trách nhiệm nghiệp vụ của module mà không cần suy luận từ package Java.

Nếu không khai báo `displayName`, phần trình bày thường dựa trên tên module được phát hiện từ cấu trúc package. Điều này tiện khi package đã ổn định, nhưng nhãn có thể thay đổi khi nhóm đổi tên package hoặc tổ chức lại module. Khai báo `displayName` tường minh giúp giữ nhãn tài liệu ổn định qua các lần refactor kỹ thuật.

`displayName` là nhãn dành cho người đọc. Nó không thay thế module identifier, không thay đổi base package, không mở API và không quyết định dependency. Muốn giữ cả danh tính logic lẫn tên hiển thị ổn định, hãy quản lý `id` và `displayName` như hai metadata riêng biệt.

Trong `SPRING_MODULITH_MODULE_MODEL`, cách đặt tên rõ ràng giúp tài liệu kiến trúc phản ánh trách nhiệm nghiệp vụ lâu dài của module, trong khi cấu trúc package có thể được cải tiến độc lập.

## 1. Phân biệt base package, module identifier và display name

Ba giá trị này có liên quan nhưng phục vụ các mục đích khác nhau:

| Khái niệm | Ví dụ | Vai trò |
|---|---|---|
| Base package | `com.example.shop.inventory` | Namespace Java chứa các kiểu thuộc module |
| Module identifier (`id`) | `inventory` | Định danh logic dùng trong mô hình và metadata dependency |
| Display name | `Inventory Management` | Nhãn dễ đọc dùng trong tài liệu và phần trình bày |

Base package phục vụ Java compiler và quy tắc package. Identifier dùng để nhận diện module, chẳng hạn trong `allowedDependencies = "inventory"`. Display name giúp người đọc hiểu module phụ trách lĩnh vực nào.

Không nên dùng display name thay cho identifier trong cấu hình dependency. Ví dụ, `allowedDependencies` tham chiếu `inventory`, không tham chiếu chuỗi `Inventory Management`.

## 2. Khai báo `displayName` tại package gốc

`@ApplicationModule` được đặt trong `package-info.java` của package gốc application module. Có thể khai báo tên hiển thị tường minh như sau:

```java
@org.springframework.modulith.ApplicationModule(
    displayName = "Inventory Management"
)
package com.example.shop.inventory;
```

File nằm tại:

```text
src/main/java/com/example/shop/inventory/package-info.java
```

Trong ví dụ:

- Module vẫn có base package `com.example.shop.inventory`.
- Identifier vẫn được xác định theo quy tắc nhận diện module hiện tại nếu chưa khai báo `id` tường minh.
- `Inventory Management` là nhãn dùng để trình bày module.

Nếu module đã có `id` riêng, có thể khai báo cả hai:

```java
@org.springframework.modulith.ApplicationModule(
    id = "inventory",
    displayName = "Inventory Management"
)
package com.example.shop.stock;
```

Ở đây package đã chuyển sang `com.example.shop.stock`, nhưng identifier vẫn là `inventory` và display name vẫn là `Inventory Management`. Ví dụ dùng `id` tường minh yêu cầu phiên bản Spring Modulith có hỗ trợ thuộc tính `id`.

## 3. Vì sao nên khai báo display name tường minh?

Tên package thường phục vụ cấu trúc kỹ thuật. Theo thời gian, nhóm có thể đổi package để làm rõ namespace, gom module vào một bounded context hoặc loại bỏ tên cũ. Nếu tài liệu lấy nhãn trực tiếp từ tên module mặc định, việc đổi package có thể khiến tiêu đề trong sơ đồ và báo cáo thay đổi dù trách nhiệm nghiệp vụ không đổi.

Ví dụ ban đầu:

```text
com.example.shop.inventory
```

Nhãn được trình bày có thể dựa trên tên module `inventory`. Sau một đợt refactor, package được đổi thành:

```text
com.example.shop.stock
```

Nếu không khai báo `displayName`, tên trong tài liệu có thể chuyển sang nhãn dựa trên `stock`. Nếu tên nghiệp vụ mà người đọc đã quen vẫn là “Inventory Management”, hãy giữ nhãn đó bằng metadata:

```java
@org.springframework.modulith.ApplicationModule(
    id = "inventory",
    displayName = "Inventory Management"
)
package com.example.shop.stock;
```

Nhờ vậy, tài liệu tiếp tục dùng cùng một nhãn trong khi package Java được tổ chức lại. Đây là sự ổn định ở lớp trình bày; các import và tham chiếu Java vẫn phải được cập nhật theo package mới.

## 4. Display name không phải định danh kỹ thuật

Không dùng `displayName` để biểu diễn các giá trị mà code hoặc metadata dependency cần tham chiếu ổn định.

| Công việc | Metadata nên dùng |
|---|---|
| Import kiểu Java | Fully qualified class name trong base package thực tế |
| Khai báo dependency tới module | Module identifier trong `allowedDependencies` |
| Khai báo dependency tới named interface | `module-id::interface-name` |
| Hiển thị tên module trong tài liệu | `displayName` |
| Phân loại package nội bộ hay API | Package structure, `@NamedInterface` và module type |

Ví dụ:

```java
@org.springframework.modulith.ApplicationModule(
    id = "inventory",
    displayName = "Inventory Management"
)
package com.example.shop.stock;
```

Consumer vẫn tham chiếu identifier:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory"
)
package com.example.shop.order;
```

Không viết `allowedDependencies = "Inventory Management"`. Display name có thể chứa dấu cách, chữ hoa hoặc cách diễn đạt hướng tới người đọc; đó không phải cú pháp identifier dành cho dependency.

## 5. Display name không làm thay đổi module boundary

Thay đổi `displayName` chỉ thay đổi nhãn trình bày được khai báo trong metadata module. Nó không:

- Biến package nội bộ thành API công khai.
- Tạo hoặc xóa application module.
- Thay đổi `allowedDependencies`.
- Thay đổi tên package hoặc Java import.
- Đăng ký, đổi tên hoặc inject Spring bean.
- Phá hoặc tạo dependency cycle.

Ví dụ, module có thể đổi nhãn từ `Inventory` thành `Inventory Management` mà không thay đổi API package hoặc quan hệ `order → inventory`. Ngược lại, chuyển package hoặc thay đổi `id` có thể ảnh hưởng đến nhận diện module và metadata dependency ngay cả khi display name không đổi.

Vì vậy, khi review thay đổi `displayName`, hãy xem đó là thay đổi cách tài liệu gọi module. Nếu cùng một commit còn đổi package, `id`, named interface hoặc whitelist, hãy review các thay đổi đó như những quyết định kiến trúc riêng.

## 6. Chọn một display name phản ánh trách nhiệm nghiệp vụ

Display name tốt giúp người đọc hiểu module làm gì. Nên chọn nhãn ngắn, rõ và bền vững:

- Dùng tên lĩnh vực hoặc capability mà module sở hữu.
- Ưu tiên ngôn ngữ nghiệp vụ quen thuộc với nhóm phát triển.
- Tránh tên phụ thuộc vào một class, framework hoặc công nghệ lưu trữ.
- Tránh đưa tên team, tên người phụ trách hoặc tên sprint vào nhãn.
- Không dùng trạng thái tạm thời như `New`, `Legacy2`, `Temporary` nếu đó không phải khái niệm nghiệp vụ.
- Dùng một quy ước viết hoa và cách diễn đạt thống nhất giữa các module.

Ví dụ:

| Tên kém ổn định | Tên hiển thị rõ trách nhiệm hơn |
|---|---|
| `InventoryJpaModule` | `Inventory Management` |
| `OrderTeamModule` | `Order Management` |
| `PaymentV2` | `Payment Processing` |
| `CustomerNew` | `Customer Management` |
| `StockRepositoryModule` | `Inventory Management` nếu module sở hữu toàn bộ nghiệp vụ tồn kho |

Tên hiển thị không cần lặp lại từ `Module` ở cuối. Nó là nhãn tài liệu, không phải tên class.

## 7. Giữ nhãn ổn định khi package được đổi tên

Hãy xem một lần refactor từ `inventory` sang `stock`. Có ba trường hợp:

| Metadata trước refactor | Metadata sau refactor | Hệ quả |
|---|---|---|
| Không có `id`, không có `displayName` | Package đổi từ `inventory` sang `stock` | Tên module mặc định và nhãn dựa trên tên module có thể thay đổi |
| Có `displayName = "Inventory Management"`, không có `id` | Package đổi sang `stock`, giữ display name | Nhãn tài liệu ổn định; identifier mặc định có thể đổi theo package |
| Có `id = "inventory"` và display name tường minh | Package đổi sang `stock`, giữ cả hai metadata | Identifier và nhãn tài liệu đều ổn định; package Java vẫn thay đổi |

Nếu chỉ quan tâm tiêu đề trong tài liệu, `displayName` tường minh có thể đủ. Nếu consumer hoặc metadata kiến trúc cần giữ cùng identifier, phải quản lý thêm `id` tường minh.

Ví dụ cấu hình trước refactor:

```java
@org.springframework.modulith.ApplicationModule(
    id = "inventory",
    displayName = "Inventory Management"
)
package com.example.shop.inventory;
```

Sau refactor:

```java
@org.springframework.modulith.ApplicationModule(
    id = "inventory",
    displayName = "Inventory Management"
)
package com.example.shop.stock;
```

Giữ nguyên hai metadata nhưng cập nhật package declaration và các import Java theo namespace mới. Nếu không đặt `id`, đừng giả định display name ổn định cũng sẽ giữ nguyên identifier.

## 8. Giữ display name ổn định khi trách nhiệm module thay đổi

Ổn định không có nghĩa là giữ một nhãn cũ bất kể module đã thay đổi trách nhiệm. Khi phạm vi nghiệp vụ thực sự thay đổi, hãy đánh giá lại tên hiển thị.

Ví dụ:

- Module `inventory` ban đầu chỉ quản lý số lượng tồn kho.
- Sau đó module sở hữu cả chính sách đặt trước và phân bổ hàng.
- `Inventory Management` có thể vẫn mô tả đúng phạm vi mới.
- Nếu module chuyển thành một capability rộng hơn như quản lý chuỗi cung ứng, tên cũ có thể không còn chính xác.

Hãy phân biệt hai loại thay đổi:

1. **Refactor kỹ thuật:** package, class hoặc cách tổ chức nội bộ thay đổi nhưng trách nhiệm nghiệp vụ giữ nguyên. Nên giữ display name.
2. **Thay đổi ranh giới nghiệp vụ:** module nhận thêm, bỏ hoặc chuyển giao trách nhiệm. Có thể cần đổi display name để phản ánh phạm vi mới.

Khi đổi nhãn, hãy cập nhật tài liệu sinh tự động và các tài liệu kiến trúc được quản lý thủ công có sử dụng tên cũ. Không đổi `id` chỉ để đồng bộ cách viết display name nếu danh tính logic của module không thay đổi.

## 9. Display name và tài liệu kiến trúc được sinh tự động

Spring Modulith cung cấp `Documenter` để tạo tài liệu từ `ApplicationModules`, ví dụ Application Module Canvas và sơ đồ module. Metadata module giúp phần tài liệu trình bày module theo tên dễ đọc, thay vì chỉ liệt kê package kỹ thuật.

Ví dụ tạo mô hình và sinh module canvas:

```java
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);

new Documenter(modules).writeModuleCanvases();
```

Khi `displayName` được khai báo tường minh, tài liệu có thể sử dụng nhãn đó ở những vị trí trình bày tên module. Nhờ vậy, việc đổi package không nhất thiết làm tiêu đề module trong tài liệu đổi theo.

Sau khi thay đổi display name, hãy sinh lại tài liệu kiến trúc theo quy trình dự án và review các file đầu ra:

- Tiêu đề module có đúng trách nhiệm nghiệp vụ không?
- Cùng một module có đang xuất hiện dưới nhiều nhãn khác nhau không?
- Sơ đồ dependency có giữ đúng các cạnh và module identifier không?
- Các tài liệu được commit có còn chứa tên cũ không?

Display name giúp tài liệu dễ đọc hơn, nhưng không thay thế việc review nội dung và phạm vi của sơ đồ. Nếu module boundary thay đổi, cần đánh giá cả các cạnh dependency và API được công bố.

## 10. Quy ước tên cho cả module

Một dự án nên định nghĩa quy ước rõ ràng để người viết metadata không tùy ý pha trộn package name, identifier và display name.

Ví dụ quy ước:

| Metadata | Quy ước đề xuất | Ví dụ |
|---|---|---|
| Base package | Tên package Java viết thường, theo namespace ứng dụng | `com.example.shop.inventory` |
| Module identifier | Token ngắn, viết thường, ổn định | `inventory` |
| Named interface | Token ngắn thể hiện nhóm hợp đồng | `spi`, `events`, `reporting` |
| Display name | Cụm từ dễ đọc, thể hiện capability nghiệp vụ | `Inventory Management` |

Không nên suy ra display name bằng cách ghép hoặc viết hoa identifier trong mọi trường hợp. Identifier `crm` có thể cần nhãn `Customer Relationship Management`; identifier `stock` có thể cần nhãn `Inventory Management` nếu đó là thuật ngữ người dùng nội bộ quen thuộc.

Đối với module mới, hãy chọn identifier và display name cùng lúc nhưng ghi rõ vai trò của từng giá trị. Đối với module cũ, ưu tiên giữ nhãn đã được dùng ổn định trong tài liệu nếu trách nhiệm nghiệp vụ chưa thay đổi.

## 11. Kiểm tra metadata hiển thị của module

Sau khi khai báo `displayName`, tạo mô hình để quan sát module:

```java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules modules = ApplicationModules.of(ShopApplication.class);
modules.forEach(System.out::println);
```

Kết quả trình bày mô hình giúp kiểm tra logical name, base package và các Spring bean được nhận diện. Khi cần xác nhận nhãn được dùng trong tài liệu, hãy sinh module canvas hoặc tài liệu tương ứng bằng `Documenter` và kiểm tra đầu ra.

`ApplicationModules.verify()` vẫn là kiểm tra kiến trúc:

```java
import org.springframework.modulith.core.ApplicationModules;

ApplicationModules.of(ShopApplication.class).verify();
```

`verify()` kiểm tra dependency cycle, encapsulation và các quy tắc dependency đã khai báo. Nó không phải một bài kiểm tra chính tả hoặc chất lượng ngôn ngữ của `displayName`. Việc chọn nhãn đúng vẫn cần review của nhóm.

## 12. Những thay đổi nào cần review khi đổi tên hiển thị?

Khi thay đổi `displayName`, hãy kiểm tra những phần phụ thuộc vào cách trình bày:

- Module canvas và sơ đồ kiến trúc được sinh lại.
- Tài liệu onboarding hoặc tài liệu thiết kế dùng nhãn cũ.
- Báo cáo nội bộ hoặc trang tài liệu tham chiếu display name.
- Quy ước tên của các module cùng cấp để bảo đảm nhất quán.

Nếu thay đổi đồng thời package hoặc identifier, cần review thêm:

- Package declaration và import Java.
- `allowedDependencies` ở các consumer nếu identifier thay đổi.
- Named interface dependency dạng `module::interface`.
- Các cấu hình hoặc công cụ nội bộ tham chiếu module identifier.
- Detection strategy và các bài kiểm tra kiến trúc sau refactor.

Đừng dùng một thay đổi display name để che giấu một lần đổi module identity. Hãy ghi rõ metadata nào thay đổi và lý do.

## 13. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `displayName` là module identifier | Identifier dùng nhận diện module; display name dùng trình bày. |
| Đổi display name làm thay đổi `allowedDependencies` | Dependency tham chiếu identifier, không tham chiếu display name. |
| Khai báo display name giữ nguyên package | Package Java vẫn thay đổi khi refactor; display name chỉ giữ nhãn tài liệu. |
| Giữ display name đồng nghĩa giữ module ID | Cần khai báo `id` riêng nếu muốn identifier ổn định qua package rename. |
| Display name quyết định package nào được expose | API exposure dựa trên package structure, Named Interface và module type. |
| `@Service` hoặc bean name được đổi theo display name | Display name của module không phải tên Spring bean. |
| Nên đưa tên team vào display name | Tên team có thể thay đổi; nhãn nên phản ánh trách nhiệm nghiệp vụ. |
| Nên giữ display name cũ dù module đổi trách nhiệm | Nếu ranh giới nghiệp vụ thay đổi thực sự, hãy đánh giá và cập nhật nhãn cho đúng. |
| `verify()` xác nhận display name phù hợp | `verify()` kiểm tra quy tắc kiến trúc, không đánh giá chất lượng tên hiển thị. |

## 14. Quy trình giữ display name ổn định

Khi tạo module hoặc refactor package, thực hiện theo trình tự:

1. **Xác định trách nhiệm nghiệp vụ.** Viết ngắn gọn module sở hữu capability nào.
2. **Chọn display name.** Dùng cụm từ dễ đọc, không phụ thuộc package hoặc công nghệ.
3. **Khai báo tường minh.** Đặt `displayName` trong `@ApplicationModule` ở `package-info.java` của package gốc.
4. **Xác định nhu cầu giữ identifier.** Nếu consumer cần giữ cùng tên logic sau package rename, khai báo `id` tường minh trên phiên bản hỗ trợ.
5. **Tách metadata khỏi package.** Không dùng display name làm tên package hoặc giá trị dependency.
6. **Refactor package nếu cần.** Cập nhật namespace Java, import và cấu hình liên quan.
7. **Sinh lại tài liệu.** Kiểm tra module canvas và sơ đồ có hiển thị đúng nhãn.
8. **Review dependency.** Nếu `id` thay đổi, cập nhật các consumer tham chiếu identifier hoặc named interface.
9. **Chạy kiểm tra kiến trúc.** Dùng `ApplicationModules.verify()` để xác nhận dependency và encapsulation.
10. **Review ngôn ngữ.** Bảo đảm display name nhất quán với thuật ngữ của các module khác.

## 15. Checklist cho display name ổn định

- [ ] Display name mô tả trách nhiệm nghiệp vụ của module.
- [ ] `displayName` được khai báo tường minh nếu cần giữ nhãn qua package refactor.
- [ ] Display name không bị dùng nhầm làm module identifier.
- [ ] `id` được quản lý riêng nếu cần giữ danh tính logic.
- [ ] Tên không phụ thuộc team, người phụ trách, sprint hoặc công nghệ triển khai.
- [ ] Cách viết hoa và thuật ngữ nhất quán với các module cùng cấp.
- [ ] Package declaration và import được cập nhật độc lập khi refactor.
- [ ] `allowedDependencies` dùng identifier, không dùng display name.
- [ ] Named interface vẫn được tham chiếu bằng `module-id::interface-name`.
- [ ] Tài liệu sinh tự động được tạo lại và review sau thay đổi.
- [ ] `ApplicationModules.verify()` được chạy khi có thay đổi module metadata hoặc dependency.
- [ ] Nhãn được cập nhật khi trách nhiệm nghiệp vụ thay đổi thực sự.

## 16. Kết luận

`displayName` của `@ApplicationModule` là nhãn dành cho con người, giúp tài liệu và sơ đồ kiến trúc trình bày module theo trách nhiệm nghiệp vụ. Khai báo tường minh `displayName` giúp giữ nhãn ổn định khi package Java được đổi tên hoặc tổ chức lại. Tuy nhiên, display name không phải module identifier và không ảnh hưởng đến package, API exposure hay dependency rules.

Khi cần giữ danh tính logic qua refactor, hãy quản lý `id` riêng bên cạnh `displayName`. Consumer tiếp tục tham chiếu identifier trong `allowedDependencies`, còn tài liệu dùng display name để hiển thị. Chọn tên theo capability nghiệp vụ, sinh lại tài liệu sau thay đổi và review nhãn cùng sơ đồ để bảo đảm người đọc vẫn nhận ra đúng trách nhiệm của module.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html)
- [Spring Modulith — `@ApplicationModule` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith — `ApplicationModules` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
