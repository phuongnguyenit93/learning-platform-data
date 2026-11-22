# Quan hệ giữa JAR, runtime image và gói cài đặt

Khi phân phối một ứng dụng Java, có ba loại artifact thường được nhắc đến nhưng giải quyết ba nhu cầu khác nhau:

- **JAR** đóng gói class, resource và có thể cả dependency của ứng dụng thành một artifact Java.
- **Runtime image** là một môi trường chạy Java đã được tạo sẵn, có các module runtime cần thiết để chạy ứng dụng.
- **Gói cài đặt (installer/package)** đóng gói ứng dụng để cài đặt theo cách quen thuộc của hệ điều hành, có thể kèm runtime image, launcher và thông tin tích hợp với desktop hoặc hệ thống.

Trong JDK 17, các công cụ chính là `jar` để tạo và kiểm tra JAR, `jlink` để tạo runtime image tùy chỉnh, và `jpackage` để tạo application image hoặc gói cài đặt nền tảng. Chúng có thể được kết hợp thành một quy trình phân phối:

~~~text
Java source + resources + dependencies
                 |
                 v
             javac / build
                 |
                 v
          JAR application
                 |
                 +--------------------------+
                 |                          |
                 v                          v
       Chạy trên Java có sẵn       jlink tạo runtime image
                                            |
                                            v
                                  jpackage tạo app image
                                            |
                                            v
                                   Native installer
~~~

JAR là artifact ứng dụng; runtime image cung cấp môi trường thực thi; installer cung cấp trải nghiệm cài đặt. Một ứng dụng có thể chỉ phát hành JAR, phát hành app image có runtime riêng, hoặc phát hành installer chứa app image. Chọn cách nào phụ thuộc đối tượng sử dụng, yêu cầu triển khai, nền tảng đích và cách quản lý phiên bản.

## 1. JAR: đóng gói ứng dụng Java

JAR (Java Archive) là một định dạng archive dựa trên ZIP, dùng để chứa class file, resource, metadata và có thể chứa chữ ký. Một JAR thông thường có thể gồm:

~~~text
application.jar
|
+-- META-INF/
|   +-- MANIFEST.MF
|   +-- signatures (nếu được ký)
|
+-- com/
|   +-- example/
|       +-- Main.class
|       +-- service/
|       +-- model/
|
+-- config/
+-- images/
+-- messages/
~~~

JAR giúp phân phối nhiều file dưới một artifact, giữ cấu trúc package và resource. Nó không mặc nhiên chứa JVM hoặc toàn bộ dependency bên ngoài.

### 1.1. Tạo JAR bằng công cụ jar

Giả sử source được biên dịch vào thư mục `out`:

~~~bash
javac --release 17 -d out src/com/example/Main.java
~~~

Tạo JAR:

~~~bash
jar --create --file application.jar -C out .
~~~

Tùy chọn:

- `--create` tạo archive mới.
- `--file application.jar` chỉ định tên file đầu ra.
- `-C out .` chuyển vào thư mục `out` rồi thêm nội dung thư mục đó vào archive.

Liệt kê nội dung:

~~~bash
jar --list --file application.jar
~~~

Với JAR modular, xem descriptor:

~~~bash
jar --describe-module --file application.jar
~~~

JAR không có module descriptor tường minh có thể được mô tả như automatic module khi công cụ phân tích nó trên module path.

### 1.2. Executable JAR và Main-Class

Một JAR có thể được khởi chạy bằng `java -jar` nếu manifest khai báo lớp có phương thức `main` phù hợp.

Tạo JAR kèm main class:

~~~bash
jar --create --file application.jar --main-class com.example.Main -C out .
~~~

Manifest sẽ có thuộc tính:

~~~text
Main-Class: com.example.Main
~~~

Chạy:

~~~bash
java -jar application.jar
~~~

`Main-Class` chỉ xác định điểm bắt đầu của ứng dụng. Nó không tự đưa mọi dependency bên ngoài vào JAR. Nếu ứng dụng dùng thư viện khác, runtime vẫn phải tìm thấy chúng qua classpath hoặc cơ chế đóng gói khác.

### 1.3. JAR không đồng nghĩa với fat JAR

Có hai kiểu phân phối thường gặp:

| Kiểu | Nội dung | Dependency |
| --- | --- | --- |
| JAR ứng dụng thông thường | Class và resource của ứng dụng | Cần cung cấp riêng qua classpath/module path |
| Fat JAR / uber JAR | Class/resource ứng dụng và nội dung dependency được đóng gói chung | Thường đã gom dependency vào một artifact |

Fat JAR thường do build tool hoặc plugin đóng gói tạo ra; lệnh `jar` cơ bản không tự giải nén và hợp nhất dependency. Khi gom nhiều JAR, cần xử lý đúng resource trùng tên, service provider configuration, license, chữ ký cũ và metadata. Không nên chỉ giải nén mọi dependency rồi chép đè file cùng đường dẫn.

Fat JAR vẫn không chứa JVM. Người dùng cần có runtime tương thích, trừ khi artifact được phân phối cùng runtime image theo một cách khác.

### 1.4. JAR với classpath

Ứng dụng không modular thường chạy trên classpath:

~~~bash
java -cp "application.jar:lib/*" com.example.Main
~~~

Trên Windows, dấu phân cách classpath là dấu chấm phẩy:

~~~powershell
java -cp "application.jar;lib/*" com.example.Main
~~~

Có thể khai báo `Class-Path` trong manifest để tham chiếu dependency JAR tương đối với JAR ứng dụng:

~~~text
Manifest-Version: 1.0
Main-Class: com.example.Main
Class-Path: lib/library-a.jar lib/library-b.jar
~~~

Đường dẫn trong manifest được diễn giải theo quy tắc URL tương đối với vị trí JAR chứa manifest. Cần giữ đúng cấu trúc thư mục khi phân phối. Với ứng dụng lớn, build tool thường quản lý dependency và launcher classpath rõ ràng hơn việc tự viết manifest.

### 1.5. Modular JAR

Từ Java 9, một JAR có thể là module tường minh nếu chứa `module-info.class`. Ví dụ:

~~~java
module com.example.app {
    requires java.net.http;
    exports com.example.api;
}
~~~

Module descriptor khai báo dependency và ranh giới package. Có thể xem descriptor:

~~~bash
jar --describe-module --file application.jar
~~~

Chạy module trên module path:

~~~bash
java --module-path mods -m com.example.app/com.example.Main
~~~

Một JAR không có `module-info.class` vẫn có thể chạy trên classpath. Khi đặt lên module path, nó có thể được xem như automatic module theo quy tắc đặt tên và nội dung archive. Automatic module hữu ích cho chuyển tiếp, nhưng không có module descriptor tường minh và không phù hợp làm nền tảng cho mọi quy trình tạo runtime image tùy chỉnh.

## 2. JAR không cung cấp runtime Java

Khi người dùng chạy:

~~~bash
java -jar application.jar
~~~

lệnh `java` được lấy từ một JDK hoặc Java runtime đã cài trên máy. JAR không mang theo executable JVM.

Điều này tạo ra một số yêu cầu vận hành:

- Máy đích cần có Java runtime tương thích.
- Phiên bản runtime phải hỗ trợ class file version mà ứng dụng và dependency sử dụng.
- Runtime phải có các module/API mà ứng dụng cần.
- Người dùng hoặc quản trị viên phải cài đặt, cập nhật và chọn runtime phù hợp.
- Hai máy có thể chạy cùng JAR nhưng dùng runtime khác vendor, version, cấu hình hoặc kiến trúc.

Với ứng dụng Java 17, biên dịch bằng `javac --release 17` giúp giới hạn API Java SE và class file theo Java 17. Tuy nhiên, điều đó không tự đóng gói Java 17 runtime vào JAR.

### 2.1. Khi nào chỉ phát hành JAR?

JAR phù hợp khi:

- Người dùng là developer hoặc quản trị viên đã quản lý Java runtime.
- Ứng dụng chạy trong môi trường server/container đã có Java.
- Một tổ chức muốn quản lý runtime tập trung.
- Ứng dụng là thư viện được tích hợp vào hệ thống khác.
- Muốn giữ artifact ứng dụng độc lập với cách cài runtime trên từng máy.

Nếu đối tượng sử dụng là người dùng desktop không quen cài Java, chỉ phát hành JAR có thể tạo thêm bước thiết lập và hỗ trợ.

## 3. Runtime image là gì?

Runtime image là thư mục chứa môi trường chạy Java đã được lắp ghép từ các module runtime và thành phần cần thiết. Nó thường chứa:

~~~text
runtime/
|
+-- bin/
|   +-- java
|   +-- keytool (nếu được giữ lại)
|
+-- conf/
+-- legal/
+-- lib/
    +-- modules
    +-- security/
    +-- ...
~~~

Cấu trúc thực tế phụ thuộc JDK, hệ điều hành và các module được chọn. Runtime image được tạo bằng `jlink` có thể nhỏ hơn một JDK đầy đủ vì không cần các công cụ phát triển như compiler và debugger.

Một runtime image không phải JAR ứng dụng. Nó cung cấp JVM và các module runtime để chạy ứng dụng. Thông thường, ứng dụng và dependency JAR vẫn được phân phối bên cạnh runtime image hoặc được đặt trong app image do `jpackage` tạo.

### 3.1. JDK, runtime image và JRE

Các khái niệm này cần phân biệt:

| Artifact | Mục đích |
| --- | --- |
| JDK | Bộ công cụ phát triển, gồm compiler, launcher, debugger, archive tools và runtime |
| Runtime image | Môi trường chạy Java được tạo từ các module runtime |
| Custom runtime image | Runtime image được chọn module phù hợp với ứng dụng, thường tạo bằng `jlink` |
| JRE | Cách gọi quen thuộc cho môi trường chạy Java; trong quy trình hiện đại có thể tạo runtime image tùy chỉnh thay vì tải một JRE độc lập theo kiểu cũ |

Không cần phát hành toàn bộ JDK cho người dùng cuối chỉ để chạy ứng dụng. Một runtime image phù hợp thường đủ cho mục đích đó.

## 4. jlink: tạo runtime image tùy chỉnh

`jlink` là công cụ trong JDK để liên kết các module và tạo runtime image. Nó chỉ làm việc với module; vì vậy ứng dụng và các module phụ thuộc cần có thể được phân giải trên module path.

Ví dụ module ứng dụng:

~~~java
module com.example.app {
    requires java.logging;
    requires java.net.http;
}
~~~

Sau khi biên dịch module và đặt JAR vào thư mục `mods`, tạo runtime image:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --output build/runtime
~~~

Trong ví dụ trên:

- `--module-path` chỉ vị trí các module JDK và module ứng dụng.
- `$JAVA_HOME/jmods` chứa các module của JDK đang dùng.
- `mods` chứa module ứng dụng và module phụ thuộc.
- `--add-modules com.example.app` xác định module gốc cần đưa vào runtime; các dependency được phân giải theo quan hệ `requires`.
- `--output build/runtime` là thư mục runtime image được tạo.

Trên Windows, dấu phân cách module path là dấu chấm phẩy. Ví dụ PowerShell:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods;mods" --add-modules com.example.app --output build\runtime
~~~

Tên biến và cú pháp đường dẫn phụ thuộc shell. Trong script build đa nền tảng, nên xây dựng module path theo hệ điều hành thay vì dùng một chuỗi cố định.

### 4.1. Chọn module gốc

`--add-modules` nhận một hoặc nhiều module gốc. `jlink` phân giải các module mà chúng yêu cầu theo quan hệ module. Không cần thêm thủ công mọi module bắc cầu nếu chúng được khai báo đúng trong descriptor.

Có thể xem module có trong runtime:

~~~bash
build/runtime/bin/java --list-modules
~~~

Trên Windows:

~~~powershell
build\runtime\bin\java.exe --list-modules
~~~

Nếu ứng dụng dùng reflection, service loading hoặc nạp class theo tên lúc runtime, có thể cần bổ sung module không được phát hiện qua dependency tĩnh. Hãy xác định yêu cầu runtime thực tế và kiểm tra bằng integration test.

### 4.2. Launcher tùy chỉnh

Có thể tạo launcher trong runtime image:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --launcher myapp=com.example.app/com.example.Main --output build/runtime
~~~

Sau khi tạo, có thể chạy:

~~~bash
build/runtime/bin/myapp
~~~

Launcher được cấu hình để gọi module và main class tương ứng. Đây là một cách tạo runtime có lối khởi chạy dễ dùng hơn cho người dùng cuối.

### 4.3. Service binding

Nếu ứng dụng dùng Java Service Provider mechanism, có thể cần module provider không nằm trong đồ thị dependency trực tiếp. Tùy cách ứng dụng và provider được khai báo, tùy chọn `--bind-services` yêu cầu `jlink` liên kết các module provider cho các service mà module gốc sử dụng:

~~~bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --bind-services --output build/runtime
~~~

Không nên bật hoặc bỏ tùy chọn này theo thói quen mà không hiểu service nào cần có mặt. Hãy kiểm tra `uses` và `provides` trong module descriptor, cấu hình ServiceLoader và test trên runtime image được tạo.

### 4.4. Các tùy chọn jlink hữu ích

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `--module-path` | Nơi tìm module JDK và module ứng dụng |
| `--add-modules` | Chọn module gốc để đưa vào image |
| `--bind-services` | Bổ sung module provider cho service được dùng |
| `--launcher` | Tạo launcher cho module/main class |
| `--output` | Thư mục runtime image đầu ra |
| `--limit-modules` | Giới hạn tập module có thể quan sát khi phân giải module |
| `--strip-debug` | Loại bỏ debug information |
| `--no-header-files` | Không đưa header native vào image |
| `--no-man-pages` | Không đưa man pages vào image |
| `--compress` | Chọn mức nén tài nguyên trong image nếu được hỗ trợ bởi bản JDK |
| `--save-opts` | Lưu tùy chọn jlink để tái sử dụng |

Có thể xem trợ giúp và plugin có sẵn trên đúng JDK 17 đang dùng:

~~~bash
jlink --help
jlink --list-plugins
~~~

Không nên tối ưu kích thước bằng cách loại bỏ module hoặc tài nguyên khi chưa xác nhận ứng dụng không cần chúng. Runtime image nhỏ hơn nhưng thiếu provider, charset, locale data hoặc module được nạp động có thể chỉ lỗi khi đi vào một nhánh chức năng cụ thể.

### 4.5. jlink cần module hóa

`jlink` tạo runtime image từ module. Một thư viện JAR thuần classpath không tự trở thành module tường minh chỉ vì được đặt vào thư mục module path.

Nếu ứng dụng còn dependency classpath:

- Các JAR đó vẫn được phân phối cùng ứng dụng.
- Runtime image cần chứa các module Java SE mà code và dependency yêu cầu.
- Launcher cần thiết lập classpath để JVM tìm thấy chúng.
- Với module hóa đầy đủ, khai báo descriptor và dependency module rõ ràng giúp `jlink` phân giải chính xác hơn.

Có thể dùng `jdeps` để phân tích dependency module của ứng dụng, nhưng kết quả tĩnh cần được đối chiếu với reflection, service loading và các dependency runtime khác.

## 5. Runtime image có phụ thuộc nền tảng không?

Có. Runtime image được tạo cho một nền tảng cụ thể, gồm hệ điều hành và kiến trúc CPU. Ví dụ, runtime image tạo trên Windows x64 không phải artifact dùng trực tiếp trên Linux ARM64.

Điều này quan trọng khi xây dựng pipeline phát hành:

- Tạo runtime image cho từng hệ điều hành/kiến trúc đích.
- Dùng JDK và module phù hợp với nền tảng đích.
- Kiểm thử trên đúng nền tảng mà người dùng sẽ chạy.
- Không dùng một runtime image duy nhất cho mọi hệ điều hành.

Có thể dùng CI matrix hoặc build agent theo từng nền tảng để tạo runtime image tương ứng. Nếu ứng dụng phụ thuộc native library/JNI, mỗi nền tảng còn cần binary native tương thích.

## 6. jpackage: tạo application image và installer

`jpackage` đóng gói ứng dụng Java thành một application image hoặc gói cài đặt theo nền tảng. Nó được thiết kế để giúp người dùng chạy ứng dụng mà không phải tự dựng classpath hoặc tự cài một Java runtime riêng.

Các đầu ra thường gặp:

- **Application image:** thư mục ứng dụng đã đóng gói, có launcher và có thể chứa runtime image.
- **Installer:** gói cài đặt theo hệ điều hành, có thể cài shortcut, thông tin ứng dụng, thư mục cài và metadata gỡ cài đặt.

`jpackage` có thể dùng runtime image đã tạo bằng `jlink` qua tùy chọn `--runtime-image`. Nếu không cung cấp runtime image, `jpackage` có thể tạo runtime phù hợp bằng cách gọi `jlink` với các tùy chọn được cấu hình.

### 6.1. Application image

Ví dụ đóng gói một ứng dụng classpath có JAR chính:

~~~bash
jpackage --type app-image --name ExampleApp --input input --main-jar application.jar --main-class com.example.Main --runtime-image build/runtime --dest dist
~~~

Trong đó:

- `--type app-image` yêu cầu tạo application image.
- `--name` đặt tên ứng dụng.
- `--input input` chỉ thư mục chứa JAR và các file dependency/resource cần đóng gói.
- `--main-jar` chỉ JAR chính trong input directory.
- `--main-class` chỉ lớp main.
- `--runtime-image` cung cấp runtime image đã tạo.
- `--dest dist` chỉ thư mục chứa kết quả.

Cấu trúc đầu ra có thể khác theo hệ điều hành, nhưng về ý nghĩa app image chứa launcher, nội dung ứng dụng và runtime được chỉ định. Người dùng có thể chạy launcher trong thư mục image mà không phải tự gõ classpath.

### 6.2. Installer cho hệ điều hành

Từ cùng cấu hình ứng dụng, có thể yêu cầu loại package tương ứng nền tảng:

| Nền tảng | Loại package thường dùng |
| --- | --- |
| Windows | `exe` hoặc `msi` |
| macOS | `dmg` hoặc `pkg` |
| Linux | `deb` hoặc `rpm` |
| Nhiều nền tảng | `app-image` (thư mục ứng dụng, không phải installer native) |

Ví dụ trên Windows:

~~~powershell
jpackage --type msi --name ExampleApp --input input --main-jar application.jar --main-class com.example.Main --runtime-image build\runtime --dest dist --app-version 1.0.0 --vendor ExampleOrg
~~~

Ví dụ trên Linux:

~~~bash
jpackage --type deb --name example-app --input input --main-jar application.jar --main-class com.example.Main --runtime-image build/runtime --dest dist --app-version 1.0.0 --vendor ExampleOrg
~~~

Ví dụ trên macOS:

~~~bash
jpackage --type dmg --name ExampleApp --input input --main-jar application.jar --main-class com.example.Main --runtime-image build/runtime --dest dist --app-version 1.0.0 --vendor ExampleOrg
~~~

Các ví dụ giả định thư mục input, JAR, main class và runtime image đã tồn tại, đồng thời máy build có toolchain cần thiết cho loại package đó.

### 6.3. Đóng gói ứng dụng modular

Với ứng dụng modular, có thể dùng tùy chọn `--module-path` và `--module` thay cho `--main-jar`/`--main-class`:

~~~bash
jpackage --type app-image --name ModularApp --module-path mods --module com.example.app/com.example.Main --dest dist
~~~

Cách cấu hình chính xác còn phụ thuộc dependency và runtime image. Khi đã có runtime image riêng, có thể cung cấp qua `--runtime-image`. Đọc `jpackage --help` trên JDK 17 để xác nhận các tùy chọn tương thích với chế độ đóng gói đang chọn.

### 6.4. Một số tùy chọn jpackage hữu ích

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `--type` | Chọn `app-image` hoặc installer type mà nền tảng hỗ trợ |
| `--name` | Tên ứng dụng |
| `--input` | Thư mục chứa JAR và dependency |
| `--main-jar` | JAR chính của ứng dụng classpath |
| `--main-class` | Main class |
| `--module-path` | Module path cho ứng dụng modular |
| `--module` | Module và main class của ứng dụng |
| `--runtime-image` | Runtime image có sẵn để đưa vào app |
| `--dest` | Thư mục đầu ra |
| `--app-version` | Phiên bản ứng dụng |
| `--vendor` | Nhà cung cấp |
| `--icon` | Icon ứng dụng/package |
| `--arguments` | Tham số mặc định truyền cho ứng dụng |
| `--java-options` | Tùy chọn JVM cho launcher |
| `--launcher` | Cấu hình launcher bổ sung |
| `--resource-dir` | Tài nguyên tùy chỉnh cho package |
| `--license-file` | File license cho installer khi loại package hỗ trợ |

Các tùy chọn riêng cho Windows, macOS hoặc Linux có thể bổ sung shortcut, menu, package metadata, signing và cấu hình cài đặt. Kiểm tra `jpackage --help` trên đúng nền tảng và JDK đang build:

~~~bash
jpackage --help
~~~

Không giả định mọi option đều có ý nghĩa hoặc được hỗ trợ giống nhau trên mọi hệ điều hành.

## 7. Phân biệt ba artifact bằng trách nhiệm

| Câu hỏi | JAR | Runtime image | Installer/package |
| --- | --- | --- | --- |
| Chứa class/resource ứng dụng? | Có | Không nhất thiết | Thường chứa app image hoặc tham chiếu nội dung ứng dụng |
| Cung cấp JVM? | Không | Có | Có thể chứa runtime image |
| Có dependency ứng dụng? | Có thể, tùy loại JAR | Không tự động chứa mọi dependency classpath | Có thể đóng gói dependency trong app image |
| Cần Java cài sẵn trên máy đích? | Có, nếu chạy JAR trực tiếp | Không cần runtime riêng bên ngoài | Không cần nếu installer chứa runtime |
| Có launcher dễ dùng? | Có thể chạy qua `java -jar` | Có thể có launcher do `jlink --launcher` tạo | Thường tạo launcher native |
| Tích hợp cách cài đặt hệ điều hành? | Không | Không | Có |
| Gỡ cài đặt theo package manager? | Không | Không | Có thể, tùy loại package |
| Dùng chung mọi OS/CPU? | Thường portable nếu không phụ thuộc native | Không | Không, thường theo nền tảng |

Cần lưu ý: installer không bắt buộc phải chứa runtime. Có thể đóng gói app mà yêu cầu Java có sẵn, nhưng với desktop application phân phối cho người dùng cuối, bundle runtime thường giúp giảm phụ thuộc vào môi trường máy đích.

## 8. Ba mô hình phân phối phổ biến

### 8.1. Chỉ phát hành JAR

~~~text
Download application.jar
        |
        v
Người dùng cài Java tương thích
        |
        v
java -jar application.jar
~~~

Ưu điểm:

- Artifact nhỏ và dễ lưu trữ.
- Dễ đưa vào server, container hoặc pipeline CI/CD.
- Runtime được quản lý tập trung.
- Phù hợp thư viện hoặc ứng dụng dành cho developer.

Điểm cần quản lý:

- Người dùng phải cài đúng runtime.
- Cần cung cấp dependency nếu không phải fat JAR.
- Hướng dẫn chạy phụ thuộc môi trường shell và classpath.

### 8.2. Phát hành app image có runtime riêng

~~~text
Application JAR + dependencies
             |
             +------+
                    |
JDK modules -> jlink runtime
                    |
                    v
             jpackage app-image
                    |
                    v
          Folder có launcher + runtime
~~~

Ưu điểm:

- Người dùng không cần tự cài Java riêng.
- Có thể chỉ mang các module cần thiết.
- Launcher và cấu trúc thư mục được tạo sẵn.
- Phù hợp phân phối nội bộ hoặc qua kho tải artifact.

Điểm cần quản lý:

- App image gắn với nền tảng/kiến trúc.
- Phải tạo và kiểm thử cho từng nền tảng đích.
- Kích thước lớn hơn JAR đơn lẻ vì chứa runtime.

### 8.3. Phát hành installer có runtime riêng

~~~text
Application JAR + dependencies
             |
             v
      jlink runtime image
             |
             v
      jpackage app image
             |
             v
   Native installer (MSI/DMG/DEB...)
             |
             v
 Cài đặt, launcher, tích hợp OS
~~~

Ưu điểm:

- Trải nghiệm cài đặt quen thuộc.
- Có thể tạo shortcut/menu và metadata ứng dụng.
- Có thể cài runtime riêng cùng ứng dụng.
- Hỗ trợ quy trình cài/gỡ theo hệ điều hành.

Điểm cần quản lý:

- Installer phụ thuộc hệ điều hành và kiến trúc.
- Cần quy trình ký và phát hành package.
- Cần quản lý nâng cấp, dữ liệu người dùng và tương thích package manager.
- Pipeline build thường cần agent cho từng nền tảng.

## 9. Quan hệ với dependency và module graph

JAR, runtime image và installer có thể chứa các lớp dependency khác nhau:

- JAR ứng dụng chứa class và resource của ứng dụng.
- Dependency JAR chứa thư viện ngoài.
- Module runtime chứa các module của Java platform.
- App image kết hợp nội dung ứng dụng, dependency và runtime theo cấu hình.
- Installer đóng gói app image và metadata cài đặt.

Một lỗi thường gặp là nghĩ rằng `jlink` sẽ tự đóng gói mọi dependency JAR. `jlink` liên kết module runtime; dependency classpath cần được phân phối cùng ứng dụng và launcher phải tìm được chúng.

### 9.1. Xác định module runtime cần thiết

Có thể phân tích module dependency bằng `jdeps`:

~~~bash
jdeps --print-module-deps --class-path "input/lib/*" input/application.jar
~~~

Kết quả là danh sách module Java platform được công cụ xác định từ bytecode và classpath cung cấp. Dùng danh sách đó để hiểu runtime cần những module nào, rồi đối chiếu với các tính năng nạp động và service provider mà phân tích tĩnh có thể không thấy.

Với ứng dụng modular, quan hệ `requires` trong module descriptor là nguồn quan trọng để `jlink` phân giải dependency. Với ứng dụng classpath, cần quan sát cả thư viện ngoài, reflection, resource loading và cấu hình runtime.

### 9.2. ServiceLoader và provider

Ứng dụng dùng `ServiceLoader` có thể tìm implementation ở runtime. Nếu provider không được biểu diễn như dependency module trực tiếp, runtime image có thể thiếu module provider dù ứng dụng vẫn biên dịch thành công.

Kiểm tra:

- File service configuration trong JAR classpath.
- Directive `uses` và `provides` trong module descriptor.
- Các module provider được đặt trên module path.
- Cách `jlink --bind-services` ảnh hưởng đến tập module được liên kết.
- Test service loading trên runtime image cuối cùng.

Không nên chỉ chạy ứng dụng trên full JDK rồi suy ra runtime image tùy chỉnh chắc chắn có đủ module.

## 10. Launcher và cấu hình runtime

Launcher do `jpackage` tạo có thể đóng gói các JVM option và argument mặc định. Ví dụ:

~~~bash
jpackage --type app-image --name ExampleApp --input input --main-jar application.jar --main-class com.example.Main --java-options "-Xmx1g" --arguments "--config config/app.properties" --dest dist
~~~

Các option trong ví dụ chỉ minh họa cách truyền cấu hình; giá trị heap và đường dẫn config phải phù hợp môi trường thực tế.

Khi thiết kế launcher:

- Chỉ đặt JVM option thực sự cần thiết.
- Tránh hard-code đường dẫn tuyệt đối trên máy build.
- Xác định nơi lưu config và dữ liệu người dùng.
- Cho phép log đi tới vị trí có thể thu thập và xoay vòng.
- Xử lý working directory rõ ràng; không giả định thư mục hiện tại là thư mục cài đặt.
- Cung cấp cách truyền tham số khi cần chạy nhiều cấu hình.

### 10.1. Dữ liệu người dùng không nên nằm trong thư mục cài đặt

Thư mục cài đặt có thể được cập nhật hoặc thay thế khi nâng phiên bản. Dữ liệu người dùng như database local, cấu hình riêng, cache và log nên được lưu ở vị trí dữ liệu phù hợp với hệ điều hành và quyền truy cập.

Không nên ghi file mutable cạnh JAR hoặc launcher nếu thư mục cài đặt có thể chỉ đọc hoặc bị package manager thay thế. Ứng dụng nên phân biệt resource bất biến đi kèm artifact với dữ liệu do người dùng tạo.

## 11. Phiên bản Java và tương thích runtime

Một quy trình đóng gói cần thống nhất:

- Phiên bản source/API mục tiêu.
- Phiên bản class file.
- JDK dùng để tạo runtime image.
- Phiên bản module runtime được bundle.
- Dependency Java và native library.
- Hệ điều hành/kiến trúc đích.

Ví dụ với ứng dụng Java 17:

~~~bash
javac --release 17 -d out src/com/example/Main.java
~~~

Nếu runtime image được tạo từ JDK 17, runtime bundle sẽ có module runtime của bản JDK đó. Cần test ứng dụng trên chính runtime image được phát hành, thay vì chỉ test bằng JDK đầy đủ của máy phát triển.

JAR có thể chạy trên runtime mới hơn nếu class file và API tương thích, nhưng runtime image tùy chỉnh vẫn gắn với nền tảng và bộ module được tạo. Nâng cấp JDK có thể yêu cầu tạo lại runtime image và installer để nhận bản vá bảo mật/runtime mới.

## 12. Build theo từng nền tảng

Vì runtime image và installer thường gắn với hệ điều hành, kiến trúc và công cụ native, pipeline phát hành nên tách artifact theo target:

| Build target | Runtime image | Installer |
| --- | --- | --- |
| Windows x64 | Runtime Windows x64 | MSI hoặc EXE |
| macOS ARM64 | Runtime macOS ARM64 | DMG hoặc PKG |
| macOS x64 | Runtime macOS x64 | DMG hoặc PKG |
| Linux x64 | Runtime Linux x64 | DEB hoặc RPM |
| Linux ARM64 | Runtime Linux ARM64 | Package phù hợp bản phân phối |

Đây là ma trận ví dụ; danh sách target thực tế phụ thuộc người dùng và nền tảng mà ứng dụng hỗ trợ.

`jpackage` tạo package native trên nền tảng tương ứng; không nên giả định có thể tạo mọi loại installer từ một máy build duy nhất. Một pipeline đa nền tảng thường dùng runner Windows, macOS và Linux riêng, sau đó gom artifact vào một release.

Một số installer cần công cụ đóng gói native của hệ điều hành hoặc bộ công cụ bên ngoài. Kiểm tra yêu cầu của loại package trên JDK 17 và môi trường build trước khi chạy pipeline.

## 13. Ký và xác minh artifact

JAR có thể được ký bằng cơ chế ký JAR của Java; installer có thể cần chữ ký code signing của hệ điều hành để người dùng xác minh nhà phát hành và tính toàn vẹn.

Đây là hai lớp khác nhau:

- **JAR signing:** chữ ký nằm trong metadata của JAR và có thể được kiểm tra bằng công cụ Java.
- **OS code signing:** chữ ký gắn với executable hoặc installer theo định dạng và trust model của hệ điều hành.

Ví dụ kiểm tra chữ ký JAR:

~~~bash
jarsigner -verify -verbose -certs application.jar
~~~

Kết quả cần được diễn giải theo certificate chain, timestamp, policy và trạng thái tin cậy. Việc lệnh verify không báo lỗi không tự chứng minh người ký là nhà phát hành mà người dùng mong đợi; cần xác minh certificate identity và nguồn tải.

Ngoài chữ ký, có thể phát hành checksum (ví dụ SHA-256) để người nhận kiểm tra file tải xuống có khớp artifact được công bố. Checksum giúp phát hiện sai lệch nội dung, nhưng không xác thực danh tính nhà phát hành nếu checksum được lấy từ cùng một nguồn không đáng tin.

## 14. Kiểm thử artifact cuối cùng

Không chỉ kiểm thử source hoặc JAR. Cần kiểm thử chính artifact sẽ được phân phối:

1. Tạo JAR và kiểm tra nội dung, manifest/module descriptor.
2. Chạy JAR trên runtime Java 17 sạch với dependency đúng.
3. Tạo runtime image bằng `jlink`.
4. Kiểm tra module list và launcher của runtime image.
5. Chạy ứng dụng bằng runtime image, không dùng JDK đầy đủ trên PATH.
6. Tạo app image bằng `jpackage`.
7. Chạy launcher từ thư mục app image trên máy sạch.
8. Tạo installer native trên runner nền tảng tương ứng.
9. Cài đặt, khởi chạy, nâng cấp và gỡ cài đặt theo quy trình hỗ trợ.
10. Kiểm tra dữ liệu người dùng có còn sau nâng cấp hoặc gỡ cài đặt theo đúng chính sách sản phẩm.

Các test nên bao gồm chức năng có dùng reflection, ServiceLoader, charset, locale, timezone, file system, TLS và native library nếu ứng dụng phụ thuộc các phần đó. Runtime image nhỏ có thể thiếu module mà full JDK trên máy phát triển vô tình cung cấp.

### 14.1. Kiểm tra runtime image

Có thể gọi trực tiếp executable trong runtime image:

~~~bash
build/runtime/bin/java -version
build/runtime/bin/java --list-modules
build/runtime/bin/java -jar input/application.jar
~~~

Nếu có launcher do `jlink` tạo:

~~~bash
build/runtime/bin/myapp
~~~

Trên Windows, executable nằm trong `bin` với phần mở rộng `.exe`.

### 14.2. Kiểm tra app image và installer

Với app image, chạy launcher trong thư mục image trên một máy/VM sạch không có Java cài sẵn để xác nhận runtime được bundle đúng.

Với installer, kiểm tra:

- Cài đặt trên tài khoản có quyền phù hợp.
- Shortcut/menu và icon.
- Vị trí cài và quyền truy cập.
- Khởi chạy sau khi cài.
- Nâng cấp từ phiên bản trước.
- Gỡ cài đặt và chính sách giữ/xóa dữ liệu.
- Chữ ký, publisher và cảnh báo của hệ điều hành.

Không nên coi việc tạo được file MSI/DMG/DEB/RPM là bằng chứng ứng dụng đã cài và chạy đúng trên máy đích.

## 15. Lựa chọn mô hình phân phối

| Đối tượng / môi trường | Cách phân phối thường phù hợp | Lý do |
| --- | --- | --- |
| Developer hoặc server đã quản lý Java | JAR và dependency | Runtime được quản lý tập trung |
| Ứng dụng chạy trong container | JAR trong container image có Java runtime | Image container quản lý runtime và deployment |
| Ứng dụng desktop nội bộ | App image hoặc installer có runtime | Không bắt người dùng cài Java riêng |
| Ứng dụng desktop phát hành rộng | Installer theo OS, thường kèm runtime | Trải nghiệm cài đặt và cập nhật quen thuộc |
| Thư viện dùng bởi ứng dụng khác | JAR library | Không cần launcher hay installer |
| Công cụ CLI cho môi trường kiểm soát | JAR hoặc app image có launcher | Chọn theo việc runtime có được quản lý sẵn hay không |

Không có mô hình tốt nhất cho mọi sản phẩm. JAR thường đơn giản cho developer và server; runtime image giảm phụ thuộc vào Java cài sẵn; installer cải thiện tích hợp và quản lý cài đặt cho người dùng cuối.

## 16. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `java -jar` báo thiếu class | JAR không chứa dependency và classpath không được thiết lập | Đóng gói dependency hoặc cung cấp launcher/classpath |
| JAR chạy trên máy dev nhưng lỗi trên máy khác | Runtime/API hoặc dependency khác phiên bản | Chạy trên Java mục tiêu và kiểm tra `--release` |
| JAR không tự cung cấp Java | JAR chỉ chứa archive nội dung ứng dụng | Phân phối runtime image hoặc yêu cầu cài Java |
| jlink báo không tìm thấy module | Module path thiếu module hoặc dependency | Kiểm tra module descriptor và `--module-path` |
| Runtime image thiếu provider | Service provider không được liên kết | Kiểm tra `uses`/`provides`, service configuration và `--bind-services` |
| Ứng dụng chạy trên JDK nhưng lỗi trong runtime image | Runtime image thiếu module được nạp động | Phân tích dependency và test các nhánh chức năng |
| Nghĩ jlink đóng gói mọi dependency JAR | Nhầm module runtime với classpath dependency | Phân phối JAR dependency và cấu hình launcher |
| App image chạy trên Windows nhưng không chạy Linux | Runtime image/launcher phụ thuộc nền tảng | Build và test image cho từng OS/architecture |
| jpackage không tạo được installer | Thiếu công cụ native hoặc loại package không được hỗ trợ trên host | Kiểm tra yêu cầu nền tảng và `jpackage --help` |
| Installer cài được nhưng app không khởi chạy | Sai main class, runtime, đường dẫn hoặc JVM options | Kiểm tra launcher config và chạy app image trực tiếp |
| Nâng cấp làm mất dữ liệu | Dữ liệu lưu trong thư mục cài đặt bị thay thế | Lưu dữ liệu mutable ở thư mục dữ liệu người dùng |
| Installer không được hệ điều hành tin cậy | Thiếu hoặc sai code signing | Ký artifact và xác minh publisher/certificate |
| Runtime image quá lớn | Chọn module hoặc tài nguyên dư thừa | Phân tích dependency, chọn module có kiểm soát |
| Runtime image quá nhỏ nhưng lỗi ở chức năng phụ | Loại module được nạp động hoặc service provider | Bổ sung module cần thiết và test đầy đủ |

## 17. Quy trình tham khảo cho Java 17

Một pipeline đơn giản cho ứng dụng modular có thể đi theo các bước:

~~~bash
# 1. Compile module cho Java 17
javac --release 17 -d mods/com.example.app src/module-info.java src/com/example/Main.java

# 2. Build runtime image
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.app --launcher example=com.example.app/com.example.Main --output build/runtime

# 3. Tạo application image
jpackage --type app-image --name ExampleApp --module-path mods --module com.example.app/com.example.Main --runtime-image build/runtime --dest dist
~~~

Đây là skeleton minh họa; dự án thực tế cần xử lý source layout, dependency module, resource, service provider, version, icon và cấu hình launcher. Với ứng dụng classpath, thay tùy chọn module bằng `--main-jar` và `--main-class`, đồng thời bảo đảm input directory chứa dependency.

Sau khi tạo app image, kiểm tra launcher và runtime image trên môi trường sạch. Khi cần installer, chạy `jpackage` với `--type` tương ứng trên runner của nền tảng đích.

## 18. Bài tập thực hành

### Bài 1 — Tạo executable JAR

Viết class có `main`, biên dịch bằng `--release 17`, tạo JAR với `--main-class`, rồi chạy bằng `java -jar`. Dùng `jar --list` xem nội dung archive và kiểm tra manifest.

### Bài 2 — JAR có dependency

Thêm một thư viện bên ngoài. Thử chạy khi chỉ có JAR ứng dụng, sau đó cung cấp dependency qua classpath hoặc tạo fat JAR. Giải thích vì sao JAR thông thường không tự chứa dependency.

### Bài 3 — Tạo modular JAR

Viết `module-info.java`, biên dịch module và đóng gói thành JAR. Dùng `jar --describe-module` để xem descriptor. Chạy trên module path.

### Bài 4 — Tạo runtime image

Dùng `jlink` tạo runtime image cho module ứng dụng. Dùng executable Java trong image chạy ứng dụng và so sánh danh sách module với JDK đầy đủ.

### Bài 5 — Tạo launcher

Dùng `jlink --launcher` tạo launcher có tên riêng. Chạy launcher mà không gọi `java -m` thủ công.

### Bài 6 — Tạo app image

Dùng `jpackage --type app-image` để tạo app image. Chạy trên máy/VM không cài Java riêng và xác nhận runtime được bundle.

### Bài 7 — Tạo installer

Trên hệ điều hành phù hợp, tạo installer native. Kiểm tra cài đặt, shortcut, khởi chạy, nâng cấp và gỡ cài đặt.

### Bài 8 — So sánh dung lượng

So sánh kích thước JAR, runtime image và installer. Giải thích phần dung lượng tăng thêm đến từ JVM/module runtime, native launcher, metadata và tài nguyên đóng gói.

## 19. Nguyên tắc cần nhớ

- **JAR** đóng gói class, resource và có thể cả dependency; bản thân JAR không cung cấp JVM.
- **Runtime image** cung cấp JVM và tập module runtime cần thiết; có thể được tùy chỉnh bằng `jlink`.
- **Installer** đóng gói ứng dụng để cài theo hệ điều hành; thường được tạo bằng `jpackage` và có thể chứa runtime image.
- `jlink` liên kết module runtime; dependency JAR thuần classpath vẫn cần được phân phối và đưa vào launcher.
- Runtime image và installer thường gắn với OS/CPU target; tạo artifact riêng cho từng nền tảng được hỗ trợ.
- `jpackage` có thể tạo app image hoặc native installer; installer type và toolchain phụ thuộc hệ điều hành.
- Test chính runtime image/app image/installer được phát hành, không chỉ test source hoặc JAR trên máy phát triển.
- Quản lý dữ liệu người dùng tách khỏi thư mục cài đặt để nâng cấp/gỡ cài đặt không làm mất dữ liệu ngoài ý muốn.
- Ký artifact, xác minh publisher và phát hành checksum trong quy trình phân phối phù hợp.

Khi hiểu rõ trách nhiệm của JAR, runtime image và installer, nhóm phát triển có thể chọn cách phát hành phù hợp: dùng JAR trong môi trường đã quản lý Java, dùng runtime image để cung cấp môi trường chạy riêng, hoặc dùng `jpackage` để tạo ứng dụng có launcher và gói cài đặt native cho người dùng Java 17.
