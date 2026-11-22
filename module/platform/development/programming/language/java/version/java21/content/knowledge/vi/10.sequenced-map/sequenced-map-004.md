# pollFirstEntry, pollLastEntry và thao tác lấy kèm xóa

`SequencedMap` trong Java 21 cung cấp hai phương thức `pollFirstEntry()` và `pollLastEntry()` để lấy một mapping ở đầu hoặc cuối encounter order đồng thời xóa mapping đó khỏi map. Mỗi phương thức trả về một `Map.Entry<K,V>` chứa key và value vừa bị xóa; nếu map rỗng, phương thức trả về `null`.

`SequencedMap` được bổ sung trong Java 21 để chuẩn hóa thao tác trên map có thứ tự. Các phương thức `firstEntry()`, `lastEntry()`, `pollFirstEntry()` và `pollLastEntry()` vốn đã có trong `NavigableMap`; Java 21 đưa chúng vào hợp đồng chung `SequencedMap` để các map có encounter order như `LinkedHashMap` cũng có thể cung cấp cùng nhóm thao tác ở hai đầu.

Hai phương thức này phù hợp khi cần xử lý lần lượt phần tử ở hai đầu của một map có thứ tự, chẳng hạn lấy công việc cũ nhất/mới nhất trong hàng đợi hoặc loại bỏ mapping ở đầu/cuối cache. Muốn dùng đúng, cần hiểu encounter order của implementation, trạng thái map sau thao tác, snapshot `Map.Entry` được trả về và cách phân biệt map rỗng với entry có value null.

## 1. Ý nghĩa của pollFirstEntry và pollLastEntry

Hai phương thức có cùng kiểu trả về và cùng quy tắc, chỉ khác vị trí được chọn:

```java
Map.Entry<K, V> pollFirstEntry();
Map.Entry<K, V> pollLastEntry();
```

| Phương thức | Mapping được chọn | Tác động lên map | Kết quả khi map rỗng |
|---|---|---|---|
| `pollFirstEntry()` | Mapping đầu tiên trong encounter order hiện tại | Xóa mapping đầu tiên rồi trả entry của mapping đó | Trả `null` |
| `pollLastEntry()` | Mapping cuối cùng trong encounter order hiện tại | Xóa mapping cuối cùng rồi trả entry của mapping đó | Trả `null` |

Tên `poll` thể hiện thao tác lấy kèm loại bỏ mapping. Sau khi gọi thành công, key của entry trả về không còn là key được lưu trong map do mapping tương ứng đã bị xóa. Phương thức không chỉ đọc entry như `firstEntry()` hoặc `lastEntry()`.

Các phương thức này là thao tác tùy chọn (*optional operation*). Nếu implementation không hỗ trợ xóa mapping, lời gọi có thể ném `UnsupportedOperationException`.

## 2. Ví dụ với LinkedHashMap

`LinkedHashMap` là implementation phổ biến của `SequencedMap`. Với constructor mặc định, encounter order là thứ tự thêm key vào map. `pollFirstEntry()` lấy mapping được thêm sớm nhất còn tồn tại; `pollLastEntry()` lấy mapping được thêm muộn nhất còn tồn tại.

```java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.SequencedMap;

public class PollEntriesExample {
    public static void main(String[] args) {
        SequencedMap<String, Integer> scores = new LinkedHashMap<>();
        scores.put("An", 8);
        scores.put("Binh", 9);
        scores.put("Chi", 10);

        Map.Entry<String, Integer> first = scores.pollFirstEntry();
        System.out.println(first.getKey() + " = " + first.getValue());
        System.out.println(scores); // {Binh=9, Chi=10}

        Map.Entry<String, Integer> last = scores.pollLastEntry();
        System.out.println(last.getKey() + " = " + last.getValue());
        System.out.println(scores); // {Binh=9}
    }
}
```

Kết quả theo thứ tự:

```text
An = 8
{Binh=9, Chi=10}
Chi = 10
{Binh=9}
```

Khai báo biến bằng interface `SequencedMap` giúp code phụ thuộc vào hợp đồng thao tác theo thứ tự. Implementation thực tế ở đây là `LinkedHashMap`, nhưng có thể thay bằng một implementation khác miễn là đáp ứng yêu cầu về encounter order và hỗ trợ xóa.

## 3. Encounter order phụ thuộc implementation

Không được mặc định rằng “first” luôn là key được thêm đầu tiên. `SequencedMap` định nghĩa first và last theo encounter order của map. Cách tạo ra thứ tự này phụ thuộc implementation:

| Implementation | Encounter order | `pollFirstEntry()` thường lấy |
|---|---|---|
| `LinkedHashMap` với insertion-order mặc định | Thứ tự thêm mapping | Mapping được thêm sớm nhất còn lại |
| `LinkedHashMap` với access-order | Từ ít được truy cập gần đây nhất đến được truy cập gần đây nhất | Mapping ít được truy cập gần đây nhất |
| `TreeMap` | Thứ tự key theo natural ordering hoặc comparator | Mapping có key nhỏ nhất theo thứ tự đó |
| `ConcurrentSkipListMap` | Thứ tự key theo comparator | Mapping có key nhỏ nhất theo thứ tự đó |

Với `TreeMap`, `pollLastEntry()` lấy mapping có key lớn nhất theo comparator. Với `LinkedHashMap`, nó lấy mapping cuối cùng trong encounter order hiện tại. Đây là lý do nên mô tả thao tác theo đầu/cuối của thứ tự, thay vì gắn ý nghĩa “nhỏ nhất/lớn nhất” hoặc “cũ nhất/mới nhất” cho mọi loại map.

### Lưu ý về LinkedHashMap access-order

`LinkedHashMap` có constructor cho phép bật access-order:

```java
LinkedHashMap<String, Integer> cache =
        new LinkedHashMap<>(16, 0.75f, true);

cache.put("A", 1);
cache.put("B", 2);
cache.put("C", 3);

cache.get("A");

Map.Entry<String, Integer> leastRecent = cache.pollFirstEntry();
System.out.println(leastRecent.getKey()); // B
System.out.println(cache);                // {C=3, A=1}
```

Sau `get("A")`, thứ tự truy cập chuyển thành `B`, `C`, `A`. Vì vậy, `pollFirstEntry()` lấy `B`, mapping ít được truy cập gần đây nhất. Mẫu này hữu ích khi quản lý cache theo chính sách LRU; nếu muốn tự triển khai chính sách cache hoàn chỉnh, vẫn cần xử lý giới hạn dung lượng, cập nhật truy cập và đồng bộ phù hợp.

## 4. So sánh với firstEntry và lastEntry

`SequencedMap` còn có `firstEntry()` và `lastEntry()`. Hai phương thức này chỉ đọc mapping ở hai đầu, không xóa mapping khỏi map.

```java
SequencedMap<String, Integer> map = new LinkedHashMap<>();
map.put("A", 1);
map.put("B", 2);

Map.Entry<String, Integer> observed = map.firstEntry();
System.out.println(observed); // A=1
System.out.println(map);      // {A=1, B=2}

Map.Entry<String, Integer> removed = map.pollFirstEntry();
System.out.println(removed);  // A=1
System.out.println(map);      // {B=2}
```

| Phương thức | Đọc mapping | Xóa mapping | Khi map rỗng |
|---|---:|---:|---|
| `firstEntry()` | Có | Không | `null` |
| `lastEntry()` | Có | Không | `null` |
| `pollFirstEntry()` | Có | Có | `null` |
| `pollLastEntry()` | Có | Có | `null` |

Cả bốn phương thức đều trả `Map.Entry` dạng snapshot tại thời điểm gọi. Entry trả về không phải view liên kết để thay đổi map. Phương thức `setValue()` trên entry này không được hỗ trợ và sẽ ném `UnsupportedOperationException`. Snapshot lưu cặp key/value tại thời điểm lấy; nếu value là một object mutable, bản thân object value vẫn có thể được thay đổi theo hành vi của class đó.

Do `firstEntry()` và `lastEntry()` cũng trả snapshot, không nên lấy entry bằng một trong hai phương thức rồi gọi `setValue()` với kỳ vọng cập nhật map. Nếu cần cập nhật mapping, dùng `put`, `replace` hoặc API cập nhật phù hợp của map.

## 5. Xử lý map rỗng và value null

`pollFirstEntry()` và `pollLastEntry()` trả `null` khi map rỗng. Nhưng một mapping hợp lệ có thể chứa value null nếu implementation cho phép. Vì vậy, phải kiểm tra chính đối tượng `Map.Entry` trả về, không kiểm tra `entry.getValue()` để kết luận map rỗng.

```java
SequencedMap<String, String> map = new LinkedHashMap<>();
map.put("no-description", null);

Map.Entry<String, String> removed = map.pollFirstEntry();

if (removed == null) {
    System.out.println("Map rỗng");
} else {
    System.out.println("Key: " + removed.getKey());
    if (removed.getValue() == null) {
        System.out.println("Mapping tồn tại nhưng value là null");
    }
}
```

`LinkedHashMap` cho phép null key và null value. Nếu implementation cho phép null key, entry trả về vẫn là một `Map.Entry` khác null dù `getKey()` trả null. Các implementation như `TreeMap` hoặc `ConcurrentSkipListMap` có quy tắc về null key riêng; cần xem hợp đồng của implementation và comparator đang dùng. Không suy ra mọi `SequencedMap` đều chấp nhận null key/value.

Quy tắc kiểm tra an toàn:

```java
Map.Entry<K, V> entry = map.pollFirstEntry();

if (entry == null) {
    // Không có mapping để lấy.
} else {
    K key = entry.getKey();
    V value = entry.getValue();
    // key hoặc value có thể null nếu implementation cho phép.
}
```

## 6. Dùng reversed để lấy từ đầu đối diện

`SequencedMap.reversed()` trả về view có encounter order đảo ngược. Vì vậy, first của reverse view chính là last của map ban đầu; tương tự, last của reverse view là first của map ban đầu.

```java
SequencedMap<String, Integer> map = new LinkedHashMap<>();
map.put("A", 1);
map.put("B", 2);
map.put("C", 3);

Map.Entry<String, Integer> fromOriginalLast =
        map.reversed().pollFirstEntry();

System.out.println(fromOriginalLast); // C=3
System.out.println(map);              // {A=1, B=2}
```

Với implementation hỗ trợ sửa đổi reverse view như `LinkedHashMap`, thao tác xóa trên view được ghi xuống map gốc. Cách này có thể hữu ích khi một thuật toán đang duyệt theo chiều đảo nhưng vẫn muốn dùng cùng thao tác `pollFirstEntry()`.

## 7. Xử lý hết các mapping ở một đầu

Có thể dùng `pollFirstEntry()` để lấy và xóa lần lượt tất cả mapping theo encounter order. Cần kiểm tra `null` ở entry trả về để dừng vòng lặp:

```java
static <K, V> void drainFromFront(SequencedMap<K, V> map) {
    Map.Entry<K, V> entry;

    while ((entry = map.pollFirstEntry()) != null) {
        process(entry.getKey(), entry.getValue());
    }
}

static <K, V> void process(K key, V value) {
    System.out.println(key + " -> " + value);
}
```

Sau vòng lặp, map đã rỗng nếu các lần poll hoàn tất bình thường. Nếu quá trình xử lý có thể thất bại, hãy quyết định rõ liệu mapping có được xóa trước khi xử lý hay không. `pollFirstEntry()` xóa mapping ngay khi trả entry; nếu `process` ném exception, mapping đó không tự động được đưa trở lại map.

Với `pollLastEntry()`, có thể xử lý theo thứ tự ngược từ cuối map. Lựa chọn đầu hay cuối cần phản ánh quy tắc nghiệp vụ, ví dụ FIFO thường lấy đầu, còn xử lý ưu tiên phần tử mới nhất có thể lấy cuối.

## 8. Khả năng thay đổi và an toàn luồng

`pollFirstEntry()` và `pollLastEntry()` là thao tác đọc kèm xóa, nhưng không nên suy ra rằng mọi `SequencedMap` đều an toàn khi nhiều thread cùng truy cập. `LinkedHashMap` không được đồng bộ hóa; nếu nhiều thread sửa cấu trúc map, ứng dụng phải tự đồng bộ hoặc chọn cấu trúc dữ liệu đồng thời phù hợp.

`ConcurrentSkipListMap` triển khai `SequencedMap` và cung cấp các thao tác poll theo thứ tự key trong môi trường concurrent. Nếu cần thao tác đồng thời, hãy dùng đúng hợp đồng concurrency của implementation thay vì bao một `LinkedHashMap` bằng các lời gọi riêng lẻ rồi giả định thao tác lấy và xóa sẽ trở thành atomic.

Ngoài ra, `SequencedMap` cho phép implementation không hỗ trợ một số thao tác tùy chọn. Với map chỉ đọc hoặc wrapper không cho phép xóa, `pollFirstEntry()` và `pollLastEntry()` có thể ném `UnsupportedOperationException`. Hãy xác nhận map được truyền vào có hỗ trợ removal trước khi dùng chúng như thao tác tiêu thụ dữ liệu.

## 9. Checklist sử dụng pollFirstEntry và pollLastEntry

- [ ] Kiểu map thực tế triển khai `SequencedMap`.
- [ ] Đã hiểu encounter order của implementation: insertion-order, access-order hay thứ tự theo comparator.
- [ ] Dùng `pollFirstEntry()` khi cần lấy và xóa mapping đầu; dùng `pollLastEntry()` cho mapping cuối.
- [ ] Kiểm tra `entry == null` để nhận biết map rỗng.
- [ ] Không dùng `entry.getValue() == null` để kết luận map rỗng.
- [ ] Đã kiểm tra implementation có hỗ trợ removal hay có thể ném `UnsupportedOperationException`.
- [ ] Không gọi `setValue()` trên entry snapshot trả về.
- [ ] Không giả định `LinkedHashMap` an toàn luồng khi có nhiều thread sửa map.
- [ ] Nếu dùng `reversed()`, đã xác định first/last của view tương ứng với đầu nào của map gốc.

## Tài liệu tham khảo

- [SequencedMap — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html): chữ ký, giá trị trả về, optional operation, snapshot entry và reverse-ordered view.
- [LinkedHashMap — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html): insertion-order, access-order, khả năng chứa null và hỗ trợ các thao tác `SequencedMap`.
- [Creating Sequenced Collections, Sets, and Maps — Java SE 21](https://docs.oracle.com/en/java/javase/21/core/creating-sequenced-collections-sets-and-maps.html): encounter order, reverse view và các phương thức lấy/xóa mapping ở hai đầu.
- [ConcurrentSkipListMap — Java SE 21 API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html): thao tác poll đầu/cuối theo thứ tự key trong map đồng thời.
