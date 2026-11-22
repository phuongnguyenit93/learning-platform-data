# So sánh nội dung bằng `equals()` thay cho `==` trong Java

> **Java core — language-basics / Ký tự và chuỗi**  
> **Yêu cầu:** JDK 17+, không dùng thư viện ngoài.  
> **Mục tiêu:** Hiểu vì sao `==` không phải cách kiểm tra nội dung `String`; sử dụng `equals()`, `Objects.equals()` và `equalsIgnoreCase()` đúng ngữ cảnh, tránh lỗi `null` và kết quả tưởng như ngẫu nhiên do string pool.

## 1. `==` và `equals()` trả lời hai câu hỏi khác nhau

Một biến kiểu `String` là **tham chiếu** đến đối tượng chuỗi. Hai biến có thể trỏ đến **hai đối tượng khác nhau** nhưng nội dung văn bản bên trong giống hệt nhau.

| Cách viết | Với hai tham chiếu `String` | Dùng khi nào? |
| --- | --- | --- |
| `a == b` | Kiểm tra **cùng tham chiếu/cùng đối tượng** (hoặc cả hai `null`) | Khi thật sự cần kiểm tra identity, hoặc kiểm tra `a == null` |
| `a.equals(b)` | Kiểm tra **nội dung** của hai chuỗi theo quy tắc `String.equals` | Khi muốn so sánh chính xác văn bản và biết `a != null` |
| `Objects.equals(a, b)` | So sánh nội dung như `equals` nhưng an toàn nếu một/hai giá trị là `null` | Khi một hoặc hai tham chiếu có thể `null` |
| `a.equalsIgnoreCase(b)` | So sánh nội dung **không phân biệt hoa/thường** theo quy tắc của Java | Khi yêu cầu nghiệp vụ thực sự không phân biệt hoa/thường |

Ví dụ cốt lõi:

~~~java
String first = new String("Java");
String second = new String("Java");

System.out.println(first == second);      // false: hai đối tượng khác nhau.
System.out.println(first.equals(second)); // true: nội dung giống nhau.
~~~

`String.equals(Object)` so sánh chuỗi theo trình tự **đơn vị mã UTF-16** và có phân biệt hoa/thường. Nó trả về `false` khi đối số là `null` hoặc không phải `String`; không ép kiểu số hay tự xóa khoảng trắng để cố làm hai giá trị bằng nhau.

**Quy tắc thực tế:** Muốn biết hai chuỗi mang **cùng giá trị văn bản**, ưu tiên `equals` (hoặc `Objects.equals` khi cần null-safe), không dùng `==`.

## 2. Vì sao đôi lúc `==` với String lại ra `true`?

Java có **string pool** cho các literal chuỗi. Trong cùng chương trình, hai literal có nội dung tương đương thường dùng chung đối tượng chuỗi đã được intern:

~~~java
String a = "Java";
String b = "Java";

System.out.println(a == b);      // true do cùng literal được intern.
System.out.println(a.equals(b)); // true vì nội dung giống nhau.
~~~

Kết quả `a == b` trong tình huống trên **không chứng minh** rằng `==` là phép so sánh nội dung. Khi tạo đối tượng `new String("Java")` hoặc ghép chuỗi ở runtime, cùng nội dung vẫn có thể đi kèm tham chiếu khác:

~~~java
String pooled = "Java";
String copied = new String("Java"); // Chỉ dùng để minh họa reference identity.
String part = "Ja";
String combined = part + "va";      // Ghép ở runtime.

System.out.println(pooled == copied);    // false
System.out.println(pooled.equals(copied)); // true
System.out.println(pooled == combined);  // false
System.out.println(pooled.equals(combined)); // true
~~~

Đừng cố dựa vào việc JVM tối ưu chuỗi hay chuỗi đến từ literal, file, người dùng hoặc API để dùng `==` thay `equals`. `new String(...)` hiếm khi cần trong code ứng dụng thực tế; nó xuất hiện ở đây để chứng minh hai object khác nhau.

## 3. Chương trình Java 17+ chạy được

Tạo file **StringEqualsDemo.java**:

~~~java
import java.util.Objects;

public final class StringEqualsDemo {
    public static void main(String[] args) {
        String literal = "Java";
        String alias = literal;
        String separate = new String("Java");
        String part = "Ja";
        String computed = part + "va";
        String lower = "java";
        String missing = null;

        System.out.println("sameReference=" + (literal == alias));
        System.out.println("differentReference=" + (literal == separate));
        System.out.println("sameContent=" + literal.equals(separate));
        System.out.println("computedReference=" + (literal == computed));
        System.out.println("computedContent=" + literal.equals(computed));

        System.out.println("caseSensitive=" + literal.equals(lower));
        System.out.println("ignoreCase=" + literal.equalsIgnoreCase(lower));
        System.out.println("spacesMatter=" + literal.equals(" Java "));
        System.out.println("trimmed=" + literal.equals(" Java ".trim()));

        System.out.println("isNull=" + (missing == null));
        System.out.println("constantFirst=" + "Java".equals(missing));
        System.out.println("bothNull=" + Objects.equals(missing, null));
        System.out.println("oneNull=" + Objects.equals(literal, missing));

        String composed = "\u00E9";
        String decomposed = "e\u0301";
        System.out.println("unicodeForms=" + composed.equals(decomposed));

        if ("Java".equals(computed)) {
            System.out.println("decision=match");
        }
    }
}
~~~

Biên dịch và chạy từ thư mục chứa file (Bash, PowerShell hoặc Command Prompt):

~~~bash
javac -encoding UTF-8 StringEqualsDemo.java
java StringEqualsDemo
~~~

**Expected output chính xác:**

~~~text
sameReference=true
differentReference=false
sameContent=true
computedReference=false
computedContent=true
caseSensitive=false
ignoreCase=true
spacesMatter=false
trimmed=true
isNull=true
constantFirst=false
bothNull=true
oneNull=false
unicodeForms=false
decision=match
~~~

**Cách kiểm chứng:**

- `literal` và `alias` cùng trỏ đến một đối tượng, nên `==` là `true`. `separate` là một đối tượng mới, nên `==` là `false` dù `equals()` là `true`.
- `computed` được tạo bằng phép nối phụ thuộc biến ở runtime. Nội dung bằng `"Java"` nhưng không cùng tham chiếu với literal.
- `equals()` phân biệt `"Java"` và `"java"`; `equalsIgnoreCase()` cho `true`. Khoảng trắng đầu/cuối cũng làm `equals` trả `false` nếu chưa chuẩn hóa dữ liệu.
- `"Java".equals(missing)` an toàn và trả `false`. `Objects.equals(null, null)` trả `true`; `Objects.equals("Java", null)` trả `false`.
- `"\u00E9"` là ký tự `é` viết bằng một code point, còn `"e\u0301"` là `e` cùng dấu sắc kết hợp; có thể hiển thị giống nhau nhưng **khác trình tự UTF-16**, nên `equals` cho `false`.

## 4. So sánh an toàn khi có `null`

Nếu `input` có thể là `null`, gọi `input.equals("OK")` sẽ gây `NullPointerException`.

~~~java
String input = null;
// boolean bad = input.equals("OK"); // Ném NullPointerException nếu chạy.
boolean safe = "OK".equals(input);   // false
~~~

**Ba cách phổ biến:**

| Tình huống | Cách viết |
| --- | --- |
| Biết `input` không `null` | `input.equals(expected)` |
| So với một chuỗi cố định, `input` có thể `null` | `"OK".equals(input)` |
| Hai biến đều có thể `null` | `Objects.equals(left, right)` |

`Objects.equals(left, right)` trả `true` nếu **cả hai đều `null`**. Nếu nghiệp vụ xem “hai giá trị cùng thiếu” là *không bằng nhau*, cần viết quy tắc riêng, ví dụ `left != null && left.equals(right)`.

Lưu ý: `String.equals(null)` **không ném exception** nếu đối tượng bên trái không `null`; nó trả `false`. Exception xảy ra khi **tham chiếu bên trái** là `null` mà bạn vẫn gọi method.

## 5. Phân biệt nội dung chính xác và nội dung chuẩn hóa

Vì `String.equals` kiểm tra nội dung chính xác, những chuỗi gần giống không tự được xem là bằng nhau:

- **Chữ hoa/thường:** `"Java".equals("java")` là `false`.
- **Khoảng trắng:** `"Java".equals(" Java ")` là `false`.
- **Unicode:** các chuỗi có ký tự nhìn giống nhau nhưng dùng các trình tự code point khác nhau có thể không `equals`.

Khi nghiệp vụ cho phép chuẩn hóa, hãy thực hiện **rõ ràng trước khi so sánh**:

~~~java
String expected = "Java";
String input = " java ";
boolean accepted = expected.equalsIgnoreCase(input.strip());
System.out.println(accepted); // true
~~~

Nhưng **không nên luôn strip hoặc bỏ phân biệt hoa/thường**: mật khẩu, định danh phân biệt hoa/thường và nội dung phải giữ nguyên có thể cần so sánh chính xác. `equalsIgnoreCase` cũng không phải công cụ tổng quát cho mọi quy tắc phân biệt ngôn ngữ, Unicode normalization hay so sánh theo locale.

Khi thật sự cần Unicode normalization, Java cung cấp `java.text.Normalizer`; đó là một bước xử lý riêng, **không** được `equals` tự động thực hiện.

## 6. Bẫy thường gặp

| Dòng mã hoặc nhận định | Điểm sai và cách sửa |
| --- | --- |
| `if (username == "admin")` | `==` so tham chiếu; dùng `"admin".equals(username)` nếu so nội dung chính xác |
| `new String("x") == new String("x")` | `false` vì hai object khác nhau; dùng `equals` |
| “Hai literal cho `== true` thì so nội dung bằng `==` là đủ.” | Sai: string pool không bảo đảm mọi `String` có cùng nội dung cùng reference |
| `input.equals("YES")` khi `input` có thể `null` | Có thể NPE; dùng `"YES".equals(input)` hoặc `Objects.equals` |
| `"a".equals("A")` | `false`; chỉ dùng `equalsIgnoreCase` nếu yêu cầu không phân biệt hoa/thường |
| `"a".equals(" a ")` | `false` vì khoảng trắng khác nhau |
| So sánh `StringBuilder` bằng `equals` và kỳ vọng so ký tự | `StringBuilder` không override `Object.equals` để so nội dung; nếu cần, so `toString()` của hai builder |

### Bài tập tự luyện

**Bài 1.** Cho `String x = "hello"; String y = new String("hello");`. Dự đoán `x == y` và `x.equals(y)`, giải thích không dựa vào việc string pool có hay không.

**Bài 2.** Cho `String input = null;`. Viết ba cách kiểm tra an toàn rằng input có nội dung `"YES"` hoặc báo thiếu dữ liệu. `Objects.equals(null, null)` có phù hợp nếu hai trường đều chưa được nhập không?

**Bài 3.** Viết điều kiện chấp nhận `"yes"`, `"YES"` và `" Yes "`, nhưng không chấp nhận `"y"`. Chỉ chuẩn hóa khi nghiệp vụ cho phép.

**Bài 4.** Tự thử so `"\u00E9"` với `"e\u0301"`. Vì sao người dùng có thể nhìn thấy cùng một chữ nhưng `equals` cho `false`? Điều kiện nào cần chuẩn hóa Unicode?

**Bài 5.** Tạo hai `StringBuilder` chứa `"abc"`, thử `a.equals(b)` và `a.toString().equals(b.toString())`. Khi nào phép so sánh nội dung là đúng mục đích?

### Ghi nhớ

**Với `String`, `==` hỏi “cùng đối tượng?”; `equals()` hỏi “cùng nội dung?”.** Dùng `equals` để so giá trị văn bản; ưu tiên `"literal".equals(value)` hoặc `Objects.equals(a, b)` khi cần an toàn với `null`. Đừng nhầm hiệu ứng của string pool, việc chuẩn hóa dữ liệu hay `equalsIgnoreCase` với quy tắc so sánh chính xác của `String.equals`.
