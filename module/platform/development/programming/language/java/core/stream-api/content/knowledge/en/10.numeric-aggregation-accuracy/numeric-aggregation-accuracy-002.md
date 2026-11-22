# Tràn số khi tính tổng số nguyên và cách lựa chọn kiểu

Khi dùng Java Stream API để cộng số lượng, doanh thu hoặc điểm số, cú pháp `sum()` rất ngắn nhưng **không tự bảo đảm tổng chính xác**. Phép cộng trên `int` và `long` có miền giá trị hữu hạn. Nếu tổng vượt phạm vi cho phép, Java có thể tạo ra giá trị âm hoặc một giá trị dương sai mà không ném ngoại lệ.

Bài học thuộc chương **Độ chính xác khi tổng hợp số** của mô-đun **JAVA_STREAM_API**. Mục tiêu là hiểu khi nào `IntStream.sum()`, `LongStream.sum()`, `reduce()` và các collector có thể tràn số; biết **mở rộng kiểu trước khi tính**, dùng `Math.addExact` khi muốn phát hiện tràn số, chọn `BigInteger` khi cần tổng số nguyên không bị giới hạn bởi `long`, và đánh giá các lựa chọn theo dữ liệu thực tế. Các nguyên tắc này cũng áp dụng cho `filter`, `map`, `groupingBy`, collector tùy chỉnh và pipeline song song.

## 1. Tràn số nguyên là gì?

Java dùng số nguyên nguyên thủy có độ rộng cố định:

| Kiểu | Số bit | Giá trị nhỏ nhất | Giá trị lớn nhất |
| --- | ---: | ---: | ---: |
| `byte` | 8 | -128 | 127 |
| `short` | 16 | -32.768 | 32.767 |
| `int` | 32 | -2.147.483.648 | 2.147.483.647 |
| `long` | 64 | -9.223.372.036.854.775.808 | 9.223.372.036.854.775.807 |

`IntStream` tính tổng dưới kiểu `int`, còn `LongStream` tính tổng dưới kiểu `long`. Nếu phép cộng vượt giới hạn, Java giữ các bit thấp theo ngữ nghĩa số nguyên bù hai; kết quả “quay vòng” (*wraparound*). Phép cộng nguyên thủy thông thường **không tự ném `ArithmeticException` khi tràn số**.

Ví dụ:

```java
int intMax = Integer.MAX_VALUE;
long longMax = Long.MAX_VALUE;

System.out.println(intMax + 1);  // -2147483648
System.out.println(longMax + 1); // -9223372036854775808
```

Trong toán học, hai tổng phải lớn hơn giá trị tối đa. Kết quả trong Java khác vì kiểu lưu trữ không chứa được giá trị cần biểu diễn.

### 1.1. Tràn số xảy ra ngay cả khi pipeline trông hợp lệ

```java
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class OverflowBasics {
    public static void main(String[] args) {
        int wrong = IntStream.of(Integer.MAX_VALUE, 1)
            .sum();

        long correctWithinLong = IntStream.of(Integer.MAX_VALUE, 1)
            .asLongStream()
            .sum();

        long wrongAgain = LongStream.of(Long.MAX_VALUE, 1L)
            .sum();

        System.out.println(wrong);             // -2147483648
        System.out.println(correctWithinLong); // 2147483648
        System.out.println(wrongAgain);        // -9223372036854775808
    }
}
```

`asLongStream()` mở rộng từng `int` sang `long` **trước khi cộng**, nên tổng `2.147.483.648` được giữ chính xác. Tuy vậy, `long` cũng có giới hạn và không giải quyết được mọi trường hợp.

## 2. Phân biệt kiểu dữ liệu đầu vào và kiểu của phép tổng

Một lỗi phổ biến là chỉ nhìn **kiểu của biến nhận kết quả**:

```java
import java.util.stream.IntStream;

long total = IntStream.of(1_500_000_000, 1_500_000_000)
    .sum();

System.out.println(total); // -1294967296 (sai với tổng toán học)
```

`IntStream.sum()` trả về `int`. Phép cộng `int` đã tràn **trước khi** kết quả được gán sang biến `long`. Việc khai báo `long total` chỉ mở rộng **giá trị sai** sau tràn; nó không sửa được phép tính trước đó.

Muốn nhận tổng đúng, cần chuyển kiểu **trước phép tổng**:

```java
long total = IntStream.of(1_500_000_000, 1_500_000_000)
    .asLongStream()
    .sum();

System.out.println(total); // 3000000000
```

Cách tương đương là ánh xạ sang `long`:

```java
long total = IntStream.of(1_500_000_000, 1_500_000_000)
    .mapToLong(value -> value)
    .sum();
```

### 2.1. `Stream<Integer>` cũng cần chọn phép cộng thích hợp

Danh sách `List<Integer>` tạo `Stream<Integer>`. Nếu dùng `reduce` với kiểu nhận là `Integer`, tổng vẫn theo kiểu `int`:

```java
import java.util.List;

List<Integer> values = List.of(1_500_000_000, 1_500_000_000);

int wrong = values.stream()
    .reduce(0, Integer::sum);

long correct = values.stream()
    .mapToLong(Integer::longValue)
    .sum();

System.out.println(wrong);   // -1294967296
System.out.println(correct); // 3000000000
```

`mapToLong(Integer::longValue)` chuyển mỗi `Integer` sang `long` rồi thực hiện tổng ở `LongStream`. Đây là cách thuận tiện khi dữ liệu nguồn có kiểu wrapper nhưng phép tổng phải có phạm vi lớn hơn.

Nếu `List<Integer>` có thể chứa `null`, `Integer::longValue` sẽ ném `NullPointerException`. Hãy xác định chính sách xử lý giá trị thiếu trước khi unboxing, chẳng hạn `filter(Objects::nonNull)` nếu nghiệp vụ cho phép bỏ qua phần tử thiếu.

### 2.2. Mở rộng kiểu phải xảy ra trước cả phép nhân

Giả sử mỗi dòng hóa đơn có `int quantity` và `int unitPrice`. Viết `mapToLong(x -> x.quantity() * x.unitPrice())` **vẫn có thể sai**, vì hai toán hạng là `int` nên phép nhân thực hiện theo `int`, rồi kết quả mới được chuyển sang `long`.

```java
record Item(int quantity, int unitPriceVnd) {}

Item item = new Item(50_000, 50_000);

long wrong = item.quantity() * item.unitPriceVnd();

long correct = (long) item.quantity() * item.unitPriceVnd();

System.out.println(wrong);   // -1794967296
System.out.println(correct); // 2500000000
```

Đúng trong pipeline:

```java
import java.util.List;

List<Item> items = List.of(new Item(50_000, 50_000));

long revenue = items.stream()
    .mapToLong(item -> (long) item.quantity() * item.unitPriceVnd())
    .sum();

System.out.println(revenue); // 2500000000
```

**Nguyên tắc:** Hãy kiểm tra kiểu ở **từng phép toán trung gian**, không chỉ ở `sum()` hoặc biến nhận kết quả.

## 3. Chọn kiểu theo miền giá trị của bài toán

Việc chọn kiểu nên xuất phát từ số lượng phần tử tối đa, phạm vi mỗi giá trị và các phép tính trung gian.

Giả sử có tối đa `N` giá trị nguyên, mỗi giá trị có độ lớn tuyệt đối không vượt quá `M`. Khi đó, độ lớn của tổng không vượt `N × M`. Có thể dùng giới hạn này để đánh giá kiểu số, miễn là việc **tính chính giới hạn** cũng không bị tràn.

Ví dụ: hệ thống có nhiều nhất một triệu bản ghi, mỗi bản ghi có số lượng sản phẩm không quá một triệu. Tổng lớn nhất là `10^12`; lớn hơn giới hạn `int` nhưng nằm trong `long`. Vì thế `mapToLong` hoặc `LongStream` thích hợp hơn `IntStream.sum()`.

Với tổng có giá trị âm và dương, cần chú ý cả giới hạn dưới lẫn giới hạn trên của kiểu. Ngay cả khi **tổng cuối cùng** nằm trong giới hạn, các tổng trung gian vẫn có thể vượt giới hạn nếu dữ liệu được cộng theo thứ tự bất lợi.

| Nhu cầu | Kiểu/chiến lược phù hợp | Điểm cần nhớ |
| --- | --- | --- |
| Giá trị và mọi tổng trung gian bảo đảm nằm trong 32 bit | `int` / `IntStream.sum()` | Dễ đọc, gọn, nhưng không có kiểm tra tràn mặc định. |
| Các giá trị là `int`, tổng cần miền 64 bit | `IntStream.asLongStream().sum()` hoặc `Stream<T>.mapToLong(...).sum()` | Mở rộng **trước khi cộng**. |
| Dữ liệu vốn là `long` và chắc chắn không vượt 64 bit | `LongStream.sum()` | Cộng `long` vẫn có thể tràn nếu giả định sai. |
| Phải báo lỗi nếu cộng vượt kiểu đã chọn | `Math.addExact` kết hợp `reduce` hoặc phép lặp | Ngoại lệ xảy ra tại phép cộng trung gian bị tràn. |
| Tổng có thể vượt `Long.MAX_VALUE` hoặc cần kết quả số nguyên tuyệt đối | `BigInteger` | Chính xác theo số nguyên, đổi lại chi phí đối tượng/bộ nhớ. |
| Tiền có phần thập phân hoặc phép tính cần quy tắc làm tròn thập phân | `BigDecimal` | Chọn `scale` và cách làm tròn theo nghiệp vụ. |

Không dùng `double` chỉ để tránh giới hạn của `long`: `double` không bảo đảm biểu diễn chính xác mọi số nguyên lớn. Các số nguyên chỉ được bảo đảm chính xác liên tiếp đến `2^53`; lớn hơn mức này, một số giá trị khác nhau có cùng biểu diễn `double`.

## 4. Phát hiện tràn số bằng `Math.addExact`

`Math.addExact(int, int)` và `Math.addExact(long, long)` thực hiện phép cộng và **ném `ArithmeticException` nếu kết quả vượt phạm vi kiểu tương ứng**.

```java
int safe = Math.addExact(1_000_000, 2_000_000);
System.out.println(safe); // 3000000

try {
    int overflow = Math.addExact(Integer.MAX_VALUE, 1);
    System.out.println(overflow);
} catch (ArithmeticException exception) {
    System.out.println("Tổng vượt phạm vi int");
}
```

Trong Stream, có thể truyền `Math::addExact` vào `reduce`:

```java
import java.util.stream.IntStream;

int exactSum = IntStream.of(100, 200, 300)
    .reduce(0, Math::addExact);

System.out.println(exactSum); // 600
```

Nếu tổng trung gian bị tràn, `reduce` sẽ ném ngoại lệ:

```java
try {
    int total = IntStream.of(Integer.MAX_VALUE, 1)
        .reduce(0, Math::addExact);

    System.out.println(total);
} catch (ArithmeticException exception) {
    System.out.println("Phát hiện tràn số trong quá trình reduce");
}
```

Tương tự với `LongStream`:

```java
import java.util.stream.LongStream;

long total = LongStream.of(1_000_000_000L, 2_000_000_000L)
    .reduce(0L, Math::addExact);

System.out.println(total); // 3000000000
```

### 4.1. `Math.addExact` không “nới rộng” phạm vi

`Math.addExact` **phát hiện lỗi**, chứ không tự chuyển tổng sang kiểu lớn hơn. Nếu tổng hợp lệ về toán học nhưng vượt phạm vi `int`, cần chọn `long` hoặc `BigInteger` tùy yêu cầu.

Ví dụ, phép cộng `Integer.MAX_VALUE + 1` chính xác trong `long`, nên nếu nghiệp vụ cho phép tổng đó, `asLongStream().sum()` có ý nghĩa hơn việc cố cộng `int` và bắt ngoại lệ.

### 4.2. Tổng cuối vừa kiểu vẫn có thể có trung gian vượt kiểu

Xem dãy:

```text
[2_147_483_647, 1, -1]
Tổng toán học cuối cùng = 2_147_483_647
```

Nếu cộng từ trái sang phải bằng `Math.addExact`, phép tính `2_147_483_647 + 1` ném ngoại lệ **trước khi** cộng `-1`, dù tổng cuối cùng có thể biểu diễn bằng `int`.

```java
import java.util.stream.IntStream;

try {
    int total = IntStream.of(Integer.MAX_VALUE, 1, -1)
        .reduce(0, Math::addExact);
    System.out.println(total);
} catch (ArithmeticException exception) {
    System.out.println("Một tổng trung gian đã vượt phạm vi int");
}
```

Khi sử dụng `parallel()`, các nhóm phần tử có thể được cộng và kết hợp theo thứ tự khác nhau; với `Math.addExact`, việc có phát hiện tràn trung gian hay không có thể phụ thuộc cách nhóm. Vì vậy, nếu yêu cầu là **kết quả cuối cùng chính xác theo số nguyên toán học rồi mới kiểm tra có nằm trong `int` hay không**, hãy tích lũy bằng kiểu đủ rộng hoặc `BigInteger`, sau đó chuyển về kiểu đích bằng phép chuyển đổi có kiểm tra.

## 5. Tính tổng không giới hạn 64 bit bằng `BigInteger`

`BigInteger` trong `java.math` biểu diễn số nguyên có độ chính xác tùy ý, bị giới hạn chủ yếu bởi bộ nhớ và nguồn lực thực thi. Nó không phải kiểu nguyên thủy và **không có `BigIntegerStream` chuẩn** trong Java Stream API.

Có thể bắt đầu từ `LongStream`, chuyển mỗi `long` thành `BigInteger`, rồi giảm bằng phép cộng:

```java
import java.math.BigInteger;
import java.util.stream.LongStream;

public class BigIntegerSumDemo {
    public static void main(String[] args) {
        BigInteger total = LongStream.of(Long.MAX_VALUE, 1L)
            .mapToObj(BigInteger::valueOf)
            .reduce(BigInteger.ZERO, BigInteger::add);

        System.out.println(total); // 9223372036854775808
    }
}
```

`mapToObj(BigInteger::valueOf)` tạo `Stream<BigInteger>` từ các giá trị `long`. `reduce(BigInteger.ZERO, BigInteger::add)` sử dụng `ZERO` làm phần tử trung hòa và `add` để tổng hợp. Các phép cộng trên `BigInteger` không tràn như kiểu `long`; dữ liệu lớn sẽ tăng chi phí tính toán và bộ nhớ.

Ví dụ tương tự với đối tượng nghiệp vụ:

```java
record Entry(long amountVnd) {}

BigInteger total = java.util.List.of(
        new Entry(Long.MAX_VALUE),
        new Entry(1L)
    ).stream()
    .map(entry -> BigInteger.valueOf(entry.amountVnd()))
    .reduce(BigInteger.ZERO, BigInteger::add);

System.out.println(total); // 9223372036854775808
```

Nếu các giá trị đầu vào **đã vượt `long`**, không thể lưu chúng trong `long` rồi mới chuyển thành `BigInteger`. Cần đọc và lưu đúng từ đầu, ví dụ:

```java
BigInteger huge = new BigInteger("123456789012345678901234567890");
BigInteger answer = huge.add(BigInteger.ONE);

System.out.println(answer);
// 123456789012345678901234567891
```

### 5.1. Chuyển kết quả về kiểu nhỏ hơn sau khi kiểm tra

`BigInteger` có các phương thức `intValueExact()` và `longValueExact()`. Chúng ném `ArithmeticException` nếu không thể biểu diễn giá trị chính xác trong kiểu đích.

```java
BigInteger sum = BigInteger.valueOf(Integer.MAX_VALUE)
    .add(BigInteger.ONE);

long asLong = sum.longValueExact();
System.out.println(asLong); // 2147483648

try {
    int asInt = sum.intValueExact();
    System.out.println(asInt);
} catch (ArithmeticException exception) {
    System.out.println("Tổng chính xác nhưng vượt phạm vi int");
}
```

Phương pháp này hữu ích khi đầu vào có dấu âm/dương bù trừ khiến tổng cuối nằm trong giới hạn, nhưng cần bảo đảm không mất thông tin do tổng trung gian tràn.

## 6. Tràn số trong `reduce`, `collect` và thống kê

Tên phương thức `sum` không phải dấu hiệu duy nhất của rủi ro. Bất kỳ phép tổng hợp nào cộng bằng kiểu hữu hạn đều cần được xem xét.

### 6.1. `reduce` không tự động kiểm tra tràn

```java
import java.util.List;

List<Integer> values = List.of(Integer.MAX_VALUE, 1);

int totalWithReduce = values.stream()
    .reduce(0, Integer::sum);

System.out.println(totalWithReduce); // -2147483648
```

`Integer::sum` cộng bằng `int` và có cùng giới hạn như phép `+`. Phần tử trung hòa `0` không làm phép cộng trở nên chính xác hơn.

### 6.2. `Collectors.summingInt` và `summingLong`

`Collectors.summingInt` trả về `Integer`; `Collectors.summingLong` trả về `Long`. Chúng cũng có thể tràn số nếu tổng vượt phạm vi tương ứng.

```java
import java.util.List;
import java.util.stream.Collectors;

record Expense(String category, int amountVnd) {}

List<Expense> expenses = List.of(
    new Expense("Thiết bị", 1_500_000_000),
    new Expense("Thiết bị", 1_500_000_000)
);

int wrong = expenses.stream()
    .collect(Collectors.summingInt(Expense::amountVnd));

long correctWithinLong = expenses.stream()
    .collect(Collectors.summingLong(expense -> (long) expense.amountVnd()));

System.out.println(wrong);             // -1294967296
System.out.println(correctWithinLong); // 3000000000
```

Trong biểu thức `summingLong`, ánh xạ trả về `long`, nên dữ liệu được mở rộng trước khi tổng hợp.

### 6.3. Phân biệt `IntStream.sum()` và `IntSummaryStatistics.getSum()`

Một điểm dễ bỏ sót: `IntStream.sum()` trả về `int`, trong khi `IntSummaryStatistics.getSum()` trả về `long`.

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

int overflowed = IntStream.of(1_500_000_000, 1_500_000_000)
    .sum();

IntSummaryStatistics statistics =
    IntStream.of(1_500_000_000, 1_500_000_000)
        .summaryStatistics();

long widened = statistics.getSum();

System.out.println(overflowed); // -1294967296
System.out.println(widened);     // 3000000000
```

`IntSummaryStatistics` cộng các giá trị `int` vào bộ tích lũy `long`; điều này giải quyết ví dụ trên, nhưng **không có nghĩa tổng `long` sẽ luôn an toàn**. `LongSummaryStatistics.getSum()` cũng trả về `long` và có thể tràn khi vượt 64 bit.

Tương tự, `Collectors.summarizingInt(...)` trả về `IntSummaryStatistics`, nên `getSum()` là `long`; đừng nhầm với `Collectors.summingInt(...)` trả về `Integer`.

### 6.4. Gom nhóm bằng `groupingBy` vẫn phải chọn kiểu tổng

Giả sử muốn báo cáo tổng theo khu vực. Nếu tổng nhóm có thể lớn hơn `int` nhưng nằm trong `long`, dùng:

```java
import java.util.Map;
import java.util.stream.Collectors;

record Sale(String region, int amountVnd) {}

List<Sale> sales = List.of(
    new Sale("Bắc", 1_500_000_000),
    new Sale("Bắc", 1_500_000_000),
    new Sale("Nam", 100_000_000)
);

Map<String, Long> totals = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        Collectors.summingLong(sale -> (long) sale.amountVnd())
    ));

System.out.println(totals.get("Bắc")); // 3000000000
System.out.println(totals.get("Nam")); // 100000000
```

Nếu tổng nhóm có thể vượt `long`, dùng `BigInteger` trong một collector thích hợp:

```java
import java.math.BigInteger;
import java.util.Map;
import java.util.stream.Collectors;

record LargeSale(String region, long amountVnd) {}

List<LargeSale> largeSales = List.of(
    new LargeSale("Bắc", Long.MAX_VALUE),
    new LargeSale("Bắc", 1L)
);

Map<String, BigInteger> exactTotals = largeSales.stream()
    .collect(Collectors.groupingBy(
        LargeSale::region,
        Collectors.reducing(
            BigInteger.ZERO,
            sale -> BigInteger.valueOf(sale.amountVnd()),
            BigInteger::add
        )
    ));

System.out.println(exactTotals.get("Bắc"));
// 9223372036854775808
```

`Collectors.reducing` cho phép chọn rõ **kiểu của bộ tích lũy và phép kết hợp**. Collector tùy chỉnh có thể phù hợp với các phép tổng hợp phức tạp hơn, nhưng không cần thiết nếu `reducing` giải quyết đủ yêu cầu.

## 7. Tràn số ở phép nhân trước khi tổng hợp

Bài toán thực tế thường tính `đơn giá × số lượng` trước khi cộng các dòng. Mỗi phép nhân phải được bảo vệ giống phép cộng.

Ví dụ lỗi:

```java
record Purchase(int quantity, int unitPriceVnd) {}

Purchase purchase = new Purchase(50_000, 50_000);

long wrong = purchase.quantity() * purchase.unitPriceVnd();

System.out.println(wrong); // -1794967296
```

Để dùng `long` từ đầu:

```java
long lineTotal = (long) purchase.quantity()
    * purchase.unitPriceVnd();

System.out.println(lineTotal); // 2500000000
```

Nếu sản phẩm vẫn có nguy cơ vượt phạm vi `long`, dùng `Math.multiplyExact(long, long)` để phát hiện hoặc `BigInteger.multiply` để tính chính xác.

```java
long price = 4_000_000_000L;
long quantity = 3L;

long safeProduct = Math.multiplyExact(price, quantity);
System.out.println(safeProduct); // 12000000000
```

Khi đơn giá và số lượng lớn hơn nhiều, biểu thức như `Math.multiplyExact(Long.MAX_VALUE, 2L)` sẽ ném ngoại lệ. `BigInteger` hỗ trợ phép nhân lớn:

```java
BigInteger exactProduct = BigInteger.valueOf(Long.MAX_VALUE)
    .multiply(BigInteger.valueOf(2L));

System.out.println(exactProduct); // 18446744073709551614
```

Vì vậy, đối với quy trình `filter → mapToLong → sum`, phải kiểm tra **cả phép ánh xạ tạo ra giá trị số** lẫn tổng cuối cùng.

## 8. Tiền tệ có phần thập phân: không thay bằng `double`

Nếu dữ liệu là tiền có phần thập phân, dùng `double` để tránh tràn số nguyên có thể tạo ra lỗi biểu diễn nhị phân.

```java
double result = 0.1 + 0.2;
System.out.println(result); // 0.30000000000000004
```

Với tiền tệ, lựa chọn thông thường là:

- Dùng `long` lưu **đơn vị nhỏ nhất** như đồng, xu, cent, nếu giới hạn và quy tắc làm tròn đã xác định.
- Dùng `BigDecimal` khi có số thập phân, cần phép tính theo số thập phân và quy tắc làm tròn rõ ràng.

Ví dụ `BigDecimal`:

```java
import java.math.BigDecimal;
import java.util.List;

List<BigDecimal> amounts = List.of(
    new BigDecimal("0.10"),
    new BigDecimal("0.20")
);

BigDecimal total = amounts.stream()
    .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(total); // 0.30
```

Ví dụ sử dụng chuỗi thập phân để xây giá trị `BigDecimal` chính xác theo dữ liệu đầu vào. Tránh `new BigDecimal(0.1)` nếu ý định là số thập phân đúng `0.1`, vì đối số `double` đã mang biểu diễn nhị phân xấp xỉ. Cần đặt quy định về `scale` và `RoundingMode` khi tính phần trăm, thuế hoặc phép chia.

`BigDecimal` giải quyết bài toán số thập phân; `BigInteger` giải quyết bài toán số nguyên có độ lớn tùy ý. Hãy chọn theo **ý nghĩa nghiệp vụ**, không chỉ vì muốn một kiểu “lớn hơn”.

## 9. Ví dụ hoàn chỉnh: tổng hợp doanh thu an toàn

Đoạn mã Java 17+ dưới đây cho thấy ba chiến lược rõ ràng:

1. `long` cho tổng thường gặp mà phạm vi đã được kiểm soát.
2. `Math.multiplyExact` và `Math.addExact` để phát hiện tràn số ở kiểu `long`.
3. `BigInteger` nếu muốn cộng chính xác cả khi tổng có thể vượt `long`.

```java
import java.math.BigInteger;
import java.util.List;

public class SafeRevenueAggregation {
    record Order(String id, long unitPriceVnd, long quantity) {}

    static long totalWithLong(List<Order> orders) {
        return orders.stream()
            .mapToLong(order ->
                order.unitPriceVnd() * order.quantity()
            )
            .sum();
    }

    static long totalWithExactChecks(List<Order> orders) {
        return orders.stream()
            .mapToLong(order -> Math.multiplyExact(
                order.unitPriceVnd(), order.quantity()
            ))
            .reduce(0L, Math::addExact);
    }

    static BigInteger totalWithBigInteger(List<Order> orders) {
        return orders.stream()
            .map(order -> BigInteger.valueOf(order.unitPriceVnd())
                .multiply(BigInteger.valueOf(order.quantity())))
            .reduce(BigInteger.ZERO, BigInteger::add);
    }

    public static void main(String[] args) {
        List<Order> regularOrders = List.of(
            new Order("O-01", 1_500_000_000L, 2L),
            new Order("O-02", 2_000_000_000L, 3L)
        );

        System.out.println(totalWithLong(regularOrders));
        System.out.println(totalWithExactChecks(regularOrders));
        System.out.println(totalWithBigInteger(regularOrders));
        // Cả ba đều in: 9000000000

        List<Order> hugeOrders = List.of(
            new Order("O-03", Long.MAX_VALUE, 1L),
            new Order("O-04", 1L, 1L)
        );

        System.out.println(totalWithLong(hugeOrders));
        // -9223372036854775808: giá trị tràn, không dùng cho nghiệp vụ.

        try {
            System.out.println(totalWithExactChecks(hugeOrders));
        } catch (ArithmeticException exception) {
            System.out.println("Tổng vượt phạm vi long");
        }

        System.out.println(totalWithBigInteger(hugeOrders));
        // 9223372036854775808: tổng chính xác.
    }
}
```

**Phân tích:** `totalWithLong` chỉ phù hợp khi có bằng chứng rằng **cả từng phép nhân và phép cộng** nằm trong `long`. `totalWithExactChecks` bảo vệ phép nhân và cộng bằng ngoại lệ; nếu chính sách là từ chối dữ liệu vượt giới hạn, đó là cách dễ hiểu. `totalWithBigInteger` nhận chi phí đối tượng và số học độ chính xác tùy ý để giữ kết quả chính xác về mặt số nguyên.

Không dùng kết quả sai do tràn số để lưu hóa đơn, quyết toán hoặc giới hạn tín dụng. Cần chọn chiến lược phù hợp ngay ở ranh giới dữ liệu và kiểm tra giới hạn trong các bước trung gian.

## 10. Tính lazy, song song và tính đúng của phép cộng

`filter`, `map`, `mapToLong` và `mapToObj` là thao tác trung gian, thường được thực thi khi terminal operation `sum()` hoặc `reduce()` tiêu thụ pipeline. Một Stream chỉ được tiêu thụ một lần.

```java
import java.util.stream.LongStream;

var amounts = LongStream.of(100L, 200L)
    .filter(value -> value > 0L); // Chưa tính tổng.

long total = amounts.sum(); // 300

// amounts.count(); // Không được dùng lại Stream đã tiêu thụ.
```

### 10.1. Song song không khắc phục tràn số

`parallel()` chia xử lý thành nhiều phần, sau đó kết hợp kết quả. Nó **không mở rộng kiểu số**:

```java
int wrong = java.util.stream.IntStream
    .of(Integer.MAX_VALUE, 1)
    .parallel()
    .sum();

System.out.println(wrong); // -2147483648
```

Phép cộng `int` vẫn là phép cộng `int`. Với số nguyên bù hai, kết quả tràn theo kiểu modular; dù pipeline chạy tuần tự hay song song, kết quả đó vẫn **không phải tổng toán học chính xác**.

`BigInteger::add` là phép cộng kết hợp (associative), nên thích hợp về mặt ngữ nghĩa cho `reduce` song song khi không có tác dụng phụ và dùng phần tử trung hòa `BigInteger.ZERO`. Tuy nhiên, xử lý song song có chi phí chia/ghép và cấp phát; không mặc định nhanh hơn với tập dữ liệu nhỏ.

### 10.2. `Math.addExact` và thứ tự gom nhóm

Như mục 4.2, `Math.addExact` ném ngoại lệ ở phép cộng trung gian bị tràn. Với xử lý song song, cách chia nhóm ảnh hưởng tổng trung gian được tạo ra; vì thế không nên dùng chiến lược này như một cách chứng minh độc lập với thứ tự rằng “tổng toán học cuối nằm trong giới hạn”.

Khi cần kiểm tra **chỉ tổng cuối** (cho phép giá trị trung gian vượt giới hạn), dùng `BigInteger` rồi gọi `intValueExact()` hoặc `longValueExact()` ở cuối. Khi mục tiêu là **không bao giờ thực hiện phép toán vượt miền `long`**, kiểm tra `Math.addExact`/`Math.multiplyExact` là phù hợp.

### 10.3. Trạng thái chia sẻ trong pipeline

Không tự cộng tiền vào một biến ngoài lambda:

```java
long[] total = {0L};

orders.parallelStream().forEach(order ->
    total[0] += order.unitPriceVnd() * order.quantity()
); // Không an toàn: có thể race condition.
```

Hãy dùng `mapToLong(...).sum()` khi miền `long` đã đủ, dùng `reduce(0L, Math::addExact)` để phát hiện tràn, hoặc `reduce(BigInteger.ZERO, BigInteger::add)` để có tổng nguyên chính xác. Các phương thức gom nhóm/collector cũng phải tuân thủ quy tắc về bộ tích lũy an toàn khi song song.

Nếu hiệu năng ảnh hưởng quyết định thiết kế, hãy đo bằng dữ liệu đại diện với công cụ phù hợp như JMH. `BigInteger` có thể tốn thêm bộ nhớ, còn `long` có thể nhanh hơn nếu tính đúng đã được bảo đảm. Hiệu năng chỉ có ý nghĩa khi **cả hai phương án đều trả về kết quả đúng theo yêu cầu**.

## 11. Các lỗi thường gặp

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Gán kết quả `IntStream.sum()` vào biến `long` và tưởng đã an toàn | `int` đã tràn trước khi gán | Dùng `asLongStream()` hoặc `mapToLong` trước `sum()`. |
| Viết `mapToLong(x -> x.intA() * x.intB())` | Nhân theo kiểu `int` rồi mới mở rộng | Ép một toán hạng sang `long` trước phép nhân. |
| Dùng `Integer::sum` trong `reduce` với tổng lớn | Tràn `int` âm thầm | Dùng `mapToLong`, `Math.addExact` hoặc `BigInteger` theo mục tiêu. |
| Cho rằng `Collectors.summingLong` không bao giờ tràn | Vẫn giới hạn trong `long` | Kiểm tra biên hoặc gom bằng `BigInteger`. |
| Dùng `Math.addExact` rồi nghĩ có thể nhận tổng lớn hơn kiểu | Ném ngoại lệ, không tạo số lớn hơn | Chọn `long` hoặc `BigInteger`. |
| Dùng `long` để nhân số đã tính bằng `int` | Tổn thất thông tin xảy ra trước phép gán | Chuyển kiểu trước phép toán. |
| Dùng `double` để lưu tổng số nguyên rất lớn | Có thể mất giá trị nguyên chính xác | Giữ `long` nếu đủ hoặc dùng `BigInteger`. |
| Dùng `new BigDecimal(0.1)` để thể hiện đúng 0,1 | Mang xấp xỉ nhị phân từ `double` | Dùng chuỗi thập phân hoặc giá trị đã được chuẩn hóa. |
| Chỉ xem tổng cuối mà bỏ qua các phép nhân/phép cộng trung gian | Trung gian đã tràn, kết quả không đáng tin | Kiểm tra toàn bộ pipeline và các biểu thức ánh xạ. |
| Tưởng `parallel()` sẽ giúp tính tổng chính xác hơn | Không thay đổi miền giá trị | Chọn kiểu số và phép cộng chính xác trước. |

## 12. Bài tập thực hành

### Bài 1: Tràn `IntStream.sum()`

Với `IntStream.of(1_200_000_000, 1_200_000_000)`, dự đoán kết quả của `sum()`. Viết lại bằng `asLongStream().sum()` và giải thích vì sao việc gán kết quả của `sum()` ban đầu sang `long` không thể sửa sai.

### Bài 2: Tính tiền theo dòng hóa đơn

Mỗi dòng có `quantity` và `unitPriceVnd` kiểu `int`, mỗi trường có giá trị `60_000`. Viết `Stream<Item>.mapToLong(...).sum()` để tổng hợp 100 dòng đúng. Thử viết `item.quantity() * item.unitPriceVnd()` trước khi ép kiểu và quan sát sự khác biệt.

### Bài 3: Phát hiện thay vì chấp nhận tràn

Tạo `IntStream.of(Integer.MAX_VALUE, 1)`. So sánh `sum()` với `reduce(0, Math::addExact)`. Khi nào nên ném ngoại lệ, khi nào nên mở rộng sang `long`?

### Bài 4: Tổng cuối trong phạm vi nhưng trung gian vượt phạm vi

Thử dãy `[Integer.MAX_VALUE, 1, -1]` với `reduce(0, Math::addExact)`. Sau đó đổi thành pipeline `mapToObj(BigInteger::valueOf)` (từ `IntStream`), `reduce(BigInteger.ZERO, BigInteger::add)` và `intValueExact()`. Giải thích sự khác biệt về ý nghĩa của hai chiến lược.

### Bài 5: Tổng theo nhóm bằng `BigInteger`

Cho nhiều đơn hàng có `region` và `amountVnd` kiểu `long`. Hãy dùng `Collectors.groupingBy` kết hợp `Collectors.reducing` để tạo `Map<String, BigInteger>`. Chạy thử nhóm có hai phần tử `Long.MAX_VALUE` và `1L`.

### Bài 6: Giới hạn và kế hoạch hiệu năng

Giả sử một ngày có thể có hai triệu giao dịch, giá trị mỗi giao dịch nằm trong khoảng -2 triệu đến +2 triệu đơn vị. Hãy tính biên tổng về mặt toán học, chọn kiểu phù hợp cho `sum()` và chỉ ra những giả định cần có. Nếu khối lượng tăng lên vài tỷ giao dịch, hãy đánh giá lại biên và nêu phép thử cần thực hiện.

### Bài 7: Tiền có phần thập phân

Tổng hợp `0.10` và `0.20` bằng `double` và `BigDecimal`. So sánh kết quả, sau đó giải thích khi nào hệ thống nên lưu tiền theo đơn vị nhỏ nhất bằng `long` và khi nào cần dùng `BigDecimal`.

## 13. Tự kiểm tra kiến thức

- `IntStream.sum()` trả về kiểu gì, và giới hạn của kiểu đó là bao nhiêu?
- Vì sao `long total = intStream.sum()` không tránh được tràn `int`?
- Cần ép kiểu vào thời điểm nào nếu phép nhân giữa hai `int` có thể vượt phạm vi?
- `Math.addExact` có tác dụng phát hiện hay mở rộng số? Khi nào nó ném ngoại lệ?
- Vì sao một dãy có tổng cuối vừa `int` vẫn có thể ném lỗi khi cộng bằng `Math.addExact`?
- `IntSummaryStatistics.getSum()` khác `IntStream.sum()` ở kiểu trả về ra sao?
- Khi nào `BigInteger` phù hợp hơn `long`, và cách kiểm tra khi chuyển ngược kiểu?
- Vì sao `parallelStream()` không chữa được tràn số hay các tác dụng phụ chia sẻ?
- Với tiền thập phân, `BigDecimal` giải quyết vấn đề nào mà `BigInteger` không trực tiếp mô tả?

**Ghi nhớ:** Độ chính xác của phép tổng phụ thuộc vào **kiểu của từng phép tính**, không phụ thuộc vào kiểu biến nhận kết quả cuối cùng. Mở rộng sang `long` **trước khi cộng hoặc nhân** nếu miền 64 bit đủ; dùng `Math.addExact`/`Math.multiplyExact` để báo lỗi khi tràn; chọn `BigInteger` khi tổng nguyên có thể vượt `long`. Với Java Stream API, hãy kiểm tra kỹ cả `map`, `reduce`, `sum`, collector và tác động của xử lý song song để giữ kết quả nghiệp vụ đúng.
