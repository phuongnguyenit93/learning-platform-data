# StringBuffer.repeat và lựa chọn cấu trúc chuỗi phù hợp

Java 21 bổ sung hai overload `repeat(...)` cho `StringBuffer` và `StringBuilder`, giúp nối lặp một Unicode code point hoặc một `CharSequence` vào buffer mà không cần tự viết vòng lặp `append`. Việc chọn `String`, `StringBuilder`, `StringBuffer` hay `StringJoiner` vẫn phụ thuộc vào mục đích: chuỗi bất biến, dựng chuỗi có thể thay đổi, chia sẻ buffer giữa nhiều thread hay ghép nhiều giá trị bằng dấu phân cách.

`StringBuffer.repeat(...)` sửa chính buffer hiện tại và trả lại chính buffer đó để có thể nối chuỗi lệnh. Hai overload nhận `int codePoint` và `CharSequence` có ý nghĩa khác nhau. Khi làm việc với Unicode, cần nhớ code point không đồng nghĩa với ký tự hiển thị (grapheme cluster), còn `StringBuffer.length()` đếm đơn vị UTF-16 chứ không đếm số code point.

## 1. StringBuffer.repeat có từ Java 21

Java 21 cung cấp hai phương thức:

```java
StringBuffer repeat(int codePoint, int count)
StringBuffer repeat(CharSequence cs, int count)
```

- `repeat(int codePoint, int count)`: nối `count` lần code point được chỉ định vào buffer.
- `repeat(CharSequence cs, int count)`: nối `count` lần toàn bộ chuỗi ký tự `cs` vào buffer.
- `count == 0`: không thêm nội dung.
- `count < 0`: ném `IllegalArgumentException`.
- Overload nhận `CharSequence` không chấp nhận `null`; truyền `null` sẽ gây `NullPointerException`.
- Overload nhận code point yêu cầu một code point hợp lệ; giá trị không hợp lệ gây `IllegalArgumentException`.

Hai phương thức sửa đổi đối tượng `StringBuffer` hiện tại và trả về tham chiếu đến buffer đó. Chúng không tạo một `StringBuffer` mới cho kết quả.

## 2. Dùng repeat(int codePoint, int count)

Overload nhận `int` phù hợp khi muốn lặp một Unicode code point, chẳng hạn dấu chấm, ký tự trang trí hoặc emoji:

```java
public class RepeatCodePointDemo {
    public static void main(String[] args) {
        StringBuffer output = new StringBuffer();

        output.append("Loading");
        output.repeat('.', 3);

        System.out.println(output); // Loading...

        StringBuffer rockets = new StringBuffer();
        rockets.repeat(0x1F680, 3); // U+1F680: ROCKET

        System.out.println(rockets); // 🚀🚀🚀
        System.out.println(rockets.length());
        System.out.println(rockets.codePointCount(0, rockets.length()));
    }
}
```

Kết quả với ba emoji rocket:

```text
🚀🚀🚀
6
3
```

Rocket nằm ngoài Basic Multilingual Plane nên mỗi code point được mã hóa bằng một cặp surrogate UTF-16. Vì vậy, ba code point chiếm sáu `char` trong buffer. `length()` trả về số đơn vị UTF-16; `codePointCount(...)` đếm số code point trong đoạn chỉ định.

Có thể truyền một `char` như `'.'` vào overload `int` vì `char` được mở rộng thành `int`. Với ký tự supplementary như emoji, dùng giá trị code point dạng `int` hoặc `Character` API phù hợp; không thể biểu diễn một code point supplementary bằng một `char` đơn lẻ.

## 3. Dùng repeat(CharSequence cs, int count)

Overload nhận `CharSequence` lặp toàn bộ chuỗi được truyền vào. Dùng nó khi đơn vị cần lặp gồm nhiều code point hoặc nhiều đơn vị UTF-16:

```java
public class RepeatSequenceDemo {
    public static void main(String[] args) {
        StringBuffer line = new StringBuffer("+");
        line.repeat("-", 20);
        line.append('+');

        System.out.println(line); // +--------------------+

        StringBuffer family = new StringBuffer();
        String familyEmoji = "👨‍👩‍👧‍👦";
        family.repeat(familyEmoji, 2);

        System.out.println(family);
    }
}
```

Chuỗi emoji gia đình chứa nhiều code point được nối bằng Zero Width Joiner (ZWJ). Lặp cả `CharSequence` giúp giữ nguyên chuỗi code point đó trong mỗi lần lặp. Nếu chỉ lặp một code point riêng lẻ, kết quả có thể không còn là một ký tự hiển thị giống ban đầu.

Một ví dụ khác là chữ `e` kết hợp dấu sắc dạng combining mark:

```java
String decomposed = "e\u0301"; // e + COMBINING ACUTE ACCENT

StringBuffer text = new StringBuffer();
text.repeat(decomposed, 3);

System.out.println(text); // ééé
```

Ở đây, `repeat(decomposed, 3)` lặp cả chuỗi gồm chữ cái và dấu kết hợp. `repeat('e', 3)` chỉ lặp chữ `e`, không tự thêm combining mark.

## 4. Code point không phải lúc nào cũng là một ký tự hiển thị

Unicode có nhiều khái niệm cần phân biệt:

- **UTF-16 code unit:** một giá trị `char` 16 bit trong Java. `String.length()` và `StringBuffer.length()` trả về số code unit.
- **Code point:** một giá trị trong không gian mã Unicode. Một code point có thể chiếm một hoặc hai code unit UTF-16.
- **Grapheme cluster:** đơn vị văn bản mà người dùng thường cảm nhận là một ký tự hiển thị. Một grapheme cluster có thể gồm nhiều code point, chẳng hạn chữ cái và dấu kết hợp hoặc chuỗi emoji có ZWJ.

Do đó, `repeat(int codePoint, count)` lặp code point, không lặp một grapheme cluster tổng quát. Nếu cần lặp nguyên một ký tự hiển thị được tạo từ nhiều code point, hãy truyền cả chuỗi dưới dạng `CharSequence`.

| Dữ liệu | Số code point | Số UTF-16 code unit (thường gặp) | Cách lặp phù hợp |
|---|---:|---:|---|
| `A` | 1 | 1 | `repeat('A', count)` |
| `🚀` | 1 | 2 | `repeat(0x1F680, count)` |
| `e` + combining acute accent | 2 | 2 | `repeat("e\u0301", count)` |
| Emoji gia đình có ZWJ | Nhiều | Nhiều | `repeat(familySequence, count)` |

Không nên dùng `charAt(index)` hoặc lặp từng `char` nếu mục tiêu là xử lý code point Unicode tổng quát; thao tác đó có thể tách một cặp surrogate. Với xử lý theo code point, dùng `codePointAt`, `codePoints`, `Character.charCount` và các API tương ứng.

## 5. repeat trên StringBuffer và StringBuilder

`StringBuffer` và `StringBuilder` đều là chuỗi có thể thay đổi, và Java 21 có `repeat(...)` trên cả hai. Điểm khác biệt chính là đồng bộ hóa:

| Đặc điểm | String | StringBuilder | StringBuffer |
|---|---|---|---|
| Có thể thay đổi nội dung sau khi tạo? | Không | Có | Có |
| `repeat(...)` trên chính đối tượng? | Không; `String.repeat(int)` trả về String mới | Có | Có |
| Đồng bộ hóa các phương thức instance? | Không áp dụng vì bất biến | Không | Có |
| Trường hợp dùng thường gặp | Giá trị chuỗi bất biến | Dựng chuỗi trong một thread hoặc một tác vụ | Buffer mutable được chia sẻ giữa nhiều thread khi cần đồng bộ ở từng thao tác |

Ví dụ cùng một thao tác với `StringBuilder`:

```java
StringBuilder builder = new StringBuilder("ID-");
builder.repeat('0', 5);
builder.append(42);

System.out.println(builder); // ID-0000042
```

Nếu buffer chỉ được một thread sử dụng, `StringBuilder` thường là lựa chọn phù hợp. Nếu thật sự cần một buffer mutable được nhiều thread truy cập, `StringBuffer` cung cấp đồng bộ hóa ở cấp phương thức. Tuy nhiên, điều đó không tự làm cho một chuỗi nhiều lời gọi trở thành một thao tác nguyên tử.

Ví dụ, hai thread có thể xen kẽ giữa `append("A")` và `append("B")`; mỗi lời gọi riêng được đồng bộ nhưng cả cặp không được bảo đảm chạy liền nhau. Nếu cần một nhóm thao tác không bị xen kẽ, hãy đồng bộ trên cùng buffer:

```java
synchronized (buffer) {
    buffer.append("prefix-");
    buffer.repeat('.', 3);
    buffer.append("-suffix");
}
```

Trong ứng dụng thực tế, thường dễ quản lý hơn nếu mỗi tác vụ dựng chuỗi trong buffer riêng rồi chuyển kết quả thành `String` bất biến để chia sẻ.

## 6. Phân biệt String.repeat và StringBuffer.repeat

`String.repeat(int count)` đã có từ Java 11. Nó trả về một `String` mới chứa chuỗi ban đầu được lặp lại; nó không sửa đổi chuỗi ban đầu. `StringBuffer.repeat(...)` được bổ sung ở Java 21 và nối trực tiếp vào buffer mutable.

```java
String token = "ab";
String repeated = token.repeat(3);

System.out.println(repeated); // ababab
System.out.println(token);    // ab

StringBuffer buffer = new StringBuffer("prefix-");
buffer.repeat(token, 3);

System.out.println(buffer);   // prefix-ababab
```

Chọn theo kết quả cần nhận:

- Đã có một `String` và muốn tạo một `String` lặp: dùng `String.repeat(count)`.
- Đang dựng một chuỗi lớn bằng nhiều thao tác append/repeat: dùng `StringBuilder` hoặc `StringBuffer` phù hợp với yêu cầu đồng bộ.
- Chỉ cần thêm một đoạn lặp vào buffer đang có: dùng `buffer.repeat(...)`.

Không cần chuyển mọi lời gọi `String.repeat` thành `StringBuffer`. Nếu kết quả cần là một giá trị bất biến và chỉ có một phép lặp, `String.repeat` diễn đạt đúng mục tiêu.

## 7. Khi nào dùng StringJoiner hoặc String.join?

`repeat` dùng để lặp nội dung giống nhau. Khi cần ghép nhiều phần tử với dấu phân cách, `StringJoiner`, `String.join` hoặc `Collectors.joining` phù hợp hơn.

```java
import java.util.StringJoiner;

StringJoiner joiner = new StringJoiner(", ", "[", "]");
joiner.add("Java");
joiner.add("Unicode");
joiner.add("Strings");

System.out.println(joiner); // [Java, Unicode, Strings]
```

Hoặc ghép một tập hợp chuỗi:

```java
String languages = String.join(" | ", "Java", "Kotlin", "Scala");
System.out.println(languages); // Java | Kotlin | Scala
```

Không dùng `repeat` để mô phỏng việc ghép danh sách có các phần tử khác nhau. Hãy chọn API phản ánh đúng cấu trúc dữ liệu và dấu phân cách cần tạo.

## 8. Xử lý count, capacity và dữ liệu đầu vào

Lặp một chuỗi rất dài nhiều lần có thể làm buffer tăng kích thước đáng kể. Trước khi gọi `repeat`, hãy xác thực count và giới hạn kích thước đầu ra nếu giá trị đến từ request hoặc file bên ngoài.

Ví dụ, kiểm tra số lần lặp và ước lượng kích thước theo UTF-16 code unit:

```java
static StringBuffer repeatWithLimit(String text, int count, int maxChars) {
    if (text == null) {
        throw new NullPointerException("text");
    }
    if (count < 0) {
        throw new IllegalArgumentException("count must not be negative");
    }

    long requiredChars = (long) text.length() * count;
    if (requiredChars > maxChars) {
        throw new IllegalArgumentException("Output is too large");
    }

    StringBuffer buffer = new StringBuffer((int) requiredChars);
    return buffer.repeat(text, count);
}
```

Phép nhân được thực hiện bằng `long` để tránh tràn số nguyên khi ước lượng kích thước. `maxChars` là giới hạn nghiệp vụ do ứng dụng chọn; nó không phải giới hạn chung của Java. Việc cấp phát vẫn có thể thất bại nếu bộ nhớ không đủ, vì vậy không nên xem kiểm tra độ dài là bảo đảm rằng cấp phát sẽ thành công.

Khi biết trước kích thước đầu ra, truyền capacity ban đầu phù hợp có thể giảm số lần mở rộng buffer. Không đặt capacity cực lớn chỉ để tránh mở rộng; điều đó có thể giữ nhiều bộ nhớ hơn cần thiết. Với dữ liệu người dùng, giới hạn count và tổng kích thước trước khi dựng chuỗi để tránh tiêu thụ bộ nhớ ngoài dự kiến.

## 9. Lỗi thường gặp

| Vấn đề | Nguyên nhân | Cách xử lý |
|---|---|---|
| `IllegalArgumentException` khi gọi repeat | Count âm hoặc code point không hợp lệ | Kiểm tra đầu vào trước khi gọi |
| `NullPointerException` với overload CharSequence | Đối số `cs` là null | Xác định chính sách null và kiểm tra trước |
| Emoji bị đếm nhiều hơn số lần lặp | `length()` đếm UTF-16 code unit, không đếm code point | Dùng `codePointCount(...)` khi cần đếm code point |
| Dấu kết hợp hoặc emoji hiển thị không như mong đợi | Chỉ lặp một code point trong khi ký tự hiển thị gồm nhiều code point | Lặp toàn bộ `CharSequence` đại diện cho grapheme cluster |
| Dùng StringBuffer nhưng thao tác ghép vẫn xen kẽ | Đồng bộ từng method không bảo đảm một chuỗi method call là atomic | Đồng bộ trên cùng buffer quanh nhóm thao tác hoặc dùng buffer riêng cho mỗi task |
| Dùng StringBuffer trong code một thread mà không có lý do | Chọn cấu trúc có đồng bộ hóa không cần thiết | Ưu tiên StringBuilder nếu buffer chỉ thuộc một thread |
| Bộ nhớ tăng mạnh khi repeat | Count hoặc nội dung lặp quá lớn | Đặt giới hạn đầu ra, kiểm tra kích thước và đo mức cấp phát |

## 10. Checklist chọn cấu trúc chuỗi

- Dùng `String` cho giá trị bất biến, dễ chia sẻ và truyền giữa các thành phần.
- Dùng `String.repeat(count)` khi cần tạo một String lặp từ String có sẵn.
- Dùng `StringBuilder` để dựng chuỗi mutable trong một thread hoặc một tác vụ riêng.
- Dùng `StringBuffer` khi cần buffer mutable có đồng bộ ở từng phương thức; đồng bộ thêm nếu một nhóm lời gọi phải nguyên tử.
- Dùng `repeat(int codePoint, count)` khi muốn lặp một code point Unicode.
- Dùng `repeat(CharSequence, count)` khi đơn vị cần lặp có thể chứa nhiều code point, combining marks hoặc ZWJ.
- Phân biệt UTF-16 code unit, code point và grapheme cluster khi đo độ dài hoặc xử lý ký tự hiển thị.
- Dùng `StringJoiner` hoặc `String.join` để ghép các phần tử khác nhau bằng delimiter.
- Kiểm tra count, null và giới hạn kích thước trước khi dựng chuỗi lớn từ dữ liệu bên ngoài.
- Chỉ tối ưu capacity hoặc chọn cấu trúc theo hiệu năng sau khi đã xác định workload và đo đạc phù hợp.

`StringBuffer.repeat` giúp diễn đạt việc nối lặp trực tiếp trên buffer, còn lựa chọn giữa `String`, `StringBuilder`, `StringBuffer` và `StringJoiner` phụ thuộc vào tính bất biến, khả năng sửa đổi, chia sẻ giữa thread và hình thức dữ liệu cần ghép. Với Unicode, hãy chọn overload theo đơn vị muốn lặp: một code point hay cả chuỗi code point tạo nên nội dung hiển thị.
