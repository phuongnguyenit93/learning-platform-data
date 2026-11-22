# Kiểm tra GraphicsDevice trước khi dùng hiệu ứng trong Java Swing

## 1. Vì sao cần kiểm tra trước khi bật hiệu ứng?

Ứng dụng Swing có thể chạy trên nhiều hệ điều hành, màn hình, trình quản lý cửa sổ, máy từ xa hoặc môi trường không có màn hình (*headless*). Các **hiệu ứng của toàn cửa sổ** như làm mờ cửa sổ (`Window.setOpacity`), bo hình dạng cửa sổ (`Window.setShape`) và nền trong suốt theo từng pixel (`Window.setBackground` với alpha thấp hơn 255) **không được đảm bảo** trên mọi thiết bị đồ họa.

`java.awt.GraphicsDevice` biểu diễn thiết bị đồ họa; `GraphicsConfiguration` mô tả một cấu hình của thiết bị; `GraphicsEnvironment` giúp truy cập các thiết bị đang có. Trước khi gọi API phụ thuộc khả năng màn hình, ứng dụng nên:

1. Kiểm tra có môi trường đồ họa hay không bằng `GraphicsEnvironment.isHeadless()`.
2. Lấy `GraphicsDevice` của **cửa sổ sẽ sử dụng hiệu ứng** (qua `window.getGraphicsConfiguration().getDevice()`), đặc biệt khi có nhiều màn hình.
3. Kiểm tra **đúng loại tính năng** bằng `device.isWindowTranslucencySupported(...)`; với alpha theo pixel, chú ý thêm `GraphicsConfiguration.isTranslucencyCapable()`.
4. Đảm bảo các điều kiện của `Window`: thường phải **undecorated**, **không ở full-screen mode**; xử lý thất bại có kiểm soát và dùng hiệu ứng thay thế trong nội dung Swing.

Các API này vẫn hiện diện trong Java SE hiện đại. Chúng có từ Java 7 hoặc trước đó, nhưng không cần dựa vào các API nội bộ cũ như `com.sun.awt.AWTUtilities`.

## 2. Phân biệt ba cấp độ đồ họa

| Đối tượng | Trả lời câu hỏi nào? | Dùng khi nào? |
| --- | --- | --- |
| `GraphicsEnvironment` | Có môi trường màn hình không? Có những thiết bị màn hình nào? | Trước khi tạo GUI; xử lý headless; khám phá đa màn hình |
| `GraphicsDevice` | Thiết bị màn hình này hỗ trợ loại translucency, full-screen hoặc display mode nào? | Kiểm tra hiệu ứng gắn với màn hình của cửa sổ |
| `GraphicsConfiguration` | Cấu hình màn hình này có khả năng per-pixel alpha không, có bounds/transform nào? | Kiểm tra cấu hình cụ thể của cửa sổ, HiDPI, tương thích hình ảnh |
| `Graphics2D` | Vẽ các hình và alpha bên **trong một component** thế nào? | Vẽ hiệu ứng trong `JPanel.paintComponent`; không yêu cầu transparency của toàn cửa sổ |

Ví dụ lấy thiết bị từ một cửa sổ đang hiển thị:

```java
GraphicsConfiguration config = frame.getGraphicsConfiguration();
GraphicsDevice device = config.getDevice();

System.out.println(device.getIDstring());
System.out.println(device.getType() == GraphicsDevice.TYPE_RASTER_SCREEN);
```

Đây là **đoạn minh họa bên trong một phương thức đã có biến `frame` kiểu `JFrame`**, không phải tệp Java độc lập. `getIDstring()` là định danh do hệ thống cung cấp để chẩn đoán, không phải mã ổn định cho logic nghiệp vụ.

`GraphicsEnvironment.getLocalGraphicsEnvironment().getDefaultScreenDevice()` hữu ích khi cần chọn màn hình mặc định **trước khi tạo cửa sổ**; nhưng cửa sổ có thể nằm trên màn hình khác. Với một `JFrame` đã hiển thị, ưu tiên thiết bị từ `frame.getGraphicsConfiguration()`. Không coi tất cả màn hình của hệ thống có cùng khả năng.

## 3. Kiểm tra đúng loại hiệu ứng

`GraphicsDevice.WindowTranslucency` định nghĩa ba khả năng:

| Giá trị | Tác dụng | API thường dùng |
| --- | --- | --- |
| `TRANSLUCENT` | Toàn bộ cửa sổ có một độ mờ chung, ví dụ opacity `0.85f` | `Window.setOpacity(0.85f)` |
| `PERPIXEL_TRANSPARENT` | Mỗi pixel của hình dạng cửa sổ chỉ hoàn toàn có/không có, ví dụ cửa sổ bo tròn | `Window.setShape(Shape)` |
| `PERPIXEL_TRANSLUCENT` | Từng pixel có alpha bất kỳ từ 0 đến 1, tạo vùng mờ hoặc trong suốt cục bộ | `Window.setBackground(new Color(0, 0, 0, 0))` và vẽ alpha đúng cách |

Cú pháp kiểm tra:

```java
GraphicsDevice gd = frame.getGraphicsConfiguration().getDevice();

boolean canFade = gd.isWindowTranslucencySupported(
        GraphicsDevice.WindowTranslucency.TRANSLUCENT);

boolean canShape = gd.isWindowTranslucencySupported(
        GraphicsDevice.WindowTranslucency.PERPIXEL_TRANSPARENT);

GraphicsConfiguration gc = frame.getGraphicsConfiguration();
boolean canPerPixel = gd.isWindowTranslucencySupported(
        GraphicsDevice.WindowTranslucency.PERPIXEL_TRANSLUCENT)
        && gc.isTranslucencyCapable();
```

`GraphicsConfiguration.isTranslucencyCapable()` kiểm tra cấu hình hiện tại có hỗ trợ `PERPIXEL_TRANSLUCENT` không. Một thiết bị có thể có **nhiều** cấu hình; khi chuyển sang chế độ per-pixel, hệ thống có thể đổi `GraphicsConfiguration` của cửa sổ. Vì vậy, kiểm tra trên cấu hình hiện tại là cách thận trọng và phải xem lại cấu hình nếu ứng dụng thay đổi chế độ.

**Không nhầm lẫn:**

- `TRANSLUCENT` **không** có nghĩa là per-pixel alpha được hỗ trợ.
- `PERPIXEL_TRANSPARENT` **không** cho phép mức alpha trung gian như 0.4 ở mỗi pixel; nó điều khiển hình dạng hiển thị.
- `GraphicsDevice.isFullScreenSupported()` và `isDisplayChangeSupported()` dùng cho full-screen/display mode; **không** thay thế kiểm tra translucency.
- Chữ “accelerated” hoặc khả năng phần cứng **không** bảo đảm một hiệu ứng cụ thể của cửa sổ sẽ được hỗ trợ.

## 4. Chương trình Java chạy độc lập: có kiểm tra và có phương án dự phòng

Chương trình dưới đây:

- Chạy các thao tác Swing trên **Event Dispatch Thread (EDT)**.
- Thoát sớm trong môi trường headless, tránh tạo `JFrame` rồi mới phát sinh `HeadlessException`.
- Kiểm tra `GraphicsDevice` thực tế của `JFrame` sau khi đặt cửa sổ lên màn hình.
- Chỉ gọi `setOpacity` và `setShape` nếu phần cứng/hệ thống báo hỗ trợ; xử lý ngoại lệ do điều kiện thay đổi.
- **Luôn vẽ một hình bán trong suốt bên trong `JPanel`** bằng `Graphics2D`. Đây là hiệu ứng bên trong component, hoạt động cả khi cả cửa sổ phải giữ nguyên hình chữ nhật và opaque.
- Có nút **Đóng** vì ví dụ dùng cửa sổ `undecorated`, không có nút đóng mặc định trên thanh tiêu đề.

Tạo file **`DeviceEffectsDemo.java`**:

```java
import java.awt.*;
import java.awt.geom.RoundRectangle2D;
import javax.swing.*;

public class DeviceEffectsDemo {
    public static void main(String[] args) {
        if (GraphicsEnvironment.isHeadless()) {
            System.out.println("Headless: no screen effects");
            return;
        }
        SwingUtilities.invokeLater(DeviceEffectsDemo::showUI);
    }

    private static void showUI() {
        JFrame frame = new JFrame("GraphicsDevice capabilities");
        frame.setDefaultCloseOperation(WindowConstants.DISPOSE_ON_CLOSE);

        // Phải đặt trước khi cửa sổ trở thành displayable (pack/show).
        frame.setUndecorated(true);

        JPanel panel = new JPanel(new BorderLayout()) {
            @Override
            protected void paintComponent(Graphics g) {
                super.paintComponent(g);
                Graphics2D g2 = (Graphics2D) g.create();
                try {
                    g2.setRenderingHint(
                            RenderingHints.KEY_ANTIALIASING,
                            RenderingHints.VALUE_ANTIALIAS_ON);
                    g2.setColor(new Color(28, 57, 106));
                    g2.fillRect(0, 0, getWidth(), getHeight());

                    // Hiệu ứng alpha BÊN TRONG JPanel.
                    g2.setComposite(AlphaComposite.SrcOver.derive(0.65f));
                    g2.setColor(Color.ORANGE);
                    g2.fillRoundRect(35, 35, 240, 100, 32, 32);
                } finally {
                    g2.dispose();
                }
            }
        };

        panel.setPreferredSize(new Dimension(320, 200));
        JButton close = new JButton("Đóng");
        close.addActionListener(e -> frame.dispose());

        JPanel controls = new JPanel(new FlowLayout(FlowLayout.RIGHT));
        controls.add(close);
        panel.add(controls, BorderLayout.SOUTH);

        frame.setContentPane(panel);
        frame.pack();
        frame.setLocationRelativeTo(null);
        frame.setVisible(true);

        // Lấy thiết bị của cửa sổ hiện tại, không giả định màn hình mặc định.
        GraphicsConfiguration gc = frame.getGraphicsConfiguration();
        GraphicsDevice device = gc.getDevice();

        boolean opacity = device.isWindowTranslucencySupported(
                GraphicsDevice.WindowTranslucency.TRANSLUCENT);
        boolean shape = device.isWindowTranslucencySupported(
                GraphicsDevice.WindowTranslucency.PERPIXEL_TRANSPARENT);
        boolean perPixel = device.isWindowTranslucencySupported(
                GraphicsDevice.WindowTranslucency.PERPIXEL_TRANSLUCENT)
                && gc.isTranslucencyCapable();

        System.out.println("Opacity supported: " + opacity);
        System.out.println("Shape supported: " + shape);
        System.out.println("Per-pixel supported: " + perPixel);

        if (opacity) {
            try {
                frame.setOpacity(0.88f);
            } catch (UnsupportedOperationException
                     | IllegalComponentStateException ex) {
                System.out.println("Opacity fallback: opaque");
            }
        }

        if (shape) {
            try {
                frame.setShape(new RoundRectangle2D.Double(
                        0, 0, frame.getWidth(), frame.getHeight(), 28, 28));
            } catch (UnsupportedOperationException
                     | IllegalComponentStateException ex) {
                System.out.println("Shape fallback: rectangular");
            }
        }
    }
}
```

Chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 DeviceEffectsDemo.java
java DeviceEffectsDemo
```

Khi có GUI, cửa sổ xuất hiện cùng hình cam bán trong suốt **bên trong**. Các dòng `Opacity supported`, `Shape supported`, `Per-pixel supported` in `true` hoặc `false` **tùy môi trường**; không có một đầu ra cố định cho mọi máy. Nếu thiết bị không hỗ trợ hiệu ứng cửa sổ, chương trình vẫn vẽ hình cam trong `JPanel` và giữ cửa sổ opaque/chữ nhật. Chương trình **chỉ báo cáo** `perPixel`, không tự bật per-pixel mode.

Kiểm tra nhánh không có màn hình:

```bash
java -Djava.awt.headless=true DeviceEffectsDemo
```

Đầu ra chính xác của nhánh này:

```text
Headless: no screen effects
```

**Vì sao `setUndecorated(true)` đặt trước `pack()`?** `JFrame.setUndecorated(boolean)` không được đổi khi frame đã `displayable`. Hiệu ứng opacity/shape không được đặt lên một frame có decoration chuẩn. Ví dụ cố ý dùng cửa sổ undecorated, có nút Đóng riêng. Trong ứng dụng thực tế, nếu người dùng cần thanh tiêu đề và các điều khiển hệ thống, nên **giữ frame có decoration** và chỉ dùng hiệu ứng vẽ bên trong component.

**Vì sao vẫn có `try/catch` sau capability check?** Giá trị khả năng phụ thuộc thiết bị/hệ thống, trạng thái full-screen, decoration và thời điểm gọi. `Window.setOpacity`/`setShape` có thể ném `UnsupportedOperationException` hoặc `IllegalComponentStateException` dù ứng dụng đã kiểm tra trước đó. Phương án dự phòng hợp lý là bỏ hiệu ứng phụ mà vẫn duy trì chức năng chính.

## 5. Khi nào được dùng setBackground với alpha?

`Window.setBackground(new Color(0, 0, 0, 0))` yêu cầu kiểu translucency **`PERPIXEL_TRANSLUCENT`**, cửa sổ **undecorated** và **không ở chế độ full-screen**. Cần thiết kế đồng bộ quá trình vẽ của Swing: các panel cần trong suốt phải được vẽ đúng alpha, tránh component hoặc root pane opaque tự phủ kín nền.

Lưu ý hai thao tác có vẻ tương tự nhưng khác bản chất:

- `g2.setComposite(AlphaComposite.SrcOver.derive(0.65f))` khi vẽ hình trong `JPanel.paintComponent` pha màu với **nội dung component** đã có bên dưới. Nó **không làm lộ cửa sổ khác hoặc desktop** phía sau toàn bộ `JFrame`.
- `frame.setBackground(new Color(0, 0, 0, 0))` bật chế độ alpha theo pixel ở **cấp Window** (nếu hệ thống cho phép). Các vùng được vẽ với alpha phù hợp có thể để lộ màn hình phía sau cửa sổ.

Nếu không cần thấy desktop qua cửa sổ, thường **không cần per-pixel window translucency**: vẽ bằng `Graphics2D` trên `JPanel` vừa đơn giản, vừa ít phụ thuộc window manager hơn. Đừng bật per-pixel mode chỉ để làm một biểu tượng/bảng màu trông “mờ” bên trong giao diện.

## 6. Nhiều màn hình, DPI và thay đổi thiết bị

Một máy có thể có màn hình tích hợp và màn hình ngoài với cấu hình khác nhau. `GraphicsDevice` trả về từ màn hình mặc định lúc khởi động **không nhất thiết** là thiết bị đang chứa cửa sổ sau khi người dùng kéo cửa sổ sang màn hình thứ hai.

Cách xử lý cho ứng dụng nhiều màn hình:

1. Sau khi đặt/hiển thị cửa sổ, dùng `window.getGraphicsConfiguration().getDevice()` để chọn thiết bị hiện tại.
2. Khi cửa sổ di chuyển giữa các màn hình hoặc cấu hình màn hình thay đổi, kiểm tra lại khả năng; khôi phục cửa sổ opaque bằng `setOpacity(1.0f)` hoặc hình dạng mặc định bằng `setShape(null)` nếu không thể giữ hiệu ứng cũ.
3. Với hiệu ứng hình dạng phụ thuộc kích thước, tính lại `Shape` khi cửa sổ resize; một `RoundRectangle2D` được tạo từ kích thước cũ **không tự mở rộng** theo khung mới.
4. Tính đến HiDPI: `GraphicsConfiguration.getDefaultTransform()` có thể chứa tỷ lệ scale của màn hình. Swing thường vẽ theo hệ tọa độ logic; đừng tự nhân scale lần thứ hai khi không cần.

Đoạn xử lý sự kiện dưới đây chỉ là **minh họa** cho một `JFrame frame` đã tạo; không phải chương trình riêng:

```java
frame.addComponentListener(new java.awt.event.ComponentAdapter() {
    @Override
    public void componentMoved(java.awt.event.ComponentEvent e) {
        GraphicsDevice current =
                frame.getGraphicsConfiguration().getDevice();
        if (!current.isWindowTranslucencySupported(
                GraphicsDevice.WindowTranslucency.TRANSLUCENT)) {
            frame.setOpacity(1.0f); // Opaque fallback.
        }
    }
});
```

Trong sản phẩm thật, cũng cần xử lý thay đổi cấu hình màn hình/dock/remote session. Không cần gọi `setOpacity` liên tục trong mỗi khung hình; kiểm tra khi có sự kiện thay đổi thiết bị/cấu hình. Nếu một cửa sổ được chuyển sang full-screen bằng `GraphicsDevice.setFullScreenWindow(...)`, các hiệu ứng translucency có thể bị đặt lại; không giả định chúng tự khôi phục khi thoát full-screen.

## 7. Lỗi phổ biến khi kiểm tra GraphicsDevice

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Gọi `getDefaultScreenDevice()` trước khi kiểm tra headless | Có thể nhận `HeadlessException` trong server/CI | Gọi `GraphicsEnvironment.isHeadless()` trước |
| Chỉ kiểm tra một màn hình duy nhất | Bật hiệu ứng sai trên cửa sổ thuộc màn hình khác | Lấy `getGraphicsConfiguration().getDevice()` từ cửa sổ |
| Gọi `setOpacity(0.5f)` trên `JFrame` có thanh tiêu đề hệ thống | `IllegalComponentStateException` | Dùng undecorated nếu thật cần hiệu ứng cửa sổ; nếu không, giữ decoration và vẽ trong component |
| Nhầm `PERPIXEL_TRANSPARENT` với `PERPIXEL_TRANSLUCENT` | Shape chỉ cắt vùng hiện/ẩn, không tạo alpha tùy ý | Dùng đúng capability theo loại hiệu ứng |
| Dựa vào boolean capability rồi bỏ qua exception | Có thể lỗi khi môi trường thay đổi | Bắt ngoại lệ theo API và có fallback |
| Cố sửa display mode để vẽ hiệu ứng nhỏ | Can thiệp toàn màn hình, gây trải nghiệm xấu | Dùng `Graphics2D`/Swing painting cho hiệu ứng trong component |
| Vẽ trực tiếp bằng `component.getGraphics()` ngoài lifecycle | Hình dễ biến mất sau repaint/resize | Override `paintComponent` và gọi `repaint()` khi cần |
| Để hiệu ứng bắt buộc mới mở được GUI | Không chạy được trên remote/headless/thiết bị không hỗ trợ | Xem hiệu ứng là khả năng tùy chọn, giữ đường chạy UI chuẩn |
| Dùng API nội bộ không được hỗ trợ | Phụ thuộc JDK/hệ điều hành, dễ hỏng khi nâng cấp | Dùng `java.awt`/`javax.swing` công khai hiện hành |

## 8. Cách quyết định khi thiết kế Swing thực tế

- **Muốn mờ/pha màu một biểu tượng, shape, nền panel:** dùng `Graphics2D` + `AlphaComposite` trong `paintComponent`. Không cần khảo sát `GraphicsDevice.WindowTranslucency`.
- **Muốn cả cửa sổ bán trong suốt:** kiểm tra `TRANSLUCENT`, chỉ dùng window undecorated, không full-screen; áp dụng `setOpacity` và có fallback opaque.
- **Muốn cửa sổ bo góc/cắt theo hình:** kiểm tra `PERPIXEL_TRANSPARENT`, gọi `setShape` với shape hiện tại; cập nhật khi resize và có fallback hình chữ nhật.
- **Muốn vùng cửa sổ có alpha khác nhau để thấy desktop:** kiểm tra `PERPIXEL_TRANSLUCENT` và cấu hình phù hợp; chuẩn bị chiến lược vẽ alpha đồng bộ, fallback opaque.
- **Muốn đổi độ phân giải hoặc exclusive full-screen:** dùng `isDisplayChangeSupported()`/`isFullScreenSupported()` theo đúng mục đích; đây là một bài toán khác so với hiệu ứng trang trí Swing.

Trong mọi trường hợp, chỉ tạo/sửa component Swing trên **EDT**; với animation cần cập nhật nhiều lần, có thể dùng `javax.swing.Timer` để thay đổi trạng thái và gọi `repaint()` thay vì chặn EDT bằng `Thread.sleep(...)`. Đừng làm giảm khả năng đọc, thao tác chuột/bàn phím hoặc đóng cửa sổ chỉ để giữ hiệu ứng trang trí.

## 9. Tự kiểm tra kiến thức

1. **`GraphicsEnvironment.isHeadless()` là `true`:** có nên gọi `getScreenDevices()` rồi tạo cửa sổ? **Không.** Bỏ qua GUI hoặc chuyển sang luồng xử lý không cần màn hình.
2. **Thiết bị hỗ trợ `TRANSLUCENT` nhưng không hỗ trợ `PERPIXEL_TRANSLUCENT`:** có dùng `setBackground(Color alpha=0)` để tạo lỗ trong suốt không? **Không.** Hai capability khác nhau; có thể dùng `setOpacity` cho toàn cửa sổ hoặc vẽ alpha trong component.
3. **Cửa sổ đang có thanh tiêu đề bình thường:** có thể gọi `setShape(nonNull)` ngay khi `PERPIXEL_TRANSPARENT` là `true` không? **Không.** Còn cần undecorated và không full-screen.
4. **Một `JPanel` có hình bán trong suốt:** có bắt buộc bật window translucency không? **Không.** `Graphics2D.setComposite` đủ cho nội dung component.
5. **Người dùng kéo `JFrame` sang màn hình ngoài:** có tiếp tục dùng capability của màn hình đầu mãi không? **Không.** Cần xét `GraphicsConfiguration` hiện tại và khôi phục fallback khi capability đổi.
6. **`isFullScreenSupported()` là `true`:** có suy ra `setOpacity` và `setShape` sẽ được hỗ trợ không? **Không.** Đây là các khả năng độc lập; full-screen còn hạn chế các hiệu ứng cửa sổ.

### Tài liệu API Java chính thức (còn được hỗ trợ)

- [GraphicsDevice và `isWindowTranslucencySupported`](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/java/awt/GraphicsDevice.html)
- [GraphicsDevice.WindowTranslucency](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/java/awt/GraphicsDevice.WindowTranslucency.html)
- [GraphicsConfiguration và `isTranslucencyCapable`](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/java/awt/GraphicsConfiguration.html)
- [GraphicsEnvironment và `isHeadless`](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/java/awt/GraphicsEnvironment.html)
- [Window: `setOpacity`, `setShape`, `setBackground`](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/java/awt/Window.html)
- [JComponent và `paintComponent`](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/javax/swing/JComponent.html)
