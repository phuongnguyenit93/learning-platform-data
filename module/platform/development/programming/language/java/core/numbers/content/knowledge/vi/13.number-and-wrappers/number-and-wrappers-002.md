# `Byte`, `Short`, `Integer`, `Long`, `Float` và `Double` trong Java

## 1. Sáu lớp wrapper là gì?

Java có sáu kiểu nguyên thủy biểu diễn số được nhắc đến ở đây: `byte`, `short`, `int`, `long`, `float`, `double`. Mỗi kiểu có một **lớp bao (wrapper class)** tương ứng trong gói `java.lang`:

| Kiểu nguyên thủy | Lớp wrapper | Loại số | Độ rộng |
| --- | --- | --- | ---: |
| `byte` | `Byte` | Số nguyên có dấu | 8 bit |
| `short` | `Short` | Số nguyên có dấu | 16 bit |
| `int` | `Integer` | Số nguyên có dấu | 32 bit |
| `long` | `Long` | Số nguyên có dấu | 64 bit |
| `float` | `Float` | Dấu phẩy động nhị phân IEEE 754 | 32 bit |
| `double` | `Double` | Dấu phẩy động nhị phân IEEE 754 | 64 bit |

Các wrapper này là những **đối tượng bất biến (immutable)**: sau khi tạo, giá trị bên trong không thay đổi. Chúng đều là lớp `final`, đều kế thừa lớp trừu tượng `java.lang.Number`, và hỗ trợ so sánh cùng kiểu qua `Comparable<T>`.

Ví dụ:

```java
byte primitiveByte = 7;
Byte wrappedByte = Byte.valueOf(primitiveByte);

int primitiveInt = 42;
Integer wrappedInt = Integer.valueOf(primitiveInt);

double primitiveDouble = 0.5;
Double wrappedDouble = Double.valueOf(primitiveDouble);
```

Sự khác nhau quan trọng:

- **Primitive** (`int`, `double`...) trực tiếp biểu diễn giá trị kiểu nguyên thủy; không có phương thức instance và không thể là `null`.
- **Wrapper** (`Integer`, `Double`...) là một tham chiếu tới đối tượng chứa giá trị; có phương thức hữu ích như `compareTo`, `intValue`, `toString`, `equals`, có thể là `null`, và dùng được ở nơi cần đối tượng hoặc kiểu tham số của generic.
- `Byte`, `Short`, `Integer`, `Long` biểu diễn số nguyên theo độ rộng cố định; `Float`, `Double` biểu diễn số dấu phẩy động hữu hạn hoặc các giá trị đặc biệt như `NaN`, vô cực.

Bài này tập trung vào sáu wrapper số kể trên. `Boolean`, `Character` cũng là wrapper của primitive nhưng không thuộc nhóm số kế thừa `Number`. `BigInteger` và `BigDecimal` là những kiểu số đối tượng khác, không tương ứng trực tiếp với một primitive.

## 2. Miền giá trị và các hằng số quan trọng

### 2.1. Các wrapper số nguyên

| Wrapper | Primitive | `MIN_VALUE` | `MAX_VALUE` |
| --- | --- | ---: | ---: |
| `Byte` | `byte` | `-128` | `127` |
| `Short` | `short` | `-32768` | `32767` |
| `Integer` | `int` | `-2147483648` | `2147483647` |
| `Long` | `long` | `-9223372036854775808` | `9223372036854775807` |

Mỗi wrapper số nguyên có các hằng số `SIZE` (số bit), `BYTES` (số byte) và `TYPE` (đối tượng `Class` đại diện primitive tương ứng).

```java
System.out.println(Integer.SIZE);  // 32
System.out.println(Long.BYTES);    // 8
System.out.println(Integer.TYPE);  // int
```

Đây là các dòng **minh họa trong một phương thức**, không phải một chương trình đầy đủ. Có thể dùng `Integer.MIN_VALUE` và `Integer.MAX_VALUE` khi kiểm tra miền trước khi chuyển từ `long` xuống `int`.

### 2.2. `Float` và `Double`: đừng hiểu sai `MIN_VALUE`

| Wrapper | Bit | `MAX_VALUE` | `MIN_VALUE` |
| --- | ---: | --- | --- |
| `Float` | 32 | Khoảng `3.4028235E38` | Khoảng `1.4E-45`, **dương** |
| `Double` | 64 | Khoảng `1.7976931348623157E308` | Khoảng `4.9E-324`, **dương** |

Với `Float`/`Double`, `MIN_VALUE` là **số dương khác 0 nhỏ nhất có thể biểu diễn** (số dưới chuẩn/subnormal), **không** phải số âm lớn nhất về độ lớn. Giá trị âm hữu hạn thấp nhất là `-Float.MAX_VALUE` hoặc `-Double.MAX_VALUE`.

Các hằng số hữu ích khác:

- `Float.MIN_NORMAL`, `Double.MIN_NORMAL`: số dương chuẩn hóa nhỏ nhất.
- `Float.POSITIVE_INFINITY`, `Double.POSITIVE_INFINITY` và các hằng số `NEGATIVE_INFINITY`: vô cực dương/âm.
- `Float.NaN`, `Double.NaN`: giá trị “không phải một số”.
- `Float.SIZE == 32`, `Double.SIZE == 64`; `Float.BYTES == 4`, `Double.BYTES == 8`.

Hai kiểu dấu phẩy động có thể mất độ chính xác khi biểu diễn phân số thập phân hoặc số nguyên lớn. `Float` có khoảng 24 bit chính xác phần trị, `Double` có khoảng 53 bit; điều này khác với số bit tổng cộng của kiểu. Vì vậy, không chọn `Double` chỉ vì nó có thể chứa số rất lớn rồi mặc định mọi phép tính decimal đều chính xác tuyệt đối.

## 3. Mối quan hệ với `java.lang.Number`

`Number` là một lớp trừu tượng để biểu diễn “một giá trị số” dưới dạng đối tượng. Cả sáu wrapper đều kế thừa nó. Các phương thức chuyển giá trị phổ biến của `Number` gồm:

| Phương thức | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `byteValue()` | `byte` | Lấy giá trị theo kiểu `byte` |
| `shortValue()` | `short` | Lấy giá trị theo kiểu `short` |
| `intValue()` | `int` | Lấy giá trị theo kiểu `int` |
| `longValue()` | `long` | Lấy giá trị theo kiểu `long` |
| `floatValue()` | `float` | Lấy giá trị theo kiểu `float` |
| `doubleValue()` | `double` | Lấy giá trị theo kiểu `double` |

Ví dụ đa hình:

```java
Number[] values = {
    Byte.valueOf((byte) 7),
    Short.valueOf((short) 300),
    Integer.valueOf(42),
    Long.valueOf(9_000_000_000L),
    Float.valueOf(1.25f),
    Double.valueOf(0.5)
};

for (Number value : values) {
    System.out.println(value.getClass().getSimpleName()
            + ": " + value.doubleValue());
}
```

Nhờ `Number`, mã có thể đọc một **dạng giá trị số chung** từ các loại đối tượng khác nhau. Tuy nhiên, các phương thức `...Value()` không bảo đảm chuyển đổi chính xác:

```java
Number n = Integer.valueOf(257);
byte narrowed = n.byteValue(); // 1: chỉ giữ 8 bit thấp
```

Một `Long` lớn chuyển sang `double` có thể mất các bit phần trị; một `Double` có phần lẻ chuyển sang `int` bị cắt về 0 hoặc bão hòa tại biên; `Float.NaN` chuyển sang kiểu nguyên cho 0 theo quy tắc Java.

**`Number` không định nghĩa `parse`, `valueOf`, `compareTo` hoặc `add` chung cho mọi subtype.** Những phương thức `parseXxx`, `valueOf`, `compare` là API riêng của các wrapper cụ thể. Việc một biến được khai báo `Number` không biến Java thành ngôn ngữ có toán tử số học đa hình trên đối tượng:

```java
Number n = Integer.valueOf(12);
int a = n.intValue();     // hợp lệ
// int b = n + 1;         // không biên dịch: Number không tự unbox thành int
```

Muốn giữ nguyên kiểu cụ thể, hãy dùng `Integer`, `Long`, `Double` hoặc API/generic được thiết kế phù hợp, thay vì giả định `Number` tự động chuyển thành mọi primitive.

## 4. Tạo wrapper: `valueOf`, autoboxing và constructor

Cách thường dùng để tạo wrapper là **`valueOf`** hoặc để Java **autoboxing** (tự đóng hộp):

```java
Byte b = Byte.valueOf((byte) 10);
Short s = Short.valueOf((short) 1000);
Integer i = Integer.valueOf(42);
Long l = Long.valueOf(9_000_000_000L);
Float f = Float.valueOf(1.25f);
Double d = Double.valueOf(0.5);

Integer autoInteger = 42; // compiler chèn thao tác boxing
Double autoDouble = 0.5;  // autoboxing từ double
```

Các wrapper là immutable; muốn có giá trị mới, gán một wrapper khác:

```java
Integer count = 5;
count++; // unbox -> cộng 1 theo int -> box, rồi gán lại biến count
```

Biến `count` đổi đối tượng mà nó tham chiếu; **đối tượng `Integer` ban đầu không bị sửa**. Do autoboxing tạo thao tác đối tượng, với vòng lặp và phép tính số học tần suất lớn thường ưu tiên primitive nếu không cần `null`/generic.

Không cần gọi `new Integer(...)`, `new Double(...)` và các constructor wrapper cổ điển. Các constructor kiểu này đã bị deprecated, nên ưu tiên `valueOf`/autoboxing để diễn đạt ý định rõ và cho phép JVM tái sử dụng đối tượng khi thích hợp.

### Cảnh báo khi dùng `==` với wrapper

`==` giữa **hai tham chiếu wrapper** kiểm tra chúng có chỉ vào cùng đối tượng không. `equals` kiểm tra giá trị theo hợp đồng của từng lớp. `Integer.valueOf` bắt buộc cache ít nhất các giá trị `-128` đến `127`, nhưng mã không nên phụ thuộc vào identity để so sánh số:

```java
Integer x = Integer.valueOf(100);
Integer y = Integer.valueOf(100);
System.out.println(x == y);      // true trong phạm vi cache được bảo đảm

Integer p = Integer.valueOf(200);
Integer q = Integer.valueOf(200);
System.out.println(p.equals(q));  // true
```

Kết quả `p == q` **không được dùng làm quy tắc** vì phạm vi cache ngoài mức bảo đảm có thể thay đổi theo môi trường. Khi một bên là primitive và một bên wrapper, toán hạng wrapper có thể bị *unbox* để thực hiện so sánh số:

```java
Integer boxed = 42;
int primitive = 42;
System.out.println(boxed == primitive); // true: so sánh giá trị int
```

Vì các biểu thức nhìn giống nhau có thể mang nghĩa reference hoặc numeric, nên trong mã kiểm tra giá trị wrapper cùng kiểu hãy ưu tiên `equals` (có xử lý `null`) hoặc chuyển sang primitive một cách tường minh khi cần.

## 5. Autoboxing, unboxing và `null`

**Autoboxing** là chuyển primitive thành wrapper; **unboxing** là chuyển wrapper thành primitive:

```java
Integer boxed = 12; // autoboxing: int -> Integer
int raw = boxed;     // unboxing: Integer -> int
```

Unboxing một tham chiếu `null` ném `NullPointerException`:

```java
Integer missing = null;
// int n = missing; // NullPointerException khi chạy
```

Bẫy này còn xuất hiện trong phép tính, so sánh với primitive hoặc toán tử `++`:

```java
Integer maybeCount = null;
// if (maybeCount > 0) { } // NullPointerException
// maybeCount++;            // NullPointerException
```

Nếu `null` mang nghĩa “chưa biết”, phải kiểm tra trước:

```java
Integer count = null;
int safeCount = count == null ? 0 : count;
```

Chọn giá trị mặc định 0 chỉ khi nghiệp vụ cho phép; nhiều ứng dụng phải phân biệt số 0 với dữ liệu thiếu.

### Wrapper trong collection và generic

Java generic cần kiểu tham chiếu, vì vậy:

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> scores = new ArrayList<>();
scores.add(10);                // 10 được box thành Integer
scores.add(20);
int first = scores.get(0);    // unboxing
```

`List<int>` không hợp lệ trong Java 17; dùng `List<Integer>`. Tương tự, có thể tạo `List<Long>`, `Map<String, Double>` hoặc `List<Number>`.

Lưu ý `List<Integer>` không phải subtype của `List<Number>`, dù `Integer` kế thừa `Number`: generic Java mặc định là **invariant**. Để đọc danh sách nhiều kiểu số, chữ ký `List<? extends Number>` có thể phù hợp, nhưng thao tác ghi vào danh sách bị giới hạn bởi wildcard. Đây là vấn đề kiểu generic, không phải khác biệt giá trị của wrapper.

Collection có thể chứa wrapper `null` khi cấu trúc dữ liệu cho phép, nên đọc từ `List<Integer>` rồi unbox vẫn có nguy cơ `NullPointerException`.

## 6. Phân tích chuỗi số: `parseXxx`, `valueOf(String)` và radix

Mỗi wrapper có các API phân tích chuỗi tương ứng:

| Wrapper | Trả về primitive | Trả về wrapper |
| --- | --- | --- |
| `Byte` | `Byte.parseByte(text)` | `Byte.valueOf(text)` |
| `Short` | `Short.parseShort(text)` | `Short.valueOf(text)` |
| `Integer` | `Integer.parseInt(text)` | `Integer.valueOf(text)` |
| `Long` | `Long.parseLong(text)` | `Long.valueOf(text)` |
| `Float` | `Float.parseFloat(text)` | `Float.valueOf(text)` |
| `Double` | `Double.parseDouble(text)` | `Double.valueOf(text)` |

Ví dụ:

```java
int a = Integer.parseInt("42");       // primitive int
Integer b = Integer.valueOf("42");    // Integer
long c = Long.parseLong("9000000000");
double d = Double.parseDouble("0.5");
```

**`parseXxx` không tạo wrapper ở kết quả** (dù JIT/runtime có thể có tối ưu nội bộ), còn `valueOf(String)` trả đối tượng wrapper. Cả hai đều có thể ném `NumberFormatException` khi chuỗi không hợp lệ hoặc vượt miền của kiểu.

### Hệ cơ số cho wrapper nguyên

Bốn wrapper nguyên có overload nhận **radix**, thông thường từ 2 đến 36:

```java
int hex = Integer.parseInt("FF", 16); // 255
int binary = Integer.parseInt("1010", 2); // 10
long base36 = Long.parseLong("Z", 36); // 35
```

Nếu chuỗi gồm tiền tố như `"0xFF"` hoặc `"0b1010"`, đừng mặc định `parseInt(text, radix)` nhận nguyên xi tiền tố:

```java
int hex = Integer.parseInt("FF", 16); // hợp lệ
int prefixed = Integer.decode("0xFF"); // 255
// Integer.parseInt("0xFF", 16); // NumberFormatException
```

`Integer.decode`/`Long.decode`/`Byte.decode`/`Short.decode` hỗ trợ quy tắc tiền tố thập lục phân và bát phân của các API này, nhưng không phải bộ parse tổng quát cho mọi dạng literal Java. Một số dấu phân tách hợp lệ trong mã nguồn, như dấu gạch dưới của `1_000`, **không tự được chấp nhận** khi parse chuỗi:

```java
int literal = 1_000;            // hợp lệ trong mã Java
// Integer.parseInt("1_000");  // NumberFormatException
```

`Integer.parseInt(" 42 ")` cũng không tự bỏ khoảng trắng; chỉ `trim()`/`strip()` khi chính sách đầu vào cho phép. Với các định dạng theo locale (ví dụ dấu phẩy thập phân), `parseDouble` không thay thế một parser phù hợp locale.

### Chuỗi số thực và giá trị đặc biệt

`Float.parseFloat` và `Double.parseDouble` nhận cú pháp thập phân hoặc dạng dấu phẩy động phù hợp API Java; chúng cũng có thể phân tích chuỗi `"NaN"`, `"Infinity"` và `"-Infinity"`.

```java
double half = Double.parseDouble("0.5");           // 0.5
double infinity = Double.parseDouble("Infinity");  // dương vô cực
boolean infinite = Double.isInfinite(infinity);    // true
```

Đầu vào là chuỗi đúng cú pháp chưa chắc đã mang giá trị hữu hạn: phải kiểm tra `Float.isFinite` / `Double.isFinite` nếu nghiệp vụ yêu cầu hữu hạn. Không dùng `Double.parseDouble` để lưu tiền thập phân cần chính xác tuyệt đối; cân nhắc `BigDecimal` từ chuỗi đầu vào.

## 7. Chuyển ngược sang chuỗi và các tiện ích cho số nguyên

Các wrapper có `toString`, `toString(primitive)` và `valueOf`; với `Integer`/`Long`, có thêm hỗ trợ nhị phân, thập lục phân, không dấu:

```java
String decimal = Integer.toString(255);       // "255"
String hex = Integer.toHexString(255);        // "ff"
String binary = Integer.toBinaryString(10);   // "1010"
String base16 = Integer.toString(255, 16);    // "ff"
String unsigned = Integer.toUnsignedString(-1); // "4294967295"
```

`Integer.toUnsignedString(-1)` và `Long.toUnsignedString(-1L)` xem cùng mẫu bit 32/64 bit theo **cách diễn giải không dấu**. Chúng không làm Java có primitive `uint`/`ulong`.

Ví dụ đọc một giá trị âm theo mẫu bit không dấu:

```java
int mask = -1;
System.out.println(Integer.toUnsignedString(mask));  // 4294967295
System.out.println(Long.toUnsignedString(-1L));       // 18446744073709551615
```

Với `byte` và `short`, có thể mở rộng không dấu:

```java
int uByte = Byte.toUnsignedInt((byte) -1);   // 255
int uShort = Short.toUnsignedInt((short) -1); // 65535
```

`Integer` và `Long` còn cung cấp phương thức tiện ích như `bitCount`, `highestOneBit`, `lowestOneBit`, `numberOfLeadingZeros`, `numberOfTrailingZeros`, `rotateLeft`, `rotateRight` và so sánh/chia không dấu (`compareUnsigned`, `divideUnsigned`...). Các phương thức thao tác trên **mẫu bit có độ rộng cố định**. Không có nghĩa `Integer`/`Long` tự động trở thành số nguyên không dấu khi gọi chúng.

Một số toán tử như `+`, `-`, `&`, `<<` áp dụng lên primitive sau khi unbox, không phải phương thức instance của wrapper.

## 8. So sánh, `equals`, `compareTo` và các giá trị đặc biệt

### 8.1. Wrapper nguyên

Với `Byte`, `Short`, `Integer`, `Long`, `equals` kiểm tra cùng **lớp wrapper** và cùng giá trị:

```java
Integer a = Integer.valueOf(10);
Integer b = Integer.valueOf(10);
Long c = Long.valueOf(10L);

System.out.println(a.equals(b)); // true
System.out.println(a.equals(c)); // false: khác kiểu wrapper
```

`Integer.compare(x, y)`, `Long.compare(x, y)` hoặc `compareTo` cho thứ tự theo số nguyên có dấu. `Integer.compareUnsigned`/`Long.compareUnsigned` dùng khi cùng mẫu bit phải được đọc như số không dấu.

```java
System.out.println(Integer.compare(-1, 1));        // -1
System.out.println(Integer.compareUnsigned(-1, 1)); // 1
```

Không viết `a - b` làm `Comparator` cho `Integer` vì hiệu có thể overflow, dẫn đến sai thứ tự. Dùng `Integer.compare(a, b)` hoặc `Comparator.comparingInt(...)` tùy tình huống.

### 8.2. `Float` và `Double`: `NaN`, dấu của 0 và thứ tự

Đây là sự khác biệt đáng nhớ giữa toán tử so sánh primitive và hợp đồng wrapper:

```java
double nan = Double.NaN;

System.out.println(nan == nan); // false
System.out.println(
        Double.valueOf(nan).equals(Double.valueOf(nan))); // true

System.out.println(+0.0 == -0.0); // true
System.out.println(
        Double.valueOf(+0.0).equals(Double.valueOf(-0.0))); // false
```

`Double.equals` coi mọi giá trị `NaN` là bằng nhau theo hợp đồng wrapper, nhưng phân biệt `+0.0` với `-0.0`. `Float.equals` có đặc điểm tương ứng. Điều này giúp `equals` và `hashCode` của wrapper có hành vi nhất quán, kể cả trong collection.

`Double.compare(a, b)` và `Float.compare(a, b)` định nghĩa thứ tự phục vụ sorting: `-0.0` thấp hơn `+0.0`, và `NaN` được sắp cao hơn mọi giá trị số, kể cả vô cực dương.

```java
System.out.println(Double.compare(-0.0, +0.0)); // -1
System.out.println(
        Double.compare(Double.NaN, Double.POSITIVE_INFINITY)); // 1
```

Không dùng `Double.compare` để kết luận hai giá trị gần bằng nhau về mặt tính toán. Nếu bài toán cần dung sai, phải đưa ra chính sách so sánh sai số riêng; quan hệ gần bằng có thể **không bắc cầu**, nên không thích hợp làm hợp đồng `equals`/`hashCode` hoặc `Comparator` sắp xếp.

### 8.3. So sánh khác wrapper type

`Integer.valueOf(10).equals(Long.valueOf(10L))` là `false`, dù hai số nguyên biểu diễn cùng giá trị toán học. Nếu cần so sánh hai giá trị kiểu `Number` khác loại, phải xác định quy tắc chuyển đổi trước:

- Với các số nguyên có miền phù hợp, so sánh trên cùng kiểu nguyên rộng hơn có thể hợp lý.
- Chuyển một `long` rất lớn sang `double` có thể **mất chữ số**, khiến hai giá trị khác nhau trở thành cùng một `double`.
- Với số decimal yêu cầu chính xác, phải dùng biểu diễn decimal phù hợp từ nguồn gốc, không cast bừa mọi `Number` sang `double`.

Không có một phương thức `Number.equalsNumericValue` dùng chung cho tất cả subtype và mọi miền giá trị.

## 9. Chuyển đổi qua `xxxValue()` có thể làm mất giá trị

Các wrapper cung cấp phương thức lấy giá trị ở nhiều kiểu nguyên thủy. Chúng thuận tiện nhưng thường có quy tắc giống các phép ép kiểu Java:

```java
Integer n = Integer.valueOf(257);
byte small = n.byteValue(); // 1

Double d = Double.valueOf(-2.9);
int truncated = d.intValue(); // -2

Long large = Long.valueOf(9_007_199_254_740_993L);
double approximate = large.doubleValue();
// approximate mang giá trị 9_007_199_254_740_992
```

Cần phân biệt:

- **Giữ nguyên giá trị:** `Integer.intValue()`, `Long.longValue()` đối với chính kiểu tương ứng, hoặc chuyển integer nhỏ sang kiểu lớn đủ miền.
- **Thu hẹp số nguyên:** `long` → `int`, `int` → `short`/`byte` có thể bỏ các bit cao; thao tác wrapper không tự báo overflow.
- **Thực sang nguyên:** `Double.intValue()`, `Float.longValue()` cắt phần lẻ về 0 khi hữu hạn và trong miền; NaN và giá trị ngoài miền có kết quả đặc biệt theo quy tắc Java.
- **Nguyên sang thực:** `Long.doubleValue()` và `Integer.floatValue()` có thể làm tròn phần bit thấp.

Nếu muốn kiểm tra `long` có vừa miền `int` hay không, dùng `Math.toIntExact(longValue)` thay vì `Integer.valueOf((int) longValue)`:

```java
long quantity = 3_000_000_000L;

// int wrong = (int) quantity; // giá trị âm vì tràn miền int
// int checked = Math.toIntExact(quantity); // ném ArithmeticException
```

Với `BigInteger`, `BigDecimal`, các phương thức `intValueExact()`/`longValueExact()` áp dụng hợp đồng khác để kiểm tra mất thông tin. Sáu primitive wrapper của bài này **không phải** các kiểu decimal/số nguyên độ dài tùy ý.

## 10. Ví dụ Java 17 hoàn chỉnh

Tạo tệp `NumberWrappersDemo.java`:

```java
public class NumberWrappersDemo {
    public static void main(String[] args) {
        Number[] numbers = {
                Byte.valueOf((byte) 7),
                Short.valueOf((short) 300),
                Integer.valueOf(42),
                Long.valueOf(9_000_000_000L),
                Float.valueOf(1.25f),
                Double.valueOf(0.5)
        };

        for (Number value : numbers) {
            System.out.println(
                    value.getClass().getSimpleName() + " = " + value);
        }

        System.out.println("parse hex = " + Integer.parseInt("FF", 16));
        System.out.println("unsigned byte = " + Byte.toUnsignedInt((byte) -1));
        System.out.println("unsigned int = " + Integer.toUnsignedString(-1));
        System.out.println("narrowed 257 = "
                + Integer.valueOf(257).byteValue());

        Integer a = Integer.valueOf(200);
        Integer b = Integer.valueOf(200);
        System.out.println("boxed equals = " + a.equals(b));

        System.out.println("primitive NaN == NaN = "
                + (Double.NaN == Double.NaN));
        System.out.println("wrapper NaN equals = "
                + Double.valueOf(Double.NaN)
                        .equals(Double.valueOf(Double.NaN)));

        System.out.println("primitive signed zero = " + (+0.0 == -0.0));
        System.out.println("wrapper signed zero equals = "
                + Double.valueOf(+0.0).equals(Double.valueOf(-0.0)));

        System.out.println("unsigned compare(-1, 1) = "
                + Integer.compareUnsigned(-1, 1));
    }
}
```

Biên dịch/chạy:

```bash
javac NumberWrappersDemo.java
java NumberWrappersDemo
```

Kết quả:

```text
Byte = 7
Short = 300
Integer = 42
Long = 9000000000
Float = 1.25
Double = 0.5
parse hex = 255
unsigned byte = 255
unsigned int = 4294967295
narrowed 257 = 1
boxed equals = true
primitive NaN == NaN = false
wrapper NaN equals = true
primitive signed zero = true
wrapper signed zero equals = false
unsigned compare(-1, 1) = 1
```

Các giá trị đặc biệt và parse trong ví dụ dùng những API có hành vi được quy định bởi Java; `valueOf(200)` chỉ được kiểm tra qua `equals`, nên kết quả không phụ thuộc cache bên ngoài miền bảo đảm.

## 11. Nên chọn wrapper nào?

| Nhu cầu | Lựa chọn |
| --- | --- |
| Số nguyên nhỏ cần đúng miền -128..127 | `Byte` nếu API/generic yêu cầu đối tượng; `byte` nếu không |
| Số nguyên 16 bit có dấu | `Short`/`short` khi giao thức/định dạng cần |
| Số nguyên thông thường, chỉ số, bộ đếm | `Integer`/`int` nếu vừa miền 32 bit |
| Số nguyên lớn hơn miền `int` | `Long`/`long` nếu vừa miền 64 bit |
| Số thực nhị phân với yêu cầu bộ nhớ thấp, chịu sai số lớn hơn | `Float`/`float` |
| Số thực nhị phân thông thường, cần độ chính xác cao hơn `float` | `Double`/`double` |
| Collection, generic, dữ liệu có thể vắng mặt (`null`) | Wrapper tương ứng, với chính sách xử lý `null` rõ ràng |
| Số nguyên vượt miền `long` | `BigInteger` |
| Số decimal đòi hỏi chữ số thập phân chính xác, quy tắc làm tròn rõ | `BigDecimal` tạo từ nguồn decimal thích hợp |

Không phải lúc nào `Byte`/`Short` tiết kiệm bộ nhớ hơn `Integer` khi sử dụng **đối tượng**: một wrapper có overhead của object và tham chiếu, khác với primitive nằm trong mảng nguyên thủy. Khi cần lưu hàng triệu số không nullable, các mảng `byte[]`, `int[]`, `double[]` thường tránh overhead boxing so với `List<Byte>`, `List<Integer>`, `List<Double>`.

`Float`/`Double` không phải lựa chọn an toàn mặc định cho tiền tệ vì các số decimal như `0.1` không được biểu diễn chính xác dưới dạng nhị phân. Nếu đầu vào là decimal, `BigDecimal` từ chuỗi giúp giữ đúng chữ số nguồn; lưu dữ liệu tiền dưới dạng số nguyên của đơn vị nhỏ nhất cũng là chiến lược khả thi trong miền phù hợp.

## 12. Lỗi phổ biến và cách khắc phục

1. **Dùng `==` cho hai wrapper để so sánh giá trị.** Kết quả có thể phụ thuộc cache và identity. Dùng `equals`, `Objects.equals(a, b)` nếu có `null`, hoặc unbox có kiểm soát.
2. **Unboxing `null`.** `Integer missing = null; int n = missing;` ném `NullPointerException`; kiểm tra trường hợp thiếu trước khi tính.
3. **Nghĩ `valueOf` và `parseXxx` cùng kiểu trả về.** `Integer.parseInt` trả `int`, `Integer.valueOf` trả `Integer`.
4. **Nhầm `Float.MIN_VALUE` là giá trị âm nhất.** Đây là số **dương khác 0 nhỏ nhất**; số hữu hạn âm nhỏ nhất là `-Float.MAX_VALUE`.
5. **Chuyển wrapper qua `xxxValue()` rồi cho rằng không mất dữ liệu.** `Integer.valueOf(257).byteValue()` là `1`, `Long.doubleValue()` có thể mất chính xác.
6. **Để Java tự unbox trong các phép so sánh không rõ ràng.** `Integer` so với `int` có thể unbox; nhưng hai `Integer` với `==` là so sánh tham chiếu. Hãy ghi rõ ý nghĩa bạn muốn.
7. **Giả định mọi `Number` đều có phương thức `valueOf`, `parseInt` hay phép cộng đối tượng.** Các API này thuộc wrapper cụ thể; `Number` chỉ cung cấp giao diện trích giá trị dạng primitive.
8. **Phân tích chuỗi khác cú pháp mà không bắt lỗi.** `Integer.parseInt("1_000")` không được hỗ trợ dù `1_000` là literal Java hợp lệ; parse chuỗi có thể ném `NumberFormatException`.
9. **Bỏ qua `NaN` và vô cực.** `Double.valueOf("NaN")` là hợp lệ theo parser, nhưng có thể trái hợp đồng dữ liệu; dùng `isNaN`, `isInfinite`, `isFinite`.
10. **Nhầm hợp đồng `equals` của số thực wrapper với toán tử `==` của primitive.** Wrapper coi NaN bằng NaN theo `equals` và phân biệt dấu 0; primitive thì ngược lại trong hai trường hợp đó.
11. **Dùng trừ hai số trong comparator.** `return a-b` có thể overflow; dùng `Integer.compare(a,b)`, `Long.compare(a,b)` và comparator phù hợp.
12. **Dùng đối tượng wrapper cho vòng lặp số học nóng mà không cần.** Boxing/unboxing có thể tăng allocation hoặc overhead và tạo nguy cơ `null`; dùng primitive và mảng primitive khi bài toán phù hợp.
13. **Đọc số không dấu như số có dấu.** Mẫu bit `0xFFFFFFFF` là `-1` khi đọc `int` signed, nhưng `"4294967295"` khi gọi `Integer.toUnsignedString(-1)`.
14. **Cho rằng `equals` giữa các subtype `Number` so sánh giá trị toán học.** `Integer(10)` và `Long(10)` không bằng nhau theo `equals`; chọn quy tắc ép kiểu chung một cách an toàn theo dữ liệu.

## 13. Bài tập tự kiểm tra

**Câu 1.** Cho hai biến:

```java
Integer a = Integer.valueOf(200);
Integer b = Integer.valueOf(200);
```

Nên dùng `a == b` hay `a.equals(b)` để kiểm tra cùng giá trị số nguyên?

**Đáp án:** `a.equals(b)`. `==` kiểm tra identity của hai tham chiếu wrapper và không bảo đảm đúng cho mọi giá trị.

**Câu 2.** `Float.MIN_VALUE` âm hay dương? Nếu cần số `float` âm hữu hạn nhỏ nhất về thứ tự số học, viết thế nào?

**Đáp án:** `Float.MIN_VALUE` dương, là số dương khác 0 nhỏ nhất; cận âm hữu hạn là `-Float.MAX_VALUE`.

**Câu 3.** Điều gì xảy ra khi chạy:

```java
Integer count = null;
int n = count;
```

**Đáp án:** Ném `NullPointerException` tại bước unboxing.

**Câu 4.** Hai biểu thức `Integer.parseInt("42")` và `Integer.valueOf("42")` trả về kiểu nào?

**Đáp án:** Lần lượt là primitive `int` và wrapper `Integer`.

**Câu 5.** Tại sao `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` là `true`, trong khi `Double.NaN == Double.NaN` là `false`?

**Đáp án:** Wrapper `Double.equals` dùng hợp đồng giá trị đối tượng, coi NaN bằng NaN để có hành vi nhất quán với `hashCode`; toán tử primitive `==` tuân theo quy tắc số học dấu phẩy động, với NaN không bằng bất kỳ số nào, kể cả chính nó.

**Câu 6.** `Byte.toUnsignedInt((byte)-1)` trả gì? Còn `Integer.valueOf(257).byteValue()`?

**Đáp án:** `255` và `1`. Trường hợp đầu diễn giải mẫu 8 bit toàn `1` như không dấu; trường hợp sau thu hẹp `int` 257 xuống 8 bit thấp.

**Câu 7.** `Number n = Long.valueOf(9_007_199_254_740_993L);` rồi gọi `n.doubleValue()` có giữ nguyên giá trị nguyên không?

**Đáp án:** Không. `double` không biểu diễn chính xác số nguyên `2^53 + 1`; giá trị bị làm tròn thành `9_007_199_254_740_992`. Gọi `doubleValue()` không báo lỗi và không giữ thông tin đã mất.

**Câu 8.** Có nên dùng `List<int>` trong Java 17? Vì sao `List<Integer>` có thể chứa `null`?

**Đáp án:** `List<int>` không hợp lệ với Java generic; dùng `List<Integer>` vì generic cần kiểu tham chiếu. `Integer` là reference nên một số collection chấp nhận phần tử `null`, khác với primitive `int`.

**Ghi nhớ:** `Byte`, `Short`, `Integer`, `Long`, `Float`, `Double` là sáu lớp wrapper bất biến của primitive số, cùng kế thừa `Number`. Chúng giúp parse, format, so sánh, thao tác bit và dùng generic/collection. Chọn kiểu theo miền giá trị và độ chính xác; phân biệt primitive với đối tượng, `parseXxx` với `valueOf`, `==` với `equals`, và kiểm tra `null` cũng như dữ liệu mất chính xác khi chuyển đổi.