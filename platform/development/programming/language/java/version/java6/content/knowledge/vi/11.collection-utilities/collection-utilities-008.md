# `SimpleImmutableEntry` và giới hạn của bất biến nông trong Java

`AbstractMap.SimpleImmutableEntry<K, V>` là một cách biểu diễn **một cặp khóa–giá trị có tham chiếu cố định** trong Java Collections Framework. API này có từ Java 6 và **vẫn được hỗ trợ trong các JDK hiện hành**. Điểm quan trọng nhất: không thay được khóa hay thay tham chiếu giá trị qua `SimpleImmutableEntry`, nhưng **đối tượng mà khóa/giá trị trỏ đến vẫn có thể thay đổi**. Vì vậy, tên “Immutable” không đồng nghĩa với bất biến sâu.

Các ví dụ sử dụng Java 17+ để vừa học API gốc vừa áp dụng các phương thức hiện đại đang hữu ích.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Tạo và sử dụng `SimpleImmutableEntry`; hiểu hành vi `getKey()`, `getValue()`, `setValue()`, `equals()` và `hashCode()`.
2. Phân biệt một `Map.Entry` độc lập với entry thuộc `map.entrySet()`.
3. Giải thích vì sao cặp khóa–giá trị “không gán lại được” vẫn có thể quan sát thấy dữ liệu thay đổi.
4. Tạo snapshot phù hợp bằng **defensive copy** và đối chiếu với `Map.entry`, `Map.Entry.copyOf`, `Map.ofEntries`.
5. Tránh lỗi liên quan đến mutable key, hash code, rò rỉ trạng thái và chia sẻ dữ liệu giữa luồng.

## 2. `SimpleImmutableEntry` thực chất là gì?

Đây là lớp lồng `public static` của `java.util.AbstractMap`, triển khai `Map.Entry<K, V>` và `Serializable`. Có hai cách tạo thông dụng:

```java
new AbstractMap.SimpleImmutableEntry<>("language", "Java");
new AbstractMap.SimpleImmutableEntry<>(existingEntry);
```

Constructor thứ nhất giữ **các tham chiếu** khóa và giá trị nhận vào. Constructor thứ hai lấy `getKey()` và `getValue()` từ một entry có sẵn rồi giữ lại các tham chiếu tương ứng; nó **không tạo bản sao sâu** của đối tượng bên trong. Với các instance được tạo trực tiếp từ lớp này, không có liên kết sống với một `Map` nào.

| API/thuộc tính | Hành vi cần nhớ |
| --- | --- |
| `getKey()`, `getValue()` | Trả về khóa/giá trị; nếu là kiểu tham chiếu thì trả **chính tham chiếu đã lưu**. |
| `setValue(newValue)` | **Luôn ném `UnsupportedOperationException`** trong triển khai `SimpleImmutableEntry`. |
| `equals(Object)` | Hai `Map.Entry` bằng nhau nếu khóa tương đương và giá trị tương đương theo `equals`; không yêu cầu cùng lớp triển khai. |
| `hashCode()` | Theo hợp đồng `Map.Entry`: hash của khóa XOR hash của giá trị, coi `null` là 0. |
| `toString()` | Dạng biểu diễn `key=value`. |
| `null` | Constructor `SimpleImmutableEntry` chấp nhận khóa hoặc giá trị `null`. |
| `Serializable` | Lớp triển khai `Serializable`; việc tuần tự hóa thành công còn phụ thuộc vào toàn bộ đồ thị đối tượng khóa/giá trị. |

Lưu ý chính xác về API: `SimpleImmutableEntry` **không phải lớp `final`**. Đối tượng được tạo trực tiếp từ chính lớp này không cho phép thay tham chiếu qua các phương thức của nó; tuy nhiên, một lớp con có thể cung cấp hành vi khác. Khi thiết kế hợp đồng API, đừng suy ra mọi đối tượng được khai báo dưới kiểu `SimpleImmutableEntry` đều có bất biến sâu hoặc chắc chắn có cùng hành vi với instance gốc.

### Entry độc lập khác entry của Map

- `new SimpleImmutableEntry<>(k, v)` tạo cặp dữ liệu độc lập; cập nhật mapping trong `Map` gốc về sau **không tự thay tham chiếu** trong entry này.
- `new SimpleImmutableEntry<>(mapEntry)` lấy một snapshot **của hai tham chiếu tại thời điểm tạo**; không tiếp tục đọc trực tiếp từ map.
- Entry thu được khi duyệt `map.entrySet()` có thể liên kết với map nền. Tùy triển khai và ngữ cảnh, `setValue` có thể cập nhật map. Không được giả định rằng mọi `Map.Entry` đều độc lập hoặc đều hỗ trợ `setValue`.
- Nếu dữ liệu nền có thể đổi đồng thời, chỉ chụp một cặp entry **không biến thao tác đọc nhiều phần tử thành snapshot nhất quán của cả map**.

## 3. Ví dụ chạy được: snapshot của một mapping

Tạo tệp `EntrySnapshotDemo.java`:

```java
import java.util.AbstractMap;
import java.util.HashMap;
import java.util.Map;

public class EntrySnapshotDemo {
    public static void main(String[] args) {
        Map<String, Integer> config = new HashMap<>();
        config.put("timeout", 30);

        Map.Entry<String, Integer> snapshot =
                new AbstractMap.SimpleImmutableEntry<>(
                        "timeout", config.get("timeout"));

        config.put("timeout", 60);

        System.out.println("map=" + config.get("timeout"));
        System.out.println("snapshot=" + snapshot);
        System.out.println("same mapping="
                + snapshot.equals(Map.entry("timeout", 30)));

        try {
            snapshot.setValue(90);
        } catch (UnsupportedOperationException ex) {
            System.out.println("setValue=blocked");
        }
    }
}
```

Biên dịch và chạy:

```bash
javac EntrySnapshotDemo.java
java EntrySnapshotDemo
```

Đầu ra chính xác:

```text
map=60
snapshot=timeout=30
same mapping=true
setValue=blocked
```

**Vì sao?** `snapshot` lưu tham chiếu tới `Integer` mang giá trị 30. Lệnh `config.put` sau đó thay mapping trong map, không sửa entry độc lập. `Integer` là kiểu không biến đổi nội dung, nên đây là ví dụ snapshot ổn định. `equals` trả `true` dù đối tượng còn lại được tạo bằng `Map.entry`, vì cả hai biểu diễn cùng mapping.

Điều này **không** chứng minh rằng với mọi kiểu `K`/`V`, `SimpleImmutableEntry` sẽ giữ nguyên trạng thái có thể quan sát về sau.

## 4. “Bất biến nông” là giới hạn quan trọng nhất

Giả sử entry giữ một `ArrayList`. Nó không cho gán một `List` khác bằng `setValue`, nhưng vẫn trả về danh sách đang có qua `getValue`. Cả người tạo và người nhận entry đều có thể thay đổi **cùng một đối tượng**.

Tạo tệp `ShallowEntryDemo.java`:

```java
import java.util.AbstractMap;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class ShallowEntryDemo {
    public static void main(String[] args) {
        List<String> tags = new ArrayList<>(List.of("core"));

        Map.Entry<String, List<String>> entry =
                new AbstractMap.SimpleImmutableEntry<>("module", tags);

        tags.add("security");
        System.out.println("after source change=" + entry.getValue());

        entry.getValue().add("java");
        System.out.println("source after entry change=" + tags);

        try {
            entry.setValue(List.of("replacement"));
        } catch (UnsupportedOperationException ex) {
            System.out.println("setValue=blocked");
        }
    }
}
```

Chạy:

```bash
javac ShallowEntryDemo.java
java ShallowEntryDemo
```

Đầu ra chính xác:

```text
after source change=[core, security]
source after entry change=[core, security, java]
setValue=blocked
```

Đây là ba hiện tượng khác nhau:

1. `tags.add("security")` thay đổi nội dung đối tượng đã được tham chiếu; `entry.getValue()` nhìn thấy thay đổi ấy.
2. `entry.getValue().add("java")` sửa trực tiếp đối tượng được chia sẻ; biến `tags` cũng nhìn thấy thay đổi.
3. `entry.setValue(...)` cố thay tham chiếu giá trị, nên bị chặn.

**Khóa cũng gặp vấn đề tương tự.** Nếu khóa là một `List` hoặc đối tượng có `equals/hashCode` phụ thuộc vào các trường có thể đổi, nội dung khóa thay đổi sẽ kéo theo kết quả `equals` và `hashCode` của entry thay đổi. Khi entry hoặc khóa được dùng trong `HashSet`/`HashMap`, điều này có thể phá vỡ giả định tra cứu ổn định. Với khóa dựa vào nội dung, hãy ưu tiên dữ liệu bất biến và không đột biến nó sau khi đưa vào cấu trúc băm.

### Ba tầng cần phân biệt

- **Không thể gán lại tham chiếu (unmodifiable entry):** `SimpleImmutableEntry` trực tiếp không cho `setValue`; khóa cũng không có setter.
- **Bất biến nông (shallow immutability):** cặp tham chiếu ổn định nhưng trạng thái đối tượng mà chúng trỏ tới có thể thay đổi.
- **Bất biến của toàn bộ đồ thị dữ liệu:** mọi phần dữ liệu liên quan cần được thiết kế bất biến, sao chép phù hợp hoặc quản lý quyền sở hữu rõ ràng. Chỉ dùng `SimpleImmutableEntry` **chưa đủ** để đạt điều này.

Đặt một danh sách vào `Collections.unmodifiableList(source)` chỉ tạo **view không cho sửa qua wrapper**, không nhất thiết khóa nguồn: chỉnh sửa `source` vẫn có thể xuất hiện qua view. Đó không phải snapshot độc lập.

## 5. Tạo snapshot an toàn bằng defensive copy

Với `List<String>`, một cách phù hợp là chụp bản sao danh sách tại ranh giới API, rồi giữ danh sách không chỉnh sửa được trong entry. Ví dụ dưới đây dùng `List.copyOf` (Java 10+) và chuỗi `String` vốn không thể đổi nội dung.

Tạo tệp `DefensiveEntryDemo.java`:

```java
import java.util.AbstractMap;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class DefensiveEntryDemo {
    static Map.Entry<String, List<String>> snapshot(
            String key, List<String> source) {
        return new AbstractMap.SimpleImmutableEntry<>(
                key, List.copyOf(source));
    }

    public static void main(String[] args) {
        List<String> source = new ArrayList<>(List.of("read"));
        Map.Entry<String, List<String>> safe =
                snapshot("permissions", source);

        source.add("write");
        System.out.println("snapshot=" + safe.getValue());

        try {
            safe.getValue().add("delete");
        } catch (UnsupportedOperationException ex) {
            System.out.println("value=unmodifiable");
        }

        System.out.println("source=" + source);
    }
}
```

Chạy:

```bash
javac DefensiveEntryDemo.java
java DefensiveEntryDemo
```

Đầu ra chính xác:

```text
snapshot=[read]
value=unmodifiable
source=[read, write]
```

`List.copyOf(source)` tạo danh sách không chỉnh sửa được và, khi nguồn là `ArrayList` có thể sửa như ở đây, tách cấu trúc danh sách khỏi nguồn. Sau đó `source.add` không ảnh hưởng `safe.getValue()`. Thử `add` lên danh sách trong entry cũng bị chặn.

**Các giới hạn của phương án này:**

- `List.copyOf` **từ chối phần tử `null`**. Cần chọn chính sách dữ liệu phù hợp trước khi sao chép.
- `List.copyOf` không clone từng phần tử. Với `List<MutableObject>`, danh sách mới giữ **cùng các tham chiếu phần tử**; thay đổi trạng thái từng phần tử vẫn lộ ra.
- Nếu khóa cũng là đối tượng mutable, hãy xử lý khóa tương tự: tạo immutable representation hoặc defensive copy cho khóa.
- Với cấu trúc lồng nhau (`List<List<T>>`, cây đối tượng, map chứa DTO có setter...), phải quyết định rõ những lớp dữ liệu nào cần được sao chép hoặc chuyển thành kiểu bất biến.
- Giữ tham chiếu qua `SimpleImmutableEntry` không tự cung cấp đồng bộ hóa hay bảo đảm an toàn khi nhiều luồng cùng đọc/ghi một đối tượng mutable.

### Khi nào record hữu ích hơn cặp khóa–giá trị?

Nếu hai giá trị mang nghĩa nghiệp vụ, kiểu tên trường rõ ràng thường dễ đọc hơn `getKey()`/`getValue()`. Ví dụ minh họa dưới đây là **đoạn code thành phần**, có thể đặt trong một lớp Java 17+:

```java
record AccessPolicy(String role, List<String> permissions) {
    AccessPolicy {
        permissions = List.copyOf(permissions);
    }
}
```

Constructor thực hiện defensive copy nên nội dung danh sách quyền không bị sửa qua alias bên ngoài, trong điều kiện mỗi phần tử là `String` bất biến. Bản thân từ khóa `record` **không tự sao chép sâu** các thành phần mutable; nếu bỏ `List.copyOf`, record cũng gặp vấn đề bất biến nông.

## 6. Các lựa chọn hiện đại: chọn đúng theo mục đích

| Lựa chọn | Từ Java | Đặc điểm | Khi nên dùng |
| --- | --- | --- | --- |
| `new AbstractMap.SimpleImmutableEntry<>(k, v)` | 6 | Entry độc lập, `setValue` bị chặn, nhận `null`, lớp triển khai `Serializable`; dữ liệu tham chiếu vẫn nông. | Cần một `Map.Entry` độc lập, có thể cần `null` hoặc hợp đồng về kiểu triển khai cụ thể. |
| `Map.entry(k, v)` | 9 | Tạo entry không chỉnh sửa được, **không nhận `null`**, không `Serializable`; là đối tượng dạng value-based. | Viết cặp khóa–giá trị ngắn gọn, đặc biệt khi chuẩn bị cho `Map.ofEntries`. |
| `Map.Entry.copyOf(entry)` | 17 | Tạo entry độc lập tương đương, từ chối `null` ở entry/khóa/giá trị; có thể tái sử dụng entry đầu vào phù hợp. | Tách mapping khỏi entry nhận từ map mà không cần giữ loại triển khai. |
| `Map.of(k, v)` / `Map.ofEntries(...)` | 9 | Tạo **map không cho thêm, xóa, sửa mapping**, không nhận khóa/giá trị `null`; vẫn không clone sâu dữ liệu mutable. | Cần cả một map không chỉnh sửa được, thay vì một entry riêng lẻ. |
| `Map.copyOf(existingMap)` | 10 | Tạo map không chỉnh sửa được từ mapping hiện có, không nhận `null`; không deep copy khóa/giá trị. | Cần snapshot của cấu trúc map với phần tử phù hợp. |
| `new AbstractMap.SimpleEntry<>(k, v)` | 6 | Entry độc lập nhưng **cho `setValue`**. | Thật sự cần thay tham chiếu giá trị trong một cặp độc lập. |

Một số khác biệt dễ bỏ sót:

- `Map.entry` và `Map.Entry.copyOf` trả các entry không chỉnh sửa được nhưng **cũng chỉ giữ tham chiếu** tới khóa/giá trị; chúng không chữa vấn đề mutable object.
- `Map.ofEntries` lấy khóa/giá trị từ các entry để tạo map; map tạo ra **không lưu chính đối tượng entry đầu vào**. Chỉnh sửa một `SimpleEntry` đã truyền vào không đồng nghĩa sửa được map.
- Không dùng `Map.entry` nếu dữ liệu có thể là `null`; `SimpleImmutableEntry` cho phép `null`, trong khi các factory map hiện đại nêu trên thường không cho phép.
- Khi dữ liệu là snapshot của `entrySet()`, có thể dùng `map.entrySet().stream().map(Map.Entry::copyOf).toList()` trên Java 17+ để tách **các mapping** khỏi map gốc. Các khóa/giá trị mutable bên trong vẫn được chia sẻ; việc đọc snapshot của map đang bị sửa đồng thời phải có chiến lược đồng bộ/nhất quán riêng.
- Không dựa vào **identity** của đối tượng `Map.entry` (ví dụ `==`, `synchronized(entry)`) vì API xác định đó là đối tượng value-based.

## 7. `equals`, `hashCode` và các hệ quả thực tế

Theo hợp đồng `Map.Entry`, so sánh cặp mapping dựa trên `equals` của **cả khóa lẫn giá trị**; công thức hash là:

```text
entryHash = (key == null ? 0 : key.hashCode())
          ^ (value == null ? 0 : value.hashCode())
```

Dấu `^` là XOR trên số nguyên. Lợi ích: entry từ các triển khai khác nhau vẫn có thể bằng nhau nếu cùng mapping. Mặt trái: khi nội dung mutable của khóa hay giá trị ảnh hưởng `hashCode`, hash của chính entry cũng có thể đổi dù `setValue` chưa từng được gọi.

Ví dụ tình huống cần tránh: đặt một `SimpleImmutableEntry<List<String>, Integer>` chứa khóa `ArrayList` vào `HashSet` rồi sửa phần tử trong khóa. `ArrayList.hashCode()` phụ thuộc vào nội dung, nên cấu trúc băm có thể không tìm lại được phần tử ở vị trí bucket kỳ vọng. Đừng dựa vào kết quả `contains` hay `remove` sau dạng đột biến này.

Thực hành đúng: nếu cần dùng entry làm phần tử trong `HashSet` hay khóa trong `HashMap`, giữ toàn bộ dữ liệu tham gia `equals/hashCode` ổn định trong suốt thời gian lưu trữ.

## 8. Checklist thiết kế API

Trước khi trả `SimpleImmutableEntry` từ một hàm hoặc lưu trong một collection, tự kiểm tra:

1. **Mục đích:** cần một cặp `Map.Entry` độc lập, hay cần một `Map` bất biến, hay nên dùng `record` có tên trường rõ hơn?
2. **Loại dữ liệu:** khóa và giá trị là immutable như `String`, `Integer`, `LocalDate`, hay là `List`, `Map`, array, DTO mutable?
3. **Sao chép:** có alias từ caller hoặc nơi khác có thể sửa dữ liệu sau khi entry được tạo không? Nếu có, defensive copy ở đúng ranh giới.
4. **Phần tử lồng nhau:** sao chép container đã đủ chưa, hay các phần tử bên trong vẫn mutable?
5. **Hash/equality:** dữ liệu có thể đổi khi entry đang nằm trong cấu trúc băm không?
6. **Đồng thời:** các luồng có đang chia sẻ đối tượng mutable không? Nếu có, cần thiết kế đồng bộ và quyền sở hữu dữ liệu, không chỉ dựa vào tên lớp.
7. **Null/serialization:** có cần `null` hay giao thức serialization không? Chọn constructor/factory theo hợp đồng thực tế thay vì suy diễn.
8. **Nguồn gốc của entry:** entry đến từ `entrySet()` hay tạo độc lập? Có cần chụp snapshot để thoát phụ thuộc vào map nền không?

## 9. Lỗi thường gặp và cách sửa

**Lỗi 1 – “`setValue` bị chặn nên `getValue()` cũng an toàn.”** Sai nếu value là kiểu mutable. Đọc/ghi thuộc tính hay thêm phần tử vào value vẫn có thể thực hiện được. **Sửa:** dùng immutable value, defensive copy phù hợp, hoặc hợp đồng ownership rõ ràng.

**Lỗi 2 – “`new SimpleImmutableEntry<>(existingEntry)` là deep copy.”** Sai: nó chỉ chụp hai tham chiếu. **Sửa:** tự sao chép khóa/giá trị, nhất là object graph lồng nhau.

**Lỗi 3 – “Bất kỳ `Map.Entry` nào cũng có thể `setValue`.”** Sai: `setValue` là thao tác tùy chọn và một số entry không gắn với map. **Sửa:** chỉ dùng thao tác đó khi hợp đồng của entry cụ thể cho phép.

**Lỗi 4 – “Một entry độc lập chính là map chỉ đọc.”** Sai: một entry chỉ là một cặp; `SimpleImmutableEntry` không chứa toàn bộ map. **Sửa:** dùng `Map.of`/`Map.ofEntries`/`Map.copyOf` cho map không chỉnh sửa được.

**Lỗi 5 – “`record`, `List.copyOf` hoặc `Map.copyOf` tự bảo đảm bất biến sâu.”** Sai khi phần tử bên trong có trạng thái mutable. **Sửa:** thiết kế immutable domain model, sao chép ở từng cấp cần thiết và kiểm thử tình huống alias.

**Lỗi 6 – “Entry có tham chiếu cố định thì mặc nhiên thread-safe.”** Sai nếu các đối tượng được trỏ tới thay đổi đồng thời. **Sửa:** chia sẻ immutable object graph, immutable snapshot phù hợp hoặc đồng bộ hóa theo mô hình xử lý.

## 10. Tự kiểm tra kiến thức

**Câu 1.** Tạo `var x = new AbstractMap.SimpleImmutableEntry<>("k", new ArrayList<>(List.of("a")));`. Lệnh `x.setValue(new ArrayList<>())` có chạy được không? Lệnh `x.getValue().add("b")` thì sao?

**Đáp án:** `setValue` ném `UnsupportedOperationException`; `add` thành công vì giá trị ban đầu là `ArrayList` mutable. Sau đó `x.getValue()` chứa `["a", "b"]`.

**Câu 2.** Vì sao `new SimpleImmutableEntry<>(entryFromMap)` không tự động tạo snapshot bất biến sâu?

**Đáp án:** constructor chỉ giữ các tham chiếu `getKey()/getValue()` tại thời điểm gọi. Nó tách khỏi mapping của map gốc, nhưng các object mutable được tham chiếu vẫn chia sẻ và có thể thay đổi.

**Câu 3.** Nếu cần trả một danh sách quyền dưới dạng cặp key–value và muốn caller không thể thay đổi cả cấu trúc danh sách lẫn các quyền, nên xử lý thế nào?

**Đáp án:** với quyền biểu diễn bằng `String`, dùng `List.copyOf(source)` cho value, chọn key immutable rồi mới tạo entry. Với phần tử là object mutable, phải tạo immutable representation hoặc sao chép phù hợp từng phần tử; chỉ copy list là chưa đủ.

## Tài liệu chính thức để tra cứu

- [`AbstractMap.SimpleImmutableEntry` — JDK 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/AbstractMap.SimpleImmutableEntry.html)
- [`Map.Entry` — JDK 25 API, bao gồm `copyOf`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.Entry.html)
- [`Map` — JDK 26 API, `entry`, `ofEntries`, `copyOf`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html)
- [Creating Unmodifiable Lists, Sets, and Maps — Oracle](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html)

**Ghi nhớ:** `SimpleImmutableEntry` cố định **cặp tham chiếu** trong instance trực tiếp, không tự đóng băng trạng thái các đối tượng được tham chiếu. Chất lượng của snapshot phụ thuộc vào đặc tính bất biến và cách sao chép **cả khóa lẫn giá trị**.
