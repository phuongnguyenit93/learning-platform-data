# Qualified export cho integration đặc thù

## 1. Mục tiêu

Java Platform Module System (JPMS) cho phép một module công khai package của nó thông qua directive **exports** trong file **module-info.java**. Export không nhất thiết phải dành cho mọi module. Khi một package chỉ phục vụ một số hệ thống tích hợp cụ thể, module nguồn có thể dùng **qualified export** để chỉ định chính xác các module được phép truy cập.

Ví dụ, một module nền tảng có thể cung cấp package tích hợp cho module adapter của đối tác, module báo cáo và module kiểm thử nội bộ. Các module khác vẫn không được truy cập package đó qua quy tắc module thông thường.

Sau bài học, bạn có thể:
- Viết directive **exports package.name to module.one, module.two;**.
- Phân biệt qualified export với unqualified export.
- Thiết kế package API dành cho một nhóm module tích hợp xác định.
- Hiểu vì sao consumer vẫn cần **requires** để đọc module cung cấp.
- Phân biệt qualified export với **opens**, **--add-exports** và **--add-opens**.
- Chẩn đoán lỗi module access và kiểm thử phạm vi tích hợp.

## 2. Qualified export là gì?

Một module có thể export package theo hai cách.

**Unqualified export** công khai package cho mọi module đọc module nguồn:

~~~java
module com.example.platform {
    exports com.example.platform.api;
}
~~~

Mọi module đọc được **com.example.platform** đều có thể truy cập các public type trong package **com.example.platform.api**, theo các quy tắc truy cập Java thông thường.

**Qualified export** chỉ công khai package cho các module được liệt kê:

~~~java
module com.example.platform {
    exports com.example.platform.partner
        to com.example.crm.adapter,
           com.example.audit.integration;
}
~~~

Trong ví dụ này, package **com.example.platform.partner** được export cho hai module đích:
- **com.example.crm.adapter**
- **com.example.audit.integration**

Các module khác không nằm trong danh sách vẫn không được truy cập package này thông qua module system, kể cả khi chúng đọc được module **com.example.platform**.

Qualified export là một directive ở cấp package. Nó không chọn riêng từng class hoặc method trong package. Nếu package được export cho một module đích, các public type trong package đó có thể được module đích truy cập theo quy tắc Java. Vì vậy, hãy thiết kế package sao cho chỉ chứa những kiểu thực sự thuộc API tích hợp.

## 3. Cú pháp trong module-info.java

Cú pháp:

~~~java
exports package.name to module.name.one, module.name.two;
~~~

Các thành phần:

- **exports**: khai báo package được công khai qua ranh giới module.
- **package.name**: tên package đầy đủ, không phải tên class hoặc đường dẫn thư mục.
- **to**: đánh dấu đây là qualified export.
- **module.name.one** và **module.name.two**: tên module đích, phân tách bằng dấu phẩy.

Ví dụ:

~~~java
module com.example.orders {
    exports com.example.orders.api;
    exports com.example.orders.partner
        to com.example.crm.adapter,
           com.example.billing.bridge;
}
~~~

Ở đây:
- **com.example.orders.api** là API công khai cho mọi module đọc module **com.example.orders**.
- **com.example.orders.partner** chỉ được export cho hai module tích hợp đã nêu.
- Package khác không được export sẽ tiếp tục được đóng đối với truy cập thông thường từ module khác.

Tên trong danh sách **to** là tên module, không phải tên package của ứng dụng. Ví dụ, nếu module consumer khai báo:

~~~java
module com.example.crm.adapter {
    requires com.example.orders;
}
~~~

thì tên module đích chính xác là **com.example.crm.adapter**.

Qualified export chỉ có ý nghĩa khi source module là named module và các module đích cũng được nhận diện bằng tên module. Không ghi **ALL-UNNAMED** trong danh sách **to**. ALL-UNNAMED là target đặc biệt của các tùy chọn launcher như **--add-exports**, không phải tên module hợp lệ để dùng trong directive module-info.java.

## 4. Ví dụ producer và consumer hoàn chỉnh

Giả sử module **com.example.platform** cung cấp một API dành riêng cho hai integration module.

Cấu trúc thư mục minh họa:

~~~text
src/
  com.example.platform/
    module-info.java
    com/example/platform/api/PlatformService.java
    com/example/platform/partner/PartnerGateway.java
  com.example.crm.adapter/
    module-info.java
    com/example/crm/adapter/CrmSync.java
  com.example.audit.integration/
    module-info.java
    com/example/audit/integration/AuditExport.java
  com.example.external.app/
    module-info.java
    com/example/external/app/Main.java
~~~

Module nguồn:

~~~java
module com.example.platform {
    exports com.example.platform.api;

    exports com.example.platform.partner
        to com.example.crm.adapter,
           com.example.audit.integration;
}
~~~

API chung:

~~~java
package com.example.platform.api;

public interface PlatformService {
    String platformName();
}
~~~

API tích hợp riêng:

~~~java
package com.example.platform.partner;

public final class PartnerGateway {
    public String submit(String payload) {
        return "accepted: " + payload;
    }
}
~~~

Module CRM consumer:

~~~java
module com.example.crm.adapter {
    requires com.example.platform;
}
~~~

Mã consumer:

~~~java
package com.example.crm.adapter;

import com.example.platform.partner.PartnerGateway;

public final class CrmSync {
    public String synchronize() {
        PartnerGateway gateway = new PartnerGateway();
        return gateway.submit("customer-42");
    }
}
~~~

Module audit cũng được phép đọc package tích hợp vì đã nằm trong danh sách qualified export:

~~~java
module com.example.audit.integration {
    requires com.example.platform;
}
~~~

Trong khi đó, module không được liệt kê:

~~~java
module com.example.external.app {
    requires com.example.platform;
}
~~~

Nếu module này cố import **com.example.platform.partner.PartnerGateway**, compiler sẽ báo package không được export cho module **com.example.external.app**. Việc có **requires com.example.platform** chỉ làm module nguồn trở nên readable; nó không tự cấp quyền truy cập mọi package bên trong module đó.

## 5. Qualified export không thay thế requires

Để module consumer dùng được một public type trong package được export, hai điều kiện cần được thỏa mãn:

1. Consumer phải đọc được module nguồn.
2. Package chứa public type phải được export cho consumer.

Thông thường, consumer khai báo **requires** trong module descriptor:

~~~java
module com.example.crm.adapter {
    requires com.example.platform;
}
~~~

Module nguồn khai báo qualified export:

~~~java
module com.example.platform {
    exports com.example.platform.partner
        to com.example.crm.adapter;
}
~~~

Hai directive này phối hợp với nhau:
- **requires** nằm ở consumer và tạo quan hệ readability tới module nguồn.
- **exports ... to ...** nằm ở source module và cho phép module đích truy cập package được chỉ định.

Nếu thiếu **requires**, consumer có thể không đọc được module nguồn dù package đã được export cho nó. Nếu thiếu tên consumer trong danh sách **to**, consumer có thể đọc module nguồn nhưng vẫn không truy cập được package.

Trong trường hợp phải cấu hình module graph từ dòng lệnh mà không sửa được descriptor, có thể cân nhắc **--add-reads** để bổ sung readability. Đây là workaround cho cấu hình runtime; với một integration ổn định, nên thể hiện dependency bằng **requires** trong module-info.java.

## 6. Khi nào nên dùng qualified export?

Qualified export phù hợp khi một package là API tích hợp có chủ đích nhưng không phải API chung của toàn bộ hệ sinh thái module.

Một số trường hợp:

- **Adapter đối tác:** chỉ module adapter do đối tác cung cấp được dùng API tích hợp.
- **Bridge giữa hai hệ thống:** module bridge cần một số type để chuyển đổi dữ liệu hoặc giao thức.
- **Plugin được kiểm soát:** một số module plugin đã biết cần dùng extension API riêng.
- **API nội bộ giữa các module trong cùng sản phẩm:** nhóm phát triển muốn tách public API ổn định khỏi package dành cho một số thành phần phối hợp.
- **Tích hợp migration:** một module cũ cần truy cập package chuyển tiếp trong khi các module mới đã dùng API công khai khác.

Không nên dùng qualified export chỉ vì muốn "ẩn" một class khỏi người dùng trong cùng module. Nếu class không phải API, hãy đặt nó trong package không export. Qualified export là công cụ kiểm soát module nào được truy cập package, không phải công cụ chọn class bên trong package.

Nếu nhiều module bên ngoài cần package như một hợp đồng công khai lâu dài, unqualified export có thể đơn giản và phù hợp hơn. Nếu chỉ một vài module tích hợp được quản lý cần package đó, qualified export giúp thể hiện chính xác phạm vi phụ thuộc.

## 7. Thiết kế package dành riêng cho integration

Vì qualified export áp dụng cho toàn package, cách tổ chức package quyết định phạm vi API được lộ ra.

Ví dụ nên tách API công khai, API tích hợp và implementation:

~~~text
com.example.platform.api
com.example.platform.partner
com.example.platform.internal
com.example.platform.impl
~~~

Module descriptor:

~~~java
module com.example.platform {
    exports com.example.platform.api;

    exports com.example.platform.partner
        to com.example.crm.adapter,
           com.example.audit.integration;
}
~~~

Trong cách tổ chức này:
- **api** chứa các type mà mọi consumer hợp lệ có thể dùng.
- **partner** chứa các type được chia sẻ với module tích hợp đã chọn.
- **internal** và **impl** không được export nên vẫn nằm trong ranh giới module.

Tránh đặt implementation class public trong package đã qualified-export nếu consumer không cần chúng. Dù consumer không được khuyến khích sử dụng, public class trong package được export vẫn có thể trở thành một phần bề mặt API mà module nguồn phải cân nhắc duy trì.

Một thiết kế tốt thường cung cấp interface hoặc facade nhỏ thay vì để integration truy cập nhiều class triển khai. Ví dụ, chỉ export **PartnerGateway** và các kiểu dữ liệu request/response cần thiết; giữ cache, repository, internal factory và implementation trong package không export.

## 8. Qualified export khác với opens

**exports** và **opens** giải quyết hai kiểu truy cập khác nhau.

| Directive | Tác dụng | Trường hợp thường dùng |
|---|---|---|
| **exports p** | Cho phép module đọc nguồn truy cập public type/member trong package p theo quy tắc Java | API được gọi trực tiếp qua code |
| **exports p to m** | Chỉ cho module m truy cập public API của package p | API tích hợp dành cho module cụ thể |
| **opens p** | Cho phép deep reflection vào package p ở runtime | Framework cần truy cập reflective vào thành viên không public |
| **opens p to m** | Chỉ mở package p cho deep reflection từ module m | Framework hoặc adapter reflection được kiểm soát |

Ví dụ qualified open:

~~~java
module com.example.persistence {
    opens com.example.persistence.entity
        to com.example.orm;
}
~~~

Ví dụ này cho phép module **com.example.orm** thực hiện deep reflection vào package entity theo quy tắc reflection. Nó không tương đương với qualified export.

Nếu integration gọi trực tiếp một public method của **PartnerGateway**, hãy dùng qualified export. Nếu framework cần truy cập private field hoặc private constructor qua reflection, hãy đánh giá qualified open. Không thêm cả **exports** và **opens** nếu chỉ một quyền là đủ.

Một package đã export không tự động mở cho deep reflection vào các thành viên private. Ngược lại, package được mở cho reflection không đồng nghĩa mã consumer có thể import mọi public type trong package theo cách thông thường.

## 9. Qualified export khác với --add-exports

Có thể bổ sung export bằng tùy chọn launcher:

~~~bash
java --add-exports com.example.platform/com.example.platform.partner=com.example.crm.adapter --module-path mods --module com.example.crm.adapter/com.example.crm.adapter.Main
~~~

Tùy chọn này thêm export vào module configuration của tiến trình JVM. Nó không sửa **module-info.java** và không thay đổi module descriptor trong JAR.

So sánh:

- **Qualified export trong module-info.java:** là thiết kế của source module, được đóng gói trong descriptor và áp dụng khi module được phân giải.
- **--add-exports:** là override từ dòng lệnh, thường dùng cho migration, kiểm thử hoặc môi trường triển khai đặc biệt.
- **--add-opens:** mở package cho deep reflection ở runtime, không thay thế qualified export.

Nếu sở hữu source module, hãy ưu tiên thể hiện quan hệ tích hợp lâu dài trong **module-info.java**. Dùng cờ dòng lệnh khi cần một điều chỉnh vận hành có chủ đích hoặc khi không thể sửa module descriptor.

Tùy chọn **--add-exports** cũng không tự tạo readability. Nếu consumer không đọc source module, cần **requires** hoặc một cấu hình **--add-reads** thích hợp.

## 10. Giới hạn và điều cần cân nhắc

Qualified export thu hẹp tập module được phép truy cập package, nhưng không phải một cơ chế bảo mật thay thế cho xác thực hay phân quyền ứng dụng.

Một số điểm cần nhớ:

1. **Phạm vi là package:** tất cả public type trong package đều có thể trở thành bề mặt API đối với các module đích.
2. **Module name là hợp đồng:** đổi tên module consumer có thể khiến qualified export không còn khớp.
3. **Readability vẫn cần thiết:** qualified export không thêm **requires** cho consumer.
4. **Reflection là vấn đề riêng:** truy cập private qua reflection có thể cần **opens**, không phải **exports**.
5. **Không phải sandbox:** module system giúp đóng gói và kiểm soát khả năng truy cập theo module; không thay thế kiểm soát bảo mật, xác thực danh tính plugin hay phân quyền dữ liệu.
6. **API vẫn cần quản lý phiên bản:** các module được export cho có thể phụ thuộc vào kiểu public; thay đổi chữ ký hoặc xóa type có thể phá vỡ integration.
7. **Tránh split package:** không phân tán các class cùng package qua nhiều named module. Thiết kế package ownership rõ ràng giúp module resolution dễ dự đoán.

Nếu target module không có mặt trong module graph, qualified export vẫn được ghi trong descriptor nhưng không tạo ra quyền truy cập cho một consumer đang không tồn tại. Khi module đích được đưa vào graph ở lần chạy khác, quan hệ export mới có ý nghĩa đối với module đó.

## 11. Biên dịch và chạy ví dụ

Giả sử các module được đặt trong thư mục **src** theo cấu trúc ở phần ví dụ. Có thể biên dịch các module cùng lúc bằng module source path:

~~~bash
javac --module-source-path src -d mods -m com.example.platform,com.example.crm.adapter,com.example.audit.integration
~~~

Nếu muốn kiểm tra module graph, dùng:

~~~bash
java --module-path mods --describe-module com.example.platform
~~~

Chạy module consumer:

~~~bash
java --module-path mods --module com.example.crm.adapter/com.example.crm.adapter.Main
~~~

Nếu consumer được phép truy cập package partner, module graph sẽ phân giải và mã có thể dùng public type trong package đó. Nếu một module khác không nằm trong danh sách qualified export cố import cùng type, lỗi có thể xuất hiện khi biên dịch hoặc khi liên kết/truy cập runtime, tùy thời điểm kiểm tra.

Đối với artifact JAR đã đóng gói, có thể kiểm tra descriptor bằng:

~~~bash
jar --describe-module --file platform.jar
~~~

Kết quả mô tả module giúp xác nhận tên module và các package được export. Dùng **jdeps** hoặc công cụ phân tích module để kiểm tra dependency nếu cần.

## 12. Chẩn đoán lỗi qualified export

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Consumer báo package không được export | Module đích chưa được liệt kê trong qualified export | Thêm đúng tên module consumer vào danh sách **to** |
| Consumer báo module không đọc được source module | Thiếu **requires** hoặc readability | Khai báo requires hoặc kiểm tra module graph |
| Directive **to** báo module không tìm thấy | Tên module đích sai hoặc module chưa có trên module path lúc biên dịch | Kiểm tra tên trong module-info.java và cấu hình compile |
| Consumer trên classpath không truy cập được | Unnamed module không thể được liệt kê như target trong module descriptor | Dùng named module cho integration hoặc cấu hình --add-exports tạm thời |
| Framework không truy cập private field | Chỉ export package, chưa mở cho deep reflection | Xem xét **opens p to m** hoặc --add-opens |
| Module khác vẫn truy cập được package | Package cũng được unqualified export hoặc có override từ dòng lệnh | Kiểm tra module-info.java và JVM arguments |
| Integration lỗi sau khi đổi tên module | Qualified export vẫn nhắm tới tên module cũ | Đồng bộ module name trong descriptor và dependency |

Khi điều tra, kiểm tra cả hai phía: descriptor của source module và descriptor của consumer. Xác định chính xác package, module name, **requires**, **exports ... to ...**, và các cờ JVM được truyền vào tiến trình. Đừng chỉ nhìn source code của consumer rồi kết luận lỗi nằm ở modifier public.

## 13. Tự kiểm tra

**1. Directive exports com.example.partner to com.example.crm; cho phép những module nào truy cập package?**

Chỉ module có tên **com.example.crm** được export package đó, với điều kiện consumer đọc được source module và tuân theo các quy tắc truy cập Java thông thường.

**2. Qualified export có tự động thêm requires cho module consumer không?**

Không. Consumer vẫn phải đọc source module, thường bằng directive **requires** trong module-info.java.

**3. Có thể ghi ALL-UNNAMED trong danh sách module sau từ khóa to không?**

Không. **ALL-UNNAMED** là target đặc biệt của tùy chọn dòng lệnh như **--add-exports**, không phải tên module dùng trong qualified export của module descriptor.

**4. Nếu framework cần đọc private field qua reflection thì qualified export có đủ không?**

Không. Deep reflection cần package được mở bằng **opens** hoặc một cơ chế runtime tương ứng như **--add-opens**.

**5. Qualified export có phải cơ chế bảo mật để giới hạn plugin độc hại không?**

Không. Nó kiểm soát khả năng truy cập package giữa module; không thay thế xác thực plugin, sandbox hay kiểm soát quyền ở tầng ứng dụng.

**6. Vì sao nên tách package partner khỏi package implementation?**

Vì qualified export áp dụng cho cả package. Tách package giúp chỉ công khai các type tích hợp cần thiết và giữ implementation ở bên trong module.

## 14. Ghi nhớ

Qualified export là cách module nguồn công khai một package cho một danh sách module đích xác định. Nó hữu ích cho integration đặc thù khi một số adapter hoặc bridge cần API riêng, còn các module khác không cần truy cập package đó.

Hãy đặt directive **exports ... to ...** trong module-info.java của source module, khai báo **requires** ở consumer, và tổ chức package theo đúng bề mặt API cần chia sẻ. Dùng **opens** cho deep reflection và xem **--add-exports** là override runtime/compile-time có chủ đích. Qualified export cải thiện encapsulation, nhưng không thay thế xác thực hay phân quyền bảo mật của ứng dụng.

## Tài liệu tham khảo

- [Java Language Specification — Module Declarations, Exports](https://docs.oracle.com/javase/specs/jls/se21/html/jls-7.html#jls-7.7.2)
- [The Java Module System — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Module.html)
- [The java Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [JEP 261: Module System](https://openjdk.org/jeps/261)
