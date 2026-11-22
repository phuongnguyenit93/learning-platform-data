# Tra cứu tùy chọn jpackage theo đúng JDK đang dùng

## 1. Vì sao phải tra cứu đúng JDK?

`jpackage` là công cụ của JDK giúp đóng gói ứng dụng Java thành **application image** có launcher và Java runtime đi kèm, hoặc thành **gói cài đặt native** như MSI/EXE, DEB/RPM hay DMG/PKG. Tùy chọn của công cụ cần được hiểu theo ba chiều:

- **Phiên bản JDK / jpackage**: JDK 17, 21, 24, 25, 26… có thể khác nhau ở options, defaults hoặc hành vi tạo runtime.
- **Hệ điều hành build**: Windows, Linux và macOS có các option riêng. Không thể đóng gói native cho OS khác chỉ bằng cách đổi `--type`.
- **Loại output**: `--type app-image` dùng để tạo và thử launcher; installer native có yêu cầu công cụ hệ thống và các tùy chọn khác.

**Quy tắc thực hành:** trước khi sao chép một lệnh từ blog, video, tài liệu dự án hoặc câu trả lời trên mạng, hãy chạy **`jpackage --help` của chính JDK đang build**, xem **`jpackage --version`** và đối chiếu **tài liệu man page đúng major version**. Không có một danh sách option duy nhất áp dụng cho mọi JDK, vendor và OS.

Trong bối cảnh lộ trình Java 14, cần phân biệt lịch sử với thực tế hiện nay. `jpackage` xuất hiện ở dạng incubating trong Java 14–15, nhưng trở thành công cụ JDK **chính thức từ Java 16 (JEP 392)**. Các ví dụ dưới đây áp dụng cách dùng **Java 17+ hiện hành**, không yêu cầu module incubator hoặc lệnh preview cũ.

## 2. Đừng đồng nhất các phiên bản khác nhau

Một máy build có thể chứa nhiều JDK. Bốn thông tin cần tách riêng:

| Khái niệm | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| Java launcher version | `java -version` | Phiên bản của lệnh `java` hiện được gọi |
| jpackage tool version | `jpackage --version` | Phiên bản công cụ đóng gói hiện được gọi |
| Target bytecode/API | `javac --release 17` | Ứng dụng nhắm tương thích Java 17 ở mức biên dịch |
| Runtime được đưa vào app image | Tự tạo qua `jlink` hoặc `--runtime-image` | Java runtime thật chạy cùng launcher sau đóng gói |

Ví dụ: code được biên dịch bằng `javac --release 17` nhưng đóng gói bằng `jpackage` JDK 24. `jpackage --version` in `24.0.2` trong khi class file vẫn nhắm Java 17. Đây **không phải mâu thuẫn**: công cụ build và bytecode target là hai thuộc tính khác nhau.

Nếu `java -version` là 17 nhưng `jpackage --version` là 24, có thể hệ thống đang lấy **hai executable từ hai thư mục JDK khác nhau**. Không đoán lỗi từ số phiên bản: xác định **đường dẫn thực tế** và JDK được cấu hình cho CI/IDE.

Nếu truyền một **`--runtime-image` có sẵn**, runtime bên trong app image lại là quyết định độc lập cần kiểm tra bằng metadata/runtime tests.

## 3. Xác định đúng executable trên máy build

### 3.1. Windows PowerShell

~~~powershell
Get-Command java
Get-Command javac
Get-Command jlink
Get-Command jpackage

(Get-Command java).Source
(Get-Command jpackage).Source

where.exe java
where.exe jpackage
~~~

`Get-Command` cho biết lệnh được PowerShell phân giải từ đâu. `where.exe` giúp tìm các đường dẫn khớp trong PATH. Viết rõ `where.exe` vì trong PowerShell, `where` có thể là alias `Where-Object`.

Môi trường Windows dùng để kiểm thử các ví dụ trong bài có `java.exe`, `jpackage.exe` và `jlink.exe` cùng nằm dưới JDK **Azul OpenJDK 24.0.2**. Đây là thông tin một **môi trường kiểm thử**, không phải giá trị mặc định của người học.

Khi cần dùng một JDK đã chọn, nên gọi executable của JDK đó bằng đường dẫn rõ ràng:

~~~powershell
$jdkBin = Join-Path $env:JAVA_HOME "bin"

& (Join-Path $jdkBin "java.exe") -version
& (Join-Path $jdkBin "jpackage.exe") --version
& (Join-Path $jdkBin "jpackage.exe") --help
~~~

Đoạn trên giả định `JAVA_HOME` đã trỏ tới **thư mục gốc của JDK phù hợp**. Nếu nó chưa được đặt, cần kiểm tra cấu hình IDE, Gradle/Maven hoặc CI; không nên tự kết luận PATH luôn đồng bộ với JAVA_HOME.

### 3.2. Linux / macOS

~~~bash
command -v java
command -v javac
command -v jlink
command -v jpackage

java -version
javac -version
jlink --version
jpackage --version
~~~

`command -v` là cách kiểm tra vị trí công cụ đang được shell gọi. Nếu có nhiều JDK, dùng đường dẫn tuyệt đối như `$JAVA_HOME/bin/jpackage` sau khi xác minh JAVA_HOME. Không phụ thuộc tùy tiện `readlink -f` trên macOS vì công cụ này không mặc nhiên có ở mọi bản macOS.

**Hãy chạy phép kiểm tra trong đúng CI job/runner tạo package.** JDK trên máy cá nhân có thể khác JDK của máy build, container hoặc service account.

## 4. Hai lệnh tra cứu quan trọng nhất

~~~bash
jpackage --version
jpackage --help
~~~

Theo tài liệu Java hiện hành:

- `--version`: in phiên bản sản phẩm của jpackage và kết thúc.
- `--help` hoặc `-h`: in **hướng dẫn, mô tả và danh sách tùy chọn hợp lệ cho nền tảng hiện tại**, rồi kết thúc.
- `--help` **không tạo app image**, không cần có JAR đầu vào và không đòi quyền cài đặt ứng dụng.

Ví dụ môi trường thử nghiệm trên Azul OpenJDK 24.0.2:

~~~text
24.0.2
~~~

Đây là kết quả **`jpackage --version`**, không phải một output cố định cho mọi JDK. JDK 17, 21, 25 và 26 sẽ in phiên bản tương ứng của chúng.

### Lọc nhanh tùy chọn trong PowerShell

~~~powershell
jpackage --help | Select-String -Pattern "--type|--main-jar|--module"
jpackage --help | Select-String -Pattern "--runtime-image|--jlink-options"
jpackage --help | Select-String -Pattern "--win-console|--win-dir-chooser"
~~~

`Select-String` chỉ lọc dòng hiển thị. Nó không tạo bản mô tả đầy đủ cho option và **không xác nhận option phù hợp với mọi loại package**. Sau khi thấy tên, đọc cả nhóm heading và đoạn mô tả của option trong help.

### Lọc nhanh trong bash

~~~bash
jpackage --help | grep -E -- '--type|--main-jar|--module'
jpackage --help | grep -E -- '--runtime-image|--jlink-options'
jpackage --help | grep -E -- '--linux|--mac|--win'
~~~

`grep` là lệnh shell giúp tìm văn bản; nó không phải option của jpackage. Trên Linux, một số option `--win-*` không xuất hiện, và đó là bình thường.

### Không nhầm help của các công cụ khác

~~~bash
java --help
jlink --help
jdeps --help
~~~

Ba lệnh trên mô tả **ba công cụ khác**. `java --help` không có nhiệm vụ giải thích `--main-jar` của jpackage; `jlink --help` giải thích các tùy chọn **tạo runtime**, không thay `jpackage --help`. Khi muốn truyền `--jlink-options`, hãy đọc **cả hai** help tương ứng.

## 5. Tài liệu online phải khớp major version

Đường dẫn chính thức cho một số bản JDK thường được sử dụng:

| jpackage đang chạy | Tài liệu Oracle phù hợp |
| --- | --- |
| JDK 17 | https://docs.oracle.com/en/java/javase/17/docs/specs/man/jpackage.html |
| JDK 21 | https://docs.oracle.com/en/java/javase/21/docs/specs/man/jpackage.html |
| JDK 24 | https://docs.oracle.com/en/java/javase/24/docs/specs/man/jpackage.html |
| JDK 25 | https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html |
| JDK 26 | https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html |

Nếu đang build bằng `jpackage 24.0.2`, nên **tra Java 24**. Không lấy option chỉ được mô tả trong tài liệu Java 26 làm bằng chứng rằng công cụ Java 24 chắc chắn hỗ trợ.

Tài liệu versioned giúp hiểu:

1. Option nào có sẵn và option nào đã thay đổi giữa releases.
2. **Giá trị** bắt buộc của option, ví dụ `--name NAME`, `--type TYPE`, `--dest PATH`.
3. Những giá trị có thể dùng nhiều lần, hoặc có cú pháp danh sách.
4. Cách xử lý **đường dẫn**, module-path và runtime image.
5. Option chỉ dùng cho **Windows, Linux hoặc macOS**.
6. Option dành cho **launcher, runtime image, application image hay installer**.
7. Giá trị **mặc định**, điều kiện tương thích và các option loại trừ lẫn nhau.
8. Native prerequisites: công cụ bổ sung nào cần có khi tạo MSI, DEB, RPM, DMG, PKG.

**Nguồn ưu tiên:** help của executable đang dùng → man page cùng major version → hướng dẫn Packaging Tool User's Guide của phiên bản tương ứng → release notes nếu nghi có thay đổi. Với JDK của vendor khác Oracle, kiểm tra cả ghi chú của vendor nếu có sự khác biệt.

Các bài hướng dẫn còn nói về `jdk.incubator.jpackage`/mô-đun ươm tạo của Java 14 thuộc bối cảnh **lịch sử**, không phải cách cấu hình mới trên Java 17+.

## 6. Phân nhóm jpackage options theo mục tiêu

Đọc help có cấu trúc hiệu quả hơn việc học thuộc toàn bộ tên cờ:

| Nhóm | Tùy chọn thường gặp | Mục đích |
| --- | --- | --- |
| Thông tin và chẩn đoán | `--help`, `--version`, `--verbose` | Khám phá/diagnostics |
| Đầu ra và metadata | `--type`, `--name`, `--dest`, `--app-version`, `--vendor`, `--icon` | Định dạng, tên, vị trí, metadata |
| App non-modular | `--input`, `--main-jar`, `--main-class` | Đóng gói JAR chạy bằng classpath |
| App modular | `--module-path`, `--module` | Đóng gói module và main class |
| Runtime tự tạo | `--add-modules`, `--jlink-options` | Điều khiển modules và jlink |
| Runtime có sẵn | `--runtime-image` | Chèn Java runtime image đã xây |
| Launcher | `--java-options`, `--arguments`, `--add-launcher` | JVM options, program args và launcher bổ sung |
| Image có sẵn/installer | `--app-image` và các cờ platform-specific | Tạo installer từ app image |
| Tài nguyên/điều tra | `--resource-dir`, `--temp` | Tùy biến resources hoặc giữ file tạm |
| Riêng từng hệ điều hành | `--win-*`, `--linux-*`, `--mac-*` | Hành vi launcher, gói cài đặt native |

Tên trong bảng là những nhóm **thường được hỗ trợ trên JDK hiện đại**; tập khả dụng cuối cùng là tập được **`jpackage --help` của JDK đó** xác nhận.

### Giá trị không phải tên option

Ví dụ:

~~~bash
jpackage --type app-image --name MyApp --dest dist
~~~

- `--type` là option; `app-image` là **giá trị** (application image).
- `--name` là option; `MyApp` là **giá trị** (tên app).
- `--dest` là option; `dist` là **giá trị** (thư mục đích).

Không viết `--app-image` thay `--type app-image`. Hai biểu thức này có **ngữ nghĩa khác nhau**: `--type app-image` yêu cầu tạo image, còn `--app-image` nhận **đường dẫn tới application image đã được tạo từ trước**.

## 7. Tập option và package types phụ thuộc OS

| Build trên OS | Loại đầu ra phù hợp | Ví dụ option nền tảng |
| --- | --- | --- |
| Windows | `app-image`, `exe`, `msi` | `--win-console`, `--win-dir-chooser`, các option `--win-*` khác |
| Linux | `app-image`, `deb`, `rpm` | Các option `--linux-*` liên quan installer/menu/shortcut |
| macOS | `app-image`, `dmg`, `pkg` | Các option `--mac-*` liên quan metadata/signing |

`--type app-image` tạo thư mục/bundle có thể chạy, **chưa phải installer**. Gói `.exe/.msi`, `.deb/.rpm` hay `.dmg/.pkg` cần định dạng phù hợp **đúng hệ điều hành**.

Tài liệu `jpackage` liệt kê nhiều giá trị `--type` trên cùng một trang, nhưng **không thể dựng gói Linux từ máy Windows chỉ bằng `--type deb`**. jpackage không hỗ trợ native cross-platform packaging; nên dùng runner của từng OS.

### Launcher-only và installer-only

Windows là ví dụ dễ hiểu:

- `--win-console`: tạo launcher có console để hiển thị stdout/stderr, phù hợp ứng dụng CLI và **app-image smoke test**.
- `--win-dir-chooser`: option về trải nghiệm **chọn thư mục cài đặt** khi tạo package Windows; không phải điều cần thêm vào mỗi lệnh `--type app-image`.

Tra nhóm **“Platform dependent option for creating the application launcher”** và **“Platform dependent options for creating the application package”** trong help để biết cờ thuộc lớp nào.

### Native prerequisites

Một option hợp lệ có thể vẫn **build thất bại** nếu thiếu công cụ OS: tool tạo Windows installers, công cụ DEB/RPM trên Linux, hoặc tool ký/signing trên macOS. Yêu cầu và phiên bản tool bổ sung có thể thay đổi theo JDK và hệ điều hành. Vì vậy:

1. Tra trang **Packaging Prerequisites** của đúng JDK.
2. Kiểm tra tool native trên build runner.
3. Tạo **`--type app-image`** trước để xác minh bản thân launcher hoạt động.
4. Sau đó mới tạo installer và kiểm tra cài/nhổ gói trên máy thử.

Không cố định một version WiX, RPM tool hoặc Xcode cho **mọi** JDK nếu chưa đọc tài liệu bản đang dùng.

## 8. Demo Java 17+ thực sự chạy được trên Windows

Ví dụ này đã được kiểm tra bằng **Azul OpenJDK 24.0.2 trên Windows**. Ta sẽ tạo một JAR, dùng `jpackage --help` để xác nhận tùy chọn `--win-console`, build app image rồi chạy launcher.

### 8.1. Mã Java hoàn chỉnh

Tạo file **`PackageCheck.java`**:

~~~java
public class PackageCheck {
    public static void main(String[] args) {
        System.out.println("PACKAGE_OK");
        System.out.println("arg-count=" + args.length);
    }
}
~~~

Chương trình chỉ có hai dòng stdout; không in ngày giờ, Java vendor hay đường dẫn nên kết quả dễ đối chiếu.

### 8.2. Kiểm tra các option có thật

Trong PowerShell:

~~~powershell
(Get-Command jpackage).Source
jpackage --version
jpackage --help | Select-String -Pattern "--type|--main-jar|--main-class|--win-console"
~~~

**Không** chạy tiếp nếu lệnh `jpackage` không tồn tại hoặc thực tế trỏ tới JDK không đúng mục tiêu. Cần giải quyết đường dẫn/toolchain trước.

### 8.3. Biên dịch và tạo JAR

Trong một thư mục thực hành mới có `PackageCheck.java`:

~~~powershell
mkdir input
mkdir classes
mkdir dist

javac --release 17 -encoding UTF-8 -d classes PackageCheck.java

jar --create --file input/demo.jar -C classes .
~~~

- `javac --release 17` kiểm tra code và sinh class nhắm Java 17.
- `jar --create ...` tạo file `input/demo.jar` từ `classes`.
- Không cần thêm `Main-Class` vào manifest vì ví dụ sẽ chỉ rõ `--main-class PackageCheck`.
- Nếu chạy lại lab, hãy chọn output folder sạch hoặc tên app khác; không tự ghi đè gói cũ mà chưa xác nhận.

### 8.4. Tạo application image

~~~powershell
jpackage --type app-image --name PackageCheck --input input --main-jar demo.jar --main-class PackageCheck --dest dist --win-console
~~~

Các thành phần:

| Option | Giá trị | Ý nghĩa |
| --- | --- | --- |
| `--type` | `app-image` | Tạo image, không tạo installer |
| `--name` | `PackageCheck` | Tên app và launcher |
| `--input` | `input` | Folder chứa JAR |
| `--main-jar` | `demo.jar` | Tên JAR trong input |
| `--main-class` | `PackageCheck` | Main class |
| `--dest` | `dist` | Thư mục output |
| `--win-console` | Không nhận giá trị | Launcher console của Windows |

Ở đây không có `--runtime-image`, nên `jpackage` tự dùng `jlink` tạo runtime phù hợp với quy tắc của JDK đang dùng.

### 8.5. Chạy app image và xem stdout

~~~powershell
.\dist\PackageCheck\PackageCheck.exe
~~~

**Đầu ra đã kiểm thử:**

~~~text
PACKAGE_OK
arg-count=0
~~~

Kiểm tra có metadata runtime:

~~~powershell
Test-Path .\dist\PackageCheck\runtime\release
~~~

Trên môi trường đã chạy thử:

~~~text
True
~~~

`True` cho thấy file `runtime/release` tồn tại. **Nó không thay thế** smoke test launcher, test modules, tài nguyên, native dependencies hoặc kiểm thử trên máy sạch.

### 8.6. Cùng ví dụ trên Linux/macOS

Bỏ cờ Windows:

~~~bash
jpackage --type app-image --name PackageCheck \
  --input input --main-jar demo.jar \
  --main-class PackageCheck --dest dist
~~~

Các đường dẫn launcher điển hình:

~~~bash
# Linux
./dist/PackageCheck/bin/PackageCheck

# macOS
./dist/PackageCheck.app/Contents/MacOS/PackageCheck
~~~

Đây là **mẫu bố cục nền tảng**, không phải kết quả đã chạy thử trên Linux/macOS trong bài. Layout chính xác có thể khác theo JDK/vendor; hãy xem thư mục xuất ra. `--win-console` không áp dụng cho hai hệ điều hành này.

## 9. Không nhầm --type app-image, --app-image và --runtime-image

Ba cách viết gần giống:

| Tùy chọn | Nhận dữ liệu nào? | Sử dụng khi nào? |
| --- | --- | --- |
| `--type app-image` | Giá trị `app-image` của option `--type` | Muốn tạo mới application image |
| `--app-image existing-image` | Thư mục app image đã có | Muốn làm gói cài đặt từ app image đó |
| `--runtime-image custom-runtime` | Thư mục Java runtime đã link | Muốn app image mới dùng runtime riêng |

`--runtime-image` **không nhận file `.jar`** hoặc `java.exe`; đó phải là thư mục runtime image hợp lệ. Khi đã cung cấp runtime, jpackage **không tự liên kết lại các modules bị thiếu**. Bạn phải chuẩn bị modules bằng `jlink` hoặc nguồn runtime phù hợp.

`--app-image` và `--runtime-image` là hai lựa chọn loại trừ nhau theo tài liệu jpackage. Nếu muốn một runtime riêng, hãy chọn nó **khi tạo app image**, rồi mới dùng image đó trong bước đóng installer nếu cần.

### Runtime do jpackage tự tạo

~~~bash
jpackage --type app-image --name MyApp \
  --input input --main-jar myapp.jar \
  --main-class com.example.Main
~~~

Không truyền `--runtime-image` nên jpackage tự tạo runtime qua jlink.

### Runtime cung cấp sẵn

~~~bash
jlink --add-modules java.base,java.logging --output custom-runtime

jpackage --type app-image --name MyApp \
  --input input --main-jar myapp.jar \
  --main-class com.example.Main \
  --runtime-image custom-runtime
~~~

Đây là **mảnh lệnh minh họa**, không phải build hoàn chỉnh cho mọi app. Đừng chỉ thêm `java.logging` theo thói quen; phải xác định modules ứng dụng thực sự cần. Có thể dùng `jdeps --print-module-deps` như một điểm xuất phát, nhưng vẫn phải kiểm thử reflection, JNI, ServiceLoader, provider modules và resources khi chạy thật.

## 10. Một khác biệt giữa các phiên bản: service bindings từ JDK 25

Đây là ví dụ thực tế cho thấy **cùng một lệnh không nhất thiết tạo cùng runtime khi nâng JDK**.

Theo Oracle Packaging Overview:

- **Trước JDK 25**, runtime do jpackage tự tạo có thể đưa **service bindings** vào theo mặc định.
- **Từ JDK 25 trở lên**, jpackage-generated runtime **không tự bổ sung service bindings** theo mặc định.
- Nếu ứng dụng dựa vào service provider modules được phát hiện động, cần kiểm tra tập modules và có thể truyền **`--bind-services`** cho `jlink` thông qua `--jlink-options`.

Ví dụ minh họa (trên JDK hỗ trợ option):

~~~bash
jpackage --type app-image --name MyApp \
  --input input --main-jar myapp.jar \
  --main-class com.example.Main \
  --jlink-options "--strip-native-commands --strip-debug --no-man-pages --no-header-files --bind-services"
~~~

Nếu đã tự cung cấp `--jlink-options`, cần chỉ định đầy đủ những jlink options muốn sử dụng; **đừng giả định mọi option mặc định vẫn được tự động cộng thêm**. Một số defaults thường thấy khi không truyền `--jlink-options` là `--strip-native-commands`, `--strip-debug`, `--no-man-pages` và `--no-header-files`.

**Không bật `--bind-services` một cách mù quáng:** nó có thể kéo thêm provider modules, làm runtime lớn hơn. Nên bật có mục đích và test những chức năng cần nhà cung cấp dịch vụ. Với app dùng custom runtime qua `--runtime-image`, dịch vụ/modules phải có sẵn trong image đó vì jpackage không bổ sung chúng khi copy.

Như vậy, ngoài việc kiểm tra **tên option**, người học còn phải kiểm tra **mặc định của chính phiên bản JDK**.

## 11. Modular và non-modular: đọc đúng nhánh tùy chọn

### 11.1. Ứng dụng chạy bằng classpath JAR

~~~bash
jpackage --type app-image --name Demo \
  --input input --main-jar demo.jar \
  --main-class com.example.Main
~~~

- `--input` chứa JAR/resources cần đóng gói.
- `--main-jar` chỉ tới JAR theo đường dẫn tương đối từ input.
- `--main-class` chỉ rõ Java main class.

### 11.2. Ứng dụng modular

~~~bash
jpackage --type app-image --name Demo \
  --module-path mods \
  --module com.example.demo/com.example.demo.Main
~~~

Lệnh thứ hai chỉ hợp lệ khi đã build **modular JAR/module** có descriptor và main class tương ứng. Không lấy một JAR non-modular rồi chỉ đổi `--main-jar` thành `--module`.

### 11.3. Các lựa chọn launcher

- `--java-options`: cấu hình JVM khi app được mở từ launcher.
- `--arguments`: cấu hình các tham số chương trình mặc định theo quy tắc launcher.
- `--add-launcher`: tạo một launcher bổ sung với cấu hình properties riêng.

Không nhúng token, mật khẩu hoặc tham số chứa dữ liệu cá nhân vào file launcher hoặc command line chỉ để debug. Dữ liệu này có thể bị ghi vào artifact, log hoặc công cụ kiểm tra process. Dùng cơ chế cung cấp secrets thích hợp tại thời điểm chạy.

## 12. Phân loại lỗi theo công cụ trước khi sửa

| Triệu chứng | Nguyên nhân khả dĩ | Hành động phù hợp |
| --- | --- | --- |
| Lệnh `jpackage` không tìm thấy | PATH/JDK thiếu executable đúng | Xác nhận full JDK và đường dẫn, không thêm flag ngẫu nhiên |
| `jpackage --version` không khớp mong đợi | Đang lấy tool của JDK khác | So `Get-Command`/`command -v` với JDK được cấu hình |
| “Unrecognized option” | Flag không có ở JDK/OS này, gõ sai hoặc copy từ JDK mới | Đọc help và man page cùng version |
| “Invalid package type” | `--type` không phù hợp OS | Dùng `app-image` hoặc installer đúng nền tảng |
| `--win-console` bị từ chối | Lệnh chạy trên Linux/macOS hoặc version khác | Bỏ cờ Windows, đọc platform-dependent help |
| `--win-dir-chooser` không có tác dụng | Đang build app image chứ không phải installer | Chọn đúng package type và xem nhóm installer options |
| “Main class not found” | Sai `--main-jar`, `--main-class` hoặc file input | Kiểm tra `jar --list --file input/demo.jar` |
| Build app image được nhưng launcher lỗi | Thiếu module/runtime/API/native libraries | Kiểm tra runtime modules và chạy smoke test |
| Installer thất bại nhưng app image chạy | Thiếu native packaging prerequisites | Kiểm tra toolchain Windows/Linux/macOS theo version |
| `UnsupportedClassVersionError` | Bytecode mới hơn runtime đóng gói | Chọn runtime đủ mới hoặc compile bằng `--release` thích hợp |
| Sau nâng JDK thiếu service provider | Thay đổi service bindings hoặc module graph | Kiểm tra `--bind-services` và providers cần thiết |
| Lệnh nhiều dòng lỗi trên PowerShell | Copy dấu `\` nối dòng của bash | Viết một dòng hoặc dùng cú pháp nối dòng PowerShell đúng |
| `--verbose` in đường dẫn/cấu hình | Log có metadata môi trường | Bảo vệ quyền đọc và retention của build logs |
| App image đầu ra trùng tên cũ | Thư mục output không sạch | Tạo dest mới hoặc quản lý artifact cũ an toàn |

Nếu một option không được nhận diện, **đừng thay thế bằng một tên gần giống** chỉ vì giúp lệnh đi tiếp. Hãy xác minh nguồn tài liệu và cú pháp.

### Kiểm tra JAR và modules

~~~bash
jar --list --file input/demo.jar
jdeps --print-module-deps input/demo.jar
~~~

Lệnh thứ nhất liệt kê file trong JAR, giúp đối chiếu tên class. Lệnh thứ hai phân tích dependencies tĩnh, **không đảm bảo phát hiện đầy đủ reflection, dynamic loading, native libraries, service providers**. JDK package là công cụ đóng gói; nó không thay kiểm thử tích hợp.

## 13. Ghi nhận phiên bản và tùy chọn trong CI/CD

Một job CI/CD nên ghi nhận:

| Thông tin | Tại sao cần? |
| --- | --- |
| JDK vendor, version, patch/build | Tái lập công cụ |
| Đường dẫn đến `java`, `jpackage` và `jlink` | Tránh PATH trộn JDK |
| OS và kiến trúc | Native packaging phụ thuộc nền tảng |
| `jpackage --version` | Định danh tool thật được gọi |
| Full command và options | Tái hiện lỗi |
| Package type và launcher artifacts | Phân biệt image/installer |
| Runtime modules/version trong image | Phát hiện thiếu module/providers |
| Phiên bản native packaging prerequisites | Giải thích lỗi toolchain |
| Kết quả launcher smoke/integration tests | Chứng minh bản build thực chạy |

### PowerShell: log các thông tin tối thiểu

~~~powershell
Write-Output "JDK tool paths:"
(Get-Command java).Source
(Get-Command jpackage).Source

java -version
javac -version
jlink --version
jpackage --version

jpackage --help | Select-String -Pattern "--type|--runtime-image|--win-console"
~~~

Đây là lệnh **chẩn đoán không tạo package**. `java -version` có thể ghi thông tin vào stderr; cách CI hiển thị dòng stderr tùy shell.

### Bash: cùng ý tưởng

~~~bash
command -v java
command -v jpackage
java -version
javac -version
jlink --version
jpackage --version
jpackage --help | grep -E -- '--type|--runtime-image|--module'
~~~

Khi build bị lỗi, cần lưu phiên bản tool **trong chính job thất bại**, không sử dụng kết quả chạy thủ công ở một máy khác làm bằng chứng.

**Chú ý bảo mật:** `--verbose` và log đầy đủ có thể chứa đường dẫn, thông tin môi trường hoặc các giá trị bạn truyền trong command line. Không nhúng secrets trong options; giới hạn quyền xem log, artifact và thư mục tạm. Tùy chọn `--temp` của jpackage nếu được cung cấp có thể giữ các file tạm sau khi build, cần xử lý theo chính sách retention.

## 14. Quy trình chọn tùy chọn trước khi phát hành

1. **Định nghĩa output:** cần app image để test hay native installer để cài đặt?
2. **Xác định máy build:** OS, kiến trúc, native prerequisites và JDK vendor/version.
3. **Tra cứu tại nguồn:** chạy `jpackage --version`, `--help`.
4. **Đối chiếu online:** mở man page **đúng JDK major version**.
5. **Kiểm tra đầu vào:** JAR/module, main class, dependency, icon/resources.
6. **Quyết định runtime:** để jpackage tự link hay dùng `--runtime-image`?
7. **Kiểm soát các option jlink:** đọc `jlink --help`, xác định module graph và service bindings nếu có.
8. **Build app image trước:** `--type app-image` giúp kiểm tra launcher không phụ thuộc installer native.
9. **Chạy launcher trên môi trường sạch** cùng OS/architecture, xác nhận tính năng thực tế.
10. **Tạo installer sau:** chọn loại native và các option nền tảng đúng version.
11. **Kiểm tra cài đặt/gỡ cài đặt**, quyền, shortcut/menu và yêu cầu signing.
12. **Lưu build metadata**, runtime version và một kết quả test có thể tái hiện.

Đặt mục tiêu xây gói có thể chạy, bảo mật, update được và dùng đúng module; không chạy theo việc đưa nhiều flags nhất có thể.

## 15. Bài tập có đáp án gợi ý

### Bài 1 — Nên tra lệnh nào?

Bốn lệnh:

~~~bash
java -version
jpackage --version
jpackage --help
jlink --help
~~~

**Đáp án:** `java -version` cho biết Java launcher; `jpackage --version` cho biết jpackage tool; `jpackage --help` nêu các tùy chọn của chính phiên bản/nền tảng; `jlink --help` tra options xây runtime khi cần dùng `--jlink-options`.

### Bài 2 — Hai JDK trong PATH

`java -version` in 17 nhưng `jpackage --version` in 24.0.2. Có thể tiếp tục đóng gói không?

**Đáp án:** phải xác nhận rõ toolchain. Kiểm tra đường dẫn thực của từng executable và target Java/runtime mong muốn. Build có thể hợp lệ nếu chủ động dùng JDK 24 để đóng gói code Java 17, nhưng không nên để sự khác biệt này xảy ra vô tình.

### Bài 3 — Copy option Windows sang Linux

Lệnh chứa `--win-console` chạy được trên Windows, nhưng lỗi trên Ubuntu.

**Đáp án:** option dành cho Windows launcher; bỏ khỏi lệnh Linux, kiểm tra `jpackage --help` trên runner Linux và đường dẫn launcher phù hợp.

### Bài 4 — Vì sao không có MSI?

Build `jpackage --type app-image ...` tạo ra folder `dist/MyApp`. Người dùng mong file `.msi`.

**Đáp án:** `app-image` không phải installer. Muốn MSI trên Windows, phải chọn `--type msi`, đáp ứng prerequisites và test installer.

### Bài 5 — Truyền JAR vào runtime-image

Lệnh dùng `--runtime-image input/demo.jar`.

**Đáp án:** sai vì đây là đường dẫn JAR, trong khi `--runtime-image` yêu cầu **thư mục runtime image** đã xây. JAR thuộc `--input`/`--main-jar`.

### Bài 6 — Nâng từ JDK 21 lên JDK 26

Runtime đóng gói mới thiếu một service provider mà app tìm bằng `ServiceLoader`.

**Đáp án:** tra sự khác biệt service bindings từ JDK 25, kiểm tra danh sách modules, cân nhắc `--bind-services` hoặc provider modules cụ thể theo tài liệu jlink cùng version, sau đó kiểm thử image.

### Bài 7 — Xác nhận kết quả chạy thật

Chạy bản `PackageCheck` ở mục 8. Vì sao stdout là:

~~~text
PACKAGE_OK
arg-count=0
~~~

**Đáp án:** mã Java cố định hai dòng, launcher không truyền program argument, nên args length bằng 0. `jpackage --version` là thông tin riêng của công cụ build, không phải output ứng dụng.

### Bài 8 — Đọc sai tài liệu

Máy đang dùng `jpackage 17.0.x` nhưng ví dụ từ man page `Java 26` có thêm một option.

**Đáp án:** không giả định option khả dụng ở 17. Chạy help của jpackage 17, đọc trang JDK 17 và chỉ dùng option hỗ trợ. Nếu tính năng yêu cầu JDK mới, hãy nâng công cụ theo quy trình kiểm thử và phân phối.

## 16. Tài liệu chính thức còn áp dụng

- [Oracle JDK 26 — The jpackage Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jpackage.html): danh sách option, help/version, runtime, app image, launcher và platform-dependent options.
- [Oracle JDK 25 — The jpackage Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jpackage.html): tham chiếu cho phiên bản 25.
- [Oracle JDK 24 — The jpackage Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jpackage.html): đối chiếu với JDK 24 được dùng trong bài kiểm thử.
- [Oracle JDK 21 — The jpackage Command](https://docs.oracle.com/en/java/javase/21/docs/specs/man/jpackage.html): đối chiếu JDK 21.
- [Oracle JDK 17 — The jpackage Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jpackage.html): phiên bản phù hợp Java 17+.
- [Oracle JDK 25 — Packaging Overview](https://docs.oracle.com/en/java/javase/25/jpackage/packaging-overview.html): native prerequisites, cách tạo app image và service bindings từ JDK 25.
- [Oracle JDK 26 — The jlink Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jlink.html): những lựa chọn có thể dùng khi tạo runtime.
- [Oracle JDK 26 — The jdeps Command](https://docs.oracle.com/en/java/javase/26/docs/specs/man/jdeps.html): phân tích phụ thuộc module.
- [OpenJDK JEP 392 — Packaging Tool](https://openjdk.org/jeps/392): jpackage thành công cụ JDK chính thức từ Java 16.
