# Kết hợp `copyOf` với phần tử bất biến để thiết kế dữ liệu chỉ đọc (Java 10+)

## 1. Mục tiêu bài học

Trong Java hiện đại, `List.copyOf`, `Set.copyOf` và `Map.copyOf` (đều có từ **Java 10**) giúp tạo **collection không cho sửa cấu trúc hoặc ánh xạ** qua API của collection. Tuy nhiên, những phương thức này chỉ sao chép **tham chiếu tới phần tử, khóa và value**, không tự nhân bản sâu các đối tượng bên trong.

Vì vậy, để tạo một **mô hình dữ liệu chỉ đọc đáng tin cậy**, ta thường kết hợp hai quyết định:

1. **Đóng băng collection ở ranh giới công bố:** dùng `List.copyOf`, `Set.copyOf`, `Map.copyOf` nhằm ngăn người nhận thêm/xóa/thay thế phần tử hoặc mapping.
2. **Dùng phần tử bất biến:** chọn `String`, `Integer`, `LocalDate`, các value object được thiết kế immutable, hoặc `record` có những thành phần immutable và được sao chép phòng vệ khi cần.

Khi cả cấu trúc collection và các phần tử được công bố đều thực sự bất biến, việc chia sẻ tham chiếu không còn là nguy cơ sửa trạng thái từ xa. Ngược lại, **`copyOf` đơn độc không đủ** nếu phần tử có setter, mảng, `Date` mutable, `StringBuilder`, hoặc các collection mutable lồng nhau.

Sau bài học, bạn có thể:
- Phân biệt *unmodifiable collection*, *shallow copy* và *deep immutability*.
- Nhận biết loại phần tử nào có thể an toàn dùng chung tham chiếu.
- Kết hợp `copyOf` với `record` và defensive copying tại constructor.
- Xử lý collection lồng nhau; không ngộ nhận rằng một `record` mặc định đã bất biến sâu.
- Tạo API công bố dữ liệu ổn định, ngăn sửa gián tiếp từ phía caller.
- Hiểu các điều kiện `null`, thứ tự duyệt, equality, thread safety và chi phí sao chép.

**Phiên bản:** `copyOf` của `List`, `Set`, `Map` có từ Java 10. `record` trở thành tính năng chính thức từ Java 16; chương trình thực hành sử dụng **JDK 17+**, không cần preview. Các quy tắc được trình bày vẫn áp dụng trong Java hiện đại.

## 2. Unmodifiable collection không đồng nghĩa dữ liệu bất biến sâu

Xét hai ý nghĩa khác nhau của từ “không sửa được”:

- **Cấu trúc collection không sửa được:** không thể đổi những phần tử/mapping được lưu trong collection bằng `add`, `remove`, `set`, `put`, `replace`, ...
- **Trạng thái bên trong từng object bất biến:** sau khi tạo, không có đường hợp lệ nào để thay đổi trạng thái quan sát được của các object phần tử.

Ví dụ minh họa:

~~~java
var source = new ArrayList<StringBuilder>();
source.add(new StringBuilder("draft"));

List<StringBuilder> copy = List.copyOf(source);
copy.get(0).append("!"); // Hợp lệ: thay đổi StringBuilder

System.out.println(source.get(0)); // draft!
System.out.println(copy.get(0));   // draft!
~~~

Đây là đoạn mã đặt trong một phương thức, cần import `java.util.ArrayList` và `java.util.List`. Nó sử dụng API đã có ở Java 10 trở lên.

`copy` là unmodifiable list: `copy.add(...)` bị từ chối. Nhưng `StringBuilder` vẫn mutable. Hai danh sách cùng trỏ tới một `StringBuilder`, nên thay đổi được nhìn thấy từ cả hai.

So sánh với phần tử immutable:

~~~java
var source = new ArrayList<String>();
source.add("draft");

List<String> copy = List.copyOf(source);
source.set(0, "published");

System.out.println(source.get(0)); // published
System.out.println(copy.get(0));   // draft
~~~

`String` không có thao tác sửa nội dung đối tượng tại chỗ. `source.set` chỉ **thay tham chiếu phần tử ở list nguồn**; snapshot vẫn giữ tham chiếu tới đối tượng chuỗi `"draft"` cũ.

**Điểm mấu chốt:** `copyOf` giới hạn thao tác **trên container**. Phần tử immutable giới hạn thao tác **trên chính dữ liệu được tham chiếu**. Kết hợp cả hai mới cho ra một mô hình dữ liệu chỉ đọc có ý nghĩa rộng hơn.

## 3. `copyOf` sao chép những gì?

### 3.1. `List.copyOf`

~~~java
List<String> names = List.copyOf(sourceNames);
~~~

Với `sourceNames` là một `ArrayList<String>` mutable, kết quả:
- Lấy những tham chiếu phần tử ở thời điểm copy, không theo dõi các thao tác `add/remove/set` của nguồn về sau.
- Không cho thay cấu trúc list qua biến `names`.
- Giữ các đối tượng `String` có sẵn, không tạo `String` mới cho từng phần tử.
- Từ chối nguồn `null` và phần tử `null` bằng `NullPointerException`.

Nếu `sourceNames` đã là một list unmodifiable phù hợp, implementation **có thể tái sử dụng instance**. Đừng coi `List.copyOf(source) != source` là một bảo đảm của API; điều đáng dựa vào là nội dung và hợp đồng unmodifiable.

### 3.2. `Set.copyOf`

~~~java
Set<String> labels = Set.copyOf(sourceLabels);
~~~

Kết quả không cho thêm/xóa phần tử. Với một `HashSet` mutable làm nguồn, việc thay membership của nguồn về sau không tự cập nhật bản sao. Từng object phần tử vẫn có thể dùng chung tham chiếu.

**Chú ý đặc thù của set:**
- `Set.copyOf` không cam kết **thứ tự duyệt** như `LinkedHashSet` hoặc `TreeSet` nguồn.
- Nếu đầu vào là một `Collection` chứa phần tử trùng theo `equals`, tập kết quả chỉ giữ các phần tử phân biệt; không được dựa vào instance nào trong các bản trùng được chọn.
- Không nhận phần tử `null`.
- Cần phần tử có equality/hashCode ổn định. Thay đổi field tham gia `equals` hoặc `hashCode` khi object đã nằm trong set là một thiết kế rủi ro.

### 3.3. `Map.copyOf`

~~~java
Map<String, Integer> counts = Map.copyOf(sourceCounts);
~~~

Kết quả ngăn các thao tác thay mapping (`put/remove/replace` và cập nhật qua `Map.Entry.setValue`). Với nguồn là `HashMap` mutable thông thường, thao tác sửa nguồn về sau không tự đổi mapping trong snapshot.

**Nhưng `Map.copyOf` không deep-copy key hoặc value.** Nếu value là `StringBuilder` hay một entity mutable, code có thể sửa object ấy qua tham chiếu dù mapping không thay đổi.

Map kết quả:
- Không nhận khóa `null`, value `null`, hoặc map đầu vào `null`.
- Không cam kết thứ tự duyệt.
- Có thể tái sử dụng instance khi map nguồn đã là unmodifiable phù hợp.

**Nguyên tắc chung:** *container snapshot* không đồng nghĩa *deep snapshot*. Không có phương thức `copyOf` chung tự biết cách sao chép mọi object graph.

## 4. Chọn phần tử bất biến để chia sẻ tham chiếu an toàn

Những kiểu thường phù hợp để dùng làm phần tử hoặc value immutable:

| Kiểu hoặc mô hình | Lý do thường an toàn | Điểm phải kiểm tra |
| --- | --- | --- |
| `String` | Nội dung chuỗi không thay đổi sau khi tạo | Không cần tạo `new String(...)` chỉ để tránh chia sẻ |
| `Integer`, `Long`, `BigDecimal` | Giá trị object bất biến | Phép tính tạo giá trị mới, không sửa object cũ |
| `LocalDate`, `LocalDateTime`, `Instant` | Các kiểu ngày/giờ thuộc `java.time` immutable | Phân biệt với đối tượng thời gian mutable của thư viện khác |
| `UUID` | Dùng như value object bất biến | Không dựa vào identity `==` để so sánh giá trị |
| `enum` | Các hằng enum là instance cố định | Tránh thiết kế enum với trạng thái mutable có setter |
| `record Product(int id, String name)` | `int` và `String` không chứa state mutable công bố | `record` chỉ an toàn sâu khi từng component cũng an toàn |
| Lớp `final` có private final fields và defensive copy | Có thể kiểm soát hoàn toàn trạng thái được công bố | Cần kiểm tra nested references, getter, constructor và mutability |

Ví dụ:

~~~java
record Product(int id, String name) {}

var source = new ArrayList<Product>();
source.add(new Product(1, "Paper"));

List<Product> published = List.copyOf(source);
source.add(new Product(2, "Pen"));

System.out.println(published.size());       // 1
System.out.println(published.get(0).name()); // Paper
~~~

`Product` trong ví dụ là một record gồm `int` và `String` immutable. Có thể **chia sẻ chính đối tượng `Product`** giữa danh sách nguồn và snapshot mà không lo một caller sửa `id` hoặc `name` của object ấy.

**Không nên đồng nhất “field là final” với “trạng thái sâu bất biến”.** Nếu `final` field tham chiếu đến một `List`, một mảng hoặc đối tượng mutable, người giữ tham chiếu đó vẫn có thể sửa dữ liệu bên trong.

## 5. `record` + `List.copyOf`: defensive copy ngay tại constructor

Một mẫu thiết kế rất hữu ích với Java 17+ là dùng **record chứa các value object immutable** và gọi `List.copyOf` trên collection nhận từ bên ngoài:

~~~java
import java.util.List;
import java.util.Objects;

record Item(String sku, int unitPrice, int quantity) {
    Item {
        Objects.requireNonNull(sku, "sku");
        if (unitPrice < 0 || quantity <= 0) {
            throw new IllegalArgumentException("invalid item");
        }
    }

    int subtotal() {
        return Math.multiplyExact(unitPrice, quantity);
    }
}

record Order(String id, List<Item> items) {
    Order {
        Objects.requireNonNull(id, "id");
        items = List.copyOf(items);
    }

    int total() {
        return items.stream().mapToInt(Item::subtotal).sum();
    }
}
~~~

**Đây là định nghĩa kiểu minh họa**. Chương trình độc lập có `main` sử dụng cùng mô hình ở mục 9.

Trong **compact constructor** `Order { ... }`:
1. `items` là tham số constructor nhận từ caller.
2. `List.copyOf(items)` tạo ra list unmodifiable chứa các phần tử tương ứng; từ chối `null`.
3. Phép gán `items = List.copyOf(items)` khiến **component field của record được khởi tạo bằng list đã kiểm soát**, không giữ trực tiếp `ArrayList` mutable mà caller đưa vào.
4. `Item` chỉ có `String` và `int`, đều không thể bị sửa nội dung sau khi tạo. Do đó, chia sẻ object `Item` giữa caller và `Order` là an toàn ở mức trạng thái mà record này công bố.

Giả sử:

~~~java
var mutable = new ArrayList<Item>();
mutable.add(new Item("PEN", 4, 2));

Order order = new Order("O-1", mutable);
mutable.add(new Item("BOOK", 30, 1));

System.out.println(mutable.size());    // 2
System.out.println(order.items().size()); // 1
~~~

Đây là đoạn mã minh họa bên trong phương thức, cần import `ArrayList`. Việc caller thêm phần tử vào `mutable` sau đó không đổi danh sách trong `order`.

### Vì sao getter của record không cần copy thêm ở trường hợp này?

Record tạo accessor `items()` trả về trường `items`. Nếu trường đã là list unmodifiable và các phần tử `Item` immutable, trả trực tiếp list đó **không làm lộ đường sửa trạng thái** qua API của model.

~~~java
List<Item> readOnly = order.items();
// readOnly.add(new Item("X", 1, 1)); // UnsupportedOperationException
~~~

Không cần gọi `List.copyOf(items)` mỗi lần getter chỉ để “chắc chắn”, miễn là constructor đã khống chế dữ liệu đi vào và không có nested mutable references bị lộ.

Tuy nhiên, khi mô hình có một object mutable thật sự (ví dụ `byte[]`), một getter trả mảng hoặc mutable object có thể làm lộ trạng thái; khi đó phải thiết kế accessor phòng vệ riêng. **Kiểm tra cả lúc nhận dữ liệu và lúc công bố dữ liệu** (*defensive copying at ingress and egress*).

## 6. Record không tự động bảo đảm bất biến sâu

Xét:

~~~java
record Drafts(List<StringBuilder> notes) {
    Drafts {
        notes = List.copyOf(notes);
    }
}
~~~

Compact constructor đã chặn sửa **danh sách** nhưng chưa chặn sửa các phần tử `StringBuilder`.

~~~java
var note = new StringBuilder("draft");
var input = new ArrayList<StringBuilder>();
input.add(note);

var drafts = new Drafts(input);

note.append("!");
System.out.println(drafts.notes().get(0)); // draft!

drafts.notes().get(0).append("?");
System.out.println(note); // draft!?
~~~

Hai đường sửa đều thành công vì list và caller đang giữ cùng **object mutable**. Kể cả record có component tự động final, chỉ **tham chiếu tới list** là final; nội dung mutable bên dưới không tự trở thành bất biến.

Một ví dụ khác:

~~~java
record Department(List<List<String>> teams) {
    Department {
        teams = List.copyOf(teams);
    }
}
~~~

Đoạn trên mới cố định cấu trúc của **outer list**. Nếu từng inner list là một `ArrayList<String>` mutable được chia sẻ, caller vẫn có thể sửa `teams.get(0)` để làm dữ liệu quan sát qua `Department` thay đổi.

**Kết luận:** muốn dữ liệu chỉ đọc sâu, phải xem xét **toàn bộ đường đi tham chiếu mutable được công bố**, không chỉ field đầu tiên hay collection cấp ngoài.

## 7. Xử lý collection lồng nhau đúng cách

Giả sử dữ liệu là `List<List<String>>`; `String` immutable nhưng **mỗi inner list có thể mutable**. Chỉ dùng `List.copyOf(outer)` là chưa đủ, vì nó giữ nguyên các inner list.

### 7.1. Cách chưa đủ

~~~java
var inner = new ArrayList<String>();
inner.add("An");

var outer = new ArrayList<List<String>>();
outer.add(inner);

List<List<String>> shallow = List.copyOf(outer);
inner.add("Binh");

System.out.println(shallow.get(0)); // [An, Binh]
~~~

**Vì sao?** `shallow` không nhận thêm inner list mới từ `outer`, nhưng vẫn trỏ tới chính `inner` mutable.

### 7.2. Sao chép phòng vệ từng tầng collection

Với JDK 17+:

~~~java
List<List<String>> safe = outer.stream()
        .map(List::copyOf)
        .toList();
~~~

- `List::copyOf` tạo inner list unmodifiable cho mỗi phần tử của outer list.
- `Stream.toList()` (Java 16+) tạo outer list unmodifiable.
- `String` immutable, nên không cần nhân bản từng object `String`.
- Nếu `outer` hoặc inner list chứa `null`, việc copy có thể bị từ chối theo điều kiện API; chuẩn hóa dữ liệu trước khi copy.

Một record có thể encapsulate công thức đó:

~~~java
record Department(List<List<String>> teams) {
    Department {
        teams = teams.stream()
                .map(List::copyOf)
                .toList();
    }
}
~~~

**Điều kiện an toàn:** mô hình giả sử thành phần sâu nhất là `String` immutable. Nếu inner list chứa `MutableEmployee`, dùng `List.copyOf` cho cả hai cấp vẫn chưa cách ly trạng thái của `MutableEmployee`; lúc đó cần immutable DTO hoặc copy sâu theo domain.

Nếu dự án cần cú pháp từ Java 10, có thể dùng `Collectors.toUnmodifiableList()` (Java 10+) thay cho `Stream.toList()`:

~~~java
List<List<String>> safe = outer.stream()
        .map(List::copyOf)
        .collect(java.util.stream.Collectors.toUnmodifiableList());
~~~

Đây là đoạn minh họa, không phải tệp runnable độc lập. Điểm chung vẫn là **không còn cấp `List` mutable nào bị chia sẻ**, trong khi các chuỗi immutable có thể dùng chung tham chiếu.

## 8. Kết hợp `Set.copyOf` và `Map.copyOf` với phần tử bất biến

### 8.1. Tập các nhãn immutable

~~~java
var sourceTags = new HashSet<String>(List.of("office", "sale"));
Set<String> tags = Set.copyOf(sourceTags);

sourceTags.add("new");
System.out.println(tags.contains("new")); // false
~~~

Thành viên của `tags` không thay đổi theo việc thêm phần tử vào nguồn mutable. Các phần tử `String` không thể sửa nội dung, nên chia sẻ tham chiếu là phù hợp.

Nếu cần thứ tự đầu ra xác định để hiển thị:

~~~java
System.out.println(new TreeSet<>(tags)); // [office, sale]
~~~

`TreeSet` ở đây được tạo để **sắp xếp khi hiển thị**, không phải vì `Set.copyOf` giữ thứ tự nguồn. Đoạn ví dụ giả sử đã import `HashSet`, `List`, `Set`, `TreeSet`.

### 8.2. Map khóa bất biến → value bất biến

~~~java
var indexSource = new HashMap<String, Item>();
indexSource.put("PEN", new Item("PEN", 4, 2));

Map<String, Item> bySku = Map.copyOf(indexSource);

indexSource.put("PEN", new Item("PEN", 99, 1));
System.out.println(bySku.get("PEN").unitPrice()); // 4
~~~

Với `Item` là record ở mục 5, bản sao giữ **object `Item` ban đầu** (giá 4). Việc thay mapping trong nguồn bằng một `Item` mới không tự thay `bySku`; object `Item` cũ lại bất biến nên không bị sửa tại chỗ.

### 8.3. Map value là collection cần sao chép nhiều tầng

Với `Map<String,List<String>>`, `Map.copyOf` đơn độc **không** làm các inner list bất biến. Khi dữ liệu nguồn có value mutable, có thể xây dựng một map mới với từng danh sách được sao chép:

~~~java
Map<String, List<String>> safe = sourceMap.entrySet().stream()
        .collect(java.util.stream.Collectors.toUnmodifiableMap(
                Map.Entry::getKey,
                e -> List.copyOf(e.getValue())
        ));
~~~

`sourceMap` là một `Map<String,List<String>>` đã được khai báo và hợp lệ; đây là đoạn mã minh họa.

Ở đây:
1. `Map.Entry::getKey` giữ các key `String` immutable.
2. `List.copyOf(e.getValue())` tạo **value list unmodifiable** riêng cho mỗi entry.
3. `Collectors.toUnmodifiableMap` (có từ Java 10) tạo một map unmodifiable.
4. Trạng thái công bố an toàn hơn vì cả **map** và **list value** đều không cho sửa và phần tử sâu nhất là `String`.

Nếu value chứa `StringBuilder` hoặc entity mutable, vẫn cần chuyển sang một representation immutable của các phần tử trước khi công bố.

### 8.4. `Set` và `Map` cần khóa ổn định

Cần đặc biệt tránh các phần tử trong `Set` hoặc key trong `Map` bị thay đổi field liên quan đến `equals()`/`hashCode()` sau khi đưa vào collection. Việc đó có thể làm kết quả tra cứu không còn đáng tin cậy, đặc biệt với implementation dựa trên hashing.

Immutable value object là lựa chọn tốt vì:
- Khóa có thể được so sánh theo giá trị ổn định.
- Không có setter thay đổi identity logic của object.
- Snapshot chia sẻ tham chiếu không tạo đường làm hỏng cấu trúc tra cứu từ bên ngoài.

## 9. Chương trình Java 17+ hoàn chỉnh: defensive copy và immutable elements

Tạo tệp **ImmutableCopyOfDesignDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

public class ImmutableCopyOfDesignDemo {

    record LineItem(String sku, int unitPrice, int quantity) {
        LineItem {
            Objects.requireNonNull(sku, "sku");
            if (unitPrice < 0 || quantity <= 0) {
                throw new IllegalArgumentException("invalid line item");
            }
        }

        int subtotal() {
            return Math.multiplyExact(unitPrice, quantity);
        }
    }

    record ShopSnapshot(
            List<LineItem> lines,
            Set<String> tags,
            Map<String, LineItem> bySku) {

        ShopSnapshot {
            lines = List.copyOf(lines);
            tags = Set.copyOf(tags);
            bySku = Map.copyOf(bySku);
        }

        int total() {
            return lines.stream().mapToInt(LineItem::subtotal).sum();
        }
    }

    static final class MutableNote {
        private String text;

        MutableNote(String text) {
            this.text = text;
        }

        void append(String suffix) {
            text += suffix;
        }

        String text() {
            return text;
        }
    }

    // Cố ý cho thấy record + List.copyOf chưa đủ
    // nếu phần tử vẫn mutable.
    record LooseNotes(List<MutableNote> notes) {
        LooseNotes {
            notes = List.copyOf(notes);
        }
    }

    public static void main(String[] args) {
        var pen = new LineItem("PEN", 4, 2);
        var book = new LineItem("BOOK", 30, 1);

        var sourceLines = new ArrayList<>(List.of(pen, book));
        var sourceTags = new HashSet<>(List.of("office", "sale"));
        var sourceIndex = new HashMap<String, LineItem>();
        sourceIndex.put("PEN", pen);
        sourceIndex.put("BOOK", book);

        var snapshot = new ShopSnapshot(
                sourceLines, sourceTags, sourceIndex);

        System.out.println("initial lines = " + snapshot.lines().size());
        System.out.println("initial total = " + snapshot.total());

        // Source thay đổi sau constructor.
        sourceLines.add(new LineItem("ERASER", 3, 2));
        sourceTags.add("new");
        sourceIndex.put("PEN", new LineItem("PEN", 99, 1));

        System.out.println("source lines = " + sourceLines.size());
        System.out.println("snapshot lines = " + snapshot.lines().size());
        System.out.println("snapshot has new tag = "
                + snapshot.tags().contains("new"));
        System.out.println("source PEN price = "
                + sourceIndex.get("PEN").unitPrice());
        System.out.println("snapshot PEN price = "
                + snapshot.bySku().get("PEN").unitPrice());
        System.out.println("same immutable item = "
                + (snapshot.lines().get(0) == sourceLines.get(0)));

        // Không thể sửa các collection đã copy.
        try {
            snapshot.lines().add(new LineItem("RULER", 2, 1));
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot list add = blocked");
        }

        try {
            snapshot.tags().remove("office");
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot tag remove = blocked");
        }

        try {
            snapshot.bySku().put("PEN", new LineItem("PEN", 7, 1));
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot map put = blocked");
        }

        // Record vẫn có thể chứa mutable object!
        var note = new MutableNote("draft");
        var sourceNotes = new ArrayList<>(List.of(note));
        var loose = new LooseNotes(sourceNotes);

        note.append("!");
        System.out.println("loose note after source edit = "
                + loose.notes().get(0).text());

        loose.notes().get(0).append("?");
        System.out.println("source note after snapshot edit = "
                + note.text());

        // copyOf từ chối phần tử null.
        try {
            List.copyOf(Arrays.asList("ok", null));
        } catch (NullPointerException ex) {
            System.out.println("null element = rejected");
        }
    }
}
~~~

Biên dịch và chạy bằng **JDK 17 trở lên**:

~~~bash
javac ImmutableCopyOfDesignDemo.java
java ImmutableCopyOfDesignDemo
~~~

**Đầu ra chính xác:**

~~~text
initial lines = 2
initial total = 38
source lines = 3
snapshot lines = 2
snapshot has new tag = false
source PEN price = 99
snapshot PEN price = 4
same immutable item = true
snapshot list add = blocked
snapshot tag remove = blocked
snapshot map put = blocked
loose note after source edit = draft!
source note after snapshot edit = draft!?
null element = rejected
~~~

### Giải thích chi tiết

1. **Tổng tiền ban đầu:** `PEN` có `4 × 2 = 8`, `BOOK` có `30 × 1 = 30`, tổng `38`.
2. **Đổi collection nguồn:** caller thêm `ERASER` vào `sourceLines`, thêm nhãn `new` vào `sourceTags`, và thay value `PEN` trong `sourceIndex`. Các collection trong `snapshot` không phản ánh các thao tác thay cấu trúc/mapping này vì constructor đã gọi `copyOf`.
3. **Chia sẻ `LineItem` an toàn:** `same immutable item = true` cho thấy snapshot giữ cùng record `LineItem` ban đầu. Do `LineItem` chỉ có `String` và số nguyên, việc chia sẻ không cho phép sửa state của item.
4. **Chặn mutator:** `snapshot.lines().add`, `snapshot.tags().remove`, `snapshot.bySku().put` đều bị từ chối bởi `UnsupportedOperationException`. Code cố ý bắt ngoại lệ để chứng minh hợp đồng.
5. **Đối chứng với phần tử mutable:** `LooseNotes` cũng gọi `List.copyOf` nhưng chứa `MutableNote`. Caller sửa `note` thì record nhìn thấy thay đổi; ngược lại sửa qua `loose.notes().get(0)` cũng thay object nguồn. **Bất biến nông không đủ**.
6. **Phần tử `null`:** `List.copyOf` từ chối bằng `NullPointerException`.
7. **Output ổn định:** chương trình kiểm tra `Set` qua `contains` và `Map` qua `get(key)`, không dựa vào thứ tự duyệt không cam kết của `Set.copyOf` hoặc `Map.copyOf`.

**Lưu ý tên class/tệp:** Lớp `public` là `ImmutableCopyOfDesignDemo`, nên tên file phải là `ImmutableCopyOfDesignDemo.java` để lệnh `javac` bên trên hoạt động.

## 10. Những điều `copyOf` và record không tự bảo đảm

### 10.1. Không phải mọi record đều immutable sâu

~~~java
record UnsafeConfig(byte[] bytes) {}
~~~

Field của record là final, nhưng `bytes` là **mảng mutable**. Caller giữ mảng có thể sửa nội dung sau khi truyền vào; accessor `bytes()` mặc định cũng trả về chính mảng ấy. Dùng `List.copyOf` ở một cấp khác không giải quyết được việc mảng bị chia sẻ.

Nếu cần thiết kế với mảng, phải sao chép tại constructor và khi công bố:

~~~java
record SafeConfig(byte[] bytes) {
    SafeConfig {
        bytes = bytes.clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }
}
~~~

Đây là đoạn định nghĩa kiểu minh họa chạy trên Java 17+; trường hợp `bytes == null` sẽ gây `NullPointerException` khi clone, phù hợp nếu hợp đồng không chấp nhận null. Trong ứng dụng, có thể thêm thông báo kiểm tra dữ liệu rõ hơn.

**Giải thích:** clone của mảng `byte[]` đủ để tách dữ liệu vì các phần tử là giá trị nguyên thủy. Với mảng chứa object mutable, clone mảng chỉ sao chép **tham chiếu phần tử**, nên vẫn cần xem lại trạng thái sâu.

### 10.2. `copyOf` không chứng minh an toàn khi truy cập đồng thời

Một object graph thực sự immutable thường dễ chia sẻ giữa nhiều thread hơn vì không có mutation sau khi khởi tạo. Tuy nhiên:
- Nếu collection chứa mutable element, `copyOf` không làm biến mất data race ở element đó.
- Nếu nhiều thread sửa nguồn trong lúc bạn đang xây dựng snapshot, `copyOf` **không phải giao dịch snapshot nguyên tử**; cần phối hợp truy cập hoặc cơ chế nhất quán phù hợp.
- An toàn khi công bố object tới thread khác vẫn cần tuân thủ các quy tắc *safe publication* và thiết kế đồng bộ chung của chương trình.

Tránh suy luận “`Map.copyOf` là thread-safe cho mọi object được map tham chiếu”. Nó chỉ có hợp đồng unmodifiable về mapping.

### 10.3. Snapshot có thể giữ object lâu hơn nguồn

Một snapshot có thể còn giữ tham chiếu đến các object phần tử mà nguồn đã xóa. Nếu các phần tử là object lớn, việc giữ nhiều phiên bản snapshot có thể tăng lượng bộ nhớ sử dụng.

Với immutable value object, việc chia sẻ tham chiếu là một lợi thế về hiệu quả, nhưng bạn vẫn cần quản lý vòng đời snapshot để không giữ lại dữ liệu không cần thiết quá lâu.

### 10.4. Không dựa vào identity của collection kết quả

`List.copyOf`, `Set.copyOf`, `Map.copyOf` có thể tái sử dụng instance của input unmodifiable phù hợp. Đừng kiểm tra rằng `copy != source` như một điều kiện chung.

Đối tượng **phần tử** có thể giữ cùng tham chiếu vì đây là shallow copy; khi phần tử immutable thì điều đó thường hoàn toàn ổn. So sánh **giá trị** của immutable object nên dùng `equals` theo hợp đồng, không giả định mọi value bằng nhau đều cùng instance `==`.

### 10.5. Không được nhầm unmodifiable với “không có phương thức sửa”

~~~java
List<String> values = List.copyOf(List.of("A", "B"));
// values.add("C"); // Có thể biên dịch, nhưng ném UnsupportedOperationException.
~~~

Kiểu `List` vẫn công khai phương thức `add`; tính unmodifiable là **hành vi runtime** của implementation. Cần đọc hợp đồng API và thử nghiệm đúng mục đích, không chỉ nhìn chữ ký kiểu tĩnh.

## 11. Quy trình thiết kế dữ liệu chỉ đọc cho API

Với một API cung cấp danh sách đơn hàng, cấu hình, bảng giá hoặc tập quy tắc, có thể áp dụng quy trình sau:

**Bước 1 — Xác định hợp đồng công bố.** Người gọi được đọc những gì? Có cần một snapshot giữ nguyên nội dung đã công bố khi dữ liệu nguồn cập nhật không? Có đường sửa trực tiếp hoặc gián tiếp nào phải bị chặn?

**Bước 2 — Chọn phần tử immutable.** Ưu tiên value object gồm `String`, số, `LocalDate` hoặc những immutable components khác. Nếu cần `record`, kiểm tra **từng component**; record có `List` hay mảng mutable cần defensive copy.

**Bước 3 — Copy tại ranh giới constructor/factory.** Với danh sách, `items = List.copyOf(items)`; với set/map, dùng `Set.copyOf` hoặc `Map.copyOf`. Điều này ngăn caller giữ một `ArrayList` hay `HashMap` mutable rồi thay đổi những gì model thấy.

**Bước 4 — Xem xét các tầng nested.** Nếu `Map<String, List<Product>>` thì map copy thôi chưa đủ; các list value cũng cần copy. Nếu `Product` mutable, chuyển sang immutable DTO hoặc sao chép trạng thái cần bảo vệ.

**Bước 5 — Kiểm tra các edge case.** Xử lý `null`, trùng phần tử trong `Set.copyOf`, thứ tự duyệt không cam kết của set/map, và key có `equals`/`hashCode` ổn định.

**Bước 6 — Kiểm tra behavior sau khi công bố.** Thử sửa nguồn sau constructor; thử mutator trên kết quả; thử sửa một nested object qua getter. Một test chỉ xác nhận `list.add` ném ngoại lệ là **chưa đủ** để chứng minh deep immutability.

**Bước 7 — Kiểm tra chi phí.** Không cần clone từng `String` hoặc immutable record nếu chỉ muốn cách ly state: chia sẻ immutable value objects thường an toàn và tiết kiệm bộ nhớ. Đừng tạo deep copy tốn kém không cần thiết chỉ để có identity mới.

## 12. Bảng lựa chọn nhanh

| Mô hình dữ liệu | Cách công bố thường phù hợp | Mức bất biến được bảo đảm |
| --- | --- | --- |
| `List<String>` | `List.copyOf(source)` | Cấu trúc unmodifiable; phần tử `String` immutable |
| `List<LocalDate>` | `List.copyOf(source)` | Cấu trúc unmodifiable; `LocalDate` immutable |
| `List<ProductRecord>`, với component chỉ gồm immutable value | `List.copyOf(source)` | Có thể đạt immutable xuyên suốt graph được công bố |
| `List<StringBuilder>` | Chuyển thành `String` rồi `List.copyOf` | Tách khỏi các builder mutable |
| `List<List<String>>` | Copy từng inner list, rồi copy outer list | Hai cấp collection unmodifiable; chuỗi immutable |
| `Map<String, Integer>` | `Map.copyOf(source)` | Mapping unmodifiable; key/value immutable |
| `Map<String, List<String>>` | Copy từng list value, rồi tạo map unmodifiable | Cả map và các value list đều unmodifiable |
| `Set<ImmutableKey>` | `Set.copyOf(source)` | Membership unmodifiable; key equality ổn định |
| `record Config(byte[] data)` | Clone mảng lúc nhận và lúc trả, hoặc chuyển sang immutable representation | Không để lộ mảng mutable từ nguồn hoặc accessor |
| `List<MutableEntity>` | Snapshot sang immutable DTO, rồi `List.copyOf` | Tránh rò rỉ object mutable của tầng nghiệp vụ |

Không nhất thiết lúc nào cũng cần bất biến sâu; có use case chủ đích dùng shared mutable state. Nhưng khi thiết kế API mang ý nghĩa **“chỉ đọc, không bị sửa từ bên ngoài”**, hãy nói rõ trạng thái nào được đảm bảo không đổi.

## 13. Các lỗi và hiểu lầm thường gặp

### Hiểu lầm 1 — “`List.copyOf` deep-copy tất cả phần tử”

Sai. Nó giữ tham chiếu tới các phần tử đã có. Điều này **an toàn khi phần tử immutable**, nhưng vẫn để lộ state khi phần tử mutable.

### Hiểu lầm 2 — “Record luôn là immutable object”

Sai. Record chỉ bảo đảm các component field không thể bị gán lại sau khi khởi tạo. Nếu component là mảng, collection hoặc object mutable, state bên trong vẫn có thể bị thay đổi qua tham chiếu.

### Hiểu lầm 3 — “Đã gọi `copyOf` ở constructor, mọi getter đều an toàn”

Chưa chắc. Nếu record chứa `List<MutableEmployee>`, getter trả về list unmodifiable nhưng từng `MutableEmployee` vẫn có thể có setter. Cần đánh giá cả **element type** và nested state.

### Hiểu lầm 4 — “Cần tạo object `String` mới trong mỗi snapshot”

Không cần. `String` immutable, nên việc chia sẻ tham chiếu không làm thay đổi nội dung chuỗi. Tạo identity mới không có lợi ích trong tình huống này.

### Hiểu lầm 5 — “Một `List.copyOf` bên ngoài đủ cho `List<List<String>>`”

Không. Inner list có thể mutable và vẫn được chia sẻ. Cần làm unmodifiable từng inner list hoặc xây dựng mô hình value bất biến khác.

### Hiểu lầm 6 — “Unmodifiable đồng nghĩa thread-safe tuyệt đối”

Không. Vẫn có thể tồn tại mutable object được chia sẻ, lỗi truy cập nguồn đồng thời, hoặc vấn đề công bố object. Hãy tách vấn đề bất biến với chiến lược đồng bộ.

### Hiểu lầm 7 — “`Set.copyOf` sẽ giữ đúng thứ tự của `LinkedHashSet`”

Không có cam kết thứ tự duyệt. Tránh dùng thứ tự của `Set.copyOf` làm dữ liệu nghiệp vụ hoặc kỳ vọng trong unit test.

### Hiểu lầm 8 — “`Map.copyOf` bảo vệ mọi value object khỏi việc bị sửa”

Không. Mapping không sửa được, nhưng object value mutable vẫn có thể bị sửa từ bên ngoài. Dùng value object immutable hoặc defensive copy theo mô hình dữ liệu.

## 14. Câu hỏi tự kiểm tra

**Câu 1.** Vì sao `List.copyOf(List<String>)` thường là lựa chọn tốt cho một snapshot chỉ đọc?

**Đáp án:** List kết quả không cho sửa cấu trúc, còn `String` không có trạng thái mutable. Chia sẻ tham chiếu đến các chuỗi không tạo đường sửa nội dung của chuỗi đã được công bố.

**Câu 2.** Với `List<StringBuilder>`, `List.copyOf` có bảo đảm nội dung chuỗi không đổi sau khi công bố không?

**Đáp án:** Không. `StringBuilder` có thể bị sửa; bản sao giữ tham chiếu đến cùng builder. Nếu cần dữ liệu immutable, chuyển builder thành `String` trước khi công bố.

**Câu 3.** Trong record `Order(String id, List<Item> items)`, vì sao cần viết `items = List.copyOf(items)` ở constructor?

**Đáp án:** Để tránh giữ trực tiếp `ArrayList` mutable do caller cung cấp. Sau constructor, caller không thể thêm/xóa phần tử trong record bằng cách sửa list đầu vào. Cần bảo đảm `Item` cũng immutable để đạt mô hình bất biến sâu.

**Câu 4.** Nếu `Item` là `record Item(String sku, int price)`, snapshot và nguồn cùng trỏ tới một object `Item` có nguy hiểm không?

**Đáp án:** Không đối với trạng thái được biểu diễn bởi các component `String` và `int`, vì chúng immutable. Không cần nhân bản `Item` chỉ để có địa chỉ bộ nhớ khác.

**Câu 5.** `record Team(List<List<String>> groups)` gọi `List.copyOf(groups)` đã đủ chưa?

**Đáp án:** Chưa đủ nếu inner lists mutable. Phải copy từng inner list và tạo outer list unmodifiable, còn `String` có thể chia sẻ.

**Câu 6.** `Map.copyOf(Map<String, MutableAccount>)` có bảo vệ trạng thái `MutableAccount` không?

**Đáp án:** Không. Nó chặn thay mapping nhưng vẫn chia sẻ object value. Dùng immutable DTO hoặc copy sâu các trường cần tách.

**Câu 7.** Tại sao không nên dựa vào `copy != source` để kiểm tra `copyOf`?

**Đáp án:** API có thể tái sử dụng instance của một input đã unmodifiable phù hợp. Tiêu chí đúng là hợp đồng nội dung và khả năng sửa, không phải identity của container.

**Câu 8.** `List.copyOf` có chấp nhận phần tử `null` không?

**Đáp án:** Không. `List.copyOf` từ chối phần tử `null` và nguồn `null` bằng `NullPointerException`. `Set.copyOf` và `Map.copyOf` cũng áp dụng những hạn chế null tương ứng.

**Câu 9.** Vì sao cần các key có `equals/hashCode` ổn định khi dùng `Set.copyOf` hay `Map.copyOf`?

**Đáp án:** Một object key hoặc phần tử set bị thay đổi field ảnh hưởng equality/hashing có thể làm việc tra cứu mất tính nhất quán. Immutable value object giúp ngăn vấn đề đó.

**Câu 10.** Một record chứa `byte[]` có thể đạt bất biến ở trạng thái công bố bằng cách nào?

**Đáp án:** Clone mảng ở constructor để không nhận trực tiếp mảng mutable của caller, và clone khi trả ra qua accessor. Với mảng chứa mutable object, còn phải kiểm tra các object phần tử chứ không chỉ clone mảng.

## 15. Ghi nhớ cuối bài

1. **`copyOf` chỉ khóa cấu trúc hoặc mapping của collection, không sao chép sâu element.**
2. **Kết hợp collection unmodifiable với các value object immutable** để tránh rò rỉ trạng thái qua phần tử.
3. Với Java 17+, **record + compact constructor dùng `List.copyOf`/`Set.copyOf`/`Map.copyOf`** là mẫu thiết kế rõ ràng; nhưng record có component mutable không tự immutable sâu.
4. Với dữ liệu lồng nhau, phải kiểm tra và sao chép phòng vệ **từng tầng mutable được công bố**.
5. Với `Set` và `Map`, dùng khóa immutable có equality/hashCode ổn định; không dựa vào thứ tự duyệt từ `copyOf`.
6. Chia sẻ immutable object là **chủ đích tốt về hiệu quả**, không phải lỗi thiết kế. Chỉ deep-copy phần trạng thái mutable mà hợp đồng thực sự cần tách biệt.
7. Kiểm thử thiết kế chỉ đọc bằng cả hai phép: **sửa nguồn sau khi tạo snapshot** và **thử sửa dữ liệu qua object graph đã công bố**.

**Tài liệu tham khảo còn áp dụng:**
- [Java SE 17 — `List.copyOf(Collection)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)).
- [Java SE 17 — `Set.copyOf(Collection)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)).
- [Java SE 17 — `Map.copyOf(Map)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)).
- [Java SE 17 — `Record`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Record.html).
- [Java SE 17 — `Stream.toList()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#toList()).
