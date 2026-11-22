# Tạo installer artifact cho ứng dụng Java

**Installer artifact** là gói phân phối giúp người dùng cài đặt, cập nhật, khởi chạy và gỡ bỏ một ứng dụng Java theo cách phù hợp với hệ điều hành. Một installer tốt cần chứa ứng dụng, các dependency cần thiết, Java runtime tương thích, metadata, icon, launcher và cấu hình cài đặt.

jpackage xuất hiện dưới dạng công cụ incubator ở JDK 14 và trở thành công cụ chính thức từ JDK 16. Công cụ này hỗ trợ tạo application image và native installer cho Windows, macOS và Linux. jpackage có thể dùng jlink để tạo runtime image riêng, giúp người dùng chạy ứng dụng mà không cần cài JDK/JRE độc lập.

Bài học này trình bày cách chuẩn bị JAR hoặc module, tạo application image, tạo installer theo nền tảng, quản lý version và upgrade, ký artifact, kiểm thử cài đặt/gỡ bỏ và đưa gói cài vào CI/CD.

## 1. Installer artifact là gì?

Một ứng dụng Java có thể được phân phối theo nhiều dạng:

| Artifact | Nội dung | Cách sử dụng |
|---|---|---|
| JAR | Bytecode và resource của ứng dụng | Người dùng cần Java runtime và lệnh chạy phù hợp |
| Fat JAR | Ứng dụng cùng dependency được đóng gói | Vẫn cần Java runtime |
| Modular JAR | JAR có module descriptor | Chạy bằng module path và runtime tương thích |
| Runtime image | Java runtime tùy chỉnh tạo bằng jlink | Chưa nhất thiết có launcher/installer cho ứng dụng |
| Application image | Launcher, application files và runtime | Có thể chạy trực tiếp từ thư mục image |
| Native installer | Gói cài đặt theo OS, có thể cài shortcut, menu, file association | Người dùng cài như ứng dụng desktop thông thường |

### Phân biệt application image và installer

**Application image** là một thư mục đã được tổ chức để chạy ứng dụng. Thư mục này thường có:

- Launcher native của ứng dụng.
- JAR/module và resource.
- File cấu hình launcher do jpackage tạo.
- Java runtime image được đóng gói.

**Native installer** là gói cài đặt sử dụng cơ chế của hệ điều hành. Installer có thể đăng ký shortcut, menu, file association, installation location và thông tin package để hệ điều hành quản lý.

Application image thường là bước trung gian rất hữu ích: tạo image, chạy thử, rồi dùng chính image đó để tạo MSI, EXE, PKG hoặc DMG.

Một application image có thể được nén thành ZIP để phân phối thủ công, nhưng nó không tự có đầy đủ trải nghiệm cài đặt và quản lý package như native installer.

## 2. Các định dạng installer theo hệ điều hành

jpackage hỗ trợ các loại package sau:

| Nền tảng | Định dạng | Đặc điểm |
|---|---|---|
| Windows | MSI | Windows Installer package, hỗ trợ cài đặt và nâng cấp qua Windows Installer |
| Windows | EXE | Bộ cài dạng executable, thường bao bọc MSI |
| macOS | DMG | Disk image chứa ứng dụng .app để người dùng cài/copy |
| macOS | PKG | Installer package của macOS |
| Linux | DEB | Package cho Debian/Ubuntu và hệ tương thích |
| Linux | RPM | Package cho Fedora/RHEL và hệ tương thích |
| Đa nền tảng trong cùng OS | app-image | Thư mục ứng dụng có launcher và runtime |

Định dạng cần chọn theo cách người dùng cài đặt và hệ thống phân phối của tổ chức. Ví dụ, ứng dụng desktop cho Windows thường cung cấp MSI hoặc EXE; phần mềm quản lý bằng package repository trên Linux thường cung cấp DEB hoặc RPM.

Không nên mặc định một định dạng dùng được trên mọi hệ điều hành. jpackage tạo package theo nền tảng đang chạy và không hỗ trợ cross-platform packaging.

## 3. jpackage và jlink phối hợp như thế nào?

jpackage nhận application JAR hoặc module, metadata, launcher options và resource. Nếu không cung cấp runtime image, jpackage gọi jlink để tạo Java runtime phù hợp rồi đặt runtime đó trong application image.

Luồng đóng gói:

~~~text
Java source
    |
    v
javac / Maven / Gradle
    |
    v
JAR hoặc modular JAR
    |
    v
jpackage
    |
    +----> jlink tạo runtime image
    |
    v
Application image
    |
    v
Native installer
    |
    v
Install / launch / update / uninstall
~~~

Điều này có nghĩa người dùng có thể chạy ứng dụng bằng launcher được tạo mà không cần tự cài Java runtime riêng.

### Runtime image không phải toàn bộ JDK

Runtime image do jpackage tạo thường đã loại bỏ:

- Debug symbols.
- Các native command thông thường của JDK.
- Man pages.
- Header files.
- Một số file phục vụ phát triển như src.zip.

Runtime vẫn có các thành phần cần thiết để chạy ứng dụng.

Vì vậy, không nên giả định thư mục runtime đi kèm application image có lệnh java.exe hoặc java giống JDK đầy đủ. Launcher của ứng dụng sử dụng runtime được đóng gói.

### jpackage chọn Java runtime phiên bản nào?

Nếu không truyền --runtime-image, jpackage dùng JDK đang chạy công cụ để gọi jlink. Cờ javac --release chỉ điều khiển API và class-file target khi compile; nó không buộc jpackage tạo runtime của cùng release đó.

Ví dụ:

- Build source bằng JDK 24 với javac --release 17.
- Chạy jpackage từ JDK 24.
- Application image mặc định sẽ chứa runtime được tạo từ JDK 24.

Nếu sản phẩm cần chạy trên Java 17, hãy dùng JDK 17 để tạo runtime image phù hợp hoặc tạo runtime bằng jlink của JDK 17 rồi truyền qua --runtime-image.

### ServiceLoader và module runtime

Với ứng dụng sử dụng ServiceLoader hoặc provider modules, cần kiểm tra các provider có được đưa vào runtime image hay không.

jpackage có tùy chọn jlink:

~~~bash
--jlink-options "--bind-services --strip-debug --no-man-pages --no-header-files"
~~~

Có thể thêm module bằng --add-modules khi dependency được nạp động hoặc không được suy luận đầy đủ từ module graph.

Với ứng dụng modular, runtime mặc định chứa main module và dependency closure của nó. Với ứng dụng classpath/non-modular, runtime mặc định chứa tập module JDK phù hợp cho classpath application. Các provider service có thể cần --bind-services.

## 4. Chuẩn bị ứng dụng trước khi đóng gói

Trước khi gọi jpackage, cần có artifact ứng dụng đã build và các resource cần thiết.

Một cấu trúc input đơn giản:

~~~text
installer-project/
├── src/
│   └── com/acme/desktop/Main.java
├── build/
│   ├── classes/
│   └── installer-input/
│       ├── acme-desktop.jar
│       ├── dependency-a.jar
│       └── dependency-b.jar
├── assets/
│   ├── app.ico
│   ├── app.icns
│   └── app.png
└── dist/
~~~

Thư mục được truyền vào --input chứa các file sẽ được đưa vào application image. Đảm bảo main JAR, dependency JAR và resource cần thiết đã có ở đúng vị trí.

### Xác định main class

Ứng dụng cần có entry point hợp lệ:

~~~java
package com.acme.desktop;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Acme Desktop started");
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -d build/classes src/com/acme/desktop/Main.java
~~~

Đóng gói JAR:

~~~bash
jar --create --file build/installer-input/acme-desktop.jar --main-class com.acme.desktop.Main -C build/classes .
~~~

Chạy thử JAR trước:

~~~bash
java -jar build/installer-input/acme-desktop.jar
~~~

Stdout:

~~~text
Acme Desktop started
~~~

Nếu ứng dụng có dependency, hãy build và copy chúng vào input folder theo cấu hình classpath phù hợp. Với ứng dụng modular, sử dụng module path và main module thay vì main-jar.

### Chuẩn bị resource

Resource cần cho ứng dụng phải được đóng gói hoặc cài ở vị trí có thể truy cập. Ví dụ:

- File cấu hình mặc định.
- Template.
- Certificate công khai cần thiết.
- Native library theo OS/architecture.
- Font hoặc asset.
- License text.
- File association metadata.

Không đóng gói secret, private key, mật khẩu hoặc token production vào installer. Người dùng có thể giải nén application image và đọc các file đã đóng gói.

### Tách dữ liệu cài đặt và dữ liệu người dùng

Không ghi file người dùng thay đổi thường xuyên vào thư mục cài đặt ứng dụng. Dùng user home hoặc application data directory để lưu:

- Preferences.
- Cache.
- Log.
- Database local.
- Downloaded files.
- User-created documents.

Installer và updater có thể thay thế hoặc xóa file trong installation directory. Thiết kế vị trí dữ liệu riêng giúp upgrade và uninstall an toàn hơn.

## 5. Tạo application image cho ứng dụng non-modular

Với ứng dụng dùng classpath hoặc JAR thông thường, dùng --input, --main-jar và --main-class.

Ví dụ:

~~~bash
jpackage --type app-image --input build/installer-input --name AcmeDesktop --main-jar acme-desktop.jar --main-class com.acme.desktop.Main --app-version 1.2.3 --vendor "Acme Corporation" --description "Acme Desktop Application" --dest dist
~~~

Trên Windows PowerShell có thể viết trên một dòng hoặc dùng dấu backtick để xuống dòng; ví dụ trên không cần continuation character.

Giải thích:

- --type app-image: chỉ tạo application image.
- --input: thư mục chứa application JAR và các file đầu vào.
- --name: tên ứng dụng và launcher.
- --main-jar: JAR chính, tính tương đối với input folder.
- --main-class: main class.
- --app-version: version của ứng dụng/package.
- --vendor: tên nhà cung cấp.
- --description: mô tả ứng dụng.
- --dest: thư mục nhận output.

Sau khi tạo, output thường có dạng:

~~~text
dist/
└── AcmeDesktop/
    ├── AcmeDesktop.exe
    ├── app/
    │   ├── AcmeDesktop.cfg
    │   └── acme-desktop.jar
    └── runtime/
~~~

Cấu trúc cụ thể phụ thuộc nền tảng. Trên Linux launcher thường nằm trong bin/; trên macOS là bundle .app; trên Windows launcher có thể nằm ở root application image.

### Chạy thử application image

Windows:

~~~powershell
.\dist\AcmeDesktop\AcmeDesktop.exe
~~~

Linux:

~~~bash
./dist/AcmeDesktop/bin/AcmeDesktop
~~~

macOS:

~~~bash
open dist/AcmeDesktop.app
~~~

Stdout ví dụ cho ứng dụng console:

~~~text
Acme Desktop started
~~~

Với GUI application, không bật console launcher nếu không cần terminal output.

## 6. Tạo application image cho ứng dụng modular

Với JPMS, dùng --module-path và --module:

~~~bash
jpackage --type app-image --module-path mods --module com.acme.desktop/com.acme.desktop.Main --name AcmeDesktop --app-version 1.2.3 --dest dist
~~~

Nếu module path cần cả application modules và JDK jmods, truyền các đường dẫn phù hợp bằng path separator của OS. Trên Windows separator là dấu chấm phẩy; trên Linux/macOS là dấu hai chấm.

Module chính phải có module descriptor hợp lệ và dependency cần thiết phải resolve được.

### Thêm module cần thiết

Nếu ứng dụng cần module không được suy luận từ dependency graph:

~~~bash
jpackage --type app-image --module-path mods --add-modules java.sql,java.logging --module com.acme.desktop/com.acme.desktop.Main --name AcmeDesktop --dest dist
~~~

Chỉ thêm các module thực sự cần thiết. Thêm quá nhiều module làm runtime image lớn hơn.

### Tự tạo runtime bằng jlink

Có thể tạo runtime riêng trước:

~~~powershell
jlink --module-path "mods;$env:JAVA_HOME\jmods" --add-modules com.acme.desktop --bind-services --strip-debug --no-header-files --no-man-pages --output build/runtime
~~~

Trên Linux/macOS thay dấu chấm phẩy trong module path bằng dấu hai chấm.

Sau đó đóng gói runtime image:

~~~bash
jpackage --type app-image --module-path mods --module com.acme.desktop/com.acme.desktop.Main --runtime-image build/runtime --name AcmeDesktop --dest dist
~~~

Runtime image phải tương thích với OS, architecture và JDK release mục tiêu.

## 7. Tùy chỉnh launcher và JVM options

jpackage cho phép cấu hình JVM options và application arguments.

Ví dụ:

~~~bash
jpackage --type app-image --input build/installer-input --name AcmeDesktop --main-jar acme-desktop.jar --main-class com.acme.desktop.Main --java-options "-Xms256m" --java-options "-Xmx1024m" --java-options "-Dfile.encoding=UTF-8" --arguments "--profile=desktop" --dest dist
~~~

Các JVM options được truyền tới runtime của ứng dụng. Chọn heap phù hợp với memory budget của thiết bị; không đặt Xmx quá cao so với môi trường mục tiêu.

### Tạo launcher phụ

Có thể tạo launcher bổ sung bằng --add-launcher. Ví dụ file **import.properties**:

~~~properties
main-class=com.acme.desktop.ImportMain
arguments=--mode=import
java-options=-Xmx512m
description=Import Acme data
~~~

Tạo image:

~~~bash
jpackage --type app-image --input build/installer-input --name AcmeDesktop --main-jar acme-desktop.jar --main-class com.acme.desktop.Main --add-launcher Import=import.properties --dest dist
~~~

Application image có thể chứa launcher chính và launcher Import. Tệp properties cần được quản lý cùng source/build configuration để tái lập.

### Console và GUI launcher

Trên Windows, --win-console tạo console launcher, phù hợp ứng dụng CLI hoặc cần tương tác terminal. Với desktop GUI, thường không bật tùy chọn này để tránh mở cửa sổ console không cần thiết.

## 8. Metadata, icon, license và file association

Installer là giao diện đầu tiên người dùng nhìn thấy. Metadata cần chính xác và nhất quán với tên sản phẩm.

Các option chung:

| Option | Mục đích |
|---|---|
| --name | Tên ứng dụng/package |
| --app-version | Phiên bản |
| --vendor | Nhà cung cấp |
| --description | Mô tả |
| --copyright | Thông tin bản quyền |
| --about-url | Website sản phẩm |
| --icon | Icon |
| --license-file | File license |
| --install-dir | Thư mục cài đặt |
| --resource-dir | Thay thế resource/template mặc định |
| --file-associations | Đăng ký loại file ứng dụng mở |

### Icon theo nền tảng

Định dạng icon thường dùng:

- Windows: .ico.
- macOS: .icns.
- Linux: .png.

Ví dụ:

~~~bash
jpackage --type app-image --input build/installer-input --name AcmeDesktop --main-jar acme-desktop.jar --main-class com.acme.desktop.Main --icon assets/acme.ico --dest dist
~~~

Icon phải đúng định dạng và kích thước phù hợp với nền tảng. Một icon PNG không tự động thay thế được icon ICO trên Windows.

### License file

Ví dụ:

~~~bash
jpackage --type msi --input build/installer-input --name AcmeDesktop --main-jar acme-desktop.jar --main-class com.acme.desktop.Main --license-file LICENSE.txt --dest dist
~~~

License file được dùng cho trải nghiệm cài đặt tùy định dạng package. Hãy đảm bảo nội dung license và copyright đã được duyệt.

### File association

Có thể tạo file properties để đăng ký extension:

~~~properties
extension=acme
mime-type=application/x-acme
description=Acme Project File
icon=assets/acme-file.ico
~~~

Sau đó:

~~~bash
jpackage --type msi --input build/installer-input --name AcmeDesktop --main-jar acme-desktop.jar --main-class com.acme.desktop.Main --file-associations file-association.properties --dest dist
~~~

Kiểm tra file association trên máy cài đặt thực tế. Hành vi có thể khác theo OS và installer type.

## 9. Tạo Windows MSI và EXE

Trên Windows, jpackage hỗ trợ app-image, msi và exe.

Ví dụ tạo MSI:

~~~powershell
jpackage --type msi --input build/installer-input --name AcmeDesktop --main-jar acme-desktop.jar --main-class com.acme.desktop.Main --app-version 1.2.3 --vendor "Acme Corporation" --win-menu --win-menu-group "Acme Tools" --win-shortcut --win-upgrade-uuid "8c8f7a40-ecf1-4d6a-91bd-47f2c90f2b10" --dest dist
~~~

Ví dụ tạo EXE:

~~~powershell
jpackage --type exe --input build/installer-input --name AcmeDesktop --main-jar acme-desktop.jar --main-class com.acme.desktop.Main --app-version 1.2.3 --win-menu --win-shortcut --dest dist
~~~

### Windows installer options

| Option | Ý nghĩa |
|---|---|
| --win-dir-chooser | Cho người dùng chọn thư mục cài |
| --win-menu | Tạo Start Menu shortcut |
| --win-menu-group | Nhóm Start Menu |
| --win-shortcut | Tạo desktop shortcut |
| --win-shortcut-prompt | Hỏi người dùng có muốn shortcut |
| --win-per-user-install | Cài theo user |
| --win-upgrade-uuid | Định danh upgrade của sản phẩm |
| --win-update-url | URL thông tin update |
| --win-help-url | URL hỗ trợ |

### WiX requirement

Để tạo MSI/EXE trên Windows, jpackage cần WiX Toolset 3.0 trở lên theo yêu cầu của JDK 24. Kiểm tra WiX đã cài và các công cụ cần thiết nằm trong PATH trước khi build installer.

Application image vẫn có thể tạo mà không cần WiX. Vì vậy, có thể kiểm thử launcher và runtime trước, sau đó chạy bước tạo MSI/EXE trên Windows build agent đã cài đủ công cụ.

### Upgrade UUID

Giữ cùng một --win-upgrade-uuid cho các phiên bản tiếp nối của cùng sản phẩm để Windows Installer nhận diện quan hệ upgrade. Không tạo UUID ngẫu nhiên mới cho mỗi lần phát hành nếu muốn nâng cấp cài đặt hiện tại.

Tăng app-version theo quy tắc version của sản phẩm. Thay đổi upgrade identity chỉ khi tạo một sản phẩm/package line độc lập và đã xác định chính sách migration.

## 10. Tạo macOS DMG và PKG

Trên macOS, jpackage hỗ trợ app-image dưới dạng .app bundle, dmg và pkg.

Ví dụ tạo DMG:

~~~bash
jpackage --type dmg --input build/installer-input --name AcmeDesktop --main-jar acme-desktop.jar --main-class com.acme.desktop.Main --app-version 1.2.3 --mac-package-identifier com.acme.desktop --icon assets/acme.icns --dest dist
~~~

Ví dụ tạo PKG:

~~~bash
jpackage --type pkg --input build/installer-input --name AcmeDesktop --main-jar acme-desktop.jar --main-class com.acme.desktop.Main --app-version 1.2.3 --mac-package-identifier com.acme.desktop --dest dist
~~~

### macOS package identifier

Dùng bundle identifier ổn định, thường theo reverse-domain:

~~~text
com.acme.desktop
~~~

Identifier cần hợp lệ và nhất quán giữa các phiên bản để hệ thống nhận diện ứng dụng.

### Code signing

Có thể yêu cầu jpackage ký bundle:

~~~bash
jpackage --type dmg --input build/installer-input --name AcmeDesktop --main-jar acme-desktop.jar --main-class com.acme.desktop.Main --mac-package-identifier com.acme.desktop --mac-sign --mac-signing-key-user-name "Developer ID Application: Acme Corporation" --dest dist
~~~

Có thể chọn keychain bằng --mac-signing-keychain và cấu hình entitlements bằng --mac-entitlements. Việc ký cần certificate và signing identity hợp lệ.

Trên JDK 24, Xcode command line tools cần có khi sử dụng --mac-sign và khi dùng --icon để tùy chỉnh DMG image.

### Notarization

Code signing và notarization là hai bước khác nhau. Với ứng dụng phân phối ngoài Mac App Store, quy trình phát hành thường cần:

1. Ký application bundle và thành phần native.
2. Tạo DMG hoặc PKG.
3. Gửi artifact tới Apple notarization service bằng công cụ của Apple, chẳng hạn xcrun notarytool.
4. Chờ kết quả và xử lý lỗi nếu có.
5. Staple ticket vào artifact bằng xcrun stapler.
6. Kiểm tra lại signature và notarization.

Không xem việc jpackage chạy thành công là bằng chứng ứng dụng đã được notarize.

## 11. Tạo Linux DEB và RPM

Trên Linux, jpackage hỗ trợ DEB và RPM.

Ví dụ DEB:

~~~bash
jpackage --type deb --input build/installer-input --name acme-desktop --main-jar acme-desktop.jar --main-class com.acme.desktop.Main --app-version 1.2.3 --linux-package-name acme-desktop --linux-deb-maintainer packages@acme.example --linux-app-category Utility --linux-shortcut --dest dist
~~~

Ví dụ RPM:

~~~bash
jpackage --type rpm --input build/installer-input --name acme-desktop --main-jar acme-desktop.jar --main-class com.acme.desktop.Main --app-version 1.2.3 --linux-package-name acme-desktop --linux-rpm-license-type MIT --linux-app-category Utility --linux-shortcut --dest dist
~~~

### Linux package options

| Option | Ý nghĩa |
|---|---|
| --linux-package-name | Tên package |
| --linux-deb-maintainer | Maintainer email cho DEB |
| --linux-package-deps | Package dependency cần có |
| --linux-rpm-license-type | License type cho RPM |
| --linux-app-release | Release/revision của package |
| --linux-app-category | Category |
| --linux-menu-group | Nhóm menu |
| --linux-shortcut | Tạo shortcut |

### Công cụ cần có

Theo yêu cầu packaging của JDK 24:

- Ubuntu cần fakeroot để tạo DEB.
- Red Hat Linux cần rpm-build để tạo RPM.

Hãy build package trên distro tương thích và kiểm thử trên máy cài đặt sạch. Một DEB hoặc RPM có thể khai báo dependency tới package native của OS; khai báo chính xác để package manager xử lý.

## 12. Tạo package từ application image có sẵn

Một quy trình tốt là tách bước tạo image khỏi bước tạo installer:

1. Build JAR/module.
2. Tạo application image.
3. Chạy smoke test.
4. Ký application image nếu cần.
5. Tạo native installer từ image đã kiểm thử.

Ví dụ tạo MSI từ image:

~~~powershell
jpackage --type msi --app-image dist/AcmeDesktop --name AcmeDesktop --app-version 1.2.3 --win-menu --win-shortcut --dest installer-output
~~~

Cách này giúp kiểm thử cùng một application image trước khi tạo installer. Khi build nhiều định dạng cho cùng một OS, có thể dùng image làm đầu vào nếu định dạng và tùy chọn tương thích.

Không sửa thủ công file runtime hoặc launcher trong image sau khi ký. Nếu thay đổi nội dung sau signing, cần ký lại theo quy trình.

## 13. Installer lifecycle: install, upgrade và uninstall

Một installer artifact cần được đánh giá qua toàn bộ vòng đời, không chỉ tạo file thành công.

### Install

Kiểm tra:

- Installation path.
- Quyền user/admin.
- Shortcut và Start Menu.
- File association.
- Runtime được đóng gói.
- Application launcher chạy được.
- Native library có thể load.
- Application data directory có quyền ghi.

### Upgrade

Kiểm tra:

- Cùng product identity.
- Version mới được nhận diện.
- File ứng dụng được thay thế đúng.
- User data và cấu hình được giữ.
- Database/schema migration có thể hoàn tất.
- Upgrade bị gián đoạn có thể phục hồi.
- Không có hai bản cài xung đột ngoài chủ ý.

Với Windows MSI, giữ upgrade UUID ổn định cho cùng sản phẩm. Với macOS và Linux, giữ bundle/package identity phù hợp để hệ thống nhận diện đúng ứng dụng.

### Uninstall

Kiểm tra:

- Application files được gỡ.
- Shortcut và file associations được xử lý đúng.
- Service/background process được dừng.
- Không để process giữ file trong installation directory.
- Chính sách dữ liệu người dùng được thực hiện đúng.

Không xóa user-created documents hoặc database local một cách bất ngờ. Quy định rõ dữ liệu nào bị xóa, dữ liệu nào được giữ và cách người dùng sao lưu.

### Installation directory và user data

Windows có thể dùng --install-dir với sub-path dưới thư mục cài đặt mặc định. Linux/macOS có thể dùng đường dẫn cài đặt tuyệt đối theo quy tắc nền tảng.

Không đặt database hoặc cấu hình thay đổi thường xuyên trong installation directory. Updater và installer thường có quyền thay thế file tại đó.

## 14. Signing và xác minh tính toàn vẹn

Installer là artifact được người dùng chạy với quyền trên hệ thống. Cần xác minh nguồn gốc và tính toàn vẹn.

### Windows Authenticode

Windows installer thường được ký bằng certificate code signing thông qua SignTool của Windows SDK. jpackage tạo package; việc ký MSI/EXE có thể thực hiện bằng bước signing riêng trong pipeline.

Ví dụ dạng lệnh:

~~~powershell
signtool sign /fd SHA256 /tr <timestamp-service-url> /td SHA256 /a AcmeDesktop.msi
~~~

Kiểm tra signature:

~~~powershell
signtool verify /pa /v AcmeDesktop.msi
~~~

Dùng certificate và timestamp service được tổ chức phê duyệt. Bảo vệ private key trong signing service hoặc secure CI secret store; không đặt private key trong source repository hoặc installer.

### macOS signing và notarization

Dùng Developer ID signing identity phù hợp, entitlements tối thiểu và quy trình notarization của Apple. Sau khi ký, không chỉnh sửa bundle nếu chưa ký lại.

Kiểm tra:

~~~bash
codesign --verify --deep --strict --verbose=2 AcmeDesktop.app
spctl --assess --type execute --verbose AcmeDesktop.app
~~~

Sau khi notarize, kiểm tra ticket đã được staple và package có thể mở trên máy sạch theo Gatekeeper policy.

### Linux package signing

jpackage tạo DEB/RPM package; việc ký package hoặc repository metadata thường được thực hiện bằng công cụ và quy trình của distro/repository. Ví dụ RPM repository có thể dùng GPG signing. Với DEB, nhiều tổ chức ký repository metadata và xác minh qua apt trust configuration.

Không xem SHA-256 đơn thuần là chữ ký. Hash giúp phát hiện thay đổi khi có giá trị tham chiếu đáng tin cậy; chữ ký xác thực người phát hành và artifact theo trust chain.

### Checksum và provenance

Lưu checksum:

Windows PowerShell:

~~~powershell
Get-FileHash .\dist\AcmeDesktop.msi -Algorithm SHA256
~~~

Linux/macOS:

~~~bash
sha256sum dist/AcmeDesktop.deb
~~~

Lưu kèm:

- Source revision.
- JDK vendor/version.
- jpackage/JDK version.
- OS và architecture.
- Build tool/plugin versions.
- Package version.
- Checksum.
- Signing identity và kết quả verification.
- SBOM và provenance nếu pipeline có hỗ trợ.

## 15. Kiểm thử installer artifact

Một package tạo thành công chưa chứng minh cài đặt và vận hành đúng.

### Kiểm tra application image

- Launcher có tồn tại và chạy được.
- Runtime image đi kèm đầy đủ.
- Ứng dụng chạy khi không cài Java riêng.
- JVM options được áp dụng.
- Resource và native library được tìm thấy.
- Log/config path có quyền ghi.

### Kiểm tra native installer

- Cài trên máy/VM sạch.
- Cài bằng user thường và admin khi có hỗ trợ.
- Kiểm tra shortcut/menu.
- Mở file association.
- Khởi chạy ứng dụng sau reboot.
- Kiểm tra upgrade từ version trước.
- Kiểm tra uninstall.
- Kiểm tra dữ liệu người dùng còn lại theo chính sách.
- Kiểm tra certificate và signature.
- Kiểm tra package manager nhận diện đúng version.

### Kiểm tra runtime độc lập

Không chỉ chạy bằng JAR với JDK của máy build. Hãy chạy launcher trong application image hoặc cài installer lên máy không có JDK, để xác nhận runtime đã được đóng gói đúng.

### Kiểm tra OS và architecture

Build và test riêng cho từng target:

- Windows x64/ARM64 nếu hỗ trợ.
- macOS Intel/Apple Silicon theo mục tiêu phân phối.
- Linux x64/ARM64 và các distro cần hỗ trợ.

Native libraries, runtime image và installer package phụ thuộc nền tảng. Không tái sử dụng package tạo trên Windows cho Linux hoặc ngược lại.

## 16. Tổ chức CI/CD cho installer artifact

Một pipeline có thể chia thành các stage:

~~~text
Checkout source
    |
    v
Compile + unit tests
    |
    v
Build JAR / modules
    |
    v
Create application image
    |
    v
Smoke test launcher
    |
    v
Create native installer
    |
    v
Sign + verify
    |
    v
Install / upgrade / uninstall tests
    |
    v
Checksum + SBOM + provenance
    |
    v
Publish artifacts
~~~

### Build matrix theo OS

Dùng build runner riêng:

| Runner | Artifact |
|---|---|
| Windows | MSI/EXE và Windows app-image |
| macOS | DMG/PKG và .app image |
| Ubuntu/Debian | DEB và Linux app-image |
| RHEL/Fedora | RPM và Linux app-image |

Mỗi runner cần JDK, build tool và native packaging tools tương ứng.

### Pin toolchain

Pin:

- JDK vendor/version.
- Maven/Gradle Wrapper.
- Plugin versions.
- Dependency versions.
- jpackage options.
- Installer toolchain (WiX, Xcode, rpm-build, fakeroot).
- OS image và architecture.

Nếu JDK version thay đổi, runtime image có thể thay đổi dù application source không đổi. Hãy xem đây là thay đổi runtime cần kiểm thử.

### Đặt tên artifact nhất quán

Ví dụ:

~~~text
AcmeDesktop-1.2.3-windows-x64.msi
AcmeDesktop-1.2.3-macos-aarch64.dmg
AcmeDesktop-1.2.3-linux-x64.deb
AcmeDesktop-1.2.3-linux-x64.rpm
~~~

Không ghi đè artifact của một OS/architecture bằng artifact của target khác. Lưu package, checksum, SBOM và build metadata cùng release.

## 17. Troubleshooting

### jpackage báo không tìm thấy main class

Kiểm tra --main-class có đúng fully qualified class name không, main JAR có chứa class và package path không, và class có public static void main(String[] args) không.

### jpackage báo main JAR không nằm trong input directory

--main-jar phải là tên/relative path nằm trong thư mục --input. Kiểm tra chính tả và cấu trúc folder trước khi chạy.

### Application image tạo được nhưng launcher không chạy

Kiểm tra:

- Runtime image có đủ module không.
- Launcher config có đúng main class/module không.
- JAR và resource có trong application image không.
- Native libraries có đúng OS/architecture không.
- JVM options có hợp lệ không.
- Log hoặc console output có thông tin lỗi không.

### ClassNotFoundException hoặc NoClassDefFoundError

Dependency có thể chưa được đóng gói hoặc launcher classpath/module path chưa đúng. Kiểm tra input folder, module descriptor, dependency versions và launcher config.

### ServiceLoader không tìm thấy provider

Kiểm tra module descriptor uses/provides hoặc META-INF/services. Nếu jlink tạo runtime image, xem có cần --bind-services để liên kết provider modules không.

### Runtime thiếu module

Dùng jdeps để phân tích dependency và thêm module cần thiết bằng --add-modules hoặc tạo lại runtime image bằng jlink. Kiểm tra dynamic reflection và service loading vì một số dependency có thể không được suy luận tĩnh.

### Windows MSI/EXE không tạo được

Kiểm tra WiX Toolset 3.0 trở lên đã cài và các công cụ nằm trong PATH. Xem output --verbose và thư mục --temp nếu cần giữ lại file trung gian để chẩn đoán.

### Linux DEB/RPM không tạo được

Kiểm tra đang build trên Linux phù hợp và có fakeroot cho Ubuntu/DEB hoặc rpm-build cho Red Hat/RPM. Kiểm tra package name, version, maintainer, category và dependency syntax.

### macOS package bị từ chối

Kiểm tra icon, bundle identifier, signing identity, entitlements, certificate chain và notarization. Không chỉnh sửa app bundle sau signing; nếu có thay đổi phải ký và notarize lại.

### Installer chạy trên máy build nhưng lỗi trên máy khác

Kiểm tra OS version, CPU architecture, native libraries, quyền truy cập, runtime dependencies, environment variables và package prerequisites. Thử trên VM sạch cùng phiên bản OS mục tiêu.

### Installer upgrade không nhận diện version cũ

Kiểm tra package identity. Trên Windows, giữ --win-upgrade-uuid của cùng sản phẩm. Trên macOS/Linux, giữ bundle/package name và identifier phù hợp. Tăng version theo quy tắc package manager.

## 18. Lab Java 17+: tạo application image bằng jpackage

Tạo file **Main.java**:

~~~java
package com.acme.installer;

public final class Main {
    public static void main(String[] args) {
        System.out.println("Installer artifact demo");
        System.out.println("Java runtime: "
                + Runtime.version().feature());
        System.out.println("Arguments: "
                + String.join(",", args));
    }
}
~~~

Biên dịch:

~~~bash
javac --release 17 -d classes Main.java
~~~

Tạo input folder và JAR:

~~~bash
mkdir input
jar --create --file input/artifact-demo.jar --main-class com.acme.installer.Main -C classes .
~~~

Chạy JAR để kiểm tra:

~~~bash
java -jar input/artifact-demo.jar alpha beta
~~~

Stdout trên JDK 24:

~~~text
Installer artifact demo
Java runtime: 24
Arguments: alpha,beta
~~~

Tạo application image trên Windows:

~~~powershell
jpackage --type app-image --input input --name ArtifactDemo --main-jar artifact-demo.jar --main-class com.acme.installer.Main --app-version 1.2.3 --vendor "Acme Example" --description "Java installer artifact lab" --dest output --win-console
~~~

Chạy launcher:

~~~powershell
.\output\ArtifactDemo\ArtifactDemo.exe alpha beta
~~~

Stdout:

~~~text
Installer artifact demo
Java runtime: 24
Arguments: alpha,beta
~~~

Application image chứa launcher, application files và runtime image. Trong thử nghiệm trên OpenJDK 24.0.2, image chạy được và có dung lượng khoảng 126 MB. Dung lượng thay đổi theo JDK, module, OS và ứng dụng.

Ứng dụng được biên dịch với --release 17 nhưng runtime đi kèm là Java 24 vì jpackage được chạy từ JDK 24.0.2. Nếu cần runtime Java 17, phải tạo runtime image bằng JDK 17 và truyền --runtime-image cho jpackage.

### Thử tạo MSI

Sau khi app-image chạy thành công, dùng Windows runner đã cài WiX:

~~~powershell
jpackage --type msi --app-image output\ArtifactDemo --name ArtifactDemo --app-version 1.2.3 --win-menu --win-shortcut --win-upgrade-uuid "8c8f7a40-ecf1-4d6a-91bd-47f2c90f2b10" --dest installer
~~~

Sau đó cài MSI trên VM Windows sạch, kiểm tra launcher, shortcut, upgrade và uninstall. UUID ở đây là ví dụ; sản phẩm thực tế phải dùng UUID ổn định do nhóm release quản lý.

## 19. Checklist trước khi phát hành installer

- Application JAR/module đã build và test.
- Main class/module được khai báo chính xác.
- Dependency và resource đã được đóng gói.
- Java runtime tương thích được bundle.
- Đã xác định OS và architecture mục tiêu.
- Application image chạy được trên máy không có JDK.
- Version, vendor, description, copyright và license chính xác.
- Icon và file associations đúng nền tảng.
- Installation directory và user data directory tách biệt.
- Upgrade identity ổn định.
- Installer cài đặt và gỡ bỏ được trên VM sạch.
- Upgrade từ phiên bản trước được kiểm thử.
- User data được giữ/xóa đúng chính sách.
- Code signing và notarization hoàn tất khi cần.
- Checksum, SBOM và provenance được lưu.
- Artifact được đặt tên theo version/OS/architecture.
- CI lưu log và kết quả verification.
- Package cuối cùng được kiểm thử đúng định dạng sẽ phát hành.

## 20. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| Installer artifact | Gói cài đặt ứng dụng |
| jpackage | Công cụ tạo application image và native installer |
| jlink | Công cụ tạo Java runtime image tùy chỉnh |
| Application image | Thư mục ứng dụng gồm launcher, files và runtime |
| Native installer | Package theo cơ chế cài đặt của hệ điều hành |
| MSI | Windows Installer package |
| EXE installer | Bộ cài executable cho Windows |
| DMG | macOS disk image |
| PKG | macOS installer package |
| DEB | Package của Debian/Ubuntu |
| RPM | Package của Fedora/RHEL và hệ tương thích |
| Runtime image | Bộ runtime Java đã được link |
| Main JAR | JAR chứa main class của ứng dụng |
| Module path | Đường dẫn chứa JPMS modules |
| File association | Liên kết loại file với ứng dụng |
| Upgrade UUID | Định danh upgrade của Windows package |
| Code signing | Ký số artifact bằng certificate |
| Notarization | Quy trình Apple kiểm tra phần mềm phân phối ngoài App Store |
| SBOM | Danh sách thành phần phần mềm trong artifact |
| Provenance | Thông tin nguồn và quy trình tạo artifact |

Installer artifact hoàn chỉnh cần đóng gói ứng dụng cùng runtime phù hợp, khai báo metadata và installation behavior rõ ràng, hỗ trợ upgrade/uninstall, ký và xác minh package, rồi kiểm thử trên môi trường sạch. jpackage giúp chuẩn hóa phần đóng gói, còn CI theo từng nền tảng bảo đảm artifact phát hành phù hợp với hệ điều hành và kiến trúc mục tiêu.

## Tài liệu tham khảo

- Oracle JDK 24 — The jpackage Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jpackage.html
- Oracle JDK 24 — Packaging Overview: https://docs.oracle.com/en/java/javase/24/jpackage/packaging-overview.html
- Oracle JDK 24 — jlink Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jlink.html
- Oracle JDK 24 — jar Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jar.html
- Microsoft — SignTool: https://learn.microsoft.com/en-us/windows/win32/seccrypto/signtool
- Apple — Notarizing macOS Software: https://developer.apple.com/documentation/security/notarizing_macos_software_before_distribution
- Gradle — Java Application Plugin: https://docs.gradle.org/current/userguide/application_plugin.html