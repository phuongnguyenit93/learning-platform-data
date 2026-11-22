# Tách cấu trúc kết quả khỏi thay đổi của Map nguồn với `Map.copyOf` (Java 10+)

## 1. Mục tiêu: một bản chụp Map không thay đổi theo nguồn

Khi một lớp đang giữ `Map` có thể cập nhật theo thời gian, đôi khi ta cần trả về một kết quả **đại diện cho trạng thái ánh xạ tại thời điểm gọi** thay vì một đối tượng tiếp tục phản ánh mọi thao tác `put`, `remove` hoặc `replace` trên nguồn. Từ Java 10, `Map.copyOf` hỗ trợ trực tiếp nhu cầu này.

```java
var source = new HashMap<String, Integer>();
source.put("apple", 10);
source.put("banana", 20);

var snapshot = Map.copyOf(source); // Map<String, Integer>
source.put("apple", 99);
source.remove("banana");

// snapshot vẫn ánh xạ "apple" -> 10 và "banana" -> 20
```

Các dòng trên là **mã minh họa đặt trong một phương thức**; cần `import java.util.HashMap;` và `import java.util.Map;`.

**Hợp đồng cốt lõi:** `Map.copyOf(source)` trả về một `Map` **không cho sửa các ánh xạ** và **không phản ánh những thay đổi của Map nguồn sau thời điểm tạo**. Nội dung được giữ lại gồm các cặp khóa–giá trị ở mức cấu trúc `Map`, không phải bản sao sâu của mọi đối tượng.

Đây là kiến thức **vẫn áp dụng trong Java hiện đại**. `Map.copyOf` không phải một phương thức bị loại bỏ, cũng không phải một cách tạo live view.

## 2. Hợp đồng API chính xác

Chữ ký của phương thức:

```java
static <K, V> Map<K, V> copyOf(Map<? extends K, ? extends V> map)
```

Đây là **chữ ký API**, không phải một phương thức tự triển khai trong chương trình của bạn. Với tham số `Map<String, Integer>`, kết quả có thể suy luận kiểu là `Map<String, Integer>`:

```java
Map<String, Integer> source = new HashMap<>();
source.put("a", 1);

var snapshot = Map.copyOf(source); // kiểu tĩnh Map<String, Integer>
```

Các điều khoản quan trọng của `Map.copyOf`:

1. **Không cho sửa:** không thể thêm, xóa hoặc thay thế ánh xạ trong kết quả bằng `put`, `remove`, `clear`, `replace`, `compute`... Những lời gọi mutator không được hỗ trợ và ném `UnsupportedOperationException`.
2. **Không chứa `null`:** tham số map không được là `null`; các khóa và giá trị trong map nguồn cũng không được là `null`. Vi phạm gây `NullPointerException` khi gọi `copyOf`.
3. **Độc lập khỏi thay đổi cấu trúc của nguồn về sau:** khi thêm, xóa hoặc thay giá trị ánh xạ trên nguồn, kết quả đã tạo không phản ánh các thao tác ấy.
4. **Không bảo đảm thứ tự duyệt:** Map được tạo bởi nhóm factory `Map.of`/`Map.ofEntries`/`Map.copyOf` có thứ tự iteration không xác định. Không nên dựa vào thứ tự `entrySet()`, `keySet()` hay `toString()` để làm output ổn định.
5. **Không hứa trả về instance mới:** nếu nguồn vốn là một Map không sửa được thích hợp, implementation có thể tái sử dụng instance; kết quả thuộc nhóm **value-based**. Không dựa vào `==` hay identity hash để kiểm tra semantics.
6. **Sao chép nông:** `Map.copyOf` không clone từng khóa hoặc từng giá trị. Nếu một value hoặc key là đối tượng có thể thay đổi trạng thái, việc thay đổi object đó qua tham chiếu khác vẫn có thể ảnh hưởng hành vi nhìn thấy được.

Quan trọng nhất với đề bài: **thay đổi ánh xạ ở Map nguồn và thay đổi trạng thái của object được tham chiếu trong Map là hai vấn đề khác nhau**.

## 3. So sánh với view và một Map mới có thể sửa

Ba biểu thức sau có thể cùng chứa các cặp khóa–giá trị lúc đầu, nhưng cam kết lâu dài khác nhau:

```java
Map<String, String> source = new LinkedHashMap<>();
source.put("team", "A");
source.put("version", "1");

var liveView = Collections.unmodifiableMap(source);
var snapshot = Map.copyOf(source);
var editableCopy = new HashMap<>(source);
```

Đoạn trên cần các import thuộc `java.util`.

| Tiêu chí | `Map.copyOf(source)` | `Collections.unmodifiableMap(source)` | `new HashMap<>(source)` |
| --- | --- | --- | --- |
| Kết quả có cho `put`/`remove`? | Không | Không qua view | Có |
| Khi gọi `source.put(...)` sau thời điểm tạo | **Không đổi ánh xạ của snapshot** | **Thấy thay đổi**, vì view bám nguồn | Không đổi ánh xạ của bản sao |
| Kết quả có thể chứa key/value `null`? | **Không** | Có, nếu backing map cho phép | Có đối với `HashMap` |
| Có tạo bản sao cấu trúc độc lập? | Có về mặt hợp đồng kết quả; có thể reuse Map đã unmodifiable phù hợp | Không; view dựa trên nguồn | Có, một `HashMap` mới |
| Có giữ bảo đảm thứ tự iteration của `LinkedHashMap` nguồn? | **Không** | View thể hiện thứ tự của backing map | `HashMap` không bảo đảm thứ tự |
| Có sao chép sâu value/key mutable? | Không | Không | Không |
| Có bảo đảm identity mới mỗi lần gọi? | Không; value-based | Không dùng view làm công cụ khóa/identity thiết kế | `new` tạo instance `HashMap` mới |

**Khi nào chọn loại nào?**

- Cần **kết quả chỉ đọc không bị nguồn thay đổi về sau** → `Map.copyOf`, nếu đầu vào không chứa `null`.
- Cần **góc nhìn chỉ đọc đang phản ánh nguồn cập nhật** → `Collections.unmodifiableMap(source)`, nhưng cần hiểu rõ coupling với backing map.
- Cần **Map riêng để bổ sung/sửa/xóa** → `new HashMap<>(source)` hoặc `new LinkedHashMap<>(source)` tùy yêu cầu thứ tự.

## 4. Chứng minh bằng các thao tác `put`, `remove` và `replace`

```java
var source = new LinkedHashMap<String, String>();
source.put("team", "A");
source.put("version", "1");

var snapshot = Map.copyOf(source);
var view = Collections.unmodifiableMap(source);

source.put("version", "2"); // đổi giá trị của khóa đang có
source.remove("team");      // xóa một khóa
source.put("status", "live"); // thêm khóa mới
```

Sau khi sửa:

| Biểu thức đọc | Kết quả theo khóa | Ý nghĩa |
| --- | --- | --- |
| `snapshot.get("team")` | `"A"` | Vẫn giữ mapping từ thời điểm tạo |
| `snapshot.get("version")` | `"1"` | Không bị `source.put("version","2")` thay đổi |
| `snapshot.containsKey("status")` | `false` | Không thêm khóa mới theo nguồn |
| `view.containsKey("team")` | `false` | View thấy việc xóa khóa ở nguồn |
| `view.get("version")` | `"2"` | View đọc trạng thái mới |
| `view.get("status")` | `"live"` | View thấy khóa mới |

Thử sửa trực tiếp kết quả cũng khác nhau:

```java
// snapshot.put("new", "X"); // biên dịch được theo interface Map,
// nhưng nếu chạy sẽ ném UnsupportedOperationException.

// view.remove("status");   // cũng ném UnsupportedOperationException.
// source.remove("status"); // hợp lệ; view sẽ phản ánh việc xóa.
```

Với cả snapshot và view, **biên dịch được** một lời gọi mutator không có nghĩa đối tượng runtime **cho phép thay đổi**. Hợp đồng unmodifiable được kiểm tra khi chạy.

## 5. `Map.copyOf` trên unmodifiable view vẫn tạo kết quả độc lập về ánh xạ

Một trường hợp dễ nhầm: đầu vào là một `Collections.unmodifiableMap`, nên trông như đã “bất biến”:

```java
var source = new LinkedHashMap<String, String>();
source.put("A", "1");
var view = Collections.unmodifiableMap(source);
var snapshot = Map.copyOf(view);

source.put("B", "2");

System.out.println(view.containsKey("B"));     // true
System.out.println(snapshot.containsKey("B")); // false
```

**Vì sao?** `Collections.unmodifiableMap(source)` chỉ cấm sửa *qua view*. Đối tượng `source` vẫn có thể sửa, do đó view **không phải snapshot**. `Map.copyOf` phải đáp ứng hợp đồng: kết quả không phản ánh sửa đổi tiếp theo của đầu vào. Vì vậy việc dùng view làm nguồn không làm `copyOf` biến thành live view.

Điều này không mâu thuẫn với ghi chú của Javadoc rằng khi đầu vào vốn là một unmodifiable Map, `copyOf` thường có thể không tạo bản sao mới. Đó là **tối ưu hóa implementation được phép**, không phải một cam kết rằng mọi unmodifiable view sẽ được giữ nguyên tham chiếu bất chấp backing có thể đổi. Điều quan trọng là hợp đồng kết quả, không phải một giả định về identity.

## 6. Không nhầm shallow snapshot với deep immutability

Giả sử value là đối tượng có thể sửa:

```java
var note = new StringBuilder("draft");
var source = new HashMap<String, StringBuilder>();
source.put("note", note);

var snapshot = Map.copyOf(source);

note.append("-done");
System.out.println(snapshot.get("note")); // draft-done
```

Ở đây không có `snapshot.put(...)` nào. Map vẫn chứa **cùng tham chiếu `StringBuilder`** đã lưu lúc tạo; nội dung của đối tượng được thay đổi bên ngoài.

Phân biệt:

- **Thay ánh xạ:** `source.put("note", new StringBuilder("new"))` tạo liên kết khóa `note` đến một object khác trên nguồn; `snapshot` không tự nhận ánh xạ mới.
- **Sửa đối tượng đang được tham chiếu:** `oldBuilder.append("...")` thay nội dung object mà cả hai Map có thể còn tham chiếu; giá trị quan sát qua `snapshot` thay theo.

Với **khóa mutable**, rủi ro còn đáng chú ý hơn: nếu `equals`/`hashCode` của khóa thay đổi sau khi nó được dùng làm khóa, phép `get` và khả năng tìm entry có thể gặp hành vi không mong muốn. Vì thế nên dùng key có tính bất biến và value có hợp đồng bất biến hoặc sao chép phù hợp khi cần một snapshot dữ liệu ổn định lâu dài.

**Kết luận kỹ thuật:** `Map.copyOf` tách **tập ánh xạ**, không tự động sao chép sâu đồ thị object ở phía dưới.

## 7. Quy tắc `null`: khác biệt có thể làm chương trình thất bại

`HashMap` cho phép một khóa `null` và các giá trị `null`; `Map.copyOf` từ chối bất kỳ key hay value `null` nào:

```java
var source = new HashMap<String, String>();
source.put("x", null);

var editable = new HashMap<>(source);            // hợp lệ
var view = Collections.unmodifiableMap(source); // hợp lệ
// var snapshot = Map.copyOf(source);            // ném NullPointerException
```

Cũng không được truyền chính map `null`:

```java
// Map.copyOf(null); // ném NullPointerException
```

Đây là **ngoại lệ lúc chạy** của lời gọi copy, không phải hành vi “tự động lọc phần tử null”. Nếu dữ liệu nghiệp vụ cho phép phân biệt “khóa vắng” với “khóa có giá trị null”, cần quyết định chính sách trước khi dùng `copyOf`:

1. Nếu `null` không hợp lệ: kiểm tra/chuẩn hóa dữ liệu đầu vào rồi `Map.copyOf`.
2. Nếu `null` cần được giữ: có thể dùng `Collections.unmodifiableMap(new HashMap<>(source))` để có một copy cấu trúc không cho sửa qua view, miễn là backing copy không bị lộ hoặc sửa qua tham chiếu khác.
3. Nếu chỉ cần Map mutable riêng: dùng `new HashMap<>(source)`.

Không nên âm thầm loại bỏ `null` hoặc thay bằng chuỗi rỗng khi điều đó làm sai ý nghĩa nghiệp vụ.

## 8. Không dựa vào thứ tự iteration của kết quả

`Map.copyOf` không cam kết giữ encounter order của `LinkedHashMap` đầu vào. Hai Map có cùng ánh xạ nhưng thứ tự duyệt `keySet`/`entrySet` và cách in `toString()` có thể khác.

```java
var source = new LinkedHashMap<String, Integer>();
source.put("z", 10);
source.put("a", 20);

var snapshot = Map.copyOf(source);

// Không khẳng định println(snapshot) luôn in "{z=10, a=20}".
System.out.println(new TreeMap<>(snapshot)); // {a=20, z=10}
```

Ví dụ dùng `TreeMap` **chỉ để hiển thị ổn định theo thứ tự khóa**; không phải vì `Map.copyOf` đã tự sắp xếp. Với các key có thể so sánh được như `String`, `TreeMap` tạo thứ tự tự nhiên. Khi muốn **giữ thứ tự chèn** như một phần hợp đồng kết quả, phải lựa chọn cấu trúc phù hợp, chẳng hạn tạo bản sao `LinkedHashMap` rồi bọc thành một unmodifiable view mà không để lộ backing copy:

```java
Map<String, Integer> orderedSnapshot =
        Collections.unmodifiableMap(new LinkedHashMap<>(source));
```

Đây là lựa chọn khác với `Map.copyOf`, cần nêu rõ rằng bản sao bên trong không bị cập nhật qua tham chiếu khác. Nếu thứ tự không quan trọng, `Map.copyOf` thường đơn giản hơn cho snapshot chỉ đọc.

## 9. Không dựa vào identity của instance trả về

Các Map do `Map.of`, `Map.ofEntries` và `Map.copyOf` tạo là **value-based**. Mã đúng nên quan tâm các ánh xạ và `equals`, không dựa vào identity.

```java
var original = Map.of("A", 1, "B", 2);
var copy = Map.copyOf(original);

System.out.println(original.equals(copy)); // true
// Đừng dùng original == copy làm điều kiện đúng/sai của chương trình.
```

Tùy implementation, `copyOf` có thể trả lại Map đã unmodifiable phù hợp thay vì tạo một object mới. Các thao tác không nên làm với kết quả `Map.copyOf`:

- Dùng `synchronized(snapshot)` để phối hợp luồng.
- Lưu snapshot trong `IdentityHashMap` để nhận diện dữ liệu theo identity thay vì giá trị.
- Dùng `System.identityHashCode(snapshot)` làm định danh bền vững.
- Phụ thuộc vào `snapshot1 == snapshot2` để kết luận dữ liệu có giống nhau hay không.

Nếu cần khóa, tạo một object riêng, ổn định, thuộc quyền sở hữu của thành phần:

```java
private final Object lock = new Object();
```

Dòng trên là khai báo trường minh họa trong một lớp, không phải một lệnh để đặt trong phần thân phương thức. Value-based không ngăn `Map.copyOf` được dùng làm dữ liệu chỉ đọc; nó chỉ nói rằng ứng dụng không nên dựa vào **danh tính của Map**.

## 10. Tạo snapshot khi Map nguồn có thể được cập nhật đồng thời

`Map.copyOf(source)` bảo đảm **kết quả không phản ánh sửa nguồn về sau**. Nhưng điều đó **không đồng nghĩa** việc copy một Map đang được nhiều luồng sửa đồng thời tạo được một snapshot nhất quán/atomically tại một thời điểm cụ thể.

Ví dụ, nếu một luồng đang thực hiện nhiều lệnh `put` và một luồng khác gọi `copyOf` đồng thời trên một `HashMap` thông thường mà không có quy tắc đồng bộ, ứng dụng có thể gặp race condition hoặc trạng thái không nhất quán. `Map.copyOf` không phải primitive đồng bộ dành cho Map mutable bất kỳ.

Một thiết kế rõ ràng là yêu cầu mọi cập nhật và thao tác lấy snapshot dùng cùng một khóa:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

final class SettingsStore {
    private final Object lock = new Object();
    private final Map<String, String> mutable = new HashMap<>();

    void put(String key, String value) {
        Objects.requireNonNull(key);
        Objects.requireNonNull(value);
        synchronized (lock) {
            mutable.put(key, value);
        }
    }

    Map<String, String> snapshot() {
        synchronized (lock) {
            return Map.copyOf(mutable);
        }
    }
}
```

Đây là một lớp Java minh họa độc lập có thể biên dịch. Những điểm quan trọng:

- `mutable` là Map private, người gọi bên ngoài không được sửa trực tiếp.
- `put` và `snapshot` cùng đồng bộ trên `lock`, nên không có thao tác cập nhật trung gian xen vào lúc copy.
- `Objects.requireNonNull` đảm bảo hợp đồng không nhận `null` mà `Map.copyOf` yêu cầu.
- Kết quả `snapshot()` không phản ánh những lần `put` thực hiện **sau khi snapshot được tạo**.

Nếu ứng dụng còn có phương thức `remove`, `clear` hoặc cập nhật hàng loạt, các thao tác đó cũng phải tuân thủ cùng quy tắc khóa. Nếu các object value mutable được đưa vào Map thay vì `String`, cần tính cả độ an toàn và tính bất biến của chúng.

## 11. Chương trình hoàn chỉnh kiểm chứng hợp đồng (Java 17+)

Lưu vào tệp `MapSnapshotDemo.java`:

```java
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.TreeMap;

public class MapSnapshotDemo {
    static void checkFailure(String name, Runnable action) {
        try {
            action.run();
            System.out.println(name + "=none");
        } catch (UnsupportedOperationException | NullPointerException e) {
            System.out.println(name + "=" + e.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        var source = new LinkedHashMap<String, String>();
        source.put("team", "A");
        source.put("version", "1");

        var liveView = Collections.unmodifiableMap(source);
        var snapshot = Map.copyOf(source);
        var editable = new HashMap<>(source);

        source.put("version", "2");
        source.remove("team");
        source.put("status", "live");
        editable.put("extra", "only-copy");

        System.out.println("source=" + new TreeMap<>(source));
        System.out.println("liveView=" + new TreeMap<>(liveView));
        System.out.println("snapshot=" + new TreeMap<>(snapshot));
        System.out.println("editable=" + new TreeMap<>(editable));

        checkFailure("snapshot.put", () -> snapshot.put("x", "y"));
        checkFailure("liveView.put", () -> liveView.put("x", "y"));

        var withNull = new HashMap<String, String>();
        withNull.put("x", null);
        checkFailure("copyOf.null", () -> Map.copyOf(withNull));
        System.out.println("hashMap.null=" + withNull.containsKey("x"));

        var note = new StringBuilder("draft");
        var withMutableValue = new HashMap<String, StringBuilder>();
        withMutableValue.put("note", note);
        var shallowSnapshot = Map.copyOf(withMutableValue);
        note.append("-done");
        System.out.println("shallow.note=" + shallowSnapshot.get("note"));

        var viewSnapshot = Map.copyOf(liveView);
        source.put("status", "changed");
        System.out.println("liveView.after=" + new TreeMap<>(liveView));
        System.out.println("viewSnapshot.after=" + new TreeMap<>(viewSnapshot));
    }
}
```

Biên dịch và chạy:

```bash
javac MapSnapshotDemo.java
java MapSnapshotDemo
```

Đầu ra:

```text
source={status=live, version=2}
liveView={status=live, version=2}
snapshot={team=A, version=1}
editable={extra=only-copy, team=A, version=1}
snapshot.put=UnsupportedOperationException
liveView.put=UnsupportedOperationException
copyOf.null=NullPointerException
hashMap.null=true
shallow.note=draft-done
liveView.after={status=changed, version=2}
viewSnapshot.after={status=live, version=2}
```

**Vì sao output ổn định?** Mọi Map được in ra đều chuyển sang `TreeMap` trước khi in để sắp xếp theo khóa. Nếu in trực tiếp `snapshot`, thứ tự ánh xạ **không được bảo đảm** và có thể khác giữa các JDK.

**Đọc kết quả từng phần:**

1. `source` bị thay `version` từ `"1"` sang `"2"`, xóa `team` và thêm `status`. `liveView` phản ánh đúng các thay đổi này vì nó dùng backing map.
2. `snapshot` vẫn có `{team=A, version=1}`, chính là các ánh xạ lúc tạo, không đổi theo source.
3. `editable` là một `HashMap` cấu trúc riêng nên vẫn giữ hai ánh xạ cũ và có thêm `extra` theo thao tác riêng.
4. Gọi `put` trên `snapshot` hoặc `liveView` ném `UnsupportedOperationException`; đây là hai cách đạt tính không sửa được **qua kết quả**, nhưng chỉ snapshot tách khỏi source.
5. `Map.copyOf` từ chối value `null`; `HashMap` của ví dụ vẫn chấp nhận nó.
6. `shallowSnapshot` nhìn thấy nội dung `StringBuilder` bị đổi, minh họa giới hạn của shallow copy.
7. `viewSnapshot` được tạo từ unmodifiable view khi `status=live`; sau khi source đổi thành `status=changed`, live view đi theo nguồn còn `viewSnapshot` vẫn giữ ánh xạ cũ.

## 12. Câu hỏi thường gặp

### `Map.copyOf` có tạo object mới mỗi lần gọi không?

**Không có bảo đảm như vậy.** Tài liệu Java lưu ý trường hợp nguồn đã là unmodifiable map, factory có thể tránh copy không cần thiết. Cần dựa trên **nội dung và hợp đồng không thay đổi theo source**, không dựa trên `==`.

### `Map.copyOf` có cần Map nguồn thuộc một kiểu nhất định không?

Không. Tham số là `Map<? extends K, ? extends V>`, nên các implementation phù hợp có thể dùng làm đầu vào: `HashMap`, `LinkedHashMap`, `TreeMap`, unmodifiable view, v.v. Tuy nhiên, đầu vào phải tuân thủ hợp đồng không chứa `null` và phải được truy cập/duyệt một cách an toàn. Kết quả không giữ lại cam kết thứ tự hay comparator của implementation nguồn.

### Có thể thêm ánh xạ vào snapshot rồi dùng lại không?

Không thể sửa chính Map trả về. Nếu cần tạo một phiên bản mới, hãy xây Map mutable từ snapshot, chỉnh sửa rồi tạo snapshot mới:

```java
Map<String, Integer> current = Map.of("A", 1);
var draft = new HashMap<>(current);
draft.put("B", 2);
var next = Map.copyOf(draft);

// current vẫn chỉ có A -> 1; next có A -> 1 và B -> 2.
```

Cách này giữ các phiên bản kết quả riêng theo thời điểm, hữu ích khi công bố snapshot cấu hình hoặc dữ liệu truy xuất.

### `Map.copyOf` có làm các phần tử value trở thành thread-safe hay immutable không?

Không. Nó chỉ chặn sửa **cấu trúc ánh xạ trong Map kết quả**. Nếu value là một `ArrayList` mutable hoặc một entity có thể cập nhật, cùng tham chiếu đó vẫn có thể được thay đổi ở nơi khác. Cần lựa chọn immutable value, tạo bản sao phần tử hoặc quy định đồng bộ riêng.

### Nếu chỉ muốn người gọi không sửa Map, có cần `copyOf` không?

Tùy ý định API. `Collections.unmodifiableMap(source)` cấm sửa qua view nhưng cho người gọi nhìn thấy cập nhật của source. Nếu người gọi cần **dữ liệu cố định theo thời điểm**, `Map.copyOf` là cách diễn đạt hợp đồng rõ hơn. Nếu cố ý cung cấp **live read-only view**, `Collections.unmodifiableMap` có thể là đúng.

## 13. Checklist trước khi dùng `Map.copyOf`

1. **Có thực sự cần snapshot không?** Nếu nguồn sẽ đổi và kết quả phải giữ nguyên ánh xạ, `Map.copyOf` phù hợp.
2. **Nguồn có `null` key/value không?** Nếu có, phải thiết kế chính sách dữ liệu khác hoặc chuẩn hóa đúng nghiệp vụ.
3. **Các key và value có mutable không?** Nếu cần snapshot bất biến sâu, xử lý tính bất biến của phần tử, đặc biệt key dùng trong map dựa trên hash.
4. **Có yêu cầu giữ thứ tự duyệt không?** Nếu có, `Map.copyOf` không cung cấp bảo đảm; cân nhắc `Collections.unmodifiableMap(new LinkedHashMap<>(source))`.
5. **Có nhiều luồng cùng sửa/đọc Map nguồn không?** Nếu có, phối hợp khi lấy snapshot; `copyOf` không tự thực hiện một giao dịch nguyên tử trên Map mutable.
6. **Có đang phụ thuộc vào reference identity hoặc synchronized trên snapshot không?** Bỏ giả định đó; kết quả của factory là value-based.
7. **Người gọi nên được sửa dữ liệu kết quả không?** Nếu có, dùng bản sao mutable thay vì `copyOf`.
8. **API có cần phân biệt live view với snapshot?** Đặt tên phương thức và viết tài liệu hợp đồng rõ ràng, ví dụ `snapshot()` và `view()`.

## 14. Bài tập tự kiểm tra

Trong một phương thức có import `java.util.*;`:

```java
var source = new HashMap<String, Integer>();
source.put("x", 1);

var a = Map.copyOf(source);
var b = Collections.unmodifiableMap(source);
var c = new HashMap<>(source);

source.put("x", 2);
source.put("y", 3);
c.put("z", 4);
```

**Câu 1:** Giá trị `a.get("x")`, `b.get("x")` và `c.get("x")` là bao nhiêu?

**Đáp án:** `a.get("x")` = `1`; `b.get("x")` = `2`; `c.get("x")` = `1`. `a` giữ snapshot; `b` là live view; `c` là Map cấu trúc riêng.

**Câu 2:** Map nào có khóa `y`? Map nào có khóa `z`?

**Đáp án:** `b` thấy `y` từ nguồn, trong khi `a` và `c` không có `y`. Chỉ `c` có `z` do cập nhật riêng. `a` giữ đúng một ánh xạ `x=1` từ thời điểm tạo.

**Câu 3:** `a.put("q", 5)` và `b.put("q", 5)` có hợp lệ không?

**Đáp án:** Cả hai là lời gọi biên dịch được nhưng ném `UnsupportedOperationException` khi chạy. `c.put("q", 5)` được phép.

**Câu 4:** Nếu sau đó `source.put(null, 9)`, `Map.copyOf(source)` có kết quả gì?

**Đáp án:** `HashMap` chấp nhận khóa `null`; khi gọi `Map.copyOf(source)` mới, nó ném `NullPointerException`. Snapshot `a` đã tạo trước đó không bị thay đổi vì nguồn thêm khóa `null`.

**Câu 5:** Nếu `Map.copyOf(source)` được tạo từ một unmodifiable view có backing mutable, liệu snapshot có trở thành live view không?

**Đáp án:** Không. `copyOf` có hợp đồng kết quả không phản ánh thay đổi của Map đầu vào về sau. Không nên suy luận theo lớp wrapper hoặc identity của kết quả.

## Kết luận

`Map.copyOf(source)` là lựa chọn trực tiếp để **đóng băng các ánh xạ khóa–giá trị ở thời điểm tạo trong một Map không sửa được**, tách khỏi các thao tác thêm, xóa hoặc thay ánh xạ về sau trên nguồn. Nó **khác** `Collections.unmodifiableMap(source)` vì view này vẫn quan sát backing map, và **khác** `new HashMap<>(source)` vì bản sao ấy vẫn sửa được.

Sử dụng đúng hợp đồng còn đòi hỏi chú ý `null`, **thứ tự duyệt không được bảo đảm**, **sao chép nông key/value**, **identity value-based** và **quy tắc đồng bộ** nếu nguồn được cập nhật bởi nhiều luồng.

## Tài liệu tham khảo chính thức

- [Java SE 27 — `Map.copyOf(Map)`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): kết quả unmodifiable, không phản ánh sửa đổi của nguồn sau khi tạo; từ Java 10.
- [Java SE 27 — `Map`, mục Unmodifiable Maps](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Map.html): các quy tắc về `null`, thứ tự duyệt, value-based và key/value mutable.
- [Java SE 27 — `Collections.unmodifiableMap`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)): view không cho sửa trực tiếp trên backing Map.
- [Java SE 27 — `HashMap`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/HashMap.html): mutable map, cho phép `null` key và values, không bảo đảm thứ tự iteration.
- [Java SE 27 — `LinkedHashMap`](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/LinkedHashMap.html): khi cần cấu trúc duy trì encounter order.
