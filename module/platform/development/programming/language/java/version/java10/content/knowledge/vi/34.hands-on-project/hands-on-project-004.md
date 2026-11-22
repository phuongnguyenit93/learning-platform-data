# Thiết kế đối tượng trả danh sách bằng `List.copyOf` — Java 10+

## 1. Bài toán thiết kế: làm sao trả dữ liệu mà không lộ trạng thái bên trong?

Trong một ứng dụng Java, đối tượng nghiệp vụ thường có danh sách:

- Giỏ hàng trả về danh sách mặt hàng.
- Đơn hàng trả về các dòng chi tiết.
- Lịch học trả về các buổi học đã đăng ký.
- Một cấu hình trả về danh sách quyền truy cập.
- Kết quả dịch vụ trả về danh sách DTO.
- Một bản snapshot của trạng thái được truyền giữa các tầng.

Nếu getter trả trực tiếp một `ArrayList` đang được giữ bên trong, caller có thể sửa nó:

```java
// MINH HỌA ANTI-PATTERN: không phải source độc lập.
public final class BadOrder {
    private final List<String> itemCodes = new ArrayList<>();

    public List<String> getItemCodes() {
        return itemCodes; // Lộ chính reference mutable nội bộ.
    }
}

// Caller có thể viết:
order.getItemCodes().clear(); // Thay đổi trạng thái BadOrder.
```

Điều này vi phạm **encapsulation**: chỉ riêng việc đọc kết quả getter cũng cho phép một phần code bên ngoài thay đổi dữ liệu mà đối tượng phải quản lý. Nếu trong object có invariant (ví dụ đơn hàng phải có ít nhất một mặt hàng hoặc tổng số lượng phải đồng bộ), caller có thể phá invariant mà không đi qua validation.

Bắt đầu từ **Java 10**, `List.copyOf(Collection<? extends E>)` cho một cách ngắn gọn để tạo **danh sách không thể chỉnh sửa** mang các phần tử trong collection nguồn theo thứ tự duyệt. Nó giúp xác định **ranh giới sở hữu dữ liệu** khi constructor nhận danh sách từ caller và khi public API trả danh sách.

Ý tưởng chuẩn:

```java
// Mẫu áp dụng khi phần tử đã đủ bất biến.
private final List<Item> items;

public OrderSnapshot(Collection<? extends Item> source) {
    this.items = List.copyOf(source);
}

public List<Item> items() {
    return items;
}
```

**Vấn đề trọng tâm:** `List.copyOf` bảo vệ **cấu trúc của danh sách**, nhưng **không tự biến các đối tượng phần tử thành bất biến**. Nếu `Item` mutable thì getter vẫn có thể làm lộ trạng thái thông qua `items().get(0).set...`. Bài này phân biệt rõ hai tầng để tránh một thiết kế chỉ “trông có vẻ immutable”.

## 2. Mục tiêu học tập và phạm vi Java hiện hành

Sau bài, bạn có thể:

1. Giải thích chính xác hợp đồng `List.copyOf` kể từ Java 10.
2. Thiết kế đối tượng có `private final List<T>` và copy dữ liệu ở constructor.
3. Trả `List<T>` từ getter mà không lộ một danh sách có thể sửa.
4. Hiểu snapshot khác với unmodifiable **view**.
5. Kiểm thử thay đổi source sau khi constructor đã chạy.
6. Phân biệt các thao tác structural mutation với thay đổi state của phần tử.
7. Biết `List.copyOf` chỉ là **shallow copy** đối với element references.
8. Chọn phần tử immutable (ví dụ record chứa `String` và primitive) để có snapshot đáng tin.
9. Sao chép/chuẩn hóa phần tử mutable thành DTO bất biến khi cần.
10. Bảo vệ nested lists bằng `List.copyOf` ở từng tầng.
11. Xử lý `null` collection và `null` elements theo API contract.
12. Hiểu giữ iteration order và giữ các phần tử trùng lặp.
13. Phân biệt `List.copyOf`, `List.of`, `Collections.unmodifiableList` và `ArrayList`.
14. So sánh `Stream.toList` và `Collectors.toUnmodifiableList` trên JDK mới.
15. Thiết kế object versioning với `withItem` mà không mutate object cũ.
16. Tránh copy không cần thiết trong getter của immutable object.
17. Biết giới hạn khi nguồn bị sửa **đồng thời** trong lúc copy.
18. Tránh dựa vào `==`, `System.identityHashCode` hoặc monitor của value-based lists.
19. Viết unit tests cho contract “không thay đổi cấu trúc”.
20. Dùng Java 17+ biên dịch và chạy một demo đầy đủ, stdout đã kiểm thử.
21. Phân biệt Java 10 `List.copyOf` với Java 16+ `record` và `Stream.toList`.
22. Đưa ra API contract, lỗi phổ biến, checklist triển khai và phương pháp đo hiệu năng.

**Ghi chú cập nhật:** Oracle **Java SE 26 `List.copyOf`** vẫn tài liệu hóa hành vi nêu ở đây. Bài không phụ thuộc API preview, thư viện legacy hoặc một đặc tính nội bộ không được cam kết của JVM.

## 3. Hợp đồng chính xác của `List.copyOf`

Chữ ký API:

```java
static <E> List<E> copyOf(Collection<? extends E> coll)
```

Theo Java SE 26, phương thức:

- Trả một **unmodifiable List** chứa những phần tử được lấy từ `coll` theo **thứ tự iteration** của collection nguồn.
- **Không cho `coll` là `null`**.
- **Không cho phần tử nào của `coll` là `null`**.
- Nếu source collection bị sửa **sau** khi copy, danh sách trả về **không phản ánh** những thay đổi cấu trúc này.
- `UnsupportedOperationException` được dùng khi caller thử mutate unmodifiable list (ví dụ `add`, `remove`, `set`).
- Nếu input đã là một danh sách bất biến phù hợp, implementation **có thể tái sử dụng instance** thay vì tạo instance mới; không bảo đảm mỗi lần gọi luôn cấp phát một object mới.
- Kết quả là một **value-based list**: code không được dựa vào identity để phân biệt các danh sách có nội dung bằng nhau.

```java
List<String> source = new ArrayList<>(List.of("a", "b"));
List<String> result = List.copyOf(source);

source.add("c");
System.out.println(result); // [a, b]
```

Đây là đoạn **minh họa** (cần import `java.util.List` và `java.util.ArrayList`), còn bài có một chương trình độc lập ở mục 10.

### Chính xác “unmodifiable” nghĩa là gì?

Không thể chỉnh sửa **phần tử ở vị trí nào trong danh sách**, chẳng hạn thêm/xóa/thay reference của một element.

**Nhưng:** nếu list chứa `MutableNote`, caller vẫn có thể gọi `list.get(0).rename("new")` và thay state của object phần tử.

Như vậy:

```text
List.copyOf
     |
     +--> ngăn add/remove/set/clear ở List
     +--> chặn thay đổi cấu trúc nguồn xuất hiện về sau
     |
     x--> KHÔNG tự sao chép sâu các element objects
     x--> KHÔNG tự đóng băng state của mutable elements
```

Đây là kiến thức quan trọng nhất khi thiết kế đối tượng trả danh sách.

## 4. Thiết kế ranh giới sở hữu dữ liệu

Một object snapshot nên có mô hình:

```text
Caller A sở hữu ArrayList ban đầu
       |
       | new OrderSnapshot(callerList)
       v
Constructor:
    validate các ràng buộc
    List.copyOf(callerList)
       |
       v
OrderSnapshot sở hữu List không thể chỉnh sửa
       |
       | items() trả List từ snapshot
       v
Caller B chỉ được đọc List
    - không add/remove/set
    - không làm thay đổi snapshot của caller A
```

**Hai chiều phải được bảo vệ:**

1. **Input boundary:** caller tạo object không còn thay đổi state của object đó bằng cách sửa collection input sau constructor.
2. **Output boundary:** caller nhận getter không thay đổi state của object bằng cách sửa collection trả về.

Nếu chỉ thực hiện bước (2) bằng cách bọc một view, nhưng không thực hiện bước (1), object vẫn có thể bị sửa “ngầm” qua source collection bên ngoài.

### Các invariant đáng bảo vệ

Giả sử `OrderSnapshot` đã xác thực:

- Item code không rỗng.
- Quantity > 0.
- Danh sách được giữ theo đúng thứ tự.
- Một số nghiệp vụ khác đã tính tổng số lượng.

Nếu caller có thể thay dữ liệu bên trong sau thời điểm xác thực, các invariant không còn đúng.

**Cách khắc phục:** dùng List snapshot và những element types đủ immutable. Khi cần cập nhật, tạo phiên bản mới với validation một lần nữa.

## 5. Thiết kế chuẩn của constructor và getter

Một mẫu tốt:

```java
// Trong class có import java.util.Collection, List, Objects.
public final class OrderSnapshot {
    private final List<Item> items;

    public OrderSnapshot(Collection<? extends Item> source) {
        Objects.requireNonNull(source, "source");
        this.items = List.copyOf(source);
    }

    public List<Item> items() {
        return items;
    }
}
```

Đây là **mẫu rút gọn**; phải có kiểu `Item` và các imports để thành một file hoàn chỉnh. Trong chương trình đầy đủ, `Item` là record có components bất biến và có validation.

### Tại sao copy ở constructor?

- Constructor là lúc object nhận **quyền sở hữu một snapshot** của đầu vào.
- Không giữ reference tới `ArrayList` của caller.
- Bất kỳ `source.add(...)` hoặc `source.set(...)` **sau constructor** không làm thay đổi danh sách snapshot.
- Cấu trúc unmodifiable giữ object không bị sửa qua getter.

### Tại sao getter chỉ `return items`?

Vì `items` đã được kiểm soát và không cho chỉnh sửa cấu trúc. Nếu phần tử cũng immutable, trả cùng list như một **read-only value** là hợp lý; không cần `List.copyOf(items)` cho mỗi lần gọi getter.

**Cẩn thận:** “getter có thể return trực tiếp list” chỉ đúng khi object đã snapshot nguồn và phần tử không mở ra đường mutable state nguy hiểm. Với danh sách mutable elements hoặc backing view, return trực tiếp vẫn có thể làm lộ state.

### Tại sao dùng kiểu `List<Item>` cho field và return?

Client nên phụ thuộc **giao diện** `List` thay vì class `ArrayList` cụ thể. Điều này thể hiện rõ contract dữ liệu có thứ tự, cho phép thay implementation, tránh vô tình hứa hẹn khả năng mutate.

Không khai báo getter trả `ArrayList<Item>` nếu muốn kết quả unmodifiable, vì implementation từ `List.copyOf` không cần là `ArrayList`.

## 6. Phân biệt `List` và `Collection` làm đầu vào

Chữ ký `copyOf` nhận `Collection<? extends E>`, không bắt buộc nhận `List<E>`. Do đó có thể copy từ:

- `ArrayList`.
- `LinkedList`.
- `LinkedHashSet`.
- Một collection khác cho phép duyệt ổn định.

Ví dụ:

```java
Collection<String> source = new LinkedHashSet<>(
        List.of("B", "A", "C"));
List<String> copied = List.copyOf(source);
```

Bởi vì `LinkedHashSet` duyệt theo insertion order, `copied` nhận thứ tự `B, A, C`.

**Không được suy ra mọi Set có thứ tự ổn định.** `HashSet` không cam kết iteration order. `List.copyOf` **giữ thứ tự iteration hiện tại của nguồn**, chứ không tự sort. Nếu API yêu cầu sắp xếp cụ thể, hãy sort trước khi copy hoặc lấy nguồn có ordering được định nghĩa rõ.

### Vì sao dùng generic `? extends Item`?

Constructor có thể nhận collection chứa các subtype của `Item` khi kiểu phần tử cho phép, không buộc mọi caller phải có chính xác `Collection<Item>`.

Trong bài, `Item` là record (final) nên không có subtype; wildcard vẫn minh họa API `List.copyOf` generic và giúp người học hiểu chữ ký trong thư viện. Nếu domain cố định chỉ dùng record này, `Collection<Item>` cũng là một lựa chọn API đơn giản hợp lệ.

## 7. Giữ thứ tự và giữ duplicate elements

Một danh sách có thể chứa phần tử trùng lặp, ví dụ các dòng hàng hóa được lặp trong lịch sử:

```java
List<String> source = List.of("A", "B", "A");
List<String> snapshot = List.copyOf(source);

// snapshot: [A, B, A]
```

`List.copyOf` **không phải `Set.copyOf`**:

- Không tự loại trùng.
- Không gộp phần tử theo `equals`.
- Không tự sắp xếp.
- Không bỏ phần tử `A` thứ hai.
- Giữ order của source `Collection` khi duyệt.

Nếu nghiệp vụ yêu cầu uniqueness, phải thiết kế một quy tắc riêng, ví dụ kiểm duplicates trước khi snapshot hoặc dùng một `Set` với hợp đồng thích hợp. **Không thay `List.copyOf` bằng `Set.copyOf` chỉ vì muốn kết quả unmodifiable**: việc đó làm thay đổi ngữ nghĩa dữ liệu.

### Thứ tự của list khác thứ tự của unordered source

`List.copyOf(hashSet)` không cam kết cùng một thứ tự giữa JVM runs nếu `hashSet` vốn không có encounter order ổn định. Điều **được cam kết** là list tuân theo thứ tự mà source iterator thực tế cung cấp tại thời điểm copy thích hợp.

Nếu kết quả API hiển thị cho người dùng theo một thứ tự cụ thể, nên **xếp thứ tự nguồn trước**:

```java
List<String> ordered = source.stream()
        .sorted()
        .toList(); // Java 16+, unmodifiable list.
```

`Stream.toList()` là API Java 16+; không coi nó là API mới của Java 10.

## 8. Bất biến “vùng chứa” và bất biến “phần tử” khác nhau

Xét:

```java
final class MutableNote {
    private String text;

    MutableNote(String text) {
        this.text = text;
    }

    void rename(String text) {
        this.text = text;
    }

    String text() {
        return text;
    }
}
```

Nếu lưu:

```java
MutableNote note = new MutableNote("draft");
List<MutableNote> notes = List.copyOf(List.of(note));

note.rename("published");
System.out.println(notes.get(0).text()); // published
```

**Không có mâu thuẫn** với hợp đồng `List.copyOf`. Snapshot giữ **reference tới chính `note`**; chỉ ngăn thay đổi việc reference nào đang ở index 0.

### Quy tắc thiết kế

Nếu object được gọi là **snapshot bất biến** theo nghĩa người dùng muốn nội dung không đổi, cần:

- Element type thực sự immutable, **hoặc**
- Mapping sang DTO immutable, **hoặc**
- Defensive copy **từng element**, nếu thư viện/kiểu dữ liệu cho phép clone/copy đúng ngữ nghĩa.

Một `List<MutableNote>` unmodifiable **không đủ** để cam kết “nội dung snapshot không bao giờ đổi”.

### Tại sao `record` cũng cần suy nghĩ?

Record trong Java được mô tả là **shallowly immutable**. Record có component kiểu `String`, `int` thường thuận lợi cho một DTO immutable. Nhưng record có component `List<T>` hoặc mảng vẫn có thể chứa dữ liệu mutable.

Ví dụ:

```java
// Trong file cùng import java.util.List.
record UnsafeResponse(List<String> codes) {
    // Không defensive copy: caller có thể sửa list nguồn.
}
```

Muốn bảo vệ:

```java
record SafeResponse(List<String> codes) {
    SafeResponse {
        codes = List.copyOf(codes);
    }
}
```

Đây là **mã minh họa record Java 16+**, không phải một tính năng ngôn ngữ đã có trong Java 10. API `List.copyOf` mới là phần có từ Java 10.

## 9. Nested lists: phải bảo vệ từng cấp

`List.copyOf` ở outer list chỉ đóng băng **outer structure**.

```java
List<String> inner = new ArrayList<>(List.of("x"));
List<List<String>> outer = List.copyOf(List.of(inner));

inner.add("y");
System.out.println(outer.get(0)); // [x, y]
```

Outer list không cho `outer.add(...)`, nhưng inner list vẫn sửa được.

Nếu muốn cả hai cấp đều unmodifiable và không bị source thay đổi, cần snapshot **từng inner list** rồi snapshot outer:

```java
List<List<String>> safeOuter = List.copyOf(
        source.stream()
              .map(List::copyOf)
              .toList()
);
```

Mã trên minh họa khi `source` là `Collection<List<String>>` phù hợp và các inner lists không có null. Với Java 17+, `Stream.toList` dùng được. `List.copyOf` outer có thể không cần nếu intermediate đã là unmodifiable list với snapshot inner values, nhưng dùng trong ví dụ để nhấn mạnh contract đầu ra và cùng null-policy.

**Không gọi đây là deep copy tổng quát cho mọi đồ thị object.** Nó chỉ copy hai tầng list và giữ references của các `String` elements (bản thân `String` immutable). Nếu phần tử là `MutableUser` thì cần xử lý sâu thêm.

### Record chứa nested list

```java
record MatrixView(List<List<String>> rows) {
    MatrixView {
        rows = List.copyOf(
                rows.stream()
                    .map(List::copyOf)
                    .toList());
    }
}
```

Đây cũng là đoạn minh họa Java 17+ (cần imports). Nó có thể bảo vệ structure của hai tầng nhưng không thiết lập được mọi invariant nghiệp vụ (ví dụ mọi hàng phải cùng độ dài); constructor cần validation tương ứng nếu contract yêu cầu.

## 10. Ví dụ đầy đủ Java 17+: thiết kế snapshot, getter và update mới

Tạo tệp **`ListCopyOfReturnDesignDemo.java`**:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collection;
import java.util.Collections;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

public final class ListCopyOfReturnDesignDemo {
    public record Item(String code, int quantity) {
        public Item {
            Objects.requireNonNull(code, "code");
            if (code.isBlank() || quantity <= 0) {
                throw new IllegalArgumentException("invalid item");
            }
        }
    }

    public static final class OrderSnapshot {
        private final List<Item> items;

        public OrderSnapshot(Collection<? extends Item> source) {
            this.items = List.copyOf(Objects.requireNonNull(source, "source"));
        }

        public List<Item> items() {
            return items;
        }

        public OrderSnapshot withItem(Item item) {
            Objects.requireNonNull(item, "item");
            List<Item> next = new ArrayList<>(items);
            next.add(item);
            return new OrderSnapshot(next);
        }

        public int totalQuantity() {
            return items.stream().mapToInt(Item::quantity).sum();
        }
    }

    public static final class MutableNote {
        private String text;

        public MutableNote(String text) {
            this.text = Objects.requireNonNull(text, "text");
        }

        public void rename(String text) {
            this.text = Objects.requireNonNull(text, "text");
        }

        public String text() {
            return text;
        }
    }

    public record NoteView(String text) {
        public NoteView {
            Objects.requireNonNull(text, "text");
        }
    }

    private static String codes(List<Item> items) {
        return items.stream().map(Item::code).collect(Collectors.joining(","));
    }

    private static boolean unsupported(Runnable task) {
        try {
            task.run();
            return false;
        } catch (UnsupportedOperationException expected) {
            return true;
        }
    }

    private static boolean nullRejected(Runnable task) {
        try {
            task.run();
            return false;
        } catch (NullPointerException expected) {
            return true;
        }
    }

    public static void main(String[] args) {
        List<Item> input = new ArrayList<>(List.of(
                new Item("A", 2), new Item("B", 1), new Item("A", 2)));
        OrderSnapshot snapshot = new OrderSnapshot(input);

        System.out.println("original=" + codes(snapshot.items()));
        System.out.println("originalQuantity=" + snapshot.totalQuantity());
        input.set(0, new Item("Z", 9));
        input.add(new Item("C", 4));
        System.out.println("sourceAfterEdit=" + codes(input));
        System.out.println("snapshotAfterEdit=" + codes(snapshot.items()));
        System.out.println("addRejected=" + unsupported(
                () -> snapshot.items().add(new Item("X", 1))));
        System.out.println("setRejected=" + unsupported(
                () -> snapshot.items().set(0, new Item("X", 1))));
        System.out.println("removeRejected=" + unsupported(
                () -> snapshot.items().remove(0)));
        System.out.println("clearRejected=" + unsupported(
                () -> snapshot.items().clear()));

        OrderSnapshot newer = snapshot.withItem(new Item("D", 5));
        System.out.println("newVersion=" + codes(newer.items()));
        System.out.println("oldVersion=" + codes(snapshot.items()));
        System.out.println("newQuantity=" + newer.totalQuantity());

        List<Item> liveView = Collections.unmodifiableList(input);
        List<Item> frozen = List.copyOf(liveView);
        input.add(new Item("E", 3));
        System.out.println("liveViewSize=" + liveView.size());
        System.out.println("frozenSize=" + frozen.size());
        System.out.println("snapshotSize=" + snapshot.items().size());

        MutableNote note = new MutableNote("draft");
        List<MutableNote> shallow = List.copyOf(List.of(note));
        List<NoteView> projected = List.copyOf(shallow.stream()
                .map(n -> new NoteView(n.text()))
                .collect(Collectors.toList()));
        note.rename("published");
        System.out.println("shallowMutableText=" + shallow.get(0).text());
        System.out.println("projectedImmutableText=" + projected.get(0).text());

        List<String> inner = new ArrayList<>(List.of("x"));
        List<List<String>> shallowNested = List.copyOf(List.of(inner));
        List<List<String>> deepNested =
                List.copyOf(List.of(List.copyOf(inner)));
        inner.add("y");
        System.out.println("shallowNested=" + String.join(",", shallowNested.get(0)));
        System.out.println("deepNested=" + String.join(",", deepNested.get(0)));
        System.out.println("deepNestedMutationRejected=" + unsupported(
                () -> deepNested.get(0).add("z")));

        System.out.println("nullElementRejected=" + nullRejected(
                () -> List.copyOf(Arrays.asList("x", null))));
        System.out.println("nullCollectionRejected=" + nullRejected(
                () -> List.copyOf((Collection<String>) null)));
        System.out.println("emptySize=" +
                List.copyOf(Collections.<String>emptyList()).size());
        Collection<String> orderedSet = new LinkedHashSet<>(List.of("B", "A", "C"));
        System.out.println("setIterationOrder=" + String.join(",", List.copyOf(orderedSet)));
        System.out.println("duplicatesPreserved=" +
                (List.copyOf(List.of("A", "A", "B")).size() == 3));
    }
}
```

Biên dịch:

```bash
javac --release 17 -encoding UTF-8 ListCopyOfReturnDesignDemo.java
```

Chạy:

```bash
java ListCopyOfReturnDesignDemo
```

**Stdout chính xác đã kiểm thử trên JDK 24 với mục tiêu Java 17:**

```text
original=A,B,A
originalQuantity=5
sourceAfterEdit=Z,B,A,C
snapshotAfterEdit=A,B,A
addRejected=true
setRejected=true
removeRejected=true
clearRejected=true
newVersion=A,B,A,D
oldVersion=A,B,A
newQuantity=10
liveViewSize=5
frozenSize=4
snapshotSize=3
shallowMutableText=published
projectedImmutableText=draft
shallowNested=x,y
deepNested=x
deepNestedMutationRejected=true
nullElementRejected=true
nullCollectionRejected=true
emptySize=0
setIterationOrder=B,A,C
duplicatesPreserved=true
```

**Lưu ý tương thích:** `List.copyOf` có từ Java 10. Demo dùng `record` (Java 16+) để minh họa element DTO bất biến, do đó yêu cầu compiler target Java 17+ theo quy trình của bài. Các khái niệm List.copyOf cũng áp dụng cho class Java 10 thông thường.

### Ba nhóm quan trọng của ví dụ

1. **`OrderSnapshot`**: constructor nhận mutable collection và tạo snapshot qua `List.copyOf`; getter trả list unmodifiable; phương thức `withItem` tạo **một object mới**.
2. **`MutableNote` / `NoteView`**: minh họa giữ nguyên reference của phần tử mutable, rồi đưa dữ liệu vào DTO record bất biến trước khi trả.
3. **Nested lists + null/ordering tests**: chỉ copy outer list là không đủ, null bị từ chối, duplication được giữ và iteration order được bảo toàn.

Tất cả test chạy trong bộ nhớ; không cần Docker, Internet, database hoặc thư viện ngoài JDK.

## 11. Đọc từng phần stdout của demo

### Nhóm A — bảo vệ input boundary

```text
original=A,B,A
originalQuantity=5
sourceAfterEdit=Z,B,A,C
snapshotAfterEdit=A,B,A
```

Khi tạo snapshot, source có ba phần tử: A(2), B(1), A(2). `OrderSnapshot` lưu list mới theo iteration order: `A,B,A`. Tổng số lượng là 2 + 1 + 2 = 5.

Sau đó caller sửa source: thay phần tử đầu bằng Z(9), thêm C(4). **Snapshot không phản ánh cả việc thay và thêm**, vì list của object đã chốt tại thời điểm xây dựng. Đây là phép thử thực tế cho cả constructor ownership và API return.

### Nhóm B — cấm thay đổi cấu trúc đầu ra

```text
addRejected=true
setRejected=true
removeRejected=true
clearRejected=true
```

Các thao tác:

- `add(...)`: thêm phần tử.
- `set(index,...)`: thay reference tại một vị trí.
- `remove(index)`: xóa phần tử.
- `clear()`: xóa tất cả.

đều bị unmodifiable list từ chối bằng `UnsupportedOperationException`.

Không nên chỉ test `add` mà quên `set`; một danh sách “fixed size” như `Arrays.asList` có thể cấm thêm/xóa nhưng **cho `set`**, nên nó chưa đủ để xây dựng read-only output contract.

### Nhóm C — tạo phiên bản object mới

```text
newVersion=A,B,A,D
oldVersion=A,B,A
newQuantity=10
```

`withItem(new Item("D",5))`:

1. Copy các phần tử của snapshot cũ vào `ArrayList` tạm.
2. Thêm item mới vào list tạm.
3. Xây `new OrderSnapshot(next)` và tiếp tục áp dụng List.copyOf.
4. Trả **object mới**, không sửa object cũ.

Cả hai snapshot đều tồn tại đồng thời với dữ liệu riêng về list structure. Cách này hữu ích cho event processing, versioned read models hoặc cấu trúc immutable DTO nhỏ, khi hiệu năng/memory đã được cân nhắc.

### Nhóm D — unmodifiable view không phải snapshot

```text
liveViewSize=5
frozenSize=4
snapshotSize=3
```

`liveView = Collections.unmodifiableList(input)` chỉ bọc nguồn bằng một **view không cho caller chỉnh sửa qua view**. Nhưng khi `input.add(E)`, `liveView.size()` tăng theo.

`frozen = List.copyOf(liveView)` đã có một snapshot tại thời điểm lấy; source đổi về sau không thay `frozen`. Snapshot ban đầu `snapshot` vẫn chỉ có ba items.

### Nhóm E — shallow element references

```text
shallowMutableText=published
projectedImmutableText=draft
```

`MutableNote` ban đầu có text `draft`. `shallow` giữ reference của object đó. Sau khi `note.rename("published")`, cả `note` và `shallow.get(0)` nói `published`.

`projected` chứa `NoteView` record **đã được tạo từ trạng thái `draft` trước khi rename**, nên không thay đổi. Đây là mẫu **projection sang immutable DTO** trước khi công bố dữ liệu.

### Nhóm F — nested lists

```text
shallowNested=x,y
deepNested=x
deepNestedMutationRejected=true
```

Outer List.copyOf không bảo vệ inner list; nested copy bảo vệ structure của inner list (với `String` immutable). Lệnh thử thay inner snapshot bị từ chối.

### Nhóm G — hợp đồng đầu vào

```text
nullElementRejected=true
nullCollectionRejected=true
emptySize=0
setIterationOrder=B,A,C
duplicatesPreserved=true
```

- Null elements và null collection bị từ chối.
- Empty collection tạo empty unmodifiable list hợp lệ.
- `LinkedHashSet` duyệt `B,A,C` nên `List.copyOf` giữ đúng iteration order đó.
- Duplicates `A,A,B` được giữ nguyên theo ngữ nghĩa List.

## 12. `List.copyOf` và `Collections.unmodifiableList`: khác nhau ở điểm quyết định

Hai API có mục đích dùng được nhưng **không hoán đổi ngữ nghĩa**.

| Khía cạnh | `List.copyOf(source)` | `Collections.unmodifiableList(source)` |
| --- | --- | --- |
| Kết quả có cho caller mutate qua kết quả? | Không | Không |
| Thay đổi cấu trúc nguồn sau lúc tạo có phản ánh? | **Không** | **Có**, view phản ánh backing list |
| Được gọi với `Collection` bất kỳ? | Có | Cần `List` |
| Reject null elements? | Có | View phụ thuộc backing list; có thể chứa null |
| Tạo một snapshot độc lập của structure? | Có | Không, nếu chỉ bọc mutable source |
| Copy sâu element objects? | Không | Không |
| Khi source đã là unmodifiable immutable list | Có thể reuse | Tạo wrapper/view theo API semantics |
| Dùng cho **constructor defensive copy** | Rất phù hợp | Chưa đủ nếu caller vẫn giữ mutable source |
| Dùng khi **muốn view theo dõi source** | Không | Phù hợp nếu đó là contract |

**Bảng không nói `Collections.unmodifiableList` là legacy.** Đây là API hiện hành và có use case hợp lệ khi người thiết kế **cố ý muốn live read-only view**. Nó chỉ không giải quyết input aliasing khi mục tiêu là immutable snapshot.

### Ví dụ lớp lỗi

```java
// Sai nếu contract hứa snapshot bất biến:
public final class BadSnapshot {
    private final List<String> codes;

    public BadSnapshot(List<String> source) {
        codes = Collections.unmodifiableList(source);
    }

    public List<String> codes() {
        return codes;
    }
}
```

Caller còn giữ `source` và có thể sửa nó; `codes()` đổi theo.

**Cách sửa ngắn:**

```java
codes = List.copyOf(source);
```

Nếu cần giữ null elements vì hợp đồng nghiệp vụ cũ, `List.copyOf` không phải API thay thế trực tiếp; phải chủ động chọn null policy/representation khác thay vì âm thầm bỏ qua.

## 13. Phân biệt `List.copyOf`, `List.of` và `ArrayList`

`List.of` được giới thiệu từ **Java 9**:

```java
List<String> fixed = List.of("read", "write");
```

Nó tiện để tạo một unmodifiable list **từ các phần tử được liệt kê tường minh**. `List.copyOf` được giới thiệu từ **Java 10**, tiện để **snapshot một Collection đã tồn tại**:

```java
List<String> copy = List.copyOf(existingCollection);
```

`new ArrayList<>(existingCollection)` tạo một **modifiable copy**:

```java
List<String> writableCopy = new ArrayList<>(existingCollection);
writableCopy.add("new-item");
```

Chọn theo contract:

| Mục tiêu | Cách dùng |
| --- | --- |
| Tạo unmodifiable list từ 2–3 phần tử | `List.of(...)` |
| Bảo vệ API boundary từ source Collection | `List.copyOf(source)` |
| Muốn mutable working buffer độc lập | `new ArrayList<>(source)` |
| Muốn view không mutate qua handle nhưng live updates | `Collections.unmodifiableList(source)` |
| Muốn snapshot và sau đó cập nhật | `new ArrayList<>(snapshot)` → chỉnh sửa → `List.copyOf` |

**Không tự coi `List.of(existingList)` tương đương `List.copyOf(existingList)`.** Nếu `existingList` là một List object, `List.of(existingList)` thường tạo **list một phần tử chứa chính List đó**, tùy overload/type inference, chứ không duyệt ra các elements mong muốn.

## 14. `Stream.toList` và `Collectors.toUnmodifiableList` trên JDK mới

Có nhiều cách tạo unmodifiable list trong Java hiện nay, nhưng cần biết ranh giới và phiên bản.

### `Stream.toList()` — Java 16+

```java
List<String> result = source.stream()
        .map(String::trim)
        .toList();
```

- Kết quả unmodifiable.
- Giữ encounter order nếu stream có thứ tự.
- Không bảo đảm implementation class hoặc reference identity.
- **Có thể chứa null** nếu stream cung cấp null; Javadoc không cấm như `List.copyOf`.
- Có từ Java **16**, không phải Java 10.

### `Collectors.toUnmodifiableList()` — Java 10+

```java
List<String> result = source.stream()
        .map(String::trim)
        .collect(Collectors.toUnmodifiableList());
```

- Kết quả unmodifiable.
- Giữ encounter order khi stream có encounter order.
- **Không chấp nhận null elements**; được ghi rõ trong Javadoc.
- Có từ Java **10**.

### `List.copyOf(...)` — Java 10+

```java
List<String> result = List.copyOf(source);
```

- Nhận một `Collection`, không cần biến thành stream.
- Chọn khi đã có collection cần snapshot.
- Chặn null collection và null elements.
- Nếu collection đã là unmodifiable list phù hợp, có thể reuse nội bộ.

**Không tạo nhiều lớp copy chỉ để “cho chắc”**. Ví dụ trên Java 17, sau `stream.toList()` nếu element đã immutable và không có yêu cầu normalize null thêm, việc gọi `List.copyOf` lần nữa có thể không thêm bảo vệ về cấu trúc. Hãy dùng một cách có hợp đồng rõ ràng, đo khi hot path.

### `Collectors.toList()` khác

`Collectors.toList()` **không bảo đảm** loại implementation, tính chỉnh sửa, serializability hay thread-safety. Dù hiện có thể thường trả `ArrayList`, không viết business contract dựa vào giả định implementation đó.

Khi trả DTO unmodifiable từ một pipeline, `toUnmodifiableList()` hoặc `toList()` (khi null policy phù hợp) là lựa chọn hiện hành. Khi đầu vào đã là Collection, `List.copyOf` là cách trực tiếp.

## 15. Null contract: nên báo lỗi rõ, không âm thầm lọc

Java SE `List.copyOf` ném `NullPointerException` nếu:

- `coll == null`.
- Có ít nhất một phần tử `null` trong source.

```java
List.copyOf(null);                  // NPE
List.copyOf(Arrays.asList("x", null)); // NPE
List.copyOf(List.of());             // empty list hợp lệ
```

Đây là các đoạn gọi minh họa; để chạy cần đặt trong method có imports và xử lý exception phù hợp. Chương trình đầy đủ đã kiểm trực tiếp hai trường hợp NPE.

### Chọn cách giải quyết đúng nhu cầu

**Hợp đồng A — null là đầu vào không hợp lệ:**

```java
public OrderSnapshot(Collection<? extends Item> source) {
    this.items = List.copyOf(Objects.requireNonNull(source, "source"));
}
```

Ưu điểm: fail-fast, caller thấy ngay dữ liệu lỗi. `Objects.requireNonNull` giúp thông báo tên tham số rõ ràng; bản thân `List.copyOf` cũng từ chối null.

**Hợp đồng B — null collection có nghĩa là danh sách rỗng:**

```java
List<String> result = source == null ? List.of() : List.copyOf(source);
```

Chỉ dùng nếu **đó thật sự là quyết định nghiệp vụ**, không phải workaround để giấu bug. Một null source do bug không nên bị tự động biến thành “không có dữ liệu” một cách không có chủ ý.

**Hợp đồng C — null elements có ý nghĩa:**

Cần chọn một representation khác (ví dụ một DTO/Optional có ý nghĩa rõ) hoặc một collection implementation phù hợp rồi thiết kế defensive copy bằng cách khác. **Không dùng `filter(Objects::nonNull)` một cách âm thầm**, vì có thể làm mất dữ liệu và thay đổi kích thước/kết quả mà caller không biết.

## 16. Trường hợp mutable element: nên copy dữ liệu sang value type

Trong domain model, phần tử có thể là entity mutable:

```java
final class UserEntity {
    private String displayName;

    String displayName() { return displayName; }
    void rename(String value) { displayName = value; }
}
```

Nếu service trả:

```java
return List.copyOf(users); // Chỉ ngăn sửa list, vẫn lộ UserEntity mutable.
```

thì client vẫn có thể `result.get(0).rename(...)` nếu method public/accessible. Đây là một **security/data-integrity risk** ở application boundary.

### Cách một — trả DTO bất biến

```java
// Java 17+; các kiểu/biến được minh họa ngoài chương trình độc lập.
record UserView(String displayName) {
    UserView {
        Objects.requireNonNull(displayName);
    }
}

List<UserView> safeViews = users.stream()
        .map(user -> new UserView(user.displayName()))
        .collect(Collectors.toUnmodifiableList());
```

Cách này tạo **một object giá trị mới** cho mỗi entity, giảm nguy cơ client can thiệp state entity.

### Cách hai — copy ở mỗi element

Nếu element type có copy constructor đúng và không chứa mutable nested references, có thể chuyển:

```java
List<SafeElement> safe = List.copyOf(
        source.stream().map(SafeElement::copyOf).toList());
```

Đây là **pseudocode về API thiết kế**, vì `SafeElement.copyOf` không phải một class JDK; code phải được định nghĩa cho kiểu thật. Cần bảo đảm copy constructor/copy method thực hiện đủ sâu theo yêu cầu.

### Cách ba — expose view không chứa mutable entity

Nếu không nên trả full entity, API có thể chỉ trả ID, keys hoặc immutable projection theo use case:

```java
List<String> ids = List.copyOf(
        entities.stream().map(Entity::id).toList());
```

Đoạn mã minh họa giả định `Entity::id` tồn tại và trả non-null String; không phải chương trình độc lập.

**Nguyên tắc:** `List.copyOf` giữ element references; để đạt giá trị bất biến phải thiết kế element type và các references lồng nhau.

## 17. Record trả danh sách: canonical constructor phải snapshot

Một dạng API phổ biến trên Java 17+:

```java
public record OrderResponse(List<Item> items) {
    public OrderResponse {
        items = List.copyOf(Objects.requireNonNull(items, "items"));
    }
}
```

Đây là đoạn minh họa trong project có `Item` và imports. Gán lại biến tham số trong **compact canonical constructor** có tác dụng chuẩn hóa giá trị được gán cho record component.

Nếu không copy:

```java
public record UnsafeOrderResponse(List<Item> items) {}
```

thì caller có thể tạo `new UnsafeOrderResponse(mutable)` rồi sửa `mutable` từ bên ngoài. Record components là `final`, nhưng list mà chúng tham chiếu có thể mutable.

### Getter do record sinh tự động

Accessor `items()` của record trả lại component list. Nếu canonical constructor đã snapshot và element type immutable thì điều này phù hợp: **không cần override accessor chỉ để copy lại mỗi lần**.

Tuy nhiên record **shallowly immutable**, không đảm bảo mọi component object đều immutable. Ví dụ record có field `byte[]`, `Date` hoặc `List<MutableEntity>` cần chính sách defensive copy khác.

### Vấn đề validation

Constructor nên xác thực thêm những bất biến nghiệp vụ:

```java
public record InvoiceLines(List<Item> items) {
    public InvoiceLines {
        items = List.copyOf(Objects.requireNonNull(items, "items"));
        if (items.isEmpty()) {
            throw new IllegalArgumentException("invoice needs at least one line");
        }
    }
}
```

**Đừng viết validation giả định tất cả collections phải không rỗng**. Nếu contract cho phép empty lists, không cần hạn chế đó. Thiết kế phụ thuộc domain.

## 18. Cập nhật bất biến: tạo phiên bản mới thay vì sửa list trả về

Một public API read-only đôi khi vẫn cần hỗ trợ thêm/bớt items theo nghiệp vụ. **Không** biến getter thành chỗ để caller mutate:

```java
// Không nên:
order.items().add(newItem);
```

Thay vào đó, cung cấp business method rõ ràng:

```java
public OrderSnapshot withItem(Item item) {
    Objects.requireNonNull(item, "item");
    List<Item> next = new ArrayList<>(items);
    next.add(item);
    return new OrderSnapshot(next);
}
```

Ưu điểm:

- Validation tập trung ở constructor và business method.
- Snapshot cũ không đổi.
- Có thể so sánh các phiên bản, truyền snapshot đến nhiều tầng.
- Caller không sửa state qua getter.
- API nêu rõ tác dụng: trả **một giá trị mới**, không mutate tại chỗ.

### Khi nào không nên dùng snapshot mỗi update?

Nếu có hàng triệu phần tử và cập nhật liên tục, copy toàn bộ list mỗi lần có thể quá tốn kém. Trong trường hợp đó:

- Dùng mutable aggregate với business methods được kiểm soát, nhưng **không expose backing list**.
- Hoặc dùng cấu trúc persistent/structurally shared nếu thực sự cần immutable updates quy mô lớn.
- Hoặc xuất snapshot tại những điểm đọc cần thiết, có chiến lược đồng bộ.
- Đo memory allocations và latency trước khi áp dụng.

**Không nói `List.copyOf` luôn O(1)**. Nếu source modifiable, thường cần duyệt/sao chép n phần tử; implementation có thể reuse unmodifiable lists nhưng đó là optimization, không phải cam kết identity.

## 19. API đọc liên tục: copy trong constructor hay mỗi getter?

Hai mô hình:

**Mô hình A — snapshot immutable object:**

```java
final class Snapshot {
    private final List<String> values;

    Snapshot(Collection<String> source) {
        values = List.copyOf(source);
    }

    List<String> values() {
        return values;
    }
}
```

Nếu callers không có đường mutating `String` elements và object không thay reference list, mỗi lần getter chỉ trả handle đến unmodifiable list.

**Mô hình B — mutable owner có internal mutable state:**

```java
final class MutableStore {
    private final List<String> values = new ArrayList<>();

    // Cần đảm bảo đồng bộ nếu có nhiều thread.
    public synchronized List<String> snapshot() {
        return List.copyOf(values);
    }

    public synchronized void add(String value) {
        values.add(Objects.requireNonNull(value));
    }
}
```

Ở đây **getter được đặt tên `snapshot()`** vì mỗi lần gọi tạo trạng thái ở thời điểm đọc; đồng bộ với write methods giúp tránh việc copy một ArrayList đang bị mutate cùng lúc.

**Hai mô hình có hợp đồng khác nhau**: A là immutable object, B là mutable object nhưng mỗi lần read trả immutable snapshot. Chọn theo nhu cầu cập nhật và chi phí.

Đừng “tối ưu” bằng cách trả `Collections.unmodifiableList(values)` trong mô hình B rồi gọi đó là snapshot; view ấy sẽ thay đổi khi store cập nhật.

## 20. Đồng thời và safe publication: đừng hiểu sai về thread safety

Một `List.copyOf` có structure unmodifiable là điều kiện có ích cho sharing, nhưng **không tự biến mọi bài toán concurrency thành an toàn**.

### Trường hợp hợp lý

`OrderSnapshot` trong demo:

- Class cuối cùng `final`.
- Field list `private final`.
- Được gán snapshot trong constructor.
- Element `Item` là record với `String` và primitive đã validate.
- Không có setter hoặc đường cập nhật in-place.

Nếu được xây dựng đúng và được publish thích hợp, nhiều thread có thể đọc snapshot như một giá trị không đổi về mặt dữ liệu.

### Trường hợp nguy hiểm

Giả sử thread A đang chạy `List.copyOf(sharedArrayList)` và thread B cùng lúc `sharedArrayList.add(...)` hoặc `clear()` mà không đồng bộ.

Không có cam kết rằng việc copy này là **atomic snapshot** của một `ArrayList` bị sửa đồng thời. Có thể thấy dữ liệu không nhất quán hoặc exception tùy thời điểm/implementation. `List.copyOf` **không khóa source** và không tự giải quyết race conditions.

**Cách đúng:**

- Sao chép dưới một lock đồng bộ với các writers.
- Hoặc sử dụng kiến trúc publish immutable snapshots qua `volatile`/`AtomicReference`/safe publication phù hợp.
- Hoặc dùng một collection concurrency-specific có hợp đồng snapshot traversal được hiểu rõ.
- Nếu source có mutable elements, cũng phải quản lý concurrency của những elements đó.

### Không khóa vào object `List.copyOf`

Danh sách trả về là **value-based**. Không viết:

```java
// Anti-pattern: monitor của value-based result không được dùng làm lock.
synchronized (snapshot.items()) {
    // ...
}
```

Dùng một **lock riêng** hoặc primitive concurrency phù hợp. Điều này quan trọng trên Java hiện đại bởi identity của value-based lists không phải một hợp đồng API ổn định.

## 21. Giá trị, reference và identity của danh sách trả về

Danh sách unmodifiable từ factory có thể:

- Là một instance mới.
- Là một instance được chia sẻ/reuse.
- Là một implementation nội bộ không phải ArrayList.
- Có cùng nội dung với một list khác nhưng khác reference, hoặc cùng reference tùy tối ưu.

Vì vậy **không kiểm**:

```java
// Không nên dùng làm hợp đồng thiết kế:
boolean alwaysDifferent = List.copyOf(source) != source;
```

Nếu source đã là một unmodifiable list phù hợp, Java SE cho phép implementation không tạo copy mới.

**Nên kiểm nội dung/contract:**

```java
List<String> actual = List.copyOf(source);
boolean sameElements = actual.equals(List.of("a", "b"));
```

Với Lists, `equals` có hợp đồng so sánh thứ tự và giá trị elements. Nếu element types mutable, kết quả equality/hashCode vẫn có thể thay đổi theo state của chúng; vì vậy element immutability là điều quan trọng.

### Đừng dùng identity hash hoặc IdentityHashMap

Danh sách value-based không nên làm identity-sensitive operations như `==`, `System.identityHashCode`, `synchronized(list)` hoặc identity-based maps để quyết định business behavior.

Một unit test nên kiểm **semantic outcomes** (nội dung, thứ tự, cách phản ứng khi mutate, input aliasing), không kiểm tên class runtime hay identity.

## 22. Performance và memory: copy ở ranh giới đúng chỗ

`List.copyOf` không phải lúc nào cũng “copy luôn luôn”, cũng không phải lúc nào cũng “copy miễn phí”.

### Thực tế cần cân nhắc

- Khi input là **modifiable collection**, việc tạo snapshot thường phải đọc và lưu các references sang structure mới, chi phí phụ thuộc kích thước.
- Khi input đã là một **unmodifiable list** thích hợp, implementation **có thể reuse instance**.
- Một lần tạo `OrderSnapshot` theo yêu cầu có thể hợp lý hơn việc mỗi getter lặp lại List.copyOf.
- Nếu API trả dữ liệu lớn hàng chục nghìn lần mỗi giây, chi phí allocations/GC đáng đo bằng benchmarks thực tế.
- List.copyOf là **shallow copy**: không phải chi phí clone từng object, nhưng cũng không bảo đảm deep immutability.
- Với nested structures, thêm mỗi tầng snapshot làm tăng công việc và allocations tương ứng.
- Với mutable working buffer, `new ArrayList<>(snapshot)` thường thích hợp trước khi thêm/xóa, rồi có thể List.copyOf khi công bố bản mới.

**Không đưa ra cam kết benchmark tuyệt đối** kiểu “`List.copyOf` nhanh hơn luôn” hoặc “trả list trong getter là O(1) mọi JVM”. Kiểm workload, JDK build, GC và profile thật.

### Các tối ưu sai dễ gây bug

1. Bỏ defensive copy để tiết kiệm một lần allocation → làm lộ input aliasing.
2. Copy mỗi getter dù field immutable → tạo code thừa/chi phí tiềm năng.
3. Dùng unmodifiable view làm snapshot → dữ liệu tiếp tục thay đổi từ source.
4. Dùng custom caching dựa vào `==` của value-based list → contract không ổn.
5. Dùng `parallelStream` không kiểm encounter order và rồi tin List.copyOf tự sắp xếp → order sai.

Tối ưu sau khi đã định nghĩa đúng API contract và có số đo.

## 23. Thiết kế API return type và hợp đồng văn bản

Một getter tên `items()` chưa nói đủ điều về kết quả. Với public API, Javadoc có thể nêu:

```java
/**
 * Returns the items captured when this snapshot was created.
 * The returned list is unmodifiable, preserves item order,
 * and does not reflect later changes to the input collection.
 *
 * @return unmodifiable list of immutable item values, never null
 */
public List<Item> items() {
    return items;
}
```

Đây là đoạn **minh họa Javadoc** bằng tiếng Anh. Khi type `Item` immutable, lời hứa “immutable item values” là hợp lệ. Nếu element là mutable entity, phải sửa docs: **không** hứa immutable contents.

### Nên trả `List`, không trả `Collection`, khi order/index là một phần contract

- `List` thể hiện dữ liệu có order và cho phép index.
- `Collection` tổng quát hơn khi không cần semantics thứ tự.
- `Set` thích hợp cho uniqueness, nhưng không thay List nếu order/duplicates quan trọng.

Nếu caller chỉ cần iterate, `Collection` có thể đủ, nhưng kết quả `List.copyOf` vẫn là một List cụ thể và contract của List là có thứ tự.

### Serialization và API transport

Một `List.copyOf` unmodifiable **không đồng nghĩa** DTO có thể serialize được với mọi thư viện/format. Những frameworks có thể yêu cầu public constructors, setters hoặc có chiến lược mapping khác. **Không bỏ defensive copying chỉ vì JSON mapper cần serialize**; thay vào đó cấu hình mapper/DTO đúng và bảo đảm deserialization đi qua validation nếu contract yêu cầu.

## 24. Getter trả danh sách dưới dạng DTO cho nhiều tầng

Một flow thực tế:

```text
Database / mutable repository entities
             |
             | đọc/validate
             v
Service: chuyển entity -> immutable DTO
             |
             | List.copyOf(...) / toUnmodifiableList()
             v
ReadModel / Response Object
  private final List<ItemView>
             |
             v
Controller / Caller / Other Thread
  đọc List<ItemView> (không sửa được)
```

Điểm thiết kế:

1. Không expose persistence entities mutable nếu contract muốn snapshot.
2. Chuyển sang DTO có fields không mở ra state mutable.
3. Chỉ giữ danh sách unmodifiable trong read model.
4. Để tất cả business updates đi qua commands/service methods, không dựa vào `response.items().add(...)`.
5. Nếu business cần versioning, phản hồi mới thay vì sửa phản hồi cũ.
6. Nếu domain cho phép element mutable, Javadoc phải nói rõ và có cơ chế bảo vệ phù hợp.

### Ví dụ với permissions

Một permission snapshot nên có:

```java
record PermissionView(String resource, String action) {
    PermissionView {
        Objects.requireNonNull(resource);
        Objects.requireNonNull(action);
    }
}
```

Và:

```java
record PermissionResponse(List<PermissionView> permissions) {
    PermissionResponse {
        permissions = List.copyOf(permissions);
    }
}
```

Đây là những **đoạn minh họa Java 17+** riêng, không nằm trong file demo chính. Cần import `List` và `Objects` trong source thật. Chúng phù hợp khi permission values không mutate sau khi tạo.

**Quan trọng:** read-only list **không thực thi authorization**. Controller/service vẫn phải kiểm quyền truy cập theo chính sách hiện hành; immutable DTO chỉ ngăn aliasing và thay đổi ngoài ý muốn.

## 25. Test contract theo hành vi, không theo class implementation

Bộ tests tối thiểu cho object trả List.copyOf:

| Trường hợp | Kỳ vọng |
| --- | --- |
| Tạo object bằng mutable `ArrayList` | Snapshot chứa đúng elements/order |
| Caller `add` vào source sau constructor | Snapshot không đổi |
| Caller `set` vào source sau constructor | Snapshot không đổi |
| Getter `add` vào returned List | `UnsupportedOperationException` |
| Getter `set` vào returned List | `UnsupportedOperationException` |
| Getter `remove`/`clear` | `UnsupportedOperationException` |
| Input collection null | `NullPointerException` theo contract |
| Input chứa null | `NullPointerException` |
| Input rỗng | Empty unmodifiable List |
| Input có duplicates | Duplicates vẫn còn |
| Input là `LinkedHashSet` | Duy trì order của iterator |
| Element mutable bị sửa từ nơi khác | Snapshot nhìn thấy thay đổi element (cảnh báo shallow) |
| Element được map sang DTO immutable | Snapshot DTO không thay |
| Nested list chỉ copy outer | Inner có thể thay |
| Nested list copy từng cấp | Inner snapshot không phản ánh source |
| Cập nhật bằng `withItem` | Old snapshot giữ nguyên; new snapshot có item mới |

### Đừng test kiểu class hoặc reference identity

Không làm:

```java
assertTrue(result.getClass() == java.util.ArrayList.class);
assertNotSame(source, result);
```

`List.copyOf` không hứa implementation class hoặc identity luôn mới. Test hợp đồng **unmodifiable/content** thay vì kiểm “instance nào được reuse”.

### Test Java hợp đồng “không mutate” nên rõ ràng

Với JUnit hiện hành, có thể dùng `assertThrows(UnsupportedOperationException.class, () -> list.add(...))`. Nhưng bài demo không phụ thuộc JUnit để chạy trong mọi JDK 17+, nên có helper `unsupported(Runnable)` ghi kết quả boolean theo hành vi thật.

## 26. Lỗi lập trình thường gặp

### Lỗi A — Trả backing `ArrayList` trực tiếp

Caller có thể thêm/xóa. **Sửa:** thiết kế immutable snapshot, không lộ mutable list.

### Lỗi B — Dùng `Collections.unmodifiableList(source)` rồi coi là snapshot

Nó là read-only **view** trên source; source đổi thì view đổi. **Sửa:** `List.copyOf(source)` khi contract yêu cầu snapshot.

### Lỗi C — Dùng List.copyOf nhưng elements là mutable entities

Chỉ đóng băng list structure, không đóng băng object state. **Sửa:** immutable DTO, copy từng element, validation.

### Lỗi D — Record có `List` component mà không copy

Record shallowly immutable, vẫn giữ reference mutable. **Sửa:** compact constructor với `List.copyOf`.

### Lỗi E — Chỉ copy outer list khi có nested lists

Inner list vẫn mutable. **Sửa:** map `List::copyOf` trên từng inner list và snapshot outer.

### Lỗi F — Nuốt `NullPointerException` rồi trả List rỗng

Che giấu dữ liệu lỗi. **Sửa:** xác định null policy từ API contract; chỉ đổi null thành empty khi thực sự có ý nghĩa.

### Lỗi G — Lọc bỏ null elements không báo caller

Dữ liệu và index/order thay đổi. **Sửa:** validate hoặc dùng representation phù hợp, không silently filter.

### Lỗi H — Dùng `Set.copyOf` để làm danh sách “immutable”

Mất duplicates và thay đổi semantics ordering. **Sửa:** dùng `List.copyOf` nếu nghiệp vụ cần list.

### Lỗi I — Mong `List.copyOf` tự sort

Nó giữ iteration order, không sort. **Sửa:** sort trước nếu API yêu cầu.

### Lỗi J — Dùng `List.of(existingList)` với mục đích copy elements

Có nguy cơ tạo một list chứa **một List element**, không phải snapshot từng phần tử. **Sửa:** `List.copyOf(existingList)`.

### Lỗi K — Coi `Arrays.asList` là read-only

`Arrays.asList` fixed-size nhưng có thể `set` và phản ánh thay đổi backing array. **Sửa:** `List.copyOf` khi cần unmodifiable snapshot.

### Lỗi L — Gọi `List.copyOf` mỗi getter mặc dù field đã snapshot

Không tăng độ an toàn khi phần tử immutable; có thể thêm overhead/khó hiểu. **Sửa:** copy tại constructor/boundary.

### Lỗi M — Trông đợi `List.copyOf` thread-safe khi source đang bị mutate

Không có atomic snapshot guarantee của mutable source thiếu đồng bộ. **Sửa:** dùng lock/safe snapshots đúng ngữ nghĩa.

### Lỗi N — Khóa monitor trên returned List

List factory là value-based; identity-sensitive operations không đáng tin. **Sửa:** lock riêng/concurrency primitives.

### Lỗi O — Đếm allocations bằng identity của lists

Factory có thể reuse result. **Sửa:** profiling và benchmark thay vì `==`.

### Lỗi P — Dùng `Stream.toList` nhưng tưởng nó có cùng null policy với `List.copyOf`

`Stream.toList` không có cấm null như copyOf; kiểm yêu cầu dữ liệu. **Sửa:** dùng `toUnmodifiableList` hoặc `copyOf` khi muốn null-rejecting.

### Lỗi Q — Trả List mutable cho JSON API rồi nghĩ frontend không thể sửa

“Client sẽ không sửa” không phải rào an toàn nội bộ; business code phía Java vẫn có thể mutate. **Sửa:** bảo vệ object trước serialization và giữ authorization đúng.

### Lỗi R — Dựa vào thứ tự của `HashSet` làm thứ tự hiển thị

Không ổn định. **Sửa:** chọn ordered collection/sort trước copy.

### Lỗi S — Viết Javadoc “deeply immutable” khi phần tử mutable

Sai hợp đồng. **Sửa:** dùng câu chữ chính xác hoặc copy phần tử.

### Lỗi T — Đổi mọi collection sang copyOf không xét nhu cầu live view

Có use case view cập nhật theo source. **Sửa:** chọn đúng semantics; `Collections.unmodifiableList` vẫn là API hiện hành hợp lệ cho live view.

## 27. Checklist triển khai trước khi công bố API

1. Danh sách đầu vào thuộc quyền sở hữu của ai?
2. Caller có còn giữ reference và có thể mutate nguồn sau constructor không?
3. Constructor đã gọi `List.copyOf` đúng một điểm boundary chưa?
4. Field có `private final List<T>` không?
5. Getter có trả unmodifiable List không?
6. Có ai tiếp cận mutable backing list qua phương thức khác không?
7. Element type có **thực sự immutable** không?
8. Nếu là record, components có mutable references/mảng không?
9. Nếu elements là entities, đã tạo immutable projections/DTO chưa?
10. Có nested collections cần copy từng tầng không?
11. Null collection policy đã được document chưa?
12. Null element policy có phù hợp `List.copyOf` không?
13. Source collection có thứ tự iterator đã định nghĩa rõ không?
14. Có cần duplicates hay uniqueness trong nghiệp vụ không?
15. Có business rules về item count/quantity/order không?
16. Khi cập nhật, object tạo phiên bản mới hay cho phép mutate qua command?
17. Nếu object mutable, getter có tạo snapshot dưới cơ chế đồng bộ phù hợp không?
18. Có copy list từ source đang bị thread khác sửa không?
19. Getter có lặp lại copy không cần thiết không?
20. Có dựa vào identity/implementation class của list không?
21. Có test `add`, `set`, `remove` và `clear` bị từ chối không?
22. Có test source mutation **sau** constructor không?
23. Có test mutable elements và nested lists không?
24. Có test duplicates/order/null/empty không?
25. Có nêu hợp đồng list unmodifiable trong Javadoc không?
26. Có đo overhead nếu list rất lớn/hot path không?
27. Có kiểm JDK target và API version không?
28. Có tránh API preview/legacy khi mục tiêu là Java hiện đại không?

## 28. Bài tập thực hành

**Câu 1.** `List.copyOf` có từ Java mấy?

**Câu 2.** API nhận `Collection` hay bắt buộc `List`?

**Câu 3.** Source chứa `["A","B","A"]` thì result có mấy phần tử?

**Câu 4.** Nếu caller `source.add("X")` sau constructor, snapshot thay đổi không?

**Câu 5.** Nếu caller `snapshot.items().set(0, item)` thì chuyện gì xảy ra?

**Câu 6.** Vì sao `Collections.unmodifiableList(source)` không đủ để tách snapshot khỏi source mutable?

**Câu 7.** Một `List<MutableNote>` tạo bằng List.copyOf đã trở thành deeply immutable chưa?

**Câu 8.** Muốn trả bất biến về nội dung từ mutable entity, nên làm gì?

**Câu 9.** Nested list chỉ copy outer có giữ inner cố định không?

**Câu 10.** Có thể truyền collection chứa null vào List.copyOf không?

**Câu 11.** Có thể truyền collection rỗng vào List.copyOf không?

**Câu 12.** `List.copyOf(new HashSet<>(...))` tự sort theo chữ cái không?

**Câu 13.** `List.copyOf(existingList)` và `List.of(existingList)` có chắc tương đương không?

**Câu 14.** Vì sao getter của immutable snapshot không cần List.copyOf lần nữa?

**Câu 15.** Khi input đã là unmodifiable list, List.copyOf có chắc luôn tạo reference mới không?

**Câu 16.** `record OrderResponse(List<Item> items)` có tự defensive copy list không?

**Câu 17.** Vì sao `String` + `int` trong Item record giúp design an toàn hơn?

**Câu 18.** Có an toàn không nếu thread A copyOf ArrayList trong khi thread B sửa nó không lock?

**Câu 19.** Có nên `synchronized(snapshot.items())` không?

**Câu 20.** `List.copyOf` có phải deep copy cho mọi object graph không?

**Câu 21.** Vì sao `Stream.toList` khác `List.copyOf` về null policy?

**Câu 22.** `Collectors.toUnmodifiableList` có từ Java mấy?

**Câu 23.** Khi cần list mutable làm workspace, chọn gì?

**Câu 24.** Nếu domain muốn live read-only view, List.copyOf có phù hợp không?

**Câu 25.** Demo in `snapshotAfterEdit=A,B,A` nhưng `sourceAfterEdit=Z,B,A,C` nói lên điều gì?

**Câu 26.** Vì sao phải kiểm cả add, set, remove, clear khi test unmodifiable?

**Câu 27.** Lợi ích của `withItem` là gì?

**Câu 28.** Vì sao không thể tuyên bố List.copyOf luôn có chi phí O(1)?

**Đáp án:**

1. **Java 10**, vẫn được hỗ trợ trên Java SE 26.
2. Nhận `Collection<? extends E>`.
3. **3**, duplicates được giữ.
4. Không, snapshot không phản ánh sửa đổi sau khi copy.
5. Ném `UnsupportedOperationException`.
6. Vì view vẫn được backing bởi source, nên source đổi thì view phản ánh.
7. Không. List giữ references của mutable elements.
8. Chuyển sang immutable DTO hoặc defensive copy các elements đúng mức.
9. Không. Inner list vẫn có thể mutable.
10. Không, sẽ NPE.
11. Có, tạo empty unmodifiable list.
12. Không; giữ iteration order, HashSet không có stable order contract.
13. Không. `List.of(existingList)` có thể tạo list một phần tử là chính existingList.
14. Vì field đã là unmodifiable snapshot và elements immutable; copy nữa không thêm rào.
15. Không. Implementation có thể reuse unmodifiable list.
16. Không. Record shallowly immutable; cần canonical constructor.
17. `String` immutable, `int` primitive, nên không có mutable object components.
18. Không có snapshot atomic guarantee; cần đồng bộ.
19. Không nên; returned lists value-based, tránh identity-sensitive operations.
20. Không, copyOf chỉ shallow ở elements.
21. `Stream.toList` không có cấm null như List.copyOf.
22. **Java 10**.
23. `new ArrayList<>(source)`.
24. Không, vì List.copyOf chốt snapshot; dùng unmodifiable view nếu hợp đồng cần live changes.
25. Source mutable đã bị sửa nhưng snapshot độc lập về list structure.
26. Để phân biệt unmodifiable list với fixed-size list, hoặc view/modifier còn lọt.
27. Trả object mới, giữ old snapshot và business validation.
28. Vì source mutable thường phải duyệt/copy elements; optimization khi input immutable không là cam kết identity/cost.

## 29. Tổng kết

- **`List.copyOf` từ Java 10** tạo một unmodifiable list theo iteration order, giữ duplicates và từ chối null source/elements.
- Snapshot trả về không phản ánh thay đổi của source collection sau khi copy.
- Muốn một đối tượng trả danh sách an toàn, nên **copy ở constructor/boundary**, giữ `private final List<T>` và trả field qua getter.
- **Unmodifiable structure không có nghĩa immutable elements**. Mutable elements/nested collections vẫn có thể thay đổi; dùng immutable DTO hoặc defensive copying theo từng tầng.
- `Collections.unmodifiableList` là **view**, không phải snapshot từ mutable source.
- Không cần List.copyOf lặp lại ở mỗi getter nếu field đã có snapshot và elements immutable.
- `List.of`, `Stream.toList` và `Collectors.toUnmodifiableList` có use cases/versions/null policies khác; chọn theo contract.
- Với concurrency, phải bảo vệ source khi copy và publish snapshot đúng cách.
- Kết quả List.copyOf có **value-based identity**; không dựa vào `==`, locks hay implementation class.
- Cách cập nhật immutable object là **tạo phiên bản mới** hoặc dùng một mutable aggregate với controlled business methods.
- Demo Java 17+ được biên dịch, chạy và xác minh stdout cho input aliasing, unmodifiable operations, shallow elements, nested lists, null, ordering, duplicates và versioning.

## 30. Tài liệu chính thức còn áp dụng

1. [Oracle Java SE 26 — List.copyOf](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): định nghĩa, null rejection, iteration order, không phản ánh sửa source về sau, behavior khi source unmodifiable; `Since: 10`.
2. [Oracle Java SE 26 — Unmodifiable Lists](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html#unmodifiable-lists): unmodifiable, null policy, value-based instances, element mutability caveat.
3. [Oracle Java SE 26 — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/26/core/creating-immutable-lists-sets-and-maps.html): sự khác nhau giữa mutable collection, copyOf và unmodifiable views.
4. [Oracle Java SE 26 — Collections.unmodifiableList](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collections.html#unmodifiableList(java.util.List)): unmodifiable view phản ánh thay đổi backing list.
5. [Oracle Java SE 26 — Collection](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Collection.html): Collections Framework contract và nguồn cho copyOf.
6. [Oracle Java SE 26 — Record](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Record.html): record **shallowly immutable**, canonical constructor dùng validation/defensive copy.
7. [Oracle Java SE 26 — Stream.toList](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Stream.html#toList()): unmodifiable kết quả, encounter order, `Since: 16`.
8. [Oracle Java SE 26 — Collectors.toUnmodifiableList](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableList()): unmodifiable, no null, `Since: 10`.
9. [Oracle Java SE 26 — ArrayList](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/ArrayList.html): modifiable array-backed List dùng cho mutable workspace.
10. [Java SE 26 — Collections Framework Overview](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/doc-files/coll-overview.html): phân biệt unmodifiable, immutable và fixed-size collections.
