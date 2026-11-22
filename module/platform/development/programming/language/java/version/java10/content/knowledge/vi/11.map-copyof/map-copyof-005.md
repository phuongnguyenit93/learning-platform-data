# Thứ tự duyệt và giới hạn giữ đặc tính sắp xếp của nguồn khi dùng `Map.copyOf` (Java 10+)

## 1. Mục tiêu và kết luận cần nhớ

`Map.copyOf(Map<? extends K, ? extends V> source)`, có từ **Java 10**, tạo một `Map<K,V>` **không cho sửa** chứa các ánh xạ khóa–giá trị của map nguồn tại thời điểm sao chép. Tuy nhiên, **API không cam kết giữ thứ tự duyệt của map nguồn**. Ngay cả khi nguồn là `TreeMap` đã sắp xếp theo comparator, hoặc `LinkedHashMap` đang duyệt theo thứ tự chèn, `Map.copyOf` **không bảo đảm** rằng kết quả duyệt theo thứ tự ấy.

```java
var source = new java.util.TreeMap<String, Integer>();
source.put("B", 2);
source.put("A", 1);
source.put("C", 3);

var copied = java.util.Map.copyOf(source);
System.out.println(copied.size());          // 3
System.out.println(copied.get("B"));       // 2

// KHÔNG được giả định copied.keySet() sẽ duyệt theo [A, B, C].
```

**Điểm quan trọng nhất:** `Map.copyOf` giữ **nội dung ánh xạ** theo hợp đồng của `Map`; nó **không phải** công cụ giữ **thứ tự sắp xếp** hay **comparator** của `SortedMap` nguồn. Chạy trên một phiên bản JDK thấy kết quả “có vẻ vẫn được sắp xếp” không tạo ra hợp đồng mà ứng dụng có thể dựa vào.

Sau bài học, bạn sẽ:

- Phân biệt **thứ tự duyệt** (encounter/iteration order), **sắp xếp khóa**, **thứ tự chèn** và **nội dung ánh xạ**.
- Biết những gì `Map.copyOf` giữ được và không giữ được.
- Hiểu hệ quả khi nguồn là `TreeMap`, `SortedMap`, `NavigableMap`, `LinkedHashMap` hoặc `HashMap`.
- Chọn cách tạo **snapshot không sửa được nhưng giữ comparator hoặc thứ tự chèn**.
- Hiển thị hoặc xuất dữ liệu có thứ tự một cách xác định mà không phụ thuộc thứ tự của `Map.copyOf`.
- Kiểm tra sai lầm về overload constructor `TreeMap`, comparator không nhất quán với `equals`, `null`, alias và mutable values.
- Biên dịch/chạy ví dụ Java 17+ với stdout không phụ thuộc chi tiết triển khai của JDK.

Bài chỉ dùng quy tắc Java vẫn đang áp dụng. Các API cốt lõi hoạt động trên Java 17 và các bản Java hiện đại.

## 2. “Thứ tự duyệt của map” là gì?

Thứ tự duyệt của một map là trình tự mà iterator của các collection view như `keySet()`, `values()` hoặc `entrySet()` trả các phần tử. Thứ tự đó có thể được một implementation **cam kết** hoặc **không cam kết**.

Ví dụ:

```java
for (var entry : map.entrySet()) {
    System.out.println(entry.getKey() + "=" + entry.getValue());
}
```

Giả sử `map` đã được khai báo. Dòng nào được in trước phụ thuộc vào **hợp đồng thứ tự của implementation cụ thể**, không chỉ phụ thuộc vào việc `map` có cùng các ánh xạ hay không.

Ba tình huống khác nhau:

- **Sắp xếp theo khóa:** `TreeMap` duyệt theo thứ tự tự nhiên của khóa hoặc `Comparator` được cung cấp.
- **Thứ tự chèn:** `LinkedHashMap` mặc định giữ thứ tự các khóa được chèn đầu tiên, nếu không được cấu hình hoặc thao tác lại theo chế độ thứ tự khác.
- **Không cam kết thứ tự:** `HashMap` không hứa một thứ tự duyệt ổn định; các map từ `Map.of`, `Map.ofEntries`, `Map.copyOf` cũng không cam kết thứ tự duyệt.

`Map` có hợp đồng nội dung (`size`, `get`, `containsKey`, `equals`, `entrySet`), nhưng **bằng nhau về ánh xạ không đồng nghĩa bằng nhau về thứ tự duyệt**.

### Hai map có thể `equals` bằng nhau nhưng thứ tự khác nhau

```java
var insertion = new java.util.LinkedHashMap<String, Integer>();
insertion.put("C", 3);
insertion.put("A", 1);
insertion.put("B", 2);

var sorted = new java.util.TreeMap<String, Integer>(insertion);

System.out.println(insertion.equals(sorted)); // true
System.out.println(insertion.keySet());        // [C, A, B]
System.out.println(sorted.keySet());           // [A, B, C]
```

`Map.equals` xét **các ánh xạ khóa–giá trị**, không xem thứ tự duyệt là tiêu chí. Điều này giải thích vì sao kiểm tra `Map.copyOf(source).equals(source)` có thể thành công ngay cả khi thứ tự duyệt khác hoàn toàn.

## 3. Hợp đồng hiện hành của `Map.copyOf`

Chữ ký:

```java
static <K, V> Map<K, V> copyOf(Map<? extends K, ? extends V> map)
```

Theo tài liệu `java.util.Map`, `Map.copyOf`:

1. Trả về map **không cho thêm, xóa hoặc cập nhật mapping** qua API của chính nó. Ví dụ `put`, `remove`, `clear` và `replace` không được hỗ trợ.
2. Lấy **các ánh xạ hiện có ở nguồn** tại thời điểm gọi. Nếu nguồn thay đổi mapping về sau, bản sao không phản ánh các thay đổi đó.
3. Không chấp nhận `null` làm tham số nguồn, khóa hoặc giá trị: gọi sai có thể ném `NullPointerException`.
4. **Không cam kết thứ tự duyệt** các mapping và thứ tự ấy có thể thay đổi.
5. Không bảo đảm tạo object mới khi nguồn đã là unmodifiable map; implementation có thể tái sử dụng object.
6. Không deep-copy các object khóa/giá trị mutable: đó vẫn có thể là các reference chia sẻ.

**Không suy diễn thêm** rằng `Map.copyOf` có một thuật toán sắp xếp cụ thể, luôn dùng `HashMap`, luôn có thứ tự ngẫu nhiên, hoặc chắc chắn sẽ đảo thứ tự của nguồn. API đơn giản là **không hứa thứ tự**.

### Phân biệt “không có bảo đảm” với “chắc chắn mất thứ tự”

Khi một bản sao có vẻ duyệt giống nguồn trong lần chạy hiện tại, điều đó vẫn **có thể xảy ra**. Nhưng thay đổi JDK, số lượng phần tử, khóa hoặc điều kiện chạy có thể tạo thứ tự khác. Vì vậy câu đúng là:

> `Map.copyOf` **không bảo đảm bảo toàn thứ tự** của map nguồn.

Không nên phát biểu tuyệt đối rằng nó **luôn luôn** đổi thứ tự, vì đó không phải điều hợp đồng API khẳng định.

## 4. Nguồn `TreeMap` hoặc `SortedMap`: không giữ đặc tính sorted-map

`TreeMap<K,V>` triển khai `NavigableMap`/`SortedMap` và duy trì thứ tự khóa theo:

- **Natural ordering** khi không cung cấp comparator; hoặc
- Một `Comparator<? super K>` do caller chỉ định.

Ví dụ `TreeMap` ngược thứ tự chữ cái:

```java
java.util.SortedMap<String, Integer> source =
        new java.util.TreeMap<>(java.util.Comparator.reverseOrder());
source.put("A", 1);
source.put("C", 3);
source.put("B", 2);

System.out.println(source.keySet()); // [C, B, A]
```

Nếu copy bằng:

```java
var copied = java.util.Map.copyOf(source);
```

thì kiểu tĩnh của `copied` là `Map<String,Integer>`, không phải `SortedMap<String,Integer>`. Không thể dựa vào `copied.firstKey()` hay `copied.comparator()`: các phương thức đó **không thuộc interface `Map`**. Đừng ép kiểu sang `SortedMap` chỉ vì nguồn là `TreeMap`; `Map.copyOf` không bảo đảm kết quả triển khai `SortedMap`.

**Nội dung các mapping vẫn được giữ** (ví dụ `copied.get("A") == 1`), nhưng:

- Không còn **hợp đồng thứ tự duyệt `[C, B, A]`** của `source`.
- Không còn **hợp đồng comparator** do `SortedMap` cung cấp.
- Không còn giao diện truy vấn có thứ tự như `firstKey`, `lastKey`, `headMap` hoặc `subMap` trên kiểu trả về `Map`.
- Không được giả định rằng iterator, `forEach` hay `toString()` của bản sao thể hiện thứ tự khóa.

Đây là **giới hạn quan trọng của `Map.copyOf`** khi mã đang dựa vào map đã sắp xếp.

## 5. Nguồn `LinkedHashMap`: thứ tự chèn cũng không được giữ

`LinkedHashMap` thông thường có thứ tự duyệt theo thứ tự chèn khóa:

```java
var source = new java.util.LinkedHashMap<String, Integer>();
source.put("C", 3);
source.put("A", 1);
source.put("B", 2);

System.out.println(source.keySet()); // [C, A, B]
```

Nhưng:

```java
var copy = java.util.Map.copyOf(source);
// Không được assert copy.keySet().toString().equals("[C, A, B]").
```

`Map.copyOf` không mang theo hợp đồng “duyệt theo thứ tự chèn”, mặc dù nó mang theo đúng ba mapping. Điều này có thể ảnh hưởng đến:

- Xuất CSV/JSON hoặc tạo báo cáo khi thứ tự cột/hàng dựa vào thứ tự duyệt.
- Giao diện người dùng nếu muốn hiển thị theo thứ tự nhập.
- Kiểm thử so sánh chuỗi `map.toString()`.
- Tính toán hoặc tác vụ mà thuật toán cố ý xử lý bản ghi trước–sau.

**Điểm cần kiểm tra:** nếu mã chỉ gọi `get(key)` và không phụ thuộc thứ tự duyệt, `Map.copyOf` có thể là lựa chọn rất tốt. Nếu thứ tự là một phần của hành vi sản phẩm, cần giải pháp có hợp đồng thứ tự rõ ràng.

## 6. Nguồn `HashMap`: vốn đã không có thứ tự cố định

`HashMap` không cam kết thứ tự duyệt. Gọi `Map.copyOf(hashMap)` cũng không tạo ra một thứ tự duyệt được cam kết.

```java
var source = new java.util.HashMap<String, Integer>();
source.put("B", 2);
source.put("A", 1);

var copy = java.util.Map.copyOf(source);
System.out.println(copy.size());  // 2
System.out.println(copy.get("A")); // 1
```

Đừng suy luận:

- Vì `HashMap` hiện in theo `[A, B]` nên `Map.copyOf` sẽ in như thế.
- Vì `Map.copyOf` “sao chép” nên nó giữ vị trí iterator của từng entry.
- Vì thứ tự trùng nhau trong test một lần nên chương trình có thể dùng thứ tự ấy như dữ liệu nghiệp vụ.

Nếu cần thứ tự mới, hãy **xác định rõ** muốn sắp theo khóa hay giữ trình tự một nguồn có encounter order đáng tin cậy.

## 7. Bảng so sánh các lựa chọn

| Lựa chọn | Có sửa mapping qua tham chiếu trả về? | Giữ thứ tự duyệt có hợp đồng? | Nguồn sửa sau đó ảnh hưởng kết quả? |
| --- | --- | --- | --- |
| `Map.copyOf(source)` | Không | **Không** | Không ảnh hưởng đến tập mapping; object key/value mutable là chuyện riêng |
| `Collections.unmodifiableMap(source)` | Không qua view | Theo thứ tự của **backing map** ở thời điểm duyệt | **Có**, vì là live view |
| `Collections.unmodifiableMap(new LinkedHashMap<>(source))` | Không qua view | **Có**, theo thứ tự entry được duyệt khi tạo `LinkedHashMap` copy | Không ảnh hưởng mapping nếu không lộ backing copy |
| `Collections.unmodifiableSortedMap(new TreeMap<>(sortedSource))` | Không qua view | **Có**, theo comparator của `SortedMap` nguồn nếu chọn đúng constructor | Không ảnh hưởng mapping nếu không lộ backing copy |
| `Collections.unmodifiableNavigableMap(new TreeMap<>(sortedSource))` | Không qua view | **Có**, kèm API điều hướng của `NavigableMap` | Không ảnh hưởng mapping nếu không lộ backing copy |
| `new TreeMap<>(source)` | **Có** | Sắp theo natural ordering hoặc comparator tùy constructor | Không ảnh hưởng mapping ở bản copy; đây là map mutable |
| `new LinkedHashMap<>(source)` | **Có** | Theo thứ tự duyệt khi copy; thường giữ thứ tự chèn từ một `LinkedHashMap` nguồn | Không ảnh hưởng mapping ở bản copy; đây là map mutable |

Bảng nói về **thành viên mapping**. Nếu giá trị là `StringBuilder`, entity/bean mutable hoặc key chứa field mutable, đổi trạng thái object qua alias vẫn có thể làm dữ liệu quan sát được trong các kết quả copy/view thay đổi.

## 8. Cần snapshot không sửa được **và** giữ comparator? Dùng `TreeMap` copy + wrapper

Nếu nghiệp vụ yêu cầu:

1. Giữ các mapping tại một thời điểm;
2. Không cho caller thêm/xóa/thay mapping;
3. Duyệt theo **chính comparator** của `SortedMap` nguồn;

thì có thể tạo **bản sao `TreeMap` độc lập** rồi bọc bằng `Collections.unmodifiableSortedMap`.

```java
static <K, V> java.util.SortedMap<K, V> sortedSnapshot(
        java.util.SortedMap<K, V> source) {
    var copy = new java.util.TreeMap<K, V>(source);
    return java.util.Collections.unmodifiableSortedMap(copy);
}
```

Đây là **phương thức minh họa đặt trong một lớp Java**; bản đầy đủ được kiểm tra ở mục 13.

**Vì sao hoạt động?**

- `new TreeMap<K,V>(source)` với đối số được khai báo tĩnh là `SortedMap` chọn constructor `TreeMap(SortedMap)`, giữ **comparator của nguồn** (hoặc natural ordering nếu comparator là `null`), và sao chép các mapping.
- `Collections.unmodifiableSortedMap(copy)` trả view không cho caller sửa qua tham chiếu trả về, đồng thời cung cấp các phương thức của `SortedMap` như `comparator()`, `firstKey()`, `lastKey()`.
- `copy` là biến cục bộ **không được trả hoặc lưu lộ ra ngoài**. Khi `source` thay đổi cấu trúc về sau, kết quả trả về giữ các mapping đã copy.
- Wrapper là **view của `copy`**, không phải một kiểu “deep immutable” bí ẩn. Nếu ai đó vẫn giữ reference đến `copy`, họ có thể sửa nó; đó là lý do phải không làm lộ backing copy.

Với nhu cầu `lowerEntry`, `ceilingKey`, `descendingMap` hoặc các API điều hướng, có thể bọc qua `Collections.unmodifiableNavigableMap`:

```java
static <K, V> java.util.NavigableMap<K, V> navigableSnapshot(
        java.util.SortedMap<K, V> source) {
    var copy = new java.util.TreeMap<K, V>(source);
    return java.util.Collections.unmodifiableNavigableMap(copy);
}
```

**Không dùng `Map.copyOf` thay cho hai wrapper này** nếu comparator và SortedMap/NavigableMap API là một phần hợp đồng.

### So sánh với live view

```java
var view = java.util.Collections.unmodifiableSortedMap(source);
```

`view` giữ tính sorted của `source` và chặn sửa trực tiếp qua view, nhưng **không tạo snapshot**: nếu mã khác vẫn sửa `source`, view phản ánh thay đổi đó. Phương pháp đúng tùy yêu cầu là **live view** hay **snapshot**.

## 9. Bẫy overload constructor `TreeMap`: `Map` và `SortedMap` là hai constructor khác nhau

`TreeMap` có hai constructor liên quan:

```java
new TreeMap<K, V>(Map<? extends K, ? extends V> source)
new TreeMap<K, V>(SortedMap<K, ? extends V> source)
```

Chúng **không đồng nghĩa**:

- Constructor nhận `Map` tạo `TreeMap` sắp xếp theo **natural ordering của khóa**, không tự lấy comparator tùy chỉnh của nguồn.
- Constructor nhận `SortedMap` sao chép mapping và dùng **chính thứ tự/comparator** của `SortedMap` nguồn.

Ví dụ:

```java
java.util.SortedMap<String, Integer> descending =
        new java.util.TreeMap<>(java.util.Comparator.reverseOrder());
descending.put("A", 1);
descending.put("B", 2);

// Giữ comparator ngược:
var sameOrder = new java.util.TreeMap<String, Integer>(descending);
System.out.println(sameOrder.firstKey()); // B

// Nếu biến chỉ được khai báo là Map, constructor Map dùng natural order:
java.util.Map<String, Integer> asMap = descending;
var naturalOrder = new java.util.TreeMap<String, Integer>(asMap);
System.out.println(naturalOrder.firstKey()); // A
```

**Kiểu tĩnh của đối số tại vị trí gọi** quyết định overload được chọn; không được kết luận chỉ dựa vào lớp runtime của `descending`.

Nếu dữ liệu đầu vào chỉ có kiểu `Map` mà bạn muốn dùng comparator cụ thể, hãy truyền comparator chủ động:

```java
var copied = new java.util.TreeMap<String, Integer>(
        java.util.Comparator.reverseOrder());
copied.putAll(asMap);
```

Khi đó caller có trách nhiệm chọn comparator đúng với miền khóa và yêu cầu nghiệp vụ.

## 10. Cần giữ thứ tự chèn? Copy sang `LinkedHashMap` rồi bọc

Nếu nguồn có encounter order đáng tin cậy, đặc biệt là `LinkedHashMap` mặc định, có thể tạo snapshot độc lập:

```java
static <K, V> java.util.Map<K, V> insertionOrderSnapshot(
        java.util.Map<K, V> source) {
    var copy = new java.util.LinkedHashMap<K, V>(source);
    return java.util.Collections.unmodifiableMap(copy);
}
```

Ví dụ:

```java
var original = new java.util.LinkedHashMap<String, Integer>();
original.put("C", 3);
original.put("A", 1);
original.put("B", 2);

var snapshot = insertionOrderSnapshot(original);
System.out.println(snapshot.keySet()); // [C, A, B]
```

**Giới hạn:** constructor của `LinkedHashMap` nhận một `Map` và lặp qua các entry của `Map` đó; nó bảo toàn **thứ tự quan sát được khi copy**, không “khôi phục” thứ tự chèn lịch sử từ một `HashMap` không có hợp đồng thứ tự. Nếu nguồn không cam kết thứ tự, bản copy có thể duyệt ổn định theo thứ tự đã thu được, nhưng thứ tự ban đầu đó **không phải thứ tự nghiệp vụ đáng tin cậy**.

Nếu cần một encounter order khác (ví dụ ưu tiên trước–sau theo thời gian), phải xác định quy tắc và sắp xếp dữ liệu trước hoặc ghi nó trong cấu trúc có thứ tự thích hợp.

### Vì sao không chỉ dùng `Collections.unmodifiableMap(original)`?

`Collections.unmodifiableMap(original)` là **live view**. Nếu `original.put("D", 4)` được gọi sau đó, view sẽ phản ánh mapping `D`. Khi cần ảnh chụp snapshot của thứ tự và nội dung ở thời điểm hiện tại, **copy trước, bọc sau** là khác biệt then chốt.

## 11. Chỉ cần đầu ra có thứ tự, không cần map bản thân có thứ tự?

Khi bạn đã có `Map.copyOf(source)` và mục tiêu chỉ là **in**, **xuất báo cáo** hoặc **hiển thị** theo một thứ tự xác định, có thể tạo luồng entry được sắp xếp:

```java
var copy = java.util.Map.copyOf(source);

var lines = copy.entrySet().stream()
        .sorted(java.util.Map.Entry.comparingByKey())
        .map(e -> e.getKey() + "=" + e.getValue())
        .toList();

System.out.println(lines);
```

Đây là đoạn minh họa với `source` là `Map<String,Integer>` và khóa `String` có natural ordering. Kết quả `lines` có thứ tự theo key, **không phụ thuộc** iterator của `copy`. `Stream.toList()` có từ Java 16, ví dụ này dành cho Java 17+.

Nếu khóa không có natural ordering hoặc muốn comparator tùy chỉnh:

```java
var lines = copy.entrySet().stream()
        .sorted(java.util.Map.Entry.comparingByKey(
                java.util.Comparator.reverseOrder()))
        .map(e -> e.getKey() + "=" + e.getValue())
        .toList();
```

Cách này **chỉ sắp xếp kết quả khi đọc**; không biến `copy` thành `SortedMap` và không bảo đảm `copy.entrySet().iterator()` đã được sắp xếp. Với nhiều lần truy vấn có thứ tự và các thao tác khoảng khóa, `SortedMap` snapshot phù hợp hơn.

### Chú ý khóa không comparable

`Map.Entry.comparingByKey()` tự nhiên cần khóa có `Comparable` phù hợp. Nếu khóa là một class không có thứ tự tự nhiên, hãy cung cấp comparator công khai và rõ ràng để tránh `ClassCastException` khi chạy.

## 12. Những giới hạn khác khi bảo toàn dữ liệu và thứ tự

### 12.1. `null` không được `Map.copyOf` chấp nhận

```java
var source = new java.util.HashMap<String, Integer>();
source.put("A", null);

// Map.copyOf(source); // Ném NullPointerException
```

Một số map nguồn như `HashMap` hoặc `TreeMap` có thể cho phép value `null`. `Map.copyOf` **không** cho phép **khóa hay giá trị `null`**. Vì thế không được refactor tự động khi chưa biết hợp đồng dữ liệu.

`Collections.unmodifiableMap(new LinkedHashMap<>(source))` hoặc `Collections.unmodifiableSortedMap(new TreeMap<>(sortedSource))` có thể giữ value `null` nếu backing map cho phép; đó là một **khác biệt chức năng**, không chỉ khác thứ tự.

### 12.2. `Map.copyOf` không phải deep copy

```java
var builder = new StringBuilder("A");
var source = java.util.Map.of("key", builder);
var copy = java.util.Map.copyOf(source);

builder.append("B");
System.out.println(copy.get("key")); // AB
```

Tập mapping giữ reference tới object `StringBuilder`. Mapping không được thêm/xóa/thay qua `copy`, nhưng **đối tượng value** vẫn có thể sửa. Điều tương tự áp dụng cho các giải pháp `TreeMap` hoặc `LinkedHashMap` snapshot nếu bạn chỉ copy reference.

Nếu yêu cầu là **snapshot giá trị hoàn toàn ổn định**, chuyển mỗi value mutable thành một value object bất biến hoặc defensive copy phù hợp.

### 12.3. Cẩn thận với key mutable

Các `Map` dựa vào hợp đồng `equals/hashCode` của key để tra cứu. Nếu một key thay đổi field dùng trong `equals/hashCode` sau khi được đưa vào map, các phép tìm kiếm có thể hoạt động không như kỳ vọng. `Map.copyOf` không đóng băng key.

Với `TreeMap`, key mutable tác động đến comparator có thể làm hỏng giả định thứ tự của cây. Muốn bảo toàn tính sorted ổn định, hãy dùng key bất biến theo tiêu chí so sánh.

### 12.4. Không tự động thread-safe

Unmodifiable map không cho sửa mapping qua reference trả về; nó không tự làm **đối tượng value mutable** trở thành thread-safe, và một unmodifiable **view** trên backing map được sửa đồng thời vẫn cần phối hợp phù hợp. Bất biến sâu và xuất bản an toàn là các vấn đề riêng.

### 12.5. `Map.copyOf` có thể trả lại cùng instance

Nếu nguồn đã là unmodifiable map phù hợp, JDK có thể không tạo object mới. Vì thế không dùng `==` hay identity hash code để suy luận nó đã copy dữ liệu theo cách nào. Quan tâm đến **hợp đồng bất biến cấu trúc**, không đến identity implementation.

### 12.6. Comparator có thể coi hai khóa `equals` khác nhau là tương đương

`TreeMap` sử dụng `Comparator.compare(k1,k2)==0` làm điều kiện tương đương khóa trong cấu trúc sắp xếp. Nếu comparator **không nhất quán với `equals`**, việc chuyển từ một `Map` chứa hai khóa khác nhau theo `equals` sang `TreeMap` có thể **gộp mất một mapping**.

Ví dụ:

```java
var source = java.util.Map.of("A", 1, "a", 2); // hai String khác nhau theo equals

var caseInsensitive = new java.util.TreeMap<String, Integer>(
        String.CASE_INSENSITIVE_ORDER);
caseInsensitive.putAll(source);
System.out.println(source.size());          // 2
System.out.println(caseInsensitive.size()); // 1
```

Không được coi thao tác chuyển sang một sorted map với comparator bất kỳ là **tương đương nội dung 100%**. Trước khi chuyển, cần biết comparator có phân biệt tất cả các khóa mà business logic coi là khác nhau hay không.

### 12.7. Những API có thứ tự mới hơn không tự “nâng cấp” `Map.copyOf`

Trong các phiên bản Java hiện đại, `SequencedMap` có thể mô tả encounter order của một số map và cung cấp API hướng thứ tự. Tuy nhiên, `Map.copyOf` vẫn chỉ có hợp đồng trả về `Map` không cam kết iteration order. Nếu dự án yêu cầu thứ tự, chọn đúng interface và implementation có bảo đảm phù hợp; đừng suy luận rằng vì Java có `SequencedMap` nên `Map.copyOf` tự giữ thứ tự.

## 13. Ví dụ Java 17+ độc lập, stdout không phụ thuộc thứ tự của `Map.copyOf`

Tạo tệp **`MapCopyOrderingDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.SortedMap;
import java.util.TreeMap;

public class MapCopyOrderingDemo {
    static <K, V> SortedMap<K, V> sortedSnapshot(SortedMap<K, V> source) {
        var copy = new TreeMap<K, V>(source);
        return Collections.unmodifiableSortedMap(copy);
    }

    static <K, V> Map<K, V> insertionSnapshot(Map<K, V> source) {
        var copy = new LinkedHashMap<K, V>(source);
        return Collections.unmodifiableMap(copy);
    }

    public static void main(String[] args) {
        var insertion = new LinkedHashMap<String, Integer>();
        insertion.put("C", 3);
        insertion.put("A", 1);
        insertion.put("B", 2);

        var plainCopy = Map.copyOf(insertion);
        System.out.println("sourceKeys=" + insertion.keySet());
        System.out.println("copyEqualsSource=" + plainCopy.equals(insertion));
        System.out.println("copySize=" + plainCopy.size());
        System.out.println("copyHasA=" + plainCopy.containsKey("A"));

        var sortedLines = plainCopy.entrySet().stream()
                .sorted(Map.Entry.comparingByKey())
                .map(e -> e.getKey() + "=" + e.getValue())
                .toList();
        System.out.println("copySortedLines=" + sortedLines);

        var stableInsertion = insertionSnapshot(insertion);
        insertion.put("D", 4);
        System.out.println("sourceAfterAdd=" + insertion.keySet());
        System.out.println("copyHasD=" + plainCopy.containsKey("D"));
        System.out.println("insertionSnapshotKeys=" + stableInsertion.keySet());

        SortedMap<String, Integer> descending =
                new TreeMap<>(Comparator.reverseOrder());
        descending.put("A", 1);
        descending.put("C", 3);
        descending.put("B", 2);

        var sortedCopy = Map.copyOf(descending);
        var stableSorted = sortedSnapshot(descending);
        System.out.println("sortedSourceKeys=" + descending.keySet());
        System.out.println("sortedCopyEquals=" + sortedCopy.equals(descending));
        System.out.println("sortedSnapshotKeys=" + stableSorted.keySet());
        System.out.println("sortedSnapshotFirst=" + stableSorted.firstKey());

        descending.put("D", 4);
        System.out.println("sortedSourceAfterAdd=" + descending.keySet());
        System.out.println("sortedCopyHasD=" + sortedCopy.containsKey("D"));
        System.out.println("sortedSnapshotAfterAdd=" + stableSorted.keySet());

        var liveView = Collections.unmodifiableSortedMap(descending);
        descending.put("E", 5);
        System.out.println("liveViewKeys=" + liveView.keySet());

        Map<String, Integer> asMap = descending;
        var naturalCopy = new TreeMap<String, Integer>(asMap);
        System.out.println("naturalCopyFirst=" + naturalCopy.firstKey());

        try {
            stableSorted.put("Z", 99);
        } catch (UnsupportedOperationException expected) {
            System.out.println("sortedSnapshotUnmodifiable=true");
        }

        var nullable = new HashMap<String, Integer>();
        nullable.put("X", null);
        try {
            Map.copyOf(nullable);
        } catch (NullPointerException expected) {
            System.out.println("copyRejectsNullValue=true");
        }

        var colliding = Map.of("A", 1, "a", 2);
        var caseInsensitive = new TreeMap<String, Integer>(
                String.CASE_INSENSITIVE_ORDER);
        caseInsensitive.putAll(colliding);
        System.out.println("caseSensitiveCount=" + colliding.size());
        System.out.println("caseInsensitiveCount=" + caseInsensitive.size());

        var value = new StringBuilder("v1");
        var valueCopy = Map.copyOf(Map.of("K", value));
        value.append("X");
        System.out.println("mutableValue=" + valueCopy.get("K"));
    }
}
```

Lệnh biên dịch/chạy (JDK 17 trở lên):

```bash
javac --release 17 -encoding UTF-8 MapCopyOrderingDemo.java
java MapCopyOrderingDemo
```

**Stdout chính xác:**

```text
sourceKeys=[C, A, B]
copyEqualsSource=true
copySize=3
copyHasA=true
copySortedLines=[A=1, B=2, C=3]
sourceAfterAdd=[C, A, B, D]
copyHasD=false
insertionSnapshotKeys=[C, A, B]
sortedSourceKeys=[C, B, A]
sortedCopyEquals=true
sortedSnapshotKeys=[C, B, A]
sortedSnapshotFirst=C
sortedSourceAfterAdd=[D, C, B, A]
sortedCopyHasD=false
sortedSnapshotAfterAdd=[C, B, A]
liveViewKeys=[E, D, C, B, A]
naturalCopyFirst=A
sortedSnapshotUnmodifiable=true
copyRejectsNullValue=true
caseSensitiveCount=2
caseInsensitiveCount=1
mutableValue=v1X
```

### Phân tích ví dụ

1. `insertion` giữ thứ tự chèn `[C, A, B]`. `Map.copyOf(insertion)` có cùng mapping và kích thước, **nhưng chương trình cố ý không in `plainCopy.keySet()` vì API không cam kết thứ tự của nó**.
2. `sortedLines` sắp xếp bằng `Map.Entry.comparingByKey()` trước khi in, nên thứ tự `[A=1, B=2, C=3]` xác định.
3. `stableInsertion` sao chép vào `LinkedHashMap` rồi bọc `unmodifiableMap`; thêm `D` vào nguồn không làm snapshot thay đổi.
4. `descending` là `SortedMap` với `Comparator.reverseOrder()`. `stableSorted` dùng constructor `TreeMap(SortedMap)`, nên vẫn duyệt `[C, B, A]` và `firstKey()` trả `C`.
5. `sortedCopy` từ `Map.copyOf` **vẫn có mapping bằng nguồn tại lúc copy**, nhưng không được giả định có `firstKey`, comparator hoặc một thứ tự duyệt nhất định.
6. `liveView` phản ánh thay đổi `E` trong backing `descending`, khác với snapshot `stableSorted`.
7. `naturalCopy` nhận biến kiểu tĩnh `Map` nên constructor `TreeMap(Map)` sắp xếp tự nhiên, `firstKey()` trả `A`.
8. `stableSorted.put` bị chặn; `Map.copyOf` không chấp nhận value `null`.
9. Comparator case-insensitive gộp khóa `"A"` và `"a"`, minh họa rủi ro khi comparator không nhất quán với `equals`.
10. `valueCopy` vẫn trỏ tới `StringBuilder` chung, cho thấy không có deep copy dù mapping không cho sửa.

Không có dòng output nào dựa vào thứ tự duyệt không được cam kết của `Map.copyOf` hay `HashMap`.

## 14. Những lỗi dễ gặp và cách sửa

### Lỗi A: “Nguồn là `TreeMap` nên bản `copyOf` vẫn tự động sorted”

```java
SortedMap<String, Integer> source = new TreeMap<>();
source.put("B", 2);
source.put("A", 1);

var copy = Map.copyOf(source);
// copy.firstKey(); // Lỗi biên dịch: kiểu Map không có firstKey
```

**Sửa:** nếu cần sorted snapshot, chọn `Collections.unmodifiableSortedMap(new TreeMap<>(source))` với nguồn được khai báo là `SortedMap`; nếu chỉ cần in có thứ tự, sắp xếp stream.

### Lỗi B: “`Map.copyOf` giữ insertion order của `LinkedHashMap`”

```java
var source = new LinkedHashMap<String, Integer>();
source.put("B", 2);
source.put("A", 1);

var copy = Map.copyOf(source);
// Không khẳng định copy.keySet() in [B, A].
```

**Sửa:** `Collections.unmodifiableMap(new LinkedHashMap<>(source))` khi cần snapshot có thứ tự chèn.

### Lỗi C: “`Collections.unmodifiableSortedMap(source)` là snapshot”

```java
var source = new TreeMap<String, Integer>();
var view = Collections.unmodifiableSortedMap(source);
source.put("A", 1); // view thấy A
```

**Sửa:** copy sang `TreeMap` mới trước khi bọc, không làm lộ backing copy.

### Lỗi D: “`new TreeMap<>(map)` sẽ luôn giữ comparator gốc”

Không đúng nếu overload nhận đối số **kiểu tĩnh `Map`**. Constructor `TreeMap(Map)` sắp theo natural ordering. Để giữ comparator, dùng `TreeMap(SortedMap)` hoặc tạo `TreeMap` với comparator tường minh.

### Lỗi E: Test so sánh `Map.copyOf(source).toString()`

Test so sánh chuỗi phụ thuộc thứ tự duyệt có thể lỗi sau khi đổi JDK mà code vẫn đúng.

**Sửa:** so sánh `Map.equals`, `get`, `size` và `containsKey` cho nội dung. Nếu thứ tự được yêu cầu, dùng structure có hợp đồng hoặc sắp xếp trước khi assert.

### Lỗi F: Chọn comparator vô tình gộp khóa

Nếu comparator trả `0` cho hai khóa khác nhau theo `equals`, `TreeMap` có thể chỉ giữ một mapping trong hai.

**Sửa:** dùng comparator **nhất quán với `equals`** nếu hệ thống cần giữ nguyên mọi mapping, hoặc mô tả rõ việc gộp khóa theo comparator là quy tắc nghiệp vụ.

### Lỗi G: Lẫn “không sửa map” với “không sửa value”

`Map.copyOf`, `Collections.unmodifiableMap` và `Collections.unmodifiableSortedMap` đều không tự đóng băng value mutable. Nếu cần snapshot sâu, chuyển đổi value sang kiểu bất biến hoặc phòng vệ khi copy.

### Lỗi H: Quên giá trị `null` ở map nguồn

Một `TreeMap`/`HashMap` chứa value `null` có thể hoạt động bình thường, nhưng `Map.copyOf` sẽ ném `NullPointerException`. Chọn API và chính sách null theo yêu cầu sản phẩm, đừng chỉ xét thứ tự.

## 15. Checklist khi review `Map.copyOf(source)`

Đánh giá từ yêu cầu nghiệp vụ, không từ thứ tự tình cờ trong debugger:

1. **Ứng dụng có cần duyệt theo thứ tự nào không?** Natural order, comparator tùy chỉnh, thứ tự chèn hay không quan trọng?
2. **Nguồn có cam kết thứ tự không?** `TreeMap`, `LinkedHashMap`, `HashMap` khác nhau; `Map.copyOf` không tự chuyển tiếp cam kết ấy.
3. **Có cần API `SortedMap`/`NavigableMap` không?** Nếu có, `Map.copyOf` không đáp ứng hợp đồng interface.
4. **Có cần snapshot hay live view?** Snapshot cấu trúc và wrapper live là hai nhu cầu khác nhau.
5. **Nếu copy sang `TreeMap`, overload nào được chọn?** `TreeMap(Map)` so với `TreeMap(SortedMap)`; comparator có được giữ không?
6. **Comparator có nhất quán với `equals` không?** Nếu không, các khóa “khác nhau theo map gốc” có thể bị gộp.
7. **Nguồn có `null` không?** `Map.copyOf` từ chối khóa/giá trị null; các wrapper trên map khác có thể có hợp đồng khác.
8. **Khóa và giá trị có mutable không?** Copy mapping không phải deep copy.
9. **Kết quả có bị sửa qua một alias tới backing map không?** Khi dùng wrapper, chỉ trả wrapper trên bản copy không bị lộ.
10. **Test kiểm giá trị hay kiểm thứ tự?** Với `Map.copyOf` chỉ nên kiểm nội dung; nếu cần thứ tự, kiểm map hoặc kết quả đã được sắp xếp có chủ đích.
11. **Có khả năng truy cập đa luồng không?** Unmodifiable view không thay cho đồng bộ hóa khi backing map hoặc value mutable có thể đổi.
12. **Có thật sự cần copy?** Nếu chỉ muốn bảo vệ mapping khỏi sửa từ caller và không quan tâm thứ tự, `Map.copyOf` là giải pháp gọn và rõ.

## 16. Bài tập tự kiểm tra

**Câu 1.** Một `TreeMap<String,Integer>` duyệt theo thứ tự khóa tăng dần. `Map.copyOf(tree)` có bắt buộc duyệt tăng dần không?

**Câu 2.** `Map.copyOf(tree).equals(tree)` là `true`. Có thể kết luận thứ tự iterator cũng giống nhau không?

**Câu 3.** Khi cần snapshot chỉ đọc và giữ comparator của `SortedMap`, nên dùng cấu trúc nào?

**Câu 4.** Vì sao `Collections.unmodifiableSortedMap(source)` chưa phải snapshot nếu `source` còn có thể bị sửa?

**Câu 5.** Với `LinkedHashMap` được chèn `C, A, B`, làm sao trả về map không sửa được duyệt theo đúng thứ tự ấy mà không bị ảnh hưởng khi source thay đổi?

**Câu 6.** `new TreeMap<>(someMap)` và `new TreeMap<>(someSortedMap)` có khác gì về comparator?

**Câu 7.** Khi chỉ muốn xuất báo cáo A–Z từ `Map.copyOf(source)`, có cần dựng lại cả map không?

**Câu 8.** Nếu comparator phân biệt hoa/thường không giống `String.equals`, có thể mất mapping khi chuyển sang `TreeMap` không?

**Câu 9.** `Map.copyOf` từ một `HashMap` có value `null` sẽ thế nào?

**Câu 10.** `Map.copyOf(Map.of("K", new StringBuilder("A")))` có làm `StringBuilder` bất biến không?

**Đáp án:**

1. Không. Hợp đồng `Map.copyOf` không bảo đảm encounter order, kể cả nguồn `TreeMap` có sắp xếp.
2. Không. `Map.equals` so sánh mapping; thứ tự duyệt không tham gia phép so sánh bằng nhau.
3. Copy bằng `new TreeMap<>(sortedSource)` với đối số **kiểu tĩnh `SortedMap`** rồi trả `Collections.unmodifiableSortedMap(copy)`; hoặc `unmodifiableNavigableMap` khi cần API điều hướng.
4. Vì wrapper là live view; sửa backing `source` vẫn hiện lên view.
5. `Collections.unmodifiableMap(new LinkedHashMap<>(source))` với source có encounter order mong muốn; không lộ backing copy.
6. Constructor `TreeMap(Map)` dùng natural ordering; `TreeMap(SortedMap)` giữ comparator/order của nguồn.
7. Không. Dùng `copy.entrySet().stream().sorted(Map.Entry.comparingByKey())` rồi map ra dòng; đó là thứ tự khi **xuất**, không thay đổi map.
8. Có. Nếu comparator coi hai khóa khác nhau theo `equals` là tương đương (`compare==0`), `TreeMap` chỉ giữ một mapping cho nhóm.
9. Ném `NullPointerException`; cần xử lý/chọn hợp đồng null trước khi sao chép.
10. Không. Mapping không sửa được, nhưng object value vẫn mutable và reference có thể được chia sẻ.

## 17. Tóm tắt và nguồn Java chính thức hiện hành

- **`Map.copyOf` (Java 10+) giữ mapping, không cam kết thứ tự duyệt.**
- `TreeMap`/`SortedMap` nguồn có comparator **không** làm kết quả `Map.copyOf` tự trở thành sorted map.
- `LinkedHashMap` nguồn có insertion order **không** buộc `Map.copyOf` giữ thứ tự ấy.
- Muốn **sorted snapshot không sửa được**: tạo một `TreeMap` mới từ **`SortedMap` được định kiểu rõ**, bọc bằng `Collections.unmodifiableSortedMap` hoặc `Collections.unmodifiableNavigableMap`.
- Muốn **insertion-order snapshot không sửa được**: tạo `LinkedHashMap` copy rồi bọc bằng `Collections.unmodifiableMap`.
- Chỉ cần xuất có thứ tự: **sắp xếp entry stream** trước khi xuất, không dựa vào iterator của `Map.copyOf`.
- Hãy đánh giá **live view vs snapshot**, overload constructor, comparator consistency, `null`, key/value mutable và test không dựa vào thứ tự không được bảo đảm.

Tài liệu chính thức, vẫn có hiệu lực:

1. [Java SE 27 API — `Map.copyOf` và Unmodifiable Maps](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): quy tắc không cam kết iteration order, `null`, snapshot mapping và tính unmodifiable.
2. [Java SE 27 API — `TreeMap`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/TreeMap.html): constructor `Map` vs `SortedMap` và comparator.
3. [Java SE 27 API — `Collections.unmodifiableSortedMap`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Collections.html#unmodifiableSortedMap(java.util.SortedMap)): wrapper view có hợp đồng sorted map.
4. [Java SE 27 API — `Collections.unmodifiableNavigableMap`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Collections.html#unmodifiableNavigableMap(java.util.NavigableMap)): API điều hướng trên view không cho sửa.
5. [Java SE 27 API — `LinkedHashMap`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/LinkedHashMap.html): encounter order và conversion constructor.
6. [Java SE 27 API — `SortedMap`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/SortedMap.html): giao diện bản đồ sắp xếp, `firstKey`, `lastKey` và comparator.
