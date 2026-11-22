# `Number` là lớp trừu tượng và hợp đồng chuyển đổi giá trị trong Java

Trong Java, `java.lang.Number` là **lớp trừu tượng (abstract class)** làm kiểu cha chung cho nhiều lớp biểu diễn số: `Byte`, `Short`, `Integer`, `Long`, `Float`, `Double`, `BigInteger`, `BigDecimal` và một số lớp số học đồng thời như `AtomicInteger`, `AtomicLong`. Mục đích của nó không phải cung cấp một “kiểu số chung có thể tự cộng, trừ, nhân, chia”, mà là cung cấp **giao diện ở cấp đối tượng để chuyển giá trị số sang một số kiểu nguyên thủy**.

```java
Number a = Integer.valueOf(42);
Number b = Long.valueOf(4_294_967_297L);
Number c = new java.math.BigDecimal("12.75");

System.out.println(a.intValue()); // 42
System.out.println(b.intValue()); // 1: không còn giữ đủ giá trị long.
System.out.println(c.intValue()); // 12: phần thập phân bị loại bỏ.
```

Cả ba cùng có kiểu tham chiếu `Number`, nhưng **hành vi chuyển đổi phụ thuộc lớp cụ thể của đối tượng**. Phương thức `intValue()` không cam kết luôn chính xác: có thể làm mất phần lẻ, mất độ lớn, mất bit quan trọng hoặc trả kết quả đổi dấu.

**Mục tiêu của bài:** hiểu hợp đồng của lớp `Number`, phân biệt phương thức trừu tượng và phương thức đã triển khai, sử dụng đa hình, nhận ra các chuyển đổi có thể mất thông tin, và quyết định khi nào cần cơ chế chuyển đổi *exact* riêng của từng kiểu.

## 1. Vị trí của `Number` trong hệ thống kiểu Java

Khai báo cơ bản của JDK:

```java
public abstract class Number implements java.io.Serializable {
    // Các phương thức chuyển giá trị sang kiểu nguyên thủy.
}
```

`Number` thuộc `java.lang` nên không cần `import`. Nó là một **class**, không phải interface; không thể tạo đối tượng bằng `new Number()` vì lớp là `abstract`.

```java
// Number n = new Number(); // Lỗi biên dịch: Number là abstract.

Number n1 = Integer.valueOf(10);
Number n2 = Double.valueOf(2.5);
Number n3 = new java.math.BigInteger("12345678901234567890");
```

Sơ đồ khái niệm:

```text
Object
  └── Number (abstract, Serializable)
       ├── Byte / Short / Integer / Long
       ├── Float / Double
       ├── BigInteger / BigDecimal
       ├── AtomicInteger / AtomicLong
       └── Các lớp con Number khác
```

Một số lớp kể trên là **wrapper của primitive**, một số không phải wrapper:

| Loại | Ví dụ | Đặc điểm |
| --- | --- | --- |
| Wrapper số nguyên | `Byte`, `Short`, `Integer`, `Long` | Đối tượng bất biến chứa giá trị primitive tương ứng |
| Wrapper số thực | `Float`, `Double` | Đối tượng bất biến chứa giá trị binary32/binary64 |
| Số nguyên tùy ý độ lớn | `BigInteger` | Bất biến, không giới hạn bởi 32/64 bit cố định (trong giới hạn bộ nhớ/triển khai) |
| Số thập phân | `BigDecimal` | Bất biến, giá trị gồm phần nguyên không tỷ lệ và `scale`; phù hợp thập phân chính xác |
| Số trong ngữ cảnh đồng thời | `AtomicInteger`, `AtomicLong` | Có thể thay đổi giá trị bằng thao tác atomic; không phải wrapper bất biến |

**Đừng hiểu `Number` là bảo đảm mọi lớp con đều bất biến hoặc thread-safe.** Đối tượng wrapper như `Integer` là bất biến; `AtomicInteger` lại có thể cập nhật. Mặc dù `Number` triển khai `Serializable`, các quyết định về biểu diễn bền vững, định dạng trao đổi, quy tắc so sánh và an toàn dữ liệu vẫn là trách nhiệm của API/kiểu cụ thể.

## 2. Hợp đồng sáu phương thức chuyển đổi

Theo API Java SE 17, `Number` khai báo sáu phương thức chính:

| Phương thức | Kiểu trả về | Trong `Number` | Bảo đảm |
| --- | --- | --- | --- |
| `intValue()` | `int` | **Trừu tượng** | Trả giá trị sau chuyển đổi sang `int` theo lớp triển khai |
| `longValue()` | `long` | **Trừu tượng** | Trả giá trị sau chuyển đổi sang `long` |
| `floatValue()` | `float` | **Trừu tượng** | Trả giá trị sau chuyển đổi sang `float` |
| `doubleValue()` | `double` | **Trừu tượng** | Trả giá trị sau chuyển đổi sang `double` |
| `byteValue()` | `byte` | **Có triển khai mặc định** | Mặc định lấy `(byte) intValue()` |
| `shortValue()` | `short` | **Có triển khai mặc định** | Mặc định lấy `(short) intValue()` |

Bốn phương thức trừu tượng yêu cầu **lớp con cụ thể phải cung cấp cách trả giá trị tương ứng**, trừ khi kế thừa một triển khai từ lớp cha trung gian. Hai phương thức `byteValue` và `shortValue` **không trừu tượng** trong `Number`, và lớp con có thể ghi đè nếu cần.

### Tại sao không có `charValue()` hay `booleanValue()`?

`char` và `boolean` đều là primitive Java, nhưng không thuộc sáu primitive được `Number` cung cấp chuyển đổi. `char` đại diện một đơn vị mã UTF-16, không phải kiểu số có dấu theo cùng hợp đồng; `boolean` không phải kiểu số. Vì vậy, **không có `Number.charValue()`, `Number.booleanValue()` hoặc `Number.stringValue()`**.

Muốn chuỗi, có thể gọi `toString()` của **đối tượng cụ thể**, nhưng `Number` không cam kết mọi lớp con sẽ dùng cùng một định dạng hiển thị hoặc cùng radix. Muốn phân tích chuỗi thành số, sử dụng parser riêng như `Integer.parseInt`, `Double.parseDouble`, `new BigInteger(String)`, `new BigDecimal(String)`; **`Number` không có phương thức static `parse` tổng quát**.

### Mã dạng đơn giản để hiểu hợp đồng

```java
public abstract class Number implements java.io.Serializable {
    public abstract int intValue();
    public abstract long longValue();
    public abstract float floatValue();
    public abstract double doubleValue();

    public byte byteValue() {
        return (byte) intValue();
    }

    public short shortValue() {
        return (short) intValue();
    }
}
```

Đây là **sơ đồ mô tả API**, không phải mã cần viết lại để thay `java.lang.Number` có sẵn trong JDK. Các chú thích truy xuất nguồn và chi tiết triển khai thực tế có thể khác; điều quan trọng là bốn phương thức abstract và hai phương thức có triển khai mặc định.

## 3. Đa hình: kiểu khai báo là `Number`, kiểu runtime quyết định hành vi

`Number` cho phép một API nhận nhiều kiểu số dưới cùng một kiểu tham chiếu:

```java
static void showAsDouble(Number number) {
    System.out.println(number.doubleValue());
}
```

Nếu truyền một `Integer`, một `Long` hoặc `BigDecimal`, Java gọi phương thức `doubleValue()` **được triển khai bởi đối tượng thực tế** (dynamic dispatch). Đây là đa hình; không phải tất cả số được “tự biến” thành `double` ngay lúc gán cho biến `Number`.

```java
Number n = Long.valueOf(9_007_199_254_740_993L);
System.out.println(n.longValue());   // 9007199254740993
System.out.println(n.doubleValue()); // 9.007199254740992E15 (mất 1 đơn vị).
```

`n` vẫn tham chiếu đối tượng `Long` giữ giá trị nguyên đúng. **Chỉ kết quả trả về của `doubleValue()`** có thể mất chính xác. Bản thân việc gán `Long` vào biến `Number` không tự thu hẹp giá trị.

### `Number` không có toán tử số học chung

```java
Number x = Integer.valueOf(3);
Number y = Double.valueOf(2.5);

// Number sum = x + y; // Không biên dịch: + không được định nghĩa cho Number.
double approximate = x.doubleValue() + y.doubleValue(); // 5.5.
```

Trong Java, toán tử `+` cho số nguyên thủy hoặc toán tử ghép chuỗi; nó **không được overload bởi class `Number`**. Việc hai đối tượng cùng là `Number` không cho Java biết nên dùng số nguyên lớn, số thập phân, hay chấm động nhị phân cho phép cộng.

Nếu **chủ động** chuyển cả hai sang `double`, phép cộng theo binary64 có thể hợp lý cho số đo gần đúng. Nhưng đó là **quyết định thuật toán**, không phải phép cộng trừu tượng giữ chính xác với mọi lớp con `Number`.

## 4. Hợp đồng là “chuyển giá trị”, không phải “giữ nguyên mọi thông tin”

Java API nói rõ: ngữ nghĩa chi tiết của `intValue`, `longValue`, `floatValue`, `doubleValue`... do **triển khai cụ thể** quyết định. Các chuyển đổi thường tương tự widening/narrowing primitive conversion, nên có thể:

1. **Mất phần lẻ:** `3.75` chuyển sang `int` thành `3`.
2. **Mất độ lớn:** `long` lớn hơn miền `int` chuyển sang `int` giữ mẫu bit thấp theo quy tắc thu hẹp nguyên.
3. **Thay đổi dấu:** số nguyên dương lớn có thể thành `int` âm.
4. **Mất độ chính xác:** một `long` vượt độ chính xác nguyên liên tiếp của `double` bị làm tròn.
5. **Mất miền hữu hạn:** `BigDecimal` rất lớn chuyển sang `double` có thể trở thành `Infinity`.
6. **Phụ thuộc trạng thái nếu lớp con có thể thay đổi:** `AtomicInteger.intValue()` đọc một giá trị tại thời điểm gọi.

`Number` **không hứa** sẽ ném exception nếu giá trị không thể biểu diễn chính xác dưới kiểu đích. Nếu nghiệp vụ đòi hỏi “không mất thông tin”, cần dùng các phương thức **exact** của loại số phù hợp hoặc kiểm tra miền/bước làm tròn riêng.

### Ví dụ: `long` thu hẹp xuống `int`

```java
Number n = Long.valueOf(4_294_967_297L);
System.out.println(n.longValue()); // 4294967297
System.out.println(n.intValue());  // 1
```

Giá trị ban đầu bằng `2^32 + 1`. Khi chuyển thành `int` 32 bit, các bit cao bị bỏ đi và 32 bit thấp biểu diễn 1. **Không có `ArithmeticException`** ở lời gọi `intValue()` này.

Tương tự:

```java
Number n = new java.math.BigInteger("2147483648");
System.out.println(n.intValue()); // -2147483648
```

Giá trị `2^31` không nằm trong miền `int` có dấu; 32 bit thấp có bit dấu bằng 1, nên kết quả thành `Integer.MIN_VALUE`. Dữ liệu không còn cùng dấu và độ lớn ban đầu.

### Ví dụ: `double` sang `int`

```java
System.out.println(Double.valueOf(3.75).intValue()); // 3
System.out.println(Double.valueOf(-3.75).intValue()); // -3
System.out.println(Double.valueOf(Double.NaN).intValue()); // 0
System.out.println(Double.valueOf(Double.POSITIVE_INFINITY).intValue()); // 2147483647
```

Các quy tắc chuyển primitive floating-point sang integer trong Java gồm bỏ phần lẻ theo hướng về 0, NaN thành 0, và giới hạn về giá trị cực đại/cực tiểu của kiểu nguyên trong các trường hợp ngoài miền. **Không được** diễn giải 0 trả về từ NaN là phép đo thật sự bằng 0. Nếu dữ liệu ngoại vi chứa NaN/Infinity, hãy xác thực bằng `Double.isFinite` trước khi chuyển.

## 5. Vì sao `byteValue()` và `shortValue()` dễ gây bất ngờ?

Mặc định `Number.byteValue()` tương đương với gọi `intValue()` rồi cast `byte`; `shortValue()` tương tự:

```java
byte small = (byte) 258; // 2.
short shortResult = (short) 65537; // 1.
```

Một lớp con chỉ cần triển khai bốn phương thức trừu tượng, và có thể kế thừa hai hành vi này. Do đó, ngay cả khi lớp con lưu dữ liệu trong `long`, gọi `byteValue()` theo mặc định sẽ qua bước `intValue()`. Các lớp con có thể override nếu hợp đồng của chúng cần hành vi khác.

**Kết luận:** tên `byteValue()` không có nghĩa “kiểm tra giá trị vừa miền byte”; nó chỉ yêu cầu một kết quả kiểu `byte`. Nếu muốn phát hiện mất dữ liệu, xem các phương thức `byteValueExact()` của `BigInteger` hoặc `BigDecimal`, thay vì mặc định tin `Number.byteValue()`.

## 6. Tự triển khai một lớp con `Number`

Khi có một loại số tự định nghĩa cần tham gia API nhận `Number`, ta có thể tạo lớp con và cài đặt bốn phương thức trừu tượng:

```java
static final class CounterNumber extends Number {
    private final long value;

    CounterNumber(long value) {
        this.value = value;
    }

    @Override
    public int intValue() {
        return (int) value;
    }

    @Override
    public long longValue() {
        return value;
    }

    @Override
    public float floatValue() {
        return value;
    }

    @Override
    public double doubleValue() {
        return value;
    }
}
```

Đây là **lớp lồng trong một class khác**, minh họa với dữ liệu lưu `long`. Chương trình đầy đủ có ở phần 11.

- `longValue()` giữ nguyên giá trị đã lưu.
- `intValue()` có thể tràn theo quy tắc cast `long -> int`.
- `floatValue()` và `doubleValue()` có thể làm tròn số nguyên lớn.
- `byteValue()` và `shortValue()` được kế thừa từ `Number`, thông qua `intValue()`.

```java
System.out.println(new CounterNumber(258L).byteValue()); // 2
```

**Lưu ý thiết kế:** mở rộng `Number` không tự tạo các API parse, format, cộng, so sánh hay hợp đồng equality có ý nghĩa. Nếu class đại diện tiền, phân số, đơn vị đo hoặc số bất biến riêng, cần thiết kế những thao tác đó một cách độc lập, và xem xét có thực sự cần kế thừa `Number` hay không. Đây là lựa chọn kiến trúc, không phải điều kiện bắt buộc của mọi lớp “có giá trị số”.

## 7. Phương thức `Exact` thuộc lớp con, không thuộc `Number`

`Number` không có `intValueExact()` hoặc `longValueExact()` dùng chung. Tuy nhiên các lớp số lớn cung cấp API kiểm tra mất thông tin.

| Loại | Phương thức | Bảo đảm / phản ứng |
| --- | --- | --- |
| `BigInteger` | `intValueExact()`, `longValueExact()`, `shortValueExact()`, `byteValueExact()` | Ném `ArithmeticException` nếu giá trị nguyên vượt miền kiểu đích |
| `BigDecimal` | `intValueExact()`, `longValueExact()`, `shortValueExact()`, `byteValueExact()` | Ném `ArithmeticException` nếu có phần lẻ khác 0 **hoặc** không vừa miền đích |
| `BigDecimal` | `toBigIntegerExact()` | Ném `ArithmeticException` nếu có phần thập phân khác 0 |
| `long` sang `int` | `Math.toIntExact(long)` | Ném `ArithmeticException` nếu `long` không vừa `int` |

### `BigDecimal`: `intValue` và `intValueExact` là hai chính sách

```java
java.math.BigDecimal value =
        new java.math.BigDecimal("12.75");

System.out.println(value.intValue()); // 12
// value.intValueExact(); // ArithmeticException: bỏ phần lẻ khác 0.
```

`intValue()` trên `BigDecimal` bỏ phần lẻ và khi giá trị nguyên vượt miền `int` có thể chỉ giữ 32 bit thấp. `intValueExact()` yêu cầu giá trị **là số nguyên** và **vừa `int`**. Chẳng hạn `new BigDecimal("12.00").intValueExact()` trả 12, vì phần thập phân toán học bằng 0.

### `BigInteger`: chỉ cần kiểm tra giới hạn

```java
java.math.BigInteger tooLarge =
        new java.math.BigInteger("2147483648");

System.out.println(tooLarge.intValue()); // -2147483648
// tooLarge.intValueExact(); // ArithmeticException: vượt Integer.MAX_VALUE.
```

`BigInteger` luôn biểu diễn một số nguyên, nên không có phần lẻ cần bỏ; API exact chủ yếu kiểm tra **miền kiểu đích**.

### `long` sang `int` khi đang làm việc với primitive

```java
long count = 4_294_967_297L;
// int unsafe = (int) count;       // 1, mất bit cao.
// int safe = Math.toIntExact(count); // ArithmeticException.
```

Các API exact này **không phải phương thức của `Number`**. Khi biến chỉ có kiểu khai báo `Number`, trình biên dịch không biết có `intValueExact` trên mọi subtype hay không. Phải thiết kế hợp đồng đầu vào, kiểm tra loại cụ thể hoặc chọn một API có kiểu chính xác hơn.

## 8. Xử lý một `Number` không rõ lớp mà không mất dữ liệu âm thầm

Một cách *không nên làm* khi muốn giữ nguyên thập phân:

```java
static java.math.BigDecimal badConversion(Number n) {
    return new java.math.BigDecimal(n.doubleValue());
}
```

Hàm này chuyển mọi loại số sang `double` trước: `BigInteger` lớn có thể mất chữ số và `BigDecimal` chính xác có thể bị làm tròn; `new BigDecimal(double)` sẽ mô tả **chính xác xấp xỉ nhị phân** đã được đưa vào, không khôi phục dữ liệu gốc. Ngoài ra `Double.NaN` và vô cực không thể tạo `BigDecimal` theo cách này.

Một ví dụ **có hợp đồng rõ** chỉ chấp nhận kiểu thập phân và kiểu nguyên thích hợp:

```java
static java.math.BigDecimal toExactDecimal(Number n) {
    if (n == null) {
        throw new IllegalArgumentException("number is required");
    }
    if (n instanceof java.math.BigDecimal bd) {
        return bd;
    }
    if (n instanceof java.math.BigInteger bi) {
        return new java.math.BigDecimal(bi);
    }
    if (n instanceof Byte || n instanceof Short
            || n instanceof Integer || n instanceof Long) {
        return java.math.BigDecimal.valueOf(n.longValue());
    }
    throw new IllegalArgumentException(
            "Unsupported numeric source: " + n.getClass().getName());
}
```

Đây là phương thức minh họa Java 17+ (dùng `instanceof` pattern matching). Nó **chủ động từ chối** `Float`, `Double`, `AtomicInteger` và mọi subtype lạ để tránh suy diễn sai rằng `Number.doubleValue()` bảo đảm thập phân chính xác.

Nếu ứng dụng muốn chấp nhận `double` hữu hạn, có thể đưa ra quy tắc riêng như `BigDecimal.valueOf(d)`, nhưng phải hiểu **giá trị `double` đã được làm tròn trước đó** và phân biệt với `new BigDecimal(d)`. Với dữ liệu đo xấp xỉ, chính sách cho phép làm tròn có thể hợp lý; với giao thức số thập phân chính xác, chỉ chấp nhận các loại rõ ràng như trên sẽ an toàn hơn.

**Thông điệp thiết kế:** đừng kỳ vọng một phương thức `Number` tự quyết định đúng độ chính xác cho mọi hệ thống. Càng cần giữ chính xác, kiểu tham số/kiểu trả về càng nên **cụ thể**.

## 9. `Number` khác autoboxing, unboxing và generic arithmetic

### Boxing không biến `Number` thành primitive

```java
Number a = 42;      // int -> Integer (boxing) -> Number (upcast).
Number b = 1.25;    // double -> Double (boxing) -> Number.
int x = a.intValue();

// int y = a; // Không biên dịch: không unbox trực tiếp một Number bất kỳ.
```

Java hỗ trợ **unboxing** từ các wrapper được ngôn ngữ xác định như `Integer`, `Double`, `Long`, chứ không có quy tắc unboxing từ **mọi subtype `Number`**. Lời gọi `intValue()` là gọi phương thức, không phải tự động chuyển tất cả `Number` thành primitive theo cùng phép toán.

Khi một biến có kiểu `Integer`, biểu thức như `Integer boxed = 3; int v = boxed;` có thể dùng unboxing ngầm. Nếu boxed bằng `null`, phép unboxing phát sinh `NullPointerException`. Tương tự, `Number n = null; n.intValue()` gây NPE vì gọi phương thức trên tham chiếu null.

### Generic `T extends Number` không tự cung cấp toán tử `+`

```java
static double sumAsDouble(
        java.util.List<? extends Number> numbers) {
    double result = 0.0;
    for (Number n : numbers) {
        result += n.doubleValue();
    }
    return result;
}
```

Phương thức này có thể dùng cho `List<Integer>`, `List<Long>`, `List<BigDecimal>`..., nhưng kết quả **là tổng xấp xỉ binary64**, không bảo đảm thập phân chính xác hoặc miễn overflow. `List<? extends Number>` chỉ mô tả ràng buộc kiểu; nó không làm Java cho phép `n1 + n2` trên các đối tượng `Number`.

Với thư viện tính tiền, tổng số nguyên lớn hoặc phân số hữu tỉ, thường nên nhận `List<BigDecimal>`, `List<BigInteger>`, hoặc một kiểu giá trị riêng có hợp đồng rõ. Đừng sử dụng generic `Number` rồi ép tất cả sang `double` nếu yêu cầu loại trừ mất dữ liệu.

## 10. Equality, thứ tự và tính biến đổi không được `Number` chuẩn hóa

Hai đối tượng có giá trị toán học giống nhau không nhất thiết so sánh bằng nhau khi gọi `equals`:

```java
System.out.println(
        Integer.valueOf(1).equals(Long.valueOf(1L))); // false.

System.out.println(
        new java.math.BigDecimal("1.0")
            .equals(new java.math.BigDecimal("1.00"))); // false.
```

`Integer.equals` yêu cầu đối tượng cùng kiểu `Integer` và cùng giá trị; `Long.equals` có quy tắc kiểu tương ứng. Với `BigDecimal`, `equals` còn xét **scale**, nên 1.0 khác 1.00; trong khi `compareTo` cho thấy giá trị toán học bằng nhau:

```java
java.math.BigDecimal x = new java.math.BigDecimal("1.0");
java.math.BigDecimal y = new java.math.BigDecimal("1.00");
System.out.println(x.compareTo(y) == 0); // true.
```

`Number` **không đặt một quy tắc `equals`/`hashCode`/`compareTo` chung giữa mọi subtype**. Không nên gọi `new HashSet<Number>()` rồi kỳ vọng nó tự gộp `Integer(1)`, `Long(1L)` và `BigDecimal("1.0")` thành một phần tử.

Một số `Number` còn **mutable**:

```java
java.util.concurrent.atomic.AtomicInteger counter =
        new java.util.concurrent.atomic.AtomicInteger(3);
Number snapshotSource = counter;
counter.incrementAndGet();
System.out.println(snapshotSource.intValue()); // 4.
```

`snapshotSource` tham chiếu **cùng đối tượng** `AtomicInteger` đã đổi giá trị, không phải ảnh chụp `3`. Nếu cần giá trị snapshot bất biến, hãy đọc primitive tại thời điểm có chủ đích (`int snapshot = counter.intValue()`) rồi lưu riêng. `intValue` của `AtomicInteger` trả giá trị quan sát tại lời gọi; nếu nhiều luồng cập nhật, các lần gọi liên tiếp không nhất thiết cùng một số.

## 11. Chương trình Java 17+ độc lập

Tạo tệp `NumberContractDemo.java`:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

public class NumberContractDemo {
    static class CounterNumber extends Number {
        private final long value;

        CounterNumber(long value) {
            this.value = value;
        }

        @Override public int intValue() {
            return (int) value;
        }
        @Override public long longValue() {
            return value;
        }
        @Override public float floatValue() {
            return value;
        }
        @Override public double doubleValue() {
            return value;
        }
    }

    public static void main(String[] args) {
        List<Number> list = List.of(
                Integer.valueOf(42),
                Long.valueOf(4_294_967_297L),
                Double.valueOf(3.75),
                new BigDecimal("42.50"),
                new BigInteger("4294967296"),
                new AtomicInteger(7));

        for (Number n : list) {
            System.out.println(n.getClass().getSimpleName()
                    + ": int=" + n.intValue()
                    + ", long=" + n.longValue());
        }

        System.out.println("Default byteValue: "
                + new CounterNumber(258L).byteValue());

        System.out.println("Decimal intValue: "
                + new BigDecimal("12.75").intValue());
        try {
            new BigDecimal("12.75").intValueExact();
        } catch (ArithmeticException ex) {
            System.out.println("Decimal intValueExact: rejected");
        }

        System.out.println("BigInteger intValue: "
                + new BigInteger("2147483648").intValue());
        try {
            new BigInteger("2147483648").intValueExact();
        } catch (ArithmeticException ex) {
            System.out.println("BigInteger intValueExact: rejected");
        }

        System.out.println("NaN intValue: "
                + Double.valueOf(Double.NaN).intValue());
        System.out.println("Infinity intValue: "
                + Double.valueOf(Double.POSITIVE_INFINITY).intValue());

        System.out.println("Cross-wrapper equals: "
                + Integer.valueOf(1).equals(Long.valueOf(1L)));
        System.out.println("Decimal equals by scale: "
                + new BigDecimal("1.0").equals(new BigDecimal("1.00")));
        System.out.println("Decimal compareTo numerically: "
                + (new BigDecimal("1.0")
                    .compareTo(new BigDecimal("1.00")) == 0));
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 NumberContractDemo.java
java NumberContractDemo
```

Kết quả stdout:

```text
Integer: int=42, long=42
Long: int=1, long=4294967297
Double: int=3, long=3
BigDecimal: int=42, long=42
BigInteger: int=0, long=4294967296
AtomicInteger: int=7, long=7
Default byteValue: 2
Decimal intValue: 12
Decimal intValueExact: rejected
BigInteger intValue: -2147483648
BigInteger intValueExact: rejected
NaN intValue: 0
Infinity intValue: 2147483647
Cross-wrapper equals: false
Decimal equals by scale: false
Decimal compareTo numerically: true
```

Chương trình kiểm chứng bốn ý chính: cùng kiểu tham chiếu `Number` có thể chứa nhiều kiểu số; chuyển đổi sang `int`/`long` có thể làm mất giá trị; hai phương thức `byteValue/shortValue` có mặc định; chuyển đổi *exact* và bình đẳng `equals` là **hợp đồng của kiểu cụ thể**, không phải của mọi `Number`.

## 12. Cách chọn kiểu và cách thiết kế API

| Nhu cầu | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Hiển thị thống kê xấp xỉ từ nhiều lớp số, sai số được chấp nhận | `Number` rồi `doubleValue()` **có chủ đích** | Dễ viết API đa hình; phải kiểm tra finite/độ chính xác |
| API yêu cầu số nguyên đúng miền `int` | `int`/`Integer` với kiểm tra đầu vào, hoặc `intValueExact` trên loại hỗ trợ | Không tin `Number.intValue` để phát hiện overflow |
| Số nguyên không giới hạn trong 64 bit | `BigInteger` | Tránh mất bit bởi `longValue/intValue` |
| Tài chính hoặc phép toán decimal chính xác | `BigDecimal` | Giữ cách biểu diễn thập phân và kiểm soát rounding |
| Chỉ lưu primitive 32/64 bit, cần hiệu suất/memory rõ | `int`/`long`/`double` | Tránh boxing không cần thiết trong vòng lặp nóng |
| Giá trị số có thể thay đổi giữa các luồng | `AtomicInteger`/`AtomicLong` nếu đúng nhu cầu đồng thời | Có API atomic; đọc `Number` chỉ là lấy một giá trị |
| Danh sách dị loại để trình bày/ghi log | `List<Number>` | Dùng chung kiểu tham chiếu; không suy ra arithmetic/equality |
| Thao tác cộng/trừ trên nhiều kiểu mà **phải** giữ chính xác | Thiết kế kiểu số riêng hoặc chọn kiểu chuẩn hóa phù hợp | `Number` không mô tả phép toán algebra hay quy tắc rounding |

### Hợp đồng API nên ghi rõ những gì?

Nếu định nghĩa phương thức nhận `Number`, nên trả lời:

1. Có cho phép **mọi** subtype `Number` không, hay chỉ `Integer`/`Long`/`BigDecimal`?
2. Có chấp nhận NaN, vô cực, số âm, phần thập phân hay không?
3. Có thể mất độ chính xác, cắt phần lẻ, thay đổi dấu hoặc tràn không?
4. Giá trị có thể bị thay đổi giữa hai lần đọc từ một `Number` mutable không?
5. Kết quả trả về mang kiểu nào; lỗi nhập liệu và overflow được báo thế nào?
6. Nếu chuyển sang `double`, sai số và miền độ lớn cho phép là bao nhiêu?
7. Có cần quy tắc `equals`/`compareTo` liên kiểu hay chỉ xử lý riêng từng subtype?

Trong API công khai, **chấp nhận `Number` vì linh hoạt** phải đi kèm **tài liệu về độ chính xác và conversion**. Nếu chỉ có một kiểu số hợp lệ theo nghiệp vụ, nhận đúng kiểu đó thường đơn giản và an toàn hơn.

## 13. Những lỗi hay gặp

| Nhầm lẫn | Điều xảy ra | Cách xử lý |
| --- | --- | --- |
| Tưởng `Number` là interface | Nó là **abstract class**, có phương thức đã triển khai | Dùng `extends Number` khi tạo subtype |
| Cố tạo `new Number()` | Lỗi biên dịch | Tạo đối tượng lớp con cụ thể |
| Tưởng đủ triển khai `intValue()` | `longValue`, `floatValue`, `doubleValue` còn abstract | Triển khai cả bốn nếu không được kế thừa từ lớp cha |
| Tin `n.intValue()` luôn kiểm tra miền | `Long(4294967297)` trả 1 | Dùng checked/exact conversion nếu bắt buộc |
| Tin `n.doubleValue()` bảo toàn mọi số nguyên | `2^53+1` không giữ chính xác trong binary64 | Giữ `long`/`BigInteger` nếu cần |
| Tin `n.byteValue()` tự ném lỗi nếu quá 127 | Mặc định cast từ `intValue` | Dùng exact API phù hợp |
| Tưởng `Number` hỗ trợ `x + y` | Toán tử `+` không được định nghĩa cho hai `Number` | Chọn kiểu số/chiến lược toán học tường minh |
| Dùng `new BigDecimal(n.doubleValue())` để “bảo toàn” dữ liệu | Dữ liệu đã mất trước khi xây `BigDecimal` | Nhận loại hỗ trợ exact và chuyển trực tiếp |
| Xem mọi `Number` là wrapper bất biến | `AtomicInteger` thay đổi được | Chú ý tính mutable và snapshot |
| Tưởng `Number` chuẩn hóa `equals` và `compareTo` | Mỗi subtype có hợp đồng riêng | Tránh equality/hashing liên kiểu chưa thiết kế |
| Tưởng gán `Number n = 2` biến số nguyên thành `double` | Giá trị được boxing thành `Integer` | Phân biệt boxing, upcast và conversion |
| Gọi `n.intValue()` trên `null` | `NullPointerException` | Kiểm tra null tại biên |
| Dùng `Number` cho tiền chính xác nhưng lại cộng qua `doubleValue` | Độ chính xác decimal có thể mất | Dùng `BigDecimal` và chính sách làm tròn |
| Giữ `Number` qua serialization mà không định nghĩa schema | Kiểu cụ thể/precision có thể mơ hồ khi liên hệ với hệ khác | Xác định loại số, format, scale và chính sách chuyển đổi trong giao thức |

## 14. Tự kiểm tra

1. `Number` là class, interface hay abstract class? Vì sao không dùng `new Number()`?
2. Bốn phương thức abstract của `Number` là gì? Hai phương thức nào có triển khai mặc định, và mặc định dùng cách nào?
3. Vì sao `Number n = Long.valueOf(4_294_967_297L); n.intValue()` trả 1 chứ không ném exception?
4. Một `BigDecimal("12.75")` cho `intValue()` bằng bao nhiêu? `intValueExact()` có hành vi gì?
5. Vì sao `BigInteger("2147483648").intValue()` có thể **âm** dù số gốc dương?
6. `Number n = Integer.valueOf(3)` có thể dùng `int x = n;` không? Tại sao `int x = n.intValue();` hợp lệ?
7. Tại sao `List<? extends Number>` không làm phép cộng `+` giữa hai phần tử trở thành hợp lệ?
8. Vì sao chuyển `BigInteger` lớn qua `doubleValue()` rồi tạo `BigDecimal` không bảo toàn mọi chữ số?
9. Khi nào `AtomicInteger` thuộc `Number` có thể cho hai kết quả `intValue()` khác nhau liên tiếp?
10. Vì sao `Integer.valueOf(1).equals(Long.valueOf(1L))` là false? `BigDecimal("1.0")` và `BigDecimal("1.00")` có giống nhau theo `equals` và `compareTo` không?
11. Nếu API chỉ chấp nhận số nguyên vừa `int`, nên thay `Number.intValue()` không kiểm tra bằng hợp đồng nào?
12. Với một loại đơn vị đo mới, việc `extends Number` có tự tạo toán tử arithmetic hoặc comparator không?

## 15. Tài liệu chính thức

- [`java.lang.Number` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Number.html): mô tả lớp abstract, bốn phương thức abstract, hai phương thức có mặc định và cảnh báo mất thông tin khi conversion.
- [`java.math.BigDecimal` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html): hợp đồng chuyển kiểu và các phương thức `intValueExact`, `longValueExact`, `toBigIntegerExact`.
- [`java.math.BigInteger` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigInteger.html): số nguyên lớn, `intValueExact`/`longValueExact` và chuyển đổi cắt bit thấp.
- [Java Language Specification `5.1.2 và `5.1.3](https://docs.oracle.com/javase/specs/jls/se17/html/jls-5.html): widening/narrowing primitive conversions.
- [`java.util.concurrent.atomic.AtomicInteger` — Java SE 17 API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/atomic/AtomicInteger.html): lớp số nguyên cập nhật atomic có kế thừa `Number`.

**Kết luận:** `Number` là **kiểu cha trừu tượng cho các đối tượng số có khả năng chuyển sang sáu primitive**. Nó cho đa hình chuyển đổi, **không cam kết** arithmetic chung, độ chính xác, bình đẳng liên kiểu hoặc tính bất biến. `intValue`/`longValue`/`floatValue`/`doubleValue` có thể làm mất thông tin; hai phương thức `byteValue`/`shortValue` có mặc định thông qua `intValue`. Khi cần miền số, phần lẻ hoặc độ chính xác được bảo đảm, hãy chọn **kiểu cụ thể và checked/exact conversion** thay vì coi mọi `Number` như một giá trị số có thể hoán đổi hoàn toàn.