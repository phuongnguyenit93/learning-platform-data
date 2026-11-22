# HiDPI và khác biệt giữa tọa độ logic với pixel vật lý trong Java Desktop (Java 9+)

## 1. Vì sao bài toán HiDPI quan trọng?

Khi lập trình Swing, AWT hoặc Java 2D, một nút rộng **100 đơn vị tọa độ** không nhất thiết chiếm đúng **100 pixel vật lý** trên màn hình. Hệ điều hành có thể đặt mức scale 125%, 150% hoặc 200% để giao diện hiển thị có kích thước dễ đọc trên màn hình mật độ điểm ảnh cao (**HiDPI**, High Dots Per Inch). JDK hiện đại phối hợp với hệ thống đồ họa để xử lý phần lớn phép scale khi vẽ giao diện.

Bài toán thường gặp: ứng dụng vẽ hình rõ ở 100% nhưng bị mờ ở 200%; vị trí nhấp chuột bị lệch; ảnh chụp màn hình có kích thước pixel khác `frame.getWidth()`; khi kéo cửa sổ sang monitor có độ scale khác, bản vẽ không còn khớp. Nguyên nhân nền tảng là nhầm lẫn giữa **không gian tọa độ logic** và **pixel của thiết bị**.

Các API cần biết trong Java 9+ vẫn có trong Java hiện hành: `GraphicsConfiguration.getDefaultTransform()`, `Graphics2D.getTransform()`, `AffineTransform`, `BufferedImage`, `MultiResolutionImage`, và `Robot.createMultiResolutionScreenCapture(...)` (API này có từ Java 9). Không cần dùng thư viện lỗi thời hoặc can thiệp vào pixel vật lý của hệ điều hành để dựng giao diện Swing thông thường.

## 2. Ba khái niệm phải tách bạch

| Khái niệm | Đơn vị và ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Tọa độ logic** (user space) | Đơn vị mà mã Java 2D/Swing thường dùng để bố trí, vẽ, nhận sự kiện chuột. | `g.drawRect(10, 10, 100, 50)`. |
| **Tọa độ thiết bị** (device space) | Không gian đích mà hệ thống render ánh xạ tới; với màn hình HiDPI, mỗi đơn vị logic có thể phủ nhiều pixel. | Scale 2×: hình 100×50 đơn vị logic tương ứng vùng xấp xỉ 200×100 pixel thiết bị. |
| **Pixel của bitmap** | Phần tử ảnh thật trong `BufferedImage`/PNG/JPEG; kích thước lấy bằng `getWidth()/getHeight()`. | `new BufferedImage(200, 100, ...)` tạo đúng 200×100 pixel dữ liệu, bất kể monitor. |

**Không nhầm DPI với scale:** DPI vật lý là mật độ pixel trên mỗi inch của màn hình; OS UI scale (125%, 150%, 200%) là hệ số hiển thị do hệ thống chọn, phụ thuộc chính sách DPI của nền tảng. Scale 2× **không khẳng định** màn hình có DPI vật lý chính xác gấp đôi. `Toolkit.getDefaultToolkit().getScreenResolution()` cũng không phải cách đáng tin để suy ra mọi màn hình có bao nhiêu pixel vật lý trên mỗi đơn vị logic.

### Ví dụ quy đổi dễ hình dung

Giả sử đang xét một hình chữ nhật ở vị trí logic `(x=10, y=20)`, kích thước **160×80** đơn vị; transform chỉ có scale đồng nhất, không có xoay/shear/translation:

| Mức UI scale | Hệ số | Kích thước vùng xấp xỉ trong pixel |
| --- | ---: | ---: |
| 100% | `1.00×` | 160×80 |
| 125% | `1.25×` | 200×100 |
| 150% | `1.50×` | 240×120 |
| 200% | `2.00×` | 320×160 |

Ở 150%, điểm logic `(10,20)` có thể ánh xạ thành `(15,30)` trong không gian pixel tương đối. Đây là **mô hình minh họa của phép scale thuần**; tọa độ màn hình tuyệt đối còn có vị trí cửa sổ, gốc của monitor và các phép transform khác.

**Lưu ý:** Scale không bắt buộc là số nguyên. Với tỉ lệ 1.25, độ rộng logic 101 tương ứng 126.25 đơn vị thiết bị theo toán học; khi rasterize, pixel nguyên, anti-aliasing và quy tắc làm tròn sẽ quyết định vùng pixel thực sự được tô. Không thể bảo đảm phép `(int) (logical * scale)` chính xác cho mọi hình vẽ.

## 3. Java 2D chuyển từ logic sang thiết bị như thế nào?

Hệ thống render dùng một `AffineTransform`:

```text
tọa độ của component / Java 2D user space
                  |
                  | default transform của GraphicsConfiguration
                  | + transform do ứng dụng thêm nếu có
                  v
tọa độ trong Java 2D device space
                  |
                  | rasterizer + anti-aliasing + clipping
                  v
các pixel của surface / màn hình
```

`AffineTransform` là phép biến đổi affine 2D, có thể biểu diễn scale, translation, rotation và shear:

```text
x_device = m00 * x_user + m01 * y_user + m02
y_device = m10 * x_user + m11 * y_user + m12
```

Với trường hợp phổ biến chỉ có scale theo hai trục và translation:

```text
x_device = scaleX * x_user + translateX
y_device = scaleY * y_user + translateY
```

Không phải mọi transform đều có `scaleX == scaleY`. Nếu có xoay/shear, lấy `getScaleX()` và nhân trực tiếp với width cũng không đủ: phải biến đổi cả hình, hoặc biến đổi các góc để tìm bounding box phù hợp.

### API nào trả scale thực tế?

Đối với một cửa sổ đang hiển thị:

```java
GraphicsConfiguration config = frame.getGraphicsConfiguration();
AffineTransform defaultTx = config.getDefaultTransform();
double scaleX = defaultTx.getScaleX();
double scaleY = defaultTx.getScaleY();
```

Đây là **đoạn mã tích hợp**: `frame` là `JFrame`/`Window` đang có `GraphicsConfiguration`. Với cấu hình màn hình HiDPI thông thường, `defaultTx` chứa scale từ user space sang device space. Nếu cần lấy transform của một `Graphics2D` cụ thể đang vẽ, dùng `g2.getTransform()`:

```java
@Override
protected void paintComponent(Graphics graphics) {
    super.paintComponent(graphics);
    Graphics2D g2 = (Graphics2D) graphics.create();
    try {
        AffineTransform current = g2.getTransform();
        // current có thể gồm default transform và transform hiện hành.
        g2.drawRect(10, 10, 100, 50); // Kích thước trong user space.
    } finally {
        g2.dispose();
    }
}
```

Mã trên là **thân phương thức của một lớp kế thừa `JPanel`**, không phải một file chạy riêng. `current` không nhất thiết chỉ gồm scale màn hình: Java 2D có thể đã áp dụng translation do Swing/component hoặc do code vẽ trước đó.

**Phân biệt hai transform thường bị nhầm:**

- `GraphicsConfiguration.getDefaultTransform()`: biến đổi mặc định cho thiết bị/đích vẽ. Trên màn hình HiDPI có thể là 1.25×, 1.5×, 2×... tùy OS/JDK/monitor; với `BufferedImage` độc lập thường là identity.
- `GraphicsConfiguration.getNormalizingTransform()`: phục vụ quy đổi kích thước vật lý theo mô hình **72 user-space units = 1 inch**, dựa trên thông tin thiết bị. Đây **không phải** API chuẩn để hỏi hệ số UI scale của màn hình.
- `Graphics2D.getTransform()`: phép biến đổi **hiện tại** của context vẽ, có thể đã gồm default scale và các biến đổi người lập trình thêm.

**Đừng gọi `g2.setTransform(new AffineTransform())` trong `paintComponent` để “đặt scale lại 100%”**: điều đó có thể xóa transform HiDPI và translation mà Java/Swing cần. Muốn vẽ trong hệ tọa độ riêng, tạo một bản sao `Graphics2D` qua `graphics.create()` rồi `translate/scale/rotate` trên bản sao đó; `dispose()` xong không ảnh hưởng context của caller.

## 4. Ví dụ Java 17 tự chạy: đổi logic → pixel và tạo bitmap đúng độ phân giải

Chương trình dưới đây dùng scale giả lập `scaleX=1.5`, `scaleY=2.0` để có stdout **tất định**, kể cả khi chạy headless, CI hoặc máy không có màn hình HiDPI. Nó minh họa phép `AffineTransform.transform(...)` và phép nghịch đảo `createInverse()`, sau đó tạo bitmap với số pixel tương ứng.

**Lưu thành `HiDpiCoordinates.java`:**

```java
import java.awt.Color;
import java.awt.Graphics2D;
import java.awt.geom.AffineTransform;
import java.awt.geom.Point2D;
import java.awt.image.BufferedImage;
import java.io.File;
import java.util.Locale;
import javax.imageio.ImageIO;

public class HiDpiCoordinates {
    public static void main(String[] args) throws Exception {
        double scaleX = 1.5, scaleY = 2.0;
        AffineTransform toPixels =
                AffineTransform.getScaleInstance(scaleX, scaleY);

        Point2D logical = new Point2D.Double(120, 40);
        Point2D physical = toPixels.transform(logical, null);
        Point2D back = toPixels.createInverse()
                .transform(physical, null);

        int logicalWidth = 160, logicalHeight = 80;
        int pixelWidth = (int) Math.ceil(logicalWidth * scaleX);
        int pixelHeight = (int) Math.ceil(logicalHeight * scaleY);
        BufferedImage output = new BufferedImage(
                pixelWidth, pixelHeight, BufferedImage.TYPE_INT_ARGB);

        Graphics2D g = output.createGraphics();
        try {
            g.setColor(Color.WHITE);
            g.fillRect(0, 0, pixelWidth, pixelHeight);
            g.scale(scaleX, scaleY);
            g.setColor(Color.BLUE);
            g.fillRect(10, 10, 50, 20);
        } finally {
            g.dispose();
        }
        ImageIO.write(output, "png", new File("hidpi-demo.png"));

        System.out.printf(Locale.ROOT,
                "Logical: (%.1f, %.1f)%n", logical.getX(), logical.getY());
        System.out.printf(Locale.ROOT,
                "Pixels: (%.1f, %.1f)%n", physical.getX(), physical.getY());
        System.out.printf(Locale.ROOT,
                "Round trip: (%.1f, %.1f)%n", back.getX(), back.getY());
        System.out.printf(Locale.ROOT,
                "Image pixels: %d x %d%n", output.getWidth(), output.getHeight());
    }
}
```

**Biên dịch/chạy với JDK 17+** (không cần thư viện ngoài):

```bash
javac -encoding UTF-8 --release 17 HiDpiCoordinates.java
java HiDpiCoordinates
```

**Stdout chính xác:**

```text
Logical: (120.0, 40.0)
Pixels: (180.0, 80.0)
Round trip: (120.0, 40.0)
Image pixels: 240 x 160
```

Ngoài stdout, chương trình ghi `hidpi-demo.png` có kích thước **240×160 pixel**. Phần `g.scale(scaleX, scaleY)` làm cho lệnh vẽ `fillRect(10, 10, 50, 20)` được hiểu bằng **đơn vị logic** và chuyển sang bitmap độ phân giải lớn hơn. Phần tô nền trắng được thực hiện *trước* phép scale để phủ đủ toàn bộ buffer.

Ví dụ chỉ mô phỏng quy đổi bằng transform; **không tuyên bố máy đang dùng màn hình 150% theo X và 200% theo Y**. Trong ứng dụng thật, scale cần lấy từ cấu hình thiết bị/graphics context phù hợp. `Math.ceil` ở đây là lựa chọn cấp phát buffer đủ kích thước khi chỉ có scale dương; nó không mô tả đầy đủ pixel coverage của mọi hình quay, shear hoặc anti-aliasing.

## 5. Ví dụ Swing: đo scale của màn hình đang hiển thị và vẽ đúng logic

Lớp sau tạo cửa sổ Swing, đo `GraphicsConfiguration.getDefaultTransform()` và vẽ hình chữ nhật **100×40 đơn vị logic**. Không chủ động “nhân đôi” `drawRect` vì Java 2D đã xử lý transform HiDPI của context.

**Lưu thành `SwingHiDpiInspector.java`:**

```java
import java.awt.Color;
import java.awt.Dimension;
import java.awt.Graphics;
import java.awt.Graphics2D;
import java.awt.GraphicsConfiguration;
import java.awt.GraphicsEnvironment;
import java.awt.geom.AffineTransform;
import java.util.Locale;
import javax.swing.JFrame;
import javax.swing.JPanel;
import javax.swing.SwingUtilities;

public class SwingHiDpiInspector {
    public static void main(String[] args) {
        if (GraphicsEnvironment.isHeadless()) {
            System.out.println("Không có môi trường desktop.");
            return;
        }
        SwingUtilities.invokeLater(() -> {
            JFrame frame = new JFrame("HiDPI Inspector");
            JPanel panel = new JPanel() {
                @Override protected void paintComponent(Graphics graphics) {
                    super.paintComponent(graphics);
                    Graphics2D g2 = (Graphics2D) graphics.create();
                    try {
                        AffineTransform tx = g2.getTransform();
                        g2.setColor(Color.BLUE);
                        g2.fillRect(20, 20, 100, 40);
                        g2.setColor(Color.BLACK);
                        g2.drawString(String.format(Locale.ROOT,
                                "Draw scale X=%.2f Y=%.2f",
                                tx.getScaleX(), tx.getScaleY()), 20, 100);
                    } finally {
                        g2.dispose();
                    }
                }
            };
            panel.setPreferredSize(new Dimension(440, 150));
            frame.setContentPane(panel);
            frame.pack();
            frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
            frame.setLocationRelativeTo(null);
            frame.setVisible(true);

            GraphicsConfiguration gc = frame.getGraphicsConfiguration();
            AffineTransform transform = gc.getDefaultTransform();
            System.out.printf(Locale.ROOT, "Screen scale X=%.2f Y=%.2f%n",
                    transform.getScaleX(), transform.getScaleY());
        });
    }
}
```

**Chạy:**

```bash
javac -encoding UTF-8 --release 17 SwingHiDpiInspector.java
java SwingHiDpiInspector
```

Trên máy có desktop, chương trình mở cửa sổ và in dòng `Screen scale X=... Y=...`. Ví dụ với thiết bị áp scale 1.5×, số có thể là `1.50`, nhưng **không thể ấn định stdout duy nhất** vì phụ thuộc OS, driver, JDK và cấu hình màn hình. Trong chế độ headless, chương trình in đúng:

```text
Không có môi trường desktop.
```

Khi chạy trên máy có hai màn hình khác scale, hãy kéo cửa sổ qua từng màn hình và **đọc lại `frame.getGraphicsConfiguration().getDefaultTransform()`** thay vì lưu cố định số vừa in ở startup; một số môi trường chỉ cập nhật graphics configuration khi quá trình chuyển màn hình hoàn tất. Trong `paintComponent`, hãy tôn trọng `Graphics2D` mà Swing truyền vào. Thực tế môi trường GUI có thể cần gọi `repaint/revalidate` khi dữ liệu/layout phụ thuộc scale thay đổi.

**Hai ví dụ trong bài đã được biên dịch với `javac --release 17` và kiểm thử phần không phụ thuộc GUI trên OpenJDK 24.0.2.** Ví dụ Swing đã kiểm tra nhánh headless; việc kéo cửa sổ qua monitor có DPI khác phải được xác minh trên hệ điều hành/monitor thật.

## 6. Tọa độ chuột: component, window, desktop, bitmap là các hệ khác nhau

Khi xử lý sự kiện Swing:

```java
@Override
public void mouseClicked(java.awt.event.MouseEvent event) {
    java.awt.Point inComponent = event.getPoint();
    System.out.println("Click trong component: " + inComponent);
}
```

`MouseEvent.getPoint()` trả tọa độ **trong component sinh ra sự kiện**. Nó không có nghĩa là chỉ số pixel trong PNG và không nên nhân tay với 1.25 hoặc 2.0 để xác định nút nào được nhấn. Các phép hit-test và layout Swing thường dùng cùng hệ tọa độ logic của component.

Nếu cần chuyển giữa hai component Swing, dùng API tọa độ của Swing:

```java
Point pointInTarget = SwingUtilities.convertPoint(
        sourceComponent, event.getPoint(), targetComponent);
```

Đây là mã **tích hợp**: `sourceComponent` là component nguồn, `targetComponent` là component đích trong hệ phân cấp Swing, `event` là `MouseEvent` nhận được từ nguồn. `SwingUtilities.convertPoint(...)` chuyển tọa độ giữa **hai hệ component**; đó không phải hàm biến tọa độ logic thành pixel màn hình vật lý.

Với thông tin vị trí trên desktop, AWT cung cấp `Component.getLocationOnScreen()` và `GraphicsConfiguration.getBounds()` theo hệ tọa độ màn hình/thiết bị mà nền tảng và `GraphicsDevice` công bố. Trên desktop nhiều màn hình, gốc màn hình phụ có thể có tọa độ âm, hoặc các màn hình dùng coordinate system riêng. Không lấy origin monitor ở Java rồi coi như offset pixel vật lý tuyệt đối của toàn bộ OS trong mọi trường hợp.

**Quy tắc thực tế:** trước khi nhân scale, hãy ghi rõ *tọa độ đầu vào đang ở hệ nào* (local component? virtual desktop? Java 2D user space? pixels trong `BufferedImage`?) và *API tiếp nhận kỳ vọng hệ nào*. Chỉ transform khi thực sự đi qua ranh giới giữa các hệ.

## 7. Vẽ đồ họa không bị nhân scale hai lần

Trong `paintComponent(Graphics)`, Java 2D thường đã có phép biến đổi từ user space sang thiết bị. Code đúng nên làm:

```java
Graphics2D g2 = (Graphics2D) graphics.create();
try {
    g2.setColor(Color.BLUE);
    g2.fillRoundRect(10, 10, 120, 48, 12, 12);
} finally {
    g2.dispose();
}
```

Đây là **đoạn mã tích hợp** với tham số `graphics` do Swing cung cấp. Không nhân tay `x`, `y`, `width`, `height` với `getDefaultTransform().getScaleX()` trong thao tác vẽ chuẩn, vì khi đó hình có thể bị scale **hai lần**. Nếu muốn zoom riêng cho nội dung, nhân thêm biến đổi có chủ đích:

```java
Graphics2D g2 = (Graphics2D) graphics.create();
try {
    g2.translate(20, 20);
    g2.scale(1.25, 1.25); // Zoom nội dung 125%, bổ sung lên transform hiện có.
    g2.drawRect(0, 0, 100, 60);
} finally {
    g2.dispose();
}
```

`g2.scale(...)` trong trường hợp này là **zoom do ứng dụng chọn**, độc lập với hệ số màn hình. `Graphics2D.setTransform(...)` nên dùng để **khôi phục transform đã lưu**, không dùng tùy tiện để xóa default transform của màn hình HiDPI. Mặc định Java 2D áp dụng anti-aliasing/hint theo cấu hình; để đường biên rõ trên scale phân số, cân nhắc `RenderingHints.KEY_ANTIALIASING`, độ dày `BasicStroke` và vị trí pixel, nhưng **không** nên sửa mọi tọa độ thành integer pixel rồi bỏ qua transform.

## 8. Bitmap, icon và ảnh nhiều độ phân giải

### 8.1. BufferedImage lưu đúng số pixel được khai báo

`BufferedImage` là dữ liệu raster có `width×height` pixel thật:

```java
BufferedImage image = new BufferedImage(
        400, 200, BufferedImage.TYPE_INT_ARGB);
System.out.println(image.getWidth() + "x" + image.getHeight());
```

Đoạn này có stdout `400x200`, không thay đổi dù máy đang scale 125%, 150% hay 200%. Khi hiển thị vào component, Java 2D có thể vẽ bitmap với phép scale khác; nếu chỉ có bản 16×16 rồi phóng to lên 32×32, kết quả dễ bị mờ hoặc thiếu chi tiết.

### 8.2. MultiResolutionImage cho ảnh cần nhiều mức chi tiết

`java.awt.image.MultiResolutionImage` và `java.awt.image.BaseMultiResolutionImage` là API chuẩn, vẫn được hỗ trợ. Khi chuẩn bị icon cho HiDPI, có thể cung cấp các biến thể 1×/2× thay vì chỉ có bản thấp rồi phóng to:

```java
BufferedImage image1x = ImageIO.read(Path.of("icon-16.png").toFile());
BufferedImage image2x = ImageIO.read(Path.of("icon-32.png").toFile());
MultiResolutionImage icon = new BaseMultiResolutionImage(image1x, image2x);
Image suitable = icon.getResolutionVariant(32, 32);
```

**Đoạn minh họa tích hợp** trên cần imports `java.awt.Image`, `java.awt.image.BufferedImage`, `java.awt.image.MultiResolutionImage`, `java.awt.image.BaseMultiResolutionImage`, `java.nio.file.Path` và `javax.imageio.ImageIO`. Hai tệp icon cần tồn tại thật. `getResolutionVariant(32,32)` cho implementation chọn biến thể phù hợp theo kích thước yêu cầu; không giả định mọi monitor sẽ chỉ có scale 1×/2× hoặc Java luôn chọn một ảnh cố định.

Với hình vector hoặc `Graphics2D` vẽ trực tiếp, Java có thể rasterize ở độ phân giải của surface nên việc giữ vector thường sắc nét hơn việc kéo giãn bitmap nhỏ.

### 8.3. Robot.createMultiResolutionScreenCapture — API có từ Java 9

`java.awt.Robot.createScreenCapture(Rectangle)` trả về `BufferedImage`; nếu ứng dụng cần ảnh chụp có **biến thể độ phân giải native** khi surface HiDPI có scale, hãy dùng:

```java
Robot robot = new Robot(window.getGraphicsConfiguration().getDevice());
MultiResolutionImage capture =
        robot.createMultiResolutionScreenCapture(window.getBounds());

for (Image variant : capture.getResolutionVariants()) {
    System.out.println(variant.getWidth(null) + "x"
            + variant.getHeight(null));
}
```

Đây là **mã tích hợp**, chạy trong môi trường desktop hỗ trợ screen capture, cần imports `java.awt.Robot`, `java.awt.Image`, `java.awt.Window` và `java.awt.image.MultiResolutionImage`; `window` là một cửa sổ nằm trong vùng tọa độ của `GraphicsDevice` mà `Robot` đang sử dụng. Cần xử lý `AWTException`/`SecurityException`/`IllegalArgumentException` theo môi trường. Các nền tảng hiện đại có thể yêu cầu người dùng cấp quyền ghi/chụp màn hình. Thực hiện capture **ngoài Event Dispatch Thread (EDT)** vì thao tác có thể chậm.

Theo contract của Java, trên màn hình không scale có thể chỉ có **một** biến thể ảnh bằng kích thước người dùng yêu cầu; trên màn hình HiDPI có thể có **hai** biến thể: ảnh cơ sở kích thước người dùng yêu cầu và ảnh ở độ phân giải pixel thiết bị. Đừng hardcode rằng `variants.get(1)` luôn có mặt; hãy duyệt và chọn theo kích thước thật. Với cửa sổ trải trên nhiều monitor có scale khác nhau, cần kiểm thử và có thể chụp riêng từng vùng monitor thay vì suy ra một scale duy nhất.

Dù tên phương thức là “capture”, giá trị `window.getBounds()` vẫn là rectangle trong hệ tọa độ màn hình mà AWT/Robot làm việc. Không nên tự nhân tọa độ `Rectangle` với scale rồi truyền lại cho `Robot` — có thể khiến chụp sai vùng.

## 9. Nhiều màn hình và thay đổi scale lúc ứng dụng đang chạy

Trên hệ thống có nhiều `GraphicsDevice`:

```java
GraphicsEnvironment ge =
        GraphicsEnvironment.getLocalGraphicsEnvironment();

for (GraphicsDevice device : ge.getScreenDevices()) {
    GraphicsConfiguration gc = device.getDefaultConfiguration();
    AffineTransform tx = gc.getDefaultTransform();
    System.out.println(device.getIDstring()
            + " scale=" + tx.getScaleX() + "x" + tx.getScaleY());
}
```

Đây là **đoạn tích hợp** cần imports `java.awt.GraphicsEnvironment`, `java.awt.GraphicsDevice`, `java.awt.GraphicsConfiguration` và `java.awt.geom.AffineTransform`. Chỉ thực hiện khi môi trường có màn hình (`!GraphicsEnvironment.isHeadless()`). Nó lấy scale của **cấu hình mặc định trên từng màn hình**; scale thực đang dùng bởi một component/cửa sổ cần đọc từ `component.getGraphicsConfiguration()` hoặc graphics context đúng thời điểm.

Hệ quả khi kéo cửa sổ từ màn hình A (100%) sang B (200%):

- Kích thước **logic** của component không nhất thiết đổi từ 200 thành 400.
- Số **pixel thiết bị** dùng để hiển thị cùng diện tích logic có thể tăng.
- Bitmap cache/screenshot cần chọn lại biến thể hoặc render lại khi môi trường đổi.
- Các giá trị scale, monitor và bounds đã cache có thể trở nên cũ.

Giá trị scale thực tế phụ thuộc nền tảng: Windows, macOS và Linux/X11/Wayland có cách xử lý DPI và mức scale khác nhau, có thể có giới hạn với scale phân số hoặc từng monitor. Không đưa ra giả định “mọi hệ điều hành đều scale chính xác 150%” hoặc “mọi lần di chuyển cửa sổ đều có thông báo đổi DPI giống nhau”. Dùng API Java hiện hành và thử nghiệm trên nền tảng triển khai thật.

## 10. Khi nào phải tự đổi đơn vị, khi nào không?

| Tình huống | Cách xử lý |
| --- | --- |
| Bố trí/paint Swing (size, preferredSize, `drawRect`, `drawString`) | Dùng đơn vị logic và transform mà Swing đã cấp; **không tự nhân OS scale lần nữa**. |
| Hit-test `MouseEvent` trong component | Dùng `event.getX()/getY()` và geometry cùng hệ component; chuyển component bằng `SwingUtilities.convertPoint` khi cần. |
| Vẽ vào `BufferedImage` để xuất PNG 2× | Tự tạo buffer pixel lớn hơn và `g.scale(2,2)`, vì `BufferedImage.createGraphics()` không tự biến thành màn hình 2×. |
| Chuyển tọa độ model sang surface có `AffineTransform` đã biết | Dùng `transform(point, ...)`; chiều ngược dùng `createInverse()`, xử lý `NoninvertibleTransformException`. |
| Đọc hệ số HiDPI màn hình của cửa sổ | `window.getGraphicsConfiguration().getDefaultTransform()`, kiểm tra lại khi cửa sổ chuyển màn hình. |
| Xem transform của thao tác paint hiện hành | `g2.getTransform()`; có thể gồm nhiều phép biến đổi chứ không chỉ scale. |
| Chụp màn hình cần độ phân giải gốc | Cân nhắc `Robot.createMultiResolutionScreenCapture`, xử lý permission và từng monitor. |
| Tạo icon dễ đọc ở nhiều scale | Dùng vector hoặc `MultiResolutionImage` với nhiều biến thể có chi tiết phù hợp. |
| Muốn biết độ lớn vật lý chính xác của màn hình | Không suy luận chỉ từ `getScaleX()`; cần thông tin DPI vật lý đáng tin từ môi trường ngoài khi bài toán thực sự yêu cầu. |

## 11. Các lỗi điển hình

| Triệu chứng | Nguyên nhân và cách khắc phục |
| --- | --- |
| Nút/viền được vẽ quá lớn ở 200% | Đã **nhân scale hai lần** trong `paintComponent`. Trả về vẽ logic trong context Java 2D mặc định. |
| Ảnh icon mờ ở 150%/200% | Bitmap nguồn có quá ít pixel và bị nội suy khi phóng. Cung cấp vector hoặc `MultiResolutionImage` nhiều biến thể. |
| Vùng chọn bằng chuột lệch | Trộn tọa độ `MouseEvent`, tọa độ màn hình hoặc pixel bitmap. Đổi về cùng hệ trước hit-test. |
| `g2.getTransform()` không chỉ là scale | Có translation/rotation do component hoặc code vẽ. Xem toàn bộ matrix, tránh chỉ nhân `getScaleX/Y()`. |
| `getDefaultTransform()` trả identity trên CI | Chạy headless, surface offscreen hoặc desktop không bật scale. Không giả định luôn có màn hình. |
| PNG xuất ra 160×80 khi kỳ vọng 320×160 | Tạo `BufferedImage(160,80)`; OS scale không tự tăng kích thước pixel trong file. Cấp phát buffer lớn hơn. |
| Screenshot chỉ có độ phân giải logic | Đang dùng `createScreenCapture`/biến thể cơ sở. Xem `createMultiResolutionScreenCapture` và các variant, nếu nền tảng hỗ trợ. |
| Screenshot sai vùng monitor | Trộn không gian tọa độ AWT/Robot, cộng offset màn hình sai hoặc dùng `Robot` của device khác. Lấy đúng graphics device và rectangle tương ứng. |
| Đường kẻ 1 đơn vị nhìn nhòe | Tại scale phân số, một đường có thể phủ nhiều pixel và cần anti-aliasing. Đánh giá hints, stroke và vị trí theo thiết kế; không ép mọi nét vào một pixel vật lý. |
| Cửa sổ đẹp ở 100% nhưng lệch sau khi chuyển monitor | Đã cache scale hoặc kích thước buffer; kiểm tra lại graphics configuration và render lại tài nguyên phụ thuộc scale. |

## 12. Checklist kiểm thử giao diện HiDPI

1. Kiểm thử thật trên **100%, 125%, 150%, 200%** nếu các mức đó được nền tảng hỗ trợ; lưu ý OS/JDK có thể áp dụng giá trị khác với con số hiển thị trong Settings.
2. Kiểm tra cỡ chữ, vùng nhấp, icon, stroke 1 unit, đường ranh giữa component, cuộn, text caret và menu.
3. Kéo cửa sổ giữa hai monitor có scale khác nhau, kiểm tra layout và sự sắc nét của icon sau khi chuyển màn hình.
4. Với thao tác vẽ riêng, log `GraphicsConfiguration.getDefaultTransform()` và `Graphics2D.getTransform()` tại đúng chỗ; xác nhận chưa nhân scale hai lần.
5. Với screenshot/ảnh xuất, kiểm tra **kích thước `BufferedImage` thật** và số biến thể `MultiResolutionImage`; không phỏng đoán theo pixel hiển thị.
6. Chạy unit test phần biến đổi tọa độ ở chế độ headless; với render/Robot, thêm integration test trên desktop và xử lý quyền màn hình.
7. Nếu cần debug môi trường, kiểm tra tài liệu Java 2D Properties/JDK hiện hành; các cờ `sun.java2d.*` là chi tiết triển khai/tùy nền tảng, **không nên xem như API chuẩn để sửa mọi vấn đề HiDPI trong mã ứng dụng**.

## 13. Câu hỏi ôn tập

1. **Một JPanel rộng 200 đơn vị logic trên màn hình scale 200% sẽ báo `getWidth()` bằng 400 chứ?**  
   Không nhất thiết. `getWidth()` phản ánh kích thước của component trong hệ tọa độ Swing; vùng thiết bị có thể dùng khoảng 400 pixel, còn kích thước logic của component vẫn 200.

2. **Có nên lấy `getDefaultTransform().getScaleX()` rồi nhân tất cả `drawRect` của Swing?**  
   Không. `Graphics2D` đang vẽ thường đã chứa transform HiDPI; tự nhân thêm dễ gây scale hai lần.

3. **`BufferedImage(100,50)` ở monitor 2× chứa bao nhiêu pixel dữ liệu?**  
   Vẫn 100×50 pixel. Muốn xuất ảnh 2×, phải tạo buffer 200×100 và vẽ với scale tương ứng hoặc dùng nguồn ảnh độ phân giải cao.

4. **Chuyển từ tọa độ logic sang pixel rồi ngược lại bằng API nào?**  
   `AffineTransform.transform(point, null)` và `createInverse().transform(point, null)`, với transform đúng hệ tọa độ và có khả năng nghịch đảo.

5. **`Robot.createMultiResolutionScreenCapture` hữu ích khi nào?**  
   Khi cần ảnh chụp có các biến thể theo độ phân giải người dùng yêu cầu và độ phân giải thiết bị ở màn hình HiDPI, thay vì mặc định một `BufferedImage`.

6. **Màn hình 200% có luôn đồng nghĩa ảnh của ứng dụng xuất ra file sẽ là 2× không?**  
   Không. Ảnh trong file có pixel theo kích thước buffer/encoder mà ứng dụng tạo, độc lập với scale hiển thị hiện tại.

## 14. Tài liệu chính thức còn hiệu lực

- [`GraphicsConfiguration` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/java/awt/GraphicsConfiguration.html): `getDefaultTransform()`, `getNormalizingTransform()`, `getBounds()`.
- [`Graphics2D` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/java/awt/Graphics2D.html): user space → device space, `getTransform()`, `scale()` và cảnh báo khi dùng `setTransform()`.
- [`AffineTransform` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/java/awt/geom/AffineTransform.html): ma trận tọa độ, `transform()` và `createInverse()`.
- [`Robot` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/java/awt/Robot.html): `createMultiResolutionScreenCapture()` (since 9), coordinate system và quyền chụp màn hình.
- [`MultiResolutionImage` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/java/awt/image/MultiResolutionImage.html): ảnh có nhiều biến thể độ phân giải.
- [`BufferedImage` — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/java/awt/image/BufferedImage.html): ảnh raster và kích thước pixel thật.
- [Java SE 26 — Troubleshooting Guide, Java 2D Properties](https://docs.oracle.com/en/java/javase/26/troubleshoot/java-2d-properties.html): hành vi scale có khác biệt giữa Windows, macOS, Linux và các tùy chọn triển khai.
