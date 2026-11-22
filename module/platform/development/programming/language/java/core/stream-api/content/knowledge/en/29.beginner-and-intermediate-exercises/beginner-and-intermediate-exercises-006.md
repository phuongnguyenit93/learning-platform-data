# Lập báo cáo nhóm bằng Collector nhiều tầng

## 1. Bài toán thực hành và mục tiêu

Trong **JAVA_STREAM_API**, các thao tác `filter`, `map`, `reduce` và `collect` giúp biến một tập bản ghi thành báo cáo mà không phải tự quản lý nhiều vòng lặp lồng nhau. Khi cần thống kê theo **hai hoặc nhiều chiều**, ví dụ vùng bán hàng và kênh bán, ta có thể lồng các collector thay vì dựng `Map` thủ công.

Bài tập này thuộc chương **Bài tập nền tảng và trung cấp**, với một tình huống báo cáo doanh số có thể triển khai và kiểm thử độc lập:

> Từ danh sách đơn hàng, hãy lập báo cáo theo **vùng → kênh bán**, trong đó mỗi nhóm có số đơn đã thanh toán, tổng tiền, giá trị nhỏ nhất, lớn nhất và trung bình. Phải phân biệt nhóm không có đơn đã thanh toán với nhóm không tồn tại trong dữ liệu.

Kết thúc bài, người học có thể:

1. Nhận diện hai khóa nhóm và phác thảo kiểu `Map<K1, Map<K2, D>>` trước khi viết mã.
2. Sử dụng `Collectors.groupingBy` lồng nhau để đếm hoặc cộng dồn theo từng nhóm.
3. Kết hợp `counting`, `summingLong`, `summarizingLong`, `mapping`, `filtering` và `collectingAndThen`.
4. Chọn `LinkedHashMap` cho thứ tự vùng gặp lần đầu và `TreeMap` để sắp kênh theo khóa.
5. Xử lý chính xác nguồn rỗng, nhóm bị lọc hết, giá trị `0` và những trường hợp dữ liệu không hợp lệ.
6. Viết chương trình Java 17 và unit test JUnit 5 kiểm tra **cả nội dung lẫn thứ tự được yêu cầu**.
7. Nhận diện giới hạn của phép cộng `long`, collection mutable, trạng thái dùng chung và xử lý song song.

**Phạm vi:** Đây là một bài hướng dẫn có yêu cầu, ví dụ, lời giải tham khảo và bài mở rộng. Không cần cơ sở dữ liệu, máy chủ hay framework ngoài JDK để chạy phần chính.

## 2. Thiết kế dữ liệu và kết quả mong muốn

### 2.1. Mỗi đơn hàng có những trường gì?

Mô hình tối giản:

```java
record Sale(
    String id,
    String region,
    String channel,
    long amountVnd,
    boolean paid
) {}
```

Ý nghĩa:

| Trường | Kiểu | Vai trò |
| --- | --- | --- |
| `id` | `String` | Định danh đơn hàng |
| `region` | `String` | Khóa nhóm cấp 1, ví dụ `HN`, `HCM`, `DN` |
| `channel` | `String` | Khóa nhóm cấp 2, ví dụ `WEB` hoặc `STORE` |
| `amountVnd` | `long` | Số tiền nguyên đơn vị đồng |
| `paid` | `boolean` | Đơn đã thanh toán hay chưa |

Ở chương trình hoàn chỉnh, constructor của `Sale` sẽ validate `id`, `region`, `channel` và số tiền để không đưa dữ liệu không hợp lệ vào collector.

### 2.2. Bộ dữ liệu đầu vào

| ID | Vùng | Kênh | Số tiền (VND) | Đã thanh toán? |
| --- | --- | --- | ---: | --- |
| O1 | HN | WEB | 120.000 | Có |
| O2 | HN | STORE | 40.000 | Có |
| O3 | HCM | WEB | 70.000 | Có |
| O4 | HN | WEB | 30.000 | Không |
| O5 | HCM | STORE | 50.000 | Có |
| O6 | DN | WEB | 90.000 | Không |
| O7 | DN | STORE | 20.000 | Có |
| O8 | HCM | WEB | 10.000 | Có |

Tổng số đơn trong nguồn là **8**. Có **6 đơn đã thanh toán**, tổng tiền các đơn đã thanh toán bằng **310.000 VND**.

### 2.3. Bảng kết quả chuẩn để đối chiếu

| Vùng | Kênh | Tất cả đơn | Đơn đã thanh toán | Tổng đã thanh toán (VND) | Trung bình đã thanh toán (VND) |
| --- | --- | ---: | ---: | ---: | ---: |
| HN | STORE | 1 | 1 | 40.000 | 40.000 |
| HN | WEB | 2 | 1 | 120.000 | 120.000 |
| HCM | STORE | 1 | 1 | 50.000 | 50.000 |
| HCM | WEB | 2 | 2 | 80.000 | 40.000 |
| DN | STORE | 1 | 1 | 20.000 | 20.000 |
| DN | WEB | 1 | 0 | 0 | **Không có mẫu** |

**Hai yêu cầu về thứ tự:**

- Các vùng theo lần xuất hiện đầu trong danh sách nguồn: **HN → HCM → DN**.
- Các kênh trong mỗi vùng theo thứ tự tên tăng dần: **STORE → WEB**.

Bảng dùng thứ tự đó, không phải vì mọi `Map` của Java đều có thứ tự. Ở lời giải, ta sẽ chọn loại map cụ thể để bảo đảm.

## 3. Bước 1 — Đọc bài toán thành các kiểu kết quả

Trước khi viết lambda, xác định kiểu cần thu:

```text
List<Sale>
    │
    └── Stream<Sale>
            │
            └── groupingBy(region)
                    │
                    ├── HN  ── groupingBy(channel) ── STORE, WEB
                    ├── HCM ── groupingBy(channel) ── STORE, WEB
                    └── DN  ── groupingBy(channel) ── STORE, WEB
                                                        │
                                                        └── downstream statistic
```

Ba dạng kết quả sẽ được xây dựng theo mức tăng dần:

```java
// A. Đếm tất cả đơn, chưa lọc paid.
Map<String, Map<String, Long>>

// B. Tổng tiền đơn đã thanh toán.
Map<String, Map<String, Long>>

// C. Bản báo cáo chi tiết cho mọi nhóm xuất hiện trong nguồn.
Map<String, Map<String, Cell>>
```

`Cell` là một record chứa số mẫu, tổng tiền, min/max và trung bình của **những đơn đã thanh toán**.

Lưu ý, hai dạng A và B có cùng **kiểu Java** nhưng **ý nghĩa thống kê khác**; đặt tên biến/phương thức sao cho người đọc không nhầm “số đơn” với “tiền”. Trong code hoàn chỉnh, ta dùng `LinkedHashMap<String, TreeMap<String, ...>>` để làm rõ loại map ngoài và map trong.

## 4. Bước 2 — Phân nhóm hai tầng và đếm số bản ghi

Mẫu cơ bản:

```java
Collectors.groupingBy(
    Sale::region,                  // Nhóm cấp 1.
    LinkedHashMap::new,            // Factory map ngoài.
    Collectors.groupingBy(
        Sale::channel,             // Nhóm cấp 2.
        TreeMap::new,              // Factory map trong.
        Collectors.counting()      // Giá trị mỗi nhóm cấp 2.
    )
)
```

Khi áp dụng vào `sales.stream().collect(...)`, ta được:

```java
LinkedHashMap<String, TreeMap<String, Long>> counts =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        LinkedHashMap::new,
        Collectors.groupingBy(
            Sale::channel,
            TreeMap::new,
            Collectors.counting()
        )
    ));
```

**Cách đọc từ trong ra ngoài:**

1. `Collectors.counting()` nhận các `Sale` trong một cặp vùng/kênh và tạo `Long`.
2. `groupingBy(Sale::channel, TreeMap::new, counting())` tạo một `TreeMap<String,Long>` cho từng vùng.
3. `groupingBy(Sale::region, LinkedHashMap::new, ...)` tạo `LinkedHashMap<String,TreeMap<String,Long>>`.
4. `collect` tiêu thụ `Stream<Sale>` và trả map hoàn chỉnh.

Kết quả đếm chuẩn:

```text
HN:
    STORE -> 1
    WEB   -> 2
HCM:
    STORE -> 1
    WEB   -> 2
DN:
    STORE -> 1
    WEB   -> 1
```

**Tự kiểm tra:** tổng tất cả count ở các ô phải bằng `8`; riêng `HN/WEB` có 2 đơn kể cả đơn chưa thanh toán O4. Nếu chỉ muốn đếm đã thanh toán, cần một quy tắc lọc ở bước sau.

## 5. Bước 3 — Lọc trước khi nhóm để tính tổng tiền đã thanh toán

Nếu báo cáo chỉ cần những nhóm **có ít nhất một đơn đã thanh toán**, lọc trước khi tạo nhóm là tự nhiên:

```java
LinkedHashMap<String, TreeMap<String, Long>> paidTotals =
    sales.stream()
        .filter(Sale::paid)
        .collect(Collectors.groupingBy(
            Sale::region,
            LinkedHashMap::new,
            Collectors.groupingBy(
                Sale::channel,
                TreeMap::new,
                Collectors.summingLong(Sale::amountVnd)
            )
        ));
```

Với dữ liệu mẫu:

```text
HN:
    STORE -> 40000
    WEB   -> 120000
HCM:
    STORE -> 50000
    WEB   -> 80000
DN:
    STORE -> 20000
    // Không có khóa WEB.
```

Giải thích trường hợp `DN/WEB`: O6 có vùng DN, kênh WEB, nhưng chưa thanh toán. `filter(Sale::paid)` loại O6 **trước khi** các tầng grouping gặp nó, nên map không có ô `DN/WEB`. Khi muốn hiển thị đầy đủ những nhóm từng tồn tại, cách này không đủ.

**Đừng nhầm:** “không có khóa” khác “có khóa với tổng bằng 0”. Với dữ liệu giao dịch, cả hai có thể cần biểu diễn riêng.

## 6. Bước 4 — Giữ ô nhóm, chỉ lọc dữ liệu thống kê bằng `Collectors.filtering`

`Collectors.filtering` (Java 9+) là một **downstream collector**. Đặt nó **bên trong grouping** sẽ giữ các nhóm mà collector ngoài đã nhìn thấy, kể cả khi không có phần tử nào vượt qua predicate của downstream.

```java
LinkedHashMap<String, TreeMap<String, Long>> paidTotalsKeepingCells =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        LinkedHashMap::new,
        Collectors.groupingBy(
            Sale::channel,
            TreeMap::new,
            Collectors.filtering(
                Sale::paid,
                Collectors.summingLong(Sale::amountVnd)
            )
        )
    ));
```

Bây giờ:

```text
HN:  STORE -> 40000, WEB -> 120000
HCM: STORE -> 50000, WEB -> 80000
DN:  STORE -> 20000, WEB -> 0
```

Vì sao vẫn có `DN/WEB`? Collector cấp vùng và kênh thấy O6 nên **tạo nhóm DN/WEB**. Downstream `filtering(Sale::paid, ...)` bỏ O6, còn `summingLong` trên tập rỗng trả tổng bằng `0L`.

Tuy nhiên, số `0` **chưa đủ** để biết nhóm có mẫu nào đã thanh toán hay không. Một đơn hợp lệ có số tiền `0` cũng làm tổng bằng `0`. Bước tiếp theo sẽ dùng `summarizingLong` để giữ cả `count` và `sum`.

## 7. Bước 5 — Thu đầy đủ `count`, `sum`, `min`, `max` và `average`

Thay vì tạo năm pipeline hoặc năm map riêng, dùng `Collectors.summarizingLong` để tạo `LongSummaryStatistics` cho mỗi ô.

```java
LinkedHashMap<String, TreeMap<String, LongSummaryStatistics>> stats =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        LinkedHashMap::new,
        Collectors.groupingBy(
            Sale::channel,
            TreeMap::new,
            Collectors.filtering(
                Sale::paid,
                Collectors.summarizingLong(Sale::amountVnd)
            )
        )
    ));
```

Ví dụ:

```java
LongSummaryStatistics hcmWeb = stats.get("HCM").get("WEB");

System.out.println(hcmWeb.getCount());   // 2
System.out.println(hcmWeb.getSum());     // 80000
System.out.println(hcmWeb.getMin());     // 10000
System.out.println(hcmWeb.getMax());     // 70000
System.out.println(hcmWeb.getAverage()); // 40000.0
```

### 7.1. Tập rỗng và giá trị sentinel

Với ô `DN/WEB`, `LongSummaryStatistics` có:

```java
LongSummaryStatistics dnWeb = stats.get("DN").get("WEB");

System.out.println(dnWeb.getCount()); // 0
System.out.println(dnWeb.getSum());   // 0
System.out.println(dnWeb.getMin());   // Long.MAX_VALUE
System.out.println(dnWeb.getMax());   // Long.MIN_VALUE
System.out.println(dnWeb.getAverage()); // 0.0
```

**Không** coi `Long.MAX_VALUE` là min thực và `Long.MIN_VALUE` là max thực ở một nhóm không có mẫu. `getAverage() == 0.0` cũng không có nghĩa đã quan sát giá trị trung bình 0.

Quy tắc hiển thị:

- `count > 0`: min/max/average là các số liệu của nhóm.
- `count == 0`: min/max/average nên hiển thị là **“Chưa có dữ liệu”** hoặc kiểu tùy chọn rỗng.

### 7.2. `LongSummaryStatistics` là đối tượng mutable

`LongSummaryStatistics` có các phương thức `accept(...)` và `combine(...)`. Caller có thể làm thay đổi số liệu sau khi thu thập; vì vậy, **không** xem `Map<String,Map<String,LongSummaryStatistics>>` là báo cáo bất biến. Để công bố kết quả ổn định, nên tạo DTO/record chỉ chứa các trường cần thiết.

## 8. Bước 6 — Hoàn thiện từng ô bằng `collectingAndThen`

Tạo kiểu kết quả:

```java
record Cell(
    long paidCount,
    long totalVnd,
    OptionalLong minVnd,
    OptionalLong maxVnd,
    OptionalDouble averageVnd
) {}
```

`OptionalLong` và `OptionalDouble` biểu diễn **có hoặc không có số liệu**. Với ô có `paidCount == 0`, ba trường min/max/average sẽ rỗng.

Sơ đồ composed collector:

```text
Sale
  │
  └── groupingBy(region, LinkedHashMap)
          │
          └── groupingBy(channel, TreeMap)
                  │
                  └── filtering(paid)
                          │
                          └── summarizingLong(amountVnd)
                                  │
                                  └── collectingAndThen(finisher)
                                         │
                                         ▼
                                        Cell
```

Hàm finisher nhận `LongSummaryStatistics` và trả `Cell`:

```java
Collectors.collectingAndThen(
    Collectors.summarizingLong(Sale::amountVnd),
    s -> new Cell(
        s.getCount(),
        s.getSum(),
        s.getCount() > 0
            ? OptionalLong.of(s.getMin()) : OptionalLong.empty(),
        s.getCount() > 0
            ? OptionalLong.of(s.getMax()) : OptionalLong.empty(),
        s.getCount() > 0
            ? OptionalDouble.of(s.getAverage()) : OptionalDouble.empty()
    )
)
```

Khi kết hợp `Collectors.filtering` bên ngoài finisher, mỗi ô có một `Cell` hoàn chỉnh. Đây là **phép thu thập nhiều tầng**: collector ngoài nhóm dữ liệu, collector trong chọn mẫu, bộ thống kê tích lũy số liệu, finisher chuyển kết quả mutable thành một kiểu giá trị dễ sử dụng.

## 9. Lời giải tham khảo hoàn chỉnh (Java 17+)

Đoạn chương trình dưới đây có thể lưu thành `SalesGroupReport.java`, biên dịch và chạy với JDK 17 trở lên. Đây là **bản tham khảo độc lập**, không phụ thuộc các đoạn code lẻ ở trên.

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Objects;
import java.util.OptionalDouble;
import java.util.OptionalLong;
import java.util.TreeMap;
import java.util.function.Function;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public final class SalesGroupReport {

    private SalesGroupReport() {}

    public record Sale(
        String id,
        String region,
        String channel,
        long amountVnd,
        boolean paid
    ) {
        public Sale {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(region, "region");
            Objects.requireNonNull(channel, "channel");
            if (id.isBlank() || region.isBlank() || channel.isBlank()) {
                throw new IllegalArgumentException("Các mã không được rỗng");
            }
            if (amountVnd < 0L) {
                throw new IllegalArgumentException("amountVnd phải >= 0");
            }
        }
    }

    public record Cell(
        long paidCount,
        long totalVnd,
        OptionalLong minVnd,
        OptionalLong maxVnd,
        OptionalDouble averageVnd
    ) {}

    public static List<Sale> sample() {
        return List.of(
            new Sale("O1", "HN", "WEB",   120_000L, true),
            new Sale("O2", "HN", "STORE",  40_000L, true),
            new Sale("O3", "HCM", "WEB",   70_000L, true),
            new Sale("O4", "HN", "WEB",    30_000L, false),
            new Sale("O5", "HCM", "STORE", 50_000L, true),
            new Sale("O6", "DN", "WEB",    90_000L, false),
            new Sale("O7", "DN", "STORE",  20_000L, true),
            new Sale("O8", "HCM", "WEB",   10_000L, true)
        );
    }

    // Bước 2: đếm mọi đơn theo vùng rồi kênh.
    public static LinkedHashMap<String, TreeMap<String, Long>>
    countAll(List<Sale> source) {
        Objects.requireNonNull(source, "source");
        return source.stream().collect(Collectors.groupingBy(
            Sale::region,
            LinkedHashMap::new,
            Collectors.groupingBy(
                Sale::channel,
                TreeMap::new,
                Collectors.counting()
            )
        ));
    }

    // Bước 3: chỉ tạo nhóm cho các đơn đã thanh toán.
    public static LinkedHashMap<String, TreeMap<String, Long>>
    paidTotalsFilteringBeforeGrouping(List<Sale> source) {
        Objects.requireNonNull(source, "source");
        return source.stream()
            .filter(Sale::paid)
            .collect(Collectors.groupingBy(
                Sale::region,
                LinkedHashMap::new,
                Collectors.groupingBy(
                    Sale::channel,
                    TreeMap::new,
                    Collectors.summingLong(Sale::amountVnd)
                )
            ));
    }

    // Downstream của mỗi ô: lọc paid, thống kê và tạo Cell.
    private static Collector<Sale, ?, Cell> paidCellCollector() {
        return Collectors.filtering(
            Sale::paid,
            Collectors.collectingAndThen(
                Collectors.summarizingLong(Sale::amountVnd),
                stats -> {
                    boolean hasSamples = stats.getCount() > 0L;
                    return new Cell(
                        stats.getCount(),
                        stats.getSum(),
                        hasSamples
                            ? OptionalLong.of(stats.getMin())
                            : OptionalLong.empty(),
                        hasSamples
                            ? OptionalLong.of(stats.getMax())
                            : OptionalLong.empty(),
                        hasSamples
                            ? OptionalDouble.of(stats.getAverage())
                            : OptionalDouble.empty()
                    );
                }
            )
        );
    }

    // Bước 6: tạo đủ ô cho mọi cặp region/channel từng xuất hiện.
    public static LinkedHashMap<String, TreeMap<String, Cell>>
    reportKeepingExistingGroups(List<Sale> source) {
        Objects.requireNonNull(source, "source");
        return source.stream().collect(Collectors.groupingBy(
            Sale::region,
            LinkedHashMap::new,
            Collectors.groupingBy(
                Sale::channel,
                TreeMap::new,
                paidCellCollector()
            )
        ));
    }

    public static long overallPaidCount(
        LinkedHashMap<String, TreeMap<String, Cell>> report
    ) {
        return report.values().stream()
            .flatMap(inner -> inner.values().stream())
            .mapToLong(Cell::paidCount)
            .sum();
    }

    public static long overallPaidAmount(
        LinkedHashMap<String, TreeMap<String, Cell>> report
    ) {
        return report.values().stream()
            .flatMap(inner -> inner.values().stream())
            .mapToLong(Cell::totalVnd)
            .sum();
    }

    public static void main(String[] args) {
        List<Sale> source = sample();
        var allCounts = countAll(source);
        var paidTotals = paidTotalsFilteringBeforeGrouping(source);
        var report = reportKeepingExistingGroups(source);

        System.out.println(List.copyOf(report.keySet()));
        // [HN, HCM, DN]

        System.out.println(List.copyOf(report.get("HN").keySet()));
        // [STORE, WEB]

        System.out.println(allCounts.get("HN").get("WEB")); // 2
        System.out.println(paidTotals.get("HCM").get("WEB")); // 80000
        System.out.println(paidTotals.get("DN").containsKey("WEB"));
        // false, vì đã lọc trước khi nhóm.

        System.out.println(report.get("HCM").get("WEB"));
        // Cell[paidCount=2, totalVnd=80000, minVnd=OptionalLong[10000],
        //      maxVnd=OptionalLong[70000], averageVnd=OptionalDouble[40000.0]]

        Cell noPaid = report.get("DN").get("WEB");
        System.out.println(noPaid.paidCount()); // 0
        System.out.println(noPaid.totalVnd());  // 0
        System.out.println(noPaid.averageVnd().isEmpty()); // true

        System.out.println(overallPaidCount(report));  // 6
        System.out.println(overallPaidAmount(report)); // 310000
    }
}
```

### 9.1. Lý do tách `paidCellCollector` ra một phương thức

Nếu viết tất cả các lambda trong một biểu thức `groupingBy` dài, nhiều tầng ngoặc và generic làm bài khó đọc. Phương thức:

```java
private static Collector<Sale, ?, Cell> paidCellCollector()
```

giữ được hợp đồng đầu vào `Sale` và đầu ra `Cell`, đồng thời **giấu kiểu trạng thái tích lũy `A`** của collector. Việc tách này giúp kiểm thử riêng logic thống kê mà không cần dựng toàn bộ bản đồ hai tầng.

### 9.2. Vòng đời các collector trong lời giải

| Tầng | Input | Kết quả | Trách nhiệm |
| --- | --- | --- | --- |
| Stream ban đầu | `Sale` | `Stream<Sale>` | Cung cấp bản ghi theo thứ tự `List` |
| Outer grouping | `Sale` | `LinkedHashMap<String,...>` | Gom theo `region` |
| Inner grouping | `Sale` | `TreeMap<String,Cell>` | Gom theo `channel` |
| Downstream filtering | `Sale` | Kết quả downstream | Chỉ gửi đơn `paid == true` vào thống kê |
| Downstream summarizing | `Sale` | `LongSummaryStatistics` | Count/sum/min/max/average |
| Finisher | `LongSummaryStatistics` | `Cell` | Chuyển sentinel của nhóm rỗng thành Optional rỗng |

Điều quan trọng là **giữ toàn bộ cặp khóa đã xuất hiện**, không phải tạo mọi tổ hợp vùng và kênh có thể có. Nếu nguồn chỉ chứa `HN/WEB` thì collector không tự tạo `HN/STORE`. Muốn đầy đủ những tổ hợp quy định trong cấu hình, cần một bước dựng khung nhóm theo tập khóa hợp lệ sau đó bổ sung dữ liệu.

## 10. Những lựa chọn thiết kế làm thay đổi báo cáo

### 10.1. Thứ tự map ngoài và map trong

`LinkedHashMap::new` giữ thứ tự **chèn khóa lần đầu** trong pipeline tuần tự có encounter order; ở dataset này, thứ tự vùng là `HN, HCM, DN`. `TreeMap::new` sắp kênh theo thứ tự tự nhiên của `String`; ở đây là `STORE, WEB`.

Nếu không cần thứ tự, overload `groupingBy(classifier, downstream)` ngắn hơn nhưng không cam kết kiểu map hoặc thứ tự duyệt khóa. Nếu muốn sắp cả vùng, có thể dùng `TreeMap::new` cho outer grouping. Nếu muốn giữ thứ tự kênh gặp lần đầu, dùng `LinkedHashMap::new` cho inner grouping.

**Không kiểm thử thứ tự chỉ bằng `Map.equals`:** hai map có thể `equals` vì ánh xạ khóa–giá trị giống nhau, dù thứ tự `keySet()` khác. Hãy so sánh một `List` tạo từ `keySet()` khi thứ tự là một yêu cầu riêng.

### 10.2. Nguồn rỗng và nguồn sau lọc rỗng

`List.<Sale>of()` dẫn đến map ngoài **rỗng**, không phải map chứa các vùng với số 0. Một nguồn chỉ có các đơn chưa thanh toán vẫn tạo các nhóm/ô trong `reportKeepingExistingGroups`, nhưng mọi `Cell` có `paidCount == 0` và các Optional rỗng.

Đó là ba trạng thái khác nhau:

| Trạng thái | Biểu diễn |
| --- | --- |
| Không có bản ghi nguồn | Map rỗng |
| Có bản ghi trong vùng/kênh nhưng không có đơn đã thanh toán | Có ô, `paidCount == 0` |
| Có đơn đã thanh toán nhưng tổng tiền bằng 0 | Có ô, `paidCount > 0` và `totalVnd == 0` |

### 10.3. `null` và khóa nhóm

`Collectors.groupingBy` không cho classifier trả khóa `null` trong các triển khai JDK thông dụng; đồng thời `TreeMap` tự nhiên không hỗ trợ khóa chuỗi null. Code tham khảo từ chối `region == null` hoặc `channel == null` ngay ở constructor `Sale`.

Nếu nguồn chứa **phần tử `Sale` bằng `null`**, các method reference `Sale::region` và `Sale::channel` có thể ném `NullPointerException` khi truy cập. Cần validate nguồn hoặc áp dụng `filter(Objects::nonNull)` **chỉ nếu** bỏ dòng lỗi được nghiệp vụ cho phép. Tránh âm thầm giảm tổng doanh thu do dữ liệu thiếu.

### 10.4. Tràn số `long`

`Collectors.summingLong` và `LongSummaryStatistics` không tự bảo đảm phát hiện tràn `long`. Với số tiền có thể vượt `Long.MAX_VALUE`, kết quả có thể bị sai. Nếu yêu cầu tài chính tuyệt đối, cân nhắc `BigInteger` hoặc `BigDecimal` và một collector chính xác phù hợp. Ví dụ tổng tiền nguyên đồng theo nhóm bằng `BigInteger`:

```java
import java.math.BigInteger;

var exactTotals = SalesGroupReport.sample().stream()
    .filter(SalesGroupReport.Sale::paid)
    .collect(Collectors.groupingBy(
        SalesGroupReport.Sale::region,
        Collectors.reducing(
            BigInteger.ZERO,
            sale -> BigInteger.valueOf(sale.amountVnd()),
            BigInteger::add
        )
    ));
```

Trong ví dụ chính, các số tiền nằm trong miền `long`; đây là bài học về **Collector nhiều tầng**, không phải một thư viện kế toán hoàn chỉnh.

### 10.5. Tính bất biến của kết quả

`Cell` là record với các trường `long` và Optional nên không có thao tác sửa thuộc tính trực tiếp. Nhưng hai map `LinkedHashMap` và `TreeMap` trả về vẫn mutable: người gọi có thể `put` hoặc `remove`.

Nếu một API cần xuất bản một snapshot không thể sửa đổi và **vẫn giữ thứ tự**, có thể tạo bản sao map trong `LinkedHashMap`, các map con trong `TreeMap`, rồi bọc bằng `Collections.unmodifiableMap` hoặc `Collections.unmodifiableSortedMap` tương ứng. Chỉ bọc một view mà không sao chép sẽ không ngăn một nơi khác sửa map gốc. `Map.copyOf` không cam kết giữ thứ tự duyệt khóa của nguồn.

## 11. Mở rộng một: thêm danh sách ID theo từng ô với `mapping`

Khi một báo cáo cần kiểm tra những đơn nào thuộc nhóm, `Collectors.mapping` chuyển từng `Sale` thành `id` **trong downstream** mà không thay đổi khóa nhóm.

```java
LinkedHashMap<String, TreeMap<String, List<String>>> paidIds =
    SalesGroupReport.sample().stream()
        .collect(Collectors.groupingBy(
            SalesGroupReport.Sale::region,
            LinkedHashMap::new,
            Collectors.groupingBy(
                SalesGroupReport.Sale::channel,
                TreeMap::new,
                Collectors.filtering(
                    SalesGroupReport.Sale::paid,
                    Collectors.mapping(
                        SalesGroupReport.Sale::id,
                        Collectors.toList()
                    )
                )
            )
        ));

System.out.println(paidIds.get("HCM").get("WEB")); // [O3, O8]
System.out.println(paidIds.get("DN").get("WEB"));  // []
```

Chú ý sự khác nhau giữa:

- `stream.map(Sale::id)` **trước grouping**: stream không còn kiểu `Sale`, nên không thể trực tiếp gọi `Sale::region` hoặc `Sale::channel` nữa.
- `Collectors.mapping(Sale::id, toList())` **sau khi đã xác định hai khóa**: collector ngoài vẫn nhận `Sale`, còn downstream chỉ giữ ID.

### 11.1. Đề bài trung cấp: trả danh sách ID không trùng

Thay `Collectors.toList()` bằng `Collectors.toSet()` nếu nghiệp vụ muốn bỏ giá trị ID trùng. Nhưng `toSet()` **không cam kết thứ tự**. Nếu muốn ID phân biệt và được sắp tăng, có thể dùng `Collectors.toCollection(TreeSet::new)` hoặc tiếp tục `collectingAndThen` để chuyển Set thành danh sách sắp.

Tùy nghiệp vụ, việc hai đơn cùng `id` có thể là **lỗi dữ liệu**; đừng tự loại trùng nếu yêu cầu báo cáo cần phát hiện lỗi.

## 12. Mở rộng hai: `teeing` cho hai chỉ số độc lập

`Collectors.teeing` được giới thiệu từ **Java 12**. Nó gửi cùng các phần tử đến **hai downstream collector** rồi kết hợp hai kết quả bằng một hàm.

Ví dụ báo cáo mỗi vùng gồm số đơn và tổng tiền đã thanh toán:

```java
import java.util.Map;
import java.util.stream.Collectors;

record CountAndAmount(long count, long amountVnd) {}

Map<String, CountAndAmount> byRegion =
    SalesGroupReport.sample().stream()
        .filter(SalesGroupReport.Sale::paid)
        .collect(Collectors.groupingBy(
            SalesGroupReport.Sale::region,
            Collectors.teeing(
                Collectors.counting(),
                Collectors.summingLong(
                    SalesGroupReport.Sale::amountVnd
                ),
                CountAndAmount::new
            )
        ));

System.out.println(byRegion.get("HN"));
// CountAndAmount[count=2, amountVnd=160000]
```

`teeing` hữu ích khi hai chỉ số có cách tích lũy riêng nhưng muốn tạo một kết quả chung. Tuy nhiên, nếu cần `count + sum + min + max + average` của **cùng một trường số**, `summarizingLong` thường đơn giản hơn.

### 12.1. Vì sao không nên lấy trung bình các trung bình nhóm?

HN có 2 đơn đã thanh toán, HCM có 3, DN có 1. Trung bình doanh thu trên mỗi đơn toàn hệ thống phải là:

\[
\mathrm{averageAll}
= \frac{160000 + 130000 + 20000}{2 + 3 + 1}
= \frac{310000}{6}
\approx 51666.67 \text{ VND}
\]

**Không** lấy trung bình đơn giản của ba giá trị trung bình vùng khi kích thước nhóm khác nhau:

```text
HN:  160000 / 2 = 80000
HCM: 130000 / 3 ≈ 43333.33
DN:   20000 / 1 = 20000
```

Trung bình của ba số này không bằng trung bình của 6 đơn. Muốn gộp thống kê, phải gộp **tổng** và **số mẫu**, hoặc dùng một collector trên toàn nguồn.

## 13. Kiểm thử với JUnit 5

Những unit test sau tham chiếu lớp `SalesGroupReport` ở mục 9. Đặt test trong package phù hợp và thêm JUnit Jupiter theo cấu hình dự án.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;

class SalesGroupReportTest {

    @Test
    void countsEverySourceRowExactlyOnce() {
        var counts = SalesGroupReport.countAll(
            SalesGroupReport.sample()
        );

        long total = counts.values().stream()
            .flatMap(inner -> inner.values().stream())
            .mapToLong(Long::longValue)
            .sum();

        assertEquals(8L, total);
        assertEquals(Long.valueOf(2L), counts.get("HN").get("WEB"));
        assertEquals(Long.valueOf(1L), counts.get("DN").get("STORE"));
    }

    @Test
    void preservesSpecifiedRegionAndChannelOrder() {
        var report = SalesGroupReport.reportKeepingExistingGroups(
            SalesGroupReport.sample()
        );

        assertEquals(List.of("HN", "HCM", "DN"),
            new ArrayList<>(report.keySet()));
        assertEquals(List.of("STORE", "WEB"),
            new ArrayList<>(report.get("HN").keySet()));
    }

    @Test
    void filteringBeforeGroupingRemovesUnpaidOnlyCell() {
        var filtered =
            SalesGroupReport.paidTotalsFilteringBeforeGrouping(
                SalesGroupReport.sample()
            );

        assertFalse(filtered.get("DN").containsKey("WEB"));
        assertEquals(Long.valueOf(80_000L),
            filtered.get("HCM").get("WEB"));
    }

    @Test
    void downstreamFilteringKeepsCellWithoutPaidSamples() {
        var report = SalesGroupReport.reportKeepingExistingGroups(
            SalesGroupReport.sample()
        );
        var cell = report.get("DN").get("WEB");

        assertEquals(0L, cell.paidCount());
        assertEquals(0L, cell.totalVnd());
        assertTrue(cell.minVnd().isEmpty());
        assertTrue(cell.maxVnd().isEmpty());
        assertTrue(cell.averageVnd().isEmpty());
    }

    @Test
    void reportsValuesForGroupWithTwoPaidSales() {
        var report = SalesGroupReport.reportKeepingExistingGroups(
            SalesGroupReport.sample()
        );
        var hcmWeb = report.get("HCM").get("WEB");

        assertEquals(2L, hcmWeb.paidCount());
        assertEquals(80_000L, hcmWeb.totalVnd());
        assertEquals(10_000L, hcmWeb.minVnd().orElseThrow());
        assertEquals(70_000L, hcmWeb.maxVnd().orElseThrow());
        assertEquals(40_000.0,
            hcmWeb.averageVnd().orElseThrow(), 1e-9);
    }

    @Test
    void overallCountsAndAmountsMatchControlTotals() {
        var report = SalesGroupReport.reportKeepingExistingGroups(
            SalesGroupReport.sample()
        );

        assertEquals(6L, SalesGroupReport.overallPaidCount(report));
        assertEquals(310_000L,
            SalesGroupReport.overallPaidAmount(report));
    }

    @Test
    void emptySourceReturnsEmptyOuterMap() {
        var empty = List.<SalesGroupReport.Sale>of();

        assertTrue(SalesGroupReport.countAll(empty).isEmpty());
        assertTrue(SalesGroupReport.reportKeepingExistingGroups(
            empty
        ).isEmpty());
    }

    @Test
    void zeroAmountIsDifferentFromNoSamples() {
        var source = List.of(
            new SalesGroupReport.Sale(
                "Z1", "HN", "WEB", 0L, true
            ),
            new SalesGroupReport.Sale(
                "Z2", "DN", "STORE", 10L, false
            )
        );

        var report = SalesGroupReport.reportKeepingExistingGroups(
            source
        );

        assertEquals(1L, report.get("HN").get("WEB").paidCount());
        assertEquals(0L, report.get("HN").get("WEB").totalVnd());
        assertTrue(report.get("HN").get("WEB")
            .averageVnd().isPresent());
        assertTrue(report.get("DN").get("STORE")
            .averageVnd().isEmpty());
    }

    @Test
    void invalidInputFailsExplicitly() {
        assertThrows(NullPointerException.class, () ->
            SalesGroupReport.reportKeepingExistingGroups(null)
        );
        assertThrows(NullPointerException.class, () ->
            new SalesGroupReport.Sale(
                "X", null, "WEB", 10L, true
            )
        );
        assertThrows(IllegalArgumentException.class, () ->
            new SalesGroupReport.Sale(
                "Y", "HN", "WEB", -1L, true
            )
        );
    }
}
```

**Cách tự đánh giá:** nếu các phép thử về **tổng count**, **tổng tiền**, **ô rỗng** và **thứ tự khóa** đều đúng, pipeline đã đáp ứng các hợp đồng cơ bản của bài tập. Unit test không thay thế đánh giá miền dữ liệu thực, nhưng giúp phát hiện lỗi nhóm sai khóa, thiếu bản ghi hoặc lẫn lộn `filter` với downstream `filtering`.

## 14. Những sai lầm thường gặp khi viết collector nhiều tầng

| Sai lầm | Hậu quả | Hướng sửa |
| --- | --- | --- |
| Lọc `paid` trước grouping nhưng vẫn muốn giữ nhóm chỉ có đơn chưa thanh toán | Nhóm bị mất khỏi map | Dùng downstream `filtering` |
| `groupingBy(Sale::region, toList())` rồi lọc, nhóm lại thủ công nhiều lần | Nhiều lượt xử lý và code dài | Lồng downstream `groupingBy` |
| `map(Sale::id)` trước khi phân nhóm theo `region` | Mất thông tin region/channel trong stream | Dùng downstream `mapping` |
| Dùng `HashMap` rồi tin vào thứ tự hiển thị | Thứ tự không được cam kết | Chọn `LinkedHashMap` hoặc `TreeMap` tường minh |
| Đọc min/max của thống kê rỗng | Nhận giá trị sentinel không phải số đo | Kiểm tra `count`, dùng Optional |
| Xem tổng bằng 0 là không có đơn | Nhầm với đơn hợp lệ có số tiền 0 | Lưu cả `count` |
| Dùng `Long::sum`/`summingLong` khi tổng có thể vượt `long` | Tràn số không được phát hiện | Dùng số học lớn hoặc kiểm tra phù hợp |
| Sửa `List` nguồn trong mapper/collector | Vi phạm non-interference | Giữ mapper và classifier thuần |
| Trả `LongSummaryStatistics` rồi coi là immutable | Caller có thể `accept/combine` | Dùng `collectingAndThen` thành record |
| Giữ mọi đơn bằng `toList` dù chỉ cần số liệu | Bộ nhớ tăng không cần thiết | Downstream `counting`/`summarizingLong` |
| Dùng `groupingByConcurrent` rồi đòi thứ tự chèn | Concurrent grouping là unordered | Phân nhóm tuần tự hoặc sắp sau thu thập |
| Tạo test chỉ so `Map.equals` | Không phát hiện lỗi thứ tự khóa | So `List.copyOf(map.keySet())` |

## 15. Xử lý song song và nguồn dữ liệu có tài nguyên

### 15.1. Collector thường vẫn có thể chạy với parallel stream

`Collectors.groupingBy` không phải concurrent collector theo mặc định, nhưng có thể được sử dụng trên `parallelStream()`: Stream framework tích lũy các container cục bộ rồi dùng combiner để gộp. Không tự chia sẻ một `HashMap` hoặc `ArrayList` giữa các thread bằng `forEach`.

Tuy nhiên, nếu báo cáo **bắt buộc giữ thứ tự lần gặp đầu của vùng**, phiên bản **tuần tự từ `List` có encounter order** là lựa chọn dễ diễn giải và kiểm thử nhất. Khi dữ liệu lớn, có thể cân nhắc grouping song song rồi **sắp lại kết quả theo thứ tự được định nghĩa tường minh**, nhưng phải đo chi phí.

`Collectors.groupingByConcurrent` trả `ConcurrentMap` và là collector unordered; nó không thay thế trực tiếp yêu cầu giữ thứ tự `LinkedHashMap`. Dù kết quả con là list, đừng mặc định thứ tự list hoặc an toàn ghi đồng thời sau khi `collect` kết thúc.

### 15.2. Không nhầm nguồn rỗng với lỗi đọc dữ liệu

Nếu dữ liệu đến từ `Files.lines(path)` hoặc một stream I/O, cần xác định ai đóng tài nguyên:

```java
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static Map<String, Long> wordCountsByInitial(Path path)
    throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines
            .flatMap(line -> java.util.Arrays.stream(
                line.strip().split("\\s+")
            ))
            .filter(word -> !word.isEmpty())
            .collect(Collectors.groupingBy(
                word -> word.substring(0, 1),
                Collectors.counting()
            ));
    }
}
```

Đây là một **minh họa độc lập về tài nguyên**, không phải bản phân nhóm `Sale`. `Files.lines` phải được đóng qua `try-with-resources`; nếu tệp không đọc được, chương trình cần báo lỗi thay vì tự coi đó là một tập dữ liệu rỗng.

### 15.3. Chi phí bộ nhớ và hiệu năng

Map nhiều tầng có số entry tỷ lệ với **số cặp khóa thực sự xuất hiện**. Nếu có rất nhiều vùng/kênh, việc tạo nhiều `TreeMap` và bộ thống kê cho từng ô sẽ tốn bộ nhớ. Đổi lại, `summarizingLong` chỉ giữ trạng thái số cho mỗi ô, rẻ hơn lưu toàn bộ đơn trong `List` nếu không cần chi tiết từng đơn.

Việc xử lý song song chỉ có thể hiệu quả khi chi phí xử lý mỗi bản ghi đủ lớn và phân bố khóa hợp lý. Nếu một vùng hoặc kênh chiếm gần hết dữ liệu, chi phí gộp và tranh chấp có thể lớn. Đánh giá hiệu năng bằng benchmark có warm-up trên dữ liệu đại diện; không kết luận từ một lần `System.nanoTime()`.

## 16. Bài tập mở rộng không có lời giải sẵn

Sau khi hoàn thành chương trình chính, hãy thử các yêu cầu sau. Mỗi yêu cầu phải đi kèm **kiểu đầu ra**, **dữ liệu kiểm thử** và **hợp đồng trường hợp rỗng** rõ ràng.

### Bài A — Thêm chiều thứ ba

Thêm trường `String productType` vào `Sale`. Tạo báo cáo **vùng → kênh → loại sản phẩm** với downstream `counting()`. Dự đoán kiểu:

```java
Map<String, Map<String, Map<String, Long>>>
```

Viết unit test cho ít nhất hai loại sản phẩm trong một kênh, và một loại không xuất hiện trong nguồn. Có phải các khóa không xuất hiện tự được tạo?

### Bài B — Giữ cả số đơn và tiền đã thanh toán

Định nghĩa `record BasicCell(long count, long totalVnd)`. Thay `summarizingLong` bằng `Collectors.teeing(counting(), summingLong(...), BasicCell::new)` sau `filtering` để tạo hai giá trị. Đối chiếu với `Cell` đầy đủ trong ví dụ chính.

### Bài C — Lấy các ID đã thanh toán theo từng nhóm

Dùng `mapping(Sale::id, toList())` làm downstream sau `filtering(Sale::paid, ...)`. Yêu cầu mỗi list trong nhóm được sắp tăng theo ID. Nếu có hai đơn trùng ID, chọn **giữ cả hai**, **loại trùng** hoặc **báo lỗi**, và chứng minh lựa chọn bằng test.

### Bài D — Top 2 kênh theo doanh thu từng vùng

Từ báo cáo `Map<String,Map<String,Cell>>`, tạo một cấu trúc mới chỉ giữ tối đa hai kênh có `totalVnd` lớn nhất cho từng vùng. Khi hòa tiền, sắp theo tên kênh tăng dần. Nêu rõ thứ tự khóa trong map mới hoặc trả một `List` xếp hạng nếu dễ diễn đạt hơn.

### Bài E — Trung bình có trọng số

Thêm trường `int itemCount`. Nếu yêu cầu “doanh thu trung bình **trên mỗi sản phẩm**”, tại sao `averagingLong(Sale::amountVnd)` không đủ? Hãy tích lũy **tổng tiền** và **tổng số sản phẩm** trong cùng một collector, xử lý mẫu số bằng 0 và tràn số.

### Bài F — Snapshot bất biến

Sau khi xây báo cáo, tạo phiên bản API chỉ trả map không thể sửa đổi ở **cả hai tầng**, không để lộ tham chiếu mutable gốc. Kiểm thử thao tác `put` ở tầng ngoài và tầng trong đều bị từ chối, nhưng thứ tự khóa vẫn đúng.

### Bài G — Dữ liệu sai và ghi nhận lỗi

Thiết kế một cơ chế validate ở ranh giới nhập dữ liệu để tách các bản ghi `Sale` hợp lệ khỏi các dòng sai mã vùng hoặc sai số tiền. Quy định **báo lỗi để dừng** hay **trả báo cáo kèm danh sách bản ghi lỗi**; không được âm thầm bỏ dữ liệu rồi coi báo cáo hoàn chỉnh.

## 17. Tiêu chí tự đánh giá và bảng quyết định

Đánh giá lời giải bằng một checklist nhỏ:

- [ ] Có đủ **8 bản ghi** trong phép đếm tất cả đơn.
- [ ] Có đúng **6 bản ghi đã thanh toán**, tổng tiền **310.000 VND**.
- [ ] Ngoài cùng nhóm theo `region`, bên trong theo `channel`.
- [ ] Thứ tự vùng là `HN, HCM, DN` và thứ tự kênh là `STORE, WEB`.
- [ ] Bản lọc trước grouping **không có ô DN/WEB**.
- [ ] Bản dùng downstream `filtering` **có ô DN/WEB** với count và sum bằng 0.
- [ ] Ô `DN/WEB` không hiển thị min/max/average giả.
- [ ] Các ô khác có count, sum, min, max, average như bảng dữ liệu chuẩn.
- [ ] Có kiểm thử nguồn rỗng, đơn hợp lệ số tiền `0` và dữ liệu không hợp lệ.
- [ ] Không dựa vào trạng thái mutable dùng chung, thứ tự map không cam kết hoặc số học có thể tràn.

| Câu hỏi | Collector/hướng xử lý |
| --- | --- |
| Có hai khóa nhóm? | `groupingBy(k1, ..., groupingBy(k2, ..., downstream))` |
| Cần đếm mọi bản ghi trong từng ô? | `counting()` |
| Chỉ cần tổng một trường `long`? | `summingLong(mapper)` |
| Cần count, sum, min, max, average? | `summarizingLong(mapper)` |
| Cần lọc nhưng vẫn giữ nhóm có dữ liệu nguồn? | `filtering(predicate, downstream)` |
| Cần chuyển đối tượng thành ID trong một ô? | `mapping(idMapper, toList())` |
| Cần biến thống kê mutable thành DTO rõ ràng? | `collectingAndThen(downstream, finisher)` |
| Cần hai phép tổng hợp khác nhau trên cùng phần tử? | `teeing(leftCollector, rightCollector, merger)` |
| Cần giữ thứ tự vùng gặp đầu? | `LinkedHashMap::new` với ordered sequential stream |
| Cần sắp tên kênh? | `TreeMap::new` |
| Cần biểu diễn nhóm không có mẫu? | `count == 0` và `OptionalLong`/`OptionalDouble.empty()` |
| Cần báo cáo giá trị tiền rất lớn chính xác? | BigInteger/BigDecimal hoặc bộ tích lũy kiểm soát tràn |

## 18. Tổng kết

Để **lập báo cáo nhóm bằng Collector nhiều tầng**, hãy đi từ **kiểu kết quả mong muốn** thay vì ghép lambda một cách ngẫu nhiên. Lớp `groupingBy` ngoài chọn khóa vùng; lớp `groupingBy` trong chọn kênh; downstream collector quyết định **giữ chi tiết, đếm, tính tổng hay thống kê**. Sự khác nhau giữa `Stream.filter` và `Collectors.filtering` quyết định một nhóm rỗng có còn được thể hiện hay không. `collectingAndThen` giúp chuyển trạng thái thống kê mutable thành một kết quả có ý nghĩa với nguồn rỗng.

Trong thực tế, một báo cáo tốt không chỉ cho số liệu đúng ở dữ liệu mẫu: nó phải có **quy tắc thứ tự, chính sách dữ liệu thiếu, cách biểu diễn nhóm không có mẫu, kiểm thử và giới hạn hiệu năng/số học** rõ ràng. Đó là nền tảng để mở rộng sang collector tùy chỉnh, phân nhóm đồng thời và pipeline xử lý dữ liệu lớn trong Java Stream API.
