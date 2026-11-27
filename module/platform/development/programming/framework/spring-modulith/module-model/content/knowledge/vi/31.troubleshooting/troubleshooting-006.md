# allowedDependencies không khớp identifier

Khi Spring Modulith báo một dependency không được phép dù tên module có vẻ đúng, nguyên nhân thường nằm ở identifier mà mô hình module thực sự sử dụng. Giá trị trong allowedDependencies phải khớp với định danh logic của module đích và, nếu khai báo một named interface, phải khớp cả tên giao diện đó.

Ví dụ, module shipping muốn dùng API của inventory. Cấu hình inventory::api chỉ hợp lệ nếu mô hình phát hiện module đích có identifier inventory và module đó thực sự công khai named interface api. Tên hiển thị trên tài liệu, tên lớp Java, tên folder hoặc tên package mà nhóm tự suy đoán có thể khác với identifier mà Spring Modulith đang dùng.

Bài này trình bày cách xác định identifier thật, tìm lỗi sai phổ biến và sửa allowedDependencies mà không vô tình mở rộng quyền truy cập vào package nội bộ.

## 1. Hiểu đúng cấu trúc của một dependency identifier

Một application module có package gốc, một identifier logic và có thể có nhiều named interface. Ví dụ:

~~~text
com.example
├── Application.java
├── inventory
│   ├── package-info.java
│   ├── StockAvailability.java
│   ├── api
│   │   ├── package-info.java
│   │   └── StockSummary.java
│   └── internal
│       └── StockRepository.java
└── shipping
    ├── package-info.java
    └── ShippingService.java
~~~

Theo cách phát hiện module mặc định, package trực tiếp dưới package gốc của ứng dụng là package gốc của application module. Với cấu trúc trên, tên logic cục bộ của module thường là inventory hoặc shipping.

Module inventory có API mặc định trong package gốc com.example.inventory. Package con api chỉ trở thành named interface khi được công khai rõ ràng:

~~~java
@org.springframework.modulith.NamedInterface("api")
package com.example.inventory.api;
~~~

Module tiêu thụ shipping khai báo phụ thuộc trong package-info.java của chính nó:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "inventory::api"
)
package com.example.shipping;
~~~

Cú pháp có hai phần:

- Phần trước dấu :: là identifier của module cung cấp.
- Phần sau dấu :: là tên named interface mà module tiêu thụ được phép sử dụng.

Tên package api không tự động trở thành tên named interface chỉ vì package có tên api. Annotation phải được khai báo và tên trong annotation phải khớp với phần sau dấu ::.

## 2. Phân biệt identifier, display name và package name

Ba giá trị này có mục đích khác nhau:

| Giá trị | Ví dụ | Vai trò |
|---|---|---|
| Package gốc | com.example.inventory | Vị trí package của module |
| Identifier logic | inventory | Định danh dùng trong allowedDependencies theo mặc định |
| Display name | Quản lý tồn kho | Tên thân thiện để hiển thị trong tài liệu |

Không dùng displayName để khai báo allowedDependencies. displayName phục vụ người đọc, còn identifier dùng để Spring Modulith nối các module trong mô hình kiến trúc.

Trong cấu trúc mặc định, identifier cục bộ thường được suy ra từ tên package module. Vì thế, nếu package gốc là com.example.inventory thì giá trị inventory thường là identifier phù hợp. Tuy nhiên, có các cấu hình khiến identifier khác với tên segment cuối của package; cần kiểm tra mô hình thay vì đoán.

## 3. Xem identifier mà Spring Modulith thực sự phát hiện

Trước khi sửa annotation, hãy in mô hình module để xem tên logic và package gốc mà Spring Modulith đã nhận diện:

~~~java
package com.example;

import org.springframework.modulith.core.ApplicationModules;

class InspectModules {

    public static void main(String[] args) {
        var modules = ApplicationModules.of(Application.class);
        System.out.println(modules);
    }
}
~~~

Biểu diễn mô hình module chứa thông tin về module, tên logic và package gốc. Đối chiếu các thông tin đó với giá trị ở allowedDependencies.

Với API Spring Modulith hiện hành, có thể truy vấn một module theo tên và xem các named interface mà nó công khai:

~~~java
var modules = ApplicationModules.of(Application.class);

modules.getModuleByName("inventory")
        .ifPresent(module -> {
            System.out.println(module.getIdentifier());
            System.out.println(module.getNamedInterfaces());
        });
~~~

Nếu module đã được đổi identifier thành stock, hãy truy vấn bằng stock. API getIdentifier() có từ Spring Modulith 1.3; với phiên bản cũ hơn, tham khảo API đúng phiên bản dự án hoặc dùng biểu diễn mô hình modules để kiểm tra.

Để chẩn đoán, hãy xác nhận lần lượt:

1. Application.class nằm ở package gốc dự kiến.
2. Module cung cấp thực sự được phát hiện.
3. Identifier của module cung cấp có đúng với phần trước dấu :: không.
4. Named interface có tồn tại và tên có đúng với phần sau dấu :: không.
5. Module tiêu thụ khai báo dependency ở đúng package.

## 4. Lỗi sai tên module

Một lỗi thường gặp là dùng tên số nhiều hoặc tên nghiệp vụ tự đặt thay vì identifier logic.

Ví dụ module có package gốc com.example.inventory nhưng consumer khai báo:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "inventories"
)
package com.example.shipping;
~~~

Trong khi identifier thực tế là inventory. Sửa thành:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "inventory"
)
package com.example.shipping;
~~~

Nếu cần giới hạn vào named interface api, dùng:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "inventory::api"
)
package com.example.shipping;
~~~

Không thêm tên lớp StockRepository hoặc StockAvailability vào allowedDependencies. Thuộc tính này mô tả quan hệ module, không phải danh sách class được phép import.

## 5. Lỗi sai tên named interface

Giả sử package api được khai báo:

~~~java
@org.springframework.modulith.NamedInterface("api")
package com.example.inventory.api;
~~~

Consumer lại viết:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "inventory::public-api"
)
package com.example.shipping;
~~~

Identifier module inventory là đúng, nhưng tên named interface public-api không tồn tại. Hãy sửa một phía sao cho thống nhất. Nếu muốn giữ tên api, consumer cần dùng:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "inventory::api"
)
package com.example.shipping;
~~~

Nếu muốn named interface có tên public-api, đổi annotation ở package được công khai:

~~~java
@org.springframework.modulith.NamedInterface("public-api")
package com.example.inventory.api;
~~~

Khi đổi tên named interface, tìm và cập nhật tất cả consumer đang tham chiếu tên cũ. Tên package và tên named interface là hai khái niệm riêng; annotation value mới là tên được dùng trong cú pháp module::interface.

## 6. Identifier tùy chỉnh bằng @ApplicationModule(id)

Ở các phiên bản Spring Modulith hỗ trợ thuộc tính id trên @ApplicationModule, module có thể khai báo identifier ổn định thay cho tên logic mặc định. Ví dụ:

~~~java
@org.springframework.modulith.ApplicationModule(id = "stock")
package com.example.inventory;
~~~

Nếu module inventory có named interface api, consumer phải tham chiếu identifier stock:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "stock::api"
)
package com.example.shipping;
~~~

Trong trường hợp này, dùng inventory::api sẽ không khớp với identifier tùy chỉnh stock.

Hãy phân biệt id với displayName:

~~~java
@org.springframework.modulith.ApplicationModule(
        id = "stock",
        displayName = "Quản lý tồn kho"
)
package com.example.inventory;
~~~

- stock là identifier logic được dùng trong quan hệ module.
- Quản lý tồn kho là tên hiển thị cho tài liệu và người đọc.

Không dùng chuỗi displayName trong allowedDependencies. Khi thay đổi id của một module, cần tìm tất cả nơi tham chiếu identifier cũ, bao gồm allowedDependencies và các cấu hình khác dùng tên module.

## 7. Local identifier và fully-qualified module name

Mặc định, Spring Modulith sử dụng tên module cục bộ. Ví dụ, package com.example.inventory thường được định danh là inventory.

Nếu ứng dụng có nhiều package gốc được phát hiện thông qua additionalPackages và chúng chứa các module cùng tên cục bộ, có thể cấu hình sử dụng fully-qualified module names:

~~~java
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.modulith.Modulithic;

@Modulithic(useFullyQualifiedModuleNames = true)
@SpringBootApplication
class Application {
}
~~~

Khi bật tùy chọn này, identifier mặc định được tạo từ package đầy đủ. Ví dụ dependency đến named interface api có thể phải viết:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "com.example.inventory::api"
)
package com.example.shipping;
~~~

Nếu consumer vẫn dùng inventory::api trong khi mô hình yêu cầu com.example.inventory::api, identifier sẽ không khớp.

Chỉ bật fully-qualified names khi có lý do về cấu trúc nhiều package gốc hoặc xung đột tên module. Khi thay đổi tùy chọn này, rà soát toàn bộ allowedDependencies và các cấu hình tham chiếu module để chúng dùng cùng một quy ước.

## 8. Kiểm tra module có được phát hiện hay không

Identifier không thể khớp nếu module đích chưa xuất hiện trong mô hình. Theo mặc định, Spring Modulith tìm application module trong các package con trực tiếp của package chứa lớp Spring Boot.

Ví dụ, với lớp ứng dụng ở com.example, cấu trúc sau phù hợp với cách phát hiện mặc định:

~~~text
com.example
├── Application.java
├── inventory
└── shipping
~~~

Nếu module nằm ngoài package gốc, được đặt sâu hơn dự kiến hoặc được quản lý bởi custom detection strategy, kiểm tra cách phát hiện module:

- Đặt lớp ứng dụng ở đúng package gốc.
- Nếu dùng @Modulithic(additionalPackages = ...), xác nhận package bổ sung đã được khai báo.
- Nếu dùng detection strategy explicitly-annotated, bảo đảm package module được đánh dấu bằng @ApplicationModule hoặc annotation @Module của jMolecules.
- Nếu dùng custom ApplicationModuleDetectionStrategy, xác nhận strategy được đăng ký và chọn đúng package gốc của module.
- Nếu dùng nested modules, kiểm tra identifier của module cha và module con theo mô hình thực tế.

Đừng giải quyết lỗi module không được phát hiện bằng cách thêm một chuỗi phỏng đoán vào allowedDependencies. Trước hết phải làm cho module xuất hiện trong mô hình.

## 9. Đặt allowedDependencies ở đúng phía

allowedDependencies được khai báo trên module tiêu thụ, tức module đang tạo ra dependency.

Ví dụ, shipping sử dụng inventory:

~~~java
@org.springframework.modulith.ApplicationModule(
        allowedDependencies = "inventory::api"
)
package com.example.shipping;
~~~

Đặt cấu hình này trong package-info.java của inventory sẽ có ý nghĩa ngược lại: nó quy định inventory được phép phụ thuộc vào module nào. Nó không cấp quyền cho shipping sử dụng inventory.

Hãy đọc quan hệ theo hướng:

~~~text
shipping  ─────depends on─────>  inventory::api
  consumer                         provider
  khai báo                         cung cấp
  allowedDependencies              named interface
~~~

Nếu thông báo vi phạm nói module shipping không được phép phụ thuộc vào inventory, hãy kiểm tra annotation trên package gốc của shipping trước.

## 10. Chọn phạm vi named interface chính xác

Khi khai báo dependency tường minh, có thể chỉ rõ phạm vi API mà consumer được phép sử dụng:

| Cú pháp | Ý nghĩa |
|---|---|
| inventory | Khai báo dependency đến module inventory theo identifier của module |
| inventory::api | Cho phép named interface api |
| inventory::* | Cho phép tất cả named interface được khai báo; không bao gồm package gốc |
| inventory::** | Cho phép package gốc và tất cả named interface được khai báo |

Nếu consumer cần package gốc và một named interface cụ thể, hãy khai báo từng entry phù hợp hoặc dùng cú pháp bao phủ có chủ đích. Đừng dùng wildcard rộng chỉ để bỏ qua lỗi identifier; điều đó làm giảm khả năng kiểm soát bề mặt API.

Một package có tên internal vẫn là nội bộ nếu nó không được công khai theo mô hình module. Thêm tên module vào allowedDependencies không biến mọi package con thành API công khai. Với module OPEN, quy tắc truy cập nội bộ có thể khác; chỉ dùng kiểu module đó khi dự án chủ ý áp dụng chiến lược chuyển đổi legacy tương ứng.

## 11. Hiểu trạng thái mặc định và danh sách rỗng

Một điểm dễ nhầm là để thuộc tính allowedDependencies mặc định khác với khai báo một danh sách rỗng.

- Không khai báo allowedDependencies: không bật giới hạn danh sách dependency tường minh của module.
- Khai báo allowedDependencies với danh sách rỗng: module không được phép phụ thuộc vào application module khác theo danh sách đó.
- Khai báo một hoặc nhiều identifier: chỉ các dependency được khai báo phù hợp mới được cho phép.

Vì vậy, nếu vô tình tạo annotation với allowedDependencies = {}, test có thể báo mọi dependency đều không được phép. Nếu mục tiêu là không giới hạn dependency bằng allowlist, hãy để thuộc tính ở giá trị mặc định. Nếu muốn bảo vệ module chặt chẽ, khai báo chính xác các dependency cần thiết.

## 12. Quy trình chẩn đoán và sửa lỗi

Khi verify báo allowedDependencies không khớp identifier, thực hiện theo trình tự:

1. Đọc module nguồn trong thông báo vi phạm. Đây là module cần kiểm tra annotation allowedDependencies.
2. In ApplicationModules.of(Application.class) để xem danh sách module và logical name.
3. Xác nhận module đích tồn tại trong mô hình và xác định package gốc.
4. Xác nhận module có id tùy chỉnh hay đang dùng local identifier hoặc fully-qualified identifier.
5. Nếu dependency dùng module::interface, kiểm tra annotation @NamedInterface và tên chính xác.
6. Kiểm tra allowedDependencies được khai báo trên consumer và đúng package-info.java.
7. Chỉ sửa identifier hoặc named interface sau khi đã xác nhận mô hình thực tế.
8. Chạy lại ApplicationModules.verify() và kiểm tra các dependency liên quan.

Có thể giữ một test kiến trúc đơn giản:

~~~java
package com.example;

import org.junit.jupiter.api.Test;
import org.springframework.modulith.core.ApplicationModules;

class ModularityTests {

    @Test
    void verifiesAllowedModuleDependencies() {
        ApplicationModules.of(Application.class).verify();
    }
}
~~~

Nếu test vẫn thất bại, đọc toàn bộ danh sách vi phạm. Một consumer có thể có nhiều dependency sai identifier; sửa lỗi đầu tiên không đảm bảo các entry còn lại đã đúng.

## 13. Bài tập thực hành

1. Tạo module inventory với package gốc com.example.inventory và named interface api.
2. Khai báo @NamedInterface("api") trong package-info.java của package inventory.api.
3. Khai báo shipping chỉ được phụ thuộc vào inventory::api.
4. Cố ý đổi inventory thành inventories và chạy verify để quan sát lỗi.
5. Khôi phục identifier đúng, sau đó đổi api thành public-api trong allowedDependencies để quan sát lỗi named interface.
6. Thử đặt id tùy chỉnh stock trên module inventory và cập nhật consumer thành stock::api.
7. Nếu dự án dùng fully-qualified module names, kiểm tra identifier hiển thị và cập nhật dependency tương ứng.
8. Chạy architecture test và giải thích vì sao Java compile có thể thành công nhưng Spring Modulith verification vẫn thất bại.

Sau bài tập, bạn cần phân biệt được module identifier, package name, display name và named-interface name; biết kiểm tra identifier thật từ mô hình ApplicationModules; và có thể sửa dependency theo đúng phía consumer mà không mở rộng nhầm API.

## Tài liệu tham khảo

- [Explicit Application Module Dependencies and Named Interfaces – Spring Modulith](https://docs.spring.io/spring-modulith/reference/fundamentals.html)
- [Verifying Application Module Structure – Spring Modulith](https://docs.spring.io/spring-modulith/reference/verification.html)
- [ApplicationModule Annotation API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/ApplicationModule.html)
- [ApplicationModules API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/core/ApplicationModules.html)
- [Modulithic Annotation API](https://docs.spring.io/spring-modulith/docs/current/api/org/springframework/modulith/Modulithic.html)
