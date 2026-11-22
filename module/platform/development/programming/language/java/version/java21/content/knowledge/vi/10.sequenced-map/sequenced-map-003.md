# firstEntry, lastEntry và kết quả khi map rỗng

Trong Java 21, `SequencedMap<K, V>` biểu diễn map có **encounter order** xác định và cho phép truy cập mapping ở hai đầu. Hai phương thức `firstEntry()` và `lastEntry()` trả về mapping đầu tiên hoặc cuối cùng theo thứ tự đó. Nếu map rỗng, cả hai trả về `null`.

Giá trị trả về là một `Map.Entry` snapshot không thể sửa bằng `setValue()`. Gọi `firstEntry()` hoặc `lastEntry()` chỉ đọc mapping, không xóa nó khỏi map. Nếu cần lấy và đồng thời xóa mapping ở một đầu, dùng `pollFirstEntry()` hoặc `pollLastEntry()`.

`firstEntry()` và `lastEntry()` đã có trên `NavigableMap` từ trước. Điểm mới trong Java 21 là `SequencedMap` đưa khả năng truy cập hai đầu vào một interface chung cho các map có thứ tự, bao gồm cả `LinkedHashMap`.

## 1. SequencedMap và encounter order

`SequencedMap<K, V>` thuộc `java.util`, mở rộng `Map<K, V>` và quy định thứ tự duyệt của các mapping. Thứ tự này quyết định mapping nào được xem là đầu tiên và mapping nào là cuối cùng.

Một số implementation và kiểu map liên quan:

- `LinkedHashMap<K, V>` duy trì encounter order. Mặc định là thứ tự thêm mapping; constructor có `accessOrder = true` có thể duy trì thứ tự truy cập.
- `SortedMap<K, V>` và `NavigableMap<K, V>` duy trì thứ tự theo natural ordering của key hoặc theo `Comparator` được cung cấp. `TreeMap` là implementation phổ biến.
- `HashMap<K, V>` không triển khai `SequencedMap`; không nên dựa vào thứ tự duyệt của nó để xác định mapping đầu hoặc cuối.

Do đó, “đầu” và “cuối” không nhất thiết có cùng ý nghĩa với mọi implementation. Với `LinkedHashMap` mặc định, đó là mapping theo thứ tự được thêm. Với access-order `LinkedHashMap`, encounter order phản ánh thứ tự truy cập hiện tại. Với `TreeMap`, đầu và cuối phụ thuộc vào thứ tự key theo comparator.

## 2. Cú pháp và hợp đồng firstEntry/lastEntry

Hai phương thức có chữ ký:

```java
Map.Entry<K, V> firstEntry();
Map.Entry<K, V> lastEntry();
```

- `firstEntry()` trả về mapping đầu tiên theo encounter order.
- `lastEntry()` trả về mapping cuối cùng theo encounter order.
- Nếu map rỗng, cả hai trả về `null`.
- Nếu map có ít nhất một mapping, phương thức trả về một `Map.Entry` không null, kể cả khi key hoặc value của mapping đó là `null` và implementation cho phép null.
- Entry trả về là snapshot không thể sửa đổi; `setValue()` không được hỗ trợ.
- Hai phương thức không thay đổi map.

Ví dụ với `LinkedHashMap`:

```java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.SequencedMap;

public class SequencedMapEndsDemo {
    public static void main(String[] args) {
        SequencedMap<String, Integer> stock = new LinkedHashMap<>();
        stock.put("apple", 12);
        stock.put("orange", 8);
        stock.put("pear", 5);

        Map.Entry<String, Integer> first = stock.firstEntry();
        Map.Entry<String, Integer> last = stock.lastEntry();

        System.out.println(first.getKey() + " = " + first.getValue());
        System.out.println(last.getKey() + " = " + last.getValue());
        System.out.println(stock);
    }
}
```

Kết quả:

```text
apple = 12
pear = 5
{apple=12, orange=8, pear=5}
```

Map vẫn giữ nguyên ba mapping sau hai lời gọi. Vì biến được khai báo bằng `SequencedMap`, compiler nhận diện được `firstEntry()` và `lastEntry()` thông qua kiểu interface.

## 3. Hành vi khi map rỗng

Khác với `SequencedCollection.getFirst()` và `getLast()`, hai phương thức của `SequencedMap` không ném `NoSuchElementException` khi map rỗng. Chúng trả về `null`:

```java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.SequencedMap;

public class EmptySequencedMapDemo {
    public static void main(String[] args) {
        SequencedMap<String, Integer> stock = new LinkedHashMap<>();

        Map.Entry<String, Integer> first = stock.firstEntry();
        Map.Entry<String, Integer> last = stock.lastEntry();

        System.out.println(first); // null
        System.out.println(last);  // null
    }
}
```

Khi map rỗng là trạng thái hợp lệ, kiểm tra kết quả null trước khi truy cập key hoặc value:

```java
static <K, V> void printEnds(SequencedMap<K, V> map) {
    Map.Entry<K, V> first = map.firstEntry();
    if (first == null) {
        System.out.println("Map rỗng");
        return;
    }

    Map.Entry<K, V> last = map.lastEntry();
    System.out.println("Đầu: " + first.getKey() + " -> " + first.getValue());
    System.out.println("Cuối: " + last.getKey() + " -> " + last.getValue());
}
```

Nếu map rỗng biểu thị dữ liệu đầu vào không hợp lệ, có thể ném exception nghiệp vụ ở tầng phù hợp. Nếu map rỗng là bình thường, trả về hoặc hiển thị trạng thái rỗng thường dễ hiểu hơn. Không gọi `getKey()` hoặc `getValue()` trước khi xác nhận entry khác null.

## 4. Phân biệt map rỗng với mapping có key/value null

Một số implementation như `LinkedHashMap` cho phép key null và value null. Vì vậy, không được nhầm một entry chứa null với trường hợp map rỗng.

```java
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.SequencedMap;

SequencedMap<String, String> values = new LinkedHashMap<>();
values.put(null, null);

Map.Entry<String, String> first = values.firstEntry();

System.out.println(values.isEmpty());       // false
System.out.println(first == null);         // false
System.out.println(first.getKey());        // null
System.out.println(first.getValue());      // null
```

Map đang có một mapping nên `firstEntry()` trả về một đối tượng `Map.Entry` khác null. Key và value bên trong entry có thể null. Điều kiện `entry == null` biểu thị map không có mapping đầu/cuối, không biểu thị key hoặc value null.

Không phải implementation nào cũng cho phép null. `TreeMap` với natural ordering không chấp nhận null key; khả năng chấp nhận null value phụ thuộc implementation. Luôn xét hợp đồng của map cụ thể thay vì suy luận từ interface chung.

## 5. Entry trả về là snapshot, không phải cách sửa map

`firstEntry()` và `lastEntry()` trả về entry snapshot tại thời điểm gọi. Không dùng `setValue()` để cập nhật mapping:

```java
SequencedMap<String, Integer> scores = new LinkedHashMap<>();
scores.put("An", 9);

Map.Entry<String, Integer> first = scores.firstEntry();

// Không được hỗ trợ: entry snapshot không cho phép setValue.
// first.setValue(10); // ném UnsupportedOperationException

// Cập nhật map bằng API của map:
scores.put("An", 10);
```

Entry snapshot giữ key/value đã quan sát ở thời điểm lấy entry. Nếu map thay đổi sau đó, không nên xem entry cũ là một view trực tiếp của mapping hiện tại. Hãy gọi lại `firstEntry()` hoặc `lastEntry()` nếu cần quan sát trạng thái mới.

## 6. Phân biệt firstEntry/lastEntry với pollFirstEntry/pollLastEntry

Hai cặp phương thức có mục đích khác nhau:

| Phương thức | Kết quả | Có xóa mapping khỏi map? | Khi map rỗng |
|---|---|---|---|
| `firstEntry()` | Entry đầu tiên | Không | Trả về `null` |
| `lastEntry()` | Entry cuối cùng | Không | Trả về `null` |
| `pollFirstEntry()` | Entry đầu tiên | Có | Trả về `null` |
| `pollLastEntry()` | Entry cuối cùng | Có | Trả về `null` |

Ví dụ lấy và xóa mapping đầu tiên:

```java
SequencedMap<String, Integer> queue = new LinkedHashMap<>();
queue.put("job-1", 1);
queue.put("job-2", 2);

Map.Entry<String, Integer> peeked = queue.firstEntry();
System.out.println(peeked); // job-1=1
System.out.println(queue.size()); // 2

Map.Entry<String, Integer> removed = queue.pollFirstEntry();
System.out.println(removed); // job-1=1
System.out.println(queue.size()); // 1
```

Tên `poll` biểu thị thao tác lấy ra khỏi map, vì vậy chỉ dùng khi muốn loại bỏ mapping. Nếu chỉ cần xem mapping đầu/cuối, dùng `firstEntry()` hoặc `lastEntry()` để giữ nguyên dữ liệu.

## 7. Dùng với LinkedHashMap và TreeMap

### LinkedHashMap

`LinkedHashMap` là lựa chọn phổ biến khi cần giữ thứ tự mapping theo lúc thêm:

```java
import java.util.LinkedHashMap;
import java.util.SequencedMap;

SequencedMap<String, String> headers = new LinkedHashMap<>();
headers.put("Content-Type", "application/json");
headers.put("Accept", "application/json");
headers.put("Cache-Control", "no-cache");

System.out.println(headers.firstEntry()); // Content-Type=application/json
System.out.println(headers.lastEntry());  // Cache-Control=no-cache
```

`LinkedHashMap` cũng có thể được tạo ở access-order. Trong trường hợp đó, encounter order thay đổi theo các thao tác truy cập được định nghĩa bởi `LinkedHashMap`, nên first/last phản ánh thứ tự hiện tại thay vì thứ tự thêm ban đầu. Nếu logic nghiệp vụ cần thứ tự thêm ổn định, dùng chế độ insertion-order mặc định.

### TreeMap

`TreeMap` duy trì mapping theo thứ tự key. Khi nhìn qua `SequencedMap`, hai phương thức first/last lấy mapping ở hai đầu thứ tự sắp xếp:

```java
import java.util.SequencedMap;
import java.util.TreeMap;

SequencedMap<Integer, String> priorities = new TreeMap<>();
priorities.put(30, "Low");
priorities.put(10, "High");
priorities.put(20, "Normal");

System.out.println(priorities.firstEntry()); // 10=High
System.out.println(priorities.lastEntry());  // 30=Low
```

Đầu và cuối ở đây được quyết định bởi natural ordering hoặc comparator, không phải thứ tự gọi `put`. `TreeMap` cũng đã có các phương thức `firstEntry()` và `lastEntry()` thông qua `NavigableMap`; Java 21 cho phép sử dụng các thao tác sequenced này qua kiểu chung `SequencedMap`.

## 8. Làm việc qua kiểu SequencedMap và reversed()

Khi một phương thức cần nhận nhiều loại map có encounter order, khai báo tham số bằng `SequencedMap<K, V>`:

```java
static <K, V> void logEnds(SequencedMap<K, V> map) {
    Map.Entry<K, V> first = map.firstEntry();
    Map.Entry<K, V> last = map.lastEntry();

    if (first == null) {
        System.out.println("Không có mapping");
        return;
    }

    System.out.println("First: " + first);
    System.out.println("Last: " + last);
}
```

Phương thức có thể nhận `LinkedHashMap`, `TreeMap` hoặc implementation khác triển khai `SequencedMap`. Một biến khai báo bằng `Map<K, V>` không thể gọi trực tiếp `firstEntry()` và `lastEntry()`, vì `Map` không công bố hai phương thức này. Hãy khai báo bằng interface thể hiện đúng khả năng mà phương thức cần.

`SequencedMap.reversed()` cung cấp view có encounter order đảo ngược. Mapping đầu tiên của view đảo tương ứng mapping cuối cùng của map gốc:

```java
SequencedMap<String, Integer> values = new LinkedHashMap<>();
values.put("A", 1);
values.put("B", 2);
values.put("C", 3);

SequencedMap<String, Integer> reversed = values.reversed();

System.out.println(values.firstEntry());   // A=1
System.out.println(values.lastEntry());    // C=3
System.out.println(reversed.firstEntry()); // C=3
System.out.println(reversed.lastEntry());  // A=1
```

`reversed()` trả về view, không tạo bản sao độc lập. Thay đổi được hỗ trợ qua view sẽ phản ánh lên map gốc. Nếu chỉ cần mapping cuối cùng, gọi `lastEntry()` trực tiếp thường đơn giản hơn việc tạo view đảo rồi lấy `firstEntry()`.

## 9. Lỗi thường gặp và cách xử lý

| Tình huống | Nguyên nhân | Cách xử lý |
|---|---|---|
| `firstEntry()` trả về null | Map rỗng | Kiểm tra entry null trước khi gọi `getKey()` hoặc `getValue()` |
| `lastEntry()` trả về null | Map rỗng | Xử lý trường hợp không có mapping cuối |
| Nhầm entry null với key/value null | Chỉ kiểm tra dữ liệu bên trong entry thay vì kiểm tra chính entry | Kiểm tra `entry == null`; entry có thể khác null dù key hoặc value null |
| `cannot find symbol: firstEntry()` | Biến được khai báo bằng `Map` hoặc compiler thấp hơn Java 21 đối với `SequencedMap` | Dùng `SequencedMap` hoặc `NavigableMap` phù hợp và JDK 21 |
| Mapping biến mất sau khi đọc | Đã gọi `pollFirstEntry()` hoặc `pollLastEntry()` | Dùng `firstEntry()`/`lastEntry()` nếu chỉ cần đọc |
| `setValue()` ném `UnsupportedOperationException` | Entry trả về là snapshot không thể sửa | Cập nhật mapping bằng `map.put(key, value)` hoặc API sửa đổi phù hợp |
| Đầu/cuối không theo thứ tự thêm | Map dùng comparator hoặc access-order | Xác định encounter order của implementation và cấu hình phù hợp |

Nếu map có thể bị thread khác thay đổi đồng thời, một entry snapshot chỉ phản ánh trạng thái tại thời điểm gọi. Cặp thao tác kiểm tra `isEmpty()` rồi lấy entry cũng không tự trở thành một thao tác nguyên tử; cần đồng bộ hoặc dùng cơ chế concurrency phù hợp với yêu cầu của ứng dụng.

## 10. Checklist khi sử dụng firstEntry/lastEntry

- Biến có kiểu khai báo hỗ trợ `SequencedMap` hoặc `NavigableMap`.
- Đã hiểu encounter order: thứ tự thêm, access-order hay thứ tự theo comparator.
- Kiểm tra kết quả entry có null trước khi đọc key/value nếu map có thể rỗng.
- Phân biệt entry null (map rỗng) với entry chứa key hoặc value null.
- Nhớ rằng entry trả về là snapshot không thể sửa bằng `setValue()`.
- Dùng `firstEntry()`/`lastEntry()` để đọc và `pollFirstEntry()`/`pollLastEntry()` để lấy đồng thời xóa.
- Không giả định map khai báo bằng `Map<K, V>` có thể gọi API của `SequencedMap`.
- Xem xét đồng bộ nếu map có thể bị thay đổi đồng thời.

`firstEntry()` và `lastEntry()` cung cấp cách đọc mapping ở hai đầu của một sequenced map. Khi map rỗng, cả hai trả về `null`; khi map có mapping chứa key hoặc value null, entry vẫn là một đối tượng khác null. Phân biệt đúng hai trạng thái này, hiểu snapshot và chọn đúng giữa thao tác đọc với thao tác poll giúp tránh lỗi khi làm việc với `SequencedMap` trong Java 21.
