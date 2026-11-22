# Java 10 — Set.copyOf: Giới hạn thao tác thêm, xóa và sửa qua iterator

## Mục tiêu

`Set.copyOf(Collection<? extends E>)` xuất hiện từ **Java 10**. Nó tạo một `Set` **không cho sửa đổi quan hệ thành viên** từ một collection. Bài này tập trung vào cách đọc và duyệt kết quả mà không nhầm `Iterator` với một cơ chế sửa nội dung.

Sau bài học, bạn có thể:
1. Phân biệt những phép đọc như `contains`, `size`, `iterator.hasNext/next` với những thao tác thay đổi tập hợp.
2. Giải thích vì sao `add`, `remove`, `clear`, `removeIf` và `iterator.remove()` trên `Set.copyOf` đều bị chặn.
3. Biết rằng `Iterator<E>` thông thường **không có** `add` hoặc `set`; đây là khác biệt với `ListIterator`.
4. Phân biệt **không thể thay đổi tập phần tử** với **không thể thay đổi object phần tử**.
5. Thực hiện cập nhật bằng cách tạo một mutable set mới, sau đó dùng `Set.copyOf` để xuất một tập không cho sửa.
6. Viết test không dựa vào thứ tự duyệt hoặc identity của đối tượng set.

Các quy tắc được trình bày đều phù hợp với Java hiện đại. Những ví dụ chạy độc lập hướng tới **Java 17+**, và nội dung cốt lõi của `Set.copyOf` cũng áp dụng cho Java 10. Không cần dùng API đã lỗi thời.

## 1. Hợp đồng chính thức của Set.copyOf

Chữ ký API (trích phần khai báo để nhận diện, không phải mã phải tự định nghĩa):

```java
static <E> Set<E> copyOf(Collection<? extends E> coll)
```

Ví dụ trong một phương thức:

```java
Set<String> permissions = Set.copyOf(List.of("READ", "WRITE"));
```

Cần import `java.util.Set` và `java.util.List`. Set kết quả có hai phần tử `READ`, `WRITE`. Bạn có thể hỏi `permissions.contains("READ")` hoặc duyệt chúng nhưng **không thể thêm/xóa** qua API của set.

Những điểm phải nắm:

- Set kết quả **unmodifiable**: mọi phương thức mutator trên Set do `Set.copyOf` tạo ra ném `UnsupportedOperationException`.
- Các thao tác đọc, truy vấn và duyệt vẫn được hỗ trợ.
- Collection nguồn có thể là `List` hoặc `Set`. `copyOf` chỉ giữ **một phần tử thuộc mỗi nhóm phần tử bằng nhau**, vì kết quả là set.
- Nếu nguồn có nhiều object bằng nhau theo `equals`, **đại diện nào được giữ không được cam kết**.
- `null` không được chấp nhận ở cả collection nguồn và phần tử; vi phạm dẫn đến `NullPointerException`.
- Thay đổi cấu trúc collection nguồn sau khi copy **không ảnh hưởng** đến tập kết quả.
- Các phần tử không được deep-copy: có thể giữ tham chiếu đến object mutable.
- Thứ tự duyệt set kết quả **không được xác định**; đừng dựa vào thứ tự chèn từ source.
- Đầu vào đã là unmodifiable set phù hợp có thể được tái sử dụng; đừng dựa vào `==` hay tên lớp implementation.

**Khác biệt phiên bản:** `Set.of("A", "B")` xuất hiện từ **Java 9**; `Set.copyOf(Collection)` xuất hiện từ **Java 10**. `Set.of("A", "A")` ném `IllegalArgumentException` vì đối số trùng, trong khi `Set.copyOf(List.of("A", "A"))` hợp lệ và có một phần tử `"A"`.

## 2. Iterator trên Set.copyOf: đọc được, xóa không được

Lời gọi `set.iterator()` trả một `Iterator<E>`. Interface này cho phép:
- `hasNext()`: hỏi liệu còn phần tử hay không.
- `next()`: lấy phần tử tiếp theo. Nếu đã hết, `next()` ném `NoSuchElementException`.
- `forEachRemaining(Consumer)`: xử lý lần lượt các phần tử còn lại.
- `remove()`: thao tác **tùy chọn** nhằm xóa phần tử vừa được `next()` trả về từ collection mà iterator duyệt. Với set của `Set.copyOf`, thao tác này **không được hỗ trợ**.

Ví dụ đọc được:

```java
var roles = Set.copyOf(List.of("ADMIN", "EDITOR"));
var iterator = roles.iterator();

while (iterator.hasNext()) {
    String role = iterator.next();
    System.out.println(role);
}
```

Đây là mảnh code đặt trong method, cần import `Set` và `List`. Kết quả in ra hai vai trò, nhưng **không có stdout theo một thứ tự cố định** vì thứ tự duyệt của set kết quả không được bảo đảm.

Ví dụ lỗi khi chạy:

```java
var roles = Set.copyOf(List.of("ADMIN", "EDITOR"));
var iterator = roles.iterator();
iterator.next();   // Đọc một phần tử hợp lệ
iterator.remove(); // UnsupportedOperationException
```

Mảnh này cố ý ném ngoại lệ. Gọi `next()` trước giúp minh họa rằng `remove()` bị chặn **vì collection không cho sửa**, chứ không phải vì chưa có phần tử vừa duyệt.

Vòng `for-each` cũng duyệt bằng iterator; nó không ban quyền sửa:

```java
for (var role : roles) {
    System.out.println(role); // Hợp lệ: chỉ đọc
}
```

**Không được phép đổi cách viết vòng lặp để “lách” hạn chế.** Iterator lấy từ `Set.copyOf` luôn phải được xem là iterator chỉ đọc.

### 2.1. Iterator không có add hoặc set

Hai lời gọi sau là **lỗi biên dịch** (đã được comment):

```java
var iterator = roles.iterator();
// iterator.add("VIEWER"); // Sai: Iterator không có add(E)
// iterator.set("OWNER");  // Sai: Iterator không có set(E)
```

`ListIterator<E>` dành cho danh sách có thêm `add` và `set` theo hợp đồng riêng; `Set` không có vị trí index để thay phần tử theo cách đó và không trả `ListIterator`. Vì vậy, câu “sửa Set qua iterator” không thể được hiểu là gọi `set(...)`.

Muốn “thay phần tử A bằng B” trong một `Set` mutable, bạn thường **remove A rồi add B**. Với `Set.copyOf`, cần thực hiện các bước đó trên **set mới có thể sửa** và xuất một snapshot mới.

## 3. Các phương thức mutator bị chặn

| Thao tác | Ý định | Hành vi của Set.copyOf |
|---|---|---|
| `add(value)` | Thêm phần tử | `UnsupportedOperationException` |
| `addAll(collection)` | Thêm nhiều phần tử | `UnsupportedOperationException` |
| `remove(value)` | Xóa phần tử | `UnsupportedOperationException` |
| `removeAll(collection)` | Xóa một nhóm | `UnsupportedOperationException` |
| `retainAll(collection)` | Chỉ giữ nhóm phù hợp | `UnsupportedOperationException` |
| `clear()` | Xóa hết | `UnsupportedOperationException` |
| `removeIf(predicate)` | Xóa phần tử thỏa điều kiện | `UnsupportedOperationException` |
| `iterator.remove()` | Xóa phần tử vừa duyệt | `UnsupportedOperationException` |

Javadoc **Unmodifiable Sets** của `Set.of/Set.copyOf` xác định các mutator luôn bị từ chối. Đừng dựa vào trường hợp gọi mutator nhưng “không thực sự thay đổi gì”, chẳng hạn `remove("not-present")`, để đoán rằng set được phép sửa.

Cần phân biệt ngoại lệ:
- `UnsupportedOperationException`: một thao tác bị implementation chặn do hợp đồng không cho sửa.
- `NoSuchElementException`: iterator đã hết phần tử nhưng bạn vẫn gọi `next()`.
- `ConcurrentModificationException`: có thể xuất hiện trong các collection mutable khác khi bị sửa trong lúc duyệt, **không phải** điều kiện để `Set.copyOf` chặn sửa.

### 3.1. removeIf không phải lọc trả set mới

`removeIf` trông giống `filter` vì nhận predicate, nhưng bản chất **sửa trực tiếp collection**:

```java
roles.removeIf(role -> role.startsWith("A"));
```

Trên tập tạo bởi `Set.copyOf`, lời gọi bị chặn. Nếu muốn loại phần tử khỏi **kết quả mới**, bạn có thể lọc bằng stream rồi gom sang tập mới, hoặc tạo `HashSet` mới và gọi `removeIf` trên tập đó.

### 3.2. forEach không tạo ra quyền sửa

Đoạn này vẫn sai về mặt hợp đồng:

```java
roles.forEach(role -> roles.remove(role));
```

`forEach` chỉ duyệt. Gọi `roles.remove(...)` trong callback vẫn cố sửa set không cho sửa, nên bị từ chối. Ngoài ra, việc sửa cùng một collection đang duyệt còn thường là một nguồn lỗi với các implementation mutable. Hãy xây kết quả riêng nếu cần.

## 4. Ví dụ hoàn chỉnh Java 17+: thử từng thao tác

Lưu file **`SetCopyMutationDemo.java`**:

```java
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class SetCopyMutationDemo {
    static String label(Runnable action) {
        try {
            action.run();
            return "allowed";
        } catch (UnsupportedOperationException ex) {
            return "blocked";
        }
    }

    public static void main(String[] args) {
        var source = new LinkedHashSet<>(List.of("red", "blue"));
        Set<String> frozen = Set.copyOf(source);

        var iterator = frozen.iterator();
        String first = iterator.next();
        System.out.println("readItemPresent=" + frozen.contains(first));

        System.out.println("iteratorRemove=" + label(iterator::remove));
        System.out.println("add=" + label(() -> frozen.add("green")));
        System.out.println("remove=" + label(() -> frozen.remove("red")));
        System.out.println("removeIf="
                + label(() -> frozen.removeIf("blue"::equals)));
        System.out.println("clear=" + label(frozen::clear));

        System.out.println("unchanged="
                + frozen.equals(Set.of("red", "blue")));

        source.add("green");
        source.remove("red");
        System.out.println("snapshotStable="
                + frozen.equals(Set.of("red", "blue")));
        System.out.println("sourceChanged="
                + source.equals(Set.of("blue", "green")));
    }
}
```

Chạy trên JDK 17 trở lên:

```bash
javac --release 17 SetCopyMutationDemo.java
java SetCopyMutationDemo
```

**Stdout chính xác, độc lập thứ tự duyệt:**

```text
readItemPresent=true
iteratorRemove=blocked
add=blocked
remove=blocked
removeIf=blocked
clear=blocked
unchanged=true
snapshotStable=true
sourceChanged=true
```

Giải thích chi tiết:

1. `source` là mutable `LinkedHashSet`. `frozen` được tạo qua `Set.copyOf(source)` nên không cho sửa.
2. `iterator.next()` được phép; chương trình dùng `frozen.contains(first)` thay vì đoán `red` hay `blue` đứng đầu.
3. Phương thức `label` nhận `Runnable` và chuyển ngoại lệ thành nhãn `blocked` để minh họa. Mọi mutator được thử đều bị chặn.
4. Phép `Set.equals` kiểm tra thành viên mà không phụ thuộc thứ tự, nên kết quả có thể dự đoán.
5. Khi xóa `red` và thêm `green` vào `source`, tập nguồn khác trước nhưng `frozen` vẫn chứa `red`, `blue`.

Trong code nghiệp vụ, đừng dùng helper kiểu `label` để nuốt ngoại lệ rồi coi như đã cập nhật thành công. Nếu tập không cho sửa, hành động đúng là xây một tập khác.

## 5. “Sửa qua iterator” có hai nghĩa khác nhau

### 5.1. Sửa tư cách thành viên của Set

Thay đổi danh sách đối tượng thuộc set gồm:
- Thêm một object mới: `add`;
- Xóa object có sẵn: `remove`, `iterator.remove`;
- Thay đối tượng A bằng B: về mặt logic là xóa A rồi thêm B;
- Loại các phần tử theo điều kiện: `removeIf`, `removeAll` hoặc `retainAll`.

Những thao tác này đều là **mutator của set** và bị chặn trên kết quả `Set.copyOf`.

### 5.2. Sửa trạng thái của object đang nằm trong Set

`Set.copyOf` **không deep-copy** các phần tử. Nếu một object bên trong có setter, việc gọi setter của object ấy qua tham chiếu lấy từ iterator có thể thành công:

```java
var ticket = new Ticket(101, "draft");
var items = Set.copyOf(Set.of(ticket));

items.iterator().next().setStatus("approved");
```

Đây là mảnh code giả định class `Ticket` có constructor và method `setStatus` phù hợp. Lệnh gọi `setStatus` đang thay đổi **object phần tử**, không gọi mutator của `Set`. Điều này không có nghĩa `Iterator` của tập cho phép `remove`.

**Cần đặc biệt cẩn thận với `equals/hashCode`.** Nếu các field bị sửa có ảnh hưởng đến `equals()` hoặc `hashCode()`, một set dựa trên hash có thể rơi vào trạng thái tìm kiếm membership không đúng kỳ vọng. Khi lưu object trong set, ưu tiên khóa định danh ổn định; khi cần bất biến sâu, dùng các value object bất biến hoặc sao chép phần tử theo đúng mô hình dữ liệu.

## 6. Ví dụ Java 17+: view, phần tử mutable và cách xây set mới

Lưu thành **`SetCopySemanticsDemo.java`**:

```java
import java.util.Collections;
import java.util.HashSet;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

public class SetCopySemanticsDemo {
    static final class Ticket {
        private final int id;
        private String status;

        Ticket(int id, String status) {
            this.id = id;
            this.status = status;
        }

        String status() {
            return status;
        }

        void setStatus(String status) {
            this.status = status;
        }

        @Override
        public boolean equals(Object other) {
            return other instanceof Ticket t && t.id == id;
        }

        @Override
        public int hashCode() {
            return Integer.hashCode(id);
        }
    }

    public static void main(String[] args) {
        var backing = new LinkedHashSet<>(List.of("A", "B"));
        var snapshot = Set.copyOf(backing);
        var view = Collections.unmodifiableSet(backing);

        backing.add("C");
        System.out.println("snapshotOld="
                + snapshot.equals(Set.of("A", "B")));
        System.out.println("viewTracks="
                + view.equals(Set.of("A", "B", "C")));

        var copyOfDuplicates = Set.copyOf(List.of("A", "A", "B"));
        System.out.println("duplicateSize=" + copyOfDuplicates.size());

        var ticket = new Ticket(101, "draft");
        var items = Set.copyOf(Set.of(ticket));
        items.iterator().next().setStatus("approved");

        System.out.println("elementUpdated=" + ticket.status());
        System.out.println("sameReference="
                + (items.iterator().next() == ticket));

        var mutableCopy = new HashSet<>(snapshot);
        mutableCopy.remove("A");
        mutableCopy.add("D");
        var updated = Set.copyOf(mutableCopy);

        System.out.println("rebuildOriginal="
                + snapshot.equals(Set.of("A", "B")));
        System.out.println("rebuildUpdated="
                + updated.equals(Set.of("B", "D")));
    }
}
```

```bash
javac --release 17 SetCopySemanticsDemo.java
java SetCopySemanticsDemo
```

**Stdout:**

```text
snapshotOld=true
viewTracks=true
duplicateSize=2
elementUpdated=approved
sameReference=true
rebuildOriginal=true
rebuildUpdated=true
```

Những điểm được xác nhận:

- `Set.copyOf(backing)` tạo tập không phản ánh sửa đổi cấu trúc nguồn sau đó; `Collections.unmodifiableSet(backing)` là **view không cho sửa qua view**, nhưng vẫn nhìn thấy thay đổi trực tiếp ở `backing`.
- `Set.copyOf` từ collection có phần tử trùng vẫn hợp lệ, chỉ giữ một phần tử tương đương theo hợp đồng `Set`.
- `Ticket` có trường `status` mutable nhưng `id` cố định. `equals/hashCode` chỉ phụ thuộc `id`, nên đổi `status` không làm thay đổi quy tắc định danh phần tử trong set.
- `sameReference=true` cho thấy `Set.copyOf` không deep-copy object. Đây là phép so sánh **phần tử Ticket riêng** để giải thích shared reference, **không phải** so sánh identity giữa hai object Set.
- `mutableCopy` là `HashSet` mới và có thể cập nhật. `updated` chứa B, D; `snapshot` ban đầu vẫn chứa A, B.

**Khác biệt quan trọng:** unmodifiable view cũng không cho phép `iterator.remove()` qua view. Nó phản ánh thay đổi của backing set do nơi khác thực hiện; vì thế đừng coi `Collections.unmodifiableSet` là snapshot tương đương `Set.copyOf`.

## 7. Quy trình cập nhật một cách an toàn

### 7.1. Sao chép sang tập mutable, sửa, rồi tạo kết quả mới

```java
Set<String> oldPermissions = Set.copyOf(List.of("READ", "WRITE"));

var working = new HashSet<>(oldPermissions);
working.remove("WRITE");
working.add("EXPORT");

Set<String> newPermissions = Set.copyOf(working);
```

Đây là mảnh code trong phương thức, cần import `Set`, `List` và `HashSet`.

Khi kết thúc:
- `oldPermissions` vẫn chứa READ, WRITE;
- `newPermissions` chứa READ, EXPORT;
- `working` là bộ đệm có thể sửa, được giới hạn trong phạm vi tạo kết quả;
- không cố gắng cast unmodifiable Set sang `HashSet` để sửa implementation nội bộ.

Nếu ứng dụng thường xuyên cập nhật một tập rất lớn, sao chép liên tục có thể tốn chi phí. Hãy chọn thiết kế quản lý trạng thái và điểm xuất snapshot thích hợp. Mẫu này rõ ràng cho những lần cập nhật có quy mô phù hợp.

### 7.2. Đóng gói thành hàm trả tập mới

```java
static Set<String> without(Set<String> source, String removed) {
    var mutable = new HashSet<>(source);
    mutable.remove(removed);
    return Set.copyOf(mutable);
}
```

Đây là method minh họa trong một class, cần import `Set` và `HashSet`. Nó không thay đổi `source` và cung cấp tập không cho sửa cho người gọi.

### 7.3. Lọc bằng Stream

`removeIf` sửa collection nhận lệnh; `filter` của stream có thể dùng để tạo collection khác:

```java
Set<String> active = oldPermissions.stream()
        .filter(value -> !"WRITE".equals(value))
        .collect(Collectors.toUnmodifiableSet());
```

Đây là mảnh code cần `java.util.stream.Collectors` và biến `oldPermissions` đã khai báo. `Collectors.toUnmodifiableSet()` có từ **Java 10**. Nó cung cấp set không cho sửa, không cam kết thứ tự duyệt và có thể giữ đại diện bất kỳ nếu kết quả chứa các phần tử trùng theo `equals`.

Khi mục tiêu là tạo một danh sách có thứ tự và có thể chứa phần tử trùng, `Set` có thể không phải cấu trúc phù hợp. Chọn `List` hoặc một dạng biểu diễn thứ tự cụ thể thay vì cố ép `Set.copyOf` làm công cụ sắp xếp.

## 8. Phân biệt read-only, unmodifiable, immutable

Ba khái niệm liên quan nhưng khác nhau:

- **Chỉ đọc qua một tham chiếu (read-only view):** người nhận không sửa được qua tham chiếu view, trong khi backing collection vẫn có thể thay đổi ở nơi khác. Ví dụ `Collections.unmodifiableSet(backing)`.
- **Unmodifiable set có snapshot cấu trúc:** không sửa được qua kết quả; thay đổi cấu trúc nguồn sau `Set.copyOf` không phản ánh vào kết quả.
- **Bất biến sâu (deep immutability):** cả tập hợp **và** nội dung object phần tử (và các object lồng nhau có liên quan) không thay đổi. `Set.copyOf` **không tự cung cấp** điều này.

Nếu tập chỉ chứa `String` hoặc những value object có tính bất biến phù hợp, kết quả có thể được dùng như một value set rất ổn định. Nếu chứa entity mutable hoặc cache object, cần cân nhắc mức ổn định mà API thực sự hứa hẹn.

Để bảo vệ invariant, đừng sửa những trường quyết định `equals/hashCode` của phần tử khi phần tử đang nằm trong một set, kể cả set không cho sửa về cấu trúc.

## 9. Null, phần tử trùng và thứ tự duyệt

### Null

`Set.copyOf(null)` hoặc `Set.copyOf` trên collection chứa `null` ném `NullPointerException`.

```java
var source = new HashSet<String>();
source.add(null);
Set.copyOf(source); // NullPointerException
```

Đây là mảnh code minh họa cố ý ném ngoại lệ. Nếu dữ liệu đầu vào có thể null, hãy xử lý theo hợp đồng nghiệp vụ **trước khi copy** thay vì bắt ngoại lệ rồi im lặng bỏ dữ liệu.

### Trùng lặp

`Set.copyOf` có thể nhận `List.of("A", "A", "B")` và tạo tập gồm A, B. Với hai object khác nhau nhưng bằng nhau theo `equals`, implementation được quyền giữ một trong các object tương đương. Vì vậy, đừng dựa vào thứ tự đầu vào để quyết định “object đại diện” còn lại.

### Thứ tự

Iteration order của unmodifiable set tạo bởi `Set.copyOf` **không được bảo đảm**, kể cả khi nguồn là `LinkedHashSet`. Không assert `iterator.next()` trả phần tử đầu tiên đã chèn; cũng không so sánh `toString()` với một thứ tự tên cố định.

Để kiểm thử nội dung, dùng `Set.equals` hoặc kiểm tra `containsAll` kết hợp `size`. Nếu dữ liệu phải hiển thị theo thứ tự, hãy biến đổi sang `List` có sort/encounter order được xác định.

### Identity

Kết quả `Set.copyOf` là một giá trị set có thể được implementation tái sử dụng. Tránh kiểm tra object identity giữa các set hoặc đồng bộ trên set này. Cần quan tâm **hợp đồng thành viên và không cho sửa**, không quan tâm lớp implementation.

## 10. Giao diện Iterator không tự cấp quyền sửa trong bất kỳ collection nào

`Iterator.remove()` nói chung là **optional operation**. Vì vậy:
- Iterator của một mutable `HashSet` có thể cho phép xóa phần tử vừa duyệt theo đúng quy tắc iterator.
- Iterator của `Set.copyOf` không cho phép.
- Iterator của `Collections.unmodifiableSet(backing)` cũng không cho phép, dù `backing` có thể được sửa trực tiếp ở nơi khác.

Không viết code generic giả định mọi `Iterator` đều có `remove()` hoạt động. Nếu method nhận `Collection<E>` tùy ý, phải xét hợp đồng về mutability mà method yêu cầu; nếu muốn sửa, hãy nhận đúng một mutable abstraction/thiết kế rõ quyền sở hữu hoặc tạo bản mutable mới.

**Phân biệt với `ListIterator`:** `ListIterator.set` thay thế phần tử ở vị trí trong List và `ListIterator.add` chèn vào List. Đó là các operation thuộc ngữ nghĩa của `List`, không có trong `Set.iterator()`.

## 11. Kiểm thử hợp đồng và exception

Mục tiêu kiểm thử nên là hành vi:
1. Đọc được phần tử.
2. Mutator trên set kết quả bị chặn.
3. Iterator không thể remove.
4. Snapshot cấu trúc không thay đổi theo nguồn.
5. Không dựa thứ tự hoặc identity.
6. Nếu có object mutable, thiết kế khóa `equals/hashCode` rõ ràng.

Mẫu Java đơn giản, đặt trong một method và import `Set`/`List`:

```java
var frozen = Set.copyOf(List.of("A", "B"));

if (!frozen.equals(Set.of("A", "B"))) {
    throw new AssertionError("Incorrect members");
}

var it = frozen.iterator();
it.next();

boolean blocked = false;
try {
    it.remove();
} catch (UnsupportedOperationException expected) {
    blocked = true;
}

if (!blocked) {
    throw new AssertionError("Iterator allowed removal");
}
```

Trong JUnit có thể dùng `assertThrows(UnsupportedOperationException.class, it::remove)`, nhưng đó là **mảnh sử dụng framework**, cần test class và dependency JUnit tương ứng. Mục tiêu kiểm chứng vẫn giống nhau.

**Không nên viết:**
- Assert thứ tự phần tử của `Set.copyOf` bằng `toString()`.
- Test `Set.copyOf(source) != source` để chứng minh copy.
- Cast kết quả sang implementation cụ thể như `HashSet` để “bật” quyền sửa.
- Lạm dụng `try/catch` để bỏ qua `UnsupportedOperationException` trong business logic.

## 12. Tương tác với đồng thời và các collection nguồn

`Set.copyOf` không cung cấp một bảo đảm chung rằng nó sẽ đọc được một ảnh chụp **nguyên tử** nếu một thread khác đang sửa collection nguồn cùng lúc. Một số iterator của mutable collection là fail-fast; collection concurrent có thể dùng cơ chế duyệt khác.

Khi cần snapshot nhất quán trong môi trường đồng thời, hãy bảo đảm nguồn ổn định trong thời gian copy theo cơ chế đồng bộ hoặc một cấu trúc dữ liệu có hợp đồng phù hợp. Sau khi copy, set kết quả không cho thay đổi cấu trúc qua API; nhưng điều đó **không làm mọi object phần tử trở nên thread-safe**.

## 13. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu và sửa đúng |
|---|---|
| “`Set.copyOf` cho phép xóa qua iterator vì chỉ chặn `remove` trực tiếp.” | `iterator.remove()` cũng ném `UnsupportedOperationException`. |
| “`removeIf` chỉ lọc nên dùng trên unmodifiable set được.” | Đây là mutator; muốn lọc, tạo kết quả khác. |
| “`Iterator` có `set` và `add`.” | Không. Hai method này có ở `ListIterator`, không phải `Iterator`. |
| “Không sửa được set nên các phần tử cũng bất biến.” | Không. `Set.copyOf` không deep-copy phần tử. |
| “Sửa object phần tử qua iterator tương đương với xóa/thêm trong Set.” | Setter của object và mutator của Set là hai hoạt động khác. |
| “`Collections.unmodifiableSet` tạo snapshot độc lập.” | Là view; thay đổi backing set có thể được phản ánh. |
| “`Set.copyOf` tự giữ thứ tự chèn của `LinkedHashSet` nguồn.” | Không có bảo đảm thứ tự duyệt của kết quả. |
| “Đầu vào có trùng thì `Set.copyOf` ném giống `Set.of`.” | `Set.copyOf` giữ một đại diện tương đương; `Set.of` từ chối phần tử trùng. |
| “Tạo set không cho sửa có nghĩa giữ nguyên identity object bên ngoài.” | Kết quả có thể tái sử dụng instance; không nên dựa identity của Set. |
| “Thay đổi thuộc tính có trong `hashCode` là vô hại khi set không cho sửa.” | Có thể phá invariant membership; tránh thay đổi khóa định danh. |
| “Muốn sửa thì cast sang `HashSet`.” | Tạo `new HashSet<>(existingSet)` rồi sửa bản mới. |

## 14. Checklist code review

- [ ] Phương thức trả set này có ý định cung cấp **unmodifiable snapshot** không?
- [ ] Các consumer có đang gọi `add`, `remove`, `clear`, `removeIf` hoặc `iterator.remove` không?
- [ ] Code có nhầm `Iterator` với `ListIterator` và cần thay phần tử theo vị trí không?
- [ ] Collection nguồn có thể chứa `null` hay các phần tử trùng theo `equals` không?
- [ ] Có chỗ nào giả định thứ tự duyệt của `Set.copyOf` không?
- [ ] Các object phần tử có field mutable tham gia `equals/hashCode` không?
- [ ] Nếu cần cập nhật, đã xây một mutable copy mới và trả lại snapshot mới chưa?
- [ ] Có phân biệt `Set.copyOf` với `Collections.unmodifiableSet` khi nguồn còn có thể thay đổi không?
- [ ] Test có kiểm tra mutator/iterator remove và dùng so sánh theo membership thay vì thứ tự không?
- [ ] Có suy đoán object identity hoặc phụ thuộc tên implementation của unmodifiable set không?

Một thiết kế thông dụng là giữ mutable set trong phần quản lý trạng thái và **xuất `Set.copyOf` ở ranh giới API** khi muốn người nhận không thể làm thay đổi tập thành viên. Nếu caller thực sự cần quyền sửa, hãy thể hiện rõ việc cấp quyền hoặc trả bản mutable độc lập; tránh API mơ hồ rồi bắt lỗi lúc chạy.

## 15. Câu hỏi ôn tập

**1.** `Set.copyOf(List.of("READ", "WRITE")).add("ADMIN")` có thành công không?

**Đáp án:** Không. Kết quả là unmodifiable set; `add` ném `UnsupportedOperationException`.

**2.** Vì sao `iterator.next()` thành công nhưng `iterator.remove()` thất bại?

**Đáp án:** `next` là phép đọc; `remove` là mutator tùy chọn, không được hỗ trợ bởi iterator của `Set.copyOf`.

**3.** Có thể dùng `iterator.set("ADMIN")` không?

**Đáp án:** Không có method đó trên `Iterator`. Muốn thay tư cách thành viên, tạo set mới có thể sửa rồi dùng `remove`/`add`.

**4.** `removeIf` có tương đương với `stream().filter(...)` không?

**Đáp án:** Không. `removeIf` thay đổi collection nhận lệnh; `filter` tạo một luồng phần tử được chọn để sau đó thu về collection khác.

**5.** Vì sao `items.iterator().next().setStatus("done")` có thể chạy dù `items` tạo bằng `Set.copyOf`?

**Đáp án:** Đang gọi setter trên object phần tử mutable, không phải thay đổi tập thành viên. Nhưng cần bảo đảm không phá invariant `equals/hashCode`.

**6.** Nguồn mutable set được thêm phần tử sau `Set.copyOf`; tập kết quả có theo thay đổi không?

**Đáp án:** Không, về quan hệ thành viên. Nó không phải unmodifiable view của backing collection.

**7.** `Set.copyOf(List.of("A", "A", "B"))` có ném `IllegalArgumentException` như `Set.of("A", "A")` không?

**Đáp án:** Không. `copyOf` cho phép collection nguồn có trùng và tạo set chứa hai giá trị A, B.

**8.** Làm sao loại WRITE và thêm EXPORT mà vẫn giữ tập gốc?

**Đáp án:** `var m = new HashSet<>(original); m.remove("WRITE"); m.add("EXPORT"); var updated = Set.copyOf(m);`.

**9.** Có nên assert phần tử đầu tiên của iterator từ `Set.copyOf` là phần tử đầu tiên của `LinkedHashSet` nguồn?

**Đáp án:** Không. Iteration order của set kết quả không được cam kết.

**10.** `Set.copyOf` có bảo đảm thay đổi object phần tử đồng thời là thread-safe không?

**Đáp án:** Không. Nó không deep-copy phần tử và không tự điều phối truy cập đồng thời.

## 16. Tài liệu chính thức

- [Oracle Java SE 17 — `Set`, mục Unmodifiable Sets](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Set.html): `Set.copyOf` (Since: 10), chặn mutator, null, trùng, thứ tự và value-based semantics.
- [Oracle Java SE 17 — `Iterator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html): `hasNext`, `next`, `remove`, `forEachRemaining`.
- [Oracle Java SE 17 — `Collection`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html): unmodifiable collection, mutator và unmodifiable view.
- [Oracle Java SE 17 — `Collections.unmodifiableSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#unmodifiableSet(java.util.Set)): view chỉ đọc phản ánh backing set.
- [Oracle Java SE 17 — `ListIterator`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html): phân biệt các method `add/set` của list iterator.
- [Oracle Java SE 17 — `Collectors.toUnmodifiableSet`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#toUnmodifiableSet()): tạo unmodifiable set từ stream, bổ sung ở Java 10.
- [OpenJDK — JEP 269](https://openjdk.org/jeps/269): bối cảnh các factory method `Set.of` từ Java 9.

**Ghi nhớ:** `Set.copyOf` cho phép **đọc và duyệt** bằng `Iterator`, nhưng không cho sửa tập bằng `add/remove/clear/removeIf` hay `iterator.remove()`. `Iterator` không có `set/add`. Nếu cần thay đổi thành viên, hãy **tạo mutable set mới rồi xuất Set.copyOf mới**. Nếu phần tử là object mutable, việc sửa object vẫn có thể xảy ra và cần kiểm soát `equals/hashCode`.