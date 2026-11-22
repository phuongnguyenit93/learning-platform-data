# Kiểm thử phần tử có thể thay đổi trong collection chỉ đọc

## 1. Mục tiêu của bài thực hành

Một lỗi hiểu nhầm khá nguy hiểm khi dùng Java Collections là cho rằng **danh sách không cho `add`, `remove` hay `set`** thì mọi dữ liệu bên trong nó cũng bất biến.

Ví dụ:

~~~java
class Box {
    int count;
    Box(int count) { this.count = count; }
}

Box box = new Box(1);
List<Box> readOnly = List.of(box);

// readOnly.add(new Box(2)); // UnsupportedOperationException
readOnly.get(0).count = 9;    // Hợp lệ
System.out.println(readOnly.get(0).count); // 9
~~~

Vùng collection ở đây **không cho sửa cấu trúc**, nhưng phần tử `box` là một đối tượng **mutable**. Khi đọc lại qua collection, người dùng vẫn thấy giá trị mới. Điều này **không mâu thuẫn** với hợp đồng của `List.of` hoặc `List.copyOf`.

Đề mục thuộc nhóm **“Thực hành tổng hợp”** của Java 10: **“Kiểm thử phần tử có thể thay đổi trong collection chỉ đọc”**. Bài tích hợp các tính năng vẫn còn áp dụng hiện nay:

- `List.of`, `Set.of`, `Map.of` — factory unmodifiable collections từ **Java 9**.
- `List.copyOf`, `Set.copyOf`, `Map.copyOf` và `Collectors.toUnmodifiableList` — các cơ chế unmodifiable snapshot/collector có từ **Java 10**.
- `Collections.unmodifiableList`, `unmodifiableSet`, `unmodifiableMap` — unmodifiable **views** của collection/map gốc.
- `Stream.toList()` — từ **Java 16**, trả unmodifiable list; hữu ích trong Java 17/21/25 hiện đại.
- Các mẫu **defensive copying**, **immutable value objects**, bảo vệ nested collections và API encapsulation.

**Luận điểm cần chứng minh bằng code:** *Không sửa được collection* khác với *không sửa được các đối tượng mà collection đang tham chiếu*. Một unmodifiable collection không phải phép sao chép sâu toàn bộ object graph.

### Kết quả cần đạt

Sau bài, bạn có thể:

1. Phân biệt **read-only view**, **unmodifiable snapshot** và **deep/effective immutability**.
2. Tự viết test chứng minh structural mutators ném `UnsupportedOperationException`.
3. Tự viết test chứng minh phần tử mutable vẫn có thể bị sửa qua reference lấy từ collection.
4. Hiểu **aliasing**: nguồn, snapshot, factory và collector có thể cùng trỏ tới **một object**.
5. Phân biệt `List.copyOf` không phản ánh **thay đổi thành viên của source** với việc nó vẫn quan sát **thay đổi nội tại của object**.
6. Thấy `Collections.unmodifiableList(source)` là **live read-through view**, còn `List.copyOf(source)` cho snapshot về mặt thành viên collection.
7. Kiểm tra tương tự cho **`Map.copyOf` với mutable values**, **`Set.copyOf` với mutable elements**.
8. Tạo nested copies đúng: **copy outer list thôi chưa đủ** nếu inner list mutable.
9. Biết khi nào nên chuyển mutable entity sang **immutable DTO/record snapshot**.
10. Phân biệt `UnsupportedOperationException` và `NullPointerException` trong các factories.
11. Không dựa vào identity, iteration order hoặc loại concrete implementation mà Javadoc không bảo đảm.
12. Hiểu tại sao unmodifiable collection **không tự bảo đảm thread safety**.
13. Xây dựng test rõ ràng, deterministic và có assertions, không chỉ in ra các số rồi tự đoán.
14. Chạy chương trình Java 17+ hoàn chỉnh và đối chiếu stdout thực tế.
15. Tạo test riêng cho API trả collection công khai để tránh lộ quyền sửa trạng thái nội bộ.

## 2. Ba tầng cần phân biệt: vỏ collection, phần tử và trạng thái bên trong

Xét ba câu hỏi độc lập:

**A. Có thể sửa danh sách các reference không?** Ví dụ thêm/xóa một phần tử hoặc thay entry ở index 0.

**B. Có thể sửa trạng thái của đối tượng đang được tham chiếu không?** Ví dụ `user.setName("new")`, `order.setTotal(...)`.

**C. Trạng thái lồng trong đối tượng hoặc nested collection có thể sửa không?** Ví dụ `user.getRoles().add("ADMIN")` hoặc `order.getLines().get(0).setQuantity(99)`.

Nếu chỉ chặn A mà vẫn cho phép B/C, chưa thể gọi toàn bộ dữ liệu là bất biến.

| Khái niệm | Không cho sửa cấu trúc ngoài | Ngăn sửa phần tử mutable | Có thể phản ánh source thay đổi |
| --- | --- | --- | --- |
| `Collections.unmodifiableList(source)` | **Có** — qua view | **Không** | **Có**, là live view. |
| `List.copyOf(source)` | **Có** | **Không** | Không phản ánh thay đổi thành viên của source; **vẫn thấy thay đổi đối tượng cùng tham chiếu**. |
| `List.of(mutableObject)` | **Có** | **Không** | Không có source collection gốc, nhưng phần tử vẫn có thể bị sửa qua alias. |
| `source.stream().collect(toUnmodifiableList())` | **Có** | **Không** | Không cập nhật thành viên từ source, nhưng vẫn giữ object references. |
| `source.stream().toList()` | **Có** (Java 16+) | **Không** | Không cập nhật thành viên từ source, nhưng giữ phần tử theo reference. |
| `List.copyOf(sourceOfImmutableValues)` | **Có** | Nếu values thật sự immutable thì không có trạng thái để sửa. | Một **effective immutable snapshot** nếu không có những đường mutable khác. |

Theo Oracle Javadoc **`Collection`** và **`List`**, **unmodifiable không đồng nghĩa immutable** khi phần tử mutable. Hai unmodifiable lists vẫn có thể thay đổi kết quả `equals` hoặc `hashCode` sau khi đối tượng chứa bên trong bị sửa.

### 2.1. “Chỉ đọc” là giới hạn qua một giao diện, không tự khóa object

Nếu API trả:

~~~java
List<MutableOrder> orders = service.getOrders();
~~~

và collection là unmodifiable thì client không được `orders.add(...)`. Nhưng client vẫn có thể gọi:

~~~java
orders.get(0).setStatus("CANCELLED");
~~~

nếu `MutableOrder` cho phép setter. Đây là **quyền sửa thông qua reference tới phần tử**, không phải sửa danh sách. Nếu đây là dữ liệu nội bộ nghiệp vụ, wrapper unmodifiable **không đủ làm ranh giới bảo mật/encapsulation**.

### 2.2. Aliasing: nhiều container, một phần tử

~~~text
MutableBox box(count=1)
            ^
            |
   +--------+----------+--------------+
   |                   |              |
source ArrayList    List.copyOf     List.of
   |                   |              |
   +-------------------+--------------+
       cùng giữ reference tới box
~~~

Khi một alias gọi `box.setCount(7)`, những danh sách vẫn trỏ tới `box` sẽ đọc được `count=7`. Không có lời hứa nào rằng `List.copyOf` gọi `clone`, copy constructor hoặc Java serialization cho từng phần tử.

**Không kiểm tra deep copying chỉ bằng việc nhìn collection có cùng `size()`.** Muốn phát hiện aliasing, phải thay **state của phần tử** rồi quan sát kết quả.

## 3. Phân biệt `Collections.unmodifiableList` và `List.copyOf`

Đây là hai API dễ bị đánh đồng.

### 3.1. `Collections.unmodifiableList` là live view

~~~java
var source = new java.util.ArrayList<String>();
source.add("A");

var view = java.util.Collections.unmodifiableList(source);

source.add("B");
System.out.println(view.size()); // 2
~~~

`view` **không cho phép** gọi `view.add("C")`. Nhưng `source` vẫn mutable, và các truy vấn trên view **read through** đến source; nên khi nguồn thêm "B", view hiện có hai phần tử.

Javadoc còn ghi rõ những thao tác thay đổi qua view, kể cả qua iterator, đều phải bị từ chối. Tuy vậy nguồn vẫn có thể bị biến đổi nếu còn giữ reference.

**Điểm cần test:** `Collections.unmodifiableList` không phải **snapshot độc lập của thành viên**. Nếu caller vẫn giữ mutable source, không thể dùng view làm bản ghi trạng thái cố định.

### 3.2. `List.copyOf` giữ snapshot thành viên

~~~java
var source = new java.util.ArrayList<String>();
source.add("A");

var copy = java.util.List.copyOf(source);
source.add("B");

System.out.println(source.size()); // 2
System.out.println(copy.size());   // 1
~~~

Theo API **Java 10+**, `List.copyOf` trả unmodifiable list chứa các phần tử được lấy từ source theo iteration order. Nếu source sau đó thêm/xóa/thay **reference thành viên**, returned list không phản ánh các thay đổi ấy.

Nhưng đối tượng mutable bên trong vẫn được chia sẻ:

~~~java
var box = new MutableBox("A", 1);
var source = new java.util.ArrayList<MutableBox>();
source.add(box);

var copy = java.util.List.copyOf(source);
box.setCount(7);
System.out.println(copy.get(0).count()); // 7
~~~

**Mảnh code giả định đã có class `MutableBox`**, không phải file độc lập. Phần 7 cung cấp chương trình đầy đủ.

### 3.3. `copyOf` có thể tái sử dụng unmodifiable list đã có

Oracle Javadoc nói khi đầu vào vốn là unmodifiable list, `List.copyOf` **thường không tạo thêm bản sao**. Các collections từ `List.of`/`List.copyOf` còn được mô tả là **value-based**, không nên dựa vào `==`, identity hash code hoặc synchronization trên returned list.

**Không test:**

~~~java
List<String> a = List.of("A");
List<String> b = List.copyOf(a);
// assert a != b; // SAI: không được đảm bảo tạo instance khác
// assert a == b; // CŨNG SAI: không được đảm bảo tái sử dụng
~~~

Đây là **mảnh mã để nêu phản ví dụ**, không chạy nó như test thành công. Test đúng là **giá trị và hợp đồng hành vi**, không phải identity của chính collection object.

**Phân biệt cực quan trọng:** Có thể so `copy.get(0) == box` trong bài lab vì đang hỏi **reference của phần tử mutable có được dùng chung hay không**. Việc đó khác hoàn toàn với so `copy == source` để suy ra implementation của collection.

## 4. Các factory/collector hiện còn áp dụng

| API | Từ Java | Collection kết quả | Có tự deep-copy phần tử không? |
| --- | --- | --- | --- |
| `List.of(elements...)` | 9 | Unmodifiable `List` | Không. |
| `Set.of(elements...)` | 9 | Unmodifiable `Set` | Không. |
| `Map.of(key,value,...)` | 9 | Unmodifiable `Map` | Không. |
| `List.copyOf(collection)` | 10 | Unmodifiable `List` snapshot thành viên | Không. |
| `Set.copyOf(collection)` | 10 | Unmodifiable `Set` snapshot thành viên | Không. |
| `Map.copyOf(map)` | 10 | Unmodifiable `Map` snapshot entries | Không, keys/values vẫn là objects. |
| `Collectors.toUnmodifiableList()` | 10 | Unmodifiable `List` | Không. |
| `Collectors.toUnmodifiableSet()` | 10 | Unmodifiable `Set` | Không. |
| `Collectors.toUnmodifiableMap(...)` | 10 | Unmodifiable `Map` | Không. |
| `Stream.toList()` | 16 | Unmodifiable `List` | Không. |
| `Collections.unmodifiableList(source)` | Tồn tại từ lâu | Unmodifiable **view** trên source | Không. |

**Ghi chú cập nhật:** `Stream.toList()` là cách viết ngắn gọn, hiện được dùng nhiều trên Java 17+, nhưng **không tồn tại trong Java 10**. Khi muốn target runtime Java 10, dùng `Collectors.toUnmodifiableList()` hoặc `List.copyOf(...)` phù hợp.

### 4.1. `Collectors.toList()` không bảo đảm modifiability

~~~java
var list = stream.collect(java.util.stream.Collectors.toList());
~~~

Javadoc của `Collectors.toList()` **không cam kết** returned list thuộc concrete class nào, có mutable không, thread-safe hay serializable không. Không dùng collector đó như một API contract rằng `add` luôn được hỗ trợ.

Nếu thực sự cần mutable `ArrayList`:

~~~java
var list = stream.collect(
        java.util.stream.Collectors.toCollection(
                java.util.ArrayList::new));
~~~

Đây là **đoạn minh họa**, giả định đã có một `stream` tương thích. Muốn unmodifiable collection với yêu cầu null và thứ tự phù hợp, dùng factory/collector có hợp đồng tường minh.

### 4.2. `Arrays.asList` là fixed-size, không phải unmodifiable

~~~java
var list = java.util.Arrays.asList("A", "B");
list.set(0, "X"); // Hợp lệ
// list.add("C"); // UnsupportedOperationException
~~~

`Arrays.asList` trả list có kích thước cố định được backing bởi array: không cho thay đổi kích thước, nhưng thường **cho `set`** để thay phần tử hiện có. Nếu gọi đây là “immutable list” sẽ sai.

**Test đúng:** kiểm tra riêng `add`, `set` và khả năng thay đổi array nguồn. “Không add được” **không đủ** để kết luận “không sửa được”.

## 5. Thiết kế bộ test: cấu trúc và trạng thái phải kiểm tra riêng

| Test case | Hành động | Expected |
| --- | --- | --- |
| T01 — alias tham chiếu | Tạo `List.copyOf(source)` chứa `MutableBox`, so `copy.get(0)==box` | `true`. |
| T02 — live view | Thêm element vào `source` sau khi tạo `Collections.unmodifiableList` | `view.size` tăng. |
| T03 — snapshot | Thêm element vào `source` sau `List.copyOf` | `copy.size` giữ nguyên. |
| T04 — factory | Tạo `List.of(box)` rồi sửa box qua alias | Giá trị trong factory list đổi. |
| T05 — collector | Tạo `toUnmodifiableList` rồi sửa box | Giá trị từ collector list đổi. |
| T06 — Stream | Tạo `Stream.toList()` rồi sửa box | Giá trị trong list đổi. |
| T07 — sửa qua collection | `copy.get(0).setCount(9)` | Source quan sát cùng object mới. |
| T08 — chặn add | `copy.add(...)` | `UnsupportedOperationException`. |
| T09 — chặn set | `view.set(0,...)` | `UnsupportedOperationException`. |
| T10 — chặn clear/remove | `factory.clear()`, `collected.remove(0)` | `UnsupportedOperationException`. |
| T11 — mutable container mới | `new ArrayList<>(copy)` rồi `add` | Container mới có thể sửa, phần tử vẫn dùng chung. |
| T12 — Map snapshot | `Map.copyOf(sourceMap)`, sau đó thêm mapping vào source | Kích thước map copy không đổi. |
| T13 — mutable Map value | Sửa object value đã có | Value trong copy thay đổi. |
| T14 — Map entry | `entry.setValue(...)` trên `Map.copyOf` | `UnsupportedOperationException`. |
| T15 — Set element | `Set.copyOf(Set.of(box))` | Giữ reference phần tử, chặn `set.add`. |
| T16 — nested shallow | `List.copyOf(List.of(mutableInner))`, sửa inner | List con trong outer thay đổi. |
| T17 — nested copied | `List.copyOf(List.of(List.copyOf(inner)))` | Inner snapshot giữ kích thước cũ. |
| T18 — immutable value DTO | Tạo `record FrozenBox(String,int)` từ mutable box rồi sửa box | Record snapshot giữ giá trị cũ. |
| T19 — null input | `List.copyOf(listContainingNull)` | `NullPointerException`. |
| T20 — wrapper nullable | `Collections.unmodifiableList(listContainingNull)` | Có thể đọc phần tử null. |

Không gom tất cả lỗi vào một catch chung rồi tính PASS. Mỗi test nên phân biệt đúng exception class và đúng trạng thái sau tác động.

### 5.1. Thử thay phần tử, thêm phần tử, rồi sửa **chính đối tượng**

Ba bước này không tương đương:

~~~java
List<MutableBox> copy = List.copyOf(source);

copy.add(new MutableBox("X", 1));     // Structural change -> UOE
copy.set(0, new MutableBox("Y", 1));   // Element replacement -> UOE
copy.get(0).setCount(99);             // Mutable element edit -> allowed
~~~

Đoạn này **giả định đã có `source`**, không phải file độc lập. Hai thao tác đầu bị từ chối và nếu chạy liên tiếp không catch sẽ dừng ở `add`. Trong test hoàn chỉnh, từng lệnh được kiểm tra qua helper `expectUoe`.

### 5.2. Kiểm thử phải quan sát được cả hai chiều aliasing

- **Sửa nguồn:** `box.setCount(7)` → `copy.get(0).count()==7`.
- **Sửa qua phần tử lấy từ copy:** `copy.get(0).setCount(9)` → `source.get(0).count()==9`.

Nếu cả hai đúng, điều đang xảy ra là **shared mutable element**, không phải copy sâu và cũng không phải collection bị cho phép `set`.

## 6. Bộ dữ liệu thử nghiệm

Ta dùng object mutable đơn giản:

~~~java
static final class MutableBox {
    private final String label;
    private int count;

    MutableBox(String label, int count) {
        this.label = label;
        this.count = count;
    }

    String label() { return label; }
    int count() { return count; }
    void setCount(int count) { this.count = count; }
}
~~~

**`label` có reference final** tới một `String` (String immutable), nhưng `count` thay đổi qua setter. Không override `equals`/`hashCode`, để thí nghiệm `Set.copyOf` kiểm tra reference mà không rơi vào vấn đề mutable hash keys.

Ta còn dùng:

~~~java
record FrozenBox(String label, int count) {}
~~~

Trong bài lab này, `FrozenBox` là snapshot của một `String` và một primitive `int`. Bởi `String` immutable và `int` là giá trị, bản ghi đó **không bị thay đổi bởi việc sửa `MutableBox` gốc**.

**Không suy rộng** rằng mọi Java `record` đều deep immutable. Một record chứa `List<String>` mutable hoặc `MutableBox` vẫn có thể phơi bày references mutable nếu không defensive-copy.

## 7. Chương trình Java 17+ hoàn chỉnh, có assertions

Tạo file **`ReadOnlyElementMutationLab.java`**:

~~~java
import java.util.*;
import java.util.stream.Collectors;

public class ReadOnlyElementMutationLab {
    static final class MutableBox {
        private final String label;
        private int count;

        MutableBox(String label, int count) {
            this.label = label;
            this.count = count;
        }

        String label() { return label; }
        int count() { return count; }
        void setCount(int count) { this.count = count; }
    }

    record FrozenBox(String label, int count) {}

    static void check(boolean ok, String message) {
        if (!ok) throw new AssertionError(message);
    }

    static void expectUoe(String label, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError(
                    label + " must reject structural change");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + "=UOE");
        }
    }

    static void expectNpe(String label, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError(
                    label + " must reject null");
        } catch (NullPointerException expected) {
            System.out.println(label + "=NPE");
        }
    }

    public static void main(String[] args) {
        MutableBox box = new MutableBox("A", 1);
        List<MutableBox> source = new ArrayList<>();
        source.add(box);

        List<MutableBox> liveView =
                Collections.unmodifiableList(source);
        List<MutableBox> snapshot = List.copyOf(source);
        List<MutableBox> factory = List.of(box);
        List<MutableBox> collected =
                source.stream()
                      .collect(Collectors.toUnmodifiableList());
        List<MutableBox> streamList =
                source.stream().toList();

        boolean shared = snapshot.get(0) == box
                && liveView.get(0) == box
                && collected.get(0) == box
                && factory.get(0) == box
                && streamList.get(0) == box;
        check(shared,
                "All lists must refer to the same element");
        System.out.println("sharedElementReference=" + shared);

        source.add(new MutableBox("B", 2));
        check(liveView.size() == 2
                && snapshot.size() == 1
                && factory.size() == 1
                && collected.size() == 1
                && streamList.size() == 1,
                "Structural sizes");
        System.out.println(
                "sizesAfterSourceAdd=view:" + liveView.size()
                + ",copy:" + snapshot.size()
                + ",factory:" + factory.size()
                + ",collector:" + collected.size()
                + ",stream:" + streamList.size());

        box.setCount(7);
        check(snapshot.get(0).count() == 7
                && liveView.get(0).count() == 7
                && collected.get(0).count() == 7
                && factory.get(0).count() == 7
                && streamList.get(0).count() == 7,
                "Mutable element aliasing");
        System.out.println(
                "countsAfterElementEdit=view:"
                + liveView.get(0).count()
                + ",copy:" + snapshot.get(0).count()
                + ",factory:" + factory.get(0).count()
                + ",collector:" + collected.get(0).count()
                + ",stream:" + streamList.get(0).count());

        snapshot.get(0).setCount(9);
        check(source.get(0).count() == 9,
                "Reverse aliasing");
        System.out.println("sourceCountAfterEditViaCopy="
                + source.get(0).count());

        expectUoe("copy.add", () ->
                snapshot.add(new MutableBox("C", 3)));
        expectUoe("view.set", () ->
                liveView.set(0, new MutableBox("Z", 3)));
        expectUoe("factory.clear", factory::clear);
        expectUoe("collector.remove", () ->
                collected.remove(0));
        expectUoe("stream.add", () ->
                streamList.add(box));

        List<MutableBox> mutableContainer =
                new ArrayList<>(snapshot);
        mutableContainer.add(new MutableBox("C", 3));
        check(mutableContainer.size() == 2
                && snapshot.size() == 1,
                "Container copy must be independently modifiable");
        System.out.println("mutableContainerSize="
                + mutableContainer.size());

        Map<String, MutableBox> mapSource =
                new LinkedHashMap<>();
        mapSource.put("first", box);
        Map<String, MutableBox> mapSnapshot =
                Map.copyOf(mapSource);
        mapSource.put("second", new MutableBox("D", 4));

        check(mapSnapshot.size() == 1
                && mapSnapshot.get("first") == box,
                "Map snapshot must hold same value reference");
        System.out.println("mapSnapshotSize="
                + mapSnapshot.size());

        box.setCount(11);
        check(mapSnapshot.get("first").count() == 11,
                "Map value mutability");
        System.out.println("mapValueAfterEdit="
                + mapSnapshot.get("first").count());

        expectUoe("map.put", () ->
                mapSnapshot.put("new", box));
        expectUoe("map.entry.setValue", () ->
                mapSnapshot.entrySet().iterator().next()
                        .setValue(new MutableBox("X", 0)));

        Set<MutableBox> setSnapshot =
                Set.copyOf(Set.of(box));
        check(setSnapshot.iterator().next() == box,
                "Set copy must preserve element reference");
        System.out.println("setSharedElementReference="
                + (setSnapshot.iterator().next() == box));
        expectUoe("set.add", () ->
                setSnapshot.add(new MutableBox("Y", 0)));

        List<String> inner =
                new ArrayList<>(List.of("x"));
        List<List<String>> shallowOuter =
                List.copyOf(List.of(inner));
        List<List<String>> deepOuter =
                List.copyOf(List.of(List.copyOf(inner)));

        inner.add("y");
        check(shallowOuter.get(0).size() == 2
                && deepOuter.get(0).size() == 1,
                "Nested collections need nested copies");
        System.out.println(
                "nestedSizes=shallow:"
                + shallowOuter.get(0).size()
                + ",deep:" + deepOuter.get(0).size());
        expectUoe("deep.inner.add", () ->
                deepOuter.get(0).add("z"));

        MutableBox mutable =
                new MutableBox("frozen", 3);
        List<FrozenBox> frozen = List.of(
                new FrozenBox(mutable.label(),
                              mutable.count()));
        mutable.setCount(50);
        check(frozen.get(0).count() == 3,
                "Immutable value snapshot must not change");
        System.out.println(
                "frozenCountAfterOriginalEdit="
                + frozen.get(0).count());

        List<String> allowsNull =
                Collections.unmodifiableList(
                        new ArrayList<>(
                                Arrays.asList("A", null)));
        check(allowsNull.size() == 2
                && allowsNull.get(1) == null,
                "Unmodifiable wrapper may contain null");
        System.out.println(
                "wrapperAllowsNull="
                + (allowsNull.get(1) == null));

        expectNpe("copyOf.null", () ->
                List.copyOf(Arrays.asList("A", null)));
        expectNpe("of.null", () ->
                List.of("A", null));
        expectNpe("collector.null", () ->
                Arrays.asList("A", (String) null)
                        .stream()
                        .collect(
                                Collectors.toUnmodifiableList()));
        expectNpe("mapCopy.nullValue", () ->
                Map.copyOf(
                        Collections.singletonMap(
                                "k", null)));

        System.out.println("RESULT=PASS");
    }
}
~~~

### 7.1. Biên dịch và chạy

~~~bash
javac -encoding UTF-8 --release 17 ReadOnlyElementMutationLab.java
java ReadOnlyElementMutationLab
~~~

**Không cần dependencies ngoài JDK.** Chương trình dùng `record` và `Stream.toList()`, nên chọn **Java 17+**. Những APIs từ Java 9/10 được nhắc đến vẫn có trong Java hiện đại.

### 7.2. Stdout đã kiểm chứng bằng OpenJDK 24.0.2

~~~text
sharedElementReference=true
sizesAfterSourceAdd=view:2,copy:1,factory:1,collector:1,stream:1
countsAfterElementEdit=view:7,copy:7,factory:7,collector:7,stream:7
sourceCountAfterEditViaCopy=9
copy.add=UOE
view.set=UOE
factory.clear=UOE
collector.remove=UOE
stream.add=UOE
mutableContainerSize=2
mapSnapshotSize=1
mapValueAfterEdit=11
map.put=UOE
map.entry.setValue=UOE
setSharedElementReference=true
set.add=UOE
nestedSizes=shallow:2,deep:1
deep.inner.add=UOE
frozenCountAfterOriginalEdit=3
wrapperAllowsNull=true
copyOf.null=NPE
of.null=NPE
collector.null=NPE
mapCopy.nullValue=NPE
RESULT=PASS
~~~

**Kiểm chứng thực tế:** `javac --release 17` thành công trên JDK 24.0.2; chạy `java ReadOnlyElementMutationLab` cho toàn bộ stdout trên và **exit code 0**. Nếu có assertion không đúng hoặc một collection chấp nhận structural change trái với expected, code sẽ ném `AssertionError` và không in `RESULT=PASS`.

### 7.3. Đọc kết quả theo đúng nguyên tắc

- `sharedElementReference=true`: cả source, view, copy, factory, collector và stream result đều cùng tham chiếu một `MutableBox` ban đầu.
- `sizesAfterSourceAdd=view:2,...copy:1`: view đọc qua source, còn các bản snapshot giữ thành viên trước khi source thêm B.
- `countsAfterElementEdit=...:7`: tất cả danh sách cùng thấy `count` mới **vì cùng giữ box**.
- `sourceCountAfterEditViaCopy=9`: caller có thể lấy box từ list unmodifiable và dùng setter; source cũng thấy thay đổi đó.
- Các dòng `=UOE`: thao tác sửa **collection/container** được từ chối.
- `mutableContainerSize=2`: `new ArrayList<>(snapshot)` là container khác có thể thêm phần tử, nhưng **các references cũ vẫn được dùng chung**.
- `mapSnapshotSize=1`: thay đổi entries ở map nguồn không thêm entry vào map copy.
- `mapValueAfterEdit=11`: sửa mutable object được tham chiếu bởi value ở map copy vẫn có hiệu lực.
- `map.entry.setValue=UOE`: không thể vượt qua unmodifiable map bằng việc sửa entry lấy từ `entrySet()`.
- `setSharedElementReference=true`: `Set.copyOf` giữ phần tử reference, không clone object.
- `nestedSizes=shallow:2,deep:1`: copy outer list thôi không đóng băng inner mutable list.
- `frozenCountAfterOriginalEdit=3`: immutable value snapshot đã lấy dữ liệu 3 trước khi mutable source đổi thành 50.
- `wrapperAllowsNull=true`: wrapper unmodifiable có thể giữ null nếu source có null.
- Các dòng `=NPE`: các factory/collector được thử không chấp nhận null, **khác với UOE của structural mutators**.

## 8. Vì sao helper kiểm tra exception là quan trọng?

Bài dùng:

~~~java
static void expectUoe(String label, Runnable operation) {
    try {
        operation.run();
        throw new AssertionError(
                label + " must reject structural change");
    } catch (UnsupportedOperationException expected) {
        System.out.println(label + "=UOE");
    }
}
~~~

Nó nêu rõ contract:

- Nếu mutator ném `UnsupportedOperationException` → test **PASS**.
- Nếu mutator **thành công ngoài dự kiến** → helper ném `AssertionError` → test **FAIL**.
- Nếu ném một exception không mong đợi như `NullPointerException` → không bị catch bởi helper → test **FAIL**.

Một test kém hơn là:

~~~java
try {
    list.add(element);
} catch (Exception ignored) {
    // tự coi mọi lỗi là PASS
}
~~~

**Đây là phản ví dụ, không phải source độc lập.** Cách catch mọi exception làm mất thông tin: nếu `add` lỗi do phần tử null, validation, hay bug khác thì chưa chắc bạn đã chứng minh đúng hợp đồng unmodifiable.

### 8.1. Không dùng no-op mutators để kết luận quá rộng

Trong `Collection` Javadoc, một số mutator operations có thể **không ném ngoại lệ khi thao tác không thay đổi gì** nếu implementation không hỗ trợ modification và contract cho phép. Ví dụ: `removeAll(Collections.emptySet())` có thể không đổi dữ liệu.

Đối với `List.of` và `List.copyOf`, Javadoc bảo đảm mọi mutator method trên returned list sẽ ném `UnsupportedOperationException`. Nhưng khi kiểm tra collection implementations tổng quát, nên chọn thao tác **rõ ràng sẽ thay đổi cấu trúc nếu được phép**, như `add(newElement)`, rồi assert cụ thể.

**Không** dùng một lần gọi `removeIf(x -> false)` hay `remove("absent")` không ném exception để kết luận chắc rằng collection mutable.

### 8.2. Biết phiên bản Java của API nào

- Java 9: `List.of`, `Set.of`, `Map.of`.
- Java 10: `List.copyOf`, `Set.copyOf`, `Map.copyOf`, `Collectors.toUnmodifiableList` và họ collector liên quan.
- Java 16: `Stream.toList()`.
- Java 17: record API đã stable; demo dùng `record FrozenBox`.

Nếu một codebase bắt buộc `--release 10`, chương trình demo Java 17+ không thể compile **nguyên xi** vì có `record` và `Stream.toList()`. Có thể thay `record` bằng class final truyền thống và thay `stream().toList()` bằng `collect(Collectors.toUnmodifiableList())`. Nhưng cách phân biệt **shallow unmodifiable vs immutable values** vẫn áp dụng.

## 9. Nested collections: vỏ ngoài unmodifiable chưa đủ

Xét:

~~~java
List<String> inner =
        new ArrayList<>(List.of("x"));

List<List<String>> outer =
        List.copyOf(List.of(inner));

inner.add("y");
System.out.println(outer.get(0).size()); // 2
~~~

`outer` không cho thêm một danh sách con hoặc thay reference danh sách con. Nhưng phần tử `outer.get(0)` chính là `inner`, vẫn mutable.

### 9.1. Sao chép từng tầng khi dữ liệu ở tầng đó mutable

~~~java
List<List<String>> nestedFrozen =
        List.copyOf(List.of(List.copyOf(inner)));
~~~

Khi `inner` còn chứa `"x"` và chưa có `"y"`, `nestedFrozen.get(0).size()` giữ nguyên 1 nếu sau đó `inner.add("y")`.

Ở ví dụ này, tầng trong đã được copy và `String` immutable, nên toàn bộ nested list có thể được xem là effectively immutable về dữ liệu. Nếu tầng trong chứa **`MutableBox`**, copy list trong vẫn **không copy MutableBox**.

### 9.2. Deep copy nghĩa là copy **đến nơi không còn alias mutable ngoài ý muốn**

Ví dụ:

~~~text
List<List<MutableBox>>
      |
      +-- outer list (List.copyOf)
             |
             +-- inner list (List.copyOf)
                    |
                    +-- MutableBox(count=1)
                           ^
                           |
                      alias ở caller
~~~

Nếu caller sửa `MutableBox.count`, snapshot vẫn thay đổi. Cần **materialize immutable values** từ từng MutableBox hoặc copy đối tượng theo policy nghiệp vụ.

Không có một phương thức tổng quát `List.deepCopyOf(ObjectGraph)` trong Java Collections Framework có thể tự xử lý arbitrary graphs, cycles, shared references, synchronization và domain invariants một cách an toàn.

### 9.3. Với nested mutable maps

Tương tự:

~~~java
Map<String, List<String>> source = new HashMap<>();
var roles = new ArrayList<>(List.of("USER"));
source.put("alice", roles);

var outer = Map.copyOf(source);
roles.add("ADMIN");

System.out.println(outer.get("alice")); // [USER, ADMIN]
~~~

**Đây là mảnh mã minh họa, không phải file độc lập**. `Map.copyOf` chỉ cố định mapping từ key đến **reference của List**. Muốn đóng băng cấu trúc của từng list value:

~~~java
Map<String, List<String>> snapshot = new HashMap<>();
source.forEach((key, value) ->
        snapshot.put(key, List.copyOf(value)));

Map<String, List<String>> frozen =
        Map.copyOf(snapshot);
~~~

Điều kiện để snapshot được **effectively immutable**: keys là `String` (immutable), mọi inner list đã copy và các phần tử `String` cũng immutable. Nếu values là objects mutable, phải copy sâu thêm theo thiết kế.

## 10. Map và Set: lỗi tinh vi hơn do equality/hash

Ở `Map.copyOf`:

~~~java
Map<String, MutableBox> map = Map.copyOf(sourceMap);
map.get("first").setCount(11); // Vẫn có thể sửa MutableBox
// map.put("new", box);        // UOE
~~~

Unmodifiable map chặn **thêm/xóa/thay entries**; nó không đóng băng mutable values.

### 10.1. `Map.Entry.setValue` không phải đường vòng

Nếu map là unmodifiable, returned entries từ `entrySet()` cũng phải không mở ra đường sửa map. Trong lab:

~~~java
mapSnapshot.entrySet()
           .iterator()
           .next()
           .setValue(new MutableBox("X", 0));
~~~

đã ném `UnsupportedOperationException`. Nhưng:

~~~java
mapSnapshot.get("first").setCount(11);
~~~

vẫn thay đổi state của **value object**.

Đây là sự phân biệt giữa thay **value reference trong map** và thay **nội dung của value object**.

### 10.2. Mutable keys còn nguy hiểm hơn mutable values

Nếu object làm key có `equals`/`hashCode` phụ thuộc vào trường mutable, sửa trường đó sau khi insert vào `HashMap`, `HashSet` hoặc những cấu trúc hash-based có thể làm:

- `contains` hoặc `get` không tìm thấy key theo cách dự kiến.
- Nhiều keys từng khác nhau trở thành bằng nhau.
- Các invariant của lookup và duplicate semantics khó dự đoán.
- `equals` hoặc `hashCode` của cả collection thay đổi dù container không bị gọi mutator.

**Không** dùng một test đoán chính xác `contains(key)` phải trả false sau mutation cho mọi `Set.of`/`Set.copyOf` implementation: cách tổ chức buckets/entries là chi tiết triển khai. Contract an toàn là **tránh mutable state trong equals/hashCode của key** hoặc dùng immutable key types.

Trong lab, `MutableBox` **không override equals/hashCode**, nên kiểm tra cùng reference ở `Set.copyOf` không phụ thuộc vào một hash thay đổi giữa lúc chạy.

### 10.3. Không trông chờ iteration order của Set/Map factory

Các unmodifiable Set/Map factories không hứa iteration order cố định; trong một số JVM, thứ tự có thể khác qua các lần chạy. Khi test `Set.copyOf` hoặc `Map.copyOf`:

- So các tập mappings/elements theo **ý nghĩa**, không hard-code thứ tự trả về.
- Dùng key cụ thể như `map.get("first")` thay vì `iterator().next()` để suy ra phần tử đầu tiên có ý nghĩa; riêng lab `map.entrySet().iterator().next()` chỉ để gọi `setValue` trên một map chỉ có **một** entry.
- Không dựa vào concrete class implementation hoặc object identity của container.

### 10.4. Trùng phần tử và null

- `Set.of("A","A")` ném `IllegalArgumentException` vì duplicate elements.
- `Set.copyOf(collection)` có thể rút gọn duplicate elements, một trong những references đại diện có thể không xác định nếu nhiều đối tượng bằng nhau nhưng khác identity.
- `Map.of(...)` không chấp nhận duplicate keys.
- `List.of`/`List.copyOf` không chấp nhận null.
- `Set.copyOf`/`Map.copyOf` có những hạn chế null tương ứng với elements/keys/values của chúng.

**Không test `Set.copyOf` bằng cách buộc nó giữ nguyên reference cụ thể khi đầu vào có nhiều objects bằng nhau theo `equals`.** Điều đó không được hứa trong contract.

## 11. Null, exception types và sự khác nhau giữa các API

Trong bài lab có:

~~~java
List<String> wrapper = Collections.unmodifiableList(
        new ArrayList<>(Arrays.asList("A", null)));
System.out.println(wrapper.get(1) == null); // true

List.copyOf(Arrays.asList("A", null)); // NPE
List.of("A", null);                    // NPE
~~~

`Collections.unmodifiableList` **không tự loại bỏ null** khỏi nguồn. Nếu source hợp lệ chứa null, wrapper có thể đọc được null.

Trong khi đó `List.of` và `List.copyOf` **không chấp nhận null elements**. `Collectors.toUnmodifiableList` cũng **không nhận null values** theo Javadoc.

### 11.1. Phân biệt ba nhóm kết quả

| Tình huống | Expected | Chứng minh điều gì? |
| --- | --- | --- |
| `list.copyOfSource.add(e)` | `UnsupportedOperationException` | Không cho structural changes. |
| `List.copyOf(listWithNull)` | `NullPointerException` | Không cho null input element. |
| `mutableBox.setCount(99)` | Thành công, state quan sát được đổi | Element mutable dù list unmodifiable. |

**Không viết test catch mọi `RuntimeException` rồi coi PASS**. Nếu test kỳ vọng UOE mà nhận NPE, đó là tình huống khác và phải báo FAIL.

### 11.2. `Stream.toList()` và collector khác nhau về cam kết

`Stream.toList()` (Java 16+) trả unmodifiable list, và không nêu cùng hạn chế cấm null như `Collectors.toUnmodifiableList()`. Các APIs unmodifiable có thể có **null policies khác nhau**. Khi triển khai với dữ liệu có thể null, hãy kiểm tra Javadoc cụ thể và đưa null-case vào tests.

**Không suy ra** vì cả hai đều trả unmodifiable list nên mọi đặc điểm về null, concrete implementation, serialization hoặc performance của chúng giống nhau.

### 11.3. `List.copyOf(null)`

Truyền collection reference `null` thay vì collection có phần tử null cũng không hợp lệ. Đây là hai ca cần phân biệt:

~~~java
List.copyOf((Collection<String>) null); // NPE: source reference null
List.copyOf(Arrays.asList("A", null));   // NPE: element null
~~~

Đây là **mảnh minh họa**, không chạy các dòng này liên tục không catch. Lab chính đã có kiểm thử element-null.

## 12. “Bất biến” đủ dùng cho API nghiệp vụ: snapshot thành immutable values

Giải pháp mạnh hơn là tạo **value snapshot** mà caller không thể thay đổi qua setters hoặc các reference lồng trong.

Ví dụ từ mutable domain object:

~~~java
record FrozenBox(String label, int count) {}

MutableBox source = new MutableBox("A", 3);
List<FrozenBox> result =
        List.of(new FrozenBox(source.label(),
                              source.count()));

source.setCount(50);
System.out.println(result.get(0).count()); // 3
~~~

**Đây là đoạn minh họa trong phạm vi class đã có `MutableBox`**, phần 7 đã kiểm chứng cùng cơ chế. `FrozenBox` chỉ giữ `String` và `int`, do đó giá trị 3 được snapshot một lần, không phản ánh mutation sau đó.

### 12.1. Record không tự deep-immutable

Xét:

~~~java
record UserView(String name, List<String> roles) {}

var roles = new ArrayList<>(List.of("USER"));
var user = new UserView("Alice", roles);
roles.add("ADMIN");
System.out.println(user.roles()); // [USER, ADMIN]
~~~

`record` tự động tạo final fields và accessor, nhưng `roles` vẫn trỏ tới mutable list truyền vào. Record **shallow** nếu các components mutable.

Dạng tốt hơn:

~~~java
record UserView(String name, List<String> roles) {
    public UserView {
        roles = List.copyOf(roles);
    }
}
~~~

Bản này defensively copies **cấu trúc của roles**. Nếu roles chứa `String` immutable, returned record có thể được xem là effectively immutable về hai components này. Nếu components chứa `MutableRole`, cần copy chúng thành immutable values trước.

**Lưu ý:** Hai đoạn là ví dụ đối chiếu, không đặt **hai record cùng tên** trong cùng một Java file.

### 12.2. Ingress và egress: copy ở đúng biên

Một API quản lý internal state thường có hai biên:

**Input boundary:** caller trao một mutable list cho constructor/method. Nếu giữ reference trực tiếp, caller có thể sửa lại sau đó.

**Output boundary:** service trả một list cho caller. Nếu trả mutable internal list, caller có thể sửa cấu trúc. Nếu chỉ bọc unmodifiable view, caller còn có thể sửa **mutable elements**.

Mẫu hiệu quả:

1. Chuyển mutable entity → immutable DTO qua mapping rõ ràng.
2. Với nested collections, copy từng mutable layer và mỗi mutable element theo policy.
3. Dùng `List.copyOf` để khóa cấu trúc ở output boundary.
4. Nếu data thay đổi qua thời gian, định nghĩa mỗi lần lấy snapshot hay live view.
5. Không dựa vào `List.copyOf` để **tự deep-copy** toàn bộ object graph.

### 12.3. Ví dụ API trả immutable snapshot

~~~java
record OrderLineView(String sku, int quantity) {}

List<OrderLineView> snapshotLines(
        List<MutableOrderLine> source) {
    return source.stream()
            .map(line -> new OrderLineView(
                    line.getSku(),
                    line.getQuantity()))
            .toList();
}
~~~

**Đây là đoạn kiến trúc minh họa, không phải chương trình độc lập:** `MutableOrderLine` và method được khai báo trong domain code của bạn. Nếu `sku` là immutable String và `quantity` primitive int, result là unmodifiable list của immutable values. Với Java 10 target, có thể dùng `collect(Collectors.toUnmodifiableList())` thay cho `Stream.toList()`.

Tất cả việc snapshot cần được làm dưới chính sách đồng bộ/ownership phù hợp nếu nguồn có thể bị cập nhật đồng thời.

## 13. Concurrency: unmodifiable collection không tự tạo thread safety

Dùng `List.copyOf` thường giúp tránh việc thread khác tự ý gọi `add` hay `remove` qua reference trả ra. Nhưng **nếu các phần tử mutable**, thread A có thể sửa `box.count` trong khi thread B đọc `snapshot.get(0).count`.

Ví dụ:

~~~text
Thread A: box.setCount(99)
Thread B: snapshot.get(0).count()
~~~

Nếu không có synchronization/happens-before phù hợp, Java Memory Model **không bảo đảm** thread B thấy đúng giá trị mới vào một thời điểm cụ thể; hơn nữa có thể có **data race**. Các phép kiểm thử đơn luồng của bài cố ý tránh nondeterminism để chứng minh aliasing; chúng **không chứng minh thread safety**.

### 13.1. Ba loại an toàn khác nhau

| Loại | Cần gì? | `List.copyOf` tự bảo đảm? |
| --- | --- | --- |
| Chặn mutator qua returned collection | Unmodifiable container | **Có** theo contract. |
| Chặn external mutation của elements | Immutable elements hoặc defensive copy | **Không**. |
| Quan sát đồng thời an toàn | Immutable values + safe publication hoặc synchronization phù hợp | **Không tự động** cho mutable elements. |

Một unmodifiable **view** bọc `ArrayList` không làm những thay đổi đồng thời ở backing list an toàn. Khi iterate view trong lúc backing list bị đổi, vẫn phải tuân thủ contract của source implementation và quy tắc đồng bộ.

### 13.2. Snapshot khi source đang bị sửa đồng thời

`List.copyOf(source)` không phải một **atomic transaction** chụp toàn bộ trạng thái của một mutable collection đang được nhiều threads cập nhật. Nếu producer có thể thay đổi source đồng thời, cần lock, immutable state handoff, snapshot versioning, hoặc một cơ chế concurrent collection/transaction phù hợp.

Ngay cả khi tạo được stable list membership, snapshot vẫn có thể chứa mutable objects mà thread khác chỉnh sau đó. Nếu cần nhất quán về **state của từng phần tử**, phải snapshot những trường cần thiết dưới cơ chế đồng bộ tương ứng.

### 13.3. Vì sao không đưa race conditions vào stdout chính?

Không có scheduler/CPU timing nào bảo đảm cùng một interleaving trên mọi máy. Một test kiểu “thread A sửa, thread B nhất định đọc X” không có synchronization là **flaky**.

Bài lab chính là deterministic, tuần tự, có assertions. Đối với concurrency, hãy dùng unit tests với latches/barriers và thiết kế threadsafe rõ ràng; không suy ra race-safe chỉ vì một lần chạy thành công.

## 14. Mutable keys và equality: một ca rủi ro cần xử lý bằng thiết kế

Giả sử:

~~~java
class MutableKey {
    String id;
    MutableKey(String id) { this.id = id; }

    @Override public boolean equals(Object obj) {
        return obj instanceof MutableKey other
                && java.util.Objects.equals(id, other.id);
    }

    @Override public int hashCode() {
        return java.util.Objects.hashCode(id);
    }
}
~~~

Nếu đặt `MutableKey` vào `HashSet` hoặc làm key trong `HashMap`, sau đó đổi `id`, bạn có thể phá vỡ các giả định lookup vì hashing/equality thay đổi. **Unmodifiable Set/Map không giúp đối tượng key trở thành immutable**.

Thực hành an toàn:

- Dùng `String`, primitive wrappers hoặc record value với **components immutable** làm hash keys.
- Không đưa fields có thể đổi vào `equals`/`hashCode` khi object dùng làm key của hash collection trong thời gian sống của mapping.
- Nếu ID thực sự thay đổi, remove mapping dưới key cũ rồi insert object/key mới theo synchronization policy.
- Khi test, kiểm tra **domain invariant** thay vì hard-code một hành vi nội bộ như “Set.contains phải luôn false sau mutation” — implementation có thể khác.

**Đây là ví dụ thiết kế lỗi tiềm ẩn**, không phải lời khuyên thử sửa key thật trong production.

## 15. Chẩn đoán khi API “read-only” nhưng dữ liệu vẫn đổi

Một ứng dụng có thể gặp tình huống:

~~~text
GET /orders -> response shows quantity=1
Client receives List<Order> marked unmodifiable
Client mutates order.setQuantity(7)
Later GET /orders -> response shows quantity=7
~~~

Nếu domain service trả **cùng mutable entity reference**, caller đã sửa object state qua getter; API chỉ chặn **thay đổi list membership**.

Quy trình kiểm tra:

1. Xác định API trả **live view** hay **snapshot**.
2. Kiểm tra `returnedList == internalList` không phải tiêu chí chính; xem liệu **element references** có cùng nhau không.
3. Sửa **source list membership** sau khi tạo returned list; quan sát size/contents.
4. Sửa **một field mutable** trong phần tử nguồn; quan sát qua returned list.
5. Thử mutators trên returned collection; assert UOE đúng loại.
6. Nếu nested collections, sửa inner list qua reference còn giữ.
7. Nếu map, sửa value object qua returned map; kiểm tra entry/put bị chặn.
8. Nếu set/map keys mutable, kiểm tra quy tắc equals/hashCode và thiết kế lại keys.
9. Kiểm tra quyền ghi trong API: caller có thể lấy reference tới mutable entity không?
10. Nếu cần immutable snapshot, tạo DTO với immutable fields và defensive copy từng layer.
11. Nếu có concurrency, xác định thread ownership và happens-before.
12. Phân biệt expected object changes với bug ở serialization, caching hay database persistence.

### 15.1. “Bị thay đổi” nghĩa là thay đổi nào?

| Triệu chứng | Câu hỏi đầu tiên |
| --- | --- |
| `size()` của view tăng | Backing source có bị thêm entry không? |
| `size()` của `List.copyOf` vẫn 1 nhưng value đổi | Phần tử có mutable state/shared alias không? |
| `hashCode()` của list/map đổi | Có mutable element/key/value tham gia equals/hashCode không? |
| `Set.contains` trở nên bất thường | Có mutable hash key hoặc equality inconsistency không? |
| Returned record chứa list bị sửa | Constructor/accessor có defensive copying chưa? |
| Snapshot dùng trong thread khác thấy dữ liệu không nhất quán | Có race khi đọc/copy source hoặc mutate elements không? |

Đây là lý do phải định nghĩa **đúng đối tượng kiểm thử**: container membership, element fields, nested data hay visibility giữa threads.

## 16. Những cách kiểm thử dễ cho kết luận sai

| Phản mẫu | Vì sao sai | Cách kiểm thử đúng |
| --- | --- | --- |
| Chỉ thử `list.add` rồi kết luận elements immutable. | Add kiểm tra cấu trúc, không kiểm tra object state. | Gọi setter trên `list.get(0)`. |
| Chỉ thử `list.get(0) == object` rồi kết luận object mutable. | Cùng reference chưa nói class có setter không. | Mutate state qua một alias rồi quan sát. |
| Coi `List.copyOf` là deep clone. | API không gọi copy constructor cho từng element. | Tạo immutable DTO/defensive deep copy. |
| Coi `Collections.unmodifiableList` là snapshot. | Nó read-through source. | Sửa source rồi kiểm tra `view.size`. |
| Coi `Stream.toList` là mutable ArrayList. | Kết quả unmodifiable Java 16+. | Test UOE, không rely concrete type. |
| Coi `Collectors.toList` luôn mutable. | Javadoc không cam kết mutability. | Dùng `toCollection(ArrayList::new)`. |
| Dùng `Arrays.asList` rồi coi là immutable vì `add` lỗi. | `set` có thể thay phần tử. | Kiểm tra fixed-size vs unmodifiable. |
| Bắt mọi `Exception` rồi báo PASS. | Che mất NPE/IO/bugs. | Assert đúng loại exception. |
| Thử `removeIf(x->false)` không lỗi rồi kết luận mutable. | No-op mutators có semantics khác. | Dùng thao tác chắc chắn thay đổi nếu được phép. |
| Assert `List.copyOf(a) != a`. | Factory có thể tái sử dụng unmodifiable input. | Test contents và mutator contract. |
| Assert iteration order của `Set.copyOf`. | Order không được bảo đảm. | So Set equality/contains. |
| Giữ mutable key trong Set rồi tin hash index ổn định. | equals/hashCode thay đổi làm lookup không ổn định. | Dùng immutable key. |
| Dùng `record` chứa mutable list mà cho rằng deep immutable. | Record là shallow nếu component mutable. | Canonical constructor defensive-copy. |
| Copy outer list rồi dừng. | Inner mutable list vẫn có alias. | Copy inner và elements cần thiết. |
| Cho rằng unmodifiable = threadsafe. | Mutable elements/backing source vẫn có races. | Immutable values, synchronization và safe publication. |
| Coi `NullPointerException` như bằng chứng UOE. | Null policy khác structural mutability. | Test riêng từng exception. |
| Dựa vào concrete class `ImmutableCollections...`. | Implementation nội bộ có thể đổi. | Dựa public Javadoc. |
| Gọi `toArray` rồi cho rằng array chứa deep copies. | Phần tử trong array vẫn là references tới objects. | Copy values nếu cần. |
| Serialization JSON không cho đổi nghĩa object immutable. | Serialization là một pipeline khác; domain reference có thể mutable. | Kiểm tra state encapsulation trước serialize. |
| Chỉ chạy test một lần có concurrency race. | Race dễ flaky. | Test deterministic và thiết kế đồng bộ. |

## 17. Bài tập có đáp án

### Bài 1 — List không sửa được, phần tử vẫn sửa được

~~~java
var box = new MutableBox("A", 1);
var list = List.of(box);
box.setCount(4);
~~~

**Hỏi:** `list.get(0).count()` là bao nhiêu?

**Đáp án:** **4**. `List.of` chặn mutators của list, không chặn setter của box.

### Bài 2 — View phản ánh nguồn

~~~java
var source = new ArrayList<String>();
source.add("A");
var view = Collections.unmodifiableList(source);
source.add("B");
~~~

**Đáp án:** `view.size() == 2`. View read-through backing source.

### Bài 3 — Copy không phản ánh thay đổi thành viên

~~~java
var source = new ArrayList<String>();
source.add("A");
var snapshot = List.copyOf(source);
source.add("B");
~~~

**Đáp án:** `snapshot.size() == 1`. Copy giữ các elements theo thời điểm tạo, không cập nhật membership từ source.

### Bài 4 — Nhưng giá trị mutable thì sao?

~~~java
var item = new MutableBox("A", 1);
var snap = List.copyOf(List.of(item));
item.setCount(9);
~~~

**Đáp án:** `snap.get(0).count() == 9`. Shallow snapshot giữ reference của phần tử.

### Bài 5 — Sửa qua snapshot

~~~java
var box = new MutableBox("A", 1);
var source = new ArrayList<>(List.of(box));
var snap = List.copyOf(source);
snap.get(0).setCount(8);
~~~

**Đáp án:** `source.get(0).count() == 8`. Đây là mutation của object, không phải mutation của list.

### Bài 6 — Thay phần tử tại index 0

~~~java
List<String> list = List.of("A");
list.set(0, "B");
~~~

**Đáp án:** `UnsupportedOperationException`, vì thay reference phần tử trong list bị cấm.

### Bài 7 — `ArrayList` mới từ copy

~~~java
List<String> a = List.of("A");
List<String> b = new ArrayList<>(a);
b.add("B");
~~~

**Đáp án:** `b.size()==2` và `a.size()==1`. Mutable container mới, nhưng nếu elements là mutable objects thì vẫn có thể chia sẻ references.

### Bài 8 — Nested list

~~~java
var inner = new ArrayList<>(List.of("x"));
var outer = List.copyOf(List.of(inner));
inner.add("y");
~~~

**Đáp án:** `outer.get(0).size()==2`. Outer unmodifiable không bảo vệ inner mutable.

### Bài 9 — Nested snapshot đúng

Nếu tạo `var outer = List.copyOf(List.of(List.copyOf(inner)));` **trước khi** inner có "y", sau đó `inner.add("y")` thì sao?

**Đáp án:** Inner snapshot vẫn có size 1. Với phần tử `String` immutable, cấu trúc nested snapshot có thể coi effectively immutable.

### Bài 10 — Map mutable value

`Map.copyOf` có một value `MutableBox(count=1)`. Caller gọi `map.get("x").setCount(6)`.

**Đáp án:** Có thể sửa thành 6; `Map.copyOf` không deep-copy values.

### Bài 11 — `Map.Entry.setValue`

Dùng `map.entrySet().iterator().next().setValue(newBox)` khi `map` được tạo bằng `Map.copyOf`.

**Đáp án:** `UnsupportedOperationException`; không thể đi vòng qua unmodifiable map để thay mapping.

### Bài 12 — Set hash key

Một object có `hashCode` dựa trên trường mutable được giữ trong `HashSet` rồi đổi trường đó. Có nguy cơ gì?

**Đáp án:** Lookup/contains và invariant equality có thể không nhất quán. Dùng immutable key types hoặc tránh mutate fields tham gia equals/hashCode.

### Bài 13 — Null và wrapper

`Collections.unmodifiableList(new ArrayList<>(Arrays.asList("A", null)))` có thể đọc null không?

**Đáp án:** Có, wrapper không tự loại null nguồn. Nhưng `List.copyOf` đối với list chứa null sẽ ném NPE.

### Bài 14 — Collector null

`Stream.of("A", null).collect(Collectors.toUnmodifiableList())` có kết quả gì?

**Đáp án:** `NullPointerException` theo contract collector. Không trộn với structural mutation error.

### Bài 15 — `Stream.toList`

`Stream.of(box).toList()` trên Java 17 có cho `add` không, và box có sửa được không?

**Đáp án:** `add` ném UOE. Nếu box có setter và còn alias, box vẫn có thể sửa. `Stream.toList` là unmodifiable nhưng shallow.

### Bài 16 — Record chưa đủ

`record UserView(List<String> roles) {}` nhận một mutable ArrayList. Caller sửa list sau đó thì record có thay đổi quan sát được không?

**Đáp án:** Có thể có. Record giữ reference của list; cần defensive copy ở canonical constructor, và elements cũng phải immutable nếu muốn effective immutability.

### Bài 17 — Record values thật sự độc lập

`record FrozenBox(String label, int count) {}` được tạo từ box count=3; sau đó box count đổi 50.

**Đáp án:** `FrozenBox.count()` vẫn 3, vì value snapshot là primitive int và String immutable.

### Bài 18 — Thread safety

Một unmodifiable list chứa `MutableBox` có an toàn để hai threads đọc/sửa `count` không đồng bộ không?

**Đáp án:** Không có bảo đảm chỉ nhờ unmodifiable list. Cần synchronization, immutable values hoặc chiến lược thread ownership.

### Bài 19 — Identity của copy

Có được test `List.copyOf(List.of("A")) == List.of("A")` là một hành vi ổn định không?

**Đáp án:** Không. Returned lists có thể là value-based, có thể được tái sử dụng, không hứa identity. Test bằng nội dung và public contracts.

### Bài 20 — API dữ liệu nội bộ

Một method trả `Collections.unmodifiableList(internalOrders)` nhưng `Order` có setter. Client có thể làm gì?

**Đáp án:** Client không thể thêm/xóa qua view, nhưng có thể sửa mỗi `Order` lấy ra. Nếu cần bảo vệ internal state, trả immutable DTO snapshots hoặc copy values theo ranh giới API.

## 18. Checklist kiểm thử và triển khai

- [ ] Tôi đã xác định chính xác dữ liệu nào cần **read-only** và dữ liệu nào cần **immutable**.
- [ ] Tôi phân biệt **unmodifiable view**, **snapshot membership** và **deep copy**.
- [ ] Tôi không coi `Collections.unmodifiableList` là bản snapshot độc lập.
- [ ] Tôi hiểu `List.copyOf` không tự clone các phần tử.
- [ ] Tôi biết `List.of` có thể chứa đối tượng mutable.
- [ ] Tôi biết `Collectors.toUnmodifiableList` và `Stream.toList` cũng giữ references tới elements.
- [ ] Tôi có test sửa **source membership** sau khi tạo view và copy.
- [ ] Tôi có test sửa **state của element** qua original reference.
- [ ] Tôi có test sửa **element thông qua copy.get(0)**.
- [ ] Tôi kiểm tra cả hai chiều aliasing mà không nhầm với structural mutation.
- [ ] Tôi dùng `expectUoe` để test đúng exception cho mutators.
- [ ] Tôi dùng `expectNpe` riêng cho null constraints.
- [ ] Tôi không bắt mọi exception rồi tự cho PASS.
- [ ] Tôi có test `set` và `add`, không chỉ no-op methods.
- [ ] Tôi không khẳng định returned collection có một concrete class hoặc identity cố định.
- [ ] Tôi không dùng iteration order không được bảo đảm của Set/Map factories.
- [ ] Tôi kiểm tra `Map.copyOf` không deep-copy values.
- [ ] Tôi không dùng mutable hash keys trong Set/Map nếu equality/hashCode đổi theo state.
- [ ] Tôi kiểm tra nested lists/maps và copy từng mutable layer cần thiết.
- [ ] Tôi không cho rằng Java record tự deep immutable.
- [ ] Tôi dùng immutable DTO/value snapshots khi API cần bảo vệ trạng thái.
- [ ] Tôi biết `List.copyOf` có thể tái sử dụng một unmodifiable list input.
- [ ] Tôi không dùng unmodifiable list như bằng chứng thread safety của mutable elements.
- [ ] Tôi áp dụng synchronization khi cần snapshot nguồn đang được sửa đồng thời.
- [ ] Tôi biết Java 10 `copyOf` và Java 16 `Stream.toList` khác nhau về mốc phát hành.
- [ ] Tôi kiểm thử bằng Java 17+ và đọc kết quả bằng assertions có tính xác định.
- [ ] Tôi đọc Javadoc đúng bản JDK và tránh dựa vào private/internal implementation details.

## 19. Tài liệu chính thức và còn áp dụng

1. [Oracle Java SE 25 — Collection: Unmodifiable Collections](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collection.html): khái niệm unmodifiable, mutable elements và lưu ý no-op mutators.
2. [Oracle Java SE 25 — List.of / List.copyOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html): unmodifiable list, shallow mutable elements, null rejection, snapshot và value-based semantics.
3. [Oracle Java SE 25 — Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): read-through view của backing list.
4. [Oracle Java SE 25 — Map.copyOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): unmodifiable map, mutable keys/values và null restrictions.
5. [Oracle Java SE 25 — Set.copyOf](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)): unmodifiable set, duplicate elements và mutable objects.
6. [Oracle Java SE 25 — Collectors.toUnmodifiableList](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableList()): Java 10 collector, unmodifiable output, cấm null.
7. [Oracle Java SE 25 — Stream.toList](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/stream/Stream.html#toList()): Java 16+, unmodifiable list, encounter order nếu stream có encounter order.
8. [Oracle Java SE 25 — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/25/core/creating-immutable-lists-sets-and-maps.html): so sánh factory methods, shallow mutability, use cases và hướng dẫn thực hành.
9. [Oracle Java SE 25 — Arrays.asList](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Arrays.html#asList(T...)): fixed-size list backed by array, không đồng nghĩa unmodifiable.
10. [Oracle Java SE 25 — Record Classes](https://docs.oracle.com/en/java/javase/25/language/records.html): record components/canonical constructors, record cũng có thể chứa mutable references.
11. [Oracle Java SE 25 — java.util.concurrent package](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/package-summary.html): concurrency và memory consistency cần phân biệt với unmodifiable container.

**Tổng kết:** Một collection **unmodifiable** chỉ ngăn sửa danh sách/set/map qua các mutator methods; nó không tự đóng băng **mutable elements**, nested lists, map values hay mutable hash keys. `Collections.unmodifiableList` là **live view**; `List.copyOf` là **snapshot của collection membership** nhưng vẫn dùng chung element references. Test đúng phải kiểm tra cả **sửa cấu trúc bị từ chối** và **sửa trạng thái phần tử vẫn quan sát được**. Khi cần một snapshot thật sự ổn định cho API công khai hoặc nhiều threads, hãy tạo **immutable value objects**, defensive-copy từng lớp mutable cần thiết và thiết kế synchronization phù hợp; đừng dựa vào một chữ “read-only” để khẳng định toàn bộ object graph là bất biến.