# Loại bỏ các phần tử bằng nhau theo `equals` với `Set.copyOf` (Java 10+)

## 1. Mục tiêu và quy tắc nền tảng

`Set.copyOf(Collection<? extends E> coll)` là factory method được bổ sung từ **Java 10** để tạo một `Set<E>` **không cho sửa** từ các phần tử của một `Collection`. Vì `Set` biểu diễn một tập hợp các phần tử **không trùng theo quy tắc bằng nhau**, nếu đầu vào chứa nhiều phần tử được coi là bằng nhau, tập kết quả chỉ giữ **một phần tử đại diện** cho mỗi nhóm tương đương.

```java
var source = java.util.List.of("An", "Binh", "An", "Chi", "Binh");
var unique = java.util.Set.copyOf(source);

System.out.println(unique.size());        // 3
System.out.println(unique.contains("An")); // true
```

Không được suy ra rằng thứ tự duyệt là `An, Binh, Chi`. `Set.copyOf` **không cam kết thứ tự duyệt**. Nếu cần trình bày kết quả dễ kiểm tra, hãy sắp xếp khi hiển thị hoặc kiểm tra bằng `contains`/`size`.

**Quy tắc rất quan trọng:** Java API quy định nếu input có phần tử trùng, `Set.copyOf` giữ lại **một phần tử bất kỳ** trong nhóm trùng. Nó **không cam kết phần tử xuất hiện đầu tiên hay cuối cùng** được giữ. Điều này đặc biệt quan trọng khi hai object khác nhau nhưng `equals` trả `true`.

Sau bài học, bạn sẽ biết:

- Xác định “trùng” bằng `equals` và vai trò của `hashCode`.
- Giải thích số phần tử sau khi chuyển `List` hoặc `Collection` sang `Set.copyOf`.
- Phân biệt `Set.copyOf` và `Set.of` khi gặp trùng.
- Tránh giả định về phần tử đại diện và thứ tự duyệt.
- Hiểu ảnh hưởng của kiểu phần tử, `null`, unmodifiable set, shallow copy và object mutable.
- Chọn cách loại trùng ổn định khi nghiệp vụ yêu cầu “giữ bản ghi đầu tiên”, “giữ mới nhất” hoặc “so sánh không phân biệt hoa thường”.
- Viết test không phụ thuộc chi tiết triển khai không được API cam kết.

Tất cả quy tắc chính được trình bày dưới đây vẫn còn áp dụng trong Java hiện đại; ví dụ chạy độc lập dùng Java 17+.

## 2. `Set.copyOf` làm gì khi đầu vào chứa phần tử trùng?

Chữ ký API:

```java
static <E> Set<E> copyOf(Collection<? extends E> coll)
```

Giả sử nguồn là một `List`:

```java
var letters = java.util.List.of("A", "B", "A", "C", "B");
var set = java.util.Set.copyOf(letters);
```

Ở đây có **5 vị trí trong danh sách**, nhưng chỉ **3 giá trị phân biệt** theo `String.equals`: `"A"`, `"B"` và `"C"`. Do đó:

```java
System.out.println(set.size() == 3);   // true
System.out.println(set.contains("A")); // true
System.out.println(set.contains("B")); // true
System.out.println(set.contains("C")); // true
```

`Set` kết quả chứa mỗi giá trị phân biệt một lần. Tuy nhiên, **đừng in thẳng `set` rồi so sánh với một chuỗi có thứ tự cố định**; thứ tự duyệt của các unmodifiable set từ factory không được chỉ định.

### Điều gì được giữ và điều gì bị loại?

Về mặt logic, với input:

```text
A, B, A, C, B
│  │  │  │  │
│  │  └──┘  └─ đại diện của nhóm B (đã có một B)
│  └────────── B
└───────────── A

Các lớp tương đương theo equals: {A}, {B}, {C}
Số phần tử trong tập kết quả: 3
```

Sơ đồ thể hiện **các nhóm bằng nhau**, không mô tả thuật toán nội bộ hoặc cam kết vị trí nào sẽ được giữ.

`Set.copyOf` không thay `equals` của phần tử, không tự chuẩn hóa văn bản, không tự sắp xếp và không tạo một tiêu chí so sánh mới.

## 3. `equals`, `==` và `hashCode`: “bằng nhau” có nghĩa gì?

### 3.1. `==` so sánh cùng reference; `equals` so sánh theo hợp đồng của lớp

Với các đối tượng tham chiếu:

- `a == b` trả lời liệu hai tham chiếu có trỏ tới **cùng một object** hay không.
- `a.equals(b)` trả lời liệu hai đối tượng có được lớp của chúng định nghĩa là **bằng nhau về mặt logic** hay không.

Ví dụ dùng `String`:

```java
var a = new String("Java");
var b = new String("Java");

System.out.println(a == b);      // false: hai object khác nhau
System.out.println(a.equals(b)); // true: nội dung bằng nhau
System.out.println(java.util.Set.copyOf(java.util.List.of(a, b)).size()); // 1
```

Đừng dùng `==` để kết luận có trùng trong một set chứa các value objects, trừ khi bản chất của lớp đúng là so sánh identity (như mặc định của `Object` khi không override `equals`).

### 3.2. `hashCode` phải nhất quán với `equals`

Java yêu cầu: nếu `a.equals(b) == true`, thì `a.hashCode() == b.hashCode()`. Chiều ngược lại không bắt buộc: hai object có cùng hash code vẫn có thể không bằng nhau.

Nhiều `Set` dùng bảng băm bên trong. Để việc loại trùng và tra cứu diễn ra đúng theo hợp đồng của collection, class phần tử phải triển khai `equals` và `hashCode` nhất quán khi muốn có so sánh giá trị tùy chỉnh.

```java
record ProductKey(String sku) { }

var a = new ProductKey("SKU-01");
var b = new ProductKey("SKU-01");

System.out.println(a.equals(b)); // true
System.out.println(java.util.Set.copyOf(java.util.List.of(a, b)).size()); // 1
```

`record` tạo `equals`/`hashCode` dựa trên các component, trừ khi bạn định nghĩa lại; trong ví dụ này, `sku` là chuỗi nên sự bằng nhau phụ thuộc vào `String.equals`. Record có từ Java 16 và được dùng ở đây trong ví dụ Java 17+.

### 3.3. Nếu không override `equals`

Một class thông thường chỉ kế thừa `Object.equals` thì về cơ bản bằng nhau theo **identity**:

```java
class Box {
    final String label;
    Box(String label) { this.label = label; }
}

var first = new Box("same");
var second = new Box("same");
var boxes = java.util.Set.copyOf(java.util.List.of(first, second));

System.out.println(boxes.size()); // 2
```

Hai `Box` có cùng `label` nhưng vẫn là hai object khác nhau. `Set.copyOf` không tự đi sâu vào field `label` để đoán ý định loại trùng.

**Đánh giá đúng yêu cầu nghiệp vụ trước khi dùng API:** muốn loại trùng theo mã định danh, email hay toàn bộ field? Tiêu chí ấy phải được mô hình hóa bởi `equals/hashCode` hoặc một bước chuẩn hóa/chọn khóa rõ ràng trước khi sao chép.

## 4. Một phần tử “bất kỳ” được giữ: không mặc định first-wins hoặc last-wins

Hãy tưởng tượng hai bản ghi khác nhau:

```java
var first = new Item("ID-01", "nguồn A");
var second = new Item("ID-01", "nguồn B");
```

Giả sử `Item.equals` và `hashCode` **chỉ dựa trên `id`**, thì hai object bằng nhau dù thông tin `source` khác nhau. Khi gọi:

```java
var result = java.util.Set.copyOf(java.util.List.of(first, second));
```

`result.size()` là 1. Nhưng API **không bảo đảm** phần tử còn lại là `first` hay `second`.

Điều có thể khẳng định:

- Hai object được coi là trùng theo `equals`.
- Tập kết quả có một đại diện của lớp tương đương đó.
- Đại diện có thể là một trong các object trùng đầu vào.
- Bạn **không được** dựa vào việc bản ghi nguồn A hay nguồn B sẽ thắng.

Điều **không được cam kết**:

- “Giữ phần tử đầu tiên trong danh sách”.
- “Giữ phần tử cuối cùng trong danh sách”.
- “Giữ phần tử mới nhất theo thời gian”.
- “Luôn giữ cùng object khi đổi JVM hoặc bản Java”.
- “Duyệt `Set` theo thứ tự `List` nguồn”.

Hành vi thực tế trong một bản JDK cụ thể không thay thế được hợp đồng API. Khi hai object bằng nhau theo key nhưng khác dữ liệu phụ, **chọn đại diện phải là một bước nghiệp vụ riêng** nếu dữ liệu phụ quan trọng.

## 5. Ví dụ class tùy chỉnh với `equals` chỉ so sánh khóa

Mô hình một mặt hàng có mã `id` và nhãn `label`:

```java
static final class Item {
    private final String id;
    private final String label;

    Item(String id, String label) {
        this.id = java.util.Objects.requireNonNull(id);
        this.label = java.util.Objects.requireNonNull(label);
    }

    String id() { return id; }
    String label() { return label; }

    @Override
    public boolean equals(Object other) {
        return other instanceof Item item && id.equals(item.id);
    }

    @Override
    public int hashCode() {
        return id.hashCode();
    }
}
```

Đây là **class lồng trong một class Java** (chương trình hoàn chỉnh ở mục 12). Quy tắc:

- `id` giống nhau ⇒ `equals` trả `true`.
- `label` có thể khác nhưng **không** tham gia so sánh bằng nhau.
- `hashCode` dùng đúng `id` để nhất quán với `equals`.

Thử:

```java
var a = new Item("P-1", "phiên bản A");
var b = new Item("P-1", "phiên bản B");
var c = new Item("P-2", "phiên bản C");

var set = java.util.Set.copyOf(java.util.List.of(a, b, c));
System.out.println(a.equals(b)); // true
System.out.println(set.size());   // 2
```

Không nên khẳng định tập sẽ in một chuỗi cụ thể vì `Set.copyOf` không cam kết thứ tự và không chọn đại diện theo quy tắc “đầu tiên”.

**Kiểm tra đại diện một cách hợp lệ:** nếu lấy phần tử có `id` bằng `"P-1"`, chỉ nên khẳng định nó là một trong `a` hoặc `b`, không khẳng định chắc chắn cái nào.

## 6. So sánh `Set.copyOf` với `Set.of` và `Collectors.toUnmodifiableSet`

Ba API đều có thể tạo unmodifiable set, nhưng **đầu vào trùng** được xử lý khác nhau.

| API | Dữ liệu đầu vào | Nếu có phần tử trùng theo `equals` | Có sửa tập được không? |
| --- | --- | --- | --- |
| `Set.of("A", "B")` | Các đối số cụ thể | Nếu truyền phần tử trùng, ném `IllegalArgumentException` | Không |
| `Set.copyOf(collection)` | `Collection<? extends E>` | **Loại trùng; giữ một đại diện bất kỳ** | Không |
| `stream.collect(Collectors.toUnmodifiableSet())` | Các phần tử do stream phát ra | Tạo set không trùng; thứ tự/đại diện không được cam kết khi nhiều phần tử bằng nhau | Không |
| `new HashSet<>(collection)` | `Collection<? extends E>` | Tập có một phần tử cho mỗi lớp bằng nhau theo quy tắc set | **Có**, đây là set mutable |
| `Collections.unmodifiableSet(backing)` | Một `Set` có sẵn | Không tự đọc lại danh sách trùng; view của set nguồn | Không qua view, nhưng backing set có thể bị sửa qua alias |

### 6.1. `Set.of` báo lỗi nếu trùng

```java
try {
    java.util.Set.of("A", "A");
} catch (IllegalArgumentException expected) {
    System.out.println("duplicatesRejected=true");
}
```

`Set.of` hữu ích khi tập giá trị được viết cố định và **trùng là sai sót cần phát hiện**. Nó khác `Set.copyOf` vốn có chủ đích chấp nhận collection đầu vào chứa trùng.

### 6.2. `Set.copyOf` loại trùng

```java
var input = java.util.List.of("A", "A", "B");
var unique = java.util.Set.copyOf(input);
System.out.println(unique.size()); // 2
```

**Không ném `IllegalArgumentException` chỉ vì trùng.** Lưu ý API vẫn có thể ném ngoại lệ khác khi đầu vào vi phạm điều kiện, ví dụ `null`.

### 6.3. `Collectors.toUnmodifiableSet` có từ Java 10

```java
var unique = java.util.stream.Stream.of("A", "B", "A")
        .collect(java.util.stream.Collectors.toUnmodifiableSet());
System.out.println(unique.size()); // 2
```

Collector không yêu cầu tạo `List` trung gian. Nó cũng không phải công cụ chọn “phần tử đầu tiên theo thứ tự stream” khi các object bằng nhau nhưng có field phụ khác nhau.

### 6.4. `HashSet` để sửa tiếp

```java
var editable = new java.util.HashSet<>(java.util.List.of("A", "A", "B"));
editable.add("C");
System.out.println(editable.size()); // 3
```

Nếu yêu cầu là **tập có thể thay đổi**, `Set.copyOf` không phải lựa chọn phù hợp vì kết quả không hỗ trợ thêm/xóa.

## 7. `null`: không phải phần tử trùng hợp lệ để loại bỏ

`Set.copyOf` yêu cầu:

- Tham số `coll` không được là `null`.
- Các phần tử trong collection nguồn **không được là `null`**.

Nếu vi phạm, Java ném `NullPointerException`.

```java
var source = new java.util.ArrayList<String>();
source.add("A");
source.add(null);

// java.util.Set.copyOf(source); // Ném NullPointerException
```

Không nên coi nhiều `null` là “các phần tử trùng” rồi chờ `Set.copyOf` giữ một `null`. Factory **không chấp nhận bất kỳ `null` nào**.

Nếu ứng dụng có quy tắc “bỏ `null` rồi mới loại trùng”, viết rõ điều đó:

```java
var cleaned = source.stream()
        .filter(java.util.Objects::nonNull)
        .collect(java.util.stream.Collectors.toList());

var unique = java.util.Set.copyOf(cleaned);
```

Đây là **đoạn minh họa trong một phương thức** với `source` như trên. Việc lọc `null` là một **quyết định nghiệp vụ**, không phải hành vi mặc định của `Set.copyOf`. Ở Java 17+, cũng có thể dùng `source.stream().filter(Objects::nonNull).toList()` làm collection trung gian không sửa được.

Không dùng `Set.copyOf(null)`; compiler có thể gặp bài toán chọn overload nếu có API khác cùng tên trong ngữ cảnh, nhưng trong lời gọi static factory này, tham số `null` trực tiếp được chấp nhận về mặt kiểu và ném `NullPointerException` khi chạy.

## 8. `String.equals` phân biệt hoa thường và khoảng trắng

`Set.copyOf` không tự làm sạch dữ liệu trước khi so sánh. Ví dụ:

```java
var input = java.util.List.of("Java", "java", " Java ");
var distinct = java.util.Set.copyOf(input);

System.out.println(distinct.size()); // 3
```

Vì `String.equals` phân biệt chữ hoa/chữ thường và khoảng trắng, ba chuỗi trên **không bằng nhau**.

Nếu nghiệp vụ muốn coi chúng là một mã/từ khóa giống nhau, chuẩn hóa trước:

```java
var normalized = input.stream()
        .map(String::strip)
        .map(s -> s.toLowerCase(java.util.Locale.ROOT))
        .toList();

var distinctNormalized = java.util.Set.copyOf(normalized);
System.out.println(distinctNormalized.size()); // 1
```

Dùng `Locale.ROOT` giúp biểu diễn ý định xử lý không phụ thuộc locale mặc định khi chuẩn hóa khóa kỹ thuật. Nếu dữ liệu là tên riêng hoặc ngôn ngữ tự nhiên, quy tắc case folding/chuẩn hóa Unicode có thể phức tạp hơn; không áp dụng `toLowerCase` bừa bãi cho mọi loại dữ liệu.

**Quan trọng:** chuẩn hóa thành `"java"` đã thay đổi dữ liệu đầu vào dùng trong output. Nếu cần giữ chuỗi gốc và đồng thời loại trùng theo khóa chuẩn hóa, bạn phải tạo một cấu trúc ánh xạ khóa → đại diện và **định nghĩa chính sách chọn đại diện**.

## 9. Khi `compareTo` hoặc comparator khác `equals`

Đừng nhầm tiêu chí bằng nhau của `Set.copyOf` với tiêu chí xếp hạng của `TreeSet`.

```java
var a = new java.math.BigDecimal("1.0");
var b = new java.math.BigDecimal("1.00");

System.out.println(a.equals(b));       // false: scale khác nhau
System.out.println(a.compareTo(b) == 0); // true: giá trị số bằng nhau
System.out.println(java.util.Set.copyOf(java.util.List.of(a, b)).size()); // 2
```

`BigDecimal.equals` phân biệt cả giá trị **và scale**; `compareTo` có thể xem hai số bằng nhau về thứ tự. `Set.copyOf` sử dụng quan hệ bằng nhau của set dựa trên `equals` chứ không áp dụng `compareTo` để gộp các phần tử.

Ngược lại, một `TreeSet<BigDecimal>` dùng thứ tự tự nhiên có thể coi `a` và `b` trùng theo `compareTo`, dẫn đến chỉ một phần tử được giữ trong chính `TreeSet`:

```java
var sorted = new java.util.TreeSet<java.math.BigDecimal>();
sorted.add(a);
sorted.add(b);
System.out.println(sorted.size()); // 1
```

Khi gọi `Set.copyOf(sorted)`, đầu vào đã chỉ còn một phần tử. Đó là kết quả của **bước thêm vào TreeSet**, không phải `Set.copyOf` tự đổi quy tắc trùng sang `compareTo`.

**Bài học:** xác định rõ bạn muốn trùng theo `equals`, comparator, khóa chuẩn hóa hay quy tắc nghiệp vụ khác.

## 10. Snapshot cấu trúc, không phải deep copy

`Set.copyOf` tạo một **unmodifiable set** chứa các phần tử của collection tại thời điểm gọi. Khi **collection nguồn** được thay đổi sau đó, tập trả về **không phản ánh các thay đổi thêm/xóa ấy**.

```java
var source = new java.util.ArrayList<String>(
        java.util.List.of("A", "A", "B"));
var frozenSet = java.util.Set.copyOf(source);

source.add("C");
source.remove("A");

System.out.println(source.size());    // 3: [A, B, C]
System.out.println(frozenSet.size()); // 2: vẫn chứa A, B
```

Không có nghĩa mỗi **đối tượng phần tử** đều được clone. `Set.copyOf` là một thao tác sao chép **tập thành viên/reference**, không phải deep copy của object graph.

### Phần tử mutable vẫn có thể thay đổi

```java
var builder = new StringBuilder("A");
var set = java.util.Set.copyOf(java.util.List.of(builder));

builder.append("B");
System.out.println(set.iterator().next().toString()); // AB
```

Kết quả list/set vẫn có một reference đến cùng `StringBuilder`; trạng thái của đối tượng đã đổi. Với phần tử mutable mà `equals/hashCode` phụ thuộc vào field thay đổi, set có thể hoạt động không nhất quán: không nên đổi các field dùng để xác định bằng nhau **sau khi** đưa phần tử vào set.

**Đặc biệt:** nếu class chứa mã định danh `id` và `equals/hashCode` chỉ dựa trên `id`, hãy giữ `id` bất biến. Thay đổi field hiển thị không tham gia `equals/hashCode` vẫn có thể được quan sát qua set nhưng không tạo ra “một phần tử mới”.

### `Set.copyOf` có thể tái sử dụng input

Nếu nguồn vốn đã là một unmodifiable `Set`, `Set.copyOf` **có thể trả lại cùng instance** thay vì tạo object mới. Điều này là chi tiết được cho phép, không phải thứ cần kiểm tra bằng `==`. Java coi các collection factory không sửa được này là *value-based*; đừng dùng identity của kết quả hoặc synchronized trên kết quả làm một hợp đồng chương trình.

## 11. Kết quả không có thứ tự duyệt được cam kết

`Set.copyOf` giữ **tính duy nhất**, không giữ hợp đồng **thứ tự của `List`**.

```java
var copy = java.util.Set.copyOf(
        java.util.List.of("B", "A", "C", "A"));
```

Không nên test:

```java
// Không nên:
assert "[A, B, C]".equals(copy.toString());
```

Vì có thể có thứ tự duyệt khác mà vẫn đúng hợp đồng `Set.copyOf`.

Test đúng theo tính chất nghiệp vụ:

```java
assert copy.size() == 3;
assert copy.containsAll(java.util.Set.of("A", "B", "C"));
```

Nếu cần in có thứ tự cố định:

```java
System.out.println(new java.util.TreeSet<>(copy)); // [A, B, C]
```

`TreeSet` ở đây chỉ **sắp xếp để trình bày** vì `String` có thứ tự tự nhiên; không làm thay đổi nội dung hoặc thứ tự duyệt cam kết của chính `copy`.

Với phần tử tùy chỉnh, cần một comparator phù hợp nếu muốn sắp xếp; đừng vô tình làm mất thêm các phần tử khi comparator coi hai object khác nhau theo `equals` là tương đương.

## 12. Chương trình Java 17+ độc lập

Tạo tệp **`SetCopyOfEqualityDemo.java`**:

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.Objects;
import java.util.Set;
import java.util.TreeSet;

public class SetCopyOfEqualityDemo {
    static final class Item {
        private final String id;
        private final String label;

        Item(String id, String label) {
            this.id = Objects.requireNonNull(id);
            this.label = Objects.requireNonNull(label);
        }

        String id() {
            return id;
        }

        String label() {
            return label;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Item item && id.equals(item.id);
        }

        @Override
        public int hashCode() {
            return id.hashCode();
        }
    }

    public static void main(String[] args) {
        var input = List.of("red", "blue", "red", "green", "blue");
        var distinct = Set.copyOf(input);
        System.out.println("inputSize=" + input.size());
        System.out.println("distinctSize=" + distinct.size());
        System.out.println("containsRed=" + distinct.contains("red"));
        System.out.println("sorted=" + new TreeSet<>(distinct));

        var source = new ArrayList<String>(
                List.of("A", "A", "B"));
        var snapshot = Set.copyOf(source);
        source.add("C");
        System.out.println("sourceSize=" + source.size());
        System.out.println("snapshotSize=" + snapshot.size());

        var first = new Item("K-1", "origin-A");
        var second = new Item("K-1", "origin-B");
        var third = new Item("K-2", "origin-C");
        var items = Set.copyOf(List.of(first, second, third));
        var representative = items.stream()
                .filter(item -> item.id().equals("K-1"))
                .findFirst()
                .orElseThrow();

        System.out.println("equalItems=" + first.equals(second));
        System.out.println("itemsSize=" + items.size());
        System.out.println("representativeFromInput="
                + (representative == first || representative == second));
        System.out.println("representativeId=" + representative.id());
        System.out.println("containsEquivalent="
                + items.contains(new Item("K-1", "other label")));

        var differentCase = Set.copyOf(List.of("Java", "java", " Java "));
        var normalized = Set.copyOf(
                List.of("Java", "java", " Java ").stream()
                        .map(String::strip)
                        .map(s -> s.toLowerCase(Locale.ROOT))
                        .toList());
        System.out.println("differentCaseSize=" + differentCase.size());
        System.out.println("normalizedSize=" + normalized.size());

        var decimalA = new BigDecimal("1.0");
        var decimalB = new BigDecimal("1.00");
        System.out.println("bigDecimalEquals=" + decimalA.equals(decimalB));
        System.out.println("bigDecimalCompareEqual="
                + (decimalA.compareTo(decimalB) == 0));
        System.out.println("bigDecimalSetSize="
                + Set.copyOf(List.of(decimalA, decimalB)).size());

        try {
            Set.of("x", "x");
        } catch (IllegalArgumentException expected) {
            System.out.println("setOfRejectsDuplicates=true");
        }

        try {
            Set.copyOf(java.util.Arrays.asList("x", null));
        } catch (NullPointerException expected) {
            System.out.println("copyOfRejectsNull=true");
        }

        try {
            distinct.add("yellow");
        } catch (UnsupportedOperationException expected) {
            System.out.println("unmodifiable=true");
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac --release 17 -encoding UTF-8 SetCopyOfEqualityDemo.java
java SetCopyOfEqualityDemo
```

**Stdout chính xác:**

```text
inputSize=5
distinctSize=3
containsRed=true
sorted=[blue, green, red]
sourceSize=4
snapshotSize=2
equalItems=true
itemsSize=2
representativeFromInput=true
representativeId=K-1
containsEquivalent=true
differentCaseSize=3
normalizedSize=1
bigDecimalEquals=false
bigDecimalCompareEqual=true
bigDecimalSetSize=2
setOfRejectsDuplicates=true
copyOfRejectsNull=true
unmodifiable=true
```

### Vì sao stdout đáng tin cậy?

1. `distinct.size()` và `contains` đo đúng tính duy nhất mà không phụ thuộc thứ tự set.
2. `new TreeSet<>(distinct)` tạo thứ tự tự nhiên của `String` **chỉ cho mục đích in**.
3. `source` thay đổi số phần tử sau khi copy, còn `snapshot` vẫn giữ các thành viên tại thời điểm copy.
4. Hai `Item` trùng `id` nên chỉ một đại diện `K-1` tồn tại. Test chỉ kiểm `representative` là **một trong hai object gốc**, không khẳng định phải là `first` hoặc `second`.
5. `Item.equals/hashCode` nhất quán theo `id`, vì vậy `items.contains(new Item("K-1", "..."))` hợp lệ.
6. `String.equals` phân biệt chữ hoa thường và khoảng trắng; sau chuẩn hóa, ba giá trị trở thành một.
7. `BigDecimal.equals` khác `compareTo` về scale, minh họa sự khác biệt giữa bằng nhau và so sánh thứ tự.
8. Các khối `catch` xác nhận ngoại lệ của `Set.of` (đối số trùng), `Set.copyOf` (`null`) và việc cấm sửa set kết quả.

Chương trình **không in trực tiếp đại diện có nhãn khác nhau**, cũng không dựa vào thứ tự duyệt không được cam kết của `Set.copyOf`.

## 13. Muốn chọn phần tử đại diện theo chính sách rõ ràng thì làm sao?

`Set.copyOf` phù hợp khi **mọi phần tử bằng nhau có thể thay thế cho nhau** theo ý nghĩa nghiệp vụ, hoặc bạn chỉ quan tâm tới số lượng/nhóm giá trị duy nhất. Nếu bản ghi cùng khóa nhưng khác dữ liệu phụ, nên **xác định đại diện trước**, rồi mới tạo tập không sửa được.

### 13.1. Giữ lần xuất hiện đầu tiên theo khóa

```java
var byId = new java.util.LinkedHashMap<String, Item>();

for (var item : inputItems) {
    byId.putIfAbsent(item.id(), item);
}

var firstById = java.util.Set.copyOf(byId.values());
```

Đây là **đoạn minh họa nằm trong phương thức**, giả sử `inputItems` là `List<Item>` và class `Item` đã định nghĩa. `putIfAbsent` không thay value đang có với cùng khóa, nên map giữ **bản ghi đầu tiên cho mỗi id** nếu các value không phải `null`. `LinkedHashMap` có thể hỗ trợ thứ tự chèn **khi duyệt map**, nhưng khi tiếp tục chuyển sang `Set.copyOf`, **thứ tự của Set kết quả không được bảo đảm**.

**Một chi tiết quan trọng:** nếu `Item.equals` phân biệt các field khác với `id`, `Set.copyOf(byId.values())` vẫn có thể gộp thêm những object `equals` bằng nhau ngoài các nhóm khóa. Hãy bảo đảm quy tắc `equals` tương thích với ý định hoặc giữ dữ liệu trong map/snapshot có cấu trúc thích hợp.

### 13.2. Giữ lần xuất hiện cuối cùng theo khóa

```java
var byId = new java.util.LinkedHashMap<String, Item>();

for (var item : inputItems) {
    byId.put(item.id(), item);
}

var lastById = java.util.Set.copyOf(byId.values());
```

`put` thay value của key đã có bằng object cuối cùng đã gặp. Thứ tự iteration mặc định của `LinkedHashMap` vẫn là thứ tự khóa được chèn lần đầu nếu không cấu hình access-order; điều đó **không** tạo ra cam kết thứ tự của `lastById`.

### 13.3. Giữ “mới nhất” theo thời gian

Nếu business rule là “chọn record có `updatedAt` lớn nhất”, đừng đồng nhất nó với “phần tử được duyệt sau cùng” hoặc với hành vi đại diện tùy ý của `Set.copyOf`. Hãy dùng một reducer hoặc logic chọn theo `updatedAt`, quy định xử lý khi bằng thời gian, rồi chuyển kết quả đã chọn sang cấu trúc không sửa được nếu cần.

Ví dụ, khi muốn giữ theo `id` và timestamp, một `Map<Id, Entity>` thường là mô hình dữ liệu thích hợp hơn một `Set<Entity>` có `equals` chỉ dựa trên `id`.

## 14. Tình huống dễ lỗi trong dự án thực tế

### Lỗi A: Tưởng `Set.copyOf` luôn giữ phần tử đầu tiên

```java
var first = new Item("42", "old");
var latest = new Item("42", "new");
var set = Set.copyOf(List.of(first, latest));

// Không được giả định phần tử còn lại có label "old" hay "new".
```

**Sửa:** chọn đại diện theo quy tắc rõ (như `putIfAbsent`/`put` hoặc so sánh timestamp) trước khi tạo tập.

### Lỗi B: Tưởng `Set.copyOf` giữ cả thứ tự

```java
var set = Set.copyOf(List.of("B", "A", "C"));
```

**Không** cam kết duyệt theo `B, A, C`. Nếu yêu cầu giữ thứ tự xuất hiện và loại trùng:

```java
var ordered = new java.util.LinkedHashSet<>(List.of("B", "A", "C", "A"));
System.out.println(ordered); // [B, A, C] với thứ tự chèn
```

`LinkedHashSet` là **mutable set**. Nếu cần trả về API không cho sửa qua tham chiếu của caller và giữ thứ tự duyệt, cân nhắc wrapper `Collections.unmodifiableSet(new LinkedHashSet<>(...))` nhưng phải tránh lộ reference tới backing set; lựa chọn thiết kế này khác hợp đồng `Set.copyOf`.

### Lỗi C: Chỉ override `equals`, quên `hashCode`

Nếu hai object bằng nhau theo `equals` nhưng khác `hashCode`, lớp vi phạm hợp đồng Java; các set dựa trên hash có thể loại trùng hoặc tra cứu sai kỳ vọng.

**Sửa:** định nghĩa cả `equals` và `hashCode` trên cùng tập field bất biến.

### Lỗi D: Dùng object có khóa mutable làm phần tử

```java
// Nếu MutableItem.equals/hashCode dựa trên mutableId:
var set = Set.copyOf(items);
// Một nơi khác thay mutableId của item.
```

Không còn an toàn để suy đoán `contains` và hành vi phân biệt phần tử như lúc tạo tập. **Sửa:** ổn định khóa, dùng object bất biến hoặc snapshot riêng.

### Lỗi E: Bỏ qua `null`

```java
var input = new java.util.ArrayList<String>();
input.add("A");
input.add(null);
// Set.copyOf(input); // Ném NullPointerException
```

**Sửa:** xác định chính sách dữ liệu có `null`, lọc hoặc báo lỗi rõ ràng trước khi gọi.

### Lỗi F: So sánh hai string bằng `==` để dự đoán trùng

```java
var a = new String("A");
var b = new String("A");
System.out.println(a == b);      // false
System.out.println(a.equals(b)); // true
```

`Set.copyOf(List.of(a,b))` vẫn có một phần tử. **Sửa:** nhìn vào `equals`/`hashCode` đúng với kiểu phần tử.

### Lỗi G: Cho rằng trả về unmodifiable set nghĩa là deep immutable

```java
var builder = new StringBuilder("A");
var set = Set.copyOf(List.of(builder));
builder.append("B"); // Cùng object tham chiếu bên trong set đã đổi trạng thái
```

**Sửa:** chuyển phần tử sang dạng bất biến trước khi tạo set nếu cần snapshot giá trị bền vững.

## 15. Checklist review và chiến lược test

Khi thấy `Set.copyOf(collection)` trong code review:

1. **Nguồn là kiểu collection nào?** `List` có thể chứa phần tử trùng; `Set` nguồn vốn đã định nghĩa tính duy nhất theo chính sách của nó.
2. **Tiêu chí trùng là gì?** Kiểm tra `equals` và `hashCode` trên kiểu phần tử, bao gồm `String`, `BigDecimal` hoặc record/class tùy chỉnh.
3. **Các phần tử cùng nhóm có thực sự thay thế cho nhau không?** Nếu khác field phụ quan trọng, phải chọn đại diện trước.
4. **Có cần thứ tự duyệt không?** Nếu có, `Set.copyOf` không cam kết thứ tự; dùng cấu trúc phù hợp.
5. **Có thể có `null` không?** API không chấp nhận `null` ở nguồn hoặc phần tử.
6. **Caller có muốn sửa tập không?** `Set.copyOf` trả unmodifiable set, không phải `HashSet` mutable.
7. **Đã hiểu sự khác biệt với `Set.of` chưa?** `Set.of` từ chối trùng bằng `IllegalArgumentException`; `copyOf` chấp nhận và loại trùng.
8. **Phần tử có mutable state không?** Nếu field tham gia `equals/hashCode` đổi, membership/tra cứu có thể bất ổn.
9. **Có đang test `set.toString()` hoặc thứ tự iterator không?** Đừng làm vậy khi không được hợp đồng cam kết.
10. **Có xử lý đại diện tùy ý bằng mã phía sau không?** Nếu sử dụng `label`, timestamp hoặc giá trị phụ của phần tử còn lại, phải mô hình hóa chính sách đại diện.
11. **Đã kiểm tra kiểu generic chưa?** `var unique = Set.copyOf(List.of("A","B"));` suy luận `Set<String>`. Với nguồn generic thiếu kiểu, phải kiểm tra kiểu suy luận ở initializer.
12. **Đã có kiểm thử biên?** Tập rỗng, một phần tử, nhiều phần tử trùng, hai object `equals` nhưng khác identity/field phụ, `null`, thay đổi nguồn sau copy.

### Test tốt hơn test thứ tự

```java
var actual = Set.copyOf(List.of("A", "B", "A"));

assert actual.size() == 2;
assert actual.contains("A");
assert actual.contains("B");
assert actual.equals(Set.of("A", "B"));
```

Khi test hai instance khác nhau nhưng bằng nhau theo `id`, kiểm tra `actual.size()` và `contains(new Item(id, ...))`; **không assert rằng phần tử đầu tiên được giữ**.

## 16. Bài tập tự kiểm tra

Mỗi câu mô tả một trường hợp độc lập.

**Câu 1.** `Set.copyOf(List.of("A", "B", "A"))` có bao nhiêu phần tử? Có ném `IllegalArgumentException` không?

**Câu 2.** Nếu thay bằng `Set.of("A", "B", "A")`, kết quả gì xảy ra?

**Câu 3.** Hai `new String("Java")` riêng biệt có được coi là trùng trong `Set.copyOf` không? Vì sao?

**Câu 4.** Một class `User` có hai field `id` và `name`, nhưng `equals`/`hashCode` chỉ dựa vào `id`. Hai `User` trùng `id`, khác tên: `Set.copyOf(List.of(user1,user2))` giữ tên nào?

**Câu 5.** `Set.copyOf(List.of("Java","java"))` có bao nhiêu phần tử? Muốn gộp không phân biệt hoa thường cần làm gì?

**Câu 6.** Nếu dùng `BigDecimal("1.0")` và `BigDecimal("1.00")`, tại sao `Set.copyOf` có thể cho 2 phần tử còn `TreeSet` dùng thứ tự tự nhiên lại cho 1?

**Câu 7.** `Set.copyOf` có được phép nhận `List` chứa `null` rồi bỏ `null` không?

**Câu 8.** Khi sửa một `ArrayList` nguồn sau khi `Set.copyOf`, `Set` kết quả có nhận phần tử mới không?

**Câu 9.** Nếu object phần tử thay đổi field tham gia `equals/hashCode` sau khi tạo set, có an toàn không?

**Câu 10.** Tại sao dùng `Set.copyOf` để chọn “bản ghi đầu tiên cho mỗi mã ID” là không đủ?

**Đáp án:**

1. Có **2** phần tử; **không** ném lỗi vì trùng. Tập chứa `A` và `B` không cam kết thứ tự duyệt.
2. `Set.of` ném `IllegalArgumentException` do giá trị trùng.
3. Có, vì `String.equals` so sánh nội dung dù hai object không trùng identity.
4. Không bảo đảm `user1` hay `user2`; đại diện của nhóm trùng là **bất kỳ** theo hợp đồng `copyOf`.
5. Có **2** phần tử; phải chuẩn hóa khóa, ví dụ `strip` và `toLowerCase(Locale.ROOT)` theo quy tắc nghiệp vụ.
6. `BigDecimal.equals` xét cả scale, `compareTo` lại có thể coi bằng nhau về giá trị số. `Set.copyOf` dựa trên `equals`, còn `TreeSet` dựa trên thứ tự/comparator.
7. Không. `Set.copyOf` ném `NullPointerException` khi input chứa `null`.
8. Không; tập chứa thành viên tại thời điểm copy. Nhưng các object phần tử mutable vẫn có thể đổi trạng thái qua alias.
9. Không nên; có thể phá vỡ giả định membership và tra cứu. Giữ field định danh bất biến.
10. Vì `Set.copyOf` không cam kết phần tử đầu tiên được giữ. Cần chọn đại diện tường minh, ví dụ `LinkedHashMap.putIfAbsent`.

## 17. Ghi nhớ và nguồn chính thức

- **`Set.copyOf(Collection)`** tạo unmodifiable set từ collection, được bổ sung từ **Java 10**.
- Nếu có các phần tử **bằng nhau theo `equals`**, chỉ một đại diện được giữ; **đại diện là tùy ý**, không bảo đảm đầu hay cuối.
- **`equals/hashCode` nhất quán** là nền tảng để set xác định phần tử trùng đúng theo hợp đồng.
- **`Set.of` khác `Set.copyOf`:** `of` từ chối phần tử trùng với `IllegalArgumentException`, còn `copyOf` loại trùng.
- **Không `null`, không sửa, không cam kết thứ tự duyệt** là các điều kiện quan trọng.
- `Set.copyOf` bảo vệ tập thành viên khỏi thay đổi cấu trúc của collection nguồn, nhưng **không deep-copy mutable elements**.
- Nếu nghiệp vụ cần “first-wins”, “last-wins” hoặc “mới nhất”, **hãy chọn đại diện trước** bằng chính sách rõ ràng.

Tài liệu tham khảo hiện hành:

1. [Java SE 26 – `java.util.Set.copyOf`, `Set.of` và Unmodifiable Sets](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)): quy định bỏ trùng, chọn phần tử đại diện tùy ý, `null`, thứ tự duyệt và trạng thái không cho sửa.
2. [Dev.java – Collections Factory Methods: Getting an Unmodifiable Copy of a Collection](https://dev.java/learn/api/collections-and-streams/collections-framework/factory-methods/): tài liệu học chính thức của Java về `Set.copyOf` từ Java 10.
3. [Java SE 26 – `Object.equals` và `hashCode`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Object.html): hợp đồng bằng nhau và hash.
4. [Java SE 26 – `BigDecimal.equals` và `compareTo`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/math/BigDecimal.html): trường hợp hai số cùng giá trị nhưng khác scale.
5. [Java SE 26 – `java.util.Set`](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/Set.html): đặc trưng tập hợp và quy tắc duy nhất theo `equals`.
