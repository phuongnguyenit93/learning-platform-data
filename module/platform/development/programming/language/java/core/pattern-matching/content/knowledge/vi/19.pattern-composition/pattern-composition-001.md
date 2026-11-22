# Kết hợp type pattern với toán tử `&&` trong Java 17+

## 1. Mục tiêu và ý tưởng chính

Khi một giá trị có kiểu khai báo rộng như `Object`, ta thường cần kiểm tra **kiểu thực tế** trước khi dùng phương thức chỉ có ở kiểu cụ thể. Từ Java 16, *pattern matching for `instanceof`* (JEP 394) cho phép vừa kiểm tra kiểu, vừa khai báo biến đã được kiểm tra kiểu:

~~~java
Object input = "Java";
if (input instanceof String text) {
    System.out.println(text.length()); // 4
}
~~~

Khi kết hợp với **toán tử AND ngắn mạch `&&`**, ta có thể sử dụng ngay pattern variable ở những điều kiện đứng sau, mà không cần ép kiểu thủ công:

~~~java
Object input = "Java";

if (input instanceof String text && text.length() >= 4) {
    System.out.println(text.toUpperCase()); // JAVA
}
~~~

Cách hiểu chính xác:

- `input instanceof String text` là một **type pattern**. Nếu thành công, biến `text` được ràng buộc với đối tượng `String` đã khớp.
- `&&` đánh giá từ trái sang phải và **chỉ đánh giá vế phải nếu vế trái trả về `true`**.
- Do đó khi chạy đến `text.length() >= 4`, Java biết chắc `input` đã khớp `String` và `text` đã được gán giá trị.
- Thân `if` chỉ chạy khi **cả** phép kiểm tra kiểu và điều kiện về độ dài đúng. Trong thân đó, `text` có kiểu tĩnh `String`.

Đây là quy tắc **flow scoping**: phạm vi dùng pattern variable phụ thuộc vào luồng điều khiển bảo đảm phép khớp đã thành công. Bài dùng cú pháp Java 17+; tính năng này được chuẩn hóa từ Java 16, **không cần** `--enable-preview` trên Java 17.

## 2. So sánh với cách viết truyền thống

Trước khi có type pattern, chương trình thường viết:

~~~java
Object value = "Spring";

if (value instanceof String) {
    String text = (String) value;
    if (!text.isBlank() && text.length() >= 4) {
        System.out.println(text.toUpperCase()); // SPRING
    }
}
~~~

Với type pattern và `&&`, toàn bộ điều kiện có thể diễn đạt rõ hơn:

~~~java
Object value = "Spring";

if (value instanceof String text
        && !text.isBlank()
        && text.length() >= 4) {
    System.out.println(text.toUpperCase()); // SPRING
}
~~~

Điểm khác biệt có giá trị học tập không chỉ là ít dòng: trình biên dịch kết nối **kết quả khớp kiểu** với **sự tồn tại của pattern variable** ở các toán hạng theo sau. Không cần viết `(String) value` một lần nữa.

**Lưu ý:** `instanceof String text` trả về `false` khi `value == null`. Vì vậy không cần thêm `value != null` trước phép `instanceof` để bảo vệ chính biểu thức này.

## 3. Vì sao `&&` cho phép dùng biến ở vế phải?

Toán tử `&&` có ba đặc điểm quan trọng:

1. Đánh giá **toán hạng trái trước**, rồi mới quyết định có chạy toán hạng phải hay không.
2. Nếu toán hạng trái là `false`, kết quả toàn biểu thức là `false`; toán hạng phải bị **bỏ qua hoàn toàn** (*short-circuit*).
3. Khi toán hạng phải được đánh giá, một type pattern trả về `true` ở bên trái đã ràng buộc các pattern variable của nó.

Xét:

~~~java
Object value = "JVM";

boolean valid = value instanceof String s
        && s.startsWith("J")
        && s.length() >= 3;

System.out.println(valid); // true
~~~

Thứ tự thực tế:

- Bước 1: `value instanceof String s` khớp, `s` mang giá trị `"JVM"`.
- Bước 2: `s.startsWith("J")` trả về `true`.
- Bước 3: `s.length() >= 3` trả về `true`.
- Kết quả `valid` là `true`.

Nếu `value` là `42` hoặc `null`, bước 1 trả về `false`; hai lời gọi phương thức trên `s` **không chạy**. Nếu `value` là `"Go"`, bước 1 thành công nhưng bước 2 trả về `false`; bước 3 không chạy.

Có thể viết dấu ngoặc để làm rõ ý: `(value instanceof String s) && s.length() >= 3`. Dấu ngoặc chỉ giúp dễ đọc; `instanceof` vốn được phân tích trước `&&` theo độ ưu tiên toán tử.

## 4. Flow scoping: pattern variable xuất hiện ở đâu?

### 4.1. Vế phải của `&&` và nhánh `if` đúng

~~~java
static void printUpper(Object input) {
    if (input instanceof String text && !text.isBlank()) {
        // Cả phép khớp kiểu và điều kiện phụ đều đúng.
        System.out.println(text.toUpperCase());
    }
}
~~~

`text` được phép xuất hiện ở vế phải của `&&` và thân `if`. Trong hai vị trí đó, việc khớp thành công đã được bảo đảm.

### 4.2. Không tự động dùng được trong `else`

~~~java
// Ví dụ cố ý SAI — không đưa vào chương trình chạy.
if (input instanceof String text && text.length() > 3) {
    System.out.println(text);
} else {
    // System.out.println(text); // Lỗi biên dịch: text không bảo đảm đã khớp.
}
~~~

Nhánh `else` có thể chạy vì `input` không phải `String`, hoặc vì `input` là `String` nhưng quá ngắn. Trình biên dịch không thể bảo đảm `text` đã được ràng buộc ở **mọi** đường đi vào `else`.

### 4.3. Không mặc nhiên dùng được sau câu `if`

~~~java
// Ví dụ cố ý SAI.
if (input instanceof String text && text.length() > 3) {
    System.out.println(text);
}
// System.out.println(text); // Không có bảo đảm match sau câu if thông thường.
~~~

Một biến được khai báo bằng type pattern không trở thành biến cục bộ có phạm vi khắp phương thức. Nó tuân theo luật *definitely matched*, không chỉ theo vị trí cặp ngoặc nhọn.

### 4.4. Trường hợp đặc biệt: guard trả về sớm

Nếu luồng điều khiển **loại bỏ được mọi trường hợp không khớp**, biến có thể được dùng sau `if`:

~~~java
static String normalize(Object value) {
    if (!(value instanceof String text)) {
        return "Không phải chuỗi";
    }
    // Đi tới đây nghĩa là instanceof String text đã thành công.
    return text.trim();
}
~~~

Ví dụ này hợp lệ, vì nhánh có khả năng không khớp luôn kết thúc phương thức bằng `return`. Nó minh họa rằng flow scoping dựa trên các đường đi có thể tiếp tục, không đơn thuần dựa trên số dòng mã.

## 5. Kết hợp nhiều type pattern bằng `&&`

Một điều kiện có thể tạo **nhiều pattern variable**, mỗi biến được giới thiệu ở vị trí tương ứng:

~~~java
Object left = "Go";
Object right = "Java";

if (left instanceof String a
        && right instanceof String b
        && a.length() < b.length()) {
    System.out.println(a + " ngắn hơn " + b); // Go ngắn hơn Java
}
~~~

Luồng xử lý:

1. `left instanceof String a` phải thành công, nếu không dừng ngay.
2. `right instanceof String b` chỉ được chạy sau bước 1; nếu khớp, `b` được ràng buộc.
3. Ở `a.length() < b.length()`, cả `a` lẫn `b` đều chắc chắn đã khớp và có kiểu `String`.
4. Trong thân `if`, cả hai biến đều dùng được.

Pattern variable có tên do lập trình viên chọn; chúng không bắt buộc giống tên biến đầu vào. Nên đặt tên khác nhau cho các biến cùng xuất hiện trong một phạm vi, chẳng hạn `a`/`b` hoặc `firstText`/`secondText`.

Đây là cách kết hợp hữu ích khi cần kiểm tra **hai nguồn dữ liệu độc lập** rồi áp dụng điều kiện liên quan đến cả hai.

## 6. Kết hợp kiểm tra kiểu với guard bảo vệ thao tác tiếp theo

`&&` còn hữu ích để kiểm tra từng điều kiện tiên quyết trước một thao tác có thể thất bại nếu đầu vào không hợp lệ.

Ví dụ với danh sách có kiểu generic chưa biết:

~~~java
Object candidate = java.util.List.of("Spring", 42);

if (candidate instanceof java.util.List<?> list
        && !list.isEmpty()
        && list.get(0) instanceof String first
        && first.length() > 3) {
    System.out.println(first.toUpperCase()); // SPRING
}
~~~

- `candidate instanceof List<?> list`: chỉ tiếp tục nếu đầu vào là một `List`.
- `!list.isEmpty()`: bảo đảm có phần tử ở vị trí 0 trước khi gọi `get(0)`. Nếu bỏ bước này, danh sách rỗng có thể gây `IndexOutOfBoundsException`.
- `list.get(0) instanceof String first`: kiểm tra kiểu thực tế của phần tử đầu và khai báo pattern variable `first`.
- `first.length() > 3`: chỉ chạy sau khi phần tử đầu thật sự là `String`.

Ở đây `List<?>` được sử dụng vì tham số generic không được xác nhận trực tiếp bằng `instanceof List<String>` tại runtime (*type erasure*). Việc xác minh phần tử đầu là `String` được thực hiện riêng bằng type pattern.

Nếu danh sách rỗng hoặc phần tử đầu không phải chuỗi, toàn bộ biểu thức là `false` và nhánh `if` không chạy. Nếu phần tử đầu bằng `null`, phép `instanceof String first` trả về `false`.

**Giới hạn bảo vệ:** short-circuit chỉ tránh việc chạy các toán hạng chưa cần thiết. Nó không tự xử lý exception có thể phát sinh bên trong một toán hạng đã được thực thi; ví dụ `get(0)` vẫn có thể gây lỗi nếu nội dung danh sách thay đổi đồng thời theo cách không an toàn giữa các thao tác. Khi chia sẻ dữ liệu giữa nhiều luồng, còn cần quy tắc đồng bộ và tính nhất quán phù hợp.

## 7. So sánh `&&`, `&` và `||` trong điều kiện có pattern variable

| Toán tử | Cách đánh giá | Có dùng được biến của type pattern bên trái ở toán hạng phải trong dạng dưới đây? |
| --- | --- | --- |
| `&&` | Ngắn mạch: vế phải chỉ chạy khi vế trái `true`. | **Có**: `obj instanceof String s && s.length() > 0`. |
| `&` với boolean | Đánh giá cả hai toán hạng; không ngắn mạch. | **Không**: `obj instanceof String s & s.length() > 0` không bảo đảm `s` được ràng buộc. |
| `||` | Ngắn mạch: vế phải chỉ chạy khi vế trái `false`. | **Không**: `obj instanceof String s || s.length() > 0`, vì vế phải chạy khi pattern bên trái không khớp. |

Các đoạn sau **cố ý sai** và không thuộc chương trình chạy:

~~~java
// Sai: với ||, vế phải có thể chạy khi không phải String.
// if (obj instanceof String s || s.isEmpty()) { ... }

// Sai: & không short-circuit, s không bảo đảm đã khớp ở vế phải.
// if (obj instanceof String s & s.length() > 0) { ... }

// Sai: s xuất hiện trước khi được giới thiệu.
// if (s.length() > 0 && obj instanceof String s) { ... }
~~~

Điều cần nhớ là **chỉ dùng pattern variable sau đoạn đã chứng minh kiểu tương ứng thành công**. Đừng thay `&&` bằng `&` với mục đích “vẫn là toán tử AND”; hai toán tử có cách đánh giá khác nhau và các quy tắc phạm vi khác nhau.

`||` không phải luôn luôn không dùng được với pattern matching. Ví dụ `!(obj instanceof String s) || s.isEmpty()` có cấu trúc luồng khác: khi vế phải được chạy, phép phủ định bên trái đã là `false`, nên pattern gốc đã khớp. Tuy nhiên, trong bài này, mẫu dễ đọc và phổ biến nhất để kiểm tra kiểu rồi bổ sung điều kiện vẫn là `instanceof T variable && predicate(variable)`.

## 8. Kiểu tĩnh của pattern variable và việc kiểm tra `null`

Pattern variable có **kiểu được khai báo trong type pattern**, không tự nhận tất cả phương thức của lớp runtime cụ thể:

~~~java
Object value = new StringBuilder("JVM");

if (value instanceof CharSequence seq
        && seq.length() >= 3
        && seq.charAt(0) == 'J') {
    System.out.println(seq); // JVM
}
~~~

Ở đây `seq` có kiểu tĩnh `CharSequence`. Nó dùng được `length()` và `charAt()` của giao diện đó, nhưng không thể gọi tùy ý phương thức chỉ có ở `StringBuilder` nếu không kiểm tra hoặc chuyển kiểu phù hợp.

Khi đối tượng bên trái là `null`, `instanceof CharSequence seq` trả về `false`, nên không có lời gọi phương thức trên `seq`. Vì vậy biểu thức sau là an toàn với `null` của **chính đối tượng đang kiểm tra**:

~~~java
static boolean isLongString(Object value) {
    return value instanceof String s && s.length() >= 4;
}
~~~

Nhưng nếu toán hạng sau truy cập một **giá trị khác** có thể bằng `null` thì vẫn cần kiểm tra. Chẳng hạn:

~~~java
static boolean equalsIgnoreCase(Object input, String expected) {
    return input instanceof String s
            && expected != null
            && s.equalsIgnoreCase(expected);
}
~~~

`instanceof` của `input` không cung cấp bảo đảm nào về `expected`; điều kiện `expected != null` là quy tắc của đầu vào riêng này. (Bản thân `String.equalsIgnoreCase(null)` trả về `false`; ví dụ thêm điều kiện để minh họa nguyên tắc bảo vệ một tham chiếu khác.)

## 9. Ví dụ hoàn chỉnh, chạy được bằng Java 17+

Tạo tệp **`TypePatternAndDemo.java`** với toàn bộ nội dung:

~~~java
import java.util.List;

public class TypePatternAndDemo {
    static String describe(Object value) {
        if (value instanceof String text
                && !text.isBlank()
                && text.length() >= 4) {
            return "Chuỗi hợp lệ: " + text.toUpperCase();
        }
        return "Không đạt điều kiện";
    }

    static String compare(Object left, Object right) {
        if (left instanceof String a
                && right instanceof String b
                && a.length() < b.length()) {
            return a + " ngắn hơn " + b;
        }
        return "Không so sánh được";
    }

    static String firstLongString(Object value) {
        if (value instanceof List<?> list
                && !list.isEmpty()
                && list.get(0) instanceof String first
                && first.length() > 3) {
            return "Phần tử đầu: " + first;
        }
        return "Không có chuỗi đầu phù hợp";
    }

    static String classify(Object value) {
        if (value instanceof CharSequence seq
                && seq.length() > 2
                && seq.charAt(0) == 'J') {
            return "Bắt đầu bằng J: " + seq;
        }
        return "Khác";
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe("  "));
        System.out.println(describe(null));
        System.out.println(compare("Go", "Java"));
        System.out.println(compare("Java", 5));
        System.out.println(firstLongString(List.of("Spring", 7)));
        System.out.println(firstLongString(List.of()));
        System.out.println(firstLongString(List.of(42)));
        System.out.println(classify(new StringBuilder("JVM")));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac --release 17 TypePatternAndDemo.java
java TypePatternAndDemo
~~~

Đầu ra:

~~~text
Chuỗi hợp lệ: JAVA
Không đạt điều kiện
Không đạt điều kiện
Go ngắn hơn Java
Không so sánh được
Phần tử đầu: Spring
Không có chuỗi đầu phù hợp
Không có chuỗi đầu phù hợp
Bắt đầu bằng J: JVM
~~~

Giải thích theo từng hàm:

- **`describe`** kiểm tra `String`, loại chuỗi chỉ chứa khoảng trắng, rồi mới xét độ dài. Với `null`, toán hạng `instanceof` đã `false`, các phương thức của `text` không chạy.
- **`compare`** buộc hai đối tượng đều là `String` rồi dùng hai pattern variable `a`, `b` trong cùng điều kiện.
- **`firstLongString`** bảo đảm có danh sách, có phần tử đầu, phần tử đầu là chuỗi và đủ dài trước khi lấy kết quả.
- **`classify`** chứng minh type pattern có thể dùng với giao diện `CharSequence`, không chỉ với lớp `String`.

Ví dụ sử dụng các tính năng sẵn có trong Java 17; `String.isBlank()` đã xuất hiện từ Java 11 và `List.of()` từ Java 9.

## 10. Sai lầm thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Đọc biến pattern ở vế phải của `||` sau một phép `instanceof` dương | Vế phải `||` chạy khi kiểm tra kiểu bên trái thất bại; biến chưa được ràng buộc. | Dùng `&&` khi muốn kiểm tra kiểu trước, rồi dùng biến ở điều kiện tiếp theo. |
| Dùng `&` thay `&&` | `&` không ngắn mạch, dẫn tới sai phạm vi của biến và có thể đánh giá điều kiện chưa an toàn. | Dùng `&&` để bảo đảm điều kiện sau chỉ chạy khi điều kiện trước đúng. |
| Tham chiếu pattern variable trong `else` của `if (obj instanceof T t && guard)` | Nhánh `else` không bảo đảm `obj` đã khớp `T`. | Chỉ dùng `t` ở nơi luồng điều khiển chắc chắn match; tổ chức nhánh hoặc return sớm. |
| Dùng pattern variable sau câu `if` thông thường | Không có cơ sở chắc chắn cho mọi đường đi. | Giới hạn phép dùng trong nhánh đúng hoặc dùng guard với đường đi không khớp kết thúc ngay. |
| Kiểm tra `list.get(0) instanceof String s` trước `!list.isEmpty()` | Có thể ném `IndexOutOfBoundsException` trên danh sách rỗng. | Đặt điều kiện về sự tồn tại trước thao tác truy cập. |
| Giả định pattern variable là kiểu runtime cụ thể hơn khai báo | Có thể gọi phương thức không có trong kiểu tĩnh và lỗi biên dịch. | Chọn type pattern đúng mức (ví dụ `String s`) hoặc kiểm tra thêm kiểu trước khi dùng API riêng. |
| Cho rằng `&&` tự bắt mọi exception | Toán hạng đã chạy vẫn có thể ném exception. | Kiểm tra tiền điều kiện đầy đủ và quản lý dữ liệu dùng chung đúng cách. |
| Ép kiểu lại sau khi `instanceof T t` thành công | Làm mã dài và dễ sai không cần thiết. | Dùng trực tiếp `t`, biến đã có kiểu tĩnh `T`. |

## 11. Bài tập tự kiểm tra

**Bài 1.** Cho `Object value`. Viết một biểu thức boolean trả về `true` khi `value` là chuỗi có ít nhất 5 ký tự và bắt đầu bằng `"A"`, dùng **một** type pattern cùng `&&`.

**Bài 2.** Cho `Object left, right`. Chỉ in ra tổng khi cả hai là `Integer` và tổng lớn hơn 10. Hãy dùng hai type pattern và `&&`, rồi giải thích vị trí nào có thể dùng đồng thời hai biến.

**Bài 3.** Chỉ ra lỗi trong đoạn sau và sửa lại:

~~~java
// Cố ý không biên dịch:
if (value instanceof String s || s.length() > 2) {
    System.out.println("OK");
}
~~~

**Bài 4.** Vì sao điều kiện `value instanceof List<?> list && !list.isEmpty() && list.get(0) instanceof String first` an toàn hơn việc gọi `list.get(0)` trước khi kiểm tra `isEmpty()`? Điều gì xảy ra nếu phần tử đầu là `null`?

**Đáp án gợi ý:**

~~~java
// 1
boolean accepted = value instanceof String text
        && text.length() >= 5
        && text.startsWith("A");

// 2
if (left instanceof Integer a
        && right instanceof Integer b
        && a + b > 10) {
    System.out.println(a + b);
}

// 3
if (value instanceof String s && s.length() > 2) {
    System.out.println("OK");
}
~~~

Ở bài 2, `a` và `b` có thể dùng trong điều kiện thứ ba và trong thân `if` sau khi hai phép khớp tương ứng thành công. Với bài 4, short-circuit bảo đảm không gọi `get(0)` trên danh sách rỗng; nếu phần tử đầu bằng `null` thì `instanceof String first` là `false` và không có biến `first` nào được dùng sau đó.

## 12. Tổng kết kiến thức áp dụng

Mẫu tổng quát cần ghi nhớ là:

~~~java
if (expression instanceof TargetType variable
        && conditionUsing(variable)) {
    // variable đã được ràng buộc và có kiểu tĩnh TargetType.
}
~~~

Khi ghép nhiều type pattern, đặt **kiểm tra kiểu và điều kiện tiên quyết** trước, đặt **thao tác dùng pattern variable** sau. `&&` đảm bảo tính ngắn mạch; cơ chế *flow scoping* đảm bảo biến chỉ được sử dụng ở các vị trí mà phép khớp kiểu tương ứng chắc chắn đã thành công.

### Tài liệu tham khảo

- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): chuẩn hóa cú pháp type pattern trong `instanceof` từ Java 16.
- [Java Language Specification 17 — §6.3: Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se17/html/jls-6.html#jls-6.3): quy tắc phạm vi của pattern variables.
- [Java Language Specification 17 — §15.23: Conditional-And Operator `&&`](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.23): đánh giá ngắn mạch của `&&`.
- [Oracle Java — Pattern Matching for instanceof](https://docs.oracle.com/en/java/javase/17/language/pattern-matching-instanceof.html): ví dụ dùng type pattern và flow scoping.
