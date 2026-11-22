# `==` so sánh tham chiếu, còn `equals()` so sánh nội dung `String`

Trong Java, hai biến `String` có thể lưu những chuỗi ký tự **giống hệt nhau** nhưng vẫn tham chiếu tới **hai đối tượng khác nhau**. Vì vậy, biểu thức `a == b` và `a.equals(b)` trả lời hai câu hỏi khác nhau:

- **`a == b`**: hai biến tham chiếu có đang trỏ đến **cùng một đối tượng** hay không?
- **`a.equals(b)`**: theo hợp đồng của lớp `String`, hai đối tượng có chứa **cùng dãy ký tự UTF-16** hay không?

Khi kiểm tra tên, mã, trạng thái, nội dung nhập từ người dùng hoặc chuỗi đọc từ API, **hầu như luôn dùng `equals()` cho so sánh nội dung**. Dùng `==` khi thật sự muốn biết hai tham chiếu có cùng đối tượng, hoặc khi so sánh tham chiếu với `null`.

## 1. Phân biệt “cùng đối tượng” với “cùng giá trị”

Đoạn mã sau minh họa trực tiếp:

```java
String a = new String("Java");
String b = new String("Java");

System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
```

Hai lời gọi `new String("Java")` tạo hai đối tượng `String` riêng biệt, dù các đối tượng cùng chứa nội dung `"Java"`.

Hãy hình dung:

```text
Biến a ───────► String object #1: "Java"
Biến b ───────► String object #2: "Java"

a == b       → false  (hai đối tượng khác nhau)
a.equals(b)  → true   (nội dung giống nhau)
```

Ngược lại, nếu gán tham chiếu:

```java
String a = new String("Java");
String b = a;

System.out.println(a == b);      // true
System.out.println(a.equals(b)); // true
```

Lúc này `a` và `b` cùng trỏ đến một đối tượng. Vì thế `==` trả về `true`, và dĩ nhiên nội dung cũng bằng nhau.

| Tình huống | `a == b` | `a.equals(b)` khi `a != null` |
| --- | --- | --- |
| Hai biến cùng trỏ tới một `String` | `true` | `true` |
| Hai đối tượng `String` khác nhau nhưng cùng nội dung | `false` | `true` |
| Hai đối tượng `String` có nội dung khác nhau | `false` | `false` |
| `a` khác `null`, `b == null` | `false` | `false` |
| Cả `a` và `b` đều `null` | `true` | **Ném `NullPointerException`** nếu gọi `a.equals(b)` |

Chú ý: với kiểu nguyên thủy như `int` hoặc `boolean`, `==` so sánh **giá trị primitive**. Bài này nói về hai toán hạng có kiểu **tham chiếu `String`**: trong trường hợp đó, `==` so sánh danh tính đối tượng, không so sánh từng ký tự.

## 2. Java định nghĩa `String.equals()` như thế nào?

`String` ghi đè phương thức `equals(Object)` kế thừa từ `Object`. Nó chỉ trả về `true` khi đối số là một `String` chứa **chính xác cùng chuỗi các đơn vị mã UTF-16** với đối tượng nhận lời gọi. Điều đó có một số hệ quả:

1. **Phân biệt chữ hoa và chữ thường**: `"Java".equals("java")` là `false`.
2. **Tính cả khoảng trắng**: `"Java".equals("Java ")` là `false`.
3. **Tính cả ký tự xuống dòng và dấu điều khiển**: `"A\n".equals("A")` là `false`.
4. **Phân biệt ký tự Unicode được biểu diễn bằng các dãy mã khác nhau**: chẳng hạn `"\u00E9"` (é ghép sẵn) và `"e\u0301"` (e cùng dấu sắc kết hợp) có thể hiển thị giống nhau nhưng `equals()` là `false`.
5. **Không tự chuẩn hóa, không tự `trim()` và không tự đổi chữ hoa/chữ thường**. Nếu bài toán cần quy tắc khác, chương trình phải xác định và thực hiện quy tắc đó trước khi so sánh.

Với hai `String` thực sự cùng nội dung, `equals()` luôn trả về `true`, bất kể chúng nằm ở các đối tượng khác nhau hoặc được tạo qua những cách khác nhau. Đây mới là phép so sánh đúng về **giá trị văn bản**.

`String.equals()` nhận tham số kiểu `Object`. Khi đối số không phải một đối tượng `String` (kể cả `null`), kết quả là `false`:

```java
"Java".equals(null)               // false
"Java".equals(new Object())       // false
"Java".equals(new String("Java")) // true
```

Các biểu thức trên là ví dụ minh họa trong một phương thức, không phải chương trình hoàn chỉnh.

**Đừng áp dụng máy móc quy tắc này cho mọi lớp Java.** Phương thức `Object.equals()` mặc định dùng so sánh danh tính; nhiều lớp khác định nghĩa `equals()` theo hợp đồng riêng. `StringBuilder` chẳng hạn không ghi đè `Object.equals()` để so sánh nội dung giống `String`. Chủ đề ở đây là **hợp đồng cụ thể của `String.equals()`**.

## 3. Vì sao so sánh hai chuỗi literal bằng `==` đôi khi lại trả về `true`?

Java có cơ chế **String Pool**: các chuỗi literal cùng nội dung được dùng chung một tham chiếu `String` đã được intern. Vì vậy:

```java
String a = "Java";
String b = "Java";

System.out.println(a == b);      // true
System.out.println(a.equals(b)); // true
```

Kết quả `==` là `true` ở đây là hệ quả của **hai biến đang cùng tham chiếu một đối tượng trong pool**. Nó **không** có nghĩa `==` đã chuyển thành phép so sánh nội dung.

Trong khi đó:

```java
String a = "Java";
String b = new String("Java");

System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
```

Lời gọi `new String("Java")` tạo một đối tượng riêng, mặc dù cùng giá trị. Vì vậy, việc dựa vào `==` để đánh giá dữ liệu văn bản có thể tạo ra lỗi chỉ xuất hiện khi thay đổi nguồn hoặc cách xây dựng chuỗi.

### Nối chuỗi hằng lúc biên dịch và nối lúc chạy

Một biểu thức nối mà **mọi thành phần là hằng thời gian biên dịch** có thể được tính sẵn và trở thành chuỗi literal được intern:

```java
String a = "Java";
String folded = "Ja" + "va";

System.out.println(a == folded); // true
```

Ở trường hợp khác, giá trị được xây dựng lúc chạy:

```java
String prefix = "Ja";
String runtime = prefix + "va";

System.out.println(a.equals(runtime)); // true
```

Không nên dùng `a == runtime` để kiểm tra nội dung, cho dù cách tạo ở một phiên bản mã/JDK cụ thể khiến chương trình in gì. Đối với **nối chuỗi không phải hằng thời gian biên dịch**, quy tắc ngôn ngữ tạo chuỗi kết quả lúc chạy; và một thay đổi nhỏ trong cách khởi tạo có thể làm việc thử nghiệm `==` trước đó không còn đúng.

Lưu ý về từ khóa `final`: một biến `final String` được khởi tạo bằng **biểu thức hằng** có thể là *constant variable*, nên dùng nó trong biểu thức nối cũng có thể khiến toàn bộ nối chuỗi trở thành hằng thời gian biên dịch. Đừng cho rằng cứ xuất hiện một tên biến trong phép nối thì biểu thức chắc chắn được tính lúc chạy.

## 4. Ví dụ hoàn chỉnh Java 17+: `==`, `equals()`, literal và `intern()`

Lưu mã sau vào tệp `StringEqualityDemo.java`:

```java
public class StringEqualityDemo {
    public static void main(String[] args) {
        String literal = "Java";
        String sameLiteral = "Java";
        String allocated = new String("Java");
        String runtime = new StringBuilder("Ja")
                .append("va").toString();
        String folded = "Ja" + "va";
        String pooled = allocated.intern();

        System.out.println(
                "literal == sameLiteral: " + (literal == sameLiteral));
        System.out.println(
                "literal == allocated: " + (literal == allocated));
        System.out.println(
                "literal.equals(allocated): " + literal.equals(allocated));
        System.out.println(
                "literal == runtime: " + (literal == runtime));
        System.out.println(
                "literal.equals(runtime): " + literal.equals(runtime));
        System.out.println(
                "literal == folded: " + (literal == folded));
        System.out.println(
                "literal == pooled: " + (literal == pooled));
        System.out.println(
                "literal.equals(java): " + literal.equals("java"));
        System.out.println(
                "literal.equals(null): " + literal.equals(null));
    }
}
```

Biên dịch và chạy:

```bash
javac StringEqualityDemo.java
java StringEqualityDemo
```

Kết quả:

```text
literal == sameLiteral: true
literal == allocated: false
literal.equals(allocated): true
literal == runtime: false
literal.equals(runtime): true
literal == folded: true
literal == pooled: true
literal.equals(java): false
literal.equals(null): false
```

**Giải thích từng nhóm kết quả:**

- `literal` và `sameLiteral` là cùng một literal nên tham chiếu cùng đối tượng đã được intern.
- `allocated` là một `String` mới. Vì vậy `literal == allocated` trả `false` nhưng `literal.equals(allocated)` vẫn là `true`.
- `runtime` được tạo từ `StringBuilder.toString()`; nó mang cùng dãy ký tự nhưng là một đối tượng chuỗi độc lập trong ví dụ.
- `folded` là phép nối hai literal tại thời điểm biên dịch nên trùng tham chiếu pool với `"Java"`.
- `allocated.intern()` trả về tham chiếu chuẩn của chuỗi cùng nội dung trong pool, nên `literal == pooled` là `true`.
- `equals()` so sánh **chính xác** dãy ký tự; `"Java"` và `"java"` khác nhau do chữ hoa/chữ thường, còn đối số `null` đơn giản không phải một chuỗi bằng nội dung.

`intern()` là một API thực sự tồn tại nhưng **không cần thiết** để kiểm tra nội dung. Không gọi `intern()` hàng loạt chỉ để khiến `==` cho kết quả mong muốn: dùng `equals()` vừa đơn giản hơn vừa làm rõ đúng ý nghĩa của điều kiện.

## 5. Xử lý `null` khi so sánh nội dung

`equals()` là phương thức thực thể: nếu `input == null` thì `input.equals("OK")` ném `NullPointerException`. Ngược lại, `"OK".equals(input)` trả `false` khi đầu vào thiếu, bởi literal nhận lời gọi luôn khác `null`.

```java
String input = null;
System.out.println("OK".equals(input)); // false
System.out.println(input != null && input.equals("OK")); // false
System.out.println(java.util.Objects.equals(input, "OK")); // false
System.out.println(java.util.Objects.equals(null, null)); // true
```

Đặt literal bên trái khi so với hằng, dùng `&&` để kiểm tra receiver trước khi gọi, hoặc chọn `Objects.equals(a, b)` khi cả hai có thể `null` **và** yêu cầu coi hai giá trị vắng mặt là bằng nhau. Những cách này xử lý dữ liệu nullable; chúng không làm `==` trở thành phép so sánh nội dung.

Các bài riêng về `String.equals(null)` và `Objects.equals` phân tích sâu hơn đối số khác kiểu, hợp đồng null-safe và các trường hợp nghiệp vụ.



## 6. Tại sao `==` có thể tạo lỗi “chạy máy tôi thì đúng”?

Giả sử một ứng dụng kiểm tra một trạng thái:

```java
String status = new String("READY");

if (status == "READY") {
    System.out.println("Accepted");
} else {
    System.out.println("Rejected");
}
```

Kết quả là `Rejected`, dù `status` chứa đúng chữ `"READY"`. Nguyên nhân: `new String("READY")` tạo object khác với literal `"READY"`, vì vậy `==` là `false`.

Đổi thành:

```java
if ("READY".equals(status)) {
    System.out.println("Accepted");
} else {
    System.out.println("Rejected");
}
```

Kết quả là `Accepted`. Điều kiện giờ kiểm tra **nội dung**, đúng với mục tiêu nghiệp vụ.

Lỗi dạng này dễ lọt qua kiểm thử sơ sài nếu thử bằng chuỗi literal trong code, khi hai tham chiếu vô tình được chia sẻ từ String Pool. Khi dữ liệu đến từ API, tệp, người dùng hoặc chuỗi ghép lúc chạy, hành vi dựa trên danh tính đối tượng không còn phù hợp. Vì vậy, tránh dựa vào String Pool để viết điều kiện nội dung.

## 7. Liên hệ với tính bất biến và `hashCode()`

`String` là **immutable**: nội dung của một đối tượng `String` không thể bị thay đổi sau khi tạo bằng API thông thường.

```java
String a = "Java";
String b = a;

a = a.concat(" 17");

System.out.println(a);           // Java 17
System.out.println(b);           // Java
System.out.println(a == b);      // false
System.out.println(a.equals(b)); // false
```

Gán lại biến `a` không sửa đối tượng `String` cũ mà `b` vẫn giữ. Do đó, hai phép so sánh sau phép nối trong ví dụ cùng trả về `false`, nhưng **vì hai lý do khác nhau**: tham chiếu khác nhau và nội dung cũng khác nhau.

Nếu hai `String` bằng nhau theo `equals()` thì `hashCode()` phải bằng nhau. Chiều ngược lại sai khi hai chuỗi khác nội dung có mã băm trùng nhau. Bài riêng về `equals` và `hashCode` giải thích cách `HashMap`/`HashSet` xử lý các trường hợp này.

## 8. Phân biệt các cách so sánh chuỗi thường gặp

| Phương thức/toán tử | Kiểm tra | Khi dùng |
| --- | --- | --- |
| `a == b` | Hai tham chiếu cùng object (hoặc cùng `null`) | Khi danh tính đối tượng thực sự là mục tiêu; kiểm tra `null`. |
| `a.equals(b)` | Hai chuỗi cùng dãy UTF-16 code units | So sánh nội dung chính xác và `a` chắc chắn khác `null`. |
| `"X".equals(a)` | Nội dung của `a` đúng bằng `"X"` | So sánh với hằng literal, an toàn khi `a` là `null`. |
| `Objects.equals(a, b)` | Bằng nhau theo `equals`, xử lý `null` | Khi một hoặc cả hai tham chiếu có thể là `null`. |
| `a.equalsIgnoreCase(b)` | So sánh bỏ qua một số khác biệt hoa/thường theo hợp đồng `String` | Chỉ khi quy tắc cho phép bỏ qua khác biệt hoa/thường. |
| `a.compareTo(b)` | So sánh thứ tự từ điển dựa trên UTF-16 code units | Khi cần sắp xếp/tính thứ tự; trả số âm, 0 hoặc dương. |
| `a.contentEquals(charSequence)` | So sánh nội dung với `CharSequence` | Khi đối tượng kia thuộc kiểu như `StringBuilder` mà yêu cầu là so sánh ký tự. |

`compareTo() == 0` với hai `String` tương đương `equals()` về nội dung; `compareTo()` không nhằm trả lời câu hỏi hai biến có cùng tham chiếu. Cũng cần lưu ý các thao tác sắp xếp dựa trên Unicode/locale có thể cần `Collator` hoặc thuật toán riêng nếu ứng dụng muốn thứ tự ngôn ngữ tự nhiên, không phải thứ tự UTF-16.

## 9. Sai lầm phổ biến và cách tránh

1. **Dùng `==` để kiểm tra dữ liệu văn bản**: `if (input == "yes")` có thể sai vì danh tính khác. Dùng `"yes".equals(input)` để kiểm tra nội dung.
2. **Tin rằng `==` luôn sai với hai chuỗi**: cũng không đúng; hai literal cùng nội dung có thể tham chiếu cùng object do pool, hoặc hai biến cùng trỏ tới một object. Vấn đề nằm ở ý nghĩa phép kiểm tra.
3. **Cho rằng `equals()` không bao giờ ném ngoại lệ**: gọi trên tham chiếu `null` gây `NullPointerException`. Dùng literal ở bên trái hoặc `Objects.equals()` khi cần.
4. **Cho rằng `Objects.equals(null, null)` trả `false`**: kết quả là `true`; hai tham chiếu đều `null` được coi là bằng nhau bởi helper này.
5. **Lạm dụng `intern()` để “sửa” so sánh**: không cần intern để so sánh đúng nội dung. Dùng `equals()`, chỉ xem xét intern nếu có mục đích riêng và đã cân nhắc trade-off.
6. **Nghĩ `equals()` tự bỏ khoảng trắng**: `"Java"` khác `"Java "`. Nếu muốn chuẩn hóa đầu vào, cần quy tắc rõ ràng, chẳng hạn `strip()` khi thực sự cho phép bỏ whitespace ở biên.
7. **Nghĩ `equals()` tự bỏ qua hoa/thường**: `"Java"` khác `"java"`. Chỉ dùng `equalsIgnoreCase()` nếu yêu cầu so sánh quy định điều đó.
8. **Nghĩ mọi chuỗi hiển thị giống nhau đều `equals() == true`**: Unicode có thể biểu diễn văn bản bằng nhiều dãy mã khác nhau. Cân nhắc chuẩn hóa nếu hệ thống cần.
9. **Dùng `hashCode()` để quyết định hai chuỗi bằng nhau**: băm trùng không chứng minh cùng nội dung; `equals()` mới diễn đạt chính xác điều kiện bằng nhau.
10. **Dùng `==` để so sánh chuỗi chỉ vì nó “nhanh hơn”**: trả lời sai bài toán không phải tối ưu. Ưu tiên tính đúng đắn; tối ưu sau khi đo và xác định vấn đề thực.

## 10. Câu hỏi tự kiểm tra

**Câu 1.** Dự đoán kết quả:

```java
String first = "hi";
String second = "hi";
String third = new String("hi");

System.out.println(first == second);
System.out.println(first == third);
System.out.println(first.equals(third));
```

Đáp án:

```text
true
false
true
```

Hai literal được intern cùng tham chiếu; `new String` tạo object khác nhưng cùng dãy ký tự.

**Câu 2.** Hai biến đều là `null` thì điều kiện nào trả `true`, điều kiện nào gây ngoại lệ?

```java
String a = null;
String b = null;

System.out.println(a == b);
System.out.println(java.util.Objects.equals(a, b));
// System.out.println(a.equals(b));
```

Hai dòng in đầu đều là `true`. Nếu bỏ chú thích dòng cuối, lời gọi `a.equals(b)` ném `NullPointerException` do `a` là `null`.

**Câu 3.** Hai chuỗi vừa khác tham chiếu vừa khác nội dung, `a == b` và `a.equals(b)` sẽ ra sao?

Cả hai cùng là `false`, nhưng ý nghĩa vẫn khác: `==` kiểm tra cùng object, `equals()` kiểm tra cùng văn bản. **Không thể suy ngược** từ việc hai kết quả trùng nhau rằng hai cơ chế tương đương.

**Câu 4.** Một chương trình đọc `String command` từ người dùng; cần nhận đúng lệnh viết hoa `"START"`. Viết điều kiện nào?

```java
if ("START".equals(command)) {
    // Thực hiện tác vụ.
}
```

Điều kiện kiểm tra nội dung chính xác, phân biệt hoa/thường và không gặp NPE khi `command == null`. Nếu nghiệp vụ chấp nhận `"start"`, mới cân nhắc `equalsIgnoreCase()` cùng quy tắc chuẩn hóa phù hợp.

## Tổng kết

Với hai tham chiếu `String a` và `String b`, hãy tự hỏi:

- **Có đang cần biết hai biến trỏ cùng một object không?** → `a == b`.
- **Có đang cần biết hai giá trị văn bản giống nhau không?** → `a.equals(b)` nếu `a` không `null`; `Objects.equals(a, b)` khi cần an toàn với `null`.
- **Một vế là chuỗi literal cố định?** → thường dùng `"expected".equals(actual)` cho mục đích kiểm tra nội dung.
- **Yêu cầu có phân biệt hoa/thường, khoảng trắng hoặc Unicode không?** → xác định rõ quy tắc trước khi so sánh; `equals()` mặc định kiểm tra nội dung chính xác.

String Pool có thể khiến một vài phép `==` giữa literal trả `true`, nhưng **đó là tính chất chia sẻ tham chiếu**, không thay đổi hợp đồng so sánh. Mã xử lý dữ liệu văn bản đúng phải phản ánh điều kiện bằng nhau về **nội dung**, không lệ thuộc vào cách JVM tổ chức các đối tượng `String`.

## Tài liệu tham khảo

- [Java SE 21 API — `java.lang.String`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/String.html): `equals`, `equalsIgnoreCase`, `compareTo`, `contentEquals`, `intern`.
- [Java Language Specification §15.21.3 — Reference Equality Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.21.3): ý nghĩa của `==` và `!=` đối với kiểu tham chiếu.
- [Java Language Specification §3.10.5 — String Literals](https://docs.oracle.com/javase/specs/jls/se21/html/jls-3.html#jls-3.10.5): quy định literal chuỗi được intern.
- [Java SE 21 API — `java.util.Objects.equals`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Objects.html#equals(java.lang.Object,java.lang.Object)): phép kiểm tra bằng nhau an toàn với `null`.
