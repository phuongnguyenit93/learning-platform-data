# Collectors cho nhóm, phân vùng và tổng hợp nhiều tầng trong Java 27

Khi xử lý dữ liệu bằng Java Stream, yêu cầu thực tế không chỉ là lọc một danh sách. Chương trình thường cần tạo báo cáo như **doanh thu theo khu vực**, **số đơn theo kênh**, **phân loại đạt/không đạt**, hoặc **đếm và cộng tổng cho từng nhóm con**. Lớp `java.util.stream.Collectors` cung cấp các collector có thể **lồng và kết hợp** để mô tả những phép tổng hợp đó bằng API kiểu tĩnh.

Trong Java 27, `groupingBy`, `partitioningBy`, `mapping`, `flatMapping`, `filtering`, `collectingAndThen`, `teeing` và các collector thống kê đều là những API **đã ổn định**. Bài viết chỉ dùng các tính năng hiện hành; không cần `--enable-preview` và không khuyến khích cách xây danh sách bằng side effect trong `forEach`.

## 1. Tư duy nền tảng: từ Stream tới Collector lồng nhau

Ví dụ pipeline:

```java
Map<String, Long> countByRegion = sales.stream()
    .collect(Collectors.groupingBy(
        Sale::region,
        Collectors.counting()
    ));
```

Luồng dữ liệu có dạng:

```text
List<Sale>
   │ .stream()
   ▼
Stream<Sale>
   │ .collect(...)
   ▼
groupingBy(Sale::region, counting())
   │           │              │
   │           └─ chọn khóa    └─ tổng hợp phần tử mỗi nhóm
   ▼
Map<String, Long>
```

Ở đây:

- `sales.stream()` tạo pipeline từ nguồn dữ liệu; bản thân Stream **không lưu trữ** tập kết quả.
- `collect(collector)` là **terminal operation**: tiêu thụ Stream và trả kết quả. Một Stream đã tiêu thụ không được dùng lại; muốn tính báo cáo khác hãy gọi `sales.stream()` mới.
- `groupingBy(classifier)` chọn một **khóa nhóm** cho mỗi phần tử bằng hàm `classifier`.
- `groupingBy(classifier, downstream)` vừa nhóm vừa dùng **downstream collector** để tổng hợp các phần tử thuộc từng nhóm.
- `counting()` trả `Long`; thay nó bằng `toList()`, `summingLong(...)` hay một collector lồng khác sẽ thay đổi kiểu **giá trị** của Map.

Một `Collector<T, A, R>` về mặt khái niệm gồm: `supplier` tạo vùng tích lũy, `accumulator` nhận phần tử, `combiner` gộp hai vùng tích lũy và `finisher` biến vùng tích lũy thành kết quả. Các collector dựng sẵn quản lý những chi tiết này, kể cả khi Stream chạy song song. `A` thường là kiểu nội bộ người gọi không cần biết.

### Các nhóm công cụ chính

| Bài toán | Collector | Dạng kết quả thường gặp |
| --- | --- | --- |
| Gom các phần tử cùng khóa | `groupingBy(key)` | `Map<K, List<T>>` |
| Gom và đếm/tính tổng | `groupingBy(key, downstream)` | `Map<K, D>` |
| Phân đôi theo một điều kiện | `partitioningBy(predicate)` | `Map<Boolean, List<T>>` |
| Phân đôi và thống kê | `partitioningBy(predicate, downstream)` | `Map<Boolean, D>` |
| Đổi kiểu dữ liệu bên trong nhóm | `mapping(mapper, downstream)` | Ví dụ `Map<K, Set<String>>` |
| Trải phẳng nhiều phần tử con trong nhóm | `flatMapping(mapper, downstream)` | Ví dụ `Map<K, Set<String>>` |
| Lọc phần tử **bên trong** nhóm | `filtering(predicate, downstream)` | Ví dụ `Map<K, List<T>>` |
| Thay đổi kết quả cuối của downstream | `collectingAndThen(downstream, finisher)` | Ví dụ `Map<K, List<T>>` với danh sách không cho phép sửa |
| Tổng hợp hai kết quả trong một collector | `teeing(downstream1, downstream2, merger)` | Ví dụ `Map<K, Summary>` |
| Nhiều tầng nhóm | `groupingBy(key1, groupingBy(key2, downstream))` | `Map<K1, Map<K2, D>>` |

Mấu chốt của báo cáo nhiều tầng là **collector ngoài quyết định cách chia nhóm**, còn **collector trong quyết định mỗi nhóm được tổng hợp thành gì**.

## 2. Bộ dữ liệu xuyên suốt và ví dụ Java chạy được

Để tránh nói chung chung, ta dùng giao dịch bán hàng có khu vực (`region`), kênh (`channel`), sản phẩm (`product`), số tiền theo **đơn vị nhỏ nhất** (`amountCents`) và các nhãn (`tags`). Dùng `long` theo đơn vị nhỏ nhất ở ví dụ giúp không phụ thuộc phép tính dấu phẩy động khi cộng số tiền.

Chương trình độc lập dưới đây cho thấy nhóm một tầng, chia hai nhóm, tổng hợp hai tầng, lấy bộ nhãn và dùng `teeing`. Lưu thành `SalesCollectorsDemo.java`:

```java
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.stream.Collectors;

public class SalesCollectorsDemo {

    record Sale(
        String region,
        String channel,
        String product,
        String customer,
        long amountCents,
        List<String> tags
    ) {}

    record Summary(long count, long totalCents) {}

    static List<Sale> sampleSales() {
        return List.of(
            new Sale("North", "WEB",   "Book", "An",   12_000, List.of("new", "member")),
            new Sale("North", "STORE", "Pen",  "Binh",  3_000, List.of("office")),
            new Sale("South", "WEB",   "Book", "Chi",   8_000, List.of("new", "gift")),
            new Sale("South", "WEB",   "Bag",  "Dung", 20_000, List.of("gift")),
            new Sale("North", "WEB",   "Pen",  "An",    5_000, List.of("office", "member")),
            new Sale("South", "STORE", "Pen",  "Chi",   4_000, List.of("office"))
        );
    }

    public static void main(String[] args) {
        List<Sale> sales = sampleSales();

        Map<String, Long> countByRegion = sales.stream().collect(
            Collectors.groupingBy(Sale::region, Collectors.counting())
        );

        Map<Boolean, Long> highValueCount = sales.stream().collect(
            Collectors.partitioningBy(
                sale -> sale.amountCents() >= 10_000,
                Collectors.counting()
            )
        );

        Map<String, Map<String, Summary>> regionChannel = sales.stream().collect(
            Collectors.groupingBy(
                Sale::region,
                TreeMap::new,
                Collectors.groupingBy(
                    Sale::channel,
                    TreeMap::new,
                    Collectors.teeing(
                        Collectors.counting(),
                        Collectors.summingLong(Sale::amountCents),
                        Summary::new
                    )
                )
            )
        );

        Map<String, Set<String>> tagsByRegion = sales.stream().collect(
            Collectors.groupingBy(
                Sale::region,
                TreeMap::new,
                Collectors.flatMapping(
                    sale -> sale.tags().stream(),
                    Collectors.toCollection(TreeSet::new)
                )
            )
        );

        System.out.println("North count = " + countByRegion.get("North"));
        System.out.println("South count = " + countByRegion.get("South"));
        System.out.println("High value = " + highValueCount.get(true));
        System.out.println("Other value = " + highValueCount.get(false));
        System.out.println("Report = " + regionChannel);
        System.out.println("Tags = " + tagsByRegion);
    }
}
```

Đầu ra (các Map cần thứ tự hiển thị đều dùng `TreeMap`):

```text
North count = 3
South count = 3
High value = 2
Other value = 4
Report = {North={STORE=Summary[count=1, totalCents=3000], WEB=Summary[count=2, totalCents=17000]}, South={STORE=Summary[count=1, totalCents=4000], WEB=Summary[count=2, totalCents=28000]}}
Tags = {North=[member, new, office], South=[gift, new, office]}
```

Tổng toàn bộ là `52_000` cents. Các đoạn mã ngắn ở những phần sau sử dụng lại `Sale`, `Summary`, `sampleSales()` và biến `sales` của ví dụ này; hãy đặt các đoạn đó bên trong `main` hoặc một method có dữ liệu tương ứng, **không** dán tất cả vào file như các khai báo top-level độc lập.

## 3. groupingBy: nhóm theo một khóa

### 3.1. Dạng ngắn: nhóm thành List

```java
Map<String, List<Sale>> byRegion = sales.stream()
    .collect(Collectors.groupingBy(Sale::region));

System.out.println(byRegion.get("North").size()); // 3
System.out.println(byRegion.get("South").size()); // 3
```

`groupingBy(Sale::region)` gần tương đương với `groupingBy(Sale::region, toList())`. Với mỗi khóa, Map có một danh sách các giao dịch thuộc khóa đó.

Kiểu dữ liệu:

- Đầu vào: `Stream<Sale>`.
- Khóa: `String` do `Sale::region` trả về.
- Kết quả: `Map<String, List<Sale>>`.

**Không có bảo đảm** về implementation, khả năng sửa đổi, thứ tự duyệt, khả năng serializable hay tính thread-safe của Map/List được tạo bởi overload mặc định. Không viết nghiệp vụ phụ thuộc vào việc nó “thường là `HashMap` hoặc `ArrayList`”.

Nếu Stream rỗng, `groupingBy` cho Map rỗng: nó không tự tạo trước khóa `North`, `South` hay bất kỳ nhóm nào chưa có phần tử.

### 3.2. Nhóm và đếm hoặc cộng theo khóa

Nếu không cần giữ toàn bộ giao dịch, dùng downstream thống kê để giảm bộ nhớ:

```java
Map<String, Long> ordersByRegion = sales.stream().collect(
    Collectors.groupingBy(
        Sale::region,
        Collectors.counting()
    )
);

Map<String, Long> revenueByRegion = sales.stream().collect(
    Collectors.groupingBy(
        Sale::region,
        Collectors.summingLong(Sale::amountCents)
    )
);

System.out.println(revenueByRegion.get("North")); // 20000
System.out.println(revenueByRegion.get("South")); // 32000
```

Với `counting()`, mỗi nhóm tích lũy thành `Long`. Với `summingLong`, mỗi nhóm được cộng theo giá trị của `amountCents`.

Đây là hai lần `collect` trên **hai Stream mới** lấy từ cùng nguồn `sales`. Một đối tượng Stream cụ thể không thể dùng cho hai terminal operations.

### 3.3. Chỉ định loại Map và thứ tự hiển thị

Overload ba tham số:

```java
Map<String, Long> sortedRevenue = sales.stream().collect(
    Collectors.groupingBy(
        Sale::region,
        TreeMap::new,
        Collectors.summingLong(Sale::amountCents)
    )
);
```

`TreeMap::new` chọn một `Map` có khóa được sắp xếp theo natural ordering; nó **không sắp xếp các phần tử bên trong List của nhóm**. Khi cần thứ tự khóa theo lần xuất hiện đầu tiên trong luồng tuần tự có encounter order, có thể dùng `LinkedHashMap::new`.

Dạng tổng quát:

```java
groupingBy(classifier, mapFactory, downstream)
```

Trong đó `mapFactory` cung cấp một Map mới, còn `downstream` tạo giá trị ở mỗi khóa. Chọn `TreeMap` nếu cần so sánh/sắp xếp khóa; `EnumMap` nếu khóa là enum thích hợp; `LinkedHashMap` nếu cần thứ tự xuất hiện đầu tiên của khóa theo encounter order. Không giả định overload mặc định có trật tự khóa xác định.

### 3.4. Xử lý khóa null và chuẩn hóa dữ liệu

Trong triển khai `Collectors.groupingBy` của JDK, kết quả phân loại `null` không được chấp nhận: có thể xảy ra `NullPointerException` dù một số loại Map vốn cho phép key null.

Nếu dữ liệu thiếu khu vực, **chuẩn hóa trước khi nhóm**:

```java
Map<String, Long> safeCounts = sales.stream().collect(
    Collectors.groupingBy(
        sale -> sale.region() == null ? "UNKNOWN" : sale.region(),
        Collectors.counting()
    )
);
```

Với dữ liệu không đáng tin cậy, cũng cần cân nhắc `strip()` và quy tắc chữ hoa/chữ thường. Chẳng hạn `"North"`, `" north "` và `"NORTH"` là ba khóa khác nhau nếu không chuẩn hóa. Đảm bảo phép chuẩn hóa là hàm thuần, không gây tác động phụ lên bản ghi nguồn.

## 4. partitioningBy: chia theo điều kiện Boolean

`partitioningBy(predicate)` chia phần tử thành hai nhóm:

- Khóa `true` cho phần tử thỏa điều kiện.
- Khóa `false` cho phần tử không thỏa.

```java
Map<Boolean, List<Sale>> byAmount = sales.stream().collect(
    Collectors.partitioningBy(sale -> sale.amountCents() >= 10_000)
);

System.out.println(byAmount.get(true).size());  // 2
System.out.println(byAmount.get(false).size()); // 4
```

Điểm khác với `groupingBy(sale -> predicate.test(sale))`: **partitioningBy luôn trả cả hai key `true` và `false`**, ngay cả khi một phía không có phần tử.

```java
Map<Boolean, List<Integer>> emptyPartition =
    java.util.stream.Stream.<Integer>empty()
        .collect(Collectors.partitioningBy(n -> n > 0));

System.out.println(emptyPartition.get(true));  // []
System.out.println(emptyPartition.get(false)); // []
```

Trong khi đó, `groupingBy(n -> n > 0)` trên Stream rỗng trả một Map **không có key nào**.

### 4.1. Phân vùng rồi tổng hợp

```java
Map<Boolean, Long> counts = sales.stream().collect(
    Collectors.partitioningBy(
        sale -> sale.amountCents() >= 10_000,
        Collectors.counting()
    )
);

Map<Boolean, Long> amounts = sales.stream().collect(
    Collectors.partitioningBy(
        sale -> sale.amountCents() >= 10_000,
        Collectors.summingLong(Sale::amountCents)
    )
);

System.out.println(counts.get(true));  // 2
System.out.println(counts.get(false)); // 4
System.out.println(amounts.get(true)); // 32000
System.out.println(amounts.get(false)); // 20000
```

Với phiên bản có downstream, hai khóa vẫn luôn tồn tại. Nếu một phía không có dữ liệu, giá trị của phía đó là kết quả **downstream trên đầu vào rỗng**: ví dụ `counting()` cho `0L`, `toList()` cho danh sách rỗng, `summingLong(...)` cho `0L`.

### 4.2. Chia theo điều kiện nhưng chỉ lấy trường cần thiết

```java
Map<Boolean, List<String>> productsByAmount = sales.stream().collect(
    Collectors.partitioningBy(
        sale -> sale.amountCents() >= 10_000,
        Collectors.mapping(Sale::product, Collectors.toList())
    )
);

// true  → [Book, Bag]
// false → [Pen, Book, Pen, Pen]
```

Dùng `partitioningBy` khi điều kiện thực sự nhị phân. Nếu có ba hay nhiều nhóm như `NEW`, `PAID`, `CANCELLED`, nên dùng `groupingBy` với enum/status thay vì lồng nhiều Boolean Map khó đọc.

## 5. Downstream collectors: mapping, flatMapping và filtering

Các collector này không trực tiếp quyết định **khóa nhóm**; chúng biến đổi dữ liệu **sau khi phần tử đã được phân loại** để đưa vào collector ở tầng sâu hơn.

### 5.1. mapping: đổi Sale thành một trường dữ liệu

```java
Map<String, List<String>> productsByRegion = sales.stream().collect(
    Collectors.groupingBy(
        Sale::region,
        Collectors.mapping(
            Sale::product,
            Collectors.toList()
        )
    )
);
```

Một phiên bản loại trùng tên sản phẩm:

```java
Map<String, Set<String>> productTypes = sales.stream().collect(
    Collectors.groupingBy(
        Sale::region,
        Collectors.mapping(Sale::product, Collectors.toSet())
    )
);
```

Trong các kết quả này, giá trị Map không phải danh sách `Sale` nữa; nó là danh sách/tập hợp `String`. `toSet()` không bảo đảm thứ tự duyệt. Nếu muốn thứ tự từ điển:

```java
Map<String, Set<String>> sortedProductTypes = sales.stream().collect(
    Collectors.groupingBy(
        Sale::region,
        Collectors.mapping(
            Sale::product,
            Collectors.toCollection(TreeSet::new)
        )
    )
);
```

### 5.2. flatMapping: một phần tử tạo nhiều phần tử con

Mỗi `Sale` chứa `List<String> tags`. Nếu dùng `mapping(Sale::tags, toList())`, kết quả có kiểu `Map<String, List<List<String>>>`; mỗi danh sách nhãn vẫn còn lồng bên trong.

Để gom **tất cả nhãn** trong cùng khu vực vào một `Set`:

```java
Map<String, Set<String>> tagsByRegion = sales.stream().collect(
    Collectors.groupingBy(
        Sale::region,
        Collectors.flatMapping(
            sale -> sale.tags().stream(),
            Collectors.toSet()
        )
    )
);
```

`flatMapping` gọi hàm `Sale -> Stream<String>` cho từng phần tử, đưa 0..n phần tử nhãn vào downstream. Sau khi sử dụng, mỗi Stream con được `flatMapping` đóng. Nên trả `Stream.empty()` khi không có phần tử con, hoặc đảm bảo `tags` là danh sách rỗng; `null` được đặc tả coi như Stream rỗng nhưng không nên dựa vào nó để che dữ liệu lỗi.

**Chú ý:** `flatMapping` khác với pipeline `sales.stream().flatMap(...)`. Nếu gọi `flatMap` **trước** `groupingBy`, sau bước trải phẳng có thể đã mất thông tin `region` trừ khi chủ động mang khóa theo. Downstream `flatMapping` giữ nhóm ngoài nguyên vẹn.

### 5.3. filtering: lọc *bên trong* nhóm nhưng vẫn giữ nhóm

Ví dụ chỉ giữ giao dịch `amountCents >= 20_000`. Trong dữ liệu minh họa, kênh `STORE` có giao dịch nhưng **không giao dịch nào đạt ngưỡng**:

```java
Map<String, List<Sale>> keepGroups = sales.stream().collect(
    Collectors.groupingBy(
        Sale::channel,
        Collectors.filtering(
            sale -> sale.amountCents() >= 20_000,
            Collectors.toList()
        )
    )
);

System.out.println(keepGroups.containsKey("STORE")); // true
System.out.println(keepGroups.get("STORE").size());    // 0
System.out.println(keepGroups.get("WEB").size());      // 1
```

Trong khi đó:

```java
Map<String, List<Sale>> dropGroups = sales.stream()
    .filter(sale -> sale.amountCents() >= 20_000)
    .collect(Collectors.groupingBy(Sale::channel));

System.out.println(dropGroups.containsKey("STORE")); // false
```

Sự khác biệt rất quan trọng khi làm báo cáo: **`stream.filter(...)` trước khi nhóm làm biến mất các nhóm không còn phần tử**; còn **`Collectors.filtering(...)` ở downstream tạo giá trị rỗng cho các nhóm đã có phần tử đầu vào nhưng không vượt qua bộ lọc**.

Tất nhiên, nếu một khóa chưa từng xuất hiện trong dữ liệu đầu vào, `groupingBy` vẫn **không tự tạo** khóa đó. Muốn báo cáo cố định tất cả khu vực/kênh, phải bổ sung giá trị mặc định dựa vào danh mục nghiệp vụ sau khi tổng hợp.

### 5.4. collectingAndThen: biến đổi kết quả cuối

Khi muốn mỗi nhóm trả về danh sách **không cho phép thêm/xóa/sửa qua List API**:

```java
Map<String, List<Sale>> stableGroups = sales.stream().collect(
    Collectors.groupingBy(
        Sale::region,
        Collectors.collectingAndThen(
            Collectors.toList(),
            List::copyOf
        )
    )
);
```

`collectingAndThen(downstream, finisher)` cho phép chạy một bước hoàn tất trên **kết quả downstream của mỗi nhóm**. `List.copyOf` tạo danh sách không cho phép sửa cấu trúc; nó từ chối phần tử `null`. Nếu `Sale` hoặc những object bên trong nó mutable, việc dùng `List.copyOf` vẫn chỉ tạo **bất biến nông** (*shallow immutability*), không đóng băng toàn bộ object graph.

Đừng nhầm:

- `Collectors.toList()`: tài liệu không cam kết loại List cụ thể hoặc nó có cho phép sửa hay không.
- `Collectors.toUnmodifiableList()`: tạo danh sách không cho phép sửa và không chấp nhận phần tử null.
- `Stream.toList()`: là **terminal operation khác**, không phải collector downstream truyền trực tiếp vào `groupingBy`.
- `Collectors.toCollection(ArrayList::new)`: khi cần định rõ một collection mutable cụ thể.

## 6. Tổng hợp số liệu theo nhóm

Tùy yêu cầu, không cần lưu danh sách cho mọi khóa. Các collector thống kê tích lũy lượng thông tin gọn hơn.

| Collector | Kết quả | Trường hợp sử dụng |
| --- | --- | --- |
| `counting()` | `Long` | Số bản ghi trong nhóm |
| `summingInt(mapper)` | `Integer` | Tổng trường kiểu int |
| `summingLong(mapper)` | `Long` | Tổng trường kiểu long |
| `summingDouble(mapper)` | `Double` | Tổng giá trị double |
| `averagingInt/Long/Double(mapper)` | `Double` | Trung bình, bằng `0.0` nếu nhóm rỗng |
| `summarizingInt/Long/Double(mapper)` | `Int/Long/DoubleSummaryStatistics` | Count, sum, min, max, average trong một đối tượng |
| `minBy(comparator)` / `maxBy(comparator)` | `Optional<T>` | Phần tử nhỏ nhất/lớn nhất của từng nhóm |
| `reducing(identity, mapper, op)` | Kiểu phù hợp với giá trị giảm | Giảm dữ liệu với phép toán kết hợp, ví dụ cộng `BigDecimal` |

### 6.1. Đếm, tính tổng, trung bình theo khu vực

```java
Map<String, Long> counts = sales.stream().collect(
    Collectors.groupingBy(Sale::region, Collectors.counting())
);

Map<String, Long> totals = sales.stream().collect(
    Collectors.groupingBy(
        Sale::region,
        Collectors.summingLong(Sale::amountCents)
    )
);

Map<String, Double> averages = sales.stream().collect(
    Collectors.groupingBy(
        Sale::region,
        Collectors.averagingLong(Sale::amountCents)
    )
);

// North: count=3, total=20000, average≈6666.67
// South: count=3, total=32000, average≈10666.67
```

`averagingLong` trả `Double`. Với tiền tệ, trung bình và số tiền cần làm tròn theo nghiệp vụ; đừng nhầm kết quả `double` với giá trị tiền chính xác. `summingLong` cũng có nguy cơ tràn `long` nếu phạm vi giá trị quá lớn; cần kiểm tra ràng buộc đầu vào hoặc dùng kiểu số phù hợp.

### 6.2. summarizingLong: một lượt có nhiều chỉ số

```java
Map<String, java.util.LongSummaryStatistics> stats = sales.stream().collect(
    Collectors.groupingBy(
        Sale::region,
        Collectors.summarizingLong(Sale::amountCents)
    )
);

java.util.LongSummaryStatistics north = stats.get("North");
System.out.println(north.getCount());   // 3
System.out.println(north.getSum());     // 20000
System.out.println(north.getMin());     // 3000
System.out.println(north.getMax());     // 12000
System.out.println(north.getAverage()); // 6666.666...
```

`LongSummaryStatistics` là một container thống kê, thích hợp khi cần đồng thời đếm, min/max, tổng và trung bình. Khi collection rỗng, các giá trị min/max của statistics dùng sentinel theo đặc tả; không nên trình bày sentinel như một “giá trị giao dịch thực”. Kiểm tra `getCount() == 0` trước khi hiển thị min/max.

### 6.3. maxBy/minBy: tìm bản ghi nổi bật của từng nhóm

```java
Map<String, java.util.Optional<Sale>> largestSale = sales.stream().collect(
    Collectors.groupingBy(
        Sale::region,
        Collectors.maxBy(
            java.util.Comparator.comparingLong(Sale::amountCents)
        )
    )
);

System.out.println(
    largestSale.get("South").orElseThrow().product()
); // Bag
```

`maxBy` cho `Optional<Sale>` vì collector cũng có thể được dùng trong nhóm rỗng (ví dụ lồng sau `filtering`). Nếu cần lấy bản ghi lớn nhất khi **đã xác thực chắc chắn không rỗng**, dùng `orElseThrow()`; trường hợp không chắc chắn thì xử lý `Optional.empty()` rõ ràng.

### 6.4. Cộng BigDecimal bằng reducing khi cần số thập phân chính xác

Trong ứng dụng tài chính thực tế, có thể lưu số tiền bằng `BigDecimal` thay vì tính ở đơn vị nhỏ nhất kiểu long. Khi đó dùng `reducing`:

```java
record Payment(String region, java.math.BigDecimal amount) {}

List<Payment> payments = List.of(
    new Payment("North", new java.math.BigDecimal("19.95")),
    new Payment("North", new java.math.BigDecimal("5.05")),
    new Payment("South", new java.math.BigDecimal("7.50"))
);

Map<String, java.math.BigDecimal> amountByRegion = payments.stream().collect(
    Collectors.groupingBy(
        Payment::region,
        Collectors.reducing(
            java.math.BigDecimal.ZERO,
            Payment::amount,
            java.math.BigDecimal::add
        )
    )
);

System.out.println(amountByRegion.get("North")); // 25.00
```

`reducing(identity, mapper, op)` dùng giá trị đơn vị `ZERO` và phép cộng kết hợp. `BigDecimal::add` trả đối tượng mới; tránh dùng phép cộng bằng `double` rồi chuyển sang `BigDecimal` nếu phải giữ chính xác dữ liệu tiền tệ. Trong hệ thống thật, quy tắc đồng tiền, scale và làm tròn phải được định nghĩa riêng.

## 7. Tổng hợp hai kết quả đồng thời với teeing

`Collectors.teeing(first, second, merger)` phân phối **mỗi phần tử** tới hai collector và dùng `merger` kết hợp hai kết quả cuối. Từ Java 12, `teeing` đã là API chính thức, vì vậy dùng trực tiếp trong Java 27.

Ví dụ cần trong cùng một nhóm vừa **đếm đơn** vừa **cộng số tiền**:

```java
record Summary(long count, long totalCents) {}

Map<String, Summary> overview = sales.stream().collect(
    Collectors.groupingBy(
        Sale::region,
        Collectors.teeing(
            Collectors.counting(),
            Collectors.summingLong(Sale::amountCents),
            Summary::new
        )
    )
);

System.out.println(overview.get("North")); // Summary[count=3, totalCents=20000]
```

Giải thích:

- `counting()` tạo kết quả `Long`.
- `summingLong(Sale::amountCents)` tạo kết quả `Long`.
- `Summary::new` tạo một record tổng hợp từ hai giá trị.
- Mỗi key region có **một** kết quả `Summary`, không cần Map con để chứa hai chỉ số rời rạc.

`teeing` hữu ích khi hai phép tính có thể độc lập trên cùng tập đầu vào, nhưng không tự có hiệu năng vượt trội trong mọi trường hợp. Với những chỉ số cùng kiểu mà `summarizingLong` đã cung cấp (count/sum/min/max/average), hãy cân nhắc `summarizingLong` trước để tránh cấu trúc quá phức tạp.

**Lưu ý:** nếu `Summary` dùng constructor có hành vi kiểm tra dữ liệu, việc kiểm tra diễn ra khi kết quả được ghép. Với một nhóm rỗng tồn tại do `filtering` hoặc `partitioningBy`, downstream của `teeing` cũng tạo kết quả trên đầu vào rỗng: `counting() -> 0L` và `summingLong(...) -> 0L`.

## 8. Nhóm nhiều tầng: groupingBy lồng groupingBy

Một nhóm đơn có thể chưa đủ. Muốn báo cáo **khu vực → kênh → tổng doanh thu**, lồng collector:

```java
Map<String, Map<String, Long>> revenueByRegionAndChannel =
    sales.stream().collect(
        Collectors.groupingBy(
            Sale::region,
            Collectors.groupingBy(
                Sale::channel,
                Collectors.summingLong(Sale::amountCents)
            )
        )
    );

System.out.println(revenueByRegionAndChannel.get("North").get("WEB"));   // 17000
System.out.println(revenueByRegionAndChannel.get("North").get("STORE")); // 3000
System.out.println(revenueByRegionAndChannel.get("South").get("WEB"));   // 28000
System.out.println(revenueByRegionAndChannel.get("South").get("STORE")); // 4000
```

Từ ngoài vào trong:

1. `groupingBy(Sale::region, ...)` tạo một key cho mỗi khu vực.
2. `groupingBy(Sale::channel, ...)` tạo map con cho mỗi kênh trong khu vực.
3. `summingLong(...)` tính tổng các giao dịch thuộc cặp `(region, channel)`.

Kiểu kết quả phản ánh cấu trúc báo cáo:

```text
Map<String, Map<String, Long>>
    region ──────┘  └── channel └── tổng cents
```

### 8.1. Hai tầng và nhiều chỉ số cho từng nhóm lá

Lồng `teeing` vào tầng cuối:

```java
Map<String, Map<String, Summary>> detailed = sales.stream().collect(
    Collectors.groupingBy(
        Sale::region,
        TreeMap::new,
        Collectors.groupingBy(
            Sale::channel,
            TreeMap::new,
            Collectors.teeing(
                Collectors.counting(),
                Collectors.summingLong(Sale::amountCents),
                Summary::new
            )
        )
    )
);
```

Map ngoài là khu vực, Map trong là kênh và `Summary` là các chỉ số của mỗi cặp. `TreeMap::new` ở **mỗi tầng** giúp có thứ tự khóa xác định theo natural ordering. Nếu chỉ đặt map factory ở tầng ngoài, không được suy ra Map trong cũng được sắp xếp.

### 8.2. Kết hợp groupingBy với partitioningBy

Yêu cầu: trong từng khu vực, chia giao dịch thành **giá trị cao/thấp** rồi đếm:

```java
Map<String, Map<Boolean, Long>> tierCounts = sales.stream().collect(
    Collectors.groupingBy(
        Sale::region,
        Collectors.partitioningBy(
            sale -> sale.amountCents() >= 10_000,
            Collectors.counting()
        )
    )
);

System.out.println(tierCounts.get("North").get(true));  // 1
System.out.println(tierCounts.get("North").get(false)); // 2
System.out.println(tierCounts.get("South").get(true));  // 1
System.out.println(tierCounts.get("South").get(false)); // 2
```

Điểm hay: khu vực nào **đã xuất hiện** trong nguồn sẽ có **cả** giá trị `true` lẫn `false` trong Map con, kể cả khi một phía bằng 0. Nhưng một khu vực hoàn toàn vắng mặt trong nguồn sẽ không có Map ngoài nếu không bổ sung riêng.

### 8.3. Khi nào lồng quá nhiều tầng?

Mỗi tầng nhóm làm kiểu dữ liệu dài hơn, ví dụ `Map<K1, Map<K2, Map<K3, Summary>>>`. Có thể dùng nếu cấu trúc nghiệp vụ thực sự có dạng phân cấp. Nếu người gọi khó xử lý nhiều null hoặc phải xuất sang API/JSON định dạng ổn định, hãy cân nhắc:

- Dùng một **composite key** dạng record, ví dụ `record RegionChannel(String region, String channel) {}`, rồi `groupingBy(s -> new RegionChannel(s.region(), s.channel()), downstream)`.
- Tạo các record báo cáo có tên, thay vì dùng ba hoặc bốn Map lồng nhau.
- Tổng hợp một lần rồi chuyển kết quả sang DTO báo cáo theo yêu cầu của tầng hiển thị.

Việc làm phẳng hay lồng nhóm là quyết định thiết kế mô hình đầu ra, không phải giới hạn của `Collectors`.

## 9. Phân biệt groupingBy với toMap khi có khóa trùng

`groupingBy` được thiết kế để **nhiều phần tử có cùng khóa**; collector ở mỗi khóa quyết định cách tích lũy:

```java
Map<String, Long> countsByProduct = sales.stream().collect(
    Collectors.groupingBy(Sale::product, Collectors.counting())
);
// Book = 2, Pen = 3, Bag = 1
```

Ngược lại, `Collectors.toMap(keyMapper, valueMapper)` hai đối số yêu cầu khóa không trùng. Nếu dữ liệu có hai `Sale` mang `product = "Book"`, cách viết sau sẽ ném `IllegalStateException`:

```java
// NÉM IllegalStateException vì product trùng
Map<String, Long> invalid = sales.stream().collect(
    Collectors.toMap(Sale::product, Sale::amountCents)
);
```

Nếu mục tiêu là cộng dồn giá trị cho khóa trùng, có thể truyền **merge function**:

```java
Map<String, Long> amountsByProduct = sales.stream().collect(
    Collectors.toMap(
        Sale::product,
        Sale::amountCents,
        Long::sum
    )
);
```

Tuy nhiên, với phép **báo cáo nhóm** tổng quát, `groupingBy(..., summingLong(...))` thường trực quan hơn, dễ mở rộng sang nhiều tầng, còn `toMap` rất phù hợp khi đã có cặp khóa/giá trị và chính sách xử lý khóa trùng rõ ràng.

## 10. Điều cần biết về thứ tự, tính bất biến và null

### 10.1. Thứ tự phần tử không giống thứ tự khóa Map

`groupingBy` không cam kết thứ tự duyệt key của Map mặc định. Với một Stream tuần tự có encounter order, dùng `LinkedHashMap::new` nếu cần key theo thứ tự xuất hiện đầu tiên:

```java
Map<String, List<Sale>> orderedGroups = sales.stream().collect(
    Collectors.groupingBy(
        Sale::region,
        java.util.LinkedHashMap::new,
        Collectors.toList()
    )
);
```

`List` được `toList()` tạo theo **encounter order** của một Stream có thứ tự đầu vào. Nhưng thứ tự key của `Map` và thứ tự phần tử trong mỗi `List` là hai đặc tính độc lập. Nếu muốn nhóm được sắp theo tiêu chí nghiệp vụ, có thể dùng `collectingAndThen` với `List.copyOf(list.stream().sorted(...).toList())` hoặc sắp xếp một danh sách mutable mới một cách tường minh.

### 10.2. Không mặc định Map và List trả về đều mutable

Tài liệu `Collectors` của Java SE 27 nói rõ nhiều collector không cam kết loại collection, độ mutability, serializability hoặc thread-safety của kết quả. Nếu cần chắc chắn kết quả **không cho phép sửa**, tạo snapshot có chủ đích:

```java
Map<String, List<Sale>> immutableListsByRegion = sales.stream().collect(
    Collectors.groupingBy(
        Sale::region,
        Collectors.collectingAndThen(
            Collectors.toList(),
            List::copyOf
        )
    )
);

Map<String, List<Sale>> immutableMapAndLists =
    Map.copyOf(immutableListsByRegion);
```

`Map.copyOf` từ chối key/value null và tạo map không cho phép sửa, nhưng **không bảo đảm thứ tự duyệt key** theo `TreeMap` hoặc `LinkedHashMap`. Đồng thời, bất biến của collection chỉ là **bề mặt**: nếu một phần tử bên trong chứa object mutable, trạng thái object đó vẫn có thể thay đổi.

### 10.3. Null và trường hợp rỗng

- `groupingBy` trên nguồn rỗng: Map rỗng.
- `groupingBy` và classifier trả null: triển khai JDK từ chối khóa null (`NullPointerException`).
- `partitioningBy` trên nguồn rỗng: Map **có đủ** `false` và `true`, hai phía mang kết quả downstream trên đầu vào rỗng.
- `Collectors.toUnmodifiableList()`, `List.copyOf(...)`, `Map.copyOf(...)` đều có quy tắc từ chối null thích hợp; không dùng khi dữ liệu chưa xử lý null.
- `minBy/maxBy` và collector `reducing(BinaryOperator)` dùng `Optional` để diễn đạt việc không có kết quả; đừng gọi `get()` hoặc `orElseThrow()` mà không kiểm tra lý do hợp lệ.

## 11. Parallel stream và groupingByConcurrent

`groupingBy` thông thường **không phải concurrent collector**, dù có thể được dùng trên `parallelStream()`. Với phép tính song song, framework có thể tích lũy ở nhiều container riêng và gộp Map bằng `combiner`. Khi số nhóm lớn, chi phí gộp có thể đáng kể.

`groupingByConcurrent` trả `ConcurrentMap` và là một collector `CONCURRENT`, `UNORDERED`; phù hợp khi:

- Khối lượng dữ liệu và công việc đủ lớn để thử nghiệm parallel stream.
- Không cần bảo toàn encounter order bên trong danh sách kết quả.
- Classifier và downstream tuân thủ nguyên tắc không có side effect, dữ liệu đầu vào không bị mutate đồng thời.

```java
java.util.concurrent.ConcurrentMap<String, Long> counts =
    sales.parallelStream().collect(
        Collectors.groupingByConcurrent(
            Sale::region,
            Collectors.counting()
        )
    );

System.out.println(counts.get("North")); // 3
```

Cần phân biệt:

- `ConcurrentMap` kết quả không có nghĩa mọi `List`/object value bên trong đều thread-safe để tiếp tục mutate tùy ý; Javadoc cũng **không cam kết thread-safety của các List** trả về khi downstream là `toList()`.
- `groupingByConcurrent` được đặc tả là **unordered**. Với kết quả là danh sách, thứ tự encounter của phần tử trong mỗi nhóm có thể không còn được bảo toàn.
- Parallel không tự động nhanh hơn; chi phí phân vùng, đồng bộ, kết hợp và kích thước dữ liệu có thể làm nó chậm hơn luồng tuần tự.
- Với pipeline có thứ tự đầu vào quan trọng, hãy giữ `groupingBy` tuần tự hoặc kiểm soát thứ tự khi xây kết quả. Không ép mọi báo cáo sang concurrent chỉ để dùng nhiều CPU.

Trong pipeline song song, tránh accumulator ngoài như `HashMap` hoặc `ArrayList` bị mutate trong `forEach`. Dùng `collect` với collector thích hợp để Stream framework quản lý phép tích lũy và gộp kết quả.

## 12. Hiệu năng và cách chọn collector thực tế

Với `n` phần tử, phép nhóm/đếm theo một khóa thường đòi hỏi xử lý mỗi phần tử một lần, nhưng chi phí thật còn phụ thuộc vào hàm hash/so sánh, số lượng khóa và downstream.

| Thiết kế | Tác động tài nguyên | Khi thích hợp |
| --- | --- | --- |
| `groupingBy(key)` → `Map<K, List<T>>` | Giữ tham chiếu đến tất cả `n` phần tử qua các List | Cần truy xuất lại phần tử từng nhóm |
| `groupingBy(key, counting())` | Chủ yếu giữ `O(g)` trạng thái kết quả với `g` nhóm | Chỉ cần số lượng |
| `groupingBy(key, summingLong(...))` | Chủ yếu giữ `O(g)` trạng thái tổng | Chỉ cần tổng số |
| `groupingBy(key, summarizingLong(...))` | Giữ một vùng thống kê cho mỗi nhóm | Cần min/max/count/sum/average |
| `groupingBy(key, groupingBy(key2, downstream))` | Trạng thái tăng theo số cặp khóa thực tế và downstream | Báo cáo nhiều chiều |
| `partitioningBy(predicate, downstream)` | Hai nhóm cố định; chi phí phụ thuộc downstream | Báo cáo đạt/không đạt |
| `teeing(a, b, merger)` | Duy trì trạng thái tích lũy của **cả hai** downstream | Cần ghép hai thống kê độc lập |
| `groupingByConcurrent(...)` | Có chi phí đồng bộ/scheduling; thứ tự không bảo đảm | Dữ liệu lớn và benchmark chứng minh lợi ích |

Ký hiệu `O(g)` ở đây chỉ nhằm minh họa mức tăng trưởng **theo số nhóm**, không cam kết một giới hạn byte chính xác cho mọi implementation hoặc JVM.

Một Stream được collect sang Map/List thông thường cần đầu vào hữu hạn để hoàn tất và có thể tiêu thụ nhiều bộ nhớ. Nếu đọc tập dữ liệu cực lớn, cân nhắc tổng hợp theo lô, hoặc dùng cơ sở dữ liệu/hệ thống tính toán phân tán khi bài toán vượt giới hạn bộ nhớ ứng dụng.

**Lựa chọn khuyến nghị:** với hầu hết thống kê nghiệp vụ, bắt đầu từ Stream tuần tự, biểu diễn khóa/kiểu kết quả rõ ràng, đo benchmark thật trước khi chuyển sang `parallelStream`. Tránh xây các Map trung gian nếu một collector lồng nhau đã mô tả được báo cáo.

## 13. Lỗi thường gặp và cách sửa

| Lỗi/hiện tượng | Nguyên nhân | Cách khắc phục |
| --- | --- | --- |
| `NullPointerException` khi `groupingBy` | Classifier trả khóa null | Chuẩn hóa khóa hoặc chặn dữ liệu thiếu trước khi nhóm |
| `Map.get("STORE") == null` sau khi lọc | Dùng `stream.filter` trước `groupingBy` nên nhóm bị mất | Dùng downstream `Collectors.filtering` nếu muốn giữ nhóm có phần tử đầu vào |
| Báo cáo thiếu một khu vực hoàn toàn không có dữ liệu | `groupingBy` không tạo nhóm chưa từng gặp | Khởi tạo/bổ sung khóa từ danh mục nghiệp vụ sau khi tính |
| `partitioningBy` lại có hai key khi Stream rỗng | Đó là hợp đồng API, không phải lỗi | Xử lý cả `true` và `false`, kể cả kết quả downstream rỗng |
| Nhầm `Map<String,List<List<String>>>` thành `Map<String,Set<String>>` | `mapping` giữ danh sách con lồng nhau | Dùng `flatMapping` rồi `toSet`/`toCollection` |
| `List` kết quả không sửa được trên một JDK | `Collectors.toList()` không cam kết mutability | Dùng `toCollection(ArrayList::new)` nếu cần mutable, hoặc `toUnmodifiableList` nếu cần immutable |
| Thứ tự khóa Map thay đổi | `groupingBy` không cam kết thứ tự khóa mặc định | Dùng `TreeMap::new` hoặc `LinkedHashMap::new` trong overload ba tham số |
| `toMap` ném `IllegalStateException` | Trùng khóa và không có merge function | Dùng `groupingBy` hoặc `toMap(..., mergeFunction)` |
| Tổng `long` bất thường | Overflow hoặc dữ liệu đầu vào sai | Kiểm tra phạm vi, chọn `BigDecimal`/kiểu dữ liệu phù hợp |
| `Optional.get()` ném exception sau `maxBy` | Downstream không có phần tử để chọn | Xử lý `Optional.empty()` hoặc chứng minh nhóm không rỗng |
| `parallelStream` nhanh chậm không ổn định | Chi phí gộp kết quả, đồng bộ, số nhóm, tải JVM | Benchmark và tránh phụ thuộc parallel mặc định |
| Danh sách trong `groupingByConcurrent` bị sửa đồng thời gây lỗi | Outer `ConcurrentMap` không đồng nghĩa inner `List` thread-safe | Xử lý kết quả sau collect và không mutate value từ nhiều thread |
| Bài toán tiền tệ sai phần lẻ | Dùng `double` như số tiền chính xác | Dùng đơn vị tiền nhỏ nhất hoặc `BigDecimal` và quy tắc làm tròn rõ |
| Gọi `collect` hai lần trên cùng Stream | Stream đã bị tiêu thụ ở lần đầu | Tạo Stream mới từ nguồn cho từng terminal operation |

## 14. Bài tập tự kiểm tra và checklist

Với 6 giao dịch trong `sampleSales()`, hãy tự tính trước khi chạy chương trình:

1. `groupingBy(Sale::product, counting())` phải cho số lượng: Book = **2**, Pen = **3**, Bag = **1**.
2. `groupingBy(Sale::region, summingLong(Sale::amountCents))`: North = **20_000**, South = **32_000**.
3. `partitioningBy(s -> s.amountCents() >= 10_000, counting())`: true = **2**, false = **4**.
4. `groupingBy(Sale::region, groupingBy(Sale::channel, summingLong(...)))`: North/WEB = **17_000**, North/STORE = **3_000**, South/WEB = **28_000**, South/STORE = **4_000**.
5. `groupingBy(Sale::channel, filtering(s -> s.amountCents() >= 20_000, toList()))` vẫn phải có khóa `STORE` với List rỗng.

Checklist trước khi dùng collector trong sản phẩm:

- **Chọn đúng phép chia:** nhiều khóa → `groupingBy`; điều kiện nhị phân → `partitioningBy`.
- **Chọn dữ liệu đầu ra tối thiểu:** cần phần tử gốc → `toList`; chỉ cần số liệu → `counting`/`summingLong`/`summarizingLong`.
- **Tách rõ loại biến đổi:** `mapping` tạo một phần tử mới; `flatMapping` tạo nhiều phần tử; `filtering` loại phần tử **sau khi xác định nhóm**.
- **Thiết kế loại Map và thứ tự:** nếu thứ tự khóa quan trọng, chỉ định `mapFactory`; đừng trông đợi vào implementation mặc định.
- **Xử lý null/nhóm rỗng:** classifier không nên trả null; phân biệt nhóm không tồn tại và nhóm tồn tại nhưng không có phần tử sau downstream `filtering`.
- **Biểu diễn báo cáo nhiều tầng có chủ đích:** lồng `groupingBy` vừa đủ; dùng record cho kết quả tổng hợp/khóa composite khi cấu trúc phức tạp.
- **Kiểm soát mutability:** không cho rằng `Collectors.toList()` luôn mutable; nếu cần snapshot không thể sửa, tạo bằng API rõ ràng.
- **Chọn số học chính xác:** với tiền, dùng `BigDecimal` hoặc đơn vị nhỏ nhất, kiểm tra phạm vi giá trị và làm tròn.
- **Giữ collector không có side effect:** tránh mutate trạng thái bên ngoài hoặc giả định thứ tự thực thi, đặc biệt với parallel.
- **Đo lường trước khi tối ưu:** `groupingByConcurrent` chỉ là lựa chọn khi thứ tự không quan trọng và benchmark xác nhận lợi ích.

## Tài liệu tham khảo chính thức

- [`Collectors` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Collectors.html) — `groupingBy`, `partitioningBy`, `mapping`, `flatMapping`, `filtering`, `reducing`, `teeing` và các collector thống kê.
- [`Collector<T,A,R>` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Collector.html) — supplier/accumulator/combiner/finisher, characteristics và các yêu cầu khi dùng song song.
- [`Stream<T>` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/Stream.html) — `collect` terminal operation, `toList()` và quy tắc tiêu thụ pipeline.
- [`java.util.stream` package — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/stream/package-summary.html) — pipeline, encounter order và concurrent reduction.
- [`LongSummaryStatistics` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/LongSummaryStatistics.html) — các phép thống kê count/sum/min/max/average.
- [`Map` — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Map.html) — các hợp đồng Map và `Map.copyOf`.
