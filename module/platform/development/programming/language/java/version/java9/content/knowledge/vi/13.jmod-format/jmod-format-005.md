# Giới hạn sử dụng JMOD trực tiếp lúc chạy

## 1. Mục tiêu

JMOD là định dạng archive dành cho module của JDK. Nó được dùng trong quy trình đóng gói và liên kết runtime, đặc biệt khi tạo custom runtime image bằng jlink. JMOD có thể chứa class, module descriptor và các thành phần phụ trợ như native library, header, command, configuration, man page hoặc legal notice.

Điểm cần nhớ khi triển khai ứng dụng: **JMOD không phải định dạng module mà Java launcher nạp trực tiếp lúc chạy**. Đưa file .jmod vào tùy chọn --module-path của lệnh java sẽ bị từ chối. JMOD được dùng làm đầu vào cho công cụ liên kết như jlink; runtime image được tạo ra mới là thứ người dùng chạy.

Với ứng dụng cần chạy trực tiếp trên một JDK/JRE đã cài, hãy phân phối modular JAR hoặc exploded module trên runtime module path. Nếu muốn đóng gói runtime riêng, dùng jlink để tạo runtime image từ các module, có thể lấy module đầu vào từ JMOD.

## 2. JMOD là gì?

JMOD là định dạng đóng gói module được giới thiệu cùng Java Platform Module System. Công cụ jmod trong JDK có thể tạo, liệt kê, mô tả và giải nén archive:

~~~bash
jmod create ...
jmod list ...
jmod describe ...
jmod extract ...
~~~

Một JMOD có thể chứa nhiều nhóm nội dung:

| Thành phần | Ví dụ nội dung |
|---|---|
| classes | class file, resource và module-info.class |
| libs | native library |
| cmds | native command |
| config | file cấu hình |
| header-files | header dùng khi tích hợp native |
| man-pages | tài liệu lệnh |
| legal-notices | thông tin giấy phép |

JMOD được thiết kế để phục vụ quá trình xây dựng JDK và liên kết runtime. Ví dụ, các JDK thường có thư mục $JAVA_HOME/jmods chứa các JMOD của module nền tảng. jlink dùng những archive này để chọn và kết hợp các module cần thiết.

JMOD không phải JAR có thêm phần mở rộng khác. Dù cả hai đều là archive chứa class, định dạng và mục đích sử dụng của chúng khác nhau.

## 3. Vì sao không thể dùng JMOD trực tiếp với Java launcher?

Java launcher hỗ trợ module path chứa modular JAR, exploded module và các module phù hợp với định dạng runtime. JMOD không thuộc nhóm định dạng được nạp trực tiếp khi khởi chạy ứng dụng.

Ví dụ lệnh sau không hợp lệ:

~~~bash
java --module-path dist/hello.jmod --module com.acme.hello
~~~

Trên OpenJDK 24.0.2, lỗi thực tế có dạng:

~~~text
Error occurred during initialization of boot layer
java.lang.module.FindException: JMOD format not supported at execution time: dist\hello.jmod
~~~

Thông báo chỉ rõ giới hạn: JMOD format không được hỗ trợ tại thời điểm thực thi. Đây là giới hạn của Java launcher, không có nghĩa archive bị hỏng hoặc module descriptor sai.

Không dùng JMOD trực tiếp trong các cách sau:

- Không đặt file .jmod trên runtime --module-path rồi gọi java -m.
- Không dùng file .jmod làm classpath như một JAR thông thường.
- Không dùng java -jar để chạy JMOD.
- Không đổi phần mở rộng .jmod thành .jar; đổi tên không chuyển đổi định dạng archive.

Nếu muốn kiểm tra JMOD, dùng jmod list, jmod describe hoặc jmod extract. Nếu muốn chạy module, dùng modular JAR/exploded module hoặc tạo runtime image bằng jlink.

## 4. Phân biệt module path của java và jlink

Cả java và jlink đều có tùy chọn --module-path, nhưng tập định dạng đầu vào được hỗ trợ khác nhau.

| Công cụ | JMOD trên module path | Mục đích |
|---|---|---|
| java | Không hỗ trợ | Nạp module để thực thi ứng dụng |
| jlink | Hỗ trợ | Liên kết module thành custom runtime image |
| jmod | Nhận JMOD làm archive đầu vào cho list/describe/extract/hash | Quản lý nội dung JMOD |

Vì vậy, đừng suy luận rằng một file được chấp nhận bởi jlink --module-path cũng sẽ được chấp nhận bởi java --module-path.

Thư mục $JAVA_HOME/jmods là ví dụ điển hình. Nó chứa các JMOD mà jlink có thể dùng để tạo runtime image. Java launcher chạy ứng dụng trên runtime đã được cài đặt; nó không đọc trực tiếp thư mục JMOD này để dựng boot layer.

## 5. Tạo một modular JAR để chạy trực tiếp

Nếu ứng dụng cần chạy như một named module trên JDK có sẵn, modular JAR là lựa chọn thông dụng.

Cấu trúc ví dụ:

~~~text
hello-app/
├── src/
│   └── com.acme.hello/
│       ├── module-info.java
│       └── com/acme/hello/Main.java
├── mods/
└── dist/
~~~

File src/com.acme.hello/module-info.java:

~~~java
module com.acme.hello {
    exports com.acme.hello;
}
~~~

File src/com.acme.hello/com/acme/hello/Main.java:

~~~java
package com.acme.hello;

public final class Main {
    public static void main(String[] args) {
        System.out.println("module=" + Main.class.getModule().getName());
        System.out.println("hello=JMOD linked runtime");
    }
}
~~~

Biên dịch bằng JDK 17 trở lên:

~~~bash
mkdir -p mods dist

javac --release 17 \
  --module-source-path src \
  -d mods \
  -m com.acme.hello
~~~

Đóng gói module thành JAR:

~~~bash
jar --create \
  --file dist/hello.jar \
  --main-class com.acme.hello.Main \
  -C mods/com.acme.hello .
~~~

Chạy JAR trên module path:

~~~bash
java --module-path dist/hello.jar --module com.acme.hello
~~~

Output:

~~~text
module=com.acme.hello
hello=JMOD linked runtime
~~~

Khi cần giữ JPMS semantics, hãy chạy modular JAR qua --module-path và --module. Không nhầm cách này với java -jar: -jar khởi chạy JAR trên classpath/unnamed module, nên module-info.class không tạo ranh giới named module cho lần chạy đó.

## 6. Tạo JMOD từ module đã biên dịch

Khi cần đưa module vào quy trình jlink, tạo JMOD bằng công cụ jmod:

~~~bash
jmod create \
  --class-path mods/com.acme.hello \
  --main-class com.acme.hello.Main \
  dist/hello.jmod
~~~

Ý nghĩa:

- create yêu cầu tạo archive JMOD.
- --class-path chỉ định thư mục chứa class và module-info.class của module đã biên dịch.
- --main-class ghi main class của module để công cụ liên kết có thể tạo launcher phù hợp.
- dist/hello.jmod là file JMOD đầu ra.

JMOD là artifact phục vụ bước đóng gói/liên kết. Lệnh trên không tạo một file mà Java launcher có thể chạy trực tiếp.

Nếu module có native library, command, configuration hoặc header cần thiết, có thể cung cấp các thư mục tương ứng bằng tùy chọn của jmod create như --libs, --cmds, --config và --header-files. Chỉ thêm thành phần mà module thực sự cần; kiểm tra target platform nếu archive chứa native component.

## 7. Kiểm tra JMOD

Liệt kê entry:

~~~bash
jmod list dist/hello.jmod
~~~

Output của ví dụ:

~~~text
classes/module-info.class
classes/com/acme/hello/Main.class
~~~

Xem descriptor:

~~~bash
jmod describe dist/hello.jmod
~~~

Output:

~~~text
com.acme.hello
exports com.acme.hello
requires java.base mandated
main-class com.acme.hello.Main
~~~

Các lệnh này giúp xác nhận module name, package được export, dependency và main class đã được ghi vào JMOD.

Có thể giải nén archive để kiểm tra nội dung:

~~~bash
mkdir extracted
jmod extract --dir extracted dist/hello.jmod
~~~

Sau khi extract, nội dung được phân loại theo các section của JMOD. Việc extract chỉ phục vụ kiểm tra hoặc xử lý artifact; nó không biến archive thành một module runtime hoàn chỉnh nếu chưa đặt nội dung vào cấu trúc module phù hợp.

## 8. Tạo custom runtime image bằng jlink

Đây là cách sử dụng JMOD đúng mục đích. jlink đọc module từ JDK jmods và JMOD của ứng dụng, resolve dependency rồi tạo runtime image chỉ chứa các module cần thiết.

Ví dụ trên Linux/macOS:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:dist/hello.jmod" \
  --add-modules com.acme.hello \
  --output runtime \
  --launcher hello=com.acme.hello
~~~

Trên Windows PowerShell, dấu phân cách module path là dấu chấm phẩy:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;dist\hello.jmod" --add-modules com.acme.hello --output runtime --launcher hello=com.acme.hello
~~~

--add-modules chọn module gốc cần liên kết. jlink tự resolve các dependency module cần thiết. --output chỉ định thư mục runtime image. --launcher tạo lệnh khởi chạy có tên hello trỏ tới module.

Sau khi link, có thể chạy bằng runtime riêng:

~~~bash
runtime/bin/java --module com.acme.hello
runtime/bin/hello
~~~

Trên Windows:

~~~powershell
.\runtime\bin\java.exe --module com.acme.hello
.\runtime\bin\hello.exe
~~~

Output:

~~~text
module=com.acme.hello
hello=JMOD linked runtime
~~~

Runtime image chứa JVM và các module được liên kết. Người dùng chạy chương trình từ runtime image này; họ không cần đưa file .jmod vào runtime module path nữa.

## 9. Những gì jlink làm và không làm

jlink tạo runtime image từ các module đã resolve được. Nó không đơn thuần đổi đuôi JMOD thành JAR và cũng không tạo một fat JAR.

jlink có thể:

- Chọn các module JDK và application module cần thiết.
- Resolve dependency của module graph.
- Kết hợp module vào runtime image.
- Loại bỏ thành phần không cần thiết như debug information, header files hoặc man pages theo tùy chọn.
- Tạo launcher cho module và main class.

jlink không tự:

- Biến mọi thư viện classpath truyền thống thành named module.
- Tìm đầy đủ dependency được nạp bằng reflection hoặc tên class trong file cấu hình.
- Đóng gói dữ liệu ngoài module graph mà ứng dụng cần, trừ khi chúng được tổ chức và cung cấp phù hợp.
- Bảo đảm runtime image chạy trên mọi hệ điều hành hoặc kiến trúc.
- Thay thế việc kiểm thử artifact và runtime image trên môi trường triển khai.

Nếu ứng dụng có dependency ngoài JDK, cần bảo đảm chúng có module descriptor hoặc được chuyển đổi/đóng gói phù hợp để jlink resolve. Nếu còn thư viện không modular, cân nhắc giữ ứng dụng trên classpath hoặc modular hóa dependency trước khi chọn quy trình jlink.

## 10. Native library và target platform

Một điểm khác biệt quan trọng của JMOD là nó có thể chứa native library, native command và header files. Đây là lý do JMOD hữu ích trong quá trình xây dựng runtime image và phân phối module gắn với nền tảng.

Nếu JMOD chứa native component, artifact thường gắn với hệ điều hành và kiến trúc mục tiêu. Không dùng một JMOD có native library của Windows để giả định nó sẽ hoạt động trong runtime image Linux. Tùy chọn --target-platform của jmod create cho phép ghi nhận nền tảng mục tiêu khi cần.

Hãy kiểm tra:

- JDK/JMOD được dùng để build có phù hợp với target platform không.
- Native library có đúng kiến trúc và ABI không.
- jlink có resolve được module và native dependency không.
- Runtime image có chạy được trên môi trường đích không.

Với module chỉ chứa Java class và resource thuần Java, vấn đề platform có thể ít phức tạp hơn, nhưng vẫn nên dùng toolchain tương thích và kiểm thử trên runtime đích.

## 11. Chọn artifact phù hợp khi triển khai

| Nhu cầu | Artifact/cách làm |
|---|---|
| Chạy ứng dụng trên JDK đã cài | Modular JAR hoặc exploded module trên java --module-path |
| Chạy ứng dụng classpath truyền thống | JAR và classpath theo cấu hình ứng dụng |
| Tạo runtime riêng, giảm module không cần thiết | JMOD/module đầu vào + jlink |
| Đóng gói native library, header, command cho quy trình link | JMOD |
| Kiểm tra module descriptor trong JMOD | jmod describe |
| Xem hoặc giải nén nội dung JMOD | jmod list hoặc jmod extract |

Không phát hành file JMOD như thể đó là file thực thi độc lập cho người dùng cuối. Nếu muốn phân phối một runtime riêng, phát hành thư mục runtime image được jlink tạo ra cùng ứng dụng và resource cần thiết.

## 12. Lỗi thường gặp

| Triệu chứng | Nguyên nhân | Hướng xử lý |
|---|---|---|
| JMOD format not supported at execution time | Đưa JMOD vào java --module-path | Dùng modular JAR/exploded module hoặc đưa JMOD vào jlink |
| Module not found khi chạy | Module path thiếu modular JAR hoặc module directory | Kiểm tra tên module và runtime module path |
| jlink không tìm thấy dependency | Thiếu module trên jlink module path | Bổ sung JMOD/modular JAR/exploded module chứa dependency |
| JMOD thiếu module-info.class | Đầu vào đóng gói không phải module đã biên dịch đúng | Kiểm tra output của javac và jmod list |
| Launcher trong runtime image không chạy | Thiếu main class hoặc khai báo launcher sai | Kiểm tra jmod describe và tùy chọn --launcher |
| Runtime image lỗi native library | Native artifact sai OS/architecture hoặc thiếu dependency | Build lại cho target platform và kiểm thử trên máy đích |
| JAR chạy nhưng JMOD không chạy trực tiếp | Hai artifact có vai trò và định dạng khác nhau | Dùng JAR cho runtime module path, JMOD cho link time |

## 13. Checklist trước khi phát hành

- [ ] Xác định mục tiêu là chạy trên JDK có sẵn hay phân phối custom runtime.
- [ ] Dùng modular JAR/exploded module khi Java launcher cần nạp module trực tiếp.
- [ ] Chỉ dùng JMOD như đầu vào cho jmod/jlink và công cụ build tương ứng.
- [ ] Kiểm tra module descriptor và main class bằng jmod describe.
- [ ] Kiểm tra archive bằng jmod list hoặc jmod extract.
- [ ] Resolve đủ dependency trước khi chạy jlink.
- [ ] Nếu có native component, kiểm tra target platform và ABI.
- [ ] Chạy thử runtime image được tạo ra trên môi trường triển khai thực tế.
- [ ] Không đưa .jmod vào runtime --module-path hoặc classpath.
- [ ] Giữ đúng JDK/toolchain được hỗ trợ cho quy trình build và link.

## Tài liệu tham khảo

- [jmod Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jmod.html)
- [jlink Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jlink.html)
- [java Launcher — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/java.html)
- [jar Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html)
- [Java Platform Module System — JEP 261](https://openjdk.org/jeps/261)
