# Type pattern có áp dụng cho kiểu primitive không? — Java 21

**Trả lời theo Java 21:** **Không thể dùng type pattern trực tiếp để kiểm tra một giá trị primitive bằng `instanceof` hoặc dùng primitive type pattern làm nhãn `case` ở mức ngoài cùng của `switch`.** Ví dụ `int n = 7; n instanceof int x` và `case int x -> ...` không hợp lệ trong Java 21. Type pattern thông dụng như `obj instanceof Integer number` hoạt động trên **đối tượng** của kiểu tham chiếu `Integer`, không phải trên primitive `int`.

Có một điểm rất dễ bỏ sót: **record pattern của Java 21 có thể chứa type pattern cho component primitive**, chẳng hạn `Point(int x, int y)` với `record Point(int x, int y)`. Đây là việc *tách các component primitive từ một đối tượng record* đã khớp, không phải kiểm tra trực tiếp một primitive bằng `instanceof`. Phân biệt ba tình huống này sẽ giúp tránh những kết luận như “pattern matching không bao giờ dùng được với `int`”.

## 1. Primitive và reference type khác nhau ở đâu?

Java có tám kiểu primitive: `boolean`, `byte`, `short`, `char`, `int`, `long`, `float`, `double`. Giá trị primitive mang dữ liệu trực tiếp theo kiểu ngôn ngữ; nó **không phải một instance của class** và không thể nhận giá trị `null`.

Các wrapper tương ứng là `Boolean`, `Byte`, `Short`, `Character`, `Integer`, `Long`, `Float`, `Double`. Chúng là **reference type**, nên có thể được lưu trong biến `Object`, `Number` (với các wrapper số) hoặc các interface mà wrapper triển khai.

| Primitive | Wrapper | Type pattern trên biến `Object` trong Java 21 |
| --- | --- | --- |
| `boolean` | `Boolean` | `obj instanceof Boolean b` |
| `byte` | `Byte` | `obj instanceof Byte b` |
| `short` | `Short` | `obj instanceof Short s` |
| `char` | `Character` | `obj instanceof Character c` |
| `int` | `Integer` | `obj instanceof Integer i` |
| `long` | `Long` | `obj instanceof Long l` |
| `float` | `Float` | `obj instanceof Float f` |
| `double` | `Double` | `obj instanceof Double d` |

Các ví dụ cột cuối giả định `obj` là biểu thức kiểu `Object`. **Type pattern ở đây kiểm tra wrapper**, không biến primitive thành một kiểu đối tượng của riêng nó.

## 2. Vì sao `instanceof` không kiểm tra trực tiếp primitive?

Với Java 21, toán tử `instanceof` dùng kiểm tra kiểu runtime của một giá trị tham chiếu. Type pattern trực tiếp thông thường khai báo biến thuộc kiểu tham chiếu:

```java
static void inspect(Object value) {
    if (value instanceof Integer number) {
        System.out.println(number + 1);
    }
}
```

`number` ở đây có **kiểu `Integer`**, và chỉ có hiệu lực tại nơi phép khớp `instanceof` được chứng minh là thành công.

Các ví dụ dưới đây **không biên dịch với JDK 21**:

```java
int n = 7;

// Không hợp lệ: toán hạng trái là primitive và type pattern ở đây là primitive.
// if (n instanceof int x) { System.out.println(x); }

// Không hợp lệ: primitive bên trái không dùng instanceof với wrapper.
// if (n instanceof Integer x) { System.out.println(x); }

Object value = Integer.valueOf(7);

// Không hợp lệ trong Java 21: top-level primitive type pattern.
// if (value instanceof int x) { System.out.println(x); }
```

Đây là các dòng minh họa lỗi, không phải một tệp Java chạy độc lập. Cách hợp lệ là giữ primitive để tính toán trực tiếp, hoặc dùng wrapper khi cần kiểm tra kiểu động của một tham chiếu.

**Tại sao không cần type pattern cho `int n` trong nhiều trường hợp?** Khi biến đã được khai báo `int n`, trình biên dịch biết chính xác kiểu `int`. Không có một đối tượng với subtype động để kiểm tra. Nếu cần xét **giá trị**, hãy dùng điều kiện như `n > 0`, `n == 0`, hoặc một `switch` theo hằng số.

## 3. Autoboxing làm ví dụ hoạt động, nhưng không thay đổi giới hạn

**Autoboxing** chuyển một giá trị primitive thành đối tượng wrapper tại những ngữ cảnh được Java cho phép, chẳng hạn gán `int` vào `Object`:

```java
int original = 42;
Object boxed = original; // autoboxing: int -> Integer

if (boxed instanceof Integer number) {
    System.out.println(number + 1);
}
```

Kết quả in ra `43`. Diễn biến chính xác:

1. `original` là primitive `int`.
2. Khi gán vào `Object`, Java boxing giá trị thành một đối tượng `Integer`.
3. `instanceof Integer number` kiểm tra đối tượng `Integer` này và tạo pattern variable `number`.
4. Biểu thức `number + 1` dùng **unboxing** để lấy `int` từ wrapper khi tính toán.

Điều đó **không có nghĩa** `instanceof` đã chấp nhận primitive. Phép boxing xảy ra ở ngữ cảnh gán, **trước** khi kiểm tra pattern; toán hạng của `instanceof` là tham chiếu `boxed`.

Tương tự, đoạn sau hợp lệ:

```java
Number number = Integer.valueOf(42);

if (number instanceof Integer integer) {
    System.out.println(integer.intValue());
}
```

`Number` là kiểu tham chiếu rộng, `Integer` là subtype của `Number`; type pattern giúp kiểm tra subtype runtime rồi làm việc với wrapper cụ thể.

**Lưu ý về biến đã có kiểu `Integer`:** nếu dùng `Integer integer = 42;` rồi thử `integer instanceof Integer i`, type pattern là phép kiểm tra không cần thiết vì kiểu biểu thức đã là subtype của kiểu pattern; trong Java 21, trình biên dịch có thể báo lỗi đối với type pattern luôn đúng theo kiểu tĩnh. Với nhu cầu kiểm tra khác `null`, viết `integer != null` là rõ ràng hơn.

## 4. Nhìn giá trị số không suy ra wrapper tương ứng

Autoboxing bảo toàn kiểu primitive ban đầu. Nó không tự biến mọi số thành `Integer` chỉ vì giá trị hiển thị giống nhau:

```java
Object first = 7;   // Integer
Object second = 7L; // Long
Object third = 7.0; // Double

System.out.println(first instanceof Integer);  // true
System.out.println(second instanceof Integer); // false
System.out.println(third instanceof Double);   // true
```

`7`, `7L` và `7.0` đều biểu diễn giá trị số “bảy” theo cách con người thường nói, nhưng chúng có **kiểu khác nhau** và sau boxing là các **class khác nhau**.

Nếu muốn xử lý nhiều wrapper số theo cùng một nhánh, có thể dùng:

```java
static String formatNumber(Object value) {
    if (value instanceof Number number) {
        return "number=" + number;
    }
    return "not a number";
}
```

`Number` bao gồm các wrapper số như `Integer`, `Long`, `Double` và cả một số class số khác. Nó **không bao gồm `Boolean` hoặc `Character`**. Việc gọi `number.intValue()` hoặc `number.doubleValue()` có thể **chuyển đổi hoặc làm mất độ chính xác**; kiểm tra `Number` không chứng minh phép chuyển đổi số mong muốn là an toàn cho mọi nghiệp vụ.

## 5. `switch` với primitive trong Java 21: nhãn hằng, không phải primitive type pattern

`switch` cổ điển và `switch` expression của Java 21 hỗ trợ một số kiểu primitive làm selector, ví dụ `int`, `byte`, `short`, `char`; khi selector là primitive, có thể dùng các **case constant** thích hợp:

```java
static String classify(int value) {
    return switch (value) {
        case -1 -> "negative one";
        case 0 -> "zero";
        case 1 -> "one";
        default -> "another integer";
    };
}
```

Đây là nhánh theo **giá trị hằng số**, không phải pattern có biến mới. Trong Java 21, đừng viết:

```java
// KHÔNG BIÊN DỊCH như một nhánh switch(int) trong Java 21:
// case int n -> "number: " + n;
```

Đồng thời, `switch` Java 21 **chưa nhận trực tiếp `long`, `float`, `double`, `boolean` làm selector primitive**. Muốn phân loại những kiểu đó, dùng `if/else` hoặc mô hình dữ liệu phù hợp.

Một `switch` dùng **selector tham chiếu** có thể khớp wrapper:

```java
static String describe(Object value) {
    return switch (value) {
        case null -> "missing";
        case Integer i when i > 0 -> "positive int wrapper: " + i;
        case Integer i -> "int wrapper: " + i;
        case Long l -> "long wrapper: " + l;
        default -> "other";
    };
}
```

Ở đây `case Integer i` và `case Long l` là **type pattern của reference type**. `when` kiểm tra giá trị sau khi pattern đã khớp. Nhánh `case null` xử lý riêng một selector rỗng; `default` không tự động thay cho nhánh `null` trong pattern switch.

Đoạn này là method minh họa, cần đặt trong một class để biên dịch.

## 6. Ngoại lệ quan trọng: primitive component trong record pattern Java 21

Khẳng định “Java 21 không hỗ trợ primitive ở bất kỳ type pattern nào” là **sai**. Java 21 đã chuẩn hóa **record patterns** (JEP 440). Với record có component primitive, người lập trình có thể dùng type pattern primitive **bên trong record pattern** để trích xuất dữ liệu:

```java
record Point(int x, int y) {}

static String readPoint(Object source) {
    if (source instanceof Point(int x, int y)) {
        return "x=" + x + ", y=" + y;
    }
    return "not a point";
}
```

Cách đọc chính xác:

- `source` có kiểu `Object` và `Point` là một **reference type** (record class).
- `source instanceof Point(...)` kiểm tra đối tượng có khớp record `Point` hay không.
- Các component `x` và `y` của `Point` có kiểu `int`, nên `int x` và `int y` là các **component type pattern** hợp lệ trong record pattern này.
- `x`, `y` là pattern variable mang giá trị primitive đã được trích xuất. Không có `instanceof` chạy trực tiếp trên một biến `int` đơn lẻ.

Cú pháp ngắn hơn dùng `var` cũng hợp lệ; compiler suy ra `x` và `y` là `int`:

```java
if (source instanceof Point(var x, var y)) {
    System.out.println(x + y);
}
```

Đoạn trên minh họa bên trong method có tham số `Object source` và khai báo `Point` như phía trên.

### Không tùy ý chuyển primitive khi khớp record component

Nếu record khai báo `int x`, trong Java 21 nên dùng component pattern tương ứng `int x` hoặc `var x`. Không được mặc định rằng một pattern `long x`, `double x` hoặc việc kiểm tra số khác sẽ tự thực hiện chuyển đổi primitive ngầm định giống phép gán thông thường.

Ví dụ, thay `Point(int x, int y)` bằng `Point(long x, long y)` để “khớp mọi `int` rồi tự nâng kiểu” **không phải cú pháp component pattern được Java 21 hỗ trợ theo cách đó**. Hãy dùng `int`/`var` để tách component rồi chuyển kiểu trong biểu thức Java bình thường nếu cần:

```java
if (source instanceof Point(int x, int y)) {
    long sum = (long) x + y;
    System.out.println(sum);
}
```

Ép `x` sang `long` trước phép cộng cũng tránh tràn số trung gian trong trường hợp tổng hai `int` vượt phạm vi `int`.

## 7. Phân biệt ba cú pháp dễ nhầm

| Mã Java 21 | Hợp lệ? | Điều thực sự được kiểm tra |
| --- | --- | --- |
| `Object obj = 7; obj instanceof Integer i` | Có | Đối tượng `Integer` sau boxing |
| `int n = 7; n instanceof Integer i` | Không | Primitive không dùng trực tiếp làm toán hạng của `instanceof` |
| `Object obj = 7; obj instanceof int i` | Không | Primitive type pattern ở top-level `instanceof` |
| `switch (n) { case 7 -> ... }` | Có | So sánh một giá trị primitive với hằng số |
| `switch (n) { case int i -> ... }` | Không | Primitive type pattern ở nhãn `case` |
| `switch (obj) { case Integer i -> ... }` | Có nếu đủ các nhánh | Pattern của wrapper `Integer` |
| `obj instanceof Point(int x, int y)` | Có khi `Point` là record có `int x, int y` | Khớp một record, rồi tách component primitive |
| `obj instanceof Point(var x, var y)` | Có với record thích hợp | Khớp record; compiler suy ra kiểu component |

Các dạng `switch` trong bảng là **đoạn cú pháp minh họa**, dấu `...` không phải mã chạy. Với `switch` expression, cần nhánh bao phủ mọi giá trị có thể có và một biểu thức kết quả hợp lệ trong từng nhánh. Pattern variable còn tuân theo *flow scoping*: chỉ dùng ở nơi compiler chắc chắn pattern đã khớp.

## 8. `null`, unboxing và an toàn kiểu

Primitive không có giá trị `null`, còn wrapper có thể `null`. Điều này dẫn đến hai quy tắc quan trọng.

**Pattern `instanceof Integer i` không khớp `null`:**

```java
Object value = null;
System.out.println(value instanceof Integer); // false
```

**Unboxing một wrapper `null` gây `NullPointerException`:**

```java
Integer maybeNull = null;
// int n = maybeNull; // biên dịch được, nhưng sẽ ném NullPointerException khi chạy
```

Đừng hiểu nhầm kết quả khớp `Integer` là tất cả wrapper đều có thể unbox an toàn ở mọi nơi. Chỉ khi chính phép khớp thành công tại đường đi đang xét thì pattern variable đó mới bảo đảm là đối tượng không `null`.

Một mẫu an toàn:

```java
static int incrementOrZero(Object value) {
    if (value instanceof Integer i) {
        return i + 1; // i là Integer khác null tại đây
    }
    return 0;
}
```

Phép cộng `i + 1` dùng unboxing, nhưng nhánh `if` đã bảo đảm `i` không phải `null`. Tuy nhiên, phép cộng `int` vẫn có khả năng tràn số ở `Integer.MAX_VALUE`; nếu cần phát hiện tràn số, dùng `Math.addExact(i, 1)`.

## 9. Generic container cũng không tự biến phần tử thành primitive pattern

Java generics chỉ nhận **reference type** làm type argument. Không thể khai báo `List<int>`; phải dùng `List<Integer>`. Nhưng do *type erasure*, type pattern `instanceof List<Integer> list` không phải cách kiểm tra một `Object` có chứa toàn `Integer` hay không.

Cách phù hợp là kiểm tra container theo kiểu có thể kiểm tra ở runtime, rồi kiểm tra phần tử theo wrapper:

```java
static int sumIntegers(Object input) {
    if (!(input instanceof java.util.List<?> list)) {
        return 0;
    }

    int sum = 0;
    for (Object element : list) {
        if (element instanceof Integer number) {
            sum += number; // unboxing ở phép cộng
        }
    }
    return sum;
}
```

Đây là method minh họa; nó cố ý **bỏ qua phần tử không phải `Integer`**. Nếu yêu cầu nghiệp vụ là “mọi phần tử phải là số nguyên”, cần kiểm tra toàn bộ và báo lỗi thay vì im lặng bỏ qua. Cũng cần xem xét tràn số khi cộng; type pattern không tự kiểm tra điều kiện số học.

## 10. Chương trình hoàn chỉnh chạy trên JDK 21

Tạo file **`PrimitivePatternDemo.java`**:

```java
public class PrimitivePatternDemo {
    record Reading(int amount, String unit) {}

    static String examine(Object value) {
        return switch (value) {
            case null -> "null";
            case Integer number when number > 0 -> "positive wrapper:" + number;
            case Integer number -> "wrapper:" + number;
            case Reading(int amount, String unit) ->
                    "record:" + amount + " " + unit;
            default -> "other";
        };
    }

    static String byConstant(int code) {
        return switch (code) {
            case 0 -> "zero";
            case 1 -> "one";
            default -> "different";
        };
    }

    public static void main(String[] args) {
        int primitive = 7;
        Object boxed = primitive; // int -> Integer

        if (boxed instanceof Integer number) {
            System.out.println("instanceof:" + (number + 1));
        }

        System.out.println(examine(boxed));
        System.out.println(examine(-3));
        System.out.println(examine(new Reading(12, "items")));
        System.out.println(byConstant(1));
        System.out.println(examine(null));
    }
}
```

Biên dịch/chạy với **JDK 21**:

```bash
javac --release 21 PrimitivePatternDemo.java
java PrimitivePatternDemo
```

Stdout dự kiến:

```text
instanceof:8
positive wrapper:7
wrapper:-3
record:12 items
one
null
```

Giải thích theo từng dòng:

1. `boxed` chứa một đối tượng `Integer` được tạo bởi boxing từ `primitive`; pattern `Integer number` khớp và phép cộng cho kết quả `8`.
2. `examine(boxed)` khớp `case Integer number when number > 0`, in `positive wrapper:7`.
3. `examine(-3)` nhận `Integer` do boxing lúc truyền đối số vào tham số `Object`; guard `> 0` sai, nên nhánh `Integer` kế tiếp trả `wrapper:-3`.
4. `new Reading(12, "items")` là đối tượng record. Record pattern tách thành công component primitive `int amount` và component tham chiếu `String unit`; in `record:12 items`.
5. `byConstant(1)` là `switch` theo hằng số primitive, trả `one`, không có type pattern.
6. `examine(null)` được xử lý tường minh bởi `case null`.

Đây là ví dụ phân biệt đồng thời **primitive được dùng trực tiếp**, **wrapper được kiểm tra bằng type pattern**, và **primitive component được tách qua record pattern**. Lệnh `--release 21` kiểm tra cú pháp và API theo Java 21, không yêu cầu `--enable-preview`.

## 11. Khi nào nên chọn cách nào?

- **Biến đã là primitive `int`/`double`/...:** dùng toán tử số học, so sánh, `if`, và `switch` theo hằng số với selector primitive được Java 21 hỗ trợ. Không cần pattern chỉ để “xác nhận kiểu”.
- **Biến kiểu `Object` hoặc supertype có thể chứa wrapper:** dùng `instanceof Integer i`, `instanceof Double d`, hoặc pattern `switch` trên tham chiếu để phân biệt kiểu runtime.
- **Muốn xử lý nhiều wrapper số:** `instanceof Number n` hữu ích, nhưng hãy chọn cách chuyển đổi và chính sách mất dữ liệu/tràn số phù hợp.
- **Muốn tách primitive component từ một record:** dùng record pattern `Point(int x, int y)` hoặc `Point(var x, var y)` đúng kiểu component của record.
- **Cần kiểm tra miền giá trị:** kết hợp `when` trong pattern `switch`, điều kiện `&&` sau `instanceof`, hoặc validation riêng. Pattern matching không tự biến “đúng kiểu” thành “đúng dữ liệu”.
- **Cần hỗ trợ `null`:** phân biệt primitive và nullable wrapper; trong `switch` tham chiếu, cân nhắc `case null`; khi unbox, tránh wrapper `null`.

### Tài liệu đọc thêm

- Oracle Java 21 — Record Patterns: https://docs.oracle.com/en/java/javase/21/language/record-patterns.html
- Oracle Java 21 — Pattern Matching for switch: https://docs.oracle.com/en/java/javase/21/language/pattern-matching-switch.html
- JEP 440 — Record Patterns: https://openjdk.org/jeps/440
- JEP 441 — Pattern Matching for switch: https://openjdk.org/jeps/441

**Kết luận:** Trong Java 21, type pattern trực tiếp của `instanceof` và nhãn `case` ở mức ngoài cùng làm việc với **reference type**; đối với các giá trị primitive độc lập, dùng cấu trúc điều kiện thông thường. Primitive vẫn có vai trò trong pattern matching thông qua **component type pattern bên trong record pattern**. Nhận diện đúng *vị trí* của pattern và *kiểu thực tế* của selector sẽ giúp chọn cú pháp hợp lệ và giải thích hành vi chính xác.
