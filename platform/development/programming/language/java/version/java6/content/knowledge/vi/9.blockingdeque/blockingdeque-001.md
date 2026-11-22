# BlockingDeque và nhu cầu phối hợp producer–consumer

## 1. Hai luồng có tốc độ khác nhau cần một điểm bàn giao

Trong mô hình producer–consumer:

- **Bên tạo dữ liệu (producer)** tạo công việc hoặc thông điệp.
- **Bên xử lý (consumer)** lấy dữ liệu và thực hiện công việc.
- Một vùng đệm ở giữa giúp hai bên không phải chạy đúng cùng nhịp.

Hai tình huống thường xuất hiện:

1. Consumer đến trước khi có dữ liệu: nó nên chờ thay vì liên tục hỏi “đã có chưa?”.
2. Producer tạo nhanh hơn tốc độ xử lý: khi vùng đệm đầy, cần một chính sách chờ, từ chối hoặc giới hạn thời gian chờ.

`BlockingDeque<E>` là hàng đợi hai đầu có các thao tác hỗ trợ chờ. Nó kết hợp khả năng thêm/lấy ở cả hai đầu của `Deque` với cơ chế phối hợp của `BlockingQueue`.

“Blocking” nghĩa là **luồng gọi có thể phải chờ**, không có nghĩa mọi phương thức của đối tượng đều chờ. Phải chọn đúng nhóm phương thức theo nhu cầu. Hợp đồng hiện hành được mô tả trong [BlockingDeque API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingDeque.html).

Các ví dụ trong bài dùng Java 17 trở lên và `LinkedBlockingDeque` làm cách cài đặt cụ thể.

## 2. Deque khác Queue ở đâu trong bài toán này?

Một queue thường diễn đạt thêm ở cuối, lấy ở đầu. Deque cho phép thao tác ở cả hai phía:

```text
First / đầu                               Last / cuối
    [công việc A] [công việc B] [công việc C]
```

| Quy tắc | Thêm | Lấy | Hành vi |
| --- | --- | --- | --- |
| FIFO thông thường | Cuối | Đầu | Công việc được thêm trước được lấy trước |
| LIFO tại đầu | Đầu | Đầu | Công việc vừa thêm được lấy trước |
| Đưa công việc lên trước | Đầu | Đầu cho consumer | Phần tử được đưa đầu có thể vượt các phần tử đang chờ |

Với một producer thêm bằng `putLast` và một consumer lấy bằng `takeFirst`, ta có FIFO rõ ràng.

Không đổi đầu thêm/lấy tùy ý rồi vẫn hứa giữ FIFO toàn cục. Nếu liên tục đưa công việc mới lên đầu, công việc thường ở phía sau có thể chờ rất lâu. Deque tự nó không phải bộ lập lịch ưu tiên có mọi quy tắc công bằng.

Nếu nhu cầu chỉ là FIFO producer–consumer, một `BlockingQueue` phù hợp có thể đủ. Chọn BlockingDeque khi hai đầu thực sự giúp mô tả cách xử lý.

## 3. Bốn nhóm phương thức, không phải một kiểu chờ duy nhất

Với thao tác trên đầu First:

| Khi chưa làm được ngay | Thêm đầu | Lấy đầu |
| --- | --- | --- |
| Báo lỗi bằng ngoại lệ | `addFirst(e)` | `removeFirst()` |
| Trả trạng thái đặc biệt ngay | `offerFirst(e)` trả false nếu đầy | `pollFirst()` trả null nếu rỗng |
| Chờ cho đến khi làm được hoặc bị ngắt | `putFirst(e)` | `takeFirst()` |
| Chờ có giới hạn | `offerFirst(e, timeout, unit)` | `pollFirst(timeout, unit)` |

Đầu Last có nhóm tương ứng: addLast/offerLast/putLast và removeLast/pollLast/takeLast.

### 3.1. put và take dùng cho điều kiện chờ tự nhiên

- `putLast(e)`: nếu đầy thì chờ có chỗ để thêm.
- `takeFirst()`: nếu rỗng thì chờ có phần tử để lấy.
- Cả hai có thể ném `InterruptedException` khi luồng bị ngắt.

Ứng dụng không cần tự viết vòng lặp hỏi rỗng/đầy kèm sleep hoặc tự ghép wait/notify để làm việc này.

### 3.2. offer và poll có timeout dùng cho giới hạn chờ

- `offerLast(e, time, unit)`: trả true nếu thêm được, false nếu chưa thêm được trong khoảng chờ cho phép.
- `pollFirst(time, unit)`: trả phần tử hoặc null khi hết thời gian chờ mà chưa lấy được.

Bên gọi phải xử lý kết quả thất bại. Offer trả false không có nghĩa dữ liệu đã được lưu để tự gửi lại sau.

Timeout là giới hạn của chính sách chờ trong lời gọi, không phải lời hứa toàn bộ luồng sẽ hoàn thành tác vụ đúng một mốc thời gian thực tuyệt đối bất chấp lịch chạy hệ điều hành.

### 3.3. Tên ngắn kế thừa có quy ước đầu/cuối

Các phương thức kế thừa từ BlockingQueue tương ứng với FIFO:

```text
put(e)             tương ứng putLast(e)
offer(e)           tương ứng offerLast(e)
take()             tương ứng takeFirst()
poll()             tương ứng pollFirst()
peek()             tương ứng peekFirst()
```

Trong bài có hai đầu, viết rõ First/Last thường giúp người đọc tránh nhầm quy tắc.

Một lỗi khác: `push(e)` là thao tác ngăn xếp thêm ở đầu nhưng **không phải putFirst**. Trên deque có giới hạn, push có thể ném `IllegalStateException` khi đầy; nó không tự chờ có chỗ chỉ vì đối tượng là BlockingDeque.

## 4. Vùng đệm có giới hạn và phản hồi khi quá tải

### 4.1. Chọn dung lượng rõ ràng

```java
// Đoạn minh họa.
BlockingDeque<Message> work = new LinkedBlockingDeque<>(2);
```

Dung lượng 2 nghĩa là tối đa hai phần tử đang chờ trong deque. Constructor không chỉ gợi ý kích thước ban đầu; đó là giới hạn dung lượng.

Nếu dùng `new LinkedBlockingDeque<>()`, giới hạn mặc định là `Integer.MAX_VALUE`. Không xem đây là bộ đệm nhỏ tự bảo vệ ứng dụng khỏi mọi tình trạng tăng hàng chờ. LinkedBlockingDeque tạo các nút khi thêm dữ liệu; giới hạn nên phản ánh tài nguyên và chính sách của ứng dụng. Xem [LinkedBlockingDeque API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/LinkedBlockingDeque.html).

### 4.2. Chờ khi đầy tạo sức ép ngược

Với putLast, producer không thể tiếp tục xếp thêm vô hạn khi vùng đệm đã đầy. Nó chỉ tiếp tục sau khi consumer giải phóng chỗ, hoặc khi việc chờ bị ngắt.

Cơ chế này tạo **sức ép ngược (backpressure)** tại điểm bàn giao. Nó không tự giới hạn mọi tài nguyên của hệ thống:

- Công việc đã được consumer lấy ra để xử lý không còn nằm trong số phần tử đang chờ.
- Producer có thể đã tạo hoặc giữ dữ liệu ở nơi khác trước khi gọi put.
- Dung lượng đếm số phần tử, không trực tiếp đếm tổng số byte.

Nếu cần giới hạn tổng công việc đang xử lý cộng đang chờ, phải thiết kế thêm quy tắc tài nguyên phù hợp.

### 4.3. Không tự kiểm tra rồi thêm

Không dùng:

```java
// Mẫu minh họa không bảo đảm dành được chỗ.
if (work.remainingCapacity() > 0) {
    work.addLast(message);
}
```

Một producer khác có thể lấy hết chỗ giữa hai lời gọi. Dùng ngay put hoặc offer phù hợp và xử lý kết quả; thao tác thêm phải là nơi quyết định có thành công hay không.

Tương tự, `isEmpty()` rồi remove không thay thế take/poll khi nhiều consumer cùng lấy.

## 5. Quy tắc truyền dữ liệu và vòng đời consumer

### 5.1. Không dùng null làm thông điệp

BlockingDeque cấm phần tử null. Null được dùng làm kết quả không có dữ liệu của poll/peek, nên không thể đồng thời là một công việc hợp lệ trong deque.

Trong ví dụ, thông điệp là một record bất biến:

```java
// Định nghĩa minh họa.
record Message(String text, boolean stop) { }
```

Cờ stop phân biệt thông điệp kết thúc với công việc thật. Chuỗi rỗng không tự mang nghĩa kết thúc; đó là quy tắc được thể hiện bằng một trường riêng.

### 5.2. Rỗng tạm thời không có nghĩa đã kết thúc

Consumer gọi takeFirst khi rỗng sẽ chờ vì deque không biết producer đã kết thúc hay chỉ đang tạo chậm.

BlockingDeque không có một thao tác close chung để công bố “không còn dữ liệu nữa”. Một chiến lược là gửi thông điệp kết thúc, thường gọi là poison pill. Đây là giao thức của ứng dụng, không phải một phần tử đặc biệt do deque tự hiểu. Hợp đồng về đóng/kết thúc được giải thích trong [BlockingQueue API](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingQueue.html).

Trong chương trình, producer gửi bốn job bằng putLast rồi một thông điệp stop cũng ở cuối. Một consumer lấy FIFO nên nhận đủ bốn job trước stop.

Với nhiều producer, chỉ gửi tín hiệu kết thúc sau khi chắc chắn mọi producer liên quan đã hoàn tất gửi công việc. Với nhiều consumer, cần một giao thức đủ đánh thức và kết thúc tất cả, chẳng hạn một stop cho mỗi consumer theo mô hình phù hợp. Một stop bị một consumer lấy không tự phát cho các consumer còn lại.

Nếu dữ liệu còn có thể được thêm ở đầu sau khi stop đã được xếp, phải xét lại thứ tự và quy tắc dừng; không áp dụng máy móc lập luận FIFO.

### 5.3. Ngắt luồng là một đường kết thúc khác

put/take và các biến thể chờ có thể bị ngắt. Nếu dùng Runnable và không truyền tiếp ngoại lệ được, mẫu thường là xử lý yêu cầu dừng, khôi phục cờ ngắt rồi thoát:

```java
// Đoạn minh họa trong hàm của một tác vụ.
try {
    Message message = work.takeFirst();
    process(message);
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
```

Đoạn minh họa giả định đã có hàm process và biến work. Điều quan trọng là không nuốt ngoại lệ rồi tiếp tục vòng lặp vô hạn như chưa có yêu cầu dừng.

Chương trình hoàn chỉnh dùng Callable, để InterruptedException truyền về Future; main thu các tác vụ theo thứ tự hoàn tất bằng CompletionService, đọc lỗi qua get và dọn executor trong finally. Gửi stop là đường kết thúc bình thường, còn interrupt là một tín hiệu hủy hoặc xử lý sự cố khác.

## 6. Chương trình hoàn chỉnh

Chương trình có ba phần chính:

1. Nạp đầy deque dung lượng 1, cho producer thử put thêm, rồi giải phóng chỗ.
2. Cho một producer và một consumer bàn giao bốn job qua deque dung lượng 2.
3. Minh họa thêm đầu và lời gọi có timeout.

Phần đầu dùng CountDownLatch để biết tác vụ producer đã đến đoạn chuẩn bị put. Khi deque vẫn đầy và chưa có bên lấy, lời gọi put không thể hoàn tất; không cần sleep để đoán thời gian luồng bị chặn.

Lưu thành **BlockingDequeDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.BlockingDeque;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutorCompletionService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingDeque;
import java.util.concurrent.TimeUnit;

public class BlockingDequeDemo {
    record Message(String text, boolean stop) {
        Message {
            Objects.requireNonNull(text);
        }
    }

    public static void main(String[] args) throws Exception {
        ExecutorService pool = Executors.newFixedThreadPool(2);
        try {
            BlockingDeque<String> probe = new LinkedBlockingDeque<>(1);
            probe.addLast("A");
            CountDownLatch attemptingPut = new CountDownLatch(1);
            Future<Void> waitingProducer = pool.submit(() -> {
                attemptingPut.countDown();
                probe.putLast("B");
                return null;
            });
            attemptingPut.await();
            System.out.println("Completed while full: " +
                    waitingProducer.isDone());
            System.out.println("Removed to free space: " + probe.takeFirst());
            waitingProducer.get();
            System.out.println("Next after put completes: " + probe.takeFirst());

            BlockingDeque<Message> work = new LinkedBlockingDeque<>(2);
            ExecutorCompletionService<List<String>> pipeline =
                    new ExecutorCompletionService<>(pool);
            Future<List<String>> consumer = pipeline.submit(() -> {
                List<String> processed = new ArrayList<>();
                while (true) {
                    Message message = work.takeFirst();
                    if (message.stop()) break;
                    processed.add(message.text());
                }
                return processed;
            });
            pipeline.submit(() -> {
                for (int number = 1; number <= 4; number++) {
                    work.putLast(new Message("job-" + number, false));
                }
                work.putLast(new Message("", true));
                return List.of();
            });
            for (int completed = 0; completed < 2; completed++) {
                pipeline.take().get();
            }
            List<String> processed = consumer.get();
            System.out.println("Processed FIFO: " + processed);
            System.out.println("Remaining after stop: " + work.size());

            BlockingDeque<String> ends = new LinkedBlockingDeque<>(3);
            ends.putLast("normal-1");
            ends.putLast("normal-2");
            ends.putFirst("urgent");
            System.out.println("Front insertion: " + ends.takeFirst());
            System.out.println("Next normal item: " + ends.takeFirst());

            BlockingDeque<String> timed = new LinkedBlockingDeque<>(1);
            timed.putLast("occupied");
            System.out.println("Timed offer while full: " +
                    timed.offerLast("extra", 20, TimeUnit.MILLISECONDS));
            timed.takeFirst();
            System.out.println("Timed poll while empty: " +
                    timed.pollFirst(20, TimeUnit.MILLISECONDS));
        } finally {
            pool.shutdownNow();
        }
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac -encoding UTF-8 BlockingDequeDemo.java
java BlockingDequeDemo
```

Kết quả chuẩn:

```text
Completed while full: false
Removed to free space: A
Next after put completes: B
Processed FIFO: [job-1, job-2, job-3, job-4]
Remaining after stop: 0
Front insertion: urgent
Next normal item: normal-1
Timed offer while full: false
Timed poll while empty: null
```

### 6.1. Vì sao kết quả FIFO cố định?

Chỉ có một producer thêm job-1 đến job-4 bằng putLast theo thứ tự ấy, và một consumer lấy bằng takeFirst. Việc ai được CPU trước không đảo thứ tự bàn giao trong deque.

Main lấy đủ hai kết quả hoàn tất qua CompletionService và Future.get trước khi in kết quả. Danh sách processed chỉ do consumer sửa rồi chuyển về main sau khi hoàn tất, nên không có nhiều luồng cùng ghi ArrayList đó.

Nếu có nhiều consumer xử lý công việc tốn thời gian khác nhau, thứ tự hoàn tất bên ngoài có thể khác thứ tự lấy. Không tổng quát stdout của mô hình một consumer thành một bảo đảm hoàn tất theo FIFO với nhiều consumer.

### 6.2. Các timeout kiểm chứng điều gì?

Deque timed đã có một phần tử và dung lượng bằng 1. Không bên nào lấy trong lúc timed offer chạy, nên offer thêm thất bại. Sau đó main lấy phần tử cũ ra; không bên nào thêm trong lúc timed poll chạy, nên poll trả null.

Chương trình chỉ hứa kết quả boolean/null. Nó không in hoặc yêu cầu thời lượng đo được phải đúng chính xác 20 mili giây.

### 6.3. Vì sao executor có hai luồng?

Producer có thể chờ khi đầy, consumer có thể chờ khi rỗng; cả hai phải có cơ hội chạy.

Nếu dùng một pool chỉ một luồng rồi tác vụ đầu chiếm luồng để chờ một điều kiện chỉ tác vụ thứ hai trong cùng pool mới tạo được, chương trình có thể không tiến được. Đặt BlockingDeque vào chương trình không tự bảo đảm mọi cách cấp lịch tác vụ đều tránh bế tắc.

## 7. Những bảo đảm có và chưa có

### 7.1. Công bố dữ liệu giữa hai luồng

Các hành động xảy ra trước khi producer đặt một đối tượng vào deque có quan hệ happens-before với các hành động sau khi consumer truy cập/lấy đối tượng đó qua deque theo hợp đồng.

Điều này hỗ trợ bàn giao dữ liệu đã chuẩn bị. Nó không tự bảo vệ mọi sửa đổi xảy ra **sau khi gửi** trên cùng một đối tượng mutable.

Ví dụ, producer gửi một ArrayList rồi tiếp tục sửa trong khi consumer đang đọc thì vẫn cần chính sách chia sẻ/đồng bộ. Trong ví dụ, Message và String bất biến giúp trách nhiệm sở hữu rõ hơn.

### 7.2. Lấy một phần tử không đồng nghĩa xử lý thành công

takeFirst xóa phần tử khỏi deque và trả cho consumer. Nếu process thất bại sau đó, deque không tự khôi phục phần tử, không tự thử lại và không lưu bền vững qua khởi động lại tiến trình.

Nếu yêu cầu nghiệp vụ cần xác nhận hoàn tất, thử lại hoặc không mất việc khi lỗi, cần thiết kế thêm. BlockingDeque giải quyết bàn giao và chờ trong bộ nhớ, không phải toàn bộ vòng đời xử lý công việc.

### 7.3. Chờ không có nghĩa cả chương trình luôn tiến

Không giữ một khóa ứng dụng trong lúc gọi take/put có thể chờ vô hạn nếu bên tạo điều kiện cần chính khóa đó. Các thao tác deque có đồng bộ nội bộ, nhưng các khóa ngoài và tài nguyên khác vẫn có thể tạo vòng chờ.

Đồng thời, nếu consumer đã lỗi và không còn ai lấy, producer có thể kẹt ở put. Cần thu lỗi tác vụ và có đường hủy phù hợp. Chương trình lấy kết quả theo thứ tự tác vụ hoàn tất và gọi Future.get để nhận ngoại lệ; nếu consumer lỗi trước, main có thể nhận lỗi đó mà không phải đợi producer đang mắc ở put. Khối finally yêu cầu ngắt các tác vụ còn lại khi main thoát. Đây vẫn là xử lý trong bộ nhớ, không phải cơ chế phục hồi công việc bền vững.

## 8. Khi nên và không nên chọn BlockingDeque

| Nhu cầu | Cân nhắc |
| --- | --- |
| Producer–consumer FIFO | BlockingQueue thường đã đủ; dùng deque nếu còn cần hai đầu |
| Cần đưa một số phần tử lên đầu | BlockingDeque diễn đạt trực tiếp, nhưng phải định nghĩa thứ tự và nguy cơ chờ lâu của phần tử khác |
| Cần chờ khi rỗng hoặc đầy | Dùng take/put hoặc biến thể timeout |
| Chỉ cần thử lấy ngay rồi làm việc khác | Poll không timeout |
| Không muốn giữ luồng chờ | Cần xem lại mô hình xử lý hoặc chọn thao tác không chờ phù hợp |
| Cần ưu tiên theo giá trị số | Thêm đầu/cuối không thay thế một cấu trúc có quy tắc ưu tiên đầy đủ |
| Cần lưu việc qua khởi động lại | Deque trong bộ nhớ chưa đáp ứng |

Với LinkedBlockingDeque, các thao tác hai đầu thường có chi phí hằng số nếu bỏ qua thời gian chờ. Tìm/xóa theo giá trị, contains và các thao tác hàng loạt có thể tuyến tính theo số phần tử. Thời gian chờ do đầy/rỗng là một phần rất quan trọng của độ trễ thực tế, không thể chỉ nhìn độ phức tạp cấu trúc.

## 9. Lỗi thường gặp và thực hành

| Lỗi | Cách sửa |
| --- | --- |
| Mọi phương thức trên BlockingDeque đều chờ | Chọn đúng add/offer/put và remove/poll/take |
| Dùng push để chờ có chỗ | Dùng putFirst hoặc timed offerFirst |
| Dùng null để báo kết thúc | Dùng thông điệp kết thúc hợp lệ, không null |
| Rỗng nghĩa là producer đã xong | Thiết kế giao thức dừng |
| Kiểm tra remainingCapacity rồi add | Dùng trực tiếp put/offer và xử lý kết quả |
| Bỏ qua false của offer | Quyết định thử lại, từ chối hoặc chuyển hướng dữ liệu |
| Nuốt InterruptedException | Xử lý yêu cầu dừng và giữ đúng chính sách ngắt |
| Dung lượng deque là toàn bộ công việc trong hệ thống | Còn dữ liệu đang xử lý hoặc ở vùng đệm khác |
| Nhiều consumer hoàn tất đúng thứ tự lấy | Phân biệt thứ tự bàn giao và hoàn tất |
| Chỉ một stop tự kết thúc mọi consumer | Tính số consumer và thời điểm gửi tín hiệu |

Bài tập:

1. Đổi dung lượng work từ 2 sang 1. Kết quả bốn job vẫn giữ FIFO; giải thích chỗ nào producer có thể phải chờ.
2. Bỏ thông điệp stop trong bản thử có cơ chế hủy kiểm soát. Giải thích vì sao consumer không thể tự biết hết dữ liệu chỉ bằng việc deque tạm rỗng.
3. Dùng offerLast không timeout trên một deque đã đầy. Kết quả phải là false và phần tử mới chưa được thêm.
4. Thêm một thông điệp ở đầu trước khi consumer lấy. Dự đoán thứ tự và chỉ rõ tại sao không còn là FIFO theo toàn bộ thứ tự thêm.
5. Thiết kế giao thức dừng cho hai consumer sau khi hai producer đã hoàn tất. Chỉ rõ ai gửi tín hiệu dừng và số lượng tín hiệu.
6. Cho consumer xử lý chậm, sau đó giải thích dung lượng deque giới hạn phần nào của bộ nhớ và công việc, phần nào chưa được giới hạn.

Khi dùng BlockingDeque để phối hợp producer–consumer, hãy chốt đầu thêm/lấy, giới hạn vùng đệm, chính sách chờ và giao thức kết thúc. Một lời gọi đúng không thay thế bốn quyết định về vòng đời luồng và dữ liệu ấy.
