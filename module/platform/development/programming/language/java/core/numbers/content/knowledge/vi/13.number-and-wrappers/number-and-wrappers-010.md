# Number không cung cấp toán tử cộng chung cho mọi lớp con trong Java

Trong Java, **`java.lang.Number` là lớp cha trừu tượng của nhiều kiểu số dạng đối tượng**, nhưng **không có toán tử cộng `+` áp dụng chung cho hai biến kiểu `Number`**. Đây là khác biệt quan trọng giữa **mối quan hệ kế thừa đối tượng** và **quy tắc toán tử số học của ngôn ngữ**.

Ví dụ, đoạn mã sau **không biên dịch**:

```java
// Ví dụ cố ý SAI để thấy giới hạn của kiểu Number:
Number a = Integer.valueOf(10);
Number b = Double.valueOf(2.5);
// Number total = a + b; // COMPILE ERROR: toán tử + không áp dụng cho Number.
```

Dù ở thời điểm chạy đối tượng trong `a` là `Integer` và đối tượng trong `b` là `Double`, trình biên dịch nhìn thấy **kiểu tĩnh** của hai biểu thức là `Number`. Java không có cơ chế tự gọi “phép cộng ảo” của lớp con chỉ vì chúng cùng kế thừa `Number`.

Ngược lại, mã này hợp lệ:

```java
Integer a = 10;
Double b = 2.5;
double result = a + b; // 12.5, unboxing rồi nâng kiểu số nguyên thủy.
```

Vì `Integer` và `Double` là **các kiểu wrapper cụ thể hỗ trợ unboxing**, trình biên dịch có thể xác định phép cộng của các giá trị nguyên thủy. Đổi tên kiểu khai báo sang `Number` làm thay đổi quy tắc biên dịch, dù đối tượng tại runtime có thể không đổi.

## 1. Lớp `Number` cung cấp những gì?

`Number` nằm trong `java.lang`, không cần import. Nó là một **abstract class** dùng làm lớp cha cho các đối tượng biểu diễn một giá trị số. Những lớp quen thuộc kế thừa `Number` gồm `Byte`, `Short`, `Integer`, `Long`, `Float`, `Double`, `BigInteger`, `BigDecimal` và cả `AtomicInteger`/`AtomicLong`. Danh sách này không đóng: chương trình hoặc thư viện khác cũng có thể khai báo lớp con.

Các phương thức chuyển giá trị quan trọng của `Number` là:

| Phương thức | Kiểu trả về | Ý nghĩa |
| --- | --- | --- |
| `byteValue()` | `byte` | Chuyển giá trị sang kiểu nguyên 8 bit |
| `shortValue()` | `short` | Chuyển giá trị sang kiểu nguyên 16 bit |
| `intValue()` | `int` | Chuyển giá trị sang kiểu nguyên 32 bit |
| `longValue()` | `long` | Chuyển giá trị sang kiểu nguyên 64 bit |
| `floatValue()` | `float` | Chuyển sang dấu phẩy động 32 bit |
| `doubleValue()` | `double` | Chuyển sang dấu phẩy động 64 bit |

Chúng cung cấp **cách đọc giá trị dưới một kiểu nguyên thủy được chọn**, chứ **không định nghĩa một phép cộng số học đa hình**. Trong lớp `Number`, bốn phương thức `intValue`, `longValue`, `floatValue`, `doubleValue` là abstract; `byteValue` và `shortValue` có cài đặt dựa trên chuyển kiểu từ `intValue`.

Cần phân biệt `Number` với `java.text.NumberFormat`, `java.text.DecimalFormat` hoặc một interface nghiệp vụ tên `Numeric`: chúng là các khái niệm khác nhau.

## 2. Vì sao toán tử `+` không tự động áp dụng cho `Number`?

Java định nghĩa `+` dựa trên **kiểu toán hạng được ngôn ngữ hỗ trợ**:

- Nếu hai toán hạng phù hợp cho **phép cộng số nguyên thủy**, Java thực hiện unboxing cần thiết rồi **binary numeric promotion**, kết quả là `int`, `long`, `float` hoặc `double`.
- Nếu một toán hạng là `String` trong phép `+`, Java có thể thực hiện **nối chuỗi** thay vì cộng số.
- `BigInteger`, `BigDecimal` và các lớp số tùy biến **không thể tự nạp chồng toán tử `+`** bằng cách khai báo một phương thức tên `add`. Java không hỗ trợ operator overloading tùy ý cho đối tượng.

Điểm dễ nhầm là **chỉ có những wrapper cụ thể** như `Integer` hay `Double` được unbox tự động theo quy tắc của Java. Kiểu khai báo `Number` không phải một kiểu được unbox trực tiếp thành “một số nguyên thủy bất kỳ”.

```java
Integer x = 3;
Integer y = 4;
int ok = x + y;           // Hợp lệ: hai Integer thành hai int.

// Number nx = x;
// Number ny = y;
// int notOk = nx + ny;  // LỖI biên dịch: Number + Number.
```

Không có toán tử `add(Number,Number)` chung được kế thừa từ `Object` hay `Number`, và Java không tra cứu phương thức `add` của đối tượng lúc chạy mỗi khi thấy dấu `+`.

**Kiểu động** dùng cho dispatch phương thức và `instanceof`; **kiểu tĩnh** là cơ sở chính để kiểm tra toán tử ở thời điểm biên dịch.

## 3. Điều gì xảy ra khi khai báo biến bằng `Number`?

```java
Number a = Integer.valueOf(10);
Number b = Double.valueOf(2.5);
```

Hai biến hợp lệ do cả `Integer` lẫn `Double` kế thừa `Number`. Thông tin kiểu thật của đối tượng không biến mất, nhưng biến tham chiếu chỉ bảo đảm **các thao tác công khai của `Number`**. Vì vậy:

```java
double approx = a.doubleValue() + b.doubleValue(); // 12.5
int discarded = a.intValue() + b.intValue();       // 12: phần 0.5 bị mất.
```

Hai phép cộng ở đây chạy được bởi chúng ta đã **chọn rõ cách chuyển đổi**. Kết quả `approx` là **tổng xấp xỉ theo `double`**; `discarded` là tổng sau khi từng đối tượng được chuyển sang `int`. Không thể coi chúng là hai cách viết tương đương của “cộng Number”.

Việc lấy `intValue()` đối với `2.5` sẽ bỏ phần thập phân, cho `2`. Với giá trị lớn hoặc các lớp con đặc biệt, chuyển đổi còn có thể mất bit, overflow khi chuyển hoặc đổi từ giá trị chính xác sang giá trị gần đúng. Vì vậy **việc ép về một kiểu chung là quyết định nghiệp vụ**, không phải hành vi mặc định an toàn.

## 4. `Integer + Integer`: unboxing chứ không phải phép cộng đối tượng

Java cho phép:

```java
Integer left = 10;
Integer right = 20;
Integer sum = left + right; // int 30, sau đó boxing về Integer.
```

Điều diễn ra là:

1. Hai biến `Integer` được **unbox** thành hai `int`.
2. Phép cộng nguyên thủy `int + int` tạo ra `int`.
3. Kết quả `int` được **box** trở lại `Integer` khi gán.

Đây không phải việc `Integer` có một overload `operator+`; Java quy định sẵn phép tự chuyển wrapper tương ứng. Nó cũng không biến các đối tượng `Integer` thành đối tượng có thể sửa giá trị: `Integer` bất biến.

```java
Integer n = null;
// int invalid = n + 1; // Biên dịch được về kiểu, nhưng chạy sẽ ném NullPointerException.
```

Unboxing cần có một đối tượng khác `null`. Trong Java, `Number` cũng có thể nhận `null`; nếu gọi `doubleValue()` trên `null`, bạn cũng gặp `NullPointerException`. Cần định nghĩa rõ cách xử lý dữ liệu thiếu trước khi cộng.

## 5. Vì sao không thể có phép cộng chính xác duy nhất cho mọi `Number`?

Các lớp con của `Number` có **mô hình số học và miền giá trị không đồng nhất**:

| Lớp | Kiểu giá trị | Phép cộng được khuyến nghị |
| --- | --- | --- |
| `Integer` | Số nguyên có dấu 32 bit | `int + int`, hoặc `Math.addExact` khi cần phát hiện tràn |
| `Long` | Số nguyên có dấu 64 bit | `long + long`, hoặc `Math.addExact` |
| `Float`/`Double` | Dấu phẩy động nhị phân hữu hạn độ chính xác | Cộng `float`/`double`, có thể có sai số làm tròn |
| `BigInteger` | Số nguyên độ chính xác tùy ý | `bigInteger.add(otherBigInteger)` |
| `BigDecimal` | Số thập phân có thang đo và độ chính xác thích hợp | `bigDecimal.add(otherBigDecimal)` |
| `AtomicInteger`/`AtomicLong` | Wrapper số có trạng thái thay đổi nguyên tử | API `addAndGet`/`getAndAdd` nếu cần cập nhật trạng thái |

Một phép cộng “chung” phải trả lời những câu hỏi không hề có một đáp án duy nhất:

- Trả về `int`, `long`, `double`, `BigInteger` hay `BigDecimal`?
- Nếu một đầu vào là `BigDecimal("0.1")` và đầu vào kia là `Double.valueOf(0.2)`, muốn cộng **decimal theo ký tự hiển thị**, hay cộng giá trị nhị phân thực tế của `double`?
- Nếu `BigInteger` rất lớn không thể chuyển chính xác sang `double`, chấp nhận mất chính xác hay báo lỗi?
- Nếu có overflow số nguyên hoặc NaN/Infinity, phải quay vòng, ném ngoại lệ hay chuyển sang kiểu khác?
- Nếu là `AtomicInteger`, muốn **đọc giá trị hiện tại** hay **cập nhật một biến có thể bị các luồng khác thay đổi**?

Do các lớp mang những ngữ nghĩa khác nhau, `Number` cố ý chỉ đưa ra hợp đồng chuyển kiểu cơ bản. **Không có một kết quả cộng chính xác với semantics duy nhất** cho mọi tổ hợp lớp con, nhất là khi có lớp do thư viện bên ngoài tự định nghĩa.

## 6. Tính gần đúng bằng `doubleValue()`: khi nào dùng được?

Đối với thống kê, đồ họa hoặc các phép đo chấp nhận sai số dấu phẩy động, có thể định nghĩa rõ một hàm cộng gần đúng:

```java
static double approximateSum(Number a, Number b) {
    return a.doubleValue() + b.doubleValue();
}
```

Đây là **phương thức trong một lớp Java**. Nó có tác dụng vì cả hai đối tượng đều được chuyển về `double` trước khi cộng. Nhưng tên `approximateSum` nên nêu thẳng đây là phép tính gần đúng.

Ví dụ giới hạn độ chính xác:

```java
java.math.BigInteger big =
        new java.math.BigInteger("9007199254740993");

double converted = big.doubleValue();
// converted biểu diễn 9007199254740992, mất một đơn vị.
```

`double` chỉ có 53 bit significand hiệu dụng. Giá trị `9_007_199_254_740_993 = 2^53 + 1` không thể lưu chính xác bằng `double` và sẽ được làm tròn. Nếu đối tượng `BigInteger` còn lớn hơn dải của `double`, `doubleValue()` có thể trả Infinity. Kết quả cộng `double` cũng có thể bị rounding, overflow hoặc underflow.

**Khi dùng cách này:** người lập trình đã chấp nhận sai số, dữ liệu đầu vào nằm trong dải có ý nghĩa và đặc tả đầu ra yêu cầu `double`. Không dùng `doubleValue()` như giải pháp cộng tổng quát cho tiền tệ hoặc số nguyên lớn đòi hỏi chính xác từng đơn vị.

## 7. Vì sao `intValue()` và `longValue()` không phải giải pháp tổng quát?

Hai phương thức này dễ dùng nhưng có thể **thu hẹp kiểu, bỏ phần lẻ hoặc cắt bớt bit**.

```java
Number a = Integer.valueOf(10);
Number b = Double.valueOf(2.5);
int sum = a.intValue() + b.intValue(); // 12, KHÔNG phải 12.5
```

Một ví dụ khác:

```java
java.math.BigInteger beyondInt =
        new java.math.BigInteger("4294967296");
int lost = beyondInt.intValue(); // 0: chỉ còn 32 bit thấp.
```

Đối với `BigInteger`, `intValue()` có thể chỉ giữ 32 bit thấp, khiến `4_294_967_296` thành `0`. Cách này không báo lỗi. Nếu thật sự cần chuyển `BigInteger` sang `int` một cách chính xác, dùng `intValueExact()`, phương thức sẽ ném `ArithmeticException` khi giá trị không nằm trong phạm vi.

Tương tự, `BigDecimal.intValueExact()` có thể phát hiện cả giá trị có phần thập phân không thể chuyển chính xác thành số nguyên. Các phương thức `Exact` là API của **lớp cụ thể**; `Number` không hứa rằng mọi lớp con đều có `intValueExact()`.

Một nguyên tắc hữu ích: **chọn miền giá trị và chính sách lỗi trước**, rồi mới gọi phương thức chuyển đổi. Đừng chuyển toàn bộ `Number` về `int` chỉ vì cần một phép cộng cú pháp đơn giản.

## 8. `BigInteger.add`: chính xác đối với số nguyên lớn

Nếu dữ liệu mang ngữ nghĩa số nguyên chính xác, `BigInteger` cho phép cộng không bị tràn ở ranh giới `int`/`long` thông thường:

```java
java.math.BigInteger a =
        new java.math.BigInteger("9007199254740993");
java.math.BigInteger b = java.math.BigInteger.ONE;
java.math.BigInteger exact = a.add(b);
// exact == 9007199254740994 (về giá trị số).
```

Đây là **mảnh mã** có thể đặt trong một phương thức. `BigInteger` không định nghĩa toán tử `+`; bạn phải gọi `a.add(b)`. Phương thức trả về **một đối tượng giá trị mới**; nó không sửa `a` hoặc `b`.

Nếu `a` được khai báo là `Number` dù bên trong trỏ tới `BigInteger`, trình biên dịch vẫn **không cho phép** `a.add(b)`, vì `Number` không có phương thức `add`. Cần giữ kiểu cụ thể trong API hoặc kiểm tra/cast hợp lệ. Tránh cast thiếu kiểm tra với dữ liệu không chắc chắn.

```java
Number value = new java.math.BigInteger("123");
if (value instanceof java.math.BigInteger big) {
    java.math.BigInteger plusOne = big.add(java.math.BigInteger.ONE);
}
```

**`instanceof` pattern matching** ở ví dụ này được hỗ trợ trong Java 17. Với lớp khác `BigInteger`, nhánh đó không chạy; chúng ta không giả định mọi `Number` đều có cùng phương thức cộng.

## 9. `BigDecimal.add`: phép cộng số thập phân theo ngữ nghĩa đã chọn

Nếu bài toán cần phép cộng decimal chính xác, đặc biệt trong bài toán tài chính hoặc các giá trị có thang đo thập phân, `BigDecimal` thường là lựa chọn phù hợp:

```java
java.math.BigDecimal a = new java.math.BigDecimal("0.1");
java.math.BigDecimal b = new java.math.BigDecimal("0.2");
java.math.BigDecimal sum = a.add(b); // 0.3 chính xác theo decimal.
```

Khi cả hai giá trị được tạo trực tiếp từ chuỗi thập phân `"0.1"` và `"0.2"`, `BigDecimal` giữ chính xác ý nghĩa thập phân và kết quả cộng là `0.3`. Ngược lại, phép `double` `0.1 + 0.2` không bằng `0.3` theo phép so sánh `==` do biểu diễn nhị phân hữu hạn.

Cảnh báo quan trọng: `new BigDecimal(0.1)` lấy **đúng giá trị nhị phân đã làm tròn của `double` 0.1**, vì vậy không có cùng ý nghĩa như `new BigDecimal("0.1")`. `BigDecimal.valueOf(0.1)` dùng biểu diễn chuỗi decimal round-trip của `double` và thường cho kết quả gần ý định chữ số người viết hơn, nhưng vẫn **không khôi phục được một giá trị chính xác ban đầu đã mất trước đó**.

Với phép cộng `BigDecimal.add` không truyền `MathContext`, các chữ số decimal được tính chính xác trong giới hạn tài nguyên. Nếu cung cấp `MathContext` và precision hữu hạn, phép toán có thể làm tròn theo bối cảnh đó; đặc tả nghiệp vụ cần nêu rõ.

Không nên chuyển **tùy ý mọi `Number` thành `BigDecimal` bằng `new BigDecimal(number.doubleValue())`**, vì một `BigInteger` lớn có thể bị mất chính xác ngay ở bước `doubleValue()`. Cũng không nên coi `number.toString()` của lớp con bất kỳ là dữ liệu decimal chuẩn: API `Number` không bắt buộc format chuỗi mà `BigDecimal` parse được.

## 10. Giải bài toán generic bằng cách truyền phép cộng của kiểu cụ thể

Với một kiểu `T extends Number`, Java cho biết `T` có các phương thức chuyển số, nhưng **không thể suy ra phép cộng giữ nguyên kiểu `T`**. Vì thế hàm sau là **không hợp lệ**:

```java
// Ví dụ cố ý SAI — không đưa vào chương trình chạy:
// static <T extends Number> T add(T a, T b) {
//     return a + b; // COMPILE ERROR: T + T không được định nghĩa.
// }
```

Một hướng thiết kế an toàn hơn là yêu cầu bên gọi cung cấp **chiến lược cộng** cho `T`:

```java
static <T extends Number> T addWith(
        T a, T b, java.util.function.BinaryOperator<T> adder) {
    return adder.apply(a, b);
}
```

Ví dụ cách gọi:

```java
Integer a = addWith(7, 9, Integer::sum); // 16

java.math.BigDecimal d =
        addWith(new java.math.BigDecimal("1.25"),
                new java.math.BigDecimal("2.75"),
                java.math.BigDecimal::add);    // 4.00
```

`BinaryOperator<T>` là một functional interface có chữ ký nhận hai `T` và trả một `T`. **Hàm generic chỉ tổ chức lời gọi, còn phép cộng thực sự do caller quyết định.** Ưu điểm là người dùng có thể chọn phát hiện overflow, xử lý decimal, áp dụng MathContext hoặc chính sách nghiệp vụ khác.

Trong trường hợp kiểu nguyên thủy cố định, có thể đơn giản hơn bằng `IntBinaryOperator`, `LongBinaryOperator` hoặc `DoubleBinaryOperator`, tránh boxing không cần thiết. Với `Integer::sum`, kết quả vẫn theo ngữ nghĩa `int` thông thường: **có thể overflow**. Nếu cần phát hiện tràn, truyền `Math::addExact` với kiểu phù hợp.

## 11. Danh sách `List<Number>`: cần chọn chính sách tổng

Một danh sách gồm nhiều lớp con:

```java
java.util.List<Number> values = java.util.List.of(1, 2.5, 3L);
```

Không có chuyện `List<Number>` tự biết nên dùng `BigDecimal`, `long` hay `double` cho tổng. Bạn có thể chủ động xác định chính sách “tổng gần đúng bằng `double`”:

```java
double total = 0.0;
for (Number value : values) {
    total += value.doubleValue();
}
// total == 6.5 với dữ liệu ví dụ.
```

Đây là **mảnh mã** khi `values` đã được khai báo. Nếu dùng stream, `values.stream().mapToDouble(Number::doubleValue).sum()` cũng thể hiện rõ lựa chọn tổng `double`, song nó không bảo đảm chính xác cho số nguyên lớn hoặc số thập phân tài chính.

Với dữ liệu chỉ gồm `BigInteger`, hãy sử dụng `List<BigInteger>` rồi `reduce(BigInteger.ZERO, BigInteger::add)`. Với `BigDecimal` cũng có thể dùng `reduce(BigDecimal.ZERO, BigDecimal::add)` với sự chú ý tới thang đo của kết quả. Đừng làm mất thông tin kiểu cụ thể quá sớm bằng cách đổi mọi cấu trúc dữ liệu thành `List<Number>` nếu ứng dụng yêu cầu toán học chính xác.

## 12. Kết hợp nhiều lớp con: thiết kế quy tắc trước khi viết code

Nếu API thật sự cần chấp nhận cả `Integer`, `Long`, `BigInteger`, `BigDecimal`, `Double` và những lớp khác, trước tiên cần chốt **quy tắc cộng**. Một lựa chọn thiết kế có kiểm soát:

1. **Số nguyên chính xác:** chỉ chấp nhận các loại nguyên đã nêu rõ và chuyển sang `BigInteger` không mất thông tin, sau đó dùng `BigInteger.add`.
2. **Số thập phân chính xác:** chấp nhận những nguồn decimal tin cậy (`BigDecimal`, chuỗi số decimal đã được parse theo contract) và dùng `BigDecimal.add`.
3. **Số thực gần đúng:** chấp nhận `float`/`double` hay các lớp tương thích với hợp đồng `doubleValue()`, kiểm tra phạm vi và đặc biệt NaN/Infinity nếu ứng dụng cần.
4. **Hỗn hợp:** quyết định tường minh được phép nâng lên `BigDecimal`, chuyển về `double`, hay phải báo lỗi khi hai kiểu không tương thích.
5. **Lớp con tùy biến:** không tự mặc định `Number.toString()` hay `doubleValue()` có tính chất chính xác/parse được. Cần adapter hoặc chính sách được lớp đó cung cấp.

Một hệ thống quan tâm type safety có thể sử dụng các đối tượng biểu diễn phép tính (strategy), ví dụ `NumericOps<T>` chứa phương thức `T add(T,T)`, hoặc phân tách API thành `sumIntegers`, `sumDecimals`, `sumApproximateDoubles`. Đây là cách đặt **ngữ nghĩa cộng** vào hợp đồng của ứng dụng thay vì giả định `Number` đã có sẵn hợp đồng đó.

## 13. Wrapper dạng nguyên tử không thay đổi quy tắc `Number`

`AtomicInteger` và `AtomicLong` trong `java.util.concurrent.atomic` cũng kế thừa `Number` và cho phép đọc các dạng số thông qua `intValue()`, `longValue()`, v.v. Nhưng chúng là **bộ chứa trạng thái có thể thay đổi**, thiết kế cho một số thao tác nguyên tử:

```java
java.util.concurrent.atomic.AtomicInteger counter =
        new java.util.concurrent.atomic.AtomicInteger(5);
int updated = counter.addAndGet(3); // 8.
```

`addAndGet(3)` là **phương thức trên `AtomicInteger`**, không phải `Number.add`. Nếu chỉ giữ biến ở kiểu `Number`:

```java
Number n = counter;
int snapshot = n.intValue(); // Đọc giá trị tại thời điểm gọi.
```

Bạn không thể gọi `n.addAndGet(3)` khi biến có kiểu tĩnh `Number`, vì `Number` không khai báo phương thức này. Ngoài ra, `n.intValue() + 3` chỉ cộng trên một giá trị snapshot, **không cập nhật atomic counter**. Không nên dùng `Number` để che giấu khác biệt về trạng thái/đồng bộ nếu logic nghiệp vụ cần cập nhật chính đối tượng.

## 14. Chương trình Java 17+ hoàn chỉnh

Tạo tệp **`NumberAdditionDemo.java`**:

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.BinaryOperator;

public class NumberAdditionDemo {
    static double approximateSum(Number a, Number b) {
        return a.doubleValue() + b.doubleValue();
    }

    static <T extends Number> T addWith(
            T a, T b, BinaryOperator<T> adder) {
        return adder.apply(a, b);
    }

    public static void main(String[] args) {
        Number left = Integer.valueOf(10);
        Number right = Double.valueOf(2.5);
        System.out.println("numberTypes="
                + left.getClass().getSimpleName()
                + "," + right.getClass().getSimpleName());
        System.out.println("approximateSum=" + approximateSum(left, right));
        System.out.println("intValueSum=" + (left.intValue() + right.intValue()));

        Integer boxedA = 10;
        Integer boxedB = 20;
        System.out.println("wrapperPlus=" + (boxedA + boxedB));

        BigInteger large = new BigInteger("9007199254740993");
        System.out.println("bigIntegerAdd=" + large.add(BigInteger.ONE));
        System.out.println("bigIntegerToDouble="
                + BigDecimal.valueOf(large.doubleValue()).toPlainString());
        System.out.println("bigIntegerToInt=" + new BigInteger("4294967296").intValue());

        BigDecimal tenth = new BigDecimal("0.1");
        BigDecimal fifth = new BigDecimal("0.2");
        System.out.println("decimalAdd=" + tenth.add(fifth).toPlainString());
        System.out.println("doublePoint3Equal=" + ((0.1 + 0.2) == 0.3));

        System.out.println("genericInteger="
                + addWith(7, 9, Integer::sum));
        System.out.println("genericDecimal="
                + addWith(new BigDecimal("1.25"),
                        new BigDecimal("2.75"), BigDecimal::add).toPlainString());

        List<Number> values = List.of(1, 2.5, 3L);
        double total = 0.0;
        for (Number value : values) {
            total += value.doubleValue();
        }
        System.out.println("heterogeneousDoubleTotal=" + total);

        AtomicInteger atomic = new AtomicInteger(5);
        Number asNumber = atomic;
        System.out.println("atomicAsNumber=" + asNumber.intValue());
        System.out.println("atomicAddAndGet=" + atomic.addAndGet(3));

        Integer nullable = null;
        try {
            int result = nullable + 1;
            System.out.println(result);
        } catch (NullPointerException ex) {
            System.out.println("nullUnboxing=NullPointerException");
        }
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac --release 17 -encoding UTF-8 NumberAdditionDemo.java
java NumberAdditionDemo
```

Stdout chính xác:

```text
numberTypes=Integer,Double
approximateSum=12.5
intValueSum=12
wrapperPlus=30
bigIntegerAdd=9007199254740994
bigIntegerToDouble=9007199254740992
bigIntegerToInt=0
decimalAdd=0.3
doublePoint3Equal=false
genericInteger=16
genericDecimal=4.00
heterogeneousDoubleTotal=6.5
atomicAsNumber=5
atomicAddAndGet=8
nullUnboxing=NullPointerException
```

Các nhóm kết quả cần lưu ý:

- `numberTypes=Integer,Double` xác minh cả hai đối tượng đều là lớp con `Number`, nhưng `Number + Number` vẫn không hợp lệ về mặt kiểu tĩnh.
- `approximateSum=12.5`, `intValueSum=12`: **chọn phương thức chuyển kiểu quyết định kết quả**; `intValue()` cắt mất phần thập phân của `2.5`.
- `wrapperPlus=30`: `Integer + Integer` chạy được qua unboxing; đó không phải cộng object bằng nạp chồng toán tử.
- `bigIntegerAdd=9007199254740994` đối lập `bigIntegerToDouble=9007199254740992`: cộng `BigInteger` giữ chính xác; đổi qua `double` có thể làm tròn. `bigIntegerToInt=0` cho thấy chuyển hẹp có thể mất toàn bộ phần giá trị quan trọng.
- `decimalAdd=0.3` và `doublePoint3Equal=false`: `BigDecimal` từ chuỗi biểu diễn decimal chính xác, còn `double` là xấp xỉ nhị phân.
- `genericInteger=16` và `genericDecimal=4.00`: hai phép cộng được **truyền dưới dạng chiến lược cụ thể**.
- `heterogeneousDoubleTotal=6.5`: danh sách hỗn hợp có thể cộng theo chính sách `double`, chứ không nhờ toán tử `+` của `Number`.
- `atomicAddAndGet=8`: phương thức cập nhật của wrapper nguyên tử; `nullUnboxing=NullPointerException`: unboxing trên `null` thất bại khi chạy.

## 15. Những nhầm lẫn thường gặp

| Nhầm lẫn | Thực tế | Cách xử lý |
| --- | --- | --- |
| `Number` là cha của mọi wrapper nên `Number + Number` được | `Number` không thuộc nhóm kiểu được unbox trực tiếp | Giữ kiểu cụ thể hoặc chuyển theo chính sách |
| `Integer + Integer` chứng minh lớp `Integer` có `operator+` | Java thực hiện unboxing, cộng nguyên thủy và boxing | Phân biệt quy tắc ngôn ngữ với phương thức đối tượng |
| Mọi `Number` đều có `add` | `add` thuộc một số lớp cụ thể như `BigInteger`, `BigDecimal` | Dùng API lớp cụ thể |
| `doubleValue()` luôn giữ đủ giá trị | Số nguyên lớn/decimal có thể bị làm tròn, vượt phạm vi | Dùng `BigInteger` hoặc `BigDecimal` khi yêu cầu chính xác |
| `intValue()` chỉ bỏ phần lẻ | Nó còn có thể bỏ bit cao của số nguyên rất lớn | Chuyển chính xác với API `*ValueExact` khi có |
| Generic `<T extends Number>` có phép `a+b` | Bound `Number` không khai báo phép cộng | Nhận `BinaryOperator<T>` hoặc interface nghiệp vụ |
| `Number.toString()` luôn là chuỗi decimal hợp lệ | Contract của `Number` không bắt buộc mọi lớp con theo định dạng này | Hỗ trợ loại nguồn đã biết và kiểm thử |
| `new BigDecimal(0.1)` giống `new BigDecimal("0.1")` | Bản `double` đã bị làm tròn nhị phân | Dùng chuỗi decimal theo đặc tả |
| `List<Number>` có tổng chính xác mặc định | Không có kiểu/semantics chung cho phép cộng | Chọn `List<BigDecimal>`, `List<BigInteger>` hoặc quy tắc rõ |
| `AtomicInteger` cộng được qua `Number` | API nguyên tử của lớp cụ thể, không phải của `Number` | Giữ đúng kiểu khi cần cập nhật đồng thời |
| Unboxing wrapper `null` sẽ tự coi là 0 | Unboxing `null` ném `NullPointerException` | Kiểm tra hoặc quy ước dữ liệu thiếu rõ ràng |

## 16. Tự kiểm tra kiến thức

1. **Vì sao `Number a = 1; Number b = 2; a+b` không biên dịch?** Vì kiểu tĩnh của hai toán hạng là `Number`, không có unboxing chung hay overload phép cộng.
2. **Vì sao `Integer a = 1; Integer b = 2; a+b` hợp lệ?** Hai `Integer` được unbox thành hai `int`, sau đó cộng nguyên thủy.
3. **`Number x = 10, y = 2.5;` muốn cộng gần đúng thì viết gì?** `x.doubleValue() + y.doubleValue()`, kết quả `12.5`; phải chấp nhận chính sách `double`.
4. **Nếu thay bằng `x.intValue() + y.intValue()` thì kết quả ra sao?** `12`, vì phần 0.5 bị bỏ trước khi cộng.
5. **`BigInteger` cộng bằng cách nào?** Dùng `a.add(b)`, không phải `a+b`.
6. **`BigDecimal("0.1") + BigDecimal("0.2")` nên viết gì?** `new BigDecimal("0.1").add(new BigDecimal("0.2"))`, trả `0.3`.
7. **Một hàm generic `<T extends Number>` có thể `return a+b` không?** Không; cần chiến lược cộng `BinaryOperator<T>` hoặc API rõ cho từng kiểu.
8. **Vì sao `BigInteger("9007199254740993").doubleValue()` mất một đơn vị?** Vì `double` không lưu chính xác mọi số nguyên lớn hơn `2^53`.
9. **Nếu nhận một `Number` là `AtomicInteger`, gọi `intValue()+1` có cập nhật bộ đếm không?** Không; chỉ cộng một snapshot. Dùng `AtomicInteger.addAndGet` khi cần cập nhật nguyên tử.
10. **Nếu hệ thống cần cộng tiền chính xác, có nên nhận mọi loại `Number` rồi gọi `doubleValue()`?** Không; nên dùng kiểu và chính sách decimal chính xác (thường `BigDecimal`) cho dữ liệu hợp lệ ngay từ đầu.

**Ghi nhớ:** **`Number` là abstraction để cùng đọc giá trị dưới những kiểu nguyên thủy, không phải abstraction cho phép cộng**. Toán tử `+` của Java được quyết định bởi kiểu tĩnh, unboxing và quy tắc số nguyên thủy; các kiểu số đối tượng khác có API riêng. Khi cần tổng của nhiều lớp con, hãy **quyết định rõ kiểu đích, độ chính xác, overflow, cách xử lý hỗn hợp và lỗi**, rồi dùng phương thức cụ thể hoặc truyền phép toán tường minh.
