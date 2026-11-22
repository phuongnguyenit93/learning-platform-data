# Giữ thứ tự khóa bằng `LinkedHashMap` và sắp xếp bằng `TreeMap`

## 1. Vì sao thu thập thành `Map` phải quan tâm đến thứ tự?

Trong Java Stream API, một pipeline thường lọc và biến đổi bản ghi bằng `filter`, `map`, rồi dùng `collect` để tạo kết quả. Khi đầu ra là `Map<K,V>`, không chỉ **khóa nào ứng với giá trị nào** quan trọng, mà đôi khi **thứ tự duyệt các khóa** cũng là một phần của yêu cầu nghiệp vụ.

Ví dụ, một luồng đơn hàng xuất hiện theo thứ tự vùng:

```text
O-1: HN, 120_000
O-2: HCM, 80_000
O-3: HN, 30_000
O-4: DN, 50_000
```

Sau khi cộng tiền theo vùng, ta cần một trong hai kết quả:

- **Giữ thứ tự vùng xuất hiện lần đầu:** `HN → HCM → DN`. Hữu ích cho báo cáo muốn giữ thứ tự nguồn.
- **Duyệt khóa theo thứ tự đã sắp:** `DN → HCM → HN`. Hữu ích cho bảng tra cứu và hiển thị theo mã vùng.

Hai nhu cầu dùng hai loại map khác nhau:

| Nhu cầu | Cấu trúc thường chọn |
| --- | --- |
| Thứ tự **chèn khóa** (*insertion order*) | `LinkedHashMap` |
| Thứ tự **so sánh khóa** (*sorted key order*) | `TreeMap` |
| Chỉ cần ánh xạ khóa → giá trị, không yêu cầu thứ tự | `Map` thông thường, có thể do collector quyết định |

**Mục tiêu của bài:** đọc và dùng đúng overload `Collectors.toMap`, `Collectors.groupingBy` có tham số `mapFactory`; chọn `LinkedHashMap` hay `TreeMap`; xử lý khóa trùng; thiết kế comparator; kiểm thử thứ tự; nhận diện giới hạn của `null`, stream song song, tài nguyên và hiệu năng.

Lưu ý: *thứ tự gặp phần tử của stream* (*encounter order*) và *thứ tự duyệt khóa của map* là hai khái niệm khác nhau. Một `List` có encounter order không làm cho `HashMap` tự động duyệt theo thứ tự ấy.

## 2. Ba kiểu `Map` và lời hứa về thứ tự

### 2.1. `HashMap`: không có cam kết về thứ tự duyệt

`HashMap` cho phép tìm kiếm khóa hiệu quả trong nhiều trường hợp nhưng **không bảo đảm** thứ tự lặp qua `keySet()`, `values()` hoặc `entrySet()`. Việc một lần chạy cho ra thứ tự “như đã chèn” hoặc “như đã sắp” chỉ là tình cờ.

```java
import java.util.HashMap;
import java.util.Map;

Map<String, Integer> map = new HashMap<>();
map.put("HN", 1);
map.put("HCM", 2);
map.put("DN", 3);

System.out.println(map.keySet());
// Không dự đoán thứ tự chính xác chỉ dựa trên thứ tự put.
```

Vì vậy, nếu phần mềm phải xuất CSV, JSON hay bảng hiển thị theo một thứ tự đã định, **không dựa vào thứ tự duyệt của `HashMap`**.

### 2.2. `LinkedHashMap`: giữ thứ tự chèn

Ở chế độ mặc định, `LinkedHashMap` duy trì thứ tự lần đầu một khóa được đưa vào map:

```java
import java.util.LinkedHashMap;
import java.util.List;

LinkedHashMap<String, Integer> map = new LinkedHashMap<>();
map.put("HN", 1);
map.put("HCM", 2);
map.put("DN", 3);
map.put("HN", 99); // Cập nhật giá trị khóa đã tồn tại.

System.out.println(List.copyOf(map.keySet()));
// [HN, HCM, DN]
System.out.println(map.get("HN")); // 99
```

Chèn lại một khóa đã tồn tại bằng `put` không đổi vị trí khóa đó trong **insertion-order `LinkedHashMap`**. Điều này đặc biệt hữu ích khi collector gặp nhiều bản ghi có cùng khóa nhưng muốn giữ vị trí xuất hiện đầu tiên.

**Ngoại lệ cần phân biệt:** `LinkedHashMap` có constructor nhận tham số `accessOrder`. Khi tạo với `accessOrder = true`, các thao tác truy cập như `get` có thể đưa entry về cuối. Bài này dùng **chế độ chèn mặc định** (`new LinkedHashMap<>()`), không dùng chế độ access-order cho báo cáo thứ tự đầu vào.

### 2.3. `TreeMap`: khóa được duyệt theo comparator

`TreeMap` là một `NavigableMap` duy trì khóa theo **thứ tự tự nhiên** hoặc theo `Comparator` được cung cấp:

```java
import java.util.List;
import java.util.TreeMap;

TreeMap<String, Integer> map = new TreeMap<>();
map.put("HN", 1);
map.put("HCM", 2);
map.put("DN", 3);

System.out.println(List.copyOf(map.keySet()));
// [DN, HCM, HN]
```

Không quan trọng `HN` được thêm trước `DN`: `TreeMap` sử dụng so sánh khóa, không sử dụng thời điểm chèn. Vì vậy, “dùng `TreeMap`” **không đồng nghĩa** “giữ thứ tự gặp phần tử”.

### 2.4. Bảng so sánh nhanh

| Thuộc tính | `HashMap` | `LinkedHashMap` mặc định | `TreeMap` |
| --- | --- | --- | --- |
| Thứ tự duyệt khóa | Không cam kết | Thứ tự chèn lần đầu | Theo thứ tự khóa/comparator |
| Thao tác `put/get` điển hình | Trung bình gần `O(1)` | Trung bình gần `O(1)` | `O(log n)` |
| `firstKey()/lastKey()` | Không có | Không phải API của `SortedMap` | Có |
| Phụ thuộc hash/equals | Có | Có | Dựa vào comparator/`compareTo` |
| Có tự sắp theo **giá trị**? | Không | Không | Không, sắp theo **khóa** |
| Phù hợp nhất | Tra cứu không quan tâm thứ tự | Báo cáo theo thứ tự xuất hiện | Tra cứu/range query theo thứ tự khóa |

Các độ phức tạp trên mô tả thao tác map điển hình; hiệu năng thực còn tùy số lượng, phân bố khóa, chi phí `hashCode`/comparator, cấp phát và truy cập bộ nhớ.

## 3. Overload `Collectors.toMap` có `mapFactory`

Để chọn loại map kết quả ngay khi thu thập, dùng overload bốn tham số:

```java
<T, K, U, M extends Map<K, U>> Collector<T, ?, M> toMap(
    Function<? super T, ? extends K> keyMapper,
    Function<? super T, ? extends U> valueMapper,
    BinaryOperator<U> mergeFunction,
    Supplier<M> mapFactory
)
```

Giải mã từng tham số:

| Tham số | Chức năng |
| --- | --- |
| `keyMapper` | Lấy khóa `K` từ phần tử `T` |
| `valueMapper` | Lấy giá trị `U` từ phần tử `T` |
| `mergeFunction` | Gộp hai giá trị `U` khi **trùng khóa** |
| `mapFactory` | Tạo map kết quả thuộc kiểu cụ thể `M` |

Tại sao cần tham số `mergeFunction`? Vì nhiều phần tử có thể có cùng khóa. Nếu không quy định cách gộp, một overload `toMap` hai tham số sẽ ném `IllegalStateException` khi gặp khóa trùng.

Với `mapFactory`, ta được quyền yêu cầu kiểu map là `LinkedHashMap` hoặc `TreeMap`, thay vì dựa vào kiểu cụ thể do collector mặc định trả về.

## 4. Ví dụ hoàn chỉnh: tổng doanh thu với hai thứ tự khóa

Ví dụ chạy trực tiếp trên **JDK 17 trở lên**:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class OrderedRevenueDemo {

    public record Order(String id, String region, long amountVnd) {
        public Order {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(region, "region");
            if (id.isBlank() || region.isBlank() || amountVnd < 0L) {
                throw new IllegalArgumentException("Order không hợp lệ");
            }
        }
    }

    public static List<Order> sample() {
        return List.of(
            new Order("O-1", "HN", 120_000L),
            new Order("O-2", "HCM", 80_000L),
            new Order("O-3", "HN", 30_000L),
            new Order("O-4", "DN", 50_000L)
        );
    }

    public static LinkedHashMap<String, Long> totalsInSourceOrder(
        List<Order> orders
    ) {
        return orders.stream().collect(Collectors.toMap(
            Order::region,
            Order::amountVnd,
            Long::sum,
            LinkedHashMap::new
        ));
    }

    public static TreeMap<String, Long> totalsBySortedKey(
        List<Order> orders
    ) {
        return orders.stream().collect(Collectors.toMap(
            Order::region,
            Order::amountVnd,
            Long::sum,
            TreeMap::new
        ));
    }

    public static void main(String[] args) {
        List<Order> orders = sample();

        Map<String, Long> byEncounter = totalsInSourceOrder(orders);
        Map<String, Long> byKey = totalsBySortedKey(orders);

        System.out.println(List.copyOf(byEncounter.keySet()));
        // [HN, HCM, DN]
        System.out.println(List.copyOf(byKey.keySet()));
        // [DN, HCM, HN]

        System.out.println(byEncounter.get("HN")); // 150000
        System.out.println(byKey.get("HN"));       // 150000
        System.out.println(byEncounter.equals(byKey)); // true
    }
}
```

**Đọc pipeline lần lượt:**

1. `orders.stream()` là `Stream<Order>`, có encounter order từ `List`.
2. `Order::region` sinh khóa `String`.
3. `Order::amountVnd` sinh giá trị `Long` nhờ autoboxing của `long`.
4. `Long::sum` hợp nhất số tiền khi hai đơn cùng vùng.
5. `LinkedHashMap::new` hoặc `TreeMap::new` quyết định thứ tự **duyệt khóa**.
6. `collect(...)` là terminal operation; kết quả là map, không còn là stream.

Hai map có thể `equals` vì `Map.equals` so sánh tập ánh xạ khóa–giá trị, **không coi thứ tự duyệt là một phần của phép so sánh**. Nếu yêu cầu kiểm thử thứ tự, phải so sánh `List.copyOf(map.keySet())` hoặc một danh sách entry theo thứ tự.

**Lưu ý tiền tệ:** ví dụ dùng `long` đơn vị đồng và `Long::sum` để tập trung vào thứ tự khóa. `Long::sum` không tự phát hiện tràn số; nếu miền giá trị có thể vượt `long`, cần chọn kiểu hoặc chính sách số học phù hợp. Việc dùng `LinkedHashMap`/`TreeMap` không thay đổi rủi ro số học đó.

## 5. Giữ thứ tự khóa khi `groupingBy`

`Collectors.groupingBy` thường trả `Map<K,List<T>>` hoặc `Map<K,D>` với downstream collector. Overload ba tham số cho phép chọn `mapFactory`:

```java
<T, K, D, A, M extends Map<K, D>> Collector<T, ?, M> groupingBy(
    Function<? super T, ? extends K> classifier,
    Supplier<M> mapFactory,
    Collector<? super T, A, D> downstream
)
```

Tư duy: **phân loại** phần tử thành khóa, **tạo map** theo factory, sau đó **gom giá trị của từng khóa** bằng downstream collector.

### 5.1. `LinkedHashMap` + `toList`: nhóm theo thứ tự xuất hiện

Sử dụng `Order` và `sample()` của `OrderedRevenueDemo` ở mục 4:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.stream.Collectors;

LinkedHashMap<String, List<OrderedRevenueDemo.Order>> grouped =
    OrderedRevenueDemo.sample().stream()
        .collect(Collectors.groupingBy(
            OrderedRevenueDemo.Order::region,
            LinkedHashMap::new,
            Collectors.toList()
        ));

System.out.println(List.copyOf(grouped.keySet()));
// [HN, HCM, DN]
System.out.println(
    grouped.get("HN").stream().map(
        OrderedRevenueDemo.Order::id
    ).toList()
); // [O-1, O-3]
```

Đối với một **stream tuần tự có encounter order**, khóa xuất hiện lần đầu sẽ được chèn vào `LinkedHashMap` trước. Những phần tử cùng khóa được đưa vào downstream collector và cập nhật giá trị tương ứng; khóa không bị chèn lại khi nhóm đã có sẵn.

### 5.2. `TreeMap` + `counting`: nhóm và sắp theo khóa

```java
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

TreeMap<String, Long> orderCountByRegion =
    OrderedRevenueDemo.sample().stream()
        .collect(Collectors.groupingBy(
            OrderedRevenueDemo.Order::region,
            TreeMap::new,
            Collectors.counting()
        ));

System.out.println(List.copyOf(orderCountByRegion.keySet()));
// [DN, HCM, HN]
System.out.println(orderCountByRegion.get("HN")); // 2
```

Kiểu downstream thay đổi từ `List<Order>` thành `Long`, nhưng `TreeMap` vẫn quyết định thứ tự **khóa nhóm**.

### 5.3. So sánh `toMap` và `groupingBy`

| Yêu cầu | Cách đọc |
| --- | --- |
| Mỗi phần tử có một khóa và một giá trị, khóa có thể trùng | `toMap(keyMapper, valueMapper, mergeFunction, mapFactory)` |
| Muốn giữ **mọi bản ghi** trong mỗi nhóm | `groupingBy(classifier, mapFactory, toList())` |
| Muốn đếm, tổng hợp hoặc tính thống kê cho mỗi nhóm | `groupingBy(classifier, mapFactory, downstream)` |
| Muốn thứ tự khóa theo lần gặp đầu | `LinkedHashMap::new` |
| Muốn thứ tự khóa theo comparator | `TreeMap::new` hoặc supplier tạo TreeMap có comparator |

Không nhầm **thứ tự khóa của map** với **thứ tự phần tử bên trong các `List` downstream**: đó là hai hợp đồng riêng và phải xét theo encounter order cũng như đặc tính của collector.

## 6. Khóa trùng: vị trí khóa và giá trị được gộp là hai quyết định khác nhau

Giả sử nguồn có ba bản ghi theo thứ tự:

```text
("HN", 10), ("HCM", 20), ("HN", 30)
```

Khi dùng `LinkedHashMap` mặc định, thứ tự khóa là `[HN, HCM]`. Nhưng giá trị của `HN` phụ thuộc `mergeFunction`:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Entry(String key, int value) {}

List<Entry> rows = List.of(
    new Entry("HN", 10),
    new Entry("HCM", 20),
    new Entry("HN", 30)
);

Map<String, Integer> keepFirst = rows.stream()
    .collect(Collectors.toMap(
        Entry::key,
        Entry::value,
        (oldValue, newValue) -> oldValue,
        LinkedHashMap::new
    ));

Map<String, Integer> keepLast = rows.stream()
    .collect(Collectors.toMap(
        Entry::key,
        Entry::value,
        (oldValue, newValue) -> newValue,
        LinkedHashMap::new
    ));

Map<String, Integer> sumValues = rows.stream()
    .collect(Collectors.toMap(
        Entry::key,
        Entry::value,
        Integer::sum,
        LinkedHashMap::new
    ));

System.out.println(keepFirst.get("HN"));  // 10
System.out.println(keepLast.get("HN"));   // 30
System.out.println(sumValues.get("HN"));  // 40
System.out.println(List.copyOf(keepLast.keySet())); // [HN, HCM]
```

**Lưu ý quan trọng:** “giữ giá trị đến sau” (`keepLast`) **không có nghĩa** “chuyển khóa đến cuối map” (`LinkedHashMap` mặc định vẫn giữ vị trí chèn ban đầu). Nếu nghiệp vụ yêu cầu thứ tự theo lần cập nhật cuối, cần định nghĩa một thuật toán khác; không tự suy luận điều đó từ `(old, newer) -> newer`.

### 6.1. Khi nào nên báo lỗi trùng khóa?

Nếu khóa là mã định danh duy nhất, mọi sự trùng lặp có thể là lỗi dữ liệu. Đừng tự chọn gộp:

```java
Map<String, Entry> unique = rows.stream()
    .collect(Collectors.toMap(
        Entry::key,
        java.util.function.Function.identity(),
        (first, second) -> {
            throw new IllegalArgumentException(
                "Khóa trùng: " + first.key()
            );
        },
        LinkedHashMap::new
    ));
// Với rows hiện tại, terminal operation sẽ ném ngoại lệ.
```

Với dữ liệu có khóa thật sự duy nhất, overload hai tham số `toMap(keyMapper,valueMapper)` cũng phù hợp, nhưng **không cho phép chỉ định mapFactory**; nếu còn yêu cầu thứ tự, dùng overload bốn tham số như trên.

### 6.2. Gộp cần có hợp đồng cho xử lý song song

Với một collector được dùng trên parallel stream, kết quả phải tương đương kết quả tuần tự theo hợp đồng collector. Chọn phép gộp có tính kết hợp (*associative*) và phù hợp với quy tắc nghiệp vụ. Các phép `Long::sum`, `Integer::sum` có tính kết hợp theo phép cộng số nguyên modulo; nếu muốn phát hiện tràn bằng `Math.addExact`, cần xác định chính sách khi tổng vượt miền biểu diễn. Với `double`, thứ tự gộp có thể đổi sai số làm tròn.

Những phép như trừ `(a,b) -> a-b` không có tính kết hợp, nên rất dễ cho kết quả sai khi chia và gộp các phần của pipeline.

## 7. Sắp xếp `TreeMap` theo thứ tự tự nhiên hoặc comparator

`TreeMap` dùng `Comparable` của khóa hoặc comparator. Không cần sắp xếp stream trước:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

TreeMap<String, Long> ascending =
    OrderedRevenueDemo.sample().stream()
        .collect(Collectors.toMap(
            OrderedRevenueDemo.Order::region,
            OrderedRevenueDemo.Order::amountVnd,
            Long::sum,
            TreeMap::new
        ));

System.out.println(List.copyOf(ascending.keySet()));
// [DN, HCM, HN]
```

### 7.1. Đảo chiều thứ tự khóa

Đưa comparator vào supplier:

```java
import java.util.Comparator;
import java.util.TreeMap;
import java.util.stream.Collectors;

TreeMap<String, Long> descending =
    OrderedRevenueDemo.sample().stream()
        .collect(Collectors.toMap(
            OrderedRevenueDemo.Order::region,
            OrderedRevenueDemo.Order::amountVnd,
            Long::sum,
            () -> new TreeMap<String, Long>(Comparator.reverseOrder())
        ));

System.out.println(List.copyOf(descending.keySet()));
// [HN, HCM, DN]
```

Comparator ở đây thay đổi **cách TreeMap duyệt và nhận diện khóa tương đương**, không chỉ tạo một view hiển thị khác.

### 7.2. Khóa gồm nhiều trường

Giả sử khóa có hai phần: mã vùng và năm. Một record làm khóa sẽ có `equals`/`hashCode` tự sinh, nhưng **không tự triển khai `Comparable`**; muốn lưu trong `TreeMap` phải cung cấp comparator:

```java
import java.util.Comparator;
import java.util.TreeMap;

record RegionYear(String region, int year) {}

Comparator<RegionYear> byRegionThenYear =
    Comparator.comparing(RegionYear::region)
        .thenComparingInt(RegionYear::year);

TreeMap<RegionYear, Long> revenue = new TreeMap<>(byRegionThenYear);
revenue.put(new RegionYear("HN", 2026), 100L);
revenue.put(new RegionYear("DN", 2025), 200L);
revenue.put(new RegionYear("HN", 2025), 300L);

System.out.println(List.copyOf(revenue.keySet()));
// [RegionYear[region=DN, year=2025],
//  RegionYear[region=HN, year=2025],
//  RegionYear[region=HN, year=2026]]
```

Comparator nhiều tầng phải phản ánh đúng ý nghĩa nghiệp vụ; ví dụ có thể đổi `thenComparingInt(RegionYear::year)` thành một comparator đảo chiều năm nếu báo cáo cần năm mới trước.

### 7.3. Comparator xác định khóa **trùng nhau**

`TreeMap` xem hai khóa là tương đương khi comparator trả `0`. Điều này có thể khác `equals`:

```java
import java.util.TreeMap;

TreeMap<String, Integer> insensitive =
    new TreeMap<>(String.CASE_INSENSITIVE_ORDER);

insensitive.put("hn", 10);
insensitive.put("HN", 20);

System.out.println(insensitive.size());    // 1
System.out.println(insensitive.get("hn")); // 20
```

Đây không chỉ là thay đổi thứ tự hiển thị: hai chuỗi `"hn"` và `"HN"` đã bị coi là **cùng một khóa** trong `TreeMap`. Nếu dùng `Collectors.toMap`, chúng có thể kích hoạt `mergeFunction`; khi dùng `groupingBy`, chúng thuộc cùng nhóm theo comparator.

**Nguyên tắc:** comparator của sorted map nên **nhất quán với `equals`** nếu muốn tuân thủ đầy đủ hợp đồng `Map`. Nếu dữ liệu cần gộp mã không phân biệt hoa/thường, thường an toàn hơn khi **chuẩn hóa khóa trước** (ví dụ `strip().toUpperCase(Locale.ROOT)`), rồi dùng comparator phù hợp với khóa đã chuẩn hóa. Không dùng comparator chỉ xét độ dài chuỗi làm khóa nếu hai mã khác nhau nhưng cùng độ dài vẫn phải phân biệt.

## 8. Muốn sắp theo **giá trị** phải làm gì?

`TreeMap` chỉ sắp theo **khóa**, không tự sắp entry theo doanh thu hoặc số lượng. Nếu yêu cầu “vùng có doanh thu cao nhất đứng trước”, một hướng là sắp stream **entry** theo giá trị, rồi thu về `LinkedHashMap`:

```java
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;

Map<String, Long> source = OrderedRevenueDemo.totalsBySortedKey(
    OrderedRevenueDemo.sample()
);

LinkedHashMap<String, Long> byRevenueDescending = source.entrySet()
    .stream()
    .sorted(
        Map.Entry.<String, Long>comparingByValue(
            Comparator.reverseOrder()
        ).thenComparing(Map.Entry.comparingByKey())
    )
    .collect(Collectors.toMap(
        Map.Entry::getKey,
        Map.Entry::getValue,
        (left, right) -> left,
        LinkedHashMap::new
    ));

System.out.println(List.copyOf(byRevenueDescending.keySet()));
// [HN, HCM, DN] (150000, 80000, 50000)
```

Ở đây `sorted` sắp theo **giá trị giảm dần**, rồi theo **khóa tăng dần** để phá hòa một cách xác định. `LinkedHashMap` giữ đúng thứ tự entry sau khi `sorted` cung cấp. Sử dụng `TreeMap` ở bước cuối sẽ làm mất mục tiêu “sắp theo giá trị”, vì TreeMap lại sắp theo khóa.

Nếu chỉ cần xuất một danh sách xếp hạng, không nhất thiết phải thu ngược về map:

```java
List<Map.Entry<String, Long>> ranking = source.entrySet()
    .stream()
    .sorted(
        Map.Entry.<String, Long>comparingByValue().reversed()
            .thenComparing(Map.Entry.comparingByKey())
    )
    .toList();
```

**Ghi nhớ:** `Map.equals` vẫn có thể báo hai map bằng nhau dù thứ tự khác nhau; kiểm thử sắp xếp bằng danh sách khóa/entry.

## 9. Thứ tự thao tác `filter`, `map`, `sorted` và `collect`

Một pipeline đúng phụ thuộc thứ tự các bước. Xét dữ liệu `Order` ban đầu ở mục 4.

### 9.1. Lọc trước, rồi giữ thứ tự xuất hiện của khóa

```java
LinkedHashMap<String, Long> onlyLargeOrders =
    OrderedRevenueDemo.sample().stream()
        .filter(order -> order.amountVnd() >= 50_000L)
        .collect(Collectors.toMap(
            OrderedRevenueDemo.Order::region,
            OrderedRevenueDemo.Order::amountVnd,
            Long::sum,
            LinkedHashMap::new
        ));

System.out.println(List.copyOf(onlyLargeOrders.keySet()));
// [HN, HCM, DN]
```

Ở dữ liệu khác, nếu bản ghi đầu tiên của một vùng bị `filter` loại, **lần xuất hiện đầu tiên sau lọc** mới quyết định vị trí khóa trong `LinkedHashMap`. Đó là thứ tự theo **stream đầu vào của collector**, không nhất thiết theo collection thô.

### 9.2. Sắp phần tử trước, rồi giữ thứ tự các khóa sau sắp

```java
LinkedHashMap<String, Long> byRegionOfSortedRows =
    OrderedRevenueDemo.sample().stream()
        .sorted(java.util.Comparator.comparing(
            OrderedRevenueDemo.Order::region
        ))
        .collect(Collectors.toMap(
            OrderedRevenueDemo.Order::region,
            OrderedRevenueDemo.Order::amountVnd,
            Long::sum,
            LinkedHashMap::new
        ));

System.out.println(List.copyOf(byRegionOfSortedRows.keySet()));
// [DN, HCM, HN]
```

Trường hợp này `LinkedHashMap` vẫn không “tự sắp xếp”; `sorted` đã tạo một encounter order mới. Nếu mục tiêu chỉ là sắp **khóa kết quả**, dùng `TreeMap` thường trực tiếp hơn và tránh bước sắp toàn bộ phần tử nguồn.

### 9.3. Nguồn không có encounter order

Nếu nguồn là `HashSet` hoặc pipeline đã gọi `unordered()`, “khóa xuất hiện đầu tiên” không còn là khái niệm ổn định. `LinkedHashMap` vẫn giữ thứ tự **chèn thực tế** của collector, nhưng thứ tự ấy không nhất thiết được bảo đảm theo yêu cầu nghiệp vụ. Muốn thứ tự xác định, hãy định nghĩa rõ phép sắp hoặc khởi tạo nguồn có encounter order.

## 10. Nguồn rỗng, khóa `null` và giá trị `null`

### 10.1. Nguồn rỗng

Với `LinkedHashMap::new` hoặc `TreeMap::new`, collector trên nguồn rỗng trả một map rỗng thuộc kiểu đã yêu cầu:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.TreeMap;
import java.util.stream.Collectors;

LinkedHashMap<String, Integer> emptyInsertion =
    List.<String>of().stream()
        .collect(Collectors.toMap(
            s -> s,
            String::length,
            Integer::sum,
            LinkedHashMap::new
        ));

TreeMap<String, Integer> emptySorted =
    List.<String>of().stream()
        .collect(Collectors.toMap(
            s -> s,
            String::length,
            Integer::sum,
            TreeMap::new
        ));

System.out.println(emptyInsertion.isEmpty()); // true
System.out.println(emptySorted.isEmpty());    // true
```

Không cần dùng `Optional<Map<...>>` chỉ vì map có thể rỗng; `Map` rỗng thường đã diễn đạt đủ “không có phần tử để thu thập”. Nếu cần phân biệt “không có bản ghi” với “nguồn truy vấn bị lỗi”, thiết kế trạng thái lỗi riêng.

### 10.2. Khóa `null`

`TreeMap` sử dụng thứ tự tự nhiên của `String` không chấp nhận khóa `null`. `Collectors.groupingBy` cũng từ chối classifier trả khóa `null` trong các triển khai JDK thông dụng, thay vì tự tạo nhóm `null`. Đừng dựa vào việc `HashMap` cho phép một khóa null để suy rằng mọi overload collector đều có hợp đồng giống nhau.

Một chính sách tường minh:

```java
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

record SourceRow(String region, long amount) {}

List<SourceRow> rows = List.of(
    new SourceRow(null, 10L),
    new SourceRow(" hn ", 20L)
);

Map<String, Long> totals = rows.stream()
    .collect(Collectors.toMap(
        row -> row.region() == null
            ? "UNKNOWN"
            : row.region().strip().toUpperCase(Locale.ROOT),
        SourceRow::amount,
        Long::sum,
        TreeMap::new
    ));

System.out.println(List.copyOf(totals.keySet()));
// [HN, UNKNOWN]
```

Nếu `"UNKNOWN"` có thể là mã vùng thật, hãy cân nhắc khóa kiểu riêng hoặc từ chối dữ liệu thiếu vùng, thay vì lặng lẽ nhập nhằng hai trường hợp. Việc chuẩn hóa chỉ đúng khi được nghiệp vụ cho phép.

### 10.3. Giá trị `null`

Đối với `Collectors.toMap` chuẩn, không nên truyền một `valueMapper` có thể trả `null`; các implementation JDK thông dụng ném `NullPointerException` thay vì lưu nó trong map. Hãy quy định rõ sẽ **bỏ bản ghi**, **thay thế** bằng giá trị mặc định hợp lệ hay **báo lỗi**.

```java
// Ví dụ: từ chối thiếu amount bằng cách validate trước:
record Payment(String id, Long amount) {}

List<Payment> payments = List.of(
    new Payment("P1", 10L),
    new Payment("P2", null)
);

// payments.stream().collect(Collectors.toMap(
//     Payment::id, Payment::amount, Long::sum, LinkedHashMap::new
// )); // NullPointerException trên JDK thông dụng.
```

Nếu tất cả bản ghi đều phải có số tiền, hãy báo lỗi tại bước tạo `Payment` hoặc validate tại ranh giới nguồn. Nếu dữ liệu thiếu có thể bỏ, `filter(payment -> payment.amount() != null)` là một lựa chọn tường minh trước `collect`.

## 11. Tính thay đổi được, sao chép và giữ thứ tự sau khi trả kết quả

`LinkedHashMap` và `TreeMap` thu được theo các ví dụ là **mutable**. Người gọi có thể `put`/`remove`, và điều đó có thể không phù hợp nếu đây là kết quả báo cáo đã chốt.

### 11.1. Tạo snapshot không thể sửa đổi nhưng giữ thứ tự

`Collections.unmodifiableMap` tạo **view không thể sửa đổi** của một map. Để bảo đảm không ai khác còn giữ tham chiếu map mutable và thay đổi thứ tự/nội dung bên dưới, hãy sao chép trước:

```java
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.Map;

LinkedHashMap<String, Long> mutable =
    OrderedRevenueDemo.totalsInSourceOrder(OrderedRevenueDemo.sample());

Map<String, Long> immutableSnapshot = Collections.unmodifiableMap(
    new LinkedHashMap<>(mutable)
);

System.out.println(List.copyOf(immutableSnapshot.keySet()));
// [HN, HCM, DN]
// immutableSnapshot.put("HP", 10L); // UnsupportedOperationException
```

Nếu dùng `Collections.unmodifiableMap(mutable)` **không sao chép**, một chỗ khác vẫn cầm biến `mutable` có thể thay đổi map bên dưới. Wrapper không biến bản gốc thành bất biến.

### 11.2. `Map.copyOf` và `Collectors.toUnmodifiableMap`

`Map.copyOf(source)` và `Collectors.toUnmodifiableMap` trả map không thể sửa đổi, nhưng **không bảo đảm giữ thứ tự duyệt khóa của `LinkedHashMap` nguồn**. Nếu thứ tự là một phần hợp đồng hiển thị, không dùng chúng rồi khẳng định `keySet()` sẽ được duyệt đúng thứ tự trước đó.

Với `TreeMap`, nếu cần snapshot **không thể sửa đổi và vẫn có thứ tự khóa**, có thể dùng:

```java
import java.util.Collections;
import java.util.SortedMap;
import java.util.TreeMap;

TreeMap<String, Long> sorted =
    OrderedRevenueDemo.totalsBySortedKey(OrderedRevenueDemo.sample());

SortedMap<String, Long> sortedSnapshot =
    Collections.unmodifiableSortedMap(new TreeMap<>(sorted));

System.out.println(List.copyOf(sortedSnapshot.keySet()));
// [DN, HCM, HN]
```

Các view không thể sửa đổi cũng không có nghĩa đối tượng **giá trị** bên trong map đều bất biến. Nếu value là `ArrayList` hoặc DTO mutable, phải tính đến việc sao chép sâu hoặc thiết kế kiểu giá trị bất biến.

## 12. Stream song song và giới hạn bảo đảm thứ tự

`LinkedHashMap` và `TreeMap` thông thường **không an toàn cho nhiều luồng cập nhật đồng thời**. Tuy nhiên, `Collectors.toMap(..., mapFactory)` và `groupingBy(..., mapFactory, downstream)` không phải collector concurrent mặc định: khi xử lý song song, framework có thể tạo các map tích lũy riêng và hợp nhất chúng bằng combiner.

```java
Map<String, Long> totals = OrderedRevenueDemo.sample()
    .parallelStream()
    .collect(Collectors.toMap(
        OrderedRevenueDemo.Order::region,
        OrderedRevenueDemo.Order::amountVnd,
        Long::sum,
        LinkedHashMap::new
    ));
```

Với `Long::sum` và các giá trị không tràn, tổng tiền theo từng khóa là phép tổng hợp không phụ thuộc thứ tự gộp. Tuy nhiên, để một báo cáo **bảo đảm thứ tự khóa theo lần gặp đầu trong nguồn**, cách rõ ràng nhất là dùng **ordered sequential stream** và `LinkedHashMap`, hoặc sắp kết quả theo tiêu chí xác định. Đừng tự mở rộng lời hứa thứ tự của một đoạn code tuần tự thành hợp đồng cho mọi collector/pipeline song song chưa được xác minh.

### 12.1. Không tráo `groupingBy` thành `groupingByConcurrent`

`Collectors.groupingByConcurrent` được thiết kế cho concurrent accumulation và có đặc tính `CONCURRENT`/`UNORDERED`; các map/concurrent accumulator phù hợp cho khả năng song song, **không thay thế** một cách trực tiếp nhu cầu giữ thứ tự insertion order bằng `LinkedHashMap`. Tương tự, `toConcurrentMap` không cung cấp thứ tự duyệt khóa theo lần xuất hiện của nguồn.

Khi yêu cầu thứ tự khóa là nghiệp vụ, tối ưu song song phải được đo và kiểm chứng riêng. Thông thường dữ liệu vừa phải, phép gộp đơn giản và yêu cầu thứ tự cao sẽ dễ bảo trì hơn nếu thu thập tuần tự.

### 12.2. Đừng dùng trạng thái dùng chung ngoài collector

Tránh:

```java
import java.util.LinkedHashMap;
import java.util.Map;

Map<String, Long> shared = new LinkedHashMap<>();
// Phản ví dụ:
// orders.parallelStream().forEach(order ->
//     shared.merge(order.region(), order.amountVnd(), Long::sum)
// );
```

`LinkedHashMap` không an toàn cho nhiều luồng ghi đồng thời. Cách dùng `collect` với supplier và combiner đúng hợp đồng giữ mutable state **bên trong collector**, thay vì để `forEach` sửa một map dùng chung.

## 13. Chi phí hiệu năng và bộ nhớ

### 13.1. `LinkedHashMap`

Chèn hoặc tra cứu khóa thường gần `O(1)` trung bình; thứ tự chèn được ghi nhận nhờ cấu trúc liên kết giữa các entry. So với map không lưu thứ tự, nó thường cần thêm bộ nhớ cho thông tin liên kết. Duyệt các entry theo thứ tự chèn hữu ích cho báo cáo, nhưng không phải **sắp xếp** dữ liệu.

### 13.2. `TreeMap`

`TreeMap` dùng cấu trúc cây cân bằng, thao tác tìm/chèn/xóa thường `O(log n)`. Nó cung cấp các thao tác theo khoảng khóa như `subMap`, `headMap`, `tailMap`, `firstKey`, `lastKey`. Nếu thường xuyên cần tra cứu và duyệt theo khóa, việc duy trì thứ tự trong map có thể thuận tiện hơn việc liên tục chuyển map sang danh sách rồi sắp xếp.

### 13.3. `sorted` trước `LinkedHashMap`

Pipeline `stream.sorted(...).collect(toMap(..., LinkedHashMap::new))` có thể phải giữ và sắp toàn bộ các phần tử nguồn trước khi thu; chi phí thường khoảng `O(n log n)` cho sắp xếp, với chi phí bộ nhớ trung gian tùy thực thi. Nếu chỉ cần các **khóa kết quả được sắp** và số khóa nhỏ hơn nhiều số phần tử, `TreeMap` ở collector thường trực tiếp hơn.

### 13.4. Grouping nhiều phần tử

`groupingBy(..., toList())` giữ tất cả phần tử của từng nhóm và có thể tốn nhiều bộ nhớ. Nếu chỉ cần `count` hoặc `sum`, hãy dùng downstream `counting()` hoặc `summingLong()` để lưu trạng thái nhỏ hơn. Nếu nguồn là stream I/O từ `Files.lines`, cần đóng nguồn bằng `try-with-resources` dù terminal operation là `collect`; chi phí bộ nhớ của kết quả là một vấn đề riêng.

**Tối ưu hóa dựa trên số đo.** Nếu yêu cầu đồng thời nhiều phần tử, comparator đắt hoặc khóa có tần suất lặp cao, hãy benchmark bằng dữ liệu đại diện thay vì giả định `LinkedHashMap` luôn nhanh hơn `TreeMap`. Mục tiêu đầu tiên là hợp đồng đầu ra đúng.

## 14. Kiểm thử thứ tự khóa, khóa trùng và dữ liệu biên

Với JUnit 5, kiểm thử cả **giá trị** lẫn **thứ tự khóa**. Ví dụ sử dụng lớp `OrderedRevenueDemo` ở mục 4:

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.TreeMap;
import org.junit.jupiter.api.Test;

class OrderedRevenueDemoTest {

    @Test
    void linkedHashMapKeepsFirstKeyEncounterOrder() {
        LinkedHashMap<String, Long> actual =
            OrderedRevenueDemo.totalsInSourceOrder(
                OrderedRevenueDemo.sample()
            );

        assertEquals(List.of("HN", "HCM", "DN"),
            List.copyOf(actual.keySet()));
        assertEquals(150_000L, actual.get("HN"));
        assertEquals(3, actual.size());
    }

    @Test
    void treeMapSortsByKeyNotBySourceOrder() {
        TreeMap<String, Long> actual =
            OrderedRevenueDemo.totalsBySortedKey(
                OrderedRevenueDemo.sample()
            );

        assertEquals(List.of("DN", "HCM", "HN"),
            List.copyOf(actual.keySet()));
        assertEquals(50_000L, actual.get("DN"));
    }

    @Test
    void mapEqualityDoesNotTestIterationOrder() {
        var sample = OrderedRevenueDemo.sample();
        var insertion = OrderedRevenueDemo.totalsInSourceOrder(sample);
        var sorted = OrderedRevenueDemo.totalsBySortedKey(sample);

        assertEquals(insertion, sorted);
        // Nhưng keySet() có thứ tự khác nhau:
        assertTrue(!List.copyOf(insertion.keySet())
            .equals(List.copyOf(sorted.keySet())));
    }

    @Test
    void emptySourceReturnsRequestedMapType() {
        var empty = List.<OrderedRevenueDemo.Order>of();

        assertTrue(OrderedRevenueDemo.totalsInSourceOrder(empty).isEmpty());
        assertTrue(OrderedRevenueDemo.totalsBySortedKey(empty).isEmpty());
    }

    @Test
    void duplicateKeyChangesValueNotFirstPosition() {
        var source = OrderedRevenueDemo.sample();
        var map = OrderedRevenueDemo.totalsInSourceOrder(source);

        assertEquals(List.of("HN", "HCM", "DN"),
            List.copyOf(map.keySet()));
        assertEquals(120_000L + 30_000L, map.get("HN"));
    }
}
```

**Các trường hợp nên bổ sung:** khóa thường/viết hoa với comparator case-insensitive, nguồn có phần tử `null`, giá trị mapper trả `null`, dữ liệu rỗng sau `filter`, thứ tự khóa sau `sorted`, merge function giữ đầu/giữ cuối, comparator không nhất quán với equals, tính có thể sửa đổi của map kết quả, và chính sách tràn số.

**Không dùng duy nhất `assertEquals(map1,map2)` để kiểm tra thứ tự duyệt**, vì hai map có thể bằng nhau dù một map giữ insertion order và map kia có sorted order. Không kiểm thử số lần hoặc lịch chạy của combiner để suy luận thứ tự song song.

## 15. Bài tập thực hành

### Bài 1 — Giữ thứ tự vùng xuất hiện

Cho:

```java
record Sale(String region, long amount) {}
List<Sale> sales = List.of(
    new Sale("HCM", 10),
    new Sale("HN", 20),
    new Sale("HCM", 30),
    new Sale("DN", 40)
);
```

Viết `Collectors.toMap` bốn tham số dùng `LinkedHashMap::new` và `Long::sum` để nhận `[HCM, HN, DN]` khi duyệt khóa, với tổng `HCM = 40`. Thử thêm một giao dịch `HN` cuối nguồn và chứng minh vị trí khóa `HN` không thay đổi.

### Bài 2 — Nhóm và sắp theo khóa

Từ `sales` ở Bài 1, dùng `Collectors.groupingBy(Sale::region, TreeMap::new, Collectors.counting())`. Kiểm tra thứ tự `[DN, HCM, HN]` và kết quả `HCM = 2`.

### Bài 3 — Chọn merge policy

Giả sử dữ liệu cấu hình có ba bản ghi `("timeout",10)`, `("retries",2)`, `("timeout",30)`. Thu vào `LinkedHashMap` theo ba chính sách: giá trị đầu thắng, giá trị cuối thắng, và báo lỗi khi có khóa trùng. Giải thích tại sao giá trị cuối thắng không đổi vị trí `timeout`.

### Bài 4 — Comparator bất thường

Tạo `TreeMap<String,Integer>` với `String.CASE_INSENSITIVE_ORDER`; lần lượt `put("hn",1)`, `put("HN",2)`. Dự đoán kích thước map rồi giải thích vì sao comparator có ảnh hưởng đến việc nhận diện **khóa bằng nhau**. Đề xuất thiết kế chuẩn hóa mã vùng để tránh nhập nhằng.

### Bài 5 — Sắp theo giá trị

Từ map doanh thu vùng, sắp giảm dần theo doanh thu, phá hòa bằng mã vùng tăng dần rồi thu vào `LinkedHashMap`. Giải thích vì sao thay map đích bằng `TreeMap` sẽ phá thứ tự theo giá trị.

### Bài 6 — Map rỗng và dữ liệu thiếu

Cho nguồn rỗng, kiểm tra loại map được factory tạo. Thêm một dòng có `region == null`, chọn một chính sách báo lỗi hoặc map vào `UNKNOWN`, rồi giải thích vì sao không nên tự cho rằng mọi collector đều hỗ trợ null key.

### Bài 7 — Song song

So sánh kết quả tổng tiền giữa `stream()` và `parallelStream()` với merge `Long::sum`. Phân tích rõ **giá trị theo khóa** và **thứ tự duyệt khóa** là hai yêu cầu độc lập; nếu thứ tự bắt buộc, đề xuất giải pháp tuần tự hoặc một bước sắp kết quả tường minh và đo chi phí thực tế.

## 16. Bảng quyết định

| Cần gì? | Lựa chọn thường phù hợp |
| --- | --- |
| Map từ phần tử, khóa **duy nhất** | `toMap(keyMapper, valueMapper)` nếu không yêu cầu loại map cụ thể |
| Map có thể trùng khóa, cần cộng dồn | `toMap(key, value, merge, mapFactory)` |
| Thứ tự khóa theo **lần xuất hiện đầu** | `LinkedHashMap::new` trên stream tuần tự có encounter order |
| Thứ tự khóa **tăng dần theo comparator** | `TreeMap::new` hoặc supplier tạo TreeMap với comparator |
| Thứ tự khóa giảm dần | `() -> new TreeMap<>(Comparator.reverseOrder())` |
| Map nhóm giữ các phần tử theo từng khóa | `groupingBy(classifier, LinkedHashMap::new, toList())` |
| Map nhóm sắp khóa và đếm | `groupingBy(classifier, TreeMap::new, counting())` |
| Sắp **giá trị** giảm dần | Sắp `entrySet().stream()` theo value rồi thu vào `LinkedHashMap` |
| Không chấp nhận khóa trùng | Merge function ném lỗi |
| Giá trị thiếu hoặc khóa null | Validate, lọc hoặc chuẩn hóa theo chính sách tường minh |
| Kết quả cần không thể sửa đổi nhưng vẫn có thứ tự | Bản sao `LinkedHashMap`/`TreeMap` + wrapper unmodifiable tương ứng |
| Muốn dùng concurrent collector | Đọc kỹ `CONCURRENT`/`UNORDERED` và từ bỏ giả định insertion order nếu không được cam kết |

`LinkedHashMap` và `TreeMap` giải quyết **hai kiểu thứ tự khác nhau** khi thu thập dữ liệu bằng Java Stream API: một kiểu giữ lần chèn khóa, một kiểu duy trì so sánh khóa. Khi kết hợp `mapFactory` với `toMap` hoặc `groupingBy`, hãy xác định cả chính sách khóa trùng, tính hợp lệ của khóa/giá trị, thứ tự thực của nguồn và yêu cầu về khả năng sửa đổi. Làm rõ các hợp đồng đó sẽ giúp báo cáo, phép nhóm và collector tùy chỉnh đúng ngữ nghĩa, dễ kiểm thử và có cơ sở để tối ưu hiệu năng.
