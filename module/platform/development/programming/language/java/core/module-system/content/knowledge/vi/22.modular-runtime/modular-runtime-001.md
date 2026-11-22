# java --module-path chạy module

> Phạm vi: Java Platform Module System (JPMS, từ Java 9). Bài này hướng dẫn chạy một named module bằng Java launcher với **--module-path** và **--module**.

## Mục tiêu

Sau bài này, bạn có thể:

- Viết đúng cú pháp **java --module-path ... --module ...**.
- Phân biệt module path với class path.
- Chạy một module từ thư mục module đã biên dịch hoặc từ modular JAR.
- Chỉ định main class và truyền đối số cho chương trình.
- Hiểu cách launcher resolve module chính cùng các dependency được khai báo bằng **requires**.
- Kiểm tra module path và xử lý các lỗi thường gặp khi chạy ứng dụng modular.

## 1. Cú pháp cơ bản

Cú pháp tổng quát:

~~~bash
java [các-tùy-chọn-JVM] --module-path <module-path> --module <module-name>[/<main-class>] [application-args...]
~~~

Có thể viết bằng các dạng rút gọn:

~~~bash
java -p <module-path> -m <module-name>[/<main-class>] [application-args...]
~~~

Trong đó:

- **java**: Java application launcher.
- **--module-path** hoặc **-p**: chỉ định nơi launcher tìm các module ứng dụng và thư viện.
- **--module** hoặc **-m**: chỉ định module chính cần khởi chạy.
- **module-name**: tên module được khai báo trong **module-info.java** hoặc tên automatic module của JAR.
- **main-class**: tên đầy đủ của lớp có phương thức **public static void main(String[] args)**.
- **application-args**: các đối số được truyền cho phương thức **main**.

Ví dụ ngắn:

~~~bash
java --module-path mods \
     --module com.acme.app/com.acme.app.Main
~~~

Lệnh trên yêu cầu launcher tìm module **com.acme.app** trên module path **mods**, sau đó gọi lớp **com.acme.app.Main** trong module đó.

Có thể viết tương đương:

~~~bash
java -p mods -m com.acme.app/com.acme.app.Main
~~~

Tên module và tên lớp chính là hai thành phần khác nhau. Phần trước dấu gạch chéo là module name; phần sau là fully qualified class name.

## 2. Module path chứa những gì?

**Module path** là nơi Java tìm các module có thể quan sát được trong quá trình resolve. Nó có thể chứa:

- Thư mục chứa các exploded module (module đã biên dịch thành cây thư mục).
- Modular JAR có **module-info.class**.
- JAR chưa có module descriptor nhưng được nhận diện như automatic module.
- Các thư mục chứa modular JAR để launcher tìm module trong đó.

Ví dụ với exploded modules:

~~~text
project/
├── src/
│   ├── com.acme.lib/
│   │   ├── module-info.java
│   │   └── com/acme/lib/Message.java
│   └── com.acme.app/
│       ├── module-info.java
│       └── com/acme/app/Main.java
└── mods/
    ├── com.acme.lib/
    │   ├── module-info.class
    │   └── com/acme/lib/Message.class
    └── com.acme.app/
        ├── module-info.class
        └── com/acme/app/Main.class
~~~

Trong cấu trúc này, **mods** là module path. Mỗi thư mục con là một exploded module có **module-info.class** ở thư mục gốc của module.

Ví dụ với modular JAR:

~~~text
project/
└── mlib/
    ├── com.acme.lib.jar
    └── com.acme.app.jar
~~~

Khi đó, **mlib** là thư mục chứa các JAR module và có thể được chỉ định bằng **--module-path mlib**.

Bạn cũng có thể liệt kê trực tiếp nhiều JAR:

~~~bash
java --module-path "mlib/com.acme.app.jar:mlib/com.acme.lib.jar" \
     --module com.acme.app/com.acme.app.Main
~~~

Dấu phân cách các phần tử trong module path phụ thuộc hệ điều hành:

| Hệ điều hành | Dấu phân cách |
|---|---|
| Windows | Dấu chấm phẩy **;** |
| Linux, macOS | Dấu hai chấm **:** |

Ví dụ trên Windows:

~~~powershell
java --module-path "mlib/com.acme.app.jar;mlib/com.acme.lib.jar" -m com.acme.app/com.acme.app.Main
~~~

Nếu module path chỉ có một thư mục, không cần dùng dấu phân cách.

## 3. Ví dụ chạy exploded modules

Giả sử ứng dụng có hai module: **com.acme.lib** cung cấp một API đơn giản và **com.acme.app** gọi API đó.

### Module thư viện

File **src/com.acme.lib/module-info.java**:

~~~java
module com.acme.lib {
    exports com.acme.lib;
}
~~~

File **src/com.acme.lib/com/acme/lib/Message.java**:

~~~java
package com.acme.lib;

public class Message {
    public static String greet(String name) {
        return "Hello, " + name + "!";
    }
}
~~~

Module descriptor export package **com.acme.lib** để module khác có thể sử dụng public API trong package đó.

### Module ứng dụng

File **src/com.acme.app/module-info.java**:

~~~java
module com.acme.app {
    requires com.acme.lib;
}
~~~

File **src/com.acme.app/com/acme/app/Main.java**:

~~~java
package com.acme.app;

import com.acme.lib.Message;

public class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println(Message.greet(name));
    }
}
~~~

Directive **requires com.acme.lib** khai báo dependency của app đối với module thư viện.

### Biên dịch

Đứng tại thư mục gốc **project**, chạy:

~~~bash
javac -d mods --module-source-path src \
      -m com.acme.lib,com.acme.app
~~~

Giải thích:

- **--module-source-path src**: chỉ ra cây thư mục chứa source của các module.
- **-d mods**: ghi các file đã biên dịch vào thư mục **mods**.
- **-m com.acme.lib,com.acme.app**: yêu cầu javac biên dịch hai module đã nêu.

Sau khi biên dịch, **mods** chứa các exploded modules tương ứng.

### Chạy module chính

~~~bash
java --module-path mods \
     --module com.acme.app/com.acme.app.Main
~~~

Kết quả:

~~~text
Hello, Java!
~~~

Truyền đối số cho chương trình:

~~~bash
java --module-path mods \
     --module com.acme.app/com.acme.app.Main Lan
~~~

Kết quả:

~~~text
Hello, Lan!
~~~

Các đối số nằm sau phần **module/main-class** được chuyển vào **args** của phương thức **main**. Chúng không phải là tên module hay tùy chọn của launcher.

## 4. Chạy module từ modular JAR

Trong dự án thực tế, các module thường được đóng gói thành JAR để phân phối.

Giả sử đã biên dịch như phần trước và thư mục **mods** có:

- **mods/com.acme.lib/module-info.class**
- **mods/com.acme.app/module-info.class**

Tạo thư mục chứa JAR:

~~~bash
mkdir mlib
~~~

Đóng gói module thư viện:

~~~bash
jar --create --file mlib/com.acme.lib.jar \
    -C mods/com.acme.lib .
~~~

Đóng gói module ứng dụng:

~~~bash
jar --create --file mlib/com.acme.app.jar \
    -C mods/com.acme.app .
~~~

Chạy ứng dụng với thư mục JAR làm module path:

~~~bash
java --module-path mlib \
     --module com.acme.app/com.acme.app.Main
~~~

Launcher tìm module chính trong **mlib**, đọc descriptor của app, thấy **requires com.acme.lib**, rồi resolve dependency từ module path.

Có thể chỉ định từng file JAR trực tiếp:

~~~bash
java --module-path "mlib/com.acme.app.jar:mlib/com.acme.lib.jar" \
     -m com.acme.app/com.acme.app.Main
~~~

Nếu module path chứa cả JAR ứng dụng và JAR thư viện, thứ tự file không thay đổi ý nghĩa của directive **requires**. Điều quan trọng là module cần thiết phải có thể được tìm thấy và tên module phải khớp.

## 5. Chạy module mà không ghi main class trong lệnh

Cú pháp thường thấy có dạng:

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Ở đây main class được chỉ định rõ sau dấu gạch chéo. Trong một số trường hợp, có thể chỉ định module name:

~~~bash
java --module-path mlib -m com.acme.app
~~~

Cách thứ hai yêu cầu module có main class được ghi trong module descriptor (thuộc tính **ModuleMainClass**). Có thể thiết lập thuộc tính này khi tạo modular JAR bằng tùy chọn **--main-class** của công cụ **jar**:

~~~bash
jar --create \
    --file mlib/com.acme.app.jar \
    --main-class com.acme.app.Main \
    -C mods/com.acme.app .
~~~

Sau đó chạy:

~~~bash
java --module-path mlib --module com.acme.app
~~~

Nếu module không có main class được ghi trong descriptor và lệnh không chỉ định **/main-class**, launcher không biết lớp nào cần chạy. Khi đó, hãy thêm main class vào lệnh hoặc đóng gói lại JAR với **--main-class**.

## 6. Launcher resolve module như thế nào?

Khi chạy:

~~~bash
java --module-path mods \
     --module com.acme.app/com.acme.app.Main
~~~

launcher thực hiện các bước chính:

1. Đọc module path để tìm module có tên **com.acme.app**.
2. Xác định module chính cần khởi chạy.
3. Đọc module descriptor của module chính.
4. Resolve các dependency mà module khai báo bằng **requires**, cùng các dependency bắc cầu cần thiết.
5. Kiểm tra module graph có thể được tạo hợp lệ hay không.
6. Nạp lớp main class từ module chính và gọi phương thức **main**.

Ví dụ descriptor:

~~~java
module com.acme.app {
    requires com.acme.lib;
}
~~~

Nếu **com.acme.lib** không nằm trên module path hoặc không thể resolve, ứng dụng sẽ không chạy thành công. Việc chỉ định module chính không tự động làm cho mọi JAR trong dự án trở thành dependency; các quan hệ module phải được khai báo và resolve phù hợp.

Một số điểm cần nhớ:

- **requires** xác định dependency module.
- **exports** xác định package public mà module khác có thể truy cập.
- Module path xác định nơi tìm module.
- **--module** xác định module gốc cần chạy.
- Tên file JAR không nhất thiết là module name. Với explicit module, tên nằm trong descriptor; với automatic module, tên có thể đến từ manifest hoặc được suy ra từ tên file.

Nếu cần thêm một module vào tập module gốc ngoài module chính, launcher có tùy chọn **--add-modules**. Chỉ dùng khi ứng dụng thực sự cần resolve module đó dù nó không được kéo vào từ chuỗi **requires** thông thường.

## 7. Phân biệt --module-path với --class-path

Hai tùy chọn phục vụ hai cơ chế nạp lớp khác nhau.

| Tùy chọn | Ý nghĩa | Cách tham chiếu |
|---|---|---|
| **--module-path** hoặc **-p** | Nơi tìm named module và automatic module | Module name, **requires**, **-m** |
| **--class-path** hoặc **-cp** | Nơi tìm lớp và JAR theo cơ chế class path | Class name; các lớp thuộc unnamed module |

Ví dụ chạy ứng dụng class path:

~~~bash
java -cp libs/*:classes com.acme.app.Main
~~~

Ví dụ chạy ứng dụng modular:

~~~bash
java --module-path mods -m com.acme.app/com.acme.app.Main
~~~

Không nên nhầm hai lệnh này. Khi dùng **-m**, launcher tìm một module đã resolve trong module graph. Khi dùng tên lớp sau class path, launcher chạy lớp theo cơ chế class path.

Tùy chọn **-jar** cũng là một chế độ khởi chạy riêng:

~~~bash
java -jar app.jar
~~~

Lệnh này chạy JAR theo cơ chế **-jar** dựa trên manifest **Main-Class**; nó không tương đương với việc đặt modular JAR lên module path và chạy bằng **-m**. Khi mục tiêu là chạy ứng dụng như named module, dùng **--module-path** và **--module**.

## 8. Một số tùy chọn hữu ích khi chạy module

| Tùy chọn | Công dụng |
|---|---|
| **--module-path**, **-p** | Chỉ định module path |
| **--module**, **-m** | Chỉ định module chính và có thể chỉ định main class |
| **--add-modules** | Thêm module vào tập module gốc cần resolve |
| **--show-module-resolution** | In thông tin quá trình resolve module |
| **--list-modules** | Liệt kê các module mà launcher có thể quan sát |
| **--describe-module** | Hiển thị thông tin descriptor của module |
| **--class-path**, **-cp** | Chỉ định class path cho các lớp/JAR theo cơ chế class path |
| **-Dname=value** | Thiết lập system property |
| **-Xmx<size>** | Đặt giới hạn heap tối đa cho JVM |

Ví dụ xem quá trình resolve:

~~~bash
java --show-module-resolution \
     --module-path mods \
     --module com.acme.app/com.acme.app.Main
~~~

Ví dụ liệt kê module:

~~~bash
java --module-path mods --list-modules
~~~

Ví dụ mô tả module:

~~~bash
java --module-path mods --describe-module com.acme.app
~~~

Có thể dùng **jar --describe-module --file <jar-file>** để kiểm tra descriptor của một JAR cụ thể.

## 9. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| **Module ... not found** | Module chính không có trên module path hoặc tên module sai | Kiểm tra đường dẫn và tên trong **module-info.class**; dùng **jar --describe-module** |
| **FindException: Module ... not found, required by ...** | Dependency trong **requires** không được tìm thấy | Đưa JAR/thư mục module cần thiết vào module path; kiểm tra tên module |
| **Error occurred during initialization of boot layer** | Module graph không thể resolve hoặc có xung đột | Chạy với **--show-module-resolution**; kiểm tra module trùng tên, split package và dependency |
| **Main method not found** hoặc không tìm thấy main class | Sai tên lớp, sai module hoặc module không khai báo main class khi lệnh bỏ phần **/main-class** | Chỉ định đầy đủ **module/main-class** hoặc đóng gói main class bằng **jar --main-class** |
| **ClassNotFoundException** | Lớp không nằm trong module/JAR được resolve hoặc đường dẫn không đúng | Kiểm tra cấu trúc JAR, package và module path |
| **NoClassDefFoundError** | Lớp cần lúc chạy không được nạp, thường do thiếu dependency hoặc môi trường chạy khác môi trường biên dịch | Kiểm tra dependency runtime và module graph |
| Chạy được trên class path nhưng lỗi trên module path | Descriptor thiếu dependency/export cần thiết hoặc ứng dụng phụ thuộc vào hành vi class path | Kiểm tra **requires**, **exports**, package và module graph |

Trình tự debug:

1. Kiểm tra lệnh có đúng **--module-path** và **--module** hay không.
2. Kiểm tra module path có trỏ tới đúng thư mục hoặc JAR không.
3. Dùng **jar --describe-module** để xác nhận module name của từng JAR.
4. Kiểm tra module chính có nằm trong module path hoặc là module hệ thống có thể quan sát hay không.
5. Kiểm tra mọi dependency trong **requires** có thể được resolve.
6. Chạy lại với **--show-module-resolution** để xem launcher chọn và resolve module nào.
7. Xác nhận main class đúng tên package và nằm trong module chính.

## 10. Ghi nhớ

- **--module-path** (**-p**) là nơi tìm module; **--module** (**-m**) chọn module chính để chạy.
- Cú pháp đầy đủ thường dùng là **-m module.name/package.MainClass**.
- Có thể chạy exploded module hoặc modular JAR.
- Module chính và các module phụ thuộc phải được resolve thành module graph hợp lệ.
- **requires** khai báo dependency; **exports** công bố package API.
- Đối số ứng dụng được đặt sau module/main class.
- Nếu bỏ main class khỏi lệnh, module cần có main class được ghi trong descriptor.
- Chạy bằng **-m** khác với chạy JAR bằng **-jar** hoặc chạy lớp bằng **-cp**.

## Tài liệu tham khảo

- [Java Launcher — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/java.html)
- [The javac Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)
- [The jar Command — Java SE 21 Tool Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html)
- [JEP 261 — Module System](https://openjdk.org/jeps/261)
