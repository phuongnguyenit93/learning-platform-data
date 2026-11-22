# Công cụ thời điểm build trong JDK

## 1. Vai trò của công cụ build-time

Công cụ build-time là các chương trình trong JDK được dùng để biến mã nguồn và tài nguyên thành sản phẩm có thể kiểm tra, đóng gói và phân phối. Chúng tham gia vào các công đoạn như biên dịch `.java` thành `.class`, tạo JAR, sinh tài liệu API, phân tích phụ thuộc, tạo runtime image và đóng gói ứng dụng.

Một quy trình điển hình có thể đi theo thứ tự:

1. Biên dịch mã nguồn bằng `javac`.
2. Kiểm tra bytecode và phụ thuộc bằng `javap`, `jdeps` hoặc `jdeprscan` khi cần.
3. Sinh tài liệu API bằng `javadoc`.
4. Đóng gói lớp và tài nguyên bằng `jar`.
5. Với ứng dụng dạng module, tạo runtime tối giản bằng `jlink`.
6. Tạo gói phân phối bằng `jpackage`; ký JAR nếu quy trình phát hành yêu cầu.

Các công cụ này được cài cùng JDK và thường nằm trong thư mục `bin`. Maven, Gradle và Ant là các hệ thống build riêng; chúng có thể gọi những công cụ JDK này để tự động hóa quy trình, nhưng bản thân chúng không phải là lệnh build-time thuộc JDK.

Không phải dự án nào cũng cần tất cả công cụ. Ứng dụng nhỏ có thể chỉ cần `javac` và `jar`; thư viện công khai thường cần thêm `javadoc`; ứng dụng module có thể dùng `jdeps` và `jlink`; sản phẩm phân phối cho người dùng cuối có thể cần `jpackage`.

## 2. `javac` — biên dịch mã nguồn Java

`javac` đọc tệp `.java`, kiểm tra cú pháp và kiểu, sau đó sinh bytecode trong tệp `.class`. Bytecode chạy trên JVM tương thích với phiên bản Java mục tiêu.

Ví dụ cấu trúc dự án:

~~~text
project/
├── src/
│   └── com/
│       └── example/
│           └── Hello.java
└── out/
~~~

Nội dung `src/com/example/Hello.java`:

~~~java
package com.example;

public class Hello {
    public static void main(String[] args) {
        String name = args.length == 0 ? "JDK" : args[0];
        System.out.println("Hello, " + name + "!");
    }
}
~~~

Tạo thư mục đầu ra và biên dịch với API Java 17:

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 -Xlint:all -d out src/com/example/Hello.java
java -cp out com.example.Hello Java
~~~

Kết quả:

~~~text
Hello, Java!
~~~

Trên Windows PowerShell, có thể tạo thư mục đầu ra bằng:

~~~powershell
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -Xlint:all -d out src/com/example/Hello.java
java -cp out com.example.Hello Java
~~~

Các tùy chọn `javac` thường gặp:

| Tùy chọn | Ý nghĩa |
|---|---|
| `--release 17` | Biên dịch theo phiên bản Java 17, gồm mức ngôn ngữ, định dạng bytecode và tập API công khai của phiên bản đó. Đây thường là lựa chọn tốt khi build bằng JDK mới hơn nhưng cần chạy trên Java 17. |
| `-source 17` | Chỉ định cú pháp/ngôn ngữ nguồn được chấp nhận. |
| `-target 17` | Chỉ định phiên bản bytecode đầu ra. Dùng riêng `-source` và `-target` không bảo đảm mã chỉ gọi các API có trong Java 17; `--release` xử lý cả giới hạn API. |
| `-encoding UTF-8` | Chỉ định bảng mã đọc tệp nguồn. Nên khai báo rõ để tránh khác biệt giữa máy phát triển và CI. |
| `-d out` | Đặt các tệp `.class` vào thư mục `out`; cấu trúc package được giữ bên dưới thư mục này. |
| `-classpath` hoặc `-cp` | Khai báo JAR/thư mục chứa các lớp cần thiết khi biên dịch. |
| `--module-path` | Khai báo đường dẫn chứa các module khi biên dịch dự án dùng Java Platform Module System (JPMS). |
| `-Xlint:all` | Bật các cảnh báo biên dịch phổ biến. |
| `-Werror` | Chuyển cảnh báo thành lỗi; thường dùng trong CI sau khi dự án đã xử lý các cảnh báo hiện có. |
| `-parameters` | Lưu tên tham số phương thức trong bytecode để thư viện dùng reflection có thể đọc được. |
| `-g` | Sinh thông tin debug như số dòng và biến cục bộ. |
| `@file` | Đọc danh sách tùy chọn và tệp nguồn từ một argument file, hữu ích khi lệnh quá dài. |

Ví dụ biên dịch nhiều tệp, trong đó `lib/*` chứa các JAR phụ thuộc:

~~~bash
javac --release 17 -classpath "lib/*" -d out src/com/example/*.java
~~~

Khi dùng classpath, các lớp được tìm theo tên package và class. Khi dùng JPMS, cần cấu hình module path và khai báo module phù hợp; không nên trộn hai cơ chế một cách tùy tiện.

Một số lỗi thường gặp:

- `package ... does not exist`: thiếu thư viện trong classpath/module path hoặc đường dẫn nguồn chưa đúng.
- `cannot find symbol`: tên lớp, phương thức hoặc biến không đúng; hoặc thiếu import/phụ thuộc.
- `invalid source release`: JDK đang chạy `javac` quá cũ so với phiên bản `--release` yêu cầu.
- `UnsupportedClassVersionError` khi chạy: runtime thấp hơn phiên bản bytecode đã biên dịch. Hãy đồng bộ phiên bản runtime hoặc biên dịch với `--release` thấp hơn.

## 3. `jar` — đóng gói lớp và tài nguyên

JAR (Java Archive) là tệp ZIP có cấu trúc và quy ước dành cho ứng dụng Java. JAR có thể chứa bytecode, tài nguyên, metadata và manifest. Nó thuận tiện để phân phối ứng dụng hoặc thư viện.

Tạo JAR có khai báo lớp khởi chạy:

~~~bash
jar --create --file app.jar --main-class com.example.Hello -C out .
~~~

Trong đó:

- `--create` tạo JAR mới.
- `--file app.jar` đặt tên tệp đầu ra.
- `--main-class` ghi lớp có phương thức `main` vào manifest.
- `-C out .` chuyển vào thư mục `out` trước khi thêm nội dung, nhờ đó JAR chứa `com/example/Hello.class` thay vì một đường dẫn lồng `out/`.

Liệt kê nội dung và chạy ứng dụng:

~~~bash
jar --list --file app.jar
java -jar app.jar Java
~~~

Kết quả của lệnh chạy:

~~~text
Hello, Java!
~~~

Các thao tác thường dùng khác:

~~~bash
# Giải nén JAR vào thư mục hiện tại
jar --extract --file app.jar

# Cập nhật hoặc thêm tệp vào JAR đã có
jar --update --file app.jar -C resources .

# Xem mô tả module của một modular JAR
jar --describe-module --file app.jar
~~~

Một vài điểm cần nhớ:

- `java -jar app.jar` dùng lớp khởi chạy trong manifest. Nếu không có `Main-Class`, JVM không biết lớp nào cần chạy.
- `java -cp app.jar com.example.Hello` chỉ định lớp chạy trực tiếp; classpath có thể chứa nhiều thư mục và JAR.
- JAR thông thường có thể chạy trên classpath. Modular JAR còn có `module-info.class` và có thể được đặt trên module path.
- Thay đổi nội dung JAR sau khi ký sẽ làm chữ ký không còn hợp lệ; hãy ký sau khi hoàn tất đóng gói.

## 4. `javadoc` — sinh tài liệu API

`javadoc` đọc mã nguồn và các chú thích Javadoc để tạo tài liệu HTML cho package, lớp, constructor, phương thức và API công khai.

Ví dụ chú thích trên phương thức:

~~~java
/**
 * Trả về lời chào cho một người.
 *
 * @param name tên người nhận lời chào
 * @return chuỗi lời chào
 */
public static String greeting(String name) {
    return "Hello, " + name + "!";
}
~~~

Sinh tài liệu cho package `com.example`:

~~~bash
javadoc -d docs -sourcepath src -subpackages com.example
~~~

Thư mục `docs` chứa trang HTML có thể mở bằng trình duyệt. Với thư viện, nên viết Javadoc cho các API công khai, mô tả tham số, giá trị trả về, ngoại lệ và điều kiện sử dụng. Các thẻ thường gặp gồm:

- `@param`: mô tả tham số.
- `@return`: mô tả giá trị trả về.
- `@throws` hoặc `@exception`: mô tả ngoại lệ có thể được ném.
- `@since`: phiên bản bắt đầu cung cấp API.
- `@deprecated`: đánh dấu API không còn được khuyến nghị và nêu lựa chọn thay thế.
- `{@link ...}`: tạo liên kết tới lớp hoặc thành phần API khác.

Javadoc là tài liệu cho người dùng API; nó không thay thế README hướng dẫn cài đặt, ví dụ chạy ứng dụng hoặc tài liệu kiến trúc.

## 5. `javap` — xem cấu trúc bytecode

`javap` là trình disassembler của JDK. Nó đọc tệp `.class` hoặc lớp trong JAR và hiển thị chữ ký lớp, phương thức, bytecode cùng metadata. Công cụ này hữu ích khi cần xác nhận compiler đã sinh ra gì, kiểm tra overload, generic signature hoặc điều tra khác biệt giữa các bản build.

~~~bash
# Xem chữ ký lớp và phương thức
javap -classpath out com.example.Hello

# Hiển thị bytecode của các phương thức
javap -classpath out -c com.example.Hello

# Hiển thị cả thành viên private
javap -classpath out -p com.example.Hello

# Hiển thị thông tin chi tiết của class file
javap -classpath out -verbose com.example.Hello
~~~

`javap` chỉ giúp quan sát bytecode; nó không thay thế debugger và cũng không khôi phục chính xác mã nguồn ban đầu.

## 6. `jdeps` và `jdeprscan` — phân tích phụ thuộc, API lỗi thời

`jdeps` phân tích phụ thuộc ở cấp package, lớp hoặc module. Nó giúp phát hiện thư viện phụ thuộc vào module nào của JDK, hỗ trợ chuẩn bị ứng dụng cho JPMS và tìm việc sử dụng API nội bộ.

~~~bash
# Tóm tắt phụ thuộc của JAR
jdeps --summary app.jar

# Phân tích phụ thuộc đệ quy
jdeps --recursive app.jar

# In danh sách module JDK cần thiết
jdeps --print-module-deps app.jar

# Tìm việc sử dụng API nội bộ của JDK
jdeps --jdk-internals app.jar
~~~

Kết quả phụ thuộc module có thể dùng làm đầu vào cho `jlink`. Khi phân tích thư viện có nhiều phiên bản class trong multi-release JAR, cần chọn phiên bản đích phù hợp bằng tùy chọn `--multi-release`.

`jdeps` chỉ phân tích những phụ thuộc có thể suy ra từ bytecode và đường dẫn đã cung cấp. Nó không thay thế kiểm thử tích hợp, không phát hiện mọi phụ thuộc được nạp động qua reflection và không thể tự xác nhận toàn bộ hành vi lúc chạy.

`jdeprscan` quét bytecode để tìm việc sử dụng API đã bị đánh dấu deprecated trong một phiên bản Java cụ thể:

~~~bash
jdeprscan --release 17 app.jar
~~~

Dùng kết quả để lập kế hoạch thay thế API cũ. Deprecated không đồng nghĩa với đã bị xóa; cần đọc tài liệu API và kiểm tra phiên bản mục tiêu trước khi sửa.

## 7. JPMS, `jmod` và `jlink`

Java Platform Module System (JPMS) cho phép ứng dụng khai báo module, phụ thuộc module và package được xuất ra bên ngoài. Tệp `module-info.java` mô tả module.

Ví dụ `src/module-info.java`:

~~~java
module com.example.hello {
    exports com.example;
}
~~~

Giữ `Hello.java` trong package `com.example`, sau đó biên dịch và đóng gói module:

~~~bash
javac --release 17 -d mods/com.example.hello src/module-info.java src/com/example/Hello.java
jar --create --file mlib/com.example.hello.jar --main-class com.example.Hello -C mods/com.example.hello .
java --module-path mlib -m com.example.hello/com.example.Hello Java
~~~

Ở đây:

- `mods/com.example.hello` là thư mục chứa module đã biên dịch.
- `mlib` là thư mục chứa modular JAR.
- `--module-path` chỉ đường dẫn tìm module.
- `-m` hoặc `--module` chỉ định module và lớp khởi chạy.

### `jmod`

JMOD là định dạng lưu trữ module được dùng chủ yếu trong quá trình tạo runtime image. Công cụ `jmod` có thể tạo, liệt kê, mô tả và kiểm tra tệp JMOD.

~~~bash
# Tạo JMOD từ module đã biên dịch
jmod create --class-path mods/com.example.hello --module-version 1.0 mlib/com.example.hello.jmod

# Xem mô tả module
jmod describe mlib/com.example.hello.jmod

# Liệt kê nội dung
jmod list mlib/com.example.hello.jmod
~~~

JMOD không phải định dạng thay thế trực tiếp cho JAR thông thường trong classpath. Nó chủ yếu phục vụ các công cụ module của JDK, đặc biệt là `jlink`.

### `jlink`

`jlink` ghép các module ứng dụng và module nền tảng cần thiết để tạo một runtime image tùy chỉnh. Runtime image này có thể nhỏ hơn một JDK đầy đủ vì chỉ chứa các module được chọn và phần phụ thuộc của chúng.

Ví dụ trên Windows PowerShell:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mlib" --add-modules com.example.hello --launcher hello=com.example.hello/com.example.Hello --output runtime-image
~~~

Trên macOS/Linux, dấu phân cách module path là dấu hai chấm:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mlib" --add-modules com.example.hello --launcher hello=com.example.hello/com.example.Hello --output runtime-image
~~~

Chạy launcher được tạo:

~~~powershell
.\runtime-image\bin\hello.bat
~~~

~~~bash
./runtime-image/bin/hello
~~~

Điều kiện và giới hạn quan trọng:

- Ứng dụng và các phụ thuộc cần được tổ chức thành module phù hợp; `jlink` không thể ghép tùy ý mọi thư viện classpath chưa được modular hóa.
- Module path phải chứa các module ứng dụng và các module nền tảng tương ứng, thường lấy từ thư mục `jmods` của JDK.
- Runtime image gắn với nền tảng/kiến trúc được tạo ra. Cần tạo image riêng cho từng hệ điều hành và kiến trúc cần hỗ trợ.
- `jlink` tạo runtime để chạy ứng dụng; nó không tạo bộ cài đặt native cho người dùng.

## 8. `jpackage` — đóng gói ứng dụng để phân phối

`jpackage` tạo application image hoặc gói cài đặt native từ ứng dụng Java. Công cụ có thể tạo runtime image đi kèm ứng dụng nếu không được cung cấp runtime image riêng.

Giả sử `dist` chứa `hello.jar`, có thể tạo application image:

~~~bash
jpackage --type app-image --name HelloApp --input dist --main-jar hello.jar --main-class com.example.Hello --dest packages
~~~

Các loại gói thường gặp tùy hệ điều hành:

- Windows: `msi` hoặc `exe`.
- macOS: `dmg` hoặc `pkg`.
- Linux: `deb` hoặc `rpm`.

Ví dụ tạo MSI trên Windows:

~~~powershell
jpackage --type msi --name HelloApp --input dist --main-jar hello.jar --main-class com.example.Hello --dest packages
~~~

Một số loại installer cần công cụ đóng gói tương ứng được cài trên máy build. Gói native thường được tạo trên đúng hệ điều hành đích; hãy kiểm tra yêu cầu của JDK và nền tảng trước khi thiết lập CI đa nền tảng.

Phân biệt:

- JAR là định dạng đóng gói Java có thể chạy trên JVM tương thích.
- Application image là thư mục chứa ứng dụng và runtime cần thiết.
- Native installer là gói cài đặt theo nền tảng, tích hợp với cơ chế cài đặt của hệ điều hành.

## 9. `keytool` và `jarsigner` — quản lý chứng thư và ký JAR

`keytool` quản lý keystore, cặp khóa và chứng thư số. `jarsigner` ký JAR và xác minh chữ ký. Hai công cụ này thường xuất hiện trong quy trình phát hành cần xác thực nguồn gốc và tính toàn vẹn của JAR.

Tạo keystore PKCS12 và cặp khóa:

~~~bash
keytool -genkeypair -alias release -keyalg RSA -keysize 3072 -validity 365 -storetype PKCS12 -keystore release.p12
~~~

Lệnh sẽ yêu cầu thông tin chứng thư và mật khẩu keystore. Ký JAR:

~~~bash
jarsigner -keystore release.p12 -storetype PKCS12 app.jar release
~~~

Xác minh chữ ký:

~~~bash
jarsigner -verify -verbose -certs app.jar
~~~

Lưu ý khi phát hành:

- Bảo vệ private key và mật khẩu keystore; không đưa chúng vào source control hoặc log CI.
- Chỉ ký sau khi JAR đã hoàn thiện. Mọi thay đổi nội dung sau khi ký có thể làm xác minh chữ ký thất bại.
- Chữ ký JAR xác minh tính toàn vẹn và danh tính theo chứng thư; nó không chứng minh ứng dụng an toàn hoặc không có lỗi.
- Quy trình ký mã và quy trình ký installer của hệ điều hành có thể là hai bước riêng.

## 10. Một số công cụ JDK khác có thể gặp

| Công cụ | Công dụng chính | Khi nào hữu ích |
|---|---|---|
| `jdeprscan` | Tìm API deprecated được sử dụng trong bytecode. | Nâng cấp phiên bản Java hoặc loại bỏ API cũ. |
| `serialver` | In `serialVersionUID` của lớp Serializable. | Kiểm tra tương thích serialization. |
| `jmod` | Tạo và kiểm tra module archive. | Chuẩn bị module cho runtime image. |
| `keytool` | Quản lý khóa, keystore và chứng thư. | Thiết lập truststore hoặc quy trình ký. |
| `jarsigner` | Ký và xác minh JAR. | Phát hành JAR cần chữ ký số. |
| `jshell` | REPL tương tác để thử biểu thức và API Java. | Thử nghiệm nhanh trong lúc phát triển; không phải bước đóng gói build thông thường. |

Không nên nhầm các công cụ build-time với công cụ giám sát JVM lúc chạy như `jcmd`, `jstack`, `jmap` hoặc `jstat`. Các công cụ đó phục vụ chẩn đoán tiến trình Java đang chạy.

## 11. Kết hợp công cụ trong quy trình build

Một quy trình thủ công tối giản cho ví dụ ở trên có thể là:

~~~bash
# 1. Biên dịch theo Java 17 và bật cảnh báo
mkdir -p out
javac --release 17 -encoding UTF-8 -Xlint:all -d out src/com/example/Hello.java

# 2. Sinh tài liệu API
javadoc -d docs -sourcepath src -subpackages com.example

# 3. Đóng gói ứng dụng
jar --create --file app.jar --main-class com.example.Hello -C out .

# 4. Phân tích phụ thuộc
jdeps --summary app.jar

# 5. Chạy kiểm tra thủ công
java -jar app.jar Java
~~~

Trong dự án thực tế, Maven hoặc Gradle thường quản lý dependency, source set, test, plugin và thứ tự các bước. Các hệ thống này gọi `javac`, `jar`, `javadoc` hoặc những công cụ liên quan thay cho việc chạy lệnh thủ công. Nên giữ phiên bản JDK nhất quán giữa máy phát triển và CI, khai báo rõ phiên bản đích bằng `--release`, cố định phiên bản dependency và tách thư mục đầu ra khỏi mã nguồn.

Một pipeline phát hành có thể bổ sung các bước sau khi build thành công:

1. Chạy unit test và integration test.
2. Dùng `jdeps` để rà soát phụ thuộc và module cần thiết.
3. Dùng `jlink` nếu muốn phân phối runtime tối giản cho ứng dụng modular.
4. Dùng `jpackage` để tạo application image hoặc installer.
5. Ký các artifact phù hợp bằng quy trình bảo vệ khóa riêng.
6. Lưu artifact, checksum và thông tin phiên bản build để truy vết.

## 12. Lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra/xử lý |
|---|---|---|
| `javac` không được nhận diện | `PATH` chưa trỏ tới thư mục `bin` của JDK hoặc chỉ cài JRE. | Chạy `java -version`, `javac -version`; kiểm tra `JAVA_HOME` và `PATH`. |
| Biên dịch được nhưng chạy báo không tìm thấy lớp | Sai classpath, sai tên đầy đủ của lớp hoặc cấu trúc package. | Kiểm tra thư mục đầu ra và chạy với tên lớp đầy đủ, ví dụ `com.example.Hello`. |
| `no main manifest attribute` | JAR không có `Main-Class`. | Tạo lại JAR với `jar --main-class` hoặc manifest phù hợp. |
| `UnsupportedClassVersionError` | Runtime thấp hơn phiên bản bytecode. | Đồng bộ runtime hoặc build với `javac --release` phù hợp. |
| `jlink` báo không tìm thấy module | Thiếu module trên module path hoặc ứng dụng chưa được modular hóa đúng. | Kiểm tra `module-info.java`, `--module-path` và kết quả `jdeps --print-module-deps`. |
| `jpackage` không tạo được installer | Thiếu công cụ native cần thiết hoặc build trên nền tảng không phù hợp. | Kiểm tra loại gói, hệ điều hành đích và yêu cầu của JDK. |
| `jarsigner -verify` báo chữ ký không hợp lệ | JAR bị thay đổi sau khi ký hoặc chứng thư/chữ ký có vấn đề. | Tạo lại artifact sạch, ký lại và xác minh sau cùng. |

Để chẩn đoán phiên bản công cụ đang được gọi, chạy:

~~~bash
java -version
javac -version
jar --version
javadoc --version
jdeps --version
jlink --version
jpackage --version
~~~

Nếu `java` và `javac` trỏ tới hai JDK khác nhau, kết quả build có thể không nhất quán. Hãy kiểm tra đường dẫn thực tế của các lệnh và cấu hình `JAVA_HOME`/`PATH` để chúng cùng dùng một JDK.

## 13. Bảng ghi nhớ nhanh

| Nhu cầu | Công cụ |
|---|---|
| Biên dịch `.java` thành `.class` | `javac` |
| Đóng gói lớp và tài nguyên thành JAR | `jar` |
| Sinh tài liệu API HTML | `javadoc` |
| Xem bytecode và chữ ký lớp | `javap` |
| Phân tích phụ thuộc package/module | `jdeps` |
| Tìm việc sử dụng API deprecated | `jdeprscan` |
| Tạo/kiểm tra module archive | `jmod` |
| Tạo runtime image tùy chỉnh | `jlink` |
| Tạo application image hoặc installer | `jpackage` |
| Quản lý keystore và chứng thư | `keytool` |
| Ký và xác minh JAR | `jarsigner` |
| Kiểm tra `serialVersionUID` | `serialver` |

Khi lựa chọn công cụ, hãy bắt đầu từ artifact cần tạo: `.class` cần `javac`, JAR cần `jar`, tài liệu API cần `javadoc`, runtime tối giản cần `jlink`, còn installer cần `jpackage`. Dùng `jdeps`, `javap`, `jdeprscan`, `keytool` và `jarsigner` khi yêu cầu phân tích, tương thích hoặc phát hành đòi hỏi chúng.
