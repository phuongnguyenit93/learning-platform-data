# Module path, classpath và xung đột package trong Java 17

Khi một chương trình Java dùng thư viện bên ngoài, trình biên dịch và JVM cần biết phải tìm class ở đâu. Hai cơ chế thường gặp là **classpath** và **module path**. Classpath là cơ chế tìm class truyền thống. Module path được dùng với hệ thống module JPMS (Java Platform Module System), chính thức có từ Java 9 và tiếp tục được hỗ trợ trong Java 17.

Khác biệt không chỉ nằm ở tên tham số dòng lệnh. Một JAR đặt trên classpath thường thuộc **unnamed module**; một JAR có module descriptor đặt trên module path là **named module**. Cách các module nhìn thấy package, khai báo phụ thuộc và xử lý package trùng nhau vì thế cũng khác.

Bài học này giải thích cách chọn classpath hay module path, cách biên dịch và chạy ứng dụng modular trong Java 17, cách thư viện cũ tham gia module system, và cách nhận biết cũng như xử lý xung đột package.

## 1. Classpath là gì?

**Classpath** là danh sách các thư mục và JAR mà trình biên dịch hoặc JVM tìm kiếm khi cần nạp class và resource. Có thể khai báo bằng:

- **-cp** hoặc **-classpath** trên **javac** và **java**;
- **--class-path** trên các công cụ hỗ trợ cú pháp dài;
- biến môi trường **CLASSPATH** nếu môi trường triển khai có cấu hình.

Ví dụ:

~~~bash
javac -cp "lib/greetings.jar" -d out src/com/acme/app/Main.java
java -cp "out:lib/greetings.jar" com.acme.app.Main
~~~

Trong lệnh chạy trên Linux/macOS, dấu phân cách giữa các phần tử classpath là dấu hai chấm (**:**). Trên Windows, dùng dấu chấm phẩy (**;**):

~~~powershell
java -cp "out;lib/greetings.jar" com.acme.app.Main
~~~

Classpath có thể chứa:

- thư mục chứa các file **.class**;
- JAR chứa class và resource;
- nhiều thư mục hoặc JAR, phân cách theo quy tắc của hệ điều hành.

### 1.1. Classpath và unnamed module

Khi chạy trên classpath, các class được nạp bởi một class loader thuộc **unnamed module** tương ứng với class loader đó. Ứng dụng truyền thống không cần có **module-info.java**.

Unnamed module có những đặc điểm đáng chú ý:

- Không có tên module được khai báo trong **module-info.java**.
- Các package của nó được export để những module đọc được unnamed module có thể truy cập theo quy tắc truy cập Java.
- Unnamed module đọc các module trong module layer tương ứng.
- Các named module không tự động đọc unnamed module.

Điều cuối cùng quan trọng khi kết hợp ứng dụng modular với thư viện đặt trên classpath: một named module không thể mặc nhiên dùng class của thư viện trong unnamed module chỉ vì JAR đó có mặt trên dòng lệnh.

### 1.2. Classpath không khai báo quan hệ module

Classpath không có khai báo **requires** và **exports** theo JPMS. Việc một class có thể được tìm thấy chủ yếu phụ thuộc:

1. class có nằm trong một entry của classpath hay không;
2. class loader có tìm thấy và nạp được class đó hay không;
3. các điều kiện tương thích bytecode, phụ thuộc và quyền truy cập Java có thỏa mãn hay không.

Classpath vẫn được dùng rộng rãi cho ứng dụng không modular, công cụ dòng lệnh, test và thư viện chưa chuyển sang module. Java 17 không yêu cầu mọi ứng dụng phải chuyển sang module path.

## 2. Module path là gì?

**Module path** là danh sách vị trí chứa các module mà trình biên dịch hoặc JVM có thể tìm thấy. Dùng **--module-path** hoặc viết tắt **-p**:

~~~bash
javac --module-path mods -d out ...
java --module-path mods --module com.acme.app/com.acme.app.Main
~~~

Module path có thể chứa:

- **Modular JAR**: JAR có module descriptor **module-info.class**.
- **Exploded module**: thư mục chứa cấu trúc của một module đã biên dịch, bao gồm module descriptor.
- **Automatic module**: JAR không có module descriptor nhưng được đặt trên module path và được hệ thống module coi như một module tự động.

Khi dùng module path, Java giải quyết các module theo tên và quan hệ phụ thuộc. Module descriptor cho biết module nào cần module nào, package nào được export và các chính sách liên quan.

### 2.1. Named module và module-info.java

Một module có tên được khai báo trong file **module-info.java** ở gốc module:

~~~java
module com.acme.greetings {
    exports com.acme.greetings.api;
}
~~~

Trong ví dụ:

- **com.acme.greetings** là **tên module**.
- **com.acme.greetings.api** là **tên package** được export.
- Các module khác có thể đọc module này và truy cập các kiểu public trong package được export, nếu khai báo quan hệ phụ thuộc phù hợp.

Tên module và tên package là hai khái niệm khác nhau. Tên module thường dùng quy ước reverse-DNS như **com.acme.greetings**; package thường là **com.acme.greetings.api**. Module name không tự động quyết định package name.

### 2.2. requires và exports

Một module sử dụng API của module khác cần khai báo **requires**:

~~~java
module com.acme.app {
    requires com.acme.greetings;
}
~~~

Module cung cấp API cần export package chứa API:

~~~java
module com.acme.greetings {
    exports com.acme.greetings.api;
}
~~~

Hai khai báo có ý nghĩa khác nhau:

| Chỉ thị | Ý nghĩa |
| --- | --- |
| **requires module.name;** | Module hiện tại đọc module được yêu cầu. |
| **exports package.name;** | Package được công khai cho các module đọc module này. |
| **exports package.name to other.module;** | Chỉ export package cho những module được liệt kê. |
| **requires transitive module.name;** | Module phụ thuộc được truyền tiếp cho module đọc module hiện tại. |
| **opens package.name;** | Mở package cho reflection sâu theo quy tắc module. |
| **opens package.name to other.module;** | Chỉ mở package cho các module được liệt kê. |

**exports** phục vụ truy cập API theo quy tắc truy cập Java. **opens** phục vụ các thao tác reflection sâu, ví dụ framework cần truy cập thành viên không public. Không nên dùng **opens** thay cho **exports** khi mục tiêu chỉ là công khai API.

## 3. Ví dụ: hai module giao tiếp qua package được export

Giả sử ứng dụng có hai module:

~~~text
project/
└── src/
    ├── com.acme.greetings/
    │   ├── module-info.java
    │   └── com/acme/greetings/api/Greeter.java
    └── com.acme.app/
        ├── module-info.java
        └── com/acme/app/Main.java
~~~

Module thư viện:

**src/com.acme.greetings/module-info.java**

~~~java
module com.acme.greetings {
    exports com.acme.greetings.api;
}
~~~

**src/com.acme.greetings/com/acme/greetings/api/Greeter.java**

~~~java
package com.acme.greetings.api;

public class Greeter {
    public String greet(String name) {
        return "Xin chào, " + name + "!";
    }
}
~~~

Module ứng dụng:

**src/com.acme.app/module-info.java**

~~~java
module com.acme.app {
    requires com.acme.greetings;
}
~~~

**src/com.acme.app/com/acme/app/Main.java**

~~~java
package com.acme.app;

import com.acme.greetings.api.Greeter;

public class Main {
    public static void main(String[] args) {
        Greeter greeter = new Greeter();
        System.out.println(greeter.greet("Java 17"));
    }
}
~~~

Biên dịch hai module từ module source path:

~~~bash
javac --module-source-path src -d out \
    -m com.acme.greetings,com.acme.app
~~~

Chạy module ứng dụng:

~~~bash
java --module-path out \
    --module com.acme.app/com.acme.app.Main
~~~

Kết quả:

~~~text
Xin chào, Java 17!
~~~

**--module-source-path** cho **javac** biết nơi tìm mã nguồn của các module. **-m** hoặc **--module** chọn module cần biên dịch. Khi chạy, **--module-path out** cung cấp các module đã biên dịch và **--module module/mainClass** chỉ định module cùng lớp main.

Nếu chỉ muốn chạy một module có main class đã khai báo trong module descriptor, có thể dùng dạng **--module com.acme.app**; ví dụ trên chỉ rõ tên lớp để dễ thấy ranh giới giữa module và package.

## 4. Phân biệt classpath và module path

| Tiêu chí | Classpath | Module path |
| --- | --- | --- |
| Cơ chế | Tìm class/resource theo danh sách thư mục và JAR. | Tìm module theo tên và giải quyết đồ thị phụ thuộc. |
| Module identity | Các class nằm trong unnamed module của class loader. | Các module có tên, hoặc automatic module. |
| Khai báo phụ thuộc | Không có **requires** trong classpath. | Dùng **requires** trong **module-info.java**. |
| Công khai package | Không có **exports** của JPMS. | Named module cần export package cho module khác đọc. |
| Đóng gói | JAR thông thường hoặc thư mục class. | Modular JAR, exploded module, hoặc automatic module. |
| Phát hiện xung đột | Trùng class có thể bị che khuất theo thứ tự tìm kiếm/class loader. | Module system kiểm tra module graph và các package export bị trùng trong ngữ cảnh người đọc. |
| Phù hợp | Ứng dụng truyền thống, test, thư viện chưa modular. | Ứng dụng modular cần dependency rõ ràng và đóng gói theo module. |

Hai cơ chế có thể xuất hiện đồng thời trên cùng một lệnh chạy. Tuy nhiên, việc một JAR có mặt trên classpath không có nghĩa named module sẽ tự động đọc được JAR đó.

## 5. Automatic module: cầu nối cho thư viện chưa có module descriptor

Một JAR không chứa **module-info.class** nhưng được đặt trên module path có thể được coi là **automatic module**.

Tên module tự động thường được xác định theo thứ tự:

1. Giá trị **Automatic-Module-Name** trong manifest của JAR, nếu có.
2. Nếu không có, tên được suy ra từ tên tệp JAR theo quy tắc đặt tên automatic module.

Ví dụ, một thư viện **legacy-utils-2.1.jar** không có module descriptor có thể được đặt trên module path. Tên automatic module được suy ra từ tên JAR sau khi chuẩn hóa theo quy tắc của Java. Với ứng dụng cần tên ổn định, nhà phát hành thư viện nên cung cấp **Automatic-Module-Name** trong manifest.

Automatic module có những đặc điểm:

- Có tên module để module khác dùng trong **requires**.
- Export các package của nó.
- Đọc các module khác trong module graph theo quy tắc dành cho automatic module.
- Có thể giúp đưa thư viện cũ vào module path trong giai đoạn chuyển đổi.

Ví dụ, module ứng dụng khai báo:

~~~java
module com.acme.app {
    requires legacy.utils;
}
~~~

Tên **legacy.utils** phải là tên module mà runtime nhận diện, không nhất thiết giống tên file JAR hoặc package. Hãy kiểm tra tên thực tế bằng công cụ **jar**.

Automatic module là cơ chế tương thích và chuyển đổi. Nó không cung cấp mức đóng gói package chặt chẽ như một named module có descriptor được thiết kế rõ ràng. Khi có thể, nên dùng phiên bản thư viện có module descriptor ổn định.

## 6. Đưa thư viện lên classpath hay module path?

Giả sử ứng dụng cần dùng **vendor-utils.jar**.

### 6.1. Đặt thư viện trên classpath

~~~bash
javac -cp "lib/vendor-utils.jar" -d out \
    src/com/acme/app/Main.java

java -cp "out:lib/vendor-utils.jar" com.acme.app.Main
~~~

Đây là mô hình classpath. Các class của ứng dụng và thư viện nằm trong unnamed module tương ứng với class loader. Không cần khai báo **requires**.

### 6.2. Đặt JAR không modular trên module path

Nếu **vendor-utils.jar** không có **module-info.class**, runtime có thể coi nó là automatic module:

~~~bash
javac --module-path lib -d out \
    --module-source-path src -m com.acme.app

java --module-path "out:lib" \
    --module com.acme.app/com.acme.app.Main
~~~

Module ứng dụng cần **requires** tên automatic module:

~~~java
module com.acme.app {
    requires vendor.utils;
}
~~~

Tên trên chỉ là minh họa. Trước khi viết **requires**, hãy kiểm tra tên module mà JAR thực sự cung cấp.

### 6.3. Đặt thư viện trên classpath khi ứng dụng là named module

Có thể đặt cả **--module-path** và **--class-path** trong cùng lệnh:

~~~bash
java --module-path mods \
    --class-path "legacy/old-helper.jar" \
    --module com.acme.app/com.acme.app.Main
~~~

Tuy nhiên, JAR trên classpath thuộc unnamed module. Named module không tự động đọc unnamed module. Nếu module ứng dụng cần truy cập thư viện đó, hãy cân nhắc:

- chuyển thư viện sang module path nếu nó có thể hoạt động như automatic module;
- dùng phiên bản modular của thư viện;
- hoặc, trong giai đoạn chuyển đổi có chủ đích, bổ sung readability bằng **--add-reads** sau khi hiểu rõ tác động.

Ví dụ cú pháp bổ sung readability ở runtime:

~~~bash
java --module-path mods \
    --class-path "legacy/old-helper.jar" \
    --add-reads com.acme.app=ALL-UNNAMED \
    --module com.acme.app/com.acme.app.Main
~~~

Đây là công cụ tương thích, không phải cách thiết kế dependency lâu dài. Nếu source của named module trực tiếp import class trong unnamed module, cần bổ sung readability cho bước biên dịch bằng tùy chọn tương ứng của **javac** và cho bước chạy bằng **java**. **--add-reads** chỉ bổ sung quan hệ đọc; nó không biến JAR thành named module và không giải quyết xung đột package.

## 7. Package là gì trong ngữ cảnh module?

Trong Java, package là không gian tên dùng để nhóm các kiểu và hỗ trợ kiểm soát truy cập. Ví dụ:

~~~java
package com.acme.payment;

public class PaymentService {
}
~~~

Tên package là **com.acme.payment**. Một package có thể chứa nhiều class, interface, enum hoặc record.

Trong module system:

- Module chứa các package.
- Module descriptor quyết định package nào được export hoặc open.
- Module khác cần đọc module cung cấp package đó.
- Tên module không thay thế tên package.

Ví dụ:

~~~text
module com.acme.billing
└── package com.acme.billing.api
    ├── Invoice.java
    └── BillingClient.java
~~~

**com.acme.billing** là module name; **com.acme.billing.api** là package name. Module có thể chứa nhiều package, nhưng chỉ package được export mới trở thành API công khai cho module khác theo JPMS.

## 8. Xung đột package là gì?

**Split package** xảy ra khi cùng một tên package được chia giữa nhiều đơn vị đóng gói/module. Vấn đề đặc biệt quan trọng khi chuyển ứng dụng từ classpath sang module path.

Ví dụ hai thư viện đều chứa package:

~~~text
vendor-a.jar
└── com/example/util/
    └── TextHelper.class

vendor-b.jar
└── com/example/util/
    └── DateHelper.class
~~~

Trên classpath, hai JAR có thể cùng chứa các class thuộc **com.example.util**. Điều này không tự động tạo lỗi chỉ vì tên package trùng; tuy nhiên, nó làm package bị chia giữa các JAR và có thể gây khó khăn khi bảo trì hoặc chuyển sang JPMS.

Khi chuyển sang named modules, một xung đột điển hình xảy ra khi hai module được giải quyết cùng export package **com.example.util** tới cùng một module tiêu thụ. Module system không thể coi package đó là một API duy nhất không mơ hồ và việc giải quyết/biên dịch module graph sẽ thất bại.

Ví dụ:

~~~java
module com.vendor.a {
    exports com.example.util;
}
~~~

~~~java
module com.vendor.b {
    exports com.example.util;
}
~~~

~~~java
module com.acme.app {
    requires com.vendor.a;
    requires com.vendor.b;
}
~~~

Nếu cả hai module export package trùng tới **com.acme.app**, ứng dụng gặp xung đột split package. Thông báo lỗi cụ thể tùy công cụ và giai đoạn phát hiện, nhưng nguyên nhân là consumer nhìn thấy cùng package từ nhiều module.

Điểm cần hiểu chính xác: không phải mọi lần xuất hiện cùng chuỗi package name ở bất kỳ đâu cũng dẫn đến cùng một lỗi. Xung đột phụ thuộc vào module graph, các package được export và module nào đọc chúng. Tuy vậy, thiết kế module nên tránh chia một package giữa nhiều named module.

## 9. Xung đột class trên classpath khác split package trong module path

Hai tình huống này không nên đánh đồng:

### 9.1. Trùng package trên classpath

Nhiều JAR trên classpath có thể chứa các class thuộc cùng một package. Ví dụ:

~~~text
lib-a.jar: com/acme/util/StringTools.class
lib-b.jar: com/acme/util/DateTools.class
~~~

Nếu hai JAR chứa các class khác nhau trong cùng package, chương trình classpath truyền thống có thể hoạt động bình thường.

### 9.2. Trùng cùng tên class trên classpath

Nếu hai JAR cùng chứa một binary name:

~~~text
lib-a.jar: com/acme/util/Version.class
lib-b.jar: com/acme/util/Version.class
~~~

thì class loader thường tìm thấy class theo thứ tự classpath và class đầu tiên được nạp sẽ được dùng trong class loader đó. Kết quả có thể phụ thuộc thứ tự entry, dẫn tới chạy nhầm phiên bản hoặc lỗi liên kết như **NoSuchMethodError** khi code được biên dịch với một phiên bản nhưng runtime nạp phiên bản khác.

Đừng dựa vào thứ tự classpath để quản lý nhiều phiên bản của cùng một thư viện. Hãy loại bỏ bản trùng và chọn một phiên bản dependency thống nhất.

### 9.3. Split package giữa named modules

Với named modules, module descriptor và module graph tham gia vào việc xác định package nào được cung cấp cho consumer. Nếu hai module cùng export một package cho module đọc chúng, xung đột được phát hiện trong quá trình resolve/compile.

Do đó:

- Classpath có thể che giấu split package mà module path sẽ phát hiện.
- Một JAR hoạt động trên classpath chưa chắc chuyển lên module path mà không thay đổi.
- Đổi vị trí JAR từ classpath sang module path có thể làm lộ lỗi module name, readability, exports hoặc split package.

## 10. Cách phát hiện package và module bị trùng

### 10.1. Xem module descriptor của JAR

Dùng **jar --describe-module**:

~~~bash
jar --describe-module --file lib/vendor-utils.jar
~~~

Kết quả cho biết module name, các package và thông tin descriptor. Nếu JAR không có module descriptor, công cụ có thể hiển thị tên automatic module hoặc gợi ý tên module được suy ra.

Với một JAR modular, có thể xem trực tiếp descriptor:

~~~bash
jar --describe-module --file mods/com.acme.greetings.jar
~~~

### 10.2. Quan sát module resolution

Khi chạy ứng dụng modular, dùng:

~~~bash
java --show-module-resolution \
    --module-path mods \
    --module com.acme.app/com.acme.app.Main
~~~

Tùy chọn này hiển thị các module được giải quyết và quan hệ phụ thuộc được dùng để khởi động ứng dụng.

### 10.3. Phân tích dependency bằng jdeps

**jdeps** phân tích dependency ở cấp class/package/module. Ví dụ kiểm tra module:

~~~bash
jdeps --module-path mods --check com.acme.app
~~~

Có thể dùng các tùy chọn của **jdeps** để xem dependency theo package hoặc module khi cần điều tra một thư viện có phụ thuộc ngoài dự kiến hay không.

### 10.4. Kiểm tra nội dung JAR

Dùng **jar --list** để xem class và package trong một JAR:

~~~bash
jar --list --file lib/vendor-a.jar
jar --list --file lib/vendor-b.jar
~~~

Tìm các đường dẫn package xuất hiện trong nhiều JAR. Khi nghi ngờ trùng class, so sánh cả binary name và phiên bản artifact, không chỉ so sánh tên package.

## 11. Cách xử lý xung đột package

### 11.1. Gộp các class thuộc cùng một package vào một module

Nếu **com.example.util** là một package API duy nhất nhưng bị chia qua hai module, giải pháp tốt thường là đặt các class của package đó vào **một module sở hữu package**. Module còn lại có thể phụ thuộc vào module này.

Ví dụ:

~~~text
com.example.util
        |
        v
com.acme.common
        |
        +------> com.vendor.a
        |
        +------> com.vendor.b
~~~

Thiết kế này làm rõ module nào sở hữu package và giảm xung đột khi consumer đọc các module.

### 11.2. Đổi package khi hai API thực sự độc lập

Nếu hai thư viện có các khái niệm khác nhau nhưng dùng cùng tên package, cân nhắc đổi package để tên phản ánh namespace của nhà cung cấp hoặc miền nghiệp vụ:

~~~text
com.vendorA.util
com.vendorB.util
~~~

Đây là thay đổi API có thể ảnh hưởng source compatibility và binary compatibility; cần phối hợp với người dùng thư viện và kế hoạch nâng cấp.

### 11.3. Chọn một phiên bản dependency

Nếu xung đột do hai phiên bản của cùng một thư viện, chọn một phiên bản tương thích và loại bỏ bản còn lại khỏi dependency graph. Công cụ build nên quản lý phiên bản tập trung để tránh JAR trùng lặp ở runtime.

### 11.4. Relocate package khi đóng gói thư viện phụ thuộc

Một số thư viện được đóng gói cùng dependency bằng kỹ thuật shading/relocation. Package của dependency được đổi sang namespace riêng để tránh va chạm với phiên bản mà ứng dụng khác cung cấp.

Đây là quyết định đóng gói cần kiểm soát cẩn thận:

- không đổi package của API công khai ngoài ý muốn;
- kiểm tra resource, service descriptor và reflection string;
- đảm bảo license và thông tin nguồn gốc dependency vẫn được giữ theo yêu cầu.

### 11.5. Dùng automatic module như bước chuyển đổi có kiểm soát

Nếu thư viện chưa có **module-info.java**, automatic module có thể là bước chuyển tiếp để đưa nó vào module path. Nhưng cần kiểm tra:

- tên module tự động có ổn định không;
- package nào được export;
- có split package với module khác không;
- dependency có module name bị trùng không.

Automatic module không tự sửa package trùng. Nó chỉ cung cấp cách đặt một JAR chưa modular vào module graph.

### 11.6. Không dùng add-exports để chữa split package

**--add-exports** bổ sung quyền export một package từ module này cho module khác trong một số tình huống tương thích. Nó không hợp nhất hai package bị chia và không giải quyết xung đột khi hai module cùng export package trùng cho một consumer.

Tương tự, **--add-opens** phục vụ reflection sâu; nó không phải công cụ sửa package collision. Hãy giải quyết nguyên nhân ở dependency/module layout.

## 12. Quy trình biên dịch và chạy trong Java 17

Khi làm việc với ứng dụng modular, có thể theo quy trình:

1. Xác định các module và package thuộc từng module.
2. Đặt **module-info.java** tại gốc source/module tương ứng.
3. Khai báo **requires** cho dependency module.
4. Export đúng package API bằng **exports**.
5. Đặt modular JAR hoặc exploded module lên module path.
6. Biên dịch bằng **javac** với module source path hoặc module path phù hợp.
7. Chạy bằng **java --module-path** và chọn module entry point.
8. Nếu có lỗi, kiểm tra module name, readability, exports và split package trước khi thêm các tùy chọn tương thích.

Ví dụ lệnh biên dịch và chạy:

~~~bash
javac --module-source-path src -d out \
    -m com.acme.greetings,com.acme.app

java --module-path out \
    -m com.acme.app/com.acme.app.Main
~~~

Với ứng dụng classpath, quy trình đơn giản hơn:

~~~bash
javac -cp "lib/*" -d out src/com/acme/app/Main.java
java -cp "out:lib/*" com.acme.app.Main
~~~

Ở Windows, thay dấu hai chấm trong classpath bằng dấu chấm phẩy. Wildcard lib/* giúp đưa các JAR trong thư mục vào classpath; nó không biến chúng thành named modules.

## 13. Các lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân | Cách xử lý |
| --- | --- | --- |
| **ClassNotFoundException** | Class không có trong classpath/module path phù hợp hoặc tên class sai. | Kiểm tra lệnh chạy, vị trí JAR và binary name. |
| **NoClassDefFoundError** | Class cần thiết không được nạp tại runtime hoặc quá trình khởi tạo class thất bại. | Kiểm tra dependency runtime, classpath/module path và nguyên nhân khởi tạo gốc. |
| **module not found** | Module name trong **requires** không được tìm thấy trên module path. | Dùng **jar --describe-module**, kiểm tra tên module và đường dẫn. |
| Package không được export | Module đọc được dependency nhưng package cần dùng không được export. | Thêm **exports** phù hợp trong module cung cấp API hoặc dùng API công khai đúng. |
| Named module không đọc được class trên classpath | Classpath JAR thuộc unnamed module; named module không đọc nó mặc định. | Đưa JAR lên module path nếu phù hợp hoặc dùng **--add-reads** như cầu nối chuyển đổi. |
| Xung đột split package | Nhiều module export cùng package tới một consumer. | Gộp package về một module, đổi namespace hoặc loại dependency trùng. |
| **NoSuchMethodError** sau khi chạy | Runtime nạp phiên bản class khác với phiên bản đã dùng khi biên dịch. | Loại JAR trùng, thống nhất dependency và kiểm tra thứ tự classpath. |
| Hai module cùng tên | Có nhiều artifact khai báo cùng module name trong module path. | Chọn một artifact/version và loại bản trùng khỏi module path. |
| JAR cũ chạy trên classpath nhưng lỗi khi chuyển module path | Automatic module hoặc JPMS làm lộ dependency, exports hay package conflict. | Kiểm tra descriptor, module graph và split package; chuyển đổi theo từng dependency. |
| Dùng **--add-opens** để sửa lỗi compile package | Nhầm quyền reflection với readability/export. | Dùng **requires**/**exports** đúng mục tiêu; **opens** chỉ dành cho reflection sâu. |

## 14. Bài tập tự luyện

### Bài 1 — Chọn classpath hay module path

Một chương trình nhỏ chỉ có **Main.java** và hai JAR chưa có module descriptor. Hãy viết lệnh **javac** và **java** dùng classpath để biên dịch và chạy chương trình. Sau đó giải thích các class được đặt trong module nào.

### Bài 2 — Đọc module descriptor

Cho module:

~~~java
module com.acme.orders {
    requires com.acme.common;
    exports com.acme.orders.api;
}
~~~

Trả lời:

1. Module này đọc module nào?
2. Package nào được export?
3. Một module khác có thể dùng class trong package nội bộ chưa được export hay không?
4. **exports** khác **opens** ở điểm nào?

### Bài 3 — Tìm nguyên nhân split package

Hai module **com.vendor.one** và **com.vendor.two** đều export package **com.shared.util**. Module **com.acme.app** khai báo **requires** cả hai. Hãy giải thích vì sao consumer gặp xung đột và đề xuất cách tổ chức lại dependency.

### Bài 4 — Trùng class trên classpath

Hai JAR đều chứa **com.acme.Version**. Ứng dụng chạy được nhưng in ra phiên bản không mong muốn. Giải thích vai trò của thứ tự classpath và vì sao nên loại bản JAR trùng thay vì dựa vào thứ tự tìm kiếm.

### Bài 5 — Automatic module

Một JAR không có **module-info.class** được đặt trên module path. Hãy giải thích vì sao nó vẫn có thể được dùng trong **requires**, cách xác định tên module và những hạn chế của automatic module so với named module có descriptor.

### Bài 6 — Điều tra một ứng dụng không khởi động

Một ứng dụng báo **module not found** sau khi chuyển từ classpath sang module path. Hãy liệt kê các bước chẩn đoán bằng **jar --describe-module**, kiểm tra **module-info.java**, xem module path và bật **--show-module-resolution**.

## 15. Ghi nhớ khi dùng classpath và module path

- Classpath là cơ chế tìm class truyền thống; classpath classes thuộc unnamed module tương ứng với class loader.
- Module path tìm module theo tên; named module khai báo dependency và package API trong **module-info.java**.
- **requires** tạo readability; **exports** công khai package; **opens** phục vụ reflection sâu.
- JAR không có module descriptor trên module path có thể trở thành automatic module; kiểm tra tên bằng **jar --describe-module**.
- Named module không tự động đọc unnamed module; có thể dùng **--add-reads** như cầu nối chuyển đổi nhưng nên thiết kế dependency rõ ràng.
- Split package giữa các named modules gây xung đột khi cùng export package cho một consumer; hãy để một module sở hữu package.
- Trùng class trên classpath có thể khiến class loader nạp phiên bản theo thứ tự tìm kiếm, gây lỗi liên kết khó phát hiện.
- Tránh nhiều phiên bản của cùng dependency và nhiều module cùng tên trên module path.
- Dùng **jar --describe-module**, **java --show-module-resolution** và **jdeps --check** để điều tra cấu trúc module.
- Không dùng **--add-exports** hoặc **--add-opens** như cách chữa split package; hãy sửa dependency và ranh giới module.

### Tài liệu tham khảo

- [Java SE 17 API — Module](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Module.html) — mô hình module ở runtime.
- [Java SE 17 API — ModuleLayer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ModuleLayer.html) — module layer và module graph.
- [Java SE 17 javac documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html) — **--module-path**, **--module-source-path**, **--module** và các tùy chọn biên dịch.
- [Java SE 17 java documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html) — classpath, module path, **--module**, **--add-reads** và **--show-module-resolution**.
- [Java SE 17 jar documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html) — đóng gói JAR và **--describe-module**.
- [Java SE 17 jdeps documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html) — phân tích dependency và kiểm tra module.
- [JEP 261: Module System](https://openjdk.org/jeps/261) — thiết kế hệ thống module Java.
