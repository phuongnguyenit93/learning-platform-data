# Window: hình dạng tùy chỉnh và độ trong suốt trong Java Swing

## 1. Mục tiêu và bối cảnh

Một cửa sổ Swing thông thường là hình chữ nhật với thanh tiêu đề và viền do hệ điều hành quản lý. Khi thiết kế popup, bảng điều khiển nổi, bảng thông báo hoặc giao diện công cụ đặc thù, đôi khi cần:

- Cắt khung cửa sổ thành **hình tròn, elip, bo góc hoặc hình dạng bất kỳ**.
- Làm **toàn bộ cửa sổ bán trong suốt** để nhìn thấy cửa sổ khác phía sau.
- Để **nền hoặc một số vùng trong suốt**, trong khi các thành phần giao diện vẫn rõ và có độ đục riêng.

Kể từ Java 7, AWT cung cấp các API **công khai và vẫn được hỗ trợ** như `Window.setShape(Shape)`, `Window.setOpacity(float)` và `Window.setBackground(Color)`, hoạt động cùng các lớp Swing `JFrame`, `JDialog`, `JWindow`. Bài này sử dụng những API hiện hành và ví dụ **Java 17+**; nó không dựa vào API nội bộ hoặc cơ chế riêng của JDK cũ.

**Điều kiện vận hành:** hiệu ứng phụ thuộc thiết bị hiển thị, hệ điều hành, compositor/window manager, môi trường remote desktop và cấu hình đồ họa. Không được mặc định mọi máy đều hỗ trợ. Ứng dụng cần kiểm tra khả năng rồi có phương án cửa sổ chữ nhật/không trong suốt để dự phòng.

## 2. Ba hiệu ứng khác nhau, ba API riêng

| Nhu cầu | API chính | Khả năng cần kiểm tra | Kết quả |
| --- | --- | --- | --- |
| Độ trong suốt **đồng đều** của toàn cửa sổ | `window.setOpacity(0.85f)` | `WindowTranslucency.TRANSLUCENT` | Toàn bộ cửa sổ, cả chữ, nút và nội dung bên trong, có mức alpha giống nhau. |
| Thay đổi **biên hình học** cửa sổ | `window.setShape(shape)` | `WindowTranslucency.PERPIXEL_TRANSPARENT` | Chỉ vùng bên trong `Shape` hiển thị và có thể tương tác; vùng ngoài hình dạng bị loại bỏ. |
| Độ trong suốt **theo từng pixel** | `window.setBackground(new Color(0, 0, 0, 0))` kết hợp vẽ màu có alpha | `WindowTranslucency.PERPIXEL_TRANSLUCENT`; với cấu hình đồ họa cụ thể, kiểm tra thêm `GraphicsConfiguration.isTranslucencyCapable()` | Có thể vẽ nền bán trong suốt hoặc các vùng alpha khác nhau; thành phần khác vẫn có thể đục hoàn toàn. |

Tên các enum dễ gây nhầm:

- `PERPIXEL_TRANSPARENT` là **khả năng cắt hình dạng** cửa sổ bằng `setShape`.
- `PERPIXEL_TRANSLUCENT` là **khả năng hỗ trợ kênh alpha từng pixel** của cửa sổ, ví dụ nền bo góc bán trong suốt qua `setBackground`.
- `TRANSLUCENT` là **độ đục đồng đều** của cả cửa sổ qua `setOpacity`.

**Độ đục (`opacity`) không phải phần trăm trong suốt.** `1.0f` là đục 100%; `0.7f` nghĩa là độ đục 70%, độ trong suốt 30%; `0.0f` có thể làm cửa sổ vô hình nhưng việc nhận chuột lúc này còn tùy nền tảng, nên không nên dùng làm cơ chế bảo mật hay chặn click.

`Color(r, g, b, alpha)` dùng alpha nguyên từ `0` đến `255`: `0` trong suốt hoàn toàn, `255` đục hoàn toàn. Đừng nhầm alpha này với `setOpacity(float)` có miền giá trị `0.0f..1.0f`.

## 3. Các điều kiện tiên quyết

### 3.1. Kiểm tra năng lực của thiết bị hiển thị

```java
import java.awt.GraphicsDevice;
import java.awt.GraphicsEnvironment;
import static java.awt.GraphicsDevice.WindowTranslucency.*;

GraphicsDevice device = GraphicsEnvironment
        .getLocalGraphicsEnvironment()
        .getDefaultScreenDevice();

boolean canShape = device.isWindowTranslucencySupported(PERPIXEL_TRANSPARENT);
boolean canFade = device.isWindowTranslucencySupported(TRANSLUCENT);
boolean canUsePerPixelAlpha =
        device.isWindowTranslucencySupported(PERPIXEL_TRANSLUCENT);
```

Đây là **đoạn minh họa** về cách kiểm tra sau khi đã xác nhận có môi trường đồ họa; nó không phải tệp Java độc lập. Khi cửa sổ cụ thể được tạo, nên lấy `GraphicsDevice` từ `frame.getGraphicsConfiguration().getDevice()` để kiểm tra đúng thiết bị đang dùng. Với alpha theo pixel, kiểm tra cả `frame.getGraphicsConfiguration().isTranslucencyCapable()`. Khi chuyển cửa sổ sang màn hình khác, không nên mặc định khả năng thiết bị sẽ luôn giống màn hình ban đầu.

Nếu chạy ở môi trường **headless** (ví dụ nhiều máy chủ CI, container không có hệ thống cửa sổ), `GraphicsEnvironment.isHeadless()` có thể là `true`. Không tạo `JFrame` trong trường hợp này vì sẽ gặp `HeadlessException`.

### 3.2. Cửa sổ phải undecorated, không ở full-screen mode

Các lời gọi `setShape(nonNullShape)`, `setOpacity(value < 1.0f)` và `setBackground(colorWithAlphaLessThan255)` yêu cầu cửa sổ phù hợp điều kiện nền tảng, trong đó `JFrame`/`JDialog` phải **không có viền hệ thống** (`undecorated`) và cửa sổ không ở chế độ full-screen. Đặt `setUndecorated(true)` **trước khi cửa sổ trở nên displayable**, thông thường trước `setVisible(true)` hoặc `pack()`.

```java
JFrame frame = new JFrame("Demo");
frame.setUndecorated(true); // Trước setVisible()/pack().
frame.setSize(420, 240);
// Sau khi kiểm tra năng lực: frame.setOpacity(0.85f), setShape(...), ...
frame.setVisible(true);
```

Đoạn trên là **mã minh họa** trong một phương thức có import `javax.swing.JFrame`. Bỏ viền hệ điều hành cũng làm mất thanh tiêu đề và nút đóng mặc định. Ứng dụng cần cung cấp nút đóng, vùng kéo cửa sổ và các thao tác bàn phím phù hợp.

Nếu dùng cửa sổ có decorations hoặc môi trường không hỗ trợ, Java có thể ném `IllegalComponentStateException` hoặc `UnsupportedOperationException`. Với `setOpacity` ngoài `[0, 1]`, Java ném `IllegalArgumentException`. Kiểm tra và degrade có chủ đích thay vì đặt hiệu ứng một cách vô điều kiện.

### 3.3. Threading Swing

Tạo/cập nhật giao diện, gọi `setShape`, `setOpacity` và xử lý tương tác trên **Event Dispatch Thread (EDT)**. `SwingUtilities.invokeLater(...)` là cách dễ dùng để khởi tạo UI từ `main`. Không xử lý tác vụ I/O hay tính toán lâu trên EDT vì giao diện sẽ bị đứng; nếu cần thì dùng `SwingWorker` hoặc cơ chế chạy nền phù hợp, rồi cập nhật UI trên EDT.

## 4. Ví dụ chạy được: cửa sổ bo góc và thanh điều chỉnh opacity

Tạo tệp **ShapedOpacityWindowDemo.java** bằng UTF-8. Chương trình hiển thị một `JFrame` không viền, thử bo góc qua `RoundRectangle2D`, có thanh kéo điều chỉnh độ đục của **toàn cửa sổ**, nút đóng và kéo di chuyển bằng nhãn tiêu đề. Nếu thiết bị không hỗ trợ một hiệu ứng, chương trình giữ dạng chữ nhật hoặc độ đục 100% cho hiệu ứng đó.

```java
import java.awt.BorderLayout;
import java.awt.Color;
import java.awt.GraphicsDevice;
import java.awt.GraphicsEnvironment;
import java.awt.Point;
import java.awt.event.ComponentAdapter;
import java.awt.event.ComponentEvent;
import java.awt.event.MouseAdapter;
import java.awt.event.MouseEvent;
import java.awt.event.WindowEvent;
import java.awt.geom.RoundRectangle2D;
import javax.swing.BorderFactory;
import javax.swing.JButton;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JPanel;
import javax.swing.JSlider;
import javax.swing.SwingUtilities;
import javax.swing.WindowConstants;

import static java.awt.GraphicsDevice.WindowTranslucency.PERPIXEL_TRANSPARENT;
import static java.awt.GraphicsDevice.WindowTranslucency.TRANSLUCENT;

public class ShapedOpacityWindowDemo {
    public static void main(String[] args) {
        if (GraphicsEnvironment.isHeadless()) {
            System.err.println("Không có môi trường đồ họa để hiển thị Swing.");
            return;
        }
        SwingUtilities.invokeLater(ShapedOpacityWindowDemo::showWindow);
    }

    private static void showWindow() {
        JFrame frame = new JFrame("Swing window effects");
        frame.setDefaultCloseOperation(WindowConstants.EXIT_ON_CLOSE);
        frame.setUndecorated(true); // Phải đặt trước khi cửa sổ displayable.
        frame.setSize(460, 240);
        frame.setLocationRelativeTo(null);

        GraphicsDevice device = frame.getGraphicsConfiguration().getDevice();
        boolean canShape =
                device.isWindowTranslucencySupported(PERPIXEL_TRANSPARENT);
        boolean canFade =
                device.isWindowTranslucencySupported(TRANSLUCENT);

        JPanel root = new JPanel(new BorderLayout(12, 12));
        root.setBackground(new Color(236, 244, 252));
        root.setBorder(BorderFactory.createEmptyBorder(20, 24, 20, 24));

        JPanel header = new JPanel(new BorderLayout(12, 0));
        header.setOpaque(false);
        JLabel title = new JLabel("Swing: bo góc và độ đục");
        JButton close = new JButton("Đóng");
        close.addActionListener(e -> frame.dispatchEvent(
                new WindowEvent(frame, WindowEvent.WINDOW_CLOSING)));
        header.add(title, BorderLayout.CENTER);
        header.add(close, BorderLayout.EAST);
        root.add(header, BorderLayout.NORTH);

        JLabel status = new JLabel("Shape: " + (canShape ? "có" : "không")
                + " | Opacity: " + (canFade ? "có" : "không"));
        root.add(status, BorderLayout.CENTER);

        JPanel controls = new JPanel(new BorderLayout(12, 0));
        controls.setOpaque(false);
        controls.add(new JLabel("Độ đục"), BorderLayout.WEST);
        JSlider slider = new JSlider(25, 100, 85);
        JLabel percent = new JLabel(canFade ? "85%" : "100%");
        controls.add(slider, BorderLayout.CENTER);
        controls.add(percent, BorderLayout.EAST);
        root.add(controls, BorderLayout.SOUTH);
        frame.setContentPane(root);

        if (canFade) {
            frame.setOpacity(0.85f);
            slider.addChangeListener(e -> {
                int value = slider.getValue();
                frame.setOpacity(value / 100.0f);
                percent.setText(value + "%");
            });
        } else {
            slider.setEnabled(false);
        }

        if (canShape) {
            Runnable updateShape = () -> {
                if (frame.getWidth() > 0 && frame.getHeight() > 0) {
                    frame.setShape(new RoundRectangle2D.Double(
                            0, 0, frame.getWidth(), frame.getHeight(), 64, 64));
                }
            };
            frame.addComponentListener(new ComponentAdapter() {
                @Override
                public void componentResized(ComponentEvent event) {
                    updateShape.run();
                }
            });
            updateShape.run();
        }

        MouseAdapter drag = new MouseAdapter() {
            private Point offset;

            @Override
            public void mousePressed(MouseEvent event) {
                Point cursor = event.getLocationOnScreen();
                Point window = frame.getLocation();
                offset = new Point(cursor.x - window.x, cursor.y - window.y);
            }

            @Override
            public void mouseDragged(MouseEvent event) {
                if (offset == null) {
                    return;
                }
                Point cursor = event.getLocationOnScreen();
                frame.setLocation(cursor.x - offset.x, cursor.y - offset.y);
            }
        };
        title.addMouseListener(drag);
        title.addMouseMotionListener(drag);

        frame.setVisible(true);
    }
}
```

Biên dịch/chạy trên máy có desktop và JDK 17+:

```bash
javac -encoding UTF-8 ShapedOpacityWindowDemo.java
java ShapedOpacityWindowDemo
```

**Kết quả:** một cửa sổ Swing xuất hiện. Nếu `PERPIXEL_TRANSPARENT` được hỗ trợ, bốn góc cửa sổ bị cắt theo hình bo tròn. Nếu `TRANSLUCENT` được hỗ trợ, thanh kéo đặt độ đục trong khoảng 25–100%; cả chữ và nút đều mờ cùng cửa sổ. Nếu không hỗ trợ, UI vẫn xuất hiện dưới dạng chữ nhật và/hoặc thanh kéo bị vô hiệu hóa. Chương trình đồ họa không có stdout cố định khi chạy thành công. Trong môi trường headless, nó chỉ in thông báo kiểm tra môi trường ra **stderr**.

Giải thích cơ chế:

1. `setUndecorated(true)` được gọi trước khi cửa sổ hiển thị, đáp ứng điều kiện để đổi hình dạng và giảm opacity.
2. Mỗi `setShape(new RoundRectangle2D.Double(...))` tạo vùng hiển thị/click tương ứng với kích thước cửa sổ hiện tại. `ComponentListener.componentResized` tính lại shape khi cửa sổ đổi kích thước. Với kích thước cố định, vẫn nên tính shape theo `getWidth()/getHeight()` để tránh dùng tọa độ cũ.
3. `setOpacity(0.85f)` áp dụng **đồng đều** cho cả cửa sổ. `JSlider` cập nhật giá trị trên EDT; nút, chữ và panel đều chịu opacity này.
4. `JPanel` và các thành phần bên trong có thể dùng nền **đục bình thường**, vì cắt theo `setShape` diễn ra ở cấp cửa sổ.
5. Khi bỏ decorations, nút `Đóng` gửi `WINDOW_CLOSING` cho `JFrame` để kích hoạt `EXIT_ON_CLOSE`, còn nhãn tiêu đề xử lý kéo cửa sổ. Lấy độ lệch từ tọa độ trên màn hình giúp kéo đúng ngay cả khi vị trí cửa sổ thay đổi.

**Thay đổi hình dạng:** dùng `Ellipse2D.Double(0, 0, width, height)` để tạo cửa sổ elip; dùng các lớp khác thực hiện `java.awt.Shape` khi cần. Với `frame.setShape(null)`, cửa sổ trở về hình mặc định, thường là chữ nhật. Biên ngoài `Shape` bị loại bỏ khỏi vùng tương tác chuột; điều này khác với chỉ vẽ vùng alpha 0.

## 5. Ví dụ chạy được: nền trong suốt theo từng pixel

`setOpacity(0.7f)` làm **mọi thứ** mờ, kể cả chữ và nút. Nếu muốn panel nền mờ nhưng nội dung vẫn rõ, dùng chế độ **per-pixel translucency**: `Window.setBackground(new Color(0, 0, 0, 0))` và vẽ lên một thành phần không opaque bằng `Graphics2D` với màu có alpha.

Tạo tệp **PerPixelWindowDemo.java**. Ví dụ chỉ bật chế độ per-pixel sau khi kiểm tra hỗ trợ; nếu không có, nó hiển thị một `JFrame` chữ nhật thông thường với thông báo lý do. Trong chế độ có hỗ trợ, cửa sổ có các góc trong suốt, một tấm nền xanh bán trong suốt và nút đóng vẫn rõ.

```java
import java.awt.BorderLayout;
import java.awt.Color;
import java.awt.Graphics;
import java.awt.Graphics2D;
import java.awt.GraphicsDevice;
import java.awt.GraphicsEnvironment;
import java.awt.RenderingHints;
import java.awt.event.WindowEvent;
import javax.swing.BorderFactory;
import javax.swing.JButton;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JPanel;
import javax.swing.SwingUtilities;
import javax.swing.WindowConstants;

import static java.awt.GraphicsDevice.WindowTranslucency.PERPIXEL_TRANSLUCENT;

public class PerPixelWindowDemo {
    public static void main(String[] args) {
        if (GraphicsEnvironment.isHeadless()) {
            System.err.println("Không có môi trường đồ họa để hiển thị Swing.");
            return;
        }
        SwingUtilities.invokeLater(PerPixelWindowDemo::showWindow);
    }

    private static void showWindow() {
        JFrame frame = new JFrame("Per-pixel translucency");
        frame.setDefaultCloseOperation(WindowConstants.EXIT_ON_CLOSE);

        GraphicsDevice device = frame.getGraphicsConfiguration().getDevice();
        boolean canUseAlpha =
                device.isWindowTranslucencySupported(PERPIXEL_TRANSLUCENT)
                && frame.getGraphicsConfiguration().isTranslucencyCapable();

        if (!canUseAlpha) {
            JLabel fallback = new JLabel(
                    "Thiết bị/cấu hình hiện tại không hỗ trợ alpha từng pixel.");
            fallback.setBorder(BorderFactory.createEmptyBorder(20, 20, 20, 20));
            frame.setContentPane(fallback);
            frame.setSize(520, 180);
            frame.setLocationRelativeTo(null);
            frame.setVisible(true);
            return;
        }

        frame.setUndecorated(true);
        frame.setBackground(new Color(0, 0, 0, 0));
        frame.getRootPane().setOpaque(false);
        frame.getLayeredPane().setOpaque(false);

        JPanel canvas = new JPanel(new BorderLayout(10, 10)) {
            @Override
            protected void paintComponent(Graphics graphics) {
                super.paintComponent(graphics);
                Graphics2D g2 = (Graphics2D) graphics.create();
                try {
                    g2.setRenderingHint(RenderingHints.KEY_ANTIALIASING,
                            RenderingHints.VALUE_ANTIALIAS_ON);
                    g2.setColor(new Color(30, 51, 86, 190));
                    g2.fillRoundRect(12, 12,
                            getWidth() - 24, getHeight() - 24, 48, 48);
                } finally {
                    g2.dispose();
                }
            }
        };
        canvas.setOpaque(false);
        canvas.setBorder(BorderFactory.createEmptyBorder(32, 34, 32, 34));

        JLabel message = new JLabel(
                "<html><b>Nền bán trong suốt</b><p>Chữ và nút vẫn rõ.</p></html>");
        message.setForeground(Color.WHITE);
        canvas.add(message, BorderLayout.CENTER);

        JButton close = new JButton("Đóng");
        close.addActionListener(e -> frame.dispatchEvent(
                new WindowEvent(frame, WindowEvent.WINDOW_CLOSING)));
        canvas.add(close, BorderLayout.SOUTH);

        frame.setContentPane(canvas);
        frame.setSize(440, 220);
        frame.setLocationRelativeTo(null);
        frame.setVisible(true);
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 PerPixelWindowDemo.java
java PerPixelWindowDemo
```

Kết quả trực quan tùy môi trường đồ họa: nếu được hỗ trợ, vùng ngoài hình bo góc trong suốt; phần nền xanh có alpha `190/255`, trong khi chữ trắng và nút đóng vẫn được vẽ theo style riêng. Nếu không được hỗ trợ, một cửa sổ thông thường hiển thị thông báo fallback. Không có stdout cố định khi ứng dụng hiển thị.

Các điểm cần hiểu:

- Lời gọi `frame.setBackground(new Color(0, 0, 0, 0))` yêu cầu chế độ alpha từng pixel ở cấp **window**. Việc gọi riêng `panel.setOpaque(false)` trên một `JFrame` thông thường **không đủ** để nhìn xuyên qua cửa sổ xuống ứng dụng khác; nó chủ yếu cho phép nội dung phía sau trong cùng cây thành phần Swing hiển thị.
- `canvas.setOpaque(false)` và root/layered pane không opaque giúp tránh các lớp Swing vẽ nền hình chữ nhật che mất vùng alpha đã chủ động tạo. `paintComponent` tạo bản sao `Graphics2D`, bật khử răng cưa và tô `RoundRect` bằng màu có alpha; `dispose()` chỉ giải phóng bản sao graphics, **không** đóng cửa sổ.
- `setBackground` và `getGraphicsConfiguration().isTranslucencyCapable()` liên quan đến chế độ từng pixel; hỗ trợ có thể thay đổi theo desktop/window manager và có thể làm hệ thống điều chỉnh cấu hình đồ họa.
- Vùng alpha `0` được hiển thị trong suốt, **nhưng không bảo đảm click chuột xuyên qua** trên mọi nền tảng. Nếu bắt buộc một vùng không nhận sự kiện chuột, hãy dùng `setShape` để loại vùng đó khỏi shape (sau khi kiểm tra khả năng `PERPIXEL_TRANSPARENT`).
- Ví dụ bỏ thanh tiêu đề hệ điều hành và cung cấp nút đóng; nếu triển khai thật, cần thêm hành vi di chuyển, hỗ trợ bàn phím, menu ngữ cảnh và khả năng tiếp cận phù hợp với đối tượng sử dụng.

## 6. Kết hợp hiệu ứng và thay đổi trạng thái

Các hiệu ứng có thể kết hợp khi thiết bị hỗ trợ tất cả những khả năng cần thiết:

- `setShape` giới hạn phần hình học **có thể thấy và click**.
- `setBackground` alpha < 255 cho phép **độ trong suốt theo pixel** của nền do ứng dụng vẽ.
- `setOpacity` < 1.0f nhân thêm **độ đục đồng đều** của toàn cửa sổ, khiến cả nội dung đã có alpha cũng mờ hơn.

Chẳng hạn, cửa sổ dạng elip với nền trong suốt và opacity 0.9 chỉ nên thiết lập sau khi xác nhận đủ `PERPIXEL_TRANSPARENT`, `PERPIXEL_TRANSLUCENT` và `TRANSLUCENT` tương ứng. Hầu hết giao diện chỉ cần một hoặc hai hiệu ứng; phối hợp nhiều alpha làm chữ và nút khó đọc.

Có thể đưa cửa sổ về trạng thái ban đầu khi chức năng hỗ trợ bằng:

```java
frame.setShape(null);                 // Shape mặc định.
frame.setOpacity(1.0f);               // Không giảm opacity toàn cửa sổ.
frame.setBackground(new Color(0, 0, 0, 255)); // Nền window đục.
```

Đây là **đoạn minh họa** cho một `JFrame` hiện có, không phải chương trình độc lập. Khi chọn lại màu nền, nhớ cập nhật cách vẽ và `setOpaque` của các panel nếu không muốn nền cửa sổ bị đen hoặc không đồng nhất. Với mã production, hãy chọn cấu hình rõ ràng ngay từ lúc tạo cửa sổ, và thay đổi qua sự kiện trên EDT.

## 7. Lưu ý thực tế: UI, hiệu năng và accessibility

1. **Không dựa vào UI trong suốt làm kiểm soát an ninh.** Một điểm ảnh vô hình không đồng nghĩa vùng đó không bắt chuột; shape mới xác định vùng bị loại bỏ khỏi hit testing theo hợp đồng API.
2. **Thiết kế fallback:** nếu thiết bị không hỗ trợ, giữ `JFrame` chữ nhật đục và cho phép người dùng làm việc bình thường. Đừng để ứng dụng crash chỉ vì hiệu ứng trang trí.
3. **Không gây mất khả năng sử dụng:** với cửa sổ không viền, phải có nút đóng, vùng kéo, điều hướng bàn phím, focus rõ ràng, đủ tương phản và cách đóng không phụ thuộc chuột. Tránh dùng opacity thấp cho chữ, biểu mẫu nhập liệu hoặc hộp thoại quan trọng.
4. **Hiệu năng và repaint:** thay đổi alpha hoặc shape liên tục có thể tốn tài nguyên tùy compositor. Với animation hoặc resize, giới hạn số lần cập nhật khi cần và thử trên các màn hình/desktop thực tế; không làm tác vụ nặng trong `paintComponent`.
5. **Swing painting:** tùy mode, kiểm soát `setOpaque` và cách vẽ nền. Nếu component khai báo opaque, nó phải tự vẽ đầy đủ vùng nền; khi vẽ màu alpha, dùng `Graphics2D.create()` và `dispose()` trên bản sao, gọi `repaint()` khi trạng thái render thay đổi.
6. **Kiểm thử đa màn hình và headless:** khả năng hỗ trợ thuộc thiết bị/configuration. GUI test cần môi trường hiển thị thật hoặc virtual display phù hợp; kiểm thử logic riêng nên chạy được không phụ thuộc việc mở window.
7. **Không dùng API nội bộ đã lỗi thời:** những ví dụ cũ dùng `com.sun.awt.AWTUtilities`, reflection hoặc mã Java Web Start đời cũ không cần thiết cho Java hiện hành. Dùng trực tiếp API chuẩn trong `java.awt.Window` và `GraphicsDevice`.

## 8. Lỗi thường gặp và cách sửa

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| `IllegalComponentStateException` khi giảm opacity hoặc set shape | Cửa sổ đang có decorations hoặc ở full-screen mode. | Chọn `setUndecorated(true)` trước khi displayable; tránh full-screen cho các hiệu ứng này. |
| `UnsupportedOperationException` | Device không hỗ trợ `WindowTranslucency` tương ứng. | Kiểm tra khả năng và fallback trước khi gọi API. |
| `IllegalArgumentException` từ `setOpacity` | Giá trị nằm ngoài `[0.0f, 1.0f]`. | Kẹp giá trị và chuyển slider sang `value / 100.0f`. |
| `IllegalComponentStateException` từ `setUndecorated` | Cửa sổ đã displayable (ví dụ đã `pack()`/`setVisible(true)`). | Xác định decorations trước khi hiển thị; nếu phải đổi mode, quản lý vòng đời cửa sổ thích hợp. |
| Đổi `JPanel.setOpaque(false)` mà không thấy desktop phía sau | Chỉ đổi painting của panel, chưa bật per-pixel alpha cho top-level window. | Kiểm tra `PERPIXEL_TRANSLUCENT`, đặt alpha nền cấp `Window` và tự vẽ. |
| Kéo slider opacity thấy cả chữ mờ | `setOpacity` áp dụng cho **toàn cửa sổ**. | Dùng per-pixel translucency nếu chỉ muốn nền mờ. |
| Cửa sổ bị cắt sai sau resize | `Shape` cũ giữ kích thước trước khi resize. | Tính lại `Shape` dựa trên `getWidth()/getHeight()` trong `componentResized`. |
| Cửa sổ không thể di chuyển/đóng như bình thường | `setUndecorated(true)` bỏ thanh tiêu đề hệ điều hành. | Tạo nút đóng và cơ chế kéo, keyboard/focus phù hợp. |
| Vùng alpha 0 vẫn bắt chuột | Click-through của pixel alpha 0 tùy OS. | Dùng `setShape` nếu cần loại vùng đó khỏi hit testing. |
| Chạy trên CI báo `HeadlessException` | Không có desktop/graphics environment. | Kiểm tra `GraphicsEnvironment.isHeadless()`, chỉ mở GUI khi có display. |

## 9. Bài tập và câu hỏi tự kiểm tra

1. Đổi `RoundRectangle2D.Double(...)` thành `Ellipse2D.Double(...)` trong ví dụ thứ nhất. Quan sát vùng tương tác chuột: có thể click ở góc hình chữ nhật bao quanh elip không?
2. Kéo opacity từ 100% xuống 50% và quan sát **chữ/nút**. Vì sao chúng cũng mờ? Hiệu ứng này khác ví dụ per-pixel ở điểm nào?
3. Thêm một checkbox `Bo góc` trong cửa sổ thứ nhất, bật bằng `setShape(...)` và tắt bằng `setShape(null)`. Chỉ bật nếu `PERPIXEL_TRANSPARENT` được hỗ trợ.
4. Trong ví dụ thứ hai, thay alpha màu nền từ `190` sang `90` rồi `255`. Giải thích khác biệt giữa alpha của `Color` và giá trị `setOpacity` của toàn window.
5. Giả lập trạng thái không hỗ trợ khả năng đồ họa (ví dụ thay điều kiện kiểm tra thành `false` trong bản thử nghiệm). Xác minh ứng dụng có fallback và không ném ngoại lệ khi mở.
6. Thử resize cửa sổ có shape và viết một kiểm tra thủ công để bảo đảm shape luôn khớp kích thước thực tế. Nếu chuyển sang màn hình khác, giải thích vì sao phải kiểm tra khả năng nền tảng.

## 10. Tài liệu API hiện hành

- [Window — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.desktop/java/awt/Window.html): `setShape`, `setOpacity`, `setBackground`, các điều kiện hợp lệ và ngoại lệ.
- [GraphicsDevice — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.desktop/java/awt/GraphicsDevice.html): `WindowTranslucency` và `isWindowTranslucencySupported`.
- [GraphicsConfiguration — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.desktop/java/awt/GraphicsConfiguration.html): `isTranslucencyCapable()`.
- [JFrame — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.desktop/javax/swing/JFrame.html): cửa sổ top-level, decorations và vòng đời.
- [SwingUtilities — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.desktop/javax/swing/SwingUtilities.html): `invokeLater` để tạo/cập nhật Swing UI trên EDT.

**Ghi nhớ:** `setShape` thay đổi **vùng hình học**, `setOpacity` thay đổi **độ đục cả cửa sổ**, `setBackground` với alpha kích hoạt **độ trong suốt theo pixel**. Cả ba đều là API công khai của Java hiện hành, nhưng phải kiểm tra hỗ trợ của hệ thống và chuẩn bị fallback.