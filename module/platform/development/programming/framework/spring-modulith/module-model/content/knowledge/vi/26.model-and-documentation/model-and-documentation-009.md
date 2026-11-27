# Đối chiếu tài liệu với package tree

Trong Spring Modulith, package tree là cấu trúc mã nguồn thực tế mà framework dùng để nhận diện application module. Tài liệu kiến trúc như Application Module Canvas hoặc sơ đồ dependency diễn giải cấu trúc đó cho người đọc. Khi package được di chuyển, module được tách, API thay đổi hoặc dependency mới xuất hiện, tài liệu có thể không còn phản ánh đúng codebase nếu nhóm không tạo lại và đối chiếu.

Đối chiếu tài liệu với package tree giúp trả lời ba câu hỏi: module nào đang tồn tại, mỗi module sở hữu những package nào và các module đang phụ thuộc nhau qua hợp đồng nào. Spring Modulith có thể xây dựng mô hình từ lớp ứng dụng, kiểm tra ranh giới và sinh tài liệu từ mô hình đó. Nhóm nên dùng kết quả này để phát hiện tài liệu thủ công đã lỗi thời và sửa lại phần mô tả cần thiết.

## 1. Package tree và tài liệu kiến trúc thể hiện điều gì?

Package tree cho thấy vị trí package và class trong source code. Ví dụ:

~~~text
com.acme.shop
├── ShopApplication.java
├── order
│   ├── OrderManagement.java
│   ├── OrderCompleted.java
│   ├── internal
│   │   └── CompleteOrderService.java
│   └── web
│       └── OrderController.java
├── inventory
│   ├── InventoryManagement.java
│   ├── internal
│   │   └── InventoryManagementImpl.java
│   └── persistence
│       └── JpaStockRepository.java
└── shipping
    ├── ShippingManagement.java
    └── internal
        └── OrderCompletedListener.java
~~~

Tài liệu kiến trúc diễn giải các package đó theo góc nhìn module:

~~~text
Dependency graph:
shipping ─────> order ─────> inventory

Event flow:
order ── OrderCompleted ──> shipping
~~~

Hai biểu diễn có mục đích khác nhau:

| Package tree | Tài liệu module |
| --- | --- |
| Hiển thị package và class nằm ở đâu | Hiển thị ranh giới và trách nhiệm của module |
| Cho thấy package con như `internal`, `web`, `persistence` | Cho thấy phần nào là API mặc định, named interface hoặc nội bộ |
| Là cấu trúc source code hiện tại | Là cách diễn giải module và dependency từ mô hình |
| Thay đổi khi file hoặc package được di chuyển | Cần được tạo lại hoặc cập nhật khi mô hình thay đổi |

Package tree là bằng chứng về vị trí mã nguồn. Tài liệu là cách giải thích cấu trúc đó. Nếu tài liệu nói `shipping` không phụ thuộc `order` nhưng listener trong package `shipping` import `OrderCompleted` của `order`, hai biểu diễn đang mâu thuẫn và cần được xem xét.

## 2. Xác định đúng package gốc của ứng dụng

Spring Modulith cần một lớp ứng dụng hoặc package gốc để xây dựng mô hình module. Với Spring Boot, thường dùng lớp có `@SpringBootApplication`:

~~~java
package com.acme.shop;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

Theo quy ước phát hiện module mặc định, các package con trực tiếp của package ứng dụng có thể được nhận diện là application module. Với ví dụ trên, `com.acme.shop.order`, `com.acme.shop.inventory` và `com.acme.shop.shipping` là các module dự kiến.

Khi đối chiếu, hãy xác nhận:

- Lớp ứng dụng đang nằm tại package gốc mà tài liệu mô tả.
- Các module trong tài liệu tương ứng với package module thực tế.
- Package bổ sung được khai báo qua `@Modulithic(additionalPackages = ...)`, nếu có, cũng xuất hiện trong phạm vi tài liệu.
- Không nhầm package kỹ thuật như `config`, `common` hoặc `bootstrap` với module nghiệp vụ nếu chúng không được chủ ý mô hình hóa như module.

Nếu lớp ứng dụng chuyển package hoặc phạm vi phát hiện module thay đổi, hãy tạo lại mô hình và tài liệu trước khi kết luận rằng package tree và diagram không khớp.

## 3. Đối chiếu từng module với base package

Với mỗi module được hiển thị trong tài liệu, tìm package gốc tương ứng trong source tree. Ví dụ, module `inventory` có base package `com.acme.shop.inventory`:

~~~text
com.acme.shop.inventory
├── InventoryManagement.java
├── internal
│   └── InventoryManagementImpl.java
└── persistence
    └── JpaStockRepository.java
~~~

Package gốc là nơi công bố API mặc định. Những package con như `internal` và `persistence` thuộc phần triển khai nội bộ theo quy ước đóng gói mặc định.

Khi xem Application Module Canvas, hãy kiểm tra tên module, package gốc, các kiểu API được công bố và những dependency được mô tả có khớp với cấu trúc hiện tại hay không.

| Nội dung cần đối chiếu | Dấu hiệu trong source tree | Câu hỏi cho tài liệu |
| --- | --- | --- |
| Module name | Package gốc `inventory` | Tài liệu có gọi đúng module không? |
| Public API | Kiểu public ở base package | Canvas có mô tả đúng hợp đồng được công bố không? |
| Internal packages | `inventory.internal`, `inventory.persistence` | Tài liệu có vô tình mô tả chi tiết nội bộ như API không? |
| Module responsibility | Các use case và kiểu nghiệp vụ trong module | Mô tả trách nhiệm có còn đúng sau refactor không? |
| Dependencies | Import và kiểu được tham chiếu từ module khác | Các cạnh trên diagram có khớp dependency thực tế không? |

Không nên chỉ so sánh tên folder. Hãy xem package declaration trong Java source vì package declaration mới là định danh package của class. Cấu trúc thư mục thông thường phản ánh package, nhưng một số build layout hoặc source set tùy chỉnh có thể làm đường dẫn vật lý khác với package name.

## 4. Kiểm tra API mặc định và package nội bộ

Tài liệu module cần phân biệt API mà module cam kết cung cấp với chi tiết triển khai. Ví dụ:

~~~java
package com.acme.shop.inventory;

public interface InventoryManagement {

    boolean reserve(String sku, int quantity);
}
~~~

Implementation nằm trong package con:

~~~java
package com.acme.shop.inventory.internal;

import com.acme.shop.inventory.InventoryManagement;
import org.springframework.stereotype.Service;

@Service
class InventoryManagementImpl implements InventoryManagement {

    @Override
    public boolean reserve(String sku, int quantity) {
        // Kiểm tra và giữ hàng.
        return true;
    }
}
~~~

Khi đối chiếu tài liệu:

- `InventoryManagement` có thể được ghi nhận là API mặc định của `inventory`.
- `InventoryManagementImpl` là implementation nội bộ.
- `JpaStockRepository` không nên xuất hiện như hợp đồng mà module khác được phép gọi.
- Nếu tài liệu liệt kê implementation nội bộ trong danh sách public API, cần sửa cách diễn giải.

Java modifier `public` và API visibility của Spring Modulith không đồng nghĩa. Một class `public` trong package con vẫn có thể là chi tiết nội bộ theo mô hình module.

## 5. Đối chiếu Named Interface với package tree

Một module có thể công bố thêm package con bằng `@NamedInterface`. Ví dụ:

~~~text
com.acme.shop.inventory
├── InventoryManagement.java
├── internal
│   └── InventoryManagementImpl.java
└── events
    ├── package-info.java
    └── StockReserved.java
~~~

File `events/package-info.java`:

~~~java
@org.springframework.modulith.NamedInterface("events")
package com.acme.shop.inventory.events;
~~~

Trong tài liệu, `inventory::events` là named interface của module `inventory`. Khi đối chiếu, hãy xác nhận:

1. Package được ghi trong `package-info.java` đúng với package path hiện tại.
2. Annotation `@NamedInterface` vẫn còn và dùng đúng tên.
3. Các kiểu được mô tả trong named interface thực sự nằm trong package được công bố.
4. Module tiêu thụ tham chiếu đúng tên interface trong `allowedDependencies`.

Ví dụ, module `shipping` có thể khai báo:

~~~java
@org.springframework.modulith.ApplicationModule(
    allowedDependencies = "inventory::events"
)
package com.acme.shop.shipping;
~~~

Nếu tài liệu ghi `inventory::events` nhưng package `com.acme.shop.inventory.integration` đã đổi annotation từ `@NamedInterface("events")` thành `@NamedInterface("integration")`, diagram và source metadata không còn khớp. Cần xác định đó là thay đổi chủ ý của hợp đồng hay một cập nhật bị bỏ sót.

## 6. So sánh dependency trong tài liệu với import và event listener

Dependency giữa hai module có thể được tạo ra bởi lời gọi API trực tiếp, constructor injection, kiểu được tham chiếu hoặc event listener. Khi kiểm tra diagram, hãy lần theo mã nguồn của module tiêu thụ để xác nhận mỗi cạnh.

Ví dụ module `order` sử dụng API của `inventory`:

~~~java
package com.acme.shop.order.internal;

import com.acme.shop.inventory.InventoryManagement;
import org.springframework.stereotype.Service;

@Service
class PlaceOrderService {

    private final InventoryManagement inventory;

    PlaceOrderService(InventoryManagement inventory) {
        this.inventory = inventory;
    }
}
~~~

Dependency graph phải thể hiện `order` phụ thuộc `inventory`.

Với event listener:

~~~java
package com.acme.shop.shipping.internal;

import com.acme.shop.order.OrderCompleted;
import org.springframework.modulith.events.ApplicationModuleListener;
import org.springframework.stereotype.Component;

@Component
class OrderCompletedListener {

    @ApplicationModuleListener
    void on(OrderCompleted event) {
        // Tạo yêu cầu giao hàng.
    }
}
~~~

`shipping` cần event type `OrderCompleted`, do đó module phụ thuộc vào `order`. Event flow chạy từ publisher `order` đến subscriber `shipping`, còn chiều dependency hướng từ subscriber đến module sở hữu event contract.

Hãy rà soát cả hai chiều biểu diễn để không đọc nhầm mũi tên. Một sơ đồ có thể minh họa event flow, trong khi một dependency diagram lại thể hiện chiều phụ thuộc ngược lại.

## 7. Tạo lại tài liệu từ mô hình Spring Modulith

Spring Modulith cung cấp `Documenter` để tạo tài liệu từ `ApplicationModules`. Ví dụ tạo Application Module Canvas:

~~~java
import org.springframework.modulith.core.ApplicationModules;
import org.springframework.modulith.docs.Documenter;

class ModuleDocumentation {

    void generate() {
        ApplicationModules modules =
                ApplicationModules.of(ShopApplication.class);

        new Documenter(modules).writeModuleCanvases();
    }
}
~~~

Mô hình được tạo từ `ShopApplication.class`, vì vậy tài liệu phản ánh package và metadata mà Spring Modulith nhận diện tại thời điểm chạy bước sinh tài liệu.

Sau khi đổi package, thêm module, công bố named interface hoặc thay dependency, hãy chạy lại bước tạo tài liệu. Đừng tiếp tục sử dụng canvas cũ như bằng chứng cho cấu trúc mới.

Có thể kết hợp sinh tài liệu với kiểm tra kiến trúc:

~~~java
ApplicationModules modules =
        ApplicationModules.of(ShopApplication.class);

modules.verify();
new Documenter(modules).writeModuleCanvases();
~~~

`verify()` kiểm tra các quy tắc kiến trúc. `Documenter` tạo tài liệu để người đọc xem mô hình. Sinh tài liệu thành công không thay thế verification, và verification thành công cũng không bảo đảm mô tả nghiệp vụ trong canvas đã được viết đúng về mặt ngữ nghĩa.

## 8. Dùng bảng đối chiếu để tìm sai lệch

Khi review một module, có thể lập bảng ngắn theo các trường sau:

| Hạng mục | Package tree thực tế | Tài liệu hiện tại | Kết quả |
| --- | --- | --- | --- |
| Module name | `inventory` | `inventory` | Khớp |
| Base package | `com.acme.shop.inventory` | `com.acme.shop.inventory` | Khớp |
| Public API | `InventoryManagement` | `InventoryManagement` | Khớp |
| Named interface | `inventory::events` | `inventory::events` | Khớp |
| Internal packages | `internal`, `persistence` | `internal`, `persistence` | Khớp |
| Dependency | `order -> inventory` | `order -> inventory` | Khớp |

Nếu kết quả không khớp, ghi rõ loại sai lệch:

- **Sai lệch package:** tài liệu nhắc package đã được đổi tên hoặc di chuyển.
- **Sai lệch module:** package tree có module mới nhưng tài liệu chưa cập nhật.
- **Sai lệch API:** tài liệu công bố một kiểu đã chuyển vào package nội bộ hoặc không còn tồn tại.
- **Sai lệch named interface:** tên hoặc package được công bố đã thay đổi.
- **Sai lệch dependency:** source có cạnh mới nhưng diagram không thể hiện, hoặc diagram giữ cạnh đã bị loại bỏ.
- **Sai lệch trách nhiệm:** package vẫn đúng nhưng chức năng nghiệp vụ của module đã thay đổi.

Không nên tự động sửa tài liệu theo mọi khác biệt. Trước tiên xác định source code hay tài liệu đang phản ánh quyết định kiến trúc mới nhất. Nếu package tree đã thay đổi có chủ ý, cập nhật tài liệu. Nếu package tree thay đổi ngoài dự kiến, cần xem lại refactor hoặc metadata.

## 9. Quy trình đối chiếu sau một lần refactor

Thực hiện theo trình tự sau:

1. Xác định lớp ứng dụng và package gốc dùng để xây dựng mô hình.
2. Xem package tree mới và liệt kê các base package của module.
3. Mở `package-info.java` để kiểm tra `@ApplicationModule` và `@NamedInterface`.
4. Đối chiếu public API, package nội bộ và named interface của từng module.
5. Rà soát import, constructor injection và event listener để xác nhận dependency.
6. Kiểm tra `allowedDependencies` và module identifier nếu tên module đã thay đổi.
7. Chạy `ApplicationModules.verify()` để phát hiện dependency không hợp lệ và cycle.
8. Tạo lại Application Module Canvas bằng `Documenter`.
9. So sánh tài liệu mới với tài liệu đang dùng và cập nhật phần mô tả nghiệp vụ nếu cần.
10. Đưa bước verification và sinh tài liệu vào quy trình CI phù hợp với dự án.

Quy trình này giúp nhóm kiểm tra cả cấu trúc code lẫn phần giải thích kiến trúc mà những người khác dựa vào.

## 10. Tích hợp kiểm tra vào CI

Một architecture test có thể giữ quy tắc module luôn được kiểm tra:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesModuleStructure() {
        ApplicationModules.of(ShopApplication.class).verify();
    }
}
~~~

Test nên chạy trong pipeline kiểm thử thông thường để phát hiện dependency vi phạm ngay khi có thay đổi. Nếu dự án sinh tài liệu tự động, có thể thêm bước tạo canvas sau khi kiểm tra kiến trúc thành công.

Khi review kết quả CI, phân biệt:

- Test verification thất bại: mô hình có vi phạm kiến trúc cần được xử lý.
- Tài liệu sinh ra thay đổi: package, module, API hoặc dependency có thể đã thay đổi.
- Tài liệu thủ công thay đổi nhưng model không đổi: cần kiểm tra xem phần mô tả có phản ánh đúng code hay không.

Không nên chỉ so sánh ảnh diagram đã render. Hãy lưu hoặc review artifact nguồn phù hợp với quy trình dự án để người review có thể nhận biết module và dependency nào đã thay đổi.

## 11. Giới hạn của việc đối chiếu

Package tree và tài liệu Spring Modulith giúp hiểu cấu trúc module, nhưng không mô tả mọi khía cạnh runtime:

- Component scan có thể đăng ký bean từ nhiều package; điều đó không tự biến package nội bộ thành API.
- Bean có thể được đăng ký bằng `@Bean`, `@Import` hoặc auto-configuration ngoài component scan thông thường.
- Sơ đồ dependency không chứng minh event listener được thực thi thành công.
- Application Module Canvas không thay thế tài liệu nghiệp vụ chi tiết hoặc hợp đồng API HTTP.
- `ApplicationModules.verify()` kiểm tra quy tắc kiến trúc mà mô hình hỗ trợ, không xác nhận mọi quyết định thiết kế đều hợp lý.
- Một package có thể giữ nguyên tên trong khi trách nhiệm nghiệp vụ thay đổi; trường hợp này cần review nội dung và cập nhật mô tả thủ công.

Vì vậy, hãy kết hợp đối chiếu package tree, generated documentation, architecture test và review của nhóm sở hữu module.

## 12. Những nhầm lẫn thường gặp

**Cho rằng diagram là bản sao trực tiếp của cây thư mục.** Diagram mô tả module và dependency; package tree cho thấy vị trí package và class. Một module có thể chứa nhiều package con.

**Cho rằng package con `internal` không xuất hiện trong tài liệu thì package đó không tồn tại.** Tài liệu có thể tập trung vào API và dependency ở cấp module. Hãy kiểm tra source tree khi cần xác nhận chi tiết nội bộ.

**Cho rằng mọi class `public` đều là public API.** Spring Modulith xem package con là nội bộ theo mặc định, kể cả khi class có modifier `public`.

**Cho rằng named interface là module riêng.** Named interface mở rộng vùng API của module cha; nó không tự tạo application module mới.

**Cho rằng event flow và dependency graph có cùng chiều mũi tên.** Subscriber phụ thuộc vào module cung cấp event type, trong khi event được chuyển từ publisher đến subscriber.

**Cho rằng tạo lại canvas là đủ để kiểm tra kiến trúc.** Canvas hỗ trợ quan sát; `ApplicationModules.verify()` mới thực hiện kiểm chứng các quy tắc dependency mà mô hình hỗ trợ.

**Cho rằng tài liệu sinh tự động luôn mô tả đúng trách nhiệm nghiệp vụ.** Công cụ có thể mô tả cấu trúc và dependency từ code, nhưng nhóm vẫn phải review nội dung ngữ nghĩa và cập nhật phần giải thích.

## 13. Checklist đối chiếu tài liệu với package tree

- [ ] Xác định đúng lớp ứng dụng và package gốc.
- [ ] Mỗi module trên tài liệu có package gốc tương ứng trong source tree.
- [ ] Module identifier và display name được phân biệt rõ.
- [ ] Public API nằm ở base package hoặc named interface được công bố.
- [ ] Package con nội bộ không bị mô tả nhầm thành API.
- [ ] Mọi named interface trên tài liệu có `package-info.java` và annotation tương ứng.
- [ ] Dependency trên diagram khớp với import, injection point và event listener.
- [ ] `allowedDependencies` phản ánh đúng hợp đồng mà module tiêu thụ sử dụng.
- [ ] Event flow không bị nhầm với chiều dependency.
- [ ] Đã chạy `ApplicationModules.verify()` sau thay đổi.
- [ ] Đã tạo lại Application Module Canvas từ mô hình mới.
- [ ] Đã cập nhật mô tả trách nhiệm nếu chức năng module thay đổi.
- [ ] Architecture test được giữ trong CI.

## 14. Kết luận

Đối chiếu tài liệu với package tree là cách xác nhận tài liệu kiến trúc còn phản ánh đúng cấu trúc module trong codebase. Hãy bắt đầu từ package gốc của ứng dụng, kiểm tra từng base package, public API, named interface và các dependency được hình thành từ import, injection hoặc event listener.

Sau refactor, tạo lại Application Module Canvas từ `ApplicationModules` và dùng `ApplicationModules.verify()` để kiểm tra ranh giới. Khi phát hiện sai lệch, xác định thay đổi nào là chủ ý kiến trúc rồi cập nhật tài liệu hoặc source metadata tương ứng. Kết hợp bước này với review của nhóm sở hữu module để giữ cả cấu trúc code lẫn cách giải thích kiến trúc nhất quán.

## Tài liệu tham khảo

- [Spring Modulith — Fundamentals: Application Modules](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Spring Modulith — Documenting Application Modules](https://docs.spring.io/spring-modulith/reference/documentation.html)
- [Spring Modulith — Verifying Application Module Structure](https://docs.spring.io/spring-modulith/reference/verification.html)
- [Spring Modulith — `Documenter` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/docs/Documenter.html)
- [Spring Modulith — `ApplicationModules` API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
