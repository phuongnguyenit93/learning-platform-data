# Package không export và tính đóng gói

Trong JPMS, package là đơn vị mà một module có thể công bố ra bên ngoài. Một package có thể chứa class public nhưng vẫn không được module khác truy cập nếu module sở hữu nó không khai báo **exports**. Quy tắc này giúp module giữ lại phần implementation bên trong và chỉ đưa những package thực sự thuộc API ra cho consumer.

Học cách dùng package không export là bước quan trọng để hiểu tính đóng gói của JPMS. Cần phân biệt quyền truy cập ở cấp ngôn ngữ Java với quyền truy cập ở cấp module: modifier **public** trên class không tự động làm package trở thành API công khai của module.

## 1. Package không export có ý nghĩa gì?

Một named module được mô tả bằng **module-info.java**. Directive **exports** chỉ định package mà module cho phép các module khác truy cập như API.

Ví dụ:

~~~java
module com.acme.billing {
    exports com.acme.billing.api;
}
~~~

Giả sử module có các package:

~~~text
com.acme.billing
├── module-info.java
└── com/acme/billing
    ├── api/
    │   └── InvoiceService.java
    └── internal/
        ├── InvoiceRepository.java
        └── InvoiceCalculator.java
~~~

Ở đây, module chỉ export **com.acme.billing.api**. Package **com.acme.billing.internal** không được export nên code thuộc module khác không thể sử dụng các kiểu trong package đó như một API Java thông thường.

Điều này vẫn đúng nếu class trong package nội bộ được khai báo **public**:

~~~java
package com.acme.billing.internal;

public class InvoiceCalculator {
    public long calculateTotal(long subtotal, long tax) {
        return subtotal + tax;
    }
}
~~~

Modifier **public** cho biết mức truy cập của class theo quy tắc ngôn ngữ Java. JPMS bổ sung một lớp kiểm soát: module chứa package đó có công bố package cho module gọi hay không. Vì package **com.acme.billing.internal** chưa được export, một named module khác không thể import và sử dụng **InvoiceCalculator** chỉ bằng cách khai báo **requires com.acme.billing**.

## 2. Kết hợp readability và exports

Để module ứng dụng sử dụng API của module billing, nó cần khai báo dependency:

~~~java
module com.acme.application {
    requires com.acme.billing;
}
~~~

Code của ứng dụng có thể dùng kiểu trong package đã export:

~~~java
package com.acme.application;

import com.acme.billing.api.InvoiceService;

public class Checkout {
    private final InvoiceService invoiceService;

    public Checkout(InvoiceService invoiceService) {
        this.invoiceService = invoiceService;
    }
}
~~~

Nếu ứng dụng cố import class trong package nội bộ:

~~~java
import com.acme.billing.internal.InvoiceCalculator;
~~~

compiler sẽ báo package hoặc kiểu không được truy cập vì module **com.acme.billing** không export package đó cho **com.acme.application**.

Hai điều kiện cần được hiểu riêng:

1. **Readability:** module gọi phải đọc module cung cấp kiểu, thường thông qua directive **requires**.
2. **Accessibility at module boundary:** package chứa kiểu phải được module cung cấp export cho module gọi.

Có **requires** không có nghĩa module gọi được truy cập mọi package của dependency. **requires** tạo quan hệ phụ thuộc và readability; **exports** quyết định package nào được công bố.

## 3. Tính đóng gói có hai lớp

Java đã có các mức truy cập của ngôn ngữ:

- **private:** thành viên chỉ được truy cập trong phạm vi class theo quy tắc Java.
- **package-private:** thành viên không khai báo modifier chỉ được truy cập trong cùng package.
- **protected:** cho phép truy cập theo quy tắc package và kế thừa.
- **public:** cho phép truy cập theo quy tắc Java, với điều kiện các ranh giới module liên quan cũng cho phép.

JPMS bổ sung ranh giới module ở phía ngoài các quy tắc đó. Một kiểu public trong package không export vẫn không thể được named module bên ngoài dùng như API.

| Lớp kiểm soát | Câu hỏi được trả lời | Cơ chế |
|---|---|---|
| Thành viên và kiểu Java | Class hoặc thành viên có public, protected, package-private hay private? | Access modifier của Java |
| Phụ thuộc module | Module hiện tại có đọc module cung cấp kiểu không? | **requires**, **requires transitive** |
| Công bố package | Package có được mở cho truy cập Java thông thường từ module khác không? | **exports** |
| Deep reflection | Module framework có thể truy cập thành viên không public bằng reflection không? | **opens** |

Vì vậy, tính đóng gói của JPMS không thay thế modifier Java. Nó bổ sung một ranh giới ở cấp package/module, giúp tác giả module kiểm soát bề mặt API trước khi các quy tắc truy cập của class và thành viên được áp dụng.

## 4. Code bên trong module vẫn dùng package không export

Package không export không phải package bị vô hiệu hóa. Các class thuộc cùng module vẫn có thể sử dụng nhau theo quy tắc truy cập Java thông thường.

Ví dụ, **InvoiceService** là API công khai của module và có thể gọi implementation nội bộ:

~~~java
package com.acme.billing.api;

import com.acme.billing.internal.InvoiceCalculator;

public class InvoiceService {
    private final InvoiceCalculator calculator =
        new InvoiceCalculator();

    public long total(long subtotal, long tax) {
        return calculator.calculateTotal(subtotal, tax);
    }
}
~~~

Đoạn code trên hợp lệ khi cả hai package thuộc cùng module **com.acme.billing**. Package **internal** không cần export để code cùng module truy cập nó.

Thiết kế này tạo ra một đường sử dụng rõ ràng:

- Consumer phụ thuộc vào **com.acme.billing.api**.
- API của module gọi implementation trong **com.acme.billing.internal**.
- Consumer không phụ thuộc trực tiếp vào class triển khai.
- Tác giả module có thể thay đổi hoặc thay thế implementation nội bộ mà không phải giữ tương thích cho consumer bên ngoài.

Không export một package cũng không có nghĩa class hoặc file trong package đó bị xóa khỏi JAR. Các class vẫn được biên dịch và đóng gói; module system kiểm soát khả năng truy cập giữa các module.

## 5. Export toàn package và qualified exports

Nếu một package cần được dùng bởi mọi module đọc module hiện tại, có thể dùng export không giới hạn:

~~~java
module com.acme.billing {
    exports com.acme.billing.api;
}
~~~

Nếu package chỉ phục vụ một consumer cụ thể, có thể dùng **qualified exports**:

~~~java
module com.acme.billing {
    exports com.acme.billing.api;
    exports com.acme.billing.internal.spi
        to com.acme.application;
}
~~~

Trong ví dụ này:

- Các module đọc **com.acme.billing** có thể truy cập package **com.acme.billing.api**.
- Chỉ module **com.acme.application** được truy cập package **com.acme.billing.internal.spi**.
- Những module khác vẫn không được dùng package SPI này như API.

Qualified exports phù hợp với SPI nội bộ giữa các module trong cùng một hệ thống, hoặc với một framework/module được chỉ định cần gọi một package hỗ trợ. Tên module đích phải khớp với tên module thực tế trong descriptor của consumer.

Không nên dùng qualified exports chỉ để né một lỗi phụ thuộc chưa được hiểu rõ. Hãy xác định module nào thực sự cần package và vì sao package đó phải trở thành một phần hợp đồng giữa hai module.

## 6. Package không export và reflection

Reflection có quy tắc riêng khi đi qua ranh giới module. Một framework có thể cần truy cập field, constructor hoặc method không public để ánh xạ object, serialize dữ liệu hoặc inject dependency.

**exports** chủ yếu cho phép truy cập API Java thông thường. Để cho phép deep reflection vào package nội bộ, module có thể khai báo **opens**:

~~~java
module com.acme.billing {
    exports com.acme.billing.api;
    opens com.acme.billing.internal to com.acme.orm;
}
~~~

Module **com.acme.orm** được phép deep reflection vào các kiểu thuộc package **com.acme.billing.internal** tại runtime. Package này vẫn không trở thành package có thể import tự do khi biên dịch.

Các hình thức mở package:

| Directive | Phạm vi |
|---|---|
| **opens package.name;** | Mở package cho deep reflection từ các module khác tại runtime. |
| **opens package.name to framework.module;** | Chỉ mở package cho module được chỉ định. |
| **open module module.name { ... }** | Mở tất cả package của module cho deep reflection tại runtime. |

Nếu framework gọi **setAccessible(true)** trên thành viên không public của một package chưa mở phù hợp, JVM có thể ném **InaccessibleObjectException**. Với **trySetAccessible()**, kết quả có thể là **false** khi quyền truy cập không được phép. Các API như **MethodHandles.privateLookupIn** cũng phải tuân theo điều kiện mở package và readability tương ứng.

Hãy mở đúng package cho đúng framework. Mở toàn module bằng **open module** có phạm vi rộng hơn và làm giảm lợi ích của việc giữ implementation nội bộ.

## 7. Ví dụ hoàn chỉnh: API công khai và implementation nội bộ

Giả sử module billing cung cấp chức năng tính tổng hóa đơn. API public không để lộ class calculator:

~~~java
// module-info.java
module com.acme.billing {
    exports com.acme.billing.api;
}
~~~

~~~java
// com/acme/billing/api/InvoiceService.java
package com.acme.billing.api;

import com.acme.billing.internal.InvoiceCalculator;

public class InvoiceService {
    private final InvoiceCalculator calculator =
        new InvoiceCalculator();

    public long total(long subtotal, long tax) {
        return calculator.calculateTotal(subtotal, tax);
    }
}
~~~

~~~java
// com/acme/billing/internal/InvoiceCalculator.java
package com.acme.billing.internal;

public class InvoiceCalculator {
    public long calculateTotal(long subtotal, long tax) {
        return subtotal + tax;
    }
}
~~~

Module ứng dụng chỉ khai báo dependency và dùng API:

~~~java
// module-info.java
module com.acme.application {
    requires com.acme.billing;
}
~~~

~~~java
// com/acme/application/Main.java
package com.acme.application;

import com.acme.billing.api.InvoiceService;

public class Main {
    public static void main(String[] args) {
        InvoiceService service = new InvoiceService();
        System.out.println(service.total(1000, 80));
    }
}
~~~

Ứng dụng có thể biên dịch và chạy vì **com.acme.billing.api** đã được export. Nếu thay import trong ứng dụng bằng **com.acme.billing.internal.InvoiceCalculator**, compiler sẽ từ chối truy cập package nội bộ.

Đây là cách dùng encapsulation để giữ implementation có thể thay đổi độc lập với consumer. Consumer biết contract **InvoiceService**; module billing sở hữu cách tính toán và các class hỗ trợ bên trong.

## 8. Khi nào cần tạm mở package từ dòng lệnh?

Trong giai đoạn chuyển đổi ứng dụng cũ hoặc điều tra lỗi, đôi khi cần cấp quyền truy cập tạm thời mà chưa muốn sửa descriptor ngay. JDK cung cấp các tùy chọn launcher/compiler:

- **--add-exports** bổ sung quyền export package cho module đích.
- **--add-opens** bổ sung quyền mở package cho deep reflection tại runtime.

Ví dụ, cấp quyền truy cập Java thông thường vào package nội bộ cho một module công cụ:

~~~bash
java --module-path mods   --add-exports com.acme.billing/com.acme.billing.internal=com.acme.tools   -m com.acme.tools/com.acme.tools.Inspector
~~~

Ví dụ, mở package cho reflection từ framework:

~~~bash
java --module-path mods   --add-opens com.acme.billing/com.acme.billing.internal=com.acme.orm   -m com.acme.application/com.acme.application.Main
~~~

Nếu consumer nằm trên classpath, có thể dùng đích **ALL-UNNAMED**. Khi biên dịch code cần truy cập package, tùy chọn **--add-exports** cũng có thể được truyền cho **javac**.

Các tùy chọn này hữu ích cho migration, kiểm thử hoặc chẩn đoán. Khi đã xác định được quan hệ cần thiết, hãy cân nhắc đưa quyền truy cập phù hợp vào descriptor bằng **exports**, qualified exports hoặc **opens**. Không nên duy trì một danh sách mở rộng tùy tiện vì nó khiến ranh giới module khó hiểu và khó kiểm soát.

## 9. Service provider có thể nằm trong package không export

Một trường hợp hữu ích là module cung cấp implementation của service nhưng không muốn consumer phụ thuộc vào package chứa provider.

Ví dụ module plugin:

~~~java
module com.acme.csv.exporter {
    requires com.acme.report.spi;

    provides com.acme.report.spi.ReportExporter
        with com.acme.csv.internal.CsvReportExporter;
}
~~~

Package **com.acme.csv.internal** có thể không export. Module ứng dụng chỉ cần đọc module SPI và khai báo **uses** service tương ứng. Nó tìm provider qua **ServiceLoader**, không cần import class triển khai.

Điều này giúp giữ implementation provider ở bên trong module. Consumer chỉ biết interface **ReportExporter**, còn provider có thể thay đổi class hoặc package triển khai mà không làm lộ chi tiết đó ra ngoài.

Để cơ chế hoạt động, provider phải tuân thủ quy tắc provider của JPMS/ServiceLoader, module chứa provider phải được resolve vào layer được tìm kiếm, và service type phải là cùng một kiểu API mà host sử dụng.

## 10. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Compiler báo package không visible dù đã có **requires** | Module dependency không export package cần dùng. | Kiểm tra **exports** hoặc qualified exports trong descriptor của module cung cấp. |
| Class public vẫn không import được | Public chỉ giải quyết quyền truy cập ở cấp Java; package chưa được export. | Export đúng package API hoặc thiết kế lại consumer để dùng API đã công bố. |
| Framework ném **InaccessibleObjectException** | Package cần deep reflection chưa được mở cho framework. | Dùng **opens package to framework.module** hoặc cấu hình **--add-opens** có giới hạn. |
| Module A dùng được API nhưng module B không dùng được | Qualified export chỉ cho phép module đích đã chỉ định. | Kiểm tra tên module consumer trong directive **exports ... to ...**. |
| Consumer phụ thuộc vào class implementation | Implementation đã bị đưa vào package API hoặc package nội bộ bị export quá rộng. | Đưa implementation về package không export và công bố interface/facade ổn định. |
| ServiceLoader không tìm thấy provider | Provider module chưa được resolve hoặc descriptor khai báo sai service/provider. | Kiểm tra **uses**, **provides**, service type và layer được tìm kiếm. |

Khi debug, hãy xác định lỗi thuộc lớp nào: Java access modifier, readability, export hay deep reflection. Sau đó kiểm tra đúng descriptor và module đích. Thêm quyền mở rộng chỉ để làm lỗi biến mất có thể che khuất thiết kế phụ thuộc chưa hợp lý.

## 11. Bài tập thực hành

1. Tạo module **com.acme.billing** với hai package **api** và **internal**. Chỉ export package **api**.
2. Tạo module **com.acme.application** khai báo **requires com.acme.billing**. Dùng một class public trong package API và chạy ứng dụng.
3. Thử import một class public thuộc package **internal** từ ứng dụng. Quan sát lỗi compiler và giải thích vì sao modifier public chưa đủ.
4. Chuyển lời gọi implementation vào một facade trong package API. Xác nhận ứng dụng không cần biết class nội bộ.
5. Thêm một module framework mô phỏng reflection. So sánh hành vi khi package nội bộ chưa có **opens** và khi package được mở có giới hạn.
6. Tạo service interface trong module SPI và provider trong package không export. Tìm provider bằng **ServiceLoader** từ ứng dụng.
7. Thử **exports package to module** với một consumer được chỉ định, sau đó đổi tên module consumer để quan sát lỗi truy cập.
8. Dùng **--add-exports** hoặc **--add-opens** trong một lần chạy chẩn đoán, rồi chuyển quyền cần thiết vào descriptor nếu đó là hợp đồng lâu dài.

## 12. Nguyên tắc thiết kế nên ghi nhớ

- Export package có nghĩa là chấp nhận package đó làm một phần bề mặt API của module.
- Class public trong package không export vẫn có thể là implementation nội bộ.
- Code trong cùng module vẫn sử dụng package không export theo quy tắc Java thông thường.
- **requires** và **exports** giải quyết hai câu hỏi khác nhau: module có đọc dependency hay không, và package nào của dependency được công bố.
- **opens** phục vụ deep reflection tại runtime; nó không thay thế exports cho việc import API khi biên dịch.
- Qualified exports/opens nên chỉ rõ module thực sự cần quyền.
- Package nội bộ không phải sandbox bảo mật; nó là ranh giới encapsulation của Java module system.

Khi thiết kế module, hãy bắt đầu từ API mà consumer cần dùng, export những package đó, rồi giữ các package triển khai ở trạng thái không export. Cách tổ chức này giúp giảm coupling, giữ quyền thay đổi implementation và làm cho hợp đồng giữa các module rõ ràng hơn.