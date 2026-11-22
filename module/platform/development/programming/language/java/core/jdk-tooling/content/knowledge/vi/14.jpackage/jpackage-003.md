# Application image với jpackage

## 1. Application image là gì?

**Application image** là một thư mục ứng dụng do công cụ **jpackage** tạo ra. Image chứa launcher native của ứng dụng, payload cần thiết và một Java runtime image để ứng dụng có thể chạy trên máy đích mà không cần người dùng cài riêng Java.

Có thể hình dung một application image gồm ba phần:

1. **Application launcher:** executable theo hệ điều hành, cho phép người dùng mở ứng dụng như một chương trình thông thường.
2. **Application payload:** JAR, class, resource, file cấu hình mặc định và các nội dung ứng dụng cần đóng gói.
3. **Java runtime image:** runtime được jpackage tạo bằng jlink hoặc runtime image đã chuẩn bị trước và truyền qua tùy chọn --runtime-image.

Application image là một dạng đầu ra của jpackage với loại **app-image**. Đây là một thư mục có cấu trúc, không phải một file JAR hay một bộ cài đặt. Người dùng có thể chạy launcher bên trong thư mục image; nhóm phát triển có thể kiểm thử image trước khi tạo installer hoặc phân phối.

Lợi ích chính là đóng gói ứng dụng cùng runtime tương thích, tạo launcher theo nền tảng và giảm các bước cài đặt Java thủ công cho người dùng cuối. Image vẫn phụ thuộc vào hệ điều hành, kiến trúc CPU và các native library mà ứng dụng cần.

## 2. Phân biệt application image, JAR, runtime image và installer

Các loại artifact này giải quyết những việc khác nhau:

| Artifact | Nội dung và mục đích |
|---|---|
| Executable JAR | Đóng gói class/resource Java và metadata khởi chạy; máy đích vẫn cần Java runtime phù hợp. |
| Runtime image | Một Java runtime được tạo bằng jlink; bản thân nó chưa có launcher và payload ứng dụng hoàn chỉnh. |
| Application image | Launcher native, application payload và runtime image được tổ chức thành một thư mục chạy được. |
| Installer/package | Bộ cài đặt nền tảng như MSI, EXE, DMG, PKG, DEB hoặc RPM tùy hệ điều hành và JDK; có thể cài file, shortcut và tích hợp hệ điều hành. |

Một quy trình thường gặp:

~~~text
Source code + dependencies
          |
          v
       JAR files
          |
          v
       jpackage
          |
          +----> application launcher
          +----> application payload
          +----> Java runtime image
          |
          v
     Application image
          |
          +----> test / archive / distribute
          |
          v
       Installer
~~~

Application image có thể được tạo trực tiếp từ ứng dụng hoặc dùng làm đầu vào để jpackage tạo installer bằng tùy chọn --app-image. Ví dụ, trên Windows có thể tạo MSI từ image đã kiểm thử. Loại installer khả dụng phụ thuộc hệ điều hành và công cụ đóng gói có trên máy build.

Không nên nhầm tùy chọn **--type app-image** với **--type msi** hoặc **--type dmg**. App-image tạo thư mục ứng dụng; các loại còn lại tạo package cài đặt dành cho nền tảng tương ứng.

## 3. jpackage hoạt động như thế nào?

jpackage nhận thông tin về ứng dụng, xác định entry point, thu thập nội dung cần đóng gói và tạo launcher. Theo mặc định, nếu không cung cấp runtime image có sẵn, jpackage sử dụng **jlink** để tạo runtime phù hợp rồi đặt runtime đó vào application image.

Với ứng dụng không modular, jpackage nhận main JAR và main class. Với ứng dụng modular, jpackage nhận module path và main module. Tùy kiểu ứng dụng, công cụ xác định module cần có trong runtime image; có thể chỉ định thêm module bằng --add-modules.

Các bước chính:

1. Đọc JAR hoặc module đầu vào và thông tin launcher.
2. Xác định module cần có trong runtime image.
3. Tạo runtime bằng jlink hoặc sao chép runtime image được cung cấp.
4. Tạo launcher native và cấu hình khởi chạy.
5. Đóng gói application payload cùng runtime vào thư mục đích.

jpackage là công cụ thuộc JDK. Nên dùng JDK đầy đủ trên máy build vì cần các công cụ như jpackage, jlink và các tiện ích Java khác.

Kiểm tra phiên bản và tùy chọn mà JDK đang dùng hỗ trợ:

~~~bash
jpackage --version
jpackage --help
~~~

Các tùy chọn nền tảng có thể khác nhau giữa Windows, Linux và macOS cũng như giữa các phiên bản JDK. Hãy xem help của đúng JDK trên máy build trước khi đưa lệnh vào CI.

## 4. Chuẩn bị ứng dụng không modular

Ví dụ dưới đây tạo một ứng dụng Java đơn giản, đóng gói thành JAR rồi tạo application image.

Cấu trúc source:

~~~text
hello-app/
├── src/
│   └── demo/
│       └── Hello.java
├── classes/
├── input/
└── dist/
~~~

File **src/demo/Hello.java**:

~~~java
package demo;

public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from jpackage application image!");
    }
}
~~~

Biên dịch source và tạo JAR:

~~~bash
mkdir -p classes input dist

javac --release 17 -encoding UTF-8 -d classes src/demo/Hello.java

jar --create \
    --file input/hello.jar \
    --main-class demo.Hello \
    -C classes .
~~~

**--release 17** đặt API và bytecode đích của ứng dụng ở Java 17. JAR được đặt trong thư mục **input**, và **demo.Hello** là main class.

Trên Windows PowerShell, có thể tạo thư mục bằng:

~~~powershell
New-Item -ItemType Directory -Force classes, input, dist | Out-Null
~~~

Sau đó chạy các lệnh javac và jar tương tự. Các đường dẫn ví dụ dùng dấu gạch chéo xuôi, được các công cụ JDK hỗ trợ trên Windows.

## 5. Tạo application image cho ứng dụng không modular

Từ thư mục gốc **hello-app**, chạy:

~~~bash
jpackage --type app-image \
    --name HelloApp \
    --app-version 1.0.0 \
    --input input \
    --main-jar hello.jar \
    --main-class demo.Hello \
    --dest dist
~~~

Ý nghĩa các tùy chọn:

- **--type app-image:** yêu cầu tạo application image.
- **--name HelloApp:** đặt tên image và launcher chính.
- **--app-version 1.0.0:** đặt phiên bản ứng dụng.
- **--input input:** chỉ định thư mục chứa các file cần đóng gói.
- **--main-jar hello.jar:** chọn JAR chính; đường dẫn được tính tương đối từ thư mục input.
- **--main-class demo.Hello:** chỉ định class có phương thức main.
- **--dest dist:** đặt thư mục cha chứa image được tạo.

Nếu bỏ --dest, jpackage mặc định ghi output vào thư mục làm việc hiện tại. Nên chỉ định rõ thư mục đích để CI và script đóng gói có thể tìm artifact nhất quán.

Khi dùng --main-jar, có thể chỉ định --main-class để launcher không phải dựa vào Main-Class trong manifest. --main-class chỉ dùng cùng --main-jar. Với ứng dụng modular, dùng --module thay cho cặp tùy chọn này.

Lệnh trên tạo một application image tên HelloApp bên trong dist. Trên Windows, launcher thường có tên HelloApp.exe; trên Linux là launcher HelloApp; trên macOS image thường là bundle HelloApp.app.

### Console application trên Windows

Ví dụ Hello in kết quả ra console. Khi tạo image trên Windows, thêm tùy chọn nền tảng **--win-console** để tạo console launcher:

~~~powershell
jpackage --type app-image --name HelloApp --app-version 1.0.0 --input input --main-jar hello.jar --main-class demo.Hello --dest dist --win-console
~~~

--win-console là tùy chọn dành cho Windows. Ứng dụng GUI thông thường có thể không cần console launcher. Hãy kiểm tra jpackage --help trên nền tảng đích trước khi dùng tùy chọn riêng của hệ điều hành.

## 6. Chạy application image và kiểm tra kết quả

Sau khi jpackage hoàn tất, chạy launcher nằm bên trong image.

Windows PowerShell:

~~~powershell
.\dist\HelloApp\HelloApp.exe
~~~

Linux:

~~~bash
./dist/HelloApp/bin/HelloApp
~~~

macOS có thể mở application bundle:

~~~bash
open dist/HelloApp.app
~~~

Để quan sát stdout khi chạy ví dụ console từ terminal trên macOS, có thể gọi executable trong bundle:

~~~bash
./dist/HelloApp.app/Contents/MacOS/HelloApp
~~~

Kết quả do ứng dụng in ra:

~~~text
Hello from jpackage application image!
~~~

Các đường dẫn launcher ở trên là bố cục điển hình của application image trên từng hệ điều hành. Tên thư mục, vị trí file cấu hình và một số thành phần nội bộ có thể thay đổi theo JDK, nền tảng và tùy chọn đóng gói.

Khi chạy application image, launcher sử dụng runtime được đóng gói cùng image. Người dùng không cần dựa vào JAVA_HOME hoặc Java được cài toàn hệ thống để khởi chạy ứng dụng đó. Tuy vậy, ứng dụng vẫn có thể cần native library, quyền truy cập file, thiết bị hoặc thành phần hệ điều hành khác.

## 7. Application image cho ứng dụng modular

Với ứng dụng modular, dùng **--module-path** để chỉ định vị trí các module và **--module** để xác định main module cùng main class.

Ví dụ:

~~~bash
jpackage --type app-image \
    --name ModularHello \
    --module-path mods \
    --module com.example.app/com.example.app.Main \
    --dest dist
~~~

Trong đó:

- **mods** chứa module ứng dụng và các module dependency.
- **com.example.app** là tên main module.
- **com.example.app.Main** là main class của module.
- jpackage liên kết main module vào runtime image.

Nếu main class đã được khai báo trong module metadata phù hợp, có thể dùng dạng **--module com.example.app**; tuy nhiên, chỉ rõ main class giúp lệnh đóng gói dễ đọc và dễ kiểm tra.

Có thể bổ sung module cần thiết:

~~~bash
jpackage --type app-image \
    --name ModularHello \
    --module-path mods \
    --module com.example.app/com.example.app.Main \
    --add-modules java.sql,java.logging \
    --dest dist
~~~

--add-modules nhận danh sách tên module phân tách bằng dấu phẩy. Hãy thêm module mà ứng dụng thực sự cần, đặc biệt khi module được nạp động hoặc sử dụng qua reflection và không thể xác định đầy đủ từ dependency tĩnh.

--module và --main-jar là hai cách chỉ định entry point khác nhau; không truyền đồng thời cả hai. Nếu ứng dụng là modular, dùng module path và main module. Nếu ứng dụng không modular, dùng input directory, main JAR và main class.

## 8. Runtime image được tạo hoặc cung cấp trước

Theo mặc định, jpackage tạo runtime image bằng jlink. Runtime đi kèm application image thường được rút gọn theo các tùy chọn mặc định của jpackage, ví dụ loại bỏ debug information, header file, man page và native command không cần cho ứng dụng.

Điều này giúp image gọn hơn một JDK đầy đủ. Runtime image không bao gồm compiler javac, javadoc hay toàn bộ công cụ phát triển như một JDK.

Có hai cách kiểm soát runtime:

**Cách 1: để jpackage tự gọi jlink.**

Dùng --add-modules để bổ sung module cần thiết và --jlink-options để truyền các tùy chọn jlink phù hợp. Kiểm tra help của JDK mục tiêu để biết giá trị mặc định và tùy chọn được hỗ trợ.

Ví dụ:

~~~bash
jpackage --type app-image \
    --name HelloApp \
    --input input \
    --main-jar hello.jar \
    --main-class demo.Hello \
    --add-modules java.sql \
    --dest dist
~~~

**Cách 2: tạo runtime image riêng bằng jlink rồi truyền vào jpackage.**

Ví dụ tạo runtime image cho ứng dụng modular:

~~~bash
jlink \
    --module-path "$JAVA_HOME/jmods:mods" \
    --add-modules com.example.app \
    --output custom-runtime
~~~

Trên Windows, ký tự phân tách nhiều phần tử module path thường là dấu chấm phẩy; trên Linux/macOS thường là dấu hai chấm. Thay đường dẫn theo vị trí JDK và module thực tế.

Sau đó dùng runtime image đã tạo:

~~~bash
jpackage --type app-image \
    --name ModularHello \
    --module-path mods \
    --module com.example.app/com.example.app.Main \
    --runtime-image custom-runtime \
    --dest dist
~~~

Khi truyền --runtime-image, jpackage sao chép runtime image được chỉ định vào application image thay vì tự tạo runtime mới bằng jlink. Runtime phải phù hợp với hệ điều hành và kiến trúc đích, đồng thời chứa đầy đủ module mà ứng dụng cần.

Cần phân biệt release đích của bytecode với phiên bản runtime được đóng gói. Ví dụ, compile bằng javac --release 17 nhưng chạy jpackage từ JDK 24 thì runtime image mặc định được tạo từ JDK 24. Nếu muốn bundle runtime Java 17, hãy dùng jpackage/JDK 17 hoặc tạo runtime image Java 17 bằng jlink rồi truyền qua --runtime-image. Luôn kiểm tra runtime trong image thực tế.

## 9. Đóng gói dependency, resource và application content

Đối với ứng dụng không modular, --input chỉ định thư mục chứa các file được đưa vào application image. Thư mục này có thể chứa main JAR, dependency JAR, resource ngoài JAR và các file ứng dụng cần khi chạy.

Ví dụ:

~~~text
input/
├── hello.jar
├── lib/
│   ├── logging.jar
│   └── database-driver.jar
└── config/
    └── app-defaults.properties
~~~

jpackage đưa các file trong input directory vào application payload. Hãy xác nhận launcher có cấu hình classpath phù hợp với dependency JAR và ứng dụng tìm được resource ở vị trí đã đóng gói. Một cách đơn giản để giảm cấu hình dependency là tạo executable/fat JAR theo quy trình build của dự án, rồi kiểm thử image từ JAR đó.

Tùy chọn **--app-content** cho phép thêm file hoặc thư mục vào payload ngoài input directory:

~~~bash
jpackage --type app-image \
    --name HelloApp \
    --input input \
    --main-jar hello.jar \
    --main-class demo.Hello \
    --app-content extra-data,licenses \
    --dest dist
~~~

Có thể dùng --app-content nhiều lần. Các đường dẫn phải tồn tại và được chỉ định phù hợp với thư mục làm việc khi chạy jpackage.

Không đóng gói file cấu hình môi trường phát triển, private key, mật khẩu, token hoặc secret vào application image. Nếu ứng dụng cần cấu hình riêng theo từng môi trường, hãy cung cấp cơ chế cấu hình bên ngoài và bảo vệ quyền đọc/ghi file đó.

Native library cũng cần đúng nền tảng và kiến trúc. Một file DLL, SO hoặc DYLIB của hệ điều hành khác không thể thay thế lẫn nhau. Hãy kiểm tra đường dẫn nạp native library và các dependency hệ thống khi thử image trên máy sạch.

## 10. Tùy chỉnh launcher và tham số JVM

jpackage cung cấp các tùy chọn để thiết lập cách launcher khởi chạy ứng dụng.

| Tùy chọn | Công dụng |
|---|---|
| --arguments | Tham số mặc định truyền cho main class khi người dùng không cung cấp tham số riêng. |
| --java-options | Tùy chọn truyền cho Java runtime, ví dụ heap size hoặc system property. |
| --icon | Icon của launcher/package theo định dạng được nền tảng hỗ trợ. |
| --description | Mô tả ứng dụng. |
| --vendor | Tên nhà cung cấp ứng dụng. |
| --app-version | Phiên bản ứng dụng/package. |
| --add-launcher | Tạo launcher bổ sung với cấu hình riêng. |
| --verbose | In chi tiết hoạt động đóng gói. |

Ví dụ đặt JVM option và tham số mặc định:

~~~bash
jpackage --type app-image \
    --name HelloApp \
    --input input \
    --main-jar hello.jar \
    --main-class demo.Hello \
    --java-options "-Xms128m" \
    --java-options "-Xmx512m" \
    --arguments "--mode=desktop" \
    --dest dist
~~~

--java-options dành cho JVM; --arguments dành cho chương trình Java. Hai loại tham số có mục đích khác nhau. Không đặt secret vào command line vì chúng có thể xuất hiện trong log hoặc danh sách tiến trình tùy môi trường.

### Tạo launcher phụ bằng --add-launcher

Có thể tạo file Properties cho launcher phụ, ví dụ **launchers/report.properties**:

~~~properties
arguments=--mode=report
java-options=-Xmx512m
description=Report mode
~~~

Tạo image với launcher chính và launcher phụ:

~~~bash
jpackage --type app-image \
    --name HelloApp \
    --input input \
    --main-jar hello.jar \
    --main-class demo.Hello \
    --add-launcher Reports=launchers/report.properties \
    --dest dist
~~~

Launcher Reports dùng các tùy chọn được định nghĩa trong file Properties. Một số khóa có thể ghi đè cấu hình dòng lệnh của launcher chính, ví dụ main-jar, main-class, arguments, java-options, icon hoặc description. Danh sách khóa hỗ trợ tùy thuộc JDK và nền tảng; xem jpackage --help.

## 11. Bố cục application image theo hệ điều hành

Application image có cấu trúc khác nhau theo nền tảng vì launcher và runtime phụ thuộc hệ điều hành.

### Windows

Một image điển hình có dạng:

~~~text
HelloApp/
├── HelloApp.exe
├── app/
│   ├── HelloApp.cfg
│   └── hello.jar
└── runtime/
    ├── bin/
    └── lib/
~~~

File EXE là launcher native. Thư mục app chứa payload và cấu hình launcher; runtime chứa Java runtime image. Tên file và chi tiết nội bộ có thể thay đổi theo phiên bản JDK.

### Linux

Một image thường có dạng:

~~~text
HelloApp/
├── bin/
│   └── HelloApp
└── lib/
    ├── app/
    │   ├── HelloApp.cfg
    │   └── hello.jar
    └── runtime/
~~~

Launcher nằm trong bin; application payload và runtime thường nằm dưới lib.

### macOS

Application image thường là một bundle **HelloApp.app**:

~~~text
HelloApp.app/
└── Contents/
    ├── Info.plist
    ├── MacOS/
    │   └── HelloApp
    ├── app/
    └── runtime/
~~~

Info.plist chứa metadata của bundle; executable launcher nằm trong Contents/MacOS. Có thể mở bundle từ Finder hoặc dùng lệnh open.

Đây là cấu trúc tham khảo. Không nên hard-code đường dẫn nội bộ của runtime hoặc launcher configuration trong ứng dụng nếu không có lý do rõ ràng. Hãy dùng launcher được jpackage tạo và các API Java phù hợp để xác định vị trí resource.

## 12. Application image và installer

Sau khi kiểm thử application image, có thể dùng chính image đó làm đầu vào cho bước tạo installer.

Ví dụ trên Windows, nếu JDK và hệ thống hỗ trợ MSI:

~~~powershell
jpackage --type msi --name HelloApp --app-image dist\HelloApp --dest packages
~~~

Trên macOS hoặc Linux, loại package và công cụ native cần thiết sẽ khác. Xem jpackage --help trên máy build để biết các loại package được hỗ trợ, ví dụ DMG/PKG trên macOS hoặc DEB/RPM trên Linux khi có công cụ tương ứng.

Installer có thể tích hợp thêm shortcut, menu, file association, thư mục cài đặt và metadata hệ điều hành. Những tích hợp này thuộc quy trình tạo package cài đặt và phụ thuộc tùy chọn nền tảng. Application image tự nó chỉ là thư mục ứng dụng có thể chạy; nó không tự đăng ký ứng dụng với hệ điều hành như một installer.

Tùy chọn --app-image cho phép jpackage tạo package từ một image đã được xây dựng và kiểm thử. Điều này giúp tách việc tạo runtime/application payload khỏi việc tạo installer, đồng thời có thể tái sử dụng cùng image trong quy trình đóng gói phù hợp.

## 13. Kiểm thử và xác minh application image

Một lệnh jpackage kết thúc thành công chỉ xác nhận công cụ đã tạo output theo cấu hình yêu cầu. Cần kiểm thử image thực tế trước khi phân phối.

Quy trình kiểm tra:

1. Xác nhận thư mục image được tạo trong đúng --dest.
2. Kiểm tra launcher có tồn tại và có quyền thực thi trên Linux/macOS.
3. Chạy launcher trên máy sạch cùng hệ điều hành và kiến trúc mục tiêu.
4. Xác nhận ứng dụng chạy mà không phụ thuộc vào Java cài toàn hệ thống.
5. Kiểm tra resource, dependency JAR, native library và file cấu hình.
6. Kiểm tra tham số mặc định, tham số người dùng và JVM options.
7. Kiểm tra log, stdout/stderr, exit code và hành vi khi thiếu cấu hình.
8. Xác nhận runtime đi kèm đúng release và đã nhận bản vá bảo mật cần thiết.
9. Lưu checksum và build identity của image trước khi phát hành.

Có thể bật verbose để điều tra quá trình đóng gói:

~~~bash
jpackage --type app-image --verbose \
    --name HelloApp \
    --input input \
    --main-jar hello.jar \
    --main-class demo.Hello \
    --dest dist
~~~

Khi cần kiểm tra module phụ thuộc, jdeps có thể giúp phân tích dependency tĩnh của JAR:

~~~bash
jdeps --print-module-deps --multi-release 17 input/hello.jar
~~~

Kết quả của jdeps là thông tin hỗ trợ lựa chọn module. Các dependency được nạp bằng reflection, cấu hình hoặc ServiceLoader có thể cần được khai báo bổ sung và kiểm thử riêng.

Nếu image được nén thành ZIP để phân phối, phải giữ nguyên toàn bộ cấu trúc thư mục và thuộc tính cần thiết, đặc biệt quyền thực thi trên nền tảng Unix. Không chỉ lấy file launcher EXE hoặc binary trong bin rồi gửi riêng, vì runtime và payload đi kèm cũng cần thiết.

## 14. Khả năng tương thích nền tảng và cập nhật runtime

Application image có tính đặc thù theo nền tảng:

- Image Windows dành cho Windows và kiến trúc CPU tương ứng.
- Image Linux cần phù hợp với kiến trúc và yêu cầu thư viện hệ thống của môi trường đích.
- Image macOS cần phù hợp với kiến trúc Intel hoặc Apple Silicon mà JDK/runtime được xây dựng cho.
- Native library phải được biên dịch cho đúng hệ điều hành, kiến trúc và ABI.

jpackage không phải công cụ cross-compiler để tạo image cho mọi hệ điều hành từ một máy build duy nhất. Thực tế phát hành thường cần build image trên runner phù hợp với từng nền tảng đích, rồi kiểm thử artifact trên nền tảng đó.

Runtime được bundle bên trong image là một bản runtime riêng. Khi máy build cài bản vá JDK mới, application image cũ không tự cập nhật runtime. Cần tạo lại image bằng JDK đã cập nhật hoặc runtime image mới, chạy test và phát hành bản ứng dụng mới.

Với phân phối công khai, hãy kiểm tra yêu cầu ký mã, notarization trên macOS, chính sách antivirus và metadata package của nền tảng. Quy trình ký và phát hành có thể cần công cụ/chứng thư riêng ngoài việc tạo app-image.

## 15. Lỗi thường gặp khi tạo application image

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| jpackage không tìm thấy main JAR | Sai --input hoặc tên --main-jar không tương đối với input directory. | Kiểm tra file JAR và đường dẫn tương đối. |
| Không tìm thấy main class | Main class sai package hoặc JAR không chứa class đó. | Dùng jar tf để kiểm tra nội dung và khai báo đúng tên đầy đủ. |
| Image chạy trên máy build nhưng không chạy máy khác | Thiếu native dependency, khác kiến trúc hoặc khác yêu cầu hệ điều hành. | Kiểm thử trên máy sạch cùng nền tảng mục tiêu. |
| Ứng dụng báo thiếu module | Runtime image không chứa module được nạp động hoặc dependency cần thiết. | Dùng --add-modules hoặc runtime image được tạo bằng jlink với module đầy đủ. |
| Dependency JAR không được tìm thấy | Dependency không nằm trong payload hoặc launcher configuration/classpath chưa phù hợp. | Đưa dependency vào quy trình đóng gói và kiểm tra launcher config. |
| Image dùng Java release cao hơn dự kiến | jpackage tạo runtime từ JDK đang chạy công cụ. | Kiểm tra jpackage --version; dùng đúng JDK hoặc --runtime-image. |
| Launcher không hiện console trên Windows | Dùng GUI launcher cho ứng dụng cần stdin/stdout. | Tạo image với --win-console. |
| Image quá lớn | Runtime chứa nhiều module hoặc payload thừa. | Phân tích dependency, tinh chỉnh module và loại file không cần khỏi input. |
| Native library không nạp được | File sai OS/architecture hoặc search path chưa đúng. | Kiểm tra định dạng binary, ABI và vị trí nạp thư viện. |
| Không thấy shortcut/file association | Đang tạo app-image thay vì installer hoặc thiếu tùy chọn package nền tảng. | Tạo installer phù hợp và cấu hình tích hợp hệ điều hành. |
| Không chạy được sau khi giải nén | Archive làm mất quyền thực thi hoặc thay đổi cấu trúc thư mục. | Tạo lại archive giữ metadata và kiểm tra quyền launcher. |
| Image cũ còn lỗ hổng runtime | Runtime đã bundle không được cập nhật cùng JDK hệ thống. | Rebuild image bằng JDK/runtime đã vá và phát hành lại. |

## 16. Quy trình build application image trong CI

Một pipeline có thể chia thành các bước sau:

1. Checkout đúng commit và thiết lập JDK được tổ chức hỗ trợ.
2. Build ứng dụng và dependency bằng Gradle/Maven hoặc javac/jar.
3. Chuẩn bị input directory chỉ chứa file runtime cần phân phối.
4. Chạy jpackage với --type app-image, tên, phiên bản, entry point và thư mục đích rõ ràng.
5. Kiểm tra runtime image, launcher, payload và native dependencies.
6. Chạy smoke test bằng launcher của application image.
7. Lưu artifact theo OS/architecture, commit và phiên bản JDK.
8. Tạo checksum, ký mã nếu quy trình phát hành yêu cầu.
9. Chỉ dùng image đã kiểm thử để tạo installer hoặc đưa vào kênh phân phối.

Nên pin JDK/toolchain và ghi nhận phiên bản jpackage, jlink, hệ điều hành, kiến trúc, module list cùng các tùy chọn đóng gói. Điều này giúp tái lập image và điều tra khác biệt giữa các lần build.

Giữ input directory sạch. Không đóng gói file test, log build, source không cần thiết, cache hoặc secret. Nếu cần cấu hình riêng cho production, hãy cấp phát qua cơ chế triển khai an toàn thay vì nhúng thông tin nhạy cảm vào image.

## 17. Checklist trước khi phát hành application image

- [ ] Đã xác định ứng dụng modular hay non-modular.
- [ ] Đã chọn đúng main JAR/main class hoặc main module.
- [ ] Đã kiểm tra toàn bộ dependency, resource và native library cần thiết.
- [ ] Đã chọn rõ phiên bản JDK dùng để chạy jpackage.
- [ ] Đã xác nhận phiên bản runtime được bundle trong image.
- [ ] Đã dùng --type app-image và chỉ định --dest rõ ràng.
- [ ] Đã cấu hình --add-modules hoặc runtime image tùy chỉnh nếu cần.
- [ ] Đã kiểm tra launcher, tham số, JVM options và icon.
- [ ] Đã kiểm thử trên máy sạch của từng OS/architecture mục tiêu.
- [ ] Đã xác nhận image chạy được mà không cần Java cài toàn hệ thống.
- [ ] Đã giữ nguyên cấu trúc và quyền file khi archive/phân phối.
- [ ] Đã lên kế hoạch rebuild image khi runtime nhận bản vá bảo mật.
- [ ] Đã kiểm tra ký mã, notarization và installer nếu kênh phát hành yêu cầu.

Application image giúp đóng gói Java application thành một thư mục có launcher native, payload và runtime riêng. Khi kiểm soát đúng entry point, module runtime, dependency và nền tảng đích, jpackage tạo được artifact dễ kiểm thử, phân phối và chuyển tiếp sang bước tạo installer.