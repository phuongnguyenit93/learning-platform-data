# LinkedList: thao tác hai đầu và chính sách null

`LinkedList` vừa là một `List`, vừa triển khai `Deque` — hàng đợi hai đầu. Ta có thể thêm, xem hoặc lấy/xóa phần tử ở đầu và cuối mà không phải tìm nút bằng chỉ số.

Điểm cần lựa chọn rõ là **đầu nào**, **có xóa phần tử không**, và **khi rỗng thì trả tín hiệu hay ném ngoại lệ**. Với `LinkedList`, còn một yếu tố dễ gây lỗi: cấu trúc cho phép lưu `null`, trong khi nhiều phương thức cũng dùng `null` để báo không có phần tử.

Bài này dùng API tương thích Java 17, giải thích các nhóm phương thức, cách dùng theo FIFO/LIFO và cách thiết kế chính sách `null` để không nhầm dữ liệu với trạng thái rỗng.

## 1. Hai đầu của một danh sách liên kết

Có thể hình dung một danh sách đang chứa A, B, C như sau:

~~~text
first / head                       last / tail
     |                                  |
     v                                  v
    [A] <------------> [B] <----------> [C]
~~~

- **Đầu (first/head):** phía chứa phần tử A trong sơ đồ.
- **Cuối (last/tail):** phía chứa phần tử C.
- `addFirst` thêm trước A; `addLast` thêm sau C.
- Lấy ở đầu hoặc cuối không cần đi qua các nút ở giữa.

Trong triển khai danh sách liên kết hai chiều, cấu trúc giữ tham chiếu tới cả nút đầu lẫn nút cuối. Việc đọc một đầu hoặc cập nhật một đầu chỉ cần số lượng thao tác liên kết cố định.

Điều này khác với `get(i)` ở giữa: chỉ số giữa còn đòi hỏi tìm nút. Đừng dùng chi phí của thao tác hai đầu để suy ra mọi thao tác trên `LinkedList` đều O(1).

### 1.1. Deque mô tả cách sử dụng, LinkedList là một cách triển khai

Đoạn thân phương thức minh họa:

~~~java
Deque<String> work = new LinkedList<>();
work.addLast("A");
work.addFirst("urgent");
~~~

Biến được khai báo bằng `Deque` để thể hiện rằng chương trình quan tâm tới hai đầu. Đối tượng thật vẫn là `LinkedList`; khả năng lưu `null`, cơ chế bộ nhớ và yêu cầu đồng bộ đến từ triển khai này.

Theo [LinkedList Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html), cấu trúc hỗ trợ các phần tử bao gồm `null`. Theo [Deque Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html), các phương thức được tổ chức thành các cặp có cách báo thất bại khác nhau.

### 1.2. Danh sách rỗng khác danh sách chứa null

Hai trạng thái dưới đây khác nhau:

~~~text
rong:
size = 0
khong co nut phan tu

chua mot phan tu null:
size = 1
first/last -> [item = null]
~~~

Một nút có phần tử `null` vẫn là một nút thật và vẫn được tính vào kích thước. Sự vắng mặt của nút đầu/cuối mới biểu thị danh sách rỗng; giá trị `null` trong phần tử không tự làm danh sách rỗng.

Đây là nền tảng để hiểu những kết quả tưởng như giống nhau của `peek`, `poll`, `getFirst` và `removeFirst`.

## 2. Xem hay lấy/xóa: chọn đúng nhóm phương thức

Có hai quyết định độc lập:

1. Chỉ xem phần tử, hay lấy và xóa khỏi cấu trúc?
2. Khi không có phần tử, ném ngoại lệ hay trả `null`?

### 2.1. Các phương thức ở đầu

| Mục đích | Ném ngoại lệ nếu rỗng | Trả null nếu rỗng | Có xóa phần tử? |
|---|---|---|---|
| Xem đầu | `getFirst()` | `peekFirst()` | Không |
| Lấy đầu | `removeFirst()` | `pollFirst()` | Có, nếu có nút đầu |

Nhóm ném ngoại lệ dùng `NoSuchElementException` khi danh sách rỗng. Nhóm trả `null` không ném ngoại lệ vì lý do rỗng.

Cách chọn có thể dựa vào hợp đồng của chương trình:

- Nếu không có phần tử là tình huống bình thường, nhóm `peek/poll` thường thuận tiện.
- Nếu tại điểm đó chương trình yêu cầu chắc chắn phải có phần tử, nhóm `get/remove` giúp làm lộ việc vi phạm yêu cầu.
- Khi cho phép phần tử `null`, chỉ nhìn kết quả của nhóm `peek/poll` không đủ để phân biệt trạng thái rỗng.

### 2.2. Các phương thức ở cuối

| Mục đích | Ném ngoại lệ nếu rỗng | Trả null nếu rỗng | Có xóa phần tử? |
|---|---|---|---|
| Xem cuối | `getLast()` | `peekLast()` | Không |
| Lấy cuối | `removeLast()` | `pollLast()` | Có, nếu có nút cuối |

Hai đầu đối xứng về ý nghĩa. Khi đọc mã, hậu tố `First` hoặc `Last` cho biết đầu nào được tác động; động từ cho biết có xóa không và dùng cách báo rỗng nào.

### 2.3. Xem không làm thay đổi số phần tử

Với `[A, B, C]`:

~~~text
getFirst()  -> A, danh sach van [A, B, C]
peekLast()  -> C, danh sach van [A, B, C]

removeFirst() -> A, danh sach thanh [B, C]
pollLast()    -> C, danh sach thanh [B]
~~~

Nếu thuật toán cần kiểm tra phần tử đầu nhiều lần trước khi quyết định xử lý, `peekFirst` hoặc `getFirst` phù hợp hơn việc lấy rồi tự thêm lại. Nếu đã xử lý xong và cần loại khỏi hàng đợi, chỉ `peek` sẽ không tiến được trạng thái.

### 2.4. Ngoại lệ khi rỗng không phải ngoại lệ vì phần tử null

Nếu đầu danh sách là một phần tử `null` nhưng danh sách không rỗng:

- `getFirst()` trả về `null`, không ném `NoSuchElementException`.
- `removeFirst()` trả về `null` và xóa nút đó.
- `peekFirst()` trả về `null` và giữ nguyên nút.
- `pollFirst()` trả về `null` và xóa nút đó.

Tương tự ở cuối.

Vì vậy, không nên gọi nhóm ném ngoại lệ là “nhóm luôn trả phần tử khác null”. Nhóm này phân biệt **không có nút** bằng ngoại lệ; nó không thay đổi chính sách dữ liệu của `LinkedList`.

## 3. Thêm vào hai đầu: add và offer khác nhau ở hợp đồng

| Đầu thêm | Phương thức thêm | Kiểu kết quả | Phương thức offer | Kiểu kết quả |
|---|---|---|---|---|
| Đầu | `addFirst(e)` | `void` | `offerFirst(e)` | `boolean` |
| Cuối | `addLast(e)` | `void` | `offerLast(e)` | `boolean` |

Trong hợp đồng `Deque` tổng quát, với một cấu trúc bị giới hạn sức chứa:

- Nhóm `add` có thể báo không thêm được vì hết chỗ bằng `IllegalStateException`.
- Nhóm `offer` có thể trả `false` vì không còn chỗ.

Đó là lý do có hai dạng. `offer` không có nghĩa “bỏ qua mọi lỗi và luôn không ném ngoại lệ”. Một triển khai cấm `null` vẫn có thể ném `NullPointerException` khi `offer(null)`.

### 3.1. Với LinkedList, offer thường trả true khi hoàn thành

`LinkedList` không có tham số cấu hình giới hạn số phần tử kiểu một hàng đợi hữu hạn. Các phương thức `offer`, `offerFirst`, `offerLast` của nó trả `true` sau khi thêm thành công.

Không dùng `false` như cơ chế dự kiến để phát hiện danh sách liên kết “đầy”. Bộ nhớ vẫn hữu hạn; cấp phát có thể thất bại. `offer` không biến lỗi thiếu tài nguyên thành một hệ thống điều tiết tải hoặc một bảo đảm có thể lưu vô hạn.

Nếu yêu cầu cần giới hạn tải, cần một thiết kế có sức chứa và cách báo/chờ phù hợp. Đổi `add` thành `offer` trên cùng `LinkedList` không tự tạo giới hạn đó.

### 3.2. Null được LinkedList chấp nhận ở cả hai đầu

Một `LinkedList<String>` có thể nhận `addFirst(null)`, `addLast(null)`, `offerFirst(null)` và `offerLast(null)`. Đây là phần tử `null`, không phải lệnh “không thêm gì”.

Sau một lần thêm thành công, kích thước tăng lên kể cả khi giá trị thêm là `null`.

Tuy nhiên, một tham số collection nguồn bằng `null`, chẳng hạn truyền vào constructor nhận collection, là một trường hợp khác với collection có phần tử `null`. “Cho phép phần tử null” không có nghĩa mọi tham số API đều được phép là `null`.

### 3.3. Offer và poll không chờ dữ liệu

Các phương thức ở đây là thao tác tức thời trên trạng thái hiện tại. `pollFirst()` trên một `LinkedList` rỗng trả `null`; nó không chờ đến khi một luồng khác thêm phần tử.

Nếu bài toán là phối hợp các luồng có thao tác chờ, hết thời gian chờ hoặc sức chứa giới hạn, cần hợp đồng đồng thời thích hợp. Không diễn giải tên `Queue` hoặc `Deque` là một cam kết tự chặn/chờ.

## 4. Dùng cùng cấu trúc theo FIFO hoặc LIFO

### 4.1. Hàng đợi FIFO: vào cuối, ra đầu

FIFO là “vào trước, ra trước”. Với `LinkedList`, cách dùng thường gặp:

~~~java
Queue<String> queue = new LinkedList<>();
queue.offer("first");
queue.offer("second");
String next = queue.poll(); // "first"
~~~

Đoạn trên chỉ minh họa phần thân phương thức. Các tên ngắn của `Queue` được ánh xạ vào đầu/cuối của `Deque` như sau:

| Tên ngắn | Ý nghĩa trên LinkedList |
|---|---|
| `add(e)` | Thêm cuối; trả `true` khi thành công |
| `offer(e)` | Tương đương hướng thêm của `offerLast(e)` |
| `remove()` | Lấy/xóa đầu; rỗng thì ném ngoại lệ |
| `poll()` | Lấy/xóa đầu; rỗng thì trả `null` |
| `element()` | Xem đầu; rỗng thì ném ngoại lệ |
| `peek()` | Xem đầu; rỗng thì trả `null` |

Tính FIFO ở đây đến từ việc thêm vào cuối và lấy ra đầu của triển khai này. Không suy từ giao diện `Queue` rằng mọi loại hàng đợi Java đều dùng cùng quy tắc sắp thứ tự; có các triển khai có quy tắc khác. Xem [Queue Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html).

Khi chỉ cần dùng theo hàng đợi, khai báo `Queue` giúp tránh gọi nhầm các thao tác ở đầu/cuối khác. Nếu cần cả hai đầu, dùng `Deque` để thể hiện đầy đủ yêu cầu.

### 4.2. Ngăn xếp LIFO: vào đầu, ra đầu

LIFO là “vào sau, ra trước”. Các tên stack trong `Deque`:

| Tên | Tương đương |
|---|---|
| `push(e)` | `addFirst(e)` |
| `pop()` | `removeFirst()` |
| `peek()` | `peekFirst()` |

Đẩy one rồi two sẽ có thứ tự đầu→cuối là `[two, one]`; `pop()` lấy two trước.

Không trộn `push` với `pollLast` rồi vẫn gọi đó là cùng một quy tắc LIFO. Tên “ngăn xếp” không tự ngăn mã gọi lấy ở đầu còn lại.

### 4.3. remove() khác remove(value) và remove(index)

Với đối tượng `LinkedList` cụ thể có nhiều phương thức cùng tên:

- `remove()`: lấy/xóa đầu.
- `remove(int index)`: tìm và xóa theo chỉ số.
- `remove(Object value)`: tìm và xóa lần xuất hiện phù hợp đầu tiên.

Trong một biến kiểu `Deque<Integer>`, `remove(1)` chọn `remove(Object)` qua đóng hộp vì giao diện này không có `remove(int)`. Trong một biến kiểu `LinkedList<Integer>`, `remove(1)` lại chọn xóa chỉ số 1.

Bởi vậy, với ý định thao tác đầu mút, dùng tên rõ như `removeFirst`, `pollFirst`, `removeLast` giúp tránh nhầm ý nghĩa. Xóa theo giá trị hoặc theo chỉ số giữa còn có thể cần tìm kiếm, không có cùng mô hình chi phí với xóa đầu/cuối.

## 5. Vấn đề cốt lõi của null: một kết quả có hai nghĩa

### 5.1. Bảng trạng thái ở đầu

| Trạng thái trước gọi | peekFirst | getFirst | pollFirst | removeFirst |
|---|---|---|---|---|
| Rỗng | `null`, không đổi | `NoSuchElementException` | `null`, không đổi | `NoSuchElementException` |
| Đầu là X khác null | X, không đổi | X, không đổi | X, xóa nút đầu | X, xóa nút đầu |
| Đầu là null thật | `null`, không đổi | `null`, không đổi | `null`, xóa nút đầu | `null`, xóa nút đầu |

Bảng ở cuối có ý nghĩa đối xứng khi thay `First` bằng `Last`.

Từ bảng này:

~~~text
deque rong       -> peekFirst() tra null
peekFirst()==null -> CHUA DU de ket luan deque rong
~~~

Một chiều suy luận đúng không làm chiều ngược tự đúng.

### 5.2. Poll trả null có thể đã thay đổi danh sách

Giả sử danh sách đang là `[null, job]`:

~~~text
pollFirst() -> null
danh sach sau do -> [job]
~~~

Nếu danh sách rỗng:

~~~text
pollFirst() -> null
danh sach sau do -> []
~~~

Kết quả trả về bằng nhau, nhưng một lần đã lấy/xóa phần tử thật còn lần kia không lấy gì.

Do đó, sau khi nhận `null`, không được tự suy ra rằng thao tác không làm thay đổi trạng thái. Đây là lỗi đặc biệt nguy hiểm khi chương trình bỏ qua hoặc thử lại phần việc mà nó tưởng chưa xảy ra.

### 5.3. Vòng lặp dùng null làm dấu kết thúc có thể dừng sớm

Mẫu sau chỉ phù hợp nếu dữ liệu được bảo đảm không chứa `null`:

~~~java
String item;
while ((item = deque.pollFirst()) != null) {
    process(item);
}
~~~

Với `[A, null, B]`:

1. Lấy A và xử lý A.
2. Lấy phần tử `null`, nút đó bị xóa.
3. Điều kiện vòng lặp sai, nên vòng dừng.
4. B vẫn còn chưa được xử lý trong deque.

Mã không chỉ bỏ qua việc xử lý `null`; nó còn dừng trước các phần tử phía sau. Ví dụ đầy đủ bên dưới cho kết quả `processed=[A], remaining=[B]`.

### 5.4. Optional.ofNullable không phục hồi thông tin đã mất

Bọc kết quả bằng:

~~~java
Optional<String> item = Optional.ofNullable(deque.pollFirst());
~~~

không phân biệt được “không có phần tử” với “đã lấy ra phần tử null”. Cả hai đều thành `Optional.empty`.

Đây là hành vi được định nghĩa của [Optional.ofNullable Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html#ofNullable(T)). Muốn phân biệt hai trạng thái, cần giữ một thông tin riêng về sự hiện diện; không thể khôi phục nó chỉ từ giá trị `null` mà `poll` đã trả.

### 5.5. Mở hộp có thể ném ngoại lệ sau khi nút đã bị lấy ra

Với `Deque<Integer>`:

~~~java
int value = deque.removeFirst();
~~~

Nếu có một phần tử `null` ở đầu, `removeFirst` có thể xóa nó và trả `null`; sau đó quá trình chuyển `Integer` sang `int` ném `NullPointerException`.

Lỗi mở hộp không có nghĩa là deque chắc chắn không đổi. Phải phân biệt bước gọi phương thức đã hoàn thành với bước chuyển kiểu giá trị trả về.

Nếu dữ liệu thực sự cho phép `null`, hãy nhận bằng kiểu bao `Integer` và xử lý chính sách `null` rõ ràng trước khi cần một giá trị nguyên thủy.

## 6. Chọn một chính sách null rõ ràng

### 6.1. Nếu null không phải dữ liệu hợp lệ: từ chối ở ranh giới

Trong nhiều hàng đợi công việc, không có lý do nghiệp vụ để một phần tử công việc chính nó là `null`. Từ chối sớm giúp nhóm `poll/peek` có tín hiệu rỗng rõ nghĩa.

Một helper có thể dùng `Objects.requireNonNull` trước khi thêm. Tuy nhiên, helper chỉ kiểm tra các lời gọi đi qua nó. Nếu nơi khác vẫn giữ deque có thể sửa và gọi trực tiếp `addFirst(null)`, chính sách đã bị đi vòng.

Muốn bảo đảm điều kiện cho cả ứng dụng, phải quản lý quyền sở hữu và mọi đường đưa dữ liệu vào: thêm đầu, thêm cuối, thêm lô hoặc sửa qua các giao diện khác nếu bị lộ. Tài liệu API của lớp nghiệp vụ nên nói rõ rằng công việc không được là `null`.

Khi chỉ cần một deque không chứa `null`, có thể cân nhắc `ArrayDeque`. Cấu trúc này cấm phần tử `null`; việc thêm `null` bị từ chối bằng `NullPointerException`, như mô tả tại [ArrayDeque Java 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html).

Đổi triển khai vẫn cần kiểm tra các yêu cầu khác: API đang dùng, bộ nhớ và cách truy cập. Việc cùng có kiểu `Deque` không bảo đảm dữ liệu cũ chứa `null` được chấp nhận khi chuyển sang cấu trúc khác.

### 6.2. Nếu null là dữ liệu thật: kiểm tra sự rỗng độc lập với giá trị

Trong phạm vi một luồng, khi không có thay đổi xen giữa kiểm tra và lấy phần tử, có thể viết:

~~~java
while (!deque.isEmpty()) {
    String item = deque.removeFirst();
    processIncludingNull(item);
}
~~~

Trạng thái rỗng được kiểm tra bằng `isEmpty`; giá trị lấy ra có thể là `null` và vẫn được đưa vào xử lý theo quy tắc nghiệp vụ.

Đây là mẫu minh họa, với hàm `processIncludingNull` do ứng dụng định nghĩa. Tên hàm nhấn mạnh rằng không thể chỉ đổi điều kiện vòng lặp rồi giả định mọi mã xử lý bên trong đã hỗ trợ `null`.

Không áp dụng mẫu “kiểm tra rồi lấy” như một thao tác nguyên tử trong môi trường có các luồng khác cùng sửa. Khi đó phải có cơ chế phối hợp phù hợp cho cả chuỗi hành động.

### 6.3. Nếu cần trả kết quả có phân biệt: dùng cờ hiện diện riêng

Ví dụ, một kết quả có hai trường:

~~~text
present = true,  value = null  -> da lay duoc mot phan tu, gia tri cua no la null
present = false, value = null  -> khong co phan tu de lay
~~~

Chương trình bên dưới dùng record `Removal<E>` để minh họa. Hàm trợ giúp kiểm tra rỗng rồi gọi `removeFirst`, và được giới hạn rõ ở tình huống không có thay đổi đồng thời.

Đây là cách biểu diễn kết quả, không phải một lớp hàng đợi đồng thời hoàn chỉnh. Khi dùng ngoài ví dụ, cần thiết kế cả hợp đồng tạo kết quả và quy tắc truy cập cấu trúc.

### 6.4. Giá trị tùy chọn bên trong phần tử khác phần tử null

Một công việc có thể tồn tại nhưng thiếu ghi chú. Ta có thể biểu diễn bằng một đối tượng công việc khác `null`, với trường ghi chú có chính sách riêng, thay vì dùng chính `null` làm cả phần tử hàng đợi.

Tương tự, nếu cần dấu kết thúc, dấu phân cách lô hoặc loại thông điệp đặc biệt, một kiểu dữ liệu thể hiện rõ các loại thông điệp thường dễ kiểm tra hơn một `null` không có tên. Khi dùng `null` làm dấu quy ước, phải đánh giá xung đột với các phương thức coi `null` là trạng thái rỗng.

Giao diện `Deque` khuyến khích không tận dụng khả năng chèn `null` ngay cả ở triển khai cho phép, chính vì sự nhập nhằng của các giá trị trả về. Khả năng được lớp hỗ trợ và chính sách nên dùng của ứng dụng là hai quyết định khác nhau.

## 7. Chương trình hoàn chỉnh: hai đầu, FIFO/LIFO và các trạng thái null

Ví dụ chạy trong một luồng. Nó kiểm tra thao tác ở cả hai đầu, kết quả khi rỗng, phần tử `null` thật, vòng lặp bị dừng sớm và hai cách biểu diễn trạng thái không có dữ liệu.

### 7.1. Mã nguồn

Lưu thành `LinkedListEndsNullDemo.java`:

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedList;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.Objects;
import java.util.Optional;
import java.util.Queue;

public class LinkedListEndsNullDemo {
    record Removal<E>(boolean present, E value) {}

    // Chi dung khi khong co thay doi dong thoi giua check va remove.
    static <E> Removal<E> removeNullableFirst(Deque<E> deque) {
        if (deque.isEmpty()) {
            return new Removal<>(false, null);
        }
        return new Removal<>(true, deque.removeFirst());
    }

    static void enqueueNonNull(Deque<String> deque, String value) {
        deque.addLast(Objects.requireNonNull(value, "value"));
    }

    static void showEmptyFailure(String name, Runnable operation) {
        try {
            operation.run();
            throw new AssertionError("expected NoSuchElementException");
        } catch (NoSuchElementException exception) {
            System.out.println(name + ": NoSuchElementException");
        }
    }

    public static void main(String[] args) {
        Deque<String> ends = new LinkedList<>();
        ends.addLast("B");
        ends.addFirst("A");
        boolean tailAccepted = ends.offerLast("C");
        boolean headAccepted = ends.offerFirst("Z");
        System.out.printf("offers: head=%s, tail=%s, values=%s%n",
                headAccepted, tailAccepted, ends);
        System.out.printf("get ends: first=%s, last=%s, size=%d%n",
                ends.getFirst(), ends.getLast(), ends.size());
        System.out.printf("peek ends: first=%s, last=%s, size=%d%n",
                ends.peekFirst(), ends.peekLast(), ends.size());
        System.out.println("removeFirst: " + ends.removeFirst());
        System.out.println("pollLast: " + ends.pollLast());
        System.out.println("remaining: " + ends);

        Queue<String> queue = new LinkedList<>();
        queue.offer("one");
        queue.offer("two");
        System.out.println("FIFO poll: " + queue.poll());
        System.out.println("FIFO element: " + queue.element());
        System.out.println("FIFO remove: " + queue.remove());

        Deque<Integer> dequeView = new LinkedList<>(List.of(1, 2, 3));
        LinkedList<Integer> listView = new LinkedList<>(List.of(1, 2, 3));
        boolean removedValue = dequeView.remove(1);
        int removedIndex = listView.remove(1);
        System.out.printf("remove(1) as Deque: returned=%s, values=%s%n",
                removedValue, dequeView);
        System.out.printf("remove(1) as LinkedList: returned=%d, values=%s%n",
                removedIndex, listView);

        Deque<String> stack = new LinkedList<>();
        stack.push("one");
        stack.push("two");
        System.out.println("stack values: " + stack);
        System.out.println("LIFO pop: " + stack.pop());
        System.out.println("LIFO peek: " + stack.peek());

        Deque<String> empty = new LinkedList<>();
        System.out.printf("empty peek: first=%s, last=%s%n",
                empty.peekFirst(), empty.peekLast());
        System.out.printf("empty poll: first=%s, last=%s%n",
                empty.pollFirst(), empty.pollLast());
        showEmptyFailure("empty getFirst", () -> empty.getFirst());
        showEmptyFailure("empty getLast", () -> empty.getLast());
        showEmptyFailure("empty removeFirst", () -> empty.removeFirst());
        showEmptyFailure("empty removeLast", () -> empty.removeLast());

        Deque<String> nullable = new LinkedList<>();
        System.out.println("offerFirst(null): " + nullable.offerFirst(null));
        nullable.addLast("job");
        System.out.printf("null head: size=%d, peek=%s, get=%s%n",
                nullable.size(), nullable.peekFirst(), nullable.getFirst());
        String removedNull = nullable.pollFirst();
        System.out.printf("poll stored null: value=%s, remaining=%s%n",
                removedNull, nullable);
        System.out.println("poll job: " + nullable.pollFirst());
        System.out.println("poll empty: " + nullable.pollFirst());

        Deque<String> tailNull = new LinkedList<>();
        tailNull.addLast("job");
        tailNull.addLast(null);
        System.out.printf("null tail: peek=%s, get=%s, size=%d%n",
                tailNull.peekLast(), tailNull.getLast(), tailNull.size());
        String removedTailNull = tailNull.removeLast();
        System.out.printf("remove stored tail null: value=%s, remaining=%s%n",
                removedTailNull, tailNull);

        Deque<String> risky = new LinkedList<>();
        risky.addLast("A");
        risky.addLast(null);
        risky.addLast("B");
        List<String> processed = new ArrayList<>();
        String item;
        while ((item = risky.pollFirst()) != null) {
            processed.add(item);
        }
        System.out.printf("sentinel loop: processed=%s, remaining=%s%n",
                processed, risky);

        Deque<String> complete = new LinkedList<>();
        complete.addLast("A");
        complete.addLast(null);
        complete.addLast("B");
        List<String> all = new ArrayList<>();
        while (!complete.isEmpty()) {
            all.add(complete.removeFirst());
        }
        System.out.printf("explicit-empty loop: processed=%s, remaining=%s%n",
                all, complete);

        Deque<String> results = new LinkedList<>();
        results.addLast(null);
        System.out.println("explicit result 1: " + removeNullableFirst(results));
        System.out.println("explicit result 2: " + removeNullableFirst(results));
        results.addLast(null);
        Optional<String> optional = Optional.ofNullable(results.pollFirst());
        System.out.printf("Optional after stored null: %s, remaining=%s%n",
                optional, results);

        Deque<String> guarded = new LinkedList<>();
        enqueueNonNull(guarded, "job");
        try {
            enqueueNonNull(guarded, null);
        } catch (NullPointerException exception) {
            System.out.println("guard rejects null: remaining=" + guarded);
        }
        Deque<String> array = new ArrayDeque<>();
        try {
            array.addLast(null);
        } catch (NullPointerException exception) {
            System.out.println("ArrayDeque null: NullPointerException");
        }

        Deque<Integer> numbers = new LinkedList<>();
        numbers.addLast(null);
        try {
            int value = numbers.removeFirst();
            System.out.println(value);
        } catch (NullPointerException exception) {
            System.out.println("unboxing removed null: NullPointerException, size="
                    + numbers.size());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~shell
javac --release 17 -encoding UTF-8 LinkedListEndsNullDemo.java
java LinkedListEndsNullDemo
~~~

### 7.2. Kết quả stdout

~~~text
offers: head=true, tail=true, values=[Z, A, B, C]
get ends: first=Z, last=C, size=4
peek ends: first=Z, last=C, size=4
removeFirst: Z
pollLast: C
remaining: [A, B]
FIFO poll: one
FIFO element: two
FIFO remove: two
remove(1) as Deque: returned=true, values=[2, 3]
remove(1) as LinkedList: returned=2, values=[1, 3]
stack values: [two, one]
LIFO pop: two
LIFO peek: one
empty peek: first=null, last=null
empty poll: first=null, last=null
empty getFirst: NoSuchElementException
empty getLast: NoSuchElementException
empty removeFirst: NoSuchElementException
empty removeLast: NoSuchElementException
offerFirst(null): true
null head: size=2, peek=null, get=null
poll stored null: value=null, remaining=[job]
poll job: job
poll empty: null
null tail: peek=null, get=null, size=2
remove stored tail null: value=null, remaining=[job]
sentinel loop: processed=[A], remaining=[B]
explicit-empty loop: processed=[A, null, B], remaining=[]
explicit result 1: Removal[present=true, value=null]
explicit result 2: Removal[present=false, value=null]
Optional after stored null: Optional.empty, remaining=[]
guard rejects null: remaining=[job]
ArrayDeque null: NullPointerException
unboxing removed null: NullPointerException, size=0
~~~

### 7.3. Đọc những điểm quyết định trong kết quả

Sau các lần thêm đầu/cuối, deque là `[Z, A, B, C]`. Hai nhóm `get` và `peek` đều giữ size = 4. `removeFirst` lấy Z, `pollLast` lấy C, còn `[A, B]`.

Nhóm FIFO lấy one trước two, trong khi ngăn xếp đã đẩy one rồi two lại lấy two trước. Đây là kết quả của các đầu được chọn, không phải hai lớp lưu trữ khác nhau.

Hai dòng `remove(1)` cho thấy kiểu tham chiếu ảnh hưởng việc chọn overload khi biên dịch: qua `Deque`, giá trị 1 bị xóa và kết quả trả là boolean; qua `LinkedList`, phần tử 2 tại chỉ số 1 bị xóa và được trả về.

Nhóm rỗng cho `null` ở `peek/poll` và `NoSuchElementException` ở `get/remove`. Chương trình chỉ in loại ngoại lệ, không phụ thuộc câu thông báo cụ thể của bản JDK.

Dòng `null head: size=2` chứng minh giá trị xem được là `null` mà danh sách vẫn còn phần tử. Lần `poll stored null` tiếp theo trả `null` nhưng đã xóa nút đầu, để lại `[job]`.

Ở cuối, `getLast` cũng trả được `null` khi có nút cuối chứa `null`. `removeLast` lấy/xóa nút đó bình thường; không có `NoSuchElementException` vì danh sách không rỗng.

Hai vòng lặp cho kết quả khác nhau:

- Mẫu sentinel dừng khi lấy ra `null`, còn B chưa xử lý.
- Mẫu kiểm tra rỗng tách khỏi giá trị xử lý đủ A, `null`, B trong điều kiện một luồng của ví dụ.

Hai record kết quả giữ sự khác biệt giữa “có phần tử null” và “không có phần tử”. `Optional.ofNullable` nhận kết quả `poll` lại không giữ được khác biệt đó.

Helper kiểm tra đầu vào từ chối `null` trước khi thêm nên danh sách guarded vẫn chỉ có job. `ArrayDeque` tự từ chối phần tử `null`. Cuối cùng, lỗi mở hộp xảy ra khi size đã về 0, xác nhận rằng lời gọi lấy/xóa có thể hoàn thành trước khi việc dùng giá trị bị lỗi.

Trong các dòng in, `null` là tham chiếu null do mã thêm trực tiếp; không phải chuỗi ký tự `"null"`. Chỉ nhìn chuỗi hiển thị của một collection bất kỳ không luôn phân biệt được hai dữ liệu này.

## 8. Chi phí và các giới hạn sử dụng

### 8.1. O(1) ở hai đầu là công việc liên kết

Với `LinkedList`, xem đầu/cuối và nối/tháo một nút ở đầu/cuối dùng số lượng cập nhật cấu trúc cố định. Không phải tìm nút giữa và không phải dịch một đoạn mảng.

Mã nguồn [LinkedList OpenJDK 17, bản jdk-17+35](https://raw.githubusercontent.com/openjdk/jdk/jdk-17%2B35/src/java.base/share/classes/java/util/LinkedList.java) thể hiện việc dùng tham chiếu đầu/cuối và cập nhật liên kết khi các nút được thêm hoặc bỏ.

Phân tích này không bảo đảm mỗi lần thêm có cùng độ trễ: cần cấp một nút mới, còn có ảnh hưởng của bộ nhớ và thu gom rác. Nó cũng không chứng minh `LinkedList` luôn nhanh hơn một deque dùng mảng trên mọi tải thực tế.

Nếu thuật toán chỉ thêm và tháo n phần tử ở các đầu, phần công việc quản lý liên kết có tổng O(n). Nếu lại đi tìm một giá trị giữa danh sách trước mỗi lần, phải cộng công việc tìm đó.

### 8.2. Null không thay đổi bậc chi phí nhưng thay đổi cách diễn giải

Lưu `null` vẫn tạo một phần tử và một nút. Lấy nó khỏi đầu không cần tìm kiếm thêm vì giá trị là `null`.

Vấn đề lớn của chính sách `null` ở đây là ý nghĩa dữ liệu và tính đúng của luồng xử lý, không phải một hệ số tốc độ. Tối ưu một thao tác nhanh không có ích nếu chương trình dừng sớm và bỏ sót công việc.

### 8.3. Không tự an toàn khi dùng nhiều luồng

Một đối tượng `LinkedList` thông thường không tự đồng bộ. Chuỗi `isEmpty` rồi `removeFirst` gồm hai hành động; luồng khác có thể thay đổi cấu trúc giữa hai hành động nếu không có phối hợp.

Chỉ khóa riêng từng lời gọi hoặc nhìn giá trị `null` sau một phép lấy chưa chắc đáp ứng đúng hợp đồng của cả quy trình. Cần thiết kế quyền truy cập, đồng bộ hoặc cấu trúc đồng thời theo yêu cầu cụ thể.

Các ví dụ cố ý dùng một luồng để làm rõ API. Không dùng chúng làm bằng chứng rằng hàng đợi nhiều luồng đã an toàn.

### 8.4. Tên kiểu giúp hạn chế những cách gọi không cần thiết

Nếu chỉ cần FIFO, có thể nhận/trả `Queue<E>`. Nếu cần hai đầu, `Deque<E>` thể hiện ý định. Nếu cần thêm cả truy cập danh sách theo chỉ số, phải đánh giá riêng chi phí đó thay vì coi mọi API trên `LinkedList` đều tương đương.

Dù dùng kiểu nào, hãy ghi rõ chính sách `null` ở hợp đồng của ứng dụng. Một biến `Deque<E>` không tự nói dữ liệu của nó cho phép `null` hay không; hai triển khai `LinkedList` và `ArrayDeque` đã có khác biệt này.

## 9. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| Deque luôn cấm null | Giao diện không bắt buộc mọi triển khai cấm; LinkedList cho phép |
| LinkedList cho phép null nên nên dùng null làm dấu rỗng | poll/peek đã dùng null làm tín hiệu; ứng dụng cần chính sách rõ |
| peekFirst trả null thì chắc chắn rỗng | Đầu có thể là phần tử null |
| pollFirst trả null thì không có gì bị xóa | Có thể vừa lấy/xóa một phần tử null thật |
| getFirst luôn trả giá trị khác null | Nó ném ngoại lệ khi không có nút, vẫn trả null nếu nút chứa null |
| removeFirst ném NullPointerException khi phần tử null | Bản thân LinkedList có thể trả null; lỗi có thể xảy ra ở mã xử lý sau đó |
| Bọc poll bằng Optional giải quyết mọi trạng thái | ofNullable gộp null dữ liệu và null báo rỗng thành Optional.empty |
| Offer không bao giờ ném lỗi | Nó không chuyển mọi lỗi đầu vào hoặc cấp phát thành false |
| Offer false là cách báo LinkedList hết bộ nhớ | LinkedList không có cơ chế sức chứa hữu hạn như vậy |
| Poll đợi đến khi có phần tử | Nó kiểm tra trạng thái hiện tại và trả ngay |
| Push rồi pollLast vẫn là cùng mẫu ngăn xếp | Hai thao tác dùng hai đầu khác nhau, cần kiểm tra thứ tự |
| remove(), remove(value), remove(index) đều lấy đầu | Đây là các hợp đồng khác nhau |
| isEmpty rồi remove là nguyên tử | Chỉ đúng khi đã có điều kiện phối hợp phù hợp cho cả chuỗi |
| Mọi thao tác LinkedList O(1) vì hai đầu O(1) | Tìm giữa theo chỉ số/giá trị vẫn cần chi phí tìm kiếm |

## 10. Bài tập tự kiểm tra

### Bài 1: đọc mà không lấy

Deque đang có `[A, B]`. Sau `peekFirst()`, `getLast()`, kích thước còn bao nhiêu? Hai giá trị trả về là gì?

**Giải thích:** Vẫn có 2 phần tử; kết quả lần lượt A và B. Cả hai chỉ xem.

### Bài 2: lấy ở hai đầu

Từ `[A, B, C]`, gọi `pollLast()` rồi `removeFirst()`. Còn gì?

**Giải thích:** Lấy C, sau đó lấy A, còn `[B]`. Hậu tố xác định phía tác động, không phụ thuộc nhóm ném ngoại lệ hay trả tín hiệu khi rỗng.

### Bài 3: một phần tử null

Deque đang chứa đúng một phần tử `null`. `getFirst()`, `isEmpty()` và `size()` cho gì?

**Giải thích:** `getFirst` trả `null`, `isEmpty` là false, size = 1. Xem đầu không xóa nút. Nếu tiếp theo gọi `removeFirst`, nó trả `null` và làm deque rỗng.

### Bài 4: dừng bằng sentinel

Với `[A, null, B, C]`, vòng `while ((x = pollFirst()) != null)` xử lý được những giá trị nào và để lại gì?

**Giải thích:** Chỉ xử lý A; phần tử null đã bị lấy ra khi kiểm tra điều kiện, vòng dừng và còn `[B, C]`.

### Bài 5: thứ tự ngăn xếp

Gọi `push("A")`, `push("B")`, `push("C")`, rồi `pop()`. Giá trị trả về là gì?

**Giải thích:** C, vì push và pop đều thao tác ở đầu; phần vào cuối cùng được lấy trước. Sau đó dãy đầu→cuối là `[B, A]`.

### Bài 6: đổi triển khai

Một biến kiểu `Deque<String>` hiện giữ `LinkedList` và dữ liệu có `null`. Chỉ đổi constructor sang `ArrayDeque` có bảo toàn mọi hành vi không?

**Giải thích:** Không. `ArrayDeque` không cho chèn `null`. Cần xem lại chính sách dữ liệu và mọi đường thêm phần tử, không chỉ giữ nguyên tên giao diện.

### Bài 7: kết quả có hiện diện

Vì sao `Removal(true, null)` khác `Removal(false, null)`, còn `Optional.ofNullable(pollFirst())` không phân biệt được hai trường hợp đó?

**Giải thích:** Record giữ một cờ riêng mô tả đã có phần tử hay chưa. Optional được tạo chỉ từ giá trị trả về; khi giá trị là null, cả hai nguồn gốc đều bị biểu diễn là không có giá trị.

Sử dụng hai đầu của `LinkedList` hiệu quả đòi hỏi chọn đúng **phía**, **tác động lên cấu trúc** và **cách báo rỗng**. Khi chính sách `null` được quyết định rõ, các cặp phương thức trở nên nhất quán và luồng xử lý tránh được việc nhầm một phần tử hợp lệ với sự kết thúc dữ liệu.
