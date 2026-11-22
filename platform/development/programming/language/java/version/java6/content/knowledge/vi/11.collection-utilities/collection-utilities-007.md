# AbstractMap.SimpleEntry và cập nhật value trong Java

## 1. Vì sao cần SimpleEntry?

`java.util.AbstractMap.SimpleEntry<K, V>` là lớp lồng `static` của `AbstractMap`, triển khai `Map.Entry<K, V>`. Mỗi instance giữ một cặp khóa–giá trị. Giá trị có thể thay đổi bằng `setValue(V newValue)`, còn khóa không có setter. Lớp được bổ sung từ Java 6 và **vẫn được hỗ trợ trong Java hiện đại**, phù hợp khi cần một cặp khóa–giá trị độc lập có thể cập nhật.

**Điểm cần phân biệt ngay:** `SimpleEntry` không có liên kết với bất kỳ `Map` nào, kể cả khi được tạo bằng constructor nhận `Map.Entry`. Sửa value của `SimpleEntry` không tự động cập nhật map nguồn. Ngược lại, sửa một entry đang được duyệt từ `map.entrySet()` có thể cập nhật trực tiếp map nếu implementation hỗ trợ.

Mục tiêu của bài:
- Tạo `SimpleEntry` với generic và dùng `getKey()`, `getValue()`, `setValue()`.
- Biết chính xác giá trị trả về của `setValue` và những gì không thay đổi.
- Phân biệt bản sao `SimpleEntry` với một entry từ map view.
- Hiểu `equals`, `hashCode`, tính mutable, và chọn API hiện đại thích hợp.

## 2. API cần nắm

```java
import java.util.AbstractMap;
import java.util.Map;

Map.Entry<String, Integer> entry =
        new AbstractMap.SimpleEntry<>("threshold", 10);
```

| Thành phần | Hành vi |
| --- | --- |
| `SimpleEntry(K key, V value)` | Tạo một cặp độc lập từ key và value. |
| `SimpleEntry(Map.Entry<? extends K, ? extends V> entry)` | Tạo bản sao của cặp key/value tại thời điểm gọi; không liên kết với map. |
| `K getKey()` | Trả về key đã được giữ từ khi khởi tạo. |
| `V getValue()` | Trả về value hiện tại của entry. |
| `V setValue(V newValue)` | Thay value và **trả về value cũ**. |
| `equals` / `hashCode` | So sánh theo key và value, tuân theo hợp đồng `Map.Entry`. |
| `toString()` | Trả về chuỗi dễ đọc như `threshold=10`. |

Lệnh `V old = entry.setValue(next);` có hai kết quả đồng thời: biến `old` giữ **giá trị trước cập nhật**, còn `entry.getValue()` trả **giá trị mới**. `setValue` không trả về entry và không sửa khóa. `K`, `V` là tham số generic, vì vậy dùng `Integer` thay cho kiểu nguyên thủy `int`.

`SimpleEntry` cho phép `null` ở key hoặc value; lời gọi `setValue(null)` cũng hợp lệ. Điều này không có nghĩa mọi loại `Map` đều chấp nhận `null`.

## 3. Ví dụ: cập nhật value và lấy giá trị cũ

Tạo file `SimpleEntryBasics.java`:

```java
import java.util.AbstractMap;

public class SimpleEntryBasics {
    public static void main(String[] args) {
        AbstractMap.SimpleEntry<String, Integer> quota =
                new AbstractMap.SimpleEntry<>("quota", 10);

        System.out.println(quota.getKey() + "=" + quota.getValue());

        Integer oldValue = quota.setValue(15);

        System.out.println("old=" + oldValue);
        System.out.println("new=" + quota.getValue());
        System.out.println("key=" + quota.getKey());
    }
}
```

Biên dịch và chạy trên JDK 17+:

```bash
javac SimpleEntryBasics.java
java SimpleEntryBasics
```

Output:

```text
quota=10
old=10
new=15
key=quota
```

Ban đầu cặp có value `10`; sau `setValue(15)`, entry chứa `15` nhưng biến `oldValue` chứa `10`. Key luôn là `"quota"` trong cả hai lần đọc.

Trường hợp value cũ là `null`:

```java
AbstractMap.SimpleEntry<String, Integer> item =
        new AbstractMap.SimpleEntry<>("limit", null);
Integer previous = item.setValue(0); // previous == null
// item.getValue() == 0
```

Đây là đoạn minh họa đặt trong một phương thức/JShell, không phải một lớp chương trình độc lập.

## 4. SimpleEntry không cập nhật Map nguồn

### 4.1. Copy constructor tạo một entry tách biệt

Tạo file `DetachedEntryDemo.java`:

```java
import java.util.AbstractMap;
import java.util.HashMap;
import java.util.Map;

public class DetachedEntryDemo {
    public static void main(String[] args) {
        Map<String, Integer> source = new HashMap<>();
        source.put("cpu", 10);

        Map.Entry<String, Integer> mapEntry =
                source.entrySet().iterator().next();
        AbstractMap.SimpleEntry<String, Integer> copy =
                new AbstractMap.SimpleEntry<>(mapEntry);

        copy.setValue(20);
        System.out.println("map=" + source.get("cpu")
                + ", entry=" + copy.getValue());

        source.put("cpu", 30);
        System.out.println("map=" + source.get("cpu")
                + ", entry=" + copy.getValue());
    }
}
```

```bash
javac DetachedEntryDemo.java
java DetachedEntryDemo
```

```text
map=10, entry=20
map=30, entry=20
```

Sửa `copy` không chạm đến `source`. Về sau `source.put("cpu", 30)` cũng không cập nhật `copy`. Constructor `SimpleEntry(existingEntry)` chỉ tạo **bản sao độc lập**.

Lưu ý bản sao là **shallow copy**: Java sao chép tham chiếu đến key/value, không clone sâu nội dung của các đối tượng. Nếu value là object có trạng thái mutable, bản sao và map có thể cùng trỏ tới object đó. *Thay value bằng `setValue`* khác với *thay đổi nội dung của object value hiện có*.

### 4.2. Cập nhật mapping trong Map bằng API của Map

Nếu mục đích là sửa map đang chứa dữ liệu, thông thường sử dụng `put`, `replace`, `computeIfPresent`, hoặc `replaceAll`. Trong khi duyệt trực tiếp `entrySet()` của một map mutable, `entry.setValue` cũng có thể cập nhật map.

Tạo file `UpdateMapDemo.java`:

```java
import java.util.LinkedHashMap;
import java.util.Map;

public class UpdateMapDemo {
    public static void main(String[] args) {
        Map<String, Integer> scores = new LinkedHashMap<>();
        scores.put("An", 5);
        scores.put("Binh", 7);

        for (Map.Entry<String, Integer> entry : scores.entrySet()) {
            entry.setValue(entry.getValue() + 1);
        }

        System.out.println(scores);
    }
}
```

```bash
javac UpdateMapDemo.java
java UpdateMapDemo
```

```text
{An=6, Binh=8}
```

Các entry trong vòng lặp thuộc view của `scores` và `LinkedHashMap` hỗ trợ cập nhật value; vì thế hai mapping thật thay đổi.

**Không suy rộng hành vi này sang mọi `Map.Entry`.** Theo hợp đồng Java, `Map.Entry.setValue` là thao tác tùy chọn: entry bất biến có thể ném `UnsupportedOperationException`. Đối với entry lấy bằng cách duyệt `entrySet()`, liên kết với map chỉ được bảo đảm trong quá trình lặp; không giữ entry đó để sử dụng về sau rồi mặc định nó vẫn đồng bộ với map. Nếu map bị thay đổi sau khi lấy entry, ngoài thao tác `setValue` được cho phép trong vòng lặp, hành vi của entry có thể không xác định.

### 4.3. Quy tắc chọn nhanh

- **Cần sửa một cặp tạm thời độc lập:** `new SimpleEntry<>(key, value)` và `setValue(...)`.
- **Cần chỉnh bản sao của mapping:** `new SimpleEntry<>(someMapEntry)` rồi chỉnh copy.
- **Cần thay đổi dữ liệu của `Map`:** `map.put(key, value)`, `replace`, `computeIfPresent` hoặc cập nhật entry trong vòng lặp nếu map hỗ trợ.
- **Cần cặp cố định chỉ đọc:** cân nhắc `Map.entry(key, value)` từ Java 9+.

## 5. Ví dụ ứng dụng: danh sách cặp khóa–giá trị có thể chỉnh

Một luồng xử lý có thể xây dựng danh sách các giá trị đang chờ biến đổi. Khi danh sách này không phải một map thật, `SimpleEntry` lưu các cặp độc lập và cho phép sửa value tại chỗ.

Tạo file `PendingUpdatesDemo.java`:

```java
import java.util.AbstractMap;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class PendingUpdatesDemo {
    public static void main(String[] args) {
        List<Map.Entry<String, Integer>> pending = new ArrayList<>();
        pending.add(new AbstractMap.SimpleEntry<>("min", 2));
        pending.add(new AbstractMap.SimpleEntry<>("max", 8));

        for (Map.Entry<String, Integer> item : pending) {
            item.setValue(item.getValue() * 2);
        }

        for (Map.Entry<String, Integer> item : pending) {
            System.out.println(item.getKey() + "=" + item.getValue());
        }
    }
}
```

```bash
javac PendingUpdatesDemo.java
java PendingUpdatesDemo
```

```text
min=4
max=16
```

Mỗi phần tử được lưu dưới kiểu giao diện `Map.Entry` nhưng có implementation là `SimpleEntry`, nên lệnh `setValue` hoạt động. Nếu ứng dụng chỉ cần đọc, nên ưu tiên dữ liệu bất biến để tránh thay đổi ngoài ý muốn.

## 6. equals, hashCode và ý nghĩa của mutable value

Hai `Map.Entry` được coi là bằng nhau nếu cả key và value tương đương theo `equals` (có xét `null`); chúng không nhất thiết phải cùng lớp triển khai. `hashCode` của entry kết hợp hash từ key và value. Do đó **đổi value có thể làm đổi `equals` và `hashCode`**.

Tạo file `EntryEqualityDemo.java`:

```java
import java.util.AbstractMap;
import java.util.Map;

public class EntryEqualityDemo {
    public static void main(String[] args) {
        var mutable = new AbstractMap.SimpleEntry<>("mode", "safe");
        Map.Entry<String, String> fixed = Map.entry("mode", "safe");

        System.out.println(mutable.equals(fixed));

        mutable.setValue("fast");
        System.out.println(mutable.equals(fixed));
    }
}
```

```bash
javac EntryEqualityDemo.java
java EntryEqualityDemo
```

```text
true
false
```

**Không thay value của `SimpleEntry` khi nó đang đóng vai trò khóa trong `HashMap` hoặc phần tử của `HashSet`.** Các cấu trúc băm dựa vào hash ổn định trong khi phần tử nằm trong collection; sửa value có thể khiến tìm kiếm/loại bỏ hoạt động sai kỳ vọng. Nếu cần loại khóa băm, dùng một representation bất biến.

## 7. So sánh với các lựa chọn còn phù hợp hiện nay

| Trường hợp | API phù hợp | Đặc điểm |
| --- | --- | --- |
| Cặp độc lập, value phải thay được | `AbstractMap.SimpleEntry<K,V>` | `setValue` thay value và trả value cũ. |
| Cặp độc lập, value không cần thay | `AbstractMap.SimpleImmutableEntry<K,V>` | Không hỗ trợ `setValue`. |
| Tạo cặp cố định gọn trong Java 9+ | `Map.entry(k, v)` | Bất biến, không cho `null`, `setValue` ném `UnsupportedOperationException`. |
| Giá trị có hai hoặc nhiều trường mang ý nghĩa miền nghiệp vụ | Một `record` / class có tên trường rõ ràng | Ví dụ `record Price(String sku, int cents) {}`. |
| Thay value của mapping trong Map | `Map.put` / `replace` / `computeIfPresent` / `replaceAll` | Sửa map theo ràng buộc của implementation. |

`Map.entry` trả entry bất biến; đừng dùng khi cần `setValue`. Một map được tạo bằng `Map.of(...)` cũng không cho sửa mapping. `SimpleEntry` có thể chứa value `null`, còn `Map.entry` không chấp nhận key hoặc value `null`.

Không nên coi `SimpleEntry` là thay thế cho mọi loại dữ liệu hai trường: nếu mỗi trường có ý nghĩa nghiệp vụ riêng, `record` hoặc class có tên thích hợp thường dễ đọc và bảo trì hơn.

## 8. Những lỗi dễ mắc

1. **Hiểu nhầm giá trị trả về.** `old = entry.setValue(newValue)` lưu *giá trị cũ* vào `old`; lấy giá trị mới bằng `entry.getValue()`.
2. **Lầm tưởng SimpleEntry gắn với map.** Copy từ `map.entrySet()` không tạo liên kết sống; sửa bản sao không thay map.
3. **Cho rằng mọi entry đều sửa được.** Giao diện `Map.Entry` cho phép implementation từ chối `setValue`; kiểm tra loại entry và tính mutable của map.
4. **Muốn sửa key.** `SimpleEntry` không có `setKey`. Hãy tạo entry mới; nếu đang quản lý map, thay mapping bằng API của map.
5. **Đổi value sau khi chèn vào HashSet/HashMap làm khóa.** Khả năng thay đổi `hashCode` khiến cấu trúc băm không còn hoạt động đúng theo hợp đồng.
6. **Nhầm shallow copy với deep copy.** Value mutable được copy bằng tham chiếu, không nhân bản đối tượng.
7. **Dùng như dữ liệu an toàn cho nhiều luồng.** `SimpleEntry` tự nó không bảo đảm đồng bộ hóa. Nếu nhiều luồng ghi/đọc cùng entry, cần cơ chế đồng bộ thích hợp hoặc cấu trúc dữ liệu khác.
8. **Đặt `null` khi không có quy ước.** `SimpleEntry` cho phép `null`, nhưng việc cho phép này nên là quyết định thiết kế rõ ràng.

## 9. Câu hỏi tự kiểm tra

**1.** Có `new SimpleEntry<>("size", 3)`; sau `int before = entry.setValue(5)`, `before` và `entry.getValue()` bằng bao nhiêu?

**Đáp án:** `before == 3` và `entry.getValue() == 5`.

**2.** Tạo `SimpleEntry` từ `map.entrySet().iterator().next()`, sau đó `copy.setValue(100)`. Map nguồn có tự thay đổi không?

**Đáp án:** Không. `copy` là entry độc lập. Cập nhật map bằng API của `Map` hoặc bằng entry thuộc view của map khi được hỗ trợ.

**3.** Cần cặp `("port", 8080)` cố định trong Java 17+, không dùng `null`. Có thể chọn API nào?

**Đáp án:** `Map.entry("port", 8080)`; không gọi `setValue` trên entry đó.

## 10. Tham khảo chính thức

- [Oracle API — AbstractMap.SimpleEntry](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/AbstractMap.SimpleEntry.html): constructor, `setValue`, `equals` và tính độc lập với map.
- [Oracle API — Map.Entry](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.Entry.html): hợp đồng `Map.Entry`, giới hạn liên kết với `entrySet()`, thao tác `setValue` tùy chọn.
- [Oracle API — Map](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html): thao tác cập nhật mapping và `Map.entry`.
