# Applicability của pattern tại compile time (Java 21)

## Mục tiêu và phạm vi

Trong nhóm **Compiler và type checking**, một câu hỏi quan trọng của Pattern Matching là: **trình biên dịch có cho phép áp dụng một pattern lên giá trị có kiểu tĩnh đã biết hay không?** Thuộc tính đó gọi là *applicability* của pattern tại compile time.

Sau bài này, bạn có thể:

- Phân biệt **applicability (hợp lệ ở compile time)** với **matching (khớp ở runtime)**.
- Dựa vào kiểu tĩnh của biểu thức và kiểu trong pattern để dự đoán code có biên dịch không.
- Kiểm tra applicability của **type pattern**, **record pattern** và các **component pattern lồng nhau**.
- Nhận diện lỗi với các kiểu không thể cast an toàn, số component, kiểu primitive, generic/erasure và tên biến lặp.
- Phân biệt các kiểm tra khác của compiler như *dominance*, *exhaustiveness* và *scope*.

**Phiên bản:** ví dụ dùng **Java 21**. Record Patterns (JEP 440) và Pattern Matching for `switch` (JEP 441) đã chính thức ở Java 21, không cần `--enable-preview`. Đặc biệt, đừng đem các quy tắc mở rộng pattern cho kiểu primitive của các bản Java mới/preview áp ngược vào Java 21.

## 1. Applicability là kiểm tra ở compile time

Ví dụ:

```java
Object obj = "hello";
if (obj instanceof String text) {
    System.out.println(text.length());
}
```

Compiler nhìn thấy **kiểu tĩnh** của biểu thức `obj` là `Object` và pattern `String text`. Nó xác định liệu một giá trị kiểu `Object` có thể được **checked cast** sang `String` hay không. Có thể, nên pattern **applicable** và câu lệnh hợp lệ.

Đến **runtime**, JVM mới kiểm tra giá trị thực tế của `obj` có phải `String` khác `null` hay không. Với giá trị `"hello"`, pattern khớp; với `Integer.valueOf(5)`, pattern không khớp. Cả hai trường hợp đều **biên dịch được** nếu kiểu tĩnh của `obj` vẫn là `Object`.

Ngược lại:

```java
String name = "hello";
if (name instanceof Integer number) {
    System.out.println(number);
}
```

Đoạn trên **không biên dịch** trong Java 21: kiểu tĩnh `String` không có checked cast conversion hợp lệ sang `Integer`. Compiler từ chối trước khi chạy, dù người viết dự định đặt điều kiện trong `if`.

**Không đánh đồng:** `pattern không applicable` ⇒ lỗi compile time; `pattern applicable nhưng giá trị không khớp` ⇒ chương trình vẫn chạy, biểu thức `instanceof` thường trả `false` hoặc `switch` xét nhánh khác.

## 2. Định nghĩa chính xác theo JLS Java 21

Theo [JLS §14.30.3](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3), pattern `p` *applicable at type T* khi phù hợp một trong các quy tắc sau.

| Loại pattern | Điều kiện áp dụng tại kiểu tĩnh `T` |
|---|---|
| **Reference type pattern** khai báo biến kiểu `U` | `T` là kiểu tham chiếu và có **checked cast conversion** từ `T` sang `U` (JLS §5.5) |
| **Primitive type pattern** khai báo biến kiểu primitive `P` | Trong Java 21, pattern này applicable tại đúng kiểu primitive `P` |
| **Record pattern** với kiểu record `R` và các component pattern | (1) `T` checked-cast-convertible sang `R`; **và** (2) **mỗi** component pattern applicable tại **kiểu khai báo của component tương ứng** trong `R` |

Định nghĩa record pattern là **đệ quy**: nếu component chứa một record pattern khác, compiler tiếp tục kiểm tra applicability của pattern con theo kiểu component ở tầng đó.

Ví dụ:

```java
record Duo(Object first, Number second) {}
Object value = new Duo("A", 7);

if (value instanceof Duo(String label, Integer score)) {
    System.out.println(label + ": " + score);
}
```

Compiler thực hiện các kiểm tra về kiểu theo hướng:

1. `T = Object` có checked cast conversion sang record `R = Duo`.
2. Component `first` khai báo là `Object`; type pattern `String label` applicable tại `Object`.
3. Component `second` khai báo là `Number`; type pattern `Integer score` applicable tại `Number`.
4. Mọi điều kiện đều hợp lệ; code biên dịch. Ở runtime, record là `Duo`, thành phần đầu là `String` và thành phần hai là `Integer` nên toàn bộ pattern khớp.

Điều kiện cast ở đây là **checked**: không được dựa vào phép chuyển kiểu generic không kiểm tra được vì erasure. Ngoài applicability, record pattern còn phải thỏa các ràng buộc cú pháp/kiểu khác như đúng số component, tên biến không trùng, và kiểu `R` thực sự là một record class.

## 3. Kiểu tĩnh quyết định code có được phép viết

Xét cùng ý định kiểm tra `String`:

| Kiểu tĩnh của biểu thức | Pattern | Compile time | Runtime |
|---|---|---|---|
| `Object` | `String s` | Hợp lệ | Khớp nếu giá trị là `String` khác null |
| `Number` | `Integer i` | Hợp lệ | Khớp nếu giá trị là `Integer` khác null |
| `String` | `Integer i` | **Lỗi** | Không chạy vì các kiểu không cast tương thích |
| `String` | `CharSequence cs` | **Hợp lệ trong Java 21** | Khớp nếu `String` khác null |
| `Duo` | `Duo(var a, var b)` | Hợp lệ | Khớp nếu `Duo` khác null và các component pattern khớp |
| `Object` | `Duo(var a, var b)` | Hợp lệ | Khớp nếu giá trị là `Duo` phù hợp; null thì không khớp |

Điểm dễ nhầm: **Java 21 cho phép type pattern mà kiểu tĩnh đã là subtype của kiểu pattern**, miễn điều kiện applicability được đáp ứng. Ví dụ sau **biên dịch** bằng `javac --release 21`:

```java
String text = "abc";
boolean a = text instanceof CharSequence cs;
boolean b = text instanceof String s;
```

Hai biến boolean đều `true` vì `text` khác null. Nếu `text == null`, các biểu thức `instanceof` trên trả `false`. Một số tài liệu về phiên bản Java cũ mô tả `instanceof` pattern “luôn đúng” là lỗi; phải kiểm tra đúng phiên bản JLS đang sử dụng. **Applicability không đồng nghĩa với bảo đảm runtime match**, nhất là khi giá trị có thể null.

Với hai **final class** không có quan hệ chuyển kiểu checked cast phù hợp như `String` và `Integer`, compiler có thể kết luận không thể khớp và từ chối. Đừng suy diễn rằng mọi cặp kiểu có tên khác nhau đều không applicable: giao diện và lớp không `final` có thể có quan hệ cast hợp lệ dù không cùng một chuỗi kế thừa tường minh.

## 4. Record pattern: compiler kiểm tra từng component

Giả sử:

```java
record Duo(Object first, Number second) {}
```

Phân tích các pattern:

| Record pattern | Compile time | Giải thích |
|---|---|---|
| `Duo(String a, Integer b)` | Hợp lệ | `Object → String` và `Number → Integer` là checked cast conversions hợp lệ |
| `Duo(String a, Long b)` | Hợp lệ | `Number → Long` hợp lệ; runtime có thể không khớp nếu `second` đang là `Integer` |
| `Duo(var a, var b)` | Hợp lệ | `a` suy ra `Object`, `b` suy ra `Number` |
| `Duo(String a, String b)` | **Lỗi** | `Number → String` không checked-cast-convertible |
| `Duo(var a)` | **Lỗi** | `Duo` có hai component, pattern list chỉ có một |
| `Duo(var a, var a)` | **Lỗi** | Khai báo cùng tên pattern variable hai lần trong một record pattern |

Lưu ý: các dòng là **pattern fragments**, phải đặt trong một ngữ cảnh như `instanceof` hoặc nhánh `case` để dùng thực tế.

**Từ `var` đến kiểu suy ra:** `Duo(var a, var b)` không có nghĩa là compiler chọn kiểu runtime của component. `a` được xác định theo kiểu khai báo `Object` và `b` theo `Number`. Muốn dùng API chỉ có ở `Integer` thì cần pattern tương ứng `Integer b` hoặc kiểm tra thêm.

### Primitive component phải tương ứng đúng kiểu trong Java 21

```java
record Point(int x, int y) {}
```

- `Point(int x, int y)`: hợp lệ, hai component khai báo `int`.
- `Point(var x, var y)`: hợp lệ, compiler suy ra hai biến kiểu `int`.
- `Point(long x, int y)`: **không hợp lệ trong Java 21**: component đầu có kiểu `int` nhưng primitive pattern `long x` không applicable tại `int`, dù phép gán thông thường từ `int` sang `long` có thể widening.

**Bẫy:** Khả năng widening trong phép gán hoặc phép toán số học **không** tự cấp quyền sử dụng mọi primitive type pattern trong Java 21. Ở phiên bản này, quy tắc applicability cho primitive pattern dùng **đúng kiểu `P`**. Đồng thời `instanceof` yêu cầu biểu thức bên trái là kiểu tham chiếu hoặc null type trong Java 21, nên không viết `5 instanceof int i`.

## 5. Nested record pattern: applicability kiểm tra đệ quy

Khai báo thêm:

```java
record Address(String city, Point point) {}
record Customer(Address address) {}
```

Với pattern:

```java
Customer(Address(String city, Point(int x, int y)))
```

compiler kiểm tra:

1. Biểu thức selector có checked cast conversion tới `Customer` hay không.
2. Component `Customer.address` có kiểu `Address`; record pattern `Address(...)` có applicable tại `Address` không.
3. Component `Address.city` khai báo `String`; `String city` applicable tại `String`.
4. Component `Address.point` khai báo `Point`; `Point(int x, int y)` applicable tại `Point`.
5. Hai component `Point.x` và `Point.y` khai báo `int`, khớp với primitive patterns `int x`, `int y`.

Nếu chỉ **một** component pattern không applicable, **toàn bộ** nested record pattern không hợp lệ tại compile time. Ví dụ thay `Point(int x, int y)` bằng `Point(long x, int y)` gây lỗi ngay ở pattern nguyên thủy bên trong.

**Applicability khác với null-matching:** Nested record pattern `Address(...)` hoặc `Point(...)` không khớp runtime `null`, dù compiler đã chấp nhận. Type pattern trực tiếp trong danh sách component (như `String city` khi component khai báo `String`, hoặc `var point` khi component khai báo `Point`) có thể bind `null` khi unconditional với kiểu component. Compiler quyết định khả năng áp dụng theo kiểu tĩnh, rồi runtime mới quyết định có khớp giá trị thực tế không.

## 6. Ví dụ Java 21 độc lập: trường hợp compiler chấp nhận

Tạo tệp **`PatternApplicabilityDemo.java`** với toàn bộ nội dung:

```java
import java.util.List;

public class PatternApplicabilityDemo {
    record Duo(Object first, Number second) {}
    record Point(int x, int y) {}
    record Box<T>(T value) {}

    public static void main(String[] args) {
        Object source = "Java";
        System.out.println("Object -> String: "
                + (source instanceof String s && s.length() == 4));

        Object value = new Duo("A", Integer.valueOf(7));
        if (value instanceof Duo(String label, Integer score)) {
            System.out.println("Duo nested: " + label + "/" + score);
        }
        System.out.println("Duo component Long: "
                + (value instanceof Duo(String label, Long score)));

        Duo direct = new Duo("B", null);
        if (direct instanceof Duo(var left, var right)) {
            System.out.println("Duo typed source: " + left + "/"
                    + (right == null));
        }

        Number number = Integer.valueOf(8);
        System.out.println("Number -> Integer: "
                + (number instanceof Integer i && i > 0));

        Box<String> box = new Box<>("ok");
        if (box instanceof Box(var data)) {
            System.out.println("generic inferred: " + data.toUpperCase());
        }

        Object unknown = List.of("x");
        System.out.println("List<?>: "
                + (unknown instanceof List<?> list && list.size() == 1));

        Object missing = null;
        System.out.println("null record: "
                + (missing instanceof Duo(var a, var b)));

        Object choice = Integer.valueOf(9);
        String route = switch (choice) {
            case null -> "null";
            case String s -> "string";
            case Integer i when i > 0 -> "integer-positive";
            default -> "other";
        };
        System.out.println("switch(Object): " + route);
    }
}
```

Chạy trên **JDK 21+**:

```bash
javac --release 21 PatternApplicabilityDemo.java
java PatternApplicabilityDemo
```

**Stdout đã kiểm chứng:**

```text
Object -> String: true
Duo nested: A/7
Duo component Long: false
Duo typed source: B/true
Number -> Integer: true
generic inferred: OK
List<?>: true
null record: false
switch(Object): integer-positive
```

Giải thích các dòng tiêu biểu:

- `Object → String`: compiler chấp nhận cast; giá trị thực tế là `String` nên điều kiện runtime đúng.
- `Duo(String, Integer)`: mỗi component pattern applicable và dữ liệu cũng khớp.
- `Duo(String, Long)`: **vẫn compile thành công** vì `Number → Long` cast hợp lệ; runtime nhận `Integer` nên toàn bộ pattern không khớp, in `false`.
- `Duo(var, var)`: kiểu tĩnh của biến đã là `Duo`, record pattern vẫn applicable; component `second == null` được bind vào biến `right`.
- `Box(var data)`: với `Box<String>`, generic record pattern suy luận kiểu component `String`; `data.toUpperCase()` biên dịch.
- `List<?>`: pattern kiểm tra được mà không giả vờ JVM xác minh được một đối số generic không reifiable.
- `null record`: `instanceof` trả `false` ở runtime; không có lỗi applicability.
- `switch(Object)`: `String` và `Integer` đều là lựa chọn applicable tại kiểu selector `Object`; nhánh thực tế khớp `Integer` và guard `i > 0`.

Các khai báo record trong ví dụ là kiểu lồng trong lớp Java, nên chỉ cần lưu đúng một tệp theo tên public class.

## 7. Ví dụ không biên dịch: hiểu từng nguyên nhân

Các đoạn sau **cố ý sai**. Mỗi đoạn độc lập; không ghép vào chương trình chạy ở mục 6. Tất cả đã được kiểm tra bằng `javac --release 21` và bị compiler từ chối. Nội dung thông báo lỗi chính xác có thể khác nhau tùy phiên bản `javac`.

### 7.1. Source type không cast được sang pattern type

```java
String value = "hi";
boolean bad = value instanceof Integer i; // COMPILE ERROR
```

`String` và `Integer` là hai kiểu lớp không có checked cast conversion cho tình huống này; compiler xác định pattern không applicable tại kiểu tĩnh `String`. Nếu thay kiểu tĩnh của biến thành `Object`, kiểm tra `Integer` trở nên hợp lệ nhưng có thể trả `false` runtime.

### 7.2. Component pattern không applicable

```java
record Duo(Object first, Number second) {}
Object source = new Duo("A", 7);
boolean bad = source instanceof Duo(String first, String second); // ERROR
```

Tầng record ngoài có thể applicable, nhưng component thứ hai khai báo `Number`, trong khi pattern yêu cầu `String`. Vì `Number` không checked-cast-convertible sang `String`, toàn bộ record pattern bị từ chối.

### 7.3. Sai số component và trùng tên biến

```java
// Với record Duo(Object first, Number second) {}:
boolean wrongCount = source instanceof Duo(var a);          // ERROR
boolean repeated = source instanceof Duo(var x, var x);     // ERROR
```

`Duo` có hai component, nên phải khai báo hai component patterns. Không được khai báo hai pattern variables cùng tên trong một record pattern. Đây là các điều kiện **well-formedness ở compile time**, nên cần phân biệt với quy tắc cast/applicability thuần túy.

### 7.4. Primitive pattern không khớp kiểu component

```java
record Point(int x, int y) {}
Object source = new Point(1, 2);
boolean bad = source instanceof Point(long x, int y); // ERROR Java 21
```

Component đầu có kiểu `int`, còn primitive type pattern là `long`. Trong Java 21, pattern này không applicable tại kiểu `int`. Sửa thành `Point(int x, int y)` hoặc `Point(var x, var y)`.

### 7.5. Generic pattern cần unchecked conversion

```java
record Box<T>(T value) {}
Box raw = new Box("hello");
boolean bad = raw instanceof Box<String>(var text); // ERROR
```

Kiểu tĩnh `Box` là **raw type**. Chuyển sang `Box<String>` ở pattern yêu cầu thông tin tham số generic không thể checked cast tương ứng; compiler không chấp nhận. Sử dụng `Box<String>` ngay ở kiểu biến nếu hệ thống biết điều đó từ trước, hoặc dùng một pattern khác mà việc cast được kiểm tra an toàn.

Tương tự:

```java
Object o = List.of("hello");
boolean bad = o instanceof List<String> xs; // ERROR
```

Từ `Object` đến `List<String>` không có checked cast conversion an toàn (type argument `String` bị erasure). Nhưng `o instanceof List<?> xs` là hợp lệ; sau đó kiểm tra **các phần tử** bằng pattern riêng nếu cần xác nhận kiểu.

**Lưu ý:** Không nên giải quyết lỗi generic bằng cách ép raw/unchecked cast rồi coi dữ liệu đã an toàn; cách đó dời rủi ro sang runtime. Hãy thiết kế kiểu API để giữ thông tin generic có thể chứng minh ở compile time.

## 8. Applicability trong switch và các kiểm tra khác

Khi viết:

```java
Object item = Integer.valueOf(9);
String route = switch (item) {
    case null -> "null";
    case String s -> "text";
    case Integer n when n > 0 -> "positive-int";
    default -> "other";
};
```

Compiler dựa vào **kiểu tĩnh `Object` của selector `item`** để xét applicability từng pattern. Cả `String s` và `Integer n` đều applicable tại `Object`. Khi chạy, chỉ nhánh `Integer` với guard đúng được chọn.

Nhưng ở `switch`, compiler còn kiểm tra những thuộc tính **khác applicability**:

- **Dominance:** nhánh `case Object any -> ...` đứng trước `case String s -> ...` sẽ bao phủ nhánh String, khiến nhánh String bị từ chối. Bản thân `String s` vẫn applicable tại `Object`.
- **Exhaustiveness:** `switch expression` phải có các nhánh bao phủ mọi khả năng mà ngôn ngữ yêu cầu. Một pattern applicable riêng lẻ không tự làm toàn bộ switch exhaustive.
- **Guard và scope:** biến `n` được bind khi `case Integer n` khớp và có thể dùng trong `when n > 0`. Gọi `n` ngoài nhánh không hợp lệ.
- **Null:** `case null` xử lý selector bằng `null`; `default` đơn thuần không tự thay thế mọi tình huống null trong pattern switch. Đây là hành vi runtime, không phải điều kiện checked cast của một pattern.
- **Pattern list:** nhiều `case` áp dụng được riêng lẻ vẫn có thể gây lỗi dominance hoặc trùng label khi đặt cạnh nhau.

**Chốt ranh giới:** một `case` phải **applicable** mới được xét đến tính khớp; sau đó toàn bộ `switch` còn chịu các kiểm tra khác về khả năng tới được nhánh và tính đầy đủ.

## 9. Quy trình tìm nguyên nhân khi javac báo lỗi pattern

1. **Xác định Java version**: biên dịch bằng `javac --release 21` để giữ đúng quy tắc Java 21; không lấy ví dụ preview mới hơn để lý giải ngược.
2. **Xác định kiểu tĩnh T** của selector/biểu thức từ khai báo, kiểu suy luận của biểu thức hoặc generic type. Không đoán bằng kiểu giá trị runtime.
3. **Xác định loại pattern**: reference type pattern, primitive type pattern hay record pattern.
4. **Kiểm tra checked cast** từ `T` sang kiểu của pattern. Nếu compiler chứng minh cast không được phép hoặc sẽ phải unchecked, sửa kiểu/pattern.
5. **Với record pattern**, kiểm tra từng component theo **kiểu khai báo trong record**, đệ quy xuống các record con. Kiểm tra đúng số component và không trùng tên biến.
6. **Với generic**, xác định phần thông tin nào có thật ở compile time và phần nào bị erasure. Cân nhắc wildcard hoặc thay đổi API để có typed record.
7. **Với switch**, nếu riêng từng pattern đã hợp lệ nhưng toàn bộ code vẫn lỗi, kiểm tra dominance, exhaustiveness, guard và phạm vi biến.
8. **Sau khi compiler chấp nhận**, mới kiểm tra các trường hợp runtime: khác kiểu thực tế, `null` ở root/nested component, guard sai và nhánh fallback.

Một mẹo hữu ích là cố định kiểu tĩnh tại chỗ:

```java
Object broad = "abc";
String narrow = "abc";

// broad instanceof Integer i  -> hợp lệ nhưng runtime false.
// narrow instanceof Integer i -> không applicable, lỗi compile time.
```

Đây là **mẫu minh họa để so sánh**, không ghép hai biểu thức vào cùng một lớp vì khai báo trùng tên biến `i` có thể dẫn đến lỗi khác. Điểm mấu chốt là thay đổi kiểu khai báo của selector có thể làm đổi **khả năng biên dịch**, dù giá trị quan sát giống hệt.

## 10. Bài tập tự kiểm tra

Dùng:

```java
record Pair(Object left, Number right) {}
Object obj = new Pair("x", Integer.valueOf(3));
Pair pair = new Pair("x", Integer.valueOf(3));
```

Hãy dự đoán compile time trước, rồi nếu compile được mới xét runtime:

| Biểu thức | Compile time | Kết quả runtime / giải thích |
|---|---|---|
| `obj instanceof Pair(String s, Integer n)` | Hợp lệ | `true` với dữ liệu đã cho |
| `obj instanceof Pair(String s, Long n)` | Hợp lệ | `false` vì second thực tế là `Integer` |
| `obj instanceof Pair(Integer s, Integer n)` | Hợp lệ | `false` vì first thực tế là `String`, dù first khai báo `Object` |
| `obj instanceof Pair(String s, String n)` | **Lỗi** | Component second khai báo `Number` không cast được sang `String` |
| `pair instanceof Pair(var a, var b)` | Hợp lệ | `true`; kiểu của a là `Object`, b là `Number` |
| `obj instanceof Pair(var a)` | **Lỗi** | Sai arity: record có hai component |
| `obj instanceof Pair(var a, var a)` | **Lỗi** | Tên biến pattern trùng trong cùng record pattern |

Câu hỏi bổ sung:

1. Tại sao compiler chấp nhận `Pair(String, Long)` dù giá trị second đang là Integer? Vì nó xét **kiểu khai báo `Number`**, mà có checked cast conversion sang `Long`; mismatch runtime là chuyện khác.
2. Vì sao `pair instanceof Pair(var a, var b)` hợp lệ dù `pair` đã có kiểu tĩnh `Pair`? Vì record pattern vẫn yêu cầu runtime deconstruction và không được xem là unconditional, đặc biệt giá trị root có thể null.
3. Nếu `String name = null` thì `name instanceof CharSequence cs` có hợp lệ không? **Hợp lệ trong Java 21**, nhưng runtime trả `false` vì root value null.
4. Vì sao `Box raw instanceof Box<String>(var v)` lỗi? Vì generic conversion cần unchecked cast, trái điều kiện checked cast của record pattern.
5. Khi một pattern applicable nhưng đặt sau `case Object any` trong `switch(Object)`, vì sao vẫn có thể lỗi? Vì **dominance** là kiểm tra compile-time độc lập.

## Ghi nhớ

**Applicability là rào kiểm tra kiểu tĩnh trước khi chương trình chạy.** Với reference type pattern, cần checked cast conversion từ kiểu biểu thức `T` sang kiểu pattern `U`. Với record pattern, cần điều kiện cast tới record **và** từng component pattern applicable theo kiểu component được khai báo, kể cả nhiều tầng lồng nhau. Với primitive pattern trong Java 21, kiểu phải tương ứng đúng.

Một pattern applicable vẫn có thể **không khớp runtime** do giá trị khác kiểu thực tế, `null` hoặc component con không khớp. Và một cấu trúc gồm các pattern applicable vẫn có thể **không compile** vì arity, generic unchecked cast, tên biến trùng, dominance hay exhaustiveness. Hãy kiểm tra **kiểu tĩnh → applicability → các ràng buộc còn lại → matching runtime** theo đúng thứ tự.

## Tài liệu chính thức

- [JLS Java SE 21 — §14.30.3 Properties of Patterns (applicability, unconditional, dominance)](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.3)
- [JLS Java SE 21 — §14.30.1 Kinds of Patterns](https://docs.oracle.com/javase/specs/jls/se21/html/jls-14.html#jls-14.30.1)
- [JLS Java SE 21 — §15.20.2 The instanceof Operator](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.20.2)
- [JLS Java SE 21 — §5.5 Casting Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.5)
- [Oracle Java 21 — Record Patterns, Generic Records, Type Inference](https://docs.oracle.com/en/java/javase/21/language/record-patterns.html)
- [JEP 440 — Record Patterns](https://openjdk.org/jeps/440)
- [JEP 441 — Pattern Matching for switch](https://openjdk.org/jeps/441)
