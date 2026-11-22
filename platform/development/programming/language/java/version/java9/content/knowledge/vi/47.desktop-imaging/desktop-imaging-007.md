# Taskbar: biểu tượng, tiến trình và yêu cầu chú ý trong Java 9+

Từ Java 9, lớp **`java.awt.Taskbar`** trong module `java.desktop` cho phép ứng dụng desktop Java tương tác với vùng tác vụ của hệ điều hành: **taskbar** trên Windows, **Dock** trên macOS hoặc cơ chế tương đương trên một số môi trường Linux. Ứng dụng có thể cập nhật biểu tượng, gắn badge, hiển thị tiến độ và yêu cầu người dùng chú ý mà không dùng API riêng của hệ điều hành.

Bài này trình bày API còn phù hợp trong các JDK hiện đại, cách kiểm tra tính năng trước khi gọi, ví dụ Swing chạy với Java 17+, xử lý môi trường headless và kiểm thử đa nền tảng. Phần hiển thị taskbar là **tính năng bổ sung**: quy trình chính của ứng dụng phải hoạt động ngay cả khi hệ điều hành không hỗ trợ.

## 1. Kết quả học tập và phạm vi

Sau bài học, bạn có thể:

1. Phân biệt `Taskbar` với `JFrame`/`Window` và với vùng system tray.
2. Kiểm tra `GraphicsEnvironment.isHeadless()`, `Taskbar.isTaskbarSupported()` và từng `Taskbar.Feature`.
3. Đặt icon ứng dụng hoặc badge, đồng thời hiểu khác biệt giữa icon của cửa sổ và icon của ứng dụng.
4. Thể hiện tiến độ **0–100%**, trạng thái chưa xác định, tạm dừng hoặc lỗi khi nền tảng hỗ trợ.
5. Yêu cầu chú ý tới **ứng dụng** hoặc **một cửa sổ** mà không ép giành focus hay gây nháy liên tục.
6. Tạo fallback trong giao diện, dọn trạng thái khi hoàn thành, và kiểm thử hành vi trên nhiều OS.

API `Taskbar` được bổ sung ở Java 9 nhưng **không có nghĩa mọi tính năng sẽ hoạt động trên mọi hệ điều hành**. Hệ thống có thể có taskbar nhưng không hỗ trợ badge, tiến trình, hay attention theo kiểu Java cung cấp.

## 2. Taskbar có những thành phần gì?

```text
Ứng dụng Java (AWT / Swing)
        │
        ├── JFrame / Window:
        │      tiêu đề, nội dung, icon của cửa sổ
        │
        └── java.awt.Taskbar:
               icon ứng dụng ──► ảnh hoặc badge
               progress     ──► 0..100 hoặc trạng thái cửa sổ
               attention    ──► nhấp nháy/bật nhảy tùy nền tảng
                               ▼
                    Windows taskbar / macOS Dock /
                    vùng tác vụ hỗ trợ tương đương
```

`Taskbar` là **API hướng đến tích hợp với vỏ desktop của hệ điều hành**. Nó không tự tạo thanh taskbar, không có đảm bảo vị trí hiển thị, không phải thành phần Swing vẽ trong `JFrame`, và không phải `SystemTray`. `SystemTray`/`TrayIcon` phù hợp với icon thường trú trong khay hệ thống khi nền tảng có khay; `Taskbar` hướng tới biểu diễn ứng dụng hoặc cửa sổ trong vùng tác vụ.

Ví dụ thực tế:

- Trình tải tệp: hiển thị phần trăm hoàn thành trên biểu tượng ứng dụng/cửa sổ.
- Trình xử lý dữ liệu: đánh dấu tiến trình tạm dừng hoặc lỗi (nếu hỗ trợ trạng thái cửa sổ).
- Ứng dụng chat: badge số lượng thông báo chưa đọc; thông báo mới có thể yêu cầu chú ý.
- Trình chỉnh sửa ảnh: biểu tượng ứng dụng và tiến độ xuất ảnh.

**Ưu tiên UX:** tiến độ, lỗi và thông báo vẫn phải có trong chính cửa sổ ứng dụng; taskbar chỉ giúp người dùng biết tình trạng khi chuyển sang cửa sổ khác.

## 3. Ba tầng kiểm tra hỗ trợ bắt buộc

Thứ tự an toàn:

```java
if (GraphicsEnvironment.isHeadless()) {
    // Không có màn hình/thiết bị hiển thị GUI thích hợp.
} else if (!Taskbar.isTaskbarSupported()) {
    // Nền tảng hiện tại không cung cấp Taskbar.
} else {
    Taskbar taskbar = Taskbar.getTaskbar();
    if (taskbar.isSupported(Taskbar.Feature.PROGRESS_VALUE)) {
        taskbar.setProgressValue(40);
    }
}
```

Đây là **đoạn minh họa trong một phương thức**, cần import `java.awt.GraphicsEnvironment`, `java.awt.Taskbar`; ví dụ độc lập đầy đủ nằm ở phần 8.

Có ba câu hỏi tách biệt:

| Kiểm tra | Câu hỏi được trả lời | Nếu không đạt |
| --- | --- | --- |
| `GraphicsEnvironment.isHeadless()` | Tiến trình có đang chạy trong môi trường không có GUI? | Không tạo cửa sổ/không gọi taskbar |
| `Taskbar.isTaskbarSupported()` | Nền tảng có API taskbar ở mức lớp? | Dùng giao diện Swing hoặc log phù hợp |
| `taskbar.isSupported(Taskbar.Feature.X)` | **Tính năng cụ thể** có hỗ trợ không? | Bỏ qua thao tác native của tính năng đó |

`Taskbar.getTaskbar()` có thể phát sinh `HeadlessException` hoặc `UnsupportedOperationException` nếu môi trường không phù hợp. Kiểm tra trước khi gọi, và khi API native vẫn báo không hỗ trợ thì degrade gracefully. `Taskbar.isTaskbarSupported() == true` **không chứng minh** mọi `Feature` đều đúng.

Trên CI, container, tiến trình server và một số phiên remote desktop, chế độ headless rất phổ biến. Chương trình GUI cần tránh tạo `JFrame` ở các môi trường này. Để kiểm tra phần logic không phụ thuộc GUI, hãy dùng self-test hoặc unit test mà không mở cửa sổ.

## 4. Bảng `Taskbar.Feature`: chọn đúng tính năng

| Feature | API liên quan | Phạm vi |
| --- | --- | --- |
| `ICON_IMAGE` | `setIconImage(Image)` | Icon **ứng dụng** |
| `ICON_BADGE_TEXT` | `setIconBadge(String)` | Badge dạng văn bản |
| `ICON_BADGE_NUMBER` | `setIconBadge(String)` | Badge dạng số |
| `ICON_BADGE_IMAGE_WINDOW` | `setWindowIconBadge(Window, Image)` | Badge hình ảnh của một cửa sổ |
| `PROGRESS_VALUE` | `setProgressValue(int)` | Tiến độ **ứng dụng** |
| `PROGRESS_VALUE_WINDOW` | `setWindowProgressValue(Window, int)` | Tiến độ của một cửa sổ |
| `PROGRESS_STATE_WINDOW` | `setWindowProgressState(Window, State)` | Trạng thái tiến trình của cửa sổ |
| `USER_ATTENTION` | `requestUserAttention(boolean, boolean)` | Yêu cầu chú ý cho ứng dụng |
| `USER_ATTENTION_WINDOW` | `requestWindowUserAttention(Window)` | Yêu cầu chú ý cho cửa sổ |
| `MENU` | `setMenu(PopupMenu)`, `getMenu()` | Menu ngữ cảnh của icon ứng dụng |

Không có tính năng cấp ứng dụng tên `PROGRESS_STATE` trong `Taskbar.Feature`: trạng thái `NORMAL`, `PAUSED`, `ERROR`, `INDETERMINATE`, `OFF` áp dụng qua **`PROGRESS_STATE_WINDOW`**. Nếu muốn có phần trăm trên icon ứng dụng, dùng `PROGRESS_VALUE`. Nếu muốn trạng thái như “đang tạm dừng” cho một cửa sổ, cần `PROGRESS_STATE_WINDOW`.

**Cấp ứng dụng và cấp cửa sổ:** một ứng dụng có thể mở nhiều `JFrame`. Nền tảng có thể gom chúng thành một icon, nên kết quả taskbar khi nhiều cửa sổ phát tiến trình đồng thời có thể phụ thuộc OS. Chọn một nguồn trạng thái chính và hiển thị nhất quán thay vì để các cửa sổ cạnh tranh.

## 5. Biểu tượng ứng dụng và badge

### 5.1 Icon của `JFrame` so với icon của Taskbar

```java
BufferedImage icon = new BufferedImage(64, 64, BufferedImage.TYPE_INT_ARGB);
// Vẽ vào icon bằng Graphics2D hoặc nạp ảnh từ tài nguyên ứng dụng.
frame.setIconImage(icon); // Icon cửa sổ
if (taskbar.isSupported(Taskbar.Feature.ICON_IMAGE)) {
    taskbar.setIconImage(icon); // Icon ứng dụng ở vùng taskbar/Dock
}
```

Đây là đoạn minh họa cần biến `frame`, `taskbar` đã khởi tạo. `JFrame.setIconImage` chỉ đặt ảnh liên quan tới **cửa sổ**; không đảm bảo đổi icon Dock/application ở mọi OS. `Taskbar.setIconImage` nhắm vào **ứng dụng**, và có thể không được hỗ trợ ở nơi icon cố định bởi launcher/package.

Khi dùng hình ảnh thực tế:

- Ưu tiên PNG trong tài nguyên ứng dụng, có độ phân giải tốt và alpha trong suốt; cung cấp đúng kích thước hoặc để UI toolkit hỗ trợ scale.
- Kiểm tra kết quả trên màn hình có mật độ điểm ảnh khác nhau; biểu tượng 16×16 bị phóng lớn dễ vỡ.
- Giữ icon nhất quán với launcher/installer của ứng dụng. Tùy hệ điều hành, icon hiển thị có thể do gói cài đặt hoặc tập tin launcher quyết định.
- Không dùng `getResource(...)` mà không kiểm tra giá trị trả về khi cần nạp asset; path sai có thể gây lỗi trước khi bạn gọi Taskbar.

### 5.2 Badge số hoặc chữ

```java
if (taskbar.isSupported(Taskbar.Feature.ICON_BADGE_TEXT)) {
    taskbar.setIconBadge("NEW");
} else if (taskbar.isSupported(Taskbar.Feature.ICON_BADGE_NUMBER)) {
    taskbar.setIconBadge("3");
}

// Khi người dùng đã xử lý thông báo:
if (taskbar.isSupported(Taskbar.Feature.ICON_BADGE_TEXT)
        || taskbar.isSupported(Taskbar.Feature.ICON_BADGE_NUMBER)) {
    taskbar.setIconBadge(null);
}
```

Đây là mã minh họa trong phương thức. `setIconBadge(null)` **ẩn badge** theo tài liệu API. Một số nền tảng chỉ nhận badge số dạng chuỗi; nếu chỉ `ICON_BADGE_NUMBER` được hỗ trợ thì truyền `"3"`, không truyền `"NEW"` rồi mong nền tảng tự hiểu. Cả số và chữ có thể bị giới hạn kích thước/vị trí/kiểu vẽ; không dùng badge làm nguồn duy nhất để báo trạng thái.

Badge hình ảnh cho cửa sổ là tính năng khác: `ICON_BADGE_IMAGE_WINDOW` cùng `setWindowIconBadge(window, image)`. Tránh nhầm badge này với `setIconImage(...)` thay ảnh nền của icon ứng dụng.

## 6. Tiến độ phần trăm: quy đổi và hiển thị

`setProgressValue(int)` và `setWindowProgressValue(Window, int)` nhận số **0–100** biểu diễn phần trăm. Giá trị **ngoài khoảng này sẽ tắt chỉ báo tiến độ** theo tài liệu API; không dùng `-1` để biểu thị “đang chạy chưa biết còn bao lâu” nếu mục tiêu là indeterminate progress. Indeterminate thuộc `Taskbar.State.INDETERMINATE` ở **cấp cửa sổ** và chỉ có tác dụng khi `PROGRESS_STATE_WINDOW` hỗ trợ.

Để chuyển tiến độ nghiệp vụ sang UI:

```java
static int percent(long finished, long total) {
    if (total <= 0) return -1;             // Chưa biết tổng
    if (finished <= 0) return 0;
    if (finished >= total) return 100;
    return (int) Math.round(100.0 * finished / total);
}
```

Đây là phương thức minh họa; chương trình hoàn chỉnh cũng dùng công thức này và có self-test. Ví dụ `finished=1`, `total=8` trả **13%** sau làm tròn; `finished=8`, `total=8` trả **100%**. Chỉ dùng tổng nếu biết rõ số lượng công việc tương ứng. Nếu có nhiều pha khác trọng số, phải tính tiến độ tổng theo trọng số thực của từng pha, không cộng phần trăm tùy tiện.

| Tình huống | UI trong cửa sổ | Taskbar nếu hỗ trợ |
| --- | --- | --- |
| Biết tổng, đã làm xong 25% | `JProgressBar` 25% | `PROGRESS_VALUE_WINDOW` hoặc `PROGRESS_VALUE` → 25 |
| Chưa biết tổng | Spinner hoặc `JProgressBar` indeterminate | `PROGRESS_STATE_WINDOW` → `INDETERMINATE` |
| Tạm dừng | Văn bản “Đã tạm dừng” | `PROGRESS_STATE_WINDOW` → `PAUSED` |
| Lỗi | Thông báo lỗi và cách xử lý | `PROGRESS_STATE_WINDOW` → `ERROR` |
| Hoàn tất/huỷ | Hiển thị kết quả cuối cùng | Xóa tiến độ bằng giá trị ngoài 0–100 hoặc `State.OFF` |

Nếu nền tảng hỗ trợ tiến độ **cửa sổ**, cách làm thường là đặt `Taskbar.State.NORMAL` (khi tính năng trạng thái có) rồi đặt phần trăm bằng `setWindowProgressValue`. Nếu chỉ hỗ trợ `PROGRESS_VALUE`, hiển thị tiến độ **ứng dụng**. Chỉ số 100% nên được giữ đủ lâu để người dùng nhận ra hoàn tất, nhưng sau khi đã xác nhận kết quả cần dọn trạng thái native để tránh icon mãi ở 100%.

## 7. Trạng thái cửa sổ và yêu cầu chú ý

Các hằng `Taskbar.State`:

| State | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| `OFF` | Dừng/ẩn hiển thị tiến trình | Công việc hoàn thành hoặc bị hủy |
| `NORMAL` | Tiến độ xác định, thông thường | Đang tải 40% |
| `INDETERMINATE` | Đang làm việc, chưa biết bao nhiêu phần trăm | Đang liên hệ dịch vụ chưa có tổng |
| `PAUSED` | Tiến trình tạm dừng | Người dùng nhấn Pause |
| `ERROR` | Có lỗi liên quan đến công việc | Đồng bộ thất bại |

Để hiển thị trạng thái cửa sổ:

```java
if (taskbar.isSupported(Taskbar.Feature.PROGRESS_STATE_WINDOW)) {
    taskbar.setWindowProgressState(frame, Taskbar.State.INDETERMINATE);
}
// Khi đã biết tiến độ, chuyển về NORMAL và cập nhật giá trị.
if (taskbar.isSupported(Taskbar.Feature.PROGRESS_STATE_WINDOW)) {
    taskbar.setWindowProgressState(frame, Taskbar.State.NORMAL);
}
if (taskbar.isSupported(Taskbar.Feature.PROGRESS_VALUE_WINDOW)) {
    taskbar.setWindowProgressValue(frame, 65);
}
```

Đây là đoạn minh họa; hai feature phải được kiểm tra **độc lập**. Chuyển từ `INDETERMINATE` sang trạng thái xác định có thể làm reset giá trị đã đặt; hãy cập nhật phần trăm **sau** khi đổi trạng thái. Tác dụng với cửa sổ phụ thuộc việc `Window` đó có biểu diễn được trên taskbar không; cửa sổ phải đang hiển thị và nền tảng phải chấp nhận.

### Yêu cầu chú ý

```java
if (taskbar.isSupported(Taskbar.Feature.USER_ATTENTION_WINDOW)) {
    taskbar.requestWindowUserAttention(frame);
} else if (taskbar.isSupported(Taskbar.Feature.USER_ATTENTION)) {
    taskbar.requestUserAttention(true, false);
}
```

Đây là cách **yêu cầu** OS làm nổi bật ứng dụng/cửa sổ. Hệ điều hành có thể nhấp nháy icon, làm icon bật nhảy hoặc không hiện gì nếu ứng dụng đang active, hệ thống hạn chế thông báo hoặc người dùng tắt hiệu ứng. `critical=true` là yêu cầu quan trọng ở cấp ứng dụng; không đồng nghĩa bảo đảm luôn giành focus.

`requestUserAttention(enabled, critical)` có hai cờ:

- `enabled=true`: bắt đầu yêu cầu chú ý.
- `enabled=false`: yêu cầu bỏ trạng thái chú ý trên những nền tảng hỗ trợ việc hủy.
- `critical=true`: thông báo mức quan trọng; nên giới hạn cho sự cố thật sự có hậu quả, không dùng cho tiến độ thường ngày.

Một số OS xóa hiệu ứng khi người dùng mở ứng dụng; ở nơi khác cần gọi lại với `enabled=false`. Hiệu ứng attention **không phải modal dialog** và không có bảo đảm được người dùng nhìn thấy. Khi người dùng xem xong vấn đề, cập nhật badge và trạng thái trong cửa sổ theo luồng sản phẩm.

Tránh tự gọi `frame.toFront()` hoặc `frame.requestFocus()` lặp lại để thu hút chú ý: hành vi ấy có thể cướp focus, gây khó chịu hoặc bị OS từ chối. Chỉ dùng attention khi có sự kiện quan trọng (tin nhắn mới, lỗi đồng bộ, yêu cầu người dùng quyết định), có giới hạn tần suất và có cách nhận biết sự kiện đã xử lý.

## 8. Ví dụ Swing hoàn chỉnh: icon, phần trăm, badge, attention

Ví dụ sau tạo một cửa sổ **TaskbarDemo**. Nút bấm thử hiển thị tiến độ, thêm/xóa badge và yêu cầu chú ý; mỗi hiệu ứng native có kiểm tra `Taskbar.Feature`. Nếu không hỗ trợ, người dùng vẫn thấy trạng thái trong cửa sổ.

Ví dụ tạo icon trong bộ nhớ để không cần file ảnh bên ngoài. Khi chạy trên CI có `headless`, chương trình in thông báo SKIP thay vì tạo GUI. Khi chạy với `--self-test`, chương trình kiểm tra hàm tính phần trăm mà không cần desktop.

Tạo file **`TaskbarDemo.java`**, lưu mã UTF-8:

```java
import java.awt.BorderLayout;
import java.awt.Color;
import java.awt.FlowLayout;
import java.awt.Font;
import java.awt.Graphics2D;
import java.awt.GraphicsEnvironment;
import java.awt.Taskbar;
import java.awt.image.BufferedImage;
import javax.swing.JButton;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JPanel;
import javax.swing.JProgressBar;
import javax.swing.SwingUtilities;

public final class TaskbarDemo {
    private final JFrame frame = new JFrame("Taskbar Java 9+");
    private final JProgressBar progress = new JProgressBar(0, 100);
    private final JLabel status = new JLabel("Sẵn sàng");
    private final Taskbar taskbar;
    private int currentPercent;

    private TaskbarDemo(Taskbar taskbar) {
        this.taskbar = taskbar;
    }

    static int percent(long finished, long total) {
        if (total <= 0) return -1;
        if (finished <= 0) return 0;
        if (finished >= total) return 100;
        return (int) Math.round(100.0 * finished / total);
    }

    private boolean supports(Taskbar.Feature feature) {
        return taskbar != null && taskbar.isSupported(feature);
    }

    private static BufferedImage makeIcon() {
        BufferedImage image = new BufferedImage(
                64, 64, BufferedImage.TYPE_INT_ARGB);
        Graphics2D g = image.createGraphics();
        try {
            g.setColor(new Color(0x21609C));
            g.fillRoundRect(0, 0, 64, 64, 16, 16);
            g.setColor(Color.WHITE);
            g.setFont(new Font(Font.SANS_SERIF, Font.BOLD, 38));
            g.drawString("J", 21, 45);
        } finally {
            g.dispose();
        }
        return image;
    }

    private void addButton(JPanel panel, String text, Runnable action) {
        JButton button = new JButton(text);
        button.addActionListener(event -> action.run());
        panel.add(button);
    }

    private void show() {
        frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
        frame.setLayout(new BorderLayout(12, 12));

        BufferedImage icon = makeIcon();
        frame.setIconImage(icon);

        progress.setStringPainted(true);
        progress.setValue(0);
        progress.setString("0%");
        frame.add(progress, BorderLayout.NORTH);

        JPanel actions = new JPanel(new FlowLayout());
        addButton(actions, "+20%", () ->
                showProgress(Math.min(100, currentPercent + 20)));
        addButton(actions, "Ẩn tiến độ", this::clearProgress);
        addButton(actions, "Badge 3", () -> setBadge("3"));
        addButton(actions, "Xóa badge", () -> setBadge(null));
        addButton(actions, "Yêu cầu chú ý", this::requestAttention);

        frame.add(actions, BorderLayout.CENTER);
        frame.add(status, BorderLayout.SOUTH);
        frame.pack();
        frame.setLocationRelativeTo(null);
        frame.setVisible(true);

        if (supports(Taskbar.Feature.ICON_IMAGE)) {
            try {
                taskbar.setIconImage(icon);
            } catch (UnsupportedOperationException | SecurityException ex) {
                status.setText("Không thể đặt icon Taskbar: " + ex.getClass().getSimpleName());
            }
        }
    }

    private void showProgress(int value) {
        currentPercent = Math.max(0, Math.min(100, value));
        progress.setValue(currentPercent);
        progress.setString(currentPercent + "%");

        try {
            if (supports(Taskbar.Feature.PROGRESS_VALUE_WINDOW)) {
                if (supports(Taskbar.Feature.PROGRESS_STATE_WINDOW)) {
                    taskbar.setWindowProgressState(frame, Taskbar.State.NORMAL);
                }
                taskbar.setWindowProgressValue(frame, currentPercent);
                status.setText("Tiến độ cửa sổ: " + currentPercent + "%");
            } else if (supports(Taskbar.Feature.PROGRESS_VALUE)) {
                taskbar.setProgressValue(currentPercent);
                status.setText("Tiến độ ứng dụng: " + currentPercent + "%");
            } else {
                status.setText("Taskbar không hỗ trợ phần trăm; xem thanh tiến độ trong cửa sổ");
            }
        } catch (UnsupportedOperationException | SecurityException ex) {
            status.setText("Chỉ dùng progress trong cửa sổ: "
                    + ex.getClass().getSimpleName());
        }
    }

    private void clearProgress() {
        currentPercent = 0;
        progress.setValue(0);
        progress.setString("Đã ẩn tiến độ");

        try {
            if (supports(Taskbar.Feature.PROGRESS_VALUE_WINDOW)) {
                taskbar.setWindowProgressValue(frame, -1);
            }
            if (supports(Taskbar.Feature.PROGRESS_STATE_WINDOW)) {
                taskbar.setWindowProgressState(frame, Taskbar.State.OFF);
            }
            if (supports(Taskbar.Feature.PROGRESS_VALUE)) {
                taskbar.setProgressValue(-1);
            }
            status.setText("Đã dọn tiến độ");
        } catch (UnsupportedOperationException | SecurityException ex) {
            status.setText("Không thể dọn tiến độ Taskbar: "
                    + ex.getClass().getSimpleName());
        }
    }

    private void setBadge(String badge) {
        try {
            if (supports(Taskbar.Feature.ICON_BADGE_TEXT)
                    || supports(Taskbar.Feature.ICON_BADGE_NUMBER)) {
                taskbar.setIconBadge(badge);
                status.setText(badge == null
                        ? "Đã xóa badge" : "Badge: " + badge);
            } else {
                status.setText("Badge không hỗ trợ; trạng thái vẫn có trong ứng dụng");
            }
        } catch (UnsupportedOperationException | SecurityException ex) {
            status.setText("Không thể cập nhật badge: "
                    + ex.getClass().getSimpleName());
        }
    }

    private void requestAttention() {
        try {
            if (supports(Taskbar.Feature.USER_ATTENTION_WINDOW)) {
                taskbar.requestWindowUserAttention(frame);
                status.setText("Đã gửi yêu cầu chú ý cho cửa sổ");
            } else if (supports(Taskbar.Feature.USER_ATTENTION)) {
                taskbar.requestUserAttention(true, false);
                status.setText("Đã gửi yêu cầu chú ý cho ứng dụng");
            } else {
                status.setText("Không hỗ trợ attention; nội dung vẫn hiển thị");
            }
        } catch (UnsupportedOperationException | SecurityException ex) {
            status.setText("Không thể yêu cầu attention: "
                    + ex.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        if (args.length == 1 && "--self-test".equals(args[0])) {
            if (percent(0, 8) != 0 || percent(1, 8) != 13
                    || percent(8, 8) != 100 || percent(3, 0) != -1) {
                throw new AssertionError("Incorrect progress calculation");
            }
            System.out.println("PASS: progress calculation");
            return;
        }

        if (GraphicsEnvironment.isHeadless()) {
            System.out.println("SKIP: headless Taskbar demo");
            return;
        }

        SwingUtilities.invokeLater(() -> {
            Taskbar nativeTaskbar = null;
            if (Taskbar.isTaskbarSupported()) {
                try {
                    nativeTaskbar = Taskbar.getTaskbar();
                } catch (UnsupportedOperationException | SecurityException ex) {
                    System.err.println("Taskbar unavailable: "
                            + ex.getClass().getSimpleName());
                }
            }
            new TaskbarDemo(nativeTaskbar).show();
        });
    }
}
```

Biên dịch bằng JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 TaskbarDemo.java
```

Kiểm tra logic không dùng GUI:

```bash
java TaskbarDemo --self-test
```

Stdout:

```text
PASS: progress calculation
```

Kiểm tra headless rõ ràng:

```bash
java -Djava.awt.headless=true TaskbarDemo
```

Stdout:

```text
SKIP: headless Taskbar demo
```

Trên máy có desktop thực, chạy:

```bash
java TaskbarDemo
```

Một cửa sổ Swing xuất hiện. Nhấn `+20%` vài lần để nâng tiến độ; dùng `Ẩn tiến độ` để dọn chỉ báo; dùng `Badge 3`, `Xóa badge`; chuyển sang ứng dụng khác rồi thử `Yêu cầu chú ý` nếu OS có hiệu ứng. Dòng trạng thái ở **trong cửa sổ** luôn cung cấp fallback khi thiếu tính năng native. **Không có stdout cố định** cho lượt chạy GUI vì kết quả được tương tác qua cửa sổ và taskbar, còn khả năng hỗ trợ phụ thuộc OS/provider.

### Giải thích thiết kế ví dụ

- `GraphicsEnvironment.isHeadless()` chạy trước khi khởi tạo `JFrame`, nên self-test và lệnh headless không vô tình tạo GUI.
- `Taskbar.isTaskbarSupported()` kiểm tra khả năng nền tảng; `isSupported(feature)` kiểm tra riêng từng thao tác.
- `SwingUtilities.invokeLater(...)` tạo và cập nhật thành phần Swing trên **Event Dispatch Thread (EDT)**.
- Icon được tạo bằng `BufferedImage`, đặt cho `JFrame` và có thể được đặt cho Taskbar khi `ICON_IMAGE` được hỗ trợ.
- Nhánh tiến độ ưu tiên `PROGRESS_VALUE_WINDOW`, rồi fallback `PROGRESS_VALUE`.
- Badge `"3"` dùng được trên nền tảng chỉ hỗ trợ số; `null` xóa badge khi tính năng sẵn có.
- Yêu cầu attention chỉ được kích hoạt khi người dùng bấm nút, không phát sinh tự động liên tục khi khởi động.
- Mỗi thao tác dùng `UnsupportedOperationException`/`SecurityException` như điều kiện fallback; ứng dụng chính vẫn hoạt động.

Ví dụ cố tình **không mô phỏng công việc nền thực**; nút bấm thay đổi một giá trị ngay trên EDT. Ứng dụng tải hoặc xử lý dữ liệu thực phải chạy tác vụ nặng ở luồng nền để tránh đơ cửa sổ.

## 9. Tiến độ thật với `SwingWorker` và EDT

Trong Swing, mọi thay đổi `JProgressBar`, `JLabel` và trạng thái cửa sổ nên được điều phối trên EDT. **Không** chạy sao chép tệp, kết nối mạng hay tính toán nặng trên EDT: cửa sổ sẽ treo, icon/progress không phản hồi, attention có thể bị trì hoãn.

Mô hình thông thường:

```java
// Đoạn minh họa trong một phương thức đang chạy trên EDT.
// taskbarDemo là thành phần UI của ứng dụng thực (tự đóng gói cập nhật Taskbar).
SwingWorker<Void, Void> worker = new SwingWorker<>() {
    @Override
    protected Void doInBackground() throws Exception {
        for (int i = 0; i <= 100; i += 10) {
            // Thay bằng đơn vị công việc thật; không ngủ trên EDT.
            setProgress(i); // Phát thuộc tính bound "progress" cho UI.
        }
        return null;
    }

    @Override
    protected void done() {
        // Đã quay về EDT; kiểm tra kết quả, hiển thị lỗi/thành công.
    }
};
worker.addPropertyChangeListener(event -> {
    if ("progress".equals(event.getPropertyName())) {
        int value = (Integer) event.getNewValue();
        // Cập nhật JProgressBar và Taskbar tại đây trên EDT.
    }
});
worker.execute();
```

Đây là **mã minh họa** cần các import `javax.swing.SwingWorker` và tích hợp với thành phần UI của ứng dụng; tự nó không phải chương trình độc lập. Không dùng vòng lặp `i += 10` như cách tính tiến độ thật: ứng dụng phải phát số lượng bước đã hoàn thành/tổng số thực, hoặc trạng thái indeterminate khi chưa biết tổng. `SwingWorker` thông báo thay đổi progress về EDT khi dùng `setProgress`.

Khi kết thúc công việc, luôn cập nhật UI theo đúng kết quả: thành công, hủy hoặc lỗi. Với trạng thái error, người dùng vẫn cần đọc được thông báo và có hành động khôi phục trong cửa sổ; màu đỏ/nhấp nháy trên taskbar không đủ thông tin.

## 10. Fallback đúng cho từng nền tảng

**Windows:** thường có biểu diễn cửa sổ trên taskbar; tùy phiên bản hệ điều hành, cách đóng gói chương trình và JDK, các tính năng progress/attention có thể khác. Các tính năng window progress nên được kiểm tra riêng. Nếu ứng dụng mở nhiều cửa sổ được gom thành nhóm, OS quyết định biểu diễn nào hiển thị.

**macOS:** Dock thường thể hiện ứng dụng; badge/attention/icon có thể tồn tại ở cấp ứng dụng. Việc bỏ yêu cầu attention có thể được OS xử lý khác, ví dụ khi người dùng kích hoạt ứng dụng. Không giả định `setWindowProgressValue` hoạt động chỉ vì `setIconImage` hoạt động.

**Linux:** phụ thuộc desktop environment, window manager, launcher và tích hợp giữa JDK với shell. Không kết luận mọi Linux desktop đều hỗ trợ. Javadoc của Java 17 nêu giới hạn của hỗ trợ Linux đối với một số môi trường Unity; trong các runtime mới, hãy dựa trên capability thực tế thay vì viết hard-code “Linux luôn có/không có”. Một chương trình chạy từ terminal không nhất thiết có biểu tượng ứng dụng giống khi được launch từ `.desktop` file.

**Headless/CI:** không có taskbar để quan sát. Chạy test phần logic và xác minh ứng dụng không bị crash khi thiếu GUI. Đối với tương tác native, cần kiểm thử thủ công hoặc automated GUI test trên môi trường desktop thực với đủ khả năng hiển thị.

Khả năng `Taskbar.isSupported(feature)` trả `true` chỉ chứng minh **hỗ trợ API**, không đảm bảo hiệu ứng sẽ nhìn thấy: hệ điều hành có thể giấu biểu tượng, tắt animation, không cho cửa sổ không displayable hiện trên taskbar hoặc hạn chế attention khi ứng dụng đang active.

## 11. Phân biệt Taskbar, notification và accessibility

Bốn kênh thể hiện trạng thái cho người dùng:

| Kênh | Mục đích | Rủi ro nếu dùng duy nhất |
| --- | --- | --- |
| `JProgressBar`/status trong cửa sổ | Thể hiện tiến độ, lỗi và kết quả đầy đủ | Người dùng không thấy khi chuyển app |
| `Taskbar` progress | Nhìn nhanh tiến độ khi app ở nền | Nền tảng có thể không hỗ trợ |
| Badge | Số tác vụ/tin chưa đọc hoặc trạng thái ngắn | Không chứa mô tả nguyên nhân hay hành động |
| Attention | Đề nghị người dùng quay lại ứng dụng | OS có thể bỏ qua; lặp lại sẽ gây phiền |

`Taskbar.requestUserAttention(...)` **không thay thế** hệ thống notification có nội dung, âm thanh, quyền cho phép hoặc lịch sử thông báo. Không dùng nó để yêu cầu quyền truy cập hay xử lý dữ liệu nhạy cảm. Với khả năng tiếp cận, cần có text trạng thái rõ ràng trong cửa sổ, cập nhật ý nghĩa tiến độ và có lựa chọn không phụ thuộc chỉ vào màu hay animation.

Ví dụ, khi đồng bộ lỗi, ứng dụng có thể hiện: `"Không thể đồng bộ. Kiểm tra kết nối và thử lại."` trong cửa sổ, đặt tiến độ trạng thái `ERROR` nếu được hỗ trợ và yêu cầu attention một lần. Khi người dùng mở lỗi, ứng dụng cập nhật badge/attention theo trạng thái đã được đọc.

## 12. Kiểm thử tiến độ, icon và attention

Đừng viết unit test kiểu “taskbar đã nhấp nháy” bằng cách so chuỗi log: OS quyết định cách hiển thị. Nên tách hai lớp:

1. **Unit test logic:** kiểm tra hàm `percent`, luật chuyển trạng thái `RUNNING -> PAUSED -> COMPLETED` hoặc `ERROR`, điều kiện nào phát attention và khi nào xóa badge. Fake interface cập nhật taskbar để kiểm tra các lệnh được phát. Có thể chạy ở headless.
2. **Kiểm thử tích hợp GUI:** chạy ứng dụng trên Windows/macOS/Linux desktop mục tiêu, kiểm tra từng `Feature` thực tế, quan sát icon/progress/attention, thử cả cửa sổ được focus và không focus, thử trạng thái hoàn tất, hủy, lỗi và nhiều cửa sổ.

Ma trận đề xuất:

| Trường hợp | Kỳ vọng |
| --- | --- |
| `java -Djava.awt.headless=true ...` | Bỏ qua GUI an toàn, không ném `HeadlessException` |
| `Taskbar.isTaskbarSupported()==false` | Chức năng xử lý vẫn chạy; Swing hiển thị trạng thái |
| Có `PROGRESS_VALUE_WINDOW` | 0/25/100 được hiển thị trên biểu diễn cửa sổ khi OS cho phép |
| Chỉ có `PROGRESS_VALUE` | Tiến độ được thể hiện cấp ứng dụng |
| Không hỗ trợ progress | Có `JProgressBar` và text tương đương |
| Có `ICON_BADGE_NUMBER` | Đặt số `"3"` và xóa bằng `null` |
| Có `ICON_BADGE_TEXT` | Badge text tùy khả năng của OS |
| Có `USER_ATTENTION(_WINDOW)` | Yêu cầu một lần, tôn trọng OS và trạng thái active |
| Không hỗ trợ attention | Giao diện vẫn có thông báo, app không crash |
| Đã hoàn tất/hủy | Trạng thái native được dọn; không còn progress/badge cũ |
| Có nhiều cửa sổ | Hành vi nhóm icon được kiểm chứng trên OS mục tiêu |

Cần ghi môi trường (phiên bản JDK, OS, desktop environment, launcher, chế độ remote/headless) khi có vấn đề phát sinh. Vì taskbar là tích hợp native, khác biệt UI giữa các OS **không tự là lỗi Java**; phải so với chức năng sản phẩm đã yêu cầu và feature support runtime.

## 13. Lỗi phổ biến

| Cách làm dễ lỗi | Tại sao sai | Cách làm phù hợp |
| --- | --- | --- |
| Gọi `Taskbar.getTaskbar()` ngay khi app khởi động trên CI | Headless/không hỗ trợ nền tảng | Kiểm tra headless và `isTaskbarSupported()` |
| Kiểm tra `isTaskbarSupported()` rồi gọi mọi API | Mỗi `Feature` được hỗ trợ độc lập | `isSupported(feature)` trước từng thao tác |
| Chỉ gọi `JFrame.setIconImage(...)` và kỳ vọng đổi Dock icon | Icon cửa sổ khác icon ứng dụng | Khi có `ICON_IMAGE`, dùng `Taskbar.setIconImage(...)` |
| Dùng `"NEW"` trên nền tảng chỉ có badge số | `ICON_BADGE_NUMBER` không phải text tự do | Chỉ truyền chuỗi số hoặc dùng fallback trong UI |
| Dùng `setProgressValue(-1)` để hiện “đang tải” | Ngoài 0–100 có nghĩa là ẩn | `State.INDETERMINATE` nếu hỗ trợ, còn không dùng spinner trong UI |
| Gọi `setWindowProgressState(...)` khi chỉ có `PROGRESS_VALUE` | Khác feature cấp cửa sổ và cấp ứng dụng | Chọn đúng API theo capability |
| Gọi `requestUserAttention(...)` liên tục | Có thể gây nhấp nháy/phiền hoặc OS bỏ qua | Kích hoạt theo sự kiện, giới hạn tần suất |
| Kỳ vọng attention tự đem ứng dụng lên foreground | OS không cam kết giành focus | Thông báo rõ trong UI, tôn trọng focus người dùng |
| Cập nhật Swing từ background thread | Vi phạm mô hình EDT, lỗi race/hiển thị | `SwingWorker`, `SwingUtilities.invokeLater(...)` |
| Không dọn badge/progress sau khi xong | Người dùng thấy trạng thái đã cũ | Xóa theo lifecycle của công việc |
| Test chỉ trên máy phát triển | Feature khác theo OS/JDK/launcher | Chạy ma trận desktop và headless phù hợp |

## 14. Checklist áp dụng trong ứng dụng thực

- [ ] Luồng chính hoạt động khi không có `Taskbar` hoặc một `Feature` riêng lẻ.
- [ ] Trước khi lấy Taskbar đã kiểm tra `GraphicsEnvironment.isHeadless()` và `Taskbar.isTaskbarSupported()`.
- [ ] Icon cửa sổ, icon ứng dụng và badge được phân biệt rõ; ảnh sắc nét, phù hợp launcher.
- [ ] Tiến độ nghiệp vụ quy đổi đúng 0–100, có cách biểu đạt khi chưa biết tổng.
- [ ] Cấp window vs cấp application được chọn đúng; không dùng `PROGRESS_STATE_WINDOW` khi không hỗ trợ.
- [ ] Mọi lần hoàn tất/hủy/lỗi có hành vi dọn native rõ ràng.
- [ ] Attention được phát có mục đích, không spam và không giành focus vô cớ.
- [ ] Cập nhật Swing chạy trên EDT; tác vụ dài chạy ngoài EDT.
- [ ] Có mô tả trạng thái bằng chữ trong UI, phù hợp accessibility.
- [ ] Có unit test logic ở headless và kiểm thử GUI trên OS/desktop/launcher thực.
- [ ] Mọi `UnsupportedOperationException`/`SecurityException` từ tích hợp native được xử lý theo chức năng fallback của sản phẩm.

## Tài liệu chính thức

- [Java SE 17 — `java.awt.Taskbar`](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/Taskbar.html): các API icon, badge, progress và attention cùng quy tắc hỗ trợ.
- [Java SE 17 — `Taskbar.Feature`](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/Taskbar.Feature.html): danh sách feature và phương thức tương ứng.
- [Java SE 17 — `Taskbar.State`](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/Taskbar.State.html): các trạng thái của progress cửa sổ.
- [OpenJDK JEP 272 — Platform-Specific Desktop Features](https://openjdk.org/jeps/272): lý do đưa API desktop đa nền tảng vào Java 9.
- [Java SE 17 — `GraphicsEnvironment`](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/GraphicsEnvironment.html): kiểm tra headless.
- [Java SE 17 — `SwingWorker`](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/javax/swing/SwingWorker.html): mẫu tách tác vụ nền khỏi cập nhật GUI trên EDT.

**Cốt lõi:** `Taskbar` giúp nâng trải nghiệm desktop bằng icon, badge, tiến độ và attention, nhưng thành công phụ thuộc OS và từng `Feature`. Kiểm tra capability, duy trì UI fallback và dọn trạng thái theo lifecycle là điều kiện để ứng dụng Java chạy tin cậy.
