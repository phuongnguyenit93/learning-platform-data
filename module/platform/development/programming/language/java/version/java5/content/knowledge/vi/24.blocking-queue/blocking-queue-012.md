# Điều phối dừng khi có nhiều luồng sản xuất hoặc tiêu thụ

## 1. Dừng là một giao thức của cả nhóm luồng

Trong mô hình bên sản xuất – bên tiêu thụ, các luồng sản xuất đưa công việc vào `BlockingQueue`, còn các luồng tiêu thụ lấy công việc ra để xử lý. Khi có nhiều luồng ở mỗi phía, “một luồng đã xong” không đồng nghĩa “toàn bộ hệ thống đã xong”.

Muốn dừng đúng, phải trả lời ba câu hỏi:

1. Từ lúc nào chắc chắn không còn công việc mới được thêm?
2. Làm thế nào để mọi bên tiêu thụ biết đã hết việc, kể cả khi đang chờ ở `take()`?
3. Ai xác nhận các công việc đã nhận đều xử lý xong và mọi luồng đã kết thúc?

`BlockingQueue` không có thao tác đóng hàng đợi hoặc tắt hệ thống tích hợp sẵn. [Hợp đồng `BlockingQueue`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/BlockingQueue.html) để việc biểu diễn kết thúc cho ứng dụng quyết định; một cách phổ biến là dùng đối tượng báo hết dữ liệu.

Cần tách hai chính sách ngay từ đầu:

| Chính sách | Mục tiêu | Điều có thể chấp nhận |
| --- | --- | --- |
| Dừng êm | Ngừng thêm dữ liệu mới, xử lý hết phần đã nhận, rồi kết thúc | Phải chờ các công việc đang chạy và phần tồn trong hàng |
| Hủy do lỗi hoặc hết thời hạn | Ngừng chờ và yêu cầu cả nhóm kết thúc | Có thể còn công việc chưa xử lý; phải ghi nhận và có cách giải quyết riêng |

Ngắt luồng để hủy không phải bằng chứng rằng dữ liệu đã được xử lý hết. Một ví dụ dừng êm cũng không được mặc định rằng mọi luồng luôn thành công mà bỏ qua đường lỗi.

## 2. Quy tắc cốt lõi khi có nhiều bên sản xuất

Giả sử có hai bên sản xuất `P1`, `P2`, và ba bên tiêu thụ `C1`, `C2`, `C3`.

Sai lầm thường gặp là mỗi bên sản xuất tự gửi tín hiệu dừng ngay khi nó hết dữ liệu. Nếu `P1` xong sớm, tín hiệu đó có thể làm một bên tiêu thụ thoát trong lúc `P2` còn đang tạo công việc. Nếu đủ bên tiêu thụ đều thoát sớm, `P2` còn có thể bị kẹt ở `put()` vì hàng đầy và không còn ai lấy.

Cách dễ kiểm soát hơn là giao quyền kết thúc cho một bộ điều phối duy nhất:

```text
các bên sản xuất chạy và đưa công việc vào hàng
        ↓
bộ điều phối xác nhận TẤT CẢ bên sản xuất đã hoàn tất thành công
        ↓
bộ điều phối gửi tín hiệu dừng cho các bên tiêu thụ
        ↓
các bên tiêu thụ xử lý phần công việc trước tín hiệu rồi kết thúc
        ↓
bộ điều phối chờ TẤT CẢ bên tiêu thụ kết thúc thành công
```

“Bên sản xuất hoàn tất” phải có nghĩa là nó đã thực hiện xong mọi thao tác đưa công việc thuộc trách nhiệm của mình vào hàng. Nếu nó chỉ khởi chạy thêm một tác vụ khác rồi báo xong trong khi tác vụ đó còn có thể thêm dữ liệu, điều kiện kết thúc chưa được đáp ứng.

Với luồng dữ liệu liên tục, cần có bước ngừng tiếp nhận từ nguồn bên ngoài trước khi đợi bên sản xuất hoàn tất. Chỉ đọc một cờ “đã đóng” rồi thêm phần tử ở bước riêng có thể có khoảng đua; việc đóng tiếp nhận và quản lý các lần gửi đang diễn ra phải được đồng bộ ở lớp quản lý.

## 3. Một tín hiệu dừng cho mỗi bên tiêu thụ

Đối tượng báo dừng thường được gọi là poison pill. Nó là một thông điệp điều khiển mà bên tiêu thụ nhận ra và dùng để thoát vòng lặp.

Trong giao thức mỗi bên tiêu thụ lấy một tín hiệu rồi thoát, có `C` bên tiêu thụ thì cần gửi `C` tín hiệu. Khi một bên đã nhận tín hiệu, nó phải kết thúc, không quay lại lấy thêm tín hiệu của bên khác.

Không dùng `null` vì `BlockingQueue` không cho phép phần tử `null`. Cũng không dùng một giá trị dữ liệu bình thường như chuỗi rỗng hoặc số `-1` nếu chúng có thể là công việc hợp lệ. Một kiểu thông điệp riêng giúp tách rõ dữ liệu và điều khiển.

Ví dụ sẽ dùng:

```java
interface Message {}
record Work(int value) implements Message {}
enum End implements Message { INSTANCE }
```

Có thể đưa cùng tham chiếu `End.INSTANCE` vào hàng nhiều lần; mỗi lần thêm là một mục trong hàng. Đếm số mục tín hiệu, không phải số đối tượng được cấp phát.

Có thiết kế để bên tiêu thụ nhận một tín hiệu rồi đưa lại cho bên tiếp theo, nhưng cách đó cần thêm lập luận về lỗi, số bên còn sống và khả năng đưa lại khi hàng đầy. Không trộn hai giao thức. Bài này chỉ dùng một tín hiệu cho mỗi bên tiêu thụ, do bộ điều phối gửi.

## 4. Điều kiện để tín hiệu đứng sau toàn bộ công việc

Ví dụ dùng `ArrayBlockingQueue`, một hàng đợi FIFO. Tất cả lần thêm công việc đã hoàn tất trước khi bộ điều phối bắt đầu thêm tín hiệu, nên tín hiệu được xếp sau các công việc còn ở trong hàng.

Điều này không có nghĩa mọi công việc đã xử lý xong khi tín hiệu đầu tiên được lấy. Một bên tiêu thụ có thể đang xử lý công việc đã lấy trước đó, trong khi bên khác đã gặp tín hiệu và thoát. Bộ điều phối vẫn phải đợi tất cả bên tiêu thụ hoàn tất mới kết luận dừng êm thành công.

Không áp dụng nguyên xi lập luận FIFO cho mọi `BlockingQueue`. Hàng ưu tiên có thể đưa tín hiệu lên trước dữ liệu; hàng trì hoãn có thêm điều kiện thời gian. Khi thay loại hàng đợi, phải kiểm tra lại toàn bộ ý nghĩa thứ tự của giao thức.

Cũng cần giữ cố định số bên tiêu thụ trong một lượt dừng hoặc có cơ chế đăng ký/rút lui được quản lý rõ ràng. Gửi ba tín hiệu cho một nhóm có thể tự tăng lên bốn bên tiêu thụ sẽ để một bên không nhận được tín hiệu.

## 5. Ví dụ hoàn chỉnh: hai bên sản xuất, ba bên tiêu thụ

Lưu thành `CoordinatedStopDemo.java`. Chương trình Java 17+ có các đặc điểm:

- Hàng FIFO chỉ có dung lượng 2, nhỏ hơn số bên tiêu thụ và số công việc.
- Hai bên sản xuất tạo tổng cộng các số 1 đến 6.
- Ba bên tiêu thụ xử lý, rồi mỗi bên nhận một thông điệp `End` để kết thúc.
- Bộ điều phối nhận kết quả theo thứ tự tác vụ hoàn tất, phát hiện ngoại lệ qua `Future.get()` và có thời hạn tổng cho ví dụ.

`ExecutorCompletionService` giúp bộ điều phối quan sát tác vụ nào đã kết thúc, thay vì chỉ chờ một bên sản xuất có thể đang bị kẹt và không nhìn thấy lỗi của bên khác. Cơ chế nhận kết quả này được mô tả trong [Java SE `ExecutorCompletionService`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorCompletionService.html).

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.ExecutorCompletionService;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;
import java.util.concurrent.atomic.AtomicInteger;

public class CoordinatedStopDemo {
    interface Message {}
    record Work(int value) implements Message {}
    enum End implements Message { INSTANCE }
    enum Role { PRODUCER, CONSUMER }

    public static void main(String[] args) throws Exception {
        int producers = 2;
        int consumers = 3;
        BlockingQueue<Message> queue = new ArrayBlockingQueue<>(2);
        AtomicInteger processed = new AtomicInteger();
        AtomicInteger sum = new AtomicInteger();
        ExecutorService pool = Executors.newFixedThreadPool(producers + consumers);
        ExecutorCompletionService<Role> completed =
                new ExecutorCompletionService<>(pool);
        List<Future<Role>> futures = new ArrayList<>();

        int producersFinished = 0;
        int consumersFinished = 0;
        int endMessagesSent = 0;
        int tasksFinished = 0;
        long start = System.nanoTime();
        long budget = TimeUnit.SECONDS.toNanos(10);

        try {
            for (int c = 0; c < consumers; c++) {
                futures.add(completed.submit(() -> {
                    while (true) {
                        Message message = queue.take();
                        if (message == End.INSTANCE) {
                            return Role.CONSUMER;
                        }
                        Work work = (Work) message;
                        sum.addAndGet(work.value());
                        processed.incrementAndGet();
                    }
                }));
            }

            for (int p = 0; p < producers; p++) {
                int first = p * 3 + 1;
                futures.add(completed.submit(() -> {
                    for (int value = first; value < first + 3; value++) {
                        queue.put(new Work(value));
                    }
                    return Role.PRODUCER;
                }));
            }

            while (tasksFinished < producers + consumers) {
                if (System.nanoTime() - start >= budget) {
                    throw new TimeoutException("workers did not finish in time");
                }

                Future<Role> result = completed.poll(20, TimeUnit.MILLISECONDS);
                if (result != null) {
                    Role role = result.get();
                    tasksFinished++;
                    if (role == Role.PRODUCER) {
                        producersFinished++;
                    } else {
                        consumersFinished++;
                    }
                }

                if (producersFinished == producers
                        && endMessagesSent < consumers
                        && queue.offer(End.INSTANCE)) {
                    endMessagesSent++;
                }
            }
        } finally {
            for (Future<Role> future : futures) {
                future.cancel(true);
            }
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("workers did not terminate");
            }
        }

        System.out.println("producers finished: " + producersFinished);
        System.out.println("end messages sent: " + endMessagesSent);
        System.out.println("consumers finished: " + consumersFinished);
        System.out.println("processed: " + processed.get());
        System.out.println("sum: " + sum.get());
        System.out.println("queue empty: " + queue.isEmpty());
    }
}
```

Biên dịch và chạy:

```shell
javac --release 17 CoordinatedStopDemo.java
java CoordinatedStopDemo
```

Stdout khi các tác vụ hoàn tất bình thường trong thời hạn của ví dụ:

```text
producers finished: 2
end messages sent: 3
consumers finished: 3
processed: 6
sum: 21
queue empty: true
```

Không in tên luồng xử lý từng phần tử vì thứ tự đó phụ thuộc lập lịch và không giúp chứng minh giao thức dừng. Hai biến `processed`, `sum` là biến nguyên tử để việc tổng hợp từ nhiều bên tiêu thụ không bị mất cập nhật.

## 6. Đọc đúng vai trò của bộ điều phối trong ví dụ

### Xác nhận thành công thay vì chỉ đếm tác vụ đã dừng

`result.get()` chạy trước khi tăng bộ đếm. Nếu bên sản xuất hoặc tiêu thụ ném ngoại lệ, `get()` báo lỗi bằng `ExecutionException`; tác vụ đó không được tính như đã hoàn tất thành công. Chương trình đi vào nhánh dọn dẹp và yêu cầu hủy các tác vụ còn lại.

Nếu chỉ gọi `isDone()` hoặc giảm một bộ đếm trong `finally` rồi xem như thành công, có thể phát tín hiệu dừng dù bên sản xuất đã thất bại giữa chừng và thiếu công việc. Cần phân biệt “đã kết thúc” với “đã hoàn tất đúng yêu cầu”.

### Không để việc gửi tín hiệu làm bộ điều phối mất khả năng quan sát lỗi

Khi hàng đầy, `queue.offer(End.INSTANCE)` trả `false`. Bộ điều phối không tăng số tín hiệu đã gửi; nó quay lại quan sát kết quả tác vụ rồi thử trong lượt sau. `completed.poll(20, MILLISECONDS)` giúp tránh vòng quay bận và vẫn kiểm tra được thời hạn tổng.

Nếu thay bằng một vòng `put` tín hiệu mà không có giám sát khác, khi các bên tiêu thụ đều lỗi và hàng đầy, bộ điều phối có thể kẹt ở chính thao tác gửi tín hiệu. Khả năng kết thúc phải bao gồm cả đường lỗi, không chỉ đường chạy bình thường.

Dung lượng hàng không bắt buộc lớn hơn hoặc bằng số bên tiêu thụ. Trong ví dụ dung lượng 2 nhưng gửi được 3 tín hiệu vì các bên tiêu thụ liên tục lấy ra. Không yêu cầu nhét toàn bộ tín hiệu vào hàng cùng một lúc.

### Bảo đảm có luồng để cả hai phía tiến triển

Nhóm luồng có `producers + consumers` chỗ chạy, nên cả bên tạo lẫn bên xử lý đều có cơ hội hoạt động. Nếu dùng một nhóm quá nhỏ và toàn bộ chỗ chạy bị chiếm bởi các bên đang chờ, phía đối ứng có thể chưa bao giờ được lập lịch để giải phóng điều kiện chờ.

Trong ứng dụng lớn, có thể dùng các nhóm luồng riêng hoặc cách quản lý khác. Điểm cần chứng minh là những tác vụ phụ thuộc nhau không chiếm hết tài nguyên khiến đối tác không thể chạy.

### Thời hạn tổng là chính sách, không phải bằng chứng công việc đã hoàn thành

Mốc 10 giây chỉ là giới hạn của lượt chạy minh họa, không phải một con số nên sao chép cho mọi hệ thống. Khi quá thời hạn, ví dụ báo lỗi và hủy; nó không in báo cáo thành công. Khoảng chờ dọn dẹp 5 giây cũng có giới hạn, và việc không kết thúc được được báo bằng ngoại lệ.

Nếu nhánh dọn dẹp tự thất bại, ứng dụng thực tế nên lưu cả lỗi ban đầu lẫn lỗi dọn dẹp, chẳng hạn bằng cơ chế ngoại lệ bị bổ sung (`suppressed exception`). Ví dụ ưu tiên báo việc luồng không chịu kết thúc; nó không thay thế hệ thống ghi nhận lỗi đầy đủ của ứng dụng.

## 7. Ngắt luồng và `shutdown` không thay thế tín hiệu hết dữ liệu

`ExecutorService.shutdown()` ngừng nhận tác vụ mới nhưng cho tác vụ đã gửi tiếp tục chạy. Một bên tiêu thụ đã nằm trong vòng `take()` vô hạn vẫn có thể chờ mãi sau `shutdown`, nếu không ai gửi thông điệp kết thúc.

`shutdownNow()` yêu cầu dừng theo khả năng tốt nhất, thường bằng ngắt luồng. Nó không bảo đảm mọi tác vụ thực sự dừng và không bảo đảm công việc đã xử lý hết. Các khác biệt này được nêu trong [Java SE `ExecutorService`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ExecutorService.html).

Trong ví dụ:

- Đường bình thường: các bên tiêu thụ đã tự kết thúc do nhận đủ tín hiệu trước khi đi vào `finally`.
- Đường lỗi: `cancel(true)` và `shutdownNow()` yêu cầu hủy các tác vụ còn lại; `put()` và `take()` có thể thoát qua `InterruptedException`.
- `awaitTermination` đợi nhóm luồng kết thúc; gửi yêu cầu hủy và xác nhận kết thúc là hai bước riêng.

Tác vụ trong ví dụ là `Callable`, nên có thể truyền `InterruptedException` ra để hoàn tất bằng lỗi. Nếu tự bắt trong `Runnable` và quyết định kết thúc, thường khôi phục cờ ngắt bằng `Thread.currentThread().interrupt()` rồi thoát. Không bắt ngoại lệ rồi tiếp tục vòng lặp vô hạn, vì như vậy đã vô hiệu hóa yêu cầu dừng.

Nếu xử lý công việc có gọi I/O hoặc mã không đáp ứng ngắt, phải có cơ chế hủy hoặc thời hạn riêng cho hoạt động đó. Không dùng cơ chế dừng luồng cưỡng bức lỗi thời để che việc thiếu hợp tác khi hủy.

## 8. Những điều dễ bị bỏ sót khi cần dừng êm

### Hàng trống chưa chắc đã hết việc

Một bên tiêu thụ có thể vừa lấy công việc cuối và còn đang xử lý, trong khi bên sản xuất còn có thể tạo thêm. `queue.isEmpty()` không chứng minh cả hai điều kiện “không còn dữ liệu mới” và “không còn xử lý đang diễn ra”.

Không viết một bộ điều phối chỉ đợi `isEmpty()` rồi tuyên bố xong. Cần biết trạng thái bên sản xuất và kết quả bên tiêu thụ.

### Không giữ khóa mà bên đối ứng cần trong lúc chờ

Nếu bên sản xuất giữ một khóa ứng dụng rồi gọi `put` khi hàng đầy, còn bên tiêu thụ phải có chính khóa đó mới xử lý hoặc tiến tới lần lấy tiếp theo, hệ thống có thể mắc kẹt. Khóa nội bộ của hàng đợi không giải quyết được chu trình chờ do khóa ứng dụng tạo ra.

### Hủy có thể bỏ lại công việc đã nhận

Khi một bên tiêu thụ lỗi sau khi lấy phần tử, phần tử đó không còn trong hàng nhưng cũng có thể chưa xử lý xong. Chỉ kiểm tra phần tử còn trong hàng không đủ để biết mọi công việc chưa hoàn tất.

Nếu ứng dụng cần khôi phục, phải theo dõi công việc đang xử lý, trạng thái xác nhận, cơ chế thử lại hoặc nơi lưu bền phù hợp. Hàng đợi bộ nhớ và tín hiệu dừng không tự cung cấp bảo đảm xử lý đúng một lần khi tiến trình hoặc tác vụ lỗi.

### Bộ đếm và chốt chờ phải có định nghĩa chính xác

Có thể dùng `CountDownLatch` để chờ một nhóm hữu hạn, nhưng cần lưu lỗi riêng. Đặt `countDown()` trong `finally` giúp không kẹt vì bỏ quên giảm chốt, song chỉ cho biết tác vụ đã đi đến bước kết thúc, không khẳng định thành công. Không suy ra mọi công việc đã được tạo hoặc xử lý chỉ vì chốt đã về 0.

### Số tín hiệu phải khớp giao thức tiêu thụ

Cách mỗi bên nhận một tín hiệu rồi thoát giả định việc lấy từng thông điệp. Nếu bên tiêu thụ lấy một lô bằng `drainTo`, một bên có thể hút nhiều tín hiệu cùng lúc. Khi đổi sang xử lý theo lô, phải thiết kế lại cách phân phối tín hiệu, không giữ nguyên lập luận của ví dụ.

## 9. Tự kiểm tra bằng một dòng thời gian

Giả sử `P1` hoàn tất, `P2` còn đang tạo dữ liệu, và hàng hiện đang trống:

1. Đã có thể gửi tín hiệu kết thúc cho toàn bộ bên tiêu thụ chưa?
2. Vì sao một tín hiệu duy nhất không đủ cho ba bên tiêu thụ theo giao thức trong bài?
3. Khi một bên tiêu thụ đã nhận tín hiệu nhưng bên khác còn xử lý, đã được báo dừng êm thành công chưa?
4. Nếu một bên tiêu thụ lỗi làm bên sản xuất kẹt ở `put`, bộ điều phối chỉ chờ `Future` của bên sản xuất sẽ gặp vấn đề gì?
5. Vì sao gọi `shutdown()` lên executor chưa đủ để đánh thức mọi `take()`?

Gợi ý: (1) Chưa, vẫn có dữ liệu tương lai từ `P2`. (2) Bên nhận đầu tiên lấy tín hiệu ra rồi thoát; hai bên còn lại không còn tín hiệu. (3) Chưa, phải chờ tất cả hoàn tất thành công. (4) Có thể chờ mãi mà không quan sát lỗi của phía tiêu thụ; cần giám sát kết quả và đường hủy. (5) Nó quản lý nhận tác vụ của executor, không đóng hàng đợi ứng dụng và không tự đưa thông điệp kết thúc vào đó.
