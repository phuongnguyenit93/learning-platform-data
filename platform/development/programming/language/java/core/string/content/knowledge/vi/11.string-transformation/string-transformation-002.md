# `String.replace(CharSequence, CharSequence)` — thay thế chuỗi nguyên văn trong Java

Khi cần thay một đoạn văn bản bằng đoạn khác trong `String`, Java cung cấp overload **`replace(CharSequence target, CharSequence replacement)`**. Phương thức tìm các lần xuất hiện **liên tiếp, khớp chính xác và không chồng lấn** của `target` rồi thay chúng bằng `replacement`. Các chuỗi được hiểu là **văn bản nguyên văn (literal)**, không phải biểu thức chính quy (regex).

Ví dụ:

```java
String text = "Java Java Core";
String updated = text.replace("Java", "Kotlin");

System.out.println(updated); // Kotlin Kotlin Core
System.out.println(text);    // Java Java Core
```

Đây là thao tác **biến đổi nội dung** của chuỗi: kết quả trả về là một `String` mang nội dung mới; đối tượng `String` ban đầu vẫn giữ nguyên vì `String` là kiểu bất biến (*immutable*).

## 1. Cú pháp và ý nghĩa của hai tham số

Chữ ký API:

```java
public String replace(CharSequence target,
                      CharSequence replacement)
```

- **`target`:** dãy ký tự cần tìm. Ví dụ `"old"` hoặc `" "`. Các lần xuất hiện được tìm theo **nội dung chính xác**, phân biệt chữ hoa/thường.
- **`replacement`:** dãy ký tự đưa vào thay cho mỗi lần khớp. Nó được dùng **nguyên văn**; các ký tự như `$` và `\` trong replacement không có ý nghĩa đặc biệt của regex.
- **Giá trị trả về:** chuỗi kết quả sau thay thế tất cả các lần khớp **không chồng lấn** của `target`. Nếu không có đoạn khớp, nội dung kết quả bằng nội dung ban đầu.
- **Đối tượng nhận:** chuỗi gốc, ví dụ `text` trong `text.replace(target, replacement)`.
- **Kiểu tham số:** `CharSequence` nên không chỉ nhận `String` mà còn có thể nhận `StringBuilder` và các kiểu triển khai `CharSequence` khác.

Các trường hợp thường gặp:

| Chuỗi gốc | `target` | `replacement` | Nội dung kết quả |
| --- | --- | --- | --- |
| `"red blue red"` | `"red"` | `"green"` | `"green blue green"` |
| `"2026/10/22"` | `"/"` | `"-"` | `"2026-10-22"` |
| `"a.b.c"` | `"."` | `"-"` | `"a-b-c"` |
| `"hello"` | `"ll"` | `"LL"` | `"heLLo"` |
| `"hello"` | `"xyz"` | `"?"` | `"hello"` |
| `"AB"` | `"a"` | `"x"` | `"AB"` |

Chú ý `"a.b.c".replace(".", "-")` thay đúng hai ký tự dấu chấm. Dấu `.` ở đây **không** phải toán tử regex có nghĩa “bất kỳ ký tự nào”.

### Ví dụ đầy đủ chạy bằng Java 17+

Lưu tệp `ReplaceBasicDemo.java`:

```java
public class ReplaceBasicDemo {
    public static void main(String[] args) {
        String original = "Java Java Core";
        String updated = original.replace("Java", "Kotlin");

        System.out.println(updated);
        System.out.println(original);
        System.out.println("a.b.c".replace(".", "-"));
        System.out.println("a.b.c".replace("\\.", "-"));

        System.out.println(
                "abc".replace("xyz", "?").equals("abc"));
        System.out.println("Java".replace(
                new StringBuilder("av"),
                new StringBuilder("123")));
    }
}
```

Biên dịch và chạy:

```bash
javac -encoding UTF-8 ReplaceBasicDemo.java
java ReplaceBasicDemo
```

Kết quả:

```text
Kotlin Kotlin Core
Java Java Core
a-b-c
a.b.c
true
J123a
```

Lý giải:

1. Hai lần xuất hiện `"Java"` đều được thay bằng `"Kotlin"`. `original` không thay đổi.
2. `replace(".", "-")` khớp dấu chấm thật; `replace("\\.", "-")` tìm **hai ký tự** là dấu gạch chéo ngược và dấu chấm, không có trong `"a.b.c"` nên trả nội dung như cũ.
3. Không có `"xyz"` trong `"abc"` nên kết quả vẫn có cùng nội dung với `"abc"`. Ví dụ dùng `equals()` để kiểm tra **nội dung**, không dựa vào việc hai tham chiếu có trùng nhau hay không.
4. `new StringBuilder("av")` và `new StringBuilder("123")` được chấp nhận vì triển khai `CharSequence`. Trong chuỗi `Java`, đoạn `"av"` thay thành `"123"`, tạo `"J123a"`.

## 2. Tất cả lần khớp *không chồng lấn*, xét từ trái sang phải

`replace(target, replacement)` thay tất cả các lần xuất hiện **không chồng lấn** của `target`. Nếu có những lần khớp giao nhau, lần khớp sớm hơn được sử dụng trước; vị trí đã sử dụng không tiếp tục được lấy cho lần khớp khác.

Ví dụ với `"aaaaa"`, tìm `"aa"`:

```text
Chuỗi:   a a a a a
Chỉ số:  0 1 2 3 4
Khớp 1:  [0,2)  -> X
Khớp 2:      [2,4) -> X
Còn lại:          a
Kết quả: XXa
```

Đặc biệt, `"aaa".replace("aa", "b")` trả **`"ba"`** vì dùng cặp `aa` ở vị trí 0–1, rồi giữ nguyên chữ `a` cuối; không có lần khớp thứ hai không chồng lấn.

### Ví dụ biên và thay thế không lặp vô hạn

Lưu `ReplaceEdgesDemo.java`:

```java
public class ReplaceEdgesDemo {
    public static void main(String[] args) {
        System.out.println("aaaaa".replace("aa", "X"));
        System.out.println("aaa".replace("aa", "b"));
        System.out.println("banana".replace("ana", "X"));

        System.out.println("aba".replace("a", "aa"));
        System.out.println("aba".replace("", "-"));
        System.out.println("".replace("", "X"));
        System.out.println("abc".replace("b", ""));

        System.out.println(
                "ab".replace("b", "$1\\").equals("a$1\\"));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ReplaceEdgesDemo.java
java ReplaceEdgesDemo
```

Kết quả:

```text
XXa
ba
bXna
aabaa
-a-b-a-
X
ac
true
```

Chi tiết cần hiểu:

- `"banana".replace("ana", "X")` thành `"bXna"`: `"ana"` đầu tiên từ chỉ số 1 đến trước 4 được thay, phần `"na"` còn lại giữ nguyên. Hai lần xuất hiện tiềm năng của `"ana"` chồng lên nhau nên không thay cả hai.
- `"aba".replace("a", "aa")` thành `"aabaa"`. **Không tiếp tục tìm `"a"` trong chính nội dung `"aa"` vừa thay vào**; nếu tìm lại liên tục như vậy sẽ khác hoàn toàn với một lượt thay thế.
- `"abc".replace("b", "")` thành `"ac"`: replacement rỗng có tác dụng **xóa** các lần xuất hiện của target.
- `"ab".replace("b", "$1\\")` tạo đúng `"a$1\\"` dưới dạng giá trị chuỗi Java. Dấu `$` và dấu gạch chéo ngược trong replacement là **ký tự literal**; không diễn giải group hay escape theo cú pháp regex.

### Trường hợp `target` rỗng

`""` là dãy con rỗng và có vị trí khớp ở các **ranh giới** của chuỗi. Trong trường hợp ASCII đơn giản:

```java
System.out.println("aba".replace("", "-")); // -a-b-a-
System.out.println("".replace("", "X"));    // X
```

Điều này thường gây bất ngờ: **target rỗng không có nghĩa là không thay gì**. Nếu `target` do người dùng cung cấp, cần quyết định rõ việc cho phép chuỗi rỗng hay không:

```java
if (target == null || target.isEmpty()) {
    throw new IllegalArgumentException(
            "target must be non-empty");
}
String updated = original.replace(target, replacement);
```

Đây là đoạn mã minh họa **bên trong một phương thức**, giả định `original` và `replacement` đã hợp lệ. Đặc biệt với Unicode, đừng dùng thao tác chèn tại mọi đơn vị chuỗi để thay cho thuật toán phân đoạn ký tự mà người dùng nhìn thấy; một emoji có thể chiếm nhiều đơn vị UTF-16.

## 3. Ranh giới giữa chuỗi literal và regex

`replace(CharSequence, CharSequence)` coi **cả `target` lẫn `replacement` là văn bản nguyên văn**. `replaceFirst(regex, replacement)` và `replaceAll(regex, replacement)` dùng biểu thức chính quy để tìm; `replacement` của chúng có cú pháp riêng cho `$1` và backslash.

~~~java
String source = "a.b.c";
System.out.println(source.replace(".", "-"));       // a-b-c
System.out.println(source.replaceAll(".", "-"));    // -----
System.out.println(source.replaceAll("\\.", "-")); // a-b-c
System.out.println("ab".replace("b", "$1\\"));       // a$1\
~~~

Ở overload literal, `"."` khớp đúng dấu chấm và `"$1\\"` được chèn nguyên văn. Với regex, phải escape dấu chấm thành `"\\."`; nếu pattern và replacement lấy từ dữ liệu động, `Pattern.quote(target)` và `Matcher.quoteReplacement(replacement)` giúp coi các phần tương ứng là literal. Bài so sánh `replace`, `replaceFirst`, `replaceAll` riêng trong chương trình bày sâu cách escape, nhóm bắt và lỗi regex. Khi không cần regex, chọn trực tiếp `replace(target, replacement)`.

## 4. `String` bất biến và sử dụng giá trị trả về

Phương thức tìm và tạo **giá trị kết quả**, không sửa `String` nhận lời gọi:

~~~java
String original = "red red";
String updated = original.replace("red", "blue");
System.out.println(original); // red red
System.out.println(updated);  // blue blue
~~~

Nếu chỉ viết `original.replace("red", "blue");` rồi bỏ giá trị trả về, biến `original` vẫn chứa `"red red"`. Có thể gán lại một biến khi không cần dùng bản gốc; nếu cần hiển thị hay đối chiếu nội dung đã nhận, giữ `original` và `updated` riêng. Với nhiều phép thay nối tiếp, phép sau chạy trên kết quả của phép trước; thứ tự quy tắc có thể thay đổi kết quả.

## 5. Kiểm tra null và dữ liệu đầu vào

Không có đối tượng để gọi `replace()` nếu biến nhận là `null`. Ngoài ra, đối với overload `replace(CharSequence, CharSequence)`, Java yêu cầu **cả target và replacement đều khác `null`**.

```java
String text = "hello";

// Các lời gọi sau sẽ ném NullPointerException:
// text.replace((CharSequence) null, "x");
// text.replace("l", (CharSequence) null);

String missing = null;
// missing.replace("a", "b");
```

Nếu đầu vào có thể vắng mặt, cần chọn chính sách rõ ràng: từ chối bằng ngoại lệ, giữ nguyên, hoặc trả về giá trị khác theo yêu cầu nghiệp vụ. Ví dụ utility trả về `null` nếu chuỗi gốc `null`, còn hai tham số thay thế phải hợp lệ:

```java
import java.util.Objects;

public class SafeReplaceDemo {
    public static String replaceOrNull(
            String text, String target, String replacement) {
        Objects.requireNonNull(target, "target");
        Objects.requireNonNull(replacement, "replacement");
        return text == null
                ? null
                : text.replace(target, replacement);
    }

    public static void main(String[] args) {
        System.out.println(
                replaceOrNull("a/b/c", "/", "-"));
        System.out.println(
                replaceOrNull(null, "/", "-") == null);
    }
}
```

Chạy `javac -encoding UTF-8 SafeReplaceDemo.java` và `java SafeReplaceDemo`, kết quả:

```text
a-b-c
true
```

Phương thức ví dụ cố ý chọn chính sách trả về `null` khi `text` thiếu. Trong API khác, ném `IllegalArgumentException` hoặc `NullPointerException` theo hợp đồng có thể phù hợp hơn. **Đừng tự biến `null` thành chuỗi `"null"`** khi nghiệp vụ chưa quy định cách xử lý.

## 6. Unicode và phân biệt chữ hoa/thường

`String.replace(CharSequence, CharSequence)` so khớp dãy ký tự **chính xác theo nội dung UTF-16**, không tự áp dụng chuẩn hóa Unicode, không bỏ dấu và không so khớp theo văn hóa/ngôn ngữ.

Hai biểu diễn nhìn giống nhau có thể không có cùng dãy code unit:

- `"\u00E9"` là ký tự `é` dựng sẵn (U+00E9).
- `"e\u0301"` gồm `e` (U+0065) và dấu sắc kết hợp U+0301.

Ví dụ tệp `ReplaceUnicodeDemo.java`:

```java
import java.text.Normalizer;

public class ReplaceUnicodeDemo {
    public static void main(String[] args) {
        String composed = "Caf\u00E9";
        String decomposed = "Cafe\u0301";

        System.out.println(
                composed.replace("e\u0301", "X"));

        String normalized = Normalizer.normalize(
                decomposed, Normalizer.Form.NFC);
        System.out.println(
                normalized.replace("\u00E9", "X"));
    }
}
```

Chạy:

```bash
javac -encoding UTF-8 ReplaceUnicodeDemo.java
java ReplaceUnicodeDemo
```

Kết quả:

```text
Café
CafX
```

Chuỗi đầu không chứa chuỗi hai code point `e + dấu sắc kết hợp`, nên nội dung không đổi. Sau khi chuẩn hóa chuỗi phân rã về `NFC`, chuỗi có ký tự dựng sẵn và thay `é` bằng `X` thành công.

Nếu yêu cầu xử lý tương đương Unicode, **chuẩn hóa cả nguồn và target** về cùng một dạng phù hợp trước khi thay; cần nhớ normalization có thể làm thay đổi code point và offset. Nếu yêu cầu là tìm kiếm không phân biệt hoa/thường, cân nhắc phép biến đổi chữ theo `Locale` hoặc thuật toán Unicode case folding phù hợp; `replace()` mặc định **không bỏ qua** chữ hoa/thường.

Cần thận trọng với emoji, dấu kết hợp và surrogate pairs: phương thức tìm đoạn theo UTF-16, **không cam kết** giữ ranh giới *grapheme cluster* (cụm ký tự người dùng cảm nhận). Nếu mục tiêu là thay một ký tự hiển thị hoàn chỉnh, cần xác định ranh giới Unicode theo quy tắc ứng dụng.

## 7. Khi nào nên dùng `replace()`?

Một số tình huống hợp lý:

- **Đổi ký hiệu phân cách cố định:** `"a/b/c".replace("/", "-")` → `"a-b-c"`.
- **Thay token văn bản đã được nhận diện:** `"Hello, {name}!".replace("{name}", "Lan")` → `"Hello, Lan!"`, trong ngữ cảnh đầu vào và thứ tự thay thế đã được kiểm soát.
- **Loại bỏ một đoạn cụ thể:** `"a--b".replace("--", "")` → `"ab"`.
- **Chuẩn hóa cách viết một cụm cố định trong văn bản nội bộ:** `"ERROR: ERROR:".replace("ERROR", "WARN")` → `"WARN: WARN:"`.

Lưu ý, **thay thế nguyên văn không phải thao tác parse**: thay `"cat"` trong `"catalog"` cũng có thể làm thay một phần từ lớn hơn. Với token nghiệp vụ, mã định danh, placeholder có escape/nesting hoặc dữ liệu cấu trúc, nên dùng parser hoặc cơ chế template chuyên dụng để tránh thay nhầm.

Với văn bản dài, nhiều mục tiêu thay thế hoặc gọi `replace()` lặp trong vòng lặp, hiệu năng phụ thuộc cách xử lý và dữ liệu. Mỗi lần gọi trả về một `String` theo ngữ nghĩa API, nhưng số lượng cấp phát thực tế là chi tiết triển khai và có thể được JVM tối ưu. Khi cần ghép nhiều phần trong vòng lặp, `StringBuilder` thường phù hợp; khi có nhiều mẫu thay thế hoặc yêu cầu tránh các lần thay lẫn nhau, nên thiết kế một phép xử lý duy nhất dựa trên quy tắc thay thế cụ thể.

Ví dụ sự khác nhau giữa **một lần gọi** và **hai lần gọi nối tiếp**:

```java
String text = "ab";
System.out.println(text.replace("a", "b"));   // bb
System.out.println(text.replace("a", "b")
                       .replace("b", "c"));     // cc
```

Trong hai lần gọi nối tiếp, lần thứ hai tìm cả `"b"` cũ lẫn `"b"` do lần thứ nhất tạo ra. Điều này **khác** với một lần thay thế `target`: kết quả vừa chèn **không bị xử lý lại trong chính lần gọi đó**.

## 8. Các lỗi thường gặp

1. **Dùng `replaceAll()` khi target là văn bản nguyên văn:** dấu `.`, `*`, `[`, `(` hoặc `\` có thể mang nghĩa regex và dẫn đến kết quả sai hoặc ngoại lệ `PatternSyntaxException`. Dùng `replace(CharSequence, CharSequence)` cho văn bản literal.
2. **Nghĩ chỉ thay lần đầu tiên:** `replace()` thay **tất cả** lần khớp không chồng lấn; với regex, `replaceFirst()` là API riêng cho lần đầu.
3. **Không lưu giá trị trả về:** `text.replace(...)` không biến đổi đối tượng `text` vì `String` bất biến.
4. **Đặt `$1` trong replacement rồi chờ group substitution:** overload `replace(CharSequence, CharSequence)` **không có** group capture. `$1` được chèn nguyên văn.
5. **Tưởng target rỗng luôn vô tác dụng:** `"ab".replace("", "-")` có thể chèn thêm ký tự ở các ranh giới; cần kiểm tra/định nghĩa chính sách đầu vào.
6. **Quên null:** target hoặc replacement null gây `NullPointerException`; biến chuỗi nhận null cũng không thể gọi phương thức.
7. **Nhầm khớp chuỗi con với khớp từ:** `"catalog".replace("cat", "dog")` trở thành `"dogalog"` vì `replace()` không hiểu ranh giới từ.
8. **Trông chờ không phân biệt chữ hoa/thường:** `"Java".replace("java", "X")` vẫn là `"Java"`.
9. **Chỉ test ASCII:** dữ liệu có dấu, Unicode normalization, emoji và dấu kết hợp có thể đòi hỏi quy tắc xử lý thêm.
10. **Thay thế nhiều lần mà không xét thứ tự:** đầu ra từ phép thay thứ nhất có thể trở thành target của phép thứ hai nếu gọi `replace()` nối tiếp.
11. **Dựa vào `==` để kiểm tra kết quả:** nên dùng `equals()` để so nội dung thay vì so tham chiếu.

## 9. Tự kiểm tra

Với `String s = "aaaa";`:

| Lời gọi | Kết quả | Giải thích |
| --- | --- | --- |
| `s.replace("a", "X")` | `"XXXX"` | Có bốn lần khớp literal `a` |
| `s.replace("aa", "b")` | `"bb"` | Hai đoạn `aa` không chồng lấn |
| `s.replace("aaa", "Z")` | `"Za"` | Một đoạn `aaa` từ trái sang phải |
| `s.replace("a", "")` | `""` | Xóa tất cả `a` |
| `s.replace("A", "X")` | `"aaaa"` | Phân biệt hoa/thường |
| `s.replace("b", "X")` | `"aaaa"` | Không có target |
| `s.replace("", "-")` | `"-a-a-a-a-"` | Thay target rỗng tại ranh giới |

Bạn có thể tự tạo file Java cho các ví dụ trên và dùng `System.out.println(...)` để kiểm tra. Nếu đang xử lý dữ liệu đến từ người dùng, hãy thử thêm chuỗi rỗng, `null`, target dài hơn nguồn, ký tự đặc biệt như `.`/`$`/`\` và chuỗi tiếng Việt có dấu.

**Ghi nhớ:** `replace(CharSequence target, CharSequence replacement)` thực hiện thay thế **mọi lần xuất hiện literal, không chồng lấn**; **target và replacement đều được hiểu nguyên văn**. `replaceAll()` dùng **regex** và có quy tắc thay thế khác. Luôn sử dụng giá trị `String` trả về, kiểm tra đầu vào `null`/rỗng theo yêu cầu, và chỉ dùng `equals()` khi cần so nội dung chuỗi.
