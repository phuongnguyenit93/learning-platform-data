# Bản sao độc lập về cấu trúc so với khung nhìn của dữ liệu nguồn

## 1. Bài toán: cùng là collection “chỉ đọc” nhưng dữ liệu có đổi theo nguồn không?

Một chương trình thường tạo `List`, `Set` hoặc `Map` có thể sửa để tập hợp dữ liệu, sau đó đưa cho phần khác chỉ có quyền đọc. Có **hai hợp đồng khác nhau** cần phân biệt:

- **Bản sao không sửa được, độc lập về cấu trúc** (*unmodifiable snapshot*): tập phần tử, thứ tự danh sách hoặc ánh xạ khóa–giá trị được ghi nhận khi tạo bản sao. Những thao tác thêm, xóa, thay thế mục trong collection **nguồn** về sau không làm thay đổi cấu trúc của bản sao.
- **Khung nhìn không sửa được** (*unmodifiable view*): người nhận không thể gọi các thao tác sửa thông qua khung nhìn, nhưng khung nhìn vẫn đọc dữ liệu từ collection **gốc**. Nếu một đoạn code khác sửa collection gốc, kết quả đọc qua khung nhìn có thể thay đổi theo.

Ví dụ từ Java 10 đến các JDK hiện đại:

~~~java
// Đoạn minh họa đặt bên trong một phương thức, đã import java.util.*.
List<String> source = new ArrayList<>(List.of("A", "B"));

List<String> view = Collections.unmodifiableList(source);
List<String> snapshot = List.copyOf(source);

source.add("C");

System.out.println(view);     // [A, B, C]
System.out.println(snapshot); // [A, B]
~~~

Hai biến `view` và `snapshot` đều từ chối `add`, `remove` hay `set` thông qua chính chúng. Điểm khác là **view phản ánh thay đổi từ nguồn**, còn **snapshot giữ cấu trúc đã ghi nhận**.

**Phạm vi cần hiểu rõ:** “độc lập về cấu trúc” không đồng nghĩa với sao chép sâu từng đối tượng phần tử. Nếu phần tử là object có thể sửa và cả nguồn lẫn bản sao giữ tham chiếu tới object đó, thay đổi trạng thái object vẫn có thể thấy ở cả hai. Phần này sẽ được minh họa riêng ở mục 6.

Bài tập trung vào các API vẫn được hỗ trợ: `List.copyOf`, `Set.copyOf`, `Map.copyOf` (được bổ sung từ Java 10), cùng các phương thức `Collections.unmodifiable...` (khung nhìn vẫn là API hợp lệ và có trường hợp sử dụng rõ ràng). Không cần cơ chế Java nội bộ hoặc API đã lỗi thời.

## 2. Bốn khái niệm phải tách bạch

**(1) Collection có thể sửa (modifiable)**

~~~java
var source = new ArrayList<>(List.of("A", "B"));
source.add("C");
source.set(0, "X");
source.remove("B");
~~~

`ArrayList` cho phép thay đổi số lượng và phần tử thông qua các phương thức công khai, nếu các điều kiện của API được đáp ứng.

**(2) Khung nhìn không sửa được (unmodifiable view)**

~~~java
List<String> view = Collections.unmodifiableList(source);
~~~

`view.add("D")` bị từ chối bằng `UnsupportedOperationException`. Tuy vậy, `source.add("D")` vẫn có thể thực hiện và làm `view` đọc thấy `"D"`. Wrapper không có nghĩa là dữ liệu nền đã được đóng băng.

**(3) Bản sao không sửa được (unmodifiable snapshot)**

~~~java
List<String> snapshot = List.copyOf(source);
~~~

`snapshot` không cho sửa thông qua API của nó, và `source.add("D")` hay `source.remove("A")` sau thời điểm tạo bản sao không làm đổi các vị trí/phần tử đã được ghi nhận trong `snapshot`. Bản sao có thể giữ **tham chiếu** tới cùng các object phần tử.

**(4) Dữ liệu bất biến sâu (deeply immutable data)**

Một collection chỉ thật sự giữ **nội dung bất biến sâu** nếu những object mà bạn quan tâm bên trong nó cũng có trạng thái bất biến hoặc được sao chép/đóng băng theo hợp đồng phù hợp. `List.copyOf` tự nó **không** sao chép sâu cây object.

Hai cách “unmodifiable” đều ngăn người dùng gọi thao tác chỉnh cấu trúc qua kết quả trả về. Chúng khác nhau ở việc **thay đổi từ bên ngoài** có tác động đến dữ liệu mà người đọc nhìn thấy hay không.

## 3. Các API tạo snapshot từ Java 10

| Phương thức | Tham số nguồn | Kết quả | Điều cần chú ý |
| --- | --- | --- | --- |
| `List.copyOf(Collection<? extends E>)` | Bất kỳ `Collection` hợp lệ | `List<E>` không sửa được, giữ thứ tự duyệt của nguồn khi lấy bản sao | Cho phần tử trùng nhau; không nhận `null` |
| `Set.copyOf(Collection<? extends E>)` | Một `Collection`, kể cả `List` | `Set<E>` không sửa được, không trùng phần tử theo `equals` | Nếu nguồn có phần tử trùng, giữ một phần tử bất kỳ trong nhóm trùng; thứ tự duyệt kết quả không được bảo đảm |
| `Map.copyOf(Map<? extends K, ? extends V>)` | Một `Map` | `Map<K,V>` không sửa được chứa các ánh xạ tại lúc tạo | Không nhận khóa hoặc giá trị `null`; không dựa vào thứ tự duyệt kết quả |

Cả ba phương thức này có `Since: 10` trong Javadoc Java SE hiện hành. Chúng dùng được trên Java 17+ và các JDK hiện đại theo hợp đồng API.

### Snapshot cho List

~~~java
// Đoạn trong phương thức.
var mutable = new ArrayList<>(List.of("Java", "Kotlin"));
var snapshot = List.copyOf(mutable);

mutable.set(0, "JDK");
mutable.add("Scala");

System.out.println(mutable);  // [JDK, Kotlin, Scala]
System.out.println(snapshot); // [Java, Kotlin]
~~~

`List.copyOf` ghi nhận phần tử theo **thứ tự duyệt** của collection đầu vào; với `ArrayList`, đó là thứ tự danh sách. Thao tác `set` cũng như `add` sau đó trên `mutable` không làm thay đổi các vị trí của `snapshot`.

### Snapshot cho Set

~~~java
// Không in trực tiếp Set vì không nên dựa vào thứ tự duyệt.
var mutable = new LinkedHashSet<>(List.of("A", "B"));
var snapshot = Set.copyOf(mutable);

mutable.add("C");
System.out.println(mutable.contains("C"));  // true
System.out.println(snapshot.contains("C")); // false
System.out.println(snapshot.size());        // 2
~~~

`Set.copyOf` ghi nhận **tập phần tử**, không bảo đảm giữ thứ tự của `LinkedHashSet` đầu vào. Nếu ứng dụng yêu cầu thứ tự xác định, cần chọn cấu trúc và hợp đồng trả về phù hợp thay vì suy đoán thứ tự của `Set.copyOf`.

### Snapshot cho Map

~~~java
// Đoạn trong phương thức, dùng import java.util.*.
var mutable = new LinkedHashMap<String, Integer>();
mutable.put("Java", 10);
var snapshot = Map.copyOf(mutable);

mutable.put("Java", 17);
mutable.put("Kotlin", 2);

System.out.println(mutable.get("Java"));          // 17
System.out.println(snapshot.get("Java"));         // 10
System.out.println(snapshot.containsKey("Kotlin")); // false
~~~

`Map.copyOf` ghi nhận ánh xạ khóa–giá trị. Sửa giá trị của một khóa hay thêm khóa mới trong `mutable` không làm thay đổi các entry của `snapshot`. Không dùng `snapshot.toString()` để suy luận thứ tự key vì kết quả không bảo đảm thứ tự duyệt theo `LinkedHashMap` nguồn.

## 4. Các khung nhìn `Collections.unmodifiable...`

Java Collections Framework cũng có:

~~~java
Collections.unmodifiableList(list);
Collections.unmodifiableSet(set);
Collections.unmodifiableMap(map);
Collections.unmodifiableCollection(collection);
~~~

Những phương thức này tạo **khung nhìn đọc** bọc quanh collection nguồn. Khi gọi `view.get(...)`, `view.contains(...)`, `view.size()` hoặc `view.get(key)`, kết quả được đọc qua collection nền theo hợp đồng của wrapper. Người dùng không sửa được bằng những phương thức mutator trên view, nhưng mã giữ tham chiếu `list`/`set`/`map` gốc vẫn có thể sửa.

~~~java
// Đoạn minh họa.
var source = new ArrayList<>(List.of("A"));
var view = Collections.unmodifiableList(source);

source.add("B");
System.out.println(view); // [A, B]

source.remove("A");
System.out.println(view); // [B]
~~~

**Điều gì làm view hữu ích?** Khi một thành phần muốn cung cấp cửa sổ đọc vào **trạng thái hiện tại** mà vẫn giữ toàn quyền cập nhật dữ liệu nội bộ. Người nhận có thể đọc được thay đổi mới qua view sau khi nguồn cập nhật. Đó là hành vi đúng khi sản phẩm cần quan sát dữ liệu đang thay đổi.

**Điều gì làm view nguy hiểm nếu hiểu sai?** Người gọi nhận một “collection chỉ đọc” và tưởng đó là ảnh chụp ổn định để xử lý, lưu cache, tạo báo cáo hoặc kiểm tra nhất quán. Nếu chủ nguồn thay đổi, view sẽ đọc ra dữ liệu khác. Với đa luồng, còn cần cơ chế đồng bộ tương ứng của nguồn; wrapper `unmodifiable...` không tự biến một collection mutable thành thread-safe.

### So sánh trực tiếp

| Tình huống | `Collections.unmodifiableList(source)` | `List.copyOf(source)` |
| --- | --- | --- |
| Có thể gọi `result.add(...)`? | Không | Không |
| Nguồn `source.add(...)` sau đó | View thấy phần tử mới | Snapshot không có phần tử mới |
| Nguồn `source.set(...)` sau đó | View thấy giá trị tại vị trí mới | Snapshot giữ tham chiếu phần tử ban đầu ở vị trí đó |
| Nguồn `source.remove(...)` sau đó | View phản ánh việc xóa | Snapshot giữ cấu trúc ban đầu |
| Phần tử là object mutable và object đó được sửa | Có thể nhìn thấy thay đổi | Vẫn có thể nhìn thấy thay đổi, do sao chép nông |
| Có nguồn `null` hoặc phần tử `null`? | Wrapper phản ánh dữ liệu nguồn nếu collection đó cho phép | `List.copyOf` từ chối nguồn hoặc phần tử `null` |
| Dùng để công bố “dữ liệu hiện tại” | Phù hợp khi muốn live view | Cần gọi lại để lấy snapshot mới |
| Dùng làm cấu trúc ổn định cho một lần xử lý | Không bảo đảm ổn định nếu nguồn tiếp tục đổi | Phù hợp về cấu trúc sau khi tạo xong |

Đối với Set và Map, quy tắc tương đương: `Collections.unmodifiableSet(sourceSet)` và `Collections.unmodifiableMap(sourceMap)` là **view**, còn `Set.copyOf` và `Map.copyOf` là **snapshot cấu trúc** khi nguồn mutable.

## 5. Ví dụ trước–sau: phòng tránh lộ thay đổi ngoài ý muốn

Giả sử một lớp lưu các tên tính năng mà phía ngoài chỉ được đọc:

~~~java
// Ví dụ minh họa trong class FeatureFlags.
private final List<String> flags = new ArrayList<>();

public List<String> getFlagsView() {
    return Collections.unmodifiableList(flags);
}

public List<String> getFlagsSnapshot() {
    return List.copyOf(flags);
}
~~~

Đây là **đoạn thành viên của class**, chưa phải file Java hoàn chỉnh. Cả hai phương thức có kiểu trả về tường minh `List<String>`, nhưng hợp đồng khác nhau.

- `getFlagsView()`: nếu nội bộ lớp thay `flags` bằng cách thêm/xóa phần tử, mã bên ngoài đang giữ view sẽ thấy thay đổi khi đọc tiếp. Dù không gọi `add` trên view, bên ngoài vẫn không có ảnh chụp ổn định.
- `getFlagsSnapshot()`: các phần tử/độ dài của danh sách snapshot đã trả ra không thay đổi khi `flags` được sửa. Muốn dữ liệu mới, người gọi phải lấy snapshot lần khác.
- `private final` chỉ cấm **gán lại biến trường `flags`**, không cấm `flags.add(...)` hoặc `flags.remove(...)`. Thêm `final` cho tham chiếu không có tác dụng tạo snapshot.

Nếu mục tiêu là “kết quả của một lần tính toán không bị thay đổi cấu trúc sau khi bàn giao”, dùng snapshot là hợp đồng rõ ràng. Nếu mục tiêu là “theo dõi trạng thái cập nhật mới nhất”, view có thể phù hợp, nhưng phải thể hiện trong tên API/tài liệu và giải quyết tính đồng bộ khi có nhiều luồng.

### Sao chép trước rồi mới bọc view cũng tạo snapshot cấu trúc

Không phải chỉ có `copyOf` mới tạo được một cấu trúc độc lập. Ví dụ vẫn hợp lệ hiện nay:

~~~java
List<String> snapshot = Collections.unmodifiableList(
        new ArrayList<>(source)
);
~~~

Với `source` là danh sách có thể sửa, phần `new ArrayList<>(source)` tạo một **collection mới**, rồi `unmodifiableList` ngăn sửa thông qua wrapper. Vì backing list mới không được xuất ra ngoài qua đoạn code này, thay đổi **nguồn ban đầu** không ảnh hưởng cấu trúc của kết quả.

Khác với `List.copyOf`, cách này có thể giữ `null` trong phần tử nếu `ArrayList` đầu vào có `null`; tuy nhiên đây vẫn là **sao chép nông**, không phải deep copy. Trong trường hợp dữ liệu không chứa `null` và chỉ cần snapshot không sửa được, `List.copyOf(source)` ngắn gọn và diễn đạt mục đích tốt hơn.

**Phân biệt kết quả:** `new ArrayList<>(source)` một mình chỉ là bản sao **có thể sửa**. Muốn không cho người nhận sửa thì cần bọc view trên bản sao mới hoặc dùng `List.copyOf`.

## 6. Sao chép nông: object phần tử vẫn có thể thay đổi

Điểm cốt lõi của cụm từ **“độc lập về cấu trúc”**: chỉ phần chứa/tham chiếu và sự phân bổ phần tử của collection là độc lập. Những phần tử là object không tự trở thành bất biến.

~~~java
// Đoạn mã minh họa nằm trong cùng một class, gồm các khai báo sau.
static class Item {
    String name;

    Item(String name) {
        this.name = name;
    }
}

// Trong một phương thức:
var item = new Item("Ban đầu");
var source = new ArrayList<Item>();
source.add(item);

var snapshot = List.copyOf(source);

item.name = "Đã đổi";
source.clear();

System.out.println(snapshot.size());    // 1
System.out.println(snapshot.get(0).name); // Đã đổi
~~~

- `source.clear()` làm collection nguồn không còn phần tử, nhưng `snapshot.size()` vẫn bằng `1`: bản sao độc lập về **cấu trúc**.
- `item.name = "Đã đổi"` sửa cùng một object mà `snapshot.get(0)` đang tham chiếu. Bản sao thấy tên mới: **không có deep copy**.
- `snapshot.set(0, new Item(...))` không hợp lệ khi chạy và ném `UnsupportedOperationException`, nhưng việc sửa trạng thái *bên trong Item* không đi qua mutator của list nên wrapper không ngăn được.

Điều tương tự xảy ra với `Map.copyOf` nếu một **value** là object mutable. Bản đồ mới giữ ánh xạ độc lập, nhưng có thể trỏ đến cùng object value mà mã khác đang sửa. Với các **key mutable**, việc thay những trường ảnh hưởng `equals` hoặc `hashCode` còn có thể phá giả định tra cứu của map/set; hãy ưu tiên key bất biến.

### Nếu cần dữ liệu bất biến sâu thì làm gì?

Có thể tách dữ liệu thành các object bất biến thực sự. Ví dụ `record Item(String name) {}` mang dữ liệu `String` bất biến; nếu record chỉ chứa các thành phần bất biến, snapshot cấu trúc thường đủ cho mục tiêu đọc ổn định.

~~~java
// Java 17+, đoạn record minh họa ở cấp class/file.
record Item(String name) {}
~~~

**Nhưng record không tự deep copy mọi trường**: một record chứa `List<String>` có thể vẫn giữ danh sách mutable được truyền vào nếu constructor không chụp bản sao. Với object mutable nhiều lớp, cần chủ động sao chép/đóng băng dữ liệu con ở điểm tạo cấu trúc, và thiết kế thành phần sao cho không rò rỉ tham chiếu mutable.

Không dùng việc in `snapshot` không thay đổi trong một ví dụ `String` để khẳng định `List.copyOf` tự sao chép sâu. `String` vốn bất biến nên ví dụ String không bộc lộ vấn đề tham chiếu dùng chung.

## 7. Chương trình Java 17+ hoàn chỉnh: nhìn rõ snapshot và view

Lưu tệp đúng tên **`SnapshotVsViewDemo.java`**. Chương trình sử dụng các API công khai còn được hỗ trợ và cố tình in thuộc tính có thứ tự hoặc giá trị đơn lẻ để kết quả không phụ thuộc thứ tự duyệt `Set.copyOf` hay `Map.copyOf`.

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public class SnapshotVsViewDemo {
    static final class Box {
        private String label;

        Box(String label) {
            this.label = label;
        }

        void rename(String newLabel) {
            this.label = newLabel;
        }

        String label() {
            return label;
        }
    }

    public static void main(String[] args) {
        var source = new ArrayList<>(List.of("red", "blue"));
        List<String> view = Collections.unmodifiableList(source);
        List<String> snapshot = List.copyOf(source);

        source.set(0, "green");
        source.add("gold");

        System.out.println("source=" + source);
        System.out.println("view=" + view);
        System.out.println("snapshot=" + snapshot);

        source.remove("blue");
        System.out.println("viewAfterRemove=" + view);
        System.out.println("snapshotAfterRemove=" + snapshot);

        var box = new Box("v1");
        var boxes = new ArrayList<Box>();
        boxes.add(box);
        var boxCopy = List.copyOf(boxes);

        box.rename("v2");
        boxes.clear();
        System.out.println("boxCopySize=" + boxCopy.size());
        System.out.println("boxCopyElement=" + boxCopy.get(0).label());

        var setSource = new LinkedHashSet<>(List.of("a", "b"));
        Set<String> setView = Collections.unmodifiableSet(setSource);
        Set<String> setCopy = Set.copyOf(setSource);
        setSource.add("c");
        System.out.println("setViewSize=" + setView.size());
        System.out.println("setCopyHasC=" + setCopy.contains("c"));

        var mapSource = new LinkedHashMap<String, Integer>();
        mapSource.put("a", 1);
        Map<String, Integer> mapView = Collections.unmodifiableMap(mapSource);
        Map<String, Integer> mapCopy = Map.copyOf(mapSource);
        mapSource.put("a", 9);
        mapSource.put("b", 2);
        System.out.println("mapViewA=" + mapView.get("a"));
        System.out.println("mapCopyA=" + mapCopy.get("a"));
        System.out.println("mapCopyHasB=" + mapCopy.containsKey("b"));

        try {
            snapshot.add("new");
        } catch (UnsupportedOperationException expected) {
            System.out.println("snapshotMutable=false");
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 SnapshotVsViewDemo.java
java SnapshotVsViewDemo
~~~

**Stdout chính xác:**

~~~text
source=[green, blue, gold]
view=[green, blue, gold]
snapshot=[red, blue]
viewAfterRemove=[green, gold]
snapshotAfterRemove=[red, blue]
boxCopySize=1
boxCopyElement=v2
setViewSize=3
setCopyHasC=false
mapViewA=9
mapCopyA=1
mapCopyHasB=false
snapshotMutable=false
~~~

### Phân tích kết quả

1. Tại thời điểm gọi `List.copyOf(source)`, danh sách nguồn có `[red, blue]`. Sau `set` và `add`, nguồn và view cùng là `[green, blue, gold]`, nhưng snapshot vẫn `[red, blue]`.
2. `source.remove("blue")` làm view có `[green, gold]`. Snapshot giữ `[red, blue]` vì việc xóa ở nguồn không ảnh hưởng cấu trúc bản sao.
3. `Box` là một phần tử mutable. `box.rename("v2")` đổi trạng thái object được cả nguồn và snapshot tham chiếu. Sau `boxes.clear()`, snapshot vẫn có một phần tử với label `v2`.
4. `Set.copyOf` không phản ánh phần tử `"c"` được thêm sau đó; `Set` view phản ánh kích thước mới. Chương trình không in toàn bộ set nên không phụ thuộc thứ tự duyệt vốn không được bảo đảm.
5. `Map.copyOf` vẫn giữ ánh xạ `"a" → 1` và không có `"b"`. Map view đọc thấy giá trị `9` từ nguồn đã sửa.
6. Gọi `snapshot.add("new")` gây `UnsupportedOperationException`; chương trình bắt ngoại lệ để chứng minh snapshot không cho sửa cấu trúc qua tham chiếu này.

Tất cả đầu ra đến từ thao tác tuần tự trong một luồng; ví dụ không có giả định về hành vi khi collection nguồn bị nhiều luồng sửa đồng thời.

## 8. Những giới hạn hợp đồng của `copyOf` cần biết

### 8.1. Không hỗ trợ null

~~~java
// Các lời gọi sau KHÔNG thành công; minh họa ngoại lệ, không chạy nối tiếp.
List.copyOf(java.util.Arrays.asList("A", null)); // NullPointerException
Set.copyOf(java.util.Arrays.asList("A", null));  // NullPointerException

Map<String, Integer> nullable = new java.util.HashMap<>();
nullable.put("A", null);
Map.copyOf(nullable);                           // NullPointerException
~~~

`List.copyOf` và `Set.copyOf` cũng từ chối tham số nguồn `null`, còn `Map.copyOf` từ chối map nguồn `null` hoặc có khóa/giá trị `null`. Ví dụ dùng `Arrays.asList` chỉ để tạo dữ liệu chứa `null`; đây không phải chương trình độc lập. Nếu dữ liệu đầu vào được phép chứa null, cần quyết định chính sách: lọc, báo lỗi, chuẩn hóa hoặc chọn cấu trúc khác; đừng âm thầm thay dữ liệu nếu contract không cho phép.

### 8.2. Số lượng phần tử trùng nhau

- `List.copyOf` giữ các lần xuất hiện trùng nhau của phần tử theo thứ tự duyệt input.
- `Set.copyOf` chấp nhận đầu vào là `Collection` chứa nhiều phần tử bằng nhau và kết quả chỉ giữ một đại diện cho mỗi nhóm trùng theo `equals`. Nếu các instance khác nhau nhưng `equals` coi như nhau, không nên giả định nó giữ instance nào.
- `Set.of("A", "A")` là phương thức **khác**: cố truyền phần tử trùng nhau sẽ ném `IllegalArgumentException`. Không đánh đồng `Set.of` với `Set.copyOf`.
- `Map.copyOf` nhận một `Map`; về bản chất Map đã không có hai entry đồng thời với cùng một key theo tiêu chí khóa của nó. Không tự tạo “quy tắc merge key trùng” cho `Map.copyOf`.

~~~java
// HỢP LỆ:
var repeated = List.of("A", "A", "B");
var listCopy = List.copyOf(repeated);  // size() == 3
var setCopy = Set.copyOf(repeated);    // size() == 2

System.out.println(listCopy.size()); // 3
System.out.println(setCopy.size());  // 2
~~~

Không phụ thuộc thứ tự được hiển thị của `setCopy`. Nếu ứng dụng cần trật tự, phải dùng abstraction đáp ứng yêu cầu đó.

### 8.3. Không bảo đảm mỗi lần gọi đều cấp phát object mới

~~~java
// Đoạn minh họa trong phương thức.
var original = List.of("A", "B");
var copy = List.copyOf(original);
System.out.println(original.equals(copy)); // true
~~~

`copyOf` có thể **tái sử dụng một collection đã không sửa được** thay vì luôn cấp phát bản sao vật lý mới. Javadoc và hướng dẫn Oracle ghi rõ trường hợp input đã unmodifiable có thể không cần copy. Vì vậy:

- Không viết logic dựa vào `original == copy` hoặc `original != copy`.
- Không dùng identity của các collection này làm khóa cho cơ chế cache/dedup chỉ dựa trên việc “đây là bản sao mới”.
- Không dùng các object kết quả theo kiểu dựa vào identity để đồng bộ hóa; các collection unmodifiable từ factory này được đặc tả theo hướng value-based.

Hợp đồng cần dựa vào là **nội dung và tính không sửa được**, không phải việc luôn có một địa chỉ object mới. Khi nguồn thật sự là mutable, `copyOf` cung cấp kết quả không phản ánh các sửa đổi cấu trúc sau đó của nguồn.

### 8.4. Snapshot không tự bảo đảm nguyên tử khi nguồn đang bị cập nhật đồng thời

`List.copyOf(source)`, `Set.copyOf(source)` và `Map.copyOf(source)` **không phải** phép “đóng băng giao dịch” đồng thời cho mọi implementation collection mutable. Nếu nhiều luồng sửa nguồn trong khi đang tạo bản sao, không được suy ra snapshot là trạng thái nhất quán tại một thời điểm theo ý nghĩa giao dịch. Tùy implementation, có thể có ngoại lệ hoặc kết quả không phù hợp giả định.

Khi cần ảnh chụp nhất quán, hãy đồng bộ đúng cách với bên ghi, sử dụng dữ liệu/collection phù hợp với yêu cầu concurrency, hoặc tạo snapshot tại một điểm mà nguồn không bị sửa. Sau khi tạo xong, tính unmodifiable của container không tự bảo vệ trạng thái của những **phần tử mutable** khỏi thay đổi từ luồng khác.

### 8.5. Tính sửa được của một object phần tử không liên quan đến mutator của container

Ngay cả khi `snapshot.add(...)` ném `UnsupportedOperationException`, `snapshot.get(0).setName(...)` vẫn có thể chạy nếu object ở vị trí đó cho phép sửa. Nếu một object được dùng làm key trong map/set mà các trường tham gia `equals/hashCode` thay đổi, truy vấn như `contains` hoặc `get` có thể không còn hành vi như mong muốn. Để có tính ổn định dữ liệu thực sự, ưu tiên các value object bất biến, hoặc sao chép riêng các phần tử.

## 9. Cách chọn API theo nhu cầu

| Nhu cầu thực tế | Lựa chọn thường phù hợp | Lý do |
| --- | --- | --- |
| Trả danh sách kết quả tính toán không đổi sau khi trả | `List.copyOf(source)` | Không phản ánh thay đổi cấu trúc của `source` về sau |
| Trả tập mã quyền/feature flags đã chốt | `Set.copyOf(source)` | Tập membership độc lập, không sửa được qua kết quả |
| Trả bảng cấu hình khóa–giá trị tại một thời điểm | `Map.copyOf(source)` | Ánh xạ độc lập về cấu trúc sau thời điểm sao chép |
| Cung cấp quyền xem dữ liệu luôn cập nhật theo collection nội bộ | `Collections.unmodifiableList(source)` hoặc biến thể Set/Map | Live view, đọc qua backing collection |
| Cần kết quả không sửa được nhưng cho phép phần tử `null` | Xem xét `Collections.unmodifiableList(new ArrayList<>(source))` nếu hợp đồng chấp nhận null | Chụp cấu trúc bằng một collection mới, rồi bọc không sửa được |
| Cần bản sao có thể tiếp tục sửa | `new ArrayList<>(source)`, `new HashSet<>(source)`, `new HashMap<>(source)` | Là collection mới nhưng vẫn hỗ trợ sửa |
| Cần snapshot chứa object mutable nhưng không đổi được trạng thái của chúng | Sao chép/chuẩn hóa từng phần tử thành kiểu bất biến trước khi tạo collection cuối | `copyOf` không phải deep copy |
| Cần data view/snapshot nhất quán trong nhiều luồng | Thiết kế đồng bộ hoặc mô hình dữ liệu concurrency phù hợp | `unmodifiable` không thay thế cơ chế quản lý đồng thời |

**Không nhầm với `List.of`, `Set.of`, `Map.of`:** các factory này tạo unmodifiable collection từ các phần tử/entry bạn cung cấp trực tiếp. Chúng hữu ích với các giá trị đã biết và tồn tại từ Java 9; còn `copyOf` (Java 10) được thiết kế để lấy unmodifiable collection từ **collection/map đã có sẵn**. Tất cả vẫn là API hợp lệ.

Một phương thức tạo ảnh chụp thường nên công bố kiểu trả về qua interface, ví dụ:

~~~java
public static List<String> namesSnapshot(List<String> source) {
    return List.copyOf(source);
}
~~~

Đây là **phương thức minh họa**, đặt trong một class. Chữ ký `List<String>` cho người gọi biết hợp đồng kiểu; tên/tài liệu cần cho biết đây là snapshot về cấu trúc, và liệu phần tử có bất biến hay không.

## 10. Lỗi thường gặp

**Lỗi 1: “`Collections.unmodifiableList(source)` chính là một bản sao”.** Sai: đó là view, nên `source.add(...)` có thể làm kết quả khác đi. Nếu cần độc lập cấu trúc, tạo bản sao thực sự.

**Lỗi 2: “`List.copyOf(source)` sao chép sâu các phần tử”.** Sai: với object mutable, bản sao vẫn có thể trỏ tới cùng object. Nếu trạng thái của object thay đổi, kết quả đọc sẽ phản ánh thay đổi đó.

**Lỗi 3: “Collection không sửa được thì tất cả object bên trong cũng bất biến”.** Sai: unmodifiable là hợp đồng trên API thay đổi **container**, không buộc mỗi phần tử phải là immutable.

**Lỗi 4: “Snapshot phải có reference khác nguồn”.** Sai: khi nguồn đã unmodifiable, phương thức có thể trả lại instance phù hợp; không dựa vào toán tử `==` để định nghĩa snapshot.

**Lỗi 5: “Bản sao của LinkedHashSet/LinkedHashMap luôn giữ thứ tự in”.** Sai: `Set.copyOf`/`Map.copyOf` không cam kết duy trì encounter/iteration order của implementation nguồn. Nếu test chỉ kiểm tra thành viên, dùng `contains`/`get`/`size` thay vì so sánh `toString()` của tập/map.

**Lỗi 6: “`Set.copyOf` từ list có phần tử trùng ném lỗi giống `Set.of`”.** Sai: `Set.copyOf` giữ đại diện của nhóm bằng nhau, còn `Set.of` từ chối duplicate argument.

**Lỗi 7: “`copyOf` chấp nhận mọi nội dung, kể cả null”.** Sai: các phương thức này từ chối `null` theo hợp đồng. Xác định chính sách dữ liệu trước khi lấy snapshot.

**Lỗi 8: “View không sửa được thì thread-safe”.** Sai: nếu collection nền được sửa từ luồng khác mà không có đồng bộ phù hợp, view không tự loại bỏ race condition. Ngay cả snapshot container cũng không tự làm object phần tử mutable trở nên thread-safe.

**Lỗi 9: “Snapshot sẽ nhận dữ liệu mới khi nguồn được cập nhật”.** Sai: cần tạo snapshot mới cho những thay đổi cấu trúc sau đó. Nếu cần theo dõi thay đổi sống, hãy thiết kế rõ ràng live view hoặc cơ chế subscription phù hợp.

## 11. Bài tập kiểm tra hiểu biết

**Câu 1.** Với `var source = new ArrayList<>(List.of("A")); var view = Collections.unmodifiableList(source); var copy = List.copyOf(source); source.add("B");`, giá trị của `view` và `copy` là gì?

Đáp án: `view` là `[A, B]`, `copy` vẫn là `[A]`. View đọc qua nguồn, snapshot ghi nhận cấu trúc trước khi `add`.

**Câu 2.** Sau `List.copyOf(source)`, gọi `copy.add("C")` thì điều gì xảy ra?

Đáp án: `UnsupportedOperationException`. Phương thức `copyOf` tạo list không sửa được qua kết quả trả về.

**Câu 3.** Một `Box` trong `List.copyOf` có field mutable. Sửa `box.name` sau khi tạo list copy thì `copy.get(0).name` có đổi không?

Đáp án: Có thể thấy giá trị mới, nếu cả nguồn và copy giữ cùng tham chiếu `Box`; `copyOf` là sao chép nông các phần tử, không sao chép trạng thái từng object.

**Câu 4.** `Set.copyOf(List.of("A", "A", "B"))` có lỗi duplicate không?

Đáp án: Không. Kết quả có hai phần tử phân biệt theo `equals`. `Set.of("A", "A", "B")` mới là lời gọi bị từ chối vì duplicate.

**Câu 5.** Nếu `List<String> original = List.of("A"); List<String> copy = List.copyOf(original);`, có thể khẳng định `original != copy` không?

Đáp án: Không. Với nguồn đã unmodifiable, implementation có thể tái sử dụng instance. Phải xét nội dung và hợp đồng API, không dựa vào identity.

**Câu 6.** Vì sao `List.copyOf(source)` chưa đủ để đảm bảo một cấu hình đa luồng bất biến sâu?

Đáp án: Nó chỉ bảo đảm cấu trúc list không bị sửa qua kết quả hoặc thay đổi cấu trúc nguồn về sau không phản ánh vào list copy. Nếu phần tử vẫn mutable hoặc snapshot được lấy khi nguồn đang cập nhật thiếu đồng bộ, các giả định về tính nhất quán vẫn có thể bị phá.

## 12. Checklist khi thiết kế API chỉ đọc

1. **Nêu đúng yêu cầu:** người dùng muốn nhìn thấy thay đổi mới từ nguồn, hay muốn dữ liệu ở một thời điểm ổn định?
2. **Nếu cần snapshot**, ưu tiên `List.copyOf`/`Set.copyOf`/`Map.copyOf` cho dữ liệu hợp lệ, không có `null`. Kiểm tra kỹ quy tắc trùng phần tử và thứ tự cho `Set`/`Map`.
3. **Nếu cần live view**, dùng `Collections.unmodifiable...` và mô tả rõ đây là khung nhìn; không để người gọi hiểu nhầm là bản sao độc lập.
4. **Đánh giá object bên trong:** có phần tử/key/value mutable không? Có cần defensive copy từng phần tử để tránh lộ trạng thái không?
5. **Đánh giá thời điểm và đồng thời:** nguồn có bị thay đổi trong khi copy không? Nếu có, thiết kế điểm tạo snapshot nhất quán thay vì chỉ dựa vào tên hàm `copyOf`.
6. **Kiểm tra đầu vào:** `null`, duplicate, yêu cầu iteration order, tính serializable và hợp đồng cụ thể của API.
7. **Kiểm tra đầu ra:** viết test sửa collection nguồn sau khi lấy kết quả, rồi xác nhận snapshot giữ cấu trúc trong khi view phản ánh thay đổi; nếu phần tử mutable, thử thay đổi trạng thái của phần tử để hiểu giới hạn sao chép nông.
8. **Biên dịch và chạy trên target thực tế**, ví dụ `javac --release 17` khi ứng dụng chạy trên Java 17; không dựa vào implementation class riêng tư hoặc thứ tự ngẫu nhiên.

## 13. Nguồn chính thức và kiến thức còn hiệu lực

- [Oracle JDK 25 — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html): có hướng dẫn riêng về unmodifiable copies từ `copyOf`, khả năng giữ chung tham chiếu phần tử mutable và so sánh với khung nhìn `Collections.unmodifiable...`.
- [Oracle Java SE 27 — List API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/List.html): hợp đồng `List.copyOf`, thứ tự các phần tử, `null`, việc không phản ánh thay đổi từ nguồn và lưu ý về nhận dạng object.
- [Oracle Java SE 27 — Set API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Set.html): `Set.copyOf`, xử lý duplicate, `null` và thứ tự không bảo đảm.
- [Oracle Java SE 27 — Map API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Map.html): `Map.copyOf` với entry, khóa/giá trị `null` và tính độc lập với thay đổi nguồn.
- [Oracle Java SE 25 — Collections API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html): `unmodifiableList`, `unmodifiableSet` và `unmodifiableMap` là các view không sửa được.
- [Oracle Java SE 25 — Collection API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collection.html): mô tả chính thức về unmodifiable view, backing collection và cách thay đổi nguồn có thể được nhìn thấy qua view.

**Điểm cần ghi nhớ:** `copyOf` dùng để tạo collection **không sửa được, độc lập về cấu trúc** so với collection nguồn mutable; `Collections.unmodifiable...` là **khung nhìn chỉ đọc** lên dữ liệu nền. Cả hai đều không mặc nhiên tạo deep copy các phần tử. Hãy chọn theo nhu cầu nhìn thấy trạng thái mới hoặc giữ snapshot ổn định, và thiết kế riêng tính bất biến của dữ liệu bên trong khi cần.