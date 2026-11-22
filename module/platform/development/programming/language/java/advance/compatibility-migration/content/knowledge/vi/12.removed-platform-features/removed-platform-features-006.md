# Applet, Java Web Start và phương án phân phối ứng dụng desktop

Trong nhiều hệ thống Java lâu năm, giao diện người dùng không chỉ là ứng dụng web hoặc chương trình desktop thông thường. Một số sản phẩm được triển khai dưới dạng **Java Applet** chạy bên trong trình duyệt, số khác dùng **Java Web Start** để tải và khởi chạy ứng dụng Java từ một liên kết JNLP. Các công nghệ này từng giúp triển khai Java client tới nhiều máy tính, nhưng phụ thuộc vào Java browser plugin, Java Deployment stack và những giả định bảo mật không còn phù hợp với nền tảng hiện đại.

Khi migration từ Java 8 lên các JDK như 11, 17 hoặc 21, chỉ nâng phiên bản source/target là chưa đủ. Applet có thể không còn được trình duyệt thực thi; `javaws` không còn là công cụ tiêu chuẩn đi kèm JDK mới; JavaFX không còn được gói sẵn trong JDK từ Java 11. Nhóm phát triển cần chọn lại **cách khởi chạy, đóng gói, cập nhật và phân phối** ứng dụng.

Bài học này phân biệt Applet với Java Web Start, mô tả các mốc thay đổi có ảnh hưởng đến compatibility, phân tích hướng chuyển đổi phù hợp cho desktop client và trình bày quy trình migration, ví dụ Java Swing, `jlink`, `jpackage` và checklist triển khai.

## 1. Phân biệt Applet, Java Web Start và desktop application

Đây là ba mô hình khác nhau, dù đều có thể sử dụng Java SE và giao diện AWT/Swing.

| Mô hình | Cách khởi chạy lịch sử | Quan hệ với trình duyệt | Cơ chế phân phối |
|---|---|---|---|
| Java Applet | Trình duyệt nạp Applet qua Java Plugin | Chạy trong hoặc gắn với trang web; có vòng đời Applet | Trình duyệt/Java Plugin tải class/JAR và quản lý runtime |
| Java Web Start | Người dùng mở JNLP bằng `javaws` | Trình duyệt thường chỉ cung cấp liên kết tải/mở JNLP; ứng dụng chạy riêng | JNLP khai báo resource, runtime, quyền và entrypoint |
| Desktop Java độc lập | Chạy `java -jar`, launcher hoặc executable native | Không cần plugin trình duyệt | JAR + runtime, `jlink` image, `jpackage` app image/installer hoặc công cụ khác |

Điểm dễ nhầm:

- **Applet không phải Java Web Start.** Applet dựa vào cơ chế tích hợp trình duyệt; Java Web Start khởi chạy ứng dụng desktop độc lập bằng tệp JNLP.
- **JNLP không đồng nghĩa với `javaws` có sẵn trong mọi JDK.** JNLP là định dạng/protocol mô tả khởi chạy, còn `javaws` là launcher được cung cấp bởi một implementation cụ thể.
- **Swing/AWT chưa biến mất chỉ vì Applet hoặc Java Web Start bị loại bỏ khỏi deployment stack.** Nhiều giao diện Swing/AWT có thể được chuyển sang ứng dụng desktop thông thường.
- **Đóng gói thành executable không tự tạo cơ chế cập nhật qua mạng.** Đây là trách nhiệm thiết kế riêng.

## 2. Các mốc thay đổi quan trọng theo JDK

Các mốc này giúp phân biệt công nghệ đã bị loại khỏi deployment stack với API vẫn còn trong JDK một thời gian.

| Mốc | Thay đổi liên quan | Tác động migration |
|---|---|---|
| JDK 8 | Applet và Java Web Start còn được hỗ trợ trong một số bộ phân phối Java 8, đặc biệt deployment stack của Oracle | Hệ thống cũ có thể phụ thuộc `javaws`, Java Plugin và Java Control Panel |
| JDK 9 | Applet API được đánh dấu deprecated; Java Plugin đi vào lộ trình ngừng hỗ trợ | Không nên phát triển Applet mới; cần chuẩn bị phương án thay thế |
| JDK 11 | Oracle JDK loại bỏ Java Deployment technologies gồm Java Plugin, Java Web Start và Java Control Panel; JavaFX không còn được đóng gói cùng JDK | Không thể giả định `javaws`/browser plugin/JavaFX có sẵn chỉ bằng cách cài JDK 11 |
| JDK 14 | `jpackage` được giới thiệu ở dạng incubating | Có thêm hướng tạo native app image/installer trong lộ trình JDK mới |
| JDK 16 | `jpackage` trở thành công cụ chuẩn (JEP 392) | Có giải pháp đóng gói desktop chính thức đi kèm JDK |
| JDK 17 | Applet API được deprecated for removal (JEP 398); `jpackage` có sẵn | Applet API vẫn là legacy và không phải phương án phân phối được khuyến nghị; nên chuyển mô hình |
| JDK 21 và về sau | Desktop Java vẫn có các công cụ và thư viện được hỗ trợ theo từng bản phân phối; ứng dụng cần kiểm tra riêng API và runtime | Tách việc nâng JDK khỏi việc chọn launcher, UI toolkit và kênh phân phối |

Các bản phân phối Java có thể khác nhau về bộ công cụ đi kèm hoặc sản phẩm triển khai độc lập. Khi nói “JDK không còn Java Web Start”, cần hiểu rằng **launcher cổ điển không còn nằm trong deployment stack tiêu chuẩn như trước**, không có nghĩa mọi implementation JNLP của bên thứ ba đều biến mất.

Đặc biệt, **việc giữ API Applet ở một release không đồng nghĩa trình duyệt hiện đại còn hỗ trợ chạy Applet**. Vấn đề chính là browser plugin đã bị loại khỏi các trình duyệt phổ biến và Java Deployment architecture cũ không còn là nền tảng triển khai khả thi.

## 3. Java Applet hoạt động như thế nào?

Một Applet là một đối tượng Java được thiết kế để được host (thường là trình duyệt có Java Plugin, trước đây cũng có applet viewer) nạp và quản lý.

Ví dụ Applet AWT tối giản thuộc kiểu legacy:

```java
import java.applet.Applet;
import java.awt.Button;
import java.awt.FlowLayout;

public class LegacyApplet extends Applet {

    @Override
    public void init() {
        setLayout(new FlowLayout());
        add(new Button("Gửi yêu cầu"));
    }

    @Override
    public void start() {
        // Host có thể gọi khi Applet được kích hoạt.
    }

    @Override
    public void stop() {
        // Host có thể gọi khi Applet bị tạm dừng.
    }

    @Override
    public void destroy() {
        // Dọn tài nguyên khi host hủy Applet.
    }
}
```

Các phương thức vòng đời thường gặp:

1. `init()`: khởi tạo dữ liệu hoặc thành phần giao diện.
2. `start()`: chạy lại hoặc tiếp tục công việc khi host kích hoạt Applet.
3. `stop()`: tạm dừng công việc khi host ngừng hiển thị/kích hoạt.
4. `destroy()`: giải phóng tài nguyên khi Applet kết thúc.

Một host có thể gọi `start()` và `stop()` nhiều lần. Khi di chuyển sang desktop, không nên sao chép nguyên vòng đời này vào một `main()` rồi giả định chúng tương đương.

### 3.1. Những gì Applet từng phụ thuộc vào

Một ứng dụng Applet thường có một hoặc nhiều thành phần sau:

- Thẻ HTML cũ để gắn Applet vào trang và truyền parameter.
- Java Plugin/NPAPI hoặc cơ chế tích hợp tương ứng của trình duyệt.
- Quy tắc sandbox và cấp quyền theo trust model của Java Plugin.
- Resource tải từ codebase của trang web.
- Applet context, browser scripting bridge hoặc JavaScript integration.
- Applet/JAR signing, deployment descriptor và các thiết lập deployment security.
- Giả định về mạng, cookie, proxy, session và host origin.
- AWT/Swing UI được render trong vùng trang thay vì cửa sổ độc lập.

Khi browser plugin không còn hoạt động, việc nâng class file lên Java 17 **không làm một thẻ Applet cũ chạy lại**. Cần chuyển chức năng sang mô hình phù hợp với trình duyệt hoặc ứng dụng desktop riêng.

### 3.2. Phân biệt UI code và host integration

Trong Applet cũ, phần xử lý nghiệp vụ đôi khi độc lập với trình duyệt, nhưng entrypoint và quyền truy cập tài nguyên phụ thuộc host.

Ví dụ, trong một ứng dụng nhập liệu:

```text
Applet host / HTML parameters
          |
          v
AWT/Swing UI
          |
          v
Domain validation + business rules
          |
          v
HTTP/SOAP client + file access
```

Phần domain validation hoặc business rules có thể tái sử dụng. Nhưng host integration, cấu hình endpoint, permission và cơ chế trình duyệt cần được thay mới.

## 4. Giới hạn của việc tiếp tục dùng Applet

### 4.1. Trình duyệt không còn là môi trường khởi chạy khả thi

Các trình duyệt hiện đại không cung cấp Java Plugin phổ biến như trước. Điều này làm cho mô hình Applet nhúng vào trang web không còn là lựa chọn đáng tin cậy để phân phối cho người dùng cuối.

Không thể sửa bằng cách:

```text
javac --release 17 LegacyApplet.java
```

hoặc thêm JVM flags. Compiler target không điều khiển khả năng của trình duyệt.

### 4.2. Hạn chế tương thích bảo mật

Applet truyền thống có hệ thống permission/sandbox riêng; nhiều ứng dụng còn yêu cầu quyền mở file, in hoặc kết nối mạng. Môi trường desktop mới không tự tái tạo chính sách cấp quyền của Applet.

Khi chuyển đổi, phải thiết kế lại:

- Người dùng có chấp thuận mở file, lưu file hoặc in không?
- Credential và token được cấp và lưu ở đâu?
- Giao diện có được phép gọi endpoint cũ từ môi trường mới không?
- Proxy, TLS và truststore được cấu hình thế nào?
- File hoặc dữ liệu tạm được lưu trong thư mục nào?
- Các thao tác nguy hiểm được giới hạn quyền như thế nào?

### 4.3. Browser scripting bridge không tự chuyển thành desktop API

Applet có thể đã gọi JavaScript hoặc bị JavaScript gọi thông qua cơ chế tích hợp của Java Plugin. Khi chuyển sang standalone desktop, kênh liên lạc này không còn tự động tồn tại.

Nếu cần tương tác hai chiều giữa trình duyệt và ứng dụng desktop, có thể cân nhắc giải pháp có hợp đồng rõ như:

- Backend API: cả browser app và desktop app giao tiếp với server.
- URI scheme/protocol handler có kiểm soát: browser yêu cầu mở ứng dụng thông qua hệ điều hành.
- Browser extension và native messaging host được triển khai/kiểm soát riêng.
- Local loopback endpoint trong một số sản phẩm, kèm authentication, origin checks và hạn chế CORS/CSRF phù hợp.

Không nên mở một local HTTP endpoint không bảo vệ rồi cho rằng nó tương đương sandbox Applet.

## 5. Java Web Start và JNLP

Java Web Start từng cung cấp cách khởi chạy desktop Java từ liên kết web. Ứng dụng được mô tả bởi file **JNLP (Java Network Launch Protocol)**, chứa thông tin artifact, entrypoint, runtime và metadata deployment.

Một ví dụ cấu trúc JNLP đơn giản mang tính minh họa:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<jnlp spec="1.0+"
      codebase="https://download.example.invalid/desktop">
    <information>
        <title>Inventory Desktop</title>
        <vendor>Example Organization</vendor>
        <description>Ứng dụng quản lý kho</description>
    </information>

    <resources>
        <j2se version="1.8+"/>
        <jar href="inventory-client.jar" main="true"/>
    </resources>

    <application-desc main-class="com.example.inventory.Main"/>
</jnlp>
```

Đây là ví dụ lịch sử cho Java Web Start, **không phải file chắc chắn chạy được trên mọi launcher JNLP mới**. Thuộc tính runtime, permission, resource và vendor feature cần được kiểm tra theo implementation đang lựa chọn.

### 5.1. Tệp JNLP từng giải quyết những vấn đề gì?

- Cung cấp metadata để launcher xác định application entrypoint.
- Mô tả các JAR, native library và resource được tải về.
- Hỗ trợ caching và một số cơ chế cập nhật resource.
- Có thể khai báo yêu cầu runtime Java.
- Có thể cấu hình desktop shortcut, offline availability và deployment behavior tùy implementation.
- Hỗ trợ các chính sách security và API Java Web Start theo môi trường lịch sử.

Nhiều hệ thống có quy trình “người dùng click link trên portal, launcher kiểm tra bản mới, tải JAR rồi mở ứng dụng” dựa trên JNLP.

### 5.2. Vì sao JDK 11 không khởi chạy JNLP như JDK 8?

Java Web Start (`javaws`) là một phần của Java Deployment stack lịch sử, không phải tính năng bắt buộc có mặt trong mọi JDK. Khi stack này bị loại khỏi Oracle JDK 11, việc nâng máy người dùng từ Java 8 lên Java 11 có thể làm mất `javaws`.

Hệ quả:

```bash
javaws inventory.jnlp
```

không còn là lệnh có thể giả định trên máy chỉ cài JDK 11/17 chuẩn. `java -jar inventory.jnlp` cũng không phải phương pháp thay thế: JNLP là XML descriptor, không phải JAR executable.

### 5.3. JNLP không phải Applet

Cần phân loại chính xác hệ thống cũ:

- Nếu người dùng chạy chương trình qua một tệp `.jnlp` bằng `javaws` và nhìn thấy một cửa sổ độc lập, đó thường là Java Web Start application.
- Nếu Java UI nằm trực tiếp trong trang web và yêu cầu Java Plugin, đó là Applet.
- Nếu chỉ có shortcut chạy `java -jar`, đó là ứng dụng desktop Java truyền thống, dù file JAR được tải từ website.

Chuyển một Applet thành Java Web Start không chỉ là đổi extension file. Cần tạo entrypoint và xử lý lại lifecycle, browser integration và security model.

## 6. Phương án chuyển tiếp: JNLP launcher độc lập

Một tổ chức có thể cần tiếp tục hỗ trợ JNLP trong thời gian migration, đặc biệt nếu có rất nhiều desktop client đã triển khai và một cơ chế cập nhật JNLP lâu năm.

Các giải pháp thuộc hệ sinh thái Java Web Start độc lập, chẳng hạn **OpenWebStart** hoặc các triển khai dựa trên IcedTea-Web, có thể là lựa chọn chuyển tiếp cho **những ứng dụng JNLP được hỗ trợ**.

Điều cần nhấn mạnh:

- Đây không phải tính năng được tự động khôi phục bằng cách cài JDK 17.
- Mức hỗ trợ JNLP feature, JNLP services, JVM management, signing và security khác nhau theo implementation/version.
- Một launcher JNLP độc lập **không tương đương với Java Plugin trong trình duyệt** và không tự khôi phục Applet nhúng.
- Các thành phần gắn chặt với vendor JDK 8 hoặc các API triển khai riêng cần được kiểm chứng.
- Cần xem điều khoản phân phối, chính sách cập nhật launcher và khả năng vận hành trên hệ điều hành mục tiêu.

### 6.1. Khi nào nên cân nhắc launcher JNLP độc lập?

Giải pháp có thể phù hợp nếu:

- Ứng dụng thực sự là Java Web Start **standalone** chứ không phải browser Applet.
- Business logic và UI vẫn tương thích với runtime Java mục tiêu.
- Cần duy trì mô hình tải/cập nhật JAR từ máy chủ.
- Tổ chức có thể quản lý launcher trên máy trạm.
- Các tính năng JNLP đang dùng có implementation thay thế hỗ trợ hoặc có thể chuyển đổi.

Nếu ứng dụng lệ thuộc sâu vào legacy Java Deployment API, integration với trình duyệt hoặc security prompts cũ, chi phí thử nghiệm có thể cao. Khi đó, phương án đóng gói native hoặc viết lại giao diện có thể bền vững hơn.

### 6.2. Những thành phần nên kiểm kê trước khi thử

Kiểm tra file JNLP và code đang sử dụng:

- `<application-desc>`, `<applet-desc>`, `<component-desc>` và loại khởi chạy.
- `<resources>`, `<jar>`, `<nativelib>` và runtime yêu cầu.
- `<security>` như `<all-permissions/>`, nếu có.
- `<extension>`, `<property>`, offline/caching và các tham số bổ sung.
- API `javax.jnlp.*` như BasicService, FileOpenService, DownloadService hoặc PersistenceService nếu được dùng.
- Code signing, certificate chain và các yêu cầu trust.
- Các URL resource, authentication, proxy và server headers.
- Cơ chế đặt shortcut và cơ chế update riêng của ứng dụng.

Không nên kết luận tương thích JNLP chỉ vì file XML được parse thành công. Cần khởi chạy, cài shortcut, tải update và kiểm tra các luồng chính trên máy sạch.

## 7. Chọn hướng migration: ứng dụng web hay desktop?

Trước khi chọn công cụ đóng gói, cần xác định mô hình trải nghiệm người dùng.

### 7.1. Chuyển thành ứng dụng web

Phù hợp khi phần lớn chức năng có thể chạy trong browser:

- Form nhập liệu và tra cứu dữ liệu.
- Dashboard, báo cáo, workflow phê duyệt.
- Gọi API qua HTTP và xử lý state phía server.
- Sử dụng trình duyệt trên nhiều hệ điều hành mà không cần runtime Java cài tại client.

Một kiến trúc thường gặp:

```text
Browser UI (HTML/CSS/JavaScript)
             |
             v
     Backend API (Java)
             |
             v
    Database / Services
```

Ưu điểm là không phải phát hành Java runtime tới máy trạm. Nhưng các chức năng như đọc thiết bị USB, smart card, in đặc thù, truy cập filesystem sâu hoặc làm việc offline cần thiết kế riêng.

### 7.2. Giữ ứng dụng desktop Java

Phù hợp nếu sản phẩm cần:

- Swing/AWT/JavaFX UI hiện có và có thể tái sử dụng đáng kể.
- Tích hợp OS, in ấn, thiết bị ngoại vi, clipboard hoặc file local.
- Chạy offline hoặc đồng bộ dữ liệu khi có mạng.
- Khả năng đóng gói runtime riêng, không phụ thuộc JDK cài sẵn.
- Chu trình phát hành/rollback dành cho phần mềm desktop.

Có thể chọn `jpackage` để tạo launcher/app image/installer, hoặc phân phối một runtime image và script nếu có lý do vận hành.

### 7.3. Mô hình kết hợp

Một số hệ thống chọn giao diện web cho chức năng chính, kết hợp tiện ích desktop nhỏ cho thiết bị đặc thù:

```text
Browser / Web App  <---- HTTPS API ----> Backend Services
       |
       | giao thức tích hợp được thiết kế riêng
       v
 Local Desktop Agent -----> Printer / Scanner / Smart Card
```

Thiết kế này cần kiểm soát authentication, authorization, cập nhật agent và giới hạn kênh giao tiếp giữa browser và ứng dụng local.

### 7.4. Bảng lựa chọn

| Yêu cầu | Web app | Desktop + `jpackage` | JNLP launcher độc lập |
|---|---|---|---|
| Không cần cài phần mềm trên máy người dùng | Thường phù hợp | Không | Cần launcher/runtime |
| Tái sử dụng Swing/AWT hiện có | Hạn chế | Tốt | Có thể tốt |
| Thiết bị ngoại vi/local filesystem nâng cao | Cần cơ chế tích hợp riêng | Phù hợp hơn | Tùy permission/implementation |
| Offline-first | Cần thiết kế offline web riêng | Phù hợp | Tùy cache và ứng dụng |
| Kênh cập nhật tự động | Dễ cập nhật ở server | Cần xây dựng/áp dụng updater | Có thể có caching/update theo launcher |
| Đầu tư dài hạn cho sản phẩm desktop Java | Không trực tiếp | Phù hợp | Thường là phương án chuyển tiếp |
| Khôi phục Applet trong browser hiện đại | Không theo mô hình Applet | Không; chuyển sang cửa sổ riêng | Không tự khôi phục Java Plugin |

Không có lựa chọn tối ưu cho mọi ứng dụng. Cần cân bằng khả năng tái sử dụng code, chi phí cài đặt, vận hành máy trạm, bảo mật, offline và nhu cầu truy cập phần cứng.

## 8. Chuyển Applet thành ứng dụng Swing độc lập

Giả sử Applet cũ hiển thị một nút và xử lý action. Khi chuyển sang desktop, thường có thể giữ domain/controller và thay entrypoint bằng JFrame, JDialog hoặc một cửa sổ JavaFX phù hợp.

Ví dụ ứng dụng Swing chạy độc lập:

```java
import javax.swing.JButton;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JPanel;
import javax.swing.SwingUtilities;
import java.awt.BorderLayout;

public final class InventoryDesktopApp {
    private InventoryDesktopApp() {
    }

    public static void main(String[] args) {
        SwingUtilities.invokeLater(InventoryDesktopApp::showWindow);
    }

    private static void showWindow() {
        JFrame frame = new JFrame("Inventory Desktop");
        frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);

        JLabel status = new JLabel("Chưa gửi yêu cầu");
        JButton button = new JButton("Gửi yêu cầu");
        button.addActionListener(event -> status.setText("Đã nhận thao tác"));

        JPanel panel = new JPanel(new BorderLayout(12, 12));
        panel.add(status, BorderLayout.CENTER);
        panel.add(button, BorderLayout.SOUTH);

        frame.setContentPane(panel);
        frame.setSize(420, 180);
        frame.setLocationRelativeTo(null);
        frame.setVisible(true);
    }
}
```

Đây là một ví dụ code desktop không sử dụng Applet API. Có thể biên dịch bằng JDK 17:

```bash
javac InventoryDesktopApp.java
java InventoryDesktopApp
```

Ứng dụng cần desktop environment; trong môi trường server/headless, tạo JFrame có thể không hoạt động.

### 8.1. Những phần có thể tái sử dụng

- Validation, domain service và nghiệp vụ độc lập với UI.
- Data access và HTTP client còn tương thích.
- Logic xử lý sự kiện có thể được tách vào controller.
- Một phần Swing/AWT component, nếu không dựa vào Applet context.
- Resource icon, localization và file cấu hình, sau khi điều chỉnh cách nạp.

### 8.2. Những phần cần thiết kế lại

- `Applet.init/start/stop/destroy` thành startup, foreground/background lifecycle và shutdown của desktop app.
- Tham số HTML thành config file, environment variable hoặc arguments.
- Cơ chế browser plugin/JavaScript bridge thành API/giao thức rõ ràng.
- Cơ chế chọn file/in do deployment sandbox quản lý thành quyền OS và UI chính thức.
- Resource từ JNLP codebase thành resource đi kèm app, URL API hoặc cache riêng.
- Update từ Java Deployment sang installer/updater được quản lý.

### 8.3. Event Dispatch Thread và công việc nền

Với Swing, thao tác cập nhật UI nên chạy trên Event Dispatch Thread (EDT). Tác vụ mạng hoặc file dài không nên chạy trực tiếp trong action listener vì sẽ làm giao diện đứng.

Có thể dùng `SwingWorker` hoặc executor để chuyển việc nặng sang luồng nền, sau đó cập nhật UI an toàn. Migration là dịp thích hợp để tách UI khỏi I/O, tránh mang nguyên mô hình threading không rõ ràng từ Applet sang desktop.

## 9. JavaFX khi chuyển từ Java 8 sang 11/17+

Nếu ứng dụng desktop cũ dùng JavaFX, cần nhớ rằng JavaFX không còn được gói sẵn trong JDK 11 tiêu chuẩn. Thư viện JavaFX được phân phối riêng trong hệ sinh thái OpenJFX hoặc các bộ phân phối phù hợp.

Hệ quả:

- Một dự án build và chạy JavaFX trên JDK 8 có thể không còn biên dịch/chạy chỉ bằng cách thay `JAVA_HOME` sang JDK 17.
- Cần bổ sung dependency JavaFX có version và classifier/native artifact đúng OS/architecture.
- Với ứng dụng modular, có thể cần `requires javafx.controls;`, `javafx.fxml` hoặc các module JavaFX tương ứng.
- Khi đóng gói `jlink`/`jpackage`, cần đưa module JavaFX và native resources phù hợp vào runtime/application image.
- FXML, reflection và controller packages có thể cần `opens ... to javafx.fxml;` trong module descriptor.

Ví dụ descriptor ứng dụng JavaFX modular:

```java
module com.example.inventory.desktop {
    requires javafx.controls;
    requires javafx.fxml;

    exports com.example.inventory.desktop;
    opens com.example.inventory.desktop.ui to javafx.fxml;
}
```

Đây chỉ là ví dụ descriptor; build thực tế còn cần dependency JavaFX và module path tương thích. Không nhầm **JavaFX rời JDK** với **JavaFX bị loại khỏi khả năng phát triển ứng dụng**.

## 10. `jpackage`: phương án đóng gói desktop hiện đại

`jpackage` giúp tạo **application image** hoặc installer native cho ứng dụng Java, có thể kèm Java runtime image riêng. Đây là một giải pháp chuẩn trong JDK mới cho phân phối desktop Java, không phụ thuộc Java Plugin hoặc `javaws`.

### 10.1. App image và installer khác nhau

- **App image:** thư mục chứa launcher và các thành phần cần chạy. Có thể dùng để kiểm tra đóng gói hoặc làm đầu vào cho installer.
- **Installer native:** gói cài đặt theo hệ điều hành, ví dụ `msi`/`exe` trên Windows, `dmg`/`pkg` trên macOS, `deb`/`rpm` trên Linux.

App image không tự động là một installer có UI cài/gỡ hoặc cơ chế cập nhật.

### 10.2. Ví dụ tạo JAR của ứng dụng Swing

Giả sử file `InventoryDesktopApp.java` đã được compile:

```bash
javac -d build/classes InventoryDesktopApp.java

jar --create \
  --file build/inventory-desktop.jar \
  --main-class InventoryDesktopApp \
  -C build/classes .
```

Nếu ứng dụng có nhiều dependency, phải chuẩn bị các JAR runtime cần thiết. Lệnh trên chỉ minh họa trường hợp một class đơn giản không có external dependency.

### 10.3. Đóng gói bằng `jpackage`

Ví dụ tạo app image:

```bash
jpackage \
  --type app-image \
  --name InventoryDesktop \
  --input build \
  --main-jar inventory-desktop.jar \
  --main-class InventoryDesktopApp \
  --dest dist
```

Các tham số quan trọng:

| Tùy chọn | Vai trò |
|---|---|
| `--type app-image` | Tạo thư mục application image thay vì installer |
| `--name` | Tên ứng dụng/launcher |
| `--input` | Thư mục chứa JAR và resource đầu vào |
| `--main-jar` | JAR có entrypoint |
| `--main-class` | Main class khi cần chỉ định |
| `--dest` | Nơi ghi artifact được tạo |
| `--runtime-image` | Sử dụng runtime image được tạo sẵn |
| `--java-options` | Thêm JVM argument cần thiết cho launcher |

Nếu dùng `--input build`, cần tránh đưa nhầm JAR khác hoặc tài nguyên không cần thiết vào gói. Với ứng dụng thật, nên chuẩn bị một thư mục staging chỉ chứa những dependency/runtime resources được chấp nhận phát hành.

### 10.4. Chọn định dạng theo nền tảng

Các định dạng cài đặt và dependency native khác nhau theo OS:

| Nền tảng xây dựng | Kết quả thường dùng | Lưu ý |
|---|---|---|
| Windows | `app-image`, `exe`, `msi` | Cần môi trường và packaging toolchain Windows phù hợp; xử lý signing/installer policy |
| macOS | `app-image`, `dmg`, `pkg` | Cần xem xét code signing, notarization và quyền OS |
| Linux | `app-image`, `deb`, `rpm` | Các công cụ tạo gói hệ điều hành cần được cài phù hợp |

Thông thường, **không thể dùng một lần chạy `jpackage` trên Linux để tạo đầy đủ installer native Windows/macOS**. Xây dựng và kiểm thử artifact theo OS/architecture mục tiêu; nếu cần Windows x64 và Windows ARM64, hoặc macOS Intel/Apple Silicon, cần quản lý từng biến thể tương ứng.

### 10.5. Runtime image đi kèm

Một ưu điểm lớn là ứng dụng có thể đi kèm runtime phù hợp. Người dùng không phải tự chọn và cài JDK trên máy trạm chỉ để chạy client.

Tuy vậy, đi kèm runtime kéo theo nghĩa vụ cập nhật:

- Khi có bản vá bảo mật JDK, phải đóng gói và phát hành lại runtime/app image.
- Installer phải có đường nâng cấp, sửa lỗi, rollback và thông tin phiên bản.
- Native libraries cần đúng kiến trúc và hệ điều hành.
- Cần theo dõi nguồn gốc runtime và license của bản phân phối đang dùng.

Không nên coi runtime bundle là “cài một lần rồi không bảo trì”.

## 11. `jlink`: tạo runtime image tùy chỉnh

`jlink` xuất hiện từ Java 9 và được dùng để liên kết một runtime image gồm những module cần thiết. Nó khác `jpackage`:

- `jlink` tạo **runtime image**.
- `jpackage` tạo **application image hoặc installer** và có thể dùng runtime image đó.

### 11.1. Phân tích dependency bằng `jdeps`

Với JAR ứng dụng và các thư viện ở `lib`, có thể khảo sát:

```bash
jdeps --print-module-deps \
  --class-path "lib/*" \
  build/inventory-desktop.jar
```

Kết quả là điểm khởi đầu để chọn module JDK cần có, nhưng phân tích tĩnh có thể bỏ sót module/provider dùng qua reflection hoặc service loading.

### 11.2. Tạo runtime cho ứng dụng Swing

Ví dụ cho runtime cần `java.desktop`:

```bash
jlink \
  --add-modules java.desktop \
  --output build/inventory-runtime
```

Tùy ứng dụng, có thể cần thêm `java.net.http`, `java.sql`, `java.logging`, security/service provider hoặc module khác.

Sau đó cho `jpackage` sử dụng image:

```bash
jpackage \
  --type app-image \
  --name InventoryDesktop \
  --input build/staging \
  --main-jar inventory-desktop.jar \
  --runtime-image build/inventory-runtime \
  --dest dist
```

Đối với ứng dụng dùng `ServiceLoader`, JDBC driver, locale hoặc module JavaFX, cần xác minh runtime image chứa đủ module và provider. `jlink` không tự giải quyết mọi classpath library hay native dependency.

### 11.3. Kiểm thử runtime cuối cùng

Một custom image có thể khởi động màn hình đầu nhưng lỗi ở chức năng chỉ chạy sau đó, ví dụ:

- Hộp thoại chọn/in file.
- Kết nối HTTPS với truststore không đúng.
- Localized text/charset/timezone.
- JDBC driver/serialization provider.
- Smart card hoặc native DLL/.so/.dylib.
- Reflection và dynamic loading.

Vì vậy, test phải chạy trên **app image/installer thực tế**, không chỉ bằng JDK đầy đủ trên máy phát triển.

## 12. Phương án JAR + runtime + script

Không phải mọi môi trường cần installer native. Với hệ thống nội bộ, có thể phân phối một archive gồm runtime phù hợp, JAR và launcher script:

```text
inventory-desktop/
├── runtime/
│   └── bin/java
├── app/
│   ├── inventory-desktop.jar
│   └── lib/
└── bin/
    └── start.sh
```

Ví dụ launcher Linux/macOS với đường dẫn tương đối:

```bash
#!/usr/bin/env sh
APP_HOME="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
exec "$APP_HOME/runtime/bin/java" \
  -jar "$APP_HOME/app/inventory-desktop.jar" "$@"
```

Ví dụ này yêu cầu JAR executable có cấu hình classpath/manifest hợp lệ hoặc cơ chế nạp dependency tương ứng. Nếu JAR không chứa dependency, script phải thiết lập classpath/module path đúng.

Ưu điểm là kiểm soát và dễ triển khai bằng công cụ quản trị nội bộ. Nhược điểm là phải tự xử lý shortcut, cài/gỡ, desktop integration, mã hóa ký code, cập nhật và bảo trì runtime.

## 13. Phân phối, cập nhật và rollback

Java Web Start từng gắn quá trình khởi chạy với cơ chế tải resource/update. Khi chuyển sang installer hoặc app image, phần đó không tự xuất hiện.

### 13.1. Chọn chính sách cập nhật

Các lựa chọn phổ biến:

1. **Cập nhật thủ công:** người dùng tải và cài bản mới.
2. **Quản trị tập trung:** IT/MDM/software distribution đẩy installer theo nhóm thiết bị.
3. **Updater riêng của ứng dụng:** ứng dụng kiểm tra phiên bản, tải gói đã ký và thực hiện nâng cấp.
4. **Auto-update framework bên ngoài:** dùng nếu đáp ứng yêu cầu về OS, bảo mật và tích hợp.

Với ứng dụng nghiệp vụ quan trọng, cần chọn rõ cơ chế, không mặc định để người dùng tự thay JAR.

### 13.2. Phát hành an toàn

Một quy trình phát hành desktop nên quản lý:

- Version ứng dụng và runtime JDK.
- Hash/checksum artifact và chữ ký code/installer.
- Channel phát hành (test, pilot, production).
- Quy tắc xác minh bản tải từ server.
- Nguồn tải HTTPS/TLS và chính sách chứng chỉ.
- Khả năng rollback nếu schema/local data còn tương thích.
- Nơi lưu config, log, cache và dữ liệu người dùng, tránh ghi đè khi cài bản mới.
- Chế độ cài per-user hoặc per-machine và yêu cầu admin.
- Giám sát lỗi startup, crash và sự cố kết nối.

Không được nhúng token, mật khẩu hay private key vào installer. Nếu app cần đăng nhập, dùng authentication hiện đại và secure storage phù hợp với OS.

### 13.3. Version compatibility giữa client và server

Desktop client có thể không được cập nhật đồng thời trên mọi máy. Khi backend API thay đổi, nên hỗ trợ rollout hỗn hợp:

```text
Client 1.7  ──API v1──┐
                    ├── Server trong giai đoạn chuyển tiếp
Client 2.0  ──API v2──┘
```

Cần xác định thời hạn hỗ trợ client cũ, hợp đồng request/response, chính sách bắt buộc nâng cấp và cách rollback khi client đã cập nhật dữ liệu local sang format mới.

## 14. Bảo mật: từ sandbox Applet/JNLP sang ứng dụng OS

Một trong các thay đổi lớn nhất không nằm ở Java syntax mà ở **trust model**.

### 14.1. Không kế thừa tự động sandbox cũ

Applet sandbox và JNLP security model từng quản lý việc ứng dụng được tải từ mạng truy cập tài nguyên máy trạm. Khi trở thành ứng dụng desktop cài trên máy, chương trình thường chạy theo quyền tài khoản người dùng và các hạn chế OS.

Cần đánh giá lại:

- Truy cập file/hệ thống thiết bị.
- Kết nối mạng tới host ngoài và localhost.
- Lưu thông tin đăng nhập.
- Code signing và nguồn artifact.
- Quyền của updater/installer.
- Phạm vi dữ liệu ứng dụng được đọc/ghi.
- Endpoint có thể bị gọi từ UI hoặc browser integration.

### 14.2. Không thay thế warning bằng quyền toàn phần

Một số JNLP cũ khai báo:

```xml
<security>
    <all-permissions/>
</security>
```

Khi migration, không nên coi mục tiêu là “cấp toàn quyền” cho ứng dụng mới. Cần phân tích chính xác tính năng yêu cầu permission nào và giới hạn theo least privilege.

### 14.3. Code signing khác TLS

- **TLS/HTTPS** bảo vệ kênh tải và giúp xác minh endpoint khi được cấu hình đúng.
- **Code signing** giúp xác minh publisher và tính toàn vẹn của artifact theo hệ sinh thái ký của nền tảng.
- **Checksum** hữu ích cho integrity nhưng tự nó không xác thực publisher nếu checksum được phân phối từ nguồn không đáng tin cậy.

Khi phát hành installer, cần phối hợp các cơ chế này; không coi chúng thay thế hoàn toàn cho nhau.

## 15. Kiểm kê hệ thống legacy trước khi quyết định migration

Một ứng dụng desktop cũ thường có nhiều phụ thuộc ngoài JAR. Nên lập danh mục để tránh bỏ sót yêu cầu khi thay launcher.

| Hạng mục | Câu hỏi cần trả lời |
|---|---|
| Loại ứng dụng | Applet trong browser, JNLP standalone hay `java -jar`? |
| UI toolkit | AWT, Swing, JavaFX hay thư viện UI khác? |
| Vòng đời | `Applet.init/start/stop/destroy`, `main` hay JNLP entrypoint? |
| Browser integration | Có JS bridge, cookie, session, parameter HTML không? |
| Java runtime | Vendor/version/architecture hiện tại và tối thiểu mục tiêu? |
| Dependency | JAR, native library, JavaFX, `javax.jnlp.*` hoặc API Java Deployment nào? |
| Security | JAR signing, certificate, sandbox, `all-permissions`, secret/token? |
| Filesystem | Local file, thư mục dữ liệu, import/export, in ấn? |
| Network | Proxy, DNS, TLS, SOAP/REST endpoints, offline cache? |
| Deployment | JNLP resource cache, portal link, shortcut, installer hoặc quản trị tập trung? |
| Update | Ai nâng client, dùng channel nào, rollback ra sao? |
| Hệ điều hành | Windows/macOS/Linux, x64/ARM64, account permission? |

Kết quả kiểm kê giúp tách những thành phần có thể tái sử dụng (domain, API client, UI component) khỏi những thành phần cần thay thế (host, launcher, updater, policy).

## 16. Quy trình migration đề xuất

### Bước 1: Chốt baseline hoạt động

Lưu phiên bản Java 8/JDK cũ, JNLP/HTML descriptor, artifact đã ký, dependency, môi trường trình duyệt hoặc launcher và các luồng nghiệp vụ đã được kiểm thử.

### Bước 2: Xác định đúng công nghệ cũ

Không dùng cùng một hướng migration cho Applet và Java Web Start. Xác định Applet phụ thuộc browser plugin hay ứng dụng desktop khởi chạy bằng `javaws`. Nếu có cả hai, cần chia thành hai nhóm riêng.

### Bước 3: Tách code khỏi cơ chế host

Tách domain service, validation, data access và HTTP client ra khỏi Applet/JNLP lifecycle. Định nghĩa một entrypoint desktop hoặc backend API phù hợp.

### Bước 4: Chọn đích phân phối

Cân nhắc web app, desktop đóng gói bằng `jpackage`, JNLP launcher độc lập làm cầu nối hoặc mô hình lai. Ghi rõ lý do dựa trên chức năng, OS, offline và thiết bị ngoại vi.

### Bước 5: Nâng JDK và dependency

Chọn JDK mục tiêu, cấu hình compiler/toolchain và dependency hiện đại. Nếu dùng JavaFX, khai báo OpenJFX riêng. Nếu còn `javax.jnlp.*`, thay API hoặc xác nhận launcher mới hỗ trợ trước khi phát hành.

### Bước 6: Tạo entrypoint và package

Với desktop, tạo `main()`/launcher, cấu hình manifest và chọn `jpackage` hoặc mô hình runtime image thích hợp. Nếu dùng `jlink`, xác định module JDK và service provider cần thiết.

### Bước 7: Thiết kế deployment/update

Xác định app version, runtime version, kênh tải, code signing, cách cài/gỡ, update và rollback. Đưa config/data của người dùng ra khỏi vùng bị thay thế khi cài mới.

### Bước 8: Kiểm thử chức năng trên máy sạch

Không chỉ chạy bằng IDE. Cài artifact thật trên OS/architecture đích, dùng tài khoản có quyền người dùng thông thường và kiểm tra đăng nhập, file, in, offline, proxy, TLS và native integration.

### Bước 9: Pilot với nhóm người dùng nhỏ

Triển khai theo giai đoạn, theo dõi crash, log, hiệu năng, tỷ lệ cập nhật và tương thích API server. Chuẩn bị hỗ trợ cho máy không đủ điều kiện hoặc không có quyền cài installer.

### Bước 10: Loại bỏ cơ chế legacy có kiểm soát

Khi client mới ổn định, ngừng phụ thuộc vào browser plugin/JNLP launcher cũ, khóa kênh phát hành lỗi thời và cập nhật tài liệu vận hành. Không xóa API/server endpoint còn phục vụ client chưa nâng cấp nếu chưa hết thời hạn hỗ trợ.

## 17. Rủi ro thường gặp và cách tránh

### “Applet compile được trên JDK mới nên chạy được trong Chrome/Edge”

Không đúng. Browser plugin là khả năng của trình duyệt và deployment stack, không phải tính năng được khôi phục bằng việc biên dịch class Applet.

### “Thay `javaws` bằng `java -jar` là đủ”

Không đúng. `javaws` đọc JNLP, xử lý resource, runtime, security, update và entrypoint. `java -jar` chạy executable JAR; những chức năng deployment trước đó cần được xây dựng hoặc thay thế riêng.

### “Dùng OpenWebStart là Applet sẽ chạy lại trong trình duyệt”

Không đúng. Launcher JNLP độc lập không tự khôi phục Java Plugin cho Applet nhúng. Phải xác định ứng dụng có thực sự là standalone JNLP hay không.

### “Có `jpackage` thì ứng dụng tự cập nhật”

Không đúng. `jpackage` tạo app image/installer. Phương án update, rollback và kênh phát hành vẫn cần được thiết kế và vận hành.

### “Chỉ copy JAR là có thể chuyển nguyên Applet sang desktop”

Không đúng. Vòng đời Applet, browser integration, sandbox và resource loading cần được xử lý lại. Code xử lý nghiệp vụ có thể tái sử dụng nhưng host abstraction thay đổi.

### “JavaFX vẫn mặc định nằm trong JDK 17”

Không đúng với các JDK tiêu chuẩn: JavaFX được phân phối riêng kể từ Java 11. Cần quản lý dependency/module/native assets của OpenJFX hoặc bản phân phối phù hợp.

### “Ứng dụng chạy trên máy dev thì installer chắc chắn hoạt động”

Không đúng. Máy dev có thể có JDK, driver, native libs, certificate hoặc quyền admin mà máy người dùng không có. Luôn kiểm thử trên máy sạch và artifact cuối.

### “Bundled runtime không cần vá bảo mật”

Không đúng. Khi đóng gói runtime đi kèm app, trách nhiệm cập nhật runtime chuyển sang quy trình phát hành ứng dụng. Phải có cadence cập nhật và khả năng rollout phiên bản mới.

## 18. Checklist hoàn tất

- [ ] Phân biệt đúng Applet, Java Web Start/JNLP và desktop JAR truyền thống.
- [ ] Đã ghi nhận browser plugin, `javaws`, JNLP API và launcher dependencies.
- [ ] Đã xác định JDK runtime mục tiêu và các tính năng không còn trong JDK.
- [ ] Đã đánh giá cách tái sử dụng AWT/Swing/JavaFX và business logic.
- [ ] Nếu chọn web app, đã thiết kế lại browser integration và các chức năng local.
- [ ] Nếu chọn desktop, đã có `main()`/launcher không phụ thuộc Applet host.
- [ ] Nếu chọn JNLP bridge, đã kiểm thử launcher độc lập với JNLP feature thực tế.
- [ ] Nếu dùng JavaFX, đã khai báo và đóng gói OpenJFX tương ứng OS/architecture.
- [ ] Nếu dùng `jlink`, runtime image có đủ module/provider và được test thực tế.
- [ ] Nếu dùng `jpackage`, đã kiểm thử app image/installer trên máy sạch.
- [ ] Đã xác định code signing, TLS, authentication và quyền filesystem/device.
- [ ] Đã thiết kế kênh cập nhật, versioning, rollback và bảo trì runtime đi kèm.
- [ ] Đã kiểm thử offline, proxy, certificate, in ấn và native device khi liên quan.
- [ ] Đã có kế hoạch tương thích client/server trong giai đoạn rollout hỗn hợp.
- [ ] Đã có kế hoạch ngừng phân phối Applet/`javaws` legacy khi migration hoàn tất.

## 19. Kết luận

Applet và Java Web Start đại diện cho hai mô hình triển khai Java client khác nhau, nhưng cả hai đều phụ thuộc những thành phần deployment lịch sử không còn được cung cấp như trước trong các JDK mới và môi trường trình duyệt hiện đại. Vì vậy, migration không thể chỉ thực hiện bằng cách thay compiler target hoặc tăng phiên bản Java runtime.

Đối với hệ thống còn dùng Applet, trọng tâm là tách phần nghiệp vụ khỏi browser host và chuyển giao diện sang web hoặc desktop. Đối với Java Web Start standalone, có thể đánh giá JNLP launcher độc lập như giải pháp chuyển tiếp, hoặc chuyển sang phân phối desktop có runtime riêng bằng `jlink` và `jpackage`. Dù chọn hướng nào, cần quản lý đồng thời entrypoint, security, update, code signing, compatibility giữa client/server và kiểm thử installer trên môi trường cuối cùng.
