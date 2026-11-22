# Named module và module identity

Trong Java Platform Module System (JPMS), **named module** là module có tên xác định. Tên này được khai báo trong module descriptor hoặc được suy ra khi một thư viện cũ trở thành automatic module. Tên module giúp module system nhận diện dependency và giải quyết đồ thị module.

Khi chương trình chạy, mỗi module được định nghĩa trong một runtime environment còn có đối tượng **java.lang.Module** đại diện. Đối tượng này cung cấp thông tin về tên, descriptor, class loader và ModuleLayer liên quan. Vì vậy, cần phân biệt tên module trong descriptor với danh tính của module object tại runtime, đồng thời không nhầm module identity với Maven coordinates hay class identity.

## 1. Named module là gì?

Named module là module có tên. Với explicit named module, tên được khai báo trực tiếp trong file **module-info.java** ở thư mục gốc của source module.

Ví dụ:

~~~java
module com.acme.orders {
    requires java.logging;
    requires com.acme.customer;

    exports com.acme.orders.api;
}
~~~

Tên module ở đây là **com.acme.orders**. Descriptor cũng khai báo dependency và package được công bố. Khi biên dịch, compiler tạo **module-info.class**; file này được đặt ở gốc thư mục module đã biên dịch hoặc ở gốc modular JAR.

Ví dụ cấu trúc source:

~~~text
src/
└── com.acme.orders/
    ├── module-info.java
    └── com/acme/orders/
        ├── api/
        │   └── OrderService.java
        └── internal/
            └── OrderRepository.java
~~~

Tên module thường dùng quy ước đảo ngược tên miền, chẳng hạn **com.acme.orders** hoặc **org.example.reporting**. Đây là quy ước đặt tên, không phải một yêu cầu bắt buộc phải sở hữu tên miền tương ứng. Tên module phân biệt chữ hoa/chữ thường và không phải tên package được suy ra tự động từ mọi thư mục source.

Một explicit named module có các đặc điểm:

- Có module descriptor thực sự được biên dịch từ **module-info.java**.
- Có tên module do tác giả khai báo.
- Có thể khai báo dependency bằng **requires**.
- Có thể công bố package bằng **exports** và mở package cho reflection bằng **opens**.
- Có thể khai báo service dependency và provider bằng **uses** và **provides**.

## 2. Named module khác unnamed module

Không phải mọi code Java đều thuộc named module. Code được nạp từ classpath thuộc **unnamed module** gắn với class loader đã nạp code đó.

| Đặc điểm | Named module | Unnamed module |
|---|---|---|
| Tên module | Có tên, ví dụ **com.acme.orders** | Không có tên; **Module.getName()** trả về **null** |
| Descriptor | Có descriptor tường minh hoặc descriptor tự động của automatic module | Không có module descriptor |
| Nguồn thường gặp | Module path, system modules | Classpath |
| Khai báo **requires** | Có thể khai báo trong descriptor | Không khai báo bằng **module-info.java** |
| Kiểm soát package | Package được export/open theo descriptor và quy tắc module | Các package của unnamed module được xem là export và open cho các module khác |

Mỗi class loader có một unnamed module riêng. Do đó, hai class loader khác nhau có thể có hai unnamed module khác nhau, dù cả hai đều không có tên.

Code trên classpath không trở thành named module chỉ vì nó gọi một API trong named module. Tương tự, việc thêm một thư viện vào classpath không làm xuất hiện một module name ổn định cho thư viện đó.

## 3. Explicit named module và automatic module

Cần phân biệt hai loại named module thường gặp.

### 3.1. Explicit named module

Đây là module có **module-info.class** được đóng gói cùng code. Tác giả chủ động khai báo tên, dependency và ranh giới package.

~~~java
module com.acme.customer {
    exports com.acme.customer.api;
}
~~~

Khi modular JAR được đặt trên module path, module system đọc descriptor này để nhận diện module. Tên module trong descriptor là tên có thẩm quyền; tên file JAR không quyết định tên module.

Có thể xem descriptor bằng:

~~~bash
jar --describe-module --file customer-api.jar
~~~

### 3.2. Automatic module

Một JAR cũ không có **module-info.class** vẫn có thể được xem là named module khi đặt trên module path. Module system tạo descriptor tự động cho JAR đó; loại module này được gọi là **automatic module**.

Tên automatic module được xác định theo thứ tự:

1. Nếu manifest có thuộc tính **Automatic-Module-Name**, dùng tên ổn định được khai báo ở đó.
2. Nếu không có thuộc tính này, tên được suy ra từ tên file JAR theo quy tắc đặt tên automatic module.

Ví dụ manifest:

~~~text
Automatic-Module-Name: com.acme.legacy.csv
~~~

Automatic module vẫn có tên và có thể được một named module khác khai báo trong **requires**. Tuy nhiên, descriptor của nó được tạo tự động, không thể hiện đầy đủ ý định encapsulation như explicit descriptor. Automatic module xuất toàn bộ package của nó và có quy tắc readability rộng để hỗ trợ chuyển đổi.

Vì thế, automatic module là cầu nối tương thích hữu ích khi đưa thư viện cũ lên module path. Khi có thể sửa hoặc đóng gói lại thư viện, explicit named module thường giúp kiểm soát dependency và package rõ ràng hơn.

## 4. Module name là định danh, không phải phiên bản thư viện

Tên **com.acme.orders** nhận diện module trong module descriptor và trong quá trình resolve. Nó không đồng nghĩa với:

- Tên file JAR.
- Maven groupId hoặc artifactId.
- Phiên bản dependency.
- Đường dẫn file trên đĩa.
- Tên package gốc của mọi class trong module.

Ví dụ, build tool có thể quản lý artifact bằng tọa độ:

~~~groovy
dependencies {
    implementation 'com.acme:orders-api:2.1.0'
}
~~~

Trong khi descriptor của artifact có tên module:

~~~java
module com.acme.orders {
    exports com.acme.orders.api;
}
~~~

Build tool chọn artifact và phiên bản cần dùng. JPMS sử dụng tên module cùng descriptor để thiết lập quan hệ module. Hai tên có thể liên quan theo quy ước dự án, nhưng không phải cùng một hệ thống định danh.

Module descriptor có thể mang metadata phiên bản trong một số quy trình đóng gói, nhưng tên module vẫn là một trường riêng. Directive **requires com.acme.orders** không phải khai báo dải phiên bản và module system không thay thế cơ chế chọn phiên bản của Maven hoặc Gradle.

Đặt tên module ổn định đặc biệt quan trọng với thư viện. Với automatic module, hãy khai báo **Automatic-Module-Name** trong manifest để tên không thay đổi chỉ vì tên file JAR được đổi.

## 5. Module name và runtime module identity

Khi một class loader định nghĩa module, JVM tạo một đối tượng **java.lang.Module** đại diện cho module đó. Có thể lấy module object từ một class:

~~~java
Module module = OrderService.class.getModule();

System.out.println(module.isNamed());
System.out.println(module.getName());
System.out.println(module.getDescriptor());
System.out.println(module.getLayer());
System.out.println(module.getClassLoader());
~~~

Các thông tin thường dùng:

| API | Thông tin |
|---|---|
| **Module.isNamed()** | Cho biết module có phải named module hay không. |
| **Module.getName()** | Trả về tên module; trả về **null** với unnamed module. |
| **Module.getDescriptor()** | Trả về descriptor của named module; unnamed module không có descriptor. |
| **Module.getLayer()** | Trả về ModuleLayer định nghĩa module; unnamed module không thuộc một named module layer nên kết quả là **null**. |
| **Module.getClassLoader()** | Trả về class loader định nghĩa module; có thể là **null** nếu module được định nghĩa bởi bootstrap class loader. |
| **Module.getPackages()** | Trả về tập tên package thuộc module. |
| **Module.canRead(other)** | Kiểm tra module hiện tại có readability tới module khác hay không. |
| **Module.isExported(packageName, other)** | Kiểm tra package có được export cho module đích hay không. |
| **Module.isOpen(packageName, other)** | Kiểm tra package có được mở cho deep reflection từ module đích hay không. |

Ví dụ, nếu **OrderService** thuộc explicit named module **com.acme.orders**, các giá trị có thể cho biết tên module, descriptor và layer đã định nghĩa class. Nếu class nằm trên classpath, **isNamed()** là **false** và **getName()** trả về **null**.

Module object là đại diện runtime có thể dùng để kiểm tra quan hệ module. Trong code cần so sánh hoặc lưu một module runtime cụ thể, đừng chỉ lưu tên string rồi mặc định tên đó là một handle toàn cục. Hãy xét chính đối tượng **Module**, layer và class loader đã định nghĩa nó.

## 6. Vai trò của ModuleLayer đối với identity

**ModuleLayer** là môi trường runtime chứa các module đã được resolve và định nghĩa. JVM tạo boot layer khi khởi chạy ứng dụng; có thể truy cập layer này bằng:

~~~java
ModuleLayer boot = ModuleLayer.boot();
~~~

Có thể tìm một module trong layer:

~~~java
Module ordersModule = boot
    .findModule("com.acme.orders")
    .orElseThrow(() ->
        new IllegalStateException("Module not found"));
~~~

Một layer có thể có layer cha. Các module trong layer con có thể đọc module ở layer cha theo dependency đã resolve. Layer cũng liên kết các module với class loader được dùng để định nghĩa chúng.

Khi ứng dụng dùng nhiều layer độc lập, không nên giả định một tên module string luôn là định danh runtime duy nhất trong toàn bộ tiến trình. Hãy xem module object và layer/class loader liên quan để xác định module đang được nói tới. Cách này đặc biệt hữu ích khi xây dựng plugin, nơi các nhóm module có thể được resolve và định nghĩa riêng trong những layer khác nhau.

Một số API thường dùng:

~~~java
ModuleLayer layer = ModuleLayer.boot();

layer.modules().forEach(module -> {
    System.out.println(module.getName());
    System.out.println(module.getClassLoader());
});
~~~

- **ModuleLayer.boot()** lấy boot layer.
- **ModuleLayer.modules()** trả về các module được định nghĩa trực tiếp trong layer đó.
- **ModuleLayer.findModule(name)** tìm module theo tên trong layer và các layer cha.
- **Module.getLayer()** cho biết layer đã định nghĩa module object.

Layer là một phần của runtime module identity; nó không phải tên phiên bản hoặc tọa độ artifact.

## 7. Module identity không đồng nhất với class identity

Module và class là hai cấp định danh khác nhau.

Một class được JVM nhận diện theo tên nhị phân và defining class loader. Module system bổ sung ngữ cảnh module để áp dụng readability, exports, opens và các quy tắc truy cập. Vì vậy:

- Hai class có cùng tên nhị phân nhưng được định nghĩa bởi hai class loader khác nhau vẫn là hai class runtime khác nhau.
- Hai class thuộc cùng module có thể dùng chung module object nhưng vẫn có identity riêng theo class.
- Module name không thay thế defining class loader khi phân tích lỗi nạp class.
- Package không export ảnh hưởng khả năng truy cập qua ranh giới module; nó không tự đổi tên class hoặc di chuyển class sang module khác.

Ví dụ, nếu gặp **ClassCastException** dù hai object có tên class hiển thị giống nhau, cần kiểm tra class loader đã định nghĩa từng class. Nếu gặp lỗi package không visible hoặc **IllegalAccessError**, cần kiểm tra readability và exports. Hai nhóm lỗi có thể cùng xuất hiện trong ứng dụng modular nhưng nguyên nhân nằm ở hai lớp khác nhau.

## 8. Quan sát named module bằng công cụ JDK

Các công cụ JDK giúp xác nhận tên module và trạng thái module thực tế.

Liệt kê các module có trong runtime hiện tại:

~~~bash
java --list-modules
~~~

Mô tả một JAR:

~~~bash
jar --describe-module --file orders.jar
~~~

Quan sát quá trình resolve khi khởi chạy:

~~~bash
java --show-module-resolution \
  --module-path mods \
  -m com.acme.orders/com.acme.orders.Main
~~~

Các lệnh trên trả lời những câu hỏi khác nhau:

- **java --list-modules** cho biết các module mà runtime hiện tại liệt kê được.
- **jar --describe-module** cho biết module descriptor hoặc thông tin automatic module của JAR.
- **--show-module-resolution** cho biết module system resolve những module nào khi chạy ứng dụng.

Để kiểm tra một class cụ thể trong chương trình, dùng **Class.getModule()** rồi xem **getName()**, **getDescriptor()**, **getLayer()** và **getClassLoader()**. Đừng suy luận module runtime chỉ từ tên file JAR hoặc package của class.

## 9. Quy trình nhận diện module trong một ứng dụng

Khi cần xác định một class thuộc module nào, hãy làm theo thứ tự:

1. Xác định class được nạp từ module path hay classpath.
2. Nếu là modular JAR, đọc **module-info.class** để lấy tên module explicit.
3. Nếu JAR không có descriptor nhưng nằm trên module path, kiểm tra **Automatic-Module-Name** hoặc tên automatic module suy ra từ file.
4. Nếu class đến từ classpath, xác định unnamed module gắn với class loader đã nạp class.
5. Trong runtime, lấy **Class.getModule()** để kiểm tra module object thật sự.
6. Nếu có nhiều layer, kiểm tra **Module.getLayer()** và class loader để phân biệt các runtime context.
7. Khi lỗi liên quan tới dependency hoặc package, kiểm tra thêm **canRead**, **isExported** và **isOpen**.

Quy trình này giúp phân biệt lỗi do tên module, do artifact không nằm trên module path, do package chưa export, hoặc do class được nạp bởi một loader khác.

## 10. Bài tập thực hành

1. Tạo explicit named module **com.acme.orders** với file **module-info.java** và một package API.
2. Biên dịch module thành exploded module hoặc modular JAR, sau đó dùng **jar --describe-module** để xác nhận tên.
3. Đổi tên file JAR nhưng giữ nguyên **module-info.class**. Quan sát tên module vẫn giữ nguyên.
4. Tạo một JAR không có descriptor, thêm **Automatic-Module-Name** vào manifest và đặt JAR trên module path. Xác nhận nó trở thành automatic module có tên đã khai báo.
5. Đặt một class Java lên classpath và gọi **Class.getModule()**. Quan sát **isNamed()** và **getName()**.
6. In **getLayer()** và **getClassLoader()** của class thuộc named module và class thuộc unnamed module.
7. Dùng **ModuleLayer.boot().findModule(...)** để tìm module nền tảng hoặc module ứng dụng trong boot layer.
8. So sánh lỗi package không export với lỗi class được định nghĩa bởi hai class loader khác nhau; giải thích vì sao module identity và class identity không thể dùng thay cho nhau.

## 11. Những điểm cần ghi nhớ

- Named module là module có tên; explicit named module có descriptor do tác giả khai báo.
- Automatic module cũng là named module, nhưng descriptor được tạo tự động từ manifest hoặc tên JAR.
- Code trên classpath thuộc unnamed module; tên module của nó là **null**.
- Module name là định danh trong module system, không phải Maven coordinates, tên file JAR hoặc version string.
- **java.lang.Module** đại diện cho module tại runtime và cung cấp thông tin về descriptor, layer, class loader và quyền truy cập.
- **ModuleLayer** xác định môi trường runtime nơi module được định nghĩa.
- Class identity vẫn gắn với tên nhị phân và defining class loader; module system bổ sung quy tắc truy cập ở cấp module.
- Khi debug, hãy kiểm tra module object thực tế thay vì suy luận chỉ từ tên package hoặc file JAR.

Khi đã phân biệt được module name, module object, ModuleLayer và class loader, bạn sẽ đọc được dependency graph và chẩn đoán lỗi JPMS chính xác hơn. Đây cũng là nền tảng để hiểu các ứng dụng nhiều layer và cơ chế plugin ở runtime.