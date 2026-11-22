# Giới hạn thay giá trị qua `Map.Entry` khi dùng `Map.copyOf` (Java 10+)

## 1. Mục tiêu và quy tắc cốt lõi

`Map.copyOf(Map<? extends K, ? extends V>)` được bổ sung trong **Java 10** để tạo một `Map` **không cho sửa các ánh xạ khóa–giá trị** (*unmodifiable map*). Hạn chế này không chỉ áp dụng cho `map.put(...)`, `map.remove(...)` hay `map.replace(...)`, mà còn áp dụng khi cố **thay giá trị qua một `Map.Entry` lấy từ `entrySet()`**.

Điểm cần ghi nhớ:

~~~java
Map<String, Integer> source = new HashMap<>();
source.put("Java", 10);

Map<String, Integer> frozen = Map.copyOf(source);
Map.Entry<String, Integer> entry = frozen.entrySet().iterator().next();

System.out.println(entry.getKey());   // Java
System.out.println(entry.getValue()); // 10

// entry.setValue(99); // Biên dịch được, nhưng khi chạy:
// UnsupportedOperationException.
~~~

Đoạn mã là minh họa đặt trong phương thức, cần import `java.util.Map` và `java.util.HashMap`. Tập chỉ có một entry để kết quả không phụ thuộc thứ tự duyệt. Chương trình Java 17+ độc lập nằm ở mục 8.

**Vì sao vẫn biên dịch?** `Map.Entry<K,V>` định nghĩa phương thức `V setValue(V newValue)`, nhưng đây là **thao tác tùy chọn**. Kiểu tĩnh `Map.Entry<String,Integer>` cho phép gọi phương thức đó; implementation của entry trả về từ `Map.copyOf` từ chối việc thay thế mapping khi thực thi bằng `UnsupportedOperationException`.

Sau bài này, bạn sẽ:
- Phân biệt **`getKey()`/`getValue()` để đọc** với **`setValue()` để thay ánh xạ**.
- Hiểu vì sao `Map.copyOf` chặn cả thay đổi **đi vòng qua `entrySet()`**.
- Đối chiếu với `Map.Entry` của một `HashMap` có thể sửa, và với `Collections.unmodifiableMap(...)`.
- Phân biệt thay **tham chiếu value trong map** với sửa **trạng thái bên trong một object value mutable**.
- Biết cách tạo bản sao mutable khi cần cập nhật và cách công bố dữ liệu an toàn.

Các quy tắc vẫn áp dụng trong Java hiện đại. Ví dụ thực hành sử dụng JDK 17+ và phân biệt rõ tính năng riêng của JDK 17.

## 2. `Map.Entry` biểu diễn gì?

Mỗi entry biểu diễn **một cặp ánh xạ khóa–giá trị** trong `Map<K,V>`:

~~~java
Map<String, Integer> scores = new HashMap<>();
scores.put("An", 10);

for (Map.Entry<String, Integer> entry : scores.entrySet()) {
    String key = entry.getKey();
    Integer value = entry.getValue();

    System.out.println(key + " = " + value); // An = 10
}
~~~

Trong `Map.Entry<K,V>`, những phương thức quan trọng là:

| Phương thức | Mục đích | Với entry của `Map.copyOf` |
| --- | --- | --- |
| `K getKey()` | Đọc khóa của entry | Được phép |
| `V getValue()` | Đọc value đang được entry biểu diễn | Được phép |
| `V setValue(V newValue)` | Thử thay value ứng với khóa; nếu hỗ trợ thì trả về value cũ | **Không hỗ trợ; ném `UnsupportedOperationException`** |
| `equals` / `hashCode` | So sánh entry theo hợp đồng của `Map.Entry` | Dùng được; không thay mapping |

Một `Map.Entry` **không mặc nhiên cho phép sửa** chỉ vì interface có phương thức `setValue`. Một entry có thể:
1. Kết nối với một `Map` mutable và hỗ trợ ghi lại value;
2. Kết nối với unmodifiable map, không cho ghi;
3. Là một đối tượng key–value độc lập, không liên kết với map nào, có thể mutable hoặc unmodifiable tùy cách tạo.

Khả năng sửa không phụ thuộc riêng vào generic `K,V`; nó phụ thuộc **hợp đồng và implementation cụ thể**. Cũng không nên coi `Map.Entry` như “địa chỉ một ô trong map” có thể tùy ý thao tác ngoài vòng đời iterator: với entry lấy từ view của một map mutable, API chỉ bảo đảm liên hệ với backing map trong phạm vi duyệt và theo các điều kiện được tài liệu quy định.

## 3. `Map.copyOf`: không thể sửa ánh xạ bằng đường vòng qua `entrySet()`

Tạo một map không cho sửa:

~~~java
Map<String, Integer> snapshot = Map.copyOf(source);
~~~

`snapshot` không cho thêm, xóa, thay value hoặc đổi cấu trúc mapping qua API của nó. Do đó những thao tác sau không được hỗ trợ:

~~~java
// snapshot.put("An", 20);       // UnsupportedOperationException
// snapshot.remove("An");        // UnsupportedOperationException
// snapshot.replace("An", 20);   // UnsupportedOperationException
// snapshot.clear();             // UnsupportedOperationException
~~~

Dấu comment trong các ví dụ này nhằm giữ mã hợp lệ khi ghép vào chương trình; nếu bỏ comment, lệnh có thể **biên dịch**, nhưng phương thức thay đổi dữ liệu sẽ bị từ chối khi chạy.

Bất biến tương tự cần được giữ khi duyệt `entrySet()`:

~~~java
for (var entry : snapshot.entrySet()) {
    System.out.println(entry.getKey() + "=" + entry.getValue()); // Đọc hợp lệ
    // entry.setValue(99); // Ném UnsupportedOperationException
}
~~~

Vì sao? Nếu `entry.setValue(99)` được phép cập nhật ánh xạ trong `snapshot`, người dùng có thể phá vỡ hợp đồng unmodifiable map **mặc dù không gọi `snapshot.put`**. Vì thế, các entry do `entrySet()` của map này cung cấp không cho phép thay value qua `setValue`.

Còn các đường chỉnh sửa khác qua view?
- `snapshot.entrySet()` không hỗ trợ loại bỏ entry để gián tiếp xóa mapping.
- `snapshot.keySet()` không thể được dùng để xóa khóa trong snapshot.
- `snapshot.values()` không thể được dùng để xóa value nhằm sửa ánh xạ trong snapshot.
- Các phương thức mutator của map như `put`, `putAll`, `replace`, `compute`, `merge` không biến một map từ `Map.copyOf` thành có thể sửa.

**Phân biệt biên dịch và runtime:** Java vẫn cho phép viết `entry.setValue(v)` vì kiểu tĩnh là `Map.Entry<K,V>`. Lỗi runtime là do operation tùy chọn không được implementation hỗ trợ, không phải do `setValue` biến mất khỏi interface.

## 4. Đối chiếu với `Map.Entry` của `HashMap` mutable

Với `HashMap` thông thường, entry lấy trong quá trình duyệt `entrySet()` **hỗ trợ `setValue`**, và thay đổi đó **ghi ngược về map nguồn**:

~~~java
Map<String, Integer> mutable = new HashMap<>();
mutable.put("An", 10);

for (var entry : mutable.entrySet()) {
    int oldValue = entry.setValue(15);
    System.out.println("old = " + oldValue); // old = 10
}
System.out.println(mutable.get("An")); // 15
~~~

Trong vòng lặp:
- `entry.getKey()` là `"An"`.
- `entry.getValue()` ban đầu là `10`.
- `entry.setValue(15)` được `HashMap` hỗ trợ, trả về value cũ là `10`.
- `mutable.get("An")` sau đó là `15`.

Nhưng nếu cùng logic này được chạy trên kết quả `Map.copyOf(mutable)`, thì `entry.setValue(15)` **không được hỗ trợ**.

### Không giữ entry của map mutable rồi sử dụng tùy tiện sau khi map đổi

Tài liệu `Map.Entry` quy định kết nối giữa entry lấy từ `entrySet()` và map nền chỉ đáng tin trong phạm vi iteration; nếu map đã bị sửa sau khi lấy entry (ngoại trừ chính `setValue` theo hợp đồng), hành vi liên quan đến entry ấy có thể không xác định theo đặc tả.

Vì vậy hãy ưu tiên:

~~~java
for (var entry : mutable.entrySet()) {
    if (entry.getKey().equals("An")) {
        entry.setValue(15); // Khi implementation cho phép
    }
}
~~~

Tránh lưu entry vào cache lâu dài rồi mong nó cập nhật đồng bộ theo mọi thay đổi của map. Nếu cần lưu một cặp khóa–giá trị độc lập, xem `Map.entry(...)` hoặc `Map.Entry.copyOf(...)` (lưu ý mốc phiên bản ở mục 10).

## 5. `Map.copyOf` và `Collections.unmodifiableMap` có giống nhau không?

Hai cách đều chặn cập nhật thông qua map hoặc entry mà chúng trả về, nhưng **quan hệ với dữ liệu nguồn khác nhau**.

~~~java
Map<String, Integer> source = new HashMap<>();
source.put("An", 10);

Map<String, Integer> snapshot = Map.copyOf(source);
Map<String, Integer> view = Collections.unmodifiableMap(source);

source.put("An", 20);

System.out.println(snapshot.get("An")); // 10
System.out.println(view.get("An"));     // 20
~~~

*Giả sử import `Map`, `HashMap`, `Collections`. Đây là đoạn minh họa trong phương thức.*

- **`Map.copyOf(source)`**: với `source` là `HashMap` mutable thông thường, trả map unmodifiable chứa các ánh xạ lúc gọi. `source.put("An",20)` sau đó không cập nhật mapping trong snapshot.
- **`Collections.unmodifiableMap(source)`**: tạo một **view** bọc map nguồn. Code không được thay đổi qua view, nhưng khi nguồn đổi, việc đọc qua view phản ánh mapping mới.
- **Entry của cả hai kết quả**: không được dùng `entry.setValue(...)` để thay mapping qua các kết quả unmodifiable.
- **Source**: vẫn có thể thay đổi qua biến `source` nếu implementation gốc hỗ trợ.

Bảng nhanh:

| Đối tượng | `put("An",30)` qua đối tượng đó | `entry.setValue(30)` qua `entrySet` của nó | `source.put(...)` có phản ánh ở đối tượng đó? |
| --- | --- | --- | --- |
| `source` là `HashMap` mutable | Có | Có, khi dùng entry trong iteration hợp lệ | Có |
| `Map.copyOf(source)` | Không | Không | Không, với nguồn mutable thông thường |
| `Collections.unmodifiableMap(source)` | Không | Không | Có, vì là view |
| `new HashMap<>(snapshot)` | Có | Có, với entry của bản sao `HashMap` | Không |

Bất kể map có cập nhật mapping hay không, một **object value có trạng thái mutable** vẫn có thể bị thay đổi; mục 7 giải thích sự khác nhau.

## 6. Nếu thực sự cần thay value, làm cách nào?

### 6.1. Tạo bản sao mutable

Thay vì tìm đường vượt qua `Map.copyOf`, hãy tạo một map mới có thể sửa từ snapshot:

~~~java
Map<String, Integer> frozen = Map.of("An", 10);
Map<String, Integer> editable = new HashMap<>(frozen);

editable.put("An", 20);   // Được phép
System.out.println(frozen.get("An"));   // 10
System.out.println(editable.get("An")); // 20
~~~

Nếu muốn dùng `entry.setValue`, duyệt **`editable.entrySet()`**:

~~~java
for (var entry : editable.entrySet()) {
    if (entry.getKey().equals("An")) {
        entry.setValue(30);
    }
}
System.out.println(editable.get("An")); // 30
System.out.println(frozen.get("An"));   // 10
~~~

Hai câu lệnh tạo map có thể sửa và chỉnh entry **không ảnh hưởng snapshot cũ**. Đây là hai đoạn minh họa có thể đặt liên tiếp trong một phương thức, với các import tương ứng.

Khi nghiệp vụ cần trả một map mới sau khi chỉnh sửa:

~~~java
Map<String, Integer> modified = new HashMap<>(frozen);
modified.put("An", 99);
Map<String, Integer> newSnapshot = Map.copyOf(modified);
~~~

`newSnapshot` là bản chụp ánh xạ mới và không cho sửa qua API map. `frozen` vẫn chứa ánh xạ cũ. Lưu ý `new HashMap<>(frozen)` tạo **bản sao nông** của các đối tượng khóa và value; nếu value mutable, các map có thể dùng chung object ấy.

### 6.2. Dùng `replaceAll` / `compute` ở đúng nơi

Nếu cần tính value mới cho nhiều khóa, hãy thực hiện trên map mutable trước khi tạo snapshot:

~~~java
var editable = new HashMap<String, Integer>();
editable.put("An", 10);
editable.put("Binh", 20);

editable.replaceAll((key, value) -> value + 5);
Map<String, Integer> result = Map.copyOf(editable);

System.out.println(result.get("An")); // 15
System.out.println(result.get("Binh")); // 25
~~~

Không gọi `snapshot.replaceAll` hoặc `snapshot.compute` với kỳ vọng chúng có quyền sửa vì đang dùng callback. Các lời gọi này vẫn nhằm cập nhật mapping và không được phép trên map unmodifiable.

### 6.3. Không ép kiểu để đoán lớp implementation

~~~java
// HashMap<String, Integer> mutable = (HashMap<String, Integer>) frozen;
~~~

Không được giả định rằng một map trả về từ `Map.copyOf` là `HashMap` hoặc có thể bị “mở khóa” nhờ cast. Cast sai có thể ném `ClassCastException` và cũng không thay đổi hợp đồng unmodifiable.

## 7. `setValue` bị cấm nhưng object value vẫn có thể mutable

Đây là khác biệt quan trọng giữa **thay tham chiếu value của ánh xạ** và **sửa trạng thái của object value**.

Giả sử `Counter` có phương thức `increase()`:

~~~java
final class Counter {
    private int count;

    Counter(int count) {
        this.count = count;
    }

    void increase() {
        count++;
    }

    int get() {
        return count;
    }
}
~~~

*Đây là kiểu minh họa. Chương trình hoàn chỉnh ở mục 8 có định nghĩa tương ứng.*

~~~java
var counter = new Counter(5);
Map<String, Counter> source = new HashMap<>();
source.put("visits", counter);

Map<String, Counter> frozen = Map.copyOf(source);
counter.increase();

System.out.println(source.get("visits").get()); // 6
System.out.println(frozen.get("visits").get()); // 6
~~~

Ở đây `source.get("visits")` và `frozen.get("visits")` đang trỏ tới **cùng object `Counter`**. `Map.copyOf` sao chép ánh xạ theo tham chiếu nhưng **không deep-copy từng value**.

Vì thế, đoạn sau cũng có thể hợp lệ:

~~~java
frozen.get("visits").increase(); // Sửa Counter, không sửa mapping
~~~

Nhưng các cách thay thế *toàn bộ value* lại bị cấm:

~~~java
// frozen.put("visits", new Counter(100)); // UnsupportedOperationException

// for (var e : frozen.entrySet()) {
//     e.setValue(new Counter(100));       // UnsupportedOperationException
// }
~~~

Sau khi snapshot được tạo, `source.put("visits", new Counter(100))` thay tham chiếu value của **nguồn**; snapshot vẫn trỏ đến object `Counter` cũ. Hành vi này khác với việc sửa trực tiếp state của `Counter` cũ được chia sẻ giữa hai map.

**Lưu ý với key mutable:** Sửa các field của key mà `equals()` hoặc `hashCode()` phụ thuộc vào có thể làm việc tra cứu không còn đáng tin cậy trong các map sử dụng hashing. Một unmodifiable map không tự làm key hoặc value trở thành bất biến sâu; dùng key có equality/hashCode ổn định.

Nếu API yêu cầu dữ liệu không thay đổi từ bên ngoài, đừng chỉ dựa vào `Map.copyOf`; hãy chọn các value object immutable, hoặc làm **defensive/deep copy** của phần trạng thái mutable cần tách trước khi công bố map.

## 8. Ví dụ Java 17+ hoàn chỉnh: kiểm chứng các giới hạn

Tạo tệp **MapCopyOfEntryDemo.java**:

~~~java
import java.util.Collections;
import java.util.HashMap;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;

public class MapCopyOfEntryDemo {
    static final class Counter {
        private int count;

        Counter(int count) {
            this.count = count;
        }

        void add(int amount) {
            count += amount;
        }

        int get() {
            return count;
        }
    }

    public static void main(String[] args) {
        Map<String, Integer> source = new LinkedHashMap<>();
        source.put("basic", 10);
        source.put("pro", 20);

        Map<String, Integer> snapshot = Map.copyOf(source);
        Map<String, Integer> view = Collections.unmodifiableMap(source);

        // Entry của snapshot chỉ cho đọc, không cho thay value.
        for (var entry : snapshot.entrySet()) {
            if (entry.getKey().equals("basic")) {
                System.out.println("snapshot entry = "
                        + entry.getKey() + ":" + entry.getValue());
                try {
                    entry.setValue(99);
                } catch (UnsupportedOperationException ex) {
                    System.out.println("snapshot entry.setValue = blocked");
                }
            }
        }
        System.out.println("snapshot basic = " + snapshot.get("basic"));

        // Source thay mapping; snapshot không đổi, view phản ánh nguồn.
        source.put("basic", 11);
        source.put("new", 30);
        source.remove("pro");
        System.out.println("source basic = " + source.get("basic"));
        System.out.println("snapshot basic after source update = "
                + snapshot.get("basic"));
        System.out.println("snapshot retains pro = "
                + snapshot.containsKey("pro"));
        System.out.println("snapshot has new = "
                + snapshot.containsKey("new"));

        // Entry của mutable LinkedHashMap hỗ trợ setValue.
        for (var entry : source.entrySet()) {
            if (entry.getKey().equals("basic")) {
                int previous = entry.setValue(12);
                System.out.println("source entry.setValue previous = " + previous);
            }
        }
        System.out.println("source basic after entry update = "
                + source.get("basic"));
        System.out.println("snapshot basic after entry update = "
                + snapshot.get("basic"));

        // View unmodifiable cũng phải chặn đường sửa qua entry.
        for (var entry : view.entrySet()) {
            if (entry.getKey().equals("basic")) {
                try {
                    entry.setValue(100);
                } catch (UnsupportedOperationException ex) {
                    System.out.println("view entry.setValue = blocked");
                }
            }
        }

        // Không xóa được mapping qua iterator của snapshot.entrySet().
        Iterator<Map.Entry<String, Integer>> iterator =
                snapshot.entrySet().iterator();
        iterator.next();
        try {
            iterator.remove();
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot iterator.remove = blocked");
        }

        // Tạo bản sao mutable và sửa qua Entry của bản sao đó.
        Map<String, Integer> editable = new HashMap<>(snapshot);
        for (var entry : editable.entrySet()) {
            if (entry.getKey().equals("basic")) {
                int previous = entry.setValue(99);
                System.out.println("editable entry.setValue previous = " + previous);
            }
        }
        System.out.println("editable basic = " + editable.get("basic"));
        System.out.println("snapshot basic after editable update = "
                + snapshot.get("basic"));

        // Map unmodifiable vẫn chia sẻ một object value mutable.
        var counter = new Counter(5);
        Map<String, Counter> counterSource = new HashMap<>();
        counterSource.put("visits", counter);
        Map<String, Counter> counterSnapshot = Map.copyOf(counterSource);

        System.out.println("same counter value reference = "
                + (counterSource.get("visits")
                    == counterSnapshot.get("visits")));

        counterSnapshot.get("visits").add(2);
        System.out.println("counter source = "
                + counterSource.get("visits").get());
        System.out.println("counter snapshot = "
                + counterSnapshot.get("visits").get());

        for (var entry : counterSnapshot.entrySet()) {
            try {
                entry.setValue(new Counter(100));
            } catch (UnsupportedOperationException ex) {
                System.out.println("counter entry.setValue = blocked");
            }
        }

        counterSource.put("visits", new Counter(100));
        System.out.println("counter source after replacement = "
                + counterSource.get("visits").get());
        System.out.println("counter snapshot after replacement = "
                + counterSnapshot.get("visits").get());

        // JDK 17+: Map.Entry.copyOf tạo entry độc lập, không liên kết nguồn.
        Map<String, Integer> one = new HashMap<>();
        one.put("score", 3);
        Map.Entry<String, Integer> independent =
                Map.Entry.copyOf(one.entrySet().iterator().next());
        one.put("score", 4);
        System.out.println("independent entry value = "
                + independent.getValue());
        System.out.println("source entry value = " + one.get("score"));
        try {
            independent.setValue(5);
        } catch (UnsupportedOperationException ex) {
            System.out.println("independent entry.setValue = blocked");
        }
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp bằng **JDK 17 trở lên**:

~~~bash
javac MapCopyOfEntryDemo.java
java MapCopyOfEntryDemo
~~~

**Đầu ra chính xác:**

~~~text
snapshot entry = basic:10
snapshot entry.setValue = blocked
snapshot basic = 10
source basic = 11
snapshot basic after source update = 10
snapshot retains pro = true
snapshot has new = false
source entry.setValue previous = 11
source basic after entry update = 12
snapshot basic after entry update = 10
view entry.setValue = blocked
snapshot iterator.remove = blocked
editable entry.setValue previous = 10
editable basic = 99
snapshot basic after editable update = 10
same counter value reference = true
counter source = 7
counter snapshot = 7
counter entry.setValue = blocked
counter source after replacement = 100
counter snapshot after replacement = 7
independent entry value = 3
source entry value = 4
independent entry.setValue = blocked
~~~

### Tại sao kết quả đáng tin?

1. `snapshot.entrySet()` có thể duyệt theo thứ tự bất kỳ; chương trình **tìm entry có khóa `basic`** trước khi in, không dự đoán thứ tự của `Map.copyOf`.
2. `snapshot.entry.setValue(99)` bị chặn. Giá trị của `snapshot.get("basic")` vẫn là `10`.
3. `source.put/remove` và `entry.setValue` của `LinkedHashMap` chỉ ảnh hưởng nguồn; snapshot vẫn giữ các mapping ban đầu.
4. View `Collections.unmodifiableMap(source)` chặn ghi qua entry dù bản thân nguồn là mutable; quyền ghi vẫn có thể thực hiện qua biến `source`.
5. Iterator của `snapshot.entrySet()` không hỗ trợ `remove()`, bảo vệ mapping khỏi đường sửa gián tiếp.
6. `editable` là `HashMap` mới, nên entry của `editable` cho phép `setValue` trong vòng lặp, trong khi `snapshot` không đổi.
7. `Counter` là object mutable được chia sẻ: gọi `add(2)` thông qua `counterSnapshot.get` sửa **state object**, không sửa mapping. Do đó cả hai map cùng thấy số `7`.
8. `counterSource.put(..., new Counter(100))` đổi **tham chiếu value ở nguồn**, không đổi tham chiếu mà snapshot đã giữ.
9. `Map.Entry.copyOf` ở cuối là một tính năng **Java 17**, không phải tính năng giới thiệu trong Java 10. Nó tạo entry không liên kết với map nguồn; sửa nguồn từ `3` thành `4` không sửa `independent`, và `setValue` trên entry độc lập cũng bị chặn.

Không dùng thư viện bên ngoài; stdout không phụ thuộc thứ tự duyệt `HashMap` hoặc `Map.copyOf`.

## 9. `Map.entry`, `Map.Entry.copyOf`, `SimpleEntry`: đừng nhầm với entry của `Map.copyOf`

Những API này đều tạo hoặc biểu diễn cặp khóa–giá trị nhưng có hợp đồng khác nhau:

| API/cách tạo | Nguồn gốc | `setValue` được phép? | Có ghi ngược vào map đang dùng? |
| --- | --- | --- | --- |
| `snapshot.entrySet()` với `snapshot = Map.copyOf(source)` | Entry của map unmodifiable | Không | Không |
| `mutable.entrySet()` với `mutable` là `HashMap` | Entry trong view của map mutable | Có, trong điều kiện hợp lệ | Có |
| `Collections.unmodifiableMap(source).entrySet()` | Entry của unmodifiable view | Không | Không qua view |
| `Map.entry(key, value)` (Java 9+) | Entry độc lập, unmodifiable | Không | Không |
| `Map.Entry.copyOf(entry)` (Java 17+) | Bản sao entry độc lập, unmodifiable | Không | Không |
| `new AbstractMap.SimpleEntry<>(key,value)` | Entry độc lập, mutable | Có | Không, trừ khi code tự sử dụng kết quả để cập nhật map |
| `new AbstractMap.SimpleImmutableEntry<>(key,value)` | Entry độc lập, unmodifiable | Không | Không |

**Quan trọng:** `AbstractMap.SimpleEntry` dù cho phép `setValue`, vẫn chỉ thay **đối tượng entry độc lập**; nó không làm thay đổi một `HashMap` ngẫu nhiên có cùng cặp khóa–giá trị. Còn entry lấy từ `mutable.entrySet()` trong lúc duyệt, nếu implementation hỗ trợ, có thể **write-through** về map gốc.

### Ví dụ nhỏ: `Map.entry` so với `SimpleEntry`

~~~java
Map.Entry<String, Integer> fixed = Map.entry("An", 10);
// fixed.setValue(20); // UnsupportedOperationException

var local = new AbstractMap.SimpleEntry<>("An", 10);
int old = local.setValue(20); // Trả về 10
System.out.println(old);               // 10
System.out.println(local.getValue());  // 20
~~~

Đoạn minh họa cần import `java.util.Map`, `java.util.AbstractMap`. `local` không phải entry được lấy từ một map cụ thể; cập nhật `local` không tự cập nhật các map khác.

## 10. Điều gì khác giữa khóa, value và mapping?

Với một `Map<String, Counter>`, hãy tách rõ ba lớp dữ liệu:

~~~text
Map:
  "visits"  ───────► Counter(count=5)
      |                    |
    khóa               object value
      \____________________/
             mapping
~~~

- **Thay mapping:** gán `"visits"` tới một `Counter` khác. Trên map mutable, dùng `put`, `replace`, hoặc `entry.setValue` khi được hỗ trợ. Trên `Map.copyOf`, việc này bị cấm.
- **Sửa object value hiện có:** gọi `get("visits").add(2)` để đổi `count` trên cùng object. Có thể hợp lệ dù map unmodifiable, nếu object value cho phép sửa và người gọi có quyền truy cập.
- **Sửa key mutable:** đặc biệt nguy hiểm nếu ảnh hưởng `equals`/`hashCode`. Map unmodifiable cũng không tự bảo vệ key object.

Sự bất biến của **mối quan hệ khóa–value** không đồng nghĩa với tính bất biến sâu của **những object được tham chiếu**. Vì vậy không nên tuyên bố `Map.copyOf` là *deep immutable* nếu value là các entity có setter.

Nếu cần snapshot giá trị thực sự độc lập, dùng immutable value object hoặc defensive copy. Ví dụ với `Counter` có phương thức `get()`:

~~~java
Map<String, Integer> numericSnapshot = new HashMap<>();
sourceCounters.forEach((key, counter) ->
        numericSnapshot.put(key, counter.get()));

Map<String, Integer> published = Map.copyOf(numericSnapshot);
~~~

Đây là **đoạn minh họa** giả sử `sourceCounters` có kiểu `Map<String, Counter>`, và các khóa là `String`. Giá trị `Integer` là bất biến, nên thay đổi state `Counter` gốc sau khi snapshot được tạo không tự đổi các số đã công bố. Nếu nguồn đang được thay đổi đồng thời, cần cơ chế đồng bộ hoặc snapshot nhất quán riêng; `Map.copyOf` không phải giao dịch thread-safe của toàn bộ object graph.

## 11. Những sai lầm thường gặp

**Sai lầm 1 — “`Map.Entry` luôn có `setValue`, vậy map không cho sửa vẫn sửa được qua entry.”**  
Không. `setValue` là thao tác **tùy chọn**. Với entry của `Map.copyOf`, nó bị chặn bằng `UnsupportedOperationException`.

**Sai lầm 2 — “`snapshot.put` bị cấm nhưng `snapshot.entrySet().iterator().next().setValue` sẽ thành công.”**  
Không. Mọi đường cập nhật mapping qua API được trả về phải tuân theo hợp đồng unmodifiable của snapshot.

**Sai lầm 3 — “`Collections.unmodifiableMap(source)` là bản sao snapshot.”**  
Không. Đó là view của nguồn; map nguồn đổi thì kết quả view có thể phản ánh các mapping mới. Tuy nhiên entry trong view vẫn không được dùng để ghi ngược qua view.

**Sai lầm 4 — “`Map.copyOf` luôn sao chép sâu value.”**  
Không. Nó lưu tham chiếu tới các object key/value đã có; nếu value mutable, thay đổi state có thể được nhìn thấy qua snapshot.

**Sai lầm 5 — “`new HashMap<>(snapshot)` làm value mutable trở nên độc lập.”**  
Không. Nó tạo cấu trúc map mới nhưng có thể chia sẻ cùng object value. Nếu cần tách state phải copy phần tử mutable, không chỉ copy map.

**Sai lầm 6 — “`Map.Entry.copyOf` là tính năng Java 10 như `Map.copyOf`.”**  
Không. `Map.Entry.copyOf` có từ **Java 17**. Khi viết code mục tiêu Java 10, không dùng API này; có thể dùng `Map.entry(k,v)` để tạo một entry unmodifiable độc lập (Java 9+) nếu phù hợp.

**Sai lầm 7 — “`Map.copyOf` cho phép key hoặc value `null` như `HashMap`.”**  
Không. `Map.copyOf` từ chối `null` key/value, ném `NullPointerException`. Cần kiểm tra dữ liệu đầu vào và chọn cách biểu diễn trạng thái thiếu.

**Sai lầm 8 — “Có thể dựa vào thứ tự entries trong `snapshot.entrySet()`.”**  
Không. `Map.copyOf` không cam kết thứ tự duyệt. Nếu ví dụ hoặc thuật toán cần thứ tự, nên truy cập theo khóa hoặc sắp xếp thông qua một cấu trúc có hợp đồng thứ tự phù hợp.

**Sai lầm 9 — “Map unmodifiable đảm bảo thread safety cho mọi value mutable.”**  
Không. Unmodifiable mapping và an toàn khi nhiều thread cùng truy cập/ghi các object value là những tính chất khác nhau. Hãy dùng thiết kế dữ liệu immutable hoặc cơ chế đồng bộ phù hợp với yêu cầu.

## 12. Câu hỏi tự kiểm tra

**1. Cho `Map<String,Integer> frozen = Map.copyOf(source);`. `frozen.entrySet().iterator().next().setValue(99)` có biên dịch được không? Có chạy thành công không?**

Có thể **biên dịch**, vì `Map.Entry` khai báo `setValue`. Nhưng entry trả về từ map unmodifiable **không hỗ trợ** thay value; khi gọi sẽ ném `UnsupportedOperationException`.

**2. Vì sao `HashMap.entrySet()` có thể cho dùng `setValue` nhưng `Map.copyOf(...).entrySet()` không?**

Khả năng ghi qua `setValue` phụ thuộc implementation/backing map. Entry của `HashMap` mutable hỗ trợ write-through trong iteration hợp lệ; entry của `Map.copyOf` phải bảo toàn hợp đồng map không cho sửa.

**3. Nếu sửa `source.put("An",20)` sau khi gọi `Map.copyOf(source)` với nguồn `HashMap` mutable thì snapshot có đổi thành `20` không?**

Không. Snapshot giữ mapping tại thời điểm tạo, không phải view theo dõi những thay đổi sau đó ở nguồn.

**4. Nếu dùng `Collections.unmodifiableMap(source)` thì có thể sửa value qua `view.entrySet()` không?**

Không. Unmodifiable view chặn thay đổi qua entry, nhưng người giữ nguồn vẫn có thể gọi `source.put(...)`, và view sẽ thấy mapping mới.

**5. Vì sao `frozen.get("visits").add(2)` có thể hợp lệ dù `entry.setValue(new Counter(...))` không hợp lệ?**

Lệnh đầu sửa **trạng thái object `Counter`** được tham chiếu, không thay ánh xạ trong map. Lệnh sau cố thay object value được gắn với khóa, vi phạm hợp đồng unmodifiable.

**6. Làm sao cho phép sửa dữ liệu mà không thay đổi snapshot cũ?**

Tạo một map mutable mới, chẳng hạn `new HashMap<>(snapshot)`, chỉnh các mapping của map mới, sau đó có thể gọi `Map.copyOf(newMap)` để công bố snapshot mới. Nếu object value mutable cần độc lập, phải sao chép sâu những value đó.

**7. `Map.entry(k,v)`, `Map.Entry.copyOf(e)`, `new AbstractMap.SimpleEntry<>(k,v)` khác nhau gì?**

Hai cách đầu tạo entry độc lập **unmodifiable** (`Map.Entry.copyOf` cần Java 17+). `SimpleEntry` tạo entry độc lập **mutable**. Chúng không tự ghi ngược vào một map chỉ vì cặp key–value giống nhau.

**8. Vì sao không nên giữ một entry của `HashMap.entrySet()` lâu sau khi sửa map gốc?**

Hợp đồng `Map.Entry` chỉ bảo đảm kết nối với backing map trong phạm vi iteration và có các giới hạn khi map đã được sửa ngoài `setValue`. Không nên coi entry đó như một handle bền vững cho map.

## 13. Ghi nhớ cuối bài

1. **`Map.copyOf` (Java 10+) tạo map unmodifiable**, không thể thay mapping qua `put`, `replace` **hoặc `Map.Entry.setValue`**.
2. **`Map.Entry.setValue` là thao tác tùy chọn**: có ở interface không đồng nghĩa mọi entry đều hỗ trợ.
3. Entry từ `HashMap.entrySet()` mutable có thể write-through trong quá trình duyệt hợp lệ; entry từ `Map.copyOf` không thể.
4. **`Collections.unmodifiableMap` là view**, cũng chặn `setValue` qua entry nhưng phản ánh thay đổi thực hiện qua map nguồn.
5. **Unmodifiable mapping không đồng nghĩa immutable value**: state của object value mutable được chia sẻ vẫn có thể thay đổi.
6. Khi cần chỉnh sửa, **tạo bản sao map mutable**; khi cần tách biệt trạng thái hoặc công bố dữ liệu an toàn, dùng defensive copy hoặc immutable value objects.

**Tài liệu tham khảo còn áp dụng:**
- [Java SE 17 — `Map.copyOf(Map)` và Unmodifiable Maps](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)).
- [Java SE 17 — `Map.Entry.setValue(V)` và `Map.Entry.copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.Entry.html).
- [Java SE 17 — `Collections.unmodifiableMap(Map)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)).
- [Java SE 17 — `AbstractMap.SimpleEntry`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/AbstractMap.SimpleEntry.html).
