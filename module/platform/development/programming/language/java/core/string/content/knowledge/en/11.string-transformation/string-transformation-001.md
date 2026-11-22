# `String.replace(char, char)` — thay mọi ký tự khớp trong Java

## 1. Mục tiêu và ý nghĩa

`String.replace(char oldChar, char newChar)` là phương thức dùng để **thay tất cả lần xuất hiện** của một đơn vị ký tự `char` bằng một `char` khác trong chuỗi Java. Chẳng hạn, `"banana".replace('a', 'o')` có kết quả `"bonono"`: cả ba chữ `a` đều được thay. Phương thức không dừng ở kết quả đầu tiên và không cần vòng lặp tự tìm từng vị trí.

Bốn điểm cần nắm:

1. `oldChar` và `newChar` là hai đối số kiểu **`char`**, viết bằng dấu nháy đơn như `'a'`; chúng biểu diễn đơn vị mã UTF-16, không phải một chuỗi ký tự tùy ý.
2. `replace(char,char)` tìm và thay **mọi phần tử khớp chính xác**. Phép tìm phân biệt hoa/thường: `'a'` khác `'A'`.
3. `String` **bất biến**. Phương thức trả về kết quả kiểu `String`; không sửa chuỗi đã gọi. Muốn lưu kết quả, phải gán nó vào biến hoặc truyền cho nơi cần dùng.
4. Đây là thao tác thay **ký tự literal**, không phải biểu thức chính quy (*regex*). Muốn thay toàn bộ đoạn văn bản có nhiều `char`, dùng overload `replace(CharSequence, CharSequence)`; muốn xử lý regex, dùng `replaceAll(String, String)`.

Bài này đi từ cú pháp đến ví dụ chạy được, phân biệt overload, Unicode và những lỗi thường gặp khi xử lý dữ liệu văn bản.

## 2. Cú pháp, kiểu dữ liệu và kết quả trả về

Khai báo API trong Java SE 17:

```java
public String replace(char oldChar, char newChar)
```

| Thành phần | Ý nghĩa |
| --- | --- |
| `oldChar` | Đơn vị `char` cần tìm trong chuỗi nguồn |
| `newChar` | Đơn vị `char` sẽ thay cho mỗi vị trí khớp |
| Kết quả | Một giá trị `String` có nội dung sau khi thay các vị trí khớp |
| Quy tắc khớp | So sánh chính xác giá trị `char`; không tự bỏ qua hoa/thường, dấu hoặc chuẩn hóa Unicode |
| Phạm vi | Toàn bộ chuỗi, từ đầu đến cuối; không có tham số giới hạn số lần thay |

Ví dụ biểu thức (đặt trong một phương thức, như `main`):

```java
"banana".replace('a', 'o');   // "bonono"
"aaaa".replace('a', 'b');     // "bbbb"
"aba".replace('a', 'b');      // "bbb"
"Java".replace('a', 'A');     // "JAvA"
"Java".replace('A', 'x');     // "Java" (không có 'A')
```

Những dòng trên là **các biểu thức minh họa**, chưa tạo thành file Java độc lập. Trong Java, một literal `char` có đúng một đơn vị mã UTF-16; `'a'` là `char`, còn `"a"` là `String`. Việc truyền hai `String` vào `replace("a","o")` vẫn hợp lệ, nhưng Java chọn **overload nhận `CharSequence`**, không phải overload đang học.

Phương thức không nhận tham số `boolean` điều khiển số lần thay và không có phiên bản `replace(char,char,int limit)` trong `String`. Nếu chỉ muốn thay lần đầu tiên hoặc thay một vùng, cần chọn thuật toán/API khác.

## 3. Chương trình đầy đủ: tất cả vị trí khớp đều được thay

Lưu thành `ReplaceCharDemo.java`:

```java
public class ReplaceCharDemo {
    public static void main(String[] args) {
        String original = "banana";
        String changed = original.replace('a', 'o');

        System.out.println(original);
        System.out.println(changed);
        System.out.println("aaaa".replace('a', 'b'));
        System.out.println("aba".replace('a', 'b'));
        System.out.println("a.b.a".replace('.', '-'));
        System.out.println("a$a$a".replace('$', '#'));
        System.out.println("Java".replace('x', 'y'));
        System.out.println("Java".replace('a', 'a'));
        System.out.println("Java".replace('a', 'A'));
        System.out.println("Java".replace('A', 'x'));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac -encoding UTF-8 ReplaceCharDemo.java
java ReplaceCharDemo
```

Kết quả chuẩn:

```text
banana
bonono
bbbb
bbb
a-b-a
a#a#a
Java
Java
JAvA
Java
```

Giải thích:
- `original` vẫn là `banana`; biến `changed` giữ kết quả `bonono`.
- `"aaaa".replace('a','b')` thay cả bốn vị trí, và `"aba".replace('a','b')` cho `bbb`, không chỉ thay chữ `a` đầu tiên.
- Dấu `'.'` và `'$'` được xem như ký tự bình thường. Chúng **không mang ý nghĩa regex** trong overload `char,char`.
- Không có `'x'` trong `Java` nên nội dung giữ nguyên. `oldChar == newChar` cũng không làm nội dung thay đổi.
- Phép thay phân biệt hoa/thường: chữ `a` trong `Java` khớp, chữ `A` không có trong `Java`.

## 4. Tại sao đây là thao tác đồng thời theo nội dung nguồn?

Điều kiện khớp được xét theo **chuỗi nguồn ban đầu** trong một lần gọi. Ký tự vừa được thay vào không được xem là mục tiêu mới để “thay dây chuyền” ngay trong chính lần gọi đó.

Ví dụ:

```java
System.out.println("aba".replace('a', 'b')); // bbb
```

Từ `aba`, hai vị trí `a` được thay bằng `b`; chữ `b` gốc vẫn là `b`. Không có một bước thứ hai trong lần gọi này để tiếp tục xử lý các chữ `b`. Do đó kết quả là `bbb`.

Tuy nhiên, **nối nhiều lần gọi `replace`** là một chuỗi các phép biến đổi khác nhau; phép sau nhìn thấy kết quả của phép trước:

```java
System.out.println(
        "aba".replace('a', 'b').replace('b', 'c')); // ccc
System.out.println(
        "aba".replace('b', 'c').replace('a', 'b')); // bcb
```

Đây là snippet đặt trong `main`. Ở dòng đầu, `aba` thành `bbb`, rồi toàn bộ `b` thành `c`. Dòng sau bắt đầu bằng `aca`, rồi thay `a` bằng `b` để thành `bcb`. **Thứ tự các lời gọi quan trọng**; không được giả định hai phép thay ký tự luôn giao hoán.

Nếu muốn thực hiện đồng thời một bảng chuyển đổi nhiều ký tự khác nhau mà không để ký tự mới bị xử lý bởi quy tắc tiếp theo, có thể duyệt chuỗi nguồn một lần, quyết định ký tự thay thế cho từng vị trí và xây dựng kết quả riêng. Không nên ghép các lời gọi `replace` khi phép thay thứ hai không được phép ảnh hưởng ký tự mà phép thứ nhất vừa tạo ra.

## 5. `String` bất biến: kết quả phải được giữ lại

Một lỗi thường gặp:

```java
String text = "banana";
text.replace('a', 'o'); // Có tính kết quả, nhưng kết quả bị bỏ qua.
System.out.println(text); // banana
```

`replace` **không sửa** đối tượng `String` mà `text` đang trỏ tới. Để sử dụng nội dung sau khi thay:

```java
String text = "banana";
text = text.replace('a', 'o');
System.out.println(text); // bonono
```

Lệnh gán sau đó chỉ khiến **biến** `text` tham chiếu tới kết quả; chuỗi bất biến `"banana"` ban đầu không bị đổi nội dung. Nếu có biến khác vẫn trỏ tới chuỗi cũ, biến đó tiếp tục thấy `banana`.

Trường hợp ký tự cần tìm không xuất hiện, tài liệu `String.replace(char,char)` cho phép trả về tham chiếu tới chính `String` đã gọi. Vì vậy **không được suy luận rằng một lời gọi `replace` lúc nào cũng cấp phát một đối tượng mới**. Điều được cam kết ở mức lập trình là **nội dung kết quả** và **tính bất biến**. Để so chuỗi, dùng `equals`, không dùng `==` nhằm phỏng đoán có diễn ra thay thế hay không.

Một biến `final String` không được gán lại:

```java
final String text = "banana";
String changed = text.replace('a', 'o'); // Hợp lệ.
// text = changed; // Lỗi biên dịch: không thể gán lại biến final.
```

Đây là snippet minh họa. `final` của biến ngăn gán lại tham chiếu, còn tính bất biến của `String` ngăn sửa nội dung đối tượng; đó là hai khái niệm khác nhau.

## 6. Chọn đúng API khi thao tác với một `char`

`String` có nhiều dạng thay thế. Bài này dùng **`replace(char,char)`** khi đầu vào và đầu ra đều là *một đơn vị UTF-16*; hai đối số trong dấu nháy đơn được xử lý như ký tự nguyên văn. Ba lựa chọn gần tên có mục đích khác:

| API | Điều được tìm | Số lần thay |
| --- | --- | --- |
| `replace(char, char)` | Một `char` chính xác | Tất cả vị trí khớp |
| `replace(CharSequence, CharSequence)` | Đoạn chuỗi literal, có thể dài hơn một `char` | Tất cả lần khớp không chồng lấn |
| `replaceFirst(String, String)` | Regex | Match đầu tiên |
| `replaceAll(String, String)` | Regex | Tất cả match |

Ví dụ đặt trong `main`:

~~~java
System.out.println("a.b".replace('.', '/'));      // a/b
System.out.println("a.b".replace(".", "/"));      // a/b
System.out.println("a.b".replaceAll(".", "/"));   // ///
System.out.println("a.b".replaceFirst(".", "/")); // /.b
~~~

Với regex, dấu `.` có nghĩa đặc biệt; với cả hai overload `replace`, nó chỉ là dấu chấm. `replaceAll` và `replaceFirst` còn diễn giải `$1` và backslash trong chuỗi replacement theo cú pháp regex, còn `replace` chèn replacement nguyên văn. Nếu chỉ đổi dấu phân cách đơn lẻ, overload `char,char` thể hiện đúng ý định nhất; bài so sánh ba API ở phần sau của chương đi sâu vào nhóm bắt, escape và lựa chọn regex.

## 7. Khi nào nên chọn `replace(char,char)`?

Chọn overload `char,char` khi:
- Mục tiêu là **đúng một** đơn vị UTF-16 có giá trị cố định hoặc được truyền qua biến `char`.
- Muốn thay **mọi** vị trí khớp một cách trực tiếp, ví dụ đổi dấu phân cách `','` thành `';'` hoặc đổi khoảng trắng ASCII `' '` thành `'_'`.
- Không cần regex, capture group, kiểm tra nhiều ký tự liên tiếp hay giới hạn số lần thay.
- Muốn kết quả vẫn có cùng số đơn vị UTF-16 với nguồn (vì mỗi `char` được thay bằng đúng một `char`).

Một ứng dụng thông dụng là chuẩn hóa dấu phân tách theo đúng ký tự được biết trước:

```java
String csvLike = "red,green,blue";
String separated = csvLike.replace(',', ';');
System.out.println(separated); // red;green;blue
```

Đây là snippet trong `main`. Phép thay không hiểu cú pháp CSV: nếu dấu phẩy nằm trong trường được đặt trong dấu nháy kép, thay tất cả dấu phẩy bằng dấu chấm phẩy có thể phá cấu trúc dữ liệu. Hãy dùng parser CSV nếu cần hiểu ngữ nghĩa định dạng.

Tương tự, `replace(' ', '_')` chỉ thay **dấu cách U+0020**; nó không thay mọi dạng whitespace như tab, xuống dòng, non-breaking space. Nếu cần quy tắc dựa trên lớp ký tự, hãy chọn regex Unicode phù hợp hoặc xử lý code point rõ ràng.

## 8. Phạm vi khớp: phân biệt hoa/thường, dấu và Unicode

`replace(char,char)` so khớp **chính xác từng `char`**. Nó không biết hai chữ là biến thể hoa/thường hay dấu tiếng Việt của cùng một chữ cơ sở:

```java
System.out.println("Java".replace('a', 'o')); // Jovo
System.out.println("Java".replace('A', 'o')); // Java
System.out.println("café".replace('é', 'e')); // cafe
```

Đây là snippet minh họa. Chữ `é` dạng tiền tổ hợp là một mã Unicode thuộc BMP, có thể chứa trong một `char`. Nhưng Unicode cũng cho phép biểu diễn chữ có dấu bằng **chữ cơ sở + dấu kết hợp**; hai cách biểu diễn có thể nhìn giống nhau nhưng dữ liệu `char` khác nhau.

Chương trình độc lập, lưu `ReplaceUnicodeFormDemo.java`:

```java
public class ReplaceUnicodeFormDemo {
    public static void main(String[] args) {
        String composed = "caf\u00E9";       // café: U+00E9
        String decomposed = "cafe\u0301";    // e + dấu sắc U+0301

        System.out.println(composed.replace('\u00E9', 'e'));
        System.out.println(decomposed.replace('\u00E9', 'e')
                .equals(decomposed));
        System.out.println(composed.equals(decomposed));
    }
}
```

```bash
javac -encoding UTF-8 ReplaceUnicodeFormDemo.java
java ReplaceUnicodeFormDemo
```

```text
cafe
true
false
```

Vì `decomposed` **không chứa phần tử `char` có giá trị U+00E9**, thay `'é'` không tác động gì lên chuỗi đó. Nếu nghiệp vụ cần xử lý các cách biểu diễn Unicode tương đương, cân nhắc chuẩn hóa bằng `java.text.Normalizer` trước khi áp dụng quy tắc thay; chọn dạng chuẩn hóa phù hợp và hiểu rằng chuẩn hóa cũng có thể làm thay đổi dãy code point.

## 9. `char` là đơn vị UTF-16, không phải mọi ký tự hiển thị

Java `char` có kích thước 16 bit, chứa **một code unit UTF-16**. Các Unicode code point ngoài BMP (ví dụ nhiều emoji) cần **hai** `char`: high surrogate và low surrogate. Một literal `char` không thể biểu diễn **toàn bộ** emoji như `🙂` bằng một giá trị `char` duy nhất.

Giả sử chuỗi có hai emoji:

```java
String emoji = "A🙂B🙂";
System.out.println(emoji.length()); // 6 đơn vị char
System.out.println(emoji.codePointCount(0, emoji.length())); // 4 code point
```

Không thể dùng `emoji.replace('🙂', '*')` như một cách thay nguyên emoji: ký tự emoji ngoài BMP không vừa trong một literal `char`. Hãy chọn overload nhận chuỗi để tìm đủ cả cặp surrogate:

```java
String result = emoji.replace("🙂", "*");
System.out.println(result); // A*B*
```

Chương trình hoàn chỉnh, lưu `ReplaceEmojiDemo.java`:

```java
public class ReplaceEmojiDemo {
    public static void main(String[] args) {
        String text = "A🙂B🙂";

        System.out.println(text.length());
        System.out.println(text.codePointCount(0, text.length()));
        System.out.println(text.replace("🙂", "*"));
        System.out.println(text.replace('A', 'X'));
        System.out.println(text);
    }
}
```

```bash
javac -encoding UTF-8 ReplaceEmojiDemo.java
java ReplaceEmojiDemo
```

```text
6
4
A*B*
X🙂B🙂
A🙂B🙂
```

Phép `replace("🙂", "*")` thay cả **đoạn chuỗi** gồm hai code unit; `replace('A','X')` chỉ thay code unit `A` đơn lẻ. Cả hai không sửa `text`.

**Nguy cơ với surrogate:** nếu gọi `replace(char,char)` lên riêng high surrogate hoặc low surrogate của một code point ngoài BMP, có thể phá cặp UTF-16 hợp lệ và tạo dãy surrogate lẻ. Khi cần biến đổi theo Unicode code point, dùng `String.codePoints()` và `StringBuilder.appendCodePoint()` hoặc phương thức xử lý chuỗi có ranh giới đúng; khi yêu cầu là “một ký tự người đọc thấy”, còn phải cân nhắc *grapheme cluster* (ví dụ chữ có dấu kết hợp hay emoji nối bằng ZWJ).

## 10. Viết hàm nhận `char` làm tham số và quản lý kết quả

Một hàm hỗ trợ thay ký tự có thể rất ngắn:

```java
import java.util.Objects;

public class ReplaceUtility {
    public static String replaceEvery(
            String input, char from, char to) {
        Objects.requireNonNull(input, "input");
        return input.replace(from, to);
    }

    public static void main(String[] args) {
        String original = "a-a-a";
        String updated = replaceEvery(original, '-', '_');

        System.out.println(updated);
        System.out.println(original);
    }
}
```

Lưu thành `ReplaceUtility.java` rồi chạy:

```bash
javac -encoding UTF-8 ReplaceUtility.java
java ReplaceUtility
```

```text
a_a_a
a-a-a
```

`Objects.requireNonNull` giúp báo lỗi rõ tại ranh giới hàm khi `input` là `null`; bản thân lời gọi `input.replace(...)` cũng không thể hoạt động nếu `input` là `null`. Hai tham số `char` là giá trị nguyên thủy nên không có giá trị `null`. Hàm trả một chuỗi mới về **giá trị**; các tham chiếu khác tới `original` tiếp tục thấy nội dung gốc.

Có thể truyền biến `char` thay cho literal:

```java
char delimiter = ',';
char newDelimiter = ';';
String converted = "a,b,c".replace(delimiter, newDelimiter);
// converted có nội dung "a;b;c".
```

Đây là snippet độc lập về biểu thức nhưng cần đặt vào thân phương thức Java. Nếu hệ thống cần lựa chọn ký tự tùy ý từ người dùng, kiểm tra rằng giá trị đầu vào có đúng **một đơn vị UTF-16** trước khi chuyển thành `char`; đừng dùng `input.charAt(0)` rồi lặng lẽ bỏ phần còn lại của một chuỗi có nhiều code unit.

## 11. Chi phí, nhiều phép thay và chọn công cụ phù hợp

Về mặt thuật toán, để xác định tất cả vị trí khớp, Java phải xem xét nội dung chuỗi cần xử lý. Với một lần thay trên chuỗi dài `n` code unit, có thể coi chi phí quét là **O(n)**; việc tạo kết quả và tối ưu cấp phát phụ thuộc phiên bản/cài đặt JDK. Không dựa vào giả định `replace` luôn tạo đối tượng mới, cũng không dùng so sánh tham chiếu để đo xem có thay thế.

Khi cần **nhiều loại chuyển đổi liên tiếp**, mã như sau dễ hiểu nhưng mỗi lần gọi là một phép xử lý độc lập:

```java
String normalized = "a.b-c".replace('.', '_').replace('-', '_');
// normalized: "a_b_c"
```

Đối với lượng dữ liệu rất lớn và rất nhiều quy tắc ký tự, bạn có thể duyệt một lần rồi ghi vào `StringBuilder` hoặc mảng, tránh quét lặp; lựa chọn theo độ phức tạp thực tế và đo hiệu năng. Ví dụ, nếu nhiều ký tự nguồn khác nhau đều cần được thay thành `'_'`, một vòng lặp `switch` trên từng `char` có thể biểu diễn phép thay đồng thời rõ hơn; với Unicode phức tạp, thay vì duyệt từng `char` hãy xem xét duyệt code point.

Đừng tự tối ưu quá sớm: `replace(char,char)` ngắn gọn, dễ đọc, truyền tải rõ ý định và thường phù hợp cho các phép thay ký tự đơn lẻ.

## 12. Các lỗi thường gặp

| Lỗi | Vì sao sai | Cách sửa |
| --- | --- | --- |
| Gọi `text.replace('a','o')` rồi bỏ kết quả | `String` bất biến; biến `text` không đổi | Gán lại `text = text.replace(...)` hoặc giữ biến kết quả |
| Tưởng chỉ thay lần xuất hiện đầu tiên | `replace(char,char)` thay **tất cả** vị trí khớp | Dùng thuật toán thay lần đầu nếu đó là yêu cầu |
| Dùng `replaceAll(".", "_")` để tìm dấu chấm literal | `.` trong regex khớp nhiều ký tự | Dùng `replace('.', '_')` hoặc `replace(".", "_")` |
| Tưởng `'a'` và `'A'` là cùng ký tự | Phương thức so khớp chính xác | Áp dụng chính sách hoa/thường riêng nếu cần |
| Dùng `char` cho emoji ngoài BMP | Một emoji có thể cần hai đơn vị UTF-16 | Dùng overload `replace(CharSequence,CharSequence)` với chuỗi đầy đủ |
| Giả định `'é'` khớp mọi cách viết chữ e có dấu | Dữ liệu Unicode có thể tiền tổ hợp hoặc kết hợp | Chuẩn hóa Unicode nếu yêu cầu |
| Ghép nhiều `replace` nhưng muốn xử lý đồng thời | Phép sau xử lý cả ký tự do phép trước tạo ra | Viết phép ánh xạ từng vị trí theo nguồn gốc |
| Kiểm tra `result == original` để biết có thay | `==` kiểm tra identity, không phải nội dung | Dùng `equals` hoặc so nội dung theo yêu cầu |
| Cho rằng `replace(' ', '_')` thay mọi whitespace | Chỉ thay space U+0020 | Chọn xử lý whitespace theo đặc tả |
| Dùng thay ký tự đơn để xử lý định dạng có cú pháp | Không hiểu dấu nháy/escape/grammar của CSV, URL, JSON... | Dùng parser/encoder tương ứng |
| Phá cặp surrogate bằng cách thay một nửa | `char` không luôn là code point hoàn chỉnh | Chuyển đổi theo code point hoặc chuỗi hoàn chỉnh |

## 13. Bài tập tự kiểm tra

**Bài 1.** Với `String s = "aAaA";`, kết quả của `s.replace('a','x')` là gì? Vì sao hai chữ `A` giữ nguyên?

**Bài 2.** Dự đoán kết quả:
```java
String value = "abba";
String result = value.replace('a', 'b');
System.out.println(value);
System.out.println(result);
```

**Bài 3.** Vì sao `"a.b".replace('.', '_')` và `"a.b".replaceAll(".", "_")` cho hai kết quả khác nhau?

**Bài 4.** Nếu cần đổi mọi đoạn `"cat"` thành `"dog"` trong `"cat-cat"`, bạn sẽ dùng overload nào? Vì sao `replace(char,char)` không đáp ứng trực tiếp?

**Bài 5.** Với `String source = "A🙂A";`, hãy giải thích tại sao `replace('A','X')` hoạt động như mong đợi, còn thay emoji bằng một literal `char` không phải lựa chọn hợp lệ.

Đáp án:
- Bài 1: `"xAxA"` vì `'a'` khác `'A'`.
- Bài 2: in `abba` rồi `bbbb`; mảng ký tự không liên quan, đây là hai giá trị `String` bất biến.
- Bài 3: `replace` theo `char` tìm đúng dấu chấm nên ra `a_b`; regex `.` của `replaceAll` khớp ba ký tự nên ra `___`.
- Bài 4: `"cat-cat".replace("cat", "dog")` cho `"dog-dog"`; cần thay cả một đoạn ba `char` bằng đoạn khác.
- Bài 5: `A` là một đơn vị UTF-16; emoji `🙂` cần một cặp surrogate, phải thay bằng chuỗi `"🙂"` hoặc xử lý code point.

## 14. Ghi nhớ

- `String.replace(char oldChar, char newChar)` thay **mọi `char` trùng `oldChar`** trong chuỗi, không dùng regex và không giới hạn ở lần đầu.
- Kết quả là một `String`; nội dung chuỗi nguồn vẫn bất biến. Muốn dùng kết quả, **giữ giá trị trả về**.
- `char` biểu diễn một đơn vị UTF-16. Chọn đúng overload theo đơn vị cần thay: `char` đơn lẻ, đoạn `CharSequence` literal hay một mẫu regex.
- Phép so khớp là chính xác, có phân biệt hoa/thường và biểu diễn Unicode; nếu yêu cầu nghiệp vụ khác, phải định nghĩa rõ cách chuẩn hóa/xử lý.
- Nhiều lời gọi `replace` liên tiếp được thực hiện theo thứ tự; phép sau nhìn thấy kết quả phép trước.

## Tài liệu Java SE 17

- [`String.replace(char,char)`, `replace(CharSequence,CharSequence)` và `replaceAll` — Oracle Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html)
- [`Character`, UTF-16 và surrogate — Oracle Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html)
- [`Normalizer` — Oracle Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html)
