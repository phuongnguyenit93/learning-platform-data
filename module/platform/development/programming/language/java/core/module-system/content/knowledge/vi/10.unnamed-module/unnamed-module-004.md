# Classpath library khi ứng dụng đã modular

Một ứng dụng Java đã sử dụng Java Platform Module System (JPMS) vẫn có thể cần các thư viện cũ chưa có file module-info.java. Những thư viện này có thể tiếp tục nằm trên classpath trong khi ứng dụng chính được biên dịch và khởi chạy như một named module trên module path.

Đây là cách chuyển đổi theo từng bước: ứng dụng giữ module descriptor và module graph của mình, còn thư viện chưa modular hóa được nạp vào unnamed module. Điểm cần xử lý là quan hệ đọc giữa named module và unnamed module. Theo mặc định, named module không đọc unnamed module, vì vậy ứng dụng thường cần tùy chọn **--add-reads** khi biên dịch và khi chạy.

## 1. Mô hình kết hợp module path và classpath

Giả sử ứng dụng có cấu trúc:

~~~text
application/
├── src/
│   └── com.example.app/
│       ├── module-info.java
│       └── com/example/app/Main.java
├── mods/
│   └── com.example.api.jar
└── libs/
    ├── legacy-client.jar
    └── legacy-codec.jar
~~~

Trong đó:

- **com.example.app** là explicit named module, có module-info.java.
- **com.example.api.jar** là modular JAR trên module path.
- **legacy-client.jar** và **legacy-codec.jar** là thư viện chưa có module descriptor, được đặt trên classpath.

Khi ứng dụng chạy, module system phân giải named module trên module path. Các JAR nằm trên classpath được nạp vào unnamed module của application class loader. Các JAR classpath không tự trở thành những named module riêng biệt chỉ vì ứng dụng chính đã modular hóa.

Mô hình khái quát:

~~~text
                  JVM
                   |
        +----------+-----------+
        |                      |
    Module path             Classpath
        |                      |
        v                      v
  Named modules           Unnamed module
        |                      |
  com.example.app        legacy-client.jar
  com.example.api        legacy-codec.jar
        |
        |  --add-reads
        +---------------------> Unnamed module
~~~

Named module và unnamed module có thể cùng tồn tại trong một tiến trình. Cần cấu hình quan hệ đọc phù hợp để mã trong named module tham chiếu được class của thư viện classpath.

## 2. Unnamed module và quy tắc đọc module

Mỗi class loader có một unnamed module. Với ứng dụng thông thường, các class và JAR trên classpath được đặt trong unnamed module của application class loader.

Unnamed module có hai đặc điểm quan trọng:

- Nó đọc tất cả named module.
- Tất cả package của nó được export và open.

Chiều ngược lại không tự động đúng: một named module không đọc unnamed module theo mặc định. Vì vậy, dù một JAR đã xuất hiện trên classpath và class loader có thể tìm bytecode của nó, mã trong named module vẫn có thể gặp lỗi biên dịch hoặc truy cập do thiếu quan hệ đọc.

Không thể viết một directive như sau trong module-info.java:

~~~java
module com.example.app {
    requires ALL-UNNAMED;
}
~~~

**ALL-UNNAMED** là tên đích đặc biệt dành cho các tùy chọn dòng lệnh của Java compiler và launcher. Nó không phải tên module hợp lệ để khai báo trong requires. Muốn thêm quan hệ đọc từ named module tới unnamed module, hãy dùng **--add-reads**.

## 3. Khai báo dependency của ứng dụng modular

Giả sử thư viện classpath cung cấp class:

~~~java
// legacy-client.jar
package com.legacy.client;

public final class LegacyClient {
    public String fetch() {
        return "data from legacy service";
    }
}
~~~

Ứng dụng modular sử dụng class đó:

~~~java
// src/com.example.app/com/example/app/Main.java
package com.example.app;

import com.legacy.client.LegacyClient;

public class Main {
    public static void main(String[] args) {
        LegacyClient client = new LegacyClient();
        System.out.println(client.fetch());
    }
}
~~~

Descriptor của ứng dụng có thể khai báo dependency tới các named module khác:

~~~java
module com.example.app {
    requires com.example.api;
}
~~~

Không thêm requires cho thư viện legacy trên classpath vì thư viện đó không có tên module riêng trong cấu hình này. Thay vào đó, compiler và JVM cần được cấp quan hệ đọc tới unnamed module bằng tùy chọn **--add-reads com.example.app=ALL-UNNAMED**.

## 4. Biên dịch: classpath cho thư viện, module path cho module

Khi biên dịch ứng dụng modular, cần phân biệt hai đường tìm kiếm:

- **--module-path** chứa các named module mà compiler cần phân giải.
- **--class-path** chứa thư viện cũ và class không thuộc named module.

Ví dụ trên Linux hoặc macOS:

~~~bash
javac --module-source-path src --module-path mods --class-path "libs/*" --add-reads com.example.app=ALL-UNNAMED -d out -m com.example.app
~~~

Giải thích:

- **--module-source-path src** cho compiler biết nơi chứa source của các module.
- **--module-path mods** cho compiler tìm các named module, ví dụ **com.example.api**.
- **--class-path "libs/*"** đưa các JAR legacy vào classpath trong quá trình biên dịch.
- **--add-reads com.example.app=ALL-UNNAMED** cho phép module ứng dụng đọc unnamed module để tham chiếu class của thư viện classpath.
- **-d out** chỉ định thư mục output.
- **-m com.example.app** chọn module cần biên dịch.

Trên Windows, ký tự phân tách nhiều entry trong classpath là dấu chấm phẩy (**;**); trên Linux và macOS là dấu hai chấm (**:**). Wildcard **libs/*** đưa các JAR nằm trực tiếp trong thư mục libs vào classpath, không tìm đệ quy các thư mục con.

Nếu bỏ **--add-reads**, compiler có thể báo package từ thư viện legacy không được nhìn thấy hoặc module không đọc được package đó. Khi gặp lỗi này, hãy xác định thư viện thực sự đang nằm trên classpath hay module path trước khi thay đổi descriptor.

## 5. Chạy: truyền lại classpath và quan hệ đọc

Tùy chọn dùng lúc biên dịch không tự động trở thành cấu hình runtime. Khi chạy, cần cung cấp lại classpath và quan hệ đọc cho JVM.

Linux hoặc macOS:

~~~bash
java --module-path "mods:out" --class-path "libs/*" --add-reads com.example.app=ALL-UNNAMED -m com.example.app/com.example.app.Main
~~~

Windows PowerShell:

~~~powershell
java --module-path "mods;out" --class-path "libs/*" --add-reads com.example.app=ALL-UNNAMED -m com.example.app/com.example.app.Main
~~~

Các thành phần có ý nghĩa:

- **--module-path** chứa module ứng dụng đã biên dịch và các named dependency.
- **--class-path** chứa các thư viện legacy cần thiết ở runtime.
- **--add-reads** thêm quan hệ đọc từ named module tới unnamed module.
- **-m module/class** khởi chạy class main thuộc named module.

Classpath runtime phải chứa cả những dependency gián tiếp mà thư viện legacy cần khi thực thi. Một JAR có mặt lúc biên dịch nhưng thiếu ở runtime vẫn có thể gây **NoClassDefFoundError**.

Không nên chỉ dựa vào classpath của terminal hoặc IDE. Script chạy, container và cấu hình triển khai phải truyền cùng tập thư viện và các tùy chọn module cần thiết.

## 6. ALL-UNNAMED có ý nghĩa gì?

**ALL-UNNAMED** đại diện cho tất cả unnamed module, không phải một module có tên cố định. Một số tùy chọn module của Java sử dụng nó để áp dụng một quan hệ hoặc quyền truy cập cho các module không có tên.

Ví dụ:

~~~bash
--add-reads com.example.app=ALL-UNNAMED
~~~

Có nghĩa là named module **com.example.app** được phép đọc các unnamed module.

Tùy chọn này có thể được dùng khi biên dịch và chạy. Nếu chỉ thêm ở runtime, compiler vẫn có thể từ chối mã nguồn tham chiếu thư viện classpath. Nếu chỉ thêm khi biên dịch, ứng dụng có thể biên dịch thành công nhưng lỗi lúc chạy vì module graph runtime vẫn thiếu quan hệ đọc.

Không nên nhầm các tùy chọn sau:

| Tùy chọn | Mục đích |
| --- | --- |
| --add-reads | Thêm quan hệ đọc giữa module nguồn và module đích |
| --add-exports | Cho phép module đích truy cập một package của module nguồn |
| --add-opens | Cho phép deep reflection vào package của module nguồn |

Khi named module cần gọi API public từ thư viện classpath, thường cần **--add-reads**. Nếu thư viện classpath cần truy cập package của named module, có thể phải xem xét quyền export hoặc open ở chiều ngược lại.

## 7. Khi thư viện classpath cần truy cập package của ứng dụng modular

Một trường hợp khác là thư viện legacy nằm trên classpath dùng reflection hoặc gọi API thuộc named module của ứng dụng.

Giả sử module ứng dụng có package:

~~~java
module com.example.app {
    exports com.example.app.api;
}
~~~

Unnamed module có thể đọc named module, nhưng package của named module chỉ được export theo các directive và cấu hình module tương ứng. Nếu thư viện classpath cần truy cập một package cụ thể, có thể dùng **--add-exports** để cấp quyền truy cập API cho tất cả unnamed module:

~~~bash
--add-exports com.example.app/com.example.app.internal=ALL-UNNAMED
~~~

Nếu framework trên classpath cần deep reflection vào private member của package:

~~~bash
--add-opens com.example.app/com.example.app.model=ALL-UNNAMED
~~~

Hai tùy chọn có mục đích khác nhau:

- **--add-exports** cho phép truy cập các kiểu public trong package.
- **--add-opens** cho phép deep reflection vào package.

Chỉ thêm quyền khi có thư viện cụ thể yêu cầu. Không nên mở toàn bộ package của ứng dụng cho ALL-UNNAMED vì điều đó làm giảm hiệu quả encapsulation mà JPMS cung cấp.

## 8. Giữ thư viện trên classpath hay chuyển thành automatic module?

Một JAR legacy không có module-info.class có thể được xử lý theo hai cách khi ứng dụng modular.

**Cách A: Giữ JAR trên classpath**

JAR thuộc unnamed module. Ứng dụng cần thêm quan hệ đọc với ALL-UNNAMED nếu named module tham chiếu class trong thư viện. Cách này phù hợp khi muốn giữ nguyên cách chạy legacy trong giai đoạn chuyển đổi.

**Cách B: Đặt JAR trên module path**

Nếu JAR không có module-info.class nhưng được đặt trên module path, Java có thể coi nó là automatic module. Tên module có thể được lấy từ thuộc tính manifest **Automatic-Module-Name** hoặc suy ra từ tên JAR.

Khi đó, ứng dụng khai báo requires bằng tên automatic module:

~~~java
module com.example.app {
    requires com.legacy.client;
}
~~~

Ứng dụng không cần dùng quan hệ **--add-reads ...=ALL-UNNAMED** cho dependency đó vì nó đã được nhận diện như một named automatic module.

Automatic module thường export các package của nó và có khả năng đọc các named module khác. Điều này giúp thư viện cũ tham gia vào module graph, nhưng không tạo ra ranh giới encapsulation chặt như explicit named module.

| Tiêu chí | Classpath / unnamed module | Automatic module |
| --- | --- | --- |
| Vị trí | Classpath | Module path |
| Tên module | Không có tên tường minh | Tên từ manifest hoặc tên JAR |
| requires trong app | Không thể requires trực tiếp | Có thể requires theo tên automatic module |
| Quan hệ đọc từ app | Thường cần add-reads tới ALL-UNNAMED | Dùng dependency trong module graph |
| Encapsulation | Package của unnamed module được export và open | Các package được export theo hành vi automatic module |
| Mục tiêu | Tương thích và chuyển đổi từng bước | Bước trung gian để modular hóa dependency |

Nếu thư viện có thể được modular hóa chính thức, explicit module với module-info.java sẽ cho kết quả rõ ràng và kiểm soát tốt hơn automatic module.

## 9. Thư viện classpath và dependency bắc cầu

Classpath không có module descriptor để mô tả quan hệ requires. Vì vậy, ứng dụng hoặc công cụ build phải bảo đảm tất cả JAR cần thiết đều có mặt trên classpath runtime.

Ví dụ:

~~~text
libs/
├── legacy-client.jar
├── legacy-codec.jar
└── legacy-logging.jar
~~~

Nếu **legacy-client.jar** cần **legacy-codec.jar**, việc chỉ thêm client JAR vào classpath có thể đủ để biên dịch một phần mã nhưng chưa đủ để chạy. Hãy thêm các dependency runtime cần thiết:

~~~bash
--class-path "libs/*"
~~~

Wildcard chỉ mở rộng các JAR trong một thư mục. Nếu dependency được đặt trong **libs/codec/**, cần thêm thư mục đó bằng một entry classpath riêng.

Cũng cần tránh đưa nhiều phiên bản của cùng một thư viện vào classpath. Khi các JAR có class trùng tên, class loader có thể nạp phiên bản không mong đợi tùy theo thứ tự tìm kiếm. Dùng Maven hoặc Gradle để phân giải và khóa dependency giúp giảm lỗi này.

## 10. Tích hợp với Maven và Gradle

Trong dự án thực tế, không nên phải tự gõ một lệnh javac/java dài mỗi lần chạy. Hãy cấu hình build tool để giữ riêng compile classpath, module path và các tùy chọn module.

Với Maven, dependency legacy có thể được khai báo như dependency bình thường. Cấu hình compiler plugin có thể truyền tùy chọn **--add-reads** qua compiler arguments. Cấu hình chạy test hoặc ứng dụng cũng phải truyền tùy chọn tương ứng cho JVM fork hoặc Java launcher.

Với Gradle, dependency legacy thường được khai báo trong configuration phù hợp như **implementation**. Nếu build đang dùng module path inference hoặc cấu hình module path riêng, hãy kiểm tra dependency thực tế được đặt ở classpath hay module path. Các compiler argument có thể được cấu hình qua **options.compilerArgs**, còn JVM runtime argument có thể được truyền qua **applicationDefaultJvmArgs**, **JavaExec.jvmArgs** hoặc cấu hình test tương ứng.

Điều cần xác minh trong build:

- Thư viện legacy đang nằm trên classpath hay module path?
- Compiler có nhận **--add-reads** không?
- JVM chạy ứng dụng có nhận cùng tùy chọn không?
- Tất cả dependency bắc cầu của thư viện có mặt ở runtime không?
- Test runner và ứng dụng production có cùng cách phân giải module không?

Không nên suy ra vị trí dependency chỉ từ tên configuration. Hãy xem task command line hoặc báo cáo dependency của build tool để xác nhận.

## 11. Dùng ServiceLoader với thư viện legacy

Một số thư viện cũ cung cấp implementation thông qua file cấu hình service tại **META-INF/services/** thay vì khai báo **provides ... with** trong module descriptor.

Khi kết hợp service giữa named module và classpath, cần xác định rõ:

- Module chứa service interface.
- Module tiêu thụ service và directive **uses**.
- Thư viện provider đang ở classpath hay module path.
- Class loader nào được dùng để tìm provider.

Nếu provider nằm trong classpath, nó thuộc unnamed module và thường sử dụng cơ chế provider configuration file truyền thống. Với ứng dụng modular, hãy chọn overload **ServiceLoader** và class loader phù hợp với cách triển khai; kiểm tra provider có được tìm thấy từ class loader mà ứng dụng đang sử dụng hay không.

Khi có thể, nên chuyển provider thành named module và khai báo **provides ... with**. Cách đó làm quan hệ service rõ ràng trong module descriptor và module graph.

## 12. Lỗi thường gặp khi dùng classpath library trong modular app

**Package is not visible hoặc module không đọc được dependency**

Named module đang tham chiếu classpath library nhưng thiếu quan hệ đọc. Kiểm tra classpath và bổ sung **--add-reads module=ALL-UNNAMED** cho compiler và runtime.

**Biên dịch thành công nhưng runtime báo NoClassDefFoundError**

Một dependency của thư viện không có trên classpath runtime hoặc lệnh chạy không dùng cùng cấu hình với lệnh biên dịch. Kiểm tra toàn bộ dependency bắc cầu và script triển khai.

**ClassNotFoundException khi nạp theo tên**

Class loader được dùng để tìm class không nhìn thấy thư viện hoặc tên class sai. Kiểm tra classpath runtime, working directory và class loader truyền vào API nạp class.

**Thư viện legacy gọi API của named module và bị chặn**

Unnamed module đọc named module, nhưng package của named module có thể chưa export cho unnamed module. Kiểm tra **--add-exports**; nếu framework cần reflection sâu, xem xét **--add-opens**.

**Đã thêm --add-reads khi compile nhưng chạy vẫn lỗi**

Quan hệ đọc lúc biên dịch không tự động được chuyển sang runtime. Truyền lại tùy chọn **--add-reads** trong lệnh java hoặc cấu hình runtime của build tool.

**JAR có Automatic-Module-Name nhưng vẫn thuộc unnamed module**

Thuộc tính Automatic-Module-Name chỉ có ý nghĩa khi JAR được đặt trên module path để trở thành automatic module. Nếu JAR nằm trên classpath, nó vẫn thuộc unnamed module.

**Trùng class hoặc lệch phiên bản thư viện**

Kiểm tra dependency tree và thứ tự classpath. Loại bỏ các phiên bản trùng, khóa phiên bản và kiểm tra nguồn class thực tế được nạp khi cần.

## 13. Quan sát classpath và module runtime

Có thể in các system property để xem môi trường khởi chạy:

~~~java
System.out.println("java.class.path = "
    + System.getProperty("java.class.path"));

System.out.println("jdk.module.path = "
    + System.getProperty("jdk.module.path"));
~~~

Có thể kiểm tra module chứa một class:

~~~java
Class<?> type = com.legacy.client.LegacyClient.class;

System.out.println("Module: " + type.getModule());
System.out.println("ClassLoader: " + type.getClassLoader());
System.out.println("Is named: " + type.getModule().isNamed());
~~~

Nếu class thuộc unnamed module, **type.getModule().isNamed()** trả về false. Đây là cách xác nhận thư viện thực tế đang được nạp từ classpath theo mô hình unnamed module.

Để xem log class loading trên JDK 9 trở lên:

~~~bash
java -Xlog:class+load=info --module-path mods --class-path "libs/*" --add-reads com.example.app=ALL-UNNAMED -m com.example.app/com.example.app.Main
~~~

Log giúp tìm class nào được nạp và nguồn của nó, hữu ích khi có nhiều bản sao thư viện hoặc classpath khác nhau giữa local và production.

## 14. Lộ trình chuyển đổi dependency legacy

Có thể quản lý việc chuyển đổi theo các bước:

1. Liệt kê tất cả JAR legacy và dependency bắc cầu của chúng.
2. Xác định thư viện nào cần giữ trên classpath do chưa thể modular hóa.
3. Thêm classpath và **--add-reads** cho named module thực sự cần dùng các thư viện đó.
4. Kiểm tra riêng compile-time và runtime.
5. Nếu thư viện cần truy cập package nội bộ của ứng dụng, cấp **--add-exports** hoặc **--add-opens** đúng phạm vi và có lý do rõ ràng.
6. Khi thư viện ổn định, cân nhắc chuyển nó lên module path như automatic module.
7. Khi có thể sửa hoặc nâng cấp thư viện, bổ sung module-info.java để tạo explicit named module.
8. Gỡ các tùy chọn add-reads/add-exports/add-opens đã không còn cần thiết và kiểm tra lại ứng dụng.

Classpath library vẫn là một phần hợp lệ trong quá trình modular hóa Java. Nắm rõ unnamed module, quan hệ đọc, ALL-UNNAMED và sự khác nhau giữa classpath với module path giúp ứng dụng hiện đại tiếp tục dùng được thư viện cũ mà vẫn tiến dần tới cấu trúc module có dependency và API được kiểm soát.