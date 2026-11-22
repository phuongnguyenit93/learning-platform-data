# StringCharacterIterator và giới hạn khi dùng cho mã lập trình

`java.text.StringCharacterIterator` là lớp Java Core hiện thực giao diện `CharacterIterator`, cho phép **di chuyển tiến, lùi và đặt vị trí trong một chuỗi ký tự**. Nó hữu ích khi một API văn bản cần con trỏ trong một vùng chuỗi, nhưng tên “CharacterIterator” rất dễ gây hiểu nhầm: lớp này duyệt **đơn vị UTF-16 `char`**, không tự ghép surrogate pair thành Unicode code point, không nhận biết grapheme, không tìm ranh giới từ, và **không phân tích được cú pháp mã nguồn Java**.

Bài học thuộc nhóm **Ranh giới văn bản**. Mục tiêu là hiểu hợp đồng iterator, dùng đúng các chỉ số `begin/end/index`, phân biệt code unit/code point/ký tự hiển thị, và nhận diện lúc cần `BreakIterator` hoặc lexer/parser thay vì tiếp tục viết các vòng lặp `char` thủ công. Mọi ví dụ mã nguồn chạy độc lập đều hướng đến Java 17+.

## 1. Khái niệm và phạm vi trách nhiệm

`CharacterIterator` là một giao diện trong `java.text` mô tả giao thức duyệt có vị trí, theo hai chiều, trong một vùng văn bản. `StringCharacterIterator` là lớp hiện thực giao diện đó trên `String`, cung cấp:

- vùng đọc với chỉ số bắt đầu `getBeginIndex()` và kết thúc `getEndIndex()`;
- chỉ số con trỏ hiện tại `getIndex()`;
- các thao tác `first()`, `last()`, `current()`, `next()`, `previous()` và `setIndex(int)`;
- giá trị đặc biệt `CharacterIterator.DONE` khi không còn ký tự hợp lệ;
- khả năng tạo bản sao trạng thái với `clone()`.

`String` trong Java có thể bất biến, nhưng **iterator có trạng thái vị trí thay đổi được**. Một lần gọi `first()` hoặc `setIndex()` thay đổi con trỏ của chính iterator, vì vậy không chia sẻ một instance giữa nhiều thuật toán/luồng rồi mong mỗi bên có một vị trí riêng.

Đoạn minh họa tối giản:

~~~java
import java.text.CharacterIterator;
import java.text.StringCharacterIterator;

StringCharacterIterator it =
        new StringCharacterIterator("Java");

for (char c = it.first();
        c != CharacterIterator.DONE;
        c = it.next()) {
    System.out.print(c);
}
// In: Java
~~~

Đây là **đoạn minh họa bên trong phương thức**. `first()` đặt ở đầu và trả ký tự đầu; `next()` **di chuyển trước một vị trí rồi mới trả ký tự**. Gọi `next()` trước khi xử lý ký tự đầu sẽ làm bỏ mất phần tử đầu tiên. Vòng lặp này cũng có một trường hợp biên với U+FFFF, xem mục 5.

### Không phải BreakIterator

`BreakIterator` dùng để tìm ranh giới ký tự hiển thị, từ, dòng hoặc câu theo quy tắc văn bản/locale; `StringCharacterIterator` chỉ trả `char` ở một vị trí. Một thuật toán tìm từ có thể dùng iterator làm **nguồn dữ liệu**, nhưng iterator không tự biết đâu là dấu cách, dấu câu hoặc ranh giới từ.

## 2. Các phương thức và hợp đồng vị trí

Ví dụ chuỗi `"abXYZ"`:

~~~text
Text:           a  b  X  Y  Z
UTF-16 index:   0  1  2  3  4
endIndex:                      5
~~~

Chỉ số `end` là **exclusive**: nếu vùng `[begin,end)` có `begin=1` và `end=4`, nó bao gồm các chỉ số 1,2,3, tức `bXY`. Tuy nhiên, `getIndex()` **được phép bằng `end`** để biểu diễn trạng thái con trỏ ở cuối.

| API | Tác dụng | Điểm cần lưu ý |
| --- | --- | --- |
| `new StringCharacterIterator(text)` | Tạo con trỏ trên toàn chuỗi tại 0 | Có thể dùng cho chuỗi rỗng |
| `new StringCharacterIterator(text,pos)` | Đặt vị trí ban đầu | `pos` phải hợp lệ |
| `new StringCharacterIterator(text,begin,end,pos)` | Chỉ đọc vùng `[begin,end)` | Chỉ số vẫn theo chuỗi gốc |
| `first()` | Chuyển về `begin`, trả ký tự đầu | Rỗng thì trả `DONE` |
| `last()` | Chuyển về `end-1`, trả ký tự cuối | Rỗng thì trả `DONE` |
| `current()` | Trả `char` ở vị trí hiện tại | Ở `end` thì trả `DONE` |
| `next()` | Tiến một vị trí, trả ký tự mới | Nếu tới `end` thì trả `DONE` |
| `previous()` | Lùi một vị trí, trả ký tự mới | Không vượt `begin` |
| `setIndex(p)` | Đặt vị trí bằng `p` | Hợp lệ khi `begin <= p <= end` |
| `getIndex()` | Lấy chỉ số hiện tại | Có thể bằng `end` |
| `getBeginIndex()`, `getEndIndex()` | Biên vùng | Begin inclusive; end exclusive |

Một cửa sổ:

~~~java
StringCharacterIterator it =
        new StringCharacterIterator("abXYZ", 1, 4, 2);

System.out.println(it.current());       // X
System.out.println(it.getBeginIndex()); // 1
System.out.println(it.getEndIndex());   // 4
~~~

Đây là **đoạn minh họa** với import `java.text.StringCharacterIterator`. `first()` từ đây trả `b`, `last()` trả `Y`; gọi `next()` sau `last()` chuyển con trỏ tới 4 và trả `DONE`. Nếu gọi `previous()` từ vị trí 4, con trỏ quay về 3 và trả `Y`.

`setIndex(end)` là **hợp lệ**, trả `DONE`. Ngược lại, `setIndex(end+1)` hoặc `setIndex(begin-1)` ném `IllegalArgumentException`. Khi xử lý vùng do API hoặc người dùng đưa vào, cần xác minh điều kiện:

~~~text
0 <= begin <= end <= text.length()
begin <= pos <= end
~~~

Đặc biệt, `begin/end` là **UTF-16 offsets** theo `String` chứ không phải byte offsets trong file UTF-8, số code point hay số “chữ” người đọc thấy.

## 3. char UTF-16 không đồng nghĩa Unicode code point

Java `String` đánh chỉ số theo UTF-16 code units. Một giá trị `char` là một đơn vị 16-bit. Một Unicode code point ngoài Basic Multilingual Plane (BMP) cần **hai** đơn vị: high surrogate và low surrogate.

Với chuỗi `A😀B`:

~~~text
Người đọc:        A      😀       B          (3 cụm thấy trong ví dụ)
Code points:     U+0041  U+1F600 U+0042      (3)
UTF-16 units:      A     high low   B         (4)
UTF-16 indexes:    0       1    2    3
~~~

`String.length()` trả `4`, `codePointCount(0,length)` trả `3`; iterator theo `char` đi qua **4** phần tử. Nếu lấy `substring(0,2)` có thể cắt giữa surrogate pair; nếu `setIndex(2)` sẽ trỏ vào low surrogate, không phải emoji nguyên vẹn.

Nếu thuật toán cần code point:

~~~java
String text = "A\uD83D\uDE00B";
int count = text.codePointCount(0, text.length()); // 3

for (int cp : text.codePoints().toArray()) {
    // cp là một int biểu diễn Unicode code point
}
~~~

Đây là đoạn minh họa Java 17. Ngoài `String.codePoints()` còn có `codePointAt(index)` và `Character.charCount(cp)` để tự điều khiển vị trí:

~~~java
int cp = text.codePointAt(index);
index += Character.charCount(cp);
~~~

Ở đây `index` phải là vị trí hợp lệ, đồng thời ứng dụng phải có chính sách với surrogate lẻ/đầu vào không hợp lệ. Dùng `charAt` hoặc `StringCharacterIterator` mà không ghép surrogate sẽ làm sai khi thuật toán thật sự cần xử lý từng code point.

### Code point cũng chưa phải grapheme cluster

Với `"e\u0301"` (e + dấu sắc kết hợp):

~~~text
UTF-16 units: 2
Code points: 2
Người dùng thường nhìn thấy: 1 chữ có dấu
~~~

Một emoji có skin tone modifier hoặc chuỗi nối ZWJ cũng có thể tạo một grapheme cluster từ nhiều code point. `StringCharacterIterator` không có thuật toán nhận diện ranh giới grapheme; `String.codePoints()` cũng không tự gộp các code point thành grapheme. Khi cần chọn văn bản, di chuyển cursor UI hoặc tính số ký tự hiển thị, sử dụng giải pháp Unicode segmentation có kiểm thử, ví dụ `BreakIterator.getCharacterInstance(locale)` ở phạm vi nó hỗ trợ.

**Không giả định** dữ liệu grapheme/emoji của mọi JDK 17 trùng với Unicode/UAX #29 mới nhất; hãy kiểm tra phiên bản và các chuỗi thực tế của sản phẩm.

## 4. Duyệt xuôi, duyệt ngược và quản lý con trỏ

Duyệt xuôi:

~~~java
for (char c = it.first();
        c != CharacterIterator.DONE;
        c = it.next()) {
    // Xử lý một char UTF-16
}
~~~

Duyệt ngược:

~~~java
for (char c = it.last();
        c != CharacterIterator.DONE;
        c = it.previous()) {
    // Xử lý một char UTF-16
}
~~~

Đây là đoạn minh họa có `it` đã được tạo. Sự khác biệt giữa `current` và `next` đáng chú ý: `current` **không di chuyển**, còn `next` thay đổi index; nếu gọi lẫn lộn có thể bị đếm thiếu/trùng một ký tự.

Khi thuật toán cần đi từ vị trí giữa về cả hai phía, ghi lại `getIndex()` trước khi thay đổi cursor. Nếu dùng một iterator cho hai vòng quét và gọi `first` lần nữa, con trỏ của vòng quét trước không được giữ nguyên. Tạo iterator khác hoặc clone khi cần hai tiến trình độc lập.

### Một cửa sổ không phải bản sao String

`new StringCharacterIterator(text,begin,end,pos)` chỉ giới hạn phạm vi duyệt. Nó không biến begin thành 0, không đổi byte layout và không tạo một token mới. Nếu muốn có một `String` độc lập của cửa sổ, gọi `text.substring(begin,end)` khi hợp lý; nhưng chỉ được làm vậy nếu begin/end chính xác theo UTF-16 và không cắt giữa surrogate pair một cách vô tình.

Cửa sổ rất hữu ích khi **một parser khác đã xác định chính xác phạm vi** của từ/token rồi muốn dùng iterator để duyệt lại. Nó không tự tìm phạm vi ấy.

## 5. CharacterIterator.DONE và trường hợp U+FFFF

Hằng `CharacterIterator.DONE` có giá trị `char` `'\uFFFF'`, một **Unicode noncharacter** được chọn làm dấu hiệu hết văn bản. Giao diện được thiết kế với giả định giá trị này không xuất hiện như một ký tự văn bản bình thường.

Tuy nhiên, đối tượng `String` trong Java **có thể chứa code unit 0xFFFF**. Nếu lấy input không được kiểm soát, vòng lặp kiểm tra chỉ bằng `c != CharacterIterator.DONE` có thể dừng **ngay tại ký tự dữ liệu U+FFFF**, dù con trỏ chưa tới `getEndIndex()`.

Thay vì dựa vào sentinel, khi yêu cầu phải duyệt **mọi đơn vị UTF-16 của input tùy ý**, có thể dùng vòng lặp theo index:

~~~java
for (int i = it.getBeginIndex(); i < it.getEndIndex(); i++) {
    char c = it.setIndex(i);
    // c có thể bằng DONE nhưng vẫn là dữ liệu trong vùng
}
~~~

Đây là đoạn minh họa với biến `it` đã có. Nó xử lý mọi code unit trong vùng, kể cả giá trị trùng sentinel. Điều này **không** biến nó thành code-point iterator hoặc lexical analyzer; nó chỉ tránh nhầm giá trị dữ liệu với dấu hiệu kết thúc.

Trong các ứng dụng có dữ liệu đã được xác minh không chứa U+FFFF, vòng lặp `c != DONE` là kiểu được tài liệu API minh họa. Với dữ liệu ngoại lai, hoặc các công cụ phân tích cú pháp/an ninh, nên hiểu giới hạn này và xác định chính sách validation đầu vào.

## 6. Ví dụ Java 17 hoàn chỉnh

Chương trình sau minh họa cửa sổ chỉ số, surrogate pair, marker comment bị hiểu nhầm và U+FFFF sentinel. Phần kết quả dùng chữ ASCII/số nên không phụ thuộc terminal có hiển thị emoji tốt hay không.

Tạo tệp **`StringCharacterIteratorDemo.java`**:

~~~java
import java.text.CharacterIterator;
import java.text.StringCharacterIterator;

public class StringCharacterIteratorDemo {
    public static void main(String[] args) {
        String ascii = "abXYZ";
        StringCharacterIterator window =
                new StringCharacterIterator(ascii, 1, 4, 2);

        System.out.println("Range: "
                + window.getBeginIndex()
                + ".." + window.getEndIndex());
        System.out.println("Current: " + window.current());
        System.out.println("First: " + window.first());
        System.out.println("Last: " + window.last());
        System.out.println("Next is DONE: "
                + (window.next() == CharacterIterator.DONE));
        System.out.println("Index after end: " + window.getIndex());
        System.out.println("Previous: " + window.previous());
        System.out.println("At end is DONE: "
                + (window.setIndex(4) == CharacterIterator.DONE));

        String emoji = "A\uD83D\uDE00B";
        int high = 0;
        int low = 0;
        StringCharacterIterator units =
                new StringCharacterIterator(emoji);

        for (char c = units.first();
                c != CharacterIterator.DONE;
                c = units.next()) {
            if (Character.isHighSurrogate(c)) high++;
            if (Character.isLowSurrogate(c)) low++;
        }

        System.out.println("UTF-16 units: " + emoji.length());
        System.out.println("Code points: "
                + emoji.codePointCount(0, emoji.length()));
        System.out.println("Surrogate halves: " + high + "/" + low);

        String code = "\"// inside string\"; // actual comment";
        int naiveMarkers = 0;
        for (int i = 0; i + 1 < code.length(); i++) {
            if (code.charAt(i) == '/'
                    && code.charAt(i + 1) == '/') {
                naiveMarkers++;
            }
        }
        System.out.println("Naive // markers: " + naiveMarkers);

        String containsDone = "A" + (char) 0xFFFF + "B";
        int seen = 0;
        StringCharacterIterator sentinel =
                new StringCharacterIterator(containsDone);
        for (char c = sentinel.first();
                c != CharacterIterator.DONE;
                c = sentinel.next()) {
            seen++;
        }
        System.out.println("DONE sentinel ambiguity: "
                + seen + "/" + containsDone.length());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 StringCharacterIteratorDemo.java
java StringCharacterIteratorDemo
~~~

Stdout đã được đối chiếu trên JDK:

~~~text
Range: 1..4
Current: X
First: b
Last: Y
Next is DONE: true
Index after end: 4
Previous: Y
At end is DONE: true
UTF-16 units: 4
Code points: 3
Surrogate halves: 1/1
Naive // markers: 2
DONE sentinel ambiguity: 1/3
~~~

**Giải thích:**

1. Vùng `[1,4)` trên `"abXYZ"` chỉ chứa `bXY`. `current` ở vị trí 2 là `X`; `last` trả `Y`; `next` tiếp theo đi tới vị trí `4` và trả `DONE`; `previous` từ đó quay về `Y`.
2. `A😀B` có bốn UTF-16 code units nhưng ba code points. Iterator duyệt được một high surrogate và một low surrogate chứ không tự tạo đối tượng “emoji”.
3. Chuỗi mô phỏng mã nguồn chứa hai cặp `//`, nhưng chỉ cặp bên ngoài string literal là comment Java. Kết quả đếm 2 là **sai nếu dùng như số comment**.
4. Chuỗi `A + U+FFFF + B` có ba code units, nhưng vòng lặp dừng khi gặp `U+FFFF` nên chỉ đếm 1. Đây là ví dụ có chủ đích về sự mơ hồ của `DONE`.

## 7. Vì sao không thể dùng trực tiếp để hiểu mã lập trình?

`StringCharacterIterator` không có khái niệm **token**, **keyword**, **string literal**, **comment**, **operator** hay **AST**. Nó chỉ cho biết đơn vị `char` nào nằm tại vị trí nào. Một **lexer** cho Java phải nhận chuỗi source rồi tạo token theo đặc tả lexical. Sau đó **parser** mới phân tích cấu trúc cú pháp (khai báo, biểu thức, câu lệnh...) dựa trên token.

Ví dụ:

~~~java
String source = "\"// inside string\"; // real comment";
~~~

Đoạn này tạo một chuỗi runtime mô phỏng source text. Có hai cặp `//` nhưng một cặp nằm bên trong string literal. Vòng lặp kiểm tra `source.charAt(i)=='/' && source.charAt(i+1)=='/'` tìm thấy cả hai. Chỉ có lexer hiểu trạng thái literal mới phân biệt được cặp nào là comment.

Một lexer Java thực tế phải xử lý:

- khoảng trắng, line terminators và vị trí dòng/cột;
- Unicode escapes theo quy tắc đầu vào của Java;
- comment dòng `//` và comment khối `/* ... */`;
- string literal, character literal, escape và text block;
- số nguyên/số thực với dấu chấm, tiền tố, suffix và dấu phân cách chữ số;
- identifier Unicode, keyword và contextual keyword;
- operator/token đa ký tự như `==`, `!=`, `->`, `::`, `&&`;
- các trường hợp cú pháp và quy tắc của từng phiên bản Java;
- lỗi lexical, diagnostics và cách tiếp tục parse sau lỗi.

Một state machine rút gọn có thể có các trạng thái:

~~~text
DEFAULT
  "       → STRING
  //      → LINE_COMMENT
  /*      → BLOCK_COMMENT
STRING
  escape  → xử lý ký tự tiếp theo theo grammar
  "       → DEFAULT
LINE_COMMENT
  newline → DEFAULT
BLOCK_COMMENT
  */      → DEFAULT
~~~

Đây **chỉ là sơ đồ ý tưởng**, chưa phải Java lexer đúng: còn text blocks, Unicode escape preprocessing và nhiều chi tiết khác. Một lexer có thể dùng `StringCharacterIterator` làm **nguồn char**, nhưng tính đúng đắn của nó do **thuật toán và đặc tả JLS** quyết định.

### Unicode escape không giống runtime string

Trong source Java, những dãy dấu backslash và ký hiệu `u` có thể được xử lý trong các bước dịch **trước khi chia token**, theo điều kiện hợp lệ của Unicode escape trong JLS. Điều này khác với việc bạn đã có một `String` runtime rồi đưa vào iterator.

Không nên tự dùng một regex để thay thế mọi chuỗi giống `\uXXXX` và gọi đó là lexer; quy tắc backslash hợp lệ, Unicode escape và các giai đoạn phân tách source phải tuân thủ đặc tả Java. Với công cụ kiểm tra, refactor, compile hoặc security scanning, ưu tiên compiler API hoặc lexer/parser chuyên dụng được kiểm thử theo phiên bản Java.

### Identifier trong Java phân biệt chữ hoa/thường

Java không mặc định đổi identifier sang lowercase: `name` và `Name` là hai tên khác nhau. `StringCharacterIterator` không xác nhận được tên hợp lệ chỉ bằng việc kiểm tra `Character.isLetter(c)`.

Nếu phải duyệt identifier Unicode, hãy cân nhắc API **code point**:

~~~java
int cp = source.codePointAt(index);
boolean start = Character.isJavaIdentifierStart(cp);
boolean part = Character.isJavaIdentifierPart(cp);
index += Character.charCount(cp);
~~~

Đây là đoạn minh họa với `String source` và `int index` hợp lệ. Các phép kiểm tra trên `int cp` chỉ hỗ trợ phân loại code point; chúng **không** thay thế kiểm tra keyword, Unicode escapes, ngữ cảnh lexical, các ký tự ignorable hoặc grammar Java.

## 8. Chọn công cụ đúng với loại ranh giới

| Nhu cầu | Công cụ/chiến lược | Giới hạn |
| --- | --- | --- |
| Duyệt một vùng UTF-16 trong `String` | `StringCharacterIterator` | Chỉ trả `char` và chỉ số, có sentinel |
| Lấy `char` tại một vị trí cụ thể | `String.charAt(i)` | Không ghép code point |
| Duyệt code points Unicode | `String.codePoints()`, `codePointAt` | Không tách grapheme |
| Phân đoạn từ, câu, dòng, chữ hiển thị | `BreakIterator`/Unicode segmentation | Phụ thuộc rules/runtime; không phân tích Java |
| Chuẩn hóa biểu diễn Unicode | `java.text.Normalizer` | Không nhận biết từ/token |
| Xác định lexical tokens của Java | Lexer tuân thủ JLS | Cần states, escapes, phiên bản |
| Phân tích cú pháp Java, refactor | Parser/compiler API, AST | Cần ngữ nghĩa cấu trúc |
| Kiểm tra Unicode identifier | Code-point APIs và grammar kiểm chứng | Không chỉ `isJavaIdentifierStart` |
| Đọc source file | `Reader`/charset phù hợp rồi lexer | UTF-8 bytes khác UTF-16 offsets |

### BreakIterator và CharacterIterator phối hợp thế nào?

`BreakIterator` có thể nhận text thông qua `setText(String)` hoặc `setText(CharacterIterator)`. Điều đó **không** làm `StringCharacterIterator` tự biết ranh giới: nó là một nguồn/cursor; thuật toán tìm vị trí ngắt thuộc `BreakIterator`.

~~~text
StringCharacterIterator:   ký tự/đơn vị UTF-16 ở offset
BreakIterator:             vị trí ngắt văn bản theo quy tắc
Lexer Java:                token theo lexical grammar
Parser Java:               cấu trúc cú pháp/AST
~~~

Dùng đúng tầng phụ thuộc việc bạn muốn hiển thị/soạn văn bản tự nhiên, xử lý code point hay thực sự hiểu source code.

## 9. Ranh giới byte, UTF-16, code point và editor offset

Source Java trên đĩa có thể được lưu bằng UTF-8. Sau khi giải mã theo charset, một `String` Java dùng chỉ số UTF-16. Vì vậy:

~~~text
UTF-8 bytes → decode → Java String (UTF-16 indexed)
                           |
                           v
                       lexer/parser
                           |
                           v
                       token spans
~~~

Một vị trí byte offset trong file **không** tự tương đương với `String` index. Một code-point index cũng khác UTF-16 index nếu có code point ngoài BMP.

Đặt tên rõ ràng cho hợp đồng vị trí:

~~~text
startByteOffset
startUtf16Offset
endUtf16Offset
startCodePointIndex
startLine
startColumn
~~~

Không lấy `substring(startByteOffset,endByteOffset)` nếu chỉ số ấy thật sự là byte offset. Không tự “cộng 1 cho mỗi ký tự người dùng thấy” để tính offset source: Unicode combining marks, surrogate pairs, tab và CRLF có thể khiến đơn vị đo khác nhau.

Khi một parser trả về range đã được kiểm chứng theo UTF-16, `StringCharacterIterator(text,begin,end,pos)` có thể hữu ích để đọc lại phần source ấy. Tuy nhiên, **iterator không tạo ra range token**, không tự đếm dòng/cột và không bảo đảm các range nằm tại ranh giới grapheme/code point.

## 10. Hiệu năng, trạng thái và lựa chọn thay thế

- `StringCharacterIterator` có state nên có nguy cơ xung đột khi tái sử dụng giữa nhiều vòng quét.
- Trong một phép duyệt tuyến tính, chi phí chủ yếu là đọc lần lượt các đơn vị UTF-16; nó không tạo sẵn một danh sách code point hay AST.
- Nếu chỉ cần một vị trí, `charAt(i)` thường đơn giản hơn.
- Nếu cần đọc file rất lớn hoặc dữ liệu mạng, một lexer dựa trên `Reader`/stream với lookahead được thiết kế đúng có thể tránh giữ toàn bộ source trong một `String`; tuy nhiên độ đúng grammar vẫn là yêu cầu chính.
- Không dùng `StringCharacterIterator` để tự giải mã file; charset được áp ở bước đọc bytes.
- Không dùng nó để tự normalize Unicode hoặc chuyển chữ theo locale.
- Nếu một thuật toán cần dùng chung nội dung nguồn nhưng có nhiều con trỏ, tạo iterator riêng/clone khi thích hợp thay vì dùng chung một con trỏ mutable.
- Với syntax highlighting, code navigation hoặc refactor, compiler/parser thường đáng tin hơn một tập regex đơn giản, nhất là khi mã nguồn có nhiều loại literal và escape.

## 11. Bảng lỗi thường gặp

| Sai lầm | Vì sao sai | Cách phòng tránh |
| --- | --- | --- |
| Coi `char` là Unicode code point | Emoji có surrogate pair | Dùng code-point APIs |
| Coi code point là ký tự người dùng thấy | Dấu kết hợp/emoji sequences | Dùng Unicode segmentation |
| Dùng iterator như lexer | Không có lexical states | Lexer/parser theo JLS |
| Đếm mọi `//` là comment | Có thể nằm trong literal | Phân tích string/comment đúng |
| Dùng regex giản lược cho text block/escape | Thiếu grammar Java | Parser/lexer được kiểm thử |
| Nhầm `end` là inclusive | `end` là vị trí ngay sau vùng | Luôn dùng `[begin,end)` |
| Nghĩ `setIndex(end)` ném lỗi | `end` hợp lệ cho cursor | Xử lý `DONE` |
| Dựa duy nhất vào `c != DONE` với input chứa U+FFFF | Giá trị dữ liệu trùng sentinel | Validation hoặc loop theo index |
| Dùng UTF-8 byte offset như UTF-16 index | Độ dài khác | Chuyển đổi đúng đơn vị |
| Dùng chung iterator trên nhiều luồng | Vị trí bị thay đổi | Instance riêng |
| Cho rằng BreakIterator là lexer | Quy tắc từ tự nhiên khác Java tokens | Tách tầng xử lý |
| Dùng `isJavaIdentifierStart(char)` cho mọi Unicode | Có supplementary code points | Overload nhận `int` và grammar |
| Lowercase tên identifier trước khi parse | Java phân biệt case | Bảo toàn mã nguồn |
| Dùng iterator để đếm grapheme UI | Không có segmentation | Công cụ boundary phù hợp |

## 12. Kiểm thử và bài tập

Một ma trận test nên có:

- Vùng `new StringCharacterIterator("abXYZ",1,4,2)`: kiểm tra `current/first/last/next/previous` và `getIndex` ở `end`.
- Vùng rỗng `[begin,begin)`: kiểm tra `DONE` và không vượt biên.
- `setIndex(end)` hợp lệ; `setIndex(end+1)` ném `IllegalArgumentException`.
- `A😀B`: 4 UTF-16 units, 3 code points; iterator thấy hai surrogate halves.
- `e + combining acute`: có thể là một chữ nhìn thấy nhưng hai code points.
- String chứa U+FFFF: loop theo sentinel dừng sớm, loop theo chỉ số vẫn thấy đủ đơn vị.
- `//` bên trong và bên ngoài string literal: naïve counter sai với số comment.
- Source có escape, text block, Unicode identifiers: kiểm thử bằng lexer/parser phù hợp.
- Kiểm tra offset từ file UTF-8 và UTF-16 `String` không bị trộn.
- Hai thuật toán dùng cùng iterator: thử thay đổi vị trí để thấy mutable state.

**Câu 1.** `StringCharacterIterator` trả `char` hay code point?

**Đáp án:** Trả `char` UTF-16. Một code point ngoài BMP dùng hai `char`.

**Câu 2.** Với `StringCharacterIterator("abXYZ",1,4,2)`, tại sao `getEndIndex() == 4`?

**Đáp án:** Vùng được phép đọc là các chỉ số 1,2,3; 4 là chỉ số **ngay sau** ký tự cuối. `end` là exclusive nhưng vẫn là vị trí con trỏ hợp lệ.

**Câu 3.** Có thể dùng `StringCharacterIterator` để nhận ra `//` là comment Java không?

**Đáp án:** Không chỉ bằng iterator; phải có trạng thái lexical và xử lý literal/comment theo grammar Java.

**Câu 4.** Tại sao vòng lặp `c != CharacterIterator.DONE` có thể dừng trước cuối?

**Đáp án:** `DONE` trùng `char` U+FFFF, một code unit mà `String` Java có thể chứa.

**Câu 5.** Duyệt code points đã đủ nhận biết một grapheme chưa?

**Đáp án:** Chưa. Một grapheme có thể gồm nhiều code points (dấu kết hợp hoặc emoji sequence).

**Bài thực hành:** Duyệt `A😀B` bằng `StringCharacterIterator` và `String.codePoints()`, đối chiếu số phần tử. Giới hạn iterator vào `bXY`, thử `setIndex(end)` và chỉ số ngoài phạm vi. Sau đó tạo chuỗi source có `//` trong literal và comment thật; xây bảng token mong muốn rồi giải thích vì sao iterator không sinh được bảng này nếu thiếu lexer.

## 13. Tài liệu chính thức

- [StringCharacterIterator — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/StringCharacterIterator.html): ba constructor, phạm vi và phương thức cursor.
- [CharacterIterator — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/CharacterIterator.html): `DONE` và hợp đồng `first/next/previous/setIndex`.
- [String — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): UTF-16 indexing, `length`, `codePointAt` và `codePoints`.
- [Character — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html): surrogate pair, code point và ký tự identifier.
- [BreakIterator — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/BreakIterator.html): boundary segmentation.
- [Java Language Specification 17, chương 3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html): Unicode escapes, lexical structure, comments và tokens.
- [Compiler Tree API — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/jdk.compiler/com/sun/source/tree/package-summary.html): cây cú pháp dành cho công cụ phân tích nguồn.

**Kết luận:** `StringCharacterIterator` là con trỏ **UTF-16** trên chuỗi có vùng chỉ số, không phải Unicode code-point iterator, bộ tìm ranh giới grapheme, lexer hoặc parser. Dùng nó khi cần giao diện `CharacterIterator`; dùng code-point/segmentation API cho Unicode và lexer/parser theo **JLS** khi yêu cầu thực sự là hiểu mã lập trình.
