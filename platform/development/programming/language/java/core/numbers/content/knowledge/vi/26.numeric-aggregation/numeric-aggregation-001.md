# `int[]`, `long[]`, `double[]` và các stream chuyên biệt trong Java

## 1. Mảng số là nguồn dữ liệu, stream là pipeline xử lý

Java có ba loại mảng nguyên thủy thường dùng để tổng hợp số: `int[]`, `long[]` và `double[]`. Mảng giữ các phần tử theo **chỉ số** và có thể thay đổi phần tử; stream trình bày **một lượt duyệt và chuỗi thao tác** trên nguồn dữ liệu. Việc tạo stream không tự sao chép toàn bộ mảng.

```java
int[] counts = {3, 1, 4, 1, 5};
long[] bytes = {3_000_000_000L, 4_000_000_000L};
double[] temperatures = {19.5, 20.0, 21.5};
```

Độ rộng mỗi phần tử nguyên thủy là 32 bit (`int`), 64 bit (`long`) hoặc 64 bit dấu phẩy động nhị phân (`double`). Mảng có `length` và hỗ trợ truy cập `counts[0]`. Stream không cung cấp chỉ số tự động, sử dụng **một lần** và chỉ chạy pipeline trung gian khi có thao tác kết thúc như `sum()`, `average()` hoặc `toArray()`.

**Trọng tâm bài này** là chọn đúng nguồn mảng, đoạn mảng và vị trí chuyển kiểu. Bài tiếp theo đi sâu vào primitive stream so với `Stream<Integer/Long/Double>`, boxing và các collector.

## 2. Tạo đúng stream từ ba loại mảng

| Mảng đầu vào | Factory | Loại stream | Phần tử được duyệt |
| --- | --- | --- | --- |
| `int[]` | `Arrays.stream(array)` | `IntStream` | từng giá trị `int` |
| `long[]` | `Arrays.stream(array)` | `LongStream` | từng giá trị `long` |
| `double[]` | `Arrays.stream(array)` | `DoubleStream` | từng giá trị `double` |

```java
int intSum = java.util.Arrays.stream(new int[] {1, 2, 3}).sum(); // 6
long longSum = java.util.Arrays.stream(new long[] {3_000_000_000L, 4_000_000_000L}).sum(); // 7000000000
double doubleMean = java.util.Arrays.stream(new double[] {2.0, 4.0})
        .average().orElseThrow(); // 3.0
```

**Bẫy `Stream.of(array)`**: với mảng primitive, `Stream.of(new int[] {1, 2, 3})` có kiểu `Stream<int[]>` và **một phần tử là nguyên mảng**. `Arrays.stream(new int[] {1, 2, 3})` có kiểu `IntStream` với **ba phần tử số**. `Arrays.asList(intArray)` cũng giữ nguyên mảng primitive thành một phần tử của list thay vì tạo ba `Integer`.

### Một đoạn liên tiếp của mảng

`Arrays.stream(array, fromInclusive, toExclusive)` chỉ đọc vùng chỉ số `[fromInclusive, toExclusive)`. Với `int[] a = {10,20,30,40,50}`, `Arrays.stream(a,1,4).sum()` bằng `20+30+40 = 90`. `fromInclusive > toExclusive` gây `IllegalArgumentException`; chỉ số ngoài mảng có thể gây `ArrayIndexOutOfBoundsException`. Ba kiểu mảng đều có overload đọc đoạn.

## 3. Khi tính toán cần chỉ số

`Arrays.stream(array)` cho **giá trị** từng phần tử; nó không tự cung cấp vị trí trong mảng. Nếu cần chọn vị trí, xử lý hai mảng song song theo chỉ số hoặc tra cứu metadata tại vị trí, hãy tạo dãy chỉ số bằng `IntStream.range(0, array.length)`.

```java
int[] scores = {7, 9, 4, 10};
int[] highIndices = java.util.stream.IntStream.range(0, scores.length)
        .filter(i -> scores[i] >= 9)
        .toArray(); // {1, 3}
```

`range(start, end)` không gồm cận trên. Nếu xử lý hai mảng `prices[]` và `quantities[]`, phải kiểm tra độ dài tương ứng trước khi dùng cùng chỉ số. Khi đầu vào không bảo đảm có cùng số phần tử, đừng bỏ qua kiểm tra và trông chờ stream tự biết ý nghĩa quan hệ giữa hai mảng.

```java
int[] prices = {100, 200, 300};
int[] quantities = {2, 3, 1};
if (prices.length != quantities.length) {
    throw new IllegalArgumentException("Array lengths differ");
}
long revenue = java.util.stream.IntStream.range(0, prices.length)
        .mapToLong(i -> (long) prices[i] * quantities[i])
        .sum(); // 1100
```

Phép cast `(long) prices[i]` đặt **trước phép nhân** để nhân theo `long`. Nếu viết `(long) (prices[i] * quantities[i])`, phép nhân `int` có thể đã tràn trước khi bị ép kiểu. Tất nhiên tổng nhiều tích cũng phải nằm trong miền `long` nếu dùng `.sum()` kiểu đó.

## 4. Chuyển kiểu trước phép toán có thể mất dữ liệu

Việc đưa mảng `int[]` qua `Arrays.stream(...).sum()` tạo tổng kiểu `int`, có thể tràn. Khi tổng toán học của một `int[]` có thể vượt miền `int`, hãy nâng từng phần tử thành `long` **trước khi cộng**:

```java
int[] values = {2_000_000_000, 2_000_000_000};
int wrapped = java.util.Arrays.stream(values).sum(); // -294967296
long widened = java.util.Arrays.stream(values).asLongStream().sum(); // 4000000000
```

Với một mảng `int[]` thực tế (độ dài và phần tử đều trong giới hạn của Java), tổng toán học vẫn vừa miền `long`; nhưng tổng của `long[]` hoặc một luồng vô hạn/gom qua nhiều batch có thể vượt `long`. Khi cần tổng nguyên vượt miền `long`, dùng `BigInteger`. Bài **sum có thể tràn đối với số nguyên** phân biệt chi tiết phát hiện tràn từng bước và kiểm tra giới hạn tổng cuối.

Chuyển số nguyên `long` lớn sang `double` cũng có rủi ro: `double` chỉ bảo toàn liên tiếp mọi số nguyên đến `2^53`. Không chuyển dữ liệu ID/số đếm lớn qua `DoubleStream` chỉ vì muốn gọi phép trung bình khi yêu cầu là chính xác đến từng đơn vị.

## 5. Các terminal operation và ý nghĩa dữ liệu rỗng

| Terminal operation | `IntStream` | Khi rỗng |
| --- | --- | --- |
| `sum()` | `int` | `0` |
| `count()` | `long` | `0` |
| `average()` | `OptionalDouble` | `OptionalDouble.empty()` |
| `min()` / `max()` | `OptionalInt` | `OptionalInt.empty()` |
| `summaryStatistics()` | `IntSummaryStatistics` | `getCount()==0`, các cực trị là sentinel |
| `toArray()` | `int[]` | mảng rỗng |

Đối với `LongStream` và `DoubleStream`, các phép tương tự trả kiểu `long`/`double` hoặc `OptionalLong`/`OptionalDouble` phù hợp. `sum()` của dãy rỗng bằng 0 theo quy ước reduction; **trung bình hoặc cực trị của dãy rỗng không có giá trị số**. Vì vậy `average().orElse(0.0)` chỉ nên dùng nếu domain chủ động định nghĩa mặc định là 0.

`summaryStatistics()` cho count/sum/min/max/average trong **một lượt tiêu thụ stream**, hữu ích khi nguồn không dễ duyệt nhiều lần. Chú ý `IntSummaryStatistics.getSum()` trả `long`; với `LongSummaryStatistics` trường tổng vẫn là `long`. Khi `getCount() == 0`, không diễn giải `getMin()` hoặc `getMax()` là phép đo thực. Những ranh giới này được trình bày kỹ trong các bài về average, min/max và SummaryStatistics.

## 6. Ví dụ độc lập trên Java 17+

Tạo file `NumericArraysDemo.java`:

```java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.OptionalDouble;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class NumericArraysDemo {
    public static void main(String[] args) {
        int[] counts = {3, 1, 4, 1, 5};
        long[] distances = {3_000_000_000L, 4_000_000_000L};
        double[] temperatures = {19.5, 20.0, 21.5};

        System.out.println("array sum=" + Arrays.stream(counts).sum());
        System.out.println("long sum=" + Arrays.stream(distances).sum());
        System.out.println("double mean="
                + Arrays.stream(temperatures).average().orElseThrow());
        System.out.println("array as one=" + Stream.of(counts).count());
        System.out.println("primitive elements=" + Arrays.stream(counts).count());

        int[] indices = IntStream.range(0, counts.length)
                .filter(i -> counts[i] >= 4)
                .toArray();
        System.out.println("high indices=" + Arrays.toString(indices));

        int[] big = {2_000_000_000, 2_000_000_000};
        System.out.println("wrapped sum=" + Arrays.stream(big).sum());
        System.out.println("widened sum=" + Arrays.stream(big).asLongStream().sum());

        IntSummaryStatistics stats = Arrays.stream(counts).summaryStatistics();
        System.out.println("stats=" + stats.getCount() + "/"
                + stats.getSum() + "/" + stats.getMin() + "/"
                + stats.getMax() + "/" + stats.getAverage());
        OptionalDouble empty = Arrays.stream(new int[0]).average();
        System.out.println("empty average present=" + empty.isPresent());
    }
}
```

```bash
javac --release 17 NumericArraysDemo.java
java NumericArraysDemo
```

```text
array sum=14
long sum=7000000000
double mean=20.333333333333332
array as one=1
primitive elements=5
high indices=[2, 4]
wrapped sum=-294967296
widened sum=4000000000
stats=5/14/1/5/2.8
empty average present=false
```

Để kiểm chứng một kết quả, hãy tách câu hỏi thành **nguồn là mảng nào**, **pipeline xử lý theo giá trị hay chỉ số**, **kiểu tính toán tại mỗi phép toán**, và **trường hợp nguồn rỗng**. `DoubleStream.average()` có thể làm tròn theo binary64; đừng nhầm chữ số output với decimal exact.

## 7. Chọn cách duyệt theo bài toán

- **Mảng và vòng lặp:** thuận tiện khi cần sửa phần tử tại chỗ, truy cập chỉ số hoặc quản lý trạng thái theo thứ tự tường minh.
- **Primitive stream:** thuận tiện khi cần chuỗi lọc/biến đổi/tổng hợp không đòi boxing từng phần tử.
- **`IntStream.range` theo chỉ số:** thuận tiện khi cần vị trí hoặc tương quan giữa nhiều mảng; phải xác thực kích thước và tránh sửa nguồn từ lambda.
- **`summaryStatistics()`:** thuận tiện khi cần nhiều thống kê trong cùng một lần tiêu thụ; phải xác nhận số mẫu và giới hạn số học.

Trong pipeline song song, không mutate mảng/biến cộng dồn dùng chung và không kỳ vọng `parallel()` tự tăng tốc với mảng nhỏ. Với tổng `double`, cách phân nhóm có thể làm thay đổi các bit cuối; với yêu cầu decimal exact dùng loại dữ liệu và chính sách rounding phù hợp.

## 8. Câu hỏi tự kiểm tra

1. `Stream.of(new int[] {1,2,3}).count()` và `Arrays.stream(new int[] {1,2,3}).count()` khác nhau vì sao?
2. Làm sao lấy chỉ số của phần tử chẵn mà không nhầm chỉ số với giá trị?
3. Trong tổng doanh thu `price * quantity`, cast phải đứng ở đâu để phép nhân thực hiện bằng `long`?
4. Vì sao `long total = Arrays.stream(intArray).sum()` không sửa được tổng `int` đã bị tràn?
5. Khi `average()` rỗng, giữ Optional, ném lỗi hay hiển thị zero nên được quyết định bởi yếu tố nào?
6. Khi cần cả min/max/count trên một nguồn chỉ duyệt một lần, dùng API nào và cần guard điều kiện gì?

**Ghi nhớ:** Dạng mảng quyết định loại primitive stream; việc sử dụng một stream chỉ là một lượt xử lý trên nguồn. Với bài toán tổng hợp số, tính đúng đòi hỏi **chọn nguồn, chỉ số, kiểu tính toán và chính sách nguồn rỗng** rõ ràng trước khi tối ưu pipeline.