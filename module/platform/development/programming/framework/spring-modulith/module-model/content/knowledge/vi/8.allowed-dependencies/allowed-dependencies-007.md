# Phát hiện dependency ngoài danh sách cho phép

Khi một application module có `allowedDependencies`, danh sách đó trở thành giới hạn kiến trúc cho các dependency trực tiếp mà module được phép tạo ra. Nếu code bắt đầu sử dụng một module khác mà không có trong danh sách, Spring Modulith có thể phát hiện vi phạm khi kiểm tra cấu trúc.

Điều này giúp nhóm nhận ra một thay đổi đã mở rộng phạm vi phụ thuộc: một bean mới được inject, một type từ module khác được import hoặc một event listener mới được đăng ký. Khi test kiến trúc thất bại, việc cần làm là xác định dependency nào xuất hiện, vì sao nó xuất hiện và hợp đồng nào thực sự cần được dùng. Chỉ sau khi hiểu nguyên nhân mới quyết định sửa code hay cập nhật allowlist.

## 1. Khi nào dependency bị xem là ngoài danh sách?

Giả sử ứng dụng có các application module `order`, `inventory`, `customer` và `shipping`. Module `order` được cấu hình chỉ phụ thuộc vào `customer`:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "customer"
)
package com.acme.shop.order;
```

Trong khi đó, một service của `order` lại inject API của `inventory`:

```java
package com.acme.shop.order.internal;

import com.acme.shop.inventory.InventoryManagement;
import org.springframework.stereotype.Service;

@Service
class OrderService {

    private final InventoryManagement inventory;

    OrderService(InventoryManagement inventory) {
        this.inventory = inventory;
    }
}
```

Code tạo ra dependency trực tiếp `order -> inventory`, nhưng allowlist của `order` chỉ có `customer`. Đây là dependency ngoài danh sách cho phép.

Điểm quan trọng là dependency được suy ra từ code. `allowedDependencies` không tạo dependency và cũng không tự động inject bean. Nó chỉ quy định module hiện tại được phép phụ thuộc vào module hoặc Named Interface nào.

## 2. `ApplicationModules.verify()` phát hiện vi phạm như thế nào?

Tạo mô hình module từ lớp Spring Boot application rồi gọi `verify()`:

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

Spring Modulith phân tích cấu trúc package và các quan hệ dependency mà nó nhận diện, sau đó kiểm tra những quy tắc kiến trúc đã cấu hình. Trong đó có ba nhóm kiểm tra chính:

1. **Không có chu trình ở cấp application module:** đồ thị dependency giữa các module phải là directed acyclic graph.
2. **Chỉ truy cập API được công bố:** module khác không được tham chiếu type trong package nội bộ của một module đóng.
3. **Chỉ dùng dependency được cho phép:** nếu module khai báo `allowedDependencies`, các dependency đến application module khác phải khớp với danh sách đó.

Nếu phát hiện vi phạm, `verify()` ném exception và bài test thất bại. Vì vậy, một dependency ngoài allowlist có thể được phát hiện ngay trong test suite hoặc pipeline CI.

`verify()` kiểm tra cấu trúc kiến trúc trên code đã biên dịch. Nó không chặn Java compiler biên dịch import và cũng không phải cơ chế bảo mật runtime. Nếu nhóm không chạy bài test này, annotation vẫn nằm trong source nhưng vi phạm có thể không được phát hiện trong quy trình build.

## 3. Đọc diagnostic để tìm đúng dependency vi phạm

Khi test thất bại, hãy đọc thông tin vi phạm theo các câu hỏi sau:

| Cần xác định | Câu hỏi cần trả lời |
| --- | --- |
| Module nguồn | Module nào đang tạo dependency? |
| Module đích | Dependency đang đi đến module nào? |
| Type hoặc package liên quan | Code đang import type nào, inject bean nào hoặc lắng nghe event nào? |
| Hợp đồng được phép | `allowedDependencies` hiện tại khai báo module hoặc Named Interface nào? |
| Loại vấn đề | Chỉ thiếu allowlist, truy cập package nội bộ hay còn có chu trình dependency? |

Ví dụ diagnostic có thể được hiểu theo dạng khái niệm như sau:

```text
Module: order
Dependency target: inventory
Referenced API: InventoryManagement
Allowed targets: customer
Result: dependency to inventory is not allowed
```

Đây là ví dụ minh họa cách đọc thông tin, không phải chuỗi thông báo cố định của framework. Nội dung diagnostic thực tế phụ thuộc vào module, type và phiên bản Spring Modulith.

Nếu test báo `order` phụ thuộc `inventory`, hãy tìm nơi `order` tham chiếu type của `inventory`, constructor injection, method parameter/return type hoặc event listener nhận event do `inventory` công bố. Sau đó đối chiếu package chứa type đó với API package hoặc Named Interface của `inventory`.

Đừng dừng ở việc tìm dòng import đầu tiên. Một dependency có thể được tạo ra gián tiếp từ chữ ký của một bean, một type được dùng trong API hoặc một listener được khai báo ở nơi khác trong module.

## 4. Phân biệt ba loại vi phạm thường gặp

Không phải mọi lỗi dependency đều được sửa bằng cách thêm module vào `allowedDependencies`.

| Diagnostic phản ánh | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Dependency đến module không có trong allowlist | Module nguồn sử dụng một module chưa được cho phép | Xem lại nhu cầu; loại bỏ dependency hoặc bổ sung module/API phù hợp nếu quan hệ đó có chủ đích |
| Truy cập type trong package nội bộ | Module nguồn import chi tiết triển khai của module đích | Dùng API package gốc hoặc công bố Named Interface hẹp; không chỉ thêm tên module vào allowlist |
| Chu trình dependency giữa module | Các module phụ thuộc ngược tạo thành một vòng | Tái cấu trúc hướng phụ thuộc, tách hợp đồng hoặc dùng event khi phù hợp; mở rộng allowlist không giải quyết chu trình |

Ví dụ, nếu `order` được phép phụ thuộc vào `inventory` nhưng import `inventory.internal.StockRepository`, dependency đến module `inventory` có thể đã nằm trong allowlist, song việc truy cập package nội bộ vẫn vi phạm quy tắc API boundary. Hai quy tắc được kiểm tra độc lập.

Ngược lại, nếu `order` import `inventory.InventoryManagement` ở package API nhưng `inventory` không nằm trong allowlist, lỗi nằm ở danh sách dependency được phép. Khi đó, nhóm cần quyết định quan hệ `order -> inventory` có thật sự là một phần thiết kế hay không.

## 5. Kiểm tra cú pháp Named Interface trong allowlist

Một module có thể công bố package con bằng `@NamedInterface`. Ví dụ, module `inventory` công bố giao diện `api`:

```java
@org.springframework.modulith.NamedInterface("api")
package com.acme.shop.inventory.api;
```

Nếu `order` chỉ cần các type trong package này, allowlist có thể chỉ định đúng Named Interface:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory :: api"
)
package com.acme.shop.order;
```

Nếu code của `order` tham chiếu `inventory.InventoryManagement` ở package gốc, dependency đó không khớp với `inventory :: api`. Khi cần cả API package gốc và Named Interface `api`, hãy khai báo cả hai:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "inventory",
        "inventory :: api"
    }
)
package com.acme.shop.order;
```

Không nên mở rộng quyền đến mọi package chỉ vì một type chưa được đặt trong đúng Named Interface. Hãy xác định hợp đồng nào thực sự được module nguồn sử dụng rồi chọn phạm vi công bố tương ứng.

## 6. Hiểu `*`, `**` và danh sách rỗng

Spring Modulith hỗ trợ cú pháp wildcard để kiểm soát Named Interface. Hai wildcard có phạm vi khác nhau:

| Khai báo | Phạm vi được phép |
| --- | --- |
| `inventory :: api` | Chỉ Named Interface `api` của module `inventory` |
| `inventory :: *` | Tất cả Named Interface được khai báo của `inventory`, không bao gồm package gốc |
| `inventory :: **` | Package gốc và tất cả Named Interface được khai báo của `inventory` |

Ví dụ, `inventory :: *` không cho phép `order` tham chiếu `InventoryManagement` ở package gốc. Nếu muốn cho phép cả API mặc định lẫn mọi Named Interface, dùng `inventory :: **`.

Có một khác biệt quan trọng giữa không khai báo thuộc tính và khai báo mảng rỗng:

```java
// Không đặt allowlist tường minh: không giới hạn dependency bằng thuộc tính này.
@org.springframework.modulith.ApplicationModule
package com.acme.shop.reporting;
```

```java
// Allowlist rỗng tường minh: không cho phép dependency đến application module khác.
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {}
)
package com.acme.shop.reporting;
```

Mặc định của thuộc tính là một giá trị sentinel để phân biệt trạng thái chưa cấu hình. Vì vậy, `allowedDependencies = {}` có nghĩa là không cho phép dependency đến application module khác; bỏ thuộc tính hoàn toàn có nghĩa là không đặt giới hạn allowlist tường minh. Allowlist này áp dụng cho các application module trong mô hình; code không được gán vào application module, chẳng hạn một số thư viện dùng chung, không phải target module cần liệt kê ở đây. Các quy tắc kiến trúc khác như package nội bộ và dependency cycle vẫn được kiểm tra.

## 7. Dependency không được phép không tự biến mất khi đi qua module trung gian

Giả sử đồ thị hiện tại là:

```text
order -> inventory -> catalog
```

Nếu code trong `order` trực tiếp tham chiếu type của `catalog`, dependency trực tiếp `order -> catalog` vẫn cần được đánh giá. Việc `inventory` đã phụ thuộc vào `catalog` không tự động cấp quyền cho `order` sử dụng API đó.

Điều này giúp dependency graph phản ánh chính xác module nào thực sự dùng hợp đồng của module nào. Nếu `order` cần dữ liệu từ `catalog`, hãy cân nhắc gọi API của module sở hữu dữ liệu hoặc để `inventory` cung cấp một hợp đồng phù hợp với trách nhiệm của nó.

## 8. Xử lý vi phạm theo đúng nguyên nhân

Khi phát hiện dependency ngoài allowlist, có bốn hướng xử lý thường gặp:

1. **Loại bỏ dependency không cần thiết:** xóa lời gọi hoặc type tham chiếu nếu code đang phụ thuộc vào module khác mà không có lý do nghiệp vụ.
2. **Dùng hợp đồng đúng của module sở hữu:** thay import đến repository hoặc service nội bộ bằng API package gốc hoặc Named Interface đã công bố.
3. **Công bố Named Interface có chủ đích:** nếu một package con thực sự là hợp đồng tích hợp, đánh dấu nó bằng `@NamedInterface` và cho phép đúng interface đó.
4. **Cập nhật allowlist:** nếu dependency trực tiếp là hợp lý, ổn định và đã được thống nhất trong thiết kế, thêm module hoặc Named Interface tương ứng vào `allowedDependencies`.

Ví dụ, nếu `order` cần gọi API kiểm tra tồn kho của `inventory`, có thể cập nhật:

```java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = {
        "customer",
        "inventory"
    }
)
package com.acme.shop.order;
```

Nếu `order` chỉ cần event từ `inventory`, một allowlist hẹp như `inventory :: events` có thể phù hợp hơn. Lựa chọn phụ thuộc vào hợp đồng mà code thực sự sử dụng.

Đừng thêm module vào allowlist chỉ để làm test xanh. Nếu quan hệ không hợp lý, hãy sửa code để dependency graph phản ánh đúng ownership và luồng nghiệp vụ. Nếu quan hệ hợp lý, hãy cập nhật allowlist cùng với thay đổi code để hợp đồng kiến trúc được review như một phần của thay đổi đó.

## 9. Thu thập và xử lý violations có chủ đích

Trong test thông thường, `verify()` là cách ngắn gọn để làm build thất bại khi có vi phạm:

```java
ApplicationModules.of(ShopApplication.class).verify();
```

Nếu cần xem hoặc xử lý tập violations trước khi quyết định ném exception, API `detectViolations()` trả về đối tượng `Violations`:

```java
var violations = ApplicationModules.of(ShopApplication.class)
        .detectViolations();

violations.throwIfPresent();
```

`detectViolations()` thực thi các kiểm tra và trả về tập vi phạm để có thể xử lý tiếp. API này hữu ích khi cần áp dụng chính sách xử lý có chủ đích; không nên bỏ qua vi phạm chỉ để làm pipeline thành công. `verify()` có thể được dùng trong test kiến trúc thông thường, còn `detectViolations()` phù hợp khi cần truy cập và xử lý kết quả chi tiết hơn.

## 10. Đưa phát hiện dependency ngoài allowlist vào CI

Một test kiến trúc nên chạy cùng các test tự động khác:

```java
package com.acme.shop;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ArchitectureTests {

    @Test
    void applicationModulesRespectTheirContracts() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
```

Khi một pull request thêm dependency mới, CI chạy test và báo lỗi nếu dependency vi phạm allowlist hoặc các quy tắc module khác. Người review có thể xem cùng lúc thay đổi code và thay đổi `package-info.java` để đánh giá dependency mới có hợp lý không.

Quy trình này giúp phát hiện sớm các thay đổi làm rộng dependency graph. Nó cũng tạo một tiêu chuẩn chung để nhóm thảo luận về việc module nào sở hữu API và module nào được phép sử dụng API đó.

## 11. Những nhầm lẫn thường gặp

| Nhận định | Cách hiểu chính xác |
| --- | --- |
| Test thất bại vì thiếu module trong allowlist thì cứ thêm module đó. | Trước tiên phải xác định dependency có hợp lý và đang dùng đúng API hay không. |
| Cho phép một module là cho phép mọi package của nó. | Package nội bộ vẫn bị đóng; allowlist và API visibility là hai quy tắc riêng. |
| `module :: *` cho phép cả package gốc. | `*` chỉ bao gồm các Named Interface; `**` mới bao gồm package gốc và tất cả Named Interface. |
| `allowedDependencies = {}` giống như bỏ thuộc tính. | Mảng rỗng tường minh cấm dependency đến application module khác; bỏ thuộc tính dùng giá trị mặc định không giới hạn bằng allowlist. |
| Dependency bắc cầu được kế thừa. | Module phải được cho phép dependency trực tiếp mà code của nó thực sự sử dụng. |
| `verify()` chỉ kiểm tra `allowedDependencies`. | Nó còn kiểm tra chu trình module và việc truy cập package nội bộ; tùy classpath có thể có các kiểm tra bổ sung. |
| `verify()` ngăn compiler hoặc runtime truy cập sai. | Nó là kiểm tra kiến trúc cần được chạy trong test/CI. |

## 12. Ghi nhớ

Dependency ngoài allowlist xuất hiện khi code của một application module phụ thuộc trực tiếp vào module hoặc Named Interface không được liệt kê trong `allowedDependencies`. `ApplicationModules.verify()` phát hiện vi phạm và làm bài test thất bại. Kết quả cần được đọc cùng module nguồn, module đích và type/package liên quan để xác định nguyên nhân.

Hãy phân biệt dependency ngoài danh sách với truy cập package nội bộ và chu trình dependency; mỗi loại cần cách xử lý riêng. Dùng tên module cho API package mặc định, `module :: interface` cho Named Interface cụ thể, `*` cho mọi Named Interface và `**` cho toàn bộ phần API được công bố. Nhớ rằng mảng rỗng tường minh cấm dependency module, còn bỏ thuộc tính là không đặt allowlist tường minh. Cuối cùng, chạy `ApplicationModules.verify()` trong CI để giữ hợp đồng kiến trúc qua từng thay đổi.

## Tài liệu tham khảo

- [Spring Modulith Reference — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith Reference — Fundamentals and Explicit Application Module Dependencies](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith API — `ApplicationModule`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [Spring Modulith API — `ApplicationModules`](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
