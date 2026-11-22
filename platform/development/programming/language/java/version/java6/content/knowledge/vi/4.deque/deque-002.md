# Thêm đầu, thêm cuối và thứ tự xử lý trong Deque

## 1. Hai đầu của deque là hai vị trí thao tác khác nhau

`Deque` là hàng đợi hai đầu (double-ended queue). Ta có thể thêm, xem hoặc lấy phần tử ở cả đầu và cuối:

```text
đầu (first/head)                         cuối (last/tail)
       ↓                                      ↓
      [A,                 B,                  C]
```

Trong cách vẽ của bài, đầu nằm bên trái, cuối nằm bên phải. Đây là thứ tự logic, không phải mô tả địa chỉ bộ nhớ hay cấu trúc mảng bên trong.

Hai thao tác thêm chính:

- `addFirst(e)`: đặt e thành phần tử đầu mới.
- `addLast(e)`: đặt e thành phần tử cuối mới.

Thứ tự xử lý không chỉ phụ thuộc thêm ở đâu. Nó còn phụ thuộc ta **lấy phần tử từ đầu nào**. Cùng một deque có thể được dùng như hàng đợi FIFO hoặc ngăn xếp LIFO bằng cách chọn đúng cặp thao tác. Xem [Deque](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/Deque.html).

## 2. Theo dõi từng bước thay vì đoán thứ tự cuối

Bắt đầu bằng deque rỗng:

| Bước | Thao tác | Trạng thái từ đầu đến cuối |
| --- | --- | --- |
| 0 | Khởi tạo | `[]` |
| 1 | `addLast("A")` | `[A]` |
| 2 | `addLast("B")` | `[A, B]` |
| 3 | `addFirst("X")` | `[X, A, B]` |
| 4 | `addLast("C")` | `[X, A, B, C]` |

Sau bước 4:

```text
peekFirst() → X
peekLast()  → C

Nếu liên tục pollFirst(): X, A, B, C
Nếu liên tục pollLast() : C, B, A, X
```

Hai chuỗi lấy ở trên là hai phương án riêng bắt đầu từ cùng trạng thái, không phải chạy cả hai liên tiếp trên một deque đã bị lấy hết.

Lưu ý:

- Thêm đầu không đảo thứ tự của các phần tử đã có; X chỉ đứng trước A.
- Thêm cuối không đổi vị trí tương đối của A và B.
- Mỗi lần lấy loại phần tử đó khỏi deque.
- `peekFirst()`/`peekLast()` chỉ xem, không làm deque ngắn đi.

Nếu một thuật toán vừa thêm vừa lấy, hãy ghi lại trạng thái sau từng thao tác. Việc chỉ nhớ thứ tự submit ban đầu dễ dẫn tới nhầm khi có `addFirst()`.

## 3. Chọn cặp thao tác để tạo FIFO hoặc LIFO

Giả sử lần lượt đưa A, B, C vào:

| Cách thêm | Cách lấy | Thứ tự lấy | Cách dùng |
| --- | --- | --- | --- |
| `addLast` | `pollFirst` | A, B, C | FIFO thông thường |
| `addFirst` | `pollLast` | A, B, C | FIFO với hướng biểu diễn ngược |
| `addFirst` | `pollFirst` | C, B, A | LIFO ở đầu |
| `addLast` | `pollLast` | C, B, A | LIFO ở cuối |

Mẹo suy luận:

- **Thêm ở một đầu, lấy ở đầu đối diện**: giữ thứ tự vào trước ra trước.
- **Thêm và lấy ở cùng một đầu**: phần tử mới nhất nằm gần vị trí lấy, nên vào sau ra trước.

Trong code hàng đợi công việc, cặp `addLast/pollFirst` thường dễ đọc vì “việc mới vào cuối, việc cũ lấy ở đầu”. Trong code ngăn xếp, các tên `push/pop` diễn đạt mục đích trực tiếp.

Không gọi một cấu trúc là “queue” rồi trộn thao tác ở các đầu một cách tùy ý. Hãy định nghĩa chính sách lấy/thêm ngay tại lớp quản lý nó.

## 4. Những tên ngắn tương đương đầu nào?

Deque còn thừa kế các tên của Queue và hỗ trợ tên của ngăn xếp:

| Tên gọi | Tương đương trên Deque |
| --- | --- |
| `add(e)` | `addLast(e)` |
| `offer(e)` | `offerLast(e)` |
| `remove()` | `removeFirst()` |
| `poll()` | `pollFirst()` |
| `element()` | `getFirst()` |
| `peek()` | `peekFirst()` |
| `push(e)` | `addFirst(e)` |
| `pop()` | `removeFirst()` |

Một lỗi thường gặp là nghĩ `push()` thêm cuối vì nó “đẩy thêm một phần tử”. Trong Deque, `push()` đặt ở đầu.

Tên `peek()` đọc đầu trong cả cách dùng FIFO lẫn LIFO. Với FIFO thông thường, đó là phần tử vào sớm nhất còn chờ; với stack dùng push, đó là phần tử vừa được đẩy gần nhất.

Không suy ra `remove(e)` là lấy đầu: overload nhận một đối tượng là tìm và loại một lần xuất hiện của phần tử đó. Khi đọc code, phải nhìn cả danh sách tham số, không chỉ tên phương thức.

## 5. add và offer: cùng vị trí, khác cách báo không còn chỗ

Ngoài `addFirst/addLast`, có `offerFirst/offerLast`:

| Hành động | Dạng báo lỗi bằng ngoại lệ | Dạng trả giá trị đặc biệt |
| --- | --- | --- |
| Thêm đầu | `addFirst(e)` | `offerFirst(e)` |
| Thêm cuối | `addLast(e)` | `offerLast(e)` |
| Lấy đầu | `removeFirst()` | `pollFirst()` |
| Lấy cuối | `removeLast()` | `pollLast()` |
| Xem đầu | `getFirst()` | `peekFirst()` |
| Xem cuối | `getLast()` | `peekLast()` |

Với deque có giới hạn dung lượng:

- `addFirst/addLast` ném `IllegalStateException` khi không thể thêm vì đầy.
- `offerFirst/offerLast` trả false khi không thể thêm ngay vì đầy.
- `addFirst/addLast` có kiểu trả về void; không viết `if (deque.addFirst(x))`.

Khi rỗng:

- `removeFirst/removeLast/getFirst/getLast` ném `NoSuchElementException`.
- `pollFirst/pollLast/peekFirst/peekLast` trả null.

“Dạng trả giá trị đặc biệt” không có nghĩa mọi lỗi đều bị biến thành false/null. Ví dụ, đưa null vào một triển khai cấm null vẫn có thể ném `NullPointerException`.

`ArrayDeque` có thể tăng dung lượng theo nhu cầu và không có giới hạn sức chứa cố định do người dùng đặt. `new ArrayDeque<>(2)` không tạo một deque tối đa hai phần tử. Tham số constructor là yêu cầu dung lượng ban đầu phù hợp, không phải chính sách giới hạn. Xem [ArrayDeque](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/ArrayDeque.html).

Nếu muốn minh họa giới hạn rõ ràng, có thể dùng `new LinkedBlockingDeque<>(2)`. Các thao tác offer không có tham số timeout vẫn trả ngay theo khả năng thêm hiện tại; chúng không tự đợi đến khi có chỗ. Xem [LinkedBlockingDeque](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html).

## 6. Chương trình Java đầy đủ

Chương trình dùng Java 17+ và chạy một luồng, minh họa:

1. Trộn thêm đầu/thêm cuối.
2. Quan sát hai đầu mà không lấy phần tử.
3. Lấy theo FIFO và LIFO.
4. Đưa nhiều công việc khẩn vào đầu.
5. Offer vào deque giới hạn dung lượng.

Lưu thành `DequeEndOrderDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.concurrent.LinkedBlockingDeque;

public class DequeEndOrderDemo {
    static List<String> drainFirst(Deque<String> deque) {
        List<String> result = new ArrayList<>();
        String value;
        while ((value = deque.pollFirst()) != null) {
            result.add(value);
        }
        return result;
    }

    public static void main(String[] args) {
        Deque<String> mixed = new ArrayDeque<>();
        mixed.addLast("A");
        mixed.addLast("B");
        mixed.addFirst("X");
        mixed.addLast("C");
        System.out.println("mixed=" + mixed);
        System.out.println("ends=" + mixed.peekFirst() + "/" + mixed.peekLast());
        System.out.println("mixedDrain=" + drainFirst(mixed));
        System.out.println("emptyPoll=" + mixed.pollFirst());
        try {
            mixed.removeFirst();
        } catch (NoSuchElementException ex) {
            System.out.println("emptyRemove=NoSuchElementException");
        }

        Deque<String> fifo = new ArrayDeque<>();
        Deque<String> stack = new ArrayDeque<>();
        for (String value : List.of("A", "B", "C")) {
            fifo.addLast(value);
            stack.push(value);
        }
        System.out.println("fifo=" + drainFirst(fifo));
        System.out.println("lifo=" + drainFirst(stack));

        Deque<String> urgent =
                new ArrayDeque<>(List.of("normal-1", "normal-2"));
        urgent.addFirst("urgent-1");
        urgent.addFirst("urgent-2");
        System.out.println("urgentOrder=" + drainFirst(urgent));

        Deque<String> bounded = new LinkedBlockingDeque<>(2);
        System.out.println("offerLastA=" + bounded.offerLast("A"));
        System.out.println("offerFirstB=" + bounded.offerFirst("B"));
        System.out.println("offerLastC=" + bounded.offerLast("C"));
        System.out.println("bounded=" + bounded);
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 -encoding UTF-8 DequeEndOrderDemo.java
java DequeEndOrderDemo
```

Kết quả suy ra từ các thao tác và hợp đồng API:

```text
mixed=[X, A, B, C]
ends=X/C
mixedDrain=[X, A, B, C]
emptyPoll=null
emptyRemove=NoSuchElementException
fifo=[A, B, C]
lifo=[C, B, A]
urgentOrder=[urgent-2, urgent-1, normal-1, normal-2]
offerLastA=true
offerFirstB=true
offerLastC=false
bounded=[B, A]
```

Phương thức `drainFirst()` làm rỗng deque được truyền vào. Nó trả thứ tự đã lấy, không tạo một snapshot rồi giữ nguyên nguồn.

Vòng lặp dừng bằng giá trị null của `pollFirst()`, phù hợp vì các triển khai dùng trong chương trình không cho chứa null. Không dùng cách dừng này với một cấu trúc cho phép null mà chưa xác định ý nghĩa của null.

## 7. Tại sao công việc khẩn mới lại chạy trước công việc khẩn cũ?

Trạng thái ban đầu:

```text
[normal-1, normal-2]
```

Sau `addFirst("urgent-1")`:

```text
[urgent-1, normal-1, normal-2]
```

Sau `addFirst("urgent-2")`:

```text
[urgent-2, urgent-1, normal-1, normal-2]
```

Nếu lấy ở đầu, urgent-2 ra trước urgent-1. Việc “đưa việc khẩn vào đầu” tạo chính sách vào sau ra trước giữa những việc cùng được thêm ở đầu; nó không tự bảo đảm FIFO trong nhóm khẩn.

Nếu yêu cầu là:

```text
mọi việc khẩn trước việc thường
nhưng trong từng nhóm vẫn theo thứ tự đến
```

thì cần mô hình/chính sách khác, chẳng hạn hai hàng đợi FIFO và một quy tắc chọn nhóm. Không chỉ đổi tên biến hoặc gán nhãn “priority” cho deque là đạt yêu cầu.

Deque cũng không tự sắp theo giá trị, độ ưu tiên hay timestamp. Nó giữ thứ tự do các thao tác ở hai đầu tạo ra.

Nếu liên tục có việc được thêm đầu, các việc ở cuối có thể phải chờ lâu theo chính sách xử lý. Cần xem yêu cầu công bằng của ứng dụng, không chỉ xem thao tác thêm có thành công hay không.

## 8. Thứ tự duyệt không nhất thiết là thứ tự lấy mà thuật toán chọn

Khi duyệt bằng iterator thông thường, deque được xem theo thứ tự từ đầu tới cuối. `descendingIterator()` duyệt chiều ngược lại.

Ví dụ cùng trạng thái `[X, A, B, C]`:

```text
iterator()           : X, A, B, C
descendingIterator() : C, B, A, X
```

Duyệt không tự loại phần tử. Thứ tự thực thi của chương trình còn phụ thuộc thao tác lấy mà nó dùng:

- Nếu worker liên tục `pollFirst()`, thứ tự lấy từ đầu.
- Nếu worker liên tục `pollLast()`, thứ tự lấy từ cuối.
- Nếu vừa duyệt vừa sửa cấu trúc, phải tuân thủ hợp đồng iterator và triển khai, không mặc định iterator là danh sách tác vụ bất biến.

Trong chương trình mẫu, in ArrayDeque giúp quan sát thứ tự phần tử, còn `drainFirst()` mới thể hiện thứ tự lấy. Khi viết kiểm tra, nên so sánh danh sách phần tử theo thứ tự cần có thay vì suy luận từ một vị trí trong mảng nội bộ.

Không tự cho rằng mọi Deque có `equals()` so sánh theo từng phần tử giống List. Khi cần kiểm tra nội dung/thứ tự, có thể đưa các phần tử sang một List theo chiều duyệt đã chọn.

## 9. Khi nhiều luồng cùng dùng deque, cần thêm hợp đồng đồng thời

`Deque` chỉ là kiểu giao diện; nó không hứa mọi triển khai đều an toàn khi nhiều luồng cùng sửa.

`ArrayDeque` trong ví dụ không được dùng đồng thời bởi nhiều luồng mà thiếu cơ chế bảo vệ. Đổi sang một triển khai đồng thời cũng chưa làm cả một chuỗi thao tác tùy ý thành nguyên tử.

Ví dụ ý tưởng:

```java
if (!deque.isEmpty()) {
    String job = deque.removeFirst();
}
```

Nếu một luồng khác lấy phần tử cuối cùng ở giữa hai thao tác, điều kiện cũ không còn đúng. Với hợp đồng phù hợp, một lần `pollFirst()` rồi xử lý trường hợp null thường diễn đạt trực tiếp việc “thử lấy”.

Nếu cần chờ phần tử hoặc chờ chỗ trống, xem các thao tác blocking/timed của `BlockingDeque` và chính sách timeout/ngắt. Không gọi một thao tác chờ vô hạn trên luồng không được phép bị chặn.

Thứ tự xử lý nhiều worker còn khác thứ tự lấy: một việc được lấy trước có thể hoàn tất sau vì mất nhiều thời gian hơn. Deque quyết định thứ tự truy cập phần tử theo thao tác, không bảo đảm thời điểm kết thúc nghiệp vụ.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| addFirst luôn làm cả deque thành FIFO | FIFO cần xét cả đầu lấy |
| push thêm cuối | push tương đương addFirst |
| add và addFirst giống nhau | add tương đương addLast |
| peek lấy phần tử ra | peek chỉ xem |
| pollLast vẫn lấy phần tử cũ nhất | Tùy cách thêm; thêm cuối rồi lấy cuối tạo LIFO |
| ArrayDeque(2) chỉ chứa tối đa 2 phần tử | Nó không phải giới hạn sức chứa |
| offer luôn trả false cho mọi lỗi | False báo không thêm ngay do giới hạn; lỗi phần tử vẫn có thể ném ngoại lệ |
| Hai lần addFirst cho việc khẩn giữ thứ tự đến | Việc thêm đầu sau đứng trước việc thêm đầu trước |
| Thứ tự lấy luôn là thứ tự hoàn tất | Công việc sau khi lấy có thời gian xử lý khác nhau |
| Có interface Deque là tự an toàn nhiều luồng | Phải chọn triển khai và cơ chế đồng bộ phù hợp |

Bài tập:

1. Từ deque rỗng, chạy `addFirst(A)`, `addLast(B)`, `addFirst(C)`, `pollLast()`. Hãy ghi trạng thái sau mỗi bước.
2. Đổi FIFO trong chương trình sang `addFirst/pollLast`. Vì sao thứ tự lấy vẫn A, B, C?
3. Đổi stack sang `addLast/pollLast`. Cần thay cả thao tác thêm và thao tác lấy nào?
4. Với deque có dung lượng 2 đang là `[B, A]`, lấy cuối rồi offerLast(C). Trạng thái mới là gì?
5. Thiết kế quy tắc giữ FIFO riêng cho công việc khẩn và thường. Vì sao một dãy addFirst chưa đủ?

Khi đọc hoặc viết một thuật toán dùng Deque, hãy nêu rõ hai lựa chọn: **thêm ở đâu, lấy ở đâu**. Từ hai lựa chọn đó có thể suy ra thứ tự xử lý thay vì dựa vào tên biến hoặc cảm giác về “đầu” và “cuối”.
