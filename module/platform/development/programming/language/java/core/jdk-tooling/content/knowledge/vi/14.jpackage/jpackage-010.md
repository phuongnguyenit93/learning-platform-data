# Kiểm tra installer được tạo bằng `jpackage`

`jpackage` đóng gói ứng dụng Java thành **application image** hoặc **native installer** cho nền tảng đích. Kiểm tra installer không chỉ là xác nhận tệp `.msi`, `.exe`, `.pkg`, `.dmg`, `.deb` hay `.rpm` đã được tạo. Cần xác nhận gói chứa đúng ứng dụng, launcher, runtime Java, tài nguyên và metadata; cài đặt được trên môi trường sạch; khởi chạy đúng; nâng cấp và gỡ cài đặt không để lại trạng thái ngoài dự kiến.

Có ba lớp đầu ra cần phân biệt:

- **Application image (`app-image`):** thư mục ứng dụng có launcher, nội dung ứng dụng và runtime image nếu được đóng gói cùng.
- **Native installer:** gói cài đặt tích hợp với hệ điều hành, có metadata, đường dẫn cài đặt, shortcut, file association và cơ chế uninstall phù hợp.
- **Runtime package:** gói runtime image độc lập, không nhất thiết chứa ứng dụng.

Một lần build thành công chỉ chứng minh công cụ đã tạo artifact. Chất lượng phát hành phải được xác nhận bằng cách kiểm tra nội dung, metadata, chữ ký, cài đặt, chạy ứng dụng, nâng cấp và gỡ bỏ trên hệ điều hành mục tiêu.

## 1. Phân biệt application image và native installer

`jpackage` có thể tạo application image trước, sau đó dùng image đó làm đầu vào cho bước đóng gói installer.

| Loại đầu ra | Mục đích | Kiểm tra chính |
|---|---|---|
| `app-image` | Thư mục có launcher, ứng dụng và runtime | Cấu trúc file, launcher, runtime, resource và hành vi |
| `exe` | Installer Windows dạng executable | Chữ ký, metadata, UI cài đặt, log, install/uninstall |
| `msi` | Windows Installer package | MSI tables, ProductCode/UpgradeCode, log, install/upgrade/uninstall |
| `pkg` | Installer package trên macOS | Chữ ký, package metadata, payload, Gatekeeper và install |
| `dmg` | Disk image phân phối ứng dụng trên macOS | Tính toàn vẹn DMG, nội dung mount, chữ ký app và thao tác copy/install |
| `deb` | Debian package trên Linux | Control metadata, dependency, file payload và install/remove |
| `rpm` | RPM package trên Linux | Package metadata, dependency, signature và install/erase |

Các loại installer phụ thuộc hệ điều hành và JDK. `jpackage --help` hiển thị các loại hợp lệ cho nền tảng đang chạy. Trên môi trường Windows đã kiểm tra với JDK 24.0.2, danh sách gồm `app-image`, `exe` và `msi`. Trên Linux hoặc macOS, hãy chạy `jpackage --help` ngay trên máy build mục tiêu để xác nhận loại gói và tùy chọn nền tảng được hỗ trợ.

Thông thường, `jpackage` tạo gói native cho hệ điều hành mà nó đang chạy. Không thể tạo MSI trên Linux hoặc DMG trên Windows chỉ bằng cách đổi `--type`; cần build trên nền tảng tương ứng hoặc dùng môi trường build tương ứng.

## 2. Kiểm tra toolchain trước khi đóng gói

Ghi nhận phiên bản công cụ và nền tảng:

~~~text
java --version
javac --version
jpackage --version
jpackage --help
~~~

Đối chiếu:

- JDK có `jpackage` trong thư mục `bin`.
- JDK dùng để đóng gói phù hợp với release mục tiêu và dependency của ứng dụng.
- Hệ điều hành và kiến trúc của máy build tương ứng với artifact cần phát hành.
- Native packaging tool mà nền tảng yêu cầu đã sẵn sàng.
- Phiên bản, vendor, tên sản phẩm và icon đã được xác định.
- Có quyền tạo thư mục output và thư mục tạm.

Tùy hệ điều hành và loại gói, native tool có thể là WiX Toolset trên Windows, công cụ đóng gói `.deb`/`.rpm` trên Linux, hoặc các công cụ package/signing có sẵn trên macOS. Kiểm tra tài liệu của đúng JDK và hệ điều hành thay vì giả định mọi loại gói đều được tạo chỉ bằng `jpackage`.

Lưu lại phiên bản JDK, hệ điều hành, kiến trúc, command line và phiên bản native tool trong build log. Đây là dữ liệu cần thiết khi phải tái tạo một installer cũ hoặc điều tra khác biệt giữa CI và máy phát triển.

## 3. Các đầu vào ảnh hưởng đến installer

`jpackage` có hai cách khai báo ứng dụng chính:

- **Non-modular application:** dùng `--input`, `--main-jar` và có thể chỉ rõ `--main-class`.
- **Modular application:** dùng `--module-path` và `--module`.

Không dùng đồng thời `--module` và `--main-jar` trong cùng cấu hình ứng dụng.

Các tùy chọn quan trọng:

| Tùy chọn | Tác dụng |
|---|---|
| `--type` | Chọn `app-image` hoặc native package type phù hợp nền tảng |
| `--name` | Tên ứng dụng/gói |
| `--dest` | Thư mục chứa artifact đầu ra |
| `--input` | Thư mục chứa JAR và file cần đóng gói |
| `--main-jar` | JAR chính, đường dẫn tương đối với input directory |
| `--main-class` | Lớp `main` khi dùng `--main-jar` |
| `--module-path` | Nơi tìm module cho ứng dụng modular |
| `--module` | Tên module và có thể kèm main class |
| `--app-content` | File/thư mục bổ sung trong payload |
| `--runtime-image` | Runtime image đã được chuẩn bị trước |
| `--add-modules` | Module bổ sung cần đưa vào runtime image |
| `--app-version` | Phiên bản ứng dụng/gói |
| `--vendor` | Nhà cung cấp |
| `--description` | Mô tả ứng dụng |
| `--copyright` | Thông tin bản quyền |
| `--icon` | Icon của ứng dụng/gói |
| `--license-file` | File license đi kèm installer |
| `--about-url` | Trang chủ/thông tin ứng dụng |
| `--verbose` | In thêm hoạt động đóng gói |
| `--temp` | Chỉ định thư mục tạm; nếu chỉ định, thư mục được giữ lại sau khi chạy |

`--input` chứa các file được đóng gói. Với ứng dụng cần cấu hình hoặc resource ngoài JAR, hãy kiểm tra chúng thực sự có trong payload. Không giả định `jpackage` tự tìm và copy mọi file nằm ở thư mục source của dự án.

## 4. Tạo application image trước để kiểm tra

Tạo image riêng giúp kiểm tra launcher và runtime trước khi điều tra native installer. Nếu image chưa chạy đúng, lỗi nằm ở ứng dụng hoặc cấu hình đóng gói, chưa cần kiểm tra giao diện installer.

Một cấu trúc dự án non-modular:

~~~text
project/
  src/
    demo/
      Main.java
  classes/
  input/
    inventory.jar
  dist/
  installers/
~~~

Tạo `src/demo/Main.java`:

~~~java
package demo;

public class Main {
    public static void main(String[] args) {
        System.out.println("Installer smoke test OK");
    }
}
~~~

Từ thư mục `project`, biên dịch và tạo JAR:

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force classes, input, dist, installers | Out-Null
javac --release 17 -d classes src\demo\Main.java
jar --create --file input\inventory.jar --main-class demo.Main -C classes .
~~~

macOS/Linux:

~~~sh
mkdir -p classes input dist installers
javac --release 17 -d classes src/demo/Main.java
jar --create --file input/inventory.jar --main-class demo.Main -C classes .
~~~

Tạo application image trên Windows:

~~~powershell
jpackage --type app-image --name Inventory --input input --main-jar inventory.jar --main-class demo.Main --app-version 1.2.0 --vendor "Example Corp" --dest dist --win-console --verbose
~~~

`--win-console` tạo launcher console trên Windows, phù hợp ví dụ in stdout. Với ứng dụng GUI, chọn cấu hình launcher phù hợp và kiểm tra log của ứng dụng thay vì trông chờ cửa sổ console.

Trên Linux/macOS, bỏ `--win-console` và dùng các tùy chọn launcher dành cho nền tảng tương ứng. Nếu muốn đóng gói app image từ một runtime image tự tạo bằng `jlink`, dùng `--runtime-image` để cung cấp runtime đã chuẩn bị.

## 5. Kiểm tra application image

Sau khi tạo image, kiểm tra toàn bộ cây file:

Windows PowerShell:

~~~powershell
Get-ChildItem -Force -Recurse dist\Inventory |
    Select-Object FullName, Length
~~~

macOS/Linux:

~~~sh
find dist/Inventory -type f -print
~~~

Cấu trúc chi tiết thay đổi theo nền tảng và JDK, nhưng thường có các thành phần tương đương:

- Launcher của ứng dụng.
- Thư mục chứa JAR và resource.
- Cấu hình launcher.
- Runtime image đi kèm nếu `jpackage` đã tạo hoặc copy runtime.
- File hỗ trợ theo nền tảng.

Kiểm tra các điểm sau:

1. Launcher có tên đúng và nằm đúng vị trí.
2. JAR chính và mọi resource cần thiết đều có trong payload.
3. Runtime được đóng gói nếu ứng dụng yêu cầu self-contained runtime.
4. Không có file build/test/debug không cần thiết.
5. Icon, tên sản phẩm và metadata được áp dụng đúng.
6. File cấu hình launcher có main class/module, JVM option và argument mong muốn.
7. Không có đường dẫn tuyệt đối trỏ về thư mục build trên máy phát triển.

Chạy launcher trực tiếp từ image:

Windows:

~~~powershell
.\dist\Inventory\Inventory.exe
~~~

Linux:

~~~sh
./dist/Inventory/bin/Inventory
~~~

macOS dùng application bundle có cấu trúc .app; launcher nằm trong Contents/MacOS:

~~~sh
./dist/Inventory.app/Contents/MacOS/Inventory
~~~

Stdout của ví dụ console:

~~~text
Installer smoke test OK
~~~

Nếu image chứa runtime, kiểm tra module runtime:

Windows:

~~~powershell
.\dist\Inventory\runtime\bin\java.exe --list-modules
~~~

Linux:

~~~sh
./dist/Inventory/lib/runtime/bin/java --list-modules
~~~

macOS:

~~~sh
./dist/Inventory.app/Contents/runtime/Contents/Home/bin/java --list-modules
~~~

Vị trí runtime có thể khác theo cấu trúc image và nền tảng. Hãy tìm executable `java` trong runtime được đóng gói thay vì hard-code một đường dẫn chung cho mọi OS.

## 6. Tạo installer từ application image đã kiểm tra

Sau khi application image chạy đúng, dùng `--app-image` để tạo native installer. Cách này giúp tách kiểm tra nội dung ứng dụng khỏi kiểm tra native package.

Ví dụ Windows MSI:

~~~powershell
jpackage --type msi --name Inventory --app-image dist\Inventory --app-version 1.2.0 --vendor "Example Corp" --dest installers --win-menu --win-shortcut --win-upgrade-uuid "123e4567-e89b-42d3-a456-426614174000" --verbose
~~~

Các điểm quan trọng:

- `--app-image` trỏ đến application image đã tạo và kiểm tra.
- `--type msi` yêu cầu native Windows Installer package.
- `--win-menu` và `--win-shortcut` yêu cầu shortcut phù hợp.
- `--win-upgrade-uuid` xác định UpgradeCode của sản phẩm MSI; cần giữ ổn định cho các bản phát hành cùng dòng sản phẩm.
- `--app-version` cần tuân theo quy tắc versioning của package format và công cụ native.

Tên artifact thường dựa trên tên ứng dụng và phiên bản, ví dụ `Inventory-1.2.0.msi`. Hãy lấy tên thực tế từ thư mục `installers`, không giả định tên file nếu build script có quy tắc riêng.

Trên Windows JDK đã kiểm tra, `jpackage --help` xác nhận `app-image`, `exe` và `msi` là các loại hợp lệ. Với EXE installer, thay `--type msi` bằng `--type exe` nếu muốn định dạng đó và native tool cần thiết đã được cài đặt.

## 7. Kiểm tra metadata và nội dung installer trên Windows

### 7.1. Kiểm tra chữ ký và checksum

Xem chữ ký Authenticode:

~~~powershell
Get-AuthenticodeSignature .\installers\Inventory-1.2.0.msi |
    Format-List Status, StatusMessage, SignerCertificate
~~~

Với launcher `.exe`:

~~~powershell
Get-AuthenticodeSignature .\dist\Inventory\Inventory.exe |
    Format-List Status, StatusMessage, SignerCertificate
~~~

Nếu quy trình phát hành ký bằng Windows SDK, có thể xác minh bằng:

~~~text
signtool verify /pa /v installers\Inventory-1.2.0.msi
signtool verify /pa /v dist\Inventory\Inventory.exe
~~~

`NotSigned` có thể là kết quả bình thường trong build thử nghiệm chưa ký. Với artifact phát hành, chính sách release phải yêu cầu chữ ký hợp lệ, certificate đúng nhà phát hành và timestamp theo yêu cầu tổ chức.

Tạo checksum SHA-256:

~~~powershell
Get-FileHash .\installers\Inventory-1.2.0.msi -Algorithm SHA256
~~~

Lưu hash trong manifest phát hành và so sánh sau khi tải artifact từ nơi phân phối. Checksum chứng minh nội dung file không thay đổi so với hash đã tin cậy; nó không thay thế chữ ký số hoặc xác minh nguồn phát hành.

### 7.2. Kiểm tra MSI database

Dùng công cụ Orca (Windows SDK) để xem các bảng MSI quan trọng:

- `Property`: tên sản phẩm, phiên bản, nhà cung cấp và package metadata.
- `File`: danh sách file được cài.
- `Component`: thành phần cài đặt và key path.
- `Directory`: cấu trúc thư mục cài đặt.
- `Shortcut`: shortcut được tạo.
- `Registry`: registry entries.
- `Feature`: tính năng cài đặt.
- `Upgrade`: quy tắc nhận diện và nâng cấp phiên bản.

Đối chiếu metadata với thông tin release. Kiểm tra shortcut trỏ đến launcher đúng, install directory hợp lý và không có file không mong muốn.

Có thể tạo administrative installation image để kiểm tra hoặc phân phối nội bộ bằng:

~~~text
msiexec /a installers\Inventory-1.2.0.msi TARGETDIR=C:\PackageInspection
~~~

Administrative install trích xuất cấu trúc triển khai MSI vào thư mục đích; nó không tương đương với cài đặt ứng dụng đầy đủ và không thay thế test cài đặt thực tế.

## 8. Cài đặt, chạy và gỡ MSI trong môi trường thử nghiệm

Thực hiện cài đặt trên máy ảo hoặc máy kiểm thử sạch, không dùng máy build làm bằng chứng duy nhất. Ghi log chi tiết:

~~~powershell
msiexec /i .\installers\Inventory-1.2.0.msi /qn /l*v install.log
~~~

Sau khi cài:

- Xác nhận tiến trình cài đặt kết thúc với mã thoát thành công; mã `3010` có nghĩa cài đặt thành công nhưng cần khởi động lại.
- Xác định install directory thực tế từ MSI log hoặc cấu hình installer.
- Kiểm tra launcher và runtime được cài.
- Kiểm tra Start Menu/Desktop shortcut nếu đã yêu cầu.
- Khởi chạy ứng dụng bằng shortcut và trực tiếp từ install directory.
- Kiểm tra quyền ghi file, cấu hình, log và dữ liệu người dùng.
- Kiểm tra file association nếu sản phẩm đăng ký loại file riêng.

Gỡ cài đặt bằng package:

~~~powershell
msiexec /x .\installers\Inventory-1.2.0.msi /qn /l*v uninstall.log
~~~

Sau khi uninstall, xác nhận:

- Ứng dụng không còn trong danh sách chương trình đã cài.
- Shortcut do installer tạo đã được xóa.
- File và registry entries thuộc installer đã được dọn.
- Dữ liệu người dùng cần giữ lại được xử lý đúng theo chính sách sản phẩm.
- Có thể cài lại sạch sau khi uninstall.

Không nên xóa thủ công thư mục cài đặt trước khi chạy uninstall vì điều đó có thể làm mất khả năng kiểm tra quy trình gỡ cài đặt thực tế.

## 9. Kiểm tra EXE installer và quy trình nâng cấp Windows

EXE installer có thể cung cấp wizard hoặc bootstrapper bao quanh quá trình cài đặt. Kiểm tra:

- Tên và publisher hiển thị trong giao diện.
- Đường dẫn cài đặt mặc định và tùy chọn thay đổi directory nếu bật `--win-dir-chooser`.
- Shortcut Start Menu/Desktop theo các tùy chọn `--win-menu` và `--win-shortcut`.
- Hành vi cài per-user/per-machine.
- Thông báo lỗi khi thiếu quyền hoặc có phiên bản đang chạy.
- Chữ ký Authenticode và cảnh báo SmartScreen theo môi trường phát hành.

Nếu phát hành nhiều phiên bản MSI, kiểm tra nâng cấp trên máy ảo:

1. Cài phiên bản cũ.
2. Ghi nhận version, install path, shortcut và dữ liệu người dùng.
3. Cài phiên bản mới với cùng UpgradeCode.
4. Xác nhận phiên bản mới thay thế đúng bản cũ theo chính sách.
5. Kiểm tra dữ liệu cần giữ lại và file được cập nhật.
6. Gỡ phiên bản mới và kiểm tra trạng thái cuối.

`--win-upgrade-uuid` là định danh nâng cấp của dòng sản phẩm MSI. Không tạo UUID mới ngẫu nhiên cho mỗi bản phát hành nếu mục tiêu là nâng cấp cùng sản phẩm. Lưu UUID này trong cấu hình release để build tái hiện được.

## 10. Kiểm tra package trên Linux

Trên Linux, loại native package có thể gồm `.deb` hoặc `.rpm` tùy distro, JDK và công cụ native có sẵn. Chạy `jpackage --help` trên máy Linux để xác nhận tùy chọn và package type hỗ trợ.

### 10.1. Kiểm tra Debian package

Xem metadata:

~~~sh
dpkg-deb --info Inventory.deb
dpkg-deb --field Inventory.deb Package Version Architecture Depends
~~~

Liệt kê file trong payload:

~~~sh
dpkg-deb --contents Inventory.deb
~~~

Giải nén để kiểm tra:

~~~sh
mkdir -p extracted
dpkg-deb --extract Inventory.deb extracted
~~~

Đối chiếu package name, version, architecture, dependency, file path và launcher. Cài đặt trong máy ảo Debian/Ubuntu tương ứng, chạy smoke test, rồi gỡ bằng package manager:

~~~sh
sudo apt install ./Inventory.deb
sudo apt remove inventory
~~~

Tên package thực tế có thể khác tên file; đọc trường `Package` từ metadata trước khi dùng lệnh remove.

`dpkg-deb` kiểm tra metadata và payload, nhưng chữ ký repository APT thường được xác minh ở cấp repository metadata. Không coi việc `dpkg-deb --info` thành công là bằng chứng package đã được ký hoặc nguồn phát hành đáng tin cậy.

### 10.2. Kiểm tra RPM package

Xem metadata và file payload:

~~~sh
rpm -qpi Inventory.rpm
rpm -qpl Inventory.rpm
rpm -qp --requires Inventory.rpm
~~~

Kiểm tra digest/chữ ký nếu package đã được ký:

~~~sh
rpm -K Inventory.rpm
~~~

Cài đặt và gỡ trên máy ảo tương ứng:

~~~sh
sudo dnf install ./Inventory.rpm
sudo dnf remove inventory
~~~

Trên hệ thống dùng `yum` hoặc package manager khác, thay lệnh theo distro. Đọc package name thực tế từ metadata trước khi gỡ.

Kiểm tra scriptlet, dependency, file permission, system menu/desktop entry và vị trí dữ liệu. Package RPM chưa ký có thể báo thiếu chữ ký; điều này cần được đánh giá theo chính sách phát hành thay vì tự động xem là lỗi payload.

## 11. Kiểm tra package trên macOS

Trên macOS, `jpackage` có thể tạo application image, installer `.pkg` hoặc disk image `.dmg` tùy JDK và hệ điều hành.

### 11.1. Kiểm tra DMG

Xác minh disk image:

~~~sh
hdiutil verify Inventory.dmg
~~~

Mount để xem nội dung:

~~~sh
hdiutil attach Inventory.dmg
~~~

Kiểm tra ứng dụng `.app` và các file đi kèm. Sau khi kiểm tra, tháo volume bằng `hdiutil detach` với mount point thực tế.

### 11.2. Kiểm tra PKG

Kiểm tra chữ ký installer:

~~~sh
pkgutil --check-signature Inventory.pkg
spctl --assess --type install --verbose Inventory.pkg
~~~

Có thể xem cấu trúc package:

~~~sh
pkgutil --expand Inventory.pkg expanded-pkg
~~~

Đối chiếu package identifier, version, payload, install location và script nếu có. Cài đặt trong máy thử nghiệm macOS:

~~~sh
sudo installer -pkg Inventory.pkg -target /
~~~

Sau đó kiểm tra app có mở được, runtime có hoạt động và Gatekeeper không chặn ứng dụng ngoài dự kiến.

### 11.3. Kiểm tra chữ ký ứng dụng và notarization

Nếu phát hành ứng dụng macOS, kiểm tra chữ ký bundle:

~~~sh
codesign --verify --deep --strict --verbose=2 Inventory.app
spctl --assess --type execute --verbose Inventory.app
~~~

Với ứng dụng phân phối bên ngoài hệ sinh thái nội bộ, signing và notarization phải theo chính sách Apple Developer của tổ chức. Xác minh trạng thái package và app bundle riêng; chữ ký package không tự chứng minh mọi binary bên trong có cấu hình đúng.

## 12. Kiểm tra file association, shortcut và metadata

Nếu dùng `--file-associations`, kiểm tra cả file cấu hình association lẫn hành vi sau cài đặt. Các key thường dùng gồm:

- `extension`: phần mở rộng file.
- `mime-type`: MIME type.
- `icon`: icon liên kết.
- `description`: mô tả loại file.

Kiểm tra trên máy sạch:

1. Cài ứng dụng.
2. Xác nhận file type được đăng ký đúng.
3. Mở một file mẫu bằng double-click.
4. Kiểm tra ứng dụng nhận đúng đường dẫn file và xử lý nội dung.
5. Gỡ cài đặt rồi xác nhận association được dọn theo mong muốn.

Metadata như `--name`, `--app-version`, `--vendor`, `--description`, `--copyright`, icon, license file và about URL cần thống nhất với trang download, manifest phát hành và thông tin hiển thị trong OS.

## 13. Runtime image và dependency cần kiểm tra

Một installer Java self-contained thường mang theo runtime image. Cần xác nhận:

- Runtime thuộc đúng phiên bản Java mục tiêu.
- Các module ứng dụng cần đều có trong runtime.
- Reflection, service provider, plugin và JNI hoạt động trong runtime rút gọn.
- Native library đúng hệ điều hành và kiến trúc.
- Resource, cấu hình và truststore cần thiết có sẵn.
- JVM option và argument mặc định của launcher đúng.
- Không có dependency vô tình trỏ về JDK trên máy build.

Nếu truyền `--runtime-image`, `jpackage` sử dụng runtime image có sẵn. Nếu không truyền, công cụ có thể gọi `jlink` để tạo runtime image với các tùy chọn mặc định của phiên bản JDK đó. Kiểm tra `jpackage --help` để xem các mặc định và tùy chọn `--jlink-options`.

Trên JDK được kiểm tra trong bài này, help mô tả mặc định `--strip-debug`, `--no-header-files`, `--no-man-pages` và `--strip-native-commands` khi `jpackage` tự tạo runtime image. Mặc định có thể thay đổi giữa các JDK; nếu cần runtime có module hoặc native command cụ thể, tạo runtime riêng bằng `jlink` và cung cấp qua `--runtime-image`.

## 14. Log, thư mục tạm và tái hiện lỗi đóng gói

Khi installer build thất bại, bật verbose:

~~~text
jpackage --verbose ...
~~~

Có thể giữ thư mục tạm để điều tra:

~~~text
jpackage --temp build-temp --verbose ...
~~~

Theo `jpackage --help`, thư mục `--temp` phải là thư mục mới hoặc trống; khi chỉ định, nó không tự bị xóa sau khi lệnh kết thúc. Kiểm tra log, cấu hình WiX hoặc file trung gian theo nền tảng trong thư mục này.

Khi ghi nhận lỗi, lưu:

- Toàn bộ command line và exit code.
- Phiên bản `java`, `javac`, `jpackage`.
- OS version và architecture.
- Native packaging tool và phiên bản.
- Nội dung stdout/stderr.
- Thư mục tạm và file log.
- Loại package được yêu cầu.
- Metadata đầu vào và danh sách file payload.

Không chỉ nhìn thấy file đầu ra là kết luận build thành công. Kiểm tra exit code của `jpackage` và xác nhận artifact có kích thước hợp lý, đọc được bằng công cụ native của hệ điều hành.

## 15. Ma trận kiểm thử installer trước phát hành

| Nhóm kiểm tra | Câu hỏi cần xác nhận | Bằng chứng |
|---|---|---|
| Build | `jpackage` kết thúc thành công? | Exit code, verbose log |
| Artifact | Đúng loại, tên, version và architecture? | File/package metadata |
| Payload | Có JAR, resource, launcher và runtime? | App image/package contents |
| Runtime | Ứng dụng chạy trên máy không cài JDK? | Clean VM smoke test |
| Metadata | Vendor, description, icon, license đúng? | Installer UI/package database |
| Signature | Chữ ký và certificate hợp lệ? | Authenticode/codesign/pkg verification |
| Install | Cài đúng vị trí và tạo shortcut? | Install log, filesystem, OS menu |
| Operation | App mở được, nhận argument/file association? | Functional test |
| Upgrade | Bản mới thay thế đúng bản cũ? | Upgrade test, retained data |
| Uninstall | Shortcut và file cài được dọn đúng? | Uninstall log, filesystem |
| Integrity | Artifact không đổi sau upload? | SHA-256 checksum |
| Portability | Gói đúng OS/CPU và native dependency? | Test trên target VM |

Một quy trình tối thiểu nên có clean install, launch, functional smoke test, upgrade và uninstall. Với ứng dụng quan trọng, bổ sung test quyền người dùng, đường dẫn có dấu cách/ký tự Unicode, offline install, nhiều user profile, file association, service, firewall và antivirus theo môi trường triển khai.

## 16. Lỗi thường gặp khi kiểm tra installer

### `jpackage` báo không hỗ trợ package type

**Nguyên nhân:** package type không phù hợp hệ điều hành hoặc JDK hiện tại.

**Cách xử lý:** chạy `jpackage --help` trên host build, dùng loại gói được liệt kê và build trên OS mục tiêu.

### Không tìm thấy WiX hoặc native packaging tool

**Nguyên nhân:** thiếu công cụ native cần thiết hoặc PATH không chứa công cụ.

**Cách xử lý:** cài đúng phiên bản theo tài liệu JDK/nền tảng, kiểm tra executable và chạy lại `jpackage --verbose`.

### `Main class` hoặc `main JAR` không hợp lệ

**Nguyên nhân:** sai đường dẫn tương đối với `--input`, manifest thiếu main class hoặc khai báo main class không đúng.

**Cách xử lý:** kiểm tra JAR bằng `jar --list --file`, xác nhận class có `public static void main(String[] args)` và dùng `--main-jar`/`--main-class` đúng.

### Installer tạo thành công nhưng ứng dụng không chạy

**Nguyên nhân:** thiếu resource, runtime module, JVM option, native library hoặc đường dẫn cấu hình.

**Cách xử lý:** chạy app image trước khi đóng gói native installer; kiểm tra launcher config, runtime `--list-modules` và log ứng dụng.

### Ứng dụng chạy trên máy build nhưng lỗi trên máy sạch

**Nguyên nhân:** máy build có JDK, PATH, biến môi trường, file cấu hình hoặc dependency ngoài mà installer không đóng gói.

**Cách xử lý:** test trên VM sạch không có JDK, kiểm tra mọi resource/native dependency và dùng runtime được đóng gói.

### MSI không nâng cấp bản cũ

**Nguyên nhân:** UpgradeCode không ổn định, version không phù hợp quy tắc MSI hoặc cấu hình nâng cấp thay đổi.

**Cách xử lý:** giữ `--win-upgrade-uuid` cho cùng dòng sản phẩm, kiểm tra bảng `Upgrade` trong MSI và chạy test từ phiên bản cũ sang phiên bản mới.

### Chữ ký không hợp lệ hoặc hệ điều hành cảnh báo

**Nguyên nhân:** artifact chưa ký, certificate không tin cậy, timestamp thiếu/hết hạn hoặc binary bị thay đổi sau ký.

**Cách xử lý:** ký ở bước release bằng certificate phù hợp, xác minh chữ ký sau khi ký và không chỉnh sửa binary sau bước ký. Trên macOS, kiểm tra cả code signing, Gatekeeper và notarization theo yêu cầu phân phối.

### Cài được nhưng uninstall để lại shortcut/file

**Nguyên nhân:** file được tạo ngoài payload installer hoặc ứng dụng tự ghi dữ liệu vào vị trí không được quản lý bởi package.

**Cách xử lý:** phân biệt file do installer sở hữu với dữ liệu người dùng; bổ sung cleanup phù hợp và xác nhận bằng uninstall test trên VM sạch.

## 17. Checklist phát hành

- [ ] Đã ghi nhận JDK, `jpackage`, OS và architecture.
- [ ] Đã kiểm tra `jpackage --help` trên host build.
- [ ] Đúng `--type`, `--name`, `--app-version`, `--vendor` và destination.
- [ ] Input JAR/module và resource đã được xác nhận.
- [ ] Application image được tạo và chạy thành công trước khi đóng gói installer.
- [ ] Runtime image có đủ module và native dependency.
- [ ] Installer payload và metadata đã được kiểm tra bằng công cụ native.
- [ ] Chữ ký và certificate đã được xác minh theo release policy.
- [ ] Checksum SHA-256 đã được lưu trong manifest phát hành.
- [ ] Clean install trên VM mục tiêu thành công.
- [ ] Launcher, shortcut, file association và resource hoạt động.
- [ ] Upgrade từ bản cũ đã được kiểm tra.
- [ ] Uninstall dọn đúng file/shortcut và giữ dữ liệu cần thiết.
- [ ] Log, command line và toolchain được lưu để tái hiện.
- [ ] Artifact đã được thử trên hệ điều hành/kiến trúc mục tiêu.

`jpackage` tạo ra artifact có thể phân phối, nhưng chỉ kiểm thử trên môi trường sạch mới xác nhận installer hoạt động trong điều kiện gần với máy người dùng. Hãy kiểm tra application image trước, xác minh metadata và chữ ký bằng công cụ của hệ điều hành, sau đó chạy đầy đủ luồng cài đặt, khởi chạy, nâng cấp và gỡ cài đặt trước khi phát hành.