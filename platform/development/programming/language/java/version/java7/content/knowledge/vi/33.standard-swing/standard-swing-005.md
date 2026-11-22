# Nimbus Look and Feel trong `javax.swing.plaf.nimbus` — Swing hiện đại

## 1. Nimbus là gì và có còn được hỗ trợ?

**Nimbus** là một **Look and Feel (L&F)** của Java Swing: bộ quy tắc định hình cách vẽ, màu sắc, trạng thái tương tác và cảm giác thị giác của các thành phần như `JButton`, `JTextField`, `JComboBox`, `JTable`, `JProgressBar`. Nimbus hoạt động đa nền tảng; chương trình Swing vẫn dùng các lớp Swing quen thuộc, còn giao diện được vẽ thông qua một Look and Feel cụ thể.

**Kết luận về khả năng hỗ trợ:** `javax.swing.plaf.nimbus` là **public API**, vẫn được liệt kê trong tài liệu Java SE/JDK 26 của module `java.desktop`. Các lớp `NimbusLookAndFeel`, `NimbusStyle`, `AbstractRegionPainter` và `State<T>` tiếp tục có tài liệu chính thức. Vì vậy, **namespace `javax.swing.plaf.nimbus` đang được hỗ trợ** cho ứng dụng Swing desktop; không cần thư viện Nimbus bên ngoài trong bản JDK desktop tiêu chuẩn.

Nội dung bài học này áp dụng cho code Java hiện nay, ví dụ **Java 17+**. Điều đáng nhớ không phải chỉ là Nimbus có từ thời Java 7, mà là **các API công khai này vẫn dùng được trong Java hiện đại**. Không nhập các lớp từ namespace nội bộ `com.sun.*` để sử dụng Nimbus: ứng dụng nên dùng public API `javax.swing.plaf.nimbus` hoặc để `UIManager` chọn Look and Feel đã đăng ký.

**Phạm vi:** Nimbus dùng cho **Swing desktop GUI**; nó không phải framework giao diện web, không biến ứng dụng Swing thành ứng dụng native OS, và không giải quyết logic nghiệp vụ. Ứng dụng chạy trên máy chủ headless không có màn hình không thể hiển thị `JFrame` như ứng dụng desktop.

## 2. Nimbus nằm ở đâu trong kiến trúc Swing?

Swing sử dụng cơ chế **pluggable Look and Feel**. Phần lớn component Swing giao việc vẽ cho `ComponentUI` (UI delegate). Cùng một `JButton` có thể trông khác khi chuyển từ Nimbus sang Look and Feel khác, trong khi các action listener và mô hình dữ liệu của nó vẫn giữ nguyên.

```text
JFrame / JPanel / JButton / JTextField ...
                 |
                 v
  Swing UI delegate (ComponentUI)
                 |
                 v
      Look and Feel được chọn
        /                   \
    Nimbus                L&F khác
  (Synth-based)       (Metal, System...)
        |
        +-- NimbusStyle / UIDefaults / trạng thái
        +-- Painter: nền, viền, vùng được chọn...
```

Trong cấu trúc Nimbus:

- `NimbusLookAndFeel`: lớp public cài đặt Nimbus; **extends `SynthLookAndFeel`**, kế thừa nền tảng hỗ trợ định nghĩa style theo region/state.
- `NimbusStyle`: đại diện style được tìm cho một **region** của component, lấy màu, font, painter và thuộc tính theo quy ước key trong `UIDefaults`; là lớp `final`.
- `AbstractRegionPainter`: lớp cơ sở để xây dựng họa sĩ vẽ (painter) cho vùng/component khi cần thiết kế chuyên sâu.
- `State<T extends JComponent>`: cho phép định nghĩa trạng thái tùy chỉnh; những trạng thái thường gặp bao gồm enabled, disabled, mouse-over, focused, pressed, selected.
- `UIDefaults`: bảng key/value chứa các thiết lập giao diện. Nimbus có thể lấy các painter khác nhau cho các trạng thái khác nhau.
- `UIManager`: chọn Look and Feel, truy vấn Look and Feel đã cài và quản lý mặc định UI ở mức ứng dụng.

Một thành phần có thể được tô khác nhau khi đang bật/tắt, khi chuột di chuyển lên, khi nhận focus, hoặc khi được chọn. Đó là lý do một thay đổi đơn giản như `button.setBackground(...)` **không nhất thiết quyết định toàn bộ vẻ ngoài** trong mọi trạng thái Nimbus.

## 3. Nhận diện chính xác package, module và API

| Tên | Vai trò | Khi nào sử dụng |
| --- | --- | --- |
| `javax.swing.plaf.nimbus.NimbusLookAndFeel` | Triển khai Nimbus Look and Feel | Chọn trực tiếp Nimbus bằng public API |
| `javax.swing.UIManager` | Liệt kê và kích hoạt các L&F | Ưu tiên cho ứng dụng muốn hỗ trợ fallback |
| `javax.swing.UIManager.LookAndFeelInfo` | Tên hiển thị và tên lớp của L&F đã đăng ký | Duyệt `getInstalledLookAndFeels()` |
| `javax.swing.UIDefaults` | Bảng cấu hình key/value | Đặt màu, font, painter; override từng component |
| `javax.swing.plaf.nimbus.NimbusStyle` | Style dựa trên Synth, liên kết region/state | Đọc/định nghĩa style chuyên sâu |
| `javax.swing.plaf.nimbus.AbstractRegionPainter` | Cơ sở viết painter tùy biến | Khi xây renderer Nimbus chuyên sâu |
| `javax.swing.plaf.nimbus.State` | Định nghĩa trạng thái tùy biến | Thành phần có trạng thái ngoài bộ có sẵn |

Các thành phần trên thuộc **module `java.desktop`**. Nếu dự án dùng Java Platform Module System (JPMS), file `module-info.java` cần có:

```java
module my.desktop.app {
    requires java.desktop;
}
```

Đây là đoạn cấu hình module minh họa, không phải một chương trình độc lập. Dự án không dùng `module-info.java` và chạy classpath bình thường không cần thêm file này. Một runtime tự đóng gói bằng `jlink` cần chứa module `java.desktop` nếu dùng Swing.

## 4. Bật Nimbus đúng cách trước khi tạo component

Trình tự an toàn khi khởi động ứng dụng:

1. Chạy thao tác UI trên **Event Dispatch Thread (EDT)**, ví dụ `SwingUtilities.invokeLater(...)`.
2. Trước khi tạo component, dùng `UIManager.getInstalledLookAndFeels()` để xác định Nimbus có mặt; tên hiển thị thông dụng là `"Nimbus"`.
3. Gọi `UIManager.setLookAndFeel(info.getClassName())`, xử lý lỗi và có phương án dùng L&F hiện tại khi không có Nimbus.
4. Tạo `JFrame`, `JPanel`, button, text field và đăng ký sự kiện.
5. Hiển thị giao diện bằng `setVisible(true)`.

Không giả định tên file hoặc lớp của Nimbus được đăng ký trên **mọi** bản Java tùy biến. `getInstalledLookAndFeels()` mô tả chính các L&F hiện có trong runtime đang chạy. Với JDK desktop phổ biến, Nimbus thường có trong danh sách.

### Ví dụ 1 — ứng dụng Swing kích hoạt Nimbus với fallback

Lưu thành **`NimbusHello.java`**. Đây là **chương trình độc lập**, có `main` và chạy được bằng Java 17+ trên hệ thống có GUI.

```java
import java.awt.BorderLayout;
import java.awt.GridLayout;
import javax.swing.JButton;
import javax.swing.JComboBox;
import javax.swing.JFrame;
import javax.swing.JLabel;
import javax.swing.JOptionPane;
import javax.swing.JPanel;
import javax.swing.JProgressBar;
import javax.swing.JTextField;
import javax.swing.SwingUtilities;
import javax.swing.UIManager;
import javax.swing.UnsupportedLookAndFeelException;

public class NimbusHello {
    private static boolean enableNimbus() {
        for (UIManager.LookAndFeelInfo info :
                UIManager.getInstalledLookAndFeels()) {
            if ("Nimbus".equals(info.getName())) {
                try {
                    UIManager.setLookAndFeel(info.getClassName());
                    return true;
                } catch (ClassNotFoundException
                         | InstantiationException
                         | IllegalAccessException
                         | UnsupportedLookAndFeelException ex) {
                    System.err.println(
                            "Cannot enable Nimbus: "
                            + ex.getClass().getSimpleName());
                    return false;
                }
            }
        }
        return false;
    }

    private static void createAndShowUI() {
        boolean nimbusSelected = enableNimbus();

        JFrame frame = new JFrame("Nimbus Swing Demo");
        frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);

        JPanel content = new JPanel(new BorderLayout(12, 12));
        content.setBorder(
                javax.swing.BorderFactory.createEmptyBorder(16, 16, 16, 16));

        JPanel form = new JPanel(new GridLayout(0, 2, 8, 8));
        JTextField name = new JTextField(18);
        JComboBox<String> priority = new JComboBox<>(
                new String[] {"Thap", "Trung binh", "Cao"});
        JProgressBar progress = new JProgressBar(0, 100);
        progress.setValue(65);
        progress.setStringPainted(true);

        form.add(new JLabel("Ten:"));
        form.add(name);
        form.add(new JLabel("Muc do:"));
        form.add(priority);
        form.add(new JLabel("Tien do:"));
        form.add(progress);

        JButton action = new JButton("Xac nhan");
        action.addActionListener(event ->
                JOptionPane.showMessageDialog(
                        frame, "Xin chao " + name.getText()));

        content.add(form, BorderLayout.CENTER);
        content.add(action, BorderLayout.SOUTH);

        frame.setContentPane(content);
        frame.pack();
        frame.setLocationRelativeTo(null);
        frame.setVisible(true);

        System.out.println("Nimbus selected: " + nimbusSelected);
        System.out.println("Active look and feel: "
                + UIManager.getLookAndFeel().getName());
    }

    public static void main(String[] args) {
        SwingUtilities.invokeLater(NimbusHello::createAndShowUI);
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 NimbusHello.java
java NimbusHello
```

**Kết quả:** Cửa sổ hiện textbox, combo box, progress bar 65% và nút bấm; nhấn nút mở hộp thoại. Nếu Nimbus có sẵn và được kích hoạt thành công, stdout là:

```text
Nimbus selected: true
Active look and feel: Nimbus
```

Nếu runtime không có Nimbus, dòng đầu tiên là `Nimbus selected: false` và dòng thứ hai chứa tên L&F mặc định thực tế; giao diện vẫn được tạo. Nếu hệ thống không có môi trường đồ họa, `JFrame` có thể phát sinh `HeadlessException`; đây là hạn chế môi trường chạy, không chứng tỏ namespace Nimbus đã bị xóa.

**Vì sao đoạn code đúng?** `UIManager.setLookAndFeel` chạy **trước khi tạo** `JFrame` và các `JComponent`, toàn bộ khởi tạo UI ở EDT, nên mỗi component nhận UI delegate theo Nimbus ngay lúc khởi tạo. Action listener chỉ làm việc với API Swing thông thường, không phụ thuộc Nimbus.

## 5. Có thể dùng `NimbusLookAndFeel` trực tiếp không?

Có. `NimbusLookAndFeel` là **lớp công khai** thuộc `javax.swing.plaf.nimbus`. Khi ứng dụng yêu cầu Nimbus và đã kiểm soát runtime, bạn có thể khởi tạo trực tiếp:

```java
// Đoạn minh họa, đặt trong phương thức phù hợp trên EDT.
// Imports: javax.swing.UIManager;
//          javax.swing.UnsupportedLookAndFeelException;
//          javax.swing.plaf.nimbus.NimbusLookAndFeel;
try {
    UIManager.setLookAndFeel(new NimbusLookAndFeel());
} catch (UnsupportedLookAndFeelException ex) {
    throw new IllegalStateException("Nimbus is not supported", ex);
}
```

Đây là **đoạn minh họa cần đặt trong class/method**, không phải chương trình độc lập. Cách này ít code hơn, nhưng khi cần hỗ trợ nhiều bản runtime hoặc fallback sang L&F khác, cách duyệt `getInstalledLookAndFeels()` ở ví dụ đầu phù hợp hơn.

Bạn cũng có thể chỉ định L&F ngay khi khởi động JVM:

```bash
java -Dswing.defaultlaf=javax.swing.plaf.nimbus.NimbusLookAndFeel MySwingApp
```

`MySwingApp` là tên class ứng dụng Swing có `main` của bạn; câu lệnh là **mẫu**, chỉ chạy khi class đó tồn tại. Tham số `-D` phải xuất hiện **trước** tên class. Không nên dùng cấu hình L&F toàn JVM cùng với mã tự thay đổi L&F một cách thiếu chủ đích vì thiết lập sau có thể thay thế thiết lập trước.

## 6. Tùy biến toàn ứng dụng bằng `UIDefaults`

Nimbus dùng các key trong bảng defaults, ví dụ:

- `nimbusBase`: màu nền tảng để tạo một phần bảng màu chủ đạo.
- `nimbusFocus`: màu dùng trong biểu diễn trạng thái focus.
- `control`: màu control tổng quát.
- `ProgressBar[Enabled].foregroundPainter`: painter vẽ foreground của progress bar khi ở trạng thái Enabled.
- `ProgressBar[Enabled].backgroundPainter`: painter vẽ nền tương ứng.

Các tên key Nimbus được mô tả trong Java API, nhưng **tập key/value cụ thể có thể đổi giữa các JDK**. Khi triển khai tùy biến sâu, kiểm tra `UIManager.getLookAndFeelDefaults()` và thử trên đúng runtime/phân phối JDK của ứng dụng. Không hard-code toàn bộ bảng màu mặc định của một JDK cũ rồi giả định nó luôn giống nhau.

Cấu hình toàn ứng dụng thường dùng `UIManager.put(key, value)` **trước khi** kích hoạt Nimbus và tạo các component. Ví dụ:

```java
// Đoạn minh họa, đặt trước khi gọi setLookAndFeel(...).
UIManager.put("nimbusBase", new java.awt.Color(33, 101, 132));
UIManager.put("nimbusFocus", new java.awt.Color(235, 145, 55));
UIManager.put("control", new java.awt.Color(245, 247, 250));
```

Màu hiển thị thực tế có thể là màu đã biến đổi hoặc pha trộn do Nimbus dựng từ các giá trị gốc; không nên suy luận mọi pixel trên mọi component đều có đúng mã RGB đã đặt. Cấu hình UI defaults mang **phạm vi toàn ứng dụng**: các component cùng kiểu/region và trạng thái có thể bị ảnh hưởng.

## 7. Tùy biến riêng một component bằng `Nimbus.Overrides`

Nếu chỉ muốn khác biệt trên một component, Nimbus hỗ trợ client property `"Nimbus.Overrides"` có giá trị **`UIDefaults`**. Các key trong đó được ưu tiên cho **instance cụ thể** đó; các component khác tiếp tục dùng defaults chung.

Có thêm client property `"Nimbus.Overrides.InheritDefaults"`:

| Giá trị | Ý nghĩa |
| --- | --- |
| `Boolean.TRUE` | Giữ defaults chung rồi áp các key đã override cho component; đây là hành vi mặc định |
| `Boolean.FALSE` | Chỉ lấy bảng override của component; nếu bỏ nhiều key cần thiết thì UI có thể khác mong đợi |

Thông thường dùng `TRUE` để chỉ thay các key cần thiết. Painter có thể được viết bằng interface `javax.swing.Painter`. Tùy biến theo trạng thái có thể khiến giao diện thay đổi khi hover, focus hoặc disabled, vì mỗi trạng thái có thể sử dụng painter riêng.

### Ví dụ 2 — màu chung Nimbus và painter riêng cho một progress bar

Lưu thành **`NimbusTheme.java`**. Đây là chương trình hoàn chỉnh khác với ví dụ 1.

```java
import java.awt.Color;
import java.awt.GridLayout;
import javax.swing.JFrame;
import javax.swing.JComponent;
import javax.swing.JLabel;
import javax.swing.JPanel;
import javax.swing.JProgressBar;
import javax.swing.Painter;
import javax.swing.SwingUtilities;
import javax.swing.UIDefaults;
import javax.swing.UIManager;
import javax.swing.UnsupportedLookAndFeelException;
import javax.swing.plaf.nimbus.NimbusLookAndFeel;

public class NimbusTheme {
    private static void createAndShowUI() {
        UIManager.put("nimbusBase", new Color(33, 101, 132));
        UIManager.put("nimbusFocus", new Color(235, 145, 55));

        try {
            UIManager.setLookAndFeel(new NimbusLookAndFeel());
        } catch (UnsupportedLookAndFeelException ex) {
            throw new IllegalStateException("Nimbus unavailable", ex);
        }

        JProgressBar normal = new JProgressBar(0, 100);
        normal.setValue(65);
        normal.setStringPainted(true);

        JProgressBar customized = new JProgressBar(0, 100);
        customized.setValue(65);
        customized.setStringPainted(true);

        UIDefaults overrides = new UIDefaults();
        overrides.put(
                "ProgressBar[Enabled].foregroundPainter",
                (Painter<JComponent>) (graphics, component, width, height) -> {
                    graphics.setColor(new Color(35, 165, 110));
                    graphics.fillRoundRect(
                            0, 0, width, height, 8, 8);
                });
        customized.putClientProperty("Nimbus.Overrides", overrides);
        customized.putClientProperty(
                "Nimbus.Overrides.InheritDefaults", Boolean.TRUE);

        JPanel panel = new JPanel(new GridLayout(0, 1, 8, 8));
        panel.setBorder(
                javax.swing.BorderFactory.createEmptyBorder(16, 16, 16, 16));
        panel.add(new JLabel("Nimbus mac dinh:"));
        panel.add(normal);
        panel.add(new JLabel("Nimbus override theo component:"));
        panel.add(customized);

        JFrame frame = new JFrame("Nimbus UIDefaults");
        frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);
        frame.setContentPane(panel);
        frame.pack();
        frame.setLocationRelativeTo(null);
        frame.setVisible(true);

        System.out.println("Nimbus class: "
                + UIManager.getLookAndFeel().getClass().getName());
    }

    public static void main(String[] args) {
        SwingUtilities.invokeLater(NimbusTheme::createAndShowUI);
    }
}
```

Chạy trên JDK 17+ có GUI:

```bash
javac -encoding UTF-8 NimbusTheme.java
java NimbusTheme
```

Khi Nimbus được hỗ trợ, stdout:

```text
Nimbus class: javax.swing.plaf.nimbus.NimbusLookAndFeel
```

**Để quan sát:** cửa sổ hiển thị hai progress bar. Cả hai chịu màu Nimbus chung; **chỉ progress bar thứ hai** có override painter cho trạng thái `Enabled`. Renderer có thể vẽ lại bằng painter khác khi trạng thái thay đổi; vì vậy ví dụ thay **một trạng thái**, không cam kết mọi trạng thái đều có cùng màu tùy chỉnh.

**Lưu ý kỹ thuật:** painter được gọi trong quá trình vẽ, có thể gọi rất thường xuyên. Không thực hiện I/O, sleep, truy vấn mạng hoặc tạo tài nguyên đắt tiền bên trong `paint(...)`. Cần xử lý kích thước `width`/`height` thực tế và thử ở nhiều độ phân giải. Nếu chỉ thay màu chữ, nhãn hoặc font đơn giản, ưu tiên API component và defaults phù hợp trước khi viết painter riêng.

## 8. Đổi Look and Feel khi cửa sổ đang mở

Kích hoạt Nimbus **trước khi tạo UI** là đường đi đơn giản nhất. Nếu người dùng có menu chọn giao diện lúc ứng dụng đang chạy, thay đổi `UIManager.setLookAndFeel(...)` **không tự động bảo đảm** mọi component đã tồn tại được cập nhật.

Trong trường hợp đổi L&F giữa chừng:

1. Chạy việc chuyển đổi trên EDT.
2. Chọn L&F mới và xử lý lỗi.
3. Gọi `SwingUtilities.updateComponentTreeUI(window)` cho từng cửa sổ đang hiển thị, rồi `validate()`/`repaint()` và cân nhắc `pack()` khi thay đổi kích cỡ thành phần.
4. Kiểm tra lại custom renderer, icon, border, cell editor, popup và những UI defaults đã cache; chỉ giữ các override tương thích với L&F mới.

Ví dụ logic cập nhật sau khi `UIManager.setLookAndFeel(...)` thành công (đoạn code đặt trong một method chạy ở EDT):

```java
for (java.awt.Window window : java.awt.Window.getWindows()) {
    javax.swing.SwingUtilities.updateComponentTreeUI(window);
    window.validate();
    window.repaint();
}
```

Đây **là một đoạn minh họa**, không phải `main` độc lập. API Nimbus cảnh báo rằng đổi Look and Feel nhưng giữ `ComponentUI` cũ có thể gây hành vi không mong đợi, chẳng hạn sai màu.

## 9. Đặc tính về hiển thị, khả năng tiếp cận và vận hành

**Đa nền tảng không có nghĩa là pixel-perfect.** Nimbus tạo một hệ giao diện tương đối đồng nhất, nhưng font thực tế, kích cỡ chữ, DPI/scaling, anti-aliasing, thiết bị hiển thị, vùng vẽ và bản JDK vẫn có thể ảnh hưởng kết quả. Hãy dùng layout manager (`BorderLayout`, `GridLayout`, `GridBagLayout`...) thay vì đặt vị trí cố định bằng pixel.

**Đừng xử lý công việc dài trên EDT.** Nimbus là một lớp hiển thị; nó không thay đổi quy tắc Swing: cập nhật giao diện trên EDT, đưa tác vụ I/O/tính toán dài vào `SwingWorker` hoặc worker khác, rồi đưa kết quả về EDT. Event handler chạy nặng sẽ làm giao diện Nimbus cũng bị treo.

**Đánh giá accessibility.** Một theme trông đẹp vẫn phải có tương phản đủ tốt, biểu thị rõ focus, vùng click hợp lý, hỗ trợ bàn phím và các tên/description truy cập (`AccessibleContext` khi cần). Thay màu `nimbusFocus` mà làm mất dấu hiệu focus là một lỗi trải nghiệm.

**Kiểm thử trên runtime thực tế.** Module `java.desktop` cần được phân phối đầy đủ; đóng gói với `jpackage`/`jlink` phải thử bản release trên Windows/macOS/Linux mục tiêu. Không dựa trên preview của IDE để kết luận runtime production có cùng L&F/charset/font.

**Đảm bảo phù hợp với ngữ cảnh:** Swing và Nimbus phù hợp khi bảo trì/phát triển ứng dụng Java desktop Swing. Đừng trộn widget Swing với công nghệ khác rồi giả định chỉ thay Nimbus là thống nhất toàn bộ UI. Tùy chỉnh sâu bằng painter đòi hỏi thêm QA cho từng trạng thái, component và phiên bản JDK.

## 10. Những hiểu nhầm và lỗi thường gặp

| Hiểu nhầm/lỗi | Diễn giải đúng / cách xử lý |
| --- | --- |
| “`javax.swing.plaf.nimbus` đã bị loại bỏ vì Java 7 cũ” | Không đúng: package vẫn có trong Java SE 26 docs của module `java.desktop`. |
| “Nimbus là một bộ component mới” | Nimbus là Look and Feel cho **các component Swing có sẵn**, không thay `JButton`/`JTextField`. |
| “Cứ đặt `JButton.setBackground` là thay được mọi trạng thái” | Nimbus có state-specific painter; cần kiểm tra style/UIDefaults cho kết quả mong muốn. |
| “Chỉ cần `UIManager.setLookAndFeel(...)` khi mọi cửa sổ đã mở” | Các component đã tồn tại có thể phải được cập nhật bằng `SwingUtilities.updateComponentTreeUI(...)`. |
| “Không cần EDT vì chỉ thay màu” | Thao tác với UI Swing phải tuân thủ mô hình EDT; thao tác lâu phải chạy ngoài EDT. |
| “Mọi JVM đều có Nimbus mặc định” | Nên kiểm tra `getInstalledLookAndFeels()` nếu ứng dụng phải chạy ở các runtime/phân phối tùy biến. |
| “Cấu hình `Nimbus.Overrides` cho một nút đổi cả ứng dụng” | Overrides theo component instance; `UIManager.put` thay defaults ở phạm vi rộng hơn. |
| “Chọn `InheritDefaults=false` cho một thay đổi nhỏ” | Có thể đánh mất nhiều key mặc định; thường dùng `Boolean.TRUE`. |
| “Namespace của Swing cần đổi thành `jakarta.swing`” | Không đúng: Swing tiếp tục dùng `javax.swing`/`javax.swing.plaf.nimbus` trong Java SE. |
| “Thay L&F sẽ sửa được giao diện nghẽn/đơ” | Giao diện đơ thường do block EDT; cần xử lý luồng và tác vụ dài, không phải đổi Nimbus. |

## 11. Quy trình áp dụng vào ứng dụng Swing hiện tại

1. **Xác định yêu cầu:** giữ giao diện thống nhất đa nền tảng hay theo phong cách OS? Nếu Nimbus phù hợp thì chọn từ installed L&F.
2. **Đặt L&F sớm:** gọi `UIManager.setLookAndFeel(...)` trên EDT, trước khi dựng cây component.
3. **Dùng API Swing tiêu chuẩn:** giữ logic nghiệp vụ và action listener tách khỏi quyết định theme.
4. **Tùy biến có chủ đích:** với yêu cầu màu chung dùng `UIManager.put`; với component đặc biệt dùng `Nimbus.Overrides` và kế thừa defaults.
5. **Chạy thử các trạng thái:** normal, hover, focused, selected, disabled, validation error; thử nhiều font và DPI.
6. **Kiểm tra đóng gói:** đảm bảo `java.desktop` có mặt, thử bản phân phối thực tế và fallback phù hợp.
7. **Đo hiệu năng nếu viết painter:** không thực hiện tác vụ dài trong `paint`; kiểm tra redraw/resize và trải nghiệm bàn phím.

## 12. Câu hỏi tự kiểm tra

1. Tại sao `NimbusLookAndFeel` là một lớp public API đang được hỗ trợ, còn việc dựa vào các namespace nội bộ không phù hợp với code hiện đại?
2. Sự khác nhau giữa `UIManager.put(...)` và `component.putClientProperty("Nimbus.Overrides", defaults)` là gì?
3. Vì sao nên gọi `UIManager.setLookAndFeel(...)` **trước khi** tạo `JFrame` và các `JComponent`?
4. Điều gì cần làm khi đổi Look and Feel trên cửa sổ đã tồn tại?
5. Khi button không đổi màu như mong đợi, những yếu tố nào thuộc `state` và `Painter` cần kiểm tra?

**Tóm tắt kiến thức cần nhớ:** Nimbus tiếp tục là Look and Feel Swing hợp lệ của Java SE. Code nên dùng public package `javax.swing.plaf.nimbus` hoặc `UIManager`, chọn L&F trên EDT trước khi tạo UI, tùy biến thông qua `UIDefaults` và `Nimbus.Overrides` khi cần, đồng thời kiểm tra trạng thái và runtime thực tế.

## Tài liệu tham khảo hiện hành

- [Oracle Java SE 26 — Package `javax.swing.plaf.nimbus`](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/javax/swing/plaf/nimbus/package-summary.html) — xác nhận namespace, painter, `UIDefaults`, component overrides.
- [Oracle Java SE 26 — `NimbusLookAndFeel`](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/javax/swing/plaf/nimbus/NimbusLookAndFeel.html) — public Look and Feel class, quan hệ kế thừa.
- [Oracle Java SE 26 — `NimbusStyle`](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/javax/swing/plaf/nimbus/NimbusStyle.html) — style, region/state và overrides.
- [Oracle Java SE 26 — `State`](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/javax/swing/plaf/nimbus/State.html) — custom component state.
- [Oracle Java SE 26 — `UIManager`](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/javax/swing/UIManager.html) — installed L&Fs, set/get Look and Feel, defaults.
- [Oracle Java SE 26 — `JComponent`](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/javax/swing/JComponent.html) — UI delegate, client properties, painting.
- [Oracle Java SE 26 — module `java.desktop`](https://docs.oracle.com/en/java/javase/26/docs/api/java.desktop/module-summary.html) — Swing và package Nimbus nằm trong Java desktop module.
