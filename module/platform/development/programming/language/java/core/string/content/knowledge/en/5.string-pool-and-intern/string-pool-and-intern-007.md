# Vì sao quan sát `==` trên literal không thay thế so sánh nội dung của `String`

Khi thử Java, nhiều người thấy:

```java
String a = "Java";
String b = "Java";
System.out.println(a == b); // true
```

Rồi kết luận rằng có thể dùng `==` để kiểm tra hai chuỗi có cùng chữ. **Đó là kết luận sai.** Kết quả `true` ở đây đến từ cơ chế *string pool*: hai literal cùng nội dung được tham chiếu tới cùng một đối tượng `String`. Toán tử `==` vẫn chỉ so sánh **danh tính đối tượng (object identity)**, không tự so sánh từng ký tự.

Với nhu cầu kiểm tra hai giá trị văn bản có giống nhau hay không, dùng `String.equals(...)` (hoặc một phép so sánh giá trị phù hợp với yêu cầu nghiệp vụ). Bài học này giải thích tại sao những phép thử nhỏ trên literal dễ gây hiểu nhầm và cách viết code đúng cho chuỗi đến từ đầu vào thực tế.

## 1. Ba thứ khác nhau: biến, đối tượng và nội dung

Xét mã:

```java
String first = "core";
String second = first;
String third = new String("core");
```

- **Biến tham chiếu** `first`, `second` và `third` lưu các giá trị tham chiếu đến đối tượng `String`.
- **Đối tượng `String`** có danh tính riêng trong bộ nhớ; hai biến có thể trỏ đến cùng một đối tượng.
- **Nội dung chuỗi** là dãy ký tự, ở đây đều là `"core"`.

Mô hình tham chiếu:

```text
first  ──┐
         ├──────────> String "core" (đối tượng từ pool)
second ──┘

third ──────────────> String "core" (đối tượng do new tạo)
```

Khi so sánh hai biến kiểu tham chiếu:

- `first == second` hỏi: «Hai biến có trỏ tới **cùng một đối tượng** không?» → `true`.
- `first == third` hỏi cùng câu hỏi đó → `false`.
- `first.equals(third)` hỏi: «Hai đối tượng `String` có **cùng nội dung** không?» → `true`.

Dù các chuỗi cùng chữ, identity và value không phải một khái niệm. Dùng `==` để kiểm tra nội dung chỉ tình cờ cho kết quả mong đợi khi hai bên đang tham chiếu tới cùng đối tượng.

## 2. Tại sao hai literal giống nhau có thể cho `== true`?

Java lưu các chuỗi literal dưới dạng đã được *intern* trong **string pool**. Theo ngữ nghĩa Java, các literal cùng nội dung (và các biểu thức chuỗi hằng có cùng nội dung) tham chiếu đến đối tượng `String` chuẩn tắc trong pool.

```java
String a = "Java";
String b = "Java";
System.out.println(a == b); // true
```

Đây là đặc tính có chủ ý của ngôn ngữ và cách tổ chức literal. Nó giúp sử dụng lại đối tượng cho các giá trị hằng giống nhau. Tuy nhiên, điều này **không biến `==` thành phép so sánh nội dung**. Khi hai tham chiếu khác đối tượng, `==` vẫn trả về `false` ngay cả khi các ký tự bằng nhau.

Có thể hình dung câu hỏi sai thường gặp như sau:

> «Hai literal cùng chữ trả về `true` với `==`, vậy mọi chuỗi cùng chữ cũng sẽ trả về `true`.»

Bước suy luận sai là đánh đồng «cùng nội dung» với «luôn cùng tham chiếu». Pool giải thích **vì sao trường hợp literal đặc biệt có thể chia sẻ identity**; nó không đưa ra bảo đảm cho mọi chuỗi được sinh ra lúc chạy.

### Ví dụ 1: literal và bản sao có cùng nội dung

Tạo tệp `LiteralIdentityDemo.java`:

```java
public class LiteralIdentityDemo {
    public static void main(String[] args) {
        String a = "Java";
        String b = "Java";
        String copied = new String("Java");

        System.out.println(a == b);
        System.out.println(a == copied);
        System.out.println(a.equals(copied));
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac LiteralIdentityDemo.java
java LiteralIdentityDemo
```

Kết quả chính xác:

```text
true
false
true
```

Dòng đầu đúng vì literal `"Java"` được dùng chung qua pool. Dòng thứ hai sai vì `new String("Java")` tạo **đối tượng mới** có identity khác. Dòng cuối đúng vì `equals` so sánh nội dung hai `String`.

Cả ba phép so sánh đều đang làm đúng công việc của chúng. Lỗi nằm ở việc chọn `==` khi thật ra bài toán yêu cầu so sánh văn bản.

## 3. Chuỗi hằng tại thời điểm biên dịch cũng có thể dùng chung đối tượng pooled

Không chỉ literal viết nguyên một lần mới có thể nhận cùng tham chiếu. **Biểu thức hằng chuỗi (constant expression)** được đánh giá tại thời điểm biên dịch cũng có thể trở thành cùng giá trị literal/interned.

Ví dụ:

```java
String a = "Java";
String b = "Ja" + "va";
System.out.println(a == b); // true
```

`"Ja" + "va"` là biểu thức hằng, được tính tại thời điểm biên dịch thành `"Java"`. Vì vậy `b` nhận tham chiếu tới cùng chuỗi đã intern.

Tương tự, một **constant variable** `final String` được khởi tạo bằng biểu thức hằng có thể góp phần tạo biểu thức hằng:

```java
final String prefix = "Ja";
String c = prefix + "va";
System.out.println(c == "Java"); // true
```

Điểm cần nhớ: **`final` không tự động làm mọi phép nối trở thành biểu thức hằng**. Giá trị khởi tạo và loại biểu thức phải thỏa định nghĩa *constant expression* của ngôn ngữ. Ví dụ, nếu một biến `final` nhận giá trị từ phương thức lúc chạy thì phép nối với nó không phải biểu thức hằng chỉ vì nó có `final`.

### Ví dụ 2: kiểm tra literal và phép nối hằng

Tạo tệp `ConstantExpressionDemo.java`:

```java
public class ConstantExpressionDemo {
    public static void main(String[] args) {
        String literal = "Java";
        String folded = "Ja" + "va";

        final String compileTimePrefix = "Ja";
        String foldedWithFinal = compileTimePrefix + "va";

        String runtimePrefix = new String("Ja");
        String constructedAtRuntime = runtimePrefix + "va";

        System.out.println(literal == folded);
        System.out.println(literal == foldedWithFinal);
        System.out.println(literal.equals(constructedAtRuntime));
        System.out.println(literal == constructedAtRuntime);
    }
}
```

```bash
javac ConstantExpressionDemo.java
java ConstantExpressionDemo
```

Kết quả với Java 17+:

```text
true
true
true
false
```

Hai lần `true` đầu không chứng minh `==` so sánh chữ: chúng chỉ phản ánh phép nối **hằng** cùng nhận đối tượng pooled. Với `runtimePrefix` là đối tượng tạo lúc chạy, phép nối sinh ra giá trị `"Java"` mới; `equals` xác nhận nội dung đúng, còn `==` cho thấy nó không cùng identity với literal ở ví dụ này.

Trong ứng dụng thực tế, chuỗi nhận từ mạng, bàn phím, file, cơ sở dữ liệu và kết quả xử lý lúc chạy không được giả định có cùng identity với literal dù nội dung trùng khớp.

## 4. Chuỗi từ bên ngoài có thể bằng literal mà `==` vẫn `false`

Một ví dụ rất gần với việc đọc dữ liệu bên ngoài là tạo chuỗi từ mảng ký tự:

```java
char[] incoming = {'o', 'k'};
String fromInput = new String(incoming);

System.out.println(fromInput == "ok");       // false
System.out.println(fromInput.equals("ok"));   // true
```

`fromInput` và literal `"ok"` có cùng nội dung. Tuy nhiên, constructor `String(char[])` tạo một đối tượng `String` từ dữ liệu đầu vào, nên tham chiếu của nó khác tham chiếu literal pooled. Nếu code phân nhánh theo `if (fromInput == "ok")`, nhánh này sẽ **không chạy** dù người dùng đã nhập đúng chữ.

### Ví dụ 3: một nhánh lỗi và một nhánh đúng

Tạo tệp `StringDecisionDemo.java`:

```java
public class StringDecisionDemo {
    public static void main(String[] args) {
        String expected = "READY";
        String received = new String(
                new char[] {'R', 'E', 'A', 'D', 'Y'}
        );

        if (received == expected) {
            System.out.println("Identity matched");
        } else {
            System.out.println("Identity did not match");
        }

        if (expected.equals(received)) {
            System.out.println("Content matched");
        } else {
            System.out.println("Content did not match");
        }
    }
}
```

```bash
javac StringDecisionDemo.java
java StringDecisionDemo
```

Kết quả:

```text
Identity did not match
Content matched
```

Chỉ thay đổi **cách tạo đối tượng** mà nội dung vẫn như nhau đã khiến `==` chuyển từ `true` sang `false`. Đó chính là lý do không nên dùng một phép thử trên hai literal để xác nhận logic so sánh nội dung của chương trình.

## 5. `String.intern()` thay đổi điều gì, và không thay đổi điều gì?

`String.intern()` trả về một **tham chiếu chuẩn tắc** tới chuỗi có cùng nội dung trong string pool. Nếu chuỗi tương ứng đã có trong pool, nó trả về tham chiếu ở pool. Nếu chưa có, pool sẽ bảo đảm có một đối tượng chuẩn tắc tương ứng và trả về tham chiếu đó.

Ví dụ:

```java
String literal = "topic";
String dynamic = new String("topic");
String canonical = dynamic.intern();

System.out.println(literal == dynamic);   // false
System.out.println(literal == canonical); // true
System.out.println(dynamic == canonical); // false
```

Điểm quan trọng:

1. `dynamic` được tạo riêng qua `new`, vì vậy nó có identity khác `literal`.
2. `dynamic.intern()` trả về tham chiếu chuẩn tắc cho nội dung `"topic"`; literal `"topic"` đã hiện diện trong ví dụ.
3. Gọi `intern()` **không gán lại biến `dynamic`** và không biến đối tượng mà `dynamic` đang tham chiếu thành đối tượng literal.

### Ví dụ 4: kiểm tra rõ trước và sau `intern()`

Tạo tệp `InternDemo.java`:

```java
public class InternDemo {
    public static void main(String[] args) {
        String literal = "topic";
        String dynamic = new String("topic");
        String canonical = dynamic.intern();

        System.out.println(literal == dynamic);
        System.out.println(literal == canonical);
        System.out.println(dynamic == canonical);
        System.out.println(literal.equals(dynamic));
    }
}
```

```bash
javac InternDemo.java
java InternDemo
```

Kết quả:

```text
false
true
false
true
```

`intern()` có thể phục vụ những thiết kế cần chuẩn tắc hóa tham chiếu có chủ đích. Tuy nhiên, không cần (và thường không nên) gọi `intern()` chỉ để dùng `==` thay `equals`. Việc tự quản lý chuẩn tắc hóa làm code phụ thuộc thêm vào chiến lược chia sẻ đối tượng và có thể tốn tài nguyên mà yêu cầu so sánh nội dung không cần đến.

Một nguyên tắc tốt: **pool/intern giải thích nguồn gốc tham chiếu; `equals` giải quyết nhu cầu so sánh nội dung.**

## 6. Viết phép so sánh nội dung như thế nào?

Với hai `String` khác `null`:

```java
String expected = "Java";
String actual = new String("Java");

boolean sameContent = expected.equals(actual); // true
```

`String.equals(Object other)` trả về `true` khi đối số là một `String` có cùng dãy ký tự. Nó không yêu cầu cùng đối tượng hay cùng nguồn khởi tạo.

Về hướng gọi và `null`:

- Nếu biết chắc `a != null`, dùng `a.equals(b)`.
- Nếu có một hằng mong đợi, dùng `"READY".equals(received)`: nhận `false` an toàn khi `received == null`.
- Nếu **cả hai phía có thể null**, dùng `Objects.equals(a, b)` (import `java.util.Objects`); hai giá trị cùng `null` cho `true`.
- Để kiểm tra một tham chiếu **có null hay không**, dùng `value == null` hoặc `value != null`. Đây là so sánh tham chiếu đúng mục đích.
- Chỉ dùng `equalsIgnoreCase` khi nghiệp vụ thực sự yêu cầu bỏ qua khác biệt hoa/thường; nó không phải lựa chọn mặc định cho mọi văn bản.

### Ví dụ 5: so sánh an toàn khi có `null`

Tạo tệp `NullSafeComparisonDemo.java`:

```java
import java.util.Objects;

public class NullSafeComparisonDemo {
    public static void main(String[] args) {
        String received = null;

        System.out.println("READY".equals(received));
        System.out.println(Objects.equals("READY", received));
        System.out.println(Objects.equals(null, received));

        received = new String("READY");
        System.out.println("READY".equals(received));
        System.out.println("READY" == received);
    }
}
```

```bash
javac NullSafeComparisonDemo.java
java NullSafeComparisonDemo
```

Kết quả:

```text
false
false
true
true
false
```

Nếu viết `received.equals("READY")` khi `received == null`, chương trình sẽ ném `NullPointerException`. Không nên «sửa» lỗi này bằng `received == "READY"`: phép so sánh tham chiếu chỉ che mất lỗi null trong ví dụ nhỏ rồi gây ra lỗi logic khi dữ liệu hợp lệ đến từ nơi khác.

## 7. So sánh nhanh: kết quả nào được bảo đảm?

| Hai biểu thức được so sánh | `==` | `equals` | Giải thích |
| --- | --- | --- | --- |
| `"x"` và `"x"` | `true` | `true` | Hai literal cùng giá trị đã intern |
| `"x"` và `"x" + ""` | `true` | `true` | Phép nối toàn hằng được tính ở compile time |
| `a` và `b` sau `String b = a` | `true` | `true` khi `a` là `String` khác null | Cùng tham chiếu; với null, không được gọi `a.equals(...)` |
| `"x"` và `new String("x")` | `false` | `true` | `new` tạo đối tượng `String` khác |
| `"x"` và `new String("x").intern()` | `true` | `true` | `intern()` trả về tham chiếu pooled |
| `"x"` và `new String("y")` | `false` | `false` | Khác đối tượng và khác nội dung |

Bảng này sử dụng các biểu thức có điều kiện rõ ràng. Với một `String` bất kỳ lấy từ hệ thống bên ngoài, **không thể đoán kết quả `==` chỉ từ chữ hiển thị**. Không nên coi `== true` là «nội dung bằng nhau» theo hợp đồng API so sánh giá trị, dù cùng tham chiếu tất nhiên dẫn tới cùng nội dung tại thời điểm đó.

## 8. Hai lỗi dễ lọt qua kiểm thử

### Lỗi A — kiểm thử chỉ dùng literal

```java
static boolean isAdmin(String role) {
    return role == "ADMIN"; // Sai mục đích nếu kiểm tra nội dung.
}
```

Nếu thử `isAdmin("ADMIN")`, kết quả thường là `true` và có thể khiến bạn nghĩ hàm đúng. Nhưng khi nguồn dữ liệu tạo đối tượng mới cùng nội dung, ví dụ `isAdmin(new String("ADMIN"))`, kết quả là `false`.

Sửa thành:

```java
static boolean isAdmin(String role) {
    return "ADMIN".equals(role);
}
```

Đây là đoạn minh họa phương thức, có thể đặt trong một lớp Java; nó không phải chương trình độc lập vì chưa có `main`. Phép so sánh mới trả về `true` cho các `String` có nội dung chính xác `"ADMIN"` bất kể cách tạo đối tượng. Khi `role == null`, nó trả về `false`.

### Lỗi B — dùng `intern()` để hợp thức hóa `==`

Một cách sửa kém cần thiết là:

```java
String received = new String("READY");
if (received.intern() == "READY") {
    // ...
}
```

Điều này hoạt động với ví dụ cụ thể, nhưng làm logic dựa vào pool, còn người đọc phải hiểu chiến lược canonicalization. Cách trực tiếp và đúng nghĩa hơn:

```java
String received = new String("READY");
if ("READY".equals(received)) {
    // ...
}
```

Các phương thức so sánh giá trị đều thể hiện ý định rõ hơn việc thay đổi cách quản lý tham chiếu chỉ để tạo điều kiện cho `==`.

## 9. Khi nào `==` với `String` vẫn có ý nghĩa?

`==` không phải toán tử «cấm dùng» trên `String`. Nó đúng khi điều bạn muốn kiểm tra **thực sự là identity**, chẳng hạn:

- `value == null` để kiểm tra không có tham chiếu.
- `a == b` trong mã nội bộ cố ý xác định hai biến có cùng đối tượng hay không, ví dụ khi nghiên cứu pool hoặc kiểm tra tối ưu hóa; kết quả này nói về *đối tượng*, không thay thế bước kiểm tra nội dung.
- Logic có một hợp đồng riêng thật sự dựa trên identity (trường hợp hiếm và cần được nêu rõ).

Nếu câu hỏi nghiệp vụ là «mã trạng thái có đúng `READY` không?», «username có giống nhau không?», hay «giá trị text ở hai nguồn có bằng nhau không?», thì câu trả lời cần phép so sánh **nội dung**. Đừng thay hợp đồng nghiệp vụ bằng giả định về pooling.

Cũng cần nhớ: `String` bất biến nên hai biến chia sẻ một đối tượng pooled không có nghĩa là sửa chuỗi của một biến sẽ tác động đến biến kia. Gán lại biến hoặc tạo giá trị chuỗi mới không sửa nội dung đối tượng `String` cũ.

## 10. Tự kiểm tra

### Câu 1 — các giá trị đúng hay sai?

```java
String x = "cat";
String y = "cat";
String z = new String("cat");

System.out.println(x == y);
System.out.println(y == z);
System.out.println(x.equals(z));
```

Đáp án:

```text
true
false
true
```

`x` và `y` cùng tham chiếu literal. `z` là đối tượng riêng có cùng nội dung.

### Câu 2 — lý do thật sự của `true`?

```java
String text = "abcdef";
String built = "abc" + "def";
System.out.println(text == built);
```

Đáp án là `true` vì phép nối toàn literal là biểu thức hằng được tính tại thời điểm biên dịch. Điều này **không** có nghĩa toán tử `==` so từng ký tự.

### Câu 3 — thử trường hợp data đến từ runtime

```java
String expected = "abc";
String actual = new String(new char[] {'a', 'b', 'c'});

System.out.println(expected == actual);
System.out.println(expected.equals(actual));
```

Đáp án:

```text
false
true
```

Chuỗi runtime không cùng identity với literal dù nội dung bằng nhau.

### Câu 4 — chọn phép so sánh

Giả sử `String token` có thể bằng `null` và bạn muốn biết token có chính xác là `"OK"` không. Chọn `token == "OK"`, `token.equals("OK")` hay `"OK".equals(token)`?

**Đáp án:** `"OK".equals(token)`. Nó trả về `true` khi nội dung khớp, `false` nếu `token` khác hoặc `null`. `token.equals("OK")` có nguy cơ ném `NullPointerException`; `token == "OK"` kiểm tra identity sai mục đích.

## Kết luận

**`==` trên `String` so sánh tham chiếu; `equals` so sánh nội dung.** Hai literal cùng chữ, hoặc hai biểu thức hằng có cùng kết quả, có thể cùng tham chiếu nhờ string pool nên `==` trả về `true`. Đó là một quan sát đúng về **identity của literal**, nhưng **không** phải bảo đảm rằng mọi chuỗi có cùng chữ được tạo ở thời điểm chạy sẽ cùng tham chiếu. Với dữ liệu văn bản thực tế, hãy viết phép so sánh theo yêu cầu giá trị ngay từ đầu, sử dụng `equals` và xử lý `null` rõ ràng.