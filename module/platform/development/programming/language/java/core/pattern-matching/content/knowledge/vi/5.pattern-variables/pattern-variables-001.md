# Quy tắc khai báo pattern variable trong Java

## 1. Pattern variable là gì và được khai báo ở đâu?

**Pattern variable** là biến cục bộ được **khai báo bên trong một pattern**. Khi giá trị đầu vào khớp pattern đó, Java tạo và gán giá trị cho biến theo quy tắc của pattern. Nếu không khớp, biến không có giá trị hợp lệ để sử dụng. Khai báo này gắn với phép đối sánh, không phải khai báo biến cục bộ thông thường có dấu `=`.

Ví dụ quen thuộc từ Java 16:

```java
Object value = "Java";
if (value instanceof String text) {
    System.out.println(text.length());
}
```

Trong `String text`:

- `String` là **kiểu được kiểm tra** đồng thời là kiểu khai báo của biến;
- `text` là **tên pattern variable**;
- `value instanceof String text` sẽ kiểm tra `value` có khớp kiểu `String` hay không;
- nếu khớp, biến `text` được gán chính giá trị tham chiếu đã kiểm tra và được dùng ở vị trí mà trình biên dịch xác nhận mẫu đã khớp.

Điểm khác với mã truyền thống:

```java
if (value instanceof String) {
    String text = (String) value; // Kiểm tra rồi vẫn phải ép kiểu.
}
```

Pattern variable giúp giảm ép kiểu thủ công, nhưng **không tự chuyển đổi một kiểu dữ liệu sang kiểu khác** và không trở thành trường (`field`) của lớp.

### Các vị trí khai báo chính theo phiên bản

| Vị trí dùng pattern | Ví dụ khai báo | Phiên bản Java chính thức |
| --- | --- | --- |
| `instanceof` type pattern | `value instanceof String text` | Java 16+ |
| `switch` type pattern | `case String text -> ...` | Java 21+ |
| `switch` type pattern có guard | `case String text when text.isBlank() -> ...` | Java 21+ |
| Record pattern | `value instanceof Point(int x, int y)` | Java 21+ |
| Record pattern dùng suy luận kiểu | `value instanceof Point(var x, var y)` | Java 21+ |

**Chọn JDK:** Ví dụ `instanceof` trong bài có thể biên dịch bằng Java 17; ví dụ `switch` theo kiểu và record pattern dùng Java 21 trở lên. Các tính năng đã chính thức này không cần `--enable-preview`. Trong cùng một dự án, luôn kiểm tra phiên bản mà `javac` đang nhắm đến.

## 2. Cú pháp của type pattern và các thành phần bắt buộc

Với type pattern ở cấp ngoài, mẫu thường có dạng:

```text
[final] ReferenceType variableName
```

Khi đặt sau `instanceof`:

```java
if (input instanceof String text) {
    // text là String khi nhánh được thực thi.
}
```

Và trong `switch` trên Java 21:

```java
switch (input) {
    case String text -> System.out.println(text.length());
    default -> System.out.println("Other");
}
```

Hai đoạn trên là **mảnh mã minh họa**, giả định biến `input` đã được khai báo trong một phương thức. Quy tắc cụ thể:

1. **Phải có kiểu và tên biến hợp lệ.** Ví dụ `String text`, `Number number`, `java.util.List<?> items`. Tên phải là định danh Java hợp lệ, không trùng một biến cục bộ đang có hiệu lực trong phạm vi có xung đột.
2. **Top-level type pattern dùng kiểu tham chiếu.** Trong Java 17/21, `input instanceof int n` là sai: `int` là kiểu nguyên thủy và không hợp lệ cho type pattern ở vị trí này. Để kiểm tra giá trị được đóng gói, dùng `input instanceof Integer n`.
3. **Không được viết giá trị khởi tạo trong pattern.** Viết `instanceof String text`; **không** viết `instanceof String text = "abc"`. Java gán biến lúc pattern khớp.
4. **Một type pattern khai báo một tên biến.** Không viết danh sách kiểu/biến ngăn bởi dấu phẩy như một khai báo địa phương thông thường. Nếu cần lấy nhiều thành phần của một `record`, dùng record pattern có đúng số component.
5. **Không dùng `var` cho top-level type pattern** của `instanceof` hay `case` trong Java 21: `input instanceof var text` không hợp lệ. `var` chỉ có vai trò suy luận kiểu trong **component type pattern** phù hợp bên trong record pattern.
6. **Tên biến không kèm cú pháp mảng sau định danh.** Nếu cần kiểu mảng, viết kiểu tại vị trí kiểu (`String[] texts`) khi hợp lệ; không viết `String texts[]` trong type pattern.
7. **Chỉ dùng kiểu tương thích phép kiểm tra.** Trình biên dịch bác bỏ các tổ hợp không thể khớp hoặc kiểm tra `instanceof` theo mẫu đã chắc chắn đúng về kiểu tĩnh. Chẳng hạn biến có kiểu tĩnh `String` đem kiểm tra bằng `instanceof String text` sẽ bị báo lỗi vì mẫu không còn kiểm tra điều gì hữu ích.
8. **Generic phải an toàn về kiểu.** Với `Object input`, có thể dùng `input instanceof java.util.List<?> items`; còn `input instanceof java.util.List<String> items` không hợp lệ trong trường hợp này vì không thể kiểm tra đầy đủ tham số kiểu ở thời điểm chạy.

Lưu ý: các ràng buộc của **top-level type pattern** không được áp dụng máy móc cho **type pattern là thành phần của record pattern**. Component kiểu nguyên thủy và `var` có thể hợp lệ bên trong record pattern, như phần 6.

### Cần phân biệt loại biến

```java
String existing = "hello";               // Local variable bình thường.
Object candidate = existing;              // Local variable bình thường.
if (candidate instanceof String matched) {
    System.out.println(matched);          // Pattern variable.
}
```

`matched` không phải tham số phương thức, không phải field, không được “đưa ra ngoài” `if` bằng cách gọi tên trực tiếp. Việc các biến này đều có kiểu `String` không làm cách khai báo và phạm vi của chúng giống nhau.

## 3. Khai báo hợp lệ gắn với điều kiện pattern thực sự khớp

**Khai báo về mặt cú pháp** có thể xuất hiện trong điều kiện, nhưng **biến được đưa vào sử dụng** chỉ tại vị trí mà trình biên dịch xác nhận pattern đã khớp (*definitely matched*).

### Khi `instanceof` trả về `true`

```java
Object data = "hello";
if (data instanceof String text) {
    System.out.println(text.toUpperCase()); // Hợp lệ.
} else {
    System.out.println("Không khớp");       // Không dùng text ở đây.
}
// Không thể tùy ý dùng text ở đây.
```

Pattern variable chỉ được khởi tạo khi mẫu khớp. Với `null`, **type pattern trong `instanceof` không khớp**: `null instanceof String text` trả về `false`, không khởi tạo `text`.

### Khi nối điều kiện bằng `&&`

```java
if (data instanceof String text && !text.isBlank()) {
    System.out.println(text.strip());
}
```

Vế phải của `&&` chỉ chạy khi vế trái đúng, nên `text` đã được ràng buộc. Không thể đối xứng với `||` như sau:

```java
// SAI: vế phải có thể chạy khi pattern chưa khớp.
if (data instanceof String text || text.isBlank()) {
    System.out.println(data);
}
```

Đây là ví dụ **cố ý không biên dịch**, vì Java không đảm bảo `text` đã được khai báo và khởi tạo tại thời điểm gọi `isBlank()`.

### Khi phủ định rồi thoát sớm

```java
static int lengthOrZero(Object value) {
    if (!(value instanceof String text)) {
        return 0;
    }
    return text.length(); // Hợp lệ: đến đây bắt buộc đã khớp.
}
```

Đoạn trên là **một phương thức** cần đặt trong lớp. Tại điểm sau `if`, mọi đường đi còn tiếp tục đều phải qua trường hợp `value instanceof String text` thành công.

Điều cần nhớ khi khai báo: **phạm vi dựa trên phân tích luồng điều khiển**, không chỉ dựa vào dấu ngoặc nhọn. Cách phân tích chi tiết các nhánh `if`/`while`/`for` nên học tiếp ở bài về flow scoping.

## 4. Quy tắc đặt tên: không trùng với biến cục bộ đang có hiệu lực

Pattern variable có quy tắc tên giống biến cục bộ Java; bạn không thể khai báo lại một tên địa phương đang có hiệu lực ở nơi gây xung đột.

```java
Object data = "Java";
String text = "existing";
if (data instanceof String text) { // SAI: text đã được khai báo.
    System.out.println(text);
}
```

Đây là ví dụ **cố ý không biên dịch**. Cách sửa là dùng tên khác, rõ ý nghĩa:

```java
Object data = "Java";
String text = "existing";
if (data instanceof String matchedText) {
    System.out.println(matchedText);
}
```

Một số hướng dẫn đặt tên có ích:

- Đặt theo vai trò của dữ liệu: `text`, `number`, `request`, `point`. Tránh biến `a`, `b` khi có nhiều pattern.
- Với `switch` có nhiều case, đặt tên theo kiểu dữ liệu được dùng trong chính nhánh đó; đừng cố dùng tên của biến ở case này trong case khác.
- Khi dùng record pattern lồng nhau, đặt tên cho từng component theo ý nghĩa thực tế, tránh trùng tên trong phạm vi xung đột.
- Tránh gọi pattern variable giống một biến cục bộ đã tồn tại trong phương thức, kể cả khi code có nhiều nhánh và dấu ngoặc.

Không nên “sửa” xung đột bằng cách gán hoặc ép kiểu một biến đã có rồi giả định nó biến thành pattern variable. Hãy quyết định rõ ai khai báo tên đó, phạm vi nào sử dụng tên đó và pattern nào cấp giá trị.

## 5. `final`, phép gán và tính chất biến cục bộ

Từ Java 16, pattern variable **không mặc định là `final`**. Nó là một biến cục bộ và có thể được gán lại khi nằm trong phạm vi hợp lệ:

```java
Object data = "  Java  ";
if (data instanceof String text) {
    text = text.strip();          // Hợp lệ: text không mặc định final.
    System.out.println(text);     // Java
}
```

Phép gán lại `text` chỉ thay đổi giá trị tham chiếu của biến cục bộ `text`; **không thay đổi biến `data`**. Với đối tượng mutable, thay đổi trạng thái đối tượng và gán lại tham chiếu là hai việc khác nhau.

Nếu muốn bảo đảm không gán lại, Java cho phép khai báo `final` ngay trong type pattern:

```java
Object data = "Java";
if (data instanceof final String text) {
    System.out.println(text.length()); // Hợp lệ.
    // text = "Other";                 // SAI nếu bỏ chú thích: text là final.
}
```

Nếu không có phép gán lại, biến mẫu thông thường có thể là **effectively final**, có ích khi sử dụng trong lambda và những ngữ cảnh yêu cầu giá trị được giữ nguyên. Một biến bị gán lại sẽ không còn effectively final.

**Quy tắc thiết kế:** Thường nên giữ pattern variable ở giá trị ban đầu để mã dễ đọc. Khi cần chuyển đổi dữ liệu (chuẩn hóa, cắt chuỗi, tính giá trị mới), cân nhắc tạo tên biến mới như `normalizedText`. Việc được phép gán lại không có nghĩa luôn nên làm.

## 6. Khai báo trong `switch` và record pattern trên Java 21

### Pattern variable ở một `case`

```java
static String classify(Object value) {
    return switch (value) {
        case null -> "null";
        case String text when text.isBlank() -> "blank";
        case String text -> "text: " + text;
        case Integer number -> "integer: " + number;
        default -> "other";
    };
}
```

Đây là phương thức minh họa, yêu cầu **Java 21+**. `text` trong case có `when` được ràng buộc trước khi điều kiện `text.isBlank()` được đánh giá. Biến của từng pattern chỉ dùng ở nơi được cho phép trong **case/guard tương ứng**, không phải biến dùng chung xuyên qua các case. `case null` xử lý `null` và không khai báo pattern variable. Không được đặt một case tổng quát che khuất các case cụ thể ở phía sau.

Khi `when` sai, mẫu `String` có guard không được chọn; case `String` tiếp theo có thể khớp và khai báo biến dành cho nhánh đó.

### Khai báo một hoặc nhiều biến từ record pattern

Với record:

```java
record Point(int x, int y) {}
```

Trong một phương thức, với `Object data`:

```java
if (data instanceof Point(int x, int y)) {
    System.out.println(x + ", " + y);
}
```

Ở đây `int x` và `int y` là **component type patterns** nằm **bên trong** `Point(...)`. `Point(...)` là record pattern; nó kiểm tra kiểu record và đối sánh từng component theo thứ tự khai báo. Java 21 cũng cho phép suy luận kiểu component:

```java
if (data instanceof Point(var x, var y)) {
    System.out.println(x + y);
}
```

Trong ví dụ này, `x` và `y` được suy luận thành `int` vì record có hai component kiểu `int`. **Điều này không làm `input instanceof var something` trở thành hợp lệ** ở cấp ngoài.

Record pattern có thể lồng nhau khi component chứa một record khác:

```java
record Point(int x, int y) {}
record Line(Point start, Point end) {}

// Trong một phương thức, với Object data:
if (data instanceof Line(Point(int x1, int y1), Point(int x2, int y2))) {
    System.out.println(x1 + "," + y1 + " -> " + x2 + "," + y2);
}
```

Đoạn này minh họa cú pháp, cần được đặt trong lớp/phương thức phù hợp. Nếu ghép với ví dụ `Point` trước đó, **khai báo `Point` một lần**.

**Lưu ý về `null`:** Top-level type pattern trong `instanceof` không khớp `null`. Trong Java 21, một số **component type pattern** của record có thể khớp `null` khi chúng vô điều kiện đối với kiểu component, nên không nên khái quát rằng mọi biến pattern luôn khác `null`. Bản thân record pattern vẫn không khớp một giá trị record là `null`.

## 7. Ví dụ hoàn chỉnh Java 17: khai báo, kiểm tra và phạm vi

Tạo tệp `PatternVariableRules17.java` với **toàn bộ** nội dung sau:

```java
public class PatternVariableRules17 {

    static String describe(Object input) {
        if (input instanceof String text && !text.isBlank()) {
            return "String(" + text.length() + "): " + text;
        }

        if (input instanceof Integer number) {
            return "Integer: " + number;
        }

        return "Unsupported";
    }

    static int lengthOrZero(Object value) {
        if (!(value instanceof String text)) {
            return 0;
        }
        return text.length();
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(21));
        System.out.println(describe("  "));
        System.out.println(describe(null));
        System.out.println(lengthOrZero("abc"));
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac -encoding UTF-8 --release 17 PatternVariableRules17.java
java PatternVariableRules17
```

Kết quả chính xác:

```text
String(4): Java
Integer: 21
Unsupported
Unsupported
3
```

**Giải thích:** `text` chỉ tồn tại ở nơi đã kiểm tra `String`; `number` chỉ gắn với nhánh `Integer`; giá trị `null` và chuỗi toàn khoảng trắng đều rơi xuống `Unsupported`. Trong `lengthOrZero`, khi đầu vào không phải `String`, phương thức thoát trước; nếu còn chạy, `text` chắc chắn có giá trị phù hợp.

Bài kiểm tra tại chỗ: thêm `System.out.println(text);` sau chuỗi `if` của `describe` sẽ gây lỗi biên dịch vì biến mẫu không được bảo đảm trong phạm vi đó. **Đừng coi mã sửa thử này là chương trình hoàn chỉnh hợp lệ.**

## 8. Ví dụ hoàn chỉnh Java 21: khai báo trong `switch` và record pattern

Tạo tệp `PatternVariableRules21.java`:

```java
public class PatternVariableRules21 {

    record Pair(int left, int right) {}

    static String explain(Object value) {
        return switch (value) {
            case null -> "null";
            case Pair(int left, int right) ->
                    "Pair: " + left + " + " + right + " = " + (left + right);
            case String text when text.isBlank() -> "blank";
            case String text -> "Text: " + text;
            case Integer number -> "Integer: " + number;
            default -> "Other";
        };
    }

    public static void main(String[] args) {
        System.out.println(explain(new Pair(2, 3)));
        System.out.println(explain(" "));
        System.out.println(explain("Java"));
        System.out.println(explain(7));
        System.out.println(explain(null));
    }
}
```

Biên dịch và chạy bằng JDK 21 trở lên:

```bash
javac -encoding UTF-8 --release 21 PatternVariableRules21.java
java PatternVariableRules21
```

Kết quả chính xác:

```text
Pair: 2 + 3 = 5
blank
Text: Java
Integer: 7
null
```

**Giải thích:** `Pair(int left, int right)` khai báo hai biến component trong record pattern; các case `String text` và `Integer number` khai báo biến theo type pattern; `when` truy cập được `text` vì type pattern đã khớp. `case null` không có biến và phải được xét riêng. Đổi thứ tự `case String text` tổng quát lên trước `case String text when ...` có thể tạo case bị che khuất, bị từ chối khi biên dịch.

## 9. Lỗi khai báo thường gặp và cách sửa

| Trường hợp | Vì sao sai hoặc dễ hiểu nhầm | Cách xử lý |
| --- | --- | --- |
| `input instanceof int n` | Top-level type pattern Java 17/21 đòi kiểu tham chiếu | `input instanceof Integer n` |
| `input instanceof var x` | `var` không hợp lệ cho top-level type pattern | Dùng kiểu tường minh, ví dụ `String x` |
| `input instanceof String s = "x"` | Pattern không có bộ khởi tạo như khai báo cục bộ | Bỏ `= "x"`; sử dụng giá trị được ràng buộc |
| Biến cục bộ `text` đã có rồi khai báo `String text` trong cùng phạm vi xung đột | Trùng tên khai báo | Chọn tên khác, ví dụ `matchedText` |
| `input instanceof java.util.List<String> xs` | Tham số kiểu generic không kiểm tra đầy đủ tại runtime | Dùng `java.util.List<?> xs` rồi kiểm tra phần tử phù hợp |
| Dùng biến mẫu sau nhánh `else`/`||` không bảo đảm khớp | Không có chứng minh biến đã được khởi tạo | Chỉ dùng ở nhánh/vị trí definitely matched |
| Dùng `case String s` trên `--release 17` | Pattern `switch` chính thức từ Java 21 | Nâng mục tiêu lên 21 hoặc dùng `instanceof` |
| Cho rằng `text` là `final` mặc định | Từ Java 16 biến mẫu không mặc định `final` | Ghi `final String text` nếu muốn cấm gán lại |
| Đồng nhất quy tắc top-level với component record | `Point(var x, var y)` có cú pháp riêng | Phân biệt record pattern với type pattern ở cấp ngoài |
| Giả định `null` luôn tạo biến kiểu tham chiếu | Top-level `instanceof` không khớp `null`; nested component có ngoại lệ | Xử lý `null` đúng theo ngữ cảnh đối sánh |

Không nên dùng ngoại lệ Java mới hơn hoặc cú pháp preview chưa được bật để “sửa” ví dụ đang chủ đích chạy trên Java 17/21.

## 10. Bài luyện để tự xác nhận đã hiểu quy tắc khai báo

1. **Nhận diện:** Trong `if (obj instanceof String name)`, chỉ ra vị trí khai báo, kiểu của biến, điều kiện khiến biến được gán và nơi chắc chắn dùng được.
2. **Sửa cú pháp:** Chuyển `obj instanceof int i`, `obj instanceof var x` và `obj instanceof String s = "a"` thành các khai báo type pattern hợp lệ cho tình huống dữ liệu tương ứng.
3. **Đổi tên:** Trong phương thức đã có biến địa phương `String name`, hãy xử lý `Object input` bằng type pattern mà không khai báo lại `name`.
4. **Phạm vi:** Dự đoán đoạn nào biên dịch: `obj instanceof String s && s.length() > 0`; `obj instanceof String s || s.isEmpty()`; `if (!(obj instanceof String s)) return;` rồi dùng `s` phía sau.
5. **Tính bất biến của tên biến:** Cho ví dụ gán lại biến pattern, sau đó dùng `final` để trình biên dịch từ chối cùng phép gán ấy. Giải thích vì sao biến nguồn không bị gán lại.
6. **Record pattern (Java 21):** Định nghĩa `record Range(int min, int max)` và viết cả `Range(int min, int max)` lẫn `Range(var min, var max)`; chỉ ra kiểu thực tế của hai biến.
7. **Kiểm tra phiên bản:** Biên dịch chương trình 17 bằng `--release 17` và chương trình 21 bằng `--release 21`. Thử chỉ thay `--release 17` cho chương trình 21 để hiểu lỗi phiên bản ngôn ngữ.

**Tự đánh giá đạt:** Bạn biết viết type pattern hợp lệ, phân biệt tên khai báo/kiểu/giá trị được ràng buộc, biết vì sao `var` hoặc kiểu nguyên thủy không dùng trực tiếp ở cấp ngoài, biết tránh trùng tên, biết phạm vi an toàn tối thiểu, và đọc được các khai báo biến thành phần trong record pattern.

## 11. Nguồn chính thức để tra cứu

- [Java Language Specification, Java SE 21 `14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): cú pháp type pattern, record pattern, quy tắc khớp và khởi tạo pattern variable.
- [Java Language Specification, Java SE 21 `6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3): phạm vi biến pattern trong `instanceof`, toán tử điều kiện và `switch`.
- [JEP 394 — Pattern Matching for instanceof](https://openjdk.org/jeps/394): Java 16, hỗ trợ khai báo biến trong `instanceof` và bỏ quy tắc mặc định `final`.
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441): Java 21, type pattern trong `case`, guard và xử lý `null`.
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440): Java 21, khai báo các biến component và record pattern lồng nhau.

Khi soạn mã thật, hãy kiểm tra cả `java -version` và `javac -version`, sau đó dùng `--release` tương ứng với mục tiêu biên dịch của dự án.
