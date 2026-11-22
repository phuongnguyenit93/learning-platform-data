# Đóng gói modular JAR và chọn lớp main

## 1. Mục tiêu

Một modular JAR là tệp JAR chứa module descriptor module-info.class. Descriptor xác định tên module, các module phụ thuộc và những package được công khai. Khi đóng gói ứng dụng thành modular JAR, ngoài việc tạo file JAR, cần xác định lớp khởi chạy để Java launcher biết phải gọi phương thức main nào.

Quy trình hiện đại thường gồm:

1. Tổ chức source theo package và khai báo module trong module-info.java.
2. Biên dịch module để tạo module-info.class cùng các class của ứng dụng.
3. Đóng gói các class thành JAR và gắn main class.
4. Kiểm tra module descriptor và main class đã được ghi đúng.
5. Chạy executable JAR theo classpath bằng java -jar hoặc chạy named module theo JPMS bằng --module-path và --module.

Java 9 là phiên bản đầu tiên có JPMS, nhưng không nên triển khai ứng dụng mới bằng JDK 9 đã hết vòng đời hỗ trợ. Các bước dưới đây sử dụng cú pháp và công cụ JDK vẫn được duy trì trong các JDK hiện đại; ví dụ được biên dịch theo Java 17 để có mức tương thích rõ ràng.

## 2. Modular JAR khác gì JAR thông thường?

| Loại JAR | Đặc điểm | Cách chạy thường gặp |
|---|---|---|
| JAR thông thường | Không có module descriptor tường minh; các class thường chạy trên classpath | java -cp app.jar com.acme.Main |
| Executable JAR thông thường | JAR có manifest Main-Class | java -jar app.jar |
| Modular JAR | Có module-info.class, xác định module và ranh giới package | java --module-path app.jar --module com.acme.app |
| Modular JAR có main class | Có module descriptor và ModuleMainClass | java --module-path app.jar --module com.acme.app |

Một JAR có module-info.class vẫn là một JAR. Điểm khác biệt là khi đặt trên module path, JVM nhận diện nó như một named module và áp dụng quy tắc đọc module, phụ thuộc và truy cập package của JPMS.

Nếu đưa modular JAR lên classpath, module descriptor không được dùng để thiết lập ranh giới module. Các class được nạp như classpath thông thường. Vì vậy, nếu mục tiêu là chạy theo JPMS, hãy dùng module path.

## 3. Cấu trúc source của một module

Ví dụ ứng dụng com.acme.hello có một package API công khai và một package chứa lớp khởi chạy nội bộ:

~~~text
hello-app/
├── src/
│   ├── module-info.java
│   └── com/
│       └── acme/
│           └── hello/
│               ├── api/
│               │   └── Greeting.java
│               └── internal/
│                   └── Main.java
├── out/
└── build/
~~~

File src/module-info.java:

~~~java
module com.acme.hello {
    exports com.acme.hello.api;
}
~~~

Tên module là com.acme.hello. Chỉ package com.acme.hello.api được export cho module khác sử dụng. Package com.acme.hello.internal vẫn nằm trong module nhưng không trở thành API công khai.

File src/com/acme/hello/api/Greeting.java:

~~~java
package com.acme.hello.api;

public final class Greeting {
    private Greeting() {
    }

    public static String message() {
        return "Hello from modular JAR";
    }
}
~~~

File src/com/acme/hello/internal/Main.java:

~~~java
package com.acme.hello.internal;

import com.acme.hello.api.Greeting;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("module=" + Main.class.getModule().getName());
        System.out.println("greeting=" + Greeting.message());
    }
}
~~~

Lớp Main nằm trong package không export. Module launcher vẫn có thể gọi main class đã được khai báo cho module; package chứa main class không cần export chỉ để khởi chạy ứng dụng. Việc export nên dành cho API mà module khác cần truy cập.

## 4. Hiểu các chỉ thị trong module-info.java

Module descriptor là nơi mô tả ranh giới và phụ thuộc của module.

| Chỉ thị | Công dụng |
|---|---|
| requires module.name; | Khai báo module cần thiết để biên dịch và chạy |
| requires transitive module.name; | Module phụ thuộc được truyền tiếp cho module đọc module hiện tại |
| requires static module.name; | Phụ thuộc cần khi biên dịch nhưng không bắt buộc ở runtime |
| exports package.name; | Công khai package cho các module đọc module hiện tại |
| exports package.name to other.module; | Chỉ công khai package cho các module được nêu |
| opens package.name; | Cho phép reflection sâu vào package |
| opens package.name to framework.module; | Chỉ mở package cho module framework cụ thể |
| uses service.Type; | Khai báo module sử dụng một service |
| provides service.Type with impl.Type; | Đăng ký implementation của service |

Không cần thêm requires java.base; module này được hệ thống yêu cầu ngầm định cho mọi module thông thường.

exports và opens giải quyết hai nhu cầu khác nhau. exports cho phép module khác truy cập các public type của package theo quy tắc ngôn ngữ Java. opens cho phép reflection truy cập sâu hơn, kể cả các thành viên không public trong phạm vi được mở. Không dùng opens thay cho exports, và chỉ mở package khi framework thực sự cần reflection.

Nếu module dùng một thư viện bên ngoài, hãy khai báo requires cho module tương ứng và cung cấp dependency đó trên module path khi biên dịch lẫn chạy. Tên module cần khớp với tên được khai báo trong module descriptor của thư viện.

## 5. Biên dịch module

Từ thư mục gốc hello-app, tạo thư mục output và build:

~~~bash
mkdir -p out build

javac --release 17 -d out \
  src/module-info.java \
  src/com/acme/hello/api/Greeting.java \
  src/com/acme/hello/internal/Main.java
~~~

--release 17 giới hạn cú pháp, API nền tảng và định dạng bytecode theo Java 17. Có thể dùng JDK mới hơn để biên dịch nhưng vẫn tạo artifact tương thích với release đã chọn.

Sau khi biên dịch, thư mục out chứa cấu trúc module đã được biên dịch:

~~~text
out/
├── module-info.class
└── com/
    └── acme/
        └── hello/
            ├── api/
            │   └── Greeting.class
            └── internal/
                └── Main.class
~~~

module-info.class phải nằm ở thư mục gốc của nội dung module khi tạo modular JAR. Không đặt descriptor trong một thư mục package.

Nếu dùng nhiều module, nên tổ chức output theo từng module và sử dụng --module-source-path, --module-path hoặc build tool để quản lý dependency. Không gom class của nhiều named module vào cùng một JAR thông thường; mỗi named module cần module descriptor và artifact riêng theo cấu trúc module tương ứng.

## 6. Đóng gói modular JAR và khai báo main class

Dùng công cụ jar đi kèm JDK:

~~~bash
jar --create \
  --file build/hello.jar \
  --main-class com.acme.hello.internal.Main \
  -C out .
~~~

Các thành phần quan trọng:

- --create tạo một JAR mới.
- --file build/hello.jar chỉ định đường dẫn và tên file đầu ra.
- --main-class chỉ định lớp có phương thức public static void main(String[] args) dùng làm điểm khởi chạy mặc định.
- -C out . chuyển thư mục làm việc vào out rồi thêm toàn bộ nội dung của thư mục đó vào JAR.

Với modular JAR, --main-class ghi thông tin main class của module vào module descriptor (ModuleMainClass). Công cụ cũng tạo thông tin manifest phù hợp để JAR có thể được khởi chạy theo chế độ executable JAR. Nhờ vậy, launcher có thể xác định main class mặc định khi chạy module.

Không nhầm --main-class với tên module. Tên module lấy từ module-info.java; main class là tên đầy đủ của lớp Java, gồm package và class name. Ví dụ trên:

- Module: com.acme.hello
- Main class: com.acme.hello.internal.Main
- JAR: build/hello.jar

Lớp main không cần trùng tên module hoặc tên file JAR.

## 7. Kiểm tra nội dung JAR trước khi chạy

Dùng jar --describe-module để xem module descriptor và main class:

~~~bash
jar --describe-module --file build/hello.jar
~~~

Kết quả cần thể hiện các thông tin chính tương tự:

~~~text
com.acme.hello
exports com.acme.hello.api
requires java.base mandated
main-class com.acme.hello.internal.Main
~~~

Dòng main-class xác nhận main class đã được ghi cho module. Dòng exports xác nhận package API đã được công khai. Dòng requires java.base mandated là phụ thuộc nền tảng được hệ thống thêm ngầm định.

Có thể xem danh sách entry trong JAR:

~~~bash
jar --list --file build/hello.jar
~~~

Cần thấy module-info.class và các class nằm đúng package. Nếu thiếu module-info.class, JAR không phải explicit modular JAR. Nếu thiếu class main hoặc ghi sai package, launcher sẽ không thể khởi chạy ứng dụng.

## 8. Chọn cách khởi chạy phù hợp

### 8.1. Chạy JAR bằng -jar theo classpath (unnamed module)

~~~bash
java -jar build/hello.jar
~~~

Launcher đọc `Main-Class` trong manifest và chạy lớp trên class path. **Ngay cả khi JAR có `module-info.class`, chế độ `-jar` vẫn khởi chạy ứng dụng trong unnamed module; module descriptor không tham gia tạo module graph.** Vì vậy, `Main.class.getModule().getName()` trả về `null`. Cách này phù hợp khi cần chạy một executable JAR theo classpath và không cần JPMS resolution.

Kết quả:

~~~text
module=null
greeting=Hello from modular JAR
~~~

### 8.2. Chạy module bằng --module-path và --module

~~~bash
java --module-path build/hello.jar --module com.acme.hello
~~~

--module-path chỉ định nơi chứa các module. --module (viết tắt -m) chọn module cần chạy. Vì JAR đã lưu main class mặc định, không cần ghi tên lớp sau tên module.

Cách này phù hợp khi ứng dụng gồm nhiều modular JAR và cần kiểm soát module path:

~~~bash
java --module-path "build/hello.jar:lib" --module com.acme.hello
~~~

Dấu phân cách path ở ví dụ trên là : trên Linux/macOS. Trên Windows dùng ;:

~~~powershell
java --module-path "build\hello.jar;lib" --module com.acme.hello
~~~

Các dependency module phải có mặt trên module path và phải thỏa mãn các khai báo requires. Nếu thiếu module hoặc có xung đột module, launcher sẽ báo lỗi khi resolve module graph.

### 8.3. Chỉ định main class tường minh

Có thể ghi rõ lớp cần chạy ngay trên command line:

~~~bash
java --module-path build/hello.jar \
  --module com.acme.hello/com.acme.hello.internal.Main
~~~

Cách này hữu ích khi module có nhiều entry point hoặc cần chạy một lớp main khác với main class mặc định được ghi trong JAR. Tên sau dấu / là fully qualified class name.

Khi truyền đối số cho chương trình, đặt chúng sau module/class:

~~~bash
java --module-path build/hello.jar \
  --module com.acme.hello/com.acme.hello.internal.Main --mode report
~~~

Các đối số sau module/class được chuyển cho main(String[] args).

### 8.4. So sánh -jar và -m

| Tiêu chí | `java -jar` | `java --module-path ... --module ...` |
|---|---|---|
| Cách nạp | Class path; JAR được nạp vào unnamed module | Module path; JAR được resolve như named module |
| Module descriptor | Không tham gia module graph trong chế độ `-jar` | `module-info.class` được dùng để resolve `requires` và exports |
| Main class | `Main-Class` trong manifest | `ModuleMainClass` của module hoặc class chỉ định sau `/` |
| Dependency | Theo classpath/manifest `Class-Path`; không dùng quan hệ `requires` | Các module phải có trên module path và thỏa mãn module graph |
| Cách dùng | Executable JAR khi không cần JPMS resolution | Chạy ứng dụng theo JPMS |

Nếu chỉ cần chạy một executable JAR theo classpath, dùng `java -jar`. Nếu muốn chạy ứng dụng như named module để module descriptor, `requires`, exports và module graph có hiệu lực, dùng `java --module-path ... --module ...` hoặc `-m`.

## 9. Manifest và module main class

JAR có manifest tại META-INF/MANIFEST.MF. Với executable JAR thông thường, thuộc tính Main-Class cho biết lớp khởi chạy:

~~~text
Manifest-Version: 1.0
Main-Class: com.acme.app.Main
~~~

Modular JAR còn có module descriptor. Khi dùng jar --main-class, công cụ ghi main class cho module. Đây là thông tin được jar --describe-module hiển thị dưới dòng main-class.

Không nên chỉ nhìn manifest rồi kết luận JAR là modular. Hãy kiểm tra sự hiện diện của module-info.class và dùng jar --describe-module. Một JAR thông thường có thể có Main-Class nhưng vẫn không có module descriptor.

Nếu build bằng Maven hoặc Gradle, cấu hình plugin đóng gói để tạo manifest main class và đảm bảo module descriptor được giữ trong JAR. Sau khi build, luôn kiểm tra artifact đầu ra bằng jar --describe-module, jar --list và chạy thử đúng cách triển khai dự kiến. Không giả định mọi plugin đều tự thiết lập ModuleMainClass chỉ vì manifest có Main-Class.

## 10. Dependency và đóng gói ứng dụng nhiều module

Một modular JAR không tự chứa tất cả dependency của ứng dụng. JAR ví dụ ở trên chỉ chứa module com.acme.hello. Nếu module khai báo requires com.acme.logging, module phụ thuộc phải được phân phối và có trên module path khi chạy.

Một layout triển khai đơn giản:

~~~text
distribution/
├── app/
│   └── hello.jar
└── lib/
    ├── logging.jar
    └── config.jar
~~~

Chạy ứng dụng:

~~~bash
java --module-path "app/hello.jar:lib" --module com.acme.hello
~~~

Trên Windows, thay dấu : bằng ;. Nếu dependency không phải explicit named module, cần kiểm tra cách nó được nhận diện trên module path và các giới hạn của automatic module. Đối với ứng dụng mới, ưu tiên dependency có module descriptor rõ ràng hoặc được nhà cung cấp hỗ trợ JPMS.

Tránh split package: cùng một package không nên được chia giữa nhiều named module. Module graph cần có tên module duy nhất và các phụ thuộc phải resolve được. Hãy kiểm tra dependency tree khi nâng cấp thư viện hoặc chuyển ứng dụng từ classpath sang module path.

## 11. Tạo runtime image bằng jlink khi phù hợp

Khi ứng dụng và các dependency cần thiết đều là named module, jlink có thể tạo runtime image chỉ chứa các module cần thiết:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:build/hello.jar" \
  --add-modules com.acme.hello \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --output build/runtime
~~~

Chạy ứng dụng bằng runtime image:

~~~bash
build/runtime/bin/java --module com.acme.hello
~~~

Trên Windows, executable nằm tại build\runtime\bin\java.exe.

jlink tạo runtime image từ module JDK và application modules đã resolve được. Nó không phải công cụ tạo fat JAR và không tự gom mọi thư viện không modular vào một artifact. Nếu ứng dụng có dependency ngoài JDK chưa phải named module, cần xử lý kiến trúc đóng gói trước khi dùng jlink.

Không cần dùng jlink cho mọi ứng dụng. Nếu môi trường triển khai đã có JDK phù hợp và việc cài runtime chung được quản lý tốt, phân phối modular JAR cùng dependency trên module path thường đơn giản hơn.

## 12. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| no main manifest attribute | JAR thông thường không có manifest Main-Class | Đóng gói executable JAR và đặt main class |
| Module ... not found | Module path thiếu JAR hoặc thư mục chứa module | Kiểm tra --module-path, tên module và dependency |
| Module ... does not have a main class | Module không có ModuleMainClass và command line không chỉ định class | Dùng jar --main-class hoặc -m module/class |
| Could not find or load main class | Sai tên đầy đủ của lớp hoặc class không nằm trong JAR | Kiểm tra package, class name và jar --list |
| Invalid or corrupt jarfile | JAR bị lỗi hoặc nội dung đóng gói sai | Tạo lại JAR và kiểm tra entry |
| Package ... is not visible | Package chưa được export cho module gọi | Khai báo exports phù hợp trong module descriptor |
| module not found khi biên dịch | Thiếu dependency module trên module path | Bổ sung dependency và kiểm tra tên module |
| FindException hoặc lỗi resolve module | Module trùng tên, thiếu dependency hoặc split package | Kiểm tra toàn bộ module path và module graph |

Không khắc phục lỗi bằng cách mở toàn bộ package hoặc chuyển tất cả dependency sang classpath mà không hiểu nguyên nhân. Hãy xác định lỗi nằm ở module descriptor, artifact, module path hay main class.

## 13. Checklist trước khi phát hành

- [ ] module-info.java khai báo đúng tên module và các dependency.
- [ ] Chỉ export package API cần công khai.
- [ ] Các package nội bộ không bị export nếu không cần.
- [ ] module-info.class nằm ở root của modular JAR.
- [ ] Main class có public static void main(String[] args) và nằm trong artifact.
- [ ] JAR được tạo bằng jar --main-class hoặc build tool có cấu hình tương đương.
- [ ] jar --describe-module hiển thị đúng module, exports, requires và main class.
- [ ] jar --list xác nhận các class nằm đúng package.
- [ ] Kiểm thử riêng chế độ classpath bằng `java -jar` và chế độ JPMS bằng `--module-path`/`-m` nếu sản phẩm hỗ trợ cả hai.
- [ ] Mọi dependency có mặt và resolve được trên module path.
- [ ] CI kiểm tra artifact đã đóng gói, không chỉ kiểm tra class trong thư mục build.
- [ ] Nếu dùng jlink, runtime image được chạy thử trên môi trường triển khai thực tế.

## Tài liệu tham khảo

- [The Java Platform Module System — JEP 261](https://openjdk.org/jeps/261)
- [The jar Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jar.html)
- [The java Launcher](https://docs.oracle.com/en/java/javase/25/docs/specs/man/java.html)
- [The javac Compiler](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html)
- [The jlink Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jlink.html)
- [Module System — Java Platform Documentation](https://docs.oracle.com/en/java/javase/25/docs/)
