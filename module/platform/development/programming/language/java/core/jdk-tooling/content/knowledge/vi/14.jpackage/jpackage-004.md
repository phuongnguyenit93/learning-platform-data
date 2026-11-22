# Native installer bằng jpackage

**jpackage** là công cụ của JDK dùng để đóng gói ứng dụng Java thành application image hoặc gói cài đặt gốc của hệ điều hành (native installer). Gói cài đặt có thể tích hợp với quy trình cài đặt, menu ứng dụng, shortcut, thư mục cài đặt và cơ chế quản lý phần mềm của nền tảng.

Native installer thường chứa ứng dụng cùng một runtime Java riêng được tạo hoặc cung cấp khi đóng gói. Người dùng có thể cài và chạy ứng dụng mà không cần tự cài JDK/JRE tương thích trên máy, miễn là gói được tạo cho đúng hệ điều hành và kiến trúc.

Một lệnh cơ bản trên Windows:

~~~bash
jpackage --type msi --name HelloDesk --input build/input --main-jar hello.jar --main-class com.example.hello.Main --dest build/installers
~~~

Trên Linux có thể tạo DEB hoặc RPM; trên macOS có thể tạo PKG hoặc DMG. Tập định dạng được hỗ trợ phụ thuộc nền tảng đang chạy jpackage.

## 1. Native installer, application image và runtime image

Ba khái niệm này liên quan nhưng không giống nhau:

- **Runtime image:** bộ runtime Java đã được liên kết từ các module cần thiết, thường do jlink tạo. Nó chứa các module và thư viện runtime cần cho ứng dụng.
- **Application image:** thư mục ứng dụng có launcher, thư viện ứng dụng, cấu hình và runtime image đi kèm. Có thể chạy application image mà không cần cài đặt qua installer.
- **Native installer:** gói cài đặt theo định dạng của hệ điều hành. Nó cài application image vào vị trí phù hợp và có thể tích hợp menu, shortcut, metadata và uninstall.

Luồng đóng gói điển hình:

~~~text
Java source / JAR / modular application
                  |
                  v
             javac / jar
                  |
                  v
             jpackage
                  |
          +-------+--------+
          |                |
          v                v
    Application image   Native installer
          |                |
          v                v
       chạy thử        cài lên máy
                           |
                           v
                      chạy ứng dụng
~~~

jpackage có thể tạo application image trước, hoặc tạo trực tiếp native installer. Khi không truyền runtime image có sẵn, jpackage thường gọi jlink để tạo runtime phù hợp với ứng dụng. Có thể truyền runtime image đã được tạo trước bằng tùy chọn --runtime-image.

Application image hữu ích để kiểm thử và triển khai dạng thư mục. Native installer phù hợp khi cần trải nghiệm cài đặt quen thuộc cho người dùng cuối.

## 2. Định dạng gói theo hệ điều hành

Các loại package chính:

| Nền tảng | Định dạng | Mục đích |
|---|---|---|
| Windows | exe | Installer thực thi của Windows |
| Windows | msi | Windows Installer package |
| Linux | deb | Gói cho hệ sinh thái Debian/Ubuntu |
| Linux | rpm | Gói cho hệ sinh thái RPM như Fedora/RHEL |
| macOS | pkg | Gói cài đặt macOS |
| macOS | dmg | Disk image chứa ứng dụng hoặc gói cài đặt |
| Mọi nền tảng được hỗ trợ | app-image | Application image dạng thư mục hoặc bundle |

Tên và khả năng tạo package phụ thuộc hệ điều hành nơi chạy jpackage. jpackage không phải công cụ cross-compile installer tổng quát: thông thường phải build gói Windows trên Windows, gói macOS trên macOS và gói Linux trên Linux.

Application image cũng gắn với nền tảng vì runtime chứa thư viện native và executable phù hợp với hệ điều hành/kiến trúc. Không sao chép image Linux sang Windows rồi kỳ vọng nó chạy như một ứng dụng Windows.

### Windows

Có thể tạo MSI:

~~~bash
jpackage --type msi --name HelloDesk --input build/input --main-jar hello.jar --dest build/installers
~~~

Hoặc EXE:

~~~bash
jpackage --type exe --name HelloDesk --input build/input --main-jar hello.jar --dest build/installers
~~~

Tùy chọn thường dùng:

- **--win-menu:** tạo shortcut trong Start Menu.
- **--win-shortcut:** tạo shortcut trên desktop.
- **--win-menu-group:** đặt tên nhóm trong Start Menu.
- **--win-dir-chooser:** cho phép chọn thư mục cài đặt.
- **--win-upgrade-uuid:** định danh nâng cấp ổn định giữa các phiên bản của cùng ứng dụng.

Đối với MSI, máy build cần bộ công cụ đóng gói Windows mà phiên bản JDK đang dùng yêu cầu, thường là WiX Toolset. Hãy kiểm tra tài liệu jpackage của đúng JDK để biết phiên bản và điều kiện cài đặt.

### Linux

Tạo DEB:

~~~bash
jpackage --type deb --name hellodesk --input build/input --main-jar hello.jar --dest build/installers
~~~

Tạo RPM:

~~~bash
jpackage --type rpm --name hellodesk --input build/input --main-jar hello.jar --dest build/installers
~~~

Một số tùy chọn Linux:

- **--linux-package-name:** tên package trong hệ thống quản lý package.
- **--linux-deb-maintainer:** thông tin maintainer của DEB.
- **--linux-rpm-license-type:** loại license trong metadata RPM.
- **--linux-app-category:** category ứng dụng.
- **--linux-shortcut:** tạo shortcut desktop khi môi trường hỗ trợ.
- **--linux-package-deps:** khai báo package dependency ở cấp hệ điều hành nếu cần.

Để tạo DEB hoặc RPM, máy build cần công cụ đóng gói tương ứng. Ví dụ môi trường DEB thường dùng các công cụ của hệ sinh thái dpkg; môi trường RPM cần công cụ build RPM. Tên package, dependency và metadata nên tuân theo quy ước của bản phân phối Linux mục tiêu.

### macOS

Có thể tạo PKG:

~~~bash
jpackage --type pkg --name HelloDesk --input build/input --main-jar hello.jar --dest build/installers --mac-package-identifier com.example.hellodesk
~~~

Hoặc DMG:

~~~bash
jpackage --type dmg --name HelloDesk --input build/input --main-jar hello.jar --dest build/installers
~~~

Một số tùy chọn macOS:

- **--mac-package-identifier:** định danh package dạng reverse-domain.
- **--mac-package-name:** tên package hiển thị.
- **--mac-sign:** yêu cầu ký ứng dụng theo cấu hình ký của jpackage.
- **--mac-signing-key-user-name:** danh tính chứng thư ký.
- **--mac-signing-keychain:** keychain chứa chứng thư.
- **--mac-entitlements:** file entitlements dùng khi ký trong các trường hợp phù hợp.

Tạo gói macOS thường cần công cụ hệ thống của Apple và môi trường ký phù hợp nếu phân phối ra ngoài. Với ứng dụng phát hành công khai, cần tìm hiểu quy trình Developer ID signing và notarization của Apple; việc tạo PKG/DMG không tự bảo đảm ứng dụng đã được notarize.

## 3. Cú pháp và các tùy chọn chung của jpackage

Cú pháp tổng quát:

~~~bash
jpackage [options]
~~~

Những tùy chọn thường gặp:

| Tùy chọn | Chức năng |
|---|---|
| --type | Loại đầu ra: app-image, exe, msi, deb, rpm, pkg hoặc dmg tùy nền tảng |
| --name | Tên ứng dụng |
| --input | Thư mục chứa các file đầu vào để đóng gói |
| --dest | Thư mục chứa kết quả |
| --main-jar | JAR chính của ứng dụng không modular |
| --main-class | Main class của ứng dụng |
| --module | Module và main class của ứng dụng modular |
| --module-path | Nơi tìm các module |
| --runtime-image | Runtime image đã tạo sẵn |
| --add-modules | Các module cần thêm vào runtime image |
| --jlink-options | Các tùy chọn chuyển cho jlink khi tạo runtime |
| --app-version | Phiên bản ứng dụng |
| --vendor | Nhà cung cấp ứng dụng |
| --description | Mô tả ứng dụng |
| --copyright | Thông tin bản quyền |
| --license-file | File license được đưa vào package |
| --icon | Icon của ứng dụng hoặc installer nếu nền tảng hỗ trợ |
| --resource-dir | Thư mục chứa tài nguyên tùy chỉnh cho bộ đóng gói |
| --verbose | Hiển thị log chi tiết |

Các tùy chọn cụ thể và khả năng hỗ trợ có thể khác theo phiên bản JDK. Chạy lệnh sau để xem trợ giúp trên máy build:

~~~bash
jpackage --help
~~~

Để xem tùy chọn của một loại package:

~~~bash
jpackage --type msi --help
~~~

Nếu nền tảng không hỗ trợ loại package được yêu cầu, jpackage sẽ báo lỗi. Luôn xác nhận danh sách tùy chọn của đúng JDK và hệ điều hành dùng để build.

## 4. Đóng gói ứng dụng không modular

Ứng dụng không modular thường được đóng gói từ một JAR chính cùng các thư viện phụ thuộc.

Với dạng này, thường dùng:

- **--input:** thư mục chứa JAR chính và các dependency cần đóng gói.
- **--main-jar:** tên JAR chính tương đối với input directory.
- **--main-class:** tên đầy đủ của lớp có main method, nếu không muốn dựa vào Main-Class trong manifest.

Ví dụ:

~~~bash
jpackage \
    --type app-image \
    --name HelloDesk \
    --input build/input \
    --main-jar hello.jar \
    --main-class com.example.hello.Main \
    --dest build/app-image
~~~

Nếu JAR đã có manifest Main-Class hợp lệ, có thể bỏ --main-class. Trong quy trình build ổn định, nên xác nhận manifest hoặc chỉ định main class tường minh.

Các dependency JAR khác cần có trong input directory và phải được cấu hình để launcher tìm thấy. Nếu ứng dụng dùng classpath phức tạp, kiểm tra file cấu hình launcher trong application image sau khi đóng gói và thử chạy trên máy sạch.

## 5. Đóng gói ứng dụng modular

Ứng dụng modular dùng module descriptor và module path.

Cú pháp:

~~~bash
jpackage \
    --type app-image \
    --name Greeter \
    --module-path mlib \
    --module com.example.greeter/com.example.greeter.Main \
    --dest build/app-image
~~~

Trong đó:

- **--module-path mlib:** nơi chứa modular JAR hoặc exploded modules.
- **--module com.example.greeter/com.example.greeter.Main:** module và main class cần chạy.
- **--name Greeter:** tên application image.
- **--dest:** nơi ghi image.

Nếu module descriptor đã khai báo Main-Class thông qua ModuleMainClass attribute, có thể không cần ghi main class trong một số trường hợp; tuy nhiên, chỉ định rõ module/main class giúp cấu hình dễ đọc và dễ kiểm tra.

Với modular application, jpackage dùng module graph để xác định dependency. Nếu cần thêm module runtime cụ thể, có thể dùng --add-modules. Không đưa automatic module hoặc JAR classpath tùy ý vào module path rồi giả định jlink sẽ liên kết được chúng.

## 6. Runtime image đi kèm ứng dụng

Một native installer có thể chứa runtime Java riêng. Đây là điểm quan trọng giúp người dùng cài ứng dụng mà không cần cài JDK riêng.

Có hai cách cung cấp runtime:

### Để jpackage tạo runtime

Nếu không chỉ định --runtime-image, jpackage có thể gọi jlink để tạo runtime image cho ứng dụng.

~~~bash
jpackage \
    --type app-image \
    --name HelloDesk \
    --input build/input \
    --main-jar hello.jar \
    --main-class com.example.hello.Main \
    --add-modules java.base \
    --dest build/app-image
~~~

Tùy chọn --add-modules giúp xác định module cần đưa vào runtime. Với ứng dụng dùng Swing/AWT, JDBC driver, logging hoặc các API khác, tập module cần thiết có thể lớn hơn java.base. Chọn module theo dependency thực tế và kiểm thử ứng dụng sau khi tạo image.

jpackage có thể dùng jlink options để điều chỉnh runtime image. Ví dụ:

~~~bash
jpackage \
    --type app-image \
    --name HelloDesk \
    --input build/input \
    --main-jar hello.jar \
    --main-class com.example.hello.Main \
    --jlink-options "--strip-debug --no-header-files --no-man-pages" \
    --dest build/app-image
~~~

Các tùy chọn jlink hợp lệ phụ thuộc JDK. Nếu truyền option không được hỗ trợ, quá trình tạo image sẽ thất bại.

### Cung cấp runtime image có sẵn

Nếu đã tạo runtime bằng jlink, có thể truyền:

~~~bash
jpackage \
    --type app-image \
    --name HelloDesk \
    --input build/input \
    --main-jar hello.jar \
    --main-class com.example.hello.Main \
    --runtime-image build/runtime \
    --dest build/app-image
~~~

Khi dùng --runtime-image, jpackage đóng gói runtime đã có thay vì tự tạo runtime mới. Runtime image phải phù hợp với nền tảng đích và chứa đủ module ứng dụng cần.

Không đưa runtime image của một hệ điều hành vào installer cho hệ điều hành khác. Hãy build và kiểm thử riêng cho từng nền tảng.

## 7. Launcher và cấu hình chạy ứng dụng

jpackage tạo launcher cho ứng dụng. Launcher thường nằm trong application image và được installer cài cùng ứng dụng.

Một số tùy chọn điều khiển launcher:

- **--arguments:** đối số mặc định truyền cho main class khi người dùng khởi chạy ứng dụng.
- **--java-options:** tùy chọn truyền cho JVM, ví dụ heap hoặc system property.
- **--add-launcher:** thêm launcher khác với cấu hình riêng.
- **--icon:** icon launcher nếu nền tảng hỗ trợ.

Ví dụ:

~~~bash
jpackage \
    --type app-image \
    --name HelloDesk \
    --input build/input \
    --main-jar hello.jar \
    --main-class com.example.hello.Main \
    --arguments "production" \
    --java-options "-Xmx512m" \
    --java-options "-Dapp.profile=production" \
    --dest build/app-image
~~~

Các đối số ứng dụng được chuyển cho String[] args. Các java options được áp dụng cho JVM trước khi chạy main class.

Không nhầm --arguments với --java-options. Một giá trị như production là đối số ứng dụng; -Xmx512m là tùy chọn JVM.

### Nhiều launcher

Có thể thêm launcher thứ hai bằng --add-launcher:

~~~bash
jpackage \
    --type app-image \
    --name HelloDesk \
    --input build/input \
    --main-jar hello.jar \
    --main-class com.example.hello.Main \
    --add-launcher diagnostics=build/diagnostics.properties \
    --dest build/app-image
~~~

File diagnostics.properties chứa cấu hình launcher bổ sung, ví dụ main-jar, main-class, module, arguments, java-options hoặc icon theo cấu hình được jpackage hỗ trợ. Các thuộc tính hợp lệ và cách ghi cần đối chiếu với jpackage --help của JDK đang dùng.

Nhiều launcher hữu ích khi cùng một application image cần nhiều entry point như ứng dụng chính, công cụ quản trị hoặc chế độ chẩn đoán. Mỗi launcher cần trỏ tới entry point hợp lệ và các dependency tương ứng phải có trong image.

## 8. Metadata, icon, license và file association

Installer cần metadata để hiển thị tên, phiên bản, nhà cung cấp và thông tin hỗ trợ.

Ví dụ:

~~~bash
jpackage \
    --type app-image \
    --name HelloDesk \
    --app-version 1.2.0 \
    --vendor "Example Company" \
    --description "Desktop greeting application" \
    --copyright "Copyright 2026 Example Company" \
    --input build/input \
    --main-jar hello.jar \
    --main-class com.example.hello.Main \
    --dest build/app-image
~~~

Các trường metadata có thể được hiển thị trong trình cài đặt hoặc hệ điều hành tùy nền tảng.

### Icon

Dùng --icon để chỉ định file icon phù hợp với hệ điều hành. Định dạng được chấp nhận phụ thuộc nền tảng; ví dụ Windows thường dùng ICO, macOS dùng ICNS và Linux có thể dùng PNG.

~~~bash
jpackage --type app-image --name HelloDesk --icon src/packaging/hellodesk.png ...
~~~

Đường dẫn icon phải tồn tại trên máy build. Kiểm tra icon hiển thị trong application image và installer thực tế.

### License

Dùng --license-file để đính kèm file license trong gói nếu loại package hỗ trợ.

~~~bash
jpackage --type msi --name HelloDesk --license-file packaging/LICENSE.rtf ...
~~~

Định dạng license hoặc cách trình cài đặt hiển thị license có thể phụ thuộc nền tảng. Hãy kiểm tra gói cuối cùng.

### File association

jpackage hỗ trợ cấu hình file association qua file properties được truyền bằng --file-associations. Cấu hình có thể mô tả extension, MIME type, mô tả và icon tương ứng.

File association có thể làm thay đổi hành vi hệ điều hành khi người dùng mở một loại file. Hãy chỉ đăng ký association thực sự thuộc ứng dụng và kiểm thử cả cài đặt, cập nhật lẫn gỡ cài đặt.

## 9. Ví dụ thực hành Java 17+: tạo application image và installer

Ví dụ tạo ứng dụng HelloDesk đơn giản từ JAR không modular. Sau đó dùng jpackage tạo application image và native installer.

Cấu trúc source:

~~~text
jpackage-demo/
└── src/
    └── com/
        └── example/
            └── hello/
                └── Main.java
~~~

### Bước 1: viết ứng dụng

Tạo src/com/example/hello/Main.java:

~~~java
package com.example.hello;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("Hello from HelloDesk.");

        if (args.length > 0) {
            System.out.println("profile=" + args[0]);
        }
    }
}
~~~

Chương trình in lời chào và in đối số đầu tiên nếu có.

### Bước 2: biên dịch bằng Java 17

Từ thư mục gốc jpackage-demo:

~~~bash
mkdir -p build/classes build/input
javac --release 17 -d build/classes src/com/example/hello/Main.java
~~~

Trên PowerShell:

~~~powershell
New-Item -ItemType Directory -Force -Path "build/classes" | Out-Null
New-Item -ItemType Directory -Force -Path "build/input" | Out-Null
javac --release 17 -d "build/classes" "src/com/example/hello/Main.java"
~~~

### Bước 3: tạo JAR có Main-Class

~~~bash
jar --create \
    --file build/input/hello.jar \
    --main-class com.example.hello.Main \
    -C build/classes .
~~~

Kiểm tra manifest nếu cần:

~~~bash
jar --describe-module --file build/input/hello.jar
~~~

JAR không modular có thể được mô tả như automatic module khi dùng module path, nhưng trong ví dụ này ta sử dụng --main-jar nên không cần chuyển nó thành named module.

### Bước 4: tạo application image

~~~bash
jpackage \
    --type app-image \
    --name HelloDesk \
    --app-version 1.0.0 \
    --vendor "Example Company" \
    --input build/input \
    --main-jar hello.jar \
    --main-class com.example.hello.Main \
    --arguments "production" \
    --dest build/app-image
~~~

jpackage tạo application image trong build/app-image. Image chứa launcher, ứng dụng và runtime được đóng gói theo cấu hình của jpackage.

Vị trí và phần mở rộng launcher bên trong image khác nhau theo nền tảng. Trên Windows, launcher thường là file .exe; trên Linux là executable; trên macOS application image có thể là bundle .app.

### Bước 5: kiểm thử application image

Chạy launcher được tạo trong image. Trên Linux, đường dẫn thường có dạng:

~~~bash
./build/app-image/HelloDesk/bin/HelloDesk
~~~

Trên Windows, launcher thường có dạng:

~~~powershell
.\build\app-image\HelloDesk\HelloDesk.exe
~~~

Trên macOS, mở application bundle được tạo trong thư mục đích hoặc chạy executable bên trong bundle theo cấu trúc image.

Output:

~~~text
Hello from HelloDesk.
profile=production
~~~

Nếu không thấy output, kiểm tra launcher, file cấu hình, main class, input JAR và runtime image. Một số ứng dụng GUI không mở console nên không hiển thị stdout như ví dụ CLI.

### Bước 6: tạo native installer trên Windows

Trên Windows, chạy:

~~~powershell
jpackage --type msi --name HelloDesk --app-version 1.0.0 --vendor "Example Company" --input "build/input" --main-jar "hello.jar" --main-class "com.example.hello.Main" --win-menu --win-shortcut --dest "build/installers"
~~~

Nếu cần EXE installer:

~~~powershell
jpackage --type exe --name HelloDesk --app-version 1.0.0 --input "build/input" --main-jar "hello.jar" --main-class "com.example.hello.Main" --dest "build/installers"
~~~

Tên và vị trí file installer được jpackage xác định theo tên ứng dụng, phiên bản và quy tắc nền tảng. Kiểm tra output directory sau khi build.

### Bước 7: tạo native installer trên Linux

Trên hệ thống hỗ trợ DEB:

~~~bash
jpackage --type deb --name hellodesk --app-version 1.0.0 --vendor "Example Company" --input build/input --main-jar hello.jar --main-class com.example.hello.Main --dest build/installers
~~~

Trên hệ thống hỗ trợ RPM:

~~~bash
jpackage --type rpm --name hellodesk --app-version 1.0.0 --vendor "Example Company" --input build/input --main-jar hello.jar --main-class com.example.hello.Main --dest build/installers
~~~

Chỉ tạo định dạng tương ứng với hệ sinh thái package và công cụ đóng gói có trên máy build.

### Bước 8: tạo native installer trên macOS

Tạo PKG:

~~~bash
jpackage --type pkg --name HelloDesk --app-version 1.0.0 --vendor "Example Company" --input build/input --main-jar hello.jar --main-class com.example.hello.Main --mac-package-identifier com.example.hellodesk --dest build/installers
~~~

Hoặc tạo DMG:

~~~bash
jpackage --type dmg --name HelloDesk --app-version 1.0.0 --vendor "Example Company" --input build/input --main-jar hello.jar --main-class com.example.hello.Main --dest build/installers
~~~

Các lệnh cho Windows, Linux và macOS là những lựa chọn thay thế theo nền tảng. Một máy build không tạo đồng thời installer native cho cả ba hệ điều hành chỉ bằng cách đổi --type.

## 10. Cài đặt, chạy và gỡ cài đặt

Sau khi tạo native installer, cần kiểm thử như một người dùng cuối.

### Windows

Với MSI, có thể cài qua giao diện Windows Installer hoặc dùng:

~~~powershell
msiexec /i "HelloDesk-1.0.0.msi"
~~~

Gỡ cài đặt:

~~~powershell
msiexec /x "HelloDesk-1.0.0.msi"
~~~

Tên file thực tế cần thay bằng artifact được jpackage tạo ra. Kiểm tra Start Menu, desktop shortcut, vị trí cài đặt và mục Uninstall trong Windows Settings.

### Debian/Ubuntu

Cài DEB:

~~~bash
sudo apt install ./hellodesk_1.0.0-1_amd64.deb
~~~

Gỡ cài đặt theo tên package:

~~~bash
sudo apt remove hellodesk
~~~

Tên package và tên file phụ thuộc metadata, phiên bản và kiến trúc. Không sao chép tên minh họa nếu artifact thực tế có tên khác.

### Fedora/RHEL

Cài RPM:

~~~bash
sudo dnf install ./hellodesk-1.0.0-1.x86_64.rpm
~~~

Gỡ cài đặt:

~~~bash
sudo dnf remove hellodesk
~~~

Tùy bản phân phối, lệnh package manager có thể khác. Dùng đúng công cụ của hệ điều hành đích.

### macOS

Với DMG, mở disk image và làm theo hướng dẫn bên trong. Với PKG, mở gói cài đặt hoặc dùng công cụ installer của macOS theo chính sách quản trị.

Kiểm tra ứng dụng xuất hiện đúng vị trí, mở được và có thể gỡ bỏ theo quy trình dự kiến. Đối với ứng dụng phân phối ngoài App Store, kiểm tra Gatekeeper, chữ ký và notarization trên máy sạch.

## 11. Phiên bản, nâng cấp và định danh package

Installer cần metadata ổn định để hệ điều hành nhận diện ứng dụng và xử lý nâng cấp.

- **--app-version:** phiên bản ứng dụng hiển thị trong package.
- **--name:** tên ứng dụng và thường ảnh hưởng tên artifact.
- **--vendor:** nhà cung cấp.
- **--win-upgrade-uuid:** định danh upgrade cho Windows installer; cần giữ ổn định giữa các phiên bản của cùng sản phẩm.
- **--mac-package-identifier:** định danh package macOS.
- **--linux-package-name:** tên package Linux.

Không đổi upgrade UUID giữa các phiên bản MSI nếu mục tiêu là nâng cấp cài đặt hiện có như cùng một sản phẩm. Hãy quản lý UUID trong cấu hình phát hành và kiểm thử đường nâng cấp từ phiên bản trước.

Tăng app version theo quy tắc phát hành của dự án. Kiểm tra cách nền tảng chuẩn hóa version; một số định dạng package có quy tắc riêng về số thành phần và ký tự.

Nên kiểm thử cả ba đường:

1. Cài mới trên máy chưa có ứng dụng.
2. Nâng cấp từ phiên bản trước.
3. Gỡ cài đặt và xác nhận dữ liệu người dùng được giữ hoặc xóa theo thiết kế.

Không đặt dữ liệu người dùng cần giữ lâu dài bên trong thư mục cài đặt nếu installer có thể thay thế hoặc xóa thư mục đó khi cập nhật/gỡ cài đặt.

## 12. Chữ ký số và phân phối an toàn

Native installer là artifact thực thi và cần được phát hành qua quy trình bảo mật phù hợp.

### Windows

Có thể ký installer bằng Authenticode sau khi tạo gói. Chữ ký giúp xác định nhà phát hành và phát hiện thay đổi file sau khi ký. Quy trình ký thường sử dụng chứng thư và công cụ ký của Windows SDK.

Không sửa file MSI/EXE sau khi ký; mọi thay đổi sẽ làm chữ ký mất hiệu lực. Kiểm tra chữ ký và timestamp trước khi phát hành.

### macOS

Ứng dụng macOS phân phối công khai thường cần ký bằng Developer ID phù hợp và notarize theo yêu cầu của Apple. Tùy loại package, có thể cần ký application bundle, installer package và hoàn tất notarization.

jpackage có một số tùy chọn ký macOS, nhưng việc tạo PKG/DMG tự nó không có nghĩa artifact đã được ký và notarize đúng quy trình phát hành.

### Linux

DEB/RPM có thể được phân phối qua repository được ký metadata hoặc cơ chế xác minh package của tổ chức. Bảo vệ artifact và repository, kiểm soát quyền ghi và công bố checksum/signature theo quy trình phát hành.

### Chuỗi cung ứng phần mềm

- Pin phiên bản JDK và dependency dùng để build.
- Lưu lại lệnh hoặc cấu hình jpackage.
- Kiểm tra nguồn và license của thư viện đóng gói.
- Quét dependency và artifact trước khi phát hành.
- Ký artifact cuối cùng sau khi đã hoàn tất mọi thay đổi.
- Lưu checksum và provenance build.
- Chỉ phân phối installer từ kênh chính thức.

## 13. Tích hợp vào CI/CD

Có thể tích hợp jpackage vào pipeline phát hành:

1. Checkout source và cài đúng JDK.
2. Build ứng dụng và dependency.
3. Chạy unit test.
4. Tạo JAR hoặc modular artifact.
5. Tạo application image bằng jpackage.
6. Chạy smoke test launcher.
7. Tạo native installer cho nền tảng hiện tại.
8. Kiểm tra metadata, icon, launcher và runtime.
9. Ký artifact nếu cần.
10. Cài thử trong môi trường sạch.
11. Lưu artifact, checksum và build metadata.

Dùng runner riêng cho Windows, Linux và macOS để tạo package đúng nền tảng. Có thể dùng cùng source và version, nhưng mỗi runner tạo artifact riêng.

Không build installer trên runner dùng chung với trạng thái package cũ mà không dọn output. Đặt output theo version/build number hoặc làm sạch thư mục đích trước khi tạo artifact mới.

Nên tách cấu hình package theo nền tảng trong script hoặc build tool để không vô tình truyền tùy chọn --win-* vào build Linux hay --mac-* vào build Windows.

## 14. Lỗi thường gặp và cách xử lý

**jpackage không tìm thấy main JAR**

Kiểm tra --input và --main-jar. Tên main JAR thường được tính tương đối với input directory. Bảo đảm file đã được copy vào input trước khi chạy.

**Không tìm thấy main class**

Kiểm tra manifest Main-Class hoặc chỉ định --main-class với tên đầy đủ gồm package. Đảm bảo class thực sự nằm trong JAR và có phương thức main hợp lệ.

**Không tìm thấy module**

Với modular app, kiểm tra --module-path, --module, module-info.class và dependency requires. Với app không modular, dùng --main-jar thay vì cố chạy nó như named module.

**Runtime image thiếu module**

Kiểm tra API mà ứng dụng sử dụng và các dependency. Dùng --add-modules hoặc cung cấp runtime image đã tạo với đủ module. Chạy thử trên máy không có JDK để phát hiện dependency vô tình lấy từ môi trường developer.

**Không tạo được installer native**

Kiểm tra loại package có hỗ trợ trên hệ điều hành build không và các công cụ đóng gói nền tảng đã cài chưa. Xem toàn bộ lỗi jpackage và chạy jpackage --help trên đúng JDK.

**Installer chạy nhưng launcher lỗi**

Thử chạy application image trước khi tạo installer. Kiểm tra launcher, runtime, cấu hình, file dependency và đối số mặc định.

**Icon hoặc metadata không xuất hiện**

Kiểm tra đường dẫn resource, định dạng icon và tùy chọn đúng nền tảng. Kiểm tra package sau khi tạo vì một số metadata hiển thị khác nhau giữa hệ điều hành.

**Package manager không nhận dependency**

Khai báo dependency ở đúng tầng: Java module dependency trong module graph và OS package dependency trong metadata package. Hai loại dependency này khác nhau.

**Installer không nâng cấp đúng**

Kiểm tra app version, package identifier và upgrade UUID trên Windows. Thử nâng cấp từ đúng loại package phiên bản trước và xác nhận dữ liệu người dùng.

**Ứng dụng bị cảnh báo bảo mật**

Kiểm tra chữ ký số, certificate chain, timestamp, notarization và nguồn phân phối. Không bỏ qua cảnh báo bằng cách hướng dẫn người dùng tắt cơ chế bảo vệ của hệ điều hành.

## 15. Checklist trước khi phát hành native installer

- [ ] Ứng dụng khởi chạy được từ JAR hoặc module trước khi đóng gói.
- [ ] Main class/module được cấu hình chính xác.
- [ ] Tất cả dependency và resource cần thiết có trong input hoặc runtime.
- [ ] Runtime image có đúng module và phiên bản Java.
- [ ] Application image chạy được trên nền tảng đích.
- [ ] Native installer được tạo trên đúng hệ điều hành.
- [ ] Metadata, version, vendor, icon và license chính xác.
- [ ] Shortcut, menu và file association hoạt động như dự kiến.
- [ ] Cài mới, nâng cấp và gỡ cài đặt đã được kiểm thử.
- [ ] Chữ ký và notarization đã hoàn tất khi cần.
- [ ] Installer đã được thử trên máy sạch không cài JDK.
- [ ] Checksum và provenance build được lưu cùng artifact.

## 16. Quy trình ngắn gọn cần nhớ

~~~bash
# Compile application
javac --release 17 -d build/classes src/com/example/hello/Main.java

# Create input JAR
jar --create --file build/input/hello.jar \
    --main-class com.example.hello.Main \
    -C build/classes .

# Create an application image first
jpackage --type app-image \
    --name HelloDesk \
    --input build/input \
    --main-jar hello.jar \
    --main-class com.example.hello.Main \
    --dest build/app-image

# Create a native installer on the target OS
jpackage --type <platform-package> \
    --name HelloDesk \
    --input build/input \
    --main-jar hello.jar \
    --main-class com.example.hello.Main \
    --dest build/installers
~~~

Thay <platform-package> bằng loại phù hợp: msi hoặc exe trên Windows, deb hoặc rpm trên Linux, pkg hoặc dmg trên macOS. Tùy chọn và công cụ đóng gói cần thiết phụ thuộc nền tảng.

jpackage giúp biến ứng dụng Java thành application image hoặc native installer có thể phân phối cho người dùng cuối. Để phát hành ổn định, cần chọn đúng package format, đưa đủ runtime và dependency, kiểm thử cài đặt/nâng cấp/gỡ cài đặt, đồng thời ký và xác minh artifact theo yêu cầu của từng hệ điều hành.

## Tài liệu tham khảo

- [The jpackage Command — Java Platform, Standard Edition](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html)
- [The jlink Command — Java Platform, Standard Edition](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html)
- [Packaging Tool User Guide — Java Platform, Standard Edition](https://docs.oracle.com/en/java/javase/26/jpackage/packaging-tool-user-guide.pdf)
