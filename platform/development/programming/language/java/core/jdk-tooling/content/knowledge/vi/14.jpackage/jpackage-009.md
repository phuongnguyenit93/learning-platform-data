# Tùy chọn nền tảng của jpackage

**jpackage** là công cụ trong JDK dùng để đóng gói ứng dụng Java thành application image có runtime đi kèm hoặc thành bộ cài đặt theo định dạng quen thuộc của hệ điều hành. Ngoài các tùy chọn chung như tên ứng dụng, phiên bản, biểu tượng và thư mục đầu ra, jpackage cung cấp các **platform-specific options** để cấu hình launcher, shortcut, menu, metadata gói cài đặt và chữ ký theo từng nền tảng.

Các tùy chọn nền tảng chỉ có hiệu lực khi chạy jpackage trên hệ điều hành tương ứng. Ví dụ, **--win-menu** chỉ dành cho Windows; **--linux-package-deps** chỉ dành cho Linux; **--mac-sign** chỉ dành cho macOS. Vì vậy, quy trình phát hành đa nền tảng cần build riêng trên từng hệ điều hành đích.

## 1. jpackage tạo ra những loại đầu ra nào?

Có hai nhóm đầu ra cần phân biệt:

### Application image

Application image là thư mục ứng dụng đã được đóng gói, thường gồm:

- Launcher để khởi chạy ứng dụng.
- JAR hoặc module của ứng dụng.
- Runtime Java được tạo bằng jlink hoặc được cung cấp qua **--runtime-image**.
- Cấu hình và tài nguyên cần thiết.

Có thể tạo application image bằng:

~~~bash
jpackage --type app-image --name HelloDesk --input input --main-jar hello.jar --main-class com.example.Main --dest dist
~~~

Application image hữu ích để kiểm thử và triển khai trực tiếp. Nó chưa phải bộ cài đặt native như MSI, DEB hoặc DMG.

### Native installer/package

jpackage có thể tạo gói cài đặt theo nền tảng:

| Nền tảng | Định dạng phổ biến | Ý nghĩa |
|---|---|---|
| Windows | .exe, .msi | Bộ cài đặt Windows |
| Linux | .deb, .rpm | Gói cài đặt cho các họ phân phối Linux |
| macOS | .pkg, .dmg | Gói cài đặt hoặc ảnh đĩa chứa ứng dụng |

**app-image** có trên các nền tảng được hỗ trợ. Các định dạng installer phụ thuộc hệ điều hành đang chạy và phần mềm đóng gói được cài trên máy build.

Trong JDK 24, danh sách định dạng được tài liệu jpackage mô tả gồm app-image, exe, msi, rpm, deb, pkg và dmg. Khi chạy **jpackage --help**, công cụ chỉ hiển thị các tùy chọn và loại gói hợp lệ trên máy hiện tại. Ví dụ, JDK 24 trên Windows hiển thị app-image, exe và msi; các tùy chọn Linux/macOS sẽ xuất hiện khi chạy trên các hệ điều hành đó.

## 2. Nguyên tắc chọn tùy chọn nền tảng

Một lệnh jpackage thường gồm các nhóm:

1. **Tùy chọn chung:** tên, phiên bản, vendor, mô tả, icon và thư mục đích.
2. **Tùy chọn đầu vào ứng dụng:** thư mục chứa JAR/resource hoặc module path và module chính.
3. **Tùy chọn runtime:** module cần thêm, jlink options hoặc runtime image đã tạo sẵn.
4. **Tùy chọn launcher:** đối số mặc định, JVM options, launcher bổ sung và console behavior.
5. **Tùy chọn package theo hệ điều hành:** installer type, shortcut, menu, metadata, signing hoặc nội dung DMG.

Một số tùy chọn chung thường gặp:

| Tùy chọn | Công dụng |
|---|---|
| --type | Chọn app-image, exe, msi, deb, rpm, pkg hoặc dmg nếu nền tảng hỗ trợ |
| --name | Tên ứng dụng và gói |
| --app-version | Phiên bản ứng dụng/gói |
| --vendor | Nhà cung cấp ứng dụng |
| --description | Mô tả ứng dụng |
| --copyright | Thông tin bản quyền |
| --icon | Đường dẫn icon phù hợp nền tảng |
| --dest | Thư mục chứa đầu ra |
| --install-dir | Vị trí cài đặt theo quy tắc của nền tảng |
| --license-file | Tệp license |
| --about-url | Trang chủ ứng dụng |
| --resource-dir | Thư mục thay thế template hoặc tài nguyên mặc định của jpackage |
| --verbose | In chi tiết quá trình đóng gói |

**--install-dir** có cách diễn giải khác nhau theo hệ điều hành: trên Linux/macOS thường là đường dẫn cài đặt tuyệt đối; trên Windows là đường dẫn con tương đối dưới vị trí cài đặt, ví dụ Program Files hoặc AppData.

### Tùy chọn runtime và launcher

jpackage thường gọi jlink để tạo runtime image cho ứng dụng. Nếu không chỉ định **--runtime-image**, jpackage dùng các tùy chọn jlink mặc định của công cụ; tài liệu JDK 24 nêu các tùy chọn như **--strip-native-commands**, **--strip-debug**, **--no-man-pages** và **--no-header-files**.

Các tùy chọn hữu ích:

- **--runtime-image:** dùng runtime image đã tạo trước bằng jlink.
- **--jlink-options:** truyền tùy chọn bổ sung cho jlink.
- **--add-modules:** thêm module cần thiết vào runtime image.
- **--module-path:** vị trí các module.
- **--module:** module chính và có thể kèm main class.
- **--input:** thư mục chứa các tệp đầu vào của ứng dụng không modular.
- **--main-jar** và **--main-class:** xác định JAR và lớp chính của ứng dụng không modular.
- **--arguments:** đối số mặc định truyền cho main class.
- **--java-options:** tùy chọn truyền cho JVM.
- **--add-launcher:** tạo launcher bổ sung từ một tệp properties.

Chỉ chọn một trong hai cách khai báo điểm vào: **--module** cho ứng dụng modular hoặc **--main-jar** cho ứng dụng JAR thông thường. Không dùng đồng thời cả hai trong cùng cấu hình.

## 3. Tùy chọn riêng cho Windows

Các tùy chọn Windows chỉ có khi chạy jpackage trên Windows.

### Tùy chọn launcher

| Tùy chọn | Công dụng |
|---|---|
| --win-console | Tạo console launcher; dùng cho ứng dụng cần đọc/ghi console như CLI |

Ứng dụng desktop GUI thường không cần console launcher. Công cụ CLI, chương trình tương tác qua terminal hoặc ứng dụng cần hiển thị stdout/stderr nên cân nhắc **--win-console**.

### Tùy chọn installer

| Tùy chọn | Công dụng |
|---|---|
| --win-dir-chooser | Hiển thị hộp thoại cho phép người dùng chọn thư mục cài đặt |
| --win-help-url | URL trợ giúp hoặc hỗ trợ kỹ thuật |
| --win-menu | Tạo yêu cầu thêm shortcut vào Start Menu |
| --win-menu-group | Tên nhóm trong Start Menu |
| --win-per-user-install | Yêu cầu cài đặt theo phạm vi người dùng |
| --win-shortcut | Yêu cầu tạo shortcut trên Desktop |
| --win-shortcut-prompt | Hiển thị lựa chọn để người dùng quyết định có tạo shortcut hay không |
| --win-update-url | URL thông tin cập nhật ứng dụng |
| --win-upgrade-uuid | UUID dùng để nhận diện ứng dụng trong cơ chế nâng cấp |

**--win-menu** và **--win-shortcut** phù hợp khi muốn tích hợp ứng dụng vào trải nghiệm desktop Windows. Nếu dùng **--win-shortcut-prompt**, cần kết hợp với yêu cầu tạo menu hoặc shortcut để installer có lựa chọn tương ứng.

### Ví dụ tạo MSI trên Windows

Giả sử thư mục input chứa hello.jar, trong đó manifest hoặc cấu hình build xác định lớp chính com.example.Main:

~~~powershell
jpackage --type msi --name HelloDesk --input input --main-jar hello.jar --main-class com.example.Main --app-version 1.0.0 --vendor "Example Team" --win-menu --win-menu-group "Example Apps" --win-shortcut --win-dir-chooser --win-per-user-install --dest dist
~~~

Để tạo EXE installer, đổi **--type msi** thành **--type exe**. Nếu ứng dụng là CLI, thêm **--win-console** vào cấu hình launcher.

### Công cụ cần có trên Windows

Để tạo installer EXE/MSI, máy build cần WiX Toolset. JDK 24 hỗ trợ WiX Toolset phiên bản 3, 4 và 5; các bản JDK cũ hơn có thể có yêu cầu WiX khác. Kiểm tra release notes của JDK đang dùng và bảo đảm công cụ WiX được cài đúng cách.

Nếu chỉ tạo **--type app-image**, không cần tạo installer MSI/EXE nên có thể kiểm thử application image trước khi cài các công cụ đóng gói native.

## 4. Tùy chọn riêng cho Linux

Các tùy chọn Linux chỉ có khi chạy jpackage trên Linux. jpackage có thể tạo DEB cho Debian/Ubuntu và RPM cho các hệ thống dùng RPM như Fedora hoặc Red Hat Enterprise Linux.

### Tùy chọn Linux

| Tùy chọn | Công dụng |
|---|---|
| --linux-package-name | Tên package Linux; mặc định theo tên ứng dụng |
| --linux-deb-maintainer | Email người bảo trì package DEB |
| --linux-menu-group | Nhóm menu desktop |
| --linux-package-deps | Khai báo package hoặc capability hệ thống cần thiết |
| --linux-rpm-license-type | Giá trị license trong trường License của RPM spec |
| --linux-app-release | Release của RPM hoặc Debian revision của DEB |
| --linux-app-category | Group của RPM hoặc Section của DEB |
| --linux-shortcut | Yêu cầu tạo shortcut ứng dụng |

### Tạo DEB

Ví dụ tạo gói DEB cho Debian/Ubuntu:

~~~bash
jpackage \
  --type deb \
  --name HelloDesk \
  --input input \
  --main-jar hello.jar \
  --main-class com.example.Main \
  --app-version 1.0.0 \
  --linux-package-name hellodesk \
  --linux-deb-maintainer "packaging@example.com" \
  --linux-app-category utils \
  --linux-menu-group Utility \
  --linux-shortcut \
  --dest dist
~~~

**--linux-deb-maintainer** nhận email người bảo trì package. **--linux-app-category** ánh xạ vào Section trong metadata DEB. Hãy chọn giá trị phù hợp với quy ước của bản phân phối và kho package mục tiêu.

### Tạo RPM

Ví dụ tạo gói RPM:

~~~bash
jpackage \
  --type rpm \
  --name HelloDesk \
  --input input \
  --main-jar hello.jar \
  --main-class com.example.Main \
  --app-version 1.0.0 \
  --linux-package-name hellodesk \
  --linux-rpm-license-type Apache-2.0 \
  --linux-app-release 1 \
  --linux-app-category Applications/Utilities \
  --linux-shortcut \
  --dest dist
~~~

**--linux-rpm-license-type** ghi loại license trong RPM spec. **--linux-app-release** là release của RPM package; với DEB, giá trị này được dùng làm Debian revision.

### Khai báo dependency hệ thống

Nếu ứng dụng phụ thuộc thư viện hệ thống bên ngoài runtime Java, có thể khai báo bằng **--linux-package-deps**. Giá trị cần theo cú pháp package/capability của hệ sinh thái đóng gói và tên package trên bản phân phối mục tiêu.

Không khai báo một dependency chỉ vì nó có trên máy build. Chỉ liệt kê thư viện mà người dùng thực sự cần có khi cài package; kiểm thử installer trên hệ thống sạch để phát hiện dependency bị thiếu.

### Công cụ cần có trên Linux

- Tạo DEB trên Ubuntu cần công cụ **fakeroot** theo hướng dẫn đóng gói của Oracle.
- Tạo RPM trên Red Hat Linux cần package **rpm-build**.
- Cần build trên hệ Linux phù hợp với định dạng package và kiểm thử package trên bản phân phối mục tiêu.

Tên package và dependency có thể khác giữa các phiên bản phân phối. Một gói DEB tạo trên Ubuntu không mặc nhiên phù hợp với mọi bản Debian/Ubuntu; tương tự, RPM có thể phụ thuộc phiên bản hệ thống và dependency metadata.

## 5. Tùy chọn riêng cho macOS

Các tùy chọn macOS chỉ có khi chạy jpackage trên macOS. jpackage có thể tạo application bundle .app, installer .pkg hoặc disk image .dmg.

### Tùy chọn launcher và nhận diện ứng dụng

| Tùy chọn | Công dụng |
|---|---|
| --mac-package-identifier | Định danh duy nhất của ứng dụng trong macOS |
| --mac-package-name | Tên hiển thị trong Menu Bar và cửa sổ thông tin |
| --mac-app-category | Giá trị LSApplicationCategoryType trong Info.plist |

**--mac-package-identifier** mặc định có thể lấy từ main class. Giá trị chỉ nên chứa chữ cái ASCII, chữ số, dấu gạch ngang và dấu chấm. Ví dụ: com.example.hellodesk.

**--mac-package-name** phải ngắn hơn 16 ký tự theo tài liệu JDK 24. Chọn tên ngắn, dễ hiển thị; tên package và tên hiển thị có thể khác nhau.

### Tùy chọn ký số

| Tùy chọn | Công dụng |
|---|---|
| --mac-sign | Yêu cầu ký application image hoặc package |
| --mac-signing-keychain | Chỉ định keychain cần tìm signing identity |
| --mac-signing-key-user-name | Phần tên team hoặc user trong Apple signing identity |
| --mac-package-signing-prefix | Tiền tố cho identifier của các thành phần cần ký nhưng chưa có identifier |
| --mac-entitlements | Đường dẫn tệp entitlements dùng khi ký executable và library |
| --mac-app-store | Đánh dấu đầu ra dành cho Mac App Store |

Ký số giúp xác định nguồn phát hành và hỗ trợ quy trình bảo mật của macOS. Để phân phối rộng rãi, cần thiết kế quy trình code signing và notarization theo yêu cầu Apple; **--mac-sign** tự nó không đồng nghĩa với việc đã hoàn tất notarization.

Xcode command line tools cần thiết khi dùng **--mac-sign** và khi dùng icon tùy chỉnh cho DMG. Signing identity phải có sẵn trong keychain được chỉ định hoặc keychain mặc định.

### Nội dung bổ sung cho DMG

**--mac-dmg-content** cho phép thêm tệp hoặc thư mục vào disk image. Có thể dùng nhiều lần. Ví dụ, thêm tệp hướng dẫn cài đặt hoặc tài liệu đi kèm:

~~~bash
jpackage \
  --type dmg \
  --name HelloDesk \
  --input input \
  --main-jar hello.jar \
  --main-class com.example.Main \
  --app-version 1.0.0 \
  --mac-package-identifier com.example.hellodesk \
  --mac-package-name HelloDesk \
  --mac-app-category public.app-category.utilities \
  --mac-dmg-content docs/README.txt \
  --dest dist
~~~

### Ví dụ ký package trên macOS

~~~bash
jpackage \
  --type pkg \
  --name HelloDesk \
  --input input \
  --main-jar hello.jar \
  --main-class com.example.Main \
  --app-version 1.0.0 \
  --mac-package-identifier com.example.hellodesk \
  --mac-sign \
  --mac-signing-key-user-name "Developer ID Installer: Example Team" \
  --mac-signing-keychain login.keychain-db \
  --mac-entitlements entitlements.plist \
  --dest dist
~~~

Tên signing identity và entitlement phải khớp với tài khoản, loại chứng chỉ và chính sách phát hành thực tế. Ví dụ chỉ minh họa vị trí các tùy chọn; cần thay bằng identity và tệp entitlements hợp lệ của tổ chức.

## 6. Icon, file association và tài nguyên nền tảng

### Icon theo hệ điều hành

Icon cần đúng định dạng mà nền tảng mong đợi:

| Nền tảng | Định dạng thường dùng |
|---|---|
| Windows | .ico |
| Linux | .png |
| macOS | .icns |

Có thể truyền icon bằng **--icon**. Nếu dùng **--resource-dir**, jpackage có thể lấy tài nguyên thay thế theo tên quy ước, ví dụ launcher-name.ico trên Windows, launcher-name.png trên Linux và launcher-name.icns trên macOS.

### File association

**--file-associations** nhận tệp properties mô tả loại file mà ứng dụng đăng ký xử lý. Các khóa thường dùng gồm:

~~~properties
extension=hello
mime-type=application/x-hello
description=HelloDesk document
icon=hello-document.ico
~~~

Có thể dùng nhiều tệp association. Icon và cách đăng ký association phụ thuộc nền tảng; kiểm tra package sau khi cài trên hệ điều hành đích.

### Resource directory

**--resource-dir** cho phép thay template hoặc tài nguyên mặc định của jpackage. Đây là khả năng tùy biến sâu cho quy trình đóng gói, ví dụ desktop file trên Linux, icon launcher, WiX template trên Windows hoặc tài nguyên bundle trên macOS.

Chỉ thay resource khi đã hiểu cấu trúc và vòng đời của file template. Một template sai có thể khiến installer lỗi, shortcut không tạo được hoặc package macOS không đáp ứng yêu cầu ký số.

## 7. Ví dụ chuẩn bị ứng dụng dùng chung cho các nền tảng

Các ví dụ nền tảng ở trên giả định đã có **input/hello.jar**. Có thể tạo JAR nhỏ bằng JDK 17 trở lên.

Tệp src/com/example/Main.java:

~~~java
package com.example;

public class Main {
    public static void main(String[] args) {
        String name = args.length == 0 ? "Java" : args[0];
        System.out.println("Hello, " + name + "!");
    }
}
~~~

Tạo thư mục đầu vào:

~~~bash
mkdir -p input
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force input
~~~

Biên dịch:

~~~bash
javac --release 17 -d out src/com/example/Main.java
~~~

Đóng gói JAR với Main-Class:

~~~bash
jar --create --file input/hello.jar --main-class com.example.Main -C out .
~~~

Sau đó chạy jpackage trên từng hệ điều hành đích và chọn **--type** phù hợp. JAR này là non-modular; nếu ứng dụng modular, dùng **--module-path** và **--module** thay cho **--input**/**--main-jar**.

### Kiểm thử application image trước khi tạo installer

Có thể tạo application image:

~~~bash
jpackage --type app-image --name HelloDesk --input input --main-jar hello.jar --dest dist
~~~

Chạy launcher nằm trong application image để kiểm tra runtime và resource. Khi image hoạt động đúng, dùng **--app-image** để tạo installer native trên cùng hệ điều hành.

Ví dụ trên Windows, nếu application image được tạo ở dist/HelloDesk:

~~~powershell
jpackage --type msi --name HelloDesk --app-image dist/HelloDesk --win-menu --win-shortcut --dest installer
~~~

Trên macOS, application image thường là bundle HelloDesk.app; có thể dùng bundle đó làm đầu vào cho PKG hoặc DMG. Trên Linux, dùng thư mục application image để tạo DEB hoặc RPM.

## 8. Build đa nền tảng và kiến trúc CPU

jpackage không hỗ trợ cross-platform packaging: gói native phải được tạo trên hệ điều hành mà nó nhắm tới. Không thể chạy jpackage trên Windows để tạo trực tiếp DEB cho Linux hoặc DMG cho macOS.

Một pipeline phát hành đa nền tảng thường có các job riêng:

| Build agent | Đầu ra | Việc cần xác minh |
|---|---|---|
| Windows | app-image, EXE, MSI | WiX, shortcut, install scope, uninstall và launcher |
| Linux | app-image, DEB, RPM | Package metadata, dependency, desktop entry và cài/gỡ |
| macOS | app bundle, PKG, DMG | Bundle structure, icon, code signing và notarization |

Ngoài hệ điều hành, cần chú ý kiến trúc CPU:

- Chọn JDK và runtime image tương thích với kiến trúc mục tiêu.
- Kiểm tra JNI và native libraries có đúng OS, CPU architecture và ABI.
- Nếu phát hành cho cả x64 và ARM64, xây dựng và kiểm thử artifact cho từng kiến trúc theo toolchain hỗ trợ.
- Không trộn runtime image hoặc native library của nền tảng khác vào package hiện tại.

Có thể dùng CI với runner Windows, Linux và macOS để tạo artifact tương ứng. Mỗi job nên ghi lại JDK vendor/version, OS, kiến trúc, loại package và các tùy chọn jpackage.

## 9. Lỗi thường gặp

### Option không được nhận diện

Một tùy chọn như **--win-menu** chỉ có trên Windows. Nếu chạy trên Linux hoặc macOS, jpackage có thể báo tùy chọn không hợp lệ. Kiểm tra **jpackage --help** trên đúng build agent và chỉ truyền tùy chọn của nền tảng đó.

### Không tạo được EXE/MSI

Máy Windows có thể thiếu WiX hoặc PATH chưa nhận diện đúng công cụ. Kiểm tra WiX version, JDK release và thông báo lỗi từ jpackage.

### Không tạo được DEB hoặc RPM

Kiểm tra công cụ đóng gói tương ứng: **fakeroot** cho quy trình DEB trên Ubuntu hoặc **rpm-build** cho RPM trên Red Hat Linux. Cũng kiểm tra quyền truy cập thư mục đích và metadata package.

### Không ký được package macOS

Kiểm tra Xcode command line tools, signing identity, keychain, entitlements và quyền truy cập certificate. Đảm bảo identifier và tài nguyên bundle hợp lệ. Nếu phân phối ngoài môi trường nội bộ, hoàn thiện quy trình notarization riêng theo yêu cầu Apple.

### Icon không xuất hiện hoặc sai định dạng

Dùng đúng định dạng icon cho hệ điều hành đích và kiểm tra đường dẫn tương đối/tuyệt đối. Với **--resource-dir**, tên tệp phải khớp quy ước tài nguyên mà jpackage tìm kiếm.

### Package cài được nhưng ứng dụng không khởi chạy

Kiểm tra main class/JAR hoặc module, dependency, runtime image, đối số mặc định, JVM options và resource. Chạy thử application image trước khi tạo installer để tách lỗi launcher/runtime khỏi lỗi installer.

### Dependency Linux bị thiếu

Khai báo package hệ thống thực sự cần bằng **--linux-package-deps** và kiểm thử trên bản phân phối sạch. Tên dependency phải đúng với hệ package manager đích.

### Gói được tạo trên sai OS hoặc kiến trúc

Tạo artifact native trên build agent đúng nền tảng và kiến trúc. Không dùng installer của một OS làm đầu ra cho OS khác; kiểm tra native libraries và runtime image trước khi phát hành.

## 10. Checklist đóng gói theo nền tảng

- Chọn rõ **--type**; không dựa vào default platform type trong build release.
- Xác định ứng dụng modular hay non-modular và chọn **--module** hoặc **--main-jar**.
- Kiểm tra JAR, module, resource và dependency trước khi đóng gói.
- Chọn icon đúng định dạng: ICO, PNG hoặc ICNS.
- Dùng **--app-image** để kiểm thử launcher/runtime trước khi tạo installer.
- Chỉ dùng **--win-*** trên Windows, **--linux-*** trên Linux và **--mac-*** trên macOS.
- Cài đủ công cụ native: WiX trên Windows, fakeroot/rpm-build trên Linux và Xcode command line tools khi cần trên macOS.
- Khai báo đúng shortcut, menu group, install directory, package dependency và metadata.
- Dùng signing identity và entitlements hợp lệ khi ký ứng dụng macOS.
- Kiểm tra code signing và notarization theo yêu cầu phát hành của Apple.
- Build riêng cho từng OS và kiến trúc CPU mục tiêu.
- Cài, chạy, nâng cấp và gỡ package trên môi trường sạch tương ứng.
- Lưu JDK version, OS, architecture, package type và lệnh build để tái lập artifact.

## 11. Thuật ngữ cần nhớ

| Thuật ngữ | Ý nghĩa |
|---|---|
| jpackage | Công cụ đóng gói ứng dụng Java thành application image hoặc installer |
| Platform-specific option | Tùy chọn chỉ có trên một hệ điều hành |
| Application image | Thư mục ứng dụng có launcher và runtime cần thiết |
| Native installer | Gói cài đặt theo định dạng của hệ điều hành |
| MSI / EXE | Định dạng installer Windows |
| DEB / RPM | Định dạng package Linux |
| PKG / DMG | Định dạng installer hoặc disk image trên macOS |
| WiX Toolset | Công cụ tạo installer Windows được jpackage sử dụng |
| File association | Liên kết phần mở rộng file với ứng dụng |
| Signing identity | Danh tính/chứng chỉ dùng ký ứng dụng |
| Entitlements | Quyền được cấp cho ứng dụng macOS đã ký |
| Notarization | Quy trình Apple kiểm tra phần mềm trước khi phân phối |
| Runtime image | Runtime Java được jlink tạo hoặc cung cấp sẵn |
| Resource directory | Thư mục chứa template và tài nguyên thay thế cho jpackage |

Tùy chọn nền tảng của jpackage giúp tích hợp ứng dụng Java với cách cài đặt và khởi chạy quen thuộc trên từng hệ điều hành. Hãy chọn đúng installer type, dùng đúng tùy chọn của Windows/Linux/macOS, build trên nền tảng đích và kiểm thử package như người dùng cuối sẽ cài đặt.

## Tài liệu tham khảo

- Oracle JDK 24 — The jpackage Command: https://docs.oracle.com/en/java/javase/24/docs/specs/man/jpackage.html
- Oracle JDK 24 — Packaging Overview: https://docs.oracle.com/en/java/javase/24/jpackage/packaging-overview.html
- Oracle — JDK 24 Release Notes, WiX Toolset support: https://www.oracle.com/java/technologies/javase/24-relnote-issues.html