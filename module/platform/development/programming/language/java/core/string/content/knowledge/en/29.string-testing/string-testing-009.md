# Phân biệt lỗi nội dung, lỗi chỉ số, lỗi regex và lỗi mã hóa khi xử lý String trong Java

Một lỗi liên quan đến chuỗi không nhất thiết là “Java xử lý sai ký tự”. Cùng triệu chứng *kết quả không như mong đợi* có thể xuất phát từ **nội dung thực tế khác nhau**, **truy cập sai vị trí**, **cú pháp biểu thức chính quy (regex)** hoặc **chuyển đổi byte và bảng mã**. Cách xử lý phải bắt đầu bằng việc xác định lớp lỗi; nếu chẩn đoán nhầm, cách sửa có thể che triệu chứng mà vẫn làm hỏng dữ liệu.

Bài học này tập trung vào `String` trong Java 17+: dấu hiệu nhận biết, ngoại lệ thường gặp, bước tái hiện, cách kiểm tra và cách sửa đúng cho bốn nhóm lỗi **nội dung – chỉ số – regex – mã hóa**. Các ví dụ được tách rõ thành đoạn minh họa và một chương trình Java độc lập có đầu ra xác định.

## 1. Bản đồ chẩn đoán nhanh

| Nhóm lỗi | Câu hỏi cần hỏi | Dấu hiệu tiêu biểu | Hướng kiểm tra |
| --- | --- | --- | --- |
| **Nội dung** | Hai chuỗi có **thực sự chứa cùng dữ liệu** không? | `equals` trả `false`; khoảng trắng/dấu Unicode khó thấy; `==` sai khi so nội dung; chuẩn hóa/hoa-thường khác nhau | In chuỗi ở trong dấu phân cách, kiểm tra `length`, code points, so sánh `equals`, quan sát Unicode |
| **Chỉ số** | Vị trí hoặc đoạn con có **nằm trong biên hợp lệ** không? | `StringIndexOutOfBoundsException`, lỗi lệch một đơn vị, cắt trúng surrogate | In `length`, `begin`/`end`, xác nhận chỉ số tính theo UTF-16 code units |
| **Regex** | Mẫu có đang bị hiểu là **cú pháp regex** không? | `PatternSyntaxException`; `split` chia quá nhiều; `replaceAll` thay ngoài ý muốn; lỗi `$`/`\` trong replacement | Tách rõ string literal, regex pattern, replacement; dùng `Pattern.quote` / `Matcher.quoteReplacement` khi cần |
| **Mã hóa** | Byte đã được **mã hóa và giải mã bằng cùng charset** chưa? | Chữ biến thành `�`, `?` hoặc mojibake (ví dụ `Ã©`); round-trip thất bại; byte hỏng | In hex của `byte[]`, ghi rõ `Charset`, dùng encoder/decoder ở chế độ `REPORT` |

**Ưu tiên kiểm tra:** xác định giá trị đầu vào và đầu ra thực tế; nếu có exception, đọc **loại ngoại lệ và vị trí phát sinh** trước khi đổi mã. Việc thấy ký tự `?` hoặc `�` không tự động cho biết lỗi ở phía gửi hay phía nhận: có thể dữ liệu đã bị thay thế trong một bước trước đó.

## 2. Nhận diện từng loại bằng một ca nhỏ có thể tái hiện

Nếu không có ngoại lệ nhưng kết quả sai, trước tiên **so nội dung thật và xác nhận API đang dùng**. Dưới đây là bốn tình huống có kết quả khác nhau dù đều liên quan đến `String`:

~~~java
// Nội dung: hai đối tượng khác nhau nhưng cùng chữ.
String a = "OK";
String b = new String("OK");
System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true

// Chỉ số: endIndex vượt length() = 3.
// "abc".substring(2, 4); // IndexOutOfBoundsException

// Regex: dấu chấm là wildcard; thay literal dùng replace.
System.out.println("a.b".replaceAll(".", "X")); // XXX
System.out.println("a.b".replace(".", "_"));    // a_b

// Mã hóa: bên gửi dùng UTF-8, bên đọc dùng charset khác.
byte[] bytes = "é".getBytes(java.nio.charset.StandardCharsets.UTF_8);
String wrong = new String(bytes, java.nio.charset.StandardCharsets.ISO_8859_1);
System.out.println("é".equals(wrong)); // false
~~~

- Với **nội dung**, xem `equals`, `length`, các code point và ký tự vô hình; `"e\u0301"` và `"\u00E9"` có thể giống mắt nhìn nhưng khác chuỗi, chỉ chuẩn hóa Unicode khi hợp đồng yêu cầu.
- Với **chỉ số**, kiểm tra `0 <= begin <= end <= length()` trước `substring(begin,end)`. `charAt(index)` yêu cầu `index < length()`; chỉ số là UTF-16, nên đừng cắt giữa surrogate pair nếu muốn giữ code point.
- Với **regex**, phân biệt `Pattern.compile`/`replaceAll`/`split` với thay thế literal `replace`. `Pattern.quote` bảo vệ văn bản trong pattern; `Matcher.quoteReplacement` bảo vệ văn bản trong replacement, đặc biệt khi chứa `$` hoặc backslash.
- Với **mã hóa**, kiểm tra byte gốc theo hex, charset tại hai đầu và quy tắc xử lý lỗi. `new String(bytes, UTF_8)` có thể thay byte sai bằng `U+FFFD`; nếu phải từ chối, dùng `CharsetDecoder` cấu hình `CodingErrorAction.REPORT`. Khi ký tự không biểu diễn được ở charset đích, dùng encoder `REPORT`.

Các kiểm thử chuyên biệt của từng nhóm ở các bài trước cho biết ma trận biên sâu hơn. Bài này dùng kết quả quan sát để **quyết định tiếp theo cần kiểm tra tầng nào**, tránh sửa lỗi nội dung bằng cách nuốt exception hoặc tự đổi charset.

## 3. Chương trình Java 17+ phân biệt bốn nhóm lỗi

Lưu nội dung dưới đây thành tệp `StringErrorKindsDemo.java`:

```java
import java.nio.ByteBuffer;
import java.nio.CharBuffer;
import java.nio.charset.CharacterCodingException;
import java.nio.charset.CodingErrorAction;
import java.nio.charset.StandardCharsets;
import java.text.Normalizer;
import java.util.HexFormat;
import java.util.regex.Pattern;
import java.util.regex.PatternSyntaxException;
import java.util.stream.Collectors;

public class StringErrorKindsDemo {
    public static void main(String[] args) {
        // 1. Nội dung: so tham chiếu và Unicode normalization.
        String same = new String("java");
        System.out.println("== same content: " + (same == "java"));
        System.out.println("equals: " + same.equals("java"));

        String composed = "\u00E9";
        String decomposed = "e\u0301";
        System.out.println("unicode equals: "
                + composed.equals(decomposed));
        System.out.println("unicode NFC equals: "
                + composed.equals(Normalizer.normalize(
                        decomposed, Normalizer.Form.NFC)));

        // 2. Chỉ số: ngoại lệ và UTF-16 code units.
        try {
            "abc".substring(2, 4);
        } catch (StringIndexOutOfBoundsException e) {
            System.out.println("index error: "
                    + e.getClass().getSimpleName());
        }

        String emoji = "A\uD83D\uDE00";
        System.out.println("UTF-16 units: " + emoji.length());
        System.out.println("code points: "
                + emoji.codePointCount(0, emoji.length()));
        System.out.println("high surrogate: "
                + Character.isHighSurrogate(emoji.charAt(1)));

        // 3. Regex: dấu chấm có nghĩa đặc biệt.
        String dotted = "a.b";
        System.out.println("regex dot: "
                + dotted.replaceAll(".", "X"));
        System.out.println("literal dot: "
                + dotted.replace(".", "_"));
        System.out.println("quoted regex: "
                + Pattern.compile(Pattern.quote("."))
                        .matcher(dotted).replaceAll("_"));

        try {
            Pattern.compile("[");
        } catch (PatternSyntaxException e) {
            System.out.println("invalid regex: "
                    + e.getClass().getSimpleName());
        }

        // 4. Mã hóa: sai charset, mất dữ liệu và decoder strict.
        byte[] utf8 = "\u00E9".getBytes(StandardCharsets.UTF_8);
        System.out.println("utf8 hex: "
                + HexFormat.of().formatHex(utf8));
        System.out.println("wrong decode equal: "
                + "\u00E9".equals(new String(
                        utf8, StandardCharsets.ISO_8859_1)));

        byte[] latin = "\u20AC".getBytes(
                StandardCharsets.ISO_8859_1);
        System.out.println("Latin-1 replacement hex: "
                + HexFormat.of().formatHex(latin));
        System.out.println("round trip euro: "
                + "\u20AC".equals(new String(
                        latin, StandardCharsets.ISO_8859_1)));

        try {
            StandardCharsets.ISO_8859_1.newEncoder()
                    .onUnmappableCharacter(CodingErrorAction.REPORT)
                    .encode(CharBuffer.wrap("\u20AC"));
        } catch (CharacterCodingException e) {
            System.out.println("strict encode: "
                    + e.getClass().getSimpleName());
        }

        byte[] invalidUtf8 = {(byte) 0xC3, (byte) 0x28};
        String lossy = new String(
                invalidUtf8, StandardCharsets.UTF_8);
        String codePoints = lossy.codePoints()
                .mapToObj(cp -> String.format("U+%04X", cp))
                .collect(Collectors.joining(" "));
        System.out.println("lossy decode code points: " + codePoints);

        try {
            StandardCharsets.UTF_8.newDecoder()
                    .onMalformedInput(CodingErrorAction.REPORT)
                    .decode(ByteBuffer.wrap(invalidUtf8));
        } catch (CharacterCodingException e) {
            System.out.println("strict decode: "
                    + e.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 StringErrorKindsDemo.java
java StringErrorKindsDemo
```

Đầu ra xác định của chương trình:

```text
== same content: false
equals: true
unicode equals: false
unicode NFC equals: true
index error: StringIndexOutOfBoundsException
UTF-16 units: 3
code points: 2
high surrogate: true
regex dot: XXX
literal dot: a_b
quoted regex: a_b
invalid regex: PatternSyntaxException
utf8 hex: c3a9
wrong decode equal: false
Latin-1 replacement hex: 3f
round trip euro: false
strict encode: UnmappableCharacterException
lossy decode code points: U+FFFD U+0028
strict decode: MalformedInputException
```

Các trường hợp đã kiểm tra:

- **Nội dung:** cùng chữ `java` nhưng tham chiếu khác; dạng Unicode composed/decomposed không bằng nhau cho đến khi chuẩn hóa NFC.
- **Chỉ số:** `substring(2, 4)` vượt quá độ dài `3` và phát sinh `StringIndexOutOfBoundsException`; emoji chiếm hai code units nhưng một code point.
- **Regex:** `.` khớp ba ký tự, còn `replace` hoặc `Pattern.quote` giữ nghĩa dấu chấm nguyên văn; mẫu `[` không hợp lệ.
- **Mã hóa:** `é` thành `c3a9` trong UTF-8; giải mã sai bằng Latin-1 không giữ nguyên chuỗi; dấu euro bị thay khi encode ISO-8859-1; strict encoder/decoder báo lỗi đúng loại.

Các giá trị trong ví dụ chứng minh **hành vi xác định** và nhóm nguyên nhân. Trong dự án thật, cần tái hiện trên dữ liệu và đường I/O đang gây lỗi.

## 4. Quy trình debug có thể áp dụng lặp lại

### Bước 1 — Thu nhỏ trường hợp lỗi

Giữ một ví dụ đầu vào ngắn nhất vẫn làm lỗi xuất hiện: `"a.b"` cho regex dấu chấm, `"abc"` với `charAt(3)` cho lỗi biên, `"é"` cho sai UTF-8/Latin-1. Thu nhỏ giúp phân biệt nguyên nhân mà không bị logic khác che khuất.

### Bước 2 — Phân loại theo kết quả hay ngoại lệ

- **Trả kết quả sai nhưng không ném ngoại lệ:** xét nội dung thật, dùng đúng API literal/regex hay không, charset đã đồng bộ chưa.
- **`StringIndexOutOfBoundsException`:** kiểm tra `length` và công thức `begin/end`, giá trị `-1` từ tìm kiếm, code point so với code unit.
- **`PatternSyntaxException`:** in mẫu regex (đã bảo vệ dữ liệu nhạy cảm) và xác minh escape, dấu ngoặc, quantifier; nếu pattern là văn bản nguyên vẹn thì dùng `Pattern.quote`.
- **`CharacterCodingException` khi encoder/decoder strict:** xác định byte hoặc code point không hợp lệ, charset và vị trí trong pipeline.
- **`NullPointerException`:** kiểm tra hợp đồng null của API và nguồn vào. Đây là tình huống cần kiểm tra riêng, không tự kết luận thuộc một trong bốn nhóm chính.

### Bước 3 — Quan sát dữ liệu đúng lớp

**Nếu lỗi nội dung:** quan sát độ dài, `equals`, code points, khoảng trắng. **Nếu lỗi chỉ số:** log `begin`, `end`, `length()` cùng điều kiện kiểm tra biên. **Nếu lỗi regex:** log pattern đã xử lý escape, phân biệt toàn chuỗi (`matches`) với tìm một đoạn (`find`), xem ý nghĩa của replacement. **Nếu lỗi encoding:** quan sát byte hex **trước** khi decode, charset nhận/cho và có bước chuyển mã nào ở giữa.

Để tái hiện và giải thích, có thể dùng các thao tác quan sát sau:

```java
// Chỉ là các ví dụ độc lập, giả sử các biến có sẵn.
System.out.println("length=" + input.length());
System.out.println("hex=" + HexFormat.of().formatHex(bytes));
System.out.println("index=" + index + ", end=" + end);
```

Khi code này đưa vào sản phẩm, cần tránh log dữ liệu nhạy cảm/secret; ghi nhận những thuộc tính tối thiểu cần cho việc chẩn đoán.

### Bước 4 — Đặt quy tắc mong muốn trước khi sửa

Quy tắc phải xác định dữ liệu nào hợp lệ: có bỏ khoảng trắng không? chấp nhận Unicode dạng composed/decomposed không? chỉ số tính theo code points hay code units? pattern có là regex do người dùng cấu hình hay chỉ chuỗi literal? chấp nhận dữ liệu lỗi bị thay thế hay buộc từ chối?

Khi đã rõ hợp đồng, lựa chọn sửa sẽ tương ứng: `equals`, xử lý normalized input, kiểm tra biên, `Pattern.quote`, `Matcher.quoteReplacement`, charset tường minh, strict decoder hoặc thông báo lỗi hợp lệ.

### Bước 5 — Viết kiểm thử cho trường hợp biên

Kiểm thử tối thiểu nên có:

| Nhóm | Trường hợp bình thường | Trường hợp biên / lỗi |
| --- | --- | --- |
| Nội dung | Hai chuỗi giống hệt và `equals` đúng | Thừa space, `null`, dấu kết hợp, khác locale/casing |
| Chỉ số | Lấy substring tại đoạn hợp lệ | Chuỗi rỗng, `begin=end`, `-1` từ `indexOf`, `end>length`, surrogate pair |
| Regex | Pattern đơn giản khớp | Dấu `.` nguyên văn, dấu `$` trong replacement, pattern `[` sai, chuỗi rỗng khi split |
| Encoding | UTF-8 round-trip với tiếng Việt | Charset không biểu diễn được ký tự, byte UTF-8 bị hỏng, decode khác charset, emoji |

Không cần tạo hệ thống test phức tạp chỉ để kiểm tra hành vi của JDK; giá trị thực sự là **kiểm tra hàm của ứng dụng phản ứng đúng khi đầu vào biến đổi**.

## 5. Các anti-pattern cần tránh

### Bắt ngoại lệ rồi tiếp tục với dữ liệu sai

```java
// Không nên dùng như cách sửa mọi lỗi chỉ số:
try {
    returnValue = input.substring(start, end);
} catch (IndexOutOfBoundsException e) {
    returnValue = "";
}
```

Đây là đoạn minh họa. Trả chuỗi rỗng có thể biến một lỗi lập trình thành dữ liệu hợp lệ giả. Tốt hơn: xác định contract cho `start/end`, validate trước khi gọi và báo lỗi rõ nghĩa nếu không hợp lệ.

### Ép tất cả chuỗi qua `replaceAll`

Nếu chỉ cần thay ký tự/đoạn nguyên văn, dùng `String.replace`. Dùng regex khi thực sự cần ngôn ngữ pattern, và kiểm soát pattern + replacement theo hai quy tắc escape khác nhau.

### “Sửa encoding” bằng `new String(old.getBytes(...), ...)` tùy tiện

Nếu `old` đã là văn bản bị mojibake hoặc đã mất ký tự thay thế, chuỗi chuyển qua lại nhiều charset có thể làm hỏng thêm. Nên tìm **byte gốc** và thông tin charset gốc của nguồn, xác định chính xác giai đoạn encode/decode không khớp. Chỉ áp dụng chuyển mã sửa sai khi đã kiểm chứng được dữ liệu và thuật toán biến đổi tương ứng.

### So sánh chuỗi bằng `==` để “nhanh hơn”

`==` là phép so tham chiếu; thay `equals` bằng `==` làm thay đổi ý nghĩa kiểm tra. Nếu cần cải thiện hiệu năng, đo trước và chọn cách biểu diễn/thuật toán phù hợp mà vẫn giữ semantics.

### Trộn quy tắc index byte và index Unicode

Byte offset của file UTF-8, vị trí UTF-16 code unit và số code points là ba hệ đo khác nhau. Đừng dùng một số nguyên cho cả ba mà thiếu bước chuyển đổi rõ ràng.

## 6. Bài tập tự kiểm tra

**Câu 1.** `"name ".equals("name")` trả `false` mà không có exception. Thuộc nhóm nào?

**Trả lời:** **Lỗi nội dung**: chuỗi bên trái có thêm một dấu cách. Kiểm tra và quyết định theo quy tắc dữ liệu liệu dấu cách có ý nghĩa hay không.

**Câu 2.** `"abc".charAt(3)` gây lỗi nào?

**Trả lời:** **Lỗi chỉ số**, vì index hợp lệ từ 0 đến 2. `charAt(3)` gây `StringIndexOutOfBoundsException`.

**Câu 3.** Vì sao `"a.b".replaceAll(".", "X")` trả `"XXX"`?

**Trả lời:** **Lỗi dùng regex sai ý định**: dấu chấm trong pattern có ý nghĩa đặc biệt. Nếu muốn thay dấu chấm nguyên văn, dùng `replace(".", "X")` hoặc pattern `"\\."`.

**Câu 4.** Một dịch vụ gửi chuỗi `"é"` theo UTF-8, đầu nhận giải mã bằng ISO-8859-1. Lỗi gì?

**Trả lời:** **Sai charset khi giải mã**. Byte UTF-8 `c3 a9` bị hiểu theo bộ mã khác; hãy decode bằng UTF-8 và ghi rõ charset giữa hai phía.

**Câu 5.** Tại sao `"e\u0301".equals("\u00E9")` trả `false` nhưng vẫn có thể nhìn như cùng chữ?

**Trả lời:** **Lỗi giả định về nội dung Unicode**. Hai chuỗi có code point sequence khác nhau; chuẩn hóa NFC khi chính sách dữ liệu yêu cầu.

**Câu 6.** Một regex `[A-Z]+` hợp lệ nhưng `matcher.find()` trả `false`. Đây có phải `PatternSyntaxException` không?

**Trả lời:** Không. Pattern hợp lệ và không có match là **kết quả tìm kiếm bình thường**. Chỉ pattern sai cú pháp mới gây `PatternSyntaxException` khi compile.

**Câu 7.** Khi decode byte UTF-8 sai định dạng, có thể buộc Java ném lỗi thay vì tự thay ký tự không?

**Trả lời:** Có. Dùng `StandardCharsets.UTF_8.newDecoder().onMalformedInput(CodingErrorAction.REPORT)`; với byte lỗi thích hợp, `decode` sẽ ném một lớp con của `CharacterCodingException`.

## 7. Checklist khi một ca lỗi String xuất hiện

1. **Lỗi thuộc lớp nào?** Giá trị khác kỳ vọng, truy cập biên, pattern không hợp lệ hay sai encoding?
2. **Có dữ liệu gốc không?** Giữ lại đầu vào ngắn có thể tái hiện; nếu liên quan I/O, giữ byte gốc ở môi trường kiểm thử.
3. **Đang so cái gì?** Tham chiếu hay nội dung, UTF-16 index hay code point, literal hay regex, String hay byte?
4. **Khi nào dữ liệu đổi?** Xác định bước đọc → giải mã → chuẩn hóa → xử lý → encode; kiểm tra từng ranh giới.
5. **Đã sửa đúng hợp đồng chưa?** Đừng xóa ký tự, nuốt ngoại lệ hoặc chọn charset bằng suy đoán.
6. **Kiểm thử hồi quy có đủ trường hợp biên chưa?** Bao gồm chuỗi rỗng, Unicode, regex literal, byte hỏng và index đầu/cuối.

Điều quan trọng nhất là **quan sát đúng đơn vị dữ liệu**. Nếu đang gặp lỗi nội dung, nhìn vào code points; nếu lỗi chỉ số, nhìn vào biên UTF-16; nếu regex, nhìn vào pattern và replacement; nếu mã hóa, nhìn vào **byte gốc và charset**. Khi phân loại đúng, cách sửa thường rõ ràng hơn và kiểm thử cũng nhắm đúng nguyên nhân.

### Tài liệu chính thức

- [Java SE 17 — `String`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html).
- [Java SE 17 — `Pattern` và `Matcher`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/regex/Pattern.html).
- [Java SE 17 — `Charset`, `CharsetEncoder` và `CharsetDecoder`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/nio/charset/Charset.html).