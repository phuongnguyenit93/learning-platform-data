# Phân biệt nội dung chuỗi với biến tham chiếu đến chuỗi

Trong Java, khi viết `String name = "Java";`, cần phân biệt **nội dung chuỗi** (`"Java"`), **đối tượng `String`** biểu diễn nội dung đó và **biến tham chiếu** (`name`) dùng để truy cập đối tượng. Ba khái niệm liên quan nhưng không đồng nhất. Nắm được sự khác biệt này giúp giải thích phép gán, tính bất biến của `String`, so sánh bằng `==` và `equals()`, cũng như các trường hợp dễ gây lỗi khi xử lý chuỗi.

## 1. Nội dung, đối tượng và biến tham chiếu

Xét:

```java
String text = "Java";
```

- `String` là kiểu tham chiếu (`reference type`), không phải kiểu nguyên thủy như `int` hay `boolean`.
- `"Java"` là một *string literal*: biểu thức cung cấp tham chiếu tới một đối tượng `String` có nội dung là bốn ký tự `J`, `a`, `v`, `a`. Java quản lý các literal và chuỗi được `intern()` trong một vùng dùng chung gọi là *string pool*.
- `text` là biến kiểu `String`. Giá trị của biến này là **một tham chiếu tới đối tượng** (hoặc `null`); không nên hiểu biến tự chứa một bản sao độc lập của toàn bộ nội dung `"Java"`.
- Nội dung chuỗi là dãy ký tự mà đối tượng `String` biểu diễn. Nội dung ấy có thể được hỏi bằng các phương thức như `length()`, `charAt()` hoặc `equals()`.

Có thể hình dung quan hệ ở mức khái niệm:

```text
Biến text --tham chiếu--> Đối tượng String
                         Nội dung: "Java"
```

Sơ đồ nhằm minh họa quan hệ tham chiếu, **không phải** địa chỉ bộ nhớ cụ thể, cấu trúc vùng nhớ hay cách JVM phải triển khai nội bộ. Java không cung cấp địa chỉ bộ nhớ đối tượng thông qua biến `String`.

| Khía cạnh | Nội dung chuỗi | Biến tham chiếu `String` |
|---|---|---|
| Câu hỏi cần trả lời | Chuỗi biểu diễn những ký tự nào? | Biến đang trỏ đến đối tượng nào (hay `null`)? |
| Ví dụ | `"Java"` | `text` trong `String text = "Java";` |
| So sánh thường dùng | `equals()` | `==` kiểm tra hai tham chiếu có cùng đối tượng |
| Có thể thay đổi bằng phép gán? | Không sửa được nội dung của một `String` hiện hữu | Có, biến có thể được gán tham chiếu khác |
| Có thể bằng `null`? | Không: `null` không phải một chuỗi có nội dung | Có: biến tham chiếu có thể chứa `null` |

## 2. Gán tham chiếu không tạo bản sao chuỗi

```java
String first = "Java";
String alias = first;
```

Sau phép gán `alias = first`, hai biến đang **cùng tham chiếu đến một đối tượng `String`**. Phép gán giữa hai biến tham chiếu không tạo ra một đối tượng mới và cũng không sao chép các ký tự sang một đối tượng khác.

```text
first -----+
           +----> String có nội dung "Java"
alias -----+
```

Nếu thực hiện `first = "Kotlin";`, Java chỉ thay giá trị tham chiếu được giữ trong biến `first`. Biến `alias` vẫn tham chiếu đến chuỗi `"Java"`:

```text
first ----------> String có nội dung "Kotlin"
alias ----------> String có nội dung "Java"
```

Điều này khác với ý tưởng “đổi nội dung trong đối tượng ban đầu”. Phép gán lại một biến không tự thay đổi tham chiếu của các biến khác.

## 3. `String` bất biến: đổi giá trị biến khác với sửa nội dung đối tượng

Đối tượng `String` là **immutable**: sau khi được tạo, nội dung của chính đối tượng đó không thể bị thay đổi qua API của `String`. Các thao tác như `concat()`, `replace()`, `substring()` hoặc nối chuỗi có thể trả về một tham chiếu tới chuỗi có nội dung mong muốn; chúng không chỉnh sửa các ký tự bên trong đối tượng gốc. Một thao tác có thể trả về chính đối tượng cũ khi phù hợp (chẳng hạn nối với chuỗi rỗng), vì vậy không nên khẳng định mọi lời gọi đều tạo đối tượng mới.

```java
String a = "Java";
String b = a;

a = a.concat(" Core");

System.out.println(a); // Java Core
System.out.println(b); // Java
```

Ban đầu, `a` và `b` cùng trỏ đến `"Java"`. `concat(" Core")` cho kết quả là chuỗi `"Java Core"`; phép gán đặt tham chiếu kết quả vào `a`. `b` vẫn trỏ đến đối tượng `"Java"` ban đầu. Tương tự, `a += " Core"` không “sửa tại chỗ” đối tượng `String` gốc.

Điểm thực hành: khi muốn giữ kết quả của các thao tác trả về chuỗi, hãy sử dụng giá trị được trả về, ví dụ `text = text.trim();`. Chỉ gọi `text.trim();` mà bỏ qua kết quả sẽ không cập nhật biến `text`.

## 4. So sánh: `==` hỏi “cùng đối tượng?”, `equals()` hỏi “cùng nội dung?”

Với hai biến kiểu `String`:

- `a == b` là **so sánh tham chiếu**: `true` nếu cả hai đang trỏ đến cùng một đối tượng, hoặc cả hai cùng là `null`.
- `a.equals(b)` là **so sánh nội dung** theo định nghĩa của `String.equals`: `true` khi `b` là chuỗi có cùng dãy ký tự; phép so sánh có phân biệt chữ hoa/chữ thường. Nếu `a` là `null` thì lời gọi `a.equals(b)` ném `NullPointerException`.
- Có thể có **cùng nội dung nhưng khác đối tượng**. Ngược lại, nếu hai tham chiếu cùng trỏ đến một đối tượng `String` thì nội dung hiển nhiên giống nhau.

Ví dụ hoàn chỉnh, chạy được trên Java 17+:

**Tệp `StringReferenceDemo.java`**

```java
public class StringReferenceDemo {
    public static void main(String[] args) {
        String first = "Java";
        String alias = first;
        String separate = new String("Java");
        String sameLiteral = "Java";

        System.out.println("first == alias: " + (first == alias));
        System.out.println("first == separate: " + (first == separate));
        System.out.println("first.equals(separate): " + first.equals(separate));
        System.out.println("first == sameLiteral: " + (first == sameLiteral));

        first = first.concat(" Core");
        System.out.println("first: " + first);
        System.out.println("alias: " + alias);
        System.out.println("separate: " + separate);
        System.out.println("first == alias sau gan lai: " + (first == alias));
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp:

```bash
javac StringReferenceDemo.java
java StringReferenceDemo
```

**Đầu ra:**

```text
first == alias: true
first == separate: false
first.equals(separate): true
first == sameLiteral: true
first: Java Core
alias: Java
separate: Java
first == alias sau gan lai: false
```

Diễn giải từng điểm quan trọng:

1. `alias = first` sao chép tham chiếu nên `first == alias` là `true`.
2. `new String("Java")` chủ động tạo một đối tượng `String` mới, khác đối tượng từ literal `"Java"`. Hai đối tượng vẫn cùng nội dung nên `==` là `false` và `equals()` là `true`.
3. Hai lần sử dụng literal `"Java"` dùng chung đối tượng đã intern, nên `first == sameLiteral` là `true` tại thời điểm so sánh.
4. Sau `first = first.concat(" Core")`, `first` giữ tham chiếu tới kết quả có nội dung `"Java Core"`; `alias` và `separate` vẫn có nội dung `"Java"`. Vì `first` đã được gán lại, `first == alias` là `false`.

**Quy tắc sử dụng:** nếu yêu cầu nghiệp vụ là kiểm tra hai chuỗi có cùng văn bản hay không (tên, mã, dữ liệu nhập, trạng thái biểu diễn bằng chuỗi), thường dùng `equals()`; không lấy kết quả `==` làm tiêu chí so sánh nội dung.

## 5. String pool: vì sao đôi khi `==` trả về `true`?

Java lưu các string literal và những chuỗi được intern để có thể tái sử dụng cùng một đối tượng. Cơ chế này giúp giải thích hiện tượng hai literal có cùng nội dung thường có cùng tham chiếu. Trong khi đó, `new String("Java")` tạo đối tượng mới cho biểu thức `new`.

Trình biên dịch còn có thể tính trước **biểu thức hằng** bằng phép nối các literal. Ngược lại, nối chuỗi từ dữ liệu được xác định lúc chạy tạo kết quả theo luồng thực thi; đừng dựa vào tham chiếu trùng nhau để kết luận hai nội dung bằng nhau.

**Tệp `StringPoolDemo.java`**

```java
public class StringPoolDemo {
    public static void main(String[] args) {
        String literal = "Java";
        String folded = "Ja" + "va";
        String prefix = new String("Ja");
        String computed = prefix + "va";

        System.out.println(literal == folded);
        System.out.println(literal.equals(computed));
        System.out.println(literal == computed);
        System.out.println(literal == computed.intern());
    }
}
```

```bash
javac StringPoolDemo.java
java StringPoolDemo
```

**Đầu ra với Java 17+:**

```text
true
true
false
true
```

- `"Ja" + "va"` là biểu thức hằng và được gộp thành literal `"Java"` khi biên dịch: `literal == folded` là `true`.
- `prefix` là giá trị có đối tượng được tạo lúc chạy bằng `new`. `computed` có cùng ký tự với `literal`, vì vậy `equals()` là `true`, nhưng kết quả phép nối lúc chạy không tự động trở thành cùng đối tượng đã intern với literal.
- `computed.intern()` trả về tham chiếu chuẩn tương ứng trong pool; vì literal `"Java"` đã tồn tại nên so sánh tham chiếu với `literal` là `true`.

Cơ chế pool giải thích sự khác nhau giữa các biểu thức, **không phải** lý do dùng `==` để so nội dung. Trong mã ứng dụng, việc tạo `new String(...)` chỉ nhằm kiểm tra sự khác biệt tham chiếu thường là thừa; không cần cố ép các chuỗi vào pool để so sánh đúng.

## 6. `null`, chuỗi rỗng và so sánh an toàn

`null` có nghĩa là biến **không tham chiếu đến một đối tượng nào**. Nó khác chuỗi rỗng `""`: chuỗi rỗng là một đối tượng `String` hợp lệ, có độ dài `0`.

```java
String missing = null;
String empty = "";

System.out.println(missing == null); // true
System.out.println(empty == null);   // false
System.out.println(empty.length());  // 0
```

Gọi `missing.length()` hay `missing.equals("Java")` sẽ ném `NullPointerException` vì không có đối tượng để gọi phương thức.

Hai cách so sánh nội dung an toàn khi có thể có `null`:

- Với một literal chắc chắn không null, đảo phía gọi: `"Java".equals(candidate)`; nếu `candidate` là `null`, kết quả là `false`.
- Với hai biến đều có thể null, dùng `Objects.equals(left, right)`. Phương thức trả về `true` khi cả hai `null` hoặc khi hai giá trị không null bằng nhau theo `equals()`.

**Tệp `SafeStringCompareDemo.java`**

```java
import java.util.Objects;

public class SafeStringCompareDemo {
    public static void main(String[] args) {
        String candidate = null;

        System.out.println(candidate == null);
        System.out.println("Java".equals(candidate));
        System.out.println(Objects.equals(candidate, null));
        System.out.println("".equals(candidate));
    }
}
```

```bash
javac SafeStringCompareDemo.java
java SafeStringCompareDemo
```

**Đầu ra:**

```text
true
false
true
false
```

Lưu ý: `Objects.equals(null, null)` là `true` vì hai giá trị cùng không có tham chiếu; điều đó **không** có nghĩa `null` là một chuỗi chứa văn bản.

## 7. Lỗi thường gặp và cách tránh

| Lỗi hoặc hiểu nhầm | Vì sao sai? | Cách làm đúng |
|---|---|---|
| `if (input == "yes")` để kiểm tra văn bản người dùng nhập | `input` có thể trỏ tới đối tượng khác literal dù nội dung là `"yes"` | `"yes".equals(input)` |
| Cho rằng `String copy = original;` tạo bản sao nội dung | Phép gán sao chép giá trị tham chiếu | Hiểu rằng cả hai cùng trỏ một đối tượng; `String` bất biến nên không cần sao chép phòng ngừa việc sửa nội dung |
| Cho rằng `text = text + "!"` thay đổi đối tượng cũ | `text` được gán tham chiếu tới kết quả nối | Phân biệt gán lại biến với sửa đối tượng |
| Gọi `text.trim();` rồi mong `text` thay đổi | `trim()` trả về kết quả, không sửa `String` gốc | `text = text.trim();` |
| Thấy `"a" == "a"` là `true` và suy ra `==` luôn so ký tự | Hai literal có thể được dùng chung nhờ string pool | Dùng `equals()` hoặc `Objects.equals()` cho nội dung |
| Gọi `text.equals(other)` khi `text` có thể null | Truy cập phương thức qua tham chiếu `null` gây `NullPointerException` | Kiểm tra null, đảo phía literal, hoặc dùng `Objects.equals()` |
| Xem `null` và `""` là một | `null` không trỏ đến đối tượng, `""` là chuỗi hợp lệ với 0 ký tự | Xử lý riêng theo yêu cầu nghiệp vụ |

## 8. Tự kiểm tra

Dự đoán kết quả trước khi chạy đoạn mã sau:

```java
String x = "cat";
String y = x;
String z = new String("cat");

x = "dog";

System.out.println(y);
System.out.println(x == y);
System.out.println(y.equals(z));
System.out.println(y == z);
```

**Đáp án theo thứ tự:** `cat`, `false`, `true`, `false`.

Giải thích: `y` giữ tham chiếu ban đầu tới `"cat"`; gán `"dog"` cho `x` không ảnh hưởng `y`. `z` là đối tượng khác nhưng có cùng nội dung với `y`.

Khi đọc bất kỳ đoạn mã liên quan đến `String`, hãy tự hỏi theo đúng thứ tự: **(1) Biến hiện trỏ đến đối tượng nào? (2) Nội dung của đối tượng đó là gì? (3) Phép toán đang kiểm tra tham chiếu, kiểm tra nội dung, hay đang gán lại tham chiếu?** Ba câu hỏi này giúp phân biệt rõ “chuỗi chứa gì” với “biến đang trỏ đến đâu”, kể cả khi string pool hoặc phép nối chuỗi xuất hiện.