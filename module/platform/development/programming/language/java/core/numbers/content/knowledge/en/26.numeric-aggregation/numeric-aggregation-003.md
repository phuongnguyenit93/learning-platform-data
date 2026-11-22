# `sum` có thể tràn đối với số nguyên trong Java

Khi tính tổng một dãy số nguyên, tất cả phần tử đều hợp lệ chưa chắc tổng cũng nằm trong phạm vi kiểu dữ liệu. Java sử dụng các kiểu số nguyên có độ rộng cố định. Nếu phép cộng `int` hoặc `long` vượt giới hạn, kết quả **quấn vòng (wrap around)**; Java không tự đổi sang kiểu lớn hơn và phép cộng thông thường không ném lỗi. Điều này áp dụng cho vòng lặp, `IntStream.sum()`, `LongStream.sum()`, `reduce` và nhiều collector.

Bài này giúp nhận biết nơi xảy ra tràn, chọn cách tổng hợp chính xác và định nghĩa hợp đồng API rõ ràng: cho phép tổng rộng hơn, kiểm tra từng phép cộng, hay trả về kết quả không giới hạn 64 bit.

## 1. Bản chất tràn số nguyên

| Kiểu | Số bit | Nhỏ nhất | Lớn nhất |
| --- | ---: | ---: | ---: |
| `byte` | 8 | -128 | 127 |
| `short` | 16 | -32.768 | 32.767 |
| `int` | 32 | -2.147.483.648 | 2.147.483.647 |
| `long` | 64 | -9.223.372.036.854.775.808 | 9.223.372.036.854.775.807 |

`int` biểu diễn số nguyên có dấu bằng 32 bit; `long` bằng 64 bit. Khi cộng vượt miền, các bit kết quả được giữ theo modulo \(2^{32}\) hoặc \(2^{64}\). Bởi vậy:

```java
int a = Integer.MAX_VALUE;
int b = 1;
int wrapped = a + b; // -2147483648
```

Ở đây tổng toán học là `2147483648`, lớn hơn `Integer.MAX_VALUE`, còn `wrapped` trở thành `Integer.MIN_VALUE`. Tương tự, `Long.MAX_VALUE + 1L` cho `Long.MIN_VALUE`.

Phân biệt bốn đại lượng: **giới hạn của một phần tử**, **tổng toán học**, **kiểu dùng để cộng trung gian**, và **kiểu trả về**. Một danh sách có các số hợp lệ trong `int` có thể có tổng vượt `int` nếu đủ nhiều phần tử. Ngược lại, có trường hợp tổng cuối vừa `int` nhưng tổng trung gian theo một thứ tự cộng lại vượt `int`.

Lỗi đặc biệt phổ biến:

```java
int x = Integer.MAX_VALUE;
int y = 1;

long wrong = x + y;          // -2147483648: cộng bằng int trước khi gán
long correct = (long) x + y; //  2147483648: cộng bằng long
```

Kiểu của biến đích **không** quyết định kiểu của phép cộng đã thực hiện. Cần nâng kiểu **trước** phép cộng, hoặc dùng bộ tích lũy kiểu rộng ngay từ đầu.

## 2. `IntStream.sum()` và `LongStream.sum()` có thể overflow

`IntStream.sum()` trả `int`. `LongStream.sum()` trả `long`. Các API này không tự nâng kiểu hoặc kiểm tra tràn:

```java
import java.util.Arrays;

int[] values = {Integer.MAX_VALUE, 1};

int wrong = Arrays.stream(values).sum();                // -2147483648
long right = Arrays.stream(values).asLongStream().sum(); // 2147483648
```

`asLongStream()` đổi từng `int` thành `long` trước khi cộng. Vì vậy phép cộng tích lũy diễn ra trong miền `long`, đủ để biểu diễn tổng của ví dụ.

Với nguồn là `long[]`, dù dùng `LongStream` vẫn có giới hạn:

```java
long[] values = {Long.MAX_VALUE, 1L};
long wrong = Arrays.stream(values).sum(); // Long.MIN_VALUE
```

Hai mảnh mã trên dùng tên biến trùng nhau vì là **hai ví dụ riêng**; đặt chúng trong những phạm vi riêng nếu thử cùng một chương trình.

Các API tổng hợp có hành vi và kiểu trả về đáng chú ý:

| API/biểu thức | Loại kết quả | Điểm có thể tràn |
| --- | --- | --- |
| `int + int` | `int` | Ngay phép `+` |
| `long target = intA + intB` | Phép cộng `int`, sau đó gán `long` | Trước khi gán |
| `(long) intA + intB` | `long` | Nếu vượt miền `long` |
| `IntStream.sum()` | `int` | Bộ tích lũy 32 bit |
| `IntStream.asLongStream().sum()` | `long` | Bộ tích lũy 64 bit |
| `LongStream.sum()` | `long` | Bộ tích lũy 64 bit |
| `Collectors.summingInt(...)` | `Integer` | Tổng 32 bit |
| `Collectors.summingLong(...)` | `Long` | Tổng 64 bit |
| `IntSummaryStatistics.getSum()` | `long` | Tổng 64 bit |
| `LongSummaryStatistics.getSum()` | `long` | Tổng 64 bit |

`IntSummaryStatistics` là một điểm dễ nhầm: mặc dù nhận các phần tử `int`, trường tổng của nó sử dụng `long`. Tuy nhiên, các API có tổng `long` cũng không phải tổng chính xác không giới hạn.

## 3. `reduce`, `Integer::sum` và vòng lặp không tự chống tràn

Stream là mô hình xử lý dữ liệu, không phải cơ chế bảo vệ arithmetic. Những cách sau đều có thể cho tổng sai khi dùng `int`:

```java
int[] data = {Integer.MAX_VALUE, 1};

int loopSum = 0;
for (int value : data) {
    loopSum += value;
}

int reduced = Arrays.stream(data).reduce(0, Integer::sum);
int streamSum = Arrays.stream(data).sum();
```

`Integer.sum(int, int)` thực hiện phép cộng kiểu `int`; nó **không** có hành vi giống `Math.addExact`. `Collectors.summingInt` cũng tích lũy theo `int`:

```java
int result = Stream.of(Integer.MAX_VALUE, 1)
        .collect(Collectors.summingInt(Integer::intValue));
// result = -2147483648
```

Ví dụ collector cần `import java.util.stream.Stream;` và `import java.util.stream.Collectors;`.

Nếu nguồn là `List<Integer>`, hãy nâng từng phần tử trước khi tổng hợp:

```java
List<Integer> numbers = List.of(Integer.MAX_VALUE, 1);
long result = numbers.stream().mapToLong(Integer::longValue).sum();
```

Nhớ rằng đoạn dưới **đã tràn trước khi gán**:

```java
long wrong = numbers.stream().mapToInt(Integer::intValue).sum();
```

Một mảng `int[]` có chiều dài tối đa biểu diễn được bằng `int`, còn mỗi phần tử nằm trong miền `int`. Vì thế tổng toán học của mọi phần tử trong **một mảng `int[]`** luôn vừa `long`: tích của số phần tử lớn nhất với độ lớn một phần tử vẫn nhỏ hơn `Long.MAX_VALUE`. Đây là lý do `long` là kiểu thích hợp cho phép tổng toàn bộ `int[]`.

Điều đó **không áp dụng vô điều kiện cho mọi `IntStream`**, vì một luồng có thể phát sinh lượng phần tử lớn hơn giới hạn chiều dài một mảng. Một hệ thống tổng hợp qua nhiều đợt cũng có thể vượt `long` sau thời gian dài.

## 4. Giải pháp A: nâng kiểu trước khi cộng và trả `long`

Nếu biết trước tổng sẽ nằm trong miền `long`, hãy sử dụng bộ tích lũy `long`:

```java
long total = 0L;
for (int value : values) {
    total += value;
}
```

Trong biểu thức `total += value`, `value` được nâng lên `long` trước phép cộng. Với `int[]`, cách tương đương:

```java
long total = Arrays.stream(values).asLongStream().sum();
```

Nếu API **phải trả `int`** nhưng chỉ quan tâm tổng cuối có vừa `int` không, cộng an toàn bằng `long` rồi dùng `Math.toIntExact`:

```java
long total = Arrays.stream(values).asLongStream().sum();
int result = Math.toIntExact(total);
```

`Math.toIntExact(long)` ném `ArithmeticException` khi giá trị nằm ngoài phạm vi `int`, thay vì cắt bit như ép kiểu `(int) total`.

Tuy nhiên, nếu bản thân tổng `long` đã tràn ở bước trước, `Math.toIntExact` không thể khôi phục kết quả toán học ban đầu. Phải bảo đảm bộ tích lũy đủ rộng hoặc dùng `BigInteger`.

### Lưu ý phép nhân trước phép cộng

Nhiều tổng thực tế là tổng của `quantity * unitPrice`. Nếu cả hai toán hạng là `int`, phép nhân có thể tràn trước khi đưa vào `long`:

```java
int quantity = 100_000;
int unitPrice = 50_000;

long wrong = quantity * unitPrice;           // int đã tràn
long correct = (long) quantity * unitPrice;  // 5_000_000_000
```

Trong collector hoặc `mapToLong`, cần đặt phép ép kiểu vào đúng toán hạng **trước phép nhân**. Với phép nhân cần báo lỗi ngay khi tràn trong kiểu nguyên thủy, Java còn cung cấp `Math.multiplyExact`.

## 5. Giải pháp B: phát hiện tràn trong từng bước với `Math.addExact`

`Math.addExact(int, int)` và `Math.addExact(long, long)` ném `ArithmeticException` nếu tổng vượt miền tương ứng.

```java
int checked = Math.addExact(Integer.MAX_VALUE, 1);
// ArithmeticException: integer overflow
```

Có thể dùng trong vòng lặp:

```java
int sum = 0;
for (int value : values) {
    sum = Math.addExact(sum, value);
}
```

Hoặc trong `IntStream.reduce`:

```java
int sum = Arrays.stream(values).reduce(0, Math::addExact);
```

Đây là hợp đồng **kiểm tra mọi phép cộng trung gian**, khác với kiểm tra **chỉ tổng cuối**. Ví dụ:

```text
[2147483647, 1, -1]
```

Tổng toán học cuối là `2147483647`, hợp lệ đối với `int`. Nhưng khi cộng từ trái sang phải, hai phần tử đầu cho tổng `2147483648` và `Math.addExact` ném lỗi ngay, dù cộng thêm `-1` sẽ đưa tổng về miền `int`.

So sánh:

```java
int[] values = {Integer.MAX_VALUE, 1, -1};

int finalChecked = Math.toIntExact(
        Arrays.stream(values).asLongStream().sum());
// finalChecked = Integer.MAX_VALUE, thành công.

int everyStepChecked = Arrays.stream(values).reduce(0, Math::addExact);
// ArithmeticException do tổng trung gian vượt int.
```

Trong **parallel stream**, phép giảm có thể nhóm các phần tử theo thứ tự trung gian khác nhau. Với `Math::addExact`, một cách nhóm có thể gặp tràn còn cách khác không gặp, dù tổng toán học cuối giống nhau. Do đó, nếu nghiệp vụ chỉ muốn kiểm tra phạm vi tổng cuối, dùng kiểu tích lũy đủ rộng hoặc `BigInteger` để tính chính xác **trước khi** kiểm tra kiểu trả về. Nếu nghiệp vụ bắt buộc từ chối phép cộng trung gian ngoài phạm vi trong một thứ tự xác định, nên mô tả rõ thứ tự đó và dùng vòng lặp tuần tự.

**Quy tắc thiết kế:** Chọn và đặt tên rõ hai chế độ `sumCheckingEveryAddition` (báo lỗi ở bất kỳ bước nào) và `sumExactlyThenNarrow` (kiểm tra tổng cuối). Chúng không có cùng hợp đồng.

## 6. Giải pháp C: dùng `BigInteger` khi `long` cũng không đủ

Nếu tổng có thể vượt 64 bit, dùng `java.math.BigInteger` để cộng các số nguyên chính xác:

```java
import java.math.BigInteger;
import java.util.Arrays;

long[] data = {Long.MAX_VALUE, 1L};

BigInteger total = Arrays.stream(data)
        .mapToObj(BigInteger::valueOf)
        .reduce(BigInteger.ZERO, BigInteger::add);

// total = 9223372036854775808
```

`BigInteger` lưu số nguyên với độ dài biến thiên; `BigInteger.add` không quấn vòng ở giới hạn 32/64 bit. `BigInteger.valueOf(long)` giữ nguyên giá trị `long` đầu vào. Với nguồn là `int[]`, có thể dùng phương thức tương tự trên `IntStream.mapToObj(BigInteger::valueOf)`; Java mở rộng `int` thành `long` phù hợp với chữ ký `valueOf`.

Khi cần thu hẹp kết quả về kiểu nguyên thủy, phân biệt:

```java
long unsafe = total.longValue();       // Có thể cắt bớt bit.
long checked = total.longValueExact(); // Ném ArithmeticException nếu ngoài miền long.
```

Tương tự có `intValueExact()`. `BigInteger` phải cấp phát đối tượng và xử lý nhiều bit hơn kiểu nguyên thủy; chỉ dùng khi phạm vi dữ liệu đòi hỏi. Nó không đảm bảo tính toán có chi phí vô hạn: chương trình vẫn có giới hạn tài nguyên.

### Vì sao không thay bằng `double`?

`double` có miền độ lớn rộng nhưng chỉ giữ chính xác 53 bit significand cho các số nguyên. Vượt ngưỡng đó, không phải mọi số nguyên đều biểu diễn chính xác; tổng có thể bị làm tròn. Vì vậy, `double` không phải lựa chọn để giữ tổng nguyên tuyệt đối chính xác khi tổng có thể vượt `long`.

Nếu dữ liệu là số thập phân có phần lẻ với yêu cầu độ chính xác decimal, hãy xem xét `BigDecimal`; đó là bài toán khác với tổng nguyên và cũng cần chính sách scale/rounding phù hợp.

## 7. Tình huống với `summaryStatistics` và collectors

Đôi khi không chỉ cần tổng mà còn cần số phần tử, min và max:

```java
import java.util.IntSummaryStatistics;

IntSummaryStatistics stats = Arrays.stream(values).summaryStatistics();
long count = stats.getCount();
long sum = stats.getSum();
int min = stats.getMin();
int max = stats.getMax();
```

`getSum()` trả `long`, thường thuận tiện và đủ cho một `int[]`. Với stream rỗng, `count` bằng 0 và `sum` bằng 0; `min` là `Integer.MAX_VALUE`, `max` là `Integer.MIN_VALUE`. Kiểm tra `count > 0` trước khi diễn giải min/max thành quan sát thực tế.

Đối với `Stream<Order>` mà phương thức `Order::quantity` trả `int`, hai lựa chọn:

```java
int risky = orders.stream()
        .collect(Collectors.summingInt(Order::quantity));

long wider = orders.stream()
        .collect(Collectors.summingLong(Order::quantity));
```

Ví dụ này sử dụng lớp `Order` giả định; đây là **mảnh mã minh họa**, không phải chương trình độc lập. `summingLong` giúp nâng số lượng sang `long` trước phép cộng nhưng vẫn có thể tràn nếu tổng vượt `long`.

Nếu cần tổng giá trị `quantity * unitPrice`, nhớ nâng kiểu **trước nhân**:

```java
long total = orders.stream()
        .mapToLong(order -> (long) order.quantity() * order.unitPrice())
        .sum();
```

Nếu không nâng kiểu ngay trong mapper, biểu thức `int * int` có thể tràn rồi mới thành `long`. Nếu tổng nhiều tích vẫn có thể vượt miền `long`, chuyển sang `BigInteger` và tính từng tích bằng `BigInteger.multiply`.

## 8. Chương trình Java 17+ đầy đủ

Lưu nội dung sau trong tệp **`IntegerSumOverflowDemo.java`**:

```java
import java.math.BigInteger;
import java.util.Arrays;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class IntegerSumOverflowDemo {
    public static void main(String[] args) {
        int[] values = {Integer.MAX_VALUE, 1};

        System.out.println("int sum = " + Arrays.stream(values).sum());
        System.out.println("long sum = "
                + Arrays.stream(values).asLongStream().sum());
        System.out.println("summary sum = "
                + Arrays.stream(values).summaryStatistics().getSum());
        System.out.println("collector sum = "
                + Stream.of(Integer.MAX_VALUE, 1)
                        .collect(Collectors.summingInt(Integer::intValue)));

        try {
            int checked = Arrays.stream(values).reduce(0, Math::addExact);
            System.out.println("checked sum = " + checked);
        } catch (ArithmeticException ex) {
            System.out.println("checked sum = overflow");
        }

        long widened = Arrays.stream(values).asLongStream().sum();
        try {
            System.out.println("toIntExact = " + Math.toIntExact(widened));
        } catch (ArithmeticException ex) {
            System.out.println("toIntExact = overflow");
        }

        int[] mixed = {Integer.MAX_VALUE, 1, -1};
        System.out.println("mixed long final = "
                + Math.toIntExact(Arrays.stream(mixed).asLongStream().sum()));
        try {
            Arrays.stream(mixed).reduce(0, Math::addExact);
            System.out.println("mixed checked = valid");
        } catch (ArithmeticException ex) {
            System.out.println("mixed checked = prefix overflow");
        }

        long[] large = {Long.MAX_VALUE, 1L};
        System.out.println("long overflow = " + Arrays.stream(large).sum());
        BigInteger exact = Arrays.stream(large)
                .mapToObj(BigInteger::valueOf)
                .reduce(BigInteger.ZERO, BigInteger::add);
        System.out.println("big sum = " + exact);
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```bash
javac -encoding UTF-8 IntegerSumOverflowDemo.java
java IntegerSumOverflowDemo
```

Stdout chính xác (đã đối chiếu các biểu thức trên Java 21; mã dùng API có từ Java 17):

```text
int sum = -2147483648
long sum = 2147483648
summary sum = 2147483648
collector sum = -2147483648
checked sum = overflow
toIntExact = overflow
mixed long final = 2147483647
mixed checked = prefix overflow
long overflow = -9223372036854775808
big sum = 9223372036854775808
```

Điều cần quan sát: `IntStream.sum()` và `summingInt` đều quấn vòng; `asLongStream().sum()` và `IntSummaryStatistics.getSum()` giữ đúng tổng đầu tiên; `Math.addExact` và `Math.toIntExact` kiểm tra **những điều kiện khác nhau**; `LongStream.sum()` có thể tràn trong khi `BigInteger` giữ được tổng chính xác.

## 9. Định nghĩa hợp đồng của API tổng hợp

Một hàm tên `sum()` dễ khiến người dùng nghĩ rằng kết quả luôn bằng tổng toán học. Nếu có nguy cơ vượt phạm vi, API cần nói rõ kiểu trả về và chính sách overflow.

| Nhu cầu | Cách triển khai | Hành vi với overflow |
| --- | --- | --- |
| Tổng đầy đủ của một `int[]` | `Arrays.stream(values).asLongStream().sum()` | Trả `long` an toàn cho mảng `int[]` |
| API phải trả `int`, chỉ quan tâm kết quả cuối | Tính bằng `long`, rồi `Math.toIntExact` | Ném khi tổng cuối ngoài `int` |
| Từ chối ngay mọi phép cộng `int` bị tràn | Vòng lặp với `Math.addExact` | Ném ở phép cộng trung gian |
| Tổng các giá trị `long` có thể vượt 64 bit | `BigInteger` | Trả tổng nguyên chính xác |
| Cần count/min/max/sum trên `int[]` | `IntSummaryStatistics` | Tổng dùng `long`; kiểm tra điều kiện nguồn |
| Tổng số lượng từ object | `mapToLong` hoặc `Collectors.summingLong` | Tính trên `long` |
| `BigInteger` cần chuyển về `long` | `longValueExact()` | Ném khi tổng ngoài `long` |

Tên và chữ ký phương thức nên phản ánh chính sách, ví dụ:

```java
long sumIntsAsLong(int[] values);
int sumIntsAndCheckFinalRange(int[] values);
int sumIntsAndCheckEachAddition(int[] values);
BigInteger sumLongsExactly(long[] values);
```

Những dòng trên là **chữ ký minh họa**, cần thêm thân phương thức và đặt trong class thích hợp để biên dịch. Tài liệu API cũng cần quy định `null` đầu vào có hợp lệ không, mảng rỗng trả 0 hay không, thứ tự xử lý có quan trọng không, và có cho phép trả tổng lớn hơn phần tử nguồn không.

Trong nghiệp vụ tiền tệ lưu số cent bằng `long`, đừng mặc định rằng `long` luôn đủ: cần xét giới hạn số giao dịch, số lượng mỗi giao dịch và thời gian tích lũy. Với miền lớn khó chứng minh, cân nhắc `BigInteger`.

## 10. Những lỗi thường gặp và cách kiểm thử

### Lỗi cần tránh

1. Tin rằng `IntStream.sum()` tự mở rộng lên `long` hoặc ném ngoại lệ khi tràn.
2. Gán biểu thức `int + int` vào `long` rồi nghĩ phép cộng đã dùng `long`.
3. Dùng `Integer::sum` thay `Math.addExact`, tưởng rằng hai API có cùng hành vi.
4. Dùng `Collectors.summingInt` khi tổng có thể vượt giới hạn `int`.
5. Nghĩ rằng kiểm tra từng phép cộng với `Math.addExact` luôn tương đương với kiểm tra tổng cuối.
6. Dùng `Math.toIntExact` sau một phép cộng `long` đã tràn; khi đó kết quả toán học đã mất.
7. Dùng `BigInteger.longValue()` khi cần bảo toàn giá trị thay vì `longValueExact()`.
8. Dùng `double` để “tránh tràn nguyên” khi cần số nguyên tuyệt đối chính xác.
9. Quên phép nhân `int * int` có thể tràn trước khi tổng hợp.
10. Giả định parallel reduction không ảnh hưởng đến thời điểm phát hiện tràn từng phép cộng.

### Các ca kiểm thử tối thiểu

| Dữ liệu | Tổng toán học | Điều cần kiểm tra |
| --- | --- | --- |
| `[]` | 0 | Hợp đồng mảng rỗng |
| `[1, 2, 3]` | 6 | Trường hợp bình thường |
| `[Integer.MAX_VALUE, 1]` | 2.147.483.648 | Tràn `int` phía dương |
| `[Integer.MIN_VALUE, -1]` | -2.147.483.649 | Tràn `int` phía âm |
| `[Integer.MAX_VALUE, 1, -1]` | 2.147.483.647 | Tràn trung gian dù tổng cuối hợp lệ |
| `[Long.MAX_VALUE, 1L]` | 9.223.372.036.854.775.808 | Tràn `long`, cần `BigInteger` |
| `[100_000 * 50_000]` với toán hạng `int` | 5.000.000.000 | Cần nâng kiểu trước phép nhân |

Với code có `parallel()` và kiểm tra từng phép cộng, nên kiểm thử dữ liệu có số dương và âm lớn để hiểu rõ kết quả chịu ảnh hưởng bởi thứ tự nhóm. Với API kiểm tra tổng cuối, dùng kiểu tích lũy đủ rộng rồi kiểm tra một lần.

**Nguyên tắc:** Xác định độ lớn cực đại của phần tử, số phần tử tối đa và giới hạn tổng. Nâng kiểu **trước phép tính**; sử dụng `long` nếu chứng minh đủ rộng, `BigInteger` nếu cần miền vượt 64 bit. Nếu phải ném lỗi khi vượt kiểu trả về, nêu rõ đó là lỗi tại **mỗi bước cộng** hay ở **tổng cuối**.

### Tài liệu Java chính thức

- [`IntStream.sum()` và `IntStream.summaryStatistics()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/IntStream.html)
- [`LongStream.sum()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/LongStream.html)
- [`Math.addExact()` và `Math.toIntExact()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Math.html)
- [`Collectors.summingInt()` và `Collectors.summingLong()`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collectors.html)
- [`BigInteger`](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/math/BigInteger.html)