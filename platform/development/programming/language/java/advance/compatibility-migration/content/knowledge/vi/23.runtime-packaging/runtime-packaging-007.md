
# jpackage và cách phân phối ứng dụng desktop

Một chương trình Java chạy được từ IDE hoặc bằng lệnh `java -jar` chưa đồng nghĩa với một **ứng dụng desktop có thể phân phối cho người dùng cuối**. Họ cần launcher, biểu tượng, cách cài đặt, cập nhật, gỡ cài đặt, quyền ghi dữ liệu, hỗ trợ nhiều hệ điều hành và một Java runtime tương thích mà không phải tự cấu hình.

`jpackage` giúp tạo **application image** và **gói cài đặt native** cho những ứng dụng Java desktop. Trong bài toán *Java Advance Compatibility Migration*, phần *Đóng gói và môi trường*, công cụ này đặc biệt quan trọng khi hệ thống chuyển từ mô hình “cài JRE trên máy khách rồi chạy JAR” sang mô hình **đóng gói ứng dụng cùng runtime riêng**, nhằm kiểm soát JDK version và giảm lỗi môi trường.

Tuy nhiên, việc chạy thành công `jpackage` mới chứng minh công cụ đã tạo artifact. **Khả năng cài đặt và vận hành trên máy thật** còn phụ thuộc module Java, JavaFX, native libraries, CPU architecture, hệ điều hành, signing, cấu hình launcher và quy trình update. Bài học hướng dẫn từng lớp đó và cách kiểm chứng khi nâng JDK.

Các ví dụ sử dụng `jpackage` của JDK hỗ trợ công cụ này. Tên option, công cụ bổ trợ và native installer format có thể khác theo JDK release hoặc vendor. Luôn kiểm tra `jpackage --help` và tài liệu của **đúng JDK và OS đích**. Các package names, versions và paths minh họa phải được thay bằng dữ liệu thực tế của dự án.

## 1. Java desktop cần những gì ngoài một JAR?

Một ứng dụng đơn giản có thể chạy như sau:

~~~bash
java -jar desktop-app.jar
~~~

Nhưng người dùng cuối thường không muốn mở terminal rồi tìm classpath hoặc cài JDK thủ công. Khi phân phối một ứng dụng desktop, nhóm phát triển cần giải quyết:

- **Launcher:** người dùng double-click icon hoặc chọn từ menu hệ điều hành.
- **Runtime:** phiên bản Java, modules, JVM options và native dependencies.
- **Installer:** vị trí cài đặt, shortcut, file associations và quyền cài.
- **Phiên bản:** tên gói, version, upgrade identity và tương thích dữ liệu.
- **Bảo mật:** chữ ký số của package, source tải xuống, update authenticity.
- **Dữ liệu:** nơi lưu cấu hình, cache, logs và tài liệu người dùng.
- **Vận hành:** hỗ trợ lỗi khởi động, gỡ cài đặt, rollback và bản vá bảo mật.
- **Đa nền tảng:** Windows, macOS, Linux và kiến trúc CPU.

Một bản JAR chạy đúng trên máy developer vẫn có thể thất bại khi đặt trên máy không có JDK hoặc thiếu JavaFX native libraries.

### 1.1. Các cách phân phối phổ biến

| Mô hình | Người dùng nhận | Điểm mạnh | Hạn chế |
|---|---|---|---|
| JAR thuần | JAR, tài liệu hướng dẫn Java | Đơn giản cho developer | Phụ thuộc JRE/system setup |
| JAR cùng script | JAR, dependency, shell/batch script | Dễ tùy chỉnh nội bộ | Launcher và UX còn thủ công |
| `jpackage --type app-image` | Thư mục ứng dụng, launcher, runtime | Kiểm thử/copy trước installer | Chưa tự là native installer |
| Installer do jpackage tạo | MSI/EXE, DMG/PKG, DEB/RPM tùy OS | Trải nghiệm cài đặt quen thuộc | Phụ thuộc công cụ/metadata của OS |
| Installer + update system riêng | Gói cài và cơ chế cập nhật | Có thể kiểm soát lifecycle | Phải thiết kế xác thực, rollback |

**`jpackage` không biến toàn bộ Java bytecode thành mã máy AOT** như một native-image compiler. Nó chủ yếu xây launcher, runtime image và cấu trúc/gói cài ứng dụng theo nền tảng.

## 2. jpackage là gì?

`jpackage` là công cụ dòng lệnh trong JDK có nhiệm vụ tạo application image và native package cho một ứng dụng Java.

Những mốc lịch sử quan trọng:

- **JDK 14:** `jpackage` được giới thiệu ở trạng thái incubating theo JEP 343.
- **JDK 16:** `jpackage` trở thành công cụ production theo JEP 392.
- **Những JDK tiếp theo:** tiếp tục điều chỉnh tính năng, signing, installer options và cách tích hợp nền tảng.

Vì vậy, một dự án chạy trên **JDK 8 hoặc JDK 11 không thể mặc định dựa vào công cụ `jpackage` chuẩn trong JDK đó**. Có thể dùng JDK mới hơn cho bước build/package và chọn runtime phù hợp, nhưng phải kiểm chứng application compatibility và bytecode target riêng.

### 2.1. Kiểm tra toolchain

~~~bash
java -version
javac -version
jpackage --version
jpackage --help
~~~

Trên Windows PowerShell:

~~~powershell
java -version
jpackage --version
jpackage --help
~~~

Nếu máy có nhiều JDK, `java` và `jpackage` trên PATH có thể đến từ hai installations khác nhau. Nên gọi theo đường dẫn JDK rõ ràng trong CI và ghi lại version.

### 2.2. jpackage khác jlink như thế nào?

| Công cụ | Trách nhiệm chính |
|---|---|
| `javac` | Biên dịch Java source |
| `jar` | Tạo/đọc JAR |
| `jdeps` | Phân tích các tham chiếu module/dependency ở bytecode |
| `jlink` | Tạo custom Java runtime image chứa tập modules đã chọn |
| `jpackage` | Tạo application image và installer với launcher |
| Maven/Gradle | Quản lý dependency, build pipeline và gọi các công cụ |
| Công cụ OS | MSI, signing, notarization, Linux package metadata |

`jlink` tạo runtime image, **không tự xây trải nghiệm installer của ứng dụng**. `jpackage` có thể xây một runtime cho package hoặc dùng runtime image mà nhóm đã cung cấp qua `--runtime-image`.

## 3. jpackage tạo ra những thành phần nào?

Quy trình tổng quát:

~~~mermaid
flowchart TD
    A["Source / resources"] --> B["Compile + JAR/modules"]
    C["Third-party dependencies"] --> D["Application input"]
    B --> D
    E["JDK / custom runtime / JavaFX"] --> F["Runtime image"]
    D --> G["jpackage"]
    F --> G
    H["Icons, metadata, launcher flags"] --> G
    G --> I["Application image"]
    I --> J["Native installer theo OS"]
    J --> K["Cài đặt, khởi chạy, upgrade, uninstall"]
~~~

Một application image thường có:

- **Application launcher**: file thực thi hoặc entrypoint phù hợp OS.
- **Application files**: JARs/modules, resources, native dependencies cần thiết.
- **Java runtime**: tập JVM/Java modules đóng cùng ứng dụng.
- **Launcher configuration**: main class/module và JVM arguments.
- **OS metadata**: tên, version, biểu tượng và những thành phần khác.

Không nên hardcode cấu trúc các thư mục trong image vì layout khác nhau theo OS và JDK. Trên macOS, bundle `.app` có cấu trúc riêng; trên Windows/Linux cách đặt launcher và runtime khác.

### 3.1. Bundled runtime khác system JRE

Khi ứng dụng mang runtime riêng, người dùng **thường không phải cài Java system-wide** để chạy ứng dụng đó. Điều này giảm rủi ro:

- Máy khách không có Java.
- Máy khách có Java cũ không tương thích.
- Nhiều ứng dụng tranh nhau Java version.
- Environment variables bị đặt sai.
- JDK system được nâng gây regression cho app desktop.

Nhưng đổi lại, nhóm phát hành phải **cập nhật bản Java runtime được đóng trong installer** khi có bản vá bảo mật. Việc người dùng cập nhật system JDK không chắc tác động tới bundled runtime.

### 3.2. Runtime được đóng gói không phải toàn bộ hệ điều hành

GUI, printer, font rendering, JNI, native drivers, OpenGL/graphics stack và các OS APIs vẫn phụ thuộc platform. Có bundled runtime không bảo đảm một app image Linux chạy trên mọi distro, hoặc DLL Windows chạy trên macOS.

## 4. Các kiểu output theo nền tảng

| OS build | `--type` thường gặp | Kết quả |
|---|---|---|
| Windows | `app-image` | Thư mục có launcher/runtime |
| Windows | `exe`, `msi` | Gói cài đặt native Windows |
| macOS | `app-image` | Application bundle |
| macOS | `dmg`, `pkg` | Disk image hoặc installer package |
| Linux | `app-image` | Thư mục ứng dụng |
| Linux | `deb`, `rpm` | Linux package |

Đây là **các định dạng thông dụng**, không bảo đảm mọi JDK/vender có đúng mọi tùy chọn. Kiểm tra hỗ trợ trên host bằng `jpackage --help`.

### 4.1. Native packaging thường phải build trên target OS

Không nên giả định build Linux tạo được MSI và DMG chuẩn chỉ bằng cách đổi `--type`. `jpackage` được thiết kế theo **native packaging platform**, nên quy trình CI thường cần worker/build host Windows, macOS và Linux riêng.

Tương tự, runtime image và native libraries phải tương thích kiến trúc CPU:

~~~text
Windows x64  != Windows ARM64
macOS x64    != macOS ARM64
Linux x64    != Linux ARM64
~~~

Java bytecode có thể portable, nhưng launcher, runtime, JavaFX và native libraries không tự trở thành cross-platform.

### 4.2. App image và installer giải quyết hai việc khác nhau

**App image** giúp xác minh application runtime và launcher. **Installer** thêm quy trình cài đặt, metadata, shortcut và gỡ cài đặt theo OS.

Quy trình nên là:

1. Biên dịch ứng dụng và chuẩn bị dependency.
2. Tạo app image.
3. Chạy launcher thực tế trên OS đích.
4. Kiểm tra GUI, resources, network, JNI.
5. Sau khi app image đạt mới tạo native installer.
6. Test install, upgrade và uninstall như người dùng cuối.

## 5. Ví dụ tự chứa: ứng dụng Swing nhỏ

Ví dụ dùng Swing để không cần giả định JavaFX đã có trong JDK. Source:

~~~java
package com.example.desktop;

import java.awt.BorderLayout;
import javax.swing.JButton;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.SwingUtilities;

public final class DesktopMain {
    private DesktopMain() {
    }

    public static void main(String[] args) {
        SwingUtilities.invokeLater(() -> {
            JFrame frame = new JFrame("DeskDemo");
            frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
            frame.setLayout(new BorderLayout());

            JLabel label = new JLabel("Xin chào Java desktop");
            JButton button = new JButton("Nhấn");

            button.addActionListener(event ->
                    label.setText("Đã nhấn nút"));

            frame.add(label, BorderLayout.CENTER);
            frame.add(button, BorderLayout.SOUTH);
            frame.setSize(420, 230);
            frame.setLocationRelativeTo(null);
            frame.setVisible(true);
        });
    }
}
~~~

Giải thích:

- `SwingUtilities.invokeLater` khởi tạo GUI trên Event Dispatch Thread.
- `JFrame.EXIT_ON_CLOSE` cho phép ứng dụng thoát khi đóng cửa sổ.
- `java.desktop` là Java SE module liên quan Swing/AWT.
- Application main class là `com.example.desktop.DesktopMain`.
- Ví dụ không có dependencies ngoài Java SE.

### 5.1. Biên dịch và tạo JAR

Trong shell Unix:

~~~bash
mkdir -p build/classes build/package-input
javac -d build/classes src/com/example/desktop/DesktopMain.java
jar --create --file build/package-input/desk-demo.jar \
    --main-class com.example.desktop.DesktopMain \
    -C build/classes .
~~~

Chạy trước packaging:

~~~bash
java -jar build/package-input/desk-demo.jar
~~~

Nếu project dùng Maven/Gradle, để build tool tạo JAR và copy runtime dependencies, không nên tự duy trì một đường build riêng dễ lệch với CI.

### 5.2. Chuẩn bị input directory khi có nhiều JAR

Ví dụ khái niệm:

~~~text
build/package-input/
├── desktop-app.jar
├── dependency-a.jar
├── dependency-b.jar
└── resources/
~~~

`--input` chỉ định thư mục input. `--main-jar` xác định JAR chính trong đó. **Đừng hiểu rằng jpackage sẽ tự resolve dependency từ Maven repository** chỉ vì có main JAR; build pipeline phải chuẩn bị các application files mà launcher cần.

Sau khi đóng gói, phải thử launcher từ image để kiểm tra classpath và resources thực tế.

## 6. Tạo app-image với jpackage

Ví dụ:

~~~bash
jpackage \
  --type app-image \
  --input build/package-input \
  --dest build/dist \
  --name DeskDemo \
  --main-jar desk-demo.jar \
  --main-class com.example.desktop.DesktopMain \
  --app-version 1.0.0 \
  --vendor "Example Team" \
  --add-modules java.desktop
~~~

Các option:

| Option | Công dụng |
|---|---|
| `--type app-image` | Tạo thư mục ứng dụng tự chứa |
| `--input` | Thư mục các application files |
| `--dest` | Output directory |
| `--name` | Tên ứng dụng/launcher |
| `--main-jar` | JAR chính, tương đối với input |
| `--main-class` | Main class của non-modular application |
| `--app-version` | Phiên bản ứng dụng |
| `--vendor` | Tên nhà phát hành |
| `--add-modules` | Module bổ sung cho quá trình tạo runtime |

Nếu main JAR manifest đã chỉ rõ main class, công cụ có thể suy ra class tùy mô hình; việc chỉ định tường minh làm ví dụ dễ theo dõi.

### 6.1. Kiểm tra output

Cấu trúc minh họa:

~~~text
build/dist/
└── DeskDemo/
    ├── launcher
    ├── app/
    │   └── desk-demo.jar
    └── runtime/
        ├── bin/
        └── lib/
~~~

**Đây không phải layout chuẩn bắt buộc.** Mỗi OS/JDK có thể tổ chức khác; đặc biệt macOS app bundle có cấu trúc riêng.

Kiểm thử:

- Tìm launcher thực tế trong image.
- Mở cửa sổ ứng dụng.
- Nhập tiếng Việt và kiểm tra font.
- Kiểm tra hình ảnh/resources.
- Đóng ứng dụng và xác nhận process kết thúc.
- Thử trên máy không có system Java configured.
- Kiểm tra source JDK/runtime version được nhúng khi cần chẩn đoán.

### 6.2. App image là điểm dừng kỹ thuật hữu ích

Nếu launcher trong app image đã không chạy, đóng nó thành MSI/DMG thường không giải quyết được lỗi runtime. Nên sửa trước những vấn đề như missing class, thiếu module, sai main class hoặc native libraries.

## 7. Ứng dụng non-modular và modular

`jpackage` hỗ trợ hai mô hình chính.

### 7.1. Non-modular application

Thường dùng `--input`, `--main-jar`, `--main-class`:

~~~bash
jpackage --type app-image \
  --name DeskDemo \
  --input build/package-input \
  --main-jar desk-demo.jar \
  --main-class com.example.desktop.DesktopMain
~~~

Hợp với ứng dụng truyền thống chạy trên classpath. Không bắt buộc phải thêm `module-info.java` chỉ để phân phối bằng jpackage.

Tuy nhiên, cần kiểm tra những JAR runtime, file service metadata và dynamic class loading không bị thiếu sau packaging.

### 7.2. Modular application (JPMS)

Ví dụ module descriptor:

~~~java
module com.example.desktop {
    requires java.desktop;
    exports com.example.desktop;
}
~~~

Nếu modular JARs đã được tạo trong `build/mods`:

~~~bash
jpackage \
  --type app-image \
  --name DeskDemo \
  --module-path build/mods \
  --module com.example.desktop/com.example.desktop.DesktopMain \
  --dest build/dist
~~~

Ở đây `--module` chỉ định main module và main class. Named modules cần module graph thích hợp.

### 7.3. Không trộn hai cách khai báo main application

Một lỗi thường gặp là dùng cả cấu hình main JAR và module main từ hai mô hình khác nhau rồi không biết launcher sẽ chọn gì. Hãy chọn một mô hình phù hợp và chạy thử output.

### 7.4. Có nên modular hóa chỉ vì packaging?

Không nhất thiết. JPMS mang lại explicit module boundaries nhưng cũng có thể làm lộ:

- Split packages.
- Reflection không có `opens`.
- Automatic module naming.
- Provider modules không được resolve.
- Dependencies chưa hỗ trợ module path.

Nếu ứng dụng legacy classpath đang ổn, có thể chuyển packaging trước và để migration JPMS thành một hạng mục được kiểm chứng độc lập.

## 8. jlink và runtime image tùy biến

`jlink` tạo một Java runtime image chỉ chứa những modules được chọn.

Ví dụ ứng dụng Swing đơn giản:

~~~bash
jlink \
  --add-modules java.base,java.desktop \
  --output build/runtime \
  --strip-debug \
  --no-header-files \
  --no-man-pages
~~~

Sau đó:

~~~bash
jpackage \
  --type app-image \
  --name DeskDemo \
  --input build/package-input \
  --main-jar desk-demo.jar \
  --main-class com.example.desktop.DesktopMain \
  --runtime-image build/runtime \
  --dest build/dist
~~~

`--runtime-image` nhận runtime đã tạo sẵn. Điều này cho phép team kiểm soát modules, JDK update và các tùy chọn jlink riêng.

### 8.1. Rủi ro khi runtime image quá nhỏ

Một app chỉ có cửa sổ chính có thể chạy, nhưng chức năng ít dùng thất bại:

- In tài liệu.
- Dùng JDBC.
- Tải TLS/security provider.
- Mở JavaFX/FXML controller.
- Tải class theo reflection string.
- Dùng ServiceLoader.
- Nạp plugin động.
- Gọi một JNI library.

Không nên suy từ “startup thành công” rằng runtime image đã đầy đủ.

### 8.2. jdeps hỗ trợ xác định modules

Ví dụ:

~~~bash
jdeps --print-module-deps \
  --class-path "build/package-input/*" \
  build/package-input/desk-demo.jar
~~~

`jdeps` tìm dependency tĩnh. Nó không nhất thiết phát hiện service provider được chọn động, module nạp qua reflection hoặc feature optional. Vì vậy kết quả `jdeps` phải được đối chiếu với integration tests.

### 8.3. Service binding

Khi tạo runtime modular, một số ứng dụng cần provider modules. `jlink` có khả năng service binding và `jpackage` có option liên quan để chuyển lựa chọn modules/jlink options theo JDK.

Nếu dùng `ServiceLoader`, crypto providers hoặc locale services, cần kiểm tra các provider được đóng trong image. Không đơn giản chỉ giữ `java.base` vì nó là module tối thiểu.

## 9. Đóng gói JavaFX

JavaFX có yêu cầu khác với Swing:

- Module `javafx.controls`, `javafx.graphics`, `javafx.fxml` nếu sử dụng.
- Các native libraries có tính OS/architecture.
- FXML resources và CSS/images/fonts.
- Reflection access cho FXML controller.
- JavaFX version tương thích với toolchain và runtime.

Trong các JDK hiện đại thông thường, **JavaFX không mặc định đi kèm như một phần của Java SE runtime**. Vì vậy, cài một JDK không có nghĩa app JavaFX có đủ JavaFX libraries.

### 9.1. Module descriptor

Ví dụ:

~~~java
module com.example.viewer {
    requires javafx.controls;
    requires javafx.fxml;
    exports com.example.viewer;
    opens com.example.viewer.controller to javafx.fxml;
}
~~~

`opens` cho phép FXML loader thực hiện reflection vào controller package theo thiết kế.

### 9.2. Target-specific JavaFX JMODs

Nếu xây custom runtime bằng jlink, phải dùng JavaFX JMODs phù hợp với OS/CPU đích. Một bộ JavaFX native libraries cho Linux không thể giả định chạy được trên Windows.

Trong CI, nên tạo job packaging riêng và xác minh input artifact theo platform.

### 9.3. Những bài test quan trọng với JavaFX

- Stage/scene mở được.
- FXML controller được tạo.
- CSS/fonts/images load đúng.
- Bàn phím, input tiếng Việt và Unicode.
- Rendering/DPI/multiple displays.
- Media/WebView nếu ứng dụng sử dụng.
- Native libraries không lỗi khi bắt đầu.
- Application image chạy mà không dùng JavaFX SDK ngoài.

Nếu `javafx.graphics` hoặc thư viện native thiếu, lỗi có thể xuất hiện khi launch hoặc chỉ khi gọi feature cụ thể.

## 10. Phân phối trên Windows

Windows thường hỗ trợ tạo `msi` hoặc `exe` bằng `jpackage`.

Ví dụ PowerShell một dòng (giả định input folder đã chuẩn bị):

~~~powershell
jpackage --type msi --input build\package-input --dest build\dist --name DeskDemo --main-jar desk-demo.jar --main-class com.example.desktop.DesktopMain --app-version 1.0.0 --vendor "Example Team" --win-menu --win-shortcut
~~~

### 10.1. Công cụ hỗ trợ installer

Trên một số JDK, packaging Windows MSI/EXE yêu cầu **WiX Toolset**. Phiên bản WiX được hỗ trợ thay đổi theo JDK, vì vậy phải tham khảo hướng dẫn của bản `jpackage` đang chạy.

Nếu gặp lỗi toolchain không tìm thấy WiX hoặc không tương thích version, đây là lỗi **native packaging toolchain**, không phải Java source lỗi.

### 10.2. Icon Windows

Icon native Windows thường dùng `.ico`:

~~~powershell
jpackage --type app-image --input build\package-input --name DeskDemo --main-jar desk-demo.jar --icon assets\desk-demo.ico
~~~

Không mặc định một PNG là format icon phù hợp cho mọi installer.

### 10.3. Installation scope và permissions

Có thể cần quyết định cài:

- Theo user.
- Cho toàn máy.
- Vào một install directory cố định.
- Có/không shortcut.
- Có cho chọn thư mục nếu được hỗ trợ.
- Có yêu cầu quyền admin hay không.

Ứng dụng không nên yêu cầu quyền admin để ghi config thường xuyên. Hãy lưu mutable data vào per-user application data directory.

### 10.4. Upgrade identity trên Windows

Installer MSI có metadata nhận diện sản phẩm và upgrade. Các tùy chọn Windows-specific (chẳng hạn upgrade identifier, khi JDK hỗ trợ) cần được quản lý ổn định giữa các bản nếu muốn nâng cấp tại chỗ.

Nếu mỗi bản release đổi identity ngẫu nhiên, có thể tạo cài đặt song song hoặc không thay thế được version cũ.

## 11. Phân phối trên macOS

macOS thường có `app-image` dạng app bundle, `dmg` và `pkg`.

Ví dụ:

~~~bash
jpackage \
  --type dmg \
  --input build/package-input \
  --dest build/dist \
  --name DeskDemo \
  --main-jar desk-demo.jar \
  --main-class com.example.desktop.DesktopMain \
  --app-version 1.0.0 \
  --vendor "Example Team" \
  --icon assets/desk-demo.icns
~~~

### 11.1. Icon và app bundle

macOS icon thường dùng `.icns`. Bundle có cấu trúc nội bộ riêng để chứa launcher, runtime và resources. Không hardcode project-root paths trong ứng dụng.

### 11.2. Code signing

Để phân phối qua những kênh yêu cầu, app bundle và installer phải được ký theo chính sách macOS. Không phải cứ ký JAR là native app bundle cũng được ký.

Signing certificates/keys cần được bảo vệ trong hệ thống phát hành, không đặt mật khẩu hoặc private key trong Git hay terminal logs.

### 11.3. Notarization và Gatekeeper

Một quy trình phát hành ngoài App Store có thể cần:

1. Tạo app bundle hoặc installer.
2. Ký đúng các thành phần.
3. Thực hiện notarization theo quy trình Apple nếu kênh phân phối yêu cầu.
4. Kiểm tra kết quả và xử lý lỗi.
5. Staple ticket khi phù hợp.
6. Kiểm thử mở ứng dụng trên máy sạch có chính sách bảo mật mặc định.

`jpackage` **không phải một dịch vụ phát hành/notarization tự động**; những bước này cần công cụ và credentials tương ứng.

### 11.4. Intel và Apple Silicon

macOS có các kiến trúc CPU khác nhau. Runtime image, JavaFX modules và JNI libraries phải phù hợp. Nếu phát hành nhiều architecture, cần các build và kiểm thử tương ứng hoặc một chiến lược packaging được nền tảng hỗ trợ rõ ràng.

## 12. Phân phối trên Linux

Các định dạng thường gặp:

~~~bash
jpackage \
  --type deb \
  --input build/package-input \
  --dest build/dist \
  --name desk-demo \
  --main-jar desk-demo.jar \
  --main-class com.example.desktop.DesktopMain \
  --app-version 1.0.0 \
  --vendor "Example Team" \
  --linux-shortcut
~~~

Hoặc chọn `--type rpm` với môi trường build phù hợp.

### 12.1. Toolchain OS

DEB/RPM packaging cần các công cụ tạo package của hệ điều hành theo yêu cầu JDK. Không có guarantee rằng mọi distro có cùng công cụ hoặc phiên bản tương thích.

Cần kiểm tra:

- Toolchain package builder.
- Package metadata và naming.
- OS distribution/architecture.
- Shared library dependencies.
- Permissions của launcher và install directory.
- Desktop environment integration.

### 12.2. Linux không phải một môi trường duy nhất

Một package chạy được trên Ubuntu mới chưa chắc chạy được trên bản Debian cũ hoặc Linux distribution khác. JNI/GUI có thể phụ thuộc libc, X11/Wayland, graphics, fonts và system libraries.

Hãy công bố **supported Linux distributions và versions**, sau đó test trên đúng target images.

### 12.3. Package repository

Tạo file DEB/RPM không tự cung cấp package repository, ký repository metadata hay update channel. Nếu phân phối qua repository, cần thêm hạ tầng và policy bảo mật tương ứng.

## 13. Metadata, version và package identity

Những option cần quản lý:

| Metadata | Vai trò |
|---|---|
| `--name` | Tên ứng dụng và launcher |
| `--app-version` | Version sản phẩm |
| `--vendor` | Publisher |
| `--description` | Mô tả |
| `--copyright` | Thông tin bản quyền |
| `--icon` | Biểu tượng native |
| Identifier/package-name theo OS | Nhận diện ứng dụng và upgrade |

### 13.1. App version khác Java runtime version

Ví dụ:

~~~text
Application: DeskDemo 2.4.1
Bundled Java runtime: JDK 21, update cụ thể
JavaFX runtime: version đã chọn
jpackage tool: version cụ thể của JDK
Installer: Windows MSI build tương ứng
~~~

Có thể phát hành app version mới mà không đổi JDK, hoặc phải rebuild cùng application version policy khi cập nhật Java security patch.

Vì vậy, một release nên ghi cả **app version, Java runtime update và package checksum**.

### 13.2. Định danh ổn định ảnh hưởng upgrade

Đổi application name, package name hoặc OS-specific identifier có thể làm installer coi bản mới là sản phẩm khác. Khi rebrand hoặc đổi channel (stable/beta), cần thiết kế identity, install path và dữ liệu user có chủ đích.

## 14. Launcher options và arguments

`jpackage` cho phép truyền JVM options vào launcher, ví dụ:

~~~bash
jpackage \
  --type app-image \
  --input build/package-input \
  --name DeskDemo \
  --main-jar desk-demo.jar \
  --java-options "-Dapp.environment=desktop"
~~~

Các tùy chọn phải được phân biệt:

- **`--java-options`:** tham số cho JVM như `-D...`, GC hoặc module access flags.
- **`--arguments`:** tham số ứng dụng nhận qua `main(String[] args)`.
- **`--main-class`:** class cần được launcher gọi.
- **`--module`:** main module/main class nếu modular.

### 14.1. Không copy JVM flags cũ vào launcher mới

Một ứng dụng Java 8 có thể mang GC flag hoặc internal-API options đã bị xóa trên JDK mới, ví dụ một số cờ CMS. Khi đưa nguyên chuỗi đó vào launcher, app image có thể **không khởi động** dù JAR build thành công.

Phải kiểm tra JVM flags trên bundled JDK, đặc biệt:

- GC selection và GC logging.
- Module opens/exports.
- Encoding/locale.
- Heap limits.
- Native library path.
- Java agents.

Chỉ giữ cờ có mục đích được chứng minh.

### 14.2. Additional launchers

Ứng dụng có thể có launcher phụ như import tool hoặc diagnostics. Một số bản `jpackage` hỗ trợ option `--add-launcher` trỏ tới properties file để khai báo launcher bổ sung.

Đây là cách tổ chức nhiều entrypoints, nhưng cần kiểm tra syntax/options được hỗ trợ theo JDK cụ thể. Không coi launcher phụ là cơ chế phân quyền: người dùng vẫn cần chính sách authorization trong ứng dụng.

## 15. File associations

Một ứng dụng xem file có thể đăng ký extension để người dùng mở tài liệu bằng double-click. `jpackage` hỗ trợ file associations trên các OS/JDK phù hợp.

Ví dụ một properties file khái niệm:

~~~properties
extension=demo
mime-type=application/x-desk-demo
description=DeskDemo document
~~~

Định dạng properties, các trường bổ sung và icon của association phải được xác minh trên JDK/OS target.

### 15.1. Test association như người dùng

- Double-click file có extension được đăng ký.
- File path có khoảng trắng và Unicode.
- File bị hỏng hoặc không được phép mở.
- Nhiều lần mở khi ứng dụng đang chạy.
- Thay đổi default app của user.
- Gỡ cài đặt có xóa association/shortcut phù hợp không?
- App thực sự nhận đúng path/open event.

Việc tạo association không tự triển khai logic mở file trong Java; ứng dụng cần xử lý input phù hợp với launcher/OS.

### 15.2. Không chiếm extension phổ biến vô lý

Việc đăng ký file association ảnh hưởng môi trường người dùng. Ưu tiên extension/MIME type có chủ đích và tránh thay đổi default handlers ngoài phạm vi được duyệt.

## 16. Thư mục cài đặt không phải chỗ ghi dữ liệu user

Một lỗi migration phổ biến là ứng dụng cũ đặt JAR và file `settings.properties` trong cùng thư mục, rồi tiếp tục ghi vào thư mục đó sau khi dùng installer.

Điều này có thể thất bại vì:

- Install directory chỉ cho phép administrator ghi.
- Installer overwrite application-owned files khi upgrade.
- Gỡ cài đặt có thể xóa file cùng package.
- App bundle macOS có chính sách integrity/signing.
- Nhiều user chia sẻ một cài đặt nhưng cần config riêng.

### 16.1. Chia loại dữ liệu

| Loại | Nơi phù hợp về nguyên tắc |
|---|---|
| JAR/runtime/resources readonly | Install directory |
| User preferences | Per-user config directory |
| Local database do user sở hữu | Per-user application data directory |
| Cache | Per-user cache location |
| Logs | Thư mục writable theo policy |
| Tài liệu do user tạo | Thư mục do user chọn |
| Credentials | OS credential store/secret manager phù hợp |
| Shared settings | Đường dẫn managed bởi tổ chức, quyền rõ |

### 16.2. Convention theo OS

- Windows: vùng AppData theo user, qua API/path policy thích hợp.
- macOS: vùng Application Support trong user Library.
- Linux: XDG Base Directory conventions khi áp dụng.

Không hardcode đường dẫn chứa tên user hoặc ghi file vào thư mục tạm mà không có lifecycle policy.

### 16.3. Resource được đóng trong JAR

Nếu là resource mặc định chỉ đọc:

~~~java
try (var stream = DesktopMain.class
        .getResourceAsStream("/config/defaults.properties")) {
    if (stream == null) {
        throw new IllegalStateException("Missing defaults");
    }
    // Đọc dữ liệu từ stream.
}
~~~

Không giả định current working directory của launcher là project root. File mutable nên có đường dẫn data riêng, không sửa JAR hoặc install bundle.

## 17. Native dependencies và kiến trúc CPU

Một ứng dụng Java desktop có thể dùng:

- JNI/JNA DLL/SO/DYLIB.
- JavaFX graphics native libraries.
- Database native client.
- Printer/scanner drivers.
- Multimedia codecs.
- Browser embedding engine.
- PKCS#11/HSM client.
- OS integration bridges.

`jpackage` không tự làm những thư viện này portable.

Ví dụ:

~~~text
Java bytecode: platform-independent
Windows x64 DLL: architecture-specific
Target runtime: Linux ARM64
~~~

Không thể chạy DLL Windows x64 trên Linux ARM64 chỉ vì JVM có thể nạp Java bytecode.

### 17.1. Kiểm tra đường dẫn thư viện

Nếu ứng dụng dùng `System.loadLibrary(...)` hoặc `System.load(...)`, cần kiểm tra launcher config, paths, quyền thực thi và packaging layout.

Không dựa vào việc developer đã đặt native library trong system directories hoặc PATH. Máy user sạch có thể không có những thứ đó.

### 17.2. JavaFX và file media

Ứng dụng JavaFX có thể startup được nhưng chỉ lỗi khi mở WebView/media hoặc một scene có resource. Đó là lý do phải test các chức năng ít được sử dụng, không chỉ màn hình đầu tiên.

## 18. Signing, trust và bảo mật của installer

Một native installer tải từ Internet có thể chịu:

- Code signing policy.
- macOS Gatekeeper/notarization.
- Windows SmartScreen/reputation.
- Enterprise endpoint protection.
- Linux package repository signing.
- Browser download warning.

**Checksum, code signing và notarization là các lớp khác nhau.**

| Cơ chế | Câu hỏi chính |
|---|---|
| SHA-256 checksum | File có thay đổi không? |
| Code signing | File gắn với publisher/khóa ký được tin cậy không? |
| Notarization / platform validation | Artifact có đáp ứng quy trình kiểm tra nền tảng không? |
| Update signatures | Bản update có đến từ nguồn được phép không? |
| SBOM/provenance | Artifact gồm những thành phần nào, được build ra sao? |

Không gửi private keys/password trong source repository hoặc logging. Signing cần được tích hợp trong release pipeline có access control.

### 18.1. Không chữa warning bằng cách tắt hệ điều hành bảo vệ

Nếu người dùng bị Gatekeeper/SmartScreen chặn, giải pháp phát hành bền vững là xác minh ký, notarization, uy tín publisher và distribution channel. Không nên hướng dẫn tắt toàn bộ cơ chế bảo vệ để app chạy.

## 19. jpackage không phải hệ thống auto-update

Gói MSI/DMG/DEB được tạo không có nghĩa ứng dụng tự phát hiện và cài phiên bản mới.

Nếu muốn auto-update hoặc managed rollout, cần thiết kế:

- Release metadata và version channel.
- Xác thực nguồn và chữ ký bản cập nhật.
- Download, checksum/signature validation.
- Compatibility OS/CPU.
- Cơ chế nâng cấp installer.
- Quyền user/admin.
- Xử lý ứng dụng đang chạy.
- Phương án rollback.
- Data schema migration.
- Logging/telemetry lỗi update.

Với doanh nghiệp, có thể dùng công cụ quản lý thiết bị/package repository phù hợp hệ điều hành. Với người dùng phổ thông, có thể dùng một updater được hỗ trợ, nhưng phải đánh giá bảo mật riêng.

### 19.1. Upgrade identity ổn định

Windows MSI, macOS bundle identifiers và Linux package names/versions đều có semantics ảnh hưởng upgrade. Đừng thay định danh sản phẩm ngẫu nhiên mỗi release.

### 19.2. Không mất dữ liệu khi nâng cấp

Một installer có thể thay application files mà không cần xóa tài liệu của người dùng. Tuy nhiên, nếu local data format/schema thay đổi, bản cũ có thể không đọc được sau rollback.

Cần có kế hoạch **data migration, backup và backward compatibility** ngoài việc chỉ quản lý file installer.

## 20. Runtime updates và trách nhiệm bảo trì

Khi bundle Java runtime, nhóm sản phẩm chịu trách nhiệm đưa bản vá Java tới user thông qua bản phát hành ứng dụng.

Một bản vá JDK có thể sửa:

- Security/TLS bugs.
- Certificate validation.
- Runtime/GC defects.
- Charset/locale handling.
- Graphics/font behavior.
- Native library issues.
- HotSpot crashes.

Không phải chỉ thay `-jar` hoặc cập nhật Java hệ thống là đủ.

### 20.1. Ghi release inventory

~~~yaml
product:
  name: DeskDemo
  version: "2.4.1"
target:
  os: "windows"
  arch: "x64"
runtime:
  distribution: "Approved JDK vendor"
  version: "Exact Java update version"
tooling:
  jpackage_version: "Recorded build JDK"
dependencies:
  sbom: "release-sbom.json"
security:
  signed: true
integrity:
  sha256: "Artifact checksum"
~~~

Các giá trị là minh họa. Release thật cần checksum/version chính xác; không ghi secret.

### 20.2. License và redistribution

Quyền phân phối JDK runtime, JavaFX modules và third-party libraries phụ thuộc license của thành phần và vendor cụ thể. Trước khi phát hành:

- Kiểm tra giấy phép và redistribution terms.
- Lưu required license notices.
- Kiểm tra native dependencies.
- Lập SBOM.
- Theo dõi CVEs và JDK security updates.

Công cụ `jpackage` chạy được không có nghĩa tự xử lý nghĩa vụ giấy phép.

## 21. Pipeline build đa hệ điều hành

Một pipeline điển hình:

~~~mermaid
flowchart TD
    A["Tag release và khóa dependency"] --> B["Build + unit/integration tests"]
    B --> C["Chuẩn bị JARs, resources, icons"]
    C --> D{"Platform target"}
    D --> E["Windows build agent"]
    D --> F["macOS build agent"]
    D --> G["Linux build agent"]
    E --> H["App image + MSI/EXE"]
    F --> I["App bundle + DMG/PKG"]
    G --> J["App image + DEB/RPM"]
    H --> K["Test + code sign/validate"]
    I --> K
    J --> K
    K --> L["Checksums, SBOM, release manifest"]
    L --> M["Staged release/rollout"]
~~~

### 21.1. Những phần dùng chung

- Mã Java.
- Unit tests.
- Dependency versions/locks.
- Business integration tests.
- Default app metadata.
- Release notes.
- Security scanning.
- Test data.

### 21.2. Những phần riêng theo OS

- Installer creation tools.
- Icon formats.
- Native libraries/JavaFX JMODs.
- Signing/notarization.
- Linux package dependencies.
- File associations/shortcuts.
- Target architecture.
- GUI end-user tests.

Không nên chỉ thử Linux rồi công bố Windows/macOS supported.

### 21.3. Build reproducibility

Ghi version JDK/jpackage, OS build image, target architecture, dependency checksums, build commit và signing stage. Native installer thường có timestamps/metadata, nên **byte-for-byte reproducibility** có thể cần thêm cấu hình ngoài việc khóa Java dependencies.

Mục tiêu tối thiểu là có thể tái tạo một release từ danh sách đầu vào và công cụ được phê duyệt.

## 22. UI regression khi đổi bundled JDK

Mã GUI vẫn compile nhưng hành vi trên desktop có thể đổi do runtime mới:

- Font fallback và shaping của tiếng Việt.
- High-DPI scaling.
- Multiple monitors.
- Input Method Editor.
- Theme/look-and-feel.
- File dialog.
- Printing.
- Clipboard/drag-and-drop.
- JavaFX rendering.
- Default charset và locale.
- Timezone/TZDB.
- TLS/truststore khi kết nối backend.
- Native integration.

Vì vậy, một phép thử `main()` không ném exception chưa đủ.

### 22.1. File cũ và charset

Ứng dụng Java cũ có thể ghi config/CSV bằng default charset trên Windows. Khi bundled runtime mới dùng quy tắc charset khác, đọc file cũ có thể tạo ký tự lỗi.

Phải xác định **charset thực của dữ liệu lịch sử**, chuyển đổi bằng cách có kiểm chứng và dùng charset tường minh cho dữ liệu mới.

### 22.2. TLS và API backend

Nâng JDK runtime có thể thay truststore và các thuật toán TLS bị hạn chế. Nếu desktop app mất kết nối backend, cần phân biệt lỗi network/proxy, server certificate, TLS policy và app packaging. Không tắt kiểm tra certificate để chữa lỗi nhanh.

## 23. Tình huống migration từ Java 8 và script sang jpackage

Giả sử một ứng dụng bán hàng nội bộ:

- Được biên dịch bằng Java 8.
- Chạy qua `run.bat`.
- Yêu cầu user tự cài JRE.
- Dùng Swing, JDBC và một PDF library.
- Lưu `settings.properties` cạnh file JAR.
- Phân phối bản mới bằng cách copy đè JAR.

Mục tiêu: dùng JDK mới hơn, có installer theo OS và runtime đi kèm.

### Bước 1 — Chụp baseline

Ghi JDK hiện tại, runtime dependencies, native libraries, startup options, lưu trữ user data và danh sách OS/CPU được hỗ trợ.

### Bước 2 — Nâng code/dependencies

Kiểm tra driver, TLS, logging, PDF library, charset và UI behavior trên JDK target. Không gộp đổi toàn bộ UI framework nếu mục tiêu chỉ là packaging.

### Bước 3 — Chuẩn hóa application input

Tạo main JAR có entrypoint, copy runtime dependencies/resources và quản lý versions theo build tool.

### Bước 4 — Tạo app image

Chạy `jpackage --type app-image`, thử launcher trên máy sạch. Nếu runtime image được tối giản, test cả JDBC, PDF printing và các tính năng dùng reflection.

### Bước 5 — Chuyển mutable config

Di chuyển dữ liệu khỏi install directory sang per-user location; có migration/backup cho user data cũ.

### Bước 6 — Tạo installer

Build Windows/macOS/Linux trên host phù hợp, chuẩn bị icon, package identifiers và ký theo policy.

### Bước 7 — Thử nâng cấp

Cài bản cũ, tạo dữ liệu, nâng lên bản mới, kiểm tra config và documents còn nguyên. Nếu rollback có thể xảy ra, kiểm tra backward compatibility của dữ liệu.

### Bước 8 — Phát hành

Kèm checksum, release manifest, Java runtime version, supported OS matrix và hướng dẫn hỗ trợ/gỡ cài đặt.

## 24. Chẩn đoán lỗi thường gặp

| Triệu chứng | Khả năng | Hướng xử lý |
|---|---|---|
| `jpackage: command not found` | Tool không có trong JDK/PATH | Xác nhận JDK version và đường dẫn |
| `Unsupported package type` | Chọn installer format sai OS/build | `jpackage --help` trên host |
| Windows installer build lỗi | WiX/toolchain thiếu hoặc lệch | Đọc requirement đúng JDK |
| Launcher không tìm main class | JAR/module/entrypoint sai | Kiểm tra `--main-jar`, `--module`, manifest |
| `NoClassDefFoundError` | Runtime dependency/module thiếu | Input dir, classpath, jlink runtime |
| `ServiceConfigurationError` | Provider/SPI bị thiếu | Service descriptors, module resolution |
| `InaccessibleObjectException` | JPMS reflection | `opens` và framework support |
| JavaFX native error | OS/architecture dependency không khớp | Platform-specific JavaFX libs |
| App chạy IDE nhưng không chạy app image | Dependency môi trường ẩn | Test trên máy sạch, inspect output |
| Không ghi được config | App ghi vào thư mục cài | Dùng per-user writable dir |
| Unicode bị lỗi | Charset/font | Xác định raw bytes và font fallback |
| Windows cảnh báo | Signing/reputation | Kiểm tra code-signing policy |
| macOS chặn | Signing/notarization | Kiểm tra Gatekeeper và release process |
| Upgrade tạo bản thứ hai | Identity/version mismatch | Kiểm tra installer metadata |
| Linux không nạp thư viện | ABI/system deps thiếu | Test distro/architecture và native libs |
| Uninstall mất dữ liệu user | Lưu data ở install directory | Sửa data location và migration |

### 24.1. Phân tầng lỗi để tránh chữa sai

- **Build/compile:** lỗi source, classpath, JDK toolchain.
- **Packaging:** thiếu công cụ installer, icon, version metadata.
- **Launcher:** sai main class/module hoặc JVM options.
- **Runtime:** thiếu module, JAR, provider, native lib.
- **OS trust:** signing, notarization, permissions.
- **Upgrade:** package identity, data migration, update process.

Đừng thêm JVM flags hoặc copy JAR ngẫu nhiên khi lỗi thực tế là WiX hoặc OS signing.

## 25. Ma trận kiểm thử release

| Trục | Kịch bản | Xác minh |
|---|---|---|
| OS | Các Windows/macOS/Linux được công bố | Install và launcher |
| CPU | x64/ARM64 được hỗ trợ | Runtime và native libs đúng |
| Runtime | Bundled JDK phiên bản mục tiêu | Khởi động, đủ modules |
| UI | Swing/JavaFX | Rendering, keyboard, DPI |
| Permissions | Standard user | Cấu hình/log writable |
| Charset | Tiếng Việt/Unicode | Không lỗi dữ liệu |
| Network | Online/offline, TLS | Kết nối và error handling |
| Local data | Có dữ liệu từ bản cũ | Upgrade giữ dữ liệu |
| File association | Double-click file | App mở đúng tài liệu |
| Signing | Artifact tải từ kênh thật | OS trust policy |
| Native integration | Printing/device/JNI | Chức năng thật |
| Uninstall | Gỡ hoàn toàn | Theo policy, không mất user documents |
| Clean machine | Không có system JDK | Bundled runtime hoạt động |

### 25.1. Kiểm thử theo chu trình người dùng

1. Tải installer từ distribution channel.
2. Xác thực file theo policy.
3. Cài với quyền người dùng thực.
4. Mở từ OS launcher/menu.
5. Dùng chức năng quan trọng.
6. Đóng/mở lại.
7. Nâng từ phiên bản cũ.
8. Kiểm tra dữ liệu.
9. Gỡ cài.
10. Kiểm tra file associations/shortcuts.

Một ứng dụng chạy từ terminal developer không thay thế được chu trình này.

## 26. Sai lầm thường gặp

### 26.1. “jpackage biến ứng dụng thành mã máy độc lập JVM”

Không đúng. Runtime Java thường được đóng cùng ứng dụng.

### 26.2. “Bundled Java nghĩa là không cần dependency nào của OS”

Sai. Native libraries, system graphics/fonts và OS ABI vẫn quan trọng.

### 26.3. “Có jpackage thì mọi JDK đều tự có JavaFX”

Sai. JavaFX cần dependency và native runtime phù hợp.

### 26.4. “Dùng một build host tạo mọi installer”

Không phải mô hình native packaging thông thường. Cần OS-specific builds.

### 26.5. “Chạy được app image thì installer chắc chắn ổn”

Không đủ. Signing, permissions, shortcuts, file associations và upgrades cần test riêng.

### 26.6. “Ứng dụng desktop ghi config trong thư mục cài là bình thường”

Dễ hỏng permissions và dữ liệu khi upgrade/uninstall.

### 26.7. “Có MSI/DMG thì tự cập nhật được”

Không. `jpackage` không cung cấp hệ thống auto-update đa nền tảng hoàn chỉnh.

### 26.8. “Chỉ cần đổi app version để cài đè”

Cần package identity và installer upgrade metadata hợp lệ.

### 26.9. “Java update trên máy user tự vá runtime của app”

Không chắc khi app mang bundled runtime riêng.

### 26.10. “JDK runtime image càng nhỏ càng tốt”

Image quá nhỏ có thể thiếu dynamic modules/providers.

### 26.11. “Chỉ cần test Windows/macOS ở IDE”

Không đủ; phải chạy artifact trên máy sạch và test cài đặt.

### 26.12. “Tắt Gatekeeper/SmartScreen là cách xử lý lỗi ký”

Không phải phương án phân phối an toàn.

### 26.13. “Mọi OS dùng chung một icon file”

Sai. Icon formats/conventions khác nhau.

### 26.14. “Copy GC flags Java 8 sang bundled JDK mới”

Có thể làm launcher không khởi động do option đã deprecated/removed.

### 26.15. “jpackage tự quản lý license/SBOM”

Không. Đây là trách nhiệm riêng của release process.

## 27. Checklist trước khi publish

### Application

- [ ] Main class hoặc module được xác định rõ.
- [ ] Runtime JARs/resources đã tập hợp đầy đủ.
- [ ] App chạy ngoài IDE.
- [ ] JavaFX modules/native libs đúng platform nếu dùng.
- [ ] Không dùng paths tương đối với project root ở runtime.
- [ ] Có log khởi động phù hợp và không chứa secrets.

### Runtime

- [ ] `jpackage` JDK version được ghi lại.
- [ ] Runtime image/JDK update được duyệt.
- [ ] Custom modules/providers đủ cho các workflows.
- [ ] JVM options tương thích JDK mới.
- [ ] License và redistribution conditions đã được xem xét.
- [ ] Bundled runtime được thử khi máy không có system JDK.

### Installer

- [ ] Tạo app image và chạy launcher thành công.
- [ ] Tạo gói native đúng OS/architecture.
- [ ] Biểu tượng đúng format.
- [ ] Metadata/identifier/version ổn định.
- [ ] WiX/OS packaging tools đúng phiên bản nếu cần.
- [ ] Signing/notarization theo kênh phát hành.
- [ ] Shortcut/menu/file associations được kiểm tra.
- [ ] Cài và gỡ với quyền đúng policy.

### Data và update

- [ ] Config/log/user documents không nằm trong install dir.
- [ ] Nâng cấp giữ lại dữ liệu.
- [ ] Dữ liệu cũ có migration/backup khi đổi format.
- [ ] Update source được xác thực và kiểm tra integrity.
- [ ] Có rollback phù hợp với dữ liệu và installer.
- [ ] Ghi runtime version, checksum và SBOM khi cần.

### Desktop QA

- [ ] Test OS/CPU matrix thực tế.
- [ ] Test Unicode, tiếng Việt, fonts/DPI.
- [ ] Test offline/network/TLS.
- [ ] Test printing/JNI/device integration khi dùng.
- [ ] Test startup ở user account bình thường.
- [ ] Test clean install và upgrade.
- [ ] Test uninstall và leftover files theo policy.
- [ ] Có release notes và support diagnostics.

## Kết luận

`jpackage` giúp chuyển ứng dụng Java desktop từ mô hình phát hành JAR phụ thuộc JRE hệ thống sang **application image và native installer mang Java runtime riêng**. Nó hỗ trợ launcher và packaging trên Windows, macOS, Linux; nhưng một bản build thành công chưa bảo đảm ứng dụng chạy đúng trên mọi máy khách.

Chiến lược migration đáng tin cậy là: **xác định main application và dependencies → tạo app image → kiểm chứng runtime modules/JavaFX/native libraries → tạo installer trên đúng OS/CPU → ký và xác thực → thử install, upgrade, uninstall, user-data preservation → phát hành kèm runtime version, checksum và kế hoạch cập nhật**. Khi coi packaging là một phần của tương thích môi trường, nhóm phát triển có thể nâng JDK mà vẫn giữ trải nghiệm desktop ổn định, an toàn và dễ hỗ trợ.

