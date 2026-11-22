# Viết Collector tùy biến để tổng hợp nhiều chỉ số

Trong các dự án thực tế, một lần duyệt dữ liệu thường phải tạo **nhiều chỉ số liên quan**: tổng số đơn hàng, số đơn đã thanh toán, tổng tiền, giá trị nhỏ nhất/lớn nhất, trung bình và số đơn theo khu vực. Viết sáu hoặc bảy pipeline `stream()` riêng biệt có thể vẫn đúng với một `List` nhỏ, nhưng không phù hợp nếu nguồn rất lớn, chỉ tiêu thụ một lần hoặc gắn với I/O. Một **`Collector` tùy biến** có thể lưu đủ trạng thái trung gian, cập nhật mọi chỉ số khi nhận từng phần tử rồi tạo một đối tượng báo cáo ở cuối.

Đây là bài thực hành nâng cao thuộc chương **Bài tập nâng cao và dự án** của module **JAVA_STREAM_API**. Ta kết hợp kiến thức về pipeline lazy, `filter`, `map`, `reduce`, `collect`, grouping, hợp đồng Collector, `Spliterator` và xử lý song song. Bên cạnh việc viết code Java 8 có thể chạy độc lập, bài tập yêu cầu suy luận về **tính đúng đắn**, **dữ liệu rỗng**, **tràn số**, **trạng thái dùng chung**, **tài nguyên** và **hiệu năng**; các kỹ thuật biến đổi nâng cao như Stream Gatherers không phải điều kiện cần để giải bài toán này.

## 1. Bài toán dự án: báo cáo nhiều KPI từ đơn hàng

Giả sử ứng dụng nhận các đơn hàng với bốn thuộc tính:

- `id`: mã đơn.
- `region`: khu vực, ví dụ `BAC`, `NAM` hoặc `TRUNG`.
- `amountCents`: số tiền ở đơn vị nhỏ nhất của tiền tệ, kiểu `long` và không âm.
- `paid`: trạng thái đã thanh toán, kiểu `boolean`.

Cho dữ liệu:

| Đơn | Khu vực | Số tiền (cents) | Đã thanh toán? |
|---|---|---:|---|
| O1 | BAC | 10.000 | Có |
| O2 | NAM | 5.000 | Không |
| O3 | BAC | 30.000 | Có |
| O4 | NAM | 20.000 | Có |
| O5 | BAC | 0 | Có |
| O6 | TRUNG | 4.000 | Không |

Yêu cầu báo cáo:

| Chỉ số | Kết quả mong đợi |
|---|---|
| Tổng số đơn | `6` |
| Số đơn đã thanh toán | `4` |
| Số đơn chưa thanh toán | `2` |
| Tổng tiền đã thanh toán | `60_000L` |
| Tiền đơn đã thanh toán thấp nhất | `0L` |
| Tiền đơn đã thanh toán cao nhất | `30_000L` |
| Tiền trung bình của đơn đã thanh toán | `15_000.0` |
| Số đơn theo khu vực | `{BAC=3, NAM=2, TRUNG=1}` |

Các quy tắc nghiệp vụ cần làm rõ **trước khi** viết Collector:

1. Số đơn theo khu vực tính **tất cả** đơn, kể cả chưa thanh toán.
2. Tổng, min, max và trung bình tiền chỉ xét **đơn đã thanh toán**.
3. Nếu **không có đơn đã thanh toán**, tổng tiền bằng 0 nhưng **min/max/trung bình không tồn tại**, không phải đều bằng 0.
4. Đơn `null` hoặc khu vực `null` được coi là dữ liệu không hợp lệ; ví dụ sẽ báo lỗi thay vì âm thầm loại bỏ.
5. Để kiểm soát tràn `long`, dùng `Math.addExact`. Nếu vượt giới hạn sẽ phát sinh ngoại lệ thay vì tạo tổng sai.

Việc thiết kế rõ các quy tắc này quan trọng không kém cú pháp Stream: một pipeline nhanh nhưng cho sai tập bản ghi vẫn là một triển khai không đạt.

## 2. Vì sao cần Collector nhiều chỉ số?

### 2.1. Cách đơn giản nhưng duyệt nguồn nhiều lần

Với một danh sách trong bộ nhớ, ta có thể viết:

```java
long orderCount = orders.stream().count();

long paidCount = orders.stream()
        .filter(Order::isPaid)
        .count();

long paidTotal = orders.stream()
        .filter(Order::isPaid)
        .mapToLong(Order::getAmountCents)
        .sum();
```

Đoạn minh họa giả định có kiểu `Order` và nguồn `orders`. Mỗi lệnh `stream()` tạo một pipeline mới để tính **một đại lượng**. Với `List` có thể duyệt lại, cách này đôi khi rất dễ đọc và là lựa chọn hợp lý. Nhưng nếu tính thêm min, max, average và các thống kê khác, số lần quét tăng lên.

Quan trọng hơn, không thể gọi hai terminal operation trên **cùng một đối tượng `Stream`**:

```java
Stream<Order> source = orders.stream();

long count = source.count();

// SAI: Stream đã tiêu thụ.
// long paidCount = source.filter(Order::isPaid).count();
```

Với nguồn I/O chỉ đọc một lần, việc tạo lại Stream có thể đòi hỏi mở lại file, đọc lại dữ liệu hoặc thậm chí không khả thi. Một Collector nhiều chỉ số giúp hoàn thành các phép đo trong **một lần thu thập**.

### 2.2. Bốn yêu cầu thiết kế

Collector tùy biến của chúng ta cần có:

1. **Trạng thái trung gian đủ thông tin** để cập nhật các KPI và gộp được hai phần kết quả.
2. **Hàm thêm một đơn hàng** vào trạng thái mà không sửa dữ liệu nguồn.
3. **Hàm kết hợp hai trạng thái** để hoạt động đúng cả với parallel stream.
4. **Hàm hoàn tất** tạo báo cáo bất biến, không cho caller sửa trạng thái nội bộ.

Điểm quan trọng là **không tính trung bình trong mỗi lần tích lũy**. Chỉ giữ `sum` và `count`, rồi tính `sum / count` ở bước cuối, vì trung bình đơn lẻ của hai nhóm không đủ để tính trung bình chung khi kích thước nhóm khác nhau.

## 3. Kiểu Collector<T, A, R> và các thành phần

`java.util.stream.Collector<T, A, R>` có ba kiểu:

| Ký hiệu | Ý nghĩa | Trong dự án |
|---|---|---|
| `T` | Kiểu phần tử nguồn | `Order` |
| `A` | Kiểu trạng thái tích lũy có thể thay đổi | `MetricsAccumulator` |
| `R` | Kiểu kết quả cuối | `Report` |

Một Collector hoàn chỉnh có năm khái niệm:

| Thành phần | Trách nhiệm | Định hướng triển khai |
|---|---|---|
| `supplier` | Tạo trạng thái rỗng | `MetricsAccumulator::new` |
| `accumulator` | Nhận một `Order`, cập nhật trạng thái | `MetricsAccumulator::add` |
| `combiner` | Gộp kết quả hai nhánh | `MetricsAccumulator::combine` |
| `finisher` | Tạo báo cáo cuối | `MetricsAccumulator::finish` |
| `characteristics` | Công bố tính chất Collector | Không công bố đặc tính không được bảo đảm |

Để tạo Collector bằng Java 8:

```java
Collector<Order, MetricsAccumulator, Report> collector =
        Collector.of(
                MetricsAccumulator::new,
                MetricsAccumulator::add,
                MetricsAccumulator::combine,
                MetricsAccumulator::finish);
```

Đây là mẫu mã sẽ được định nghĩa đầy đủ ở phần 5. Vì `A = MetricsAccumulator` khác `R = Report`, **không khai báo `IDENTITY_FINISH`**. Vì container là trạng thái mutable thông thường, **không khai báo `CONCURRENT`**. Vì kết quả số học và Map đếm không phụ thuộc encounter order, phép thu thập này *có thể* được thiết kế là unordered, nhưng ví dụ không cần công bố `UNORDERED` để đúng và dễ kiểm chứng.

## 4. Mô hình trạng thái trung gian

### 4.1. Lưu dữ liệu gì?

`MetricsAccumulator` cần các trường:

```text
orderCount        : long
paidCount         : long
paidCents         : long
minPaidCents      : long (ban đầu Long.MAX_VALUE)
maxPaidCents      : long (ban đầu Long.MIN_VALUE)
regionCounts      : Map<String, Long>
```

**Không cần lưu từng đơn hàng**. Bộ tích lũy chỉ tăng đếm, cộng tiền, cập nhật min/max và tăng đếm theo vùng. Bộ nhớ tăng chủ yếu theo **số khu vực phân biệt**, không tăng tuyến tính theo tổng số đơn.

### 4.2. Bất biến của trạng thái

Sau khi tích lũy một tập đơn hợp lệ:

- `orderCount >= 0` và `paidCount >= 0`.
- `0 <= paidCount <= orderCount`.
- `paidCents` là tổng `amountCents` của các đơn đã thanh toán, trong miền `long` không tràn.
- Nếu `paidCount > 0`, `minPaidCents` và `maxPaidCents` là cực trị thật của các đơn đã thanh toán.
- Nếu `paidCount == 0`, không được hiển thị `Long.MAX_VALUE` hay `Long.MIN_VALUE` như cực trị thật.
- Tổng mọi giá trị trong `regionCounts` bằng `orderCount`, nếu số đếm không tràn.

Những bất biến này là công cụ kiểm tra một Collector chính xác hơn việc chỉ xem nó “chạy được”.

### 4.3. Vì sao dùng Optional cho min, max và average?

Với một nguồn rỗng, hoặc nguồn có đơn nhưng không có đơn nào đã thanh toán:

```text
paidCount = 0
paidCents = 0
minPaid   = không tồn tại
maxPaid   = không tồn tại
average   = không tồn tại
```

`OptionalLong` và `OptionalDouble` giúp biểu diễn trạng thái thiếu giá trị. Việc trả số `0` từ `minPaid` sẽ sai về ý nghĩa khi không có phép đo; nhưng nếu có **một đơn đã thanh toán với số tiền 0**, min bằng `OptionalLong[0]` là kết quả hợp lệ.

## 5. Chương trình Java 8 hoàn chỉnh: một lần collect cho nhiều KPI

Mã dưới đây có thể lưu thành `MultiMetricCollectorDemo.java` và chạy với JDK 8 trở lên. Mã sử dụng số tiền ở đơn vị nhỏ nhất và chỉ chấp nhận giá trị không âm. Các hàm tích lũy bảo vệ tràn số bằng `Math.addExact`.

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.OptionalDouble;
import java.util.OptionalLong;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class MultiMetricCollectorDemo {

    static final class Order {
        private final String id;
        private final String region;
        private final long amountCents;
        private final boolean paid;

        Order(String id, String region, long amountCents, boolean paid) {
            this.id = Objects.requireNonNull(id, "id");
            this.region = Objects.requireNonNull(region, "region");
            if (amountCents < 0) {
                throw new IllegalArgumentException(
                        "amountCents không được âm");
            }
            this.amountCents = amountCents;
            this.paid = paid;
        }

        String getId() { return id; }
        String getRegion() { return region; }
        long getAmountCents() { return amountCents; }
        boolean isPaid() { return paid; }
    }

    // A: Trạng thái trung gian, chỉ thay đổi trong quá trình collect.
    static final class MetricsAccumulator {
        private long orderCount;
        private long paidCount;
        private long paidCents;
        private long minPaidCents = Long.MAX_VALUE;
        private long maxPaidCents = Long.MIN_VALUE;
        private final Map<String, Long> regionCounts = new HashMap<>();

        // Accumulator: tiếp nhận một đơn.
        void add(Order order) {
            Objects.requireNonNull(order, "order");

            orderCount = Math.addExact(orderCount, 1L);
            regionCounts.merge(order.getRegion(), 1L, Math::addExact);

            if (order.isPaid()) {
                paidCount = Math.addExact(paidCount, 1L);
                paidCents = Math.addExact(
                        paidCents, order.getAmountCents());
                minPaidCents = Math.min(
                        minPaidCents, order.getAmountCents());
                maxPaidCents = Math.max(
                        maxPaidCents, order.getAmountCents());
            }
        }

        // Combiner: gộp đủ thông tin của nhánh phải vào nhánh trái.
        MetricsAccumulator combine(MetricsAccumulator right) {
            orderCount = Math.addExact(orderCount, right.orderCount);
            paidCount = Math.addExact(paidCount, right.paidCount);
            paidCents = Math.addExact(paidCents, right.paidCents);

            if (right.paidCount > 0) {
                minPaidCents = Math.min(
                        minPaidCents, right.minPaidCents);
                maxPaidCents = Math.max(
                        maxPaidCents, right.maxPaidCents);
            }

            right.regionCounts.forEach((region, count) ->
                    regionCounts.merge(
                            region, count, Math::addExact));
            return this;
        }

        // Finisher: chụp một bản kết quả không cho sửa Map bên trong.
        Report finish() {
            OptionalLong min = paidCount == 0
                    ? OptionalLong.empty()
                    : OptionalLong.of(minPaidCents);
            OptionalLong max = paidCount == 0
                    ? OptionalLong.empty()
                    : OptionalLong.of(maxPaidCents);
            OptionalDouble avg = paidCount == 0
                    ? OptionalDouble.empty()
                    : OptionalDouble.of(
                            (double) paidCents / paidCount);

            Map<String, Long> snapshot = Collections.unmodifiableMap(
                    new TreeMap<>(regionCounts));

            return new Report(
                    orderCount, paidCount, paidCents,
                    min, max, avg, snapshot);
        }
    }

    // R: DTO báo cáo bất biến sau khi collect kết thúc.
    static final class Report {
        final long orderCount;
        final long paidCount;
        final long paidCents;
        final OptionalLong minPaid;
        final OptionalLong maxPaid;
        final OptionalDouble averagePaid;
        final Map<String, Long> regionCounts;

        Report(long orderCount, long paidCount, long paidCents,
                OptionalLong minPaid, OptionalLong maxPaid,
                OptionalDouble averagePaid,
                Map<String, Long> regionCounts) {
            this.orderCount = orderCount;
            this.paidCount = paidCount;
            this.paidCents = paidCents;
            this.minPaid = minPaid;
            this.maxPaid = maxPaid;
            this.averagePaid = averagePaid;
            this.regionCounts = regionCounts;
        }

        long unpaidCount() {
            return orderCount - paidCount;
        }
    }

    static Collector<Order, MetricsAccumulator, Report>
            metricsCollector() {
        return Collector.of(
                MetricsAccumulator::new,
                MetricsAccumulator::add,
                MetricsAccumulator::combine,
                MetricsAccumulator::finish);
    }

    // Phép so sánh được viết rõ để kiểm tra kết quả song song.
    static boolean sameReport(Report a, Report b) {
        return a.orderCount == b.orderCount
                && a.paidCount == b.paidCount
                && a.paidCents == b.paidCents
                && a.minPaid.equals(b.minPaid)
                && a.maxPaid.equals(b.maxPaid)
                && a.averagePaid.equals(b.averagePaid)
                && a.regionCounts.equals(b.regionCounts);
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
                new Order("O1", "BAC",   10_000L, true),
                new Order("O2", "NAM",    5_000L, false),
                new Order("O3", "BAC",   30_000L, true),
                new Order("O4", "NAM",   20_000L, true),
                new Order("O5", "BAC",        0L, true),
                new Order("O6", "TRUNG",  4_000L, false)
        );

        // Hai cách thực thi phải cho các KPI tương đương.
        Report sequential = orders.stream()
                .collect(metricsCollector());
        Report parallel = orders.parallelStream()
                .collect(metricsCollector());

        System.out.println(sequential.orderCount);    // 6
        System.out.println(sequential.paidCount);     // 4
        System.out.println(sequential.unpaidCount()); // 2
        System.out.println(sequential.paidCents);     // 60000
        System.out.println(sequential.minPaid.orElse(-1)); // 0
        System.out.println(sequential.maxPaid.orElse(-1)); // 30000
        System.out.println(
                sequential.averagePaid.orElse(-1));  // 15000.0
        System.out.println(sequential.regionCounts);
        // {BAC=3, NAM=2, TRUNG=1}

        System.out.println(sameReport(sequential, parallel)); // true

        // Nguồn hoàn toàn rỗng: không có cực trị/trung bình.
        Report empty = Collections.<Order>emptyList()
                .stream()
                .collect(metricsCollector());
        System.out.println(empty.orderCount); // 0
        System.out.println(empty.paidCents); // 0
        System.out.println(empty.averagePaid.isPresent()); // false
        System.out.println(empty.minPaid.isPresent()); // false
        System.out.println(empty.regionCounts.isEmpty()); // true

        // Có đơn nhưng không đơn nào thanh toán.
        Report noPaid = Arrays.asList(
                new Order("X1", "BAC", 100L, false))
                .stream()
                .collect(metricsCollector());
        System.out.println(noPaid.orderCount); // 1
        System.out.println(noPaid.paidCount);  // 0
        System.out.println(noPaid.averagePaid.isPresent()); // false
        System.out.println(noPaid.regionCounts.get("BAC")); // 1

        // Collector tùy biến có thể dùng làm downstream theo nhóm.
        Map<String, Report> reportsByRegion = orders.stream()
                .collect(Collectors.groupingBy(
                        Order::getRegion, metricsCollector()));
        System.out.println(
                reportsByRegion.get("BAC").paidCount); // 3
        System.out.println(
                reportsByRegion.get("NAM").paidCents); // 20000
    }
}
```

**Kết quả quan trọng:** báo cáo tuần tự và song song tương đương, cùng đếm sáu đơn và bốn đơn đã thanh toán, có tổng tiền 60.000 và trung bình 15.000. Với một nguồn rỗng, `paidCents == 0` nhưng `averagePaid` và `minPaid` đều rỗng. Với nguồn chỉ chứa đơn chưa thanh toán, số đơn và số đơn theo khu vực vẫn được đếm, trong khi thống kê tiền đã thanh toán không tồn tại.

Ví dụ dùng bộ dữ liệu nhỏ để kiểm tra **tính đúng**, không phải benchmark cho thấy parallel stream nhanh hơn. Không cần thêm `CONCURRENT` chỉ vì phép thu thập có thể chạy trên parallel stream: framework quản lý các bộ tích lũy độc lập rồi gọi combiner.

## 6. Giải thích từng thành phần của Collector

### 6.1. Supplier: trạng thái rỗng thật sự

`MetricsAccumulator::new` tạo một đối tượng mới với các bộ đếm bằng 0 và `regionCounts` rỗng. Các giá trị `Long.MAX_VALUE` và `Long.MIN_VALUE` chỉ là *sentinel* nội bộ để cập nhật min/max; chúng **không được xuất ra báo cáo** nếu chưa có đơn đã thanh toán.

Supplier không được lấy một `MetricsAccumulator` đã dùng trước đó từ biến static rồi trả lại cho tất cả các nhánh. Làm vậy có thể khiến hai worker cùng thay đổi một trạng thái mutable, gây race và vi phạm hợp đồng thu thập.

### 6.2. Accumulator: cập nhật đủ KPI cho mỗi phần tử

Với đơn `O2` chưa thanh toán:

```text
orderCount   + 1
regionCounts["NAM"] + 1
paidCount    giữ nguyên
paidCents    giữ nguyên
min/max      giữ nguyên
```

Với đơn `O3` đã thanh toán, ngoài hai chỉ số đầu, accumulator còn:

```text
paidCount + 1
paidCents + 30000
minPaidCents = min(minPaidCents, 30000)
maxPaidCents = max(maxPaidCents, 30000)
```

Không dùng `forEach` để cập nhật một đối tượng Report chung bên ngoài pipeline. Việc thay đổi trạng thái trung gian là trách nhiệm của Collector, có giới hạn sở hữu và kết hợp rõ ràng.

### 6.3. Combiner: không được chỉ cộng tổng tiền

Khi gộp hai trạng thái, phải gộp **tất cả** chỉ số:

| Trường | Cách gộp |
|---|---|
| `orderCount` | Cộng đếm từ nhánh trái và nhánh phải |
| `paidCount` | Cộng đếm đã thanh toán |
| `paidCents` | Cộng tổng tiền đã thanh toán |
| `minPaidCents` | Chọn min trên các nhánh có ít nhất một đơn đã thanh toán |
| `maxPaidCents` | Chọn max trên các nhánh có ít nhất một đơn đã thanh toán |
| `regionCounts` | Hợp nhất Map và cộng số đếm trùng khóa |

Nếu bỏ quên việc kết hợp `regionCounts`, chương trình có thể “đúng” khi chạy tuần tự nhưng mất nhóm hoặc mất số đếm khi chạy song song. Nếu gộp trung bình trực tiếp, kết quả có thể sai với những phân đoạn có kích thước khác nhau.

**Vì sao có thể cập nhật trạng thái bên trái rồi trả về chính nó?** Trong mutable reduction không concurrent, framework quản lý việc sử dụng từng container theo vòng đời của Collector. Combiner được phép lấy trạng thái nhánh trái làm kết quả sau gộp, miễn không gây chia sẻ trái phép và kết quả vẫn đúng.

### 6.4. Finisher: chuyển trạng thái tạm thành kết quả có ý nghĩa

Finisher chỉ tính trung bình sau khi đã có tổng và số đếm, đồng thời chuyển sentinel min/max thành `OptionalLong`. Nó còn tạo một **bản sao `TreeMap`** và bọc bằng `Collections.unmodifiableMap`:

```java
Map<String, Long> snapshot = Collections.unmodifiableMap(
        new TreeMap<>(regionCounts));
```

Lợi ích của bản sao: `Report` không giữ trực tiếp Map mutable của accumulator. `TreeMap` còn cung cấp thứ tự khóa tăng dần cho mục đích trình bày; **đây là quyết định thiết kế kết quả**, không phải điều kiện để collector có thể xử lý song song.

Vì finisher thực hiện việc chuyển đổi thực sự từ `MetricsAccumulator` sang `Report`, không khai báo `Collector.Characteristics.IDENTITY_FINISH`.

## 7. Chứng minh hợp đồng đơn vị, kết hợp và tương đương

Một Collector tùy biến cần cho kết quả đúng với mọi cách framework chia và kết hợp dữ liệu hợp lệ.

### 7.1. Đơn vị (identity)

Gọi `E` là một accumulator mới từ supplier. Nó có các bộ đếm bằng 0, Map rỗng và chưa có cực trị. Với một trạng thái hợp lệ `A`:

```text
combine(A, E) tương đương A
```

Trong code, gộp số đếm và tiền với 0 không đổi kết quả; Map rỗng không thêm khóa nào; do `E.paidCount == 0` nên không làm thay đổi min/max.

Trường hợp đối xứng `combine(E, A)` cũng cho cùng ý nghĩa: tổng/đếm được chép qua bằng phép cộng, min/max có giá trị từ `A` nếu `A` có đơn đã thanh toán, và Map đếm được hợp nhất.

### 7.2. Kết hợp nhóm (associativity)

Giả sử `A`, `B` và `C` là trạng thái tích lũy cho ba phân đoạn độc lập. Ta cần:

```text
combine(combine(A, B), C)  ≈  combine(A, combine(B, C))
```

Đếm và tổng dùng phép cộng `long`, min/max dùng phép chọn cực trị, còn Map cộng số đếm theo từng khóa. Với **dữ liệu hợp lệ không gây tràn**, việc đổi cách nhóm không làm thay đổi chỉ số. Mọi phép cộng được kiểm tra bằng `Math.addExact` để thất bại rõ ràng khi kết quả vượt miền `long`.

**Lưu ý về trung bình:** ta không gộp giá trị trung bình từng nhánh. Ví dụ:

```text
Nhánh A: [10]         sum=10, count=1, average=10
Nhánh B: [20, 30]     sum=50, count=2, average=25

SAI:  (10 + 25) / 2 = 17.5
ĐÚNG: (10 + 50) / (1 + 2) = 20
```

Do đó, trạng thái trung gian bắt buộc giữ đủ thông tin `sum` và `count` đến bước finisher.

### 7.3. Tương đương (equivalence)

Các cách tích lũy khác nhau phải tạo `Report` tương đương về **mọi KPI**, không chỉ riêng tổng tiền. Ví dụ, nếu hai báo cáo có `paidCents` bằng nhau nhưng `regionCounts` khác nhau thì **không tương đương** với yêu cầu dự án.

Hàm `sameReport` trong ví dụ so sánh mọi chỉ số và Map kết quả. Trên bộ dữ liệu nhỏ với kết quả số nguyên, việc so sánh `OptionalDouble` là hợp lý; trong các hệ thống tính trung bình từ nhiều giá trị dấu phẩy động, không nên luôn yêu cầu kết quả từng bit giống nhau vì thứ tự cộng có thể ảnh hưởng sai số.

### 7.4. Vì sao không khai báo CONCURRENT?

`MetricsAccumulator` dùng `HashMap` và nhiều trường `long` được thay đổi trực tiếp. Nếu nhiều worker cùng gọi `add` trên **một** accumulator, đây không phải code thread-safe.

Nhưng khi dùng `orders.parallelStream().collect(metricsCollector())`, Collector **không có characteristic `CONCURRENT`**. Framework có thể cấp **container riêng cho các nhánh**, rồi gộp chúng; không yêu cầu mọi trường hay Map trong accumulator phải chịu cập nhật concurrent trên cùng instance.

`UNORDERED` chỉ nên công bố nếu kết quả không phụ thuộc encounter order. Các chỉ số của ví dụ được thiết kế không phụ thuộc thứ tự, nhưng chỉ cần bỏ characteristic đó thì collector vẫn hoạt động đúng; không công bố `CONCURRENT` vẫn là quyết định thiết yếu.

## 8. Xử lý nguồn rỗng và chỉ số không tồn tại

Có hai trường hợp khác nhau:

| Trường hợp | `orderCount` | `paidCount` | `paidCents` | `averagePaid` | `regionCounts` |
|---|---:|---:|---:|---|---|
| Không có đơn nào | 0 | 0 | 0 | `OptionalDouble.empty()` | Map rỗng |
| Có một đơn chưa thanh toán ở BAC | 1 | 0 | 0 | `OptionalDouble.empty()` | `{BAC=1}` |
| Có một đơn đã thanh toán số tiền 0 | 1 | 1 | 0 | `OptionalDouble[0.0]` | Tùy khu vực |
| Có hai đơn thanh toán 100 và 300 | 2 | 2 | 400 | `OptionalDouble[200.0]` | Tùy khu vực |

Một hệ thống dashboard có thể yêu cầu hiển thị dấu `—` khi không có trung bình, hoặc chủ động dùng `orElse(0.0)`. Tuy nhiên, **chính sách hiển thị không nên xóa mất thông tin “không có dữ liệu”** trong tầng thống kê nếu báo cáo cần phân biệt với trung bình thực sự bằng 0.

Đối với các nhóm, `groupingBy` chỉ tạo khóa cho nhóm có ít nhất một phần tử cha. Nếu không có đơn thuộc khu vực `TAY`, `reportsByRegion` không tự thêm khóa `TAY` với `Report` rỗng; tầng báo cáo phải bổ sung nhóm vắng mặt nếu nghiệp vụ yêu cầu.

## 9. Mở rộng dự án: biến thể và chính sách dữ liệu

### 9.1. Thêm số đơn chưa thanh toán

Không cần thêm một trường mutable riêng nếu:

```java
long unpaidCount = report.orderCount - report.paidCount;
```

Vì `paidCount` là tập con của `orderCount`, ta có thể tính chỉ số này tại `Report.unpaidCount()`. Tránh lưu những chỉ số suy ra được nếu chúng có thể trở nên không nhất quán khi cập nhật/combiner.

### 9.2. Tỷ lệ thanh toán

Nếu muốn tỷ lệ đơn đã thanh toán:

```java
OptionalDouble paidRate = report.orderCount == 0
        ? OptionalDouble.empty()
        : OptionalDouble.of(
                (double) report.paidCount / report.orderCount);
```

Khi nguồn rỗng, tỷ lệ không được xác định. Việc tính tỷ lệ trong finisher hoặc trong một phương thức của `Report` giúp tránh gộp trực tiếp các tỷ lệ không có trọng số.

### 9.3. Thêm tổng tiền theo khu vực

Có thể bổ sung:

```java
Map<String, Long> paidCentsByRegion = new HashMap<>();
```

Trong accumulator, chỉ với đơn đã thanh toán:

```java
paidCentsByRegion.merge(
        order.getRegion(),
        order.getAmountCents(),
        Math::addExact);
```

Trong combiner, duyệt Map từ nhánh phải và `merge(region, amount, Math::addExact)` vào Map bên trái. Trong finisher, tạo một snapshot bất biến cho kết quả. Việc thêm bất kỳ Map thống kê mới nào **đòi hỏi cả accumulator và combiner cập nhật đầy đủ**; nếu chỉ sửa accumulator, kết quả có nguy cơ sai trên parallel stream.

### 9.4. Số tiền âm, hoàn tiền và đổi tiền tệ

Ví dụ gốc từ chối `amountCents < 0`. Nếu ứng dụng hỗ trợ hoàn tiền, đây không chỉ là vấn đề đổi phép kiểm tra: cần quy tắc rõ ràng về tổng âm, cực trị, số tiền thanh toán và cách nhận diện giao dịch điều chỉnh.

Nếu có **nhiều loại tiền tệ**, không được cộng trực tiếp mọi `amountCents` thành một tổng duy nhất. Cần nhóm theo loại tiền, chuyển đổi theo tỷ giá được phê duyệt hoặc định nghĩa một đơn vị kế toán thống nhất trước khi tổng hợp.

### 9.5. Nhiều phân vị hoặc top-N

Median, percentile, top-N và distinct count chính xác có thể cần trạng thái phức tạp hơn. Ví dụ để tính median chính xác, một collector có thể phải giữ nhiều dữ liệu hơn chỉ `(sum, count, min, max)`. Không nên gán cho mọi KPI cùng độ phức tạp bộ nhớ: có chỉ số tính online với trạng thái hằng số, có chỉ số cần lưu nhiều phần tử.

## 10. Các vấn đề về độ chính xác và dữ liệu không hợp lệ

### 10.1. Tràn số nguyên

`long` không có miền giá trị vô hạn. Dùng `Math.addExact` giúp phát hiện trường hợp tổng hoặc số đếm vượt `Long.MAX_VALUE`. Khi điều đó xảy ra, collector sẽ ném `ArithmeticException`; không trả lại một con số bị tràn âm một cách âm thầm.

Với dữ liệu tiền lớn hoặc yêu cầu tính toán vượt phạm vi `long`, có thể thiết kế một accumulator sử dụng `BigInteger` hoặc `BigDecimal`. Mỗi lựa chọn có chi phí và chính sách làm tròn khác nhau.

### 10.2. Trung bình là double, không phải số tiền thập phân chính xác tuyệt đối

`(double) paidCents / paidCount` biểu diễn số thực nhị phân và có thể làm tròn. Nó phù hợp cho nhiều thống kê hiển thị, nhưng không luôn phù hợp với yêu cầu tài chính phải làm tròn chính xác theo một quy tắc cố định.

Ví dụ chuyển sang `BigDecimal` ở finisher:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Optional;

Optional<BigDecimal> exactAverage = paidCount == 0
        ? Optional.empty()
        : Optional.of(BigDecimal.valueOf(paidCents)
                .divide(BigDecimal.valueOf(paidCount),
                        2, RoundingMode.HALF_UP));
```

Đây là đoạn minh họa trong phạm vi `MetricsAccumulator`, nơi có các biến `paidCents` và `paidCount`. Quy tắc `scale = 2` và `HALF_UP` phải được chọn theo yêu cầu nghiệp vụ; nếu thống kê ở đơn vị cents thì kết quả cũng đang ở đơn vị cents, không tự chuyển sang đồng/đô la.

### 10.3. Null và phần tử hỏng

Đừng mặc định phần tử null được Stream tự loại bỏ. Với bộ dữ liệu chứa null, `MetricsAccumulator.add` hiện dùng `Objects.requireNonNull(order)` để **từ chối rõ ràng**; nó không tự bỏ qua bản ghi hỏng.

Nếu nghiệp vụ yêu cầu bỏ bản ghi null trước khi báo cáo:

```java
Report result = orders.stream()
        .filter(Objects::nonNull)
        .collect(metricsCollector());
```

Cách này làm số đếm phản ánh **các đơn hợp lệ sau lọc**, không phải tổng số dòng dữ liệu gốc. Nếu cần chỉ số **số bản ghi bị loại**, phải mô hình hóa nó trong accumulator hoặc một bước xác thực có thống kê riêng. Không nên vừa lọc âm thầm vừa báo cáo “tổng số bản ghi đã nhận”.

## 11. Đọc dữ liệu từ nguồn I/O nhưng vẫn đóng tài nguyên

Một ưu điểm của collector nhiều chỉ số là có thể tính nhiều KPI **ngay trong lúc duyệt file**, không phải giữ tất cả đơn trong bộ nhớ. Nhưng collector **không tự đóng** một Stream gắn tài nguyên I/O.

Ví dụ khái quát:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    Report report = lines
            .map(line -> parseOrder(line)) // Hàm parser do ứng dụng cung cấp.
            .collect(metricsCollector());
}
```

Đoạn này minh họa cách dùng trong một lớp có `parseOrder(String)` và `path` đã khai báo; nó không phải chương trình độc lập. `Files.lines` phải được đặt trong `try-with-resources` ngay cả khi đã gọi terminal operation `collect`. Nếu parse lỗi hoặc đọc file ném ngoại lệ, nguồn vẫn được đóng khi rời khối `try`.

Đối với nguồn lớn, nên cân nhắc:

- Parser có thể phân tích từng dòng độc lập không, hay cần trạng thái của dòng trước?
- Bộ tích lũy đang giữ bao nhiêu khóa khu vực? Nếu số khóa rất lớn, `regionCounts` có thể tốn bộ nhớ.
- Có giới hạn file descriptor hoặc tài nguyên khác không? `parallel()` không thay thế quản lý nguồn.
- Kết quả có cần thứ tự không? Collector hiện chỉ tính thống kê, không cần giữ thứ tự đơn hàng.

## 12. Khi nào nên dùng collector có sẵn thay vì tự viết?

Collector tùy biến phù hợp khi cần **nhiều đại lượng với cùng quy tắc dữ liệu**, một lần duyệt và một đối tượng báo cáo nhất quán. Tuy nhiên, không nên tự viết khi API có sẵn đã thể hiện đủ yêu cầu.

| Bài toán | Công cụ thường đơn giản hơn |
|---|---|
| Chỉ tính tổng tiền | `mapToLong(...).sum()` hoặc `Collectors.summingLong(...)` |
| Chỉ đếm số đơn | `count()` hoặc `Collectors.counting()` |
| Cần count/sum/min/max/average của **một trường số** | `summarizingLong(...)` |
| Đếm đơn theo khu vực | `groupingBy(..., counting())` |
| Tổng tiền theo khu vực | `groupingBy(..., summingLong(...))` |
| Muốn kết hợp **hai** collector độc lập | `Collectors.teeing(...)` từ Java 12 |
| Nhiều chỉ số, một DTO nhất quán, trạng thái tùy biến | `Collector.of(...)` |

### 12.1. So sánh với summarizingLong

`Collectors.summarizingLong` tạo `LongSummaryStatistics`, tính count, sum, min, max và average của **một trường số**:

```java
java.util.LongSummaryStatistics stats = orders.stream()
        .filter(Order::isPaid)
        .collect(Collectors.summarizingLong(
                Order::getAmountCents));
```

Cách này rất phù hợp nếu chỉ cần thống kê tiền của các đơn đã thanh toán. Nhưng nó không tự đếm **toàn bộ đơn**, **số đơn chưa thanh toán** và **số đơn theo khu vực** trong cùng một kết quả. Hơn nữa, `LongSummaryStatistics.getAverage()` trả 0 khi count bằng 0; nếu muốn phân biệt không có dữ liệu thì phải kiểm tra `getCount()`.

### 12.2. So sánh với teeing

Java 12 thêm `Collectors.teeing(downstream1, downstream2, merger)` để chạy **hai** collector trên cùng đầu vào rồi gộp hai kết quả cuối thành một:

```java
// Java 12+, chỉ minh họa hai đại lượng:
Map.Entry<Long, Long> totals = orders.stream()
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.summingLong(Order::getAmountCents),
                (count, sum) ->
                        new java.util.AbstractMap.SimpleImmutableEntry<>(
                                count, sum)));
```

Đoạn này tính count của **tất cả** đơn và tổng tiền của **tất cả** đơn, không lọc trạng thái đã thanh toán. Khi cần nhiều đại lượng với các quy tắc con khác nhau, có thể lồng `teeing`, nhưng độ phức tạp kiểu tổng hợp dễ tăng. Collector tùy biến thường rõ ràng hơn nếu có một mô hình KPI thống nhất gồm nhiều bộ đếm và Map.

## 13. Kiểm tra bằng cách chia và gộp thủ công

Không nên chỉ thử ví dụ tuần tự. Một lỗi combiner có thể không bộc lộ cho đến khi chạy song song. Hãy mô phỏng việc chia nguồn thành hai nhánh:

```java
// Đoạn chạy trong lớp MultiMetricCollectorDemo ở phần 5.
MetricsAccumulator left = new MetricsAccumulator();
MetricsAccumulator right = new MetricsAccumulator();

left.add(new Order("A", "BAC", 100L, true));
right.add(new Order("B", "NAM", 200L, true));

Report merged = left.combine(right).finish();

MetricsAccumulator sequential = new MetricsAccumulator();
sequential.add(new Order("A", "BAC", 100L, true));
sequential.add(new Order("B", "NAM", 200L, true));
Report onePass = sequential.finish();

System.out.println(sameReport(merged, onePass)); // true
```

Tiếp tục thử gộp với một trạng thái rỗng, gộp ba nhánh theo hai cách đặt ngoặc khác nhau, các nhánh chỉ có đơn chưa thanh toán và các nhóm trùng khóa. Test thủ công giúp phát hiện lỗi, nhưng **không chứng minh** cho mọi dữ liệu; cần lý giải bằng hợp đồng toán học của bộ tích lũy.

### 13.1. Bộ ca kiểm tra quan trọng

| Ca kiểm tra | Điều phải đúng |
|---|---|
| Nguồn hoàn toàn rỗng | Count và tổng bằng 0; cực trị/trung bình vắng mặt; Map rỗng |
| Một đơn đã thanh toán tiền 0 | Paid count = 1; min/max/average có giá trị 0 |
| Một đơn chưa thanh toán | Tổng đơn = 1, paid = 0, Map khu vực vẫn tăng |
| Tất cả đơn thuộc một khu vực | Count theo khu vực bằng tổng số đơn |
| Các đơn thuộc nhiều khu vực | Sum count của Map bằng tổng số đơn |
| Đảo thứ tự danh sách | Các KPI và Map phải tương đương |
| Chạy tuần tự và song song | Kết quả tương đương trên dữ liệu hợp lệ |
| Gộp với trạng thái rỗng | Kết quả không đổi |
| Gộp ba trạng thái theo hai thứ tự ngoặc | Kết quả tương đương |
| Số tiền âm hoặc region null | Từ chối theo chính sách ví dụ |
| Tổng tiền vượt `long` | Ném `ArithmeticException` thay vì tràn âm |

Với một dự án có kiểm thử tự động, nên dùng JUnit và tạo nhiều tổ hợp dữ liệu nhỏ; nếu kiểm thử hiệu năng, cần đo riêng và tránh coi việc “test thông qua” là bằng chứng collector song song luôn nhanh hơn.

## 14. Các lỗi phổ biến khi viết Collector nhiều chỉ số

| Lỗi | Hậu quả | Hướng sửa |
|---|---|---|
| Tính trung bình bằng cách lấy trung bình hai accumulator | Sai khi các nhánh có kích thước khác nhau | Giữ sum và count; chia ở finisher |
| Combiner chỉ gộp sum, bỏ Map hoặc count | Mất số liệu trên parallel stream | Gộp đủ mọi trường trạng thái |
| Supplier trả cùng một object static | Các nhánh có thể sửa chung container | Tạo trạng thái mới cho mỗi lần supplier được gọi |
| Đánh dấu `CONCURRENT` cho `HashMap` và `long` mutable | Data race khi worker cùng cập nhật | Không công bố `CONCURRENT` nếu accumulator không an toàn đồng thời |
| Đánh dấu `IDENTITY_FINISH` khi `A != R` | Framework có thể bỏ qua finisher | Không dùng characteristic đó |
| Xuất sentinel min/max khi count = 0 | Báo cáo hiển thị cực trị giả | Chuyển thành Optional rỗng |
| `toList` giữ mọi đơn chỉ để tính KPI | Tốn bộ nhớ không cần thiết | Tích lũy chỉ số trực tiếp |
| Dùng `sum` của `int` cho dữ liệu lớn | Tràn số | Dùng kiểu phù hợp, `Math.addExact` hoặc BigInteger |
| Gọi `getAsDouble()` trên Optional rỗng | `NoSuchElementException` | Kiểm tra `isPresent` hoặc dùng chính sách mặc định rõ ràng |
| Dùng `parallelStream()` rồi suy ra nhanh hơn | Overhead, tranh chấp, phân nhánh tốn chi phí | Benchmark theo dữ liệu thật |
| Đọc file bằng `Files.lines` mà không đóng | Rò rỉ file descriptor | `try-with-resources` |
| Lọc bản ghi hỏng mà không báo số lượng bị loại | KPI bị hiểu sai phạm vi dữ liệu | Định nghĩa chính sách kiểm tra và thống kê chất lượng |

## 15. Bài tập nâng cao có hướng dẫn và đáp án

### Bài 1. Bổ sung tỷ lệ đơn đã thanh toán

**Đề bài:** Từ các trường đã có, xây một phương thức `paidRate()` trả `OptionalDouble`. Nếu nguồn rỗng, không trả mặc định 0.

**Đáp án tham khảo:**

```java
OptionalDouble paidRate() {
    return orderCount == 0
            ? OptionalDouble.empty()
            : OptionalDouble.of((double) paidCount / orderCount);
}
```

Đặt phương thức này trong `Report`. Bộ tích lũy không cần trường mới, vì tỷ lệ suy ra được từ hai bộ đếm đã có.

### Bài 2. Thêm tổng tiền đã thanh toán theo khu vực

**Đề bài:** Bổ sung `Map<String, Long> paidCentsByRegion` vào accumulator, rồi cập nhật nó trong các pha.

**Hướng dẫn:** Tại `add` chỉ cộng tiền nếu `order.isPaid()`. Tại `combine` hợp nhất toàn bộ Map của nhánh phải bằng `merge`. Tại `finish` tạo snapshot bất biến. Không quên thử trường hợp một khu vực chỉ có đơn chưa thanh toán: tùy chính sách, nó có thể không xuất hiện trong Map **tiền đã thanh toán**, dù vẫn xuất hiện trong Map **số đơn**.

### Bài 3. Đếm lỗi dữ liệu thay vì ném ngoại lệ

**Đề bài:** Thay chính sách từ chối `Order null` thành báo cáo cả `invalidCount` và `validCount`.

**Gợi ý:** Nếu đầu vào là một Stream có phần tử null, đưa kiểm tra null vào `add` thay vì gọi `Objects.requireNonNull` ngay từ đầu. Với đơn null, tăng `invalidCount` và `return`; với đơn hợp lệ, cập nhật các KPI. `combine` phải cộng thêm `invalidCount`. Định nghĩa rõ `orderCount` là số đơn hợp lệ hay tổng số bản ghi đã đọc và giữ nhất quán qua mọi bước.

### Bài 4. Tạo collector cho điểm thi

**Đề bài:** Thay `Order` bằng `StudentResult(studentId, className, score)`. Tính số bài làm, tổng điểm, điểm thấp nhất, cao nhất, trung bình và số bài theo lớp.

**Đáp án định hướng:** Dùng trạng thái gồm `count`, `sum`, `min`, `max` và `Map<className, count>`; viết các hàm `add`, `combine`, `finish` tương tự. Cần quyết định cho điểm không hợp lệ, dữ liệu thiếu và quy tắc làm tròn trước khi triển khai.

### Bài 5. Phát hiện lỗi kết hợp trung bình

Hai nhánh có dữ liệu: A = `[10]`, B = `[20, 30]`. Một combiner gộp average A và average B bằng cách lấy trung bình của hai giá trị trung bình.

**Đáp án:** Kết quả sai là `(10 + 25) / 2 = 17.5`, còn trung bình đúng là `(10 + 20 + 30) / 3 = 20`. Cần gộp `(sum=10,count=1)` với `(sum=50,count=2)` rồi chia `60/3`.

### Bài 6. Kiểm tra khả năng chạy song song

**Đề bài:** Có cần thêm `Collector.Characteristics.CONCURRENT` để `orders.parallelStream().collect(metricsCollector())` hoạt động không?

**Đáp án:** Không. Collector thông thường có thể chạy song song bằng các container riêng và combiner. Nếu công bố `CONCURRENT` với `HashMap`, các trường `long` và cập nhật mutable không được đồng bộ, chương trình có thể gặp data race.

### Bài 7. Thiết kế một yêu cầu hiệu năng có thể đo được

**Đề bài:** Hãy xác định cách so sánh collector tùy biến với việc chạy nhiều pipeline độc lập.

**Đáp án định hướng:** Dùng cùng dữ liệu và cùng quy tắc KPI, kiểm tra tính đúng trước, làm warm-up, đo nhiều lượt trên các kích thước đại diện, phân biệt trường hợp dữ liệu trong bộ nhớ với I/O, quan sát cả cấp phát bộ nhớ và tải CPU. Với benchmark Java nghiêm túc nên dùng JMH. Đừng mặc định custom collector luôn nhanh hơn: nếu số liệu rất nhỏ hoặc những thống kê có sẵn đủ dùng, sự đơn giản của `summarizingLong` có thể đáng giá hơn.

## 16. Checklist hoàn thành dự án

Một Collector nhiều chỉ số có thể coi là được thiết kế tốt khi trả lời được các câu hỏi sau:

1. **Đã xác định rõ nguồn dữ liệu và phạm vi từng KPI chưa?** Count tất cả bản ghi hay chỉ bản ghi hợp lệ? Tiền xét mọi đơn hay chỉ đơn đã thanh toán?
2. **Trạng thái trung gian có đủ thông tin không?** Đã giữ sum, count và dữ liệu để suy ra mọi chỉ số chưa?
3. **Supplier có tạo trạng thái mới, rỗng và độc lập không?**
4. **Accumulator có xử lý một phần tử theo quy tắc đã công bố và tránh side effect bên ngoài không?**
5. **Combiner có gộp đủ mọi trường và thỏa tính kết hợp không?**
6. **Finisher có trả kết quả không phụ thuộc vào Map mutable nội bộ và xử lý nguồn rỗng đúng không?**
7. **Đã kiểm tra số học chưa?** Có tràn số, mất chính xác thập phân hoặc chia cho 0 không?
8. **Đã kiểm thử tuần tự, song song, nguồn rỗng, một phần tử, dữ liệu hỏng và nhóm trùng khóa chưa?**
9. **Có đang công bố characteristics chính xác không?** Đặc biệt, không đánh dấu `CONCURRENT` hay `IDENTITY_FINISH` tùy tiện.
10. **Có cần collector tùy biến thật không?** `counting`, `summingLong`, `summarizingLong`, `groupingBy` hoặc `teeing` đã giải quyết đủ yêu cầu chưa?

**Kết luận:** Viết Collector tùy biến để tổng hợp nhiều chỉ số không chỉ là gọi `Collector.of`. Bài toán cốt lõi là chọn một **trạng thái có thể gộp**, giữ đủ thông tin cho mọi KPI, bảo đảm **đơn vị – kết hợp – tương đương**, và tách kết quả cuối khỏi trạng thái mutable. Khi thiết kế đúng, cùng một Collector có thể được dùng trên Stream tuần tự, Stream song song hoặc làm downstream của `groupingBy`, đồng thời giúp tiết kiệm các lần duyệt dữ liệu không cần thiết mà vẫn kiểm soát được độ chính xác và tài nguyên.
