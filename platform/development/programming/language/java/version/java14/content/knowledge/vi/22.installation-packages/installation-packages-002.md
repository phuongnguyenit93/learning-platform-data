# Tạo gói cài đặt từ application image đã kiểm chứng bằng jpackage

> **Bối cảnh:** Java 14 → *Gói cài đặt* → **Tạo gói từ app image đã kiểm chứng**. `jpackage` từng ở trạng thái incubating trong JDK 14–15 nhưng đã là công cụ chính thức từ **JDK 16 (JEP 392)**. Bài áp dụng cho **JDK 17+ hiện đại**, dùng API và lệnh `jpackage` còn được hỗ trợ. Tập trung vào quy trình **build image → chạy thử và chốt image → tạo installer từ chính image**, không dùng cú pháp incubator cũ.

## 1. Mục tiêu và lý do cần hai giai đoạn

Khi đóng gói một ứng dụng Java để phân phối, hai công việc sau có mục đích **khác nhau**:

1. **Tạo và kiểm chứng application image**: kiểm tra launcher, JAR/modules, cấu hình JVM, resource files, native libraries và Java runtime đi kèm có hoạt động đúng hay không.
2. **Tạo native installer từ application image ấy**: đưa cây ứng dụng đã xác nhận vào định dạng cài đặt theo hệ điều hành (MSI/EXE, DEB/RPM, DMG/PKG), sau đó thử cài đặt, nâng cấp và gỡ cài đặt.

`jpackage` có tùy chọn **`--type app-image`** cho giai đoạn 1 và **`--app-image <path>`** cho giai đoạn 2. Chúng **không phải cùng một tùy chọn**.

~~~text
Mã Java / JAR / modules
          |
          v
jpackage --type app-image
          |
          v
Application image (launcher + app + runtime)
          |
          +--> Chạy launcher, smoke tests, cấu hình, modules, permissions
          |
          +--> Chỉnh sửa có kiểm soát nếu cần
          |         |
          |         +--> chạy lại các kiểm tra sau khi chỉnh sửa
          v
Image ĐÃ KIỂM CHỨNG, cố định nội dung
          |
          v
jpackage --type <native-installer> --app-image <image> --name <name>
          |
          v
Installer (MSI/EXE, DEB/RPM, DMG/PKG)
          |
          v
Kiểm thử cài/chạy/nâng cấp/gỡ trên OS mục tiêu
~~~

**Điểm chính:** tạo lại installer từ image đã kiểm chứng giúp tránh việc một pipeline vô tình **build lại application image từ nguồn đầu vào khác** khi tạo installer. Tuy nhiên, việc **installer thành công** vẫn phải được kiểm chứng riêng; image chạy được không tự chứng minh quy trình cài/gỡ, shortcut, quyền hoặc ký số hoạt động.

## 2. Phân biệt ba tùy chọn dễ nhầm

| Tùy chọn | Mục đích | Dùng ở giai đoạn nào? |
| --- | --- | --- |
| `--type app-image` | Yêu cầu `jpackage` **tạo cây application image** thay vì installer | Giai đoạn 1 |
| `--app-image <directory>` | Chỉ định **application image có sẵn** để tạo installable package; trên macOS còn có chế độ ký image theo tài liệu | Giai đoạn 2 |
| `--runtime-image <directory>` | Cung cấp **Java runtime image** đã tạo bằng `jlink` hoặc công cụ phù hợp | Khi tạo app-image ban đầu, **không đi kèm `--app-image`** |

### 2.1. `--name` là bắt buộc ở lượt tạo package từ image

Theo hướng dẫn Oracle JDK 25, khi dùng `--app-image` để tạo installer từ application image đã có, phải truyền **`--name`**.

Ví dụ, từ một image tên `ImageCheck` trên Windows:

~~~powershell
jpackage --type msi --name ImageCheck --app-image .\build\images\ImageCheck --dest .\build\installers
~~~

Tên `ImageCheck` cần được chọn có chủ đích và nhất quán với image, launcher, versioning và chính sách nâng cấp. Đừng nghĩ `--app-image` tự loại bỏ yêu cầu xác định tên ứng dụng.

### 2.2. Không kết hợp `--app-image` với `--runtime-image`

Hai tùy chọn **loại trừ nhau** theo hướng dẫn Oracle:

~~~text
Error: Mutually exclusive options [--runtime-image] and [--app-image]
~~~

Bởi `--app-image` trỏ tới **toàn bộ ứng dụng đã bao gồm runtime**. Nếu muốn thay runtime, hãy **tạo lại image ở giai đoạn 1 với runtime mới**, chạy lại smoke tests, rồi mới dùng image ấy để tạo installer. Không thể “tiêm” một runtime khác bằng cách thêm `--runtime-image` vào lệnh giai đoạn 2.

### 2.3. Đừng nhầm với cách đóng gói trực tiếp từ JAR

~~~bash
# Đi thẳng từ JAR vào installer, bỏ qua bước image được kiểm chứng:
jpackage --type deb --name SampleApp --input build/input --main-jar sample.jar

# Dùng application image đã được build/test trước đó:
jpackage --type deb --name SampleApp --app-image build/images/SampleApp
~~~

Hai dòng trên là **ví dụ cú pháp dành cho Linux**, không phải lệnh độc lập chạy được khi chưa chuẩn bị `sample.jar`/image và native DEB tools. Dòng đầu cho phép `jpackage` tạo image khi đóng gói. Dòng sau **tái sử dụng image có sẵn**.

**Quy tắc:** khi dùng `--app-image`, không tiếp tục giả định `--input`, `--main-jar`, `--main-class`, `--module` hoặc `--jlink-options` của lượt tạo image sẽ được chạy lại. Các nội dung launcher/runtime cần được xác lập và kiểm tra ở **giai đoạn 1**. Tránh trộn hai chế độ đóng gói.

## 3. App-image chứa gì và cần kiểm chứng gì?

Một image do `jpackage --type app-image` tạo ra thường có:

| Hệ điều hành | Đường dẫn image ví dụ | Thành phần chính |
| --- | --- | --- |
| Windows | `build/images/ImageCheck/` | `ImageCheck.exe`, `app/`, `runtime/` |
| Linux | `build/images/ImageCheck/` | `bin/ImageCheck`, `lib/app/`, `lib/runtime/` |
| macOS | `build/images/ImageCheck.app/` | `Contents/MacOS/ImageCheck`, `Contents/app/`, `Contents/runtime/` |

Cấu trúc chính xác và tên các file nội bộ có thể thay đổi theo JDK; đừng tự chỉnh sửa file do tool sinh nếu không hiểu hợp đồng launcher/runtime.

Các kiểm tra cần hoàn tất **trước khi gọi `--app-image` ở giai đoạn 2**:

1. **Launcher thực sự khởi chạy.** Chạy file thực thi trong image, kiểm tra exit code và tác vụ quan trọng; không chỉ kiểm tra thư mục có tồn tại.
2. **Bundled runtime phù hợp.** Kiểm tra các Java modules, service providers, TLS/JDBC/desktop modules nếu có; không mặc định `javac --release 17` khiến image chứa Java 17 nếu builder là JDK mới hơn.
3. **Tài nguyên và dependency đầy đủ.** File cấu hình mặc định, localization, icons, bản quyền, JNI/native libraries và file được load bằng đường dẫn tương đối.
4. **Không cần JDK cài trên máy người dùng.** Thử trên môi trường sạch để xác nhận launcher thật sự dùng runtime đi kèm; môi trường developer có JDK không phải bằng chứng.
5. **OS/architecture phù hợp.** Image Windows không phải Linux image, image macOS x64 không tự chạy trên mọi máy ARM64.
6. **Bảo mật.** Không nhúng token, API keys, mật khẩu hoặc private signing keys vào image. Kiểm tra quyền thực thi và integrity của artifact.
7. **Các thay đổi sau kiểm thử.** Nếu thêm file, sửa launcher config, thay JVM options, thay JAR hay runtime, trạng thái “đã kiểm chứng” không còn tự động đúng; **phải chạy lại test và chốt lại image mới**.

**Không phân phối image chỉ vì lệnh `jpackage` kết thúc mã 0.** Cần chạy ít nhất một smoke test tiêu biểu, đặc biệt với ứng dụng có GUI, JNI hoặc sử dụng `ServiceLoader`.

## 4. Ví dụ Java 17+ chạy được để tạo và xác nhận image

Tạo một chương trình nhỏ để tách lỗi toolchain khỏi lỗi ứng dụng thật. Lưu file **`ImageCheck.java`**:

~~~java
public class ImageCheck {
    public static void main(String[] args) {
        System.out.println("VERIFIED_IMAGE_OK");
    }
}
~~~

Biên dịch và đóng JAR bằng JDK 17+:

~~~bash
javac --release 17 ImageCheck.java
jar --create --file image-check.jar ImageCheck.class
java ImageCheck
~~~

**Kết quả từ chương trình Java trực tiếp:**

~~~text
VERIFIED_IMAGE_OK
~~~

Đây là chương trình Java hoàn chỉnh, không có dependency ngoài JDK. Khi tạo `app-image` sau đó, phải đặt JAR vào `--input` và chọn `--main-class ImageCheck`; JAR này không cần có `Main-Class` trong manifest vì được truyền tường minh.

### 4.1. Windows PowerShell: tạo và kiểm chứng image

Giả sử đang đứng trong thư mục chứa `ImageCheck.java`:

~~~powershell
New-Item -ItemType Directory -Force -Path .\build\classes, .\build\input, .\build\images, .\build\installers | Out-Null

javac --release 17 -d .\build\classes .\ImageCheck.java
jar --create --file .\build\input\image-check.jar -C .\build\classes .

jpackage --type app-image --name ImageCheck --app-version 1.0 --input .\build\input --main-jar image-check.jar --main-class ImageCheck --dest .\build\images --win-console

Test-Path .\build\images\ImageCheck\ImageCheck.exe
Test-Path .\build\images\ImageCheck\runtime
& .\build\images\ImageCheck\ImageCheck.exe
$LASTEXITCODE
~~~

**Stdout riêng của launcher Java**:

~~~text
VERIFIED_IMAGE_OK
~~~

Giá trị `$LASTEXITCODE` sau khi chạy launcher phải bằng `0` khi chương trình thành công. `--win-console` cho phép ứng dụng console in kết quả ra console; không cần dùng cho mọi ứng dụng GUI. `Test-Path` chỉ xác nhận sự tồn tại, **không thay việc chạy launcher**.

**Kiểm chứng thực tế:** chương trình và các lệnh tương đương đã chạy trên Windows với JDK 24; app-image có launcher, file cấu hình và runtime, launcher in `VERIFIED_IMAGE_OK` với exit code `0`. Điều đó xác nhận giai đoạn image, **chưa phải** native installer.

### 4.2. Linux Bash: tạo image và chạy launcher

~~~bash
mkdir -p build/classes build/input build/images build/installers

javac --release 17 -d build/classes ImageCheck.java
jar --create --file build/input/image-check.jar -C build/classes .

jpackage --type app-image --name ImageCheck --app-version 1.0 \
  --input build/input --main-jar image-check.jar \
  --main-class ImageCheck --dest build/images

test -x build/images/ImageCheck/bin/ImageCheck
./build/images/ImageCheck/bin/ImageCheck
echo $?
~~~

Nếu thành công, launcher in `VERIFIED_IMAGE_OK` và `echo $?` cho `0`. Ví dụ cần **JDK, Linux và các thư viện hệ thống phù hợp**; không thể chạy trực tiếp câu lệnh Linux trên PowerShell.

### 4.3. macOS Terminal: tạo `.app` và chạy launcher

~~~bash
mkdir -p build/classes build/input build/images build/installers

javac --release 17 -d build/classes ImageCheck.java
jar --create --file build/input/image-check.jar -C build/classes .

jpackage --type app-image --name ImageCheck --app-version 1.0 \
  --input build/input --main-jar image-check.jar \
  --main-class ImageCheck --dest build/images

test -x build/images/ImageCheck.app/Contents/MacOS/ImageCheck
./build/images/ImageCheck.app/Contents/MacOS/ImageCheck
echo $?
~~~

Launcher từ Terminal in `VERIFIED_IMAGE_OK`; exit code bằng `0` khi thành công. Nếu bundle cần signing/notarization hoặc app resources đặc biệt, kiểm thử thêm các yêu cầu đó trước khi phát hành thực tế.

### Lưu ý quan trọng về script mẫu

- Chạy **đúng phần lệnh của hệ điều hành bạn đang dùng**.
- Dùng **output directory mới**. Nếu `build/images/ImageCheck` hoặc `ImageCheck.app` đã tồn tại, `jpackage` có thể từ chối tạo lại; không xóa artifact cũ tùy tiện.
- Lệnh JAR được lấy từ `build/input` ở bước tạo image; **giai đoạn 2 không cần chỉ định JAR lại**.
- `--app-version 1.0` được xác định khi tạo image; kiểm tra version và nâng cấp theo chính sách phát hành. Đừng tự thay version vào installer mà chưa thử tương thích nâng cấp.
- Kiểm tra các cách khởi động thực tế, không chỉ `System.out.println`; ví dụ cố ý tối giản để chứng minh quy trình hai giai đoạn.

## 5. Tạo installer từ **image đã kiểm chứng**

Sau khi **đã chạy launcher thành công và chốt nội dung image**, hãy dùng **`--app-image`** cùng `--type` chọn đúng định dạng native. Chỉ dùng installer tools của **nền tảng đang build**.

### 5.1. Windows: EXE hoặc MSI

Trên Windows, `--type msi` và `--type exe` cần **WiX Toolset** tương thích với JDK builder.

~~~powershell
# Kiểm tra WiX CLI. WiX v3 thường có candle/light;
# WiX v4/v5 có wix CLI.
Get-Command wix, candle, light -ErrorAction SilentlyContinue |
    Select-Object Name, Source

# Lệnh chỉ chạy khi đã có WiX và image được kiểm chứng:
jpackage --type msi --name ImageCheck --app-image .\build\images\ImageCheck --dest .\build\installers --win-menu --win-shortcut --verbose

# Có thể tạo EXE installer ở một lần chạy riêng:
# jpackage --type exe --name ImageCheck --app-image .\build\images\ImageCheck --dest .\build\installers --verbose
~~~

**Đặc điểm:** installer dùng **toàn bộ image đã build**, không phải biên dịch lại class Java. `--win-menu` và `--win-shortcut` là các tùy chọn **installer** tạo mục Start Menu/shortcut; không thay thế test launcher trong image. `--verbose` giúp phân tích lỗi khi tạo gói.

**Tình huống thử nghiệm thực tế:** trên Windows JDK 24, image ví dụ tạo và chạy thành công, nhưng lệnh `jpackage --type msi --app-image ...` **không tạo được MSI** vì **không tìm thấy WiX v3 `candle.exe`/`light.exe` hoặc WiX v4/v5 `wix.exe`**. Đây là lỗi thiếu công cụ native installer, **không phải lỗi mã Java hoặc app-image**. Không được đánh dấu “installer build PASS” trong môi trường ấy cho đến khi cài/cấu hình WiX phù hợp và chạy thành công.

Tính tương thích WiX tùy bản JDK: **JDK 24+** hỗ trợ WiX 3/4/5; toolchain JDK cũ như 17/21 không nên mặc định chạy được với WiX 5. Kiểm tra đúng release notes của JDK bạn đang dùng. Không phân phối EXE/MSI mà chưa kiểm tra ký số và chính sách tin cậy của Windows nếu sản phẩm cần.

### 5.2. Linux: DEB hoặc RPM

Khi đang chạy `jpackage` trên Linux có `dpkg-deb`/`fakeroot` (DEB) hoặc `rpmbuild` (RPM), có thể dùng:

~~~bash
# Trên Linux tương thích Debian/Ubuntu:
command -v dpkg-deb
command -v fakeroot

jpackage --type deb --name ImageCheck \
  --app-image build/images/ImageCheck \
  --linux-package-name imagecheck \
  --dest build/installers --verbose

# Trên Linux/RPM toolchain phù hợp, chạy riêng:
# jpackage --type rpm --name ImageCheck \
#   --app-image build/images/ImageCheck \
#   --linux-package-name imagecheck --dest build/installers
~~~

`--linux-package-name imagecheck` giúp xác định tên package theo quy tắc gói Linux; `--name ImageCheck` vẫn xác định ứng dụng theo metadata của image. Chỉ tạo định dạng mà distro và toolchain của bạn hỗ trợ. Installer DEB/RPM cần kiểm thử qua package manager trên distro mục tiêu, vì đường dẫn cài đặt, quyền và runtime dependencies có thể khác máy build.

### 5.3. macOS: DMG hoặc PKG

Với app-image đã kiểm chứng `build/images/ImageCheck.app`:

~~~bash
# Trên macOS với các công cụ đóng gói phù hợp:
command -v hdiutil
command -v pkgbuild

jpackage --type dmg --name ImageCheck \
  --app-image build/images/ImageCheck.app \
  --dest build/installers --verbose

# Hoặc tạo PKG trong một lần riêng:
# jpackage --type pkg --name ImageCheck \
#   --app-image build/images/ImageCheck.app \
#   --dest build/installers
~~~

Signing và notarization là **các bước bổ sung khi kênh phân phối yêu cầu**, không tự xảy ra chỉ vì có `.dmg` hoặc `.pkg`. Oracle có chế độ đặc biệt **ký app-image trên macOS** bằng `jpackage --type app-image --app-image ... --mac-sign`; đây không phải câu lệnh tạo installer, và có tập tùy chọn cho phép rất hạn chế. Nếu ký/chỉnh app-image, phải kiểm tra lại tính toàn vẹn và launcher sau thay đổi.

### 5.4. Không build chéo hệ điều hành

| Máy đang chạy `jpackage` | Có thể tạo định dạng native | Không tạo trực tiếp bằng `jpackage` |
| --- | --- | --- |
| Windows | `exe`, `msi` | Linux DEB/RPM, macOS DMG/PKG |
| Linux | `deb`, `rpm` | Windows EXE/MSI, macOS DMG/PKG |
| macOS | `dmg`, `pkg` | Windows EXE/MSI, Linux DEB/RPM |

CI cần runners **đúng OS** (và kiểm tra architecture) cho từng artifact. Một Linux container trên host Windows vẫn là môi trường Linux với jpackage bên trong container.

## 6. Đảm bảo installer dùng **đúng** image đã kiểm chứng

### 6.1. Xác định artifact được phép phát hành

Để tránh tình huống “test image A nhưng package image B”, mỗi build nên chốt:

- **Tên ứng dụng / phiên bản / nền tảng / architecture**.
- **Đường dẫn image được kiểm chứng** và đường dẫn output installer **riêng**.
- **Commit, JDK version, build job ID** hoặc nhãn định danh phù hợp.
- **Checksum hoặc manifest** của artifact (nếu cần kiểm soát chuỗi cung ứng) và kết quả test launcher.
- Danh sách những sửa đổi đã chủ động thực hiện trên image (resources, cấu hình launcher, runtime) và kết quả test lại.

Không sửa các file của image **sau khi đã chốt kiểm thử** rồi vẫn gọi nó là image đã kiểm chứng. Nếu cần đổi cấu hình hoặc ký image khiến các bytes thay đổi, cập nhật artifact identity và xác thực lại.

### 6.2. Khác biệt giữa kiểm thử launcher và kiểm thử installer

| Loại kiểm tra | Image stage | Installer stage |
| --- | --- | --- |
| File launcher có tồn tại và khởi động | **Có** | Có, nhưng cần kiểm lại sau cài |
| Java bundled runtime đủ modules | **Có** | Xác nhận không bị thay đổi/mất sau đóng gói |
| File cấu hình/JAR/resources | **Có** | Xác nhận payload được cài đúng |
| Cài đặt bằng UI hoặc package manager | Không, vì app-image không phải installer | **Có** |
| Tạo shortcut, file association, menu | Không kết luận từ launcher | **Có** |
| Quyền cài đặt và quyền chạy | Chỉ kiểm tra quyền của image hiện tại | **Có** trên máy sạch/standard user |
| Nâng cấp từ phiên bản trước | Không được xác nhận bởi smoke test | **Có** |
| Gỡ cài đặt và cleanup | Không thuộc app-image | **Có** |
| Signing/notarization/trust | Có thể cần khi ký image | Kiểm tra lại trên artifact được phân phối |

**Bài học:** `jpackage --app-image` đưa một image đã chuẩn bị vào installer, nhưng **không cấp “giấy chứng nhận chất lượng” cho installer**. Test image và installer là hai tầng bằng chứng.

### 6.3. Phạm vi của việc tái sử dụng image

Khi dùng `--app-image`, `jpackage` không cần build lại `--input` hoặc chạy lại compiler của chương trình. Đây là lợi ích cốt lõi nếu đã thử image tốt. Tuy nhiên, installer vẫn có thể tùy biến **metadata, đích cài, menu, license, signing và script cài đặt** thông qua tùy chọn packaging, khiến kết quả cài đặt khác một image copy đơn giản.

Đừng coi `--app-image` là cơ chế đóng dấu chữ ký số, khóa nội dung không thể thay đổi, hay tự kiểm tra checksum. Những kiểm soát đó thuộc CI/release process.

## 7. Xử lý thay đổi app-image giữa hai giai đoạn

Oracle cho phép **chỉnh application image** trước khi dựng installer. Một số lý do chính đáng:

- Bổ sung tài nguyên hoặc cấu hình đi kèm ứng dụng.
- Đổi cấu hình launcher có kế hoạch (chỉ khi hiểu định dạng và version tương ứng).
- Thay hoặc tùy biến runtime để ứng dụng có đủ modules/services.
- Sắp xếp lại một số file payload theo yêu cầu triển khai.

**Quy trình an toàn:**

1. Build image ban đầu từ nguồn và JDK đã chốt.
2. Thực hiện thay đổi có ghi nhận; tránh chèn secrets hoặc file tạm.
3. Kiểm tra lại launcher **sau thay đổi**, đặc biệt là các tính năng cần Java modules, reflection, ServiceLoader hoặc native library.
4. Chốt phiên bản artifact; không cho giai đoạn installer tự lấy một image khác.
5. Chạy `jpackage --app-image ... --name ...` để tạo native installer.
6. Kiểm thử installer và payload sau cài.

**Thay runtime:** tránh truyền `--runtime-image` cùng `--app-image` ở lượt dựng installer — **bị cấm**. Nếu cần runtime tùy chỉnh, tạo bằng `jlink`/JDK tương thích và dùng `--runtime-image` khi **tạo app-image ban đầu**, sau đó chạy kiểm tra lại. Với JDK 25+, runtime tự sinh bởi `jpackage` có thay đổi liên quan service bindings; phải xác nhận đủ providers thật trên image, không chỉ nhìn thông báo build thành công.

**Đừng sửa launcher nhị phân tùy ý**: các binary/metadata nội bộ do JDK tạo có thể thay đổi; một image “đã kiểm chứng” phải được giữ nguyên hoặc kiểm thử lại sau mọi thay đổi.

## 8. Chẩn đoán lỗi: hỏng image hay thiếu native packager?

| Triệu chứng | Giai đoạn/khả năng | Cách kiểm tra đúng |
| --- | --- | --- |
| `jpackage` không có trên PATH | Preflight JDK | `java --version`, `javac --version`, `jpackage --version`, JAVA_HOME |
| `--type app-image` lỗi vì thiếu JAR/main class | Giai đoạn image | `--input`, `--main-jar`, `--main-class`, module paths |
| Image có launcher nhưng launcher không chạy | Image chưa qua QA | Runtime/modules, config, OS/architecture, missing files |
| `--app-image` báo sai đường dẫn | Giai đoạn installer | Trỏ **đúng thư mục image**; macOS cần trỏ đúng bundle `.app` |
| Thêm `--runtime-image` cùng `--app-image` gây lỗi | Cấu hình installer sai | Không kết hợp hai option; build lại image với runtime đúng |
| Không truyền `--name` khi dùng `--app-image` | Thiếu tham số bắt buộc | Đặt `--name` cùng tên ứng dụng của image |
| Windows MSI/EXE lỗi “cannot find WiX tools” | Native installer toolchain | Cài/cấu hình WiX đúng bản/JDK; image có thể đã PASS |
| Linux DEB/RPM lỗi tools | Native installer | Kiểm tra `dpkg-deb`/`fakeroot`/`rpmbuild` theo distro |
| macOS DMG/PKG/signing lỗi | Native packager / signing | Kiểm tra `hdiutil`/`pkgbuild`/`xcode-select`/certificate |
| MSI/PKG/DEB tạo thành công nhưng app cài không mở | Hậu kiểm installer | Test trên máy sạch, logs, runtime paths, permissions |
| Tạo installer từ image sửa sau QA | Image “đã kiểm chứng” không còn đúng | Re-run smoke tests, chốt lại hash/version |
| CI build image OS này, installer OS khác | Không hỗ trợ cross-packaging | Build image và installer trên OS đích |
| Tạo image JDK24 với `--release 17`, nghĩ runtime là JDK17 | Nhầm compile target và bundled runtime | Xem runtime của image và test compatibility |

Cách khoanh vùng hợp lý: nếu **launcher từ image chạy được** nhưng `--type msi` lỗi thiếu WiX, hãy sửa **toolchain WiX** trước, không thay code Java. Nếu **launcher không chạy**, đừng cố dựng installer để “sửa” vấn đề; kiểm tra image trước.

### Lệnh chẩn đoán cơ bản

~~~bash
java --version
javac --version
jar --version
jlink --version
jpackage --version
jpackage --help

# Khi đã có native tools và file image, thêm --verbose vào
# lệnh jpackage tạo installer để nhận log chi tiết.
~~~

Các lệnh này dùng được trong shell hỗ trợ lệnh cơ bản của JDK, nhưng cú pháp `--app-image` và tool native vẫn phải theo **OS đang chạy**.

## 9. CI/CD: hai job hoặc hai stage có artifact identity rõ

Với ứng dụng thật, có thể tách pipeline thành các giai đoạn:

**Stage A – Build và Verify Image**

- Chọn JDK builder, build JAR/modules và chốt version.
- Gọi `jpackage --type app-image`.
- Chạy smoke tests launcher, dependency checks, kiểm tra bundled runtime.
- Lưu kết quả test và artifact identity (hash/manifest + OS/architecture).
- Chỉ khi PASS mới chuyển image sang giai đoạn installer.

**Stage B – Installer từ Image Đã Verify**

- Nhận **chính image đã được Stage A chốt** trên **cùng OS/architecture thích hợp**.
- Kiểm tra native packager (WiX, DEB/RPM builder, macOS tools/signing).
- Gọi `jpackage --type <installer-type> --name <name> --app-image <verified-image> --dest <installer-output>`.
- Chạy test cài đặt, chạy ứng dụng đã cài, upgrade/uninstall, signing/notarization khi cần.
- Chỉ phát hành artifact khi **cả hai stage** đạt yêu cầu.

### Build matrix gợi ý

| Job | Image được kiểm tra | Installer từ image |
| --- | --- | --- |
| Windows x64 | Windows app-image/EXE launcher | MSI và/hoặc EXE với WiX |
| Linux x64 | Linux app-image/launcher | DEB với fakeroot/dpkg-deb hoặc RPM với rpmbuild |
| macOS ARM64 | macOS `.app`/launcher | DMG và/hoặc PKG; signing/notarization nếu yêu cầu |

Không sao chép image Windows sang Linux rồi mong Linux `jpackage` “đóng lại” thành DEB. Image và runtime có mã native khác OS.

## 10. Checklist QA trước khi ký duyệt installer

- [ ] `jpackage` thuộc JDK phiên bản hiện hành đã chọn và hỗ trợ `--app-image`.
- [ ] App-image đã build bằng `--type app-image` trên **đúng OS/architecture** của package.
- [ ] Tên ứng dụng/version và các file payload đã được xác định rõ.
- [ ] Launcher trong image chạy thành công; exit code, chức năng, tài nguyên và runtime đã được test.
- [ ] Nếu image bị chỉnh sửa/ký lại, QA đã được chạy lại trên **artifact hiện tại**.
- [ ] `--app-image` trỏ **đúng image đã kiểm chứng**, không phải output installer hoặc runtime riêng.
- [ ] Lệnh installer có `--type` native và `--name` hợp lệ.
- [ ] **Không** truyền `--runtime-image` cùng `--app-image`.
- [ ] Native tools đã sẵn: WiX (Windows), DEB/RPM tools (Linux), macOS packagers; signing prerequisites nếu dùng.
- [ ] Output installer nằm ở **thư mục riêng** và không vô tình thay đổi image đầu vào.
- [ ] Installer tạo xong được test cài đặt, launcher từ install path, quyền user, shortcuts, resources.
- [ ] Các kịch bản nâng cấp/gỡ cài đặt, package metadata và versioning được kiểm thử.
- [ ] CI lưu log JDK/tool versions, checksum, OS/architecture, mã thoát; không xuất secrets.
- [ ] Chỉ đánh dấu release PASS khi **cả image QA và installer QA** đều PASS.

## 11. Bài tập thực hành

1. Tạo `ImageCheck.java` và app-image như mục 4. Chạy launcher để nhận `VERIFIED_IMAGE_OK`. Ghi đường dẫn image cùng version/JDK/OS.
2. Đọc hai lệnh `--type app-image` và `--app-image` trong `jpackage --help`, giải thích vì sao chúng thuộc hai giai đoạn khác nhau.
3. Trên Windows, giả sử app-image đã PASS nhưng `--type msi` báo thiếu WiX. Xác định bước cần sửa, nêu vì sao **không** nên sửa JAR.
4. Trên Linux, từ cùng image đã kiểm chứng, lập hai lệnh tạo `--type deb` và `--type rpm`; kiểm tra tool prerequisites tương ứng trước khi chạy.
5. Trên macOS, dùng `.app` đã smoke test để tạo `.dmg`; nêu điều kiện để ký gói/notarization khi phát hành thật.
6. Thử thêm `--runtime-image` vào lệnh đã có `--app-image` và đọc lỗi. Hãy giải thích cách đúng để chọn custom runtime tại giai đoạn image.
7. Tạo image version `1.0`, xác nhận launcher, sau đó thay một file cấu hình. Tại sao image này **cần QA lại** trước khi dựng installer?
8. Thiết kế hai stage CI giữ checksum/identity của image, quy định không rebuild khi tạo native installer, và viết tiêu chí release.
9. Đưa ra sự khác biệt giữa kiểm thử launcher từ image và kiểm thử sau cài: permissions, shortcuts, signing, upgrade và uninstall.
10. Giải thích tại sao `javac --release 17` dùng cùng JDK 24 `jpackage` không làm runtime bundled tự chuyển thành Java 17.

## 12. Tài liệu chuẩn

- [Oracle JDK 25 – Image and Runtime Modifications](https://docs.oracle.com/en/java/javase/25/jpackage/image-and-runtime-modifications.html): quy trình hai bước `--type app-image` → `--app-image`, yêu cầu `--name`, xung đột với `--runtime-image`.
- [Oracle JDK 25 – jpackage command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html): cú pháp tất cả tùy chọn, installer types và `--app-image`.
- [Oracle JDK 25 – Packaging Overview](https://docs.oracle.com/en/java/javase/25/jpackage/packaging-overview.html): cấu trúc generated image, prerequisites từng hệ điều hành và runtime.
- [Oracle JDK 24 – Image and Runtime Modifications](https://docs.oracle.com/en/java/javase/24/jpackage/image-and-runtime-modifications.html): xác nhận quy trình vẫn có trong JDK 24.
- [OpenJDK JEP 392 – Packaging Tool](https://openjdk.org/jeps/392): `jpackage` trở thành công cụ chính thức từ JDK 16.

**Ghi nhớ:** `--type app-image` tạo **ứng dụng có thể kiểm tra**; `--app-image` nạp **chính application image đã qua QA** để tạo installer. Dùng `--name`, chọn `--type` đúng hệ điều hành, không ghép `--runtime-image` vào lượt installer, và **kiểm thử cài đặt** riêng sau khi tạo gói. Một image hoạt động tốt là điều kiện tốt để đóng gói, **không phải bằng chứng cuối cùng rằng installer đã đạt chất lượng phát hành**.