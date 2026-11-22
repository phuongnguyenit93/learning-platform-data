# Hàng đợi có giới hạn, không giới hạn và SynchronousQueue

## 1. Chọn hàng đợi là chọn cách tiếp nhận tải

Khi tất cả luồng làm việc đều bận, tác vụ mới sẽ được giữ ở đâu? Ứng dụng muốn nhận thêm bao nhiêu việc trước khi phản hồi quá tải? Có muốn tạo thêm luồng khi không có nơi lưu tác vụ chờ không?

Trong `ThreadPoolExecutor`, hàng đợi không chỉ là chỗ cất tạm. Nó phối hợp với `corePoolSize`, `maximumPoolSize` và chính sách từ chối để quyết định công việc được xếp chờ, được giao cho luồng bổ sung hay không được tiếp nhận.

Ba hướng chính:

- **Có giới hạn:** chỉ giữ tối đa một số phần tử.
- **Không đặt giới hạn nhỏ theo cấu hình:** tiếp tục nhận nhiều tác vụ chờ, với giới hạn tài nguyên thực tế.
- **Chuyển giao trực tiếp bằng SynchronousQueue:** không có vùng lưu phần tử chờ bên trong.

Các loại này có từ Java 5 và vẫn sử dụng trên Java hiện đại. Toàn bộ chương trình trong bài chạy với Java 17+.

## 2. “Blocking” không có nghĩa mọi lời gọi đều chờ

`BlockingQueue` có nhiều nhóm thao tác:

| Thao tác | Nếu chưa thể đưa phần tử vào ngay |
| --- | --- |
| `add(e)` | Ném lỗi nếu không thêm được do hết dung lượng |
| `offer(e)` | Trả `false` |
| `put(e)` | Chờ tới khi thêm được hoặc bị ngắt |
| `offer(e, timeout, unit)` | Chờ có giới hạn |

Cách dùng hàng đợi quyết định cách bên gửi bị ảnh hưởng. Với ThreadPoolExecutor tiêu chuẩn, khi thử xếp tác vụ, nó không dùng `put` để luôn chờ hàng đợi có chỗ; nếu không xếp được, nó xét khả năng tạo luồng và từ chối.

Vì thế, cấu hình `ArrayBlockingQueue` không tự biến `execute` thành thao tác chặn cho tới khi hàng đợi rảnh. Nếu muốn giảm tốc độ bên gửi hoặc trả lỗi quá tải, phải chọn chính sách tiếp nhận rõ ràng.

Tương tự, `SynchronousQueue.put` có thể chờ một bên nhận, nhưng điều đó không có nghĩa `ThreadPoolExecutor.execute` với SynchronousQueue sẽ chờ vô hạn một luồng rảnh.

## 3. Hàng đợi có giới hạn

### ArrayBlockingQueue

`new ArrayBlockingQueue<Runnable>(100)` tạo vùng đệm dùng mảng, giữ tối đa 100 phần tử. Dung lượng không thay đổi sau khi tạo.

Phần tử được lấy theo FIFO: phần tử đã ở đầu hàng đợi lâu nhất được lấy trước. Có tùy chọn công bằng cho các luồng đang chờ truy cập, nhưng nó không bảo đảm toàn bộ tác vụ của một bộ luồng nhiều luồng sẽ kết thúc theo thứ tự gửi. [Tài liệu ArrayBlockingQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ArrayBlockingQueue.html)

### LinkedBlockingQueue có dung lượng chỉ định

`new LinkedBlockingQueue<Runnable>(100)` cũng có giới hạn 100 phần tử, nhưng cấu trúc lưu trữ dựa trên các nút liên kết được cấp phát khi thêm.

Vì vậy, “LinkedBlockingQueue là không giới hạn” là phát biểu thiếu điều kiện. Constructor có truyền capacity tạo một hàng đợi có giới hạn.

Chọn cấu trúc mảng hay nút liên kết cần dựa trên đặc điểm tải và đo đạc. Không có quy tắc rằng một loại luôn nhanh hơn trong mọi cấu hình, kích thước phần tử và mức cạnh tranh.

### Giới hạn theo phần tử chưa phải giới hạn theo byte

Một tác vụ có thể giữ một mảng dữ liệu lớn, đối tượng yêu cầu hoặc nhiều tham chiếu tài nguyên. Hai hàng đợi cùng chứa 100 tác vụ có thể chiếm lượng bộ nhớ khác xa nhau.

Dung lượng hàng đợi cũng là ngân sách **công việc đang chờ**, không bao gồm các tác vụ đã được luồng làm việc lấy ra để chạy. Với bộ luồng đạt max bằng 4 và hàng đợi có dung lượng 100, có thể có tới 4 công việc ở các luồng và 100 phần tử chờ trong cấu hình thông thường đó; còn tài nguyên ở tầng ngoài vẫn phải tính riêng.

## 4. Hàng đợi được gọi là “không giới hạn”

`new LinkedBlockingQueue<Runnable>()` không đặt một dung lượng nhỏ theo yêu cầu ứng dụng; dung lượng của constructor mặc định là `Integer.MAX_VALUE`. Nó không cấp phát sẵn từng ấy nút và cũng không có nghĩa bộ nhớ là vô hạn. [Tài liệu LinkedBlockingQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/LinkedBlockingQueue.html)

Nếu bên gửi nhanh hơn khả năng xử lý trong thời gian dài, các tác vụ chờ tích tụ. Việc chưa thấy từ chối không chứng minh hệ thống còn khỏe: độ trễ có thể đã tăng và bộ nhớ đang bị giữ nhiều hơn.

Trong ThreadPoolExecutor, sau khi đạt core, hàng đợi loại này thường tiếp tục nhận tác vụ. Do chưa gặp trạng thái hàng đợi không nhận thêm được, bộ thực thi thường không cần mở rộng tới max.

Ví dụ core bằng 2, max bằng 20 không tự cho phép xử lý đồng thời tới 20 tác vụ khi dùng hàng đợi mặc định không có giới hạn thực dụng. Hai luồng có thể bận trong lúc hàng nghìn công việc chờ phía sau.

Điều này có thể phù hợp cho một tập công việc hữu hạn đã biết và nguồn gửi được kiểm soát. Nhưng không nên coi nó là giải pháp tự xử lý một nguồn tải mở không có giới hạn.

## 5. SynchronousQueue: chuyển giao, không phải vùng đệm một phần tử

`SynchronousQueue` không có dung lượng lưu nội bộ, kể cả một phần tử. Một bên đưa dữ liệu cần ghép với một bên nhận:

```text
Luồng gửi  ---- phần tử ---->  Luồng nhận
           cần gặp nhau
           không có kệ lưu ở giữa
```

`offer(e)` chỉ thành công khi có bên đang sẵn sàng nhận. `put(e)` chờ sự ghép đôi. `offer` có timeout chờ ghép đôi trong thời gian giới hạn.

Những phương thức quan sát như `size()` luôn thấy 0; `isEmpty()` luôn là true. Điều đó không chứng minh không có luồng nào đang đợi chuyển giao. Đây là đặc điểm giao diện collection của SynchronousQueue, không phải thước đo toàn bộ tải hệ thống. [Tài liệu SynchronousQueue](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/SynchronousQueue.html)

Trong bộ thực thi, nếu không có luồng rảnh đang nhận công việc, việc offer có thể thất bại. Bộ thực thi khi đó thử tạo thêm luồng nếu còn dưới max. Nếu đã đạt max, tác vụ đi tới chính sách từ chối.

Không có chỗ lưu chờ có thể làm hệ thống bộc lộ tình trạng bận sớm hơn. Nó không tự bảo vệ tài nguyên nếu max được đặt cực lớn và nguồn gửi liên tục tạo nhu cầu thêm luồng.

## 6. Thí nghiệm nhỏ với API hàng đợi

Chương trình chỉ dùng hàng đợi trực tiếp để thấy hai cơ chế khác nhau; nó không thay thế đường gửi công việc qua ExecutorService.

Tệp **QueueOperationsDemo.java**:

```java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.FutureTask;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.TimeUnit;

public class QueueOperationsDemo {
    public static void main(String[] args) throws Exception {
        ArrayBlockingQueue<String> buffered = new ArrayBlockingQueue<>(1);

        System.out.println("buffer.offerA=" + buffered.offer("A"));
        System.out.println("buffer.offerB=" + buffered.offer("B"));
        System.out.println("buffer.size=" + buffered.size());
        System.out.println("buffer.take=" + buffered.take());

        SynchronousQueue<String> handoff = new SynchronousQueue<>();
        System.out.println("handoff.offerWithoutReceiver="
                + handoff.offer("unused"));

        FutureTask<String> receive = new FutureTask<>(handoff::take);
        Thread receiver = new Thread(receive, "handoff-receiver");

        try {
            receiver.start();
            boolean delivered = handoff.offer("payload", 5, TimeUnit.SECONDS);
            if (!delivered) {
                throw new IllegalStateException("No receiver accepted payload");
            }

            System.out.println("handoff.delivered=" + delivered);
            System.out.println("handoff.received="
                    + receive.get(5, TimeUnit.SECONDS));
            System.out.println("handoff.size=" + handoff.size());
        } finally {
            receiver.interrupt();
            receiver.join(5000);
            if (receiver.isAlive()) {
                throw new IllegalStateException("Receiver did not terminate");
            }
        }
    }
}
```

Chạy:

```shell
javac --release 17 QueueOperationsDemo.java
java QueueOperationsDemo
```

Stdout khi hoàn tất bình thường:

```text
buffer.offerA=true
buffer.offerB=false
buffer.size=1
buffer.take=A
handoff.offerWithoutReceiver=false
handoff.delivered=true
handoff.received=payload
handoff.size=0
```

Với vùng đệm một phần tử, A có thể được lưu khi chưa có bên nhận; B không còn chỗ. Với SynchronousQueue, lần offer đầu thất bại vì chưa có bên nhận, dù size bằng 0.

Lần offer có timeout phối hợp với luồng receiver để chuyển `payload`. FutureTask ở đây chỉ giữ kết quả của luồng nhận. Các dòng stdout được in bởi main theo các mốc lấy kết quả, không dựa vào thứ tự in cạnh tranh giữa hai luồng.

## 7. Cùng core/max, ba hàng đợi tạo ba hành vi

Giữ cấu hình core bằng 1, max bằng 2, cùng `AbortPolicy`, rồi gửi bốn tác vụ. Mọi tác vụ đã bắt đầu đều bị giữ ở chốt, nên trạng thái không bị thay đổi bởi việc hoàn thành quá nhanh.

Dự đoán:

| Hàng đợi | Tác vụ ở các luồng | Tác vụ chờ | Bị từ chối |
| --- | --- | --- | --- |
| ArrayBlockingQueue(1) | 2 | 1 | 1 |
| LinkedBlockingQueue mặc định | 1 | 3 | 0 |
| SynchronousQueue | 2 | 0 | 2 |

Tệp **QueuePolicyDemo.java**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.Callable;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Future;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.SynchronousQueue;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;

public class QueuePolicyDemo {
    public static void main(String[] args) throws Exception {
        inspect("bounded", new ArrayBlockingQueue<>(1), 2);
        inspect("unbounded", new LinkedBlockingQueue<>(), 1);
        inspect("handoff", new SynchronousQueue<>(), 2);
    }

    private static void inspect(
            String label, BlockingQueue<Runnable> queue, int expectedWorkers)
            throws Exception {
        ThreadPoolExecutor pool = new ThreadPoolExecutor(
                1, 2, 30, TimeUnit.SECONDS,
                queue, new ThreadPoolExecutor.AbortPolicy());

        CountDownLatch firstStarted = new CountDownLatch(1);
        CountDownLatch workersStarted = new CountDownLatch(expectedWorkers);
        CountDownLatch release = new CountDownLatch(1);
        List<Future<Integer>> accepted = new ArrayList<>();
        int rejected = 0;

        Callable<Integer> work = () -> {
            firstStarted.countDown();
            workersStarted.countDown();
            release.await();
            return 1;
        };

        try {
            accepted.add(pool.submit(work));
            if (!firstStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("First task did not start");
            }

            for (int i = 0; i < 3; i++) {
                try {
                    accepted.add(pool.submit(work));
                } catch (RejectedExecutionException ex) {
                    rejected++;
                }
            }

            if (!workersStarted.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Expected workers did not start");
            }

            System.out.println(label + ": poolSize=" + pool.getPoolSize()
                    + ", queueSize=" + queue.size()
                    + ", accepted=" + accepted.size()
                    + ", rejected=" + rejected);

            release.countDown();
            int completed = 0;
            for (Future<Integer> future : accepted) {
                completed += future.get();
            }
            System.out.println(label + ": results=" + completed);
        } finally {
            release.countDown();
            pool.shutdownNow();
            if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Executor did not terminate");
            }
        }
    }
}
```

Chạy:

```shell
javac --release 17 QueuePolicyDemo.java
java QueuePolicyDemo
```

Stdout:

```text
bounded: poolSize=2, queueSize=1, accepted=3, rejected=1
bounded: results=3
unbounded: poolSize=1, queueSize=3, accepted=4, rejected=0
unbounded: results=4
handoff: poolSize=2, queueSize=0, accepted=2, rejected=2
handoff: results=2
```

Cách đọc:

- **Bounded:** việc thứ hai chờ, việc thứ ba tạo luồng bổ sung vì hàng đợi đã đầy, việc thứ tư bị từ chối.
- **Unbounded:** sau luồng core, ba việc tiếp theo vẫn xếp được vào hàng đợi nên không tạo luồng thứ hai.
- **Handoff:** không có vùng lưu chờ; việc thứ hai tạo luồng bổ sung, hai việc sau không còn nơi tiếp nhận.

Mã dùng chốt để giữ các luồng bận trước lúc đọc số đo. Nó không kết luận số đo tương tự sẽ luôn ổn định trong một ứng dụng có tác vụ liên tục đến và hoàn tất. Quy tắc phối hợp hàng đợi/core/max mới là điều cần áp dụng. [Tài liệu ThreadPoolExecutor: Queuing](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)

## 8. FIFO của hàng đợi không bảo đảm FIFO của toàn bộ bộ thực thi

Trong trường hợp bounded của thí nghiệm, việc thứ hai ở hàng đợi, còn việc thứ ba được giao trực tiếp cho luồng bổ sung. Việc thứ ba vì thế có thể bắt đầu trước việc thứ hai.

Ngay cả khi mọi tác vụ đều đi qua một hàng đợi FIFO, nhiều luồng có thể mất thời gian xử lý khác nhau; thứ tự hoàn thành vẫn có thể đảo.

Tùy chọn `fair=true` của ArrayBlockingQueue hoặc SynchronousQueue nói về quyền truy cập của các luồng đang chờ theo hợp đồng hàng đợi. Nó không làm mọi tác vụ nghiệp vụ có cùng độ trễ hay hoàn thành theo số thứ tự.

Nếu nghiệp vụ bắt buộc xử lý lệnh tuần tự, hãy thiết kế ranh giới tuần tự hóa riêng; không chỉ bật fairness rồi coi yêu cầu đã được đáp ứng.

## 9. Hàng đợi lớn đổi đợt tải ngắn thành thời gian chờ

Một vùng đệm có thể hấp thụ một đợt yêu cầu ngắn để bộ luồng xử lý dần. Nhưng nếu tốc độ nhận duy trì cao hơn tốc độ xử lý, hàng đợi chỉ trì hoãn thời điểm bộc lộ quá tải.

Ví dụ giả định nhận 150 tác vụ/giây nhưng chỉ xử lý bền vững 100 tác vụ/giây. Khi tình trạng kéo dài, phần việc chờ có xu hướng tăng khoảng 50 tác vụ mỗi giây. Đó là phép tính mô hình để suy luận tải, không phải con số hiệu năng của Java.

Cần tính cả:

- Bộ nhớ mà tác vụ chờ đang giữ.
- Thời gian chờ trước khi bắt đầu xử lý.
- Khả năng kết quả đã hết giá trị khi tới lượt.
- Hạn mức kết nối và tốc độ của tài nguyên bên ngoài.
- Chính sách phản hồi khi không thể nhận thêm.

Tăng queue capacity có thể giảm số lần bị từ chối trong đợt tải ngắn, nhưng cũng có thể làm người dùng chờ lâu hơn. Giảm queue capacity có thể tạo cơ hội mở rộng luồng sớm hơn, đồng thời làm từ chối xuất hiện sớm khi đã đạt max.

## 10. SynchronousQueue không tự chữa mọi quan hệ phụ thuộc

Chuyển giao trực tiếp có thể giúp bộ thực thi nhận ra cần thêm luồng khi các luồng hiện tại bận. Nhưng nếu max hữu hạn đã hết vị trí, tác vụ con vẫn có thể bị từ chối.

Nếu một tác vụ cha giữ luồng rồi chờ tác vụ con trên cùng bộ thực thi, hãy kiểm tra quan hệ chờ. Thay hàng đợi không tự chứng minh thiết kế không kẹt.

Đặt max rất lớn để mọi yêu cầu đều có thể tạo thêm luồng cũng không phải nguồn tài nguyên vô tận. Luồng, bộ nhớ, kết nối và CPU vẫn có giới hạn.

Chọn SynchronousQueue khi ý định là chuyển ngay cho bên xử lý hoặc phản hồi theo chính sách khi không có khả năng tiếp nhận, đồng thời đặt giới hạn và quan sát tải phù hợp.

## 11. Không biến việc kiểm tra queue thành quyết định tiếp nhận riêng

Các biểu thức `size()` và `remainingCapacity()` hữu ích để quan sát. Nhưng giữa lúc kiểm tra còn chỗ và lúc gửi, một luồng khác có thể đã sử dụng vị trí đó.

Với SynchronousQueue, `size() == 0` ngay cả khi toàn bộ luồng làm việc đang bận. Không dùng riêng queue size để kết luận hệ thống rảnh.

Gửi công việc qua `execute` hoặc `submit`, rồi xử lý từ chối theo chính sách. Không lấy `pool.getQueue().put(task)` làm cách tránh bị từ chối: nó bỏ qua đường kiểm tra vòng đời và tạo luồng của bộ thực thi, có thể làm công việc chờ mà không có khả năng thực hiện đúng.

Hàng đợi cũng không tự đảm bảo công việc bị hủy được lấy ra ngay. Các phần tử bao đã hủy có thể cần cơ chế dọn phù hợp với lớp triển khai và tải thực tế.

## 12. Chọn hàng đợi bằng hợp đồng tải

| Yêu cầu | Hướng suy nghĩ |
| --- | --- |
| Muốn đặt ngân sách việc chờ rõ ràng | Hàng đợi có giới hạn, max hữu hạn và phản hồi quá tải |
| Nguồn công việc hữu hạn, có kiểm soát | Có thể dùng hàng đợi dung lượng lớn nhưng vẫn đo bộ nhớ/độ trễ |
| Muốn chuyển trực tiếp, không lưu việc chờ trong queue | SynchronousQueue với giới hạn luồng và chính sách từ chối |
| Bắt buộc nhận bền vững qua lỗi tiến trình | Cần cơ chế lưu trữ công việc bền vững riêng; queue trong RAM không đủ |

Không loại hàng đợi nào biến bộ thực thi trong bộ nhớ thành hệ thống lưu công việc bền vững. Tiến trình kết thúc có thể làm mất tác vụ chờ; nếu nghiệp vụ cần khả năng phục hồi, đó là một yêu cầu kiến trúc khác.

Khi xem một cấu hình ThreadPoolExecutor, hãy đọc **core, max, loại queue, dung lượng queue và rejection handler cùng nhau**. Bộ thông tin đó mới cho biết ứng dụng tiếp nhận công việc thế nào khi bận.
