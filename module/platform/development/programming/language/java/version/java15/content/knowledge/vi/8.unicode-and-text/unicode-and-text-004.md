# Bidi và văn bản có nhiều chiều viết trong Java 15+

## 1. Bidi là gì, và tại sao quan trọng?

**Bidi (bidirectional text)** là văn bản kết hợp các phần viết **từ trái sang phải (LTR — left-to-right)** và **từ phải sang trái (RTL — right-to-left)**. Tiếng Việt, tiếng Anh và chữ Latin thường được đọc theo chiều LTR; chữ Hebrew và Arabic có chiều viết RTL. Một câu có thể chứa cả tên người viết bằng Arabic/Hebrew, địa chỉ email, số điện thoại, ngày tháng, số tiền và dấu câu. Khi đó, **thứ tự ký tự lưu trữ** không nhất thiết trùng với **thứ tự vị trí ký tự được hiển thị**.

Ví dụ một chuỗi có thứ tự logic:

```text
Invoice [space] שלום [space] 123
```

Chữ `שלום` thuộc Hebrew. Dãy `123` là chữ số. Khi đưa chuỗi vào một trình hiển thị hỗ trợ Unicode Bidirectional Algorithm (UBA), các nhóm chữ có thể được bố trí theo hai hướng khác nhau; dấu câu và khoảng trắng còn phụ thuộc **hướng cơ sở của đoạn**. Không thể suy ra kết quả chỉ bằng cách đảo toàn bộ String.

**Mục tiêu của bài:**

1. Phân biệt **logical order** (thứ tự mã ký tự trong String) và **visual order** (thứ tự vẽ trên màn hình).
2. Hiểu hướng cơ sở, nhóm ký tự strong/weak/neutral, **embedding levels** và **directional runs** của Unicode Bidirectional Algorithm.
3. Sử dụng API `java.text.Bidi` trong Java 15+ để kiểm tra hướng và run, đồng thời hiểu giới hạn của API.
4. Hiểu **directional isolation** khi chèn tên, nhãn hay dữ liệu đa ngôn ngữ vào giao diện hoặc văn bản thuần.
5. Tránh lỗi đảo String, cắt surrogate pair, xử lý dấu câu sai, lưu nhầm thứ tự hiển thị và bỏ sót những ký tự điều khiển Bidi vô hình.

`java.text.Bidi` và các quy tắc Unicode Bidi là kiến thức vẫn được sử dụng trong Java hiện đại; không cần API preview, giải pháp lỗi thời hoặc runtime Java 15 hết hỗ trợ để học chúng.

## 2. Thứ tự logic và thứ tự hiển thị là hai khái niệm khác nhau

### Thứ tự logic (logical order)

Java `String` lưu dữ liệu dưới dạng chuỗi **UTF-16 code units** theo thứ tự logic. Các thao tác `equals()`, `indexOf()`, `startsWith()`, `substring()`, `codePoints()`, cũng như phần lớn giao thức lưu trữ/trao đổi văn bản, làm việc trên thứ tự này. Khi một renderer hiển thị chữ Hebrew từ phải sang trái, nó **không mặc nhiên đảo dữ liệu String gốc**.

Một đoạn Java:

```java
String text = "ABC \u05E9\u05DC\u05D5\u05DD";
boolean startsWithLatin = text.startsWith("ABC "); // true
```

Đây là **đoạn minh họa** cần đặt bên trong phương thức nếu muốn chạy riêng. Bốn escape `\u05E9\u05DC\u05D5\u05DD` biểu diễn các chữ Hebrew của từ `שלום`. Khi hiển thị bằng font và công cụ bố cục phù hợp, chữ Hebrew có hướng RTL nhưng `text.startsWith("ABC ")` vẫn đúng.

### Thứ tự hiển thị (visual order)

Unicode Bidirectional Algorithm quyết định vị trí hiển thị của các **run có hướng khác nhau** khi cùng xuất hiện trong một dòng. Việc hiển thị còn phụ thuộc kích thước container, base direction, xuống dòng, dấu ngoặc, dấu câu và khả năng của renderer.

**Không lưu chuỗi theo thứ tự nhìn thấy rồi mới so sánh.** Khi lưu database, JSON hoặc nội dung người dùng, giữ logical order; phần giao diện chịu trách nhiệm vẽ theo quy tắc Bidi. Tránh `new StringBuilder(text).reverse().toString()` để “sửa” chữ RTL: thao tác đảo UTF-16 có thể làm sai chữ số, dấu kết hợp và surrogate pairs, đồng thời không thực hiện Unicode Bidi Algorithm.

Bidi **không phải** phép dịch ngôn ngữ, không phải phát hiện ngôn ngữ, cũng không phải thuật toán nối dạng chữ Arabic. **Arabic shaping** và glyph selection là công việc riêng của font và text layout engine.

## 3. Unicode Bidirectional Algorithm (UAX #9)

Unicode Standard Annex #9 quy định cách xử lý văn bản hai chiều. Những khái niệm chính:

### 3.1. Bidi class của ký tự

| Loại | Ví dụ | Vai trò |
| --- | --- | --- |
| **L** — strong LTR | Phần lớn chữ Latin, như `A`, `B` | Tín hiệu hướng trái sang phải |
| **R** — strong RTL | Nhiều chữ Hebrew | Tín hiệu hướng phải sang trái |
| **AL** — Arabic Letter | Nhiều chữ Arabic | Tín hiệu RTL của nhóm Arabic |
| **EN** — European Number | `0` đến `9` | Nhóm **yếu**; cách bố trí phụ thuộc ngữ cảnh |
| **AN** — Arabic Number | Một số hệ chữ số Arabic-Indic | Nhóm **yếu** với quy tắc riêng |
| **WS**, **ON** và các neutral classes | Khoảng trắng, dấu câu, nhiều ký hiệu | Hướng được giải quyết theo môi trường xung quanh |
| **Formatting / isolate controls** | LRM, RLM, LRI, RLI, FSI, PDI, RLO... | Điều chỉnh cách các vùng ảnh hưởng hướng của nhau |

Chữ số trong câu RTL thường **không** bị đảo thứ tự từng chữ số. Dấu ngoặc, dấu hai chấm hoặc dấu chấm có thể xuất hiện ở vị trí khó đoán nếu nhìn văn bản theo từng ký tự riêng lẻ, vì UBA xét cả ngữ cảnh.

`Character.getDirectionality(codePoint)` cho biết **loại hướng của một code point**. Nó khác `Bidi.getLevelAt(offset)`, vốn trả về **mức đã giải quyết trong ngữ cảnh đoạn**. Không suy ra visual order chỉ bằng phân loại một ký tự.

### 3.2. Hướng cơ sở (base direction)

UBA phân tích **theo paragraph**. Mỗi paragraph có hướng cơ sở:

- **LTR**: base level `0`.
- **RTL**: base level `1`.
- **Auto/default**: tìm ký tự **strong** đầu tiên theo quy tắc UBA, và dùng hướng fallback nếu không có strong character.

Base direction có thể được chọn tường minh bởi giao diện, chẳng hạn `dir="ltr"` hoặc `dir="rtl"` trong HTML, hoặc do chính sách đọc plain text. Nó không buộc mọi ký tự trong paragraph cùng một chiều: vùng Hebrew/Arabic xen trong đoạn Latin thường có mức RTL, và ngược lại.

### 3.3. Embedding level và directional run

UBA xử lý ký tự định hướng tường minh, phân loại weak/neutral, sau đó giải quyết **embedding level** cho các vị trí và sắp xếp các run khi vẽ từng dòng.

- Mức **chẵn** tương ứng LTR trong quy tắc sắp xếp.
- Mức **lẻ** tương ứng RTL.
- Một **run** là đoạn liền nhau trong thứ tự logic có cùng mức đã giải quyết.
- Mức 0 và 1 là phổ biến, nhưng các cấu trúc lồng và chữ số trong vùng RTL có thể dẫn đến mức lớn hơn.

Một paragraph có thể chứa run Latin → run Hebrew → run Latin mà thứ tự lưu trữ không đổi. Việc chuyển từ **logical runs** sang thứ tự hiển thị là hoạt động của renderer. Khi xuống dòng, phân tích Bidi còn phải áp dụng quy tắc theo dòng; không được tùy ý lấy kết quả thứ tự paragraph rồi dùng cho mọi vị trí con trỏ.

### 3.4. Bidi không thay thế shaping và text rendering

`java.text.Bidi` trả về thông tin để **phân tích hướng và run**. Nó không tự tạo glyph, không tự định vị ký tự trên màn hình và không tự nối các dạng chữ Arabic. Một ứng dụng tự xây dựng renderer còn cần font, glyph shaping, line breaking, caret mapping, selection và hit testing. Nếu đã dùng browser, text layout của hệ điều hành, Swing hoặc thư viện UI có hỗ trợ Bidi, hãy để renderer xử lý; tránh đảo String trước khi truyền vào.

## 4. API `java.text.Bidi` còn được sử dụng trong Java hiện đại

| Phương thức / hằng | Công dụng |
| --- | --- |
| `new Bidi(String paragraph, int flags)` | Phân tích một paragraph với lựa chọn base direction |
| `Bidi.DIRECTION_LEFT_TO_RIGHT` | Ép base direction LTR |
| `Bidi.DIRECTION_RIGHT_TO_LEFT` | Ép base direction RTL |
| `Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT` | Suy hướng từ ký tự strong đầu tiên; fallback LTR |
| `Bidi.DIRECTION_DEFAULT_RIGHT_TO_LEFT` | Suy hướng từ ký tự strong đầu tiên; fallback RTL |
| `baseIsLeftToRight()` / `getBaseLevel()` | Đọc hướng và mức cơ sở |
| `isLeftToRight()`, `isRightToLeft()`, `isMixed()` | Xác định đặc tính đơn hướng hoặc hỗn hợp của kết quả phân tích |
| `getRunCount()` | Số run theo mức nhúng |
| `getRunStart(i)` / `getRunLimit(i)` | Offset bắt đầu và **giới hạn loại trừ** của logical run `i` |
| `getRunLevel(i)` | Level của run `i`, chẵn/LTR hay lẻ/RTL |
| `getLevelAt(offset)` | Level tại offset trong đoạn |
| `createLineBidi(lineStart, lineLimit)` | Phân tích mức cho một dòng thuộc paragraph đã phân tích |
| `Bidi.requiresBidi(char[], start, limit)` | Kiểm tra nhanh nhu cầu phân tích Bidi |
| `Bidi.reorderVisually(...)` | Sắp xếp mảng **đối tượng/run** theo mức; không phải phép đảo `String` hay tạo glyph |

Các chỉ số của `String`/`Bidi` trong Java tính theo **UTF-16 code units**, không phải số Unicode code points hay số grapheme người dùng thấy. Một code point ngoài BMP có thể dùng hai code units; một cụm ký tự hiển thị có thể gồm nhiều code points.

**Dùng flags theo dữ liệu:**

1. Nếu paragraph **được chỉ định** hướng LTR/RTL, truyền hằng hướng tương ứng.
2. Nếu chỉ có plain text và không có metadata hướng, dùng một `DIRECTION_DEFAULT_*` phù hợp fallback của ứng dụng để thuật toán suy theo ký tự strong đầu tiên.
3. Với văn bản nhập từ nhiều ngôn ngữ, chọn **hướng theo từng paragraph hoặc field**, không mặc định mọi field cùng hướng của toàn bộ ứng dụng.
4. Đừng dùng `isMixed()` để phát hiện “có nhiều ngôn ngữ”; đây là đặc tính **Bidi** đã phân tích, không phải bộ phân loại ngôn ngữ.

## 5. Ví dụ Java 15+ hoàn chỉnh, có thể chạy

Tạo file **`BidiTextDemo.java`**:

```java
import java.text.Bidi;

public class BidiTextDemo {
    public static void main(String[] args) {
        String latin = "Hello";
        // U+05E9 U+05DC U+05D5 U+05DD: Hebrew "shalom".
        String hebrew = "\u05E9\u05DC\u05D5\u05DD";
        String mixed = latin + " " + hebrew + " 123";

        Bidi latinBidi = new Bidi(
                latin, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);
        Bidi hebrewBidi = new Bidi(
                hebrew, Bidi.DIRECTION_DEFAULT_LEFT_TO_RIGHT);
        Bidi mixedBidi = new Bidi(
                mixed, Bidi.DIRECTION_LEFT_TO_RIGHT);

        System.out.println("latin base LTR="
                + latinBidi.baseIsLeftToRight());
        System.out.println("hebrew base RTL="
                + !hebrewBidi.baseIsLeftToRight());
        System.out.println("mixed base LTR="
                + mixedBidi.baseIsLeftToRight());
        System.out.println("mixed isMixed="
                + mixedBidi.isMixed());

        char[] characters = mixed.toCharArray();
        System.out.println("mixed requiresBidi="
                + Bidi.requiresBidi(characters, 0, characters.length));
        System.out.println("logical startsWith Hello="
                + mixed.startsWith("Hello "));
        System.out.println("hebrew UTF-16 length="
                + hebrew.length());
        System.out.println("hebrew first level odd="
                + ((hebrewBidi.getLevelAt(0) & 1) == 1));
        System.out.println("hebrew first direction R="
                + (Character.getDirectionality(hebrew.codePointAt(0))
                    == Character.DIRECTIONALITY_RIGHT_TO_LEFT));
    }
}
```

Dùng JDK còn được hỗ trợ và có `javac` hỗ trợ `--release 15` (ví dụ JDK 21), rồi chạy tại thư mục chứa file:

```bash
javac --release 15 -encoding UTF-8 -d out BidiTextDemo.java
java -cp out BidiTextDemo
```

**Stdout chính xác (không phụ thuộc vào cách terminal vẽ chữ RTL):**

```text
latin base LTR=true
hebrew base RTL=true
mixed base LTR=true
mixed isMixed=true
mixed requiresBidi=true
logical startsWith Hello=true
hebrew UTF-16 length=4
hebrew first level odd=true
hebrew first direction R=true
```

Giải thích:

- `"Hello"` có ký tự strong LTR đầu tiên nên base LTR.
- Chuỗi Hebrew có ký tự strong RTL đầu tiên, vì thế cờ `DIRECTION_DEFAULT_LEFT_TO_RIGHT` chỉ là **fallback**; base thực tế của nó vẫn RTL.
- Chuỗi hỗn hợp có base LTR tường minh và chứa run Hebrew, nên `isMixed()` là true và `requiresBidi(...)` là true.
- `startsWith("Hello ")` tiếp tục đúng vì String giữ **logical order**, dù vị trí hiển thị có thể khác.
- Bốn ký tự Hebrew trong ví dụ thuộc BMP, vì vậy `length() == 4`. Không tổng quát hóa quy tắc này cho mọi chữ Unicode.
- `getLevelAt(0)` của chuỗi Hebrew cho mức lẻ; `Character.getDirectionality` của chữ đầu tiên cho lớp ký tự RTL. Một bên là **mức đã giải quyết**, một bên là **thuộc tính ký tự**.

### Khảo sát các run trong chuỗi mixed

Thêm đoạn sau vào cuối `main` nếu muốn xem các run (đây là **đoạn bổ sung**, không phải class độc lập):

```java
for (int run = 0; run < mixedBidi.getRunCount(); run++) {
    int start = mixedBidi.getRunStart(run);
    int limit = mixedBidi.getRunLimit(run);
    int level = mixedBidi.getRunLevel(run);
    String direction = (level % 2 == 0) ? "LTR" : "RTL";
    String logicalSlice = mixed.substring(start, limit);

    System.out.printf(
            "run=%d, range=[%d,%d), level=%d, direction=%s, units=%d%n",
            run, start, limit, level, direction,
            logicalSlice.length());
}
```

`getRunLimit` trả về **vị trí ngay sau** run. `substring(start, limit)` cho bạn phần **logic** trong run, không phải một chuỗi đã được render. Không hard-code số run của dữ liệu tổng quát: nó phụ thuộc văn bản, cờ và phiên bản dữ liệu Unicode của JDK.

## 6. Ký tự điều khiển hướng và isolation

Một số code points điều chỉnh hướng mà **không có glyph nhìn thấy**:

| Ký hiệu | Unicode | Ý nghĩa |
| --- | --- | --- |
| LRM | U+200E | Left-to-Right Mark, tín hiệu hướng LTR cục bộ |
| RLM | U+200F | Right-to-Left Mark, tín hiệu hướng RTL cục bộ |
| ALM | U+061C | Arabic Letter Mark |
| LRI | U+2066 | Left-to-Right Isolate: mở vùng cách ly LTR |
| RLI | U+2067 | Right-to-Left Isolate: mở vùng cách ly RTL |
| FSI | U+2068 | First Strong Isolate: suy hướng của vùng từ ký tự strong đầu |
| PDI | U+2069 | Pop Directional Isolate: đóng vùng isolate |
| RLO | U+202E | Right-to-Left Override: ép hướng RTL trong một phạm vi |
| LRO | U+202D | Left-to-Right Override: ép hướng LTR trong một phạm vi |
| PDF | U+202C | Pop Directional Formatting: đóng embedding/override |

**Isolate** giúp một vùng text được xử lý hướng **độc lập với xung quanh**, đặc biệt khi chèn dữ liệu người dùng từ ngôn ngữ khác vào câu. RLO/LRO là các **override** mạnh, có thể làm nội dung nhìn khác thường và không nên dùng tùy tiện.

### Ưu tiên markup ở giao diện HTML

Ví dụ một trang LTR hiển thị tên Hebrew:

```html
<p dir="ltr">
  Owner: <bdi dir="auto">שלום</bdi> (active)
</p>
```

`dir="ltr"` chỉ định base direction của đoạn ngoài. `<bdi dir="auto">` cách ly tên chèn vào và suy hướng phù hợp. Nếu đã biết chính xác hướng của một phần tử, có thể đặt `dir="rtl"` hoặc `dir="ltr"` tại container tương ứng. Với các trường nhập liệu, HTML `dir="auto"` cũng hữu ích khi hỗ trợ nhiều ngôn ngữ.

### Khi truyền plain text

Nếu cần truyền văn bản **thuần** sang renderer hỗ trợ UBA hiện đại mà không có markup, có thể biểu diễn một vùng cách ly bằng **FSI + nội dung + PDI**:

```java
static String isolateForPlainText(String value) {
    if (value == null) {
        throw new IllegalArgumentException("value must not be null");
    }
    char firstStrongIsolate = (char) 0x2068;
    char popDirectionalIsolate = (char) 0x2069;
    return firstStrongIsolate + value + popDirectionalIsolate;
}
```

Đây là **phương thức minh họa** để đặt trong class. Hai control vẫn là ký tự trong String, vì vậy ảnh hưởng `length()`, `equals()`, copy/paste, lưu trữ và tìm kiếm. Chỉ chèn chúng khi **định dạng đích và renderer** thực sự cần, đồng thời kiểm tra kết quả trên môi trường hiển thị. Khi có markup như HTML, dùng cơ chế `dir`/`<bdi>` thay vì đưa control vô hình vào dữ liệu dài hạn.

Bidi isolation **không phải** cơ chế escape chống HTML injection/XSS, SQL injection hoặc shell injection; những vấn đề đó cần encoder/parameterized query theo đúng giao thức.

## 7. Chữ số, dấu câu và ký tự nhiều chiều

Khi chèn số điện thoại, địa chỉ, URL, mã sản phẩm hoặc ngày giờ vào câu RTL:

- Chữ số thuộc các lớp hướng yếu và thường vẫn được đọc theo thứ tự LTR trong cụm số; không đảo từng chữ số bằng tay.
- Dấu gạch chéo, dấu hai chấm, dấu ngoặc và ký hiệu tiền tệ có thể nhận vị trí hiển thị dựa trên **các run và ký tự lân cận**.
- Một nhãn Latin như `Order ID: 123` ở trong container RTL có thể cần **vùng LTR riêng**, nhất là nếu các dấu câu ở ranh giới trông không như mong đợi.
- Hướng của cả trang không luôn là hướng của từng field: tên Hebrew trong một giao diện LTR và địa chỉ email LTR trong giao diện RTL đều cần xử lý đúng ngữ cảnh.

Thử nghiệm ở renderer thật quan trọng hơn việc đọc chuỗi từ terminal: console, browser, ứng dụng desktop và công cụ PDF có thể dùng font, layout hoặc cách hiển thị khác nhau. Hãy kiểm tra văn bản **trên đúng giao diện đích**.

## 8. Vị trí con trỏ, vùng chọn và giới hạn UTF-16

### UTF-16 không phải số ký tự người dùng nhìn thấy

`String.length()` đếm **UTF-16 code units**. `String.codePoints()` duyệt **Unicode code points**. Một code point ngoài BMP thường chiếm **hai** UTF-16 code units (*surrogate pair*). Một **grapheme cluster** có thể chứa nhiều code points (chữ + dấu kết hợp, hoặc một chuỗi emoji phức hợp).

Offset từ `Bidi.getRunStart/getRunLimit/getLevelAt` dùng chỉ số tương ứng với văn bản được phân tích, **không tự biểu diễn một grapheme**. Nếu dùng chúng để cắt dữ liệu hoặc đặt caret, cần xét ranh giới code point và grapheme, cùng với kết quả text layout.

### Di chuyển con trỏ khi có run RTL và LTR

Trong văn bản hỗn hợp, một phím mũi tên sang phải hoặc sang trái có thể được diễn giải theo **vị trí hiển thị**, khác với tăng/giảm chỉ số String. Ranh giới giữa hai run có thể tạo ra nhiều cách đặt caret tương ứng một ranh giới logic tùy renderer.

Không tự viết `cursorIndex++` rồi giả định con trỏ sẽ sang phải đúng một glyph. Hãy sử dụng text layout/selection API của framework. Trong Java2D có `java.awt.font.TextLayout` cho bài toán bố cục văn bản; trong browser, để engine trình duyệt xử lý Bidi và vùng chọn. **`Bidi` chỉ giải quyết một phần của pipeline hiển thị**, không phải đầy đủ shaping và hit testing.

## 9. Bảo mật và dữ liệu có Bidi controls vô hình

Do một số Bidi control không nhìn thấy, văn bản **trông như có thứ tự A** trên màn hình có thể được **lưu theo thứ tự B** trong String. Những tình huống cần để ý:

- **Log và giao diện quản trị:** các control có thể dịch chuyển vị trí dấu câu, phần mở rộng file hoặc đoạn chữ khi hiển thị.
- **Đường dẫn và tên file:** người xem có thể nhầm vị trí dấu `.`, `/` hoặc hậu tố, trong khi phần mềm thực thi dựa trên thứ tự logic.
- **Source code và code review:** Bidi controls trong comment/literal có thể tạo khác biệt giữa thứ tự hiển thị và thứ tự parser hiểu (nhóm vấn đề thường gọi là *Trojan Source*).
- **So sánh chuỗi:** `equals()` so sánh dữ liệu code units, không so sánh hình ảnh glyph. Một chuỗi có control vô hình không giống chuỗi thiếu control đó.

### Chẩn đoán bằng mã Unicode

Khi nghi ngờ dữ liệu chứa control, in các **code points** thay vì chỉ in chữ:

```java
String input = "A" + (char) 0x202E + "B";
input.codePoints().forEach(
        cp -> System.out.printf("U+%04X%n", cp));
```

Đặt đoạn này bên trong phương thức `main` sẽ in **stdout chính xác**:

```text
U+0041
U+202E
U+0042
```

`U+202E` là RIGHT-TO-LEFT OVERRIDE. Thông tin mã code point cho phép phân tích mà không phụ thuộc terminal. Có thể dùng `Character.getDirectionality(int)` cho từng code point, nhưng muốn hiểu hiển thị cuối cùng vẫn cần UBA với **toàn bộ paragraph**.

Khi tạo log hoặc màn hình kiểm toán, cân nhắc thay các Bidi control nhạy cảm bằng biểu diễn `U+XXXX` hay nhãn dễ đọc để tránh đánh lừa người xem. Áp dụng kiểm tra/giới hạn tùy **loại dữ liệu** (chẳng hạn tên file nhạy cảm, source code, mã định danh). **Không cấm toàn bộ chữ Hebrew/Arabic và không xóa mọi ký tự Unicode `Cf` một cách máy móc**: một số ký tự vô hình có ý nghĩa ngôn ngữ hoặc bố cục. Nếu cần bảo toàn văn bản gốc, nên giữ bản logic và chỉ hiển thị an toàn ở lớp presentation.

## 10. Những lỗi phổ biến

| Sai lầm | Vì sao sai | Cách làm phù hợp |
| --- | --- | --- |
| Dùng `StringBuilder.reverse()` với Hebrew/Arabic | Đảo UTF-16 code units; không giải quyết số, dấu câu và shaping | Giữ logical order và để renderer hỗ trợ UBA |
| Nghĩ base RTL nghĩa là đảo hết câu | UBA có level chẵn/lẻ, weak/neutral và run | Chọn base direction đúng và để thuật toán xử lý |
| Coi `isMixed()` là phép phát hiện nhiều ngôn ngữ | Hàm chỉ phân loại cấu trúc Bidi đã giải quyết | Dùng xử lý Bidi cho hướng; nhận diện ngôn ngữ là vấn đề riêng |
| Dùng `Bidi.reorderVisually` để tự đảo String | Hàm sắp xếp đối tượng/run, không làm shaping và layout | Dùng text rendering engine cho hình ảnh cuối |
| Xem `getRunLimit` là chỉ số cuối bao gồm | Hàm trả về **exclusive end** | Dùng khoảng `[start, limit)` |
| Coi String index là chỉ số grapheme | Một grapheme có thể gồm nhiều codepoints/code units | Phân biệt UTF-16, code points, graphemes và layout |
| Dùng RLO/LRO để “sửa” tên người | Ép hướng của đoạn và có thể tạo rủi ro hiển thị | Ưu tiên isolate/`dir`/`<bdi>` với phạm vi xác định |
| Chỉ kiểm tra text trên console | Terminal có thể khác font và thuật toán của UI đích | Thử trong browser/desktop/PDF renderer đang dùng |
| Xóa vô điều kiện mọi ký tự điều khiển | Có thể phá văn bản hợp lệ và dữ liệu cần giữ nguyên | Áp dụng chính sách theo giao thức và vai trò của dữ liệu |

## 11. Checklist kiểm thử đa ngôn ngữ

Một ứng dụng hỗ trợ Unicode text nên kiểm thử:

1. Paragraph chỉ Latin, chỉ Hebrew, chỉ Arabic và **trộn Latin/RTL**.
2. Các trường hợp có **số, dấu ngoặc, dấu hai chấm, dấu chấm, gạch chéo, URL, email** cạnh chữ RTL.
3. Base direction đặt LTR/RTL tường minh và chế độ tự suy hướng từ ký tự strong đầu tiên.
4. Vùng chèn dữ liệu người dùng có **`<bdi>`/`dir`** hoặc isolate plain-text đúng hoàn cảnh.
5. Ký tự Bidi control vô hình để kiểm tra code review và biểu diễn log an toàn.
6. Ký tự ngoài BMP, dấu kết hợp, emoji, xuống dòng dài và trường hợp đặt caret/selection tại ranh giới LTR–RTL.
7. Thứ tự ký tự **logic** trước/sau lưu vào database, xuất JSON và đọc lại phải được bảo toàn.
8. Đối chiếu rendering thật trên môi trường deploy: browser, hệ điều hành, font, bản dữ liệu Unicode của JDK và các thư viện bố cục văn bản có thể ảnh hưởng cách phân đoạn/hiển thị.

**Quy tắc thực hành:** giữ nguyên logical order của dữ liệu; xác định base direction tại ranh giới hiển thị; isolate những đoạn có hướng không biết trước; dùng `java.text.Bidi` để phân tích mức/run khi cần; giao nhiệm vụ vẽ glyph/caret cho text layout engine; kiểm tra các control vô hình ở những điểm có rủi ro.

## Tài liệu chính thức còn phù hợp

- **Unicode Standard Annex #9 — Unicode Bidirectional Algorithm**, quy tắc paragraph, class, embedding levels, runs và isolates: https://www.unicode.org/reports/tr9/
- **Java SE 15 `java.text.Bidi`**, API và ngữ nghĩa methods: https://docs.oracle.com/en/java/javase/15/docs/api/java.base/java/text/Bidi.html
- **Java SE 25 `java.text.Bidi`**, tài liệu API của Java hiện đại: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/text/Bidi.html
- **Java SE `Character.getDirectionality(int)`**, thông tin hướng code point: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html
- **W3C Internationalization — Inline Markup and Bidirectional Text**, sử dụng hướng và isolation trong HTML: https://www.w3.org/International/articles/inline-bidi-markup/
- **Unicode UAX #29 — Text Segmentation**, khái niệm grapheme clusters: https://www.unicode.org/reports/tr29/

Đây là kiến thức về Unicode và API Java SE **vẫn áp dụng trong Java hiện đại**. Với ứng dụng vận hành thực tế, sử dụng JDK/JVM còn được hỗ trợ và xác nhận hành vi trên chính renderer đích; không tự cài một Java 15 runtime đã hết hỗ trợ chỉ để thực hành Bidi.
