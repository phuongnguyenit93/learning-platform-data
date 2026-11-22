# Danh sách con và các đường sửa đổi qua iterator khi dùng `List.copyOf`

*Chủ đề Java 10 — `List.copyOf`. Bài học sử dụng các quy tắc đang áp dụng trên Java 17+ và các bản Java hiện đại. Trọng tâm: `subList`, `Iterator`, `ListIterator`, các đường sửa đổi gián tiếp, và cách bảo vệ hợp đồng collection không thể sửa.*

## 1. Kết luận trọng tâm

`List.copyOf(collection)` (có từ Java 10) tạo một **danh sách không thể sửa** (*unmodifiable list*) chứa các phần tử từ collection nguồn, theo thứ tự duyệt của nguồn. Nếu nguồn bị thay đổi sau đó, nội dung danh sách kết quả **không phản ánh thay đổi ấy**. Những đặc điểm cần hiểu cùng nhau:

1. **Không sửa trực tiếp:** `add`, `remove`, `set`, `clear`, `replaceAll`, `sort` và các phương thức thay đổi danh sách không được hỗ trợ.
2. **Không sửa qua danh sách con:** `subList(from, to)` của danh sách tạo bởi `List.copyOf` cũng là một **danh sách con không thể sửa**.
3. **Không sửa qua iterator:** gọi `Iterator.remove()`; hoặc `ListIterator.remove()`, `set(...)`, `add(...)` từ iterator của danh sách/`subList` đều bị từ chối bằng `UnsupportedOperationException`.
4. **Không thể dùng “đường vòng” qua `Collections` hoặc view để vượt qua hạn chế:** các thuật toán đòi thay đổi phần tử/cấu trúc vẫn không thể sửa danh sách đó.
5. **Không phải deep immutable:** nếu **bản thân phần tử** là một đối tượng mutable, thay đổi đối tượng ấy qua tham chiếu khác có thể khiến giá trị quan sát qua list thay đổi. `List.copyOf` chỉ bảo vệ **cấu trúc/ánh xạ phần tử của danh sách**.

Ví dụ tối giản (các import `java.util.List` và `java.util.Iterator` khi đặt vào lớp Java):

~~~java
var names = List.copyOf(List.of("An", "Bình", "Chi"));
var middle = names.subList(1, 3);   // [Bình, Chi]
var it = middle.iterator();
System.out.println(it.next());      // Bình
// it.remove();                      // Biên dịch được, ném UnsupportedOperationException
// middle.clear();                   // Biên dịch được, ném UnsupportedOperationException
~~~

Trong bài này, “không sửa được” có nghĩa **API không cho thay đổi cấu trúc/đổi phần tử**, không phải biến `names` hay `middle` thành hằng số ở mức cú pháp, cũng không có nghĩa các object phần tử bất biến sâu.

## 2. Phân biệt ba khái niệm: snapshot, view và copy có thể sửa

Để hiểu vì sao `subList` đôi khi sửa được, đôi khi không, trước tiên cần phân biệt rõ:

| Cách tạo | Vai trò | Có phản ánh thay đổi ở nguồn sau đó? | Sửa trực tiếp/qua iterator? |
| --- | --- | --- | --- |
| `List.copyOf(source)` | Kết quả unmodifiable, dạng snapshot về các phần tử/ánh xạ tại lúc sao chép | **Không** đối với thay đổi cấu trúc hoặc thay thế phần tử của nguồn | **Không** |
| `List.copyOf(source).subList(a,b)` | View phần được chọn của **danh sách đã unmodifiable** | Không phản ánh sửa đổi sau đó ở `source` | **Không** |
| `source.subList(a,b)` với `source` là `ArrayList` mutable | View được hậu thuẫn bởi chính `source` | **Có**, theo hợp đồng view và giới hạn sửa đổi của backing list | **Có**, nếu thao tác được nguồn hỗ trợ |
| `Collections.unmodifiableList(source)` | View không sửa được qua wrapper | **Có**; nội dung có thể phản ánh thay đổi ở `source` | **Không** qua wrapper |
| `Collections.unmodifiableList(source).subList(a,b)` | Subview unmodifiable, dựa trên nguồn mutable | Có thể thấy **thay thế phần tử không làm đổi cấu trúc** của nguồn | **Không** qua subview |
| `new ArrayList<>(source.subList(a,b))` | Bản sao mutable của phần được chọn | **Không** đối với sửa đổi cấu trúc/thay thế phần tử của nguồn | **Có** trên bản sao |

`List.copyOf` không nhất thiết **luôn tạo một object mới**: nếu nhận một danh sách đã unmodifiable phù hợp, implementation có thể tái sử dụng nó. Vì vậy, “snapshot” ở đây diễn tả **hợp đồng giá trị không thay đổi theo các sửa đổi của nguồn sau đó**, chứ không cam kết `original != copy` bằng toán tử `==`.

Một lựa chọn thiết kế quan trọng: `subList` **là view**, không tự động đồng nghĩa với **bản sao**. Khả năng sửa được thừa hưởng từ danh sách nền mà view dựa vào. Nếu nền là unmodifiable, view cũng không thể sửa; nếu nền là `ArrayList` mutable, subview có thể sửa trong các điều kiện API cho phép.

## 3. `List.copyOf` rồi gọi `subList`: thao tác nào hợp lệ?

~~~java
var original = new ArrayList<>(List.of("A", "B", "C", "D"));
var stable = List.copyOf(original);  // [A, B, C, D]
var middle = stable.subList(1, 3); // [B, C]
~~~

Các thao tác **đọc** hợp lệ trên `middle`:

~~~java
var first = middle.get(0);              // "B"
var length = middle.size();             // 2
var containsC = middle.contains("C");   // true
var array = middle.toArray();           // Object[] chứa B, C
for (var name : middle) {
    System.out.println(name);
}
~~~

`subList(fromIndex, toIndex)` dùng **chỉ số đầu bao gồm, chỉ số cuối không bao gồm**: đoạn `(1,3)` có phần tử vị trí 1 và 2. `subList(2,2)` là danh sách con rỗng. Chỉ số âm, `toIndex > size` hoặc `fromIndex > toIndex` không hợp lệ, gây `IndexOutOfBoundsException`.

Các thao tác **ghi/sửa đổi** không được phép:

~~~java
// Ví dụ CỐ Ý gây UnsupportedOperationException khi chạy:
middle.add("E");
middle.remove("B");
middle.set(0, "X");
middle.clear();
middle.replaceAll(String::toLowerCase);
middle.sort(String::compareTo);
~~~

Những dòng trên **không phải một chương trình chạy nối tiếp**: lệnh đầu đã ném ngoại lệ nên các lệnh sau không được thực hiện nếu không bắt lỗi. Mục đích là minh họa: thay vì sửa thành công, mỗi đường ghi sẽ bị từ chối. Đừng hiểu `subList` làm rơi mất tính unmodifiable của `List.copyOf`.

**Chú ý đặc biệt:** các danh sách của `List.of` và `List.copyOf` là unmodifiable theo hợp đồng: bất kỳ method mutator nào trên chúng đều không được hỗ trợ. Không viết mã dựa trên việc mutator có thể “không làm gì” chỉ vì danh sách rỗng, phần tử không tồn tại hoặc thao tác trông như no-op.

## 4. Vì sao `Iterator.remove()` không phải cách lách?

`Iterator<E>` cung cấp `hasNext()`, `next()` và một method tùy chọn `remove()`. **Có method trong interface không có nghĩa collection nền cho phép thực thi**.

~~~java
var stable = List.copyOf(List.of("A", "B", "C"));
var iterator = stable.iterator();

System.out.println(iterator.next()); // A
// iterator.remove();                  // UnsupportedOperationException
~~~

Lời gọi `iterator.next()` hợp lệ, nhưng `remove()` cố thay đổi collection mà iterator duyệt. Với list tạo bởi `List.copyOf`, điều đó không được hỗ trợ. Tương tự:

~~~java
var part = stable.subList(1, 3); // [B, C]
var iterator = part.iterator();
iterator.next();
// iterator.remove();             // UnsupportedOperationException
~~~

Không khác biệt giữa iterator của danh sách gốc và iterator của danh sách con về **quyền sửa đổi**. Dù tên phương thức là `iterator.remove` chứ không phải `list.remove`, nó vẫn là phép thay đổi cấu trúc.

### Quy tắc vị trí vẫn tồn tại trên iterator mutable

Trên `ArrayList` mutable, `Iterator.remove()` chỉ hợp lệ sau `next()` phù hợp và không được gọi lặp `remove()` trước khi tiến sang phần tử khác. Nếu dùng sai trạng thái, có thể ném `IllegalStateException`. Với unmodifiable list, mục tiêu cần nhớ là **quyền sửa không có**; để minh họa chính xác `UnsupportedOperationException`, hãy gọi `next()` trước `remove()` trong bài kiểm thử.

## 5. `ListIterator` có ba đường sửa đổi: `remove`, `set`, `add`

`ListIterator<E>` mở rộng khả năng duyệt hai chiều: `next()`, `previous()`, `hasNext()`, `hasPrevious()`, `nextIndex()`, `previousIndex()`. Ngoài việc đọc, interface khai báo **ba** phương thức có thể thay đổi danh sách:

- `remove()`: loại phần tử cuối cùng được trả về bởi `next()` hoặc `previous()` khi trạng thái iterator cho phép.
- `set(E e)`: thay thế phần tử cuối cùng được trả về khi trạng thái iterator cho phép.
- `add(E e)`: chèn phần tử mới tại vị trí hiện tại của iterator.

Đối với `List.copyOf` hoặc `subList` của nó, **cả ba đều không được hỗ trợ**:

~~~java
var stable = List.copyOf(List.of("A", "B", "C"));
var view = stable.subList(0, 2);

var setter = view.listIterator();
setter.next();
// setter.set("X");       // UnsupportedOperationException

var remover = view.listIterator();
remover.next();
// remover.remove();       // UnsupportedOperationException

var adder = view.listIterator();
// adder.add("X");        // UnsupportedOperationException
~~~

Các method duyệt `previous()`/`next()` vẫn dùng được khi vị trí hợp lệ. Danh sách unmodifiable không chặn **đọc**, chỉ chặn những cách sửa nó. Không nên đoán rằng `ListIterator.set` được phép vì nó “chỉ đổi phần tử chứ không thêm/xóa”: **thay thế phần tử cũng là sửa đổi**.

## 6. Ví dụ hoàn chỉnh, biên dịch và chạy được trên Java 17+

Chương trình sau chứng minh đầy đủ: `List.copyOf` tạo danh sách ổn định khi nguồn bị thay phần tử; `subList` vẫn unmodifiable; cả bốn đường sửa đổi `Iterator.remove`, `ListIterator.set/remove/add` bị chặn; còn `ArrayList.subList` có thể sửa qua iterator và làm thay đổi nguồn.

~~~java
// File: CopyOfSubListDemo.java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

public class CopyOfSubListDemo {
    @FunctionalInterface
    interface Action {
        void run();
    }

    static void expectUoe(String label, Action action) {
        try {
            action.run();
            System.out.println(label + " = unexpected success");
        } catch (UnsupportedOperationException expected) {
            System.out.println(label + " = blocked");
        }
    }

    public static void main(String[] args) {
        var source = new ArrayList<>(List.of("A", "B", "C", "D"));
        var snapshot = List.copyOf(source);
        var middle = snapshot.subList(1, 3);

        System.out.println("snapshot = " + snapshot);
        System.out.println("middle = " + middle);

        source.set(1, "Changed");
        System.out.println("snapshot after source.set = " + snapshot);

        var iterator = middle.iterator();
        System.out.println("iterator next = " + iterator.next());
        expectUoe("iterator.remove", iterator::remove);

        var setter = middle.listIterator();
        setter.next();
        expectUoe("listIterator.set", () -> setter.set("X"));

        var remover = middle.listIterator();
        remover.next();
        expectUoe("listIterator.remove", remover::remove);

        var adder = middle.listIterator();
        expectUoe("listIterator.add", () -> adder.add("X"));
        expectUoe("middle.clear", middle::clear);

        var editableSubList = source.subList(1, 3);
        var mutableIterator = editableSubList.iterator();
        mutableIterator.next();
        mutableIterator.remove();
        System.out.println("source after mutable iterator.remove = " + source);

        var detached = new ArrayList<>(middle);
        detached.add("E");
        System.out.println("detached = " + detached);
        System.out.println("snapshot still = " + snapshot);

        var readOnlyView = Collections.unmodifiableList(source);
        var viewSubList = readOnlyView.subList(1, 3);
        source.set(1, "Updated");
        System.out.println("readOnlyView subList = " + viewSubList);
    }
}
~~~

Lưu chính xác tên tệp `CopyOfSubListDemo.java`, chạy với JDK 17+:

~~~bash
javac --release 17 CopyOfSubListDemo.java
java CopyOfSubListDemo
~~~

Đầu ra chuẩn:

~~~text
snapshot = [A, B, C, D]
middle = [B, C]
snapshot after source.set = [A, B, C, D]
iterator next = B
iterator.remove = blocked
listIterator.set = blocked
listIterator.remove = blocked
listIterator.add = blocked
middle.clear = blocked
source after mutable iterator.remove = [A, C, D]
detached = [B, C, E]
snapshot still = [A, B, C, D]
readOnlyView subList = [Updated, D]
~~~

**Diễn giải:**

1. `source` lúc đầu là `ArrayList<String>` mutable. `snapshot` được tạo từ `List.copyOf(source)`; `middle` là đoạn phần tử 1..2 của snapshot.
2. `source.set(1, "Changed")` **không** làm `snapshot` hay `middle` thay đổi. Mối quan hệ là snapshot giá trị, không phải view trực tiếp của `source`.
3. `iterator.next()` đọc được `"B"`. `iterator.remove()` bị chặn dù iterator đã ở trạng thái có phần tử để xóa.
4. `ListIterator.set`, `remove` và `add` mỗi thao tác được thử trên **một iterator mới**, tránh lẫn lỗi trạng thái với việc không hỗ trợ sửa.
5. `middle.clear()` cũng bị chặn. Không thể dựa vào `subList` để xóa một đoạn của `snapshot`.
6. Trái ngược, `editableSubList` lấy từ `source` mutable; gọi `mutableIterator.remove()` xóa phần tử `"Changed"` ngay ở `source`. Sau đó nguồn còn `[A, C, D]`.
7. `new ArrayList<>(middle)` tạo một danh sách mutable tách biệt. Gọi `detached.add("E")` thành công, snapshot gốc vẫn là `[A, B, C, D]`.
8. `Collections.unmodifiableList(source)` là wrapper/view; phần con `viewSubList` **quan sát** thay đổi `source.set(1, "Updated")` không làm đổi số phần tử. Bởi vậy nó in `[Updated, D]`. Đây là một ví dụ có chủ đích về **non-structural change**; đừng suy rộng ra rằng việc sửa cấu trúc backing list từ ngoài subList là an toàn.

Method `expectUoe` chỉ dùng cho ví dụ để phát hiện đúng loại ngoại lệ. Nó không in nội dung thông báo lỗi cụ thể, vì message/stack trace có thể khác giữa các phiên bản JDK.

## 7. `source.subList` của danh sách mutable: view có thể sửa nguồn

Với `ArrayList` mutable, `subList` cho phép nhiều thao tác thay đổi **được phép ở parent list**, ví dụ:

~~~java
var source = new ArrayList<>(List.of("A", "B", "C", "D", "E"));
var range = source.subList(1, 4); // [B, C, D], là view

range.set(0, "X");       // source: [A, X, C, D, E]
range.remove(1);         // source: [A, X, D, E]
range.add("Y");          // source: [A, X, D, Y, E]

var it = range.iterator();
it.next();               // X
it.remove();             // source: [A, D, Y, E]
~~~

`range` thay đổi cả parent vì đây là một view được backing bởi `source`. Trái lại, nếu chọn:

~~~java
var stable = List.copyOf(source);
var range = stable.subList(1, 3);
// range.remove(0); // UnsupportedOperationException
~~~

thì khả năng sửa không xuất hiện chỉ vì method cùng tên `subList`. **Đối tượng list nền và hợp đồng mutability mới là điểm khác biệt**.

### Một lỗi đặc biệt: sửa backing list trực tiếp khi đang dùng `subList`

Theo `List.subList`, nếu list nền bị **thay đổi cấu trúc** theo cách không thực hiện thông qua sublist, ý nghĩa hành vi của sublist có thể trở nên **không xác định** theo hợp đồng API:

~~~java
var base = new ArrayList<>(List.of("A", "B", "C"));
var part = base.subList(0, 2); // View [A, B]
base.add("D");                 // Sửa cấu trúc bên ngoài part
// Không nên tiếp tục dùng part và giả định nó vẫn hợp lệ.
~~~

Trên một số triển khai, thao tác tiếp theo trên `part` có thể gây `ConcurrentModificationException`; **không được viết code phụ thuộc chắc chắn sẽ có ngoại lệ đó**. Cảnh báo này là giới hạn của view mutable, **không phải** lỗi tồn tại ở một `List.copyOf(source)` độc lập sau khi nguồn thay đổi.

Nếu cần tính ổn định trước thay đổi của nguồn, hãy snapshot phần mong muốn thành một danh sách riêng, ví dụ `List.copyOf(base.subList(0, 2))`, trong khi nguồn còn ở trạng thái hợp lệ.

## 8. Lấy snapshot của một đoạn thay vì lưu subview

Giả sử chỉ cần phần tử vị trí `from` đến ngay trước `to` của nguồn:

~~~java
var source = new ArrayList<>(List.of("A", "B", "C", "D"));
var selected = source.subList(1, 3); // Mutable view [B, C]
var result = List.copyOf(selected);  // Unmodifiable snapshot [B, C]

source.set(1, "Changed");
// result vẫn là [B, C]
~~~

Đây thường là cách viết tốt khi một method muốn **trả về phần dữ liệu đã chọn, nhưng không cho caller sửa và không phản ánh thay đổi từ source sau đó**. Lưu ý:

- `List.copyOf` từ chối `null`: nếu collection nguồn chứa một phần tử `null`, kết quả không được tạo và `NullPointerException` phát sinh.
- `subList` có giới hạn chỉ số; cần xác định `from` và `to` hợp lệ trước khi gọi.
- Nếu `source` mutable đang bị thay đổi đồng thời, việc lấy sublist rồi copy **không tự bảo đảm atomic**; bảo vệ truy cập nguồn theo chiến lược thread-safe phù hợp.
- Snapshot không có nghĩa deep copy các object phần tử.

Phân biệt hai cách:

~~~java
var selectedView = List.copyOf(source).subList(1, 3);
var selectedCopy = List.copyOf(source.subList(1, 3));
~~~

Cả hai đều cho kết quả unmodifiable và không phản ánh những thay đổi cấu trúc/thay thế phần tử được thực hiện sau đó trên `source`. Nhưng biểu thức đầu tạo/giữ một list unmodifiable đại diện toàn bộ nguồn rồi lấy view đoạn; biểu thức sau lấy view mutable của đoạn nguồn tại thời điểm sao chép và tạo snapshot cho đoạn. Không dựa vào giả định đối tượng trung gian nào được cấp phát hay `==` giữa các kết quả.

## 9. Muốn sửa một phần của `List.copyOf` thì làm thế nào?

**Không thể sửa trực tiếp list đã xuất bản qua `subList` hoặc iterator**. Hãy tạo một danh sách mutable mới một cách chủ đích, sửa nó, rồi xuất bản lại nếu cần:

~~~java
var published = List.copyOf(List.of("A", "B", "C", "D"));
var editing = new ArrayList<>(published); // Bản sao mutable
editing.subList(1, 3).clear();          // Xóa B, C ở bản sao
editing.add("E");

var updatedPublication = List.copyOf(editing);
// published: [A, B, C, D]
// updatedPublication: [A, D, E]
~~~

Đoạn này minh họa mẫu **copy → modify → publish**:

1. Tạo working copy mutable bằng `new ArrayList<>(published)`.
2. Thực hiện thao tác cần sửa, ví dụ `subList.clear` hoặc `ListIterator.set/remove/add`, trên bản sao đó.
3. Gọi `List.copyOf` để xuất bản một unmodifiable snapshot mới.
4. Không ghi đè bằng suy nghĩ “`published` cũng đã sửa”; nó vẫn giữ giá trị cũ.

Nếu chỉ cần sửa một đoạn:

~~~java
var readOnly = List.copyOf(List.of("A", "B", "C", "D"));
var editableSegment = new ArrayList<>(readOnly.subList(1, 3));
editableSegment.set(0, "X");
editableSegment.add("Y");
// editableSegment: [X, C, Y]
// readOnly vẫn: [A, B, C, D]
~~~

Đây là cách thay thế an toàn khi nhu cầu là **chỉnh sửa dữ liệu riêng** chứ không phải chọc thủng tính unmodifiable của đối tượng gốc.

## 10. Những đường sửa đổi gián tiếp khác cũng bị chặn

Không chỉ `add` hoặc `remove` mới thay đổi danh sách. Với đối tượng trả từ `List.copyOf` và sublist của nó, không thể dùng những đường khác như:

| Đường thử sửa | Ví dụ | Kết quả có ý nghĩa |
| --- | --- | --- |
| API list | `list.set(0, "X")`, `list.clear()` | `UnsupportedOperationException` |
| API sublist | `list.subList(1,3).clear()` | `UnsupportedOperationException` |
| Iterator | `list.iterator().remove()` | Không hỗ trợ; để test đúng, gọi `next()` trước |
| ListIterator | `set`, `remove`, `add` | Không hỗ trợ; với `set/remove`, nên gọi `next()` trước |
| Default mutators | `replaceAll`, `sort`, `removeIf` | Không được phép sửa list unmodifiable |
| API Collections | `Collections.sort(list)`, `Collections.reverse(list)`, `Collections.fill(list,"X")` | Không thể dùng để thay đổi phần tử của list unmodifiable |
| Stream/lambda | `list.stream().forEach(...)` | Chỉ duyệt phần tử; không trao quyền sửa list |
| Biến thứ hai trỏ cùng list | `var alias = list; alias.add("X")` | Alias không làm thay đổi quyền sửa |
| Ép kiểu giao diện | `Collection<String> c = list; c.clear()` | Đổi kiểu tham chiếu không đổi mutability |

Các thao tác đọc như `get`, `contains`, `indexOf`, `stream`, `forEach`, `iterator.next`, `ListIterator.previous` vẫn có thể thực hiện hợp lệ theo các điều kiện chỉ số/định vị của mỗi method.

**Về Collections.sort/reverse/shuffle:** đó là các thuật toán thay đổi thứ tự/phần tử thông qua các phép cập nhật. Nếu cần trình tự được sắp xếp, hãy sao chép:

~~~java
var stable = List.copyOf(List.of("C", "A", "B"));
var sorted = new ArrayList<>(stable);
sorted.sort(String::compareTo);
var sortedReadOnly = List.copyOf(sorted); // [A, B, C]
~~~

Không truyền danh sách unmodifiable trực tiếp vào thuật toán yêu cầu thay đổi. Với `removeIf` và các default methods, chỉ dựa vào hợp đồng không sửa được của list; đừng dựa vào việc một số implementation có thể kiểm tra/đi qua các phần tử theo thứ tự khác nhau trước khi báo lỗi.

## 11. “Unmodifiable” không đồng nghĩa “deep immutable” hoặc “thread-safe”

Giả sử một phần tử là đối tượng có thể sửa:

~~~java
var item = new StringBuilder("A");
var stable = List.copyOf(List.of(item));
item.append("B");
System.out.println(stable.get(0)); // AB
~~~

`stable.set(0, new StringBuilder("X"))` không được phép, nhưng `StringBuilder` được giữ bên trong list vẫn thay đổi khi tham chiếu `item` bên ngoài gọi `append`. `subList` chứa phần tử đó cũng có thể quan sát thay đổi.

Khi ứng dụng cần **bất biến sâu**, hãy thiết kế phần tử immutable hoặc sao chép cả phần tử theo chính sách cụ thể. Cũng đừng coi `List.copyOf` là giải pháp đồng bộ mọi tương tác giữa các luồng. Nó cung cấp hợp đồng unmodifiable với cấu trúc list; tính an toàn khi các object phần tử bị chia sẻ và sửa đồng thời vẫn cần được xem xét riêng.

### Không dùng `==` làm kiểm thử snapshot

Kết quả của `List.of`/`List.copyOf` và sublist của chúng có đặc tính *value-based* trong tài liệu API. Không dựa vào danh tính object, không dùng chính list đó làm khóa để khóa đồng bộ, và không kiểm thử giả định hai lần gọi luôn có `==` khác nhau. Kiểm tra **giá trị/hành vi**, ví dụ `equals`, `size`, việc không bị ảnh hưởng bởi sửa đổi nguồn và việc mutator bị từ chối.

### `null` và `copyOf`

`List.copyOf` không nhận một collection chứa phần tử `null`. Cũng không thể dùng `subList` của list đó để “tạo một giá trị null” rồi vẫn nói đây là list từ `copyOf`. Nếu nguồn là `ArrayList` cho phép null, `List.copyOf(source.subList(a,b))` sẽ từ chối nếu **đoạn được chọn** có null; chính sách cần rõ ở ranh giới dữ liệu.

## 12. Lỗi thường gặp và cách sửa

| Nhầm lẫn | Sửa lại cách hiểu |
| --- | --- |
| “`subList` luôn tạo ArrayList mới.” | Không. `subList` tạo view của một đoạn list, không phải lời cam kết tạo copy. |
| “Danh sách con của `List.copyOf` sửa được vì nó là view.” | Sai. View đó vẫn unmodifiable như list nền. |
| “Dùng `iterator.remove` sẽ lách được `List.copyOf`.” | Sai. Iterator không cấp quyền sửa vượt quá collection nền. |
| “`ListIterator.set` chỉ thay phần tử nên cho phép.” | Sai. `set` là mutator và bị từ chối. |
| “`ListIterator.add` không cần next nên chắc thêm được.” | Sai. Dù API cho phép gọi khi định vị phù hợp trên mutable list, nó vẫn bị từ chối trên unmodifiable list. |
| “Không thể xóa dải bằng `subList.clear` trên ArrayList.” | Có thể. Nó sửa trực tiếp mutable backing list, nhưng không dùng được trên `List.copyOf`. |
| “`Collections.unmodifiableList(source)` tạo snapshot.” | Không. Đó là read-only view và có thể phản ánh sửa đổi của backing list. |
| “`List.copyOf` chắc chắn tạo object mới.” | Không được giả định; kết quả có thể tái sử dụng list unmodifiable phù hợp. |
| “Unmodifiable đồng nghĩa phần tử immutable.” | Sai. Các phần tử tham chiếu tới object mutable vẫn có thể đổi trạng thái. |
| “Cứ sửa backing ArrayList ngoài subList là subList cập nhật an toàn.” | Sai với sửa đổi cấu trúc: hợp đồng `subList` không bảo đảm hành vi. |
| “`ConcurrentModificationException` luôn xuất hiện khi view bị invalid.” | Không được cam kết; fail-fast là cơ chế phát hiện best-effort ở nhiều implementation. |
| “Dùng `var` làm list thành mutable.” | Sai. `var` chỉ suy luận kiểu tĩnh của biến cục bộ, không đổi hợp đồng API. |

## 13. Bài thực hành và đáp án

**Bài 1.** Cho:

~~~java
var readOnly = List.copyOf(List.of("A", "B", "C"));
var part = readOnly.subList(0, 2);
~~~

Hỏi: `part.add("X")` và `part.listIterator().add("X")` có thành công không?

**Đáp án:** Không. Cả hai đều là phép sửa list/sublist unmodifiable và ném `UnsupportedOperationException` nếu được thực thi. `part` vẫn chứa `[A, B]`.

**Bài 2.** Cho:

~~~java
var src = new ArrayList<>(List.of(1, 2, 3));
var stable = List.copyOf(src);
src.set(1, 99);
~~~

Hỏi: `stable.get(1)` bằng gì?

**Đáp án:** `2`. `List.copyOf` đã tạo kết quả không phản ánh việc sau đó nguồn thay phần tử ở chỉ số 1.

**Bài 3.** Cho:

~~~java
var src = new ArrayList<>(List.of("A", "B", "C"));
var part = src.subList(1, 3);
var it = part.iterator();
it.next();
it.remove();
~~~

Hỏi: `src` còn gì?

**Đáp án:** `[A, C]`. `part` là mutable backed view; iterator xóa phần tử đầu của sublist, tức `"B"` ở nguồn.

**Bài 4.** Cho:

~~~java
var immutable = List.copyOf(List.of("X", "Y"));
var it = immutable.listIterator();
it.next();
// it.set("Z");
~~~

Nếu bỏ chú thích ở dòng cuối?

**Đáp án:** `UnsupportedOperationException`. `next` chỉ làm thay đổi trạng thái vị trí của iterator, không biến `set` thành phép hợp lệ trên unmodifiable list.

**Bài 5.** Viết đoạn mã tạo một danh sách có thể sửa từ phần tử 1 tới 2 của snapshot:

**Đáp án:**

~~~java
var stable = List.copyOf(List.of("A", "B", "C", "D"));
var editable = new ArrayList<>(stable.subList(1, 3));
editable.add("E");  // [B, C, E], stable không đổi
~~~

**Bài 6.** Đoạn sau an toàn không?

~~~java
var source = new ArrayList<>(List.of("A", "B", "C"));
var view = source.subList(0, 2);
source.add("D");
// Tiếp tục sử dụng view
~~~

**Đáp án:** Không nên. `source.add` là sửa đổi cấu trúc từ ngoài `view`; ý nghĩa thao tác với sublist sau đó không được bảo đảm. Thay bằng việc chỉ sửa qua view cho hoạt động mong muốn, hoặc tạo snapshot độc lập trước khi sửa source.

**Bài 7.** `Collections.unmodifiableList(source).subList(0,2)` và `List.copyOf(source).subList(0,2)` có giống nhau không?

**Đáp án:** Cả hai đều không cho caller sửa qua sublist, nhưng **khác việc phản ánh thay đổi nguồn**: wrapper là view dựa vào `source`, còn kết quả `List.copyOf` không phản ánh sửa đổi của nguồn sau khi copy. Cần phân biệt ngữ cảnh non-structural và structural của backing list.

**Bài 8.** Nếu `List.copyOf` chứa `StringBuilder`, gọi `append` trên `StringBuilder` gốc có ảnh hưởng giá trị in ra không?

**Đáp án:** Có thể có. `List.copyOf` không tạo bản sao sâu của object phần tử, chỉ bảo vệ cấu trúc list.

## 14. Checklist khi thiết kế API trả về một phần danh sách

- Bạn cần **view có cập nhật theo nguồn** hay **snapshot ổn định**?
- Đối tượng nguồn có thể sửa không? Có luồng nào khác đồng thời thay đổi không?
- Bạn muốn bảo vệ khỏi cả `list.set`, `subList.clear`, `iterator.remove` và `listIterator.set/add/remove` chưa?
- Chỉ số `from` và `to` đã được kiểm tra hợp lệ chưa?
- Phần dữ liệu được chọn có chứa `null` (khi dùng `List.copyOf` sẽ bị từ chối) không?
- Các phần tử có mutable không, và có cần snapshot sâu ở cấp phần tử không?
- Có kiểm thử cả thao tác đọc được phép và thao tác sửa bị từ chối chưa?
- Người gọi có thực sự cần sửa **bản sao** không? Khi đó trả `new ArrayList<>(...)` có thể phù hợp hơn.
- Bạn đã tránh dựa vào `==`, thứ tự cấp phát, thông báo lỗi hoặc việc `ConcurrentModificationException` luôn xuất hiện chưa?

## 15. Nguồn tham khảo chính thức còn hiệu lực

- [Java SE API — `List`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/List.html): mô tả Unmodifiable Lists, `copyOf`, `subList`, các optional operations và quy tắc view. Đặc biệt, tài liệu xác nhận các sublist của danh sách từ `List.of`/`List.copyOf` cũng nằm trong nhóm unmodifiable, hỗ trợ `RandomAccess`.
- [Java SE API — `ListIterator`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ListIterator.html): `next`/`previous`, `remove`, `set` và `add` cùng điều kiện trạng thái.
- [Java SE API — `Iterator`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Iterator.html): phương thức `remove` là optional operation.
- [Java SE API — `ArrayList`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayList.html): `subList` được hậu thuẫn bởi danh sách nguồn, sửa thông qua view và giới hạn khi sửa trực tiếp backing list.
- [Java SE API — `Collections.unmodifiableList`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Collections.html): wrapper unmodifiable là read-only view, không phải snapshot.
- [JEP 269 — Convenience Factory Methods for Collections](https://openjdk.org/jeps/269): bối cảnh unmodifiable collection factories, vẫn áp dụng trong JDK hiện đại.
- [Java Language Specification — Local Variable Declarations](https://docs.oracle.com/javase/specs/jls/se25/html/jls-14.html#jls-14.4): quy tắc dùng `var` cho biến cục bộ, không ảnh hưởng mutability của list.

**Ghi nhớ:** `List.copyOf` chặn cả **đường sửa trực tiếp** lẫn **đường sửa gián tiếp qua `subList`, `Iterator` và `ListIterator`**. Một `subList` chỉ có quyền sửa nếu list nền thực sự hỗ trợ thao tác đó. Muốn chỉnh sửa dữ liệu đã được xuất bản dưới dạng unmodifiable, hãy tạo **bản sao mutable riêng**, chỉnh sửa bản sao và xuất bản kết quả mới khi cần.