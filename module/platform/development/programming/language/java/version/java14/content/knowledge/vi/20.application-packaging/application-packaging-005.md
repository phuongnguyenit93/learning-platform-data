# Kiểm tra JDK cùng công cụ đóng gói theo hệ điều hành trước khi chạy jpackage

> **Bối cảnh:** Java 14 → *Đóng gói ứng dụng* → **Kiểm tra JDK cùng công cụ đóng gói theo hệ điều hành**. Công cụ `jpackage` xuất hiện dưới dạng **incubating** trong JDK 14–15 và **chính thức từ JDK 16 (JEP 392)**. Bài học này dùng quy trình hiện hành của JDK 17+; không áp dụng tên module incubator hay cách chạy của các bản Java 14–15 đã lỗi thời.

## 1. Hiểu rõ loại đầu ra để kiểm tra đúng công cụ

`jpackage` nhận JAR hoặc modules của ứng dụng Java và tạo **application image** chứa launcher cùng Java runtime, hoặc gói cài đặt native cho hệ điều hành. Có hai cấp kiểm tra khác nhau:

- **`--type app-image`:** kiểm tra JDK, cấu hình application/JAR, khả năng tạo runtime và launcher. Trên Windows có launcher `.exe`, macOS có bundle `.app`, Linux có thư mục chứa launcher. **Đây không phải gói installer.**
- **Native installer:** dùng `--type exe`/`msi` (Windows), `dmg`/`pkg` (macOS), `deb`/`rpm` (Linux). Cần công cụ đóng gói của **chính hệ điều hành** và đôi khi cả công cụ ký số.

Theo Oracle, **mỗi định dạng platform-specific phải được build trên chính nền tảng đó**. `jpackage` không phải cross-compiler. Muốn phát hành Windows, Linux và macOS, hãy chạy các job build riêng trên từng hệ điều hành, đồng thời kiểm tra CPU architecture (x86-64, ARM64...) và phiên bản OS đích.

| Hệ điều hành nơi chạy `jpackage` | `app-image` | Installer hỗ trợ | Native prerequisites quan trọng |
| --- | --- | --- | --- |
| Windows | Launcher EXE trong application image | `exe`, `msi` | **WiX Toolset** cho installer |
| macOS | Bundle `.app` | `dmg`, `pkg` | Công cụ packaging macOS; Xcode Command Line Tools trong các trường hợp ký gói/tùy chỉnh icon |
| Linux | Thư mục launcher và runtime | `deb`, `rpm` | Công cụ xây dựng Debian/RPM phù hợp với distro, ví dụ `fakeroot`, `dpkg-deb`, `rpm-build` |

**Nguyên tắc chẩn đoán:** có lệnh `java` chạy được không đồng nghĩa có JDK đầy đủ; có lệnh `jpackage` chạy được không đồng nghĩa đã cài WiX, rpm-build, fakeroot hoặc signing tools; tạo được app-image cũng **không bảo đảm** installer sẽ được tạo hoặc cài đặt thành công.

## 2. Preflight chung: xác nhận đúng JDK đang được dùng

Trước khi build, kiểm tra năm nhóm:

1. **Host:** tên hệ điều hành, bản OS, kiến trúc CPU và nơi CI job thực sự chạy (không chỉ tên máy chủ vật lý).
2. **JDK:** phiên bản và vị trí thực tế của `java`, `javac`, `jar`, `jlink`, `jpackage`. Các tool nên đến từ **cùng installation JDK** đã chọn.
3. **Input:** JAR/modules đã build, main class hoặc main module, tài nguyên và dependency bên ngoài. Đường dẫn `--input` và `--main-jar` phải đúng.
4. **Native tools:** định dạng EXE/MSI, DMG/PKG, DEB/RPM yêu cầu những công cụ khác nhau; kiểm tra chính xác theo type.
5. **Thử nghiệm:** tạo `app-image` rồi **chạy launcher trong image**. Sau đó mới thử installer, ký gói và chạy trên máy sạch.

### Công dụng của các lệnh JDK

| Lệnh | Kiểm tra |
| --- | --- |
| `java --version` | Java runtime mà shell sẽ dùng |
| `javac --version` | Java compiler, giúp phát hiện môi trường chỉ có JRE/runtime rút gọn |
| `jar --version` | Tool tạo JAR |
| `jlink --version` | Tool tạo runtime image |
| `jpackage --version` | `jpackage` tồn tại và chạy được; phiên bản builder |
| `jpackage --help` | Cú pháp/tùy chọn mà **chính phiên bản hiện tại** hỗ trợ |
| `java --list-modules` | Các JDK modules hiện có, bao gồm `jdk.jpackage` trong JDK builder thích hợp |
| `jpackage --verbose ...` | Log chi tiết khi chạy build thực tế để tìm lỗi |

Không cần gọi `jlink` thủ công trong mọi dự án: `jpackage` thường dùng `jlink` tạo runtime nếu không chỉ định `--runtime-image`. Tuy nhiên runtime cuối cùng vẫn cần đủ modules và native dependencies của ứng dụng.

### Phân biệt phiên bản compile với phiên bản runtime bundled

~~~bash
javac --release 17 PackCheck.java
~~~

`--release 17` yêu cầu trình biên dịch dùng ngữ nghĩa/API/class-file target của Java 17. Nếu tiếp theo bạn gọi `jpackage` từ **JDK 24**, runtime image tự tạo có thể mang JDK 24, **không phải JDK 17**. Quyết định rõ phiên bản **chạy ứng dụng** và phiên bản **công cụ đóng gói**. Đừng trộn `javac` của JDK A, `java` của JDK B và `jpackage` của JDK C mà không chủ đích.

## 3. Windows: PowerShell kiểm tra JDK, PATH, JAVA_HOME

Mở PowerShell và chạy:

~~~powershell
# Các lệnh JDK đang được chọn trên PATH:
java --version
javac --version
jar --version
jlink --version
jpackage --version
jpackage --help

# Đường dẫn executable được PowerShell phân giải:
Get-Command java, javac, jar, jlink, jpackage | Select-Object Name, Source

# Nếu có nhiều installation, xem tất cả kết quả trên PATH:
where.exe java
where.exe jpackage

# Kiểm tra JAVA_HOME riêng biệt:
$env:JAVA_HOME
~~~

**Cách diễn giải:**

- Lệnh `jpackage --version` thành công cho thấy công cụ có thể chạy từ môi trường hiện tại. Không có nghĩa WiX đã sẵn sàng.
- `java` thành công nhưng `javac`/`jpackage` không tìm thấy: có thể đang chọn JRE/custom runtime image hoặc JDK thiếu tool, hoặc PATH sai.
- Nếu `Get-Command jpackage` dẫn tới một JDK khác `JAVA_HOME`, hãy làm rõ toolchain và sửa PATH hoặc gọi bằng đường dẫn tuyệt đối.
- PowerShell `Get-Command` và `where.exe` giúp phân tích PATH; không thay thế việc chạy thực tế lệnh.

Khi `JAVA_HOME` đã trỏ đến một thư mục **JDK đầy đủ**:

~~~powershell
Test-Path (Join-Path $env:JAVA_HOME 'bin\java.exe')
Test-Path (Join-Path $env:JAVA_HOME 'bin\jpackage.exe')

& (Join-Path $env:JAVA_HOME 'bin\java.exe') --version
& (Join-Path $env:JAVA_HOME 'bin\jpackage.exe') --version
~~~

Đây là cú pháp PowerShell; `&` là call operator cần thiết khi thực thi một path được đặt trong biểu thức hoặc có khoảng trắng. Nếu `JAVA_HOME` rỗng, `Join-Path` có thể báo lỗi; **thiết lập biến trước khi chạy đoạn này**.

### 3.1. Windows installer cần WiX

Cả `--type exe` lẫn `--type msi` phụ thuộc **WiX Toolset**. Kiểm tra công cụ có thể được shell tìm thấy:

~~~powershell
Get-Command wix, candle, light -ErrorAction SilentlyContinue |
    Select-Object Name, Source

# Với WiX v4/v5, khi có wix CLI:
wix --version

# Với WiX v3, kiểm tra candle/light nếu có:
# candle.exe -?
# light.exe -?
~~~

- **WiX v3** thường cung cấp `candle.exe` và `light.exe`.
- **WiX v4/v5** cung cấp `wix` CLI.
- Nếu `Get-Command` không thấy gì, có thể WiX chưa cài **hoặc không có trong PATH**. Cần xác nhận cách cài đặt thực tế, không kết luận quá sớm.

**Lưu ý phiên bản hiện đại:** trước JDK 24, `jpackage` trên Windows chủ yếu phụ thuộc WiX **v3**; **từ JDK 24**, Oracle cho biết hỗ trợ **WiX v3, v4 và v5**. Nếu dùng toolchain Java 17/21 với WiX v5, không thể mặc định chúng tương thích. Chọn JDK/WiX có hỗ trợ lẫn nhau hoặc điều chỉnh toolchain theo chính sách dự án.

**Quan trọng:** Windows `--type app-image` **không yêu cầu WiX**, nhưng `--type exe`/`msi` có. Dùng app-image để phân biệt lỗi JAR/runtime/launcher với lỗi tạo installer.

## 4. Linux: kiểm tra phân phối và tools cho DEB/RPM

Bắt đầu bằng thông tin host và toolchain:

~~~bash
uname -s
uname -m
cat /etc/os-release

command -v java
command -v javac
command -v jar
command -v jlink
command -v jpackage

java --version
javac --version
jpackage --version
jpackage --help
~~~

`uname -s` cho biết loại hệ điều hành, `uname -m` cho CPU architecture; `/etc/os-release` giúp xác định distribution để chọn package manager đúng. `command -v jpackage` cho biết vị trí executable trên PATH, **không xác nhận đã cài native packaging tools**.

Kiểm tra theo định dạng đầu ra:

~~~bash
# Khi dự định tạo DEB:
command -v dpkg-deb
command -v fakeroot

# Khi dự định tạo RPM:
command -v rpmbuild
command -v rpm
~~~

Oracle nêu **`rpm-build`** cần cho Red Hat family khi tạo RPM và **`fakeroot`** cần trên Ubuntu khi tạo DEB; hãy kiểm tra `dpkg-deb`/`rpmbuild` ở môi trường cụ thể. Các tên gói cài đặt có thể thay đổi theo distro. Không dùng lệnh `apt` cứng cho mọi Linux.

**Ví dụ sau khi đã có JAR:**

~~~bash
# Chạy trên Linux phù hợp với định dạng Debian:
jpackage --type deb --name PackCheck \
  --input build/input --main-jar packcheck.jar \
  --main-class PackCheck --dest build/dist

# Khi cần RPM, chạy một lệnh jpackage riêng với --type rpm.
~~~

Không dùng `jpackage` Linux để build Windows EXE/MSI. Linux **container** chạy trên máy chủ Windows vẫn là môi trường Linux đối với công cụ jpackage trong container.

### Điều cần kiểm tra sau khi tạo DEB/RPM

- Có đúng **architecture** và OS/distro mục tiêu không?
- Runtime bundled có phụ thuộc hệ thống native nào chưa sẵn trên máy cài đặt?
- Cài/gỡ qua package manager có hoạt động với quyền dự kiến không?
- Launcher khi chạy từ đường dẫn cài đặt có tải được Java modules, JAR, resources và JNI/native libraries không?

`--type app-image` tạo được một cây thư mục Linux **không tự bảo đảm** chạy trên mọi distro, bản glibc hay architecture.

## 5. macOS: kiểm tra JDK, công cụ DMG/PKG và ký gói

Trong Terminal (Bash hoặc Zsh):

~~~bash
uname -s
uname -m

command -v java
command -v javac
command -v jar
command -v jlink
command -v jpackage

java --version
javac --version
jpackage --version
jpackage --help

# Các công cụ macOS liên quan:
command -v pkgbuild
command -v hdiutil
command -v codesign
~~~

Nếu máy có nhiều JDK, có thể kiểm tra:

~~~bash
/usr/libexec/java_home -V
echo "$JAVA_HOME"
"$JAVA_HOME/bin/jpackage" --version
~~~

Dòng cuối chỉ dùng sau khi `JAVA_HOME` đã được cấu hình đúng. Không mặc định IDE, terminal và CI đều dùng chung JDK.

| Mục tiêu | Các điểm cần xác nhận |
| --- | --- |
| `--type app-image` | JDK và bundle `.app` chạy được trên macOS mục tiêu |
| `--type dmg` | Tools tạo DMG, application bundle và tùy chọn icon nếu dùng |
| `--type pkg` | Native package tooling, nơi cài đặt và quyền truy cập |
| Ký số/notarization | Developer identity, certificates, Xcode Command Line Tools và quy trình ký/notarize |

Theo Oracle, **Xcode Command Line Tools** là điều kiện khi chỉ định `--mac-sign` và khi dùng `--icon` tùy chỉnh ảnh DMG. Kiểm tra:

~~~bash
xcode-select -p
~~~

Kết quả thành công chỉ là dấu hiệu CLT đã cấu hình, **không chứng minh** có certificate, profile, entitlement hoặc quyền notarize. Đừng coi file `.dmg` vừa được tạo đã tự được ký số.

Ví dụ sau khi có JAR và toolchain phù hợp:

~~~bash
jpackage --type dmg --name PackCheck \
  --input build/input --main-jar packcheck.jar \
  --main-class PackCheck --dest build/dist
~~~

Các option macOS khác như `--mac-sign` chỉ dùng khi dự án đã có quy trình quản lý danh tính ký số và khóa hợp lệ.

## 6. Ví dụ Java 17+ hoàn chỉnh: build JAR rồi thử app-image

Để kiểm tra JDK đủ công cụ, ta tạo một ứng dụng console không có dependency bên ngoài. **Chạy trên từng nền tảng bằng cú pháp shell tương ứng**. Việc tạo app-image giúp loại trừ lỗi cơ bản trước khi thử native installer.

Tạo file **`PackCheck.java`**:

~~~java
public class PackCheck {
    public static void main(String[] args) {
        System.out.println("PACKAGE_OK");
    }
}
~~~

### 6.1. Windows PowerShell

Đứng tại thư mục có `PackCheck.java`:

~~~powershell
New-Item -ItemType Directory -Force -Path .\build\classes, .\build\input, .\build\dist | Out-Null

javac --release 17 -d .\build\classes .\PackCheck.java
jar --create --file .\build\input\packcheck.jar -C .\build\classes .

jpackage --type app-image --name PackCheck --input .\build\input --main-jar packcheck.jar --main-class PackCheck --dest .\build\dist --win-console

& .\build\dist\PackCheck\PackCheck.exe
~~~

### 6.2. Linux Bash

~~~bash
mkdir -p build/classes build/input build/dist
javac --release 17 -d build/classes PackCheck.java
jar --create --file build/input/packcheck.jar -C build/classes .

jpackage --type app-image --name PackCheck \
  --input build/input --main-jar packcheck.jar \
  --main-class PackCheck --dest build/dist

./build/dist/PackCheck/bin/PackCheck
~~~

### 6.3. macOS Terminal

~~~bash
mkdir -p build/classes build/input build/dist
javac --release 17 -d build/classes PackCheck.java
jar --create --file build/input/packcheck.jar -C build/classes .

jpackage --type app-image --name PackCheck \
  --input build/input --main-jar packcheck.jar \
  --main-class PackCheck --dest build/dist

./build/dist/PackCheck.app/Contents/MacOS/PackCheck
~~~

**Stdout của launcher ứng dụng khi thành công:**

~~~text
PACKAGE_OK
~~~

- `javac --release 17` kiểm tra compiler và khả năng biên dịch mã cho Java 17.
- `jar --create` tạo file `packcheck.jar`. `--main-jar` trong `jpackage` là tên JAR **nằm trong `--input`**. `--main-class PackCheck` xác định entry point; JAR này không cần Main-Class manifest vì tùy chọn được cung cấp tường minh.
- `jpackage --type app-image` kết hợp JAR với launcher và runtime đi kèm. `--win-console` **chỉ dành cho Windows** để ứng dụng console có thể hiển thị stdout.
- Đường dẫn chạy launcher **khác nhau theo OS**: Windows `PackCheck.exe`, Linux `bin/PackCheck`, macOS `PackCheck.app/Contents/MacOS/PackCheck`.
- Nếu thư mục output của lần build trước đã tồn tại, công cụ có thể từ chối tạo app-image. Dùng thư mục build mới/sạch **một cách có chủ đích** và không ghi đè artifacts khác.
- Lệnh sẽ không hoạt động trên máy chưa có JDK 17+ phù hợp. Không thể bảo đảm cùng một installer hay runtime image dùng được cho mọi OS.

**Kết quả kiểm chứng thực tế:** trên môi trường Windows với JDK 24, chuỗi `javac --release 17` → `jar` → `jpackage --type app-image --win-console` tạo được launcher; chạy launcher in đúng `PACKAGE_OK` và trả exit code 0. Đây là kiểm tra trên một môi trường, **không phải cam kết** installer Windows, Linux hoặc macOS nào cũng chạy nếu thiếu tools.

## 7. Sau app-image: tạo native installer khi prerequisites đã sẵn

### Windows, WiX phù hợp

~~~powershell
jpackage --type msi --name PackCheck --input .\build\input --main-jar packcheck.jar --main-class PackCheck --dest .\build\dist --win-console

# Hoặc chạy một lần riêng với --type exe nếu cần EXE installer.
~~~

Chỉ chạy khi WiX đã được kiểm tra. Không cần `--win-console` với GUI không sử dụng console. Cần test installer và uninstaller trên máy sạch; không chỉ kiểm tra file `.msi`/`.exe` xuất hiện.

### Linux DEB hoặc RPM

~~~bash
jpackage --type deb --name PackCheck \
  --input build/input --main-jar packcheck.jar \
  --main-class PackCheck --dest build/dist

# Trên distro/toolchain RPM thích hợp, dùng --type rpm thay deb.
~~~

Thực thi `deb` cần môi trường Linux và công cụ DEB, `rpm` cần toolchain RPM. Không nhầm `--type deb` với việc đưa nguyên JAR vào `.deb` mà không có runtime.

### macOS DMG hoặc PKG

~~~bash
jpackage --type dmg --name PackCheck \
  --input build/input --main-jar packcheck.jar \
  --main-class PackCheck --dest build/dist

# Chạy riêng với --type pkg nếu muốn .pkg installer.
~~~

Đóng gói chưa đồng nghĩa ký số hoặc notarization. Khi phát hành rộng, thực hiện các bước bảo mật tương ứng kênh phân phối và chính sách macOS.

## 8. Dùng `jlink` và kiểm tra runtime thật bên trong package

Nếu `--runtime-image` không được chỉ định, `jpackage` tạo runtime bằng `jlink`. Điều này thường giúp người dùng cuối không cần tự cài một JVM riêng, nhưng **runtime image chỉ đúng khi các Java modules và native libraries cần thiết đã được bao gồm**.

Một ứng dụng có thể build thành công nhưng launcher sau đóng gói lại thiếu provider/mô-đun được tải gián tiếp bằng `ServiceLoader`, JNI hoặc reflection.

Khi muốn cung cấp runtime tạo sẵn:

~~~bash
# Chỉ minh họa cú pháp; path/to/runtime phải là runtime image thực.
jpackage --type app-image --name PackCheck \
  --input build/input --main-jar packcheck.jar \
  --main-class PackCheck --dest build/dist \
  --runtime-image path/to/runtime
~~~

Không coi đây là lệnh chạy được nếu chưa tạo `path/to/runtime` tương thích OS/architecture. Muốn tùy biến modules, xem các option `--add-modules`, `--module-path`, `--jlink-options` hoặc dùng `jlink` có chủ đích.

**Chi tiết còn áp dụng từ JDK 25:** Oracle ghi rõ `jpackage` **không còn tự thêm service bindings** trong runtime image như các phiên bản trước; nếu ứng dụng thực sự phụ thuộc các provider dịch vụ đó, hãy kiểm tra và dùng `--jlink-options` với `--bind-services` khi phù hợp, đồng thời bảo toàn những option mặc định cần thiết được hướng dẫn trong JDK đang chạy. Đây là lý do cần test **launcher bên trong output** thay vì chỉ kiểm tra tool `jpackage` tồn tại.

## 9. Thiết kế CI/CD cho nhiều hệ điều hành

Một pipeline phát hành đa nền tảng nên có các job riêng:

| Job | Runner | Kiểm tra |
| --- | --- | --- |
| `win-x64` | Windows x64 + JDK + WiX | JDK PATH, WiX version, app-image, EXE/MSI, cài/gỡ |
| `macos-arm64` | macOS ARM64 + JDK, CLT khi cần | App bundle, DMG/PKG, ký/notarize nếu yêu cầu |
| `linux-deb` | Linux distro có `dpkg-deb`/`fakeroot` | App-image, DEB, cài/gỡ và runtime |
| `linux-rpm` | Linux distro có `rpmbuild` | App-image, RPM, cài/gỡ và runtime |

Mỗi job nên ghi log **OS, architecture, java/javac/jpackage versions, package type, tool native version, mã thoát và đường dẫn output**. Không đưa khóa ký số, tokens hoặc passwords vào log. Gói từ một runner không thể được coi là hợp lệ trên nền tảng khác nếu chưa có test tương ứng.

**Không giả định cross-packaging:** dùng Linux container trên Windows host vẫn là `jpackage` chạy trong Linux. Nếu cần installer Windows, cần một job thực sự chạy công cụ trên Windows.

## 10. Bảng lỗi thường gặp và cách khoanh vùng

| Dấu hiệu | Kiểm tra trước | Xử lý |
| --- | --- | --- |
| `java --version` chạy, `jpackage` báo không tìm thấy | PATH, JDK đầy đủ, custom runtime, `JAVA_HOME` | Chọn JDK 17+ có tools, gọi đúng executable |
| `javac` và `jpackage` khác JDK | `Get-Command`/`command -v`, IDE/CI toolchains | Khóa nhất quán JDK cho build |
| Windows MSI/EXE báo lỗi tool phụ trợ | WiX được cài chưa, CLI có trên PATH chưa, version | Dùng WiX/JDK tương thích; JDK 24+ hỗ trợ WiX 4/5 |
| Windows app-image chạy, MSI không tạo | Installer prerequisites/metadata | Giữ kết quả app-image; xem log `--verbose` của installer |
| Linux DEB không tạo | `dpkg-deb`, `fakeroot`, distro | Cài dependencies theo distro/format |
| Linux RPM không tạo | `rpm-build`/`rpmbuild` | Chuẩn bị RPM toolchain |
| macOS DMG/PKG hoặc ký gói lỗi | `pkgbuild`, `hdiutil`, `xcode-select`, identity | Kiểm tra tools và signing policy |
| Muốn tạo EXE từ Linux | OS builder không đúng | Chạy job trên Windows |
| `--win-console` không hợp lệ | Đang chạy Linux/macOS | Chỉ dùng option theo `--help` của platform |
| JAR không tìm thấy | `--input`, `--main-jar`, tên file | Sửa đường dẫn/đầu vào |
| Launcher xuất hiện nhưng không chạy | Runtime thiếu module/provider/native library; sai architecture | Chạy launcher; kiểm tra `--runtime-image`, JAR và dependencies |
| Không nhận GUI hoặc stdout | Cấu hình launcher, platform, quyền và màn hình | Đối chiếu `--win-console`, GUI libs và môi trường chạy |
| Gói chỉ cài được trên máy developer | OS/CPU/dependency/signing khác máy đích | Test máy sạch theo support matrix |
| `--type app-image` báo output đã tồn tại | Dùng lại output từ lần trước | Dùng output sạch, quản lý artifacts có chủ đích |

**Trình tự kiểm tra tiết kiệm thời gian:**

~~~text
1. Xác minh OS, architecture
2. java + javac + jar + jlink + jpackage hoạt động/cùng JDK?
   - Không -> sửa JDK, JAVA_HOME, PATH
3. Build JAR và tạo --type app-image, chạy launcher?
   - Không -> xem main-class, modules, runtime, libraries, output
4. Tạo installer đúng OS, đủ WiX / DEB / RPM / mac tools?
   - Không -> xem --verbose và lỗi native toolchain
5. Cài/chạy/gỡ trên máy sạch tương ứng với OS/architecture
~~~

Công cụ `--help` xác nhận syntax, **không xác nhận native dependencies đã sẵn**; `--verbose` và lệnh tạo package thực tế mới giúp chẩn đoán đúng nguyên nhân.

## 11. Checklist cuối và bài tập

**Checklist trước phát hành:**

- [ ] Đã biết chính xác hệ điều hành và architecture của build host và target.
- [ ] Đã xác nhận `java`, `javac`, `jar`, `jlink`, `jpackage` ở đúng toolchain.
- [ ] Đã kiểm tra `JAVA_HOME`/`PATH`, phiên bản JDK không bị lệch giữa IDE và CI.
- [ ] Đã chọn `--type` hợp lệ cho **nền tảng đang chạy**.
- [ ] Đã kiểm tra WiX cho Windows EXE/MSI, DEB/RPM builder trên Linux, công cụ pkg/dmg và CLT/signing khi cần trên macOS.
- [ ] Đã chuẩn bị JAR/modules, main class/module, resources, native libraries và license/metadata.
- [ ] Đã chạy thành công `--type app-image` và launcher thực.
- [ ] Đã thử định dạng installer cần phát hành, cài/gỡ/cập nhật theo chính sách sản phẩm.
- [ ] Đã kiểm tra runtime bundled, Java modules/service providers và dependencies thực tế.
- [ ] Đã test package trên máy sạch, OS/version và CPU đúng target.
- [ ] Đã ghi tool versions, logs, artifact hashes; secrets ký số không nằm trong log.

**Bài tập thực hành:**

1. Chạy `java --version`, `javac --version` và `jpackage --version` trên máy bạn. Nếu phiên bản khác nhau, giải thích nguồn PATH/JAVA_HOME.
2. Tạo `PackCheck.java`, build JAR, tạo app-image và chạy launcher phù hợp OS. Ghi lại output `PACKAGE_OK`.
3. Trên Windows, kiểm tra `Get-Command wix,candle,light`. Giải thích vì sao chỉ có WiX 5 có thể không đáp ứng toolchain JDK 17/21.
4. Trên Linux, giải thích khác nhau giữa tạo DEB và RPM, và vì sao `jpackage` không tạo Windows EXE trực tiếp trên Linux.
5. Trên macOS, kiểm tra `xcode-select -p` và nêu vì sao có CLT vẫn chưa đủ để ký/notarize.
6. Tạo app-image thành công nhưng installer báo thiếu native tool. Hãy đề xuất hướng sửa **không đổi mã Java vô ích**.
7. So sánh `javac --release 17` với `jpackage` chạy từ JDK 24: runtime bundled dùng JDK nào?
8. Thiết kế CI matrix cho Windows, Linux và macOS; mỗi job cần ghi những thông tin phiên bản và test gì?
9. Ứng dụng dùng `ServiceLoader` chạy bình thường trong IDE nhưng thiếu provider từ JDK 25 app-image; bạn sẽ kiểm tra runtime và `--bind-services` như thế nào?

## 12. Nguồn chính thống

- [Oracle JDK 25 – Packaging Overview và Packaging Pre-Reqs](https://docs.oracle.com/en/java/javase/25/jpackage/packaging-overview.html): yêu cầu mỗi OS, app-image, runtime bundled và service-binding change JDK 25.
- [Oracle JDK 25 – jpackage command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html): các tùy chọn `--type`, `--input`, `--main-jar`, `--runtime-image` và loại package.
- [Oracle JDK 17 – jpackage command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jpackage.html): cách dùng trên JDK 17.
- [OpenJDK JEP 392 – Packaging Tool](https://openjdk.org/jeps/392): công cụ `jpackage` ổn định từ JDK 16.
- [Oracle JDK 24 Release Notes – WiX Toolset v4/v5](https://www.oracle.com/java/technologies/javase/24-relnote-issues.html): từ JDK 24 hỗ trợ WiX 3, 4, 5.
- [Oracle JDK 25 – jlink command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jlink.html): tạo runtime image.

**Ghi nhớ:** **JDK đầy đủ + toolchain nhất quán**, **native packaging tools của đúng OS/format** và **launcher kiểm thử từ app-image** là ba lớp xác minh tách biệt. `jpackage` hiện đại đóng gói được ứng dụng trên Windows, macOS, Linux, nhưng **không hỗ trợ tạo native installer của một OS khác trên cùng build host**.