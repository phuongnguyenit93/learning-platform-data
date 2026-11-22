# Chọn chờ chặn hoặc chờ bận theo kiểu tải thực tế trong Java

Khi một thread cần chờ một điều kiện, có hai chiến lược phổ biến:

- **Chờ chặn (blocking):** thread tạm ngừng thực thi cho tới khi có tín hiệu, dữ liệu hoặc tài nguyên. Scheduler có thể dành CPU cho thread khác.
- **Chờ bận (busy waiting/spinning):** thread liên tục kiểm tra điều kiện trong một vòng lặp. Thread phản ứng nhanh khi điều kiện đổi nhưng tiêu thụ CPU trong suốt thời gian chờ.

Không có chiến lược tốt nhất cho mọi tải. Chờ chặn thường phù hợp với thời gian chờ dài, không xác định hoặc hệ thống đang bận. Spin chỉ đáng cân nhắc khi thời gian chờ rất ngắn, có thể dự đoán, độ trễ đánh thức quan trọng và CPU còn lõi để chạy thread tạo tín hiệu.

Java cung cấp các primitive đồng bộ để chờ chặn và từ Java 9 có `Thread.onSpinWait()` làm gợi ý cho vòng spin. Phương thức này không tự đồng bộ dữ liệu, không nhường CPU như `yield()` và cũng không đưa thread vào trạng thái chờ chặn.

## 1. Hai chiến lược chờ

### Chờ chặn

Thread gọi một API chờ. Khi điều kiện chưa thỏa, API không tiếp tục chạy vòng lặp kiểm tra trong Java code. Thread có thể bị park hoặc chờ trên cơ chế đồng bộ của JVM/hệ điều hành.

Ví dụ:

~~~java
BlockingQueue<Job> queue = new ArrayBlockingQueue<>(100);
Job job = queue.take();
~~~

Nếu queue rỗng, `take()` chờ cho tới khi có phần tử hoặc thread bị interrupt. Trong thời gian chờ, thread không liên tục đọc queue để kiểm tra.

Ưu điểm:

- Không đốt CPU liên tục khi chờ lâu.
- Phù hợp với thời gian chờ không xác định hoặc phụ thuộc I/O, người dùng, mạng và công việc khác.
- Cho phép scheduler dùng CPU cho thread đang có việc.
- Thường giúp tăng thông lượng tổng thể khi số thread chờ lớn.

Chi phí:

- Đánh thức thread có độ trễ do scheduler, runtime và cơ chế đồng bộ.
- Chuyển trạng thái runnable/blocked có thể phát sinh chi phí lập lịch và chuyển ngữ cảnh.
- Khi sự kiện đến cực nhanh, chi phí park rồi unpark có thể lớn hơn thời gian thực sự cần chờ.

Không nên hiểu rằng mọi lần chờ chặn đều nhất thiết gây một system call hoặc context switch ngay lập tức. Chi tiết phụ thuộc JVM, hệ điều hành, primitive và trạng thái scheduler.

### Chờ bận (spin)

Thread liên tục kiểm tra một điều kiện cho tới khi điều kiện đúng:

~~~java
while (!ready) {
    Thread.onSpinWait();
}
~~~

Thread vẫn chạy và tiêu thụ CPU trong vòng lặp. Khi điều kiện thay đổi, nó có thể nhận biết ngay ở lần đọc kế tiếp mà không cần chờ scheduler đánh thức.

Ưu điểm:

- Có thể giảm độ trễ khi thời gian chờ rất ngắn.
- Tránh chi phí park/unpark nếu điều kiện thay đổi gần như tức thời.
- Có thể phù hợp với một số cấu trúc đồng bộ mức thấp, nơi thread giữ CPU trong một khoảng rất ngắn.

Chi phí và rủi ro:

- Dùng CPU liên tục dù không có công việc hữu ích.
- Có thể làm thread producer chậm hơn nếu spin chiếm lõi CPU mà producer cần.
- Khi có nhiều thread spin, CPU contention làm tăng độ trễ của cả hệ thống.
- Tăng điện năng, nhiệt và tải trong môi trường container/VM.
- Không phù hợp với chờ lâu, chờ I/O hoặc điều kiện có thời điểm hoàn tất không dự đoán được.

Spin không làm điều kiện xảy ra nhanh hơn. Nó chỉ đổi chi phí chờ từ thời gian ngủ/lập lịch sang thời gian CPU.

## 2. Thread.onSpinWait() có tác dụng gì?

Java 9 bổ sung:

~~~java
Thread.onSpinWait();
~~~

Đây là một gợi ý cho runtime và processor rằng thread hiện tại đang ở trong vòng lặp spin. JVM có thể ánh xạ gợi ý này thành chỉ thị phù hợp với kiến trúc CPU hoặc tối ưu cho mẫu chờ bận.

Các điểm cần nhớ:

- Phương thức không có bảo đảm rằng thread sẽ yield, sleep, park hoặc nhường CPU cho thread khác.
- Phương thức không tạo quan hệ happens-before và không cung cấp memory visibility.
- Gọi hay không gọi phương thức không được làm thay đổi tính đúng đắn của thuật toán.
- Có thể gọi trong vòng spin nhiều lần; nếu runtime không có tối ưu phù hợp, lời gọi vẫn có thể không tạo hiệu ứng đáng kể.
- Chỉ dùng khi đã chọn chiến lược spin; không biến một vòng lặp chờ dài thành thiết kế hiệu quả.

Ví dụ:

~~~java
while (!ready) {
    Thread.onSpinWait();
}
~~~

`onSpinWait()` là hint. Điều kiện `ready` vẫn phải được đọc bằng cơ chế có memory semantics thích hợp, ví dụ volatile, AtomicBoolean hoặc VarHandle access mode.

## 3. Điều kiện spin phải được công bố an toàn

Một vòng spin đọc field thường có thể bị tối ưu theo cách không quan sát được thay đổi từ thread khác. Ví dụ sau không an toàn:

~~~java
boolean ready; // field thường, chia sẻ giữa hai thread

while (!ready) {
    Thread.onSpinWait();
}
~~~

Nếu thread khác ghi ready mà không có quan hệ đồng bộ, chương trình có data race. Thread chờ không được bảo đảm nhìn thấy giá trị mới; compiler có thể tối ưu việc đọc theo quy tắc JMM.

Dùng volatile cho cờ đơn giản:

~~~java
private static volatile boolean ready;

// Thread producer
ready = true;

// Thread consumer
while (!ready) {
    Thread.onSpinWait();
}
~~~

Ghi volatile synchronizes-with lần đọc volatile quan sát giá trị đó. Các thao tác ghi trước lần ghi volatile được công bố cho thread đọc.

Có thể dùng AtomicBoolean:

~~~java
AtomicBoolean ready = new AtomicBoolean();

while (!ready.get()) {
    Thread.onSpinWait();
}

// Thread producer
ready.set(true);
~~~

Hoặc dùng VarHandle với access mode acquire/release nếu cần giao thức bộ nhớ cấp thấp. Không chọn plain access chỉ vì vòng lặp cần nhanh; tối ưu vi phạm JMM không phải là tối ưu hợp lệ.

Cũng cần phân biệt visibility với atomicity. Một volatile flag có thể công bố dữ liệu đã ghi trước nó, nhưng không làm một thao tác compound như `count++` trở thành nguyên tử.

## 4. Các API chờ chặn thường dùng

Nên chọn primitive thể hiện trực tiếp điều kiện mà thread cần chờ.

| Nhu cầu | API phù hợp | Hành vi |
|---|---|---|
| Chờ phần tử trong hàng đợi | `BlockingQueue.take()` | Chờ tới khi queue có phần tử |
| Chờ một điều kiện dưới lock | `Condition.await()` | Nhả lock và chờ tín hiệu, sau đó lấy lại lock |
| Chờ monitor | `Object.wait()` | Nhả monitor và chờ `notify`/`notifyAll` hoặc điều kiện khác |
| Chờ một tín hiệu hoàn tất | `CountDownLatch.await()` | Chờ latch về 0 |
| Chờ permit | `Semaphore.acquire()` | Chờ có permit |
| Chờ kết quả tác vụ | `Future.get()` | Chờ kết quả hoặc lỗi |
| Park/unpark mức thấp | `LockSupport.park()` | Park thread cho tới khi được unpark, interrupt hoặc một lần trả về khác |

Các API blocking thường có cơ chế interrupt. Nếu phương thức ném `InterruptedException`, hãy quyết định rõ tầng gọi sẽ truyền tiếp ngoại lệ hay khôi phục trạng thái interrupt:

~~~java
try {
    queue.take();
} catch (InterruptedException ex) {
    Thread.currentThread().interrupt();
    return;
}
~~~

Không nuốt interrupt rồi tiếp tục chờ vô hạn. Interrupt thường được dùng để yêu cầu worker dừng hoặc hủy công việc.

### Chờ condition phải kiểm tra trong vòng lặp

Với `Object.wait()` hoặc `Condition.await()`, luôn kiểm tra lại điều kiện trong vòng lặp:

~~~java
synchronized (lock) {
    while (!ready) {
        lock.wait();
    }
    usePublishedValue();
}
~~~

`wait()` có thể trả về do spurious wakeup, notification dành cho nhiều waiter hoặc một tín hiệu không làm điều kiện mong muốn trở thành đúng. Vòng lặp bảo đảm thread chỉ tiếp tục khi predicate thật sự thỏa mãn.

Với Condition:

~~~java
lock.lock();
try {
    while (!ready) {
        condition.await();
    }
    usePublishedValue();
} finally {
    lock.unlock();
}
~~~

Thread gọi `await()` nhả lock trong lúc chờ và lấy lại lock trước khi phương thức trả về. Bên phát tín hiệu phải cập nhật predicate dưới cùng lock rồi gọi `signal()` hoặc `signalAll()`.

### Không dùng sleep hoặc yield làm cơ chế đồng bộ

- `Thread.sleep()` tạm dừng thread trong một khoảng thời gian; nó không nhả monitor đang giữ và không tạo happens-before với thread khác.
- `Thread.yield()` chỉ là gợi ý cho scheduler. Scheduler có thể bỏ qua gợi ý này.
- Polling bằng `sleep()` có thể tăng độ trễ vì thread chỉ kiểm tra lại sau khoảng ngủ; polling vẫn cần cơ chế visibility đúng.

Nếu có thể biểu diễn sự kiện bằng queue, latch, semaphore hoặc condition, hãy dùng primitive đó thay cho đoán thời gian bằng sleep.

## 5. Khi nào chọn blocking?

Ưu tiên blocking khi:

- Thời gian chờ có thể kéo dài hoặc không dự đoán được.
- Thread chờ thường xuyên hơn thread tạo tín hiệu.
- Ứng dụng có nhiều thread chờ cùng lúc.
- CPU đã bận hoặc cần dành lõi cho producer, request handler và công việc hữu ích.
- Chờ I/O, dữ liệu từ queue, kết quả tác vụ hoặc tín hiệu từ người dùng.
- Tiết kiệm CPU, điện năng và thông lượng tổng thể quan trọng hơn vài microsecond độ trễ đánh thức.

Ví dụ producer-consumer:

~~~java
BlockingQueue<Task> tasks = new ArrayBlockingQueue<>(256);

// Worker
while (!Thread.currentThread().isInterrupted()) {
    Task task = tasks.take();
    process(task);
}

// Producer
tasks.put(nextTask);
~~~

Queue tự điều phối việc chờ khi rỗng và áp lực ngược khi đầy. Producer có thể bị chặn ở `put()` khi queue đạt capacity, nhờ đó tốc độ gửi không vượt mãi khả năng tiêu thụ.

Với I/O, thường nên dùng API blocking phù hợp hoặc API bất đồng bộ. Không spin liên tục chờ socket, file hoặc phản hồi mạng: thời gian chờ có thể kéo dài nhiều bậc độ lớn so với chu kỳ CPU.

## 6. Khi nào cân nhắc busy waiting?

Spin chỉ đáng cân nhắc khi phần lớn điều kiện sau đúng:

- Thời gian chờ thường rất ngắn và có phân bố đo được.
- Độ trễ đánh thức quan trọng hơn chi phí CPU.
- Thread producer có thể chạy song song trên lõi khác.
- Số thread spin nhỏ và được kiểm soát.
- Điều kiện được đọc bằng volatile, atomic hoặc VarHandle với memory ordering đúng.
- Vòng spin có đường thoát rõ ràng, kể cả interrupt hoặc timeout nếu cần.
- Benchmark trên phần cứng và tải gần production cho thấy lợi ích thực.

Ví dụ một cờ báo sẵn sàng cho thao tác rất ngắn:

~~~java
private static volatile boolean ready;

static void awaitReady() {
    while (!ready) {
        if (Thread.currentThread().isInterrupted()) {
            return;
        }
        Thread.onSpinWait();
    }
}
~~~

Nếu thời gian chờ kéo dài hơn dự kiến, vòng spin vẫn tiếp tục tiêu thụ CPU. Bản thân `onSpinWait()` không tự chuyển sang blocking.

Không nên dùng spin chỉ vì muốn tránh synchronized. Lock hiện đại thường có tối ưu nội bộ; tự viết spin lock có thể kém công bằng, gây starvation và khó xử lý cancellation.

## 7. Chờ bận, chờ chặn và chiến lược lai

Trong một số tải rất nhạy độ trễ, có thể spin trong một khoảng ngắn rồi chuyển sang blocking. Ý tưởng:

1. Thử kiểm tra condition một số lần giới hạn.
2. Nếu condition đã đúng, tiếp tục ngay.
3. Nếu vẫn chưa đúng, đăng ký chờ bằng primitive phù hợp.
4. Sau khi được đánh thức, kiểm tra lại condition trong vòng lặp.

Chiến lược lai chỉ có ích nếu phần lớn sự kiện đến trong khoảng spin ngắn và phần còn lại được xử lý bằng blocking an toàn. Nó phức tạp hơn vì phải tránh race giữa lần kiểm tra cuối và thời điểm đăng ký chờ.

Không tự ghép spin và park bằng một protocol thiếu đồng bộ. Các cấu trúc đồng bộ của JDK thường đã xử lý các cuộc đua này. Nếu cần một thuật toán lai mức thấp, hãy dựa vào primitive có hợp đồng rõ ràng và kiểm thử concurrency chuyên biệt.

### Bounded spin

Nếu tự viết một vòng spin, đặt giới hạn rõ ràng:

~~~java
for (int attempt = 0; attempt < MAX_SPINS; attempt++) {
    if (ready) {
        return;
    }
    Thread.onSpinWait();
}

// Sau giới hạn, chuyển sang cơ chế chờ đã đồng bộ.
awaitWithCondition();
~~~

Đây chỉ là phác thảo: `awaitWithCondition()` phải phối hợp đúng với producer để không bỏ lỡ tín hiệu giữa lần kiểm tra cuối và lúc bắt đầu chờ. Không thể thay thế phần đồng bộ đó bằng một lời gọi sleep tùy ý.

## 8. Tác động của tải CPU và số lõi

Cùng một vòng spin có thể tốt trên máy nhàn rỗi nhưng rất xấu khi CPU bão hòa.

### CPU còn lõi rảnh

Nếu consumer spin trên một lõi và producer chạy trên lõi khác, producer có thể cập nhật condition mà không bị consumer lấy mất thời gian CPU của nó. Khi đó spin ngắn có thể giảm độ trễ nhận biết.

### CPU chỉ có một lõi hoặc bị oversubscribe

Nếu consumer spin chiếm CPU, producer có thể không được scheduler chạy đủ sớm để cập nhật condition. Consumer vừa đốt CPU vừa trì hoãn chính sự kiện mà nó đang chờ.

Trong container, số CPU được cấp có thể thấp hơn số logical processor của máy host. Trong VM, thời gian CPU có thể bị chia sẻ với workload khác. Không nên dựa vào số lõi vật lý nhìn thấy bên ngoài môi trường triển khai.

### Nhiều consumer cùng spin

Nhiều vòng lặp spin tạo áp lực lên cache coherence và memory subsystem. Nếu tất cả cùng đọc một biến được ghi thường xuyên, việc truyền cache line có thể làm producer và consumer chậm hơn.

Cần đo cả CPU utilization, throughput và latency; chỉ nhìn thời gian phản hồi của một thread có thể che giấu chi phí hệ thống.

## 9. Công bằng, starvation và cancellation

Spin không tự tạo fairness. Thread có ưu tiên cao hoặc được scheduler cấp CPU nhiều hơn có thể tiếp tục chạy, trong khi thread tạo tín hiệu bị trì hoãn. Một vòng spin không có timeout cũng có thể chạy mãi nếu producer lỗi hoặc sự kiện không bao giờ đến.

Đối với mọi cơ chế chờ, cần xác định:

- Điều kiện nào kết thúc chờ.
- Có deadline hoặc timeout hay không.
- Thread có thể bị interrupt/cancel không.
- Khi producer kết thúc mà không phát tín hiệu, waiter được giải phóng thế nào.
- Có giữ lock hoặc tài nguyên cần thiết cho producer trong lúc chờ không.

Với blocking API, xử lý `InterruptedException` đúng cách. Với spin, tự kiểm tra `Thread.currentThread().isInterrupted()` hoặc một cancellation flag có visibility phù hợp. `Thread.onSpinWait()` không kiểm tra interrupt thay cho ứng dụng.

Không spin trong khi giữ một lock mà thread tạo tín hiệu cần lấy. Đây là cách dễ tự tạo deadlock hoặc starvation.

## 10. Đo lường trước khi chọn

Không chọn chiến lược chỉ dựa trên một lần chạy thử. So sánh bằng benchmark phù hợp với workload thực tế:

- **Wait duration:** phân bố thời gian từ lúc bắt đầu chờ đến khi condition đúng.
- **Latency:** đặc biệt p95, p99 và tail latency.
- **CPU utilization:** CPU time tiêu thụ trong lúc chờ.
- **Throughput:** số công việc hoàn tất trên giây.
- **Context switches và scheduling delay:** chi phí đánh thức và chờ được chạy.
- **Power/thermal:** quan trọng với máy chủ mật độ cao, laptop và thiết bị nhúng.
- **Contention:** số thread cùng chờ hoặc cùng cập nhật condition.

Dùng JMH hoặc một harness benchmark được kiểm soát để đo microbenchmark; sau đó xác nhận trong môi trường tích hợp với tải, CPU quota và số subscriber/thread thực tế. Tránh kết luận từ benchmark chỉ đo một thread trên máy rảnh.

## 11. Ví dụ Java chạy được: BlockingQueue và spin với volatile

Chương trình sau minh họa hai kiểu chờ độc lập:

- Consumer dùng `BlockingQueue.take()` để chờ một công việc.
- Consumer khác spin trên cờ volatile; producer công bố payload trước khi đặt cờ. `Thread.onSpinWait()` chỉ là hint cho vòng spin.

~~~java
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.BlockingQueue;

public class WaitStrategyExample {
    private static volatile boolean ready;
    private static int payload;

    public static void main(String[] args) throws InterruptedException {
        BlockingQueue<String> queue = new ArrayBlockingQueue<>(1);

        Thread blockingConsumer = new Thread(() -> {
            try {
                System.out.println("blocking received=" + queue.take());
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
            }
        });

        blockingConsumer.start();
        queue.put("job");
        blockingConsumer.join();

        Thread spinningConsumer = new Thread(() -> {
            while (!ready) {
                if (Thread.currentThread().isInterrupted()) {
                    return;
                }
                Thread.onSpinWait();
            }
            System.out.println("spin received=" + payload);
        });

        Thread producer = new Thread(() -> {
            payload = 42;
            ready = true;
        });

        spinningConsumer.start();
        producer.start();

        producer.join();
        spinningConsumer.join();
    }
}
~~~

Lưu trong tệp `WaitStrategyExample.java`, biên dịch và chạy với Java 17 trở lên:

~~~shell
javac --release 17 -Xlint:all WaitStrategyExample.java
java WaitStrategyExample
~~~

Kết quả stdout chính xác:

~~~text
blocking received=job
spin received=42
~~~

Giải thích:

1. Consumer đầu gọi `take()`. Nếu queue rỗng, nó chờ chặn cho tới khi producer đưa job vào queue.
2. Consumer thứ hai đọc volatile `ready` liên tục. Trong lúc cờ false, `onSpinWait()` gợi ý runtime/CPU tối ưu vòng spin.
3. Producer ghi payload trước rồi ghi volatile `ready = true`.
4. Khi consumer đọc được true, volatile write/read tạo quan hệ synchronizes-with. Vì vậy, nó nhìn thấy payload bằng 42 dù payload là field thường.
5. `join()` giúp main chờ cả hai thread kết thúc trước khi chương trình thoát.

Ví dụ minh họa tính đúng đắn và cú pháp API; nó không chứng minh spin nhanh hơn blocking. Muốn so sánh hiệu năng, cần benchmark riêng với thời gian chờ, tải CPU và phần cứng phù hợp.

## 12. Những lỗi thường gặp

- **Spin trên field thường được chia sẻ:** có data race và không bảo đảm nhìn thấy cập nhật; dùng volatile, atomic hoặc VarHandle.
- **Cho rằng onSpinWait nhường CPU:** đây chỉ là hint, không phải yield, sleep hay park.
- **Spin cho thời gian chờ không xác định:** CPU có thể bị tiêu thụ vô ích trong thời gian dài.
- **Dùng sleep để thay thế tín hiệu:** sleep tạo độ trễ polling và không tự tạo happens-before.
- **Dùng yield để chờ điều kiện:** scheduler có thể bỏ qua yield; không có bảo đảm waiter sẽ được đánh thức đúng lúc.
- **Giữ lock trong lúc spin:** có thể ngăn producer lấy lock để cập nhật condition.
- **Quên interrupt hoặc timeout:** vòng spin có thể chạy mãi khi sự kiện không bao giờ đến.
- **Giả định volatile làm thao tác compound nguyên tử:** volatile bảo đảm visibility/ordering, không tự làm count++ nguyên tử.
- **Dùng spin trên máy CPU bão hòa:** consumer có thể tranh CPU với producer và làm cả hai chậm hơn.
- **Tăng số thread spin để giảm latency:** oversubscription có thể tăng contention, scheduling delay và tail latency.
- **Dùng một benchmark nhỏ làm kết luận production:** cần đo trên tải, CPU quota và phần cứng gần môi trường thật.
- **Tự viết hybrid wait thiếu protocol:** có thể bỏ lỡ tín hiệu giữa lần kiểm tra condition và lúc đăng ký blocking; dùng primitive JDK hoặc chứng minh đầy đủ thuật toán.

## 13. Tài liệu tham khảo chính thức

- [Thread — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/Thread.html): `onSpinWait`, sleep, yield, interrupt, start và join.
- [BlockingQueue — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/BlockingQueue.html): các thao tác chờ chặn và memory consistency effects.
- [LockSupport — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/util/concurrent/locks/LockSupport.html): park/unpark và các lưu ý về spurious return.
- [JEP 285: Spin-Wait Hints](https://openjdk.org/jeps/285): mục tiêu và thiết kế của Thread.onSpinWait trong Java 9.
- [Java Language Specification — Chapter 17](https://docs.oracle.com/javase/specs/jls/se26/html/jls-17.html): Java Memory Model, volatile và happens-before.