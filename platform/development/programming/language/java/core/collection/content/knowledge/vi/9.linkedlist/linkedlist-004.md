# Chèn và xóa tại vị trí đã có ListIterator trong LinkedList

## 1. Vì sao “đã có ListIterator” là điều kiện quan trọng?

LinkedList lưu phần tử bằng các nút liên kết đôi. Thay đổi liên kết gần một nút đã biết là thao tác cục bộ, nhưng tìm nút theo một chỉ số ở giữa có thể cần đi qua nhiều nút.

Vì vậy, hai công việc khác nhau cần được tách ra:

1. Đi đến vị trí cần sửa.
2. Chèn hoặc xóa tại vị trí đã đến.

Nếu đang duyệt bằng `ListIterator`, iterator đã giữ thông tin về vị trí quanh con trỏ. Dùng `iterator.add(...)` hoặc `iterator.remove()` tận dụng vị trí đó, thay vì lại gọi `list.add(index, ...)` hay `list.remove(index)` để tìm nút theo chỉ số.

Lợi ích không chỉ ở chi phí tìm kiếm. ListIterator còn quy định cách vừa duyệt vừa sửa danh sách mà vẫn giữ một trạng thái con trỏ hợp lệ.

Nhưng cần hiểu chính xác:

- `add` chèn tại khoảng giữa hai phần tử, theo vị trí con trỏ.
- `remove` không xóa một “phần tử tại con trỏ” tùy ý; nó xóa phần tử vừa được `next` hoặc `previous` trả về.
- Không phải cứ có iterator trong tay là có thể gọi remove ngay.

Các ví dụ dùng API có trong Java 17 và đối tượng thực tế là LinkedList. Hợp đồng ListIterator áp dụng rộng hơn, còn chi phí thao tác cục bộ được phân tích riêng cho LinkedList. [ListIterator Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html), [LinkedList.listIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html#listIterator(int)).

## 2. Con trỏ nằm giữa các phần tử

ListIterator không có một “phần tử hiện tại” làm điểm neo chung cho mọi phương thức. Con trỏ nằm giữa phần tử mà previous sẽ trả về và phần tử mà next sẽ trả về.

Với `[A, B, C]`, có bốn vị trí con trỏ:

```text
| A B C
A | B C
A B | C
A B C |
```

Dấu `|` chỉ dùng để minh họa, không phải phần tử trong danh sách.

Đoạn minh họa bên trong một phương thức, cần import `java.util.List`, `java.util.LinkedList` và `java.util.ListIterator`:

```java
List<String> values = new LinkedList<>(List.of("A", "B", "C"));
ListIterator<String> iterator = values.listIterator(1);

// A | B C
// iterator.nextIndex() = 1
// iterator.previousIndex() = 0
```

Chỉ số truyền cho `listIterator(index)` là vị trí mà next sẽ đọc nếu còn phần tử:

- `listIterator(0)`: đứng trước phần tử đầu.
- `listIterator(size())`: đứng sau phần tử cuối.
- `listIterator()`: tương ứng vị trí bắt đầu.
- Chỉ số hợp lệ là `0 <= index <= size()`.

Cho phép vị trí bằng size không có nghĩa có phần tử tại chỉ số size. Ở cuối, `hasNext()` là false và `next()` gây `NoSuchElementException`.

`nextIndex()` bằng size khi ở cuối. `previousIndex()` bằng -1 khi ở đầu. Các phương thức hỏi chỉ số hoặc `hasNext/hasPrevious` không tự di chuyển con trỏ và không chọn một phần tử để remove.

## 3. next và previous xác định phần tử nào vừa được trả về

Từ vị trí:

```text
A | B C
```

Gọi `next()`:

```text
Trả về: B
Sau đó: A B | C
```

Gọi `previous()` ngay sau đó:

```text
Trả về: B
Sau đó: A | B C
```

Hai lời gọi ngược hướng liên tiếp có thể trả cùng phần tử. Điều này đúng với mô hình con trỏ giữa phần tử; không phải iterator tự bỏ qua một nút hoặc bị lặp do lỗi.

Cần theo dõi riêng hai trạng thái:

- **Vị trí con trỏ**: xác định nơi chèn và phần tử kế tiếp ở mỗi hướng.
- **Phần tử vừa được trả về**: xác định mục tiêu của remove hoặc set khi trạng thái cho phép.

Đó là lý do một lời gọi `add` và một lời gọi `remove` không thể được hiểu bằng cùng câu “sửa phần tử ở vị trí hiện tại”.

## 4. add chèn trước phần tử mà next sẽ trả về

Từ `A | B C`, gọi `iterator.add("X")`:

```text
Trước: A | B C
Sau:   A X | B C
```

Các hệ quả:

- X được chèn giữa A và B.
- next tiếp theo vẫn trả B.
- previous tiếp theo trả X.
- Size tăng một.
- `nextIndex()` và `previousIndex()` cùng tăng một so với trước khi chèn.
- Add không cần có một lời gọi next hoặc previous trước đó.

Vì vậy, có thể chèn vào danh sách rỗng hoặc chèn ngay đầu/cuối qua một ListIterator ở biên phù hợp.

### 4.1. Chèn nhiều phần tử giữ thứ tự gọi

Từ `A | B C`:

```java
iterator.add("X");
iterator.add("Y");
```

Kết quả:

```text
A X Y | B C
```

Con trỏ đi sau phần tử vừa chèn, nên thứ tự các lần add được giữ. Nó khác với việc lặp `list.add(sameIndex, value)` tại một chỉ số cố định, vốn có thể đặt phần tử mới trước phần tử vừa chèn trước đó.

Nếu có một batch độc lập và ổn định cần chèn ở đây, có thể gọi add lần lượt cho từng phần tử. Không dùng chính danh sách đang sửa làm nguồn duyệt đồng thời cho batch mà không có chính sách riêng.

### 4.2. Add làm mất quyền remove/set trên lần trả về cũ

Giả sử đã next trả B rồi gọi add. Khi đó không được tiếp tục remove hoặc set dựa trên B đã trả trước add. Add thiết lập lại trạng thái lựa chọn phần tử.

Muốn remove phần tử X vừa chèn từ vị trí `A X | B C`, có thể gọi previous để thật sự trả X, rồi remove. Không gọi remove ngay sau add và trông chờ nó tự hiểu cần xóa X.

Theo hợp đồng, `ListIterator.add(E)` trả `void`; nó không trả phần tử mới, chỉ số chèn hay cờ thành công.

## 5. remove xóa phần tử vừa được next/previous trả về

### 5.1. Muốn xóa phần tử kế tiếp ở phía trước

Từ `A | B C`:

```java
String removed = iterator.next(); // B
iterator.remove();
```

Kết quả:

```text
A | C
```

Iterator remove trả `void`. Nếu cần giữ giá trị bị xóa, nhận giá trị từ next hoặc previous trước khi gọi remove.

Sau khi xóa B, next tiếp theo trả C. Không cần tự tăng chỉ số hoặc gọi thêm một next chỉ để “bù” cho việc xóa; làm vậy có thể bỏ qua C.

### 5.2. Muốn xóa phần tử phía sau con trỏ

Từ `A B | C`:

```java
String removed = iterator.previous(); // B
iterator.remove();
```

Kết quả cũng là:

```text
A | C
```

Nhưng đường di chuyển khác: previous đã đưa con trỏ về trước B rồi remove xóa B. Đối với nextIndex:

- Remove sau next làm nextIndex giảm một so với ngay trước remove.
- Remove sau previous không giảm nextIndex thêm lần nữa; previous đã đưa chỉ số về phía trước.

Cách dễ kiểm tra là theo dõi phần tử mà next sẽ trả về, không chỉ cộng/trừ số theo trí nhớ.

### 5.3. Remove chọn đúng lần trả về, không tìm theo giá trị

`iterator.remove()` không nhận chỉ số hoặc đối tượng cần tìm. Nó xóa đúng phần tử vừa được trả về trong lượt duyệt.

Nếu danh sách có nhiều giá trị bằng nhau, iterator không quay lại tìm lần xuất hiện đầu như `list.remove(Object)`. Điều này hữu ích khi cần xóa đúng một lần xuất hiện tại vị trí đang xử lý.

Nếu next trả `null` trên LinkedList, vẫn có một phần tử vừa được duyệt. Remove sau đó hợp lệ nếu chưa có add/remove xen giữa; giá trị phần tử bằng null không đồng nghĩa “chưa chọn phần tử”.

## 6. Quy tắc trạng thái của add, remove và set

Set được đưa vào bảng để phân biệt thay phần tử với chèn/xóa. `iterator.set(value)` thay phần tử vừa được next/previous trả về, không đổi size.

| Trạng thái sau thao tác gần nhất có liên quan | Có thể add? | Có thể remove? | Có thể set? |
|---|---|---|---|
| Vừa tạo iterator, chưa next/previous | Có | Không | Không |
| Next hoặc previous vừa trả phần tử thành công | Có | Có, một lần cho lựa chọn đó | Có |
| Vừa remove, chưa next/previous lại | Có | Không | Không |
| Vừa add, chưa next/previous lại | Có | Không | Không |
| Vừa set trên một lựa chọn hợp lệ | Có | Vẫn có thể remove lựa chọn đó | Có thể set lại |

Bảng giả sử iterator còn hợp lệ và triển khai hỗ trợ thao tác. LinkedList hỗ trợ các thao tác sửa đổi này. Với một ListIterator của danh sách không hỗ trợ sửa, còn có thể gặp `UnsupportedOperationException`.

Các vi phạm trạng thái như remove trước lần duyệt đầu, remove hai lần liên tiếp hoặc set ngay sau add gây `IllegalStateException` khi xét iterator LinkedList hợp lệ.

Một lần gọi `hasNext()` trả true không cấp quyền remove. Nó chỉ kiểm tra có phần tử phía trước. Cần next/previous thực sự trả một phần tử thành công.

Các thao tác sửa qua iterator có chữ ký khác với thao tác trực tiếp trên List:

| API | Kết quả | Mục tiêu |
|---|---|---|
| `iterator.add(e)` | `void` | Khoảng tại con trỏ |
| `iterator.remove()` | `void` | Phần tử vừa được trả về |
| `iterator.set(e)` | `void` | Phần tử vừa được trả về |
| `list.remove(index)` | Phần tử | Chỉ số hiện tại của danh sách |
| `list.remove(object)` | `boolean` | Lần xuất hiện đầu tiên bằng giá trị tìm |

Đừng thay trực tiếp phương thức này bằng phương thức kia chỉ vì cùng có tên remove. [Hợp đồng add/remove/set của ListIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html).

## 7. Chương trình đầy đủ: chèn/xóa theo cả hai hướng

Lưu thành `LinkedListCursorEditDemo.java`. Chương trình dùng API có trong Java 17:

```java
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;

public class LinkedListCursorEditDemo {
    private static void show(
            String label, List<String> values, ListIterator<String> iterator) {
        System.out.println(label + ": " + values
                + "; previousIndex = " + iterator.previousIndex()
                + "; nextIndex = " + iterator.nextIndex());
    }

    public static void main(String[] args) {
        List<String> values =
                new LinkedList<>(List.of("A", "B", "C", "D"));
        ListIterator<String> iterator = values.listIterator(1);
        show("start", values, iterator);

        iterator.add("X");
        iterator.add("Y");
        show("after two adds", values, iterator);

        System.out.println("next = " + iterator.next());
        iterator.remove();
        show("after remove following next", values, iterator);

        System.out.println("next = " + iterator.next());
        System.out.println("previous = " + iterator.previous());
        iterator.remove();
        show("after remove following previous", values, iterator);

        iterator.add("Z");
        System.out.println("next after add = " + iterator.next());
        iterator.set("D*");
        show("after set", values, iterator);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 LinkedListCursorEditDemo.java
java LinkedListCursorEditDemo
```

Kết quả chuẩn:

```text
start: [A, B, C, D]; previousIndex = 0; nextIndex = 1
after two adds: [A, X, Y, B, C, D]; previousIndex = 2; nextIndex = 3
next = B
after remove following next: [A, X, Y, C, D]; previousIndex = 2; nextIndex = 3
next = C
previous = C
after remove following previous: [A, X, Y, D]; previousIndex = 2; nextIndex = 3
next after add = D
after set: [A, X, Y, Z, D*]; previousIndex = 4; nextIndex = 5
```

Theo dõi con trỏ tương ứng:

| Bước | Danh sách và vị trí con trỏ |
|---|---|
| Khởi tạo tại 1 | `A \| B C D` |
| Add X | `A X \| B C D` |
| Add Y | `A X Y \| B C D` |
| Next trả B | `A X Y B \| C D` |
| Remove B | `A X Y \| C D` |
| Next trả C | `A X Y C \| D` |
| Previous trả C | `A X Y \| C D` |
| Remove C | `A X Y \| D` |
| Add Z | `A X Y Z \| D` |
| Next trả D, rồi set D* | `A X Y Z D* \|` |

Trong chương trình, X và Y được chèn đúng thứ tự trước B. Next sau hai lần add vẫn trả B, không trả X hoặc Y.

Phần C được next rồi previous trả lại, nên remove sau đó nhắm vào C. Iterator tiếp tục giữ đúng khoảng trước D. Sau khi chèn Z, next trả D; set thay D thành D* mà không làm thay size.

Hàm `show` in cả danh sách để quan sát. Việc in cần duyệt danh sách, nên không dùng thời gian chạy của ví dụ in từng bước để đo chi phí riêng của add/remove cục bộ.

## 8. Chi phí khi đã giữ iterator ở vị trí cần sửa

Trong triển khai LinkedList của OpenJDK, ListIterator giữ tham chiếu đến nút kế tiếp và nút vừa trả về. Add nối nút mới trước nút kế tiếp hoặc nối cuối; remove tháo nút vừa trả về. Nó không cần tìm lại từ đầu bằng chỉ số cho mỗi lần sửa.

| Công việc trên LinkedList | Chi phí thường xét |
|---|---|
| Tạo `listIterator(index)` tại vị trí giữa | `O(n)` trong trường hợp xấu vì cần đi đến vị trí |
| Tạo iterator ở đầu hoặc cuối | `O(1)` |
| Next/previous một bước | `O(1)` |
| Add tại con trỏ đã có | `O(1)` cho việc nối nút |
| Remove hợp lệ phần tử vừa trả về | `O(1)` cho việc tháo nút |
| Set hợp lệ phần tử vừa trả về | `O(1)` |

Phân tích là chi phí cấu trúc thông thường; thêm nút còn cần cấp đối tượng nút. Đây không phải cam kết độ trễ cố định theo thời gian thực.

Nếu ban đầu phải đi tới vị trí xa, rồi thực hiện `k` lần chèn/xóa cục bộ, tổng chi phí có dạng “chi phí đi đến vị trí + chi phí k thao tác”. Không bỏ phần chi phí đầu rồi khẳng định mọi thao tác tại một chỉ số bất kỳ đều hằng số.

Ví dụ, tạo lại `listIterator(index)` ở giữa cho mỗi lần chèn có thể lại trả chi phí tìm vị trí nhiều lần. Giữ và di chuyển một iterator phù hợp mới tận dụng được vị trí đã có.

Cũng không suy độ phức tạp này chỉ từ tên giao diện ListIterator. ListIterator của ArrayList có thể phải dịch phần tử khi chèn/xóa ở giữa. Cùng một hợp đồng thao tác không buộc các cấu trúc có cùng chi phí. [ListItr và liên kết nút trong OpenJDK 17](https://github.com/openjdk/jdk17u/blob/master/src/java.base/share/classes/java/util/LinkedList.java).

## 9. Một lượt duyệt vừa lọc vừa chèn

Mẫu xóa khi đang duyệt tiến:

```java
ListIterator<Integer> iterator = values.listIterator();
while (iterator.hasNext()) {
    Integer value = iterator.next();
    if (value == null || value < 0) {
        iterator.remove();
    }
}
```

Đây là đoạn minh họa với `values` là một LinkedList đã khai báo. Nhánh null được kiểm tra trước phép so sánh số, tránh unboxing null.

Sau remove, next tiếp theo đọc phần tử chưa xử lý kế tiếp. Không cần sửa một biến chỉ số để đối phó việc các vị trí dịch chuyển.

Muốn chèn ngay sau phần tử vừa được next trả về, gọi add ở vị trí hiện tại:

```java
Integer value = iterator.next();
if (Integer.valueOf(2).equals(value)) {
    iterator.add(20);
}
```

Đây là đoạn minh họa độc lập, giả sử trước đó đã kiểm tra còn phần tử. Từ `... 2 | phần-kế-tiếp ...`, kết quả là `... 2 20 | phần-kế-tiếp ...`.

Nếu vòng lặp tiếp tục chỉ gọi next theo hướng tiến, phần tử 20 vừa chèn nằm phía sau con trỏ và không được xử lý lại bởi lần next tiếp theo. Điều đó có thể đúng ý định khi chỉ muốn xử lý các phần tử ban đầu.

Nếu thuật toán cần xử lý cả dữ liệu mới chèn, phải thiết kế lại quy tắc di chuyển và điều kiện kết thúc. Việc tự gọi previous rồi xử lý lại một phần tử theo cùng quy tắc chèn có thể tạo vòng lặp không kết thúc.

### 9.1. Muốn chèn trước phần tử vừa đọc phải quản lý con trỏ rõ

Sau next trả B, con trỏ đã đứng sau B. Add ngay sẽ chèn sau B, không phải trước B.

Một mẫu minh họa chèn marker trước B:

```java
while (iterator.hasNext()) {
    String value = iterator.next();
    if ("B".equals(value)) {
        iterator.previous(); // Trở lại khoảng trước B.
        iterator.add("before-B");
        iterator.next();     // Đi qua B để tiếp tục sau B.
    }
}
```

Đoạn này dùng một `ListIterator<String>` độc lập và một danh sách chuỗi đã có. Với `[A, B, C]`, kết quả là `[A, before-B, B, C]`.

Lời gọi next cuối nhánh có mục đích: đi qua B sau khi đã chèn marker. Nếu bỏ nó, lần lặp tiếp theo có thể lại đọc B và tiếp tục chèn trước B mãi. Đây là lỗi thuật toán về con trỏ, dù mỗi lời gọi add đều hợp lệ.

### 9.2. Xóa một đoạn từ con trỏ

Nếu cần xóa tối đa `limit` phần tử ở phía next, có thể lặp “next để chọn, remove để xóa”:

```java
int removedCount = 0;
while (removedCount < limit && iterator.hasNext()) {
    iterator.next();
    iterator.remove();
    removedCount++;
}
```

Đây là đoạn minh họa với iterator hợp lệ và `limit >= 0`. Nó xóa tối đa limit phần tử, không hứa xóa đủ nếu đã tới cuối.

Nếu yêu cầu nghiệp vụ là xóa đúng một số lượng và không được sửa một phần khi thiếu dữ liệu, cần kiểm tra điều kiện hoặc thiết kế thao tác theo chính sách đó trước khi bắt đầu. Không gán khả năng hoàn tác tự động cho iterator.

## 10. Chương trình đầy đủ: một lượt sửa và các lỗi trạng thái

Lưu thành `LinkedListEditPassDemo.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedList;
import java.util.List;
import java.util.ListIterator;

public class LinkedListEditPassDemo {
    private static void expectIllegalState(String label, Runnable action) {
        try {
            action.run();
            System.out.println(label + ": no exception");
        } catch (IllegalStateException ex) {
            System.out.println(label + ": IllegalStateException");
        }
    }

    public static void main(String[] args) {
        List<Integer> values =
                new LinkedList<>(Arrays.asList(-1, null, 0, -2, 2, 3));
        List<Integer> visited = new ArrayList<>();
        ListIterator<Integer> iterator = values.listIterator();

        while (iterator.hasNext()) {
            Integer value = iterator.next();
            visited.add(value);
            if (value == null || value < 0) {
                iterator.remove();
            } else if (value == 0) {
                iterator.set(10);
                iterator.add(11);
            } else if (value == 2) {
                iterator.add(20);
            }
        }

        System.out.println("visited: " + visited);
        System.out.println("edited: " + values);

        List<String> words = new LinkedList<>(List.of("A", "B", "C"));
        ListIterator<String> edit = words.listIterator(1);
        expectIllegalState("remove before traversal", edit::remove);

        System.out.println("selected: " + edit.next());
        edit.remove();
        expectIllegalState("second remove", edit::remove);

        System.out.println("selected: " + edit.next());
        edit.add("X");
        expectIllegalState("remove after add", edit::remove);
        expectIllegalState("set after add", () -> edit.set("bad"));

        System.out.println("previous after add: " + edit.previous());
        edit.remove();
        System.out.println("words: " + words);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 LinkedListEditPassDemo.java
java LinkedListEditPassDemo
```

Kết quả chuẩn:

```text
visited: [-1, null, 0, -2, 2, 3]
edited: [10, 11, 2, 20, 3]
remove before traversal: IllegalStateException
selected: B
second remove: IllegalStateException
selected: C
remove after add: IllegalStateException
set after add: IllegalStateException
previous after add: X
words: [A, C]
```

Lượt xử lý số thực hiện:

- Xóa số âm và phần tử null ngay sau khi duyệt chúng.
- Thay 0 bằng 10 qua set, rồi chèn 11 sau đó.
- Chèn 20 sau giá trị 2.
- Tiếp tục đọc các phần tử chưa xử lý ban đầu.

Danh sách `visited` cho thấy iterator đã xử lý sáu phần tử gốc, gồm cả null. Các giá trị mới 11 và 20 không được next đọc lại trong lượt tiến này. Kết quả không bỏ sót -2 sau khi đã chèn 11, cũng không bỏ sót phần tử sau mỗi lần xóa.

Nhóm chuỗi kiểm tra hợp đồng trạng thái:

1. Vừa tạo iterator thì remove bị từ chối.
2. Next chọn B, remove xóa B; remove lần nữa bị từ chối.
3. Next chọn C, nhưng add X làm mất lựa chọn cũ đối với remove/set.
4. Previous sau add trả X, tạo một lựa chọn mới hợp lệ.
5. Remove lúc này xóa đúng X, còn `[A, C]`.

Nếu chỉ cần lọc theo điều kiện, một API như removeIf có thể diễn đạt ngắn hơn. ListIterator có giá trị khi cần phối hợp vị trí, hướng di chuyển, thay thế và chèn/xóa trong cùng một lượt có quy tắc rõ.

## 11. Chỉ sửa cấu trúc qua iterator đang quản lý lượt duyệt

Đoạn minh họa cách dùng không phù hợp:

```java
ListIterator<String> iterator = words.listIterator();
while (iterator.hasNext()) {
    String value = iterator.next();
    if ("B".equals(value)) {
        words.remove(value); // Sửa cấu trúc ngoài iterator đang duyệt.
    }
}
```

Ở đây dù đã tìm được phần tử bằng iterator, mã lại quay sang gọi remove trực tiếp trên danh sách. Điều này có thể:

- Tìm và xóa theo giá trị thay vì đúng lần xuất hiện vừa duyệt.
- Tốn thêm việc tìm kiếm.
- Làm iterator đang giữ không còn phù hợp với trạng thái cấu trúc.

Trên LinkedList, iterator có cơ chế phát hiện sửa đổi và có thể ném `ConcurrentModificationException`. Việc phát hiện không phải một cơ chế đồng bộ hoặc một chiến lược điều khiển luồng bảo đảm; không viết mã dựa vào chuyện “nếu không ném thì chắc an toàn”.

Trong lượt sửa đang xét, dùng `iterator.remove()` và `iterator.add(...)` để iterator cập nhật trạng thái của chính nó theo các thao tác đó.

Nếu có hai iterator trên cùng danh sách, sửa cấu trúc qua iterator thứ nhất không giữ iterator thứ hai hợp lệ một cách tự động. Tương tự, thêm qua một biến Deque cùng trỏ vào LinkedList vẫn là sửa cùng cấu trúc bên ngoài iterator hiện tại.

ListIterator không phải bản sao dữ liệu và không làm LinkedList an toàn cho nhiều luồng. Nếu có truy cập đồng thời, cần chính sách riêng cho việc sở hữu và sửa danh sách. [Quy tắc iterator của LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html).

## 12. Lỗi phổ biến và cách kiểm tra

| Cách hiểu hoặc cách viết | Hậu quả | Cách sửa theo ý định |
|---|---|---|
| Cho rằng con trỏ luôn trỏ vào một phần tử hiện tại | Add/remove bị đọc sai vị trí | Vẽ khoảng giữa previous và next |
| Gọi remove ngay sau listIterator(index) | Chưa có phần tử vừa trả về | Next hoặc previous để chọn đúng phía rồi remove |
| Gọi remove ngay sau add để xóa phần tử mới | IllegalStateException | Previous trả phần tử vừa chèn rồi remove nếu đó là mục tiêu |
| Gọi remove hai lần sau một lần next | Lần thứ hai sai trạng thái | Duyệt chọn phần tử khác trước lần remove tiếp |
| Gọi set sau add mà không duyệt lại | Lựa chọn trước add không còn dùng cho set | Chọn lại bằng next/previous |
| Add sau next nhưng mong chèn trước phần tử vừa đọc | Phần tử bị chèn ở phía sau phần tử vừa đọc | Tính lại di chuyển con trỏ rõ ràng |
| Sau remove lại gọi thêm next để bù chỉ số | Có thể bỏ qua phần tử kế tiếp | Để bước next của vòng lặp thực hiện việc đọc tiếp |
| Lặp lại tạo iterator theo chỉ số ở giữa | Tìm lại vị trí nhiều lần | Giữ iterator khi mẫu chỉnh sửa cục bộ cho phép |
| Gọi list.remove(value) trong lượt iterator | Tìm/xóa theo đường khác và có thể làm iterator mất hiệu lực | Sửa qua iterator đang quản lý lượt duyệt |
| Kết luận mọi ListIterator có add/remove O(1) | Bỏ qua cấu trúc triển khai | Gắn phân tích chi phí với LinkedList cụ thể |

## 13. Tự dự đoán từ vị trí con trỏ

Mỗi câu bắt đầu độc lập từ danh sách `[A, B, C]` và iterator tạo bởi `listIterator(1)`, tức `A | B C`.

1. Gọi add X rồi add Y. Danh sách và next tiếp theo là gì?
2. Gọi next rồi remove. Danh sách và nextIndex là gì?
3. Gọi previous rồi remove. Phần tử nào bị xóa?
4. Gọi add X rồi remove ngay. Có hợp lệ không?
5. Gọi add X, previous, remove. Kết quả là gì?
6. Chỉ gọi hasNext rồi remove. HasNext có cấp quyền xóa không?

Đáp án:

1. `[A, X, Y, B, C]`; con trỏ `A X Y | B C`, nên next trả B.
2. Next trả B; remove xóa B; còn `[A, C]`, con trỏ `A | C`, nextIndex bằng 1.
3. Previous trả A; remove xóa A; còn `[B, C]`, con trỏ ở đầu.
4. Không; add đã thiết lập lại trạng thái lựa chọn, remove gây `IllegalStateException`.
5. Sau add là `A X | B C`; previous trả X; remove xóa X. Danh sách trở về `[A, B, C]` với con trỏ `A | B C`.
6. Không; cần next/previous trả phần tử thật sự trước khi remove.

Khi đã có ListIterator, hãy giữ rõ ba thông tin: con trỏ đang ở khoảng nào, phần tử nào vừa được trả về và trạng thái hiện tại có cho phép remove/set hay không. Trên LinkedList, hiểu đúng ba điều đó vừa giúp sửa đúng phần tử vừa tận dụng được vị trí nút đã có để chèn/xóa cục bộ.
