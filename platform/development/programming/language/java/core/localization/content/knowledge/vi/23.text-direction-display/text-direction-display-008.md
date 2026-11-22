# Độ dài bản dịch, xuống dòng và trách nhiệm của lớp giao diện

## 1. Tại sao đây là vấn đề localization, không chỉ là CSS hay LayoutManager?

Trong ứng dụng đa ngôn ngữ, cùng một ý nghĩa có thể được biểu đạt bằng các đoạn văn có **độ dài rất khác nhau**. Một nhãn tiếng Anh ngắn có thể trở thành một cụm dài hơn khi dịch sang tiếng Đức, tiếng Pháp hoặc tiếng Việt; một ngôn ngữ khác có thể dùng ít ký tự hơn nhưng glyph rộng hơn, hoặc cần chiều cao dòng lớn hơn. Những thay đổi này không phải lỗi của bản dịch.

Ví dụ các nhãn có cùng mục đích:

```text
en-US: Settings
vi-VN: Cài đặt
de-DE: Einstellungen
```

Nếu nhà phát triển thiết kế nút có chiều rộng cố định vừa đúng `Settings`, bản dịch `Einstellungen` có thể tràn hoặc bị cắt. Giảm cỡ chữ, bắt người dịch rút gọn bằng mọi giá hoặc chèn `\n` vào bản dịch để khớp đúng pixel hiện tại thường chỉ **che giấu một thiết kế giao diện thiếu linh hoạt**.

**Nguyên tắc quan trọng:** người dịch chịu trách nhiệm về **nội dung, ngữ nghĩa, trật tự từ và cách diễn đạt tự nhiên**; lớp giao diện và bộ layout chịu trách nhiệm về **kích thước, reflow, ngắt dòng để vừa vùng hiển thị, hướng văn bản và khả năng truy cập**. Hai bên có thể phối hợp bằng các ràng buộc nội dung rõ ràng, nhưng không được biến việc "vá layout" thành nhiệm vụ mặc định của người dịch.

Bài này tập trung vào ba chủ đề:

1. **Độ dài bản dịch**: mở rộng/thu ngắn, khác biệt độ rộng glyph và chiều cao dòng.
2. **Xuống dòng**: khác nhau giữa line break tự động và newline có ý nghĩa do nội dung yêu cầu.
3. **Trách nhiệm lớp giao diện**: layout thích ứng, Unicode line breaking, RTL/BiDi, kiểm thử overflow, truncate và accessibility.

Ví dụ Java sử dụng **Java 17+**, nhất là Swing để minh họa trách nhiệm lớp UI; các nguyên tắc tương tự áp dụng cho web, mobile và các công nghệ giao diện khác, nhưng API cụ thể sẽ khác.

## 2. Số ký tự không quyết định chiều rộng của bản dịch

Không thể lấy `String.length()` nhân với một hằng số để tính số pixel cần hiển thị.

Trong Java:

- `String.length()` đếm **UTF-16 code units**, không phải Unicode code points hay glyph.
- `String.codePointCount(0, s.length())` đếm code points, nhưng một grapheme cluster có thể gồm nhiều code points.
- Font là dạng **proportional** hay **monospaced**, size, weight, kerning, ligature và text shaping đều ảnh hưởng bề rộng.
- Một chữ thuộc CJK, một chữ Latin, dấu kết hợp hoặc emoji màu có thể chiếm diện tích khác nhau.
- Một số hệ chữ cần line-height phù hợp với các dấu hoặc phần mở rộng của glyph.
- Một đoạn văn RTL trộn số và Latin cần bộ bố cục biết Unicode Bidirectional Algorithm (BiDi).

Ví dụ, `"WWWW"` và `"iiii"` đều gồm bốn chữ cái Latin, nhưng trong nhiều font proportional, bề rộng rất khác. Một chuỗi `"A🌍B"` có `length()==4` và `codePointCount()==3`, song chiều rộng hiển thị còn do font/renderer quyết định.

### Ba thước đo thường bị nhầm

| Thước đo | Đo điều gì? | Có đủ để quyết định xuống dòng? |
| --- | --- | --- |
| `String.length()` | Số UTF-16 code units | **Không** |
| Code point/grapheme count | Đơn vị ký tự Unicode/hiển thị gần người dùng | **Không**: chưa có font, width, shaping |
| Kích thước sau layout | Glyph advance, wrapping, line-height, không gian component | **Có liên quan trực tiếp** nhưng phụ thuộc renderer và viewport |

Nếu layout cần biết có vừa hay không, hãy dùng **công cụ đo text của chính UI framework**, sau khi font, hướng viết, tỷ lệ màn hình và vùng hiển thị được xác định. Trong Swing, `FontMetrics`/`TextLayout` có thể tham gia đo, nhưng layout manager vẫn chịu trách nhiệm phân phối không gian tổng thể. `FontMetrics.stringWidth` cho một dòng text không phải giải pháp tổng quát cho styled text, BiDi phức tạp hay nhiều dòng có break opportunities.

### Ví dụ Java 17+: phân biệt UTF-16 và code point

Tạo file `TextLengthDemo.java`:

```java
public class TextLengthDemo {
    public static void main(String[] args) {
        String text = "A"
                + new String(Character.toChars(0x1F30D)) + "B";

        System.out.println("utf16=" + text.length());
        System.out.println("codePoints="
                + text.codePointCount(0, text.length()));
        System.out.println("longer label length="
                + "Einstellungen".length());
    }
}
```

```bash
javac TextLengthDemo.java
java TextLengthDemo
```

Kết quả:

```text
utf16=4
codePoints=3
longer label length=13
```

Ví dụ chứng minh số `char` không mô tả trọn ý nghĩa "độ dài bản dịch". Nó **không** đo bề rộng pixel; muốn đo phải đưa chuỗi vào font và UI renderer cụ thể.

## 3. Translation expansion/contraction: không có tỷ lệ cố định

Một câu ngắn có thể dài hơn nhiều sau dịch. Câu dài đôi khi có tỷ lệ mở rộng nhỏ hơn vì các cấu trúc ngôn ngữ khác nhau. Không có quy tắc đáng tin rằng "mọi bản dịch dài hơn tiếng Anh 30%" hoặc "đoạn nào cũng chỉ cần cộng 10px".

Các yếu tố ảnh hưởng:

- **Hình thái từ:** một từ trong ngôn ngữ này có thể thành cụm nhiều từ trong ngôn ngữ khác.
- **Mức độ lịch sự/ngữ cảnh:** nút hành động, thông báo lỗi, khẳng định/hỏi, các lựa chọn xưng hô.
- **Danh từ loại, giới tính/cách/số nhiều:** cả câu thay đổi, không chỉ một hậu tố.
- **Ký tự và font:** số glyph và bề rộng mỗi glyph không có quan hệ tuyến tính với chiều dài byte hoặc `char`.
- **Hướng chữ:** layout LTR/RTL có thể thay đổi vị trí icon, back button, mũi tên và thứ tự thành phần.
- **Locale của số/ngày giờ:** số `1,234.5` có thể thành `1.234,5`, hệ chữ số khác hoặc chuỗi ngày tháng dài hơn.
- **Độ rộng màn hình và accessibility:** phóng to chữ, DPI, zoom, font fallback, thiết bị nhỏ hoặc cửa sổ được thu hẹp.

**Thiết kế nên thử cả trường hợp mở rộng và thu ngắn**, không chỉ thử độ dài trung bình. Dùng pseudo-localization để cố tình kéo dài chuỗi và bổ sung ký tự có dấu giúp phát hiện sớm các component bị cắt trước khi có đủ bản dịch thật.

### Một chính sách placeholder tốt

Thông điệp nên lưu **cả câu** với placeholder có ý nghĩa thay vì ghép các mảnh cố định:

```properties
files.count={0} files selected
save.error=Could not save {0}
```

Người dịch có quyền đổi trật tự placeholder theo ngữ pháp. Tránh:

```java
// Không phù hợp nếu dịch phải đảo cấu trúc câu:
String text = translate("prefix") + count
        + translate("suffix");
```

Một thông điệp đầy đủ giúp bản dịch đúng, nhưng **không đảm bảo tự xuống dòng**: đó vẫn là trách nhiệm component/layout.

## 4. Xuống dòng: line break tự động khác newline mang ý nghĩa

Hãy tách hai loại:

### 4.1. Soft wrap / automatic line break

Khi một đoạn text vượt chiều rộng khả dụng, UI có thể tìm **break opportunity** và hiển thị phần tiếp theo trên dòng mới. Vị trí ngắt có thể thay đổi khi:

- cửa sổ được kéo rộng/hẹp;
- ngôn ngữ được đổi;
- cỡ font/zoom thay đổi;
- thiết bị đổi từ portrait sang landscape;
- người dùng bật accessibility scaling;
- font fallback hoặc ligature thay đổi.

Soft wrap **không làm thay đổi nội dung chuỗi nguồn**. Nếu lấy text từ data model, không nhất thiết có ký tự `\n` tại vị trí hiển thị xuống dòng.

### 4.2. Hard break / newline có chủ đích

Một ký tự `\n` thực sự nằm trong nội dung. Nó có thể có **ý nghĩa ngữ nghĩa**:

- phân cách các đoạn văn;
- danh sách địa chỉ nhiều dòng;
- lời thơ, trích dẫn, caption được thiết kế có cấu trúc;
- tách tiêu đề và mô tả khi content specification đòi hỏi.

Hard break cần được **quyết định từ content model** chứ không chỉ để một chuỗi vừa vào nút rộng 120px. Nếu người dịch tự chèn `\n` vào giữa từ/câu để chữa lỗi layout, trên màn hình rộng hơn nó vẫn bị ép xuống dòng và có thể trông kỳ cục.

### 4.3. Bảng trách nhiệm

| Tình huống | Nên để ai xử lý? |
| --- | --- |
| Đo chữ có vừa nút không | UI/layout |
| Thay đổi chiều rộng và số dòng theo viewport | UI/layout |
| Chọn vị trí ngắt dòng hợp quy tắc chữ viết | Text engine/line-break algorithm |
| Chọn từ ngữ tự nhiên, trật tự câu, ngữ pháp | Người dịch/content |
| Nội dung thực sự gồm hai đoạn văn | Content structure/resource |
| Nút rất ngắn có nhãn riêng được phê duyệt | Product design + content; resource có biến thể ngắn |
| Lỗi bị cắt hoặc icon che chữ | UI/layout, không yêu cầu người dịch bỏ thông tin thiết yếu |
| Trường chữ quá dài từ input người dùng | UI có overflow/truncate policy và đường truy cập nội dung đầy đủ |

Đôi khi một sản phẩm có cả **label đầy đủ** và **short label** được bản địa hóa, ví dụ dùng trong tab bar hẹp. Khi đó đây là **hai tài nguyên được thiết kế với mục đích rõ ràng**, không phải việc cắt tùy tiện một bản dịch.

## 5. Quy tắc ngắt dòng khác nhau giữa các hệ chữ

Không thể lấy `text.split(" ")` rồi coi mọi dấu cách là ranh giới từ hay ranh giới xuống dòng hợp lệ. W3C và Unicode mô tả nhiều cơ chế:

- **Tiếng Anh và nhiều ngôn ngữ Latin/Cyrillic:** thường ngắt tại ranh giới từ và khoảng trắng, nhưng dấu câu và dấu ngoặc vẫn có quy tắc.
- **Tiếng Việt:** khoảng trắng có thể phân cách **âm tiết**, không luôn tương ứng một từ; cách xuống dòng tự nhiên còn phụ thuộc biên tập và cấu trúc câu.
- **Tiếng Thái, Khmer, Lào:** nhiều từ không phân cách bằng khoảng trắng; ngắt dòng có thể đòi hỏi dictionary-based segmentation.
- **Tiếng Trung/Nhật:** có thể ngắt theo chữ/âm tiết, nhưng quy tắc như **kinsoku shori** hạn chế việc đặt một số dấu câu ở đầu/cuối dòng.
- **Các hệ chữ có dấu kết hợp và cụm phức tạp:** không nên cắt giữa grapheme cluster hoặc orthographic syllable.
- **Tiếng Ả Rập/Do Thái (RTL):** có quy tắc ngắt từ, đồng thời còn phải xử lý thứ tự hiển thị BiDi.

Các ký tự không ngắt như **NO-BREAK SPACE** U+00A0, **NARROW NO-BREAK SPACE** U+202F và **WORD JOINER** U+2060 có thể ảnh hưởng break opportunity. Chúng thường có vai trò trong con số, tên riêng hoặc dấu câu; đừng thay toàn bộ bằng ASCII space trước khi layout.

**Chỉ dùng kỹ thuật đo text + wrapping của framework** khi đã xác nhận nó hỗ trợ các ngôn ngữ mục tiêu. Một thuật toán tự làm dựa trên số `char` hoặc dấu cách dễ phá dấu tổ hợp, emoji ZWJ, RTL và ngữ pháp văn bản.

## 6. `BreakIterator.getLineInstance`: tìm vị trí có thể ngắt, không quyết định số dòng cuối

Java SE có:

```java
BreakIterator iterator =
        BreakIterator.getLineInstance(locale);
iterator.setText(text);
```

Đây là đoạn code trong một phương thức, cần `import java.text.BreakIterator;` và biến `locale`, `text`. `BreakIterator` trả **các vị trí ranh giới** theo kiểu line break, nhưng **không biết chiều rộng pixel**, không có thông tin font và **không tự bố trí các dòng trên màn hình**.

Để lấy từng đoạn giữa các ranh giới:

```java
int start = iterator.first();
for (int end = iterator.next();
        end != BreakIterator.DONE;
        start = end, end = iterator.next()) {
    String part = text.substring(start, end);
}
```

Cả `start` và `end` đều là **UTF-16 offsets** trong `String` nguồn. `BreakIterator.DONE` có giá trị `-1`; kiểm tra trước khi gọi `substring`. Phần mềm giao diện mới là nơi kết hợp những break opportunities này với đo width, shaping và container bounds để chọn những điểm nào thực sự trở thành dòng mới.

### Ví dụ Java 17+: chỉ liệt kê break opportunities

Tạo file `LineBreakOpportunitiesDemo.java`:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class LineBreakOpportunitiesDemo {
    public static void main(String[] args) {
        String text = "Hello world again";
        BreakIterator it =
                BreakIterator.getLineInstance(Locale.US);
        it.setText(text);

        int start = it.first();
        for (int end = it.next();
                end != BreakIterator.DONE;
                start = end, end = it.next()) {
            System.out.println("[" + start + "," + end + ")="
                    + text.substring(start, end));
        }
    }
}
```

```bash
javac LineBreakOpportunitiesDemo.java
java LineBreakOpportunitiesDemo
```

Stdout theo dữ liệu `Locale.US` đã đối chiếu:

```text
[0,6)=Hello 
[6,12)=world 
[12,17)=again
```

Ở đây `[0,6)` có dấu cách sau `Hello`, và `[6,12)` có dấu cách sau `world`. Những đoạn này là **đơn vị từ phân tích line-break**, không phải ba dòng cuối cùng của UI. Trong một container rộng, toàn bộ chuỗi có thể nằm một dòng; trong container hẹp, nó có thể ngắt thành nhiều dòng.

**Không lưu các dấu xuống dòng được tính từ `BreakIterator` vào nội dung dịch** chỉ vì bố cục ở một viewport cụ thể; lần sau khi đổi font/cửa sổ, vị trí ngắt có thể khác.

## 7. UI framework chịu trách nhiệm gì?

Để một bản dịch dài vẫn hiển thị đầy đủ, lớp giao diện cần quản lý các yếu tố sau:

1. **Layout co giãn:** ưu tiên kích thước do component yêu cầu, min/max hợp lý và layout managers; không hardcode cùng một width cho mọi locale.
2. **Wrap thích hợp:** cho text nhiều dòng khi phù hợp với semantic và không gian.
3. **Chiều cao thích ứng:** khi text thành hai/ba dòng, container tăng chiều cao thay vì bị che mất.
4. **Khoảng cách:** padding, gap giữa icon và text, baseline alignment, line height; tính lại sau khi font/locale đổi.
5. **Overflow/truncation policy:** nếu buộc giới hạn không gian, phân biệt nơi cho wrap, scroll, collapse, ellipsis và nơi không được cắt.
6. **Text direction:** đặt LTR/RTL ở component/layout, không đảo chuỗi raw.
7. **Accessibility:** tôn trọng tăng kích thước chữ; đảm bảo có đường đọc toàn bộ nội dung (screen reader, expanded view, accessible description thích hợp).
8. **Reflow:** khi đổi locale, DPI, font hoặc kích thước cửa sổ, recompute layout; không cache width của bản dịch tiếng Anh.
9. **Input text:** nội dung do người dùng nhập có thể rất dài, chứa emoji/combining/RTL; không giả định chỉ các resource string mới cần xử lý.
10. **Kiểm thử trực quan:** test bản dịch ngắn, dài, những hệ chữ khác và nhiều viewport thực tế.

Những nguyên tắc này thuộc **presentation layer**. Resource bundle chứa dữ liệu ngôn ngữ, không nên chứa các con số pixel, trạng thái scroll, thông số component hay logic quyết định layout.

## 8. Java Swing: `JLabel` không tương đương `JTextArea`

Trong Swing, lựa chọn component có tác động trực tiếp đến wrapping.

| Component | Hành vi quan trọng | Khi nào cân nhắc |
| --- | --- | --- |
| `JLabel` | Thông thường hiển thị **một dòng plain text**; không tự wrap dài theo width như text area | Nhãn ngắn, tiêu đề có đủ không gian |
| `JTextArea` | Text nhiều dòng; `setLineWrap(true)` để wrap theo width; `setWrapStyleWord(true)` để ưu tiên boundary của từ | Đoạn mô tả/plain text nhiều dòng |
| `JTextPane` / `JEditorPane` | Nội dung styled/rich text, khả năng layout linh hoạt hơn | Nội dung định dạng phức tạp |
| `JScrollPane` | Cung cấp vùng cuộn khi nội dung vượt viewport | Nội dung dài mà vẫn phải đọc đủ |
| `JButton` | Nút hành động, kích thước tùy Look & Feel/font | Nút có label ngắn được thiết kế và kiểm thử |

`JTextArea.setLineWrap(false)` là mặc định của `JTextArea`. Nếu cần text tự xuống dòng trong vùng có width giới hạn, phải bật wrapping và đảm bảo component thực sự có **kích thước layout hợp lý**.

Lưu ý `setWrapStyleWord(true)` ưu tiên ranh giới từ khi có thể, nhưng **không phải cam kết đầy đủ** về mọi quy tắc line break của mọi hệ chữ/Unicode ở mọi Look & Feel. Với UI quốc tế phức tạp, cần kiểm thử hoặc dùng text layout engine thích hợp.

### Ví dụ Java 17+ có thể chạy kể cả môi trường không có màn hình

Tạo file `SwingWrapConfigurationDemo.java`:

```java
import java.awt.ComponentOrientation;
import java.util.Locale;
import javax.swing.JLabel;
import javax.swing.JTextArea;

public class SwingWrapConfigurationDemo {
    public static void main(String[] args) {
        String message = "Save changes before closing";

        JLabel label = new JLabel(message);
        JTextArea area = new JTextArea(message);

        System.out.println("label text: " + label.getText());
        System.out.println("default wrap: " + area.getLineWrap());

        area.setLineWrap(true);
        area.setWrapStyleWord(true);
        area.setEditable(false);
        System.out.println("wrap enabled: " + area.getLineWrap());
        System.out.println("word wrap enabled: "
                + area.getWrapStyleWord());

        Locale arabic = Locale.forLanguageTag("ar-EG");
        area.setComponentOrientation(
                ComponentOrientation.getOrientation(arabic));
        System.out.println("arabic LTR: "
                + area.getComponentOrientation().isLeftToRight());
    }
}
```

```bash
javac -encoding UTF-8 SwingWrapConfigurationDemo.java
java SwingWrapConfigurationDemo
```

Stdout:

```text
label text: Save changes before closing
default wrap: false
wrap enabled: true
word wrap enabled: true
arabic LTR: false
```

Đây là ví dụ **kiểm chứng thuộc tính của component**, chưa hiển thị cửa sổ. Nó không chứng minh một số dòng cụ thể sẽ hiện ra, vì việc wrap phụ thuộc **allocated width**, font và layout manager.

**Quan trọng:** `setEditable(false)` chỉ làm text không chỉnh sửa được; với text area dùng làm nhãn mô tả, có thể cần đặt thêm background, border, focus, accessible name và chính sách chọn text theo yêu cầu thiết kế. Không dùng nó như "nút chức năng" chỉ vì có cùng text.

## 9. Ví dụ giao diện Swing: để text tự giãn theo layout

Ví dụ hoàn chỉnh dùng `BorderLayout` và `JTextArea` có wrap, thay vì ghim chiều rộng của bản dịch vào resource. Tạo `LocalizedPanelDemo.java`:

```java
import java.awt.BorderLayout;
import java.awt.ComponentOrientation;
import java.awt.Dimension;
import java.util.Locale;
import javax.swing.JButton;
import javax.swing.JFrame;
import javax.swing.JPanel;
import javax.swing.JScrollPane;
import javax.swing.JTextArea;
import javax.swing.SwingUtilities;

public class LocalizedPanelDemo {
    public static void main(String[] args) {
        SwingUtilities.invokeLater(() -> {
            Locale locale = Locale.forLanguageTag("vi-VN");
            String description =
                    "Vui lòng kiểm tra các thay đổi của bạn trước khi "
                    + "đóng cửa sổ. Nội dung có thể tự xuống dòng "
                    + "khi người dùng thu hẹp cửa sổ.";

            JFrame frame = new JFrame("Localization layout");
            frame.setDefaultCloseOperation(JFrame.EXIT_ON_CLOSE);

            JTextArea message = new JTextArea(description);
            message.setEditable(false);
            message.setLineWrap(true);
            message.setWrapStyleWord(true);
            message.setOpaque(false);
            message.setBorder(null);

            JPanel content = new JPanel(new BorderLayout(12, 12));
            content.setBorder(
                    javax.swing.BorderFactory.createEmptyBorder(
                            16, 16, 16, 16));
            content.add(new JScrollPane(message),
                    BorderLayout.CENTER);
            content.add(new JButton("Đóng"), BorderLayout.PAGE_END);

            content.applyComponentOrientation(
                    ComponentOrientation.getOrientation(locale));

            frame.setContentPane(content);
            frame.setMinimumSize(new Dimension(240, 180));
            frame.setSize(460, 250);
            frame.setLocationRelativeTo(null);
            frame.setVisible(true);
        });
    }
}
```

Chạy trong môi trường **có giao diện đồ họa**:

```bash
javac -encoding UTF-8 LocalizedPanelDemo.java
java LocalizedPanelDemo
```

Chương trình mở cửa sổ Swing; không có stdout cố định. Khi kéo hẹp cửa sổ, text area có thể wrap theo chiều rộng vùng trung tâm, và `JScrollPane` giúp đọc nội dung nếu nó vượt không gian cho phép. Code được viết trên **Swing Event Dispatch Thread (EDT)** qua `SwingUtilities.invokeLater`.

**Giới hạn quan trọng của ví dụ:** một UI thực cần thêm xử lý accessibility, keyboard navigation, font fallback, đổi locale khi đang chạy, resource bundle thay vì hardcode tiếng Việt, nút thực sự có action phù hợp, và kiểm thử trên Look & Feel mục tiêu. Không xem ví dụ minh họa một cửa sổ là bộ layout sản phẩm hoàn chỉnh.

**Không ấn định một chiều cao cố định cho tất cả nhãn** chỉ vì ví dụ có kích thước khởi tạo cửa sổ. Kích thước này là mặc định ban đầu, không phải chiều dài tối đa của câu dịch. Nếu sản phẩm cần layout không cuộn, phải chọn component/container có thể tăng chiều cao theo số dòng và kiểm thử lại.

## 10. `JLabel`, HTML và những giới hạn thực tế

`JLabel` plain text thông thường là một dòng. Swing có khả năng render một **tập con HTML** trong một số component khi text bắt đầu bằng `<html>`, ví dụ:

```java
JLabel label = new JLabel(
        "<html>Đây là đoạn mô tả<br>có xuống dòng.</html>");
```

Đây là **đoạn code minh họa trong phương thức**, cần `import javax.swing.JLabel;`. `<br>` ở đây là thẻ HTML dùng bởi Swing HTML renderer, không phải `\n` trong resource thuần.

Nhưng không nên lấy bản dịch do người dùng nhập hoặc từ nguồn không đáng tin rồi chèn trực tiếp vào HTML: phải xử lý escaping/validation theo mô hình render. Việc đẩy `<br>` và style vào chuỗi bản dịch còn có thể trộn **ngữ nghĩa nội dung** với **đặc tính giao diện**, làm tăng độ khó bảo trì.

Nếu muốn tự wrap theo width và tăng chiều cao trong Swing, thường cân nhắc component nhiều dòng/layout thích hợp thay vì "bơm" vô số `<br>` vào `JLabel`. Khi dùng HTML, hãy kiểm thử subset tag được Swing hỗ trợ và cách layout cập nhật, vì nó không phải trình duyệt web hiện đại.

## 11. Tách tài nguyên ngôn ngữ khỏi quyết định layout

Resource bundle nên mô tả **văn bản và biến thể nội dung**, không lưu một bản sao bị chèn newline chỉ để phù hợp kích thước màn hình:

```properties
dialog.close.title=Đóng cửa sổ
dialog.close.description=Vui lòng lưu các thay đổi trước khi đóng.
dialog.close.action=Đóng
```

Trong UI:

- `title` được gán vào tiêu đề hoặc label phù hợp.
- `description` dùng component có thể wrap.
- `action` là nhãn của nút có kích thước linh hoạt và sự kiện.
- Placeholder số, ngày tháng, tên riêng được format theo locale trước khi đặt vào giao diện.

Đây là ví dụ `.properties` tiếng Việt nhằm minh họa cấu trúc khóa; thực tế tên bundle và locale suffix do dự án quyết định.

### Khi nào bản dịch nên chứa `\n`?

Có trường hợp **nội dung cần xuống dòng cố định** và đó là một phần của nghĩa. Ví dụ bản dịch là lời chào nhiều đoạn, thông điệp có hai đoạn có chủ đích, hoặc địa chỉ được thiết kế thành nhiều dòng. Khi dùng `.properties`:

```properties
message.long=Đoạn thứ nhất.\nĐoạn thứ hai.
```

Parser `.properties` chuyển escape `\n` thành newline trong chuỗi Java. Lớp UI phải sử dụng component hiển thị nhiều dòng; `JLabel` plain text không tự trở thành text area chỉ vì chuỗi chứa `\n`.

Không dùng escape `\n` giữa từng nhóm từ chỉ để cố định "mỗi dòng 20 ký tự", vì font, ngôn ngữ và viewport sẽ thay đổi.

**Phân biệt semantic structure và visual lines:** nội dung nên có paragraph/list fields nếu cần cấu trúc, còn số dòng cuối cùng là kết quả layout. Với bản dịch có nhiều ngữ cảnh hiển thị, cân nhắc nhiều key/tài nguyên được định nghĩa rõ mục đích hơn là dùng chung một text rồi thay newline theo nơi gọi.

## 12. Kịch bản placeholder, số nhiều và độ dài tăng đột biến

Không chỉ bản dịch tĩnh, các thông điệp có dữ liệu runtime còn có thể dài bất ngờ:

```text
"Đã lưu tài liệu"
"Đã lưu tài liệu Báo cáo tổng hợp kết quả kinh doanh quý IV..."
```

Tên tệp, tên người, đường dẫn, địa chỉ email, mã đơn hàng hoặc lượng tiền có thể làm text dài vượt dự kiến. Hệ thống còn phải xét:

- tên file có ký tự CJK không có space;
- số lượng danh sách và tên riêng rất dài;
- ngày được format đầy đủ tên tháng;
- mẫu câu plural/gender thay đổi theo biến số;
- escape text hoặc markup làm thay đổi kích thước nếu render khác.
  
Ví dụ: `ResourceBundle` + `MessageFormat` có thể tạo văn bản đúng nghĩa; nó **không chịu trách nhiệm chọn chỗ ngắt và chiều rộng nút**. Message formatter nên tạo **chuỗi có ngữ nghĩa**, lớp layout mới phân tích và trình bày.

Nên đặt **giới hạn dữ liệu theo domain** (ví dụ tên nhập tối đa N grapheme/bytes nếu có lý do) chứ không đặt giới hạn tùy tiện vào tài nguyên dịch. Nếu UI không thể hiển thị hết, quyết định overflow policy riêng cho loại nội dung.

## 13. RTL: không đảo chuỗi và không hardcode vị trí icon

Một UI đa ngôn ngữ có thể phục vụ tiếng Ả Rập hoặc tiếng Do Thái, viết theo hướng từ phải sang trái (RTL). Trách nhiệm của lớp giao diện ở đây không chỉ là xuống dòng.

- Hướng paragraph và các đoạn trộn LTR/RTL tuân theo Unicode Bidirectional Algorithm.
- Các thành phần như back navigation, biểu tượng chỉ hướng và thứ tự trường có thể cần được mirror theo design system.
- Số, URL, mã sản phẩm và các từ Latin nằm trong đoạn RTL cần text shaping/BiDi engine.
- Không áp dụng `new StringBuilder(text).reverse()` để "hỗ trợ RTL".
- Không chèn các ký tự điều khiển BiDi vô tội vạ vào resource nếu framework đã có cơ chế xác định hướng; với trường hợp embedding dữ liệu chưa biết hướng, áp dụng cơ chế bidi isolation đúng nền tảng.

Swing có `java.awt.ComponentOrientation`:

```java
Locale locale = Locale.forLanguageTag("ar-EG");
ComponentOrientation orientation =
        ComponentOrientation.getOrientation(locale);
component.applyComponentOrientation(orientation);
```

Đây là đoạn mã minh họa trong một phương thức, cần `Locale` và `ComponentOrientation` cũng như `component` đã khai báo.

**Chú ý:** `ComponentOrientation` định hướng bố cục của component, nhưng không phải bảo đảm mọi chữ, icon, tooltip, popup và layout manager đều tự hoạt động đúng cho RTL. Cần test thực tế với thư viện giao diện và Look & Feel đang sử dụng.

### Ví dụ Java 17+ về orientation

Tạo file `OrientationDemo.java`:

```java
import java.awt.ComponentOrientation;
import java.util.Locale;

public class OrientationDemo {
    public static void main(String[] args) {
        for (String tag :
                new String[] {"en-US", "vi-VN", "ar-EG", "he-IL"}) {
            Locale locale = Locale.forLanguageTag(tag);
            boolean ltr = ComponentOrientation
                    .getOrientation(locale).isLeftToRight();
            System.out.println(tag + ": " + ltr);
        }
    }
}
```

```bash
javac OrientationDemo.java
java OrientationDemo
```

```text
en-US: true
vi-VN: true
ar-EG: false
he-IL: false
```

Đây chỉ là thuộc tính hướng **của component đối với locale** theo Java, không thay thế việc render một paragraph BiDi trộn chữ.

## 14. Truncate / ellipsis: giải pháp dự phòng, không phải mặc định

Có màn hình thật sự có giới hạn diện tích: tab bar, biểu đồ, cột bảng rất hẹp, toast ngắn. Khi đó ứng dụng có thể cắt văn bản và thêm `…`, nhưng cần chính sách rõ ràng.

### 14.1. Những rủi ro khi cắt theo `char`

`String.substring(0, maxLength)` cắt theo **UTF-16 code units**, có thể làm hỏng một emoji supplementary nếu cắt giữa surrogate pair. Ngay cả `offsetByCodePoints` chỉ tránh cắt surrogate, vẫn có thể chia một **grapheme** gồm chữ với combining mark, emoji ZWJ hoặc skin tone modifier.

Nếu yêu cầu là cắt theo số "ký tự người dùng nhìn thấy", hãy chọn thuật toán grapheme segmentation. Java 17 hỗ trợ regex `\X` cho extended grapheme cluster; trong Java string literal viết `"\\X"`. Với ứng dụng có giới hạn **pixel**, còn phải đo chiều rộng sau shaping và wrapping, không chỉ đếm grapheme.

### 14.2. Đo pixel và chọn chỗ cắt

Quy trình khái niệm:

1. Đo kích thước text bằng đúng font, tỷ lệ DPI, hướng chữ, renderer và viewport.
2. Nếu vừa, hiển thị nguyên văn.
3. Nếu không vừa và component được phép nhiều dòng, ưu tiên wrap.
4. Nếu không được wrap, cân nhắc scroll, expand hoặc ellipsis.
5. Nếu dùng ellipsis, cắt theo ranh giới Unicode phù hợp và **đo lại** cả chuỗi `prefix + ellipsis`.
6. Với RTL/BiDi, hướng ellipsis và vị trí dấu cắt cần framework/UX xử lý đúng.
7. Giữ cách truy cập nội dung đầy đủ nếu thông tin quan trọng; tooltip là một kênh bổ sung chứ không phải cách duy nhất.

**Không nên cắt những thông tin quyết định** như điều khoản pháp lý, lời cảnh báo an toàn, số tiền, lỗi cần người dùng xử lý hoặc nút hành động có thể hiểu nhầm. Với nhãn quan trọng không vừa, thiết kế lại layout/label thay vì ép tối đa 8 ký tự bằng code.

### 14.3. Một đoạn mã an toàn ở mức grapheme

```java
static String truncateClusters(String s, int maxClusters) {
    if (maxClusters < 0) {
        throw new IllegalArgumentException("maxClusters");
    }
    java.util.regex.Matcher m =
            java.util.regex.Pattern.compile("\\X").matcher(s);
    int end = 0;
    int count = 0;
    while (count < maxClusters && m.find()) {
        end = m.end();
        count++;
    }
    return s.substring(0, end);
}
```

Đây là **phương thức minh họa**, cần đặt trong một lớp Java. Nó trả prefix gồm tối đa N grapheme clusters theo dữ liệu Unicode của JDK, **không tự thêm ellipsis** và **không đo pixel**. Khi dùng `m.end()` để cắt `String`, offset trả về là UTF-16 và phù hợp với `substring`.

Chú ý: nếu `maxClusters==0` kết quả là chuỗi rỗng; nếu text ít cụm hơn giới hạn, trả toàn bộ text. Bộ quy tắc Unicode/grapheme có thể được cập nhật trong các phiên bản runtime, nên cần test khi giới hạn ký tự là một hợp đồng sản phẩm quan trọng.

## 15. Unicode line breaking và khác biệt giữa "ký tự" và "đoạn từ"

Để hiểu trách nhiệm của text engine, cần tách ba khái niệm:

| Khái niệm | Công dụng | Lỗi phổ biến |
| --- | --- | --- |
| Grapheme boundary | Không tách một cụm ký tự hiển thị | Cắt trước modifier/dấu kết hợp |
| Word boundary | Xác định đoạn liên quan đến từ/từ tố theo locale | Coi mọi dấu cách đều là ranh giới từ duy nhất |
| Line-break opportunity | Chỗ có thể xuống dòng hợp quy tắc chữ viết | Coi mọi opportunity là newline bắt buộc |

Một cụm Unicode có thể không được tách giữa dòng dù có nhiều code points; ngược lại, một câu có thể chứa nhiều ranh giới dòng. Line-break engine còn phải cân nhắc dấu câu cấm đứng đầu/cuối dòng. Một số ngôn ngữ cần hỗ trợ hyphenation hoặc dictionary segmentation.

Trên Java, `BreakIterator.getLineInstance(locale)` cho danh sách ranh giới, nhưng nhiều UI framework có bộ layout khác, và chất lượng cuối cùng phụ thuộc engine/font/provider. **Không cố dùng một chuỗi nối bằng `\n` từ backend để "vẽ layout" hộ frontend**.

## 16. Kiểm thử pseudo-localization và nhiều kích thước UI

Chỉ test tiếng Anh trên màn hình rộng sẽ bỏ qua phần lớn lỗi. Một kế hoạch kiểm thử thực tế nên gồm:

| Nhóm kiểm thử | Dữ liệu | Điều cần quan sát |
| --- | --- | --- |
| Chuỗi ngắn/dài | Nhãn 4 ký tự và đoạn văn dài | Không overlap/truncate sai |
| Pseudo-localization | Bản dịch nhân độ dài, thêm ký tự có dấu | Container reflow |
| Font scaling | 100%, 150%, 200% | Không che nội dung/tác vụ |
| Viewport | Cửa sổ rộng, hẹp, phóng to | Wrap/scroll/resizing |
| CJK | Tiếng Trung/Nhật, text không có space | Line breaks, dấu câu |
| Đông Nam Á | Tiếng Thái/Khmer, tiếng Việt | Segmentation |
| RTL | Tiếng Ả Rập/Do Thái, trộn Latin/number | Bidi, alignment, icon mirroring |
| Unicode | Combining marks, emoji ZWJ, flags | Grapheme-safe truncation |
| Dynamic data | Tên file/tên người/đường dẫn rất dài | Không đẩy nút ra ngoài |
| Plural/gender | Các nhánh khác nhau trong cùng resource | Chiều dài thay đổi theo runtime |
| Accessibility | Screen reader, keyboard-only, large fonts | Nội dung vẫn tiếp cận được |
| Printing/export | PDF/report/ảnh chụp từ UI | Xuống dòng và trang không cắt sai |

**Pseudo-localization không thay thế review của người bản ngữ.** Nó tốt để tìm vấn đề cơ khí layout, còn bản dịch thật phải được đánh giá tự nhiên, ngữ pháp và khả năng đọc.

### Không đánh giá chỉ bằng ảnh chụp một thiết bị

Khi text vừa ở một kích thước cụ thể, chưa có nghĩa layout đạt yêu cầu. Cần test nhiều độ rộng và font scaling; nếu test automated UI screenshot, lưu ý font fallback, anti-aliasing, DPI và hệ điều hành có thể làm khác biệt pixel. Dùng cả automated constraints và kiểm tra accessibility, thay vì chỉ pixel-perfect của một locale duy nhất.

## 17. Kiến trúc gợi ý: Domain → i18n → UI layout

```text
Domain value (count, date, username...)
             |
             v
i18n/message formatting:
  - Chọn resource theo locale
  - Chọn plural/select branch
  - Format số/ngày giờ
  - Trả về thông điệp đầy đủ
             |
             v
UI text/layout engine:
  - Resolve font, direction, width, DPI
  - Tính line-break opportunities
  - Wrap, tăng height/scroll, baseline
  - Xử lý overflow/ellipsis nếu cần
             |
             v
Rendered UI + accessibility
```

### Ranh giới trách nhiệm

**Domain layer** giữ giá trị thực, không lưu text đã thêm newline theo pixel. **Localization layer** chuyển giá trị thành văn bản đúng nghĩa, phù hợp locale, có placeholders và cấu trúc nội dung. **Presentation layer** quyết định vị trí, kích thước và cách hiển thị. **Accessibility layer** cần đọc được văn bản và ngữ nghĩa ngay cả khi UI đang thu gọn/ellipsis.

Ví dụ: khi đổi cửa sổ từ 460px xuống 280px, **resource bundle không cần thay đổi**; layout engine nên tính lại ranh giới và số dòng. Chỉ khi sản phẩm có **biến thể nội dung thực sự khác**, ví dụ nhãn ngắn trong tab, mới cần key riêng được biên tập và dịch độc lập.

## 18. Những sai lầm phổ biến

| Sai lầm | Hệ quả | Hướng khắc phục |
| --- | --- | --- |
| Kích thước nút vừa đúng nhãn tiếng Anh | Bản dịch dài bị cắt | Layout thích ứng, ưu tiên preferred sizes |
| Bắt người dịch rút gọn tới số ký tự cố định | Dễ mất nghĩa, trái ngữ pháp | Thiết kế short variant có chủ đích nếu cần |
| Dùng `text.length()` để suy chiều rộng | UTF-16 units khác glyph width | Đo bằng font/text layout engine |
| Chèn `\n` để chữa lỗi ở viewport hiện tại | Cửa sổ khác vẫn bị ngắt gượng ép | UI soft wrapping |
| Dịch và nối từng mảnh câu | Khó đổi trật tự từ, sai ngữ pháp | Một message hoàn chỉnh với placeholders |
| Tách dòng chỉ theo space | Sai ở CJK/Thai/Khmer, một số dấu câu | Unicode line break/locale-aware engine |
| Coi `BreakIterator` là renderer | Không biết pixel/width/font | Để UI quyết định soft wrap |
| Giả định `JLabel` plain text tự wrap | Text dài tràn một dòng | Chọn JTextArea/multi-line component |
| Quên bật `JTextArea.setLineWrap` | Dòng không tự xuống | Bật wrap và cấp viewport đúng |
| Dùng chung string với CSS/HTML/markup tùy ý | Trộn content với presentation | Tách dữ liệu và render; escape an toàn |
| Đảo text để hỗ trợ RTL | Sai logical order và BiDi | Component orientation, Unicode bidi |
| Truncate theo `substring(0,n)` | Xé surrogate/grapheme, mất nghĩa | Grapheme boundaries + width measurement |
| Dùng tooltip làm cách duy nhất xem text đầy đủ | Không đảm bảo accessibility | Có view/description tương thích assistive tech |
| Chỉ test desktop tiếng Anh | Không thấy overflow ở locale khác | Pseudo-localization, CJK, RTL, font scaling |
| Hardcode font size nhỏ để ép chữ | Khó đọc, vi phạm khả năng truy cập | Hỗ trợ text scaling và reflow |
| Giới hạn label vì data động không dự kiến | Tên/đường dẫn dài làm hỏng UI | Overflow policy và domain validation |

## 19. Câu hỏi tự kiểm tra

1. **Vì sao dịch từ `Settings` sang `Einstellungen` có thể làm hỏng nút?** Vì nút đặt width cố định cho một nhãn; đó chủ yếu là lỗi UI layout.
2. **Có quy tắc mọi bản dịch luôn dài hơn tiếng Anh theo cùng tỷ lệ không?** Không; độ dài phụ thuộc nội dung, ngữ pháp, script, font.
3. **`String.length()` có đủ để biết text vừa 120px không?** Không; nó đếm UTF-16 code units, không đo glyph width.
4. **Soft wrap khác `\n` ra sao?** Soft wrap là quyết định render theo width; `\n` thực sự là ký tự trong nội dung.
5. **Có khi nào `\n` trong resource là đúng không?** Có, khi ranh giới đoạn/dòng là một phần ngữ nghĩa được biên tập.
6. **Ai chịu trách nhiệm cho chỗ xuống dòng khi người dùng thu hẹp cửa sổ?** Text renderer/UI layout, không phải người dịch cố định vị trí dấu xuống dòng.
7. **Vì sao không dùng `split(" ")` để wrap mọi ngôn ngữ?** Nhiều hệ chữ không dùng space làm delimiter từ; dấu câu và combining marks có quy tắc riêng.
8. **`BreakIterator.getLineInstance` biết chiều rộng màn hình không?** Không; nó trả break opportunities, không tính số dòng hiển thị.
9. **`JTextArea` có tự wrap theo mặc định không?** Không; `setLineWrap(false)` là mặc định.
10. **`setWrapStyleWord(true)` có thay thế engine line breaking đầy đủ cho mọi locale không?** Không, phải kiểm thử framework/provider.
11. **Một chuỗi chứa emoji ZWJ cần truncate thế nào?** Cắt theo grapheme boundaries và đo lại width nếu giới hạn pixel.
12. **Có nên đảo `String` để hiển thị tiếng Ả Rập từ phải qua trái không?** Không; để BiDi và layout engine xử lý logical vs visual order.
13. **Muốn một nhãn ngắn trong tab bar thì có thể thêm key riêng không?** Có nếu product/content thiết kế short variant có mục đích, được dịch và kiểm thử.
14. **Vì sao phải test font scaling 200%?** Text có thể wrap nhiều dòng và cần container tăng height để nội dung không bị che.
15. **Nếu hiển thị một câu lỗi quan trọng bị ellipsis, tooltip có đủ không?** Thường không; cần đường truy cập nội dung đầy đủ và accessibility.
16. **Nếu backend đã gửi một chuỗi có hard newline sau mỗi 20 ký tự, nên làm gì?** Xem lại hợp đồng content, bỏ ngắt dòng do pixel/đếm ký tự nếu không có nghĩa; để UI tự wrap.
17. **Với chữ Pháp có U+202F, có nên thay mọi khoảng trắng bằng U+0020 trước khi wrap không?** Không; nonbreaking spacing có thể cần giữ.
18. **Khi nào phép thử pseudo-localization hữu ích?** Phát hiện container cắt, thiếu reflow, text direction, trường hợp ký tự mở rộng trước khi dịch thực tế hoàn tất.

## Tài liệu tham khảo

- [Java SE 17 — JTextArea](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/javax/swing/JTextArea.html): `setLineWrap`, `setWrapStyleWord` và text wrapping.
- [Java SE 17 — JLabel](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/javax/swing/JLabel.html): label text mặc định một dòng.
- [Java SE 17 — BreakIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/BreakIterator.html): line-break boundaries theo locale.
- [Java SE 17 — ComponentOrientation](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/ComponentOrientation.html): hướng LTR/RTL cho UI.
- [Java SE 17 — FontMetrics](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/FontMetrics.html): đo chữ theo font.
- [Java SE 17 — Pattern](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html): `\X` (extended grapheme clusters).
- [W3C Internationalization — Approaches to Line Breaking](https://www.w3.org/International/articles/typography/linebreak.en.html): cách ngắt dòng theo hệ chữ, CJK, Thai, RTL, punctuation.
- [Unicode UAX #14 — Unicode Line Breaking Algorithm](https://www.unicode.org/reports/tr14/): các cơ hội xuống dòng và quy tắc Unicode.
- [Unicode UAX #29 — Unicode Text Segmentation](https://www.unicode.org/reports/tr29/): phân đoạn grapheme/word.
- [W3C Internationalization — CSS3 and International Text](https://www.w3.org/International/articles/css3-text/index): nguyên tắc line breaking và wrapping đa hệ chữ.
