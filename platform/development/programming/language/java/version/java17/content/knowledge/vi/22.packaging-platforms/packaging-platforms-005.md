# Tạo app-image và bộ cài ứng dụng bằng jpackage trong Java 17

Khi phát triển ứng dụng Java, việc đưa một file JAR cho người dùng thường chưa đủ. Người dùng có thể chưa cài Java, không biết phải chạy lệnh nào hoặc không có cách cài đặt và gỡ ứng dụng theo quy trình của hệ điều hành. Công cụ **jpackage** trong JDK giải quyết phần đóng gói này: nó tạo một application image có launcher và runtime đi kèm, hoặc tạo bộ cài native phù hợp với hệ điều hành.

Trong Java 17, jpackage là công cụ chính thức nằm trong JDK. Nó có thể đóng gói ứng dụng dạng classpath hoặc modular application, tạo runtime image bằng jlink hoặc nhận một runtime image đã chuẩn bị sẵn. Từ app-image, nhóm phát triển có thể kiểm tra ứng dụng độc lập trước khi tạo installer.

Bài học này giải thích sự khác nhau giữa app-image và installer, cách đóng gói ứng dụng classpath/modular, cách tùy chỉnh runtime và launcher, các định dạng bộ cài theo hệ điều hành, metadata, signing và quy trình kiểm tra bản phát hành.

## 1. jpackage là gì?

**jpackage** là công cụ đóng gói ứng dụng Java thành một gói có thể phân phối cho người dùng. Nó tạo ra:

- **Application image (app-image):** một thư mục ứng dụng chứa launcher, payload của ứng dụng và Java runtime cần thiết.
- **Native installer/package:** bộ cài sử dụng định dạng của hệ điều hành, ví dụ MSI/EXE trên Windows, DMG/PKG trên macOS, DEB/RPM trên Linux.

Ứng dụng được đóng gói theo cách này có thể chạy bằng runtime đi kèm. Người dùng cuối không cần cài riêng JDK để chạy ứng dụng, miễn là runtime image đã bao gồm các module Java mà ứng dụng cần.

### 1.1. App-image và installer khác nhau thế nào?

| Tiêu chí | App-image | Native installer |
| --- | --- | --- |
| Kết quả | Thư mục ứng dụng đã đóng gói | File bộ cài theo nền tảng |
| Cách sử dụng | Chạy launcher bên trong thư mục | Mở/chạy bộ cài để cài ứng dụng |
| Runtime | Có thể chứa runtime riêng | Thường cài app-image cùng runtime vào vị trí cài đặt |
| Cài đặt/gỡ bỏ | Người triển khai tự phân phối và xóa thư mục | Tích hợp cơ chế cài/gỡ của nền tảng |
| Shortcut/menu | Có thể tạo launcher, nhưng không tự tạo trải nghiệm cài đặt như installer | Có tùy chọn tạo shortcut/menu theo nền tảng |
| Phù hợp | Kiểm thử, phân phối dạng portable theo hệ điều hành, làm đầu vào cho installer | Phân phối cho người dùng cuối theo quy trình hệ điều hành |

App-image không phải file JAR và cũng không phải một gói có thể dùng chung cho mọi hệ điều hành. Nó chứa launcher và runtime phù hợp với nền tảng, kiến trúc đã build. Nếu muốn phát hành Windows, macOS và Linux, cần tạo artifact tương ứng trên các môi trường build phù hợp.

## 2. Kiểm tra jpackage trong JDK 17

jpackage nằm trong thư mục `bin` của JDK:

~~~bash
jpackage --version
jpackage --help
~~~

Nếu shell không tìm thấy lệnh, kiểm tra `JAVA_HOME` và PATH:

~~~bash
java --version
javac --version
where jpackage
~~~

Trên Linux/macOS, dùng `which jpackage` hoặc `command -v jpackage`.

Hãy dùng jpackage từ đúng JDK 17 mà nhóm chọn để build và kiểm tra sản phẩm. Công cụ đóng gói và runtime đi kèm cần có phiên bản được quản lý rõ ràng trong pipeline phát hành.

## 3. Chuẩn bị ứng dụng trước khi đóng gói

Trước khi gọi jpackage, cần có artifact ứng dụng đã build thành công. Có hai kiểu đầu vào phổ biến:

1. Ứng dụng classpath: một main JAR, có thể đi kèm các JAR dependency.
2. Ứng dụng modular: module chính và các module dependency trên module path.

Hãy xác định:

- tên launcher và tên hiển thị của ứng dụng;
- main class hoặc module entry point;
- các thư viện phụ thuộc;
- module Java mà ứng dụng cần, ví dụ `java.sql` hoặc `java.desktop`;
- file cấu hình, resource và dữ liệu mặc định cần đóng gói;
- phiên bản, vendor, icon và metadata;
- hệ điều hành/kiến trúc mục tiêu.

Không đưa mật khẩu, API key, private key, token hoặc dữ liệu khách hàng vào thư mục input. Mọi file trong payload có thể được trích xuất từ app-image hoặc installer.

## 4. Đóng gói ứng dụng classpath thành app-image

Giả sử ứng dụng đã được build:

~~~text
build/
└── package-input/
    ├── acme-desk.jar
    ├── library-a.jar
    └── library-b.jar
~~~

Ứng dụng có main class `com.acme.desktop.Main`. Tạo app-image:

~~~bash
jpackage \
    --type app-image \
    --name AcmeDesk \
    --input build/package-input \
    --main-jar acme-desk.jar \
    --main-class com.acme.desktop.Main \
    --app-version 1.2.0 \
    --vendor "Acme Software" \
    --description "Ứng dụng quản lý công việc" \
    --dest build/dist
~~~

Giải thích:

- `--type app-image`: yêu cầu tạo thư mục ứng dụng.
- `--name`: tên ứng dụng và tên artifact chính.
- `--input`: thư mục chứa JAR chính cùng các file đầu vào khác.
- `--main-jar`: JAR khởi chạy, đường dẫn tính tương đối với input directory.
- `--main-class`: lớp có phương thức main.
- `--app-version`, `--vendor`, `--description`: metadata của ứng dụng.
- `--dest`: thư mục nhận kết quả.

Sau khi chạy thành công, thư mục đích sẽ có application image tên `AcmeDesk` (cấu trúc bên trong phụ thuộc hệ điều hành). Thư mục image thường chứa launcher, payload trong thư mục app và runtime.

### 4.1. Dependency của classpath application

jpackage không tự giải quyết dependency như một công cụ quản lý dependency. Các JAR cần thiết phải được đưa vào input directory hoặc được đóng gói theo cách ứng dụng có thể tìm thấy.

Nếu main JAR dùng manifest `Class-Path`, kiểm tra các đường dẫn tương đối trỏ tới dependency vẫn đúng sau khi jpackage copy payload. Với ứng dụng dùng framework hoặc custom class loader, hãy kiểm tra cách framework tìm resource và thư viện ở vị trí cài đặt.

### 4.2. Chạy thử app-image

Đường dẫn launcher thay đổi theo nền tảng:

~~~text
Windows: build/dist/AcmeDesk/AcmeDesk.exe
Linux:   build/dist/AcmeDesk/bin/AcmeDesk
macOS:   build/dist/AcmeDesk.app/Contents/MacOS/AcmeDesk
~~~

Các đường dẫn trên minh họa bố cục thường gặp. Hãy mở launcher từ chính app-image đã tạo và kiểm tra:

- ứng dụng khởi động mà không cần JDK cài riêng;
- resource và dependency được tìm thấy;
- file cấu hình được đọc từ vị trí mong muốn;
- ứng dụng có thể ghi dữ liệu vào thư mục người dùng được phép;
- launcher hoạt động khi chạy từ working directory khác.

## 5. Đóng gói modular application

Với ứng dụng modular, module descriptor khai báo module chính và các dependency:

~~~java
module com.acme.desktop {
    requires java.desktop;
    requires com.acme.services;
}
~~~

Giả sử các module đã được biên dịch hoặc đóng gói trong `build/mods`:

~~~text
build/mods/
├── com.acme.desktop/
├── com.acme.services/
└── com.acme.common/
~~~

Tạo app-image:

~~~bash
jpackage \
    --type app-image \
    --name AcmeDesk \
    --module-path build/mods \
    --module com.acme.desktop/com.acme.desktop.Main \
    --app-version 1.2.0 \
    --vendor "Acme Software" \
    --dest build/dist
~~~

`--module-path` chỉ nơi tìm module. `--module` có dạng `module-name[/main-class]`; phần main class có thể được bỏ nếu module descriptor khai báo main class phù hợp. Module chính và các module cần thiết phải có mặt trên module path.

Với modular application, jpackage sử dụng thông tin module để tạo launcher và runtime image. Nếu có module được nạp động, dùng reflection, service loading hoặc phụ thuộc không thể suy ra đầy đủ từ module graph, cần kiểm tra runtime image và bổ sung module cần thiết khi cấu hình.

## 6. Runtime image và jlink

Một lợi ích quan trọng của jpackage là đóng gói runtime cùng ứng dụng. Nếu không cung cấp runtime image có sẵn, jpackage tạo runtime image bằng jlink. Nhờ vậy, người dùng cuối có thể chạy ứng dụng mà không cần cài JDK riêng.

Runtime image chỉ chứa môi trường chạy, không phải toàn bộ JDK với compiler, debugger và các công cụ phát triển.

### 6.1. Tùy chỉnh module trong runtime image

Có thể chỉ định các module bổ sung bằng `--add-modules` và module path bằng `--module-path` khi jpackage tạo runtime. Ví dụ:

~~~bash
jpackage \
    --type app-image \
    --name AcmeDesk \
    --input build/package-input \
    --main-jar acme-desk.jar \
    --main-class com.acme.desktop.Main \
    --add-modules java.desktop,java.logging,java.sql \
    --dest build/dist
~~~

Ví dụ trên minh họa việc bổ sung các module JDK mà ứng dụng cần. Danh sách chính xác phải dựa trên dependency thực tế; thêm quá nhiều module làm runtime image lớn hơn, thiếu module có thể khiến ứng dụng lỗi khi chạy.

`--add-modules` không thay thế việc đưa JAR dependency của ứng dụng vào payload. Nó chỉ điều khiển module Java được đưa vào runtime image.

### 6.2. Tạo runtime image riêng bằng jlink

Nếu muốn kiểm soát runtime rõ ràng hơn, có thể chạy jlink trước:

~~~bash
jlink \
    --module-path "$JAVA_HOME/jmods:build/mods" \
    --add-modules com.acme.desktop \
    --strip-debug \
    --no-header-files \
    --no-man-pages \
    --output build/runtime
~~~

Trên Windows, module path dùng dấu phân cách `;` thay cho `:`. Các module dependency của `com.acme.desktop` cần có trong module path và được giải quyết thành công. Với ứng dụng classpath, phải xác định các module JDK mà ứng dụng cần và thêm chúng tường minh; jlink không thể suy luận đầy đủ mọi dependency được nạp động qua reflection.

Đưa runtime image đã tạo vào jpackage:

~~~bash
jpackage \
    --type app-image \
    --name AcmeDesk \
    --input build/package-input \
    --main-jar acme-desk.jar \
    --main-class com.acme.desktop.Main \
    --runtime-image build/runtime \
    --dest build/dist
~~~

Khi dùng `--runtime-image`, jpackage sử dụng runtime có sẵn thay vì tự tạo runtime bằng jlink. Chọn một quy trình quản lý runtime nhất quán; kiểm tra tài liệu JDK 17 khi kết hợp với các tùy chọn cấu hình runtime khác.

### 6.3. Tối ưu kích thước runtime

Một số tùy chọn jlink thường dùng:

| Tùy chọn | Tác dụng |
| --- | --- |
| `--strip-debug` | Loại bỏ thông tin debug khỏi runtime image. |
| `--no-header-files` | Không đưa header file native vào runtime image. |
| `--no-man-pages` | Không đưa man page vào runtime image. |
| `--compress` | Nén tài nguyên trong runtime image theo mức hỗ trợ của JDK. |
| `--add-modules` | Chọn module cần đưa vào runtime image. |
| `--bind-services` | Thêm các module provider của service được tham chiếu trong module graph theo quy tắc của jlink. |

jpackage có tùy chọn `--jlink-options` để chuyển các tùy chọn thích hợp cho jlink khi nó tạo runtime image. Ví dụ:

~~~bash
jpackage \
    --type app-image \
    --name AcmeDesk \
    --module-path build/mods \
    --module com.acme.desktop/com.acme.desktop.Main \
    --jlink-options "--strip-debug --no-header-files --no-man-pages" \
    --dest build/dist
~~~

Đo kích thước và kiểm thử runtime sau khi strip/compress. Không loại bỏ module chỉ dựa trên kích thước nếu ứng dụng cần chúng qua reflection, service loading hoặc plugin.

## 7. Tạo native installer

Sau khi app-image chạy đúng, có thể tạo installer bằng cách đổi `--type` sang định dạng của nền tảng:

| Hệ điều hành build | Định dạng thường hỗ trợ trong JDK 17 |
| --- | --- |
| Windows | `exe`, `msi` |
| macOS | `dmg`, `pkg` |
| Linux | `deb`, `rpm` |
| Các nền tảng trên | `app-image` |

Định dạng native có sẵn phụ thuộc nền tảng và công cụ đóng gói đã cài. jpackage không tạo một installer Windows trên máy Linux hoặc một gói macOS trên Windows.

### 7.1. Installer Windows

Tạo MSI:

~~~powershell
jpackage --type msi --name AcmeDesk --input build/package-input --main-jar acme-desk.jar --main-class com.acme.desktop.Main --app-version 1.2.0 --vendor "Acme Software" --win-menu --win-shortcut --win-dir-chooser --dest build\installer
~~~

Các tùy chọn Windows thường dùng:

- `--win-menu`: tạo mục trong Start Menu.
- `--win-shortcut`: tạo shortcut.
- `--win-dir-chooser`: cho phép người dùng chọn thư mục cài đặt.
- `--win-per-user-install`: cấu hình cài đặt theo người dùng trong các trường hợp được hỗ trợ.
- `--win-upgrade-uuid`: định danh nâng cấp MSI; cần được quản lý ổn định qua các phiên bản phát hành của cùng sản phẩm.
- `--win-console`: giữ console cho ứng dụng console khi phù hợp.

Trên Windows, jpackage cần bộ công cụ đóng gói tương ứng; JDK 17 yêu cầu WiX Toolset phiên bản 3.0 trở lên để tạo định dạng EXE/MSI. Cài đặt và cấu hình công cụ theo tài liệu của JDK mục tiêu trước khi chạy pipeline.

### 7.2. Installer macOS

Tạo DMG:

~~~bash
jpackage \
    --type dmg \
    --name AcmeDesk \
    --input build/package-input \
    --main-jar acme-desk.jar \
    --main-class com.acme.desktop.Main \
    --app-version 1.2.0 \
    --vendor "Acme Software" \
    --mac-package-identifier com.acme.desktop \
    --dest build/installer
~~~

Một số tùy chọn macOS:

- `--mac-package-identifier`: bundle/package identifier ổn định, thường theo reverse-DNS.
- `--mac-package-name`: tên package hiển thị.
- `--mac-app-category`: category của ứng dụng.
- `--mac-dmg-content`: nội dung bổ sung hiển thị trong DMG.
- `--mac-sign`: yêu cầu ký ứng dụng/package trong quy trình hỗ trợ.
- `--mac-signing-key-user-name` và `--mac-signing-keychain`: chọn identity/keychain cho signing.
- `--mac-entitlements`: file entitlements dùng trong quá trình ký khi phù hợp.

Để phát hành ra ngoài, kiểm tra yêu cầu code signing và notarization hiện hành của Apple. Tạo được DMG/PKG không tự động có nghĩa ứng dụng đã được ký, notarize và sẵn sàng vượt mọi chính sách bảo mật trên máy người dùng.

### 7.3. Package Linux

Tạo DEB:

~~~bash
jpackage \
    --type deb \
    --name acme-desk \
    --input build/package-input \
    --main-jar acme-desk.jar \
    --main-class com.acme.desktop.Main \
    --app-version 1.2.0 \
    --linux-package-name acme-desk \
    --linux-deb-maintainer "release@example.invalid" \
    --linux-shortcut \
    --dest build/installer
~~~

Địa chỉ maintainer trong ví dụ là placeholder; thay bằng thông tin hợp lệ của đơn vị phát hành. Không dùng địa chỉ giả trong package thật.

Các tùy chọn Linux thường gặp:

- `--linux-package-name`: tên package.
- `--linux-deb-maintainer`: thông tin maintainer cho DEB.
- `--linux-menu-group`: nhóm menu.
- `--linux-package-deps`: dependency hệ điều hành cần khai báo.
- `--linux-rpm-license-type`: license type theo metadata RPM.
- `--linux-app-release`: release number của package.
- `--linux-app-category`: category ứng dụng.
- `--linux-shortcut`: tạo shortcut desktop khi nền tảng hỗ trợ.

DEB cần công cụ đóng gói Debian phù hợp như `dpkg-deb`; RPM cần công cụ tương ứng như `rpmbuild`. Kiểm tra các công cụ và phiên bản trên máy build theo tài liệu JDK 17 và hệ điều hành mục tiêu.

## 8. Đóng gói installer từ app-image đã kiểm tra

Tách hai giai đoạn có lợi khi muốn kiểm tra app-image trước rồi mới tạo installer. jpackage hỗ trợ `--app-image` để dùng application image có sẵn làm đầu vào:

~~~bash
jpackage --type msi --name AcmeDesk --app-image build/dist/AcmeDesk --dest build/installer
~~~

Ví dụ này dành cho máy Windows đã có app-image Windows được tạo và kiểm tra trên môi trường tương thích. Trên macOS hoặc Linux, thay loại package và app-image tương ứng với nền tảng.

Lợi ích của quy trình:

1. Build app-image một lần cho nền tảng mục tiêu.
2. Chạy launcher và kiểm tra runtime/dependency.
3. Sau khi xác nhận, tạo installer từ app-image.
4. Cài installer trên máy kiểm thử sạch.

App-image và installer phải cùng nền tảng, kiến trúc và runtime assumptions. Không dùng app-image của Linux làm đầu vào để tạo MSI trên Windows.

## 9. Tùy chỉnh launcher, icon và tài nguyên

### 9.1. Icon và metadata

Có thể truyền icon bằng `--icon`:

~~~bash
jpackage \
    --type app-image \
    --name AcmeDesk \
    --input build/package-input \
    --main-jar acme-desk.jar \
    --main-class com.acme.desktop.Main \
    --icon src/packaging/acme-desk.png \
    --app-version 1.2.0 \
    --vendor "Acme Software" \
    --copyright "Copyright 2026 Acme Software" \
    --dest build/dist
~~~

Định dạng icon được hỗ trợ phụ thuộc nền tảng và loại package. Ví dụ, Windows thường dùng ICO, macOS dùng ICNS, Linux thường dùng PNG. Dùng đúng định dạng/kích thước theo yêu cầu của JDK và nền tảng đích.

Metadata có thể bao gồm:

- `--app-version`;
- `--vendor`;
- `--description`;
- `--copyright`;
- `--about-url`;
- `--license-file`.

Metadata nên nhất quán với thông tin phát hành, giấy phép và thương hiệu của ứng dụng.

### 9.2. Thêm file cấu hình hoặc nội dung đi kèm

`--input` đưa các file đầu vào vào payload của ứng dụng. `--app-content` cho phép thêm nội dung ứng dụng bổ sung theo tùy chọn của jpackage. `--resource-dir` cho phép cung cấp tài nguyên tùy chỉnh cho quá trình đóng gói, chẳng hạn template hoặc icon của installer theo nền tảng.

Ví dụ:

~~~bash
jpackage \
    --type app-image \
    --name AcmeDesk \
    --input build/package-input \
    --main-jar acme-desk.jar \
    --main-class com.acme.desktop.Main \
    --app-content build/default-config \
    --resource-dir src/packaging/resources \
    --dest build/dist
~~~

Chỉ đưa file cấu hình mặc định và resource không bí mật vào gói. File cấu hình môi trường, credential và secret nên được cung cấp qua cơ chế cấu hình an toàn sau khi cài đặt.

### 9.3. Tạo launcher bổ sung bằng --add-launcher

Một ứng dụng có thể cung cấp nhiều launcher, ví dụ launcher chính và công cụ quản trị. Tạo file properties:

**admin.properties**

~~~properties
main-class=com.acme.desktop.AdminMain
arguments=--mode,admin
java-options=-Xmx1g
~~~

Gọi jpackage:

~~~bash
jpackage \
    --type app-image \
    --name AcmeDesk \
    --input build/package-input \
    --main-jar acme-desk.jar \
    --main-class com.acme.desktop.Main \
    --add-launcher admin=src/packaging/admin.properties \
    --dest build/dist
~~~

Launcher bổ sung có thể kế thừa một số thuộc tính từ launcher chính và ghi đè các thuộc tính được khai báo trong file properties. Kiểm tra tài liệu JDK 17 để biết các thuộc tính hỗ trợ và quy tắc kế thừa chính xác.

## 10. Truyền tham số và tùy chọn JVM

`--arguments` đặt tham số mặc định truyền cho ứng dụng. `--java-options` đặt tùy chọn cho JVM chạy ứng dụng:

~~~bash
jpackage \
    --type app-image \
    --name AcmeDesk \
    --input build/package-input \
    --main-jar acme-desk.jar \
    --main-class com.acme.desktop.Main \
    --arguments "--profile,desktop" \
    --java-options "-Dfile.encoding=UTF-8" \
    --java-options "-Xms256m" \
    --java-options "-Xmx2g" \
    --dest build/dist
~~~

Phân biệt:

- `--arguments`: đối số ứng dụng nhận trong `main(String[] args)`.
- `--java-options`: cờ JVM, ví dụ system property, heap size hoặc module option.

Không đặt secret trong `--arguments` hoặc `--java-options`: giá trị có thể xuất hiện trong file cấu hình launcher hoặc thông tin hệ thống. Với secret, dùng secret manager hoặc cơ chế cấp credential phù hợp lúc chạy.

## 11. Cấu hình nền tảng và yêu cầu build

jpackage tạo native package theo nền tảng đang chạy. Pipeline phát hành đa nền tảng thường cần các worker build riêng:

| Artifact | Môi trường build | Kiểm tra cần có |
| --- | --- | --- |
| Windows EXE/MSI | Windows | JDK 17, WiX Toolset tương thích, signing tool nếu cần ký |
| macOS DMG/PKG | macOS | JDK 17, công cụ Apple phù hợp, signing identity và notarization workflow khi phát hành |
| Linux DEB | Linux phù hợp | JDK 17 và công cụ tạo DEB |
| Linux RPM | Linux phù hợp | JDK 17 và công cụ tạo RPM |
| App-image | OS/architecture đích | JDK 17 và runtime phù hợp; app-image vẫn mang tính nền tảng |

Không nên coi một artifact build trên một hệ điều hành là bộ cài dùng được trên hệ điều hành khác. Hãy tạo artifact trên runner/VM tương ứng với OS và kiến trúc phát hành.

## 12. Code signing và tính toàn vẹn của bản phát hành

Native installer có thể cần chữ ký số để hệ điều hành xác minh nhà phát hành và tính toàn vẹn:

- Windows: ký file thực thi và installer bằng công cụ ký code của hệ sinh thái Windows, sau đó xác minh chữ ký.
- macOS: ký ứng dụng/package bằng identity phù hợp; với phân phối ngoài App Store, thực hiện quy trình notarization theo yêu cầu Apple.
- Linux: ký repository metadata hoặc package theo mô hình phân phối của tổ chức và repository.

jpackage cung cấp một số tùy chọn signing cho macOS; không nên giả định một lệnh jpackage duy nhất tự hoàn tất mọi bước signing, timestamping, notarization hoặc phân phối. Quản lý certificate/private key trong secret store của CI, hạn chế quyền truy cập và không đưa private key vào app-image.

Sau khi ký:

1. Xác minh chữ ký trên artifact cuối.
2. Tính checksum và lưu cùng metadata phát hành.
3. Kiểm tra artifact sau bước ký là artifact đã được kiểm thử.
4. Lưu log build và provenance theo chính sách phát hành.

## 13. Phiên bản, cài đặt nâng cấp và gỡ bỏ

`--app-version` đặt phiên bản ứng dụng trong package. Với Windows MSI, `--win-upgrade-uuid` là mã định danh nâng cấp của sản phẩm và cần được quản lý ổn định giữa các bản nâng cấp của cùng sản phẩm. Trên macOS, bundle/package identifier cũng cần ổn định.

Đừng nhầm jpackage với hệ thống auto-update. jpackage tạo app-image và installer; việc phát hiện phiên bản mới, tải bản cập nhật, xác minh, cài đặt im lặng hoặc rollback cần được thiết kế bằng cơ chế phân phối/cập nhật riêng hoặc dựa vào package manager của nền tảng.

Khi thiết kế nâng cấp, xác định:

- installer mới có nâng cấp bản cũ hay cài song song;
- dữ liệu người dùng được lưu ở đâu;
- file cấu hình có được giữ lại qua upgrade không;
- schema dữ liệu có cần migration không;
- uninstall có xóa dữ liệu người dùng hay giữ lại;
- rollback được thực hiện thế nào nếu bản mới không khởi động.

Không lưu dữ liệu người dùng lâu dài bên trong thư mục cài ứng dụng nếu installer có thể thay thế hoặc xóa thư mục đó. Dùng vị trí dữ liệu người dùng phù hợp với hệ điều hành.

## 14. Kiểm thử app-image và installer

Một lệnh jpackage chạy thành công chỉ chứng minh công cụ tạo được artifact. Nó chưa chứng minh ứng dụng chạy đúng trên máy người dùng.

Quy trình kiểm thử nên gồm:

1. **Kiểm tra app-image:** mở launcher và xác nhận ứng dụng khởi động.
2. **Máy sạch:** kiểm tra trên máy/VM không cài JDK riêng để xác nhận runtime đi kèm đủ dùng.
3. **Dependency:** kiểm tra tất cả thư viện, native library, resource và service provider.
4. **Working directory:** chạy launcher từ shortcut hoặc đường dẫn khác với thư mục cài đặt.
5. **Quyền ghi:** xác nhận ứng dụng ghi log, cache và dữ liệu người dùng vào vị trí có quyền.
6. **Cài đặt:** cài package trên OS/phiên bản được hỗ trợ.
7. **Nâng cấp:** nâng từ bản trước và kiểm tra dữ liệu người dùng.
8. **Gỡ cài đặt:** xác nhận file chương trình được xóa và dữ liệu người dùng được xử lý theo chính sách.
9. **Signing:** xác minh chữ ký và cảnh báo của hệ điều hành.
10. **Kiến trúc:** kiểm tra đúng x64/ARM64 hoặc kiến trúc đã công bố.

### 14.1. Kiểm tra launcher trên máy không có JDK

Nếu ứng dụng chạy được chỉ khi máy developer đã cài JDK, có thể app-image đang thiếu runtime/module hoặc ứng dụng đang vô tình dùng Java từ PATH. Hãy kiểm thử trong môi trường sạch và xác nhận launcher dùng runtime nằm trong image.

### 14.2. Kiểm tra runtime thiếu module

Các lỗi thường gặp khi runtime image bị tối giản:

- `ClassNotFoundException` hoặc `NoClassDefFoundError` khi ứng dụng tải class;
- lỗi service provider không tìm thấy;
- lỗi Java Desktop/AWT/Swing khi thiếu module `java.desktop`;
- lỗi JDBC driver hoặc API liên quan khi thiếu module cần thiết.

Kiểm tra dependency module, `--add-modules`, service binding và những class được tải động. Nếu cần, tạo runtime rộng hơn để xác định nguyên nhân rồi tối ưu lại có kiểm soát.

## 15. Ví dụ quy trình phát hành hoàn chỉnh

Giả sử ứng dụng classpath có cấu trúc:

~~~text
build/
├── libs/
│   ├── acme-desk.jar
│   ├── library-a.jar
│   └── library-b.jar
└── package/
    └── resources/
~~~

### Bước 1: Tạo app-image

~~~bash
jpackage \
    --type app-image \
    --name AcmeDesk \
    --input build/libs \
    --main-jar acme-desk.jar \
    --main-class com.acme.desktop.Main \
    --app-version 1.2.0 \
    --vendor "Acme Software" \
    --description "Acme desktop application" \
    --icon packaging/acme-desk.png \
    --dest build/dist
~~~

### Bước 2: Chạy và kiểm tra app-image

Khởi chạy launcher theo OS, thử đăng nhập bằng môi trường kiểm thử, đọc/ghi dữ liệu và xác nhận dependency hoạt động. Không dùng tài khoản production hoặc dữ liệu khách hàng thật trong smoke test đóng gói.

### Bước 3: Tạo installer trên runner phù hợp

Ví dụ Windows:

~~~powershell
jpackage --type msi --name AcmeDesk --app-image build\dist\AcmeDesk --app-version 1.2.0 --win-menu --win-shortcut --dest build\installer
~~~

Trên macOS/Linux, tạo DMG/PKG hoặc DEB/RPM từ app-image cùng nền tảng bằng runner tương ứng.

### Bước 4: Ký và xác minh

Thực hiện signing theo nền tảng, kiểm tra chữ ký, checksum và metadata. Certificate/private key được lấy từ hệ thống quản lý secret của pipeline.

### Bước 5: Kiểm thử trên máy sạch

Cài package, chạy ứng dụng, nâng cấp từ phiên bản trước và gỡ cài đặt. Sau khi các bước kiểm thử hoàn tất, lưu artifact và metadata phát hành ở kho phân phối có quyền truy cập và retention phù hợp.

## 16. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Không tìm thấy `jpackage` | Đang dùng JRE hoặc PATH trỏ tới JDK khác. | Dùng jpackage từ `bin` của JDK 17 và kiểm tra `JAVA_HOME`. |
| Không tạo được EXE/MSI trên Windows | Thiếu hoặc không đúng phiên bản WiX Toolset. | Cài WiX tương thích JDK 17 và cấu hình PATH theo tài liệu. |
| Không tạo được DEB/RPM | Thiếu công cụ đóng gói native của Linux. | Cài công cụ tương ứng như dpkg-deb hoặc rpmbuild trên runner. |
| Không tạo được DMG/PKG | Không chạy trên macOS hoặc thiếu công cụ cần thiết. | Build trên macOS với toolchain phù hợp. |
| Launcher báo không tìm thấy main class | Sai `--main-class`, `--main-jar` hoặc cấu trúc input. | Kiểm tra JAR, manifest và đường dẫn tương đối. |
| App-image chạy trên máy developer nhưng lỗi trên máy sạch | Thiếu module runtime, dependency hoặc native library. | Kiểm thử không có JDK; kiểm tra runtime image và payload. |
| Ứng dụng không tìm thấy file cấu hình | Dựa vào working directory hoặc đường dẫn source tree. | Dùng vị trí resource trong image và thư mục cấu hình người dùng rõ ràng. |
| Runtime image quá lớn | Đưa vào nhiều module hơn nhu cầu. | Xác định module cần thiết và tạo runtime bằng jlink có kiểm tra. |
| Ứng dụng lỗi sau khi tối giản runtime | Thiếu module được tải động hoặc service provider. | Kiểm tra module graph, reflection/service loading và bổ sung module. |
| Installer cài được nhưng shortcut không chạy | Launcher hoặc đường dẫn tham số cấu hình sai. | Kiểm tra launcher, `--arguments`, `--java-options` và thử trên máy sạch. |
| File installer bị cảnh báo nhà phát hành | Chưa ký, chữ ký không hợp lệ hoặc chưa notarize theo yêu cầu nền tảng. | Thực hiện quy trình signing/notarization và xác minh artifact. |
| Bản nâng cấp cài thành sản phẩm khác | Upgrade identifier hoặc package identifier thay đổi ngoài ý muốn. | Quản lý `--win-upgrade-uuid` và identifier ổn định qua release. |
| Dữ liệu người dùng bị xóa khi nâng cấp/gỡ | Lưu dữ liệu trong thư mục cài đặt. | Tách dữ liệu người dùng khỏi application install directory. |
| Nghĩ installer tự cập nhật ứng dụng | Nhầm jpackage với auto-update service. | Thiết kế kênh cập nhật riêng hoặc dùng package manager. |

## 17. Bài tập tự luyện

### Bài 1 — Tạo app-image cho ứng dụng classpath

Một ứng dụng có `desktop.jar`, main class `com.example.desktop.Main` và hai dependency JAR. Viết lệnh jpackage tạo app-image, đặt tên `DesktopTool`, phiên bản `1.0.0` và thư mục đích `dist`.

### Bài 2 — Đóng gói modular application

Một module `com.example.desktop` cần `java.desktop` và `com.example.service`. Viết module descriptor và lệnh jpackage sử dụng `--module-path` và `--module`.

### Bài 3 — Chọn runtime

Ứng dụng dùng Swing, JDBC và logging. Hãy xác định các module JDK có thể cần, giải thích vai trò của `--add-modules` và vì sao cần kiểm tra class được tải qua reflection.

### Bài 4 — App-image và installer

Giải thích vì sao nên chạy thử app-image trước khi tạo MSI/DMG/DEB. Nêu những lỗi mà việc chạy launcher trên máy sạch có thể phát hiện.

### Bài 5 — Build đa nền tảng

Một nhóm muốn phát hành Windows, macOS và Linux từ một máy Linux duy nhất. Giải thích giới hạn của jpackage và đề xuất cách tổ chức các runner build theo hệ điều hành.

### Bài 6 — Bảo vệ dữ liệu và signing

Một developer định đưa API key vào file properties bên trong app-image và private signing key vào thư mục packaging. Xác định rủi ro và đề xuất cách quản lý cấu hình/secret phù hợp.

### Bài 7 — Kế hoạch nâng cấp

Một ứng dụng Windows dùng MSI cần nâng cấp từ 1.2.0 lên 1.3.0. Giải thích vai trò của `--app-version`, `--win-upgrade-uuid`, vị trí lưu dữ liệu người dùng và các bước kiểm thử upgrade/uninstall.

## 18. Ghi nhớ khi dùng jpackage

- jpackage trong JDK 17 tạo app-image hoặc native installer cho ứng dụng Java.
- App-image là thư mục có launcher, payload và runtime; installer là gói cài đặt theo hệ điều hành.
- Với classpath application, dùng `--input`, `--main-jar` và `--main-class`; với modular application, dùng `--module-path` và `--module`.
- Nếu không cung cấp runtime image, jpackage tạo runtime bằng jlink; có thể điều chỉnh module qua `--add-modules` và `--jlink-options`.
- Có thể tạo runtime riêng bằng jlink rồi truyền vào jpackage qua `--runtime-image`.
- Dùng `--app-image` để tạo installer từ app-image đã được kiểm tra.
- Định dạng Windows gồm EXE/MSI, macOS gồm DMG/PKG, Linux gồm DEB/RPM; khả năng đóng gói native phụ thuộc OS và toolchain.
- jpackage không phải công cụ cross-platform installer; build artifact trên runner của nền tảng mục tiêu.
- Dùng metadata, icon, resource directory và `--add-launcher` để hoàn thiện trải nghiệm ứng dụng.
- Không đưa secret vào payload, launcher arguments, JVM options hoặc file cấu hình phát hành.
- Code signing, notarization và package signing cần quy trình theo nền tảng; không mặc định artifact tạo thành đã được ký.
- Quản lý version và identifier ổn định; jpackage không tự cung cấp dịch vụ auto-update.
- Kiểm tra app-image trên máy sạch, kiểm tra installer, upgrade, uninstall, quyền ghi và runtime module trước khi phát hành.

### Tài liệu tham khảo

- [Java SE 17 jpackage tool documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jpackage.html) — các loại package và tùy chọn đóng gói.
- [Java SE 17 jlink tool documentation](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html) — tạo runtime image tùy chỉnh.
- [Java SE 17 JDK tools reference](https://docs.oracle.com/en/java/javase/17/docs/specs/man/index.html) — công cụ JDK 17.
- [JEP 392: Packaging Tool](https://openjdk.org/jeps/392) — jpackage trở thành công cụ chính thức trong JDK.
