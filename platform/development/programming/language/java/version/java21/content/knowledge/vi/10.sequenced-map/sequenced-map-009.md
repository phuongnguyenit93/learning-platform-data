# SortedMap, NavigableMap và giới hạn định vị entry tường minh

Trong Java 21, `SortedMap` và `NavigableMap` đều có encounter order được quyết định bởi thứ tự so sánh key. `SortedMap` biểu diễn map có thứ tự tăng dần theo natural ordering hoặc `Comparator`; `NavigableMap` bổ sung các thao tác tìm key gần nhất và các view theo khoảng. Cả hai interface đều tham gia hệ thống `SequencedMap` của Java 21, nhưng không hỗ trợ tùy ý đưa một mapping lên đầu hoặc cuối bằng `putFirst()` và `putLast()`.

Giới hạn này là hệ quả trực tiếp của thứ tự sắp xếp: vị trí của mapping được quyết định bởi key và comparator. Nếu cho phép đặt key bất kỳ vào đầu hoặc cuối, map sẽ không còn tuân theo thứ tự đã cam kết. Khi cần sắp xếp theo tiêu chí nghiệp vụ, hãy định nghĩa `Comparator`; khi cần điều khiển thứ tự chèn hoặc truy cập, hãy chọn một cấu trúc có encounter order có thể định vị tường minh như `LinkedHashMap`.

## 1. SortedMap: thứ tự đến từ key

`SortedMap<K,V>` mở rộng `Map<K,V>` và `SequencedMap<K,V>`. Map duy trì một thứ tự toàn phần trên các key theo một trong hai cách:

- Natural ordering: dùng thứ tự tự nhiên của key, tức key phải triển khai `Comparable`.
- Comparator ordering: dùng `Comparator` được cung cấp khi tạo map.

Mọi key trong map phải so sánh được với các key còn lại. Nếu phép so sánh không tương thích, thao tác thêm hoặc truy vấn có thể ném `ClassCastException`. Thứ tự so sánh nên nhất quán với `equals`; nếu comparator xem hai key là bằng nhau nhưng `equals()` trả false, map vẫn xem chúng là cùng một key theo tiêu chí so sánh.

Ví dụ với natural ordering:

```java
SortedMap<String, Integer> scores = new TreeMap<>();
scores.put("Minh", 8);
scores.put("An", 9);
scores.put("Lan", 7);

System.out.println(scores.keySet());
// [An, Lan, Minh]
```

Thứ tự không phụ thuộc thứ tự gọi `put`. Khi dùng `TreeMap`, các thao tác `get`, `put`, `remove` và `containsKey` có độ phức tạp bảo đảm (O(\log n)) theo tài liệu API. Đây là đặc điểm của `TreeMap`, không phải cam kết hiệu năng chung cho mọi implementation của `SortedMap`.

Có thể truyền comparator để thay đổi tiêu chí sắp xếp:

```java
SortedMap<String, Integer> scores =
        new TreeMap<>(Comparator.comparingInt(String::length)
                                .thenComparing(Comparator.naturalOrder()));

scores.put("An", 9);
scores.put("Minh", 8);
scores.put("Bình", 7);

System.out.println(scores.keySet());
// [An, Minh, Bình]
```

Trong ví dụ, key được sắp theo độ dài chuỗi, sau đó theo thứ tự tự nhiên để phân biệt các chuỗi có cùng độ dài. Comparator là nguồn quyết định encounter order; không có khái niệm key được chèn gần đây nhất nằm ở cuối.

## 2. SortedMap là SequencedMap từ Java 21

Java 21 hoàn thiện Sequenced Collections theo JEP 431. `SortedMap` được cập nhật để mở rộng `SequencedMap`, còn `NavigableMap` mở rộng `SortedMap`. Vì vậy, sorted map có encounter order xác định và có các API chung để đọc hoặc loại bỏ mapping ở hai đầu:

| API | Ý nghĩa trong sorted map |
|---|---|
| `firstEntry()` | Mapping có key nhỏ nhất theo comparator; `null` nếu rỗng |
| `lastEntry()` | Mapping có key lớn nhất theo comparator; `null` nếu rỗng |
| `pollFirstEntry()` | Xóa và trả mapping có key nhỏ nhất; `null` nếu rỗng |
| `pollLastEntry()` | Xóa và trả mapping có key lớn nhất; `null` nếu rỗng |
| `reversed()` | View có encounter order ngược lại |
| `sequencedKeySet()` | View key có kiểu `SequencedSet` |
| `sequencedValues()` | View value có kiểu `SequencedCollection` |
| `sequencedEntrySet()` | View entry có kiểu `SequencedSet` |

`SortedMap` vẫn có các phương thức lâu đời `firstKey()` và `lastKey()`. Khác biệt quan trọng là:

- `firstKey()` và `lastKey()` trả key và ném `NoSuchElementException` nếu map rỗng.
- `firstEntry()` và `lastEntry()` trả snapshot của mapping và trả `null` nếu map rỗng.
- `pollFirstEntry()` và `pollLastEntry()` vừa trả snapshot vừa xóa mapping khỏi map.

Các entry snapshot do `firstEntry`, `lastEntry`, `pollFirstEntry` và `pollLastEntry` trả về không hỗ trợ sửa map nền thông qua `Map.Entry.setValue()`.

Ví dụ:

```java
NavigableMap<Integer, String> names = new TreeMap<>();
names.put(30, "Chi");
names.put(10, "An");
names.put(20, "Bình");

System.out.println(names.firstEntry()); // 10=An
System.out.println(names.lastEntry());  // 30=Chi

Map.Entry<Integer, String> first = names.pollFirstEntry();
System.out.println(first);              // 10=An
System.out.println(names);              // {20=Bình, 30=Chi}
```

Các thao tác ở hai đầu luôn dựa trên comparator hiện hành. Nếu comparator được đảo chiều, mapping ở đầu cũng thay đổi theo thứ tự mới.

## 3. Vì sao putFirst() và putLast() không được hỗ trợ?

`SequencedMap` định nghĩa `putFirst(key, value)` và `putLast(key, value)` để đặt mapping vào đầu hoặc cuối encounter order. Các map có thứ tự chèn như `LinkedHashMap` có thể thực hiện điều này vì encounter order độc lập với giá trị key.

Với `SortedMap`, thứ tự encounter được xác định bởi comparator. Do đó, Java 21 định nghĩa hai phương thức mặc định này trong `SortedMap` để luôn ném `UnsupportedOperationException`:

```java
NavigableMap<Integer, String> map = new TreeMap<>();
map.put(10, "An");
map.put(20, "Bình");

// Cả hai lời gọi đều ném UnsupportedOperationException.
map.putFirst(30, "Chi");
map.putLast(5, "Dung");
```

Điều này đúng cả khi key chưa tồn tại lẫn khi key đã có trong map. `putFirst` và `putLast` không phải cách yêu cầu map sắp xếp lại một mapping đang có; implementation của `SortedMap` không hỗ trợ thao tác định vị tường minh.

Hãy dùng `put(key, value)` để thêm hoặc cập nhật mapping. Map sẽ tự xác định vị trí theo natural ordering hoặc comparator:

```java
NavigableMap<Integer, String> map = new TreeMap<>();
map.put(10, "An");
map.put(20, "Bình");
map.put(5, "Dung");

System.out.println(map); // {5=Dung, 10=An, 20=Bình}
```

Nếu yêu cầu là "ưu tiên mapping mới nhất lên đầu" hoặc "đưa key vừa truy cập xuống cuối", sorted map không phải lựa chọn phù hợp. Hãy chọn cấu trúc theo đúng quy tắc thứ tự:

| Yêu cầu | Cấu trúc phù hợp |
|---|---|
| Sắp xếp theo key tự nhiên hoặc comparator | `TreeMap` / `SortedMap` |
| Tìm key gần nhất và truy vấn theo khoảng | `TreeMap` / `NavigableMap` |
| Giữ thứ tự chèn và định vị đầu/cuối | `LinkedHashMap` theo insertion order |
| Đưa mapping vừa truy cập về cuối, dùng đầu làm ứng viên LRU | `LinkedHashMap` theo access order |

Không nên cố thay đổi comparator sau khi đã đưa dữ liệu vào map. Comparator phải xác định thứ tự nhất quán trong suốt thời gian các key nằm trong cấu trúc; thay đổi trạng thái bên ngoài mà comparator dựa vào có thể làm thứ tự cây không còn phản ánh đúng comparator.

## 4. NavigableMap bổ sung các phép tìm kiếm gần nhất

`NavigableMap<K,V>` mở rộng `SortedMap<K,V>` với các thao tác tìm mapping gần một key mục tiêu. Những phương thức này phục vụ việc định vị, không phải cách duyệt tuần tự tất cả entry.

| Phương thức | Mapping/key được tìm |
|---|---|
| `lowerEntry(key)` / `lowerKey(key)` | Key lớn nhất nhưng nhỏ hơn `key` |
| `floorEntry(key)` / `floorKey(key)` | Key lớn nhất nhỏ hơn hoặc bằng `key` |
| `ceilingEntry(key)` / `ceilingKey(key)` | Key nhỏ nhất lớn hơn hoặc bằng `key` |
| `higherEntry(key)` / `higherKey(key)` | Key nhỏ nhất nhưng lớn hơn `key` |

Ví dụ:

```java
NavigableMap<Integer, String> seats = new TreeMap<>();
seats.put(10, "A");
seats.put(20, "B");
seats.put(40, "C");

System.out.println(seats.lowerEntry(20));   // 10=A
System.out.println(seats.floorEntry(20));   // 20=B
System.out.println(seats.ceilingEntry(30)); // 40=C
System.out.println(seats.higherEntry(20));  // 40=C
```

Các phương thức trả `null` nếu không có mapping thỏa mãn. Bản `...Entry` trả snapshot entry; bản `...Key` chỉ trả key. Ví dụ, với một lịch có các mốc thời gian, `floorEntry(now)` có thể tìm mốc gần nhất đã bắt đầu, còn `ceilingEntry(now)` tìm mốc gần nhất chưa đến.

## 5. Range view: SortedMap và NavigableMap

### Range của SortedMap

`SortedMap` cung cấp ba view theo khoảng:

- `subMap(fromKey, toKey)`: từ `fromKey` (inclusive) đến `toKey` (exclusive).
- `headMap(toKey)`: mọi key nhỏ hơn `toKey`.
- `tailMap(fromKey)`: mọi key lớn hơn hoặc bằng `fromKey`.

Các range là half-open: đầu dưới được bao gồm, đầu trên bị loại trừ. Ví dụ:

```java
SortedMap<Integer, String> map = new TreeMap<>();
map.put(10, "A");
map.put(20, "B");
map.put(30, "C");
map.put(40, "D");

System.out.println(map.subMap(20, 40)); // {20=B, 30=C}
System.out.println(map.headMap(30));    // {10=A, 20=B}
System.out.println(map.tailMap(30));    // {30=C, 40=D}
```

### Range của NavigableMap với cận inclusive/exclusive

`NavigableMap` bổ sung overload nhận cờ boolean để chọn rõ việc bao gồm từng cận:

```java
NavigableMap<Integer, String> map = new TreeMap<>();
map.put(10, "A");
map.put(20, "B");
map.put(30, "C");
map.put(40, "D");

System.out.println(map.subMap(20, true, 40, true));
// {20=B, 30=C, 40=D}

System.out.println(map.subMap(20, false, 40, false));
// {30=C}

System.out.println(map.headMap(30, true));
// {10=A, 20=B, 30=C}

System.out.println(map.tailMap(30, false));
// {40=D}
```

Range map là view backed bởi map gốc. Xóa hoặc cập nhật mapping qua view sẽ tác động lên map nền và ngược lại. Không thể thêm key nằm ngoài range; thao tác như vậy ném `IllegalArgumentException`.

```java
NavigableMap<Integer, String> middle = map.subMap(20, true, 40, false);
middle.put(25, "B2");  // Hợp lệ, map gốc cũng có key 25.

// middle.put(50, "E"); // IllegalArgumentException: key ngoài range.
```

Các phép so sánh cận cũng tuân theo comparator của map. Khi comparator đảo chiều, khái niệm thấp hơn/cao hơn và thứ tự của các cận được xác định theo comparator đó, không mặc định theo số học tăng dần.

## 6. Reversed view và descendingMap()

`SortedMap.reversed()` là API được bổ sung trong Java 21 qua `SequencedMap`. Nó trả về view có encounter order ngược với map gốc. Với `NavigableMap`, `reversed()` tương đương `descendingMap()` và trả về một `NavigableMap`:

```java
NavigableMap<Integer, String> map = new TreeMap<>();
map.put(10, "A");
map.put(20, "B");
map.put(30, "C");

NavigableMap<Integer, String> reverse = map.reversed();

System.out.println(map);     // {10=A, 20=B, 30=C}
System.out.println(reverse); // {30=C, 20=B, 10=A}

System.out.println(reverse.firstEntry()); // 30=C
System.out.println(reverse.lastEntry());  // 10=A
```

Đây là view đảo chiều, không phải bản sao sắp xếp lại dữ liệu. Với `NavigableMap` như `TreeMap`, view được backing bởi map gốc: cập nhật qua view sẽ được phản ánh ở map gốc và ngược lại. Gọi `reverse.reversed()` trả về view có thứ tự tương đương map ban đầu.

Trong reversed view, mọi thao tác có xét thứ tự đều đảo hướng. Ví dụ, `reverse.lowerKey(20)` tương ứng với key lớn hơn 20 trong map gốc; `reverse.firstEntry()` tương ứng với `map.lastEntry()`. Vì vậy, hãy đọc các phép lower/floor/ceiling/higher theo comparator hiện hành của chính view.

Đối với biến chỉ có kiểu `SortedMap`, kiểu trả về của `reversed()` là `SortedMap`. Nếu cần gọi các phép tìm kiếm `lowerEntry`, `floorEntry`, `ceilingEntry`, `higherEntry` trên view, hãy giữ kiểu `NavigableMap` hoặc dùng `NavigableMap.reversed()`:

```java
NavigableMap<Integer, String> descending = map.reversed();
System.out.println(descending.lowerEntry(20));
```

## 7. Những lưu ý khi dùng TreeMap và sorted map

### Key phải so sánh được

Với natural ordering, key phải triển khai `Comparable` và các key phải tương thích với nhau. Với comparator, comparator phải có khả năng so sánh mọi cặp key mà map có thể chứa. Ví dụ:

```java
record UserId(String value) { }

Comparator<UserId> byValue = Comparator.comparing(UserId::value);
NavigableMap<UserId, String> users = new TreeMap<>(byValue);
users.put(new UserId("u-02"), "Bình");
users.put(new UserId("u-01"), "An");

System.out.println(users.firstEntry());
// UserId[value=u-01]=An
```

Natural ordering của `UserId` không có sẵn vì record này không triển khai `Comparable`; comparator cung cấp quy tắc so sánh tường minh.

### Null key phụ thuộc ordering

`TreeMap` dùng natural ordering không chấp nhận null key. Nếu dùng comparator cho phép so sánh null, map có thể chấp nhận null key theo hợp đồng comparator. Không nên dựa vào việc một implementation cụ thể cho phép null nếu comparator không định nghĩa rõ hành vi đó.

### Entry snapshot và view có khác nhau

`firstEntry`, `lastEntry`, `lowerEntry`, `floorEntry`, `ceilingEntry`, `higherEntry`, `pollFirstEntry` và `pollLastEntry` trả snapshot entry không cho phép thay đổi map bằng `setValue`. Trong khi đó, `entrySet`, `sequencedEntrySet`, `navigableKeySet`, `subMap` và `reversed` là các view được liên kết với map theo hợp đồng tương ứng. Phân biệt hai loại này để tránh kỳ vọng sửa snapshot sẽ cập nhật dữ liệu gốc.

### Không mặc định mọi SortedMap đều có cùng hiệu năng

`SortedMap` và `NavigableMap` là interface, không áp đặt một cấu trúc dữ liệu duy nhất. `TreeMap` dùng cây đỏ-đen và đảm bảo thời gian logarit cho các thao tác cơ bản. Implementation khác có thể có đặc tính khác. Khi hiệu năng là yêu cầu, hãy kiểm tra hợp đồng và tài liệu của implementation cụ thể.

## 8. Chọn đúng map theo yêu cầu

| Yêu cầu chính | Nên dùng | Lý do |
|---|---|---|
| Duyệt key theo natural order | `TreeMap` / `SortedMap` | Encounter order theo thứ tự key |
| Duyệt key theo quy tắc riêng | `TreeMap` với `Comparator` | Comparator quyết định vị trí mapping |
| Tìm key gần nhất với một mốc | `NavigableMap` | Có lower/floor/ceiling/higher |
| Lấy một khoảng key với cận rõ ràng | `NavigableMap.subMap/headMap/tailMap` | Chọn inclusive/exclusive cho từng cận |
| Duyệt ngược thứ tự key | `NavigableMap.reversed()` hoặc `descendingMap()` | View đảo có các phép điều hướng tương ứng |
| Đưa mapping tùy ý lên đầu/cuối | `LinkedHashMap` | Hỗ trợ `putFirst` và `putLast` |
| Giữ thứ tự truy cập để làm LRU | Access-order `LinkedHashMap` | Truy cập mapping sẽ cập nhật vị trí |

Điểm cần nhớ của Java 21: `SortedMap` đã là một `SequencedMap`, nhưng việc có encounter order không có nghĩa là implementation phải hỗ trợ mọi thao tác định vị. Với sorted map, comparator sở hữu thứ tự; `putFirst()` và `putLast()` luôn ném `UnsupportedOperationException`. Hãy dùng các thao tác tìm kiếm, range view và reversed view để làm việc với thứ tự đã sắp xếp.

## Tài liệu tham khảo chính thức

- [Oracle Java SE 21 API — SortedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SortedMap.html)
- [Oracle Java SE 21 API — NavigableMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/NavigableMap.html)
- [Oracle Java SE 21 API — TreeMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/TreeMap.html)
- [Oracle Java SE 21 API — SequencedMap](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/SequencedMap.html)
- [Oracle Java SE 21 — Creating Sequenced Collections, Sets, and Maps](https://docs.oracle.com/en/java/javase/21/core/creating-sequenced-collections-sets-and-maps.html)
- [OpenJDK JEP 431 — Sequenced Collections](https://openjdk.org/jeps/431)
