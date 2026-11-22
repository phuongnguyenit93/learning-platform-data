# Kết hợp collector đủ rõ ràng và tránh cấu trúc lồng quá sâu trong Java

## 1. Mục tiêu: làm rõ ý nghĩa của từng cấp collector

Trong Java Stream API, các phương thức `Collectors.groupingBy()`, `mapping()`, `filtering()`, `flatMapping()`, `collectingAndThen()`, `teeing()` và các collector thống kê có thể được **lồng vào nhau** để tính nhiều loại báo cáo. Tuy nhiên, một biểu thức collector hợp lệ về kiểu dữ liệu chưa chắc đã **dễ đọc, dễ kiểm thử và dễ bảo trì**.

Ví dụ, muốn lập bản đồ `region → danh sách tên sản phẩm đã thanh toán`, ta có thể viết tất cả trong một expression:

```java
Map<String, List<String>> result = sales.stream().collect(
        Collectors.groupingBy(
                Sale::region,
                TreeMap::new,
                Collectors.filtering(
                        Sale::paid,
                        Collectors.mapping(
                                Sale::product,
                                Collectors.toList()))));
```

Đây là **đoạn trong thân phương thức**; nó sử dụng record `Sale` và các import có trong chương trình hoàn chỉnh ở mục 6. Đoạn mã **có thể đúng** nhưng bắt người đọc phải lần theo nhiều cặp ngoặc để nhận ra ba mục tiêu riêng:

1. **Phân nhóm** theo `region`.
2. **Trong từng nhóm**, chỉ chọn các Sale có `paid == true`.
3. **Biến đổi** Sale thành `product` rồi thu vào List.

Nếu mở rộng thêm tổng tiền, số lượng, danh sách tên, mức ưu tiên và nhiều cấp nhóm, biểu thức sẽ sâu hơn và khó chỉ ra chỗ gây lỗi.

Mục tiêu không phải cấm lồng collector. Mục tiêu là **mỗi cấp phải có một trách nhiệm dễ diễn đạt**, và khi logic có tên nghiệp vụ rõ ràng thì nên trích nó thành biến/phương thức hoặc một kiểu dữ liệu kết quả thích hợp.

## 2. Hiểu collector trước khi kết hợp

`Collector<T,A,R>` biểu diễn quy tắc **tích lũy** các phần tử kiểu `T`, với trạng thái tích lũy nội bộ `A`, để tạo kết quả kiểu `R`. Trong ứng dụng thông thường, phần `A` là chi tiết triển khai, nên nhiều ví dụ khai báo `Collector<T, ?, R>`.

Ví dụ:

```java
Collector<Sale, ?, Long> countSales = Collectors.counting();
Collector<Sale, ?, Integer> sumAmount =
        Collectors.summingInt(Sale::amount);
```

Đây là hai lệnh trong lớp có record `Sale` và import `java.util.stream.Collector`, `Collectors`. `counting` tạo một `Long` đếm số phần tử; `summingInt` tổng hợp thuộc tính `int` thành một `Integer` (và có thể tràn `int` nếu dữ liệu lớn).

Một số collector có **đầu vào/đầu ra** dễ hình dung:

| Collector | Ý nghĩa | Kiểu kết quả điển hình |
| --- | --- | --- |
| `toList()` | Thu các phần tử | `List<T>` |
| `counting()` | Đếm phần tử | `Long` |
| `summingInt(mapper)` | Cộng giá trị nguyên từ từng phần tử | `Integer` |
| `mapping(mapper, downstream)` | Đổi loại phần tử trước khi chuyển xuống collector con | Kết quả của `downstream` |
| `filtering(predicate, downstream)` | Chỉ chuyển phần tử đạt điều kiện xuống collector con | Kết quả của `downstream` |
| `groupingBy(classifier, downstream)` | Phân nhóm rồi thu theo từng nhóm | `Map<K,D>` |
| `collectingAndThen(downstream, finisher)` | Biến đổi kết quả cuối của downstream | Kiểu trả của `finisher` |
| `teeing(down1, down2, merger)` | Tính hai kết quả song song về mặt collector rồi kết hợp | Kiểu trả của `merger` |

Hãy đọc các collector theo **luồng dữ liệu**. Một biểu thức như `groupingBy(region, mapping(name, toList()))` có nghĩa: phần tử Sale được xếp nhóm theo region, sau đó trong mỗi nhóm **tên** được thu vào List.

Không nên nhầm `mapping` downstream với `Stream.map` ở upstream. Chúng có thể cho cùng kết quả trong một số tình huống nhưng **thứ tự thao tác và cách giữ nhóm** có thể khác, đặc biệt khi thêm `filtering`.

## 3. Dấu hiệu một collector đã lồng quá sâu

Không có số tầng lồng tối đa mà Java hoặc Javadoc quy định là “đúng”. Vấn đề là **gánh nặng nhận thức**: nếu một người đọc phải đếm nhiều dấu ngoặc và tự suy diễn toàn bộ kiểu generic mới hiểu được quy tắc nghiệp vụ thì nên xem xét trích xuất.

Các dấu hiệu đáng chú ý:

- `collect(...)` kéo dài hàng chục dòng với nhiều collector con và lambda không có tên.
- Cùng một tổ hợp `filtering(..., mapping(..., toList()))` được sao chép trong nhiều báo cáo.
- Kiểu kết quả trở thành `Map<String, Map<String, Map<String, List<...>>>>` trong khi người dùng cuối chỉ cần vài cột báo cáo.
- Nhiều điều kiện nghiệp vụ, chuyển đổi chuỗi, xác định quyền truy cập và xử lý ngoại lệ nằm sâu trong `keyMapper`, `valueMapper` hoặc `merger`.
- Thay đổi một điều kiện lọc khiến không rõ nhóm nào bị **mất**, nhóm nào còn nhưng có giá trị rỗng.
- Khó đặt unit test cho một phép biến đổi nhỏ mà không phải chạy cả pipeline.
- Kết quả trả ra là map lồng khó dùng, trong khi một record mô tả ý nghĩa tốt hơn.
- Có quá nhiều đoạn `get(...).get(...).get(...)` ở caller, dễ gặp `null` và thiếu kiểu dữ liệu miền nghiệp vụ.

Một quy tắc thực dụng: nếu không thể đặt tên ngắn gọn cho từng cấp của collector thì nên tách hoặc xem lại mô hình kết quả. Ngược lại, `groupingBy(Category::id, counting())` rất ngắn gọn và **không cần trích xuất máy móc** chỉ để tránh lồng.

## 4. Phương án 1: đặt tên cho downstream collector

Thay vì luôn viết nguyên biểu thức:

```java
Map<String, List<String>> paidProducts = sales.stream().collect(
        Collectors.groupingBy(
                Sale::region,
                TreeMap::new,
                Collectors.filtering(
                        Sale::paid,
                        Collectors.mapping(
                                Sale::product,
                                Collectors.toList()))));
```

Hãy đặt tên cho logic có ý nghĩa:

```java
static Collector<Sale, ?, List<String>> paidProductNames() {
    return Collectors.filtering(
            Sale::paid,
            Collectors.mapping(Sale::product, Collectors.toList()));
}
```

Rồi sử dụng:

```java
Map<String, List<String>> paidProducts = sales.stream().collect(
        Collectors.groupingBy(
                Sale::region, TreeMap::new, paidProductNames()));
```

Hai đoạn là **trích từ cấu trúc lớp và phương thức** ở chương trình `ReadableCollectorDemo.java` bên dưới; khi ghép vào ứng dụng cần record `Sale` và các import tương ứng.

Cách này cải thiện nhiều mặt:

1. Dòng gọi `groupingBy` đọc gần như một câu tiếng Việt: “nhóm theo region, thu tên sản phẩm đã thanh toán”.
2. Phép lọc và phép ánh xạ có thể được kiểm thử độc lập.
3. Tên `paidProductNames` diễn đạt nghiệp vụ, không buộc caller đọc chi tiết `filtering(mapping(...))`.
4. Khi chính sách thanh toán thay đổi, sửa một nơi.
5. Kiểu `Collector<Sale, ?, List<String>>` mô tả đúng hợp đồng: nhận Sale, tạo danh sách String.

**Lưu ý generic:** dấu `?` ở tham số tích lũy `A` là chủ ý. Không cố “đoán” kiểu trạng thái nội bộ của `Collectors.mapping`, vì kiểu đó thường không phải một phần nghiệp vụ cần quan tâm.

## 5. filter() trước groupingBy() khác filtering() bên trong groupingBy()

Đây là khác biệt ngữ nghĩa quan trọng, không chỉ là chuyện trình bày code.

**Cách A — lọc trước khi phân nhóm:**

```java
Map<String, List<String>> filteredFirst = sales.stream()
        .filter(Sale::paid)
        .collect(Collectors.groupingBy(
                Sale::region,
                TreeMap::new,
                Collectors.mapping(Sale::product, Collectors.toList())));
```

**Cách B — nhóm trước, lọc downstream:**

```java
Map<String, List<String>> downstreamFiltered = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::region,
                TreeMap::new,
                Collectors.filtering(
                        Sale::paid,
                        Collectors.mapping(Sale::product, Collectors.toList()))));
```

Hai đoạn giả định có `sales: List<Sale>` và các import thích hợp. Trên bộ dữ liệu trong chương trình hoàn chỉnh, region `West` chỉ có một Sale **chưa thanh toán**.

Kết quả:

```text
filteredFirst={North=[A, C], South=[E]}
downstreamFiltered={North=[A, C], South=[E], West=[]}
```

Giải thích:

- Ở **Cách A**, bản ghi `West` bị loại **trước khi** có một entry nhóm, nên map **không có khóa `West`**.
- Ở **Cách B**, classifier `Sale::region` tạo/nhận diện nhóm `West` trước, downstream `filtering` không đưa Sale nào vào List, nên `West=[]`.

Tương tự, `groupingBy(region, filtering(paid, counting()))` có thể giữ `West=0`. Điều này quan trọng trong dashboard và báo cáo: “nhóm có doanh số thanh toán bằng 0” khác với “nhóm hoàn toàn không tồn tại”.

Không nên thay `Collectors.filtering` bằng `Stream.filter` chỉ để rút ngắn số tầng lồng khi yêu cầu nghiệp vụ phải **giữ các nhóm có kết quả rỗng**.

## 6. Ví dụ chạy được: tách logic thành các collector có tên

Lưu nội dung sau thành `ReadableCollectorDemo.java`:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class ReadableCollectorDemo {
    record Sale(String region, String product, int amount, boolean paid) {}

    static Collector<Sale, ?, List<String>> paidProductNames() {
        return Collectors.filtering(
                Sale::paid,
                Collectors.mapping(Sale::product, Collectors.toList()));
    }

    static Collector<Sale, ?, Long> paidCount() {
        return Collectors.filtering(Sale::paid, Collectors.counting());
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("North", "A", 10, true),
                new Sale("South", "B", 20, false),
                new Sale("North", "C", 30, true),
                new Sale("West", "D", 5, false),
                new Sale("South", "E", 40, true),
                new Sale("North", "F", 12, false));

        Map<String, Long> counts = sales.stream().collect(
                Collectors.groupingBy(Sale::region,
                        TreeMap::new, Collectors.counting()));
        System.out.println("counts=" + counts);

        Map<String, Long> paidCounts = sales.stream().collect(
                Collectors.groupingBy(Sale::region,
                        TreeMap::new, paidCount()));
        System.out.println("paidCounts=" + paidCounts);

        Map<String, List<String>> paidProducts = sales.stream().collect(
                Collectors.groupingBy(Sale::region,
                        TreeMap::new, paidProductNames()));
        System.out.println("paidProducts=" + paidProducts);

        Map<String, List<String>> filteredFirst = sales.stream()
                .filter(Sale::paid)
                .collect(Collectors.groupingBy(Sale::region,
                        TreeMap::new,
                        Collectors.mapping(Sale::product, Collectors.toList())));
        System.out.println("filteredFirst=" + filteredFirst);

        Collector<Sale, ?, Integer> sumAmount =
                Collectors.summingInt(Sale::amount);
        Map<String, Integer> sums = sales.stream().collect(
                Collectors.groupingBy(Sale::region,
                        TreeMap::new, sumAmount));
        System.out.println("sums=" + sums);
    }
}
```

Biên dịch và chạy với Java 17:

```bash
javac --release 17 -encoding UTF-8 ReadableCollectorDemo.java
java ReadableCollectorDemo
```

Đầu ra chính xác trên chương trình đã kiểm thử:

```text
counts={North=3, South=2, West=1}
paidCounts={North=2, South=1, West=0}
paidProducts={North=[A, C], South=[E], West=[]}
filteredFirst={North=[A, C], South=[E]}
sums={North=52, South=60, West=5}
```

Chi tiết:

- `counts` dùng `counting()` downstream để đếm **tất cả** Sale theo region.
- `paidCounts` dùng một collector có tên `paidCount()`, cho `West=0` vì nhóm West đã được tạo bởi `groupingBy`.
- `paidProducts` dùng `paidProductNames()`, giữ `West=[]`.
- `filteredFirst` đặt `filter` trước nhóm nên không có West.
- `sums` dùng biến collector `sumAmount` riêng để biểu đạt một tiêu chí tổng hợp khác. Ví dụ có giá trị nhỏ nên `int` không tràn; với tổng có thể vượt `int`, cần chọn kiểu tổng khác theo miền nghiệp vụ.

`TreeMap::new` giúp output theo thứ tự khóa `North`, `South`, `West`. Dùng `HashMap`/overload mặc định có thể hoạt động đúng về mặt ánh xạ nhưng **không cam kết thứ tự in** như ví dụ này.

## 7. Phương án 2: dùng record thay cho Map nhiều tầng

Một lỗi thiết kế thường gặp là biến mọi trục dữ liệu thành một `Map` lồng:

```text
Map<Region, Map<Status, Map<Product, List<Sale>>>>
```

Không phải cấu trúc này luôn sai. Nó phù hợp nếu caller thực sự cần truy vấn theo **ba cấp khóa**. Nhưng nếu màn hình chỉ hiển thị:

```text
Region | Số đơn đã thanh toán | Tổng giá trị
North  | 2                    | 52
South  | 1                    | 60
West   | 0                    | 5
```

thì `Map<String, RegionSummary>` thường dễ dùng hơn:

```java
record RegionSummary(long paidCount, int amountTotal) {}
```

Đây là khai báo record trong lớp `StructuredCollectorDemo` ở mục 10. Caller có thể đọc `summary.paidCount()`, `summary.amountTotal()` thay vì `map.get("paid").get(...)`. Compiler kiểm tra tên/kiểu trường ngay tại thời điểm biên dịch.

Một **record**:

- Đặt tên cho ý nghĩa và loại của từng số liệu.
- Cho phép thay đổi cách tính ở bên trong collector mà không buộc caller biết cấu trúc Map lồng.
- Giúp viết test `assertEquals(new RegionSummary(2,52), result.get("North"))`.
- Tránh “stringly typed” — những khóa `"paidCount"`, `"amount"` dễ gõ sai và chỉ phát hiện lúc chạy.

Tuy nhiên record không tự xác thực mọi bất biến và không làm cho tham chiếu tới đối tượng mutable trong các thành phần trở thành bất biến sâu. Trong ví dụ, hai thành phần là số nguyên thủy nên record rất thuận tiện.

## 8. Phương án 3: teeing() cho hai chỉ số cùng một nguồn

Khi cần tính **hai kết quả** từ cùng một nhóm, `Collectors.teeing` (Java 12+) giúp biểu đạt rõ:

```java
record RegionSummary(long paidCount, int amountTotal) {}

static Collector<Sale, ?, RegionSummary> summaryForRegion() {
    Collector<Sale, ?, Long> paidCount =
            Collectors.filtering(Sale::paid, Collectors.counting());
    Collector<Sale, ?, Integer> amountTotal =
            Collectors.summingInt(Sale::amount);
    return Collectors.teeing(
            paidCount,
            amountTotal,
            RegionSummary::new);
}
```

Đây là các khai báo đặt trong lớp có record `Sale` và import `Collector`, `Collectors`. Hai collector downstream có vai trò riêng:

1. `paidCount`: đếm các Sale đã thanh toán.
2. `amountTotal`: cộng `amount` của **tất cả** Sale trong nhóm, không chỉ Sale đã thanh toán.
3. `RegionSummary::new`: kết hợp hai kết quả thành một kiểu trả cụ thể.

Dùng trong `groupingBy`:

```java
Map<String, RegionSummary> byRegion = sales.stream().collect(
        Collectors.groupingBy(
                Sale::region, TreeMap::new, summaryForRegion()));
```

Lúc này caller thấy ngay cấu trúc kết quả `Map<String,RegionSummary>` mà không phải hiểu nested generic. `teeing` không có nghĩa “tự mở hai stream nguồn và chạy terminal hai lần”: nó là **một collector** kết hợp hai downstream dưới cơ chế thu thập.

**Không nhầm với một phép gộp tùy ý:** `teeing` nhận `downstream1`, `downstream2`, và `merger` cho **hai kết quả cuối**, chứ không phải merge function cho hai phần tử cùng khóa như `toMap(..., mergeFunction)`.

## 9. Tránh lạm dụng teeing() ở mọi nơi

`teeing` tốt khi **hai số liệu thực sự cùng một đối tượng báo cáo**; nếu số liệu chỉ dùng ở hai màn hình khác nhau, có thể không cần gộp chung trong cùng collector.

Khi số lượng chỉ tiêu tăng lên năm, mười, nhiều tầng `teeing(teeing(...), teeing(...), ...)` sẽ khiến code khó đọc trở lại. Khi ấy cân nhắc:

- Một **collector tùy chỉnh** có accumulator/report riêng nếu nhiều chỉ số được tính liên quan.
- Một đối tượng thống kê trung gian có tên phương thức rõ ràng, được cập nhật trong một vòng duyệt.
- Nhiều phép tính riêng nếu dữ liệu nhỏ, nguồn có thể duyệt lại và cách đó dễ kiểm thử hơn.
- Nhóm dữ liệu trước rồi xử lý từng nhóm thành record, nếu cách tính cần logic phức tạp vượt quá khả năng biểu đạt rõ của downstream collector.

**Đừng đánh đổi tính dễ hiểu cho “một pipeline duy nhất” bằng mọi giá.** Một lần duyệt có thể hữu ích với nguồn lớn hoặc I/O one-shot, nhưng ba phép tính rõ ràng trên một `List` nhỏ đôi khi an toàn và dễ bảo trì hơn một cấu trúc collector quá sâu.

## 10. Ví dụ chạy được: teeing, collectingAndThen và DTO rõ nghĩa

Lưu toàn bộ chương trình sau vào `StructuredCollectorDemo.java`:

```java
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class StructuredCollectorDemo {
    record Sale(String region, String product, int amount, boolean paid) {}
    record RegionSummary(long paidCount, int amountTotal) {}
    record OverallSummary(long saleCount, int amountTotal) {}

    static Collector<Sale, ?, RegionSummary> summaryForRegion() {
        Collector<Sale, ?, Long> paidCount =
                Collectors.filtering(Sale::paid, Collectors.counting());
        Collector<Sale, ?, Integer> amountTotal =
                Collectors.summingInt(Sale::amount);

        return Collectors.teeing(
                paidCount,
                amountTotal,
                RegionSummary::new);
    }

    static Collector<Sale, ?, Map<String, RegionSummary>> immutableByRegion() {
        Collector<Sale, ?, Map<String, RegionSummary>> grouped =
                Collectors.groupingBy(Sale::region,
                        TreeMap::new, summaryForRegion());
        return Collectors.collectingAndThen(
                grouped, Collections::unmodifiableMap);
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("North", "A", 10, true),
                new Sale("South", "B", 20, false),
                new Sale("North", "C", 30, true),
                new Sale("West", "D", 5, false),
                new Sale("South", "E", 40, true),
                new Sale("North", "F", 12, false));

        Map<String, RegionSummary> report =
                sales.stream().collect(immutableByRegion());
        System.out.println("regions=" + report);
        try {
            report.put("Other", new RegionSummary(0, 0));
        } catch (UnsupportedOperationException e) {
            System.out.println("immutable=" + e.getClass().getSimpleName());
        }

        Collector<Sale, ?, OverallSummary> overallCollector =
                Collectors.teeing(
                        Collectors.counting(),
                        Collectors.summingInt(Sale::amount),
                        OverallSummary::new);
        System.out.println("overall=" + sales.stream().collect(overallCollector));

        Map<Boolean, List<String>> partitioned = sales.stream().collect(
                Collectors.partitioningBy(Sale::paid,
                        Collectors.mapping(Sale::product, Collectors.toList())));
        System.out.println("unpaid=" + partitioned.get(false));
        System.out.println("paid=" + partitioned.get(true));

        Map<String, List<String>> copied = sales.stream().collect(
                Collectors.groupingBy(
                        Sale::region,
                        TreeMap::new,
                        Collectors.mapping(
                                Sale::product,
                                Collectors.collectingAndThen(
                                        Collectors.toList(), List::copyOf))));
        System.out.println("copiedNorth=" + copied.get("North"));
        try {
            copied.get("North").add("X");
        } catch (UnsupportedOperationException e) {
            System.out.println("listImmutable=" + e.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```bash
javac --release 17 -encoding UTF-8 StructuredCollectorDemo.java
java StructuredCollectorDemo
```

Đầu ra được xác nhận bằng `javac --release 17` và `java`:

```text
regions={North=RegionSummary[paidCount=2, amountTotal=52], South=RegionSummary[paidCount=1, amountTotal=60], West=RegionSummary[paidCount=0, amountTotal=5]}
immutable=UnsupportedOperationException
overall=OverallSummary[saleCount=6, amountTotal=117]
unpaid=[B, D, F]
paid=[A, C, E]
copiedNorth=[A, C, F]
listImmutable=UnsupportedOperationException
```

Các thành phần quan trọng:

- `summaryForRegion()` tạo `RegionSummary` theo từng nhóm với **hai metric khác nhau**.
- `immutableByRegion()` tách bước phân nhóm và bước hoàn thiện output. `collectingAndThen(grouped, Collections::unmodifiableMap)` tạo Map không hỗ trợ sửa qua tham chiếu trả về.
- `overallCollector` tính hai chỉ số ở **cấp toàn bộ danh sách** rồi trả `OverallSummary`.
- `partitioningBy(Sale::paid, mapping(...))` tách dữ liệu theo hai trạng thái true/false mà không phải dùng Map lồng nhiều cấp.
- `collectingAndThen(toList(), List::copyOf)` tạo danh sách giá trị không sửa được **trong từng nhóm**; chỉ nên dùng khi dữ liệu tương thích với ràng buộc của `List.copyOf`.

**Ghi chú về “bất biến”:** `Collections.unmodifiableMap` là **view không sửa được** của Map nội bộ; nếu code còn giữ tham chiếu đến Map gốc và sửa nó, view sẽ phản ánh thay đổi. Trong chương trình này Map gốc được tạo trong collector rồi không lộ ra bên ngoài; các `RegionSummary` là record chứa primitive. `List.copyOf` tạo List không sửa được và từ chối phần tử `null`, nhưng nếu phần tử là object mutable, bản thân object vẫn có thể được sửa.

## 11. Khi nào nên dùng collectingAndThen()?

`Collectors.collectingAndThen(downstream, finisher)` lấy kết quả từ collector con rồi thực hiện một **bước hoàn thiện**. Nó giúp tránh trộn logic chuẩn hóa đầu ra với logic tích lũy từng phần tử:

```java
Collector<String, ?, List<String>> immutableNames =
        Collectors.collectingAndThen(
                Collectors.toList(),
                List::copyOf);
```

Đây là khai báo có thể đặt trong phương thức đã import `Collector`, `Collectors`, `List`. Kết quả là một List không cho phép thêm/xóa phần tử; nên dùng khi dữ liệu đầu vào **không chứa null**, vì `List.copyOf` ném `NullPointerException` nếu có phần tử null.

Trong báo cáo nhiều nhóm, dùng `collectingAndThen` để chuyển kết quả thành một **kiểu dữ liệu cuối** rõ ràng có thể tốt hơn việc nối thêm một tầng `Map` vô nghĩa.

Cân nhắc kỹ thứ tự kết hợp:

```text
groupingBy(region, collectingAndThen(toList(), finisher))
→ finisher chạy trên từng danh sách nhóm

collectingAndThen(groupingBy(region, toList()), finisher)
→ finisher chạy trên toàn bộ Map kết quả
```

Hai biểu thức chỉ là **mô tả hình thức**, không phải lệnh độc lập; `region` và `finisher` phải được khai báo bằng code cụ thể. Đây là khác biệt ngữ nghĩa quan trọng: vị trí của `collectingAndThen` xác định **phạm vi** của bước hoàn thiện.

Không dùng một finisher có side effects nghiệp vụ bắt buộc chỉ để né một bước xử lý tường minh; terminal collector có thể được thực thi trong môi trường song song, và các yêu cầu transaction/idempotency vẫn phải được thiết kế riêng.

## 12. partitioningBy() có thể rõ ràng hơn groupingBy(Boolean)

Nếu nhu cầu chỉ phân thành **hai nhóm dựa trên boolean**, `partitioningBy(predicate, downstream)` thường diễn đạt tốt hơn việc nhóm theo `true/false` bằng `groupingBy`:

```java
Map<Boolean, List<String>> groups = sales.stream().collect(
        Collectors.partitioningBy(
                Sale::paid,
                Collectors.mapping(Sale::product, Collectors.toList())));
```

Đây là một phần của chương trình ở mục 10. Dữ liệu tạo:

```text
false → [B, D, F]
true  → [A, C, E]
```

`partitioningBy` theo hợp đồng cung cấp **cả hai khóa** `true` và `false` trong kết quả, ngay cả khi một phía không có phần tử (đầu ra của downstream cho nhóm rỗng). Trong khi đó `groupingBy(Sale::paid,...)` trên dữ liệu chỉ toàn `true` sẽ không tự tạo khóa `false`.

Nếu API trả `Map<Boolean,List<...>>` đã đủ thể hiện cấu trúc, đừng biến nó thành `Map<Boolean, Map<String, List<...>>>` chỉ vì có thể. Hãy hỏi liệu caller thật sự cần **hai chiều chỉ mục** hay có thể trả một record như `PaidUnpaidSummary` dễ dùng hơn.

## 13. map(), filtering(), flatMapping(): tách việc biến đổi và gom nhóm

Ba công cụ này đóng các vai trò khác nhau:

- **`Stream.map` upstream** chuyển từng phần tử **trước khi** phân nhóm, có thể làm mất thông tin khóa nếu chuyển kiểu quá sớm.
- **`Collectors.mapping` downstream** giữ phép phân nhóm theo phần tử gốc rồi **chuyển loại phần tử trong mỗi nhóm**.
- **`Collectors.filtering` downstream** chọn các phần tử gửi vào collector con **sau khi đã nhận diện khóa nhóm**. Vì vậy có thể giữ nhóm kết quả rỗng.
- **`Collectors.flatMapping` downstream** chuyển mỗi phần tử thành một Stream nhỏ rồi trải phẳng vào collector con, hữu ích nếu một phần tử có **nhiều giá trị con** (ví dụ nhiều nhãn/tag).

Ví dụ cú pháp cho dữ liệu có list tag:

```java
record TaggedSale(String region, List<String> tags) {}
Collector<TaggedSale, ?, List<String>> allTags =
        Collectors.flatMapping(
                sale -> sale.tags().stream(),
                Collectors.toList());
```

Đây là đoạn **minh họa trong lớp** với `record TaggedSale`; nếu dùng độc lập cần import `List`, `Collector`, `Collectors`. Một `TaggedSale` chứa ba tag đóng góp **ba chuỗi** vào downstream; nếu chỉ dùng `mapping(TaggedSale::tags, toList())` thì kết quả có thể là `List<List<String>>`, thêm một tầng lồng không mong muốn.

Không nên dùng `flatMapping` khi chỉ có **một** giá trị cần ánh xạ: `mapping` rõ ràng hơn. Và dù dùng `flatMapping` hay `mapping`, việc phân nhóm/thu thập không thay thế bước xử lý side effects nghiệp vụ bắt buộc.

## 14. Vấn đề kiểu generic: đừng che ý nghĩa bằng cast

Các kiểu có thể trông dài:

```java
Collector<Sale, ?, Map<String, RegionSummary>> reportCollector =
        immutableByRegion();
```

Đây là lệnh trong lớp `StructuredCollectorDemo`. Kiểu này có thể giúp người đọc hiểu **đầu vào là Sale và đầu ra là Map region → RegionSummary**.

Một số kinh nghiệm:

1. **Tách bước có kiểu rõ:** `Collector<Sale, ?, Long> paidCount`, `Collector<Sale, ?, Integer> amountTotal` rồi dùng `teeing`.
2. **Ưu tiên method reference** cho getter/classifier rõ ràng: `Sale::region`, `Sale::paid`, `Sale::amount`.
3. **Tránh raw types** như `Collector raw` hoặc `(Map) result` để “vượt qua” lỗi generic; dễ tạo lỗi ở runtime.
4. **Dùng tên có ý nghĩa:** `summaryForRegion` nói được chính sách tốt hơn `collector3`.
5. Khi lambda quá phức tạp (kiểm tra null, định dạng, nhiều điều kiện), trích phương thức `normalizeRegion(Sale sale)`, `isBillable(Sale sale)` để có thể kiểm thử riêng.

Dấu `?` trong `Collector<T, ?, R>` không làm mất an toàn kiểu của dữ liệu vào/ra. Nó chỉ che chi tiết accumulator `A` khỏi mã gọi, phù hợp cho phương thức trả collector tùy biến.

## 15. Khi nào không nên tạo Map lồng?

Một Map lồng có ích nếu thực sự cần truy vấn kiểu **vùng → bộ phận → trạng thái → danh sách sự kiện**. Nhưng nếu phần gọi ngay sau đó chỉ tính số tổng và số hoàn thành, cấu trúc nhiều tầng có thể gây:

- Phải nhớ chính xác thứ tự khóa `region`, `department`, `status`.
- Nhiều chỗ xử lý `null` khi một khóa không tồn tại.
- Khó đảm bảo những nhóm không có phần tử vẫn xuất hiện.
- Khó xác định cấu trúc nào là **API công khai** và cấu trúc nào chỉ là chi tiết của collector.
- Cồng kềnh khi serialize thành JSON hoặc đưa vào DTO phản hồi.

Ba hướng thiết kế thay thế:

**Dùng record tổng hợp:** `Map<String,RegionSummary>` cho mỗi region một bộ metric cụ thể.

**Dùng danh sách hàng báo cáo:** `List<RegionReportRow>` với `record RegionReportRow(String region, long count, int total) {}` để dễ hiển thị/bộ lọc/sắp xếp. Đây là một khai báo record minh họa.

**Dùng nhóm một lần rồi xử lý nhóm theo phương thức rõ ràng:** `groupingBy(..., toList())` trả `Map<K,List<T>>`, sau đó từng nhóm được chuyển thành DTO. Cách này có thể tiêu tốn thêm bộ nhớ và cần định nghĩa rõ chi phí, nhưng đôi khi dễ hiểu hơn một cây collector khổng lồ.

Chọn mô hình dựa vào **kiểu truy vấn của caller**, không phải chỉ dựa vào cách viết ít dòng nhất.

## 16. Vòng lặp tường minh cũng là một giải pháp hợp lệ

Stream và Collectors hữu ích, nhưng không phải mọi bài toán đều cần được viết dưới dạng một expression. Nếu quy tắc cập nhật report cần kiểm tra từng bước, ghi trạng thái và xử lý lỗi, một vòng lặp tường minh có thể rõ hơn:

```java
Map<String, Long> counts = new TreeMap<>();
for (Sale sale : sales) {
    counts.merge(sale.region(), 1L, Long::sum);
}
```

Đây là các lệnh đặt trong phương thức có `Sale`, `sales`, `Map`, `TreeMap`. Chúng diễn đạt “đếm số Sale trong từng region” tương tự `groupingBy(Sale::region, TreeMap::new, counting())`.

Ưu điểm của vòng lặp:

- Rõ chính xác thời điểm cập nhật map.
- Dễ xử lý nhiều nhánh điều kiện và lỗi cụ thể.
- Dễ đặt breakpoint và kiểm tra trạng thái tích lũy.
- Không tạo nhiều collector lồng nhau.

Đánh đổi: nếu tích lũy nhiều số liệu, bạn phải tự đảm bảo accumulator đúng và có thể cần cấu trúc mutable phức tạp. Đối với Stream chạy song song, không dùng chung một `TreeMap` mutable từ nhiều thread một cách không đồng bộ; collector do framework quản lý giúp xử lý combiner theo hợp đồng của nó.

Một giải pháp có **ít dấu ngoặc hơn** không mặc định có độ phức tạp thuật toán tốt hơn; hãy cân nhắc bộ nhớ, số lượt duyệt, chi phí gom nhóm và khả năng mở rộng.

## 17. Đánh đổi hiệu năng: một lần collect hay nhiều lần?

Trong chương trình mục 6, `sales.stream()` được gọi nhiều lần để tính counts, paidCounts, paidProducts và sums **riêng rẽ**. Điều này hợp lệ vì `sales` là List có thể tạo stream mới; mỗi stream chỉ bị tiêu thụ một lần.

Nếu dữ liệu lớn hoặc nguồn là I/O một lượt, lặp lại nguồn nhiều lần có thể đắt hoặc không khả thi. Lúc đó:

- Dùng `teeing` hoặc collector tổng hợp để lấy nhiều metric trong **một terminal operation**.
- Dùng collector tùy chỉnh với accumulator chuyên biệt nếu số metric lớn và cần đảm bảo tính kết hợp.
- Materialize nguồn có kiểm soát nếu có đủ bộ nhớ và cần lặp lại để tạo báo cáo khác nhau.
- Chuyển các phép lọc/nhóm thích hợp sang hệ thống dữ liệu gốc khi xử lý ở ứng dụng quá tốn tài nguyên.

Tuy nhiên **một lần `collect`** không có nghĩa “ít phép toán nhất”; collector như `teeing` vẫn cấp phát và cập nhật hai downstream trên mỗi phần tử, còn `groupingBy` cần map và các bộ tích lũy cho từng nhóm.

Quy tắc thực dụng: bắt đầu từ **đúng nghiệp vụ và dễ đọc**, đo hiệu năng thật bằng benchmark/profiler khi cần, sau đó tối ưu **điểm nghẽn đã xác nhận**. Không làm một collector lồng sáu tầng chỉ vì phỏng đoán nó nhanh hơn ba phép thu thập rõ ràng.

## 18. Null, thứ tự và điều kiện biên

Collector kết hợp có thể thất bại hoặc cho kết quả khó hiểu khi không xét dữ liệu biên.

**Khóa null:** `Collectors.groupingBy` không chấp nhận classifier trả khóa `null` theo triển khai/hợp đồng sử dụng trong Java 17; thường phát sinh `NullPointerException`. Nên chuẩn hóa khóa về một đại diện phi null, lọc bản ghi không hợp lệ hoặc ném lỗi nghiệp vụ rõ ràng.

**Giá trị null:** `List.copyOf` không chấp nhận `null`; nếu downstream có thể sinh null, cần kiểm tra và quyết định chính sách trước khi đóng băng danh sách. `Collectors.mapping` không tự loại null.

**Thứ tự Map:** `TreeMap::new` sắp theo khóa; `LinkedHashMap::new` giữ insertion order; overload `groupingBy` không cấp mapFactory không hứa Map cụ thể hoặc iteration order.

**Thứ tự List trong nhóm:** với nguồn có encounter order và pipeline tuần tự như ví dụ, `mapping(..., toList())` cho List theo thứ tự các phần tử trong nhóm. Không tự giả định cách thu thập concurrent/unordered cho cùng thứ tự quan sát.

**Nhóm rỗng:** `groupingBy(region, filtering(..., toList()))` có thể cho `region=[]` nếu region có bản ghi nhưng không có bản ghi đạt predicate; nếu nguồn hoàn toàn không có region đó thì `groupingBy` không tự tạo key.

**Empty stream:** `groupingBy` trên nguồn rỗng trả Map rỗng; `partitioningBy` trả hai nhánh true/false; `teeing(counting(), summingInt(...), merger)` trên nguồn rỗng có thể tạo báo cáo `(0,0)` theo các downstream được chọn.

Những ràng buộc này **không được giải quyết bằng cách lồng thêm collector**. Hãy ghi rõ chúng trong API và có bài test riêng.

## 19. Parallel collector và tính an toàn

Khi dùng `parallelStream()`, collector có thể tạo các **accumulator** tách biệt rồi kết hợp lại. Điều đó khiến quy tắc dưới đây quan trọng:

1. Các hàm `classifier`, `predicate`, `mapper` nên **stateless** và **non-interfering** — không sửa nguồn hoặc shared state ngoài.
2. Một collector tùy chỉnh phải có `combiner` đúng hợp đồng, không chỉ hoạt động khi chạy tuần tự.
3. Merge function và cách tổng hợp nên có đặc tính phù hợp với cách nhóm lại, đặc biệt khi xử lý thứ tự và số thực.
4. Không mặc nhiên rằng `groupingBy(...)` là **concurrent collector** chỉ vì stream chạy parallel.
5. `groupingByConcurrent` có ngữ nghĩa concurrent/unordered khác; không thay thế máy móc nếu cần thứ tự rõ ràng.
6. Đừng ghi DB, gửi email hoặc thực hiện thao tác nghiệp vụ bắt buộc trong `mapping`/`filtering`/finisher để “tiện một lần duyệt”; hãy có bước nghiệp vụ rõ và kiểm soát lỗi.
7. Nếu kết quả phải tái lập, chọn dữ liệu/collector/định nghĩa thứ tự và phép gộp có kết quả ổn định, kiểm thử dưới đúng chế độ chạy.

Những nguyên tắc này có tính ưu tiên cao hơn việc giảm số dòng: mã một dòng nhưng có data race hoặc merge không ổn định không phải mã tốt.

## 20. Quy trình refactor collector lồng sâu

Khi gặp một biểu thức khó đọc, có thể refactor theo thứ tự sau:

**Bước 1 — Viết kiểu đầu ra mong muốn trước.** Ví dụ `Map<String,RegionSummary>`, không phải “một Map chứa nhiều thứ”.

**Bước 2 — Đặt tên các metric.** `paidCount`, `amountTotal`, `productNames`; xác nhận chính xác mỗi metric đếm/lọc đối tượng gì.

**Bước 3 — Xác định phạm vi của phép lọc.** Lọc nguồn toàn cục hay lọc riêng downstream để vẫn giữ khóa nhóm rỗng?

**Bước 4 — Chọn collector đúng nhiệm vụ.** `groupingBy` cho phân nhóm, `mapping` cho biến đổi, `filtering` cho chọn, `teeing` cho hai chỉ số, `collectingAndThen` cho kết quả sau cùng.

**Bước 5 — Tách logic có tên.** Đưa tổ hợp downstream vào `static Collector<T, ?, R> readableName()` hoặc biến cục bộ có kiểu tường minh, tránh raw types và cast.

**Bước 6 — Chọn kiểu kết quả dễ dùng.** Nếu `Map<K,Map<K2,R>>` không phản ánh API cần thiết, dùng record DTO hoặc danh sách hàng báo cáo.

**Bước 7 — Kiểm thử trường hợp biên.** Nhóm chỉ có bản ghi không đạt điều kiện, nguồn rỗng, khóa null, thứ tự, duplicate keys, parallel nếu có.

**Bước 8 — Đo hiệu năng nếu cần.** Sau khi có unit test và contract rõ ràng mới tối ưu số lần duyệt/combiner và phân bổ bộ nhớ.

Ví dụ nhỏ, ngắn và giàu ý nghĩa **không cần refactor chỉ để theo quy trình**. Mục tiêu là làm rõ cấu trúc, không tạo hàng chục phương thức nhỏ vô ích.

## 21. Lỗi phổ biến và cách tránh

| Lỗi thiết kế | Vì sao gây hại | Cách cải thiện |
| --- | --- | --- |
| Lồng bốn–năm collector với lambda phức tạp không tên | Khó suy luận thứ tự xử lý và kiểu kết quả | Trích collector con thành biến/phương thức tên nghiệp vụ |
| Dùng `Stream.filter` thay `Collectors.filtering` vô điều kiện | Có thể làm biến mất nhóm không có phần tử đạt điều kiện | Chọn vị trí lọc theo yêu cầu giữ nhóm |
| Mọi dữ liệu đều trả `Map<K,Map<K2,List<V>>>` | Caller phụ thuộc cấu trúc sâu, xử lý key thiếu rườm rà | Record kết quả hoặc mô hình báo cáo phẳng khi phù hợp |
| Dùng `teeing` nhiều tầng để tính mọi chỉ tiêu | Khó đọc và bảo trì như biểu thức ban đầu | Collector tùy chỉnh hoặc bước tính tường minh |
| Không phân biệt `counting` và `filtering(..., counting())` | Một bên đếm tất cả, bên kia chỉ đếm thỏa điều kiện | Đặt tên collector theo điều kiện thực |
| `collectingAndThen(toList(),List::copyOf)` trên list chứa null | `List.copyOf` ném NullPointerException | Xử lý null trước và công bố policy |
| Cho rằng `Collections.unmodifiableMap` là deep copy | Chỉ trả view và không đóng băng object value mutable | Dùng snapshot/defensive copy phù hợp |
| Tin `HashMap`/groupingBy mặc định bảo đảm iteration order | API không hứa thứ tự đó | Chọn mapFactory `TreeMap::new`/`LinkedHashMap::new` |
| Dùng raw `Collector` để sửa lỗi generics | Mất an toàn kiểu và che vấn đề cấu trúc | Khai báo `Collector<T, ?, R>` |
| Dùng `parallel` vì nghĩ collector phức tạp sẽ tự nhanh hơn | Overhead combiner và order constraints có thể tốn hơn | Benchmark và kiểm thử semantic |
| Nhét side effects bắt buộc vào mapper/filter/finisher | Quy trình nghiệp vụ khó xác nhận/truy vết | Tách hành động ra bước nghiệp vụ kiểm soát được |
| Dùng một Stream cho nhiều terminal collect | Stream chỉ tiêu thụ một lần | Mỗi lượt tạo stream mới từ nguồn có thể duyệt lại |

## 22. Bài tập thực hành có đáp án

**Bài 1 — Tên collector.** Có `List<Sale>`, cần `Map<String,Long>` đếm Sale đã thanh toán theo region, **giữ cả region không có Sale đã thanh toán**. Viết collector dễ đọc.

Gợi ý đáp án trong ngữ cảnh lớp chứa `Sale` và import `Collectors`, `Map`, `TreeMap`:

```java
Collector<Sale, ?, Long> paidCount =
        Collectors.filtering(Sale::paid, Collectors.counting());
Map<String, Long> result = sales.stream().collect(
        Collectors.groupingBy(Sale::region, TreeMap::new, paidCount));
```

Nếu region West chỉ có Sale chưa thanh toán, nó vẫn xuất hiện với `0`.

**Bài 2 — Upstream hay downstream?** Với nguồn có North (đã trả) và West (chưa trả), `stream().filter(Sale::paid).collect(groupingBy(...))` có tạo nhóm West không?

Đáp án: **Không**. Bản ghi West bị loại trước khi classifier của `groupingBy` nhìn thấy. Nếu muốn `West=[]` hoặc `West=0`, dùng `Collectors.filtering` downstream.

**Bài 3 — Kiểu trả.** Nếu dùng `groupingBy(Sale::region, TreeMap::new, mapping(Sale::product,toList()))`, kiểu kết quả là gì?

Đáp án: `Map<String,List<String>>`. `groupingBy` tạo khóa `String`; `mapping` biến Sale thành `String`; `toList` thu `List<String>`.

**Bài 4 — teeing.** Một region cần `paidCount` và `amountTotal`. Dùng kiểu trả nào giúp API rõ hơn `Map<String,Object>`?

Đáp án: `record RegionSummary(long paidCount,int amountTotal) {}`; dùng `teeing(filtering(paid,counting()),summingInt(amount),RegionSummary::new)` thành collector con của `groupingBy`.

**Bài 5 — Bất biến.** `collectingAndThen(toList(), List::copyOf)` có chấp nhận phần tử null không? Nó có tự làm object bên trong List trở thành immutable sâu không?

Đáp án: **Không** với cả hai. `List.copyOf` từ chối null, còn phần tử mutable vẫn có thể bị thay đổi thông qua tham chiếu khác.

**Bài 6 — Hai trạng thái.** Muốn `Map<Boolean,List<String>>` theo trạng thái `paid`, có API nào rõ hơn `groupingBy(sale -> sale.paid(), mapping(...))`?

Đáp án: `partitioningBy(Sale::paid, mapping(Sale::product, toList()))`. Kết quả chứa cả hai khóa true/false, kể cả khi một phía rỗng.

**Bài 7 — Phạm vi finisher.** Phân biệt `groupingBy(region, collectingAndThen(toList(), f))` và `collectingAndThen(groupingBy(region,toList()), f)`.

Đáp án: dạng đầu chạy `f` **trên List mỗi nhóm**, còn dạng sau chạy `f` **trên toàn bộ Map nhóm**; kiểu đầu vào của `f` cũng khác. Hai cách không hoán đổi tùy ý.

**Bài 8 — Bài toán nhiều chỉ số.** Nếu cần mười metric theo mỗi region, có nên xếp chín tầng `teeing` không?

Đáp án: thường **không nên**. Hãy xem xét accumulator/report type rõ ràng, collector tùy chỉnh, hoặc chia thành các bước đơn giản. Chọn dựa trên tính dễ đọc, số lượt duyệt được phép và chi phí tính toán thực tế.

## 23. Checklist code review

- [ ] Nhìn vào kiểu kết quả có biết ngay caller nhận gì không?
- [ ] Mỗi collector con có một nhiệm vụ rõ và có tên khi cần?
- [ ] Vị trí `filter`/`filtering` đúng ngữ nghĩa giữ nhóm rỗng?
- [ ] `mapping`/`flatMapping` đúng số lượng giá trị đầu ra mỗi phần tử?
- [ ] `teeing` chỉ kết hợp những chỉ tiêu cần đi cùng nhau?
- [ ] `collectingAndThen` áp dụng ở đúng **phạm vi** (mỗi nhóm hay cả kết quả)?
- [ ] Kiểu Map được chọn rõ nếu cần thứ tự hoặc tính chất đặc biệt?
- [ ] Dữ liệu null, nguồn rỗng và nhóm không có phần tử đạt điều kiện đã được kiểm thử?
- [ ] Không có side effects nghiệp vụ bắt buộc trong collector con?
- [ ] Nếu nguồn lớn/song song, đã xem xét số lượt duyệt, combiner và tính an toàn?

## 24. Kết luận

- **Kết hợp collector là công cụ mạnh**, nhưng sức mạnh không nằm ở số lượng hàm có thể lồng trong một biểu thức.
- Một collector dễ đọc trả lời được: **phân nhóm theo gì, chọn phần tử nào, biến đổi ra sao, tổng hợp gì và kiểu kết quả là gì**.
- **Đặt tên downstream collector** và **trả record/report type** giúp giảm gánh nặng hiểu `Map` nhiều tầng, cải thiện khả năng kiểm thử.
- `filtering` **ở downstream** khác `Stream.filter` trước `groupingBy`; nó có thể giữ key nhóm với kết quả rỗng hoặc 0.
- `teeing` phù hợp cho hai metric, `collectingAndThen` cho bước hoàn thiện, `partitioningBy` cho phân nhóm boolean, `mapping`/`flatMapping` cho chuyển đổi giá trị.
- Khi quá nhiều cấp lồng, **vòng lặp hoặc collector tùy chỉnh có accumulator riêng** có thể rõ hơn; không ép mọi nghiệp vụ thành một expression duy nhất.
- Thiết kế theo **độ rõ ràng, đúng kiểu, hợp đồng ngữ nghĩa và phép đo hiệu năng**, không chỉ theo số dòng.

Tài liệu chính thống: [Java SE 17 — Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html), [Collector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collector.html), [Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html), [Collections.unmodifiableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)).
