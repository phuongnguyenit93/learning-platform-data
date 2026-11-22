# JLayer và LayerUI trong ứng dụng Swing desktop còn được duy trì

## 1. Khi nào JLayer vẫn có giá trị?

`javax.swing.JLayer` và `javax.swing.plaf.LayerUI` là API chính thức của Swing, được bổ sung từ Java 7 và **vẫn tồn tại, hoạt động trong các JDK hiện đại** như Java 17, 21 và 25. Trong ứng dụng desktop xây dựng bằng Swing, chúng cho phép thêm lớp trình bày và nhận thông báo sự kiện cho **cả một vùng giao diện gồm nhiều component** mà không phải sửa riêng từng `JButton`, `JTextField` hay `JPanel`.

Các nhu cầu thực tế vẫn phù hợp:
- Vẽ viền nổi bật, cảnh báo, biểu tượng hướng dẫn hoặc lớp trạng thái phía trên một biểu mẫu.
- Theo dõi chuyển động chuột, focus hoặc một nhóm sự kiện AWT trong một cây component cụ thể.
- Bổ sung trạng thái như “đang tải”, “cần kiểm tra dữ liệu” cho giao diện đã có, trong khi vẫn giữ cấu trúc và listener sẵn có.
- Đóng gói hiệu ứng giao diện tái sử dụng trong một lớp `LayerUI`.

**Giới hạn phạm vi:** `JLayer` là công cụ *trang trí và quan sát sự kiện của Swing*; không phải một cửa sổ riêng, không tự động khóa tương tác và không thay thế quy tắc kiểm tra dữ liệu hay phân quyền ở tầng ứng dụng. Chủ đề này chỉ dùng các khả năng còn được hỗ trợ trong `java.desktop`, không dựa vào cơ chế desktop đã bị loại bỏ.

## 2. Hai lớp phối hợp như thế nào?

Mô hình cơ bản:

```text
JFrame
  └── JLayer<JPanel>                   ← lớp bao của một vùng giao diện
        ├── view: JPanel               ← form thật và các component con
        │     ├── JButton
        │     └── JLabel
        └── UI delegate: LayerUI<JPanel>
              ├── paint(...)           ← vẽ lớp bổ sung
              ├── installUI(...)       ← đăng ký loại sự kiện cần quan sát
              ├── process...Event(...) ← nhận thông báo sự kiện
              └── uninstallUI(...)     ← hoàn nguyên thiết lập
```

- **`JLayer<V extends Component>`** là component bao một `view`. Tạo bằng `new JLayer<>(view, layerUI)`, hoặc đặt `view` / `LayerUI` bằng `setView` / `setUI`. Bạn vẫn gắn `JLayer` vào bố cục Swing như một `JComponent` bình thường.
- **`LayerUI<V extends Component>`** là đối tượng quyết định cách vẽ và cách tiếp nhận thông báo sự kiện của `JLayer`. Tạo lớp con khi cần hiệu ứng riêng.
- **`paint(Graphics, JComponent)`** được gọi khi `JLayer` vẽ. Cách thường dùng: `super.paint(g, c)` để vẽ giao diện gốc, sau đó vẽ overlay. Nếu bỏ `super.paint`, nội dung thật có thể biến mất.
- **`setLayerEventMask(long)`** chọn nhóm sự kiện được chuyển đến `LayerUI`. Mặc định mask là `0`, nghĩa là không nhận thông báo sự kiện qua cơ chế này.
- **`installUI`/`uninstallUI`** là nơi thiết lập và dọn event mask. Luôn gọi phiên bản `super` để giữ vòng đời UI delegate đúng chuẩn.

`JLayer` là lớp `final`; không cần và không thể kế thừa nó để trang trí giao diện. Bạn thường kế thừa **`LayerUI`** rồi cung cấp đối tượng đó cho `JLayer`. `JLayer` tự quản lý bố cục phần `view` và `glassPane`; không cài `LayoutManager` tùy ý trực tiếp lên `JLayer`.

### JLayer khác gì các lớp giao diện tương tự?

| Công cụ | Dùng khi | Phạm vi |
| --- | --- | --- |
| `JLayer + LayerUI` | Cần overlay hoặc nhận thông báo sự kiện của cả vùng component đang có | Một cây component được bao bởi `JLayer` |
| `JPanel.paintComponent(...)` | Tự sở hữu một panel và chỉ cần vẽ nội dung của panel ấy | Chính panel |
| `JLayeredPane` | Cần sắp xếp các component thật thành những tầng với thứ tự chồng lên nhau | Vùng `JLayeredPane` |
| `JRootPane` / glass pane của `JFrame` | Cần phủ hoặc tương tác ở cấp cửa sổ | Phần root pane tương ứng |

Các công cụ này có nhiệm vụ khác nhau; chọn `JLayer` khi bạn muốn **gắn thêm hiệu ứng cho component hiện hữu** và giữ logic của component đó.

## 3. Ví dụ Java 17+: overlay và theo dõi chuyển động chuột

Chương trình sau minh họa đầy đủ các điểm cần học:

1. Bao `JPanel` có `JButton` và `JLabel` bằng `JLayer<JPanel>`.
2. `PointerLayerUI.paint` vẽ thanh xanh bán trong suốt phía trên form.
3. `installUI` đăng ký `AWTEvent.MOUSE_MOTION_EVENT_MASK`; `processMouseMotionEvent` cập nhật tọa độ khi trỏ chuột đi qua các component bên trong layer.
4. `JButton` vẫn nhận `ActionEvent` thông thường; lớp overlay chỉ vẽ và quan sát.
5. Chế độ `--check` xác minh đăng ký/hủy event mask **không cần mở cửa sổ đồ họa**.

Tạo tệp tên **`JLayerDemo.java`** bằng UTF-8:

```java
import java.awt.AWTEvent;
import java.awt.BorderLayout;
import java.awt.Color;
import java.awt.Graphics;
import java.awt.Graphics2D;
import java.awt.Point;
import java.awt.event.MouseEvent;
import javax.swing.BorderFactory;
import javax.swing.JButton;
import javax.swing.JComponent;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JLayer;
import javax.swing.JPanel;
import javax.swing.SwingUtilities;
import javax.swing.plaf.LayerUI;

public class JLayerDemo {
    private static final class PointerLayerUI extends LayerUI<JPanel> {
        private String caption = "Di chuyển chuột trong khung";

        @Override
        public void paint(Graphics g, JComponent c) {
            super.paint(g, c);
            Graphics2D g2 = (Graphics2D) g.create();
            try {
                g2.setColor(new Color(25, 75, 135, 220));
                g2.fillRoundRect(8, 8, Math.max(1, c.getWidth() - 16), 36, 12, 12);
                g2.setColor(Color.WHITE);
                g2.drawString(caption, 18, 31);
            } finally {
                g2.dispose();
            }
        }

        @Override
        public void installUI(JComponent c) {
            super.installUI(c);
            ((JLayer<?>) c).setLayerEventMask(AWTEvent.MOUSE_MOTION_EVENT_MASK);
        }

        @Override
        public void uninstallUI(JComponent c) {
            ((JLayer<?>) c).setLayerEventMask(0);
            super.uninstallUI(c);
        }

        @Override
        protected void processMouseMotionEvent(
                MouseEvent e, JLayer<? extends JPanel> layer) {
            if (e.getID() == MouseEvent.MOUSE_MOVED
                    || e.getID() == MouseEvent.MOUSE_DRAGGED) {
                Point p = SwingUtilities.convertPoint(
                        e.getComponent(), e.getPoint(), layer);
                caption = "Chuột: x=" + p.x + ", y=" + p.y;
                layer.repaint();
            }
        }
    }

    private static void showWindow() {
        JPanel view = new JPanel(new BorderLayout(12, 12));
        view.setBorder(BorderFactory.createEmptyBorder(56, 16, 16, 16));

        JLabel status = new JLabel("Nút trong JLayer vẫn hoạt động.");
        JButton button = new JButton("Nhấn thử");
        button.addActionListener(e -> status.setText("JButton đã nhận ActionEvent."));
        view.add(button, BorderLayout.NORTH);
        view.add(status, BorderLayout.CENTER);

        JLayer<JPanel> layer = new JLayer<>(view, new PointerLayerUI());
        JFrame frame = new JFrame("JLayer + LayerUI");
        frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
        frame.add(layer);
        frame.setSize(430, 225);
        frame.setLocationRelativeTo(null);
        frame.setVisible(true);
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && "--check".equals(args[0])) {
            SwingUtilities.invokeAndWait(() -> {
                JLayer<JPanel> layer =
                        new JLayer<>(new JPanel(), new PointerLayerUI());
                System.out.println("Event mask active: "
                        + (layer.getLayerEventMask() == AWTEvent.MOUSE_MOTION_EVENT_MASK));
                layer.setUI(null);
                System.out.println("Event mask cleared: "
                        + (layer.getLayerEventMask() == 0));
            });
        } else {
            SwingUtilities.invokeLater(JLayerDemo::showWindow);
        }
    }
}
```

Biên dịch bằng JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 JLayerDemo.java
java JLayerDemo --check
```

Kết quả `--check` (không cần màn hình):

```text
Event mask active: true
Event mask cleared: true
```

Để xem cửa sổ Swing, chạy trên máy có desktop GUI:

```bash
java JLayerDemo
```

**Hành vi giao diện:** thanh xanh ở phía trên hiển thị vị trí trỏ chuột trong vùng được bọc; bấm **Nhấn thử** làm `JLabel` chuyển sang “JButton đã nhận ActionEvent.”. Chế độ GUI không quy định một chuỗi stdout cố định. Kết quả `--check` ở trên là stdout xác định đã được kiểm tra.

## 4. Giải thích chính xác vòng đời của ví dụ

### Bước 1 — Vẽ giao diện gốc rồi mới vẽ overlay

`LayerUI.paint(...)` gọi `super.paint(g,c)` trước, để `JLayer` và các component con xuất hiện bình thường. Sau đó:
- `(Graphics2D) g.create()` tạo bản sao trạng thái đồ họa riêng cho lớp trang trí.
- Màu `new Color(25, 75, 135, 220)` có alpha 220/255, tạo hiệu ứng có độ trong suốt.
- `fillRoundRect` và `drawString` vẽ thêm vùng chú thích; `dispose()` giải phóng bản sao `Graphics2D`, không đóng `Graphics` do Swing cung cấp.

Không giữ `Graphics` trong field để dùng ở lần repaint sau; mỗi lần Swing gọi `paint` phải vẽ lại từ trạng thái hiện tại. Với hiệu ứng phụ thuộc kích thước, đọc `c.getWidth()`/`c.getHeight()` khi paint, thay vì giả định kích thước cố định.

### Bước 2 — Bật đúng nhóm sự kiện

`installUI(JComponent c)` được gọi khi `LayerUI` được cài lên `JLayer`. Đoạn:

```java
((JLayer<?>) c).setLayerEventMask(AWTEvent.MOUSE_MOTION_EVENT_MASK);
```

chỉ đăng ký thông báo di chuyển/kéo chuột. Nếu cần thêm sự kiện nhấn/thả chuột, có thể kết hợp `AWTEvent.MOUSE_EVENT_MASK` bằng toán tử bit `|`. Không nên bật tất cả mask chỉ để “phòng khi cần”.

**Điều kiện rất quan trọng:** những sự kiện mà `LayerUI` nhận qua `eventDispatched` được chuyển khi `JLayer` **đã displayable** (nằm trong cây giao diện được hiện thực hóa). Tạo `JLayer` trong bộ nhớ chưa đủ để thử nhận sự kiện chuột. Vì thế chế độ `--check` chỉ kiểm tra cấu hình mask, không giả vờ kiểm thử tương tác chuột thật.

### Bước 3 — Nhận sự kiện từ các component con

Mặc định, `LayerUI.eventDispatched(AWTEvent, JLayer)` phân loại sự kiện và gọi các phương thức `process...Event` thích hợp. Ví dụ override `processMouseMotionEvent` với đúng generic `JLayer<? extends JPanel>`.

Một `MouseEvent` sinh ra từ `JButton` chứa tọa độ cục bộ của nút, khác tọa độ của layer. Vì vậy:

```java
Point p = SwingUtilities.convertPoint(
        e.getComponent(), e.getPoint(), layer);
```

chuyển tọa độ từ component nguồn sang `JLayer` trước khi hiển thị. Sau khi đổi `caption`, gọi `layer.repaint()` để Swing lên lịch vẽ overlay mới. Không gọi `paint` trực tiếp và không tạo `Graphics` từ bên ngoài vòng đời painting chỉ để cập nhật chuột.

### Bước 4 — Gỡ UI delegate sạch sẽ

Khi `LayerUI` được gỡ/thay, `uninstallUI` đặt mask về `0` rồi gọi `super.uninstallUI(c)`. Trong `--check`, `layer.setUI(null)` được sử dụng có chủ đích để kích hoạt gỡ UI delegate và chứng minh mask được dọn. **Không gỡ UI của layer đang dùng trong cửa sổ** trừ khi bạn thật sự muốn bỏ phần trang trí.

## 5. Các quy tắc thực hành trong Swing hiện nay

### Giữ thao tác UI trên Event Dispatch Thread (EDT)

Swing yêu cầu phần lớn thao tác tạo, đọc và cập nhật trạng thái component chạy trên **EDT**. `SwingUtilities.invokeLater(JLayerDemo::showWindow)` tạo cửa sổ trên EDT; `ActionListener` và việc xử lý sự kiện chuột cũng hoạt động trong cơ chế dispatch của AWT/Swing. Đừng chặn EDT bằng truy vấn mạng, ngủ luồng hoặc xử lý file lớn. Với việc lâu, dùng `SwingWorker` hoặc cơ chế chạy nền phù hợp rồi cập nhật UI trên EDT.

### Overlay hiển thị không đồng nghĩa khóa điều khiển

Một lớp màu xám/vòng xoay vẽ bởi `paint` chỉ là **hình ảnh**. Nó không tự chặn bấm nút, nhập liệu hay phím tắt. Khi muốn chặn thao tác trong lúc lưu dữ liệu, phải điều khiển trạng thái `setEnabled(false)` của các nút/trường liên quan hoặc triển khai cơ chế điều khiển tương tác có chủ đích, đồng thời khôi phục chúng khi hoàn tất. Không dựa vào overlay để bảo vệ nghiệp vụ.

### Trạng thái và tái sử dụng LayerUI

Trong ví dụ, `caption` là trạng thái riêng của **một** `PointerLayerUI` gắn vào **một** `JLayer`. Nếu dùng chung một `LayerUI` có field thay đổi cho nhiều layer, trạng thái có thể ảnh hưởng lẫn nhau. Với UI delegate chia sẻ, hãy thiết kế theo kiểu không có trạng thái thay đổi hoặc lưu trạng thái riêng cho mỗi layer; với UI delegate có state, thường tạo từng instance.

Với hiệu ứng diễn tiến theo thời gian, có thể dùng `javax.swing.Timer` để cập nhật trạng thái rồi `repaint` trên EDT. Không tạo vòng lặp vô hạn hoặc gọi `Thread.sleep` trong `paint`.

### Tương tác với Look and Feel

`LayerUI` là UI delegate tùy biến **độc lập với Look and Feel**; nó không tự được thay bằng delegate mới khi hệ thống đổi Look and Feel như nhiều Swing component thông thường. Nếu ứng dụng cho phép đổi theme lúc chạy, hãy kiểm tra lại màu tương phản, font, kích thước overlay và cách các component con render sau khi cập nhật theme.

### Giữ hiệu năng và phạm vi quan sát hợp lý

- Chỉ bọc vùng thực sự cần hiệu ứng. `JLayer` nhận sự kiện từ cả cây con đã đăng ký và việc repaint quá nhiều có thể tốn công.
- Tránh làm phép tính, truy cập file hay gọi network trong `paint` hoặc `processMouseMotionEvent`; các lời gọi này có thể xảy ra liên tục.
- Bật mask cụ thể, tắt mask khi gỡ UI; không giữ listener hoặc tham chiếu tới cửa sổ đã đóng.
- Khi vẽ, tránh che nội dung quan trọng; kiểm tra font, kích thước cửa sổ nhỏ, scaling/HiDPI và các Look and Feel được hỗ trợ.

## 6. Lỗi thường gặp và cách kiểm tra

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra/sửa |
| --- | --- | --- |
| Mở GUI nhưng không thấy view bên dưới | Override `paint` mà quên `super.paint(g,c)` | Vẽ view trước, sau đó overlay |
| Layer không nhận sự kiện di chuyển | Mask chưa đăng ký, đăng ký sai nhóm hoặc layer chưa displayable | `setLayerEventMask(AWTEvent.MOUSE_MOTION_EVENT_MASK)` trong `installUI` và thử bằng cửa sổ thật |
| Tọa độ trỏ chuột sai khi hover nút con | `e.getPoint()` là tọa độ của component nguồn | Dùng `SwingUtilities.convertPoint(..., layer)` |
| Nhãn overlay không đổi | Chỉ sửa field nhưng chưa yêu cầu repaint | Gọi `layer.repaint()` sau khi đổi trạng thái |
| Nút vẫn nhận click dưới lớp phủ | Painting chỉ thay đổi hình ảnh | Vô hiệu hóa điều khiển hoặc thiết kế kiểm soát tương tác riêng |
| Component con bị lag khi rê chuột | Xử lý quá nặng hoặc repaint cả vùng quá thường xuyên | Giữ callback ngắn, giới hạn vùng repaint khi cần |
| Mask vẫn bật sau khi thay UI | Thiếu cleanup trong `uninstallUI` | Đặt mask về `0`, gọi `super.uninstallUI` |
| Overlay của nhiều vùng hiển thị sai trạng thái | Chia sẻ một `LayerUI` có state giữa nhiều layer | Tạo instance riêng hoặc thiết kế stateless |

**Bài kiểm thử thủ công cho chế độ cửa sổ:**

1. Chạy `java JLayerDemo`, xác nhận có tiêu đề thanh xanh và nội dung form.
2. Di chuyển chuột trên phần nền, nút và nhãn; tọa độ trong thanh xanh phải thay đổi.
3. Bấm **Nhấn thử**, xác nhận label đổi nội dung, chứng minh overlay không chiếm mất `ActionEvent`.
4. Đổi kích thước cửa sổ và quan sát overlay vẫn được vẽ lại theo chiều rộng hiện tại.
5. Chạy `java JLayerDemo --check` và xác nhận cả hai dòng `true`.

## 7. Ghi nhớ

- Trong các ứng dụng desktop Swing được duy trì, `JLayer` vẫn là cách chính thức để **bao một vùng component**, còn `LayerUI` bổ sung **painting** và **thông báo sự kiện** cho vùng đó.
- Gọi `super.paint` trước khi vẽ thêm; tạo/bỏ bản sao `Graphics2D` cẩn thận.
- Sự kiện chỉ được nhận khi đăng ký mask phù hợp; cơ chế chuyển sự kiện cần `JLayer` displayable và phải dọn mask ở `uninstallUI`.
- Giao diện Swing làm việc trên EDT; dùng `repaint` để cập nhật, dùng listener và trạng thái component để điều khiển tương tác.
- Overlay không thay thế listener, validation hoặc cơ chế chặn thao tác; thiết kế chức năng theo đúng mục đích.

### API chính thức còn được hỗ trợ

- [Java SE 25: `javax.swing.JLayer`](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/javax/swing/JLayer.html)
- [Java SE 25: `javax.swing.plaf.LayerUI`](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/javax/swing/plaf/LayerUI.html)
- [Java SE 25: `javax.swing.SwingUtilities`](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/javax/swing/SwingUtilities.html)
