# String.translateEscapes với chuỗi chứa biểu diễn escape

## Mục tiêu và ngữ cảnh

Trong Java, escape sequence là cách biểu diễn các ký tự khó nhìn thấy hoặc cần thoát cú pháp, như newline, tab, dấu nháy và backslash. `String.translateEscapes()` giải mã các **biểu diễn escape đã tồn tại bên trong một đối tượng `String` lúc chương trình chạy**, dựa trên các quy tắc escape của Java string literal. Đây không phải phương thức parse JSON hay cách thay thế cho quy tắc escape mà compiler thực hiện khi đọc mã nguồn.

Ví dụ, một file cấu hình có thể chứa đúng hai ký tự `\` và `n`. Khi đọc file ấy thành String, chương trình chưa có ký tự newline: nó chỉ có một biểu diễn văn bản. Nếu định dạng cấu hình chủ ý dùng **Java-style escapes**, gọi `translateEscapes()` có thể chuyển `\n` thành ký tự xuống dòng thật. Nhưng với String đã chứa newline, gọi phương thức này thường không cần thiết.

Phương thức `String.translateEscapes()` có từ **Java 15** và tiếp tục được hỗ trợ trong Java hiện đại. Dù bài nằm trong module Java 14, toàn bộ ví dụ dùng **Java 17+ ổn định**, không cần chế độ preview và không sử dụng API legacy.

Sau bài học, bạn sẽ phân biệt được ba lớp biểu diễn: **ký tự viết trong source code**, **ký tự thật nằm trong String runtime**, và **hình thức hiển thị trên log/console**. Bạn cũng sẽ biết escape hợp lệ, các giới hạn với `\uXXXX`, ngoại lệ khi escape sai và cách tránh giải mã hai lần.

## 1. Phân biệt escape trong Java source và String runtime

So sánh hai khai báo:

~~~java
String decodedByCompiler = "A\nB";
String encodedAtRuntime = "A\\nB";
~~~

Ở dòng thứ nhất, Java compiler đã diễn giải `\n` trong string literal thành **một ký tự LF U+000A**. `decodedByCompiler.length()` bằng `3`: các ký tự `A`, LF, `B`.

Ở dòng thứ hai, hai backslash trong source `\\` được compiler diễn giải thành **một ký tự backslash thật**, sau đó là chữ `n`. Vì thế `encodedAtRuntime.length()` bằng `4`: `A`, backslash, `n`, `B`. Lúc này, và chỉ lúc này, gọi:

~~~java
String result = encodedAtRuntime.translateEscapes();
boolean equivalent = result.equals(decodedByCompiler);
~~~

sẽ cho `equivalent == true`. Đoạn code minh họa ở hai khối trên có thể được đặt trong cùng một phương thức Java.

**Không nhầm lẫn:** trình gỡ lỗi có thể hiển thị một newline thật dưới dạng hai dấu nhìn thấy `\n` để dễ đọc, nhưng đó chỉ là **cách trình bày**, không chứng minh String đang chứa backslash + chữ n. Dùng `length()`, `charAt()` hoặc in mã Unicode để kiểm tra khi kết quả chính xác quan trọng.

### Bảng kiểm tra nhanh

| Java source | Giá trị String tại runtime | Độ dài | Sau `translateEscapes()` |
|---|---|---:|---|
| `"\n"` | Một LF thật | 1 | Vẫn là LF |
| `"\\n"` | Backslash + chữ `n` | 2 | Một LF thật |
| `"\t"` | Một TAB thật | 1 | Vẫn là TAB |
| `"\\t"` | Backslash + chữ `t` | 2 | Một TAB thật |
| `"\\s"` | Backslash + chữ `s` | 2 | Một space U+0020 |
| `"A\\nB"` | `A`, backslash, `n`, `B` | 4 | `A`, LF, `B` |

Giải mã bằng `translateEscapes()` **không thay đổi đối tượng String gốc**. String bất biến: phương thức trả về một giá trị String để sử dụng hoặc lưu vào biến mới. Một lời gọi bỏ kết quả như `encodedAtRuntime.translateEscapes();` không khiến `encodedAtRuntime` tự chuyển sang chứa newline.

## 2. Cú pháp và hợp đồng của phương thức

Chữ ký public trong `java.lang.String`:

~~~java
public String translateEscapes()
~~~

Đây là chữ ký API để giải thích, không phải phương thức bạn cần tự cài đặt. Ví dụ áp dụng:

~~~java
String encoded = "first\\nsecond";
String decoded = encoded.translateEscapes();

System.out.println(decoded.equals("first\nsecond")); // true
~~~

Các điểm quan trọng:

- Phương thức hoạt động trên **giá trị String đang có**; không đọc hay tự tìm một file, JSON hoặc nguồn dữ liệu khác.
- Các cặp backslash + ký tự theo sau được diễn giải theo tập escape Java có hỗ trợ.
- Ký tự bình thường không phải escape vẫn được giữ.
- Escape không hợp lệ làm phát sinh **`IllegalArgumentException` lúc runtime**, không phải lỗi biên dịch nếu đầu vào được xây dựng hợp lệ từ các chuỗi chứa backslash.
- `translateEscapes()` không có tham số tùy chọn; không thể yêu cầu chỉ giải mã `\n` và bỏ qua mọi escape khác bằng cùng API.
- **Không giải mã Unicode escape như `\u0041` hoặc `\u2022`.** Đây là giới hạn được nêu rõ trong tài liệu chính thức.

Với dữ liệu đầu vào ngoài chương trình, phải biết rõ định dạng quy định sử dụng Java-style escapes thì mới nên gọi phương thức.

## 3. Những escape được hỗ trợ

Theo Java SE 17 `String.translateEscapes()`:

| Chuỗi biểu diễn escape | Ký tự sau dịch | Ý nghĩa |
|---|---|---|
| `\b` | U+0008 | Backspace |
| `\t` | U+0009 | Horizontal tab |
| `\n` | U+000A | Line feed |
| `\f` | U+000C | Form feed |
| `\r` | U+000D | Carriage return |
| `\s` | U+0020 | Một dấu cách |
| `\"` | `"` | Dấu nháy kép |
| `\'` | `'` | Dấu nháy đơn |
| `\\` | `\` | Một backslash |
| `\0` đến `\377` | Các ký tự tương ứng giá trị octal | Chữ số bát phân Java |
| Backslash ngay trước line terminator thật | Không tạo ký tự | Line continuation: loại bỏ backslash và line terminator |

Mỗi mục ở cột đầu là **biểu diễn nằm trong một String trước khi dịch**. Để tạo biểu diễn đó trực tiếp bằng Java source, bạn phải xét thêm một lớp escape do compiler xử lý:

~~~java
String encodedTab   = "\\t";
String encodedSpace = "\\s";
String encodedQuote = "\\\"";
String encodedSlash = "\\\\";
~~~

Các giá trị String ở trên có độ dài tương ứng là `2`, `2`, `2`, `2`. Sau `translateEscapes()`, mỗi giá trị biến thành **một ký tự**: TAB, space, dấu nháy kép, backslash.

### `\s` có phải regex whitespace không?

**Không.** Với `String.translateEscapes()`, `\s` chỉ tạo **một space U+0020**. Trong regex, chuỗi ký hiệu `\s` mang ý nghĩa lớp ký tự whitespace, nhưng `translateEscapes()` không phải bộ parser biểu thức chính quy. Nếu bạn xây regex bằng String, cần phân biệt lớp escape của **Java source** với lớp escape của **regex engine**; không trộn các quy tắc đó.

## 4. Minh họa hai tầng escape khi viết source Java

Muốn chương trình in trực tiếp dòng mới, bạn có thể viết:

~~~java
System.out.print("A\nB");
~~~

Compiler xử lý `\n` ngay khi biên dịch. Không cần dịch runtime.

Muốn mô phỏng dữ liệu file chứa văn bản `A\nB` mà **chưa** được giải mã:

~~~java
String fromConfiguration = "A\\nB";
String readyToDisplay = fromConfiguration.translateEscapes();
System.out.print(readyToDisplay);
~~~

Ở đây Java source `"A\\nB"` chỉ là cách để **tạo dữ liệu mẫu** chứa backslash + chữ n. Trong ứng dụng thật, `fromConfiguration` thường được đọc từ file hoặc nhận từ API; phần mã đọc file không có vai trò dịch Java escape trừ khi chính parser của định dạng đó đã làm như vậy.

**Lưu ý quan trọng:** không suy luận từ việc console xuống dòng rằng source String ban đầu chắc chắn chứa `\n`. Nó có thể đã chứa LF thật từ trước, hoặc console là nơi đang chuyển các ký tự điều khiển sang hình thức trình bày.

## 5. Không giải mã Unicode escape dạng `\uXXXX`

Java hỗ trợ Unicode escapes trong **quá trình đọc mã nguồn**, theo JLS `3.3. Chúng được compiler xử lý ở bước rất sớm, không phải một escape runtime được `String.translateEscapes()` chuyển đổi.

Muốn biểu diễn nguyên văn **backslash rồi `u0041`** trong một String runtime, có thể xây dựng theo hai phần:

~~~java
String unicodeSpelling = "\\" + "u0041";
try {
    unicodeSpelling.translateEscapes();
    System.out.println("unexpected");
} catch (IllegalArgumentException ex) {
    System.out.println("unicode-not-supported");
}
~~~

Đoạn này có thể đặt trong phương thức Java 17. Kết quả là `unicode-not-supported`. Chia nguồn thành hai literal tránh vô tình cho compiler nhận một Unicode escape trong bước phân tích lexical Java source.

Không dùng `translateEscapes()` để giải mã JSON có `\uXXXX`: **JSON parser** chịu trách nhiệm các escape theo quy tắc JSON, bao gồm Unicode escapes và xử lý cặp surrogate. Thay bằng các phép `replace` tự chế mà không xác thực đầu vào dễ sai với dấu backslash được escape nhiều lớp hoặc dữ liệu không hợp lệ.

## 6. Giải mã hai lần không tương đương giải mã một lần

Xét chuỗi runtime có **hai ký tự backslash rồi chữ n**. Viết trong Java source:

~~~java
String encodedTwice = "\\\\n";
~~~

`encodedTwice.length()` bằng `3` (hai backslash, một chữ `n`). Khi gọi:

~~~java
String once = encodedTwice.translateEscapes();
String twice = once.translateEscapes();
~~~

`once` dài `2`: backslash + chữ `n`. Trong lượt dịch đầu tiên, cặp backslash `\\` trở thành một backslash; chữ `n` sau đó không được tự diễn giải lần nữa trong cùng lượt.

`twice` dài `1`: ký tự LF. Ở lượt dịch thứ hai, cặp backslash + `n` đã hiện diện ngay trong **đầu vào** nên được chuyển thành LF.

~~~java
System.out.println(encodedTwice.length()); // 3
System.out.println(once.length());         // 2
System.out.println(twice.length());        // 1
~~~

Các đoạn trên thuộc cùng một ví dụ trong phương thức, không phải những chương trình độc lập. Chúng cho thấy `translateEscapes()` **không phải phép biến đổi luôn cho kết quả giống nhau sau nhiều lần gọi**. Vì vậy, pipeline xử lý cấu hình cần xác định rõ giá trị nào **encoded** và giá trị nào **decoded**, tránh tầng API A đã dịch rồi tầng B lại dịch lần nữa.

## 7. Octal escape

Escape octal sử dụng các chữ số `0..7`. Ví dụ:

~~~java
String octalSpelling = "\\101\\040\\102";
String decoded = octalSpelling.translateEscapes();
System.out.println(decoded.equals("A B")); // true
~~~

- `\101` (bát phân) bằng `65` (thập phân), tương ứng chữ `A`.
- `\040` bằng `32`, tương ứng một dấu cách.
- `\102` bằng `66`, tương ứng chữ `B`.

Quy tắc cú pháp cần nhớ: một chữ số octal có thể đứng riêng, hai chữ số octal có thể ghép, còn **dãy ba chữ số phải có chữ số đầu thuộc `0..3`**; mức cao nhất là `\377`. Không có octal escape hợp lệ `\8` hay `\9`. Một dãy dài hơn như biểu diễn `\1234` không được đọc như một mã octal bốn chữ số duy nhất: chỉ tiêu thụ số chữ số hợp lệ cho escape, rồi xử lý ký tự còn lại.

`translateEscapes()` hỗ trợ các quy tắc này vì theo hợp đồng nó mô phỏng escape của Java string literal. Tuy nhiên, không nên ưu tiên octal khó đọc trong các chuỗi mới nếu tên escape như `\n`, `\t` hoặc `\s` đã diễn đạt đúng mục đích.

## 8. Backslash + line terminator: quy tắc khác hoàn toàn `\n`

Hai tình huống dễ nhầm:

**Tình huống A — biểu diễn backslash + chữ n:**

~~~java
String text = "left\\nright";
String translated = text.translateEscapes();
System.out.println(translated.equals("left\nright")); // true
~~~

Nội dung sau dịch có **LF thật** giữa `left` và `right`.

**Tình huống B — backslash đứng ngay trước LF thật:**

~~~java
String text = "left\\" + "\n" + "right";
String translated = text.translateEscapes();
System.out.println(translated.equals("leftright")); // true
~~~

Đầu vào tình huống B chứa backslash + **line terminator thật**, không phải chữ `n`. Quy tắc **line continuation** của Java bỏ cả backslash và line terminator. Do đó không có LF trong kết quả.

Khi chuyển dữ liệu từ một định dạng khác, phải biết chính xác cặp ký tự ở runtime là gì. Một đoạn log có hiển thị `\n` không luôn cung cấp đủ bằng chứng; dùng `length()` hoặc phương thức hiển thị escape một cách rõ ràng.

## 9. Escape không hợp lệ và IllegalArgumentException

Phương thức không dịch tùy ý mọi cặp bắt đầu bằng backslash. Ví dụ các biểu diễn runtime sau không thuộc tập escape được hỗ trợ:

~~~text
\q
\x41
\z
\u0041
\
~~~

Dòng cuối trong khối văn bản trên mô tả **một backslash duy nhất ở cuối String**, không có ký tự theo sau. Với các dạng escape sai, phương thức ném `IllegalArgumentException`.

Ví dụ:

~~~java
String invalid = "\\q";
String trailing = "\\";

try {
    invalid.translateEscapes();
} catch (IllegalArgumentException ex) {
    System.out.println("invalid");
}

try {
    trailing.translateEscapes();
} catch (IllegalArgumentException ex) {
    System.out.println("trailing");
}
~~~

Đoạn này có thể đặt trong phương thức; kết quả lần lượt là `invalid` và `trailing`.

**Thiết kế xử lý lỗi:** khi dữ liệu lấy từ user, file hoặc mạng, đừng giả định mọi backslash đều tạo một escape hợp lệ. Có thể bắt `IllegalArgumentException` và chuyển nó thành lỗi xác thực đầu vào theo hợp đồng ứng dụng. Không tự động nuốt lỗi rồi âm thầm giữ chuỗi gốc nếu việc giải mã là bắt buộc, cũng không in toàn bộ dữ liệu nhạy cảm vào log chỉ để tìm escape lỗi.

Không được dùng `translateEscapes()` như bộ parser JSON, shell, URL, HTML hoặc JavaScript; tập escape và ngữ nghĩa của các định dạng đó không hoàn toàn giống Java string literal.

## 10. Với text block: compiler đã xử lý những escape ở source

Java text block (`"""..."""`) chính thức từ Java 15. Trong text block source, compiler xử lý theo thứ tự: chuẩn hóa line endings, khử incidental whitespace và **cuối cùng** dịch escape sequence.

Ví dụ:

~~~java
String alreadyDecoded = """
        top\nnext
        """;
~~~

Ở đây `\n` là escape trong **source text block**, được compiler dịch thành LF. Dấu đóng ở dòng riêng nên sau chữ `next` còn một LF cuối text block. Chuỗi runtime đã chứa các newline thật, không cần `translateEscapes()`.

Khi bạn thật sự cần lưu **biểu diễn escape để giải mã về sau**, phải viết backslash được escape:

~~~java
String represented = """
        top\\nnext
        """;
String translated = represented.translateEscapes();
~~~

Với text block này, `represented` chứa `top`, backslash + chữ `n`, `next`, rồi LF cuối. `translated` chứa `top`, LF, `next`, LF cuối. Hai nội dung runtime khác nhau dù source trông rất giống.

Điều này cũng lý giải vì sao `\s` và `\040` thường được đặt ở **cuối dòng nguồn text block**: compiler dịch chúng **sau** khi đã khử trailing whitespace vật lý, giúp giữ một dấu cách cần thiết trong kết quả. Đây là hành vi compiler, khác với gọi phương thức trên String runtime nhận từ bên ngoài.

## 11. Chương trình Java 17+ đầy đủ, stdout kiểm chứng được

Để không phải đoán dấu cách, backslash, TAB và LF dựa trên cách terminal hiển thị, ví dụ sử dụng hàm `visible`: backslash thật sẽ được hiển thị thành hai dấu backslash; LF thành hai ký tự nhìn thấy `\n`; TAB thành `\t`; dấu cách thành ký hiệu `·`.

Tạo file **`TranslateEscapesDemo.java`**:

~~~java
public class TranslateEscapesDemo {

    private static String visible(String input) {
        return input.replace("\\", "\\\\")
                .replace("\n", "\\n")
                .replace("\t", "\\t")
                .replace("\r", "\\r")
                .replace(" ", "·");
    }

    public static void main(String[] args) {
        String represented = "A\\nB\\tC\\sD";
        String translated = represented.translateEscapes();

        System.out.println("represented=" + visible(represented));
        System.out.println("translated=" + visible(translated));
        System.out.println("lengths=" + represented.length()
                + "->" + translated.length());
        System.out.println("sameAsLiteral="
                + translated.equals("A\nB\tC D"));

        String octal = "\\101\\040\\102";
        System.out.println("octal=" + visible(octal.translateEscapes()));

        String quote = "\\\"Hello\\\"";
        System.out.println("quote=" + visible(quote.translateEscapes()));

        String continued = "left\\" + "\n" + "right";
        System.out.println("continued="
                + visible(continued.translateEscapes()));

        String doubleRepresentation = "\\\\n";
        String once = doubleRepresentation.translateEscapes();
        String twice = once.translateEscapes();
        System.out.println("onePass=" + visible(once)
                + ", length=" + once.length());
        System.out.println("twoPass=" + visible(twice)
                + ", length=" + twice.length());

        String encodedBlock = """
                top\\nnext
                """;
        System.out.println("block=" + visible(encodedBlock));
        System.out.println("blockTranslated="
                + visible(encodedBlock.translateEscapes()));

        String unicodeSpelling = "\\" + "u0041";
        try {
            unicodeSpelling.translateEscapes();
            System.out.println("unicode=unexpected");
        } catch (IllegalArgumentException ex) {
            System.out.println("unicode=not-supported");
        }

        try {
            "\\q".translateEscapes();
            System.out.println("invalid=unexpected");
        } catch (IllegalArgumentException ex) {
            System.out.println("invalid=IllegalArgumentException");
        }

        try {
            "\\".translateEscapes();
            System.out.println("trailing=unexpected");
        } catch (IllegalArgumentException ex) {
            System.out.println("trailing=IllegalArgumentException");
        }
    }
}
~~~

Biên dịch với JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 --release 17 TranslateEscapesDemo.java
java TranslateEscapesDemo
~~~

**Standard output chính xác:** mỗi lần `println` tạo một dòng vật lý; các chuỗi `\n` và `\t` nhìn thấy trong giá trị bên dưới là **biểu diễn do hàm `visible` tạo ra**, không phải newline/tab thật ở giữa dòng in.

~~~text
represented=A\\nB\\tC\\sD
translated=A\nB\tC·D
lengths=10->7
sameAsLiteral=true
octal=A·B
quote="Hello"
continued=leftright
onePass=\\n, length=2
twoPass=\n, length=1
block=top\\nnext\n
blockTranslated=top\nnext\n
unicode=not-supported
invalid=IllegalArgumentException
trailing=IllegalArgumentException
~~~

### Giải thích các dòng then chốt

- `represented` có **10 ký tự** tại runtime: `A`(1) + backslash/chữ `n`(2) + `B`(1) + backslash/chữ `t`(2) + `C`(1) + backslash/chữ `s`(2) + `D`(1). Sau giải mã, còn **7 ký tự**: `A`, LF, `B`, TAB, `C`, space, `D`.
- `sameAsLiteral=true` vì giá trị đã dịch tương đương literal `"A\nB\tC D"` do compiler xử lý.
- `octal=A·B` cho thấy `\040` tạo đúng một space.
- `quote="Hello"` cho thấy hai escape dấu nháy kép được dịch thành hai dấu nháy thật.
- `continued=leftright` cho thấy backslash + LF thật bị bỏ, không chèn newline.
- `onePass` có backslash + chữ `n`, nên hàm `visible` in hai backslash nhìn thấy trước chữ `n`; `twoPass` đã là LF nên hàm in đúng một backslash nhìn thấy trước `n`. Dấu cách trong `, length=` là phần văn bản log, **không phải** ký tự của biến `once` hoặc `twice`.
- `block` chứa biểu diễn `\n` ở giữa, nhưng cũng có một LF thật ở cuối text block. `blockTranslated` chứa LF thật ở cả hai vị trí.
- `unicode`, `invalid` và `trailing` minh họa các `IllegalArgumentException` khác nhau mà không phụ thuộc nội dung message của ngoại lệ, vốn không cần thiết cho mục tiêu học tập.

**Vì sao không in String thẳng ra console?** Khi có TAB/LF, terminal biến chúng thành khoảng trắng hoặc dòng mới; một biểu diễn kiểm chứng như `visible` giúp QA khẳng định từng ký tự và số lượng ký tự dễ dàng hơn.

## 12. Đọc dữ liệu từ file hay framework: phải biết nó đã được giải mã chưa

Giả sử một file thuần chứa:

~~~text
Hello\nWorld
~~~

Nếu đọc **như văn bản thuần** (ví dụ đọc file UTF-8 và nhận nguyên ký tự), String nhận được có thể chứa `\` + `n`, khi đó `translateEscapes()` chuyển thành LF. Ngược lại, một JSON parser nhận chuỗi JSON có escape `\n` thường đã giải mã chúng thành LF trước khi trả về String cho ứng dụng.

Đừng đoán dựa vào vẻ ngoài của giá trị trong debugger. Hãy xét **hợp đồng nguồn dữ liệu**:

1. Nguồn có quy định Java-style escapes hay một định dạng escape khác?
2. Tầng đọc file/deserialize đã dịch escape chưa?
3. Giá trị có chứa literal backslash vì một đường dẫn, regex hay mã nguồn được nhúng không?
4. Dữ liệu có thể có escape không được hỗ trợ như `\uXXXX`, `\x41` hoặc `\/` không?
5. Khi giải mã thất bại, ứng dụng cần từ chối toàn bộ input, báo vị trí lỗi hay dùng cơ chế fallback có kiểm soát?
6. Có nguy cơ dịch lần thứ hai ở tầng xử lý tiếp theo không?

Với dữ liệu nhận từ bên ngoài, không dùng phương thức này như “sửa lỗi văn bản tự động”; thay đổi newline hoặc dấu cách có thể tác động đến log, chữ ký, mẫu email và dữ liệu cần bảo toàn nguyên văn.

### Câu chuyện JSON là một trường hợp điển hình

JSON cũng sử dụng nhiều escape trùng Java như `\n` và `\"`, nhưng có các quy tắc khác, đặc biệt là Unicode escape. Dù vài ví dụ đơn giản trông giống nhau, **`String.translateEscapes()` không phải JSON unescaper**. Nếu ứng dụng đã dùng parser JSON, hãy nhận String đã được parser giải mã. Nếu cần parse JSON mới, dùng thư viện JSON phù hợp thay vì giải mã thủ công bằng phương thức Java này.

## 13. Các sai lầm thường gặp

| Lỗi | Hậu quả | Cách sửa |
|---|---|---|
| Tưởng `"A\nB"` chứa backslash và chữ `n` | Nhầm độ dài, gọi dịch dư thừa | Hiểu compiler đã tạo LF trong literal |
| Muốn tạo chuỗi runtime có `\n` nhưng viết `"\n"` | Dữ liệu đã là LF | Viết `"\\n"` khi cần chính biểu diễn escape |
| Bỏ kết quả trả về từ `translateEscapes()` | Chuỗi cũ không đổi | Gán kết quả vào biến mới/biến đích |
| Gọi giải mã nhiều lần | Một `\\\\n` có thể thành newline sau hai lượt | Theo dõi encoded/decoded, dịch đúng một lần theo hợp đồng |
| Tưởng `\u0041` được dịch thành `A` | Gặp `IllegalArgumentException` | Dùng parser định dạng có hỗ trợ Unicode escape |
| Dùng `\q`, `\x41` hoặc `\z` | Escape không hợp lệ | Xác thực input và xử lý ngoại lệ |
| Có backslash đơn ở cuối String | Escape bị thiếu ký tự theo sau | Yêu cầu nguồn escape đầy đủ, ví dụ `\\` để biểu diễn backslash |
| Hiểu `\s` như regex whitespace | Biến nghĩa dữ liệu | Nhớ `\s` ở đây là một space U+0020 |
| Dùng phương thức để parse JSON | Không hỗ trợ đầy đủ escape JSON | Dùng JSON parser |
| Dùng logic tự tạo để parse Unicode/JSON | Có thể sai với cặp surrogate hoặc backslash nhiều lớp | Dùng parser đúng định dạng |
| In trực tiếp TAB/LF rồi đếm bằng mắt | Rất khó kiểm chứng ký tự thật | Sử dụng `length()`, `charAt()` hoặc `visible` |
| Cho rằng `\n` tự chuyển thành line ending OS | Không đúng; LF là U+000A | Chuyển đổi có chủ đích nếu cần CRLF |
| Áp dụng cho mọi dữ liệu người dùng | Có thể làm đổi log/cấu trúc và phát sinh lỗi | Chỉ dịch theo quy định đầu vào, giới hạn và validate |

## 14. Bài tập tự kiểm tra

**Câu 1.** `String a = "\\n";` có độ dài bao nhiêu trước và sau `translateEscapes()`?

**Đáp án:** Trước là **2** (backslash + `n`); sau là **1** (LF).

**Câu 2.** Với `String b = "\n";`, có cần gọi `translateEscapes()` để tạo LF không?

**Đáp án:** Không. Java compiler đã diễn giải escape khi xây literal, nên `b` đã chứa LF.

**Câu 3.** `"\\101\\040\\102".translateEscapes()` trả nội dung gì?

**Đáp án:** `"A B"` vì octal `101`, `040`, `102` lần lượt tương đương `A`, space, `B`.

**Câu 4.** Vì sao `"\\q".translateEscapes()` bị lỗi?

**Đáp án:** `\q` không nằm trong tập Java escape hợp lệ, nên ném `IllegalArgumentException`.

**Câu 5.** Có thể dùng `translateEscapes()` để xử lý `\u0041` trong một String runtime không?

**Đáp án:** Không. Java Unicode escapes được compiler xử lý ở bước đọc source; phương thức này không dịch `\uXXXX`.

**Câu 6.** Với source `"\\\\n"`, tại sao một lượt dịch và hai lượt dịch có thể tạo kết quả khác nhau?

**Đáp án:** Ban đầu String chứa hai backslash và chữ n; lượt đầu biến hai backslash thành một, lượt sau mới biến backslash + n thành LF.

**Câu 7.** Nếu String runtime chứa backslash đứng ngay trước một LF **thật**, `translateEscapes()` sẽ làm gì?

**Đáp án:** Bỏ backslash và LF như một continuation. Nếu thay LF thật bằng chữ n thì nó sẽ tạo LF, chứ không bỏ.

**Câu 8.** Một framework config đã giải mã escape trước khi giao String cho chương trình. Có nên gọi thêm `translateEscapes()` không?

**Đáp án:** Không, trừ khi một tầng biểu diễn escape bổ sung được định nghĩa rõ ràng. Gọi dư có thể đổi các backslash cần được giữ nguyên.

## 15. Tài liệu tham khảo chính thức

- [Java SE 17 API — String.translateEscapes()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html#translateEscapes()): escape được hỗ trợ, ngoại lệ `IllegalArgumentException`, giới hạn Unicode, mục `Since: 15`.
- [Java Language Specification 17 — `3.10.7 Escape Sequences](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.10.7): cú pháp escape, octal và continuation.
- [Java Language Specification 17 — `3.3 Unicode Escapes](https://docs.oracle.com/javase/specs/jls/se17/html/jls-3.html#jls-3.3): Unicode escapes trong quá trình xử lý Java source.
- [Oracle Java 17 — Programmer’s Guide to Text Blocks](https://docs.oracle.com/en/java/javase/17/text-blocks/index.html): thứ tự xử lý escape/indentation, các phương thức hỗ trợ của String.
- [OpenJDK JEP 378 — Text Blocks](https://openjdk.org/jeps/378): text block và API liên quan trở thành tính năng ổn định từ Java 15.

**Ghi nhớ:** `String.translateEscapes()` giải mã **biểu diễn escape đã nằm trong String ở runtime**. Nó không thay thế bước compiler xử lý Java string literal, không xử lý `\uXXXX` và không phải bộ giải mã JSON/regex. Muốn dùng đúng, trước hết phải biết chuỗi đã decoded chưa, áp dụng đúng một tầng giải mã có chủ đích và kiểm tra lỗi dữ liệu rõ ràng.