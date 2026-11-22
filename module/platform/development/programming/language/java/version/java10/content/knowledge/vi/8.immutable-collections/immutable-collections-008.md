# UnsupportedOperationException và các thao tác sửa đổi trên Collection chỉ đọc

**Chủ đề:** Collection chỉ đọc — Java 10 trở lên. Bài học giải thích vì sao nhiều collection có thể đọc, duyệt và truyền qua API `List`/`Set`/`Map` nhưng lại từ chối `add`, `remove`, `put`, `set` hoặc các thao tác thay đổi khác bằng `UnsupportedOperationException`. Các quy tắc này vẫn áp dụng trong Java hiện đại. Mọi chương trình độc lập trong bài đều có thể biên dịch với chế độ ngôn ngữ Java 10 trên JDK hỗ trợ `--release 10`.

## 1. `UnsupportedOperationException` có ý nghĩa gì?

`UnsupportedOperationException` là một **unchecked exception** (kế thừa `RuntimeException`) báo rằng đối tượng không hỗ trợ thao tác vừa được gọi. Trong Collections Framework, một số thao tác sửa đổi được thiết kế là **optional operations**: interface như `List`, `Set` hay `Map` mô tả chúng, nhưng một implementation cụ thể có thể không cho phép thực hiện.

Ví dụ, kiểu khai báo `List<String>` cho biết đối tượng hỗ trợ giao diện `List`, **không bảo đảm danh sách có thể thay đổi**:

~~~java
List<String> names = List.of("An", "Binh");
System.out.println(names.get(0)); // An
names.add("Chi");                  // ném UnsupportedOperationException
~~~

Đây là **đoạn minh họa bên trong phương thức**. Dòng `add` biên dịch được vì `List` khai báo phương thức đó; nhưng khi chạy, đối tượng do `List.of` tạo ra là **unmodifiable list** và từ chối thay đổi. Lỗi xảy ra tại runtime do hợp đồng của instance, không phải do Java thiếu khai báo phương thức.

**Phân biệt ba vấn đề:**

- **Không biên dịch được:** kiểu tĩnh không có method, hoặc kiểu tham số không phù hợp. Ví dụ `Collection<String> c` không có `c.set(0, "x")` vì `set` là phương thức của `List`.
- **Biên dịch được nhưng ném `UnsupportedOperationException`:** method tồn tại, nhưng implementation không hỗ trợ thao tác. Ví dụ `List.of(...).add(...)`.
- **Biên dịch được nhưng ném ngoại lệ khác:** đầu vào sai quy tắc, như `List.of((String) null)` ném `NullPointerException`, hoặc `Set.of("a", "a")` ném `IllegalArgumentException`. Không được quy mọi lỗi collection về `UnsupportedOperationException`.

Các phương thức đọc như `size`, `get`, `contains`, `iterator().next()` và phép duyệt không mặc nhiên là thao tác sửa đổi; chúng vẫn dùng được khi phù hợp với giao diện.

## 2. Những collection không cho phép sửa đổi trong Java hiện đại

| Cách tạo/nhận collection | Ý nghĩa | Các thay đổi cấu trúc/nội dung bị từ chối |
| --- | --- | --- |
| `List.of(...)` (Java 9+) | List không sửa được, không nhận `null` | `add`, `addAll`, `remove`, `clear`, `set`, `sort`, `replaceAll`, `removeIf`… |
| `Set.of(...)` (Java 9+) | Set không sửa được, không nhận `null`, không cho phần tử trùng trong lời gọi factory | `add`, `remove`, `clear`, `removeIf`… |
| `Map.of(...)` / `Map.ofEntries(...)` (Java 9+) | Map không sửa được; khóa và giá trị không nhận `null`, khóa không trùng | `put`, `remove`, `clear`, `replace`, `compute`, `merge`… |
| `List.copyOf(source)` / `Set.copyOf(source)` / `Map.copyOf(source)` (Java 10+) | Tạo kết quả không sửa được từ nguồn; thực hiện sao chép cấu trúc khi cần | Các thao tác thay đổi trên kết quả |
| `stream.collect(Collectors.toUnmodifiableList())` cùng các collector tương ứng (Java 10+) | Thu thập stream thành collection không sửa được | Các thao tác thay đổi trên kết quả |
| `Collections.unmodifiableList(source)`, cùng wrapper cho `Set`/`Map` | **View không sửa được** bọc collection gốc; không tự tạo snapshot độc lập | Thao tác sửa qua wrapper bị từ chối |
| `Arrays.asList(array)` | List có **kích thước cố định**, được backing bởi array | `add`/`remove` bị từ chối, nhưng `set` hợp lệ |

Cú pháp `List.of`, `Set.of`, `Map.of` có từ Java 9; `List.copyOf`, `Set.copyOf`, `Map.copyOf` và các collector `toUnmodifiable...` có từ Java 10. Chúng vẫn là API hiện hành.

**Lưu ý phiên bản mới hơn:** `Stream.toList()` (Java 16+) cũng trả về một list không sửa được. Đây là API thường gặp trong dự án Java 17+ nhưng **không có trong Java 10**; các ví dụ chạy được dưới `--release 10` bên dưới sử dụng `Collectors.toUnmodifiableList()`.

Một điều dễ nhầm: `Collectors.toList()` **không bảo đảm** kết quả luôn là list có thể sửa đổi theo hợp đồng API. Nếu cần chắc chắn một `ArrayList` có thể sửa, có thể dùng `Collectors.toCollection(ArrayList::new)`. Nếu cần kết quả không sửa được, dùng `toUnmodifiableList()` hoặc `Stream.toList()` ở mức Java hỗ trợ.

## 3. Các phương thức sửa đổi nào thường ném lỗi?

### Trên `List`

- **Thêm hoặc xóa:** `add`, `addAll`, `remove(index)`, `remove(object)`, `removeAll`, `retainAll`, `clear`.
- **Thay nội dung tại vị trí:** `set(index, value)`; dù kích thước không đổi, đây vẫn là thao tác sửa đổi.
- **Thay đổi hàng loạt:** `replaceAll`, `sort`, `removeIf`.
- **Sửa thông qua iterator/view:** `Iterator.remove()`, `ListIterator.add/set/remove` hoặc cố thay đổi qua `subList` cũng phải tuân theo hợp đồng của collection nguồn.

### Trên `Set`

`add`, `addAll`, `remove`, `removeAll`, `retainAll`, `clear` và `removeIf` đều là các thao tác có thể không được hỗ trợ. `Set.of` giữ tính không sửa được của tập hợp, kể cả khi người gọi biết khóa/phần tử và chỉ muốn xóa một phần tử.

### Trên `Map`

`put`, `putAll`, `remove`, `clear`, `replace`, `replaceAll`, `compute`, `computeIfAbsent`, `computeIfPresent`, `merge` và những cách sửa qua entry hoặc view đều phải tuân theo hợp đồng của Map. Với `Map.of` và `Map.copyOf`, không được dựa vào các thao tác này để thay đổi ánh xạ.

**Trường hợp “không thay đổi gì” cũng không an toàn để giả định:** Java cho phép một optional operation bị từ chối ngay cả khi lời gọi tưởng như không tạo khác biệt (ví dụ xóa phần tử không tồn tại hoặc xóa danh sách đã trống). Một số implementation có thể không ném trong một số tình huống không làm thay đổi dữ liệu. Vì vậy đừng dùng phép thử `remove("missing")` hay `clear()` trên danh sách trống để suy ra collection có thể sửa đổi. Hãy dựa vào **hợp đồng API cụ thể**.

## 4. Chương trình thực hành: các thao tác ném `UnsupportedOperationException`

Lưu chương trình độc lập thành **`ReadOnlyOperationsDemo.java`**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class ReadOnlyOperationsDemo {
    static void expectUnsupported(String operation, Runnable action) {
        try {
            action.run();
            System.out.println(operation + " -> succeeded");
        } catch (UnsupportedOperationException expected) {
            System.out.println(operation + " -> UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        List<String> names = List.of("An", "Binh");
        expectUnsupported("List.of.add", () -> names.add("Chi"));
        expectUnsupported("List.of.set", () -> names.set(0, "Chi"));
        expectUnsupported("List.of.remove", () -> names.remove("An"));
        expectUnsupported("List.of.clear", names::clear);
        expectUnsupported("List.of.addAll", () -> names.addAll(List.of("Chi")));
        expectUnsupported("List.of.replaceAll", () -> names.replaceAll(String::toUpperCase));
        expectUnsupported("List.of.sort", () -> names.sort(Comparator.reverseOrder()));
        expectUnsupported("List.of.removeIf", () -> names.removeIf("An"::equals));

        Set<String> tags = Set.of("core", "api");
        expectUnsupported("Set.of.add", () -> tags.add("new"));
        expectUnsupported("Set.of.remove", () -> tags.remove("core"));

        Map<String, Integer> scores = Map.of("java", 10);
        expectUnsupported("Map.of.put", () -> scores.put("java", 20));
        expectUnsupported("Map.of.remove", () -> scores.remove("java"));

        List<String> copy = List.copyOf(List.of("A", "B"));
        expectUnsupported("List.copyOf.set", () -> copy.set(0, "C"));

        List<String> collected = Stream.of("x", "y")
                .collect(Collectors.toUnmodifiableList());
        expectUnsupported("toUnmodifiableList.add", () -> collected.add("z"));

        System.out.println("original=" + names);
    }
}
~~~

Biên dịch và chạy bằng JDK có hỗ trợ chế độ nguồn Java 10:

~~~bash
javac --release 10 ReadOnlyOperationsDemo.java
java ReadOnlyOperationsDemo
~~~

**Stdout chính xác:**

~~~text
List.of.add -> UnsupportedOperationException
List.of.set -> UnsupportedOperationException
List.of.remove -> UnsupportedOperationException
List.of.clear -> UnsupportedOperationException
List.of.addAll -> UnsupportedOperationException
List.of.replaceAll -> UnsupportedOperationException
List.of.sort -> UnsupportedOperationException
List.of.removeIf -> UnsupportedOperationException
Set.of.add -> UnsupportedOperationException
Set.of.remove -> UnsupportedOperationException
Map.of.put -> UnsupportedOperationException
Map.of.remove -> UnsupportedOperationException
List.copyOf.set -> UnsupportedOperationException
toUnmodifiableList.add -> UnsupportedOperationException
original=[An, Binh]
~~~

Ở đây `expectUnsupported` chỉ dùng để **minh họa và kiểm chứng** hành vi của API. Trong mã ứng dụng, đừng dựa vào việc bắt ngoại lệ rồi tiếp tục thử sửa một collection chỉ đọc. Nên chọn cấu trúc dữ liệu đúng yêu cầu ngay từ đầu hoặc tạo một bản sao có thể sửa.

**Điểm cần nhớ:** `set`, `sort`, `replaceAll` không thêm/xóa phần tử nhưng vẫn thay đổi danh sách. Vì vậy một **unmodifiable list** cũng từ chối những thao tác này. `Map.put` thay giá trị của khóa đã tồn tại cũng là sửa đổi và bị từ chối.

## 5. `Collections.unmodifiableList` là view, `List.copyOf` là bản chụp cấu trúc

Hai cách tạo collection đọc được nhưng không thể sửa qua kết quả là:

~~~java
var source = new ArrayList<>(List.of("A", "B"));

List<String> view = Collections.unmodifiableList(source);
List<String> snapshot = List.copyOf(source);
~~~

- `view` là một **unmodifiable view** bọc `source`. Nếu người khác vẫn giữ reference tới `source` và thay đổi nó, nội dung nhìn thấy qua `view` có thể thay đổi theo. Cố sửa **qua `view`** gây `UnsupportedOperationException`.
- `snapshot` lấy một **unmodifiable collection** từ nội dung `source` tại thời điểm tạo. Trong ví dụ này, việc thay đổi cấu trúc `source` sau đó không thêm, xóa hoặc thay vị trí phần tử của `snapshot`.
- `List.copyOf` có thể **tái sử dụng** đối tượng đầu vào nếu đầu vào vốn đã là danh sách không sửa được phù hợp; không được giả định luôn tạo object mới hay so sánh tham chiếu bằng `==`.
- Cả hai cách đều **không deep-copy** các phần tử có thể thay đổi. Nếu phần tử là một object mutable được tham chiếu từ nhiều nơi, thay đổi bên trong object đó vẫn có thể quan sát qua kết quả.

### Chương trình kiểm chứng view, snapshot và danh sách cố định kích thước

Lưu tệp **`ViewsAndCopiesDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;

public class ViewsAndCopiesDemo {
    static void expectUnsupported(String name, Runnable action) {
        try {
            action.run();
            System.out.println(name + " -> succeeded");
        } catch (UnsupportedOperationException expected) {
            System.out.println(name + " -> UnsupportedOperationException");
        }
    }

    public static void main(String[] args) {
        var source = new ArrayList<>(List.of("A", "B"));
        List<String> view = Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);

        System.out.println("before-view=" + view);
        System.out.println("before-copy=" + snapshot);
        expectUnsupported("view.add", () -> view.add("X"));

        source.set(0, "Z");
        source.add("C");
        System.out.println("after-view=" + view);
        System.out.println("after-copy=" + snapshot);

        String[] raw = {"red", "blue"};
        List<String> fixed = Arrays.asList(raw);
        fixed.set(0, "green");
        System.out.println("array-first=" + raw[0]);
        expectUnsupported("fixed.add", () -> fixed.add("extra"));
        expectUnsupported("fixed.remove", () -> fixed.remove(0));

        StringBuilder mutable = new StringBuilder("x");
        var originals = new ArrayList<StringBuilder>();
        originals.add(mutable);
        List<StringBuilder> shallowCopy = List.copyOf(originals);
        mutable.append("y");
        originals.clear();

        System.out.println("copied-element=" + shallowCopy.get(0));
        System.out.println("copied-size=" + shallowCopy.size());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 10 ViewsAndCopiesDemo.java
java ViewsAndCopiesDemo
~~~

**Stdout chính xác:**

~~~text
before-view=[A, B]
before-copy=[A, B]
view.add -> UnsupportedOperationException
after-view=[Z, B, C]
after-copy=[A, B]
array-first=green
fixed.add -> UnsupportedOperationException
fixed.remove -> UnsupportedOperationException
copied-element=xy
copied-size=1
~~~

Giải thích:

1. Lời gọi `view.add("X")` thất bại, nhưng `source.set(...)` và `source.add(...)` vẫn được vì `source` là `ArrayList` có thể sửa. `view` phản ánh dữ liệu `[Z, B, C]`.
2. `snapshot` không bị ảnh hưởng bởi việc sửa cấu trúc `source` sau khi sao chép, nên vẫn là `[A, B]`.
3. `Arrays.asList(raw)` tạo list có **kích thước cố định** dựa trên mảng. `set(0, "green")` được phép và cập nhật mảng `raw`; `add`/`remove` bị từ chối. Vì vậy **fixed-size** không đồng nghĩa **unmodifiable**.
4. `shallowCopy` giữ phần tử `StringBuilder` cùng tham chiếu. Thay đổi từ `"x"` thành `"xy"` vẫn được nhìn thấy trong danh sách không sửa được, trong khi `originals.clear()` không làm giảm số phần tử của `shallowCopy`.

Nếu muốn snapshot **không thay đổi cả nội dung bên trong phần tử**, phải tạo bản sao sâu phù hợp từng kiểu (hoặc sử dụng phần tử immutable) trước khi đưa vào collection; `List.copyOf` không làm việc đó.

## 6. Khi nào ngoại lệ KHÁC `UnsupportedOperationException` xuất hiện?

Factory collection có những ràng buộc đầu vào riêng. Việc tạo thất bại **không phải thao tác sửa một collection đã tồn tại**.

| Tình huống | Kết quả | Vì sao |
| --- | --- | --- |
| `List.of((String) null)` | `NullPointerException` | Factory `List.of` không chấp nhận phần tử `null` |
| `Set.of("a", "a")` | `IllegalArgumentException` | Factory `Set.of` không chấp nhận phần tử trùng nhau |
| `Map.of("a", 1, "a", 2)` | `IllegalArgumentException` | Factory `Map.of` không chấp nhận khóa trùng |
| `Map.of("a", null)` | `NullPointerException` | Factory `Map.of` không nhận `null` làm key/value |
| `List.copyOf(Arrays.asList("a", null))` | `NullPointerException` | Bản sao không sửa được của `List.copyOf` không nhận phần tử `null` |
| `Collectors.toUnmodifiableList()` nhận stream có `null` | `NullPointerException` | Collector này không chấp nhận phần tử `null` |
| `Set.copyOf(List.of("a", "a", "b"))` | Tạo set có 2 phần tử | `Set.copyOf` loại phần tử trùng từ nguồn thay vì bắt buộc ném như `Set.of` |
| `list.get(index)` với index ngoài giới hạn | `IndexOutOfBoundsException` | Sai vị trí truy cập, không liên quan khả năng sửa |
| `map.get(missingKey)` | Thông thường trả `null` nếu không có mapping | Đọc khóa vắng mặt không phải sửa đổi; một số Map có hạn chế kiểu key/null riêng |

Một số implementation cho phép `null` (ví dụ `ArrayList`), trong khi factory `List.of` và `List.copyOf` không cho phép. Hãy xác định ngoại lệ theo **implementation và hành động cụ thể**, không chỉ theo kiểu interface.

### Chương trình kiểm tra các ràng buộc khi tạo

Lưu **`FactoryConstraintsDemo.java`**:

~~~java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class FactoryConstraintsDemo {
    static void check(String name, Runnable action) {
        try {
            action.run();
            System.out.println(name + " -> succeeded");
        } catch (RuntimeException error) {
            System.out.println(name + " -> " + error.getClass().getSimpleName());
        }
    }

    public static void main(String[] args) {
        check("List.of(null)", () -> List.of((String) null));
        check("Set.of(duplicate)", () -> Set.of("a", "a"));
        check("Map.of(duplicate-key)", () -> Map.of("a", 1, "a", 2));
        check("List.copyOf(null-element)",
                () -> List.copyOf(Arrays.asList("a", null)));
        check("toUnmodifiableList(null)",
                () -> Stream.of("a", null)
                        .collect(Collectors.toUnmodifiableList()));

        Set<String> unique = Set.copyOf(List.of("a", "a", "b"));
        System.out.println("Set.copyOf-size=" + unique.size());
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 10 FactoryConstraintsDemo.java
java FactoryConstraintsDemo
~~~

Stdout:

~~~text
List.of(null) -> NullPointerException
Set.of(duplicate) -> IllegalArgumentException
Map.of(duplicate-key) -> IllegalArgumentException
List.copyOf(null-element) -> NullPointerException
toUnmodifiableList(null) -> NullPointerException
Set.copyOf-size=2
~~~

`Set.of` và `Map.of` không bảo đảm thứ tự duyệt phần tử/entry phù hợp để suy ra thứ tự từ stdout, nên chương trình **chỉ in kích thước hoặc kết quả cố định**, không in thứ tự các phần tử của set.

## 7. Cách sửa đúng khi thật sự cần thay đổi dữ liệu

### Trường hợp A — Tạo một bản sao có thể sửa

~~~java
List<String> original = List.of("An", "Binh");
List<String> editable = new ArrayList<>(original);

editable.add("Chi");       // hợp lệ
editable.set(0, "Anh");    // hợp lệ
editable.remove("Binh");  // hợp lệ
// original vẫn không đổi
~~~

Đây là **đoạn minh họa trong phương thức**, giả sử đã import `List` và `ArrayList`. Đừng dùng `((ArrayList<String>) original)`: kiểu thực tế của danh sách từ `List.of` không có hợp đồng là `ArrayList`, nên có thể gây `ClassCastException` hoặc che giấu lỗi thiết kế.

Tương tự:

~~~java
Set<String> editableSet = new HashSet<>(Set.of("a", "b"));
Map<String, Integer> editableMap = new HashMap<>(Map.of("a", 1));

editableSet.add("c");
editableMap.put("b", 2);
~~~

Các ví dụ sử dụng các cấu trúc mutable thông thường. Constructor sao chép dữ liệu vào instance mới, nhưng với phần tử hoặc value mutable, đây vẫn là **sao chép nông** của tham chiếu.

### Trường hợp B — Giữ dữ liệu chỉ đọc làm hợp đồng công khai

Nếu mục tiêu là cho người gọi quan sát dữ liệu mà không sửa cấu trúc nội bộ, có thể trả về snapshot:

~~~java
private final List<String> names = new ArrayList<>();

public List<String> namesSnapshot() {
    return List.copyOf(names);
}
~~~

Đây là **đoạn khai báo thành viên bên trong một class**, không phải chương trình độc lập. Người gọi không thể thêm/xóa vào kết quả, và các thay đổi cấu trúc của `names` sau đó không xuất hiện trong snapshot đó.

Nếu dùng `Collections.unmodifiableList(names)` thay cho `List.copyOf(names)`, người gọi nhận **view** có thể phản ánh các thay đổi sau này từ chính class. Hãy chọn rõ **snapshot** hay **live view** theo hợp đồng API; cả hai đều không cho người gọi sửa trực tiếp qua reference trả về.

### Trường hợp C — Thiết kế API nhận đầu vào có thể đọc

Nếu phương thức chỉ cần duyệt, đếm, tìm hoặc đọc phần tử, nó nên hoạt động với collection không sửa được:

~~~java
static int countLongNames(List<String> names) {
    int count = 0;
    for (var name : names) {
        if (name.length() >= 4) {
            count++;
        }
    }
    return count;
}
~~~

Không gọi `sort`, `removeIf`, `clear` hoặc `add` trên đầu vào khi method được mô tả là chỉ đọc. Nếu cần sắp xếp để tính toán, tạo bản sao có thể sửa rồi sắp xếp bản sao:

~~~java
var sorted = new ArrayList<>(names);
sorted.sort(String::compareTo);  // không sửa names
~~~

Nếu mục tiêu chính là trả về dữ liệu theo thứ tự mới, `stream().sorted().collect(...)` cũng có thể dùng; chọn collector theo hợp đồng về khả năng sửa đổi của kết quả.

## 8. “Unmodifiable” không đồng nghĩa với “immutable sâu”

Các khái niệm dễ lẫn:

- **Unmodifiable collection:** người có reference tới collection không thể thực hiện các thao tác sửa đổi qua API collection đó. Ví dụ `List.of(...)`, `List.copyOf(...)`.
- **Unmodifiable view:** không thể sửa qua view, nhưng backing collection vẫn có thể bị sửa ở nơi khác; view có thể phản ánh thay đổi. Ví dụ `Collections.unmodifiableList(source)`.
- **Fixed-size list:** không thể thay kích thước, nhưng có thể đổi phần tử ở vị trí đang tồn tại. Ví dụ `Arrays.asList(array)`.
- **Immutable element/deep immutability:** bản thân phần tử và trạng thái có thể truy cập qua phần tử cũng không bị thay đổi. `List.copyOf` không tự sao chép sâu mọi phần tử.
- **Read-only interface usage:** mã chỉ thực hiện truy cập đọc theo quy ước. Interface `List` vẫn có method sửa đổi; quy ước “chỉ đọc” ở tầng application không tự biến object thành unmodifiable.

Điều này đặc biệt quan trọng với các collection chứa object mutable như `StringBuilder`, entity có setter, array hoặc object chứa các cấu trúc mutable khác. Một danh sách không cho `set` vẫn có thể có phần tử mà bạn thay đổi thuộc tính bên trong.

**Luồng đa nhiệm:** Không nên suy ra rằng một unmodifiable view của backing collection đang bị thay đổi đồng thời là tự động thread-safe. Nếu cần snapshot nhất quán hoặc đồng bộ hóa, phải thiết kế theo yêu cầu thread-safety của toàn bộ dữ liệu và object phần tử.

## 9. Chẩn đoán `UnsupportedOperationException` trong dự án

Khi nhận stack trace từ `add`, `remove`, `sort`, `set` hoặc `Map.put`, rà theo thứ tự:

1. **Xác định lệnh thật sự ném lỗi.** Tìm lời gọi sửa đổi trong stack trace hoặc trong method của dự án; đừng chỉ thấy collection có kiểu `List` mà nghĩ phải sửa được.
2. **Tìm nguồn tạo instance:** `List.of`, `copyOf`, `toUnmodifiableList`, `Collections.unmodifiableList`, `Arrays.asList`, `Stream.toList`, hoặc kết quả từ một API khác có cam kết chỉ đọc.
3. **Đọc hợp đồng của nguồn dữ liệu:** wrapper/view, snapshot, fixed-size hay mutable? Kiểu tĩnh `List` hoặc từ khóa `var` không trả lời đầy đủ câu hỏi này.
4. **Xác định ý định:** có thật sự cần thay đổi source không? Nếu chỉ tính toán/sắp xếp tạm, sao chép để sửa. Nếu cần thay đổi nguồn, phải dùng một collection được thiết kế mutable tại điểm sở hữu dữ liệu.
5. **Kiểm tra hậu quả:** sao chép chỉ nông; thay đổi trên bản sao có bị lẫn với phần tử mutable không? API có dựa vào thứ tự duyệt của `Set`/`Map` không? Có cần snapshot hay live view?
6. **Kiểm thử cùng implementation và mức Java dự án hỗ trợ:** một số thao tác optional có thể ném dù kết quả không thay đổi. Dùng test thể hiện hợp đồng thực tế, không dựa vào tên biến `readOnly` hoặc phép thử no-op.

**Tránh cách “sửa” bằng cách bắt và bỏ qua lỗi:**

~~~java
// Không nên làm trong mã nghiệp vụ:
try {
    results.add(newItem);
} catch (UnsupportedOperationException ignored) {
    // Im lặng khiến yêu cầu thêm phần tử bị bỏ qua.
}
~~~

Đây là **đoạn minh họa cách làm không nên dùng**; `results` và `newItem` là biến giả định của ứng dụng. Nếu dữ liệu cần được thêm, sửa rõ nơi tạo collection hoặc sao chép để sửa. `UnsupportedOperationException` có giá trị báo hiệu một hợp đồng bị vi phạm; nuốt ngoại lệ thường làm lỗi khó phát hiện.

## 10. Lỗi phổ biến

| Ngộ nhận / lỗi | Kết quả | Cách xử lý |
| --- | --- | --- |
| `List.of(...)` trả về `List` nên chắc chắn `add` được | `UnsupportedOperationException` | Chọn `new ArrayList<>(List.of(...))` khi cần sửa |
| `list.set(i, x)` không đổi kích thước nên được trên unmodifiable list | Vẫn là sửa nội dung, bị từ chối | Sửa bản sao mutable |
| `sort` hoặc `replaceAll` chỉ “xử lý dữ liệu” | Vẫn thay đổi list tại chỗ, có thể ném lỗi | Dùng bản sao hoặc cách tạo kết quả mới |
| `Collections.unmodifiableList(source)` là snapshot | View phản ánh các thay đổi qua `source` | Dùng `List.copyOf(source)` nếu cần ảnh chụp cấu trúc |
| `List.copyOf` làm object phần tử immutable | Chỉ sao chép nông/giữ tham chiếu phần tử | Dùng element immutable hoặc defensive deep-copy khi cần |
| `Arrays.asList` không sửa được mọi mặt | `set` có thể sửa giá trị, `add`/`remove` lỗi | Phân biệt fixed-size và unmodifiable |
| Bắt `UnsupportedOperationException` rồi bỏ qua | Thao tác nghiệp vụ không thực hiện | Sửa hợp đồng mutable/unmodifiable tại điểm tạo và sử dụng |
| Dùng `List.of(null)` rồi mong lỗi `UnsupportedOperationException` | `NullPointerException` khi tạo | Kiểm tra dữ liệu null và factory contract |
| Cho rằng `Collections.unmodifiableList` đảm bảo đồng bộ hóa | Có thể đọc dữ liệu backing đang đổi | Thiết kế thread-safety riêng |
| Cho rằng `Stream.toList()` tồn tại ở Java 10 | Không có API này trong Java 10 | Với Java 10 dùng `Collectors.toUnmodifiableList()` hoặc `List.copyOf` |

## 11. Tự kiểm tra

1. Vì sao `List<String> list = List.of("A"); list.add("B");` **biên dịch được** nhưng có thể ném ngoại lệ khi chạy?
2. Trên `List.of("A", "B")`, `set(0, "C")`, `sort(...)` và `replaceAll(...)` có hợp lệ không? Vì sao?
3. Khác biệt chính giữa `Collections.unmodifiableList(source)` và `List.copyOf(source)` khi `source` bị sửa sau lúc tạo kết quả?
4. Với `String[] arr = {"A"}; var fixed = Arrays.asList(arr);`, có thể gọi `fixed.set(0, "B")` và `fixed.add("C")` không?
5. Nếu muốn thêm phần tử vào một list lấy từ `List.of`, cách xử lý hợp lý là gì?
6. Vì sao `List.copyOf(List<StringBuilder>)` không đảm bảo nội dung các `StringBuilder` không đổi?
7. Hai lỗi khác `UnsupportedOperationException` khi tạo collection bằng `List.of(null)` và `Set.of("a", "a")` là gì?
8. Có nên bắt và bỏ qua `UnsupportedOperationException` để một thao tác `add` “chạy tiếp” không?

**Đáp án:** (1) `List` khai báo `add` nhưng đây là optional operation và instance từ `List.of` không hỗ trợ; (2) không, cả ba đều sửa nội dung list; (3) view phản ánh thay đổi trên backing source, `copyOf` cung cấp kết quả không sửa được độc lập với thay đổi cấu trúc của nguồn mutable; (4) `set` được, `add` không; (5) tạo `new ArrayList<>(original)` rồi sửa bản sao; (6) các phần tử mutable vẫn là cùng tham chiếu, không deep-copy; (7) `NullPointerException` và `IllegalArgumentException`; (8) không, cần sửa cách sở hữu và sử dụng collection.

## 12. Tài liệu API còn áp dụng hiện nay

- **`UnsupportedOperationException`:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/UnsupportedOperationException.html
- **`List` và các phương thức factory `of`/`copyOf`:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html
- **`Set` và `Map`:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Set.html và https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Map.html
- **`Collections.unmodifiableList`:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Collections.html
- **`Arrays.asList`:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Arrays.html
- **`Collectors.toUnmodifiableList`:** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collectors.html
- **`Stream.toList` (Java 16+):** https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html

Các API và quy tắc trình bày ở đây đều vẫn được hỗ trợ. Với một dự án thực tế, phải phân biệt **kiểu giao diện**, **hợp đồng thay đổi của implementation**, và **mức Java được biên dịch** để xử lý chính xác những thao tác gây `UnsupportedOperationException`.