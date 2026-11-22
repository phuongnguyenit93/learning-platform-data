# Hợp đồng `equals()` và `hashCode()` của `Map.Entry<K, V>`

## 1. Hiểu đúng một `Map.Entry`

`Map.Entry<K, V>` đại diện cho **một cặp ánh xạ khóa → giá trị**. Entry có thể được lấy từ `map.entrySet()` hoặc được tạo độc lập bởi `Map.entry(k, v)`, `AbstractMap.SimpleEntry`, `AbstractMap.SimpleImmutableEntry`. Các cách này vẫn được hỗ trợ trong Java hiện đại.

Hai entry xuất phát từ hai map khác nhau hoặc từ hai lớp triển khai khác nhau vẫn có thể bằng nhau. Java định nghĩa `equals` và `hashCode` **theo nội dung cặp khóa/giá trị**, không theo danh tính object, tên lớp hay map sở hữu entry. Đây là hợp đồng đang có hiệu lực trong Java hiện nay. Ví dụ chạy được trên **Java 17+**.

## 2. Hợp đồng `equals(Object)`

Hai entry `a` và `b` bằng nhau khi đối tượng so sánh cũng là `Map.Entry` và **cả khóa lẫn giá trị** tương đương theo `equals`:

~~~java
Objects.equals(a.getKey(), b.getKey())
        && Objects.equals(a.getValue(), b.getValue())
~~~

Đây là biểu thức **minh họa trong một ngữ cảnh đã khai báo `a`/`b`**, không phải chương trình độc lập. `Objects.equals(x, y)` trả `true` khi cả hai cùng `null` hoặc khi `x != null` và `x.equals(y)`. Nó tránh `NullPointerException` khi thành phần có thể `null`.

| Entry A | Entry B | Bằng nhau? | Giải thích |
| --- | --- | --- | --- |
| `("k", 10)` | `("k", 10)` | Có | Cả hai thành phần bằng nhau |
| `("k", 10)` | `("k", 11)` | Không | Giá trị khác |
| `("k", 10)` | `("z", 10)` | Không | Khóa khác |
| `(null, 10)` | `(null, 10)` | Có | Hai khóa cùng `null` |
| `("k", null)` | `("k", null)` | Có | Hai giá trị cùng `null` |

Lưu ý: bảng thể hiện **quy tắc equality**, còn việc tạo một entry chứa `null` phụ thuộc từng implementation. `Map.entry(null, 10)` không hợp lệ; một số lớp khác chấp nhận null.

Vì `equals` dùng cả hai thành phần, chỉ kiểm tra `getKey()` sẽ thiếu điều kiện. `==` so sánh **tham chiếu có trùng nhau không**, vì thế không thay được `equals`. Entry cần tuân thủ hợp đồng của `Object.equals` (phản xạ, đối xứng, bắc cầu, nhất quán khi trạng thái không đổi). Đặc biệt, entry do bạn tự viết phải so sánh tương thích với mọi implementation hợp lệ của `Map.Entry`, không chỉ với cùng lớp.

## 3. Hợp đồng `hashCode()`

Hash của một entry được Java quy định **chính xác**:

~~~java
(key == null ? 0 : key.hashCode())
        ^ (value == null ? 0 : value.hashCode())
~~~

Toán tử `^` là **XOR theo bit**, không phải phép lũy thừa. Biểu thức tương đương khi viết phương thức trong một lớp triển khai:

~~~java
@Override
public int hashCode() {
    return Objects.hashCode(getKey()) ^ Objects.hashCode(getValue());
}
~~~

Đoạn mã trên là **phương thức cần đặt trong lớp**, không chạy độc lập; `Objects` thuộc `java.util`. `Objects.hashCode(null)` trả về `0`.

Hệ quả quan trọng:

- Nếu `a.equals(b) == true` thì **bắt buộc** `a.hashCode() == b.hashCode()`.
- Hash bằng nhau **không** suy ra `equals` bằng nhau. Ví dụ `("A", "B")` và `("B", "A")` cùng hash vì `x ^ y == y ^ x`, nhưng khác khóa và khác giá trị khi xét đúng vị trí.
- Không thay XOR bằng `Objects.hash(key, value)`: hàm này ghép hash kiểu mảng, **không** theo công thức bắt buộc của `Map.Entry`.
- `Map.hashCode()` của **cả map** là tổng hash code của các entry trong `entrySet()`. Đừng nhầm với hash code của **một entry**.

Tính nhất quán giữa `equals` và `hashCode` rất cần thiết khi đưa `Map.Entry` vào `HashSet`, dùng làm khóa cho `HashMap` hoặc gọi `map.entrySet().contains(candidate)`.

## 4. Ví dụ chạy được bằng Java 17+

Tạo tệp **`MapEntryContractDemo.java`** chứa mã đầy đủ dưới đây:

~~~java
import java.util.AbstractMap;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class MapEntryContractDemo {
    // Triển khai một entry độc lập, không cho thay value.
    static final class ReadOnlyEntry<K, V> implements Map.Entry<K, V> {
        private final K key;
        private final V value;

        ReadOnlyEntry(K key, V value) {
            this.key = key;
            this.value = value;
        }

        @Override
        public K getKey() {
            return key;
        }

        @Override
        public V getValue() {
            return value;
        }

        @Override
        public V setValue(V newValue) {
            throw new UnsupportedOperationException("Entry is read-only");
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Map.Entry<?, ?> e
                    && Objects.equals(key, e.getKey())
                    && Objects.equals(value, e.getValue());
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(key) ^ Objects.hashCode(value);
        }
    }

    public static void main(String[] args) {
        Map.Entry<String, Integer> a = Map.entry("lan", 10);
        Map.Entry<String, Integer> b =
                new AbstractMap.SimpleEntry<>("lan", 10);
        Map.Entry<String, Integer> c = Map.entry("lan", 11);

        System.out.println("same mapping: " + a.equals(b));
        System.out.println("symmetry: " + b.equals(a));
        System.out.println("same hash: " + (a.hashCode() == b.hashCode()));
        System.out.println("different value: " + a.equals(c));

        Map.Entry<String, Integer> nullableA =
                new AbstractMap.SimpleImmutableEntry<>(null, 10);
        Map.Entry<String, Integer> nullableB =
                new AbstractMap.SimpleEntry<>(null, 10);
        System.out.println("null key: " + nullableA.equals(nullableB));
        System.out.println("null hash: "
                + (nullableA.hashCode() == nullableB.hashCode()));

        Map.Entry<String, Integer> custom = new ReadOnlyEntry<>("lan", 10);
        System.out.println("custom vs standard: " + custom.equals(a));
        System.out.println("standard vs custom: " + a.equals(custom));
        System.out.println("custom hash: "
                + (custom.hashCode() == a.hashCode()));

        Set<Map.Entry<String, Integer>> set = new HashSet<>();
        set.add(a);
        System.out.println("HashSet contains: " + set.contains(b));

        Map<String, Integer> map = new HashMap<>();
        map.put("lan", 10);
        System.out.println("entrySet contains: " + map.entrySet().contains(b));

        Map.Entry<String, String> ab = Map.entry("A", "B");
        Map.Entry<String, String> ba = Map.entry("B", "A");
        System.out.println("hash collision: "
                + (ab.hashCode() == ba.hashCode()));
        System.out.println("but not equals: " + ab.equals(ba));

        Map.Entry<String, Integer> snapshot =
                Map.Entry.copyOf(map.entrySet().iterator().next());
        map.put("lan", 20);
        System.out.println("snapshot unchanged: " + snapshot.getValue());
    }
}
~~~

Tại thư mục chứa tệp, chạy:

~~~bash
javac MapEntryContractDemo.java
java MapEntryContractDemo
~~~

Kết quả stdout:

~~~text
same mapping: true
symmetry: true
same hash: true
different value: false
null key: true
null hash: true
custom vs standard: true
standard vs custom: true
custom hash: true
HashSet contains: true
entrySet contains: true
hash collision: true
but not equals: false
snapshot unchanged: 10
~~~

**Phân tích kết quả:**

1. `a` tạo bởi `Map.entry`, `b` bởi `SimpleEntry`, `custom` bởi class tự viết. Ba entry này có cùng ánh xạ `("lan", 10)` nên đều bằng nhau và có cùng hash.
2. `c` có cùng khóa nhưng giá trị `11` nên `a.equals(c)` là `false`.
3. Hai entry có khóa `null` được tạo bằng implementation cho phép null, chứng minh `equals/hashCode` xử lý null an toàn.
4. `HashSet.contains(b)` tìm được entry `a` đã chèn; `map.entrySet().contains(b)` nhận ra cặp ánh xạ tương đương trong map.
5. `ab` và `ba` có hash trùng mà không bằng nhau, vì XOR có va chạm.
6. `Map.Entry.copyOf` tạo bản sao tách khỏi map; đổi giá trị trong `map` không làm đổi `snapshot`.

## 5. Cách tạo entry và vấn đề `null`

| Cách lấy entry | `setValue` | Cho phép khóa/giá trị `null` | Quan hệ với map |
| --- | --- | --- | --- |
| `Map.entry(k, v)` (Java 9+) | Không | Không | Độc lập |
| `new AbstractMap.SimpleEntry<>(k, v)` | Có | Có | Độc lập nếu tự tạo |
| `new AbstractMap.SimpleImmutableEntry<>(k, v)` | Không | Có | Độc lập nếu tự tạo |
| `Map.Entry.copyOf(e)` (Java 17+) | Không | Không | Bản sao độc lập |
| Entry từ iterator của `map.entrySet()` | Tùy implementation | Tùy map | Có liên hệ với map trong quá trình duyệt |

`Map.entry` ném `NullPointerException` khi khóa hoặc giá trị là null. `Map.Entry.copyOf(e)` cũng ném ngoại lệ này khi `e`, khóa hay giá trị của `e` là null. Khi cần sao chép một entry chứa null, có thể dùng `new AbstractMap.SimpleImmutableEntry<>(e)`.

**Không nên giữ một entry lấy qua iterator của `map.entrySet()` rồi giả định nó tiếp tục hoạt động sau khi quá trình duyệt kết thúc hoặc map đã đổi.** Theo API, liên hệ với map được bảo đảm trong khi duyệt; hành vi ngoài thời điểm đó, hoặc sau khi map bị chỉnh sửa theo cách không phải `setValue` của entry, không được xác định. Khi cần lưu cặp ánh xạ độc lập, hãy sao chép.

Một entry không cho `setValue` chỉ ngăn việc **thay tham chiếu value qua phương thức này**; object khóa/giá trị bên trong vẫn có thể là object mutable. Sao chép entry không phải sao chép sâu object.

## 6. Đừng làm thay đổi hash khi đang lưu trong `HashSet`

`SimpleEntry.setValue` có thể thay giá trị và làm đổi hash của entry. Nếu thêm entry vào `HashSet` rồi thay đổi khóa/giá trị hoặc trạng thái của object mà `equals/hashCode` dựa vào, việc tìm bằng `contains` hoặc xóa bằng `remove` có thể thất bại. Giữ các thành phần quyết định equality/hash **ổn định trong thời gian entry là phần tử của cấu trúc hash**.

`setValue` là thao tác **tùy chọn**: `Map.entry` và `SimpleImmutableEntry` không cho sửa; entry từ map có thể cho phép hoặc không tùy map/implementation. Không được mặc định rằng mọi entry đều ghi ngược về map.

## 7. Những lỗi thường gặp khi tự triển khai `Map.Entry`

- **Chỉ so sánh khóa** trong `equals`, bỏ qua giá trị.
- **Ép cùng runtime class** trước khi so sánh; điều này phá tương thích giữa `Map.entry`, `SimpleEntry`, entry từ `HashMap` và các implementation khác.
- **Dùng `Objects.hash(key, value)`** thay XOR theo định nghĩa chính thức của `Map.Entry.hashCode`.
- **Gọi `key.equals(...)` khi khóa có thể null**, gây `NullPointerException`; dùng `Objects.equals`.
- **Cho rằng hai entry trùng hash thì phải bằng nhau**, bỏ qua va chạm.
- **Giữ entry có dữ liệu mutable trong `HashSet`** rồi thay đổi dữ liệu ảnh hưởng đến hash.
- **Dùng `record` implements `Map.Entry` với `equals/hashCode` mặc định của record**. `record` mặc định xét kiểu record và dùng hợp đồng riêng; nó không tự đáp ứng phép so sánh chéo giữa các implementation hoặc công thức XOR của `Map.Entry`. Nếu dùng record, phải override hai phương thức này và triển khai `getKey`, `getValue`, `setValue`.

Checklist thực hành: một implementation đúng phải so sánh chéo được với `Map.entry`/`SimpleEntry` theo cả hai chiều; hỗ trợ đúng ngữ nghĩa null; có `hashCode` đúng XOR; từ chối `setValue` bằng `UnsupportedOperationException` nếu là entry không sửa được.

## 8. Tự kiểm tra

1. `("id", 3)` với `("id", 4)` có bằng nhau không? **Không**, vì giá trị khác.
2. Hai entry khác lớp nhưng cùng ánh xạ có bằng nhau không? **Có**, nếu đều theo hợp đồng `Map.Entry`.
3. Hai entry có cùng hash có chắc bằng nhau không? **Không**, ví dụ `("A", "B")` và `("B", "A")`.
4. Hash của entry `(null, 7)` là gì? **`0 ^ Integer.hashCode(7)`**, tức `7`, nếu implementation cho phép khóa null.
5. Có dùng `Map.entry(null, 7)` làm ví dụ null được không? **Không**: factory này từ chối null; có thể dùng `SimpleImmutableEntry`.

**Nguồn API chính thức:** [Java SE 25 — `Map.Entry`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.Entry.html) và [Java SE 25 — `Map`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html).