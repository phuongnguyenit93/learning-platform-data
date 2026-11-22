# `String` là đối tượng bất biến trong Java 17+

`String` là **kiểu tham chiếu** đại diện cho chuỗi ký tự. Trong Java, đối tượng `String` **bất biến (*immutable*)**: sau khi tạo, nội dung của chính đối tượng đó không thể được chỉnh sửa qua API thông thường. Những thao tác như nối, thay thế, đổi chữ hoa/thường hay cắt chuỗi **tạo kết quả chuỗi** mà không sửa nội dung ban đầu.

Phân biệt hai ý rất quan trọng:

- **Đối tượng không đổi nội dung:** `String` đã tạo ra vẫn giữ cùng giá trị văn bản.
- **Biến có thể được gán tham chiếu khác:** `String name = "Java"; name = "Kotlin";` hợp lệ; bạn thay biến `name` trỏ sang giá trị chuỗi khác, **không sửa** đối tượng chứa `"Java"`.

## 1. Khai báo và thao tác: kết quả phải được sử dụng

~~~java
String title = "Java";
String extended = title.concat(" 17");

System.out.println(title);    // Java
System.out.println(extended); // Java 17
~~~

`concat` không thay đổi `title`. Nếu muốn giữ kết quả trên chính **biến** `title`, hãy gán lại:

~~~java
title = title.concat(" 17");
System.out.println(title); // Java 17
~~~

Câu lệnh này **đổi tham chiếu lưu trong biến**, không sửa đối tượng `String` cũ. Điều tương tự xảy ra với toán tử `+` hoặc `+=` dùng để ghép chuỗi.

| Phép toán | Ví dụ | Có sửa `String` ban đầu? |
| --- | --- | --- |
| Nối chuỗi | `s.concat("!")`, `s + "!"` | Không |
| Thay thế | `s.replace("a", "b")` | Không |
| Đổi chữ hoa | `s.toUpperCase()` | Không |
| Loại khoảng trắng ngoài | `s.trim()` hoặc `s.strip()` | Không |
| Lấy một đoạn | `s.substring(1)` | Không |
| Đọc ký tự, độ dài | `s.charAt(0)`, `s.length()` | Chỉ đọc |
| Sửa một vị trí ký tự | `s.setCharAt(0, 'A')` | **Không có** phương thức này trên `String` |

Một phương thức có thể trả về **cùng đối tượng** khi kết quả không cần thay đổi (ví dụ một số phép toán không làm khác nội dung). Định nghĩa bất biến **không có nghĩa mọi lời gọi đều buộc tạo đối tượng mới**, mà là không sửa nội dung của đối tượng `String` đã có.

## 2. Chương trình Java 17+ chạy được

Tạo tệp **`StringImmutabilityDemo.java`**:

~~~java
import java.util.Locale;

public class StringImmutabilityDemo {
    static void attemptChange(String input) {
        input = input.concat("!");
        System.out.println("insideMethod=" + input);
    }

    public static void main(String[] args) {
        String original = "Java";
        String alias = original;
        String extended = original.concat(" 17");

        System.out.println("original=" + original);
        System.out.println("alias=" + alias);
        System.out.println("extended=" + extended);
        System.out.println("sameOriginal=" + (original == alias));
        System.out.println("extendedIsOriginal=" + (extended == original));

        String sentence = "red blue";
        String replaced = sentence.replace("blue", "green");
        System.out.println("beforeReplace=" + sentence);
        System.out.println("afterReplace=" + replaced);

        String word = "java";
        word.toUpperCase(Locale.ROOT); // Ket qua bi bo qua.
        System.out.println("ignoredResult=" + word);
        word = word.toUpperCase(Locale.ROOT); // Gan lai tham chieu.
        System.out.println("assignedResult=" + word);

        String hello = "Hi";
        attemptChange(hello);
        System.out.println("afterMethod=" + hello);

        String literalA = "cat";
        String literalB = "cat";
        String explicit = new String("cat");
        System.out.println("literalSame=" + (literalA == literalB));
        System.out.println("newSame=" + (literalA == explicit));
        System.out.println("contentEqual=" + literalA.equals(explicit));

        StringBuilder builder = new StringBuilder("A");
        builder.append("B");
        String snapshot = builder.toString();
        builder.append("C");
        System.out.println("builder=" + builder);
        System.out.println("snapshot=" + snapshot);
    }
}
~~~

Chạy trên **Windows PowerShell** hoặc **Linux/Bash**, tại thư mục có tệp và JDK 17+:

~~~bash
java -version
javac -version
javac -encoding UTF-8 StringImmutabilityDemo.java
java StringImmutabilityDemo
~~~

**Expected output (chính xác theo thứ tự):**

~~~text
original=Java
alias=Java
extended=Java 17
sameOriginal=true
extendedIsOriginal=false
beforeReplace=red blue
afterReplace=red green
ignoredResult=java
assignedResult=JAVA
insideMethod=Hi!
afterMethod=Hi
literalSame=true
newSame=false
contentEqual=true
builder=ABC
snapshot=AB
~~~

### Giải thích từng hiện tượng

1. `alias = original` sao chép **giá trị tham chiếu**, nên hai biến cùng trỏ tới chuỗi `"Java"` và `original == alias` là `true`. `extended` có nội dung khác và không phải cùng đối tượng.
2. `replace` trả một chuỗi kết quả `"red green"`; `sentence` vẫn giữ `"red blue"`.
3. Lần gọi `word.toUpperCase(Locale.ROOT)` đầu tiên bị bỏ kết quả nên `word` vẫn là `"java"`. Sau khi viết phép gán, `word` trở thành tham chiếu tới kết quả `"JAVA"`.
4. `attemptChange` nhận **bản sao của giá trị tham chiếu**, như mọi tham số Java (truyền theo giá trị). Gán lại `input` chỉ thay biến tham số, không thay `hello` của bên gọi.
5. Hai string literal giống nhau thường cùng đối tượng từ **string pool**; vì vậy trong ví dụ `literalA == literalB` là `true`. `new String("cat")` tạo một đối tượng mới, nên `==` là `false` nhưng `equals` trả `true` vì nội dung bằng nhau.
6. `StringBuilder.append` **thay đổi chính đối tượng builder**. `snapshot = builder.toString()` thu được một đối tượng `String` bất biến với nội dung `"AB"`; thay đổi builder tiếp theo không biến `snapshot` thành `"ABC"`.

## 3. Bất biến khác với biến `final`

~~~java
String name = "Mai";
name = "An";            // Hop le: bien name khong final.

final String greeting = "Hello";
// greeting = "Hi";     // Sai: khong gan lai bien final.

StringBuilder mutable = new StringBuilder("A");
mutable.append("B");    // Hop le: sua noi dung StringBuilder.

final StringBuilder fixedReference = new StringBuilder("X");
fixedReference.append("Y"); // Hop le: final khong dong bang doi tuong.
~~~

`final` là quy tắc **gán lại biến**. Ngược lại, tính bất biến của `String` là thuộc tính **thiết kế kiểu đối tượng**. Một tham chiếu `String` không `final` vẫn trỏ tới những đối tượng chuỗi bất biến; một tham chiếu `final StringBuilder` vẫn có thể trỏ tới đối tượng thay đổi nội dung.

`String` cũng là một lớp `final` trong Java; không thể tạo subclass của `String` để cung cấp các phương thức thay đổi nội dung.

## 4. Nội dung bằng nhau không có nghĩa cùng tham chiếu

Tính bất biến cho phép chia sẻ một đối tượng `String` an toàn về **nội dung**, nhưng không làm hai đối tượng khác nhau trở thành cùng một tham chiếu. So sánh nội dung bằng `equals`:

~~~java
String pooled = "hello";
String separate = new String("hello");
System.out.println(pooled == separate);      // false
System.out.println(pooled.equals(separate)); // true
~~~

`==` kiểm tra identity của tham chiếu (hoặc cả hai cùng `null`). `equals` so sánh nội dung UTF-16 khi vế trái không `null`; `"OK".equals(value)` hoặc `Objects.equals(a, b)` giúp xử lý giá trị có thể `null`. **String pool** có thể khiến hai literal bằng nhau cùng tham chiếu, nhưng điều đó không biến `==` thành phép so nội dung đáng tin cậy.

Khi cần kiểm tra nội dung, nên dùng các API `equals` đúng hợp đồng. Các ca phân biệt hoa/thường, Unicode normalization và chi tiết pool được kiểm chứng riêng ở bài chuyên về so sánh `String`.


## 5. Vì sao bất biến hữu ích?

- **Chia sẻ an toàn hơn:** hai tham chiếu trỏ cùng `String` không thể sửa nội dung để gây bất ngờ cho nhau.
- **Làm khóa `Map` thuận tiện:** nội dung và kết quả `hashCode` của `String` không bị thay đổi trong quá trình lưu/tra cứu. Bản thân `HashMap` vẫn cần đồng bộ hóa phù hợp nếu dùng chung giữa các luồng.
- **Hữu ích khi dùng chung giữa luồng:** nội dung chuỗi không có các thao tác biến đổi có thể gây tranh chấp. Điều này không tự động khiến mọi thao tác trên biến tham chiếu hoặc tập hợp chứa nó đều thread-safe.
- **Dễ suy luận hơn:** phương thức nhận `String` không thể âm thầm sửa văn bản bên trong đối tượng mà bên gọi đang dùng.

Không nên hiểu rằng tính bất biến **tự bảo đảm tối ưu bộ nhớ hoặc hiệu năng** cho mọi thao tác nối chuỗi.

## 6. Dùng đối tượng mutable khi cần tích lũy nhiều lần

Bất biến giúp giá trị `String` dễ suy luận, nhưng phép `+=` lặp lại có thể tạo nhiều kết quả chuỗi trung gian. Khi xây văn bản dần qua vòng lặp, `StringBuilder` lưu nội dung **mutable** và có phương thức `append`:

~~~java
StringBuilder out = new StringBuilder();
for (int i = 1; i <= 3; i++) {
    if (i > 1) {
        out.append(",");
    }
    out.append(i);
}
String result = out.toString(); // "1,2,3"
~~~

Các phép nối ngắn như `"Hello, " + name` vẫn rõ ràng và thường được JVM tối ưu; không cần thay mọi `+` bằng builder. `StringBuilder` không tự đồng bộ khi nhiều luồng cùng sửa; `StringBuffer` cung cấp các phương thức đồng bộ hóa nếu thực sự cần. Bài chuyên `StringBuilder` giải thích thêm quản lý bộ đệm, dấu phân cách, `length`/`capacity` và các phương thức sửa nội dung.


## 7. Bài tập tự kiểm tra

**Bài 1 — Đoán kết quả.**

~~~java
String s = "abc";
s.replace("a", "x");
System.out.println(s);
~~~

*Đáp án:* `abc`. Kết quả thay thế bị bỏ đi. Viết `s = s.replace("a", "x");` mới khiến biến `s` tham chiếu chuỗi `"xbc"`.

**Bài 2 — Hai biến cùng tham chiếu.** Cho `String a = "hi"; String b = a; a += "!";`. Giá trị `a` và `b` sau đó là gì?

*Đáp án:* `a` là `"hi!"`; `b` vẫn là `"hi"`. Không có đối tượng `"hi"` nào bị sửa nội dung.

**Bài 3 — `final`.** Vì sao `final StringBuilder b = new StringBuilder("x"); b.append("y");` hợp lệ?

*Đáp án:* `final` ngăn gán lại biến `b`; `append` thay đổi đối tượng có thể sửa được mà `b` đang tham chiếu.

**Bài 4 — So sánh.** Tại sao `new String("a") == new String("a")` cho `false` nhưng `equals` cho `true`?

*Đáp án:* Hai lần `new` tạo hai đối tượng; `==` kiểm tra identity, `equals` kiểm tra nội dung.

**Bài 5 — Tham số.** Một phương thức nhận `String text` rồi viết `text = text.toUpperCase();`. Biến `String` mà bên gọi truyền vào có đổi không?

*Đáp án:* Không. Java sao chép giá trị tham chiếu vào tham số; muốn bên gọi dùng giá trị mới, hãy `return` chuỗi kết quả rồi gán ở bên gọi.

## Ghi nhớ

**Bất biến là thuộc tính của đối tượng `String`, không phải lời cấm gán lại mọi biến kiểu `String`.** `concat`, `replace`, `toUpperCase` và `substring` không sửa chuỗi gốc; hãy **sử dụng kết quả trả về**. Dùng `equals` thay vì `==` để so nội dung và dùng `StringBuilder` khi cần tích lũy, sửa văn bản nhiều lần.
