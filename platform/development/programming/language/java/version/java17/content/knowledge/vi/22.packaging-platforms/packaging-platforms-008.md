# Pipeline Metal trên macOS và kiểm thử Java 2D trong Java 17

## 1. Metal pipeline là gì?

Java 2D là nền tảng đồ họa của Java, cung cấp API để vẽ hình học, ảnh, văn bản và các hiệu ứng màu. Swing và AWT sử dụng Java 2D để hiển thị giao diện và nội dung lên màn hình.

Trên macOS, Java 2D có thể dùng một **rendering pipeline** để chuyển các lệnh vẽ của Java thành thao tác đồ họa native. Từ Java 17, HotSpot/JDK có thêm pipeline sử dụng **Apple Metal**, thông qua JEP 382 (*New macOS Rendering Pipeline*). Pipeline này là lựa chọn hiện đại thay cho pipeline OpenGL cũ.

Metal là API đồ họa cấp thấp của Apple, được thiết kế để khai thác GPU và các khả năng đồ họa của hệ điều hành. Java 2D vẫn giữ nguyên API Java như `Graphics2D`, `BufferedImage`, `VolatileImage`, `JComponent` và `paintComponent()`. Việc chọn Metal thay đổi phần triển khai nội bộ của Java 2D, không yêu cầu viết lại mã Swing hoặc AWT.

Trong Java 17, Metal **có sẵn nhưng chưa được bật mặc định**. Ứng dụng cần yêu cầu pipeline bằng system property:

~~~text
-Dsun.java2d.metal=true
~~~

Pipeline Metal yêu cầu macOS 10.14.x trở lên. Trên phiên bản macOS cũ hơn, yêu cầu bật Metal sẽ bị bỏ qua. Oracle xác nhận rằng Metal được hỗ trợ trong JDK 17 và JDK 18 nhưng chỉ trở thành pipeline mặc định từ JDK 19.

Điểm cần nhớ khi đọc tài liệu Java 2D: **Java 17 và Java 19+ có mặc định khác nhau**. Nếu chạy đúng JDK 17, không được giả định Metal đã được chọn chỉ vì runtime có hỗ trợ nó.

## 2. Metal, OpenGL và phiên bản JDK

### 2.1. Trạng thái pipeline theo phiên bản

| Runtime | Metal | OpenGL trên macOS |
|---|---|---|
| JDK 17 | Có hỗ trợ, mặc định tắt; bật bằng `-Dsun.java2d.metal=true`. | Là pipeline mặc định trong cấu hình JDK 17 thông thường. |
| JDK 18 | Có hỗ trợ, mặc định tắt. | Vẫn là pipeline mặc định thông thường. |
| JDK 19 trở lên | Metal được bật mặc định. | Không còn là pipeline mặc định. |

Apple đã đánh dấu OpenGL là API deprecated. Tuy nhiên, trong JDK 17, OpenGL vẫn là đường render mặc định được giữ lại để tương thích. Khi kiểm thử ứng dụng Java 17, có thể dùng nó làm đường baseline để so sánh với Metal; với dự án mới, nên ưu tiên kiểm thử Metal và lên kế hoạch nâng JDK khi phù hợp.

### 2.2. Chọn pipeline bằng system property

Trên JDK 17, bật Metal:

~~~text
java -Dsun.java2d.metal=true -jar app.jar
~~~

Tắt yêu cầu Metal để quay về pipeline mặc định của JDK 17:

~~~text
java -Dsun.java2d.metal=false -jar app.jar
~~~

Có thể yêu cầu OpenGL rõ ràng khi cần một lượt kiểm thử baseline:

~~~text
java -Dsun.java2d.opengl=true -jar app.jar
~~~

Các property `sun.java2d.metal` và `sun.java2d.opengl` là tùy chọn triển khai nội bộ của JDK, không phải API Java SE được bảo đảm ổn định giữa mọi vendor/build. Đặt chúng trên command line khi khởi chạy JVM. Không đợi tới khi Swing đã tạo component hoặc AWT đã khởi tạo mới gọi `System.setProperty()`; lúc đó Java 2D có thể đã chọn pipeline.

### 2.3. Không nhầm Java 2D Metal với JavaFX Metal

JEP 382 nói về pipeline Java 2D của JDK, được Swing và AWT sử dụng. JavaFX có hệ thống rendering riêng (Prism) và có các tùy chọn pipeline riêng. Bật `-Dsun.java2d.metal=true` không đồng nghĩa với việc JavaFX đã chuyển sang Metal.

Nếu ứng dụng dùng cả Swing và JavaFX, hãy kiểm thử hai hệ thống đồ họa theo đúng runtime và tài liệu tương ứng. Không dùng kết quả của một bài test JavaFX để kết luận pipeline Java 2D đã hoạt động.

## 3. Java 2D pipeline tác động tới phần nào?

Java 2D cung cấp một API đồ họa thống nhất, còn pipeline quyết định cách các primitive được thực thi trên nền tảng cụ thể. Các lệnh phổ biến có thể gồm:

- Vẽ đường, hình chữ nhật, ellipse, path và polygon.
- Tô màu, gradient, stroke và clipping.
- Alpha compositing và transparency.
- Vẽ ảnh, scale, rotate và transform.
- Render glyph và text.
- Render vào cửa sổ, back buffer hoặc một số bề mặt offscreen có khả năng tăng tốc.

Ví dụ, đoạn code sau không cần biết máy đang dùng Metal hay OpenGL:

~~~java
void drawScene(Graphics2D g) {
    g.setColor(Color.BLUE);
    g.fillRoundRect(20, 20, 180, 90, 18, 18);
    g.setColor(Color.WHITE);
    g.drawString("Java 2D", 55, 72);
}
~~~

Trên macOS với JDK 17, pipeline được chọn sẽ xử lý các thao tác phù hợp. Một số thao tác có thể được tăng tốc bằng GPU; những thao tác khác có thể đi qua đường xử lý phần mềm. Việc dùng Metal không có nghĩa mọi lệnh `Graphics2D` đều được thực thi trên GPU.

### 3.1. Những bề mặt render quan trọng

| Bề mặt đích | Đặc điểm khi kiểm thử |
|---|---|
| Cửa sổ Swing/AWT trên màn hình | Quan trọng nhất để xác nhận ứng dụng desktop hoạt động với pipeline hiển thị thực tế. |
| `VolatileImage` | Có thể được lưu trên bề mặt tăng tốc; phù hợp để kiểm tra đường offscreen có khả năng tăng tốc. |
| Back buffer của `BufferStrategy` | Phù hợp với ứng dụng vẽ liên tục, animation hoặc game dùng AWT. |
| `BufferedImage` | Ảnh nằm trong bộ nhớ Java; thường dùng đường render phần mềm, thích hợp cho kiểm thử pixel và xử lý ảnh. |

**Chỉ render vào `BufferedImage` không đủ để chứng minh Metal đang được sử dụng.** Oracle lưu ý rằng render vào `BufferedImage` gần như luôn đi qua software loops. Để kiểm tra pipeline hiển thị, hãy tạo cửa sổ thực và vẽ lên màn hình; có thể bổ sung `VolatileImage` hoặc `BufferStrategy` khi ứng dụng dùng chúng.

## 4. Điều kiện trước khi kiểm thử Metal

Trước khi bật Metal, xác nhận môi trường:

1. Máy đang chạy macOS 10.14.x trở lên.
2. JVM thực tế là JDK 17, không phải một JRE/JDK khác được IDE hoặc launcher chọn ngầm.
3. Bản JDK được xây dựng cho kiến trúc và phiên bản macOS của máy.
4. Máy có môi trường đồ họa desktop hoạt động và thiết bị hỗ trợ Metal.
5. Ứng dụng chạy trong session có màn hình; không chạy bài test cửa sổ trong headless environment.
6. Các thư viện native hoặc framework desktop của ứng dụng tương thích với JDK đang dùng.

Kiểm tra runtime:

~~~text
java -version
java -XshowSettings:properties -version
~~~

Khi cần xác nhận executable đang dùng:

~~~text
which java
which javac
~~~

Trên macOS, có thể xem kiến trúc và phiên bản hệ điều hành:

~~~text
sw_vers
uname -m
~~~

Nếu dùng IDE, hãy kiểm tra cả Project SDK, Gradle/Maven JVM và JVM options của Run Configuration. IDE có thể biên dịch bằng một JDK nhưng khởi chạy ứng dụng bằng một JDK khác.

### 4.1. Kiểm tra chế độ headless

Java 2D vẫn có thể tạo và xử lý `BufferedImage` trong headless mode, nhưng không thể dùng điều đó để kiểm thử pipeline cửa sổ trên màn hình.

Có thể in trạng thái:

~~~java
System.out.println(
        "Headless: " + java.awt.GraphicsEnvironment.isHeadless());
~~~

Nếu kết quả là `true`, hãy chuyển bài kiểm thử giao diện sang máy macOS có desktop session. Không đặt `-Djava.awt.headless=true` cho bài kiểm thử Metal.

## 5. Bật Metal trong ứng dụng Java 17

### 5.1. Chạy JAR từ terminal

~~~text
java -Dsun.java2d.metal=true -jar desktop-app.jar
~~~

Nếu chạy class trực tiếp:

~~~text
java -Dsun.java2d.metal=true -cp out com.example.DesktopApp
~~~

Nếu ứng dụng có các dependency ngoài:

~~~text
java -Dsun.java2d.metal=true -cp "out:lib/*" com.example.DesktopApp
~~~

Trên macOS, classpath nhiều entry dùng dấu `:`. Hãy thay tên class, thư mục và JAR theo dự án thực tế.

### 5.2. Cấu hình trong IDE

Trong Run/Debug Configuration, thêm JVM option:

~~~text
-Dsun.java2d.metal=true
~~~

Đây là VM option, không phải program argument. Nếu đặt nhầm vào program arguments, ứng dụng sẽ nhận chuỗi đó như một đối số command line và JVM không bật pipeline.

### 5.3. Cấu hình khi chạy qua Gradle

Với một JavaExec task, có thể truyền JVM argument trong cấu hình task:

~~~kotlin
tasks.register<JavaExec>("runWithMetal") {
    classpath = sourceSets["main"].runtimeClasspath
    mainClass.set("com.example.DesktopApp")
    jvmArgs("-Dsun.java2d.metal=true")
}
~~~

Tên task và main class là ví dụ. Nếu dùng Kotlin DSL, hãy đặt cấu hình vào build script của dự án; với Maven hoặc IDE, cấu hình VM options ở launcher tương ứng.

### 5.4. Đặt property trước khi khởi tạo AWT

Không nên bật property bên trong `paintComponent()` hoặc sau khi tạo `JFrame`:

~~~java
// Không dùng cách này để đổi pipeline sau khi GUI đã khởi tạo.
System.setProperty("sun.java2d.metal", "true");
~~~

Hãy truyền property khi khởi chạy JVM. Điều này giúp lựa chọn pipeline diễn ra ngay từ đầu và làm cho kết quả test có thể tái lập.

## 6. Tạo một Java 2D smoke test

Một smoke test hữu ích nên vẽ nhiều loại primitive thường gặp trong ứng dụng thật:

- Nền và hình học cơ bản.
- Text với font khác nhau.
- Gradient và alpha compositing.
- Antialiasing.
- Transform, clipping và stroke.
- Ảnh raster có transparency.
- Repaint, resize và thay đổi kích thước cửa sổ.

Ví dụ dưới đây tạo cửa sổ Swing và vẽ trực tiếp lên bề mặt hiển thị. Nó giúp kiểm tra ứng dụng có khởi động, repaint và hiển thị nội dung khi chạy với Metal hay không.

Tạo file `Java2DMetalSmokeTest.java`:

~~~java
import java.awt.AlphaComposite;
import java.awt.BasicStroke;
import java.awt.Color;
import java.awt.Font;
import java.awt.Graphics;
import java.awt.Graphics2D;
import java.awt.RenderingHints;
import java.awt.geom.AffineTransform;
import java.awt.geom.Ellipse2D;
import java.awt.geom.RoundRectangle2D;
import java.awt.image.BufferedImage;
import javax.swing.JFrame;
import javax.swing.JPanel;
import javax.swing.SwingUtilities;

public final class Java2DMetalSmokeTest {
    private Java2DMetalSmokeTest() {
    }

    private static final class DemoPanel extends JPanel {
        private final BufferedImage tile = createTile();

        DemoPanel() {
            setBackground(new Color(28, 32, 42));
        }

        @Override
        protected void paintComponent(Graphics graphics) {
            super.paintComponent(graphics);

            Graphics2D g = (Graphics2D) graphics.create();
            try {
                g.setRenderingHint(
                        RenderingHints.KEY_ANTIALIASING,
                        RenderingHints.VALUE_ANTIALIAS_ON);
                g.setRenderingHint(
                        RenderingHints.KEY_TEXT_ANTIALIASING,
                        RenderingHints.VALUE_TEXT_ANTIALIAS_ON);
                g.setRenderingHint(
                        RenderingHints.KEY_RENDERING,
                        RenderingHints.VALUE_RENDER_QUALITY);

                int width = getWidth();
                int height = getHeight();

                g.setPaint(new java.awt.GradientPaint(
                        0, 0, new Color(40, 90, 160),
                        width, height, new Color(24, 28, 48)));
                g.fillRect(0, 0, width, height);

                g.setColor(new Color(255, 255, 255, 210));
                g.setFont(new Font(Font.SANS_SERIF, Font.BOLD, 28));
                g.drawString("Java 2D / Metal pipeline smoke test", 28, 52);

                g.setPaint(new java.awt.GradientPaint(
                        40, 90, new Color(40, 190, 180),
                        260, 220, new Color(70, 90, 220)));
                g.fill(new RoundRectangle2D.Double(
                        40, 90, 220, 130, 24, 24));

                g.setComposite(AlphaComposite.getInstance(
                        AlphaComposite.SRC_OVER, 0.55f));
                g.setColor(new Color(255, 120, 60));
                g.fill(new Ellipse2D.Double(160, 135, 150, 120));
                g.setComposite(AlphaComposite.SrcOver);

                g.setColor(new Color(255, 255, 255, 220));
                g.setStroke(new BasicStroke(
                        4.0f, BasicStroke.CAP_ROUND,
                        BasicStroke.JOIN_ROUND));
                g.drawRoundRect(330, 100, 220, 110, 22, 22);

                AffineTransform old = g.getTransform();
                g.rotate(Math.toRadians(-8), 660, 165);
                g.setColor(new Color(250, 220, 90));
                g.fillRoundRect(590, 115, 150, 90, 18, 18);
                g.setTransform(old);

                g.drawImage(tile, 40, 270, 220, 150, null);
                g.setColor(Color.WHITE);
                g.setFont(new Font(Font.MONOSPACED, Font.PLAIN, 16));
                g.drawString("resize / repaint / alpha / transform", 290, 315);

                g.setClip(290, 340, 380, 100);
                g.setColor(new Color(120, 220, 150));
                for (int i = 0; i < 20; i++) {
                    g.drawLine(290, 340 + i * 7, 760, 440 - i * 5);
                }
            } finally {
                g.dispose();
            }
        }

        private static BufferedImage createTile() {
            BufferedImage image = new BufferedImage(
                    320, 200, BufferedImage.TYPE_INT_ARGB);
            Graphics2D g = image.createGraphics();
            try {
                g.setColor(new Color(255, 255, 255, 0));
                g.fillRect(0, 0, image.getWidth(), image.getHeight());
                g.setColor(new Color(245, 245, 250, 220));
                g.fillRoundRect(10, 10, 300, 180, 26, 26);
                g.setColor(new Color(30, 60, 100));
                g.setFont(new Font(Font.SANS_SERIF, Font.BOLD, 24));
                g.drawString("BufferedImage source", 28, 105);
            } finally {
                g.dispose();
            }
            return image;
        }
    }

    public static void main(String[] args) {
        System.out.println("Java: " + System.getProperty("java.version"));
        System.out.println("OS: " + System.getProperty("os.name"));
        System.out.println("Metal requested: "
                + System.getProperty("sun.java2d.metal", "(default)"));

        SwingUtilities.invokeLater(() -> {
            JFrame frame = new JFrame("Java 2D Metal Smoke Test");
            frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
            frame.setContentPane(new DemoPanel());
            frame.setSize(820, 520);
            frame.setLocationByPlatform(true);
            frame.setVisible(true);
        });
    }
}
~~~

Biên dịch và chạy:

~~~text
javac --release 17 -encoding UTF-8 Java2DMetalSmokeTest.java
java -Dsun.java2d.metal=true Java2DMetalSmokeTest
~~~

Khi cửa sổ xuất hiện, kéo thay đổi kích thước, chuyển qua lại giữa các cửa sổ, minimize/restore và quan sát nội dung. Kiểm tra không có vùng vẽ bị mất, nhấp nháy bất thường, sai alpha, text bị hỏng hoặc crash.

`BufferedImage` trong ví dụ chỉ là nguồn ảnh. Phần vẽ chính được thực hiện lên `JPanel` đang hiển thị trên màn hình, nên bài test có cơ hội đi qua pipeline Java 2D của macOS.

## 7. Kiểm tra VolatileImage và bề mặt tăng tốc

Một số ứng dụng tạo nội dung offscreen trước rồi copy lên màn hình. `VolatileImage` là kiểu ảnh có thể được lưu trên bề mặt tăng tốc và nội dung có thể bị mất khi hệ thống thay đổi trạng thái đồ họa.

Có thể kiểm tra khả năng tăng tốc của bề mặt sau khi đã có một component hiển thị:

~~~java
import java.awt.Graphics2D;
import java.awt.GraphicsConfiguration;
import java.awt.Transparency;
import java.awt.image.VolatileImage;

static void inspectVolatileSurface(
        GraphicsConfiguration configuration) {

    VolatileImage image =
            configuration.createCompatibleVolatileImage(
                    640, 360, Transparency.TRANSLUCENT);

    try {
        int validation = image.validate(configuration);

        Graphics2D g = image.createGraphics();
        try {
            g.fillRect(0, 0, 640, 360);
            g.drawString("Offscreen Java 2D", 24, 40);
        } finally {
            g.dispose();
        }

        System.out.println("Validation result: " + validation);
        System.out.println("Accelerated: "
                + image.getCapabilities().isAccelerated());
        System.out.println("Contents lost: " + image.contentsLost());
    } finally {
        image.flush();
    }
}
~~~

Gọi phương thức này sau khi component đã được hiển thị và có `GraphicsConfiguration`, ví dụ từ `component.getGraphicsConfiguration()`.

`ImageCapabilities.isAccelerated()` cho biết bề mặt có được tăng tốc hay không theo implementation. Nó **không xác nhận riêng rằng Metal là backend đang hoạt động**; một bề mặt có thể được tăng tốc bởi pipeline khác hoặc không được tăng tốc tùy runtime/hardware.

### 7.1. Xử lý việc nội dung VolatileImage bị mất

`VolatileImage` có thể mất nội dung khi display mode, surface hoặc tài nguyên đồ họa thay đổi. Ứng dụng phải kiểm tra `contentsLost()` và vẽ lại nếu cần.

Mẫu xử lý tổng quát:

~~~java
do {
    int state = image.validate(configuration);

    if (state == VolatileImage.IMAGE_INCOMPATIBLE) {
        image.flush();
        image = configuration.createCompatibleVolatileImage(
                width, height, Transparency.TRANSLUCENT);
    }

    if (state == VolatileImage.IMAGE_RESTORED
            || state == VolatileImage.IMAGE_INCOMPATIBLE) {
        // Vẽ lại toàn bộ nội dung vào image.
    }

    // Nếu IMAGE_OK, có thể dùng nội dung hiện tại.
} while (image.contentsLost());
~~~

Trong code thật, cần quản lý việc tạo lại image, quyền sở hữu và đồng bộ với vòng đời component. Không giả định `VolatileImage` giữ nội dung vĩnh viễn.

## 8. Kiểm thử hình ảnh: chức năng và pipeline là hai mục tiêu khác nhau

Một bộ kiểm thử Java 2D nên tách ít nhất hai nhóm:

### 8.1. Kiểm thử chức năng bằng BufferedImage

Dùng `BufferedImage` khi muốn kiểm tra kết quả pixel có tính lặp lại:

- Màu nền, kích thước và vị trí hình.
- Alpha compositing với giá trị xác định.
- Crop, scale và transform ảnh.
- Clip và vùng vẽ.
- Nội dung hình ảnh được tạo ra.

Ví dụ:

~~~java
BufferedImage image = new BufferedImage(
        200, 120, BufferedImage.TYPE_INT_ARGB);

Graphics2D g = image.createGraphics();
try {
    g.setColor(Color.RED);
    g.fillRect(10, 10, 50, 40);
} finally {
    g.dispose();
}

int pixel = image.getRGB(20, 20);
if (pixel != Color.RED.getRGB()) {
    throw new AssertionError("Unexpected pixel color");
}
~~~

Đây là test logic vẽ và màu sắc. Nó không chứng minh Metal đã được khởi tạo vì `BufferedImage` thường dùng software rendering.

### 8.2. Kiểm thử tích hợp giao diện trên macOS

Để kiểm tra Metal:

1. Khởi chạy JVM với `-Dsun.java2d.metal=true`.
2. Tạo cửa sổ thật bằng Swing/AWT.
3. Render nội dung lên component đang hiển thị.
4. Thực hiện repaint, resize, minimize/restore và thao tác người dùng.
5. Chụp ảnh màn hình bằng `java.awt.Robot` hoặc công cụ test UI.
6. So sánh với baseline phù hợp và xem log/diagnostic nếu có vấn đề.

Test này cần chạy trên macOS có desktop session và JDK 17 phù hợp. Một CI runner Linux hoặc test headless không thể xác nhận Metal trên macOS.

### 8.3. Kiểm thử hồi quy hình ảnh

Ảnh chụp từ Metal và OpenGL có thể khác nhẹ do:

- Cách rasterize glyph và antialiasing.
- Làm tròn tọa độ subpixel.
- Color profile và quản lý màu của màn hình.
- HiDPI scaling và backing scale factor.
- Khác biệt driver/hardware hoặc bản cập nhật macOS.

Vì vậy, không nên mặc định so sánh screenshot bằng phép so sánh từng byte. Có thể dùng ngưỡng sai khác màu, vùng sai khác tối đa, kiểm tra hình học/biên và các assertion riêng cho nội dung quan trọng. Những vùng text hoặc gradient thường cần tolerance phù hợp hơn các vùng màu phẳng.

## 9. Kiểm tra pipeline và primitive tracing

### 9.1. Ghi lại cấu hình lúc chạy

Trong chương trình, có thể in:

~~~java
System.out.println("java.version="
        + System.getProperty("java.version"));
System.out.println("os.name="
        + System.getProperty("os.name"));
System.out.println("sun.java2d.metal="
        + System.getProperty("sun.java2d.metal"));
System.out.println("sun.java2d.opengl="
        + System.getProperty("sun.java2d.opengl"));
~~~

Các giá trị property cho biết cấu hình yêu cầu hoặc giá trị được đọc, nhưng không phải API xác nhận backend thực tế. Nếu Metal không khởi tạo được, implementation có thể dùng đường dự phòng. Cần đối chiếu với runtime/build, log chẩn đoán phù hợp và kết quả trên màn hình.

Java SE không cung cấp một API công khai, portable để hỏi trực tiếp “pipeline Metal có đang render frame này không?”. Đừng dùng `GraphicsEnvironment`, `GraphicsConfiguration` hoặc một property string đơn lẻ làm bằng chứng tuyệt đối.

### 9.2. Primitive tracing

Java 2D có thể đếm các primitive được thực thi:

~~~text
java -Dsun.java2d.metal=true -Dsun.java2d.trace=count Java2DMetalSmokeTest
~~~

Khi JVM kết thúc, primitive tracing in danh sách primitive và số lần gọi ra console. Nó có thể giúp nhận ra các thao tác đi qua software loops. Ví dụ, những primitive dạng `MaskBlit` hoặc `General*` thường cho thấy một phần thao tác đang được xử lý bằng đường phần mềm.

Primitive tracing là công cụ chẩn đoán **đường thực thi của primitive**, không phải bằng chứng độc lập xác nhận Metal pipeline đã được chọn. Một pipeline tăng tốc vẫn có thể dùng software fallback cho thao tác mà backend không hỗ trợ hoặc không tăng tốc.

### 9.3. Không dùng chẩn đoán OpenGL như xác nhận Metal

Một số tài liệu Java 2D mô tả `J2D_TRACE_LEVEL` để xem quá trình khởi tạo OpenGL trên Linux/Windows. Không nên tự suy rộng rằng mọi thông điệp từ biến môi trường đó đều là chẩn đoán chính thức cho Metal trong mọi build JDK 17.

Khi cần xác nhận lỗi khởi tạo Metal, hãy thu thập log khởi động của đúng bản JDK, macOS, kiến trúc máy và cấu hình JVM; đồng thời tạo ví dụ tái hiện nhỏ. Nếu cần gửi bug report, cung cấp đủ thông tin môi trường và bước tái hiện.

## 10. So sánh Metal với baseline trên JDK 17

Để đánh giá ảnh hưởng của Metal, chạy cùng một ứng dụng và cùng một bộ thao tác với hai cấu hình:

~~~text
# Lượt A: yêu cầu Metal
java -Dsun.java2d.metal=true -jar app.jar

# Lượt B: không yêu cầu Metal; JDK 17 dùng pipeline mặc định
java -Dsun.java2d.metal=false -jar app.jar
~~~

Trong JDK 17 thông thường, lượt B dùng OpenGL làm baseline. Nếu muốn kiểm tra rõ cấu hình OpenGL:

~~~text
java -Dsun.java2d.opengl=true -jar app.jar
~~~

Đừng so sánh một lần chạy Metal trên máy mới với một lần chạy OpenGL trên máy khác rồi quy toàn bộ chênh lệch cho pipeline. Cần giữ môi trường càng giống nhau càng tốt.

### 10.1. Các tiêu chí cần đo

| Chỉ số | Cách quan sát |
|---|---|
| Thời gian khởi tạo UI | Đo từ lúc khởi chạy đến khi cửa sổ hiển thị và sẵn sàng tương tác. |
| Thời gian render frame | Đo thời gian tạo và hiển thị một frame trong workload thực tế. |
| Độ mượt khi thao tác | Quan sát animation, scrolling, resize, drag và chuyển cửa sổ. |
| CPU usage | Theo dõi CPU của tiến trình khi chạy cùng workload. |
| GPU/energy | Dùng công cụ hệ thống macOS phù hợp để quan sát mức sử dụng GPU và năng lượng. |
| Chất lượng hình ảnh | So sánh screenshot, text, alpha, clipping, transform và màu sắc. |
| Độ ổn định | Theo dõi crash, artifact, repaint bị thiếu và lỗi khi sleep/wake. |

Metal được thiết kế để dùng API đồ họa hiện đại hơn và có thể cải thiện hiệu năng/điện năng trên phần cứng phù hợp. Tuy nhiên, kết quả thực tế phụ thuộc workload, thiết bị và driver. Không giả định Metal luôn nhanh hơn cho mọi phép vẽ.

### 10.2. Benchmark có kiểm soát

Để kết quả có ý nghĩa:

1. Dùng cùng một JDK vendor/build và cùng ứng dụng.
2. Dùng cùng máy Mac, màn hình, độ phân giải và scale factor.
3. Dùng cùng dữ liệu, kích thước cửa sổ và chuỗi thao tác.
4. Chạy warm-up trước khi lấy số liệu.
5. Thực hiện nhiều lượt và so sánh median, p95 hoặc phân phối frame time.
6. Tách thời gian khởi động khỏi thời gian render ổn định.
7. Không in log hoặc ghi file trong vòng lặp render đang đo.
8. Đo cả CPU, GPU/energy và chất lượng hình ảnh, không chỉ FPS.

Không dùng `System.nanoTime()` quanh một lời gọi `drawString()` duy nhất rồi kết luận tốc độ GPU. Java 2D có thể buffer hoặc trì hoãn công việc tới thời điểm đồng bộ/hiển thị; benchmark phải phản ánh chu kỳ render hoàn chỉnh của ứng dụng.

### 10.3. Tránh benchmark sai do Event Dispatch Thread

Swing xử lý event và repaint trên Event Dispatch Thread (EDT). Nếu chạy vòng lặp tính toán dài hoặc `Thread.sleep()` trong `paintComponent()`, UI sẽ bị treo và kết quả benchmark không còn đại diện cho pipeline.

Hãy để `paintComponent()` chỉ vẽ nội dung hiện tại. Tính toán dữ liệu nặng ở worker thread, cập nhật model an toàn rồi yêu cầu repaint. Nếu benchmark animation, dùng một scheduler phù hợp để cập nhật trạng thái và đo thời gian frame, không chặn EDT.

## 11. Bộ thao tác nên có trong kiểm thử Java 2D

Một ứng dụng desktop thực tế thường không chỉ vẽ hình chữ nhật. Nên xây dựng bộ test bao phủ các nhóm sau:

| Nhóm | Thao tác mẫu | Điều cần quan sát |
|---|---|---|
| Hình học | `drawLine`, `fillRect`, `draw(Shape)`, `fill(Shape)` | Vị trí, kích thước, stroke và clipping. |
| Antialiasing | Đường chéo, ellipse, path cong | Rìa hình không bị răng cưa bất thường. |
| Alpha | `AlphaComposite.SrcOver`, ảnh RGBA | Màu pha trộn và vùng trong suốt. |
| Gradient | `GradientPaint`, `LinearGradientPaint` | Dải màu liên tục, không banding hoặc sai hướng. |
| Transform | Scale, rotate, translate, shear | Tọa độ và tâm biến đổi đúng. |
| Text | Font thường, bold, italic, glyph Unicode | Không mất glyph, không nhảy baseline bất thường. |
| Image | PNG/JPEG, ảnh lớn, ảnh trong suốt | Màu, scale, clipping và cập nhật nội dung. |
| Clip | `setClip`, `clip` | Không vẽ tràn khỏi vùng cho phép. |
| Buffering | `VolatileImage`, `BufferStrategy` | Không mất nội dung hoặc nhấp nháy. |
| Vòng đời cửa sổ | Resize, minimize, restore, move giữa màn hình | Surface được tạo lại và repaint đầy đủ. |

### 11.1. HiDPI và Retina

Trên màn hình Retina, kích thước logic của component và số pixel vật lý có thể khác nhau. Kiểm thử ở nhiều scale factor nếu sản phẩm hỗ trợ nhiều màn hình:

- Text vẫn đọc được ở kích thước UI dự kiến.
- Đường mảnh không biến mất khi scale.
- Icon và ảnh không bị mờ ngoài dự kiến.
- Popup, tooltip và cửa sổ phụ xuất hiện đúng vị trí.
- Kéo cửa sổ giữa hai màn hình có scale factor khác nhau không làm surface bị lỗi.

Không hardcode giả định rằng một logical pixel luôn tương ứng một pixel vật lý. Hãy dùng API hiển thị và layout phù hợp của Java AWT/Swing.

### 11.2. Font và text

Text rendering có thể khác nhẹ giữa pipeline, hệ điều hành và font. Hãy kiểm thử:

- Font hệ thống và font được đóng gói cùng ứng dụng.
- Chữ có dấu tiếng Việt và các glyph Unicode cần thiết.
- Kích thước nhỏ, lớn, bold và italic.
- Text trên nền sáng, nền tối và nền có transparency.
- Text được scale hoặc transform nếu ứng dụng có sử dụng.

Nếu screenshot thay đổi nhẹ ở rìa glyph, hãy đánh giá bằng tolerance phù hợp. Nếu glyph bị thiếu, ký tự sai hoặc baseline lệch rõ rệt, đó là lỗi cần điều tra.

## 12. Xử lý lỗi khi bật Metal

### 12.1. Property đã bật nhưng không thấy khác biệt

Nguyên nhân có thể:

- JVM thực tế không phải JDK 17 dự kiến.
- Property được truyền nhầm thành program argument.
- Property được đặt sau khi AWT đã khởi tạo.
- macOS thấp hơn 10.14.
- Bản JDK hoặc thiết bị không hỗ trợ pipeline trong cấu hình hiện tại.
- Workload chủ yếu render vào `BufferedImage`, không đi qua bề mặt hiển thị được tăng tốc.

Cách xử lý:

1. In `java.version`, `os.name` và property lúc khởi chạy.
2. Xác nhận VM options của IDE/launcher.
3. Chạy smoke test có cửa sổ hiển thị.
4. Dùng `VolatileImage` hoặc `BufferStrategy` nếu ứng dụng có đường render offscreen tương ứng.
5. Thu thập log runtime và thử lại trên JDK build/macOS được hỗ trợ.

### 12.2. Artifact hoặc crash

Nếu gặp vùng vẽ sai, flicker, crash hoặc lỗi khi chuyển màn hình:

1. Tạo ví dụ nhỏ chỉ dùng Swing/Java 2D để tái hiện.
2. Ghi lại JDK vendor, phiên bản đầy đủ, kiến trúc CPU và phiên bản macOS.
3. Ghi lại JVM options, đặc biệt là `sun.java2d.metal`.
4. Xác định thao tác gây lỗi: alpha, transform, text, resize, sleep/wake hay multi-monitor.
5. So sánh cùng thao tác khi không yêu cầu Metal để khoanh vùng.
6. Thu thập log, screenshot và bước tái hiện trước khi báo lỗi.

Không nên tắt Metal trên toàn bộ sản phẩm chỉ dựa vào một artifact chưa tái hiện được. Hãy tìm thao tác và môi trường cụ thể gây lỗi.

### 12.3. Hiệu năng thấp hơn kỳ vọng

Metal không bảo đảm mọi phép vẽ đều được tăng tốc. Nếu hiệu năng thấp:

- Kiểm tra destination surface có khả năng tăng tốc hay không.
- Tránh đọc pixel liên tục từ bề mặt tăng tốc nếu không cần.
- Hạn chế tạo object, font hoặc image mới trong mỗi lần repaint.
- Cache ảnh và tài nguyên bất biến phù hợp.
- Đo các primitive thường dùng trong ứng dụng.
- Dùng primitive tracing để nhận biết một số đường software fallback.
- So sánh bằng workload đại diện, không chỉ bằng demo tổng hợp.

Một số thao tác có thể chuyển qua software fallback và vẫn cho kết quả đúng. Mục tiêu là xác định phần nào thực sự gây bottleneck trước khi đổi cách vẽ.

## 13. Giới hạn và điều không nên suy luận

- Metal pipeline là implementation nội bộ của Java 2D; ứng dụng không gọi Metal API trực tiếp qua `Graphics2D`.
- Bật property chỉ là yêu cầu chọn pipeline; không nên xem property value là bằng chứng pipeline đã khởi tạo thành công.
- Một số primitive vẫn có thể dùng software fallback ngay cả khi pipeline Metal hoạt động.
- `BufferedImage` phù hợp cho kiểm thử pixel nhưng không đủ để xác nhận hardware acceleration.
- `VolatileImage.isAccelerated()` xác nhận khả năng tăng tốc của surface, không xác nhận riêng backend Metal.
- Ảnh screenshot có thể khác nhẹ do font, HiDPI, color profile và rasterization.
- JDK 17 mặc định khác JDK 19 trở lên; cần ghi rõ runtime khi so sánh.
- JavaFX có pipeline riêng; property Java 2D không điều khiển Prism.
- Pipeline đồ họa không thay đổi kết quả logic của API Java, nhưng có thể làm lộ khác biệt về rasterization hoặc lỗi native/driver.

## 14. Checklist thực hành kiểm thử trên macOS

### Trước khi chạy

- [ ] Xác nhận JDK 17 và phiên bản đầy đủ.
- [ ] Xác nhận macOS 10.14 trở lên.
- [ ] Xác nhận ứng dụng chạy trong desktop session, không headless.
- [ ] Đặt `-Dsun.java2d.metal=true` trong VM options.
- [ ] Ghi lại kiến trúc máy và thông tin màn hình.

### Khi chạy

- [ ] Cửa sổ mở và repaint bình thường.
- [ ] Hình học, text, ảnh, alpha và transform hiển thị đúng.
- [ ] Resize, minimize/restore và chuyển cửa sổ không gây artifact.
- [ ] Kiểm tra màn hình Retina/đa màn hình nếu sản phẩm hỗ trợ.
- [ ] Kiểm tra `VolatileImage`/`BufferStrategy` nếu ứng dụng sử dụng chúng.
- [ ] Thu thập log và screenshot khi có lỗi.

### Khi so sánh

- [ ] Dùng cùng JDK, máy, dữ liệu và thao tác.
- [ ] Chạy warm-up và nhiều lượt đo.
- [ ] So sánh median/p95 thay vì một mẫu đơn.
- [ ] Đo CPU, frame time, độ ổn định và chất lượng hình ảnh.
- [ ] Dùng tolerance hợp lý cho pixel/text.
- [ ] Không coi primitive tracing hoặc property value là xác nhận duy nhất về Metal.

## 15. Bài tập thực hành

### Bài tập 1 — Bật Metal trên JDK 17

Chạy `Java2DMetalSmokeTest` với `-Dsun.java2d.metal=true`. In `java.version`, `os.name` và giá trị property. Chụp lại cửa sổ sau khi đã resize và chuyển qua lại giữa các cửa sổ.

### Bài tập 2 — So sánh với pipeline mặc định

Chạy cùng chương trình với `-Dsun.java2d.metal=true` và `-Dsun.java2d.metal=false`. So sánh hình ảnh, text, repaint và độ mượt. Ghi rõ rằng JDK 17 thông thường dùng OpenGL làm baseline khi Metal bị tắt.

### Bài tập 3 — Kiểm tra BufferedImage và VolatileImage

Vẽ cùng một hình lên `BufferedImage` và `VolatileImage`. Kiểm tra pixel snapshot, `isAccelerated()` và `contentsLost()`. Giải thích vì sao hai bề mặt này không chứng minh cùng một đường render.

### Bài tập 4 — Kiểm tra alpha và transform

Tạo các hình chồng lấp với nhiều alpha value, rotate, scale và clip. So sánh screenshot trên Metal và baseline. Xác định khác biệt nào là sai lệch đáng kể và khác biệt nào nằm trong tolerance rasterization.

### Bài tập 5 — Kiểm tra HiDPI

Chạy ứng dụng trên màn hình Retina và, nếu có, màn hình ngoài với scale factor khác. Di chuyển cửa sổ qua lại và kiểm tra text, icon, popup, hình học và repaint.

### Bài tập 6 — Primitive tracing

Chạy với `-Dsun.java2d.trace=count`. Ghi lại primitive được sử dụng và xác định những primitive có dấu hiệu software loops. Giải thích vì sao đây là dữ liệu về primitive chứ không phải xác nhận trực tiếp pipeline Metal.

### Bài tập 7 — Benchmark workload thật

Chọn một màn hình hoặc luồng vẽ có trong ứng dụng. Đo thời gian frame và CPU sau warm-up, lặp lại nhiều lượt trên cùng máy. So sánh kết quả Metal và baseline, rồi nêu các giới hạn của phép đo.

## 16. Các nguyên tắc cần ghi nhớ

- JEP 382 đưa Metal pipeline vào Java 2D trên macOS từ JDK 17.
- Trên JDK 17, Metal mặc định tắt; bật bằng `-Dsun.java2d.metal=true`.
- Metal yêu cầu macOS 10.14.x trở lên; cần kiểm tra JDK build và thiết bị thực tế.
- Metal trở thành pipeline mặc định trên macOS từ JDK 19; không áp dụng mặc định đó ngược lại cho JDK 17.
- Java 2D API của Swing/AWT không thay đổi khi đổi pipeline.
- `BufferedImage` phù hợp cho test pixel nhưng thường dùng software rendering; test Metal cần render lên cửa sổ thật và có thể thêm `VolatileImage`/`BufferStrategy`.
- `VolatileImage.isAccelerated()` cho biết surface có được tăng tốc, không khẳng định backend là Metal.
- `-Dsun.java2d.trace=count` giúp nhận biết một số software primitives; nó không phải công cụ xác nhận duy nhất pipeline đã chọn.
- Kiểm thử cả hình ảnh, repaint, resize, HiDPI, nhiều màn hình, ổn định và hiệu năng.
- So sánh pipeline trên cùng runtime, máy, dữ liệu và workload; đo nhiều lượt và dùng tolerance phù hợp.
- JavaFX có pipeline riêng, không được điều khiển bởi property Java 2D.
- `sun.java2d.metal` là property triển khai nội bộ; cấu hình lúc khởi động và xác minh trên đúng JDK/macOS sẽ triển khai.

### Tài liệu tham khảo

- [JDK 17 Release Notes — JEP 382: New macOS Rendering Pipeline](https://www.oracle.com/java/technologies/javase/17-relnote-issues.html).
- [JEP 382 — New macOS Rendering Pipeline](https://openjdk.org/jeps/382).
- [Oracle Java 17 Troubleshooting Guide — Java 2D](https://docs.oracle.com/en/java/javase/17/troubleshoot/java-2d.html).
- [Oracle Java 17 Troubleshooting Guide — Java 2D Properties](https://docs.oracle.com/en/java/javase/17/troubleshoot/java-2d-properties.html).
- [Oracle Java 17 Troubleshooting Guide — Java 2D Pipeline Rendering](https://docs.oracle.com/en/java/javase/17/troubleshoot/java-2d-pipeline-rendering-selection-and-properties.html).
- [JDK 19 Release Notes — Metal Is Now the Default Java 2D Rendering Pipeline on macOS](https://www.oracle.com/java/technologies/javase/19-relnote-issues.html).
