# Readability graph thay cho classpath visibility

## 1. Vì sao JPMS thay đổi cách tổ chức dependency?

Trong Java truyền thống, ứng dụng thường gom class và JAR vào **classpath**. Class loader tìm bytecode theo đường dẫn, còn code Java import các public type mà compiler có thể tìm thấy và các mức truy cập của ngôn ngữ cho phép. Cấu hình này tiện lợi, nhưng ranh giới giữa các thư viện không được biểu diễn như một cấu trúc dependency tường minh.

Từ Java 9, **Java Platform Module System (JPMS)** bổ sung **named module** và **module descriptor**. Mỗi named module khai báo rõ những module mà nó phụ thuộc, package nào được cung cấp cho bên ngoài và những service nào được sử dụng hoặc cung cấp.

Điểm thay đổi quan trọng là **đồ thị quan hệ đọc — readability graph**. Một named module không tự động sử dụng được mọi type của mọi module chỉ vì các JAR đã được đặt trên module path. Nó phải **đọc được** module chứa type đó, và package chứa type còn phải được **export** phù hợp.

Tư duy tổng quát:

~~~text
Classpath truyền thống
    classpath entries -> class loader tìm class theo đường dẫn
    Không có named module descriptor mô tả phụ thuộc giữa các JAR

JPMS named modules
    module path + root modules -> module resolution -> module graph
    Một module chỉ đọc các module theo quan hệ JPMS hợp lệ
    Truy cập type cần cả readability và accessibility
~~~

Nhờ đó, JPMS làm dependency rõ ràng hơn, tăng khả năng đóng gói và giúp phát hiện một số lỗi cấu trúc ngay khi biên dịch hoặc phân giải module.

## 2. Classpath visibility hoạt động ra sao?

Giả sử classpath chứa các thư viện:

~~~text
lib/
├── customer-api.jar
├── order-service.jar
└── analytics.jar
~~~

Ứng dụng truyền thống được chạy:

~~~bash
java -cp "app.jar:lib/*" com.acme.app.Main
~~~

Trên Windows, dấu phân cách khi chỉ định nhiều path riêng lẻ là dấu chấm phẩy; ký tự wildcard cho thư mục JAR được xử lý theo quy tắc của launcher.

Khi code sử dụng một class, class loader tìm class trong các vị trí được cấu hình. Trong cùng không gian class loader/classpath, một JAR không cần descriptor khai báo rằng nó phụ thuộc vào JAR khác. Vì thế, một public class từ bất kỳ dependency có thể tìm thấy thường có thể được tham chiếu nếu access modifier cho phép.

Ví dụ:

~~~java
package com.acme.app;

import com.acme.customer.api.Customer;
import com.acme.analytics.Report;

public class Main {
    public static void main(String[] args) {
        Customer customer = new Customer("C-1");
        Report.print(customer);
    }
}
~~~

Mã có thể biên dịch khi compiler nhìn thấy các class cần thiết trên classpath. Không có cú pháp tương đương requires trong JAR truyền thống để thể hiện chính xác quan hệ phụ thuộc.

Hệ quả thường gặp:

- Một class có thể vô tình dùng API của dependency bắc cầu thay vì chỉ dependency được khai báo trực tiếp ở build file.
- Classpath có thể chứa nhiều phiên bản class có cùng tên đầy đủ; thứ tự tìm class ảnh hưởng kết quả.
- Việc vô tình gỡ hoặc đổi một thư viện có thể tạo ClassNotFoundException hoặc NoClassDefFoundError lúc chạy.
- Package nội bộ của thư viện dễ bị code ứng dụng sử dụng trực tiếp khi các class của nó là public.

Maven hoặc Gradle vẫn quản lý dependency ở cấp build, nhưng bản thân classpath của JVM không biểu diễn dependency graph có tên module và requires như JPMS.

## 3. Readability graph là gì?

Một **readability graph** biểu diễn quan hệ module nào **đọc được** module nào trong cấu hình JPMS đã được phân giải. Trong module descriptor, quan hệ cơ bản được khai báo bằng chỉ thị **requires**.

Ví dụ:

~~~java
module com.acme.app {
    requires com.acme.order;
}
~~~

~~~java
module com.acme.order {
    requires com.acme.customer;
}
~~~

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

Đồ thị dependency trực tiếp:

~~~text
com.acme.app
    |
    | requires
    v
com.acme.order
    |
    | requires
    v
com.acme.customer
~~~

Với các requires thông thường, app đọc order, còn order đọc customer. **Không được suy luận rằng app tự động đọc customer chỉ vì order đọc customer**. Readability không tự bắc cầu qua mọi cạnh requires.

Đây là sự khác biệt lớn so với một classpath chung, nơi class của customer-api.jar có thể đã sẵn sàng cho cả app và order nếu tất cả cùng được đặt trên classpath.

Để app sử dụng type của customer, có hai lựa chọn thiết kế:

1. App khai báo trực tiếp requires com.acme.customer.
2. Module order sử dụng requires transitive com.acme.customer khi customer là một phần của hợp đồng API mà order cung cấp.

## 4. Readability khác khả năng truy cập package

**Đọc được module (readability)** và **truy cập được type (accessibility)** là hai điều kiện riêng.

Xét module thư viện:

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

Module consumer:

~~~java
module com.acme.app {
    requires com.acme.customer;
}
~~~

Một public type ở com.acme.customer.api có thể được app sử dụng theo luật Java:

~~~java
package com.acme.customer.api;

public record Customer(String id) {
}
~~~

Nhưng một class public trong package chưa export vẫn không phải public API ở cấp module:

~~~java
package com.acme.customer.internal;

public final class CustomerCache {
    public static void clear() {
    }
}
~~~

Nếu com.acme.customer.internal không được export, app không thể truy cập CustomerCache bằng lời gọi Java thông thường chỉ nhờ requires com.acme.customer.

Có thể tóm tắt điều kiện truy cập từ named module A tới type trong named module B:

1. A có quan hệ đọc B.
2. B export package chứa type đó cho A (unqualified hoặc qualified exports).
3. Type và member thỏa mãn các quy tắc access modifier của Java.
4. Type/class có thể được phân giải bởi hệ thống class loading liên quan.

Readability mở đường đến module; exports quyết định package nào đi qua ranh giới đó. Không nên nhầm hai cơ chế này.

## 5. Một dự án mẫu có ba module

Để thấy rõ readability graph, hãy xây dựng ví dụ với các module:

- com.acme.model chứa type Customer.
- com.acme.service dùng Customer và cung cấp service API.
- com.acme.app gọi service API và cần tham chiếu type Customer.

Cấu trúc source tree:

~~~text
project/
├── src/
│   ├── com.acme.model/
│   │   ├── module-info.java
│   │   └── com/acme/model/api/Customer.java
│   ├── com.acme.service/
│   │   ├── module-info.java
│   │   └── com/acme/service/api/CustomerService.java
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
└── mods/
~~~

Trong layout này, src là source root chung, bên dưới có một thư mục cho mỗi named module. File module-info.java nằm tại gốc source của module tương ứng.

Đây là cấu trúc thuận tiện để sử dụng javac --module-source-path và -m.

## 6. Module mô hình dữ liệu

Descriptor của com.acme.model:

~~~java
module com.acme.model {
    exports com.acme.model.api;
}
~~~

Type được export:

~~~java
package com.acme.model.api;

public record Customer(String id, String displayName) {
}
~~~

Vì package com.acme.model.api được export, những module đọc com.acme.model có thể dùng Customer.

Module không cần khai báo requires java.base vì mọi named module có dependency tới java.base theo quy tắc ngầm định của JPMS.

Tuy nhiên, việc package được export chưa đủ để app import Customer. App còn phải đọc được com.acme.model qua quan hệ JPMS.

## 7. Module service với requires thông thường

Bắt đầu từ descriptor:

~~~java
module com.acme.service {
    requires com.acme.model;
    exports com.acme.service.api;
}
~~~

CustomerService:

~~~java
package com.acme.service.api;

import com.acme.model.api.Customer;

public final class CustomerService {
    public Customer findById(String id) {
        return new Customer(id, "Demo Customer");
    }
}
~~~

Module com.acme.service có quyền đọc model vì khai báo requires. Nó export service API nên app có thể dùng public class CustomerService nếu app đọc được service module.

Nhưng method findById trả về type Customer thuộc module model. Với descriptor service chỉ chứa **requires com.acme.model**, một app chỉ requires service sẽ không tự có quan hệ đọc model.

Đây là lý do requires thông thường có thể chưa đủ khi type của dependency xuất hiện trong public API của module đang cung cấp.

## 8. Consumer và lỗi readability

Descriptor ban đầu của app:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

Mã app:

~~~java
package com.acme.app;

import com.acme.model.api.Customer;
import com.acme.service.api.CustomerService;

public class Main {
    public static void main(String[] args) {
        CustomerService service = new CustomerService();
        Customer customer = service.findById("C-42");
        System.out.println(customer.displayName());
    }
}
~~~

App đã khai báo requires service nhưng chưa có quan hệ đọc model. Khi biên dịch, javac có thể báo rằng package com.acme.model.api không visible vì module com.acme.app **does not read** com.acme.model.

Module model có thể có mặt trong cùng lần biên dịch và vẫn được phân giải vì service requires model. Tuy nhiên, **module tồn tại trong configuration không có nghĩa mọi module khác đều đọc được nó**.

Điều này thể hiện điểm cốt lõi của readability graph: quyền nhìn thấy type phải được xác định theo module consumer cụ thể, không phải theo tập JAR hiện diện trên một classpath toàn cục.

## 9. Cách sửa thứ nhất: requires trực tiếp

Nếu app thực sự phụ thuộc trực tiếp vào Customer, có thể khai báo:

~~~java
module com.acme.app {
    requires com.acme.service;
    requires com.acme.model;
}
~~~

Khi đó readability graph:

~~~text
com.acme.app ------requires------> com.acme.service
      |
      +------------requires------> com.acme.model

com.acme.service --requires------> com.acme.model
~~~

App đọc cả hai module; package com.acme.model.api được model export nên app có thể dùng Customer.

Cách này làm dependency trực tiếp thể hiện rõ trong descriptor của app. Nó phù hợp khi app chủ động sử dụng API của model như một dependency riêng, không chỉ vì service module công khai type đó.

Một ứng dụng có thể có nhiều requires trực tiếp. Điều quan trọng không phải giảm số dòng requires bằng mọi giá, mà là mô tả đúng dependency thực tế.

## 10. Cách sửa thứ hai: requires transitive

Nếu module service xem Customer là một phần của **public API contract**, có thể sửa descriptor service:

~~~java
module com.acme.service {
    requires transitive com.acme.model;
    exports com.acme.service.api;
}
~~~

Descriptor app có thể giữ:

~~~java
module com.acme.app {
    requires com.acme.service;
}
~~~

Quan hệ đọc có hiệu lực:

~~~text
com.acme.app
    |
    | requires
    v
com.acme.service
    |
    | requires transitive
    v
com.acme.model

=> com.acme.app đọc được com.acme.model
~~~

Trong JPMS, requires transitive làm module đọc com.acme.service cũng đọc được dependency com.acme.model. Nhờ đó, app dùng type Customer trong public signature của CustomerService mà không cần tự thêm requires model.

Khi một module re-export một phần API của dependency qua các chữ ký public, requires transitive thường diễn đạt đúng hợp đồng hơn requires thông thường.

Không dùng requires transitive cho mọi dependency chỉ để tiện. Nó mở rộng readability graph của các module consumer và làm tăng sự ràng buộc giữa public API với dependency bên ngoài.

## 11. Biên dịch và chạy ví dụ requires transitive

Sau khi có descriptor service dùng requires transitive và descriptor app chỉ requires service, biên dịch:

~~~bash
javac --module-source-path src \
      -d mods \
      -m com.acme.model,com.acme.service,com.acme.app
~~~

Javac đọc module-info.java của từng module, phân giải graph và kiểm tra quyền truy cập type theo các cạnh requires có hiệu lực.

Output điển hình:

~~~text
mods/
├── com.acme.model/
│   ├── module-info.class
│   └── com/acme/model/api/Customer.class
├── com.acme.service/
│   ├── module-info.class
│   └── com/acme/service/api/CustomerService.class
└── com.acme.app/
    ├── module-info.class
    └── com/acme/app/Main.class
~~~

Chạy:

~~~bash
java --module-path mods \
     --module com.acme.app/com.acme.app.Main
~~~

Kết quả:

~~~text
Demo Customer
~~~

Chú ý: javac -m chọn module **để biên dịch**, còn java -m chọn module **để chạy**. Đường dẫn source module thuộc --module-source-path; các module đã biên dịch thuộc --module-path.

Với Windows, ví dụ này chỉ dùng một đường dẫn mods nên không cần phân cách nhiều path entry.

## 12. Readability là quan hệ có hướng

Trong readability graph, nếu module A đọc module B, không có nghĩa B cũng đọc A.

Ví dụ:

~~~text
com.acme.app ----reads----> com.acme.service
~~~

Module app có thể sử dụng API đã export của service. Service module không nhờ vậy có quyền import class của app.

Điều này rất quan trọng trong thiết kế dependency:

- Module tầng trên phụ thuộc vào API tầng dưới.
- Module tầng dưới không nên phụ thuộc ngược vào implementation của tầng trên.
- Nếu cần mở rộng từ module khác, có thể dùng SPI và ServiceLoader thay vì tạo dependency vòng.
- Nếu hai module cần dùng chung một type, đưa type vào module API riêng thay vì làm cả hai phụ thuộc lẫn nhau.

Readability graph giúp nhận diện coupling theo hướng dependency, thuận tiện để xây dựng cấu trúc module theo layer.

## 13. requires static: dependency tùy chọn ở runtime

JPMS còn có cú pháp **requires static**:

~~~java
module com.acme.feature {
    requires static com.acme.annotations;
}
~~~

requires static diễn đạt dependency cần thiết tại thời điểm biên dịch nhưng có thể vắng mặt lúc chạy. Ví dụ thường gặp là các annotation chỉ phục vụ compilation.

Trong khi đó:

~~~java
module com.acme.feature {
    requires com.acme.annotations;
}
~~~

là dependency bắt buộc trong quá trình resolution của module khi chạy.

Có thể kết hợp static và transitive khi một dependency compile-time được phản ánh trong API, nhưng phải cân nhắc khả năng consumer gặp type vắng mặt ở runtime.

Điểm quan trọng: **requires static không biến mọi class của dependency thành tùy ý an toàn khi chạy**. Nếu code runtime thực sự sử dụng type không có mặt, vẫn có thể gặp lỗi liên kết/class loading. Readability và optionality phải phù hợp với hành vi mã thực tế.

## 14. Module path chứa module không có nghĩa module đã được phân giải

Có hai khái niệm độc lập:

- **Observable modules**: các module mà finder/module path có thể quan sát được.
- **Resolved modules**: các module được chọn vào Configuration, dựa trên root modules, dependency requires và có thể cả service binding.

Ví dụ:

~~~text
mods/
├── com.acme.app/
├── com.acme.service/
├── com.acme.model/
└── com.acme.experiments/
~~~

Chạy:

~~~bash
java --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

Không có nghĩa mọi module trong mods đều trở thành root hoặc đều được resolved. Module com.acme.experiments có thể không tham gia graph nếu không được yêu cầu hoặc được bổ sung qua cơ chế resolution khác.

Có thể thêm root module tường minh:

~~~bash
java --module-path mods \
     --add-modules com.acme.experiments \
     -m com.acme.app/com.acme.app.Main
~~~

Nhưng **--add-modules không tự tạo cạnh reads từ app tới experiments**. Nó bổ sung module vào root set, còn quan hệ đọc vẫn theo module descriptor và các quy tắc module system.

Sự khác biệt giữa module **có mặt**, **được phân giải** và **được đọc** là trung tâm của JPMS.

## 15. Qualified exports tiếp tục giới hạn visibility

Ngay cả khi app đọc module service, service có thể chỉ export một package cho một số module đích.

Ví dụ:

~~~java
module com.acme.service {
    exports com.acme.service.api;

    exports com.acme.service.integration
        to com.acme.erp.adapter;
}
~~~

Module app đọc service nhưng không được nêu trong qualified export nên không thể import public type trong com.acme.service.integration theo cách thông thường.

Module com.acme.erp.adapter có thể dùng package integration khi nó đọc service và tên module khớp với danh sách sau to.

Có thể phân biệt:

| Cơ chế | Câu hỏi |
|---|---|
| requires | Module A có khai báo dependency tới B không? |
| requires transitive | Module đọc A có được đọc thêm B qua cạnh transitive không? |
| exports | Package nào của B được các module đọc B truy cập? |
| exports ... to | Package của B chỉ được export tới module đích nào? |
| opens / opens ... to | Package nào được phép deep reflection và với module nào? |

Vì thế không nên diễn đạt readability graph như một cách đơn giản để “nhìn thấy mọi class” trong module khác. Nó là một thành phần của cơ chế encapsulation, không thay thế các quy tắc accessibility.

## 16. Readability với unnamed module trên classpath

Classpath vẫn được Java hỗ trợ. Những class được nạp từ classpath thông thường thuộc **unnamed module** của class loader tương ứng.

Unnamed module có quy tắc readability rộng hơn named module để giữ khả năng tương thích. Tuy nhiên, không nên diễn giải rằng mọi module có trong module path đều tự động xuất hiện và mọi package nội bộ đều được mở.

Ví dụ chạy app legacy trên classpath, còn thư viện mới là named module:

~~~bash
java --module-path mods \
     --add-modules com.acme.service \
     --class-path legacy-app \
     com.acme.legacy.Main
~~~

--add-modules đưa module service vào tập root khi cần. Các package public được service export không giới hạn có thể được code unnamed module truy cập theo quy tắc tương thích, nhưng package không export vẫn được encapsulate.

Nếu một named module muốn đọc unnamed module, đó là tình huống khác: named module không thể khai báo requires một unnamed module trong module-info.java. Việc pha trộn classpath và module path đòi hỏi cân nhắc cấu trúc dependency, và có thể cần --add-reads trong trường hợp tương thích đặc biệt.

Thiết kế lâu dài nên tránh việc code named module phụ thuộc tùy ý vào classpath legacy mà không có kiến trúc rõ ràng.

## 17. Automatic module trong lộ trình migration

Khi một JAR chưa có module-info.class được đặt trên module path, nó có thể được xử lý như **automatic module**.

Automatic module tạo cầu nối cho thư viện cũ:

- Có tên module tự động hoặc tên được chỉ định bằng Automatic-Module-Name.
- Export các package của nó theo cơ chế automatic module.
- Có quy tắc readability rộng hơn explicit named module để hỗ trợ tương thích.

Tuy nhiên, automatic module **không xóa bỏ** toàn bộ quy tắc JPMS. Ví dụ, nhiều automatic modules chứa trùng package có thể gây split-package conflict khi phân giải cùng graph.

Trong quá trình migration, có thể đưa thư viện cũ lên module path như automatic module và từng bước bổ sung module descriptor. Nhưng dependency chính thức trong module-info.java vẫn nên được tổ chức theo module name ổn định.

Không nên phụ thuộc lâu dài vào module name được suy ra tùy ý từ tên file JAR, vì đổi tên artifact có thể làm thay đổi tên module mà requires đang tham chiếu.

## 18. Phân biệt lỗi readability và lỗi class loading

Trong dự án JPMS, không phải mọi lỗi liên quan class đều là cùng một loại.

**Lỗi compile-time về readability**

Ví dụ:

~~~text
package com.acme.model.api is not visible
(module com.acme.app does not read com.acme.model)
~~~

Hướng xử lý: xem requires ở module app, requires transitive ở module cung cấp public API hoặc cấu trúc module graph. Không chỉ thêm JAR vào module path nếu thiếu quan hệ đọc.

**Lỗi package không export**

Ví dụ:

~~~text
package com.acme.model.internal is not visible
(package is declared in module com.acme.model,
 which does not export it)
~~~

Hướng xử lý: sử dụng package API đã export, hoặc thiết kế exports phù hợp. requires đã tồn tại cũng không giải quyết được package không export.

**Lỗi module not found**

Ví dụ:

~~~text
Module com.acme.service not found, required by com.acme.app
~~~

Hướng xử lý: kiểm tra module path, tên module, output/JAR và dependency bắt buộc.

**Lỗi class không tìm thấy**

Có thể xuất hiện ClassNotFoundException hoặc NoClassDefFoundError khi class thực tế không thể được nạp hoặc liên kết tại runtime. Cần kiểm tra nơi chứa class, loader, module layer và dependency runtime tương ứng.

**Lỗi access qua reflection**

InaccessibleObjectException có thể xuất hiện khi framework cố deep reflection vào package của named module chưa được open. Vấn đề này không giống một missing requires thông thường.

## 19. --add-reads là giải pháp tương thích, không thay thế descriptor

Java hỗ trợ tùy chọn:

~~~text
--add-reads source.module=target.module
~~~

Ví dụ:

~~~bash
java --module-path mods \
     --add-modules com.acme.experiments \
     --add-reads com.acme.app=com.acme.experiments \
     -m com.acme.app/com.acme.app.Main
~~~

Trong ví dụ này, --add-reads bổ sung quan hệ đọc từ app tới experiments trong môi trường chạy.

Cần ghi nhớ:

- Module đích phải được phân giải hoặc có sẵn theo cơ chế phù hợp.
- --add-reads không tự export package của module đích.
- --add-reads không tạo hoặc thay file module-info.java.
- Nếu source code cần quyền đọc lúc biên dịch, có thể cần cung cấp tùy chọn phù hợp cho javac ở compile-time.
- Các flag tương thích nên được quản lý nhất quán trong build/test/runtime.

Với dependency ổn định của ứng dụng, khai báo requires trong module-info.java thường rõ ràng và dễ bảo trì hơn việc đặt --add-reads trong nhiều script khởi động.

## 20. Dynamic module layer và readability

Ứng dụng plugin có thể tạo thêm ModuleLayer trong runtime. Mỗi layer gắn với một Configuration gồm các resolved modules và quan hệ reads.

Ví dụ API:

~~~java
ModuleFinder finder =
        ModuleFinder.of(Path.of("plugin-mods"));

Configuration parent =
        ModuleLayer.boot().configuration();

Configuration config = parent.resolve(
        finder,
        ModuleFinder.of(),
        Set.of("com.acme.plugin")
);
~~~

Code trên cần các import tương ứng:

~~~java
import java.lang.module.Configuration;
import java.lang.module.ModuleFinder;
import java.nio.file.Path;
import java.util.Set;
~~~

Module được phân giải trong layer mới dựa trên root modules và requires. Module plugin không được truy cập một named module tùy ý chỉ vì nó có mặt ở plugin-mods.

Có thể tạo layer từ configuration:

~~~java
ModuleLayer pluginLayer =
        ModuleLayer.boot().defineModulesWithOneLoader(
                config,
                ClassLoader.getSystemClassLoader()
        );
~~~

Khi dùng nhiều layer, còn cần kiểm tra parent layer, class loader chứa service API và module thực sự được resolved. Readability tiếp tục có ý nghĩa đối với mỗi named module trong graph.

Không xem ModuleLayer như một classpath tự do được tạo lại với các tên khác; nó vẫn thực thi ranh giới JPMS.

## 21. Readability với ServiceLoader

ServiceLoader bổ sung một loại quan hệ động: consumer cần service contract, còn provider có thể được tìm thông qua metadata service.

Ví dụ consumer:

~~~java
module com.acme.app {
    requires com.acme.payment.api;
    uses com.acme.payment.api.PaymentGateway;
}
~~~

Provider:

~~~java
module com.acme.payment.provider {
    requires com.acme.payment.api;
    provides com.acme.payment.api.PaymentGateway
        with com.acme.payment.provider.CardGateway;
}
~~~

Consumer không nhất thiết phải requires module provider. Nó có thể chỉ requires service API và khai báo uses. Module provider cần được phân giải vào layer và đăng ký provides hợp lệ để ServiceLoader tìm thấy.

Đây không phải hành vi “mọi module đều nhìn thấy mọi class”. Consumer vẫn thao tác qua type PaymentGateway của module API, không cần import class CardGateway nằm trong provider package.

Đối với ModuleLayer tùy chỉnh, Configuration.resolveAndBind có thể đưa provider modules vào graph theo các metadata uses/provides. Cách này khác việc thêm requires trực tiếp tới từng implementation và giữ dependency inversion ở cấp module.

## 22. Quan sát graph bằng công cụ JDK

Khi chạy modular application, dùng:

~~~bash
java --show-module-resolution \
     --module-path mods \
     -m com.acme.app/com.acme.app.Main
~~~

Lệnh giúp quan sát root modules, dependency resolution và các module được phân giải. Nếu module không xuất hiện trong configuration, hãy kiểm tra module path và roots trước khi suy luận về accessibility.

Để xem descriptor của một modular JAR:

~~~bash
jar --describe-module --file dist/com.acme.service.jar
~~~

Để xem module-info.class của exploded module:

~~~bash
javap -p -v mods/com.acme.service/module-info.class
~~~

Thông tin cần đối chiếu:

- requires hay requires transitive?
- Package được exports hay chỉ exports ... to một module cụ thể?
- Tên module trong requires có đúng không?
- Module phụ thuộc có thật trên module path và đã được phân giải không?
- Có module phụ thuộc thiếu hoặc split package conflict không?

Có thể dùng jdeps để phân tích dependency ở mức bytecode:

~~~bash
jdeps --list-deps --module-path mods \
      --module com.acme.app
~~~

jdeps hỗ trợ nhận diện dependency; kết quả không thay thế việc đọc module descriptor và hiểu contract API. Những class được nạp động bằng reflection/service có thể không được biểu diễn đầy đủ trong phân tích tĩnh.

## 23. So sánh trực tiếp classpath visibility và readability graph

| Khía cạnh | Classpath truyền thống | Named modules / JPMS |
|---|---|---|
| Đầu vào | Danh sách thư mục/JAR | Module path và tập module roots |
| Đơn vị phụ thuộc | Chủ yếu class/JAR do build tool sắp xếp | Named module trong module graph |
| Khai báo dependency trong ngôn ngữ | Không có requires | module-info.java với requires |
| Type public của thư viện | Thường khả dụng khi class loader tìm thấy và access cho phép | Cần readability + exports + Java access |
| Dependency bắc cầu | Các class có thể cùng hiển thị trong classpath | Chỉ lan truyền readability theo quy tắc phù hợp, như requires transitive |
| Internal public package | Có thể bị consumer dùng trực tiếp | Có thể giữ kín nếu không export |
| Định danh phụ thuộc | JAR/path và class name | Module name, descriptor và module graph |
| Tìm class | Class loader và thứ tự search | Module resolution kết hợp class loading |
| Service discovery | Thường META-INF/services | uses/provides và ServiceLoader, cùng cơ chế tương thích |

Bảng trên mô tả sự khác biệt thường gặp khi chuyển từ classpath sang named modules. JVM vẫn dùng class loader để nạp bytecode trong JPMS; readability graph **bổ sung quy tắc truy cập ở cấp module**, không thay thế hoàn toàn class loading.

## 24. Nguyên tắc thiết kế dependency graph

Một module graph dễ bảo trì thường có các đặc điểm:

1. **Khai báo rõ dependency thực sự** bằng requires.
2. **Dùng requires transitive có chủ đích** khi API export của module chứa type đến từ dependency.
3. **Chỉ export package cần dùng bên ngoài**, giữ implementation package nội bộ.
4. **Dùng qualified exports** cho integration được kiểm soát thay vì mở rộng public API.
5. **Tách service API khỏi provider implementation**, dùng uses/provides khi cần khả năng thay thế provider.
6. **Không dựa vào JAR hiện diện trên module path** để suy ra module nào đã resolved hoặc readable.
7. **Giảm dependency vòng**; đưa hợp đồng chung vào module API nếu cần.
8. **Không sử dụng --add-reads như cấu hình chính lâu dài** nếu có thể sửa descriptor.
9. **Kiểm tra compile-time và runtime module paths** đều có dependency phù hợp.
10. **Dùng công cụ quan sát module resolution** trước khi sửa các lỗi visibility.

Khi migration từ classpath, nên đi theo từng bước: liệt kê các JAR cần thiết, xác định module name, viết descriptor, xử lý split package, giới hạn exports, sau đó giải quyết missing requires hoặc các dependency bắc cầu thực sự cần cho public API.

## 25. Bài tập thực hành

**Bài 1 – requires trực tiếp**

Với ba module app, service và model, giữ requires thông thường trong service. Hãy thêm requires model vào app để code import Customer biên dịch. Ghi lại readability edges trực tiếp của app.

**Bài 2 – requires transitive**

Xóa requires model khỏi app, đổi module service thành requires transitive model. Biên dịch lại và giải thích vì sao app vẫn truy cập được Customer.

**Bài 3 – đóng package nội bộ**

Thêm một public class vào com.acme.model.internal nhưng không export package này. Thử import từ app. Quan sát sự khác biệt giữa lỗi package không export và lỗi thiếu quan hệ đọc.

**Bài 4 – module có mặt nhưng chưa resolved**

Đặt thêm một named module không được requires vào mods. Chạy app và xem --show-module-resolution. Sau đó dùng --add-modules để quan sát sự khác biệt giữa observable và resolved.

**Bài 5 – phân tích lỗi**

Nếu javac báo module app does not read model nhưng developer nói “model.jar đã có trên module path”, hãy giải thích vì sao câu trả lời đó chưa giải quyết lỗi và nêu cách sửa descriptor thích hợp.

Các bài tập nhằm phân biệt chính xác ba khái niệm: **module có thể tìm thấy**, **module đã được phân giải** và **module consumer có quyền đọc**.

## 26. Ghi nhớ

- Classpath truyền thống ưu tiên khả năng tìm class qua class loader; các JAR trong cùng classpath không có dependency descriptor ở cấp JPMS.
- Readability graph trong JPMS mô tả named module nào đọc named module nào.
- requires tạo một quan hệ đọc; requires thông thường không tự làm quan hệ đọc bắc cầu tới mọi consumer.
- requires transitive làm readability lan truyền cho module đọc module khai báo khi dependency là một phần của API.
- requires static mô tả dependency cần ở compile-time nhưng có thể vắng mặt ở runtime, không bảo đảm mọi lời gọi runtime đều an toàn.
- **Readability và exports là hai điều kiện khác nhau**: đọc được module không đồng nghĩa truy cập được mọi package của module đó.
- Module xuất hiện trên module path chưa chắc đã là resolved root hoặc readable từ module consumer.
- Package nội bộ không export giúp named module giữ ranh giới encapsulation ngay cả khi class của nó public.
- Unnamed module và automatic module có quy tắc tương thích riêng; không đánh đồng chúng với explicit named module.
- --add-reads là công cụ tương thích bổ sung read edge tạm thời, không sửa descriptor và không tự export package.
- ServiceLoader cho phép consumer dùng service contract thay vì trực tiếp phụ thuộc provider module.
- --show-module-resolution, jar --describe-module và javap giúp chẩn đoán dependency graph.

**Kết luận:** JPMS chuyển cách tư duy từ “class có nằm đâu đó trên classpath không?” sang “module consumer có quan hệ đọc hợp lệ tới module cung cấp type và package có được export không?”. Readability graph làm dependency tường minh hơn, còn exports và access modifier quyết định ranh giới API. Nắm rõ sự phân tách đó là nền tảng để thiết kế, biên dịch và vận hành ứng dụng modular Java.