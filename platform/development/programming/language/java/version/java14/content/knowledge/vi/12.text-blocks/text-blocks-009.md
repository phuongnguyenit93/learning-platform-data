# Kiểm tra nội dung thực của text block bằng độ dài và từng ký tự

## 1. Vì sao cần kiểm tra từng ký tự?

**Text block** là cách viết chuỗi nhiều dòng trong Java bằng ba dấu nháy kép `"""`. Nó giúp đặt JSON, SQL, HTML hoặc văn bản nhiều dòng vào mã nguồn mà không phải nối nhiều chuỗi bằng toán tử `+`. Nhưng **cách văn bản trông như thế nào trong trình soạn thảo không nhất thiết trùng với nội dung của `String` sau khi biên dịch**.

Ví dụ:

~~~java
String message = """
        A
          B
        """;
~~~

Chuỗi này **không** chứa tám dấu cách trước chữ `A`, không chứa mười dấu cách trước chữ `B` và không bắt đầu bằng ký tự xuống dòng. Sau khi compiler xử lý phần thụt lề phụ của text block, giá trị thực là:

~~~text
A
  B
~~~

Để biết giá trị **chính xác** thay vì đoán từ cách hiển thị, ta cần kiểm tra:

- `String.length()`: có bao nhiêu **UTF-16 code units** trong chuỗi?
- `String.charAt(i)`: ở từng vị trí `i` có code unit gì, ví dụ `' '`, `'\t'`, `'\n'`, `'\r'`?
- `String.equals(expected)`: giá trị có khớp **toàn bộ** với chuỗi mong đợi, bao gồm dấu cách và ký tự điều khiển?
- `String.codePointCount(...)` hoặc `String.codePoints()`: khi có Unicode ngoài Basic Multilingual Plane, bao nhiêu **Unicode code points** đang hiện diện?

Các phép kiểm tra này giúp tìm lỗi rất khó nhìn bằng mắt: thừa/mất newline cuối cùng, khác số dấu cách đầu dòng, tab bị nhầm thành khoảng trắng, ký tự điều khiển hoặc một emoji được tính thành hai đơn vị UTF-16.

**Phiên bản Java:** text blocks trở thành tính năng chính thức từ **Java 15** (OpenJDK JEP 378); Java 13/14 từng có bản preview nhưng không nên dùng cú pháp/hành vi preview cũ làm chuẩn hiện tại. Các chương trình ở đây dùng **Java 17+**, biên dịch với `javac --release 17` và không cần `--enable-preview`. Tên module Java 14 không thay đổi yêu cầu sử dụng kiến thức đã ổn định ngày nay.

## 2. Ba bước Java xử lý nội dung text block

Trước khi bạn gọi `length()`, compiler đã tạo giá trị `String` từ phần văn bản của text block. Theo Java Language Specification, xử lý nội dung diễn ra theo thứ tự về cơ bản như sau:

1. **Chuẩn hóa line terminators:** các kiểu xuống dòng CRLF (`\r\n`) và CR (`\r`) trong **nội dung nguồn text block** được chuẩn hóa thành một ký tự LF (`\n`).
2. **Loại bỏ incidental white space:** compiler xác định phần thụt lề chung có thể bỏ để mã nguồn dễ định dạng; đồng thời loại bỏ khoảng trắng cuối dòng tình cờ trong text block theo quy tắc xử lý indentation.
3. **Diễn giải escape sequences:** những cách viết như `\n`, `\t`, `\s` và dấu gạch chéo ngược ở cuối dòng được diễn giải thành nội dung thực.

Đây là lý do **không thể** lấy số ký tự trên mỗi dòng trong mã nguồn rồi cộng lại để suy ra `String.length()`. Sau khi biên dịch, `length()` đo **kết quả cuối cùng**, không đo phần ký tự dùng làm dấu phân cách hay phần thụt lề incidental đã bị xóa.

### Dấu mở `"""` không tạo một newline đầu chuỗi

Một text block chuẩn có dấu mở `"""` và sau nó phải có line terminator. Phần nội dung bắt đầu **sau** line terminator bắt buộc đó. Vì vậy:

~~~java
String s = """
        Hello
        """;
~~~

có giá trị `"Hello\n"`, **không** phải `"\nHello\n"`. Nếu bạn thực sự muốn newline ở đầu, phải có **dòng nội dung trống có chủ ý** sau dòng dấu mở.

### Dấu đóng quyết định newline cuối trong trường hợp thường gặp

Nếu dấu đóng `"""` nằm trên dòng riêng, sau dòng cuối có nội dung, text block thông thường giữ LF cuối:

~~~java
String withEnd = """
        Hello
        """;
// Giá trị chính xác: "Hello\n"
~~~

Nếu dấu đóng được đặt ngay sau nội dung trên dòng cuối, text block không tự thêm LF cuối:

~~~java
String withoutEnd = """
        Hello""";
// Giá trị chính xác: "Hello"
~~~

Cả hai là **đoạn mã minh họa đặt trong phương thức**, không phải một chương trình `main` độc lập. Nên dùng `length()` và `charAt(length - 1)` để xác nhận thay vì dựa vào `System.out.println(s)`: chính `println` cũng ghi một dấu xuống dòng sau chuỗi nên dễ che mất khác biệt.

## 3. `String.length()` đếm UTF-16 code units, không đếm dòng hoặc ký tự nhìn thấy

Đối với các ký tự ASCII đơn giản, mỗi chữ cái, dấu cách, tab hoặc LF thường chiếm **một** UTF-16 code unit. Ví dụ giá trị `"A\n  B\n"` gồm:

| Vị trí `i` | Giá trị `charAt(i)` | Mã UTF-16 | Giải thích |
| ---: | --- | --- | --- |
| 0 | `'A'` | `U+0041` | Chữ A |
| 1 | `'\n'` | `U+000A` | Xuống dòng LF |
| 2 | `' '` | `U+0020` | Khoảng trắng thứ nhất |
| 3 | `' '` | `U+0020` | Khoảng trắng thứ hai |
| 4 | `'B'` | `U+0042` | Chữ B |
| 5 | `'\n'` | `U+000A` | Xuống dòng LF cuối |

Vậy `length() == 6`. Dù nhìn thấy chỉ hai chữ `A`, `B` trên hai dòng, chuỗi vẫn có sáu code units. Với chuỗi `"A\n  B"` không có LF cuối thì `length() == 5`.

**Cú pháp Java quan trọng:**

~~~java
int size = s.length();
char first = s.charAt(0);
char last = s.charAt(s.length() - 1);
~~~

`length()` là **phương thức** của `String`, có dấu ngoặc `()`. `charAt(i)` nhận chỉ số từ `0` đến `length() - 1`, trả về một `char`, tức **một UTF-16 code unit**. Nếu chuỗi rỗng hoặc chỉ số vượt phạm vi, `charAt` ném `StringIndexOutOfBoundsException`; muốn lấy ký tự cuối phải kiểm tra `!s.isEmpty()` trước.

Không được hiểu `length()` là “số Unicode characters theo cách người dùng nhìn thấy”. Ký tự ngoài BMP (chẳng hạn emoji) được biểu diễn bởi **hai UTF-16 code units**, và các chuỗi có dấu kết hợp còn có thể có nhiều code points trong một ký tự hiển thị.

## 4. Đọc từng ký tự và làm hiện khoảng trắng vô hình

Một phép debug đáng tin cậy là đi qua từng vị trí, in:

- Chỉ số `i`.
- Mã code unit ở dạng hex, ví dụ `U+000A` cho LF và `U+0009` cho tab.
- Nhãn dễ nhìn, ví dụ `\n`, `\t`, `<space>`.

**Không in trực tiếp mỗi `char` rồi kết luận:** `System.out.println(' ')` chỉ tạo một dòng tưởng như trống; `System.out.println('\n')` xuống dòng; còn tab có thể bị terminal hiển thị thành nhiều khoảng trắng tùy vị trí cột. Vì thế chuỗi nhãn và mã hex quan trọng hơn hình dạng chữ trên console.

Ví dụ một hàm hiển thị code unit:

~~~java
static String visible(char c) {
    return switch (c) {
        case '\n' -> "\\n";
        case '\r' -> "\\r";
        case '\t' -> "\\t";
        case ' ' -> "<space>";
        default -> Character.toString(c);
    };
}
~~~

Hàm trên là **mã minh họa nằm trong một class**, không có `main` riêng. Ký tự `'\n'` là LF thật, còn chuỗi `"\\n"` chứa hai ký tự có thể nhìn thấy: dấu gạch chéo ngược và `n`. Phân biệt hai giá trị đó giúp bản dump không tự xuống dòng khi gặp LF trong dữ liệu.

Khi duyệt:

~~~java
for (int i = 0; i < text.length(); i++) {
    char ch = text.charAt(i);
    System.out.printf("%d: U+%04X %s%n",
            i, (int) ch, visible(ch));
}
~~~

`%04X` in mã code unit dưới dạng ít nhất bốn chữ số hex; `%n` là dấu xuống dòng của lệnh **in kết quả** theo hệ điều hành, không phải một phần của `text` đang kiểm tra.

## 5. Chương trình Java 17+ số 1: kiểm tra LF, indentation, tab, dấu cách cuối dòng

Tạo file **`TextBlockCharacterInspector.java`**:

~~~java
public class TextBlockCharacterInspector {
    static String visible(char c) {
        return switch (c) {
            case '\n' -> "\\n";
            case '\r' -> "\\r";
            case '\t' -> "\\t";
            case ' ' -> "<space>";
            default -> Character.toString(c);
        };
    }

    static void inspect(String label, String value) {
        System.out.println(label + ": length=" + value.length()
                + ", codePoints=" + value.codePointCount(0, value.length()));
        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            System.out.printf("  %d: U+%04X %s%n", i, (int) ch, visible(ch));
        }
    }

    public static void main(String[] args) {
        String basic = """
                A
                  B
                """;

        String noFinalNewline = """
                A
                  B""";

        String escaped = """
                X\s
                Y\tZ
                Q\
                R
                """;

        inspect("basic", basic);
        inspect("noFinalNewline", noFinalNewline);
        inspect("escaped", escaped);

        System.out.println("basicExpected=" + basic.equals("A\n  B\n"));
        System.out.println("noFinalExpected="
                + noFinalNewline.equals("A\n  B"));
        System.out.println("escapedExpected="
                + escaped.equals("X \nY\tZ\nQR\n"));
    }
}
~~~

Lệnh biên dịch và chạy (JDK 17 trở lên):

~~~bash
javac --release 17 -encoding UTF-8 TextBlockCharacterInspector.java
java TextBlockCharacterInspector
~~~

**Stdout đã kiểm tra chính xác:**

~~~text
basic: length=6, codePoints=6
  0: U+0041 A
  1: U+000A \n
  2: U+0020 <space>
  3: U+0020 <space>
  4: U+0042 B
  5: U+000A \n
noFinalNewline: length=5, codePoints=5
  0: U+0041 A
  1: U+000A \n
  2: U+0020 <space>
  3: U+0020 <space>
  4: U+0042 B
escaped: length=10, codePoints=10
  0: U+0058 X
  1: U+0020 <space>
  2: U+000A \n
  3: U+0059 Y
  4: U+0009 \t
  5: U+005A Z
  6: U+000A \n
  7: U+0051 Q
  8: U+0052 R
  9: U+000A \n
basicExpected=true
noFinalExpected=true
escapedExpected=true
~~~

### Giải thích kết quả theo từng chuỗi

**`basic`** chứa đúng `"A\n  B\n"`: có hai dấu cách trước B và LF ở cuối, tổng cộng sáu code units. Java loại bỏ phần indentation chung trong mã nguồn, nhưng **giữ lại hai dấu cách có ý nghĩa tương đối** của dòng B.

**`noFinalNewline`** cũng có A và B theo thứ tự đó, nhưng dấu đóng nằm ngay sau B, nên không có LF cuối và `length() == 5`. Dump không có vị trí `5` với mã `U+000A`.

**`escaped`** chứa chính xác `"X \nY\tZ\nQR\n"`:

- `X\s`: escape `\s` tạo **một dấu cách** sau X, ngay trước LF. Vì escape được diễn giải sau khi loại incidental whitespace, cách viết này giúp bảo toàn khoảng trắng cuối dòng có chủ đích.
- `Y\tZ`: escape `\t` tạo một ký tự tab `U+0009` giữa Y và Z. Tab **không** phải bốn hay tám dấu cách; số khoảng rộng nó chiếm trên màn hình phụ thuộc cách hiển thị.
- Dòng `Q\` với dấu `\` cuối dòng dùng **line continuation** trong text block: nó làm mất line terminator ngay sau Q, nên Q và R ghép thành `QR`. Không có `U+000A` nằm giữa vị trí 7 và 8.
- Dòng cuối R vẫn có LF cuối vì dấu đóng đứng trên dòng tiếp theo.

Cả ba phép `equals(...)` đều trả `true`. Điều này không chỉ kiểm tra tổng độ dài mà còn kiểm tra **đúng tất cả code units theo thứ tự**. Hai chuỗi có cùng `length()` vẫn có thể khác nhau: ví dụ `"A B"` và `"A\tB"` đều dài 3 code units nhưng không bằng nhau.

## 6. Unicode: mỗi vị trí `charAt` không phải luôn là một code point

Java `String` dùng biểu diễn UTF-16. Với những ký tự có mã Unicode lớn hơn `U+FFFF`, Java cần **một cặp surrogate** gồm hai giá trị `char`. Chẳng hạn emoji `🙂` (code point `U+1F642`) chiếm hai UTF-16 code units: `U+D83D` và `U+DE42`.

Với text block:

~~~java
String emojiLine = """
        A🙂B
        """;
~~~

kết quả chứa A, emoji, B, LF. Số lượng:

- **`emojiLine.length() == 5`** vì A = 1, emoji = 2, B = 1, LF = 1 UTF-16 code units.
- **`emojiLine.codePointCount(0, emojiLine.length()) == 4`** vì A, 🙂, B, LF là bốn code points.
- `charAt(1)` trả **high surrogate**, không phải toàn bộ emoji; `charAt(2)` trả **low surrogate**.
- `emojiLine.codePoints()` xử lý cặp surrogate hợp lệ thành code point `U+1F642`.

Vì vậy, với yêu cầu **“kiểm tra từng ô dữ liệu của UTF-16 String”**, `charAt` là phù hợp; với yêu cầu **“duyệt từng Unicode code point”**, dùng `codePoints()` hoặc `codePointAt(...)` cùng cách dịch chỉ số hợp lệ. Cả hai vẫn không mặc định đếm “ký tự người dùng nhìn thấy” (grapheme clusters), bởi một ký tự hiển thị có thể chứa nhiều code points như chữ cái và dấu kết hợp.

### Chương trình Java 17+ số 2: code units, code points và LF

Tạo file **`TextBlockUnicodeAndLineEndingsDemo.java`**:

~~~java
public class TextBlockUnicodeAndLineEndingsDemo {
    public static void main(String[] args) {
        String text = """
                A🙂B
                """;

        System.out.println("utf16Length=" + text.length());
        System.out.println("codePointCount="
                + text.codePointCount(0, text.length()));

        for (int i = 0; i < text.length(); i++) {
            System.out.printf("unit[%d]=U+%04X%n",
                    i, (int) text.charAt(i));
        }

        text.codePoints().forEach(cp ->
                System.out.printf("point=U+%X%n", cp));

        String lines = """
                left
                right
                """;
        System.out.println("normalizedLF="
                + lines.equals("left\nright\n"));
        System.out.println("containsCR=" + lines.contains("\r"));
    }
}
~~~

Lệnh:

~~~bash
javac --release 17 -encoding UTF-8 TextBlockUnicodeAndLineEndingsDemo.java
java TextBlockUnicodeAndLineEndingsDemo
~~~

**Stdout của chương trình:**

~~~text
utf16Length=5
codePointCount=4
unit[0]=U+0041
unit[1]=U+D83D
unit[2]=U+DE42
unit[3]=U+0042
unit[4]=U+000A
point=U+41
point=U+1F642
point=U+42
point=U+A
normalizedLF=true
containsCR=false
~~~

Chương trình trên cũng đã được kiểm thử khi file nguồn được ghi với các line endings **CRLF** trên Windows. Kết quả của phần text block `lines` vẫn bằng `"left\nright\n"` và không chứa CR, đúng với quy tắc chuẩn hóa line terminators của text block. Điều này giúp giải thích vì sao `length()` trong chuỗi không nhất thiết tăng thêm một code unit chỉ vì file mã nguồn lưu bằng CRLF.

**Lưu ý phân biệt:** quy tắc chuẩn hóa này liên quan đến cách xử lý **nội dung nguồn text block**; nếu chương trình sau đó ghép hoặc nhận thêm chuỗi chứa `"\r\n"` tại runtime thì `String` kết quả vẫn có thể chứa CR và LF bình thường. Cần kiểm tra **giá trị cuối cùng tại vị trí đang debug**, không suy luận từ nguồn của một phần chuỗi.

## 7. Phân biệt các giá trị khoảng trắng thường gặp

Các ký tự dễ bị nhầm khi quan sát:

| Giá trị thực | Mã hex | Thường do đâu tạo ra? | Cách nhận diện |
| --- | --- | --- | --- |
| Dấu cách ASCII `' '` | `U+0020` | Khoảng trắng có ý nghĩa, `\s` | `charAt(i) == ' '` |
| Tab `'\t'` | `U+0009` | Escape `\t` hoặc tab thực | `charAt(i) == '\t'` |
| LF `'\n'` | `U+000A` | Dòng mới của text block | `charAt(i) == '\n'` |
| CR `'\r'` | `U+000D` | Chuỗi ghép ở runtime, escape `\r` | `charAt(i) == '\r'` |
| CRLF `"\r\n"` | **Hai** code units | Văn bản có Windows line ending ở runtime | Hai vị trí liên tiếp `U+000D`, `U+000A` |

Với text block chứa một tab ở giữa dòng, tab là **một code unit** dù console có thể đặt con trỏ sang điểm dừng tab tiếp theo. Cũng không nên coi mọi ký tự nhìn giống khoảng trắng là `U+0020`: Unicode còn có những whitespace khác, chẳng hạn non-breaking space `U+00A0`. Dump hex sẽ làm rõ khác biệt.

### Tại sao `System.out.println(text)` thường không đủ?

- `println` thêm newline riêng **sau** chuỗi. Nếu text block đã có newline cuối, có thể nhìn thấy một dòng trống; nếu không có newline cuối, cũng vẫn xuống dòng trên console.
- Trailing spaces nằm cuối dòng rất khó thấy hoặc bị hiển thị không rõ.
- Tab thường được trình hiển thị mở rộng thành khoảng trống tùy độ rộng tab stop.
- Một cặp surrogate không thể được xem chính xác bằng việc in từng `char` riêng lẻ.

Cách đáng tin hơn là in **độ dài, mã UTF-16 của từng vị trí và so sánh bằng `equals`**. Nếu cần kiểm tra ký tự cuối, hãy bảo vệ điều kiện rỗng:

~~~java
if (!text.isEmpty()) {
    char last = text.charAt(text.length() - 1);
    System.out.printf("last=U+%04X%n", (int) last);
}
~~~

Đoạn này là một khối minh họa trong method. Với `"A\n"`, `last` là `U+000A`; với `"A"`, `last` là `U+0041`.

## 8. Các lỗi thực tế và cách phát hiện

### Lỗi A — Quên LF cuối

Kỳ vọng `"SELECT 1"` nhưng text block có dấu đóng ở dòng riêng tạo `"SELECT 1\n"`. Kiểm tra `length()` và `charAt(length - 1)`; nếu API nhận chuỗi đòi không có newline cuối, đặt dấu đóng ngay cuối dòng nội dung theo quy tắc text block, hoặc dùng một phép biến đổi có chủ ý. Đừng gọi `trim()` một cách tùy tiện nếu các khoảng trắng khác cần được bảo toàn.

### Lỗi B — Thừa hoặc thiếu indentation quan trọng

Compiler xóa phần thụt lề **incidental** theo vị trí dòng và dấu đóng, nhưng giữ phần thụt lề **tương đối**. Khi đóng/mở text block được dịch chuyển, kết quả có thể thay đổi. Hãy kiểm tra vị trí đầu dòng bằng `charAt(i)`; dùng `String.equals(expected)` với biểu thức escape cụ thể trong bài test.

### Lỗi C — Cho rằng gõ dấu cách cuối dòng là đủ để giữ lại

Text block thường bỏ trailing whitespace trong bước loại incidental whitespace. Nếu cần **dấu cách ở cuối dòng có chủ ý**, đặt escape `\s` ở cuối dòng nội dung; sau khi xử lý escape nó trở thành dấu cách thực. Khi kiểm tra, tìm code unit `U+0020` ngay trước `U+000A`, như ví dụ `escaped`.

### Lỗi D — Nhầm tab với nhiều dấu cách

Chuỗi `"A\tB"` dài **3 code units**, bất kể tab được vẽ rộng bao nhiêu ô. Chuỗi `"A    B"` dài **6 code units** và không bằng chuỗi có tab. Đừng dùng mắt để kiểm tra; hãy dùng dump code units.

### Lỗi E — Nhầm dấu nối dòng `\` với dấu xuống dòng thực

Trong text block, dấu `\` ở cuối một dòng nội dung có thể **loại line terminator kế tiếp**. Vì vậy `Q\` xuống dòng rồi `R` trở thành `QR`, không phải `Q\nR`. Đây là một escape đặc biệt được xử lý sau khi xác định indentation.

### Lỗi F — Cộng ký tự mã nguồn để dự đoán `length()`

Đây là cách đếm sai vì các dấu `"""` không thuộc chuỗi, indentation có thể bị loại, `\s` tạo một dấu cách thay vì hai ký tự nguồn, `\t` thành một tab, và Unicode supplementary character có thể chiếm hai code units. Hãy gọi `length()` ở runtime trên **giá trị thực**.

### Lỗi G — Giả định một emoji là một `char`

`charAt(i)` trả **code unit**, có thể là một nửa surrogate pair. Duyệt code points bằng `codePoints()` khi muốn xử lý Unicode theo mã ký tự. Đừng cast từng surrogate sang `int` rồi hiểu là mã Unicode đầy đủ của emoji.

### Lỗi H — Vô tình thay đổi dữ liệu trước khi kiểm tra

Các method như `trim()`, `strip()`, `stripIndent()`, `replaceAll(...)` hoặc `lines()` có thể làm biến đổi hoặc chia tách biểu diễn trước khi bạn quan sát. `String.lines()` trả nội dung các dòng **không kèm** line terminators; `split(...)` có các quy tắc riêng về phần tử rỗng cuối. Nếu mục tiêu là **kiểm tra nguyên trạng**, kiểm tra chuỗi gốc trước, rồi mới cân nhắc phép chuẩn hóa nghiệp vụ.

## 9. Quy trình debug một text block trong ứng dụng

1. **Giữ nguyên giá trị cần kiểm tra** trong một biến `String actual`. Nếu chuỗi đã đi qua phép ghép, xử lý input, JSON hoặc hệ thống file, hãy lấy giá trị ở đúng thời điểm xảy ra khác biệt.
2. **In `length()`.** Nếu số lượng không như kỳ vọng, chưa vội kết luận thừa newline; nó có thể là tab, dấu cách hoặc surrogate pair.
3. **Dump `charAt(i)` + mã hex.** Quan sát đầu chuỗi, cuối chuỗi, mỗi `U+000A`, các `U+0020` sát LF và `U+0009`.
4. **Xác định code point khi có Unicode ngoài BMP.** So sánh `length()` với `codePointCount(...)` để không nhầm UTF-16 units với Unicode code points.
5. **So sánh `equals(expected)`** với chuỗi kỳ vọng viết tường minh bằng escapes như `"A\n  B\n"`. `equals` so sánh nội dung chính xác, không bỏ qua khoảng trắng.
6. **Nếu khác, tìm vị trí khác đầu tiên.** Có thể so sánh tuần tự `actual.charAt(i)` và `expected.charAt(i)` với `i < Math.min(actual.length(), expected.length())`, rồi kiểm tra độ dài và phần dư sau vị trí chung cuối.
7. **Xem lại ba bước xử lý text block:** CRLF/CR → LF, xóa incidental whitespace, diễn giải escape. Kiểm tra dấu đóng `"""`, chỗ đặt `\s`, `\t` và dấu `\` cuối dòng.
8. **Sau khi xác nhận nguyên nhân, chọn sửa đúng nhu cầu.** Đặt lại delimiter hoặc thêm escape có chủ đích thường tốt hơn gọi `trim()` hàng loạt, vì `trim()` có thể xóa cả dữ liệu hợp lệ.
9. **Viết test cố định giá trị.** Bên cạnh việc kiểm tra độ dài, dùng `equals(expected)` để bắt trường hợp hai chuỗi dài bằng nhau nhưng khác nội dung.

Có thể dùng `assert actual.equals(expected);` trong chương trình thử nghiệm; chú ý Java `assert` chỉ chạy khi bật assertions, chẳng hạn `java -ea MyClass`. Trong code kiểm thử tự động thông thường, dùng assertion của framework đang dùng (JUnit, v.v.) để có thông báo lỗi cụ thể; không nên chỉ dựa vào log console.

## 10. Câu hỏi luyện tập

**Câu 1.** Text block có giá trị `"Hi\n"`. `length()` là bao nhiêu và `charAt(2)` là gì?  
**Đáp án:** `3` và `'\n'` (`U+000A`).

**Câu 2.** Text block có giá trị `"A\tB"`. Tab được hiển thị rộng bốn cột trên console. `length()` là `3` hay `6`?  
**Đáp án:** `3`; tab là **một UTF-16 code unit**.

**Câu 3.** Vì sao hai đoạn text block có cùng hình dạng gần giống nhau lại có `length()` khác 1?  
**Đáp án:** Có thể một đoạn có **LF cuối** do dấu đóng nằm trên dòng riêng, đoạn còn lại không có vì dấu đóng nằm cùng dòng với nội dung. Kiểm tra code unit cuối để xác nhận.

**Câu 4.** Dòng `X\s` trong text block giúp giữ ký tự nào?  
**Đáp án:** Một dấu cách `U+0020` cuối dòng, vì `\s` được diễn giải sau bước loại incidental whitespace.

**Câu 5.** `String.length()` của `"🙂"` và `codePointCount(0, length())` có giống nhau không?  
**Đáp án:** Không. `length() == 2` và `codePointCount(...) == 1` vì emoji đó dùng một surrogate pair UTF-16.

**Câu 6.** File Java được lưu bằng CRLF. Có mặc định hai ký tự CR và LF cho mỗi newline trong text block không?  
**Đáp án:** Không. Các line terminators trong nội dung text block được chuẩn hóa thành LF. Nếu chương trình ghép thêm CRLF về sau, kết quả cuối vẫn có thể chứa cả hai ký tự.

**Câu 7.** Có thể so sánh hai chuỗi chỉ bằng độ dài để chứng minh chúng giống nhau không?  
**Đáp án:** Không. `"A B"` và `"A\tB"` đều dài 3 nhưng khác code unit ở vị trí 1; cần `equals` hoặc đối chiếu từng vị trí.

## Tài liệu chính thức

- **JEP 378 — Text Blocks:** text block trở thành tính năng chính thức trong Java 15, gồm quy tắc newline, indentation, `\s` và line continuation: https://openjdk.org/jeps/378
- **Java Language Specification 17, §3.10.6 — Text Blocks:** định nghĩa nội dung text block và thứ tự xử lý khi biên dịch: https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.6
- **Java SE 17 `String.length()`:** độ dài tính bằng UTF-16 code units: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#length()
- **Java SE 17 `String.charAt(int)`:** đọc UTF-16 code unit theo chỉ số: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#charAt(int)
- **Java SE 17 `String.codePointCount(int,int)` và `String.codePoints()`:** phân biệt UTF-16 code units với Unicode code points: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#codePointCount(int,int)
- **Oracle Java SE 17 — Programmer's Guide to Text Blocks:** ví dụ về loại indentation, trailing spaces và escape sequences: https://docs.oracle.com/en/java/javase/17/text-blocks/index.html