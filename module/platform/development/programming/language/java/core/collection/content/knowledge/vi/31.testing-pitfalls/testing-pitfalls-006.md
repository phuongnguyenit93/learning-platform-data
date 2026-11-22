# IndexOutOfBoundsException, NoSuchElementException và IllegalStateException

## 1. Ba câu hỏi khác nhau trước một thao tác collection

Cùng một danh sách rỗng nhưng `list.get(0)`, `list.iterator().next()` và `list.iterator().remove()` có thể thất bại theo ba cách khác nhau. Không nên gom chúng thành một lỗi chung mang tên “collection không có dữ liệu”.

Hãy tách ba câu hỏi:

1. **Địa chỉ có hợp lệ không?** Một chỉ số phải nằm trong miền mà phương thức chấp nhận. Vi phạm miền chỉ số dẫn tới `IndexOutOfBoundsException`.
2. **Có phần tử để lấy không?** Một phương thức yêu cầu phải lấy được phần tử tiếp theo hoặc phần tử đầu/cuối, nhưng không có phần tử đó, có thể ném `NoSuchElementException`.
3. **Lúc này có được thực hiện thao tác không?** Thứ tự lời gọi trước đó hoặc trạng thái hiện tại chưa cho phép thao tác. Ví dụ điển hình là `Iterator.remove()` chưa có phần tử vừa được trả về, hoặc `add` vào hàng đợi hữu hạn đang đầy: `IllegalStateException`.

Tên lớp ngoại lệ là đầu mối. Hợp đồng của **đúng phương thức trên đúng loại đối tượng** mới quyết định cách sửa.

| Lời gọi minh họa | Điều đang được yêu cầu | Lỗi cần phân biệt |
| --- | --- | --- |
| `new ArrayList<String>().get(0)` | Đọc phần tử ở chỉ số 0 | Không có chỉ số phần tử hợp lệ |
| Iterator của một List rỗng gọi `next()` | Trả phần tử kế tiếp | Không còn phần tử để trả |
| Iterator có hỗ trợ xóa gọi `remove()` trước `next()` | Xóa phần tử vừa được iterator trả về | Chưa có phần tử như vậy trong trạng thái con trỏ |
| `ArrayBlockingQueue` đã đầy gọi `add(value)` | Chèn ngay một phần tử mới | Trạng thái sức chứa không cho phép chèn |

Bài này dùng Java 17+ và collection chuẩn. Các thí nghiệm chạy một luồng để tách lỗi hợp đồng khỏi tranh chấp giữa các luồng.

## 2. IndexOutOfBoundsException: phân biệt chỉ số phần tử và vị trí chèn

### 2.1. Có n phần tử nhưng có n + 1 vị trí đặt con trỏ

Với danh sách có `n = size()` phần tử:

- Chỉ số của **phần tử hiện hữu** là từ `0` đến `n - 1`.
- **Vị trí chèn** hoặc vị trí khởi tạo `ListIterator` là từ `0` đến `n`.

Hai miền này khác nhau ở biên phải:

```text
Danh sách:           A       B       C
Chỉ số phần tử:      0       1       2
Vị trí chèn:     0       1       2       3
size() = 3

get(2)       -> đọc C
get(3)       -> vượt miền phần tử
add(3, D)    -> chèn D vào cuối, vị trí hợp lệ
listIterator(3) -> con trỏ ở cuối; next() không còn phần tử
```

Đừng diễn giải `size()` là “chỉ số cuối”. Nó là số phần tử, và trong các phương thức thích hợp còn là vị trí ngay sau phần tử cuối.

| Phương thức List | Miền hợp lệ của đối số chỉ số |
| --- | --- |
| `get(index)` | `0 <= index < size()` |
| `set(index, value)` | `0 <= index < size()` |
| `remove(index)` | `0 <= index < size()` |
| `add(index, value)` | `0 <= index <= size()` |
| `listIterator(index)` | `0 <= index <= size()` |

`set(size(), value)` không phải cách nối thêm vào cuối: `set` thay một phần tử đang tồn tại. Muốn chèn, dùng `add` theo đúng ý định. Các miền chỉ số được công bố trong [hợp đồng List của Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/List.html).

Với List rỗng, không có chỉ số nào hợp lệ để `get`, `set` hoặc xóa theo chỉ số. Tuy nhiên, vị trí chèn `0` vẫn hợp lệ nếu List hỗ trợ thêm.

### 2.2. Chỉ số của view được tính trong chính view

Một đoạn con dùng quy ước nửa mở `[fromIndex, toIndex)`: lấy từ đầu bao gồm `fromIndex`, dừng trước `toIndex`.

```text
base = [A, B, C, D]
part = base.subList(1, 3) = [B, C]

part.get(0) -> B
part.get(1) -> C
part.get(2) -> vượt miền của part, dù base vẫn có chỉ số 2
```

`subList(size(), size())` tạo một view rỗng ở cuối. View rỗng vẫn không có phần tử ở chỉ số `0`.

Giữ các đầu mút trong miền của danh sách, với đầu trái không lớn hơn đầu phải. Đừng biến bài kiểm tra chỉ số thành bài kiểm tra cùng lúc nhiều đầu mút sai rồi suy ra một thứ tự ưu tiên ngoại lệ cho mọi triển khai. View cũng có quy tắc liên kết với nguồn; một view bị vô hiệu hóa do sửa cấu trúc nguồn bằng đường khác là vấn đề riêng, không được xử lý bằng cách sửa chỉ số theo phỏng đoán.

### 2.3. Những nguyên nhân thường gặp

**Sai dấu trong điều kiện vòng lặp.** Đoạn sau sai khi đi tới `i == size()`:

```java
// Đoạn minh họa sai; values là một List đã có trong phương thức.
for (int i = 0; i <= values.size(); i++) {
    System.out.println(values.get(i));
}
```

Nếu chỉ đọc và không cần chỉ số, vòng `for` mở rộng giúp biểu đạt đúng mục đích. Nếu cần chỉ số, dùng `i < values.size()` trong điều kiện phù hợp, đồng thời xác định rõ danh sách có được thay đổi trong lúc duyệt hay không.

**Lấy phần tử cuối khi rỗng.** `get(size() - 1)` trên List rỗng trở thành `get(-1)`. Công thức đúng khi có phần tử, nhưng chưa tự xử lý trường hợp rỗng.

**Dùng kết quả tìm kiếm mà bỏ qua trường hợp không tìm thấy.**

```java
// Đoạn minh họa bên trong phương thức; names hỗ trợ thao tác cần dùng.
int index = names.indexOf("An");
if (index >= 0) {
    names.set(index, "An Nguyen");
}
```

Khi không tìm thấy, `indexOf` trả `-1`; giá trị đó không phải chỉ số hợp lệ để đọc hoặc thay thế. Việc không tìm thấy có thể là kết quả bình thường của bài toán. Xử lý nó trước thao tác theo chỉ số.

**Lưu chỉ số rồi thay đổi danh sách.** Xóa phần tử làm các phần tử phía sau dịch trái. Một chỉ số từng trỏ tới một mục có thể trỏ tới mục khác hoặc vượt miền sau thay đổi. Với yêu cầu xóa trong lúc duyệt, chọn iterator hỗ trợ xóa hoặc một chiến lược áp dụng chỉ số đã được xác định rõ. Chỉ đổi `<=` thành `<` không sửa được sai lệch về danh tính phần tử.

## 3. remove(int) và remove(Object): cùng tên, hai hợp đồng

Với `List<Integer>`, lời gọi sau **không** có nghĩa xóa số `20`:

```java
// Đoạn minh họa bên trong phương thức; cần import java.util.List và ArrayList.
List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));
numbers.remove(20); // Chọn remove(int index): yêu cầu xóa chỉ số 20.
```

Danh sách chỉ có ba phần tử, nên chỉ số `20` không hợp lệ. Nếu muốn xóa theo giá trị:

```java
boolean removed = numbers.remove(Integer.valueOf(20));
```

Ở đây đối số có kiểu `Integer`, nên lời gọi chọn `remove(Object)`: xóa lần xuất hiện đầu tiên bằng giá trị đó nếu có, rồi trả kết quả boolean.

Điểm cần kiểm thử là **phương thức thực sự được chọn**, không chỉ dữ liệu đang lưu:

- `remove(0)` trên List là xóa theo chỉ số.
- `remove(Integer.valueOf(0))` trên `List<Integer>` là xóa theo giá trị.
- `Queue.remove()` không có đối số là lấy và xóa phần tử đầu.
- `queue.remove(value)` là một lời gọi khác, tìm và xóa một phần tử bằng giá trị.

Một Stack Trace có chữ `remove` chưa đủ để phân loại lỗi. Xem chữ ký phương thức và kiểu tĩnh của đối số.

## 4. NoSuchElementException: yêu cầu phải trả phần tử nhưng không có

### 4.1. Iterator.next không phải phép dò xem có dữ liệu

`Iterator.next()` phải trả phần tử kế tiếp. Nếu lượt duyệt không còn phần tử, nó ném `NoSuchElementException`. `hasNext()` dùng để kiểm tra khả năng đi tiếp trong điều kiện sử dụng iterator hợp lệ. [Hợp đồng Iterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Iterator.html).

Mẫu đọc thông thường:

```java
// Mẫu áp dụng bên trong phương thức; iterator đã được tạo từ nguồn phù hợp.
while (iterator.hasNext()) {
    Object value = iterator.next();
    System.out.println(value);
}
```

Một lỗi dễ bị bỏ sót là gọi `next()` hai lần cho một lần kiểm tra:

```java
// Sai: một lần hasNext chỉ xác nhận còn ít nhất một phần tử.
while (iterator.hasNext()) {
    System.out.println(iterator.next());
    System.out.println(iterator.next()); // có thể vượt cuối khi chỉ còn một phần tử
}
```

Với hai phần tử, đoạn này có thể kết thúc không lỗi; với một hoặc ba phần tử, lần next thứ hai ở vòng cuối không còn dữ liệu. Vì thế kiểm thử chỉ với một đầu vào có số lượng chẵn có thể che mất lỗi.

Với `ListIterator`, `previous()` có tình huống đối xứng: con trỏ ở đầu thì không có phần tử trước đó. `hasPrevious()` kiểm tra hướng lùi. Một con trỏ hợp lệ ở cuối không có phần tử tiếp theo nhưng có thể có phần tử phía trước.

### 4.2. Queue và Deque có hai họ phương thức ở đầu mút

Java cung cấp cặp phương thức để người viết chọn cách biểu đạt trường hợp rỗng:

| Mục đích | Yêu cầu phải có phần tử | Trả giá trị đặc biệt khi rỗng |
| --- | --- | --- |
| Đọc đầu Queue | `element()` ném `NoSuchElementException` | `peek()` trả `null` |
| Lấy và xóa đầu Queue | `remove()` ném `NoSuchElementException` | `poll()` trả `null` |
| Đọc đầu Deque | `getFirst()` ném `NoSuchElementException` | `peekFirst()` trả `null` |
| Đọc cuối Deque | `getLast()` ném `NoSuchElementException` | `peekLast()` trả `null` |
| Lấy và xóa đầu Deque | `removeFirst()` ném `NoSuchElementException` | `pollFirst()` trả `null` |
| Lấy và xóa cuối Deque | `removeLast()` ném `NoSuchElementException` | `pollLast()` trả `null` |

`Deque.pop()` tương đương lấy-xóa đầu bằng `removeFirst()`, nên pop từ ngăn xếp rỗng cũng ném `NoSuchElementException`. Đây là hành vi được công bố của [Queue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html) và [Deque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html).

Chọn phương thức theo ý nghĩa nghiệp vụ:

- Nếu rỗng là điều bình thường, chẳng hạn chưa có việc để xử lý trong lượt này, `poll` và kiểm tra kết quả thường biểu đạt đúng hơn.
- Nếu trước đó chương trình đã thiết lập điều kiện phải có một phần tử, `remove()` hoặc `element()` có thể giúp phát hiện việc điều kiện bị phá.
- Đừng đổi mọi lời gọi sang `poll` rồi bỏ qua kết quả. Có thể chỉ chuyển lỗi hợp đồng thành dữ liệu bị mất âm thầm.

### 4.3. Giá trị null cần được xử lý trước khi dùng

Trong ví dụ đầy đủ, các hàng đợi dùng `ArrayDeque` hoặc `ArrayBlockingQueue`, đều không nhận phần tử `null`. Vì thế `null` từ `poll` có thể được dùng rõ ràng để nhận biết rỗng.

Không mặc định mọi triển khai Queue đều có chính sách null giống nhau. Queue cho phép null có thể làm giá trị đặc biệt trở nên khó phân biệt với dữ liệu. Nên xác định chính sách dữ liệu ngay ở biên API.

Đoạn sau có thể ném `NullPointerException` do tự mở hộp, dù đã tránh `NoSuchElementException`:

```java
// Đoạn minh họa sai khi queue rỗng; queue có kiểu Queue<Integer>.
int value = queue.poll();
```

Đọc vào `Integer`, kiểm tra `null`, rồi mới sử dụng giá trị. Việc thay phương thức phải đi cùng xử lý hợp đồng kết quả của nó.

## 5. IllegalStateException trên iterator: lỗi trình tự lời gọi

### 5.1. remove xóa phần tử vừa được trả về

Với iterator có hỗ trợ xóa, `remove()` không có đối số vì nó đã gắn với **phần tử gần nhất được chính iterator đó trả về bởi next()**.

Quy tắc cơ bản:

1. Gọi `next()` thành công để có phần tử vừa trả về.
2. Có thể xóa phần tử đó bằng `remove()` tối đa một lần.
3. Muốn xóa một phần tử tiếp theo, phải tiếp tục gọi `next()` thành công.

```text
Tạo iterator
    remove chưa hợp lệ
        |
        | next thành công
        v
Có phần tử vừa trả về
    remove hợp lệ một lần
        |
        | remove thành công
        v
Chưa có phần tử mới để xóa
    remove tiếp ngay -> IllegalStateException
```

`hasNext()` chỉ kiểm tra khả năng đi tiếp; nó không tạo “phần tử vừa trả về”. Vì thế gọi `hasNext()` rồi `remove()` ngay sau khi tạo iterator vẫn chưa đúng trình tự.

Một chi tiết khác: sau khi `next()` trả phần tử cuối, `hasNext()` có thể là false, nhưng quyền xóa phần tử cuối vừa trả về vẫn còn nếu chưa xóa nó. “Không còn phần tử tiếp theo” và “không có phần tử vừa trả về để xóa” là hai trạng thái khác nhau.

Các quy tắc trên cần đặt trong hợp đồng iterator cho phép sửa. Iterator không hỗ trợ `remove` có thể ném `UnsupportedOperationException`; gọi `next` không biến một thao tác bị cấm thành thao tác được hỗ trợ. Không tạo ca thử vừa sai trạng thái vừa không hỗ trợ xóa rồi dùng nó để khẳng định ngoại lệ nào luôn thắng.

### 5.2. ListIterator: vị trí con trỏ khác phần tử vừa trả về

`ListIterator` có con trỏ ở **khoảng giữa các phần tử**, còn `set` và `remove` tác động lên phần tử gần nhất được `next` hoặc `previous` trả về. Đó không phải một “phần tử hiện tại” luôn có sẵn chỉ vì đã tạo con trỏ.

Với ListIterator hỗ trợ các thao tác sửa tương ứng:

| Trình tự | Điều cần hiểu |
| --- | --- |
| Mới tạo, chưa đi bằng `next`/`previous` | `set` và `remove` chưa hợp lệ |
| Vừa đi bằng `next` hoặc `previous` | Có thể `set` phần tử vừa trả về; có thể `remove` nếu chưa add/remove sau lần đi đó |
| Gọi `set` nhiều lần sau một lần đi | Được phép nếu không có add/remove xen vào |
| Gọi `remove` thành công | `set` hoặc `remove` tiếp ngay chưa hợp lệ |
| Gọi `add` thành công | Phải đi lại bằng next/previous trước khi set/remove |
| Gọi `add` khi mới tạo con trỏ | Không cần một lần next/previous trước đó |

Theo [hợp đồng ListIterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ListIterator.html), `add` chèn trước phần tử mà `next()` sẽ trả, nếu có. Sau khi thêm, `previous()` trả phần tử vừa thêm, còn một lần `next()` sẽ đi tới phần tử vốn nằm sau vị trí chèn.

Chẳng hạn:

```text
values = [A, C], con trỏ ở đầu
add(B)  -> values = [B, A, C], con trỏ nằm giữa B và A
set(X)  -> chưa hợp lệ: add vừa làm mất điều kiện set/remove
next()  -> trả A
set(X)  -> values = [B, X, C]
set(Y)  -> values = [B, Y, C], vẫn hợp lệ
remove()-> values = [B, C]
set(Z)  -> chưa hợp lệ sau remove
```

Hãy kiểm thử **chuỗi thao tác**, không chỉ từng phương thức riêng lẻ. Hai lời gọi `set` với cùng đối số có thể khác kết quả chỉ vì trước đó có hoặc không có `add`.

## 6. IllegalStateException do hàng đợi đầy khác lỗi iterator

Một hàng đợi có giới hạn sức chứa có trạng thái khác: còn chỗ hoặc đã đầy. Với `ArrayBlockingQueue`, `add(value)` vào hàng đợi đầy ném `IllegalStateException`; `offer(value)` không chờ trả `false` khi không còn chỗ. [Tài liệu ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html).

```text
Sức chứa = 1, hàng đợi ban đầu rỗng
add(A)   -> true,  nội dung [A]
add(B)   -> IllegalStateException vì đầy
offer(B) -> false, nội dung vẫn [A]
poll()   -> A, nội dung []
offer(B) -> true, nội dung [B]
```

Đây không phải lỗi “chưa gọi next”. Cùng loại ngoại lệ nhưng điều kiện sử dụng hoàn toàn khác.

Chọn chính sách theo yêu cầu nhận việc:

- `add`: không nhận được là trường hợp cần báo lỗi qua ngoại lệ.
- `offer`: không nhận được ngay là kết quả boolean mà người gọi phải xử lý.
- Các phương thức chờ như `put`, `take` có hợp đồng khác về chờ và ngắt luồng. Không thay bằng chúng chỉ để làm biến mất ngoại lệ; có thể khiến chương trình chờ vô thời hạn nếu không có bên làm thay đổi trạng thái.

Chương trình bên dưới chỉ dùng các thao tác không chờ và không tạo luồng phụ. Khi nhận `false` từ offer, ứng dụng vẫn phải quyết định từ chối, lưu chỗ khác, thử lại theo chính sách hoặc báo người gọi. Boolean không thay thế quyết định đó.

## 7. Chương trình Java 17+ kiểm tra hợp đồng

Lưu mã dưới đây thành **ExceptionContractsDemo.java**. Chương trình dùng `AssertionError` để dừng nếu một kỳ vọng sai; không cần `-ea`, JUnit hoặc thư viện ngoài.

Mỗi thao tác thử ngoại lệ được khoanh trong một lambda ngắn. Hàm trợ giúp chấp nhận ngoại lệ thuộc kiểu đã yêu cầu, kể cả lớp con, nhưng không nuốt một RuntimeException khác. Các nguồn được tạo riêng theo từng nhóm để trình tự của một nhóm không làm sai dữ liệu đầu vào của nhóm khác.

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.Iterator;
import java.util.List;
import java.util.ListIterator;
import java.util.Objects;
import java.util.Queue;
import java.util.concurrent.ArrayBlockingQueue;

public class ExceptionContractsDemo {
    private static int passed;

    private static void checkEquals(String label, Object expected, Object actual) {
        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(label + ": expected=" + expected
                    + ", actual=" + actual);
        }
        passed++;
    }

    private static void expectThrows(
            String label, Class<? extends RuntimeException> type, Runnable action) {
        try {
            action.run();
        } catch (RuntimeException ex) {
            if (!type.isInstance(ex)) {
                throw new AssertionError(label + ": unexpected exception", ex);
            }
            passed++;
            return;
        }
        throw new AssertionError(label + ": expected " + type.getSimpleName());
    }

    private static void checkIndices() {
        List<String> empty = new ArrayList<>();
        expectThrows("empty get", IndexOutOfBoundsException.class, () -> empty.get(0));
        expectThrows("empty set", IndexOutOfBoundsException.class, () -> empty.set(0, "X"));
        expectThrows("empty indexed remove", IndexOutOfBoundsException.class,
                () -> empty.remove(0));
        empty.add(0, "A");
        checkEquals("empty insertion position", List.of("A"), empty);

        List<String> values = new ArrayList<>(List.of("B", "A", "C"));
        expectThrows("negative element index", IndexOutOfBoundsException.class,
                () -> values.get(-1));
        expectThrows("size is not an element index", IndexOutOfBoundsException.class,
                () -> values.get(values.size()));
        expectThrows("set cannot append", IndexOutOfBoundsException.class,
                () -> values.set(values.size(), "D"));
        expectThrows("indexed remove at size", IndexOutOfBoundsException.class,
                () -> values.remove(values.size()));
        checkEquals("last element", "C", values.get(values.size() - 1));
        values.add(values.size(), "D");
        checkEquals("insert at end", List.of("B", "A", "C", "D"), values);
        expectThrows("beyond insertion range", IndexOutOfBoundsException.class,
                () -> values.add(values.size() + 1, "E"));
        checkEquals("half-open slice", List.of("A", "C"), values.subList(1, 3));
        checkEquals("empty slice at end", List.of(),
                values.subList(values.size(), values.size()));

        List<Integer> numbers = new ArrayList<>(List.of(10, 20, 30));
        expectThrows("remove int selects index", IndexOutOfBoundsException.class,
                () -> numbers.remove(20));
        checkEquals("failed indexed remove preserves values", List.of(10, 20, 30), numbers);
        checkEquals("remove Integer selects value", true, numbers.remove(Integer.valueOf(20)));
        checkEquals("value removed", List.of(10, 30), numbers);
        checkEquals("absent value", false, numbers.remove(Integer.valueOf(99)));
        System.out.println("indices=PASS");
    }

    private static void checkIterator() {
        List<String> values = new ArrayList<>(List.of("A", "B"));
        Iterator<String> cursor = values.iterator();
        expectThrows("remove before next", IllegalStateException.class, cursor::remove);
        checkEquals("first next", "A", cursor.next());
        cursor.remove();
        checkEquals("first removal", List.of("B"), values);
        expectThrows("double remove", IllegalStateException.class, cursor::remove);
        checkEquals("last next", "B", cursor.next());
        checkEquals("no next element", false, cursor.hasNext());
        cursor.remove();
        checkEquals("last returned element can still be removed", List.of(), values);
        expectThrows("exhausted next", java.util.NoSuchElementException.class, cursor::next);

        Iterator<String> readOnly = List.of("A").iterator();
        checkEquals("read-only iterator can read", "A", readOnly.next());
        expectThrows("unsupported remove after valid next", UnsupportedOperationException.class,
                readOnly::remove);
        System.out.println("iterator=PASS");
    }

    private static void checkListIterator() {
        List<String> values = new ArrayList<>(List.of("A", "C"));
        ListIterator<String> cursor = values.listIterator();
        expectThrows("no previous at start", java.util.NoSuchElementException.class,
                cursor::previous);
        expectThrows("set before movement", IllegalStateException.class,
                () -> cursor.set("X"));
        expectThrows("remove before movement", IllegalStateException.class, cursor::remove);

        cursor.add("B");
        checkEquals("add without prior movement", List.of("B", "A", "C"), values);
        expectThrows("set immediately after add", IllegalStateException.class,
                () -> cursor.set("X"));
        expectThrows("remove immediately after add", IllegalStateException.class, cursor::remove);
        checkEquals("next after add", "A", cursor.next());
        cursor.set("X");
        cursor.set("Y");
        checkEquals("repeated set is allowed", List.of("B", "Y", "C"), values);
        cursor.remove();
        checkEquals("remove after set", List.of("B", "C"), values);
        expectThrows("set after remove", IllegalStateException.class, () -> cursor.set("X"));
        expectThrows("remove twice", IllegalStateException.class, cursor::remove);

        checkEquals("next after removal", "C", cursor.next());
        cursor.set("Z");
        checkEquals("replace last returned element", List.of("B", "Z"), values);
        checkEquals("at end", false, cursor.hasNext());
        checkEquals("previous at end", "Z", cursor.previous());
        cursor.remove();
        checkEquals("remove after previous", List.of("B"), values);

        ListIterator<String> end = values.listIterator(values.size());
        checkEquals("end position is valid", false, end.hasNext());
        expectThrows("next at end", java.util.NoSuchElementException.class, end::next);
        expectThrows("negative iterator position", IndexOutOfBoundsException.class,
                () -> values.listIterator(-1));
        expectThrows("too-large iterator position", IndexOutOfBoundsException.class,
                () -> values.listIterator(values.size() + 1));
        System.out.println("listIterator=PASS");
    }

    private static void checkEmptyEndpoints() {
        Queue<String> queue = new ArrayDeque<>();
        expectThrows("empty queue remove", java.util.NoSuchElementException.class,
                () -> queue.remove());
        expectThrows("empty queue element", java.util.NoSuchElementException.class,
                queue::element);
        checkEquals("empty poll", null, queue.poll());
        checkEquals("empty peek", null, queue.peek());
        checkEquals("remove absent value has another contract", false, queue.remove("missing"));
        queue.add("A");
        checkEquals("element reads head", "A", queue.element());
        checkEquals("element does not remove", 1, queue.size());
        checkEquals("remove returns head", "A", queue.remove());
        checkEquals("queue emptied", true, queue.isEmpty());

        Deque<String> stack = new ArrayDeque<>();
        expectThrows("empty getFirst", java.util.NoSuchElementException.class, stack::getFirst);
        expectThrows("empty getLast", java.util.NoSuchElementException.class, stack::getLast);
        expectThrows("empty removeFirst", java.util.NoSuchElementException.class,
                stack::removeFirst);
        expectThrows("empty removeLast", java.util.NoSuchElementException.class, stack::removeLast);
        expectThrows("empty pop", java.util.NoSuchElementException.class, stack::pop);
        checkEquals("empty pollFirst", null, stack.pollFirst());
        checkEquals("empty pollLast", null, stack.pollLast());
        checkEquals("empty peekFirst", null, stack.peekFirst());
        checkEquals("empty peekLast", null, stack.peekLast());
        stack.push("A");
        stack.push("B");
        checkEquals("LIFO first pop", "B", stack.pop());
        checkEquals("LIFO second pop", "A", stack.pop());
        checkEquals("stack emptied", true, stack.isEmpty());
        System.out.println("empty endpoints=PASS");
    }

    private static void checkBoundedQueue() {
        Queue<String> queue = new ArrayBlockingQueue<>(1);
        checkEquals("first add", true, queue.add("A"));
        expectThrows("add to full queue", IllegalStateException.class, () -> queue.add("B"));
        checkEquals("offer to full queue", false, queue.offer("B"));
        checkEquals("failed insertions preserve queue", List.of("A"), new ArrayList<>(queue));
        checkEquals("make room", "A", queue.poll());
        checkEquals("offer after space becomes available", true, queue.offer("B"));
        checkEquals("read new head", "B", queue.element());
        checkEquals("remove new head", "B", queue.remove());
        checkEquals("poll after draining", null, queue.poll());
        System.out.println("bounded queue=PASS");
    }

    public static void main(String[] args) {
        checkIndices();
        checkIterator();
        checkListIterator();
        checkEmptyEndpoints();
        checkBoundedQueue();
        System.out.println("PASS: " + passed + " checks");
    }
}
```

Biên dịch và chạy trong thư mục chứa tệp:

```shell
javac --release 17 -encoding UTF-8 -Xlint:all ExceptionContractsDemo.java
java ExceptionContractsDemo
```

Stdout khi toàn bộ kiểm tra đạt:

```text
indices=PASS
iterator=PASS
listIterator=PASS
empty endpoints=PASS
bounded queue=PASS
PASS: 78 checks
```

Chương trình đã được biên dịch với `--release 17` và chạy trên OpenJDK 24.0.2. `--release 17` kiểm tra mức ngôn ngữ và API đích; nó không có nghĩa quá trình chạy sử dụng một JVM 17.

### 7.1. Vì sao có kiểm tra dữ liệu sau thao tác?

Chỉ kiểm tra “có ném ngoại lệ” chưa bảo vệ đủ ý nghĩa của bài toán. Chương trình còn xác nhận:

- Thử xóa chỉ số 20 không biến thành xóa giá trị 20.
- Xóa theo giá trị thật sự bỏ đúng phần tử, và không tìm thấy trả false.
- Xóa qua iterator cập nhật danh sách; lần xóa tiếp theo chỉ hợp lệ sau khi đi tiếp.
- ListIterator cho thay cùng phần tử nhiều lần, nhưng add/remove làm thay đổi điều kiện set/remove.
- `element` không xóa, còn `remove()` và `poll()` lấy-xóa đầu hàng đợi.
- Hai lần pop cho đúng thứ tự ngăn xếp.
- Không chèn được vào hàng đợi đầy không âm thầm thay phần tử A bằng B.
- Giải phóng một chỗ cho phép thao tác chèn sau đó thành công.

Những xác nhận về trạng thái ở đây gắn với các lớp và thao tác cụ thể đã khởi tạo. Không suy ra một bảo đảm hoàn tác tự động cho mọi thao tác hàng loạt hoặc cho mọi collection tùy biến.

### 7.2. Giới hạn của thí nghiệm

Đây là kiểm tra hợp đồng trên dữ liệu nhỏ trong một luồng, không phải kiểm thử đồng thời hoặc đo hiệu năng. `ArrayList` trong ví dụ có hỗ trợ các thao tác sửa; `List.of` chỉ xuất hiện ở ca đối chiếu iterator không cho sửa và để tạo expected.

Không khẳng định mọi cách dùng sai đều phải ném một trong đúng ba ngoại lệ ở tiêu đề. Sai kiểu, null, thao tác không hỗ trợ hoặc sửa nguồn ngoài chính sách có thể dẫn đến loại lỗi khác. Cần tạo ca thử có **một điều kiện vi phạm rõ ràng**.

## 8. Quy trình gỡ lỗi: đọc phương thức, đầu vào và trạng thái

### 8.1. Khi gặp IndexOutOfBoundsException

Ghi lại:

1. Phương thức là get/set/remove theo chỉ số, add ở vị trí hay khởi tạo con trỏ?
2. Giá trị index tại lúc gọi và kích thước danh sách tại lúc đó?
3. Chỉ số tính trong danh sách gốc hay một view nhỏ hơn?
4. Chỉ số lấy từ vòng lặp, indexOf, dữ liệu nhập hay được lưu trước một thay đổi?
5. Với remove, overload nào đã được chọn?

Sửa nguyên nhân tạo địa chỉ sai. Không kẹp mọi chỉ số về đoạn hợp lệ một cách máy móc: biến chỉ số 100 thành phần tử cuối có thể làm chương trình sửa nhầm dữ liệu nhưng không còn báo lỗi.

### 8.2. Khi gặp NoSuchElementException

Xác định đúng hướng và điểm quan sát:

- Iterator đã đọc hết chưa, có vô tình gọi next hai lần không?
- ListIterator đang ở đầu hay cuối, đang đi tiến hay lùi?
- Queue/Deque thật sự rỗng hay phần tử đã bị lấy bởi một đường khác?
- Hợp đồng có cho phép rỗng không, và phương thức nên dùng ngoại lệ hay giá trị đặc biệt?

Nếu thiếu dữ liệu là một tình huống bình thường, biểu đạt nó rõ ràng. Nếu đó là vi phạm một điều kiện phải đúng, giữ thông tin giúp tìm nơi đã làm mất phần tử. Đừng bắt ngoại lệ rồi tự tạo một giá trị mặc định giả mà nghiệp vụ không cho phép.

### 8.3. Khi gặp IllegalStateException

Tên ngoại lệ không mô tả đủ trạng thái. Với iterator, ghi chuỗi `next/previous/add/set/remove` liên quan. Với hàng đợi hữu hạn, ghi sức chứa và kết quả chèn/lấy trước đó.

Một bản ghi thao tác nhỏ như sau thường hữu ích hơn chỉ in size:

```text
create iterator
next -> A
remove -> thành công
remove -> IllegalStateException
```

Size của danh sách ở cuối có thể vẫn lớn hơn 0, nhưng điều đó không cấp quyền xóa lần hai bằng cùng iterator. Điều kiện bị vi phạm là trình tự lời gọi, không phải còn dữ liệu hay không.

Không bắt `IllegalStateException` của toàn bộ một phương thức lớn rồi giả định “queue đang đầy”. Một lời gọi khác bên trong có thể là nguồn lỗi. Khoanh phạm vi thao tác và đọc stack trace.

## 9. Kiểm tra trước thao tác không tự tạo tính nguyên tử

Trong một luồng và khi không có mã khác can thiệp vào nguồn, kiểm tra index hoặc hasNext có thể giúp chọn thao tác đúng. Khi trạng thái có thể đổi giữa hai lời gọi, một phép kiểm tra trước chưa đủ.

Ví dụ minh họa một cách xử lý dễ nhầm:

```java
// Đoạn minh họa: hai lời gọi riêng, không phải một giao dịch.
if (!queue.isEmpty()) {
    String value = queue.remove();
    System.out.println(value);
}
```

Với hàng đợi được nhiều bên lấy phần tử, queue có thể rỗng sau lần kiểm tra isEmpty. Nếu API hàng đợi đồng thời được chọn có cung cấp thao tác lấy an toàn và yêu cầu cho phép không có kết quả, hãy gọi `poll()` rồi xử lý chính kết quả của lời gọi đó. Chọn collection đồng thời hoặc đồng bộ đúng phạm vi vẫn là yêu cầu riêng; đổi `remove` thành `poll` không làm một `ArrayDeque` chia sẻ không đồng bộ trở nên an toàn.

Tương tự, kiểm tra `index < list.size()` rồi gọi `get(index)` không bảo vệ một List đang bị sửa không đồng bộ. Cần giải quyết quyền truy cập nguồn, không dùng vòng lặp bắt IndexOutOfBoundsException rồi thử lại để thay cho đồng bộ.

Với iterator, sửa nguồn ngoài đường được hợp đồng cho phép còn có thể dẫn tới `ConcurrentModificationException` hoặc hành vi không được xác định. Những bảo đảm về hasNext/next phải được hiểu trong điều kiện sử dụng hợp lệ của iterator.

## 10. Thiết kế các ca kiểm thử có sức phân biệt

### 10.1. Kiểm tra cả hai phía của ranh giới

Với danh sách có kích thước n, chọn các điểm như `-1`, `0`, `n - 1`, `n` và `n + 1`, nhưng tính ý nghĩa từng điểm theo n thực tế:

- Khi n = 0, `n - 1` cũng là -1; không còn ca “phần tử cuối hợp lệ”.
- Khi n = 1, chỉ số phần tử duy nhất là 0, vị trí chèn có cả 0 và 1.
- Với n lớn hơn, index = n phân biệt rõ thao tác đọc/thay với thao tác chèn.

Không đếm các giá trị trùng nhau trong bảng mẫu thành bằng chứng đã thử thêm một vùng hành vi mới.

### 10.2. Kiểm tra chuyển trạng thái, không chỉ trạng thái đầu

| Nhóm | Ca chưa đủ | Ca bổ sung quan trọng |
| --- | --- | --- |
| Chỉ số | Chỉ thử get(0) trên List có dữ liệu | Rỗng, chỉ số âm, index = size và add tại size |
| Iterator | Chỉ thử next khi còn dữ liệu | Cạn; remove trước next; double remove; remove sau next cuối |
| ListIterator | Chỉ thử set ngay sau next | set trước khi đi, sau add/remove, set lặp và remove sau previous |
| Queue | Chỉ thử lấy từ queue có dữ liệu | Cặp remove/poll, element/peek khi rỗng |
| Sức chứa | Chỉ thử add khi còn chỗ | add thất bại, offer false, lấy ra rồi chèn lại |
| Ngăn xếp | Chỉ thử pop một lần | Rỗng, một phần tử, hai phần tử và thứ tự LIFO |

Với ListIterator, các phép quan sát `nextIndex()` và `previousIndex()` cũng hữu ích để chẩn đoán vị trí, nhưng việc biết index không thay điều kiện “đã có phần tử vừa trả về” của set/remove.

### 10.3. Không đặt kỳ vọng mạnh hơn hợp đồng

Trong kiểm thử ứng dụng:

- Chỉ bắt ngoại lệ quanh đúng lời gọi đang kiểm tra, sau khi đã chuẩn bị dữ liệu hợp lệ.
- Khi hợp đồng công bố IndexOutOfBoundsException, không bắt buộc một lớp con nội bộ hay chuỗi thông báo cụ thể, trừ khi API của chính ứng dụng cam kết điều đó.
- Không dựa vào số dòng stack trace hoặc tên lớp iterator nội bộ; chúng có thể đổi theo JDK.
- Không trộn lỗi chỉ số, thao tác không hỗ trợ và lỗi trạng thái trong cùng một ca rồi suy ra thứ tự kiểm tra cho mọi triển khai.
- Kiểm tra nội dung, vị trí hoặc số lần xử lý sau thao tác hợp lệ, không chỉ kiểm tra chương trình “không ném lỗi”.
- Không dùng một lần chạy không lỗi làm bằng chứng nguồn đang bị sửa đồng thời là an toàn.

Trong JUnit Jupiter, ý tưởng tương ứng là dùng `assertThrows` cho một lambda ngắn và assertion khác cho trạng thái sau thao tác. Chương trình của bài dùng hàm trợ giúp tự kiểm tra để chạy độc lập, nên không yêu cầu thiết lập JUnit.

## 11. Nhận diện các lỗi ở gần nhưng khác nguyên nhân

Ba ngoại lệ trong bài đều là ngoại lệ không bắt buộc khai báo hay bắt bằng checked exception. Điều đó không có nghĩa chương trình nên bỏ qua chúng; nhiều ca phản ánh lỗi sử dụng API cần sửa ở nguồn.

| Tình huống | Loại vấn đề cần xem xét |
| --- | --- |
| Chỉ số List nằm ngoài miền phương thức | IndexOutOfBoundsException |
| Iterator.next hoặc Queue.remove không có phần tử để trả | NoSuchElementException |
| Iterator.remove chưa đúng trình tự; add vào ArrayBlockingQueue đầy | IllegalStateException |
| add vào List.of hoặc remove qua iterator không hỗ trợ sửa | UnsupportedOperationException |
| Sửa nguồn ngoài chính sách iterator fail-fast | ConcurrentModificationException có thể phát hiện vi phạm |
| Tự mở hộp kết quả null từ poll | NullPointerException |

Bảng là định hướng theo các tình huống đã nêu, không phải danh sách loại trừ mọi lỗi khác. Khi đối tượng đồng thời bị dùng sai nhiều điều kiện, đọc hợp đồng cụ thể thay vì chọn ngoại lệ theo cảm giác.

Một cách sửa tốt phải trả lời được hai điều: điều kiện nào cần đúng trước thao tác, và ai chịu trách nhiệm duy trì điều kiện đó. Người gọi có thể cần kiểm tra đầu vào; bên sở hữu collection có thể cần cung cấp API phù hợp; thuật toán có thể cần đổi cách duyệt hoặc cách xử lý trạng thái rỗng/đầy.

## 12. Tự kiểm tra và thực hành

### Câu 1: List có ba phần tử, vì sao add(3, value) hợp lệ còn set(3, value) không?

Add dùng vị trí chèn, có cả vị trí sau phần tử cuối. Set cần một phần tử đang tồn tại; chỉ số phần tử chỉ tới 2.

### Câu 2: hasNext trả false có đồng nghĩa remove phải ném IllegalStateException không?

Không. Nếu next vừa trả phần tử cuối và chưa xóa phần tử đó, remove vẫn có thể hợp lệ với iterator hỗ trợ xóa. HasNext mô tả phần tử tiếp theo, còn remove dựa vào phần tử đã trả về.

### Câu 3: Đổi Queue.remove thành poll có đủ sửa lỗi không?

Chưa. Phải quyết định rỗng có hợp lệ không và xử lý null. Cũng cần giữ đúng chính sách đồng thời của collection; hai tên phương thức không thay thế thiết kế truy cập nguồn.

### Câu 4: ListIterator có thể set hai lần sau một next không?

Có, nếu nó hỗ trợ set và chưa có add/remove xen vào. Một lần set không tiêu thụ quyền thay thế như cách remove làm mất điều kiện xóa lần nữa.

### Câu 5: IllegalStateException có luôn liên quan đến iterator không?

Không. Hàng đợi hữu hạn đầy là một ví dụ khác. Cần nhìn phương thức ném lỗi và trạng thái của đối tượng đó.

### Bài thực hành

1. Thêm các ca kiểm tra get/set/add trên List một phần tử; ghi riêng miền chỉ số phần tử và vị trí chèn.
2. Viết một phép thử chứng minh `remove(1)` và `remove(Integer.valueOf(1))` có thể xóa hai thứ khác nhau trên cùng dữ liệu ban đầu.
3. Theo dõi `nextIndex()` trước và sau chuỗi ListIterator: add, next, set, remove, previous. Dự đoán danh sách sau từng bước trước khi chạy.
4. Tạo deque có hai phần tử và so sánh getFirst, peekFirst, removeFirst, pollFirst; xác nhận thao tác nào giữ nguyên kích thước.
5. Với hàng đợi sức chứa 2, viết ca đầy rồi lấy một phần tử và chèn lại. Đối chiếu cả kết quả boolean, ngoại lệ và nội dung theo thứ tự.
6. Tạo một lỗi gọi next hai lần trong vòng while, thử dữ liệu có 0, 1, 2 và 3 phần tử, rồi sửa để mỗi phần tử được xử lý đúng một lần.
7. Thiết kế một hàm có yêu cầu “rỗng là bình thường” và một hàm có yêu cầu “phải có phần tử”. Chọn rõ API và kết quả lỗi phù hợp cho từng hàm.

Mục tiêu là nhìn được địa chỉ, phần tử khả dụng và trình tự thao tác như ba điều kiện riêng. Khi một điều kiện sai, sửa cách tạo hoặc duy trì điều kiện đó, rồi kiểm thử lại cả kết quả lẫn thay đổi dữ liệu.
