# Xử lý collection lồng nhau và nhu cầu sao chép sâu

## 1. Vấn đề cần giải quyết

Trong Java, một collection có thể chứa một collection khác, hoặc chứa những object có trạng thái thay đổi được. Ví dụ:

~~~java
// Trong một phương thức, đã import java.util.List và java.util.ArrayList.
var row = new ArrayList<>(List.of("A", "B"));
var table = new ArrayList<List<String>>();
table.add(row);
~~~

Kiểu `table` là `ArrayList<List<String>>`: collection bên ngoài chứa những `List<String>` bên trong. Nếu muốn trả bảng dữ liệu **chỉ đọc**, nhiều người lập tức viết:

~~~java
List<List<String>> result = List.copyOf(table);
~~~

Câu lệnh hợp lệ trên **Java 10+**, nhưng **chỉ bảo vệ cấu trúc của list bên ngoài**. List bên trong `row` vẫn là `ArrayList` có thể sửa, và `result.get(0)` vẫn trỏ đến chính list đó. Vì thế:

~~~java
row.add("C");

System.out.println(result); // [[A, B, C]]
~~~

**Điểm cốt lõi:** `List.copyOf(table)` không tự đệ quy gọi `List.copyOf` cho từng phần tử. Nó tạo một list ngoài không sửa được, nhưng **không sao chép sâu** các object phần tử. Các lớp collection trong `java.util` không có một phép `deepCopy()` tổng quát biết cách sao chép mọi object tùy ý.

Đây là chủ đề **thiết kế dữ liệu chỉ đọc**: trước khi công bố một collection ra ngoài phương thức/lớp, phải xác định **tầng nào cần ngăn sửa** và **trạng thái nào phải không đổi sau khi trả kết quả**.

Bài sử dụng những API còn được hỗ trợ trên JDK hiện đại, đặc biệt `List.copyOf` và `Map.copyOf` (Java 10), `Collections.unmodifiable...`, record (Java 16+) và `Stream.toList()` (Java 16+). Chương trình hoàn chỉnh bên dưới nhắm tới **Java 17+**.

## 2. Phân biệt bốn cấp độ bảo vệ

| Cấp độ | Ví dụ | Tác động khi sửa nguồn/đối tượng |
| --- | --- | --- |
| **Live view chỉ đọc** | `Collections.unmodifiableList(table)` | Không cho sửa qua view, nhưng view phản ánh thay đổi collection `table` và các phần tử bên trong |
| **Snapshot nông của list ngoài** | `List.copyOf(table)` | Thêm/xóa list con khỏi `table` sau lúc copy không đổi số list con trong bản sao; sửa một list con được tham chiếu vẫn nhìn thấy |
| **Snapshot từng tầng collection** | `table.stream().map(List::copyOf).toList()` | Cả list ngoài lẫn các list con đều không sửa được; sửa cấu trúc các list nguồn về sau không đổi snapshot |
| **Snapshot sâu đến dữ liệu phần tử** | Tạo value object bất biến mới cho từng object mutable rồi thu vào những list không sửa được | Không chia sẻ trạng thái mutable mà bên ngoài còn có thể sửa, trong phạm vi đồ thị object đã sao chép đúng |

**Không đánh đồng các thuật ngữ:**

- *Unmodifiable* có nghĩa các mutator của **collection nhận được** bị từ chối; không khẳng định các object bên trong cũng bất biến.
- *Shallow copy* là sao chép **container và các tham chiếu** tới phần tử, không tự sao chép trạng thái của phần tử.
- *Defensive copy* là sao chép ở ranh giới nhận/trả dữ liệu để tránh mã khác sửa dữ liệu của mình ngoài ý muốn.
- *Deep copy* theo nghĩa đầy đủ là sao chép **toàn bộ trạng thái có thể thay đổi** trong phạm vi đồ thị object cần độc lập. Điều này phụ thuộc mô hình dữ liệu; không có một lệnh Java collections tự suy luận cách clone mọi class.
- *Immutable data* yêu cầu tất cả những phần trạng thái có thể quan sát từ object đều ổn định; record hoặc tham chiếu `final` tự nó không đủ nếu bên trong còn giữ object mutable.

Nếu phần tử sâu nhất là `String` (bất biến), snapshot từng tầng list thường đã đủ. Nếu phần tử là `Customer` có setter, chụp lại chỉ các list vẫn chưa đủ.

## 3. Ví dụ sai thường gặp: chặn sửa bên ngoài nhưng lộ list con

Xét dữ liệu hai tầng:

~~~java
var firstRow = new ArrayList<>(List.of("A", "B"));
var source = new ArrayList<List<String>>();
source.add(firstRow);

var outerCopy = List.copyOf(source);
~~~

Sau khi `outerCopy` được tạo:

~~~java
// Lỗi runtime: list ngoài không sửa được.
// outerCopy.add(List.of("X"));

// VẪN HỢP LỆ: list con là ArrayList còn sửa được.
outerCopy.get(0).add("C");

System.out.println(outerCopy); // [[A, B, C]]
~~~

Lệnh `outerCopy.get(0).add("C")` không phải sửa **list ngoài**. Nó lấy tham chiếu tới list con rồi gọi `add` trên chính list con mutable. `List.copyOf` không chặn thao tác này.

Mã khác cũng có thể giữ tham chiếu `firstRow` để sửa:

~~~java
firstRow.set(0, "X");
System.out.println(outerCopy); // [[X, B, C]]
~~~

Giờ cả hai phép sửa qua `outerCopy.get(0)` và qua `firstRow` đều tác động cùng object. Vấn đề không nằm ở cú pháp Java 10; vấn đề nằm ở **aliasing**: nhiều tham chiếu chia sẻ cùng một đối tượng mutable.

### `Collections.unmodifiableList(source)` còn là live view

~~~java
var source = new ArrayList<List<String>>();
var row = new ArrayList<>(List.of("A"));
source.add(row);

var view = Collections.unmodifiableList(source);
var outerCopy = List.copyOf(source);

source.add(new ArrayList<>(List.of("B")));
row.add("C");

System.out.println(view);      // [[A, C], [B]]
System.out.println(outerCopy); // [[A, C]]
~~~

- `view` phản ánh thao tác **thêm list con mới vào source** vì đây là unmodifiable view của backing list `source`.
- `outerCopy` không phản ánh list con mới, vì đã ghi nhận cấu trúc ngoài lúc copy.
- **Cả hai** vẫn nhìn thấy `row.add("C")`, do cùng tham chiếu tới list con mutable.

Không nên gọi `outerCopy` là deep copy chỉ vì nó không nhận list con mới sau khi `source.add(...)`.

## 4. Cách sao chép đúng cho `List<List<String>>`

Khi phần tử cuối cùng là `String` hoặc một kiểu bất biến, ta cần sao chép **mỗi list con**, rồi tạo một list ngoài không sửa được:

~~~java
// Giả sử input có kiểu List<List<String>> và không có null.
List<List<String>> snapshot = input.stream()
        .map(List::copyOf)
        .toList();
~~~

Giải thích từng bước:

1. `input.stream()` duyệt các list con theo encounter order của `List` ngoài.
2. `map(List::copyOf)` tạo một **list không sửa được** từ nội dung từng list con. Những thay đổi về phần tử/thứ tự trên list con **nguồn** sau đó không phản ánh vào list con đã chụp.
3. `toList()` của `Stream` (Java 16+) tạo **list ngoài không sửa được** và giữ encounter order nếu có.
4. Bởi các phần tử cuối là `String` bất biến, không còn một object mutable là nội dung sâu nhất bị chia sẻ để sửa.

Ví dụ:

~~~java
// Trong phương thức, Java 17+.
var row = new ArrayList<>(List.of("A"));
var source = new ArrayList<List<String>>();
source.add(row);

var snapshot = source.stream()
        .map(List::copyOf)
        .toList();

row.add("B");
source.add(new ArrayList<>(List.of("C")));

System.out.println(source);   // [[A, B], [C]]
System.out.println(snapshot); // [[A]]
~~~

Kết quả `snapshot` giữ cả số lượng hàng, thứ tự hàng và nội dung từng hàng tại thời điểm lấy snapshot. Mã ngoài không thể gọi `snapshot.add(...)` hay `snapshot.get(0).add(...)` để sửa cấu trúc ở hai cấp.

**Thay thế tương đương từ Java 10** (không dùng `Stream.toList()` của Java 16):

~~~java
List<List<String>> snapshot = List.copyOf(
        input.stream()
                .map(List::copyOf)
                .collect(java.util.stream.Collectors.toList())
);
~~~

`Collectors.toList()` tự nó không cam kết list kết quả có thể sửa hay không, nhưng `List.copyOf(...)` ở lớp ngoài bảo đảm snapshot ngoài không sửa được. `List.copyOf` ở mapper bảo đảm từng list con không sửa được. Cách đầu ngắn hơn nếu dự án chạy Java 17+.

### Dùng phương thức có tên để rõ hợp đồng

~~~java
// Đặt trong một class; Java 17+.
static List<List<String>> copyTable(List<? extends List<String>> source) {
    return source.stream()
            .map(List::copyOf)
            .toList();
}
~~~

Chữ ký `List<? extends List<String>>` cho phép tiếp nhận những subtype phù hợp của list con; giá trị trả về là `List<List<String>>`. Tên `copyTable` chỉ thể hiện thao tác ở **hai tầng list**, không nên hứa nó deep-copy một object tùy ý nếu sau này kiểu phần tử đổi từ `String` sang một class mutable.

## 5. Map chứa List: phải sao chép cả value

Trường hợp thực tế rất phổ biến:

~~~java
var names = new ArrayList<>(List.of("Mai"));
var source = new HashMap<String, List<String>>();
source.put("team", names);
~~~

Chỉ viết:

~~~java
var outerMapCopy = Map.copyOf(source);
~~~

sẽ tạo một Map **không sửa được** và độc lập với thao tác thêm/xóa entry ở Map nguồn. Tuy nhiên, **value vẫn là cùng list `names`**:

~~~java
names.add("Lan");

System.out.println(outerMapCopy.get("team")); // [Mai, Lan]
~~~

Bạn không thể `outerMapCopy.put("other", ...)`, nhưng có thể gọi `outerMapCopy.get("team").add("X")` nếu value đó là `ArrayList`. Đây là lỗ hổng thường gặp ở API kiểu `Map<String,List<String>>`.

### Chụp cấu trúc cả Map và các List value

~~~java
// Đặt bên trong một class; Java 17+.
static Map<String, List<String>> copyMapOfLists(
        Map<String, ? extends List<String>> source
) {
    var copied = new HashMap<String, List<String>>();
    source.forEach((key, values) -> copied.put(key, List.copyOf(values)));
    return Map.copyOf(copied);
}
~~~

- `List.copyOf(values)` chụp từng list value.
- `HashMap` trung gian chỉ dùng để xây các ánh xạ mới.
- `Map.copyOf(copied)` tạo Map kết quả không sửa được.
- Những thay đổi của `source.put(...)` hoặc `values.add(...)` **sau đó** không thay đổi cấu trúc snapshot.
- Không có cam kết về **thứ tự duyệt Map** từ `Map.copyOf`. Nếu kết quả cần thứ tự key xác định, dùng một chiến lược có thứ tự riêng (mục 9).

Cách viết bằng stream nếu phù hợp dự án:

~~~java
// Đoạn minh họa trong một class, import java.util.stream.Collectors.
static Map<String, List<String>> copyMapOfListsStream(
        Map<String, ? extends List<String>> source
) {
    return source.entrySet().stream()
            .collect(Collectors.toUnmodifiableMap(
                    Map.Entry::getKey,
                    entry -> List.copyOf(entry.getValue())
            ));
}
~~~

`Collectors.toUnmodifiableMap` có từ Java 10. Map nguồn đã bảo đảm mỗi key là duy nhất, vì thế overload hai mapper phù hợp trong trường hợp này. Nó không cho phép null key/value và cũng không bảo đảm thứ tự duyệt; `List.copyOf` ở value mapper từ chối list con null hoặc phần tử null.

Nếu cần **mọi value** cho mỗi key, giữ các list như trên, không dùng một merger chọn một value và làm mất thông tin khi tập hợp dữ liệu từ stream có key trùng. Nếu phải tổng hợp từ các bản ghi riêng, hãy xác định chính sách grouping trước rồi chụp các list kết quả.

## 6. Set chứa object mutable và object dùng làm key

Một `Set.copyOf` từ Java 10 tạo set không sửa được, nhưng chỉ bảo vệ cấu trúc tập phần tử. Nếu element là object mutable, nó vẫn có thể bị sửa.

~~~java
// Class minh họa, có thể đặt trong class chứa main.
static final class MutableProduct {
    String code;

    MutableProduct(String code) {
        this.code = code;
    }
}
~~~

~~~java
// Trong phương thức.
var item = new MutableProduct("A");
var source = new HashSet<MutableProduct>();
source.add(item);
var copy = Set.copyOf(source);

item.code = "B"; // Object vẫn mutable.
~~~

Trong ví dụ này class `MutableProduct` **không override `equals/hashCode`**, nên việc đổi `code` không làm thay đổi định nghĩa identity-based equality mặc định. Nhưng nếu class thật dùng `code` để tính `equals/hashCode`, sửa trường đó khi object đã nằm trong một `HashSet`/`Map` có thể làm tra cứu `contains`/`get` hoạt động không như mong muốn.

**Khuyến nghị:** các phần tử Set và key Map nên có equality/hash code ổn định trong suốt thời gian được dùng làm key/element. Với snapshot cần dữ liệu bất biến, cân nhắc chuyển chúng sang **value object bất biến** thay vì chỉ chụp Set/Map bên ngoài.

Một lưu ý khác: `Set.copyOf` **không cam kết iteration order**, ngay cả khi đầu vào là `LinkedHashSet` hoặc `TreeSet`. Nó cũng có quy tắc loại duplicate theo `equals`. Vì vậy, “sao chép sâu” ở đây phải tách bạch khỏi **sắp xếp** và **chính sách trùng phần tử**.

## 7. Nếu object bên trong mutable: phải sao chép trạng thái đến tầng đó

Giả sử kiểu phần tử không phải `String` mà là một class có setter:

~~~java
// Đoạn thành viên class.
static final class MutableItem {
    private String label;

    MutableItem(String label) {
        this.label = label;
    }

    void rename(String newLabel) {
        this.label = newLabel;
    }

    String label() {
        return label;
    }
}
~~~

Viết:

~~~java
var snapshot = source.stream()
        .map(List::copyOf)
        .toList();
~~~

với `source` kiểu `List<List<MutableItem>>` **vẫn chỉ chụp hai tầng collection**, không tạo thêm bản sao của mỗi `MutableItem`. Nếu mã gốc còn giữ tham chiếu tới `MutableItem` và gọi `rename`, nhãn đọc từ snapshot sẽ thay đổi.

### Chuyển sang immutable value object

Với Java 17, có thể dùng một `record` đơn giản:

~~~java
// Record minh họa ở cấp class/file, không đặt nguyên dòng vào main.
record ItemView(String label) {}
~~~

`String` là immutable, nên `ItemView` như trên không chứa tham chiếu tới trạng thái mutable khác (với điều kiện không có thêm cơ chế bên ngoài làm biến đổi nội dung). Ta có thể chụp cả trạng thái phần tử:

~~~java
// Trong phương thức, giả sử source có kiểu List<List<MutableItem>>.
List<List<ItemView>> snapshot = source.stream()
        .map(group -> group.stream()
                .map(item -> new ItemView(item.label()))
                .toList())
        .toList();
~~~

Các lớp được bảo vệ:

1. **Object phần tử:** `new ItemView(item.label())` ghi nhận giá trị `label` hiện tại trong object mới.
2. **List con:** `group.stream()...toList()` tạo danh sách không sửa được chứa các `ItemView` mới.
3. **List ngoài:** `source.stream()...toList()` tạo danh sách ngoài không sửa được.

~~~java
// Giả sử item là MutableItem ban đầu.
item.rename("Sau khi chụp");

// Mọi ItemView đã tạo vẫn lưu label cũ.
~~~

Với đồ thị object phức tạp có liên kết vòng, nhiều object dùng chung, trường con mutable hoặc tài nguyên không thể sao chép, “deep copy” cần **thiết kế riêng**: quyết định giữ hay tách alias, xử lý cycle, tài nguyên bên ngoài, performance và điều kiện đồng bộ. Không có phương thức `List.copyOf` nào tự làm điều đó.

### Record không mặc nhiên bất biến sâu

~~~java
// Đây là record minh họa nhưng CHƯA thực hiện defensive copy.
record UnsafeRows(List<String> values) {}
~~~

Trường `values` trong record là `final`, nhưng object `List` được giữ trong đó có thể vẫn là một `ArrayList` mutable. Ai còn tham chiếu list đầu vào có thể gọi `add`; accessor `values()` cũng trả tham chiếu list đó. `record` không tự tạo bản sao và không làm element mutable bất biến.

Khi dùng record làm DTO/state đọc, cần làm rõ chiến lược phòng vệ ở constructor và (khi cần) accessor.

## 8. Defensive copy ngay ở ranh giới class hoặc record

Khi một class muốn nhận dữ liệu lồng nhau rồi bảo vệ invariant, nên **chụp các tầng mutable ngay trong constructor** thay vì chỉ làm việc đó ở nơi gọi.

### Record sao chép list hai tầng

~~~java
// Record minh họa ở cấp class/file, chạy được trên Java 17+.
record Catalog(List<List<String>> groups) {
    Catalog {
        groups = groups.stream()
                .map(List::copyOf)
                .toList();
    }
}
~~~

Trong **compact canonical constructor** của record, biến tham số `groups` có thể được gán lại bằng snapshot; Java sẽ dùng giá trị tham số cuối để khởi tạo component field. Vì hai tầng list đã không sửa được và `String` bất biến, accessor `groups()` có thể trả về cấu trúc đó mà không làm rò rỉ list mutable.

~~~java
// Trong phương thức, Java 17+.
var row = new ArrayList<>(List.of("A"));
var input = new ArrayList<List<String>>();
input.add(row);

var catalog = new Catalog(input);

row.add("B");
input.clear();

System.out.println(catalog.groups()); // [[A]]
~~~

**Tại sao chỉ copy ở constructor là đủ trong ví dụ này?** Vì tất cả tầng lưu trạng thái đều đã được làm không sửa được, và thành phần cuối cùng là `String` bất biến. Nếu record chứa `byte[]` hoặc `List<MutableItem>`, chỉ chụp list chưa làm phần tử bất biến; cần chụp trạng thái sâu hơn và có thể phải bảo vệ accessor.

### Constructor và accessor khi còn phần tử mutable

Nếu component của record là một mảng `byte[]`, mảng đó vẫn mutable dù field là `final`. Một cách phòng vệ là **clone cả lúc nhận lẫn lúc trả**:

~~~java
// Record minh họa ở cấp class, Java 17+.
record BinaryPayload(byte[] bytes) {
    BinaryPayload {
        bytes = bytes.clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }
}
~~~

- Constructor clone mảng đầu vào, nên người gọi sửa mảng gốc về sau không làm payload đổi.
- Accessor clone khi trả về, nên người gọi không thể sửa mảng nội bộ qua mảng nhận được.
- Nếu mảng chứa các object mutable (không phải `byte` nguyên thủy), `clone()` chỉ tạo bản sao **mảng ngoài**, vẫn cần xử lý object bên trong nếu muốn bất biến sâu.

Đây là ví dụ rõ ràng về lý do phải đánh giá **từng tầng** chứ không “thấy record nên mặc định an toàn”.

## 9. Chương trình hoàn chỉnh Java 17+ và stdout chính xác

Chương trình minh họa bốn trường hợp: live view, shallow copy, snapshot hai tầng List, snapshot Map có List value và snapshot sâu đến object phần tử. Nó còn kiểm tra record defensive copy và khả năng chống sửa ở cả hai tầng.

Lưu file **`NestedReadOnlyDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class NestedReadOnlyDemo {

    static final class MutableItem {
        private String label;

        MutableItem(String label) {
            this.label = label;
        }

        void rename(String newLabel) {
            this.label = newLabel;
        }

        String label() {
            return label;
        }
    }

    record ItemView(String label) {}

    record Catalog(List<List<String>> groups) {
        Catalog {
            groups = groups.stream()
                    .map(List::copyOf)
                    .toList();
        }
    }

    static List<List<String>> copyTwoLevels(
            List<? extends List<String>> source
    ) {
        return source.stream()
                .map(List::copyOf)
                .toList();
    }

    static Map<String, List<String>> copyMapOfLists(
            Map<String, ? extends List<String>> source
    ) {
        var copied = new HashMap<String, List<String>>();
        source.forEach((key, values) ->
                copied.put(key, List.copyOf(values)));
        return Map.copyOf(copied);
    }

    public static void main(String[] args) {
        var row = new ArrayList<>(List.of("A", "B"));
        var source = new ArrayList<List<String>>();
        source.add(row);

        var liveView = Collections.unmodifiableList(source);
        var outerOnly = List.copyOf(source);
        var twoLevels = copyTwoLevels(source);

        row.add("C");
        source.add(new ArrayList<>(List.of("Z")));

        System.out.println("source=" + source);
        System.out.println("liveView=" + liveView);
        System.out.println("outerOnly=" + outerOnly);
        System.out.println("twoLevels=" + twoLevels);
        System.out.println("outerSameInner=" + (outerOnly.get(0) == row));
        System.out.println("twoLevelsSameInner=" + (twoLevels.get(0) == row));

        var names = new ArrayList<>(List.of("Mai"));
        var grouped = new LinkedHashMap<String, List<String>>();
        grouped.put("team", names);

        var mapOuterOnly = Map.copyOf(grouped);
        var mapTwoLevels = copyMapOfLists(grouped);

        names.add("Lan");
        grouped.put("new", List.of("X"));

        System.out.println("mapOuterValue=" + mapOuterOnly.get("team"));
        System.out.println("mapTwoLevelsValue=" + mapTwoLevels.get("team"));
        System.out.println("mapTwoLevelsHasNew=" + mapTwoLevels.containsKey("new"));

        var item = new MutableItem("old");
        var group = new ArrayList<MutableItem>();
        group.add(item);
        var mutableGroups = new ArrayList<List<MutableItem>>();
        mutableGroups.add(group);

        var copiedContainers = mutableGroups.stream()
                .map(List::copyOf)
                .toList();

        var valueSnapshot = mutableGroups.stream()
                .map(g -> g.stream()
                        .map(e -> new ItemView(e.label()))
                        .toList())
                .toList();

        item.rename("new");

        System.out.println("copiedMutable=" +
                copiedContainers.get(0).get(0).label());
        System.out.println("valueSnapshot=" +
                valueSnapshot.get(0).get(0).label());

        var recordInner = new ArrayList<>(List.of("v1"));
        var recordInput = new ArrayList<List<String>>();
        recordInput.add(recordInner);

        var catalog = new Catalog(recordInput);
        recordInner.add("v2");
        recordInput.clear();

        System.out.println("catalog=" + catalog.groups());

        try {
            twoLevels.get(0).add("D");
        } catch (UnsupportedOperationException expected) {
            System.out.println("innerMutationBlocked=true");
        }

        try {
            twoLevels.add(List.of("D"));
        } catch (UnsupportedOperationException expected) {
            System.out.println("outerMutationBlocked=true");
        }

        var containsNullGroup = new ArrayList<List<String>>();
        containsNullGroup.add(null);

        try {
            copyTwoLevels(containsNullGroup);
        } catch (NullPointerException expected) {
            System.out.println("nullGroupRejected=true");
        }
    }
}
~~~

Biên dịch và chạy với JDK hỗ trợ Java 17:

~~~bash
javac --release 17 NestedReadOnlyDemo.java
java NestedReadOnlyDemo
~~~

**Stdout chính xác** (không dựa vào thứ tự duyệt HashMap):

~~~text
source=[[A, B, C], [Z]]
liveView=[[A, B, C], [Z]]
outerOnly=[[A, B, C]]
twoLevels=[[A, B]]
outerSameInner=true
twoLevelsSameInner=false
mapOuterValue=[Mai, Lan]
mapTwoLevelsValue=[Mai]
mapTwoLevelsHasNew=false
copiedMutable=new
valueSnapshot=old
catalog=[[v1]]
innerMutationBlocked=true
outerMutationBlocked=true
nullGroupRejected=true
~~~

### Giải thích kết quả

1. `liveView` là view trên chính `source`: sau khi thêm list con `[Z]`, view thấy thêm hàng; thay nội dung `row` làm view thấy `C`.
2. `outerOnly` là `List.copyOf(source)` tạo **trước** khi sửa nguồn, vì thế chỉ có một hàng, nhưng hàng đó vẫn là object `row` cũ và đã trở thành `[A,B,C]`.
3. `twoLevels` sao chép từng list con rồi chụp list ngoài. Nó giữ `[[A,B]]` và không chia sẻ tham chiếu list con mutable (`twoLevelsSameInner=false`).
4. `mapOuterOnly` là `Map.copyOf(grouped)` nên có cùng list value `names` và thấy `"Lan"`. `mapTwoLevels` đã sao chép value bằng `List.copyOf` nên vẫn là `[Mai]`. Thêm key `new` vào nguồn không phản ánh vào Map snapshot.
5. `copiedContainers` chỉ sao chép container của `MutableItem`, nên nhìn thấy label mới `new`. `valueSnapshot` tạo `ItemView` mới lưu chuỗi `old`, vì thế không thay đổi khi `item.rename(...)`.
6. `Catalog` chụp hai tầng trong compact constructor. Dù sửa list con và xóa list ngoài đầu vào sau đó, `catalog.groups()` vẫn là `[[v1]]`.
7. Hai lời gọi `add` qua `twoLevels` và list con của nó bị từ chối bằng `UnsupportedOperationException`.
8. `List.copyOf(null)` khi mapper gặp **một list con null** làm thao tác tạo snapshot ném `NullPointerException`, được bắt để in `nullGroupRejected=true`.

Chương trình không tạo deep copy tổng quát cho mọi đồ thị object; nó chỉ minh họa **sao chép đủ sâu so với loại dữ liệu cụ thể**. Phần value object chỉ chứa `String` nên có trạng thái không đổi sau khi chụp.

## 10. Null, duplicate, thứ tự và các trường hợp đặc biệt

### Null ở nhiều cấp

`List.copyOf` từ chối nguồn `null` và từng phần tử `null`. Khi dùng với `List<List<String>>`:

- Nếu **list ngoài là null**, `source.stream()` tự gây `NullPointerException`.
- Nếu **một list con là null**, `map(List::copyOf)` gây `NullPointerException` khi gọi `List.copyOf(null)`.
- Nếu **một phần tử trong list con là null**, `List.copyOf(listCon)` gây `NullPointerException`.
- `Map.copyOf` cũng từ chối Map nguồn null, key null và value null.

~~~java
// Đoạn minh họa lỗi runtime, không đặt nối tiếp trong chương trình chạy.
var inner = new ArrayList<String>();
inner.add("A");
inner.add(null);

var source = new ArrayList<List<String>>();
source.add(inner);

// Gây NullPointerException vì một list con chứa null:
var snapshot = source.stream().map(List::copyOf).toList();
~~~

Nếu null có ý nghĩa nghiệp vụ bắt buộc giữ, phải thiết kế snapshot khác. Ví dụ `Collections.unmodifiableList(new ArrayList<>(source))` cho phép giữ null trong source nếu ArrayList hỗ trợ, nhưng chỉ tạo **snapshot cấu trúc một tầng**; cần sao chép từng tầng tương ứng và hiểu giới hạn shallow copy.

Không nên âm thầm loại null trong quá trình snapshot nếu người gọi kỳ vọng lưu được trạng thái “chưa biết/chưa nhập”. Đầu tiên cần chọn chính sách null, sau đó chọn API.

### Duplicate

`List.copyOf` giữ mọi phần tử trùng và thứ tự iterator. Nếu danh sách lồng nhau có cùng list con xuất hiện hai lần, copy từng tầng vẫn tạo **hai vị trí**, không tự xóa duplicate. Tuy nhiên nó có thể tạo hai list con không sửa được nhưng bằng nhau theo `equals`. Nếu chương trình cần duy trì **quan hệ alias** (“hai vị trí phải trỏ tới cùng một object”) trong deep copy, cần thiết kế cách dùng bảng ghi nhớ object đã copy; cách `map(List::copyOf)` đơn giản không cam kết giữ identity graph như vậy.

`Set.copyOf` lại loại duplicate theo hợp đồng Set và không cam kết thứ tự iterator. Chỉ dùng Set khi ý nghĩa dữ liệu là membership, không phải thứ tự hoặc số lần xuất hiện.

### Thứ tự

`List.copyOf` giữ iteration order của collection nguồn khi tạo list. Với list ngoài và list con, cách copy từng tầng ở trên giữ thứ tự các hàng/cột nếu cả hai nguồn có order đáng tin. Nhưng `Map.copyOf` và `Set.copyOf` không cam kết giữ thứ tự chèn của `LinkedHashMap`/`LinkedHashSet`.

Nếu cần xuất JSON/CSV theo thứ tự cố định, nên dùng list có thứ tự, Map có backing `LinkedHashMap` được copy rồi bọc unmodifiable view, hoặc sort theo comparator trước khi xuất; không dựa vào `toString()` của Map/Set copy.

### Identity và việc có thực sự cấp phát mới hay không

`List.copyOf`/`Map.copyOf` có thể tái sử dụng một nguồn vốn đã unmodifiable phù hợp; không đặt điều kiện nghiệp vụ vào `source != snapshot` hay `source == snapshot`. Các factory collection này có hợp đồng value-based. Trong ví dụ với nguồn **mutable ArrayList**, `List.copyOf(row)` tạo nội dung độc lập về cấu trúc, nhưng không có lý do kiểm tra class nội bộ của list copy.

### Dữ liệu chia sẻ qua nhiều nhánh và vòng tham chiếu

Với object graph phức tạp, các vòng tham chiếu có thể làm thuật toán đệ quy sao chép ngây thơ lặp vô hạn. Nếu một object được tham chiếu từ nhiều nhánh, tạo bản sao riêng cho mỗi nhánh có thể vô tình làm thay đổi quan hệ “dùng chung object”. Một deep-copy có chủ đích cần xác định phạm vi, xử lý cycle/alias, dùng cấu trúc theo dõi các object đã sao chép nếu cần, và đặc biệt không copy tài nguyên như socket/file handle một cách máy móc.

**Không** nên xem Java serialization hay `Cloneable` là “phương pháp deep copy chuẩn cho mọi object”. Việc implement `clone()` có thể vẫn chỉ là shallow copy; serialization đòi điều kiện/thiết kế riêng và có thể kéo theo vấn đề bảo mật, tương thích. Khi cần object immutable, xây dữ liệu thành value object rõ ràng thường dễ kiểm soát hơn.

## 11. Luồng đồng thời và tính nhất quán của snapshot

Một snapshot unmodifiable **không tự bảo đảm** rằng toàn bộ dữ liệu nguồn được chụp ở **một thời điểm nguyên tử** nếu các thread khác đang sửa nguồn trong quá trình copy.

Ví dụ nguy cơ:

~~~java
// Không dùng mẫu thiếu đồng bộ này để chụp một cấu trúc nguồn
// đang bị thread khác sửa cùng lúc:
var snapshot = mutableRows.stream()
        .map(List::copyOf)
        .toList();
~~~

Nếu có thay đổi xảy ra giữa lúc sao chép các hàng, một số hàng có thể phản ánh trạng thái mới, các hàng khác vẫn là trạng thái cũ; thậm chí stream/iterator có thể phát sinh lỗi tùy implementation. Tính unmodifiable của kết quả **sau khi tạo** không khắc phục được tính không nhất quán **trong lúc tạo**.

Giải pháp tùy mô hình ứng dụng:

- Bảo đảm nguồn không bị sửa trong suốt lúc tạo snapshot, bằng khóa/synchronization được bên ghi và bên đọc cùng tuân thủ.
- Dùng dữ liệu bất biến theo phiên bản (immutable state) và thay toàn bộ tham chiếu tới phiên bản mới, để người đọc chụp một phiên bản ổn định.
- Với luồng xử lý dữ liệu lớn, xác định giới hạn transaction/snapshot và consistency trước khi chọn cấu trúc.
- Nếu element mutable được chia sẻ và tiếp tục bị đổi, phải sao chép **trạng thái element** dưới cơ chế nhất quán phù hợp, chứ không chỉ khóa collection ngoài.

Không nên suy ra rằng `Collections.synchronizedList` trên một tầng tự giải quyết mọi thay đổi vào các list con. Việc đồng bộ cần bảo vệ toàn bộ trạng thái có liên quan.

## 12. Lỗi thường gặp và cách sửa

| Lỗi/giả định | Vì sao có vấn đề? | Hướng xử lý |
| --- | --- | --- |
| `List.copyOf(listOfLists)` là deep copy | Chỉ list ngoài không sửa được; list con vẫn chia sẻ tham chiếu | Copy từng list con: `stream().map(List::copyOf).toList()` |
| `Collections.unmodifiableList(list)` tạo snapshot | Đây là live view trên backing list | Tạo container mới trước khi bọc, hoặc dùng `List.copyOf` |
| `Map.copyOf(mapOfLists)` làm các list value không sửa được | Value là object, copy Map không copy value | `List.copyOf` từng value trước khi `Map.copyOf` |
| `record` là bất biến sâu dù chứa `ArrayList` hoặc `byte[]` | Field final không làm object được tham chiếu bất biến | Defensive copy ở constructor; bảo vệ accessor nếu còn object mutable |
| `source.stream().map(List::copyOf).toList()` xử lý được `MutableItem` | Chỉ copy list, chưa copy object Item | Sao chép/biến đổi từng item thành immutable value object |
| Sao chép Set nghĩa là giữ insertion order | `Set.copyOf` không cam kết order | Giữ ordered list hoặc tạo snapshot dựa trên LinkedHashSet/TreeSet phù hợp |
| Copy xong vẫn gọi `snapshot.get(0).add(...)` được | Nếu list con chưa copy thì được; nếu đã copy thì bị từ chối | Test cả mutator ngoài lẫn mutator trong |
| Bản sao bắt buộc có identity khác nguồn | Factory có thể tái sử dụng nguồn unmodifiable | Dựa trên contract nội dung, không dựa identity |
| Null ở list con được giữ tự động | `List.copyOf` từ chối null ở mọi lần gọi | Chính sách null riêng, chọn chiến lược sao chép phù hợp |
| Snapshot unmodifiable tự an toàn đa luồng | Quá trình chụp có thể tranh chấp với thread ghi | Thiết kế đồng bộ/snapshot nhất quán |
| Deep copy luôn là lựa chọn tốt nhất | Có chi phí CPU/bộ nhớ và có thể phá alias/cycle hữu ích | Sao chép đủ sâu theo nhu cầu và ranh giới sở hữu |
| Dùng `==` để kiểm tra hai danh sách có dữ liệu giống nhau | Identity khác bình đẳng giá trị | Dùng `equals` khi cần so nội dung, quản lý alias riêng khi cần |

## 13. Checklist thiết kế và bài tập

### Checklist trước khi công bố dữ liệu chỉ đọc

1. **Vẽ cấu trúc lồng nhau:** là `List<List<String>>`, `Map<K,List<V>>`, `List<MutableItem>`, array trong record, hay một đồ thị object có cycle?
2. **Đánh dấu mọi tầng mutable:** list ngoài, list con, map value, phần tử và tham chiếu tới chúng được giữ ở nơi khác.
3. **Xác định hợp đồng cần có:** chỉ chặn sửa qua API, snapshot không đổi về cấu trúc, hay bất biến cả giá trị?
4. **Dùng copy đúng tầng:** `List.copyOf`/`Map.copyOf` cho container; lặp qua từng nested collection để copy tiếp; tạo value object mới nếu element mutable cần đóng băng trạng thái.
5. **Không đánh mất dữ liệu:** cân nhắc `null`, duplicate, iteration order, comparator và quan hệ alias theo nhu cầu thật.
6. **Đặt defensive copy ở ranh giới:** constructor, factory hoặc hàm trả dữ liệu nên bảo vệ invariant; tránh đẩy nghĩa vụ phòng vệ cho mọi caller.
7. **Test đường sửa từ hai phía:** sửa nguồn ngoài, sửa list con, sửa object element; đồng thời thử mutator trên snapshot ngoài và trong.
8. **Thận trọng với concurrency:** chọn điểm chụp dữ liệu nhất quán. Một lần copy không phải transaction.
9. **Cân nhắc hiệu năng:** với dữ liệu sâu/lớn, định lượng lượng sao chép thực sự cần thiết; dữ liệu đã bất biến có thể chia sẻ an toàn trong phạm vi hợp đồng.
10. **Kiểm tra JDK mục tiêu:** `List.copyOf`/`Map.copyOf` từ Java 10; record và `Stream.toList()` sử dụng trong chương trình từ Java 16 nên ví dụ yêu cầu Java 17+.

### Câu hỏi tự đánh giá

**Câu 1.** `var nested = List.copyOf(listOfMutableLists);` có ngăn `nested.get(0).add("A")` không?

**Đáp án:** Không chắc, vì list con có thể vẫn là mutable list được giữ từ nguồn. `List.copyOf` chỉ làm list ngoài unmodifiable.

**Câu 2.** Khi cả hai tầng list đã được sao chép bằng `source.stream().map(List::copyOf).toList()`, có sửa được `snapshot.get(0).add(...)` không?

**Đáp án:** Không. `List.copyOf` ở từng list con từ chối mutator, và `Stream.toList()` ở list ngoài cũng trả list không sửa được.

**Câu 3.** Sao chép hai tầng `List<List<MutableItem>>` đã làm object `MutableItem` bất biến chưa?

**Đáp án:** Chưa. Hai tầng list không sửa được nhưng object phần tử vẫn có thể bị thay đổi qua tham chiếu khác.

**Câu 4.** `Map.copyOf(mapOfLists)` có giữ nguyên nội dung list value khi người khác gọi `listValue.add(...)` không?

**Đáp án:** Không. Map copy giữ value tham chiếu cùng object list, nên có thể nhìn thấy thay đổi nội dung list đó.

**Câu 5.** Với `record Catalog(List<List<String>> groups)`, chỉ định nghĩa record mà không copy có an toàn không?

**Đáp án:** Không nếu đầu vào có mutable list ngoài/list con. Cần chụp hai tầng trong constructor hoặc dùng mô hình chia sẻ bất biến có hợp đồng rõ ràng.

**Câu 6.** Vì sao `byte[]` trong record cần xử lý cả constructor lẫn accessor?

**Đáp án:** Mảng mutable; nếu chỉ clone đầu vào mà accessor trả lại mảng nội bộ, người gọi vẫn có thể sửa mảng ấy. Clone khi nhận và khi trả làm giảm rò rỉ trạng thái.

**Câu 7.** Nếu nguồn lồng nhau được cập nhật từ nhiều luồng, `map(List::copyOf)` có tự cho ảnh chụp đồng thời nhất quán không?

**Đáp án:** Không. Cần cơ chế đồng bộ hoặc mô hình dữ liệu bất biến theo phiên bản để lấy snapshot nhất quán.

**Câu 8.** Có nên deep-copy toàn bộ object graph bất kể yêu cầu?

**Đáp án:** Không. Sao chép sâu có chi phí và có thể thay đổi alias identity/cycle; hãy xác định ranh giới dữ liệu mutable cần cô lập, rồi chọn cơ chế sao chép phù hợp.

## 14. Tài liệu chính thức đang áp dụng

- [Oracle Java SE 25 — `List.copyOf`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): snapshot list không sửa được, thứ tự đầu vào, null và giới hạn khi phần tử mutable.
- [Oracle Java SE 26 — `Map.copyOf`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): Map không sửa được, độc lập về entry với thay đổi nguồn, nhưng key/value mutable có thể thay đổi trạng thái.
- [Oracle Java SE 25 — `Collection`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collection.html): quy tắc unmodifiable collection và việc unmodifiable không đồng nghĩa immutable nếu phần tử mutable.
- [Dev.java — Using Records to Model Immutable Data](https://dev.java/learn/using-record-to-model-immutable-data/): defensive copy trong constructor/accessor khi record có thành phần mutable.
- [Oracle Java SE 17 — `Stream.toList`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()): thu stream thành list không sửa được theo encounter order; có từ Java 16.
- [Oracle Java SE 17 — `Collections.unmodifiableList`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): live view trên list gốc; phân biệt với snapshot.
- [Oracle Java SE 17 — `Collectors.toUnmodifiableMap`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableMap(java.util.function.Function,java.util.function.Function)): collector tạo Map không sửa được khi chuyển entry stream.
- [Oracle Java SE 17 — `Set.copyOf`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)): membership không trùng và iteration order không cam kết.

**Kết luận:** collection chỉ đọc **không mặc nhiên là deep copy**. Với `List<List<String>>`, hãy chụp **từng List** nếu cần snapshot ổn định ở hai tầng; với `Map<K,List<V>>`, hãy chụp cả Map và list value; với object mutable ở tầng sâu hơn, hãy tạo trạng thái/value object bất biến hoặc defensive copy tương ứng. Bảo vệ dữ liệu phải phù hợp với **toàn bộ những tham chiếu mutable còn có thể bị sửa từ bên ngoài**, không chỉ phương thức `add` của container ngoài.