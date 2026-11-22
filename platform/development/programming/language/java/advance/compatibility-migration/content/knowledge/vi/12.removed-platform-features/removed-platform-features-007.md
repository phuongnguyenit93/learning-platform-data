# JavaFX và các thành phần desktop được phân phối riêng

Khi nâng cấp một ứng dụng Java desktop từ JDK cũ lên JDK mới, lỗi không chỉ đến từ cú pháp hay các API bị deprecated. Một phần công nghệ giao diện từng được cài kèm một số bản phân phối JDK nay đã trở thành **thành phần phát hành độc lập**. Tình huống dễ gặp nhất là ứng dụng JavaFX trước đây biên dịch và chạy với Oracle JDK 8, nhưng sau khi chuyển lên JDK 17 hoặc JDK 21 thì compiler không tìm thấy package `javafx.*`, hoặc ứng dụng khởi động với thông báo không tìm thấy các thành phần JavaFX runtime.

Điều này không có nghĩa Java không còn hỗ trợ desktop. AWT và Swing tiếp tục nằm trong module chuẩn `java.desktop` của Java SE ở các JDK hiện đại. **JavaFX là trường hợp khác:** JavaFX/OpenJFX được phát hành và quản lý độc lập với JDK từ thế hệ JDK 11. Các công nghệ triển khai desktop cũ như Java Web Start/JNLP của bộ Java Deployment truyền thống cũng không còn được phân phối như trước trong Oracle JDK hiện đại. Những khác biệt này đòi hỏi nhóm migration phải rà soát **thư viện giao diện, native runtime, công cụ build, launcher và bộ cài**, thay vì chỉ thay biến `JAVA_HOME`.

Bài học giải thích lịch sử phân phối, cách xác định dependency cần chuyển, cấu hình Maven/Gradle, xử lý JPMS, đóng gói ứng dụng cho Windows/macOS/Linux, các lỗi thường gặp và quy trình xác nhận tương thích khi nâng JDK.

## 1. Tách ba khái niệm: JDK, UI framework và bộ phân phối ứng dụng

Một ứng dụng Java desktop thường gồm nhiều lớp:

~~~text
Mã ứng dụng nghiệp vụ
          |
          v
UI framework: JavaFX / Swing / SWT
          |
          v
Java SE APIs + Java runtime (JDK/JRE hoặc runtime image)
          |
          v
Thư viện native, toolkit đồ họa, font/media/web engine
          |
          v
Ứng dụng được đóng gói: launcher, installer, updater
          |
          v
Hệ điều hành, CPU architecture, display server
~~~

Từng lớp có vòng đời và chính sách phát hành riêng. Việc chọn JDK 21 làm runtime không tự xác định phiên bản JavaFX, và phiên bản JavaFX được chọn không tự quyết định cách ứng dụng được cài đặt trên máy người dùng.

- **JDK:** bộ công cụ và runtime Java, có compiler `javac`, trình chạy `java`, các Java SE modules và công cụ như `jlink`, `jpackage` (tùy phiên bản JDK).
- **JavaFX/OpenJFX:** tập thư viện để tạo giao diện đồ họa gồm scene graph, control, CSS, FXML, animation, media, WebView và các tích hợp khác.
- **Java desktop APIs thuộc Java SE:** ví dụ AWT, Swing, Java2D, Java Sound và image I/O trong `java.desktop`; không nên đánh đồng chúng với JavaFX.
- **Desktop distribution:** cách đưa runtime, JAR, native libraries, icon, launcher, cấu hình cập nhật và installer đến máy người dùng.
- **Công cụ phụ trợ:** ví dụ JavaFX Scene Builder, IDE integrations, profiler, launcher/updater. Chúng có thể được phát hành độc lập hoặc không còn nằm trong JDK.

Khi khảo sát hệ thống hiện hữu, cần xác định chính xác lớp nào đang là nguồn phụ thuộc. Một ứng dụng Swing thuần túy không cần thêm JavaFX chỉ vì nó là ứng dụng desktop. Ngược lại, ứng dụng có `JFXPanel` để nhúng JavaFX vào Swing vẫn cần thư viện JavaFX dù phần lớn màn hình được viết bằng Swing.

## 2. JavaFX thay đổi cách phân phối qua các đời JDK

### 2.1. Giai đoạn ứng dụng Java 8

Nhiều ứng dụng JavaFX được xây dựng bằng Oracle JDK 8 vì JavaFX có mặt trong bộ phân phối đó. Developer có thể import `javafx.application.Application`, chạy ứng dụng và dùng công cụ IDE mà không phải quản lý dependency JavaFX như một bộ thư viện Maven riêng.

Tuy nhiên, **không phải mọi bản phân phối OpenJDK 8 đều có JavaFX giống nhau**. Một số vendor đóng gói hoặc hỗ trợ JavaFX theo cách khác. Vì vậy, không nên suy luận rằng “cứ JDK 8 là có JavaFX”; phải kiểm tra đúng vendor và build đang sử dụng.

### 2.2. Java 9/10 và giai đoạn chuyển tiếp

Ở các thế hệ Java 9 và 10, việc chuyển sang hệ thống module làm xuất hiện cách nhìn theo modules đối với các thành phần desktop. Dù vậy, lịch sử đóng gói JavaFX cần xét riêng theo từng vendor. Những ứng dụng đã dùng package nội bộ của JavaFX hoặc công cụ build phụ thuộc cấu trúc thư mục JDK cũ có thể gặp rủi ro ngay trong giai đoạn chuyển tiếp này.

### 2.3. Từ JDK 11: JavaFX là dependency riêng

Bước ngoặt quan trọng đối với migration là **JavaFX không còn là thành phần đi kèm Oracle JDK 11**. OpenJFX tiếp tục được phát triển và phát hành thành các module/library riêng. Ứng dụng muốn dùng JavaFX trên JDK 11 trở lên cần bổ sung đúng artifact hoặc JavaFX SDK/runtime tương ứng.

Ví dụ:

~~~java
import javafx.application.Application;
import javafx.scene.Scene;
import javafx.scene.control.Label;
import javafx.stage.Stage;
~~~

Các import này không nằm trong các Java SE modules của một JDK 21 thông thường. Nếu dự án không khai báo JavaFX dependency hoặc module path phù hợp, chỉ nâng compiler/JDK sẽ dẫn tới lỗi build.

Khi đọc tài liệu, phải phân biệt:

- **JDK version** mà ứng dụng dùng để biên dịch/chạy.
- **OpenJFX/JavaFX version** tương thích với JDK ấy.
- **JavaFX SDK, Maven artifacts hoặc JMODs** được chọn để biên dịch/đóng gói.
- **Hệ điều hành và kiến trúc CPU** của native JavaFX libraries.
- **Phiên bản Gradle/Maven plugin** dùng để resolve và đóng gói ứng dụng.

Không mặc định JDK và JavaFX có cùng số phiên bản hoặc bắt buộc nâng theo cùng lịch. Quan trọng là nhà cung cấp xác nhận tổ hợp cụ thể được hỗ trợ.

## 3. Những thành phần desktop còn ở JDK và những thành phần cần quản lý riêng

| Thành phần | Vị trí trong kiến trúc | Điều cần kiểm tra khi nâng JDK |
|---|---|---|
| AWT | Java SE, module `java.desktop` | Desktop environment, font, rendering, headless mode |
| Swing | Java SE, module `java.desktop` | Look and feel, EDT, HiDPI, Java2D, integration |
| Java Sound và image APIs | Chủ yếu Java SE desktop APIs | Codec/format hỗ trợ, nguồn tài nguyên và native environment |
| JavaFX Controls / Graphics | OpenJFX riêng | Phiên bản JavaFX, module path, native runtime |
| JavaFX FXML | OpenJFX riêng | `javafx.fxml`, controller reflection và `opens` |
| JavaFX Media / WebView | OpenJFX riêng | Native libraries, codec/WebKit và platform support |
| JavaFX ↔ Swing bridge | OpenJFX `javafx.swing` | JDK `java.desktop`, UI threads, event delivery |
| SWT | Thư viện Eclipse riêng | Artifact OS/architecture và native bindings |
| JavaFX Scene Builder | Công cụ thiết kế giao diện phát hành riêng | Phiên bản Scene Builder và FXML tương thích |
| Java Web Start/JNLP truyền thống | Công nghệ Java Deployment cũ | Phương án thay thế launcher/updater, không kỳ vọng JDK hiện đại có `javaws` |
| `jlink` / `jpackage` | Công cụ trong các JDK hỗ trợ | Module graph và cách tạo runtime image/bộ cài |

Bảng mô tả trách nhiệm quản lý, không khẳng định mọi tính năng của từng framework đều có mặt trên mọi OS hoặc vendor. Ví dụ JavaFX Media và JavaFX Web có thể có giới hạn hoặc khác biệt native ở từng nền tảng.

### 3.1. AWT/Swing không phải thứ bị loại bỏ cùng JavaFX

Một nhầm lẫn phổ biến là “Java 11 bỏ Java desktop”. Điều đó sai. Các package như `javax.swing.*` và `java.awt.*` vẫn thuộc Java SE trong module `java.desktop`.

Ứng dụng Swing:

~~~java
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.SwingUtilities;

public class SwingExample {
    public static void main(String[] args) {
        SwingUtilities.invokeLater(() -> {
            JFrame frame = new JFrame("Desktop");
            frame.add(new JLabel("Swing vẫn thuộc java.desktop"));
            frame.setSize(400, 160);
            frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
            frame.setVisible(true);
        });
    }
}
~~~

Với named module, khai báo:

~~~java
module com.acme.swingapp {
    requires java.desktop;
}
~~~

Không cần thêm `javafx.controls` nếu ứng dụng thực sự không sử dụng JavaFX.

### 3.2. JavaFX là thư viện riêng, không phải API Java SE

JavaFX dùng namespace `javafx.*`, nhưng namespace này không đồng nghĩa nó được cung cấp bởi JDK mới. Một số bản phân phối desktop có thể đóng gói sẵn JavaFX hoặc cung cấp runtime tùy chỉnh, nhưng không được dựa vào điều đó khi xây dựng artifact portable.

Dự án nên công bố explicit JavaFX version và quản lý nó như dependency thực thụ.

## 4. Các module OpenJFX quan trọng

JavaFX được chia thành nhiều module để có thể chọn các chức năng cần dùng:

| Module JavaFX | Vai trò điển hình |
|---|---|
| `javafx.base` | Properties, bindings, collections, các tiện ích nền |
| `javafx.graphics` | Application, Stage, Scene, scene graph, animation, rendering |
| `javafx.controls` | Button, TableView, TreeView, Menu, các control dựng sẵn |
| `javafx.fxml` | Tải giao diện FXML và ánh xạ controller |
| `javafx.media` | Audio/video qua media stack được hỗ trợ |
| `javafx.web` | WebView/WebEngine và web rendering |
| `javafx.swing` | Tích hợp JavaFX với Swing như `JFXPanel`, `SwingNode` |
| `javafx.swt` | Tích hợp với SWT khi bản phân phối hỗ trợ |

Một ứng dụng dùng mỗi `Button` và `Scene` có thể chỉ khai báo `javafx.controls` cùng các phụ thuộc chuyển tiếp được module graph giải quyết. Ứng dụng dùng FXML cần `javafx.fxml`. Nếu không dùng media hoặc WebView, không nên thêm `javafx.media` / `javafx.web` chỉ vì “đủ bộ”, vì chúng có thể bổ sung native components và tăng kích thước phân phối.

Phạm vi module cần thiết phải dựa vào mã nguồn và luồng thực tế. Framework có thể sử dụng một module gián tiếp; ví dụ thư viện UI wrapper đọc FXML hoặc embedding WebView dù source chính không import trực tiếp `javafx.fxml`.

### 4.1. Các native libraries đi kèm JavaFX

Một số tính năng JavaFX sử dụng mã native để tương tác với hệ điều hành, GPU, media và web engine. Vì vậy, JavaFX artifact có thể có phần phụ thuộc theo platform/architecture.

Điểm cần xác minh:

- Windows, macOS, Linux và các nền tảng JavaFX được vendor hỗ trợ.
- Kiến trúc CPU, ví dụ x86-64 so với AArch64.
- Các native artifacts đi kèm JavaFX version tương ứng.
- Thư viện hệ thống, graphics stack và media codecs cần thiết.
- Native binaries được đóng gói thật trong bộ cài hoặc runtime image cuối.
- Các ràng buộc ký mã, notarization và chính sách bảo mật OS.

Một bản build chạy trên máy Windows developer không chứng minh đã có native libraries cho macOS hoặc Linux. Cross-platform release phải được kiểm tra trên đúng tổ hợp OS/CPU hoặc bằng pipeline tương ứng.

## 5. Kiểm kê ứng dụng desktop trước khi nâng JDK

Trước khi chọn JavaFX version, lập inventory đầy đủ:

1. **Runtime cũ:** JDK/JRE vendor, version, update, OS/architecture.
2. **UI framework:** JavaFX, Swing, AWT, SWT hay kết hợp.
3. **Module JavaFX sử dụng:** controls, fxml, media, web, swing...
4. **Các package JavaFX nội bộ:** `com.sun.javafx.*` hoặc implementation API không công khai.
5. **Thư viện bên thứ ba:** controls library, chart library, FXML utilities, CSS themes, testing library.
6. **Build:** Maven/Gradle/Ant, plugin JavaFX, compiler release, annotation processor.
7. **Launch:** lệnh `java`, IDE run configuration, `javaws`, shortcut, updater hoặc native launcher.
8. **Packaging:** JAR, fat JAR, runtime image, EXE/MSI/DMG/PKG/DEB/RPM tùy hệ thống.
9. **Native dependencies:** JavaFX native libraries, JNI, codec, font, WebKit, media.
10. **Tài nguyên:** FXML, CSS, font, ảnh, icon, file localization và file cấu hình.
11. **Thread model:** JavaFX Application Thread, Swing EDT, executor, background services.
12. **Triển khai:** auto-update, code signing, certificate, chính sách OS, quyền ghi dữ liệu.
13. **Test matrix:** máy thật, HiDPI, GPU, nhiều màn hình, locale, dark mode, accessibility.

Tạo bảng minh họa:

| Hạng mục | Hiện tại | Đích | Công việc |
|---|---|---|---|
| JDK | Oracle JDK 8 | JDK được tổ chức phê duyệt | Xác minh compatibility |
| JavaFX | Từng đi kèm JDK cũ | OpenJFX dependency riêng | Chọn version/platform |
| FXML | Resource trong JAR | Vẫn trong artifact mới | Kiểm tra `opens` và resource path |
| Installer | Script cũ hoặc Web Start | Native installer/runtime image | Thiết kế triển khai |
| Libraries | Controls library cũ | Bản hỗ trợ JDK/JavaFX đích | Nâng dependency/test |
| Media/Web | Có hoặc không | Tùy tính năng thực tế | Kiểm tra native support |

Những số phiên bản trong dự án thật phải lấy từ artifact và cấu hình đang triển khai. Không sử dụng mốc “Java 8 sang 21” làm bằng chứng tự động rằng mọi thành phần đều cần thay.

## 6. Xác định chính xác dependency JavaFX

### 6.1. Kiểm tra import và tài nguyên

Một số dấu hiệu thường gặp trong source:

~~~text
javafx.application.Application
javafx.stage.Stage
javafx.scene.Scene
javafx.scene.control.*
javafx.fxml.FXML
javafx.fxml.FXMLLoader
javafx.scene.web.WebView
javafx.scene.media.MediaPlayer
javafx.embed.swing.JFXPanel
javafx.embed.swing.SwingNode
~~~

Kiểm tra thêm:

~~~text
*.fxml
*.css
*.png / *.svg / fonts
META-INF/services/*
native binaries
launcher scripts
~~~

Không chỉ tìm import: một màn hình có thể được khai báo hoàn toàn trong FXML hoặc load động bằng tên resource. Có trường hợp JavaFX được nạp qua reflection bởi framework, khiến tìm kiếm import trực tiếp không phản ánh đầy đủ.

### 6.2. Phân biệt public API và internal API

Các package công khai được tài liệu hóa là lựa chọn ưu tiên. Nếu ứng dụng dùng:

~~~java
import com.sun.javafx.some.internal.Type;
~~~

thì mã đang phụ thuộc vào implementation detail; JDK/JavaFX version mới có thể thay đổi, đóng gói hoặc loại bỏ những class đó. Không nên chỉ thêm `--add-exports` hoặc `--add-opens` rồi xem là đã migration xong.

Hướng xử lý:

- Tìm public JavaFX API tương đương.
- Nâng thư viện đã phụ thuộc internal API lên bản hỗ trợ JavaFX mới.
- Nếu không có API thay thế, cân nhắc thay component/thiết kế.
- Nếu buộc phải có workaround tạm thời, giới hạn phạm vi, ghi rõ lý do và thời hạn loại bỏ.
- Kiểm tra binary compatibility của dependency JavaFX third-party, nhất là skin, control hoặc renderer tùy chỉnh.

## 7. Chọn đúng tổ hợp JDK, JavaFX và công cụ build

Không có một ma trận áp dụng cho mọi dự án. Tối thiểu phải ghi:

| Trục | Điều cần xác nhận |
|---|---|
| JDK feature release | Compiler và runtime version dự kiến |
| JDK vendor/update | Build, lịch hỗ trợ và bản vá |
| JavaFX version | JDK tối thiểu/được hỗ trợ, release notes |
| JavaFX modules | Chức năng thực sự cần |
| Build tool | Maven/Gradle và version hỗ trợ JDK đích |
| JavaFX build plugin | Plugin version phù hợp với build tool/JavaFX |
| OS và CPU | Native artifact và platform compatibility |
| Bộ cài | `jpackage`/`jlink`/launcher hỗ trợ hình thức phát hành |

### 7.1. Không đồng nhất JavaFX version với JDK version

Tên release JavaFX thường phản ánh chu kỳ phát hành riêng. Một JavaFX version có thể hỗ trợ một tập JDK phù hợp, nhưng không nên suy ra:

- JDK 21 bắt buộc phải dùng JavaFX 21.
- JavaFX mới nhất luôn chạy được trên JDK cũ.
- JavaFX cùng số release với JDK sẽ hoạt động trên mọi hệ điều hành.
- JavaFX dependency biên dịch được là đủ để native startup thành công.

Cần đọc release notes và yêu cầu runtime của đúng bản OpenJFX/vendor. Đặc biệt chú ý đến bản cập nhật có vá bảo mật và trạng thái hỗ trợ của các bản phát hành dài hạn nếu vendor cung cấp.

### 7.2. Chọn một cách cung cấp JavaFX rõ ràng

Các cách triển khai phổ biến:

- **Maven Central/Gradle dependencies:** dùng các module `org.openjfx` và plugin để resolve artifact phù hợp platform.
- **JavaFX SDK riêng:** chỉ định đường dẫn tới thư mục `lib` của JavaFX SDK trong lệnh chạy hoặc IDE.
- **JavaFX JMODs/runtime image:** dùng các module phù hợp để tạo runtime image với `jlink` và công cụ đóng gói.
- **Bản phân phối JavaFX hỗ trợ thương mại hoặc tùy biến:** tuân thủ tài liệu và điều khoản tương ứng.

Không trộn tùy tiện JAR từ Maven với native libraries của SDK một version khác. Điều này có thể dẫn tới lỗi linking, `UnsatisfiedLinkError` hoặc lỗi rendering khó tái hiện.

## 8. Ví dụ tạo ứng dụng JavaFX tối thiểu

Giả sử ứng dụng có class:

~~~java
package com.acme.desktop;

import javafx.application.Application;
import javafx.scene.Scene;
import javafx.scene.control.Button;
import javafx.scene.layout.StackPane;
import javafx.stage.Stage;

public final class DesktopApp extends Application {
    @Override
    public void start(Stage stage) {
        Button button = new Button("Mở báo cáo");
        button.setOnAction(event ->
                System.out.println("Đã nhấn"));

        stage.setScene(new Scene(new StackPane(button), 420, 240));
        stage.setTitle("Desktop Migration");
        stage.show();
    }

    public static void main(String[] args) {
        launch(args);
    }
}
~~~

Mục tiêu của đoạn mã là cho thấy đường dẫn thư viện và lifecycle tối thiểu. Nó sử dụng `javafx.application.Application` và `javafx.scene.control.Button`, tức cần JavaFX modules tương ứng. Trên JDK không kèm JavaFX, việc chạy `javac` mà không có JavaFX dependencies sẽ thất bại.

### 8.1. Chạy bằng JavaFX SDK ở classpath application

Với JavaFX SDK đã được tải đúng OS/CPU và đúng version hỗ trợ JDK:

~~~bash
java --module-path /path/to/javafx-sdk/lib \
     --add-modules javafx.controls \
     -cp build/classes \
     com.acme.desktop.DesktopApp
~~~

Lệnh minh họa trên Linux/macOS; trên Windows cần điều chỉnh đường dẫn và cú pháp shell. Các đường dẫn phải là thư mục chứa đúng JavaFX JARs. Với project lớn, nên để Maven/Gradle hoặc launcher quản lý classpath/module path thay vì hardcode một thư mục SDK tại máy developer.

Một thông báo kiểu “JavaFX runtime components are missing” thường báo vấn đề launch/configuration, nhưng cần kiểm tra stack trace và launch command thật trước khi kết luận duy nhất là thiếu JAR.

## 9. Cấu hình Gradle cho OpenJFX

Với Gradle và Java plugin, một cách phổ biến là sử dụng JavaFX Gradle plugin được dự án chọn và cố định phiên bản. Ví dụ cấu trúc:

~~~groovy
plugins {
    id 'application'
    id 'org.openjfx.javafxplugin' version 'PLUGIN_VERSION'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

javafx {
    version = 'COMPATIBLE_JAVAFX_VERSION'
    modules = ['javafx.controls', 'javafx.fxml']
}

application {
    mainClass = 'com.acme.desktop.DesktopApp'
}
~~~

`PLUGIN_VERSION` và `COMPATIBLE_JAVAFX_VERSION` là chỗ cần thay bằng version đã xác minh, không phải giá trị thực để copy vào production. Cấu hình trên mô tả ứng dụng **chưa có module descriptor**. Với ứng dụng modular, cần khai báo main module tương ứng và kiểm tra support của phiên bản plugin, Gradle cùng toolchain.

Ý nghĩa chính:

- `application` giúp quản lý entrypoint và task run/distribution.
- Java toolchain xác định JDK dùng để biên dịch.
- JavaFX plugin hỗ trợ quản lý các module JavaFX được chọn.
- `javafx.controls` và `javafx.fxml` được khai báo theo tính năng.
- Output build phải được chạy thử trên OS có native dependencies thích hợp.

### 9.1. Tách toolchain và target release

Dự án có thể chạy Gradle bằng một JDK, biên dịch bằng toolchain khác và đặt Java `--release` tương ứng với runtime tối thiểu. Tuy nhiên, JavaFX API không phải API Java SE được `--release` tự động cung cấp. Việc đặt `options.release = 17` không biến JavaFX thành thư viện sẵn có; vẫn cần dependency đúng JavaFX version.

Nếu biên dịch ứng dụng trên JDK 21 nhưng cần chạy ở JDK 17, phải xác minh JavaFX version được chọn có hỗ trợ runtime JDK 17, chứ không chỉ kiểm tra class file target của application. JavaFX JAR bản thân nó cũng có yêu cầu Java/classfile version và native compatibility.

## 10. Cấu hình Maven cho OpenJFX

Với Maven, thường dùng `org.openjfx` dependencies và một plugin phù hợp để chạy ứng dụng. Ví dụ phần chính của `pom.xml`:

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
</properties>

<dependencies>
    <dependency>
        <groupId>org.openjfx</groupId>
        <artifactId>javafx-controls</artifactId>
        <version>COMPATIBLE_JAVAFX_VERSION</version>
    </dependency>
    <dependency>
        <groupId>org.openjfx</groupId>
        <artifactId>javafx-fxml</artifactId>
        <version>COMPATIBLE_JAVAFX_VERSION</version>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.openjfx</groupId>
            <artifactId>javafx-maven-plugin</artifactId>
            <version>COMPATIBLE_PLUGIN_VERSION</version>
            <configuration>
                <mainClass>com.acme.desktop.DesktopApp</mainClass>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

Đoạn trên là cấu trúc minh họa, chưa phải POM hoàn chỉnh. Phiên bản JavaFX/Maven plugin cần được chọn từ tài liệu tương thích. Với modular application, cấu hình `mainClass`, module descriptor và cách Maven plugin tạo launch command cần được điều chỉnh tương ứng.

Một số dự án không dùng JavaFX Maven plugin mà khai báo dependencies rồi tự cấu hình Surefire, package và launcher. Điều đó có thể hoạt động, nhưng phải kiểm tra đủ compile classpath, runtime module path, native artifacts và bộ phân phối cuối.

### 10.1. Tránh fat JAR sai cách

Một lỗi thường gặp là gom mọi JavaFX JAR cùng native binaries vào một fat JAR bằng cơ chế shade tùy tiện. Nếu các module descriptor, service metadata, native libraries hoặc platform-specific artifacts bị xử lý sai, ứng dụng có thể build thành công nhưng lỗi khi chạy.

Không giả định rằng “một JAR duy nhất chứa mọi thứ” là cách phân phối tốt nhất cho ứng dụng JavaFX. Thường cần một runtime image hoặc application distribution với native libraries đúng platform, launcher và metadata đầy đủ.

## 11. JavaFX với JPMS: module-info.java, exports và opens

Khi ứng dụng được chuyển thành explicit named module, cần khai báo module dependencies:

~~~java
module com.acme.desktop {
    requires javafx.controls;
    requires javafx.fxml;

    exports com.acme.desktop;

    opens com.acme.desktop.ui to javafx.fxml;
}
~~~

Ý nghĩa:

- `requires javafx.controls`: ứng dụng sử dụng public APIs của JavaFX Controls và các dependencies module đi kèm.
- `requires javafx.fxml`: ứng dụng sử dụng FXML loader.
- `exports com.acme.desktop`: công khai API cần thiết của package đó tới những module đọc ứng dụng.
- `opens com.acme.desktop.ui to javafx.fxml`: cho phép FXML loader truy cập controller fields/methods trong package UI bằng reflection ở runtime.

Module descriptor phải tương ứng với package trong source và cách framework khởi tạo ứng dụng. Không tự export mọi package chỉ để tránh lỗi; trong nhiều trường hợp cần `opens` có điều kiện cho FXML, không phải `exports`.

### 11.1. Vì sao FXML thường gặp lỗi khi modularize?

FXML có thể khai báo controller và liên kết các field/method được đánh dấu `@FXML`:

~~~java
package com.acme.desktop.ui;

import javafx.fxml.FXML;
import javafx.scene.control.Label;

public final class DashboardController {
    @FXML
    private Label statusLabel;

    @FXML
    private void onRefresh() {
        statusLabel.setText("Đã cập nhật");
    }
}
~~~

FXML loader cần dùng reflection để tạo controller, inject field và gọi handler. Khi class thuộc named module, quyền truy cập reflective không còn giống lúc class ở unnamed module. Nếu package chưa `opens` tới `javafx.fxml`, quá trình load có thể thất bại bằng một `LoadException` hoặc lỗi access ở nguyên nhân bên trong.

Giải pháp ưu tiên là mở **đúng package controller**:

~~~java
opens com.acme.desktop.ui to javafx.fxml;
~~~

Không sử dụng `open module ...` chỉ vì một controller cần injection. Cũng không nên chỉ đổi field `private` thành `public` nếu điều đó làm mất encapsulation không cần thiết.

### 11.2. JavaFX Web, Media và Swing bridge trong module graph

Nếu ứng dụng dùng các thành phần này, thêm module tương ứng:

~~~java
module com.acme.desktop {
    requires javafx.controls;
    requires javafx.fxml;
    requires javafx.web;
    requires javafx.media;
    requires javafx.swing;
    requires java.desktop;
}
~~~

Đây là ví dụ cho ứng dụng có đủ các nhóm tính năng, **không phải cấu hình nên áp dụng cho mọi ứng dụng**. Với Swing bridge, `java.desktop` vẫn thuộc JDK còn `javafx.swing` thuộc OpenJFX riêng. Xác nhận dependency transitive và các yêu cầu native theo bộ phân phối đang chọn.

### 11.3. Không trộn classpath và module path tùy ý

Một ứng dụng không modular có thể nằm trên classpath và load các JavaFX named modules qua `--module-path` / `--add-modules`. Khi ứng dụng trở thành named module, cần cấu hình đúng `requires`, root modules, class loader và những thư viện chưa modularize.

Nếu một thư viện JavaFX third-party vẫn chỉ nằm trên classpath, named module không thể khai báo `requires` trực tiếp tới unnamed module. Có thể cần bridge tạm thời hoặc automatic module, nhưng phải kiểm tra module name, split packages, reflection và hành vi runtime.

## 12. Resource loading: FXML, CSS, font, ảnh

Rất nhiều lỗi khi chuyển sang JavaFX/JDK mới liên quan đến file tài nguyên chứ không phải Java code.

Cấu trúc thông dụng:

~~~text
src/main/java/com/acme/desktop/DesktopApp.java
src/main/java/com/acme/desktop/ui/DashboardController.java
src/main/resources/com/acme/desktop/ui/dashboard.fxml
src/main/resources/com/acme/desktop/styles/main.css
src/main/resources/com/acme/desktop/images/logo.png
~~~

Dùng `Class.getResource` với đường dẫn phù hợp:

~~~java
URL fxml = DesktopApp.class.getResource(
        "/com/acme/desktop/ui/dashboard.fxml");

if (fxml == null) {
    throw new IllegalStateException("Thiếu dashboard.fxml trong artifact");
}

Parent root = FXMLLoader.load(fxml);
~~~

Với CSS:

~~~java
URL css = DesktopApp.class.getResource(
        "/com/acme/desktop/styles/main.css");

if (css != null) {
    scene.getStylesheets().add(css.toExternalForm());
}
~~~

Các điểm cần kiểm tra:

- File thực sự được copy từ `src/main/resources` vào JAR hoặc runtime image.
- Đường dẫn trong `getResource` có chính xác không; `Class.getResource("/...")` khác `ClassLoader.getResource("...")` về cách hiểu dấu `/`.
- Named module có package resource bị encapsulate không.
- FXML chứa `fx:controller` tham chiếu đúng class/package hay chưa.
- CSS `@import`, URL ảnh và font có dùng đường dẫn tương đối đúng không.
- Case-sensitive file names có giống nhau trên Windows và Linux không.
- Khi dùng `jlink`/`jpackage`, resource có nằm trong image cuối không.

Không nên chuyển `URL` resource thành `File` trực tiếp. Resource ở trong JAR hoặc runtime image không nhất thiết có đường dẫn filesystem thông thường. Dùng stream hoặc API resource để đọc dữ liệu.

## 13. Vòng đời JavaFX Application và UI thread

Nâng JDK/JavaFX có thể khiến các lỗi thread vốn tiềm ẩn trở nên rõ hơn. JavaFX có **JavaFX Application Thread** chuyên xử lý scene graph và các tương tác UI liên quan. Nó khác với **Swing Event Dispatch Thread (EDT)**.

Các mốc chính của `Application`:

1. `init()`: chuẩn bị ứng dụng trước khi UI chạy.
2. `start(Stage)`: entrypoint tạo scene và hiển thị stage trên JavaFX Application Thread.
3. `stop()`: cleanup khi ứng dụng dừng theo lifecycle.

Cập nhật UI từ background thread cần chuyển tác vụ về JavaFX Application Thread:

~~~java
CompletableFuture.supplyAsync(() -> loadReport())
        .thenAccept(report ->
                Platform.runLater(() -> statusLabel.setText(report)));
~~~

Đây là ví dụ ý tưởng. Hàm `loadReport`, `statusLabel` và import chưa được định nghĩa trong đoạn rút gọn. Trong ứng dụng thật, xử lý thêm lỗi, cancellation và trường hợp Stage đã đóng trước khi callback được thực thi.

Không thực hiện I/O chậm hoặc CPU-intensive work trực tiếp trong `start`, event handler hay `Platform.runLater`, vì nó làm đóng băng giao diện. Dùng `Task`, `Service`, executor hoặc cơ chế concurrency phù hợp.

### 13.1. Kết hợp JavaFX và Swing

JavaFX hỗ trợ bridge với Swing qua các thành phần như `JFXPanel` và `SwingNode`. Nhưng hai framework có event thread khác nhau.

Ví dụ hướng cập nhật:

- Swing UI: thao tác trên EDT bằng `SwingUtilities.invokeLater`.
- JavaFX UI: thao tác trên JavaFX Application Thread bằng `Platform.runLater`.
- Khi truyền dữ liệu giữa hai UI toolkit, tránh giữ khóa đồng thời hoặc chờ đồng bộ hai event threads.

Không xem `javafx.swing` là cách hợp nhất event thread. Chuyển dependency sang JavaFX phiên bản mới cần kiểm tra deadlock, focus, keyboard input, window ownership, HiDPI và popup behavior trong các màn hình hybrid.

## 14. JavaFX Media, WebView và codec

`javafx.media` và `javafx.web` là hai nhóm đặc biệt nhạy với môi trường runtime vì có native components hoặc engine phức tạp.

### 14.1. Media

Các vấn đề có thể xuất hiện:

- Codec hoặc container format không được hỗ trợ trên một OS.
- Native media library không được đóng gói.
- Audio/video device không tồn tại trong test runner hoặc container.
- Media source dùng giao thức/đường dẫn không phù hợp.
- Thay đổi trong pipeline native, driver hoặc phụ thuộc hệ thống.

Không kết luận JavaFX Media hỗ trợ mọi codec phổ biến; cần kiểm tra danh sách format/codec được bộ JavaFX/vendor cụ thể hỗ trợ và test file thực tế.

### 14.2. WebView

`WebView` nhúng web engine. Tính năng này có thể chịu ảnh hưởng của HTML/CSS/JavaScript support, TLS/certificate, cookie/session, CORS và các thay đổi bảo mật của engine được phát hành cùng JavaFX.

Khi nâng JavaFX:

- Test trang web nội bộ thực tế, đặc biệt login, redirect, upload/download và JavaScript bridges.
- Kiểm tra WebView version/engine trong JavaFX release notes.
- Hạn chế expose Java objects nhạy cảm cho nội dung web không tin cậy.
- Test tính tương thích với proxy, CA và chính sách mạng.
- Xác nhận native WebView components có trong distribution.

WebView không phải một trình duyệt bên ngoài được cập nhật độc lập từ JavaFX JAR theo cách thông thường. Muốn nhận bản vá cho engine tích hợp, cần theo dõi và nâng bản JavaFX phù hợp.

## 15. Desktop tooling cũ: Java Web Start và Java Deployment

Một số ứng dụng Java 8 từng khởi chạy bằng Java Web Start, sử dụng file JNLP và lệnh `javaws`. Các công nghệ Java Deployment cũ (bao gồm Java Web Start/Applet deployment) không còn được Oracle JDK 11 phân phối như trước. Vì vậy, khi chuyển lên JDK hiện đại, không thể chỉ giữ nguyên lệnh `javaws application.jnlp` rồi mong launcher vẫn tồn tại.

Các lựa chọn cần đánh giá:

- **Native installer/runtime image** được tạo bằng công cụ đóng gói phù hợp.
- **Launcher/updater độc lập** do tổ chức hoặc nhà cung cấp quản lý.
- **OpenWebStart hoặc giải pháp JNLP tương đương** nếu hệ thống có yêu cầu giữ mô hình Web Start và giải pháp đó hỗ trợ ứng dụng/JDK mục tiêu.
- **Chuyển kiến trúc triển khai** nếu ứng dụng cũ phụ thuộc vào security sandbox, signed JAR hoặc quyền hạn Java Web Start đã thay đổi.

Không nên tự giả định giải pháp thay thế hỗ trợ 100% mọi extension JNLP, sandbox/security policy và hành vi cache của bản Java Web Start cũ. Cần đọc tài liệu vendor và chạy thử bằng gói phát hành thực tế.

### 15.1. Những yêu cầu ngoài mã ứng dụng

Kế hoạch chuyển launcher cần trả lời:

- Người dùng cài ứng dụng thế nào?
- Runtime Java được cài sẵn hay đóng gói cùng app?
- Ai phát hành các bản vá bảo mật JDK và JavaFX?
- Cập nhật tự động qua kênh nào?
- Cách quản lý code signing và certificate?
- Shortcut, desktop integration, file associations và protocol handlers có cần không?
- Dữ liệu cục bộ, cấu hình và cache được lưu ở thư mục nào?
- Có cần hỗ trợ cài đặt offline không?
- Làm sao rollback khi ứng dụng mới không khởi động?

Các câu hỏi này thuộc compatibility migration, không phải nhiệm vụ riêng của bộ phận release. Nếu app không thể cài hoặc tự cập nhật sau khi đổi JDK, migration vẫn chưa hoàn thành.

## 16. Đóng gói bằng jlink và jpackage

### 16.1. jlink tạo runtime image theo module graph

`jlink` có thể tạo runtime image gồm các module được chọn. Với ứng dụng JavaFX modular, một quy trình điển hình gồm:

1. Biên dịch module ứng dụng.
2. Chuẩn bị JDK modules và JavaFX JMODs phù hợp với OS/CPU.
3. Cung cấp các application modules và module dependencies cần thiết.
4. Chạy `jlink` với module path và root module đã xác định.
5. Kiểm tra application launcher, JavaFX native libraries và resource trong image cuối.

Lệnh minh họa:

~~~bash
jlink \
  --module-path "$JAVA_HOME/jmods:/path/to/javafx-jmods:build/mods" \
  --add-modules com.acme.desktop \
  --output build/runtime-image
~~~

Ví dụ sử dụng biến/đường dẫn kiểu Unix, cần điều chỉnh cho Windows và version JDK. `build/mods` phải chứa module ứng dụng đã được biên dịch phù hợp, không phải bất kỳ JAR nào được thả vào thư mục.

**Hạn chế quan trọng:** `jlink` hoạt động với đồ thị explicit modules; automatic module không thể đơn giản được link như một explicit module. Nếu phụ thuộc chưa modularize, cần xem xét thay artifact, modularize hoặc chọn quy trình đóng gói khác. Không nên giả định đặt mọi JAR vào module path là `jlink` sẽ chấp nhận.

### 16.2. jpackage tạo bộ cài hoặc application image

`jpackage` là công cụ đóng gói ứng dụng Java cho các nền tảng được hỗ trợ. Nó có thể đóng gói một ứng dụng modular hoặc non-modular theo các tùy chọn thích hợp, tạo native launcher và các dạng app image/installer tùy OS.

Lộ trình khái quát:

~~~text
Build application JAR/modules
              |
              v
Resolve JavaFX libraries + native artifacts
              |
              v
Build/choose suitable runtime image
              |
              v
Package launcher, icons, app files, metadata
              |
              v
Sign/notarize (nếu OS yêu cầu)
              |
              v
Test trên máy clean không cài JDK
~~~

Với JavaFX, phải đảm bảo runtime image hoặc app distribution **thực sự chứa JavaFX modules và native components cần thiết**. Nếu JavaFX không được bundle, bộ cài có thể chạy trên máy developer có SDK nhưng thất bại trên máy người dùng mới.

Tùy loại artifact, có thể dùng `jpackage --module ...` hoặc các tùy chọn `--input`, `--main-jar`, `--main-class` và `--runtime-image`. Không thể tạo một lệnh duy nhất dùng nguyên văn cho mọi kiểu ứng dụng và OS. Cần chọn đúng cơ chế modular/non-modular theo artifact thực tế rồi kiểm tra `jpackage --help` trên JDK dùng để đóng gói.

### 16.3. Đóng gói cho từng hệ điều hành và kiến trúc

Desktop installer thường cần được xây dựng và kiểm thử cho đúng nền tảng đích. Lưu ý:

- Windows: native launcher, MSI/EXE tùy công cụ, DPI, file associations và ký mã.
- macOS: ứng dụng bundle, architecture, code signing, notarization và entitlement khi cần.
- Linux: package hoặc app image theo hệ thống phân phối, dependencies của graphics toolkit và native media stack.
- Nhiều kiến trúc CPU: cần đúng JavaFX native libraries và runtime binaries.
- Phân phối offline: installer chứa đầy đủ runtime và resource thay vì dựa vào một JDK đã cài.

Không cung cấp cùng một bộ native libraries cho mọi OS rồi kỳ vọng Java tự chọn đúng khi đóng gói đã sai. Tách build matrix theo OS/architecture nếu artifact không thực sự portable.

## 17. Các lỗi thường gặp và hướng điều tra

| Triệu chứng | Nguyên nhân khả dĩ | Kiểm tra đầu tiên |
|---|---|---|
| `package javafx.application does not exist` | Chưa khai báo JavaFX trong compile dependencies | Maven/Gradle và compiler classpath/module path |
| `module not found: javafx.controls` | Module JavaFX không ở module path hoặc tên sai | JavaFX artifacts, launch command, module descriptor |
| Thông báo thiếu JavaFX runtime components | Launcher/runtime không cung cấp JavaFX phù hợp | Cách khởi chạy, JavaFX SDK/dependencies |
| `UnsatisfiedLinkError` | Native artifact sai hoặc thiếu | OS/architecture, JavaFX native libraries |
| `NoClassDefFoundError` liên quan JavaFX | Module/JAR thiếu, classloader hoặc linking | Stack trace gốc, version và runtime path |
| FXML `LoadException` | Resource/controller path sai, quyền reflection hoặc lỗi controller | FXML URL, `fx:controller`, `opens`, nguyên nhân bên trong |
| `InaccessibleObjectException` | Named module chưa mở package cho framework | `module-info.java` và module đang reflection |
| `Not on FX application thread` | Cập nhật scene graph từ thread khác | `Platform.runLater`, Task/Service và event handler |
| `Toolkit not initialized` | JavaFX toolkit chưa khởi tạo hoặc lifecycle sai | `Application.launch` và thứ tự tạo UI |
| CSS/ảnh không xuất hiện | Resource path hoặc packaging sai | JAR entries, `getResource`, resource URL |
| WebView/Media chỉ lỗi trên OS khác | Native engine/codec không phù hợp | Release notes và test trên nền tảng thật |
| `jlink` từ chối automatic module | Module graph chứa JAR chưa explicit modularize | Module descriptor, lựa chọn packaging |
| Bộ cài chạy trên máy build nhưng không chạy máy sạch | Thiếu bundled runtime/native resource | Test clean machine/VM |

Đây là bảng gợi ý phân loại, không phải ánh xạ một-một. Ví dụ `NoClassDefFoundError` cũng có thể xuất hiện sau một lỗi class initialization trước đó. Luôn đọc root cause của stack trace và ghi đúng launch command trước khi đổi cấu hình.

### 17.1. Quy trình điều tra chuẩn

1. Ghi lại `java -version`, JDK vendor và bản cập nhật.
2. Ghi JavaFX version và danh sách JavaFX modules/artifacts được resolve.
3. Chụp đúng launch command, classpath, module path, working directory.
4. Xác định OS/CPU/display environment và liệu ứng dụng chạy headless hay có desktop session.
5. Kiểm tra JAR/runtime image thực sự chứa classes, FXML/CSS/media và native dependencies.
6. Xác định lỗi thuộc compile, class/module resolution, native loading, FXML reflection, UI thread hay packaging.
7. Tái hiện lỗi với một màn hình tối thiểu trên đúng OS/runtime.
8. Thử phương án sửa đúng tầng: dependency, version, module descriptor, resource path, native package hoặc launcher.
9. Chạy lại luồng nghiệp vụ và bộ cài thực tế.
10. Ghi nguyên nhân, bằng chứng, rollback và điều kiện đóng sự cố.

## 18. Kiểm thử ứng dụng JavaFX sau migration

Ứng dụng desktop khó được chứng minh tương thích chỉ bằng unit tests. Cần bổ sung nhiều lớp kiểm thử:

### 18.1. Build và khởi động

- Build clean với JDK và JavaFX version đích.
- Đảm bảo compiler không sử dụng API nội bộ JavaFX cũ.
- Tạo và chạy application ở classpath/module path đúng với production.
- Kiểm tra startup trên máy không có JavaFX/JDK cài riêng nếu ứng dụng tự đóng gói runtime.
- Đảm bảo thông báo lỗi/log có thể thu thập khi launcher đóng quá sớm.

### 18.2. Giao diện và thao tác người dùng

- Mở/đóng Stage, dialog, popup và các cửa sổ phụ.
- Focus, keyboard navigation, clipboard, drag/drop, IME và accessibility.
- Form, TableView, TreeView, sorting/filtering và những custom controls.
- CSS theme, font fallback, scale factor, HiDPI, nhiều màn hình.
- Ứng dụng chạy khi đổi locale và timezone.
- UI không bị đóng băng khi tải dữ liệu hoặc khi mạng chậm.

### 18.3. FXML, dữ liệu và tích hợp

- Tải mọi FXML trong artifact cuối.
- Inject controller fields và gọi event handlers.
- Load ảnh, font, CSS, localization bundles và template.
- Kết nối database/HTTP/TLS/identity provider nếu ứng dụng có dùng.
- Kiểm tra file chooser, printer, system tray và các desktop integration cần thiết.
- Nếu dùng Swing bridge, kiểm tra thao tác qua cả JavaFX thread và EDT.

### 18.4. Media, WebView và native integration

- Mở các định dạng media thật được tổ chức hỗ trợ.
- Test WebView login, script, navigation và certificate behavior.
- Kiểm tra font/rendering/video trên từng OS/architecture.
- Test thông báo/khả năng hồi phục khi GPU hoặc media backend không khả dụng.

### 18.5. Packaging, update và rollback

- Kiểm tra installer, uninstaller, update và khởi chạy lại.
- Xác nhận dữ liệu người dùng không bị xóa khi nâng cấp.
- Kiểm tra cơ chế chữ ký ứng dụng, certificate và quyền OS.
- Thử rollback bằng đúng installer/artifact cũ nếu quy trình hỗ trợ.
- Kiểm tra app không dựa vào `JAVA_HOME` hoặc SDK có sẵn trên máy developer trừ khi đó là điều kiện triển khai được công bố.

Bộ test cần bám theo ma trận phiên bản thực tế thay vì thử một cấu hình thành công rồi suy ra tất cả.

## 19. Ma trận JDK – JavaFX – OS – package

Một bảng tối thiểu phục vụ release:

| Thành phần | Trường cần điền | Ví dụ minh họa |
|---|---|---|
| JDK | Vendor, feature/update, architecture | JDK 21 x64 |
| JavaFX | Version, modules và native classifier | Phiên bản đã xác minh cho JDK đích |
| Build | Maven/Gradle version, plugin version | Plugin phù hợp JDK/JavaFX |
| OS | Version và CPU architecture | Windows x64, macOS AArch64 |
| UI | Swing, JavaFX, FXML, WebView | JavaFX Controls + FXML |
| Launch | Module path hay classpath | Named module hoặc non-modular |
| Distribution | Runtime image, installer | OS-specific application image |
| Validation | Test result và artifact hash | Passed/failed + đường dẫn log |

Ví dụ các tổ hợp cần quản lý:

| Kịch bản | Build/runtime | Cấu hình JavaFX | Mục tiêu |
|---|---|---|---|
| Baseline | JDK cũ | JavaFX đi kèm JDK cũ (nếu có) | Ghi nhận hành vi hiện tại |
| Development | JDK mới | OpenJFX dependencies riêng | Xác nhận source và UI |
| Modular | JDK mới + JPMS | JavaFX named modules | Kiểm tra `requires`/`opens` |
| Packaged | Runtime image riêng | JavaFX/native được bundle | Chạy trên máy sạch |
| OS khác | JDK/runtime đúng OS | JavaFX artifacts đúng platform | Hiển thị và media/WebView |
| Rollback | Artifact phát hành trước | Bộ thư viện cũ tương ứng | Khôi phục vận hành |

Không cần thử mọi tổ hợp tưởng tượng. Phải thử những tổ hợp mà chính sách phát hành và hỗ trợ thực sự cam kết.

## 20. Lộ trình migration theo từng giai đoạn

### Giai đoạn 1 — Chốt baseline

Đóng băng phiên bản JDK/JavaFX ứng dụng hiện đang dùng, liệt kê màn hình, resource, framework, native code, launcher và kênh cập nhật. Lưu bản cài hoạt động cùng cách tái tạo nó.

### Giai đoạn 2 — Thay implicit JavaFX bằng dependency tường minh

Chọn bản OpenJFX phù hợp với JDK đích và OS. Thêm dependency/plugin vào Maven/Gradle; tránh trộn SDK hoặc artifact khác version. Chạy ứng dụng tối thiểu trước khi nâng toàn bộ thư viện UI bên thứ ba.

### Giai đoạn 3 — Sửa API và module boundaries

Rà soát import internal `com.sun.javafx.*`, cập nhật library tùy chỉnh. Nếu dùng JPMS, thêm `module-info.java` với `requires` cần thiết và chỉ `opens` những package controller cần FXML reflection. Xác nhận resource loading qua module path.

### Giai đoạn 4 — Đổi packaging/launcher

Tạo runtime image hoặc distribution có JavaFX/native đúng platform. Nếu đang dựa vào Web Start/JNLP, thiết kế kênh launcher/update thay thế. Không chuyển sang installer mới khi chưa biết cách cập nhật và rollback.

### Giai đoạn 5 — Kiểm thử theo nền tảng

Chạy trên Windows/macOS/Linux và CPU architectures đã cam kết. Test clean machine, HiDPI, font, keyboard, FXML, media, WebView, kết nối bên ngoài và tính ổn định khi đóng/mở ứng dụng.

### Giai đoạn 6 — Triển khai từng nhóm và theo dõi

Phát hành thử cho nhóm nhỏ, thu thập lỗi startup, native loading, giao diện, dữ liệu và update. Giữ nguyên bản phát hành trước đủ để rollback nếu cần, nhưng không trộn runtime mới với các native libraries cũ trong cùng bộ cài.

## 21. Những kết luận dễ sai

**“Java 11 trở lên không còn hỗ trợ ứng dụng desktop.”** Sai. AWT/Swing và `java.desktop` vẫn tồn tại; JavaFX chỉ được phân phối riêng.

**“Chỉ cần tải JavaFX SDK và copy thư viện vào JDK là đủ.”** Không nên dùng như quy trình migration mặc định. Cần quản lý dependency, module path, native artifacts và packaging một cách tái tạo được.

**“JavaFX và JDK có cùng version là chắc chắn tương thích.”** Không có quy tắc chung như vậy. Phải xác minh release notes và yêu cầu runtime.

**“Gradle/Maven build xanh thì người dùng chạy được.”** Chưa đủ. Native libraries và launcher có thể thiếu hoặc sai OS/CPU; FXML resource có thể bị encapsulate khi chạy modular.

**“FXML chỉ là XML, không liên quan module access.”** Không đúng. Controller injection dùng reflection và có thể cần `opens package to javafx.fxml`.

**“Tất cả thư viện Swing đều bị bỏ theo JavaFX.”** Sai. Swing thuộc Java SE; chỉ ứng dụng dùng JavaFX hoặc bridge JavaFX-Swing mới cần OpenJFX tương ứng.

**“Fat JAR chứa hết JavaFX là cách phát hành chắc chắn nhất.”** Không bảo đảm. Native dependencies, module metadata, service resource và platform-specific components có thể bị đóng gói sai.

**“Có thể giữ Java Web Start bằng cách dùng lại `javaws` từ JDK mới.”** Không đúng với Oracle JDK hiện đại. Nếu cần JNLP, phải chọn và kiểm thử giải pháp cung cấp riêng hoặc đổi mô hình phát hành.

**“Chỉ cần thử giao diện trên một máy developer.”** Không đủ với app desktop. OS, CPU, display server, font, DPI, codec, certificate và installer có thể khác đáng kể.

## 22. Checklist trước khi đánh dấu migration hoàn thành

- [ ] Đã biết bản JDK/JRE và JavaFX cũ, gồm vendor và artifact.
- [ ] Đã phân biệt API Swing/AWT thuộc Java SE với JavaFX được phân phối riêng.
- [ ] Đã chọn JavaFX version được hỗ trợ trên JDK đích.
- [ ] Đã xác định đầy đủ JavaFX modules cần dùng: controls, fxml, media, web, swing...
- [ ] Đã kiểm tra native libraries theo OS và kiến trúc CPU.
- [ ] Đã quản lý JavaFX qua dependency/plugin hoặc SDK/runtime rõ ràng và tái tạo được.
- [ ] Đã rà soát mã phụ thuộc internal API `com.sun.javafx.*`.
- [ ] Đã kiểm tra `module-info.java`, `requires` và `opens` nếu ứng dụng dùng JPMS.
- [ ] Đã kiểm tra mọi file FXML, CSS, ảnh, font và localization trong artifact cuối.
- [ ] Đã kiểm tra controller injection và lỗi reflection.
- [ ] Đã kiểm thử JavaFX Application Thread và Swing EDT nếu ứng dụng hybrid.
- [ ] Đã kiểm tra WebView và media formats trên nền tảng hỗ trợ.
- [ ] Đã xác nhận launcher, installer, cập nhật và ký mã hoạt động.
- [ ] Đã chạy ứng dụng trên máy sạch không phụ thuộc SDK developer.
- [ ] Đã có ma trận test JDK/JavaFX/OS/CPU và kết quả rõ ràng.
- [ ] Đã có phương án rollback cả app, runtime và native artifacts.
- [ ] Đã ghi lại trách nhiệm cập nhật bản vá bảo mật JDK lẫn JavaFX.

## 23. Kết luận

Trong Java Advance Compatibility Migration, **JavaFX là ví dụ điển hình của một công nghệ vẫn được phát triển nhưng không còn được phân phối kèm JDK như một số bản cũ**. Từ JDK 11, ứng dụng JavaFX phải chủ động quản lý các module OpenJFX và phần native tương ứng. Trong khi đó, AWT/Swing tiếp tục thuộc Java SE, còn những công nghệ triển khai desktop cũ như Java Web Start cần một lộ trình thay thế hoặc giải pháp phân phối riêng.

Đánh giá tương thích phải xem toàn bộ chuỗi **source code → JavaFX dependency → module graph → native runtime → launcher/installer → hệ điều hành thực tế**. Chỉ khi ứng dụng được biên dịch, khởi chạy, hiển thị đúng, tìm được resource, chạy được trên máy sạch và có kênh cập nhật/rollback đã kiểm thử, quá trình chuyển đổi desktop mới thực sự hoàn tất.
