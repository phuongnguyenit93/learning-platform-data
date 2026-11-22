# Các cặp add–offer, remove–poll và element–peek

## 1. Ba công việc, hai cách báo không thực hiện được

Một hàng đợi lưu phần tử trước khi chúng được xử lý. Khi dùng nó, bạn thường cần ba việc: đưa thêm phần tử vào, lấy phần tử ra, hoặc chỉ xem phần tử sắp được lấy.

Mỗi việc có hai phương thức tương ứng trong `Queue`. Khi thao tác có thể thực hiện được, các phương thức trong cùng cặp có mục đích tương đương. Chúng khác nhau rõ nhất khi hàng đợi đầy hoặc rỗng:

- `add(e)` và `offer(e)` dùng để thêm.
- `remove()` và `poll()` dùng để lấy ra và xóa.
- `element()` và `peek()` dùng để xem nhưng giữ nguyên phần tử.

Một phía báo tình trạng không thực hiện được bằng ngoại lệ; phía còn lại dùng giá trị đặc biệt là `false` hoặc `null`. Tuy nhiên, điều đó không có nghĩa mọi lỗi dữ liệu của `offer` đều được biến thành `false`.

Bài học sẽ giải thích từng cặp, kiểm chứng hàng đợi rỗng và hàng đợi có giới hạn dung lượng, rồi làm rõ các nhầm lẫn về null, thứ tự và phương thức `remove` có đối số. Mã hoàn chỉnh dùng API có trong Java 17.

Bạn cần biết biến, lời gọi phương thức, điều kiện và vòng lặp. Cách đọc kiểu `Queue<String>`, các giá trị trả về và các ngoại lệ chính được giới thiệu tại chỗ.

## 2. Queue, đầu hàng đợi và lớp triển khai

`Queue<E>` là một interface, trong đó `E` là kiểu phần tử. Ví dụ:

~~~java
Queue<String> pending = new ArrayDeque<>();
~~~

Đây là khai báo minh họa; cần nhập `java.util.Queue` và `java.util.ArrayDeque` khi đặt vào chương trình.

`Queue<String>` cho biết đoạn mã đang làm việc với hợp đồng hàng đợi chuỗi. `ArrayDeque` là lớp cụ thể cung cấp đối tượng phía sau biến. Bạn có thể gọi các thao tác của `Queue` qua biến `pending` mà không cần biết chi tiết mảng bên trong.

**Đầu hàng đợi** (head) là phần tử mà `remove()` hoặc `poll()` sẽ lấy ra. `element()` và `peek()` cũng quan sát chính đầu này, nhưng không lấy nó ra.

Trong một hàng đợi FIFO — vào trước, ra trước — phần tử mới thường được thêm vào đuôi, còn việc lấy ra diễn ra ở đầu:

~~~text
lấy ra ← đầu [A, B, C] đuôi ← thêm mới

A được lấy trước B, B trước C.
~~~

Các tên phương thức không tự bảo đảm mọi lớp triển khai đều FIFO. Ví dụ `PriorityQueue` chọn đầu theo độ ưu tiên. Vì vậy, trước khi dự đoán phần tử được trả về, phải biết quy tắc thứ tự của lớp đang dùng. [Java 17: Queue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Queue.html).

## 3. Bảng hợp đồng của sáu phương thức

Với một hàng đợi có thể sửa và dữ liệu hợp lệ:

| Mục đích | Dạng dùng ngoại lệ | Dạng dùng giá trị đặc biệt | Khi thành công |
| --- | --- | --- | --- |
| Thêm một phần tử | `add(e)` | `offer(e)` | Thêm phần tử và trả `true` |
| Lấy ra đầu hàng đợi | `remove()` | `poll()` | Trả phần tử đầu và xóa nó |
| Xem đầu hàng đợi | `element()` | `peek()` | Trả phần tử đầu, không xóa |

Các tình huống không thực hiện được cần đọc riêng:

| Tình huống | Phương thức | Kết quả |
| --- | --- | --- |
| Hết chỗ do giới hạn dung lượng | `add(e)` | `IllegalStateException` |
| Hết chỗ do giới hạn dung lượng | `offer(e)` | `false` |
| Không có phần tử để lấy | `remove()` | `NoSuchElementException` |
| Không có phần tử để lấy | `poll()` | `null` |
| Không có phần tử để xem | `element()` | `NoSuchElementException` |
| Không có phần tử để xem | `peek()` | `null` |

`add` và `offer` trả `boolean`, còn bốn phương thức đọc/lấy trả phần tử kiểu `E`. Đừng đọc `poll` như một phép chỉ trả lời có xóa được hay không: nó trả chính phần tử vừa được lấy ra.

“Dạng dùng giá trị đặc biệt” chỉ nói về tình huống đầy hoặc rỗng tương ứng. Những vi phạm hợp đồng khác như thêm null vào lớp cấm null có thể vẫn ném ngoại lệ.

## 4. add và offer: thêm giống nhau, báo hết chỗ khác nhau

Với hàng đợi FIFO đang có `[A]` và còn chỗ:

~~~text
add(B)   → true; hàng đợi thành [A, B]
~~~

Nếu thay bằng `offer(B)` trên cùng trạng thái ban đầu, việc thêm cũng thành công và trả `true`.

Không phải `add` tự thêm ở đầu còn `offer` tự thêm ở cuối. Vị trí thêm do hợp đồng của lớp triển khai quyết định; hai tên trong cặp không biểu thị hai hướng khác nhau.

Sự khác biệt cần quan sát xuất hiện khi hàng đợi có sức chứa cố định. Ví dụ, `ArrayBlockingQueue` được tạo với sức chứa 2:

~~~java
Queue<String> bounded = new ArrayBlockingQueue<>(2);
~~~

Sau khi thêm A và B, không còn chỗ cho C:

~~~text
offer(C) → false
add(C)   → IllegalStateException
~~~

C không được thêm trong cả hai trường hợp trên. Hàng đợi vẫn chứa `[A, B]`. `offer` không âm thầm thay A bằng C và cũng không tự xóa phần tử cũ để tạo chỗ.

Khi lấy A ra, hàng đợi còn B và có chỗ trống. Một lần `offer(C)` mới có thể thành công, tạo `[B, C]`. Đây là một thao tác thêm mới ở thời điểm sau, không phải lần offer bị từ chối trước đó đang chờ ngầm.

`ArrayBlockingQueue` là hàng đợi có dung lượng cố định. Chương trình trong bài dùng nó để tạo tình huống đầy một cách xác định, không tạo thêm luồng hoặc chờ đợi. [Java 17: ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html).

## 5. Khi offer trả false, chương trình phải quyết định tiếp theo

Chọn `offer` khi việc hàng đợi hết chỗ là một tình huống mà mã gọi cần xử lý bằng nhánh thông thường. Ví dụ, một hàm nhận yêu cầu có thể trả lại kết quả “chưa nhận được” cho nơi gửi.

Nếu bỏ qua giá trị trả về:

~~~java
// Minh họa việc bỏ qua kết quả; không chứng minh phần tử đã được nhận.
pending.offer("job-3");
~~~

bạn không biết phần tử đã vào hàng đợi hay bị từ chối. Không có ngoại lệ không đồng nghĩa thêm thành công.

Một phương thức minh họa thể hiện rõ việc nhận được hay chưa:

~~~java
static boolean trySubmit(Queue<String> pending, String job) {
    return pending.offer(job);
}
~~~

Đây là một phương thức để đặt trong lớp, giả sử chính sách của hàng đợi và dữ liệu đầu vào đã được xác định. Bên gọi vẫn phải dùng kết quả, chẳng hạn báo chưa nhận hoặc thực hiện chính sách thử lại có kiểm soát.

`true` chỉ xác nhận phần tử được thêm theo thao tác hàng đợi. Nó không chứng minh công việc đã được xử lý xong, kết quả đã được lưu hay phần tử không thể bị một tác nhân khác lấy ra ngay sau đó.

Chọn `add` khi không thêm được do dung lượng thể hiện một điều bất thường mà hợp đồng của đoạn mã muốn báo bằng ngoại lệ. Không có quy tắc rằng `offer` luôn đúng còn `add` luôn sai; cách chọn phải phù hợp với ý nghĩa tình trạng hết chỗ đối với bên gọi.

Cũng không dùng vòng lặp thử `offer` liên tục không có điều kiện dừng chỉ để làm mất kết quả false. Nếu cần chờ có chỗ, hãy chọn rõ một API và chính sách chờ phù hợp thay vì biến một thao tác tức thời thành vòng lặp tiêu tốn tài nguyên.

## 6. offer không có nghĩa “không bao giờ ném ngoại lệ”

Một `ArrayDeque` không nhận phần tử `null`. Cả:

~~~java
pending.add(null);
pending.offer(null);
~~~

đều ném `NullPointerException` nếu `pending` trỏ tới một `ArrayDeque`. Hai dòng trên là minh họa riêng từng lời gọi, không phải hai lệnh cần chạy nối tiếp mà không xử lý lỗi.

`false` của `offer` không được dùng như một mã chung thay cho mọi lỗi lập trình. Một kiểu phần tử không được lớp triển khai chấp nhận, hoặc thuộc tính phần tử vi phạm giới hạn của lớp đó, cũng có thể dẫn đến ngoại lệ thích hợp.

Đối với `PriorityQueue`, các phần tử còn phải so sánh được theo quy tắc mà hàng đợi dùng. Việc đổi từ `add` sang `offer` không tự tạo ra thứ tự cho các đối tượng không so sánh được.

Quy tắc thực hành là tách:

- **Không thể thêm lúc này vì dung lượng:** xử lý kết quả của offer hoặc ngoại lệ của add.
- **Phần tử vi phạm hợp đồng đầu vào:** sửa/kiểm tra dữ liệu hoặc xử lý lỗi theo hợp đồng của chương trình.

Không bao quanh mọi thứ bằng `catch (Exception)` rồi coi tất cả thành “hàng đợi đầy”. Cách đó che lẫn lỗi dữ liệu với tình huống không có chỗ.

## 7. remove() và poll(): cùng lấy ra đầu hàng đợi

Với FIFO đang chứa `[A, B]`:

~~~text
remove() → trả A; còn [B]
~~~

Nếu dùng `poll()` trên cùng trạng thái ban đầu, cũng trả A và để lại B.

Cả hai đều xóa phần tử được trả về. Không cần gọi `remove` thêm sau khi đã `poll` thành công. Nếu bạn làm vậy, có thể lấy nhầm phần tử kế tiếp.

Khi hàng đợi rỗng:

~~~text
remove() → NoSuchElementException
poll()   → null
~~~

Chọn `poll` khi hết phần tử là một kết quả dự kiến, chẳng hạn một lượt xử lý lấy hết những gì hiện có. Chọn `remove` khi đoạn mã có hợp đồng phải có phần tử và việc rỗng là dấu hiệu vi phạm giả định cần được báo rõ.

Với một hàng đợi đã quy định không chứa null, có thể viết:

~~~java
String next = pending.poll();
if (next != null) {
    System.out.println("Received: " + next);
}
~~~

Đây là đoạn minh họa với biến `pending` đã khai báo. Nếu `next` khác null, phần tử đã rời hàng đợi trước khi lệnh in chạy. Nếu xử lý sau đó thất bại, Queue không tự đưa nó trở lại.

Đừng gán ngay kết quả `poll` cho biến nguyên thủy như `int` nếu hàng đợi có thể rỗng. Kết quả `Integer` bằng null sẽ gây lỗi khi tự mở gói, trước khi bạn kịp kiểm tra tình trạng không có dữ liệu.

## 8. element và peek: chỉ xem, không lấy ra

Với hàng đợi ổn định `[A, B]`:

~~~text
element() → A; hàng đợi vẫn [A, B]
peek()    → A; hàng đợi vẫn [A, B]
~~~

Nếu không có thao tác khác làm thay đổi dữ liệu, gọi lại sẽ vẫn xem A. Hai phương thức này không đánh dấu “A đã xử lý” và không làm B lên đầu.

Khi rỗng:

~~~text
element() → NoSuchElementException
peek()    → null
~~~

Một lỗi phổ biến là dùng `peek` làm cả điều kiện lẫn thao tác xử lý trong vòng lặp, nhưng không bao giờ xóa:

~~~java
// Minh họa lỗi: nếu hàng đợi không đổi, phần tử đầu được đọc lặp lại.
while (pending.peek() != null) {
    System.out.println(pending.peek());
}
~~~

Đoạn này không phù hợp để lấy hết dữ liệu; trên hàng đợi không rỗng và không bị thay đổi, nó không tự tiến qua phần tử kế tiếp. Dùng `poll` để lấy ra hoặc dùng bộ duyệt nếu chỉ muốn đọc từng phần tử một lần theo chính sách duyệt của lớp.

`peek` cũng không giữ chỗ hoặc dành riêng phần tử cho người đọc. Một lần `peek` rồi một lần `poll` sau đó là hai lời gọi riêng. Nếu có mã khác hoặc luồng khác xen vào sửa hàng đợi, không được mặc định hai lần ấy đang nói về cùng phần tử.

## 9. Chương trình đầy đủ kiểm chứng sáu phương thức

Lưu mã thành `QueueMethodPairsDemo.java`. Ví dụ dùng:

- `ArrayDeque` cho thao tác FIFO cơ bản và chính sách cấm null.
- `ArrayBlockingQueue` sức chứa 2 để kiểm chứng hết chỗ.
- `LinkedList` để làm lộ sự mơ hồ nếu cho null vào Queue.
- `PriorityQueue` để phân biệt đầu theo ưu tiên với đầu theo lịch sử đến.
- `Deque` để liên hệ các tên phương thức.

Hàm `drainNonNullQueue` có điều kiện dữ liệu rõ trong tên: hàng đợi không lưu null. Chương trình chỉ gọi nó với PriorityQueue, lớp cấm null.

~~~java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Deque;
import java.util.LinkedList;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.PriorityQueue;
import java.util.Queue;
import java.util.concurrent.ArrayBlockingQueue;

public class QueueMethodPairsDemo {
    static <E> List<E> drainNonNullQueue(Queue<E> queue) {
        List<E> values = new ArrayList<>();
        E value;
        while ((value = queue.poll()) != null) {
            values.add(value);
        }
        return values;
    }

    public static void main(String[] args) {
        Queue<String> fifo = new ArrayDeque<>();
        System.out.println("fifo add A=" + fifo.add("A"));
        System.out.println("fifo offer B=" + fifo.offer("B"));
        System.out.println("fifo=" + fifo);
        System.out.println("peek=" + fifo.peek());
        System.out.println("element=" + fifo.element());
        System.out.println("after inspection=" + fifo);
        System.out.println("poll=" + fifo.poll());
        System.out.println("after poll=" + fifo);
        System.out.println("remove=" + fifo.remove());
        System.out.println("after remove=" + fifo);
        System.out.println("empty poll=" + fifo.poll());
        System.out.println("empty peek=" + fifo.peek());
        try {
            fifo.remove();
        } catch (NoSuchElementException exception) {
            System.out.println("empty remove=" + exception.getClass().getSimpleName());
        }
        try {
            fifo.element();
        } catch (NoSuchElementException exception) {
            System.out.println("empty element=" + exception.getClass().getSimpleName());
        }

        Queue<String> bounded = new ArrayBlockingQueue<>(2);
        System.out.println("bounded offer A=" + bounded.offer("A"));
        System.out.println("bounded add B=" + bounded.add("B"));
        System.out.println("bounded full offer C=" + bounded.offer("C"));
        System.out.println("bounded after rejected offer=" + bounded);
        try {
            bounded.add("C");
        } catch (IllegalStateException exception) {
            System.out.println("bounded full add=" + exception.getClass().getSimpleName());
        }
        System.out.println("bounded after rejected add=" + bounded);
        System.out.println("bounded poll=" + bounded.poll());
        System.out.println("bounded retry offer C=" + bounded.offer("C"));
        System.out.println("bounded remaining=" + bounded);

        Queue<Integer> growing = new ArrayDeque<>(1);
        System.out.println("growing offers="
                + growing.offer(1) + "/" + growing.offer(2) + "/" + growing.offer(3));
        System.out.println("growing size=" + growing.size());

        Queue<String> noNull = new ArrayDeque<>();
        try {
            noNull.offer(null);
        } catch (NullPointerException exception) {
            System.out.println("offer null=" + exception.getClass().getSimpleName());
        }
        try {
            noNull.add(null);
        } catch (NullPointerException exception) {
            System.out.println("add null=" + exception.getClass().getSimpleName());
        }
        System.out.println("after invalid inserts size=" + noNull.size());

        Queue<String> permissive = new LinkedList<>();
        permissive.offer(null);
        permissive.offer("tail");
        System.out.println("nullable peek=" + permissive.peek());
        System.out.println("nullable size after peek=" + permissive.size());
        System.out.println("nullable poll=" + permissive.poll());
        System.out.println("nullable empty after poll=" + permissive.isEmpty());
        System.out.println("nullable remaining=" + permissive);

        Queue<String> named =
                new ArrayDeque<>(List.of("head", "middle", "tail"));
        System.out.println("remove middle=" + named.remove("middle"));
        System.out.println("after value remove=" + named);
        System.out.println("remove head=" + named.remove());
        System.out.println("remove missing=" + named.remove("missing"));
        System.out.println("after both removals=" + named);

        Queue<Integer> priority = new PriorityQueue<>();
        priority.addAll(List.of(7, 2, 5, 2));
        System.out.println("priority size=" + priority.size());
        System.out.println("priority peek=" + priority.peek());
        System.out.println("priority remove=" + priority.remove());
        System.out.println("priority poll=" + priority.poll());
        System.out.println("priority drain=" + drainNonNullQueue(priority));
        System.out.println("priority empty=" + priority.isEmpty());

        Deque<String> deque = new ArrayDeque<>();
        Queue<String> sameObject = deque;
        sameObject.offer("first");
        deque.offerLast("second");
        System.out.println("queue peek/deque peekFirst="
                + sameObject.peek() + "/" + deque.peekFirst());
        System.out.println("queue remove=" + sameObject.remove());
        System.out.println("deque pollFirst=" + deque.pollFirst());
        System.out.println("deque empty=" + deque.isEmpty());
    }
}
~~~

Biên dịch và chạy trong thư mục chứa tệp:

~~~shell
javac --release 17 -encoding UTF-8 QueueMethodPairsDemo.java
java QueueMethodPairsDemo
~~~

Dùng JDK 17 trở lên. Tùy chọn `--release 17` kiểm tra mã và API theo Java 17. Tên tệp khớp với lớp `public`.

Kết quả chuẩn:

~~~text
fifo add A=true
fifo offer B=true
fifo=[A, B]
peek=A
element=A
after inspection=[A, B]
poll=A
after poll=[B]
remove=B
after remove=[]
empty poll=null
empty peek=null
empty remove=NoSuchElementException
empty element=NoSuchElementException
bounded offer A=true
bounded add B=true
bounded full offer C=false
bounded after rejected offer=[A, B]
bounded full add=IllegalStateException
bounded after rejected add=[A, B]
bounded poll=A
bounded retry offer C=true
bounded remaining=[B, C]
growing offers=true/true/true
growing size=3
offer null=NullPointerException
add null=NullPointerException
after invalid inserts size=0
nullable peek=null
nullable size after peek=2
nullable poll=null
nullable empty after poll=false
nullable remaining=[tail]
remove middle=true
after value remove=[head, tail]
remove head=head
remove missing=false
after both removals=[tail]
priority size=4
priority peek=2
priority remove=2
priority poll=2
priority drain=[5, 7]
priority empty=true
queue peek/deque peekFirst=first/first
queue remove=first
deque pollFirst=second
deque empty=true
~~~

## 10. Đọc kết quả theo từng cặp

### 10.1. Thành công không làm lộ khác biệt về báo lỗi

`fifo add A=true` và `fifo offer B=true` cho thấy cả hai thêm thành công. Hàng đợi FIFO là `[A, B]`.

`peek=A` và `element=A` đi cùng `after inspection=[A, B]`. Đây là bằng chứng rằng cặp xem đầu không xóa.

`poll=A` để lại B; `remove=B` làm rỗng hàng đợi. Mỗi thao tác trong cặp lấy ra đã loại đúng một phần tử.

### 10.2. Hàng đợi rỗng tách hai kiểu kết quả

`empty poll=null` và `empty peek=null` dùng giá trị đặc biệt. `empty remove=NoSuchElementException` và `empty element=NoSuchElementException` dùng ngoại lệ.

Các khối `try/catch` trong chương trình bắt đúng lỗi đang được minh họa để tiếp tục các ví dụ sau. Chúng không biến mọi ngoại lệ phát sinh ở nơi khác thành kết quả rỗng.

### 10.3. Hàng đợi đầy tách add khỏi offer

Sau hai lần thêm vào sức chứa 2, `bounded full offer C=false` cho biết C chưa được nhận. Chuỗi `[A, B]` không đổi.

`bounded full add=IllegalStateException` cũng không thêm C. Hàng đợi không bị trộn thêm một bản C sau ngoại lệ trong ví dụ này.

Khi `bounded poll=A` tạo chỗ trống, lần thử offer tiếp theo trả true và kết quả là `[B, C]`. C được thêm đúng một lần, ở lần thử thành công sau đó.

### 10.4. Dữ liệu không hợp lệ không trở thành false

`offer null=NullPointerException` và `add null=NullPointerException` xảy ra trên ArrayDeque rỗng, nên không thể giải thích bằng “hết chỗ”.

`after invalid inserts size=0` xác nhận không có thành viên nào được thêm trong hai lời gọi lỗi đó.

## 11. Dung lượng khởi tạo không nhất thiết là sức chứa tối đa

`new ArrayDeque<>(1)` không tạo một hàng đợi chỉ được giữ một phần tử. ArrayDeque dùng mảng có thể tăng dung lượng theo nhu cầu.

Chương trình thêm 1, 2, 3 và in:

~~~text
growing offers=true/true/true
growing size=3
~~~

Tham số khởi tạo ở đây là gợi ý dung lượng ban đầu đủ chứa số phần tử được yêu cầu, không phải giới hạn một thành viên. Vì thế, dùng ArrayDeque để thử “offer trả false khi thêm phần tử thứ hai” là một phép thử sai giả định.

ArrayDeque không đặt giới hạn dung lượng cố định theo hợp đồng sử dụng của nó. Điều đó không có nghĩa tài nguyên máy tính vô hạn hoặc mọi lời gọi đều được bảo đảm thành công trong mọi điều kiện. Đừng diễn giải lỗi tài nguyên như tình trạng đầy có thể được Queue.offer biểu diễn phổ quát bằng false. [Java 17: ArrayDeque](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/ArrayDeque.html).

ArrayBlockingQueue có một sức chứa cố định được chỉ định lúc tạo. Đây là lý do bài dùng hai lớp khác nhau cho hai mục đích kiểm chứng: sự phát triển dung lượng và việc từ chối vì đã đạt giới hạn.

Khi đọc mã thực tế, hãy xác định tham số trong hàm khởi tạo là dung lượng ban đầu hay giới hạn tối đa. Không suy ý nghĩa của cùng một số chỉ từ việc hai lớp đều có chữ “Array”.

## 12. Tránh dùng null làm phần tử của Queue

`poll` và `peek` dùng null để biểu thị không có đầu hàng đợi. Nếu chính dữ liệu đầu vào có thể là null, giá trị trả về không còn đủ để phân biệt hai trường hợp.

Nhiều lớp, trong đó ArrayDeque, PriorityQueue và ArrayBlockingQueue, cấm null. Tuy nhiên, `LinkedList` cho phép null ngay cả khi đối tượng được nhìn qua kiểu Queue.

Chương trình cố ý tạo một hàng đợi như vậy:

~~~text
[null, tail]
~~~

`peek` trả null nhưng `size` vẫn là 2 vì không xóa gì. Sau đó `poll` cũng trả null, nhưng lần này đã lấy thành viên null ra; hàng đợi vẫn còn `tail` và `isEmpty` là false.

Vì vậy, câu “poll trả null thì Queue luôn rỗng” chỉ phù hợp khi hợp đồng phần tử đã loại null. Không được suy ra điều đó cho mọi lớp triển khai mà không kiểm tra.

Tài liệu Queue khuyến cáo không dùng null làm phần tử ngay cả ở lớp cho phép nó. Ví dụ LinkedList của bài là phản ví dụ để hiểu sự mơ hồ, không phải cách biểu diễn công việc được đề xuất. [Java 17: LinkedList](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/LinkedList.html).

Nếu ứng dụng cần một thông điệp có ý nghĩa “không có giá trị” hoặc “kết thúc”, dùng một mô hình thông điệp tường minh phù hợp với dữ liệu, thay vì chiếm dụng null đang được API dùng làm kết quả đặc biệt. Mô hình ấy phải được xử lý như một phần của hợp đồng ứng dụng.

## 13. remove() khác remove(Object)

Tên `remove` có hai dạng quan trọng:

| Lời gọi | Ý nghĩa | Kiểu kết quả |
| --- | --- | --- |
| `queue.remove()` | Lấy ra đầu hàng đợi | Phần tử kiểu E |
| `queue.remove(value)` | Tìm và xóa một phần tử phù hợp giá trị | boolean |

Dạng không đối số là cặp của `poll` trong bài. Dạng có đối số được kế thừa từ `Collection` và không có nghĩa “lấy đầu”.

Với ArrayDeque FIFO chứa `[head, middle, tail]`:

~~~text
remove("middle") → true
hàng đợi        → [head, tail]

remove()        → head
hàng đợi        → [tail]

remove("missing") → false
~~~

Trong trường hợp tìm theo giá trị, không tìm thấy thường được báo bằng false theo hợp đồng; đừng gán lỗi rỗng của `remove()` cho mọi lời gọi có cùng tên. [Java 17: Collection.remove(Object)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html#remove(java.lang.Object)).

Với biến mang kiểu `Queue<Integer>`, `remove(1)` là tìm phần tử có giá trị số 1 qua dạng đối số Object, không phải xóa ở chỉ số 1 như một số cách gọi trên List. Queue không cung cấp thao tác xóa theo chỉ số.

Cũng đừng kỳ vọng hai dạng có cùng chi phí. Ví dụ, xóa ở đầu của ArrayDeque khác với tìm một giá trị ở giữa. Khi đọc hiệu năng, phải xác định đúng chữ ký phương thức, không chỉ nhìn tên remove.

## 14. Cùng poll nhưng đầu của PriorityQueue khác FIFO

Chương trình đưa `7, 2, 5, 2` vào PriorityQueue theo thứ tự tự nhiên của Integer. Nó không in toàn bộ PriorityQueue rồi giả định chuỗi đó là thứ tự lấy ra.

Các kết quả:

~~~text
priority size=4
priority peek=2
priority remove=2
priority poll=2
priority drain=[5, 7]
~~~

Đầu hàng đợi là giá trị ưu tiên nhỏ nhất theo quy tắc hiện tại, không phải số 7 đến trước. Hai lần xuất hiện của số 2 cùng được giữ; đây không phải một Set loại trùng.

`remove()` và `poll()` vẫn thực hiện cùng mục đích lấy ra đầu. Chúng không chọn hai chính sách ưu tiên khác nhau. `peek` vẫn chỉ xem đầu.

Với những phần tử có cùng độ ưu tiên nhưng là các đối tượng khác nhau, không suy thứ tự đến trước từ việc khóa ưu tiên bằng nhau nếu lớp không cam kết như vậy. Nếu yêu cầu cần phân biệt thứ tự ở mức ấy, mô hình và bộ so sánh phải phản ánh yêu cầu.

Bộ duyệt của PriorityQueue không được cam kết đi qua theo thứ tự ưu tiên. Để kiểm chứng trình tự lấy ra trong bài, chương trình dùng các lời gọi lấy đầu thật sự. [Java 17: PriorityQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/PriorityQueue.html).

## 15. Quan hệ với Deque: thêm đuôi, đọc/lấy đầu khi dùng như Queue

`Deque` mở rộng Queue và cho thao tác ở cả hai đầu. Khi dùng các phương thức Queue trên một Deque, chúng tương ứng về thao tác với:

| Queue | Phương thức Deque tương ứng |
| --- | --- |
| `add(e)` | `addLast(e)` |
| `offer(e)` | `offerLast(e)` |
| `remove()` | `removeFirst()` |
| `poll()` | `pollFirst()` |
| `element()` | `getFirst()` |
| `peek()` | `peekFirst()` |

Bảng mô tả hướng và tác dụng. Cần vẫn đọc đúng chữ ký: chẳng hạn `Queue.add` trả boolean, còn `Deque.addLast` có kiểu trả về void.

Chương trình giữ hai biến nhìn vào cùng một ArrayDeque, một biến kiểu Deque và một biến kiểu Queue. Thêm `first` qua offer của Queue rồi thêm `second` qua offerLast của Deque tạo cùng chuỗi thành viên.

`sameObject.peek()` và `deque.peekFirst()` cùng thấy first. Sau khi remove qua biến Queue lấy first, pollFirst qua biến Deque lấy second. Không có hai kho dữ liệu độc lập chỉ vì hai biến có kiểu khác nhau.

Quan hệ này giúp bạn đọc mã khi các tên phương thức có hậu tố First/Last xuất hiện cạnh tên Queue ngắn hơn. Nó không có nghĩa được tự đổi việc thêm vào đầu thành thêm vào đuôi; các phương thức như addFirst phục vụ một hướng thao tác khác. [Java 17: Deque, bảng tương ứng với Queue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Deque.html).

## 16. Các phương thức này không tự chờ dữ liệu hoặc chờ chỗ

Tên `ArrayBlockingQueue` có thể khiến người mới nghĩ mọi lời gọi đều đợi. Cần đọc chính xác phương thức và chữ ký.

Trong chương trình, `offer(e)` trả kết quả theo việc có thể chèn mà không đợi chỗ trống xuất hiện; `poll()` không đợi một phần tử mới đến. Không có tham số thời gian chờ trong những chữ ký này.

`BlockingQueue` bổ sung các thao tác chờ như `put`, `take` và các biến thể có thời hạn. Chúng không nằm trong sáu chữ ký Queue đang học. Sự tồn tại của các phương thức bổ sung không làm `add` hay `element` tự biến thành thao tác chờ. [Java 17: BlockingQueue](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

Cũng không suy tính an toàn khi nhiều luồng cùng dùng chỉ từ tên interface Queue. ArrayDeque trong bài không hỗ trợ tự do dùng chung và sửa từ nhiều luồng. ArrayBlockingQueue có hợp đồng phối hợp riêng, nhưng một chuỗi kiểm tra rồi hành động vẫn cần được đọc từng bước.

Ví dụ, “kiểm tra chưa đầy rồi add” là hai thao tác; tác nhân khác có thể thêm vào giữa. Tương tự, “peek thấy A rồi poll” không phải tự động dành A cho bên vừa peek.

Khi chỉ cần thử thêm, dùng kết quả của chính lời gọi offer để biết thao tác vừa thực hiện có được chấp nhận hay không. Khi cần lấy ra, dùng kết quả của chính poll. Đừng xem một lần kiểm tra trước đó như bảo đảm vĩnh viễn cho trạng thái sau.

## 17. Chọn cặp nào theo hợp đồng của đoạn mã?

Không cần học sáu tên như sáu hành vi rời rạc. Chọn theo hai bước: xác định mục đích, rồi xác định cách biểu diễn tình trạng không thực hiện được.

| Hoàn cảnh | Lựa chọn cần cân nhắc |
| --- | --- |
| Đưa vào hàng đợi có thể đầy và cần báo chưa nhận | `offer` rồi kiểm tra boolean |
| Việc không thêm được vi phạm giả định của đoạn mã | `add` và hợp đồng ngoại lệ rõ |
| Lấy công việc nếu hiện có, hết là tình trạng bình thường | `poll` rồi kiểm tra null khi dữ liệu cấm null |
| Đoạn mã yêu cầu chắc chắn có đầu để lấy | `remove()`, rỗng sẽ báo lỗi |
| Chỉ xem đầu, rỗng là kết quả dự kiến | `peek` |
| Chỉ xem đầu, rỗng vi phạm giả định | `element` |

Không bỏ qua kết quả offer. Không gọi poll nếu chỉ cần xem. Không bắt NoSuchElementException như một cách che lỗi ở mọi bước mà không biết hàng đợi đáng lẽ có dữ liệu hay không.

Với một lượt lấy hết hàng đợi cấm null, hàm trong chương trình:

~~~java
static <E> List<E> drainNonNullQueue(Queue<E> queue) {
    List<E> values = new ArrayList<>();
    E value;
    while ((value = queue.poll()) != null) {
        values.add(value);
    }
    return values;
}
~~~

vừa làm rỗng hàng đợi vừa tạo danh sách kết quả. Nó không phải hàm đọc giữ nguyên dữ liệu và không thích hợp với hàng đợi có phần tử null.

Nếu chỉ cần duyệt để hiển thị, chọn thao tác đọc và xem hợp đồng thứ tự duyệt của lớp cụ thể. Nếu cần giữ mọi dữ liệu nguồn nguyên vẹn, đừng truyền nó vào một hàm lấy hết rồi mới nhận ra chữ drain có nghĩa là rút dữ liệu ra.

## 18. Những lỗi thường gặp

| Nhận định | Cách đọc đúng |
| --- | --- |
| “Add thêm đầu, offer thêm cuối” | Trong cùng lớp Queue, hai phương thức cùng mục đích thêm; khác cách báo không có chỗ |
| “Offer không ném ngoại lệ” | Nó vẫn có thể báo dữ liệu không hợp lệ, như null bị cấm |
| “Không có ngoại lệ nghĩa là offer thành công” | Phải kiểm tra boolean trả về |
| “Offer true nghĩa là công việc đã xử lý xong” | Nó mới xác nhận thao tác thêm được chấp nhận |
| “Poll chỉ xem đầu” | Poll trả phần tử và xóa nó |
| “Peek sẽ chuyển sang phần tử kế tiếp mỗi lần gọi” | Nếu dữ liệu không đổi, nó tiếp tục xem cùng đầu |
| “Remove luôn ném khi không tìm thấy” | Phân biệt remove không đối số với remove(Object) |
| “new ArrayDeque(2) chỉ giữ được hai phần tử” | Tham số là dung lượng khởi tạo, không phải giới hạn cố định |
| “Mọi Queue đều FIFO” | Đọc lớp triển khai; PriorityQueue là ví dụ khác |
| “Poll null luôn chứng minh rỗng” | Cần hợp đồng phần tử cấm null |
| “Có chữ Blocking thì offer(e) tự đợi chỗ” | Phải xem đúng chữ ký; có những phương thức chờ riêng |
| “Peek rồi poll là một hành động” | Đó là hai lời gọi; thay đổi xen vào có thể làm kết quả khác |
| “Queue<Integer>.remove(1) là xóa chỉ số 1” | Qua kiểu Queue, đó là dạng tìm theo giá trị Object |

Để tìm lỗi nhanh, ghi ra trạng thái trước, chữ ký chính xác, giá trị trả về hoặc ngoại lệ và trạng thái sau. Bốn thông tin đó thường đủ để tách lỗi hiểu API khỏi lỗi quy tắc thứ tự.

## 19. Thực hành có lời giải

### Bài 1: đi qua ba mục đích

FIFO ban đầu là `[A, B]`. Gọi peek, poll, element, remove theo thứ tự. Mỗi lần trả gì và tập cuối thế nào?

**Lời giải:** Peek trả A và giữ nguyên. Poll trả A, còn B. Element trả B và giữ B. Remove trả B, hàng đợi rỗng.

### Bài 2: thao tác khi rỗng

Trên ArrayDeque rỗng, poll và peek trả gì? Remove không đối số và element làm gì?

**Lời giải:** Poll và peek trả null. Remove và element ném NoSuchElementException. Không có phần tử nào bị thêm hoặc tạo mới để thay thế.

### Bài 3: giới hạn hai phần tử

ArrayBlockingQueue sức chứa 2 đã có X và Y. Offer Z thất bại rồi add Z được thử. Hai kết quả và nội dung là gì?

**Lời giải:** Offer trả false, add ném IllegalStateException. Hàng đợi vẫn là `[X, Y]`. Không có Z chờ ngầm bên trong.

### Bài 4: thử lại sau khi có chỗ

Tiếp bài trước, poll lấy X ra rồi offer Z lại. Điều gì xảy ra?

**Lời giải:** Còn Y và một chỗ trống. Offer Z mới trả true, hàng đợi thành `[Y, Z]`. Lần offer thành công là một lời gọi sau, không phải kết quả trì hoãn của lời gọi bị từ chối.

### Bài 5: offer null

Bạn đổi `add(null)` sang `offer(null)` trên ArrayDeque để tránh ngoại lệ. Cách đó có đúng không?

**Lời giải:** Không. ArrayDeque cấm null nên cả hai đều ném NullPointerException. Sự khác nhau về đầy không xóa bỏ hợp đồng đầu vào.

### Bài 6: một vòng peek

Vòng lặp kiểm tra peek khác null rồi in peek nhưng không xóa có tự xử lý lần lượt các phần tử không?

**Lời giải:** Không. Nếu hàng đợi không đổi, nó cứ xem cùng đầu. Dùng poll để lấy từng phần tử ra, hoặc bộ duyệt nếu chỉ đọc mà giữ dữ liệu.

### Bài 7: remove có đối số

FIFO là `[one, two, three]`. Remove("two") trả gì? Sau đó remove() trả gì?

**Lời giải:** Remove có đối số trả true và xóa two, còn `[one, three]`. Remove không đối số trả phần tử one và xóa đầu, còn three.

### Bài 8: dung lượng khởi tạo

Bạn tạo `new ArrayDeque<Integer>(1)` rồi offer ba số hợp lệ. Có thể kết luận offer thứ hai sẽ false không?

**Lời giải:** Không. ArrayDeque có thể tăng dung lượng và không coi 1 là sức chứa tối đa. Chương trình đã kiểm chứng ba lần offer đều true trong điều kiện bình thường.

### Bài 9: thứ tự ưu tiên

Đưa `9, 4, 6` vào PriorityQueue tự nhiên. Peek, remove và poll lần lượt trả gì nếu không có thao tác xen vào?

**Lời giải:** Peek trả 4 và giữ nguyên. Remove trả 4, còn 6 và 9. Poll tiếp theo trả 6. Không phải 9 đến trước sẽ được lấy trước.

### Bài 10: null trong LinkedList

Queue dùng LinkedList chứa `[null, tail]`. Poll trả null. Có thể dừng xử lý và khẳng định đã hết dữ liệu không?

**Lời giải:** Không. Lời gọi vừa lấy thành viên null ra; tail vẫn còn. Đây là lý do cần tránh null làm dữ liệu Queue và xác định tiền điều kiện cho các vòng poll đến null.

### Bài 11: liên hệ Deque

Trên một Deque dùng như Queue, offer tương ứng đầu hay cuối? Remove không đối số tương ứng phía nào?

**Lời giải:** Offer thêm ở cuối, tương ứng offerLast. Remove không đối số lấy ở đầu, tương ứng removeFirst. Peek nhìn đầu qua peekFirst.

### Bài 12: chữ Blocking

Biến Queue trỏ tới ArrayBlockingQueue đang đầy. Gọi offer(e) không có thời hạn thì lời gọi có tự chờ đến khi có chỗ không?

**Lời giải:** Không đợi chỗ trống xuất hiện; nó báo không thêm được bằng false. Các thao tác chờ hoặc có thời hạn thuộc những chữ ký bổ sung của BlockingQueue và phải được chọn rõ.

## 20. Cách nhớ để đọc đúng mã thật

Đầu tiên, phân loại thao tác là **thêm**, **lấy ra** hay **chỉ xem**. Sau đó đọc cách báo không thực hiện được: ngoại lệ hoặc false/null. Cuối cùng, kiểm tra lớp triển khai để biết thứ tự, giới hạn dung lượng, chính sách null và cách dùng khi có nhiều luồng.

Với mỗi lời gọi, giá trị trả về nói về chính thao tác đó: offer true là đã thêm; poll khác null là đã lấy ra khi dữ liệu cấm null; peek khác null chỉ là đã nhìn thấy đầu tại thời điểm gọi. Giữ các ý nghĩa này tách bạch sẽ tránh phần lớn lỗi sử dụng ba cặp phương thức.
