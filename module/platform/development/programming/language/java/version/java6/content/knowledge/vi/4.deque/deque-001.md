# Hàng đợi hai đầu và quan hệ Queue, Deque

## 1. Hàng đợi hai đầu là gì?

Hàng đợi hai đầu, hay **deque** (double-ended queue), là một dãy phần tử cho phép thêm, lấy và xem phần tử ở cả hai đầu. Trong tên phương thức Java, hai đầu được gọi là `First` và `Last`.

Hãy vẽ một deque đang chứa ba yêu cầu:

```text
đầu trước (First / head)                 đầu sau (Last / tail)
            |                                     |
            v                                     v
          [ A ] -------- [ B ] -------- [ C ]
```

Ta có thể thêm một phần tử trước A, thêm sau C, lấy A hoặc lấy C. Không cần biết vị trí bên trong của B để thao tác với hai đầu.

Điểm cốt lõi là **khả năng truy cập hai đầu**, không phải một thứ tự xử lý duy nhất. Khi thêm cuối và lấy đầu, deque vận hành như hàng đợi FIFO. Khi thêm đầu và lấy đầu, nó vận hành như ngăn xếp LIFO.

- FIFO (First In, First Out): vào trước, ra trước.
- LIFO (Last In, First Out): vào sau, ra trước.

Ví dụ, xử lý hồ sơ theo thứ tự tiếp nhận thường cần FIFO. Lưu các bước để quay lui thường cần LIFO. Cả hai đều có thể dùng `Deque`, nhưng phải chọn đúng cặp thao tác.

Bài dùng các API vẫn được áp dụng trên Java hiện đại; ví dụ hoàn chỉnh chạy với JDK 17 trở lên. `Deque` có từ Java 6, còn cách sử dụng trong bài không yêu cầu môi trường Java 6.

## 2. Queue và Deque liên hệ như thế nào?

Trong Java, `Queue<E>` mô tả một tập hợp phần tử chờ được xử lý, với các thao tác thêm, lấy và xem phần tử kế tiếp. `Deque<E>` kế thừa `Queue<E>` và bổ sung cách thao tác rõ ràng ở cả hai đầu.

Quan hệ liên quan đến bài có thể hình dung như sau; sơ đồ này không liệt kê toàn bộ hệ thống kiểu:

```text
Collection<E>
     |
     v
  Queue<E>
     |
     v
  Deque<E>
     ^
     |
ArrayDeque<E> là một lớp triển khai
```

Vì vậy:

- Một đối tượng triển khai `Deque` cũng có thể được sử dụng qua biến kiểu `Queue`.
- Một đối tượng triển khai `Queue` chưa chắc có khả năng của `Deque`.
- `Queue` và `Deque` là giao diện; `ArrayDeque` là một lựa chọn triển khai cụ thể.

Đoạn sau là minh họa về kiểu tham chiếu, có thể đặt trong một phương thức sau khi import các kiểu tương ứng:

```java
Deque<String> deque = new ArrayDeque<>();
Queue<String> queue = deque;
```

Hai biến cùng trỏ tới **một đối tượng**. Dòng gán không sao chép dữ liệu, không tạo hàng đợi thứ hai và không đổi lớp triển khai.

Qua biến `queue`, mã nguồn có thể gọi `offer`, `poll`, `peek`. Qua biến `deque`, mã nguồn còn có thể chọn `offerFirst`, `offerLast`, `pollFirst`, `pollLast`.

Chiều ngược lại không tự động hợp lệ:

```java
Queue<String> queue = new PriorityQueue<>();
// Deque<String> deque = queue; // Không biên dịch: Queue không phải kiểu con của Deque.
```

Không nên ép kiểu để “thêm” khả năng hai đầu cho một đối tượng. Nếu đối tượng thực tế không triển khai `Deque`, phép ép kiểu không tạo khả năng đó và có thể gây `ClassCastException`.

Khi thiết kế một phương thức, dùng kiểu `Queue` nếu nó chỉ cần hợp đồng thêm và xử lý phần tử kế tiếp; dùng `Deque` nếu nó thực sự cần chọn một trong hai đầu. Nếu ca sử dụng yêu cầu FIFO, hãy ghi rõ yêu cầu thứ tự và chọn triển khai phù hợp, vì riêng tên giao diện `Queue` chưa đủ bảo đảm FIFO. [Hợp đồng Queue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Queue.html)

## 3. Queue không luôn có nghĩa là FIFO

“Hàng đợi” trong cách nói thông thường thường gợi ý người đến trước được phục vụ trước. Giao diện `Queue` rộng hơn ý tưởng ấy: phần tử được lấy ra phụ thuộc chính sách sắp thứ tự của triển khai.

Ví dụ:

| Cách sử dụng | Phần tử được lấy tiếp theo |
| --- | --- |
| `ArrayDeque`, chỉ thêm cuối và lấy đầu | Phần tử được thêm sớm nhất còn lại |
| `PriorityQueue` theo thứ tự tự nhiên của chuỗi | Chuỗi nhỏ nhất theo thứ tự so sánh |
| `Deque` dùng `push` và `pop` | Phần tử được đẩy vào gần nhất |

Với `PriorityQueue<String>` chứa B rồi A, hai lần `poll()` trả A rồi B. Nó vẫn là một `Queue`, nhưng không xử lý theo thứ tự thêm. Thứ tự ưu tiên do thứ tự tự nhiên hoặc `Comparator` quyết định; khi các phần tử có cùng mức ưu tiên, không nên suy ra thứ tự đến trước. Cũng không dùng thứ tự duyệt của iterator để kết luận thứ tự lấy ra. [Tài liệu PriorityQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/PriorityQueue.html)

Cần phân biệt hai câu hỏi:

1. Giao diện cho phép gọi thao tác gì?
2. Triển khai và cách sử dụng quyết định phần tử nào được lấy ra?

Đối với deque, cách gọi phương thức cũng rất quan trọng. Nếu một thành phần liên tục thêm cuối nhưng thành phần khác thỉnh thoảng chèn đầu, thứ tự xử lý chung sẽ khác FIFO theo thời điểm tiếp nhận ban đầu.

## 4. Ba thao tác, hai đầu, hai cách báo thất bại

Để đọc API `Deque`, hãy phân loại theo ba hành động:

- **Thêm:** đưa phần tử vào.
- **Lấy:** trả về phần tử và xóa nó khỏi deque.
- **Xem:** trả về phần tử nhưng giữ nguyên deque.

Mỗi hành động có phiên bản cho đầu trước và đầu sau. Ngoài ra, API có hai cách báo một số tình huống không thực hiện được.

| Hành động | Đầu trước: báo bằng ngoại lệ | Đầu trước: giá trị đặc biệt | Đầu sau: báo bằng ngoại lệ | Đầu sau: giá trị đặc biệt |
| --- | --- | --- | --- | --- |
| Thêm | `addFirst(e)` | `offerFirst(e)` | `addLast(e)` | `offerLast(e)` |
| Lấy | `removeFirst()` | `pollFirst()` | `removeLast()` | `pollLast()` |
| Xem | `getFirst()` | `peekFirst()` | `getLast()` | `peekLast()` |

Với thao tác lấy hoặc xem khi deque rỗng:

- `removeFirst`, `removeLast`, `getFirst`, `getLast` ném `NoSuchElementException`.
- `pollFirst`, `pollLast`, `peekFirst`, `peekLast` trả `null`.

Với deque có giới hạn sức chứa, dạng `offer...` có thể trả `false` nếu không còn chỗ, còn dạng `add...` báo thất bại do đầy bằng ngoại lệ. Điều này không có nghĩa `offer...` biến mọi lỗi thành `false`: đầu vào không hợp lệ, chẳng hạn `null` trong một triển khai cấm `null`, vẫn có thể gây ngoại lệ. [Các nhóm phương thức Deque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/Deque.html)

### Chọn giữa poll và remove theo ý nghĩa của tình huống rỗng

Nếu “chưa có việc” là trạng thái bình thường, `pollFirst()` giúp mã xử lý trực tiếp:

```java
// Minh họa trong phương thức; pending là Deque<String> không chứa null.
String next = pending.pollFirst();
if (next != null) {
    System.out.println(next);
}
```

Nếu thuật toán có một điều kiện đã bảo đảm phải tồn tại phần tử, `removeFirst()` có thể thể hiện yêu cầu đó; ngoại lệ giúp phát hiện khi điều kiện bị vi phạm.

Không nên bắt `NoSuchElementException` rồi bỏ qua một cách máy móc. Trước hết cần xác định rỗng là trạng thái hợp lệ hay lỗi trong giả định của chương trình.

### Xem không phải là lấy

Sau `peekFirst()`, phần tử vẫn còn ở đầu. Nếu dùng `peekFirst()` trong vòng lặp nhưng không có thao tác xóa hoặc thay đổi điều kiện, chương trình có thể xử lý lặp mãi cùng một phần tử.

Ngược lại, `pollFirst()` vừa trả phần tử vừa xóa nó. Khi ca sử dụng muốn tiếp tục giữ phần tử cho một bước khác, không nên dùng thao tác lấy rồi giả định dữ liệu vẫn còn nguyên.

## 5. Các phương thức Queue được ánh xạ vào Deque ra sao?

Khi một đối tượng được dùng như `Deque`, các thao tác thừa hưởng từ `Queue` có ý nghĩa cụ thể:

| Phương thức Queue | Tương ứng trong Deque |
| --- | --- |
| `add(e)` | `addLast(e)` |
| `offer(e)` | `offerLast(e)` |
| `remove()` | `removeFirst()` |
| `poll()` | `pollFirst()` |
| `element()` | `getFirst()` |
| `peek()` | `peekFirst()` |

Vì vậy, với cùng một đối tượng deque, `offer(e)` đưa phần tử vào cuối, còn `poll()` lấy phần tử ở đầu. Đây là cách sử dụng FIFO thông thường.

Cần đọc đúng chữ ký phương thức. `remove()` không có đối số là thao tác lấy đầu. `remove(Object)` có đối số tìm và xóa một phần tử bằng giá trị, trả về `boolean`; nó không phải thao tác lấy đầu và cũng không phải xóa theo chỉ số.

Ví dụ minh họa trong một phương thức:

```java
Queue<Integer> numbers = new ArrayDeque<>();
numbers.offer(10);
numbers.offer(20);

boolean removed = numbers.remove(20); // Xóa giá trị Integer 20.
Integer head = numbers.remove();      // Lấy giá trị đầu là 10.
```

Sự khác nhau này dễ bị bỏ qua khi đã quen với `List`. Deque không cung cấp `get(index)` để truy cập theo vị trí; nó phù hợp khi thuật toán tập trung vào hai đầu.

## 6. Tạo FIFO và LIFO bằng cách chọn đúng đầu

### FIFO: thêm cuối, lấy đầu

Giả sử lần lượt tiếp nhận A, B và C:

```text
offerLast(A): [ A ]
offerLast(B): [ A, B ]
offerLast(C): [ A, B, C ]

pollFirst():  A, còn [ B, C ]
pollFirst():  B, còn [ C ]
pollFirst():  C, còn [ ]
```

Tên phương thức chỉ rõ ý định. Nếu mã nguồn chỉ cần hàng đợi, cặp `offer` và `poll` trên một `ArrayDeque` cũng có cùng tác dụng.

Ứng dụng điển hình là một danh sách việc đang chờ trong một tiến trình, nơi chính sách yêu cầu xử lý theo thứ tự thêm và không có thành phần khác thay đổi đầu trước.

### LIFO: thêm đầu, lấy đầu

Đối với ngăn xếp, phần tử mới nhất phải được lấy trước:

```text
push(A): [ A ]
push(B): [ B, A ]
push(C): [ C, B, A ]

pop():   C, còn [ B, A ]
pop():   B, còn [ A ]
pop():   A, còn [ ]
```

Trong `Deque`, `push(e)` tương ứng với thêm đầu và `pop()` tương ứng với lấy đầu theo dạng ném ngoại lệ nếu rỗng. `peek()` xem phần tử ở đầu mà không xóa.

LIFO hữu ích với trạng thái cần quay lui theo thứ tự ngược. Chẳng hạn, nếu đã thực hiện bước A rồi bước B, thao tác quay lui thường phải hoàn tác B trước A. Tuy nhiên, chính nghiệp vụ phải định nghĩa cách hoàn tác; deque chỉ giữ thứ tự các bước.

Một deque cũng có thể tạo LIFO bằng thêm cuối và lấy cuối. Nên chọn một quy ước rõ ràng và dùng nhất quán trong cùng thuật toán, thay vì trộn các cặp phương thức làm người đọc phải suy luận lại đầu nào là “đỉnh”.

### Thêm đầu không tạo ra một hàng đợi ưu tiên tổng quát

Chèn một yêu cầu khẩn cấp bằng `offerFirst` có thể đáp ứng một quy tắc đơn giản. Nhưng nếu cần sắp nhiều mức ưu tiên, quy tắc xử lý khi bằng mức, hoặc chống bỏ đói việc thường, phải thiết kế chính sách riêng.

Deque không tự so sánh độ ưu tiên. Hơn nữa, nếu liên tục chèn các việc khẩn cấp mới vào đầu, việc khẩn cấp được chèn gần nhất sẽ đứng trước việc khẩn cấp đã có. Đó có thể không phải thứ tự nghiệp vụ mong muốn.

## 7. Chương trình hoàn chỉnh: FIFO, LIFO và hai tham chiếu

Ví dụ sau dùng `ArrayDeque` để minh họa hai đầu. Một phần nhỏ dùng `PriorityQueue` nhằm kiểm chứng rằng `Queue` không đồng nghĩa FIFO.

Lưu tệp `QueueDequeDemo.java`:

```java
import java.util.ArrayDeque;
import java.util.Deque;
import java.util.PriorityQueue;
import java.util.Queue;

public class QueueDequeDemo {
    public static void main(String[] args) {
        Deque<String> fifo = new ArrayDeque<>();
        fifo.offerLast("A");
        fifo.offerLast("B");
        System.out.println("fifoPeek=" + fifo.peekFirst());
        System.out.println("fifoSize=" + fifo.size());
        System.out.println("fifo=" + fifo.pollFirst() + "," + fifo.pollFirst());
        System.out.println("fifoEmpty=" + fifo.pollFirst());

        Deque<String> lifo = new ArrayDeque<>();
        lifo.push("A");
        lifo.push("B");
        System.out.println("lifo=" + lifo.pop() + "," + lifo.pop());

        Deque<String> bothEnds = new ArrayDeque<>();
        Queue<String> queueView = bothEnds;
        queueView.offer("A");
        queueView.offer("B");
        bothEnds.offerFirst("URGENT");
        System.out.println("sameObject=" + (bothEnds == queueView));
        System.out.println("mixed=" + queueView.poll()
                + "," + queueView.poll() + "," + queueView.poll());

        Queue<String> priority = new PriorityQueue<>();
        priority.offer("B");
        priority.offer("A");
        System.out.println("priority=" + priority.poll() + "," + priority.poll());

        try {
            fifo.removeFirst();
        } catch (java.util.NoSuchElementException e) {
            System.out.println("emptyRemove=" + e.getClass().getSimpleName());
        }
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```shell
javac --release 17 QueueDequeDemo.java
java QueueDequeDemo
```

Stdout:

```text
fifoPeek=A
fifoSize=2
fifo=A,B
fifoEmpty=null
lifo=B,A
sameObject=true
mixed=URGENT,A,B
priority=A,B
emptyRemove=NoSuchElementException
```

### Giải thích từng nhóm kết quả

**`fifoPeek=A` và `fifoSize=2`:** xem đầu không xóa A nên kích thước vẫn là 2.

**`fifo=A,B`:** thêm A rồi B ở cuối và lấy ở đầu giữ thứ tự vào trước, ra trước. Sau hai lần lấy, deque rỗng.

**`fifoEmpty=null`:** `pollFirst()` trên deque rỗng không ném ngoại lệ.

**`lifo=B,A`:** `push` đưa cả hai phần tử vào đầu; B vào sau nên được `pop` trước.

**`sameObject=true`:** `bothEnds` và `queueView` tham chiếu cùng đối tượng, dù có kiểu khai báo khác nhau.

**`mixed=URGENT,A,B`:** sau khi A và B được thêm qua `queueView`, việc chèn URGENT vào đầu qua `bothEnds` ảnh hưởng ngay tới lần `queueView.poll()` kế tiếp. Kiểu tham chiếu `Queue` không tạo ra một bản sao độc lập và không ngăn thành phần khác thao tác trên cùng deque.

**`priority=A,B`:** hàng đợi ưu tiên chọn A trước B theo thứ tự tự nhiên, dù B được thêm trước.

**`emptyRemove=NoSuchElementException`:** khác với `pollFirst`, `removeFirst` báo deque rỗng bằng ngoại lệ. Ví dụ bắt ngoại lệ chỉ để quan sát hợp đồng.

Chương trình chạy trong một luồng và dùng chuỗi khác `null`. Các kết quả trên không phải bằng chứng về an toàn truy cập đồng thời hay khả năng phục hồi sau khi tiến trình dừng.

## 8. Chọn kiểu khai báo và quản lý quyền thay đổi

Quan hệ kế thừa giúp biểu đạt mức khả năng mà một đoạn mã cần, nhưng không thay thế việc quản lý ai có thể thay đổi đối tượng.

Nếu một bộ xử lý chỉ được phép thêm cuối và lấy đầu, cung cấp một tham chiếu `Queue` có thể làm hợp đồng dễ đọc hơn. Tuy nhiên, nếu nơi khác vẫn giữ `Deque` và tự ý chèn đầu hoặc xóa cuối, chính sách FIFO của toàn bộ hệ thống có thể bị phá vỡ.

Có thể cân nhắc:

- Giữ deque bên trong một lớp quản lý việc đang chờ.
- Chỉ cung cấp các thao tác nghiệp vụ được phép, như “tiếp nhận” và “lấy việc kế tiếp”.
- Không phát tán tham chiếu có thể sửa khi bên ngoài chỉ cần xem trạng thái.
- Ghi rõ chính sách thứ tự, trạng thái rỗng và cách xử lý thất bại.

Đây là cách bảo vệ điều kiện của thuật toán. Chỉ đổi kiểu biến từ `Deque` thành `Queue` không tạo ra một hàng rào bất biến cho đối tượng.

Tương tự, nếu một thuật toán thực sự cần xử lý cả hai đầu, khai báo `Deque` giúp tránh ép kiểu và truyền đạt rõ nhu cầu. Chọn giao diện nên xuất phát từ hành vi cần dùng, còn việc chọn lớp triển khai cần xét thêm điều kiện chạy.

## 9. Các giới hạn quan trọng của ArrayDeque

`ArrayDeque` là lựa chọn trực tiếp để thực hành vì có thể dùng cho cả FIFO và LIFO trong một luồng. Khi áp dụng, cần phân biệt hợp đồng của giao diện với đặc điểm của lớp này:

- Nó không cho phép phần tử `null`.
- Nó mở rộng khi cần; dung lượng khởi tạo không phải sức chứa tối đa cố định.
- Nó không tự bảo đảm an toàn khi nhiều luồng cùng truy cập.
- Phần lớn thao tác hai đầu có chi phí hằng số khấu hao; tìm kiếm hoặc xóa theo giá trị có thể cần duyệt nhiều phần tử.

“Hằng số khấu hao” không có nghĩa mọi lần thêm đều mất thời gian như nhau; một số lần có thể cần mở rộng bộ chứa. [Tài liệu ArrayDeque](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/ArrayDeque.html)

Các điểm trên dẫn đến những quyết định thực tế:

**Dùng `null` như một công việc đặc biệt:** không phù hợp với `ArrayDeque`. Hãy có một biểu diễn rõ ràng khác nếu nghiệp vụ cần tín hiệu kết thúc, đồng thời phân biệt tín hiệu ấy với “chưa có phần tử”.

**Giới hạn số việc đang chờ:** không thể chỉ truyền một số nhỏ vào hàm tạo rồi coi hàng đợi đã được giới hạn. Phải chọn cơ chế có giới hạn sức chứa hoặc thiết kế kiểm soát tiếp nhận phù hợp.

**Nhiều luồng cùng làm việc:** cần chọn triển khai và giao thức đồng thời phù hợp. `Queue` và `Deque` không tự mang ý nghĩa “chặn chờ” hoặc “an toàn đa luồng”. Ngay cả khi từng thao tác trên một triển khai là an toàn, một chuỗi kiểm tra rồi thay đổi vẫn cần xem xét tính nguyên tử.

**Độ bền dữ liệu:** một deque trong bộ nhớ không tự ghi lại công việc để phục hồi sau khi chương trình dừng. Yêu cầu bền vững thuộc một thiết kế lưu trữ hoặc trao đổi khác.

## 10. Các lỗi dễ mắc khi học quan hệ Queue, Deque

### Nghĩ mọi Queue đều là Deque

`Deque` là một khả năng cụ thể hơn của `Queue`. Một hàng đợi ưu tiên không trở thành deque chỉ vì cùng có `offer` và `poll`.

### Nghĩ phương thức không ghi First/Last là mơ hồ trong Deque

Các phương thức thừa hưởng đã có ánh xạ rõ: thêm ở cuối và lấy hoặc xem ở đầu. Hãy nhớ ánh xạ đó thay vì suy đoán theo vị trí mà phần tử vừa được thêm.

### Dùng peek để tiêu thụ phần tử

`peek` chỉ xem. Nếu chương trình muốn xử lý mỗi phần tử một lần rồi loại khỏi hàng đợi, phải có thao tác lấy phù hợp.

### Cho rằng offer không bao giờ ném ngoại lệ

Dạng trả `boolean` giúp biểu diễn thất bại do không thể tiếp nhận trong các điều kiện được hợp đồng quy định. Nó không miễn kiểm tra điều kiện hợp lệ của phần tử.

### Trộn FIFO và LIFO trên cùng dữ liệu mà không có chính sách

Bản thân deque cho phép phối hợp nhiều thao tác. Nhưng nếu người viết định dùng FIFO rồi vô tình gọi `push`, phần tử mới sẽ vào đầu. Lỗi nằm ở việc chọn thao tác không phù hợp chính sách.

### Cho rằng gán sang Queue đã khóa hành vi hai đầu

Kiểu của biến giới hạn những phương thức gọi được qua biến đó. Nó không xóa các tham chiếu khác và không đổi khả năng thực tế của đối tượng.

## 11. Tự thực hành và kiểm tra cách hiểu

### Bài 1: Dự đoán hai đầu

Thực hiện trên một deque rỗng:

```text
offerLast("A")
offerFirst("B")
offerLast("C")
pollLast()
pollFirst()
pollFirst()
```

Ba giá trị được lấy ra là C, B, A. Trước lần lấy đầu tiên, thứ tự từ First tới Last là B, A, C.

### Bài 2: Thay một phương thức

Trong phần FIFO của chương trình, thay `fifo.offerLast("B")` bằng `fifo.offerFirst("B")`.

Trước khi chạy, dự đoán lại ba dòng đầu. Kết quả trở thành:

```text
fifoPeek=B
fifoSize=2
fifo=B,A
```

Sự thay đổi này cho thấy kiểu `Deque` không tự áp đặt FIFO; thứ tự phụ thuộc cách thêm và lấy.

### Bài 3: Kiểm tra quan hệ kiểu

Viết một phương thức nhận `Queue<String>` chỉ gọi `offer` và `poll`. Truyền vào một `ArrayDeque<String>` là hợp lệ.

Sau đó thử gọi `offerFirst` ngay trên tham số kiểu `Queue<String>`. Mã không biên dịch vì hợp đồng của kiểu khai báo không có phương thức đó. Không sửa bằng ép kiểu nếu phương thức vốn không cần thao tác hai đầu.

### Bài 4: Chọn cấu trúc theo chính sách

Đối với mỗi nhu cầu, hãy nói rõ thao tác và giới hạn:

| Nhu cầu | Một cách biểu đạt |
| --- | --- |
| Xử lý việc cục bộ theo thứ tự tiếp nhận | FIFO: thêm cuối, lấy đầu |
| Quay lui các bước gần nhất | LIFO: `push`, `pop` |
| Luôn lấy công việc có khóa ưu tiên nhỏ nhất | Cần chính sách ưu tiên; không suy ra từ FIFO |
| Chờ công việc giữa nhiều luồng, có giới hạn tồn đọng | Cần xem thêm hợp đồng chặn chờ, đồng thời và sức chứa |
| Giữ việc qua lần khởi động lại | Cần thêm cơ chế bền vững ngoài deque trong bộ nhớ |

Khi giải thích lựa chọn, hãy nói được **phần tử nào sẽ được lấy tiếp theo**, **thao tác nào thay đổi deque**, và **điều gì xảy ra khi rỗng**. Ba câu trả lời đó quan trọng hơn việc chỉ nhớ tên một lớp collection.
