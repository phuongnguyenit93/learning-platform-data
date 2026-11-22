# requires trong Java Module System

Trong Java Platform Module System (JPMS), từ khóa **requires** khai báo rằng một module phụ thuộc vào và cần đọc một module khác. Directive này được viết trong tệp module descriptor là **module-info.java**. Nó giúp compiler và JVM xây dựng module graph, xác định module nào cần có khi biên dịch hoặc khởi chạy ứng dụng, và kiểm soát khả năng một module nhìn thấy các package được module khác export.

Ví dụ đơn giản:

~~~java
module com.acme.app {
    requires java.sql;
}
~~~

Module com.acme.app khai báo phụ thuộc vào module java.sql. Nhờ đó, mã nguồn của com.acme.app có thể sử dụng các API public nằm trong những package mà java.sql export, chẳng hạn java.sql.Connection.

Cần phân biệt **requires** với **exports**: requires nói module hiện tại đọc module nào; exports do module cung cấp quyết định package nào được module khác truy cập. Chỉ khai báo requires không làm mọi package nội bộ của dependency trở nên public.

## 1. Vị trí và cú pháp

Directive requires nằm trong module declaration ở module-info.java:

~~~java
module module.name {
    requires another.module;
}
~~~

Cú pháp tổng quát:

~~~java
requires [static] [transitive] module.name;
~~~

Hai modifier có thể xuất hiện độc lập hoặc cùng nhau:

- Không có modifier: dependency bắt buộc ở thời điểm biên dịch và khi resolve module graph lúc chạy.
- **transitive**: module phụ thuộc vào module này cũng được đọc dependency được khai báo transitive.
- **static**: dependency bắt buộc ở thời điểm biên dịch nhưng có thể không có khi chạy.
- **static transitive**: dependency được truyền khả năng đọc cho module phụ thuộc, nhưng vẫn là dependency tùy chọn ở runtime.

Tên module là tên module chính xác, phân biệt chữ hoa/chữ thường. Tên này lấy từ module descriptor hoặc tên automatic module khi thư viện chưa có module-info.class.

Ví dụ:

~~~java
module com.acme.data {
    requires java.sql;
    requires transitive com.acme.model;
    requires static com.acme.codegen;
}
~~~

Một module có thể có nhiều requires directive. Không khai báo version range hoặc phiên bản thư viện trong requires; việc chọn phiên bản artifact thường do Maven, Gradle, hệ thống đóng gói hoặc môi trường triển khai quản lý.

## 2. Module và module descriptor

Một named module thường có cấu trúc:

~~~text
project/
  src/
    com.acme.app/
      module-info.java
      com/
        acme/
          app/
            Main.java
~~~

Tệp module-info.java mô tả tên module và các directive như:

- **requires**: module hiện tại phụ thuộc và đọc module nào.
- **exports**: package nào được module khác truy cập.
- **opens**: package nào được mở cho reflection.
- **uses**: service interface mà module cần sử dụng.
- **provides ... with ...**: implementation cung cấp cho một service.

Ví dụ:

~~~java
module com.acme.app {
    requires java.sql;
    exports com.acme.app.api;
    opens com.acme.app.model to some.json.framework;
}
~~~

Ở đây, com.acme.app đọc module java.sql, export package API của chính nó và mở package model cho một module framework cụ thể. Ba directive này giải quyết ba vấn đề khác nhau.

### java.base được yêu cầu ngầm định

Mọi named module, ngoại trừ chính module java.base, đều có khả năng đọc java.base một cách ngầm định. Vì vậy, module thông thường không cần viết:

~~~java
module com.acme.app {
    // Không cần khai báo requires java.base.
}
~~~

Khi xem descriptor đã biên dịch bằng javap -v, requires java.base có thể xuất hiện với cờ **mandated**. Đây là dependency do ngôn ngữ/module system ngầm đưa vào.

## 3. requires tạo quan hệ đọc module

Khi module A khai báo:

~~~java
module com.acme.app {
    requires com.acme.library;
}
~~~

module com.acme.app có quan hệ đọc với com.acme.library. Nếu com.acme.library export package com.acme.library.api, mã trong com.acme.app có thể import và sử dụng các kiểu public thuộc package đó, miễn là các điều kiện truy cập Java khác cũng được thỏa mãn.

Ví dụ module cung cấp API:

~~~java
module com.acme.library {
    exports com.acme.library.api;
}
~~~

Và module ứng dụng:

~~~java
module com.acme.app {
    requires com.acme.library;
}
~~~

Mã Java trong app có thể viết:

~~~java
import com.acme.library.api.Greeting;
~~~

Nếu module thư viện không export package chứa Greeting, app có thể đọc module nhưng vẫn không được truy cập kiểu nằm trong package encapsulated đó.

**Readability** và **accessibility** là hai khái niệm cần xét cùng nhau:

1. requires làm cho module hiện tại đọc module được yêu cầu.
2. exports của module được yêu cầu quyết định package nào được truy cập từ module khác.
3. Java access modifiers như public, protected, package-private và private tiếp tục áp dụng bên trong package/class.
4. Các quy tắc reflection còn chịu ảnh hưởng của opens và module access.

## 4. requires trực tiếp và phụ thuộc bắc cầu

Giả sử có ba module:

- app sử dụng library.
- library sử dụng model.
- model export package API.

Nếu library khai báo requires model thông thường, app đọc library nhưng không tự động đọc model chỉ vì library phụ thuộc vào model.

~~~java
module com.acme.model {
    exports com.acme.model.api;
}
~~~

~~~java
module com.acme.library {
    requires com.acme.model;
    exports com.acme.library.api;
}
~~~

~~~java
module com.acme.app {
    requires com.acme.library;
}
~~~

Trong cấu hình này, com.acme.app không được mặc nhiên sử dụng trực tiếp com.acme.model.api chỉ dựa trên việc requires com.acme.library.

Nếu API public của library sử dụng kiểu thuộc model và muốn người dùng library có thể đọc kiểu đó thông qua dependency, library có thể khai báo:

~~~java
module com.acme.library {
    requires transitive com.acme.model;
    exports com.acme.library.api;
}
~~~

Khi app requires com.acme.library, quan hệ đọc transitive cho phép app đọc com.acme.model.

### requires transitive không phải exports

Modifier transitive truyền khả năng đọc module dependency tới các module phụ thuộc. Nó không tự export package của dependency và cũng không làm package nội bộ của library trở thành public.

Module com.acme.model vẫn phải tự export package API mà người dùng cần truy cập. Nếu model không export com.acme.model.internal, app không thể truy cập package đó chỉ vì library khai báo requires transitive com.acme.model.

### Khi nào dùng transitive?

Dùng requires transitive khi dependency xuất hiện trong public API của module và người sử dụng module đó cần có khả năng đọc dependency để biên dịch hoặc sử dụng API.

Ví dụ, một method public trả về com.acme.model.api.Customer. Nếu module library export package chứa method đó, module client thường cần đọc module model để tham chiếu Customer. requires transitive có thể thể hiện hợp đồng module này.

Không nên khai báo transitive cho mọi dependency. Điều đó làm module graph của người dùng rộng hơn và có thể khiến implementation detail vô tình trở thành một phần của hợp đồng phụ thuộc.

## 5. requires static: dependency tùy chọn ở runtime

**requires static** khai báo một dependency cần có khi biên dịch nhưng không bắt buộc phải có khi chạy.

~~~java
module com.acme.app {
    requires static com.acme.optional;
}
~~~

Compiler vẫn cần tìm module com.acme.optional trên module path khi biên dịch. Khi khởi chạy, module này có thể vắng mặt mà không làm việc resolve module graph thất bại chỉ vì directive static đó.

Trường hợp sử dụng có thể gồm:

- API chỉ được tham chiếu bởi annotation hoặc metadata compile-time.
- Tích hợp tùy chọn với thư viện có thể không được cài trong một số môi trường.
- Công cụ hỗ trợ build hoặc phân tích mà runtime không cần nạp.
- Tính năng mở rộng được cô lập để phần cốt lõi chạy được khi extension không hiện diện.

### Cẩn trọng khi dependency vắng mặt

requires static không biến mọi lời gọi tới dependency thành an toàn. Nếu code runtime thực sự nạp class, gọi method hoặc tạo object thuộc module tùy chọn mà module đó không có, chương trình vẫn có thể gặp lỗi như NoClassDefFoundError hoặc lỗi liên kết tương ứng.

Do đó:

- Tách code phụ thuộc tùy chọn khỏi luồng khởi chạy bắt buộc.
- Kiểm tra khả năng hiện diện của tính năng theo thiết kế.
- Không để kiểu của dependency tùy chọn xuất hiện ở nơi mà mọi caller bắt buộc phải nạp.
- Test cả trường hợp dependency có mặt và không có mặt.

## 6. Kết hợp static và transitive

Có thể dùng cả hai modifier:

~~~java
module com.acme.library {
    requires static transitive com.acme.annotations;
}
~~~

Ý nghĩa:

- com.acme.annotations cần có khi biên dịch module library.
- Khả năng đọc module này được truyền cho module phụ thuộc vào library.
- Dependency vẫn tùy chọn ở runtime.

Cách khai báo này hữu ích khi kiểu hoặc annotation của dependency xuất hiện trong API/metadata mà module downstream cần nhìn thấy lúc biên dịch, nhưng runtime không nhất thiết cần thư viện đó.

Cần thiết kế kỹ nếu public API chứa kiểu từ một module static. Khi runtime không có dependency, các class có tham chiếu tới kiểu đó không nên bị nạp hoặc sử dụng theo cách đòi hỏi module vắng mặt.

## 7. Ví dụ hoàn chỉnh với hai named module

Ví dụ này tạo module thư viện com.acme.greeter và module ứng dụng com.acme.app. Ứng dụng khai báo requires để sử dụng API do thư viện export.

Cấu trúc thư mục:

~~~text
module-demo/
  src/
    com.acme.greeter/
      module-info.java
      com/acme/greeter/api/Greeting.java
    com.acme.app/
      module-info.java
      com/acme/app/Main.java
~~~

### Module thư viện

Tệp src/com.acme.greeter/module-info.java:

~~~java
module com.acme.greeter {
    exports com.acme.greeter.api;
}
~~~

Tệp src/com.acme.greeter/com/acme/greeter/api/Greeting.java:

~~~java
package com.acme.greeter.api;

public class Greeting {
    public String message(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Module export package com.acme.greeter.api để module khác có thể sử dụng class Greeting.

### Module ứng dụng

Tệp src/com.acme.app/module-info.java:

~~~java
module com.acme.app {
    requires com.acme.greeter;
}
~~~

Tệp src/com.acme.app/com/acme/app/Main.java:

~~~java
package com.acme.app;

import com.acme.greeter.api.Greeting;

public class Main {
    public static void main(String[] args) {
        Greeting greeting = new Greeting();
        System.out.println(greeting.message("JPMS"));
    }
}
~~~

Directive requires com.acme.greeter cho phép app đọc module thư viện; exports trong descriptor của greeter cho phép app truy cập package API.

### Biên dịch

Chạy từ thư mục module-demo bằng JDK 17 trở lên:

~~~bash
javac --module-source-path src -d mods -m com.acme.greeter,com.acme.app
~~~

Ý nghĩa:

- --module-source-path src chỉ vị trí cây source được tổ chức theo tên module.
- -d mods đặt các module đã biên dịch vào thư mục mods.
- -m chỉ định hai module cần biên dịch.

Sau khi biên dịch, cấu trúc output có dạng:

~~~text
mods/
  com.acme.greeter/
    module-info.class
    com/acme/greeter/api/Greeting.class
  com.acme.app/
    module-info.class
    com/acme/app/Main.class
~~~

### Chạy ứng dụng

~~~bash
java --module-path mods --module com.acme.app/com.acme.app.Main
~~~

Stdout:

~~~text
Hello, JPMS!
~~~

JVM tìm module app và dependency greeter trên module path, resolve requires, sau đó gọi main class được chỉ định.

## 8. Ví dụ về requires transitive

Giả sử module model cung cấp kiểu Customer:

~~~java
module com.acme.model {
    exports com.acme.model.api;
}
~~~

~~~java
package com.acme.model.api;

public record Customer(String name) {
}
~~~

Module library trả về kiểu Customer trong public API:

~~~java
module com.acme.library {
    requires transitive com.acme.model;
    exports com.acme.library.api;
}
~~~

~~~java
package com.acme.library.api;

import com.acme.model.api.Customer;

public class CustomerService {
    public Customer findCustomer() {
        return new Customer("Ada");
    }
}
~~~

Module app chỉ cần requires library:

~~~java
module com.acme.app {
    requires com.acme.library;
}
~~~

Trong app, code có thể dùng Customer vì library đã khai báo dependency model là transitive:

~~~java
package com.acme.app;

import com.acme.library.api.CustomerService;
import com.acme.model.api.Customer;

public class Main {
    public static void main(String[] args) {
        Customer customer = new CustomerService().findCustomer();
        System.out.println(customer.name());
    }
}
~~~

Nếu library chỉ dùng requires com.acme.model thông thường, app sẽ phải khai báo thêm requires com.acme.model để đọc kiểu Customer trực tiếp. Đây là lý do transitive phù hợp khi dependency là một phần của API công khai.

## 9. requires và module graph

Khi biên dịch hoặc chạy một ứng dụng modular, compiler/JVM xây dựng đồ thị phụ thuộc module.

Ví dụ:

~~~text
com.acme.app
    |
    | requires
    v
com.acme.library
    |
    | requires transitive
    v
com.acme.model
~~~

Đồ thị này cho biết module nào cần được resolve và module nào có thể đọc module khác. Các dependency phải có mặt trên module path hoặc thuộc tập module hệ thống mà runtime cung cấp.

Một module được yêu cầu nhưng không tìm thấy có thể gây lỗi như:

~~~text
java.lang.module.FindException:
Module com.acme.library not found
~~~

Một module graph có chu trình phụ thuộc không hợp lệ có thể khiến quá trình resolution thất bại. Ví dụ, tránh thiết kế:

~~~text
module A requires B
module B requires A
~~~

Cách khắc phục thường là tách phần API chung thành module thứ ba, để A và B cùng phụ thuộc vào module API thay vì phụ thuộc vòng vào nhau.

## 10. requires và classpath/module path

requires thuộc mô hình named module của JPMS. Nó được khai báo trong module-info.java và được xử lý khi compiler/JVM làm việc với module path.

| Classpath | Module path |
|---|---|
| Các JAR/class thường thuộc unnamed module | JAR/module được xem xét như named hoặc automatic module |
| Không cần module-info.java | Named module thường có module-info.class |
| Không có requires directive để mô tả dependency | requires mô tả quan hệ phụ thuộc |
| Encapsulation theo package/module không giống named module | Exports và opens kiểm soát truy cập liên module |

Một thư viện đặt trên classpath không thể được tham chiếu bằng một requires directive như thể nó đã là named module. Nếu cần dùng trên module path, xác định module name của JAR. JAR có module-info.class là explicit module; JAR không có descriptor có thể trở thành automatic module khi đặt trên module path.

Tên automatic module có thể được suy ra từ tên JAR hoặc được chỉ định bằng thuộc tính Automatic-Module-Name trong manifest. Vì tên suy ra có thể thay đổi khi đổi tên artifact, thư viện công khai thường nên khai báo Automatic-Module-Name ổn định nếu chưa cung cấp module-info.class.

## 11. Kiểm tra requires bằng công cụ JDK

### Xem module descriptor trong class file

Sau khi biên dịch, dùng javap để xem descriptor:

~~~bash
javap -v mods/com.acme.app/module-info.class
~~~

Trong output, tìm phần Module. Nó chứa module name, requires, exports, opens, uses và provides. Dependency java.base ngầm định có thể được đánh dấu mandated.

### Xem module trong JAR

Nếu đã đóng gói module thành JAR:

~~~bash
jar --describe-module --file app.jar
~~~

Lệnh này giúp xem tên module và các directive được lưu trong module descriptor hoặc thông tin automatic module.

### Kiểm tra dependency bằng jdeps

~~~bash
jdeps --check com.acme.app --module-path mods
~~~

jdeps hỗ trợ kiểm tra module descriptor và các dependency liên quan. Có thể xem danh sách module dependency cần thiết cho một JAR:

~~~bash
jdeps --print-module-deps app.jar
~~~

Kết quả phụ thuộc vào class thực tế trong artifact và module path được cung cấp. jdeps phân tích bytecode dependency; nó không thay thế kiểm thử tích hợp.

### Hiển thị quá trình resolve lúc chạy

~~~bash
java --show-module-resolution --module-path mods --module com.acme.app/com.acme.app.Main
~~~

Tùy chọn --show-module-resolution hiển thị thông tin module được resolve và quan hệ phụ thuộc. Nó hữu ích khi ứng dụng báo thiếu module hoặc chọn nhầm phiên bản module trên module path.

## 12. requires trong JDK platform modules

Các module JDK được chia theo chức năng. Một số tên module thường gặp:

| Module | Nội dung tiêu biểu |
|---|---|
| java.base | Các API nền tảng như java.lang, java.util, java.io |
| java.sql | JDBC và API liên quan cơ sở dữ liệu |
| java.logging | Java Logging API |
| java.xml | XML, SAX, DOM và các API XML |
| java.desktop | AWT, Swing và một số API đồ họa |
| java.net.http | HTTP Client API |
| java.management | JMX và API quản lý JVM |

Ví dụ module sử dụng JDBC và logging:

~~~java
module com.acme.reporting {
    requires java.sql;
    requires java.logging;
}
~~~

Biên dịch và chạy cần dùng JDK/runtime có các module tương ứng. Nếu tạo runtime image tùy biến bằng jlink, cần đưa các module cần thiết vào image. Có thể xem các module hệ thống bằng:

~~~bash
java --list-modules
~~~

Một module không được đưa vào runtime image sẽ không thể được resolve chỉ nhờ việc source có requires directive. Hãy bảo đảm image chứa dependency runtime cần thiết.

## 13. Các lỗi thường gặp

| Lỗi hoặc hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Module not found | Dependency không có trên module path hoặc sai module name | Kiểm tra artifact, tên module và --module-path |
| Package is not visible | Module dependency không export package đó | Kiểm tra exports trong module descriptor |
| Module does not read another module | Thiếu requires trực tiếp hoặc requires transitive cần thiết | Khai báo dependency đúng ở module sử dụng |
| Dependency có lúc compile nhưng runtime lỗi | Dùng requires static nhưng code runtime vẫn nạp kiểu của dependency khi nó vắng mặt | Cô lập code tùy chọn và test cả hai trường hợp |
| Duplicate module / resolution error | Nhiều phiên bản module cùng tên hoặc module graph xung đột | Làm sạch module path và thống nhất dependency |
| Circular dependence | Các module requires lẫn nhau | Tách API chung thành module độc lập |
| Automatic module name thay đổi | Tên được suy ra từ tên JAR | Khai báo Automatic-Module-Name ổn định hoặc dùng module-info.java |
| Reflection bị chặn | Package chưa được opens cho framework cần reflection | Chỉ mở package cần thiết bằng opens hoặc --add-opens có kiểm soát |

Khi gặp lỗi, hãy phân biệt lỗi resolve module, lỗi truy cập package và lỗi nạp class. Chúng xảy ra ở các giai đoạn khác nhau và cần cách xử lý khác nhau.

## 14. Quy tắc thiết kế dependency bằng requires

- Chỉ khai báo module mà code thực sự phụ thuộc.
- Ưu tiên requires thông thường cho dependency bắt buộc.
- Dùng requires transitive khi dependency là một phần của API công khai và module downstream cần đọc nó.
- Dùng requires static cho dependency cần lúc compile nhưng có thể vắng mặt lúc runtime.
- Tránh requires transitive tràn lan vì nó mở rộng module graph của người dùng.
- Tránh chu trình phụ thuộc; tách API chung thành module riêng khi cần.
- Không nhầm requires với exports hoặc opens.
- Dùng module name ổn định và kiểm tra automatic module name của dependency.
- Kiểm tra module path thực tế trong CI và runtime image.
- Chỉ thêm --add-reads hoặc các tùy chọn phá vỡ encapsulation khi có lý do tương thích cụ thể; ghi lại và giới hạn phạm vi sử dụng.

Một module descriptor tốt thể hiện đúng hợp đồng phụ thuộc của module. Khi thay đổi public API, hãy xem lại các requires transitive để tránh vô tình làm thay đổi khả năng đọc module của consumer.

## 15. Checklist khi dùng requires

- [ ] Xác định module name chính xác của dependency.
- [ ] Đặt requires trong module-info.java của module cần sử dụng dependency.
- [ ] Xác nhận dependency có trên module path khi compile và runtime.
- [ ] Kiểm tra package cần dùng đã được dependency exports hay chưa.
- [ ] Dùng requires transitive chỉ khi dependency là một phần của API mà consumer cần đọc.
- [ ] Dùng requires static chỉ khi code có thể hoạt động an toàn nếu dependency vắng mặt lúc runtime.
- [ ] Kiểm tra module graph không có chu trình và không có module name trùng lặp.
- [ ] Kiểm tra descriptor đã biên dịch bằng javap hoặc jar --describe-module.
- [ ] Dùng jdeps và --show-module-resolution để điều tra dependency.
- [ ] Test trên runtime image thực tế, đặc biệt nếu dùng jlink.

## 16. Ghi nhớ

- requires khai báo module mà named module hiện tại phụ thuộc và cần đọc.
- requires thông thường là dependency bắt buộc ở compile time và khi resolve module graph runtime.
- requires transitive truyền khả năng đọc dependency tới module phụ thuộc vào module hiện tại.
- requires static cần dependency lúc biên dịch nhưng cho phép dependency vắng mặt khi resolve ở runtime.
- requires static transitive kết hợp hai hành vi trên.
- requires không export package; module cung cấp phải khai báo exports riêng.
- java.base được yêu cầu ngầm định bởi các named module thông thường.
- Module name và dependency version là hai khái niệm khác nhau; requires không khóa phiên bản artifact.
- Module graph phải được resolve trên module path; thiếu dependency có thể gây FindException.
- Dùng javap, jar, jdeps và --show-module-resolution để kiểm tra module descriptor và quan hệ dependency.

## Tài liệu tham khảo chính thức

- [Java Language Specification — Module Declarations and Requires Directives](https://docs.oracle.com/javase/specs/jls/se26/html/jls-7.html)
- [Java Virtual Machine Specification — Module Attributes](https://docs.oracle.com/javase/specs/jvms/se26/html/jvms-4.html)
- [Module API — java.lang.module](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/module/package-summary.html)
- [javac Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html)
- [java Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [jdeps Command — JDK 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)