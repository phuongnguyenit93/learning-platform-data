# Pattern là gì trong Java Language Specification (JLS)?

**Phạm vi:** Java SE 21 (JDK 21), nơi *type pattern*, *record pattern* và pattern matching trong `instanceof`/`switch` đều là tính năng ổn định. Bài này giải thích `pattern` theo đặc tả ngôn ngữ Java, không phải biểu thức chính quy (`java.util.regex.Pattern`) hay mẫu thiết kế phần mềm (*design pattern*).

## 1. Định nghĩa theo JLS `14.30

Trong Java Language Specification, **pattern (mẫu khớp)** mô tả một **phép kiểm tra có thể thực hiện trên một giá trị**. Giá trị cần kiểm tra do biểu thức hoặc câu lệnh chứa pattern cung cấp. Một pattern có thể khai báo **không, một hoặc nhiều biến cục bộ**, gọi là *pattern variables* (biến của pattern).

**Pattern matching** là quá trình kiểm tra một giá trị so với pattern tại thời điểm chạy:

1. Có một giá trị đầu vào, chẳng hạn một tham chiếu có kiểu tĩnh là `Object`.
2. Java kiểm tra giá trị ấy có thỏa cấu trúc và điều kiện kiểu của pattern không.
3. Nếu **khớp**, Java khởi tạo các pattern variable được khai báo trong pattern; chương trình có thể dùng chúng tại những vị trí mà trình biên dịch chứng minh việc khớp đã thành công.
4. Nếu **không khớp**, các biến ấy không được khởi tạo và không thể dùng như thể pattern đã thành công.

Ví dụ:

```java
Object value = "Java";
if (value instanceof String text) {
    System.out.println(text.length()); // 4
}
```

Ở đây `String text` là **type pattern**; `value` là giá trị đem kiểm tra; `text` là pattern variable. Toàn bộ `value instanceof String text` mới là biểu thức có kết quả `boolean`. Bản thân `String text` không phải một biểu thức `boolean` độc lập.

So với cách viết cũ:

```java
Object value = "Java";
if (value instanceof String) {
    String text = (String) value;
    System.out.println(text.length());
}
```

Pattern kết hợp kiểm tra kiểu với việc khai báo/khởi tạo biến, giúp bỏ thao tác ép kiểu lặp lại nhưng vẫn giữ kiểm tra kiểu ở thời điểm chạy.

## 2. Các dạng pattern trong Java 21 (`14.30.1)

Theo JLS Java SE 21, `Pattern` có hai dạng cơ bản: **`TypePattern`** và **`RecordPattern`**. Ngữ pháp rút gọn để nhận diện (không thay thế toàn bộ các sản xuất ngữ pháp trong JLS):

```text
Pattern       ::= TypePattern | RecordPattern
TypePattern   ::= khai báo đúng một biến cục bộ, không có giá trị khởi tạo
RecordPattern ::= ReferenceType "(" [Pattern ("," Pattern)*] ")"
```

### 2.1. Type pattern: kiểm tra kiểu và gắn một biến

Ví dụ `String s`, `CharSequence seq` hoặc `Number n` kiểm tra đối tượng có phù hợp với kiểu được chỉ ra hay không; khi khớp, biến tương ứng được khởi tạo bằng giá trị đã kiểm tra.

```java
Object input = 42;
if (input instanceof Integer number) {
    System.out.println(number + 1); // 43
}
```

Những giới hạn cú pháp quan trọng trong **Java 21**:

- Type pattern ở cấp ngoài cùng phải dùng **kiểu tham chiếu** và phải đặt tên biến, chẳng hạn `String s`. `obj instanceof var s` và `obj instanceof int n` không hợp lệ theo ngữ pháp ổn định Java 21.
- Một type pattern khai báo đúng **một** biến, không có phép gán khởi tạo hoặc ký hiệu mảng đặt sau tên biến. Ví dụ `String s = "x"` không phải pattern hợp lệ.
- Bên trong danh sách thành phần của record pattern có thể dùng `var` để Java suy luận kiểu thành phần, hoặc khai báo kiểu cụ thể (kể cả `int` cho thành phần `int`). `var` không được dùng tùy ý như type pattern ở cấp ngoài cùng.
- Các kiểm tra kiểu generic chịu quy tắc tương thích kiểu và *type erasure*: `List<?> list` có thể dùng cho trường hợp thích hợp, nhưng `List<String> list` không phải một kiểu có thể kiểm tra đầy đủ bằng `instanceof` tại runtime.

### 2.2. Record pattern: kiểm tra record và phân rã thành phần

Record pattern kết hợp kiểm tra một giá trị có thuộc lớp `record` tương ứng hay không với việc **khớp đệ quy** từng thành phần của record (*deconstruction*).

```java
record Point(int x, int y) {}

Object value = new Point(3, 4);
if (value instanceof Point(int x, int y)) {
    System.out.println(x + y); // 7
}
```

Trong `Point(int x, int y)`:

- `Point(...)` là record pattern; giá trị phải là một `Point` thích hợp.
- `int x` và `int y` là các type pattern lồng bên trong, tương ứng hai record component.
- `x` và `y` chỉ sẵn sàng dùng khi **toàn bộ** record pattern khớp.

Pattern có thể lồng sâu:

```java
record NamedPoint(String name, Point point) {}

Object item = new NamedPoint("A", new Point(2, 5));
if (item instanceof NamedPoint(String name, Point(int x, int y))) {
    System.out.println(name + ": " + x + ", " + y); // A: 2, 5
}
```

Các quy tắc cần nhớ:

- Kiểu đứng trước `(...)` phải là **kiểu lớp record**, không phải một lớp Java bất kỳ có các getter giống record.
- Số pattern thành phần phải **bằng đúng** số thành phần khai báo của record và đúng thứ tự; `Point(int x)` là lỗi biên dịch nếu `Point` có hai thành phần.
- `record Empty() {}` có thể khớp bằng `Empty()` mà không khai báo biến nào. Record pattern không trực tiếp khai báo biến; các pattern thành phần bên trong mới khai báo biến.
- Không được khai báo trùng tên biến pattern trong cùng một record pattern, ví dụ `Point(int x, int x)`.
- `Point(var x, var y)` hợp lệ và suy luận `x`, `y` là `int`. Đây là `var` nằm trực tiếp trong record pattern.

## 3. Pattern xuất hiện ở đâu?

### 3.1. Trong toán tử `instanceof` (`15.20.2)

`instanceof` nhận một pattern làm toán hạng bên phải. Phép kiểm tra trả về `true` hoặc `false`; khi đúng, các biến pattern có thể được dùng trong phạm vi hợp lệ:

```java
static int textLength(Object obj) {
    if (obj instanceof String s) {
        return s.length();
    }
    return -1;
}
```

Từ Java 21, `instanceof` còn có thể kiểm tra record pattern, ví dụ `obj instanceof Point(int x, int y)`. Một đối tượng kiểu tĩnh là `Object` vẫn có thể được phân rã thành các thành phần được kiểm tra kiểu tại runtime.

### 3.2. Trong nhãn `case` của `switch` (`14.11)

`switch` có thể chọn nhánh bằng pattern thay vì chỉ bằng hằng số:

```java
static String kind(Object obj) {
    return switch (obj) {
        case null      -> "null";
        case String s  -> "chuỗi: " + s;
        case Integer n -> "số nguyên: " + n;
        default        -> "kiểu khác";
    };
}
```

Trong ví dụ, `String s` và `Integer n` là pattern; `null` và `default` là các dạng nhãn `case`/nhánh khác, **không phải** pattern theo `14.30`. Nhánh `case null` xử lý `null` tường minh; nếu không có nhánh xử lý `null` phù hợp, `switch` trên tham chiếu `null` thường ném `NullPointerException`, kể cả khi có `default`.

Nhãn `case` có thể bổ sung điều kiện bảo vệ **`when`** (*guard*):

```java
static String lengthGroup(Object obj) {
    return switch (obj) {
        case String s when s.length() > 5 -> "chuỗi dài";
        case String s                     -> "chuỗi ngắn";
        default                           -> "không phải chuỗi";
    };
}
```

Java chỉ đánh giá `when` sau khi pattern tương ứng đã khớp, nên `s` được khởi tạo khi điều kiện bảo vệ chạy. Nếu `when` trả về `false`, việc lựa chọn tiếp tục xét các nhánh còn lại. **`when` là guard gắn với nhãn `case`, không phải một loại pattern thứ ba.**

## 4. Cơ chế khớp và khởi tạo biến (`14.30.2)

### Với type pattern

Một tham chiếu khác `null` khớp `String s` nếu giá trị có thể chuyển kiểu sang `String` theo quy tắc kiểm tra của JLS; khi đó `s` nhận giá trị ấy. Nếu không chuyển được, phép khớp thất bại.

### Với record pattern

Để khớp `NamedPoint(String name, Point(int x, int y))`, Java về mặt ngữ nghĩa sẽ:

1. Kiểm tra giá trị đầu vào có phù hợp với kiểu record `NamedPoint`.
2. Truy xuất các record component qua **accessor methods** (ví dụ `name()`, `point()`).
3. Khớp từng giá trị thành phần với pattern tương ứng; nếu gặp record lồng nhau, tiếp tục khớp đệ quy.
4. Chỉ công nhận các pattern variable đã khởi tạo cho biểu thức/nhánh sử dụng nếu **tất cả** phép khớp thành phần đều thành công.

Khớp pattern không phải thao tác lấy trường dữ liệu theo cú pháp getter tùy ý. Nếu accessor record ném ngoại lệ khi được gọi trong quá trình deconstruction, JLS Java 21 quy định quá trình khớp kết thúc bất thường bằng `MatchException` mang nguyên nhân từ ngoại lệ ấy. Đây là trường hợp khác với kết quả **không khớp** thông thường.

### Quy tắc `null` cần đọc chính xác

- `null instanceof String` là `false`; top-level type pattern `String s` không khớp `null`.
- Record pattern như `Point(int x, int y)` không khớp khi **chính giá trị record** là `null`.
- **Ngoại lệ tinh tế:** Một *type pattern lồng trực tiếp* trong record pattern có thể là *null-matching* nếu nó là pattern **unconditional** đối với kiểu của record component. Ví dụ:

```java
record Box(String value) {}

Object box = new Box(null);
if (box instanceof Box(var content)) {
    System.out.println(content == null); // true
}
```

`Box(var content)` khớp vì tham chiếu `Box` bên ngoài không `null`; `var content` tương ứng với component `String` và có thể nhận chính giá trị `null`. Vì vậy không nên suy diễn rằng **mọi** thành phần của record pattern đều bắt buộc khác `null`.

## 5. Phạm vi biến theo luồng điều khiển (`6.3)

JLS dùng cơ chế thường gọi là **flow scoping**: phạm vi của biến pattern phụ thuộc vào nhánh mà trình biên dịch xác định pattern đã khớp.

**Đúng — `&&` chỉ kiểm tra vế phải nếu vế trái đúng:**

```java
static boolean isLongText(Object obj) {
    return obj instanceof String s && s.length() > 5;
}
```

**Đúng — thoát sớm ở nhánh không khớp:**

```java
static void printText(Object obj) {
    if (!(obj instanceof String s)) {
        return;
    }
    System.out.println(s.toUpperCase());
}
```

**Sai — `||` có thể xét vế phải khi pattern ở vế trái thất bại:**

```java
// KHÔNG BIÊN DỊCH:
// if (obj instanceof String s || s.isEmpty()) {
//     System.out.println(s);
// }
```

Không phải cứ gặp khai báo `String s` là `s` có hiệu lực trong toàn bộ phương thức. Trình biên dịch kiểm tra khả năng biến đã được khởi tạo trên từng đường đi của luồng điều khiển. Trong `switch`, biến pattern chỉ tồn tại tại vùng phù hợp của nhãn `case`/guard/nhánh có khớp.

## 6. Những tính chất JLS dùng để kiểm tra pattern (`14.30.3)

| Thuật ngữ | Ý nghĩa học tập | Ví dụ/ảnh hưởng |
| --- | --- | --- |
| **Applicable at type** (*có thể áp dụng*) | Pattern phải hợp lệ đối với kiểu tĩnh của giá trị được kiểm tra theo các quy tắc chuyển kiểu và cấu trúc record. | `Object obj` có thể kiểm tra với `String s`; `Integer` và `String` là các kiểu final không liên quan nên `Integer i; i instanceof String s` không hợp lệ. |
| **Unconditional for type** (*khớp vô điều kiện đối với kiểu*) | Với một kiểu đầu vào nhất định, pattern được xác định là sẽ khớp mọi giá trị thuộc kiểu đó theo quy tắc JLS. | `Object o` là type pattern unconditional đối với kiểu `String`; thuộc tính này còn liên quan đến null-matching trong component record. |
| **Dominates** (*che khuất*) | Pattern trước bao phủ trường hợp pattern sau cần xử lý; thứ tự `case` có thể làm nhánh sau không thể được chọn. | `case CharSequence cs` đặt trước `case String s` gây lỗi vì nhánh sau bị che khuất. |
| **Exhaustive switch** (*bao phủ hết trường hợp*) | Các nhánh phải bao phủ những trường hợp mà `switch` yêu cầu xử lý, đặc biệt `switch` expression và enhanced `switch` statement. | Có thể dùng `default` hoặc phân hoạch đầy đủ một kiểu `sealed` bằng các pattern thích hợp. |

Một ví dụ **không biên dịch** vì dominance:

```java
// switch (obj) {
//     case CharSequence cs -> System.out.println(cs);
//     case String s -> System.out.println(s); // Bị case trước che khuất
//     default -> {}
// }
```

Đặt trường hợp cụ thể (`String`) trước trường hợp tổng quát (`CharSequence`), và chỉ dùng `default` khi cần. Guard có thể giúp phân chia các điều kiện, nhưng không nên xem guard là một pattern riêng.

Với `sealed interface` hoặc `sealed class`, trình biên dịch đôi khi có thể chứng minh một `switch` expression đã bao phủ tất cả subtype được phép mà không cần `default`. Đó là tính chất của tập nhãn `case` và kiểu selector, chứ không phải mọi pattern đều tự khớp mọi giá trị.

## 7. Chương trình hoàn chỉnh dùng type pattern, record pattern và guard

Lưu nội dung dưới đây vào tệp `PatternJlsDemo.java`. Chương trình yêu cầu **JDK 21 trở lên** và không cần bật preview:

```java
public class PatternJlsDemo {
    record Point(int x, int y) {}

    record NamedPoint(String name, Point point) {}

    static String describe(Object value) {
        // Type pattern và flow scoping qua &&
        if (value instanceof String text && !text.isBlank()) {
            return "Chuỗi: " + text;
        }

        return switch (value) {
            case null -> "null";

            // Record pattern lồng nhau với guard
            case NamedPoint(String name, Point(int x, int y))
                    when x == y -> name + ": đường chéo";

            // Record pattern lồng nhau không có guard
            case NamedPoint(String name, Point(int x, int y)) ->
                    name + ": (" + x + ", " + y + ")";

            case String ignored -> "Chuỗi trống";
            default -> "Khác";
        };
    }

    public static void main(String[] args) {
        System.out.println(describe("Java"));
        System.out.println(describe(new NamedPoint("A", new Point(2, 3))));
        System.out.println(describe(new NamedPoint("B", new Point(4, 4))));
        System.out.println(describe(null));
        System.out.println(describe(42));
    }
}
```

Biên dịch và chạy tại thư mục chứa tệp:

```bash
javac --release 21 -encoding UTF-8 PatternJlsDemo.java
java PatternJlsDemo
```

Kết quả chuẩn:

```text
Chuỗi: Java
A: (2, 3)
B: đường chéo
null
Khác
```

Giải thích lần lượt:

1. `"Java"` khớp `String text` và không blank nên trả về ngay.
2. `NamedPoint("A", Point(2, 3))` khớp record, nhưng guard `x == y` sai nên đi đến record pattern kế tiếp.
3. `NamedPoint("B", Point(4, 4))` khớp record, guard đúng nên trả về nhánh đường chéo.
4. `null` được bắt bằng `case null` trước khi xét record pattern.
5. `42` không khớp các pattern `NamedPoint` hoặc `String` nên vào `default`.

Trong ví dụ này, mỗi lần dùng `String name`, `int x` hoặc `int y` là khai báo biến pattern mới thuộc nhánh tương ứng. Java kiểm tra điều kiện khớp trước khi cho phép đọc các biến đó.

## 8. Lỗi thường gặp và cách tự kiểm tra

1. **Nhầm pattern với regex hoặc design pattern.** `java.util.regex.Pattern` kiểm tra chuỗi theo biểu thức chính quy; `14.30` mô tả cấu trúc của chính ngôn ngữ Java để khớp giá trị.
2. **Gọi cả biểu thức là pattern.** Trong `obj instanceof String s`, chỉ `String s` là pattern; `instanceof` là toán tử dùng pattern.
3. **Dùng biến khi chưa chắc khớp.** Kiểm tra phạm vi theo đường đi của `if`, `&&`, `||`, `!`, `return` và nhánh `switch`.
4. **Cho rằng record pattern giải cấu trúc được mọi class.** Nó đòi hỏi kiểu record, đúng số component và các pattern con hợp lệ.
5. **Giả định `null` luôn hành xử giống nhau.** Top-level type pattern và bản thân record pattern không khớp `null`; một số type pattern ở vị trí component record có thể khớp `null` theo quy tắc *unconditional*.
6. **Viết `case` theo thứ tự quá rộng trước.** Pattern bao trùm có thể *dominate* pattern cụ thể đặt sau, gây lỗi biên dịch.
7. **Dùng sai cú pháp theo phiên bản.** Pattern matching cho `instanceof` là tính năng ổn định từ **Java 16**; record patterns và pattern matching cho `switch` ổn định từ **Java 21**. Cú pháp parenthesized pattern riêng kiểu `case (String s)` không còn là pattern của JLS 21; dấu `_` cho unnamed pattern không thuộc tập cú pháp ổn định Java 21. Những tài liệu về preview ở phiên bản khác có thể khác ví dụ ở đây.
8. **Nhầm `when` với pattern.** `when` bổ sung điều kiện sau phép khớp pattern, còn việc gắn biến được xác định bởi type/record pattern.

Khi gặp một biểu thức khớp pattern, hãy lần lượt xác định: **giá trị bị kiểm tra là gì**, **pattern thuộc loại nào**, **kiểu tĩnh có cho phép kiểm tra không**, **điều kiện khớp runtime là gì**, **biến nào được khởi tạo khi thành công**, và **biến đó còn ở phạm vi nào sau khi điều khiển đi tiếp**.

## 9. Đối chiếu đặc tả chính thức

- [JLS Java SE 21 `14.30 — Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30): định nghĩa, loại pattern, cơ chế khớp, applicability/unconditional/dominance.
- [JLS Java SE 21 `15.20.2 — Type Comparison Operator instanceof](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2): quy tắc toán tử `instanceof`.
- [JLS Java SE 21 `14.11 — switch Statements](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.11): nhãn `case`, guard, null và tính bao phủ.
- [JLS Java SE 21 `6.3 — Scope of a Declaration](https://docs.oracle.com/javase/specs/jls/se21/html/jls-6.html#jls-6.3): phạm vi biến pattern theo luồng điều khiển.
- [Oracle Java SE 21 Language Changes](https://docs.oracle.com/en/java/javase/21/language/java-language-changes-release.html): tình trạng ổn định và lịch sử các tính năng pattern matching.
