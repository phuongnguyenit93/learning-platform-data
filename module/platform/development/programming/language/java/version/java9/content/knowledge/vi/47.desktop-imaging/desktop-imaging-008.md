# Kiểm tra khả năng hỗ trợ theo hệ điều hành trước khi gọi API Desktop và hình ảnh (Java 9+)

## 1. Bài toán: cùng mã Java, môi trường chạy có thể khác nhau

Ứng dụng Java có thể được triển khai trên Windows, macOS, Linux, máy ảo, máy chủ không có màn hình, container hoặc phiên làm việc qua remote desktop. Một số thao tác như mở ảnh bằng ứng dụng mặc định, bật trình duyệt, đưa file vào thùng rác, hiển thị biểu tượng ở khay hệ thống hay cập nhật tiến trình trên taskbar phụ thuộc trực tiếp vào **tính năng của môi trường desktop hiện tại**. Việc lớp API có sẵn trong JDK **không bảo đảm** môi trường đang chạy triển khai được thao tác đó.

Ví dụ: `java.awt.Desktop` cung cấp `open(File)` để mở tệp bằng ứng dụng gắn với phần mở rộng của hệ điều hành. Tuy nhiên, trên server/headless, không có desktop session; hoặc `Desktop.Action.OPEN` được hỗ trợ nhưng file `.png` không có ứng dụng được đăng ký để mở. Cả hai trường hợp cần đường xử lý khác.

Trong bối cảnh Java 9+, có một số khả năng desktop đáng chú ý vẫn được sử dụng hiện nay: `Desktop.browseFileDirectory(...)`, `Desktop.moveToTrash(...)` (từ Java 9), `Taskbar` (từ Java 9), `SystemTray`, `Robot`, cùng `ImageIO` và `BufferedImage` cho xử lý ảnh không cần cửa sổ. Điều quan trọng là **kiểm tra đúng loại hỗ trợ trước khi gọi, rồi vẫn xử lý lỗi khi gọi**.

**Nguyên tắc:** Đừng suy ra khả năng từ `System.getProperty("os.name")` như “Windows chắc chắn hỗ trợ” hoặc “Linux chắc chắn không hỗ trợ”. Kiểm tra tại runtime vì kết quả còn phụ thuộc session đồ họa, window manager, liên kết ứng dụng, quyền người dùng, JDK/provider và chính sách của hệ thống.

## 2. Ba tầng kiểm tra khi gọi API phụ thuộc desktop

```text
1. Có giao diện đồ họa khả dụng?
   GraphicsEnvironment.isHeadless()
               |
       headless? ── Có ──> Fallback không cần desktop
               |
              Không
               v
2. API/capability cấp nền tảng được hỗ trợ?
   Desktop.isDesktopSupported()
   Taskbar.isTaskbarSupported()
   SystemTray.isSupported()
               |
         không ──────────> Fallback
               |
              Có
               v
3. Thao tác/tính năng cụ thể được hỗ trợ?
   Desktop.isSupported(action)
   Taskbar.isSupported(feature)
               |
       không ────────────> Fallback
               |
              Có
               v
   Gọi thao tác thực tế trong try/catch
   (vẫn có thể lỗi do file/URI/permission/handler)
```

### Tầng 1 — Headless

`GraphicsEnvironment.isHeadless()` kiểm tra môi trường có thể hỗ trợ màn hình, bàn phím và chuột hay không. `true` là tín hiệu không thực hiện hoạt động cần desktop GUI. Đáng chú ý, một máy chạy Windows hoặc macOS vẫn có thể bị đặt vào chế độ headless; một container Linux cũng có thể không có display server. `-Djava.awt.headless=true` chủ động bật chế độ này.

`false` **không chứng minh** máy có đủ mọi dịch vụ desktop. Vì vậy còn phải kiểm tra API/thao tác cụ thể và xử lý lỗi lúc chạy.

### Tầng 2 — Có API cấp nền tảng không?

- `Desktop.isDesktopSupported()` trước `Desktop.getDesktop()`.
- `Taskbar.isTaskbarSupported()` trước `Taskbar.getTaskbar()`.
- `SystemTray.isSupported()` trước `SystemTray.getSystemTray()`.
- Với chụp ảnh màn hình hoặc điều khiển chuột/bàn phím bằng `Robot`, cần môi trường không headless **và** thử tạo `new Robot()` trong `try/catch` vì quyền điều khiển/ghi hình có thể bị hệ điều hành hạn chế.

### Tầng 3 — Có tính năng cụ thể không?

Có `Desktop` chưa đủ để `PRINT`, `EDIT`, `BROWSE` hay `MOVE_TO_TRASH` đều hoạt động. Dùng `desktop.isSupported(Desktop.Action.XXX)`. Tương tự, có `Taskbar` chưa đủ để hiển thị progress, badge hay menu; dùng `taskbar.isSupported(Taskbar.Feature.XXX)`.

Ngay cả khi `isSupported(...)` trả `true`, thao tác trên **file/URI cụ thể** vẫn có thể thất bại. Ví dụ `OPEN` được hỗ trợ nhưng chưa có ứng dụng mặc định cho loại file. Hãy giữ fallback rõ ràng và xử lý `IOException`, `UnsupportedOperationException` cùng lỗi truy cập/đối số phù hợp theo hợp đồng API.

## 3. Bảng kiểm tra API hiện hành

| Nhu cầu | Kiểm tra trước khi gọi | API cần bảo vệ | Fallback hợp lý |
| --- | --- | --- | --- |
| Mở file ảnh bằng ứng dụng mặc định | `!isHeadless()`, `Desktop.isDesktopSupported()`, `desktop.isSupported(OPEN)` | `desktop.open(file)` | Đưa đường dẫn/tệp tải xuống cho người dùng, xử lý ảnh trong ứng dụng |
| Mở URL trong trình duyệt | Các kiểm tra Desktop + `BROWSE` | `desktop.browse(uri)` | Hiển thị nút/link để người dùng tự mở trên client |
| Soạn email bằng ứng dụng email | Các kiểm tra Desktop + `MAIL` | `desktop.mail(uri)` | Hiển thị địa chỉ/liên kết `mailto:` |
| In file qua ứng dụng được đăng ký | Các kiểm tra Desktop + `PRINT` | `desktop.print(file)` | Tạo file đầu ra, dùng quy trình in của ứng dụng |
| Mở trình quản lý file, chọn file | Các kiểm tra Desktop + `BROWSE_FILE_DIR` | `desktop.browseFileDirectory(file)` | Cho người dùng đường dẫn hoặc cơ chế duyệt file của ứng dụng |
| Chuyển file vào Trash/Recycle Bin | Các kiểm tra Desktop + `MOVE_TO_TRASH`; phải có xác nhận của người dùng | `desktop.moveToTrash(file)` | Không tự xóa khi tính năng không có; báo không hỗ trợ |
| Cập nhật tiến trình taskbar/dock | `!isHeadless()`, `Taskbar.isTaskbarSupported()`, `taskbar.isSupported(PROGRESS_VALUE)` | `taskbar.setProgressValue(value)` | Thanh tiến trình trong UI/log |
| Hiển thị tray icon | `!isHeadless()`, `SystemTray.isSupported()` | `SystemTray.getSystemTray()`, `add(trayIcon)` | Notification trong app hoặc log |
| Chụp màn hình bằng Robot | `!isHeadless()`, tạo `Robot` thành công, kiểm tra quyền và vùng capture | `robot.createScreenCapture(rect)` | Không chụp, yêu cầu người dùng cấp quyền hoặc cung cấp ảnh |
| Đọc/ghi định dạng ảnh | `ImageIO.getImageReadersByFormatName(format).hasNext()` và `getImageWritersByFormatName(...)` | `ImageIO.read`, `ImageIO.write` | Dùng định dạng/codec có sẵn hoặc báo lỗi |
| Vẽ ảnh hoàn toàn trong bộ nhớ | Không cần desktop/headful; dùng `BufferedImage` + `Graphics2D` | `createGraphics()`, `draw...` | Không cần fallback theo OS; xử lý IO/giới hạn bộ nhớ nếu lưu file |

`java.desktop` là module chứa các API AWT/Swing và ImageIO trên các JDK Java SE hiện đại. Nếu dùng `module-info.java`, khai báo `requires java.desktop;`. Khi ứng dụng được đóng gói thành custom runtime qua `jlink`, cũng cần bảo đảm module tương ứng nằm trong runtime image.

## 4. Desktop: kiểm tra hỗ trợ chung và từng action

### 4.1. Các action thường dùng

`Desktop.Action` cung cấp các action quen thuộc `OPEN`, `EDIT`, `PRINT`, `BROWSE`, `MAIL`; từ Java 9 có thêm `BROWSE_FILE_DIR` và `MOVE_TO_TRASH`. Cách dùng chuẩn:

```java
if (!GraphicsEnvironment.isHeadless() && Desktop.isDesktopSupported()) {
    Desktop desktop = Desktop.getDesktop();
    if (desktop.isSupported(Desktop.Action.BROWSE)) {
        // Tại đây mới xem xét gọi desktop.browse(uri) theo nhu cầu người dùng.
    }
}
```

Đây là **đoạn minh họa** cần import `java.awt.Desktop` và `java.awt.GraphicsEnvironment`. Kiểm tra `Desktop.isDesktopSupported()` trước `getDesktop()` là cần thiết vì `getDesktop()` có thể ném `HeadlessException` hoặc `UnsupportedOperationException` khi môi trường không phù hợp.

### 4.2. Khi đã hỗ trợ action, vẫn có thể lỗi

Ví dụ `Desktop.Action.OPEN` trả `true` là thông tin cấp nền tảng. Nó **không xác nhận** rằng file `example.png` tồn tại, có quyền đọc hoặc có viewer mặc định. `Desktop.open(...)` có thể ném `IOException` nếu không mở được ứng dụng liên kết. Kiểm tra capability và thử thao tác thành công là hai sự kiện khác nhau.

Các điểm cần nhớ theo action:

- `OPEN`: truyền `File` thật sự tồn tại; OS tìm ứng dụng mặc định của loại file.
- `BROWSE`: truyền `URI` hợp lệ, tốt nhất hạn chế scheme theo nhu cầu (thường là `https`). Không dùng chuỗi URI không tin cậy để gọi OS handler tùy ý.
- `MAIL`: máy phải có ứng dụng mail mặc định hỗ trợ `mailto:`; nhiều máy chủ không có.
- `EDIT`/`PRINT`: tính năng phụ thuộc association và ứng dụng đích, không tương đương “chỉnh sửa” hoặc “in” mọi định dạng file.
- `BROWSE_FILE_DIR`: `Desktop.browseFileDirectory(file)` muốn tìm **thư mục chứa file và chọn file**; file và thư mục cha phải tồn tại.
- `MOVE_TO_TRASH`: `Desktop.moveToTrash(file)` trả `boolean` cho biết thao tác thành công hay không. Đây là hành động ảnh hưởng dữ liệu, chỉ gọi khi người dùng đã chủ động yêu cầu/đồng ý và bạn đã xác minh đúng file.

### 4.3. Ví dụ helper mở ảnh an toàn theo khả năng

Đoạn mã sau là một **phương thức để đưa vào class của ứng dụng**, không phải chương trình độc lập. Nó chỉ nên được gọi khi người dùng nhấn lệnh **Mở ảnh**, hoặc một sự kiện được phép mở ứng dụng bên ngoài:

```java
import java.awt.Desktop;
import java.awt.GraphicsEnvironment;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

static boolean tryOpenImage(Path imagePath) {
    if (!Files.isRegularFile(imagePath)) {
        return false;
    }
    if (GraphicsEnvironment.isHeadless() || !Desktop.isDesktopSupported()) {
        return false;
    }

    try {
        Desktop desktop = Desktop.getDesktop();
        if (!desktop.isSupported(Desktop.Action.OPEN)) {
            return false;
        }
        desktop.open(imagePath.toFile());
        return true; // Đã yêu cầu OS mở; chưa chắc viewer đã hiển thị thành công.
    } catch (IOException | IllegalArgumentException
             | UnsupportedOperationException | SecurityException ex) {
        // Ứng dụng thật nên ghi log phù hợp, không lộ đường dẫn nhạy cảm.
        return false;
    }
}
```

**Giới hạn của helper:** `return true` chỉ cho biết Java gửi được yêu cầu mở file, không bảo đảm viewer bên ngoài thực sự hiển thị ảnh. Các điều kiện có thể thay đổi giữa lúc kiểm tra và lúc gọi, do đó `try/catch` vẫn cần thiết. Nếu đây là dịch vụ web, `desktop.open(...)` mở trên **máy đang chạy JVM**, không mở trình xem ảnh trên máy của người duyệt web. Với web app, hãy trả ảnh hoặc URL hợp lệ về client để trình duyệt xử lý.

## 5. Chương trình Java 17+ hoàn chỉnh kiểm tra mà không gọi GUI nguy hiểm

Chương trình `DesktopCapabilityCheck` in ra hỗ trợ runtime của `Desktop`, các action tiêu biểu, `Taskbar`, `SystemTray` và các codec PNG đã đăng ký. Nó còn tạo một ảnh PNG 16 × 16 bằng `BufferedImage` để chứng minh **tạo ảnh không cần desktop**. Chương trình **không tự mở cửa sổ, in file hay chuyển file vào thùng rác**.

Lưu file **`DesktopCapabilityCheck.java`**:

```java
import java.awt.Color;
import java.awt.Desktop;
import java.awt.Graphics2D;
import java.awt.GraphicsEnvironment;
import java.awt.SystemTray;
import java.awt.Taskbar;
import java.awt.image.BufferedImage;
import java.io.IOException;
import java.nio.file.Path;
import javax.imageio.ImageIO;

public final class DesktopCapabilityCheck {
    public static void main(String[] args) throws IOException {
        boolean headless = GraphicsEnvironment.isHeadless();
        System.out.println("Headless: " + headless);

        boolean desktopAvailable = !headless && Desktop.isDesktopSupported();
        System.out.println("Desktop available: " + desktopAvailable);
        if (desktopAvailable) {
            Desktop desktop = Desktop.getDesktop();
            for (Desktop.Action action : new Desktop.Action[] {
                    Desktop.Action.BROWSE,
                    Desktop.Action.OPEN,
                    Desktop.Action.EDIT,
                    Desktop.Action.PRINT,
                    Desktop.Action.MAIL,
                    Desktop.Action.BROWSE_FILE_DIR,
                    Desktop.Action.MOVE_TO_TRASH
            }) {
                System.out.println("Desktop." + action
                        + ": " + desktop.isSupported(action));
            }
        }

        boolean taskbarAvailable = !headless && Taskbar.isTaskbarSupported();
        System.out.println("Taskbar available: " + taskbarAvailable);
        if (taskbarAvailable) {
            Taskbar taskbar = Taskbar.getTaskbar();
            System.out.println("Taskbar progress supported: "
                    + taskbar.isSupported(Taskbar.Feature.PROGRESS_VALUE));
        }

        boolean trayAvailable = !headless && SystemTray.isSupported();
        System.out.println("System tray available: " + trayAvailable);

        boolean pngReader = ImageIO.getImageReadersByFormatName("png").hasNext();
        boolean pngWriter = ImageIO.getImageWritersByFormatName("png").hasNext();
        System.out.println("PNG reader: " + pngReader);
        System.out.println("PNG writer: " + pngWriter);

        if (pngWriter) {
            BufferedImage image = new BufferedImage(
                    16, 16, BufferedImage.TYPE_INT_ARGB);
            Graphics2D g = image.createGraphics();
            try {
                g.setColor(Color.BLUE);
                g.fillRect(0, 0, 16, 16);
            } finally {
                g.dispose();
            }
            if (!ImageIO.write(image, "png", Path.of("sample.png").toFile())) {
                throw new IOException("No PNG writer accepted the image");
            }
            System.out.println("PNG saved: sample.png");
        }
    }
}
```

### Cách chạy để tái hiện môi trường headless

```bash
javac -encoding UTF-8 DesktopCapabilityCheck.java
java "-Djava.awt.headless=true" DesktopCapabilityCheck
```

Với bộ JDK chuẩn có PNG reader/writer đi kèm, stdout của lệnh trên:

```text
Headless: true
Desktop available: false
Taskbar available: false
System tray available: false
PNG reader: true
PNG writer: true
PNG saved: sample.png
```

Lệnh tạo file `sample.png` ngay trong thư mục hiện hành. Kết quả đã được **biên dịch bằng `javac --release 17` và chạy trên JDK 24** với chế độ headless; PNG được tạo thực tế. Nếu provider ImageIO của môi trường thay đổi, có thể không có writer PNG, chương trình sẽ không tạo file và sẽ in `PNG writer: false`; không được giả định hỗ trợ mọi codec.

Chạy **không** đặt `java.awt.headless=true` trên máy có desktop:

```bash
java DesktopCapabilityCheck
```

Kết quả `Headless`, `Desktop available`, từng action và Taskbar/SystemTray **không cố định**. Có thể `Desktop available: true` nhưng `Desktop.MOVE_TO_TRASH: false`; điều này hoàn toàn bình thường. Máy có desktop không có nghĩa mọi feature được hỗ trợ.

### Tại sao thứ tự kiểm tra trong mã đúng?

1. `GraphicsEnvironment.isHeadless()` ngăn truy cập GUI khi thiếu display.
2. `Desktop.isDesktopSupported()` được gọi trước `Desktop.getDesktop()`; chỉ khi có desktop mới kiểm tra từng `Desktop.Action`.
3. `Taskbar.isTaskbarSupported()` được gọi trước `Taskbar.getTaskbar()`; hỗ trợ `PROGRESS_VALUE` được kiểm tra riêng.
4. `SystemTray.isSupported()` là điều kiện trước khi lấy `SystemTray` và thêm icon trong ứng dụng thật.
5. `ImageIO` được kiểm tra bằng **registry codec**, độc lập với tình trạng desktop; `BufferedImage` + `Graphics2D` có thể render vào bộ nhớ ở chế độ headless.
6. Sau khi vẽ xong phải `dispose()` đối tượng `Graphics2D`; `ImageIO.write(...)` trả `boolean` để báo có writer phù hợp, hoặc có thể ném `IOException` nếu xuất file lỗi.

Chương trình là **báo cáo khả năng**, chưa phải bảo đảm tác vụ GUI cụ thể sẽ thành công: khi muốn mở browser, in hoặc dùng tray icon, mã thực thi phải kiểm tra điều kiện đầu vào và bắt lỗi riêng.

## 6. Taskbar và SystemTray: kiểm tra hai lớp hỗ trợ

### 6.1. `Taskbar` (Java 9+)

`java.awt.Taskbar` cho phép tích hợp với vùng taskbar/dock như biểu tượng ứng dụng, badge, menu hay progress **tùy tính năng của nền tảng**. Sử dụng như sau:

```java
if (!GraphicsEnvironment.isHeadless() && Taskbar.isTaskbarSupported()) {
    Taskbar taskbar = Taskbar.getTaskbar();
    if (taskbar.isSupported(Taskbar.Feature.PROGRESS_VALUE)) {
        taskbar.setProgressValue(40); // Giá trị 0..100 cho tác vụ có tiến độ.
    }
}
```

Đây là **đoạn minh họa** cần import `java.awt.Taskbar` và `java.awt.GraphicsEnvironment`. Đừng cập nhật tiến độ theo một con số cố định trong ứng dụng thật: lấy phần trăm từ tác vụ, và chỉ cập nhật nếu feature được hỗ trợ. `Taskbar.isTaskbarSupported()==true` **không bảo đảm** có `PROGRESS_VALUE`. Trên một số desktop environment, Taskbar hoàn toàn không khả dụng. Nếu không hỗ trợ, hãy hiển thị progress trong cửa sổ ứng dụng, nội dung web hoặc log.

Các feature khác như `PROGRESS_VALUE_WINDOW`, `ICON_BADGE_TEXT`, `MENU` hay yêu cầu user attention cũng phải được kiểm tra riêng bằng `isSupported(feature)` trước khi gọi các phương thức tương ứng. Một số thao tác window-specific còn yêu cầu cửa sổ đang hiển thị hợp lệ.

### 6.2. `SystemTray`

`SystemTray.isSupported()` kiểm tra khả năng tiếp cận khay hệ thống, nhưng **không cam kết mọi thao tác menu, icon và event** đều hoạt động giống nhau. Nếu được hỗ trợ, ứng dụng mới tạo `TrayIcon` và thêm vào tray; `SystemTray.add(...)` có thể ném `AWTException` (ví dụ giới hạn không gian hoặc môi trường).

```java
if (!GraphicsEnvironment.isHeadless() && SystemTray.isSupported()) {
    SystemTray tray = SystemTray.getSystemTray();
    // Tạo TrayIcon có image và listener phù hợp, rồi gọi tray.add(icon).
    // Khi thoát ứng dụng: tray.remove(icon).
}
```

Đoạn mã trên là **minh họa**, chưa phải chương trình độc lập; cần import `SystemTray`, `GraphicsEnvironment`. Khi có tray icon, nên có hành vi thay thế trong UI nếu người dùng không thấy icon. Không đặt chức năng quan trọng chỉ ở system tray vì một số môi trường không cung cấp hoặc ẩn vùng đó.

## 7. Robot và ảnh chụp màn hình: kiểm tra quyền thực tế

`java.awt.Robot` có thể tạo ảnh chụp màn hình với `createScreenCapture(Rectangle)` hoặc gửi sự kiện bàn phím/chuột. Đây là API desktop mức thấp, phụ thuộc cả **session đồ họa lẫn quyền của hệ điều hành**. `!GraphicsEnvironment.isHeadless()` là điều kiện cần nhưng **chưa đủ**: hệ điều hành có thể chặn truy cập màn hình hoặc điều khiển input. `new Robot()` có thể ném `AWTException` nếu không được cấp khả năng điều khiển.

Đoạn minh họa dưới đây **không tự chạy**; chỉ nên thực hiện khi ứng dụng được người dùng cấp quyền chụp màn hình và có nhu cầu rõ ràng:

```java
if (!GraphicsEnvironment.isHeadless()) {
    try {
        Robot robot = new Robot();
        Rectangle bounds = GraphicsEnvironment
                .getLocalGraphicsEnvironment()
                .getDefaultScreenDevice()
                .getDefaultConfiguration()
                .getBounds();
        BufferedImage capture = robot.createScreenCapture(bounds);
        // Lưu hoặc xử lý capture theo quyền và yêu cầu của người dùng.
    } catch (AWTException | SecurityException ex) {
        // Có thể do thiếu quyền, display hoặc input-control extension.
    }
}
```

Các import cần có: `java.awt.Robot`, `java.awt.Rectangle`, `java.awt.AWTException`, `java.awt.GraphicsEnvironment`, `java.awt.image.BufferedImage`. Khi đa màn hình, DPI scaling hoặc window manager khác nhau, `Rectangle` và coordinate system phải được xử lý đúng; không giả định màn hình đầu tiên có tọa độ (0,0) hay mọi cửa sổ đều có thể bị chụp.

Chụp ảnh màn hình không giống **xử lý ảnh bitmap trong bộ nhớ**: tạo `BufferedImage`, chuyển màu, crop, resize, xử lý PNG không đòi quyền chụp màn hình. Nếu chỉ tạo thumbnail/biểu đồ/ảnh phía server, nên dùng đường xử lý ảnh headless.

## 8. Xử lý hình ảnh: kiểm tra codec thay vì tên hệ điều hành

Khả năng đọc/ghi ảnh của `javax.imageio.ImageIO` phụ thuộc các `ImageReader`/`ImageWriter` được đăng ký bởi provider. Đây là kiểm tra **codec**, không phải kiểm tra desktop:

```java
boolean canReadWebp =
        ImageIO.getImageReadersByFormatName("webp").hasNext();
boolean canWritePng =
        ImageIO.getImageWritersByFormatName("png").hasNext();
```

Đây là đoạn minh họa cần import `javax.imageio.ImageIO`. `false` với một định dạng không nói rằng hệ điều hành không mở được định dạng đó trong ứng dụng khác; nó chỉ cho biết **ImageIO provider trong JVM hiện tại** không khai báo hỗ trợ cho tên format được hỏi. Chẳng hạn, codec của trình duyệt hệ điều hành và codec ImageIO là hai hệ sinh thái khác nhau. Codec tùy chọn có thể được bổ sung qua ImageIO service provider phù hợp; đừng mặc định JDK tự hỗ trợ mọi định dạng hiện đại.

### Đọc ảnh cần kiểm tra nội dung thật

```java
BufferedImage image = ImageIO.read(Path.of("input.png").toFile());
if (image == null) {
    throw new IOException("Không có ImageReader phù hợp với dữ liệu ảnh");
}
System.out.println(image.getWidth() + "x" + image.getHeight());
```

Đây là đoạn minh họa cần import `java.awt.image.BufferedImage`, `java.nio.file.Path`, `javax.imageio.ImageIO` và `java.io.IOException`. `ImageIO.read` có thể trả `null` nếu không tìm thấy reader; nó cũng có thể ném `IOException` nếu tệp không truy cập được hoặc dữ liệu ảnh lỗi. Hãy giới hạn kích thước tệp, pixel count và tài nguyên khi xử lý file do người dùng gửi lên để tránh sử dụng quá nhiều bộ nhớ.

### Tạo ảnh không cần cửa sổ

`BufferedImage` là ảnh trong bộ nhớ; `Graphics2D` vẽ lên ảnh này, không yêu cầu window manager. Demo ở mục 5 chứng minh `java.awt.headless=true` vẫn tạo `sample.png`. Vì vậy **không bao quanh mọi xử lý ảnh bằng `if (!isHeadless())`**; chỉ các thao tác cần hiển thị lên desktop hoặc tương tác màn hình mới cần guard như vậy.

### Ảnh nhiều độ phân giải và HiDPI (Java 9+)

`MultiResolutionImage` và `BaseMultiResolutionImage` cung cấp nhiều phiên bản hình ảnh theo kích cỡ để UI sử dụng biến thể phù hợp trên màn hình có mật độ pixel khác nhau. Đây là API có sẵn từ Java 9, vẫn hữu ích với Swing/AWT ngày nay. Không cần viết nhánh “Windows dùng 2x, macOS dùng 3x”: hãy cung cấp biến thể theo kích thước nếu thiết kế icon cần độ nét HiDPI, rồi để cơ chế hiển thị chọn biến thể thích hợp.

Ví dụ **đoạn mã minh họa** khi đã có hai ảnh `Image icon16` và `Image icon32`:

```java
Image multiSizeIcon = new BaseMultiResolutionImage(icon16, icon32);
```

Cần import `java.awt.Image` và `java.awt.image.BaseMultiResolutionImage`. Hai ảnh phải có kích thước tương ứng và được sắp theo thứ tự từ nhỏ đến lớn. Đây là tính năng nội dung ảnh, không thay cho `Desktop.isSupported` hay `Taskbar.isSupported` khi muốn hiển thị icon trong shell hệ điều hành.

## 9. Thiết kế fallback và nơi thực hiện kiểm tra

Một ứng dụng desktop có thể chọn hành vi theo ưu tiên:

1. Người dùng yêu cầu tác vụ, ví dụ **Xem ảnh**, **In**, **Mở thư mục chứa ảnh**.
2. Ứng dụng kiểm tra dữ liệu đầu vào (file/URI hợp lệ, quyền xử lý), tiếp đến `isHeadless`, API support và action support.
3. Nếu đủ điều kiện, gọi đúng API **trong `try/catch`**, xử lý lỗi nếu OS không tìm thấy ứng dụng liên kết hoặc không thể thực hiện.
4. Nếu không được, dùng fallback đúng nhu cầu: hiển thị ảnh bên trong Swing UI, cung cấp đường dẫn/tải ảnh, hoặc thông báo tính năng không hỗ trợ. Không tự động chạy lệnh OS thay thế không được kiểm soát.
5. Với hành động có thay đổi dữ liệu như `moveToTrash` hoặc việc in tài liệu, chỉ kích hoạt từ thao tác đã được người dùng yêu cầu; thông báo trạng thái dựa trên kết quả API thật.

**Không kiểm tra một lần rồi tin mãi mãi:** người dùng có thể thay ứng dụng mặc định, kết nối remote desktop thay đổi, quyền hệ thống hoặc plugin đổi trong phiên làm việc. Có thể cache kết quả để hiển thị nút UI, nhưng khi người dùng nhấn hãy xác minh điều kiện hiện tại và xử lý exception.

**Máy nào thực hiện?** `Desktop.open`, `Desktop.browse`, `Taskbar` và `SystemTray` vận hành trên **máy chủ của tiến trình JVM**. Nếu Java chạy trong web backend hoặc container cloud, các API không thể điều khiển trình duyệt hay desktop trên máy người dùng từ xa. Ở kiến trúc client/server, backend nên tạo ảnh/URL hoặc trả response cho client; frontend nhận sự kiện người dùng và dùng API trình duyệt phù hợp.

**Tính an toàn:** Với `Desktop.browse` và `open`, cần xác nhận URI/file đến từ nguồn tin cậy, không dùng scheme tùy ý hoặc path được ghép từ input chưa kiểm tra. Đối với `Robot`, việc truy cập màn hình/chuột/bàn phím phải theo quyền thực tế của người sử dụng. Không gắn tính năng desktop vào job chạy tự động trên server nếu business logic chỉ cần xử lý dữ liệu.

## 10. Lỗi thường gặp và cách chẩn đoán

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `HeadlessException` khi gọi `Desktop.getDesktop()` hoặc GUI API | JVM đang headless, thiếu display hoặc bật cờ headless | Kiểm tra `GraphicsEnvironment.isHeadless()` từ sớm, cung cấp fallback |
| `UnsupportedOperationException` khi gọi Desktop action | Hệ điều hành/window manager không cung cấp action | Kiểm tra `Desktop.isDesktopSupported()` và `Desktop.isSupported(action)` trước |
| `desktop.isSupported(OPEN)==true` nhưng `desktop.open(file)` lỗi | File không tồn tại, không có ứng dụng liên kết hoặc ứng dụng ngoài không khởi chạy được | Kiểm tra `Files.isRegularFile`, bắt `IOException`, hiển thị đường dẫn/ảnh bên trong ứng dụng |
| `BROWSE_FILE_DIR` không có hoặc không chọn được file | File manager không hỗ trợ hoặc file/thư mục cha không tồn tại | Kiểm tra action, đường dẫn đầu vào; fallback hiển thị path |
| `moveToTrash(file)` trả `false` | Thao tác chuyển file không thành công dù action có thể được hỗ trợ | Giữ file nguyên trạng; thông báo, không tự xóa vĩnh viễn |
| `Taskbar.isTaskbarSupported()==true` nhưng set progress lỗi | `Taskbar.Feature.PROGRESS_VALUE` không được cung cấp | Kiểm tra `taskbar.isSupported(PROGRESS_VALUE)` và có UI fallback |
| `SystemTray.isSupported()==true` nhưng thêm icon lỗi | Giới hạn tray, môi trường/khoảng trống hoặc quyền bị hạn chế | Bắt `AWTException`, giữ chức năng trong UI |
| `Robot` tạo lỗi `AWTException` | OS không cấp low-level input/screen permission | Không cố vượt quyền; yêu cầu người dùng cấu hình quyền rồi thử lại |
| `ImageIO.read(...)` trả `null` | Không có codec nhận dạng dữ liệu ảnh | Kiểm tra ImageReader theo format và chất lượng dữ liệu; dùng codec được triển khai |
| `ImageIO.write(...)` trả `false` | Không có ImageWriter phù hợp | Kiểm tra provider bằng `getImageWritersByFormatName`, chọn định dạng được hỗ trợ |
| Docker/CI không có GUI, nhưng xuất PNG thành công | `BufferedImage` và ImageIO có thể chạy offscreen | Đó là hành vi đúng; đừng bắt cả pipeline ảnh phụ thuộc desktop |
| Chạy được trên máy dev nhưng thất bại ở production | Khác JDK runtime, desktop session, OS permission, file association, codec SPI | Chạy capability probe trực tiếp trên runtime production tương đương và ghi kết quả |

**Không dùng `os.name` làm nguồn quyết định chính:** “Windows/Linux/macOS” chỉ là nhãn tổng quát. Hai máy cùng OS nhưng khác window manager, account session, tool association hoặc policy có thể hỗ trợ hai tập feature khác nhau.

## 11. Kiểm thử thực tế trên nhiều môi trường

Một chiến lược kiểm thử gọn mà hữu ích:

| Môi trường | Chạy gì? | Kết quả cần quan sát |
| --- | --- | --- |
| CI/headless | `java "-Djava.awt.headless=true" DesktopCapabilityCheck` | Không gọi GUI; file PNG được tạo khi codec có |
| Windows/macOS/Linux có desktop | `java DesktopCapabilityCheck` | Ghi khả năng desktop/action/taskbar/tray thực tế; không giả định YES |
| Máy không có ứng dụng mặc định cho một loại file | Helper `tryOpenImage(...)` trên file được phép | `false`/lỗi được xử lý mềm, không làm hỏng tác vụ chính |
| Host cần chụp màn hình | `Robot` trong test có sự đồng ý và quyền thích hợp | Không chụp nếu thiếu quyền; ghi rõ lý do |
| Custom runtime image hoặc thêm codec | Chạy probe ImageIO tại môi trường deploy | Codec cần thiết được đăng ký và hoạt động với dữ liệu thử |

Trong unit test, có thể tách capability check khỏi hành động thật bằng một giao diện ứng dụng để mock kết quả có/không hỗ trợ. Còn các tình huống tương tác desktop và kết quả liên kết ứng dụng nên được kiểm thử như **integration test có điều kiện** trên máy thích hợp; test CI headless chỉ chứng minh nhánh fallback, không chứng minh GUI hoạt động trên mọi hệ điều hành.

Một số tình huống có giá trị kiểm thử: nhận đường dẫn tệp không tồn tại; ảnh có phần mở rộng hợp lệ nhưng dữ liệu hỏng; codec chưa được đăng ký; không có trình duyệt mặc định; action được báo hỗ trợ nhưng OS trả lỗi; thùng rác không khả dụng; ứng dụng chạy trong máy chủ remote. Không cần đoán version OS để tái hiện những nhánh này.

## 12. Checklist trước khi gọi API phụ thuộc hệ điều hành

1. Phân loại thao tác: có cần **desktop của máy JVM** không, hay chỉ cần xử lý ảnh trong bộ nhớ?
2. Nếu cần desktop: kiểm tra `GraphicsEnvironment.isHeadless()` trước.
3. Chọn đúng cặp `isSupported`: `Desktop.isDesktopSupported`/`Desktop.Action`, `Taskbar.isTaskbarSupported`/`Taskbar.Feature` hoặc `SystemTray.isSupported`.
4. Kiểm tra đầu vào `File`/`URI`, quyền người dùng và quy tắc bảo mật; không tạo side effect khi chưa có sự kiện tác vụ phù hợp.
5. Gọi API trong `try/catch`; phân biệt **không hỗ trợ** với **action được hỗ trợ nhưng thao tác cụ thể thất bại**.
6. Có fallback thực dụng: mở trong chính UI, cho tải file, cung cấp đường dẫn, thông báo không có feature; không phụ thuộc shell command của một OS.
7. Đối với ảnh xử lý nền: dùng `BufferedImage`, `Graphics2D`, `ImageIO` và kiểm tra **codec/plugin**, không ép JVM có GUI.
8. Với `Robot`/screen capture: kiểm tra headless, tạo Robot trong `try/catch` và tôn trọng quyền screenshot/input của hệ điều hành.
9. Test nhánh headless và nhánh desktop trên môi trường được hỗ trợ; làm mới phép kiểm tra khi deployment đổi.
10. Trên ứng dụng client/server, xử lý Desktop trên **client phù hợp**, không trông chờ backend Java mở trình duyệt của người dùng.

## 13. Tài liệu Java chính thống còn áp dụng

- Oracle Java SE 25: [`Desktop`](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/java/awt/Desktop.html) — `isDesktopSupported`, `isSupported(Action)`, `open`, `browse`, `browseFileDirectory`, `moveToTrash`.
- Oracle Java SE 25: [`Taskbar`](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/java/awt/Taskbar.html) — `isTaskbarSupported` và `isSupported(Feature)`, từ Java 9.
- Oracle Java SE 25: [`SystemTray`](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/java/awt/SystemTray.html) — khả năng tray/icon và giới hạn nền tảng.
- Oracle Java SE 25: [`GraphicsEnvironment`](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/java/awt/GraphicsEnvironment.html) — `isHeadless` và các thao tác cần display.
- Oracle Java SE 25: [`Robot`](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/java/awt/Robot.html) — quyền và giới hạn điều khiển input/chụp màn hình.
- Oracle Java SE 26: [`ImageIO`](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/javax/imageio/ImageIO.html) — reader/writer discovery, `read`, `write`.
- Oracle Java SE 25: [`BaseMultiResolutionImage`](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/java/awt/image/BaseMultiResolutionImage.html) — biến thể HiDPI, tính năng Java 9 vẫn sử dụng được.
