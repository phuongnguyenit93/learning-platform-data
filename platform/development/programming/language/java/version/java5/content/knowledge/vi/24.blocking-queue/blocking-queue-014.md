# Lựa chọn hàng đợi theo thứ tự, dung lượng và chiến lược chờ

## 1. Chọn theo hợp đồng xử lý trước khi chọn tên lớp

Hàng đợi nằm giữa bên tạo dữ liệu (producer) và bên xử lý (consumer). Nó quyết định công việc nào được lấy tiếp theo, cho phép tích lũy bao nhiêu việc, và bên gọi phải làm gì khi chưa thể thêm hoặc lấy. Ba quyết định này tác động trực tiếp tới tính đúng đắn, độ trễ và khả năng chịu quá tải.

Không có một lớp `BlockingQueue` tốt nhất cho mọi bài toán. Cũng không thể chỉ chọn một lớp có chữ `Blocking` rồi coi như hệ thống đã có giới hạn bộ nhớ và cơ chế dừng. Cần chọn cả loại hàng đợi lẫn cách gọi API của nó.

Bài này dùng các API vẫn áp dụng trong Java hiện đại và ví dụ biên dịch được bằng Java 17 trở lên.

## 2. Ba câu hỏi nền tảng

| Trục quyết định | Câu hỏi cần trả lời | Ví dụ yêu cầu |
| --- | --- | --- |
| Thứ tự và điều kiện được lấy | Việc đến trước, việc ưu tiên hơn, việc đến hạn hay một lần giao trực tiếp sẽ được nhận? | Giữ FIFO hoặc xử lý mức khẩn cấp trước |
| Dung lượng | Có cho phép tích lũy không, tối đa bao nhiêu phần tử, khi đầy sẽ làm gì? | Chỉ giữ tối đa 500 việc chờ |
| Chiến lược chờ | Thử ngay, chờ có giới hạn hay chờ cho đến khi có thể tiếp tục? | Consumer chờ việc; producer chỉ được chờ tối đa 100 ms |

Thứ tự lấy không đồng nghĩa thứ tự hoàn tất. Dù hàng đợi FIFO, hai consumer có thể lấy A rồi B nhưng B xử lý xong trước vì tốn ít thời gian hơn. Nếu nghiệp vụ bắt buộc hoàn tất theo thứ tự, cần thiết kế việc xử lý và tổng hợp kết quả tương ứng, không chỉ thay loại hàng đợi.

## 3. So sánh những lựa chọn chính

| Loại | Thứ tự/điều kiện lấy | Dung lượng | Khi nên cân nhắc | Điểm dễ hiểu sai |
| --- | --- | --- | --- | --- |
| `ArrayBlockingQueue` | FIFO | Cố định, phải chỉ định khi tạo | Cần vùng đệm hữu hạn với giới hạn phần tử rõ ràng | Dung lượng không tự tăng |
| `LinkedBlockingQueue` | FIFO | Có thể chỉ định; mặc định `Integer.MAX_VALUE` | Cần FIFO với cấu trúc nút liên kết và giới hạn được lựa chọn rõ | Constructor không đối số không tạo một giới hạn nhỏ an toàn |
| `PriorityBlockingQueue` | Theo thứ tự tự nhiên hoặc `Comparator` | Không giới hạn logic theo số phần tử | Việc cần được lấy theo độ ưu tiên | Đối số constructor là dung lượng ban đầu, không phải mức tối đa |
| `DelayQueue` | Chỉ lấy phần tử đã đến hạn; đầu hàng đợi theo thời điểm hết trì hoãn | Không giới hạn logic theo số phần tử | Dữ liệu chỉ được nhận sau một khoảng trì hoãn | `size()>0` vẫn có thể chưa lấy được phần tử nào |
| `SynchronousQueue` | Ghép một lần giao với một lần nhận | Không có vùng đệm, kể cả một chỗ | Cần chuyển giao trực tiếp giữa hai bên | `size()==0` không có nghĩa một lần giao không thể thành công |

“Không giới hạn logic” không có nghĩa RAM vô hạn. Khi tốc độ vào vượt tốc độ xử lý kéo dài, số phần tử hoặc tài nguyên liên quan vẫn có thể tăng cho đến khi ứng dụng mất khả năng hoạt động.

## 4. Chọn theo thứ tự và thời điểm dữ liệu sẵn sàng

### FIFO: ArrayBlockingQueue hoặc LinkedBlockingQueue

FIFO nghĩa là phần tử xếp trước được lấy trước. Đây thường là lựa chọn phù hợp khi công việc không có quy tắc ưu tiên riêng và cần giữ thứ tự tiếp nhận ở tầng hàng đợi.

`ArrayBlockingQueue` dùng mảng với số chỗ cố định. `LinkedBlockingQueue` dùng các nút liên kết và có constructor nhận giới hạn. Không kết luận một lớp luôn nhanh hơn lớp kia trong mọi tải; hãy đo với số producer/consumer, kích thước công việc, mức tranh chấp và cấu hình JVM thực tế.

Chính sách `fair=true` của `ArrayBlockingQueue` liên quan tới thứ tự phục vụ các luồng chờ. Nó khác FIFO của dữ liệu: hàng đợi vẫn FIFO ngay cả khi dùng chính sách không công bằng mặc định. Công bằng có thể đổi thông lượng lấy việc giảm chênh lệch chờ giữa các luồng. Xem hợp đồng của [ArrayBlockingQueue — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html).

### Ưu tiên: PriorityBlockingQueue

`PriorityBlockingQueue` trả phần tử nhỏ nhất theo thứ tự so sánh đã cấu hình. “Nhỏ nhất” mang nghĩa của comparator, không tự có nghĩa là ít khẩn cấp nhất hay khẩn cấp nhất. Nếu quy ước số 1 khẩn cấp hơn số 2, comparator tăng dần theo số có thể phù hợp; nếu hệ thống dùng quy ước ngược thì cần comparator khác.

Các phần tử có cùng độ ưu tiên không tự được bảo đảm FIFO. Nếu cần kết quả xác định giữa chúng, thêm khóa phụ như số thứ tự ổn định. Không sửa trường dùng để so sánh của một đối tượng khi nó vẫn nằm trong hàng đợi rồi mong hàng đợi tự sắp xếp lại.

Thứ tự duyệt iterator hoặc in toàn bộ collection cũng không phải bằng chứng thứ tự lấy theo ưu tiên. Hãy kiểm tra bằng các thao tác lấy. Việc ưu tiên không tự ngắt một công việc ít ưu tiên đã được consumer lấy ra và đang chạy; cũng cần cân nhắc khả năng việc ít ưu tiên chờ lâu khi việc khẩn liên tục tới. Xem [PriorityBlockingQueue — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/PriorityBlockingQueue.html).

### Đến hạn mới được lấy: DelayQueue

`DelayQueue` dành cho phần tử thực hiện `Delayed`. Phần tử có thời gian còn lại nhỏ hơn hoặc bằng 0 mới đủ điều kiện được lấy bởi `poll`, `take` hoặc các cách lấy đầu tương ứng. `take` có thể phải chờ thời gian trì hoãn kết thúc dù trong hàng đợi đã có phần tử.

Vì vậy, nó không chỉ là “hàng đợi ưu tiên có thêm `sleep`”. Có sự khác biệt giữa đứng đầu và đã đủ điều kiện nhận. `size()` đếm cả phần tử chưa đến hạn, còn `peek()` có thể thấy đầu chưa đến hạn; `poll()` lúc đó vẫn có thể trả `null`.

Chọn nó khi ứng dụng cần quản lý dữ liệu đến hạn và tự có consumer xử lý, chẳng hạn một lần thử lại chỉ được phép bắt đầu sau một mốc. Với nhu cầu lập lịch tác vụ định kỳ hoặc quản lý vòng đời bộ thực thi, nên đánh giá công cụ lập lịch tương ứng thay vì tự xây tất cả chỉ bằng một hàng đợi. Hợp đồng lấy phần tử đến hạn nằm trong [DelayQueue — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/DelayQueue.html).

### Chuyển giao trực tiếp: SynchronousQueue

`SynchronousQueue` không tích lũy công việc trong vùng đệm. `put(e)` chờ một bên nhận; `take()` chờ một bên giao; `offer(e)` chỉ thành công khi có thể giao ngay cho bên nhận đang chờ. Chọn nó khi ứng dụng muốn một lần gửi phải gặp khả năng nhận, thay vì cho phép gửi vào một danh sách chờ.

Không dùng nó như hàng đợi một chỗ. Với một chỗ đệm, producer có thể để lại dữ liệu trước khi consumer đến; với chuyển giao trực tiếp, không có bước để lại ấy. `size()` và `remainingCapacity()` đều bằng 0 không ngăn một cặp thao tác giao–nhận thành công; xem [SynchronousQueue — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/SynchronousQueue.html).

## 5. Chọn dung lượng như một phần của chính sách quá tải

### Giới hạn rõ ràng khi cần vùng đệm hữu hạn

```java
// Các khai báo minh họa; cả hai đều giữ tối đa 500 phần tử đang xếp hàng.
BlockingQueue<Job> arrayBuffer = new ArrayBlockingQueue<>(500);
BlockingQueue<Job> linkedBuffer = new LinkedBlockingQueue<>(500);
```

Cả hai giới hạn đều áp dụng cho số phần tử còn ở trong hàng đợi. Chúng không tính công việc consumer đã lấy ra đang xử lý, dữ liệu producer còn đang giữ vì chưa thêm được, hoặc dữ liệu tồn ở tầng khác. Giới hạn số phần tử cũng không phải giới hạn byte vì mỗi phần tử có thể tham chiếu lượng dữ liệu khác nhau.

Dung lượng lớn hơn có thể hấp thụ một đợt tăng tải tạm thời lớn hơn, nhưng đồng thời giữ nhiều dữ liệu hơn và có thể tăng thời gian xếp hàng. Nếu tốc độ nhận dài hạn luôn vượt tốc độ xử lý dài hạn, tăng dung lượng chỉ dời thời điểm đầy.

`new LinkedBlockingQueue<>()` mặc định có giới hạn `Integer.MAX_VALUE`, không phải một vùng đệm nhỏ tự điều chỉnh. Dù không cấp sẵn từng ấy nút ngay lúc tạo, nó vẫn cho phép tích lũy một lượng dữ liệu rất lớn nếu không có giới hạn khác. Khi cần dung lượng hữu hạn có ý nghĩa với ứng dụng, truyền rõ con số vào constructor; xem [LinkedBlockingQueue — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html).

### Đừng nhầm initialCapacity với dung lượng tối đa

`new PriorityBlockingQueue<>(100)` chỉ đặt dung lượng lưu ban đầu, không giới hạn hàng đợi ở 100 phần tử. `PriorityBlockingQueue` và `DelayQueue` không tự tạo backpressure bằng cách chờ chỗ trống ở phía thêm. Nếu vừa cần ưu tiên/đến hạn vừa cần giới hạn lượng công việc, phải có cơ chế tiếp nhận hữu hạn riêng và xác định rõ khi nào trả lại quyền tiếp nhận.

Không thay tạm bằng FIFO hữu hạn rồi coi như đã đáp ứng yêu cầu ưu tiên. Ngược lại, cũng không chọn ưu tiên không giới hạn rồi bỏ qua yêu cầu giới hạn tài nguyên.

## 6. Chọn chiến lược chờ bằng phương thức gọi

Với hàng đợi FIFO hữu hạn, các chính sách điển hình là:

| Yêu cầu của bên gọi | Phía thêm | Phía lấy | Kết quả cần xử lý |
| --- | --- | --- | --- |
| Không thể thực hiện là lỗi của giả định chương trình | `add(e)` | `remove()` | Ngoại lệ khi đầy/rỗng |
| Thử ngay, chưa được thì làm việc khác | `offer(e)` | `poll()` | `false` hoặc `null` |
| Chờ cho đến khi có thể tiếp tục | `put(e)` | `take()` | Thành công hoặc bị ngắt |
| Chỉ dành một khoảng thời gian để chờ | `offer(e, timeout, unit)` | `poll(timeout, unit)` | Thành công, hết thời gian, hoặc bị ngắt |

Loại hàng đợi quyết định điều kiện có thể thực hiện: chỗ trống đối với FIFO hữu hạn, bên đối ứng đối với `SynchronousQueue`, và thời điểm đến hạn đối với cách lấy của `DelayQueue`. Không suy từ chữ `put` rằng mọi lớp đều chờ khi thêm: hàng đợi không giới hạn logic không chờ một chỗ trống theo dung lượng.

`offer` thất bại không tự thử lại, lưu bền vững hay báo lỗi tới người dùng. `poll` trả `null` không chứng minh luồng dữ liệu đã kết thúc. Ứng dụng cần viết rõ nhánh xử lý các kết quả này.

Timed `offer`/`poll` giới hạn lần chờ thêm/lấy, không giới hạn thời gian xử lý sau khi lấy. Các thao tác chờ có thể ném `InterruptedException`; cần chuyển yêu cầu ngắt lên hoặc kết thúc tác vụ theo chính sách hủy, không nuốt ngoại lệ rồi lặp lại vô hạn.

## 7. Ví dụ chạy đầy đủ: những lựa chọn có hợp đồng khác nhau

Lưu vào `QueueSelectionDemo.java`. Chương trình không tạo luồng phụ, để kiểm tra các hợp đồng về thứ tự và dung lượng mà không phụ thuộc lịch chạy.

```java
import java.util.Comparator;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.PriorityBlockingQueue;
import java.util.concurrent.SynchronousQueue;

public class QueueSelectionDemo {
    record Job(int priority, long sequence, String name) {}

    private static void check(boolean condition) {
        if (!condition) {
            throw new AssertionError("Unexpected queue result");
        }
    }

    public static void main(String[] args) {
        ArrayBlockingQueue<String> fifo = new ArrayBlockingQueue<>(2);
        check(fifo.offer("B"));
        check(fifo.offer("A"));
        check(!fifo.offer("C"));
        System.out.println("bounded third offer: false");
        System.out.println("FIFO removal: " + fifo.poll() + ", " + fifo.poll());

        LinkedBlockingQueue<String> defaultLinked = new LinkedBlockingQueue<>();
        System.out.println("default linked remaining: "
                + defaultLinked.remainingCapacity());

        Comparator<Job> order = Comparator.comparingInt(Job::priority)
                .thenComparingLong(Job::sequence);
        PriorityBlockingQueue<Job> priority =
                new PriorityBlockingQueue<>(2, order);

        priority.add(new Job(2, 0, "A"));
        priority.add(new Job(1, 1, "B"));
        priority.add(new Job(1, 2, "C"));
        check(priority.size() == 3);
        System.out.println("priority size after three inserts: " + priority.size());

        String names = priority.remove().name() + ", "
                + priority.remove().name() + ", " + priority.remove().name();
        check("B, C, A".equals(names));
        System.out.println("priority removal: " + names);

        SynchronousQueue<String> direct = new SynchronousQueue<>();
        check(!direct.offer("X"));
        System.out.println("direct offer without receiver: false");
        System.out.println("direct size: " + direct.size());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 QueueSelectionDemo.java
java QueueSelectionDemo
```

Stdout:

```text
bounded third offer: false
FIFO removal: B, A
default linked remaining: 2147483647
priority size after three inserts: 3
priority removal: B, C, A
direct offer without receiver: false
direct size: 0
```

`fifo` chứa B trước A nên lấy B trước A, không sắp xếp theo chữ cái. Nó đã đủ hai chỗ khi thêm C nên lần `offer` thứ ba thất bại.

Hàng đợi liên kết mặc định báo sức chứa còn lại là `Integer.MAX_VALUE` lúc rỗng. Đây là giới hạn số phần tử của constructor, không phải lượng RAM khả dụng đã được đo.

Ở hàng đợi ưu tiên, số 2 trong constructor không ngăn chèn phần tử thứ ba. Comparator cho mức 1 đi trước mức 2; B và C cùng mức 1 được phân định bằng `sequence`, nên kết quả lấy là B, C, A. Thứ tự ổn định đến từ quy tắc so sánh của chương trình.

`direct` không có consumer nào đang nhận nên không thể giao X; nó không giữ X lại cho tương lai. Chương trình không dùng `put` ở đây vì sẽ không có luồng khác để ghép nhận.

## 8. Ghép yêu cầu thực tế với lựa chọn

| Bài toán | Hướng lựa chọn | Điều cần quyết định thêm |
| --- | --- | --- |
| Xử lý nền FIFO, chỉ cho phép một lượng việc chờ hữu hạn | `ArrayBlockingQueue(capacity)` hoặc `LinkedBlockingQueue(capacity)` | Dung lượng, từ chối hay chờ khi đầy, cơ chế dừng |
| Việc khẩn phải được lấy trước việc thường đang chờ | `PriorityBlockingQueue` với comparator rõ ràng | Khóa phụ khi bằng ưu tiên và giới hạn tiếp nhận ở ngoài |
| Việc chỉ được lấy sau một mốc trì hoãn | `DelayQueue` | Cách biểu diễn thời gian, giới hạn tổng việc và vòng đời consumer |
| Giao trực tiếp khi bên kia có thể nhận | `SynchronousQueue` | Chờ hay thử ngay, thời hạn ghép và khả năng hủy |
| Cần một luồng chuyên đợi dữ liệu thay vì tự quay liên tục | Loại phù hợp kết hợp `take` hoặc timed `poll` | Đừng dùng vòng `poll` rỗng để giả lập chờ |

Không dùng `remainingCapacity()` để đặt trước chỗ: producer khác có thể thay đổi hàng đợi trước lần thêm. Không dùng `isEmpty()` rồi `remove()` như một thao tác lấy nguyên tử: consumer khác có thể lấy mất phần tử giữa hai lời gọi. Quyết định dựa vào kết quả của chính thao tác thêm/lấy.

## 9. Kiểm chứng lựa chọn bằng hành vi của hệ thống

Sau khi đã chọn đúng hợp đồng, hãy đo thời gian công việc nằm chờ, số lần bị từ chối, thời gian producer chờ, số công việc đang xử lý và bộ nhớ thực tế. Độ sâu hàng đợi chỉ là một tín hiệu; với `SynchronousQueue`, nó luôn bằng 0 nên không phản ánh số producer đang chờ giao.

Nếu consumer có thể chết do lỗi, cần báo lỗi và giải phóng hoặc hủy các producer đang chờ. Nếu mọi luồng trong cùng bộ thực thi đều chờ thêm trong khi consumer còn đợi được cấp luồng, hàng đợi không tự sửa vòng phụ thuộc ấy.

Cuối cùng, mọi `BlockingQueue` trong phạm vi này đều cấm phần tử `null` và không cung cấp giao thức đóng luồng dữ liệu thống nhất. Hãy thiết kế riêng việc ngừng nhận việc mới, thông báo kết thúc/hủy, đợi xử lý hoàn tất và quản lý công việc thất bại. Với hàng đợi ưu tiên hoặc trì hoãn, một dấu kết thúc đơn giản cũng phải tuân theo quy tắc lấy tương ứng; không mặc định nó sẽ đi sau mọi việc đã gửi.

## 10. Tự kiểm tra

1. Cần FIFO và tối đa 200 việc chờ: có thể bắt đầu bằng lớp nào? `ArrayBlockingQueue<>(200)` hoặc `LinkedBlockingQueue<>(200)`, rồi chọn chính sách lúc đầy.
2. `PriorityBlockingQueue<>(200)` có giới hạn 200 việc không? Không; đó là dung lượng ban đầu.
3. `DelayQueue.size()==1` nhưng `poll()==null` có nhất thiết là lỗi không? Không; phần tử có thể chưa đến hạn.
4. Chọn `SynchronousQueue` có làm producer luôn trả về ngay không? Không; `put` có thể chờ bên nhận.
5. Muốn chỉ chờ tối đa một khoảng để lấy việc thì chọn gì? `poll(timeout, unit)`, rồi xử lý cả `null` và ngắt luồng.
6. FIFO có bảo đảm hai consumer hoàn tất theo thứ tự lấy không? Không; thời gian xử lý của chúng có thể khác nhau.
