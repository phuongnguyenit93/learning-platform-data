# SequencedMap và encounter order của các entry

Trong Java 21, `SequencedMap<K, V>` biểu diễn một map có thứ tự encounter xác định cho các mapping. Thứ tự này quy định entry nào được xem là đầu tiên, entry nào là cuối cùng và thứ tự các entry xuất hiện khi duyệt map. Nhờ hợp đồng này, chương trình có thể đọc, thêm, lấy ra hoặc duyệt mapping ở hai đầu mà không phải tự chuyển map thành list.

Encounter order không nhất thiết là thứ tự chèn. Nó phụ thuộc vào cách implementation tổ chức map: `LinkedHashMap` thường giữ thứ tự chèn (hoặc thứ tự truy cập nếu bật access-order), trong khi `TreeMap` giữ thứ tự theo comparator. `SequencedMap` chuẩn hóa cách làm việc với thứ tự đó qua một bộ API chung.

## 1. SequencedMap là gì?

`SequencedMap<K, V>` thuộc `java.util` và mở rộng `Map<K, V>`. Interface này bổ sung các thao tác để truy cập và thay đổi vị trí của mapping ở đầu hoặc cuối encounter order.

Các nhóm API quan trọng gồm:

| Nhóm | Phương thức | Ý nghĩa |
|---|---|---|
| Đọc đầu/cuối | `firstEntry()`, `lastEntry()` | Lấy mapping đầu tiên hoặc cuối cùng |
| Lấy và xóa đầu/cuối | `pollFirstEntry()`, `pollLastEntry()` | Lấy mapping ở đầu/cuối và loại bỏ nó khỏi map |
| Đặt mapping ở đầu/cuối | `putFirst(key, value)`, `putLast(key, value)` | Thêm hoặc cập nhật mapping tại vị trí đầu/cuối encounter order |
| View theo thứ tự | `sequencedKeySet()`, `sequencedValues()`, `sequencedEntrySet()` | Lấy các view có thứ tự tương ứng của key, value và entry |
| Đảo thứ tự | `reversed()` | Lấy view có encounter order ngược với map hiện tại |

Các phương thức này bổ sung cho những thao tác quen thuộc của `Map` như `get`, `put`, `remove`, `containsKey` và `entrySet`. Chúng không thay thế mô hình key-value hoặc quy tắc duy nhất của key.

## 2. Encounter order của entry

Encounter order là thứ tự các phần tử được gặp khi duyệt một collection hoặc view có thứ tự. Với `SequencedMap`, đối tượng được sắp thứ tự là các mapping (entry), mỗi mapping gồm một key và value.

Ví dụ, nếu map có thứ tự:

```text
first                                      last
  |                                          |
  v                                          v
 An=8  ->  Binh=9  ->  Chi=10  ->  Dung=7
```

Khi duyệt entry theo encounter order, chương trình gặp `An=8`, sau đó `Binh=9`, `Chi=10` và cuối cùng `Dung=7`. Từ cùng thứ tự đó:

- `firstEntry()` trả mapping `An=8`.
- `lastEntry()` trả mapping `Dung=7`.
- `sequencedKeySet()` duyệt các key theo thứ tự `An`, `Binh`, `Chi`, `Dung`.
- `sequencedValues()` duyệt các value theo thứ tự `8`, `9`, `10`, `7`.
- `sequencedEntrySet()` duyệt đầy đủ các cặp key-value theo thứ tự encounter.

Key trong map là duy nhất, nhưng value có thể trùng lặp. Vì thế, `sequencedValues()` có thể chứa các giá trị bằng nhau ở nhiều vị trí; thứ tự của chúng vẫn tương ứng với thứ tự các mapping trong map.

## 3. Implementation nào cung cấp encounter order?

`SequencedMap` là một hợp đồng về thứ tự, không phải một thuật toán sắp xếp duy nhất. Các implementation có thể xác định encounter order theo những quy tắc khác nhau.

### LinkedHashMap: thứ tự chèn hoặc thứ tự truy cập

`LinkedHashMap` triển khai `SequencedMap`. Ở chế độ mặc định, các mapping được duyệt theo thứ tự chèn:

```java
import java.util.LinkedHashMap;
import java.util.SequencedMap;

SequencedMap<String, Integer> scores = new LinkedHashMap<>();
scores.put("An", 8);
scores.put("Binh", 9);
scores.put("Chi", 10);

System.out.println(scores.firstEntry()); // An=8
System.out.println(scores.lastEntry());  // Chi=10
```

Nếu cập nhật value của một key đã có trong `LinkedHashMap` ở chế độ insertion-order, mapping đó vẫn ở vị trí chèn ban đầu. Nếu tạo `LinkedHashMap` với `accessOrder` là `true`, encounter order thay đổi theo lần truy cập và mapping được truy cập gần đây sẽ chuyển về cuối thứ tự:

```java
LinkedHashMap<String, Integer> cache =
        new LinkedHashMap<>(16, 0.75f, true);

cache.put("A", 1);
cache.put("B", 2);
cache.put("C", 3);

cache.get("A");

System.out.println(cache.keySet()); // [B, C, A]
```

Do đó, khi nói về encounter order của `LinkedHashMap`, cần xác định map đang dùng insertion-order hay access-order.

### TreeMap: thứ tự theo comparator

`SortedMap` mở rộng `SequencedMap`; vì vậy `TreeMap` cũng có encounter order. Thứ tự này được quyết định bởi natural ordering của key hoặc `Comparator` truyền vào, không phải thứ tự chèn:

```java
import java.util.SequencedMap;
import java.util.TreeMap;

SequencedMap<Integer, String> names = new TreeMap<>();
names.put(30, "Chi");
names.put(10, "An");
names.put(20, "Binh");

System.out.println(names.firstEntry()); // 10=An
System.out.println(names.lastEntry());  // 30=Chi
```

Mặc dù key `30` được thêm trước, nó vẫn nằm cuối vì thứ tự của `TreeMap` là tăng dần theo key. Các thao tác `putFirst` và `putLast` không thể ghi đè thứ tự do comparator quyết định; trên sorted map, các thao tác định vị này không được hỗ trợ và ném `UnsupportedOperationException`.

### HashMap không cam kết encounter order

`HashMap` chỉ cung cấp các thao tác map thông thường và không đảm bảo thứ tự duyệt ổn định. Nó không triển khai `SequencedMap`, nên không thể gọi các phương thức `firstEntry`, `putFirst` hoặc `reversed` thông qua hợp đồng sequenced.

Nếu yêu cầu nghiệp vụ phụ thuộc vào thứ tự đầu/cuối hoặc thứ tự duyệt, hãy chọn một implementation có hợp đồng thứ tự rõ ràng, ví dụ `LinkedHashMap` hoặc `TreeMap`, thay vì dựa vào thứ tự quan sát tình cờ từ `HashMap`.

## 4. Đọc mapping đầu tiên và cuối cùng

`firstEntry()` và `lastEntry()` đọc mapping ở hai đầu encounter order. Nếu map rỗng, cả hai trả về `null`.

```java
SequencedMap<String, Integer> stock = new LinkedHashMap<>();
stock.put("book", 12);
stock.put("pen", 30);
stock.put("paper", 50);

Map.Entry<String, Integer> first = stock.firstEntry();
Map.Entry<String, Integer> last = stock.lastEntry();

System.out.println(first.getKey());   // book
System.out.println(first.getValue()); // 12
System.out.println(last.getKey());    // paper
```

Các entry được trả về bởi `firstEntry()` và `lastEntry()` là snapshot của mapping tại thời điểm gọi, không phải entry có thể dùng `setValue()` để cập nhật map. Muốn thay đổi value, hãy gọi `put(key, newValue)` trên map.

Nên kiểm tra map rỗng hoặc kiểm tra kết quả `null` trước khi truy cập `getKey()` và `getValue()`:

```java
Map.Entry<String, Integer> firstEntry = stock.firstEntry();
if (firstEntry != null) {
    System.out.println(firstEntry.getKey());
}
```

Lưu ý rằng `null` trả về ở đây biểu thị map không có entry. Một implementation cho phép key có giá trị `null` vẫn có thể trả về một `Map.Entry` khác null, trong đó key của entry là null.

## 5. Lấy và xóa mapping ở hai đầu

`pollFirstEntry()` lấy mapping đầu tiên rồi xóa mapping đó khỏi map. `pollLastEntry()` làm tương tự với mapping cuối cùng. Nếu map rỗng, phương thức trả về `null`.

```java
SequencedMap<String, Integer> queue = new LinkedHashMap<>();
queue.put("job-1", 10);
queue.put("job-2", 20);
queue.put("job-3", 30);

Map.Entry<String, Integer> next = queue.pollFirstEntry();

System.out.println(next);  // job-1=10
System.out.println(queue); // {job-2=20, job-3=30}

Map.Entry<String, Integer> newest = queue.pollLastEntry();

System.out.println(newest); // job-3=30
System.out.println(queue);  // {job-2=20}
```

Các phương thức `pollFirstEntry()` và `pollLastEntry()` phù hợp khi cần xử lý hoặc loại bỏ phần tử ở hai đầu theo thứ tự đã xác định, ví dụ lấy công việc cũ nhất từ hàng đợi có thứ tự hoặc loại bỏ entry cuối khỏi cấu trúc dữ liệu có giới hạn.

Entry trả về là snapshot của mapping vừa bị lấy ra. Nếu map không hỗ trợ xóa, thao tác poll có thể ném `UnsupportedOperationException`; không nên giả định mọi `SequencedMap` đều có thể sửa đổi.

## 6. Đặt mapping ở đầu hoặc cuối với putFirst và putLast

`putFirst(key, value)` và `putLast(key, value)` đặt mapping tại đầu hoặc cuối encounter order. Nếu key đã tồn tại, mapping hiện có được cập nhật và chuyển đến vị trí được yêu cầu, thay vì tạo thêm một key trùng lặp.

```java
SequencedMap<String, Integer> priorities = new LinkedHashMap<>();
priorities.put("normal", 1);
priorities.put("low", 2);
priorities.put("urgent", 3);

priorities.putFirst("urgent", 10);

System.out.println(priorities.keySet()); // [urgent, normal, low]
System.out.println(priorities.get("urgent")); // 10

priorities.putLast("normal", 5);

System.out.println(priorities.keySet()); // [urgent, low, normal]
```

Lần gọi `putFirst` cập nhật value của `urgent` và đưa mapping lên đầu. Lần gọi `putLast` cập nhật `normal` và chuyển mapping đó xuống cuối. Mỗi key vẫn chỉ có một mapping.

Các thao tác định vị này là thao tác tùy chọn. Chúng có thể ném `UnsupportedOperationException` nếu implementation không hỗ trợ thay đổi vị trí tường minh hoặc không hỗ trợ sửa đổi. Ví dụ, sorted map phải tuân theo comparator nên không thể tùy ý đưa một key lên đầu hoặc cuối bằng `putFirst`/`putLast`.

## 7. Duyệt key, value và entry theo encounter order

`SequencedMap` cung cấp ba view có thứ tự:

- `sequencedKeySet()` trả về tập key theo encounter order của map.
- `sequencedValues()` trả về collection value theo encounter order tương ứng với mapping.
- `sequencedEntrySet()` trả về tập entry theo encounter order của map.

Các view này được map hỗ trợ. Thay đổi map sẽ được phản ánh khi duyệt view; các thao tác sửa đổi qua view cũng tác động đến map nếu implementation hỗ trợ thao tác đó.

```java
SequencedMap<String, Integer> inventory = new LinkedHashMap<>();
inventory.put("book", 5);
inventory.put("pen", 12);
inventory.put("ruler", 4);

for (String key : inventory.sequencedKeySet()) {
    System.out.println(key);
}

for (Integer quantity : inventory.sequencedValues()) {
    System.out.println(quantity);
}

for (Map.Entry<String, Integer> entry : inventory.sequencedEntrySet()) {
    System.out.println(entry.getKey() + ": " + entry.getValue());
}
```

`sequencedKeySet()` và `sequencedEntrySet()` giữ tính chất set: key và entry không bị lặp theo quy tắc của map. `sequencedValues()` là collection, không phải set, vì nhiều key có thể cùng ánh xạ tới một value.

Các phương thức `keySet()`, `values()` và `entrySet()` kế thừa từ `Map` vẫn có thể dùng cho những thao tác map thông thường. Khi chương trình cần biểu diễn rõ ràng rằng view phải hỗ trợ truy cập theo thứ tự đầu/cuối, hãy dùng các phương thức sequenced tương ứng.

## 8. reversed() và quan hệ giữa hai encounter order

`reversed()` trả về một `SequencedMap` view có encounter order đảo ngược so với map hiện tại. View chia sẻ mapping với map gốc; cập nhật hoặc xóa qua một phía được phản ánh ở phía còn lại.

```java
SequencedMap<String, Integer> scores = new LinkedHashMap<>();
scores.put("An", 8);
scores.put("Binh", 9);
scores.put("Chi", 10);

SequencedMap<String, Integer> reverseScores = scores.reversed();

System.out.println(reverseScores.firstEntry()); // Chi=10
System.out.println(reverseScores.lastEntry());  // An=8
```

Ở view đảo ngược, mapping đầu tiên là mapping cuối của map gốc. Vì đây là view, `putFirst` trên view tương ứng với việc đặt mapping ở cuối thứ tự của map gốc. Tương tự, `pollFirstEntry` trên view loại bỏ mapping cuối của map gốc.

Hai lần đảo khôi phục encounter order ban đầu về mặt quan sát. Không nên phụ thuộc vào việc hai lần gọi `reversed()` trả về đúng cùng một object theo phép so sánh `==`; hợp đồng cần quan tâm là thứ tự và mối quan hệ view với map nền.

## 9. Lưu ý về null, mutability và đồng bộ hóa

`SequencedMap` không áp đặt một chính sách null key hoặc null value chung cho mọi implementation. Khả năng chứa null phụ thuộc vào implementation cụ thể. Ví dụ, `LinkedHashMap` cho phép null key và null value; một số map khác từ chối chúng. Hãy kiểm tra hợp đồng của implementation đang dùng.

Khả năng sửa đổi cũng phụ thuộc implementation. Các map bất biến hoặc view không hỗ trợ sửa đổi có thể ném `UnsupportedOperationException` khi gọi `put`, `putFirst`, `pollFirstEntry` hoặc thực hiện thao tác xóa qua view. Các phương thức đọc như `firstEntry()` vẫn có thể dùng, nhưng cần xử lý trường hợp map rỗng.

`SequencedMap` không tự cung cấp thread safety. Nếu nhiều luồng truy cập và sửa map đồng thời, cần dùng cơ chế đồng bộ phù hợp với implementation và bảo đảm việc duyệt không bị ảnh hưởng bởi cập nhật không được phối hợp.

## 10. Khi nào nên dùng SequencedMap?

| Nhu cầu | Lợi ích của SequencedMap |
|---|---|
| Cần biết mapping đầu tiên/cuối cùng | Dùng `firstEntry()` và `lastEntry()` trực tiếp |
| Cần lấy và loại bỏ entry ở hai đầu | Dùng `pollFirstEntry()` và `pollLastEntry()` |
| Cần đưa mapping lên đầu hoặc cuối | Dùng `putFirst()` và `putLast()` nếu implementation hỗ trợ |
| Cần duyệt key, value hoặc entry theo cùng thứ tự | Dùng các sequenced views tương ứng |
| Cần xem map theo chiều ngược | Dùng `reversed()` |
| Thứ tự được quyết định bởi key sort | Dùng `SortedMap`/`TreeMap`, vốn cũng có hợp đồng sequenced |

Hãy chọn `SequencedMap` khi encounter order là một phần của logic nghiệp vụ hoặc thuật toán. Nếu thứ tự không quan trọng, một `Map` thông thường vẫn đủ. Nếu thứ tự có ý nghĩa, đừng dựa vào hành vi quan sát được của implementation không cam kết thứ tự.

## Kết luận

`SequencedMap` chuẩn hóa encounter order của các mapping và cung cấp API làm việc trực tiếp với entry đầu/cuối, các view có thứ tự và góc nhìn đảo ngược. `LinkedHashMap` thường thể hiện thứ tự chèn hoặc truy cập; `TreeMap` thể hiện thứ tự theo comparator. Khi chọn implementation, cần hiểu nguồn gốc encounter order, khả năng định vị mapping, mutability và chính sách null để thao tác với map đúng hợp đồng.

## Tài liệu tham khảo

- [Java SE 21 API — SequencedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html)
- [Java SE 21 API — SequencedCollection](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedCollection.html)
- [Java SE 21 API — LinkedHashMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/LinkedHashMap.html)
- [Java SE 21 API — SortedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedMap.html)
- [Java SE 21 API — TreeMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeMap.html)
- [JEP 431 — Sequenced Collections](https://openjdk.org/jeps/431)
