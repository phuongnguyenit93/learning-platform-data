# Tra cứu ngưỡng, khoảng dữ liệu với NavigableSet và NavigableMap trong Java

Khi một hệ thống phải tìm **mức ngưỡng gần nhất**, **sự kiện gần một mốc thời gian**, hoặc **dữ liệu nằm giữa hai cận**, việc duyệt toàn bộ `List`/`Map` và lọc thủ công có thể vừa chậm vừa dễ sai quy tắc **bao gồm/loại trừ điểm biên**. Java Collections Framework cung cấp hai interface chuyên dụng:

- **`NavigableSet<E>`**: tập các phần tử **không trùng theo comparator**, được sắp xếp, cho phép tra cứu phần tử gần nhất trước/sau ngưỡng, truy vấn các đoạn và duyệt theo chiều ngược.
- **`NavigableMap<K,V>`**: ánh xạ khóa → giá trị, trong đó **khóa được sắp xếp**, cho phép lấy mục có khóa gần nhất trước/sau ngưỡng, truy vấn khoảng khóa, duyệt theo chiều ngược và lấy view các khóa dưới dạng `NavigableSet<K>`.

Bài thuộc nhóm **Thực hành**, tập trung đúng yêu cầu **“Tra cứu ngưỡng, khoảng dữ liệu với NavigableSet, NavigableMap”**. Mọi API và cách sử dụng dưới đây còn áp dụng trong **Java 17+ và Java SE 26**; tránh các mẹo collection đã lỗi thời hoặc lẫn lộn với những API không có hợp đồng tương đương.

Một chương trình **`NavigableRangeDemo.java`** hoàn chỉnh đã được **biên dịch bằng `javac --release 17 -encoding UTF-8` và chạy thành công trên JDK trong workspace, đạt 67/67 kiểm tra PASS**. Nó dùng `TreeSet<Integer>` cho ngưỡng điểm, `TreeMap<Integer,String>` cho bảng mức dịch vụ, `TreeMap<LocalDate,Integer>` cho dữ liệu theo ngày, và `ConcurrentSkipListMap` để minh họa cấu trúc có hỗ trợ concurrent access. Các kiểm tra bao phủ strict/inclusive boundaries, half-open intervals, live/backed views, descending navigation, entries dạng snapshot, null, comparator, mutation và exceptions — không dùng database, thư viện ngoài hoặc kết nối mạng.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Chọn `NavigableSet` hay `NavigableMap` theo mô hình dữ liệu: chỉ cần khóa/điểm, hay cần khóa kèm giá trị.
2. Phân biệt `lower`, `floor`, `ceiling`, `higher` ở cả Set và Map.
3. Hiểu `*Entry` khác `*Key` trong `NavigableMap`; xử lý `null` khi không có ứng viên.
4. Truy vấn khoảng bằng `subSet`/`subMap`, `headSet`/`headMap`, `tailSet`/`tailMap`.
5. Dùng cặp boolean `fromInclusive` và `toInclusive` để tránh lỗi off-by-one.
6. Áp dụng khoảng **nửa mở `[from, to)`** cho dữ liệu ngày tháng và sự kiện.
7. Nhớ `descendingSet`/`descendingMap` tạo **view với thứ tự đảo**, nên ý nghĩa `floor/ceiling` và thứ tự tham số range đảo theo comparator.
8. Phân biệt **view có liên kết với backing collection** và **copy độc lập**.
9. Biết `pollFirst/pollLast` và `pollFirstEntry/pollLastEntry` có thể **xóa** dữ liệu.
10. Biết `first/last/firstKey/lastKey` xử lý tập/map rỗng khác `firstEntry/pollFirst`.
11. Hiểu `NavigableMap` navigation entries là **snapshot mappings**, không sửa map bằng `entry.setValue`.
12. Biết `navigableKeySet()` là key view có thể xóa mapping nhưng không thêm key riêng lẻ.
13. Chọn comparator có hợp đồng phù hợp với equality; hiểu trường hợp `String.CASE_INSENSITIVE_ORDER` gộp keys khác chữ hoa/thường.
14. Phân biệt `TreeSet/TreeMap` không thread-safe với `ConcurrentSkipListSet/ConcurrentSkipListMap` có concurrent access.
15. Xử lý giá trị null khác với “không có key”, và tránh null keys trong natural-order tree.
16. Viết kiểm thử biên: nhỏ hơn min, bằng ngưỡng, giữa hai ngưỡng, lớn hơn max, khoảng rỗng, khoảng đảo, mutation ngoài bounds.
17. Chạy và giải thích 67 assertions của chương trình thực hành.

## 2. Hiểu thứ tự sắp xếp trước khi tìm ngưỡng

`TreeSet` và `TreeMap` thực thi tương ứng `NavigableSet` và `NavigableMap`. Các phần tử/khóa được sắp xếp theo:

- **Natural ordering**: đối tượng có `Comparable`, ví dụ `Integer`, `String`, `LocalDate`.
- **Comparator tùy chọn**: đối tượng `Comparator<? super T>` được truyền vào constructor.

Ví dụ dữ liệu ngưỡng điểm:

```text
[10, 20, 35, 50, 80]
                 ^
               score=42
floor(42)   -> 35
ceiling(42) -> 50
```

Nếu dùng `TreeSet<Integer>`, thứ tự tự nhiên là tăng dần. Nhưng nếu tạo `TreeSet<>(Comparator.reverseOrder())`, phương thức tìm ngưỡng áp dụng **thứ tự comparator đảo**. Các từ “lớn hơn/nhỏ hơn” trong `NavigableSet`, `NavigableMap` đều được hiểu theo **ordering của collection**, không nhất thiết theo ý nghĩa số học hoặc thời gian tăng dần.

### 2.1. Tính duy nhất dựa trên comparator

`TreeSet` chỉ chứa một phần tử cho mỗi lớp tương đương theo so sánh `compare(a,b)==0`; `TreeMap` xem hai keys tương đương nếu comparator coi chúng bằng nhau. Vì vậy:

```java
NavigableSet<String> users =
        new TreeSet<>(String.CASE_INSENSITIVE_ORDER);

users.add("Alpha");
boolean inserted = users.add("ALPHA"); // false
```

Đây là **mảnh code** và biểu hiện có chủ ý của case-insensitive comparator. `"Alpha".equals("ALPHA")` là false nhưng comparator coi chúng bằng nhau; kiểu ordering này không nhất quán với `equals`, có thể làm kết quả khác hợp đồng trực giác của `Set`/`Map`. Nếu các mã business thực sự phải phân biệt chữ hoa/thường, **không dùng case-insensitive comparator** cho khóa định danh.

### 2.2. Đặc tính thời gian

Với `TreeSet`/`TreeMap`, các thao tác cơ bản như `add/put`, `remove`, `contains/get` được tài liệu hóa với chi phí **O(log n)**. Một thao tác tìm vị trí cận bằng cây có hiệu quả hơn duyệt toàn bộ collection không sắp xếp. Khi **duyệt k phần tử** của một range view, vẫn cần chi phí tỷ lệ với số phần tử thực sự duyệt.

Đừng hứa mỗi operation của mọi implementation là O(log n) vì `NavigableSet`/`NavigableMap` là **interfaces**, không chỉ riêng cây đỏ-đen. `ConcurrentSkipListMap` có tính chất hiệu năng và concurrency khác; `descending` views có thể kém tối ưu hơn ascending trên một số implementation.

## 3. Các phương thức tra cứu ngưỡng của NavigableSet

Giả sử:

```java
NavigableSet<Integer> scores =
        new TreeSet<>(List.of(10, 20, 35, 50, 80));
```

Trong `NavigableSet<E>`:

| API | Điều kiện theo thứ tự của Set | Kết quả với mốc `35` |
| --- | --- | --- |
| `lower(35)` | Phần tử lớn nhất **nhỏ hơn** 35: `< 35`. | 20 |
| `floor(35)` | Phần tử lớn nhất **≤ 35`. | 35 |
| `ceiling(35)` | Phần tử nhỏ nhất **≥ 35`. | 35 |
| `higher(35)` | Phần tử nhỏ nhất **lớn hơn** 35: `> 35`. | 50 |

**Strict** là `lower/higher`; **inclusive** là `floor/ceiling`.

### 3.1. Khi mốc không tồn tại trong set

Ví dụ muốn tra cứu điểm 34:

```java
Integer below = scores.floor(34);  // 20
Integer above = scores.ceiling(34); // 35
```

Nếu không có ứng viên phù hợp, phương thức trả `null`:

```java
scores.lower(10);  // null: không có điểm thấp hơn min.
scores.higher(80); // null: không có điểm cao hơn max.
```

Các đoạn này là **mảnh code**, chưa bao gồm imports/main. Không viết:

```java
int tier = scores.floor(-1); // NullPointerException khi unbox null.
```

Nếu yêu cầu là “tìm mức nhỏ hơn hoặc bằng giá trị hiện tại”, nên:

```java
Integer eligible = scores.floor(inputScore);
if (eligible == null) {
    // Không có mức hợp lệ, trả kết quả nghiệp vụ rõ ràng.
} else {
    // Dùng eligible; tránh tự chọn ngưỡng 0 ngoài dữ liệu.
}
```

Ví dụ kiểm tra thật của bài xác nhận `scores.lower(10)==null` và `scores.higher(80)==null`.

### 3.2. Tìm “mức kế tiếp” khác tìm “mức hiện tại”

Với `score = 35`:

- `floor(35) == 35`: mức cao nhất chưa vượt score.
- `lower(35) == 20`: mức trước đó **thấp hơn nghiêm ngặt**.
- `ceiling(35) == 35`: mức thấp nhất không dưới score.
- `higher(35) == 50`: mức kế tiếp **cao hơn nghiêm ngặt**.

Khi dùng trong logic phân cấp, đừng thay `higher` bằng `ceiling` nếu yêu cầu thật sự là “mức tiếp theo” mà score đã trùng ngưỡng.

## 4. NavigableSet: truy vấn một khoảng

`NavigableSet` có các overload với cờ inclusive rõ ràng:

```java
NavigableSet<E> subSet(
        E fromElement, boolean fromInclusive,
        E toElement, boolean toInclusive);

NavigableSet<E> headSet(E toElement, boolean inclusive);
NavigableSet<E> tailSet(E fromElement, boolean inclusive);
```

Đây là chữ ký minh họa generic, không phải file Java có thể biên dịch riêng. Ý nghĩa:

- `subSet(from, true, to, false)` chọn khoảng **`[from, to)`**.
- `subSet(from, true, to, true)` chọn **`[from, to]`**.
- `headSet(to, false)` chọn mọi phần tử **`< to`**.
- `headSet(to, true)` chọn mọi phần tử **`≤ to`**.
- `tailSet(from, false)` chọn mọi phần tử **`> from`**.
- `tailSet(from, true)` chọn mọi phần tử **`≥ from`**.

### 4.1. Biên và kết quả mẫu

Dữ liệu gốc `[10,20,35,50,80]`:

| Truy vấn | Kết quả |
| --- | --- |
| `subSet(20,true,50,false)` | `[20,35]` |
| `subSet(20,true,50,true)` | `[20,35,50]` |
| `headSet(35,false)` | `[10,20]` |
| `tailSet(35,false)` | `[50,80]` |
| `subSet(35,true,35,true)` | `[35]` |
| `subSet(35,true,35,false)` | `[]` |

Hai đầu mút bằng nhau **không mặc định là lỗi**; chúng tạo tập rỗng trừ khi cả hai inclusive và phần tử có mặt. Ngược lại, một `from` **lớn hơn `to` theo comparator** gây `IllegalArgumentException`.

### 4.2. Một live view, không phải bản sao

`NavigableSet<Integer> window = scores.subSet(20,true,50,false)` trả về một **view được backed bởi `scores`**:

```java
NavigableSet<Integer> window =
        scores.subSet(20, true, 50, false);

scores.add(40); // window thấy 40.
window.remove(35); // scores cũng mất 35.
window.add(30); // scores xuất hiện 30.
```

Mỗi thao tác này thay đổi **cùng dữ liệu nền**. View không có cache/bản sao độc lập. Nếu cố thêm `window.add(99)`, `TreeSet` ném `IllegalArgumentException` vì 99 vượt khỏi cận của view.

**Đặc biệt:** thay đổi map/set gốc khi đang chạy iterator của view có thể tạo `ConcurrentModificationException` (best-effort fail-fast), hoặc kết quả không xác định theo Javadoc view. Đừng sửa cấu trúc đồng thời với for-each trên `TreeSet/TreeMap`. Nếu cần sửa trong vòng lặp, xem contract của `Iterator.remove` hoặc thu keys cần xóa rồi xử lý sau, hoặc chọn concurrent implementation phù hợp.

### 4.3. Bản sao và read-only view

Nếu cần ảnh chụp độc lập ở thời điểm truy vấn:

```java
NavigableSet<Integer> copy = new TreeSet<>(window);
```

`copy` không tự nhận thay đổi mới của `scores`. Nếu cần **bản sao chỉ đọc**:

```java
NavigableSet<Integer> frozen =
        Collections.unmodifiableNavigableSet(
                new TreeSet<>(window));
```

Đây là các mảnh code minh họa. `Collections.unmodifiableNavigableSet(window)` **chỉ khóa quyền sửa qua wrapper**, nhưng backing view vẫn có thể thay đổi qua `scores`. Muốn snapshot, hãy **copy trước rồi mới bọc unmodifiable**.

## 5. Set đảo chiều: descendingSet

`scores.descendingSet()` trả **view với comparator đảo chiều**, không phải một list đã được sort ngược riêng.

Với `scores=[10,20,35,50,80]`:

```text
Ascending:  [10, 20, 35, 50, 80]
Descending: [80, 50, 35, 20, 10]
```

Điểm dễ sai:

```java
NavigableSet<Integer> descending = scores.descendingSet();

descending.floor(36);   // 50 theo comparator đảo.
descending.ceiling(36); // 35 theo comparator đảo.
```

Trong `descending`, `floor` nghĩa **phần tử lớn nhất không vượt 36 theo reverse comparator**, tức 50 theo thứ tự số học. `ceiling` đảo tương tự. **Không dùng descendingSet.floor như floor theo số học**.

### 5.1. Bounds cũng đảo

Muốn lấy các số 80, 50, 35 theo chiều giảm:

```java
descending.subSet(80, true, 35, true); // [80,50,35]
```

Với descending comparator, **80 đứng trước 35**, nên đây là thứ tự cận hợp lệ. `descending.subSet(35,true,80,true)` là chiều ngược so với comparator của view và bị `IllegalArgumentException`.

### 5.2. pollFirst có tác dụng xóa

`descending.pollFirst()` lấy và **xóa phần tử đầu tiên trong view**, tức **80** trong ví dụ; dữ liệu `scores` cũng mất 80. Với set tăng dần, `scores.pollLast()` xóa phần tử lớn nhất còn lại.

Ngược lại `first()`/`last()` **chỉ xem**; khi set rỗng chúng ném `NoSuchElementException`. `pollFirst()/pollLast()` trả `null` khi rỗng. Hãy phân biệt read-only lookup và mutation trong logic production.

## 6. NavigableMap: tra cứu ngưỡng và giá trị

Khi mỗi ngưỡng gắn với **một quy tắc hoặc nhãn giá trị**, dùng `NavigableMap<K,V>` thay vì chỉ `NavigableSet`:

```java
NavigableMap<Integer, String> tiers = new TreeMap<>();

tiers.put(0, "START");
tiers.put(100, "PLUS");
tiers.put(250, "PRO");
tiers.put(500, "ELITE");
```

Một yêu cầu nghiệp vụ: **“Điểm 180 được hưởng mức dịch vụ nào đã đạt ngưỡng?”**

```java
Map.Entry<Integer, String> eligible = tiers.floorEntry(180);
// Key=100; Value="PLUS".
```

`floorEntry` trả entry có **khóa lớn nhất ≤ 180**. Từ đó business logic chọn `PLUS`. Nếu muốn ngưỡng sắp tới, dùng `ceilingEntry(180)` trả `250 → PRO`.

### 6.1. Bảng phương thức cùng ý nghĩa

| NavigableMap method | So sánh khóa | Khi tra ngưỡng 180 |
| --- | --- | --- |
| `lowerKey(key)` | Khóa lớn nhất `< key`. | 100 |
| `floorKey(key)` | Khóa lớn nhất `≤ key`. | 100 |
| `ceilingKey(key)` | Khóa nhỏ nhất `≥ key`. | 250 |
| `higherKey(key)` | Khóa nhỏ nhất `> key`. | 250 |
| `lowerEntry(key)` | Cặp khóa–giá trị tại key `< key` gần nhất. | `100=PLUS` |
| `floorEntry(key)` | Cặp tại key `≤ key` gần nhất. | `100=PLUS` |
| `ceilingEntry(key)` | Cặp tại key `≥ key` gần nhất. | `250=PRO` |
| `higherEntry(key)` | Cặp tại key `> key` gần nhất. | `250=PRO` |

Ở đây kết quả với key=180 tình cờ làm `lower==floor` và `higher==ceiling` vì 180 không có trong map. Khi key **bằng ngưỡng**, sự khác biệt mới rõ:

- `tiers.lowerKey(100) == 0`.
- `tiers.floorKey(100) == 100`.
- `tiers.ceilingKey(100) == 100`.
- `tiers.higherKey(100) == 250`.

### 6.2. Khi nào chọn *Key, khi nào *Entry?

- Chỉ cần **điểm mốc**: `floorKey`, `ceilingKey`.
- Cần **mốc kèm nội dung** như tên gói, mức thuế, giới hạn: `floorEntry`, `ceilingEntry`.
- Cần **bản ghi đầu/cuối**: `firstEntry`, `lastEntry`.
- Cần **xóa và lấy** bản ghi đầu/cuối: `pollFirstEntry`, `pollLastEntry`.

Với ngưỡng thấp hơn min, `tiers.floorEntry(-1) == null`; với mốc lớn hơn max, `tiers.ceilingEntry(999) == null`. Không dereference `.getValue()` khi entry là null.

### 6.3. Chính sách nghiệp vụ phải rõ ở ngoài cấu trúc

`floorEntry` chỉ tìm thứ tự, không quyết định đúng/sai của business logic. Nếu một đơn hàng có score âm và không có ngưỡng ≤ score:

- Có thể trả lỗi validation.
- Có thể báo “không đủ điều kiện”.
- Có thể áp một quy tắc fallback được cấu hình rõ ràng.

**Không tự trả ngưỡng 0 hoặc giá trị của firstEntry như “mặc định” nếu yêu cầu không cho phép.** Cấu trúc dữ liệu trả không có ứng viên là thông tin hợp lệ cần được xử lý.

## 7. NavigableMap: truy vấn khoảng khóa

`NavigableMap` hỗ trợ:

```java
NavigableMap<K, V> subMap(
        K fromKey, boolean fromInclusive,
        K toKey, boolean toInclusive);

NavigableMap<K, V> headMap(K toKey, boolean inclusive);
NavigableMap<K, V> tailMap(K fromKey, boolean inclusive);
```

Đây là chữ ký minh họa generic.

Giả sử `tiers` có keys `[0,100,250,500]`:

```java
NavigableMap<Integer, String> middle =
        tiers.subMap(100, true, 500, false);
```

`middle` ban đầu chứa keys 100 và 250, **không gồm 500**. Đây là **live backed view**:

```java
tiers.put(350, "PREMIUM");   // middle nhìn thấy 350.
middle.put(400, "BUSINESS"); // tiers nhìn thấy 400.
middle.remove(250);         // tiers cũng mất key 250.
```

`middle.put(900, "...")` ném `IllegalArgumentException`; 900 vượt giới hạn. Nếu thay đổi `tiers` cùng lúc thread khác duyệt `middle` mà không đồng bộ, `TreeMap` không bảo đảm thread safety.

### 7.1. Hai tham số hay bốn tham số?

`SortedMap.subMap(from, to)`/`SortedSet.subSet(from,to)` mặc định **from inclusive, to exclusive**. Với `NavigableMap` và `NavigableSet`, dùng overload 4 tham số boolean khi muốn biểu đạt ranh giới rõ ràng, nhất là lúc kết hợp nhiều rules.

`subMap(100,true,100,true)` chỉ có entry key 100 (nếu key này tồn tại), còn `subMap(100,true,100,false)` tạo view rỗng.

Nếu `fromKey > toKey` theo comparator, ném `IllegalArgumentException`. Không đảo nhầm hai đầu mút rồi giả định phương thức sẽ tự sắp xếp chúng.

### 7.2. Key set view từ Map

`tiers.navigableKeySet()` trả một `NavigableSet<K>` view các khóa của map:

```java
NavigableSet<Integer> keys = tiers.navigableKeySet();
keys.remove(350); // Cũng xóa mapping 350 ở tiers.
```

`keys.add(123)` không có giá trị `V` đi kèm, vì vậy **không hỗ trợ thêm key** và sẽ ném `UnsupportedOperationException` trên TreeMap. Đừng tạo key mới bằng cách sửa key view; phải gọi `tiers.put(key,value)`.

`tiers.descendingKeySet()` trả view khóa theo chiều ngược. Khi chỉ cần keys, không cần chuyển `Map.Entry` thành list rồi sort thủ công.

## 8. NavigableMap entries: snapshot khác backed views

Javadoc `NavigableMap` quy định các phương thức:

```text
lowerEntry, floorEntry, ceilingEntry, higherEntry,
firstEntry, lastEntry, pollFirstEntry, pollLastEntry
```

trả về **`Map.Entry` snapshot của mapping tại thời điểm gọi**, không cho cập nhật underlying map thông qua optional `Map.Entry.setValue`.

Ví dụ được xác minh:

```java
Map.Entry<Integer, String> snapshot = tiers.floorEntry(400);

tiers.put(400, "BUSINESS_NEW");
// snapshot.getValue() vẫn là "BUSINESS"
// tiers.get(400) là "BUSINESS_NEW"
```

Với `TreeMap`, gọi `snapshot.setValue("INVALID")` ném `UnsupportedOperationException`. Nếu cần sửa giá trị thật, dùng:

```java
tiers.put(snapshot.getKey(), "BUSINESS_NEW");
```

Phân biệt:

- **`subMap`** là view liên kết: nhìn thấy và tác động lên map gốc.
- **`navigableKeySet`** là view liên kết: xóa key xóa mapping.
- **`descendingMap`** là view liên kết: thay thứ tự nhìn dữ liệu.
- **`floorEntry/firstEntry`** là snapshot entry: không phải live mutable handle.

Nếu đang dùng iterator của `entrySet()`, `Map.Entry` thu được có contract khác tùy implementation; **không tự suy** mọi entry đều editable chỉ vì là `Map.Entry`.

### 8.1. Value null không đồng nghĩa key vắng mặt

`TreeMap` với natural ordering cho phép **null values** (nhưng không cho null keys trong ví dụ). Sau:

```java
tiers.put(400, null);

boolean exists = tiers.containsKey(400); // true
String value = tiers.get(400);           // null
```

`tiers.get(400)==null` có thể vì **key 400 tồn tại với value null** hoặc key không tồn tại. Để phân biệt, dùng `containsKey` hoặc `floorEntry(400)` rồi kiểm tra key/entry.

`Map.Entry<Integer,String> nearest = tiers.floorEntry(400)` vẫn **không null** khi entry key=400 tồn tại và value của nó là null.

Không nhầm `null` trả từ navigation methods khi **không có entry** với `null` là **value của một entry có thật**.

## 9. Bài toán thời gian: khoảng ngày nửa mở

Giả sử các giá trị số lượng giao dịch theo ngày:

```text
2026-10-01 -> 10
2026-10-03 -> 30
2026-10-05 -> 50
2026-10-09 -> 90
2026-10-13 -> 130
```

Dùng `TreeMap<LocalDate,Integer>` vì `LocalDate` có natural ordering theo thứ tự thời gian. Để lấy từ ngày 03/10/2026 **bao gồm** đến trước ngày 13/10/2026:

```java
NavigableMap<LocalDate,Integer> window =
        timeline.subMap(
                LocalDate.of(2026, 10, 3), true,
                LocalDate.of(2026, 10, 13), false);
```

Kết quả là các ngày **03, 05, 09**, không gồm 13. Ký hiệu chuẩn: **`[startInclusive, endExclusive)`**.

### 9.1. Vì sao khoảng nửa mở hữu ích?

- Hai cửa sổ liên tiếp `[01,13)` và `[13,20)` **không đếm trùng ngày 13**.
- Dễ nối/chia các đợt xử lý hoặc phân trang theo ngày.
- Biểu đạt rõ “từ đầu ngày A đến trước đầu ngày B”.
- Tránh tính toán “23:59:59.999” dễ sai precision và timezone.

Với dữ liệu là **timestamp tuyệt đối**, nên dùng kiểu `Instant` hoặc loại thời gian khác phù hợp dữ liệu, và xác định timezone cho ngưỡng nghiệp vụ trước khi quy đổi. `LocalDate` phù hợp dữ liệu theo **ngày lịch**, không tự là timestamp UTC.

### 9.2. Tra cứu sự kiện gần mốc

Nếu không có dữ liệu ngày 04/10, nhưng có ngày 03 và 05:

```java
timeline.floorEntry(LocalDate.of(2026, 10, 4));
// Trả entry 2026-10-03 -> 30.

timeline.ceilingEntry(LocalDate.of(2026, 10, 4));
// Trả entry 2026-10-05 -> 50.
```

Ứng dụng có thể dùng `floorEntry` cho **last-known-value** tại/trước mốc, `ceilingEntry` cho bản ghi kế tiếp tại/sau mốc. Chỉ áp dụng last-known-value khi nghiệp vụ cho phép; không tự biến dữ liệu ngày cũ thành dữ liệu ngày mới không có chứng cứ.

### 9.3. Live date range

Nếu `timeline.put(2026-10-07,70)` sau khi view đã được tạo, `window` sẽ có thêm ngày 07. Nếu `window.remove(2026-10-05)`, map gốc cũng mất ngày 05.

Muốn dùng một tập dữ liệu bất biến cho báo cáo:

```java
NavigableMap<LocalDate,Integer> snapshot =
        new TreeMap<>(window);
```

Nếu cần chỉ đọc, bọc một **copy riêng** bằng `Collections.unmodifiableNavigableMap(new TreeMap<>(window))`. Không kỳ vọng `Collections.unmodifiableNavigableMap(window)` không thay đổi khi một thành phần khác sửa backing `timeline`.

## 10. Khi đảo thứ tự NavigableMap

`descendingMap()` trả view có **ordering đảo**. Nếu keys tăng dần của map là `0,100,350,400,500`, descending key set là `500,400,350,100,0`.

Điểm thường bị quên: khi gọi `subMap` trên **descending map**, hai đầu mút phải **đúng thứ tự của comparator đang dùng**:

```java
NavigableMap<Integer,String> desc = tiers.descendingMap();

NavigableMap<Integer,String> highFirst =
        desc.subMap(500, true, 100, false);
```

Các keys được lấy sẽ trong khoảng số học `(100,500]`, nhưng **duyệt theo chiều giảm**. Nếu muốn chuyển ngược từ `desc` sang ascending, có thể dùng `desc.descendingMap()`, nó là một view về thứ tự gốc, không đòi tạo bản sao dữ liệu.

Không suy rằng `desc.floorKey(175)` giống `tiers.floorKey(175)`. `floor/higher/ceiling/lower` đều theo **thứ tự comparator hiện tại**, kể cả comparator đảo.

## 11. TreeMap, TreeSet và dữ liệu concurrent

`TreeMap` và `TreeSet` có hiệu năng tốt cho tra cứu có thứ tự trong một thread hoặc khi có đồng bộ ở tầng ngoài, nhưng **không synchronized mặc định**. Nếu nhiều threads cùng truy cập và có ít nhất một thread sửa, cần một chiến lược thread safety rõ ràng.

### 11.1. Khi có nhiều writers/readers

Các implementation hiện hành:

- `ConcurrentSkipListSet<E>`: tập sorted/navigable hỗ trợ concurrent access.
- `ConcurrentSkipListMap<K,V>`: map sorted/navigable hỗ trợ concurrent access.

`ConcurrentSkipListMap` có thể thực hiện `floorKey`, `ceilingEntry`, `subMap` tương tự interface, đồng thời cho nhiều threads truy cập. Tuy nhiên:

- Iterators là **weakly consistent**, không phải snapshot đồng bộ của toàn collection.
- Nhiều operation ghép liên tiếp không đương nhiên tạo một transaction atomic; cần phân tích invariant.
- Không cho **null keys/values**.
- Một số bulk operations không bảo đảm atomic giữa concurrent modifications.
- Descending view có thể chậm hơn ascending trong implementation skip list.
- Với `ConcurrentSkipListSet`, `size()` có thể cần duyệt và không nhất thiết phản ánh một snapshot ổn định khi có concurrent writes.

Đừng “thêm Concurrent vào tên class” rồi cho rằng toàn bộ nghiệp vụ đọc khoảng và cập nhật nhiều bản ghi đã trở thành atomic. Nếu cần consistent reporting, thiết kế snapshot/locking/versioning ở tầng thích hợp.

### 11.2. Synchronized wrapper vẫn có giới hạn

Có thể dùng các wrappers `Collections.synchronizedSortedMap` hoặc `Collections.synchronizedSortedSet` khi cần đồng bộ basic operations theo wrapper, nhưng khi duyệt views/iterators phải tuân theo yêu cầu khóa thủ công trên wrapper đúng cách. Nếu đã có yêu cầu concurrency cao và truy vấn sorted, `ConcurrentSkipListMap/Set` thường là lựa chọn đáng đánh giá.

Không tự viết:

```java
if (!map.containsKey(key)) {
    map.put(key, value);
}
```

và coi đó là một thao tác atomic trong ứng dụng đa luồng. Dù map thread-safe, chuỗi **check-then-act** vẫn có race; xem `putIfAbsent`/`compute` hoặc cơ chế transaction theo nhu cầu.

## 12. Chương trình Java17+ hoàn chỉnh: NavigableRangeDemo.java

Chương trình chia các test thành bốn nhóm:

1. **`NavigableSet<Integer>`**: 29 kiểm tra thứ tự tự nhiên, strict/inclusive, khoảng nửa mở, view mutations, reversed comparator, poll và exception.
2. **`NavigableMap<Integer,String>`**: 23 kiểm tra ngưỡng, map views, snapshot entries, key sets, null values và empty map.
3. **`NavigableMap<LocalDate,Integer>`**: 11 kiểm tra khoảng theo ngày, floor/ceiling, descending, boundaries và live mutation.
4. **Comparator + `ConcurrentSkipListMap`**: 4 kiểm tra inconsistency và concurrent navigable contracts.

Tổng cộng **67 kiểm tra PASS**, không có số liệu ngẫu nhiên hay phụ thuộc mạng. Java code dùng `List.of`, `Map.entry` và generics, phù hợp với `--release 17`. Không dùng Java 21+ API trong chương trình để giữ compatibility.

### 12.1. Toàn bộ source

**File:** `NavigableRangeDemo.java` — lưu dưới dạng UTF-8:

```java
import java.time.LocalDate;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.NavigableMap;
import java.util.NavigableSet;
import java.util.NoSuchElementException;
import java.util.TreeMap;
import java.util.TreeSet;
import java.util.concurrent.ConcurrentSkipListMap;

public final class NavigableRangeDemo {
    private static int count;

    private static void check(String label, boolean actual) {
        if (!actual) throw new AssertionError(label);
        count++;
        System.out.println(label + "=PASS");
    }

    private static boolean throwsType(
            Class<? extends Throwable> type, Runnable runnable) {
        try {
            runnable.run();
            return false;
        } catch (Throwable ex) {
            return type.isInstance(ex);
        }
    }

    private static <T> List<T> ordered(Iterable<T> source) {
        List<T> result = new ArrayList<>();
        for (T item : source) result.add(item);
        return result;
    }

    private static LocalDate day(int dayOfMonth) {
        return LocalDate.of(2026, 10, dayOfMonth);
    }

    public static void main(String[] args) {
        NavigableSet<Integer> scores =
                new TreeSet<>(List.of(10, 20, 35, 50, 80));
        check("setNaturalOrder",
                ordered(scores).equals(List.of(10, 20, 35, 50, 80)));
        check("setFloorExact", scores.floor(35) == 35);
        check("setLowerStrict", scores.lower(35) == 20);
        check("setCeilingExact", scores.ceiling(35) == 35);
        check("setHigherStrict", scores.higher(35) == 50);
        check("setFloorBetween", scores.floor(34) == 20);
        check("setCeilingBetween", scores.ceiling(34) == 35);
        check("setBelowMinIsNull", scores.lower(10) == null);
        check("setAboveMaxIsNull", scores.higher(80) == null);

        NavigableSet<Integer> window =
                scores.subSet(20, true, 50, false);
        check("setHalfOpenRange",
                ordered(window).equals(List.of(20, 35)));
        check("setClosedRange",
                ordered(scores.subSet(20, true, 50, true))
                        .equals(List.of(20, 35, 50)));
        check("setHeadExclusive",
                ordered(scores.headSet(35, false))
                        .equals(List.of(10, 20)));
        check("setTailExclusive",
                ordered(scores.tailSet(35, false))
                        .equals(List.of(50, 80)));
        check("setEqualClosedSingleton",
                ordered(scores.subSet(35, true, 35, true))
                        .equals(List.of(35)));
        check("setEqualHalfOpenEmpty",
                scores.subSet(35, true, 35, false).isEmpty());

        NavigableSet<Integer> descending = scores.descendingSet();
        check("setDescendingView",
                ordered(descending).equals(List.of(80, 50, 35, 20, 10)));
        check("setDescendingFloorUsesComparator",
                descending.floor(36) == 50);
        check("setDescendingCeilingUsesComparator",
                descending.ceiling(36) == 35);
        check("setDescendingRangeReverseBounds",
                ordered(descending.subSet(80, true, 35, true))
                        .equals(List.of(80, 50, 35)));
        check("setDescendingWrongOrderRejected",
                throwsType(IllegalArgumentException.class,
                        () -> descending.subSet(35, true, 80, true)));

        scores.add(40);
        check("setViewSeesBackingInsert",
                ordered(window).equals(List.of(20, 35, 40)));
        window.remove(35);
        check("setViewRemovalChangesBacking", !scores.contains(35));
        window.add(30);
        check("setViewInsertChangesBacking", scores.contains(30));
        check("setOutOfRangeInsertRejected",
                throwsType(IllegalArgumentException.class,
                        () -> window.add(99)));
        check("setDescendingPollFirstRemovesLargest",
                descending.pollFirst() == 80 && !scores.contains(80));
        check("setPollLastRemovesLargestRemaining",
                scores.pollLast() == 50 && !scores.contains(50));
        check("setEmptyPollReturnsNull",
                new TreeSet<Integer>().pollFirst() == null);
        check("setEmptyFirstThrows",
                throwsType(NoSuchElementException.class,
                        () -> new TreeSet<Integer>().first()));
        check("setNaturalNullRejected",
                throwsType(NullPointerException.class,
                        () -> scores.floor(null)));

        NavigableMap<Integer, String> tiers = new TreeMap<>();
        tiers.put(0, "START");
        tiers.put(100, "PLUS");
        tiers.put(250, "PRO");
        tiers.put(500, "ELITE");
        check("mapFloorThreshold",
                tiers.floorEntry(180).equals(Map.entry(100, "PLUS")));
        check("mapCeilingThreshold",
                tiers.ceilingEntry(180).equals(Map.entry(250, "PRO")));
        check("mapLowerStrict", tiers.lowerKey(100) == 0);
        check("mapHigherStrict", tiers.higherKey(100) == 250);
        check("mapFloorExact",
                tiers.floorEntry(250).equals(Map.entry(250, "PRO")));
        check("mapBelowMinimumNull", tiers.floorEntry(-1) == null);
        check("mapAboveMaximumNull", tiers.ceilingEntry(999) == null);
        check("mapFirstAndLast",
                tiers.firstKey() == 0 && tiers.lastKey() == 500);

        NavigableMap<Integer, String> subMap =
                tiers.subMap(100, true, 500, false);
        check("mapHalfOpenRange",
                ordered(subMap.navigableKeySet())
                        .equals(List.of(100, 250)));
        tiers.put(350, "PREMIUM");
        check("mapViewSeesBackingInsert", subMap.containsKey(350));
        subMap.put(400, "BUSINESS");
        check("mapViewInsertChangesBacking",
                "BUSINESS".equals(tiers.get(400)));
        check("mapOutOfRangeInsertRejected",
                throwsType(IllegalArgumentException.class,
                        () -> subMap.put(900, "INVALID")));
        subMap.remove(250);
        check("mapViewRemovalChangesBacking", !tiers.containsKey(250));

        NavigableMap<Integer, String> reverseTiers =
                tiers.descendingMap();
        check("mapDescendingOrder",
                ordered(reverseTiers.navigableKeySet())
                        .equals(List.of(500, 400, 350, 100, 0)));
        check("mapDescendingSubMapReverseBounds",
                ordered(reverseTiers.subMap(500, true, 100, false)
                        .navigableKeySet())
                        .equals(List.of(500, 400, 350)));
        check("mapKeySetRemoveChangesBacking",
                tiers.navigableKeySet().remove(350)
                        && !tiers.containsKey(350));
        check("mapKeySetCannotAdd",
                throwsType(UnsupportedOperationException.class,
                        () -> tiers.navigableKeySet().add(123)));

        Map.Entry<Integer, String> snapshot = tiers.floorEntry(400);
        tiers.put(400, "BUSINESS_NEW");
        check("mapNavigationEntryIsSnapshot",
                "BUSINESS".equals(snapshot.getValue())
                        && "BUSINESS_NEW".equals(tiers.get(400)));
        check("mapNavigationEntrySetValueUnsupported",
                throwsType(UnsupportedOperationException.class,
                        () -> snapshot.setValue("INVALID")));
        tiers.put(400, null);
        check("mapNullValueVsAbsent",
                tiers.containsKey(400) && tiers.get(400) == null
                        && tiers.floorEntry(400).getKey() == 400);
        check("mapNaturalNullKeyRejected",
                throwsType(NullPointerException.class,
                        () -> tiers.floorKey(null)));
        check("mapEmptyFirstEntryReturnsNull",
                new TreeMap<Integer, String>().firstEntry() == null);
        check("mapEmptyFirstKeyThrows",
                throwsType(NoSuchElementException.class,
                        () -> new TreeMap<Integer, String>().firstKey()));

        NavigableMap<LocalDate, Integer> timeline = new TreeMap<>();
        timeline.put(day(1), 10);
        timeline.put(day(3), 30);
        timeline.put(day(5), 50);
        timeline.put(day(9), 90);
        timeline.put(day(13), 130);

        NavigableMap<LocalDate, Integer> days =
                timeline.subMap(day(3), true, day(13), false);
        check("dateRangeHalfOpen",
                ordered(days.navigableKeySet())
                        .equals(List.of(day(3), day(5), day(9))));
        check("dateFloor",
                timeline.floorEntry(day(4)).getKey().equals(day(3)));
        check("dateCeiling",
                timeline.ceilingEntry(day(4)).getKey().equals(day(5)));
        check("dateDescendingOrder",
                ordered(timeline.descendingKeySet())
                        .equals(List.of(day(13), day(9), day(5),
                                day(3), day(1))));
        check("dateDescendingRange",
                ordered(timeline.descendingMap()
                        .subMap(day(13), true, day(3), false)
                        .navigableKeySet())
                        .equals(List.of(day(13), day(9), day(5))));
        check("dateAscendingWrongOrderRejected",
                throwsType(IllegalArgumentException.class,
                        () -> timeline.subMap(day(13), true,
                                day(3), true)));

        timeline.put(day(7), 70);
        check("dateRangeLiveInsert",
                ordered(days.navigableKeySet())
                        .equals(List.of(day(3), day(5),
                                day(7), day(9))));
        days.remove(day(5));
        check("dateRangeRemovalChangesOriginal",
                !timeline.containsKey(day(5)));
        check("dateRangeOutOfRangePutRejected",
                throwsType(IllegalArgumentException.class,
                        () -> days.put(day(1), 999)));
        check("dateHeadExclusive",
                ordered(timeline.headMap(day(9), false)
                        .navigableKeySet())
                        .equals(List.of(day(1), day(3), day(7))));
        check("dateTailInclusive",
                ordered(timeline.tailMap(day(9), true)
                        .navigableKeySet())
                        .equals(List.of(day(9), day(13))));

        NavigableSet<String> caseInsensitive =
                new TreeSet<>(String.CASE_INSENSITIVE_ORDER);
        check("comparatorCanCollapseDistinctEquals",
                caseInsensitive.add("Alpha")
                        && !caseInsensitive.add("ALPHA")
                        && caseInsensitive.size() == 1);

        NavigableMap<Integer, String> concurrent =
                new ConcurrentSkipListMap<>();
        concurrent.put(10, "TEN");
        concurrent.put(30, "THIRTY");
        check("concurrentNavigableFloor",
                concurrent.floorKey(20) == 10);
        NavigableMap<Integer, String> concurrentRange =
                concurrent.subMap(10, true, 30, false);
        concurrent.put(20, "TWENTY");
        check("concurrentRangeLiveView",
                concurrentRange.containsKey(20));
        check("concurrentRejectsNullValue",
                throwsType(NullPointerException.class,
                        () -> concurrent.put(40, null)));

        System.out.println("checks=" + count + "/" + count);
    }
}
```

**Lưu ý về source:** `throwsType` chỉ là helper kiểm tra **đúng loại exception**; việc catch `Throwable` được giới hạn trong test helper, không phải mẫu error-handling khuyến nghị cho business code. Ở ứng dụng thật, bắt các checked/runtime exceptions phù hợp và giữ nguyên nguyên nhân lỗi.

### 12.2. Lệnh chạy

```bash
javac --release 17 -encoding UTF-8 NavigableRangeDemo.java
java NavigableRangeDemo
```

`java.util`, `java.time` và `java.util.concurrent` thuộc module chuẩn **`java.base`**; không cần thư viện khác hay `--add-opens`. Code không yêu cầu database, không tạo file hay kết nối mạng.

### 12.3. Stdout chính xác đã kiểm chứng

```text
setNaturalOrder=PASS
setFloorExact=PASS
setLowerStrict=PASS
setCeilingExact=PASS
setHigherStrict=PASS
setFloorBetween=PASS
setCeilingBetween=PASS
setBelowMinIsNull=PASS
setAboveMaxIsNull=PASS
setHalfOpenRange=PASS
setClosedRange=PASS
setHeadExclusive=PASS
setTailExclusive=PASS
setEqualClosedSingleton=PASS
setEqualHalfOpenEmpty=PASS
setDescendingView=PASS
setDescendingFloorUsesComparator=PASS
setDescendingCeilingUsesComparator=PASS
setDescendingRangeReverseBounds=PASS
setDescendingWrongOrderRejected=PASS
setViewSeesBackingInsert=PASS
setViewRemovalChangesBacking=PASS
setViewInsertChangesBacking=PASS
setOutOfRangeInsertRejected=PASS
setDescendingPollFirstRemovesLargest=PASS
setPollLastRemovesLargestRemaining=PASS
setEmptyPollReturnsNull=PASS
setEmptyFirstThrows=PASS
setNaturalNullRejected=PASS
mapFloorThreshold=PASS
mapCeilingThreshold=PASS
mapLowerStrict=PASS
mapHigherStrict=PASS
mapFloorExact=PASS
mapBelowMinimumNull=PASS
mapAboveMaximumNull=PASS
mapFirstAndLast=PASS
mapHalfOpenRange=PASS
mapViewSeesBackingInsert=PASS
mapViewInsertChangesBacking=PASS
mapOutOfRangeInsertRejected=PASS
mapViewRemovalChangesBacking=PASS
mapDescendingOrder=PASS
mapDescendingSubMapReverseBounds=PASS
mapKeySetRemoveChangesBacking=PASS
mapKeySetCannotAdd=PASS
mapNavigationEntryIsSnapshot=PASS
mapNavigationEntrySetValueUnsupported=PASS
mapNullValueVsAbsent=PASS
mapNaturalNullKeyRejected=PASS
mapEmptyFirstEntryReturnsNull=PASS
mapEmptyFirstKeyThrows=PASS
dateRangeHalfOpen=PASS
dateFloor=PASS
dateCeiling=PASS
dateDescendingOrder=PASS
dateDescendingRange=PASS
dateAscendingWrongOrderRejected=PASS
dateRangeLiveInsert=PASS
dateRangeRemovalChangesOriginal=PASS
dateRangeOutOfRangePutRejected=PASS
dateHeadExclusive=PASS
dateTailInclusive=PASS
comparatorCanCollapseDistinctEquals=PASS
concurrentNavigableFloor=PASS
concurrentRangeLiveView=PASS
concurrentRejectsNullValue=PASS
checks=67/67
```

Có **67 assertion labels PASS và một dòng tổng kết**. Không in identity hashes, timestamps động hoặc dữ liệu môi trường nên stdout là kết quả deterministic trong lần thử nghiệm này. JDK có thể có thông báo khác ngoài stdout nếu chạy với flags riêng; lệnh mặc định ở trên không dùng flags bổ sung.

## 13. Diễn giải các nhóm kiểm tra

### 13.1. Set: các kiểm tra số 1–29

Bắt đầu từ `[10,20,35,50,80]`:

- Các `setFloorExact/setLowerStrict/setCeilingExact/setHigherStrict` khẳng định khác nhau giữa inclusivity và strictness ở đúng ngưỡng.
- `setFloorBetween/setCeilingBetween` kiểm chứng mốc không tồn tại (34).
- `setBelowMinIsNull/setAboveMaxIsNull` kiểm tra không có phần tử phù hợp.
- `setHalfOpenRange/setClosedRange/setHeadExclusive/setTailExclusive` bảo đảm các cận đúng và không thêm nhầm phần tử.
- `setEqualClosedSingleton/setEqualHalfOpenEmpty` bắt lỗi boundary bằng nhau.
- `setDescendingView` và hai assertions `setDescendingFloorUsesComparator/setDescendingCeilingUsesComparator` minh họa thứ tự đảo **ảnh hưởng ngữ nghĩa floor/ceiling**.
- `setDescendingRangeReverseBounds/setDescendingWrongOrderRejected` kiểm tra tham số `subSet` của reversed comparator.
- `setViewSeesBackingInsert/setViewRemovalChangesBacking/setViewInsertChangesBacking` chứng minh backed view hai chiều.
- `setOutOfRangeInsertRejected` bảo vệ cận.
- `setDescendingPollFirstRemovesLargest/setPollLastRemovesLargestRemaining` chứng minh poll là mutation.
- `setEmptyPollReturnsNull/setEmptyFirstThrows` phân biệt empty collection behaviors.
- `setNaturalNullRejected` khẳng định `TreeSet<Integer>` natural ordering không cho null query.

### 13.2. Map: các kiểm tra số 30–52

- `mapFloorThreshold/mapCeilingThreshold`: chọn gói `PLUS` cho score 180 và ngưỡng tiếp theo `PRO`.
- `mapLowerStrict/mapHigherStrict/mapFloorExact`: strict/inclusive khi key bằng ngưỡng.
- `mapBelowMinimumNull/mapAboveMaximumNull`: ranh giới.
- `mapFirstAndLast`: điểm đầu/cuối.
- `mapHalfOpenRange`: chỉ keys trong `[100,500)`.
- `mapViewSeesBackingInsert/mapViewInsertChangesBacking/mapViewRemovalChangesBacking`: view linked với backing map.
- `mapOutOfRangeInsertRejected`: view không cho put key ngoài bounds.
- `mapDescendingOrder/mapDescendingSubMapReverseBounds`: range theo reverse comparator.
- `mapKeySetRemoveChangesBacking` và `mapKeySetCannotAdd`: key set view có thể remove, không hỗ trợ add.
- `mapNavigationEntryIsSnapshot/mapNavigationEntrySetValueUnsupported`: entry từ floorEntry là snapshot, không mutable map handle.
- `mapNullValueVsAbsent`: một key tồn tại với value null vẫn là mapping có thật.
- `mapNaturalNullKeyRejected`: natural-order `TreeMap` không chấp nhận null key.
- `mapEmptyFirstEntryReturnsNull/mapEmptyFirstKeyThrows`: empty map entry/key khác nhau.

### 13.3. Dữ liệu ngày: kiểm tra số 53–63

- `dateRangeHalfOpen`: chỉ ngày 03,05,09 trong `[03,13)`.
- `dateFloor/dateCeiling`: tra bản ghi liền trước/tiếp sau ngày 04.
- `dateDescendingOrder/dateDescendingRange`: thứ tự ngày đảo và bounds đảo.
- `dateAscendingWrongOrderRejected`: map tăng dần từ ngày 13 xuống 03 là invalid.
- `dateRangeLiveInsert/dateRangeRemovalChangesOriginal`: thay đổi qua backing/view thấy ngay.
- `dateRangeOutOfRangePutRejected`: không thêm ngày 01 qua window bắt đầu 03.
- `dateHeadExclusive/dateTailInclusive`: hai kiểu biên riêng.

### 13.4. Comparator và concurrent: kiểm tra 64–67

- `comparatorCanCollapseDistinctEquals`: case-insensitive comparator coi `"Alpha"` và `"ALPHA"` là cùng vị trí.
- `concurrentNavigableFloor`: `ConcurrentSkipListMap` vẫn hỗ trợ navigation theo khóa.
- `concurrentRangeLiveView`: concurrent map trả range view liên kết với dữ liệu nền.
- `concurrentRejectsNullValue`: không chấp nhận null values.

Các kiểm tra `ConcurrentSkipListMap` ở đây **không phải load test đa luồng**, chỉ xác nhận contract method và behavior trong một JVM/thread. Cần kiểm thử concurrency/atomicity thực tế riêng nếu ứng dụng có nhiều writers.

## 14. Mô hình bài toán thực tế và cách chọn API

### 14.1. Tra mức phí hoặc ưu đãi theo ngưỡng

Dữ liệu:

```text
0   -> START
100 -> PLUS
250 -> PRO
500 -> ELITE
```

Tra score 180:

```java
Map.Entry<Integer,String> tier = tiers.floorEntry(180);
String packageName = tier == null ? "NOT_ELIGIBLE" : tier.getValue();
```

Đây là mảnh code; `"NOT_ELIGIBLE"` chỉ là policy minh họa, phải tùy hệ thống. Nếu muốn biết khoảng cách đến tier tiếp theo:

```java
Integer nextThreshold = tiers.higherKey(180); // 250.
```

Nếu score bằng 250 mà muốn tier tiếp theo, `higherKey(250)` cho 500; đừng dùng `ceilingKey(250)` vì sẽ lại là 250.

### 14.2. Truy vấn lịch sử theo thời gian

Dữ liệu `NavigableMap<LocalDate,Event>` có thể trả các events trong ngày:

```java
NavigableMap<LocalDate, Event> result =
        eventMap.subMap(startInclusive, true, endExclusive, false);
```

Đây là **mảnh code cần `Event`, `eventMap` và parameters trong ứng dụng**, không thể biên dịch độc lập. Với nhiều events cùng ngày, một `TreeMap<LocalDate,Event>` chỉ chứa **một value cho mỗi date key**; muốn nhiều events trong một ngày, dùng `Map<LocalDate,List<Event>>` hoặc khóa tổ hợp `(timestamp, eventId)` có comparator nhất quán.

### 14.3. Tìm điểm quan sát trước/sau mốc

Khi đo sensor/price:

- `floorEntry(t)` tìm mẫu tại/trước `t`.
- `ceilingEntry(t)` tìm mẫu tại/sau `t`.
- `subMap(from,true,to,false)` chọn lịch sử trong range.

Cần thêm kiểm tra chất lượng dữ liệu: mẫu trước có thể quá cũ, missing-value có thể không đồng nghĩa 0, range có thể rỗng. `NavigableMap` không tự tính interpolation hay time-weighted averages.

### 14.4. Các mức threshold chồng lấn?

`NavigableMap` tổ chức dữ liệu theo **một khóa có thứ tự**, không biểu diễn đầy đủ các interval chồng lấn nhiều chiều chỉ bằng `floorEntry`. Ví dụ một rule áp dụng từ 100 tới 300 và một rule khác từ 200 tới 500; cần thêm cấu trúc interval/rule precedence hoặc database phù hợp, không tự giả định floorEntry là “tất cả rule đang áp dụng”.

### 14.5. Hàng đợi ưu tiên theo khóa có thứ tự

`TreeMap<Integer,List<Job>>` có thể lấy một key cao/thấp nhất, nhưng `pollFirstEntry()/pollLastEntry()` **xóa cả mapping** tại mốc; nếu một key chứa nhiều jobs, logic xử lý phải rõ. Trong môi trường concurrent, cần operation atomic/policy đúng; đừng coi `TreeMap` là một priority queue thread-safe.

## 15. Những lỗi thường gặp và cách tránh

| Sai lầm | Hậu quả | Cách đúng |
| --- | --- | --- |
| Dùng `lower` thay `floor` cho ngưỡng đạt đúng 100. | Chọn tier thấp hơn. | `floorKey/Entry` nếu cho phép bằng. |
| Dùng `ceiling` thay `higher` cho “mức kế tiếp”. | Trả lại chính mức đang có. | `higher` strictly greater. |
| Cho rằng floor luôn theo số học tăng. | Sai trên `descendingSet/Map`. | Diễn giải theo comparator hiện tại. |
| Không kiểm tra null từ floor/ceiling. | NPE/unboxing hoặc nhầm fallback. | Null-check và policy rõ. |
| Dùng `subMap(start,end)` nhưng nghĩ end inclusive. | Truy vấn thiếu/đếm trùng boundary. | Overload boolean, dùng `[start,end)`. |
| Đảo from/to theo nhầm thứ tự. | IllegalArgumentException. | So cận theo comparator của collection/view. |
| Dùng `headMap` thay `tailMap`. | Chọn nhầm phía ngưỡng. | Xác định `<` hay `≥` trước. |
| Nghĩ `subMap` là bản sao độc lập. | Sửa view làm mất dữ liệu gốc. | Copy bằng `new TreeMap<>(view)` nếu cần. |
| Xóa qua `navigableKeySet` mà nghĩ không ảnh hưởng map. | Mất mapping thật. | Chỉ remove khi intentional. |
| Gọi `navigableKeySet().add(key)`. | UnsupportedOperationException. | `map.put(key,value)`. |
| Dùng `pollFirstEntry` chỉ để đọc. | Xóa dữ liệu đầu map. | `firstEntry` để đọc. |
| Đọc `firstKey` ở map rỗng. | NoSuchElementException. | `firstEntry()==null` hoặc kiểm tra `isEmpty`. |
| Nghĩ `floorEntry` là live entry. | Sửa `setValue` không được; snapshot stale. | `map.put(entry.getKey(),newValue)`. |
| Dùng `map.get(k)==null` để xác nhận không có key. | Sai nếu TreeMap lưu value null. | `containsKey(k)`. |
| Gọi `floorKey(null)` với TreeMap natural ordering. | NPE. | Không dùng null keys. |
| Comparator không nhất quán với equality. | Keys/elements khác nhau có thể bị gộp. | Comparator đúng theo business identity. |
| Đặt duplicate timestamp key trong Map rồi tưởng giữ mọi event. | Value cũ bị thay thế. | Composite key hoặc list values. |
| Sửa TreeMap giữa khi đang duyệt iterator mà không đồng bộ. | Exception hoặc behavior không bảo đảm. | Tách phase sửa, hoặc concurrency design đúng. |
| Nghĩ ConcurrentSkipListMap tự làm nhiều-step range transaction. | Race/inconsistent report. | Snapshot/versioning/locking theo yêu cầu. |
| Dùng `Collections.unmodifiableNavigableMap(view)` như bản chụp. | Backing map đổi thì wrapper vẫn đổi. | Copy trước rồi bọc read-only. |
| Kết luận O(log n) cho mọi query + scan k entries. | Đánh giá latency sai. | Tính cả chi phí duyệt k kết quả. |

## 16. Test matrix cần có trong sản phẩm thật

Với một API chọn tier bằng `floorEntry(score)`:

| Trường hợp | Input minh họa | Kỳ vọng |
| --- | --- | --- |
| Thấp hơn min | `-1` | Không có entry; policy fallback rõ. |
| Bằng min | `0` | START. |
| Giữa thresholds | `180` | PLUS (ngưỡng 100). |
| Bằng threshold | `250` | PRO. |
| Lớn hơn max | `999` | ELITE (nếu policy là highest achieved tier). |
| Empty map | Không có tiers | `floorEntry` trả null. |
| Missing value | Key tồn tại value null | Không nhầm absent key. |
| Reverse comparator | Descending map | Xác định lại floor/ceiling theo comparator. |

Với truy vấn khoảng thời gian:

| Case | Start/End | Kỳ vọng |
| --- | --- | --- |
| Khoảng chuẩn | `[03,13)` | Ngày 03,05,09; không có 13. |
| Cận bằng nhau, hai đầu inclusive | `[03,03]` | Chỉ ngày 03 nếu tồn tại. |
| Cận bằng nhau, cuối exclusive | `[03,03)` | Rỗng. |
| Cận đảo | `from > to` | IllegalArgumentException theo comparator. |
| Không có điểm dữ liệu | Khoảng không chứa key | Rỗng, không phải null view. |
| Thay đổi backing | Put ngày 07 sau khi tạo view | View mới nhìn thấy 07. |
| Put ngoài bounds qua view | Put ngày 01 vào `[03,13)` | IllegalArgumentException. |
| Snapshot | Copy trước khi backing thay đổi | Copy giữ dữ liệu tại thời điểm tạo. |

**Phân biệt unit test và integration test:** 67 assertions của bài chạy hoàn toàn trong bộ nhớ; chúng kiểm chứng behavior Java Collections Framework, không thay thế integration tests về database consistency, timezone policy, end-to-end latency hay concurrent race của ứng dụng thực.

## 17. Bài tập mở rộng

**A — Tra ngưỡng.** Từ `[10,20,35,50,80]`, ghi kết quả `lower(35)`, `floor(35)`, `ceiling(35)`, `higher(35)`; giải thích strict vs inclusive.

**B — Ngưỡng chưa tồn tại.** Thử `floor(34)` và `ceiling(34)`; phân biệt “không có key chính xác” với “không có ứng viên”.

**C — Biên min/max.** Thử `lower(10)`, `higher(80)`, `floor(-100)`, `ceiling(1000)`, viết null-handling đúng.

**D — Khoảng nửa mở.** Viết `subSet(20,true,50,false)` và kiểm chứng loại trừ 50.

**E — Hai đầu bằng nhau.** Thử `subSet(35,true,35,true)` và `subSet(35,true,35,false)`.

**F — Live view.** Tạo view rồi thêm 40 vào base; sau đó xóa 35 qua view. Quan sát cập nhật hai chiều.

**G — Bảo vệ bounds.** Thử `window.add(99)` và ghi nhận IllegalArgumentException; không catch rồi âm thầm ghi ngoài range.

**H — Descending semantics.** Dùng `descendingSet.floor(36)` và `descendingSet.ceiling(36)`; giải thích vì sao đảo so với natural-order set.

**I — Reverse range.** Tạo `descendingSet.subSet(80,true,35,true)`, so với `subSet(35,true,80,true)`.

**J — Poll có tác dụng xóa.** So `first()`, `pollFirst()`, `last()`, `pollLast()` trước và sau mutation.

**K — Map tier.** Dùng `floorEntry(180)` để chọn `PLUS` và `higherEntry(180)` để lấy tier kế tiếp.

**L — Entry snapshot.** Lưu `floorEntry(400)`, thay value của key 400 trong base map; giải thích vì sao captured entry không đổi.

**M — Key set view.** Xóa một key qua `navigableKeySet` rồi kiểm tra base map; thử `add` và giải thích exception.

**N — Null value.** Đặt map value null cho key 400, so `get`, `containsKey`, `floorEntry`.

**O — Date range.** Dùng `LocalDate` và `subMap(start,true,end,false)`, xác nhận ngày end bị loại.

**P — Copy báo cáo.** Dùng `new TreeMap<>(range)` để tạo snapshot, sửa backing và so hai maps.

**Q — Comparator identity.** Dùng case-insensitive comparator và hai keys `Alpha/ALPHA`; giải thích vì sao chỉ một key được giữ.

**R — Concurrency.** So TreeMap với ConcurrentSkipListMap về weakly consistent iterators, null values và tính atomic của compound operations.

**S — Phân trang dữ liệu.** Thiết kế API xuất các khóa trong khoảng `[start,end)` với cap theo số bản ghi, tránh lấy toàn bộ map cực lớn.

**T — Sản phẩm thật.** Viết một runbook lựa chọn collection dựa vào số keys, pattern access, write frequency, concurrency và yêu cầu snapshot consistency.

## 18. Câu hỏi tự kiểm tra

**1. NavigableSet khác Set thế nào?** — Có thứ tự, hỗ trợ tra phần tử gần nhất và các range views.

**2. NavigableMap khác HashMap thế nào?** — Khóa có ordering, hỗ trợ floor/ceiling và subMap/descendingMap.

**3. lower và floor khác nhau?** — `lower` là `<`, `floor` là `≤` theo comparator.

**4. ceiling và higher khác nhau?** — `ceiling` là `≥`, `higher` là `>` theo comparator.

**5. Không có ứng viên thì floor trả gì?** — `null` (với TreeSet/TreeMap natural keys như bài).

**6. Mốc bằng threshold có được floor tính vào không?** — Có.

**7. Mặc định subMap(from,to) bao gồm end không?** — Không, mặc định `[from,to)`.

**8. subSet(from,true,to,true) là khoảng gì?** — `[from,to]`.

**9. from lớn hơn to thì sao?** — `IllegalArgumentException` theo ordering của map/set.

**10. subMap là copy độc lập hay view?** — View có backing map; sửa qua view có thể đổi base.

**11. Có thể put key ngoài range qua subMap không?** — Không, TreeMap view ném IllegalArgumentException.

**12. descendingMap có đảo nghĩa floor/ceiling không?** — Có, quan hệ theo reverse comparator.

**13. descending subMap nhận các endpoints theo chiều nào?** — Theo comparator đảo của descending map.

**14. navigableKeySet.add(key) có được không?** — Không, key set view không có value để tạo mapping.

**15. navigableKeySet.remove(key) làm gì?** — Xóa mapping gốc.

**16. floorEntry trả reference mutable luôn phản ánh map không?** — Không, navigation entry là snapshot; setValue không cập nhật underlying map.

**17. firstKey ở map rỗng khác firstEntry thế nào?** — firstKey ném NoSuchElementException; firstEntry trả null.

**18. pollFirstEntry có xóa không?** — Có.

**19. Có nên dùng map.get(k)==null để chứng minh key vắng mặt?** — Không, TreeMap có thể lưu value null; dùng containsKey.

**20. TreeMap/TreeSet thread-safe mặc định không?** — Không.

**21. ConcurrentSkipListMap có cho null values không?** — Không.

**22. ConcurrentSkipListMap iterator có là snapshot atomic không?** — Không, weakly consistent.

**23. Comparator ảnh hưởng key uniqueness không?** — Có, compare(a,b)==0 khiến TreeSet/TreeMap xem là một key/element.

**24. Tìm lịch sử từ ngày 03 đến trước 13 nên dùng gì?** — `subMap(day03,true,day13,false)`.

**25. Muốn snapshot độc lập từ range view làm gì?** — Copy bằng `new TreeMap<>(view)` hoặc `new TreeSet<>(view)` rồi tùy cần bọc unmodifiable.

**26. Bài tập đã xác minh bao nhiêu điều kiện?** — **67/67 PASS** với mã biên dịch mức Java 17.

## 19. Tài liệu chính thức đang còn hiệu lực

- [Oracle Java SE 26 — NavigableSet](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/NavigableSet.html): `lower/floor/ceiling/higher`, `subSet/headSet/tailSet`, views, descending và poll.
- [Oracle Java SE 26 — NavigableMap](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/NavigableMap.html): `*Key/*Entry`, entry snapshots, bounds, key views, descendingMap, first/poll entries.
- [Oracle Java SE 26 — TreeSet](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/TreeSet.html): implementation theo TreeMap, basic O(log n), comparator/equals và thread-safety.
- [Oracle Java SE 26 — TreeMap](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/TreeMap.html): sorted map operations, backed subMap views, null và concurrency contracts.
- [Oracle Java SE 26 — Comparator](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Comparator.html): total ordering và tính nhất quán với equals.
- [Oracle Java SE 26 — ConcurrentSkipListMap](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentSkipListMap.html): concurrent sorted map, weakly consistent iterators và no null values.
- [Oracle Java SE 26 — ConcurrentSkipListSet](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/ConcurrentSkipListSet.html): concurrent navigable set, weakly consistent iterators, `size` considerations.
- [Oracle Java SE 26 — Collections](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collections.html): unmodifiable/synchronized wrappers và cách dùng.
- [Oracle Java SE 26 — LocalDate](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/time/LocalDate.html): immutable date-only type và natural ordering.
- [Oracle Java SE 17 — NavigableSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableSet.html): API được dùng trong ví dụ Java 17.
- [Oracle Java SE 17 — NavigableMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/NavigableMap.html): API được dùng trong ví dụ Java 17.

**Tóm tắt:** Dùng **`NavigableSet`** khi chỉ cần các mốc có thứ tự, **`NavigableMap`** khi các mốc phải đi kèm thông tin. Chọn đúng **strict/inclusive** methods, ưu tiên diễn đạt khoảng **`[from,to)`** rõ ràng, nhớ **`subSet/subMap` là live views**, và hiểu **reverse ordering thay đổi cả floor/ceiling lẫn thứ tự cận**. Xử lý null/empty/map entry snapshots, tránh comparator sai equality và chọn cấu trúc concurrent đúng khi có nhiều threads. Ví dụ Java17+ của bài đã chạy **67/67 PASS**, từ tra ngưỡng đến khoảng ngày và biến đổi view.
