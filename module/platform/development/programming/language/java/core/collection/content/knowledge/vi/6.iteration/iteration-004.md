# ListIterator: duyệt hai chiều, chỉ số và con trỏ

`Iterator` giúp lấy lần lượt các phần tử theo một chiều. Với danh sách, đôi khi ta cần đi tới, quay lại, biết vị trí kế tiếp hoặc chỉnh sửa gần vị trí đang duyệt. `ListIterator<E>` cung cấp các khả năng đó.

Điểm cần nắm trước mọi tên phương thức là:

> **Con trỏ của ListIterator nằm giữa hai phần tử, không nằm trên một phần tử hiện tại.**

Mô hình này giải thích vì sao `next()` rồi `previous()` có thể trả về cùng một phần tử, vì sao có thể tạo iterator tại `list.size()`, và vì sao `remove()` phải nhớ phần tử được trả về gần nhất.

Bài dùng API Java 17. Ba chương trình hoàn chỉnh đã được biên dịch bằng `--release 17` và chạy để đối chiếu stdout. Các đoạn mã rút gọn khác minh họa thao tác trong một phương thức, không phải tệp chạy độc lập.

Sau bài học, bạn có thể:

- Vẽ vị trí con trỏ trước và sau `next`, `previous`.
- Phân biệt vị trí khởi tạo iterator với chỉ số phần tử.
- Dùng đúng `nextIndex` và `previousIndex`, kể cả ở các biên.
- Duyệt xuôi, ngược và đổi chiều có chủ đích.
- Theo dõi riêng con trỏ và phần tử được trả về gần nhất khi chỉnh sửa.

## 1. ListIterator nằm ở đâu trong mô hình collection?

`ListIterator<E>` mở rộng `Iterator<E>`, bổ sung khả năng phù hợp với một chuỗi phần tử có thứ tự vị trí.

| Khả năng | Iterator | ListIterator |
| --- | --- | --- |
| Kiểm tra còn phần tử phía trước | `hasNext()` | `hasNext()` |
| Lấy và tiến tới | `next()` | `next()` |
| Xóa phần tử vừa trả về, nếu hỗ trợ | `remove()` | `remove()` |
| Kiểm tra còn phần tử phía sau | Không có phương thức tương ứng | `hasPrevious()` |
| Lấy và lùi lại | Không có phương thức tương ứng | `previous()` |
| Hỏi chỉ số ở hai phía con trỏ | Không | `nextIndex()`, `previousIndex()` |
| Thay phần tử vừa trả về, nếu hỗ trợ | Không | `set(element)` |
| Chèn tại vị trí con trỏ, nếu hỗ trợ | Không | `add(element)` |

Các cách lấy từ một `List<E>`:

```java
ListIterator<String> fromBeginning = values.listIterator();
ListIterator<String> fromPosition = values.listIterator(2);
```

Đoạn minh họa giả định `values` có kiểu `List<String>`, kích thước ít nhất là `2`, và đã import `ListIterator`.

Không phải mọi `Collection` đều cung cấp `ListIterator`. Chẳng hạn, một `Set` không có chỉ số danh sách và không tự có hợp đồng này.

Enhanced for trên danh sách chỉ cần cơ chế `Iterator`; nó không cho người viết điều khiển trực tiếp các khả năng hai chiều của `ListIterator`.

## 2. Mô hình con trỏ: n phần tử có n + 1 vị trí

Với danh sách:

```text
[A, B, C]
```

có bốn vị trí con trỏ:

```text
| A B C
A | B C
A B | C
A B C |
```

Dấu `|` biểu diễn khoảng trống mà con trỏ đang nằm.

Gọi vị trí đó là `p`:

- Có `p` phần tử nằm trước con trỏ.
- Nếu còn phần tử theo chiều next, `next()` trả phần tử ở chỉ số `p`.
- Nếu còn phần tử theo chiều previous, `previous()` trả phần tử ở chỉ số `p - 1`.

Khi thao tác, hãy ưu tiên hai hướng tường minh:

- **Chiều next:** đi từ đầu tới cuối.
- **Chiều previous:** đi từ cuối về đầu.

### Bảng trạng thái cho danh sách ba phần tử

| Con trỏ | nextIndex | previousIndex | hasNext | hasPrevious |
| --- | --- | --- | --- | --- |
| `\| A B C` | `0` | `-1` | `true` | `false` |
| `A \| B C` | `1` | `0` | `true` | `true` |
| `A B \| C` | `2` | `1` | `true` | `true` |
| `A B C \|` | `3` | `2` | `false` | `true` |

Có thể hình dung:

```text
nextIndex()     = p
previousIndex() = p - 1
```

Khi dùng một iterator còn hợp lệ, hai chỉ số mô tả các vị trí liền kề của cùng con trỏ. Chúng không phải hai con trỏ riêng.

## 3. Khởi tạo ở một vị trí khác đầu danh sách

`listIterator(index)` đặt con trỏ ngay trước phần tử có chỉ số đó.

Với `[A, B, C]`:

```java
ListIterator<String> cursor = values.listIterator(1);
```

tạo trạng thái:

```text
A | B C
```

Ngay sau đó:

- `next()` sẽ trả `B`.
- `previous()` sẽ trả `A`.
- `nextIndex()` là `1`.
- `previousIndex()` là `0`.

### Vì sao listIterator(size) hợp lệ?

Vị trí khởi tạo được phép nằm trong đoạn:

```text
0 <= index <= list.size()
```

`index == size` nghĩa là con trỏ ở cuối danh sách, sau phần tử cuối. Không có phần tử để `next`, nhưng có thể bắt đầu `previous`.

Ngược lại, `get(size)` không hợp lệ vì `get` yêu cầu **một phần tử** tại chỉ số đó, mà chỉ số phần tử cuối chỉ là `size - 1`.

| Lời gọi trên danh sách kích thước n | Miền chỉ số hợp lệ |
| --- | --- |
| `get(index)` | `0..n-1` |
| `listIterator(index)` | `0..n` |

Với danh sách rỗng, chỉ có một vị trí iterator hợp lệ là `0`. Khởi tạo với chỉ số âm hoặc lớn hơn kích thước gây `IndexOutOfBoundsException`.

## 4. Next và previous vừa trả phần tử vừa di chuyển

Bắt đầu tại:

```text
A | B C
```

Gọi `next()`:

```text
Giá trị trả về: B
Con trỏ mới:   A B | C
```

Gọi tiếp `previous()`:

```text
Giá trị trả về: B
Con trỏ mới:   A | B C
```

Hai lời gọi trả về cùng `B` vì con trỏ vừa đi qua phần tử đó rồi đi ngược lại qua chính nó.

### Previous không có nghĩa “lấy phần tử khác với lần next vừa rồi”

Một nhầm lẫn thường gặp là nghĩ sau khi `next()` trả `B`, `previous()` phải trả `A`. Mô hình con trỏ cho thấy điều đó sai: sau lần next, `B` nằm ngay bên trái con trỏ nên previous phải đi qua `B`.

Muốn lấy `A` theo chuỗi thao tác này, cần gọi previous thêm lần nữa.

### Các phương thức hỏi trạng thái không làm con trỏ di chuyển

- `hasNext()`.
- `hasPrevious()`.
- `nextIndex()`.
- `previousIndex()`.

Chúng không thay thế cho `next()` hoặc `previous()`. Một vòng lặp chỉ hỏi trạng thái mà không có thao tác tiến/lùi phù hợp sẽ không tự duyệt qua phần tử.

### Đổi chiều có thể khiến cùng phần tử được xử lý nhiều lần

Nếu cứ luân phiên `next()`, `previous()` ở cùng một khoảng, bạn có thể lấy lại cùng phần tử mãi.

Đây không phải lỗi của iterator. Chương trình cần một điều kiện hoặc chiến lược thay đổi hướng rõ ràng để thực sự tiến trong bài toán của mình.

## 5. Chương trình hoàn chỉnh: đi tới rồi quay lại

Tạo tệp **`ListCursorWalkDemo.java`**:

```java
import java.util.List;
import java.util.ListIterator;

public class ListCursorWalkDemo {
    public static void main(String[] args) {
        List<String> values = List.of("A", "B", "C");
        ListIterator<String> cursor = values.listIterator(1);

        show("initial", cursor);
        System.out.println("next = " + cursor.next());
        show("after next", cursor);
        System.out.println("previous = " + cursor.previous());
        show("after previous", cursor);

        while (cursor.hasNext()) {
            System.out.println("forward = " + cursor.next());
        }
        show("at end", cursor);

        while (cursor.hasPrevious()) {
            System.out.println("backward = " + cursor.previous());
        }
        show("at beginning", cursor);
    }

    private static void show(String label, ListIterator<String> cursor) {
        System.out.println(label
                + ": nextIndex=" + cursor.nextIndex()
                + ", previousIndex=" + cursor.previousIndex()
                + ", hasNext=" + cursor.hasNext()
                + ", hasPrevious=" + cursor.hasPrevious());
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 ListCursorWalkDemo.java
java -Dfile.encoding=UTF-8 ListCursorWalkDemo
```

Stdout:

```text
initial: nextIndex=1, previousIndex=0, hasNext=true, hasPrevious=true
next = B
after next: nextIndex=2, previousIndex=1, hasNext=true, hasPrevious=true
previous = B
after previous: nextIndex=1, previousIndex=0, hasNext=true, hasPrevious=true
forward = B
forward = C
at end: nextIndex=3, previousIndex=2, hasNext=false, hasPrevious=true
backward = C
backward = B
backward = A
at beginning: nextIndex=0, previousIndex=-1, hasNext=true, hasPrevious=false
```

### Theo dõi các giai đoạn

1. Iterator bắt đầu ở khoảng `A | B C`.
2. `next` trả `B` và đưa con trỏ sang phải `B`.
3. `previous` trả lại `B`, đưa con trỏ về khoảng ban đầu.
4. Vòng lặp xuôi từ vị trí đó lấy `B`, `C`; nó không tự quay về đầu để lấy `A`.
5. Ở cuối, `nextIndex` bằng `size`, nhưng `hasNext` là `false`.
6. Vòng lặp ngược lấy `C`, `B`, `A`.
7. Ở đầu, `previousIndex` là `-1` và `hasPrevious` là `false`.

Danh sách từ `List.of` không cho sửa đổi, nhưng vẫn hỗ trợ việc di chuyển iterator trong ví dụ. Khả năng duyệt và khả năng chỉnh sửa là hai phần hợp đồng cần phân biệt.

## 6. Dùng chỉ số để mô tả vị trí, không để đoán trạng thái

### nextIndex không phải lúc nào cũng là chỉ số có thể get

Ở cuối danh sách:

```text
nextIndex() == list.size()
```

Đây là giá trị báo vị trí kế tiếp nếu có, không phải một chỉ số phần tử hợp lệ để gọi `get`.

Tương tự, `previousIndex() == -1` ở đầu không có nghĩa có một phần tử tại `-1`.

Cách dùng đúng là kiểm tra hướng còn phần tử:

```java
if (cursor.hasNext()) {
    int index = cursor.nextIndex();
    String value = cursor.next();
    System.out.println(index + " -> " + value);
}
```

Hoặc theo chiều ngược:

```java
if (cursor.hasPrevious()) {
    int index = cursor.previousIndex();
    String value = cursor.previous();
    System.out.println(index + " -> " + value);
}
```

Đọc chỉ số **trước** thao tác giúp lưu đúng vị trí của phần tử sắp được trả về.

### Chỉ số sau thao tác đã mô tả khoảng mới

Nếu gọi `next()` rồi mới đọc `nextIndex()`, chỉ số đó là vị trí của phần tử kế tiếp nữa, không phải phần tử vừa nhận.

Ví dụ:

```text
Trước next: nextIndex = 1
next trả: B tại chỉ số 1
Sau next: nextIndex = 2
```

Không nên dùng tên chung như “currentIndex” mà không chỉ rõ nó là chỉ số của phần tử nào hoặc được đọc trước hay sau thao tác.

## 7. Con trỏ khác phần tử được trả về gần nhất

Để hiểu chỉnh sửa, cần theo dõi hai trạng thái riêng:

1. **Vị trí con trỏ:** khoảng trống giữa các phần tử.
2. **Phần tử được trả về gần nhất:** do `next()` hoặc `previous()` vừa cung cấp.

`set` và `remove` tác động tới phần tử được trả về gần nhất, với điều kiện trạng thái cho phép. Chúng không đơn giản có nghĩa “sửa/xóa phần tử bên phải con trỏ”.

### Vì sao cần nhớ chiều di chuyển?

- Sau `next()`, phần tử vừa trả về nằm bên trái con trỏ.
- Sau `previous()`, phần tử vừa trả về nằm bên phải con trỏ.

Vì vậy, cùng gọi `remove()` nhưng cách điều chỉnh chỉ số con trỏ khác nhau tùy thao tác trả về trước đó.

Nếu chỉ lưu “iterator đang ở chỉ số 2” mà quên lịch sử next/previous, bạn chưa có đủ thông tin để dự đoán chính xác phần tử bị `set` hoặc `remove`.

### Đi rồi quay lại không nhất thiết khôi phục toàn bộ trạng thái chỉnh sửa

`next()` rồi `previous()` có thể đưa **con trỏ** về cùng khoảng, nhưng lịch sử phần tử vừa trả về đã được cập nhật.

Do đó, không nên dùng chuỗi này như một phép “nhìn thử hoàn toàn không tác động” nếu sau đó còn dựa vào điều kiện của `set` hoặc `remove`. Các phương thức hỏi chỉ số không gây loại thay đổi lịch sử đó.

## 8. Set, add và remove ảnh hưởng thế nào đến con trỏ?

Các thao tác sau là tùy chọn. Chỉ sử dụng khi iterator của danh sách thực tế hỗ trợ chúng.

### Set: thay phần tử vừa được trả về

Sau một `next` hoặc `previous` hợp lệ:

```java
cursor.set("replacement");
```

thay giá trị của phần tử vừa được trả về.

- Không làm tăng hoặc giảm kích thước.
- Không di chuyển con trỏ.
- Không tự lấy thêm phần tử.
- Không hợp lệ nếu chưa có phần tử được next/previous trả về trong trạng thái cần thiết.
- Không hợp lệ ngay sau `add` hoặc `remove` khi chưa gọi next/previous trở lại.

Một lần `set` hợp lệ không tự xóa quyền thay thế tiếp phần tử đó. Quy tắc trạng thái không phải “mọi thao tác chỉ được gọi một lần”; mỗi thao tác có điều kiện riêng.

### Add: chèn ngay trước con trỏ

Nếu đang có:

```text
A B | C
```

gọi `add("X")` tạo:

```text
A B X | C
```

Hệ quả:

- Phần tử mới nằm ngay trước con trỏ, phía mà `previous` sẽ đi tới.
- `next()` tiếp theo vẫn trả `C`, như trước lần chèn.
- `previous()` tiếp theo sẽ trả phần tử `X` vừa chèn.
- `nextIndex` tăng một.
- Không thể gọi ngay `set` hoặc `remove` dựa trên phần tử cũ; cần một lần next/previous phù hợp trước.

`add` không có nghĩa phần tử vừa chèn tự trở thành phần tử vừa được trả về. Đây là hai trạng thái khác nhau.

### Remove sau next

Ví dụ:

```text
A B | C
```

Nếu khoảng này có được sau khi `next()` vừa trả `B`, thì `remove()` xóa `B`:

```text
A | C
```

`nextIndex` giảm một vì phần tử nằm trước con trỏ đã bị loại bỏ.

### Remove sau previous

Nếu có:

```text
A B | C D
```

sau khi `previous()` vừa trả `C`, thì `remove()` xóa `C`:

```text
A B | D
```

`nextIndex` giữ nguyên giá trị số trong tình huống này, vì phần tử vừa bị xóa nằm ngay sau con trỏ.

### Không remove hai lần cho cùng một lần trả về

Sau khi xóa, không còn phần tử vừa trả về hợp lệ để xóa tiếp. Muốn `remove` tiếp, cần gọi next/previous để nhận một phần tử khác trước.

Tương tự, `set` sau `remove` mà chưa có lần trả về mới cũng không hợp lệ.

## 9. Chương trình hoàn chỉnh: theo dõi chỉnh sửa và chỉ số

Tạo tệp **`ListCursorEditDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.ListIterator;

public class ListCursorEditDemo {
    public static void main(String[] args) {
        List<String> values = new ArrayList<>(List.of("A", "B", "C"));
        ListIterator<String> cursor = values.listIterator(1);

        System.out.println("next = " + cursor.next());
        cursor.set("B*");
        show("after set", values, cursor);

        cursor.add("X");
        show("after add", values, cursor);

        try {
            cursor.set("blocked");
        } catch (IllegalStateException exception) {
            System.out.println("set immediately after add = "
                    + exception.getClass().getSimpleName());
        }

        System.out.println("previous = " + cursor.previous());
        cursor.remove();
        show("after remove(previous)", values, cursor);

        System.out.println("next = " + cursor.next());
        cursor.remove();
        show("after remove(next)", values, cursor);

        try {
            cursor.remove();
        } catch (IllegalStateException exception) {
            System.out.println("remove twice = "
                    + exception.getClass().getSimpleName());
        }
    }

    private static void show(
            String label, List<String> values, ListIterator<String> cursor) {
        System.out.println(label + ": " + values
                + ", nextIndex=" + cursor.nextIndex()
                + ", previousIndex=" + cursor.previousIndex());
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 ListCursorEditDemo.java
java -Dfile.encoding=UTF-8 ListCursorEditDemo
```

Stdout:

```text
next = B
after set: [A, B*, C], nextIndex=2, previousIndex=1
after add: [A, B*, X, C], nextIndex=3, previousIndex=2
set immediately after add = IllegalStateException
previous = X
after remove(previous): [A, B*, C], nextIndex=2, previousIndex=1
next = C
after remove(next): [A, B*], nextIndex=2, previousIndex=1
remove twice = IllegalStateException
```

### Diễn biến theo mô hình con trỏ

| Thao tác vừa hoàn tất | Dữ liệu và con trỏ | nextIndex |
| --- | --- | --- |
| Khởi tạo tại 1 | `A \| B C` | `1` |
| `next()` trả B | `A B \| C` | `2` |
| `set("B*")` | `A B* \| C` | `2` |
| `add("X")` | `A B* X \| C` | `3` |
| `previous()` trả X | `A B* \| X C` | `2` |
| `remove()` xóa X | `A B* \| C` | `2` |
| `next()` trả C | `A B* C \|` | `3` |
| `remove()` xóa C | `A B* \|` | `2` |

Hai ngoại lệ trong chương trình là lỗi trạng thái có chủ đích:

- `set` ngay sau `add` chưa có một phần tử mới được next/previous trả về.
- `remove` lần thứ hai chưa có lần trả về mới.

Danh sách thực tế là `ArrayList`, hỗ trợ các chỉnh sửa qua iterator được dùng trong chương trình. Không nên lấy hỗ trợ đó để suy rộng sang mọi danh sách.

## 10. Đầu, cuối, danh sách rỗng và các ngoại lệ

| Tình huống | Kết quả cần hiểu |
| --- | --- |
| `next()` khi không còn phía next | `NoSuchElementException` |
| `previous()` khi không còn phía previous | `NoSuchElementException` |
| Tạo iterator ở vị trí âm hoặc lớn hơn size | `IndexOutOfBoundsException` |
| `set/remove` khi không đủ trạng thái | `IllegalStateException`, trong iterator hỗ trợ thao tác và kiểm tra trạng thái đó |
| Thao tác chỉnh sửa không được hỗ trợ | `UnsupportedOperationException` |

Một thao tác có thể đồng thời vi phạm nhiều điều kiện. Không nên thiết kế chương trình dựa vào việc mọi lớp triển khai phải ưu tiên cùng một loại kiểm tra trong mọi tình huống không hợp lệ. Hãy gọi thao tác đúng trạng thái trên nguồn được xác định hỗ trợ.

### Chương trình hoàn chỉnh

Tạo tệp **`ListCursorBoundaryDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.ListIterator;
import java.util.NoSuchElementException;

public class ListCursorBoundaryDemo {
    public static void main(String[] args) {
        List<String> empty = new ArrayList<>();
        ListIterator<String> cursor = empty.listIterator(0);

        System.out.println("empty hasNext = " + cursor.hasNext());
        System.out.println("empty hasPrevious = " + cursor.hasPrevious());
        System.out.println("empty nextIndex = " + cursor.nextIndex());
        System.out.println("empty previousIndex = " + cursor.previousIndex());

        try {
            cursor.next();
        } catch (NoSuchElementException exception) {
            System.out.println("empty next = "
                    + exception.getClass().getSimpleName());
        }

        try {
            cursor.previous();
        } catch (NoSuchElementException exception) {
            System.out.println("empty previous = "
                    + exception.getClass().getSimpleName());
        }

        try {
            empty.listIterator(1);
        } catch (IndexOutOfBoundsException exception) {
            System.out.println("invalid start position = "
                    + exception.getClass().getSimpleName());
        }

        ListIterator<String> readOnly = List.of("A", "B").listIterator(2);
        System.out.println("read-only previous = " + readOnly.previous());

        try {
            readOnly.set("changed");
        } catch (UnsupportedOperationException exception) {
            System.out.println("read-only set = "
                    + exception.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy:

```text
javac -encoding UTF-8 --release 17 ListCursorBoundaryDemo.java
java -Dfile.encoding=UTF-8 ListCursorBoundaryDemo
```

Stdout:

```text
empty hasNext = false
empty hasPrevious = false
empty nextIndex = 0
empty previousIndex = -1
empty next = NoSuchElementException
empty previous = NoSuchElementException
invalid start position = IndexOutOfBoundsException
read-only previous = B
read-only set = UnsupportedOperationException
```

### Những điểm được kiểm chứng

- Danh sách rỗng có một khoảng con trỏ tại `0`.
- Không còn phần tử theo cả hai chiều.
- `nextIndex` là `0`, `previousIndex` là `-1`.
- Gọi next/previous không có phần tử đều thất bại bằng ngoại lệ phù hợp.
- Tạo iterator ở vị trí `1` trên danh sách rỗng là vượt giới hạn.
- Iterator từ `List.of("A", "B")` có thể duyệt ngược từ cuối và nhận `B`.
- Dù đã có phần tử vừa trả về, `set` vẫn không được hỗ trợ vì danh sách này không cho sửa đổi.

Không có dữ liệu trong danh sách rỗng khác với một danh sách có phần tử `null`. Giá trị `null` không được dùng làm dấu báo hết của `next` hoặc `previous`.

## 11. Hỗ trợ chỉnh sửa phụ thuộc nguồn và iterator

| Nguồn thường gặp | Duyệt hai chiều | set qua iterator | add/remove qua iterator |
| --- | --- | --- | --- |
| `ArrayList` thông thường | Có | Có | Có |
| `LinkedList` thông thường | Có | Có | Có |
| Danh sách từ `Arrays.asList` | Có | Có | Không, do kích thước cố định |
| Danh sách từ `List.of` | Có | Không | Không |
| Iterator snapshot của `CopyOnWriteArrayList` | Có | Không | Không |

Bảng nhấn mạnh rằng ngay cả khi bản thân danh sách có thể thay đổi, iterator của nó vẫn có thể không hỗ trợ chỉnh sửa.

Với `Arrays.asList`, thay phần tử qua `set` tác động đến dữ liệu được chia sẻ với mảng nguồn. Khả năng thay phần tử không có nghĩa danh sách có thể tăng hoặc giảm kích thước.

Với iterator snapshot, dữ liệu được duyệt là một góc nhìn có hợp đồng riêng tại thời điểm tạo iterator. Không tự cho rằng các chỉ số nó báo luôn mô tả danh sách sống đang được sửa ở nơi khác.

Khi viết phương thức nhận `List`, hãy ghi rõ nó cần hỗ trợ chỉ duyệt, thay phần tử hay cả thêm/xóa. Chỉ có kiểu `List` chưa đủ để bảo đảm mọi thao tác thay đổi sẽ thành công.

## 12. Không thay đổi cấu trúc từ bên ngoài rồi chờ con trỏ tự sửa

Với iterator của những lớp như `ArrayList`, việc thêm hoặc xóa trực tiếp qua danh sách sau khi tạo iterator có thể khiến iterator bị phát hiện là không còn hợp lệ.

Ví dụ về cách tổ chức cần tránh:

```java
ListIterator<String> cursor = values.listIterator();
values.add("new");
cursor.next();
```

Nếu đang duyệt bằng một iterator có cơ chế phát hiện sửa đổi, hãy dùng các thao tác chỉnh sửa được hỗ trợ của **chính iterator đó** trong lượt duyệt.

Những điểm cần nhớ:

- Có thể gặp `ConcurrentModificationException` ngay trong một luồng.
- Cơ chế phát hiện sửa đổi là cách hỗ trợ tìm lỗi, không phải khóa đồng bộ hoặc bảo đảm an toàn luồng.
- Không được dựa vào việc mọi thay đổi sai đều chắc chắn bị phát hiện ở cùng một phương thức.
- Hai iterator của cùng danh sách không mặc định phối hợp chỉnh sửa với nhau. Một iterator sửa cấu trúc có thể làm iterator còn lại không còn hợp lệ.
- Snapshot hoặc iterator chuyên biệt có hợp đồng khác; cần đọc đúng loại nguồn thực tế.

### Chỉ số iterator không phải mã định danh ổn định của phần tử

Khi chèn hoặc xóa, chỉ số các phần tử có thể thay đổi. Không nên lưu một `nextIndex` rồi coi nó là danh tính lâu dài của một đối tượng.

Nếu cần nhận diện công việc, người dùng hoặc bản ghi sau nhiều thay đổi, hãy dùng mã định danh phù hợp. Chỉ số mô tả vị trí trong một trạng thái danh sách, không thay thế định danh nghiệp vụ.

## 13. Hiệu quả và cách sử dụng phù hợp

### Với ArrayList

- Di chuyển next/previous và thay phần tử có chi phí trực tiếp theo vị trí trong cấu trúc mảng.
- Chèn hoặc xóa ở giữa thường cần dịch các phần tử.
- Dùng `ListIterator` không biến thao tác chèn giữa danh sách thành thao tác không phải di chuyển dữ liệu.

### Với LinkedList

- Khởi tạo iterator ở một vị trí cần tìm tới nút tương ứng.
- Sau khi đã ở vị trí đó, đi tiếp hoặc lùi theo liên kết không cần tìm lại bằng chỉ số cho từng bước.
- Chèn hoặc xóa qua iterator tại vị trí đã biết có thể nối lại liên kết mà không phải tìm lại từ đầu theo chỉ số.

Các đặc tính này thuộc lớp triển khai; giao diện `ListIterator` không tự hứa cùng độ phức tạp cho mọi danh sách.

### Tránh khởi tạo lại iterator cho từng phần tử

Nếu muốn duyệt một đoạn danh sách liên kết, lấy một iterator tại điểm bắt đầu rồi tiến/lùi. Việc lặp đi lặp lại `listIterator(index)` có thể tạo lại chi phí tìm vị trí nhiều lần.

### Khi nào nên dùng?

| Nhu cầu | Lựa chọn phù hợp |
| --- | --- |
| Chỉ đọc tuần tự toàn bộ danh sách | Enhanced for hoặc iterator thông thường thường đủ |
| Cần đi tới rồi quay lại trên cùng lượt duyệt | `ListIterator` |
| Cần bắt đầu gần giữa và duyệt hai chiều | `listIterator(startPosition)` |
| Cần thay hoặc chèn gần vị trí đang duyệt | `ListIterator`, khi nguồn hỗ trợ |
| Cần truy cập một vị trí bất kỳ độc lập | Có thể dùng `get` nếu phù hợp cấu trúc |
| Cần duyệt ngược chỉ để đọc | Iterator tại `size` rồi previous là một cách rõ ràng |

Chọn `ListIterator` khi trạng thái con trỏ thực sự giúp giải bài toán. Không cần tăng độ phức tạp của một vòng lặp chỉ đọc nếu bạn không cần các khả năng bổ sung.

## 14. Lỗi thường gặp

### Tưởng con trỏ đang trỏ vào phần tử vừa lấy

Con trỏ nằm giữa phần tử; “phần tử vừa lấy” là trạng thái khác. Hãy vẽ dấu `|` sau từng bước để tránh suy đoán sai.

### Tưởng next rồi previous phải trả hai phần tử khác nhau

Hai thao tác ngược liên tiếp thường đi qua cùng phần tử theo hai hướng. Muốn tiến sang phần tử khác, phải thay đổi chuỗi thao tác có chủ đích.

### Gọi previous trên iterator mới tạo ở đầu

Ở vị trí `0`, không có phần tử bên previous. Muốn duyệt ngược toàn bộ, tạo iterator ở `list.size()`.

### Dùng nextIndex bằng size để gọi get

`size` là vị trí con trỏ hợp lệ ở cuối, không phải chỉ số phần tử. Dựa vào `hasNext` hoặc `hasPrevious` trước khi lấy.

### Dùng add rồi remove để mong xóa ngay phần tử vừa chèn

`add` không trả về phần tử qua next/previous và làm mất điều kiện set/remove dựa vào lần trả về cũ. Nếu cần thao tác với phần tử mới, phải di chuyển và lấy nó theo đúng chiều trước.

### Nghĩ set luôn thay phần tử phía next

`set` thay phần tử vừa được next/previous trả về trong trạng thái hợp lệ. Nó có thể nằm ở hai phía con trỏ tùy chiều đã đi.

### Nhầm duyệt hai chiều với không cần điều kiện dừng

Các vòng lặp đi tới rồi lùi lại có thể lặp mãi quanh cùng vị trí. Phải xác định hướng, phạm vi và điều kiện kết thúc.

### Nghĩ iterator tự cập nhật theo mọi thay đổi của list

Không có bảo đảm đó. Giữ thao tác trong hợp đồng của iterator và nguồn, nhất là khi có nhiều lượt duyệt hoặc nhiều bên sửa.

## 15. Thực hành

### Bài 1: điền bảng con trỏ

Với `[10, 20, 30, 40]`, tạo iterator tại vị trí `2`, rồi thực hiện:

```text
previous()
next()
next()
previous()
```

Với mỗi bước, ghi:

- Giá trị trả về.
- Vị trí dấu `|`.
- `nextIndex`.
- `previousIndex`.

Các giá trị trả về lần lượt cần là `20`, `20`, `30`, `30`. Hãy giải thích bằng chuyển động con trỏ.

### Bài 2: duyệt ngược từ cuối

Tạo một danh sách có ba chuỗi, lấy iterator tại `size` và in ngược bằng `hasPrevious/previous`.

Kiểm tra thêm danh sách rỗng. Giải thích vì sao không cần trừ `1` khi truyền vị trí khởi tạo iterator ở cuối.

### Bài 3: dự đoán thay đổi qua iterator

Với danh sách khả biến `[A, B, C]` và con trỏ ban đầu ở vị trí `1`:

```text
add(X)
previous()
set(Y)
next()
```

Dự đoán nội dung danh sách và con trỏ sau mỗi bước.

Sau chuỗi này, danh sách cần là `[A, Y, B, C]`; thao tác next cuối trả lại `Y`, không phải `B`. Hãy xác định lý do từ khoảng con trỏ sau previous.

### Bài 4: phân biệt lỗi trạng thái và không hỗ trợ

Thử các trường hợp trên nguồn phù hợp:

1. Iterator của `ArrayList` gọi `remove` trước khi next/previous.
2. Gọi `next`, rồi `remove`, rồi `remove` tiếp.
3. Iterator của `List.of` đã nhận phần tử rồi gọi `set`.
4. Danh sách rỗng gọi `previous`.
5. Khởi tạo iterator với vị trí lớn hơn `size`.

Ghi loại lỗi và lý do, phân biệt thiếu trạng thái hợp lệ, không có phần tử, chỉ số khởi tạo sai và thao tác không được nguồn hỗ trợ.

Tiêu chí hoàn thành là theo dõi được vị trí con trỏ cùng lịch sử phần tử vừa trả về, dự đoán chính xác chiều lấy dữ liệu và không dùng chỉ số hoặc thao tác chỉnh sửa ngoài hợp đồng.
