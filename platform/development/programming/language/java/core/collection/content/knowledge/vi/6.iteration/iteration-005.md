# ListIterator.add, set và remove

`ListIterator<E>` cho phép duyệt một `List` theo hai chiều và chỉnh sửa danh sách tại vị trí đang duyệt. Ba thao tác thay đổi có mục tiêu khác nhau:

- `add(e)`: chèn một phần tử mới vào khoảng trống tại con trỏ.
- `set(e)`: thay phần tử mà `next()` hoặc `previous()` vừa trả về.
- `remove()`: xóa lần xuất hiện mà `next()` hoặc `previous()` vừa trả về.

Muốn dùng đúng, cần theo dõi **vị trí con trỏ** và **phần tử vừa được trả về** như hai thông tin riêng. Chỉ nhìn vị trí con trỏ rồi đoán `set/remove` tác động bên trái hay bên phải sẽ dẫn đến lỗi khi đổi chiều duyệt.

Các ví dụ dùng Java 17 trở lên và một danh sách có thể chỉnh sửa, trừ phần riêng minh họa thao tác không được hỗ trợ.

## 1. Con trỏ nằm giữa các phần tử

Với danh sách A, B, C, có bốn vị trí con trỏ:

~~~text
| A B C
A | B C
A B | C
A B C |
~~~

Dấu `|` là con trỏ minh họa, không phải một phần tử trong danh sách.

Từ vị trí:

~~~text
A | B C
~~~

- `next()` sẽ trả B rồi dịch con trỏ sang phải.
- `previous()` sẽ trả A rồi dịch con trỏ sang trái.

Với danh sách dài `n`, có `n + 1` khoảng trống như vậy. Không có một “phần tử hiện tại” duy nhất mà mọi thao tác cùng tác động.

Tạo bộ duyệt:

~~~java
// Đoạn mã trong một phương thức; cần các import java.util tương ứng.
List<String> values = new ArrayList<>(List.of("A", "B", "C"));

ListIterator<String> start = values.listIterator();  // | A B C
ListIterator<String> middle = values.listIterator(1); // A | B C
ListIterator<String> end = values.listIterator(values.size()); // A B C |
~~~

Chỉ số truyền cho `listIterator(index)` là vị trí mà phần tử được trả bởi `next()` sẽ có, nếu còn phần tử. Vì con trỏ cuối dãy hợp lệ, `index == size()` được phép; đây không phải một chỉ số phần tử hợp lệ cho `get(index)`. Xem hợp đồng [List.listIterator trong Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html#listIterator(int)).

Những bộ duyệt ở trên có trạng thái riêng nhưng cùng tham chiếu một danh sách. Chúng không phải các bản sao dữ liệu; không nên dùng đồng thời để thay cấu trúc nguồn rồi cho rằng các bộ duyệt khác vẫn tự cập nhật trạng thái.

## 2. Chỉ số của con trỏ và phần tử vừa trả về

Hai phương thức quan sát hữu ích:

| Phương thức | Ý nghĩa |
| --- | --- |
| `nextIndex()` | Chỉ số của phần tử mà `next()` sẽ trả; bằng `size()` ở cuối. |
| `previousIndex()` | Chỉ số của phần tử mà `previous()` sẽ trả; bằng `-1` ở đầu. |

Ví dụ:

~~~text
Danh sách: A | B C
nextIndex()     = 1
previousIndex() = 0
~~~

Các chỉ số này mô tả khoảng trống tại con trỏ. Chúng không trực tiếp nói phần tử nào là mục tiêu của `set/remove`.

Hai chuỗi điều hướng có thể đưa đến cùng khoảng trống nhưng có mục tiêu chỉnh sửa khác nhau:

~~~text
Cách 1:
| A B C
next() trả A
A | B C
Phần tử vừa trả về: A

Cách 2:
A B | C
previous() trả B
A | B C
Phần tử vừa trả về: B
~~~

Cùng con trỏ `A | B C`, nhưng `set/remove` trong cách 1 nhắm A, còn trong cách 2 nhắm B.

Đây là điểm cốt lõi của bài. Mô tả chính thức của [ListIterator API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html) cũng phân biệt con trỏ với phần tử được trả về gần nhất.

## 3. add: chèn tại con trỏ, không cần đã duyệt một phần tử

Bắt đầu:

~~~text
P | Q
~~~

Gọi `add("X")`:

~~~text
P X | Q
~~~

Phần tử mới nằm:

- Sau phần tử mà `previous()` sẽ trả trước lúc chèn.
- Trước phần tử mà `next()` sẽ trả trước lúc chèn.
- Bên trái con trỏ sau khi chèn.

Vì vậy, sau `add("X")`:

- `next()` vẫn lấy Q nếu chưa có thao tác khác.
- `previous()` lấy X nếu chưa có thao tác khác.
- Kích thước danh sách tăng một.
- `nextIndex()` và `previousIndex()` đều tăng một so với trước khi chèn.

Ví dụ:

~~~java
List<String> values = new ArrayList<>(List.of("P", "Q"));
ListIterator<String> iterator = values.listIterator(1);

iterator.add("X");

System.out.println(values);               // [P, X, Q]
System.out.println(iterator.nextIndex());  // 2
System.out.println(iterator.previous());   // X
~~~

Dòng `previous()` cuối ví dụ đã làm con trỏ dịch sang trái. Khi suy luận bước tiếp theo, phải dùng vị trí mới, không tiếp tục coi nó đang đứng sau X.

### Add liên tiếp giữ thứ tự các lần chèn theo chiều tiến

~~~java
List<String> values = new ArrayList<>(List.of("P", "Q"));
ListIterator<String> iterator = values.listIterator(1);

iterator.add("X");
iterator.add("Y");

System.out.println(values);         // [P, X, Y, Q]
System.out.println(iterator.next()); // Q
~~~

Diễn biến:

~~~text
P | Q
P X | Q
P X Y | Q
~~~

Lần add thứ hai chèn tại con trỏ đã dịch sau X. Kết quả không phải P, Y, X, Q.

Không cần gọi `next/previous` giữa hai lần `add`. Có thể thêm ngay khi mới tạo bộ duyệt, ở đầu, giữa, cuối hoặc trong danh sách rỗng, miễn thao tác được danh sách hỗ trợ và phần tử hợp lệ.

### Add không đặt phần tử mới làm mục tiêu hợp lệ cho set/remove

Ngay sau một lần `add` thành công, không được lập tức gọi `set` hoặc `remove` dựa vào một phần tử đã được trả trước đó.

~~~java
iterator.add("X");

// iterator.set("Y"); // Trạng thái không hợp lệ nếu chưa next/previous lại.
// iterator.remove(); // Tương tự.
~~~

Nếu muốn sửa hoặc xóa X vừa chèn, có thể chủ động lấy nó bằng `previous()`, rồi thực hiện thao tác hợp lệ. Nhưng nhớ rằng thao tác điều hướng này cũng thay vị trí con trỏ.

## 4. set: thay đúng phần tử do next/previous trả về gần nhất

Ví dụ duyệt tiến:

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
ListIterator<String> iterator = values.listIterator();

String first = iterator.next(); // A
iterator.set("A*");

System.out.println(first);                // A
System.out.println(values);               // [A*, B, C]
System.out.println(iterator.nextIndex());  // 1
~~~

`set` thay phần tử trong danh sách. Biến `first` vẫn giữ tham chiếu hoặc giá trị đã nhận từ lời gọi trước, không tự được gán lại bởi thao tác của iterator.

`set`:

- Không thêm phần tử.
- Không xóa phần tử.
- Không đổi kích thước.
- Không dịch con trỏ.
- Cần một lần `next` hoặc `previous` thành công đủ điều kiện trước đó.

Không gọi `set` ngay khi mới tạo iterator, vì chưa có phần tử nào được trả để thay.

### Set sau khi duyệt lùi

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
ListIterator<String> iterator = values.listIterator(2); // A B | C

System.out.println(iterator.previous()); // B
iterator.set("B*");

System.out.println(values);              // [A, B*, C]
System.out.println(iterator.nextIndex()); // 1
~~~

B là mục tiêu vì `previous()` vừa trả B. Con trỏ sau `previous` là A | B C; `set` không dịch nó.

Nhìn vị trí con trỏ mà luôn thay phần tử bên trái sẽ sai trong trường hợp này. Phần tử vừa trả bởi `previous` đang nằm bên phải con trỏ.

### Có thể set nhiều lần

~~~java
ListIterator<String> iterator = values.listIterator();

iterator.next();
iterator.set("first replacement");
iterator.set("second replacement");
~~~

Nếu các phần tử thay thế đều hợp lệ và iterator hỗ trợ, lần `set` thứ hai vẫn hợp lệ. `set` không tự xóa quyền tác động tới lần xuất hiện đã được `next/previous` xác định.

Sau một hoặc nhiều lần `set`, `remove` cũng vẫn có thể xóa lần xuất hiện đó, miễn chưa có `add/remove` làm mất điều kiện.

### Thay phần tử khác với sửa đối tượng bên trong

Giả sử phần tử là một đối tượng có thể thay đổi:

- `iterator.set(otherObject)` thay tham chiếu được danh sách giữ ở lần xuất hiện đó.
- Gọi phương thức cập nhật trên đối tượng vừa lấy là sửa nội dung đối tượng, không gọi `ListIterator.set`.

Một danh sách không cho thay phần tử có thể vẫn chứa các đối tượng bên trong có thể thay đổi. Hai mức khả năng chỉnh sửa cần được xem xét riêng.

## 5. remove: xóa lần xuất hiện vừa được trả về

Ví dụ sau `next()`:

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
ListIterator<String> iterator = values.listIterator();

System.out.println(iterator.next()); // A
iterator.remove();

System.out.println(values);              // [B, C]
System.out.println(iterator.nextIndex()); // 0
System.out.println(iterator.next());      // B
~~~

A được trả rồi bị xóa. Con trỏ được điều chỉnh để B vẫn là phần tử tiếp theo; mã không cần tự giảm một biến chỉ số bên ngoài để tránh bỏ qua B.

Diễn biến:

~~~text
| A B C
next() trả A -> A | B C
remove()     -> | B C
~~~

### Sau previous: mục tiêu nằm bên phải con trỏ

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "C"));
ListIterator<String> iterator = values.listIterator(2); // A B | C

System.out.println(iterator.previous()); // B
iterator.remove();

System.out.println(values);              // [A, C]
System.out.println(iterator.nextIndex()); // 1
System.out.println(iterator.next());      // C
~~~

Diễn biến:

~~~text
A B | C
previous() trả B -> A | B C
remove()         -> A | C
~~~

Sau `previous`, con trỏ đã lùi. Xóa B không phải lùi con trỏ thêm một bước; C trở thành phần tử tiếp theo ở khoảng trống hiện tại.

### Remove không tìm theo equals

~~~java
List<String> values = new ArrayList<>(List.of("A", "B", "A"));
ListIterator<String> iterator = values.listIterator(values.size());

iterator.previous(); // Trả lần xuất hiện A cuối danh sách.
iterator.remove();

System.out.println(values); // [A, B]
~~~

Iterator xóa **lần xuất hiện đã được trả**, không gọi một phép tìm lại từ đầu theo giá trị A.

Nếu dùng `values.remove("A")`, ý nghĩa là xóa một phần tử khớp giá trị theo hợp đồng của danh sách; với danh sách này, đó là A đầu tiên. Ngoài việc xóa sai lần xuất hiện mong muốn, sửa cấu trúc trực tiếp qua danh sách còn có thể làm iterator đang dùng không hợp lệ.

`ListIterator.remove()` không có tham số và trả `void`. Không nhầm nó với `List.remove(index)` hoặc `List.remove(Object)`.

### Chỉ remove một lần cho một lần điều hướng

~~~java
iterator.next();
iterator.remove();

// iterator.remove(); // IllegalStateException nếu chưa next/previous lại.
~~~

Sau khi xóa mục tiêu, không còn mục tiêu hợp lệ từ lần điều hướng đó. Muốn xóa tiếp, phải lấy một phần tử tiếp theo hoặc trước đó một cách hợp lệ.

## 6. Bảng trạng thái của ba thao tác

Bảng giả định iterator hỗ trợ thao tác tương ứng, phần tử truyền vào hợp lệ và các bước được nói tới đều hoàn tất thành công.

| Trạng thái gần nhất | add | set | remove |
| --- | --- | --- | --- |
| Mới tạo, chưa next/previous | Được | Không có mục tiêu hợp lệ | Không có mục tiêu hợp lệ |
| Vừa next hoặc previous | Được | Được trên phần tử vừa trả | Được trên phần tử vừa trả |
| Vừa set, chưa add/remove sau lần điều hướng | Được | Được tiếp trên cùng lần xuất hiện | Được trên cùng lần xuất hiện |
| Vừa add, chưa next/previous lại | Được tiếp | Không hợp lệ | Không hợp lệ |
| Vừa remove, chưa next/previous lại | Được | Không hợp lệ | Không hợp lệ |

Quy tắc ngắn để theo dõi:

1. `next/previous` thành công chọn một mục tiêu cho `set/remove`.
2. `set` thay mục tiêu nhưng không làm mất điều kiện tiếp tục tác động tới lần xuất hiện đó.
3. `add` và `remove` thành công làm mất mục tiêu chỉnh sửa cũ.
4. `hasNext`, `hasPrevious`, `nextIndex` và `previousIndex` chỉ quan sát; chúng không tự chọn một mục tiêu mới.

Không dùng việc một thao tác ném lỗi làm cách điều khiển trạng thái bình thường. Đặc biệt, với một triển khai tùy biến hoặc thao tác không được hỗ trợ, không suy rộng toàn bộ trạng thái sau lỗi chỉ từ một lần chạy trên ArrayList.

### Điều hướng xen kẽ có thể trả lại cùng phần tử

~~~java
List<String> values = new ArrayList<>(List.of("A", "B"));
ListIterator<String> iterator = values.listIterator();

System.out.println(iterator.next());     // A
System.out.println(iterator.previous()); // A
iterator.set("A*");

System.out.println(values); // [A*, B]
~~~

`previous` đi ngược qua chính phần tử `next` vừa vượt qua. Đây không phải hai phần tử khác nhau. Thao tác điều hướng thành công gần nhất là `previous`, nên trạng thái con trỏ và mục tiêu phải được đọc theo bước đó.

## 7. add, set và remove đều là thao tác tùy chọn

Có phương thức trong interface không có nghĩa mọi nguồn đều cho phép thực hiện.

| Nguồn thường gặp | set qua list iterator | add/remove qua list iterator |
| --- | --- | --- |
| `ArrayList` có thể sửa | Hỗ trợ | Hỗ trợ |
| `LinkedList` có thể sửa | Hỗ trợ | Hỗ trợ |
| Danh sách từ `Arrays.asList(array)` | Hỗ trợ thay phần tử; phản ánh về mảng | Không hỗ trợ đổi kích thước |
| Danh sách từ `List.of(...)` hoặc `List.copyOf(...)` | Không hỗ trợ | Không hỗ trợ |
| Góc nhìn `Collections.unmodifiableList(...)` | Không hỗ trợ qua góc nhìn | Không hỗ trợ qua góc nhìn |

Danh sách có kích thước cố định không đồng nghĩa hoàn toàn không thể thay phần tử. `Arrays.asList` là ví dụ quan trọng.

Chương trình đầy đủ ở dưới kiểm chứng:

- `set` thay được một phần tử của danh sách có mảng phía sau.
- Mảng gốc cũng thấy giá trị mới.
- `add/remove` trên nguồn đó ném `UnsupportedOperationException`.
- `set` trên iterator của `List.of` cũng không được hỗ trợ.

Nếu không cần giữ nguồn có khả năng hạn chế, có thể tạo bản sao có thể sửa:

~~~java
List<String> editable = new ArrayList<>(source);
ListIterator<String> iterator = editable.listIterator();
~~~

Bản sao này chứa các tham chiếu phần tử từ nguồn; nó không tự sao chép sâu nội dung từng đối tượng.

## 8. Phân biệt lỗi trạng thái, lỗi khả năng và lỗi dữ liệu

| Tình huống | Loại lỗi cần phân biệt |
| --- | --- |
| set/remove khi chưa có phần tử trả về hợp lệ | `IllegalStateException` trên iterator hỗ trợ thao tác và kiểm tra trạng thái tương ứng. |
| Thao tác thay đổi không được triển khai hỗ trợ | `UnsupportedOperationException`. |
| Không còn phần tử ở chiều next/previous | `NoSuchElementException`. |
| Vị trí bắt đầu listIterator nằm ngoài miền cho phép | `IndexOutOfBoundsException`. |
| Giá trị thêm/thay không đáp ứng giới hạn kiểu hoặc nội dung của nguồn | Có thể có ngoại lệ tương ứng như `ClassCastException` hoặc `IllegalArgumentException`, tùy hợp đồng. |
| Nguồn cấm null nhưng truyền null | Phải theo chính sách và ngoại lệ của nguồn; không tự giả định null luôn được phép. |

Không viết kiểm thử đòi một ngoại lệ cụ thể theo một thứ tự ưu tiên tự đoán khi cùng lúc vi phạm nhiều điều kiện, chẳng hạn iterator vừa không hỗ trợ thao tác vừa chưa có mục tiêu hợp lệ.

Trong chương trình minh họa, các lỗi trạng thái dùng `ArrayList` hỗ trợ thay đổi, còn các lỗi không hỗ trợ được kiểm tra riêng trên nguồn có giới hạn. Cách tách đó giúp biết chính xác điều gì đang được chứng minh.

## 9. Ứng dụng: duyệt, xóa, thay và chèn trong một lượt

Giả sử cần xử lý danh sách chuỗi:

- Xóa chuỗi rỗng.
- Chuyển các chuỗi còn lại sang chữ hoa theo quy tắc trung lập của ví dụ.
- Thêm ký hiệu `"|"` sau mỗi chuỗi còn lại.

Ký hiệu trong ví dụ này là dữ liệu thật, khác với con trỏ được dùng trong sơ đồ.

~~~java
// Cần import java.util.Locale cùng các import danh sách.
List<String> tokens = new ArrayList<>(List.of("a", "", "b"));
ListIterator<String> editor = tokens.listIterator();

while (editor.hasNext()) {
    String token = editor.next();
    if (token.isEmpty()) {
        editor.remove();
    } else {
        editor.set(token.toUpperCase(Locale.ROOT));
        editor.add("|");
    }
}

System.out.println(tokens); // [A, |, B, |]
~~~

Vì sao không lặp vô hạn trên các ký hiệu mới chèn?

Sau `next()` lấy chuỗi gốc, con trỏ đã đứng sau nó. `add("|")` chèn ký hiệu trước con trỏ rồi để con trỏ ở sau ký hiệu. Lần `next()` tiếp theo lấy phần tử gốc phía sau, không quay lại ký hiệu vừa chèn.

Ở nhánh chuỗi rỗng, `remove()` xóa đúng phần tử vừa lấy và điều chỉnh bộ duyệt để không bỏ qua phần tử tiếp theo.

Ở nhánh còn lại, phải gọi `set` trước `add`. Nếu đổi thành `add` rồi `set`, lần `add` sẽ làm mất mục tiêu chỉnh sửa cũ, nên `set` không còn hợp lệ cho tới khi điều hướng lại.

Ví dụ giả định các token không `null`. Nếu miền dữ liệu cho phép `null`, cần định nghĩa một nhánh xử lý tương ứng trước khi gọi `isEmpty`.

## 10. Chương trình hoàn chỉnh

Lưu thành **ListIteratorMutationDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.ListIterator;
import java.util.Locale;

public class ListIteratorMutationDemo {
    public static void main(String[] args) {
        List<String> values = new ArrayList<>(List.of("A", "B", "C"));
        ListIterator<String> iterator = values.listIterator();
        show("Start", values, iterator);

        expectIllegalState("set before navigation",
                () -> iterator.set("bad"));
        expectIllegalState("remove before navigation", iterator::remove);

        System.out.println("next -> " + iterator.next());
        iterator.set("A1");
        iterator.set("A2");
        show("After repeated set", values, iterator);

        iterator.remove();
        show("After remove following next", values, iterator);
        expectIllegalState("remove twice", iterator::remove);

        iterator.add("X");
        show("After add X", values, iterator);
        expectIllegalState("set immediately after add",
                () -> iterator.set("bad"));
        expectIllegalState("remove immediately after add", iterator::remove);

        System.out.println("previous -> " + iterator.previous());
        iterator.set("Y");
        show("After set following previous", values, iterator);

        iterator.remove();
        show("After remove following previous", values, iterator);
        System.out.println("next after removing Y -> " + iterator.next());

        List<String> insertions = new ArrayList<>(List.of("P", "Q"));
        ListIterator<String> insertion = insertions.listIterator(1);
        insertion.add("X");
        insertion.add("Y");
        show("Two adds at the same gap", insertions, insertion);
        System.out.println("next after adds -> " + insertion.next());
        System.out.println("previous after next -> " + insertion.previous());
        System.out.println("previous again -> " + insertion.previous());
        insertion.remove();
        show("After removing returned Y", insertions, insertion);

        List<String> duplicates =
                new ArrayList<>(List.of("A", "B", "A"));
        ListIterator<String> last = duplicates.listIterator(duplicates.size());
        last.previous();
        last.remove();
        System.out.println("Remove last returned occurrence = " + duplicates);

        String[] array = {"A", "B"};
        List<String> fixed = Arrays.asList(array);
        ListIterator<String> fixedSet = fixed.listIterator();
        fixedSet.next();
        fixedSet.set("A*");
        System.out.println("Fixed-size set = " + fixed);
        System.out.println("Backing array = " + Arrays.toString(array));

        expectUnsupported("fixed-size add",
                () -> fixed.listIterator().add("X"));

        ListIterator<String> fixedRemove = fixed.listIterator();
        fixedRemove.next();
        expectUnsupported("fixed-size remove", fixedRemove::remove);

        ListIterator<String> readOnly = List.of("A").listIterator();
        readOnly.next();
        expectUnsupported("unmodifiable set", () -> readOnly.set("X"));

        List<String> tokens = new ArrayList<>(List.of("a", "", "b"));
        ListIterator<String> editor = tokens.listIterator();
        while (editor.hasNext()) {
            String token = editor.next();
            if (token.isEmpty()) {
                editor.remove();
            } else {
                editor.set(token.toUpperCase(Locale.ROOT));
                editor.add("|");
            }
        }
        System.out.println("Edited tokens = " + tokens);
    }

    private static void show(
            String label,
            List<String> values,
            ListIterator<String> iterator
    ) {
        System.out.println(label + " = " + values
                + "; nextIndex=" + iterator.nextIndex()
                + "; previousIndex=" + iterator.previousIndex());
    }

    private static void expectIllegalState(String label, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("Expected IllegalStateException");
        } catch (IllegalStateException exception) {
            System.out.println(label + " -> "
                    + exception.getClass().getSimpleName());
        }
    }

    private static void expectUnsupported(String label, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("Expected UnsupportedOperationException");
        } catch (UnsupportedOperationException exception) {
            System.out.println(label + " -> "
                    + exception.getClass().getSimpleName());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~shell
javac --release 17 -encoding UTF-8 ListIteratorMutationDemo.java
java ListIteratorMutationDemo
~~~

Stdout:

~~~text
Start = [A, B, C]; nextIndex=0; previousIndex=-1
set before navigation -> IllegalStateException
remove before navigation -> IllegalStateException
next -> A
After repeated set = [A2, B, C]; nextIndex=1; previousIndex=0
After remove following next = [B, C]; nextIndex=0; previousIndex=-1
remove twice -> IllegalStateException
After add X = [X, B, C]; nextIndex=1; previousIndex=0
set immediately after add -> IllegalStateException
remove immediately after add -> IllegalStateException
previous -> X
After set following previous = [Y, B, C]; nextIndex=0; previousIndex=-1
After remove following previous = [B, C]; nextIndex=0; previousIndex=-1
next after removing Y -> B
Two adds at the same gap = [P, X, Y, Q]; nextIndex=3; previousIndex=2
next after adds -> Q
previous after next -> Q
previous again -> Y
After removing returned Y = [P, X, Q]; nextIndex=2; previousIndex=1
Remove last returned occurrence = [A, B]
Fixed-size set = [A*, B]
Backing array = [A*, B]
fixed-size add -> UnsupportedOperationException
fixed-size remove -> UnsupportedOperationException
unmodifiable set -> UnsupportedOperationException
Edited tokens = [A, |, B, |]
~~~

Hai hàm `expectIllegalState` và `expectUnsupported` trong chương trình chỉ phục vụ minh họa: nếu thao tác không ném ngoại lệ như mong đợi, chương trình ném `AssertionError` để không lặng lẽ báo một kết quả sai. Không cần sao chép cách bắt lỗi này vào một luồng xử lý nghiệp vụ bình thường.

## 11. Đọc trạng thái trong chương trình

### Mới tạo

Danh sách A, B, C có con trỏ ở đầu. `nextIndex == 0`, `previousIndex == -1`. Chưa có mục tiêu, nên `set/remove` không hợp lệ.

### Next, set nhiều lần rồi remove

`next` trả A. Hai lần `set` vẫn tác động cùng vị trí, cuối cùng danh sách là A2, B, C và con trỏ còn đứng sau A2.

`remove` xóa lần xuất hiện đó. B, C còn lại, con trỏ trở về khoảng trống đầu dãy. Lần remove tiếp theo không có mục tiêu.

### Add rồi previous

`add("X")` tạo X, B, C và con trỏ ở sau X. Không được set/remove ngay.

`previous` trả X và đưa con trỏ về đầu. Từ đây set Y là hợp lệ, rồi remove xóa Y. B vẫn là phần tử kế tiếp.

### Hai lần add trong P, Q

Bộ duyệt ban đầu ở P | Q. Thêm X rồi Y tạo P, X, Y | Q. `next` trả Q. `previous` ngay sau đó lại trả Q; `previous` thêm lần nữa mới trả Y.

`remove` xóa Y chứ không xóa Q, vì mục tiêu là phần tử của lời gọi điều hướng thành công gần nhất. Sau xóa, danh sách là P, X | Q.

### Phần tử lặp

Bộ duyệt từ cuối trả A cuối trong A, B, A. Remove xóa lần xuất hiện cuối, để lại A, B. Nó không tìm một A khác từ đầu danh sách.

### Các nguồn có giới hạn

`Arrays.asList` cho thay A thành A*, đồng thời mảng gốc đổi. Nhưng thêm/xóa làm đổi kích thước không được hỗ trợ. Iterator của `List.of` từ chối cả việc thay A bằng X.

### Một lượt chỉnh sửa token

Thứ tự next → set → add hoặc next → remove đúng với điều kiện trạng thái, nên đầu vào a, chuỗi rỗng, b được biến thành A, ký hiệu, B, ký hiệu.

## 12. Sửa qua iterator và sửa trực tiếp qua List là hai đường khác nhau

Khi dùng iterator của một danh sách thông thường có cơ chế phát hiện thay đổi, nên thực hiện chỉnh sửa cần thiết bằng chính iterator đang duyệt, trong phạm vi nó hỗ trợ.

Không thay thế:

~~~java
iterator.remove();
~~~

bằng:

~~~java
values.remove(value);
~~~

rồi mặc nhiên cho rằng iterator vẫn hợp lệ. Sửa cấu trúc nguồn từ đường khác có thể khiến nó phát hiện thay đổi và ném `ConcurrentModificationException`.

Ngoại lệ này không phải công cụ đồng bộ, và không có nghĩa mọi lỗi truy cập đồng thời đều được phát hiện ngay. Cũng không có bảo đảm rằng sửa qua một iterator làm mọi iterator khác đang giữ cùng nguồn tự điều chỉnh đúng trạng thái.

`set` thường không thay kích thước, nhưng “không thay cấu trúc” không có nghĩa tự an toàn với nhiều luồng hay không có tác động tới thuật toán đang đọc nguồn.

Nếu cần nhiều luồng, phải chọn mô hình đồng bộ hoặc cấu trúc dữ liệu có hợp đồng phù hợp. Ví dụ, không suy ra iterator của một danh sách dùng cơ chế ảnh chụp sẽ hỗ trợ add/set/remove chỉ vì nó là `ListIterator`.

### Không dùng forEachRemaining như nơi thay đổi tùy ý

Với yêu cầu thay đổi danh sách theo từng phần tử, vòng lặp tường minh giúp theo dõi chính xác mục tiêu và thứ tự thao tác. Không dựa vào `forEachRemaining` rồi tùy ý gọi các phương thức thay đổi trong callback; hợp đồng của iterator có các giới hạn riêng về sửa nguồn trong quá trình đó.

Bài này chỉ xét chỉnh sửa giữa những lời gọi `next/previous` mà người viết mã điều khiển trực tiếp.

## 13. Hiệu năng: đúng vị trí không đồng nghĩa cùng chi phí

`ListIterator` giúp thực hiện thuật toán theo lượt duyệt, nhưng không làm mọi lớp danh sách có cùng chi phí:

- Với `ArrayList`, thêm/xóa ở giữa có thể cần dịch nhiều phần tử.
- Với `LinkedList`, khi đã có iterator ở đúng nút, thao tác liên kết có đặc điểm khác; việc tìm đến vị trí ban đầu vẫn có chi phí.
- Thay phần tử không phải cùng một bài toán với đổi kích thước.

Không chọn `LinkedList` chỉ vì thấy mã có `add/remove`, cũng không khẳng định dùng iterator sẽ tự làm mọi thao tác giữa danh sách thành hằng số.

Với chỉnh sửa hàng loạt, cân nhắc liệu tạo danh sách kết quả mới, dùng thao tác chuyên dụng hoặc gom thay đổi có rõ và hiệu quả hơn không. Chọn sau khi đã xác định kích thước, mẫu duyệt và yêu cầu giữ nguồn.

## 14. Cách tự kiểm tra một chuỗi thao tác

Sau mỗi bước, ghi bốn thông tin:

1. Nội dung và kích thước danh sách.
2. Khoảng trống con trỏ, hoặc `nextIndex/previousIndex`.
3. Phần tử do next/previous thành công gần nhất trả về.
4. Có add/remove thành công nào từ lần điều hướng đó làm mất mục tiêu hay chưa.

Dùng dữ liệu có phần tử trùng để phát hiện việc xóa theo giá trị thay vì theo lần xuất hiện. Dùng cả hướng tiến và hướng lùi để phát hiện việc coi mục tiêu luôn nằm bên trái con trỏ.

Các trường hợp biên nên có:

- Danh sách rỗng rồi add.
- Con trỏ đầu và con trỏ cuối.
- Chỉ có một phần tử rồi remove thành rỗng.
- Set ngay khi mới tạo.
- Set nhiều lần sau một lần điều hướng.
- Remove sau set.
- Remove hai lần.
- Set/remove ngay sau add.
- Add nhiều lần liên tiếp.
- Previous ngay sau add.
- Next rồi previous liên tiếp.
- Nguồn chỉ hỗ trợ một phần thao tác thay đổi.

Không tự thử ghi đè dữ liệu người dùng để quan sát ngoại lệ; các ca học tập nên dùng danh sách nhỏ tạo mới như chương trình trong bài.

## 15. Lỗi thường gặp

| Lỗi | Nguyên nhân | Cách suy luận đúng |
| --- | --- | --- |
| Set ngay khi vừa tạo iterator | Chưa có phần tử trả về gần nhất | Điều hướng thành công trước khi sửa. |
| Coi set/remove luôn tác động phần tử bên trái con trỏ | Nhầm con trỏ với mục tiêu | Theo dõi lời gọi next hoặc previous cuối. |
| Mong next trả phần tử vừa add | Add đặt phần tử mới ở trước con trỏ sau thao tác | Previous mới quay lại phần tử vừa chèn nếu chưa có bước khác. |
| Gọi set ngay sau add | Mục tiêu cũ đã bị làm mất hiệu lực | Điều hướng lại, hoặc set trước add nếu đó là ý định. |
| Cho rằng set chỉ được gọi một lần | Nhầm quy tắc của remove với set | Set có thể lặp khi chưa add/remove làm mất điều kiện. |
| Remove liên tiếp mà không điều hướng | Lần xuất hiện mục tiêu đã bị xóa | Lấy phần tử tiếp theo hoặc trước đó trước khi xóa tiếp. |
| Dùng list.remove(value) thay iterator.remove | Đổi ngữ nghĩa và đường sửa nguồn | Xóa đúng lần xuất hiện qua iterator đang duyệt. |
| Cứ thấy ListIterator là cho rằng đủ add/set/remove | Các thao tác là tùy chọn | Kiểm tra khả năng của danh sách và iterator cụ thể. |
| Tự sửa một biến chỉ số sau khi iterator.remove | Quản lý hai mô hình tiến độ dễ lệch nhau | Để iterator quản lý vị trí duyệt, chỉ dùng chỉ số ngoài khi thật sự cần. |
| Dùng khả năng sửa qua iterator làm bảo đảm an toàn nhiều luồng | Nhầm trạng thái lượt duyệt với đồng bộ | Thiết kế truy cập đồng thời theo hợp đồng riêng. |

## 16. Thực hành

1. Với A, B, C và con trỏ A | B C, hãy tạo hai chuỗi điều hướng có cùng con trỏ nhưng mục tiêu set khác nhau.
2. Dự đoán kết quả: add X, add Y, previous, remove. Ghi danh sách và con trỏ sau từng bước.
3. Lấy một phần tử, set hai lần rồi remove. Giải thích vì sao hợp lệ, trong khi remove hai lần lại không hợp lệ.
4. Bắt đầu từ cuối A, B, A và xóa A do previous trả về. So sánh với ý nghĩa của remove theo giá trị trên List.
5. Viết thuật toán thay chuỗi không rỗng bằng dạng đã chuẩn hóa, xóa chuỗi rỗng và chèn một nhãn sau mỗi chuỗi được giữ. Kiểm tra nhãn có bị duyệt lại theo chiều tiến không.
6. Chạy cùng ý tưởng trên ArrayList, LinkedList, Arrays.asList và List.of; tách khả năng thao tác khỏi chi phí và trạng thái hợp lệ.
7. Viết các ca kiểm thử cho add vào danh sách rỗng, remove phần tử duy nhất và đổi chiều next/previous.

Trước khi gọi một thao tác thay đổi, hãy xác định nó tác động tới **khoảng trống con trỏ** hay **lần xuất hiện vừa được trả về**. Sau đó kiểm tra nguồn có hỗ trợ thao tác và trạng thái có hợp lệ không. Hai câu hỏi này giải thích phần lớn hành vi của add, set và remove.
