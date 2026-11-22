# ConcurrentSkipListMap và ConcurrentSkipListSet trong Java

Trong Java concurrency, không phải collection nào được nhiều thread truy cập cũng chỉ cần lưu và tìm kiếm phần tử. Một số nghiệp vụ còn cần **duy trì khóa được sắp xếp**, hỏi phần tử gần nhất, duyệt theo thứ tự hoặc làm việc với một **khoảng khóa** trong khi thread khác đang cập nhật. Hai cấu trúc thuộc `java.util.concurrent` giải quyết nhóm nhu cầu đó là:

- **`ConcurrentSkipListMap<K,V>`:** map concurrent **có thứ tự theo khóa**, triển khai các hợp đồng `ConcurrentNavigableMap`, `NavigableMap` và `SortedMap`; hỗ trợ tìm khóa trước/sau và range view.
- **`ConcurrentSkipListSet<E>`:** set concurrent **có thứ tự phần tử**, triển khai `NavigableSet` và `SortedSet`; hỗ trợ thêm/xóa/tìm hàng xóm và range view.

Cả hai dựa trên ý tưởng **skip list**, cấu trúc nhiều mức liên kết giúp tìm kiếm, thêm và xóa với **độ phức tạp kỳ vọng O(log n)**. Các thao tác trên collection được thiết kế cho truy cập concurrent mà không cần khóa toàn bộ cấu trúc ở phía người dùng trong những trường hợp thông thường.

Nhưng từ "concurrent" **không** có nghĩa rằng mọi chuỗi nhiều thao tác là transaction, iterator là snapshot bất biến, số lượng phần tử luôn được đọc trong O(1), hoặc các object value mutable tự động trở nên thread-safe. Bài này phân tích những ranh giới đó bằng Java 17+, chú trọng giải thích API, ví dụ chạy được và lỗi thiết kế thường gặp.

**Phạm vi:** **Concurrent Collections** trong **Java concurrency nói chung**. Không dùng Spring-specific collection, annotation hoặc scheduler; phần liên quan tới Spring được dành cho chương riêng.

## 1. Vì sao cần một concurrent collection có thứ tự?

Giả sử hệ thống giữ các nhiệm vụ theo timestamp:

```text
1700000100 -> task A
1700000120 -> task B
1700000190 -> task C
```

Trong lúc worker A thêm nhiệm vụ mới, worker B cần tìm nhiệm vụ có timestamp **lớn nhất không vượt deadline**; worker C cần duyệt khoảng timestamp. `ConcurrentHashMap` giúp truy cập concurrent theo key nhưng **không duy trì thứ tự khóa** để thực hiện `floorKey`, `ceilingKey` hay `subMap`.

`TreeMap` có thứ tự và NavigableMap API, nhưng bản thân nó **không an toàn khi nhiều thread cùng sửa/đọc mà không có đồng bộ phù hợp**. Chỉ thêm `volatile` cho biến trỏ tới `TreeMap` cũng không làm các thao tác nội bộ thread-safe.

`ConcurrentSkipListMap` đáp ứng hai yêu cầu **đồng thời**:

1. Các operation đơn lẻ có hợp đồng concurrent.
2. Khóa được tổ chức theo **natural ordering** hoặc một `Comparator` đã cung cấp.

`ConcurrentSkipListSet` là cấu trúc tương tự khi chỉ quan tâm **tập khóa/phần tử**, không cần value.

## 2. Skip list: hình dung cấu trúc nhiều tầng

Skip list duy trì thứ tự tại tầng thấp nhất và dùng các "đường tắt" tại các tầng cao hơn:

```text
Level 3: HEAD ----------------------> 50
Level 2: HEAD ----------> 30 ------> 50
Level 1: HEAD -> 10 ---> 30 -> 40 -> 50
Level 0: HEAD -> 10 -> 20 -> 30 -> 40 -> 50 -> 60
                        ^
                   ascending keys
```

Sơ đồ chỉ minh họa ý tưởng; số tầng thực tế và cách giữ liên kết là chi tiết triển khai. Khi tìm `40`, thuật toán có thể đi qua đường tắt ở tầng cao rồi đi xuống thay vì quét tuần tự mọi nút từ đầu.

Ý nghĩa:

- Khóa/phần tử được truy cập theo thứ tự tăng dần.
- Search, insert, remove có **expected average O(log n)**, không phải cam kết hard worst-case cho mọi lịch chạy và mọi input.
- Triển khai concurrent phải phối hợp những thay đổi liên kết giữa nhiều thread; không được suy rằng toàn bộ collection dùng một monitor chung chặn mọi hoạt động.
- Skip list dùng thêm con trỏ/chỉ mục để đổi lấy khả năng điều hướng có thứ tự.
- Thứ tự chỉ là **thứ tự comparator**, không phải thứ tự thread đến hoặc thứ tự gọi `put`.

Đừng viết business logic phụ thuộc vào chiều cao tầng hoặc quyết định ngẫu nhiên nội bộ của một node; API bảo đảm quan hệ có thứ tự và các operation, không bảo đảm hình dạng graph.

## 3. Khởi tạo `ConcurrentSkipListMap`

Chỉ cần import:

```java
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.ConcurrentNavigableMap;
```

Một vài dạng khởi tạo:

```java
ConcurrentSkipListMap<Integer, String> byId =
        new ConcurrentSkipListMap<>();

ConcurrentSkipListMap<String, Integer> reverse =
        new ConcurrentSkipListMap<>(
                java.util.Comparator.reverseOrder());
```

Đây là các declaration minh họa trong một scope hợp lệ. Với constructor không có comparator, key phải có **natural ordering** tương thích, thường bằng `Comparable`; ví dụ `Integer`, `Long`, `String`.

Khi truyền comparator, map dùng comparator đó để sắp xếp và xác định **hai key có cùng vị trí logic hay không**. Do vậy, comparator không chỉ ảnh hưởng cách in ra, mà ảnh hưởng luôn semantics lookup/duplicate keys.

Nếu nhiều thread dùng cùng map, có thể chia sẻ reference sau khi khởi tạo theo một cơ chế publication phù hợp: truyền qua constructor, final field, hoặc thông qua executor/concurrent mechanism. Bản thân class concurrent không khiến một reference chưa được công bố an toàn tự động có visibility tốt.

## 4. Các thao tác map cơ bản

Nhóm operation thường dùng:

| Operation | Ý nghĩa |
| --- | --- |
| `put(key,value)` | Gắn value, trả value cũ nếu có |
| `get(key)` | Đọc mapping hiện tại |
| `remove(key)` | Xóa mapping nếu tồn tại |
| `putIfAbsent(key,value)` | Chỉ thêm nếu chưa có mapping theo contract |
| `remove(key,value)` | Chỉ xóa nếu mapping hiện tại khớp value mong đợi |
| `replace(key,old,new)` | Thay có điều kiện theo value |
| `computeIfAbsent(key,f)` | Tạo value khi chưa có theo cơ chế remapping |
| `computeIfPresent(key,f)` | Cập nhật khi key hiện có |
| `compute(key,f)` | Tính mapping mới từ mapping hiện tại |
| `merge(key,value,f)` | Kết hợp value mới với value cũ nếu đã có |

Các operation có tính chất update nguyên tử theo **một mapping/key** theo hợp đồng tương ứng. Điều đó **không tạo transaction xuyên hai key**.

Ví dụ sai khi cần invariant nhiều key:

```java
if (map.get("a") > 0) {
    map.put("a", map.get("a") - 1);
    map.put("b", map.get("b") + 1);
}
```

Đây là **anti-pattern minh họa**; `map` giả định đã có hai key/value. Ba lần đọc/ghi liên tiếp không tạo atomic transfer. Thread khác có thể xen vào, khiến mất cập nhật hoặc invariant tổng `a+b` bị vi phạm. Khi cần transaction nhiều key, thiết kế đồng bộ hoặc state object nguyên tử cấp cao hơn.

## 5. Ví dụ Java 17+: thứ tự, lookup và key lân cận

Lưu thành `SkipListMapBasicsDemo.java`:

```java
import java.util.concurrent.ConcurrentSkipListMap;

public class SkipListMapBasicsDemo {
    public static void main(String[] args) {
        ConcurrentSkipListMap<Integer, String> map =
                new ConcurrentSkipListMap<>();

        map.put(30, "thirty");
        map.put(10, "ten");
        map.put(50, "fifty");
        map.put(20, "twenty");

        System.out.println("Keys: " + map.navigableKeySet());
        System.out.println("First: " + map.firstKey());
        System.out.println("Last: " + map.lastKey());
        System.out.println("Floor 25: " + map.floorKey(25));
        System.out.println("Ceiling 25: " + map.ceilingKey(25));
        System.out.println("Lower 20: " + map.lowerKey(20));
        System.out.println("Higher 20: " + map.higherKey(20));
        System.out.println("Value at 30: " + map.get(30));
    }
}
```

Chạy:

```bash
javac SkipListMapBasicsDemo.java
java SkipListMapBasicsDemo
```

Stdout chính xác khi không có thread khác sửa map:

```text
Keys: [10, 20, 30, 50]
First: 10
Last: 50
Floor 25: 20
Ceiling 25: 30
Lower 20: 10
Higher 20: 30
Value at 30: thirty
```

Thứ tự key là **tăng dần theo `Integer.compareTo`**, dù thứ tự `put` ban đầu là 30, 10, 50, 20. Bốn operation `floorKey`, `ceilingKey`, `lowerKey` và `higherKey` có semantics riêng, không nên thay bằng cách lấy "phần tử gần nhất" rồi đoán.

## 6. Phân biệt `lower/floor/ceiling/higher`

Với một key mục tiêu `k`:

| Operation | Quan hệ với `k` | Nếu không có ứng viên |
| --- | --- | --- |
| `lowerKey(k)` | Khóa lớn nhất **nhỏ hơn k** | `null` |
| `floorKey(k)` | Khóa lớn nhất **nhỏ hơn hoặc bằng k** | `null` |
| `ceilingKey(k)` | Khóa nhỏ nhất **lớn hơn hoặc bằng k** | `null` |
| `higherKey(k)` | Khóa nhỏ nhất **lớn hơn k** | `null` |

Ví dụ keys `[10,20,30]`:

```text
lowerKey(20)   -> 10
floorKey(20)   -> 20
ceilingKey(20) -> 20
higherKey(20)  -> 30

floorKey(5)    -> null
ceilingKey(35) -> null
```

Không đánh đồng `floor` với **làm tròn số thực**; tên này chỉ quan hệ thứ tự. Với comparator tùy chỉnh, "nhỏ hơn" và "lớn hơn" đều **theo comparator**, không phải nhất thiết theo giá trị số hoặc thứ tự chữ cái mặc định.

Nếu cần cả key và value tương ứng trong **một entry**, dùng `lowerEntry`, `floorEntry`, `ceilingEntry` hoặc `higherEntry`. Việc lấy key rồi gọi `get(key)` hai lần là **hai operation khác nhau**; dưới concurrent removal, value có thể đã biến mất giữa hai lần đọc.

## 7. First/last và polling entry: đọc khác với xóa

Map cung cấp:

- `firstKey()`, `lastKey()`: lấy key đầu/cuối, ném `NoSuchElementException` nếu map đang rỗng.
- `firstEntry()`, `lastEntry()`: trả một entry tương ứng, hoặc `null` khi không có.
- `pollFirstEntry()`, `pollLastEntry()`: **xóa và trả** entry đầu/cuối theo thứ tự.
- `descendingMap()`: view điều hướng theo thứ tự ngược.
- `navigableKeySet()`, `descendingKeySet()`: view các keys.

`pollFirstEntry` đặc biệt hữu ích khi nhiều worker muốn **claim phần tử có khóa ưu tiên nhỏ nhất**: mỗi lần xóa một entry là một operation, nên không cần tự viết `firstEntry` rồi `remove` tách rời. Nhưng:

- Worker khác có thể thêm key nhỏ hơn **ngay sau** lần poll.
- Không thể suy rằng đã poll được "phần tử nhỏ nhất của cả tương lai".
- Nếu task cần kiểm soát deadline và chờ khi map rỗng, CSLM **không phải blocking queue**: phải kết hợp signaling/condition hoặc dùng cấu trúc scheduler thích hợp.
- Khi có comparator tùy chỉnh, "first" là **nhỏ nhất theo comparator**.

## 8. Ví dụ Java 17+: poll và descending view

Lưu thành `SkipListPollDemo.java`:

```java
import java.util.concurrent.ConcurrentSkipListMap;

public class SkipListPollDemo {
    public static void main(String[] args) {
        ConcurrentSkipListMap<Integer, String> map =
                new ConcurrentSkipListMap<>();

        map.put(5, "five");
        map.put(1, "one");
        map.put(3, "three");

        System.out.println("Ascending: " + map.navigableKeySet());
        System.out.println("Descending: " + map.descendingKeySet());

        var first = map.pollFirstEntry();
        var last = map.pollLastEntry();

        System.out.println("Polled first key: " + first.getKey());
        System.out.println("Polled last key: " + last.getKey());
        System.out.println("Remaining keys: " + map.navigableKeySet());
    }
}
```

```bash
javac SkipListPollDemo.java
java SkipListPollDemo
```

Stdout chính xác:

```text
Ascending: [1, 3, 5]
Descending: [5, 3, 1]
Polled first key: 1
Polled last key: 5
Remaining keys: [3]
```

`pollFirstEntry()` và `pollLastEntry()` **làm thay đổi** map. Ở chương trình không có writer cạnh tranh, kết quả lần lượt là 1 và 5. Nếu dùng `firstEntry` thay cho `pollFirstEntry`, entry đầu vẫn nằm trong map.

Những entry trả về từ operation điều hướng là các bản ghi **đại diện mapping tại thời điểm quan sát**, không nên coi `Map.Entry.setValue` trên chúng là cách cập nhật mapping trong collection; muốn thay value, hãy dùng API map như `replace` hoặc `compute`.

## 9. `ConcurrentSkipListSet`: chỉ cần phần tử đã sắp xếp

Khi không cần value, dùng `ConcurrentSkipListSet<E>`. Nó hỗ trợ:

- `add(e)` và `remove(e)` theo membership.
- `contains(e)` để kiểm tra phần tử.
- `first()` và `last()`.
- `lower(e)`, `floor(e)`, `ceiling(e)`, `higher(e)`.
- `pollFirst()` và `pollLast()` để lấy và xóa đầu/cuối.
- `subSet`, `headSet`, `tailSet` và `descendingSet`.

Giống map, set sắp xếp theo natural ordering hoặc comparator. Hai phần tử **so sánh bằng 0 theo comparator** được coi tương đương cho membership, ngay cả khi `equals` nói khác.

`ConcurrentSkipListSet` thích hợp cho ordered unique IDs, watermark candidates, timestamp markers hay tập token cần truy vấn theo khoảng. Nó **không phải multiset**: nếu cần đếm số lần xuất hiện của cùng một key, phải dùng map key → count với update phù hợp.

## 10. Ví dụ Java 17+: các operation của set

Lưu thành `SkipListSetDemo.java`:

```java
import java.util.concurrent.ConcurrentSkipListSet;

public class SkipListSetDemo {
    public static void main(String[] args) {
        ConcurrentSkipListSet<Integer> set =
                new ConcurrentSkipListSet<>();

        System.out.println("Added 20: " + set.add(20));
        set.add(10);
        set.add(30);
        System.out.println("Duplicate 20: " + set.add(20));
        System.out.println("Sorted: " + set);
        System.out.println("Floor 25: " + set.floor(25));
        System.out.println("Ceiling 25: " + set.ceiling(25));
        System.out.println("Polled first: " + set.pollFirst());
        System.out.println("Remaining: " + set);
    }
}
```

```bash
javac SkipListSetDemo.java
java SkipListSetDemo
```

Stdout chính xác:

```text
Added 20: true
Duplicate 20: false
Sorted: [10, 20, 30]
Floor 25: 20
Ceiling 25: 30
Polled first: 10
Remaining: [20, 30]
```

`add(20)` lần hai trả `false` vì 20 đã tồn tại theo comparator. Set không lưu duplicate. `pollFirst` vừa trả 10 vừa xóa 10. Các output in collection trực tiếp chỉ được cam kết trong ví dụ vì không có thread khác đang sửa.

## 11. Map và set đều không chấp nhận `null`

Hai class này **không cho key/element `null`**; `ConcurrentSkipListMap` cũng **không cho value `null`**.

Lý do quan trọng ở cấp API: `map.get(key) == null` được dùng để biểu thị **không có mapping**, không phải "mapping tồn tại nhưng có value null". Trong môi trường concurrent, để null vừa biểu thị absent vừa biểu thị một value hợp lệ sẽ làm các thao tác conditional khó xác định.

Ví dụ sai:

```java
ConcurrentSkipListMap<String, String> map =
        new ConcurrentSkipListMap<>();

map.put("ok", null); // NullPointerException
map.put(null, "x");  // NullPointerException
```

Đây là ví dụ lỗi minh họa, không phải chương trình xử lý exception hoàn chỉnh.

Thay vì lưu null:

- Sử dụng `Optional<T>` trong **value object** nếu cần biểu thị trạng thái thiếu dữ liệu có chủ đích.
- Dùng một record/value type như `Status(MISSING)` hoặc enum sentinel.
- Hoặc xóa mapping khi không còn giá trị hợp lệ, theo contract nghiệp vụ.

**Không nhầm** giữa "method trả null vì không có neighbor/key" và "collection cho phép lưu null". `floorKey` trả null nếu không có ứng viên, nhưng key null không phải một key hợp lệ.

## 12. Comparator quyết định cả thứ tự lẫn tính duy nhất

Với natural order, `String` có thứ tự lexicographic, `Integer` theo trị số. Khi truyền `Comparator` tùy chỉnh, collection dùng **kết quả compare** để điều hướng và quyết định hai keys/elements tương đương.

Một comparator sai có thể gây lỗi logic:

```java
Comparator<String> byLength =
        Comparator.comparingInt(String::length);
```

Nếu chỉ so độ dài, hai string khác nội dung như `"ab"` và `"cd"` có kết quả compare 0, nên trong ordered map chúng được đối xử như một key logic.

Nếu muốn phân biệt những string có cùng độ dài, bổ sung tie-breaker:

```java
Comparator<String> byLengthThenText =
        Comparator.comparingInt(String::length)
                  .thenComparing(Comparator.naturalOrder());
```

Đây là các snippet minh họa (cần import `java.util.Comparator` trong source). Comparator còn phải có tính nhất quán cần thiết: phản xạ cho tương đương, nhất quán dấu, bắc cầu. Nếu comparator dựa trên state mutable thay đổi theo thời gian, cấu trúc có thứ tự có thể không tìm được key như mong đợi.

## 13. Ví dụ Java 17+: comparator làm hai key thành một

Lưu thành `SkipListComparatorDemo.java`:

```java
import java.util.Comparator;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.ConcurrentSkipListSet;

public class SkipListComparatorDemo {
    public static void main(String[] args) {
        ConcurrentSkipListMap<String, Integer> map =
                new ConcurrentSkipListMap<>(
                        String.CASE_INSENSITIVE_ORDER);

        map.put("Alpha", 1);
        map.put("ALPHA", 2);

        System.out.println("Case-insensitive size: " + map.size());
        System.out.println("Lookup alpha: " + map.get("alpha"));

        Comparator<String> byLengthThenText =
                Comparator.comparingInt(String::length)
                          .thenComparing(Comparator.naturalOrder());

        ConcurrentSkipListSet<String> set =
                new ConcurrentSkipListSet<>(byLengthThenText);

        set.add("bb");
        set.add("c");
        set.add("a");

        System.out.println("Length order: " + set);
    }
}
```

```bash
javac SkipListComparatorDemo.java
java SkipListComparatorDemo
```

Stdout chính xác:

```text
Case-insensitive size: 1
Lookup alpha: 2
Length order: [a, c, bb]
```

Trong map case-insensitive, `"Alpha"` và `"ALPHA"` so sánh bằng 0; `put` lần hai cập nhật value của **một key logic** thay vì tạo hai entry. Với set, tie-breaker giúp `"a"` và `"c"` không bị coi là một phần tử chỉ vì cả hai dài 1.

**Lưu ý contract SortedMap/SortedSet:** ordering nên **consistent with equals** nếu muốn tuân thủ semantics chung của `Map`/`Set` dựa trên `equals`. Comparator không nhất quán có thể vẫn chạy nhưng behavior khi đối chiếu với collection khác gây bất ngờ. Không được giả định `equals` và `compare` luôn cùng định nghĩa "trùng nhau".

## 14. Range view: `subMap`, `headMap` và `tailMap`

Một ưu điểm so với `ConcurrentHashMap` là truy vấn khoảng theo khóa:

```java
map.subMap(fromKey, true, toKey, false);
map.headMap(toKey, false);
map.tailMap(fromKey, true);
```

Đây là snippet minh họa. Các overload nhận `boolean inclusive` cho phép chỉ rõ giới hạn có bao gồm key biên hay không.

Quan trọng: **kết quả là view được backing bởi map gốc**, không phải snapshot sao chép. Điều đó nghĩa là:

- Thay đổi hợp lệ qua view có thể tác động map gốc.
- Thay đổi map gốc nằm trong range sẽ hiện lên khi quan sát view sau đó.
- Thread khác sửa map gốc trong lúc bạn duyệt view thì iterator vẫn có semantics weakly consistent.
- Một key ngoài giới hạn range không thể được thêm qua view như thể nó nằm trong phạm vi hợp lệ; operation có thể ném `IllegalArgumentException`.
- Một view không tự đóng băng tập key của một khoảnh khắc.

Một API nhận range view rồi dùng nó làm **báo cáo snapshot chính xác tại một thời điểm** sẽ sai yêu cầu nếu các writer vẫn hoạt động.

## 15. Ví dụ Java 17+: range view là live/backed

Lưu thành `SkipListRangeViewDemo.java`:

```java
import java.util.concurrent.ConcurrentNavigableMap;
import java.util.concurrent.ConcurrentSkipListMap;

public class SkipListRangeViewDemo {
    public static void main(String[] args) {
        ConcurrentSkipListMap<Integer, String> map =
                new ConcurrentSkipListMap<>();

        for (int i = 1; i <= 6; i++) {
            map.put(i, "v" + i);
        }

        ConcurrentNavigableMap<Integer, String> middle =
                map.subMap(2, true, 5, false);

        System.out.println("Middle before: "
                + middle.navigableKeySet());

        middle.remove(3);
        map.put(4, "changed");

        System.out.println("Main after remove: "
                + map.navigableKeySet());
        System.out.println("Middle sees update: "
                + middle.get(4));

        boolean rejected = false;
        try {
            middle.put(6, "outside");
        } catch (IllegalArgumentException e) {
            rejected = true;
        }
        System.out.println("Outside key rejected: " + rejected);
    }
}
```

```bash
javac SkipListRangeViewDemo.java
java SkipListRangeViewDemo
```

Stdout chính xác:

```text
Middle before: [2, 3, 4]
Main after remove: [1, 2, 4, 5, 6]
Middle sees update: changed
Outside key rejected: true
```

`subMap(2, true, 5, false)` gồm 2, 3, 4; loại 5. `middle.remove(3)` xóa trong map gốc. `map.put(4, "changed")` sửa qua map gốc và view đọc được value mới. `middle.put(6,...)` vượt giới hạn view nên bị từ chối.

**Kết luận:** range view là cách giới hạn namespace key, không phải cơ chế snapshot-isolation.

## 16. Range view trên `ConcurrentSkipListSet`

Với set, các API tương ứng là:

```java
ConcurrentSkipListSet<Integer> set =
        new ConcurrentSkipListSet<>();

set.add(10);
set.add(20);
set.add(30);
set.add(40);

NavigableSet<Integer> range =
        set.subSet(20, true, 40, false);
```

Đây là snippet minh họa (cần import `java.util.NavigableSet`). `range` chứa 20 và 30 ở thời điểm đó; thay đổi trên range hoặc set có thể phản ánh ở cả hai.

`headSet(to, inclusive)` giữ phía dưới bound; `tailSet(from, inclusive)` giữ phía trên bound. Các overload không có boolean thường có semantics biên mặc định theo hợp đồng `SortedSet`: `headSet` loại cận trên, `tailSet` gồm cận dưới, `subSet(from,to)` gồm from và loại to.

Với comparator đảo thứ tự, điều kiện giới hạn cũng được diễn giải **theo comparator**. Không lấy natural numeric ordering để suy nghĩa "from" và "to" của một descending view.

## 17. Weakly consistent iterator là gì?

Iterator của các concurrent skip list collections là **weakly consistent**:

- Có thể duyệt khi thread khác đang thêm/xóa mà **không dùng cơ chế fail-fast `ConcurrentModificationException` như iterator của nhiều collection thường**.
- Nó có thể phản ánh **một phần** thay đổi concurrent; không phải snapshot cố định.
- Không bảo đảm mọi phần tử được thêm sau khi iterator được tạo đều xuất hiện.
- Không bảo đảm kết quả quan sát được là một ảnh chụp atomic tại một thời điểm.
- Các thao tác xảy ra đồng thời có thể khiến nội dung iteration khác nhau giữa các lần chạy.
- Iteration vẫn đi theo quy tắc thứ tự sắp xếp của collection trong phạm vi hành vi iterator, nhưng không suy rằng kết quả có cùng tập phần tử với `keySet()` ở một thời điểm duy nhất.

**Hai điều cần tránh:**

1. Dùng iterator rồi giả định có một "bản sao của map đúng lúc bắt đầu".
2. Bắt `ConcurrentModificationException` để xây vòng retry và tưởng đó là cách dùng đúng của loại collection này.

Nếu cần snapshot ổn định để xử lý số liệu tài chính hoặc quyết định transaction, hãy thiết kế một cơ chế snapshot/version riêng hoặc **quiesce writers**; chỉ dùng collection concurrent không đủ.

## 18. Ví dụ Java 17+: iterator hoạt động khi writer cập nhật

Lưu thành `WeakIteratorDemo.java`:

```java
import java.util.Iterator;
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;

public class WeakIteratorDemo {
    public static void main(String[] args) throws InterruptedException {
        ConcurrentSkipListMap<Integer, String> map =
                new ConcurrentSkipListMap<>();

        map.put(1, "one");
        map.put(2, "two");
        map.put(3, "three");

        Iterator<Integer> iterator =
                map.navigableKeySet().iterator();

        CountDownLatch begin = new CountDownLatch(1);
        AtomicReference<Throwable> failure = new AtomicReference<>();

        Thread reader = new Thread(() -> {
            try {
                begin.await();
                while (iterator.hasNext()) {
                    iterator.next();
                }
            } catch (Throwable e) {
                failure.set(e);
            }
        }, "reader");

        Thread writer = new Thread(() -> {
            try {
                begin.await();
                map.put(4, "four");
                map.remove(2);
            } catch (InterruptedException e) {
                Thread.currentThread().interrupt();
            }
        }, "writer");

        reader.start();
        writer.start();
        begin.countDown();
        reader.join();
        writer.join();

        System.out.println("Reader finished without error: "
                + (failure.get() == null));
        System.out.println("Final keys: "
                + map.navigableKeySet());
    }
}
```

```bash
javac WeakIteratorDemo.java
java WeakIteratorDemo
```

Stdout khi không có interruption ngoài chương trình:

```text
Reader finished without error: true
Final keys: [1, 3, 4]
```

**Không in và không hứa reader đã nhìn thấy key nào.** Nó có thể đã thấy 2 trước khi xóa, hoặc đã thấy 4 sau khi thêm, tùy scheduler. Đó chính là weak consistency. Sau khi hai thread `join`, map không còn writer, nên `Final keys` là trạng thái ổn định và có thể dự đoán.

Trong ví dụ này, `failure` được ghi từ reader qua `AtomicReference`; main đọc sau join. Việc catch `Throwable` là lựa chọn có giới hạn **để báo QA của demo**, không phải khuyến nghị nuốt mọi exception/Error trong ứng dụng production.

## 19. `size()` không nhất thiết là O(1) hoặc chính xác tức thời

Với `ConcurrentSkipListMap` và `ConcurrentSkipListSet`, `size()` không có cùng đặc tính như `ArrayList.size()` hay một bộ đếm atomic lưu sẵn.

Javadoc nhấn mạnh:

- Việc xác định size có thể yêu cầu **duyệt qua các phần tử**.
- Khi có nhiều thread concurrent update, size trả về có thể **không phản ánh số phần tử ở một thời điểm duy nhất theo kỳ vọng của caller**.
- Kết quả chỉ nên xem là **ước lượng quan sát** trong lúc collection thay đổi.
- Gọi `size()` nhiều lần trong hot path có thể tốn chi phí cao trên map/set lớn.
- Đừng dựa vào `if (map.size() < limit) map.put(...)` để tạo hard capacity.

Nếu cần giới hạn capacity, dùng bounded queue, semaphore, admission control hay một protocol atomic riêng. Concurrent sorted map **không có max-capacity enforcement tích hợp**.

**Quan trọng:** ngay cả khi đọc size cho ra 100, thread khác có thể thêm/xóa trước khi bạn hành động dựa trên con số đó. Đó là vấn đề time-of-check-to-time-of-use, không chỉ hiệu năng.

## 20. Atomic update theo khóa: `putIfAbsent`, `replace`, `remove(key,value)`

Một pattern sai:

```java
if (!map.containsKey(key)) {
    map.put(key, value);
}
```

Đây là snippet minh họa. Với nhiều threads, hai thread cùng thấy absent rồi đều `put`; một value ghi đè value khác.

Dùng API có điều kiện:

```java
V previous = map.putIfAbsent(key, newValue);
```

`previous == null` biểu thị đã có thể gắn mapping mới khi absent theo contract của map (vì value null không được lưu). Tương tự:

```java
boolean changed = map.replace(key, expectedOldValue, newValue);
boolean removed = map.remove(key, expectedValue);
```

Các snippet là ký pháp tổng quát, phải thay kiểu `V`/`key` và khai báo ở code thật.

Những operation này hữu ích để làm **compare-and-update theo một key**. Nhưng `putIfAbsent` không đủ cho mục tiêu "key phải chưa tồn tại trong toàn bộ khoảng thời gian task thực thi"; một thread khác có thể xóa mapping ngay sau khi thêm.

## 21. Ví dụ Java 17+: conditional updates không mất cập nhật

Lưu thành `ConditionalSkipListDemo.java`:

```java
import java.util.concurrent.ConcurrentSkipListMap;

public class ConditionalSkipListDemo {
    public static void main(String[] args) {
        ConcurrentSkipListMap<String, Integer> map =
                new ConcurrentSkipListMap<>();

        Integer first = map.putIfAbsent("job", 10);
        Integer second = map.putIfAbsent("job", 20);

        boolean replacedWrong = map.replace("job", 7, 30);
        boolean replacedRight = map.replace("job", 10, 30);

        boolean removedWrong = map.remove("job", 20);
        boolean removedRight = map.remove("job", 30);

        System.out.println("First insertion was absent: "
                + (first == null));
        System.out.println("Second saw old value: " + second);
        System.out.println("Wrong replace: " + replacedWrong);
        System.out.println("Right replace: " + replacedRight);
        System.out.println("Wrong remove: " + removedWrong);
        System.out.println("Right remove: " + removedRight);
        System.out.println("Map empty: " + map.isEmpty());
    }
}
```

```bash
javac ConditionalSkipListDemo.java
java ConditionalSkipListDemo
```

Stdout chính xác:

```text
First insertion was absent: true
Second saw old value: 10
Wrong replace: false
Right replace: true
Wrong remove: false
Right remove: true
Map empty: true
```

Ví dụ không có cạnh tranh thực tế nhưng cho thấy **hợp đồng conditional update** thay cho cặp thao tác "đọc rồi ghi". Trong ứng dụng concurrent, cần xử lý nhánh `false` hoặc value hiện tại do thread khác thay đổi, chứ không được tự khẳng định operation chắc thành công.

## 22. `compute`, `merge` và function có thể được gọi lại

Các API như:

```java
map.compute(key, (k, oldValue) -> nextValue(oldValue));

map.merge(key, 1, Integer::sum);

map.computeIfAbsent(key, k -> buildValue(k));
```

giúp thể hiện update theo key thay vì tách `get`/`put`. Tuy nhiên, cần phân biệt với một transaction có callback **chỉ chạy đúng một lần**.

Đối với `ConcurrentSkipListMap`, logic update concurrent có thể **thử lại** do thread khác thay đổi mapping. Javadoc các remapping operation cảnh báo function **không nhất thiết được áp dụng một lần atomically như người dùng kỳ vọng**; vì vậy function nên:

- **Không có side effect không thể lặp lại** (gửi email, trừ tiền, gọi API remote).
- Không phụ thuộc việc mỗi lần gọi callback tương ứng một commit thành công.
- Chỉ tính từ input sang output, đủ nhanh, không block lâu.
- Không tự thay đổi cùng map/key một cách gây dependency hoặc recursion khó kiểm soát.
- Chú ý `null`: với những remapping method cho phép return null, null có thể mang nghĩa **remove/no mapping**, không phải value hợp lệ.

Ví dụ nếu muốn tăng bộ đếm một mapping:

```java
map.merge("counter", 1, Integer::sum);
```

Phép cộng số nguyên **không có side effect** nên phù hợp khi implementation phải retry. Nhưng `Integer` có thể overflow nếu counter lớn; cân nhắc `Long` hoặc policy giới hạn.

## 23. Ví dụ Java 17+: nhiều thread dùng `merge`

Lưu thành `ConcurrentSkipListMergeDemo.java`:

```java
import java.util.concurrent.ConcurrentSkipListMap;
import java.util.concurrent.CountDownLatch;

public class ConcurrentSkipListMergeDemo {
    public static void main(String[] args)
            throws InterruptedException {
        ConcurrentSkipListMap<String, Integer> map =
                new ConcurrentSkipListMap<>();

        CountDownLatch start = new CountDownLatch(1);
        Thread[] workers = new Thread[4];

        for (int t = 0; t < workers.length; t++) {
            workers[t] = new Thread(() -> {
                try {
                    start.await();
                } catch (InterruptedException e) {
                    Thread.currentThread().interrupt();
                    return;
                }

                for (int i = 0; i < 500; i++) {
                    map.merge("counter", 1, Integer::sum);
                }
            });
            workers[t].start();
        }

        start.countDown();

        for (Thread worker : workers) {
            worker.join();
        }

        System.out.println("Counter: " + map.get("counter"));
        System.out.println("Keys: " + map.navigableKeySet());
    }
}
```

```bash
javac ConcurrentSkipListMergeDemo.java
java ConcurrentSkipListMergeDemo
```

Stdout trên đường chạy bình thường, không có interruption ngoài chương trình:

```text
Counter: 2000
Keys: [counter]
```

Bốn thread cùng bắt đầu từ latch, mỗi thread thực hiện 500 lần `merge`: tổng logic 2.000. Một biểu thức `map.put("counter", map.get("counter")+1)` không có atomicity tương đương và có thể làm mất increment khi concurrent.

Không kết luận thứ tự 2.000 lần callback hoặc worker nào thắng CAS trước. Chỉ **kết quả cuối của mapping** được chứng minh. `Thread.join()` giúp main đợi toàn bộ worker trước khi đọc kết quả.

## 24. Value mutable không tự trở nên thread-safe

Map được thiết kế an toàn cho concurrent operations lên **mapping**, nhưng object value có thể là kiểu mutable thông thường:

```java
ConcurrentSkipListMap<String, ArrayList<String>> map =
        new ConcurrentSkipListMap<>();
```

Đây là snippet minh họa, cần import `ArrayList`. Nếu nhiều thread lấy cùng một `ArrayList` rồi gọi `add`, collection value đó **không tự đồng bộ** chỉ vì nó được đặt trong concurrent map.

Các lựa chọn:

1. Dùng value **immutable**, cập nhật bằng `compute`/`replace` theo key.
2. Dùng value có thiết kế thread-safe riêng nếu nhiều thread cần chỉnh tại chỗ.
3. Dùng per-key lock hoặc transaction-level protocol khi cần sửa nhiều field nhất quán.
4. Không rò rỉ value mutable ra caller có thể sửa tự do.
5. Nếu value là record immutable, vẫn cần chú ý field reference tới object mutable bên trong record.

**Safe publication của reference** và **thread safety của mutation sau publication** là hai vấn đề khác nhau. Một put/get concurrent có memory consistency phù hợp nhưng không biến internal state của value thành atomic object.

## 25. "Snapshot" khác "weakly consistent view"

Một lệnh:

```java
var snapshot = new java.util.TreeMap<>(map);
```

tạo một object `TreeMap` mới, nhưng **nếu map nguồn đang bị sửa trong lúc sao chép**, tập mapping được đọc có thể đến từ nhiều thời điểm khác nhau. Đây không tự động là snapshot atomic của map concurrent.

Để có **snapshot đúng tại một điểm logical**, cần thêm giao thức:

- Tạm dừng/điều phối writers bằng lock bên ngoài mà **mọi writer** đều tuân thủ.
- Hoặc sử dụng versioning/MVCC, immutable snapshot swap hay một kiến trúc lưu trữ có snapshot semantics.
- Hoặc chấp nhận **eventual/approximate snapshot** nếu bài toán chỉ cần thống kê hoặc hiển thị sơ bộ.

Sao chép sau khi **toàn bộ writers đã hoàn tất và join** thì tập kết quả ổn định; trong trường hợp đó có thể dùng `new TreeMap<>(map)` để làm bản sao không còn bị ảnh hưởng bởi các thay đổi sau này của map nguồn (trừ việc values mutable vẫn được tham chiếu).

Đừng gọi việc copy là "linearizable snapshot" trong lúc writer active mà không có giao thức bổ sung.

## 26. `descendingMap` và các view đảo thứ tự

`descendingMap()` tạo một view theo thứ tự ngược của map. `descendingSet()` làm điều tương tự với set. Đây là **backed view**, không phải copy.

Ví dụ:

```java
var reverse = map.descendingMap();
```

Nếu original có keys `[1,3,5]`, reverse duyệt `[5,3,1]`. Nhưng nếu thread khác thêm `4` vào map gốc, reverse view cũng phản ánh trạng thái live theo thời điểm quan sát.

Với workload chỉ cần descending một lần, cân nhắc cost của iterator. Tài liệu Java cho biết ascending-ordered views/iterators có thể hiệu quả hơn descending variants trên những implementation này; không nên mặc định hai chiều có cùng đặc tính performance.

Mỗi update qua reverse view vẫn ảnh hưởng cùng backing map. Không được dùng reverse view để tạo một independent index với lifecycle riêng.

## 27. So sánh với các collection khác

| Collection | Concurrent access | Có thứ tự sorted/navigable? | Đặc điểm nổi bật |
| --- | --- | --- | --- |
| `HashMap` | Không an toàn cho concurrent mutation không đồng bộ | Không | Hash table thông thường |
| `TreeMap` | Không tự thread-safe | Có | Balanced tree, single-thread hoặc external lock |
| `ConcurrentHashMap` | Có | Không | Lookup/update theo key, throughput cao cho unordered keys |
| `ConcurrentSkipListMap` | Có | **Có** | Sorted concurrent map, neighbor/range navigation |
| `HashSet` | Không tự an toàn cho concurrent mutation | Không | Tập thông thường |
| `TreeSet` | Không tự thread-safe | Có | Sorted set, external synchronization khi chia sẻ mutable |
| `ConcurrentSkipListSet` | Có | **Có** | Sorted concurrent set, NavigableSet |
| `CopyOnWriteArraySet` | Có | Không duy trì sorted ordering | Thích hợp nhiều read, rất ít write; copy khi thay đổi |

Chọn theo **nhu cầu query** và **đặc tính workload**. Nếu chỉ cần get/put ngẫu nhiên theo key mà không cần thứ tự, `ConcurrentHashMap` thường đơn giản và có throughput/overhead hợp lý hơn. Nếu cần `floorEntry` hoặc range-based queries concurrent, `ConcurrentSkipListMap` có lợi thế API rõ ràng.

Không chọn skip list vì tên "concurrent" rồi bỏ qua thực tế rằng metadata/order maintenance cũng tốn memory và CPU hơn một hash table thông thường.

## 28. Không dùng CSLM như một hàng đợi blocking có deadline

Một map có khóa timestamp dễ khiến người viết:

```java
while (true) {
    var first = map.firstEntry();
    if (first != null && first.getKey() <= now()) {
        map.remove(first.getKey());
        runTask(first.getValue());
    }
}
```

Đây là anti-pattern minh họa, `now`/`runTask` chưa định nghĩa.

Các vấn đề:

- Vòng lặp busy-spin khi không có công việc.
- `firstEntry` rồi `remove(key)` không atomic claim. Thread khác có thể đã lấy/xóa/đổi mapping; vẫn có nguy cơ xử lý duplicate hoặc lấy value đã cũ.
- Nếu deadline ở tương lai, không có operation chờ tới đúng deadline.
- Nếu task thất bại, không có lifecycle retry/requeue rõ.
- `now()` nên dùng time source phù hợp với semantics lịch; clock adjustments có thể ảnh hưởng deadline.
- Nếu cần chính xác thứ tự chạy khi nhiều worker, chỉ có sorted order không đủ để bảo đảm global execution ordering.

`DelayQueue` hoặc `ScheduledExecutorService` thường phù hợp hơn cho scheduled delayed work; `PriorityBlockingQueue` dùng ưu tiên và blocking take nhưng **không tự chờ tới thời điểm deadline**. Nếu bắt buộc dùng map như index, phải thiết kế signaling và claim atomic bằng `pollFirstEntry`/conditional methods theo giao thức.

## 29. Độ phức tạp và lựa chọn hiệu năng

Bức tranh khái quát:

| Operation | Đặc tính thường gặp |
| --- | --- |
| `get/put/remove` theo key | Expected O(log n) |
| `floor/ceiling/lower/higher` | Expected O(log n) |
| Duyệt toàn bộ n phần tử | O(n) cho một traversal không đổi |
| `size()` | Có thể cần duyệt và tốn O(n), kém ổn định dưới concurrent update |
| Query range có k kết quả | Chi phí định vị + traversal k phần tử, nhưng concurrent changes làm kết quả quan sát không phải snapshot |
| `containsValue` của map | Có thể cần scan, không nên dùng như lookup index thứ hai |

Trên workload thực, chi phí còn phụ thuộc:

- Nhiều writer cùng đụng một key hay trải đều khắp key space.
- Comparator có tốn CPU hay không.
- Khóa dài, mutable hoặc có hash/compare không ổn định.
- Tỷ lệ range navigation so với random get/put.
- Có nhiều descending traversals hay không.
- Kích thước map, memory footprint của skip-list indexes và cache locality.
- Thread count, contention, allocation và garbage collector.
- Số thao tác composite đòi hỏi external synchronization.

**Độ phức tạp kỳ vọng** không phải chứng nhận mọi operation có upper bound thời gian cố định. Benchmarks nên được chạy với dữ liệu và contention tương ứng môi trường production; không dùng microbenchmark 10 keys để suy kết luận cho hàng triệu phần tử.

## 30. Những lỗi thường gặp

**1. "ConcurrentSkipListMap giống ConcurrentHashMap nhưng tự in sorted."** Không. Nó có NavigableMap/range semantics và cấu trúc khác; chọn theo truy vấn và chi phí.

**2. "Comparator chỉ ảnh hưởng display."** Sai. `compare(a,b)==0` có thể khiến hai key khác `equals` được coi cùng một logical key.

**3. "Có thể lưu null như ở HashMap."** Sai. CSLM cấm null key/value; CSLS cấm null element.

**4. "Weakly consistent iterator là snapshot tại lúc gọi iterator()."** Sai. Nó có thể phản ánh thay đổi concurrent.

**5. "Iterator sẽ luôn nhìn thấy mọi update xảy ra sau khi bắt đầu."** Không. Không có guarantee như vậy.

**6. "size() là đếm O(1) và hoàn toàn chính xác khi nhiều writer."** Sai. Có thể cần traversal và không là atomic snapshot.

**7. "if (get==null) put là atomic."** Sai. Dùng `putIfAbsent` hoặc remapping operation theo contract.

**8. "compute function luôn chạy đúng một lần."** Không nên giả định; remapping có thể retry, nên tránh side effect.

**9. "Map concurrent làm mọi ArrayList value thread-safe."** Sai. Value mutable phải có synchronization riêng.

**10. "subMap tạo bản sao độc lập."** Sai. Nó là view backed bởi map gốc.

**11. "Có thể put key ngoài range qua subMap."** Không. Out-of-range insertion bị từ chối.

**12. "firstEntry rồi remove là giống pollFirstEntry."** Sai. Cặp thao tác bị thread khác xen vào.

**13. "Set có thứ tự lưu được nhiều phần tử comparator-equal."** Sai. Comparator bằng 0 định nghĩa membership như một phần tử.

**14. "Concurrent collections tự bảo đảm transaction nhiều key."** Sai. Một chuỗi nhiều thao tác vẫn có thể có interleaving.

**15. "ConcurrentSkipListMap là hàng đợi blocking tự thức khi thêm item."** Không. Nó không có take/await như BlockingQueue.

**16. "Đọc lastKey từ map rỗng trả null."** Sai. `lastKey()` ném `NoSuchElementException`; `lastEntry()` trả null khi rỗng.

**17. "descendingMap là bản sao, không bị update ngoài ảnh hưởng."** Sai. Đó là live view.

**18. "Một map sorted concurrent tự đảm bảo thứ tự xử lý nghiệp vụ giữa threads."** Không. Nó bảo đảm thứ tự điều hướng khóa, không lập lịch thực thi tasks.

**19. "Chỉ cần volatile reference tới TreeMap để update an toàn."** Sai. Visibility của reference không bảo vệ nội bộ các phép put/remove.

**20. "copy map bằng new TreeMap là snapshot atomic dù writer đang sửa."** Sai. Cần snapshot protocol riêng nếu đòi hỏi tính nhất quán tại một thời điểm.

## 31. Checklist khi dùng trong ứng dụng thực

1. **Có thực sự cần sorted/navigable queries không?** Nếu không, thử `ConcurrentHashMap`.
2. **Comparator có đúng và immutable không?** Nhất quán với equals khi cần contract Map/Set phổ thông.
3. **Key có immutable không?** Không thay đổi trường tham gia comparator sau khi thêm.
4. **Có null được đưa vào không?** Map/set này từ chối null; chuyển trạng thái missing thành value type rõ.
5. **Các thao tác multi-key có invariant không?** Cần coordination/transaction riêng.
6. **Có lặp entry trong lúc writer hoạt động không?** Weakly consistent chứ không snapshot.
7. **Có cần report chính xác size không?** Đừng dùng `size` để chứng minh capacity/transaction.
8. **Có dùng subMap/subSet không?** Nhớ view backed và inclusive flags.
9. **Có lấy firstEntry rồi xóa tách rời không?** Nếu cần claim đầu nhỏ nhất, cân nhắc `pollFirstEntry`.
10. **Remapping callback có side effect không?** Nếu có, chuyển side effect ra khỏi retryable function.
11. **Value có mutable không?** Chọn immutable replacement hoặc đồng bộ nội bộ.
12. **Có cần blocking/deadline semantics không?** Skip list map/set không thay BlockingQueue.
13. **Workload có nhiều descending iterations không?** Benchmark thực tế; ascending thường có lợi.
14. **Có bảo vệ dữ liệu sau khi copy không?** Shallow copy không deep-copy mutable values.
15. **Có kiểm tra trường hợp empty không?** `firstKey/lastKey` có thể throw, `firstEntry/lastEntry` có thể trả null.
16. **Có monitor/lock ngoài cần coordination không?** Mọi writer phải tuân cùng lock nếu muốn atomic snapshot ngoài collection.
17. **Có cần cleanup/shutdown không?** Collection không sở hữu worker threads; quản lý executor theo vòng đời riêng.
18. **Đã test với contention và ordering thực tế chưa?** Dùng latches/joins, kiểm tra invariant thay vì đoán lịch chạy.

## 32. Câu hỏi tự kiểm tra

**Câu 1.** `ConcurrentSkipListMap` khác `ConcurrentHashMap` ở đâu?

CSLM duy trì **thứ tự sorted theo key** và có NavigableMap/range operations. CHM phục vụ concurrent map theo hash, không duy trì sorted key order.

**Câu 2.** `ConcurrentSkipListSet` có cho phép thêm hai String khác nội dung nhưng `Comparator.compare` trả 0 không?

Không. Đối với membership của ordered set, chúng là một phần tử logic theo comparator.

**Câu 3.** Với keys `[10,20,30]`, `floorKey(25)` và `higherKey(20)` là gì?

Lần lượt 20 và 30.

**Câu 4.** `subMap(2,true,5,false)` chứa key nào trong map `[1,2,3,4,5,6]`?

Các key 2, 3, 4. Nó là **view live**, không phải snapshot.

**Câu 5.** Tại sao iterator không ném fail-fast exception khi writer cập nhật không chứng minh nó là snapshot?

Vì nó **weakly consistent**: traversal có thể phản ánh một số cập nhật nhưng không cam kết ảnh chụp atomic.

**Câu 6.** Vì sao `size()` không thích hợp để enforce max-capacity dưới contention?

Nó có thể traversal, trả giá trị không ổn định khi writer hoạt động, và check-then-put vẫn có race.

**Câu 7.** Map cho `null` làm value không?

Không. Null value bị cấm, giúp `get()==null` biểu thị absent.

**Câu 8.** `map.putIfAbsent` tốt hơn `if(!map.containsKey(k)) map.put(k,v)` như thế nào?

Một operation conditional theo key tránh race giữa separate check và put.

**Câu 9.** Nếu value là `ArrayList`, map concurrent có bảo vệ các lời gọi `add` đồng thời không?

Không. Thread safety của mutable value là trách nhiệm riêng.

**Câu 10.** `map.firstEntry()` rồi `map.remove(key)` có tương đương `pollFirstEntry` dưới concurrency không?

Không. Thread khác có thể xen vào giữa hai lời gọi. `pollFirstEntry` tích hợp lấy và xóa entry theo operation.

**Câu 11.** `merge(key, 1, Integer::sum)` có thể dùng để tăng counter của một key từ nhiều thread không?

Có, phù hợp với pure remapping function và update semantics, nhưng phải xét overflow và contention.

**Câu 12.** Có thể dùng CSLM như một `DelayQueue` chỉ bằng việc chọn timestamp làm key không?

Không. CSLM không cung cấp blocking wait theo deadline hoặc lifecycle của task. Cần scheduler/queue và protocol thích hợp.

## 33. Tổng kết

- **`ConcurrentSkipListMap`** là sorted concurrent map theo key; **`ConcurrentSkipListSet`** là sorted concurrent set theo element. Cả hai cung cấp navigation/range API, không chấp nhận null và dùng comparator hoặc natural ordering.
- **Skip list** hỗ trợ tìm/thêm/xóa với expected logarithmic cost; không phải một ordered hash map có thứ tự ngẫu nhiên.
- **`lower/floor/ceiling/higher`**, `pollFirst/pollLast`, `descendingMap/descendingSet` và `subMap/subSet` là những API cốt lõi khi cần ordered queries.
- **Range views là live/backed**, không phải snapshot. Iterator **weakly consistent**, có thể duyệt cùng concurrent updates nhưng không cho một ảnh chụp atomic.
- **`size()` có thể tốn O(n) và không ổn định khi writer active**; không dùng để thực thi hard capacity.
- **Conditional update/remapping** giúp thao tác theo một key không bị check-then-act race; callback nên thuần vì có thể retry.
- **Comparator quyết định equivalence**; key mutable, comparator thiếu tie-breaker hoặc không nhất quán với equals dễ gây lỗi tìm kiếm/membership.
- **Concurrent collection không tự bảo vệ mutable values hay transaction nhiều key**. Cần data ownership/locking/immutable state phù hợp.
- Nếu chỉ cần unordered concurrent key/value, `ConcurrentHashMap` có thể hợp hơn; nếu cần blocking/delayed execution, dùng queue/scheduler có semantics phù hợp.

Câu hỏi chọn công cụ nên là: **"Tôi cần truy vấn theo thứ tự khóa trong lúc dữ liệu được cập nhật đồng thời, hay chỉ cần lookup theo key? Tôi cần một view weakly consistent, hay cần snapshot/transaction nhất quán?"**. Trả lời rõ hai câu hỏi ấy sẽ quyết định nên dùng `ConcurrentSkipListMap`/`ConcurrentSkipListSet`, hay cấu trúc concurrency khác của Java.