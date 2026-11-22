# JMOD và module image trong Java

**JMOD** là định dạng archive dành cho module trong hệ sinh thái JDK. Một JMOD có thể chứa bytecode và các thành phần bổ trợ như native library, header, command, cấu hình, man page và legal notice. Công cụ `jmod` tạo, liệt kê, mô tả và giải nén các archive này.

**Module image** là runtime image được tạo bằng `jlink`. Image chứa JVM cùng tập module cần thiết cho ứng dụng và có thể có launcher riêng. Trong quy trình phổ biến, JMOD là một trong các đầu vào của `jlink`: `jmod` chuẩn bị module archive, còn `jlink` liên kết module thành runtime image để triển khai.

Hai khái niệm này thuộc Java Platform Module System (JPMS), được giới thiệu trong Java 9. Chúng hỗ trợ đóng gói module và tạo runtime phù hợp cho ứng dụng modular.

## 1. JMOD giải quyết vấn đề gì?

Một modular JAR thường đóng gói class file và resource của ứng dụng. JMOD mở rộng mô hình đóng gói để chứa thêm những thành phần phục vụ nền tảng hoặc môi trường triển khai:

- Java class file và `module-info.class`.
- Native command hoặc executable đi kèm module.
- Native library.
- Header file dùng khi tích hợp JNI.
- File cấu hình.
- Man page và legal notice.
- Metadata phục vụ liên kết module.

JMOD phù hợp với việc đóng gói module ở mức nền tảng hoặc làm đầu vào cho công cụ tạo runtime image. Một JMOD không phải JAR thông thường và không được thiết kế để chạy trực tiếp bằng `java -jar`.

### JMOD, modular JAR và module image

| Thành phần | Nội dung chính | Cách sử dụng |
|---|---|---|
| Modular JAR | Class file, resource và module descriptor | Chạy ứng dụng modular hoặc làm đầu vào cho công cụ module |
| JMOD | Class file cùng section bổ trợ như native library, header, config và legal | Phân phối module cho JDK tooling và làm đầu vào cho `jlink` |
| Module image | Runtime image gồm JVM và các module được liên kết | Triển khai và chạy ứng dụng trên nền tảng tương ứng |

`jmod create` tạo archive; `jlink` mới tạo runtime image.

## 2. Cấu trúc và các section của JMOD

JMOD là định dạng archive có cấu trúc section. Khi liệt kê nội dung, `jmod list` thường hiển thị đường dẫn bắt đầu bằng tên section.

| Section | Nội dung |
|---|---|
| `classes` | `module-info.class`, class file và resource của module |
| `bin` | Native command hoặc executable đi kèm |
| `conf` | File cấu hình |
| `include` | Header file, thường dùng cho tích hợp native/JNI |
| `legal` | Legal notice và thông tin giấy phép |
| `lib` | Native library và thành phần thư viện |
| `man` | Trang hướng dẫn |
| `hashes` | Dữ liệu hash module khi được tạo/cấu hình |

Không phải JMOD nào cũng có tất cả section. Một JMOD ứng dụng đơn giản có thể chỉ chứa `classes`; module hệ thống của JDK có thể có thêm native library, command, configuration hoặc legal files.

JMOD có header và cách tổ chức riêng. Không nên coi nó là JAR chỉ đổi phần mở rộng hoặc dùng công cụ ZIP/JAR tùy ý để chỉnh sửa cấu trúc. Dùng `jmod` để thao tác với archive.

## 3. Vị trí JMOD trong JDK

Một JDK đầy đủ thường có thư mục `jmods` chứa module archive của nền tảng Java. Ví dụ đường dẫn thường gặp:

~~~text
Windows:
C:\Program Files\Java\jdk-17\jmods

Linux:
/usr/lib/jvm/jdk-17/jmods

macOS:
/Library/Java/JavaVirtualMachines/jdk-17.jdk/Contents/Home/jmods
~~~

Đường dẫn cụ thể phụ thuộc nhà cung cấp và cách cài đặt. Nếu `JAVA_HOME` trỏ đến thư mục gốc JDK, có thể tìm module archive trong:

~~~text
%JAVA_HOME%\jmods
$JAVA_HOME/jmods
~~~

JDK có thể chứa các tệp như `java.base.jmod`, `java.logging.jmod`, `java.sql.jmod` và nhiều module khác. Đây là module archive mà công cụ JDK dùng để tạo runtime image hoặc kiểm tra thành phần nền tảng.

Không nhầm thư mục `jmods` với thư mục `lib` của runtime image. JMOD của JDK là đầu vào đóng gói cho công cụ phát triển/liên kết; chúng không phải thư viện cần đưa vào classpath thông thường.

## 4. Các lệnh cơ bản của `jmod`

`jmod` là công cụ dòng lệnh trong thư mục `bin` của JDK. Xem trợ giúp bằng:

~~~text
jmod --help
~~~

| Lệnh | Công dụng |
|---|---|
| `jmod create` | Tạo JMOD từ module đã biên dịch và các section bổ trợ |
| `jmod list` | Liệt kê entry trong JMOD |
| `jmod describe` | Hiển thị module descriptor và thông tin module |
| `jmod extract` | Giải nén các section và entry của JMOD |
| `jmod hash` | Tính/lưu hash cho module theo cấu hình phù hợp |

Cú pháp và tùy chọn chi tiết phụ thuộc phiên bản JDK; kiểm tra `jmod --help` của đúng JDK đang dùng trước khi chạy script triển khai.

### 4.1. Liệt kê nội dung bằng `jmod list`

Cú pháp:

~~~text
jmod list path/to/module.jmod
~~~

Ví dụ với module của JDK, trong PowerShell:

~~~powershell
jmod list "$env:JAVA_HOME\jmods\java.base.jmod"
~~~

Trên macOS/Linux:

~~~sh
jmod list "$JAVA_HOME/jmods/java.base.jmod"
~~~

Lệnh hiển thị các entry bên trong archive, chẳng hạn class file trong `classes/`, native library trong `lib/` hoặc cấu hình trong `conf/`. Kết quả của module hệ thống khá dài; khi điều tra, hãy tìm section hoặc package cần thiết.

### 4.2. Mô tả module bằng `jmod describe`

Cú pháp:

~~~text
jmod describe path/to/module.jmod
~~~

Ví dụ:

~~~sh
jmod describe "$JAVA_HOME/jmods/java.logging.jmod"
~~~

Thông tin mô tả thường bao gồm tên module, module version nếu có, package được export, module dependency (`requires`), main class hoặc metadata liên quan. Kết quả phản ánh module descriptor và metadata của archive; nó không phải danh sách toàn bộ class file.

### 4.3. Giải nén bằng `jmod extract`

Cú pháp:

~~~text
jmod extract --dir extracted path/to/module.jmod
~~~

Ví dụ:

~~~sh
jmod extract --dir extracted "$JAVA_HOME/jmods/java.logging.jmod"
~~~

Thư mục `extracted` sẽ chứa các section được giải nén, ví dụ `classes`, `conf`, `legal` hoặc `lib` nếu archive có các section đó. Nên giải nén vào thư mục riêng; không giải nén trực tiếp vào thư mục cài JDK hoặc thư mục hệ thống đang được sử dụng.

## 5. Tạo JMOD từ một Java module

Ta sẽ tạo module nhỏ tên `com.example.greeter`, biên dịch thành exploded module, đóng gói thành JMOD rồi dùng `jlink` tạo runtime image.

Cấu trúc dự án:

~~~text
project/
  src/
    module-info.java
    com/
      example/
        greeter/
          Main.java
  out/
  mods/
  greeter-image/
~~~

### 5.1. Khai báo module

Tạo `src/module-info.java`:

~~~java
module com.example.greeter {
    exports com.example.greeter;
}
~~~

`exports` cho phép module khác truy cập các kiểu public trong package `com.example.greeter`.

Tạo `src/com/example/greeter/Main.java`:

~~~java
package com.example.greeter;

public class Main {
    public static void main(String[] args) {
        System.out.println("Hello from a custom module image!");
    }
}
~~~

Tên đầy đủ của lớp chính là `com.example.greeter.Main`.

### 5.2. Biên dịch thành exploded module

Từ thư mục gốc `project`, tạo thư mục output rồi biên dịch.

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out, mods | Out-Null
javac --release 17 -d out src/module-info.java src/com/example/greeter/Main.java
~~~

macOS/Linux:

~~~sh
mkdir -p out mods
javac --release 17 -d out src/module-info.java src/com/example/greeter/Main.java
~~~

Sau khi biên dịch, thư mục `out` có dạng:

~~~text
out/
  module-info.class
  com/
    example/
      greeter/
        Main.class
~~~

Thư mục `out` là exploded module: module descriptor nằm ở gốc và class file được sắp theo package. Có thể chạy thử module này trước khi tạo JMOD:

~~~text
java --module-path out -m com.example.greeter/com.example.greeter.Main
~~~

Stdout:

~~~text
Hello from a custom module image!
~~~

### 5.3. Tạo JMOD bằng `jmod create`

Tạo JMOD từ các class file đã biên dịch:

~~~text
jmod create --class-path out --module-version 1.0 --main-class com.example.greeter.Main mods/com.example.greeter.jmod
~~~

Ý nghĩa:

- `create`: tạo archive JMOD.
- `--class-path out`: lấy module descriptor, class file và resource từ thư mục `out`.
- `--module-version 1.0`: ghi phiên bản module.
- `--main-class`: khai báo lớp chính của module.
- `mods/com.example.greeter.jmod`: đường dẫn JMOD đầu ra.

`out` phải chứa `module-info.class` ở thư mục gốc. Nếu module descriptor bị thiếu hoặc không hợp lệ, việc tạo hoặc mô tả module sẽ thất bại.

### 5.4. Kiểm tra JMOD vừa tạo

Liệt kê nội dung:

~~~text
jmod list mods/com.example.greeter.jmod
~~~

Với ví dụ này, các entry quan trọng sẽ tương tự:

~~~text
classes/module-info.class
classes/com/example/greeter/Main.class
~~~

Mô tả module:

~~~text
jmod describe mods/com.example.greeter.jmod
~~~

Kết quả phản ánh tên module `com.example.greeter`, package export, dependency nền tảng `java.base` và main class đã khai báo. Cách trình bày chính xác phụ thuộc phiên bản JDK.

Giải nén để kiểm tra:

~~~text
jmod extract --dir extracted mods/com.example.greeter.jmod
~~~

Sau khi giải nén, class file được đặt dưới `extracted/classes/`.

## 6. Tạo module image bằng `jlink`

`jlink` liên kết một tập module và các dependency cần thiết thành runtime image. Image thường chứa Java runtime, module ứng dụng và module nền tảng được giải quyết, runtime libraries, cấu hình cần thiết và launcher nếu được khai báo.

Cú pháp cơ bản:

~~~text
jlink --module-path module-path --add-modules module-name --output image-directory
~~~

- `--module-path`: nơi tìm các module đầu vào. Thường gồm thư mục `jmods` của JDK và thư mục chứa JMOD ứng dụng.
- `--add-modules`: chỉ định module gốc cần đưa vào image. `jlink` giải quyết các dependency bắt buộc.
- `--output`: thư mục runtime image đầu ra.

### 6.1. Liên kết image cho ví dụ greeter

Trên macOS/Linux, dùng dấu hai chấm `:` để phân cách các phần tử module path:

~~~sh
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.greeter --launcher greeter=com.example.greeter/com.example.greeter.Main --output greeter-image
~~~

Trên Windows PowerShell, dùng dấu chấm phẩy `;`:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.greeter --launcher greeter=com.example.greeter/com.example.greeter.Main --output greeter-image
~~~

`--launcher` tạo lệnh `greeter` trỏ đến module và main class. Nếu không cần launcher riêng, có thể bỏ tùy chọn này và gọi Java launcher trong image bằng `-m`.

`jlink` cần tìm được module JDK mà ứng dụng phụ thuộc, tối thiểu thường có `java.base`, cùng JMOD của `com.example.greeter`. Nếu thiếu module bắt buộc, quá trình liên kết sẽ báo lỗi phân giải module.

### 6.2. Chạy ứng dụng từ module image

Trên Linux/macOS:

~~~sh
./greeter-image/bin/greeter
~~~

Trên Windows PowerShell:

~~~powershell
.\greeter-image\bin\greeter.exe
~~~

Stdout:

~~~text
Hello from a custom module image!
~~~

Đây là ứng dụng chạy bằng runtime image vừa tạo. Máy đích không cần dùng JDK đầy đủ để chạy image, nhưng image vẫn phụ thuộc hệ điều hành và kiến trúc tương thích.

### 6.3. Kiểm tra module có trong image

Dùng Java launcher bên trong image.

Linux/macOS:

~~~sh
./greeter-image/bin/java --list-modules
~~~

Windows:

~~~powershell
.\greeter-image\bin\java.exe --list-modules
~~~

Danh sách hiển thị các module runtime có trong image, bao gồm module ứng dụng và các module dependency được liên kết.

## 7. Các tùy chọn `jmod create` thường dùng

`jmod create` có thể nhận nhiều thư mục đầu vào cho các section khác nhau:

| Tùy chọn | Nội dung |
|---|---|
| `--class-path path` | Class file và resource của module |
| `--cmds path` | Native command |
| `--config path` | File cấu hình |
| `--header-files path` | Header file |
| `--libs path` | Native library |
| `--man-pages path` | Man page |
| `--legal-notices path` | Legal notice |
| `--module-version version` | Phiên bản module |
| `--main-class class` | Lớp chính của module |
| `--target-platform platform` | Nền tảng mục tiêu của module |
| `--hash-modules regex` | Tính hash cho các module phù hợp theo biểu thức |

Ví dụ đóng gói module có native library và header:

~~~text
jmod create --class-path out --libs native/lib --header-files native/include --module-version 1.0 mods/com.example.native.jmod
~~~

Các đường dẫn là ví dụ; thư mục phải chứa đúng loại file tương ứng và module descriptor hợp lệ. Khi có native library, module image sẽ phụ thuộc nền tảng và kiến trúc của thư viện native đó.

Không nên đưa thư mục tùy ý vào section chỉ vì muốn archive chứa file. Hãy đặt file vào đúng section theo ý nghĩa và kiểm tra lại bằng `jmod list`.

## 8. Các tùy chọn `jlink` hữu ích

| Tùy chọn | Công dụng |
|---|---|
| `--module-path` | Chỉ định nơi tìm module |
| `--add-modules` | Chọn module gốc cần liên kết |
| `--bind-services` | Liên kết module provider phù hợp với service được dùng |
| `--launcher` | Tạo launcher cho module/main class |
| `--output` | Chỉ định thư mục image |
| `--strip-debug` | Loại bỏ debug information khỏi module được liên kết |
| `--no-header-files` | Không đưa header files vào image |
| `--no-man-pages` | Không đưa man pages vào image |
| `--compress` | Cấu hình mức nén tài nguyên/module trong image |
| `--list-plugins` | Liệt kê các plugin có sẵn |

Các tùy chọn và mức nén hỗ trợ phụ thuộc JDK. Xem `jlink --help` và `jlink --list-plugins` trước khi chuẩn hóa cấu hình image trong CI.

Ví dụ image nhỏ hơn có thể loại bỏ debug information, header và man page nếu ứng dụng không cần chúng:

~~~text
jlink --strip-debug --no-header-files --no-man-pages --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.greeter --output greeter-image
~~~

Không nên loại bỏ thành phần nếu ứng dụng hoặc quy trình vận hành cần chúng. Mục tiêu là image đủ dùng, có thể chẩn đoán và phù hợp với yêu cầu triển khai.

## 9. JMOD và module image trong quá trình triển khai

Một luồng triển khai modular thường có các bước:

1. Viết mã nguồn và module descriptor.
2. Dùng `javac` tạo exploded module.
3. Đóng gói thành modular JAR hoặc JMOD tùy mục tiêu.
4. Kiểm tra descriptor và nội dung archive.
5. Dùng `jlink` liên kết module cùng dependency nền tảng.
6. Kiểm tra image và launcher.
7. Phân phối image phù hợp với nền tảng máy đích.

Một số phân biệt quan trọng:

- `jmod` tạo và thao tác với module archive; `jlink` tạo runtime image.
- JMOD không phải executable JAR và không được chạy bằng `java -jar`.
- JMOD được thiết kế cho JDK tooling, đặc biệt quy trình linking; không dùng JMOD như thư viện classpath thông thường khi chạy ứng dụng.
- Modular JAR có thể chạy trên runtime phù hợp và cũng có thể được dùng làm module đầu vào cho `jlink`.
- Module image chứa runtime đã liên kết; nó không phải Docker/container image và không tự bao gồm toàn bộ hệ điều hành.

## 10. Kích thước và tính di động của module image

Một lợi ích của `jlink` là tạo runtime image chỉ chứa module ứng dụng cần và các dependency được giải quyết. Kích thước image phụ thuộc:

- Tập module được liên kết.
- Native library và tài nguyên đi kèm.
- Debug metadata.
- Plugin và mức nén được chọn.
- Legal notice, configuration, man page và header có được giữ lại hay không.

Module image có tính đặc thù nền tảng. Image được tạo cho Windows không thể mang sang Linux rồi chạy trực tiếp; kiến trúc CPU và native library cũng phải tương thích. Nên tạo image bằng JDK phù hợp với nền tảng đích hoặc toolchain hỗ trợ target platform đúng cách.

Nếu ứng dụng sử dụng JNI hoặc native library, `jlink` không tự chuyển đổi thư viện native sang nền tảng khác. Phải cung cấp đúng binary cho từng hệ điều hành/kiến trúc mục tiêu.

## 11. Lỗi thường gặp khi làm việc với JMOD và module image

### `jmod` hoặc `jlink` không được nhận diện

**Nguyên nhân:** PATH không trỏ đến `bin` của JDK hoặc máy chỉ cài runtime tối giản.

**Cách xử lý:** kiểm tra `JAVA_HOME`, dùng đường dẫn đầy đủ đến `jmod`/`jlink` trong JDK hoặc thêm `%JAVA_HOME%\bin` / `$JAVA_HOME/bin` vào PATH. Kiểm tra bằng `jmod --help` và `jlink --help`.

### Module descriptor không được tìm thấy

**Nguyên nhân:** thư mục đưa vào `--class-path` không có `module-info.class` ở gốc, hoặc mã nguồn chưa được biên dịch theo module.

**Cách xử lý:** biên dịch `module-info.java` cùng các lớp ứng dụng và xác nhận `out/module-info.class` tồn tại trước khi gọi `jmod create`.

### `jmod create` báo lỗi module hoặc archive

**Nguyên nhân:** module descriptor không hợp lệ, tên module không nhất quán, đường dẫn đầu vào sai hoặc thư mục section không tồn tại.

**Cách xử lý:** kiểm tra `module-info.java`, build output và đường dẫn `--class-path`; dùng `jmod describe` sau khi tạo để xác nhận metadata.

### `jmod list` không hiển thị file mong muốn

**Nguyên nhân:** file chưa được đưa vào đúng section hoặc thư mục nguồn không được chỉ định trong lệnh `jmod create`.

**Cách xử lý:** kiểm tra `--class-path`, `--libs`, `--cmds`, `--config`, `--header-files` và các tùy chọn section tương ứng. Tạo lại archive từ input đã xác nhận.

### `jlink` báo không tìm thấy module

**Nguyên nhân:** module path thiếu JDK `jmods`, thiếu JMOD ứng dụng hoặc tên module trong `--add-modules` không đúng.

**Cách xử lý:** xác nhận module có trong `jmod describe`, kiểm tra `--module-path` gồm cả `$JAVA_HOME/jmods` và thư mục JMOD ứng dụng, rồi dùng đúng tên module trong `--add-modules`.

### `jlink` báo thiếu dependency

**Nguyên nhân:** module descriptor không khai báo đúng `requires`, hoặc dependency không có trên module path.

**Cách xử lý:** kiểm tra `requires` trong `module-info.java`, bổ sung module tương ứng và chạy lại `jlink`. Các dependency bắt buộc phải được giải quyết trong module graph.

### Image chạy được trên máy build nhưng không chạy trên máy đích

**Nguyên nhân:** khác hệ điều hành/kiến trúc, thiếu quyền thực thi, native library không tương thích hoặc cấu hình image chưa phù hợp.

**Cách xử lý:** tạo image cho đúng nền tảng đích, kiểm tra quyền thực thi launcher, thư viện native và biến môi trường cần thiết. Không sao chép một image Windows sang Linux hoặc ngược lại.

### Ứng dụng không tìm thấy resource lúc chạy

**Nguyên nhân:** resource không được đóng gói trong module hoặc đường dẫn truy cập resource không đúng.

**Cách xử lý:** xác nhận resource nằm trong module output/JMOD và dùng API resource phù hợp như `Class.getResource` hoặc `Module.getResourceAsStream`. JMOD chỉ đóng gói những file thực sự có trong các section đầu vào.

## 12. Quy trình kiểm tra JMOD và image trong CI

Một quy trình build có thể tái hiện nên ghi nhận:

- Phiên bản JDK và nền tảng build.
- Tên module và module descriptor.
- Lệnh `javac` cùng release mục tiêu.
- Các đường dẫn đầu vào cho `jmod create`.
- Kết quả `jmod describe` và các entry quan trọng từ `jmod list`.
- Module path và module gốc truyền cho `jlink`.
- Tùy chọn launcher và plugin được dùng.
- Danh sách module trong image.
- Kết quả chạy smoke test trên image.
- Hệ điều hành và kiến trúc đích.

Các bước kiểm tra mẫu:

~~~text
java --version
javac --version
jmod describe mods/com.example.greeter.jmod
jmod list mods/com.example.greeter.jmod
jlink --list-plugins
greeter-image/bin/java --list-modules
~~~

Lệnh cuối dùng đường dẫn tương ứng trên Windows hoặc Unix-like system. Trong CI, hãy chạy launcher của image để xác nhận ứng dụng thật sự khởi động và kiểm tra stdout/exit code.

## 13. Checklist ghi nhớ

- [ ] JMOD là archive module của JDK, không phải JAR thông thường.
- [ ] JMOD có thể chứa class file, native library, command, config, header, legal notice và man page.
- [ ] `jmod list` liệt kê entry trong archive.
- [ ] `jmod describe` hiển thị module descriptor và metadata.
- [ ] `jmod extract` giải nén archive theo các section.
- [ ] `jmod create` đóng gói module đã biên dịch và các section bổ trợ.
- [ ] `module-info.class` phải nằm ở gốc class output khi tạo JMOD từ exploded module.
- [ ] JMOD không chạy trực tiếp bằng `java -jar`.
- [ ] `jlink` liên kết module và dependency thành runtime image.
- [ ] Module path cho `jlink` phải có JDK `jmods` và module ứng dụng.
- [ ] `--launcher` tạo lệnh khởi chạy thuận tiện trong image.
- [ ] Kiểm tra image bằng `java --list-modules` và chạy smoke test.
- [ ] Image phụ thuộc hệ điều hành, kiến trúc và native library.
- [ ] Dùng đúng JDK/toolchain cho nền tảng triển khai.

JMOD giúp đóng gói module cùng các thành phần bổ trợ theo cấu trúc mà JDK tooling hiểu được. Kết hợp `jmod` với `jlink`, bạn có thể đi từ mã nguồn modular đến một runtime image gọn, có launcher và chỉ chứa các module cần thiết cho ứng dụng.