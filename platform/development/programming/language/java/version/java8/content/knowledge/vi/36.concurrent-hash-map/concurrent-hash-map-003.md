# `forEach`, `search` và `reduce` trên ConcurrentHashMap (Java 8+)

> **Chủ đề:** ConcurrentHashMap. Bài học hướng dẫn các phép xử lý hàng loạt (*bulk operations*) hiện hành của `java.util.concurrent.ConcurrentHashMap`: `forEach` để duyệt, `search` để tìm một kết quả, `reduce` để gộp dữ liệu, cùng biến thể `Keys`, `Values`, `Entries` và phép reduce primitive. Những API này đã xuất hiện từ Java 8 và vẫn được duy trì trên JDK hiện đại.

## 1. Mục tiêu

Sau bài này, bạn sẽ biết cách: chọn bulk `forEach` thay cho `Map.forEach` khi cần điều khiển ngưỡng phân chia; dùng `search` với quy ước **non-null = tìm thấy**; dùng `reduce` với hàm kết hợp associative/commutative; xử lý `null` như tín hiệu lọc trong transformer; chọn `parallelismThreshold`; tránh side effect không thread-safe; hiểu weak consistency và không coi bulk scan là snapshot giao dịch; và kiểm chứng chương trình Java chạy thật có các trường hợp map rỗng.

## 2. Nền tảng ConcurrentHashMap

`ConcurrentHashMap<K,V>` hỗ trợ nhiều thread đọc/cập nhật đồng thời mà không cần khóa cả map cho mọi thao tác. Một số operation đơn lẻ như `get`, `put`, `replace`, `compute` và `merge` có hợp đồng concurrency riêng. Tuy nhiên, **một phép duyệt/tổng hợp toàn map không tự động là một transaction atomic**.

```java
ConcurrentHashMap<String, Integer> map = new ConcurrentHashMap<>();
map.put("alpha", 10);
map.put("beta", 20);
map.put("gamma", 30);
map.put("delta", 40);
```

Các kiểm thử có expected output chính xác bên dưới sử dụng **map không thay đổi trong thời gian chạy bulk operations**. Điều này quan trọng: nếu một writer đồng thời thêm/xóa/sửa, kết quả duyệt có thể phản ánh trạng thái trộn của nhiều thời điểm.

### 2.1. Không có null key hoặc null value

`ConcurrentHashMap` không cho phép key hay value bằng `null`. Nhờ đó, bulk `search` và các mapped reductions có thể quy ước `null` là **không có đóng góp**.

```java
ConcurrentHashMap<String, Integer> values =
        new ConcurrentHashMap<>();

// values.put("missing", null); // NullPointerException.
```

Nếu ứng dụng cần biểu thị trạng thái “chưa có dữ liệu”, nên dùng một value object/enum có trạng thái rõ, không dùng `null` làm mapping hợp lệ. `get(key) == null` có nghĩa hiện không có mapping tại key ấy.

### 2.2. Weakly consistent, không phải snapshot

Các bulk operations có tính chất concurrency của `ConcurrentHashMap`: có thể tiến hành trong khi thread khác đang cập nhật. Nhưng **không đảm bảo toàn bộ các key/value được quan sát ở cùng một thời điểm**. Một phép reduce chạy giữa nhiều lần put/remove có thể phản ánh tổ hợp của các giá trị cũ và mới.

Một `get(key)` trả về non-null có quan hệ *happens-before* với việc chèn/cập nhật mapping liên quan; điều đó **không suy ra** một bulk operation có snapshot atomic toàn map. Với sổ cái tài chính, tổng tồn kho cần mốc chốt chuẩn hoặc logic đòi hỏi tính nhất quán giao dịch, phải chọn cơ chế đồng bộ/snapshot riêng phù hợp.

## 3. Tổng quan các nhóm bulk methods

| Công việc | Trên key-value | Trên key | Trên value | Trên entry |
| --- | --- | --- | --- | --- |
| Duyệt | `forEach` | `forEachKey` | `forEachValue` | `forEachEntry` |
| Tìm | `search` | `searchKeys` | `searchValues` | `searchEntries` |
| Gộp | `reduce` | `reduceKeys` | `reduceValues` | `reduceEntries` |
| Gộp kiểu primitive | `reduceToInt/Long/Double` | `reduceKeysTo...` | `reduceValuesTo...` | `reduceEntriesTo...` |

Tất cả các bulk methods này nhận `long parallelismThreshold` là tham số đầu tiên. Chúng không bảo đảm được chạy song song trong mọi trường hợp, và không tự tạo một snapshot của map.

### 3.1. `parallelismThreshold`

`parallelismThreshold` là ngưỡng kích thước map **ước tính** để xem xét phân chia phép toán thành subtasks:

- `Long.MAX_VALUE`: ngăn mọi phân chia song song của bulk operation.
- `1L`: cho phép phân chia song song tối đa theo cơ chế thực thi của thư viện.
- Một giá trị trung gian như `10_000L`: thử phân chia khi kích thước ước tính đủ lớn.

Đây **không phải số thread**, cũng không phải số phần tử cố định trên mỗi worker. Các bulk parallel operations dùng `ForkJoinPool.commonPool()`. Có thread cùng xử lý hay không còn tùy kích thước map, độ nặng callback, hệ thống và mức parallelism của pool. Với map nhỏ, chi phí scheduling có thể lớn hơn lợi ích; benchmark với dữ liệu/thao tác thực trước khi tối ưu.

## 4. forEach: duyệt mapping an toàn

Phân biệt hai overload:

```java
map.forEach((key, value) -> {
    // forEach từ Map, không nhận ngưỡng parallelism.
});

map.forEach(1L, (key, value) -> {
    // Bulk forEach từ ConcurrentHashMap, có threshold.
});
```

Chữ ký bulk:

```java
void forEach(long parallelismThreshold,
             BiConsumer<? super K, ? super V> action);
```

Callback nhận cả key và value; kết quả `void`. Bulk traversal **không bảo đảm thứ tự** chèn, thứ tự alphabet hoặc thứ tự giống kết quả `toString()`. Đừng cho rằng callback luôn chạy trên main thread hoặc chỉ một thread khi threshold là 1.

### 4.1. Đếm callback bằng LongAdder

```java
LongAdder counter = new LongAdder();
map.forEach(1L, (key, value) -> counter.increment());
long visited = counter.sum();
```

Snippet cần `java.util.concurrent.atomic.LongAdder`. Với map mẫu đứng yên, `visited == 4`. Nếu callback có thể chạy parallel, không dùng `int[] count={0}` rồi tăng `count[0]++` — thao tác đó có race. Nếu map đang thay đổi, số lượt duyệt không phải một count snapshot đáng tin.

### 4.2. forEach có transformer, null là “skip”

Overload có transformer:

```java
<U> void forEach(long parallelismThreshold,
        BiFunction<? super K, ? super V, ? extends U> transformer,
        Consumer<? super U> action);
```

Nếu transformer trả `null` thì action **không được gọi** đối với phần tử đó. Có thể lọc và biến đổi trước callback mà không cần tạo danh sách trung gian.

```java
Set<String> highKeys = ConcurrentHashMap.<String>newKeySet();
map.forEach(1L,
        (key, value) -> value >= 30 ? key : null,
        highKeys::add);
```

Tập kết quả gồm `delta` và `gamma`. `ConcurrentHashMap.newKeySet()` là tập phù hợp cho các callback có thể chạy song song. Để in kết quả có thứ tự **sau khi forEach trả về**, tạo `new TreeSet<>(highKeys)`; tuyệt đối không in ngay từ callback rồi assert thứ tự log.

### 4.3. forEachKey, forEachValue, forEachEntry

```java
map.forEachKey(1L, key -> {
    // Xử lý key.
});

map.forEachValue(1L, value -> {
    // Xử lý value.
});

map.forEachEntry(1L, entry -> {
    // entry.getKey(), entry.getValue().
});
```

Nhóm này có các overload transformer tương tự. Đối tượng `Map.Entry` trong bulk operations không hỗ trợ `setValue`; không dùng callback entry để thay mapping trực tiếp. Nếu muốn cập nhật giá trị theo key, hãy thiết kế một quy trình khác bằng atomic map methods như `compute` hoặc `merge`; không dựa vào quá trình duyệt bulk vừa đọc vừa sửa.

## 5. search: lấy một kết quả non-null

Chữ ký:

```java
<U> U search(long parallelismThreshold,
        BiFunction<? super K, ? super V, ? extends U> searchFunction);
```

`searchFunction` trả về:

- `null`: phần tử này không tạo kết quả; tiếp tục tìm.
- Một giá trị **không null**: một kết quả phù hợp; phép search có thể ngừng xử lý thêm và trả về giá trị.

```java
String found = map.search(1L,
        (key, value) -> value == 30 ? key : null);
// "gamma", vì điều kiện chỉ khớp một entry.

String missing = map.search(1L,
        (key, value) -> value > 100 ? key : null);
// null.
```

Nếu **nhiều** phần tử cùng phù hợp, kết quả được chọn có thể khác nhau theo lịch thực thi. `search` không hứa tìm giá trị đầu tiên theo thứ tự key, giá trị lớn nhất hay nhỏ nhất. Ngay cả khi tìm thấy, một số callback parallel có thể đã được bắt đầu; **không dùng callback search để thực hiện side effect đúng một lần**.

Nếu đã biết key, dùng `map.get(key)` thường phù hợp hơn. Nếu cần **tất cả** kết quả, dùng traversal/collect với cấu trúc đồng bộ phù hợp thay vì search (vì search chỉ trả một giá trị).

### 5.1. searchKeys, searchValues, searchEntries

```java
String foundKey = map.searchKeys(1L,
        key -> key.equals("alpha") ? key : null);

Integer foundValue = map.searchValues(1L,
        value -> value == 40 ? value : null);

String foundEntry = map.searchEntries(1L,
        entry -> entry.getValue() == 20
                ? entry.getKey() : null);
```

Trên map mẫu không thay đổi, kết quả tương ứng là `alpha`, `40` và `beta`. `searchEntries` nhận một entry giúp viết điều kiện kết hợp cả key/value. Null vẫn có nghĩa “không tìm thấy”.

## 6. reduce: gộp dữ liệu thành một kết quả

Một reduction có thể coi gồm hai bước: (1) chọn/biến đổi phần tử đóng góp, (2) gộp các đóng góp. Đối với parallel bulk reduction, reducer phải có tính:

- **Associative:** `combine(combine(a,b),c) == combine(a,combine(b,c))`.
- **Commutative:** `combine(a,b) == combine(b,a)`.

Không dùng phép trừ hoặc nối chuỗi phụ thuộc thứ tự làm reducer khi muốn kết quả xác định. Cộng số nguyên không tràn và min/max theo total order là lựa chọn đơn giản. Cần xử lý overflow cho tổng lớn và lưu ý cộng số thực floating-point không hoàn toàn associative do làm tròn.

### 6.1. reduceValues không có transformer

```java
Integer sum = map.reduceValues(1L, Integer::sum);
// 10 + 20 + 30 + 40 = 100.
```

Chữ ký object reduction cho value:

```java
V reduceValues(long parallelismThreshold,
               BiFunction<? super V, ? super V, ? extends V> reducer);
```

Không có thứ tự tích lũy cố định; chỉ dùng reducer độc lập với thứ tự. Với map rỗng, method này trả `null`, chứ không tự trả 0.

### 6.2. reduce(key,value) và lọc bằng null

```java
Integer sumAtLeast20 = map.reduce(
        1L,
        (key, value) -> value >= 20 ? value : null,
        Integer::sum);
// 20 + 30 + 40 = 90.
```

Chữ ký về mặt ý nghĩa:

```java
<U> U reduce(long parallelismThreshold,
        BiFunction<? super K, ? super V, ? extends U> transformer,
        BiFunction<? super U, ? super U, ? extends U> reducer);
```

Nếu transformer trả `null`, phần tử đó **không đóng góp** vào phép reduce. Với object reductions, `null` cũng là dấu hiệu **không có đóng góp nào**, ví dụ map rỗng hoặc toàn bộ mapping bị lọc.

### 6.3. reduceValues có transformer

```java
Integer highSum = map.reduceValues(
        1L,
        value -> value >= 30 ? value : null,
        Integer::sum);
// 30 + 40 = 70.
```

Nếu chỉ cần value, dùng `reduceValues` rõ mục đích hơn biến thể nhận cả key/value.

### 6.4. reduceKeys và reduceEntries

```java
String lexicographicSmallest = map.reduceKeys(
        1L,
        (left, right) -> left.compareTo(right) <= 0
                ? left : right);
// "alpha".
```

Với entries, lấy entry có value lớn nhất. Nếu có **giá trị bằng nhau**, phải xác định tie-break để reducer vẫn độc lập với thứ tự:

```java
Map.Entry<String, Integer> maxEntry = map.reduceEntries(1L,
        (a, b) -> {
            int c = Integer.compare(a.getValue(), b.getValue());
            if (c > 0) return a;
            if (c < 0) return b;
            return a.getKey().compareTo(b.getKey()) >= 0 ? a : b;
        });
// delta=40 trong map ví dụ.
```

Reducer chọn max theo cặp (value,key) là associative và commutative khi comparator nhất quán. Không gọi `setValue` trên entry kết quả của bulk operation.

## 7. Phép giảm dạng primitive và identity basis

Các dạng `reduceValuesToInt`, `reduceValuesToLong`, `reduceToLong`, `reduceEntriesToDouble`... nhận transformer kiểu primitive, `basis` và reducer.

```java
long totalLong = map.reduceValuesToLong(
        1L, Integer::longValue, 0L, Long::sum);
// 100.

long filteredLong = map.reduceToLong(
        1L,
        (key, value) -> value >= 20 ? value.longValue() : 0L,
        0L, Long::sum);
// 90.
```

`basis` phải là **identity** của reducer: nó có thể được sử dụng trong nhiều tác vụ con song song. Không suy luận rằng basis chỉ được cộng **một lần** ở đầu phép tính.

| Phép gộp | Basis đúng | Ví dụ sai |
| --- | --- | --- |
| Tổng `a+b` | 0 / 0L / 0.0 | 1 làm sai tổng |
| Tích `a*b` | 1 | 0 làm kết quả bằng 0 |
| Min | MAX_VALUE | 0 với giá trị toàn dương |
| Max | MIN_VALUE | 0 với giá trị toàn âm |

Với primitive transformer, **không có null**; khi cần bỏ qua phần tử trong phép cộng, trả identity (0). Với object reduction, trả `null` để bỏ qua. Với `double`, phép cộng floating-point có thể cho sai khác nhỏ do thứ tự gộp; không dùng nó làm tính toán tiền kế toán yêu cầu độ chính xác tuyệt đối.

### 7.1. Empty map: object và primitive khác nhau

```java
ConcurrentHashMap<String,Integer> empty =
        new ConcurrentHashMap<>();

Integer noValue = empty.reduceValues(1L, Integer::sum);
// null.

long zero = empty.reduceValuesToLong(
        1L, Integer::longValue, 0L, Long::sum);
// 0.
```

Đừng đồng nhất `null` với số 0 nếu chính sách nghiệp vụ cần phân biệt “không có bản ghi nào” và “tổng bằng 0”.


## 8. Chương trình Java 8 đầy đủ có tự kiểm tra

Ví dụ kết hợp đủ ba nhóm `forEach`, `search` và `reduce`, gồm biến thể xử lý key/value/entry, reduction primitive và map rỗng. Map **không bị ghi trong lúc bulk operation chạy**, nên các giá trị mong đợi ổn định. Do thứ tự callback không được bảo đảm, kết quả tập được sắp bằng `TreeSet` **sau khi forEach hoàn tất**. Hàm chọn max entry có tie-break theo key để không phụ thuộc vào thứ tự gộp.

Tạo file **`BulkMapDemo.java`** với nội dung sau:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.LongAdder;
import java.util.Set;
import java.util.TreeSet;
import java.util.Map;
import java.util.Arrays;

public class BulkMapDemo {
    public static void main(String[] args) {
        ConcurrentHashMap<String, Integer> map = new ConcurrentHashMap<>();
        map.put("alpha", 10);
        map.put("beta", 20);
        map.put("gamma", 30);
        map.put("delta", 40);

        LongAdder visits = new LongAdder();
        map.forEach(1L, (key, value) -> visits.increment());

        Set<String> highKeys = ConcurrentHashMap.<String>newKeySet();
        map.forEach(1L,
                (key, value) -> value >= 30 ? key : null,
                highKeys::add);

        String found = map.search(1L,
                (key, value) -> value == 30 ? key : null);
        String notFound = map.search(1L,
                (key, value) -> value > 100 ? key : null);
        String foundKey = map.searchKeys(1L,
                key -> key.equals("alpha") ? key : null);
        Integer foundValue = map.searchValues(1L,
                value -> value == 40 ? value : null);
        String foundEntry = map.searchEntries(1L,
                entry -> entry.getValue() == 20 ? entry.getKey() : null);

        Integer total = map.reduceValues(1L, Integer::sum);
        Integer subtotal = map.reduce(1L,
                (key, value) -> value >= 20 ? value : null,
                Integer::sum);
        Integer transformed = map.reduceValues(1L,
                value -> value >= 30 ? value : null,
                Integer::sum);
        long totalLong = map.reduceValuesToLong(1L,
                Integer::longValue, 0L, Long::sum);
        long filteredLong = map.reduceToLong(1L,
                (key, value) -> value >= 20 ? value.longValue() : 0L,
                0L, Long::sum);
        String lexicographicKey = map.reduceKeys(1L,
                (x, y) -> x.compareTo(y) <= 0 ? x : y);

        Map.Entry<String, Integer> maxEntry = map.reduceEntries(1L,
                (a, b) -> {
                    int byValue = Integer.compare(
                            a.getValue(), b.getValue());
                    if (byValue > 0) return a;
                    if (byValue < 0) return b;
                    return a.getKey().compareTo(b.getKey()) >= 0 ? a : b;
                });

        AtomicInteger keyVisits = new AtomicInteger();
        AtomicInteger valueVisits = new AtomicInteger();
        AtomicInteger entryVisits = new AtomicInteger();
        map.forEachKey(1L, key -> keyVisits.incrementAndGet());
        map.forEachValue(1L, value -> valueVisits.incrementAndGet());
        map.forEachEntry(1L, entry -> entryVisits.incrementAndGet());

        LongAdder sequentialVisits = new LongAdder();
        map.forEach(Long.MAX_VALUE,
                (key, value) -> sequentialVisits.increment());

        ConcurrentHashMap<String, Integer> empty =
                new ConcurrentHashMap<>();
        Integer emptyReduced = empty.reduceValues(1L, Integer::sum);
        long emptyPrimitive = empty.reduceValuesToLong(1L,
                Integer::longValue, 0L, Long::sum);

        System.out.println("forEach count: " + visits.sum());
        System.out.println("transformed forEach >=30: "
                + new TreeSet<>(highKeys));
        System.out.println("search value 30: " + found);
        System.out.println("search none: " + notFound);
        System.out.println("search keys/values/entries: "
                + foundKey + "/" + foundValue + "/" + foundEntry);
        System.out.println("reduceValues sum: " + total);
        System.out.println("reduce filtered >=20: " + subtotal);
        System.out.println("reduceValues filtered >=30: " + transformed);
        System.out.println("reduceValuesToLong sum: " + totalLong);
        System.out.println("reduceToLong filtered >=20: " + filteredLong);
        System.out.println("reduceKeys lexicographic min: " + lexicographicKey);
        System.out.println("reduceEntries max: " + maxEntry.getKey()
                + "=" + maxEntry.getValue());
        System.out.println("key/value/entry visits: "
                + keyVisits.get() + "/" + valueVisits.get()
                + "/" + entryVisits.get());
        System.out.println("threshold MAX visits: "
                + sequentialVisits.sum());
        System.out.println("empty object/primitive reduction: "
                + emptyReduced + "/" + emptyPrimitive);

        if (visits.sum() != 4
                || !highKeys.equals(new TreeSet<>(
                        Arrays.asList("gamma", "delta")))
                || !"gamma".equals(found) || notFound != null
                || !"alpha".equals(foundKey) || foundValue != 40
                || !"beta".equals(foundEntry)
                || total != 100 || subtotal != 90 || transformed != 70
                || totalLong != 100L || filteredLong != 90L
                || !"alpha".equals(lexicographicKey)
                || !"delta".equals(maxEntry.getKey())
                || maxEntry.getValue() != 40
                || keyVisits.get() != 4 || valueVisits.get() != 4
                || entryVisits.get() != 4
                || sequentialVisits.sum() != 4
                || emptyReduced != null || emptyPrimitive != 0L) {
            throw new AssertionError("Bulk operations mismatch");
        }
        System.out.println("Checks passed.");
    }
}
```

Biên dịch bằng JDK 17+ trong chế độ tương thích Java 8:

```bash
javac --release 8 BulkMapDemo.java
java BulkMapDemo
```

**Kết quả chạy thử trên OpenJDK 24:**


```text
forEach count: 4
transformed forEach >=30: [delta, gamma]
search value 30: gamma
search none: null
search keys/values/entries: alpha/40/beta
reduceValues sum: 100
reduce filtered >=20: 90
reduceValues filtered >=30: 70
reduceValuesToLong sum: 100
reduceToLong filtered >=20: 90
reduceKeys lexicographic min: alpha
reduceEntries max: delta=40
key/value/entry visits: 4/4/4
threshold MAX visits: 4
empty object/primitive reduction: null/0
Checks passed.
```

Mỗi dòng được in sau khi bulk operation tương ứng đã trả về; do đó output không phụ thuộc thứ tự callback. `LongAdder`/`AtomicInteger` an toàn khi callback chạy song song. `search` chỉ có một entry phù hợp cho mỗi điều kiện, tránh nondeterminism của nhiều kết quả cùng hợp lệ. Chương trình kiểm tra đầu ra bằng `AssertionError` khi sai, không dựa vào Java `assert` vốn có thể bị tắt.

## 9. Các lưu ý khi dùng trên map đang được cập nhật

### 9.1. Bộ đếm, tổng và tìm kiếm dưới concurrent writes

Giả sử thread A duyệt/tính tổng, còn thread B thực hiện:

```java
map.put("epsilon", 50);
map.remove("beta");
map.replace("gamma", 35);
```

Đây là **snippet minh họa**, không nên ghép trực tiếp vào đoạn kiểm thử deterministic bên trên. Trong tình huống thực, bulk operation có thể đã quan sát một số giá trị trước khi writer thay đổi và giá trị khác sau khi writer thay đổi. Kết quả **không bắt buộc** bằng tổng trước cập nhật hay tổng sau cập nhật.

Ngay cả `mappingCount()` hoặc `size()` khi concurrent writes cũng không nên được xem như snapshot giao dịch tuyệt đối cho logic kiểm toán. Nếu ứng dụng cần tính toán nhất quán tại một mốc, dùng đồng bộ hóa ở tầng nghiệp vụ, snapshot được xây an toàn hoặc lưu trữ hỗ trợ transaction; bản thân ConcurrentHashMap không cung cấp atomic whole-map scan.

### 9.2. Không sửa chính map trong callback bulk

Các bulk operations được thiết kế cho hàm thường **không phụ thuộc vào thứ tự** và **ít tác động trạng thái**. Việc callback sửa chính map khiến nội dung được duyệt và kết quả trở nên khó xác định, có thể tạo tranh chấp và lỗi nghiệp vụ. Nếu cần cập nhật theo key, dùng `compute`, `computeIfPresent` hoặc `merge` theo hợp đồng atomic của mỗi mapping, trong một quy trình riêng có thiết kế rõ ràng.

### 9.3. Search không có bảo đảm “chỉ một callback tìm thấy”

Khi nhiều kết quả có thể thỏa điều kiện, `search` chỉ **trả một** non-null result, nhưng nhiều lời gọi searchFunction vẫn có thể đã chạy trên các subtasks. Không gắn “gửi thông báo, trừ tiền, xóa dữ liệu” vào searchFunction vì muốn chỉ hành động trên một kết quả. Hãy tách bước lựa chọn và bước side effect, kèm kiểm tra lại điều kiện nếu dữ liệu có thể thay đổi.

### 9.4. Reduction phải đúng toán học

Không dùng reducer `(a,b)->a-b` hoặc `(a,b)->a+"/"+b` nếu muốn một kết quả độc lập với thứ tự song song. Khi cần max/min entry, đặt luật tie-break nhất quán. Với basis primitive, dùng **identity**, không phải một giá trị mặc định tùy ý. Với tiền tệ, không dùng `double` reduction để đòi hỏi khớp số lẻ tuyệt đối theo thứ tự; dùng đại diện tiền chính xác và cơ chế consistency phù hợp.

### 9.5. Hiệu năng không tự động tăng khi threshold nhỏ

Với bốn mapping và một callback chỉ tăng counter, tạo subtasks có thể đắt hơn duyệt tuần tự. `1L` trong demo nhằm **thực hành API parallel** chứ không phải khuyến nghị hiệu năng. Trên dữ liệu lớn, so sánh `Long.MAX_VALUE`, `1L` và một vài threshold trung gian bằng benchmark workload thực. Kiểm soát mức tải của `ForkJoinPool.commonPool` và tránh callback blocking I/O kéo dài nếu không có chiến lược concurrency riêng.

## 10. Sai lầm thường gặp

| Sai lầm | Hậu quả | Cách làm đúng |
| --- | --- | --- |
| Coi `forEach(1L,...)` luôn chạy đồng thời | Không có bảo đảm số thread thực tế | Dùng threshold để điều chỉnh, đo hiệu năng |
| Assert thứ tự của output callback | ConcurrentHashMap không có iteration order ổn định | Gom vào cấu trúc thread-safe, sort sau |
| Dùng `ArrayList.add` từ nhiều callback parallel | Race/corruption do ArrayList không thread-safe | Concurrent collection hoặc cách gộp an toàn |
| Tăng biến `int` bằng `count++` trong callback | Lost updates | `LongAdder` / `AtomicInteger` |
| Dùng search để trả bản ghi “đầu tiên” | Không có thứ tự xác định | Chọn bằng reducer/total order nếu cần |
| Dùng searchFunction có side effect | Có thể nhiều lời gọi đã chạy | Hàm tìm pure, side effect sau |
| Cho rằng search nhận null value trong map | ConcurrentHashMap cấm null value | Null chỉ là sentinel |
| Dùng phép trừ hoặc nối string trong parallel reduce | Kết quả phụ thuộc thứ tự | Associative + commutative reducer |
| Basis cho tổng là 1 | Basis có thể được áp dụng ở nhiều subtask | Dùng identity 0 |
| Dùng `reduceValues` trên map rỗng rồi unbox | Có thể NullPointerException | Kiểm tra null hoặc dùng primitive reduction |
| Giả định map không đổi suốt bulk traversal | Không có atomic snapshot khi writers chạy | Đồng bộ/snapshot ở tầng phù hợp |
| Gọi `entry.setValue` trong bulk entry operations | Không được hỗ trợ | Dùng atomic map update method riêng |
| Cho rằng `search` tự hủy công việc khác ngay lập tức | Callback khác có thể đã bắt đầu | Không dựa vào side effect/exactly-once |
| Mọi bản parallel nhanh hơn sequential | Overhead, contention/commonPool | Benchmark và chọn threshold |

## 11. Bài tập có đáp án

**Bài 1.** Đếm mapping của một map đứng yên bằng bulk `forEach` với threshold 1? — Dùng `LongAdder` trong `map.forEach(1L,(k,v)->adder.increment())`, đọc `adder.sum()` sau khi operation kết thúc.

**Bài 2.** Tìm key có value 30 trong map mẫu? — `map.search(1L,(k,v)->v==30?k:null)` trả `gamma`.

**Bài 3.** Nếu hai entry đều phù hợp với search, entry nào được trả? — Một kết quả non-null có sẵn; thứ tự không được bảo đảm.

**Bài 4.** Tính tổng value 10,20,30,40? — `map.reduceValues(1L,Integer::sum)` trả 100 khi map không thay đổi.

**Bài 5.** Chỉ cộng các value ≥ 20? — `map.reduce(1L,(k,v)->v>=20?v:null,Integer::sum)` trả 90; `null` bỏ phần tử trong object reduction.

**Bài 6.** Vì sao primitive reduce dùng basis 0 cho sum? — 0 là identity; basis có thể xuất hiện ở mỗi subtask và không được làm đổi tổng.

**Bài 7.** Kết quả `empty.reduceValues(1L,Integer::sum)` là gì? — `null`; còn primitive reduce cộng basis 0 cho 0.

**Bài 8.** Muốn max entry khi value bằng nhau thì sao? — Thêm tie-break theo key với comparator nhất quán để reducer associative/commutative.

**Bài 9.** `Long.MAX_VALUE` trong tham số threshold nghĩa là gì? — Ngăn chia parallel; nó **không** có nghĩa cần Long.MAX_VALUE thread.

**Bài 10.** Khi writer cập nhật trong lúc reduce, tổng có bắt buộc khớp một snapshot toàn map? — Không; cần nhất quán nghiệp vụ phải chọn giải pháp phối hợp riêng.

## 12. Tài liệu chính thức, còn áp dụng

- [Oracle Java SE 26 — ConcurrentHashMap](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentHashMap.html): hợp đồng bulk operations, `parallelismThreshold`, null filtering, các overload forEach/search/reduce, weak consistency và hạn chế `Map.Entry.setValue`.
- [Oracle Java SE 26 — LongAdder](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/atomic/LongAdder.html): counter hiệu quả trong cập nhật đồng thời.
- [Oracle Java SE 26 — ForkJoinPool](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ForkJoinPool.html): cơ chế thực thi song song và common pool.
- [Oracle Java SE 8 — ConcurrentHashMap](https://docs.oracle.com/javase/8/docs/api/java/util/concurrent/ConcurrentHashMap.html): xác nhận nhóm bulk operations đã có từ Java 8.

**Tóm tắt:** `forEach` duyệt không hứa thứ tự; `search` trả **một** kết quả non-null; `reduce` gộp dữ liệu với reducer độc lập thứ tự. Dùng đúng `parallelismThreshold`, null sentinel, identity basis và callback thread-safe. Khi map có concurrent writes, **không coi kết quả bulk là snapshot atomic**.
