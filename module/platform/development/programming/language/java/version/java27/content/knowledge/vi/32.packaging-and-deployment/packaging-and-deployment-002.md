# Đóng gói ứng dụng desktop bằng jpackage trong Java 27

Ứng dụng Java desktop có thể chạy trong IDE nhưng chưa tiện phân phối cho người dùng cuối. Người dùng thường cần **launcher**, biểu tượng, bộ cài đặt có thể gỡ bỏ và một **Java runtime đi kèm**, thay vì phải cài JDK rồi chạy lệnh `java -jar`.

`jpackage` là công cụ chính thức trong JDK 27 để tạo **application image** và **native installer** từ ứng dụng non-modular (JAR/class path) hoặc modular (JPMS). Công cụ này là tính năng ổn định từ JDK 16, không cần `--enable-preview`. Bài thuộc chương **Đóng gói và triển khai** của module **JAVA_VERSION_JAVA27**, tập trung vào cách làm hiện hành.

> **jpackage không tự biên dịch mã Java thành native machine code.** Launcher của bộ cài là chương trình native theo OS, còn ứng dụng Java vẫn được thực thi trên JVM trong runtime được đóng kèm.

## 1. JAR, application image và installer

| Hiện vật | Bên trong | Mục đích |
| --- | --- | --- |
| **JAR** | Bytecode, tài nguyên, manifest; có thể cần dependency JAR khác | Chạy bằng Java launcher trong môi trường có runtime |
| **Application image** | Native launcher, application JAR/modules, Java runtime | Kiểm thử bản phân phối trước khi tạo bộ cài |
| **Installer** | Gói cài đặt từ image theo chuẩn hệ điều hành | Trải nghiệm cài/gỡ, shortcut, metadata nâng cấp |

```text
Source + dependencies
       |
  javac / Gradle / Maven
       |
   JAR hoặc modules
       |
     jpackage
       |
  jlink tự tạo runtime
     HOẶC --runtime-image
       |
  app-image (launcher + JVM + app)
       |
     smoke test
       |
  Windows / macOS / Linux installer
       |
  ký số, kiểm thử cài-gỡ, phát hành
```

**Không dùng jpackage để thay bước build source.** Trước tiên cần có JAR/modular JAR và toàn bộ runtime dependencies.

### 1.1. Công cụ nào làm việc gì?

| Công cụ | Việc chính | Không tự làm |
| --- | --- | --- |
| `javac` | Biên dịch source ra class | Không tạo installer |
| `jar` | Tạo JAR, manifest `Main-Class` | Không bundle runtime |
| `jdeps` | Phân tích class/module dependencies | Không tìm hết reflection và provider tải động |
| `jlink` | Tạo runtime image theo module graph | Không tạo installer desktop |
| `jpackage` | Tạo image/launcher/installer theo OS | Không cross-package qua OS |
| Gradle/Maven | Build, test và staging dependencies | Không thay smoke test package thực tế |

## 2. Nền tảng, định dạng và công cụ cần có

Theo tài liệu **Oracle Java SE 27**, `jpackage` phải tạo native package trên **nền tảng mà package sẽ chạy**.

| Máy build | `--type` installer | `--type app-image` | Điều kiện bổ sung |
| --- | --- | --- | --- |
| Windows | `exe`, `msi` | Thư mục chứa launcher `.exe` | WiX Toolset 3.0 trở lên theo hướng dẫn Oracle |
| macOS | `dmg`, `pkg` | Bundle `.app` | Xcode CLI tools cho một số tác vụ icon/signing; certificate hợp lệ nếu ký |
| Linux | `deb`, `rpm` | Thư mục có launcher trong `bin/` | `rpm-build` hoặc `fakeroot` tùy distro/loại gói |

**Không thể** chạy `jpackage --type msi` trên Linux rồi kỳ vọng có MSI hợp lệ, hoặc đóng runtime Windows vào macOS app bundle. Phân phối nhiều OS và kiến trúc (x64/ARM64) cần những runner tương ứng.

Kiểm tra công cụ đang dùng:

```text
java -version
javac -version
jar --version
jpackage --version
jpackage --help
```

`--help` cho danh sách tùy chọn theo đúng **OS hiện tại**. Lệnh `java -version` trong shell chưa chắc mô tả JDK mà Gradle/Maven/CI chọn để đóng gói; cần ghim JDK của packaging job và xác minh riêng.

## 3. Ví dụ DeskNotes: một ứng dụng Swing độc lập

Ta dùng **Swing** từ module `java.desktop` của Java 27, không thêm thư viện ngoài. Ứng dụng có ô ghi chú và nút Lưu. Cấu trúc minh họa:

```text
desktop-demo/
  src/com/example/desknote/DeskNotes.java
  build/
    classes/
    input/
    dist/
    installers/
```

### 3.1. Mã nguồn đầy đủ

Lưu ở `src/com/example/desknote/DeskNotes.java`:

```java
package com.example.desknote;

import java.awt.BorderLayout;
import java.awt.Dimension;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import javax.swing.JButton;
import javax.swing.JFrame;
import javax.swing.JOptionPane;
import javax.swing.JScrollPane;
import javax.swing.JTextArea;
import javax.swing.SwingUtilities;
import javax.swing.WindowConstants;

public final class DeskNotes {
    private DeskNotes() {}

    public static void main(String[] args) {
        SwingUtilities.invokeLater(DeskNotes::showWindow);
    }

    private static void showWindow() {
        JFrame frame = new JFrame("DeskNotes");
        JTextArea editor = new JTextArea();
        editor.setLineWrap(true);
        editor.setWrapStyleWord(true);

        JScrollPane scroll = new JScrollPane(editor);
        scroll.setPreferredSize(new Dimension(480, 280));

        // Nơi lưu chỉ nhằm minh họa, không phải vị trí chuẩn mọi OS.
        Path userData = Path.of(
                System.getProperty("user.home"), ".desknotes-demo");
        Path noteFile = userData.resolve("note.txt");

        JButton save = new JButton("Lưu ghi chú");
        save.addActionListener(event -> {
            try {
                Files.createDirectories(userData);
                Files.writeString(
                    noteFile, editor.getText(), StandardCharsets.UTF_8);
                JOptionPane.showMessageDialog(frame, "Đã lưu ghi chú");
            } catch (IOException ex) {
                JOptionPane.showMessageDialog(
                    frame, "Lỗi lưu: " + ex.getMessage(),
                    "Lỗi", JOptionPane.ERROR_MESSAGE);
            }
        });

        frame.add(scroll, BorderLayout.CENTER);
        frame.add(save, BorderLayout.SOUTH);
        frame.setDefaultCloseOperation(
                WindowConstants.EXIT_ON_CLOSE);
        frame.pack();
        frame.setLocationRelativeTo(null);
        frame.setVisible(true);
    }
}
```

**Ý nghĩa:**

- `SwingUtilities.invokeLater` giúp tạo UI trên Event Dispatch Thread.
- Lưu dữ liệu dưới thư mục người dùng, **không ghi vào thư mục cài đặt** như `Program Files` hoặc `/opt`, nơi app có thể không có quyền ghi.
- `.desknotes-demo` chỉ là vị trí demo; ứng dụng production nên dùng thư mục application data chuẩn từng OS và thêm chính sách backup/quyền.
- I/O đang nằm trên UI thread để ví dụ ngắn. Với tác vụ chậm, chuyển sang background worker để không làm treo UI.

### 3.2. Biên dịch và tạo executable JAR

Ví dụ trong **shell Linux/macOS** tại thư mục `desktop-demo`:

```sh
mkdir -p build/classes build/input build/dist build/installers

javac --release 27 -d build/classes src/com/example/desknote/DeskNotes.java

jar --create --file build/input/DeskNotes.jar \
  --main-class com.example.desknote.DeskNotes -C build/classes .
```

Trên **Windows PowerShell** có thể dùng lệnh một dòng, không cần ký tự nối dòng:

```powershell
New-Item -ItemType Directory -Force build/classes,build/input,build/dist,build/installers | Out-Null
javac --release 27 -d build/classes src/com/example/desknote/DeskNotes.java
jar --create --file build/input/DeskNotes.jar --main-class com.example.desknote.DeskNotes -C build/classes .
```

Kiểm thử JAR trước khi đóng gói:

```text
java -jar build/input/DeskNotes.jar
```

Chạy trên máy có giao diện desktop. Nếu source cần hỗ trợ Java cũ hơn, `javac` của JDK 27 có thể dùng `--release` phù hợp, **nhưng** runtime được bundle bởi jpackage là vấn đề riêng. Đừng nhầm target bytecode với JDK dùng để đóng gói.

## 4. Bước đầu tiên của jpackage: tạo app-image

Từ thư mục chứa `build/input/DeskNotes.jar`, gọi **trên OS đích**:

```text
jpackage --type app-image --name DeskNotes --app-version 1.0.0 --input build/input --main-jar DeskNotes.jar --main-class com.example.desknote.DeskNotes --dest build/dist
```

| Option | Ý nghĩa |
| --- | --- |
| `--type app-image` | Tạo image, chưa tạo installer |
| `--name` | Tên app và launcher |
| `--app-version` | Version trong metadata |
| `--input` | Thư mục chứa JAR và các files cần phân phối |
| `--main-jar` | JAR chính, tên tương đối với `--input` |
| `--main-class` | Main class, có thể bỏ khi manifest khai báo đúng |
| `--dest` | Nơi ghi kết quả |
| `--verbose` | Chế độ diagnostic khi cần kiểm tra lỗi |

`--input` có thể mang theo **mọi file trong thư mục**; không copy thư mục build tạp chứa file tạm, credentials hoặc test-only dependencies vào input.

### 4.1. Cấu trúc image điển hình

**Windows:**

```text
build/dist/DeskNotes/
  DeskNotes.exe
  app/
    DeskNotes.jar
    DeskNotes.cfg
  runtime/
```

**Linux:**

```text
build/dist/DeskNotes/
  bin/DeskNotes
  lib/app/DeskNotes.jar
  lib/app/DeskNotes.cfg
  lib/runtime/
```

**macOS:**

```text
build/dist/DeskNotes.app/
  Contents/
    Info.plist
    MacOS/DeskNotes
    app/DeskNotes.jar
    app/DeskNotes.cfg
    runtime/
```

Đường dẫn bên trong image chỉ minh họa theo cấu trúc phổ biến của Oracle. Chi tiết file cấu hình có thể thay đổi theo implementation, không nên hard-code thành API của ứng dụng.

### 4.2. Smoke test trước bộ cài

- **Windows**: chạy `build\dist\DeskNotes\DeskNotes.exe`.
- **Linux**: chạy `build/dist/DeskNotes/bin/DeskNotes`.
- **macOS**: mở `build/dist/DeskNotes.app` hoặc launcher trong bundle.

Kiểm tra cửa sổ GUI mở, nút Lưu hoạt động, file ghi chú nằm trong vùng dữ liệu người dùng và ứng dụng khởi chạy được **không cần cài JDK toàn cục**. Trong Linux CI headless cần môi trường desktop/display phù hợp mới chạy smoke test Swing được.

## 5. Tạo installer native từ image đã kiểm thử

Có thể tạo native installer từ `--app-image`:

```text
# Chạy chỉ trên Windows có WiX
jpackage --type msi --name DeskNotes --app-image build/dist/DeskNotes --dest build/installers

# Chạy chỉ trên macOS
jpackage --type dmg --name DeskNotes --app-image build/dist/DeskNotes.app --dest build/installers

# Chạy chỉ trên Linux có công cụ DEB
jpackage --type deb --name DeskNotes --app-image build/dist/DeskNotes --dest build/installers
```

Đây là **ba phương án độc lập**. Windows cũng hỗ trợ `exe`, macOS hỗ trợ `pkg` và Linux RPM-based hỗ trợ `rpm`.

Có thể tạo installer trực tiếp từ JAR, ví dụ **trên Windows**:

```text
jpackage --type exe --name DeskNotes --app-version 1.0.0 --input build/input --main-jar DeskNotes.jar --main-class com.example.desknote.DeskNotes --dest build/installers --win-menu --win-shortcut
```

Nếu không đặt `--type`, jpackage chọn định dạng mặc định phụ thuộc hệ điều hành, ví dụ Windows thường là `exe` và macOS là `dmg`. **CI nên luôn chỉ định tường minh định dạng, tên, version và output** để tránh sai khác môi trường.

App-image có thể chạy trực tiếp nhưng không tự bảo đảm chức năng installer như nâng cấp, shortcut, cài/gỡ hoặc code signing. Vì vậy, kiểm thử image **chưa đủ** để xác nhận bộ cài thành công.

## 6. Metadata, icon và tùy chọn cài đặt

Ví dụ dành riêng Windows, giả định có file `branding/DeskNotes.ico`:

```text
jpackage --type msi --name DeskNotes --app-version 1.2.0 --vendor "Example Studio" --description "Ứng dụng ghi chú" --icon branding/DeskNotes.ico --input build/input --main-jar DeskNotes.jar --main-class com.example.desknote.DeskNotes --dest build/installers --win-menu --win-shortcut
```

Các định dạng icon thông dụng:

| OS | Định dạng icon | Lưu ý |
| --- | --- | --- |
| Windows | `.ico` | Hỗ trợ nhiều kích cỡ |
| macOS | `.icns` | Phù hợp ứng dụng `.app` |
| Linux | `.png` | Desktop launcher/shortcut |

`--icon` không tự chuyển SVG tùy ý thành icon chuẩn mọi OS.

| Option | Công dụng |
| --- | --- |
| `--license-file` | Tệp giấy phép cho bộ cài theo khả năng từng platform |
| `--install-dir` | Vị trí/nhánh cài đặt theo semantics OS |
| `--win-menu`, `--win-shortcut` | Tích hợp Start Menu, desktop shortcut |
| `--win-per-user-install` | Cài đặt cấp user trên Windows |
| `--win-dir-chooser` | Chọn thư mục cài khi installer hỗ trợ |
| `--linux-shortcut` | Tạo desktop shortcut trên Linux |
| `--mac-package-identifier` | Bundle identity, ví dụ `com.example.desknote` |
| `--mac-package-name` | Tên ứng dụng trên macOS |
| `--app-version` | Version của application/package |

Không copy option chỉ có trên Windows sang Linux/macOS. Khi dùng một app-image có sẵn, một số metadata/launcher option phải được quyết định **ngay lúc tạo image**, không phải sửa tùy ý ở giai đoạn installer.

### 6.1. File association

Nếu app mở file `.dnote`, tạo `file-association.properties`:

```properties
extension=dnote
mime-type=application/x-desknotes
description=DeskNotes Document
```

Khi tạo installer, thêm:

```text
--file-associations file-association.properties
```

Property được hỗ trợ gồm `extension`, `mime-type`, `description` và `icon`. Association chỉ đưa đường dẫn file tới launcher; ứng dụng còn phải xử lý input trong `main(String[] args)`, kiểm tra quyền truy cập, kích thước file và path traversal.

### 6.2. JVM options và launcher phụ

`--java-options` truyền tham số cho JVM; `--arguments` truyền tham số cho main class. Ví dụ:

```text
jpackage --type app-image --name DeskNotes --input build/input --main-jar DeskNotes.jar --main-class com.example.desknote.DeskNotes --java-options "-Ddesknotes.mode=desktop" --dest build/dist
```

Để thêm launcher phụ, có thể tạo file `diagnostics.properties`:

```properties
main-jar=DeskNotes.jar
main-class=com.example.desknote.DeskNotes
description=Diagnostic launcher
java-options=-Ddesknotes.diagnostic=true
```

Rồi dùng:

```text
--add-launcher DeskNotesDiagnostics=diagnostics.properties
```

Đây là ví dụ cấu hình: bản DeskNotes chưa xử lý diagnostic property. **Không lưu password/token/API key** trong launcher config, vì các giá trị có thể bị đọc từ package.

## 7. jlink và runtime đi kèm

Nếu không có `--runtime-image`, jpackage sử dụng `jlink` tạo runtime. Runtime mặc định thường bỏ những thành phần của **developer JDK** như một số command, debug symbols, man pages và header files.

### 7.1. Tự dựng runtime cho Swing

Từ JDK 27 đang chạy trên OS mục tiêu:

```text
jlink --add-modules java.desktop --strip-debug --no-header-files --no-man-pages --output build/desknote-runtime
```

Sau đó dùng:

```text
jpackage --type app-image --name DeskNotes --input build/input --main-jar DeskNotes.jar --main-class com.example.desknote.DeskNotes --runtime-image build/desknote-runtime --dest build/dist
```

Module `java.desktop` kéo theo những module phụ thuộc theo module graph. Nhưng **ứng dụng thật** có thể cần module/provider tải động, không suy ra rằng runtime tối giản chỉ có module được phát hiện qua static analysis là đã đủ.

Để phân tích:

```text
jdeps --print-module-deps build/input/DeskNotes.jar
```

`jdeps` không bảo đảm tìm hết module dùng qua `ServiceLoader`, reflection hoặc native integration. Test image trên các luồng nghiệp vụ đại diện trước khi quyết định runtime cuối.

### 7.2. JDK 25+ thay đổi service binding

Trong Java 27, `jpackage` **không tự đưa service bindings** vào runtime từ JDK 25 trở đi. Nếu thật sự cần service provider modules, có thể thêm `--bind-services` bằng `--jlink-options`:

```text
jpackage --type app-image --name DeskNotes --input build/input --main-jar DeskNotes.jar --main-class com.example.desknote.DeskNotes --jlink-options "--strip-native-commands --strip-debug --no-man-pages --no-header-files --bind-services" --dest build/dist
```

Khi tự khai báo `--jlink-options`, hãy liệt kê **các tùy chọn strip còn muốn dùng**; không tự giả định default vẫn được cộng lại. `--bind-services` có thể thêm provider modules và tăng kích thước runtime, chỉ bật khi cần thiết.

## 8. Ứng dụng modular theo JPMS

Nếu dự án dùng `module-info.java`:

```java
module com.example.desknote {
    requires java.desktop;
}
```

Với **modular JAR đã được build** trong `build/mods`:

```text
jpackage --type app-image --name DeskNotes --module-path build/mods --module com.example.desknote/com.example.desknote.DeskNotes --dest build/dist
```

Lệnh này áp dụng cho artifact modular; phần 3 tạo non-modular JAR nên không trực tiếp dùng chung. Khác biệt chính:

| Non-modular | Modular |
| --- | --- |
| `--input` và `--main-jar` | `--module-path` và `--module` |
| `--main-class` khi cần | `--module moduleName[/mainClass]` |
| Class path | Module graph JPMS |
| Runtime default cho classpath app | Runtime theo module dependencies |

Không được kết hợp `--main-jar` với `--module`. Danh sách đường dẫn trong `--module-path` dùng phân cách theo OS (`:` trên Unix, `;` trên Windows).

## 9. Runtime dependencies và tài nguyên

`jpackage` **không tự tải thư viện Gradle/Maven** chỉ vì chúng được khai báo trong build files. Nếu ứng dụng dùng thư viện ngoài, staging input phải chứa đủ JARs/files cần cho runtime:

```text
build/input/
  DeskNotes.jar
  json-library.jar
  database-driver.jar
  icons/
    app.png
```

IDE có thể chạy nhờ classpath tự động thêm dependency, trong khi app-image thiếu JAR dẫn tới `ClassNotFoundException` hoặc `NoClassDefFoundError`. Dùng build task để tạo distribution input **sạch, đúng runtime classpath**, không copy lẫn test dependencies hoặc secrets.

Không dựa vào current working directory `"."` khi ứng dụng được khởi động từ Start Menu/icon. Dùng resource loading qua `getResourceAsStream` cho assets trong JAR, và **application data directory** của OS cho settings, cache, local database và log.

## 10. JavaFX và native libraries

`jpackage` cũng đóng gói được JavaFX, nhưng **JavaFX không được bundle sẵn trong JDK 27**. Ứng dụng JavaFX cần các JavaFX modules/JARs và **native libraries phù hợp với OS/CPU**. Các chương trình Swing/AWT sử dụng `java.desktop` sẵn trong Java SE, nhưng vẫn phải kiểm tra display, font và đồ họa trên máy đích.

| Loại ứng dụng | Cần đóng gói/kiểm tra |
| --- | --- |
| Swing/AWT | `java.desktop`, font, icon, graphics, desktop environment |
| JavaFX | JavaFX modules, dependencies, thư viện native theo OS/architecture |
| JNI/JNA | `.dll`, `.so`, `.dylib`, khả năng load, hệ điều hành và kiến trúc |
| Embedded browser/media | Runtime/native engine, codec, GPU và giấy phép |
| Custom fonts/assets | Resource files và giấy phép sử dụng |

**Không** chỉ copy một thư viện JavaFX dành cho Windows vào app-image Linux. Kể cả classpath hợp lệ, launcher có thể lỗi `UnsatisfiedLinkError` hoặc lỗi khởi tạo GUI do thiếu thư viện native.

### 10.1. Kiểm thử runtime tối giản

Khi dùng `jdeps`/`jlink`:

1. Chạy **launcher từ image** thay vì chỉ chạy JAR trên JDK đầy đủ.
2. Thử cả các tính năng ít gặp: in ấn, export, TLS, font, locale và mở file.
3. Kiểm tra exception liên quan thiếu module/provider hoặc thư viện native.
4. Thêm modules hoặc `--bind-services` khi có bằng chứng cần thiết.
5. Đo lại kích thước và thời gian khởi động, không giảm runtime tới mức hỏng tính năng.

## 11. Chẩn đoán launcher và lỗi startup

Nếu ứng dụng chạy trong IDE nhưng không chạy khi click icon, có thể vì **entry point**, dependencies, working directory, custom runtime, native libraries hoặc chính sách bảo mật của OS.

### 11.1. Chạy launcher trong terminal

- Windows: chạy file `DeskNotes.exe` trong terminal; với build chẩn đoán có thể dùng `--win-console` để mở console. Flag này **chỉ dành cho Windows**.
- Linux: chạy launcher trong thư mục `bin` để xem stderr/log.
- macOS: chạy launcher trong `Contents/MacOS` hoặc mở bundle, kiểm tra logs, Gatekeeper và code signature.

`--win-console` không phải flag dùng chung trên macOS/Linux; cũng không nên để console chẩn đoán hiện với mọi người dùng nếu ứng dụng là GUI thông thường.

### 11.2. Đừng ghi log vào thư mục cài đặt

Ứng dụng phải dùng một thư mục log **có quyền ghi cho người dùng**, không giả định có quyền ghi ở `Program Files`, `/Applications` hay `/opt`. Giới hạn file log và giữ nội dung không có secret. Với lỗi UI, hiển thị thông báo ngắn gọn, còn stack trace được ghi có redaction nếu policy cho phép.

**Không** nhúng password, API key hoặc signing credentials vào `--java-options` hoặc launcher config; những giá trị này có thể đọc được từ package.

## 12. Ký số và phát hành đáng tin cậy

### 12.1. macOS

Trên macOS, `jpackage` hỗ trợ các option:

```text
--mac-sign
--mac-signing-key-user-name <signing-identity>
--mac-package-identifier com.example.desknote
```

Phải có signing identity hợp lệ trong keychain và Xcode command-line tools theo yêu cầu. **Ký package không tự đồng nghĩa đã notarize**. Trong quy trình phân phối macOS phù hợp, thường cần:

```text
Build app-image
    -> Smoke test
    -> Sign bằng certificate phù hợp
    -> Create DMG/PKG
    -> Notarize theo quy định Apple
    -> Verify signature / Gatekeeper / staple nếu cần
    -> Publish
```

Sử dụng hướng dẫn Apple hiện hành cho `codesign`, `notarytool`, `stapler`. Không đưa private key hay mật khẩu ký số vào source repo, log CI hoặc artifacts public.

### 12.2. Windows

`jpackage` tạo `.exe`/`.msi` nhưng **không dùng `--mac-sign`** để ký Windows. Dùng code-signing certificate của đơn vị phát hành và công cụ Windows phù hợp, ví dụ `signtool`; kiểm tra publisher, signature, timestamp và phản ứng của hệ điều hành.

### 12.3. Linux

Với `.deb`/`.rpm`, kiểm tra package metadata, dependency, quyền file và cơ chế trust của package manager/repository. Một gói tạo thành công không tự bảo đảm đã ký số hay được hệ điều hành tin cậy.

## 13. Update, version và Java runtime đã bundle

`--app-version` chỉ quyết định metadata version, **không tự cung cấp hệ thống auto-update**. Khi phát hành bản `1.0.0` rồi `1.0.1`, cần giữ danh tính ứng dụng ổn định.

| Nền tảng | Cần giữ nhất quán |
| --- | --- |
| Windows | Package identity, tên và metadata nâng cấp; `--win-upgrade-uuid` theo contract của installer |
| macOS | `--mac-package-identifier`, signing identity, update policy |
| Linux | Package name, version/release, repository metadata |

Nếu đổi identity không chủ đích, bản mới có thể bị cài **song song** như một app khác.

### 13.1. Người dùng nâng JDK toàn cục không vá runtime trong image

Application image thường chứa **một Java runtime riêng**. Việc người dùng cài bản vá Java mới trên máy **không** tự thay runtime đó.

Khi JDK có bản vá bảo mật:

1. Nâng JDK dùng ở packaging runner và kiểm tra version/build.
2. Tạo lại runtime image, app-image và native installer.
3. Chạy regression tests, gồm những tính năng dùng module/provider tải động.
4. Ký số lại artifact, tạo checksums và phát hành bản update.
5. Có rollback và giữ dữ liệu người dùng theo chính sách.

Không đánh giá bảo mật của ứng dụng chỉ qua source code hoặc `app-version`; runtime đã bundle cũng có vòng đời bản vá.

### 13.2. Tách dữ liệu người dùng khỏi install files

| Loại | Nơi lưu | Khi update/uninstall |
| --- | --- | --- |
| JAR, launcher, runtime | Thư mục installation | Installer có quyền thay thế |
| Notes, settings, local DB | Application data directory của user | Giữ/di chuyển theo chính sách migration |
| Logs, cache | Vùng writable có retention | Dọn an toàn theo quy định |
| Credentials | Kho bí mật phù hợp OS | Không lưu cố định trong installer |

Cách lưu note ở `user.home` trong demo giúp tránh ghi nhầm vào thư mục installation, nhưng sản phẩm cần chọn đường dẫn application-data cụ thể cho từng OS.

## 14. CI/CD phải chạy riêng trên các nền tảng

Quy trình phát hành có thể chia thành các bước:

```text
1. Checkout source, xác minh dependencies
2. Compile + unit/integration tests
3. Build JAR/modular distribution
4. Stage --input directory sạch
5. jpackage --type app-image trên runner OS đích
6. Smoke test launcher/GUI/file I/O
7. Build native installer theo OS
8. Sign/notarize/verify theo platform
9. Cài lên môi trường sạch, test launch
10. Test upgrade và uninstall, không mất user data
11. Tạo checksums, SBOM/provenance
12. Publish qua kênh tin cậy, có rollback
```

### 14.1. Ma trận kiểm thử

| CI runner | Output | Những điều cần kiểm tra |
| --- | --- | --- |
| Windows x64/ARM64 theo mục tiêu | `.exe`/`.msi` | WiX, shortcut, install/uninstall, code signing |
| macOS Intel/Apple silicon | `.app`/`.dmg`/`.pkg` | Bundle ID, signature, Gatekeeper, notarization |
| Debian/Ubuntu Linux | `.deb` | GUI, dependencies, permissions, package manager |
| RPM-based Linux | `.rpm` | Metadata, launcher, package manager |

Chạy thử Java Swing trên runner Linux **headless** có thể thất bại dù bộ cài đúng; dùng runner có GUI hoặc môi trường display-test phù hợp. Không dùng kết quả test trên một OS để khẳng định các bản phân phối còn lại cũng hoạt động.

### 14.2. Thông tin cần ghi vào release manifest

```text
Source commit / release tag
Build tool, plugin versions
JDK major/vendor/update version của packaging runner
Target Java release của source và runtime bundle
OS/CPU architecture
Dependency versions và checksums
jpackage options, icons, resource files
Package name, app version, bundle ID
Signing identity metadata (không lưu private key)
SHA-256 của artifacts, SBOM và test results
```

Không chạy signing step với secret trên pull request không tin cậy, không tự ký artifact tải từ nguồn chưa xác minh.

## 15. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Hướng khắc phục |
| --- | --- | --- |
| `jpackage: command not found` | Chưa chọn JDK có công cụ | Dùng JDK 27 và kiểm tra `jpackage --version` |
| Tạo MSI/EXE không thành công | Thiếu hoặc sai WiX | Chuẩn bị WiX phù hợp trên Windows |
| Gọi `--type dmg` trên Linux | Không hỗ trợ cross-platform packaging | Dùng macOS runner |
| App-image mở rồi thoát | Sai main class, thiếu JAR, exception | Chạy launcher trong terminal, thu log |
| `ClassNotFoundException` | Thiếu thư viện trong staging | Đưa runtime dependencies đúng vào `--input` |
| `NoClassDefFoundError` của JavaFX | Thiếu JavaFX/native components | Đóng đủ dependency theo OS/arch |
| `Module not found` | Module path/runtime image thiếu module | Dùng `jdeps`, kiểm tra `--module-path`/`--add-modules` |
| Không có service provider | Runtime không có service binding từ JDK25+ | Xem `ServiceLoader` và `--bind-services` nếu cần |
| IDE chạy nhưng launcher lỗi | CWD/resource path không đúng | Dùng resource API và user-data directory |
| Không ghi được settings | Ghi vào install directory | Chuyển dữ liệu sang nơi writable của user |
| Runtime tự tạo không chạy class Java 27 | Runtime từ JDK không tương thích | Dựng runtime từ JDK đủ mới |
| macOS cảnh báo app | Signing/notarization/Gatekeeper | Kiểm tra certificate và quy trình Apple |
| Windows cảnh báo publisher | Installer thiếu chữ ký tin cậy | Code sign và verify theo Windows |
| Update tạo ứng dụng thứ hai | Identity/package metadata thay đổi | Giữ bundle/package ID ổn định |
| Không thấy desktop shortcut | Thiếu option phù hợp | `--win-shortcut` hoặc `--linux-shortcut` |
| Bộ cài quá lớn | Quá nhiều modules/JAR/assets | Tối ưu runtime sau khi đã chạy đúng |
| Image chạy, installer không cài được | Permission hoặc package-builder issue | Test installer thực trên OS sạch |
| CI GUI test lỗi | Runner không có display | Tách logic tests và GUI smoke tests |

## 16. Những hiểu lầm cần tránh

**“jpackage tạo native executable không cần JVM.”** Không đúng: launcher native sử dụng JVM được đóng kèm để thực thi bytecode Java.

**“Một bộ cài tạo trên một OS chạy ở mọi OS.”** Không đúng: installer và runtime gắn với nền tảng, đôi khi cả CPU architecture.

**“Runtime jlink nhỏ nhất luôn tốt nhất.”** Không đúng: thiếu một module/provider có thể khiến chỉ một tính năng ít dùng bị hỏng.

**“App-image chạy thì installer chắc chắn thành công.”** Không đúng: còn quyền, shortcut, update, uninstall, metadata và signing.

**“jpackage là auto-updater.”** Không đúng: version metadata khác với cơ chế phát hành/cài bản mới.

## 17. Bài tập thực hành

### Bài tập A — Tạo app-image Java 27

1. Biên dịch `DeskNotes.java` bằng `javac --release 27`.
2. Tạo JAR có `Main-Class`; chạy thử `java -jar`.
3. Tạo `jpackage --type app-image` trên OS của mình.
4. Chạy launcher native, kiểm tra giao diện và nút Lưu.
5. Kiểm tra note được ghi ở user data, không phải thư mục installation.
6. Trên máy test phù hợp, xác minh launcher không cần Java toàn cục trên `PATH`.

### Bài tập B — So sánh runtime

Tạo hai image:

- Image A: `jpackage` tự tạo runtime.
- Image B: tự dùng `jlink --add-modules java.desktop` và truyền `--runtime-image`.

So sánh kích thước, các module cần thiết, startup, hiển thị Unicode, font và lưu file. Giải thích vì sao image nhỏ hơn không tự chứng minh an toàn/chính xác hơn.

### Bài tập C — Thử cài/gỡ và update

Trên OS đích, tạo một installer `1.0.0` rồi bản `1.0.1`. Cài trên máy/VM sạch, khởi chạy, lưu note, update và kiểm tra dữ liệu còn nguyên. Gỡ cài, xác nhận shortcut và thành phần installer được xử lý theo chính sách.

### Bài tập D — Phân tích lỗi launcher

Một JAR chạy được trong IDE nhưng app-image không mở cửa sổ. Đề xuất năm nguyên nhân thuộc các nhóm: main class, dependency JAR, module/runtime, working directory, native library, headless display hoặc quyền OS. Với mỗi nhóm hãy chỉ ra lệnh/hành động xác minh.

## 18. Checklist trước khi phát hành desktop Java 27

1. **Chọn đúng OS/CPU đích**; không giả định jpackage cross-package.
2. **Ghim JDK 27 bản vá phù hợp** và xác minh phiên bản jpackage.
3. **Build và test JAR trước** khi gọi jpackage.
4. **Dùng staging input sạch**, không mang tệp tạm/secret.
5. **Phân biệt non-modular và modular**: `--main-jar` khác `--module`.
6. **Tạo app-image và smoke test launcher** có GUI.
7. **Kiểm soát runtime**: đủ modules, providers và native libraries.
8. **Nhớ thay đổi service bindings từ JDK 25** khi thiết kế custom runtime.
9. **Không ghi dữ liệu user vào install directory**.
10. **Kiểm tra icons/metadata/shortcuts/file association**.
11. **Giữ package identity và versioning đúng** cho upgrade.
12. **Sign và verify theo OS**; notarize macOS nếu cần.
13. **Test install, update, uninstall** trên máy sạch và giữ user data.
14. **Cập nhật runtime bundle** khi JDK nhận bản vá bảo mật.
15. **Lưu checksums, SBOM và provenance** theo quy trình.
16. **Bảo vệ signing secrets** và kiểm tra nguồn artifact.
17. **Có kế hoạch rollback** khi release gặp lỗi.
18. **Không dùng flags cũ/preview không cần thiết**.
19. **Không coi build xanh là release thành công** nếu chưa kiểm thử installer thực.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 27 — The jpackage Command](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jpackage.html) — các tùy chọn hiện hành, image/installer, launcher và platform.
- [Oracle Java SE 27 — Packaging Overview](https://docs.oracle.com/en/java/javase/27/jpackage/packaging-overview.html) — yêu cầu OS, cấu trúc image, runtime và service bindings.
- [Oracle Java SE 27 — Basic Packaging](https://docs.oracle.com/en/java/javase/27/jpackage/basic-packaging.html) — đóng gói modular/non-modular và defaults.
- [Oracle Java SE 27 — Manage the Installation](https://docs.oracle.com/en/java/javase/27/jpackage/manage-installation.html) — license, shortcut, install path, menu.
- [Oracle Java SE 27 — jlink](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jlink.html) — custom runtime image và module graph.
- [Oracle Java SE 27 — jdeps](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jdeps.html) — phân tích module dependencies.
- [Oracle Java SE 27 — jar](https://docs.oracle.com/en/java/javase/27/docs/specs/man/jar.html) — tạo executable JAR.
- [Oracle Java SE 27 — javac](https://docs.oracle.com/en/java/javase/27/docs/specs/man/javac.html) — biên dịch Java và `--release`.
- [Oracle Java SE 27 — java.desktop](https://docs.oracle.com/en/java/javase/27/docs/api/java.desktop/module-summary.html) — Swing/AWT.
- [OpenJDK JEP 392 — Packaging Tool](https://openjdk.org/jeps/392) — jpackage chính thức từ JDK 16.
- [dev.java — jpackage](https://dev.java/learn/jvm/tool/jpackage/) — hướng dẫn sử dụng và các tùy chọn.
