# Tính chỉ số theo cửa sổ với Gatherer

Trong nhiều bài toán phân tích dữ liệu, một chỉ số không phụ thuộc vào một bản ghi đơn lẻ mà phụ thuộc vào **một nhóm bản ghi liên tiếp**: nhiệt độ trung bình của ba lần đo gần nhất, tổng số giao dịch trong mỗi lô 100 bản ghi, mức dao động giữa hai lần quan sát hoặc tỷ lệ lỗi của từng nhóm sự kiện. Đây là các bài toán **tính chỉ số theo cửa sổ** (*window-based metrics*).

Java Stream API cung cấp `Gatherer` và các phương thức `Gatherers.windowFixed`, `Gatherers.windowSliding` để tạo các cửa sổ trực tiếp trong pipeline. Sau bước `gather`, mỗi cửa sổ là một `List<T>`; từ đó có thể dùng `map`, `reduce`, `collect` hoặc các thao tác thống kê để tạo ra chỉ số theo yêu cầu.

Bài học thuộc chương **Mẫu xử lý dữ liệu thực tế** của mô-đun **JAVA_STREAM_API**. Trọng tâm là hiểu loại cửa sổ, cách ghép từng cửa sổ với phép tổng hợp, xử lý dữ liệu rỗng hoặc không đủ mẫu, đánh đổi giữa cửa sổ theo **số phần tử** và cửa sổ theo **thời gian**, cũng như các giới hạn về thứ tự, trạng thái, hiệu năng và xử lý song song.

> **Yêu cầu phiên bản:** Stream Gatherers được chuẩn hóa từ **Java 24**. Các ví dụ sử dụng `Stream.gather(...)` và `java.util.stream.Gatherers` trong bài này yêu cầu JDK 24 trở lên. Trên JDK 22/23, API này chỉ ở giai đoạn preview với quy tắc bật preview riêng; **Java 17 không có `Stream.gather`**.

## 1. Cửa sổ dữ liệu là gì?

Cửa sổ là một đoạn gồm những phần tử liên tiếp của một Stream có **encounter order**. Sau khi chia thành cửa sổ, thay vì tính một chỉ số chung cho tất cả phần tử, ta tính **một kết quả cho từng cửa sổ**.

Ví dụ chuỗi số đo:

```text
Dữ liệu:           10  20  30  40  50
Cửa sổ rộng 3:    [10  20  30]       → trung bình 20
                      [20  30  40]   → trung bình 30
                          [30  40  50] → trung bình 40
```

Cửa sổ giúp quan sát xu hướng cục bộ thay vì chỉ lấy:

```java
double overallAverage = java.util.stream.Stream
    .of(10, 20, 30, 40, 50)
    .mapToInt(Integer::intValue)
    .average()
    .orElseThrow();

System.out.println(overallAverage); // 30.0
```

**Trung bình toàn bộ bằng 30** không cho biết xu hướng tăng qua từng nhóm ba số đo. Trung bình trượt `[20, 30, 40]` thể hiện tốt hơn diễn tiến của dữ liệu.

### Hai loại cửa sổ cơ bản

| Loại cửa sổ | Đặc điểm | Ví dụ với `[10, 20, 30, 40, 50]`, kích thước 3 |
| --- | --- | --- |
| **Cố định, không chồng lấn** (*fixed / tumbling*) | Gom ba phần tử rồi bắt đầu một nhóm mới | `[10,20,30]`, `[40,50]` |
| **Trượt, chồng lấn** (*sliding*) | Mỗi cửa sổ đầy đủ mới bỏ phần tử cũ nhất, nhận phần tử kế tiếp | `[10,20,30]`, `[20,30,40]`, `[30,40,50]` |

Cả hai loại trên đều chia theo **số phần tử**, không phải theo số giây hoặc phút. Ta sẽ phân biệt điều này với cửa sổ thời gian ở phần sau.

## 2. Các API Gatherer cần dùng

Từ Java 24, `java.util.stream.Gatherers` cung cấp hai factory chính:

```java
public static <TR> Gatherer<TR, ?, List<TR>> windowFixed(
    int windowSize
);

public static <TR> Gatherer<TR, ?, List<TR>> windowSliding(
    int windowSize
);
```

Để áp dụng gatherer, sử dụng `Stream.gather(...)`:

```java
<R> Stream<R> gather(Gatherer<? super T, ?, R> gatherer)
```

Ví dụ:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowFixed(3))
    .toList();

System.out.println(windows); // [[1, 2, 3], [4, 5]]
```

Kiểu dữ liệu chuyển đổi theo pipeline:

```text
Stream<Integer>
    |
    | gather(Gatherers.windowFixed(3))
    v
Stream<List<Integer>>
    |
    | map(window -> chỉ số)
    v
Stream<Metric>
    |
    | toList()
    v
List<Metric>
```

`gather` là **intermediate operation**; nó không tự thực thi toàn bộ pipeline. Terminal operation như `toList()`, `collect(...)`, `forEach(...)` hoặc `count()` sẽ kích hoạt xử lý theo ngữ nghĩa Stream.

### 2.1. Cửa sổ chỉ có ý nghĩa với kích thước hợp lệ

`windowSize` phải lớn hơn hoặc bằng `1`. Truyền `0` hoặc số âm làm factory ném `IllegalArgumentException`.

```java
Gatherers.windowFixed(1);   // Hợp lệ.
Gatherers.windowSliding(5); // Hợp lệ.

// Gatherers.windowFixed(0);   // IllegalArgumentException.
// Gatherers.windowSliding(-2); // IllegalArgumentException.
```

Với dữ liệu từ cấu hình, nên kiểm tra kích thước tại ranh giới API và đặt giới hạn tối đa hợp lý theo bộ nhớ.

### 2.2. Cửa sổ tạo ra là danh sách không thể sửa

Mỗi cửa sổ do hai gatherer dựng sẵn này phát ra là một `List` **không hỗ trợ các phương thức sửa đổi**:

```java
List<Integer> first = Stream.of(1, 2, 3)
    .gather(Gatherers.windowFixed(2))
    .findFirst()
    .orElseThrow();

System.out.println(first); // [1, 2]

// first.add(99); // UnsupportedOperationException.
```

Không phụ thuộc vào lớp triển khai cụ thể của danh sách. Nếu thật sự cần chỉnh sửa một cửa sổ, hãy tạo bản sao mới, chẳng hạn `new ArrayList<>(window)`, thay vì sửa chính `window`.

## 3. `windowFixed`: chỉ số theo từng nhóm không chồng lấn

`Gatherers.windowFixed(k)` tạo các nhóm theo thứ tự gặp, mỗi nhóm có tối đa `k` phần tử. Khi Stream hữu hạn kết thúc, **nhóm cuối có thể ít hơn `k` phần tử**.

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> batches = Stream
    .of(4, 6, 8, 10, 12, 14, 16, 18)
    .gather(Gatherers.windowFixed(3))
    .toList();

System.out.println(batches);
// [[4, 6, 8], [10, 12, 14], [16, 18]]
```

Với `N` phần tử và `k > 0`, số cửa sổ cố định trên một nguồn hữu hạn có thứ tự là:

\[
W_{\mathrm{fixed}}=\left\lceil \frac{N}{k} \right\rceil.
\]

Nếu `N = 0` thì số cửa sổ bằng 0. Với `N = 8` và `k = 3` ta có 3 nhóm.

### 3.1. Tính tổng theo từng lô ba phần tử

```java
import java.util.List;
import java.util.stream.Gatherers;

List<Long> batchTotals = List.of(100L, 200L, 300L, 400L, 500L)
    .stream()
    .gather(Gatherers.windowFixed(3))
    .map(window -> window.stream()
        .mapToLong(Long::longValue)
        .sum())
    .toList();

System.out.println(batchTotals); // [600, 900]
```

Nhóm thứ nhất có tổng `600`; nhóm thứ hai chỉ có hai phần tử nhưng vẫn được phát ra, tổng bằng `900`.

**Phải xác định chính sách với nhóm thiếu phần tử:**

- **Chấp nhận nhóm cuối ngắn hơn:** tính trên số phần tử thực có.
- **Chỉ chấp nhận nhóm đầy đủ:** lọc theo `window.size() == k`.
- **Chưa đủ dữ liệu thì không xuất chỉ số:** thiết kế kết quả trạng thái thiếu mẫu hoặc giữ dữ liệu để xử lý ở lượt sau.

Ví dụ chỉ lấy nhóm đủ ba phần tử:

```java
List<Long> fullBatchTotals = List.of(100L, 200L, 300L, 400L, 500L)
    .stream()
    .gather(Gatherers.windowFixed(3))
    .filter(window -> window.size() == 3)
    .map(window -> window.stream()
        .mapToLong(Long::longValue)
        .sum())
    .toList();

System.out.println(fullBatchTotals); // [600]
```

### 3.2. Đếm tỷ lệ lỗi mỗi lô

Giả sử bản ghi mang trạng thái thành công hoặc lỗi:

```java
record Job(String id, boolean failed) {}
record ErrorRate(long failed, long total, double ratio) {}

List<Job> jobs = List.of(
    new Job("J-1", false),
    new Job("J-2", true),
    new Job("J-3", false),
    new Job("J-4", true),
    new Job("J-5", true)
);

List<ErrorRate> rates = jobs.stream()
    .gather(Gatherers.windowFixed(3))
    .map(window -> {
        long failed = window.stream()
            .filter(Job::failed)
            .count();

        return new ErrorRate(
            failed,
            window.size(),
            (double) failed / window.size()
        );
    })
    .toList();

System.out.println(rates);
// [ErrorRate[failed=1, total=3, ratio=0.3333333333333333],
//  ErrorRate[failed=2, total=2, ratio=1.0]]
```

Mỗi cửa sổ do `windowFixed` phát ra đều không rỗng, vì vậy `window.size()` trong ví dụ không bằng 0. Tuy nhiên, một Stream đầu vào rỗng sẽ **không có cửa sổ nào**; việc tính chỉ số chung cho một nguồn hoàn toàn rỗng phải được định nghĩa ở tầng báo cáo.

## 4. `windowSliding`: chỉ số trượt qua các phần tử liên tiếp

`Gatherers.windowSliding(k)` phát các cửa sổ chồng lấn, mỗi cửa sổ đầy đủ mới bỏ một phần tử cũ nhất rồi thêm một phần tử kế tiếp.

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> windows = Stream
    .of(10, 20, 30, 40, 50)
    .gather(Gatherers.windowSliding(3))
    .toList();

System.out.println(windows);
// [[10, 20, 30], [20, 30, 40], [30, 40, 50]]
```

Với `N >= k`, số cửa sổ trượt bằng:

\[
W_{\mathrm{sliding}}=N-k+1.
\]

Riêng trường hợp `0 < N < k`, API chuẩn phát **một cửa sổ ngắn chứa toàn bộ nguồn**. Nếu `N = 0`, không phát cửa sổ nào. Vì vậy công thức đầy đủ cho nguồn hữu hạn là:

\[
W_{\mathrm{sliding}}=
\begin{cases}
0 & N=0,\\
1 & 0<N<k,\\
N-k+1 & N\ge k.
\end{cases}
\]

### 4.1. Tính trung bình trượt của ba lần đo

```java
import java.util.List;
import java.util.stream.Gatherers;

List<Double> movingAverages =
    List.of(10, 20, 30, 40, 50)
        .stream()
        .gather(Gatherers.windowSliding(3))
        .map(window -> window.stream()
            .mapToInt(Integer::intValue)
            .average()
            .orElseThrow())
        .toList();

System.out.println(movingAverages); // [20.0, 30.0, 40.0]
```

Đây là *simple moving average* (**SMA**) theo **ba phần tử gần nhất**. Mỗi giá trị đầu ra đại diện cho một cửa sổ mà phần tử cuối là quan sát mới nhất của cửa sổ đó.

Đối với một chuỗi có thứ tự `x1, x2, ..., xN` và `k <= N`, chỉ số trung bình ở vị trí `i >= k` là:

\[
\mathrm{SMA}_i=\frac{1}{k}\sum_{j=i-k+1}^{i}x_j.
\]

Ví dụ `x3=30`, `x4=40`, `x5=50` với `k=3` thì `SMA5=(30+40+50)/3=40`.

### 4.2. Phải xử lý riêng trường hợp nguồn ngắn hơn kích thước cửa sổ

```java
List<List<Integer>> shortWindows = List.of(10, 20)
    .stream()
    .gather(Gatherers.windowSliding(3))
    .toList();

System.out.println(shortWindows); // [[10, 20]]
```

Không được giả định rằng `windowSliding(3)` **luôn** trả danh sách ba phần tử. Trên nguồn chỉ có hai phần tử, nó vẫn phát **một cửa sổ gồm hai phần tử**.

Nếu định nghĩa chỉ số bắt buộc phải đủ ba mẫu:

```java
List<Double> fullOnly = List.of(10, 20)
    .stream()
    .gather(Gatherers.windowSliding(3))
    .filter(window -> window.size() == 3)
    .map(window -> window.stream()
        .mapToInt(Integer::intValue)
        .average()
        .orElseThrow())
    .toList();

System.out.println(fullOnly); // []
```

**Quyết định nghiệp vụ cần ghi rõ:** chỉ số khởi đầu tính theo số mẫu hiện có (*warm-up average*) hay chỉ phát sau khi đủ `k` mẫu (*full-window average*)?

## 5. Bảng trường hợp biên của hai gatherer

Giả sử `k = 3`:

| Nguồn | `windowFixed(3)` | `windowSliding(3)` |
| --- | --- | --- |
| `[]` | `[]` | `[]` |
| `[1]` | `[[1]]` | `[[1]]` |
| `[1,2]` | `[[1,2]]` | `[[1,2]]` |
| `[1,2,3]` | `[[1,2,3]]` | `[[1,2,3]]` |
| `[1,2,3,4]` | `[[1,2,3],[4]]` | `[[1,2,3],[2,3,4]]` |
| `[1,2,3,4,5,6]` | `[[1,2,3],[4,5,6]]` | `[[1,2,3],[2,3,4],[3,4,5],[4,5,6]]` |

**Phân biệt quan trọng:** `windowFixed` có thể tạo **cửa sổ cuối thiếu phần tử** ngay cả với nguồn lớn hơn `k`. `windowSliding` chỉ có cửa sổ thiếu phần tử khi **tổng số phần tử của cả nguồn nhỏ hơn `k`**. Khi nguồn dài ít nhất `k` phần tử, mọi cửa sổ trượt phát ra đều đầy đủ.

Các cửa sổ đều bảo toàn thứ tự gặp của các phần tử trong nguồn. Với nguồn có thứ tự, hai gatherer này **không được hiểu là gom nhóm theo khóa** như `Collectors.groupingBy`.

## 6. Chỉ số nào có thể tính trên một cửa sổ?

Sau `gather`, mỗi phần tử downstream là `List<T>`. Vì thế có thể tổng hợp bằng các thao tác thông thường:

| Chỉ số | Gợi ý tính toán | Ý nghĩa |
| --- | --- | --- |
| Số mẫu | `window.size()` | Bao nhiêu quan sát tham gia |
| Tổng | `window.stream().mapToLong(...).sum()` | Tổng khối lượng, số lượng, doanh thu |
| Trung bình | `window.stream().mapToDouble(...).average()` | Mức điển hình trong cửa sổ |
| Nhỏ nhất/lớn nhất | `min()` / `max()` | Giá trị biên cục bộ |
| Tỷ lệ lỗi | `count(failed) / window.size()` | Tỷ lệ bản ghi lỗi trong lô |
| Số giá trị phân biệt | `distinct().count()` | Độ đa dạng của nhóm |
| Biên độ dao động | `max - min` | Độ rộng vùng giá trị quan sát |
| Thay đổi giữa đầu và cuối | `last - first` | Mức biến thiên ở hai đầu cửa sổ |

Ví dụ tính tổng, nhỏ nhất, lớn nhất và trung bình của một cửa sổ:

```java
import java.util.IntSummaryStatistics;

record WindowStats(long count, long sum, int min, int max, double average) {}

List<WindowStats> stats = List.of(4, 8, 6, 12, 10)
    .stream()
    .gather(Gatherers.windowSliding(3))
    .map(window -> {
        IntSummaryStatistics s = window.stream()
            .mapToInt(Integer::intValue)
            .summaryStatistics();

        return new WindowStats(
            s.getCount(), s.getSum(),
            s.getMin(), s.getMax(), s.getAverage()
        );
    })
    .toList();

System.out.println(stats);
// [WindowStats[count=3, sum=18, min=4, max=8, average=6.0],
//  WindowStats[count=3, sum=26, min=6, max=12, average=8.666666666666666],
//  WindowStats[count=3, sum=28, min=6, max=12, average=9.333333333333334]]
```

Trong ví dụ, `IntSummaryStatistics.getSum()` trả `long`. Nhưng `long` vẫn có giới hạn; nếu yêu cầu tổng nguyên chính xác vượt 64 bit, dùng `BigInteger`. Với dữ liệu dấu phẩy động, kết quả trung bình có thể chịu sai số làm tròn nhị phân.

### 6.1. Chỉ số đầu/cuối yêu cầu thứ tự có ý nghĩa

```java
record Change(int start, int end, int delta) {}

List<Change> changes = List.of(100, 105, 98, 120)
    .stream()
    .gather(Gatherers.windowSliding(2))
    .map(window -> {
        int start = window.get(0);
        int end = window.get(window.size() - 1);
        return new Change(start, end, end - start);
    })
    .toList();

System.out.println(changes);
// [Change[start=100, end=105, delta=5],
//  Change[start=105, end=98, delta=-7],
//  Change[start=98, end=120, delta=22]]
```

Ở đây `windowSliding(2)` giúp tính biến động giữa **hai quan sát liên tiếp** mà không cần biến `previous` mutable nằm ngoài pipeline.

## 7. Ví dụ thực tế: chỉ số cảm biến theo cửa sổ trượt

Giả sử thiết bị gửi dữ liệu nhiệt độ, mỗi bản ghi có timestamp và giá trị. Ta cần một báo cáo cho ba lần đo gần nhất: thời điểm cuối, số mẫu, trung bình, nhỏ nhất và lớn nhất.

Để chỉ số có nghĩa, nguồn phải có **thứ tự sự kiện** đúng. Ví dụ này giả định danh sách đã sắp theo thời gian tăng dần.

```java
import java.time.Instant;
import java.util.List;
import java.util.stream.Gatherers;

record Reading(Instant at, double temperature) {}

record TemperatureMetric(
    Instant windowEnd,
    int samples,
    double average,
    double minimum,
    double maximum
) {}

List<Reading> readings = List.of(
    new Reading(Instant.parse("2026-01-01T10:00:00Z"), 20.0),
    new Reading(Instant.parse("2026-01-01T10:01:00Z"), 21.0),
    new Reading(Instant.parse("2026-01-01T10:02:00Z"), 22.0),
    new Reading(Instant.parse("2026-01-01T10:03:00Z"), 25.0),
    new Reading(Instant.parse("2026-01-01T10:04:00Z"), 24.0)
);

List<TemperatureMetric> metrics = readings.stream()
    .gather(Gatherers.windowSliding(3))
    .map(window -> {
        var summary = window.stream()
            .mapToDouble(Reading::temperature)
            .summaryStatistics();

        return new TemperatureMetric(
            window.get(window.size() - 1).at(),
            window.size(),
            summary.getAverage(),
            summary.getMin(),
            summary.getMax()
        );
    })
    .toList();

metrics.forEach(System.out::println);
```

Kết quả có ba chỉ số:

| Cửa sổ | Thời điểm cuối | Trung bình | Min | Max |
| --- | --- | ---: | ---: | ---: |
| `[20,21,22]` | 10:02 UTC | 21.0 | 20.0 | 22.0 |
| `[21,22,25]` | 10:03 UTC | 22.666… | 21.0 | 25.0 |
| `[22,25,24]` | 10:04 UTC | 23.666… | 22.0 | 25.0 |

Trong trường hợp đầu vào thiếu mẫu, `windowSliding(3)` có thể tạo cửa sổ ngắn. Khi đó, `summary.getAverage()` vẫn tính trên số phần tử có thật. Nếu chỉ số cần đủ ba mẫu, thêm:

```java
.filter(window -> window.size() == 3)
```

ngay sau `gather`.

### 7.1. Đọc xu hướng và phát cảnh báo

Có thể kết hợp điều kiện ngay sau khi tính metrics:

```java
List<TemperatureMetric> hotWindows = readings.stream()
    .gather(Gatherers.windowSliding(3))
    .map(window -> {
        var summary = window.stream()
            .mapToDouble(Reading::temperature)
            .summaryStatistics();

        return new TemperatureMetric(
            window.get(window.size() - 1).at(),
            window.size(),
            summary.getAverage(),
            summary.getMin(),
            summary.getMax()
        );
    })
    .filter(metric -> metric.average() > 23.0)
    .toList();

System.out.println(hotWindows.size()); // 1
```

Ở đây điều kiện cảnh báo xét **trung bình cửa sổ** chứ không xét từng bản ghi. `filter(reading -> reading.temperature() > 23)` đặt **trước** bước `gather` sẽ xóa bớt bản ghi nguồn, làm thay đổi chính các cửa sổ và ý nghĩa chỉ số.

## 8. Cửa sổ theo số phần tử khác cửa sổ theo thời gian

Một lỗi nghiệp vụ thường gặp là tưởng `windowSliding(3)` đồng nghĩa “ba phút gần nhất”. Thực tế nó nghĩa là **ba bản ghi gần nhất**.

Xét dữ liệu:

```text
10:00 → 20°C
10:01 → 21°C
10:10 → 22°C
10:11 → 25°C
```

`windowSliding(3)` tạo cửa sổ `[10:00, 10:01, 10:10]`, dù quan sát thứ nhất và thứ ba cách nhau **10 phút**. Nó không kiểm tra timestamp hay tự loại dữ liệu cũ theo thời gian.

| Loại cửa sổ | Cơ sở xác định | Ví dụ |
| --- | --- | --- |
| Theo số phần tử | Số bản ghi theo encounter order | Ba giao dịch gần nhất |
| Theo thời gian xử lý | Đồng hồ khi hệ thống nhận/xử lý bản ghi | Số yêu cầu mỗi phút theo lúc server nhận |
| Theo thời gian sự kiện | Timestamp gắn với sự kiện | Nhiệt độ của 5 phút theo thời điểm đo |

Nếu cần cửa sổ sự kiện kéo dài 5 phút, ứng dụng phải xác định:

- Dữ liệu có được **sắp theo timestamp** chưa?
- Khoảng thời gian lấy theo **[start, end)** hay quy tắc biên nào?
- Sự kiện đến muộn hoặc timestamp trùng nhau được xử lý ra sao?
- Cửa sổ có trượt mỗi 1 phút, mỗi 1 giây hay theo từng sự kiện?
- Có cần watermark, xử lý dữ liệu đến trễ hoặc trạng thái lưu dài hạn không?

Hai factory `windowFixed` và `windowSliding` **không tự cung cấp** các quy tắc thời gian sự kiện này. Với dữ liệu theo thời gian thực phức tạp, có thể cần custom Gatherer, một mô hình quản lý trạng thái theo timestamp hoặc công cụ stream processing chuyên dụng.

### 8.1. Thứ tự nguồn quyết định đúng/sai của chỉ số

Nếu đầu vào chưa sắp theo thời gian, hãy thiết kế bước sắp xếp hoặc quy tắc xử lý riêng:

```java
import java.util.Comparator;

List<TemperatureMetric> sortedMetrics = readings.stream()
    .sorted(Comparator.comparing(Reading::at))
    .gather(Gatherers.windowSliding(3))
    .map(window -> {
        var summary = window.stream()
            .mapToDouble(Reading::temperature)
            .summaryStatistics();

        return new TemperatureMetric(
            window.get(window.size() - 1).at(),
            window.size(),
            summary.getAverage(),
            summary.getMin(),
            summary.getMax()
        );
    })
    .toList();
```

`sorted` trên một tập dữ liệu hữu hạn có chi phí thời gian và bộ nhớ. Không được dùng cách sắp toàn bộ Stream vô hạn mà kỳ vọng xử lý trực tuyến ngay lập tức.

## 9. Chỉ số theo nhóm thiết bị: kết hợp `groupingBy` và Gatherer

Nếu các bản ghi đến từ nhiều thiết bị, không nên trượt cửa sổ trực tiếp trên nguồn **trộn lẫn thiết bị**: cửa sổ có thể chứa nhiệt độ của nhiều cảm biến khác nhau.

Một cách đơn giản cho dữ liệu hữu hạn là gom theo thiết bị, sau đó tính cửa sổ riêng trên từng danh sách nhóm.

```java
import java.time.Instant;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Gatherers;

record DeviceReading(String deviceId, Instant at, double value) {}
record DeviceMetric(Instant endAt, double movingAverage) {}

List<DeviceReading> input = List.of(
    new DeviceReading("A", Instant.parse("2026-01-01T10:00:00Z"), 10.0),
    new DeviceReading("B", Instant.parse("2026-01-01T10:00:00Z"), 90.0),
    new DeviceReading("A", Instant.parse("2026-01-01T10:01:00Z"), 20.0),
    new DeviceReading("B", Instant.parse("2026-01-01T10:01:00Z"), 80.0),
    new DeviceReading("A", Instant.parse("2026-01-01T10:02:00Z"), 30.0)
);

Map<String, List<DeviceMetric>> byDevice = input.stream()
    .collect(Collectors.groupingBy(DeviceReading::deviceId))
    .entrySet().stream()
    .collect(Collectors.toMap(
        Map.Entry::getKey,
        entry -> entry.getValue().stream()
            .sorted(Comparator.comparing(DeviceReading::at))
            .gather(Gatherers.windowSliding(3))
            .map(window -> new DeviceMetric(
                window.get(window.size() - 1).at(),
                window.stream()
                    .mapToDouble(DeviceReading::value)
                    .average()
                    .orElseThrow()
            ))
            .toList()
    ));

System.out.println(byDevice.get("A"));
// [DeviceMetric[endAt=2026-01-01T10:02:00Z, movingAverage=20.0]]

System.out.println(byDevice.get("B"));
// [DeviceMetric[endAt=2026-01-01T10:01:00Z, movingAverage=85.0]]
```

Thiết bị `A` có ba mẫu nên có một cửa sổ đầy đủ. Thiết bị `B` chỉ có hai mẫu và `windowSliding(3)` phát **một cửa sổ ngắn**, trung bình bằng `85.0`. Nếu sản phẩm chỉ hiển thị chỉ số khi đủ ba mẫu thì thêm `filter(window -> window.size() == 3)` vào pipeline của từng nhóm.

**Đánh đổi:** `groupingBy` vật hóa dữ liệu của tất cả nhóm trước khi tính cửa sổ, nên bộ nhớ tăng theo quy mô đầu vào. Khi dữ liệu lớn, đã được phân luồng theo thiết bị hoặc yêu cầu xử lý trực tuyến, cần mô hình khác để tránh giữ toàn bộ lịch sử.

## 10. Chỉ số tài chính: tổng chính xác và quy tắc làm tròn

Với tiền, không nên lấy `double` chỉ vì `mapToDouble` tiện cho việc tính trung bình. Dùng `BigDecimal` khi giá trị có phần thập phân hoặc nghiệp vụ yêu cầu quy tắc làm tròn rõ ràng.

Ví dụ tổng và trung bình theo lô:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.stream.Gatherers;

record Sale(String id, BigDecimal amount) {}
record RevenueMetric(int count, BigDecimal total, BigDecimal average) {}

List<Sale> sales = List.of(
    new Sale("S1", new BigDecimal("10.10")),
    new Sale("S2", new BigDecimal("20.20")),
    new Sale("S3", new BigDecimal("30.30")),
    new Sale("S4", new BigDecimal("40.40"))
);

List<RevenueMetric> metrics = sales.stream()
    .gather(Gatherers.windowFixed(3))
    .map(window -> {
        BigDecimal total = window.stream()
            .map(Sale::amount)
            .reduce(BigDecimal.ZERO, BigDecimal::add);

        return new RevenueMetric(
            window.size(),
            total,
            total.divide(
                BigDecimal.valueOf(window.size()),
                2,
                RoundingMode.HALF_UP
            )
        );
    })
    .toList();

System.out.println(metrics);
// [RevenueMetric[count=3, total=60.60, average=20.20],
//  RevenueMetric[count=1, total=40.40, average=40.40]]
```

Lưu ý: `windowFixed` phát cửa sổ cuối chỉ có một khoản tiền. Đây có thể là đúng nếu đang tính tổng theo lô bán hàng, nhưng có thể không phù hợp nếu chính sách định nghĩa “một chu kỳ quyết toán” luôn gồm đúng ba giao dịch.

Các giá trị đầu vào phải được xác thực trước khi tính. `BigDecimal` giải quyết phép cộng số thập phân chính xác, nhưng không thay thế quy tắc kiểm tra tiền âm, giao dịch hủy, timestamp trùng hoặc đơn vị tiền tệ.

## 11. Tự viết Gatherer: trạng thái và bước hoàn tất của cửa sổ

Hai factory chuẩn phù hợp khi chỉ cần nhận **danh sách các phần tử trong cửa sổ** rồi tính chỉ số. Nhưng với cửa sổ trượt có `k` lớn, việc tạo cửa sổ và duyệt lại toàn bộ `k` phần tử để tính tổng có thể lặp nhiều công việc.

Một lựa chọn nâng cao là viết `Gatherer` với trạng thái riêng: giữ tối đa `k` phần tử trong một `Deque` cùng một tổng đang chạy. Mỗi khi có phần tử mới, bỏ phần tử cũ nhất nếu đã đủ `k`, rồi cập nhật tổng. Đây là mô hình *incremental sliding aggregation*.

### 11.1. Bốn thành phần của Gatherer tùy chỉnh

`Gatherer<T, A, R>` có ba tham số kiểu:

- `T`: kiểu đầu vào, ví dụ `Long`.
- `A`: kiểu trạng thái nội bộ, ví dụ `RunningState`.
- `R`: kiểu đầu ra, ví dụ `Long` là tổng cửa sổ.

Một gatherer có thể định nghĩa:

| Thành phần | Mục đích |
| --- | --- |
| **Initializer** | Tạo trạng thái riêng cho quá trình xử lý |
| **Integrator** | Nhận phần tử mới, cập nhật trạng thái, có thể đẩy một hoặc nhiều kết quả xuống downstream |
| **Combiner** | Ghép hai trạng thái khi muốn cho phép parallelization |
| **Finisher** | Phát đầu ra cuối cùng nếu cần, chẳng hạn cửa sổ ngắn khi nguồn kết thúc |

Khác `Collector`, Gatherer là **thao tác trung gian** có thể phát nhiều kết quả trong khi nhận đầu vào. Nó không chỉ tạo một đối tượng kết quả cuối.

### 11.2. Ví dụ custom Gatherer tính tổng trượt

Đoạn Java 24+ hoàn chỉnh sau tạo `rollingSum(k)` có ngữ nghĩa tương tự `windowSliding(k)` về xử lý số phần tử đầu vào:

- Khi đã có đủ `k` mẫu, phát tổng sau mỗi phần tử mới.
- Nếu nguồn không rỗng nhưng **ngắn hơn `k`**, finisher phát một tổng của tất cả mẫu đã nhận.
- Nếu nguồn rỗng, không phát kết quả.

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.List;
import java.util.stream.Gatherer;

public class RollingSumGathererDemo {

    static final class RunningState {
        final int width;
        final Deque<Long> values = new ArrayDeque<>();
        long sum = 0L;

        RunningState(int width) {
            this.width = width;
        }

        void accept(long value) {
            if (values.size() == width) {
                sum = Math.subtractExact(sum, values.removeFirst());
            }

            values.addLast(value);
            sum = Math.addExact(sum, value);
        }
    }

    static Gatherer<Long, RunningState, Long> rollingSum(int width) {
        if (width < 1) {
            throw new IllegalArgumentException("width must be >= 1");
        }

        return Gatherer.ofSequential(
            () -> new RunningState(width),

            // Integrator: nhận mỗi phần tử rồi phát kết quả khi đủ mẫu.
            (state, value, downstream) -> {
                state.accept(value);

                if (state.values.size() == width) {
                    return downstream.push(state.sum);
                }

                return !downstream.isRejecting();
            },

            // Finisher: phát một cửa sổ ngắn nếu cả nguồn ít hơn width.
            (state, downstream) -> {
                if (!state.values.isEmpty()
                        && state.values.size() < width
                        && !downstream.isRejecting()) {
                    downstream.push(state.sum);
                }
            }
        );
    }

    public static void main(String[] args) {
        List<Long> numbers = List.of(10L, 20L, 30L, 40L, 50L);

        System.out.println(numbers.stream()
            .gather(rollingSum(3))
            .toList()); // [60, 90, 120]

        System.out.println(List.of(10L, 20L).stream()
            .gather(rollingSum(3))
            .toList()); // [30]

        System.out.println(List.<Long>of().stream()
            .gather(rollingSum(3))
            .toList()); // []
    }
}
```

### Vì sao dùng `Gatherer.ofSequential`?

Tổng trượt có **phụ thuộc thứ tự**: để phát đúng cửa sổ tiếp theo, trạng thái phải biết `k - 1` phần tử cuối của đoạn trước. Chỉ cộng tổng của hai nhánh song song không đủ để khôi phục các cửa sổ **băng qua ranh giới nhánh**.

`Gatherer.ofSequential` nói rõ gatherer này xử lý theo mô hình tuần tự, không khai báo một combiner song song không đúng. Dù pipeline nguồn gọi `parallel()`, không được cho rằng việc tính cửa sổ có trạng thái này tự chia được trên nhiều tác vụ.

### Lưu ý quan trọng về tính đúng và độ chính xác

- `Math.addExact` và `Math.subtractExact` **phát hiện tràn `long` bằng ngoại lệ**, không tự mở rộng miền số. Nếu tổng tiền có thể vượt `long` hoặc có rủi ro từ tổng trung gian, hãy dùng `BigInteger` hoặc một bộ tích lũy chính xác hơn.
- Một lần tính `sum` có thể được cập nhật trong thời gian hằng số theo số phép toán số học mỗi phần tử, nhưng `Deque` vẫn giữ tối đa `k` phần tử.
- Tính toán trên cửa sổ trượt theo **dữ liệu đầu vào**; không gắn timestamp cho cửa sổ trừ khi trạng thái có thông tin đó.
- Khi downstream dừng sớm, `downstream.push(...)` báo không muốn nhận thêm bằng kết quả `false`; integrator phải tôn trọng tín hiệu đó.
- Trạng thái chỉ thuộc gatherer đang thực thi; không đặt `Deque` toàn cục dùng chung giữa nhiều Stream.

Ví dụ này phục vụ học thuật. Với ứng dụng thực, cần kiểm thử nhiều độ dài đầu vào, giá trị âm, tràn số, ngắt sớm, thay đổi thứ tự và các trường hợp nguồn có lỗi.

## 12. `gather`, `scan`, `reduce` và `collect` khác nhau thế nào?

Các API có thể cùng xuất hiện trong bài toán tính chỉ số, nhưng có vai trò khác nhau:

| Công cụ | Kết quả chính | Thích hợp khi |
| --- | --- | --- |
| `filter` / `map` | Chọn hoặc biến đổi từng phần tử | Quy tắc độc lập từng phần tử |
| `Gatherers.windowFixed(k)` | `Stream<List<T>>` nhóm không chồng lấn | Chỉ số theo từng lô `k` phần tử |
| `Gatherers.windowSliding(k)` | `Stream<List<T>>` nhóm chồng lấn | Chỉ số của `k` quan sát gần nhất |
| `Gatherers.scan(...)` | Giá trị tích lũy sau mỗi phần tử | Tổng chạy từ đầu, không tự loại phần tử cũ |
| `reduce(...)` | Một giá trị tổng hợp cuối | Chỉ cần tổng/toán tử gộp của toàn bộ nguồn |
| `collect(...)` | Một container hoặc đối tượng kết quả cuối | Gom nhóm, báo cáo tổng thể, Map |
| Custom `Gatherer` | Chuỗi kết quả do trạng thái trung gian điều khiển | Logic cửa sổ/cảnh báo không có sẵn |

### 12.1. Tổng chạy (*running total*) không phải tổng theo cửa sổ trượt

`Gatherers.scan` tính một giá trị tích lũy qua các phần tử từ đầu Stream:

```java
import java.util.List;
import java.util.stream.Gatherers;

List<Long> runningTotals = List.of(10L, 20L, 30L, 40L)
    .stream()
    .gather(Gatherers.scan(
        () -> 0L,
        Long::sum
    ))
    .toList();

System.out.println(runningTotals); // [10, 30, 60, 100]
```

Còn tổng cửa sổ trượt rộng ba:

```java
List<Long> rollingTotals = List.of(10L, 20L, 30L, 40L)
    .stream()
    .gather(Gatherers.windowSliding(3))
    .map(window -> window.stream()
        .mapToLong(Long::longValue)
        .sum())
    .toList();

System.out.println(rollingTotals); // [60, 90]
```

`scan` **không loại phần tử cũ**. `windowSliding` duy trì phạm vi cửa sổ gần nhất. Chúng chỉ cho kết quả giống nhau trong một số trường hợp đặc biệt, không nên thay thế tùy tiện.

### 12.2. `collect` theo nhóm khóa không phải cửa sổ liên tiếp

`Collectors.groupingBy(DeviceReading::deviceId)` gom **mọi bản ghi có cùng khóa**, dù cách nhau nhiều phần tử. Cửa sổ trượt gom **các phần tử liên tiếp theo encounter order**. Có thể kết hợp hai ý tưởng, nhưng phải định nghĩa nhóm nào cần được xét độc lập trước khi tạo cửa sổ.

## 13. Lazy, short-circuit và nguồn hữu hạn/vô hạn

`gather` là intermediate operation và được thực thi khi downstream cần dữ liệu:

```java
import java.util.stream.Gatherers;
import java.util.stream.Stream;

Stream<List<Integer>> pending = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.windowSliding(3)); // Chưa thu thập cửa sổ.

System.out.println(pending.findFirst().orElseThrow());
// [1, 2, 3]
```

Với `findFirst()`, pipeline có thể dừng sau khi nhận một cửa sổ đầy đủ. Đừng dùng các side effect trong `peek`, `map` hoặc integrator để giả định mọi phần tử của nguồn đã được duyệt.

### 13.1. Stream vô hạn và cửa sổ theo phần tử

Với nguồn vô hạn có thứ tự, `windowSliding(3)` có thể phát cửa sổ sau mỗi phần tử kể từ lúc đủ ba mẫu:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<List<Integer>> firstWindows = Stream.iterate(1, n -> n + 1)
    .gather(Gatherers.windowSliding(3))
    .limit(3)
    .toList();

System.out.println(firstWindows);
// [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
```

`limit(3)` giới hạn **số cửa sổ đầu ra**, không phải số phần tử đầu vào. Để phát ba cửa sổ rộng ba, gatherer cần đọc đến ít nhất phần tử nguồn thứ năm.

Nếu bỏ `limit` rồi gọi `toList()` trên một nguồn vô hạn, chương trình không có điểm kết thúc tự nhiên và có thể tiêu thụ tài nguyên vô hạn.

### 13.2. Không tính toán bằng side effect trong lambda

Ví dụ sai:

```java
// Không nên làm: dùng một List mutable ngoài Stream để ghi cửa sổ.
List<List<Integer>> shared = new java.util.ArrayList<>();

Stream.iterate(1, n -> n + 1)
    .limit(100)
    .parallel()
    .gather(Gatherers.windowSliding(3))
    .forEach(shared::add);
```

Một `ArrayList` ngoài pipeline không an toàn cho cập nhật đồng thời. Hãy sử dụng `toList()` hoặc collector thích hợp, để framework quản lý kết quả.

## 14. Xử lý song song và đảm bảo thứ tự

Các cửa sổ có tính **phụ thuộc vào encounter order**. Khi nguồn có thứ tự, thứ tự đó xác định những phần tử nào “liền trước” và “liền sau” nhau.

```java
List<List<Integer>> windows = Stream.of(1, 2, 3, 4, 5)
    .parallel()
    .gather(Gatherers.windowSliding(3))
    .toList();

System.out.println(windows);
// [[1, 2, 3], [2, 3, 4], [3, 4, 5]]
```

Không suy rằng `parallel()` mặc nhiên có lợi: phép tính cửa sổ có chồng lấn đòi hỏi giữ đúng ranh giới giữa các phần được chia. Một gatherer tuần tự có trạng thái có thể hạn chế lợi ích song song; ngay cả khi một gatherer có khả năng chia, việc kết hợp trạng thái và duy trì thứ tự vẫn có chi phí.

### 14.1. Tránh dùng `unordered()` khi thứ tự là ngữ nghĩa

`unordered()` không nhất thiết xáo trộn dữ liệu, nhưng **bỏ yêu cầu về encounter order**. Chỉ số “ba quan sát gần nhất” không có nghĩa xác định nếu đầu vào không có thứ tự rõ ràng.

Nếu nguồn là `HashSet` hoặc pipeline không có thứ tự, hãy xây dựng một thứ tự hợp lệ theo nghiệp vụ trước. Việc ghi một timestamp vào phần tử không làm Stream tự sắp theo timestamp.

### 14.2. Tách độc lập theo thiết bị trước khi song song

Trong bài toán nhiều thiết bị, có thể xử lý **các nhóm thiết bị độc lập** song song ở cấp nhóm, đồng thời giữ bước tính cửa sổ theo thứ tự **bên trong từng nhóm**. Đây là cách phân chia có thể dễ lý giải hơn so với cố song song hóa một chuỗi cửa sổ duy nhất có ranh giới chồng lấn.

Tuy nhiên, nếu đã materialize mọi nhóm trước thì việc đánh đổi bộ nhớ phải được đánh giá. Đừng mặc định đây là phương án tốt nhất cho nguồn dữ liệu vô hạn hoặc truyền liên tục.

## 15. Bộ nhớ, thời gian và độ chính xác

### 15.1. Số cửa sổ có thể rất lớn

Với `N` phần tử và cửa sổ trượt `k` (khi `N >= k`), có `N-k+1` cửa sổ. Ví dụ một triệu phần tử, cửa sổ rộng 100:

\[
1\,000\,000-100+1=999\,901\text{ cửa sổ}.
\]

Nếu `toList()` giữ **tất cả** danh sách cửa sổ, chi phí lưu kết quả có thể rất lớn. Một cửa sổ thường chứa tới `k` tham chiếu phần tử; việc tạo, sao chép hoặc giữ nhiều cửa sổ sẽ gây chi phí thời gian và bộ nhớ. Không nên lưu toàn bộ lịch sử cửa sổ nếu sản phẩm chỉ cần cảnh báo hiện tại hoặc một chỉ số cuối.

**Lựa chọn thiết kế:** tiêu thụ các metrics ngay khi được phát ra, hoặc viết custom Gatherer cập nhật chỉ số tăng dần mà không tạo danh sách mới cho từng cửa sổ.

### 15.2. `windowSize` lớn bất thường vẫn có chi phí

Các gatherer cửa sổ dựng sẵn có thể cấp phát bộ nhớ theo kích thước cửa sổ khá sớm. Vì vậy, một cấu hình `windowSize` cực lớn có thể tốn bộ nhớ ngay cả khi Stream đầu vào ngắn.

Cần đặt ngưỡng cấu hình, kiểm tra k > 0 và thử với các trường hợp `N < k`, `N = k`, `N = k+1` cũng như dữ liệu thực tế.

### 15.3. Độ chính xác chỉ số

- `sum()` trên `IntStream` có thể tràn `int`; `LongStream.sum()` có thể tràn `long`.
- `mapToDouble(...).average()` dùng số thực nhị phân và có sai số làm tròn.
- `BigDecimal` phù hợp cho tiền thập phân với quy tắc làm tròn xác định; `BigInteger` phù hợp cho tổng nguyên lớn.
- Mỗi cửa sổ có thể có số phần tử khác nhau khi nguồn ngắn, nên **mẫu số của trung bình phải là `window.size()`**, không mặc định luôn bằng `k`.
- Nếu dùng phương pháp tổng trượt tăng dần, phép trừ phần tử cũ và cộng phần tử mới phải giữ tính đúng khi tràn, số âm và dữ liệu bất thường.

### 15.4. Đo hiệu năng trước khi tối ưu

Đánh giá thời gian, bộ nhớ, tốc độ cấp phát và số metric phát ra bằng dữ liệu đại diện. Với code Java quan trọng về hiệu năng, có thể dùng JMH. So sánh cả mô hình cửa sổ dựng sẵn và custom Gatherer, đồng thời xác nhận **ngữ nghĩa cửa sổ và quy tắc làm tròn giống nhau** trước khi so tốc độ.

## 16. Dữ liệu I/O và quản lý vòng đời

Một nguồn Stream từ `Files.lines(path)` hoặc tài nguyên I/O tương tự cần đóng. `gather`, `limit` và terminal operation **không tự thay thế `close()`**.

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

// Đặt trong phương thức có throws IOException hoặc xử lý ngoại lệ.
Path file = Path.of("measurements.txt");

try (Stream<String> lines = Files.lines(file)) {
    List<Double> averages = lines
        .filter(line -> !line.isBlank())
        .map(Double::parseDouble)
        .gather(Gatherers.windowFixed(4))
        .map(window -> window.stream()
            .mapToDouble(Double::doubleValue)
            .average()
            .orElseThrow())
        .toList();

    System.out.println(averages);
}
```

Khi có dòng không hợp lệ, `Double.parseDouble` có thể ném `NumberFormatException`. `try-with-resources` vẫn đóng nguồn tệp khi rời khối.

**Quy tắc thứ tự xử lý:** Nếu lọc bỏ dữ liệu lỗi trước `gather`, các cửa sổ được tạo trên **những phần tử còn lại**, không còn giữ vị trí của các lần đo lỗi. Nếu nghiệp vụ cần giữ mốc thời gian và ghi nhận cửa sổ có dữ liệu thiếu, nên biểu diễn phần tử lỗi bằng một trạng thái rõ ràng thay vì đơn giản xóa nó.

## 17. Ví dụ Java 24 hoàn chỉnh: báo cáo cả fixed và sliding metrics

Chương trình dưới đây có thể được lưu thành `WindowMetricsDemo.java` và biên dịch bằng JDK 24 trở lên. Nó mô tả dữ liệu cố định trong bộ nhớ, nên không cần tự quản lý tệp hoặc kết nối I/O.

```java
import java.time.Instant;
import java.util.List;
import java.util.stream.Gatherers;

public class WindowMetricsDemo {

    record Reading(Instant at, int value) {}

    record Metric(
        Instant endAt,
        int samples,
        long sum,
        double average,
        int min,
        int max
    ) {}

    static Metric metricOf(List<Reading> window) {
        var s = window.stream()
            .mapToInt(Reading::value)
            .summaryStatistics();

        return new Metric(
            window.get(window.size() - 1).at(),
            window.size(),
            s.getSum(),
            s.getAverage(),
            s.getMin(),
            s.getMax()
        );
    }

    public static void main(String[] args) {
        List<Reading> input = List.of(
            new Reading(Instant.parse("2026-01-01T00:00:00Z"), 10),
            new Reading(Instant.parse("2026-01-01T00:01:00Z"), 20),
            new Reading(Instant.parse("2026-01-01T00:02:00Z"), 30),
            new Reading(Instant.parse("2026-01-01T00:03:00Z"), 40),
            new Reading(Instant.parse("2026-01-01T00:04:00Z"), 50)
        );

        List<Metric> fixed = input.stream()
            .gather(Gatherers.windowFixed(3))
            .map(WindowMetricsDemo::metricOf)
            .toList();

        List<Metric> sliding = input.stream()
            .gather(Gatherers.windowSliding(3))
            .map(WindowMetricsDemo::metricOf)
            .toList();

        System.out.println("FIXED");
        fixed.forEach(System.out::println);

        System.out.println("SLIDING");
        sliding.forEach(System.out::println);
    }
}
```

Kết quả:

```text
FIXED
Metric[endAt=2026-01-01T00:02:00Z, samples=3, sum=60, average=20.0, min=10, max=30]
Metric[endAt=2026-01-01T00:04:00Z, samples=2, sum=90, average=45.0, min=40, max=50]
SLIDING
Metric[endAt=2026-01-01T00:02:00Z, samples=3, sum=60, average=20.0, min=10, max=30]
Metric[endAt=2026-01-01T00:03:00Z, samples=3, sum=90, average=30.0, min=20, max=40]
Metric[endAt=2026-01-01T00:04:00Z, samples=3, sum=120, average=40.0, min=30, max=50]
```

**Phân tích:** `windowFixed` phát hai cửa sổ, trong đó cửa sổ cuối chứa hai mẫu. `windowSliding` phát ba cửa sổ đầy đủ. Phương thức `metricOf` không cần biết nguồn được chia bằng kiểu nào: nó chỉ nhận một danh sách phần tử đã hình thành cửa sổ rồi tính chỉ số. Đây là cách **tách riêng logic tạo cửa sổ và logic tính metric** để code dễ kiểm thử.

## 18. Lỗi thường gặp và cách khắc phục

| Sai lầm | Hệ quả | Cách sửa |
| --- | --- | --- |
| Chạy ví dụ `gather` trên JDK 17 | Không có `Stream.gather`/`Gatherers` chuẩn | Dùng JDK 24+ hoặc thiết kế giải pháp khác tương thích phiên bản |
| Nhầm `windowSliding(3)` với “3 phút gần nhất” | Các bản ghi cách xa nhau vẫn có thể chung cửa sổ | Phân biệt cửa sổ theo số phần tử và theo thời gian |
| Giả định `windowSliding(k)` luôn có đủ k mẫu | Nguồn có `0 < N < k` vẫn cho một cửa sổ ngắn | Lọc `window.size()==k` nếu yêu cầu |
| Giả định `windowFixed(k)` loại cửa sổ cuối không đủ k | Báo cáo có nhóm cuối ngắn hơn | Chấp nhận hoặc lọc nhóm cuối theo chính sách |
| Dùng cửa sổ trên nguồn trộn nhiều thiết bị | Metric bị lẫn dữ liệu giữa các thiết bị | Nhóm hoặc phân luồng theo thiết bị trước |
| Tính “mới nhất” trên nguồn không có encounter order hợp lệ | Cửa sổ không có ý nghĩa thời gian | Sắp theo timestamp hoặc bảo đảm thứ tự từ nguồn |
| Đặt `filter` trước `gather` nhưng vẫn nghĩ kích thước cửa sổ tính theo bản ghi gốc | Các cửa sổ được dựng sau khi đã xóa phần tử | Xác định rõ thứ tự lọc và tạo cửa sổ |
| Dùng `get(2)` cho mọi cửa sổ rộng 3 | Lỗi khi nguồn có cửa sổ ngắn | Kiểm tra `size()` hoặc lấy `get(size()-1)` |
| Chia trung bình cho k ngay cả khi cửa sổ thiếu mẫu | Trung bình sai | Chia cho số phần tử thực tế |
| Sửa danh sách cửa sổ do Gatherers tạo | `UnsupportedOperationException` | Tạo bản sao mutable nếu cần |
| Gọi `toList()` trên mọi cửa sổ của nguồn cực lớn | Chi phí bộ nhớ tăng mạnh | Tiêu thụ từng metric hoặc dùng custom Gatherer |
| Thêm `parallel()` và mặc định nhanh hơn | Chi phí phối hợp cửa sổ có thể lớn | Kiểm thử kết quả và benchmark trước |
| Dùng `reduce` trên toàn Stream để tính SMA | Chỉ có một tổng cuối, không có cửa sổ | Dùng `windowSliding` hoặc custom Gatherer |
| Dùng `Gatherers.scan` để thay sliding window | Tổng chạy không loại phần tử cũ | Sử dụng windowSliding hoặc trạng thái trượt |
| Bật source I/O nhưng quên đóng sau `limit`/`gather` | Rò rỉ tài nguyên | `try-with-resources` |
| Tính tiền bằng `double` rồi mong đúng tuyệt đối | Sai số nhị phân | `BigDecimal` và quy tắc làm tròn rõ ràng |

## 19. Bài tập thực hành

### Bài 1: Dự đoán cửa sổ

Cho `Stream.of(3, 6, 9, 12, 15, 18, 21)` và `k=3`. Viết tay danh sách các cửa sổ của `windowFixed` và `windowSliding`. Đếm số cửa sổ theo công thức rồi chạy chương trình kiểm chứng.

### Bài 2: Trung bình trượt

Cho nhiệt độ `[20, 21, 23, 24, 22, 25]`. Tính trung bình trượt ba mẫu bằng `Gatherers.windowSliding(3)` kết hợp `mapToInt(...).average()`. Ghi rõ trung bình thuộc timestamp của phần tử nào.

### Bài 3: Cửa sổ thiếu mẫu

Với dữ liệu `[10, 20]` và `k=4`, dự đoán đầu ra của `windowFixed`, `windowSliding` và hai pipeline có thêm `filter(w -> w.size()==4)`. Vì sao việc tự động bỏ cửa sổ thiếu mẫu có thể làm mất thông tin khởi động?

### Bài 4: Tỷ lệ lỗi từng lô

Tạo `record Job(String id, boolean failed)` và 10 công việc. Nhóm bằng `windowFixed(4)`; cho mỗi nhóm, tính số lỗi và tỷ lệ lỗi. Thử chọn chính sách phát cảnh báo nếu tỷ lệ lỗi lớn hơn 25%, ghi chú cách xử lý nhóm cuối chỉ có hai công việc.

### Bài 5: Phát hiện biến động lớn giữa hai mẫu

Dùng `windowSliding(2)` để tạo các cặp số đo. Viết `map` tính độ chênh tuyệt đối bằng kiểu đủ rộng nếu dữ liệu là `int`, rồi `filter` những cặp có mức thay đổi vượt ngưỡng.

### Bài 6: Chỉ số theo thiết bị

Cho dữ liệu hai cảm biến A, B trộn lẫn trong nguồn. Tạo báo cáo trung bình trượt rộng ba **riêng từng cảm biến**, giữ thứ tự timestamp. So sánh với việc áp dụng `windowSliding` trước `groupingBy` và giải thích lý do sai.

### Bài 7: Cửa sổ theo số bản ghi hay theo thời gian?

Có các bản ghi ở 10:00, 10:01, 10:10, 10:11, 10:12. Hãy chỉ ra ba bản ghi liên tiếp khác với cửa sổ ba phút thế nào. Mô tả yêu cầu phải bổ sung nếu muốn xử lý timestamp trùng, bản ghi đến muộn và khoảng thời gian mở/đóng.

### Bài 8: Custom Gatherer

Dựa trên `rollingSum(3)` ở mục 11, hãy thay tổng bằng `BigInteger` để tránh tràn `long`. Thử dữ liệu `Long.MAX_VALUE, 1L, -1L`; so sánh với cách tính dùng `Math.addExact` và giải thích khi nào cần kiểm tra tổng cuối hay mọi tổng trung gian.

### Bài 9: Benchmark và dung lượng

Với một triệu quan sát và cửa sổ rộng 100, ước lượng số cửa sổ trượt. So sánh lựa chọn `gather(windowSliding).map(...).toList()` với một custom Gatherer chỉ phát tổng, không giữ mọi danh sách cửa sổ. Đề xuất cách đo công bằng bằng JMH và kiểm tra kết quả từng trường hợp biên.

### Bài 10: Stream vô hạn

Tạo một `Stream.iterate(...)` không giới hạn, áp dụng `windowSliding(5)` và `limit(3)`. Đếm số phần tử nguồn tối thiểu cần để tạo ba cửa sổ đầy đủ; giải thích vì sao không nên bỏ `limit` khi terminal operation là `toList()`.

## 20. Tự kiểm tra kiến thức

- `windowFixed` và `windowSliding` khác nhau thế nào về mức độ chồng lấn?
- Vì sao `windowFixed(3)` có thể phát cửa sổ cuối chứa một hoặc hai phần tử?
- Trên nguồn chỉ có hai phần tử, `windowSliding(3)` trả về gì?
- Với `N >= k`, công thức số cửa sổ trượt là gì?
- `Stream.gather` là intermediate hay terminal operation?
- Vì sao `windowSliding(3)` không mặc nhiên là cửa sổ theo ba phút?
- Khi dữ liệu nhiều thiết bị, tại sao phải tách cửa sổ theo thiết bị?
- Vì sao `filter` trước `gather` có thể làm thay đổi ý nghĩa chỉ số?
- Khi nào có thể dùng `Gatherers.scan`, và vì sao nó khác tổng trượt?
- Vai trò của initializer, integrator, combiner và finisher của custom Gatherer là gì?
- Vì sao một rolling Gatherer có trạng thái thứ tự thường không thể chỉ đơn giản cộng hai kết quả của nhánh song song?
- Những nguy cơ bộ nhớ nào phát sinh khi cửa sổ lớn và kết quả `toList()` giữ mọi cửa sổ?
- Khi nào nên dùng `BigDecimal`, `BigInteger` hay `Math.addExact`?
- Vì sao `gather` trên `Files.lines` vẫn phải được bao trong `try-with-resources`?

## 21. Tài liệu tham khảo

- [Java SE 24 — `Gatherers`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html): hợp đồng và trường hợp biên của `windowFixed`, `windowSliding`, `scan`.
- [Java SE 24 — `Gatherer`](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherer.html): initializer, integrator, combiner, finisher và `ofSequential`.
- [Java SE 24 — Stream Gatherers](https://docs.oracle.com/en/java/javase/24/core/stream-gatherers.html): các mẫu sử dụng Gatherer dựng sẵn.

**Ghi nhớ:** Gatherer giúp chuyển Stream thành **các cửa sổ có thứ tự** để tính chỉ số theo nhóm liên tiếp. Dùng `windowFixed(k)` cho các lô không chồng lấn và `windowSliding(k)` cho chỉ số trượt của `k` quan sát gần nhất. Luôn xác định chính sách **cửa sổ không đủ mẫu**, phân biệt **số phần tử với khoảng thời gian**, giữ encounter order đúng với nghiệp vụ và cân nhắc bộ nhớ khi có nhiều cửa sổ. Chỉ viết custom Gatherer khi lợi ích của trạng thái tích lũy và bước hoàn tất đủ lớn để bù cho độ phức tạp của hợp đồng.
