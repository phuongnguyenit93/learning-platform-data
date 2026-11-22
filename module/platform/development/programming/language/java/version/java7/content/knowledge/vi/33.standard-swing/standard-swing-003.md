# Theo dõi sự kiện trong phạm vi lớp trang trí với Swing `JLayer` và `LayerUI`

**Chủ đề:** Swing chuẩn  
**Bài:** Theo dõi sự kiện trong phạm vi lớp trang trí  
**Môi trường:** Java 17+ (API `java.desktop` vẫn có trong các bản JDK hiện đại).

Khi muốn vẽ hiệu ứng hoặc quan sát thao tác chuột trên **một nhóm thành phần Swing** (ví dụ một biểu mẫu có nút, ô nhập và danh sách), ta có thể bọc nhóm đó bằng `javax.swing.JLayer`. `JLayer` dùng một đối tượng `javax.swing.plaf.LayerUI` để quản lý phần trang trí và nhận thông báo sự kiện từ **chính layer cùng các thành phần con**. Nhờ vậy có thể theo dõi sự kiện trong phạm vi giao diện cần quan sát mà không phải gắn `MouseListener` riêng vào từng nút/ô nhập.

Đây là cơ chế Swing vẫn được hỗ trợ, hữu ích cho overlay hướng dẫn, hiệu ứng theo vị trí con trỏ, đánh dấu vùng tương tác, đo lường tương tác ở phạm vi cục bộ và một số hành vi UI phụ trợ. `JLayer` **không phải hệ thống log toàn ứng dụng** và mặc định **không được đăng ký nhận loại sự kiện nào**.

## 1. Cấu trúc và luồng xử lý sự kiện

`JLayer<V>` bao lấy một thành phần `view` kiểu `V extends Component`; `LayerUI<V>` là đối tượng delegate chịu trách nhiệm vẽ và xử lý thông báo. `JLayer` còn có một `glassPane` riêng, nhưng không cần tạo glass pane tùy chỉnh nếu mục tiêu chỉ là quan sát sự kiện và vẽ overlay.

Luồng điển hình:

1. Tạo `view` gồm các thành phần thật, chẳng hạn `JPanel` chứa `JButton`, `JTextField`.
2. Tạo `LayerUI` và bọc bằng `new JLayer<>(view, layerUI)`.
3. Trong `LayerUI.installUI(JComponent)`, bật **đúng nhóm sự kiện** cần nhận bằng `layer.setLayerEventMask(mask)`.
4. Khi `JLayer` đang **displayable**, các sự kiện AWT phù hợp phát sinh trong phạm vi layer và các thành phần con được chuyển đến `LayerUI.eventDispatched(AWTEvent, JLayer)`.
5. Cách triển khai `LayerUI.eventDispatched` mặc định phân phối tiếp theo loại sự kiện đến các phương thức `processMouseEvent`, `processMouseMotionEvent`, `processMouseWheelEvent`, `processKeyEvent`, v.v. Ta thường ghi đè phương thức chuyên biệt tương ứng.
6. Khi trạng thái overlay thay đổi, gọi `layer.repaint()`; Swing sẽ vẽ lại qua `LayerUI.paint(Graphics, JComponent)`.
7. Trong `uninstallUI`, tắt mask bằng `setLayerEventMask(0)` và gọi `super.uninstallUI(c)`.

`JLayer` chỉ theo dõi sự kiện khớp **mask đã đăng ký**. Nó không thay thế cơ chế xử lý sự kiện của thành phần con: nút vẫn có thể nhận click và chạy `ActionListener` bình thường nếu layer chỉ quan sát. Tuy nhiên, code trong `LayerUI` có thể thay đổi sự kiện nếu tự `consume()` hoặc can thiệp glass pane; điều này phải là quyết định có chủ đích.

## 2. Chọn đúng event mask

`JLayer.setLayerEventMask(long)` nhận các bit mask khai báo trong `java.awt.AWTEvent`. Kết hợp nhiều mask bằng toán tử OR bit `|`.

| Mục đích theo dõi | Mask cần bật | Callback thường ghi đè |
|---|---|---|
| Nhấn, thả, click, vào/ra một thành phần | `AWTEvent.MOUSE_EVENT_MASK` | `processMouseEvent` |
| Di chuyển hoặc kéo chuột | `AWTEvent.MOUSE_MOTION_EVENT_MASK` | `processMouseMotionEvent` |
| Cuộn bánh xe | `AWTEvent.MOUSE_WHEEL_EVENT_MASK` | `processMouseWheelEvent` |
| Phím khi thành phần có focus | `AWTEvent.KEY_EVENT_MASK` | `processKeyEvent` |
| Focus nhận/mất | `AWTEvent.FOCUS_EVENT_MASK` | `processFocusEvent` |
| Trạng thái hiển thị, kích thước, vị trí thành phần | `AWTEvent.COMPONENT_EVENT_MASK` | `processComponentEvent` |
| Thay đổi hierarchy | `AWTEvent.HIERARCHY_EVENT_MASK` | `processHierarchyEvent` |
| Input method (nhập ngôn ngữ phức tạp) | `AWTEvent.INPUT_METHOD_EVENT_MASK` | `processInputMethodEvent` |

**Lưu ý về phạm vi:**

- `MOUSE_EVENT_MASK` **không bao gồm** `MOUSE_MOTION_EVENT_MASK` hoặc `MOUSE_WHEEL_EVENT_MASK`; muốn quan sát cả ba loại phải bật đủ.
- `KEY_EVENT_MASK` chỉ cho phép nhận sự kiện bàn phím **thực sự được phát sinh** trong vùng layer; không bảo đảm layer nhận mọi phím. Sự kiện còn phụ thuộc focus, thành phần đích và cơ chế input của Swing. Đối với phím tắt/nút điều khiển, ưu tiên `InputMap`/`ActionMap` và key bindings phù hợp thay vì dựa vào bắt `KeyEvent` ở layer.
- Các callback được kích hoạt từ sự kiện phát sinh ở **thành phần con** cũng như ở bản thân `JLayer`. Ví dụ nhấn chuột trên một `JButton` có thể tạo sự kiện với `e.getComponent()` là `JButton` đó.
- Không ghi đè `eventDispatched` cùng các `process...Event` rồi bỏ qua `super.eventDispatched(e, layer)`: nếu thay hoàn toàn cách phân phối mặc định, các callback chuyên biệt sẽ không còn được gọi tự động.
- `JLayer` cần có `LayerUI` và phải `displayable` thì cơ chế phân phối AWT thực tế mới hoạt động. Khởi tạo đối tượng trong môi trường headless chỉ có thể kiểm tra cấu hình/lifecycle, **không xác nhận được luồng sự kiện GUI thực**.

## 3. Điểm dễ sai: tọa độ sự kiện và vòng đời UI

`MouseEvent.getPoint()` luôn được hiểu theo **hệ tọa độ của thành phần nguồn**. Nếu overlay vẽ trên layer, tọa độ phải được đổi sang hệ tọa độ `JLayer`:

```java
Point p = SwingUtilities.convertPoint(e.getComponent(), e.getPoint(), layer);
```

Đây là **đoạn mã minh họa bên trong callback**: `e` là `MouseEvent`; `layer` là tham số `JLayer<? extends JPanel>` mà callback nhận. Không lấy trực tiếp `e.getX()`/`e.getY()` để vẽ lên layer khi nguồn sự kiện có thể là nút nằm ở vị trí khác trong panel.

**Vòng đời:** trong `installUI` bật các mask, trong `uninstallUI` đưa mask về `0`. Khi đổi `LayerUI` hoặc giải phóng view, việc dọn mask giúp tránh giữ cấu hình theo dõi không còn mong muốn. Không tự gọi `addMouseListener` lên mọi thành phần con nếu đã dùng `LayerUI` cho đúng phạm vi. Không cố `layer.add(button)`; `JLayer` quản lý nội dung qua `setView(...)` hoặc constructor.

**Vẽ trang trí:** ghi đè `paint`, gọi `super.paint(g, c)` để thành phần gốc vẫn hiện, rồi dùng `Graphics2D copy = (Graphics2D) g.create()` để vẽ overlay. Đảm bảo `copy.dispose()` trong `finally`; không giữ `Graphics` giữa các lần repaint. Chỉ đổi trạng thái trong callback; không dựng UI mới hoặc thực hiện I/O nặng bên trong `paint`.

## 4. Ví dụ hoàn chỉnh: theo dõi nhấn/di chuyển chuột trong cả panel

Chương trình dưới đây:

- Bọc `JPanel` chứa hai nút bằng `JLayer<JPanel>`.
- `MonitorUI` chỉ đăng ký **mouse** và **mouse motion**.
- Khi người dùng **nhấn** chuột ở bất kỳ thành phần nào trong layer, tăng bộ đếm và hiển thị tên lớp nguồn sự kiện trên overlay.
- Khi di chuột/kéo chuột, vẽ một vòng tròn ở tọa độ đã chuyển sang hệ tọa độ layer.
- Nút `Lưu` vẫn có `ActionListener` riêng để minh họa theo dõi mà không chặn hành vi gốc.
- Có chế độ `--self-test` để kiểm tra việc bật và gỡ mask mà không mở cửa sổ.

Tạo tệp **`LayerEventMonitorDemo.java`** và lưu ở UTF-8:

```java
import java.awt.AWTEvent;
import java.awt.Color;
import java.awt.Dimension;
import java.awt.FlowLayout;
import java.awt.Graphics;
import java.awt.Graphics2D;
import java.awt.Point;
import java.awt.event.MouseEvent;
import javax.swing.JButton;
import javax.swing.JComponent;
import javax.swing.JFrame;
import javax.swing.JLayer;
import javax.swing.JPanel;
import javax.swing.SwingUtilities;
import javax.swing.WindowConstants;
import javax.swing.plaf.LayerUI;

public class LayerEventMonitorDemo {
    static final class MonitorUI extends LayerUI<JPanel> {
        private int presses;
        private Point pointer;
        private String message = "Chưa có sự kiện nhấn chuột";

        @Override
        public void installUI(JComponent c) {
            super.installUI(c);
            ((JLayer<?>) c).setLayerEventMask(
                AWTEvent.MOUSE_EVENT_MASK | AWTEvent.MOUSE_MOTION_EVENT_MASK
            );
        }

        @Override
        public void uninstallUI(JComponent c) {
            ((JLayer<?>) c).setLayerEventMask(0);
            super.uninstallUI(c);
        }

        @Override
        protected void processMouseEvent(
                MouseEvent e, JLayer<? extends JPanel> layer) {
            if (e.getID() == MouseEvent.MOUSE_PRESSED) {
                presses++;
                pointer = SwingUtilities.convertPoint(
                    e.getComponent(), e.getPoint(), layer
                );
                message = "Nhấn #" + presses + " tại " +
                          e.getComponent().getClass().getSimpleName();
                layer.repaint();
            }
        }

        @Override
        protected void processMouseMotionEvent(
                MouseEvent e, JLayer<? extends JPanel> layer) {
            if (e.getID() == MouseEvent.MOUSE_MOVED ||
                e.getID() == MouseEvent.MOUSE_DRAGGED) {
                pointer = SwingUtilities.convertPoint(
                    e.getComponent(), e.getPoint(), layer
                );
                layer.repaint();
            }
        }

        @Override
        public void paint(Graphics g, JComponent c) {
            super.paint(g, c);
            Graphics2D g2 = (Graphics2D) g.create();
            try {
                g2.setColor(new Color(24, 49, 82, 220));
                g2.fillRoundRect(8, 8, 350, 30, 10, 10);
                g2.setColor(Color.WHITE);
                g2.drawString(message, 16, 28);

                if (pointer != null) {
                    g2.setColor(new Color(0, 150, 240, 190));
                    g2.drawOval(pointer.x - 12, pointer.y - 12, 24, 24);
                }
            } finally {
                g2.dispose();
            }
        }
    }

    private static JFrame createFrame() {
        JPanel view = new JPanel(new FlowLayout(FlowLayout.CENTER, 20, 68));
        JButton save = new JButton("Lưu");
        save.addActionListener(e -> System.out.println("Action: Lưu"));
        view.add(save);
        view.add(new JButton("Hủy"));
        view.setPreferredSize(new Dimension(440, 200));

        JLayer<JPanel> layer = new JLayer<>(view, new MonitorUI());
        JFrame frame = new JFrame("JLayer event monitor");
        frame.setDefaultCloseOperation(WindowConstants.EXIT_ON_CLOSE);
        frame.setContentPane(layer);
        frame.pack();
        frame.setLocationRelativeTo(null);
        return frame;
    }

    private static void selfTest() {
        JLayer<JPanel> layer = new JLayer<>(new JPanel(), new MonitorUI());
        long expected = AWTEvent.MOUSE_EVENT_MASK |
                        AWTEvent.MOUSE_MOTION_EVENT_MASK;

        if (layer.getLayerEventMask() != expected) {
            throw new AssertionError("missing mouse event masks");
        }
        layer.setUI(null); // gọi uninstallUI, gỡ mask
        if (layer.getLayerEventMask() != 0) {
            throw new AssertionError("mask was not removed");
        }
        System.out.println("SELF_TEST_OK");
    }

    public static void main(String[] args) throws Exception {
        if (args.length == 1 && "--self-test".equals(args[0])) {
            SwingUtilities.invokeAndWait(LayerEventMonitorDemo::selfTest);
            return;
        }
        SwingUtilities.invokeLater(() -> createFrame().setVisible(true));
    }
}
```

Biên dịch bằng **JDK 17 trở lên** (dòng `--release 17` bảo đảm mã dùng API Java 17):

```bash
javac --release 17 -encoding UTF-8 LayerEventMonitorDemo.java
java LayerEventMonitorDemo --self-test
java LayerEventMonitorDemo
```

Lệnh `--self-test` in chính xác:

```text
SELF_TEST_OK
```

Lệnh cuối mở cửa sổ Swing trong môi trường đồ họa. Di chuyển chuột trong panel sẽ thấy vòng tròn di chuyển; nhấn chuột trên nút hoặc nền panel sẽ cập nhật dòng trạng thái có bộ đếm; bấm **Lưu** còn in `Action: Lưu` ở console khi nút được kích hoạt. **Đó là quan sát thủ công**, không phải stdout cố định từ chế độ GUI.

**Phân tích các vị trí quan trọng trong mã:**

- `installUI`/`uninstallUI` xử lý lifecycle mask theo đúng `JLayer`, không sửa trực tiếp các nút bên trong.
- `processMouseEvent` chỉ đếm `MOUSE_PRESSED`; một cú click thường tạo các sự kiện khác như `MOUSE_RELEASED` và `MOUSE_CLICKED`, nhưng sẽ không bị đếm ba lần.
- `processMouseMotionEvent` nhận `MOUSE_MOVED`/`MOUSE_DRAGGED` vì đã bật `MOUSE_MOTION_EVENT_MASK`.
- `SwingUtilities.convertPoint` giúp vị trí overlay chính xác dù sự kiện đến từ một nút con.
- `super.paint(g, c)` vẽ phần view, sau đó phần đồ họa trên layer được phủ lên. Không gọi `e.consume()`, nên `ActionListener` của nút vẫn hoạt động.
- `SwingUtilities.invokeLater` và `invokeAndWait` đưa thao tác Swing vào **Event Dispatch Thread (EDT)**. GUI cần màn hình; kiểm thử mask có thể chạy khi không mở cửa sổ.

## 5. Quan sát sự kiện mà không phá hành vi của thành phần con

Trường hợp thông thường là **quan sát** (observation), không phải chặn sự kiện. Nên dùng quy tắc sau:

1. **Chỉ bật mask cần dùng.** Theo dõi con trỏ có thể phát sinh rất nhiều sự kiện; nếu chỉ cần nhấn chuột, bỏ `MOUSE_MOTION_EVENT_MASK`.
2. **Không `consume()` theo thói quen.** Nếu chặn thao tác của nút là yêu cầu nghiệp vụ thực sự, hãy thiết kế rõ trạng thái khóa UI; đừng coi việc nghe sự kiện đồng nghĩa với chặn toàn bộ giao diện.
3. **Không xử lý nặng trên EDT.** Callback chỉ ghi nhận trạng thái, cập nhật hiển thị và lên lịch công việc. Nếu cần I/O hoặc tính toán nặng, dùng `SwingWorker` hoặc cơ chế bất đồng bộ thích hợp; chỉ cập nhật Swing từ EDT.
4. **Không ghi log dữ liệu nhạy cảm.** Nếu thêm `KEY_EVENT_MASK`, không log nguyên nội dung phím từ ô mật khẩu, mã xác thực hoặc biểu mẫu chứa dữ liệu riêng tư. Đo lường tương tác thường chỉ cần loại sự kiện, thành phần và số đếm tổng hợp.
5. **Tách trạng thái từng layer.** `LayerUI` có thể được dùng chung theo thiết kế, nhưng nếu lớp chứa các trường `presses`, `pointer`, `message` như ví dụ, hãy tạo một instance cho mỗi `JLayer` hoặc lưu trạng thái theo từng layer; không chia sẻ nhầm trạng thái giữa nhiều panel.
6. **Cẩn thận với glass pane tùy chỉnh.** `JLayer` có `glassPane` riêng; một glass pane có bật nhận sự kiện chuột có thể tác động hit-testing và tương tác của view. Ví dụ này chỉ vẽ bằng `LayerUI.paint` nên không phải thay glass pane.
7. **Giữ ý nghĩa của focus.** Đối với phím tắt, hãy dùng key bindings của Swing; để đo sự kiện phím phải xác định đúng focus owner. Layer mask không tự cấp focus cho `JLayer`.

## 6. Cách kiểm thử đúng cơ chế theo dõi sự kiện

Bộ kiểm thử nên tách **cấu hình lifecycle** và **tương tác GUI thực tế**, vì không thể chứng minh đường phân phối AWT chỉ bằng cách tạo đối tượng `JLayer` chưa displayable.

| Nhóm test | Thao tác | Kỳ vọng |
|---|---|---|
| Mask ban đầu | Tạo `JLayer` với `MonitorUI` | `getLayerEventMask()` bằng OR của hai mask chuột |
| Gỡ UI | Gọi `layer.setUI(null)` trong `--self-test` | Mask trở về `0` |
| Nhấn nền panel | Nhấn vào vùng trống trong panel đang hiện | Bộ đếm tăng một lần cho `MOUSE_PRESSED` |
| Nhấn nút con | Nhấn `Lưu` | Overlay vẫn ghi nhận; `ActionListener` của nút vẫn hoạt động |
| Di chuyển chuột | Di chuyển giữa nền panel và nút | Vòng tròn theo con trỏ trong hệ tọa độ layer |
| Sự kiện khác loại | Chỉ bật mask chuột/motion | Không kỳ vọng callback chuyên biệt cho wheel/key/focus được gọi từ mask đang dùng |
| Không displayable | Chỉ dựng đối tượng trong unit test headless | Kiểm tra được cấu hình nhưng **không** kết luận về dispatch thật |
| Nhiều layer | Hai `JLayer` với hai instance `MonitorUI` | Bộ đếm/overlay không chia sẻ trạng thái |
| Kiểm tra EDT | Trong callback GUI dùng `SwingUtilities.isEventDispatchThread()` khi cần chẩn đoán | Các cập nhật state/paint của ví dụ diễn ra theo Swing EDT |
| Nâng JDK | Biên dịch và chạy lại test trên JDK mục tiêu | Xác nhận không đổi hành vi mà ứng dụng phụ thuộc |

Muốn kiểm thử tự động tương tác con trỏ/nhấn chuột, chạy trên môi trường GUI thật với công cụ điều khiển UI thích hợp. `java.awt.Robot` là API sẵn có, nhưng hành vi thực tế phụ thuộc hệ điều hành, focus, timing, scaling và quyền truy cập desktop; không sử dụng nó như một test headless thông thường. Với logic có nhiều điều kiện, tách xử lý dữ liệu sự kiện thành hàm thuần có thể unit test riêng.

## 7. So sánh với những cách theo dõi khác

| Nhu cầu | Cơ chế phù hợp |
|---|---|
| Chỉ một nút cần bắt click để thực hiện lệnh | `ActionListener` trên nút |
| Một component cần tương tác chuột cụ thể | `MouseListener`/`MouseMotionListener` hoặc adapter tương ứng |
| Theo dõi sự kiện từ **cả một nhóm component** và vẽ overlay thống nhất | `JLayer` + `LayerUI` |
| Phím tắt trong cửa sổ/biểu mẫu | Swing key bindings (`InputMap`/`ActionMap`) |
| Hiển thị overlay che cả cửa sổ root | Glass pane của `JRootPane` khi phạm vi là toàn root pane |

Không nên dùng `JLayer` cho mọi sự kiện chỉ vì có thể làm được. Lợi thế của nó là phạm vi theo **cây thành phần đã bọc** cùng phần trang trí; sự kiện nghiệp vụ của nút vẫn nên đặt trong handler tương ứng.

## 8. Lỗi phổ biến và cách khắc phục

- **Không nhận event:** quên `setLayerEventMask`; layer chưa displayable; bật nhầm `MOUSE_EVENT_MASK` trong khi cần `MOUSE_MOTION_EVENT_MASK`.
- **Vẽ overlay lệch khỏi vị trí chuột:** dùng `e.getX()/getY()` trực tiếp từ nút con; cần `SwingUtilities.convertPoint(...)`.
- **View biến mất:** ghi đè `paint` nhưng không gọi `super.paint(g, c)`.
- **Đếm click nhiều lần:** đếm `PRESSED`, `RELEASED` và `CLICKED` như ba thao tác riêng; chọn một sự kiện đại diện theo nghiệp vụ.
- **Không có callback chuyên biệt:** đã override `eventDispatched` nhưng không gọi `super.eventDispatched(...)` và không tự phân phối.
- **Sự kiện dừng hoạt động sau thay UI:** mask chưa được thiết lập trong `installUI` mới; nếu quan sát thêm kiểu khác phải cấu hình lại mask.
- **Rò rỉ/hành vi khó đoán:** không dọn mask ở `uninstallUI`, giữ tham chiếu ngoài lifecycle, hoặc dùng chung `LayerUI` có trạng thái mutable.
- **UI giật khi rê chuột:** ghi log/đọc file/thực hiện tác vụ nặng cho mỗi `MOUSE_MOVED`; chỉ giữ trạng thái gần nhất, giới hạn tần suất hoặc repaint vùng cần thiết khi cần tối ưu.
- **Nhầm vùng theo dõi:** tưởng layer bắt mọi event trong toàn ứng dụng; thực tế chỉ phạm vi `JLayer` và các thành phần con tương ứng.
- **Nhầm xử lý focus/keyboard:** bật key mask nhưng focus đang ở thành phần ngoài layer hoặc thao tác cần key bindings thay vì bắt raw key.

## 9. Tự kiểm tra sau bài học

1. Vì sao dùng `JLayer` để quan sát một `JPanel` chứa nhiều nút thay vì gắn `MouseListener` cho từng nút? Khi nào gắn listener trực tiếp đơn giản hơn?
2. Nếu muốn quan sát **wheel** ngoài click và di chuyển, cần thêm mask nào, và ghi đè callback nào?
3. Vì sao `SwingUtilities.convertPoint` là bước cần thiết khi vẽ hiệu ứng theo con trỏ?
4. Nếu `eventDispatched` đã ghi đè, cần làm gì để `processMouseEvent` vẫn được gọi?
5. Vì sao unit test trong môi trường headless có thể chứng minh mask được đặt đúng mà không chứng minh event sẽ đến từ nút con?
6. Hệ quả của việc chia sẻ một `LayerUI` có bộ đếm mutable cho hai `JLayer` là gì? Bạn sẽ sửa thiết kế ra sao?
7. Bạn sẽ giảm chi phí khi có hàng trăm `MOUSE_MOVED` mỗi giây và giữ EDT phản hồi bằng cách nào?

**Tài liệu API chính thức (còn được hỗ trợ):** [JLayer — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/javax/swing/JLayer.html), [LayerUI — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/javax/swing/plaf/LayerUI.html), [SwingUtilities — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/javax/swing/SwingUtilities.html), [AWTEvent — Java SE 25](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/java/awt/AWTEvent.html).