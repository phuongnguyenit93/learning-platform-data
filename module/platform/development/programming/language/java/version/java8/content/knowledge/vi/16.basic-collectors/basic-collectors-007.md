# Map supplier và yêu cầu giữ thứ tự trong Java Stream Collectors

**Chủ đề cha:** Collector cơ bản. **Áp dụng:** các JDK hiện đại, bao gồm Java 17 trở lên. Các overload của `Collectors.toMap` và `Collectors.groupingBy` có map supplier đã tồn tại từ Java 8 và vẫn được hỗ trợ. Ví dụ đầy đủ dưới đây biên dịch bằng Java 17+; `record` và `List.of` chỉ là cú pháp dữ liệu mẫu hiện đại.

Mục tiêu của bài học là **chọn đúng loại Map trong quá trình collect** và diễn đạt chính xác điều kiện giữ thứ tự: thứ tự phần tử ở nguồn, thứ tự xuất hiện của key, thứ tự key được sắp xếp, hay thứ tự các phần tử bên trong từng nhóm.

## 1. Trước tiên, phân biệt các loại thứ tự

Giả sử nguồn dữ liệu là danh sách các giao dịch với mã nhóm theo thứ tự `B, A, B, C`.

| Yêu cầu nghiệp vụ | Thứ tự mong muốn | Cấu trúc phù hợp |
| --- | --- | --- |
| Duyệt các nhóm theo **lần đầu gặp key** | `B, A, C` | `LinkedHashMap` ở chế độ insertion order |
| Duyệt các nhóm **theo key tăng dần** | `A, B, C` | `TreeMap` |
| Duyệt key là enum theo **thứ tự khai báo enum** | Theo khai báo hằng enum | `EnumMap` |
| Giữ thứ tự các bản ghi **bên trong từng nhóm** | Ví dụ nhóm B có 20 rồi 30 | Downstream có thứ tự như `toList()` |
| Không quan tâm thứ tự | Không có thứ tự bắt buộc | Dùng collector mặc định hoặc map thích hợp khác |

Các khái niệm khác nhau:

- **Encounter order của Stream**: thứ tự logic các phần tử đi qua pipeline. Với `List.stream()`, thứ tự theo list; với nguồn như `HashSet`, không được mặc nhiên giả định có một encounter order xác định.
- **Iteration order của Map**: thứ tự `entrySet()`, `keySet()`, `forEach(...)` quan sát được. `LinkedHashMap` mặc định giữ thứ tự chèn key, `TreeMap` sắp xếp theo key; `HashMap` không cam kết thứ tự.
- **Order trong downstream collection**: `Map<String, List<T>>` vừa có thứ tự key ngoài vừa có thứ tự các phần tử trong `List` bên trong. `mapFactory` chỉ quyết định map ngoài.
- **Thứ tự khi xuất sang JSON/UI**: sau khi dữ liệu rời khỏi Java, cần kiểm tra serializer và phía nhận; iteration order của Java Map không tự cam kết hiển thị của mọi nền tảng.

**Điểm mấu chốt:** `LinkedHashMap` không sắp xếp key; nó ghi nhớ thứ tự key được chèn vào map. Nếu nguồn không có thứ tự xác định, việc dùng `LinkedHashMap` không tự tạo ra thứ tự nghiệp vụ có thể tái lập.

## 2. Map supplier là gì?

`Supplier<M>` là hàm không tham số tạo một đối tượng `M` mới. Trong Collector, `mapFactory` (thường được gọi là *map supplier*) chọn implementation của map **mà collector dùng để tích lũy kết quả**.

### 2.1. `Collectors.toMap` có map supplier

Dạng tổng quát:

```java
Collectors.toMap(
        keyMapper,       // Chuyển một phần tử T thành key K
        valueMapper,     // Chuyển một phần tử T thành value U
        mergeFunction,   // Xử lý khi nhiều phần tử cho cùng key
        mapFactory       // Tạo một Map<K, U> mới, rỗng
)
```

Ví dụ điển hình:

```java
Collectors.toMap(
        Sale::category,
        Sale::amount,
        Integer::sum,
        LinkedHashMap::new
)
```

`LinkedHashMap::new` tương đương một supplier tạo `new LinkedHashMap<>()`. Khi key đã tồn tại, `Integer::sum` cộng dồn giá trị; nếu dùng `toMap(keyMapper, valueMapper)` không có merge function mà gặp key trùng, quá trình collect ném `IllegalStateException`. **Không có overload ba tham số `(keyMapper, valueMapper, mapFactory)`**; muốn truyền map supplier vào `toMap`, cần đủ bốn tham số.

### 2.2. `Collectors.groupingBy` có map supplier

Dạng tổng quát:

```java
Collectors.groupingBy(
        classifier,      // T -> key nhóm K
        mapFactory,      // Supplier<M extends Map<K,D>>
        downstream       // Collector tạo giá trị D cho từng nhóm
)
```

Ví dụ:

```java
Collectors.groupingBy(
        Sale::category,
        LinkedHashMap::new,
        Collectors.counting()
)
```

`mapFactory` chọn map **chứa các key nhóm**; `downstream` quyết định mỗi key ánh xạ tới cái gì (list, tổng, số đếm, set...). Các overload `groupingBy(classifier)` và `groupingBy(classifier, downstream)` không cho điều khiển implementation của map bằng supplier.

### 2.3. Hợp đồng của supplier

- **Mỗi lần được gọi phải trả một map mới, rỗng, dùng được để thêm/gộp phần tử.** Collector có thể gọi supplier nhiều lần, nhất là khi gom từ parallel stream.
- **Không trả cùng một instance dùng chung**, như `() -> sharedMap`: container được dùng để tích lũy và kết hợp; tái sử dụng dẫn đến sai ngữ nghĩa, dễ gây race hoặc trộn dữ liệu.
- **Không trả map không sửa được** như `Map.of()` hoặc `Collections.emptyMap()`. Collector cần cập nhật các entry trong quá trình tính.
- Supplier không tự biến map thành thread-safe; `LinkedHashMap` và `TreeMap` vẫn là các map thông thường.

## 3. Ví dụ hoàn chỉnh: theo lần gặp key và theo key sắp xếp

Tạo file **`MapSupplierDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class MapSupplierDemo {
    record Sale(String category, int amount) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("B", 20),
                new Sale("A", 10),
                new Sale("B", 30),
                new Sale("C", 40)
        );

        LinkedHashMap<String, Integer> firstSeen = sales.stream()
                .collect(Collectors.toMap(
                        Sale::category,
                        Sale::amount,
                        Integer::sum,
                        LinkedHashMap::new
                ));
        System.out.println("First seen: " + firstSeen);

        TreeMap<String, Integer> sortedKeys = sales.stream()
                .collect(Collectors.toMap(
                        Sale::category,
                        Sale::amount,
                        Integer::sum,
                        TreeMap::new
                ));
        System.out.println("Sorted keys: " + sortedKeys);

        LinkedHashMap<String, List<Integer>> grouped = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::category,
                        LinkedHashMap::new,
                        Collectors.mapping(Sale::amount, Collectors.toList())
                ));
        System.out.println("Groups: " + grouped);

        LinkedHashMap<String, Long> counts = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::category,
                        LinkedHashMap::new,
                        Collectors.counting()
                ));
        System.out.println("Counts: " + counts);
    }
}
```

Chạy:

```bash
javac --release 17 MapSupplierDemo.java
java MapSupplierDemo
```

**Stdout chính xác:**

```text
First seen: {B=50, A=10, C=40}
Sorted keys: {A=10, B=50, C=40}
Groups: {B=[20, 30], A=[10], C=[40]}
Counts: {B=2, A=1, C=1}
```

Diễn giải:

1. `List` cung cấp encounter order `B → A → B → C`; `LinkedHashMap` chèn `B`, `A` rồi `C` theo lần xuất hiện đầu. Lần gặp `B` thứ hai làm giá trị `B` tăng từ 20 thành 50 nhưng **không chuyển key B xuống cuối**.
2. `TreeMap` nhận cùng các cặp dữ liệu nhưng duyệt key theo natural order `A, B, C`. Nó không quan tâm `B` xuất hiện trước.
3. `grouped` giữ thứ tự **key nhóm** theo lần gặp đầu và thứ tự **giá trị trong từng nhóm** theo nguồn: `B=[20, 30]`.
4. `counting()` là downstream đưa ra `Long`, vì vậy kiểu kết quả là `LinkedHashMap<String, Long>`. Supplier không quyết định kiểu giá trị đếm.

`toMap` không có supplier mặc định nào bảo đảm loại map hay iteration order. Khi thứ tự quan trọng, khai báo supplier tường minh; khi không cần giữ thứ tự, có thể chọn overload đơn giản hơn.

## 4. Tham chiếu nhanh: `LinkedHashMap`, `TreeMap`, `EnumMap`

| Loại map | Thứ tự iteration | Độ phức tạp / lưu ý | Khi dùng |
| --- | --- | --- | --- |
| `LinkedHashMap` | Theo insertion order ở constructor mặc định | Tra cứu/chèn trung bình gần `O(1)`; thêm bộ nhớ để lưu liên kết | Giữ thứ tự key lần đầu xuất hiện |
| `TreeMap` | Natural ordering hoặc `Comparator` | Các thao tác map cơ bản `O(log n)` | Key phải có thứ tự tăng/giảm rõ ràng |
| `EnumMap` | Theo thứ tự khai báo enum constants | Chỉ áp dụng cho key là enum; hiệu quả với số lượng key hữu hạn | Báo cáo theo mức ưu tiên/trạng thái cố định |
| `HashMap` | Không bảo đảm thứ tự | Phù hợp khi không cần thứ tự | Thu thập thông thường |

### 4.1. `LinkedHashMap`: insertion order khác access order

`LinkedHashMap::new` tạo map theo **thứ tự chèn key**. Việc cập nhật giá trị bằng `put`/`merge` trên key đã có không tự đổi vị trí key. Một constructor khác có tham số `accessOrder=true` sẽ tạo map theo thứ tự truy cập, và các thao tác truy cập/cập nhật có thể dịch chuyển entry; đây không phải lựa chọn khi mục tiêu là giữ thứ tự chèn ban đầu.

### 4.2. `TreeMap`: comparator quyết định tính duy nhất theo cách so sánh

`TreeMap::new` cần key có natural ordering. Nếu key là kiểu tùy chỉnh, truyền comparator khi tạo map:

```java
Collectors.toMap(
        item -> item,
        String::length,
        Integer::sum,
        () -> new TreeMap<>(String.CASE_INSENSITIVE_ORDER)
)
```

Đây là **đoạn biểu thức collector** dùng trong `stream.collect(...)` khi stream chứa `String`, không phải chương trình hoàn chỉnh. Với comparator không phân biệt hoa/thường, hai key `"java"` và `"JAVA"` có kết quả so sánh 0 và được `TreeMap` xem là một key logic. Vì vậy phải chọn comparator phản ánh đúng khái niệm key duy nhất; comparator không nhất quán với `equals` có thể khiến hành vi map khác với kỳ vọng thông thường về equality.

### 4.3. `EnumMap`: theo khai báo enum, không phải lần xuất hiện

Tạo file **`EnumMapDemo.java`**:

```java
import java.util.EnumMap;
import java.util.List;
import java.util.stream.Collectors;

public class EnumMapDemo {
    enum Priority { LOW, MEDIUM, HIGH }
    record Job(Priority priority, String title) {}

    public static void main(String[] args) {
        List<Job> jobs = List.of(
                new Job(Priority.HIGH, "Backup"),
                new Job(Priority.LOW, "Cleanup"),
                new Job(Priority.HIGH, "Deploy")
        );

        EnumMap<Priority, Long> counts = jobs.stream()
                .collect(Collectors.groupingBy(
                        Job::priority,
                        () -> new EnumMap<>(Priority.class),
                        Collectors.counting()
                ));
        System.out.println(counts);
    }
}
```

Chạy `javac --release 17 EnumMapDemo.java`, sau đó `java EnumMapDemo`:

```text
{LOW=1, HIGH=2}
```

Dù nguồn gặp `HIGH` trước, map duyệt `LOW` trước `HIGH` theo khai báo enum. `MEDIUM` không xuất hiện vì chưa có phần tử ở nhóm đó. `EnumMap` không cho key `null` và supplier cần chỉ rõ enum class khi khởi tạo map rỗng.

## 5. Xử lý key trùng mà vẫn giữ vị trí key

Đây là hai yêu cầu **độc lập**:

- Giá trị nào sẽ thắng khi nhiều phần tử có cùng key?
- Key đó nằm ở vị trí nào khi duyệt map?

Với `toMap` bốn tham số, `mergeFunction` xử lý câu hỏi thứ nhất; `mapFactory` quyết định câu hỏi thứ hai. Chính sách có thể là:

```java
(existing, incoming) -> existing  // Giữ giá trị đang có
(existing, incoming) -> incoming  // Lấy giá trị mới hơn
Integer::sum                      // Cộng tổng
```

Các biểu thức trên minh họa kiểu `BinaryOperator<U>`. Với stream **tuần tự có encounter order**, “đang có” và “mới hơn” tương ứng thứ tự phần tử được xử lý. Với parallel reduction, hàm gộp phải thỏa hợp đồng kết hợp và không dựa vào trạng thái chia sẻ; không suy luận thứ tự logic từ thời điểm thread hoàn thành.

Tạo file **`DuplicateKeyDemo.java`**:

```java
import java.util.LinkedHashMap;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class DuplicateKeyDemo {
    public static void main(String[] args) {
        LinkedHashMap<String, String> latest =
                Stream.of("A=old", "B=x", "A=new")
                        .collect(Collectors.toMap(
                                item -> item.substring(0, 1),
                                item -> item.substring(2),
                                (existing, incoming) -> incoming,
                                LinkedHashMap::new
                        ));
        System.out.println(latest);
    }
}
```

Chạy `javac --release 17 DuplicateKeyDemo.java` và `java DuplicateKeyDemo`:

```text
{A=new, B=x}
```

`A` vẫn đứng trước `B` vì đã chèn trước; giá trị thay từ `old` sang `new` theo merge policy. Nếu chỉ gọi `Collectors.toMap(k, v)` với hai phần tử `A`, sẽ có `IllegalStateException` vì duplicate key. Đừng dùng `LinkedHashMap` như một “cách sửa tự động” cho key trùng.

## 6. `groupingBy`: thứ tự map ngoài và cấu trúc downstream

Chọn `LinkedHashMap::new` trong `groupingBy` giữ thứ tự key nhóm theo trình tự được chèn; nhưng **không kiểm soát trực tiếp list/set bên trong nhóm**.

Các trường hợp thực tế:

- **Có thể có phần tử trùng và cần giữ đầy đủ:** `Collectors.toList()` hoặc `toCollection(ArrayList::new)`. Khi nguồn tuần tự có encounter order, mỗi list phản ánh thứ tự phần tử thuộc nhóm ở nguồn.
- **Muốn phần tử trong nhóm duy nhất nhưng vẫn giữ thứ tự:** `Collectors.toCollection(LinkedHashSet::new)` kết hợp với `mapping(...)` khi cần.
- **Chỉ cần đếm:** `Collectors.counting()`.
- **Chỉ cần tổng:** `Collectors.summingInt(...)`.
- **Cần map key theo thứ tự sắp xếp:** thay supplier map ngoài thành `TreeMap::new`.
- **Cần sắp xếp các phần tử bên trong nhóm:** sắp xếp nguồn theo comparator phù hợp trước collect, hoặc biến đổi từng nhóm sau collect; dùng `TreeSet` nếu nghiệp vụ chấp nhận loại phần tử trùng theo comparator.

Ví dụ **đoạn mã minh họa bên trong `MapSupplierDemo.main`**, dùng biến `sales` từ ví dụ ở mục 3:

```java
var uniqueAmounts = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::category,
                LinkedHashMap::new,
                Collectors.mapping(
                        Sale::amount,
                        Collectors.toCollection(java.util.LinkedHashSet::new)
                )
        ));
```

Kết quả là các key nhóm ở dạng insertion-ordered `LinkedHashMap`, còn mỗi nhóm chứa một `LinkedHashSet` giữ thứ tự giá trị lần đầu gặp và loại trùng theo equality. Không thay list bằng set nếu cần giữ tất cả dòng dữ liệu.

**Chú ý:** `groupingBy(classifier, toList())` chọn downstream list nhưng **không chỉ định mapFactory**. Việc map tình cờ in đúng một thứ tự ở máy của bạn không phải là cam kết API về iteration order của key.

## 7. Dữ liệu nguồn và yêu cầu bảo toàn thứ tự

### 7.1. Nguồn phải có encounter order rõ ràng

Với `List`, `stream()` duyệt theo encounter order của list. Với nguồn không có thứ tự xác định (như `HashSet`), map `LinkedHashMap` vẫn giữ **thứ tự được chèn**, nhưng thứ tự ấy có thể không khớp kỳ vọng và không ổn định. Gọi `unordered()` cũng cho phép pipeline bỏ qua ràng buộc encounter order.

Nếu nghiệp vụ muốn key theo tên tăng dần: dùng `TreeMap`. Nếu nghiệp vụ muốn key theo “thứ tự người dùng chọn”: ghi nhận thứ tự đó ở nguồn, chẳng hạn danh sách, rồi thu vào `LinkedHashMap`.

### 7.2. `sorted()` và `TreeMap` khác nhau

- `stream.sorted(comparator)` sắp xếp **các phần tử** trước collect; có thể làm thay đổi thứ tự giá trị trong các list nhóm và thứ tự key được gặp.
- `TreeMap` sắp xếp **các key trong map**; nó không tự thay đổi vị trí các đối tượng trong list downstream.
- `LinkedHashMap` nhận từ stream đã `sorted(...)` sẽ giữ thứ tự **key được chèn sau sắp xếp**, không phải thứ tự phần tử trước khi sắp xếp.

Nếu chỉ cần key được sắp xếp, `TreeMap` diễn đạt ý định trực tiếp hơn so với việc sắp xếp toàn bộ dữ liệu nguồn chỉ để đổi thứ tự key.

### 7.3. Parallel stream và tính xác định

`toMap`/`groupingBy` với mapFactory thông thường không phải concurrent collector: hệ thống có thể tạo nhiều map tạm rồi gọi combiner để hợp nhất. `LinkedHashMap::new` không có nghĩa “thread-safe map” và không biến `collect` thành phép chèn từ nhiều thread vào cùng một instance chia sẻ.

`groupingByConcurrent` và `toConcurrentMap` là các collector **unordered**; không phù hợp khi thứ tự key và thứ tự đưa phần tử xuống downstream là điều kiện bắt buộc. Với dữ liệu có thứ tự, collector thông thường có thể phải trả thêm chi phí phối hợp/merge khi xử lý song song. Nếu cần hiệu năng, hãy đo thực tế trước khi chọn parallel.

Không dùng `parallelStream().forEach(sharedLinkedHashMap::put)` để làm map có thứ tự: `forEach` trong parallel không cam kết thứ tự và map thường không an toàn khi nhiều luồng cùng sửa. Cũng không dùng thời gian hoàn thành tác vụ để suy ra encounter order.

## 8. Khi cần kết quả không sửa được nhưng vẫn giữ iteration order

`Collectors.toUnmodifiableMap(...)` (Java 10+), `Map.of(...)` và `Map.copyOf(...)` không cam kết iteration order. `Map.copyOf(linkedHashMap)` là cách sao chép nội dung sang map không sửa được, **không phải bảo đảm giữ thứ tự chèn**.

Nếu cần một snapshot độc lập, không cho thay đổi qua tham chiếu trả về nhưng vẫn duyệt key theo insertion order trong Java 17+, có thể dùng:

```java
Map<String, Integer> orderedReadOnly =
        java.util.Collections.unmodifiableMap(
                new java.util.LinkedHashMap<>(firstSeen)
        );
```

Đây là **đoạn mã trong `MapSupplierDemo.main`**, sử dụng biến `firstSeen` ở mục 3; cần import `java.util.Map` hoặc ghi đầy đủ tên kiểu. `new LinkedHashMap<>(firstSeen)` chụp một bản sao có thứ tự; `unmodifiableMap` tạo view không cho sửa qua biến kết quả. Nếu bỏ bước sao chép và dùng `unmodifiableMap(firstSeen)`, thay đổi qua tham chiếu mutable gốc vẫn có thể xuất hiện. Nếu value là một list/object mutable, wrapper **không làm value bất biến sâu**.

## 9. Lỗi thường gặp

1. **Dựa vào `HashMap` mặc định:** `toMap(keyMapper, valueMapper)` và `groupingBy(classifier)` không cam kết loại Map hoặc iteration order; cần supplier khi thứ tự là yêu cầu.
2. **Nhầm “insertion order” với “sorted order”:** `LinkedHashMap` theo chèn; `TreeMap` theo comparator. Thay đổi value không đồng nghĩa đổi vị trí key trong `LinkedHashMap` mặc định.
3. **Quên mergeFunction khi key trùng:** `toMap(k, v)` gây `IllegalStateException`; viết chính sách giữ/cộng/gộp rõ ràng.
4. **Đặt supplier sai vị trí:** `toMap` bốn đối số, `groupingBy` ba đối số khi có mapFactory.
5. **Tái sử dụng map có sẵn trong supplier:** có thể vi phạm yêu cầu container mới rỗng và gây race trong parallel.
6. **Dùng map unmodifiable để collect:** `Map.of()`/`emptyMap()` không cho thêm key.
7. **Giữ key đúng nhưng nhóm sai:** supplier quyết định map ngoài; downstream và encounter order quyết định giá trị trong nhóm.
8. **Đầu vào không có thứ tự nhưng yêu cầu kết quả ổn định:** xác định/sắp xếp thứ tự nguồn trước hoặc dùng sorted map.
9. **Bỏ qua quy tắc so sánh key của `TreeMap`:** comparator coi `compare(a,b)==0` là trùng key theo map; chọn comparator nhất quán với nghiệp vụ.
10. **Cho rằng `null` luôn được chấp nhận:** `groupingBy` không nhận classifier trả `null`; `toMap` có thể ném `NullPointerException` nếu mapped value là `null` do cơ chế merge, và `TreeMap`/`EnumMap` có hạn chế riêng. Làm sạch dữ liệu đầu vào.
11. **Giả định map có thứ tự sẽ giữ nguyên khi gọi `Map.copyOf` hoặc xuất JSON:** cần kiểm tra hợp đồng của phương thức và hệ thống nhận.
12. **Tưởng map supplier làm parallel collector thành concurrent:** loại map được chọn và đặc tính collector là hai điều độc lập.

## 10. Checklist chọn Collector có thứ tự

Trước khi viết một phép collect dùng map, xác định:

1. **Key nào, value nào?** Chọn `toMap` khi mỗi key nhận một giá trị kết hợp, hoặc `groupingBy` khi cần downstream xử lý từng nhóm.
2. **Muốn thứ tự gì?** First-seen → `LinkedHashMap`; key sorted → `TreeMap`; enum declaration → `EnumMap`.
3. **Nguồn có bảo đảm encounter order không?** Nếu không, không dựa vào insertion order để tạo thứ tự nghiệp vụ.
4. **Có key trùng không?** Với `toMap`, định nghĩa merge policy trước.
5. **Các phần tử trong mỗi nhóm cần giữ thứ tự hay tính duy nhất không?** Chọn đúng downstream list/set.
6. **Có cần biến kết quả thành chỉ đọc không?** Nếu vậy, bảo toàn thứ tự qua một bản sao `LinkedHashMap` và wrapper phù hợp, thay vì suy đoán `Map.copyOf` giữ thứ tự.
7. **Có chạy song song không?** Kiểm tra tính kết hợp của merger, đặc tính collector và chi phí; không chia sẻ map mutable bằng tay giữa thread.

## 11. Bài tập kiểm tra

1. Với danh sách có key `C, A, C, B`, `Collectors.toMap(..., Integer::sum, LinkedHashMap::new)` sẽ in key theo thứ tự nào? Khi thêm `C` lần hai, key C có đổi vị trí không?
2. Muốn map ngoài theo **key tăng dần** nhưng mỗi nhóm vẫn giữ bản ghi theo nguồn, nên truyền supplier và downstream nào vào `groupingBy`?
3. Tại sao `Collectors.groupingBy(type, LinkedHashMap::new, counting())` không có tham số merge function giống `toMap`?
4. Hai string khác nhau theo `equals` nhưng bằng nhau theo comparator của `TreeMap` sẽ được xử lý ra sao khi collect?
5. Nếu cần map không sửa được và vẫn giữ insertion order, vì sao `Map.copyOf` chưa đủ?

**Đáp án gợi ý:** (1) `C, A, B`; vị trí C không đổi trong insertion-order map. (2) `TreeMap::new` và `toList()`. (3) `groupingBy` tự tích lũy mỗi nhóm qua downstream. (4) `TreeMap` xem là cùng key theo comparator, phải có chính sách merge phù hợp. (5) API `Map.copyOf` không cam kết iteration order.

**Ghi nhớ:** `mapFactory` chọn **implementation và iteration semantics của Map**; thứ tự kết quả còn phụ thuộc **encounter order của nguồn**, **mergeFunction** và **downstream collector**. Biết rõ cần bảo toàn loại thứ tự nào trước khi chọn supplier.

## Tài liệu API chính thức

- `Collectors.toMap`, `Collectors.groupingBy`, `Collectors.groupingByConcurrent`: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html
- `LinkedHashMap` (insertion order/access order): https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/LinkedHashMap.html
- `TreeMap` và comparator: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/TreeMap.html
- `EnumMap` và enum declaration order: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/EnumMap.html
- `Map`, `Map.copyOf` và iteration order: https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html
