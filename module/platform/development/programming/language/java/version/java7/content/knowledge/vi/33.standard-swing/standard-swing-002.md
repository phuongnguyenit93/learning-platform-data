# Vẽ lớp phủ lên một nhóm thành phần Swing bằng `JLayer` và `LayerUI`

Một giao diện Swing thường gồm nhiều thành phần nằm trong một vùng: `JPanel` chứa `JButton`, `JLabel`, `JTextField`, bảng, biểu mẫu hoặc các panel con. Có lúc ứng dụng cần **vẽ một hiệu ứng phủ chung lên toàn bộ vùng**: tô màu trạng thái, viền nhấn mạnh, làm mờ phần nội dung, hiển thị dấu cảnh báo hay chỉ báo đang xử lý. Nếu từng thành phần tự vẽ hiệu ứng riêng, mã dễ trùng lặp, hiệu ứng bị đứt ở khoảng trống giữa các thành phần và khó quản lý khi bố cục thay đổi.

Đối với ứng dụng Swing hiện nay, bộ đôi **`javax.swing.JLayer` + `javax.swing.plaf.LayerUI`** là API chuẩn để trang trí hình ảnh hoặc quan sát sự kiện trên **một cây thành phần** mà không phải sửa từng thành phần con. API được bổ sung từ Java 7 và tiếp tục có mặt trong `java.desktop` của các JDK hiện đại. Bài này tập trung vào **lớp phủ hiển thị**; quyền tương tác của các thành phần bên dưới cần được xử lý riêng khi thiết kế trạng thái khóa hoặc đang bận.

## 1. Cơ chế: bọc một nhóm, vẽ một lần

`JLayer<V>` nhận một thành phần `view` và một đối tượng `LayerUI`. Nếu muốn hiệu ứng phủ lên **nhiều thành phần cùng lúc**, hãy tập hợp chúng trong một container Swing, thường là `JPanel`, rồi đặt container đó làm `view` của `JLayer`.

```text
JFrame
└── panel bố cục chính
    ├── nút/chọn điều khiển lớp phủ (nằm ngoài vùng phủ)
    └── JLayer<JPanel>                  <- diện tích phủ
        └── view: JPanel
            ├── JButton A
            ├── JButton B
            ├── JLabel
            └── JPanel con (nếu có)

LayerUI<JPanel>.paint()
    1. Vẽ JLayer và toàn bộ cây con bằng super.paint(...)
    2. Vẽ màu bán trong suốt, viền, nhãn... lên bề mặt đã vẽ
```

Trong mô hình này:

1. **`JPanel` quản lý thành phần và layout** (`BorderLayout`, `GridLayout`, `GridBagLayout`...). Khi thêm/bớt các con trong `JPanel`, lớp phủ vẫn bao toàn bộ diện tích của view.
2. **`JLayer` là một wrapper** đặt vào giao diện ở vị trí trước đây định đặt `JPanel`. `JLayer` là lớp `final`; cách mở rộng chính là viết một `LayerUI`, không kế thừa `JLayer`.
3. **`LayerUI.paint(Graphics, JComponent)` chịu trách nhiệm trang trí.** Gọi `super.paint(g, c)` trước để giữ cách vẽ mặc định của các thành phần và mọi phần tử con, sau đó vẽ hiệu ứng của mình.
4. **`repaint()` yêu cầu Swing vẽ lại**, không thực hiện thao tác vẽ tức thì theo cách ứng dụng tự gọi `paint()`.
5. **Bản thân lớp phủ được vẽ không tự chặn sự kiện.** Nút và ô nhập phía dưới vẫn có thể được tương tác. Nếu cần ngăn thao tác, phải có cơ chế điều khiển tương tác riêng.

Ví dụ tạo wrapper tối thiểu:

```java
JPanel group = new JPanel();
group.add(new JButton("A"));
group.add(new JButton("B"));

LayerUI<JPanel> ui = new LayerUI<>();
JLayer<JPanel> decoratedGroup = new JLayer<>(group, ui);

// Đưa decoratedGroup vào container cha thay cho group.
```

Đoạn trên chỉ minh họa cách ghép các lớp; chưa có lớp phủ tùy biến. `LayerUI` mặc định chỉ vẽ view như bình thường.

## 2. Ví dụ hoàn chỉnh: bật/tắt lớp phủ cho cả nhóm

Chương trình dưới đây có hai nút nằm **bên trong** vùng được phủ và một checkbox **bên ngoài** vùng phủ. Khi tích checkbox, một mảng màu xanh bán trong suốt, viền bo góc và dòng chú thích được vẽ trên toàn bộ nhóm. Hai nút vẫn hoạt động; nhấn nút sẽ đổi nhãn trạng thái. Điều đó cho thấy **vẽ lớp phủ** và **khóa tương tác** là hai vấn đề khác nhau.

Lưu toàn bộ mã vào **`GroupOverlayDemo.java`**:

```java
import java.awt.BasicStroke;
import java.awt.BorderLayout;
import java.awt.Color;
import java.awt.Dimension;
import java.awt.Font;
import java.awt.Graphics;
import java.awt.Graphics2D;
import java.awt.GridLayout;
import java.beans.PropertyChangeEvent;

import javax.swing.BorderFactory;
import javax.swing.JButton;
import javax.swing.JCheckBox;
import javax.swing.JComponent;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JLayer;
import javax.swing.JPanel;
import javax.swing.SwingUtilities;
import javax.swing.plaf.LayerUI;

public final class GroupOverlayDemo {

    private static final class GroupHighlightUI extends LayerUI<JPanel> {
        private boolean active;

        void setActive(boolean value) {
            if (active == value) {
                return;
            }

            boolean previous = active;
            active = value;

            // Thông báo trạng thái giao diện đổi, để JLayer vẽ lại.
            firePropertyChange("active", previous, active);
        }

        @Override
        public void applyPropertyChange(
                PropertyChangeEvent event,
                JLayer<? extends JPanel> layer) {
            if ("active".equals(event.getPropertyName())) {
                layer.repaint();
            }
        }

        @Override
        public void paint(Graphics graphics, JComponent component) {
            // Vẽ panel và mọi thành phần con trước khi trang trí.
            super.paint(graphics, component);

            if (!active) {
                return;
            }

            // Sao chép Graphics để không làm thay đổi trạng thái
            // của ngữ cảnh vẽ mà Swing cấp cho các lớp khác.
            Graphics2D g2 = (Graphics2D) graphics.create();
            try {
                int w = component.getWidth();
                int h = component.getHeight();

                // Phủ một lớp màu bán trong suốt lên cả nhóm.
                g2.setColor(new Color(24, 95, 180, 38));
                g2.fillRect(0, 0, w, h);

                // Vẽ viền nhận diện vùng đang được đánh dấu.
                g2.setColor(new Color(24, 95, 180));
                g2.setStroke(new BasicStroke(3.0f));
                g2.drawRoundRect(
                        2, 2,
                        Math.max(0, w - 5),
                        Math.max(0, h - 5),
                        16, 16);

                g2.setFont(g2.getFont().deriveFont(Font.BOLD));
                g2.drawString("Nhóm đang được đánh dấu", 18, 27);
            } finally {
                g2.dispose();
            }
        }
    }

    private static void createAndShow() {
        JFrame frame = new JFrame("JLayer - Group Overlay");
        frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);

        // Bốn thành phần cùng thuộc một nhóm Swing.
        JPanel group = new JPanel(new GridLayout(2, 2, 10, 10));
        group.setBorder(
                BorderFactory.createEmptyBorder(50, 20, 22, 20));
        group.setPreferredSize(new Dimension(460, 175));

        JLabel status = new JLabel("Chưa chọn");
        JButton buttonA = new JButton("Thành phần A");
        JButton buttonB = new JButton("Thành phần B");

        buttonA.addActionListener(
                e -> status.setText("Bạn đã chọn A"));
        buttonB.addActionListener(
                e -> status.setText("Bạn đã chọn B"));

        group.add(buttonA);
        group.add(buttonB);
        group.add(new JLabel("Trạng thái:"));
        group.add(status);

        // Chỉ cần bọc panel chứa cả nhóm bằng một JLayer.
        GroupHighlightUI overlay = new GroupHighlightUI();
        JLayer<JPanel> decoratedGroup =
                new JLayer<>(group, overlay);

        JCheckBox show = new JCheckBox(
                "Bật lớp phủ trên cả nhóm");
        show.addActionListener(
                e -> overlay.setActive(show.isSelected()));

        JPanel root = new JPanel(new BorderLayout(8, 8));
        root.setBorder(
                BorderFactory.createEmptyBorder(12, 12, 12, 12));
        root.add(show, BorderLayout.NORTH);
        root.add(decoratedGroup, BorderLayout.CENTER);

        frame.setContentPane(root);
        frame.pack();
        frame.setLocationRelativeTo(null);
        frame.setVisible(true);
    }

    public static void main(String[] args) {
        // Khởi tạo và thay đổi giao diện Swing trên EDT.
        SwingUtilities.invokeLater(GroupOverlayDemo::createAndShow);
    }
}
```

Biên dịch và chạy với **Java 17+** (chương trình dùng Swing chuẩn trong JDK, không cần thư viện bên ngoài):

```bash
javac -encoding UTF-8 GroupOverlayDemo.java
java GroupOverlayDemo
```

**Kết quả quan sát trên giao diện** (chương trình không cố ý in stdout):

- Khi mới mở, checkbox chưa chọn, nhóm có hai nút và phần nhãn trạng thái; không thấy màu phủ hoặc viền xanh.
- Khi tích **Bật lớp phủ trên cả nhóm**, vùng chứa cả bốn thành phần có màu xanh rất nhạt, viền xanh và chữ **Nhóm đang được đánh dấu**.
- Khi bấm **Thành phần A/B**, nhãn trạng thái đổi thành **Bạn đã chọn A/B** ngay cả khi lớp phủ đang bật.
- Bỏ chọn checkbox sẽ loại bỏ hiệu ứng trong lần vẽ lại tiếp theo, giữ nguyên trạng thái và bố cục các thành phần con.

Ví dụ sử dụng một `GroupHighlightUI` cho đúng một `JLayer`. Nếu muốn nhiều nhóm bật/tắt độc lập, tạo các instance `GroupHighlightUI` riêng cho từng nhóm.

## 3. Vì sao mã hoạt động?

### 3.1. Thứ tự vẽ quyết định vị trí lớp phủ

Phần quan trọng nhất của `paint()` là:

```java
@Override
public void paint(Graphics g, JComponent c) {
    super.paint(g, c); // nội dung của JLayer, gồm view và các con

    Graphics2D g2 = (Graphics2D) g.create();
    try {
        g2.setColor(new Color(30, 110, 210, 45));
        g2.fillRect(0, 0, c.getWidth(), c.getHeight());
    } finally {
        g2.dispose();
    }
}
```

Đây là **đoạn phương thức minh họa**, được đặt trong lớp kế thừa `LayerUI` chứ không phải tệp Java độc lập. Khi `super.paint(...)` chạy trước, Swing vẽ thành phần được bọc và cây con theo quy trình chuẩn; các lệnh đồ họa tiếp theo phủ lên kết quả đó. Nếu quên gọi `super.paint(...)`, nội dung Swing bên dưới có thể không được vẽ đúng.

`Graphics2D.create()` tạo ngữ cảnh phụ để thay đổi màu, font, stroke, composite, clip hoặc transform mà không làm bẩn ngữ cảnh vẽ của Swing. Sau khi vẽ, luôn gọi `dispose()` cho ngữ cảnh phụ. Đối tượng `Graphics` do Swing cung cấp không do mã ứng dụng sở hữu, vì vậy không đóng đối tượng gốc.

Màu `new Color(red, green, blue, alpha)` có alpha từ **0 đến 255**: `0` trong suốt, `255` đục hoàn toàn. Trong ví dụ, alpha `38` tạo một lớp phủ nhẹ. Phủ quá đậm có thể che chữ hoặc trạng thái focus của nút bên dưới; cần thử trên giao diện thực.

### 3.2. Kích thước lớp phủ lấy từ wrapper

Tham số `component` trong `LayerUI.paint(Graphics, JComponent)` là `JLayer` đang được trang trí. `component.getWidth()` và `component.getHeight()` mô tả vùng của wrapper, không phải riêng kích thước của một nút. Nhờ đó, `fillRect(0, 0, width, height)` bao trùm cả khoảng đệm, khoảng trống giữa nút và các container con.

Tọa độ `(0, 0)` là góc trên bên trái của vùng đang vẽ. Với panel có layout co giãn, phương thức `paint()` được gọi lại khi cần vẽ; lớp phủ dùng kích thước hiện tại nên không cần tính tọa độ một lần rồi giữ cố định. Nếu chỉ muốn phủ một phần vùng, cần tính hình chữ nhật mục tiêu dựa trên kích thước thực tế hoặc dùng `SwingUtilities.convertRectangle(...)` để đổi hệ tọa độ của thành phần con.

### 3.3. Khi trạng thái đổi, yêu cầu vẽ lại

Trong ví dụ, checkbox đổi `active` trong `GroupHighlightUI`. `firePropertyChange("active", previous, active)` phát sự kiện thuộc tính; `JLayer` gắn với `LayerUI` nhận sự kiện và gọi `applyPropertyChange(...)`. Phương thức này yêu cầu `layer.repaint()`.

Điều này có ba lợi ích: tách logic thay đổi trạng thái khỏi logic vẽ; không phải gọi trực tiếp `paint()`; dễ tái sử dụng delegate khi cần. Với một đoạn mã nhỏ, cũng có thể giữ tham chiếu `JLayer` trong controller và gọi `layer.repaint()` khi cập nhật trạng thái. Không gọi `revalidate()` chỉ để cập nhật màu/viền; `revalidate()` phù hợp khi kích thước hoặc cấu trúc layout thay đổi.

Dù chọn cách nào, hãy thực hiện thay đổi trạng thái UI trên **Event Dispatch Thread (EDT)**. `ActionListener` của Swing thường đã chạy trên EDT; nếu cập nhật từ tác vụ nền, đưa phần cập nhật giao diện trở lại EDT bằng `SwingUtilities.invokeLater(...)` hoặc dùng `SwingWorker` để xử lý công việc dài.

## 4. Những vùng lớp phủ thường dùng

| Nhu cầu | Cách đặt `JLayer` |
| --- | --- |
| Tô viền và phủ màu một biểu mẫu có nhiều ô nhập | Bọc `JPanel` chứa toàn bộ trường nhập và nhãn |
| Đánh dấu một nhóm nút điều khiển | Bọc `JPanel` chứa nhóm nút |
| Hiển thị tình trạng đang xử lý cho riêng một tab | Bọc panel nội dung của tab cần phủ |
| Đánh dấu một vùng con trong dashboard Swing | Bọc đúng panel đại diện cho vùng đó |
| Thêm cảnh báo trực quan lên một `JScrollPane` | Bọc `JScrollPane` hoặc panel bao quanh, xác định rõ vùng cần trang trí |

Điểm lựa chọn quan trọng là **phạm vi của view**. Muốn phủ ba nhóm như một khối, có thể bọc panel cha chứa cả ba; muốn ba trạng thái riêng, bọc ba panel con bằng ba `JLayer` khác nhau. Một `JLayer` không phải lớp phủ tự động trên mọi cửa sổ Swing và không bao phủ cửa sổ/popup tách riêng khỏi cây Swing đang được bọc.

### Phân biệt ba cơ chế dễ nhầm

- **`JLayer` + `LayerUI`:** trang trí hoặc quan sát các sự kiện trong một *cây thành phần*; phù hợp để áp dụng một hiệu ứng chung cho nhóm mà không thay đổi logic layout của nhóm.
- **`JLayeredPane`:** container quản lý các thành phần ở những **tầng z-order** khác nhau; hữu ích khi thực sự cần xếp những đối tượng giao diện độc lập chồng lên nhau và tự bố trí vị trí của chúng.
- **Glass pane của `JRootPane`/`JFrame`:** một pane phía trên vùng nội dung của cửa sổ, phù hợp với những hiệu ứng/cơ chế tương tác có phạm vi gần như toàn cửa sổ. Phạm vi và cách nhận sự kiện khác với một `JLayer` bọc panel con.

Ngoài ra, `JLayer` có `getGlassPane()`/`setGlassPane(...)` riêng, dùng khi muốn cung cấp một thành phần phủ trong phạm vi của `JLayer`. Với hiệu ứng hình ảnh đơn giản, override `LayerUI.paint()` thường là cách trực tiếp và ít thành phần phụ hơn.

## 5. Sự kiện chuột, bàn phím và lớp phủ tương tác

Ví dụ chỉ vẽ hình: **không cần** cấu hình nhận sự kiện. Hai nút vẫn nhận click như bình thường. Nếu cần **quan sát** sự kiện từ cả nhóm, `JLayer` cho phép đặt `setLayerEventMask(...)` và xử lý `LayerUI.eventDispatched(AWTEvent, JLayer<? extends V>)`.

Ý tưởng triển khai khi thật sự cần bắt sự kiện chuột:

```java
// Đoạn tích hợp vào lớp LayerUI<JPanel>; cần import java.awt.AWTEvent.
@Override
public void installUI(JComponent c) {
    super.installUI(c);
    ((JLayer<?>) c).setLayerEventMask(AWTEvent.MOUSE_EVENT_MASK);
}

@Override
public void uninstallUI(JComponent c) {
    ((JLayer<?>) c).setLayerEventMask(0L);
    super.uninstallUI(c);
}
```

Khi cấu hình đúng và `JLayer` đang ở trạng thái displayable, `eventDispatched(...)` có thể nhận sự kiện thuộc loại đã đăng ký xảy ra trong vùng của layer và các con. Trong ứng dụng thực, bổ sung phương thức `eventDispatched(...)` theo loại sự kiện cần xử lý, đồng thời trả event mask về `0` khi gỡ UI để tránh giữ thiết lập không còn dùng.

**Không đồng nhất quan sát sự kiện với chặn thao tác:** đăng ký event mask không tự biến lớp phủ thành một khóa modal, cũng không phải cơ chế kiểm soát phân quyền. Nếu ứng dụng thực sự cần không cho người dùng tương tác trong lúc xử lý, hãy thiết kế chính sách riêng: bật/tắt trạng thái của control, dùng pane chặn sự kiện phù hợp, quản lý keyboard focus và thông báo trạng thái có thể truy cập. Đừng chỉ vẽ một màu xám rồi giả định nút bên dưới đã bị vô hiệu hóa.

## 6. Thực hành đúng với Swing hiện đại

### Giữ giao diện phản hồi nhanh

`paint()` có thể được gọi nhiều lần vì cửa sổ thay đổi kích thước, một control tự cập nhật hoặc hệ thống yêu cầu vẽ lại. Vì vậy:

- Chỉ thực hiện thao tác vẽ nhanh trong `paint()`; không gọi HTTP, truy vấn database, đọc file lớn hoặc đợi tác vụ nền tại đây.
- Không thay đổi cấu trúc layout, thêm/xóa control hoặc gọi `repaint()` liên tục bên trong `paint()`; dễ dẫn tới vòng lặp vẽ hoặc hiệu năng kém.
- Nếu cần animation, dùng `javax.swing.Timer` để cập nhật trạng thái và repaint theo nhịp phù hợp. Không dùng một vòng lặp ngủ chặn EDT.
- Với hiệu ứng hình ảnh nặng, cân nhắc cache tài nguyên có kích thước thích hợp và bỏ cache khi kích thước thay đổi. Tránh tạo ảnh lớn mới trong mỗi lần vẽ.
- Ưu tiên màu và viền vừa phải để người dùng vẫn đọc được text, nhận ra focus/selection và hiểu trạng thái của các nút.

### Tách trạng thái theo từng nhóm

Một instance `LayerUI` có thể được gắn với nhiều `JLayer`, nhưng các biến instance như `active` sẽ được **chia sẻ** giữa những layer đó. Nếu mỗi nhóm có trạng thái riêng, tạo mỗi nhóm một `LayerUI` riêng hoặc mô hình hóa trạng thái theo từng view. Không đặt trạng thái toàn cục chỉ vì cả ứng dụng cùng dùng kiểu phủ tương tự.

### Kiểm tra vùng vẽ và thứ tự đồ họa

- **Vẽ trước hay sau `super.paint(...)`:** để phủ lên các thành phần, thường vẽ **sau** `super.paint(...)`; vẽ trước có thể bị nội dung của view che lấp.
- **Đúng hệ tọa độ:** dùng kích thước wrapper hoặc chuyển tọa độ khi cần đánh dấu một thành phần bên trong. Không giả định nút luôn nằm ở tọa độ cố định.
- **Màu có alpha:** dùng `Color(..., alpha)` hoặc `AlphaComposite` đúng chủ đích; alpha quá cao che chữ, alpha quá thấp không truyền đạt trạng thái.
- **Dọn tài nguyên vẽ:** `dispose()` cho bản sao `Graphics2D`; không dispose bản `Graphics` Swing truyền vào.
- **Đúng phạm vi:** bọc panel cha khi muốn phủ nhiều con, thay vì đưa từng control trực tiếp vào `JLayer` (wrapper có một `view` chính).
- **Khi đổi cấu trúc giao diện:** Swing layout cần `revalidate()`, còn đổi trạng thái hiển thị chỉ cần `repaint()`.
- **Accessibility:** dùng nhãn/trạng thái UI thật và thông báo có thể hiểu bằng công nghệ hỗ trợ; màu hoặc hình phủ đơn lẻ không đủ làm tín hiệu duy nhất.

## 7. Lỗi phổ biến và cách khắc phục

| Hiện tượng | Nguyên nhân thường gặp | Hướng khắc phục |
| --- | --- | --- |
| Bật lớp phủ nhưng không nhìn thấy gì | Chưa gọi repaint, alpha quá thấp, hoặc phương thức `paint()` không vẽ lớp phủ | Yêu cầu repaint khi trạng thái đổi; kiểm tra alpha và phương thức override |
| Chỉ nút A có viền, các nút còn lại không có | `JLayer` đang bọc riêng nút A | Đưa các nút vào cùng một `JPanel`, bọc panel đó |
| Cả nhóm trắng trơn sau khi áp dụng `LayerUI` | Override `paint()` nhưng quên gọi `super.paint(...)` | Gọi `super.paint(g, c)` trước khi vẽ phần phủ |
| Đổi kích thước cửa sổ làm lệch hình phủ | Dùng tọa độ/kích thước tính cứng từ lần đầu | Dùng `c.getWidth()`, `c.getHeight()` hoặc đổi hệ tọa độ khi vẽ |
| Nút vẫn bấm được khi đang phủ màu xám | Chỉ vẽ trang trí, không có chính sách chặn tương tác | Điều khiển trạng thái nút/keyboard hoặc dùng pane tương tác phù hợp |
| Hiệu ứng của nhóm A cũng xuất hiện ở nhóm B | Hai nhóm dùng cùng instance `LayerUI` có trạng thái mutable | Dùng instance UI độc lập cho từng nhóm |
| Giao diện giật/đơ khi bật animation | Làm việc nặng trong `paint()` hoặc chặn EDT | Chuyển việc nặng ra nền, dùng Swing Timer và repaint nhẹ |
| Không thấy lớp phủ trên popup/cửa sổ khác | `JLayer` chỉ trang trí cây thành phần được bọc | Chọn lớp phủ ở đúng container/cửa sổ cần hiển thị |

## 8. Checklist kiểm thử bài thực hành

Sau khi chạy `GroupOverlayDemo.java`, tự kiểm tra:

1. **Phạm vi:** bật checkbox phải phủ toàn bộ `JPanel` chứa hai nút và hai nhãn, gồm cả các khoảng trống do layout tạo ra.
2. **Bật/tắt:** đổi checkbox qua lại nhiều lần; lớp phủ xuất hiện/biến mất, không để lại vệt màu cũ.
3. **Tương tác:** khi lớp phủ đang bật, bấm từng nút; nhãn trạng thái vẫn cập nhật chính xác.
4. **Resize:** thay kích thước cửa sổ; viền và mảng màu vẫn nằm theo kích thước thực tế của vùng được bọc.
5. **EDT:** khởi tạo giao diện qua `SwingUtilities.invokeLater(...)` và chỉ cập nhật Swing từ EDT.
6. **Chính sách UX:** nếu chuyển sang trạng thái "đang xử lý", quyết định rõ người dùng có được click hay không; thực hiện bằng cơ chế sự kiện/trạng thái riêng thay vì suy ra từ màu phủ.
7. **Hiệu năng:** khi bổ sung hiệu ứng chuyển động hoặc nhiều layer, đo tốc độ phản hồi và chỉ repaint khi trạng thái cần thay đổi.

## Kết luận

Để **vẽ một lớp phủ chung lên một nhóm thành phần Swing**, hãy gom các control vào `JPanel`, tạo `JLayer<JPanel>` bọc panel đó và đặt logic vẽ trong `LayerUI<JPanel>.paint()`. Luôn vẽ nội dung gốc bằng `super.paint(...)`, sau đó vẽ phần trang trí bằng bản sao `Graphics2D`; cập nhật trạng thái rồi yêu cầu repaint trên EDT. Đây là API Java chuẩn còn được hỗ trợ trong các JDK hiện đại. Khi cần chặn tương tác hoặc phủ nhiều cửa sổ, bổ sung cơ chế tương tác và chọn phạm vi phủ phù hợp với ứng dụng.

## Tài liệu tham khảo chính thức

- [JLayer — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/javax/swing/JLayer.html): lớp wrapper cho vùng Swing, `getView()`, `setLayerEventMask()`, `getGlassPane()`.
- [LayerUI — Java SE API](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/javax/swing/plaf/LayerUI.html): `paint()`, `applyPropertyChange()`, `installUI()`, `uninstallUI()` và sự kiện.
- [SwingUtilities — Java SE API](https://docs.oracle.com/en/java/javase/25/docs/api/java.desktop/javax/swing/SwingUtilities.html): `invokeLater()` để khởi tạo/cập nhật UI đúng EDT.
- [How to Decorate Components with JLayer — Oracle Java Tutorials](https://docs.oracle.com/javase/tutorial/uiswing/misc/jlayer.html): tài liệu cơ chế `JLayer`/`LayerUI`; phần khái niệm vẫn phù hợp nhưng ví dụ hướng dẫn gắn JDK 8, nên ưu tiên API docs hiện hành khi cần tra cứu.
