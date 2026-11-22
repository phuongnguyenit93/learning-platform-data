# Pattern target và kiểu tĩnh của target

> **Phạm vi:** Java Core Pattern Matching → Cú pháp pattern. Ví dụ `instanceof` dùng Java 17+; phần `switch` và record pattern dùng Java 21+ (không cần preview).

## Mục tiêu

Sau bài này, bạn có thể xác định **pattern target** là giá trị nào, tìm **kiểu tĩnh (static type)** của biểu thức cung cấp giá trị đó, phân biệt nó với **kiểu thực tế lúc chạy (runtime type)**, và dự đoán khi nào một pattern được compiler chấp nhận, khi nào match thành công và pattern variable có kiểu gì.

## 1. Pattern target là gì?

**Pattern** mô tả điều kiện để một giá trị khớp với cấu trúc/kiểu mong muốn, đồng thời có thể lấy các thành phần của giá trị đó ra. **Pattern target** là **giá trị được đưa ra so khớp với pattern**. Trong mã nguồn, ta thường chỉ vào **biểu thức cung cấp target**.

~~~java
Object value = "Java";
if (value instanceof String text) {
    System.out.println(text.length());
}
~~~

Ở đây:

- `value` (toán hạng bên trái `instanceof`) là **biểu thức target**; giá trị hiện tại của nó là đối tượng chuỗi `"Java"`.
- `String text` (bên phải `instanceof`) là **type pattern**: kiểm tra có phải `String` và, nếu khớp, gán đối tượng ấy cho biến `text`.
- **Kiểu tĩnh của target expression** `value` là `Object` vì biến được khai báo `Object value`.
- **Kiểu thực tế** của đối tượng tại thời điểm chạy là `String`.
- **Kiểu của pattern variable** `text` là `String`, suy ra từ pattern, không phải từ kiểu khai báo của `value`.

Có thể hình dung luồng:

~~~text
Biểu thức target: value
    | Kiểu tĩnh: Object ──[compiler kiểm tra pattern có áp dụng được không?]
    | Giá trị lúc chạy: "Java", đối tượng String
    v
Pattern: String text ────[runtime kiểm tra đối tượng có khớp String?]
    | true
    v
Biến text: String, được khởi tạo từ target
~~~

**Lưu ý về thuật ngữ:** “pattern target” ở đây là giá trị chịu phép match. Đừng nhầm với “target type” trong *target typing* của lambda/poly expression: đó là một khái niệm khác trong hệ thống kiểu Java.

## 2. Kiểu tĩnh và kiểu thực tế đóng vai trò khác nhau

**Kiểu tĩnh** của biểu thức được xác định ở thời điểm biên dịch dựa trên khai báo biến, kiểu trả về của phương thức, phép ép kiểu hoặc quy tắc suy luận kiểu. **Kiểu thực tế** là lớp của đối tượng mà biểu thức tham chiếu tới lúc chạy; nó có thể là lớp con/lớp triển khai của kiểu tĩnh.

~~~java
Object a = "hello";         // Biểu thức a có kiểu tĩnh Object.
CharSequence b = "hello";   // Biểu thức b có kiểu tĩnh CharSequence.
String c = "hello";         // Biểu thức c có kiểu tĩnh String.
~~~

Ba biến đều đang trỏ đến đối tượng `String`, nhưng compiler **không coi `a`, `b` và `c` là những biểu thức có cùng kiểu tĩnh**. Vì thế tập phép toán có thể gọi trực tiếp cũng khác nhau: `a.length()` không biên dịch, `b.length()` và `c.length()` biên dịch; trong khi `a instanceof String s` và `b instanceof String s` là các phép kiểm tra kiểu hợp lệ ở Java 17.

| Biểu thức target | Kiểu tĩnh | Giá trị lúc chạy | Pattern thử khớp | Kết quả |
| --- | --- | --- | --- | --- |
| `Object x = "abc"; x` | `Object` | `String` | `String s` | Match thành công |
| `CharSequence x = "abc"; x` | `CharSequence` | `String` | `String s` | Match thành công |
| `Number n = Integer.valueOf(7); n` | `Number` | `Integer` | `Integer i` | Match thành công |
| `Number n = Double.valueOf(7.5); n` | `Number` | `Double` | `Integer i` | Không match |
| `Object x = null; x` | `Object` | `null` | `String s` | Không match với `instanceof` |
| `Integer x = 7; x` | `Integer` | `Integer` | `String s` | Lỗi biên dịch: kiểu không tương thích |

Bảng cho thấy **hai câu hỏi độc lập**:

1. **Compile time:** Với kiểu tĩnh đã biết, phép kiểm tra pattern có hợp lệ về kiểu không?
2. **Runtime:** Nếu phép kiểm tra hợp lệ, giá trị target hiện tại có thực sự khớp pattern không?

Không thể bỏ qua câu hỏi (1) chỉ vì ta “biết chắc” đối tượng lúc chạy thuộc kiểu nào.

## 3. Compiler kiểm tra tính áp dụng của pattern ra sao?

Với **type pattern** mang kiểu tham chiếu `U` (chẳng hạn `String s`), Java kiểm tra xem kiểu tĩnh tham chiếu `T` của target có thể **checked cast** sang `U` theo quy tắc ngôn ngữ hay không. Nếu không, lỗi xuất hiện ngay tại lúc biên dịch. Đây là ý nghĩa cốt lõi của tính **applicable at type T** trong JLS.

### 3.1. Có khả năng là kiểu con: hợp lệ, match tùy đối tượng

~~~java
Number number = Integer.valueOf(42);
if (number instanceof Integer i) {
    System.out.println(i + 1); // 43
}
~~~

`Number` là kiểu tĩnh, `Integer` là kiểu cần thử. Một giá trị `Number` có thể thực sự là `Integer`, nên phép thử hợp lệ. Khi match thành công, `i` có kiểu `Integer` và có thể dùng trong khối `if`.

### 3.2. Kiểu không thể chuyển đổi theo quy tắc: lỗi biên dịch

Đoạn sau **cố ý không biên dịch**:

~~~java
Integer number = 42;
if (number instanceof String text) {  // ERROR: Integer không thể là String
    System.out.println(text);
}
~~~

Cả `Integer` và `String` là các lớp không có quan hệ cast phù hợp ở đây. Compiler không cần đợi đến runtime để phát hiện phép thử vô nghĩa. Việc đổi giá trị số không thể “sửa” lỗi này; phải xem lại thiết kế kiểu hoặc chọn pattern phù hợp.

Nếu target là `Object`, compiler cho phép kiểm tra `String` vì một `Object` có thể tham chiếu đến `String`:

~~~java
Object value = Integer.valueOf(42);
System.out.println(value instanceof String); // false, nhưng hợp lệ
~~~

### 3.3. Kiểu đã biết quá cụ thể và vấn đề phiên bản

Trong **Java 17**, đoạn sau cũng là lỗi biên dịch vì phép thử type pattern không cần thiết: kiểu tĩnh của `text` đã là subtype của kiểu pattern `String`.

~~~java
String text = "hello";
if (text instanceof String s) { // ERROR với Java 17
    System.out.println(s);
}
~~~

Ở đây hãy dùng `text` trực tiếp. **Quy định về pattern vô điều kiện đã thay đổi ở các phiên bản Java sau**, vì vậy không áp câu kết luận “mọi JDK đều từ chối” cho mã hiện đại. Khi học/biên dịch bài này trên Java 17, phân biệt rõ trường hợp này với việc `Object x` cần kiểm tra `String` lúc chạy.

### 3.4. Biểu thức target không nhất thiết là một biến

~~~java
static Object load() {
    return "ready";
}

if (load() instanceof String state) {
    System.out.println(state.toUpperCase());
}
~~~

Biểu thức target là lời gọi `load()`; **kiểu tĩnh** của nó là **kiểu trả về khai báo** `Object`, không phải `String` chỉ vì thân phương thức trả về chuỗi. Biểu thức được đánh giá, sau đó giá trị trả về được match. Với dữ liệu đầu vào động, quy tắc này đặc biệt quan trọng.

`var` cũng không thay đổi nguyên tắc:

~~~java
var first = "Java";          // first được suy luận là String.
var second = (Object) "Java"; // second được suy luận là Object.
~~~

Kiểu tĩnh của `var` được suy luận **khi biên dịch** từ initializer, không liên tục đổi theo đối tượng gán sau này.

## 4. Ví dụ Java 17: cùng một kiểu tĩnh, nhiều kết quả runtime

Lưu mã sau vào tệp **`PatternTargetDemo.java`**:

~~~java
public class PatternTargetDemo {
    static void describe(Object target) {
        if (target instanceof String text) {
            System.out.println("String: " + text + ", length=" + text.length());
        } else if (target instanceof Integer number) {
            System.out.println("Integer: " + (number * 2));
        } else if (target == null) {
            System.out.println("null");
        } else {
            System.out.println("Other: " + target.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        describe("Java");
        describe(Integer.valueOf(21));
        describe(Double.valueOf(2.5));
        describe(null);
    }
}
~~~

Biên dịch/chạy với JDK 17 trở lên:

~~~bash
javac --release 17 PatternTargetDemo.java
java PatternTargetDemo
~~~

**Stdout chính xác:**

~~~text
String: Java, length=4
Integer: 42
Other: Double
null
~~~

Mỗi lần gọi, biểu thức target bên trong `describe` vẫn có kiểu tĩnh **`Object`** vì tham số được khai báo như vậy. Tuy nhiên, giá trị runtime lần lượt là `String`, `Integer`, `Double` và `null`. Nhánh được chọn dựa trên giá trị runtime, sau khi compiler đã xác nhận mỗi phép thử hợp lệ với kiểu `Object`.

**Không phải cast thủ công:** Một khi `target instanceof String text` thành công, `text` đã mang kiểu `String`. Không cần viết thêm `(String) target`.

## 5. Kiểu của pattern variable và phạm vi sử dụng

Pattern variable có kiểu được khai báo trong pattern và chỉ chắc chắn khả dụng trên các nhánh mà compiler chứng minh pattern đã match (còn gọi là **flow scoping**).

~~~java
static int nonBlankLength(Object target) {
    if (target instanceof String text && !text.isBlank()) {
        return text.length();
    }
    return 0;
}
~~~

Trong toán tử `&&`, toán hạng phải chỉ được chạy khi `target instanceof String text` là `true`; do đó `text` được khởi tạo trước khi gọi `text.isBlank()`. Ở ngoài nhánh đảm bảo match, không thể tùy tiện truy cập `text`. Ví dụ sau **cố ý không biên dịch**:

~~~java
if (target instanceof String text) {
    System.out.println(text.length());
}
System.out.println(text); // ERROR: không ở trong phạm vi được bảo đảm match
~~~

Đừng nhầm kiểu của **target** (chẳng hạn `Object`) với kiểu của **pattern variable** (`String`). Pattern variable không làm biến target đổi kiểu khai báo, nó chỉ cho bạn một tên mới với kiểu đã được kiểm tra.

## 6. Kiểu tĩnh và generics: đừng giả định tham số kiểu lúc runtime

Do **type erasure**, không thể tùy tiện kiểm tra đối tượng `Object` bằng type pattern có tham số kiểu cụ thể không reifiable. Ví dụ **cố ý lỗi biên dịch**:

~~~java
Object target = java.util.List.of("a", "b");
if (target instanceof java.util.List<String> strings) { // ERROR
    System.out.println(strings.get(0));
}
~~~

Cách kiểm tra hợp lệ khi chỉ cần biết target là một danh sách:

~~~java
Object target = java.util.List.of("a", "b");
if (target instanceof java.util.List<?> items) {
    System.out.println(items.size()); // 2
}
~~~

`List<?>` không cam kết phần tử là `String`. Khi cần xử lý phần tử, lấy từng giá trị với kiểu tĩnh an toàn (`Object`) rồi kiểm tra thêm, ví dụ `item instanceof String s`. Một số trường hợp generic có thể được compiler chứng minh an toàn từ **kiểu tĩnh cụ thể của target**, vì vậy hãy xét điều kiện checked cast thực tế thay vì ghi nhớ máy móc rằng “mọi pattern generic đều bị cấm”.

## 7. Target trong `switch` và record pattern (Java 21+)

Trong pattern `switch`, **biểu thức selector** của `switch` cung cấp target. Compiler dùng kiểu tĩnh của selector để kiểm tra các `case` pattern; lúc chạy, giá trị selector quyết định pattern nào match. Với **record pattern**, một target còn có thể được phân rã thành các **target con** tương ứng các thành phần record. Kiểu khai báo của mỗi record component quyết định tính áp dụng của pattern lồng nhau.

Lưu mã sau vào **`PatternTargetSwitchDemo.java`** và chạy bằng **JDK 21+**:

~~~java
public class PatternTargetSwitchDemo {
    record Point(int x, int y) {}

    static String describe(Object target) {
        return switch (target) {
            case null -> "null";
            case String s when s.isEmpty() -> "empty String";
            case String s -> "String length=" + s.length();
            case Point(int x, int y) -> "Point=" + x + "," + y;
            default -> "other";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe("abc"));
        System.out.println(describe(""));
        System.out.println(describe(new Point(2, 5)));
        System.out.println(describe(Integer.valueOf(9)));
        System.out.println(describe(null));
    }
}
~~~

~~~bash
javac --release 21 PatternTargetSwitchDemo.java
java PatternTargetSwitchDemo
~~~

**Stdout chính xác:**

~~~text
String length=3
empty String
Point=2,5
other
null
~~~

Phân tích:

- Selector `target` có **kiểu tĩnh `Object`** nên các `case String s` và `case Point(int x, int y)` đều có thể áp dụng.
- Khi runtime là `Point`, record pattern kiểm tra target là `Point` rồi đọc hai component; **kiểu tĩnh của từng component là `int`**, nên `x` và `y` là các pattern variable kiểu `int`.
- `case String s when s.isEmpty()` là pattern có guard: trước hết phải match `String`, sau đó điều kiện `isEmpty()` phải đúng. `case String s` kế tiếp xử lý các chuỗi còn lại.
- `null` không khớp các type pattern thông thường. `case null` được khai báo tường minh; nếu thiếu xử lý `null`, truyền `null` vào một pattern `switch` thông thường có thể ném `NullPointerException` ngay cả khi có `default`.
- `switch` có quy tắc **dominance**. Nếu đặt `case CharSequence cs` trước `case String s` trên selector `Object`, nhánh `String` sau đó bị che phủ và compiler báo lỗi vì không thể được chọn.

Ví dụ cấu trúc lồng nhau chỉ minh họa quy tắc target con (Java 21+; đặt trong lớp/phương thức phù hợp):

~~~java
record Envelope(Object payload) {}
Object target = new Envelope("ok");
if (target instanceof Envelope(String contents)) {
    System.out.println(contents.toUpperCase()); // OK
}
~~~

Ở pattern ngoài, target có kiểu tĩnh `Object`; sau khi khớp `Envelope`, giá trị `payload` là target cho pattern trong `String contents`. Vì record khai báo `payload` là `Object`, compiler cho phép thử `String`. Nếu record khai báo một component có kiểu không tương thích với pattern tương ứng thì mã bị từ chối ngay lúc biên dịch.

## 8. Cách tự phân tích một biểu thức pattern

Khi gặp một đoạn pattern matching, đi theo thứ tự sau:

1. **Khoanh biểu thức target:** bên trái `instanceof` hoặc bên trong ngoặc `switch (...)`. Với record pattern, xác định thêm từng component được tách ra.
2. **Xác định kiểu tĩnh:** xem khai báo biến, chữ ký phương thức, kiểu được suy luận của `var`, hoặc kiểu component record. Đừng dùng `getClass()` để thay thế bước này.
3. **Đọc kiểu của pattern:** ví dụ `String s`, `Integer n` hay `Point(int x, int y)`. Xét checked cast/tính áp dụng, các giới hạn generic, và với `switch` xét dominance cùng tính đầy đủ của các nhánh.
4. **Xét giá trị lúc chạy:** `null` hay đối tượng cụ thể? Một pattern hợp lệ về cú pháp vẫn có thể không match.
5. **Xác định biến được tạo và phạm vi:** biến pattern chỉ sử dụng ở nơi phép match đã được bảo đảm; với guard/`&&` phải xét đường đi thực thi.

### Sai lầm thường gặp

- **“Target runtime là String thì compiler luôn chấp nhận String pattern.”** Sai: trước tiên phải xét kiểu tĩnh và quy tắc áp dụng; ví dụ `Integer n instanceof String s` bị từ chối.
- **“Pattern variable có cùng kiểu với target expression.”** Sai: `Object obj instanceof String s` cho `s` kiểu `String`.
- **“Một phép match hợp lệ luôn trả true.”** Sai: `Number n` có thể trỏ đến `Double` nên `n instanceof Integer i` trả `false`.
- **“Có default là switch đã bắt null.”** Không đúng với `switch` pattern thông thường của Java 21; hãy xử lý `null` theo yêu cầu nghiệp vụ.
- **“List<String> có thể xác minh mọi lúc bằng instanceof.”** Không: type erasure và điều kiện reifiability/checked cast giới hạn những phép thử có thể viết.
- **“Có thể dùng pattern variable ở bất kỳ chỗ nào sau if.”** Sai: phạm vi phụ thuộc nhánh đã chứng minh match.

## 9. Tự kiểm tra

**Câu 1.** Với `Object value = "42";`, trong `if (value instanceof String s)`, hãy chỉ ra kiểu tĩnh target, kiểu runtime và kiểu `s`.

**Câu 2.** Với `Number n = Double.valueOf(3.5);`, `n instanceof Integer i` là lỗi biên dịch hay hợp lệ nhưng trả `false`? Nếu đổi `n` sang `Integer.valueOf(3)` thì sao?

**Câu 3.** Giải thích vì sao `Integer x = 1; x instanceof String s` là lỗi biên dịch, còn `Object x = 1; x instanceof String s` biên dịch được nhưng trả `false`.

**Câu 4 (Java 21).** Trong `switch (Object target)`, tại sao `case CharSequence cs` đặt trước `case String s` lại khiến nhánh thứ hai sai? Khi `target == null` thì `default` có tự xử lý hay không?

**Đáp án:** (1) `Object` / `String` / `String`. (2) Hợp lệ, `false` với `Double` và `true` với `Integer`. (3) Kiểu tĩnh `Integer` không có chuyển đổi checked cast phù hợp sang `String`, còn `Object` có thể chứa một `String` nên compiler cho phép thử runtime. (4) `CharSequence` bao phủ mọi `String` khiến nhánh sau bị dominance; `null` cần xử lý riêng (chẳng hạn `case null`).

## Tài liệu đối chiếu

- [Java Language Specification 21, `14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): type pattern, record pattern, tính áp dụng ở kiểu tĩnh, runtime matching, dominance.
- [Java Language Specification 21, `15.20.2 — The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2): phép thử pattern và kiểm tra kiểu target.
- [Oracle Java 21 — Pattern Matching for switch](https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html): selector type, guard, null, dominance.
- [Java Language Specification 17, `15.20.2](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html#jls-15.20.2): quy tắc `instanceof` của Java 17 và tình huống pattern type quá rộng so với kiểu tĩnh.
