# counting, summing và averaging trong Java Collectors

## 1. Mục tiêu bài học

Khi xử lý dữ liệu bằng Stream, ba nhóm collector cơ bản giúp trả lời ba câu hỏi thường gặp:

1. **`counting()`:** Có bao nhiêu phần tử?
2. **`summingInt/Long/Double(mapper)`:** Tổng một thuộc tính số của các phần tử là bao nhiêu?
3. **`averagingInt/Long/Double(mapper)`:** Trung bình cộng của một thuộc tính số là bao nhiêu?

Chúng nằm trong `java.util.stream.Collectors`, được truyền vào terminal operation `Stream.collect(...)`. Cả ba nhóm vẫn là API tiêu chuẩn được hỗ trợ trong Java hiện đại và đã có từ Java 8.

Ví dụ nghiệp vụ: danh sách đơn hàng có `quantity` (số lượng), `revenue` (doanh thu) và `rating` (điểm đánh giá). Ta có thể đếm đơn hàng, cộng số lượng, tính tổng doanh thu và trung bình điểm. Khi muốn tính các chỉ số đó **theo từng nhóm**, chẳng hạn theo khu vực, các collector này đặc biệt hữu ích dưới dạng *downstream collector* của `groupingBy`.

Điểm khác nhau với `Stream.count()` hoặc `IntStream.sum()/average()` là các collector có thể **lồng vào phép gom nhóm** để tính số liệu trong từng nhóm, thay vì chỉ tính một kết quả cho toàn bộ stream.

## 2. Bảng API và kiểu dữ liệu kết quả

| Collector | Mapper đầu vào | Kết quả | Ý nghĩa |
| --- | --- | --- | --- |
| `Collectors.counting()` | Không cần mapper | `Long` | Số phần tử đã đi qua các bước lọc/biến đổi trước `collect`. |
| `Collectors.summingInt(mapper)` | `ToIntFunction<T>` | `Integer` | Tổng các giá trị `int` do mapper tạo ra. |
| `Collectors.summingLong(mapper)` | `ToLongFunction<T>` | `Long` | Tổng các giá trị `long` do mapper tạo ra. |
| `Collectors.summingDouble(mapper)` | `ToDoubleFunction<T>` | `Double` | Tổng các giá trị `double` do mapper tạo ra. |
| `Collectors.averagingInt(mapper)` | `ToIntFunction<T>` | `Double` | Trung bình cộng các giá trị `int`. |
| `Collectors.averagingLong(mapper)` | `ToLongFunction<T>` | `Double` | Trung bình cộng các giá trị `long`. |
| `Collectors.averagingDouble(mapper)` | `ToDoubleFunction<T>` | `Double` | Trung bình cộng các giá trị `double`. |

**Mapper là gì?** Mapper là hàm biến một phần tử kiểu `T` thành giá trị số nguyên thủy, ví dụ `Order::getQuantity` trả về `int` hoặc `Order::getRevenue` trả về `long`. Collector áp dụng mapper cho từng phần tử đầu vào, sau đó tổng hợp các số đã nhận.

**Lưu ý về kết quả:**

- `counting()` trả `Long` chứ không phải `Integer`. Biến `long` có thể nhận giá trị này nhờ tự động unboxing.
- `summingInt` trả `Integer`, `summingLong` trả `Long` và `summingDouble` trả `Double`.
- Cả ba `averaging...` đều trả `Double`, **kể cả khi giá trị đầu vào là `int` hoặc `long`**. Không nên khai báo biến kết quả là `int`.
- Đối với **stream rỗng**, `counting()` trả `0L`, `summingInt` trả `0`, `summingLong` trả `0L`, `summingDouble` trả `0.0`, và `averaging...` trả `0.0`.
- Với `counting()`, mỗi phần tử còn lại sau `filter` được tính là một đơn vị. Nó không tự đếm phần tử khác nhau; nếu muốn đếm giá trị khác nhau, cần đặt `distinct()` trước collector.

## 3. Ví dụ 1 — đếm, tính tổng và trung bình trên cùng một danh sách

Tạo file **CollectorBasicsDemo.java**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

public class CollectorBasicsDemo {
    public static void main(String[] args) {
        List<Integer> numbers = Arrays.asList(10, 20, 30, 40);

        long count = numbers.stream()
            .collect(Collectors.counting());

        int sumInt = numbers.stream()
            .collect(Collectors.summingInt(Integer::intValue));

        long sumLong = numbers.stream()
            .collect(Collectors.summingLong(Integer::longValue));

        double sumDouble = numbers.stream()
            .collect(Collectors.summingDouble(Integer::doubleValue));

        double averageInt = numbers.stream()
            .collect(Collectors.averagingInt(Integer::intValue));

        double averageLong = numbers.stream()
            .collect(Collectors.averagingLong(Integer::longValue));

        double averageDouble = numbers.stream()
            .collect(Collectors.averagingDouble(Integer::doubleValue));

        System.out.println("count=" + count);
        System.out.println("summingInt=" + sumInt);
        System.out.println("summingLong=" + sumLong);
        System.out.println("summingDouble=" + sumDouble);
        System.out.println("averagingInt=" + averageInt);
        System.out.println("averagingLong=" + averageLong);
        System.out.println("averagingDouble=" + averageDouble);
    }
}
```

Chạy với JDK 17 trở lên (mã chỉ dùng những API đã có trong Java 8):

```bash
javac CollectorBasicsDemo.java
java CollectorBasicsDemo
```

Kết quả:

```text
count=4
summingInt=100
summingLong=100
summingDouble=100.0
averagingInt=25.0
averagingLong=25.0
averagingDouble=25.0
```

Giải thích từng phần:

1. `counting()` đếm bốn phần tử, nên kết quả `4L`.
2. Với `summingInt(Integer::intValue)`, mỗi phần tử `Integer` được lấy giá trị `int` rồi cộng lại: `10 + 20 + 30 + 40 = 100`.
3. `summingLong` và `summingDouble` cũng cộng các giá trị được mapper chuyển thành `long` hoặc `double`; kiểu kết quả tương ứng là `Long` và `Double`.
4. Ba `averaging...` lấy tổng các giá trị tương ứng chia cho số phần tử đã được tính: `100 / 4 = 25.0`.
5. Mỗi lời gọi `numbers.stream()` tạo **stream mới**. Không thể dùng lại cùng một stream sau khi nó đã chạy terminal operation `collect`.

Đối với `List<Integer>`, `Integer::intValue` là mapper tự nhiên. Với danh sách các đối tượng nghiệp vụ, mapper thường là method reference như `Sale::getQuantity` hoặc lambda `sale -> sale.getQuantity()`.

## 4. counting(): đếm cái gì, dùng khi nào?

### 4.1. Đếm sau filter và distinct

Giả sử danh sách chứa các trạng thái `["OPEN", "CLOSED", "OPEN", "OPEN"]`:

```java
// Đoạn minh họa; biến statuses được định nghĩa ở đây.
java.util.List<String> statuses =
    java.util.Arrays.asList("OPEN", "CLOSED", "OPEN", "OPEN");

long openCount = statuses.stream()
    .filter("OPEN"::equals)
    .collect(java.util.stream.Collectors.counting()); // 3

long distinctStatuses = statuses.stream()
    .distinct()
    .collect(java.util.stream.Collectors.counting()); // 2
```

Sau `filter`, chỉ ba phần tử `OPEN` được đưa tới collector. Sau `distinct`, stream chỉ còn hai giá trị phân biệt, nên `counting()` trả `2`. Nếu stream còn chứa `null`, `counting()` vẫn tính `null` như một phần tử; việc lọc hay loại bỏ `null` cần được chỉ định riêng.

### 4.2. So sánh counting() với Stream.count()

Nếu chỉ cần một số lượng trên toàn bộ stream:

```java
// Đoạn minh họa cho biến numbers ở ví dụ 1.
long count = numbers.stream().count();
```

Đây là cách trực tiếp và thường dễ đọc hơn `numbers.stream().collect(Collectors.counting())`. Đặc biệt, `Stream.count()` có thể khai thác thông tin kích thước của nguồn và pipeline trong một số trường hợp để tối ưu.

**Chọn `Collectors.counting()` khi nó là downstream collector của `groupingBy`, `partitioningBy` hoặc một collector tổng hợp khác**, ví dụ đếm số đơn hàng trong từng khu vực. Đây là lý do chính khiến `counting()` rất hữu ích dù Stream đã có `count()`.

## 5. summingInt, summingLong, summingDouble

Ba phép `summing...` đều yêu cầu **mapper**, không tự biết phải lấy trường số nào của đối tượng đầu vào.

- **`summingInt(Sale::getQuantity)`:** phù hợp khi tính tổng số lượng mà tổng chắc chắn nằm trong phạm vi `int`.
- **`summingLong(Sale::getRevenue)`:** phù hợp khi doanh thu hoặc số lượng tích lũy được mô tả bằng `long`, đặc biệt khi số tổng có thể vượt `Integer.MAX_VALUE`.
- **`summingDouble(Sale::getRating)`:** phù hợp với số đo thực như điểm số, nhiệt độ hoặc các đại lượng chấp nhận sai số số chấm động.

Mapper phải đưa ra giá trị số có ý nghĩa với phép tổng hợp. Chẳng hạn, nếu có nhiều đơn hàng bị hủy, hãy lọc chúng trước `collect`, hoặc thể hiện quy tắc nghiệp vụ trong mapper. Không nên giả định mọi bản ghi đều có dữ liệu hợp lệ.

**Một phép tổng không phải tự động là phép tính tiền chính xác.** Kiểu `double` dùng biểu diễn nhị phân và có sai số làm tròn. Khi cần độ chính xác thập phân theo quy tắc kế toán, có thể dùng `BigDecimal` cùng `reduce(BigDecimal.ZERO, BigDecimal::add)` hoặc một collector được thiết kế cho `BigDecimal`; không có `Collectors.summingBigDecimal` tiêu chuẩn.

## 6. averagingInt, averagingLong, averagingDouble

Cả ba phép này tính **trung bình cộng số học** của giá trị mapper trên các phần tử được đưa đến collector:

```text
average = tổng giá trị được lấy ra / số phần tử được lấy ra
```

Đây là **trung bình theo từng phần tử**, không phải trung bình có trọng số. Ví dụ có hai đơn hàng với `rating = 5` và `rating = 3`, `averagingDouble` cho `4.0` dù đơn thứ nhất có 100 sản phẩm và đơn thứ hai có 1 sản phẩm. Nếu nghiệp vụ yêu cầu *trung bình theo số sản phẩm*, phải tự xác định công thức tổng có trọng số chia tổng trọng số.

### Vì sao trả Double?

Trung bình cộng có thể là số thập phân dù đầu vào là số nguyên. Ví dụ `1` và `2` cho trung bình `1.5`. Do đó, `averagingInt`/`averagingLong` không trả về `Integer`/`Long`.

### Khi nào kết quả bằng 0.0 dễ gây hiểu nhầm?

Collector `averaging...` trả `0.0` khi stream rỗng. Nhưng `0.0` cũng có thể là trung bình hợp lệ của dữ liệu thật, ví dụ `[-1, 1]`. Nếu ứng dụng cần phân biệt **“không có dữ liệu”** với **“trung bình bằng 0”**, hãy giữ thêm count, sử dụng primitive stream `average()` trả `OptionalDouble`, hoặc dùng `summarizingInt/Long/Double` để nhận đồng thời count và average.

## 7. Ví dụ 2 — dùng downstream collectors với groupingBy

Đây là tình huống thực tế quan trọng: **cùng các collector, nhưng tính riêng cho từng nhóm**. Ví dụ sau có bốn giao dịch ở hai khu vực. Để stdout có thứ tự nhóm ổn định và dễ so sánh, ví dụ dùng `TreeMap::new` làm supplier cho kết quả `groupingBy`.

Tạo file **SalesGroupingDemo.java**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class SalesGroupingDemo {
    static final class Sale {
        private final String region;
        private final int quantity;
        private final long revenue;
        private final double rating;

        Sale(String region, int quantity, long revenue, double rating) {
            this.region = region;
            this.quantity = quantity;
            this.revenue = revenue;
            this.rating = rating;
        }

        String getRegion() {
            return region;
        }

        int getQuantity() {
            return quantity;
        }

        long getRevenue() {
            return revenue;
        }

        double getRating() {
            return rating;
        }
    }

    public static void main(String[] args) {
        List<Sale> sales = Arrays.asList(
            new Sale("North", 2, 100L, 4.0),
            new Sale("South", 3, 200L, 5.0),
            new Sale("North", 5, 300L, 3.0),
            new Sale("South", 1, 100L, 4.0)
        );

        Map<String, Long> countByRegion = sales.stream()
            .collect(Collectors.groupingBy(
                Sale::getRegion,
                TreeMap::new,
                Collectors.counting()
            ));

        Map<String, Integer> quantityByRegion = sales.stream()
            .collect(Collectors.groupingBy(
                Sale::getRegion,
                TreeMap::new,
                Collectors.summingInt(Sale::getQuantity)
            ));

        Map<String, Long> revenueByRegion = sales.stream()
            .collect(Collectors.groupingBy(
                Sale::getRegion,
                TreeMap::new,
                Collectors.summingLong(Sale::getRevenue)
            ));

        Map<String, Double> ratingByRegion = sales.stream()
            .collect(Collectors.groupingBy(
                Sale::getRegion,
                TreeMap::new,
                Collectors.averagingDouble(Sale::getRating)
            ));

        System.out.println("count=" + countByRegion);
        System.out.println("quantity=" + quantityByRegion);
        System.out.println("revenue=" + revenueByRegion);
        System.out.println("rating=" + ratingByRegion);
    }
}
```

```bash
javac SalesGroupingDemo.java
java SalesGroupingDemo
```

Đầu ra:

```text
count={North=2, South=2}
quantity={North=7, South=4}
revenue={North=400, South=300}
rating={North=3.5, South=4.5}
```

**Cách đọc kết quả:**

- `countByRegion`: mỗi khu vực có **2 giao dịch**, không phụ thuộc số sản phẩm trong giao dịch.
- `quantityByRegion`: `North = 2 + 5 = 7` và `South = 3 + 1 = 4`.
- `revenueByRegion`: `North = 100 + 300 = 400` và `South = 200 + 100 = 300`.
- `ratingByRegion`: trung bình **theo số giao dịch**: `North = (4.0 + 3.0) / 2 = 3.5`, `South = (5.0 + 4.0) / 2 = 4.5`.

`groupingBy` tạo một nhóm cho mỗi giá trị khóa `region`. Với mỗi nhóm, collector downstream tổng hợp các phần tử trong nhóm. Khi dùng overload mặc định `groupingBy(classifier, downstream)`, không nên dựa vào thứ tự duyệt của `Map`; cách dùng `TreeMap::new` ở trên khiến việc in kết quả theo thứ tự khóa có thể dự đoán được.

Bốn biến được tính từ **bốn stream độc lập** (bốn lượt duyệt `sales`). Với dữ liệu lớn cần nhiều chỉ số cùng lúc, `summarizingInt/Long/Double` hoặc thiết kế một collector tổng hợp có thể tránh duyệt lại dữ liệu. Không bắt buộc phải tối ưu khi bài toán nhỏ và cách viết tách rời dễ hiểu hơn.

**Một nhóm vắng mặt khác nhóm có giá trị 0:** nếu toàn bộ bản ghi của khu vực `East` bị lọc bỏ trước `groupingBy`, `Map` thông thường sẽ không có khóa `East`. Điều đó khác với stream rỗng khi gọi trực tiếp `summingInt` trả 0.

## 8. Ví dụ 3 — đầu vào rỗng và khác biệt với OptionalDouble

Tạo file **EmptyCollectorsDemo.java**:

```java
import java.util.Collections;
import java.util.List;
import java.util.stream.Collectors;

public class EmptyCollectorsDemo {
    public static void main(String[] args) {
        List<Integer> empty = Collections.emptyList();

        long count = empty.stream()
            .collect(Collectors.counting());

        int sum = empty.stream()
            .collect(Collectors.summingInt(Integer::intValue));

        double average = empty.stream()
            .collect(Collectors.averagingInt(Integer::intValue));

        System.out.println("count=" + count);
        System.out.println("sum=" + sum);
        System.out.println("average=" + average);

        System.out.println("primitiveAverage=" +
            empty.stream().mapToInt(Integer::intValue).average());
    }
}
```

```bash
javac EmptyCollectorsDemo.java
java EmptyCollectorsDemo
```

Đầu ra:

```text
count=0
sum=0
average=0.0
primitiveAverage=OptionalDouble.empty
```

Ở đây, `Collectors.averagingInt` định nghĩa kết quả mặc định là `0.0` khi không có phần tử. Ngược lại, `IntStream.average()` trả `OptionalDouble.empty`, buộc người dùng xử lý trường hợp không có dữ liệu một cách tường minh. Cả hai đều hợp lệ, nhưng phục vụ hai cách thiết kế API khác nhau.

Ví dụ báo cáo nên xem xét cả hai cột `count` và `average` để không trình bày `0.0` của nhóm rỗng thành điểm số có thật.

## 9. Khi cần nhiều chỉ số cùng lúc: summarizingInt/Long/Double

`Collectors.summarizingInt(mapper)` cung cấp `IntSummaryStatistics` gồm `count`, `sum`, `min`, `max` và `average` trong một phép thu thập. Hai biến thể tương tự là `summarizingLong` và `summarizingDouble`.

Tạo file **SummaryAndOverflowDemo.java**:

```java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.stream.Collectors;

public class SummaryAndOverflowDemo {
    public static void main(String[] args) {
        List<Integer> values = Arrays.asList(10, 20, 30);

        IntSummaryStatistics stats = values.parallelStream()
            .collect(Collectors.summarizingInt(Integer::intValue));

        System.out.println("summaryCount=" + stats.getCount());
        System.out.println("summarySum=" + stats.getSum());
        System.out.println("summaryMin=" + stats.getMin());
        System.out.println("summaryMax=" + stats.getMax());
        System.out.println("summaryAverage=" + stats.getAverage());

        List<Integer> large = Arrays.asList(Integer.MAX_VALUE, 1);

        System.out.println("intOverflow=" +
            large.stream().collect(
                Collectors.summingInt(Integer::intValue)));

        System.out.println("longSum=" +
            large.stream().collect(
                Collectors.summingLong(Integer::longValue)));
    }
}
```

```bash
javac SummaryAndOverflowDemo.java
java SummaryAndOverflowDemo
```

Đầu ra:

```text
summaryCount=3
summarySum=60
summaryMin=10
summaryMax=30
summaryAverage=20.0
intOverflow=-2147483648
longSum=2147483648
```

**Giải thích:**

- `IntSummaryStatistics.getCount()` trả `long` và `getSum()` cũng trả `long`. Điều này có thể phù hợp hơn `summingInt` nếu tổng các giá trị `int` vượt quá phạm vi `int`.
- Hai số `Integer.MAX_VALUE` (2.147.483.647) và `1` cộng lại vượt `int`, nên `summingInt` cho kết quả tràn `-2147483648` theo quy tắc số nguyên Java.
- `summingLong(Integer::longValue)` lấy giá trị `long` ngay từ mapper nên tổng vẫn là `2147483648` trong ví dụ.
- **`long` cũng có giới hạn**: `summingLong`, `averagingLong` hoặc tổng `long` trong thống kê có thể tràn nếu giá trị tích lũy vượt miền biểu diễn. Không nên suy ra kiểu `long` không bao giờ tràn.
- `IntSummaryStatistics` có trạng thái thay đổi nội bộ để tổng hợp dữ liệu. Điều đó **không** làm `collect` sai khi dùng parallel stream: cơ chế collection quản lý các vùng chứa trung gian theo hợp đồng của nó. Tuy nhiên, bản thân một đối tượng `IntSummaryStatistics` không mặc nhiên là thread-safe nếu được chia sẻ và gọi `accept` trực tiếp từ nhiều thread.

Nếu dữ liệu đã là `IntStream`, có thể cân nhắc `IntStream.summaryStatistics()` để lấy đối tượng cùng loại mà không cần gọi `collect(Collectors.summarizingInt(...))`.

## 10. Lưu ý về độ chính xác số và dữ liệu nghiệp vụ

### 10.1. Tràn số nguyên

`summingInt` trả `Integer`, nên tổng lớn có thể overflow. Chọn `summingLong` ngay khi phép tổng có thể vượt `Integer.MAX_VALUE`. Với dữ liệu `long` cực lớn hoặc bài toán yêu cầu chính xác tuyệt đối vượt `long`, cần kiểu số hoặc thuật toán phù hợp hơn, như `BigInteger`/`BigDecimal`. Không chờ đến khi kết quả tràn mới phát hiện sai.

### 10.2. Sai số số chấm động và NaN

`summingDouble` và `averagingDouble` dựa trên phép cộng các số `double`. Tổng/trung bình có thể bị ảnh hưởng bởi sai số làm tròn; thứ tự gom các phần tử, đặc biệt trong phép thu thập song song, có thể ảnh hưởng các chữ số cuối. Collector không cam kết tính toán thập phân chính xác tuyệt đối.

Nếu mapper tạo `Double.NaN` hoặc việc cộng gây `NaN`, kết quả tổng/trung bình có thể là `NaN`. Các giá trị vô cực cũng cần được xử lý theo quy tắc nghiệp vụ thay vì xem là số đo bình thường.

### 10.3. Trung bình không có trọng số

`averagingDouble(Product::getUnitPrice)` tính trung bình **mỗi bản ghi một trọng số bằng nhau**. Nó không phải `tổng doanh thu / tổng số sản phẩm` khi mỗi bản ghi có số lượng khác nhau. Đối với trung bình có trọng số, phải xác định công thức phù hợp, ví dụ `sum(quantity * unitPrice) / sum(quantity)`, xử lý trường hợp tổng trọng số bằng 0 và chọn kiểu số đủ chính xác.

### 10.4. Khi tính tiền: BigDecimal

Java không cung cấp collector `summingBigDecimal` dựng sẵn. Với số tiền thập phân, có thể rút gọn bằng `BigDecimal::add` và tự định nghĩa quy tắc làm tròn cho trung bình.

Tạo file **MoneyDemo.java**:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Arrays;
import java.util.List;

public class MoneyDemo {
    public static void main(String[] args) {
        List<BigDecimal> amounts = Arrays.asList(
            new BigDecimal("10.25"),
            new BigDecimal("0.75")
        );

        BigDecimal total = amounts.stream()
            .reduce(BigDecimal.ZERO, BigDecimal::add);

        BigDecimal average = total.divide(
            BigDecimal.valueOf(amounts.size()),
            2,
            RoundingMode.HALF_UP
        );

        System.out.println("total=" + total);
        System.out.println("average=" + average);
    }
}
```

```bash
javac MoneyDemo.java
java MoneyDemo
```

Đầu ra:

```text
total=11.00
average=5.50
```

Trong ví dụ, danh sách đã có hai phần tử nên mẫu số khác 0. Với dữ liệu thật, cần xử lý danh sách rỗng trước phép chia. Cũng nên tạo `BigDecimal` từ chuỗi thập phân hoặc giá trị nguyên phù hợp thay vì `new BigDecimal(0.1)` nếu cần giữ đúng ý nghĩa của số tiền thập phân.

## 11. Chọn collector hay terminal operation trực tiếp?

| Nhu cầu | Cách viết nên cân nhắc | Vì sao |
| --- | --- | --- |
| Chỉ đếm số phần tử của một stream | `stream.count()` | Rõ mục tiêu; không cần collector. |
| Đếm phần tử theo nhóm | `groupingBy(key, counting())` | Mỗi khóa nhận số lượng riêng. |
| Tổng `int` trên stream đã chuyển sang primitive | `intStream.sum()` | Ngắn gọn, tránh boxing của kết quả collector. |
| Tổng một trường số theo nhóm | `groupingBy(key, summingLong(mapper))` | Mapper xác định trường cần cộng; kết quả theo nhóm. |
| Trung bình với tín hiệu “không có dữ liệu” | `intStream.average()` | Trả `OptionalDouble`; rỗng được thể hiện tường minh. |
| Trung bình theo nhóm | `groupingBy(key, averagingDouble(mapper))` | Dễ lồng vào collector nhóm. |
| Count, sum, min, max, average cùng lúc | `summarizingInt/Long/Double(mapper)` | Gom các chỉ số trong một phép thu thập. |
| Tổng số tiền cần chính xác thập phân | `reduce(BigDecimal.ZERO, BigDecimal::add)` | Không chuyển tiền sang `double`. |

**Về hiệu năng và parallel:** Các collector này làm việc với Stream tuần tự hoặc song song và không đòi hỏi tự sửa một biến tổng bên ngoài. Nhưng `parallelStream()` không bảo đảm nhanh hơn; chi phí phân chia, kết hợp và cấu trúc dữ liệu có thể lớn hơn công việc tính tổng/đếm đơn giản. Hãy ưu tiên code dễ hiểu và chỉ tối ưu sau khi đo.

**Về null:** `counting()` đếm phần tử `null` nếu phần tử đó còn trong stream; trong khi một mapper như `Integer::intValue` sẽ gây `NullPointerException` nếu gặp `null`. Dữ liệu có trường số thiếu cần một quy tắc nghiệp vụ rõ ràng: lọc bản ghi, thay bằng giá trị hợp lệ, hay thông báo dữ liệu lỗi. Không tự động coi “thiếu điểm” là `0` rồi tính trung bình nếu điều đó làm sai ý nghĩa.

## 12. Lỗi thường gặp

1. **Nhầm `counting()` với đếm distinct:** `counting()` đếm tất cả phần tử tới collector, kể cả trùng lặp. Nếu mục tiêu là đếm số giá trị duy nhất, cần `distinct()` hoặc cấu trúc `Set` phù hợp.
2. **Dùng `summingInt` cho tổng có thể rất lớn:** `Integer` có giới hạn; xác định miền dữ liệu trước và chọn `summingLong` hoặc kiểu số lớn hơn khi cần.
3. **Tưởng `averagingInt` trả số nguyên:** kết quả là `Double`; ví dụ `1` và `2` cho `1.5`.
4. **Tưởng `averaging...` trả Optional:** collector trả `Double` và dùng `0.0` cho đầu vào rỗng; primitive stream `average()` mới trả `OptionalDouble`.
5. **Dùng `double` cho tiền và kỳ vọng số thập phân chính xác:** `double` không phù hợp khi cần quy tắc kế toán chính xác; cân nhắc `BigDecimal`.
6. **Lấy `averaging...` để tính trung bình có trọng số:** collector tính mỗi phần tử một lần, không tự biết trọng số về số lượng hay doanh thu.
7. **Gọi `collect` nhiều lần trên cùng một instance Stream:** Stream đã tiêu thụ sau terminal operation; tạo stream mới từ nguồn cho lần tính khác.
8. **Sửa một collection bên ngoài trong mapper hoặc collector tùy biến:** side effect và shared mutable state có thể gây lỗi với parallel stream; dùng collector đúng hợp đồng, hoặc viết collector tùy biến có supplier/accumulator/combiner hợp lệ.
9. **Tin vào thứ tự duyệt của `HashMap` do `groupingBy` tạo:** collector không bảo đảm một thứ tự duyệt `Map` nhất định. Nếu cần thứ tự khóa rõ ràng, dùng overload nhận `TreeMap::new` hoặc sắp xếp khi trình bày.
10. **Không xử lý trường hợp nhóm thiếu dữ liệu:** stream rỗng cho `0` hay `0.0`; nhưng nhóm không xuất hiện sau `groupingBy` thường không có entry trong `Map`. Cần phân biệt hai trường hợp khi lên báo cáo.

## 13. Tự kiểm tra

**Câu 1:** `Arrays.asList(2, 4, 6).stream().collect(Collectors.averagingInt(Integer::intValue))` trả kiểu gì và giá trị nào?

**Đáp án:** `Double` với giá trị `4.0`, vì `(2 + 4 + 6) / 3 = 4.0`.

**Câu 2:** `counting()` trả `0L` khi rỗng; vậy `averagingDouble(...)` trả gì?

**Đáp án:** `0.0` (kiểu `Double`), **không phải** `OptionalDouble.empty` và cũng không phải `NaN` theo hợp đồng collector này.

**Câu 3:** Vì sao nên dùng `Collectors.counting()` trong `groupingBy` thay vì gọi `count()` trên từng nhóm thủ công?

**Đáp án:** `counting()` là downstream collector, nên Stream API có thể tự gom và đếm các phần tử cho từng khóa trong một thao tác collect.

**Câu 4:** Tổng `Integer.MAX_VALUE + 1` bằng bao nhiêu nếu dùng `summingInt`? Cần làm gì để tránh sai trong ví dụ?

**Đáp án:** Kết quả tràn thành `-2147483648`; chuyển sang `summingLong(Integer::longValue)` sẽ cho `2147483648` với đầu vào này.

**Câu 5:** Khi nào nên chuyển sang `summarizingInt`?

**Đáp án:** Khi muốn nhận đồng thời `count`, `sum`, `min`, `max` và `average` cho cùng một trường số trong một lần thu thập.

**Câu 6:** Hai nhóm `A` và `B` có giá trị lần lượt `[10, 20]` và `[100]`. Trung bình cộng của toàn bộ ba giá trị là bao nhiêu? Có thể lấy trung bình của trung bình từng nhóm không?

**Đáp án:** Tổng `130` chia `3` bằng khoảng `43.333...`. Trung bình đơn giản của hai trung bình nhóm `15` và `100` sẽ bằng `57.5` và **sai** vì nhóm có kích thước khác nhau. Phải dùng tổng và số lượng (hoặc trung bình có trọng số theo số phần tử) khi gộp kết quả từ các nhóm.

## Tài liệu API

- [Oracle Java SE 25 — `Collectors`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html) — chữ ký và hợp đồng của `counting`, `summing...`, `averaging...` và `summarizing...`.
- [Oracle Java SE 25 — `Stream`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html) — các terminal operation `collect`, `count` và quy tắc xử lý Stream.
- [Oracle Java SE 25 — `IntSummaryStatistics`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/IntSummaryStatistics.html) — thống kê count, sum, min, max, average.
- [Dev.java — Using a Collector as a Terminal Operation](https://dev.java/learn/using-a-collector-as-a-terminal-operation/) — giải thích chính thức về bộ collector thống kê.

**Ghi nhớ:** `counting` đếm phần tử; `summing...` cộng thuộc tính số; `averaging...` tính trung bình cộng và trả `Double`. Chúng đặc biệt hữu ích khi kết hợp với `groupingBy`. Hãy kiểm tra giới hạn kiểu số, dữ liệu rỗng, độ chính xác và ý nghĩa của trung bình trước khi dùng cho báo cáo nghiệp vụ.