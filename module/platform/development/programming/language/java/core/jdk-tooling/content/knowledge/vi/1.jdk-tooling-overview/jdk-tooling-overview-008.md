# Công cụ đóng gói ứng dụng Java

Đóng gói là bước biến các lớp đã biên dịch, tài nguyên và cấu hình của ứng dụng thành dạng có thể chạy hoặc phân phối. Tùy mục tiêu, sản phẩm có thể là một tệp JAR, một ứng dụng module, một runtime Java rút gọn hoặc bộ cài đặt dành cho hệ điều hành.

Bài này tập trung vào các công cụ đi kèm JDK 17 trở lên: `jar`, `jmod`, `jdeps`, `jlink`, `jpackage`, `keytool` và `jarsigner`. Các lệnh này nằm trong thư mục `bin` của JDK. Hãy dùng JDK để thực hiện các bước đóng gói; một runtime Java thông thường không cung cấp đầy đủ bộ công cụ này.

## 1. Chọn công cụ theo kết quả cần tạo

| Công cụ | Vai trò | Kết quả thường dùng |
|---|---|---|
| `jar` | Gom class, tài nguyên và manifest vào một archive | JAR thường hoặc JAR có thể chạy |
| `jmod` | Tạo và kiểm tra module archive dành cho quá trình liên kết runtime | Tệp JMOD |
| `jdeps` | Phân tích phụ thuộc giữa package, JAR và module | Danh sách phụ thuộc cần thiết |
| `jlink` | Ghép các module cần thiết thành runtime Java tùy chỉnh | Thư mục runtime có thể chạy |
| `jpackage` | Đóng gói ứng dụng cùng runtime thành application image hoặc bộ cài đặt | App image, MSI, EXE, DMG, PKG, DEB hoặc RPM tùy nền tảng |
| `keytool` | Tạo và quản lý khóa, chứng thư và keystore | Keystore và chứng thư |
| `jarsigner` | Ký và xác minh chữ ký của JAR | JAR đã ký |

Không phải ứng dụng nào cũng cần tất cả các công cụ. Với ứng dụng nhỏ, một JAR có manifest thường là đủ. Khi muốn người dùng không phải cài Java riêng, có thể tạo runtime bằng `jlink` hoặc để `jpackage` tạo runtime trong quá trình đóng gói.

## 2. Đóng gói JAR bằng `jar`

JAR (Java Archive) là tệp archive dựa trên định dạng ZIP. Nó thường chứa:

- Các tệp bytecode `.class` đã biên dịch.
- Tài nguyên như cấu hình, ảnh, tệp mẫu và dữ liệu.
- Thư mục `META-INF`, trong đó có manifest `MANIFEST.MF`.
- Chữ ký số nếu JAR đã được ký.

JAR không tự biên dịch mã nguồn. Trước tiên dùng `javac` để tạo bytecode, sau đó dùng `jar` để gom các tệp cần phân phối.

### 2.1. Tạo một executable JAR

Giả sử có cấu trúc dự án sau:

~~~text
project/
├── src/
│   └── com/
│       └── example/
│           └── HelloApp.java
├── out/
└── dist/
~~~

Nội dung `src/com/example/HelloApp.java`:

~~~java
package com.example;

public class HelloApp {
    public static void main(String[] args) {
        System.out.println("Hello from a packaged JAR.");
    }
}
~~~

Từ thư mục `project`, chạy các lệnh sau trong PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path out, dist | Out-Null
javac -d out src/com/example/HelloApp.java
jar --create --file dist/hello.jar --main-class com.example.HelloApp -C out .
java -jar dist/hello.jar
~~~

Trên Bash hoặc Zsh, lệnh tạo thư mục tương ứng là `mkdir -p out dist`; ba lệnh `javac`, `jar` và `java` còn lại giữ nguyên.

Kết quả chạy:

~~~text
Hello from a packaged JAR.
~~~

Giải thích:

- `javac -d out ...` biên dịch mã nguồn và đặt các tệp `.class` vào `out` theo cấu trúc package.
- `jar --create` yêu cầu tạo archive mới.
- `--file dist/hello.jar` chỉ định đường dẫn tệp JAR.
- `--main-class com.example.HelloApp` ghi lớp có phương thức `main` vào manifest dưới thuộc tính `Main-Class`.
- `-C out .` chuyển thư mục làm việc của lệnh `jar` sang `out` rồi thêm toàn bộ nội dung của thư mục đó vào archive.
- `java -jar` chạy JAR dựa trên thông tin điểm vào trong manifest.

Có thể kiểm tra nội dung archive mà không giải nén:

~~~powershell
jar --list --file dist/hello.jar
~~~

Để giải nén vào một thư mục riêng:

~~~powershell
jar --extract --file dist/hello.jar --dir extracted
~~~

### 2.2. Manifest và điểm vào của ứng dụng

Manifest là tệp văn bản trong `META-INF/MANIFEST.MF`. Với một executable JAR đơn giản, thuộc tính quan trọng nhất là `Main-Class`:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.HelloApp

~~~

Dòng trống ở cuối phần thuộc tính là một phần của định dạng manifest. Khi dùng `jar --main-class`, công cụ tạo thuộc tính này giúp bạn.

Nếu chạy `java -jar app.jar` mà nhận thông báo `no main manifest attribute`, JAR chưa có `Main-Class` hợp lệ. Hãy tạo lại JAR với `--main-class` hoặc cung cấp manifest đúng.

### 2.3. JAR có thư viện phụ thuộc

Một JAR chỉ chứa những tệp bạn đưa vào khi đóng gói. Nếu ứng dụng dùng thư viện bên ngoài, các thư viện đó cũng phải được phân phối và nằm trên classpath hoặc module path khi chạy.

Với ứng dụng classpath, có thể chạy lớp chính trực tiếp:

~~~powershell
java -cp "dist/hello.jar;lib/*" com.example.HelloApp
~~~

Dấu phân cách classpath là dấu chấm phẩy trên Windows và dấu hai chấm trên Linux/macOS. Khi dùng `java -jar`, tùy chọn classpath bên ngoài không được dùng để thay thế classpath của ứng dụng; cần khai báo phụ thuộc theo cách phù hợp, chẳng hạn thuộc tính `Class-Path` trong manifest, hoặc chạy lớp chính với `-cp` như ví dụ trên.

## 3. Đóng gói ứng dụng theo Java Platform Module System

Từ Java 9, ứng dụng có thể được tổ chức thành module. Một module khai báo tên, các package được xuất và những module mà nó phụ thuộc trong tệp `module-info.java`.

Ví dụ, thêm tệp `src/module-info.java`:

~~~java
module com.example.hello {
    exports com.example;
}
~~~

Biên dịch và đóng gói module:

~~~powershell
New-Item -ItemType Directory -Force -Path mods/com.example.hello, dist | Out-Null
javac -d mods/com.example.hello src/module-info.java src/com/example/HelloApp.java
jar --create --file dist/com.example.hello.jar --main-class com.example.HelloApp -C mods/com.example.hello .
jar --describe-module --file dist/com.example.hello.jar
~~~

Tệp JAR lúc này chứa cả `module-info.class`. Lệnh `jar --describe-module` cho biết tên module, các package được xuất, module phụ thuộc và lớp chính nếu đã khai báo.

Chạy module trên module path:

~~~powershell
java --module-path dist --module com.example.hello
~~~

Có thể viết ngắn tùy chọn `--module` thành `-m`. Module path là nơi JVM tìm các module; nó khác với classpath vốn được dùng để tìm các lớp của ứng dụng không tổ chức theo module.

Một JAR không có `module-info.class` đôi khi có thể được dùng như automatic module trên module path. Tên automatic module có thể được suy ra từ tên tệp hoặc khai báo trong manifest. Tuy vậy, automatic module không thay thế cho một module được thiết kế tường minh, và có giới hạn khi dùng với `jlink`.

## 4. JMOD: module archive dành cho bước liên kết

JMOD là định dạng archive của JDK dành cho nội dung module ở giai đoạn phát triển và liên kết runtime. Ngoài lớp và tài nguyên, JMOD có thể chứa native library, lệnh, tệp cấu hình, header, tài liệu và thông tin pháp lý.

Ví dụ, tạo JMOD từ thư mục module đã biên dịch:

~~~powershell
jmod create --class-path mods/com.example.hello --main-class com.example.HelloApp --module-version 1.0.0 dist/com.example.hello.jmod
jmod describe dist/com.example.hello.jmod
jmod list dist/com.example.hello.jmod
~~~

Các lệnh hữu ích:

- `jmod create` tạo tệp JMOD.
- `jmod describe` hiển thị mô tả module.
- `jmod list` liệt kê nội dung archive.

JMOD chủ yếu phục vụ việc tạo runtime bằng `jlink`. Trong quy trình phân phối ứng dụng thông thường, JAR thường thuận tiện hơn. Không đưa JMOD vào classpath để chạy như JAR; hãy dùng nó ở bước liên kết module khi phù hợp.

## 5. Phân tích phụ thuộc bằng `jdeps`

`jdeps` phân tích các phụ thuộc mà bytecode tham chiếu. Công cụ này giúp xác định ứng dụng cần những module JDK nào, đặc biệt trước khi tạo runtime tối giản.

~~~powershell
jdeps --summary dist/com.example.hello.jar
jdeps --print-module-deps dist/com.example.hello.jar
~~~

- `--summary` tóm tắt phụ thuộc theo module.
- `--print-module-deps` in danh sách module cần thiết theo định dạng có thể dùng với `jlink --add-modules`.

Với ứng dụng có thư viện bên ngoài, cần đưa các thư viện đó vào phạm vi phân tích bằng classpath hoặc module path thích hợp. Ví dụ, có thể dùng `--class-path "lib/*"` khi phân tích ứng dụng classpath.

`jdeps` phân tích tĩnh bytecode. Những phụ thuộc được nạp động qua reflection, tên lớp được tạo từ chuỗi, cấu hình bên ngoài hoặc cơ chế plugin có thể không được nhận diện đầy đủ. Vì vậy, kết quả phân tích là cơ sở để kiểm tra, không thay thế cho việc chạy thử các chức năng thực tế.

## 6. Tạo runtime tùy chỉnh bằng `jlink`

Một JDK đầy đủ chứa nhiều module mà một ứng dụng cụ thể không cần. `jlink` ghép các module được chọn cùng những phụ thuộc cần thiết thành một runtime image. Người dùng có thể chạy ứng dụng bằng runtime này mà không cần cài riêng một JRE tương thích.

### 6.1. Liên kết runtime từ các module

Với module `com.example.hello` ở phần trước, chạy lệnh sau trong PowerShell trên Windows:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;dist" --add-modules com.example.hello --launcher hello=com.example.hello/com.example.HelloApp --output runtime --strip-debug --no-header-files --no-man-pages
~~~

Trên Linux/macOS, dấu phân cách các đường dẫn module là dấu hai chấm:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:dist" --add-modules com.example.hello --launcher hello=com.example.hello/com.example.HelloApp --output runtime --strip-debug --no-header-files --no-man-pages
~~~

Lệnh trên thực hiện các việc sau:

- `--module-path` chỉ ra nơi tìm các module JDK và module ứng dụng.
- `--add-modules` chọn module gốc; `jlink` tự đưa các module phụ thuộc cần thiết vào runtime.
- `--launcher hello=...` tạo lệnh khởi chạy có tên `hello`.
- `--output runtime` chỉ định thư mục runtime image. Thư mục đích cần chưa tồn tại hoặc đang rỗng.
- `--strip-debug` loại bỏ thông tin debug không cần cho runtime phân phối.
- `--no-header-files` và `--no-man-pages` bỏ header và trang hướng dẫn để giảm dung lượng.

Sau khi tạo xong, có thể chạy launcher từ runtime image:

~~~powershell
.\runtime\bin\hello.bat
~~~

Trên Linux/macOS, launcher nằm trong `runtime/bin/hello`. Nếu không tạo launcher riêng, có thể gọi trực tiếp chương trình Java trong runtime, ví dụ `runtime/bin/java -m com.example.hello`.

### 6.2. Những giới hạn cần biết

`jlink` làm việc với các module tường minh có module descriptor. Một JAR chỉ là automatic module không thể được liên kết trực tiếp thành runtime image. Nếu ứng dụng chưa có module descriptor, hãy cân nhắc giữ mô hình classpath và dùng `jpackage`, hoặc thiết kế lại thành module trước khi dùng `jlink`.

Runtime image gắn với nền tảng hệ điều hành và kiến trúc mà nó được tạo cho. Hãy xây dựng và kiểm thử runtime trên môi trường đích phù hợp. Runtime tùy chỉnh cũng không tự tạo bộ cài đặt; nó chỉ cung cấp môi trường Java cần thiết để chạy ứng dụng.

## 7. Đóng gói ứng dụng bằng `jpackage`

`jpackage` tạo application image hoặc bộ cài đặt cho ứng dụng Java. Nó có thể đóng gói JAR cùng runtime, nhờ đó người dùng cuối không phải tự cài Java riêng.

### 7.1. Đóng gói ứng dụng classpath

Với `dist/hello.jar` ở phần 2, chạy:

~~~powershell
jpackage --type app-image --name HelloApp --app-version 1.0.0 --input dist --main-jar hello.jar --main-class com.example.HelloApp --dest packages
~~~

Ý nghĩa các tùy chọn:

- `--type app-image` tạo thư mục ứng dụng có thể chạy trên nền tảng hiện tại.
- `--name` đặt tên ứng dụng.
- `--app-version` đặt phiên bản hiển thị của ứng dụng.
- `--input` chỉ định thư mục chứa JAR và các tệp cần phân phối.
- `--main-jar` chọn JAR chính bên trong thư mục input.
- `--main-class` chỉ định lớp chính nếu JAR không tự cung cấp thông tin phù hợp.
- `--dest` chỉ định nơi đặt kết quả.

`jpackage` sẽ tạo runtime image nếu bạn không cung cấp runtime có sẵn. Có thể dùng `--runtime-image runtime` để sử dụng runtime image đã tạo bằng `jlink`, miễn là runtime đó chứa đầy đủ module và thành phần ứng dụng cần thiết.

### 7.2. Đóng gói ứng dụng module

Với module `com.example.hello` đã được đóng gói ở phần 3 và runtime đã tạo ở phần 6, có thể dùng cú pháp module:

~~~powershell
jpackage --type app-image --name HelloApp --module-path dist --module com.example.hello/com.example.HelloApp --runtime-image runtime --dest packages
~~~

Ở chế độ module, `--module-path` và `--module` xác định module cùng lớp chính. Cách khai báo này khác với chế độ classpath dùng `--input` và `--main-jar`; không trộn hai bộ tùy chọn như thể chúng là một ứng dụng duy nhất.

### 7.3. Tạo bộ cài đặt theo hệ điều hành

Thay `--type app-image` bằng loại bộ cài đặt được hỗ trợ trên máy build, ví dụ:

| Nền tảng | Loại gói thường gặp |
|---|---|
| Windows | `msi` hoặc `exe` |
| macOS | `dmg` hoặc `pkg` |
| Linux | `deb` hoặc `rpm` |

Ví dụ tạo gói MSI trên Windows:

~~~powershell
jpackage --type msi --name HelloApp --app-version 1.0.0 --input dist --main-jar hello.jar --main-class com.example.HelloApp --dest packages
~~~

Loại gói có sẵn phụ thuộc hệ điều hành, kiến trúc và công cụ hỗ trợ trên máy build. Bộ cài đặt native cần được tạo và kiểm thử trên nền tảng đích; một lệnh tạo MSI không thể thay thế bằng lệnh tạo DEB trên Linux. Hãy dùng `--type app-image` để kiểm tra ứng dụng trước khi tạo installer.

`jpackage` cũng hỗ trợ các tùy chọn bổ sung như biểu tượng, tên nhà cung cấp, thư mục cài đặt, shortcut và menu ứng dụng. Chỉ thêm các tùy chọn theo yêu cầu phân phối của sản phẩm; các tùy chọn riêng cho Windows, macOS hoặc Linux không nhất thiết dùng được trên nền tảng khác.

## 8. Ký JAR bằng `keytool` và `jarsigner`

Ký số giúp người nhận kiểm tra JAR có bị thay đổi sau khi ký hay không và xác định chứng thư được dùng để ký. Việc ký không tự động chứng minh nhà phát hành đáng tin cậy; độ tin cậy còn phụ thuộc nguồn chứng thư và chính sách xác minh của môi trường nhận.

### 8.1. Tạo keystore

Ví dụ tạo cặp khóa và chứng thư trong keystore PKCS12:

~~~powershell
keytool -genkeypair -alias release -keyalg RSA -keysize 3072 -validity 3650 -storetype PKCS12 -keystore release.p12
~~~

`keytool` sẽ yêu cầu nhập mật khẩu keystore và thông tin chứng thư. Không đưa mật khẩu thật vào mã nguồn, lệnh được lưu trong lịch sử shell hoặc repository. Với môi trường phát hành, cần quản lý keystore và khóa riêng theo chính sách bảo mật của tổ chức.

### 8.2. Ký và xác minh JAR

Ký JAR bằng alias `release`:

~~~powershell
jarsigner -keystore release.p12 -storetype PKCS12 -signedjar dist/hello-signed.jar dist/hello.jar release
~~~

Xác minh chữ ký:

~~~powershell
jarsigner -verify -verbose -certs dist/hello-signed.jar
~~~

Nên ký sau khi đã hoàn tất mọi thay đổi đối với JAR. Nếu sửa nội dung archive sau khi ký, chữ ký tương ứng sẽ không còn hợp lệ. JAR đã ký cũng cần được kiểm tra trong quy trình phát hành thực tế.

`jarsigner` ký JAR; nó không thay thế cơ chế ký bộ cài đặt native do `jpackage` tạo ra. Chữ ký cho MSI, EXE, PKG hoặc ứng dụng macOS cần quy trình và chứng thư phù hợp với nền tảng đó.

## 9. Các quy trình đóng gói thường gặp

### Trường hợp A: Chia sẻ một ứng dụng Java nhỏ

1. Biên dịch bằng `javac`.
2. Đóng gói class và tài nguyên bằng `jar`.
3. Đặt `Main-Class` trong manifest.
4. Kiểm tra bằng `java -jar` trên môi trường sạch.
5. Phân phối JAR cùng hướng dẫn cài đặt Java và các thư viện phụ thuộc nếu có.

Đây là lựa chọn gọn khi người dùng đã có runtime Java tương thích.

### Trường hợp B: Phân phối ứng dụng kèm runtime riêng

1. Tổ chức ứng dụng thành module tường minh nếu cần runtime tùy chỉnh bằng `jlink`.
2. Dùng `jdeps` để xem các module JDK được tham chiếu.
3. Kiểm tra những phụ thuộc được nạp động và các dịch vụ mà phân tích tĩnh có thể bỏ sót.
4. Dùng `jlink` tạo runtime chứa các module cần thiết.
5. Dùng `jpackage` tạo app image hoặc bộ cài đặt.
6. Kiểm thử trên máy sạch cùng hệ điều hành và kiến trúc mục tiêu.

### Trường hợp C: Chuẩn bị bản phát hành có chữ ký

1. Hoàn thiện mã nguồn, tài nguyên và cấu hình.
2. Tạo JAR hoặc app image cuối cùng.
3. Ký JAR bằng `jarsigner` nếu sản phẩm phân phối JAR.
4. Ký installer theo cơ chế của hệ điều hành nếu sản phẩm phân phối installer.
5. Xác minh chữ ký và chạy thử đúng artifact sẽ phát hành.
6. Lưu trữ artifact, phiên bản, checksum và thông tin chứng thư theo quy trình phát hành.

## 10. Lỗi phổ biến và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách kiểm tra hoặc xử lý |
|---|---|---|
| `no main manifest attribute` khi chạy `java -jar` | Manifest thiếu `Main-Class` | Tạo lại JAR với `jar --main-class` hoặc manifest hợp lệ |
| `Could not find or load main class` | Sai tên package/lớp, thiếu class hoặc sai thư mục gốc trong JAR | Dùng `jar --list` kiểm tra đường dẫn lớp; đối chiếu tên lớp đầy đủ |
| `ClassNotFoundException` hoặc `NoClassDefFoundError` | Thiếu thư viện phụ thuộc lúc chạy | Bổ sung thư viện vào classpath/module path hoặc cấu hình đóng gói |
| `FindException` hoặc `Module not found` | Module path thiếu JAR/module hoặc tên module sai | Dùng `jar --describe-module` và kiểm tra `--module-path` |
| `jlink` không liên kết được module | Module ứng dụng không tường minh hoặc module path thiếu module | Đảm bảo có `module-info.class` và khai báo đúng module path |
| `jpackage` báo không tìm thấy JAR chính | `--main-jar` không nằm trong thư mục `--input` hoặc tên tệp sai | Kiểm tra chính xác tên tệp và cấu trúc thư mục input |
| App image chạy trên máy build nhưng lỗi ở máy khác | Thiếu tài nguyên, native library, module hoặc cấu hình môi trường | Kiểm thử trên máy sạch; kiểm tra phụ thuộc native và các đường dẫn tài nguyên |
| Chữ ký JAR không hợp lệ | JAR bị sửa sau khi ký hoặc dữ liệu chữ ký không khớp | Tạo artifact cuối cùng rồi ký lại; xác minh đúng tệp sẽ phát hành |

Khi xử lý lỗi, hãy xác định lỗi xuất hiện ở bước nào: biên dịch, tạo archive, nạp class, phân giải module, tạo runtime, tạo installer hay xác minh chữ ký. Mỗi bước có đầu vào và công cụ kiểm tra riêng; phân loại đúng giúp tránh sửa nhầm manifest khi vấn đề thực tế là thư viện phụ thuộc hoặc module path.

## 11. Checklist trước khi phân phối

- [ ] Chọn đúng dạng đầu ra: JAR, runtime image hay installer.
- [ ] Đã kiểm tra JDK và phiên bản Java mục tiêu.
- [ ] JAR chứa đủ class, tài nguyên và manifest cần thiết.
- [ ] Các thư viện phụ thuộc được phân phối và nạp đúng cách.
- [ ] Nếu dùng module, tên module, module path và module descriptor nhất quán.
- [ ] Nếu dùng `jlink`, runtime chứa đủ module và đã kiểm tra các phụ thuộc động.
- [ ] Nếu dùng `jpackage`, loại gói phù hợp nền tảng và đã thử trên môi trường sạch.
- [ ] Nếu ký số, artifact đã hoàn tất trước khi ký và chữ ký đã được xác minh.
- [ ] Artifact phát hành được kiểm thử đúng phiên bản, đúng nền tảng và đúng cách người dùng sẽ khởi chạy.

Đóng gói tốt giúp ứng dụng dễ cài đặt, chạy nhất quán và thuận tiện bảo trì. Hãy chọn công cụ theo cách người dùng sẽ nhận và chạy ứng dụng: `jar` cho archive Java, `jlink` cho runtime tùy chỉnh, `jpackage` cho app image hoặc installer, còn `keytool` và `jarsigner` hỗ trợ quản lý chứng thư và xác minh tính toàn vẹn của JAR.
