# Ảnh hưởng khi tập nguồn thay đổi sau `Set.copyOf` (Java 10+)

## 1. Mục tiêu và câu trả lời ngắn gọn

`Set.copyOf(Collection<? extends E>)` được bổ sung trong **Java 10**. Phương thức trả về một `Set` **không cho sửa qua API của nó** (*unmodifiable set*), gồm các phần tử lấy từ collection nguồn tại thời điểm sao chép. Nếu tập nguồn là một `HashSet` có thể thay đổi thông thường, việc thêm hoặc xóa phần tử trong nguồn **sau khi gọi `Set.copyOf` không làm thay đổi thành viên của tập kết quả**.

Tuy nhiên, `Set.copyOf` **không sao chép sâu từng đối tượng phần tử**. Nếu nguồn chứa tham chiếu đến một object mutable, tập kết quả vẫn giữ tham chiếu đến chính object ấy. Vì vậy, sửa trạng thái object có thể được quan sát qua tập kết quả, và đặc biệt nguy hiểm nếu trạng thái bị sửa tham gia vào `equals()` hoặc `hashCode()`.

Bài học phân biệt bốn thao tác thường bị đánh đồng:
1. **Thêm/xóa phần tử ở tập nguồn** sau khi sao chép.
2. **Đổi trạng thái của một object phần tử** đang được cả nguồn và kết quả cùng tham chiếu.
3. **Sửa tập kết quả** thông qua `add`, `remove`, `clear`.
4. **Quan sát `Collections.unmodifiableSet(source)`** — một *view* bọc nguồn, khác với snapshot của `Set.copyOf(source)`.

Các quy tắc và API trình bày vẫn áp dụng trong Java hiện đại. Chương trình thực hành độc lập dùng JDK 17+; không cần tính năng preview.

## 2. `Set.copyOf` chụp những gì?

Giả sử:

~~~java
Set<String> source = new HashSet<>(List.of("A", "B"));
Set<String> copy = Set.copyOf(source);
~~~

Đây là đoạn minh họa bên trong phương thức, với các import `java.util.Set`, `HashSet`, `List`. Trước khi thay đổi nguồn:

- `source` chứa hai phần tử `"A"`, `"B"`.
- `copy` chứa hai phần tử tương ứng.
- `copy` không hỗ trợ những thao tác sửa cấu trúc như `add`, `remove`, `clear`.
- `String` là bất biến, nên việc chia sẻ tham chiếu đến chuỗi không cho phép sửa nội dung của một chuỗi đã có.

Với đầu vào là `HashSet` mutable, có thể hình dung:

~~~text
source (mutable HashSet)       copy (unmodifiable Set)
        |                              |
        v                              v
     {"A", "B"}                    {"A", "B"}
        |                              |
        +------ String "A" ------------+
        +------ String "B" ------------+
~~~

Hai tập có **cấu trúc membership độc lập sau lúc sao chép**, nhưng các giá trị phần tử không nhất thiết là object mới. Dù hai tập có cùng nội dung, **không có cam kết về thứ tự duyệt phần tử** của kết quả `Set.copyOf`.

### 2.1. `copyOf` không phải view theo dõi mọi thay đổi nguồn

~~~java
Set<String> source = new HashSet<>(List.of("A", "B"));
Set<String> copy = Set.copyOf(source);

source.add("C");
source.remove("A");

System.out.println(source.contains("C")); // true
System.out.println(copy.contains("C"));   // false
System.out.println(source.contains("A")); // false
System.out.println(copy.contains("A"));   // true
~~~

Bản sao vẫn chứa `"A"` dù nguồn đã xóa nó; bản sao không tự có `"C"` chỉ vì nguồn vừa thêm `"C"`.

Lưu ý **điều kiện của ví dụ**: `source` là một `HashSet` mutable thông thường và `copy` đã được tạo xong **trước** các thay đổi. Đừng đồng nhất kết quả với một lần đọc dữ liệu đồng thời khi nhiều thread đang sửa nguồn trong quá trình `copyOf`.

### 2.2. Thêm/xóa qua chính bản sao thì sao?

~~~java
// copy.add("D");    // Biên dịch được, nhưng ném UnsupportedOperationException.
// copy.remove("A"); // Cũng ném UnsupportedOperationException.
// copy.clear();     // Cũng ném UnsupportedOperationException.
~~~

Lỗi xảy ra ở **runtime** khi thực hiện thao tác, không phải vì Java không cho phép gọi các phương thức này trên kiểu `Set` ở compile time. Interface `Set` có các phương thức đó; implementation trả về từ `Set.copyOf` không hỗ trợ sửa đổi.

Có thể bắt `UnsupportedOperationException` để minh họa, nhưng trong code ứng dụng hãy coi đây là **hợp đồng không cho sửa**, tránh dùng exception làm luồng điều khiển bình thường.

## 3. So sánh `Set.copyOf(source)` và `Collections.unmodifiableSet(source)`

Hai kết quả đều không cho sửa cấu trúc thông qua tham chiếu trả về, nhưng **mối quan hệ với nguồn** khác nhau:

~~~java
Set<String> source = new HashSet<>(List.of("A", "B"));

Set<String> snapshot = Set.copyOf(source);
Set<String> view = Collections.unmodifiableSet(source);

source.add("C");
source.remove("A");
~~~

Sau hai thao tác với nguồn:

| Biến | Các phần tử lúc này | Giải thích |
| --- | --- | --- |
| `source` | `B`, `C` | Tập gốc được thay đổi trực tiếp |
| `snapshot` | `A`, `B` | `Set.copyOf` đã chụp membership từ nguồn mutable trước khi thay đổi |
| `view` | `B`, `C` | `Collections.unmodifiableSet` là wrapper nhìn vào chính tập gốc |

**Khác biệt cốt lõi:**
- **Snapshot:** từ một `HashSet` mutable thông thường, tập kết quả của `Set.copyOf` không được cập nhật bởi `source.add/remove` sau thời điểm sao chép.
- **Unmodifiable view:** một wrapper của `source`. Không được sửa qua wrapper, nhưng **bất kỳ code nào còn giữ `source` có thể sửa `source`**, và `view` sẽ phản ánh thay đổi đó.
- Cả hai đều không tự biến **object phần tử mutable** thành immutable.

Ví dụ để đối chiếu với snapshot mà không cần dùng Java 10:

~~~java
Set<String> detachedView =
        Collections.unmodifiableSet(new HashSet<>(source));
~~~

Đoạn trên tạo một **bản sao nông của tập nguồn** bằng `new HashSet<>(source)`, rồi bọc bản sao đó trong unmodifiable view. Thay đổi membership của `source` sau này không làm thay đổi `detachedView`; tuy nhiên các object phần tử có thể vẫn được chia sẻ.

Chỉ vì có chữ *unmodifiable* trong tên phương thức không có nghĩa đầu ra là một snapshot tách rời. Cần xem wrapper **bọc trực tiếp nguồn** hay **bọc một bản sao riêng**.

## 4. Thay đổi trạng thái của object phần tử: bản sao vẫn có thể thấy

Giả sử mỗi phần tử là một object `Product` có `id` cố định và `label` được phép đổi:

~~~java
final class Product {
    final int id;
    String label;

    Product(int id, String label) {
        this.id = id;
        this.label = label;
    }

    @Override
    public boolean equals(Object other) {
        return other instanceof Product p && id == p.id;
    }

    @Override
    public int hashCode() {
        return Integer.hashCode(id);
    }
}
~~~

*Đây là định nghĩa kiểu minh họa, không phải chương trình độc lập. Chương trình đầy đủ ở mục 8 sẽ dùng một lớp tương tự.*

Ở đây `equals` và `hashCode` **chỉ phụ thuộc vào `id` không thay đổi**, giúp minh họa việc sửa `label` mà không làm hỏng điều kiện membership của `Set`.

~~~java
var original = new Product(1, "Old");
Set<Product> source = new HashSet<>();
source.add(original);

Set<Product> copy = Set.copyOf(source);

original.label = "New";

System.out.println(copy.contains(original)); // true
System.out.println(copy.iterator().next().label); // New
~~~

Có hai sự thật đồng thời:
- Tập `copy` không hỗ trợ `copy.add(...)` hoặc `copy.remove(...)`.
- Tập `copy` vẫn chứa **chính đối tượng `original`**, nên thấy `label` đã đổi thành `New`.

Đó là **bản sao nông về object phần tử**. `Set.copyOf` không gọi copy constructor, `clone()`, hay phương thức `deepCopy()` nào cho từng `Product`.

### 4.1. Xóa đối tượng khỏi nguồn không khiến object biến mất khỏi bản sao

~~~java
source.remove(original);
System.out.println(source.contains(original)); // false
System.out.println(copy.contains(original));   // true
~~~

Sau khi tạo snapshot, membership của nguồn và kết quả không còn phải giống nhau. Vì `copy` vẫn tham chiếu đến `original`, đối tượng tiếp tục có thể được truy cập qua bản sao. Phần tử bị xóa khỏi nguồn **không nhất thiết được giải phóng khỏi bộ nhớ** khi bản sao còn giữ tham chiếu đến nó.

### 4.2. Thay thế object bằng đối tượng khác không ảnh hưởng snapshot cũ

`Set` không có `set(index, value)` như `List`; việc “thay” phần tử tương đương với một hoặc nhiều thao tác **remove/add**, tùy quy tắc `equals` và `hashCode`:

~~~java
source.remove(original);
source.add(new Product(2, "Replacement"));
~~~

Tập `copy` đã tạo trước đó vẫn trỏ tới object `original`; không tự chuyển sang `Product(2, "Replacement")`. Đừng dùng vị trí hoặc thứ tự duyệt để mô tả thay đổi trong `Set`: tập hợp không có chỉ số phần tử theo hợp đồng của `Set`.

## 5. Cảnh báo quan trọng: mutable key với `equals()`/`hashCode()`

Một nguy cơ riêng của `Set` là **thay đổi các field góp phần định nghĩa `equals()` hoặc `hashCode()` sau khi phần tử đã nằm trong tập**.

Giả sử `Product.hashCode()` được tính từ `label` thay vì `id`, và `label` có thể đổi. Khi bạn thêm đối tượng vào `HashSet` rồi sửa `label`, trạng thái hashing có thể **không còn nhất quán** với vị trí lưu trữ nội bộ. Tương tự, `Set.copyOf` có thể dùng representation dựa trên hashing; vì vậy **không thể dựa vào kết quả `contains` hay `remove` như thể không có gì thay đổi** khi element mutation làm đổi equality/hashing.

Ví dụ **cố ý mô tả một thiết kế rủi ro**, không phải đoạn code để dự đoán stdout:

~~~java
// Giả sử MutableKey.equals/hashCode phụ thuộc vào key,
// và key có thể sửa sau khi thêm vào Set.
var key = new MutableKey("before");
Set<MutableKey> source = new HashSet<>();
source.add(key);

Set<MutableKey> snapshot = Set.copyOf(source);
key.setKey("after");

// KHÔNG giả định source.contains(key) hay snapshot.contains(key)
// luôn cho kết quả như lúc key còn "before".
~~~

`MutableKey` là một kiểu giả định được mô tả trong comment, **không được định nghĩa ở đây**. Đoạn trên chỉ minh họa tình huống cần tránh; chương trình Java 17+ hoàn chỉnh ở mục 8 không có vấn đề này vì sử dụng `id` bất biến cho `equals`/`hashCode`.

**Quy tắc thực hành:**
- Chỉ dùng các phần tử có `equals`/`hashCode` ổn định khi chúng nằm trong set dựa trên hashing.
- Nếu object có dữ liệu mutable, tránh đưa các field có thể sửa vào định danh dùng làm khóa set.
- Nếu cần danh tính dựa trên dữ liệu có thể thay đổi, cân nhắc **tạo object mới** và quản lý việc thay thế có kiểm soát thay vì đột ngột thay đổi khóa của object đã nằm trong set.
- Đừng dựa vào thứ tự duyệt của `Set.copyOf`, cũng đừng thử “sửa” một hash bị thay đổi bằng cách hy vọng lời gọi `contains` sẽ tự khôi phục.

Điều này liên quan trực tiếp đến câu hỏi “tập nguồn thay đổi”: đôi khi **nguồn không gọi `add/remove`** nhưng trạng thái phần tử đổi làm việc quan sát tập và các phép membership trở nên khó tin cậy.

## 6. `Set.copyOf` không có cam kết thứ tự duyệt

Khi `source` là `LinkedHashSet`, các phần tử ở nguồn thường được duyệt theo thứ tự thêm vào; khi `source` là `TreeSet`, các phần tử được duyệt theo comparator tương ứng. Nhưng **`Set.copyOf` không cam kết giữ thứ tự duyệt của nguồn**, dù trước hay sau khi nguồn thay đổi.

~~~java
Set<String> source = new LinkedHashSet<>(List.of("C", "A", "B"));
Set<String> copy = Set.copyOf(source);

// Không dựa vào copy.toString() in ra [C, A, B].
// Không dựa vào copy.iterator().next() trả "C".
~~~

Muốn kết quả hiển thị **deterministic** khi học hoặc kiểm thử, có thể tạo một danh sách được sắp xếp từ set:

~~~java
System.out.println(new TreeSet<>(copy)); // [A, B, C]
~~~

Đoạn minh họa trên cần import các lớp `Set`, `LinkedHashSet`, `List`, `TreeSet` từ `java.util`.

Việc tạo `TreeSet` chỉ phục vụ **hiển thị có thứ tự** trong ví dụ. Nó không có nghĩa bản sao `Set.copyOf` tự được sắp xếp.

## 7. Một số điều kiện API cần biết khi nguồn thay đổi

### 7.1. Phần tử `null`

`HashSet` có thể chứa `null`, nhưng `Set.copyOf` **không cho phép phần tử `null`**:

~~~java
Set<String> source = new HashSet<>();
source.add("A");
source.add(null);

// Set.copyOf(source); // Ném NullPointerException
~~~

Collection nguồn là `null` cũng gây `NullPointerException`. Nếu nguồn có thể chứa `null`, hãy quyết định trước hợp đồng dữ liệu: lọc giá trị rỗng hoặc dùng một kiểu biểu diễn rõ nghĩa. Đừng im lặng loại dữ liệu nếu nghiệp vụ cần biết nó.

### 7.2. Phần tử trùng lặp

Tham số của `Set.copyOf` là `Collection`, **không bắt buộc là `Set`**. Nếu nguồn là một `List` chứa các phần tử trùng nhau theo `equals`, kết quả là một set, nên không giữ tất cả bản trùng:

~~~java
var source = List.of("A", "A", "B");
var copy = Set.copyOf(source);

System.out.println(copy.size()); // 2
~~~

Nếu nhiều đối tượng **khác tham chiếu nhưng được xem là bằng nhau** theo `equals`, API có thể chọn **một trong những phần tử trùng nhau** để đại diện. Đừng dựa vào việc đối tượng được giữ lại là đối tượng xuất hiện đầu tiên hoặc cuối cùng trong collection nguồn.

Điều này cũng cho thấy `Set.copyOf` là **snapshot tập hợp phần tử theo equality**, chứ không phải một bản sao lưu bảo tồn mọi vị trí của `List`.

### 7.3. Không luôn tạo một object set hoàn toàn mới

Nếu collection đưa vào đã là một **unmodifiable set phù hợp**, `Set.copyOf` có thể tái sử dụng instance thay vì tạo bản sao mới. Vì vậy, không nên kiểm thử chung bằng:

~~~java
Set<String> original = Set.of("A", "B");
Set<String> copy = Set.copyOf(original);

// Không yêu cầu original != copy;
// chỉ cần dựa vào hợp đồng phần tử và tính unmodifiable.
~~~

Ví dụ chính của bài luôn dùng `HashSet` mutable để giải thích **nguồn thay đổi sau khi tạo snapshot**. Không khái quát từ đó rằng `Set.copyOf` bắt buộc tạo một object mới với **mọi** loại input.

### 7.4. Thay đổi nguồn đồng thời với lúc copy

`Set.copyOf` không phải một giao dịch chụp snapshot nguyên tử của một collection đang bị thay đổi không đồng bộ. Nếu thread khác thêm/xóa phần tử **trong lúc** code đang duyệt hoặc sao chép nguồn, đừng giả định đầu ra là một ảnh chụp nhất quán theo thời điểm. Hãy áp dụng đồng bộ hóa, ownership hoặc cơ chế concurrent/snapshot phù hợp với yêu cầu ứng dụng.

Sau khi `copyOf` đã hoàn tất trong ví dụ **single-thread**, thay đổi membership của `HashSet` nguồn không được tự động phản ánh vào snapshot.

## 8. Chương trình Java 17+ độc lập: thay đổi nguồn, view và phần tử mutable

Tạo tệp **SetCopyOfSourceChangeDemo.java**:

~~~java
import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeSet;

public class SetCopyOfSourceChangeDemo {
    static final class Item {
        private final int id;
        private String label;

        Item(int id, String label) {
            this.id = id;
            this.label = label;
        }

        void rename(String newLabel) {
            this.label = newLabel;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Item item && id == item.id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    static String sorted(Set<String> values) {
        return new TreeSet<>(values).toString();
    }

    public static void main(String[] args) {
        Set<String> source = new HashSet<>(List.of("A", "B"));
        Set<String> snapshot = Set.copyOf(source);
        Set<String> view = Collections.unmodifiableSet(source);

        System.out.println("snapshot before = " + sorted(snapshot));

        source.add("C");
        source.remove("A");

        System.out.println("source after = " + sorted(source));
        System.out.println("snapshot after = " + sorted(snapshot));
        System.out.println("view after = " + sorted(view));
        System.out.println("snapshot has A = " + snapshot.contains("A"));
        System.out.println("snapshot has C = " + snapshot.contains("C"));

        try {
            snapshot.add("D");
        } catch (UnsupportedOperationException ex) {
            System.out.println("snapshot add = blocked");
        }

        // Object được chia sẻ giữa HashSet nguồn và bản sao.
        var original = new Item(1, "one");
        var other = new Item(2, "two");

        Set<Item> items = new HashSet<>();
        items.add(original);
        items.add(other);
        Set<Item> objectsCopy = Set.copyOf(items);

        System.out.println("same item reference = "
                + objectsCopy.stream().anyMatch(x -> x == original));

        original.rename("ONE");
        String labelFromCopy = objectsCopy.stream()
                .filter(x -> x.id == 1)
                .findFirst()
                .orElseThrow()
                .label;
        System.out.println("label via copy = " + labelFromCopy);

        items.remove(original);
        System.out.println("source contains first = "
                + items.contains(original));
        System.out.println("copy contains first = "
                + objectsCopy.contains(original));
        System.out.println("copy size = " + objectsCopy.size());

        // Đầu vào Collection có thể có phần tử trùng.
        Set<String> deduplicated = Set.copyOf(List.of("X", "X", "Y"));
        System.out.println("deduplicated size = " + deduplicated.size());

        try {
            Set.copyOf(Arrays.asList("X", null));
        } catch (NullPointerException ex) {
            System.out.println("copyOf null = rejected");
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac SetCopyOfSourceChangeDemo.java
java SetCopyOfSourceChangeDemo
~~~

**Đầu ra chính xác:**

~~~text
snapshot before = [A, B]
source after = [B, C]
snapshot after = [A, B]
view after = [B, C]
snapshot has A = true
snapshot has C = false
snapshot add = blocked
same item reference = true
label via copy = ONE
source contains first = false
copy contains first = true
copy size = 2
deduplicated size = 2
copyOf null = rejected
~~~

### Phân tích kết quả

1. **`source.add("C")` và `source.remove("A")`:** nguồn đổi thành `{B,C}`, còn snapshot đã tạo trước đó vẫn có `{A,B}`.
2. **`view`:** wrapper `Collections.unmodifiableSet(source)` phản ánh tập nền sau khi thay đổi.
3. **`snapshot.add("D")`:** bị từ chối vì kết quả `Set.copyOf` là unmodifiable.
4. **`same item reference = true`:** `objectsCopy` giữ lại chính đối tượng `original`, không tạo `Item` mới.
5. **`original.rename("ONE")`:** `label` thay đổi, và có thể đọc `ONE` thông qua phần tử của `objectsCopy`.
6. **`items.remove(original)`:** tập nguồn không còn chứa `original`, nhưng bản sao vẫn chứa chính đối tượng đó.
7. **`Item.equals/hashCode` chỉ dùng `id` bất biến**, nên việc đổi `label` không làm thay đổi khóa membership và không gây lỗi hashing khó dự đoán.
8. **Phần tử trùng:** `Set.copyOf(List.of("X","X","Y"))` có hai phần tử phân biệt.
9. **`null`:** `Set.copyOf` từ chối collection chứa phần tử `null`.

Ví dụ hiển thị `Set<String>` thông qua `TreeSet`, vì vậy stdout **không phụ thuộc thứ tự duyệt không xác định** của `HashSet` hoặc `Set.copyOf`.

## 9. So sánh dạng thay đổi sau copy

Giả sử `source` là `HashSet<Item>` mutable và `snapshot = Set.copyOf(source)` đã hoàn tất:

| Hành động sau khi sao chép | Membership của `snapshot` có đổi theo? | Ghi chú |
| --- | --- | --- |
| `source.add(newItem)` | Không | Item mới chỉ xuất hiện ở nguồn, trừ khi đã tương đương một item tồn tại |
| `source.remove(item)` | Không | Snapshot còn giữ tham chiếu item đã được chụp |
| `source.clear()` | Không | Snapshot không biến thành rỗng chỉ vì nguồn được xóa |
| `source` được gán tham chiếu sang một set khác | Không | Biến nguồn đổi tham chiếu không làm thay đổi snapshot |
| `item.rename(...)` với field không tham gia equality/hashing | Membership không đổi; **trạng thái item nhìn thấy thay đổi** | Hai tập vẫn dùng chung object |
| Sửa field dùng trong `equals/hashCode` của item | **Không được dựa vào kết quả** | Có thể phá vỡ đặc tính tra cứu của set |
| `snapshot.add/remove` | Không thực hiện được | Ném `UnsupportedOperationException` |
| Gọi `Collections.unmodifiableSet(source)` rồi nguồn đổi | View đổi theo nguồn | Wrapper không phải snapshot |

Mỗi hàng phân biệt **membership** (những object nào thuộc tập) với **trạng thái của object phần tử**. Việc in ra một item có field đã đổi không tự chứng minh một membership mới được thêm hoặc xóa.

## 10. Nếu muốn dữ liệu thực sự độc lập với nguồn

`Set.copyOf` thường đủ nếu phần tử bất biến, chẳng hạn chuỗi hoặc các value object được thiết kế đúng. Nếu phần tử mutable và API yêu cầu độc lập, cần **defensive copying ở cấp phần tử**.

### 10.1. Sao chép từng phần tử

Giả sử `Item` có một copy constructor hoặc `copy()` sao chép đầy đủ các trạng thái mutable cần bảo vệ:

~~~java
Set<Item> independent = source.stream()
        .map(Item::copy)
        .collect(java.util.stream.Collectors.toUnmodifiableSet());
~~~

Đây là **đoạn minh họa** (không phải chương trình độc lập; kiểu `Item` trong mục 8 chưa khai báo `copy()`). Với Java 10+, `Collectors.toUnmodifiableSet()` hỗ trợ tạo một set unmodifiable từ stream, song chính **`Item::copy`** mới là bước đảm bảo tách object phần tử. Nếu class có nested object mutable, `copy()` còn phải sao chép các phần trạng thái đó theo hợp đồng.

Nếu `Item::copy` chỉ gọi `new Item(id,label)` với các thành phần nguyên thủy hoặc immutable như ví dụ mục 8 thì có thể đủ cho mô hình đơn giản; nếu có `Address` mutable, phải xử lý `Address` tương ứng.

### 10.2. Chuyển sang immutable value object

Khi chỉ cần công bố ID và nhãn, dùng record có các thành phần immutable:

~~~java
record ItemSnapshot(int id, String label) {}

Set<ItemSnapshot> safe = source.stream()
        .map(item -> new ItemSnapshot(item.id, item.label))
        .collect(java.util.stream.Collectors.toUnmodifiableSet());
~~~

Đoạn này minh họa code **JDK 17+** bên trong một lớp/phương thức nhìn thấy field `Item.id`, `Item.label`. `record ItemSnapshot` gồm `int` và `String`, nên phần dữ liệu được công bố không tham chiếu đến `Item` mutable.

**Không suy rộng** rằng mọi record đều bất biến sâu: record chứa một `List<MutableItem>` hoặc object mutable vẫn có thể để lộ trạng thái thay đổi.

### 10.3. Tránh sao chép tốn kém khi element immutable

Với `Set<String>`, các tham chiếu được chia sẻ là những đối tượng `String` bất biến. Thay đổi `source` bằng `add`/`remove` không làm nội dung snapshot thay đổi; bản thân đối tượng `String` không thể bị chỉnh sửa tại chỗ. Trong trường hợp này `Set.copyOf` thường là lựa chọn phù hợp để công bố một tập kết quả unmodifiable.

## 11. Các sai lầm thường gặp

**Sai lầm 1 — “Tập nguồn thêm phần tử mới thì bản sao tự cập nhật.”**  
Sai với `Set.copyOf` được tạo từ `HashSet` mutable trước khi thêm. Muốn một view theo dõi nguồn, `Collections.unmodifiableSet(source)` là cơ chế khác.

**Sai lầm 2 — “Nguồn xóa phần tử thì bản sao cũng bỏ phần tử ấy.”**  
Không. Snapshot giữ phần tử đã chụp; nếu phần tử là object mutable, bản sao vẫn có thể giữ tham chiếu đến object đó sau khi nó không còn trong nguồn.

**Sai lầm 3 — “Unmodifiable set nghĩa là các phần tử immutable.”**  
Không. `Set.copyOf` ngăn sửa set qua API, không tự đóng băng state của object.

**Sai lầm 4 — “Sửa một field mutable trong object phần tử là thay đổi membership của set.”**  
Không nhất thiết. Nếu field không tham gia `equals/hashCode`, membership không đổi. Nếu field có tham gia, thao tác có thể làm mất tính nhất quán của tra cứu.

**Sai lầm 5 — “`Set.copyOf` giữ thứ tự của `LinkedHashSet` hoặc `TreeSet` nguồn.”**  
Không có hợp đồng như vậy. Nếu logic cần thứ tự, hãy dùng cấu trúc dữ liệu và API có hợp đồng thứ tự phù hợp, đừng dựa vào output của `Set.copyOf`.

**Sai lầm 6 — “`Set.copyOf` luôn tạo object set mới.”**  
Không nhất thiết khi input đã là unmodifiable set phù hợp. Kiểm thử nội dung và hợp đồng, không dùng `source != copy` làm quy tắc chung.

**Sai lầm 7 — “`Set.copyOf` giữ các object trùng nhau trong List nguồn.”**  
Không. Kết quả là set nên chỉ giữ các phần tử phân biệt theo equality; với các bản trùng nhau, không dựa vào đối tượng nào được chọn.

**Sai lầm 8 — “Có thể copy khi nguồn đang bị sửa đồng thời mà không cần phối hợp.”**  
Không nên mặc định. Nếu nguồn được thay đổi bởi thread khác trong lúc sao chép, cần cơ chế đồng bộ hoặc snapshot phù hợp để đáp ứng yêu cầu nhất quán.

## 12. Câu hỏi tự kiểm tra

**1. Cho `source = new HashSet<>(Set.of("A","B"))`, sau đó `copy = Set.copyOf(source)`. Nếu gọi `source.add("C")`, `copy.contains("C")` là gì?**  
`false` trong kịch bản nguồn mutable được copy xong trước khi thay đổi. Membership snapshot không tự cập nhật.

**2. Nếu `source.remove("A")` sau khi sao chép, `copy.contains("A")` có còn là `true` không?**  
Có, nếu `"A"` thuộc tập tại lúc copy và không có thao tác bất thường làm thay đổi equality của object phần tử.

**3. Vì sao `Collections.unmodifiableSet(source)` có thể thấy phần tử mới khi nguồn gọi `add`?**  
Vì đây là một **view** bọc trực tiếp tập nguồn, chứ không phải snapshot cấu trúc tách rời.

**4. `Set.copyOf` có clone từng object phần tử không?**  
Không. Nó lưu các object phần tử đã có dưới dạng tham chiếu, không thực hiện deep copy.

**5. Nếu một phần tử có field `name` mutable nhưng `equals/hashCode` chỉ dựa vào `id` final, sửa `name` có làm phần tử biến mất khỏi snapshot không?**  
Không vì khóa equality/hashing không đổi; tuy nhiên tên mới có thể được quan sát qua tham chiếu phần tử trong snapshot.

**6. Điều gì đáng lo nếu `hashCode()` dùng một field mà bạn thay đổi sau khi thêm object vào `HashSet`?**  
Việc tra cứu hoặc các thao tác dựa trên hashing có thể không còn hoạt động đúng kỳ vọng. Không nên thay đổi trạng thái tham gia equality/hashing khi object đang là phần tử set.

**7. `Set.copyOf(List.of("A","A","B"))` có bao nhiêu phần tử?**  
Hai phần tử phân biệt. API không giữ nhiều bản giống nhau theo equality như một `List`.

**8. Có nên dùng `snapshot.iterator().next()` để dự đoán phần tử đầu tiên theo thứ tự thêm ở nguồn không?**  
Không. `Set.copyOf` không cam kết thứ tự duyệt.

**9. `Set.copyOf` có chấp nhận một nguồn chứa `null` không?**  
Không, nó ném `NullPointerException`.

**10. Khi nào cần copy sâu thay vì chỉ gọi `Set.copyOf`?**  
Khi dữ liệu công bố phải độc lập với những object mutable ở nguồn; cần tạo object mới cho phần trạng thái mutable mà hợp đồng yêu cầu tách biệt, hoặc chuyển sang value object immutable.

## 13. Ghi nhớ cuối bài

- **`Set.copyOf` (Java 10+) tạo snapshot membership unmodifiable từ nguồn mutable thông thường**, chứ không phải view theo dõi những thay đổi `add/remove` sau đó.
- **Đối tượng phần tử có thể vẫn được chia sẻ theo tham chiếu**; sửa trạng thái của object ấy có thể được nhìn thấy qua snapshot.
- **Đừng sửa field tham gia `equals/hashCode` khi object đang là phần tử set**, nhất là cấu trúc dựa trên hashing.
- **`Collections.unmodifiableSet(source)` là view**, khác cơ chế snapshot của `Set.copyOf(source)`.
- **Không dựa vào thứ tự duyệt, identity set mới, hoặc thứ tự chọn phần tử trùng** nếu API không cam kết điều đó.
- Nếu API cần cách ly cả trạng thái phần tử, dùng **deep copy hoặc immutable value objects** với hợp đồng rõ ràng.

**Tài liệu tham khảo hiện còn áp dụng:**
- [Java SE 17 — `Set.copyOf(Collection)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)).
- [Java SE 17 — `Collections.unmodifiableSet(Set)`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableSet(java.util.Set)).
- [Java SE 17 — `HashSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html).
- [Java SE 17 — `Collectors.toUnmodifiableSet()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableSet()).
