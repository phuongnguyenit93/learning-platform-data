# Giới hạn xử lý Bidi khi giao diện đã có bộ bố trí văn bản trong Java

## 1. Đặt vấn đề: ai chịu trách nhiệm về chiều chữ?

Một ứng dụng Java có thể hiển thị một câu tiếng Việt chứa tên người bằng tiếng Ả Rập, hoặc một giao diện tiếng Hebrew chứa số điện thoại, mã đơn hàng và URL bằng chữ Latin. Những đoạn **trái sang phải** (left-to-right, LTR) và **phải sang trái** (right-to-left, RTL) cùng tồn tại trong **một chuỗi logic**. Khi đưa chuỗi đó lên giao diện, thứ tự ký tự nhìn thấy có thể không giống thứ tự các code point trong bộ nhớ.

Unicode có **Bidirectional Algorithm (UBA)** để xác định cách sắp xếp hiển thị những đoạn chữ hỗn hợp theo hướng. Trong Java core, lớp `java.text.Bidi` có thể **phân tích hướng**, mức nhúng và các run của một đoạn văn bản. Nhưng một giao diện hiện đại thường đã có **text layout engine** thực hiện Bidi, phân đoạn dòng, shaping, chọn glyph, positioning và quản lý caret.

Vì vậy, bài toán không phải “cứ thấy tiếng Ả Rập là gọi Bidi rồi đảo String”. Câu hỏi đúng hơn:

> **Khi UI đã sở hữu bước bố trí văn bản, Java application nên cung cấp dữ liệu và ngữ cảnh gì, và không nên làm lại phần việc nào?**

**Ý chính:** giữ chuỗi ở **logical order**, chọn **hướng đoạn văn / ngữ cảnh cô lập** ở tầng phù hợp, giao việc tính **visual order** cho một text renderer đủ chức năng; chỉ dùng `java.text.Bidi` trực tiếp khi thực sự phải tự phân tích hướng hoặc xây dựng một thành phần render text chuyên dụng.

### Mục tiêu bài học

Sau bài, bạn có thể:

1. Phân biệt **logical order**, **visual order**, **base paragraph direction**, **embedding level** và **directional run**.
2. Biết `java.text.Bidi` trả thông tin gì, và **không** trả thông tin gì.
3. Giải thích vì sao không đảo ngược `String`, không tự reorder trước khi đưa vào UI engine có hỗ trợ Bidi.
4. Nhận diện vai trò khác nhau của Unicode Bidi, Arabic shaping, font layout, line breaking và text editing.
5. Dùng đúng hướng và isolation cho thành phần độc lập như tên, email, số, mã đơn hàng hoặc URL trong dòng RTL.
6. Thiết kế xử lý hợp lý cho Swing/Java2D, JavaFX, Android hoặc giao diện web khi layout engine đã tồn tại.
7. Kiểm thử text hỗn hợp và cảnh giác với ký tự điều khiển hướng có thể gây hiểu sai dữ liệu, log hoặc mã nguồn.

## 2. Logical order và visual order không giống nhau

**Logical order** là thứ tự các ký tự/code point trong dữ liệu `String`, file, API hay database. Thứ tự này mang ý nghĩa cấu trúc, cho phép search, parse và serialize dữ liệu.

**Visual order** là thứ tự glyph được hiển thị trên dòng sau khi áp dụng thuật toán Bidi, shaping và layout. Renderer có thể hiển thị một đoạn RTL theo hướng ngược với đoạn Latin bên cạnh, mà **không sửa nội dung của `String`**.

Giả sử dữ liệu:

```text
Chuỗi logic: "ABC " + [Alef][Bet][Gimel]
Unicode:      U+0041 U+0042 U+0043 U+0020 U+05D0 U+05D1 U+05D2
```

Dãy code point vẫn nằm theo thứ tự ấy trong bộ nhớ. Nhưng để người đọc thấy đúng thứ tự của đoạn Hebrew, giao diện phải tính chiều và bố trí glyph phù hợp.

**Không nên lưu thứ tự “nhìn thấy trên màn hình” như một chuỗi đã đảo ngược.** Nếu tự biến đổi dữ liệu logic để bắt chước visual order, các thao tác copy/paste, tìm kiếm, chọn văn bản, đọc bằng screen reader, line wrapping và hiển thị ở nơi khác có thể trở nên sai.

### Một chuỗi, nhiều cách bẻ dòng

UBA giải quyết hướng và reordering trên từng đoạn/dòng theo ngữ cảnh. Khi độ rộng giao diện thay đổi, các run có thể được chia lại, dấu câu/đoạn số có thể đổi vị trí tương đối. Bởi vậy **không có một chuỗi ký tự “đã đảo đúng để render mọi chiều rộng”** phù hợp cho mọi layout.

Một renderer có thể dùng cùng logical string để tạo visual lines khác nhau khi:

- Cửa sổ được thu hẹp hoặc mở rộng.
- Font hoặc cỡ chữ thay đổi.
- Nội dung được wrap ở vị trí khác.
- Hướng cơ sở của paragraph thay đổi.
- Một đoạn được đặt vào container có cách cô lập hướng khác.

Bất kỳ cách “tiền xử lý” bằng cách đảo thứ tự code point nào trước khi UI render cũng có nguy cơ **double reordering** hoặc phá nghĩa.

## 3. UBA, shaping và layout là những giai đoạn khác nhau

| Công việc | Câu hỏi được giải quyết | Kết quả thường gặp |
| --- | --- | --- |
| **Bidi analysis** | Các ký tự/run có mức hướng nào trong đoạn? | Embedding levels, directional runs, visual-order constraints. |
| **Script shaping** | Những code point tạo glyph nào theo chữ viết/ngữ cảnh? | Dạng nối chữ Ả Rập, ligature, vị trí dấu phụ. |
| **Font fallback** | Font nào có glyph cần dùng? | Chọn font theo script/glyph coverage. |
| **Line breaking** | Văn bản phân thành những dòng nào? | Điểm wrap dựa trên chiều rộng, quy tắc dòng/ngôn ngữ. |
| **Glyph positioning** | Glyph nằm ở tọa độ nào, advance bao nhiêu? | Layout trên dòng và các thông số vẽ. |
| **Hit-testing/caret** | Click ở pixel này trỏ đến offset logic nào? | Vị trí caret, selection, keyboard navigation. |
| **Accessibility** | Đọc văn bản theo trật tự nội dung nào? | Logical text, vai trò ngữ nghĩa, thứ tự đọc phù hợp. |

`java.text.Bidi` **không** thay thế toàn bộ bảng chức năng trên. Nó cung cấp dữ liệu về chiều chữ, không phải một text widget hoàn chỉnh. Nó không chọn font phù hợp, không shaping chữ Ả Rập, không xử lý hit-testing con trỏ hay vẽ glyph trên thiết bị.

Một UI framework có layout engine thường **kết hợp** nhiều thành phần nói trên. Nếu app tự chạy Bidi rồi đảo chuỗi và sau đó lại đưa sang framework đó, bạn làm lại một bước mà framework đã đảm nhiệm, và có thể làm nó sai.

### Ví dụ chữ Ả Rập

Các chữ Ả Rập có cách nối hình dạng tùy ngữ cảnh. **Đảo ngược mã ký tự không tạo ra việc nối chữ đúng.** Shaping là trách nhiệm khác với việc tính thứ tự run theo Bidi. Nếu một ứng dụng chỉ có `Bidi`, nó vẫn cần font và shaping engine để vẽ tiếng Ả Rập một cách hoàn chỉnh.

Tương tự, dấu tổ hợp có thể bám vào glyph nền, emoji có thể gồm nhiều code point tạo một cụm, và việc di chuyển caret cần tránh chia đôi grapheme cluster. Một bước `StringBuilder.reverse()` không phải một bộ máy giải quyết các vấn đề ấy; dù Java có xử lý surrogate pair trong một số thao tác reverse, nó không làm phép đảo chuỗi trở thành thuật toán Bidi hoặc grapheme layout.

## 4. Java java.text.Bidi làm được gì?

Lớp `java.text.Bidi` phân tích cấu trúc hai chiều của một đoạn text. Một cách tạo đối tượng:

```java
String mixed = "ABC \u05D0\u05D1\u05D2";
Bidi analysis = new Bidi(
        mixed,
        Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);
```

Đoạn mã nằm trong một phương thức Java với import `java.text.Bidi`.

Các API đáng biết:

| API | Ý nghĩa |
| --- | --- |
| `Bidi(String paragraph, int flags)` | Phân tích một paragraph theo hướng cơ sở lựa chọn/ước lượng. |
| `DIRECTION_LEFT_TO_RIGHT` | Chọn hướng cơ sở LTR cụ thể. |
| `DIRECTION_RIGHT_TO_LEFT` | Chọn hướng cơ sở RTL cụ thể. |
| `DIRECTION_DEFAULT_LEFT_TO_RIGHT` | Dựa vào ký tự mạnh đầu tiên; dùng LTR làm mặc định nếu không xác định được. |
| `DIRECTION_DEFAULT_RIGHT_TO_LEFT` | Dựa vào ký tự mạnh đầu tiên; dùng RTL khi cần fallback. |
| `getBaseLevel()` | Embedding level cơ sở (chẵn là LTR, lẻ là RTL). |
| `isMixed()` | Đoạn có sự pha trộn hướng theo phân tích không. |
| `isLeftToRight()` / `isRightToLeft()` | Đặc trưng hướng của paragraph theo kết quả phân tích. |
| `getRunCount()` | Số directional runs được phân tích. |
| `getRunStart(i)` / `getRunLimit(i)` | Khoảng offset logic bắt đầu/kết thúc của run. |
| `getRunLevel(i)` | Embedding level của run. |
| `getLevelAt(offset)` | Level tại vị trí ký tự tương ứng. |
| `Bidi.requiresBidi(char[], start, limit)` | Phép kiểm tra tiện dụng xem dãy ký tự có cần xử lý hướng hai chiều. |
| `Bidi.reorderVisually(...)` | Hỗ trợ sắp lại **các đối tượng/run** theo level, không phải render toàn bộ String thành text hiển thị. |
| `createLineBidi(start, limit)` | Tạo phân tích Bidi cho một đoạn dòng dựa trên paragraph đã phân tích. |

**Cần phân biệt:** offset của `getRunStart`/`getRunLimit` là các vị trí trong chuỗi UTF-16, với `limit` là điểm kết thúc **không bao gồm**. Không nhầm với code point index, số byte UTF-8 hoặc pixel.

### Vì sao Bidi riêng lẻ không đủ để render?

Giả sử có hai run, một LTR và một RTL. `Bidi` cho biết hướng của các run, nhưng khi hiển thị thực tế còn cần:

- Biết mỗi glyph rộng bao nhiêu và đặt ở đâu.
- Tính shaping và thứ tự glyph trong các script tương ứng.
- Bẻ dòng theo kích thước container.
- Quy tắc ký tự neutral như khoảng trắng, dấu câu và ngoặc.
- Ánh xạ pixel về vị trí logical cho copy/selection/caret.
- Thay đổi level khi nội dung được nhúng trong paragraph khác.

Do đó, đọc `getRunCount()` rồi nối `substring(...)` theo thứ tự ngược **không phải** cách xây dựng một text renderer đủ chức năng.

## 5. Ví dụ Java 17+ chạy độc lập: phân tích hướng, không tự vẽ lại

Tạo file **`BidiLayoutBoundaryDemo.java`**:

```java
import java.text.Bidi;

public class BidiLayoutBoundaryDemo {

    public static void main(String[] args) {
        String mixed = "ABC \u05D0\u05D1\u05D2";

        Bidi analysis = new Bidi(
                mixed, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);

        System.out.println("utf16Length=" + mixed.length());
        System.out.println("baseLevel=" + analysis.getBaseLevel());
        System.out.println("isMixed=" + analysis.isMixed());
        System.out.println("runCount=" + analysis.getRunCount());

        for (int index = 0;
             index < analysis.getRunCount();
             index++) {
            System.out.println(
                    "run[" + index + "]="
                    + analysis.getRunStart(index)
                    + ".." + analysis.getRunLimit(index)
                    + " level=" + analysis.getRunLevel(index));
        }

        System.out.println("requiresMixed="
                + Bidi.requiresBidi(
                        mixed.toCharArray(), 0, mixed.length()));

        String latin = "ABC 123";
        System.out.println("requiresAscii="
                + Bidi.requiresBidi(
                        latin.toCharArray(), 0, latin.length()));

        Bidi hebrew = new Bidi(
                "\u05D0\u05D1\u05D2",
                Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);
        System.out.println("hebrewBaseLevel="
                + hebrew.getBaseLevel());

        System.out.println("sourceUnchanged="
                + mixed.equals("ABC \u05D0\u05D1\u05D2"));
    }
}
```

Biên dịch và chạy từ thư mục chứa file với JDK 17 hoặc mới hơn:

```bash
javac -encoding UTF-8 BidiLayoutBoundaryDemo.java
java BidiLayoutBoundaryDemo
```

**Stdout đã đối chiếu bằng Java 17:**

```text
utf16Length=7
baseLevel=0
isMixed=true
runCount=2
run[0]=0..4 level=0
run[1]=4..7 level=1
requiresMixed=true
requiresAscii=false
hebrewBaseLevel=1
sourceUnchanged=true
```

### Giải thích output

1. `utf16Length=7`: `ABC` có 3 UTF-16 code unit, khoảng trắng 1, ba chữ Hebrew mỗi chữ 1; tổng là 7.
2. `baseLevel=0` vì ký tự mạnh đầu là Latin LTR.
3. `isMixed=true` và `runCount=2`: paragraph gồm đoạn LTR và RTL.
4. `run[0]=0..4 level=0` chỉ phần Latin cùng khoảng trắng; `run[1]=4..7 level=1` chỉ phần Hebrew.
5. `requiresMixed=true` với chuỗi chứa chữ RTL; `requiresAscii=false` với chuỗi Latin/số thuần trong ví dụ.
6. `hebrewBaseLevel=1`: khi chỉ có chữ Hebrew, ký tự mạnh đầu thuộc RTL nên base level được xác định tương ứng.
7. `sourceUnchanged=true`: phân tích không đảo hay sửa nội dung String.

Đây là chương trình **đọc và in thông tin phân tích**, không phải đoạn mã hiển thị chữ. Nếu in trực tiếp chuỗi Hebrew ở terminal, thứ tự nhìn thấy phụ thuộc terminal/font/console; vì vậy ví dụ in **offset và level bằng ASCII** để tránh nhầm lẫn giữa kết quả thuật toán và khả năng render của môi trường.

## 6. Những giới hạn quan trọng của Bidi.requiresBidi

`Bidi.requiresBidi(...)` là API phát hiện nhanh nhu cầu Bidi trên một phạm vi `char[]`. Nó có ích khi bạn cần quyết định có đi vào nhánh phân tích chuyên biệt trong **một text pipeline tự quản lý**. Nhưng không nên dùng nó để tự quyết định toàn bộ chính sách UI.

Những điều nó **không** giải quyết:

- **Không xác định locale của người dùng** hay ngôn ngữ chính của một paragraph.
- **Không nói chính xác cách vẽ một dòng**; cần layout, shaping và line-breaking.
- **Không thay cho thuộc tính hướng của container**.
- **Không xác minh an toàn của Unicode bidi controls** trong text người dùng.
- **Không bảo đảm chỉ cần chạy lúc có ký tự Hebrew/Arabic**; số, ký tự neutral, punctuation và ngữ cảnh paragraph đều có thể ảnh hưởng vị trí hiển thị.
- **Không cho phép app bỏ qua engine layout** chỉ vì phương thức trả false; ngay cả text không pha RTL cũng cần font, caret và line wrapping.

Nếu widget đã có text layout và tự quyết định cần chạy Bidi hay không, ứng dụng thường **không cần gọi `requiresBidi` trước khi render**. Lặp bước này có thể tăng độ phức tạp mà không mang lại lợi ích.

## 7. Khi UI đã có text layout engine: phân chia trách nhiệm

Tùy nền tảng, tên API khác nhau, nhưng nguyên tắc thường giống nhau.

| Tầng | Trách nhiệm nên đảm nhiệm |
| --- | --- |
| **Domain / model** | Lưu chuỗi logic, ID, thứ tự dữ liệu; không sửa để “nhìn đúng”. |
| **Localization** | Chọn bản dịch, thứ tự placeholder, locale, các thông điệp RTL/LTR đúng ngữ pháp. |
| **UI component / container** | Chọn base direction, layout direction hoặc `dir` theo ngữ cảnh; cô lập đoạn chèn độc lập khi phù hợp. |
| **Text layout engine** | Chạy Bidi, shaping, line wrapping, glyph positioning, caret, selection. |
| **Accessibility** | Dùng text logic/semantic; không lấy chuỗi “đảo để hiển thị” làm văn bản đọc. |
| **Validation / security** | Xem xét dữ liệu Unicode controls, format log rõ ràng, chống mạo danh và gây hiểu nhầm. |

Khi một thành phần giao diện đảm nhiệm **Bidi + shaping**, application không nên đưa cho nó “visual order string” tự tạo. Hãy đưa **logical string** và **directional context**.

### Trường hợp UI chỉ nhận chuỗi, không có phương thức định hướng rõ ràng

Nếu một API render thực sự không có hỗ trợ Bidi, giải pháp không phải mặc định đảo `String`. Bạn có thể cần:

- Chuyển sang component/text engine có hỗ trợ Bidi.
- Dùng rich text hoặc thuộc tính paragraph direction được framework cung cấp.
- Tạo custom renderer dựa trên `TextLayout`/font shaping cùng thuật toán Bidi phù hợp, **chỉ khi thật sự cần sở hữu pipeline**.
- Kiểm thử Arabic shaping, mixed text, selection và line breaking trong môi trường đích.

**Không trộn hai chiến lược**: vừa tự reorder string, vừa yêu cầu engine reorder lại.

## 8. Swing, Java2D, JavaFX, Android và web: nơi đặt cấu hình

### 8.1. Swing/Java2D

Các Swing text component và hệ thống Java2D có cơ chế xử lý text và có thể cung cấp hỗ trợ hướng, font, run layout. Khi dùng:

- Ưu tiên API định hướng/`ComponentOrientation` hoặc text component tương ứng thay vì đảo dữ liệu.
- Với rich text, kiểm tra paragraph/style attributes mà component hỗ trợ.
- Khi thật sự tự vẽ chữ, `java.awt.font.TextLayout` có thể tham gia layout phức tạp; **chỉ riêng `java.text.Bidi` không vẽ được glyph**.
- Dùng tọa độ/hit-test do text layout tạo ra cho caret và vùng chọn, không suy từ `String.length()` thành vị trí pixel.

Không có một thuộc tính Swing duy nhất bảo đảm mọi custom component hoặc bảng vẽ tự viết đều xử lý mọi script hoàn hảo. Cần test đúng control, font và JDK mục tiêu.

### 8.2. JavaFX

Với JavaFX controls, dùng **layout node và text controls** để hiển thị. Kiểm tra cơ chế hướng node/paragraph mà phiên bản JavaFX mục tiêu hỗ trợ. Không tạo một `String` đã đảo ký tự trước khi truyền vào `Text`, `TextFlow` hoặc control có layout.

TextFlow và rich text còn có thể đặt các đoạn ở nhiều node, mỗi node có font/kiểu khác nhau; cần đảm bảo tính liên tục của ngữ cảnh Bidi và kiểm tra kết quả tại các ranh giới node. Khi gặp lỗi, xác định chính xác thành phần nào đang layout, thay vì chèn ký tự đảo hướng ngẫu nhiên.

### 8.3. Android

Android `TextView` và những thành phần text tương ứng thường có bidi/layout; `textDirection`, `layoutDirection` và một số API hỗ trợ định dạng theo hướng ngữ cảnh có vai trò riêng. Với một đoạn độc lập như địa chỉ email hay mã sản phẩm trong câu RTL, có thể dùng các tiện ích bidi formatting của Android/AndroidX khi API mục tiêu thích hợp.

Không tự áp `java.text.Bidi` rồi đảo chuỗi trước khi gán vào `TextView`. Điều đó có thể làm hỏng caret/selection, dấu câu và copy/paste. Cũng cần phân biệt **layout direction của container** (vị trí icon, nút) với **text direction** (cách phân tích ký tự).

### 8.4. Web/HTML

Nếu Java tạo nội dung đưa sang web, **trình duyệt** là chủ sở hữu của Bidi text layout. HTML có thuộc tính `dir` và phần tử `bdi` để xử lý hướng của nội dung độc lập.

Ví dụ:

```html
<p dir="rtl">
  <span>متن</span>
  <bdi dir="auto">user-123@example.com</bdi>
</p>
```

Ở đây `dir="rtl"` chọn hướng ngữ cảnh của paragraph; `bdi dir="auto"` cô lập hướng của giá trị như một phần tử độc lập. Trình duyệt tính visual order; Java không phải đảo địa chỉ email trước khi đưa vào HTML.

**Chú ý:** render dynamic text trong HTML phải escape/encode đúng để tránh XSS; `bdi` và `dir` không phải biện pháp chống injection, và không nên nối raw user text vào HTML string. Hãy dùng template engine/DOM API có quy tắc escaping an toàn. Nếu không kiểm soát được markup, cần một chính sách tách data và cấu trúc rõ ràng.

### Không đồng nhất direction của container với direction của data

Trong UI RTL, các thành phần như nút điều hướng, icon “back”, thứ tự menu hoặc vùng flex có thể cần layout theo hướng container. Nhưng một URL, địa chỉ email, số tài khoản hoặc mã SKU có thể cần được giữ nhóm và xử lý hướng độc lập. **Đảo layout container** không có nghĩa **đảo code point của mọi String**.

## 9. Embedding, isolate và trường hợp chèn dữ liệu LTR vào câu RTL

### 9.1. Vấn đề thường gặp

Ví dụ bản dịch RTL có một chỗ trống để chèn `orderId` bằng chữ Latin/số. Nếu nối raw text mà không có ngữ cảnh cô lập, dấu câu, ngoặc, dấu gạch hoặc các ký tự neutral cạnh giá trị có thể bị ảnh hưởng bởi đoạn RTL bên ngoài.

Một phương án đúng thường là **cô lập hướng của đoạn độc lập** ở tầng UI hoặc formatting, không đảo `orderId`. Hướng dẫn ở mức thiết kế:

1. Giữ `orderId` đúng logical order để có thể copy và so sánh.
2. Bảo đảm đoạn văn chính có base direction phù hợp với bản dịch.
3. Đặt `orderId` trong vùng có bidi isolation khi UI hỗ trợ, ví dụ `bdi` trên web.
4. Test dấu câu trước/sau, số âm, dấu ngoặc, dấu chấm và dấu phân cách.
5. Đừng chèn control ký tự Unicode nếu widget đã dùng rich-text isolation phù hợp; tránh double handling.

### 9.2. Unicode bidi controls

Unicode có các ký tự điều khiển định hướng, ví dụ:

| Code point | Tên | Mục đích khái quát |
| --- | --- | --- |
| `U+200E` | LEFT-TO-RIGHT MARK (LRM) | Dấu hỗ trợ một ngữ cảnh LTR. |
| `U+200F` | RIGHT-TO-LEFT MARK (RLM) | Dấu hỗ trợ một ngữ cảnh RTL. |
| `U+202A` | LEFT-TO-RIGHT EMBEDDING (LRE) | Bắt đầu embedding LTR kiểu cũ. |
| `U+202B` | RIGHT-TO-LEFT EMBEDDING (RLE) | Bắt đầu embedding RTL kiểu cũ. |
| `U+202D` | LEFT-TO-RIGHT OVERRIDE (LRO) | Ép hướng với một số text; dễ bị lạm dụng. |
| `U+202E` | RIGHT-TO-LEFT OVERRIDE (RLO) | Ép hướng; có rủi ro đánh lừa hiển thị. |
| `U+202C` | POP DIRECTIONAL FORMATTING (PDF) | Kết thúc embedding/override tương ứng. |
| `U+2066` | LEFT-TO-RIGHT ISOLATE (LRI) | Isolate đoạn LTR. |
| `U+2067` | RIGHT-TO-LEFT ISOLATE (RLI) | Isolate đoạn RTL. |
| `U+2068` | FIRST STRONG ISOLATE (FSI) | Chọn hướng isolate dựa vào ký tự mạnh đầu. |
| `U+2069` | POP DIRECTIONAL ISOLATE (PDI) | Kết thúc isolate tương ứng. |

Các isolate Unicode hiện đại giúp tách ảnh hưởng hướng của đoạn được chèn với văn bản xung quanh tốt hơn nhiều trường hợp embedding kiểu cũ. Tuy nhiên, **đó là ký tự dữ liệu thực**, có thể được lưu, copy/paste, ghi log hoặc gửi API; chúng không phải markup của UI.

**Ưu tiên cơ chế isolation của renderer** khi có: `bdi` trên web, bidi formatter chính thức của framework, text spans/paragraph attributes. Chỉ thêm LRI/RLI/FSI/PDI vào plain text khi định dạng text truyền đi thực sự yêu cầu, và bạn đã kiểm tra hành vi của nền tảng nhận. Đảm bảo cặp isolate đóng đúng bằng PDI và tránh tạo nhiều lớp control không kiểm soát.

### 9.3. Vì sao không dùng override để “sửa nhanh”?

`LRO/RLO` can thiệp mạnh vào cách hiển thị hướng. Dùng chúng để “ép” một đoạn text hỗn hợp trông đúng tại một chỗ có thể làm hỏng chỗ khác và khiến nội dung hiển thị khác thứ tự logic. Với dữ liệu từ bên ngoài, chúng còn có rủi ro bảo mật. Không dùng các Unicode override controls như giải pháp mặc định cho UI RTL.

## 10. Cảnh báo bảo mật: chuỗi nhìn thấy có thể đánh lừa người đọc

Bidirectional formatting có tính năng hợp lệ, nhưng một số control characters có thể làm cho thứ tự nhìn thấy **khác đáng kể** với thứ tự logic. Điều này đặc biệt nhạy cảm với:

- Tên file hoặc phần mở rộng file.
- Log của hệ thống bảo mật.
- Chuỗi mã nguồn và comment code.
- Tên user, tên tài liệu, mã đơn hàng.
- Cảnh báo hoặc bản tóm tắt giao dịch cần xác nhận chính xác.

Một số kiểu tấn công **Trojan Source** lợi dụng bidi controls để làm con người đọc một đoạn mã theo thứ tự hiển thị khác với thứ tự compiler xử lý. Giao diện hiển thị đúng Unicode không tự động đảm bảo nội dung không gây nhầm lẫn.

### Nguyên tắc xử lý an toàn

- **Không cấm mọi ký tự RTL**: Hebrew/Arabic và bidi formatting có nhu cầu hợp lệ.
- Có chính sách với các ký tự điều khiển hướng trong trường nhạy cảm; phân biệt text tự do với identifier có grammar hẹp.
- Với một trường chỉ cho phép ID ASCII, **validate ASCII grammar** thay vì cố dùng Bidi để xử lý dữ liệu bất thường.
- Khi audit/log cần nhận diện ký tự điều khiển, có thể thêm một **biểu diễn chẩn đoán** (code point names/hex hoặc escape), nhưng vẫn bảo toàn dữ liệu gốc nếu chính sách lưu trữ yêu cầu.
- Với tên file, mã giao dịch hoặc địa chỉ, tránh để một biểu diễn hình thức đánh lừa bước xác nhận quan trọng.
- Nếu input đi vào HTML hoặc terminal, còn phải xử lý escaping, control characters và injection theo ngữ cảnh; Bidi không thay cho những lớp bảo vệ đó.
- Test trình đọc màn hình và trải nghiệm copy/paste: dữ liệu logic và văn bản hiển thị phải cho phép người dùng kiểm tra điều họ thực sự đang gửi/lưu.

**Bidi là tính năng hiển thị, không phải thao tác thay đổi giá trị nghiệp vụ.** Bộ phận validation và security cần nhận biết bidi controls, nhưng không nên âm thầm “sửa cho dễ nhìn” bằng cách đảo chuỗi hoặc xóa mọi script RTL.

## 11. Bidi và Unicode normalization là hai vấn đề khác nhau

Unicode **normalization** (NFC, NFD, ...) xử lý những dạng biểu diễn code point có quan hệ tương đương chuẩn tắc hoặc tương thích. Nó **không quyết định visual order**, và không biến một đoạn Hebrew/Arabic thành Latin.

Tương tự:

- `toLowerCase(Locale.ROOT)` là case conversion, không phải bidi layout.
- `Collator` là collation/sort theo ngôn ngữ, không phải Bidi.
- `BreakIterator` liên quan phân đoạn text, không phải một bộ render Bidi hoàn chỉnh.
- UTF-8/UTF-16 là encoding, không mang ý nghĩa “vẽ từ phải sang trái”.
- `Bidi` không thay đổi phân tích cú pháp của URL/JSON hay thứ tự tham số của câu dịch.

Khi gặp hiển thị sai, trước tiên phân loại lỗi:

| Triệu chứng | Nguồn vấn đề có thể |
| --- | --- |
| Chữ tiếng Ả Rập không nối đúng | Shaping/font/rendering, không chỉ thứ tự Bidi. |
| Dấu ngoặc/số nằm bất ngờ ở cuối dòng | Base direction, isolation hoặc xử lý neutral characters. |
| Chữ bị `Ã...` | Decode/charset không khớp, không phải Bidi. |
| Cùng chữ khác dãy code point | Normalization, combining marks. |
| Không chọn được đúng đoạn text khi click | Hit-testing/caret logic trong layout engine. |
| Chuỗi copy ra có thứ tự khác hình vẽ | Khác biệt logical order vs visual order; cần xem pipeline copy. |
| UI bị đảo toàn bộ nút điều hướng | Layout direction/container, không nhất thiết text Bidi. |
| Icon hoặc dấu câu gắn sai với SKU | Hướng của token, isolation và ngữ cảnh kế cận. |

Bước sửa đúng phụ thuộc tầng gây lỗi, không phải cứ lỗi text là gọi `Bidi` và đảo thứ tự ký tự.

## 12. Thiết kế ứng dụng: chuỗi logic, locale, hướng và layout

Một thiết kế sạch cho text hỗn hợp có thể gồm:

1. **Model:** lưu chuỗi logic và các biến định danh theo schema.
2. **ResourceBundle/translator:** chọn thông điệp, giữ thứ tự tham số và cách diễn đạt đúng ngôn ngữ.
3. **UI adapter:** nhận locale, paragraph direction hoặc layout direction và các ranh giới isolate cần thiết.
4. **Text layout engine:** xử lý bidi, shaping, line breaks, glyph placement, caret và selection.
5. **Input handling:** trả lại chuỗi logic và metadata cần thiết, không lấy visual reordering làm giá trị lưu.
6. **Security/validation:** kiểm tra identifier, control chars nhạy cảm và chính sách hiển thị, log/audit.
7. **QA:** test các tổ hợp RTL/LTR, số, dấu câu và rich text.

### Ví dụ “đúng vai trò” khi gắn một ID vào bản dịch

Giả sử `orderId` là `AB-1234/56` và ứng dụng có bản dịch RTL:

- Thông điệp trong bản dịch giữ placeholder cho ID.
- ID được lưu là `AB-1234/56`, không đảo thành `65/4321-BA`.
- UI nhận đoạn ID như nội dung độc lập và áp isolation khi cần.
- Renderer quyết định thứ tự glyph và caret; app không tự ghép visual runs thành một chuỗi thay thế.
- Khi người dùng copy ID, clipboard nhận đúng `AB-1234/56` theo logical order.
- Khi backend xử lý, validation kiểm tra ID theo grammar, không dựa vào ảnh chụp hoặc visual order.

Một phép thử nên xác minh **đúng giá trị được copy và gửi**, không chỉ “mắt nhìn thấy hợp lý” trên một kích thước màn hình.

## 13. Lỗi thường gặp và cách tránh

| Lỗi | Vì sao không đúng | Hướng khắc phục |
| --- | --- | --- |
| Thấy chữ RTL là gọi `StringBuilder.reverse()` | Đảo code unit/grapheme không phải Unicode Bidi; có thể phá thứ tự dữ liệu logic. | Giữ String, giao layout cho renderer. |
| Tự reorder các run rồi đưa vào UI cũng xử lý Bidi | Có thể xảy ra double reordering, sai dấu câu và wrap. | Chọn một tầng sở hữu layout. |
| Dùng `Bidi` để “vẽ chữ” | `Bidi` chỉ phân tích hướng, không shaping/glyph placement. | Dùng text layout/shaping engine. |
| Chuyển String sang visual order trước khi lưu DB | Search, copy, serialize và accessibility sai. | Lưu logical order. |
| Nghĩ `Locale` quyết định toàn bộ base direction | Locale ngôn ngữ, text direction và UI layout là ngữ cảnh khác nhau. | Đặt paragraph/container direction tường minh. |
| Dùng direction của container để đảo mọi giá trị | URL, email, ID có thể cần xử lý riêng. | Cô lập các token độc lập trong dòng. |
| Chèn LRO/RLO bừa bãi | Gây override mạnh, rủi ro hiểu sai/hijack hiển thị. | Dùng isolation API phù hợp. |
| Tin `Bidi.requiresBidi` là bước bắt buộc của mọi TextView | Text component thường đã phân tích và layout. | Không chạy thuật toán trùng khi không cần. |
| Tự tính caret bằng index hiển thị | Visual order không đồng nhất UTF-16 offset. | Dùng hit-testing/caret API của layout engine. |
| Coi dấu câu sai là font thiếu glyph | Thường là hướng/isolation, không đơn thuần font. | Chẩn đoán từng tầng. |
| Loại toàn bộ chữ Hebrew/Arabic để tránh Trojan Source | Chặn nội dung hợp lệ và phân biệt script với controls. | Chính sách nhắm đúng ký tự điều khiển và trường rủi ro. |
| Chỉ test một dòng cố định | Wrap, font và kích thước màn hình đổi kết quả. | Test nhiều chiều rộng, nhiều nội dung. |

## 14. Kiểm thử Bidi khi giao diện đã có layout engine

Để kiểm thử đúng chức năng, phân biệt **unit test trên dữ liệu logic** với **integration/UI test trên renderer**.

| Loại test | Giá trị đầu vào | Điều cần xác nhận |
| --- | --- | --- |
| Java unit | `"ABC "` + ba chữ Hebrew | `Bidi` nhận diện run và level đúng trong môi trường thử. |
| String model | RTL/LTR hỗn hợp | Dữ liệu gốc không bị đảo khi đi qua pipeline. |
| UI integration | Câu RTL chứa ID Latin | ID hiển thị và copy đúng, dấu câu không tràn sang phần sai. |
| UI integration | Câu LTR chứa tên Arabic/Hebrew | Chữ nối/dấu/đọc đúng theo font và script. |
| UI responsive | Cùng text trên nhiều chiều rộng | Wrap và caret đúng sau reflow. |
| UI direction | Container LTR/RTL | Layout navigation/icon và text direction được xử lý riêng. |
| Formatting | Số, thời gian, dấu âm, URL và email | Ranh giới token đúng, không gây thay đổi byte của ID. |
| Keyboard | Di chuyển caret, chọn đoạn, Backspace/Delete | Không làm hỏng grapheme hoặc chọn nhầm vị trí. |
| Clipboard | Copy/paste token lẫn hướng | Dữ liệu logical order được giữ. |
| Accessibility | Screen reader và selection | Thứ tự đọc phản ánh nội dung và ngữ nghĩa. |
| Security | U+202E, isolate không đóng, các control nhạy cảm | Chính sách nhận diện và hiển thị/audit rõ ràng. |
| Unicode | Emoji ZWJ, combining marks, surrogate pairs | Không tách hỏng cụm ký tự. |

### Unit test Bidi không thay thế UI test

Trong chương trình Java ở mục 5, `getRunCount()==2` chứng minh parser nhận diện những run cụ thể. Nó **không** chứng minh:

- Phần chữ Hebrew được vẽ đúng glyph trên font mục tiêu.
- Dấu câu trong bản dịch thực được đặt đúng sau line wrapping.
- Chọn text bằng chuột/caret trả về offset logic đúng.
- HTML `bdi` hoặc một Android TextView được cấu hình đúng.
- Trường hợp emoji, dấu tổ hợp, URL và ký tự điều khiển hướng thực tế đều có kết quả tốt.

Chỉ integration/UI tests trên renderer thực tế mới xác minh được các yêu cầu ấy. Khi test UI, tránh dựa duy nhất vào snapshot hình ảnh: nên đối chiếu thêm nội dung clipboard, offset selection và ID đã gửi backend.

## 15. Bài tập tự luyện

**Bài 1 — Logical vs visual:** tạo chuỗi `"ABC \u05D0\u05D1\u05D2"`. Dùng `java.text.Bidi` để in base level, số run, run start/limit/level. Viết giải thích vì sao không nên tạo một String mới từ các run để đưa vào một component đã hỗ trợ Bidi.

**Bài 2 — Thay base direction:** thử `DIRECTION_LEFT_TO_RIGHT`, `DIRECTION_RIGHT_TO_LEFT` và `DIRECTION_DEFAULT_LEFT_TO_RIGHT` trên một câu có ký tự mạnh đầu khác nhau. Ghi nhận các neutral characters gần dấu chấm, dấu ngoặc, số. Không nhầm base direction với locale.

**Bài 3 — UI RTL chứa mã đơn hàng:** tạo bản dịch RTL có `orderId="AB-1234/56"`. Dùng cơ chế isolation thích hợp của UI, so sánh với phiên bản chỉ nối raw text; kiểm tra copy/paste và hiển thị trên màn hình hẹp. Không đảo giá trị orderId.

**Bài 4 — HTML:** tạo trang có `dir="rtl"` và một token `bdi dir="auto"`. Kiểm tra khi token bắt đầu bằng Latin, Arabic hoặc ký tự neutral. Nhận xét trường hợp cần hướng tường minh thay vì auto. Bảo đảm render dynamic text bằng escaping an toàn.

**Bài 5 — Text editor:** với một ô nhập văn bản hỗn hợp, thử con trỏ ở ranh giới run, chọn đoạn, xóa ký tự, dán emoji gồm nhiều code point và thay kích thước cửa sổ. Ghi nhận lỗi nếu app tự tính vị trí pixel từ UTF-16 offset.

**Bài 6 — Kiểm tra controls:** tạo dữ liệu thử chứa `U+202E`, `U+2066` và `U+2069` trong một môi trường test an toàn. Quan sát hiển thị và cách log một chuỗi ở dạng code point. Thiết kế chính sách cho tên file/identifier, phân biệt control có thể gây hiểu nhầm với chữ RTL hợp lệ.

**Bài 7 — So sánh tầng lỗi:** mô tả ba trường hợp: Arabic không nối chữ, UTF-8 bị decode sai dẫn đến `Ã...`, và dấu ngoặc nằm sai trong text RTL/LTR. Xác định lần lượt shaping, charset hay Bidi/isolation là tầng cần chẩn đoán.

### Checklist hoàn thành

- [ ] Hiểu logical order khác visual order và không đảo String để “sửa” RTL.
- [ ] Biết `java.text.Bidi` phân tích embedding levels/runs, không tự shaping hay vẽ.
- [ ] Phân biệt base direction, locale, layout direction và text direction.
- [ ] Không chạy reordering lần hai khi UI đã có text layout engine.
- [ ] Sử dụng khả năng isolation của UI cho token độc lập khi cần.
- [ ] Không trộn Unicode control characters vào dữ liệu một cách tùy tiện.
- [ ] Biết cách nhận diện bidi controls nguy hiểm ở dữ liệu nhạy cảm mà không cấm chữ RTL hợp lệ.
- [ ] Chọn tầng xử lý đúng: model, localization, text layout, input/clipboard, security.
- [ ] Kiểm thử render thực tế, wrap, caret, copy/paste, font và accessibility.
- [ ] Biết khi nào `Bidi` core hữu ích: xây dựng/chẩn đoán text layout chuyên dụng, không phải thay thế widget đã hỗ trợ Bidi.

**Kết luận:** khi giao diện đã có **bộ bố trí văn bản xử lý Bidi**, ứng dụng nên **giữ text theo logical order**, cung cấp paragraph direction/isolation thích hợp và để renderer quyết định visual order, shaping, line break và caret. `java.text.Bidi` là công cụ **phân tích** hữu ích khi thật sự cần điều khiển pipeline, không phải bước phải chạy thêm cho mọi String RTL và càng không phải lý do để đảo hay ghi đè dữ liệu ký tự.
