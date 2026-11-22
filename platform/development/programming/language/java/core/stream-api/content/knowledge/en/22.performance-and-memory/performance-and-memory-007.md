# Tránh duyệt nguồn nhiều lần và thiết kế tổng hợp trong một lượt

Trong **Java Stream API**, một báo cáo thường cần nhiều chỉ số cùng lúc: số bản ghi, tổng tiền, giá trị nhỏ nhất/lớn nhất, số giao dịch đạt điều kiện và thống kê theo nhóm. Cách dễ viết nhất đôi khi là tạo một stream riêng cho từng chỉ số. Nhưng nếu nguồn lớn, có bước chuẩn hóa tốn CPU, hoặc chỉ có thể đọc **một lần** như tệp hay dữ liệu nhận qua I/O, cách đó có thể lặp lại công việc không cần thiết hoặc không thể thực hiện.

Bài học thuộc chương **Hiệu năng và bộ nhớ** của mô-đun `JAVA_STREAM_API`. Chúng ta sẽ phân biệt “duyệt lại dữ liệu” với “dùng lại một `Stream` đã bị tiêu thụ”, thiết kế **một terminal operation tổng hợp nhiều chỉ số**, nhận diện khi `summarizingLong`, `teeing`, `groupingBy` hoặc `Collector.of` phù hợp, rồi cân nhắc độ chính xác, bộ nhớ, lazy evaluation, song song hóa và cách đo hiệu năng.

> **Nguyên tắc thực hành:** Nếu các chỉ số dùng chung một nguồn và cùng phạm vi dữ liệu, hãy cân nhắc tính chúng trong **một lần thu thập logic**. Nhưng đừng hy sinh tính đúng đắn hoặc sự rõ ràng chỉ để giảm số lần gọi `stream()`; phải so sánh trên workload thật.

## 1. Hiểu đúng “nhiều lần duyệt nguồn”

Với một `List<Long>`, đoạn sau chạy hợp lệ vì **mỗi `stream()` tạo một Stream mới**:

```java
import java.util.List;

List<Long> values = List.of(10L, 20L, 30L, 40L);

long count = values.stream().count();
long sum = values.stream().mapToLong(Long::longValue).sum();
long above20 = values.stream().filter(n -> n > 20).count();

System.out.println(count);   // 4
System.out.println(sum);     // 100
System.out.println(above20); // 2
```

Ở đây có ba terminal operation riêng biệt. Trên nguồn có thể duyệt lại, đây **không phải lỗi API**, nhưng các bước `map`, `filter`, đọc dữ liệu hay tính toán đắt tiền có thể bị lặp lại. Đồng thời, kết quả các lần duyệt có thể **không còn dựa trên cùng một ảnh chụp dữ liệu** nếu collection bị sửa giữa những lần tính.

Ngược lại, đoạn sau là **sai** vì cố dùng lại **cùng một đối tượng Stream**:

```java
import java.util.stream.Stream;

Stream<Integer> numbers = Stream.of(1, 2, 3);
long count = numbers.count();

// Sai: Stream đã được tiêu thụ bởi terminal operation.
// int sum = numbers.mapToInt(Integer::intValue).sum();
// Thường dẫn đến IllegalStateException.
```

Hai khái niệm cần phân biệt:

| Tình huống | Có hợp lệ? | Chi phí/hậu quả |
| --- | --- | --- |
| Gọi `list.stream()` nhiều lần | Có, nếu nguồn cho phép duyệt lại | Có thể xử lý lại cùng dữ liệu và bước chuyển đổi. |
| Gọi nhiều terminal operation trên **cùng Stream** | Không | Stream chỉ được vận hành một lần; có thể ném `IllegalStateException`. |
| Duyệt lại `Files.lines(path)` bằng cách **mở tệp lại** | Có thể, khi mở được nguồn mới và đóng đúng | I/O và parse lặp lại; tệp có thể đã đổi nội dung. |
| Gọi `collect` một lần với nhiều downstream collector | Có | Một pipeline nguồn về mặt logic, nhưng mỗi downstream vẫn thực hiện công việc của nó. |

### “Một lượt” không có nghĩa mỗi lambda bắt buộc được gọi đúng một lần

Stream có thể tối ưu traversal, chẳng hạn `count()` trên một nguồn `SIZED` không cần thực thi mọi `peek`. Các phép ngắn mạch như `findFirst` có thể dừng sớm. Vì vậy, “một lượt” trong bài này nghĩa là **thiết kế một pipeline và một terminal operation để tính các chỉ số từ cùng luồng phần tử**, không phải cam kết về lịch gọi callback, số thread hoặc số lần chạm tới bộ nhớ ở mức thực thi.

## 2. Đặt bài toán thực tế trước khi chọn API

Giả sử có các giao dịch đã được xác thực, mỗi giao dịch có:

- `team`: đội phụ trách, không `null`.
- `amount`: số tiền nguyên theo **đơn vị nhỏ nhất** (ví dụ xu), không âm.
- `paid`: đã thanh toán hay chưa.
- `late`: có xử lý trễ hay không.

Ta muốn xem báo cáo:

| Chỉ số | Phạm vi tính |
| --- | --- |
| Tổng số giao dịch | **Tất cả** giao dịch. |
| Số giao dịch đã thanh toán | Chỉ giao dịch có `paid == true`. |
| Tổng tiền đã thanh toán | Chỉ giao dịch đã thanh toán. |
| Min/max tiền đã thanh toán | Chỉ giao dịch đã thanh toán; không có dữ liệu thì để trống. |
| Số giao dịch đã thanh toán bị trễ | Những giao dịch có cả `paid` và `late`. |
| Các chỉ số trên theo đội | Mỗi đội đã xuất hiện trong nguồn. |

Điểm quan trọng: các chỉ số **không nhất thiết cùng predicate**. Nếu lọc `paid` ngay từ đầu, chúng ta sẽ không còn tính được **tổng số giao dịch**, và đội chỉ có giao dịch chưa thanh toán cũng biến mất khỏi báo cáo.

### Phác thảo pipeline

```text
Stream<Sale>
    |
    +--> classifier: Sale::team
              |
              +--> downstream:
                       tổng số giao dịch
                       giao dịch paid: count / sum / min / max
                       giao dịch paid & late: count
              |
              +--> kết quả bất biến theo đội
    |
    +--> Map<String, TeamReport>
```

Để bắt đầu, nên dùng các collector chuẩn khi chúng đã mô tả được yêu cầu; chỉ viết collector tùy chỉnh khi logic thực sự cần thêm kiểm soát.

## 3. Trường hợp đơn giản: `summaryStatistics` thay cho nhiều terminal operation

Nếu chỉ cần `count`, `sum`, `min`, `max` và `average` cho một trường số, Stream API đã có phép tổng hợp:

```java
import java.util.IntSummaryStatistics;
import java.util.List;

List<Integer> values = List.of(10, 20, 30, 40);

IntSummaryStatistics stats = values.stream()
    .mapToInt(Integer::intValue)
    .summaryStatistics();

System.out.println(stats.getCount());   // 4
System.out.println(stats.getSum());     // 100
System.out.println(stats.getMin());     // 10
System.out.println(stats.getMax());     // 40
System.out.println(stats.getAverage()); // 25.0
```

Đây là **một terminal operation** `summaryStatistics()` của `IntStream`. Trên `Stream<T>`, phiên bản collector tương ứng cho phép kết hợp trong `groupingBy`:

```java
import java.util.List;
import java.util.LongSummaryStatistics;
import java.util.stream.Collectors;

List<Long> amounts = List.of(10L, 20L, 30L, 40L);

LongSummaryStatistics stats = amounts.stream()
    .collect(Collectors.summarizingLong(Long::longValue));

System.out.println(stats.getSum());   // 100
System.out.println(stats.getCount()); // 4
```

| Kiểu nguồn | Phép thống kê | Kết quả |
| --- | --- | --- |
| `IntStream` | `summaryStatistics()` | `IntSummaryStatistics` |
| `LongStream` | `summaryStatistics()` | `LongSummaryStatistics` |
| `DoubleStream` | `summaryStatistics()` | `DoubleSummaryStatistics` |
| `Stream<T>` | `collect(summarizingInt/Long/Double(mapper))` | Tương ứng theo kiểu mapper |

**Giới hạn:** `LongSummaryStatistics` là một đối tượng **mutable**. Cả `sum` và `getAverage()` đều có giới hạn kiểu số; tổng `long` có thể tràn, còn trung bình trả `double` không phải kết quả tiền tệ thập phân chính xác.

Với nguồn rỗng, `getCount() == 0`, `getSum() == 0`, `getAverage() == 0.0`, nhưng `getMin() == Long.MAX_VALUE` và `getMax() == Long.MIN_VALUE`. Hai cực trị đó chỉ là **giá trị khởi tạo**, không phải quan sát. Báo cáo cần biểu diễn **không có min/max** một cách tường minh.

## 4. `Collectors.teeing`: hai phép tổng hợp trên cùng pipeline

`Collectors.teeing` (Java 12+) nhận hai downstream collector và một hàm gộp kết quả:

```java
Collectors.teeing(downstreamA, downstreamB, merger)
```

Mỗi phần tử đi vào collector `teeing` được chuyển cho **cả hai downstream**. Khi kết thúc, `merger` kết hợp hai kết quả. Nó hữu ích khi cần **hai nhánh tổng hợp khác loại** mà không muốn mở lại nguồn.

```java
import java.util.List;
import java.util.stream.Collectors;

record CountAndSum(long count, long sum) {}

CountAndSum report = List.of(10L, 20L, 30L).stream()
    .collect(Collectors.teeing(
        Collectors.counting(),
        Collectors.summingLong(Long::longValue),
        CountAndSum::new
    ));

System.out.println(report); // CountAndSum[count=3, sum=60]
```

Ví dụ này minh họa cú pháp; nếu cùng một trường số, `summarizingLong` đã cho cả count và sum với một bộ thống kê. `teeing` đáng dùng hơn khi hai nhánh mang **ngữ nghĩa khác nhau**, chẳng hạn count toàn bộ và thống kê cho tập con.

### Hai nhánh có điều kiện lọc khác nhau

```java
import java.util.List;
import java.util.stream.Collectors;

record NumberReport(long all, long even) {}

NumberReport report = List.of(1, 2, 3, 4, 5, 6).stream()
    .collect(Collectors.teeing(
        Collectors.counting(),
        Collectors.filtering(
            n -> n % 2 == 0,
            Collectors.counting()
        ),
        NumberReport::new
    ));

System.out.println(report); // NumberReport[all=6, even=3]
```

`Collectors.filtering` (Java 9+) chỉ chuyển phần tử đạt điều kiện cho downstream bên trong. Vì vậy nhánh `all` nhận **mọi phần tử**, còn nhánh `even` chỉ đếm số chẵn. Nếu đưa `.filter(n -> n % 2 == 0)` **trước `collect`**, cả hai nhánh đều mất phần tử lẻ và `all` không còn là tổng số phần tử ban đầu.

**Cần nhớ:** `teeing` có **hai trạng thái tích lũy**, không phải một trạng thái thần kỳ miễn phí. Nó giúp tránh lặp nguồn và các phép biến đổi phía trước, nhưng bản thân mỗi downstream vẫn cần làm công việc riêng.

## 5. Phân nhóm và tổng hợp trong một lượt

`groupingBy(classifier, downstream)` cho phép gộp **phân nhóm** với **thống kê từng nhóm** trong cùng một terminal operation. Không cần gọi `filter` riêng cho từng đội rồi tính count, sum, min, max nhiều lần.

```java
import java.util.List;
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.stream.Collectors;

record Entry(String team, long amount) {}

List<Entry> entries = List.of(
    new Entry("API", 100L),
    new Entry("UI",  300L),
    new Entry("API", 200L)
);

Map<String, LongSummaryStatistics> byTeam = entries.stream()
    .collect(Collectors.groupingBy(
        Entry::team,
        Collectors.summarizingLong(Entry::amount)
    ));

System.out.println(byTeam.get("API").getCount()); // 2
System.out.println(byTeam.get("API").getSum());   // 300
System.out.println(byTeam.get("UI").getMax());    // 300
```

Mỗi phần tử được classifier phân vào **một nhóm**, rồi downstream của nhóm cập nhật thống kê. Bộ nhớ tích lũy tỷ lệ với **số nhóm và trạng thái cần giữ**, thay vì buộc phải lưu toàn bộ phần tử trong mỗi nhóm như `groupingBy(team, toList())`.

Nhưng `groupingBy` chỉ tạo khóa nhóm **đã xuất hiện**. Nếu hệ thống cần hiển thị cả đội không có giao dịch, phải bổ sung danh mục đội và giá trị rỗng theo yêu cầu báo cáo, không tự giả định map đã có mọi khóa.

## 6. Ví dụ hoàn chỉnh: báo cáo nhiều chỉ số theo đội trong một terminal operation

Ví dụ sau dùng **Java 17+** cho `record`, `teeing`, `filtering` và `Map.copyOf`. Dữ liệu đầu vào đã được xác thực `team` khác null và `amount` không âm; ở sản phẩm thật cần chính sách riêng về các bản ghi lỗi.

```java
import java.util.List;
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.OptionalLong;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class OnePassTeamReport {
    record Sale(
        String team,
        String id,
        long amount,
        boolean paid,
        boolean late
    ) {}

    record TeamReport(
        long allCount,
        long paidCount,
        long paidAmount,
        OptionalLong minimumPaid,
        OptionalLong maximumPaid,
        long latePaidCount
    ) {}

    static Map<String, TeamReport> summarize(List<Sale> sales) {
        Collector<Sale, ?, LongSummaryStatistics> paidStats =
            Collectors.filtering(
                Sale::paid,
                Collectors.summarizingLong(Sale::amount)
            );

        Collector<Sale, ?, Long> latePaidCount =
            Collectors.filtering(
                sale -> sale.paid() && sale.late(),
                Collectors.counting()
            );

        Collector<Sale, ?, TeamReport> byTeamCollector =
            Collectors.teeing(
                Collectors.counting(),
                Collectors.teeing(
                    paidStats,
                    latePaidCount,
                    (stats, lateCount) -> new TeamReport(
                        0L, // Sẽ thay bằng allCount ở merger ngoài.
                        stats.getCount(),
                        stats.getSum(),
                        stats.getCount() == 0L
                            ? OptionalLong.empty()
                            : OptionalLong.of(stats.getMin()),
                        stats.getCount() == 0L
                            ? OptionalLong.empty()
                            : OptionalLong.of(stats.getMax()),
                        lateCount
                    )
                ),
                (allCount, partial) -> new TeamReport(
                    allCount,
                    partial.paidCount(),
                    partial.paidAmount(),
                    partial.minimumPaid(),
                    partial.maximumPaid(),
                    partial.latePaidCount()
                )
            );

        return sales.stream()
            .collect(Collectors.collectingAndThen(
                Collectors.groupingBy(Sale::team, byTeamCollector),
                Map::copyOf
            ));
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
            new Sale("API", "A-1", 1200L, true,  false),
            new Sale("API", "A-2",  800L, true,  true),
            new Sale("API", "A-3",  500L, false, true),
            new Sale("UI",  "U-1", 2000L, true,  true),
            new Sale("UI",  "U-2",  700L, false, false),
            new Sale("OPS", "O-1",  300L, false, true)
        );

        Map<String, TeamReport> report = summarize(sales);

        TeamReport api = report.get("API");
        System.out.println(api.allCount());            // 3
        System.out.println(api.paidCount());           // 2
        System.out.println(api.paidAmount());          // 2000
        System.out.println(api.minimumPaid().orElseThrow()); // 800
        System.out.println(api.maximumPaid().orElseThrow()); // 1200
        System.out.println(api.latePaidCount());       // 1

        TeamReport ops = report.get("OPS");
        System.out.println(ops.allCount());            // 1
        System.out.println(ops.paidCount());           // 0
        System.out.println(ops.minimumPaid().isEmpty()); // true
    }
}
```

Luồng xử lý:

1. **Nguồn chỉ tạo một Stream**: `sales.stream()`.
2. `groupingBy(Sale::team, ...)` chia phần tử vào nhóm theo `team`.
3. Nhánh `counting()` đếm **tất cả** giao dịch trong đội.
4. Nhánh `filtering(Sale::paid, summarizingLong(...))` tính thống kê chỉ cho giao dịch đã thanh toán.
5. Nhánh `filtering(sale -> sale.paid() && sale.late(), counting())` đếm giao dịch đã thanh toán và trễ.
6. Các merger của `teeing` ghép kết quả thành `TeamReport` có thành phần bất biến.
7. `collectingAndThen(..., Map::copyOf)` chốt map kết quả thành không sửa đổi được.

**Lưu ý về diễn đạt:** Hai collector `teeing` lồng nhau đúng nhưng có thể dài. Khi yêu cầu tăng lên nhiều chỉ số hoặc có quy tắc nghiệp vụ phức tạp, một `Collector.of` với accumulator riêng thường dễ đọc và kiểm soát chi phí hơn.

**Trường hợp rỗng:** `OPS` vẫn xuất hiện vì có giao dịch, nhưng không có giao dịch `paid`; do đó `paidCount == 0` và min/max dùng `OptionalLong.empty()`. Nếu danh sách `sales` hoàn toàn rỗng thì map đầu ra cũng rỗng.

**Tính bất biến:** `Map.copyOf` làm map không sửa đổi được; `TeamReport` chỉ chứa primitive và `OptionalLong` nên không lộ accumulator mutable. Không suy ra `Map.copyOf` bảo toàn thứ tự duyệt khóa.

## 7. Khi nhiều chỉ số phụ thuộc nhau: `Collector.of`

Đối với nhiều chỉ số, custom collector có thể tích lũy trực tiếp vào **một đối tượng trạng thái**: không cần hai hoặc ba nhánh `teeing` riêng. `Collector.of` phù hợp khi muốn mô tả supplier, accumulator, combiner và finisher rõ ràng.

Ví dụ Java 17+, dùng cùng record `Sale` và `TeamReport` của mục trước. Các đoạn sau là **thành phần bổ sung** nếu đặt trong lớp `OnePassTeamReport`:

```java
static final class Accumulator {
    long allCount;
    long paidCount;
    long paidAmount;
    long latePaidCount;
    long minPaid = Long.MAX_VALUE;
    long maxPaid = Long.MIN_VALUE;

    void add(Sale sale) {
        allCount++;
        if (sale.paid()) {
            paidCount++;
            paidAmount += sale.amount();
            minPaid = Math.min(minPaid, sale.amount());
            maxPaid = Math.max(maxPaid, sale.amount());
            if (sale.late()) {
                latePaidCount++;
            }
        }
    }

    Accumulator combine(Accumulator other) {
        allCount += other.allCount;
        paidCount += other.paidCount;
        paidAmount += other.paidAmount;
        latePaidCount += other.latePaidCount;
        minPaid = Math.min(minPaid, other.minPaid);
        maxPaid = Math.max(maxPaid, other.maxPaid);
        return this;
    }

    TeamReport finish() {
        return new TeamReport(
            allCount, paidCount, paidAmount,
            paidCount == 0L
                ? OptionalLong.empty() : OptionalLong.of(minPaid),
            paidCount == 0L
                ? OptionalLong.empty() : OptionalLong.of(maxPaid),
            latePaidCount
        );
    }
}

static Collector<Sale, Accumulator, TeamReport> metrics() {
    return Collector.of(
        Accumulator::new,
        Accumulator::add,
        Accumulator::combine,
        Accumulator::finish
    );
}
```

Thay downstream `byTeamCollector` ở ví dụ trước bằng `metrics()`:

```java
Map<String, TeamReport> report = sales.stream()
    .collect(Collectors.collectingAndThen(
        Collectors.groupingBy(Sale::team, metrics()),
        Map::copyOf
    ));
```

Ở đây, mỗi phần tử của một nhóm chỉ cần đi qua **một accumulator** để cập nhật toàn bộ chỉ số. Điều này giảm độ phức tạp của nested `teeing`, nhưng **tăng trách nhiệm kiểm chứng** của tác giả collector.

### Luật đúng đắn của combiner

`Collector.of` không chỉ cần accumulator. Khi chạy song song, Stream có thể tạo **nhiều Accumulator độc lập**, rồi dùng combiner để gộp. Phép gộp cần có **tính kết hợp** và trạng thái rỗng làm **identity**:

```text
combine(combine(A, B), C)  ≡  combine(A, combine(B, C))
combine(empty, A)         ≡  A
combine(A, empty)         ≡  A
```

Gộp `count`, `sum`, `min`, `max` như ví dụ phù hợp khi số liệu nằm trong phạm vi kiểu `long` và không có can thiệp ngoài. Nhưng `long` có thể **tràn âm thầm**, vì vậy nếu yêu cầu tổng chính xác ngoài miền `long`, cần kiểm soát giới hạn hoặc dùng `BigInteger`/`BigDecimal`.

**Không** khai báo `Collector.Characteristics.CONCURRENT` cho `Accumulator` này: các trường `long` được cập nhật không đồng bộ, không hỗ trợ nhiều thread cùng gọi `add` trên **một** accumulator. Các collector thông thường vẫn có thể làm việc trên parallel stream nhờ tạo accumulator riêng và gộp đúng. Cũng không khai báo `IDENTITY_FINISH` vì có bước biến trạng thái mutable thành `TeamReport`.

### Khi không nên viết collector tùy chỉnh

Nếu chỉ cần min/max/count/sum/average cho một trường, `summarizingLong` có sẵn **đơn giản hơn và ít rủi ro hơn**. Nếu chỉ thêm đúng một chỉ số điều kiện, `teeing` thường dễ hiểu hơn. Chỉ đầu tư viết và kiểm thử custom collector khi nhu cầu đủ phức tạp hoặc phép đo cho thấy có lợi ích thực tế.

## 8. Nguồn chỉ được đọc một lần: `Files.lines`

Với dữ liệu tệp, mỗi lần mở/đọc lại có thể tốn I/O và có nguy cơ nhìn thấy **phiên bản nội dung khác nhau**. Giả sử tệp chứa **một số tiền nguyên trên mỗi dòng**, đã được xác thực theo định dạng nguồn.

```text
100
200
300
400
```

Có thể tính nhiều chỉ số trong một terminal operation:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.LongSummaryStatistics;
import java.util.stream.Stream;

public class FileStatistics {
    static LongSummaryStatistics readOnce(Path path)
            throws IOException {
        try (Stream<String> lines =
                Files.lines(path, StandardCharsets.UTF_8)) {
            return lines
                .filter(line -> !line.isBlank()) // Java 11+
                .mapToLong(Long::parseLong)
                .summaryStatistics();
        }
    }
}
```

Với nội dung ví dụ, count = 4, sum = 1.000, min = 100, max = 400, average = 250.0. `Files.lines` là một stream gắn với tài nguyên I/O, nên phải dùng **`try-with-resources`**. Terminal operation **không tự thay thế `close()`**.

Đây là cách xử lý **fail-fast** với dữ liệu sai: `Long.parseLong` ném `NumberFormatException` nếu gặp dòng không hợp lệ. Nếu nghiệp vụ cần tiếp tục nhập các dòng còn lại, phải thiết kế kiểu kết quả `Valid/Rejected` và thu cả dữ liệu bị từ chối trong cùng lượt, thay vì chỉ thêm `filter` che giấu lỗi.

**Đừng dùng `Files.lines` như một parser CSV tổng quát**: dấu phẩy trong chuỗi có quote, dòng xuống hàng bên trong trường và encoding phức tạp cần parser chuyên dụng. Tệp có thể bị thay đổi trong khi đọc; một pipeline một lượt **không tự tạo snapshot nguyên tử** của tệp.

## 9. Tách “một lượt qua nguồn” khỏi “một lần tính toán”

Những kỹ thuật sau có đặc điểm khác nhau:

| Thiết kế | Số lần đi qua nguồn về mặt logic | Trạng thái/bộ nhớ đáng chú ý |
| --- | --- | --- |
| `list.stream().filter(...).count()` và `list.stream().mapToLong(...).sum()` | Hai pipeline độc lập | Có thể lặp filter/map và traversal. |
| `list.stream().collect(summarizingLong(...))` | Một pipeline | Một bộ `LongSummaryStatistics`. |
| `collect(teeing(counting(), filtering(...), merger))` | Một pipeline | Hai bộ trạng thái downstream. |
| `collect(groupingBy(key, summarizingLong(...)))` | Một pipeline | Map và bộ thống kê cho mỗi khóa. |
| `collect(groupingBy(key, toList()))`, sau đó thống kê mỗi list | Một pipeline nguồn **nhưng thêm lượt duyệt danh sách nhóm** | Giữ toàn bộ phần tử trong các list. |
| `sorted().collect(...)` | Một pipeline khai báo | Có thể phải buffer/sắp xếp toàn bộ dữ liệu trước khi phát kết quả. |
| `distinct().collect(...)` | Một pipeline khai báo | Cần trạng thái để theo dõi phần tử đã gặp. |

Vì vậy, **một terminal operation chưa đồng nghĩa bộ nhớ O(1)**, và cũng không có nghĩa bên trong pipeline không dùng buffer. `sorted`, `distinct`, `groupingBy(..., toList())` và các collector lưu toàn bộ phần tử có thể tốn nhiều bộ nhớ dù nguồn chỉ được duyệt một lần.

Nếu dữ liệu được lưu thành một collection trung gian để kiểm thử hoặc xử lý lại, điều đó cũng có thể là **một lựa chọn có chủ đích**. Mục tiêu không phải xóa mọi lần duyệt, mà là tránh lặp thao tác **đắt và không cần thiết**.

## 10. Tư duy bộ nhớ: trạng thái tổng hợp hay lưu toàn bộ dữ liệu?

Khi đầu vào có `n` phần tử và `g` nhóm khác nhau:

| Kết quả cần giữ | Độ lớn trạng thái điển hình |
| --- | --- |
| Count, sum, min, max toàn nguồn | O(1) với số chỉ số cố định. |
| Count/sum/min/max theo nhóm | O(g) nếu mỗi nhóm chỉ giữ vài số. |
| Mọi bản ghi theo nhóm `groupingBy(..., toList())` | O(n + g) tham chiếu/bộ chứa, chưa kể đối tượng dữ liệu gốc. |
| Lọc rồi thu `toList()` | O(k) với `k` phần tử được giữ; có thể gần O(n). |
| `sorted()` | Có thể cần O(n) bộ đệm phụ thuộc nguồn/triển khai. |
| `distinct()` | Có thể giữ trạng thái theo số giá trị khác nhau. |

Các biểu thức `O(...)` chỉ mô tả xu hướng, không cam kết số byte chính xác. Object header, boxing, map resizing, số phân vùng khi chạy song song và GC khiến mức sử dụng bộ nhớ thực tế thay đổi.

Một `HashMap` theo nhóm có thể vẫn lớn nếu số khóa **gần bằng số phần tử**. Vì thế, chuyển từ `toList` sang `summarizingLong` thường giảm bộ nhớ khi số nhóm nhỏ, nhưng không giải quyết hoàn toàn vấn đề cardinality rất cao. Khi nguồn vượt khả năng RAM, cần cân nhắc **chia lô, lưu trạng thái ngoài bộ nhớ hoặc kiến trúc xử lý phân tán**, không chỉ thêm `.parallel()`.

## 11. Khi cần cả bản ghi hợp lệ và bản ghi lỗi

Nếu pipeline có bước parse/validate, lời khuyên “làm một lượt” có thể áp dụng với kiểu kết quả trung gian **thành công hoặc thất bại**:

```text
Nguồn -> parseAndValidate -> Result<T>
                              |
                              +-- Valid<T>
                              |
                              +-- Invalid(reason)
                                    |
                           teeing(validCollector,
                                  errorCollector,
                                  Report::new)
```

Điểm lợi là **mỗi hàng chỉ parse một lần**, trong khi `teeing` giữ được cả dữ liệu dùng cho báo cáo lẫn nguyên nhân bị từ chối. Nếu thay vào đó dùng:

```text
source.stream().filter(this::isValid).map(this::parse).collect(...)
source.stream().filter(this::isInvalid).map(this::explain).collect(...)
```

thì các bước kiểm tra/parse có thể lặp, và với nguồn chỉ được tiêu thụ một lần có thể không khả thi. Mặc dù vậy, **không nhất thiết phải materialize tất cả `Result<T>`**; có thể đưa chúng trực tiếp vào downstream collector thích hợp.

Nếu nghiệp vụ phải lưu mọi bản ghi bị từ chối để đối soát, bộ nhớ của danh sách lỗi vẫn tăng theo số lỗi. Một lượt đọc **không xóa nhu cầu lưu trữ thực tế**: có thể cần xử lý theo batch, ghi lỗi ra vùng cách ly hoặc chuyển xuống hệ thống lưu trữ có kiểm soát.

## 12. Lazy evaluation, short-circuit và hiệu ứng phụ

Các intermediate operation như `map`, `filter` và nhiều phép biến đổi khác là **lazy**: chỉ terminal operation mới kích hoạt việc xử lý theo nhu cầu. Nhưng không nên dùng `peek` hay `map` để đếm số phần tử thực sự được gọi:

```java
import java.util.List;

long count = List.of(1, 2, 3)
    .stream()
    .peek(System.out::println)
    .count();

System.out.println(count); // 3
// Không bảo đảm peek in cả ba phần tử.
```

Với nguồn có kích thước xác định, `count()` có thể được tối ưu mà không chạy từng bước không ảnh hưởng kết quả. `findFirst`, `findAny`, `anyMatch`, `limit` có thể **ngắn mạch**, không duyệt toàn nguồn.

Vì thế:

- Không đặt ghi DB, gửi email hay cập nhật counter nghiệp vụ trong `peek`.
- Không kỳ vọng `map` được gọi đúng một lần cho mỗi phần tử nếu terminal operation có thể bỏ qua phép xử lý.
- Không cố sửa nguồn trong `filter` hoặc `forEach` khi pipeline đang hoạt động (*non-interference*).
- Không dùng một `ArrayList` ngoài `parallel().forEach(list::add)` thay cho `collect`.

**Một lượt tổng hợp** chỉ đúng về mặt nghiệp vụ nếu collector và mapper không phụ thuộc những side effect ngoài hợp đồng.

## 13. Parallel stream có thể giúp, nhưng không miễn phí

Trên `parallelStream()`, một collector thông thường có thể tạo các bộ tích lũy độc lập rồi **gộp** bằng combiner. Các phép toán cộng, min và max có thể gộp đúng khi có identity, tính kết hợp và nằm trong miền kiểu số cho phép.

```java
import java.util.LongSummaryStatistics;
import java.util.stream.Collectors;
import java.util.stream.LongStream;

LongSummaryStatistics stats = LongStream.rangeClosed(1, 100_000)
    .parallel()
    .boxed()
    .collect(Collectors.summarizingLong(Long::longValue));

System.out.println(stats.getCount()); // 100000
System.out.println(stats.getSum());   // 5000050000
```

Đoạn code này đúng về tính toán, nhưng không có nghĩa `.parallel()` nên dùng cho mọi dãy số. Thực tế `LongStream.rangeClosed(...).summaryStatistics()` có thể tránh boxing và gọn hơn. Nếu mapper rất rẻ hoặc nguồn nhỏ, chi phí chia nguồn, lập lịch và gộp có thể lớn hơn công việc hữu ích.

**Không dùng accumulator chung** trong collector tùy chỉnh: supplier phải tạo state mới; combiner gộp đúng. Đừng khai báo `CONCURRENT` nếu accumulator không hỗ trợ nhiều thread ghi đồng thời vào cùng state. Nếu các chỉ số cần giữ encounter order, phải xét lại phép gộp và sự lựa chọn collector `UNORDERED`.

Với tổng `double`, thứ tự gộp có thể làm xuất hiện sai khác do làm tròn; một “kết quả hơi khác ở vài bit cuối” không nhất thiết chứng tỏ pipeline sai. Dùng sai số chấp nhận được và chính sách nghiệp vụ khi đánh giá tính đúng.

## 14. Đo hiệu năng: một lượt có thật sự nhanh hơn?

Giảm số lần duyệt nguồn thường có lợi khi pipeline có bước **parse, lọc phức tạp, ánh xạ tốn CPU hoặc I/O**. Nhưng nếu nguồn chỉ là một mảng nhỏ và JVM có thể tối ưu các phép toán rất đơn giản, `teeing` hoặc custom collector có thể có overhead lớn hơn cách viết nhiều pipeline.

Hãy đo theo một thí nghiệm có thể tái lập:

1. **Phiên bản A — nhiều lượt**: tạo stream mới cho mỗi chỉ số, dùng cùng một danh sách bất biến.
2. **Phiên bản B — một `summarizingLong`**: khi bộ năm chỉ số đã đáp ứng yêu cầu.
3. **Phiên bản C — một `teeing` hoặc custom collector**: khi hai/một nhóm nhiều chỉ số có predicate khác nhau.
4. Giữ **cùng tập dữ liệu, cùng quy tắc lọc/parse và cùng đầu ra nghiệp vụ**. Kiểm tra đúng trước khi so thời gian.
5. Đo trên dữ liệu nhỏ, vừa, lớn; thử số nhóm ít/nhiều và phân bố khóa đều/lệch.
6. Dùng **JMH** với warm-up, nhiều measurement/fork, tiêu thụ kết quả, ghi rõ JDK, CPU, số core, heap và GC.

Mẫu bảng **chờ điền số đo thực tế**:

| Workload | Multiple streams (ms/op) | One-pass collectors (ms/op) | Allocation (B/op) | Nhận xét |
| --- | --- | --- | --- | --- |
| 1.000 bản ghi, mapper nhẹ | Đo thực tế | Đo thực tế | Đo thực tế | Có thể overhead chi phối. |
| 1.000.000 bản ghi, mapper nhẹ | Đo thực tế | Đo thực tế | Đo thực tế | Xem băng thông bộ nhớ và tối ưu JVM. |
| 1.000.000 bản ghi, parse nặng | Đo thực tế | Đo thực tế | Đo thực tế | Xem số lần lặp công việc parse. |
| 100.000 bản ghi, 10 nhóm | Đo thực tế | Đo thực tế | Đo thực tế | Bộ nhớ theo nhóm tương đối nhỏ. |
| 100.000 bản ghi, 100.000 nhóm | Đo thực tế | Đo thực tế | Đo thực tế | Map và số nhóm có thể chi phối. |

Không tự điền số liệu giả định rồi gọi đó là kết quả benchmark. Khi so sánh, cần phân biệt **time/op** (nhỏ hơn là tốt hơn) và **throughput** (lớn hơn là tốt hơn); đồng thời xem độ biến thiên giữa các lần đo.

Một lựa chọn có thể nhanh hơn trong microbenchmark nhưng chậm hơn khi nhiều request cùng chạy và tranh chấp CPU/pool. Nếu source có I/O, benchmark CPU thuần không đủ để kết luận về kết nối, timeout và khả năng chịu tải thật.

## 15. Những sai lầm thường gặp

| Cách làm | Vì sao có vấn đề | Hướng xử lý |
| --- | --- | --- |
| Gọi nhiều terminal operation trên **cùng Stream** | Stream đã tiêu thụ không được dùng lại. | Tạo nguồn mới khi hợp lệ, hoặc gộp chỉ số trong một terminal operation. |
| Mở lại tệp cho từng count/sum/min/max | I/O và parse lặp; dữ liệu có thể thay đổi giữa lần đọc. | `Files.lines` + `summaryStatistics` hoặc collector nhiều chỉ số, đóng stream đúng cách. |
| Dùng `groupingBy(key, toList())` chỉ để tính count/sum | Giữ toàn bộ phần tử và duyệt list thêm lần nữa. | `groupingBy(key, counting/summarizingLong)`. |
| Lọc `paid` trước báo cáo cả `allCount` | Mất giao dịch chưa thanh toán trong chỉ số tổng. | Dùng `teeing` và downstream `filtering` theo đúng phạm vi. |
| Coi `getMin()` của bộ thống kê rỗng là dữ liệu | Trả sentinel, không phải quan sát. | Kiểm tra count; dùng `OptionalLong`. |
| Dùng `BigDecimal` không cần thiết cho số đếm, hoặc `double` cho tiền chính xác | Tăng chi phí vô ích hoặc tạo sai số nghiệp vụ. | Chọn kiểu số theo miền dữ liệu và yêu cầu chính xác. |
| Tin “một lượt = O(1) bộ nhớ” | Stateful operations và `toList` vẫn buffer. | Xét lượng trạng thái, cardinality nhóm và kết quả phải giữ. |
| Gọi `parallel()` để chữa vấn đề duyệt nhiều lần | Parallel không tự hợp nhất các pipeline khác nhau. | Thiết kế phép tổng hợp đúng trước, rồi mới đo song song. |
| Dùng mutable identity trong `reduce` để thu list/map | Vi phạm hợp đồng rút gọn và có thể sai khi song song. | Dùng `collect` với supplier/accumulator/combiner hợp lệ. |
| Gắn `CONCURRENT` tùy tiện vào custom collector | Nhiều worker cập nhật chung state có race. | Chỉ khai báo đặc tính thật, hoặc dùng accumulator riêng. |
| Đo bằng một lần `System.nanoTime()` | Nhiễu JIT, GC, scheduling và workload. | Dùng JMH và kiểm tra kết quả tương đương. |

## 16. Bài tập thực hành

**Bài 1 — Tìm các lượt thừa.** Cho một `List<Order>` được tính `count`, `sum`, `min`, `max` bằng bốn stream mới. Viết lại bằng một `summarizingLong(Order::amount)`. Liệt kê điều kiện khiến hai phiên bản tương đương.

**Bài 2 — Phân biệt lỗi reuse.** Giải thích vì sao `list.stream().count()` rồi `list.stream().findFirst()` có thể hợp lệ nhưng `Stream<T> s = list.stream(); s.count(); s.findFirst();` là không hợp lệ.

**Bài 3 — Hai phạm vi.** Từ dữ liệu `Sale(team, amount, paid, late)`, dùng `teeing` để thu `allCount` và `paidCount` trong một terminal operation. Thay `filtering` bằng `Stream.filter` trước `collect`, giải thích kết quả sai khác.

**Bài 4 — Nhiều chỉ số theo nhóm.** Viết `groupingBy(Sale::team, summarizingLong(Sale::amount))`, kiểm tra `API` có count = 2, sum = 300 khi dữ liệu là `API:100`, `API:200`, `UI:50`. Nếu chỉ có một đội chưa từng xuất hiện, map có khóa đó không?

**Bài 5 — Một nhóm không có phần tử đạt điều kiện.** Dùng downstream `filtering(Sale::paid, summarizingLong(...))` cho đội chỉ có sale chưa thanh toán. Vì sao count = 0 còn min/max trả sentinel? Hãy chuyển sang `OptionalLong`.

**Bài 6 — Custom collector.** Viết `Accumulator` giữ count/sum/min/max; chứng minh combiner có identity và tính kết hợp khi không tràn kiểu số. Giải thích tại sao không được trả **một instance accumulator chung** từ supplier.

**Bài 7 — Bộ nhớ.** So sánh `groupingBy(team, toList())` với `groupingBy(team, summarizingLong(...))` cho 1.000.000 giao dịch nhưng chỉ 10 đội. Điều gì thay đổi nếu có tới 1.000.000 đội khác nhau?

**Bài 8 — Đọc tệp một lần.** Đọc tệp chứa số nguyên, bỏ dòng trống và tính `LongSummaryStatistics` trong một `try-with-resources`. Thử thêm một dòng sai định dạng và quyết định nên dừng cả lô hay lưu bản ghi lỗi.

**Bài 9 — Thử hiệu năng.** Benchmark ba thiết kế A/B/C bằng JMH với mapper nhẹ và mapper nặng. Chỉ kết luận sau khi đầu ra tương đương, có warm-up/fork và ghi rõ time/op, allocation và môi trường.

## 17. Checklist trước khi tối ưu

- [ ] Xác định **tất cả chỉ số** cần tính và **phạm vi dữ liệu** của từng chỉ số.
- [ ] Phân biệt **mở nguồn nhiều lần** với **dùng lại cùng Stream** (không hợp lệ).
- [ ] Ưu tiên `summaryStatistics`/`summarizingLong` khi các chỉ số số học đã đủ.
- [ ] Dùng `teeing` khi thật sự có hai downstream khác vai trò; cân nhắc custom collector cho nhiều chỉ số.
- [ ] Phân nhóm với downstream tổng hợp thay vì giữ mọi bản ghi chỉ để thống kê lại.
- [ ] Đặt `filter` và `Collectors.filtering` đúng phạm vi nghiệp vụ.
- [ ] Xử lý nhóm rỗng, min/max thiếu dữ liệu và việc tràn số.
- [ ] Chọn trạng thái tích lũy phù hợp; không làm lộ object mutable nếu báo cáo cần bất biến.
- [ ] Với custom collector, supplier tạo state mới, combiner gộp đúng; không khai báo `CONCURRENT` khi chưa an toàn.
- [ ] Đánh giá **cardinality nhóm, buffering và bộ nhớ** thay vì chỉ đếm số stream.
- [ ] Không dùng side effect trong `peek` hoặc dựa vào số lần lambda chạy.
- [ ] Đóng nguồn I/O bằng `try-with-resources`.
- [ ] Kiểm tra kết quả tuần tự trước khi thử song song.
- [ ] Đo hiệu năng bằng benchmark có kiểm soát, không kết luận từ số đo giả định.

**Ghi nhớ:** Tránh duyệt nguồn nhiều lần không có nghĩa cố nhét mọi phép xử lý vào một lambda lớn. Hãy **thiết kế phép tổng hợp theo đúng phạm vi dữ liệu**, dùng collector sẵn có khi phù hợp, gom các chỉ số bằng `teeing` hoặc accumulator riêng khi cần và trả báo cáo rõ ràng. Một pipeline có một terminal operation vẫn có thể tốn nhiều bộ nhớ; một custom collector vẫn phải đáp ứng hợp đồng khi song song. Lợi ích hiệu năng chỉ đáng tin khi **kết quả đúng, bộ nhớ được kiểm soát và phép đo phản ánh workload thực tế**.

**Tài liệu tham khảo:** [Stream — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Stream.html), [Collectors — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Collectors.html), [LongSummaryStatistics — Java SE 24 API](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/LongSummaryStatistics.html), [JMH — OpenJDK](https://github.com/openjdk/jmh).
