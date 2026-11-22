# Thực hành nhóm dữ liệu và tạo báo cáo với `Collector` trong Java Stream

Trong ứng dụng thực tế, dữ liệu hiếm khi chỉ cần một tổng số. Ta thường phải **lọc theo điều kiện nghiệp vụ, nhóm theo nhiều cấp, tính các chỉ số, tạo báo cáo có thứ tự xác định**, rồi kiểm thử các kết quả ở từng cấp. Java Stream cung cấp các `Collector` dựng sẵn như `groupingBy`, `counting`, `summingLong`, `filtering`, `mapping` và `teeing` để tổ chức công việc đó mà không cần sửa một `Map` dùng chung trong `forEach`.

Bài thực hành này dùng **Java 17+**, thiết kế một báo cáo doanh thu đơn hàng theo **khu vực** và **nhóm hàng**, từ yêu cầu → dữ liệu mẫu → thiết kế `record` → pipeline → kết quả → kiểm thử → bài mở rộng. Nội dung đặc biệt chú ý phân biệt nhóm **không tồn tại** với nhóm **có số đếm bằng 0**, giữ thứ tự xuất báo cáo, và không trộn I/O vào các lambda tính toán.

## 1. Bối cảnh và yêu cầu nghiệp vụ

Một hệ thống bán hàng có các bản ghi:

- Mã đơn hàng `id`.
- Khu vực `region` (ví dụ `North`, `South`, `Central`).
- Nhóm hàng `category` (`Books`, `Toys`).
- Giá trị đơn tính bằng **cent** `revenueCents`, kiểu `long`.
- Trạng thái `paid`: `true` đã thanh toán; `false` chưa thanh toán.

Quy định của báo cáo:

1. **Chỉ cộng doanh thu của đơn đã thanh toán.** Đơn chưa thanh toán không được đưa vào tổng doanh thu.
2. **Báo cáo chi tiết** theo cấu trúc `Map<region, Map<category, Stats>>`. Ở lá, `Stats` gồm `count` và `revenueCents`.
3. Có **báo cáo tổng theo khu vực**, **tổng theo nhóm hàng**, và **tổng toàn bộ** để đối soát.
4. **Sắp xếp khóa báo cáo** theo thứ tự tự nhiên bằng `TreeMap`; không dựa vào thứ tự tình cờ của `HashMap`.
5. Có một chỉ số riêng là **số đơn đã thanh toán trên mỗi khu vực xuất hiện trong dữ liệu gốc**, kể cả khu vực chỉ có đơn chưa thanh toán. Đây là cơ hội dùng downstream `Collectors.filtering()`.
6. Kiểm tra dữ liệu đơn hàng và đối chiếu tổng giữa các cấp, không dựa vào tác dụng phụ trong `peek` hoặc `forEach`.

Mục tiêu đầu tiên là **đúng ngữ nghĩa và có thể kiểm thử**. Nếu dữ liệu nhiều đến mức cần phân trang/database, chiến lược truy vấn và lưu trữ có thể cần thay đổi; ví dụ này minh họa báo cáo trên danh sách đã có trong bộ nhớ.

## 2. Dữ liệu đầu vào mẫu

Dữ liệu dùng cho toàn bài:

| ID | Region | Category | Revenue (cent) | Paid |
| --- | --- | --- | ---: | --- |
| S01 | North | Books | 1200 | Có |
| S02 | South | Toys | 3500 | Có |
| S03 | North | Books | 800 | Có |
| S04 | North | Toys | 7000 | Không |
| S05 | South | Books | 1500 | Có |
| S06 | North | Toys | 2500 | Có |
| S07 | South | Toys | 500 | Có |
| S08 | Central | Books | 1800 | Có |
| S09 | Central | Toys | 900 | Không |
| S10 | South | Books | 0 | Có |
| S11 | West | Toys | 1200 | Không |

Chỉ có **8 đơn được thanh toán**, gồm: `S01`, `S02`, `S03`, `S05`, `S06`, `S07`, `S08`, `S10`. Doanh thu đã thanh toán:

```text
North:   Books 1200 + 800; Toys 2500             = 4500
South:   Books 1500 + 0; Toys 3500 + 500         = 5500
Central: Books 1800                               = 1800
West:    không có đơn nào đã thanh toán           = 0
Toàn bộ: 4500 + 5500 + 1800                      = 11800
```

`S10` có doanh thu 0 nhưng **vẫn là một đơn đã thanh toán**, nên nó được tính vào `count`. Ngược lại, `S11` ở `West` chưa thanh toán nên không xuất hiện trong báo cáo doanh thu chỉ xét đơn đã thanh toán, nhưng khu vực `West` có thể xuất hiện ở chỉ số đếm có giữ nhóm từ dữ liệu gốc.

## 3. Thiết kế kiểu dữ liệu và Collector cần dùng

Ta dùng hai `record`:

```java
record Sale(
        String id,
        String region,
        String category,
        long revenueCents,
        boolean paid
) {}

record Stats(long count, long revenueCents) {}
```

Đây là các kiểu minh họa, không phải chương trình chạy độc lập. Trong chương trình đầy đủ, `Sale` có bước validate các trường.

Collector cho `Stats` kết hợp hai phép thu thập bằng `teeing` (Java 12+):

```java
static Collector<Sale, ?, Stats> statsCollector() {
    return Collectors.teeing(
            Collectors.counting(),
            Collectors.summingLong(Sale::revenueCents),
            Stats::new
    );
}
```

Diễn giải:

- `counting()` sinh `Long`, đếm mỗi phần tử nguồn.
- `summingLong(Sale::revenueCents)` sinh `Long`, cộng doanh thu các phần tử.
- `Stats::new` nhận hai kết quả `Long`, tự unbox sang `long` rồi tạo một `Stats` có hai trường.
- Kiểu `Collector<Sale, ?, Stats>` có `?` vì **kiểu container tích lũy `A` là chi tiết triển khai** của collector; người sử dụng chỉ cần biết đầu vào là `Sale` và kết quả là `Stats`.

`teeing` giúp tổng hợp nhiều chỉ số trong **một lượt thu thập** với các downstream collector được điều phối cùng nhau. Một lựa chọn khác là custom `Collector.of` tự giữ cặp `(sum,count)`; dùng collector chuẩn giúp bài thực hành ngắn và ít bẫy hơn.

### Cây cấu trúc dữ liệu cần tạo

```text
Map<String, Map<String, Stats>>
              |
              +-- Central
              |      +-- Books -> Stats(1, 1800)
              |
              +-- North
              |      +-- Books -> Stats(2, 2000)
              |      +-- Toys  -> Stats(1, 2500)
              |
              +-- South
                     +-- Books -> Stats(2, 1500)
                     +-- Toys  -> Stats(2, 4000)
```

Vì báo cáo doanh thu chỉ xét đơn `paid`, key `West` **không được tạo** ở cây này. `TreeMap` bảo đảm thứ tự key theo thứ tự tự nhiên; cách trình bày ở trên cũng dựa theo thứ tự đó.

## 4. Lời giải Java 17+ đầy đủ

Lưu mã sau vào tệp **`SalesReportDemo.java`**:

```java
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class SalesReportDemo {
    record Sale(
            String id,
            String region,
            String category,
            long revenueCents,
            boolean paid
    ) {
        Sale {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(region, "region");
            Objects.requireNonNull(category, "category");
            if (id.isBlank() || region.isBlank() || category.isBlank()
                    || revenueCents < 0) {
                throw new IllegalArgumentException("Sale không hợp lệ");
            }
        }
    }

    record Stats(long count, long revenueCents) {}

    static Collector<Sale, ?, Stats> statsCollector() {
        return Collectors.teeing(
                Collectors.counting(),
                Collectors.summingLong(Sale::revenueCents),
                Stats::new
        );
    }

    // Báo cáo chi tiết: khu vực -> nhóm hàng -> thống kê.
    static Map<String, Map<String, Stats>> byRegionAndCategory(
            List<Sale> sales
    ) {
        return sales.stream()
                .filter(Sale::paid)
                .collect(Collectors.groupingBy(
                        Sale::region,
                        TreeMap::new,
                        Collectors.groupingBy(
                                Sale::category,
                                TreeMap::new,
                                statsCollector()
                        )
                ));
    }

    // Tổng theo từng khu vực, chỉ tính đơn đã thanh toán.
    static Map<String, Stats> byRegion(List<Sale> sales) {
        return sales.stream()
                .filter(Sale::paid)
                .collect(Collectors.groupingBy(
                        Sale::region,
                        TreeMap::new,
                        statsCollector()
                ));
    }

    // Tổng theo từng nhóm hàng, chỉ tính đơn đã thanh toán.
    static Map<String, Stats> byCategory(List<Sale> sales) {
        return sales.stream()
                .filter(Sale::paid)
                .collect(Collectors.groupingBy(
                        Sale::category,
                        TreeMap::new,
                        statsCollector()
                ));
    }

    // Tổng toàn bộ đơn đã thanh toán.
    static Stats overall(List<Sale> sales) {
        return sales.stream()
                .filter(Sale::paid)
                .collect(statsCollector());
    }

    // Vẫn giữ key của những khu vực chỉ có đơn chưa thanh toán.
    static Map<String, Long> paidCountIncludingEmptyGroups(
            List<Sale> sales
    ) {
        return sales.stream().collect(Collectors.groupingBy(
                Sale::region,
                TreeMap::new,
                Collectors.filtering(
                        Sale::paid,
                        Collectors.counting()
                )
        ));
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("S01", "North", "Books", 1200, true),
                new Sale("S02", "South", "Toys", 3500, true),
                new Sale("S03", "North", "Books", 800, true),
                new Sale("S04", "North", "Toys", 7000, false),
                new Sale("S05", "South", "Books", 1500, true),
                new Sale("S06", "North", "Toys", 2500, true),
                new Sale("S07", "South", "Toys", 500, true),
                new Sale("S08", "Central", "Books", 1800, true),
                new Sale("S09", "Central", "Toys", 900, false),
                new Sale("S10", "South", "Books", 0, true),
                new Sale("S11", "West", "Toys", 1200, false)
        );

        Map<String, Map<String, Stats>> detail =
                byRegionAndCategory(sales);
        Map<String, Stats> regions = byRegion(sales);
        Map<String, Stats> categories = byCategory(sales);
        Stats total = overall(sales);
        Map<String, Long> paidCounts =
                paidCountIncludingEmptyGroups(sales);

        // Kiểm tra chéo kết quả và cả trường hợp rỗng.
        check(total.equals(new Stats(8, 11800)),
                "Sai tổng toàn bộ");
        check(detail.get("North").get("Books")
                        .equals(new Stats(2, 2000)),
                "Sai nhóm North/Books");
        check(!detail.containsKey("West"),
                "West không được có trong báo cáo doanh thu");
        check(paidCounts.get("West") == 0L,
                "West phải có số đếm paid bằng 0");
        check(overall(List.of()).equals(new Stats(0, 0)),
                "Nguồn rỗng phải cho tổng 0");
        check(byRegionAndCategory(List.of()).isEmpty(),
                "Nguồn rỗng không có group");
        check(regions.values().stream()
                        .mapToLong(Stats::revenueCents).sum()
                        == total.revenueCents(),
                "Tổng theo vùng không khớp");

        System.out.println("DETAIL:");
        detail.forEach((region, byCategory) ->
                byCategory.forEach((category, stats) ->
                        System.out.println(region + "/" + category
                                + " = " + stats.count()
                                + " orders, " + stats.revenueCents()
                                + " cents")
                )
        );

        System.out.println("BY REGION:");
        regions.forEach((region, stats) ->
                System.out.println(region + " = " + stats.count()
                        + " orders, " + stats.revenueCents() + " cents")
        );

        System.out.println("BY CATEGORY:");
        categories.forEach((category, stats) ->
                System.out.println(category + " = " + stats.count()
                        + " orders, " + stats.revenueCents() + " cents")
        );

        System.out.println("TOTAL = " + total.count()
                + " orders, " + total.revenueCents() + " cents");
        System.out.println("PAID COUNTS = " + paidCounts);
        System.out.println("CHECKS = PASS");
    }
}
```

Biên dịch/chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 SalesReportDemo.java
java SalesReportDemo
```

Stdout **xác định** (do `TreeMap` sắp key và chương trình không in từ các callback chạy song song):

```text
DETAIL:
Central/Books = 1 orders, 1800 cents
North/Books = 2 orders, 2000 cents
North/Toys = 1 orders, 2500 cents
South/Books = 2 orders, 1500 cents
South/Toys = 2 orders, 4000 cents
BY REGION:
Central = 1 orders, 1800 cents
North = 3 orders, 4500 cents
South = 4 orders, 5500 cents
BY CATEGORY:
Books = 5 orders, 5300 cents
Toys = 3 orders, 6500 cents
TOTAL = 8 orders, 11800 cents
PAID COUNTS = {Central=1, North=3, South=4, West=0}
CHECKS = PASS
```

Báo cáo chính sử dụng bản ghi đã thanh toán; `S04`, `S09`, `S11` không được cộng doanh thu. Đơn `S10` có giá trị 0 nhưng vẫn tăng `count` của nhóm `South/Books`. Vì `Stats` là `record`, `equals()` theo giá trị giúp kiểm tra `Stats(8, 11800)` trực tiếp.

## 5. Giải thích pipeline quan trọng nhất

Phần quan trọng nhất là:

```java
return sales.stream()
        .filter(Sale::paid)
        .collect(Collectors.groupingBy(
                Sale::region,
                TreeMap::new,
                Collectors.groupingBy(
                        Sale::category,
                        TreeMap::new,
                        statsCollector()
                )
        ));
```

Đây là snippet trong phương thức `byRegionAndCategory` của class trên.

Đi từ trong ra ngoài:

1. `filter(Sale::paid)`: chỉ để phần tử đã thanh toán đi vào collector.
2. `groupingBy(Sale::region, TreeMap::new, ...)`: tách các phần tử theo region. `TreeMap::new` kiểm soát thứ tự key ở cấp ngoài.
3. Downstream `groupingBy(Sale::category, TreeMap::new, statsCollector())`: ở **mỗi khu vực**, phân nhóm hàng và dùng một `TreeMap` cho key cấp trong.
4. `statsCollector()`: với những đơn thuộc **cùng region và category**, đếm đơn và tính tổng cent.
5. Kết quả có dạng `Map<String, Map<String, Stats>>`; không phải `List` hay một map phẳng.

Ví dụ `North/Books` nhận `S01` và `S03`, nên số đơn là 2 và tổng doanh thu là `1200 + 800 = 2000`. `North/Toys` chỉ nhận `S06` vì `S04` chưa thanh toán, nên có 1 đơn và 2500 cent.

### Vì sao không dùng `HashMap` mặc định để in stdout?

`Collectors.groupingBy(classifier, downstream)` **không cam kết** cụ thể loại `Map` hoặc thứ tự iteration của các key. Nếu in trực tiếp map mặc định rồi ghi một stdout theo thứ tự cố định, tài liệu có thể gây hiểu lầm.

Trong ví dụ, dùng overload **ba đối số**:

```java
Collectors.groupingBy(classifier, TreeMap::new, downstream)
```

Nhờ đó, `region` và `category` được duyệt theo thứ tự tự nhiên của `String`. Việc sắp key không có nghĩa chương trình đã sắp các `Sale` hoặc loại bỏ các bản ghi trùng nhau.

## 6. `filter()` trước nhóm khác `Collectors.filtering()` bên trong nhóm

Đây là điểm thường gây nhầm lẫn nhất.

**Lọc trước khi grouping:**

```java
Map<String, Long> result = sales.stream()
        .filter(Sale::paid)
        .collect(Collectors.groupingBy(
                Sale::region,
                Collectors.counting()
        ));
```

Với nguồn mẫu, key `West` **không tồn tại** vì tất cả Sale của `West` đã bị loại ở bước `filter`.

**Nhóm trước và lọc trong downstream:**

```java
Map<String, Long> result = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::region,
                Collectors.filtering(
                        Sale::paid,
                        Collectors.counting()
                )
        ));
```

Nhóm `West` được tạo do có dữ liệu đầu vào thuộc `West`. Sau đó downstream chỉ đếm phần tử paid, nên `West` có `0`. Hai snippet nằm trong phương thức có `sales` và import `java.util.Map`, `java.util.stream.Collectors`; không phải chương trình độc lập.

| Cách viết | Khu vực chỉ có đơn chưa thanh toán | Khi dùng |
| --- | --- | --- |
| `stream.filter(paid).collect(groupingBy(region, counting()))` | **Không có key** | Báo cáo chỉ gồm những khu vực có đơn đủ điều kiện |
| `stream.collect(groupingBy(region, filtering(paid, counting())))` | **Có key với count 0** | Báo cáo mọi khu vực từng xuất hiện, ghi rõ nhóm không có đơn paid |

Đừng nhầm trường hợp `0` với `null`: `map.get("West")` bằng `0L` khi key có mặt, nhưng bằng `null` khi key hoàn toàn không tồn tại.

## 7. Giữ kiểu dữ liệu tiền và kiểm soát độ chính xác

Ví dụ dùng `long revenueCents`, không dùng `double` để lưu tiền. Cộng những số cent nguyên giúp tránh một số lỗi biểu diễn thập phân nhị phân, nhưng **`long` vẫn có giới hạn**.

`Collectors.summingLong(Sale::revenueCents)` dùng phép cộng kiểu `long`; **không mặc định phát hiện overflow**. Với dữ liệu thực có thể vượt giới hạn, cần phương án như:

- Chặn giá trị đầu vào và giới hạn kích thước/tổng theo hợp đồng nghiệp vụ.
- Dùng phép cộng có kiểm tra `Math.addExact` trong collector tự thiết kế phù hợp.
- Dùng `BigDecimal` khi cần biểu diễn nhiều loại tiền tệ, số thập phân và chính sách làm tròn theo quy tắc đã xác định.

Không được ngầm hiểu `revenueCents=0` là “chưa thanh toán”; `paid` là trường nghiệp vụ riêng. Ví dụ `S10` minh họa rằng một đơn paid có thể có doanh thu 0.

Nếu cần **giá trị trung bình**, hãy chỉ rõ “trung bình trên đơn paid”, đặc biệt khi có đơn giá trị 0. `Collectors.averagingLong(Sale::revenueCents)` cho `Double` và có giới hạn độ chính xác số thực; không nên tùy tiện dùng để quyết định số tiền phải thanh toán chính xác đến cent.

## 8. Thêm loại báo cáo bằng downstream Collector

### 8.1. Chỉ liệt kê ID đơn paid trong từng vùng

```java
Map<String, List<String>> paidIdsByRegion = sales.stream()
        .filter(Sale::paid)
        .collect(Collectors.groupingBy(
                Sale::region,
                TreeMap::new,
                Collectors.mapping(
                        Sale::id,
                        Collectors.toList()
                )
        ));
```

Đây là snippet trong class `SalesReportDemo` hoặc phương thức có `sales`; cần import `Map`, `List`, `TreeMap` và `Collectors`.

`mapping(Sale::id, toList())` giữ một thuộc tính, không cần giữ toàn bộ `Sale` trong danh sách kết quả. Nếu chỉ cần số lượng, không nên thu các ID rồi mới lấy `.size()`; dùng `counting()` phù hợp hơn.

### 8.2. Phân vùng paid/unpaid

```java
Map<Boolean, Long> paidVsUnpaid = sales.stream()
        .collect(Collectors.partitioningBy(
                Sale::paid,
                Collectors.counting()
        ));
// false = 3, true = 8
```

`partitioningBy` chia nhóm theo hai key Boolean `true` và `false`; nó khác `groupingBy` ở chỗ luôn biểu diễn hai nhánh, kể cả khi một nhánh rỗng.

### 8.3. Dùng `summarizingLong()` thay `teeing()`

```java
Map<String, java.util.LongSummaryStatistics> summary =
        sales.stream()
                .filter(Sale::paid)
                .collect(Collectors.groupingBy(
                        Sale::region,
                        Collectors.summarizingLong(
                                Sale::revenueCents
                        )
                ));
```

Mỗi `LongSummaryStatistics` cung cấp `getCount()`, `getSum()`, `getMin()`, `getMax()`, `getAverage()`. Nếu báo cáo cần thêm min/max/average, nó có thể thuận tiện hơn `Stats` chỉ gồm hai trường.

Chú ý `LongSummaryStatistics.getSum()` cũng có giới hạn kiểu `long`; bản thân thống kê không thay cho chính sách kiểm soát overflow và độ chính xác số học.

## 9. Biến đổi danh sách kết quả thành báo cáo văn bản

Các phương thức `byRegionAndCategory`, `byRegion`, `byCategory` và `overall` đều chỉ tính dữ liệu. Bước in nằm ở phần cuối `main`:

```java
detail.forEach((region, groups) ->
        groups.forEach((category, stats) ->
                System.out.println(
                        region + "/" + category + " = "
                        + stats.count() + " orders, "
                        + stats.revenueCents() + " cents"
                )
        )
);
```

Nhờ đầu vào là các `TreeMap`, lệnh duyệt in có thứ tự xác định. Nhưng nếu muốn **trả báo cáo như một `String`** thay vì in console, có thể dùng một hàm `render`:

```java
static String render(Map<String, Map<String, Stats>> detail) {
    StringBuilder out = new StringBuilder();

    detail.forEach((region, categories) ->
            categories.forEach((category, stats) ->
                    out.append(region).append("/")
                            .append(category).append(": ")
                            .append(stats.count()).append(", ")
                            .append(stats.revenueCents())
                            .append("\n")
            )
    );

    return out.toString();
}
```

Đây là **phương thức minh họa** bổ sung trong `SalesReportDemo`, không tự chạy độc lập. `StringBuilder` là biến **cục bộ của hàm render**, không chia sẻ với một parallel stream; hàm chỉ tạo chuỗi mới, không tự ghi file hoặc console. Vì thế các kiểm thử có thể so sánh trực tiếp chuỗi render. Với quy tắc định dạng số và tiền tệ phức tạp hơn, cần cung cấp locale/currency/rounding rõ ràng.

Để xuất file hoặc HTTP response, nên tạo `String` trước rồi thực hiện I/O ở ranh giới ứng dụng. Đừng đặt thao tác `Files.writeString` vào `map`, `peek` hoặc `groupingBy` classifier.

## 10. Kiểm thử và đối soát báo cáo

Không chỉ kiểm tra “chạy không lỗi”, bài thực hành cần kiểm tra các điều kiện nghiệp vụ:

| Điều kiện | Giá trị mong đợi |
| --- | --- |
| Số đơn paid toàn bộ | 8 |
| Doanh thu paid toàn bộ | 11800 |
| `North/Books` | `Stats(2,2000)` |
| `South/Toys` | `Stats(2,4000)` |
| Tổng doanh thu North | 4500 |
| Tổng doanh thu South | 5500 |
| Tổng doanh thu Central | 1800 |
| Group doanh thu West | Không tồn tại |
| Số đơn paid West trong báo cáo gồm mọi khu vực | 0 |
| Tổng của mọi region | Bằng tổng toàn bộ |
| Tổng của mọi category | Bằng tổng toàn bộ |
| Nguồn rỗng | Tổng `Stats(0,0)`, các map nhóm rỗng |

Chương trình đầy đủ đã đưa một số kiểm tra vào `main`. Bạn có thể bổ sung kiểm tra độc lập cho category:

```java
long sumByCategory = categories.values().stream()
        .mapToLong(Stats::revenueCents)
        .sum();

check(sumByCategory == total.revenueCents(),
        "Tổng theo category không khớp");
```

Đây là snippet trong `main`, sử dụng `categories`, `total` và `check` đã khai báo.

### Kiểm thử trường hợp chỉ có đơn chưa thanh toán

```java
List<Sale> unpaidOnly = List.of(
        new Sale("U01", "West", "Books", 900, false)
);

check(byRegionAndCategory(unpaidOnly).isEmpty(),
        "Không có nhóm paid");
check(overall(unpaidOnly).equals(new Stats(0, 0)),
        "Tổng paid phải bằng 0");
check(paidCountIncludingEmptyGroups(unpaidOnly)
                .get("West") == 0L,
        "West phải được giữ với count 0");
```

Đây là snippet chạy trong `main` hoặc một phương thức test của class `SalesReportDemo`, không phải file riêng. Nó kiểm tra sự khác biệt giữa **nhóm bị loại trước khi collect** và **nhóm được giữ nhưng downstream đếm bằng 0**.

### Cần kiểm tra những gì nếu chuyển sang parallel stream?

Nếu muốn thay `sales.stream()` bằng `sales.parallelStream()`, hãy kiểm tra các tổng/nhóm vẫn có giá trị đúng. Những collector chuẩn trong bài được thiết kế để kết hợp các nhánh theo hợp đồng, và `TreeMap` giúp kết quả được trình bày theo thứ tự key rõ ràng sau khi thu thập.

Tuy nhiên:

- Không giả định số lượng thread hoặc thứ tự thời gian thực thi `classifier` và các hàm `downstream`.
- Không thêm side effect vào `map`/`filter`/classifier hoặc tự sửa một `HashMap` dùng chung.
- Không suy luận `Collectors.groupingByConcurrent` luôn giữ encounter order; nhu cầu đồng thời và nhu cầu thứ tự phải được xem xét riêng.
- Với dữ liệu nhỏ, overhead của parallelism có thể lớn hơn lợi ích. Chỉ benchmark khi bài toán thực tế đủ phức tạp.

## 11. Các lỗi thường gặp trong bài nhóm và báo cáo

| Lỗi | Hậu quả | Cách khắc phục |
| --- | --- | --- |
| Nhóm tất cả đơn rồi cộng doanh thu mà quên paid | Doanh thu gồm đơn chưa thanh toán | `filter(Sale::paid)` trước grouping hoặc downstream filtering theo đúng yêu cầu |
| Lấy `count` bằng số bản ghi có revenue dương | Bỏ mất đơn paid giá trị 0 | Đếm theo trạng thái paid, không theo `revenueCents > 0` |
| Dùng `groupingBy(region)` khi cần hai cấp | Lá chỉ là `List<Sale>` | Lồng `groupingBy(category, downstream)` |
| Nhầm `counting()` trả `Integer` | Sai kiểu generic | Dùng `Long` |
| Nhầm `teeing` là collector Java 8 | Không biên dịch ở JDK cũ | Dùng Java 12+ hoặc custom collector tương đương |
| Dùng `HashMap` rồi viết stdout theo thứ tự cố định | Thứ tự iteration không được bảo đảm | `TreeMap::new` tại cấp cần sắp xếp |
| Truy cập `map.get(a).get(b)` khi key ngoài thiếu | `NullPointerException` | Kiểm tra key hoặc `getOrDefault` |
| Trông chờ mọi category đều có trong mỗi region | Nhóm không có dữ liệu không được tự tạo | Biểu diễn zero-group theo chính sách báo cáo |
| Dùng `Collectors.toMap` mà key bị trùng | Có thể ném `IllegalStateException` | Dùng `groupingBy` hoặc merge function rõ nghĩa |
| Classifier trả `null` | `groupingBy` thường ném `NullPointerException` | Validate hoặc chuẩn hóa key |
| Tính doanh thu bằng `double` rồi mặc định chính xác đến cent | Nguy cơ sai số tiền | Dùng cent nguyên hoặc `BigDecimal` có chính sách |
| Quên giới hạn của `long` | Có thể overflow trong tổng | Validate/giám sát hoặc phép cộng kiểm tra |
| Cập nhật `Map` dùng chung trong `parallelStream().forEach` | Race và tổng sai | Dùng `collect(groupingBy(...))` |
| Dùng `peek` để đếm/log nghiệp vụ bắt buộc | Callback trung gian không có hợp đồng số lần thực thi như phép tổng hợp | Dùng terminal operation và ranh giới I/O rõ ràng |

## 12. Bài tập mở rộng

Sau khi chạy đúng chương trình, hãy tự sửa hoặc bổ sung từng yêu cầu sau, **viết expected result trước khi xem chương trình chạy**.

### Bài A — báo cáo đơn chưa thanh toán

Thêm `byRegionUnpaid` trả `Map<String, Stats>` nhưng chỉ gồm những đơn `paid == false`. Với dữ liệu mẫu:

```text
Central = Stats[count=1, revenueCents=900]
North   = Stats[count=1, revenueCents=7000]
West    = Stats[count=1, revenueCents=1200]
```

Lưu ý đây là **tổng giá trị ghi nhận trên đơn chưa thanh toán**, không phải doanh thu đã thu. Không nhầm nhãn của nó với báo cáo revenue paid.

**Gợi ý:** đổi predicate `filter(sale -> !sale.paid())` rồi dùng `groupingBy(Sale::region, TreeMap::new, statsCollector())`.

### Bài B — doanh thu bình quân trên mỗi đơn paid

Thêm `averageRevenueCents` theo khu vực bằng `Collectors.averagingLong(Sale::revenueCents)` hoặc sử dụng `Stats` để chia `revenueCents / count`. Với dữ liệu mẫu:

```text
Central: 1800.0
North:   1500.0
South:   1375.0
```

Khi làm tròn số cent trong nghiệp vụ tài chính, cần quy tắc rounding xác định; `Double` chỉ thích hợp để minh họa thống kê. Khu vực `West` không có đơn paid nên **không nên tự gán average bằng 0** nếu không có chính sách báo cáo như vậy.

### Bài C — chỉ báo top category

Tìm category có tổng doanh thu paid lớn nhất. Với dữ liệu mẫu, `Toys = 6500` cent, `Books = 5300` cent, nên `Toys` đứng đầu.

**Gợi ý:** dùng `byCategory(sales).entrySet().stream().max(Comparator.comparingLong(e -> e.getValue().revenueCents()))`. Hàm `max` trả `Optional` vì nguồn có thể rỗng. Nếu có nhiều category cùng tổng, cần xác định quy tắc xử lý hòa trước khi viết test.

### Bài D — xây dựng báo cáo CSV

Tạo một hàm `renderCsv(detail)` thuần, trả chuỗi:

```text
region,category,count,revenueCents
Central,Books,1,1800
North,Books,2,2000
North,Toys,1,2500
South,Books,2,1500
South,Toys,2,4000
```

Chỉ sau khi có chuỗi mới dùng `Files.writeString` ở lớp ngoài. Nếu các giá trị `region` hoặc `category` có thể chứa dấu phẩy, dấu nháy kép hoặc xuống dòng, cần CSV escaping theo chuẩn; ví dụ cơ bản ở đây cố ý dùng các giá trị đơn giản.

### Bài E — kiểm thử tính tương đương của báo cáo

Viết hàm test tính cùng báo cáo với `stream()` và `parallelStream()`, rồi so sánh hai map bằng `.equals()`. Cũng hãy kiểm tra nguồn rỗng, chỉ có đơn chưa thanh toán, đơn revenue 0, và trường hợp đầu vào sai. **Đừng so sánh thứ tự callback** khi chạy parallel: thứ cần kiểm tra là kết quả cuối theo hợp đồng collector.

## 13. Câu hỏi tự đánh giá

**1.** Vì sao `groupingBy(region, groupingBy(category, teeing(...)))` trả `Map` lồng nhau?

Vì `groupingBy` ngoài nhận một downstream collector có kết quả là `Map<category, Stats>`; do đó value của `Map<region,...>` chính là một map cấp trong.

**2.** Vì sao `S10` có `revenueCents=0` vẫn làm tăng `count`?

Vì quy tắc chỉ kiểm tra trạng thái `paid`, không kiểm tra doanh thu dương. `counting()` đếm phần tử đã đi tới downstream.

**3.** Vì sao `West` không xuất hiện ở `byRegionAndCategory` nhưng có trong `paidCountIncludingEmptyGroups`?

Bởi cách đầu lọc toàn bộ đơn chưa thanh toán **trước** grouping; cách thứ hai tạo group từ dữ liệu gốc rồi `filtering` **bên trong downstream**, nên `West` còn key với count 0.

**4.** Tại sao nên chọn `TreeMap::new` ở cả hai cấp nếu muốn in báo cáo theo thứ tự key?

Để có thứ tự duyệt `region` và `category` xác định. `groupingBy` mặc định không hứa thứ tự iteration của map.

**5.** `Collectors.teeing` giải quyết bài toán gì?

Nó đưa cùng các phần tử tới hai downstream collectors, rồi kết hợp hai kết quả thành một kiểu mong muốn, ở đây là `Stats(count, revenueCents)`.

**6.** Nếu chỉ cần số bản ghi trong một nhóm, có cần thu cả list rồi lấy `.size()` không?

Không. Dùng `counting()` để tránh tạo một danh sách chỉ nhằm đếm.

**7.** Có nên dùng `parallelStream().forEach(sharedMap::put)` để thay grouping không?

Không. Việc ghi đồng thời vào map ngoài có thể race; hơn nữa một key có thể có nhiều bản ghi và `put` sẽ ghi đè nếu không có phép gộp. Dùng `collect(groupingBy(...))`.

## Ghi nhớ

- **Báo cáo nhiều chiều**: `groupingBy(key1, mapFactory, groupingBy(key2, mapFactory, downstream))`.
- **Nhiều chỉ số trên cùng nhóm**: `teeing(counting(), summingLong(...), Stats::new)` hoặc collector thống kê tương ứng.
- **Đúng điều kiện nghiệp vụ**: đặt `filter` trước grouping nếu muốn bỏ hẳn các nhóm không đủ điều kiện; dùng downstream `filtering` nếu cần giữ key nhóm đã xuất hiện.
- **Thứ tự hiển thị**: chỉ định `TreeMap` hoặc chiến lược sắp xếp rõ ràng; không dựa vào `HashMap`.
- **Kiểm thử đối soát**: tổng theo region, category và toàn bộ phải nhất quán; kiểm tra thêm nhóm vắng mặt, nhóm có count 0 và nguồn rỗng.
- **Giữ pipeline thuần**: tính dữ liệu bằng collector, chỉ thực hiện I/O sau khi có kết quả. Chọn đúng kiểu tiền, xử lý dữ liệu sai và giới hạn overflow.
