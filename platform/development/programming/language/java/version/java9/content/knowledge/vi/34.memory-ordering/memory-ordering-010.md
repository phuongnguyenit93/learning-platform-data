# Thread.onSpinWait chỉ là gợi ý cho vòng chờ bận

## Mục tiêu

- Hiểu \`Thread.onSpinWait()\` được bổ sung trong Java 9 và mục đích của hint.
- Phân biệt spin-wait với nhường CPU hoặc block thread.
- Hiểu vì sao hint không thay thế \`volatile\`, atomic variable hay synchronization.
- Viết vòng chờ bận có điều kiện thoát và visibility đúng theo Java Memory Model.
- Chọn giữa spin, hybrid waiting và API signaling/blocking.
- Tránh giả định hint luôn cải thiện hiệu năng hoặc phát ra một instruction cụ thể.

## 1. Thread.onSpinWait() là gì?

Java 9 bổ sung method tĩnh:

~~~java
Thread.onSpinWait();
~~~

Đây là **hint cho runtime** rằng thread hiện tại đang ở trong vòng chờ bận (busy-wait hoặc spin-wait). Runtime có thể dùng gợi ý này để cải thiện cách thực thi vòng lặp trên nền tảng hiện tại.

~~~java
while (!ready) {
    Thread.onSpinWait();
}
~~~

Thread liên tục kiểm tra điều kiện \`ready\`. Khi điều kiện thành \`true\`, vòng lặp kết thúc.

\`onSpinWait()\` không chờ một khoảng thời gian xác định, không bảo đảm thread được lập lịch sớm hơn, không nhường CPU như \`Thread.yield()\` và không block như \`Thread.sleep()\`, \`Object.wait()\`, \`LockSupport.park()\` hoặc \`CountDownLatch.await()\`. Runtime có thể bỏ qua hint; chương trình vẫn phải đúng khi method không tạo tác động quan sát được.

Hãy xem đây là gợi ý tối ưu hóa cho vòng chờ đã được thiết kế đúng, không phải cơ chế đồng bộ hóa hay API chờ độc lập.

## 2. Busy-wait và tác động của hint

Trong vòng spin, thread vẫn chạy và kiểm tra điều kiện lặp đi lặp lại. Nó không chuyển sang trạng thái chờ chỉ vì điều kiện chưa thỏa mãn, nên có thể tiêu thụ CPU trong suốt thời gian chờ.

Khi thêm \`Thread.onSpinWait()\` vào thân vòng lặp, runtime biết thread đang spin. Trên một số CPU/runtime, hint có thể được ánh xạ thành lệnh pause hoặc hành vi tương tự. Cách triển khai phụ thuộc nền tảng và không được Java API bảo đảm.

Hint có thể giúp CPU xử lý vòng spin hiệu quả hơn, giảm một số tác động của polling liên tục hoặc cải thiện hiệu năng trên một số kiến trúc. Không có bảo đảm rằng nó luôn giảm độ trễ, điện năng hay tăng throughput. Cần đo trên workload và môi trường thực tế.

## 3. Hint không tạo ra memory visibility

Đây là điểm quan trọng nhất khi sử dụng method này.

\`Thread.onSpinWait()\` không phải volatile read/write, memory fence hoặc thao tác tạo quan hệ happens-before. Nó không làm cho một thread nhìn thấy thay đổi của thread khác.

Ví dụ sai khi chia sẻ cờ thông thường giữa hai thread:

~~~java
class State {
    boolean ready;
}

while (!state.ready) {
    Thread.onSpinWait();
}
~~~

Nếu thread khác ghi \`state.ready = true\`, vòng lặp trên không có cơ chế bảo đảm thread đang chờ nhìn thấy giá trị mới. Compiler/runtime có thể tối ưu việc đọc theo Java Memory Model.

Dùng một cơ chế công bố trạng thái có semantics phù hợp, ví dụ \`volatile\`:

~~~java
class State {
    volatile boolean ready;
}

while (!state.ready) {
    Thread.onSpinWait();
}
~~~

Hoặc \`AtomicBoolean\`:

~~~java
AtomicBoolean ready = new AtomicBoolean();

while (!ready.get()) {
    Thread.onSpinWait();
}
~~~

Ở đây, volatile read/write hoặc atomic access cung cấp semantics visibility. \`onSpinWait()\` chỉ là hint nằm trong vòng lặp. Không thay volatile/atomic bằng biến plain với lý do đã gọi hint; hint không sửa được data race.

## 4. Ví dụ đầy đủ: một thread công bố trạng thái

Ví dụ dùng cờ \`volatile\` để công bố trạng thái. \`CountDownLatch\` chỉ giúp main thread biết worker đã tới điểm bắt đầu vòng chờ; nó không thay thế volatile flag trong vòng spin.

Tạo file **OnSpinWaitDemo.java**:

~~~java
import java.util.concurrent.CountDownLatch;

public class OnSpinWaitDemo {

    private static volatile boolean ready;

    public static void main(String[] args) throws InterruptedException {
        CountDownLatch enteringSpin = new CountDownLatch(1);

        Thread worker = new Thread(() -> {
            enteringSpin.countDown();

            while (!ready) {
                Thread.onSpinWait();
            }

            System.out.println("worker observed ready = " + ready);
        }, "spin-worker");

        worker.start();
        enteringSpin.await();

        // Volatile write công bố trạng thái cho worker.
        ready = true;

        worker.join();
        System.out.println("worker finished = " + !worker.isAlive());
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~bash
javac --release 17 -Xlint:all -d out OnSpinWaitDemo.java
java -cp out OnSpinWaitDemo
~~~

Output chính xác:

~~~text
worker observed ready = true
worker finished = true
~~~

Thứ tự output ổn định vì main thread gọi \`join()\` trước khi in dòng thứ hai. Giá trị \`ready\` được chia sẻ bằng volatile. Worker có thể đã kiểm tra cờ trước hoặc sau khi main thread ghi \`true\`; trong cả hai trường hợp, nó không phụ thuộc vào tác động của hint để nhìn thấy giá trị mới.

Ví dụ biên dịch được với \`--release 9\`, vì \`Thread.onSpinWait()\` có từ Java 9.

## 5. Phân biệt onSpinWait với yield, sleep và park

| API | Hành vi |
|---|---|
| \`Thread.onSpinWait()\` | Hint cho runtime trong busy-wait loop; không block |
| \`Thread.yield()\` | Gợi ý scheduler rằng thread sẵn sàng nhường lượt; scheduler có thể bỏ qua |
| \`Thread.sleep(time)\` | Tạm ngừng thực thi trong khoảng thời gian yêu cầu, subject to scheduling/timing |
| \`LockSupport.park()\` | Có thể đưa thread vào trạng thái parked cho tới khi được unpark, bị interrupt hoặc được đánh thức theo API |
| \`CountDownLatch.await()\` | Chờ điều kiện đồng bộ cho tới khi latch mở hoặc thread bị interrupt |
| \`Object.wait()\` | Chờ trên monitor và giải phóng monitor trong lúc chờ |

\`yield()\` cũng là hint, nhưng hướng tới scheduler. \`onSpinWait()\` hướng tới runtime/processor khi thread đang chủ động spin. Không dùng hai method này thay thế cho nhau.

Nếu event có thể mất thời gian đáng kể hoặc không có giới hạn rõ ràng, API chặn hoặc signaling thường phù hợp hơn spin liên tục.

## 6. Khi nào spin-wait có thể phù hợp?

Spin-wait đôi khi hữu ích khi:

- Thời gian chờ dự kiến rất ngắn và có thể dự đoán.
- Thread chờ cần phản hồi với độ trễ thấp.
- Chi phí chuyển sang trạng thái blocked rồi đánh thức lại lớn hơn thời gian chờ dự kiến.
- Có kiểm soát số thread spin, tải CPU và contention.
- Điều kiện được kiểm tra bằng volatile, atomic hoặc cơ chế đồng bộ hóa hợp lệ.

Spin-wait không phải lựa chọn mặc định. Nếu thread chờ lâu, nó có thể chiếm core mà công việc hữu ích khác cần dùng, tăng điện năng/nhiệt, cạnh tranh CPU với thread làm điều kiện thành true và giảm throughput khi có nhiều waiter. Khi hệ thống oversubscribed, spin có thể làm độ trễ xấu hơn.

Vòng spin vô hạn cũng có thể khiến ứng dụng không thể dừng nếu điều kiện không bao giờ thay đổi. Luôn xác định ai cập nhật điều kiện và cách hủy hoặc timeout việc chờ.

## 7. Kết hợp spin với cơ chế chờ khác

Nếu độ dài chờ không chắc chắn, có thể spin trong một khoảng giới hạn rồi chuyển sang cơ chế chờ khác. Ví dụ minh họa polling có giới hạn trước khi dùng \`LockSupport.parkNanos\`:

~~~java
int spins = 0;

while (!ready) {
    if (spins++ < 100) {
        Thread.onSpinWait();
    } else {
        LockSupport.parkNanos(100_000L);
    }

    if (Thread.currentThread().isInterrupted()) {
        throw new IllegalStateException("waiting was interrupted");
    }
}
~~~

Đây là phác thảo chính sách. Trong ứng dụng thực tế:

- \`parkNanos\` có thể trả về sớm; luôn kiểm tra lại điều kiện.
- Nó có thể trả về do interrupt hoặc permit đã được cấp trước đó.
- Cần giao thức đánh thức phù hợp, chẳng hạn thread sản xuất gọi \`LockSupport.unpark(waiter)\`.
- Cần xác định timeout, cancellation và xử lý interrupt theo hợp đồng API.
- Số vòng spin và thời gian park phải được đo, không chọn tùy tiện theo một máy duy nhất.

Nếu có thể dùng \`CountDownLatch\`, \`Semaphore\`, \`Condition\`, \`BlockingQueue\` hoặc API đồng bộ hóa cấp cao hơn, hãy ưu tiên cơ chế thể hiện trực tiếp điều kiện chờ và signaling. Các API đó thường dễ bảo trì hơn vòng spin tự xây dựng.

## 8. Spin loop trong thuật toán atomic

\`onSpinWait()\` cũng có thể xuất hiện trong vòng lặp thử cập nhật nguyên tử:

~~~java
while (!atomic.compareAndSet(expected, update)) {
    Thread.onSpinWait();
}
~~~

Mỗi lần CAS thất bại, thread thử lại sau một hint. Hint không làm CAS thành công và không bảo đảm giảm contention.

Cần kiểm tra lại giá trị mong đợi hoặc tính toán lại \`update\` nếu thuật toán yêu cầu. Không tái sử dụng một giá trị \`expected\` cũ vô hạn nếu giá trị hiện tại có thể thay đổi.

Với thuật toán lock-free, hãy phân biệt:

- **Correctness:** do CAS/atomic semantics, invariants và memory ordering quyết định.
- **Progress:** do thuật toán và lịch thực thi quyết định.
- **Performance hint:** \`onSpinWait()\` có thể ảnh hưởng hiệu năng trên một số nền tảng, nhưng không thay đổi tính đúng đắn.

Một vòng CAS có thể bị starvation dù có gọi \`onSpinWait()\`. Nếu contention cao, cân nhắc backoff, giới hạn retry hoặc chuyển sang lock/queue phù hợp.

## 9. Quy tắc thiết kế vòng chờ bận

Trước khi dùng \`Thread.onSpinWait()\`, hãy trả lời:

1. Điều kiện nào kết thúc vòng lặp?
2. Thread nào cập nhật điều kiện?
3. Cơ chế nào bảo đảm visibility và ordering?
4. Điều kiện có thể không bao giờ xảy ra không?
5. Có timeout hoặc cancellation không?
6. Có bao nhiêu thread có thể spin cùng lúc?
7. Thời gian chờ dự kiến ngắn đến mức nào?
8. Có API blocking/signaling nào diễn đạt bài toán tốt hơn?
9. Đã đo CPU usage, latency và throughput trên môi trường mục tiêu chưa?

Nếu chưa trả lời được câu hỏi về điều kiện thoát và memory visibility, chưa nên đưa spin loop vào code production.

## 10. Lỗi thường gặp

### Nghĩ onSpinWait làm thread chờ hoặc ngủ

Method không block thread và không đặt thời gian chờ. Vòng lặp tiếp tục kiểm tra điều kiện.

### Nghĩ onSpinWait tạo memory fence

Method không cung cấp volatile semantics hoặc happens-before. Dùng volatile, atomic hoặc cơ chế đồng bộ hóa đúng.

### Dùng biến plain làm cờ giữa nhiều thread

Vòng lặp có thể không quan sát được cập nhật. Dùng một biến có semantics visibility phù hợp.

### Dùng spin cho thao tác I/O hoặc chờ dài

Thread có thể chiếm CPU trong khi chờ network, disk, user input hoặc event không xác định thời điểm. Dùng API asynchronous hoặc blocking phù hợp.

### Giả định hint luôn phát ra lệnh PAUSE

Runtime và CPU được tự do triển khai hoặc bỏ qua hint. Không viết logic phụ thuộc vào một instruction cụ thể.

### Dùng onSpinWait thay cho yield

Hai hint có mục đích khác nhau. \`yield\` hướng tới scheduler; \`onSpinWait\` hướng tới runtime/processor trong vòng chờ bận.

### Quên điều kiện thoát và cancellation

Một vòng spin vô hạn có thể giữ CPU mãi mãi. Thiết kế timeout, interrupt hoặc cờ hủy nếu bài toán yêu cầu.

### Tin rằng onSpinWait luôn làm chương trình nhanh hơn

Tác động phụ thuộc workload, CPU, runtime và mức contention. Đo trước khi kết luận.

## 11. Checklist

- [ ] Đã hiểu \`Thread.onSpinWait()\` là hint được bổ sung trong Java 9.
- [ ] Đã đặt method bên trong vòng busy-wait có điều kiện rõ ràng.
- [ ] Đã dùng volatile/atomic hoặc synchronization để bảo đảm visibility.
- [ ] Không dựa vào hint như memory fence hoặc cơ chế scheduling.
- [ ] Đã đánh giá thời gian chờ, số thread spin và contention.
- [ ] Đã có chiến lược timeout/cancellation khi cần.
- [ ] Đã cân nhắc latch, condition, queue, park hoặc API blocking.
- [ ] Đã đo latency, throughput và CPU usage trên môi trường mục tiêu.
- [ ] Đã kiểm tra hành vi khi runtime bỏ qua hint.
- [ ] Đã biên dịch ví dụ bằng Java 9+.

## 12. Tài liệu tham khảo

- [Java SE 17 API: Thread.onSpinWait](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Thread.html#onSpinWait())
- [JEP 285: Spin-Wait Hints](https://openjdk.org/jeps/285)

