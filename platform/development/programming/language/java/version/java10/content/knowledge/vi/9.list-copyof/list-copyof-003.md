# List.copyOf: giữ các phần tử trùng trong danh sách

## 1. Kết luận cần nhớ

`List.copyOf(Collection<? extends E> source)` là phương thức static của `java.util.List`, xuất hiện từ **Java 10** và vẫn được hỗ trợ trên các JDK hiện đại. Phương thức tạo một danh sách **không sửa được** chứa các phần tử của collection đầu vào theo **thứ tự duyệt (iteration order)** tại thời điểm lấy bản sao.

**Điểm quan trọng của bài:** nếu nguồn có các phần tử bằng nhau xuất hiện nhiều lần, `List.copyOf` **giữ nguyên tất cả những lần xuất hiện đó**. Nó không gọi `distinct()`, không tự biến list thành set, không gộp phần tử chỉ vì `equals` trả `true`.

~~~java
// Đoạn minh họa bên trong phương thức; cần import java.util.List.
var original = List.of("A", "B", "A", "A");
var copy = List.copyOf(original);

System.out.println(copy);       // [A, B, A, A]
System.out.println(copy.size()); // 4
~~~

Với ví dụ này, chuỗi `"A"` xuất hiện **3 lần** trong cả nguồn và bản sao. Nếu sử dụng `Set.copyOf(original)` thay vì `List.copyOf(original)`, tập kết quả chỉ có **2 giá trị phân biệt** (`"A"` và `"B"`), vì `Set` có hợp đồng không chứa phần tử trùng.

Hai khái niệm **“không sửa được”** và **“không có phần tử trùng”** hoàn toàn độc lập:

- **Không sửa được:** không thể thêm, xóa, thay thế phần tử qua list kết quả.
- **Cho phép trùng:** có thể lưu nhiều vị trí có giá trị bằng nhau; `size()` đếm tất cả vị trí.
- **Có thứ tự:** vị trí `0`, `1`, ... của kết quả tương ứng thứ tự duyệt phần tử khi sao chép.

Không nên dùng `Set.copyOf` chỉ để “làm collection chỉ đọc” nếu yêu cầu nghiệp vụ bắt buộc giữ số lần xuất hiện của từng mục.

## 2. Vì sao List giữ phần tử trùng còn Set không?

Theo hợp đồng Collections Framework:

- Một `List<E>` là **dãy có thứ tự**. Các vị trí khác nhau được phép chứa những phần tử có `equals` bằng nhau. Các phương thức `get(index)`, `indexOf` và `lastIndexOf` phản ánh vị trí, không phải phép toán hợp nhất giá trị.
- Một `Set<E>` mô tả một **tập phần tử duy nhất** theo hợp đồng bình đẳng (thông thường dựa vào `equals`). Tập không biểu diễn “một giá trị đã xuất hiện 3 lần” bằng 3 slot.
- Một `Map<K,V>` mô tả ánh xạ khóa–giá trị. Nó không chứa hai khóa bằng nhau dưới dạng hai entry độc lập, nên bản sao map không phải công cụ đếm số lần một giá trị xuất hiện.

Vì thế, mặc dù `List.copyOf` và `Set.copyOf` cùng được giới thiệu từ Java 10 để tạo collection không sửa được, **chúng có hợp đồng về phần tử trùng khác nhau**.

| Biểu thức | Kết quả về phần tử trùng | Ghi chú |
| --- | --- | --- |
| `List.copyOf(List.of("A", "A", "B"))` | Giữ `["A", "A", "B"]` | Giữ cả ba vị trí và thứ tự |
| `List.of("A", "A", "B")` | Giữ `["A", "A", "B"]` | Factory list trực tiếp, có từ Java 9 |
| `Set.copyOf(List.of("A", "A", "B"))` | Còn 2 phần tử phân biệt | Không bảo đảm thứ tự duyệt kết quả |
| `Set.of("A", "A", "B")` | Ném `IllegalArgumentException` | Factory set trực tiếp không chấp nhận đối số trùng |
| `List.copyOf(Set.of("A", "B"))` | Có 2 phần tử | Set nguồn đã không chứa trùng; thứ tự tùy iterator của Set nguồn |

**Đặc biệt:** `Set.copyOf` **không** ném `IllegalArgumentException` khi được truyền một collection chứa giá trị trùng nhau. Nó giữ một phần tử đại diện trong mỗi nhóm trùng. Ngược lại, `Set.of("A", "A")` từ chối lời gọi vì có đối số trùng. Đây là hai API có hợp đồng khác nhau, không nên suy luận hành vi API này từ API kia.

## 3. “Giữ trùng” cụ thể có nghĩa là gì?

### 3.1. Giữ đúng số lần xuất hiện

~~~java
// Đoạn minh họa.
var events = List.of("LOGIN", "LOGIN", "LOGOUT", "LOGIN");
var snapshot = List.copyOf(events);

System.out.println(snapshot.size()); // 4
System.out.println(java.util.Collections.frequency(snapshot, "LOGIN")); // 3
~~~

`snapshot.size()` là số **phần tử/vị trí**: `4`. `Collections.frequency(snapshot, "LOGIN")` là số lần phần tử bằng `"LOGIN"` xuất hiện: `3`. Vì `List.copyOf` giữ nguyên duplicate, hai thông số phản ánh chính xác nguồn ở thời điểm sao chép.

Nếu mỗi bản ghi đại diện cho một lần phát sinh sự kiện, tự động gộp duplicate sẽ làm sai tổng số sự kiện. Dùng list là hợp đồng phù hợp khi các lần xuất hiện đều có ý nghĩa.

### 3.2. Giữ vị trí và thứ tự duyệt

~~~java
// Đoạn minh họa.
var copied = List.copyOf(List.of("A", "B", "A", "C", "A"));

System.out.println(copied.get(0));      // A
System.out.println(copied.get(2));      // A
System.out.println(copied.indexOf("A"));     // 0
System.out.println(copied.lastIndexOf("A")); // 4
~~~

Có ba phần tử bằng `"A"` tại các index `0`, `2`, `4`. Phương thức `get` trả phần tử theo index; `indexOf` trả vị trí đầu tiên, `lastIndexOf` trả vị trí cuối. Không có bước “chọn một phần tử đại diện” như với tập hợp.

### 3.3. Bình đẳng giá trị không đồng nghĩa cùng tham chiếu object

Đối với `String`, hai phần tử cùng nội dung `"A"` được coi là bằng nhau theo `equals`. Với kiểu đối tượng tự định nghĩa, hai instance **khác nhau** có thể có `equals` bằng nhau nếu lớp cài đặt bình đẳng dựa trên giá trị.

`List.copyOf` vẫn giữ **cả hai lần xuất hiện** trong danh sách, không phụ thuộc việc hai vị trí trỏ tới cùng instance hay tới hai object có giá trị bằng nhau. Bản sao **không sao chép sâu** các object phần tử; điều này được làm rõ ở mục 7.

Ví dụ nguồn chứa hai object khác nhau được coi là bằng nhau:

~~~java
// Java 17+, record tự động cung cấp equals dựa trên thành phần.
record Tag(String value) {}

// Trong phương thức:
var first = new Tag("A");
var second = new Tag("A");

var source = List.of(first, second);
var copy = List.copyOf(source);

System.out.println(first.equals(second)); // true
System.out.println(first == second);      // false
System.out.println(copy.size());          // 2
~~~

Đây là **các đoạn minh họa riêng**, không phải một file độc lập; cần đặt `record Tag` và mã gọi vào phạm vi Java thích hợp. Kết quả `size() == 2` thể hiện duplicate theo nghĩa bình đẳng giá trị vẫn được giữ.

## 4. Giữ phần tử trùng khi sao chép từ nguồn mutable

Khi nguồn là `ArrayList`, bạn có thể thay đổi nguồn trước/sau thời điểm tạo snapshot. `List.copyOf` chụp cấu trúc ở thời điểm gọi; **thay đổi cấu trúc nguồn sau đó không làm đổi bản sao**.

~~~java
// Cần import java.util.ArrayList và java.util.List.
var source = new ArrayList<>(List.of("A", "B", "A"));
var snapshot = List.copyOf(source);

source.set(0, "X");
source.add("A");
source.remove("B");

System.out.println(source);   // [X, A, A, A]
System.out.println(snapshot); // [A, B, A]
~~~

Giải thích:
1. Snapshot ghi lại ba vị trí `A, B, A` (trong đó `A` xuất hiện 2 lần).
2. `source.set(0, "X")` thay thế phần tử đầu **trong nguồn**.
3. `source.add("A")` thêm một lần xuất hiện `A` mới vào nguồn.
4. `source.remove("B")` xóa một phần tử trong nguồn.
5. Snapshot vẫn có ba phần tử `A, B, A` với số lần trùng và vị trí như lúc tạo.

**Không đánh đồng snapshot với live view.** Ví dụ:

~~~java
// Đoạn minh họa.
var source = new ArrayList<>(List.of("A", "A"));
var view = java.util.Collections.unmodifiableList(source);
var snapshot = List.copyOf(source);

source.add("A");

System.out.println(view);     // [A, A, A]
System.out.println(snapshot); // [A, A]
~~~

`Collections.unmodifiableList(source)` bọc collection gốc để cung cấp **khung nhìn không sửa được**. Khi nguồn thay đổi, view có thể phản ánh trạng thái mới. `List.copyOf(source)` tạo bản sao cấu trúc không phản ánh các thay đổi của một nguồn mutable sau thời điểm lấy copy.

Vì vậy, muốn “giữ số lần xuất hiện tại thời điểm chốt kết quả”, hãy chọn snapshot; muốn “đọc danh sách hiện tại mà không cho sửa qua API đọc”, live view có thể phù hợp nếu đó là chủ đích rõ ràng.

## 5. “Unmodifiable” không đồng nghĩa “tự lọc duplicate”

`List.copyOf` từ chối các thao tác làm đổi cấu trúc danh sách kết quả, bao gồm `add`, `remove`, `set`, `clear`. Điều đó **không hề đặt thêm ràng buộc** rằng dữ liệu trong list chỉ có các giá trị duy nhất.

~~~java
// Đoạn minh họa.
var copy = List.copyOf(List.of("A", "A"));

System.out.println(copy.size()); // 2

// Nếu thực thi, lời gọi dưới đây ném UnsupportedOperationException:
// copy.add("B");
~~~

Phương thức `copyOf` trả danh sách **không sửa được**, nhưng dữ liệu nó chứa có thể trùng từ trước. Hai lần xuất hiện được giữ nguyên, không phải là tác dụng phụ của việc copy mutable hay immutable.

Một nhầm lẫn khác là dùng `distinct()` trong stream rồi mới gọi `List.copyOf`:

~~~java
// Đoạn minh họa, Java 17+.
var data = List.of("A", "B", "A", "A");
var unique = data.stream().distinct().toList();

System.out.println(unique); // [A, B]
~~~

`Stream.distinct()` **chủ động loại trùng** dựa trên `equals`. Với ordered stream như stream của `List`, kết quả của `distinct()` ổn định theo encounter order: giữ phần tử xuất hiện đầu tiên của mỗi nhóm bằng nhau. `Stream.toList()` (Java 16+) thu kết quả thành một danh sách không sửa được. Chính `distinct()` làm mất các lần xuất hiện trùng, **không phải `List.copyOf`**.

Nếu dữ liệu cần tính tần suất, thứ tự hoặc phục vụ audit, đừng đưa `distinct()` vào pipeline trước khi tạo bản sao chỉ vì muốn kết quả unmodifiable.

## 6. Chương trình Java 17+ hoàn chỉnh

Ví dụ sau minh họa trực tiếp việc giữ phần tử trùng, chỉ số, tần suất, sự độc lập cấu trúc, so sánh `Set.copyOf`, xử lý null và sao chép nông với object mutable. Chương trình chỉ dùng các API công khai còn hỗ trợ.

Lưu file đúng tên **`ListCopyOfDuplicatesDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Set;

public class ListCopyOfDuplicatesDemo {

    static final class Box {
        private String value;

        Box(String value) {
            this.value = value;
        }

        void rename(String value) {
            this.value = value;
        }

        String value() {
            return value;
        }
    }

    public static void main(String[] args) {
        var source = new ArrayList<>(List.of("A", "B", "A", "A"));
        var snapshot = List.copyOf(source);

        System.out.println("snapshot=" + snapshot);
        System.out.println("snapshotSize=" + snapshot.size());
        System.out.println("countA=" + Collections.frequency(snapshot, "A"));
        System.out.println("firstA=" + snapshot.indexOf("A"));
        System.out.println("lastA=" + snapshot.lastIndexOf("A"));

        source.set(0, "X");
        source.add("C");
        source.remove(2);

        System.out.println("sourceAfterEdit=" + source);
        System.out.println("snapshotAfterEdit=" + snapshot);

        var setCopy = Set.copyOf(snapshot);
        System.out.println("setSize=" + setCopy.size());

        var uniqueOrdered = snapshot.stream().distinct().toList();
        System.out.println("uniqueOrdered=" + uniqueOrdered);

        var box = new Box("old");
        var boxSource = new ArrayList<Box>();
        boxSource.add(box);
        boxSource.add(box);
        var boxCopy = List.copyOf(boxSource);

        boxSource.clear();
        box.rename("new");

        System.out.println("boxCopySize=" + boxCopy.size());
        System.out.println("boxValues="
                + boxCopy.get(0).value() + "," + boxCopy.get(1).value());
        System.out.println("sameObject="
                + (boxCopy.get(0) == boxCopy.get(1)));

        try {
            snapshot.add("Z");
        } catch (UnsupportedOperationException expected) {
            System.out.println("mutationRejected=true");
        }

        try {
            List.copyOf(Arrays.asList("A", null));
        } catch (NullPointerException expected) {
            System.out.println("nullRejected=true");
        }
    }
}
~~~

Biên dịch bằng JDK 17 trở lên với ngôn ngữ Java 17 và chạy:

~~~bash
javac --release 17 ListCopyOfDuplicatesDemo.java
java ListCopyOfDuplicatesDemo
~~~

**Stdout chính xác:**

~~~text
snapshot=[A, B, A, A]
snapshotSize=4
countA=3
firstA=0
lastA=3
sourceAfterEdit=[X, B, A, C]
snapshotAfterEdit=[A, B, A, A]
setSize=2
uniqueOrdered=[A, B]
boxCopySize=2
boxValues=new,new
sameObject=true
mutationRejected=true
nullRejected=true
~~~

### Giải thích vì sao đầu ra như vậy

1. `source` ban đầu có `[A, B, A, A]`. `List.copyOf` giữ **4 vị trí**, trong đó ba vị trí bằng `"A"`.
2. `Collections.frequency(snapshot, "A")` trả `3`; `indexOf` trả `0` và `lastIndexOf` trả `3`.
3. Nguồn bị `set(0, "X")` rồi `add("C")`: tạm thời thành `[X, B, A, A, C]`. `remove(2)` xóa một lần xuất hiện `A` tại index `2` nên nguồn cuối là `[X, B, A, C]`; snapshot vẫn `[A, B, A, A]`.
4. `Set.copyOf(snapshot)` chỉ còn 2 phần tử phân biệt. Chương trình in `size()` thay vì in toàn bộ set, vì thứ tự duyệt set kết quả không được bảo đảm.
5. `snapshot.stream().distinct().toList()` tạo `[A, B]` vì stream có encounter order từ list và `distinct` giữ lần xuất hiện đầu tiên của mỗi giá trị.
6. `boxSource` đưa **cùng một Box** vào list hai lần. `List.copyOf` giữ cả hai vị trí. Sau `boxSource.clear()`, snapshot vẫn có 2 phần tử; sau `box.rename("new")`, cả hai vị trí hiển thị `new` và so sánh `==` cho `true`. Điều này minh họa sao chép **nông**, không phải deep copy.
7. `snapshot.add("Z")` ném `UnsupportedOperationException` nên in `mutationRejected=true`.
8. `List.copyOf(Arrays.asList("A", null))` ném `NullPointerException`: không chấp nhận phần tử null. Bắt ngoại lệ giúp chương trình vẫn chạy đến hết.

Không có các đoạn mã lỗi không được comment bên trong chương trình hoàn chỉnh. Kết quả in ra không phụ thuộc thứ tự duyệt ngẫu nhiên của set hay map.

## 7. Giữ duplicate không có nghĩa tự tạo bản sao sâu

`List.copyOf` sao chép **các vị trí chứa tham chiếu phần tử**, không có hợp đồng tạo bản sao mới của từng object. Với object có thể sửa, hai vấn đề khác nhau:

- **Số vị trí không đổi**: sau khi tạo list copy, thêm/xóa phần tử trong list nguồn không thay đổi `copy.size()` và thứ tự vị trí của copy.
- **Trạng thái object vẫn có thể đổi**: nếu `copy.get(i)` trỏ tới cùng object mà mã khác đang giữ, việc sửa object đó có thể làm giá trị quan sát được qua copy thay đổi, dù không ai thêm/xóa/thay vị trí trong list copy.

Ví dụ một object được lặp **hai lần theo identity**:

~~~java
// Giả sử lớp Box và phương thức value() đã được định nghĩa.
var box = new Box("A");
var source = new ArrayList<Box>();
source.add(box);
source.add(box);

var copy = List.copyOf(source);
box.rename("B");

System.out.println(copy.size());          // 2
System.out.println(copy.get(0).value());  // B
System.out.println(copy.get(1).value());  // B
~~~

**Điểm mấu chốt:** `List.copyOf` không gộp duplicate vì hai vị trí tham chiếu cùng object. Nó giữ cả hai vị trí. Nhưng sửa một object làm cả hai vị trí quan sát cùng trạng thái mới.

Với object có `equals` theo giá trị, hai instance khác nhau nhưng bằng nhau cũng vẫn có hai vị trí trong list. Nếu cần danh sách hoàn toàn ổn định để lưu trữ lâu dài, nên dùng các value object bất biến, hoặc chủ động sao chép sâu dữ liệu phần tử theo yêu cầu. `record` hữu ích cho mô hình dữ liệu bất biến nông nhưng **không tự làm mọi thành phần tham chiếu bên trong bất biến**.

## 8. Các giới hạn không liên quan đến duplicate nhưng cần biết

### 8.1. Nguồn hoặc phần tử null bị từ chối

~~~java
// Các lời gọi sau gây NullPointerException (chỉ là ví dụ lỗi).
List.copyOf(null);

var withNull = new java.util.ArrayList<String>();
withNull.add("A");
withNull.add(null);
List.copyOf(withNull);
~~~

List mutable như `ArrayList` có thể chứa null, nhưng `List.copyOf` không chấp nhận null. **Cho phép duplicate không đồng nghĩa cho phép null**. Một chuỗi xuất hiện hai, ba hay nhiều lần thì hợp lệ; một phần tử null thì không.

Muốn giữ nguyên null mà vẫn tạo list không sửa được từ một nguồn mutable, có thể dùng một wrapper trên bản sao:

~~~java
// Đoạn minh họa trong phương thức.
var source = new java.util.ArrayList<String>();
source.add("A");
source.add(null);
source.add("A");

var result = java.util.Collections.unmodifiableList(
        new java.util.ArrayList<>(source)
);
System.out.println(result); // [A, null, A]
~~~

Trong ví dụ này, `new ArrayList<>(source)` tạo cấu trúc riêng (có thể chứa null), còn `Collections.unmodifiableList(...)` bọc bản sao mới để từ chối sửa qua kết quả. Đây vẫn là sao chép nông, không deep copy. Không dùng `List.copyOf` nếu yêu cầu hợp đồng bắt buộc giữ các phần tử null.

### 8.2. Đầu vào không nhất thiết là List

Chữ ký `List.copyOf(Collection<? extends E>)` chấp nhận một `Collection` phù hợp, không chỉ `List`:

~~~java
// HỢP LỆ, ví dụ độc lập bên trong phương thức.
var source = new java.util.LinkedHashSet<>(List.of("A", "B"));
var copy = List.copyOf(source);
System.out.println(copy); // [A, B]
~~~

`LinkedHashSet` có thứ tự duyệt theo thứ tự chèn, nên kết quả minh họa có `[A, B]`. Tuy nhiên vì `Set` nguồn không chứa duplicate, `List.copyOf` không thể “khôi phục” những lần xuất hiện trùng đã mất trước đó. Nếu đầu vào là `HashSet` với thứ tự duyệt không cam kết, đừng dựa vào thứ tự in kết quả `List.copyOf`.

**Quy tắc chính xác:** `List.copyOf` giữ nguyên các lần xuất hiện **theo iterator của collection đầu vào**. Nó không tự phục hồi dữ liệu nguồn đã bị loại trùng từ trước và cũng không tự sắp xếp phần tử.

### 8.3. Không bắt buộc cấp phát instance mới

~~~java
// Đoạn minh họa.
var fixed = List.of("A", "A");
var copy = List.copyOf(fixed);
System.out.println(fixed.equals(copy)); // true
~~~

Nếu nguồn đã là một unmodifiable list thích hợp, `List.copyOf` **có thể trả lại chính instance** hoặc một instance tương đương. Không được đặt logic trên giả định `copy != fixed`, cũng không dựa vào `copy == fixed` để suy luận thành phần trùng hay không.

Những danh sách từ factory `List.of` và `List.copyOf` là **value-based**; hãy xem các giá trị bằng nhau là có thể thay thế, tránh dùng identity làm khóa logic hoặc khóa đồng bộ. Hợp đồng của `copyOf` là dữ liệu và tính không sửa được, không phải luôn tạo một object mới.

### 8.4. Thay đổi nguồn đồng thời khi tạo copy

Ví dụ về snapshot và số lượng duplicate phía trên giả định nguồn không bị sửa đồng thời khi `List.copyOf` đang đọc phần tử. Đây **không** phải một thao tác snapshot giao dịch, nguyên tử cho mọi loại mutable collection.

Nếu luồng khác thay đổi nguồn trong lúc copy mà không có cơ chế đồng bộ thích hợp, không thể khẳng định số lượng/phần tử bản sao khớp một thời điểm nhất quán, và có thể có ngoại lệ hoặc hành vi theo implementation. Khi cần chốt đúng số lần mỗi sự kiện, hãy áp dụng đồng bộ/kiểm soát vòng đời nguồn hoặc dữ liệu phù hợp với concurrency.

### 8.5. Kiểu generic và `var` không thay đổi duplicate

~~~java
// Đoạn minh họa:
List<String> explicit = List.copyOf(List.of("A", "A"));
var inferred = List.copyOf(List.of("A", "A"));
~~~

Cả `explicit` và `inferred` có kiểu tĩnh `List<String>`; cả hai giữ hai lần xuất hiện `"A"`. `var` (Java 10+) chỉ suy luận kiểu biến cục bộ từ biểu thức khởi tạo, không thay đổi semantics của `List.copyOf`. Số lần trùng là thuộc tính dữ liệu + hợp đồng list.

## 9. Khi nghiệp vụ thực sự cần gộp duplicate

Đôi khi yêu cầu là **danh sách giá trị duy nhất**, không phải snapshot giữ nguyên các lần xuất hiện. Hãy áp dụng phép loại trùng **tường minh** trước khi xây dựng kết quả:

~~~java
// Có ordered stream từ List, Java 17+.
var source = List.of("A", "B", "A", "C", "B");

var keepAll = List.copyOf(source);
var unique = source.stream().distinct().toList();

System.out.println(keepAll); // [A, B, A, C, B]
System.out.println(unique);  // [A, B, C]
~~~

`distinct()` là lựa chọn khi cần giữ thứ tự xuất hiện đầu tiên của mỗi giá trị trên một **ordered stream**. Với những nguồn không có encounter order bảo đảm, không nên suy đoán thứ tự phần tử sau distinct.

Nếu chỉ quan tâm membership (có/không) và không quan tâm thứ tự hoặc số lần xuất hiện, có thể dùng `Set.copyOf(source)`. Không dùng Set khi bạn vẫn cần index, thứ tự hay số lần lặp. Với nguồn duplicate chứa nhiều instance khác nhau mà `equals` bằng nhau, `Set.copyOf` có thể giữ **một đại diện bất kỳ**; nếu cần ưu tiên instance đầu tiên theo một quy tắc rõ ràng, phải tự chọn quy tắc xử lý thích hợp.

### Dữ liệu cần đếm số lần

Nếu bài toán là “mỗi giá trị xuất hiện bao nhiêu lần?”, không nên loại trùng rồi mất số liệu. Sử dụng danh sách đầy đủ, hoặc tổng hợp vào map tần suất trước khi công bố kết quả:

~~~java
// Minh họa trong phương thức.
var logs = List.of("A", "B", "A", "A");
var counts = new java.util.LinkedHashMap<String, Integer>();

for (var log : logs) {
    counts.merge(log, 1, Integer::sum);
}

System.out.println(counts); // {A=3, B=1}
~~~

`LinkedHashMap` được dùng để kết quả in theo thứ tự chèn trong ví dụ. Đây là **phép tổng hợp có chủ đích**, không phải hành vi của `List.copyOf`. Có thể công bố snapshot của map bằng `Map.copyOf(counts)` nếu cần, nhưng lưu ý Map copy không bảo đảm giữ iteration order trong khi Map giữ thông tin tần suất.

## 10. Lỗi thường gặp và cách sửa

| Nhận định hoặc cách dùng sai | Vì sao sai? | Cách đúng |
| --- | --- | --- |
| “`List.copyOf` tự xóa các phần tử trùng” | List cho phép duplicate và `copyOf` giữ các phần tử theo thứ tự duyệt. | Kiểm tra `size`/`frequency` sau sao chép; dùng `distinct` chỉ khi muốn loại trùng. |
| “Dùng `List.copyOf` thì số lần xuất hiện của `A` luôn là 1” | Nó không có quy tắc unique-key hay unique-element. | Nếu nguồn có 3 `A`, list copy cũng có 3 vị trí `A`. |
| “`Set.copyOf` và `List.copyOf` giữ cùng số lượng” | Set gộp các phần tử bằng nhau; List không gộp. | Chọn cấu trúc đúng hợp đồng. |
| “`Set.copyOf(list)` ném lỗi nếu list chứa duplicate” | Với `Set.copyOf`, duplicate được loại theo quy tắc giữ đại diện; `Set.of` mới từ chối đối số trùng. | Phân biệt `copyOf` và `of` của Set. |
| “Snapshot giữ nguyên trùng nên có thể sửa copy” | `copyOf` trả về list không sửa được. | Sửa nguồn mutable trước khi chốt, hoặc dùng một bản sao mutable riêng. |
| “Nguồn thêm phần tử trùng thì snapshot đã tạo cũng thêm theo” | `List.copyOf` không phải live view. | Muốn dữ liệu mới hãy tạo snapshot mới. |
| “Hai vị trí bằng nhau chứng tỏ chỉ có một object hoặc chỉ có hai object” | Bình đẳng giá trị (`equals`) và nhận dạng (`==`) là hai khái niệm khác nhau. | Dùng hợp đồng equals/identity phù hợp; `copyOf` không deep copy phần tử. |
| “`List.copyOf` có thể chứa `null` nếu nguồn chứa nhiều null” | `List.copyOf` từ chối mọi phần tử null. | Làm sạch null theo hợp đồng hoặc dùng kiểu snapshot khác cho phép null. |
| “`copyOf` luôn tạo một instance khác” | Có thể tái sử dụng unmodifiable input. | Không dựa vào identity của kết quả. |
| “Dùng `var` khiến list deduplicate” | `var` chỉ là suy luận kiểu của biến cục bộ. | Hiểu semantics của biểu thức `List.copyOf(...)`, không suy từ từ khóa khai báo. |

## 11. Cách chọn trong dự án thực tế

**Chọn `List.copyOf(source)` khi:**

1. Mọi lần xuất hiện đều là dữ liệu có ý nghĩa: sự kiện, lịch sử thao tác, dòng hóa đơn, item của một batch hoặc chuỗi ưu tiên.
2. Cần giữ **thứ tự duyệt** và vị trí của từng phần tử, kể cả khi các phần tử bằng nhau.
3. Muốn công bố kết quả không sửa được và độc lập về **cấu trúc** trước các thay đổi nguồn xảy ra sau khi chốt.
4. Nguồn và các phần tử không null, hoặc đã có chính sách xử lý null trước khi gọi.
5. Nắm rõ giới hạn shallow copy nếu phần tử là object có trạng thái mutable.

**Chọn cách khác khi:**

- Yêu cầu là giá trị **duy nhất**: `stream().distinct()` khi cần duy trì thứ tự của ordered stream, hoặc `Set.copyOf` khi cần membership, không cần index/tần suất.
- Yêu cầu là đếm số lần: giữ nguyên list để đếm, hoặc tổng hợp thành một map tần suất.
- Yêu cầu là live view quan sát sửa đổi nguồn: `Collections.unmodifiableList(source)` có ý nghĩa khác với bản sao.
- Yêu cầu là bản sao nhưng **vẫn sửa được**: `new ArrayList<>(source)` là lựa chọn hợp lý nếu muốn mutable copy.
- Yêu cầu là dữ liệu **bất biến sâu**: xây dựng immutable value objects/sao chép phần tử theo nhu cầu trước khi tạo snapshot.
- Yêu cầu cho phép `null` như một phần tử có ý nghĩa: cân nhắc một bản sao mutable có hỗ trợ null rồi bọc bằng `Collections.unmodifiableList`, nếu phù hợp hợp đồng.

### Checklist code review

- [ ] Số lần xuất hiện của mỗi giá trị có ý nghĩa không?
- [ ] Kết quả có cần giữ nguyên thứ tự/vị trí không?
- [ ] Nguồn là list có duplicate hay một set đã loại duplicate trước đó?
- [ ] Có `distinct()`, `Set.copyOf` hoặc bước tổng hợp nào vô tình làm mất dữ liệu không?
- [ ] Collection nguồn hoặc phần tử nào có thể là null không?
- [ ] Nguồn có thể bị sửa sau lúc copy, hoặc bị sửa đồng thời trong lúc copy không?
- [ ] Phần tử có mutable state cần xử lý snapshot sâu hơn không?
- [ ] Có test xác nhận duplicate, thứ tự, unmodifiable và snapshot độc lập cấu trúc không?

## 12. Bài tập tự kiểm tra

**Câu 1.** Kết quả của `List.copyOf(List.of("A", "B", "A"))` có bao nhiêu phần tử?

**Đáp án:** 3, theo thứ tự `[A, B, A]`; `"A"` có hai lần xuất hiện.

**Câu 2.** `Set.copyOf(List.of("A", "B", "A"))` có bao nhiêu phần tử? Có lỗi không?

**Đáp án:** 2 phần tử phân biệt, không lỗi chỉ vì duplicate; không nên dựa vào thứ tự in set.

**Câu 3.** `Set.of("A", "A")` thì sao?

**Đáp án:** Ném `IllegalArgumentException` vì các đối số bằng nhau.

**Câu 4.** Nếu `source = new ArrayList<>(List.of("A", "A")); copy = List.copyOf(source); source.add("A");` thì `copy` có bao nhiêu phần tử?

**Đáp án:** 2. `copy` không phản ánh thêm một phần tử trùng trong nguồn sau khi chụp.

**Câu 5.** Nguồn chứa hai vị trí cùng tham chiếu tới một object `Box`. `List.copyOf` còn bao nhiêu vị trí? Nếu sửa object, copy có thấy thay đổi không?

**Đáp án:** Vẫn 2 vị trí; cả hai có thể thấy trạng thái object mới, do sao chép nông, mặc dù cấu trúc copy không thay đổi.

**Câu 6.** `List.copyOf(Arrays.asList("A", null, "A"))` có giữ hai `"A"` và một `null` không?

**Đáp án:** Không tạo kết quả; ném `NullPointerException` vì có phần tử `null`. Duplicate `"A"` tự nó không gây lỗi.

**Câu 7.** `var x = List.copyOf(List.of("A", "A"));` có làm khác hành vi giữ trùng so với `List<String> x = ...` không?

**Đáp án:** Không. Cả hai có kiểu tĩnh `List<String>` và dữ liệu `[A, A]`. `var` không liên quan đến việc unique hay không.

**Câu 8.** Từ một list sự kiện `[LOGIN, LOGIN, LOGOUT]`, có nên dùng `Set.copyOf` chỉ để trả kết quả chỉ đọc không?

**Đáp án:** Không nếu cần giữ hai lần sự kiện `LOGIN`. Dùng `List.copyOf` để duy trì số lần xuất hiện và thứ tự.

## 13. Nguồn chính thức còn hiệu lực

- [Java SE 21 API — List.copyOf](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/List.html#copyOf(java.util.Collection)): nêu rõ trả list không sửa được chứa các phần tử theo iteration order, không phản ánh sửa đổi nguồn và không nhận null; `Since: 10`.
- [Java SE 26 API — List](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/List.html): hợp đồng List hiện đại vẫn cho phép phần tử trùng và `List.copyOf` vẫn được hỗ trợ.
- [Java SE 21 API — Set.copyOf](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/Set.html#copyOf(java.util.Collection)): quy tắc xử lý duplicate, null và dữ liệu đầu vào từ Collection.
- [Oracle — Creating Unmodifiable Lists, Sets, and Maps](https://docs.oracle.com/en/java/javase/21/core/creating-immutable-lists-sets-and-maps.html): giải thích sự khác nhau giữa `List` và `Set`, factory `of` và `copyOf`, và snapshot không sửa được.
- [Dev.java — Creating and Processing Data with Collection Factory Methods](https://dev.java/learn/api/collections-and-streams/collections-framework/factory-methods/): minh họa collection factory hiện hành, đặc biệt `copyOf` trên Java 10+.
- [Java SE 17 API — Collections.frequency](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collections.html#frequency(java.util.Collection,java.lang.Object)): cách đếm số lần phần tử xuất hiện mà không loại trùng.

**Ghi nhớ một câu:** `List.copyOf` tạo một **danh sách không sửa được nhưng vẫn cho phép các phần tử trùng**, giữ nguyên số lần và thứ tự của chúng theo iterator nguồn; chỉ những thao tác có chủ đích như `distinct()` hoặc chuyển sang `Set` mới loại trùng.