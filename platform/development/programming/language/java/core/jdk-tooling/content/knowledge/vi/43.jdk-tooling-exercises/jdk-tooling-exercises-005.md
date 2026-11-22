# Tạo runtime bằng jlink

jlink là công cụ trong JDK dùng để ghép các Java module và dependency của chúng thành một **runtime image tùy chỉnh**. Image này chứa JVM cùng các module cần cho ứng dụng, giúp triển khai chương trình Java mà người dùng không phải cài một JDK đầy đủ trên máy.

Quy trình thường gồm: chuẩn bị ứng dụng theo Java Platform Module System (JPMS), đóng gói thành modular JAR, phân tích dependency bằng jdeps, tạo runtime image bằng jlink, chạy thử image độc lập và dùng jpackage nếu cần tạo app bundle hoặc installer.

Bài thực hành dùng Java 17+ và một ứng dụng modular nhỏ có sử dụng module java.logging. Các lệnh đã được kiểm tra trên JDK 24.0.2; cú pháp chính cũng áp dụng cho JDK 17 và 21.

## 1. jlink tạo ra những gì?

Một JDK đầy đủ có compiler, debugger, tài liệu, công cụ phân tích và nhiều module không cần thiết khi chỉ chạy ứng dụng. Runtime image do jlink tạo ra chỉ giữ các module được chọn cùng dependency bắc cầu của chúng.

| Thành phần | JDK đầy đủ | Runtime image tùy chỉnh |
|---|---|---|
| JVM và lệnh java | Có | Có |
| JDK modules | Có nhiều module | Chỉ các module đã liên kết |
| Compiler javac | Có | Thường không có |
| Công cụ javadoc, jdeps, jlink | Có | Không phải mục tiêu của runtime image |
| Module của ứng dụng | Tùy cách đóng gói | Có thể được liên kết trực tiếp |
| Launcher riêng của ứng dụng | Không tự tạo | Có thể tạo bằng --launcher |

Runtime image không phải một JDK nhỏ để tiếp tục biên dịch source. Nó là môi trường chạy được thiết kế cho ứng dụng cụ thể.

### 1.1. Vì sao cần runtime tùy chỉnh?

- Giảm dung lượng triển khai so với việc gửi cả JDK.
- Kiểm soát module nào có mặt trong runtime.
- Đóng gói ứng dụng cùng Java runtime đã kiểm thử.
- Tạo launcher riêng để người dùng không cần tự gõ lệnh java -m.
- Giảm khác biệt do máy người dùng cài Java version hoặc vendor khác nhau.

Kích thước image thực tế phụ thuộc vào module, locale data, native library và các tùy chọn tối ưu. Không có một tỷ lệ giảm dung lượng cố định cho mọi ứng dụng.

## 2. Điều kiện trước khi dùng jlink

jlink hoạt động trên module graph. Module path có thể chứa modular JAR, JMOD hoặc exploded module directory. Ứng dụng cần có module descriptor hợp lệ và dependency phải có thể được phân giải thành các module mà linker hỗ trợ.

Cần chuẩn bị:

1. JDK có các công cụ javac, jar, jdeps, jlink và tùy chọn jpackage.
2. Ứng dụng đã biên dịch và có module-info.class.
3. Các module dependency cần thiết trên module path.
4. Tên module và main class chính xác.
5. Môi trường build có OS và CPU architecture phù hợp với runtime sẽ phân phối.

Kiểm tra các công cụ cùng thuộc JDK dự định sử dụng:

~~~sh
java -version
javac -version
jar --version
jdeps --version
jlink --version
jpackage --version
~~~

Trên Windows PowerShell, có thể kiểm tra đường dẫn được chọn:

~~~powershell
Get-Command java, javac, jar, jdeps, jlink, jpackage
$env:JAVA_HOME
~~~

Trên Linux/macOS:

~~~sh
command -v java javac jar jdeps jlink jpackage
echo "$JAVA_HOME"
~~~

Nếu java và jlink đến từ hai JDK khác nhau, linker có thể sử dụng bộ JDK modules không khớp với runtime mà bạn đang kiểm tra. Hãy đặt JAVA_HOME và PATH trỏ tới cùng một JDK.

## 3. Tạo một ứng dụng modular để thực hành

Tạo cấu trúc project:

~~~text
jlink-demo/
├── src/
│   ├── module-info.java
│   └── com/
│       └── example/
│           └── app/
│               └── Main.java
└── build/
~~~

Ứng dụng dùng Java Logging để minh họa một dependency ngoài java.base.

### 3.1. Khai báo module-info.java

Tạo file src/module-info.java:

~~~java
module com.example.app {
    requires java.logging;
}
~~~

Giải thích:

- com.example.app là tên module.
- requires java.logging; khai báo ứng dụng đọc module java.logging.
- java.base được mọi module Java thông thường đọc ngầm; không cần viết requires java.base;.

Tên module không bắt buộc phải trùng với tên JAR. Tuy nhiên, nên đặt tên theo quy ước reverse-domain để tránh xung đột.

### 3.2. Viết main class

Tạo file src/com/example/app/Main.java:

~~~java
package com.example.app;

import java.util.logging.Logger;

public class Main {
    private static final Logger LOG =
        Logger.getLogger(Main.class.getName());

    public static void main(String[] args) {
        String target = args.length == 0
            ? "Java"
            : String.join(" ", args);

        LOG.info("Hello, " + target + "!");
    }
}
~~~

Chương trình nhận đối số dòng lệnh. Nếu chạy với đối số jlink, thông điệp log sẽ chứa Hello, jlink!.

### 3.3. Biên dịch module

Trên Linux/macOS hoặc Git Bash:

~~~sh
mkdir -p build/mods build/mlib

javac --release 17 \
  -d build/mods/com.example.app \
  src/module-info.java \
  src/com/example/app/Main.java
~~~

Trên Windows PowerShell, tạo thư mục và biên dịch bằng:

~~~powershell
New-Item -ItemType Directory -Force build/mods, build/mlib | Out-Null
javac --release 17 -d build/mods/com.example.app src/module-info.java src/com/example/app/Main.java
~~~

Sau khi biên dịch, thư mục build/mods/com.example.app chứa module-info.class và com/example/app/Main.class.

Có thể chạy trực tiếp exploded module để kiểm tra trước khi đóng JAR:

~~~sh
java --module-path build/mods \
  --module com.example.app/com.example.app.Main
~~~

Kết quả có dòng log chứa:

~~~text
INFO: Hello, Java!
~~~

Phần đầu log có timestamp và tên class; dòng INFO là thông điệp ổn định.

## 4. Đóng gói thành modular JAR

Tạo JAR trong thư mục module library:

~~~sh
jar --create \
  --file build/mlib/com.example.app.jar \
  --main-class com.example.app.Main \
  -C build/mods/com.example.app .
~~~

Lệnh này:

- Tạo file build/mlib/com.example.app.jar.
- Đưa module-info.class và các class của ứng dụng vào JAR.
- Khai báo main class trong metadata của modular JAR.

Xem descriptor:

~~~sh
jar --describe-module --file build/mlib/com.example.app.jar
~~~

Kết quả sẽ có thông tin tương tự:

~~~text
com.example.app
requires java.base mandated
requires java.logging
contains com.example.app
main-class com.example.app.Main
~~~

Kiểm tra này xác nhận JAR có module descriptor và module name đúng. Nếu lệnh chỉ hiển thị automatic module name, hãy kiểm tra lại quá trình đóng gói và vị trí module-info.class.

Có thể chạy JAR như một module:

~~~sh
java --module-path build/mlib \
  --module com.example.app/com.example.app.Main
~~~

## 5. Phân tích module dependency bằng jdeps

jdeps phân tích dependency ở mức package/class và có thể in danh sách JDK module cần thiết cho linker. Đây là bước quan trọng để hiểu ứng dụng đang sử dụng những module nào.

Chạy:

~~~sh
jdeps --print-module-deps \
  --module-path build/mlib \
  --module com.example.app
~~~

Với ứng dụng mẫu, output chính xác là:

~~~text
java.base,java.logging
~~~

--print-module-deps in danh sách module phân tách bằng dấu phẩy; output có thể dùng làm đầu vào cho --add-modules của jlink.

Có thể xem dependency chi tiết hơn:

~~~sh
jdeps --list-deps \
  --module-path build/mlib \
  --module com.example.app
~~~

Kiểm tra dependency bị thiếu:

~~~sh
jdeps --missing-deps \
  --module-path build/mlib \
  --module com.example.app
~~~

Nếu ứng dụng dùng multi-release JAR, chỉ định release cần phân tích bằng --multi-release khi phù hợp.

### 5.1. jdeps không nhìn thấy mọi dependency động

jdeps chủ yếu phân tích bytecode và module descriptor. Nó có thể không phát hiện đầy đủ class được nạp bằng reflection, tên class lấy từ file cấu hình, plugin tải động, service provider không khai báo rõ hoặc native library được nạp qua JNI.

Vì vậy:

- Đọc kết quả jdeps cùng với module descriptor và cấu hình ứng dụng.
- Bổ sung module cần thiết bằng --add-modules khi dependency không thể suy ra từ bytecode.
- Kiểm tra service provider bằng --bind-services khi ứng dụng dùng ServiceLoader.
- Chạy test trên chính runtime image sau khi link.

Không dùng --ignore-missing-deps để che lỗi trong build release. Nếu có dependency thiếu, xác định nguyên nhân và sửa module path hoặc cấu hình trước khi tạo image.

## 6. Tạo runtime image bằng jlink

Lệnh cơ bản:

~~~sh
jlink \
  --module-path build/mlib \
  --add-modules com.example.app \
  --launcher demo=com.example.app/com.example.app.Main \
  --strip-debug \
  --no-header-files \
  --no-man-pages \
  --output build/runtime
~~~

Giải thích các tùy chọn:

| Tùy chọn | Tác dụng |
|---|---|
| --module-path build/mlib | Nơi linker tìm module ứng dụng |
| --add-modules com.example.app | Chọn module gốc để liên kết |
| --launcher demo=... | Tạo launcher có tên demo |
| --strip-debug | Loại bỏ debug information khỏi runtime image |
| --no-header-files | Không đưa header file vào image |
| --no-man-pages | Không đưa man page vào image |
| --output build/runtime | Thư mục runtime image đầu ra |

Khi module path chỉ chứa module ứng dụng và chưa có java.base, jlink bổ sung JDK module directory jmods của JDK đang chạy. Nếu muốn khai báo rõ cả hai đường dẫn, phải dùng đúng dấu phân cách theo hệ điều hành: dấu : trên Linux/macOS và dấu ; trên Windows.

--add-modules com.example.app khiến linker đưa module ứng dụng cùng các dependency được khai báo trong module graph vào image. Không cần tự liệt kê từng dependency bắc cầu trong trường hợp thông thường.

### 6.1. Thêm module ngoài module graph

Nếu ứng dụng nạp module bằng reflection hoặc cấu hình động, có thể cần thêm module rõ ràng:

~~~sh
jlink \
  --module-path build/mlib \
  --add-modules com.example.app,java.sql,jdk.crypto.ec \
  --output build/runtime
~~~

Đây chỉ là ví dụ về cú pháp. Chỉ thêm module thực sự cần thiết; việc thêm nhiều module không dùng sẽ làm image lớn hơn và tăng bề mặt cần cập nhật.

### 6.2. Liên kết service provider

Với ứng dụng sử dụng ServiceLoader, module descriptor của ứng dụng có thể khai báo service. Ví dụ dưới đây giả định interface CodecProvider thuộc package com.example.spi và package này được export bởi module ứng dụng:

~~~java
module com.example.app {
    exports com.example.spi;
    uses com.example.spi.CodecProvider;
}
~~~

Module triển khai provider phải đọc module chứa interface và khai báo provider:

~~~java
module com.example.codec.json {
    requires com.example.app;
    provides com.example.spi.CodecProvider
        with com.example.codec.json.JsonCodecProvider;
}
~~~

Khi cần đưa provider module cùng dependency vào runtime image, dùng:

~~~sh
jlink \
  --module-path build/mlib \
  --add-modules com.example.app \
  --bind-services \
  --output build/runtime
~~~

--bind-services yêu cầu linker liên kết các module cung cấp service phù hợp và dependency của chúng. Vẫn cần kiểm tra module có khai báo uses và provides đúng hay không.

### 6.3. Giữ locale data cần thiết

Nếu ứng dụng cần locale ngoài tập mặc định, có thể thêm jdk.localedata và giới hạn locale:

~~~sh
jlink \
  --module-path build/mlib \
  --add-modules com.example.app,jdk.localedata \
  --include-locales=vi,en \
  --output build/runtime
~~~

--include-locales yêu cầu module jdk.localedata. Kiểm tra format locale và nhu cầu thực tế của ứng dụng trước khi loại bỏ locale data.

### 6.4. Tùy chọn tối ưu dung lượng

Các tùy chọn --strip-debug, --no-header-files và --no-man-pages thường phù hợp với runtime production. Nén resource bằng plugin compress có thể giảm kích thước nhưng làm tăng chi phí giải nén và cú pháp plugin thay đổi giữa các JDK release.

Xem plugin có sẵn trên JDK đang sử dụng:

~~~sh
jlink --list-plugins
~~~

Chỉ thêm tùy chọn nén sau khi kiểm tra tài liệu của đúng JDK và đo kích thước/thời gian khởi động trên ứng dụng thực tế.

## 7. Kiểm tra runtime image vừa tạo

Liệt kê module bên trong image:

~~~sh
build/runtime/bin/java --list-modules
~~~

Với ứng dụng mẫu được link bằng JDK 24.0.2, danh sách có các module:

~~~text
com.example.app
java.base@24.0.2
java.logging@24.0.2
~~~

Trên máy khác, version suffix của module JDK phản ánh JDK đã dùng để link.

Kiểm tra runtime:

~~~sh
build/runtime/bin/java --version
~~~

Chạy module bằng Java trong image:

~~~sh
build/runtime/bin/java \
  --module com.example.app/com.example.app.Main \
  from-runtime
~~~

Kiểm tra launcher do jlink tạo:

~~~sh
./build/runtime/bin/demo launcher-test
~~~

Trên Windows PowerShell:

~~~powershell
.\build\runtime\bin\demo.bat launcher-test
~~~

Kết quả log phải chứa:

~~~text
INFO: Hello, launcher-test!
~~~

Luôn chạy java bên trong image. Nếu vô tình chạy Java từ PATH của máy developer, bài kiểm tra có thể thành công dù runtime image thiếu module.

## 8. Đóng gói ứng dụng bằng jpackage

jlink tạo runtime image. jpackage dùng ứng dụng và runtime image để tạo application image hoặc installer theo hệ điều hành.

Tạo application image từ runtime vừa build:

~~~sh
jpackage \
  --type app-image \
  --name JlinkDemo \
  --module-path build/mlib \
  --module com.example.app/com.example.app.Main \
  --runtime-image build/runtime \
  --dest build/package
~~~

--runtime-image yêu cầu jpackage dùng image đã tạo sẵn. Nếu bỏ tùy chọn này, jpackage tự gọi jlink để tạo runtime theo module và các tùy chọn được cung cấp.

Application image có launcher và thư mục runtime bên trong. Cấu trúc cụ thể tùy hệ điều hành:

- Windows: có file launcher .exe và thư mục chứa application/runtime.
- Linux: có launcher trong thư mục bin và runtime trong thư mục ứng dụng.
- macOS: có app bundle .app, launcher trong Contents/MacOS và runtime trong bundle.

Chạy thử launcher trong application image trước khi tạo installer. Ví dụ Windows:

~~~powershell
.\build\package\JlinkDemo\JlinkDemo.exe packaged
~~~

Trên Linux, launcher thường nằm dưới build/package/JlinkDemo/bin/; trên macOS, launcher nằm trong build/package/JlinkDemo.app/Contents/MacOS/.

### 8.1. Tạo installer theo hệ điều hành

Các loại package thường dùng:

| Hệ điều hành | Loại package |
|---|---|
| Windows | exe, msi |
| macOS | dmg, pkg |
| Linux | deb, rpm |

Ví dụ tạo installer Windows:

~~~powershell
jpackage --type exe --name JlinkDemo --module-path build/mlib --module com.example.app/com.example.app.Main --runtime-image build/runtime --dest build/installer
~~~

Để tạo installer macOS hoặc Linux, chạy jpackage trên máy/runner của hệ điều hành đích và chọn loại package tương ứng. jpackage không hỗ trợ cross-platform packaging; muốn phát hành nhiều OS cần build trên từng nền tảng.

Trên Windows, tạo package exe hoặc msi có thể cần WiX Toolset. Trên macOS, ký app hoặc tùy chỉnh một số tài nguyên cần Xcode Command Line Tools và quy trình signing/notarization phù hợp.

### 8.2. Đóng gói ứng dụng chưa modular bằng jpackage

Ứng dụng legacy dùng classpath JAR có thể được đóng gói bằng jpackage với --input, --main-jar và --main-class:

~~~sh
jpackage \
  --type app-image \
  --name LegacyApp \
  --input build/dist \
  --main-jar legacy-app.jar \
  --main-class com.example.Main \
  --dest build/package
~~~

Thư mục build/dist phải chứa JAR và các file cần thiết cho ứng dụng. Với ứng dụng classpath không modular, jpackage tạo runtime dựa trên tập module mà launcher Java thường cung cấp cho ứng dụng unnamed module; có thể bổ sung module hoặc tùy chọn --bind-services khi cần.

Nếu muốn tự quản lý runtime bằng jlink, hãy chuyển ứng dụng và các dependency cần thiết thành explicit modules. Một JAR classpath thông thường không tự trở thành modular JAR chỉ vì được đặt trên module path.

## 9. Các giới hạn cần hiểu trước khi phát hành

### 9.1. Dependency không có module descriptor

Một modular JAR có module-info.class ở root hoặc descriptor hợp lệ trong multi-release JAR. JAR classpath cũ không có descriptor không cung cấp module graph tường minh cho jlink.

Nếu dependency chỉ có dạng JAR legacy:

- Ưu tiên bản thư viện có explicit module descriptor.
- Có thể dùng jdeps --generate-module-info để tạo descriptor gợi ý, sau đó review và kiểm thử kỹ.
- Nếu vẫn giữ classpath application, cân nhắc đóng gói bằng jpackage ở chế độ non-modular.
- Không tự đặt tên automatic module rồi cho rằng linker có thể liên kết nó như explicit module.

### 9.2. Reflection và class loading động

Các framework có thể nạp class theo tên chuỗi, quét package, đọc file cấu hình hoặc tải plugin lúc runtime. Static dependency analysis không thể luôn suy ra các class này.

Hãy kiểm thử các đường chạy thật: khởi động ứng dụng, nạp cấu hình, tạo kết nối, chạy plugin, serialize/deserialize, mở file và gọi các tính năng tùy chọn. Nếu thiếu module, bổ sung bằng --add-modules hoặc điều chỉnh module descriptor.

### 9.3. JNI và native library

Thư viện JNI/JNA cần binary đúng hệ điều hành và kiến trúc. Một runtime image Windows x64 không thể dùng nguyên trạng trên Linux ARM64. Kiểm tra native library, DLL/shared library, đường dẫn tìm kiếm và dependency động trên máy đích.

### 9.4. Runtime image phải được cập nhật

jlink không tự cập nhật image sau khi JDK có bản vá bảo mật. Khi nâng JDK, hãy tạo lại runtime image, chạy regression test và phát hành lại ứng dụng. Ghi lại JDK vendor/version, OS/architecture, module list và checksum artifact để có thể truy vết bản phát hành.

## 10. Quy trình build có thể lặp lại

Một pipeline triển khai nên thực hiện các bước theo thứ tự:

1. Cố định JDK vendor và version cho job build.
2. Biên dịch ứng dụng bằng target release đã chọn.
3. Tạo modular JAR và kiểm tra module descriptor.
4. Chạy jdeps --print-module-deps và jdeps --missing-deps.
5. Tạo runtime image với jlink và các module đã review.
6. Kiểm tra java --list-modules bên trong image.
7. Chạy launcher và test các tính năng cần reflection, service loading, locale hoặc JNI.
8. Tạo application image bằng jpackage --type app-image.
9. Kiểm tra app image trên máy sạch của hệ điều hành đích.
10. Tạo installer, ký và notarize nếu quy trình phân phối yêu cầu.
11. Lưu JDK version, module list, checksum và build provenance cùng artifact.

Đừng dùng ALL-MODULE-PATH hoặc thêm tất cả JDK modules chỉ để làm lỗi biến mất. Hãy xác định module thực sự cần thiết và thêm có chủ đích.

## 11. Troubleshooting

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Error: module not found | Thiếu JAR/module trên module path hoặc sai module name | Dùng jar --describe-module và kiểm tra --module-path |
| jlink không tìm thấy java.base | JDK modules không được linker tìm thấy | Kiểm tra JAVA_HOME, JDK đang chạy và thư mục jmods |
| Thiếu module sau khi link | Dependency được nạp động hoặc chưa khai báo | Kiểm tra jdeps, module descriptor và thêm module cần thiết |
| JAR chạy bằng java -jar nhưng linker lỗi | JAR/dependency chưa tạo thành explicit modules | Modularize dependency hoặc dùng jpackage với classpath mode |
| Service provider không xuất hiện | Chưa khai báo service hoặc chưa bind provider | Kiểm tra uses/provides và --bind-services |
| Không có locale mong muốn | Thiếu jdk.localedata hoặc locale data | Thêm module và dùng --include-locales |
| JNI báo không nạp được library | Sai OS/architecture hoặc thiếu native dependency | Build đúng platform và kiểm tra native library path |
| Launcher chạy bằng Java hệ thống nhưng image lỗi | Test đã gọi nhầm java từ PATH | Chạy executable/launcher nằm bên trong runtime image |
| Installer không chạy trên OS khác | Package là định dạng native theo platform | Tạo package trên từng OS đích |
| Runtime image vẫn quá lớn | Thêm quá nhiều module hoặc locale data | Xem --list-modules, loại module không cần và đo lại |

## 12. Checklist trước khi phân phối

- [ ] Đã dùng JDK có jlink và jpackage.
- [ ] java, javac, jdeps và jlink đến từ cùng JDK.
- [ ] Ứng dụng có module descriptor phù hợp.
- [ ] Đã kiểm tra module name bằng jar --describe-module.
- [ ] Đã xem dependency bằng jdeps --print-module-deps.
- [ ] Đã xử lý dependency thiếu bằng jdeps --missing-deps.
- [ ] Đã tạo runtime image với module gốc đúng.
- [ ] Đã kiểm tra module list bên trong image.
- [ ] Đã chạy thử launcher do jlink tạo.
- [ ] Đã kiểm tra reflection, ServiceLoader, locale và native library nếu ứng dụng dùng chúng.
- [ ] Đã tạo và thử application image bằng jpackage.
- [ ] Đã build package riêng cho từng OS/architecture đích.
- [ ] Đã có quy trình rebuild runtime khi nâng JDK hoặc cập nhật bảo mật.

## Tài liệu tham khảo

- [Oracle JDK 21 — The jlink Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jlink.html)
- [Oracle JDK 26 — The jdeps Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html)
- [Oracle JDK 21 — The jar Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html)
- [Oracle JDK 21 — The jpackage Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jpackage.html)
- [Oracle JDK 21 — Packaging Overview and Runtime Requirements](https://docs.oracle.com/en/java/javase/21/jpackage/packaging-overview.html)
- [Oracle Java SE 21 — ModuleFinder API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/module/ModuleFinder.html)