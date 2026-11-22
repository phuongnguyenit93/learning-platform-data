# Build gói theo nền tảng đích và kiểm thử trên máy sạch

Một file JAR chứa bytecode Java thường có thể chạy trên nhiều hệ điều hành nếu máy đích có runtime tương thích. Nhưng khi phân phối ứng dụng cho người dùng cuối, chỉ gửi JAR có thể chưa đủ: người dùng cần cài Java, tự cấu hình classpath, tạo shortcut và tìm cách khởi chạy. Ứng dụng cũng có thể phụ thuộc thư viện native, cấu hình hệ điều hành hoặc tài nguyên riêng cho Windows, macOS hay Linux.

Java 17 cung cấp công cụ **jpackage** để tạo application image và gói cài đặt native theo nền tảng đích. Công cụ này có thể đóng gói ứng dụng cùng runtime Java để người dùng không cần cài JDK riêng. Với ứng dụng modular, **jlink** có thể tạo runtime image tùy chỉnh chỉ gồm các module cần thiết; jpackage sau đó dùng runtime image đó khi tạo gói.

Một quy trình phát hành đáng tin cậy cần:

1. Xác định hệ điều hành, kiến trúc CPU và runtime mục tiêu.
2. Build artifact bằng JDK và dependency phù hợp với nền tảng đó.
3. Tạo application image để kiểm tra trước.
4. Tạo installer native cho nền tảng đích.
5. Cài đặt và chạy thử trên máy sạch không có môi trường phát triển.
6. Kiểm tra nâng cấp, gỡ cài đặt, quyền truy cập và các phụ thuộc native.

## 1. JAR portable và gói cài đặt theo nền tảng khác nhau thế nào?

JAR là archive chứa class, resource và metadata. Nếu ứng dụng chỉ dùng Java API chuẩn và các thư viện thuần Java, cùng một JAR thường có thể chạy trên nhiều hệ điều hành với một Java runtime tương thích.

Gói cài đặt native lại phụ thuộc nền tảng:

| Artifact | Mục tiêu | Phụ thuộc nền tảng |
| --- | --- | --- |
| JAR thuần Java | Chạy bằng Java launcher | Cần runtime tương thích; nội dung JAR thường dùng chung |
| Application image | Thư mục ứng dụng có launcher và runtime | Runtime và launcher gắn với OS/CPU đích |
| Windows installer | Cài ứng dụng trên Windows | Định dạng cài đặt và công cụ build dành cho Windows |
| macOS package/image | Cài hoặc phân phối ứng dụng trên macOS | Bundle, package, signing và quy tắc của macOS |
| Linux package | Cài trên distro Linux tương ứng | Định dạng package và môi trường hệ thống đích |

Một JAR thuần Java có thể portable, nhưng không có nghĩa mọi ứng dụng Java đều portable. Các yếu tố sau có thể làm ứng dụng phụ thuộc nền tảng:

- JNI hoặc thư viện native như DLL, dylib, SO.
- Chương trình ngoài được gọi qua ProcessBuilder.
- Đường dẫn file, dấu phân cách, quyền thực thi và quy tắc filesystem.
- Font, codec, driver, thư viện đồ họa hoặc hệ thống in.
- Hành vi theo hệ điều hành như service, registry, file association hoặc keychain.
- Kiến trúc CPU và ABI của thư viện native.

Do đó, cần phân biệt **tính portable của bytecode** với **tính portable của toàn bộ sản phẩm đã triển khai**.

### 1.1. Xác định ma trận nền tảng đích

Trước khi build, hãy xác định rõ những tổ hợp mà sản phẩm hỗ trợ. Ví dụ:

| Nền tảng | Kiến trúc | Gói cần phát hành |
| --- | --- | --- |
| Windows 11 | x64 | MSI hoặc EXE |
| macOS | Apple silicon arm64 | PKG hoặc DMG |
| Linux Ubuntu/Debian | x64 | DEB |
| Linux Fedora/RHEL | x64 | RPM |

Đây chỉ là ví dụ. Sản phẩm thực tế có thể hỗ trợ ít hoặc nhiều tổ hợp hơn. Không nên ghi “hỗ trợ Linux” nếu chỉ mới thử trên một distro và một kiến trúc.

### 1.2. Java version và nền tảng là hai điều kiện riêng

Nếu ứng dụng được biên dịch với Java 17, bytecode có thể chạy trên Java 17 hoặc runtime mới hơn tương thích, nhưng không chạy trên runtime cũ hơn nếu sử dụng bytecode/API không được hỗ trợ.

Ví dụ:

```bash
javac --release 17 -d out src/com/example/app/Main.java
```

Tùy chọn --release 17 đặt mức ngôn ngữ, bytecode và Java API mục tiêu cho quá trình biên dịch. Nó **không** biến một runtime image Windows thành runtime image Linux, và cũng không đóng gói thư viện native cho mọi kiến trúc.

## 2. jpackage trong JDK 17

jpackage là công cụ đóng gói ứng dụng Java thành application image hoặc installer native. Công cụ đã trở thành tính năng chính thức từ JDK 16, vì vậy có sẵn trong JDK 17.

Các loại gói phổ biến phụ thuộc hệ điều hành:

| Hệ điều hành build | Loại gói thường hỗ trợ |
| --- | --- |
| Windows | app-image, exe, msi |
| macOS | app-image, dmg, pkg |
| Linux | app-image, deb, rpm |

Danh sách chính xác phụ thuộc bản JDK và công cụ đóng gói được cài trên máy. Kiểm tra trực tiếp:

```bash
jpackage --version
jpackage --help
jpackage --help-extra
```

app-image là thư mục ứng dụng đã đóng gói, thường có launcher và runtime. Các định dạng msi, exe, dmg, pkg, deb, rpm tạo installer hoặc package native tương ứng.

### 2.1. Build trên nền tảng đích

jpackage tạo gói native cho nền tảng đang chạy công cụ. Không nên coi nó là công cụ cross-compiler có thể tạo installer Windows từ Linux hoặc installer macOS từ Windows.

Một pipeline phát hành nên chạy trên runner phù hợp:

```text
Windows x64 runner  ──> Windows app-image / MSI / EXE
macOS arm64 runner  ──> macOS app-image / PKG / DMG
Linux x64 runner    ──> Linux app-image / DEB / RPM
```

Runtime image cũng gắn với hệ điều hành và kiến trúc mà JDK tạo ra nó. Muốn phát hành cho Windows, macOS hoặc Linux, hãy tạo runtime/package trên nền tảng tương ứng và kiểm thử trên tổ hợp đích.

### 2.2. Cần chuẩn bị gì?

Trước khi chạy jpackage, cần có:

- JDK 17 đúng nền tảng và kiến trúc mục tiêu.
- JAR ứng dụng đã build.
- Thư mục chứa dependency nếu ứng dụng cần các JAR bên ngoài.
- Tên ứng dụng, phiên bản, vendor và metadata cần thiết.
- Icon hoặc resource theo nền tảng nếu muốn tùy biến.
- Công cụ hệ thống mà định dạng installer yêu cầu.

Một số loại installer cần công cụ đóng gói native bổ sung. Ví dụ, tạo MSI/EXE trên Windows cần bộ công cụ WiX tương thích; các định dạng macOS và Linux cũng dựa vào công cụ hệ thống tương ứng. Xem jpackage --help và tài liệu JDK 17 trên máy build để xác định yêu cầu cụ thể.

## 3. Chuẩn bị input cho jpackage

Giả sử ứng dụng không modular có cấu trúc:

```text
release/
├── input/
│   ├── desktop-app.jar
│   ├── logging.jar
│   └── database-driver.jar
└── output/
```

Thư mục input chứa JAR chính và các dependency cần thiết. jpackage dùng thư mục này làm nguồn nội dung ứng dụng.

Nếu JAR chính đã có Main-Class trong manifest, có thể chỉ định JAR đó làm entry point. Nếu không, dùng --main-class để cung cấp tên lớp đầy đủ.

Ví dụ lớp khởi chạy:

```java
package com.example.desktop;

public class Main {
    public static void main(String[] args) {
        System.out.println("Desktop application started");
    }
}
```

Tên lớp đầy đủ là com.example.desktop.Main.

## 4. Tạo application image trước khi tạo installer

Nên tạo app-image trước để kiểm tra nội dung triển khai:

```bash
jpackage --type app-image --name DesktopApp --app-version 1.0.0 --vendor ExampleOrg --input input --main-jar desktop-app.jar --main-class com.example.desktop.Main --dest output
```

Các tùy chọn:

| Tùy chọn | Mục đích |
| --- | --- |
| --type app-image | Tạo application image thay vì installer. |
| --name DesktopApp | Tên ứng dụng và tên image. |
| --app-version 1.0.0 | Phiên bản ứng dụng. |
| --vendor ExampleOrg | Thông tin nhà cung cấp. |
| --input input | Thư mục chứa JAR chính và dependency. |
| --main-jar desktop-app.jar | JAR chính của ứng dụng. |
| --main-class ... | Lớp có phương thức main. |
| --dest output | Thư mục chứa artifact đầu ra. |

Nếu JAR chính đã có Main-Class trong manifest, có thể bỏ --main-class; chỉ định tường minh giúp command dễ đọc và giảm phụ thuộc vào metadata được tạo ở bước khác.

### 4.1. Chạy thử application image

jpackage tạo thư mục image trong output. Cấu trúc chi tiết tùy hệ điều hành; bên trong thường có launcher, thư mục ứng dụng và runtime image.

Chạy launcher do jpackage tạo:

- Trên Windows, chạy file launcher EXE trong application image.
- Trên macOS, mở launcher hoặc ứng dụng APP.
- Trên Linux, chạy launcher trong thư mục image.

Không nên chỉ kiểm tra bằng java -jar desktop-app.jar. Mục tiêu ở bước này là xác nhận launcher, runtime đi kèm, resource và dependency trong application image đều hoạt động.

### 4.2. Dependency phải nằm trong input

Nếu desktop-app.jar phụ thuộc logging.jar và database-driver.jar, các file đó cần nằm trong thư mục input hoặc được cung cấp theo cấu hình đóng gói khác. jpackage không tự phân tích Maven/Gradle dependency graph để tải tất cả thư viện ngoài.

Với ứng dụng dùng manifest Class-Path, kiểm tra các đường dẫn tương đối có còn đúng sau khi đóng gói. Với ứng dụng dùng classpath riêng hoặc framework có launcher đặc biệt, làm theo cấu trúc artifact mà framework hỗ trợ.

## 5. Tạo installer native theo hệ điều hành

Sau khi application image hoạt động, có thể tạo installer trên runner của nền tảng đích.

### 5.1. Windows: MSI hoặc EXE

Ví dụ tạo MSI:

```powershell
jpackage --type msi --name DesktopApp --app-version 1.0.0 --vendor ExampleOrg --input input --main-jar desktop-app.jar --main-class com.example.desktop.Main --dest output --win-menu --win-shortcut
```

--win-menu tạo shortcut trong Start Menu; --win-shortcut yêu cầu shortcut trên desktop theo tùy chọn của công cụ. Có thể dùng --icon để chỉ định icon Windows phù hợp.

Tạo EXE bằng cách đổi loại gói:

```powershell
jpackage --type exe --name DesktopApp --input input --main-jar desktop-app.jar --main-class com.example.desktop.Main --dest output
```

MSI và EXE là hai định dạng installer khác nhau. Chọn định dạng theo cách tổ chức triển khai và công cụ quản lý phần mềm của môi trường đích.

### 5.2. macOS: DMG hoặc PKG

Ví dụ tạo DMG:

```bash
jpackage --type dmg --name DesktopApp --app-version 1.0.0 --vendor ExampleOrg --input input --main-jar desktop-app.jar --main-class com.example.desktop.Main --dest output
```

Có thể tạo PKG:

```bash
jpackage --type pkg --name DesktopApp --input input --main-jar desktop-app.jar --main-class com.example.desktop.Main --dest output
```

DMG thường được dùng làm image phân phối ứng dụng; PKG là installer package. Việc phân phối bên ngoài môi trường phát triển cần xem xét signing, notarization và chính sách Gatekeeper hiện hành của Apple.

### 5.3. Linux: DEB hoặc RPM

Ví dụ tạo DEB:

```bash
jpackage --type deb --name desktop-app --app-version 1.0.0 --vendor ExampleOrg --input input --main-jar desktop-app.jar --main-class com.example.desktop.Main --dest output
```

Ví dụ tạo RPM:

```bash
jpackage --type rpm --name desktop-app --input input --main-jar desktop-app.jar --main-class com.example.desktop.Main --dest output
```

DEB và RPM phù hợp với các họ distro khác nhau. Một gói DEB tạo trên một bản Linux không tự động được bảo đảm chạy trên mọi bản Debian/Ubuntu hoặc mọi phiên bản distro; cần xác định baseline và kiểm tra các thư viện hệ thống mà ứng dụng hoặc native dependency yêu cầu.

### 5.4. Tên gói và tên ứng dụng

Một số hệ điều hành phân biệt tên hiển thị với tên package. Ví dụ Linux package name thường cần tuân theo quy tắc đặt tên package của distro; macOS có bundle identifier riêng. Sử dụng các tùy chọn platform-specific trong jpackage --help khi cần khai báo thông tin này.

Không nên dùng một tên có ký tự không hợp lệ cho mọi hệ điều hành rồi giả định installer sẽ tự chuyển đổi giống nhau.

## 6. Tạo runtime image tối giản bằng jlink

Thông thường jpackage có thể tạo runtime image cho ứng dụng. Nếu muốn kiểm soát module runtime rõ hơn, có thể tạo trước bằng jlink, sau đó truyền image đó cho jpackage qua --runtime-image.

jlink ghép các module và dependency module thành một runtime image. Nó phù hợp nhất với ứng dụng modular, trong đó module descriptor khai báo dependency bằng requires.

Ví dụ module ứng dụng:

```java
module com.example.desktop {
    requires java.desktop;
}
```

Biên dịch module vào mods:

```bash
javac -d mods --module-source-path src -m com.example.desktop
```

Tạo runtime image:

```bash
jlink --module-path "$JAVA_HOME/jmods:mods" --add-modules com.example.desktop --output runtime-image --strip-debug --no-header-files --no-man-pages
```

Trong ví dụ, --add-modules chọn module gốc; các dependency module cần thiết được đưa vào graph theo quan hệ module. --strip-debug, --no-header-files và --no-man-pages có thể giảm kích thước image nếu ứng dụng không cần những thành phần đó.

Đường dẫn module path cần được điều chỉnh theo hệ điều hành và shell. Trên Windows, dấu phân cách module path là dấu chấm phẩy; trên Linux/macOS là dấu hai chấm.

### 6.1. Đóng gói với runtime image đã tạo

Sau khi có runtime image cho đúng nền tảng:

```bash
jpackage --type app-image --name DesktopApp --input input --main-jar desktop-app.jar --main-class com.example.desktop.Main --runtime-image runtime-image --dest output
```

--runtime-image chỉ định runtime image sẽ được đưa vào ứng dụng. Image phải phù hợp với hệ điều hành/kiến trúc đích và tương thích với ứng dụng.

### 6.2. Vì sao cần kiểm tra module runtime?

Nếu runtime image thiếu module mà ứng dụng hoặc dependency cần, ứng dụng có thể lỗi khi khởi chạy hoặc khi đi vào một chức năng cụ thể.

Đối với ứng dụng modular, kiểm tra module graph bằng công cụ JDK và thử các luồng nghiệp vụ thật. Không nên chỉ mở màn hình chính rồi kết luận runtime image đã đủ module; các chức năng ít dùng như in, TLS, logging, XML hoặc desktop integration có thể chỉ được gọi sau đó.

Ứng dụng classpath không có module descriptor cần chiến lược xác định module runtime cẩn thận hơn. Có thể dùng jdeps để phân tích dependency tĩnh, nhưng phải bổ sung module được nạp động, reflection, service loader và native integration mà phân tích tĩnh có thể không suy ra đầy đủ.

## 7. Dependency native và kiến trúc CPU

Nếu ứng dụng dùng JNI hoặc thư viện native, mỗi binary phải tương thích với:

- Hệ điều hành đích.
- Kiến trúc CPU (x64, arm64, ...).
- ABI và phiên bản runtime hệ thống cần thiết.
- Phiên bản thư viện native mà ứng dụng liên kết.

Ví dụ:

```text
native/
├── windows-x64/
│   └── engine.dll
├── macos-arm64/
│   └── libengine.dylib
└── linux-x64/
    └── libengine.so
```

Không thể đóng một file DLL vào gói macOS rồi kỳ vọng JVM tự chuyển đổi nó thành dylib. Cần build hoặc lấy đúng binary native cho từng nền tảng và đặt vào vị trí mà ứng dụng có thể nạp.

### 7.1. Kiểm tra native library loading

Nếu dùng System.loadLibrary, kiểm tra:

- Tên thư viện theo quy ước của JVM/OS.
- java.library.path hoặc cách ứng dụng xác định vị trí thư viện.
- Quyền đọc và thực thi phù hợp.
- Kiến trúc binary trùng kiến trúc tiến trình JVM.
- Các thư viện native phụ thuộc đã có trên máy đích.

Lỗi UnsatisfiedLinkError thường là dấu hiệu thư viện không tìm thấy, không tương thích hoặc thiếu dependency native.

### 7.2. Không trộn artifact x64 và arm64

Một runtime image x64 không trở thành arm64 chỉ vì được copy sang máy ARM. Nếu cần hỗ trợ cả hai kiến trúc, hãy build runtime image và gói native tương ứng trên runner phù hợp, sau đó test từng gói trên phần cứng hoặc môi trường ảo hóa tương thích.

### 7.3. Linux và baseline thư viện hệ thống

Native binary Linux có thể phụ thuộc phiên bản glibc hoặc thư viện hệ thống cụ thể. Một gói build trên distro mới có thể không chạy trên distro cũ hơn nếu cần symbol hoặc ABI mới.

Chọn distro/build image làm baseline theo chính sách hỗ trợ của sản phẩm. Kiểm tra dependency native bằng công cụ phù hợp của nền tảng và thử trên distro sạch thuộc baseline, không chỉ trên máy build.

## 8. Kiểm thử trên máy sạch nghĩa là gì?

Máy sạch là môi trường kiểm thử tách biệt, không kế thừa những thứ vô tình có trên máy phát triển. Ví dụ:

- Máy ảo mới cài hệ điều hành mục tiêu.
- Máy vật lý/runner mới được provision từ image chuẩn.
- Container sạch cho các kiểm tra phù hợp với Linux và không cần installer desktop.

Với installer native, máy ảo của đúng hệ điều hành thường là lựa chọn phù hợp hơn container vì có thể kiểm tra installer, shortcut, quyền người dùng, registry, service, desktop integration và uninstall.

### 8.1. Những gì không nên có sẵn trên máy sạch

Để kiểm tra sản phẩm thực sự tự chứa đúng như thiết kế, môi trường cần tránh:

- JDK hoặc JRE được cài sẵn nếu gói tuyên bố mang theo runtime.
- CLASSPATH hoặc JAVA_HOME được thiết lập từ trước.
- Dependency JAR nằm ngoài thư mục cài đặt mà ứng dụng vô tình đang dùng.
- Native library chỉ có trên máy phát triển.
- File cấu hình, cache hoặc dữ liệu mẫu được copy thủ công từ máy build.
- Quyền administrator/root được dùng khi ứng dụng dự kiến chạy bằng user thông thường.

Nếu sản phẩm chủ đích yêu cầu người dùng cài Java riêng, hãy ghi rõ phiên bản runtime tối thiểu và test đúng điều kiện đó. Không gọi đó là gói tự chứa runtime.

### 8.2. Máy sạch giúp phát hiện lỗi nào?

Một máy phát triển thường đã có nhiều cấu hình và thư viện hỗ trợ. Máy sạch giúp phát hiện:

- Thiếu JAR dependency hoặc resource.
- Launcher phụ thuộc vào PATH, JAVA_HOME hoặc thư mục làm việc.
- Thiếu runtime module trong image.
- Sai quyền file hoặc vị trí cài đặt.
- Đường dẫn có dấu cách hoặc ký tự Unicode.
- Native library sai OS/architecture.
- Installer không tạo shortcut hoặc không gỡ sạch.
- Ứng dụng ghi dữ liệu vào thư mục cài đặt không có quyền ghi.
- TLS, proxy, font, locale hoặc timezone khác môi trường phát triển.

## 9. Quy trình kiểm thử installer trên máy sạch

Nên dùng snapshot máy ảo hoặc image có thể tái tạo để mỗi lần kiểm thử bắt đầu từ trạng thái tương đương.

### Bước 1 — Ghi lại thông tin môi trường

Ghi nhận:

- OS và phiên bản cụ thể.
- Kiến trúc CPU.
- Tài khoản đang cài và tài khoản chạy ứng dụng.
- Runtime Java có sẵn hay không.
- Ngôn ngữ, locale, timezone.
- Dung lượng đĩa và quyền truy cập.

Thông tin này giúp tái hiện lỗi và xác định phạm vi hỗ trợ.

### Bước 2 — Cài đặt đúng artifact phát hành

Copy đúng installer được tạo bởi pipeline. Không copy thư mục build/classes, JAR phụ hoặc file cấu hình từ máy phát triển vào máy thử nghiệm nếu chúng không thuộc gói phát hành.

Thực hiện cài đặt theo hướng dẫn dành cho người dùng cuối. Nếu installer cần quyền administrator/root, xác nhận yêu cầu đó và sau cài đặt thử chạy ứng dụng bằng tài khoản thường.

### Bước 3 — Xác nhận runtime đi kèm

Nếu gói tuyên bố bao gồm runtime, thử trên máy không cài Java:

- Không thiết lập JAVA_HOME.
- Không thêm Java vào PATH.
- Chạy launcher được cài đặt.
- Xác nhận ứng dụng khởi động và ghi nhận runtime/version theo cách phù hợp.

Nếu chỉ phân phối JAR, cài đúng Java runtime được hỗ trợ rồi chạy java -jar. Hai mô hình triển khai cần được ghi rõ trong tài liệu người dùng.

### Bước 4 — Kiểm tra luồng sử dụng chính

Không chỉ kiểm tra cửa sổ hoặc dòng chữ khởi động. Chạy các luồng quan trọng:

- Đọc và ghi dữ liệu.
- Tải/cập nhật cấu hình.
- Kết nối dịch vụ ngoài hoặc database nếu có.
- Xử lý file đầu vào/đầu ra.
- Tạo log và báo lỗi.
- Các chức năng sử dụng native library hoặc module tùy chọn.

### Bước 5 — Kiểm tra đường dẫn và quyền

Thử cài vào đường dẫn có khoảng trắng và ký tự Unicode nếu nền tảng cho phép. Kiểm tra:

- Ứng dụng khởi động từ shortcut và từ launcher trực tiếp.
- Không phụ thuộc current working directory.
- Dữ liệu người dùng được ghi vào thư mục dữ liệu phù hợp.
- Ứng dụng không cố ghi vào thư mục cài đặt nếu user không có quyền.
- Đường dẫn file và thư mục được xử lý theo API đa nền tảng.

### Bước 6 — Kiểm tra nâng cấp và gỡ cài đặt

Thực hiện các trường hợp:

1. Cài bản đầu tiên.
2. Khởi chạy và tạo dữ liệu người dùng.
3. Cài bản nâng cấp theo quy trình dự kiến.
4. Kiểm tra dữ liệu và cấu hình cần giữ lại.
5. Gỡ cài đặt.
6. Xác nhận file chương trình được gỡ và dữ liệu người dùng được giữ/xóa đúng chính sách.
7. Cài lại để xác nhận trạng thái sạch.

Chính sách giữ dữ liệu khi uninstall cần được thiết kế rõ. Không nên vô tình xóa dữ liệu người dùng hoặc để lại runtime/binary cũ mà người dùng không biết.

## 10. Kiểm thử riêng theo từng nền tảng

### 10.1. Windows

Kiểm tra:

- Cài đặt MSI/EXE bằng user thường hoặc quyền quản trị theo thiết kế.
- Start Menu và desktop shortcut.
- Đường dẫn cài đặt có dấu cách.
- Quyền ghi vào thư mục dữ liệu user.
- Windows Defender/SmartScreen và chữ ký của installer.
- Uninstall từ Settings/Apps hoặc cơ chế quản trị phần mềm.
- Upgrade từ phiên bản trước và hành vi shortcut.

Nếu ứng dụng dùng registry, service hoặc file association, kiểm tra đúng quyền và hành vi khi cài, nâng cấp, gỡ.

### 10.2. macOS

Kiểm tra:

- Cài/mở ứng dụng từ DMG hoặc PKG.
- Bundle APP có launcher và runtime đúng.
- Quyền truy cập thư mục user, Documents, Downloads và các vị trí cần thiết.
- Gatekeeper, quarantine và quy trình signing/notarization của bản phát hành.
- Chạy trên kiến trúc Intel/Apple silicon mà sản phẩm tuyên bố hỗ trợ.
- Gỡ ứng dụng và xử lý dữ liệu người dùng.

Một gói chạy được trên máy build có thể vẫn bị hệ thống bảo mật chặn trên máy người dùng nếu quy trình ký và phân phối chưa hoàn chỉnh.

### 10.3. Linux

Kiểm tra:

- Cài DEB hoặc RPM trên distro thuộc phạm vi hỗ trợ.
- Launcher có quyền thực thi.
- Desktop entry/shortcut nếu ứng dụng desktop.
- Thư viện native và dependency hệ thống.
- Quyền user khi ghi log, cache và cấu hình.
- Gỡ package bằng package manager.
- Chạy trên distro sạch với phiên bản thư viện hệ thống ở mức baseline.

Không nên kiểm tra duy nhất trên đúng distro đã build package. Nếu hỗ trợ nhiều distro, cần test từng họ package và baseline được công bố.

## 11. Kiểm tra artifact và tính toàn vẹn

Trước khi phát hành, lưu metadata:

- Tên artifact và loại package.
- Phiên bản ứng dụng.
- OS/architecture mục tiêu.
- JDK/build tool version.
- Commit hoặc mã build nguồn.
- Danh sách dependency và phiên bản.
- SHA-256 checksum.
- Trạng thái ký số nếu có.

Tạo checksum bằng công cụ hệ điều hành phù hợp, ví dụ:

```bash
sha256sum DesktopApp-1.0.0.deb
```

Trên Windows PowerShell:

```powershell
Get-FileHash .\DesktopApp-1.0.0.msi -Algorithm SHA256
```

Checksum giúp phát hiện file bị thay đổi trong quá trình lưu trữ hoặc chuyển giao. Nó không thay thế chữ ký số để xác thực nhà phát hành.

### 11.1. Ký số và phân phối

Với ứng dụng phân phối ra ngoài tổ chức:

- Windows thường ký installer và executable bằng code-signing certificate theo quy trình của tổ chức.
- macOS cần thực hiện signing và notarization theo yêu cầu phân phối hiện hành của Apple.
- Linux có thể phân phối qua repository/package signing theo mô hình của distro hoặc tổ chức.

Quy trình ký phải được thực hiện bằng khóa được quản lý an toàn. Không đặt private key hoặc mật khẩu ký vào source repository hay đóng gói chúng vào application image.

### 11.2. Kiểm tra version và metadata

Đảm bảo version trong installer, tên artifact, manifest và trang phát hành nhất quán. Người vận hành cần xác định được gói đang cài là bản nào và được build từ nguồn nào.

## 12. Tự động hóa build theo nền tảng trong CI

Với nhiều nền tảng, dùng ma trận build để mỗi runner tạo artifact cho chính nền tảng của nó:

```text
CI matrix:
  windows runner:
    setup JDK 17
    build application
    jpackage --type msi
    test installer on clean Windows VM

  macOS runner:
    setup JDK 17 for target architecture
    build application
    jpackage --type dmg
    sign and notarize
    test on clean macOS VM

  Linux runner:
    setup JDK 17
    build application
    jpackage --type deb or rpm
    test on clean target distro
```

Đây là khung quy trình. Trong dự án thực tế, lệnh build và đường dẫn input phải khớp build script của repository; runner macOS có thể cần chọn kiến trúc cụ thể; Windows có thể cần cài WiX; các bước ký/notarize cũng phải được bổ sung theo chính sách phát hành.

### 12.1. Build một lần, package nhiều lần?

Bytecode thuần Java có thể dùng chung giữa các nền tảng nếu không chứa thành phần phụ thuộc OS. Nhưng application image, runtime image và installer native cần được tạo cho nền tảng đích.

Một pipeline có thể:

1. Build JAR portable một lần từ source.
2. Phân phối JAR tới các runner đích.
3. Trên từng runner, chuẩn bị dependency native và runtime tương ứng.
4. Chạy jpackage trên runner đó.
5. Cài và kiểm thử artifact trên máy sạch cùng nền tảng.

Nếu quá trình build JAR tự sinh resource hoặc code theo OS, cần tách bước build đó theo nền tảng thay vì dùng chung artifact.

### 12.2. Giữ artifact có thể tái lập

Để điều tra sự cố phát hành, lưu lại:

- JDK và build tool version.
- Các tham số jpackage/jlink.
- Input JAR và dependency.
- Runtime modules đã chọn.
- OS image và kiến trúc runner.
- Checksum của output.
- Kết quả cài đặt trên máy sạch.

Không nên chỉ lưu installer cuối cùng mà bỏ mất thông tin về runtime image và input đã dùng để tạo nó.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| jpackage không tạo được loại installer yêu cầu | Đang chạy trên OS không hỗ trợ loại package đó hoặc thiếu công cụ đóng gói native. | Build trên runner của OS đích và cài công cụ mà jpackage --help yêu cầu. |
| App image chạy trên máy build nhưng không chạy trên máy sạch | Máy build có Java, native library hoặc cấu hình ngoài gói. | Test image trên VM sạch; xác nhận runtime và dependency đã được đóng gói. |
| ClassNotFoundException khi chạy | Thiếu dependency JAR hoặc cấu hình main/classpath sai. | Kiểm tra --input, main JAR và cách cung cấp dependency. |
| UnsatisfiedLinkError | Native library thiếu, sai kiến trúc hoặc thiếu dependency hệ thống. | Dùng binary đúng OS/CPU và kiểm tra ABI/dependency. |
| Runtime image thiếu module | jlink không đưa vào module cần thiết hoặc dependency được nạp động. | Phân tích module graph, thêm module cần và test toàn bộ chức năng. |
| Gói Linux chạy trên distro build nhưng lỗi ở distro khác | Baseline glibc hoặc thư viện hệ thống khác nhau. | Công bố distro hỗ trợ và test trên baseline sạch. |
| Shortcut chạy nhưng ứng dụng không tìm thấy file cấu hình | Code phụ thuộc current working directory. | Dùng vị trí resource hoặc thư mục dữ liệu cấu hình rõ ràng. |
| Cài đặt cần quyền cao nhưng ứng dụng chạy user thường không ghi được | Ứng dụng ghi dữ liệu vào thư mục cài đặt được bảo vệ. | Chuyển dữ liệu thay đổi vào thư mục user/app data phù hợp. |
| Gói macOS bị Gatekeeper chặn | Signing/notarization hoặc quarantine chưa được xử lý đúng. | Hoàn thiện quy trình phát hành theo yêu cầu hiện hành của Apple. |
| Bản nâng cấp làm mất cấu hình | Installer hoặc ứng dụng ghi đè/xóa dữ liệu người dùng. | Tách dữ liệu user khỏi thư mục cài đặt và kiểm thử upgrade/uninstall. |
| Artifact khác kiến trúc máy đích | Runtime/native library được build cho CPU khác. | Build runtime image và dependency theo đúng kiến trúc mục tiêu. |

## 14. Checklist kiểm thử trên máy sạch

Trước khi phát hành từng gói, có thể ghi nhận các điểm sau:

- [ ] Đúng OS, phiên bản và kiến trúc được hỗ trợ.
- [ ] Installer được tạo trên runner phù hợp với nền tảng đích.
- [ ] Máy thử không có JDK/JRE nếu gói tuyên bố tự chứa runtime.
- [ ] Cài đặt thành công theo hướng dẫn người dùng cuối.
- [ ] Launcher khởi động được sau khi cài.
- [ ] Dependency Java và native đều có mặt.
- [ ] Các chức năng chính hoạt động, kể cả chức năng ít dùng.
- [ ] Đường dẫn có khoảng trắng/ký tự Unicode được xử lý đúng.
- [ ] Ứng dụng chạy bằng tài khoản user thông thường.
- [ ] Cấu hình, cache, log và dữ liệu được ghi đúng vị trí.
- [ ] Upgrade giữ đúng dữ liệu cần giữ.
- [ ] Uninstall xử lý đúng chương trình và dữ liệu người dùng.
- [ ] Chữ ký/checksum và metadata phát hành được xác nhận.
- [ ] Kết quả kiểm thử, môi trường và artifact checksum được lưu lại.

## 15. Bài tập thực hành

### Bài 1 — Tạo app image

Tạo một ứng dụng Java 17 có Main-Class, chuẩn bị thư mục input gồm JAR chính và dependency, rồi chạy jpackage --type app-image. Mở thư mục image và xác định launcher, runtime, app content.

### Bài 2 — Tạo installer trên nền tảng đích

Trên Windows, tạo MSI; trên macOS, tạo DMG hoặc PKG; trên Linux, tạo DEB hoặc RPM. Ghi lại hệ điều hành build và các công cụ hệ thống cần có.

### Bài 3 — So sánh JAR và gói tự chứa runtime

Chạy JAR trên máy có Java 17. Sau đó chạy app image trên VM không cài Java. Ghi lại khác biệt về điều kiện runtime và cấu trúc phân phối.

### Bài 4 — Tạo runtime image với jlink

Với ứng dụng modular, xác định module gốc và tạo runtime image. Thử bỏ một module cần thiết rồi quan sát lỗi; bổ sung lại module và kiểm tra các chức năng sử dụng nó.

### Bài 5 — Kiểm thử dependency native

Tích hợp một thư viện native phù hợp với môi trường thử nghiệm. Build gói cho một kiến trúc, sau đó kiểm tra vì sao binary không thể được dùng trực tiếp trên kiến trúc khác.

### Bài 6 — Kiểm thử trên máy sạch

Tạo VM mới, không cài Java, cài gói tự chứa runtime, chạy các luồng chính, nâng cấp và gỡ cài đặt. Lưu OS version, kiến trúc, checksum artifact và kết quả.

## 16. Tài liệu Java 17 chính thức

- [Java SE 17 jpackage tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jpackage.html): tạo application image và installer theo nền tảng, tùy chọn input, main class, runtime image và package type.
- [Java SE 17 jlink tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jlink.html): tạo runtime image tùy chỉnh từ module graph.
- [Java SE 17 jar tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html): tạo và kiểm tra JAR, manifest và metadata module.
- [Java SE 17 jdeps tool](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jdeps.html): phân tích dependency tĩnh của ứng dụng và thư viện.
- [Java SE 17 Launcher](https://docs.oracle.com/en/java/javase/17/docs/specs/man/java.html): tùy chọn chạy ứng dụng, classpath và module path.

Một JAR thuần Java thường có thể dùng chung giữa nhiều hệ điều hành, nhưng application image, runtime image và installer native cần phù hợp với OS và kiến trúc đích. Trong Java 17, dùng jpackage để tạo gói và jlink khi cần runtime image tùy chỉnh. Hãy build trên runner phù hợp, kiểm tra application image trước, rồi cài installer trên máy sạch không kế thừa môi trường phát triển. Việc kiểm thử phải bao gồm dependency, native library, quyền truy cập, nâng cấp và gỡ cài đặt; đó mới là bằng chứng artifact có thể triển khai trong môi trường người dùng thực tế.
