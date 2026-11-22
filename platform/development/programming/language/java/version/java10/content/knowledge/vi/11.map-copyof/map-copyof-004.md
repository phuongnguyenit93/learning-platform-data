# Bản sao nông của khóa và giá trị với `Map.copyOf`

**Chủ đề:** `Map.copyOf` — Java 10 trở lên. Bài học giải thích chính xác điều gì được sao chép khi gọi `Map.copyOf(source)`, vì sao **cấu trúc ánh xạ** không còn sửa được nhưng **đối tượng khóa và giá trị** có thể vẫn thay đổi, và cách tạo một bản sao an toàn hơn khi map chứa dữ liệu mutable. Đây là kiến thức Java hiện còn áp dụng; các ví dụ hoàn chỉnh được kiểm tra với `javac --release 10`.

## 1. `Map.copyOf` cam kết những gì?

`Map.copyOf` là phương thức factory tĩnh được bổ sung trong Java 10. Nó nhận một `Map` và trả về **unmodifiable Map** chứa các ánh xạ khóa–giá trị của đầu vào tại thời điểm sao chép.

~~~java
Map<String, Integer> source = new HashMap<>();
source.put("java", 10);

Map<String, Integer> snapshot = Map.copyOf(source);
~~~

Đây là **đoạn mã minh họa trong một phương thức**, giả sử đã import `Map` và `HashMap`.

Hai kết quả quan trọng:

1. **Không thể sửa map trả về:** các thao tác cập nhật ánh xạ, ví dụ `put`, `remove`, `clear` hoặc `replace`, không được hỗ trợ. Với thao tác sửa thực sự trên map không sửa được, có thể nhận `UnsupportedOperationException`.
2. **Sửa ánh xạ trong `source` sau đó không làm thay đổi tập ánh xạ trong `snapshot`:** nếu gọi `source.put("other", 20)`, `snapshot` không tự xuất hiện khóa `"other"`.

Nhưng cam kết này **không có nghĩa mỗi khóa và mỗi giá trị đã được sao chép sâu**. Nếu `source` chứa đối tượng mutable, map kết quả vẫn có thể giữ **cùng tham chiếu** đến chính những đối tượng đó.

### Ba tầng phải phân biệt

| Tầng dữ liệu | `Map.copyOf` thực hiện gì? | Điều có thể còn thay đổi |
| --- | --- | --- |
| Tập cặp khóa–giá trị của map | Tạo kết quả logic không sửa được, tách khỏi thay đổi cấu trúc của source | Không thể thêm/xóa/thay entry qua kết quả |
| Đối tượng làm **khóa** | Giữ đối tượng khóa được cung cấp, không tự deep-copy | Nếu khóa mutable, trạng thái/`equals`/`hashCode` có thể đổi |
| Đối tượng làm **giá trị** | Giữ đối tượng giá trị được cung cấp, không tự deep-copy | Thuộc tính của value, list/map lồng trong value có thể bị sửa qua reference khác |

Nói cách khác, **unmodifiable map** là thuộc tính của cấu trúc ánh xạ ở tầng ngoài; nó không bảo đảm **deep immutability** của toàn bộ đồ thị object.

## 2. Một ví dụ ngắn: bản sao giữ cấu trúc, không đóng băng giá trị

Giả sử giá trị của map là danh sách quyền của người dùng:

~~~java
var permissions = new ArrayList<>(List.of("read"));

Map<String, List<String>> source = new HashMap<>();
source.put("alice", permissions);

Map<String, List<String>> copied = Map.copyOf(source);
~~~

Đây là **đoạn mã minh họa bên trong một phương thức**. Có hai loại thay đổi hoàn toàn khác nhau:

~~~java
source.put("bob", List.of("write")); // chỉ sửa cấu trúc source
permissions.add("admin");          // sửa đối tượng List dùng làm value
~~~

Sau đó:

- `copied.containsKey("bob")` vẫn là `false`, vì `Map.copyOf` đã giữ một tập ánh xạ riêng.
- `copied.get("alice")` vẫn trỏ đến **danh sách `permissions`**; nó có thể đã chứa thêm `"admin"`.
- `copied.put("carol", List.of("read"))` bị từ chối, nhưng `copied.get("alice").add("audit")` có thể thành công vì phương thức `add` được gọi trên **ArrayList làm value**, không trên map ngoài.

Điểm dễ sai nhất là nhầm **“không được `put` vào map”** với **“không được sửa bất cứ thứ gì truy cập qua map”**. Với `Map<K, V>`, `V` có thể là một cấu trúc dữ liệu mutable hoàn toàn độc lập.

## 3. Ví dụ chạy được: thay đổi source và value sau khi `copyOf`

Lưu đúng tên tệp **`MapCopyShallowValuesDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class MapCopyShallowValuesDemo {
    public static void main(String[] args) {
        var roles = new ArrayList<>(List.of("read"));
        Map<String, List<String>> source = new HashMap<>();
        source.put("alice", roles);
        Map<String, List<String>> snapshot = Map.copyOf(source);

        source.remove("alice");
        source.put("bob", List.of("write"));
        System.out.println("snapshot-size=" + snapshot.size());
        System.out.println("has-alice=" + snapshot.containsKey("alice"));
        System.out.println("has-bob=" + snapshot.containsKey("bob"));

        roles.add("admin");
        System.out.println("snapshot-roles=" + snapshot.get("alice"));
        System.out.println("same-value-ref=" + (snapshot.get("alice") == roles));

        try {
            snapshot.put("carol", List.of("read"));
        } catch (UnsupportedOperationException expected) {
            System.out.println("put=UnsupportedOperationException");
        }

        snapshot.get("alice").add("audit");
        System.out.println("after-inner-add=" + snapshot.get("alice"));
    }
}
~~~

Biên dịch và chạy bằng JDK hỗ trợ `--release 10`:

~~~bash
javac --release 10 MapCopyShallowValuesDemo.java
java MapCopyShallowValuesDemo
~~~

**Stdout chính xác:**

~~~text
snapshot-size=1
has-alice=true
has-bob=false
snapshot-roles=[read, admin]
same-value-ref=true
put=UnsupportedOperationException
after-inner-add=[read, admin, audit]
~~~

Phân tích theo thứ tự:

1. `snapshot` được tạo khi `source` chỉ có khóa `alice`. Sau `source.remove("alice")` và `source.put("bob", ...)`, bản sao vẫn có đúng một ánh xạ, giữ khóa `alice` và không có `bob`.
2. `roles.add("admin")` thay đổi object danh sách đã được đưa vào map trước khi sao chép. Vì `snapshot.get("alice") == roles` là `true`, giá trị trả về cũng thấy `admin`.
3. `snapshot.put(...)` gọi phương thức sửa trên map ngoài, vì vậy ném `UnsupportedOperationException`.
4. `snapshot.get("alice").add("audit")` sửa trực tiếp danh sách làm value. Danh sách ấy là `ArrayList` mutable, nên thao tác thành công; unmodifiable map không ngăn được.

**Hệ quả:** `Map.copyOf` là một *defensive copy* đối với **cấu trúc map**, chưa phải một bản sao bảo vệ trạng thái của các value mutable. Cần sao chép value riêng nếu muốn bất biến sâu hơn.

## 4. Khóa cũng được sao chép nông — nguy hiểm đặc biệt với `hashCode` và `equals`

Rủi ro với **key mutable** không chỉ là màn hình hiển thị tên khóa bị đổi. Hợp đồng map dựa vào `equals` và, trong nhiều implementation, `hashCode` để nhận diện và tìm kiếm khóa.

Giả sử dùng một đối tượng tự định nghĩa làm khóa:

~~~java
static final class Key {
    private String name;

    Key(String name) {
        this.name = name;
    }

    void rename(String next) {
        this.name = next;
    }

    @Override
    public int hashCode() {
        return java.util.Objects.hashCode(name);
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof Key
                && java.util.Objects.equals(name, ((Key) other).name);
    }
}
~~~

Đây là **đoạn khai báo lớp lồng** để giải thích, không phải chương trình độc lập. Nếu `name` thay đổi sau khi khóa đã được thêm vào map, kết quả `hashCode`/`equals` cũng có thể đổi. Điều đó vi phạm kỳ vọng về **khóa ổn định** và có thể làm tìm kiếm bằng `get`/`containsKey` cho kết quả bất ngờ. `Map.copyOf` **không tự chuyển khóa thành immutable key** để sửa sai thiết kế này.

### Ví dụ chạy được: reference của khóa vẫn là cùng object

Lưu **`MapCopyMutableKeyDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class MapCopyMutableKeyDemo {
    static final class Key {
        private String name;

        Key(String name) {
            this.name = name;
        }

        void rename(String next) {
            this.name = next;
        }

        String name() {
            return name;
        }

        @Override
        public int hashCode() {
            return Objects.hashCode(name);
        }

        @Override
        public boolean equals(Object obj) {
            return obj instanceof Key
                    && Objects.equals(name, ((Key) obj).name);
        }
    }

    public static void main(String[] args) {
        var key = new Key("team");
        Map<Key, Integer> source = new HashMap<>();
        source.put(key, 10);
        Map<Key, Integer> snapshot = Map.copyOf(source);

        var storedKey = snapshot.keySet().iterator().next();
        System.out.println("same-key-ref=" + (storedKey == key));
        System.out.println("key-before=" + storedKey.name());

        key.rename("renamed");
        System.out.println("key-after=" + storedKey.name());
        System.out.println("size=" + snapshot.size());
    }
}
~~~

Chạy:

~~~bash
javac --release 10 MapCopyMutableKeyDemo.java
java MapCopyMutableKeyDemo
~~~

**Stdout chính xác:**

~~~text
same-key-ref=true
key-before=team
key-after=renamed
size=1
~~~

Ví dụ cố ý **không gọi `get` sau khi đổi `hashCode`** để tránh phụ thuộc vào chi tiết bucket/index của implementation. Nó chứng minh hai điều ổn định: bản sao giữ cùng **reference đến khóa** và trạng thái khóa quan sát qua map thay đổi khi object được sửa. Hợp đồng `Map.copyOf` không bảo đảm rằng mutate key sau khi chèn là thao tác an toàn.

**Nguyên tắc thực hành:**

- Ưu tiên dùng khóa **immutable**, ví dụ `String`, `UUID`, các wrapper số hoặc lớp value object được thiết kế bất biến.
- Nếu khóa là object tự định nghĩa, những thuộc tính tham gia `equals` và `hashCode` phải **ổn định trong suốt thời gian object được sử dụng làm khóa**.
- Đừng nghĩ gọi `Map.copyOf` sẽ “đóng băng” field của khóa. Nó không tạo bản sao sâu và không vô hiệu hóa setter.
- Với key mutable bắt buộc phải có, thường nên chuyển sang một **key value object immutable** mới từ các thông tin cần định danh rồi xây map mới; chỉ sao chép map ngoài không giải quyết được.

## 5. So sánh `Map.copyOf` với các phương thức tạo map khác

| Cách tạo | Thay đổi cấu trúc qua kết quả | Thay đổi source có phản ánh ở kết quả? | Đối tượng key/value |
| --- | --- | --- | --- |
| `Map.copyOf(source)` (Java 10+) | Không hỗ trợ | Không phản ánh thay đổi ánh xạ của source về sau | Giữ tham chiếu key/value; sao chép nông |
| `Collections.unmodifiableMap(source)` | Không hỗ trợ qua wrapper | **Có thể phản ánh**, vì là view bọc source | Giữ tham chiếu của backing map |
| `new HashMap<>(source)` | Hỗ trợ (map mới mutable) | Không phản ánh thay đổi cấu trúc source về sau | Giữ tham chiếu key/value; sao chép nông |
| `Map.of("x", value)` (Java 9+) | Không hỗ trợ | Không có source map để quan sát | Giữ reference value được truyền vào |
| `Map.ofEntries(...)` (Java 9+) | Không hỗ trợ | Không có source map để quan sát | Không tự deep-copy object key/value |
| Map tự tạo từ key/value immutable đã sao chép | Phụ thuộc cách hoàn thiện kết quả | Có thể tách khỏi cả trạng thái lồng bên trong nếu thiết kế đúng | Do người viết chủ động quyết định mức copy |

**`Map.copyOf` có thể tái sử dụng đầu vào vốn đã là một map không sửa được thích hợp**, vì thế “copy” không phải lời hứa luôn cấp phát một object mới hoặc luôn có reference khác. Hợp đồng cần tin cậy là khả năng sửa đổi và nội dung ánh xạ, không phải `snapshot != source`.

Với `Collections.unmodifiableMap(source)`, caller không thể sửa thông qua wrapper, nhưng **ai còn giữ source mutable** vẫn có thể thay đổi dữ liệu hiện ra qua view. Khi cần snapshot không theo source, dùng `Map.copyOf` hoặc một bản sao phù hợp thay vì unmodifiable wrapper đơn thuần.

### Ví dụ kiểm tra view và snapshot

Đoạn mã dưới đây giả sử nằm trong một phương thức và đã import `Map`, `HashMap`, `Collections`:

~~~java
Map<String, String> source = new HashMap<>();
source.put("a", "one");

Map<String, String> view = Collections.unmodifiableMap(source);
Map<String, String> snapshot = Map.copyOf(view);

source.put("b", "two");

System.out.println(view.size());     // 2
System.out.println(snapshot.size()); // 1
~~~

`view` là live view; `snapshot` giữ ánh xạ tại lúc sao chép. Vì các value là `String` immutable, ví dụ này cũng không có rủi ro sửa trạng thái bên trong value.

## 6. Cách sao chép sâu hơn cho map chứa danh sách giá trị

Một cách triển khai hay gặp là `Map<String, List<String>>`: khóa `String` vốn immutable, nhưng value có thể là một `ArrayList` mutable.

Nếu chỉ làm:

~~~java
Map<String, List<String>> result = Map.copyOf(source);
~~~

thì chỉ khóa và reference của danh sách được lưu vào map mới; **list bên trong vẫn là cùng object**. Muốn caller không thể sửa danh sách lồng nhau và không phản ánh việc sửa list nguồn, ta cần sao chép mỗi list trước khi gọi `Map.copyOf`.

### Thuật toán theo hai tầng

~~~java
static Map<String, List<String>> freeze(Map<String, ? extends List<String>> input) {
    Map<String, List<String>> prepared = new HashMap<>();

    for (Map.Entry<String, ? extends List<String>> e : input.entrySet()) {
        prepared.put(e.getKey(), List.copyOf(e.getValue()));
    }

    return Map.copyOf(prepared);
}
~~~

Đây là **đoạn khai báo phương thức**; cần import `Map`, `HashMap` và `List`. Bản sao được tạo theo hai tầng:

1. **Tầng danh sách value:** `List.copyOf(e.getValue())` chụp cấu trúc list và từ chối sửa list trả về.
2. **Tầng map:** `Map.copyOf(prepared)` tạo map không sửa được từ các list đã được sao chép.

Vì key là `String` và phần tử list cũng là `String` immutable, kết quả ví dụ có thể giữ ổn định cả **tập ánh xạ lẫn nội dung chuỗi**. Nếu key hoặc phần tử list là object mutable, cần thêm bước sao chép/chuyển đổi phù hợp; gọi `copyOf` ở hai tầng vẫn **không tự trở thành deep-copy tổng quát**.

### Chương trình chạy được: freeze map và list lồng nhau

Lưu **`MapCopyNestedSafeDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

public class MapCopyNestedSafeDemo {
    static Map<String, List<String>> freeze(Map<String, ? extends List<String>> input) {
        Map<String, List<String>> prepared = new HashMap<>();

        for (Map.Entry<String, ? extends List<String>> e : input.entrySet()) {
            prepared.put(e.getKey(), List.copyOf(e.getValue()));
        }

        return Map.copyOf(prepared);
    }

    public static void main(String[] args) {
        var roles = new ArrayList<>(List.of("read"));
        Map<String, List<String>> source = new HashMap<>();
        source.put("alice", roles);

        Map<String, List<String>> frozen = freeze(source);
        roles.add("write");
        source.put("bob", List.of("read"));

        System.out.println("frozen-roles=" + frozen.get("alice"));
        System.out.println("frozen-size=" + frozen.size());

        try {
            frozen.get("alice").add("admin");
        } catch (UnsupportedOperationException expected) {
            System.out.println("nested-add=UnsupportedOperationException");
        }

        try {
            frozen.put("bob", List.of("read"));
        } catch (UnsupportedOperationException expected) {
            System.out.println("outer-put=UnsupportedOperationException");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 10 MapCopyNestedSafeDemo.java
java MapCopyNestedSafeDemo
~~~

Stdout:

~~~text
frozen-roles=[read]
frozen-size=1
nested-add=UnsupportedOperationException
outer-put=UnsupportedOperationException
~~~

`roles.add("write")` thay đổi list gốc, nhưng list đã `List.copyOf` trong `frozen` không đổi. `source.put("bob", ...)` cũng không thay đổi tập ánh xạ của `frozen`. Cả hai tầng đều từ chối thao tác sửa qua kết quả.

Vì danh sách có phần tử `String`, ví dụ này đủ đơn giản để minh họa một *immutable data snapshot* theo ngữ nghĩa domain. Tuy nhiên phương thức `freeze` ở đây **cố ý dành cho `Map<String, List<String>>`**; đừng quảng bá nó như thuật toán deep-copy cho mọi `Map<K, V>`.

## 7. Sử dụng `Map.copyOf` trong constructor và kiểu trả về

Khi thiết kế một object có map trạng thái ban đầu, pattern sau giúp chặn sửa **cấu trúc map** từ caller:

~~~java
public final class Settings {
    private final Map<String, String> entries;

    public Settings(Map<String, String> input) {
        this.entries = Map.copyOf(input);
    }

    public Map<String, String> entries() {
        return entries;
    }
}
~~~

Đây là **định nghĩa class minh họa**, cần import `java.util.Map` nếu lưu thành file. Vì key và value đều là `String` immutable, caller không sửa được cấu trúc map và không sửa được trạng thái bên trong các chuỗi. Getter có thể trả trực tiếp field đã là map không sửa được; không cần gọi `Map.copyOf(entries)` ở mỗi lần đọc chỉ để “copy thêm”.

Nếu giá trị là một object mutable như `UserProfile` có setter, constructor `Map.copyOf(input)` **chưa bảo vệ trạng thái của value**. Nên chuyển sang immutable data transfer object hoặc copy dữ liệu cần thiết của từng value trước khi lưu. Đặc biệt cẩn thận khi đối tượng này giữ một map dùng làm cache, danh sách quyền, cấu hình, hay model trả về API.

### Trạng thái nội bộ tiếp tục sửa sau constructor

Đôi khi class có một `HashMap` mutable vì cần nhận cập nhật:

~~~java
private final Map<String, String> values = new HashMap<>();

public void putValue(String key, String value) {
    values.put(key, value);
}

public Map<String, String> snapshot() {
    return Map.copyOf(values);
}
~~~

Đây là **các thành viên minh họa bên trong một class**. `snapshot()` đưa cho caller một bản sao cấu trúc không sửa được tại lúc gọi; map nội bộ vẫn có thể thay đổi qua `putValue`. Với `String` immutable, snapshot cũ không bị tác động bởi việc cập nhật các entry tiếp theo.

Đặt tên rõ là `snapshot()` khi muốn mô tả hành vi “ảnh chụp theo thời điểm”, khác với `Collections.unmodifiableMap(values)` là một **view có thể thay đổi nội dung quan sát theo thời gian** khi backing map được sửa.

**Lưu ý đa luồng:** nếu source `HashMap` bị sửa đồng thời mà không được đồng bộ, `Map.copyOf(source)` không tự bảo đảm snapshot nguyên tử hoặc an toàn luồng. Dùng cơ chế đồng bộ hoặc sở hữu state phù hợp trước khi tạo bản sao.

## 8. Null, duplicate key và các lỗi cần phân biệt

`Map.copyOf` có điều kiện đầu vào riêng:

- `source == null` gây `NullPointerException`.
- Map nguồn chứa **khóa null** gây `NullPointerException` khi sao chép.
- Map nguồn chứa **giá trị null** cũng gây `NullPointerException` khi sao chép.
- Một `Map` hợp lệ đã chỉ có **một mapping cho mỗi khóa theo `equals`**; vì thế lỗi “duplicate key trong một `Map.copyOf` đầu vào” không giống `Map.of("a", 1, "a", 2)`. Với `Map.of`, khóa trùng làm phát sinh `IllegalArgumentException` khi tạo.
- Với map kết quả không sửa được, các thao tác cập nhật như `put` không được hỗ trợ. Nhưng `UnsupportedOperationException` khác với `NullPointerException` lúc **tạo map từ dữ liệu không hợp lệ**.

### Chương trình chạy được: ràng buộc null và view

Lưu **`MapCopyConstraintsDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;
import java.util.Collections;

public class MapCopyConstraintsDemo {
    static void expectNullPointer(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + "=allowed");
        } catch (NullPointerException expected) {
            System.out.println(label + "=NullPointerException");
        }
    }

    public static void main(String[] args) {
        Map<String, String> withNullValue = new HashMap<>();
        withNullValue.put("key", null);
        expectNullPointer("null-value", () -> Map.copyOf(withNullValue));

        Map<String, String> withNullKey = new HashMap<>();
        withNullKey.put(null, "value");
        expectNullPointer("null-key", () -> Map.copyOf(withNullKey));

        expectNullPointer("null-source", () -> Map.copyOf(null));

        Map<String, String> source = new HashMap<>();
        source.put("a", "one");
        Map<String, String> live = Collections.unmodifiableMap(source);
        Map<String, String> snapshot = Map.copyOf(live);

        source.put("b", "two");
        System.out.println("live-size=" + live.size());
        System.out.println("snapshot-size=" + snapshot.size());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 10 MapCopyConstraintsDemo.java
java MapCopyConstraintsDemo
~~~

Kết quả:

~~~text
null-value=NullPointerException
null-key=NullPointerException
null-source=NullPointerException
live-size=2
snapshot-size=1
~~~

Dùng `HashMap` làm nguồn vì implementation này có thể chứa null key/value; `Map.copyOf` không được phép chấp nhận các entry null đó. Hai dòng cuối đồng thời xác nhận `unmodifiableMap` là view, trong khi bản sao từ `Map.copyOf` không phản ánh việc thêm ánh xạ sau đó.

## 9. Vì sao không được suy ra “immutable” từ tên biến hoặc kiểu trả về?

Các khai báo sau **không tương đương** về mức bảo vệ trạng thái:

~~~java
final Map<String, List<String>> field = source;
Map<String, List<String>> shallow = Map.copyOf(source);
Map<String, List<String>> deepEnough = freeze(source);
~~~

Đây là **đoạn minh họa bên trong phương thức**; `freeze` là hàm ở phần 6. Ý nghĩa:

- `final` chỉ ngăn gán lại biến `field`; bản thân map và value có thể còn mutable.
- `shallow` bảo vệ cấu trúc map ngoài nhưng các list value còn được tham chiếu trực tiếp.
- `deepEnough` trong ví dụ tạo bản sao cấu trúc map **và** list value, với giả định key và phần tử là `String` immutable.

Việc khai báo kiểu trả về là `Map<K, V>` cũng không nói rằng caller có được `put` hay không. `Map` là interface có các thao tác sửa đổi *optional*. Cần ghi rõ hợp đồng như “returns an unmodifiable snapshot”. Ngược lại, `Collections.unmodifiableMap` không phải snapshot dù tên có “unmodifiable”.

### Khi khóa hoặc giá trị là object mutable

Đừng cố viết một hàm “deepCopyMap” chỉ bằng:

~~~java
return Map.copyOf(original);
~~~

và khẳng định đã có deep-copy. Với đối tượng mutable, bạn phải quyết định **ngữ nghĩa copy cụ thể**: sao chép field nào, xử lý nested collection ra sao, có cần giữ identity không, và làm thế nào để khóa có `equals`/`hashCode` ổn định. Một immutable value object hoặc DTO có thể là lựa chọn rõ ràng hơn việc sao chép tùy tiện mọi thứ.

Nếu key là `String` nhưng value là `List<User>` mà `User` mutable, `Map.copyOf` + `List.copyOf` chỉ đóng băng **hai tầng collection**; các `User` vẫn có thể bị sửa. Khi cần trạng thái thực sự bất biến, phải chuyển mỗi `User` sang một giá trị immutable hoặc sao chép phần dữ liệu cần thiết của mỗi phần tử.

## 10. Các nhầm lẫn thường gặp và cách tránh

| Nhầm lẫn | Thực tế | Cách xử lý |
| --- | --- | --- |
| “`Map.copyOf` sao chép sâu cả key và value.” | Chỉ bảo vệ cấu trúc ánh xạ; các object key/value vẫn được tham chiếu | Copy từng tầng và dùng value object immutable nếu cần |
| “Giá trị là `ArrayList` nhưng không thể thêm vì map unmodifiable.” | `snapshot.get(key).add(...)` vẫn có thể sửa list nếu value là mutable list | `List.copyOf` cho value trước khi `Map.copyOf` map ngoài |
| “Sửa tên key không ảnh hưởng map đã `copyOf`.” | Key mutable vẫn là cùng object; thay đổi `equals`/`hashCode` có thể phá tra cứu | Dùng khóa immutable, trạng thái định danh ổn định |
| “`Map.copyOf` luôn tạo object mới.” | Có thể tận dụng unmodifiable input phù hợp | Kiểm tra hành vi hợp đồng, không dựa `==` |
| “`Collections.unmodifiableMap` là snapshot.” | Đây là view của backing map | Dùng `Map.copyOf` khi cần tách khỏi thay đổi source |
| “`new HashMap<>(source)` cũng là unmodifiable snapshot.” | HashMap mới thường có thể sửa, nhưng vẫn là copy nông | Dùng `Map.copyOf` sau bước xử lý nếu cần không sửa được |
| “Map nguồn chứa null thì `copyOf` sẽ bỏ qua.” | Ném `NullPointerException` | Validate/chuẩn hóa dữ liệu trước khi sao chép |
| “`Map.copyOf` tự đồng bộ khi source đang thay đổi.” | Không có cam kết snapshot nguyên tử với mutable source không đồng bộ | Quản lý đồng bộ/sở hữu state riêng |
| “Thứ tự in `Map.copyOf` luôn giống source.” | Các unmodifiable map factory không bảo đảm thứ tự duyệt | Không dùng thứ tự iteration làm hợp đồng; nếu cần thứ tự, thiết kế API phù hợp |
| “Bắt `UnsupportedOperationException` rồi tiếp tục là sửa được dữ liệu.” | Bỏ qua exception không thực hiện thao tác nghiệp vụ | Sửa đúng collection mutable thuộc quyền sở hữu, hoặc tạo bản sao mutable mới |

**Về thứ tự:** Những chương trình ví dụ cố ý in `size`, `containsKey` và value theo khóa thay vì in trực tiếp một map có nhiều entry rồi giả định thứ tự cụ thể. Không dựa vào thứ tự iteration của `Map.copyOf` để làm logic ứng dụng.

## 11. Checklist kiểm thử cho một API dùng `Map.copyOf`

Khi review một constructor, getter hoặc service trả map, đặt các câu hỏi:

1. **Tầng map:** sau khi lấy snapshot, thêm/xóa/thay entry ở source có làm thay đổi `size`, `containsKey`, `get` của snapshot không?
2. **Khả năng sửa qua kết quả:** `put`, `remove`, `clear` từ API trả về có bị từ chối không?
3. **Tầng value:** nếu value là `List`, `Map` hoặc domain object mutable, sửa value ở nơi khác có hiện ra qua snapshot không? Nếu không mong muốn, đã copy/value-freeze chưa?
4. **Tầng key:** có khóa nào chứa field mutable tham gia `equals` hoặc `hashCode` không? Nếu có, thay bằng khóa ổn định.
5. **Null:** đầu vào có thể chứa key/value `null` không? Nếu có, validator phải xử lý trước `Map.copyOf`.
6. **Sở hữu dữ liệu:** caller nào còn giữ reference đến source và nested object? Ai có quyền sửa các object đó?
7. **Đa luồng:** lúc tạo snapshot source có thể đang được sửa từ thread khác không? Có đồng bộ phù hợp không?
8. **Hợp đồng công khai:** tên method và tài liệu có nói rõ unmodifiable snapshot, hay chỉ viết chung chung “read-only map”?
9. **Tương thích Java:** `Map.copyOf` yêu cầu Java 10 trở lên; dự án Java 17+ dùng bình thường, không cần API thay thế cũ.
10. **Giá trị bất biến sâu:** nếu cấu trúc lồng nhiều lớp, đã làm rõ đến tầng nào là immutable và đến tầng nào chỉ là shallow-copy chưa?

Một test chỉ xác nhận `snapshot.put(...)` ném `UnsupportedOperationException` là **chưa đủ** để khẳng định không còn aliasing. Phải kiểm thử cả **source thay đổi cấu trúc** lẫn **key/value mutable thay đổi trạng thái**.

## 12. Bài tập và đáp án

**Câu 1.** Có mã:

~~~java
Map<String, StringBuilder> source = new HashMap<>();
var value = new StringBuilder("A");
source.put("key", value);
var copied = Map.copyOf(source);
value.append("B");
~~~

Giả sử ở trong phương thức, `copied.get("key").toString()` cho kết quả gì?

**Câu 2.** `Map.copyOf(source)` đã hoàn thành, sau đó `source.clear()`. Việc này có làm xóa các entry trong kết quả `copyOf` không?

**Câu 3.** Với `Map<String, List<String>>` và các list value có thể được sửa, vì sao chỉ dùng `Map.copyOf` không đủ? Cần thêm bước gì?

**Câu 4.** Một key có `hashCode` dựa vào trường `name` và caller có thể đổi `name` qua setter. Dùng `Map.copyOf` có sửa được rủi ro đó không?

**Câu 5.** `Collections.unmodifiableMap(source)` khác `Map.copyOf(source)` ở điều gì nếu `source` vẫn còn mutable?

**Câu 6.** `Map.copyOf` gặp map nguồn có `null` key hoặc value sẽ làm gì?

**Câu 7.** Khi có `Map.copyOf(Map<String, List<User>>)` và mỗi `User` có setter, gọi thêm `List.copyOf` cho các value đã đủ bảo đảm immutable sâu chưa?

**Đáp án:**

1. `"AB"` — cùng reference `StringBuilder`; copy map không đóng băng nội dung value.
2. Không — thay đổi cấu trúc source sau đó không làm mất ánh xạ ở bản sao.
3. Sao chép từng list value bằng `List.copyOf` (hoặc chuyển sang dữ liệu immutable tương đương), rồi mới `Map.copyOf` map ngoài; với phần tử `String` immutable, cách này bảo vệ đủ các tầng của ví dụ.
4. Không — `copyOf` giữ key object; khóa có trạng thái dùng cho `equals`/`hashCode` cần ổn định.
5. `unmodifiableMap` là live view có thể phản ánh thay đổi của source; `copyOf` tạo snapshot ánh xạ.
6. Ném `NullPointerException`.
7. Chưa — `List.copyOf` cũng là sao chép nông đối với các phần tử `User`; cần chuyển/copy mỗi `User` sang dạng bất biến nếu đó là yêu cầu.

## 13. Tài liệu API và ngôn ngữ đang áp dụng

- **Oracle Javadoc — `Map.copyOf`:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)
- **Oracle Javadoc — `List.copyOf`:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)
- **Oracle Javadoc — `Collections.unmodifiableMap`:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html#unmodifiableMap(java.util.Map)
- **Oracle Javadoc — `HashMap`:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/HashMap.html
- **Java SE collections — Unmodifiable Maps:** https://docs.oracle.com/en/java/javase/21/core/creating-immutable-lists-sets-and-maps.html
- **JEP 286 — Local-Variable Type Inference (Java 10):** https://openjdk.org/jeps/286

**Kết luận:** `Map.copyOf` chặn sửa đổi **các ánh xạ bên ngoài**, nhưng nó **giữ reference tới từng key và value**. Nếu khóa hoặc giá trị mutable, map trả về chưa phải một ảnh chụp bất biến sâu. Muốn dữ liệu an toàn tại ranh giới API, hãy dùng khóa immutable, quyết định rõ mức copy của value và sao chép từng tầng cần thiết trước khi tạo map unmodifiable.