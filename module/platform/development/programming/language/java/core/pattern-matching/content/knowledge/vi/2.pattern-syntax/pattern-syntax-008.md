# Pattern matching khác với expression evaluation trong Java

Trong Java, **expression evaluation** (đánh giá biểu thức) là quá trình tính ra giá trị của một biểu thức; **pattern matching** (khớp mẫu) là quá trình kiểm tra một giá trị có phù hợp với một mẫu hay không và, khi có các biến được khai báo trong mẫu, **gắn giá trị tương ứng cho các pattern variable**. Hai cơ chế có thể phối hợp trong cùng một câu lệnh nhưng trả lời hai câu hỏi khác nhau:

- **Expression evaluation:** “Biểu thức này tạo ra giá trị nào, theo quy tắc đánh giá nào?”
- **Pattern matching:** “Giá trị đã có có khớp cấu trúc/kiểu mà pattern mô tả không, và nếu khớp thì có thể dùng những biến nào?”

Điểm dễ nhầm nhất: **`instanceof` là một biểu thức có kết quả kiểu `boolean`, nhưng `String text` nằm sau `instanceof` là một *pattern*, không phải biểu thức thông thường.** Khi đánh giá cả biểu thức `instanceof`, Java thực hiện việc khớp pattern bên trong nó. Vì vậy “đánh giá biểu thức” và “khớp pattern” là hai tầng cơ chế có thể lồng nhau, không phải hai tính năng loại trừ nhau.

## 1. Expression evaluation: tính ra một giá trị

Ví dụ các biểu thức Java thông thường:

```java
int sum = 2 + 3;                     // 2 + 3 được đánh giá thành 5
int size = "Java".length();          // lời gọi được đánh giá thành 4
boolean same = "Java".equals("Go");  // được đánh giá thành false
```

Một biểu thức có kiểu do Java kiểm tra tại thời điểm biên dịch; khi chạy, chương trình đánh giá các toán hạng/lời gọi liên quan và tạo ra **giá trị** hoặc hoàn thành bất thường (chẳng hạn ném exception). Java quy định thứ tự đánh giá, việc đánh giá ngắn mạch với `&&`/`||` và các tác dụng phụ như gọi hàm, thay đổi trạng thái.

Chẳng hạn:

```java
boolean ok = ready && checkExpensiveCondition();
```

`checkExpensiveCondition()` chỉ được gọi khi `ready` là `true`. Kết quả của **toàn bộ** biểu thức là một giá trị `boolean`. Không có pattern variable nào được khai báo hoặc gắn giá trị chỉ bởi biểu thức này.

**Đánh giá ra `true` không tự động có nghĩa là đang dùng pattern matching.** So sánh `a > b`, `equals(...)` và nhiều phương thức kiểm tra khác cũng tạo ra `boolean` mà không chứa pattern.

## 2. Pattern matching: thử mẫu và gắn biến khi khớp

Xem ví dụ dành cho Java 17+:

```java
Object input = "Java";

if (input instanceof String text) {
    System.out.println(text.length());
}
```

Phân tích các vai trò:

| Cú pháp | Vai trò | Điều xảy ra |
| --- | --- | --- |
| `input` | **Target expression** | Được đánh giá để lấy giá trị đang cần kiểm tra, ở đây là tham chiếu tới chuỗi `"Java"`. |
| `String text` | **Type pattern** | Thử xem giá trị runtime có khác `null` và tương thích với `String` không. |
| `text` | **Pattern variable** | Khi pattern khớp, được binding tới cùng đối tượng, với kiểu tĩnh `String`. |
| `input instanceof String text` | **Biểu thức `instanceof`** | Có kết quả `true` hoặc `false` tùy kết quả khớp pattern. |
| `text.length()` | **Biểu thức lời gọi phương thức** | Chỉ được phép dùng nơi Java chứng minh `text` đã được binding; kết quả ở đây là `4`. |

Luồng hoạt động:

```text
Đánh giá target expression: input
                 |
                 v
        giá trị runtime
                 |
                 v
     thử type pattern String text
          /                 \
       khớp               không khớp
        |                      |
  binding text             không binding
        |                      |
 instanceof = true       instanceof = false
        |
 dùng text ở nơi có flow scoping hợp lệ
```

Type pattern **không tạo một `String` mới**, không ép đối tượng sang một lớp khác và không tự biến đổi dữ liệu. Nó kiểm tra khả năng phù hợp và cho phép một tên biến có kiểu tĩnh hữu ích tham chiếu tới đối tượng đã khớp. Với `input` khai báo kiểu `Object`, trình biên dịch không cho gọi `input.length()`, nhưng trong nhánh khớp, `text.length()` hợp lệ vì `text` có kiểu `String`.

Với `input = 42` hoặc `input = null`, mẫu `String text` không khớp. Biểu thức `instanceof` trả về `false`; không có binding thành công nào cho `text`.

## 3. Phân biệt cú pháp: đâu là expression, đâu là pattern?

Cùng các từ `String` và `text` có thể xuất hiện ở các ngữ cảnh khác nhau:

```java
String text = "Java";                 // khai báo biến cục bộ, có initializer
Object value = "Java";

boolean matched = value instanceof String s; // instanceof expression + type pattern
```

- `String text = "Java"` là **khai báo biến** với biểu thức khởi tạo `"Java"`, không phải mẫu dùng để khớp.
- `String s` trong `value instanceof String s` là **type pattern**. Ở đây pattern được đặt trong cú pháp cho phép pattern (sau `instanceof`).
- `value instanceof String s` là **toàn bộ biểu thức** được đánh giá thành `boolean`. Pattern `String s` tự nó không phải một biểu thức `boolean` độc lập.
- `matched` chỉ lưu `true`/`false`. Việc lưu kết quả này không làm biến `s` tự nhiên có phạm vi sử dụng tại câu lệnh kế tiếp.

Ví dụ cố ý không hợp lệ:

```java
Object value = "Java";
boolean matched = value instanceof String s;
// System.out.println(s.length()); // LỖI biên dịch: s không ở trong scope tại đây.

// boolean another = String s;      // LỖI: một type pattern không là expression.
```

Khi cần thao tác với giá trị đã khớp, hãy đặt nó vào ngữ cảnh mà Java chứng minh được việc khớp:

```java
Object value = "Java";

if (value instanceof String s) {
    System.out.println(s.length()); // Hợp lệ: kết quả là 4
}
```

## 4. Một biểu thức `instanceof` gồm hai hoạt động khác nhau

Cú pháp:

```java
targetExpression instanceof Type patternVariable
```

Để đánh giá **biểu thức** `instanceof`, Java làm các bước chính:

1. Đánh giá `targetExpression` để nhận một giá trị tham chiếu. Nếu là lời gọi hàm, hàm có thể có tác dụng phụ hoặc ném exception. Phép khớp mẫu **không bỏ qua** những tác dụng đó.
2. Thử **type pattern** trên giá trị đã nhận. Type pattern không khớp `null`; với đối tượng khác `null`, phải phù hợp kiểu mà mẫu yêu cầu.
3. Nếu khớp, tạo binding cho pattern variable; kết quả biểu thức `instanceof` là `true`. Nếu không khớp, kết quả là `false` và không có binding thành công.
4. Nếu biểu thức nằm trong `if`, `&&`, toán tử điều kiện hoặc ngữ cảnh hỗ trợ flow scoping khác, Java xét đường đi điều khiển để quyết định pattern variable có được sử dụng ở chỗ tiếp theo hay không.

Do đó, **biểu thức target được đánh giá để có dữ liệu thử mẫu**; còn **mẫu mô tả cách kiểm tra và binding dữ liệu đó**. Khớp mẫu không phải là việc tính biểu thức phía bên phải `instanceof` thành một đối tượng hay một giá trị `boolean` riêng lẻ.

## 5. Ví dụ chạy được: target được đánh giá, pattern được khớp, điều kiện tiếp tục được đánh giá

Lưu tệp `PatternVsExpressionDemo.java`:

```java
public class PatternVsExpressionDemo {
    static Object load(String data) {
        System.out.println("evaluate target");
        return data;
    }

    static void inspect(String input) {
        if (load(input) instanceof String text && text.length() > 3) {
            System.out.println("matched: " + text.toUpperCase());
        } else {
            System.out.println("no match");
        }
    }

    public static void main(String[] args) {
        inspect("Java");
        inspect("Go");
        inspect(null);
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac PatternVsExpressionDemo.java
java PatternVsExpressionDemo
```

Kết quả:

```text
evaluate target
matched: JAVA
evaluate target
no match
evaluate target
no match
```

Giải thích ba lượt:

1. Với `"Java"`: biểu thức `load(input)` được đánh giá **một lần**, in ra `evaluate target` rồi trả về chuỗi. Pattern `String text` khớp và binding `text`. Chỉ lúc đó, biểu thức `text.length() > 3` ở vế phải `&&` mới được đánh giá thành `true`; nhánh đầu in `matched: JAVA`.
2. Với `"Go"`: type pattern **vẫn khớp** vì `"Go"` là `String`. Nhưng biểu thức `text.length() > 3` là `false`, nên đi vào `else`. Dòng `no match` là thông báo tổng quát của chương trình: **không được suy ra rằng pattern đã thất bại** chỉ từ việc toàn bộ điều kiện `if` sai.
3. Với `null`: biểu thức target vẫn được đánh giá và vẫn in `evaluate target`; type pattern không khớp. Vế phải `&&` **không được thực thi**; nhờ vậy không có lời gọi `text.length()` trên giá trị chưa được binding.

Ví dụ thể hiện ba cơ chế riêng: đánh giá target; thử pattern/binding; tiếp tục đánh giá một biểu thức `boolean` khác qua `&&`. Với một lần đánh giá của `if` trên đây, `load` chỉ được gọi một lần; nếu tự viết hai phép kiểm tra riêng chứa `load(...)`, chúng là hai lần đánh giá khác nhau.

## 6. Flow scoping: biến xuất hiện nhờ pattern, được dùng nhờ luồng điều khiển

Thông thường, biến cục bộ có phạm vi xác định theo cấu trúc khai báo và khối lệnh. Pattern variable thêm quy tắc **flow scoping**: có thể dùng biến chỉ ở chỗ trình biên dịch chắc chắn rằng đường đi tới đó đã khớp pattern.

**Nhánh đúng:**

```java
if (input instanceof String text) {
    System.out.println(text.toUpperCase()); // Hợp lệ
} else {
    // Không được dùng text: nhánh này không bảo đảm match.
}
```

**Vế phải của `&&`:**

```java
if (input instanceof String text && text.length() >= 4) {
    System.out.println(text);
}
```

Vế phải chỉ chạy khi phép thử pattern ở vế trái đã trả về `true`. Trong ví dụ này, cả `text.length()` lẫn `System.out.println(text)` đều ở vị trí có thể sử dụng `text`.

**Vế phải của `||`:**

```java
// Sai, không biên dịch:
// if (input instanceof String text || text.isBlank()) {
//     System.out.println(text);
// }
```

Vế phải `||` chạy khi vế trái `false`, tức không bảo đảm `String text` đã khớp. Không thể dùng `text` tại đó.

**Sau nhánh kết thúc sớm:**

```java
static int lengthOrMinusOne(Object input) {
    if (!(input instanceof String text)) {
        return -1;
    }
    return text.length(); // Hợp lệ: đường đi tới đây chắc chắn match.
}
```

Dấu `!` đảo điều kiện; câu lệnh `return` loại bỏ đường đi không khớp. Ở cuối phương thức, Java biết `text` đã được binding. Đây không phải kết quả của việc một biểu thức ngẫu nhiên trả về `true`; đây là quy tắc phạm vi gắn với pattern và luồng điều khiển.

## 7. `switch`: pattern chọn nhánh, expression tạo ra kết quả

Từ **Java 21**, pattern matching trong `switch` và guard `when` đã được chuẩn hóa. Xét một `switch expression` trả về `String`:

```java
return switch (input) {
    case String text when text.isBlank() -> "blank String";
    case String text -> "String length=" + text.length();
    case Integer number -> "Integer+1=" + (number + 1);
    case null -> "null";
    default -> "other";
};
```

Ba vai trò cần phân biệt:

- `input` là **selector expression**: được đánh giá để lấy một giá trị cho phép chọn nhánh.
- `case String text` và `case Integer number` chứa **pattern**: kiểm tra kiểu và binding biến ở nhánh phù hợp. `case null` là nhãn xử lý giá trị `null`, không phải type pattern.
- `when text.isBlank()` là **guard expression** kiểu `boolean`, chỉ được đánh giá sau khi pattern `String text` đã khớp và `text` có thể sử dụng. Giá trị sau `->` ở nhánh được chọn là biểu thức tạo ra **kết quả cuối cùng của `switch expression`**.

Vì vậy một `switch expression` vừa dùng **pattern matching để chọn nhánh**, vừa dùng **expression evaluation để tạo giá trị trả về**. Pattern tại `case` không tự mang giá trị trả về của toàn bộ `switch`.

### Ví dụ Java 21+ chạy được

Lưu tệp `SwitchPatternDemo.java`:

```java
public class SwitchPatternDemo {
    static String describe(Object input) {
        return switch (input) {
            case String text when text.isBlank() -> "blank String";
            case String text -> "String length=" + text.length();
            case Integer number -> "Integer+1=" + (number + 1);
            case null -> "null";
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(" "));
        System.out.println(describe(41));
        System.out.println(describe(null));
        System.out.println(describe(2.5));
    }
}
```

```bash
javac SwitchPatternDemo.java
java SwitchPatternDemo
```

Kết quả:

```text
String length=4
blank String
Integer+1=42
null
other
```

Với `"Java"`, pattern `String text` ở nhánh đầu khớp nhưng guard `text.isBlank()` sai; nhánh `case String text` kế tiếp được chọn và đánh giá biểu thức tạo chuỗi `"String length=4"`. Với `" "`, guard đúng nên nhánh đầu trả về `"blank String"`. Với `41`, pattern `Integer number` khớp, rồi biểu thức `number + 1` tạo ra `42`. `null` được xử lý bằng `case null`. Với `2.5`, `default` trả về `"other"`.

Khi dùng `switch` với pattern, cần chú ý **thứ tự và tính thống trị của các nhánh**: một pattern rộng đặt trước có thể che pattern hẹp phía sau, khiến trình biên dịch báo nhánh bị thống trị. `switch expression` cũng phải bao phủ mọi trường hợp theo quy tắc của Java. Đặc biệt, `switch` không có `case null` thường không xử lý `null` như `instanceof` trả về `false`; đừng suy ra hành vi của `switch` từ phép thử `instanceof`.

## 8. Record pattern: ví dụ rõ hơn về “khớp” so với “tính giá trị” (Java 21+)

Một **record pattern** có thể thử kiểu record và khớp tiếp các thành phần để tạo nhiều binding. Ví dụ sau giả định lớp record được khai báo trong cùng phạm vi biên dịch:

```java
record Pair(Object left, Object right) {}

Object input = new Pair("A", 42);
if (input instanceof Pair(String left, Integer right)) {
    System.out.println(left + ":" + right); // A:42
}
```

Ở đây:

- `input` được đánh giá thành một đối tượng `Pair`.
- `Pair(String left, Integer right)` là **record pattern** (không phải lời gọi constructor và không phải lời gọi hàm).
- Pattern kiểm tra đối tượng thuộc kiểu `Pair`, rồi khớp từng thành phần với type pattern `String left` và `Integer right`.
- Chỉ khi toàn bộ pattern khớp, hai biến `left` và `right` được binding để khối `if` sử dụng.
- Biểu thức `left + ":" + right` mới thực hiện nối chuỗi và tạo giá trị để in.

Viết `new Pair("A", 42)` là **biểu thức tạo đối tượng**; viết `Pair(String left, Integer right)` trong vị trí pattern là **cú pháp để khớp và phân rã dữ liệu**. Hình thức gần giống nhau nhưng có vai trò ngữ nghĩa khác nhau. Record pattern có từ Java 21; đừng biên dịch ví dụ này bằng cấu hình `--release 17`.

## 9. So sánh tổng hợp

| Tiêu chí | Expression evaluation | Pattern matching |
| --- | --- | --- |
| Câu hỏi chính | Biểu thức trả về giá trị gì? | Giá trị được thử có phù hợp với pattern không? |
| Đầu vào | Toán hạng, biến, lời gọi, giá trị trung gian... | Một giá trị cần thử và mẫu mô tả kiểu/cấu trúc |
| Kết quả | Giá trị theo kiểu của biểu thức, hoặc completion bất thường | Thành công/thất bại của phép khớp, cùng các binding khi thành công |
| Ví dụ | `a + b`, `s.length()`, `a > 0`, toàn bộ `x instanceof String s` | `String s` trong `instanceof`; `case String s`; `Pair(String x, Integer y)` |
| Biến mới | Không nhất thiết khai báo biến | Pattern có thể giới thiệu pattern variable |
| Luồng điều khiển | Có thứ tự đánh giá và short-circuit | Việc có được dùng pattern variable phụ thuộc flow scoping |
| Thất bại | Có thể ném exception hoặc trả về giá trị biểu thị thất bại tùy biểu thức | Không khớp thì không binding; exception khi đánh giá target hoặc xử lý liên quan vẫn có thể xảy ra |

Hai cột **không phải đối lập tuyệt đối**. Phép đánh giá một `instanceof expression` bao gồm việc thử một pattern; phép đánh giá một `switch expression` có thể bao gồm việc lựa chọn nhánh bằng pattern.

## 10. Những lỗi tư duy và lỗi code phổ biến

1. **Nghĩ `String text` là một biểu thức trả về `boolean`.** Kết quả `boolean` đến từ *toàn bộ* `input instanceof String text`; `String text` là pattern.
2. **Nghĩ mọi điều kiện `boolean` đều dùng pattern.** `input != null` hay `"Java".equals(input)` chỉ đánh giá điều kiện, không binding một `String text` mới.
3. **Nghĩ nhánh `else` chứng minh pattern không khớp.** Với `instanceof String text && text.length() > 3`, `else` còn xảy ra khi pattern khớp nhưng phép so độ dài sai.
4. **Dùng pattern variable ngoài flow scope.** Gán kết quả `instanceof` vào biến `boolean` không kéo theo khả năng dùng tên pattern variable ở các câu lệnh sau.
5. **Nghĩ target không được đánh giá khi pattern thất bại.** Target luôn cần được đánh giá để thử pattern, trừ khi toàn bộ biểu thức chứa phép thử đã bị bỏ qua bởi cấu trúc điều khiển bên ngoài. Nếu đánh giá target ném exception, phép thử không thể tạo ra kết quả bình thường.
6. **Đồng nhất `null` của `instanceof` và `switch`.** `null instanceof String text` luôn `false` đối với type pattern; `switch` cần xử lý `null` theo quy tắc của nó, ví dụ dùng `case null`.
7. **Nhầm record pattern với gọi constructor.** `new Pair(...)` tạo object; `Pair(...)` ở vị trí record pattern khớp đối tượng đang có và binding các thành phần.
8. **Nhầm pattern của ngôn ngữ với `java.util.regex.Pattern`.** `java.util.regex.Pattern` là lớp thư viện cho biểu thức chính quy; `String text` hoặc `Pair(...)` ở đây là cú pháp pattern matching của ngôn ngữ Java.
9. **Bỏ qua phiên bản Java.** Type pattern cho `instanceof` ổn định từ Java 16 (dùng tốt trong Java 17); pattern matching cho `switch`, `when` và record pattern được chuẩn hóa từ Java 21. Hai ví dụ chính ở trên có chỉ dẫn JDK phù hợp.

## 11. Cách đọc nhanh một đoạn code có pattern

Khi gặp pattern matching, nên tách rõ bốn câu hỏi theo đúng thứ tự:

1. **Target/selector expression là gì?** Nó được đánh giá khi nào, có tác dụng phụ hay có thể ném exception không?
2. **Pattern ở đâu và kiểm tra điều gì?** Kiểu hay thành phần record nào được thử?
3. **Nếu khớp, những pattern variable nào được binding?** Mỗi biến có kiểu tĩnh và phạm vi sử dụng ra sao?
4. **Biểu thức nào được đánh giá tiếp?** Đó có thể là điều kiện `&&`, guard `when`, biểu thức trong nhánh hoặc giá trị kết quả của `switch expression`.

Giữ rạch ròi **“expression tạo ra giá trị” → “pattern thử giá trị và binding” → “các expression tiếp theo sử dụng kết quả/binding trong vùng hợp lệ”** là cách đọc và viết cú pháp pattern chính xác, tránh lẫn cơ chế kiểm tra kiểu với việc tính toán thông thường.
