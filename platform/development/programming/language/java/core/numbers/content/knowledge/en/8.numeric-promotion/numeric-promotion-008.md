# Unboxing khi biểu thức chứa wrapper trong Java

## 1. Vì sao một biểu thức chứa `Integer` có thể gây lỗi?

Java có các **kiểu nguyên thủy** như `int`, `long`, `double`, `boolean` và các **lớp bao** (*wrapper*) tương ứng như `Integer`, `Long`, `Double`, `Boolean`. Wrapper là đối tượng và có thể mang tham chiếu `null`; primitive lưu giá trị của kiểu nguyên thủy và không thể là `null`.

**Unboxing** là việc Java tự chuyển giá trị của wrapper sang primitive tương ứng khi ngữ cảnh đòi hỏi primitive. Ví dụ:

```java
Integer boxed = 10;
int primitive = boxed; // unboxing: Integer -> int
```

Ngược lại, **boxing** là chuyển giá trị primitive thành wrapper:

```java
int primitive = 10;
Integer boxed = primitive; // boxing: int -> Integer
```

Trong một phép toán số học, Java có thể thực hiện một chuỗi bước: **unboxing → thăng cấp số học → tính toán → (nếu cần) boxing khi gán kết quả**. Vì vậy nhìn thấy các toán hạng có kiểu `Integer` không có nghĩa phép cộng tạo ra `Integer` hay phép cộng được thực hiện giữa các đối tượng.

Ví dụ trực tiếp:

```java
Integer left = 7;
Integer right = 5;

int sum = left + right;      // unbox cả hai, cộng int -> 12
Integer boxedSum = left + right; // unbox, cộng int, boxing kết quả -> 12
```

Nếu một wrapper bị unbox khi đang là `null`, Java ném **`NullPointerException` (NPE)**. Nó không tự coi `null` là 0, `false` hoặc một giá trị mặc định.

## 2. Nhận diện đúng kiểu primitive và lớp bao

| Primitive | Wrapper | Giá trị wrapper có thể là `null`? | Khi unbox |
|---|---|---|---|
| `byte` | `Byte` | Có | `byteValue()` tương ứng |
| `short` | `Short` | Có | `shortValue()` tương ứng |
| `int` | `Integer` | Có | `intValue()` tương ứng |
| `long` | `Long` | Có | `longValue()` tương ứng |
| `float` | `Float` | Có | `floatValue()` tương ứng |
| `double` | `Double` | Có | `doubleValue()` tương ứng |
| `char` | `Character` | Có | `charValue()` tương ứng |
| `boolean` | `Boolean` | Có | `booleanValue()` tương ứng |

Cụm “tương ứng” là cách hình dung quá trình chuyển đổi; mã nguồn thường chỉ viết biểu thức tự nhiên, ví dụ `boxed + 1`. Java thực hiện chuyển đổi cần thiết theo quy tắc của ngữ cảnh.

Các tình huống wrapper hữu ích gồm kiểu tổng quát như `List<Integer>` (Java generics không nhận `List<int>`), API cho phép thiếu dữ liệu dưới dạng `null`, hoặc thư viện yêu cầu đối tượng. Khi thực hiện tính toán thuần túy và không cần khả năng `null`, primitive thường rõ ràng hơn.

## 3. Unboxing trong phép cộng, trừ, nhân và chia

Khi toán tử số học yêu cầu kiểu số, wrapper được unbox trước. Với các kiểu tích phân, Java tiếp tục áp dụng **binary numeric promotion**:

- `Byte`, `Short` và `Character` sau unbox được nâng lên `int` khi dùng toán tử số học nhị phân.
- `Integer` sau unbox thành `int`.
- Nếu có toán hạng `Long` hoặc `long`, biểu thức tích phân dùng `long`.
- Với `Float`/`Double` hoặc `float`/`double`, kết quả theo quy tắc thăng cấp số thực tương ứng.

Ví dụ:

```java
Integer a = 10;
Integer b = 5;
Long wide = 2L;
Short small = 3;

int sum = a + b;           // int 15
int difference = a - b;    // int 5
int product = a * b;       // int 50
int quotient = a / b;      // int 2
long mixed = a + wide;     // long 12
int promoted = small * 4;  // int 12
```

Cách diễn giải `a + wide`:

1. `a` được unbox thành `int` 10.
2. `wide` được unbox thành `long` 2.
3. Thăng cấp `int` 10 thành `long` 10.
4. Cộng `long`, cho **`long` 12**.

**Kiểu kết quả do toán tử và quy tắc thăng cấp quyết định**. Kiểu wrapper của biến nhận kết quả chỉ có thể khiến Java boxing **sau khi tính**:

```java
Integer first = 10;
Integer second = 20;
Integer result = first + second; // int + int -> int 30 -> Integer
Long largeResult = first + 20L;  // int + long -> long 30 -> Long
```

Phép cộng số nguyên vẫn có thể **tràn** giống primitive. `Integer.MAX_VALUE + 1` khi được tính bằng `int` vẫn thành `Integer.MIN_VALUE`; wrapper không làm tăng miền giá trị.

## 4. Chương trình Java 17+: nhìn thấy kiểu và NPE

Lưu thành `UnboxingArithmeticDemo.java`:

```java
public class UnboxingArithmeticDemo {
    private static String typeOf(int ignored) {
        return "int";
    }

    private static String typeOf(long ignored) {
        return "long";
    }

    public static void main(String[] args) {
        Integer count = 7;
        Long increment = 5L;
        Short factor = 3;

        System.out.println("int addition: " + (count + 2));
        System.out.println("mixed result: " + (count + increment));
        System.out.println("type int: " + typeOf(count + 2));
        System.out.println("type long: " + typeOf(count + increment));
        System.out.println("short product: " + (factor * 4));

        Integer boxedSum = count + 2;
        System.out.println("boxed sum: " + boxedSum);

        Integer nullable = null;
        System.out.println("string concat: " + nullable);

        try {
            int invalid = nullable + 1;
            System.out.println(invalid);
        } catch (NullPointerException e) {
            System.out.println("arithmetic: NullPointerException");
        }

        try {
            nullable++;
        } catch (NullPointerException e) {
            System.out.println("increment: NullPointerException");
        }
    }
}
```

Chạy trên Java 17+:

```bash
javac UnboxingArithmeticDemo.java
java UnboxingArithmeticDemo
```

Kết quả:

```text
int addition: 9
mixed result: 12
type int: int
type long: long
short product: 12
boxed sum: 9
string concat: null
arithmetic: NullPointerException
increment: NullPointerException
```

Hai overload của `typeOf` là công cụ minh họa **kiểu của biểu thức tại lúc biên dịch**. Với `count + 2`, Java chọn overload `int`; với `count + increment`, Java chọn `long`.

Một điểm đáng chú ý: `"string concat: " + nullable` là **nối chuỗi**, nên giá trị tham chiếu `null` được biểu diễn bằng văn bản `"null"`. Ngược lại, `nullable + 1` cần lấy giá trị số, dẫn đến unboxing và NPE. Hai biểu thức cùng dùng `+` nhưng thuộc **hai ngữ cảnh khác nhau**.

## 5. Phép gán và phép gán kết hợp

### 5.1. Gán primitive từ wrapper

```java
Integer boxed = 42;
int number = boxed; // unboxing
```

Nếu `boxed == null`, phép gán trên sẽ ném NPE. Nếu muốn mặc định 0 khi thiếu giá trị:

```java
Integer boxed = null;
int number = boxed != null ? boxed : 0; // 0
```

Biểu thức điều kiện chỉ đánh giá nhánh được chọn. Ở đây nhánh `boxed` chỉ được chọn khi khác `null`; do đó quá trình unboxing an toàn trong điều kiện này.

### 5.2. `+=`, `-=`, `*=` và `++` cũng có thể unbox

```java
Integer count = 10;
count += 5; // unboxing -> cộng int -> boxing, count = 15
count++;    // unboxing -> tăng int -> boxing, count = 16
```

`Integer` là **đối tượng bất biến** (*immutable*). Các phép cập nhật trên biến wrapper không sửa giá trị bên trong cùng đối tượng; Java tính một giá trị primitive rồi gán lại tham chiếu wrapper phù hợp.

Nếu `count` đang là `null` thì `count += 5` hoặc `count++` cần unboxing và ném NPE. Không thể dựa vào cú pháp `+=` để suy ra null được coi là 0.

### 5.3. Gán kết quả sang kiểu wrapper khác cần đúng quy tắc chuyển đổi

```java
Integer a = 10;
Long b = 20L;

Long total = a + b; // hợp lệ: long 30 -> Long
// Long invalid = a + a; // lỗi biên dịch: int -> Long không phải chuỗi chuyển đổi gán này
long primitiveTotal = a + a; // hợp lệ: int 20 -> long
```

Dòng comment minh họa một giới hạn: Java không tự kết hợp **mở rộng primitive `int` thành `long` rồi boxing thành `Long`** trong phép gán thông thường từ biểu thức `int`. Nếu cần `Long`, hãy thực hiện phép toán kiểu `long`, ví dụ `Long total = (long) a + a;`.

## 6. So sánh: khi nào `==` unbox, khi nào so tham chiếu?

Toán tử `==` có những quy tắc khác nhau tùy kiểu toán hạng.

### 6.1. Wrapper so với primitive số: có unboxing

```java
Integer boxed = 10;
boolean equal = boxed == 10; // true, boxed được unbox
```

Nếu `boxed` là `null`, biểu thức `boxed == 10` có thể ném NPE vì phải unbox trước khi so sánh số.

```java
Integer boxed = null;
boolean isMissing = boxed == null; // true, so sánh tham chiếu, an toàn
// boolean zero = boxed == 0;     // khi chạy sẽ ném NullPointerException
```

**`boxed == null` không unbox**, vì đang so sánh tham chiếu với `null`. Đó là cách kiểm tra thiếu dữ liệu hợp lệ.

### 6.2. Hai wrapper cùng kiểu: có thể so tham chiếu

```java
Integer a = Integer.valueOf(200);
Integer b = Integer.valueOf(200);

boolean sameReference = a == b; // so tham chiếu; đừng dựa vào true/false
boolean sameValue = a.equals(b); // true
```

Khi hai toán hạng đều là `Integer`, `==` kiểm tra **có cùng đối tượng không**. Việc wrapper có thể tái sử dụng đối tượng qua cache khiến `==` đôi khi trả `true` cho cùng giá trị; **đó không phải quy tắc so sánh giá trị đáng tin cậy**.

Dùng `a.equals(b)` để so giá trị khi chắc `a` khác `null`, hoặc `java.util.Objects.equals(a, b)` khi một hay cả hai có thể là `null`:

```java
Integer a = null;
Integer b = null;

System.out.println(java.util.Objects.equals(a, b)); // true
System.out.println(java.util.Objects.equals(a, 0)); // false
```

Ngoài ra, so hai wrapper **khác kiểu** như `Integer` và `Long` có những hạn chế về khả năng so sánh tham chiếu trong biểu thức `==`. Khi mục tiêu là so giá trị số, hãy xác định kiểu số mong muốn và chuyển đổi có kiểm tra, thay vì kỳ vọng `==` tự so mọi loại wrapper theo giá trị.

### 6.3. So sánh quan hệ `<`, `>`, `<=`, `>=`

Các toán tử quan hệ yêu cầu giá trị số nên wrapper số bị unbox:

```java
Integer min = 3;
Long max = 7L;

System.out.println(min < max); // true
```

Nếu một toán hạng cần unbox mà là `null`, Java ném NPE. Cách an toàn là kiểm tra null trước hoặc thiết lập chính sách mặc định/từ chối dữ liệu thiếu.

## 7. `Boolean` trong điều kiện và toán tử logic

Wrapper `Boolean` có thể mang ba trạng thái ở mức tham chiếu: `Boolean.TRUE`, `Boolean.FALSE`, và `null`. Nhưng một điều kiện `if` hay vòng lặp `while` cần **giá trị primitive `boolean`**.

```java
Boolean enabled = Boolean.TRUE;
if (enabled) { // unbox Boolean -> boolean
    System.out.println("enabled");
}
```

Nếu `enabled == null`, `if (enabled)` ném NPE.

Tương tự, các toán tử `!`, `&&`, `||` khi cần giá trị `boolean` cũng có thể unbox wrapper:

```java
Boolean flag = null;
// boolean inverted = !flag;    // NullPointerException
// boolean result = flag && true; // NullPointerException
```

### Kiểm tra null bằng short-circuit

Toán tử `&&` và `||` có **short-circuit**: nhánh bên phải chỉ được đánh giá khi cần.

```java
Boolean flag = null;

boolean safeEnabled = flag != null && flag; // false, không unbox null
boolean alsoSafe = Boolean.TRUE.equals(flag); // false
```

Với `flag != null && flag`, vế trái sai nên vế phải không được đánh giá. Với `Boolean.TRUE.equals(flag)`, phương thức của đối tượng `Boolean.TRUE` không bị gọi trên null; nó trả false nếu flag null.

Hai cách biểu đạt chính sách khác nhau tùy ứng dụng: coi null là false có thể hợp lý với cờ tùy chọn, nhưng **không** nên mặc định null thành false khi null có nghĩa “chưa xác minh”, “chưa nhập” hoặc “không biết”. Trong trường hợp đó, hãy xử lý trạng thái thiếu dữ liệu một cách tường minh.

## 8. Chương trình Java 17+: so sánh và điều kiện null-safe

Lưu tệp `UnboxingConditionsDemo.java`:

```java
import java.util.Objects;

public class UnboxingConditionsDemo {
    public static void main(String[] args) {
        Boolean enabled = null;
        Integer limit = null;

        System.out.println("enabled == null: " + (enabled == null));
        System.out.println("Boolean.TRUE.equals: "
                + Boolean.TRUE.equals(enabled));
        System.out.println("short circuit boolean: "
                + (enabled != null && enabled));
        System.out.println("short circuit numeric: "
                + (limit != null && limit > 0));

        int defaultLimit = limit != null ? limit : 0;
        System.out.println("default limit: " + defaultLimit);
        System.out.println("Objects.equals: " + Objects.equals(limit, 0));

        try {
            boolean active = enabled;
            System.out.println(active);
        } catch (NullPointerException e) {
            System.out.println("boolean unboxing: NullPointerException");
        }

        try {
            boolean positive = limit > 0;
            System.out.println(positive);
        } catch (NullPointerException e) {
            System.out.println("numeric comparison: NullPointerException");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac UnboxingConditionsDemo.java
java UnboxingConditionsDemo
```

Kết quả:

```text
enabled == null: true
Boolean.TRUE.equals: false
short circuit boolean: false
short circuit numeric: false
default limit: 0
Objects.equals: false
boolean unboxing: NullPointerException
numeric comparison: NullPointerException
```

Ở hai biểu thức `enabled != null && enabled` và `limit != null && limit > 0`, Java dừng tại vế trái khi kết quả false, nên **tránh được unboxing của null**. Còn `boolean active = enabled` và `limit > 0` bắt buộc lấy giá trị primitive nên NPE là kết quả đúng theo quy tắc ngôn ngữ.

## 9. Toán tử ba ngôi `?:` và unboxing ẩn

Biểu thức điều kiện dạng `condition ? left : right` là một nơi rất dễ bỏ sót việc chuyển đổi kiểu.

Trong Java, **chỉ một trong hai nhánh `left` hoặc `right` được đánh giá**; tuy nhiên kiểu của toàn biểu thức được xác định theo quy tắc kiểu của toán tử điều kiện khi biên dịch. Nếu quy tắc kiểu yêu cầu primitive, **nhánh wrapper được chọn có thể bị unbox**.

Ví dụ:

```java
Integer maybe = null;

int safe = maybe != null ? maybe : 0; // 0; nhánh null không được chọn
int chosen = true ? 7 : maybe;       // 7; nhánh maybe không được đánh giá
// int bad = false ? 7 : maybe;       // sẽ ném NullPointerException
```

Không nên dựa vào khả năng “nhánh này thường không chạy” để bỏ qua chính sách null. Khi điều kiện thay đổi ở runtime, một nhánh chứa wrapper null có thể trở thành nhánh được chọn.

Mã rõ ràng hơn cho dữ liệu có thể thiếu:

```java
Integer value = null;
int effective = value == null ? 0 : value;
```

Nếu null là lỗi nghiệp vụ, thay vì mặc định 0, hãy kiểm tra và báo lỗi rõ ràng trước khi thực hiện phép toán.

## 10. Wrapper với nối chuỗi: trường hợp `+` không unbox

Toán tử `+` vừa là phép cộng số học, vừa là phép nối chuỗi. Khi **một toán hạng là `String`**, Java nối biểu diễn văn bản của toán hạng còn lại:

```java
Integer count = null;

String message = "count=" + count; // "count=null"
```

Biến `count` vẫn là `null`; Java chỉ sinh văn bản `"null"` để nối chuỗi. Nó **không** thực hiện unboxing để cộng số.

Sự khác biệt xuất hiện khi có dấu ngoặc:

```java
Integer a = 2;
Integer b = 3;

String first = "sum=" + a + b;     // "sum=23"
String second = "sum=" + (a + b); // "sum=5"
```

- `first`: phép `"sum=" + a` đã là nối chuỗi, phép `+ b` tiếp tục nối.
- `second`: dấu ngoặc buộc `a + b` chạy bằng **phép cộng số**, unbox hai wrapper, cho `int` 5; sau đó mới nối chuỗi.

Với `Integer a = null`, `"sum=" + a` cho `"sum=null"` nhưng `"sum=" + (a + 1)` ném NPE do phép cộng trong ngoặc cần unboxing.

**Lưu ý:** đừng kết luận phép nối với mọi loại đối tượng đều an toàn tuyệt đối; một `toString()` do ứng dụng tự viết vẫn có thể ném ngoại lệ. Với wrapper null, hành vi nối ra văn bản `"null"` là quy tắc đơn giản và ổn định.

## 11. Unboxing trong Collections, Stream và API tổng hợp

Java generics yêu cầu các tham số kiểu là **reference type**. Vì vậy dùng `List<Integer>`, không dùng `List<int>`:

```java
java.util.List<Integer> values = java.util.Arrays.asList(1, 2, 3);
int sum = 0;

for (Integer value : values) {
    sum += value; // unbox Integer -> int
}
```

Danh sách có thể chứa `null` nếu API cho phép, khi đó phép cộng trong vòng lặp ném NPE. Điều tương tự xảy ra ở các API cần primitive:

```java
// values.stream().mapToInt(Integer::intValue).sum()
```

`Integer::intValue` cần được gọi trên từng phần tử; nếu có phần tử null, lời gọi gặp NPE. Có thể **lọc null** trước khi chuyển:

```java
int sum = values.stream()
        .filter(java.util.Objects::nonNull)
        .mapToInt(Integer::intValue)
        .sum();
```

Cách này ngầm áp dụng chính sách “bỏ qua các phần tử null”. Nếu null biểu thị dữ liệu bị lỗi hoặc cần được ghi nhận, hãy thay bằng kiểm tra tường minh thay vì âm thầm loại bỏ.

### Ví dụ runnable với danh sách chứa null

Tạo file `UnboxingCollectionDemo.java`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

public class UnboxingCollectionDemo {
    public static void main(String[] args) {
        List<Integer> values = Arrays.asList(1, null, 3);

        int filteredSum = values.stream()
                .filter(Objects::nonNull)
                .mapToInt(Integer::intValue)
                .sum();
        System.out.println("filtered sum: " + filteredSum);

        try {
            int rawSum = values.stream()
                    .mapToInt(Integer::intValue)
                    .sum();
            System.out.println(rawSum);
        } catch (NullPointerException e) {
            System.out.println("raw stream: NullPointerException");
        }
    }
}
```

Chạy:

```bash
javac UnboxingCollectionDemo.java
java UnboxingCollectionDemo
```

Kết quả:

```text
filtered sum: 4
raw stream: NullPointerException
```

Đây là ví dụ về **hành vi thực tế của giá trị null trong pipeline**, không có nghĩa `Stream<Integer>` tự động loại bỏ null hay tự nhận giá trị 0.

## 12. Unboxing không bảo vệ khỏi tràn số và phép chia cho 0

Sau unboxing, các phép toán primitive áp dụng quy tắc bình thường:

```java
Integer max = Integer.MAX_VALUE;
int overflowed = max + 1; // Integer.MIN_VALUE

Integer numerator = 10;
Integer denominator = 0;
// int q = numerator / denominator; // ArithmeticException: / by zero
```

Ở dòng cộng, kết quả vẫn tràn theo miền `int`. Ở phép chia, các wrapper được unbox thành số nguyên trước; phép chia cho 0 ném `ArithmeticException`, **không** phải lỗi của boxing/unboxing.

Nếu mẫu dữ liệu cho phép null, ba tình huống cần phân biệt:

1. **Wrapper null** khi cần unbox → `NullPointerException`.
2. **Số chia bằng 0** sau unbox → `ArithmeticException` đối với phép chia nguyên.
3. **Giá trị vượt miền** khi cộng/trừ/nhân số nguyên bình thường → thường không tự ném ngoại lệ mà cho kết quả theo độ rộng số nguyên.

Khi tràn là lỗi nghiệp vụ, chọn API kiểm tra như `Math.addExact`, `Math.multiplyExact`; chúng vẫn không thay thế bước kiểm tra null nếu đầu vào là wrapper.

## 13. Thiết kế API an toàn với wrapper nullable

Trước khi xử lý, cần quyết định rõ **null có nghĩa gì**:

- **Bắt buộc phải có số:** kiểm tra null và báo lỗi với thông điệp hữu ích, trước khi unbox.
- **Null có nghĩa “mặc định 0”:** chuyển thành primitive 0 bằng biểu thức có kiểm tra.
- **Null có nghĩa “chưa biết”:** lưu trạng thái thiếu và xử lý riêng, không biến thành 0.
- **Một dãy cho phép bỏ giá trị null:** lọc null có chủ đích, đồng thời bảo đảm điều đó phù hợp yêu cầu.

Ví dụ phương thức yêu cầu giá trị:

```java
static int requireQuantity(Integer quantity) {
    if (quantity == null) {
        throw new IllegalArgumentException("quantity is required");
    }
    return quantity; // unboxing an toàn sau khi kiểm tra
}
```

Và ví dụ mặc định bằng 0:

```java
static int quantityOrZero(Integer quantity) {
    return quantity == null ? 0 : quantity;
}
```

Các đoạn trên là **phương thức minh họa**, cần được đặt trong một class mới tạo thành mã chạy độc lập. Chọn phương thức theo hợp đồng API chứ không đặt mặc định 0 ở mọi nơi: thiếu dữ liệu và dữ liệu thật bằng 0 có thể mang ý nghĩa khác nhau.

Với `Boolean` nullable, cách viết `Boolean.TRUE.equals(flag)` đặc biệt dễ đọc khi chính sách là **chỉ trạng thái true mới được tính là bật**. Nếu cần ba trạng thái true/false/unknown, nên giữ `Boolean` hoặc dùng kiểu miền dữ liệu tường minh thay vì ép mọi giá trị về primitive.

### Dùng `Objects.requireNonNull` khi null là lỗi

`java.util.Objects.requireNonNull(quantity, "quantity is required")` có thể kiểm tra không-null ở ranh giới API và ném NPE với thông báo rõ ràng. Sau khi kiểm tra, unboxing từ wrapper đã được xác nhận hợp lệ.

Những phương thức như `Objects.equals(a, b)` phục vụ **so sánh đối tượng null-safe**, không phải phương thức tự động chuyển wrapper null thành số 0.

## 14. Hiệu năng và tính rõ ràng

Autoboxing và unboxing giúp mã Java gọn, nhưng mỗi lần chuyển có thể liên quan đến hoạt động đối tượng, sự kiện null hoặc bộ nhớ/cấp phát tùy ngữ cảnh và tối ưu JVM.

Với vòng lặp tính toán lớn, `int`, `long` và các mảng primitive thường phù hợp nếu không cần nullable hoặc generics:

```java
long total = 0;
int[] numbers = {1, 2, 3};

for (int number : numbers) {
    total += number;
}
```

Điều này không có nghĩa phải thay mọi `List<Integer>` bằng mảng primitive. Hãy chọn kiểu theo tính đúng đắn và ràng buộc API; cân nhắc hiệu năng khi đo được vấn đề thực tế.

Một lỗi thiết kế dễ gặp là dùng wrapper nullable trong mã nghiệp vụ nhưng **không xác định chính sách null**. Hệ thống có thể vẫn chạy ở các ca thông thường, rồi ném NPE khi nhận giá trị thiếu từ database, JSON hoặc lời gọi API. Kiểm tra null tại ranh giới dữ liệu giúp đặt lỗi đúng nơi và dễ truy vết hơn.

## 15. Các nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế | Cách xử lý |
|---|---|---|
| `Integer + Integer` trả `Integer` | Unbox rồi cộng `int`; kết quả biểu thức là `int` | Xác định kiểu của toán tử; boxing chỉ xảy ra sau nếu cần |
| `Integer null + 1` tự xem null là 0 | Unbox null ném NPE | Kiểm tra/định nghĩa null trước khi cộng |
| Gán sang `Integer` bảo vệ khỏi tràn | Phép cộng `int` vẫn có thể tràn | Dùng kiểu rộng, `Math.*Exact` khi phù hợp |
| `Integer a == Integer b` luôn so giá trị | Với hai wrapper cùng kiểu, `==` có thể so tham chiếu | Dùng `equals` hoặc `Objects.equals` |
| `Integer a == 0` luôn an toàn | Wrapper bị unbox; null gây NPE | Kiểm tra null trước khi so số |
| `a == null` cũng unbox | So với null là so tham chiếu | Dùng được để phát hiện thiếu dữ liệu |
| `Boolean flag` dùng trong `if` không cần kiểm tra | `if` cần primitive boolean, có unboxing | Dùng null-check hoặc `Boolean.TRUE.equals` |
| `"value=" + nullable` luôn unbox | Đây là nối chuỗi và có thể hiển thị `null` | Phân biệt nối chuỗi với cộng số |
| `List<Integer>` không thể có null | List có thể chứa null tùy API | Kiểm tra trước phép cộng hoặc mapping primitive |
| `count++` trên `Integer` sửa cùng object | Unbox, tính primitive, boxing rồi gán lại | Hiểu tính bất biến của wrapper |
| `int` → `Long` tự chuyển mọi bước | Không có chuỗi widening primitive rồi boxing trong phép gán này | Tạo biểu thức `long` trước khi boxing |

## 16. Bài tập tự kiểm tra

**Câu 1.** Biểu thức `Integer a = 2; Integer b = 3; a + b` có kiểu gì?  
**Đáp án:** `int`. Java unbox hai wrapper rồi cộng hai số nguyên primitive.

**Câu 2.** Nếu `Integer x = null;`, `x == null` và `x == 0` khác nhau thế nào?  
**Đáp án:** `x == null` trả true vì so tham chiếu; `x == 0` cần unbox và ném `NullPointerException`.

**Câu 3.** Với `Integer x = null;`, `"x=" + x` cho gì?  
**Đáp án:** Chuỗi `"x=null"` vì đây là nối chuỗi, không cần unbox số.

**Câu 4.** `Integer a = 2, b = 3;`: vì sao `"sum=" + a + b` khác `"sum=" + (a + b)`?  
**Đáp án:** Dạng đầu nối hai biểu diễn văn bản, cho `"sum=23"`; dạng sau tính số `a + b` bằng unboxing trước, cho `"sum=5"`.

**Câu 5.** `Short s = 2; int value = s * 4;` có hợp lệ không?  
**Đáp án:** Có. Unbox thành `short`, nâng lên `int` và nhân, cho 8.

**Câu 6.** `Boolean enabled = null; if (enabled) { ... }` có an toàn không?  
**Đáp án:** Không. Điều kiện phải unbox `Boolean` thành `boolean` và ném NPE.

**Câu 7.** Cách nào an toàn nếu null được coi là false: `enabled != null && enabled` hay `Boolean.TRUE.equals(enabled)`?  
**Đáp án:** Cả hai. Cách đầu dựa vào short-circuit; cách thứ hai so với đối tượng `Boolean.TRUE`.

**Câu 8.** Tại sao `Integer count = 1; count++;` hợp lệ còn `count = null; count++;` gây NPE?  
**Đáp án:** `++` trên wrapper cần unbox, cộng 1 và boxing lại. Khi count null, bước unbox thất bại.

**Câu 9.** Với `List<Integer> list = Arrays.asList(1, null, 3)`, lệnh `mapToInt(Integer::intValue)` có an toàn không?  
**Đáp án:** Không nếu gặp null; có thể lọc `Objects::nonNull` nếu hợp đồng dữ liệu cho phép bỏ phần tử đó.

**Câu 10.** `Integer max = Integer.MAX_VALUE; int result = max + 1;` có ném NPE hoặc ArithmeticException không?  
**Đáp án:** Không, vì max không null. Phép cộng `int` tràn và trả `Integer.MIN_VALUE`. Muốn phát hiện tràn dùng `Math.addExact`.

**Câu 11.** `Integer a = 10; Long b = 20L;` thì biểu thức `a + b` có kiểu gì?  
**Đáp án:** `long`. Hai wrapper được unbox; `int` được nâng lên `long` trước phép cộng.

**Câu 12.** Muốn dùng `Long result` nhận tổng hai biến `Integer x, y` mà không mất quy tắc kiểu, nên làm gì?  
**Đáp án:** Nếu đã xác nhận x và y không null, viết `Long result = (long) x + y;` để tính bằng `long` rồi boxing kết quả thành `Long`.

## 17. Kết luận và tài liệu tham khảo

Unboxing là **chuyển wrapper về primitive do ngữ cảnh biểu thức yêu cầu**. Với phép cộng, trừ, nhân, chia, so sánh số, điều kiện `boolean` hoặc phép tăng/giảm, Java có thể unbox mà không có từ khóa cast hiển thị. Sau unboxing, **thăng cấp số học và quy tắc số nguyên primitive** tiếp tục quyết định kiểu, tràn số, chia cho 0 và kết quả.

Ba nguyên tắc thực hành:

1. **Kiểm tra hoặc định nghĩa chính sách null** trước khi wrapper phải tham gia phép toán primitive.
2. **Phân biệt nối chuỗi với cộng số và so tham chiếu với so giá trị**; cùng cú pháp `+` hoặc `==` có thể chịu quy tắc khác nhau.
3. **Đừng nhầm boxing/unboxing với bảo vệ số học**; nếu cần chống tràn, vẫn phải tính bằng kiểu phù hợp hoặc dùng phép toán có kiểm tra.

Tham khảo chuẩn ngôn ngữ: [Java Language Specification — §5.1.8 Unboxing Conversion](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.1.8), [§5.6 Numeric Contexts](https://docs.oracle.com/javase/specs/jls/se21/html/jls-5.html#jls-5.6), [§15.18 Additive Operators](https://docs.oracle.com/javase/specs/jls/se21/html/jls-15.html#jls-15.18).
