# LinkedHashMap theo insertion order hoặc access order

`LinkedHashMap` là một triển khai của `Map` giữ thứ tự duyệt ổn định. Trong Java 21, lớp này còn triển khai `SequencedMap`, vì vậy có thể đọc, duyệt ngược, lấy hoặc thay đổi vị trí mapping ở hai đầu mà không phải tự viết vòng lặp hay tạo một bản sao đảo ngược.

`LinkedHashMap` hỗ trợ hai chế độ thứ tự: *insertion order* (thứ tự chèn) và *access order* (thứ tự truy cập). Chế độ chèn phù hợp khi cần giữ trình tự thêm dữ liệu. Chế độ truy cập phù hợp khi thứ tự cần phản ánh mức độ được sử dụng gần đây, chẳng hạn trong một cache kiểu LRU. Java 21 bổ sung các API `SequencedMap` để thao tác rõ ràng với hai đầu và view đảo ngược của map.

## 1. LinkedHashMap và encounter order

`HashMap` không cam kết thứ tự duyệt. `LinkedHashMap` duy trì một danh sách liên kết kép đi qua các mapping; danh sách này xác định *encounter order* — thứ tự mà iterator, `forEach` và các collection view trả về phần tử.

Với constructor thông thường, thứ tự là insertion order:

```java
Map<String, Integer> scores = new LinkedHashMap<>();
scores.put("An", 8);
scores.put("Bình", 9);
scores.put("Chi", 7);

System.out.println(scores.keySet());
// [An, Bình, Chi]
```

Khi thêm một key đã tồn tại bằng `put`, giá trị được thay thế nhưng vị trí của key không đổi trong chế độ insertion order:

```java
scores.put("Bình", 10);

System.out.println(scores);
// {An=8, Bình=10, Chi=7}
```

Điểm khác biệt này hữu ích khi cần bảo toàn thứ tự nhập hoặc thứ tự cấu hình. Thứ tự không dựa trên phép so sánh key như `TreeMap`; nó phản ánh lịch sử sắp xếp của các mapping trong `LinkedHashMap`.

## 2. Insertion order và access order

### Insertion order — thứ tự chèn

Constructor mặc định tạo map theo insertion order:

```java
LinkedHashMap<String, Integer> map = new LinkedHashMap<>();
map.put("A", 1);
map.put("B", 2);
map.put("C", 3);

map.get("A");
map.put("B", 20);

System.out.println(map.keySet());
// [A, B, C]
```

Việc đọc `A` hoặc cập nhật giá trị của `B` không thay đổi thứ tự chèn. Nếu chèn lại một key đang có, mapping giữ vị trí cũ.

### Access order — thứ tự truy cập

Có thể bật access order bằng constructor ba tham số. Tham số cuối cùng `true` yêu cầu sắp xếp từ mapping ít được truy cập gần đây nhất ở đầu đến mapping được truy cập gần đây nhất ở cuối:

```java
LinkedHashMap<String, Integer> map =
        new LinkedHashMap<>(16, 0.75f, true);

map.put("A", 1);
map.put("B", 2);
map.put("C", 3);
System.out.println(map.keySet());
// [A, B, C]

map.get("A");
System.out.println(map.keySet());
// [B, C, A]

map.put("B", 20);
System.out.println(map.keySet());
// [C, A, B]
```

Trong chế độ này, truy cập một mapping đang tồn tại sẽ chuyển nó về cuối encounter order. Vì vậy, đầu map là ứng viên ít được sử dụng gần đây nhất, cuối map là ứng viên vừa được sử dụng gần đây nhất.

### Những thao tác nào được tính là access?

Với access-ordered `LinkedHashMap`, các thao tác sau tạo access cho mapping tương ứng nếu mapping còn tồn tại sau khi thao tác hoàn tất:

| Thao tác | Có tạo access? |
|---|---|
| `put`, `putIfAbsent` | Có |
| `get`, `getOrDefault` | Có |
| `compute`, `computeIfAbsent`, `computeIfPresent` | Có |
| `merge` | Có |
| `replace`, `replaceAll` | `replace` chỉ tạo access khi giá trị thực sự được thay thế; `replaceAll` không được liệt kê là thao tác access |
| `containsKey`, `containsValue` | Không |
| Duyệt `keySet`, `values`, `entrySet` hoặc các sequenced view | Không |
| `firstEntry`, `lastEntry`, `pollFirstEntry`, `pollLastEntry` | Không |
| `putFirst`, `putLast` | Không; đây là thao tác đặt vị trí tường minh |

`putAll` tạo một access cho mỗi mapping được xử lý, theo thứ tự iterator của `entrySet` của map nguồn. Các thao tác không nằm trong danh sách access của API không tự thay đổi thứ tự chỉ vì chúng đọc thông tin từ map.

Trong reversed view, access cũng được ghi nhận trên map nền. Do hướng encounter order đã đảo, một mapping được truy cập qua reversed view sẽ chuyển về đầu của view đảo, tương ứng với cuối của map gốc.

## 3. LinkedHashMap triển khai SequencedMap từ Java 21

Java 21 hoàn thiện Sequenced Collections theo JEP 431. `SequencedMap<K,V>` mở rộng `Map<K,V>` và mô tả map có encounter order xác định, hỗ trợ thao tác ở hai đầu và cung cấp view đảo ngược.

Có thể khai báo theo interface để thể hiện rõ nhu cầu về thứ tự:

```java
SequencedMap<String, Integer> scores = new LinkedHashMap<>();
scores.put("An", 8);
scores.put("Bình", 9);
scores.put("Chi", 7);
```

Những API chính của `SequencedMap`:

| API | Ý nghĩa |
|---|---|
| `firstEntry()` | Lấy mapping đầu tiên; trả `null` nếu map rỗng |
| `lastEntry()` | Lấy mapping cuối cùng; trả `null` nếu map rỗng |
| `pollFirstEntry()` | Xóa và trả mapping đầu tiên; trả `null` nếu map rỗng |
| `pollLastEntry()` | Xóa và trả mapping cuối cùng; trả `null` nếu map rỗng |
| `putFirst(key, value)` | Thêm hoặc cập nhật mapping và đặt nó ở đầu |
| `putLast(key, value)` | Thêm hoặc cập nhật mapping và đặt nó ở cuối |
| `reversed()` | Trả về view có encounter order ngược lại |
| `sequencedKeySet()` | View key có kiểu `SequencedSet` |
| `sequencedValues()` | View value có kiểu `SequencedCollection` |
| `sequencedEntrySet()` | View entry có kiểu `SequencedSet` |

Các thao tác đầu/cuối giúp tránh phải lấy iterator rồi gọi `next()` hoặc tự tìm phần tử cuối. Ví dụ:

```java
SequencedMap<String, Integer> scores = new LinkedHashMap<>();
scores.put("An", 8);
scores.put("Bình", 9);
scores.put("Chi", 7);

System.out.println(scores.firstEntry()); // An=8
System.out.println(scores.lastEntry());  // Chi=7

Map.Entry<String, Integer> oldest = scores.pollFirstEntry();
System.out.println(oldest);              // An=8
System.out.println(scores.keySet());     // [Bình, Chi]
```

`firstEntry()` và `lastEntry()` trả snapshot không hỗ trợ sửa mapping thông qua `setValue`. Hai phương thức `pollFirstEntry()` và `pollLastEntry()` xóa mapping khỏi map rồi trả snapshot tương ứng. Nếu map rỗng, cả bốn phương thức trả `null`.

## 4. Đặt mapping vào đầu hoặc cuối

`putFirst` và `putLast` vừa thêm/cập nhật mapping vừa xác định vị trí encounter order. Nếu key đã tồn tại, mapping được di chuyển đến vị trí được yêu cầu:

```java
LinkedHashMap<String, Integer> map = new LinkedHashMap<>();
map.put("A", 1);
map.put("B", 2);
map.put("C", 3);

map.putFirst("C", 30);
System.out.println(map); // {C=30, A=1, B=2}

map.putLast("A", 10);
System.out.println(map); // {C=30, B=2, A=10}
```

Đây là thao tác định vị tường minh, khác với access order. `putFirst` và `putLast` không được tính là access, kể cả khi map đang ở chế độ access order. Do đó, có thể dùng chúng khi cần sắp xếp vị trí mà không muốn thao tác được hiểu là một lần sử dụng gần đây.

`SequencedMap` là interface chung; không phải mọi implementation đều hỗ trợ định vị tùy ý. Ví dụ, map được sắp xếp theo comparator như `TreeMap` không thể tùy ý đặt một key lên đầu hoặc cuối mà vẫn giữ thứ tự so sánh, vì vậy các implementation đó có thể ném `UnsupportedOperationException` cho `putFirst`/`putLast`. `LinkedHashMap` hỗ trợ đầy đủ hai thao tác này.

## 5. View đảo ngược với reversed()

`reversed()` trả về một view có encounter order ngược với map gốc:

```java
LinkedHashMap<String, Integer> map = new LinkedHashMap<>();
map.put("A", 1);
map.put("B", 2);
map.put("C", 3);

SequencedMap<String, Integer> reverse = map.reversed();

System.out.println(map.keySet());
// [A, B, C]

System.out.println(reverse.keySet());
// [C, B, A]
```

Đây là view hai chiều gắn với map nền, không phải bản sao độc lập. Thay đổi qua view được ghi xuống map gốc và thay đổi trên map gốc được phản ánh trong view:

```java
reverse.put("D", 4);
System.out.println(map.keySet());
// [D, A, B, C]
System.out.println(reverse.keySet());
// [C, B, A, D]

reverse.putFirst("X", 24);
System.out.println(reverse.keySet());
// [X, C, B, A, D]
System.out.println(map.keySet());
// [D, A, B, C, X]
```

Trong reversed view, mọi thao tác có xét encounter order đều hoạt động theo hướng đã đảo. Vì vậy, `reverse.put("D", 4)` thêm mapping ở cuối view đảo, tức là đầu map gốc; `reverse.putFirst("X", 24)` đặt `X` ở đầu view đảo, tức là cuối map gốc. Có thể dùng `reversed()` để duyệt từ cuối về đầu mà không cần tạo `List` trung gian:

```java
for (Map.Entry<String, Integer> entry : map.reversed().entrySet()) {
    System.out.println(entry.getKey() + " = " + entry.getValue());
}
```

View đảo cũng có các collection view đảo tương ứng. Ví dụ `map.reversed().sequencedKeySet()` trả về các key theo thứ tự ngược của map gốc. Reversed view thường không serializable ngay cả khi map nền serializable; nếu cần lưu trữ, hãy tạo một map riêng theo thứ tự mong muốn.

## 6. Sequenced views của key, value và entry

Các phương thức `keySet()`, `values()` và `entrySet()` hiện có vẫn giữ encounter order khi duyệt, nhưng kiểu trả về của chúng lần lượt là `Set`, `Collection` và `Set`. Java 21 bổ sung các view có kiểu sequenced:

```java
LinkedHashMap<String, Integer> map = new LinkedHashMap<>();
map.put("A", 1);
map.put("B", 2);
map.put("C", 3);

SequencedSet<String> keys = map.sequencedKeySet();
SequencedCollection<Integer> values = map.sequencedValues();
SequencedSet<Map.Entry<String, Integer>> entries =
        map.sequencedEntrySet();

System.out.println(keys.getFirst());       // A
System.out.println(keys.getLast());        // C
System.out.println(values.getFirst());     // 1
System.out.println(entries.reversed());    // [C=3, B=2, A=1]
```

Các view này được backing bởi map. Xóa key hoặc entry khỏi view sẽ xóa mapping tương ứng khỏi map; thay đổi map cũng được phản ánh trong view. View không hỗ trợ `add`/`addAll` để tạo key hoặc value độc lập vì một mapping cần cả key lẫn value và phải được thêm thông qua map.

`sequencedKeySet()` và `sequencedEntrySet()` trả `SequencedSet`; `sequencedValues()` trả `SequencedCollection`. Những kiểu này cung cấp các thao tác đầu/cuối và `reversed()` phù hợp với encounter order. Nếu chỉ cần duyệt theo thứ tự hiện tại, các view Map cũ vẫn hợp lệ; dùng sequenced view khi cần biểu diễn hoặc thao tác thứ tự ở cấp kiểu.

## 7. Ứng dụng access order để xây dựng LRU cache đơn giản

LRU (Least Recently Used) loại bỏ mapping ít được truy cập gần đây nhất khi cache vượt quá dung lượng. Với access-order `LinkedHashMap`, mapping đầu tiên là ứng viên LRU; mỗi lần `get` thành công sẽ chuyển mapping được truy cập về cuối.

Ví dụ một cache nhỏ, giới hạn số mapping bằng cách xóa phần tử đầu sau khi thêm:

```java
final class LruCache<K, V> {
    private final int capacity;
    private final LinkedHashMap<K, V> entries =
            new LinkedHashMap<>(16, 0.75f, true);

    LruCache(int capacity) {
        if (capacity < 0) {
            throw new IllegalArgumentException("capacity must be >= 0");
        }
        this.capacity = capacity;
    }

    V get(K key) {
        return entries.get(key);
    }

    void put(K key, V value) {
        if (capacity == 0) {
            return;
        }

        entries.put(key, value);
        while (entries.size() > capacity) {
            entries.pollFirstEntry();
        }
    }

    int size() {
        return entries.size();
    }
}
```

Ở đây, `get` cập nhật access order; `pollFirstEntry` lấy và xóa ứng viên ít được dùng gần đây nhất. Đây là ví dụ cấu trúc LRU cơ bản, chưa có thời hạn hết hạn, tải dữ liệu khi miss, thống kê, hoặc đồng bộ hóa. `LinkedHashMap` không thread-safe; nếu cache được truy cập đồng thời, cần thiết kế đồng bộ phù hợp hoặc dùng một cache implementation hỗ trợ concurrency và chính sách eviction theo yêu cầu hệ thống.

## 8. Lưu ý về iterator, sửa đổi cấu trúc và hiệu năng

Trong insertion-order `LinkedHashMap`, chỉ thay đổi value của key đang tồn tại không làm thay đổi encounter order. Trong access-order map, thao tác `get` có thể di chuyển entry và vì vậy được xem là structural modification. Nếu đang duyệt bằng iterator rồi gọi `get` làm thay đổi thứ tự, iterator có thể ném `ConcurrentModificationException`.

```java
LinkedHashMap<String, Integer> map =
        new LinkedHashMap<>(16, 0.75f, true);
map.put("A", 1);
map.put("B", 2);
map.put("C", 3);

for (String key : map.keySet()) {
    // Có thể thay đổi encounter order và làm iterator fail-fast.
    map.get(key);
}
```

Không dựa vào `ConcurrentModificationException` để bảo đảm tính đúng đắn. Fail-fast chỉ là cơ chế phát hiện lỗi ở mức best-effort; nó không thay thế đồng bộ hóa khi có truy cập đồng thời. Nếu cần vừa duyệt vừa truy cập trong access-order map, hãy thiết kế thao tác sao cho không sửa thứ tự của map đang được duyệt, hoặc duyệt trên snapshot phù hợp.

`LinkedHashMap` có chi phí duy trì liên kết cao hơn `HashMap` một chút, nhưng duyệt collection view mất thời gian tỷ lệ với số mapping, không phụ thuộc capacity của bảng hash. Các thao tác cơ bản như `get`, `put` và `remove` có hiệu năng kỳ vọng hằng số khi hàm hash phân bố tốt. Chọn nó khi thứ tự duyệt là yêu cầu thực sự; nếu không cần encounter order, `HashMap` có thể phù hợp hơn.

## 9. Một số khác biệt cần nhớ

| Nhu cầu | Cách dùng |
|---|---|
| Giữ thứ tự thêm vào | `new LinkedHashMap<>()` |
| Đưa mapping được truy cập gần nhất về cuối | `new LinkedHashMap<>(capacity, loadFactor, true)` |
| Xem mapping đầu/cuối | `firstEntry()`, `lastEntry()` |
| Lấy và xóa mapping đầu/cuối | `pollFirstEntry()`, `pollLastEntry()` |
| Đưa mapping lên đầu/cuối | `putFirst(key, value)`, `putLast(key, value)` |
| Duyệt ngược | `reversed()` |
| Lấy view key/value/entry có thứ tự ở cấp kiểu | `sequencedKeySet()`, `sequencedValues()`, `sequencedEntrySet()` |
| Xây dựng cache LRU cơ bản | Access-order map và loại bỏ `pollFirstEntry()` khi vượt dung lượng |

Lưu ý thêm: `Map.equals()` và `hashCode()` vẫn dựa trên nội dung mapping, không dựa trên encounter order. Hai map có cùng cặp key/value vẫn có thể bằng nhau dù thứ tự duyệt khác nhau. Nếu thứ tự là một phần của hợp đồng dữ liệu, hãy kiểm tra thứ tự riêng thay vì chỉ dựa vào `equals()`.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 21 API — LinkedHashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html)
- [Oracle Java SE 21 API — SequencedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html)
- [Oracle Java SE 21 API — SequencedCollection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html)
- [Oracle Java SE 21 — Creating Sequenced Collections, Sets, and Maps](https://docs.oracle.com/en/java/javase/21/core/creating-sequenced-collections-sets-and-maps.html)
- [OpenJDK JEP 431 — Sequenced Collections](https://openjdk.org/jeps/431)
