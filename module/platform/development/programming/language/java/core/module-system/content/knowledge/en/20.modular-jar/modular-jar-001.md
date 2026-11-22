# JAR modular và module-info.class

## Mục tiêu

Sau bài này, bạn có thể nhận biết một modular JAR, giải thích vai trò của module-info.class, đọc các khai báo module cơ bản, biên dịch và đóng gói một module thành JAR, rồi kiểm tra và chạy JAR đó trên module path.

## 1. Modular JAR là gì?

JAR (Java ARchive) là định dạng đóng gói dựa trên ZIP, thường chứa các file .class, tài nguyên và metadata của ứng dụng Java. Một JAR có thể chứa một ứng dụng hoặc thư viện, nhưng bản thân việc đóng gói thành JAR không tự động biến nó thành một Java module.

Một **modular JAR** là JAR chứa module descriptor đã biên dịch, tức file module-info.class ở thư mục gốc của JAR. Descriptor xác định tên module và các quan hệ mà Java Platform Module System (JPMS) cần biết: module phụ thuộc module nào, package nào được export, package nào được mở cho reflection, module sử dụng service nào và module cung cấp service nào.

Ví dụ, một JAR có cấu trúc:

~~~text
com.acme.geometry.jar
  META-INF/
    MANIFEST.MF
  module-info.class
  com/
    acme/
      geometry/
        api/
          Point.class
          Shape.class
        internal/
          ShapeFactory.class
~~~

Nếu module-info.class hợp lệ nằm ở cấp gốc, JAR này là một explicit module. Tên module được khai báo trong descriptor, chẳng hạn com.acme.geometry; nó không nhất thiết phải giống tên file JAR.

Modular JAR vẫn là file JAR thông thường về mặt định dạng lưu trữ. Điểm làm nó trở thành explicit module là descriptor, không phải phần mở rộng .jar hay một kiểu đóng gói nhị phân khác.

## 2. module-info.java và module-info.class

Khi phát triển module, lập trình viên viết descriptor ở dạng nguồn trong file module-info.java. Trình biên dịch javac biên dịch file này thành module-info.class cùng với các lớp Java còn lại của module.

Ví dụ:

~~~java
module com.acme.geometry {
    exports com.acme.geometry.api;
}
~~~

Khai báo trên có nghĩa:

- Tên module là com.acme.geometry.
- Package com.acme.geometry.api được export để module khác có thể truy cập các kiểu public trong package đó.
- Các package khác của module không tự động được export.
- Module có quan hệ phụ thuộc ngầm định vào java.base, vì mọi module Java đều phụ thuộc vào module nền tảng này.

module-info.class là metadata nhị phân mà công cụ và runtime đọc để phân giải module. Nó không phải lớp Java thông thường để ứng dụng tạo instance, gọi constructor hay import như một API. Trong class file, module descriptor được biểu diễn bằng cấu trúc đặc biệt của JVM dành cho module.

Thông thường, mỗi explicit module có đúng một module-info.class ở gốc module. Với modular JAR, file này xuất hiện ở gốc JAR; với module dạng thư mục đã biên dịch (exploded module), nó xuất hiện ở gốc thư mục module.

## 3. Những chỉ thị thường có trong module descriptor

Module descriptor dùng các chỉ thị để mô tả API và quan hệ phụ thuộc:

| Chỉ thị | Ý nghĩa |
|---|---|
| requires module.name; | Module cần đọc một module khác |
| requires transitive module.name; | Module phụ thuộc và truyền khả năng đọc đó tới module phụ thuộc vào nó |
| requires static module.name; | Dependency cần lúc biên dịch nhưng không bắt buộc có mặt lúc chạy |
| exports package.name; | Cho phép module khác truy cập các kiểu public trong package |
| exports package.name to other.module; | Chỉ export package cho các module được nêu tên |
| opens package.name; | Cho phép truy cập reflective sâu vào package tại runtime |
| opens package.name to other.module; | Chỉ mở package cho các module được nêu tên |
| uses service.Type; | Khai báo module sử dụng một service |
| provides service.Type with ProviderType; | Đăng ký lớp cung cấp service |

Ví dụ descriptor của một module thư viện:

~~~java
module com.acme.report {
    requires java.sql;
    requires transitive com.acme.model;

    exports com.acme.report.api;
    exports com.acme.report.spi to com.acme.report.engine;

    opens com.acme.report.dto to com.fasterxml.jackson.databind;

    uses com.acme.report.spi.Formatter;
    provides com.acme.report.spi.Formatter
        with com.acme.report.internal.HtmlFormatter;
}
~~~

Một vài điểm cần phân biệt:

- requires thiết lập quan hệ đọc module. Nó không tự động export package của module được yêu cầu.
- exports phục vụ truy cập thông thường tới kiểu public của package. Nó không đồng nghĩa với việc mở toàn bộ package cho reflective access.
- opens phục vụ reflection sâu, ví dụ framework cần truy cập field hoặc constructor không public. Một package được opens không có nghĩa các kiểu của package trở thành API công khai thông thường.
- requires transitive hữu ích khi API công khai của module này để lộ kiểu thuộc module dependency; module sử dụng API có thể cần đọc dependency đó.
- requires static biểu diễn dependency tùy chọn ở runtime. Nếu module đó có mặt, quan hệ đọc vẫn được áp dụng.
- uses và provides là các khai báo của cơ chế ServiceLoader; chúng không thay thế requires và exports.

Tên module nên ổn định, có ý nghĩa và thường dùng dạng tên miền đảo ngược, ví dụ com.acme.geometry. Không nên dùng tên package hoặc tên file JAR một cách tùy tiện để thay cho việc xác định module name.

## 4. Cấu trúc một module trước khi đóng gói

Ví dụ module đơn giản tên com.acme.hello:

~~~text
src/
  com.acme.hello/
    module-info.java
    com/
      acme/
        hello/
          api/
            Greeter.java
          app/
            Main.java
~~~

File module-info.java:

~~~java
module com.acme.hello {
    exports com.acme.hello.api;
}
~~~

File Greeter.java:

~~~java
package com.acme.hello.api;

public class Greeter {
    public String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

File Main.java:

~~~java
package com.acme.hello.app;

import com.acme.hello.api.Greeter;

public class Main {
    public static void main(String[] args) {
        Greeter greeter = new Greeter();
        System.out.println(greeter.greet("Java module"));
    }
}
~~~

Package chứa Main không cần export nếu không có module khác cần truy cập các kiểu public trong package đó. Java vẫn có thể khởi chạy main class của module theo tên module và tên lớp.

## 5. Biên dịch module thành các class file

Đứng tại thư mục dự án có thư mục src, chạy:

~~~bash
javac -d out --module-source-path src -m com.acme.hello
~~~

Ý nghĩa các tùy chọn:

- -d out chỉ định thư mục chứa kết quả biên dịch.
- --module-source-path src cho javac biết cấu trúc thư mục nguồn theo module.
- -m com.acme.hello yêu cầu biên dịch module có tên đó.

Sau khi biên dịch, cấu trúc đầu ra có dạng:

~~~text
out/
  com.acme.hello/
    module-info.class
    com/
      acme/
        hello/
          api/
            Greeter.class
          app/
            Main.class
~~~

Hãy chú ý vị trí của module-info.class: nó nằm ngay trong thư mục gốc của module, cùng cấp với cây package com. Nếu file nguồn module-info.java không được biên dịch hoặc bị đặt sai vị trí, kết quả sẽ không có descriptor đúng để đóng gói thành explicit modular JAR.

Với một module đơn giản, có thể biên dịch bằng cách chỉ rõ từng file nguồn và ghi kết quả vào một thư mục. Cách dùng --module-source-path hữu ích hơn khi dự án có nhiều module theo cùng một quy ước thư mục.

## 6. Đóng gói thành modular JAR

Tạo thư mục mods nếu chưa có, sau đó đóng gói nội dung đã biên dịch:

~~~bash
mkdir -p mods

jar --create \
    --file mods/com.acme.hello.jar \
    --main-class com.acme.hello.app.Main \
    -C out/com.acme.hello .
~~~

Giải thích:

- --create tạo một JAR mới.
- --file chỉ định đường dẫn và tên file đầu ra.
- --main-class khai báo lớp main của ứng dụng; với modular JAR, jar ghi thông tin lớp khởi chạy vào metadata module để có thể chạy module mà không cần nêu lớp main ở dòng lệnh.
- -C chuyển thư mục làm việc của jar tới thư mục module đã biên dịch, rồi thêm toàn bộ nội dung tại đó. Vì vậy module-info.class được đặt ở gốc JAR.

Có thể bỏ --main-class nếu module chỉ là thư viện và không có điểm khởi chạy. Khi đó, người dùng vẫn có thể dùng module từ ứng dụng khác, nhưng không thể yêu cầu Java tự chọn main class của module.

Tên file thường được đặt gần với tên module để dễ quản lý, nhưng tên module thực sự vẫn do module-info.class quyết định.

## 7. Kiểm tra nội dung và descriptor của JAR

Dùng jar --list để xem các entry:

~~~bash
jar --list --file mods/com.acme.hello.jar
~~~

Trong kết quả, hãy xác nhận module-info.class nằm ở gốc JAR, không bị đặt trong một thư mục con ngoài ý muốn.

Dùng jar --describe-module để xem thông tin module:

~~~bash
jar --describe-module --file mods/com.acme.hello.jar
~~~

Kết quả có thể cho biết tên module, các package được export, các dependency như java.base và main class nếu đã khai báo. Ví dụ rút gọn:

~~~text
com.acme.hello jar:file:///.../com.acme.hello.jar!/module-info.class
exports com.acme.hello.api
requires java.base mandated
main-class com.acme.hello.app.Main
~~~

Có thể xem chi tiết cấu trúc class file bằng javap:

~~~bash
javap -v -p --module-path mods --module com.acme.hello module-info
~~~

javap hiển thị các thuộc tính trong class file, bao gồm phần metadata module. Đây là cách hữu ích để quan sát kết quả biên dịch ở mức bytecode khi cần tìm hiểu descriptor được lưu như thế nào.

## 8. Chạy modular JAR trên module path

Dùng module path để chạy ứng dụng:

~~~bash
java --module-path mods --module com.acme.hello
~~~

Có thể viết ngắn hơn bằng các tùy chọn tương đương:

~~~bash
java -p mods -m com.acme.hello
~~~

Vì JAR đã khai báo main class, Java có thể tìm điểm khởi chạy từ metadata module. Nếu không khai báo main class khi đóng gói, hãy nêu rõ lớp cần chạy:

~~~bash
java --module-path mods \
     --module com.acme.hello/com.acme.hello.app.Main
~~~

Kết quả dự kiến:

~~~text
Hello, Java module!
~~~

Nếu module phụ thuộc vào module khác, các module dependency cần có mặt trên module path để Java phân giải được đồ thị module. Tùy cách đóng gói ứng dụng, module path có thể chứa nhiều modular JAR hoặc thư mục module đã biên dịch.

## 9. Module path và classpath xử lý JAR khác nhau thế nào?

Cùng một file JAR có thể được đưa vào classpath hoặc module path, nhưng cách Java nhìn nhận nó khác nhau:

| Vị trí JAR | Cách Java xem JAR |
|---|---|
| Classpath (-cp hoặc -classpath) | Các lớp thuộc unnamed module; module-info.class trong JAR không được dùng để phân giải JPMS |
| Module path, có module-info.class hợp lệ | Explicit named module; tên và quan hệ module lấy từ descriptor |
| Module path, không có module-info.class | Có thể được xem như automatic module |

Điều này có nghĩa là đặt một modular JAR lên classpath không kích hoạt các quy tắc exports, requires hay opens của descriptor. Khi muốn dùng JPMS đúng nghĩa, hãy chạy hoặc biên dịch với module path.

Một module path có thể chứa cả explicit module và automatic module. Tuy nhiên, automatic module chỉ là cầu nối giúp thư viện JAR cũ tham gia module graph; nó không cung cấp mức đóng gói rõ ràng như explicit module.

## 10. Phân biệt modular JAR và automatic module

Đây là hai khái niệm dễ nhầm:

**Explicit modular JAR**

- Có module-info.class ở gốc JAR.
- Tên module và các chỉ thị được khai báo rõ ràng trong module descriptor.
- Package không được exports hoặc opens sẽ chịu quy tắc đóng gói của JPMS.
- Thường được tạo bằng cách biên dịch module-info.java cùng mã nguồn module.

**Automatic module**

- JAR không có module-info.class ở gốc.
- Khi đặt trên module path, Java có thể coi JAR đó là một module có tên.
- Nếu manifest có thuộc tính Automatic-Module-Name, thuộc tính đó cung cấp tên module ổn định.
- Nếu không có thuộc tính này, tên module được suy ra từ tên file JAR và có thể thay đổi khi tên file thay đổi.
- Automatic module có hành vi tương thích rộng để hỗ trợ thư viện cũ, chẳng hạn export các package của nó và đọc các module khác theo quy tắc automatic module.

Ví dụ manifest của một thư viện JAR cũ có thể khai báo:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.acme.legacy
~~~

Khai báo này giúp tên automatic module ổn định khi JAR được đưa lên module path. Tuy nhiên, nó không biến JAR thành explicit modular JAR và cũng không thay thế module-info.class.

Dùng jar --describe-module --file legacy-library.jar để xem công cụ nhận diện module. Với JAR không có descriptor, kết quả sẽ thể hiện đây là automatic module hoặc cho biết tên được suy ra.

## 11. Các lỗi đóng gói thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách kiểm tra hoặc xử lý |
|---|---|---|
| JAR không được nhận là explicit module | Thiếu module-info.class ở gốc JAR | Chạy jar --list và kiểm tra vị trí descriptor |
| Không tìm thấy module khi chạy | Đặt JAR ngoài module path hoặc gõ sai tên module | Kiểm tra --module-path và jar --describe-module |
| Module name khác tên file | Tên trong module-info.java là nguồn xác định tên explicit module | Dùng jar --describe-module để xác nhận tên thật |
| Package không truy cập được từ module khác | Package chưa được exports hoặc module chưa đọc module chứa package | Kiểm tra exports và requires |
| Framework không truy cập được field/constructor qua reflection | Package chưa được mở cho framework | Dùng opens hoặc opens ... to ... phù hợp |
| Ứng dụng chạy được trên classpath nhưng lỗi trên module path | Ứng dụng chưa khai báo dependency hoặc package access theo JPMS | Kiểm tra descriptor và các quan hệ module |
| JAR cũ có tên automatic module thay đổi | Tên được suy ra từ tên file JAR | Khai báo Automatic-Module-Name trong manifest hoặc chuyển thư viện sang explicit module |

Một lỗi đóng gói phổ biến là thêm nhầm cả thư mục chứa module vào JAR, khiến module-info.class không nằm ở gốc. Với lệnh jar, cần chọn đúng thư mục làm việc bằng -C và thêm nội dung bên trong thư mục module đã biên dịch.

Khi có nhiều module, hãy đóng gói từng module vào một JAR riêng hoặc một thư mục module riêng trên module path. Không nên gom các module độc lập vào một JAR duy nhất theo cách làm mất ranh giới module và descriptor của từng module.

## 12. Khi nào nên tạo modular JAR?

Nên tạo explicit modular JAR khi bạn phát triển thư viện hoặc ứng dụng cần:

- Khai báo rõ module nào là dependency.
- Kiểm soát package nào được cung cấp như API công khai.
- Giảm truy cập vô tình vào package nội bộ.
- Mô tả nhu cầu reflection bằng opens.
- Khai báo service consumer/provider bằng uses và provides.
- Phân phối module có tên và descriptor ổn định cho các ứng dụng khác.

Với thư viện cũ chưa thể chuyển ngay sang JPMS, automatic module có thể là bước chuyển tiếp. Với module mới do bạn kiểm soát, nên khai báo module-info.java và phát hành explicit modular JAR để quan hệ module được mô tả rõ ràng.

## Ghi nhớ

JAR chỉ là định dạng đóng gói; modular JAR là JAR có module-info.class ở gốc. File module-info.java được javac biên dịch thành descriptor nhị phân, chứa tên module và các chỉ thị requires, exports, opens, uses, provides. Dùng jar --describe-module để kiểm tra descriptor, jar --list để xác nhận vị trí file và java --module-path để chạy module. JAR không có descriptor khi nằm trên module path có thể trở thành automatic module, còn khi nằm trên classpath thì các quy tắc JPMS không được áp dụng.