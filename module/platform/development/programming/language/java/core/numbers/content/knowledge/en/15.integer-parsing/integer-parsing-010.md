# Kiểm tra toàn bộ đầu vào và chính sách xử lý khoảng trắng khi parse số nguyên trong Java

Một chuỗi nhìn giống số không nhất thiết là **đầu vào số nguyên hợp lệ**. Ví dụ `"42"`, `" 42 "`, `"42abc"`, `"4 2"` hay `"１２３"` có thể được xử lý khác nhau tùy parser, bộ ký tự hợp lệ và **chính sách xử lý khoảng trắng**. Khi dữ liệu đến từ người dùng, file cấu hình hoặc giao thức, cần trả lời hai câu hỏi trước khi gọi `parseInt` hoặc `parseLong`:

1. **Parser có kiểm tra hết chuỗi không?** Hay chỉ lấy một tiền tố giống số rồi bỏ qua phần đuôi?
2. **Chuỗi được phép chứa những khoảng trắng nào, ở vị trí nào?** Từ chối mọi khoảng trắng, chỉ bỏ khoảng trắng ở hai đầu, hay chấp nhận dấu phân nhóm/định dạng theo locale?

Trong Java, **`Integer.parseInt` và `Long.parseLong` kiểm tra toàn bộ chuỗi số nguyên được truyền vào**. Chúng không tự bỏ khoảng trắng. Điều này tạo nền tảng tốt cho parser nghiêm ngặt, nhưng **chưa tự xác định toàn bộ chính sách nghiệp vụ**: chẳng hạn parser Java có thể nhận chữ số Unicode, còn giao thức bên ngoài chỉ cho phép ASCII.

```java
int a = Integer.parseInt("42");       // 42.
// int b = Integer.parseInt(" 42 ");  // NumberFormatException.
// int c = Integer.parseInt("42abc"); // NumberFormatException.
int d = Integer.parseInt(" 42 ".strip()); // 42: CHỦ ĐỘNG bỏ ngoài.
```

Đoạn mã trên là **mảnh minh họa** có thể đặt trong phương thức; hai dòng dẫn tới ngoại lệ đã được chú thích. Không nên coi việc `strip()` luôn là tốt: trong một số giao thức, việc có thêm dấu cách hoặc newline đã là lỗi dữ liệu và cần được phát hiện.

## 1. “Kiểm tra toàn bộ” có nghĩa là gì?

Giả sử ứng dụng nhận `"123abc"`. Có hai hành vi rất khác nhau:

- **Full-string parsing:** chỉ chấp nhận khi **toàn bộ phần đầu vào được chỉ định** phù hợp cú pháp số nguyên, không dư ký tự. Chuỗi `"123abc"` bị từ chối.
- **Prefix parsing:** chấp nhận tiền tố `"123"`, trả giá trị 123 và dừng trước `a`, có thể bỏ qua phần `"abc"` nếu bên gọi không kiểm tra vị trí dừng.

Các phương thức `Integer.parseInt(String)`, `Long.parseLong(String)`, `Byte.parseByte(String)`, `Short.parseShort(String)` và phiên bản có radix dùng quy tắc **đầu vào số nguyên phải được parse hết**. Ví dụ:

```java
int value = Integer.parseInt("123"); // 123.
// Integer.parseInt("123abc");      // Ném NumberFormatException.
// Long.parseLong("123.0");         // Ném NumberFormatException.
```

Cú pháp `parseInt` có dấu `+` hoặc `-` đầu chuỗi, tiếp theo là các chữ số được chấp nhận trong cơ số; ký tự lạ, dấu thập phân, phần hậu tố hay ký tự thừa sẽ làm parser thất bại. **Giới hạn phạm vi** cũng được kiểm tra: `Integer.parseInt("2147483648")` ném `NumberFormatException` dù chuỗi chỉ có các chữ số thập phân.

**Phân biệt phạm vi kiểm tra:** `Integer.parseInt(CharSequence s, int begin, int end, int radix)` chỉ kiểm tra **toàn bộ đoạn `[begin,end)` đã chỉ định**, chứ không tự kiểm tra các ký tự ngoài đoạn. Nếu chỉ định đoạn `"123"` trong chuỗi `"123abc"`, gọi đó là “parse hết chuỗi nguồn” sẽ sai. Khi sử dụng parser theo slice, trách nhiệm bảo đảm slice đúng boundaries thuộc về bên gọi.

## 2. Ba chính sách xử lý khoảng trắng thường gặp

| Chính sách | Ví dụ chấp nhận | Ví dụ từ chối | Khi nào hợp lý |
| --- | --- | --- | --- |
| **STRICT**: không chuẩn hóa | `"42"`, `"-42"` | `" 42"`, `"42\n"` | File machine-readable hoặc protocol yêu cầu cú pháp chính xác |
| **OUTER-STRIP**: bỏ khoảng trắng ngoài | `" 42 "`, `"\t-42\n"` | `"4 2"` | Dữ liệu từ form/CLI cho phép người dùng thừa dấu cách hai đầu |
| **LOCALE-AWARE**: theo quy tắc văn hóa | Ví dụ `"1,234"` trong US locale | Tùy locale và cấu hình | Chuỗi được người dùng nhập theo ngôn ngữ/vùng và có phân nhóm số |

**Không tự động gộp các chính sách.** Nếu hệ thống cần kiểm soát byte-level hoặc tuân thủ schema, một giá trị `"42\n"` có thể phải bị từ chối để phát hiện lỗi đóng gói. Nếu ứng dụng yêu cầu thân thiện với người dùng, bỏ khoảng trắng ngoài có thể phù hợp, nhưng phải được ghi rõ trong hợp đồng nhập liệu.

Chính sách OUTER-STRIP không có nghĩa loại mọi khoảng trắng:

```java
" 42 ".strip().equals("42"); // true
"4 2".strip().equals("42");  // false: khoảng trắng giữa vẫn còn
```

Trong `String`, `strip`, `stripLeading`, `stripTrailing` **chỉ tác động biên**, không tự xóa hoặc nối các ký tự ở giữa. Dùng `replaceAll("\\s+", "")` một cách vô điều kiện có thể biến dữ liệu `"4 2"` thành `"42"` và che khuất input sai — không nên làm trừ khi schema thật sự yêu cầu xóa separator.

## 3. `parseInt` và `parseLong` không bỏ khoảng trắng

```java
int a = Integer.parseInt("42"); // 42.
// Integer.parseInt(" 42");     // NumberFormatException.
// Integer.parseInt("42 ");     // NumberFormatException.
// Integer.parseInt("\t42");   // NumberFormatException.
```

Bản thân `parseInt` không hiểu ký tự space/tab/newline như thành phần hợp lệ của một chữ số. Dấu `+` hoặc `-` được chấp nhận ở **đầu phần chuỗi số** (`"+42"`, `"-42"`), không có khoảng trắng chen giữa dấu và chữ số:

```java
int positive = Integer.parseInt("+42"); // 42.
// Integer.parseInt("+ 42");             // NumberFormatException.
// Integer.parseInt("4 2");              // NumberFormatException.
```

Nếu dữ liệu cho phép khoảng trắng hai đầu, gọi `strip()` **trước** khi parse:

```java
String raw = "  -42\t";
int n = Integer.parseInt(raw.strip()); // -42
```

Nhưng cần phân biệt **đã chuẩn hóa chuỗi rồi parse hết** với **parse hết dữ liệu thô**. Sau `strip`, một số ký tự của dữ liệu gốc đã cố ý bị bỏ qua; đừng dùng câu “parser kiểm tra mọi ký tự gốc” nếu bạn đã chọn phép chuẩn hóa đầu vào.

## 4. `trim()` khác `strip()` ra sao?

Trong Java 17:

- **`String.trim()`** loại các ký tự có mã `<= U+0020` ở đầu/cuối. Đây là quy tắc lịch sử dựa trên code unit, không phải toàn bộ Unicode whitespace.
- **`String.strip()`** (Java 11+) dựa vào `Character.isWhitespace` theo Unicode/Java, xử lý được nhiều dấu cách không phải ASCII, ví dụ **EM SPACE U+2003**.
- **`stripLeading()`** và **`stripTrailing()`** chỉ bỏ một phía theo cùng quy tắc `isWhitespace`.
- **`isBlank()`** giúp biết chuỗi rỗng hoặc chỉ có các code point được coi là whitespace bởi `Character.isWhitespace`, chứ không kiểm tra nó có phải số hợp lệ.

Ví dụ cụ thể:

```java
String surrounded = "\u200342\u2003"; // EM SPACE ở hai đầu.
String trimmed = surrounded.trim();    // Vẫn còn EM SPACE.
String stripped = surrounded.strip();  // "42".
int number = Integer.parseInt(stripped); // 42.
```

`strip` **không đồng nghĩa loại toàn bộ ký tự Unicode nhìn giống khoảng trắng**. Chẳng hạn `NO-BREAK SPACE U+00A0` không được `Character.isWhitespace` coi là whitespace. Vì thế:

```java
String nbsp = "\u00A042\u00A0";
boolean unchanged = nbsp.strip().equals(nbsp); // true.
```

Đừng mặc định `strip()` “làm sạch mọi dấu cách”. Nếu dữ liệu có thể chứa NBSP, NARROW NO-BREAK SPACE hoặc ký tự vô hình khác, hãy **quyết định có cho phép chúng hay không**, xác thực theo danh sách ký tự hoặc quy tắc mã hóa được thiết kế cụ thể. Dùng normalize tùy tiện có thể làm hai chuỗi vốn khác nhau trở nên giống nhau, phá vỡ hợp đồng định dạng.

## 5. Kiểm tra toàn bộ chuỗi bằng regex ASCII trước khi parse

Nếu giao thức yêu cầu số thập phân **chỉ gồm chữ số ASCII**, một mẫu đơn giản là:

```regex
[+-]?[0-9]+
```

- `[+-]?`: cho phép tối đa một dấu cộng hoặc trừ đầu chuỗi (nếu schema cho phép).
- `[0-9]+`: yêu cầu ít nhất một chữ số ASCII.
- Gọi **`Matcher.matches()`**, không phải `find()`, để yêu cầu *toàn bộ chuỗi* khớp mẫu.

Ví dụ phương thức trong một lớp Java:

```java
private static final java.util.regex.Pattern ASCII_INTEGER =
        java.util.regex.Pattern.compile("[+-]?[0-9]+");

static int parseAsciiStrict(String text) {
    java.util.Objects.requireNonNull(text, "text");
    if (!ASCII_INTEGER.matcher(text).matches()) {
        throw new IllegalArgumentException("Invalid ASCII integer");
    }
    return Integer.parseInt(text); // Vẫn cần kiểm tra phạm vi int.
}
```

Đây là **hai thành phần khai báo ở cấp lớp**, không phải một file chạy độc lập. Regex bảo đảm **đúng cú pháp ASCII**, còn `Integer.parseInt` bảo đảm **đúng miền signed int**. `"2147483648"` khớp regex nhưng bị từ chối khi parse vì vượt phạm vi.

Dùng `[0-9]` nếu bạn thật sự muốn ASCII. Một số cú pháp regex như `\\d` có ngữ nghĩa chịu ảnh hưởng cờ và chế độ Unicode của regex engine; ghi trực tiếp `[0-9]` thường rõ hơn cho protocol ASCII.

Với parser strict không cho phép dấu `+` hoặc `-`, đổi mẫu thành `[0-9]+` và kiểm tra giá trị không âm nếu cần. Đối với schema cho số âm nhưng **không cho `+`**, dùng `-?[0-9]+`. Với mục tiêu canonical (ví dụ không cho phép `"0007"`), phải thêm quy tắc kiểm tra riêng; regex trên **cho phép số 0 đầu**.

## 6. Parser từ chối mọi whitespace và parser chấp nhận whitespace ngoài

Có thể hiện thực hai chính sách bằng cách tách lớp kiểm tra và bước chuẩn hóa:

```java
static int parseAsciiWithOuterWhitespace(String text) {
    java.util.Objects.requireNonNull(text, "text");
    return parseAsciiStrict(text.strip());
}
```

Lưu ý đây là **phương thức trong cùng lớp** có `parseAsciiStrict` đã định nghĩa. Nó chấp nhận `" 42 "` hay `"\t-42\n"`, nhưng từ chối `"4 2"` và `"4\n2"`: `strip` không xóa ký tự nội bộ.

Một ví dụ chuẩn hóa có chủ đích:

```text
Input raw:       "  -42  "
Policy:          allow Unicode whitespace at both ends via strip()
Normalized:      "-42"
ASCII grammar:   [+-]?[0-9]+   → pass
Integer range:   -2^31..2^31-1 → pass
Parsed int:      -42
```

**Vị trí kiểm tra rất quan trọng.** Nếu bạn kiểm tra regex trước `strip()`, input có khoảng trắng ngoài sẽ bị từ chối. Nếu bạn `strip()` trước, input đó được chấp nhận đúng như policy. Hai thứ tự không tương đương, nên lựa chọn phải được ghi rõ trong tài liệu API.

## 7. Unicode digits: `parseInt` không đồng nghĩa ASCII-only

Java có thể xem nhiều ký tự chữ số Unicode là chữ số hợp lệ dựa trên `Character.digit`, dù chúng không phải `'0'` đến `'9'` ASCII. Ví dụ:

```java
int value = Integer.parseInt("１２３"); // 123.
```

`"１２３"` ở đây chứa **FULLWIDTH DIGIT ONE/TWO/THREE**, được Java 17 parse thành 123. Nếu hệ thống có quy tắc ASCII-only (ví dụ một trường dữ liệu kỹ thuật yêu cầu các byte `0x30`–`0x39`), thì **chỉ gọi `parseInt` không đủ để xác thực hợp đồng**.

Sử dụng `[0-9]` với `matches()` như ví dụ phía trên để từ chối các chữ số không phải ASCII. Ngược lại, trong ứng dụng quốc tế hóa, bạn có thể cố ý chấp nhận chữ số Unicode — khi đó nên giải thích rõ miền ký tự chấp nhận và kiểm thử từng loại đầu vào.

Không được đánh đồng **Unicode whitespace** với **Unicode digits**: `strip()` xử lý một số ký tự ở ngoài, còn `parseInt` xử lý chữ số bên trong; chúng là hai quy tắc độc lập.

## 8. Sự nguy hiểm của parser chỉ đọc tiền tố: `NumberFormat`

Các parser số theo locale có thể chấp nhận đầu vào **chỉ một phần**. Ví dụ với `java.text.NumberFormat` và `ParsePosition`:

```java
String text = "123abc";
java.text.ParsePosition pos = new java.text.ParsePosition(0);
Number n = java.text.NumberFormat
        .getIntegerInstance(java.util.Locale.US)
        .parse(text, pos);
// n = 123; pos.getIndex() = 3; "abc" chưa được tiêu thụ.
```

`NumberFormat` hữu ích khi xử lý biểu diễn số theo locale (dấu phân nhóm, ký hiệu địa phương), nhưng **không mặc định là bộ kiểm tra toàn bộ input cho một giao thức chặt chẽ**.

Nếu cố ý dùng `ParsePosition`, cần kiểm tra cả:

```java
boolean parsedSomething = n != null;
boolean consumedAll = parsedSomething && pos.getIndex() == text.length();
```

Nếu `pos.getIndex()` nhỏ hơn `text.length()`, còn ký tự chưa được dùng. Khi định nghĩa một **số nguyên** theo locale, còn cần xem xét cách parser xử lý dấu thập phân, dấu phân nhóm, phép làm tròn và giới hạn kiểu trả về. `getIntegerInstance` không có nghĩa parser tự bảo đảm signed `int` 32 bit và không thay thế `Integer.parseInt`.

**Nhớ rằng:** `String.matches` hay `Matcher.matches()` kiểm tra toàn chuỗi; `Matcher.find()`, `NumberFormat.parse` hay một regex `find` có thể chỉ tìm **một phần**. Đừng dùng kết quả “đã đọc được số 123” như bằng chứng “chuỗi gốc đúng toàn bộ”.

## 9. `parseInt(CharSequence, begin, end, radix)`: đúng đoạn, không đúng cả nguồn

Từ các bản Java hiện đại (bao gồm Java 17), bạn có thể parse một phần `CharSequence`:

```java
CharSequence message = new StringBuilder("id=42;tail");
int result = Integer.parseInt(message, 3, 5, 10); // 42.
```

`beginIndex` (3) là vị trí bắt đầu **inclusive**, `endIndex` (5) là vị trí kết thúc **exclusive**. Nó tiêu thụ `"42"` đúng đoạn và không đòi hỏi `";tail"` phải là số. Đây là hành vi **có chủ đích để parse field con**, không phải lỗi của API.

Nếu nguồn dự kiến **chỉ có một trường số nguyên**, hãy dùng overload nhận toàn chuỗi và/hoặc tự kiểm tra delimiter/độ dài ngoài slice. Nếu một bản ghi gồm nhiều trường, việc parse đúng slice chưa đủ: cần **parser của toàn bản ghi** xác minh prefix, separator, số trường, vị trí end và phần dư.

Đây là điểm khác biệt giữa **full-field validation** và **full-record validation**. Một field có thể đúng cú pháp số mà bản ghi chứa nó vẫn không đúng schema.

## 10. Bảng các loại khoảng trắng và ký tự dễ nhầm

| Ký tự/chuỗi ví dụ | `trim()` ở biên | `strip()` ở biên | `parseInt` trực tiếp | Lưu ý |
| --- | --- | --- | --- | --- |
| `" 42 "` (SPACE U+0020) | Bỏ | Bỏ | Lỗi | Khoảng trắng ASCII thông dụng |
| `"\t42\n"` (TAB/LF) | Bỏ | Bỏ | Lỗi | Newline ngoài có thể là lỗi framing |
| `"\u200342\u2003"` (EM SPACE) | Không bỏ | Bỏ | Lỗi | Unicode `Character.isWhitespace` nhận |
| `"\u00A042\u00A0"` (NBSP) | Không bỏ | Không bỏ | Lỗi | Không phải whitespace theo `isWhitespace` |
| `"4 2"` | Không thay phần giữa | Không thay phần giữa | Lỗi | Không tự nối thành 42 |
| `"42abc"` | Không | Không | Lỗi | Dư ký tự; parser full-string từ chối |
| `"42\u200B"` (ZERO WIDTH SPACE) | Không bỏ | Không bỏ | Lỗi | Ký tự vô hình không thuộc chính sách mặc định |
| `"１２３"` (full-width digits) | Không liên quan | Không liên quan | **123** | Nếu ASCII-only, phải kiểm tra riêng |
| `"0007"` | Không liên quan | Không liên quan | **7** | Parse mất biểu diễn chuỗi gốc có số 0 đầu |

Bảng mô tả **Java 17** theo các ký tự được chỉ rõ. Với dữ liệu Unicode, nên kiểm tra **code point** của chuỗi khi debug thay vì tin vào biểu diễn nhìn bằng mắt; nhiều ký tự trông giống space hoặc chữ số ASCII nhưng có mã khác.

## 11. Chương trình Java 17+ có thể chạy độc lập

Lưu file **`CompleteIntegerInputDemo.java`**:

```java
import java.text.NumberFormat;
import java.text.ParsePosition;
import java.util.Locale;
import java.util.Objects;
import java.util.regex.Pattern;

public class CompleteIntegerInputDemo {
    private static final Pattern ASCII_INTEGER =
            Pattern.compile("[+-]?[0-9]+");

    static int parseAsciiStrict(String text) {
        Objects.requireNonNull(text, "text");
        if (!ASCII_INTEGER.matcher(text).matches()) {
            throw new IllegalArgumentException("Invalid ASCII integer");
        }
        return Integer.parseInt(text);
    }

    static int parseAsciiWithOuterWhitespace(String text) {
        Objects.requireNonNull(text, "text");
        return parseAsciiStrict(text.strip());
    }

    static String errorName(Runnable call) {
        try {
            call.run();
            return "OK";
        } catch (RuntimeException ex) {
            return ex.getClass().getSimpleName();
        }
    }

    public static void main(String[] args) {
        System.out.println("parsePlus=" + Integer.parseInt("+42"));
        System.out.println("parseFullLength=" + Integer.parseInt("123"));
        System.out.println("strictPlus=" + parseAsciiStrict("+42"));
        System.out.println("outerStrictError="
                + errorName(() -> parseAsciiStrict(" 42 ")));
        System.out.println("outerAccepted=" + parseAsciiWithOuterWhitespace(" 42 "));
        System.out.println("outerTabsAccepted="
                + parseAsciiWithOuterWhitespace("\t-42\n"));
        System.out.println("internalWhitespaceError="
                + errorName(() -> parseAsciiWithOuterWhitespace("4 2")));
        System.out.println("newlineInsideError="
                + errorName(() -> parseAsciiWithOuterWhitespace("4\n2")));

        String emSpaces = "\u200342\u2003";
        System.out.println("unicodeStripAccepted="
                + parseAsciiWithOuterWhitespace(emSpaces));
        System.out.println("unicodeTrimUnchanged="
                + emSpaces.trim().equals(emSpaces));

        String nbsp = "\u00A042\u00A0";
        System.out.println("nbspStripUnchanged="
                + nbsp.strip().equals(nbsp));
        System.out.println("nbspRejected="
                + errorName(() -> parseAsciiWithOuterWhitespace(nbsp)));

        System.out.println("parseUnicodeDigits="
                + Integer.parseInt("１２３"));
        System.out.println("asciiUnicodeDigitsError="
                + errorName(() -> parseAsciiStrict("１２３")));
        System.out.println("unicodeDigitsWithStrip="
                + Integer.parseInt(" \u2003１２３\u2003 ".strip()));

        System.out.println("intOverflowError="
                + errorName(() -> parseAsciiStrict("2147483648")));
        System.out.println("longMax="
                + Long.parseLong("9223372036854775807"));
        System.out.println("longOverflowError="
                + errorName(() -> Long.parseLong("9223372036854775808")));
        System.out.println("emptyError="
                + errorName(() -> parseAsciiStrict("")));
        System.out.println("spacesOnlyError="
                + errorName(() -> parseAsciiWithOuterWhitespace(" \t ")));
        System.out.println("plusOnlyError="
                + errorName(() -> parseAsciiStrict("+")));
        System.out.println("nullError="
                + errorName(() -> parseAsciiStrict(null)));
        System.out.println("underscoreError="
                + errorName(() -> parseAsciiStrict("1_000")));
        System.out.println("prefixError="
                + errorName(() -> parseAsciiStrict("0x10")));

        String whole = "123abc";
        ParsePosition pos = new ParsePosition(0);
        Number parsed = NumberFormat.getIntegerInstance(Locale.US)
                .parse(whole, pos);
        System.out.println("localeParsedPrefix=" + parsed);
        System.out.println("localeConsumed=" + pos.getIndex());
        System.out.println("localeFullConsumed="
                + (pos.getIndex() == whole.length()));
        System.out.println("leadingZeroValue=" + parseAsciiStrict("0007"));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 CompleteIntegerInputDemo.java
java CompleteIntegerInputDemo
```

Kết quả stdout chính xác (đã kiểm chứng):

```text
parsePlus=42
parseFullLength=123
strictPlus=42
outerStrictError=IllegalArgumentException
outerAccepted=42
outerTabsAccepted=-42
internalWhitespaceError=IllegalArgumentException
newlineInsideError=IllegalArgumentException
unicodeStripAccepted=42
unicodeTrimUnchanged=true
nbspStripUnchanged=true
nbspRejected=IllegalArgumentException
parseUnicodeDigits=123
asciiUnicodeDigitsError=IllegalArgumentException
unicodeDigitsWithStrip=123
intOverflowError=NumberFormatException
longMax=9223372036854775807
longOverflowError=NumberFormatException
emptyError=IllegalArgumentException
spacesOnlyError=IllegalArgumentException
plusOnlyError=IllegalArgumentException
nullError=NullPointerException
underscoreError=IllegalArgumentException
prefixError=IllegalArgumentException
localeParsedPrefix=123
localeConsumed=3
localeFullConsumed=false
leadingZeroValue=7
```

Các nhóm kết quả minh họa:

- `strictPlus`, `outerStrictError`, `outerAccepted` và `outerTabsAccepted`: xác định chính sách STRICT hoặc OUTER-STRIP một cách tường minh.
- `internalWhitespaceError`, `newlineInsideError`: bỏ khoảng trắng **ngoài** không xóa ký tự **bên trong**.
- `unicodeStripAccepted` với `unicodeTrimUnchanged`: `strip` loại được EM SPACE ở biên, còn `trim` không.
- `nbspStripUnchanged`, `nbspRejected`: NBSP không được `strip` loại bỏ, nên không trở thành đầu vào số hợp lệ trong policy này.
- `parseUnicodeDigits=123` so với `asciiUnicodeDigitsError`: `Integer.parseInt` chấp nhận chữ số full-width, nhưng regex `[0-9]` từ chối chúng.
- `intOverflowError`, `longOverflowError`: cú pháp chữ số có thể đúng nhưng giá trị vượt **dải kiểu đích**.
- `emptyError`, `spacesOnlyError`, `plusOnlyError`, `nullError`: cần xử lý dữ liệu rỗng, chỉ có dấu, chỉ có khoảng trắng và `null` riêng biệt.
- `localeParsedPrefix=123`, `localeConsumed=3`, `localeFullConsumed=false`: parser theo locale chỉ đọc **tiền tố** của `"123abc"`; bắt buộc kiểm tra vị trí tiêu thụ nếu chính sách yêu cầu cả chuỗi.
- `leadingZeroValue=7`: parse số nguyên thành công nhưng **không giữ số 0 đầu của chuỗi**.

Hàm `errorName` của chương trình cố ý bắt `RuntimeException` để **in tên ngoại lệ cho demo**, không phải mẫu thiết kế xử lý lỗi cho sản phẩm. Trong ứng dụng thật, bắt ngoại lệ ở mức chính xác như `NumberFormatException` hoặc ngoại lệ do validator của bạn quy định, không âm thầm gom mọi lỗi runtime thành “input sai”.

## 12. Tách lỗi cú pháp, lỗi dải và lỗi nghiệp vụ

Trong một parser nghiêm ngặt, ít nhất cần phân biệt ba mức:

1. **Cú pháp**: ký tự lạ, khoảng trắng sai chính sách, dấu không hợp lệ, số rỗng. Ví dụ `"4 2"`, `"0x10"` (nếu chỉ cho decimal).
2. **Dải kiểu**: chữ số hợp lệ nhưng ngoài signed int/long. Ví dụ `"2147483648"` với `Integer.parseInt`.
3. **Giới hạn nghiệp vụ**: một `int` parse thành công nhưng sai quy tắc. Ví dụ số tuổi 200, số lượng âm, kích thước file vượt quota.

Trong code mẫu, `parseAsciiStrict` ném `IllegalArgumentException` với lỗi **cú pháp regex**, còn `Integer.parseInt` có thể ném `NumberFormatException` nếu **ngoài dải**. Vì `NumberFormatException` là lớp con của `IllegalArgumentException`, người gọi bắt `IllegalArgumentException` chung sẽ làm mất phân biệt giữa hai nguồn lỗi nếu không có quy ước khác.

Một kiến trúc sạch hơn cho API công khai là trả về một kiểu kết quả có mã lỗi hoặc ném ngoại lệ được tài liệu hóa. Ví dụ:

```text
ParseResult:
- OK(value)
- MISSING
- INVALID_SYNTAX
- OUT_OF_RANGE
- DOMAIN_VIOLATION
```

Đây là **mô hình kết quả**, không phải API có sẵn của JDK. Có thể hiện thực bằng enum + record/sealed interface hoặc bằng exception class của ứng dụng nếu cần phân biệt lỗi rõ ràng. Không đưa thông báo nội bộ như stack trace hoặc toàn bộ dữ liệu đầu vào nhạy cảm thẳng tới log công khai.

## 13. `null`, chuỗi trống và chính sách dữ liệu thiếu

Không nên đánh đồng các tình huống:

| Dữ liệu | Gợi ý phân loại |
| --- | --- |
| `null` | Thiếu input hoặc vi phạm hợp đồng không-null |
| `""` | Có chuỗi nhưng rỗng |
| `" "` | Chỉ có khoảng trắng (policy-dependent) |
| `"0"` | Số 0 hợp lệ |
| `"-0"` | Parser signed int trả 0, chuỗi biểu diễn khác |
| `"+" ` | Có dấu nhưng không có chữ số |
| `"0000"` | Số 0 hợp lệ nếu cho phép số 0 đầu |

`Objects.requireNonNull` có thể dùng khi API đòi hỏi đầu vào không-null; khi đó **`NullPointerException`** là tín hiệu vi phạm hợp đồng. Nếu `null` là dữ liệu thiếu hợp lệ của form/API, nên kiểm tra và trả kết quả `MISSING` thay vì để phương thức khác vô tình ném NPE.

`String.isBlank()` có ích để phát hiện chuỗi rỗng/toàn whitespace theo `Character.isWhitespace`, nhưng **`"0"` không blank** và **NBSP không được `isWhitespace` coi là whitespace**. Không thay `isBlank` bằng `parseInt` hay ngược lại: chúng giải quyết hai câu hỏi khác nhau.

## 14. Không tự xóa dấu phân nhóm, dấu chấm và các ký tự nội bộ

Các chuỗi như `"1,000"`, `"1.000"` hoặc `"1 000"` có ý nghĩa rất khác nhau theo locale: dấu phẩy có thể phân tách nghìn hoặc thập phân; dấu chấm tương tự. Nếu dữ liệu là giao thức máy đọc với schema decimal ASCII, cách an toàn là **từ chối** tất cả separator không được cho phép.

Nếu giao diện người dùng cần locale-aware parsing, hãy chọn **`Locale` cụ thể** và sử dụng bộ parser định dạng phù hợp, sau đó kiểm tra parser đã đọc **toàn bộ input**, kiểm tra kiểu/dải kết quả, và bảo đảm quy tắc thập phân/nhóm số đúng ý định.

Ví dụ nguy hiểm:

```java
// Không nên bỏ dấu phân nhóm mù quáng:
String raw = "1,5";
// raw.replace(",", "") thành "15" nhưng người dùng có thể định nhập 1.5.
```

Việc `replaceAll("[ ,._]", "")` trên mọi ký tự có thể làm hỏng nghĩa số, vượt qua kiểm tra schema hoặc che giấu dữ liệu sai. Chỉ chuẩn hóa **đúng những ký tự** mà hợp đồng rõ ràng cho phép.

## 15. Giới hạn độ dài và an toàn với input không tin cậy

Một chuỗi có thể gồm hàng triệu chữ số, dù mục tiêu chỉ là `int`. Parser sẽ báo vượt dải, nhưng vẫn có chi phí đọc/kiểm tra. Với endpoint công khai hoặc dữ liệu không tin cậy, nên:

- Đặt **giới hạn số byte/ký tự trước khi đọc hoặc nhận dữ liệu lớn** tùy giao thức và tầng truyền tải.
- Sau khi nhận `String`, kiểm tra `null`, tổng độ dài và chính sách whitespace, rồi mới regex/parse.
- Đặt giới hạn kích thước **phần đã chuẩn hóa** nếu schema quy định số chữ số tối đa. Đừng nhầm số lượng chữ số với tính đúng dải: chuỗi có nhiều số 0 đầu vẫn có thể parse thành số nhỏ.
- Tránh regex quá phức tạp dễ dẫn tới **catastrophic backtracking**. Mẫu `[+-]?[0-9]+` đơn giản và không có các nhóm lặp lồng nhau.
- Xác thực giá trị sau parse theo miền nghiệp vụ (âm/dương, giới hạn đếm, đơn vị đo, quota).
- Không log nguyên văn input không tin cậy nếu có thể chứa thông tin nhạy cảm hoặc ký tự điều khiển gây hỏng log.

Nếu schema yêu cầu chính xác `n` chữ số, hoặc cấm leading zero, hãy biểu diễn bằng validator riêng. Không suy rằng `Integer.parseInt` kiểm tra được những quy tắc định dạng đó.

## 16. Những lỗi triển khai phổ biến

| Lỗi | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Tin parser “đọc được 123” nghĩa `"123abc"` hợp lệ | Parser prefix có thể bỏ phần dư | Xác nhận `ParsePosition.getIndex() == input.length()` hoặc dùng full-string parser |
| Gọi `strip()` mặc định ở mọi API | Che lỗi khoảng trắng của giao thức strict | Chọn policy rõ: STRICT hoặc OUTER-STRIP |
| Nghĩ `strip()` loại mọi khoảng trắng | NBSP vẫn có thể tồn tại | Kiểm tra code point và policy Unicode |
| Dùng `trim()` khi mong hỗ trợ Unicode whitespace | EM SPACE ở đầu/cuối có thể còn lại | Dùng `strip()` khi đúng contract |
| Thay mọi `" "` trong chuỗi | Biến `"4 2"` thành `"42"` | Chỉ bỏ khoảng trắng ngoài khi được cho phép |
| Gọi `Matcher.find()` thay cho `matches()` | Một phần chuỗi hợp lệ đủ để pass | Dùng `matches()` để kiểm tra toàn bộ |
| Dùng `parseInt` làm validator ASCII-only | Chữ số Unicode có thể được chấp nhận | Regex ASCII `[0-9]` hoặc kiểm tra code point |
| Chỉ regex rồi nhận `"2147483648"` như `int` | Cú pháp đúng nhưng vượt dải 32 bit | Gọi `Integer.parseInt` để kiểm tra dải |
| Xem `null`, `""`, `"0"` như nhau | Mất phân biệt dữ liệu thiếu và 0 hợp lệ | Thiết kế kết quả parse có mã lỗi |
| Dùng locale của máy mặc định để parse giao thức | Kết quả thay đổi theo môi trường | Đặt locale theo schema hoặc dùng parser decimal ASCII |
| Chỉ kiểm tra field số trong một record | Record có thể còn ký tự hoặc trường không hợp lệ | Validate toàn bộ cấu trúc record và vị trí field |
| Cho phép chuỗi số bất kỳ quá dài | Tốn tài nguyên hoặc vượt quota | Đặt giới hạn input từ sớm |
| Parse mã định danh thành số nguyên | Mất số 0 đầu và ký tự định dạng | Giữ `String` cho identifier |

## 17. Bộ test tối thiểu cho hai chính sách

| Input | STRICT ASCII | OUTER-STRIP ASCII | Ghi chú |
| --- | --- | --- | --- |
| `"42"` | 42 | 42 | Giá trị đơn giản |
| `"+42"` | 42 | 42 | Nếu cho phép dấu `+` |
| `"-42"` | -42 | -42 | Nếu cho phép số âm |
| `" 42 "` | Lỗi | 42 | Phân biệt policy |
| `"\t42\n"` | Lỗi | 42 | Tab/newline ở ngoài |
| `"4 2"` | Lỗi | Lỗi | Khoảng trắng giữa |
| `"\u200342\u2003"` | Lỗi | 42 | EM SPACE được `strip` loại |
| `"\u00A042\u00A0"` | Lỗi | Lỗi | NBSP không được `strip` loại |
| `"１２３"` | Lỗi | Lỗi | ASCII-only từ chối full-width digits |
| `"0007"` | 7 | 7 | Nếu chưa cấm leading zeros |
| `"2147483647"` | 2147483647 | 2147483647 | Biên trên int |
| `"2147483648"` | Lỗi dải | Lỗi dải | Vượt biên trên |
| `"1_000"` | Lỗi | Lỗi | `_` không thuộc chuỗi số |
| `"0x10"` | Lỗi | Lỗi | Prefix hex ngoài cú pháp decimal |
| `""`, `" "`, `null` | Lỗi/thiếu | Lỗi/thiếu | Không được coi là số 0 |

Đối với `long`, thử cả `Long.MIN_VALUE`, `Long.MAX_VALUE` và hai chuỗi nằm ngay bên ngoài dải; với unsigned, thử `2^32-1` hoặc `2^64-1` tùy API. Nếu policy cho phép locale-specific grouping, thêm các test phân nhóm đúng/sai và dấu thập phân theo **locale đã khóa**, đồng thời kiểm tra tiêu thụ toàn bộ.

## 18. Câu hỏi tự kiểm tra

1. **`Integer.parseInt("123abc")` trả 123 hay báo lỗi?** Báo `NumberFormatException` vì chuỗi đầu vào không phải số nguyên hợp lệ toàn bộ.
2. **`Integer.parseInt(" 42 ")` có tự bỏ khoảng trắng không?** Không. Gọi `strip()` trước nếu hợp đồng cho phép.
3. **`" 42 ".strip()` và `"4 2".strip()` cho cùng kết quả không?** Không; `strip` chỉ loại khoảng trắng đầu/cuối, không loại khoảng trắng giữa.
4. **`trim()` và `strip()` khác nhau với EM SPACE U+2003 ra sao?** `trim` không bỏ, `strip` bỏ ở biên.
5. **`strip()` có bỏ NO-BREAK SPACE U+00A0 không?** Không, vì nó không được `Character.isWhitespace` nhận.
6. **Vì sao `Integer.parseInt("１２３")` có thể thành công?** Java dùng quy tắc nhận chữ số Unicode; nếu cần ASCII-only, phải kiểm tra riêng.
7. **Regex `[+-]?[0-9]+` đủ để bảo đảm kết quả vừa `int` không?** Không; cần `Integer.parseInt` để kiểm tra giới hạn kiểu.
8. **`NumberFormat` đọc được 123 từ `"123abc"` thì có nghĩa toàn chuỗi hợp lệ không?** Không; phải kiểm tra vị trí tiêu thụ của parser.
9. **`parseInt(CharSequence, 0, 3, 10)` kiểm tra phần sau chỉ số 3 không?** Không; nó chỉ parse đoạn được chỉ định.
10. **Có nên chuyển `"0007"` thành số 7 nếu đó là mã định danh?** Thường không; mã định danh cần giữ định dạng ban đầu, nên thường giữ dưới dạng chuỗi.

**Kết luận:** parsing số nguyên an toàn là sự phối hợp của **cú pháp toàn chuỗi**, **quy tắc khoảng trắng**, **bộ ký tự cho phép**, **giới hạn dải số** và **ràng buộc nghiệp vụ**. Java `parseInt`/`parseLong` tiêu thụ toàn bộ chuỗi số nguyên đã nhận nhưng không tự `strip`; các API theo locale có thể parse một tiền tố nếu không kiểm tra vị trí dừng. Hãy chọn STRICT hoặc OUTER-STRIP có chủ đích, xác thực ASCII/Unicode đúng đặc tả, và kiểm thử đủ các trường hợp dư ký tự, khoảng trắng, null, Unicode và overflow.
