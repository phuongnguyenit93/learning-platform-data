# Tạo installer bằng jpackage cho ứng dụng Java

jpackage là công cụ đóng gói đi kèm JDK, dùng để biến ứng dụng Java đã build thành một application image có launcher và runtime riêng, hoặc thành installer native theo hệ điều hành. Người dùng có thể cài và chạy ứng dụng mà không cần tự cài Java riêng, nếu runtime image được đóng gói đầy đủ.

Quy trình đáng tin cậy gồm hai giai đoạn: tạo application image, chạy thử image đó với runtime đi kèm, rồi mới tạo installer. Application image là thư mục ứng dụng có thể chạy trực tiếp; installer như MSI, EXE, DEB, RPM, PKG hoặc DMG bổ sung trải nghiệm cài đặt của hệ điều hành. Hai loại artifact có mục đích khác nhau và cần được kiểm tra riêng.

Bài này thực hành với ứng dụng Java 17+, sau đó mở rộng sang ứng dụng nhiều JAR, modular application, runtime image tùy chỉnh, metadata, icon, shortcut, file association, signing, nâng cấp và CI đa nền tảng. Các lệnh jpackage trong bài được đối chiếu với JDK 24.0.2; tùy chọn khả dụng phụ thuộc hệ điều hành và phiên bản JDK.

## 1. jpackage tạo ra những gì?

jpackage nhận ứng dụng đã biên dịch cùng các tài nguyên cần thiết. Công cụ tạo:

- Application launcher để khởi chạy ứng dụng.
- Thư mục chứa JAR/module, cấu hình launcher và tài nguyên.
- Java runtime image được tạo bằng jlink hoặc runtime image đã chuẩn bị sẵn.
- Installer native nếu chọn loại package của hệ điều hành.

Các loại output phổ biến:

| Hệ điều hành | Installer native | Application image |
|---|---|---|
| Windows | EXE, MSI | Thư mục ứng dụng có file .exe |
| Linux | DEB, RPM | Thư mục ứng dụng có launcher |
| macOS | PKG, DMG | Bundle .app |

Trên Windows, EXE và MSI phù hợp với quy trình cài đặt quen thuộc. Trên Linux, DEB/RPM tích hợp với package manager. Trên macOS, DMG thường phân phối bundle ứng dụng để kéo vào Applications; PKG dùng quy trình cài đặt package.

jpackage không cross-compile installer. Phải chạy công cụ trên nền tảng đích: tạo EXE/MSI trên Windows, DEB/RPM trên Linux và PKG/DMG trên macOS. Nếu cần phát hành nhiều nền tảng, dùng runner riêng cho từng hệ điều hành.

## 2. Kiểm tra JDK và điều kiện đóng gói

jpackage nằm trong thư mục bin của JDK. Kiểm tra công cụ và version:

Windows PowerShell:

~~~powershell
where.exe jpackage
jpackage --version
jpackage --help
~~~

Linux/macOS:

~~~bash
command -v jpackage
jpackage --version
jpackage --help
~~~

Nên dùng JDK đã được pin trong build pipeline. Ghi lại version của java, javac, jlink và jpackage để tránh trường hợp compile bằng một JDK nhưng đóng gói bằng JDK khác mà không nhận ra.

Một số điều kiện theo nền tảng:

| Nền tảng | Điều kiện cho installer |
|---|---|
| Windows | WiX Toolset 3.0 trở lên để tạo EXE/MSI |
| Linux RPM | rpm-build trên hệ thống đóng gói RPM |
| Linux DEB | fakeroot và công cụ đóng gói Debian trên hệ thống đóng gói DEB |
| macOS | Xcode Command Line Tools khi ký bằng --mac-sign hoặc tùy chỉnh icon DMG |

Application image có thể tạo mà không cần công cụ installer native. Đây là lý do nên tạo và kiểm thử app-image trước, ngay cả khi mục tiêu cuối là MSI/DEB/DMG.

## 3. Chuẩn bị ứng dụng mẫu

Tạo cấu trúc thư mục:

~~~text
jpackage-demo/
  src/
    demo/
      Main.java
  classes/
  input/
  dist/
~~~

File src/demo/Main.java:

~~~java
package demo;

import java.util.Arrays;

public final class Main {
    private Main() {
    }

    public static void main(String[] args) {
        System.out.println("JPACKAGE_OK");
        System.out.println("args=" + Arrays.toString(args));
    }
}
~~~

Compile bằng Java 17 API và bytecode:

Windows:

~~~powershell
javac --release 17 -encoding UTF-8 -d classes src\demo\Main.java
~~~

Linux/macOS:

~~~bash
javac --release 17 -encoding UTF-8 -d classes src/demo/Main.java
~~~

Tạo JAR có Main-Class:

~~~powershell
jar --create --file input\jpackage-demo.jar --main-class demo.Main -C classes .
~~~

Trên Linux/macOS:

~~~bash
jar --create --file input/jpackage-demo.jar --main-class demo.Main -C classes .
~~~

Kiểm tra JAR:

~~~powershell
jar --list --file input\jpackage-demo.jar
~~~

JAR này là ứng dụng non-modular trên classpath. jpackage sẽ dùng main JAR và main class để tạo launcher.

## 4. Tạo application image trước

Tạo app-image trên Windows:

~~~powershell
jpackage --type app-image --name JPackageDemo --input input --main-jar jpackage-demo.jar --app-version 1.2.3 --vendor "Java Tooling Lab" --description "Java desktop packaging demo" --arguments packaged-default --win-console --dest dist
~~~

Trên Linux/macOS:

~~~bash
jpackage --type app-image --name JPackageDemo --input input --main-jar jpackage-demo.jar --app-version 1.2.3 --vendor "Java Tooling Lab" --description "Java desktop packaging demo" --arguments packaged-default --dest dist
~~~

Với app console trên Windows, thêm --win-console để launcher có console. Ứng dụng GUI thường bỏ tùy chọn này.

Sau khi chạy thành công, Windows tạo thư mục dạng:

~~~text
dist/
  JPackageDemo/
    JPackageDemo.exe
    app/
      JPackageDemo.cfg
      jpackage-demo.jar
    runtime/
      ...
~~~

Linux thường có launcher trong bin, thư mục lib/app và runtime. macOS tạo bundle JPackageDemo.app với launcher, Resources, app và runtime trong Contents.

Không dựa vào tên hoặc cấu trúc của các file nội bộ ngoài những phần được tài liệu cam kết; cấu trúc chi tiết có thể thay đổi theo JDK.

## 5. Chạy thử application image

Trên Windows:

~~~powershell
.\dist\JPackageDemo\JPackageDemo.exe
~~~

Trên Linux:

~~~bash
./dist/JPackageDemo/bin/JPackageDemo
~~~

Trên macOS:

~~~bash
open dist/JPackageDemo.app
~~~

Nếu launcher được tạo với --arguments packaged-default và người dùng không truyền argument khác, output của ứng dụng mẫu là:

~~~text
JPACKAGE_OK
args=[packaged-default]
~~~

Kiểm tra thêm:

- Launcher chạy được từ thư mục app-image.
- Ứng dụng dùng runtime nằm trong app-image.
- JAR và tài nguyên cần thiết đều có trong payload.
- Exit code và log đúng với kỳ vọng.
- Đường dẫn có khoảng trắng không làm launcher lỗi.
- Ứng dụng hoạt động khi máy thử không có JDK cài toàn hệ thống.

Ứng dụng có thể in System.getProperty("java.home") và System.getProperty("java.version") để xác nhận runtime thực tế. Trong lần kiểm thử trên JDK 24.0.2, launcher đã báo java.version=24.0.2 và java.home trỏ vào thư mục runtime bên trong application image.

## 6. Runtime đi kèm được tạo bằng jlink

Nếu không truyền --runtime-image, jpackage gọi jlink để tạo runtime image. Runtime được tạo mặc định đã loại bỏ debug symbols, native commands, man pages và header files để giảm kích thước.

Điều này có nghĩa thư mục runtime của app-image thường không có lệnh java.exe/java để chạy thủ công. Trên Windows, runtime image mặc định có thể không chứa runtime/bin/java.exe vì jlink đã dùng --strip-native-commands. Launcher do jpackage tạo vẫn chạy ứng dụng bình thường bằng JVM trong runtime image.

Vì vậy, khi kiểm thử app-image, hãy chạy launcher của ứng dụng và kiểm tra java.home từ bên trong JVM. Không kết luận runtime bị thiếu chỉ vì không tìm thấy java.exe trong thư mục runtime.

jpackage mặc định tạo runtime cho non-modular application với tập module giống môi trường classpath thông thường. Nếu ứng dụng dùng ServiceLoader hoặc cần service provider từ runtime image, hãy cân nhắc --bind-services:

~~~powershell
jpackage --type app-image --name JPackageDemo --input input --main-jar jpackage-demo.jar --jlink-options "--bind-services" --dest dist
~~~

Có thể thêm module JDK mà ứng dụng cần bằng --add-modules:

~~~powershell
jpackage --type app-image --name JPackageDemo --input input --main-jar jpackage-demo.jar --add-modules java.sql,java.net.http --dest dist
~~~

Không đoán module dựa trên import source đơn thuần. Có thể dùng jdeps --print-module-deps trên artifact để tìm dependency tĩnh, sau đó review thêm reflection, ServiceLoader, native code và cấu hình runtime.

## 7. Chọn đúng Java runtime mục tiêu

--release 17 khi compile chỉ giới hạn ngôn ngữ, bytecode và API Java SE mà source được phép dùng. Nó không buộc jpackage tạo runtime Java 17.

Nếu chạy jpackage từ JDK 24 mà không truyền runtime image riêng, runtime được tạo bởi jlink thuộc JDK 24. Application image trong ví dụ đã được kiểm thử như vậy: source compile với --release 17 nhưng runtime đi kèm là Java 24.0.2.

Nếu sản phẩm yêu cầu người dùng chạy Java 17:

1. Dùng JDK 17 để chạy jpackage, hoặc
2. Tạo runtime image từ JDK 17 bằng jlink rồi truyền qua --runtime-image.

Ví dụ tạo runtime riêng từ JDK 17:

~~~powershell
jlink --module-path "$env:JAVA_HOME\jmods" --add-modules java.base,java.desktop,java.logging --strip-debug --no-header-files --no-man-pages --output runtime-17
~~~

Lệnh này phải được chạy với JAVA_HOME trỏ tới JDK 17 và danh sách module phải phù hợp ứng dụng thực tế. Sau đó đóng gói runtime đó:

~~~powershell
jpackage --type app-image --name JPackageDemo --input input --main-jar jpackage-demo.jar --runtime-image runtime-17 --dest dist
~~~

Runtime image phải phù hợp hệ điều hành và kiến trúc đích. Không tạo runtime Windows rồi dùng làm payload cho Linux hoặc macOS.

## 8. Đóng gói ứng dụng có nhiều JAR phụ thuộc

Với ứng dụng non-modular, thư mục --input chứa main JAR và các JAR/tài nguyên phụ cần phân phối. Manifest của main JAR nên khai báo Class-Path cho các JAR phụ thuộc.

Ví dụ manifest:

~~~text
Manifest-Version: 1.0
Main-Class: demo.Main
Class-Path: helper.jar logging.jar
~~~

Đặt các file cùng thư mục input:

~~~text
input/
  app.jar
  helper.jar
  logging.jar
  config/
    default.properties
~~~

Đóng gói:

~~~powershell
jpackage --type app-image --name MultiJarDemo --input input --main-jar app.jar --dest dist
~~~

jpackage đưa các JAR được khai báo trong manifest Class-Path vào cấu hình classpath của launcher. Trong file cấu hình launcher được tạo, danh sách này xuất hiện ở thuộc tính app.classpath. Đường dẫn trong manifest là URL tương đối với JAR chính; kiểm tra chính xác tên file, chữ hoa/thường và vị trí thư mục.

Một lựa chọn khác là tạo fat/uber JAR bằng Maven Shade Plugin hoặc Gradle Shadow Plugin. Khi dùng fat JAR, kiểm tra service descriptor, resource merging, signature file và manifest sau khi đóng gói.

Không chỉ copy dependency JAR vào input rồi giả định launcher sẽ tự tìm thấy mọi file. Hãy kiểm tra file cấu hình launcher được tạo và chạy app-image trên máy sạch.

## 9. Đóng gói modular application

Ứng dụng modular có module-info.java và các module JAR/JMOD trên module path. Ví dụ:

~~~java
module com.example.jpackage {
    requires java.desktop;
    requires java.logging;
}
~~~

Giả sử main class là com.example.Main và module đã được build vào thư mục mods:

~~~powershell
jpackage --type app-image --name ModularDemo --module-path mods --module com.example.jpackage/com.example.Main --app-version 1.0.0 --dest dist
~~~

--module chỉ định module chính và có thể kèm main class. jpackage/jlink đưa module chính cùng dependency bắc cầu vào runtime image.

Nếu cần module bổ sung ngoài dependency graph, dùng --add-modules. Nếu ứng dụng dùng service provider, cân nhắc --jlink-options "--bind-services". Kiểm tra module graph và runtime bằng jdeps, jlink, rồi chạy smoke test trên image.

Không dùng đồng thời --module và --main-jar trong cùng một lệnh; hai cách khai báo ứng dụng này loại trừ nhau.

## 10. Metadata, icon và tài nguyên

Một installer chuyên nghiệp nên khai báo thông tin sản phẩm:

| Tùy chọn | Ý nghĩa |
|---|---|
| --name | Tên ứng dụng/package |
| --app-version | Version ứng dụng/package |
| --vendor | Nhà cung cấp |
| --description | Mô tả |
| --copyright | Thông tin bản quyền |
| --about-url | Trang chủ hoặc trang hỗ trợ |
| --license-file | File license |
| --icon | Icon của ứng dụng/package |
| --dest | Thư mục output |
| --resource-dir | Thư mục ghi đè resource/template mặc định |

Định dạng icon thường dùng:

- Windows: .ico.
- macOS: .icns.
- Linux: .png.

Ví dụ Windows:

~~~powershell
jpackage --type app-image --name AcmeDesk --input input --main-jar app.jar --main-class com.acme.Main --app-version 2.4.0 --vendor "Acme Example" --description "Acme desktop application" --copyright "Copyright Acme Example" --icon packaging\acme.ico --license-file LICENSE.txt --dest dist
~~~

Đặt icon và license vào source packaging được quản lý trong repository. Không dùng icon có bản quyền nếu chưa có quyền phân phối. Không đưa secret, signing key hoặc thông tin môi trường build vào resource của ứng dụng.

--app-content có thể thêm file hoặc thư mục ngoài input vào application payload. Dùng nó cho tài nguyên bổ sung khi cấu trúc input hiện tại không phù hợp.

## 11. Tạo launcher phụ và cấu hình JVM options

Một sản phẩm có thể cung cấp nhiều launcher, ví dụ ứng dụng chính và công cụ quản trị. Tạo file properties cho launcher phụ:

~~~text
main-jar=app.jar
main-class=com.acme.Main
description=Acme maintenance console
arguments=--mode=maintenance
java-options=-Xmx512m
win-console=true
~~~

Tạo thêm launcher:

~~~powershell
jpackage --type app-image --name AcmeDesk --input input --main-jar app.jar --add-launcher Maintenance=packaging\maintenance.properties --dest dist
~~~

Các key được hỗ trợ gồm module, main-jar, main-class, description, arguments, java-options, app-version, icon và một số tùy chọn nền tảng. Tên key và option khả dụng phụ thuộc JDK/OS; đối chiếu jpackage --help trước khi dùng.

--arguments đặt argument mặc định khi người dùng khởi chạy mà không truyền argument khác. --java-options truyền JVM option cho runtime. Không dùng JVM option để lưu mật khẩu, token hoặc secret.

## 12. File association

Có thể yêu cầu installer đăng ký ứng dụng mở một loại file. Tạo file properties:

~~~text
extension=acme
mime-type=application/x-acme
description=Acme project file
icon=acme-file.ico
~~~

Đóng gói:

~~~powershell
jpackage --type msi --name AcmeDesk --app-image dist\AcmeDesk --file-associations packaging\acme-file.properties --dest dist\installers
~~~

Kiểm tra extension, MIME type, icon và hành vi khi mở file. Trên Windows, file association có thể ảnh hưởng tới lựa chọn ứng dụng mặc định của người dùng; không tự ý thay đổi association nếu installer không công bố rõ hành vi.

## 13. Tạo installer MSI hoặc EXE trên Windows

Sau khi app-image đã được kiểm thử, tạo MSI:

~~~powershell
jpackage --type msi --name JPackageDemo --app-image dist\JPackageDemo --app-version 1.2.3 --vendor "Java Tooling Lab" --win-upgrade-uuid 123e4567-e89b-42d3-a456-426614174000 --win-menu --win-shortcut --win-dir-chooser --dest dist\installers
~~~

Hoặc tạo EXE installer:

~~~powershell
jpackage --type exe --name JPackageDemo --app-image dist\JPackageDemo --app-version 1.2.3 --vendor "Java Tooling Lab" --win-upgrade-uuid 123e4567-e89b-42d3-a456-426614174000 --win-menu --win-shortcut --dest dist\installers
~~~

WiX Toolset 3.0 trở lên phải được cài trên máy build để tạo Windows EXE/MSI. Cài WiX theo chính sách máy và bảo đảm công cụ có thể được jpackage tìm thấy. Máy chỉ tạo app-image không cần WiX.

Một số tùy chọn Windows:

- --win-menu tạo shortcut trong Start Menu.
- --win-menu-group đặt nhóm Start Menu.
- --win-shortcut tạo shortcut Desktop.
- --win-shortcut-prompt hỏi người dùng có muốn tạo shortcut.
- --win-dir-chooser cho phép chọn thư mục cài.
- --win-per-user-install chọn cài theo user; mặc định thường là cài cho toàn máy.
- --install-dir đặt thư mục con trong vị trí cài mặc định.
- --win-upgrade-uuid xác định danh tính upgrade của sản phẩm.

Giữ nguyên một UUID upgrade cho các phiên bản phát hành của cùng sản phẩm. Không tạo UUID mới ở mỗi lần build nếu muốn installer nhận diện bản nâng cấp. Thay đổi version theo quy tắc phát hành và kiểm tra upgrade từ phiên bản cũ trên máy thử.

## 14. Tạo DEB hoặc RPM trên Linux

Trên Debian/Ubuntu, tạo DEB:

~~~bash
jpackage --type deb --name acmedesk --input input --main-jar app.jar --main-class com.acme.Main --app-version 2.4.0 --linux-deb-maintainer packaging@example.com --linux-package-deps "libc6" --linux-menu-group Utility --linux-shortcut --dest dist
~~~

Trên hệ RPM như Fedora/RHEL, tạo RPM:

~~~bash
jpackage --type rpm --name acmedesk --input input --main-jar app.jar --main-class com.acme.Main --app-version 2.4.0 --linux-rpm-license-type MIT --linux-app-release 1 --linux-app-category Applications/Utilities --dest dist
~~~

Máy build RPM cần rpm-build; môi trường Ubuntu tạo DEB cần fakeroot theo yêu cầu của nền tảng đóng gói. Tên dependency, category, license type và maintainer phải phù hợp chính sách phân phối thực tế.

Có thể dùng --linux-package-deps để khai báo package hệ điều hành mà ứng dụng cần. Đừng khai báo dependency hệ thống tùy tiện; kiểm tra package name trên từng bản phân phối mục tiêu.

## 15. Tạo PKG hoặc DMG trên macOS

Tạo DMG:

~~~bash
jpackage --type dmg --name AcmeDesk --input input --main-jar app.jar --main-class com.acme.Main --app-version 2.4.0 --mac-package-identifier com.acme.desk --icon packaging/AcmeDesk.icns --dest dist
~~~

Tạo PKG bằng cách đổi --type dmg thành --type pkg. --mac-package-identifier nên ổn định qua các phiên bản; đây là identifier duy nhất của ứng dụng trên macOS.

Khi phân phối ngoài Mac App Store, ký ứng dụng/package bằng certificate phù hợp. jpackage hỗ trợ --mac-sign cùng --mac-signing-key-user-name và các tùy chọn signing liên quan. Xcode Command Line Tools cần thiết cho quy trình ký này và một số thao tác tùy chỉnh DMG.

Sau khi ký, quy trình phát hành ngoài App Store thường còn cần notarization bằng Apple notary service và stapling ticket. Ví dụ với profile đã cấu hình trong Keychain:

~~~bash
xcrun notarytool submit dist/AcmeDesk.dmg --keychain-profile ACME_NOTARY --wait
xcrun stapler staple dist/AcmeDesk.dmg
~~~

Tên signing identity, keychain profile và entitlement phải đến từ tài khoản phát hành thật. Không ghi certificate private key hoặc thông tin xác thực vào repository.

## 16. Ký installer trên Windows

Windows installer nên được ký Authenticode trước khi phân phối rộng. Với Windows SDK, signtool có thể ký EXE/MSI và xác minh chữ ký:

~~~powershell
signtool sign /fd SHA256 /tr TIMESTAMP_SERVER /td SHA256 /a dist\installers\JPackageDemo-1.2.3.msi
signtool verify /pa /v dist\installers\JPackageDemo-1.2.3.msi
~~~

Thay TIMESTAMP_SERVER bằng timestamp service do tổ chức hoặc nhà cung cấp certificate sử dụng. Có thể ký file EXE và MSI riêng nếu phát hành cả hai.

Chứng thư nên được lưu trong certificate store hoặc secret manager của CI. Giới hạn quyền truy cập signing identity, không commit PFX/password và ghi log kết quả verify. Kiểm tra chữ ký sau khi mọi bước sửa đổi artifact đã hoàn tất.

## 17. Cài đặt, nâng cấp và gỡ cài đặt

Tạo installer thành công chưa chứng minh trải nghiệm cài đặt đúng. Cần kiểm tra:

1. Cài mới trên máy sạch.
2. Chạy ứng dụng từ Start Menu/Desktop hoặc menu ứng dụng.
3. Kiểm tra runtime đi kèm và file tài nguyên.
4. Nâng cấp từ phiên bản cũ.
5. Kiểm tra shortcut và file association sau nâng cấp.
6. Gỡ cài đặt và xác nhận file ứng dụng được dọn đúng.
7. Kiểm tra dữ liệu người dùng có được giữ theo chính sách hay không.
8. Cài đặt với tài khoản user thường và tài khoản quản trị nếu hỗ trợ cả hai.

Không lưu dữ liệu người dùng trong thư mục cài đặt có thể bị installer ghi đè hoặc gỡ bỏ. Dùng user home/AppData hoặc vị trí dữ liệu ứng dụng phù hợp hệ điều hành. Quy định rõ uninstall có xóa dữ liệu người dùng hay giữ lại.

Đối với Windows, giữ ổn định upgrade UUID. Với Linux, package name và version phải nhất quán để package manager nhận diện nâng cấp. Với macOS, kiểm tra bundle identifier và signing identity qua các bản phát hành.

## 18. Kiểm thử trên máy sạch và trong CI

CI nên build artifact trên runner của từng hệ điều hành đích. Ví dụ chiến lược:

| Giai đoạn | Kiểm tra |
|---|---|
| Build | Compile, unit test, package JAR/module |
| App image | Chạy launcher, kiểm tra runtime, arguments và resources |
| Installer | Tạo MSI/EXE, DEB/RPM hoặc PKG/DMG |
| Install test | Cài trên máy/VM sạch và chạy ứng dụng |
| Upgrade test | Cài bản cũ, nâng lên bản mới và kiểm tra dữ liệu |
| Security | Verify chữ ký, certificate chain và timestamp |
| Release | Lưu checksum, version, build log và installer |

Không tạo installer Windows trên runner Linux bằng cách truyền --type msi; jpackage không cross-compile. Dùng Windows runner với WiX, Linux runner với package prerequisites phù hợp và macOS runner cho PKG/DMG.

Lưu lại JDK version, jpackage command, OS image, architecture, dependency lock và checksum của artifact. Có thể tạo SHA-256:

Windows:

~~~powershell
Get-FileHash dist\installers\JPackageDemo-1.2.3.msi -Algorithm SHA256
~~~

Linux/macOS:

~~~bash
shasum -a 256 dist/installers/*
~~~

## 19. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| jpackage không tìm thấy JDK tools | PATH/JAVA_HOME trỏ sai hoặc dùng JRE | Dùng JDK đầy đủ và kiểm tra jpackage/jlink |
| Không tạo được MSI/EXE | Thiếu WiX hoặc WiX không được tìm thấy | Cài WiX Toolset và kiểm tra PATH |
| App image tạo được nhưng launcher lỗi | Main class/JAR hoặc classpath sai | Kiểm tra --main-jar, --main-class và manifest |
| ClassNotFoundException | Thiếu JAR dependency trong payload/classpath | Bổ sung JAR và manifest Class-Path |
| NoClassDefFoundError khi chạy | Dependency runtime hoặc service provider bị thiếu | Kiểm tra module, Class-Path và --bind-services |
| Không tìm thấy java.exe trong runtime | Runtime mặc định đã strip native commands | Chạy application launcher và kiểm tra java.home |
| App lỗi trên Java cũ | Runtime image được tạo từ JDK mới hơn | Dùng jpackage/runtime image từ JDK mục tiêu |
| Không thấy icon mới | Sai định dạng hoặc path icon | Dùng .ico/.icns/.png đúng OS và rebuild image |
| ServiceLoader không tìm provider | jlink runtime chưa bind service provider | Thử --jlink-options "--bind-services" |
| Installer upgrade tạo bản cài riêng | Upgrade identity/version không ổn định | Giữ upgrade UUID và package identity |
| App chạy local nhưng lỗi trên máy sạch | Thiếu native dependency, config hoặc resource | Test app-image trên VM sạch của OS đích |
| Chữ ký không hợp lệ | Ký trước khi thay đổi artifact hoặc certificate sai | Ký sau cùng và verify lại |

## 20. Checklist phát hành bằng jpackage

- [ ] JDK và jpackage version đã được pin.
- [ ] Ứng dụng đã build và test trước khi đóng gói.
- [ ] Main JAR/class hoặc module đã được khai báo đúng.
- [ ] Tất cả dependency và resource cần thiết có trong payload.
- [ ] Manifest Class-Path hoặc module path đã được kiểm tra.
- [ ] Runtime image phù hợp Java version tối thiểu.
- [ ] Service provider và module bổ sung đã được xem xét.
- [ ] App-image đã chạy thành công trên máy sạch.
- [ ] Metadata, version, vendor, icon và license đúng.
- [ ] Installer được tạo trên đúng OS/architecture.
- [ ] Windows WiX hoặc Linux/macOS packaging prerequisites đã sẵn sàng.
- [ ] Shortcut, menu, file association và install directory đã được thử.
- [ ] Upgrade, uninstall và dữ liệu người dùng đã được kiểm tra.
- [ ] Installer đã được ký và xác minh nếu cần.
- [ ] CI lưu checksum, log và version của toolchain.

jpackage giúp phân phối ứng dụng Java như phần mềm desktop native, đồng thời đóng gói runtime để người dùng không phải tự cài Java. Hãy kiểm thử application image trước, chọn đúng runtime version, xác minh dependency và service provider, rồi tạo installer trên đúng hệ điều hành. Chất lượng phát hành được quyết định bởi cả launcher, runtime, installer, signing, upgrade và uninstall chứ không chỉ bởi việc lệnh jpackage kết thúc thành công.

## Tài liệu tham khảo

- Oracle Java SE 24 — Packaging Overview: https://docs.oracle.com/en/java/javase/24/jpackage/packaging-overview.html
- Oracle Java SE 24 — The jpackage Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jpackage.html
- Oracle Java SE 24 — Support Application Requirements: https://docs.oracle.com/en/java/javase/24/jpackage/support-application-features.html
- Oracle Java SE 24 — The jlink Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jlink.html
- Oracle Java SE 24 — The jar Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html
- Microsoft — SignTool: https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool
- Apple — Notarizing macOS Software: https://developer.apple.com/documentation/security/notarizing-macos-software-before-distribution
