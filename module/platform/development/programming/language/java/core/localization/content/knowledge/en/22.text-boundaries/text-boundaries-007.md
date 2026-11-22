# Ngắt dòng theo ngôn ngữ và bố trí theo chiều rộng giao diện trong Java

## 1. Hai câu hỏi khác nhau khi văn bản phải xuống dòng

Một đoạn văn dài cần được chia thành nhiều dòng để hiển thị trong card, cửa sổ, hộp thoại, tài liệu hoặc báo cáo. Nhưng “xuống dòng” thực ra bao gồm **hai quyết định không giống nhau**:

1. **Ngữ nghĩa/ngôn ngữ:** Những vị trí nào trong chuỗi là **ranh giới được phép ngắt dòng** theo quy tắc ngôn ngữ và Unicode? Có được ngắt ở khoảng trắng, giữa hai chữ Hán, trước dấu câu, giữa các phần của emoji hoặc trong một từ tiếng Thái không?
2. **Bố trí giao diện:** Với **độ rộng thực tế**, font, cỡ chữ, kerning, shaping, khoảng cách, direction và không gian sẵn có, **nên chọn vị trí ngắt nào** để dòng vừa vùng vẽ?

Trong Java, hai API thường biểu diễn hai vai trò này:

- `java.text.BreakIterator.getLineInstance(Locale)`: xác định **các vị trí có thể ngắt dòng** trong một chuỗi theo locale, **không nhận chiều rộng của vùng hiển thị**.
- `java.awt.font.LineBreakMeasurer`: tạo các đoạn `TextLayout` **vừa một wrapping width**, có cân nhắc phép đo chữ của Java 2D và những điểm ngắt. Nó cần font/attributes và `FontRenderContext`, và có thể nhận `BreakIterator` do ứng dụng chỉ định.

**Điểm cốt lõi:** `BreakIterator` không thể biết một hộp rộng 120 px hay 480 px. Ngược lại, tính toán chiều rộng mà bỏ qua quy tắc ngắt theo ngôn ngữ có thể xé từ, tách cụm ký tự hoặc đặt dấu câu sai chỗ.

### Mục tiêu học tập

Sau bài này, bạn có thể phân biệt ranh giới ngắt “hợp lệ” với quyết định “vừa độ rộng”, sử dụng `BreakIterator.getLineInstance(locale)`, hiểu cách `LineBreakMeasurer` và `TextLayout` làm việc, chọn nơi nên xử lý wrapping trong Swing/Java 2D hoặc frontend, và tránh nhầm `String.length()` với độ rộng hiển thị.

## 2. Bốn mức ranh giới trong văn bản

Java có `BreakIterator` cho nhiều loại phân đoạn, mỗi loại phục vụ một câu hỏi riêng:

| Factory | Câu hỏi | Dùng khi |
| --- | --- | --- |
| `BreakIterator.getCharacterInstance(locale)` | Ranh giới cụm ký tự để thao tác con trỏ/cắt theo ký tự | Di chuyển caret, chọn text; cần kiểm thử Unicode mới |
| `BreakIterator.getWordInstance(locale)` | Ranh giới từ/đơn vị được bộ tách từ nhận biết | Highlight, thao tác theo từ, tìm kiếm sơ bộ |
| `BreakIterator.getLineInstance(locale)` | Những điểm **có thể ngắt dòng** | Line wrapping theo ngôn ngữ |
| `BreakIterator.getSentenceInstance(locale)` | Ranh giới câu | Phân tích/trình bày theo câu |

Không hoán đổi những factory này:

- **Word boundary** không đồng nghĩa **line-break opportunity**.
- **Character boundary** không có nghĩa được phép xuống dòng ở đó trong một đoạn văn.
- **Sentence boundary** không có nghĩa UI phải tạo một dòng mới ở cuối mọi câu.
- **Line-break boundary** không quyết định UI thực sự xuống dòng ở vị trí ấy.

Bốn thao tác đều liên quan văn bản nhưng chúng có ý nghĩa khác nhau. Một ứng dụng muốn làm nổi bật từng từ không nên dùng line-break iterator để thay thế bộ xử lý từ; một ứng dụng muốn xuống dòng tự nhiên không nên cứ sau mỗi code point là tạo dòng mới.

### Thuật ngữ: opportunity, soft wrap, hard break

- **Line-break opportunity:** một vị trí có thể dùng để ngắt theo quy tắc ngôn ngữ.
- **Soft wrap:** xuống dòng do **thiếu chiều rộng**; không nhất thiết chèn ký tự newline vào chuỗi dữ liệu gốc.
- **Hard break/explicit break:** người viết dữ liệu đã chèn newline hoặc separator với ý định tạo dòng/đoạn mới.
- **Overflow:** đoạn không thể chia phù hợp nhưng cũng không vừa width; UI phải có chính sách cuộn, cắt, ngắt cưỡng bức hoặc hiển thị khác.
- **Hyphenation:** ngắt một từ tại vị trí hợp lệ và có thể chèn dấu nối; là một khả năng ngôn ngữ riêng, không mặc nhiên được mọi formatter Java xử lý đầy đủ.

Một line-break iterator có thể trả nhiều điểm cho phép ngắt trong khi UI chọn **không** ngắt điểm nào vì toàn bộ dòng vẫn vừa.

## 3. Vì sao ngắt dòng phụ thuộc ngôn ngữ?

Mỗi ngôn ngữ và hệ chữ có quy ước khác nhau:

| Ngữ cảnh | Điều thường phải cân nhắc |
| --- | --- |
| Tiếng Anh và nhiều ngôn ngữ dùng khoảng trắng | Ưu tiên ngắt giữa các từ, tránh đặt dấu câu sát sai vị trí |
| Tiếng Việt | Khoảng trắng thường ngăn cách âm tiết; tách dòng đúng chưa chắc tương đương tách từ về mặt ngữ nghĩa |
| Tiếng Nhật | Có thể ngắt giữa các ký tự nhất định, nhưng nhiều cặp dấu/cụm nhỏ bị quy tắc kinsoku ràng buộc |
| Tiếng Trung | Thường không dùng khoảng trắng giữa từ; quy tắc dấu câu và loại ký tự quan trọng |
| Tiếng Thái và Khmer | Có thể viết nhiều từ không có khoảng trắng; cần thuật toán/từ điển hoặc dữ liệu ngôn ngữ phù hợp |
| Tiếng Ả Rập/Hebrew | Ngoài điểm ngắt còn cần xử lý text direction và shaping |
| Emoji/chuỗi có dấu kết hợp | Tránh xé đôi grapheme cluster, surrogate pair hoặc emoji ghép |
| URL/đường dẫn/tên định danh dài | Có thể cần policy cho chuỗi khó tìm chỗ ngắt hợp lệ |

**Không phải mọi khoảng trắng đều cho phép ngắt.** Ví dụ U+00A0 NO-BREAK SPACE nhằm ngăn cách một số thành phần nhưng không cho tách tại chỗ ấy theo quy tắc thông thường. Ngược lại, U+200B ZERO WIDTH SPACE có thể đánh dấu cơ hội ngắt mà không hiện khoảng trắng.

**Không phải mọi dấu gạch nối đều bắt buộc xuống dòng.** Dấu nối thông thường có thể ảnh hưởng cơ hội ngắt; soft hyphen U+00AD là gợi ý có điều kiện, và hiển thị dấu nối khi ngắt phụ thuộc engine. Không nên giả định `BreakIterator` của JDK tự cung cấp hyphenation chuẩn cho mọi ngôn ngữ hay tự chèn ký tự dấu nối vào text.

### Quy tắc Unicode không phải nguyên lý “sau mỗi code point đều được ngắt”

Unicode Standard Annex #14 định nghĩa Unicode Line Breaking Algorithm, gồm các lớp line-breaking và nhiều quy tắc cho phép/cấm ngắt. Các engine có thể áp dụng thêm tailoring theo locale hoặc dữ liệu từ điển. Điều này giải thích vì sao dùng một regex kiểu `"\\s+"` hoặc `String.split(" ")` thường không đủ cho tiếng Trung, tiếng Nhật, tiếng Thái và ký tự đặc biệt.

Các thuật toán/bộ dữ liệu của Java có thể thay đổi theo phiên bản JDK, CLDR/provider và hỗ trợ locale. Vì vậy, khi một sản phẩm yêu cầu dòng xuống ở chính xác từng chỗ cho một ngôn ngữ cụ thể, cần kiểm thử **trên runtime và rendering engine thực tế**.

## 4. BreakIterator.getLineInstance(Locale): tìm điểm được phép ngắt

API cơ bản:

```java
Locale locale = Locale.forLanguageTag("vi-VN");

BreakIterator breaker =
        BreakIterator.getLineInstance(locale);

breaker.setText("Một đoạn văn tiếng Việt để kiểm tra ngắt dòng.");
```

`BreakIterator` dùng **offset trong chuỗi UTF-16**. Gọi `first()` lấy điểm đầu, `next()` lần lượt lấy các ranh giới và trả `BreakIterator.DONE` khi hết. `last()` cho ranh giới cuối của phạm vi.

Một vòng duyệt điển hình:

```java
int start = breaker.first();

for (int end = breaker.next();
        end != BreakIterator.DONE;
        start = end, end = breaker.next()) {

    String segment = text.substring(start, end);
    // Một đoạn giữa hai cơ hội ngắt liên tiếp.
    // CHƯA phải một dòng sau khi bố trí theo chiều rộng.
}
```

Đây là đoạn minh họa trong method với `text` và `breaker` đã được khai báo. Những `segment` được trả về là các vùng giữa các ranh giới, **không** phải “các dòng” mà UI chắc chắn sẽ hiển thị.

### Các phương thức hữu ích

| Phương thức | Vai trò |
| --- | --- |
| `getLineInstance(locale)` | Tạo line-break iterator theo locale |
| `setText(String)` | Gán đoạn text cần phân tích |
| `first()` / `last()` | Về ranh giới đầu/cuối |
| `next()` / `previous()` | Duyệt qua các ranh giới |
| `following(offset)` | Ranh giới đầu tiên **sau** offset |
| `preceding(offset)` | Ranh giới cuối cùng **trước** offset |
| `isBoundary(offset)` | Kiểm tra offset có là ranh giới không |
| `current()` | Vị trí hiện tại, có thể thay đổi khi gọi API |
| `BreakIterator.DONE` | Giá trị báo đã hết ranh giới |

**Lưu ý:** `isBoundary` và các phép tìm ranh giới có thể thay đổi vị trí duyệt nội bộ. Nếu cần lưu vị trí của vòng lặp, quản lý riêng start/end hoặc tạo iterator/clone phù hợp.

### 4.1. Java 17 runnable: chứng minh line boundaries không phải viewport lines

Tệp `LineBoundaryDemo.java`:

```java
import java.text.BreakIterator;
import java.util.Locale;

public class LineBoundaryDemo {
    public static void main(String[] args) {
        String text = "Hello world, welcome to Java.";

        BreakIterator breaker =
                BreakIterator.getLineInstance(Locale.US);
        breaker.setText(text);

        int start = breaker.first();
        int end = breaker.last();

        System.out.println("startAtZero=" + (start == 0));
        System.out.println("endAtLength=" +
                (end == text.length()));
        System.out.println("startBoundary=" +
                breaker.isBoundary(0));
        System.out.println("endBoundary=" +
                breaker.isBoundary(text.length()));

        int previous = breaker.first();
        int opportunities = 0;
        boolean increasing = true;

        for (int next = breaker.next();
                next != BreakIterator.DONE;
                next = breaker.next()) {

            increasing &= next > previous;
            previous = next;
            opportunities++;
        }

        System.out.println("orderedBoundaries=" + increasing);
        System.out.println("hasEndBoundary=" +
                (previous == text.length()));
        System.out.println("hasOpportunities=" +
                (opportunities > 0));
    }
}
```

Biên dịch và chạy bằng JDK 17+:

```bash
javac -encoding UTF-8 LineBoundaryDemo.java
java LineBoundaryDemo
```

Stdout ổn định:

```text
startAtZero=true
endAtLength=true
startBoundary=true
endBoundary=true
orderedBoundaries=true
hasEndBoundary=true
hasOpportunities=true
```

Chương trình chỉ kiểm tra **đặc trưng chung của ranh giới**, không hard-code danh sách vị trí ngắt của một locale provider cụ thể. Đầu ra không hề có một biến `viewportWidth` — vì `BreakIterator` **không có tham số chiều rộng**.

Nếu muốn quan sát các candidate boundaries thật, có thể in từng `next`, `substring(previous, next)` và mã UTF-16; kết quả chi tiết có thể khác giữa JDK/provider/locale. Trong một chương trình trình bày nội dung, các candidate này cần được kết hợp tiếp với phép đo chữ, không nên chèn `"\n"` sau mọi candidate.

## 5. Chiều rộng giao diện thuộc một tầng khác

Một textbox rộng 160 đơn vị và một panel rộng 480 đơn vị chứa **cùng chuỗi**. Những cơ hội ngắt ngôn ngữ có thể giống nhau, nhưng số dòng hiển thị thường khác.

```text
VĂN BẢN GỐC
"Internationalization needs careful line breaking."

       |
       +--> BreakIterator(locale)
       |       └── Ranh giới có thể ngắt theo ngôn ngữ
       |
       +--> Layout context
                font + size + shaping + text direction
                + available width + padding + scaling
                        |
                        ├── vùng hẹp  → nhiều soft-wrapped lines
                        └── vùng rộng → ít soft-wrapped lines
```

Không tính chiều rộng bằng `String.length()`, `codePointCount()` hoặc “trung bình mỗi chữ là 8 px”. Font có glyph rộng/hẹp khác nhau, kerning, ligatures, emoji, combining marks và phông thay thế. Cùng số Unicode code points có thể chiếm các độ rộng khác nhau.

### So sánh từng loại kích thước

| Thước đo | Ví dụ API | Dùng để làm gì? |
| --- | --- | --- |
| Số UTF-16 units | `s.length()` | Index trong `String`; **không** phải chiều rộng |
| Số Unicode code points | `s.codePointCount(0, s.length())` | Đếm code points; **không** phải chiều rộng |
| Số grapheme clusters | Regex `\X` hoặc segmenter phù hợp | Đếm cụm ký tự người dùng cảm nhận; **không** phải pixel width |
| Font advances/glyph metrics | `TextLayout`, `FontRenderContext` | Đo cần thiết cho bố trí chữ |
| Wrapping width | Kích thước vùng bố trí trong hệ tọa độ rendering | Giới hạn chiều ngang thực tế |
| Số dòng hiển thị | Kết quả text layout | Phụ thuộc cả điểm ngắt và width/font |

Ví dụ các chuỗi `"WWWW"` và `"iiii"` đều dài 4 UTF-16 units, nhưng với nhiều font tỷ lệ, độ rộng thực tế rất khác. Đừng tính line wrapping bằng cách cắt sau mỗi 20 `char` nếu mục tiêu là giữ chiều rộng hiển thị chính xác.

### Width không chỉ là số pixel CSS

Trong Java 2D, `LineBreakMeasurer.nextLayout(float wrappingWidth)` nhận độ rộng theo **hệ tọa độ của text layout/render context**, thường dùng cùng tọa độ user space của thao tác vẽ. Nếu hiển thị trên màn hình HiDPI, có transform, scaling hoặc font rendering khác, phải quản lý phép đo theo cùng render context với khi vẽ. Không tự giả định con số `100f` luôn là 100 device pixels độc lập mọi transform.

## 6. LineBreakMeasurer: đưa ranh giới ngôn ngữ vào phép bố trí

Java 2D có `java.awt.font.LineBreakMeasurer`. Nó nhận:

- `AttributedCharacterIterator` cho **một đoạn văn** có thuộc tính font/format;
- `FontRenderContext` để đo glyphs trong môi trường rendering;
- tùy chọn `BreakIterator` cho các line-break opportunities.

Ví dụ tạo object:

```java
AttributedString attributed = new AttributedString(text);
attributed.addAttribute(
        TextAttribute.FONT, new Font("Dialog", Font.PLAIN, 16));

FontRenderContext frc = new FontRenderContext(
        new AffineTransform(), true, true);

LineBreakMeasurer measurer = new LineBreakMeasurer(
        attributed.getIterator(),
        BreakIterator.getLineInstance(locale),
        frc);
```

Đây là đoạn minh họa trong một method, cần import từ `java.awt.Font`, `java.awt.font.*`, `java.awt.geom.AffineTransform`, `java.text.*` và `java.util.Locale`.

`nextLayout(width)` trả `TextLayout` đại diện cho đoạn ký tự vừa trong một dòng với chiều rộng yêu cầu, rồi **nâng vị trí** bên trong measurer. Có thể duyệt đến `getPosition() == iterator.getEndIndex()`.

Nếu một từ quá dài để vừa ngay đầu dòng, chính sách mặc định của `LineBreakMeasurer` có thể lấy một phần từ để đảm bảo tiến độ. Do đó, **không được khẳng định mọi dòng tuyệt đối chỉ ngắt ở word boundary**. Tài liệu Oracle mô tả nó ưu tiên từ trọn vẹn khi vừa, nhưng khi từ đầu quá dài có thể buộc chia để đặt được ký tự vào dòng.

### Đối chiếu API

| API | Có nhận width? | Có đo glyph/font? | Có trả dòng đã bố trí? |
| --- | --- | --- | --- |
| `BreakIterator.getLineInstance(locale)` | Không | Không | Không; trả boundaries |
| `LineBreakMeasurer.nextLayout(width)` | **Có** | **Có** | **Có**, `TextLayout` |
| `TextLayout.getAdvance()` | Không phải thuật toán wrap | Đại diện độ tiến theo trục dòng | Thước đo của một layout đã tạo |
| `String.length()` | Không | Không | Không |
| `String.split("\\R")` | Không | Không | Chỉ tách **dấu xuống dòng đã có** |
| `JTextArea`/Swing UI | Kích thước thành phần | Qua engine UI | Có thể tự wrap tùy cấu hình |

### 6.1. Chương trình Java 17 chạy được: width thay đổi số dòng

Tệp `WidthLayoutDemo.java`:

```java
import java.awt.Font;
import java.awt.font.FontRenderContext;
import java.awt.font.LineBreakMeasurer;
import java.awt.font.TextAttribute;
import java.awt.font.TextLayout;
import java.awt.geom.AffineTransform;
import java.text.AttributedString;
import java.text.BreakIterator;
import java.util.Locale;

public class WidthLayoutDemo {
    record Result(int lines, String reconstructed) {}

    private static Result layout(
            String text, float width,
            Font font, FontRenderContext frc) {

        AttributedString styled = new AttributedString(text);
        styled.addAttribute(TextAttribute.FONT, font);

        LineBreakMeasurer measurer = new LineBreakMeasurer(
                styled.getIterator(),
                BreakIterator.getLineInstance(Locale.US),
                frc);

        StringBuilder recovered = new StringBuilder();
        int lines = 0;

        while (measurer.getPosition() < text.length()) {
            int start = measurer.getPosition();
            TextLayout line = measurer.nextLayout(width);

            if (line == null) {
                throw new IllegalStateException(
                        "Layout did not advance");
            }

            int end = measurer.getPosition();
            recovered.append(text, start, end);
            lines++;
        }

        return new Result(lines, recovered.toString());
    }

    public static void main(String[] args) {
        String paragraph =
                "A quick brown fox jumps over the lazy dog. "
                + "A quick brown fox jumps over the lazy dog.";

        Font font = new Font("Dialog", Font.PLAIN, 18);
        FontRenderContext frc = new FontRenderContext(
                new AffineTransform(), true, true);

        Result narrow = layout(paragraph, 100f, font, frc);
        Result wide = layout(paragraph, 400f, font, frc);

        System.out.println("narrowPreserved=" +
                narrow.reconstructed().equals(paragraph));
        System.out.println("widePreserved=" +
                wide.reconstructed().equals(paragraph));
        System.out.println("narrowHasLines=" +
                (narrow.lines() > 0));
        System.out.println("wideHasLines=" +
                (wide.lines() > 0));
    }
}
```

Lưu mã nguồn với UTF-8, biên dịch và chạy trong môi trường JDK 17 có module `java.desktop`:

```bash
javac -encoding UTF-8 WidthLayoutDemo.java
java WidthLayoutDemo
```

Stdout dự kiến:

```text
narrowPreserved=true
widePreserved=true
narrowHasLines=true
wideHasLines=true
```

Cả hai phép bố trí **không sửa văn bản gốc**, vì `reconstructed` ghép lại các đoạn cắt theo offset của measurer. Số dòng thực tế có thể khác theo font và render environment; demo cố ý không hard-code `narrow.lines()` hay `wide.lines()`. Để quan sát chúng, thêm:

```java
System.out.println("narrowLines=" + narrow.lines());
System.out.println("wideLines=" + wide.lines());
```

Đó là đoạn bổ sung **bên trong `main`**. Thông thường vùng 100 units tạo nhiều dòng hơn vùng 400 units, nhưng giá trị cụ thể phụ thuộc font và phép đo. Trong UI production, phải dùng **đúng width thực** sau khi trừ padding/insets/scrollbars, và render bằng cùng `FontRenderContext` mà bạn dùng để đo.

### 6.2. TextLayout không tự vẽ mọi thứ

`LineBreakMeasurer.nextLayout` trả layout, nhưng client vẫn cần sắp xếp vị trí từng dòng, chiều cao, baseline, ascent/descent/leading và vẽ `layout.draw(Graphics2D, x, y)` ở vị trí phù hợp. Cũng cần xử lý alignment, tabs, paragraph spacing, clipping và text direction theo yêu cầu.

Đối với một đoạn có nhiều dòng, thuật toán dàn trang có thể cộng:

```java
baseline += layout.getAscent();
layout.draw(g2d, x, baseline);
baseline += layout.getDescent() + layout.getLeading();
```

Đây là đoạn minh họa trong method vẽ, `layout`, `g2d`, `baseline`, `x` phải có sẵn. Không phải chương trình `main` độc lập.

## 7. Newline chủ động khác soft wrapping

Xét văn bản:

```text
Hello world.
Next paragraph.
```

Nếu giữa hai câu có ký tự `\n`, đây là **quyết định của người viết dữ liệu**. Nếu không có newline mà UI hẹp đến mức phải đưa chữ “Next” xuống dòng, đó là **soft wrap**.

**Không tự chèn newline vào model khi chỉ muốn cho responsive layout.** Khi kích thước cửa sổ thay đổi, newline được chèn sẵn sẽ trở thành hard break và có thể phá cấu trúc bố cục trên màn hình rộng.

Một số dấu kết thúc dòng tồn tại trong Unicode hoặc quy tắc platform:

- LF: `\n` (U+000A);
- CR: `\r` (U+000D);
- CRLF: hai code units `\r\n`, thường nên xử lý như một sequence;
- U+0085 NEXT LINE, U+2028 LINE SEPARATOR, U+2029 PARAGRAPH SEPARATOR có thể cần chính sách riêng tùy nguồn dữ liệu.

Không dùng `String.split("\n")` rồi kết luận đã xử lý tất cả các quy ước newline. Java regex `\R` nhận một Unicode linebreak sequence theo định nghĩa của `Pattern`, trong đó có CRLF.

### Java 17 runnable: tách hard breaks

Tệp `ExplicitLineBreakDemo.java`:

```java
public class ExplicitLineBreakDemo {
    public static void main(String[] args) {
        String text = "First\r\nSecond\nThird";

        String[] logicalLines = text.split("\\R", -1);

        System.out.println("lines=" + logicalLines.length);
        System.out.println("first=" + logicalLines[0]);
        System.out.println("second=" + logicalLines[1]);
        System.out.println("third=" + logicalLines[2]);
    }
}
```

```bash
javac -encoding UTF-8 ExplicitLineBreakDemo.java
java ExplicitLineBreakDemo
```

Stdout:

```text
lines=3
first=First
second=Second
third=Third
```

`split("\\R", -1)` tách các dấu kết thúc dòng đã tồn tại, **không** dàn trang theo width. Nó cũng **không giữ lại chính các ký tự dấu xuống dòng** trong mảng kết quả; nếu cần round-trip nguyên văn, phải bảo quản separators hoặc lưu text gốc.

Khi dùng `LineBreakMeasurer`, tài liệu API yêu cầu iterator đại diện **một paragraph**. Vì thế cần phân đoạn theo hard breaks trước, rồi dàn trang **riêng mỗi paragraph**. Với dòng trống liên tiếp, phần hiển thị cần giữ dòng trống theo chính sách giao diện, không để một thư viện tự loại bỏ chúng.

## 8. Vì sao số ký tự không thể thay thế đo chiều rộng?

Phương án sai phổ biến:

```java
int columns = 20;
for (int i = 0; i < text.length(); i += columns) {
    String line = text.substring(
            i, Math.min(i + columns, text.length()));
    // Hiển thị line ...
}
```

Đây là đoạn minh họa trong method, **không phải thuật toán wrap UI phù hợp** vì:

1. `String.length()` đếm UTF-16 code units chứ không đếm glyph width.
2. Một emoji U+1F600 chiếm hai units; cắt giữa pair tạo UTF-16 ill-formed.
3. Chữ dùng dấu kết hợp hoặc emoji ZWJ có thể chiếm nhiều code points nhưng một grapheme cluster.
4. Font proportional khiến chữ `W` và `i` rộng khác nhau; font fallback làm metric thay đổi.
5. Tiếng Nhật, Trung, Thái không tuân quy tắc “cứ đủ N ký tự là ngắt”.
6. Dấu câu không phải lúc nào cũng được phép xuất hiện ở đầu/cuối dòng.
7. Văn bản hai chiều có thứ tự hiển thị khác thứ tự code units.
8. Kích cỡ chữ, letter spacing, kerning, zoom và DPI ảnh hưởng thực tế.

Một biến thể “đếm code points rồi cắt” tránh vấn đề surrogate pair, nhưng **vẫn không thay thế** layout theo font và language rules.

### Khi nào cắt theo số ký tự là hợp lệ?

Nếu contract quy định một hệ thống **terminal monospace** có cột ký tự, cũng cần xét East Asian width, combining marks, control characters và emoji width. Thậm chí “mỗi code point chiếm một cột” cũng không luôn đúng. Với ô hiển thị đồ họa, cách đúng là dùng text layout theo pixel/user-space metrics.

## 9. Ngôn ngữ không có khoảng trắng giữa từ

### 9.1. Tiếng Trung và tiếng Nhật

Nhiều câu tiếng Trung/Nhật không có khoảng trắng giữa các từ. Một thuật toán chỉ tìm dấu space sẽ xem cả câu như một token và có thể tràn width hoặc cắt tùy tiện.

Một line-break iterator có thể đưa ra ranh giới dựa trên Unicode line breaking, bao gồm những điểm giữa các ký tự CJK được phép. Nhưng còn các quy tắc về dấu ngoặc, dấu câu, ký tự nhỏ, dấu kéo dài âm hoặc cặp ký tự không nên tách. Cần dùng dữ liệu locale/provider phù hợp và test câu thật.

Ví dụ không nên đưa một dấu đóng ngoặc hoặc dấu câu vốn phải đứng cùng từ trước sang đầu dòng chỉ để lấp đầy width.

### 9.2. Tiếng Thái và Khmer

Văn bản có thể gồm các từ liền nhau không có khoảng trắng. Ranh giới word/line đôi khi cần segmentation dựa trên từ điển hoặc model. `BreakIterator.getLineInstance(Locale)` của Java là API cấp cao, nhưng kết quả phụ thuộc khả năng hỗ trợ ngôn ngữ của runtime. Không giả định mọi JDK có hiệu quả phân đoạn giống nhau cho tiếng Thái, Khmer và Lào.

Với sản phẩm yêu cầu chính xác cao, hãy so sánh kết quả với dữ liệu kiểm thử bản địa và cân nhắc ICU4J hoặc segmentation engine phù hợp. Đừng thay bằng regex chỉ ngắt ở dấu cách rồi chấp nhận cả câu chạy ra ngoài màn hình.

### 9.3. Tiếng Việt: khoảng trắng chưa chắc là ranh giới từ

Tiếng Việt thường có khoảng trắng giữa âm tiết. Một từ nhiều âm tiết như “công nghệ” có thể được viết thành hai khối cách nhau bởi space. Một line break hợp lệ về mặt hiển thị không có nghĩa đã phân tích chính xác “từ” ngôn ngữ cho tìm kiếm hay NLP. Vì vậy `getLineInstance` và `getWordInstance` có mục đích khác nhau, và việc xác định word semantics sâu hơn cần bộ xử lý riêng.

## 10. Emoji, combining marks và grapheme clusters

Unicode không tương đương “mỗi code point là một ký tự nhìn thấy”:

- `e\u0301` là chữ e và combining acute accent, có thể hiển thị thành một grapheme.
- `😀` là một supplementary code point, được biểu diễn bằng **surrogate pair** trong Java UTF-16.
- Emoji có skin tone modifier gồm nhiều code points.
- Emoji gia đình có thể dùng ZWJ U+200D nối nhiều người/biểu tượng thành một grapheme cluster.
- Lá cờ emoji có thể là cặp regional indicators.

Nếu bộ dàn trang rơi vào tình huống “không có từ nào vừa width”, phải cẩn thận khi fallback sang chia ký tự: **đừng cắt giữa high và low surrogate** hoặc trong một grapheme cluster. Một engine text layout hiện đại thường xử lý shaping/cluster, nhưng phạm vi Unicode/emoji hỗ trợ phải kiểm thử với chính runtime và font được triển khai.

Java có `BreakIterator.getCharacterInstance(locale)` cho character boundaries, và từ Java 9 regex `\X` có nghĩa Unicode extended grapheme cluster theo khả năng thư viện. Tuy nhiên, segmentation mới nhất, ZWJ sequences và hành vi font rendering có thể thay đổi theo Unicode/JDK.

**Gợi ý:** Nếu UI cắt/ẩn bớt chuỗi ở một độ rộng cụ thể, ưu tiên engine layout thực tế có khả năng xử lý grapheme clusters và overflow. Đừng tùy tiện chạy `substring(0, 10)` để cắt tên người hoặc emoji.

## 11. Văn bản hai chiều và bố trí glyph

Với tiếng Ả Rập, tiếng Hebrew và chuỗi trộn Latin/số:

- **Logical order** là thứ tự ký tự trong `String`.
- **Visual order** là thứ tự glyph sau khi áp Unicode Bidirectional Algorithm và shaping.
- **Line break** chia đoạn thành các vùng hiển thị, có thể ảnh hưởng cách xử lý bidi theo từng dòng.
- **Alignment** là quyết định của UI: left/right/start/end, có thể khác tùy hướng văn bản.

`BreakIterator` chỉ cung cấp ranh giới, **không làm đầy đủ việc định hướng và vẽ glyph**. `TextLayout`/Java 2D có chức năng layout glyph và hỗ trợ văn bản phức tạp ở mức hệ thống rendering. Trường hợp cần kiểm soát bidi, Java có thêm `java.text.Bidi`.

Đừng đảo `String` bằng `reverse()` để làm RTL. Đó không phải cách render tiếng Ả Rập; cũng có thể phá surrogate pair/combining marks hoặc thứ tự ngữ nghĩa. Hãy dùng bidi-aware rendering, font hỗ trợ và test chuỗi trộn tiếng Ả Rập với số, dấu câu, URL.

Một giao diện có direction RTL vẫn phải chọn các line-break opportunities theo ngôn ngữ; chiều chữ và khả năng ngắt là **hai chiều dữ liệu khác nhau**.

## 12. Swing, Java 2D, web và server: chọn tầng chịu trách nhiệm

### 12.1. Swing components

Với `JTextArea`, Java có:

```java
JTextArea area = new JTextArea(text);
area.setLineWrap(true);
area.setWrapStyleWord(true);
```

Đây là đoạn minh họa trong UI method với import `javax.swing.JTextArea`. `setLineWrap(true)` cho phép wrap khi chiều rộng bị giới hạn; `setWrapStyleWord(true)` yêu cầu ưu tiên ranh giới từ. Đừng hiểu “word” ở đây là thuật toán phân tích từ chính xác cho mọi ngôn ngữ và mọi trường hợp; vẫn cần test với text quốc tế và UI thật.

Một số Swing components như `JLabel` hoặc `JTextPane` có cơ chế layout khác nhau; không coi tất cả nhận cùng hai cờ này. Với vẽ custom vào `Graphics2D`, `LineBreakMeasurer` là API có ý nghĩa trực tiếp.

### 12.2. Java 2D custom painting

Với PDF preview, canvas drawing, custom editor hay in ấn bằng Java 2D, ứng dụng có thể phải tự xử lý paragraph breaks, font attributes, `LineBreakMeasurer`, `TextLayout`, margins, alignment và painting. `BreakIterator` cung cấp ranh giới được phép, còn `LineBreakMeasurer` chọn đoạn vừa width.

### 12.3. Frontend web và CSS

Khi backend Java gửi văn bản sang browser, browser đã có layout engine, font metrics, CSS và width thật. Thông thường **không** nên để Java chèn newline vào nội dung chỉ để vừa với độ rộng màn hình đã đoán. Browser có thể wrap theo Unicode/CSS và kích thước thực.

Các thuộc tính CSS như `white-space`, `overflow-wrap`, `word-break`, `line-break` và `hyphens` tác động khác nhau đến xử lý wrap, khoảng trắng, phân đoạn hoặc hyphenation. Chúng cần được chọn theo thiết kế và test từng ngôn ngữ, không dùng `word-break: break-all` như giải pháp mặc định cho mọi nội dung quốc tế.

Nếu có nội dung đặc biệt như URL cực dài, code inline hoặc identifier, có thể cần policy overflow riêng để không phá layout; đó là **quyết định hiển thị**, không có nghĩa thay đổi chuỗi dữ liệu gốc.

### 12.4. Server tạo email/plain text có độ rộng cố định

Một email text/plain hoặc báo cáo terminal có thể yêu cầu giới hạn cột. Nhưng cần xem contract yêu cầu **cột monospace**, byte limit hay width thực. Trong bối cảnh không có cùng font/viewport với người nhận, server khó tạo kết quả line wrapping đúng mọi thiết bị. Ưu tiên để client hiển thị tự ngắt, trừ khi chuẩn giao thức yêu cầu hard wrap.

### 12.5. PDF và in ấn

Khổ trang, lề, cột, font, rendering context và dấu ngắt trang làm width cố định hơn web responsive. Khi đó server-side text layout có thể hợp lý, nhưng phải dùng đúng font và kích thước sẽ vẽ ra PDF/giấy. Nếu render PDF bằng một thư viện riêng, không giả định kết quả đo từ Java 2D luôn trùng tuyệt đối với thư viện PDF khác.

## 13. Line break và hard break trong nội dung dữ liệu

Không nên gộp ba hành vi:

| Hành vi | Dấu trong dữ liệu | Phụ thuộc width? | Ví dụ |
| --- | --- | --- | --- |
| Người viết chèn newline | `\n`, `\r\n` hoặc separator khác | Không | Xuống dòng thủ công |
| Renderer soft-wrap | Thường không chèn ký tự vào chuỗi | Có | Textbox bị hẹp |
| Layout engine phân đoạn theo điểm được phép | Dựa ranh giới được ngôn ngữ cho phép | Gián tiếp khi renderer chọn điểm | Chọn xuống dòng tại space |

Nếu ứng dụng lưu text có soft breaks thành newline cứng trong DB, việc copy/paste có thể mang newline dư, tìm kiếm/so sánh có thể thay đổi và text sẽ không tự bố trí lại khi resize. Tách **data model** khỏi **layout model**.

Trường hợp thực sự cần lưu hard breaks, giữ đúng quyết định của người nhập. Nếu normalize line endings theo `\n`, đó là một bước biến đổi có contract, phải tách khỏi soft wrapping.

### Ranh giới thuộc UTF-16 indexes

`BreakIterator` trả các offsets để dùng với `String.substring` và `java.text.CharacterIterator`; trong Java, đây là **UTF-16 code unit positions**. Điều này khác số code points và width. Nếu dùng `String.codePoints()`, phải chuyển đổi index đúng cách; không coi offset từ BreakIterator là vị trí thứ n của `IntStream` code points.

## 14. Sự khác nhau giữa “được phép” và “nên”

Một ví dụ tiếng Anh có các cơ hội ngắt giữa các từ:

```text
Đoạn: "A quick brown fox jumps over the lazy dog."

Candidates: nhiều chỗ giữa các từ và ở cuối đoạn

Vùng rất rộng:
"A quick brown fox jumps over the lazy dog."

Vùng hẹp:
"A quick brown"
"fox jumps over"
"the lazy dog."
```

Đây là **minh họa ý tưởng**, không phải output chuẩn của `LineBreakMeasurer` cho một font và width cụ thể. Engine thực tế có thể chia thành dòng khác theo font, cỡ chữ và cách đo.

Một renderer thường cố giữ nhiều từ vừa nhất trong một dòng. Nhưng một thuật toán dàn trang xuất bản có thể chọn ngắt khác để cân bằng độ dài dòng, tránh widow/orphan, xử lý hyphenation hoặc justification. `BreakIterator` không quyết định những tiêu chí mỹ thuật ấy; `LineBreakMeasurer` cung cấp chính sách thông dụng cho text layout, không phải engine typography vạn năng.

## 15. Tùy chỉnh và giới hạn của LineBreakMeasurer

### 15.1. nextLayout và nextOffset

- `nextLayout(width)`: trả `TextLayout` kế tiếp và **tiến position**.
- `nextOffset(width)`: ước tính offset kết thúc của layout kế tiếp nhưng **không cập nhật position**.
- `setPosition(index)`: đặt điểm bắt đầu tiếp theo trong phạm vi iterator.
- `nextLayout(width, offsetLimit, requireNextWord)`: cho giới hạn offset và chính sách yêu cầu một từ trọn vẹn khi đang thêm text vào một dòng đã có nội dung.
- `insertChar` / `deleteChar`: cập nhật một trường hợp thay đổi text đơn lẻ với iterator mới; không phải phép mutate nội dung text bên trong measurer tự động.

Theo tài liệu, `nextLayout(width, limit, true)` có thể trả `null` khi cả từ tiếp theo không vừa phần width còn lại; cần xử lý `null` thay vì lấy `getPosition()` rồi lặp vô tận.

### 15.2. Với tab và custom line policy

`LineBreakMeasurer` xem tab theo chính sách riêng, và ứng dụng có tab stops có thể phải giới hạn offset cho mỗi đoạn. Không mặc định một ký tự `\t` luôn chiếm đúng 4 dấu cách hoặc cùng width ở mọi font/render. Nếu UI dùng rich text và tabs, cần thiết kế tab handling riêng.

### 15.3. Khi độ rộng bằng 0 hoặc âm

Một vùng vẽ không có width dùng được phải được xử lý tại tầng layout trước khi gọi measurer. Tránh vòng lặp không tiến position hoặc sử dụng giá trị bất hợp lệ. Có thể kiểm tra `width > 0`, layout empty paragraph theo policy của UI, và hiển thị placeholder/scroll khi vùng quá nhỏ.

### 15.4. Rich text: nhiều font trên cùng dòng

`AttributedString` có thể chứa nhiều đoạn font khác nhau. Khi nhiều font, font size và glyph metrics thay đổi trong một paragraph, độ rộng không còn là một hàm đơn giản của số ký tự. `TextLayout` cần các thuộc tính đúng, và việc chia dòng có thể thay đổi nếu người dùng bôi đậm một từ.

### 15.5. Không phải mọi hệ thống đều có java.desktop

`BreakIterator` thuộc module `java.base`. `LineBreakMeasurer`, `TextLayout` và `FontRenderContext` thuộc `java.desktop`. Nếu ứng dụng chạy trong runtime được tạo bằng `jlink` chỉ có một số module, phần Java 2D có thể không hiện diện. Hãy xác định nhu cầu text layout trên server hay client; không tự kéo thêm phần graphics nếu backend chỉ cần ngữ nghĩa ranh giới văn bản.

## 16. Hiệu năng, caching và thread safety

Cả boundary analysis lẫn glyph layout đều có chi phí. Với UI lớn hoặc text thay đổi liên tục, tối ưu cần dựa trên profile:

- `BreakIterator` có trạng thái vị trí và text đang phân tích. Không chia sẻ một instance rồi gọi `setText` cho nhiều request đồng thời.
- `LineBreakMeasurer` là iterator/trạng thái bố trí của **một paragraph**; không dùng một instance đồng thời cho nhiều paragraph hoặc đổi text mà không làm mới/áp dụng API update được hỗ trợ.
- `FontRenderContext` và font attributes phải thống nhất với render; cache layout theo width nếu width/font/text/locale không đổi, và invalidate khi có thay đổi.
- Khi text/locale/provider khác nhau, các boundaries có thể thay đổi; không dùng cache key chỉ dựa trên chuỗi văn bản.
- Đừng hard-code một mảng newline đã wrap để dùng cho cả mobile và desktop.
- Không đo performance bằng một lần gọi có JIT warm-up chưa ổn; với workload lớn có thể dùng JMH hoặc đo UI thật.

Nếu dùng `BreakIterator.getLineInstance()` không tham số, nó dùng default locale của môi trường. Trong app đa người dùng, truyền locale được chọn tường minh; **không** đổi `Locale.setDefault` theo từng HTTP request vì default là state JVM dùng chung.

## 17. Lỗi thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “`BreakIterator.getLineInstance` tự chia paragraph thành dòng vừa 200 px.” | Nó chỉ trả các cơ hội ngắt; không nhận width |
| “Cứ mỗi boundary trả về là một dòng.” | Một dòng có thể chứa nhiều đoạn giữa các boundaries |
| “Cứ 20 `char` là vừa 20 cột.” | `char` là UTF-16 code unit, không phải glyph width |
| “Dùng `String.split(" ")` là ngắt dòng đúng mọi ngôn ngữ.” | Nhiều hệ chữ không có space giữa từ; dấu câu/Unicode còn quy tắc |
| “Word boundary luôn bằng line boundary.” | Hai loại segmentation khác mục đích |
| “Dấu xuống dòng trong model và soft wrap của UI là một.” | Hard break có trong data; soft wrap phụ thuộc layout |
| “Ngắt giữa surrogate pair là ổn nếu không có exception.” | Có thể tạo UTF-16 ill-formed |
| “Một code point là một ký tự nhìn thấy.” | Grapheme cluster có thể chứa nhiều code points |
| “Chọn Locale là đủ để biết chiều rộng của chữ.” | Width cần font, size, shaping, render context |
| “Dùng layout tiếng Anh cho tiếng Thái sẽ luôn đúng.” | Phải có segmentation/locale/data phù hợp |
| “Các glyph RTL chỉ cần đảo String.” | Cần bidi-aware shaping và rendering |
| “Tự wrap backend là hợp lý cho responsive web.” | Thường nên để browser/layout engine quyết định bằng width thực |
| “`LineBreakMeasurer` không bao giờ chia một từ.” | Có thể chia khi từ đầu không vừa width |
| “`LineBreakMeasurer` tự quản lý mọi hard paragraph breaks.” | Nên tách paragraphs và bố trí từng đoạn theo contract |
| “Thay đổi font không ảnh hưởng cách chia dòng.” | Glyph metrics thay đổi, điểm xuống dòng có thể khác |
| “Cứ có cơ hội ngắt hợp lệ là UI nhất thiết ngắt.” | Ngắt thực tế còn phụ thuộc width và bố trí |

## 18. Kiểm thử thực tế

### 18.1. Tầng ranh giới ngôn ngữ

- Chạy `BreakIterator.getLineInstance` với `en-US`, `vi-VN`, `ja-JP`, `zh-CN`, `th-TH` trên dữ liệu bản địa.
- Kiểm tra offsets tăng dần, nằm trong phạm vi UTF-16, và iterator đến cuối đoạn đúng.
- Kiểm tra cụm dấu câu, khoảng trắng không ngắt, zero-width space, dấu nối và chuỗi không có khoảng trắng.
- Kiểm tra surrogate pair, dấu kết hợp và emoji ZWJ không bị cắt trái với quy tắc/khả năng runtime được cam kết.
- Pin runtime/provider hoặc chấp nhận các biến thể boundary khi dữ liệu Unicode/locale thay đổi.
- Khi cần segmentation có dictionary, test với corpus thực; không suy từ một câu tiếng Anh.

### 18.2. Tầng bố trí

- Với **cùng text/locale/font**, đo số dòng ở các width khác nhau.
- Đổi font, font size, rich text hoặc DPI/scale rồi kiểm tra wrap lại.
- Kiểm tra nhãn dài, URL, emoji, từ rất dài, space và NBSP.
- Đảm bảo layout không tiến ra ngoài paragraph và không bị vòng lặp vô hạn khi vùng quá hẹp.
- Nếu cắt/ellipsis, kiểm tra không xé grapheme hoặc che mất nội dung quan trọng.
- Kiểm tra LTR/RTL và hỗn hợp chữ với số/dấu câu.
- Kiểm tra height, baseline, ascent/descent và clipping; dòng đủ width nhưng không đủ height vẫn bị cắt.

### 18.3. Tầng dữ liệu

- Text soft-wrapped có thể tái bố trí khi resize mà **không đổi text gốc**.
- Hard breaks được giữ theo yêu cầu; CRLF không biến thành hai dòng trống vô ý.
- Copy/paste không mang newline do soft-wrap nếu thiết kế chỉ wrap khi render.
- API/DB lưu văn bản canonical; UI layout không chèn fragment ngoài ý muốn vào dữ liệu.
- Kiểm tra khi client browser và backend khác font/rendering engine: không kỳ vọng line count chính xác giống nhau.

### 18.4. Tầng accessibility và đa ngôn ngữ

- Với screen reader, thứ tự đọc dựa trên logical text, không bị thay đổi bởi thao tác đảo visual order.
- Không dùng ký tự newline cưỡng bức làm mất ngữ nghĩa một câu dài.
- Kiểm tra bản dịch dài hơn tiếng Anh làm UI co giãn đúng.
- Với người dùng phóng to chữ, wrapping đổi nhưng thông tin vẫn không bị che.
- Kiểm tra ngôn ngữ trộn trong cùng paragraph và direction của đoạn.

## 19. Bài tập tự luyện và đáp án

**Bài 1.** `BreakIterator.getLineInstance(Locale.US)` nhận đoạn text và trả nhiều ranh giới. Liệu đó có phải số dòng hiển thị khi một textbox rộng 250 px không?

**Đáp án:** Không. Nó chỉ cung cấp các vị trí có thể ngắt. Số dòng cần width, font, shaping và engine layout.

**Bài 2.** Cùng một đoạn text, khi width tăng từ 160 lên 480 đơn vị, bộ candidate boundaries có nhất thiết thay đổi không?

**Đáp án:** Không. Nếu text/locale/thuật toán segmentation không đổi, boundary opportunities không phụ thuộc width. Các điểm **được chọn** để wrap mới có thể đổi.

**Bài 3.** Vì sao `text.substring(i, i + 20)` không phải phương án wrapping tốt?

**Đáp án:** Vì đếm UTF-16 units không phải glyph width; còn có nguy cơ cắt surrogate pair, grapheme cluster, dấu câu hoặc từ không nên chia.

**Bài 4.** Muốn bố trí đoạn văn trong Java 2D theo một chiều rộng cụ thể, dùng gì?

**Đáp án:** Dùng `AttributedCharacterIterator` có font attributes, `FontRenderContext`, `LineBreakMeasurer` và `TextLayout`; có thể truyền `BreakIterator.getLineInstance(locale)`.

**Bài 5.** Có một chuỗi với `\r\n`. `BreakIterator` và wrapping có nên xem nó giống soft break của UI không?

**Đáp án:** Không. `\r\n` là hard break trong dữ liệu. Tách và bảo quản paragraph/line semantics trước khi soft-wrap từng phần.

**Bài 6.** Một từ tiếng Thái không có space, và thuật toán `split(" ")` cho một chuỗi rất dài. Có nên chèn newline sau mỗi 10 ký tự?

**Đáp án:** Không. Cần segmentation theo ngôn ngữ và layout thực tế; ép theo số char có thể xé cụm ký tự và không tuân width.

**Bài 7.** Vì sao `LineBreakMeasurer` có thể phải tách một từ dù đã có BreakIterator?

**Đáp án:** Khi từ đầu dòng không vừa trong width yêu cầu; chính sách layout thường phải tạo một đoạn để đảm bảo tiến độ. Cần xử lý trường hợp token dài, overflow và ngữ nghĩa ứng dụng.

**Bài 8.** Backend Java sinh text để render trong mobile browser. Nên chèn newline dựa trên width giả định của máy desktop hay để client wrap?

**Đáp án:** Thông thường để browser dùng width/font thực và CSS thích hợp. Backend giữ text và hard breaks có ý nghĩa, không lưu soft-wrap.

**Bài 9.** `BreakIterator` trả UTF-16 index, còn UI cần cắt theo grapheme cluster. Có thể lấy index và cắt luôn bất kỳ nơi nào không?

**Đáp án:** Không. Cần xem đây có phải boundary phù hợp với yêu cầu grapheme và runtime không; không cắt giữa surrogate pair hoặc cụm ký tự của người dùng.

**Bài 10.** Nếu đổi font hoặc tăng kích cỡ chữ, có cần tính lại `LineBreakMeasurer` không?

**Đáp án:** Có, vì glyph metrics đã thay đổi. Bộ điểm ngắt ngôn ngữ có thể tương tự, nhưng số dòng và vị trí được chọn để xuống dòng có thể khác.

## 20. Ghi nhớ

- **Ngắt dòng theo ngôn ngữ** trả lời **“được phép ngắt ở đâu?”**; **bố trí theo chiều rộng** trả lời **“nên ngắt ở đâu để dòng vừa?”**.
- `BreakIterator.getLineInstance(locale)` cung cấp candidate boundaries và **không nhận width**. Đừng xem các đoạn giữa boundaries là những dòng UI.
- `LineBreakMeasurer` kết hợp paragraph text, font/render context và wrapping width để tạo `TextLayout` cho mỗi dòng. Có thể truyền `BreakIterator` theo locale.
- Dấu newline có sẵn là **hard break**; xuống dòng do vùng hẹp là **soft wrap** và không nên làm thay đổi text canonical.
- `String.length()`, code point count và số grapheme clusters **không phải** chiều rộng glyph. Tránh cắt text theo số `char` để giả lập wrapping.
- CJK, Thái/Khmer, dấu câu, NBSP/ZWSP, emoji và RTL cần kiểm thử phù hợp ngôn ngữ và rendering engine.
- Với frontend responsive, thường để UI engine bố trí theo width thực; với Java 2D/PDF/in ấn, đo đúng font, width và metrics.
- **Không trộn ranh giới văn bản, ngôn ngữ, mã Unicode và chiều rộng giao diện thành một phép tính.** Chọn công cụ theo đúng câu hỏi.

### Tham khảo Java 17 và Unicode

- [BreakIterator — Oracle Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/BreakIterator.html)
- [LineBreakMeasurer — Oracle Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/font/LineBreakMeasurer.html)
- [TextLayout — Oracle Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/font/TextLayout.html)
- [FontRenderContext — Oracle Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.desktop/java/awt/font/FontRenderContext.html)
- [Pattern — Java regex `\R` và `\X`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html)
- [Unicode Line Breaking Algorithm — UAX #14](https://www.unicode.org/reports/tr14/)
