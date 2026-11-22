# `String.isBlank()` so với `String.isEmpty()` trong Java

Trong Java, **chuỗi rỗng** và **chuỗi chỉ chứa khoảng trắng** là hai khái niệm khác nhau. Hai phương thức `String.isEmpty()` và `String.isBlank()` giúp kiểm tra hai tính chất này nhưng không thay thế nhau. Chọn sai phương thức có thể làm chương trình chấp nhận tên chỉ có dấu cách, từ chối đầu vào hợp lệ hoặc xử lý nhầm các ký tự Unicode nhìn như khoảng trắng.

Mục tiêu bài học:

- Hiểu chính xác điều kiện trả về `true` của `isEmpty()` và `isBlank()`.
- Phân biệt chuỗi `""`, `"   "`, tab, newline, khoảng trắng Unicode, non-breaking space và ký tự không nhìn thấy.
- Chọn phép kiểm tra phù hợp cho dữ liệu đầu vào, nhận biết `null` và quan hệ với `strip()`/`trim()`.
- Sử dụng ví dụ Java 17+ có thể biên dịch và kiểm chứng kết quả.

## 1. Khái niệm: empty và blank

### `isEmpty()`: chuỗi có độ dài bằng 0

`String.isEmpty()` trả về `true` khi và chỉ khi `length() == 0`. Nó **không đọc nội dung** để xem đó có phải dấu cách hay không.

~~~java
System.out.println("".isEmpty());       // true
System.out.println(" ".isEmpty());      // false
System.out.println("\t".isEmpty());     // false
System.out.println("Java".isEmpty());   // false
~~~

Một chuỗi có một dấu cách vẫn có `length() == 1`, nên không rỗng. Một chuỗi gồm tab hoặc xuống dòng cũng không rỗng. `isEmpty()` có sẵn từ Java 6; biểu thức `s.isEmpty()` diễn đạt rõ nghĩa hơn `s.length() == 0` nhưng có cùng điều kiện logic.

### `isBlank()`: rỗng hoặc chỉ chứa whitespace

`String.isBlank()`, được bổ sung trong Java 11, trả `true` khi chuỗi **rỗng hoặc tất cả code point của chuỗi đều được Java coi là whitespace** theo `Character.isWhitespace(int)`. Nếu có ít nhất một code point không thuộc nhóm đó, kết quả là `false`.

~~~java
System.out.println("".isBlank());          // true
System.out.println(" ".isBlank());         // true
System.out.println("\t\n".isBlank());      // true
System.out.println("  Java  ".isBlank());  // false
~~~

Có thể nhớ như sau:

- `isEmpty()` hỏi: **“Có ký tự nào không?”**
- `isBlank()` hỏi: **“Có ký tự nào không phải whitespace theo quy tắc Java không?”**

Vì không có ký tự nào để vi phạm điều kiện “chỉ chứa whitespace”, chuỗi rỗng cũng được coi là blank. Với mọi `String s` không null, **`s.isEmpty()` là `true` thì `s.isBlank()` cũng là `true`**; chiều ngược lại không đúng.

## 2. So sánh trực tiếp bằng bảng

| Nội dung String | `isEmpty()` | `isBlank()` | Giải thích |
|---|---:|---:|---|
| `""` | `true` | `true` | Không có code unit nào |
| `" "` | `false` | `true` | Một dấu cách ASCII |
| `"   "` | `false` | `true` | Ba dấu cách |
| `"\t"` | `false` | `true` | Tab là whitespace |
| `"\n"` | `false` | `true` | Line feed là whitespace |
| `" \t\n "` | `false` | `true` | Toàn whitespace |
| `"Java"` | `false` | `false` | Có chữ cái |
| `" Java "` | `false` | `false` | Có chữ cái dù hai đầu là dấu cách |
| `"\u2003"` | `false` | `true` | U+2003 EM SPACE được `Character.isWhitespace` công nhận |
| `"\u00A0"` | `false` | `false` | U+00A0 NO-BREAK SPACE không được `Character.isWhitespace` công nhận |
| `"\u200B"` | `false` | `false` | U+200B ZERO WIDTH SPACE không phải whitespace theo API này |
| Chuỗi chứa code unit U+0000 | `false` | `false` | Null character không phải whitespace theo `Character.isWhitespace` |

**Lưu ý về bảng:** `"\t"`, `"\n"` và `"\u2003"` là cách biểu diễn **trong mã nguồn Java**, không phải văn bản chứa dấu backslash và chữ `t`, `n` hay `u2003`. Vì một số dấu cách Unicode không nhìn thấy, nên khi kiểm thử hãy hiển thị mã Unicode hoặc nhãn rõ ràng thay vì chỉ in chuỗi ra terminal.

## 3. “Whitespace” của Java không có nghĩa là mọi ký tự nhìn như khoảng trống

Điểm dễ nhầm nhất của `isBlank()` là cách định nghĩa whitespace. Java dựa vào `Character.isWhitespace(int)`. Nó nhận diện nhiều ký tự như ASCII space, tab, xuống dòng và một số Unicode space, nhưng **không bao gồm mọi ký tự Unicode có tên hoặc hình dạng liên quan đến khoảng trống**.

Ví dụ:

~~~java
System.out.println(Character.isWhitespace(' '));       // true
System.out.println(Character.isWhitespace('\t'));      // true
System.out.println(Character.isWhitespace(0x2003));    // true: EM SPACE
System.out.println(Character.isWhitespace(0x00A0));    // false: NO-BREAK SPACE
System.out.println(Character.isSpaceChar(0x00A0));     // true
System.out.println(Character.isWhitespace(0x200B));    // false: ZERO WIDTH SPACE
~~~

`Character.isSpaceChar(int)` là API khác, dựa trên các Unicode category về dấu phân cách, nên **không tương đương** `Character.isWhitespace(int)`. Chẳng hạn U+00A0 là một *space separator* và `isSpaceChar(0x00A0)` trả `true`, nhưng `isWhitespace(0x00A0)` trả `false`. Một số dấu cách không ngắt dòng như U+2007 FIGURE SPACE và U+202F NARROW NO-BREAK SPACE cũng cần xem xét riêng khi nghiệp vụ muốn coi chúng là blank.

U+200B ZERO WIDTH SPACE thường vô hình nhưng không được `Character.isWhitespace` xem là whitespace. Các ký tự định dạng vô hình khác cũng có thể khiến người dùng nhìn thấy ô trống trong khi `isBlank()` lại trả `false`.

Vì vậy:

- **Trường nhập văn bản phổ thông:** `isBlank()` thường là điểm bắt đầu hợp lý để từ chối chuỗi chỉ có dấu cách, tab hoặc xuống dòng.
- **Hệ thống có quy tắc Unicode riêng:** cần định nghĩa tập code point được bỏ qua hay chấp nhận, rồi viết quy tắc kiểm tra tương ứng.
- **Mã định danh, mật khẩu, dữ liệu bảo mật:** không tùy tiện loại bỏ hoặc gộp các ký tự vô hình khi chưa có đặc tả; việc chuẩn hóa có thể thay đổi giá trị gốc.

Không nên tuyên bố “`isBlank()` nhận diện toàn bộ các loại khoảng trắng của Unicode” hoặc “mọi ký tự vô hình đều là blank”.

## 4. Quan hệ với `strip()`, `trim()` và `length()`

### `strip()` và `isBlank()` dùng tiêu chí whitespace gần nhau

`strip()` (Java 11+) bỏ các code point ở **đầu và cuối** chuỗi được `Character.isWhitespace` nhận diện. Với một `String` bình thường, `s.isBlank()` tương ứng về ý nghĩa với việc `s.strip().isEmpty()`: nếu tất cả ký tự đều là whitespace, sau `strip()` sẽ không còn gì.

~~~java
String text = " \t ";
System.out.println(text.isBlank());         // true
System.out.println(text.strip().isEmpty()); // true

String mixed = "  Java \t";
System.out.println(mixed.isBlank());         // false
System.out.println(mixed.strip());           // Java
~~~

Tuy nhiên, khi **chỉ cần biết có blank hay không**, nên gọi trực tiếp `isBlank()`: code diễn đạt đúng mục đích và không phải chủ động tạo kết quả chuỗi sau khi strip. Nếu cần cả nội dung đã chuẩn hóa để lưu, xử lý hoặc so sánh, dùng `strip()` tại điểm phù hợp.

### `trim()` dùng tiêu chí cũ, khác `strip()`

`trim()` bỏ các code unit có giá trị **không lớn hơn U+0020** ở hai đầu. Điều này khác quy tắc Unicode whitespace của `strip()`. Do đó `s.trim().isEmpty()` **không tương đương** `s.isBlank()`.

Ví dụ đối chứng:

~~~java
String emSpace = "\u2003";
System.out.println(emSpace.isBlank());          // true
System.out.println(emSpace.trim().isEmpty());   // false
System.out.println(emSpace.strip().isEmpty());  // true

String nul = String.valueOf((char) 0);
System.out.println(nul.isBlank());              // false
System.out.println(nul.trim().isEmpty());       // true
System.out.println(nul.strip().isEmpty());      // false
~~~

Dòng liên quan `nul` cho thấy có những code unit bị `trim()` loại bỏ dù `isBlank()` không coi chúng là whitespace. Ngược lại, U+2003 được `isBlank()` nhận diện nhưng `trim()` không bỏ. Dùng `trim().isEmpty()` khi thật sự muốn áp dụng quy tắc `trim()` cũ; đừng coi đây là thay thế chính xác của `isBlank()`.

### `length()` không phải thước đo “ký tự có nghĩa”

`String.length()` đếm **UTF-16 code unit**, không phải số từ, số ký tự hiển thị hoặc số code point. `"🚀".length() == 2`, và `"🚀".isBlank()` là `false`. Điều kiện `isEmpty()` chỉ dựa trên số code unit bằng 0, nên vấn đề biểu diễn Unicode không làm thay đổi ý nghĩa của nó. `isBlank()` kiểm tra whitespace theo code point Unicode của String và không có tác dụng “xóa” nội dung.

## 5. Xử lý `null` đúng cách

Cả hai phương thức đều là **instance method của `String`**. Nếu biến chứa `null`, gọi `value.isEmpty()` hoặc `value.isBlank()` đều ném `NullPointerException`. `null` không phải một chuỗi rỗng.

~~~java
String value = null;
// value.isEmpty(); // NullPointerException
// value.isBlank(); // NullPointerException
~~~

Có hai quy ước thông dụng; hãy chọn rõ ràng theo yêu cầu ứng dụng.

**Quy ước 1: null được xem là “không có dữ liệu”.** Dùng kiểm tra kết hợp:

~~~java
static boolean isMissing(String input) {
    return input == null || input.isBlank();
}
~~~

`||` có đánh giá ngắn mạch, nên khi `input == null` là true, Java không gọi `input.isBlank()`.

**Quy ước 2: null là lỗi lập trình hoặc dữ liệu bắt buộc.** Đưa ra lỗi rõ ràng trước khi kiểm tra chuỗi:

~~~java
import java.util.Objects;

static boolean blankRequiredString(String input) {
    Objects.requireNonNull(input, "input must not be null");
    return input.isBlank();
}
~~~

Việc nên chấp nhận null, từ chối null hay coi null tương đương rỗng là **quy tắc nghiệp vụ**, không phải hành vi mặc định của `isBlank()` hoặc `isEmpty()`.

## 6. Chọn đúng phương thức theo nghiệp vụ

| Nhu cầu | Thường chọn | Lý do |
|---|---|---|
| Kiểm tra chuỗi chưa có nội dung nào | `isEmpty()` | Điều kiện đúng bằng độ dài 0 |
| Trường họ tên/nội dung yêu cầu ít nhất một ký tự không phải whitespace Java | `isBlank()` | Từ chối cả `""` và `"   "` |
| Xác minh giá trị có thể null và không có nội dung đáng kể | `s == null || s.isBlank()` | Bao gồm cả null và chuỗi blank |
| Phân biệt `""` với một dấu cách do người dùng nhập | `isEmpty()` | Dấu cách là dữ liệu, không phải chuỗi rỗng |
| Trường yêu cầu dữ liệu có cấu trúc như email, mã, số | `isBlank()` chỉ là kiểm tra đầu tiên | Cần kiểm tra định dạng, độ dài và quy tắc cụ thể |
| Chuỗi cần loại bỏ khoảng trắng hai đầu trước khi xử lý | `strip()` rồi validation thích hợp | `isBlank()` chỉ trả boolean, không đổi chuỗi |
| Phân tích dữ liệu có U+00A0/U+200B | Quy tắc Unicode tường minh | `isBlank()` không coi mọi ký tự vô hình là whitespace |
| Kiểm tra String có ít nhất một code unit | `!isEmpty()` | Không bảo đảm có nội dung hữu ích cho người dùng |
| Kiểm tra String có ít nhất một code point không phải whitespace Java | `!isBlank()` | Có thể vẫn chứa ký tự vô hình hoặc control character không thuộc tập whitespace |

### Ví dụ: validate trường tên bắt buộc

~~~java
static String validateDisplayName(String raw) {
    if (raw == null || raw.isBlank()) {
        throw new IllegalArgumentException("Name is required");
    }
    String cleaned = raw.strip();
    if (cleaned.length() > 50) {
        throw new IllegalArgumentException("Name is too long");
    }
    return cleaned;
}
~~~

Đây là **ví dụ chính sách đơn giản**, không phải bộ quy tắc hoàn chỉnh cho mọi tên người. Nó dùng `length()` theo UTF-16 code unit và chỉ `strip()` những ký tự mà `Character.isWhitespace` công nhận; U+00A0 hoặc U+200B còn có thể tồn tại. Nếu thực sự cần giới hạn theo code point, số ký tự hiển thị hoặc xử lý các ký tự vô hình, phải thiết kế validation riêng. Đừng tùy tiện đổi `strip()` thành cách xóa mọi whitespace bên trong: tên gồm nhiều từ có khoảng trắng hợp lệ.

### Vì sao không luôn `strip().isEmpty()`?

Nếu chỉ cần quyết định “chuỗi có blank không”, `isBlank()` nêu đúng ý định và đơn giản. Khi vừa cần kiểm tra vừa cần giữ giá trị đã chuẩn hóa, có thể `strip()` một lần:

~~~java
String raw = "  Java  ";
String normalized = raw.strip();
if (!normalized.isEmpty()) {
    System.out.println(normalized); // Java
}
~~~

Không có nghĩa `isBlank()` luôn nhanh hơn mọi cách khác trong mọi bản JVM. Với code nhạy hiệu năng, đo đạc trước khi tối ưu; ưu tiên biểu thức rõ ràng và đúng nghĩa.

## 7. Chương trình Java 17+ hoàn chỉnh

Đặt đoạn sau vào tệp UTF-8 tên **`BlankVsEmptyDemo.java`**. Chương trình hiển thị đầu ra cho các trường hợp quan trọng, so sánh `trim()` với `strip()` và minh họa xử lý null. Các đoạn ngắn ở phần trước chỉ là snippet minh họa, có thể cần đặt trong method/class để chạy độc lập.

~~~java
public class BlankVsEmptyDemo {
    private static void check(String label, String value) {
        System.out.printf("%s: empty=%s, blank=%s%n",
                label, value.isEmpty(), value.isBlank());
    }

    private static boolean isMissing(String value) {
        return value == null || value.isBlank();
    }

    public static void main(String[] args) {
        check("empty", "");
        check("space", " ");
        check("tab-newline", "\t\n");
        check("em-space", "\u2003");
        check("no-break-space", "\u00A0");
        check("zero-width-space", "\u200B");
        check("nul", String.valueOf((char) 0));
        check("word", " Java ");

        String emSpace = "\u2003";
        String nul = String.valueOf((char) 0);
        System.out.println("em-space-trim-empty="
                + emSpace.trim().isEmpty());
        System.out.println("em-space-strip-empty="
                + emSpace.strip().isEmpty());
        System.out.println("nul-trim-empty="
                + nul.trim().isEmpty());
        System.out.println("nul-strip-empty="
                + nul.strip().isEmpty());

        System.out.println("missing-null=" + isMissing(null));
        System.out.println("missing-spaces=" + isMissing(" \t "));
        System.out.println("missing-word=" + isMissing("Java"));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac -encoding UTF-8 BlankVsEmptyDemo.java
java BlankVsEmptyDemo
~~~

Stdout chính xác:

~~~text
empty: empty=true, blank=true
space: empty=false, blank=true
tab-newline: empty=false, blank=true
em-space: empty=false, blank=true
no-break-space: empty=false, blank=false
zero-width-space: empty=false, blank=false
nul: empty=false, blank=false
word: empty=false, blank=false
em-space-trim-empty=false
em-space-strip-empty=true
nul-trim-empty=true
nul-strip-empty=false
missing-null=true
missing-spaces=true
missing-word=false
~~~

Giải thích phần dễ bất ngờ: `"\\u2003"` (trong ví dụ thực tế là escape `\u2003` của Java source) đại diện cho EM SPACE, một whitespace theo Java, nên `isBlank()` đúng và `strip()` bỏ được. `"\u00A0"` là NO-BREAK SPACE và `"\u200B"` là ZERO WIDTH SPACE: cả hai không được `Character.isWhitespace` coi là whitespace. `String.valueOf((char) 0)` tạo chuỗi chứa U+0000, không blank nhưng lại được quy tắc cũ của `trim()` loại bỏ ở hai đầu.

## 8. Những lỗi phổ biến

### Lỗi 1: dùng `isEmpty()` để kiểm tra trường bắt buộc

~~~java
String input = "   ";
if (!input.isEmpty()) {
    // Đi vào nhánh này dù người dùng chưa nhập ký tự có nghĩa.
}
~~~

Nếu chính sách là không chấp nhận chuỗi chỉ có whitespace Java, kiểm tra `!input.isBlank()` sau khi xử lý null.

### Lỗi 2: mặc định `isBlank()` bỏ qua mọi Unicode space

NO-BREAK SPACE và một số ký tự vô hình khác không được `Character.isWhitespace` nhận diện. Nếu nghiệp vụ cần coi chúng là trống, tự định nghĩa kiểm tra dựa trên tập ký tự cho phép, tiêu chí Unicode thích hợp và quy tắc chuẩn hóa đã thống nhất. Phải quyết định riêng việc có loại bỏ zero-width formatting characters hay không.

### Lỗi 3: coi `trim().isEmpty()` bằng `isBlank()`

Hai biểu thức có tiêu chí khác nhau: U+2003 và U+0000 là hai phản ví dụ điển hình. Từ Java 11, dùng trực tiếp `isBlank()` khi mong muốn chính xác là Java whitespace.

### Lỗi 4: không xét `null`

`null.isBlank()` không phải biểu thức Java hợp lệ theo nghĩa literal; còn gọi phương thức trên biến `String` đang null gây `NullPointerException`. Viết guard ở điểm nhận dữ liệu và chọn cách xử lý rõ ràng.

### Lỗi 5: chỉ kiểm tra blank rồi cho rằng dữ liệu đã hợp lệ

`"@"`, `"!"`, `"0"`, U+200B hoặc một chuỗi dài vô hạn đều không blank. Điều đó không chứng minh chúng là email, tên hợp lệ, số đúng định dạng hoặc dữ liệu an toàn. `isBlank()` là kiểm tra **thiếu nội dung theo định nghĩa whitespace**, không phải bộ xác thực nội dung.

### Lỗi 6: thay đổi chuỗi trong khi tưởng đang kiểm tra

Cả `isEmpty()` và `isBlank()` chỉ trả boolean, không sửa String. `strip()` trả lại chuỗi đã xử lý; vì `String` bất biến, gọi `raw.strip();` mà không dùng giá trị trả về sẽ không cập nhật `raw`.

## 9. Checklist lựa chọn

1. **Muốn phát hiện đúng chuỗi độ dài 0?** Dùng `isEmpty()`.
2. **Muốn phát hiện rỗng hoặc chỉ gồm Java whitespace?** Dùng `isBlank()` (Java 11+).
3. **Đầu vào có thể null?** Kiểm tra null trước; tùy nghiệp vụ dùng `s == null || s.isBlank()`.
4. **Cần loại bỏ whitespace đầu/cuối?** Dùng `strip()` khi phù hợp; tránh coi `trim()` và `strip()` là đồng nghĩa.
5. **Có Unicode space/format characters đặc biệt?** Kiểm tra tiêu chí `Character.isWhitespace` trước khi dựa vào `isBlank()`.
6. **Dữ liệu có ràng buộc khác?** Kết hợp với kiểm tra độ dài, cấu trúc, miền giá trị và nghiệp vụ cụ thể.

**Ghi nhớ:** `isEmpty()` kiểm tra **độ dài bằng 0**; `isBlank()` kiểm tra **rỗng hoặc chỉ có whitespace theo Java**. Dấu cách thông thường là điểm khác biệt dễ gặp nhất, còn non-breaking space và các ký tự Unicode vô hình là lý do cần hiểu chính xác định nghĩa whitespace.