# Kiểm tra hành vi trên cả class path và module path trong Java

Từ Java 9, JPMS (Java Platform Module System) bổ sung module path và module descriptor để kiểm soát phụ thuộc, khả năng đọc module và package được công bố. Tuy nhiên, classpath vẫn được hỗ trợ để chạy ứng dụng Java truyền thống và hỗ trợ quá trình chuyển đổi từng bước.

Điểm quan trọng là **cùng một JAR có thể có hành vi khác nhau tùy vị trí đặt nó**:

- Trên **classpath**, các lớp được nạp vào unnamed module của class loader. Nếu JAR có module-info.class, descriptor đó không được dùng để thiết lập ranh giới module trong lần chạy này.
- Trên **module path**, modular JAR có module-info.class trở thành named module; các directive như requires và exports được áp dụng.
- Một JAR không có module descriptor nếu đặt trên module path sẽ được nhận diện là automatic module; nếu đặt trên classpath, nó thuộc unnamed module.

Vì vậy, kiểm tra một ứng dụng trên cả hai đường dẫn giúp phát hiện khác biệt về phân giải dependency, đóng gói package và khả năng tương thích khi chuyển từ classpath sang JPMS.

## 1. Classpath và module path khác nhau thế nào?

| Tiêu chí | Classpath | Module path |
|---|---|---|
| Cách chỉ định | -cp hoặc --class-path | --module-path |
| Mô hình nạp lớp | Các lớp trên classpath thuộc unnamed module tương ứng với class loader | JAR hoặc thư mục module được phân giải thành named module hoặc automatic module |
| module-info.class trong modular JAR | Không được dùng để tạo named module trong lần chạy classpath | Được dùng làm module descriptor |
| requires | Không thiết lập quan hệ đọc trong lần chạy classpath | Thiết lập dependency và khả năng đọc giữa named module |
| exports | Không áp dụng như ranh giới module đối với các lớp trên classpath | Quy định package nào được module khác đọc sử dụng như API |
| Package không export | Public class vẫn có thể được truy cập từ classpath nếu thỏa quy tắc Java thông thường | Module khác không thể truy cập package qua ranh giới JPMS |
| JAR không có descriptor | Nằm trong unnamed module | Trở thành automatic module |
| Đóng gói | Linh hoạt và tương thích với hệ sinh thái classpath lâu đời | Ranh giới module rõ ràng, dependency được khai báo tường minh |

### 1.1. Classpath tạo unnamed module

Khi chạy bằng classpath, các lớp được nạp từ classpath thuộc unnamed module của class loader tương ứng. Unnamed module đọc các module quan sát được và các package của nó được công bố theo quy tắc unnamed module.

Nếu một JAR có module-info.class nhưng được đưa lên classpath, module descriptor không tham gia đồ thị module. Các directive requires, exports, opens, uses và provides trong descriptor không thiết lập ranh giới JPMS cho lần chạy đó.

Điều này không xóa bỏ quy tắc truy cập Java. Từ khóa private, protected, package-private và public vẫn có ý nghĩa; classpath chỉ không áp dụng ranh giới đóng gói giữa named module như module path.

### 1.2. Module path tạo named module hoặc automatic module

Một modular JAR có module-info.class được nhận diện là named module. Module descriptor quy định:

- Tên module.
- Các module cần đọc qua requires.
- Các package được công bố qua exports.
- Các package được mở cho reflection qua opens.
- Các service được sử dụng hoặc cung cấp qua uses và provides.

Một JAR không có module-info.class khi đặt trên module path trở thành automatic module. Tên của nó lấy từ thuộc tính Automatic-Module-Name trong manifest nếu có; nếu không, tên được suy ra từ tên file JAR.

Automatic module vẫn có tên và tham gia đồ thị module. Nó đọc các module quan sát được và tự động export các package của mình. Đây là cầu nối hữu ích cho thư viện chưa được modular hóa.

## 2. Ví dụ: cùng một modular JAR chạy trên hai đường dẫn

Ví dụ có hai module:

- com.example.greeter cung cấp API Greeting.
- com.example.app sử dụng API đó và khai báo requires com.example.greeter.

Cả hai JAR được biên dịch và đóng gói một lần. Sau đó, ta chạy chính các file JAR này trên classpath và module path để so sánh.

### 2.1. Cấu trúc nguồn

~~~text
src/
├── com.example.greeter/
│   ├── module-info.java
│   └── com/example/greeter/
│       ├── api/
│       │   └── Greeting.java
│       └── internal/
│           └── InternalMessage.java
└── com.example.app/
    ├── module-info.java
    └── com/example/app/
        └── Main.java
~~~

### 2.2. Module thư viện

File src/com.example.greeter/module-info.java:

~~~java
module com.example.greeter {
    exports com.example.greeter.api;
}
~~~

Module chỉ công bố package com.example.greeter.api. Package com.example.greeter.internal được giữ nội bộ.

File src/com.example.greeter/com/example/greeter/api/Greeting.java:

~~~java
package com.example.greeter.api;

public final class Greeting {
    private Greeting() {
    }

    public static String message(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

File src/com.example.greeter/com/example/greeter/internal/InternalMessage.java:

~~~java
package com.example.greeter.internal;

public final class InternalMessage {
    private InternalMessage() {
    }

    public static String value() {
        return "Internal package detail";
    }
}
~~~

InternalMessage là public, nhưng package chứa lớp này không được export trong module descriptor.

### 2.3. Module ứng dụng

File src/com.example.app/module-info.java:

~~~java
module com.example.app {
    requires com.example.greeter;
}
~~~

File src/com.example.app/com/example/app/Main.java:

~~~java
package com.example.app;

import com.example.greeter.api.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message("Ada"));
    }
}
~~~

Ứng dụng chỉ import API được export. Quan hệ requires cho phép module app đọc module greeter.

## 3. Biên dịch và đóng gói modular JAR

Từ thư mục chứa src, tạo thư mục đầu ra:

~~~bash
mkdir -p out mods
~~~

Biên dịch hai module cùng lúc:

~~~bash
javac -d out --module-source-path src -m com.example.greeter,com.example.app
~~~

Sau khi biên dịch, cấu trúc đầu ra có dạng:

~~~text
out/
├── com.example.greeter/
│   ├── module-info.class
│   └── com/example/greeter/
│       ├── api/Greeting.class
│       └── internal/InternalMessage.class
└── com.example.app/
    ├── module-info.class
    └── com/example/app/Main.class
~~~

Đóng gói từng module thành JAR:

~~~bash
jar --create --file mods/com.example.greeter.jar -C out/com.example.greeter .
jar --create --file mods/com.example.app.jar -C out/com.example.app .
~~~

Có thể kiểm tra descriptor của thư viện:

~~~bash
jar --describe-module --file mods/com.example.greeter.jar
~~~

Output quan trọng:

~~~text
com.example.greeter
exports com.example.greeter.api
requires java.base mandated
contains com.example.greeter.internal
~~~

Đường dẫn URI hoặc dòng đầu chi tiết có thể thay đổi theo vị trí file và phiên bản JDK. Các directive thể hiện package api được export, còn package internal chỉ được chứa trong module.

## 4. Chạy cùng JAR trên classpath

Classpath không tạo named module từ các descriptor trong JAR. Đặt cả hai JAR lên classpath:

Trên Windows PowerShell, dấu phân cách classpath là dấu chấm phẩy:

~~~powershell
java -cp "mods/com.example.app.jar;mods/com.example.greeter.jar" com.example.app.Main
~~~

Trên Linux hoặc macOS, dấu phân cách classpath là dấu hai chấm:

~~~bash
java -cp "mods/com.example.app.jar:mods/com.example.greeter.jar" com.example.app.Main
~~~

Kết quả stdout:

~~~text
Hello, Ada!
~~~

Ứng dụng vẫn chạy vì:

- Lớp Main được tìm thấy trên classpath.
- Lớp Greeting được tìm thấy trong JAR thư viện.
- Cả hai JAR được nạp như nội dung classpath thuộc unnamed module.
- module-info.class trong hai JAR không được dùng để tạo named module trong lần chạy này.
- Quan hệ requires và ranh giới exports không được áp dụng như khi chạy trên module path.

Lưu ý rằng public API vẫn phải thỏa quy tắc truy cập Java. Classpath không làm thành viên private trở thành public; nó chỉ không thực thi ranh giới package của named module.

## 5. Chạy cùng JAR trên module path

Đưa thư mục mods lên module path:

~~~bash
java --module-path mods -m com.example.app/com.example.app.Main
~~~

Kết quả stdout:

~~~text
Hello, Ada!
~~~

Lần chạy này khác với classpath:

- com.example.app và com.example.greeter là named module.
- JVM đọc module-info.class trong từng JAR.
- Module app phải đọc com.example.greeter theo requires.
- Module greeter chỉ công bố package com.example.greeter.api.
- Package internal không được export và bị bảo vệ bởi ranh giới JPMS.

Cùng một bộ JAR có thể chạy ở cả hai chế độ, nhưng cách kiểm tra quyền truy cập và phân giải dependency khác nhau.

## 6. Kiểm chứng package không export

Để thấy rõ khác biệt về đóng gói, thử import lớp public InternalMessage trong package không export.

Mã kiểm tra:

~~~java
package com.example.probe;

import com.example.greeter.internal.InternalMessage;

public class ClasspathProbe {
    public static void main(String[] args) {
        System.out.println(InternalMessage.value());
    }
}
~~~

### 6.1. Biên dịch và chạy trên classpath

~~~bash
javac -cp mods/com.example.greeter.jar -d cp-probe-out cp-probe-src/com/example/probe/ClasspathProbe.java
~~~

Trên Windows PowerShell:

~~~powershell
java -cp "cp-probe-out;mods/com.example.greeter.jar" com.example.probe.ClasspathProbe
~~~

Trên Linux hoặc macOS:

~~~bash
java -cp "cp-probe-out:mods/com.example.greeter.jar" com.example.probe.ClasspathProbe
~~~

Kết quả stdout:

~~~text
Internal package detail
~~~

Classpath cho phép probe sử dụng public class trong package này vì module descriptor của greeter không được áp dụng khi JAR nằm trên classpath. Quy tắc truy cập Java thông thường vẫn được áp dụng.

### 6.2. Biên dịch cùng mã trên module path

Tạo module descriptor cho probe:

~~~java
module com.example.probe {
    requires com.example.greeter;
}
~~~

Đặt module-info.java và ClasspathProbe.java trong cấu trúc nguồn của module com.example.probe, rồi biên dịch:

~~~bash
javac --module-path mods --module-source-path probe-module-src -d probe-module-out -m com.example.probe
~~~

Compiler từ chối truy cập package internal vì module greeter không export package đó. Diagnostic có dạng:

~~~text
error: package com.example.greeter.internal is not visible
(package com.example.greeter.internal is declared in module com.example.greeter, which does not export it)
~~~

Nếu package thực sự cần là API, module greeter phải công bố nó bằng exports. Nếu đó là chi tiết triển khai, hãy giữ package không export và cung cấp API công khai phù hợp.

Không nên thêm exports chỉ để làm mất lỗi biên dịch. Việc export package biến nó thành bề mặt API mà module khác có thể phụ thuộc.

## 7. JAR không có module descriptor trên hai đường dẫn

Một thư viện cũ có thể không chứa module-info.class.

Cùng JAR đó có cách tham gia runtime khác nhau:

| Vị trí JAR | Cách module system xử lý |
|---|---|
| Classpath | Các lớp thuộc unnamed module của class loader |
| Module path | JAR trở thành automatic module có tên |

### 7.1. Automatic-Module-Name

Tác giả thư viện có thể thêm thuộc tính Automatic-Module-Name vào manifest:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.legacy
~~~

Đóng gói thư viện và kiểm tra:

~~~bash
jar --create --file libs/legacy-utils.jar --manifest manifest.mf -C legacy-classes .
jar --describe-module --file libs/legacy-utils.jar
~~~

Output minh họa:

~~~text
No module descriptor found. Derived automatic module.

com.example.legacy automatic
requires java.base mandated
contains com.example.legacy
~~~

Khi manifest có Automatic-Module-Name, giá trị đó được dùng làm tên automatic module. Nếu không có thuộc tính này, tên được suy ra từ tên file JAR và có thể thay đổi khi tên file thay đổi.

Một named module có thể phụ thuộc vào automatic module bằng requires:

~~~java
module com.example.autoapp {
    requires com.example.legacy;
}
~~~

Biên dịch và chạy module consumer với JAR trên module path:

~~~bash
javac --module-path libs --module-source-path src-auto -d out-auto -m com.example.autoapp
java --module-path "libs;out-auto" -m com.example.autoapp/com.example.autoapp.Main
~~~

Trong ví dụ trên, dấu phân cách module path trên Windows là dấu chấm phẩy. Trên Linux hoặc macOS, thay bằng dấu hai chấm.

Automatic module tự động export các package và đọc các module quan sát được trong cấu hình. Nó là cơ chế chuyển tiếp để thư viện chưa có descriptor tham gia module path. Khi có thể, tác giả nên chuyển sang named module tường minh để kiểm soát requires và exports rõ ràng hơn.

## 8. Khác biệt về khả năng tương thích và cách chọn đường dẫn

| Tình huống | Classpath | Module path |
|---|---|---|
| Ứng dụng cũ chưa có module-info.java | Chạy trực tiếp theo cách truyền thống | Cần modular hóa ứng dụng hoặc dùng module phù hợp |
| Thư viện có module-info.class | Descriptor không được dùng trên classpath | Thành named module |
| Thư viện không có descriptor | Thuộc unnamed module | Thành automatic module |
| Muốn bảo vệ package triển khai | Không có ranh giới module cho package đó | Có thể giữ package không export |
| Muốn dependency được khai báo tường minh | Không có requires trong runtime classpath | Dùng requires trong module descriptor |
| Chuyển đổi hệ thống theo từng phần | Hỗ trợ các thành phần chưa modular hóa | Có thể kết hợp named module với automatic module |

### 8.1. Khi nào nên tiếp tục dùng classpath?

Classpath vẫn phù hợp khi:

- Ứng dụng hoặc thư viện chưa cần module descriptor.
- Tooling hoặc môi trường triển khai hiện tại dựa trên classpath.
- Đang chuyển đổi một hệ thống lớn theo từng bước.
- Dependency chưa thể được đặt trên module path trong cấu hình hiện tại.

### 8.2. Khi nào nên dùng module path?

Module path phù hợp khi:

- Muốn khai báo dependency rõ ràng bằng requires.
- Muốn công bố API bằng exports và giữ package nội bộ không export.
- Muốn phát hiện thiếu dependency khi phân giải module.
- Muốn đóng gói runtime hoặc ứng dụng theo đồ thị module.
- Cần tích hợp dịch vụ JPMS qua uses và provides.

### 8.3. Kết hợp classpath và module path trong giai đoạn chuyển đổi

Một ứng dụng có thể vẫn cần thư viện classpath trong khi một phần ứng dụng đã là named module. Tuy nhiên, named module không tự động đọc unnamed module. Nếu cần tích hợp tạm thời, có thể cấp quan hệ đọc lúc chạy:

~~~bash
java --add-reads com.example.app=ALL-UNNAMED --module-path mods -cp legacy-utils.jar -m com.example.app/com.example.app.Main
~~~

Tùy chọn này tạo quan hệ đọc bổ sung từ com.example.app tới unnamed module. Nó không export package của named module và không thay thế thiết kế dependency dài hạn.

Nếu có thể, hãy chuyển dependency lên module path để nó trở thành named module hoặc automatic module, sau đó khai báo requires theo tên module thực tế.

## 9. Các lỗi thường gặp

| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| ClassNotFoundException khi chạy classpath | Thiếu JAR hoặc đường dẫn classpath sai | Kiểm tra -cp, tên class và dấu phân cách theo hệ điều hành |
| Module not found khi chạy module path | Module không có trên module path hoặc tên module không khớp | Kiểm tra tên module bằng jar --describe-module và cấu hình --module-path |
| Package is not visible khi biên dịch module | Module nguồn không export package hoặc module đích không đọc module nguồn | Kiểm tra exports và requires |
| Ứng dụng chạy trên classpath nhưng lỗi khi chuyển sang module path | Ứng dụng đang dựa vào package không export hoặc dependency chưa khai báo | Xác định package API, bổ sung requires/exports cần thiết hoặc thay đổi cách sử dụng API |
| Cùng JAR có tên module khác dự kiến | Automatic module lấy tên từ manifest hoặc tên file | Đặt Automatic-Module-Name ổn định và kiểm tra bằng jar --describe-module |
| Classpath chạy được nhưng module path không tìm thấy dependency | Dependency chỉ được thêm vào classpath hoặc không có trên module path | Đưa dependency vào module path và khai báo requires phù hợp |
| Module descriptor có trong JAR nhưng ứng dụng vẫn chạy như classpath | JAR đang được đặt trên classpath | Kiểm tra lệnh chạy; dùng --module-path và -m để chạy named module |

## 10. Quy trình kiểm tra khi chuyển ứng dụng sang JPMS

1. Xác định chính xác JAR và phiên bản đang được chạy.
2. Dùng jar --describe-module để kiểm tra module descriptor hoặc tên automatic module.
3. Chạy bộ JAR hiện tại trên classpath và ghi nhận kết quả.
4. Đưa các modular JAR lên module path, khai báo requires và chạy lại ứng dụng.
5. Kiểm tra package public nào cần exports; giữ package triển khai không export nếu không cần công bố.
6. Với thư viện chưa modular, kiểm tra Automatic-Module-Name hoặc tên automatic module được suy ra.
7. Kiểm tra dependency runtime thực tế; một JAR có descriptor đúng vẫn có thể thiếu dependency khác trong module path.
8. Chạy kiểm thử tích hợp để phát hiện truy cập reflection, service hoặc resource phụ thuộc vào cách nạp lớp.
9. Chỉ gỡ bỏ classpath hoặc các tùy chọn tương thích tạm thời sau khi các dependency đã được chuyển đổi và kiểm thử đầy đủ.

## 11. Checklist

- [ ] Đã xác định JAR nào nằm trên classpath và JAR nào nằm trên module path.
- [ ] Đã kiểm tra module descriptor bằng jar --describe-module.
- [ ] Đã hiểu rằng module-info.class không tạo named module khi JAR nằm trên classpath.
- [ ] Đã phân biệt unnamed module với automatic module.
- [ ] Đã kiểm tra Automatic-Module-Name cho thư viện chưa modular.
- [ ] Đã kiểm tra requires và exports khi chạy trên module path.
- [ ] Đã kiểm tra package nội bộ có bị truy cập ngoài dự kiến không.
- [ ] Đã chạy cùng artifact trên cả hai đường dẫn khi cần tương thích.
- [ ] Đã kiểm tra dependency và resource ở cấu hình runtime thực tế.

## 12. Tài liệu tham khảo

- [Java SE 26 — java command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): tùy chọn classpath, module path và chạy module.
- [Java SE 26 — javac command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/javac.html): biên dịch module và cấu hình module path.
- [Java SE 26 — jar command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jar.html): tạo, liệt kê và mô tả module trong JAR.
- [Java Language Specification, Java SE 26 — Modules](https://docs.oracle.com/en/java/javase/26/docs/specs/jls/jls-7.html): quy tắc module declaration, named module, automatic module và unnamed module.
- [Dev.java — Organizing Code into Modules](https://dev.java/learn/organizing/modules/): hướng dẫn thực hành JPMS.
