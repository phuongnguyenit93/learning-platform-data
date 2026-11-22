# Phân nhóm nhiều cấp với khóa lồng nhau

Trong báo cáo kinh doanh, một nhóm dữ liệu thường chưa đủ để trả lời câu hỏi. Chẳng hạn, thống kê doanh thu **theo khu vực** mới cho biết tổng của miền Bắc, miền Trung và miền Nam; người quản lý còn muốn biết **trong từng khu vực, mỗi danh mục sản phẩm đóng góp bao nhiêu**. Khi ấy, ta cần **phân nhóm nhiều cấp** (*multi-level grouping*).

Trong **Java Stream API**, công cụ quen thuộc cho bài toán này là `Collectors.groupingBy` kết hợp với một **downstream collector** khác. Khi đặt `groupingBy` bên trong `groupingBy`, kết quả thường có dạng **`Map<K1, Map<K2, ...>>`**. Mỗi cấp bản đồ tương ứng với một chiều phân tích dữ liệu.

Bài này thuộc chương **Phân nhóm và phân hoạch** của module **JAVA_STREAM_API**. Nội dung tập trung vào cách xây bản đồ nhóm lồng nhau, tính số lượng và tổng tiền trong từng nhóm, áp dụng `mapping`/`filtering`, thiết kế khóa, truy xuất dữ liệu an toàn và kiểm soát thứ tự, tài nguyên, trạng thái khi dùng Stream song song. Đây cũng là nền tảng để tìm hiểu collector tùy chỉnh, `Spliterator` và Stream Gatherers.

## 1. Từ nhóm một cấp đến nhóm nhiều cấp

Giả sử mỗi giao dịch bán hàng có **khu vực**, **danh mục**, **giá trị** và **trạng thái thanh toán**.

Nếu chỉ nhóm theo khu vực:

~~~java
Map<String, List<Sale>> byRegion = sales.stream()
    .collect(Collectors.groupingBy(Sale::region));
~~~

Kết quả có thể hình dung:

~~~text
"Bắc"   -> [các giao dịch miền Bắc]
"Trung" -> [các giao dịch miền Trung]
"Nam"   -> [các giao dịch miền Nam]
~~~

Nhưng nếu muốn xem cả **khu vực → danh mục**, ta đặt một collector `groupingBy` làm **downstream** của collector bên ngoài:

~~~java
Map<String, Map<String, List<Sale>>> byRegionAndCategory =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        Collectors.groupingBy(Sale::category)
    ));
~~~

Cấu trúc kết quả:

~~~text
"Bắc" ->
    "Sách" -> [các giao dịch Sách ở Bắc]
    "Bút"  -> [các giao dịch Bút ở Bắc]

"Nam" ->
    "Sách" -> [các giao dịch Sách ở Nam]
    "Bút"  -> [các giao dịch Bút ở Nam]
~~~

Ở cấp thứ nhất, `Sale::region` là **hàm phân loại bên ngoài**. Với từng nhóm khu vực, `Sale::category` phân loại **tiếp** phần tử của nhóm đó. Lá cuối cùng mặc định là danh sách `List<Sale>`.

**Điểm mấu chốt:** collector lồng nhau không tạo nhiều lượt duyệt toàn bộ dữ liệu theo kiểu “mỗi khu vực lại lọc Stream từ đầu”. Nó mô tả một quá trình thu thập, trong đó các phần tử được phân phối đến bộ chứa phù hợp theo khóa của từng cấp.

## 2. Ví dụ đầy đủ: nhóm giao dịch theo khu vực và danh mục

Ví dụ sau chạy trên **JDK 17 trở lên** vì dùng `record` và `List.of`. Các API `Stream` và `Collectors.groupingBy` đã có từ Java 8.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class NestedGroupingDemo {
    record Sale(
        String id,
        String region,
        String category,
        long amountVnd,
        boolean paid
    ) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
            new Sale("S01", "Bắc",   "Sách", 100_000L, true),
            new Sale("S02", "Nam",   "Bút",   40_000L, true),
            new Sale("S03", "Bắc",   "Sách", 150_000L, false),
            new Sale("S04", "Bắc",   "Bút",   30_000L, true),
            new Sale("S05", "Nam",   "Sách", 200_000L, true),
            new Sale("S06", "Nam",   "Bút",   70_000L, false),
            new Sale("S07", "Trung", "Sách",  90_000L, true),
            new Sale("S08", "Trung", "Bút",   20_000L, false)
        );

        Map<String, Map<String, List<Sale>>> grouped =
            sales.stream().collect(Collectors.groupingBy(
                Sale::region,
                Collectors.groupingBy(Sale::category)
            ));

        List<Sale> northBooks = grouped.get("Bắc").get("Sách");

        System.out.println(northBooks.stream()
            .map(Sale::id)
            .collect(Collectors.toList()));
        // [S01, S03]

        System.out.println(grouped.get("Nam").get("Bút").size());
        // 2: S02 và S06
    }
}
~~~

Đoạn chương trình tạo một cấu trúc có hai lớp `Map`:

- **Map ngoài:** khóa `String` là khu vực.
- **Map trong:** khóa `String` là danh mục nằm trong khu vực đó.
- **Giá trị ở lá:** `List<Sale>` chứa các giao dịch của cặp khóa.

Kiểu `Map<String, Map<String, List<Sale>>>` có thể dài, nhưng nó mô tả chính xác hình dạng dữ liệu. Hãy đọc từ **ngoài vào trong**: “bản đồ khu vực, mỗi khu vực có một bản đồ danh mục, mỗi danh mục chứa một danh sách giao dịch”.

~~~mermaid
flowchart TD
    A["Stream<Sale>"] --> B["groupingBy(region)"]
    B --> C["Bắc"]
    B --> D["Nam"]
    B --> E["Trung"]
    C --> F["groupingBy(category)"]
    D --> G["groupingBy(category)"]
    E --> H["groupingBy(category)"]
    F --> I["Sách → [S01, S03]"]
    F --> J["Bút → [S04]"]
    G --> K["Bút → [S02, S06]"]
    G --> L["Sách → [S05]"]
    H --> M["Sách → [S07]"]
    H --> N["Bút → [S08]"]
~~~

Hình chỉ minh họa các khóa có mặt, **không biểu thị thứ tự duyệt của `HashMap`**. Nếu đầu ra cần thứ tự khóa xác định, phải chọn `mapFactory` hoặc sắp xếp khi hiển thị.

## 3. Hiểu overload groupingBy có downstream

Hai overload thường gặp là:

~~~java
Collectors.groupingBy(classifier)

Collectors.groupingBy(classifier, downstream)
~~~

Về ý nghĩa kiểu:

~~~java
<T, K> Collector<T, ?, Map<K, List<T>>>
groupingBy(Function<? super T, ? extends K> classifier)

<T, K, A, D> Collector<T, ?, Map<K, D>>
groupingBy(
    Function<? super T, ? extends K> classifier,
    Collector<? super T, A, D> downstream
)
~~~

Đây là chữ ký **rút gọn để học**, không phải toàn bộ mã nguồn của `Collectors`.

`classifier` nhận phần tử đầu vào `T` và trả về **khóa nhóm** `K`. `downstream` quy định cách xử lý **những phần tử trong từng nhóm** để tạo giá trị cuối `D`.

Với hai cấp nhóm:

~~~java
Collectors.groupingBy(
    Sale::region,                    // cấp 1: K1
    Collectors.groupingBy(           // cấp 2
        Sale::category               // K2; mặc định downstream là toList()
    )
)
~~~

Ta suy ra:

~~~text
T = Sale
K1 = String (region)
K2 = String (category)
D2 = List<Sale>
D1 = Map<String, List<Sale>>
Kết quả = Map<String, Map<String, List<Sale>>>
~~~

**Nguyên tắc:** khi thay downstream cuối bằng `counting()` hoặc `summingLong(...)`, chỉ **kiểu giá trị lá** thay đổi; các khóa lồng nhau vẫn theo cùng logic phân nhóm.

## 4. Nhóm hai cấp rồi đếm số lượng trong từng nhóm

Nếu mục đích chỉ là đếm, không cần lưu danh sách giao dịch tại mỗi lá. Hãy dùng `Collectors.counting()`:

~~~java
Map<String, Map<String, Long>> countByRegionAndCategory =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        Collectors.groupingBy(
            Sale::category,
            Collectors.counting()
        )
    ));
~~~

Biến `sales` và kiểu `Sale` ở đây là dữ liệu trong ví dụ đầy đủ mục 2.

Kết quả theo dữ liệu mẫu:

| Khu vực | Danh mục | Số giao dịch |
|---|---|---:|
| Bắc | Sách | 2 |
| Bắc | Bút | 1 |
| Nam | Bút | 2 |
| Nam | Sách | 1 |
| Trung | Sách | 1 |
| Trung | Bút | 1 |

`counting()` trả về giá trị `Long`, không phải `Integer`, vì số lượng phần tử có thể vượt phạm vi `int`.

Ví dụ truy xuất:

~~~java
long northBookCount =
    countByRegionAndCategory.get("Bắc").get("Sách");

System.out.println(northBookCount); // 2
~~~

Ở đây khóa có mặt chắc chắn do ta biết dữ liệu mẫu. Với dữ liệu đầu vào tùy ý, `get("Bắc")` hoặc `get("Sách")` có thể trả `null`; mục 10 trình bày cách lấy kết quả an toàn.

### 4.1. Vì sao counting tiết kiệm bộ nhớ hơn toList?

`groupingBy(region, groupingBy(category))` giữ **mọi đối tượng `Sale`** trong các danh sách. `groupingBy(region, groupingBy(category, counting()))` chỉ giữ số đếm tại mỗi cặp khóa.

Với dữ liệu lớn và chỉ cần thống kê, cách thứ hai thường có nhu cầu bộ nhớ **gần với số lượng nhóm** hơn, thay vì số lượng giao dịch. Không nên lưu hàng triệu bản ghi vào List nếu báo cáo chỉ cần `count`.

## 5. Nhóm hai cấp rồi tính tổng bằng summingLong

Yêu cầu kinh doanh phổ biến hơn là **tổng doanh thu theo khu vực và danh mục**. Ta chỉ tính các giao dịch `paid = true`:

~~~java
Map<String, Map<String, Long>> revenueByRegionAndCategory =
    sales.stream()
        .filter(Sale::paid)
        .collect(Collectors.groupingBy(
            Sale::region,
            Collectors.groupingBy(
                Sale::category,
                Collectors.summingLong(Sale::amountVnd)
            )
        ));
~~~

Bản đồ doanh thu từ dữ liệu mẫu:

| Khu vực | Danh mục | Tổng tiền đã thanh toán |
|---|---|---:|
| Bắc | Sách | 100.000 |
| Bắc | Bút | 30.000 |
| Nam | Bút | 40.000 |
| Nam | Sách | 200.000 |
| Trung | Sách | 90.000 |

Cặp **(Trung, Bút)** không xuất hiện vì giao dịch `S08` chưa thanh toán và đã bị `filter` loại trước khi nhóm.

Các thành phần của pipeline:

1. `filter(Sale::paid)` giữ các giao dịch đã thanh toán.
2. `groupingBy(Sale::region, ...)` chọn khu vực.
3. `groupingBy(Sale::category, ...)` chọn danh mục trong khu vực đó.
4. `summingLong(Sale::amountVnd)` lấy `long` ở mỗi giao dịch và cộng dồn trong từng nhóm.

`summingLong` là **downstream collector**, không phải lời gọi `mapToLong(...).sum()` sau khi có Map. Nó thực hiện tổng hợp **ngay trong quá trình thu thập theo nhóm**.

**Lưu ý tràn số:** `Long` giúp biểu diễn tổng lớn hơn `int` nhưng `long` vẫn hữu hạn. Nếu tổng tiền có thể vượt `Long.MAX_VALUE`, ứng dụng phải dùng cách biểu diễn và phép cộng phù hợp (chẳng hạn `BigDecimal` hoặc giới hạn nghiệp vụ được kiểm tra).

### 5.1. Cùng dữ liệu nhưng thống kê hai cấp khác nhau

| Downstream cuối | Kiểu lá | Khi cần dùng |
|---|---|---|
| Mặc định `toList()` | `List<Sale>` | Xem chi tiết từng bản ghi |
| `counting()` | `Long` | Đếm giao dịch |
| `summingLong(Sale::amountVnd)` | `Long` | Tổng tiền |
| `averagingLong(Sale::amountVnd)` | `Double` | Giá trị trung bình |
| `summarizingLong(Sale::amountVnd)` | `LongSummaryStatistics` | Count, sum, min, max, average |
| `maxBy(Comparator.comparingLong(...))` | `Optional<Sale>` | Tìm giao dịch có giá trị lớn nhất |

**Tính chất kiểu:** `Map<String, Map<String, Long>>` là **kết quả cấu trúc**. `Map` nào được tạo, có chỉnh sửa được hay thứ tự khóa thế nào phải xem hợp đồng collector và tham số map factory; không nên dựa vào một dạng Map cụ thể khi chưa yêu cầu.

## 6. Nhóm ba cấp: thêm trạng thái thanh toán

Có thể lồng tiếp một `groupingBy` khác nếu báo cáo cần chiều thứ ba:

~~~java
Map<String, Map<String, Map<Boolean, List<Sale>>>> tripleGroups =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        Collectors.groupingBy(
            Sale::category,
            Collectors.groupingBy(Sale::paid)
        )
    ));
~~~

Ví dụ:

~~~text
"Bắc" ->
  "Sách" ->
      true  -> [S01]
      false -> [S03]
  "Bút" ->
      true  -> [S04]

"Nam" ->
  "Bút" ->
      true  -> [S02]
      false -> [S06]
  "Sách" ->
      true  -> [S05]
~~~

Điểm đặc biệt: `groupingBy(Sale::paid)` chỉ tạo khóa Boolean **nếu có giao dịch mang giá trị đó trong nhóm**. Vì thế `tripleGroups.get("Bắc").get("Bút").get(false)` có thể là `null` thay vì một danh sách rỗng.

Đừng viết mã phụ thuộc vào việc mọi nhánh đều có tất cả các giá trị Boolean. Với nhu cầu **luôn có đúng hai nhánh `true`/`false`**, có một collector thích hợp hơn: `partitioningBy`.

### 6.1. partitioningBy cho cấp cuối có hai trạng thái

~~~java
Map<String, Map<String, Map<Boolean, List<Sale>>>> partitioned =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        Collectors.groupingBy(
            Sale::category,
            Collectors.partitioningBy(Sale::paid)
        )
    ));

System.out.println(
    partitioned.get("Bắc").get("Bút").get(false).isEmpty()
); // true
~~~

Với một nhóm **đã tồn tại** (ở đây Bắc → Bút), `partitioningBy` tạo Map có hai khóa `true` và `false`, kể cả một phía không có phần tử. Tuy nhiên, các cặp khu vực/danh mục **không hề xuất hiện trong nguồn** vẫn không được `groupingBy` tạo ra.

| Cơ chế ở cấp Boolean | Có đảm bảo khóa true và false cho mỗi nhóm hiện có? | Ứng dụng |
|---|---|---|
| `groupingBy(Sale::paid)` | Không | Chỉ quan tâm các trạng thái có giao dịch |
| `partitioningBy(Sale::paid)` | Có | Muốn có hai nhánh cố định, kể cả nhánh rỗng |

`partitioningBy` còn hỗ trợ downstream riêng, ví dụ `partitioningBy(Sale::paid, counting())` để đếm hai trạng thái trong từng nhóm.

## 7. mapping: biến phần tử trước khi lưu vào từng nhóm

Đôi khi cần các mã giao dịch, chứ không cần toàn bộ đối tượng `Sale`. Nếu `map(Sale::id)` **trước** `groupingBy`, ta không còn thông tin khu vực và danh mục để phân nhóm, trừ khi đã tạo kiểu dữ liệu trung gian khác.

Cách phù hợp là giữ `Sale` đến khi đã xác định khóa nhóm, rồi dùng **`Collectors.mapping` ở downstream**:

~~~java
Map<String, Map<String, List<String>>> idsByRegionAndCategory =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        Collectors.groupingBy(
            Sale::category,
            Collectors.mapping(
                Sale::id,
                Collectors.toList()
            )
        )
    ));
~~~

Kết quả đối với Bắc → Sách:

~~~java
System.out.println(
    idsByRegionAndCategory.get("Bắc").get("Sách")
); // [S01, S03]
~~~

`mapping(mapper, downstream)` có nghĩa: **tại từng nhóm**, ánh xạ phần tử thành kiểu mới rồi chuyển vào collector phía sau. Phương thức `mapping` là **collector**, khác với `Stream.map` là **phép toán trung gian**.

Đây là một mô hình phổ biến trong các báo cáo nhiều chiều: nhóm bằng đối tượng nguồn, nhưng chỉ xuất các trường cần thiết ở cuối.

### 7.1. Chọn Set thay vì List ở lá

Nếu mã giao dịch có thể bị lặp và cần một tập mã duy nhất:

~~~java
Map<String, Map<String, Set<String>>> uniqueIds =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        Collectors.groupingBy(
            Sale::category,
            Collectors.mapping(
                Sale::id,
                Collectors.toSet()
            )
        )
    ));
~~~

Trong ví dụ này cần `import java.util.Set;` ngoài các import tương ứng. `Collectors.toSet()` không bảo đảm thứ tự duyệt hay loại `Set` cụ thể. Nếu cần một `TreeSet` theo thứ tự tăng dần, dùng `Collectors.toCollection(TreeSet::new)` và bảo đảm các phần tử có thứ tự tự nhiên hoặc có comparator phù hợp.

## 8. filtering downstream khác filter trước groupingBy

Đây là khác biệt **ngữ nghĩa** rất quan trọng đối với báo cáo có số lượng bằng 0.

**Cách A — lọc toàn bộ Stream trước khi nhóm:**

~~~java
Map<String, Map<String, Long>> paidOnly =
    sales.stream()
        .filter(Sale::paid)
        .collect(Collectors.groupingBy(
            Sale::region,
            Collectors.groupingBy(
                Sale::category,
                Collectors.counting()
            )
        ));
~~~

Vì giao dịch `S08` thuộc **Trung → Bút** là chưa thanh toán và không có bản ghi khác trong cặp khóa đó, Map **không có nhánh Trung → Bút**.

**Cách B — giữ toàn bộ nhóm, chỉ lọc ở lá bằng `Collectors.filtering` (Java 9+):**

~~~java
Map<String, Map<String, Long>> paidCountIncludingZero =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        Collectors.groupingBy(
            Sale::category,
            Collectors.filtering(
                Sale::paid,
                Collectors.counting()
            )
        )
    ));

System.out.println(
    paidCountIncludingZero.get("Trung").get("Bút")
); // 0
~~~

Vì `groupingBy` đã xác định nhóm **Trung → Bút** trước khi downstream filtering, nhóm vẫn được tạo, còn số đếm của giao dịch đạt điều kiện trong nhóm là `0L`.

Tương tự, có thể dùng:

~~~java
Collectors.filtering(Sale::paid, Collectors.toList())
~~~

để giữ **danh sách rỗng** ở một nhóm có dữ liệu đầu vào nhưng không có phần tử thỏa điều kiện.

| Yêu cầu | Nên chọn |
|---|---|
| Báo cáo chỉ hiển thị nhóm **có giao dịch thỏa điều kiện** | `stream.filter(...).collect(groupingBy(...))` |
| Báo cáo cần giữ nhóm đã xuất hiện, kể cả kết quả con bằng 0 | `groupingBy(..., filtering(..., counting()))` |
| Báo cáo cần **mọi tổ hợp khóa có thể có**, kể cả chưa từng xuất hiện | Ngoài grouping, cần **khởi tạo/điền bổ sung các khóa thiếu** từ danh mục nghiệp vụ |

`Collectors.filtering` không tự tạo mọi cặp khu vực/danh mục không có trong dữ liệu nguồn. Nó chỉ giúp giữ nhóm mà collector ngoài đã gặp.

## 9. Nhiều thống kê tại mỗi lá bằng summarizingLong

Đôi khi cần cả `count`, `sum`, `min`, `max` và `average`. Thay vì tạo năm Map riêng (tương đương năm lượt thu thập), dùng `Collectors.summarizingLong`:

~~~java
import java.util.LongSummaryStatistics;

Map<String, Map<String, LongSummaryStatistics>> statistics =
    sales.stream()
        .filter(Sale::paid)
        .collect(Collectors.groupingBy(
            Sale::region,
            Collectors.groupingBy(
                Sale::category,
                Collectors.summarizingLong(Sale::amountVnd)
            )
        ));

LongSummaryStatistics northBooks =
    statistics.get("Bắc").get("Sách");

System.out.println(northBooks.getCount());   // 1
System.out.println(northBooks.getSum());     // 100000
System.out.println(northBooks.getMin());     // 100000
System.out.println(northBooks.getMax());     // 100000
System.out.println(northBooks.getAverage()); // 100000.0
~~~

`LongSummaryStatistics` là một bộ chứa thống kê có trạng thái. Những giá trị như count và sum được tính trong quá trình collect, chứ không cần lưu `List<Sale>` của từng nhóm.

**Trường hợp nhóm rỗng:** một `LongSummaryStatistics` mới có count bằng 0, sum bằng 0, nhưng giá trị min/max của đối tượng chưa có dữ liệu mang giá trị sentinel tương ứng (`Long.MAX_VALUE`/`Long.MIN_VALUE`). Không nên báo cáo những sentinel đó như mức giá thật; hãy kiểm tra `getCount()` trước khi diễn giải min/max.

Nếu số giao dịch/giá trị có thể cực lớn, chú ý tràn số `long` trong tổng. Ngoài ra, trung bình trả `double` nên có giới hạn độ chính xác của số thực.

## 10. Truy xuất Map lồng nhau an toàn

Ví dụ dữ liệu mẫu có `Bắc → Sách`, nên ta có thể gọi trực tiếp `grouped.get("Bắc").get("Sách")`. Nhưng với đầu vào không biết trước, một khóa có thể không xuất hiện và `Map.get` sẽ trả `null`.

Không nên viết:

~~~java
// Có thể ném NullPointerException nếu không có khu vực "Tây".
// long count = countByRegionAndCategory.get("Tây").get("Sách");
~~~

Có thể lấy giá trị một cách rõ ràng qua Map mặc định:

~~~java
Map<String, Long> categories =
    countByRegionAndCategory.getOrDefault(
        "Tây",
        java.util.Collections.emptyMap()
    );

long count = categories.getOrDefault("Sách", 0L);

System.out.println(count); // 0
~~~

Phân biệt **không tồn tại** với **giá trị đúng bằng 0**:

- Nếu nghiệp vụ quy ước nhóm vắng mặt được hiển thị `0`, dùng `getOrDefault` là hợp lý.
- Nếu cần phân biệt nhóm chưa bao giờ xuất hiện với nhóm đã xuất hiện nhưng không có giao dịch phù hợp, dùng `containsKey` hoặc `Optional`/kiểu kết quả nghiệp vụ phù hợp.

Ví dụ kiểm tra tồn tại của cặp khóa:

~~~java
Map<String, Long> categoriesOrNull =
    countByRegionAndCategory.get("Trung");

boolean hasPenGroup = categoriesOrNull != null
    && categoriesOrNull.containsKey("Bút");

System.out.println(hasPenGroup); // true với dữ liệu gốc
~~~

Khi nhiều nơi phải truy vấn Map lồng nhau, nên đóng gói việc truy xuất vào một phương thức nhỏ có tên rõ nghĩa thay vì lặp lại chuỗi `get` dễ gây lỗi.

## 11. Lựa chọn thứ tự khóa bằng mapFactory

Overload `groupingBy(classifier, downstream)` **không bảo đảm** kiểu Map hay thứ tự duyệt của các khóa. Nếu báo cáo phải được hiển thị với thứ tự xác định, sử dụng overload ba tham số:

~~~java
Collectors.groupingBy(classifier, mapFactory, downstream)
~~~

Tham số `mapFactory` là `Supplier<M>` tạo Map cho **cấp nhóm tương ứng**.

### 11.1. Sắp xếp cả hai cấp bằng TreeMap

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

Map<String, Map<String, List<String>>> sortedGroups =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        TreeMap::new,
        Collectors.groupingBy(
            Sale::category,
            TreeMap::new,
            Collectors.mapping(Sale::id, Collectors.toList())
        )
    ));
~~~

- `TreeMap::new` thứ nhất áp dụng cho khóa **khu vực**.
- `TreeMap::new` thứ hai áp dụng cho khóa **danh mục** trong mỗi khu vực.
- `mapping(Sale::id, toList())` tạo danh sách mã ở lá.

Với khóa `String`, `TreeMap` không có comparator sẽ sắp xếp theo **`String.compareTo`**. Đây không mặc nhiên là thứ tự chữ cái tiếng Việt dành cho người dùng. Nếu cần thứ tự hiển thị theo nghiệp vụ, có thể cung cấp comparator phù hợp hoặc lập bản đồ thứ tự riêng.

### 11.2. Giữ thứ tự xuất hiện của khóa với LinkedHashMap

Nếu nguồn là `List` tuần tự và muốn hiển thị các khóa theo lần xuất hiện đầu tiên:

~~~java
import java.util.LinkedHashMap;

Map<String, Map<String, List<Sale>>> insertionOrdered =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        LinkedHashMap::new,
        Collectors.groupingBy(
            Sale::category,
            LinkedHashMap::new,
            Collectors.toList()
        )
    ));
~~~

Trong xử lý **tuần tự từ List có encounter order**, `LinkedHashMap` duyệt khóa theo thứ tự chèn. Với parallel Stream, thứ tự kết hợp các bộ chứa có thể gây phức tạp; không dựa vào thứ tự thread hoàn thành hoặc giả định mọi collector đều giữ đúng lần gặp đầu nếu các đặc tính thứ tự không được bảo đảm.

**Lưu ý:** `TreeMap` chỉ thay đổi cách sắp xếp khóa, không thay đổi tên hoặc giá trị nguồn. Nếu khóa có thể `null`, cần chuẩn hóa trước; mục 12 giải thích.

## 12. Thiết kế khóa và xử lý null

### 12.1. groupingBy yêu cầu classifier trả khóa hợp lệ

Trong triển khai `Collectors.groupingBy` tiêu chuẩn của Java, classifier trả `null` sẽ gây `NullPointerException` (thường có thông điệp rằng phần tử không thể được ánh xạ sang khóa null). Đừng giả định Map mặc định sẽ nhận một khóa null.

Ví dụ nguy hiểm:

~~~java
record Sale(String id, String region, String category, long amountVnd) {}

List<Sale> raw = List.of(
    new Sale("S01", null, "Sách", 100L)
);

// Gây lỗi vì khóa group theo region là null.
// raw.stream().collect(Collectors.groupingBy(Sale::region));
~~~

Ví dụ `Sale` trên là một kiểu **độc lập** để minh họa null, không được đặt cùng tên với record `Sale` ở mục 2 trong một phạm vi khai báo.

Hai cách xử lý phổ biến:

**Cách A: loại dữ liệu thiếu khóa trước khi nhóm.**

~~~java
Map<String, List<Sale>> validRegions = raw.stream()
    .filter(s -> s.region() != null)
    .collect(Collectors.groupingBy(Sale::region));
~~~

**Cách B: dùng một khóa đại diện hợp lệ theo chính sách nghiệp vụ.**

~~~java
Map<String, List<Sale>> withUnknown = raw.stream()
    .collect(Collectors.groupingBy(
        s -> s.region() == null ? "Chưa xác định" : s.region()
    ));
~~~

Nếu chọn chuỗi sentinel `"Chưa xác định"`, cần bảo đảm nó **không gây va chạm** với một giá trị vùng thật hoặc phải chủ động chấp nhận gộp chúng.

Với nhiều cấp, phải xử lý `null` ở **tất cả cấp classifier**, không chỉ ở khóa ngoài.

### 12.2. Chuẩn hóa khóa trước khi phân nhóm

Dữ liệu đến từ nhiều nguồn có thể chứa `"Bắc"`, `" Bắc "` và một phiên bản viết hoa/viết thường khác. `groupingBy` không tự xem chúng là cùng khóa.

Một pipeline rõ ràng:

~~~java
record RegionItem(String region, String category, long amount) {}

List<RegionItem> input = List.of(
    new RegionItem(" Bắc ", "Sách", 100L),
    new RegionItem("Bắc",   "Sách", 200L)
);

Map<String, Map<String, Long>> totals = input.stream()
    .collect(Collectors.groupingBy(
        item -> item.region().trim(),
        Collectors.groupingBy(
            item -> item.category().trim(),
            Collectors.summingLong(RegionItem::amount)
        )
    ));

System.out.println(totals.get("Bắc").get("Sách")); // 300
~~~

Cách này chuẩn hóa ngay trong classifier. Với quy tắc phức tạp hoặc cần dùng khóa ở nhiều nơi, có thể tạo đối tượng trung gian đã chuẩn hóa bằng `map` rồi grouping, miễn là không làm mất các thuộc tính phục vụ phân nhóm.

Nếu xử lý tên riêng, nhãn tiếng Việt hoặc Unicode, không dùng `toLowerCase` hay so sánh chuỗi theo một locale ngẫu nhiên mà chưa xác định quy tắc miền dữ liệu.

### 12.3. equals và hashCode của khóa

Các khóa `String` đã triển khai `equals` và `hashCode` nhất quán. Với khóa là đối tượng tùy chỉnh, phải định nghĩa equality đúng ý nghĩa nhóm.

Một khóa chứa trường mutable và bị sửa sau khi đưa vào `HashMap` có thể khiến việc truy xuất nhóm thất bại. Ưu tiên khóa bất biến; với Java 16+, `record` rất thuận tiện cho composite key như mục tiếp theo.

## 13. Bản đồ lồng nhau hay composite key?

Có hai mô hình khác nhau cho cùng các chiều phân nhóm.

**Mô hình A: nested Map** — kết quả theo dạng `Map<Region, Map<Category, Value>>`.

~~~java
Map<String, Map<String, Long>> nested =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        Collectors.groupingBy(
            Sale::category,
            Collectors.summingLong(Sale::amountVnd)
        )
    ));
~~~

**Mô hình B: composite key** — gộp nhiều chiều thành một khóa kiểu record:

~~~java
record GroupKey(String region, String category) {}

Map<GroupKey, Long> flat =
    sales.stream().collect(Collectors.groupingBy(
        sale -> new GroupKey(sale.region(), sale.category()),
        Collectors.summingLong(Sale::amountVnd)
    ));
~~~

Trong hai ví dụ trên, `Sale` là kiểu ở mục 2 và tổng được tính trên **mọi giao dịch**, không chỉ giao dịch đã thanh toán. Hai cách biểu diễn có thể chứa cùng thông tin, nhưng truy xuất khác nhau:

~~~java
long byNested = nested.get("Bắc").get("Sách");
long byFlat = flat.get(new GroupKey("Bắc", "Sách"));

System.out.println(byNested); // 250000 (S01 + S03)
System.out.println(byFlat);   // 250000
~~~

### Khi nào chọn cách nào?

| Tiêu chí | Nested Map | Composite key |
|---|---|---|
| Duyệt báo cáo theo từng cấp | Thuận tiện: duyệt khu vực, rồi danh mục | Phải nhóm lại hoặc lọc theo thành phần khóa nếu muốn duyệt từng cấp |
| Tra cứu trực tiếp đúng một tổ hợp | Nhiều lần `get` | Một lần `get(new GroupKey(...))` |
| Kích thước kiểu | `Map<K1, Map<K2, V>>`, có thể dài khi lồng nhiều cấp | `Map<GroupKey, V>`, kiểu thường ngắn hơn |
| Diễn đạt báo cáo phân cấp | Tự nhiên | Cần chuyển đổi khi xuất ra dạng cây |
| Khóa có cấu trúc | Mỗi cấp một khóa | Một khóa bất biến chứa nhiều chiều |
| Tính rỗng của tổ hợp | Chỉ có nhóm xuất hiện trong nguồn | Chỉ có khóa xuất hiện trong nguồn |

`record GroupKey` tự tạo `equals` và `hashCode` dựa trên các thành phần. Đây là một cách thuận tiện để biểu diễn nhiều chiều mà không phải viết lại các phương thức so sánh.

**Không có cách nào luôn tốt hơn.** Nếu UI cần hiển thị “mỗi khu vực → các danh mục” thì Map lồng nhau rất tự nhiên. Nếu một thuật toán cần liên tục tra cứu cặp khóa, composite key có thể thuận tiện hơn.

## 14. Lồng quá nhiều cấp: dấu hiệu nên thiết kế lại

Ba, bốn hoặc năm cấp `groupingBy` đều có thể biểu diễn bằng Java, nhưng độ dài kiểu và code tăng nhanh:

~~~java
Map<String, Map<String, Map<Boolean, Long>>> counts =
    sales.stream().collect(Collectors.groupingBy(
        Sale::region,
        Collectors.groupingBy(
            Sale::category,
            Collectors.groupingBy(
                Sale::paid,
                Collectors.counting()
            )
        )
    ));
~~~

Đoạn này đếm theo **khu vực → danh mục → trạng thái thanh toán**. Về cú pháp, nó hợp lệ; về thiết kế, cần cân nhắc:

- UI thật sự cần cấu trúc phân cấp ba tầng hay chỉ cần một danh sách các dòng thống kê?
- Có cần tạo các nhóm vắng mặt với giá trị 0 không?
- Có cần sắp xếp các khóa ở từng cấp không?
- Có nên dùng `partitioningBy` cho trạng thái Boolean?
- Có nên dùng composite key hoặc một đối tượng báo cáo có tên trường rõ ràng?

Khi dùng `Map` lồng sâu, caller dễ viết nhiều chuỗi `get` và gặp `NullPointerException` khi một nhánh không tồn tại. Với dự án lớn, có thể đóng gói dữ liệu phân nhóm trong một kiểu báo cáo riêng, thay vì để cấu trúc Map phức tạp lan khắp ứng dụng.

## 15. Hiệu năng, tài nguyên và Stream song song

### 15.1. Chi phí phụ thuộc kiểu giá trị ở lá

Giả sử có `n` giao dịch và `g` tổ hợp nhóm xuất hiện:

- Nếu lá là `List<Sale>`, kết quả giữ tham chiếu tới gần `n` phần tử, cộng chi phí các Map/List.
- Nếu lá là `Long` từ `counting` hoặc `summingLong`, kích thước kết quả chủ yếu phụ thuộc vào `g` nhóm.
- Nếu classifier tạo chuỗi khóa mới, chuẩn hóa phức tạp hoặc hashCode tốn chi phí, tổng thời gian có thể tăng.
- Với Map dựa trên băm, chi phí trung bình cho việc phân loại thường thuận lợi, nhưng không nên coi một độ phức tạp cố định là bảo đảm trong mọi trường hợp.

Số chiều càng nhiều, số tổ hợp nhóm **có thể** càng lớn. Nếu từng giao dịch tạo một tổ hợp riêng, grouping không còn giảm nhiều dữ liệu, dù code vẫn dùng collector.

### 15.2. Song song vẫn phải bảo đảm đúng hợp đồng

Có thể viết:

~~~java
Map<String, Map<String, Long>> parallelTotals =
    sales.parallelStream()
        .filter(Sale::paid)
        .collect(Collectors.groupingBy(
            Sale::region,
            Collectors.groupingBy(
                Sale::category,
                Collectors.summingLong(Sale::amountVnd)
            )
        ));
~~~

`Collectors.groupingBy` là collector thông thường không concurrent; khi xử lý song song, framework có thể tạo nhiều Map trung gian rồi kết hợp. **Không cần** và **không nên** chia sẻ một `HashMap` mutable từ biến bên ngoài rồi gọi `parallelStream().forEach(...)` để tự cộng dồn.

Tuy nhiên, `parallel()` không tự bảo đảm nhanh hơn. Việc chia dữ liệu, tạo bộ chứa và hợp nhất Map lồng nhau có thể đáng kể, nhất là khi số nhóm nhiều hoặc dữ liệu nhỏ.

### 15.3. groupingByConcurrent không phải thay thế tương đương mọi lúc

Java cũng cung cấp `Collectors.groupingByConcurrent` để thu vào `ConcurrentMap` và hỗ trợ chiến lược tích lũy đồng thời. Nhưng collector này có đặc tính **UNORDERED** và cách tổ chức đồng thời khác grouping thông thường.

Nếu báo cáo cần giữ thứ tự phần tử theo encounter order, hoặc cần thứ tự khóa cụ thể, không tự động thay `groupingBy` bằng `groupingByConcurrent`. Với downstream không tự concurrent, triển khai còn phải phối hợp an toàn khi tích lũy; không tự suy ra rằng mọi container lá như `ArrayList` có thể bị nhiều thread tự ý cập nhật.

Khi chọn giữa hai cách, hãy xác định yêu cầu về **thứ tự, kết quả, concurrency, số nhóm**, rồi đo hiệu năng.

### 15.4. Nhóm dữ liệu rất lớn có thể không phù hợp với bộ nhớ JVM

`collect` là terminal operation: để tạo kết quả phân nhóm, các bộ chứa Map được xây trong bộ nhớ. Với dữ liệu rất lớn, dữ liệu streaming đầu vào không đồng nghĩa với **bộ nhớ kết quả nhỏ**.

Nếu chỉ cần một báo cáo tổng hợp có rất ít nhóm, `counting`/`summingLong` có thể phù hợp. Nếu cần lưu toàn bộ giao dịch trong từng nhóm, cần cân nhắc giới hạn heap, tải phân trang, hoặc đưa việc tổng hợp xuống cơ sở dữ liệu/giải pháp phân tích dữ liệu phù hợp với hệ thống.

Với **nguồn Stream vô hạn** không có điểm dừng, `collect(groupingBy(...))` thường không thể hoàn thành. Phải thiết kế giới hạn, cửa sổ xử lý, hoặc cơ chế dừng; các mô hình streaming thời gian thực có trạng thái đòi hỏi kiến trúc riêng.

## 16. Lỗi thường gặp và cách khắc phục

| Sai lầm | Vì sao sai hoặc gây rủi ro | Cách khắc phục |
|---|---|---|
| Dùng `groupingBy(region)` rồi tưởng đã có nhóm theo category | Chỉ phân nhóm **một cấp** | Đặt `groupingBy(category)` vào downstream |
| `map(Sale::id)` trước khi cần nhóm theo region/category | Mất dữ liệu classifier | Dùng downstream `mapping` sau các cấp grouping |
| Gọi `map.get(region).get(category)` khi khóa có thể thiếu | `Map.get` có thể trả `null` | Dùng `getOrDefault`/`containsKey`, hoặc helper |
| Giả định mọi cặp region/category đều có mặt | `groupingBy` chỉ tạo nhóm đã gặp | Khởi tạo nhóm thiếu theo danh mục nghiệp vụ |
| `filter` trước grouping nhưng muốn nhóm có count 0 | Nhóm không có phần tử đạt điều kiện bị biến mất | Dùng downstream `Collectors.filtering` (Java 9+) |
| Dùng `groupingBy(boolean)` rồi giả định luôn có true/false | Nhóm thiếu một phía không xuất hiện | `partitioningBy` ở cấp Boolean |
| Classifier trả null | Thường ném `NullPointerException` | Lọc/chuẩn hóa hoặc ánh xạ sentinel |
| Tin rằng `groupingBy` luôn trả `LinkedHashMap` | Không có bảo đảm Map mặc định | Chỉ định `mapFactory` |
| Dùng `counting()` nhưng khai báo giá trị `Integer` | `counting` tạo `Long` | Dùng `Map<..., Long>` |
| Dùng `toList()` khi chỉ cần tổng/đếm | Giữ nhiều tham chiếu phần tử không cần thiết | Dùng `summingLong`/`counting` |
| Cộng tiền trong shared Map bằng `parallelStream().forEach` | Race condition và trạng thái ngoài pipeline | Dùng collector đúng hợp đồng |
| Dùng collector trên nguồn vô hạn không điểm dừng | Không thể hoàn thành | Giới hạn hoặc thiết kế cửa sổ xử lý |
| Quên tràn số trong tổng `long` | Kết quả báo cáo có thể sai | Chọn kiểu/giới hạn và chính sách số học phù hợp |

## 17. Bài tập thực hành: báo cáo đơn hàng nhiều cấp

**Bối cảnh:** một cửa hàng có giao dịch bán hàng, mỗi giao dịch gồm mã, khu vực, danh mục, số tiền và trạng thái thanh toán. Cần báo cáo **doanh thu đã thanh toán theo khu vực → danh mục**, và **số giao dịch đã thanh toán ở từng cặp khu vực → danh mục, kể cả nhóm chỉ có giao dịch chưa thanh toán**.

**Yêu cầu:**

1. Tạo `Map<String, Map<String, Long>>` cho doanh thu đã thanh toán.
2. Tạo một Map hai cấp khác cho **số giao dịch đã thanh toán**, nhưng vẫn giữ nhóm xuất hiện trong nguồn với count 0.
3. Truy xuất an toàn cặp khóa `("Miền Tây", "Sách")` vốn không có trong dữ liệu.
4. Giải thích sự khác biệt về tập khóa giữa hai báo cáo.

### Lời giải tham khảo (Java 17+)

~~~java
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class MultiLevelGroupingPractice {
    record Sale(
        String id,
        String region,
        String category,
        long amountVnd,
        boolean paid
    ) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
            new Sale("A1", "Bắc", "Sách", 100L, true),
            new Sale("A2", "Bắc", "Sách", 200L, false),
            new Sale("A3", "Nam", "Bút",   50L, true),
            new Sale("A4", "Nam", "Sách",  70L, false)
        );

        // Báo cáo 1: loại giao dịch chưa thanh toán trước khi nhóm.
        Map<String, Map<String, Long>> paidRevenue =
            sales.stream()
                .filter(Sale::paid)
                .collect(Collectors.groupingBy(
                    Sale::region,
                    Collectors.groupingBy(
                        Sale::category,
                        Collectors.summingLong(Sale::amountVnd)
                    )
                ));

        // Báo cáo 2: tạo nhóm trước, lọc bên trong từng nhóm.
        Map<String, Map<String, Long>> paidCountWithZero =
            sales.stream().collect(Collectors.groupingBy(
                Sale::region,
                Collectors.groupingBy(
                    Sale::category,
                    Collectors.filtering(
                        Sale::paid,
                        Collectors.counting()
                    )
                )
            ));

        Map<String, Long> missingRegion =
            paidRevenue.getOrDefault(
                "Miền Tây",
                Collections.emptyMap()
            );
        long missingValue =
            missingRegion.getOrDefault("Sách", 0L);

        System.out.println(paidRevenue.get("Bắc").get("Sách")); // 100
        System.out.println(paidRevenue.get("Nam").get("Bút"));  // 50

        System.out.println(paidCountWithZero.get("Bắc").get("Sách")); // 1
        System.out.println(paidCountWithZero.get("Nam").get("Sách")); // 0

        System.out.println(missingValue); // 0 theo chính sách hiển thị
        System.out.println(
            paidRevenue.get("Nam").containsKey("Sách")
        ); // false
    }
}
~~~

**Giải thích:** nhóm **Nam → Sách** chỉ có giao dịch `A4` chưa thanh toán. Vì vậy báo cáo doanh thu dùng `filter` trước nhóm **không tạo** khóa `Sách` dưới `Nam`; báo cáo số lượng dùng downstream `filtering` **vẫn có** khóa này, nhưng giá trị bằng `0L`. Cặp `Miền Tây → Sách` hoàn toàn không có trong nguồn, nên cả hai collector đều không tạo nhóm; `getOrDefault` chỉ quyết định cách **trình bày** khi truy xuất.

### Câu hỏi tự kiểm tra

1. `groupingBy(region, groupingBy(category))` trả kiểu lá nào? — **`List<Sale>`**.
2. Thay downstream cuối bằng `counting()` thì giá trị lá kiểu gì? — **`Long`**.
3. Nếu muốn chỉ giữ mã giao dịch ở lá, nên dùng collector nào? — **`mapping(Sale::id, toList())`**.
4. `filter` ở đầu pipeline và `Collectors.filtering` ở downstream khác nhau ở điểm nào? — **Nhóm không có phần tử đạt điều kiện có thể bị bỏ hẳn hoặc được giữ với giá trị rỗng/0**.
5. `groupingBy(Sale::paid)` có luôn tạo khóa `true` và `false` không? — **Không**; `partitioningBy` phù hợp với hai nhánh cố định.
6. `groupingBy` có bảo đảm thứ tự khóa của Map kết quả không? — **Không** nếu không cấu hình map factory.
7. Composite key bằng record có nhất thiết tạo nested Map không? — **Không**, nó tạo `Map<GroupKey, V>`.
8. Có thể giả định khóa `null` được chấp nhận trong groupingBy không? — **Không**; cần chuẩn hóa hoặc loại bỏ dữ liệu thiếu khóa.
9. Dùng `parallelStream()` với grouping nhiều cấp có mặc định nhanh hơn không? — **Không**, phải đo và xét chi phí ghép các Map trung gian.

## 18. Ghi nhớ trước khi xây báo cáo đa chiều

**Phân nhóm nhiều cấp** trong Java Stream API có dạng **`groupingBy(khóaNgoài, groupingBy(khóaTrong, downstream))`**. Mỗi `groupingBy` thêm một chiều phân tích, còn downstream cuối xác định dữ liệu ở lá: danh sách chi tiết, số lượng, tổng, thống kê hoặc đại diện của nhóm.

Khi xây pipeline, hãy xác định rõ **thứ tự các khóa phân cấp**, **kiểu giá trị ở lá**, **chính sách nhóm rỗng**, **khóa thiếu/null**, **thứ tự hiển thị** và **điều kiện kết thúc của nguồn**. Khi dữ liệu lớn hoặc cần xử lý song song, ưu tiên collector tuân thủ hợp đồng và đo chi phí bộ nhớ/phối hợp; không tự cập nhật `Map` chia sẻ bằng callback có trạng thái.

Một bản đồ lồng nhau thể hiện tốt báo cáo theo cấp bậc; khi cần tra cứu tổ hợp khóa hoặc giảm độ sâu kiểu, có thể cân nhắc **composite key**. Nắm được những lựa chọn này sẽ giúp bạn triển khai `groupingBy`, `partitioningBy`, collector tùy chỉnh và các bài toán phân tích dữ liệu phức tạp một cách rõ nghĩa, kiểm tra được và an toàn hơn.
