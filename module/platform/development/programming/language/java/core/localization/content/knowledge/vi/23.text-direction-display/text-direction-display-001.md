# Thứ tự logic so với thứ tự hiển thị trong văn bản hai chiều (BiDi) — Java localization

## 1. Vì sao một chuỗi có thể được hiển thị không theo thứ tự lưu?

Trong Unicode, **thứ tự logic (logical order)** là thứ tự các ký tự/code point xuất hiện trong dữ liệu nguồn. Đó là thứ tự mà chương trình thường đọc qua `String`, duyệt `codePoints()`, lưu vào cơ sở dữ liệu, gửi trên mạng và phân tích cú pháp.

**Thứ tự hiển thị (visual order)** là cách các thành phần của văn bản được bố trí từ trái sang phải hoặc từ phải sang trái trên một dòng khi được **render** cho người đọc. Với ngôn ngữ viết từ trái sang phải (**LTR**) như tiếng Việt hoặc tiếng Anh, hai thứ tự thường trông giống nhau. Với ngôn ngữ viết từ phải sang trái (**RTL**) như Hebrew hoặc Arabic, và đặc biệt khi trộn RTL với chữ Latin/chữ số, chúng **không nhất thiết trùng nhau**.

Một đoạn văn bản có thể chứa:

- Chữ Latin (thường LTR).
- Chữ Hebrew hoặc Arabic (thường RTL).
- Các chữ số `123` thường được thể hiện theo thứ tự LTR ngay cả bên trong đoạn RTL.
- Dấu cách, ngoặc, dấu hai chấm, dấu gạch ngang và những ký hiệu có hướng hiển thị được xác định từ **ngữ cảnh**.
- Các ký tự điều khiển chiều Unicode không tạo glyph hiển thị nhưng có thể ảnh hưởng cách người đọc thấy chuỗi.

Ví dụ minh họa về **thứ tự logic**:

~~~text
Nguồn lưu theo thứ tự:
"a" "b" "c" " " ALEF BET GIMEL " " "1" "2" "3" " " "x" "y" "z"

ALEF = U+05D0, BET = U+05D1, GIMEL = U+05D2 (Hebrew)

Trong một dòng có hướng nền LTR:
- Đoạn "abc " ở mức LTR.
- Đoạn Hebrew ở mức RTL.
- Đoạn chữ số "123" ở mức LTR lồng bên trong.
- Đoạn " xyz" lại ở mức LTR.
~~~

Không nên dự đoán thứ tự màn hình bằng cách đảo toàn bộ `String`, cũng không nên dựa vào cách console hiển thị các glyph Hebrew trong một ảnh chụp. Phần mềm render có thể áp dụng **Unicode Bidirectional Algorithm (UAX #9)** và tính chất của từng đoạn, kiểu chữ, ký hiệu, chiều nền và cách ngắt dòng.

**Kết luận đầu tiên:** BiDi là vấn đề **bố trí văn bản khi hiển thị**, không phải quy tắc đảo chuỗi để lưu trữ. Người dùng có thể thấy glyph theo một thứ tự không trùng với thứ tự từng ký tự trong dữ liệu, nhưng văn bản vẫn có một thứ tự logic nhất quán để trao đổi giữa các hệ thống.

## 2. Bốn khái niệm phải phân biệt

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Logical order | Thứ tự các code point/code unit trong dữ liệu | `abc`, tiếp đến Hebrew `U+05D0 U+05D1 U+05D2`, rồi `123` |
| Base paragraph direction | Hướng nền của đoạn văn (LTR hoặc RTL) | Một nội dung tiếng Việt có thể dùng nền LTR; một đoạn Arabic có thể chọn RTL |
| Embedding level / directional run | Mức lồng của các đoạn có quy tắc hiển thị giống nhau | Level chẵn thường LTR; level lẻ thường RTL |
| Visual order | Thứ tự bố trí các run/glyph sau thuật toán, phân dòng và shaping | Trong ví dụ Java, run chữ số có thể được trình bày trước run Hebrew trong dòng LTR |

Đừng nhầm **hướng của đoạn** với **hướng từng ký tự**. Một đoạn RTL vẫn có thể chứa từ `Java` hoặc số `123` cần giữ thứ tự LTR nội tại. Ngược lại, một đoạn LTR có thể chứa một cụm Hebrew/Arabic RTL.

### 2.1. Thứ tự logic là thứ tự dữ liệu

Giả sử:

~~~java
String hebrew = "\u05D0\u05D1\u05D2";
String paragraph = "abc " + hebrew + " 123 xyz";
~~~

Hai lệnh này là **snippet** trong phương thức, không phải class độc lập. Trong `String` Java, thứ tự UTF-16 của đoạn gồm `abc`, dấu cách, ba chữ Hebrew, dấu cách, ba chữ số, dấu cách, `xyz`.

Các API như `length()`, `charAt()`, `substring()`, `indexOf()`, `codePoints()`, `equals()` và serializing **không chuyển sang thứ tự hiển thị** chỉ vì chuỗi có chữ RTL. Những API đó làm việc với nội dung logic theo hợp đồng Java.

### 2.2. Base direction không phải Locale

`Locale.forLanguageTag("ar")` mô tả locale Arabic; `Locale.forLanguageTag("he")` mô tả locale Hebrew. Nhưng một **language tag không tự quyết định đầy đủ hướng bố trí cho mọi đoạn văn thực tế**: một chuỗi có thể gồm chỉ số, mã hàng, từ Latin hoặc nội dung do người dùng nhập. Trong giao diện, hướng đoạn (`dir`) và hướng của các mảnh chèn phải dựa trên **ngữ nghĩa và context layout**, không chỉ đổi `Locale`.

`Locale` hữu ích khi chọn văn bản/nguồn dịch và quy ước văn hóa; còn BiDi xử lý tính chất chiều của **dữ liệu text và container**.

## 3. Unicode Bidirectional Algorithm (UAX #9) hoạt động ở mức khái niệm

Thuật toán Unicode BiDi phân tích các ký tự theo thuộc tính hướng và ngữ cảnh để tính **embedding levels** và thứ tự hiển thị theo từng dòng. Luồng tổng quát:

1. Xác định **ranh giới đoạn văn** và **hướng nền** (base direction).
2. Phân loại ký tự theo thuộc tính bidi: mạnh LTR, mạnh RTL, số/định dạng yếu, neutral và điều khiển.
3. Xử lý các thông tin explicit embedding/override/isolate (nếu có).
4. Giải quyết hướng của ký tự yếu hoặc neutral theo những ký tự xung quanh và các quy tắc Unicode.
5. Xác định **level** của các đơn vị văn bản: level **chẵn** diễn đạt hướng LTR, level **lẻ** diễn đạt RTL.
6. Sau khi biết ranh giới dòng, bố trí lại thứ tự các đoạn theo level cho **mỗi dòng**, kết hợp shaping, glyph và line layout từ renderer.

Sơ đồ khái niệm:

~~~text
Chuỗi Unicode (thứ tự logic trong bộ nhớ)
            |
            v
  Hướng nền + ký tự mạnh/yếu/trung tính
            |
            v
  Unicode BiDi -> embedding levels
            |
            v
  Phân dòng -> reorder theo levels
            |
            v
  Font/shaping/glyph layout -> màn hình

Chuỗi nguồn vẫn ở thứ tự logic.
~~~

**Không phải cứ level 1 là “đảo mọi code point bằng tay”**. BiDi cùng với text shaping có các quy tắc để giữ dấu tổ hợp, ligature, ngoặc, mirrored glyph và con trỏ/caret đúng ngữ nghĩa. Một `StringBuilder.reverse()` không thay thế thuật toán này.

### 3.1. Strong, weak và neutral

- **Strong:** chữ Latin thường có direction class L; Hebrew thường R; Arabic thường AL. Chúng đóng vai trò quyết định hướng của những vùng lân cận.
- **Weak:** các chữ số và một số ký hiệu số có thể phụ thuộc ngữ cảnh; không nên xem mọi ký tự số là một “ký tự RTL” vì nằm trong câu Arabic.
- **Neutral:** dấu cách, nhiều dấu câu, dấu ngoặc... có thể nhận level theo các ký tự bao quanh.
- **Formatting controls:** một số code point như `U+2066`, `U+2067`, `U+2068`, `U+2069` dùng để quản lý isolate; chúng thường không hiện glyph nhưng vẫn là **ký tự thực trong chuỗi**.

Vì các loại weak/neutral lấy ngữ cảnh, nội dung thay đổi rất nhỏ (thêm tên người, mã hóa đơn, dấu `:` hoặc ngoặc) cũng có thể làm ký tự di chuyển hoặc trông bị đổi chiều.

### 3.2. Paragraph direction và ký tự mạnh đầu tiên

Nếu ứng dụng để hướng nền **tự xác định từ ký tự mạnh đầu tiên**, một dòng bắt đầu bằng Latin có thể chọn LTR, còn dòng bắt đầu bằng Hebrew/Arabic có thể chọn RTL. Tuy nhiên text không có strong character, ví dụ chỉ chứa số và dấu câu, cần **hướng fallback** theo chính sách container hoặc flag.

Trong Java, `java.text.Bidi` có bốn hằng:

| Cờ `Bidi` | Vai trò |
| --- | --- |
| `DIRECTION_LEFT_TO_RIGHT` | Ép base direction LTR |
| `DIRECTION_RIGHT_TO_LEFT` | Ép base direction RTL |
| `DIRECTION_DEFAULT_LEFT_TO_RIGHT` | Chọn theo strong char đầu tiên; fallback LTR nếu không có |
| `DIRECTION_DEFAULT_RIGHT_TO_LEFT` | Chọn theo strong char đầu tiên; fallback RTL nếu không có |

Dùng cờ `DIRECTION_DEFAULT_...` không có nghĩa **mọi ký tự trong đoạn đều đổi thành cùng một hướng**. Nó chỉ quyết định hướng nền. Các run LTR/RTL bên trong vẫn được giải quyết bằng thuật toán.

## 4. Java SE 17: java.text.Bidi để phân tích chiều, không đổi dữ liệu

Lớp `java.text.Bidi` triển khai thuật toán hai chiều dùng trong layout. Nó cung cấp thông tin về **base level**, **run boundaries** và **run levels**, không phải một bộ API dựng thành hình ảnh hoàn chỉnh.

~~~java
import java.text.Bidi;

String text = "abc " + "\u05D0\u05D1\u05D2" + " 123 xyz";

Bidi bidi = new Bidi(
        text, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);
~~~

Đây là **đoạn lệnh minh họa trong một phương thức**, cần import như trên; chương trình độc lập ở mục 8.

### 4.1. Các method quan trọng

| API | Cách hiểu |
| --- | --- |
| `new Bidi(String, flags)` | Phân tích một đoạn văn với hướng nền được yêu cầu |
| `baseIsLeftToRight()` | Trả true nếu hướng nền LTR |
| `getBaseLevel()` | Level nền: 0 cho LTR, 1 cho RTL |
| `isLeftToRight()` | Đoạn/dòng thuần LTR với nền LTR |
| `isRightToLeft()` | Đoạn/dòng thuần RTL với nền RTL |
| `isMixed()` | Không thuộc hai trường hợp thuần trên; thường có hướng trộn hoặc nền khác hướng run |
| `getRunCount()` | Số directional runs |
| `getRunStart(i)` | Offset UTF-16 bắt đầu run thứ i theo thứ tự logic |
| `getRunLimit(i)` | Offset UTF-16 **ngay sau** run i |
| `getRunLevel(i)` | Embedding level của run i |
| `getLevelAt(offset)` | Level đã resolve tại offset UTF-16 |
| `createLineBidi(start, limit)` | Tạo Bidi information cho một **dòng** của đoạn văn |
| `requiresBidi(char[], start, limit)` | Kiểm tra liệu đoạn ký tự có cần phân tích bidi |
| `reorderVisually(levels, ..., objects, ...)` | Sắp xếp lại **các object** theo level, ví dụ danh sách directional runs |

**Chỉ số `getRunStart`, `getRunLimit`, `getLevelAt` dùng UTF-16 offsets.** Đây là điều quan trọng khi áp dụng lên `String.substring(start, limit)` hoặc chuyển giữa các API `char`/code point của Java.

### 4.2. Level chẵn và lẻ

Trong hệ Unicode BiDi:

- Level `0`: LTR ở lớp nền thông thường.
- Level `1`: RTL.
- Level `2`: LTR được lồng trong một ngữ cảnh RTL.
- Level `3`: RTL lồng sâu hơn, v.v.

Một câu **không phải chỉ có một level**. Dữ liệu chứa Hebrew và chữ số trong cùng một câu có thể xuất hiện run mức `1` và mức `2`; đặt một flag base `LTR` không xóa bỏ các mức đó.

Không giả định `getRunCount()` chính là số từ, số Unicode code point hay số phần tử cần chọn trong UI. Run là đơn vị liên tiếp theo **resolved bidi level**, không phải token ngôn ngữ.

### 4.3. Tại sao không tự reverse chuỗi?

Một cách làm sai:

~~~java
String reversed = new StringBuilder(text).reverse().toString();
~~~

Đây là ví dụ **không nên dùng** để hiển thị BiDi. Reverse sửa **thứ tự logic** và tạo dữ liệu mới; nó không có thuật toán xử lý base direction, weak/neutral characters, isolate boundaries, shaping hoặc phân dòng. Ngay cả khi một vài chữ Hebrew trông “đúng” trên terminal trong ví dụ ngắn, các chuỗi trộn chữ số/dấu/Latin sẽ dễ lỗi.

Điều đúng là giữ `String` logic và giao cho UI renderer hỗ trợ Unicode BiDi bố trí văn bản. `java.text.Bidi` hữu ích khi bạn **đang viết thành phần layout riêng** hoặc cần debug các run/level.

## 5. Visual runs và thứ tự của chữ số trong đoạn RTL

Với chuỗi demo:

~~~text
logical = "abc " + HEBREW(aleph,bet,gimel) + " 123 xyz"
UTF-16 length = 15
base = LTR
~~~

Các run được tính bởi Java trên JDK kiểm thử:

| Run theo thứ tự logic | UTF-16 khoảng [start, limit) | Level | Nội dung logic |
| --- | --- | --- | --- |
| `r0` | `[0,4)` | 0 (LTR) | `abc ` |
| `r1` | `[4,8)` | 1 (RTL) | 3 chữ Hebrew và dấu cách |
| `r2` | `[8,11)` | 2 (LTR) | `123` |
| `r3` | `[11,15)` | 0 (LTR) | ` xyz` |

**Thứ tự run logic:** `r0, r1, r2, r3`.

Sau khi xét levels để **sắp xếp các đối tượng run cho hiển thị trong một dòng**, `Bidi.reorderVisually` cho:

~~~text
visual run order = r0, r2, r1, r3
~~~

Điều này **không đồng nghĩa** chuỗi được lưu có `"123"` trước Hebrew. Chuỗi nguồn vẫn chứa Hebrew trước `123`. Bố trí trên một dòng xét level 1 RTL bao quanh run level 2 LTR, khiến thứ tự các **run object** thay đổi.

Đừng kết luận rằng từ Hebrew được hiển thị bằng việc đảo từng Unicode code point một cách tùy tiện. Renderer có thể áp dụng xử lý ký tự kết hợp, contextual shaping và glyph placement riêng. Bảng trên mô tả **run-level reordering**, không mô tả tọa độ pixel hoặc toàn bộ hình dáng cuối.

Nếu đoạn văn được xuống nhiều dòng, Unicode BiDi làm việc theo **từng dòng** sau khi break, vì vậy một bảng run cho cả paragraph không đủ mô tả hết hình ảnh. `createLineBidi` có ích khi layout engine đã biết ranh giới dòng.

## 6. Unicode controls: khi nào cần và vì sao phải thận trọng?

Trong đa số văn bản tự nhiên, thuật toán BiDi dựa trên strong/weak/neutral types là đủ. Khi một mảnh văn bản độc lập có hướng chưa biết được chèn vào câu theo ngữ cảnh khác, đôi khi cần **isolation** để nó không gây ảnh hưởng không mong muốn lên dấu câu hoặc phần text xung quanh.

Một số mã điều khiển phổ biến:

| Code point | Tên | Ý nghĩa khái quát |
| --- | --- | --- |
| `U+200E` | LRM — Left-to-Right Mark | Dấu hướng LTR không có glyph |
| `U+200F` | RLM — Right-to-Left Mark | Dấu hướng RTL không có glyph |
| `U+061C` | ALM — Arabic Letter Mark | Dấu hướng Arabic không có glyph |
| `U+2066` | LRI — Left-to-Right Isolate | Bắt đầu isolate LTR |
| `U+2067` | RLI — Right-to-Left Isolate | Bắt đầu isolate RTL |
| `U+2068` | FSI — First Strong Isolate | Bắt đầu isolate tự xác định từ strong char |
| `U+2069` | PDI — Pop Directional Isolate | Đóng một isolate |
| `U+202A`/`U+202B` | LRE/RLE | Embedding kiểu cũ |
| `U+202D`/`U+202E` | LRO/RLO | Override hướng, rủi ro gây nhầm hiển thị |
| `U+202C` | PDF | Kết thúc embedding/override |

Isolate `FSI`/`PDI` (hoặc `LRI`/`RLI` với hướng đã biết) được khuyến nghị cho văn bản thuần có mảnh chèn tự do khi thật sự cần điều khiển chiều. Các cơ chế embedding/override cũ dễ tác động đến phần xung quanh mạnh hơn cần thiết.

**Không nên tự thêm ký tự vô hình vào dữ liệu giao dịch/định danh khi chưa có contract.** Những code point ấy được lưu, có thể đi qua copy/paste/URL hoặc ảnh hưởng kết quả so sánh chuỗi, chữ ký, tìm kiếm và audit. Trong HTML, thường nên dùng **thuộc tính hướng và các phần tử semantic** thay vì chèn control characters trực tiếp.

### 6.1. HTML: tách phần tử theo hướng bằng bdi, dir

Trong UI HTML, khi chèn tên hoặc mã có hướng không biết vào một câu, một mẫu hữu ích:

~~~html
<p dir="rtl">
  <span>...</span>
  <bdi dir="auto">user-supplied-name</bdi>
  <span>...</span>
</p>
~~~

Đây là **mã HTML minh họa**, trong thực tế các chuỗi người dùng phải được **escape hoặc chèn bằng textContent** để tránh HTML injection. `<bdi>` cô lập hướng của nội dung khỏi ngữ cảnh xung quanh; `dir="auto"` chọn hướng dựa trên nội dung. Với chuỗi luôn LTR như code/ID, có thể cân nhắc phần tử riêng `dir="ltr"` hoặc cơ chế CSS đúng theo component.

Không dùng `text-align: right` như một cách thay thế cho **direction**: căn lề là vấn đề bố cục, không giải quyết thứ tự các ký tự và neutral punctuation trong nội dung.

## 7. Dữ liệu, chỉ số, caret và vấn đề bảo mật

### 7.1. Đừng đổi logical index sang visual index bằng phép đảo đơn giản

Nhiều API Java dùng **UTF-16 offsets** để định vị:

~~~java
int index = paragraph.indexOf("123");  // UTF-16 offset trong chuỗi gốc
~~~

Trong đoạn demo, `index` là 8. Dù trên màn hình run `123` có thể được đặt trước run Hebrew, `indexOf("123")` vẫn trả **8**, không tự chuyển sang tọa độ hình ảnh.

Caret, selection, highlight, delete/backspace và click chuột trong văn bản BiDi cần **mapping giữa logical positions và visual caret positions** do text layout/editor engine thực hiện. Một visual position có thể tương ứng những vị trí logic khác nhau ở ranh giới run; không dùng công thức `length - index` hoặc thứ tự run để tự điều khiển caret.

Trong Swing/AWT hoặc các renderer khác, nên dựa vào thành phần text/layout hỗ trợ BiDi và shaping thay vì tự viết lại toàn bộ thuật toán.

### 7.2. Đừng “sửa” dữ liệu Hebrew/Arabic bằng cách đảo chuỗi trước khi lưu

Trình duyệt/renderer có thể hiển thị một câu RTL theo thứ tự khác so với thứ tự code point. Điều đó không phải bằng chứng dữ liệu sai.

Nếu tự reverse văn bản trước khi lưu:

- Copy/paste qua hệ thống khác có thể tạo một chuỗi không đúng trật tự logic.
- Tìm kiếm, trích xuất, so sánh và xử lý ngôn ngữ bị sai.
- Chuỗi trộn số, Latin, dấu ngoặc và chữ RTL dễ hiển thị lộn xộn hơn.
- Khi renderer áp dụng BiDi lần nữa, hiệu ứng có thể giống “đảo hai lần”.

**Giữ nguyên thứ tự logic** và xử lý vấn đề presentation tại UI boundary.

### 7.3. BiDi control characters có thể bị lạm dụng

Các control ký tự vô hình như `U+202E` (RLO) hoặc một số tổ hợp isolate/override có thể làm **văn bản hiển thị khác thứ tự dữ liệu được parser hoặc compiler đọc**. Đây là một lớp rủi ro trong review source code, filename, extension, log, ID, URL và nội dung do người dùng nhập. Ví dụ, một tên file có điều khiển chiều có thể trông như mang phần mở rộng khác với cấu trúc byte hoặc `String` thực sự.

Nguyên tắc bảo vệ:

1. **Kiểm tra source/log theo thứ tự logic** hoặc hiển thị các format controls dưới dạng tên mã rõ ràng trong trình xem an toàn.
2. **Không tin ký tự đang nhìn bằng mắt** làm bằng chứng cho tên file, domain, extension, lệnh hoặc nội dung chữ ký.
3. Với các trường nhạy cảm (identifier, source code, extension, đường dẫn, token), cân nhắc **từ chối hoặc cảnh báo** ký tự điều khiển bidi không được phép theo chính sách riêng; không xóa bừa trong văn bản tự nhiên.
4. Khi render dữ liệu người dùng trong HTML, vẫn phải escape chống injection; isolation BiDi **không** thay thế HTML escaping.
5. Các quy tắc phân biệt confusable, Unicode normalization, canonicalization và kiểm soát quyền truy cập là những nhiệm vụ riêng; đừng tưởng `Bidi` tự giải quyết chúng.

### 7.4. Tìm kiếm và collation vẫn dựa trên dữ liệu logic

`String.equals`, `indexOf`, tokenization và `Collator` xử lý chuỗi theo hợp đồng API tương ứng, không dựa trên **thứ tự glyph đang nhìn thấy trên màn hình**. Thuật toán sắp xếp từ theo locale cũng không phải cùng một nhiệm vụ với Unicode BiDi.

Một đoạn RTL trông bị đảo khi paste không có nghĩa nên sort các code point theo vị trí hiển thị. Hãy tách **data model**, **search/collation** và **text layout**.

## 8. Ví dụ Java 17 chạy độc lập: Bidi runs, level và visual order

Tạo file **`BidiOrderDemo.java`** với nội dung:

~~~java
import java.text.Bidi;
import java.util.Arrays;
import java.util.Locale;
import java.util.stream.Collectors;

public class BidiOrderDemo {
    static String codePoints(String s) {
        return s.codePoints()
                .mapToObj(cp -> String.format(Locale.ROOT, "U+%04X", cp))
                .collect(Collectors.joining(" "));
    }

    public static void main(String[] args) {
        String hebrew = "\u05D0\u05D1\u05D2";
        String paragraph = "abc " + hebrew + " 123 xyz";
        Bidi bidi = new Bidi(
                paragraph, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);

        System.out.println("logical code points: " + codePoints(paragraph));
        System.out.println("utf16 length=" + paragraph.length());
        System.out.println("requiresBidi=" + Bidi.requiresBidi(
                paragraph.toCharArray(), 0, paragraph.length()));
        System.out.println("base level=" + bidi.getBaseLevel());
        System.out.println("isMixed=" + bidi.isMixed());
        System.out.println("run count=" + bidi.getRunCount());

        Object[] names = new Object[bidi.getRunCount()];
        byte[] levels = new byte[bidi.getRunCount()];
        for (int i = 0; i < bidi.getRunCount(); i++) {
            int start = bidi.getRunStart(i);
            int end = bidi.getRunLimit(i);
            int level = bidi.getRunLevel(i);
            names[i] = "r" + i;
            levels[i] = (byte) level;
            System.out.println("run " + i + ": [" + start + "," + end
                    + ") level=" + level
                    + " codes=" + codePoints(
                            paragraph.substring(start, end)));
        }

        Bidi.reorderVisually(levels, 0, names, 0, names.length);
        System.out.println("run order on display=" +
                Arrays.toString(names));

        Bidi rtl = new Bidi(
                hebrew, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);
        System.out.println("hebrew base level=" + rtl.getBaseLevel());
        System.out.println("hebrew rightToLeft=" + rtl.isRightToLeft());
        System.out.println("storage unchanged=" +
                paragraph.equals("abc " + hebrew + " 123 xyz"));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 BidiOrderDemo.java
java BidiOrderDemo
~~~

**Stdout đã kiểm tra** trên JDK có thuật toán BiDi tương ứng:

~~~text
logical code points: U+0061 U+0062 U+0063 U+0020 U+05D0 U+05D1 U+05D2 U+0020 U+0031 U+0032 U+0033 U+0020 U+0078 U+0079 U+007A
utf16 length=15
requiresBidi=true
base level=0
isMixed=true
run count=4
run 0: [0,4) level=0 codes=U+0061 U+0062 U+0063 U+0020
run 1: [4,8) level=1 codes=U+05D0 U+05D1 U+05D2 U+0020
run 2: [8,11) level=2 codes=U+0031 U+0032 U+0033
run 3: [11,15) level=0 codes=U+0020 U+0078 U+0079 U+007A
run order on display=[r0, r2, r1, r3]
hebrew base level=1
hebrew rightToLeft=true
storage unchanged=true
~~~

**Giải thích:**

1. `logical code points` in mã Unicode theo thứ tự **thực sự lưu** trong `String`; không in glyph Hebrew để tránh console có layout BiDi làm nhầm output.
2. Độ dài `15` là **15 đơn vị UTF-16**; các ký tự trong ví dụ nằm ở BMP.
3. `requiresBidi=true` vì đoạn trộn có ký tự RTL cần phân tích chiều.
4. Ký tự mạnh đầu tiên thuộc Latin, nên base level là `0` (LTR); `isMixed=true` vì có nhiều hướng.
5. Các run `r0`–`r3` được liệt kê **theo logic**, với `[start,limit)` trong UTF-16 indices.
6. `reorderVisually` thay thứ tự **mảng `names` mô tả các run**, tạo `[r0, r2, r1, r3]` cho một dòng. Nó **không** sửa `paragraph`, không render glyph và không tạo một câu đã được shaping hoàn chỉnh.
7. Khi chỉ chứa Hebrew, strong char đầu tiên là RTL nên base level là `1`, và `isRightToLeft()` là `true`.
8. `storage unchanged=true` xác nhận quá trình phân tích và sắp xếp mảng tên run không làm thay chuỗi nguồn.

**Khuyến cáo:** kết quả level và run có thể phụ thuộc phiên bản thuật toán/dữ liệu Unicode trong runtime và ngữ cảnh line layout. Bài này dùng một ví dụ nhỏ với JDK kiểm thử để học cách đọc API; đừng dùng run order của một đoạn cố định để hardcode giao diện tổng quát.

## 9. Vì sao Java Bidi chưa đủ để tự vẽ một đoạn văn?

`java.text.Bidi` cung cấp **bidi analysis**; nó không phải một thư viện render text hoàn chỉnh. Để vẽ chính xác cần thêm:

- **Đo chiều rộng glyph** với font thực tế.
- **Shaping** đặc thù script như Arabic contextual forms và ligature.
- **Grapheme clustering** để dấu tổ hợp/caret/delete không tách cụm sai.
- **Line breaking** trước khi reorder từng dòng.
- **Mirroring** và xử lý ngoặc/dấu trong ngữ cảnh RTL.
- **Logical-to-visual mapping** cho caret, selection, hit testing và accessibility.
- **Font fallback** và lựa chọn glyph khi một font không hỗ trợ script.

Vì vậy, các hệ thống Swing/AWT/browser/Android hoặc thư viện layout chuyên dụng thường nên chịu trách nhiệm vẽ. Tránh viết lại toàn bộ Unicode BiDi Algorithm nếu chỉ muốn hiển thị tên, bản dịch hay câu có phần RTL.

### 9.1. Các API tạo dòng

`Bidi.createLineBidi(lineStart, lineLimit)` nhận **offset UTF-16** trong paragraph và tạo đối tượng phân tích dòng, phù hợp khi **bộ layout đã xác định ranh giới dòng**. Đây không phải phương thức tự đo chiều rộng rồi tự xuống dòng.

Ở lớp layout, một paragraph có thể tách thành các dòng khác nhau tùy kích thước vùng hiển thị; vì thế thứ tự visual của một paragraph dài không thể thu được bằng một lần đảo toàn bộ chuỗi.

### 9.2. Accessibility và clipboard

Nhìn thấy chữ trên màn hình chỉ là một kênh. Screen reader, clipboard, chức năng tìm kiếm, keyboard navigation và serialization cũng cần nắm thứ tự **logic**. Trong UI, hãy giữ text theo nội dung gốc và để công cụ accessibility/layout diễn giải bidi. Nếu xuất “visual order text” bằng cách đảo ký tự, nhiều trình đọc màn hình và công cụ xử lý tiếp theo sẽ nhận sai dữ liệu.

## 10. Các lỗi thường gặp

| Lỗi | Hậu quả | Cách đúng |
| --- | --- | --- |
| Đảo `String` để hiển thị RTL | Sai khi trộn chữ số, Latin, dấu, shaping | Giữ logical order; giao render cho BiDi-aware UI |
| Tưởng `Locale` quyết định tất cả chiều văn bản | Nội dung trộn script hoặc chỉ số cần xử lý riêng | Chọn base direction và isolation theo context |
| Nhầm `getRunStart` là visual index | Selection/highlight lệch vị trí | Run offsets là UTF-16 logic |
| Nhầm `getRunCount` là số từ | Logic tokenization sai | Run là đoạn cùng resolved bidi level |
| Coi `reorderVisually` đã tạo câu hiển thị hoàn chỉnh | Thiếu shaping, glyph, line break | Renderer/layout engine xử lý tiếp |
| Dùng `text-align:right` để thay direction | Dấu và từ trộn vẫn sai vị trí | Dùng semantics chiều văn bản |
| Không isolate tên người/chữ người dùng chèn trong câu khác hướng | Dấu câu/phần lân cận có thể bị ảnh hưởng | `<bdi dir="auto">` hoặc cơ chế isolation tương ứng |
| Tự thêm RLO/LRO vào dữ liệu để “sửa layout” | Ký tự vô hình có thể lừa hiển thị, copy/paste sai | Dùng layout protocol, sanitize theo field |
| Tự loại mọi ký tự RTL trong user-generated text | Chặn ngôn ngữ thật | Chỉ hạn chế **format controls** ở field cần bảo vệ |
| Dựa vào screenshot để xác nhận thứ tự byte/logic | Glyph có thể reorder | Kiểm tra code points/logical representation |
| Dùng `length - i` để đổi caret index | Bỏ qua nhiều run, levels, graphemes | Hit testing với text layout chuyên dụng |
| Sort dữ liệu bằng visual order | Kết quả so sánh không nhất quán | Dùng `Collator`/quy tắc tìm kiếm trên logical text |

## 11. Kiểm thử và bài tập

### Kiểm thử thực tế nên có

1. **Văn bản thuần LTR:** câu tiếng Việt/Anh, nền LTR, không đổi nội dung.
2. **Văn bản thuần RTL:** đoạn Hebrew/Arabic, kiểm tra base direction và render đúng.
3. **Trộn RTL/LTR:** câu Hebrew chứa `Java` và `123`, câu tiếng Việt chứa tên Arabic.
4. **Weak/neutral:** dấu `:`, `-`, ngoặc đơn, dấu cách ở ranh giới các run.
5. **Ký tự điều khiển:** có/không có isolate, LRM/RLM và thử trường hợp Unicode control vô hình có thể gây hiểu nhầm.
6. **Dữ liệu nguồn:** so `String.codePoints()` trước và sau khi hiển thị; renderer không tự thay dữ liệu gốc.
7. **Selection/caret:** kiểm tra chọn văn bản qua ranh giới run, backspace/delete và dùng chuột.
8. **Xuống dòng:** cùng đoạn nhưng vùng hiển thị hẹp/rộng khác nhau, xem visual order mỗi dòng.
9. **Font/shaping:** Arabic contextual forms, dấu tổ hợp, ligature, fallback.
10. **HTML input:** tên người dùng RTL xen trong câu LTR và ngược lại; `<bdi>` cùng HTML escaping.
11. **Security:** filename/source/log chứa bidi override; kiểm tra khả năng hiện tên mã ký tự ẩn.
12. **Regression:** ghim runtime/layout engine nếu sản phẩm kiểm thử output theo tọa độ hoặc screenshot chính xác.

### Bài tập 1 — đổi base direction

Chạy demo nhưng thay flag `DIRECTION_DEFAULT_LEFT_TO_RIGHT` thành `DIRECTION_RIGHT_TO_LEFT`. Đọc `getBaseLevel()`, `getRunCount()`, `getRunLevel(i)` và mảng run order; giải thích tại sao **thứ tự logic code points vẫn không đổi**.

### Bài tập 2 — thay thứ tự các đoạn nguồn

Đưa Hebrew lên đầu `paragraph`, rồi dùng `DIRECTION_DEFAULT_LEFT_TO_RIGHT`. Vì strong char đầu tiên là Hebrew, base direction có thể là RTL. Hãy in `getBaseLevel()` và đối chiếu với phiên bản Latin đầu tiên.

### Bài tập 3 — chỉ số logic

Tìm `paragraph.indexOf("123")` (demo là `8`), rồi xem `Bidi.getLevelAt(8)`. Giải thích vì sao index **8** vẫn đúng dù run số có thể được bố trí khác vị trí visual.

### Bài tập 4 — HTML isolation

Tạo một thông báo RTL chứa tên tài khoản Latin do người dùng nhập. Render hai bản: một bản đặt tên trực tiếp trong `span`, một bản chứa trong `<bdi dir="auto">`. Kiểm tra dấu câu trước/sau tên. Phải escape/chèn text an toàn trong cả hai.

### Bài tập 5 — kiểm tra control vô hình

Viết hàm kiểm tra code point của một ID kỹ thuật và cảnh báo nếu có `U+202A`–`U+202E` hoặc `U+2066`–`U+2069`. Phân biệt **dữ liệu UI tự do** với trường định danh có policy chặt; không xóa bừa mọi ký tự RTL hợp lệ.

### Bài tập 6 — render không phải reverse

Thử `new StringBuilder(paragraph).reverse()`, rồi so code point của chuỗi mới với paragraph. Chỉ ra dữ liệu đã thực sự đổi, nhưng kết quả mới không phải một `Bidi.reorderVisually` và không thể thay thế rendering.

## 12. Tổng kết

**Thứ tự logic là thứ tự dữ liệu Unicode được lưu và xử lý; thứ tự hiển thị là cách renderer sắp các run/glyph để người dùng đọc được văn bản hai chiều.** Chúng có thể khác nhau khi trộn Hebrew/Arabic với Latin, chữ số và dấu câu. Hướng nền, loại ký tự, embedding levels, isolate controls và ranh giới dòng ảnh hưởng layout, nhưng không yêu cầu đảo chuỗi nguồn.

Java `java.text.Bidi` cho phép đọc hướng nền, levels, offsets và sắp xếp **các run object** theo visual order. Những chỉ số ấy vẫn theo **UTF-16 logic offsets**; `Bidi` không tự render glyph, shaping hay điều khiển caret đầy đủ. Trong ứng dụng đa ngôn ngữ, giữ nguyên text nguồn, dùng UI/layout có hỗ trợ BiDi, isolate mảnh chèn khi cần, và kiểm tra control vô hình ở các trường nhạy cảm để giảm nguy cơ hiểu nhầm hoặc lạm dụng.

**Tài liệu tham khảo:**

- Java SE 17, `java.text.Bidi`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Bidi.html
- Java SE 17, `java.lang.String`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html
- Unicode Standard Annex #9 — Unicode Bidirectional Algorithm: https://www.unicode.org/reports/tr9/
- Unicode Security Considerations (UTR #36): https://unicode.org/reports/tr36/
- W3C Internationalization — Working with text direction: https://www.w3.org/International/articles/inline-bidi-markup/
