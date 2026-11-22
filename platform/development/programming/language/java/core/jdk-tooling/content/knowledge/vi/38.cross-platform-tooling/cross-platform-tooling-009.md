# Native package cho ứng dụng Java

## 1. Native package là gì?

**Native package** là gói phân phối ứng dụng theo định dạng quen thuộc của hệ điều hành: bộ cài Windows, gói Debian/RPM hoặc disk image macOS. Người dùng có thể cài đặt, mở ứng dụng từ menu và gỡ cài đặt theo cách thông thường của nền tảng.

Trong JDK, công cụ chính cho công việc này là jpackage. Công cụ nhận JAR hoặc module Java, tạo application image và có thể tạo installer theo OS. Application image thường chứa launcher, file ứng dụng và một Java runtime riêng. Người dùng không cần cài JDK hoặc cấu hình JAVA_HOME để chạy ứng dụng đã đóng gói.

Launcher do jpackage tạo vẫn chạy bytecode Java trên JVM được đóng gói cùng ứng dụng. Nó tạo trải nghiệm cài đặt native, nhưng không biên dịch Java bytecode thành mã máy.

## 2. Phân biệt app image, native installer và native executable

| Kết quả | Ví dụ | Ý nghĩa |
|---|---|---|
| Application image | Thư mục ứng dụng có launcher và runtime | Có thể chạy trực tiếp hoặc dùng làm đầu vào tạo installer |
| Native installer/package | .msi, .exe, .deb, .rpm, .pkg, .dmg | Cài đặt, đăng ký shortcut/menu, hỗ trợ gỡ cài đặt theo OS |
| Native executable (AOT) | Binary do GraalVM tạo | Java được phân tích và biên dịch ahead-of-time thành executable native |

jpackage tạo hai loại đầu: application image và native installer. GraalVM Native Image là công nghệ riêng để tạo executable AOT. Một file .exe do jpackage tạo không tự động là GraalVM Native Image.

## 3. Công cụ trong JDK

| Công cụ | Vai trò |
|---|---|
| javac | Biên dịch source Java thành class file |
| jar | Đóng gói class và resource thành JAR |
| jdeps | Phân tích dependency giữa class/JAR và module JDK |
| jlink | Tạo custom Java runtime image từ module JDK và dependency bắc cầu |
| jpackage | Tạo application image hoặc installer theo nền tảng |

jpackage được đưa vào JDK 14 dưới dạng incubating và trở thành công cụ chuẩn từ JDK 16. Nó có trong JDK, không có trong JRE riêng. Kiểm tra phiên bản:

~~~bash
java --version
javac --version
jpackage --version
jlink --version
jdeps --version
~~~

Dùng JDK cùng hệ điều hành và kiến trúc với gói cần phát hành. Không dùng jpackage trên Windows để tạo trực tiếp installer macOS hoặc Linux.

## 4. Các định dạng theo hệ điều hành

JDK 24 hỗ trợ:

| Hệ điều hành | Application image | Native installer/package |
|---|---|---|
| Windows | Thư mục có launcher EXE và runtime | EXE, MSI |
| Linux | Thư mục có launcher trong bin/ và runtime | DEB, RPM |
| macOS | Bundle .app | DMG, PKG |

app-image dùng để thử ứng dụng hoặc chuyển một thư mục self-contained cho người dùng. Nó không tạo quy trình cài đặt, menu và gỡ cài đặt như installer.

Mỗi package phải được tạo trên nền tảng đích. Nếu phát hành Windows, Linux và macOS, pipeline cần runner tương ứng và chạy jpackage riêng trên từng runner. Muốn tạo nhiều định dạng trên cùng OS, chạy lệnh riêng cho từng định dạng.

## 5. Chuẩn bị ứng dụng trước khi đóng gói

Trước khi chạy jpackage, hãy tạo JAR có thể chạy hoặc module Java đã được build. Một ứng dụng thông thường cần:

- JAR chính chứa main class.
- Các JAR dependency và resource mà ứng dụng cần lúc chạy.
- Tên ứng dụng, version, vendor, description và copyright.
- Icon đúng định dạng của nền tảng nếu muốn dùng icon riêng.
- Các JVM option và application argument cần thiết.
- License, file association, shortcut hoặc launcher phụ nếu sản phẩm yêu cầu.

Với Maven:

~~~bash
mvn -B -ntp clean package
~~~

Với Gradle:

~~~bash
./gradlew clean build
~~~

Đưa JAR chính và các dependency cần thiết vào thư mục input của jpackage. Với ứng dụng classpath, dùng --input trỏ tới thư mục chứa file và --main-jar để chỉ JAR khởi chạy. --main-class chỉ cần khi manifest của JAR chưa khai báo main class.

Với ứng dụng modular, dùng --module-path và --module. Không truyền đồng thời --module và --main-jar.

## 6. Application image được tạo ra gồm những gì?

Một application image điển hình chứa ba phần:

- **Launcher:** file thực thi để người dùng mở ứng dụng.
- **Application payload:** JAR, resource và cấu hình launcher.
- **Runtime:** Java runtime image được đóng gói cùng ứng dụng.

Cấu trúc Windows minh họa:

~~~text
NativePackageDemo/
  NativePackageDemo.exe
  app/
    NativePackageDemo.cfg
    NativePackageDemo.jar
  runtime/
    bin/
    conf/
    lib/
~~~

Trên Linux, launcher thường nằm trong bin/. Trên macOS, application image là bundle .app có cấu trúc Contents/. Tên và một số file nội bộ có thể thay đổi theo JDK; không nên viết script phụ thuộc vào file implementation không được tài liệu cam kết.

Người dùng chạy launcher của image. Không yêu cầu họ chạy java -jar hoặc cài JDK riêng.

## 7. Đóng gói ứng dụng non-modular bằng jpackage

Ví dụ này dùng chương trình Java nhỏ, không có dependency bên ngoài.

Tạo file src/demo/NativePackageDemo.java:

~~~java
package demo;

public final class NativePackageDemo {
    public static void main(String[] args) {
        System.out.println("READY Native package");
    }
}
~~~

Biên dịch bằng JDK 17 trở lên:

~~~bash
javac --release 17 -d classes src/demo/NativePackageDemo.java
~~~

Tạo thư mục input và đóng gói JAR:

~~~bash
mkdir input
jar --create --file input/NativePackageDemo.jar --main-class demo.NativePackageDemo -C classes .
~~~

Tạo application image trên Windows:

~~~powershell
jpackage --type app-image --name NativePackageDemo --input input --main-jar NativePackageDemo.jar --main-class demo.NativePackageDemo --dest dist --app-version 1.0.0 --vendor Example --win-console
~~~

Chạy launcher được tạo:

~~~powershell
.\dist\NativePackageDemo\NativePackageDemo.exe
~~~

Stdout chính xác:

~~~text
READY Native package
~~~

--win-console yêu cầu Windows mở console cho ứng dụng cần nhập/xuất console. Ứng dụng desktop GUI thường không cần option này. Trên Linux và macOS, bỏ option Windows và chạy launcher theo cấu trúc image của nền tảng.

## 8. Tạo installer Windows

Windows hỗ trợ hai định dạng chính:

- EXE: installer dạng executable.
- MSI: Windows Installer package, có thể tích hợp với công cụ quản lý phần mềm doanh nghiệp.

Ví dụ tạo MSI:

~~~powershell
jpackage --type msi --name NativePackageDemo --input input --main-jar NativePackageDemo.jar --main-class demo.NativePackageDemo --dest installers --app-version 1.0.0 --vendor Example --win-menu --win-menu-group "Example Tools" --win-shortcut --win-per-user-install
~~~

Có thể đổi --type msi thành --type exe để tạo EXE installer. Trên JDK 24, Windows installer cần WiX Toolset 3.0 trở lên. Cài và xác nhận toolchain này trên runner trước khi chạy job tạo installer.

Một số option Windows:

- --win-menu thêm ứng dụng vào Start Menu.
- --win-menu-group đặt tên nhóm Start Menu.
- --win-shortcut tạo shortcut trên desktop.
- --win-per-user-install cài cho user hiện tại.
- --win-dir-chooser cho phép người dùng chọn thư mục cài.
- --win-upgrade-uuid gắn mã nhận diện nâng cấp của sản phẩm.

Nếu dùng --win-upgrade-uuid, tạo một UUID riêng cho sản phẩm và giữ nguyên UUID đó giữa các phiên bản nâng cấp. Tăng --app-version khi phát hành bản mới. Kiểm thử cả cài mới, nâng cấp và gỡ cài đặt trên máy Windows sạch.

## 9. Tạo package Linux

Linux hỗ trợ:

- DEB cho Debian, Ubuntu và các hệ thống tương thích.
- RPM cho Fedora, Red Hat Enterprise Linux và các hệ thống tương thích.

Ví dụ tạo DEB:

~~~bash
jpackage --type deb \
  --name native-package-demo \
  --input input \
  --main-jar NativePackageDemo.jar \
  --main-class demo.NativePackageDemo \
  --dest installers \
  --app-version 1.0.0 \
  --vendor Example \
  --linux-package-name native-package-demo \
  --linux-menu-group Development \
  --linux-app-category Development \
  --linux-shortcut
~~~

Ví dụ tạo RPM:

~~~bash
jpackage --type rpm \
  --name native-package-demo \
  --input input \
  --main-jar NativePackageDemo.jar \
  --main-class demo.NativePackageDemo \
  --dest installers \
  --app-version 1.0.0 \
  --vendor Example \
  --linux-package-name native-package-demo \
  --linux-app-category Development
~~~

Trên Linux, môi trường build cần công cụ native tương ứng. Oracle JDK 24 yêu cầu rpm-build trên hệ Red Hat để tạo RPM và fakeroot trên Ubuntu để tạo DEB. Có thể cài thêm dependency package, maintainer, license type, release number và shortcut bằng các option Linux phù hợp.

Kiểm tra package trên đúng distro hoặc container tương thích. Không giả định một file DEB chạy được trên mọi bản phân phối Linux.

## 10. Tạo package macOS

macOS hỗ trợ:

- DMG: disk image chứa ứng dụng .app.
- PKG: package installer.

Ví dụ tạo DMG:

~~~bash
jpackage --type dmg \
  --name NativePackageDemo \
  --input input \
  --main-jar NativePackageDemo.jar \
  --main-class demo.NativePackageDemo \
  --dest installers \
  --app-version 1.0.0 \
  --vendor Example \
  --mac-package-identifier com.example.NativePackageDemo
~~~

Ví dụ tạo PKG:

~~~bash
jpackage --type pkg \
  --name NativePackageDemo \
  --input input \
  --main-jar NativePackageDemo.jar \
  --main-class demo.NativePackageDemo \
  --dest installers \
  --app-version 1.0.0 \
  --vendor Example \
  --mac-package-identifier com.example.NativePackageDemo
~~~

--mac-package-identifier nên là identifier ổn định, duy nhất theo dạng reverse-domain. Nếu cần ký ứng dụng, dùng --mac-sign cùng signing identity trong Keychain. Xcode Command Line Tools cần có khi ký package và khi tùy chỉnh icon DMG. Với phân phối bên ngoài, hoàn thiện quy trình code signing và notarization của Apple trước khi phát hành.

## 11. Tạo custom Java runtime với jlink

jpackage tự chạy jlink nếu không truyền --runtime-image. Runtime mặc định phù hợp với nhiều ứng dụng. Nếu muốn kiểm soát kích thước và module, có thể tự tạo runtime trước.

jdeps phân tích dependency của JAR và in danh sách module JDK:

~~~bash
jdeps --print-module-deps input/NativePackageDemo.jar
~~~

Với chương trình demo, kết quả:

~~~text
java.base
~~~

Dùng kết quả làm đầu vào cho jlink:

~~~bash
jlink \
  --add-modules java.base \
  --strip-debug \
  --no-man-pages \
  --no-header-files \
  --output runtime
~~~

Kiểm tra module trong runtime:

~~~bash
runtime/bin/java --list-modules
~~~

Trên Windows, dùng runtime\bin\java.exe --list-modules.

Sau đó đóng gói JAR cùng runtime vừa tạo:

~~~bash
jpackage --type app-image \
  --name NativePackageDemoCustom \
  --input input \
  --main-jar NativePackageDemo.jar \
  --main-class demo.NativePackageDemo \
  --runtime-image runtime \
  --dest dist-custom \
  --app-version 1.0.0 \
  --vendor Example
~~~

--runtime-image yêu cầu jpackage dùng runtime đã chuẩn bị thay vì tự gọi jlink. Runtime image phụ thuộc OS và kiến trúc; phải tạo runtime tương ứng với nền tảng package.

## 12. Chọn module runtime chính xác

jdeps --print-module-deps là điểm bắt đầu tốt, nhưng kết quả phân tích tĩnh không phải lúc nào cũng bao quát mọi module được ứng dụng tải lúc chạy.

Hãy kiểm tra thêm:

- Reflection hoặc dynamic class loading có thể nạp class mà jdeps không nhìn thấy.
- Service provider có thể cần module provider. jlink --bind-services liên kết các provider module và dependency của chúng.
- Ứng dụng Swing/AWT cần module java.desktop.
- Locale ngoài mặc định có thể cần jdk.localedata và --include-locales.
- JavaFX, JNI, driver, codec hoặc native library bên thứ ba cần dependency riêng theo OS/architecture.
- Resource, certificate, font và file cấu hình phải được đưa vào application payload đúng vị trí.

Ví dụ runtime cần cả desktop và logging:

~~~bash
jlink \
  --add-modules java.base,java.desktop,java.logging \
  --bind-services \
  --strip-debug \
  --no-man-pages \
  --no-header-files \
  --output runtime
~~~

Chỉ thêm module đã xác định từ dependency và kiểm thử. Runtime quá nhỏ có thể tạo image thành công nhưng ứng dụng lỗi khi mở một tính năng chỉ chạy ở production.

## 13. Metadata và tùy chỉnh launcher

Một số option thường dùng:

| Option | Công dụng |
|---|---|
| --name | Tên hiển thị của ứng dụng/package |
| --app-version | Version của ứng dụng và package |
| --vendor | Nhà phát hành |
| --description | Mô tả ngắn |
| --copyright | Thông tin bản quyền |
| --icon | Icon theo định dạng của OS |
| --license-file | Đính kèm hoặc hiển thị license |
| --arguments | Đối số mặc định cho main class |
| --java-options | JVM option mặc định |
| --app-content | Thêm file/thư mục vào payload |

Ví dụ metadata và JVM option:

~~~bash
jpackage --type app-image \
  --name NativePackageDemo \
  --input input \
  --main-jar NativePackageDemo.jar \
  --main-class demo.NativePackageDemo \
  --app-version 1.0.0 \
  --vendor Example \
  --description "Java desktop package demonstration" \
  --copyright "Copyright 2026" \
  --java-options "-Xms64m" \
  --java-options "-Xmx512m" \
  --arguments "--safe-mode" \
  --dest dist
~~~

Các JVM option được đóng vào launcher; người dùng không thể truyền JVM option tùy ý như khi gọi lệnh java. Kiểm tra file cấu hình launcher trong thư mục app/ nếu cần xác nhận các giá trị đã được ghi đúng.

## 14. Tạo nhiều launcher và file association

Một ứng dụng có thể cần nhiều launcher, ví dụ launcher chính và launcher quản trị. Dùng --add-launcher cùng một file properties.

Ví dụ admin.properties:

~~~properties
main-jar=NativePackageDemo.jar
main-class=demo.NativePackageDemo
arguments=--mode,admin
java-options=-Xmx512m
win-console=true
~~~

Tạo launcher phụ:

~~~bash
jpackage --type app-image \
  --name NativePackageDemo \
  --input input \
  --main-jar NativePackageDemo.jar \
  --main-class demo.NativePackageDemo \
  --add-launcher Admin=admin.properties \
  --dest dist
~~~

Để mở một loại file bằng ứng dụng, tạo properties file:

~~~properties
extension=demo
mime-type=application/x-native-package-demo
description=Native Package Demo file
~~~

Truyền file đó qua --file-associations:

~~~bash
jpackage --type app-image \
  --name NativePackageDemo \
  --input input \
  --main-jar NativePackageDemo.jar \
  --main-class demo.NativePackageDemo \
  --file-associations demo-file.properties \
  --dest dist
~~~

File association và shortcut có hành vi khác nhau theo OS. Kiểm tra đăng ký, mở file, gỡ cài đặt và khả năng khôi phục association khi người dùng cài phiên bản mới.

## 15. Đóng gói từ application image có sẵn

Có thể tách quy trình thành hai bước:

1. Tạo app image để kiểm thử hoặc chỉnh sửa.
2. Dùng app image đã duyệt để tạo installer.

Ví dụ tạo image:

~~~bash
jpackage --type app-image \
  --name NativePackageDemo \
  --input input \
  --main-jar NativePackageDemo.jar \
  --main-class demo.NativePackageDemo \
  --dest app-images
~~~

Sau khi kiểm tra, tạo installer từ image:

~~~powershell
jpackage --type msi --name NativePackageDemo --app-image app-images/NativePackageDemo --dest installers --app-version 1.0.0 --vendor Example --win-menu --win-shortcut
~~~

Dùng --app-image khi muốn đóng gói lại image đã kiểm thử. Đảm bảo image được tạo trên đúng OS/architecture và mọi file đã được đưa vào trước bước tạo installer.

## 16. Phát hành nhiều nền tảng trong CI/CD

Vì jpackage không tạo installer cho OS khác với host, pipeline nên chạy job trên từng OS:

| Runner | Package type | Artifact |
|---|---|---|
| Windows x64 | MSI hoặc EXE | Installer Windows |
| Ubuntu x64 | DEB | Package Debian/Ubuntu |
| Linux RPM runner | RPM | Package RPM |
| macOS runner | DMG hoặc PKG | Disk image hoặc installer macOS |

Một quy trình thường gồm:

1. Checkout source và thiết lập JDK version cố định.
2. Build/test JAR hoặc module bằng Maven/Gradle.
3. Chuẩn bị input directory gồm JAR, dependency và resource.
4. Chạy jpackage trên runner tương ứng.
5. Smoke test app image hoặc cài package trên môi trường đích.
6. Ký package theo chính sách nền tảng.
7. Tạo checksum, lưu artifact và gắn version/release metadata.

Đừng chỉ build trên một OS rồi đổi phần mở rộng file để phát hành cho OS khác. Installer cần launcher, runtime, cấu trúc bundle và metadata phù hợp với nền tảng đích.

## 17. Ký và bảo vệ gói phát hành

Code signing giúp hệ điều hành và người dùng kiểm tra nguồn gốc package và phát hiện file bị sửa đổi sau khi ký.

- **Windows:** ký EXE/MSI bằng Authenticode và certificate của nhà phát hành, thường dùng Windows SDK SignTool sau khi jpackage tạo package.
- **macOS:** dùng --mac-sign và signing identity hợp lệ trong Keychain; hoàn tất notarization theo quy trình Apple khi phân phối bên ngoài môi trường kiểm thử.
- **Linux:** phát hành qua repository có metadata được ký; kiểm tra checksum và chữ ký theo chính sách package repository.

Không đưa private signing key hoặc certificate password vào application image, JAR hoặc cache build. Lưu secret trong secret store của CI, giới hạn job được phép ký và giữ log/audit cho release.

Tạo checksum sau khi package hoàn tất:

~~~powershell
Get-FileHash .\installers\NativePackageDemo-1.0.0.msi -Algorithm SHA256
~~~

Trên Linux/macOS:

~~~bash
sha256sum installers/NativePackageDemo-1.0.0.deb
~~~

## 18. jpackage và GraalVM Native Image

jpackage và GraalVM Native Image giải quyết hai nhu cầu khác nhau:

| Tiêu chí | jpackage | GraalVM Native Image |
|---|---|---|
| Đầu vào | JAR hoặc module Java | Bytecode, dependency và reachability metadata |
| Kết quả | App image hoặc installer chứa Java runtime | Executable native được biên dịch AOT |
| Cách chạy | Launcher gọi JVM đã đóng gói | Binary chạy bằng runtime native được liên kết |
| Startup | Có thời gian khởi động JVM | Thường khởi động nhanh hơn |
| Tương thích reflection | JVM hỗ trợ đầy đủ theo runtime | Cần metadata khi static analysis không xác định được thành phần động |
| Toolchain | JDK và tool đóng gói của OS | GraalVM Native Image và compiler/toolchain C/C++ của OS |

Native Image thực hiện static reachability analysis. Reflection, JNI, dynamic proxy, resource và serialization có thể cần reachability metadata. Ứng dụng dùng nhiều framework động phải được kiểm thử kỹ vì class hoặc resource không được đưa vào image có thể gây lỗi lúc chạy.

Native Image phù hợp khi cần executable AOT, startup nhanh hoặc footprint runtime thấp. Nếu mục tiêu là cung cấp bộ cài quen thuộc, bundling JVM và tích hợp menu/shortcut, jpackage thường là lựa chọn trực tiếp.

Native Image cũng phải được build cho OS/architecture mục tiêu. Trên Windows cần MSVC và Windows SDK; trên Linux/macOS cần toolchain native tương ứng.

## 19. Kiểm thử package trước khi phát hành

Một lần build thành công chỉ xác nhận công cụ tạo được package. Cần kiểm thử sản phẩm sau khi đóng gói:

- Chạy app image trên máy sạch không cài JDK.
- Cài installer bằng tài khoản user thông thường nếu hỗ trợ per-user install.
- Mở ứng dụng từ Start Menu, desktop shortcut, Dock hoặc application menu.
- Kiểm tra resource, file cấu hình, font, locale, timezone và certificate.
- Kiểm tra file association, default arguments và JVM options.
- Kiểm tra quyền ghi vào thư mục dữ liệu; không ghi log hoặc cấu hình vào thư mục cài đặt nếu user không có quyền.
- Kiểm tra nâng cấp từ phiên bản trước, rollback nếu có và gỡ cài đặt.
- Chạy smoke test trên từng OS và architecture được công bố.

Kiểm thử trên VM hoặc runner sạch giúp phát hiện ứng dụng vô tình dùng JDK, file hoặc biến môi trường có sẵn trên máy phát triển.

## 20. Lỗi thường gặp

### Không tìm thấy WiX khi tạo MSI/EXE

Kiểm tra WiX Toolset và PATH trên Windows runner. JDK 24 yêu cầu WiX 3.0 trở lên cho installer Windows. Có thể tạo app-image trước để kiểm tra ứng dụng trong lúc chuẩn bị installer toolchain.

### Package tạo thành công nhưng launcher không chạy

Kiểm tra --main-jar, --main-class, manifest, dependency JAR và resource. Chạy JAR bằng JDK sạch trước khi đóng gói, sau đó chạy launcher của app image.

### Thiếu module sau khi dùng jlink

Chạy lại jdeps, kiểm tra dependency JAR và các đường gọi động. Bổ sung module bị thiếu bằng --add-modules; nếu dùng service provider, xem xét --bind-services.

### Ứng dụng không tìm thấy file cấu hình

Không giả định working directory là thư mục cài đặt. Dùng đường dẫn resource tương đối với application directory hoặc lưu dữ liệu user trong thư mục dữ liệu phù hợp của OS.

### Runtime image quá lớn

Kiểm tra module thực sự cần, dùng jdeps --print-module-deps, tạo runtime bằng jlink và đo lại image. Đừng loại module chỉ để giảm dung lượng khi chưa kiểm tra các chức năng tương ứng.

### Package chạy trên máy build nhưng lỗi ở máy khác

Kiểm tra OS/architecture, native library, quyền truy cập, runtime module, locale và file bên ngoài. Thử trên môi trường sạch của đúng nền tảng.

### Bản nâng cấp cài thành sản phẩm khác

Kiểm tra application name, app version, package identifier và upgrade UUID. Với Windows, giữ --win-upgrade-uuid ổn định cho cùng một sản phẩm qua các phiên bản.

### macOS chặn ứng dụng chưa ký

Kiểm tra code signing identity, certificate chain và quy trình notarization. Xác minh bundle sau khi ký trước khi phát hành.

## 21. Bài lab thực hành

Thực hiện theo thứ tự sau trên JDK 17+:

1. Tạo NativePackageDemo.java như phần ví dụ.
2. Biên dịch source bằng javac --release 17.
3. Tạo JAR trong thư mục input.
4. Chạy JAR trực tiếp để xác nhận stdout.
5. Dùng jpackage --type app-image tạo application image.
6. Chạy launcher được tạo và xác nhận stdout.
7. Chạy jdeps --print-module-deps để xem module JDK cần thiết.
8. Dùng jlink tạo runtime image.
9. Đóng gói lại bằng --runtime-image.
10. Chạy app image mới và so sánh dung lượng hai image.
11. Trên runner OS tương ứng, tạo installer và thử cài/gỡ cài đặt.

Trong lần kiểm thử với Azul JDK 24.0.2 trên Windows x64, ứng dụng demo được biên dịch bằng javac --release 17, tạo JAR và đóng gói thành Windows app image. Launcher chạy thành công và in:

~~~text
READY Native package
~~~

jdeps trả về java.base. Runtime tạo bằng jlink với module này được jpackage sử dụng thành công qua --runtime-image; launcher của image custom cũng in cùng stdout. Trong môi trường kiểm thử đó, app image dùng runtime mặc định có kích thước 120.45 MiB; image dùng runtime custom chỉ gồm java.base có kích thước 44.51 MiB. Đây là số đo của chương trình demo trên một máy, không phải mức dung lượng cố định cho mọi ứng dụng.

## 22. Checklist trước khi phát hành

- [ ] JAR/module đã được build và test độc lập.
- [ ] Đã đưa dependency và resource cần thiết vào input.
- [ ] Chọn đúng OS, architecture và package type.
- [ ] Đã đặt name, version, vendor, description và icon.
- [ ] Runtime image chứa đủ module và service provider.
- [ ] App image chạy trên máy sạch không cài JDK.
- [ ] Đã kiểm thử shortcut, menu, file association và default arguments.
- [ ] Installer đã được cài, nâng cấp và gỡ thử.
- [ ] Package được ký theo chính sách của nền tảng.
- [ ] Đã tạo checksum và lưu artifact release.
- [ ] Đã ghi lại JDK version, build flags và toolchain dùng để tạo package.
- [ ] Có pipeline chạy jpackage riêng trên từng OS/architecture cần hỗ trợ.

## 23. Tài liệu tham khảo

- [Oracle JDK 24 — jpackage command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jpackage.html): option tạo app image, installer, launcher, runtime image và metadata theo OS.
- [Oracle JDK 24 — Packaging Overview](https://docs.oracle.com/en/java/javase/24/jpackage/packaging-overview.html): yêu cầu nền tảng, định dạng package, cấu trúc application image và runtime.
- [Oracle JDK 24 — Packaging Tool User's Guide](https://docs.oracle.com/en/java/javase/24/jpackage/packaging-tool-user-guide.pdf): ví dụ non-modular/modular app, metadata, launcher, file association, license, shortcut và signing.
- [Oracle JDK 24 — jlink command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jlink.html): tạo custom runtime image, module dependency, service binding và compression.
- [Oracle JDK 24 — jdeps command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jdeps.html): phân tích dependency và tạo danh sách module cho jlink.
- [GraalVM — Native Image](https://www.graalvm.org/latest/reference-manual/native-image/): biên dịch Java AOT thành executable native và các yêu cầu toolchain.
- [GraalVM — Reachability Metadata](https://www.graalvm.org/latest/reference-manual/native-image/metadata/): cấu hình reflection, JNI, resource, proxy và serialization cho Native Image.

jpackage giúp phân phối ứng dụng Java với launcher và runtime riêng, còn jlink cho phép kiểm soát module runtime được đóng gói. Hãy build trên từng nền tảng đích, kiểm thử app image trên máy sạch và tạo installer sau khi xác nhận ứng dụng chạy đúng.
