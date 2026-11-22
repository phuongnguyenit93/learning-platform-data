# SummaryStatistics và thu thập nhiều số đo trong Java

## 1. Mục tiêu: một lượt dữ liệu, nhiều thống kê

Trong một hệ thống thực tế, cùng một tập số đo thường cần trả lời nhiều câu hỏi: đã nhận **bao nhiêu** giá trị, **tổng** bao nhiêu, **nhỏ nhất/lớn nhất** là gì, và **trung bình** bao nhiêu? Nếu có nhiều thuộc tính đo (thời gian phản hồi, số byte, nhiệt độ), ta còn muốn tổng hợp tất cả trong một lượt duyệt và, khi cần, chia thống kê theo nhóm.

Java cung cấp ba lớp tích lũy thống kê cơ bản trong gói `java.util`:

- `IntSummaryStatistics`: nhận các giá trị `int`.
- `LongSummaryStatistics`: nhận các giá trị `long`.
- `DoubleSummaryStatistics`: nhận các giá trị `double`.

Cả ba cho các thống kê **count, sum, min, max, average**; hỗ trợ `accept(...)` để nhận thêm một giá trị và `combine(...)` để hợp nhất hai bộ thống kê. Chúng không tự tính phương sai, trung vị, phân vị hay số lượng giá trị phân biệt.

Bài này trình bày hai mức sử dụng: (1) lấy nhiều chỉ số thống kê cho **một dãy số**, (2) thu thập đồng thời nhiều trường đo lường của **một dãy bản ghi**, kể cả khi có giá trị cần loại khỏi một chỉ số.

## 2. Chọn đúng kiểu và hiểu các kết quả

| Đầu vào | Bộ tích lũy | Cách tạo nhanh từ stream | Kiểu `getSum()` |
| --- | --- | --- | --- |
| `int` | `IntSummaryStatistics` | `IntStream.summaryStatistics()` | `long` |
| `long` | `LongSummaryStatistics` | `LongStream.summaryStatistics()` | `long` |
| `double` | `DoubleSummaryStatistics` | `DoubleStream.summaryStatistics()` | `double` |

Các getter đều có ý nghĩa tương tự:

| Getter | Ý nghĩa |
| --- | --- |
| `getCount()` | Số phần tử được đưa vào bộ tích lũy, kiểu `long` |
| `getSum()` | Tổng các phần tử đã nhận |
| `getMin()` | Phần tử nhỏ nhất đã nhận |
| `getMax()` | Phần tử lớn nhất đã nhận |
| `getAverage()` | Trung bình cộng, kiểu `double` |

Ví dụ tối thiểu:

~~~java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

IntSummaryStatistics stats =
        IntStream.of(12, 8, 20, 10).summaryStatistics();

System.out.println(stats.getCount());   // 4
System.out.println(stats.getSum());     // 50
System.out.println(stats.getMin());     // 8
System.out.println(stats.getMax());     // 20
System.out.println(stats.getAverage()); // 12.5
~~~

Đây là **đoạn mã dùng được trong `jshell` hoặc trong một phương thức Java**; ví dụ chương trình độc lập có đủ lớp và `main` ở phần sau.

Không cần duyệt stream năm lần để gọi năm phép `count`, `sum`, `min`, `max`, `average`: chỉ cần một phép `summaryStatistics()`, sau đó đọc các getter trên **cùng một kết quả đã chốt**. Một `Stream` của Java không thể dùng lại sau thao tác kết thúc (terminal operation).

Với `Stream<T>` chứa các đối tượng, dùng các collector của `java.util.stream.Collectors`:

~~~java
// Giả sử đã có Stream<Order> orders và Order có phương thức units().
IntSummaryStatistics stats = orders.collect(
        java.util.stream.Collectors.summarizingInt(Order::units)
);
~~~

Ở đây `Order` là kiểu giả định của ứng dụng, không phải lớp Java chuẩn hay ví dụ chạy độc lập. Các collector tương ứng là `summarizingInt`, `summarizingLong`, `summarizingDouble`.

## 3. Cơ chế hoạt động của bộ tích lũy

Một đối tượng `IntSummaryStatistics` bắt đầu ở trạng thái rỗng; mỗi lần gọi `accept(int)`, nó cập nhật count, sum, min, max. Trung bình được suy ra từ tổng và số lượng khi gọi getter. Nhờ vậy, số lượng ô nhớ bổ sung **không tăng theo số mẫu**: không cần lưu mọi giá trị để tính năm thống kê này.

~~~java
import java.util.IntSummaryStatistics;

IntSummaryStatistics stats = new IntSummaryStatistics();
stats.accept(5);
stats.accept(15);
stats.accept(-5);

System.out.println(stats.getCount());   // 3
System.out.println(stats.getSum());     // 15
System.out.println(stats.getMin());     // -5
System.out.println(stats.getMax());     // 15
System.out.println(stats.getAverage()); // 5.0
~~~

Sau khi nhận thêm giá trị, các getter phản ánh **trạng thái mới**. Do đó, hãy phân biệt rõ:

- **Accumulator**: đối tượng mutable, có thể tiếp tục nhận dữ liệu.
- **Snapshot**: các con số đã sao chép vào DTO/record báo cáo để phát hành cho người tiêu dùng.

Nếu ứng dụng cần một báo cáo bất biến, đừng đưa đối tượng thống kê mutable đang còn được cập nhật cho những phần khác rồi giả định đó là snapshot.

### Hợp nhất các phần đã thu thập

~~~java
IntSummaryStatistics first = new IntSummaryStatistics();
first.accept(2);
first.accept(4);

IntSummaryStatistics second = new IntSummaryStatistics();
second.accept(6);
second.accept(8);

first.combine(second);
System.out.println(first.getCount());   // 4
System.out.println(first.getSum());     // 20
System.out.println(first.getAverage()); // 5.0
~~~

`combine` cập nhật **đối tượng nhận** (`first`) bằng thông tin từ đối tượng còn lại. Nó hữu ích trong pipeline chia dữ liệu thành nhiều phần, nhất là stream song song. Không tự coi các lớp này là thread-safe để nhiều luồng đồng thời gọi `accept` trên **cùng một instance**.

Đối với phép tổng hợp số nguyên thông thường, thứ tự ghép các phần không đổi ý nghĩa toán học nếu không bị tràn. Với số dấu phẩy động `double`, thứ tự cộng có thể làm thay đổi các bit cuối của tổng và trung bình.

## 4. Trạng thái rỗng và cách tránh kết quả gây hiểu nhầm

Nếu không nhận giá trị nào, các getter vẫn trả số chứ không trả `Optional`:

| Lớp | `count` | `sum` | `min` | `max` | `average` |
| --- | ---: | ---: | ---: | ---: | ---: |
| `IntSummaryStatistics` | `0` | `0` | `Integer.MAX_VALUE` | `Integer.MIN_VALUE` | `0.0` |
| `LongSummaryStatistics` | `0` | `0` | `Long.MAX_VALUE` | `Long.MIN_VALUE` | `0.0` |
| `DoubleSummaryStatistics` | `0` | `0.0` | `Double.POSITIVE_INFINITY` | `Double.NEGATIVE_INFINITY` | `0.0` |

Ví dụ:

~~~java
IntSummaryStatistics empty = new IntSummaryStatistics();
System.out.println(empty.getCount()); // 0
System.out.println(empty.getMin());   // 2147483647
System.out.println(empty.getMax());   // -2147483648
~~~

`getAverage() == 0.0` **không có nghĩa** tập dữ liệu có trung bình thực bằng 0 khi `count == 0`. Tương tự, `getMin()` hoặc `getMax()` của bộ rỗng là giá trị sentinel, **không phải phép đo thực**.

Khi xuất báo cáo, hãy luôn xét `getCount() > 0` trước khi trình bày min, max và average. Một API có thể trả `null`, bỏ trường, hoặc dùng một trạng thái `hasData` cho bộ rỗng; lựa chọn nào cũng cần được định nghĩa rõ.

## 5. Tập hợp nhiều số đo từ một bản ghi

Giả sử mỗi bản ghi telemetry có bốn trường:

- `region`: nơi phát sinh mẫu.
- `latencyMs`: độ trễ không âm dưới dạng `int`.
- `bytes`: lượng dữ liệu không âm dưới dạng `long`.
- `temperatureC`: nhiệt độ dưới dạng `double`; hệ thống dùng giá trị không hữu hạn (`NaN`, `±Infinity`) để chỉ mẫu nhiệt độ không hợp lệ.

Báo cáo yêu cầu tổng số dòng, độ trễ (count/min/max/average), tổng byte, nhiệt độ hợp lệ (count/average) và số mẫu nhiệt độ không hợp lệ. **Count của từng đại lượng có thể khác count số dòng** vì có chính sách lọc riêng.

Có thể gọi `stream()` nhiều lần trên cùng một `List` và tạo các báo cáo riêng, nhưng với nguồn chỉ có thể đọc một lần (file streaming, event stream), với dữ liệu lớn hoặc khi muốn kiểm soát chính sách nhất quán, một accumulator chung thuận tiện hơn.

### Chương trình Java 17+ hoàn chỉnh

Lưu mã sau thành `MultiMeasureSummaryDemo.java`:

~~~java
import java.util.DoubleSummaryStatistics;
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.Locale;
import java.util.LongSummaryStatistics;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class MultiMeasureSummaryDemo {

    record Reading(String region, int latencyMs, long bytes,
                   double temperatureC) {}

    static final class Metrics {
        long rows;
        long invalidTemperatures;

        final IntSummaryStatistics latency = new IntSummaryStatistics();
        final LongSummaryStatistics bytes = new LongSummaryStatistics();
        final DoubleSummaryStatistics temperature =
                new DoubleSummaryStatistics();

        void accept(Reading reading) {
            if (reading.latencyMs() < 0 || reading.bytes() < 0) {
                throw new IllegalArgumentException(
                        "latencyMs and bytes must be non-negative");
            }

            rows++;
            latency.accept(reading.latencyMs());
            bytes.accept(reading.bytes());

            if (Double.isFinite(reading.temperatureC())) {
                temperature.accept(reading.temperatureC());
            } else {
                invalidTemperatures++;
            }
        }

        Metrics merge(Metrics other) {
            rows += other.rows;
            invalidTemperatures += other.invalidTemperatures;
            latency.combine(other.latency);
            bytes.combine(other.bytes);
            temperature.combine(other.temperature);
            return this;
        }
    }

    static Collector<Reading, Metrics, Metrics> metricsCollector() {
        return Collector.of(Metrics::new, Metrics::accept, Metrics::merge);
    }

    static void print(String label, Metrics m) {
        System.out.printf(
                Locale.ROOT,
                "%s: rows=%d, latency(count=%d,min=%d,max=%d,avg=%.1f), "
                        + "bytes=%d, temp(count=%d,avg=%.1f), invalid=%d%n",
                label,
                m.rows,
                m.latency.getCount(),
                m.latency.getMin(),
                m.latency.getMax(),
                m.latency.getAverage(),
                m.bytes.getSum(),
                m.temperature.getCount(),
                m.temperature.getAverage(),
                m.invalidTemperatures
        );
    }

    public static void main(String[] args) {
        IntSummaryStatistics simple =
                IntStream.of(2, 4, 6).summaryStatistics();

        System.out.printf(
                Locale.ROOT,
                "simple: count=%d sum=%d min=%d max=%d avg=%.1f%n",
                simple.getCount(),
                simple.getSum(),
                simple.getMin(),
                simple.getMax(),
                simple.getAverage()
        );

        List<Reading> readings = List.of(
                new Reading("North", 10, 100L, 21.5),
                new Reading("North", 20, 300L, 22.5),
                new Reading("South", 30, 200L, Double.NaN),
                new Reading("South", 40, 400L, 19.0)
        );

        Metrics all = readings.stream().collect(metricsCollector());
        print("all", all);

        Map<String, Metrics> byRegion = readings.stream().collect(
                Collectors.groupingBy(
                        Reading::region,
                        TreeMap::new,
                        metricsCollector()
                )
        );

        byRegion.forEach(MultiMeasureSummaryDemo::print);
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~bash
javac MultiMeasureSummaryDemo.java
java MultiMeasureSummaryDemo
~~~

Kết quả stdout:

~~~text
simple: count=3 sum=12 min=2 max=6 avg=4.0
all: rows=4, latency(count=4,min=10,max=40,avg=25.0), bytes=1000, temp(count=3,avg=21.0), invalid=1
North: rows=2, latency(count=2,min=10,max=20,avg=15.0), bytes=400, temp(count=2,avg=22.0), invalid=0
South: rows=2, latency(count=2,min=30,max=40,avg=35.0), bytes=600, temp(count=1,avg=19.0), invalid=1
~~~

### Đọc cấu trúc của collector

`Collector.of` được cung cấp ba thành phần:

1. **Supplier `Metrics::new`**: tạo một accumulator mới.
2. **Accumulator `Metrics::accept`**: cập nhật mọi số đo được giao cho một mẫu; một mẫu chỉ đi qua bộ tích lũy chung một lần.
3. **Combiner `Metrics::merge`**: hợp nhất các phần, quan trọng khi collector được sử dụng với stream song song.

Sau `collect`, `all` là kết quả tổng hợp toàn tập. `groupingBy(Reading::region, TreeMap::new, metricsCollector())` tạo **một accumulator theo từng region**, đưa mỗi bản ghi vào nhóm tương ứng, và dùng `TreeMap` để in nhóm theo thứ tự khóa ổn định trong ví dụ. Với k nhóm, bộ nhớ tích lũy phụ thuộc vào số nhóm k (ngoài nguồn dữ liệu), thay vì phải tạo danh sách mọi bản ghi của mỗi nhóm.

Vì `South` có một nhiệt độ `NaN`, tổng số dòng bằng 4 nhưng số mẫu nhiệt độ hợp lệ chỉ bằng 3. `latency` và `bytes` vẫn đếm cả bốn dòng. **Không được dùng `rows` làm mẫu số cho nhiệt độ** nếu đã loại mẫu nhiệt độ không hợp lệ.

Các trường `rows` và `invalidTemperatures` trong ví dụ cũng là bộ đếm `long`. Với luồng dữ liệu rất lớn, hãy có chính sách phát hiện tràn hoặc chia phiên tổng hợp; `rows++` không tự bảo vệ khỏi tràn số.

## 6. Tình huống chỉ cần tổng hợp một trường theo nhóm

Nếu chỉ quan tâm độ trễ, không cần viết custom collector:

~~~java
Map<String, IntSummaryStatistics> latencyByRegion =
        readings.stream().collect(
                Collectors.groupingBy(
                        Reading::region,
                        Collectors.summarizingInt(Reading::latencyMs)
                )
        );
~~~

**Đây là đoạn trích trong phạm vi `main` của chương trình ở trên**, vì `readings` và `Reading` đã được định nghĩa ở đó.

Tương ứng, `Collectors.summarizingLong(Reading::bytes)` trả `LongSummaryStatistics`; `Collectors.summarizingDouble(Reading::temperatureC)` trả `DoubleSummaryStatistics` (nhưng phải chủ động xử lý `NaN` nếu có trong dữ liệu).

Ví dụ dùng `Collectors.filtering` (Java 9+) để loại bỏ mẫu nhiệt độ không hữu hạn **mà vẫn giữ nhóm**, kể cả nhóm không có nhiệt độ hợp lệ:

~~~java
Map<String, DoubleSummaryStatistics> temperatureByRegion =
        readings.stream().collect(
                Collectors.groupingBy(
                        Reading::region,
                        Collectors.filtering(
                                reading -> Double.isFinite(
                                        reading.temperatureC()),
                                Collectors.summarizingDouble(
                                        Reading::temperatureC)
                        )
                )
        );
~~~

Cần phân biệt `stream().filter(...).collect(groupingBy(...))` với `groupingBy(..., filtering(...))`: cách đầu có thể **bỏ hẳn nhóm** không còn dòng sau lọc; cách sau có thể giữ nhóm với một downstream accumulator rỗng. Hành vi nào phù hợp phụ thuộc ý nghĩa báo cáo.

Nếu muốn gộp hai collector khác loại trong một lượt với Java 12+, `Collectors.teeing` có thể phối hợp hai downstream collector và một hàm kết hợp kết quả. Khi cần ba hoặc nhiều phép đo với điều kiện chấp nhận khác nhau, custom collector như `Metrics` thường rõ ràng hơn.

## 7. Tổng hợp nhiều số đo đúng cách khi chạy song song

Khi sử dụng `parallelStream()` hay `stream().parallel()`, framework có thể tạo nhiều accumulator độc lập rồi gọi combiner để hợp nhất. Đối với custom collector, phải thỏa ba yêu cầu:

- **Accumulator đúng cho từng mẫu**: mỗi `accept` xử lý chính xác các chỉ số và điều kiện lọc của mẫu.
- **Combine đúng về ngữ nghĩa**: `merge` cộng bộ đếm, gọi `combine` cho từng loại thống kê, và trả về trạng thái hợp nhất.
- **Không phụ thuộc thứ tự** nếu muốn kết quả ổn định theo ngữ nghĩa trong parallel; các phép tính `double` vẫn có thể khác các chữ số cuối do thứ tự cộng.

Ví dụ với collector đã khai báo:

~~~java
Metrics parallel = readings.parallelStream()
        .collect(metricsCollector());
~~~

Đây là đoạn trích cùng phạm vi `main` ví dụ hoàn chỉnh. `Collector.of` ở trên **không** khai báo `CONCURRENT`: framework có thể xử lý trên nhiều accumulator riêng rồi merge, thay vì cho nhiều thread cùng sửa một `Metrics`. Tuy nhiên, không được chia sẻ một `Metrics` và gọi `accept` đồng thời từ nhiều thread bên ngoài cơ chế collector nếu không có đồng bộ.

Không tự thêm đặc tính `Collector.Characteristics.CONCURRENT` vào collector mutable này. Với `groupingByConcurrent`, quy tắc container, tính kết hợp và thread safety của downstream cần được xem xét cẩn thận; không thể suy từ việc dùng parallel stream rằng mọi đối tượng thống kê đều thread-safe.

Một custom accumulator có các phép cộng không giao hoán hay phụ thuộc thứ tự (ví dụ ghép chuỗi theo thứ tự đến) sẽ cần thiết kế combiner chặt chẽ hơn. Với cộng số thực, ngay cả khi phép cộng có tính kết hợp trên số thực toán học, **cộng floating point hữu hạn không hoàn toàn kết hợp**; khác biệt nhỏ giữa execution plan có thể xuất hiện.

## 8. Độ chính xác, tràn số và dữ liệu bất thường

### `IntSummaryStatistics` dùng `long` cho tổng

~~~java
IntSummaryStatistics stats = java.util.stream.IntStream
        .of(Integer.MAX_VALUE, Integer.MAX_VALUE)
        .summaryStatistics();

System.out.println(stats.getSum()); // 4294967294
~~~

Tổng không bị giới hạn trong miền `int` ở trường hợp này vì `getSum()` của `IntSummaryStatistics` là `long`. Tuy nhiên, nếu nhận số lượng cực lớn hoặc tổng vượt `Long.MAX_VALUE`/`Long.MIN_VALUE`, kiểu `long` vẫn có thể tràn.

`LongSummaryStatistics` cũng trả tổng `long`, **không** tự nâng thành `BigInteger`. Nếu bài toán cần tổng chính xác không giới hạn miền `long`, hãy thiết kế bộ tích lũy `BigInteger` riêng. Khi tổng thập phân cần chính xác, dùng `BigDecimal` với một accumulator phù hợp, không đưa giá trị qua `double` chỉ để dùng `DoubleSummaryStatistics`.

### `DoubleSummaryStatistics` và sai số dấu phẩy động

`DoubleSummaryStatistics` tính tổng và trung bình từ giá trị `double`. Nó có biện pháp giảm sai số tích lũy trong tính tổng, nhưng vẫn chịu giới hạn binary64; thứ tự nhận/ghép có thể ảnh hưởng đến những chữ số cuối. Nếu dữ liệu tài chính yêu cầu chính xác từng đơn vị nhỏ nhất, đây không phải công cụ thay thế `BigDecimal`.

Nếu chuỗi số đo chứa `NaN`, `DoubleSummaryStatistics` có thể trả `NaN` cho min, max, sum và average. `+Infinity`, `-Infinity` có thể làm kết quả vô hạn hoặc `NaN` (ví dụ khi trộn vô cực trái dấu). Chỉ lọc giá trị không hữu hạn khi **hợp đồng của hệ thống cho phép loại mẫu**; với ứng dụng khác, invalid values nên dẫn đến lỗi hoặc được ghi thành metric lỗi riêng.

Ví dụ một phép lọc thận trọng:

~~~java
DoubleSummaryStatistics validTemperature =
        java.util.stream.DoubleStream.of(
                21.5, Double.NaN, Double.POSITIVE_INFINITY, 22.5
        )
        .filter(Double::isFinite)
        .summaryStatistics();

System.out.println(validTemperature.getCount());   // 2
System.out.println(validTemperature.getAverage()); // 22.0
~~~

Ghi rõ rằng `getCount() == 2` ở đây là số phần tử **đã qua lọc**, không phải số sự kiện thô ban đầu (4).

### Không tính một số đo từ mẫu số không phù hợp

Nếu nguồn có một số trường là tùy chọn hoặc có chính sách lọc riêng, ví dụ 100 bản ghi nhưng chỉ 72 bản ghi có giá trị nhiệt độ hữu hạn, trung bình nhiệt độ phải dùng **72 mẫu nhiệt độ**. Tổng số bản ghi 100 là một chỉ số khác.

Với phân tích cần thêm percentile hoặc median, `SummaryStatistics` không đủ. Tính median/percentile chính xác thường cần giữ thông tin phân phối hoặc cấu trúc dữ liệu hỗ trợ; phương sai và độ lệch chuẩn cũng cần accumulator riêng (chẳng hạn thuật toán online có hỗ trợ merge). Không suy ra những đại lượng này chỉ từ count/sum/min/max/average.

## 9. Thiết kế API và kiểm thử cho báo cáo thống kê

Nên phân biệt dạng **trạng thái thu thập** với dạng **báo cáo đã chốt**. Một DTO có thể trả:

~~~json
{
  "region": "North",
  "rows": 2,
  "latency": {
    "count": 2,
    "minMs": 10,
    "maxMs": 20,
    "averageMs": 15.0
  },
  "bytes": {
    "count": 2,
    "sum": 400
  },
  "temperature": {
    "validCount": 2,
    "averageC": 22.0,
    "invalidCount": 0
  }
}
~~~

Chỉ tạo các trường `min`, `max`, `average` khi `count > 0`, hoặc thống nhất biểu diễn null cho thống kê rỗng. Nếu JSON được dùng với client JavaScript, lưu ý tổng `long` có thể vượt giới hạn số nguyên an toàn của `Number`; với số tổng byte đặc biệt lớn và yêu cầu bảo toàn chính xác, có thể truyền dưới dạng chuỗi decimal kèm schema rõ ràng.

### Bộ kiểm thử nên có

1. **Luồng rỗng:** count = 0, không diễn giải sentinel min/max như phép đo.
2. **Một mẫu:** min = max = giá trị; average tương ứng; sum đúng.
3. **Giá trị âm và dương:** min/max vẫn chính xác.
4. **Nhiều trường với missing/invalid:** mỗi trường có count riêng; tổng dòng vẫn đúng.
5. **Hợp nhất hai accumulator:** tổng hợp từng phần sau `combine` tương đương thống kê của dữ liệu kết hợp, trong giới hạn độ chính xác số thực.
6. **Một nhóm hoàn toàn invalid ở một trường:** nhóm còn tồn tại và thông báo count hợp lệ bằng 0 nếu chính sách downstream giữ nhóm.
7. **Dữ liệu lớn và biên kiểu:** kiểm thử các số `int` lớn, số `long` gần giới hạn và giá trị `double` không hữu hạn.

Mô hình kiểm chứng thủ công cho ví dụ chính: có 4 bản ghi, `latency` bằng 10, 20, 30, 40 nên tổng là 100 và trung bình là 25; byte là 100 + 300 + 200 + 400 = 1000. Ba nhiệt độ hợp lệ 21.5, 22.5, 19.0 có tổng 63.0 và trung bình 21.0; mẫu nhiệt độ thứ tư được báo vào `invalidTemperatures`, không được đưa vào tổng.

## 10. Lỗi phổ biến và cách tránh

- **Duyệt một stream nhiều lần:** `IntStream.sum()` và sau đó `IntStream.average()` trên cùng instance sẽ không hoạt động. Gọi `summaryStatistics()` một lần hoặc tạo lại stream từ nguồn có thể lặp.
- **Tưởng min/max của thống kê rỗng là giá trị thực:** luôn xét count trước.
- **Trộn count dòng với count mẫu hợp lệ:** thu thập số mẫu được dùng của từng chỉ số và số mẫu bị loại.
- **Tin rằng `DoubleSummaryStatistics` chính xác tuyệt đối:** nó xử lý `double`, có thể chịu sai số, `NaN`, vô cực và ảnh hưởng thứ tự cộng.
- **Tin rằng `LongSummaryStatistics.getSum()` không thể tràn:** tổng vẫn là `long`.
- **Dùng một instance mutable chung giữa các thread:** chỉ dùng collector có supplier/combiner đúng hợp đồng, hoặc tự đồng bộ trong kiến trúc concurrent phù hợp.
- **Lọc rồi quên dữ liệu mất mát:** nếu bỏ `NaN`, nên có thêm chỉ số đếm mẫu lỗi/không hợp lệ.
- **Lẫn lộn thống kê mô tả với phép đo phân phối:** bộ `SummaryStatistics` chỉ hỗ trợ các getter có sẵn, không suy ra chính xác median/percentile từ đó.

### Câu hỏi tự kiểm tra

1. Với `IntStream.of(4, 8, 12).summaryStatistics()`, năm getter trả gì?
2. Một nhóm có 5 bản ghi nhưng chỉ 3 nhiệt độ hữu hạn. `getCount()` của `DoubleSummaryStatistics` sau khi lọc nên là bao nhiêu?
3. Có thể gọi `getMin()` cho bộ rỗng không? Nếu có, tại sao không nên công bố nó như kết quả đo?
4. Muốn thống kê độ trễ theo `region` mà không viết accumulator riêng, dùng cặp collector nào?
5. Tại sao muốn tổng chính xác `BigDecimal` thì không nên chuyển tất cả giá trị sang `double` rồi dùng `DoubleSummaryStatistics`?
6. Khi chuyển sang `parallelStream()`, phần nào của custom collector phải chính xác để không làm mất mẫu?

**Đáp án:** (1) count = 3, sum = 24, min = 4, max = 12, average = 8.0. (2) count = 3. (3) Có, nhưng trả sentinel theo kiểu số; cần kiểm tra count = 0. (4) `Collectors.groupingBy(..., Collectors.summarizingInt(...))`. (5) `double` không giữ chính xác mọi số thập phân. (6) Supplier, accumulator và đặc biệt combiner cần bao phủ toàn bộ các trường thống kê và bộ đếm.

Điểm cần ghi nhớ: `SummaryStatistics` giúp **thu thập count/sum/min/max/average trong một lượt**, còn việc thu thập **nhiều trường đo trên cùng bản ghi** có thể xây dựng bằng một collector tổng hợp. Để báo cáo đáng tin, luôn ghi rõ cách lọc từng chỉ số, điều kiện dữ liệu rỗng, giới hạn kiểu số và cách hợp nhất kết quả.
