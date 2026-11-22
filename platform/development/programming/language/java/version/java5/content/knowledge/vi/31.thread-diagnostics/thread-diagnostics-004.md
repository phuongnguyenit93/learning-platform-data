# Đọc stack trace của luồng để xác định vị trí chờ

## 1. Trạng thái cho biết kiểu chờ; stack trace cho biết đường đi tới đó

Thấy một luồng ở `WAITING` chỉ mới biết nó đang chờ theo một cơ chế không chỉ định thời hạn. Ta còn cần biết nó đang đợi phần tử hàng đợi, kết quả tác vụ, điều kiện của khóa hay một luồng khác kết thúc.

**Stack trace của luồng** là danh sách các khung gọi phương thức (stack frame) tại thời điểm được lấy mẫu. Đọc đúng danh sách này giúp lần từ thao tác chờ ở tầng JVM/thư viện về phương thức ứng dụng đã dẫn luồng tới đó.

Mục tiêu thực tế không phải tìm một dòng có chữ “wait” rồi kết luận chương trình treo. Một kết quả chẩn đoán có ích cần trả lời:

- Luồng đang dừng ở cơ chế chờ nào?
- API hoặc tài nguyên cấp cao nào yêu cầu nó chờ?
- Đoạn mã ứng dụng nào gọi vào API đó?
- Điều kiện nào sẽ cho phép luồng tiếp tục, và ai có trách nhiệm tạo điều kiện ấy?
- Việc chờ có phù hợp với hoạt động mong đợi hay đang kéo dài bất thường?

Bài học dùng các API chẩn đoán hiện hành. Ví dụ chạy bằng Java 17 trở lên và tạo tình huống chờ có kiểm soát; không yêu cầu can thiệp vào một ứng dụng đang vận hành.

## 2. Cách đọc một stack từ trên xuống

### 2.1. Frame đầu là điểm thực thi gần nhất được ghi nhận

Trong một stack thông thường, dòng đầu gần điểm thực thi đang được quan sát nhất. Các dòng phía dưới lần lượt là các phương thức gọi dẫn tới điểm đó.

Ví dụ sau là **chuỗi phương thức đã chuẩn hóa để giải thích**, không phải nguyên văn đầu ra của một JDK cụ thể:

```text
jdk.internal.misc.Unsafe.park
java.util.concurrent.locks.LockSupport.park
java.util.concurrent.locks.AbstractQueuedSynchronizer$ConditionObject.await
java.util.concurrent.ArrayBlockingQueue.take
demo.JobWorker.awaitJob
demo.JobWorker.run
java.lang.Thread.run
```

Đọc theo hai hướng:

- Từ trên xuống: cơ chế park → condition → thao tác lấy từ hàng đợi → phương thức ứng dụng.
- Từ dưới lên: luồng chạy worker → worker gọi `awaitJob` → `awaitJob` gọi `take` → hàng đợi phải chờ nên dùng cơ chế ở tầng dưới.

Dừng ở `Unsafe.park` sẽ bỏ lỡ ý nghĩa thật: một worker đang chờ lấy công việc từ hàng đợi. Nếu hàng đợi đang trống và worker được thiết kế chờ việc mới, đây có thể là trạng thái nhàn bình thường.

### 2.2. Class, phương thức, tệp và số dòng có vai trò khác nhau

Một dòng minh họa:

```text
at demo.JobWorker.awaitJob(JobWorker.java:42)
```

cho biết lớp, phương thức và thông tin vị trí nguồn nếu có. Số dòng 42 trong ví dụ chỉ là minh họa; khi chẩn đoán phải mở đúng phiên bản mã nguồn tương ứng với bản ứng dụng đang chạy.

`StackTraceElement` cung cấp các thành phần như tên lớp, tên phương thức, tệp nguồn, số dòng, thông tin module và dấu hiệu native. Thông tin nguồn có thể thiếu; một frame native cũng không có dòng Java để mở trực tiếp. [Tài liệu StackTraceElement](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StackTraceElement.html)

Đừng coi `Native Method` là một lỗi. Nó chỉ cho biết thao tác đang ở phương thức native. Cũng không coi `Unknown Source` là bằng chứng luồng không hoạt động; nó chỉ giới hạn khả năng ánh xạ về nguồn.

### 2.3. Frame ứng dụng đầu tiên thường là điểm bắt đầu điều tra

Tìm frame thuộc mã ứng dụng gần thao tác chờ nhất, rồi đọc phương thức đó và hợp đồng của API được gọi.

Tuy nhiên, “đầu tiên” không nhất thiết là nơi phải sửa. Một hàm tiện ích dùng chung có thể chỉ bao một lời gọi `get()`; frame phía dưới mới cho biết yêu cầu nghiệp vụ nào đang chờ kết quả đó.

Ví dụ:

```text
java.util.concurrent.FutureTask.get
demo.AsyncSupport.awaitResult
demo.ReportService.buildReport
demo.ReportController.download
```

`awaitResult` chỉ ra chỗ thực hiện chờ, còn `buildReport` giúp đặt câu hỏi: kết quả của tác vụ nào, gửi vào executor nào và có đang tự chờ trên nguồn luồng đã cạn không?

## 3. Stack của luồng đang sống khác stack của một ngoại lệ

Một exception stack thường ghi đường gọi tại thời điểm ngoại lệ được tạo hoặc đi qua cơ chế ghi stack. Nó là bằng chứng về một sự kiện đã xảy ra.

Một stack của Thread được lấy lúc chẩn đoán cho biết đường thực thi của luồng tại thời điểm lấy mẫu. Nó không tự chứa toàn bộ lịch sử trước đó.

Hai trường hợp dễ nhầm:

- Luồng điều phối đang chờ `Future.get()`; stack sống của nó chỉ ra điểm chờ. Nguyên nhân tác vụ con thất bại nằm trong ngoại lệ kết quả, chẳng hạn `ExecutionException.getCause()`.
- Một luồng đã ghi log ngoại lệ rồi tiếp tục nhận việc mới; stack sống sau đó có thể cho thấy đang chờ hàng đợi. Không thể dùng ảnh sau để phủ nhận lỗi đã được ghi trước.

Vì vậy, khi điều tra, phải xác định đang đọc stack của sự kiện lỗi hay ảnh stack hiện tại của luồng nào.

## 4. Nhận diện các dạng chờ thường gặp

### 4.1. Chờ monitor nội tại: BLOCKED ở synchronized

Một luồng muốn vào `synchronized` có thể có trạng thái `BLOCKED`. Điểm thực thi thường nằm ngay ở phương thức/dòng mã đang cố nhận monitor; không nhất thiết xuất hiện một phương thức thư viện có tên “lock”.

Một thread dump có thể bổ sung thông tin dạng “waiting to lock” và đối tượng monitor. Cần tìm luồng đang giữ đúng đối tượng đó.

Không kết luận chỉ từ việc hai stack có cùng tên phương thức. Hai lời gọi cùng phương thức có thể khóa hai đối tượng khác nhau; quan hệ chờ cần dựa trên danh tính tài nguyên và thông tin sở hữu.

### 4.2. Chờ Object.wait: đã nhả monitor của đối tượng đang wait

Một chuỗi phương thức đi qua `Object.wait` cho thấy luồng đang tham gia giao thức chờ điều kiện của monitor.

Câu hỏi tiếp theo là: điều kiện nào đang được kiểm tra, luồng nào cập nhật nó và đường nào gọi notify/notifyAll? Khi được báo hiệu, bên chờ vẫn phải nhận lại monitor trước khi phương thức chờ trở về.

Nếu đã được báo hiệu nhưng monitor còn do luồng khác giữ, một ảnh tiếp theo có thể thấy bên chờ `BLOCKED` tại giai đoạn nhận lại. Không gọi notify thêm một cách tùy tiện để “chữa” tình huống mà chưa hiểu điều kiện và chủ monitor.

### 4.3. Chờ qua park: phải đọc tới API cấp cao

Nhiều công cụ của `java.util.concurrent` có thể hội tụ về park. Tên primitive ở đầu stack không phân biệt được toàn bộ các tình huống:

| Frame cấp cao cần tìm | Ý nghĩa có thể xảy ra | Câu hỏi tiếp theo |
| --- | --- | --- |
| `ArrayBlockingQueue.take` hoặc `LinkedBlockingQueue.take` | Chờ có phần tử | Bên sản xuất còn hoạt động không? Hàng đợi có đang trống đúng thiết kế không? |
| `BlockingQueue.put` của hàng đợi có giới hạn | Chờ có chỗ trống | Bên tiêu thụ có bị lỗi hoặc xử lý quá chậm không? |
| `CountDownLatch.await` | Chờ đủ lượt đếm | Những đường nào chịu trách nhiệm countDown? Có đường lỗi bỏ quên không? |
| `FutureTask.get`, `CompletableFuture.get/join` | Chờ kết quả | Tác vụ tạo kết quả đang ở đâu và có cơ hội chạy không? |
| `ReentrantLock.lock` hoặc lời gọi condition | Chờ khóa/điều kiện | Đang tranh quyền nhận hay chờ một điều kiện được báo hiệu? |
| `Semaphore.acquire` | Chờ quyền khả dụng | Ai sẽ trả quyền, có đường nào thất thoát quyền không? |

Tên frame trung gian thay đổi theo JDK và đường thực thi. Bảng là cách định hướng đọc ngữ nghĩa API, không phải tập mẫu chuỗi hoàn chỉnh cho mọi phiên bản.

### 4.4. Chờ join hoặc sleep

`Thread.join` hướng tới vòng đời một luồng khác. Cần xác định luồng đích, rồi đọc stack của chính luồng đó.

`Thread.sleep` là tạm dừng theo thời gian, không tự nhả những monitor mà luồng đang giữ. Nếu một luồng sleep bên trong vùng synchronized và các luồng khác BLOCKED trên monitor đó, hãy điều tra lý do giữ monitor xuyên suốt khoảng ngủ.

Một stack ở sleep cũng có thể là cơ chế chờ giữa các lần thử lại. Khi ấy, nguyên nhân chậm có thể nằm ở chính sách thử lại hoặc hệ thống bên ngoài, chứ không ở thao tác sleep tự thân.

### 4.5. I/O và RUNNABLE không phải lúc nào cũng là tính toán

Một stack có thể nằm ở đọc socket hoặc lời gọi native trong khi trạng thái Java vẫn là `RUNNABLE`. Không suy ra ngay rằng luồng đang tiêu thụ CPU cao.

Cần kết hợp thời gian CPU, hoạt động mạng/I/O, thời hạn gọi và ngữ cảnh yêu cầu. Một stack đứng lâu ở chỗ đọc có thể là chờ dữ liệu từ xa, còn một stack ở vòng lặp ứng dụng với CPU tăng có thể là vấn đề tính toán hoặc lặp không tiến triển.

## 5. Đọc thông tin khóa đi kèm stack

Một thread dump hoặc `ThreadInfo` có thể cung cấp thêm:

- Đối tượng mà luồng đang chờ.
- Tên hoặc định danh của luồng sở hữu khóa nếu có.
- Các monitor hoặc bộ đồng bộ có sở hữu mà luồng đang giữ.
- Stack trace và trạng thái của luồng.

Thông tin này giúp nối “A đang chờ X” với “X do B giữ”, rồi chuyển sang điều tra B. Nó phục vụ chẩn đoán, không phải một giao thức để ứng dụng tự cấp quyền hoặc nhả khóa. [Tài liệu ThreadInfo](https://docs.oracle.com/en/java/javase/25/docs/api/java.management/java/lang/management/ThreadInfo.html)

Đặc biệt, phân biệt ba ý nghĩa thường thấy trong bản dump:

| Thông tin | Cách đọc |
| --- | --- |
| Đang đợi nhận monitor | Chưa sở hữu monitor đó tại điểm chờ |
| Đã khóa một monitor | Có thể đang giữ monitor trong khi thực hiện các frame liên quan |
| Đang park để chờ một đối tượng | Đối tượng giúp mô tả bộ đồng bộ/điều kiện chờ; không mặc nhiên là monitor do một luồng khác giữ |

Một đối tượng condition hoặc future không nhất thiết có “chủ sở hữu khóa” theo cùng mô hình monitor. Không tìm thấy owner không có nghĩa việc chờ không có phụ thuộc; phụ thuộc có thể là một tác vụ phải công bố kết quả hoặc một bên phải thêm phần tử.

## 6. Ví dụ Java 17: phân biệt hàng đợi WAITING và monitor BLOCKED

Chương trình sau tạo hai tình huống:

- Một consumer gọi `ArrayBlockingQueue.take()` khi hàng đợi còn trống.
- Một luồng gọi `enterMonitor()` trong khi main cố ý giữ monitor mà nó cần.

Thay vì so khớp nguyên văn mọi dòng của JDK, chương trình kiểm tra frame API và frame ứng dụng, rồi in kết quả đã chuẩn hóa. Tùy chọn `full` cho phép xem cả stack thật trong môi trường đang chạy.

Tạo tệp `StackWaitDemo.java`:

```java
import java.util.Arrays;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

public class StackWaitDemo {
    record Sample(Thread.State state, StackTraceElement[] frames) {}

    static boolean hasFrame(
            StackTraceElement[] frames, String className, String methodName) {
        return Arrays.stream(frames).anyMatch(frame ->
                frame.getClassName().equals(className)
                        && frame.getMethodName().equals(methodName));
    }

    static Sample awaitSample(
            Thread thread, Thread.State expected, String applicationMethod)
            throws InterruptedException {
        long started = System.nanoTime();
        long budget = TimeUnit.SECONDS.toNanos(5);
        while (System.nanoTime() - started < budget) {
            Thread.State before = thread.getState();
            StackTraceElement[] frames = thread.getStackTrace();
            Thread.State after = thread.getState();
            if (before == expected && after == expected
                    && hasFrame(frames,
                            StackWaitDemo.class.getName(), applicationMethod)) {
                return new Sample(before, frames);
            }
            if (after == Thread.State.TERMINATED) {
                throw new IllegalStateException(
                        "worker terminated before sample");
            }
            Thread.sleep(1);
        }
        throw new IllegalStateException("expected sample not observed");
    }

    static void awaitStarted(CountDownLatch started)
            throws InterruptedException {
        if (!started.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("worker did not start");
        }
    }

    static void finish(Thread thread) throws InterruptedException {
        thread.join(5_000);
        if (thread.isAlive()) {
            throw new IllegalStateException("worker did not finish");
        }
    }

    static void printFrames(Sample sample, boolean full) {
        if (full) {
            for (StackTraceElement frame : sample.frames()) {
                System.out.println("    at " + frame);
            }
        }
    }

    static void awaitJob(
            ArrayBlockingQueue<String> queue, CountDownLatch started) {
        started.countDown();
        try {
            queue.take();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
        }
    }

    static void enterMonitor(Object monitor, CountDownLatch started) {
        started.countDown();
        synchronized (monitor) {
            // The method can finish after main releases this monitor.
        }
    }

    static void observeQueue(boolean full) throws InterruptedException {
        ArrayBlockingQueue<String> queue = new ArrayBlockingQueue<>(1);
        CountDownLatch started = new CountDownLatch(1);
        Thread consumer = new Thread(
                () -> awaitJob(queue, started), "queue-consumer");
        consumer.start();

        try {
            awaitStarted(started);
            Sample sample = awaitSample(
                    consumer, Thread.State.WAITING, "awaitJob");
            if (!hasFrame(sample.frames(),
                    ArrayBlockingQueue.class.getName(), "take")) {
                throw new IllegalStateException("queue.take frame missing");
            }
            System.out.println("queue.state=" + sample.state());
            System.out.println(
                    "queue.api=java.util.concurrent.ArrayBlockingQueue.take");
            System.out.println(
                    "queue.application=StackWaitDemo.awaitJob");
            printFrames(sample, full);
        } finally {
            consumer.interrupt();
            finish(consumer);
        }
    }

    static void observeMonitor(boolean full) throws InterruptedException {
        Object monitor = new Object();
        CountDownLatch started = new CountDownLatch(1);
        Thread contender = new Thread(
                () -> enterMonitor(monitor, started), "monitor-contender");

        try {
            synchronized (monitor) {
                contender.start();
                awaitStarted(started);
                Sample sample = awaitSample(
                        contender, Thread.State.BLOCKED, "enterMonitor");
                System.out.println("monitor.state=" + sample.state());
                System.out.println(
                        "monitor.application=StackWaitDemo.enterMonitor");
                printFrames(sample, full);
            }
        } finally {
            // Joining inside synchronized would prevent worker progress.
            finish(contender);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        boolean full = args.length > 0 && args[0].equals("full");
        observeQueue(full);
        observeMonitor(full);
    }
}
```

Biên dịch và chạy:

```shell
javac -encoding UTF-8 StackWaitDemo.java
java StackWaitDemo
```

Stdout mặc định trong điều kiện chạy thông thường:

```text
queue.state=WAITING
queue.api=java.util.concurrent.ArrayBlockingQueue.take
queue.application=StackWaitDemo.awaitJob
monitor.state=BLOCKED
monitor.application=StackWaitDemo.enterMonitor
```

Để xem stack thật:

```shell
java StackWaitDemo full
```

Ở chế độ này, đầu ra có thêm các dòng `at ...`; tên frame nội bộ, module, số dòng và độ sâu có thể khác giữa các JDK.

### 6.1. Ví dụ chứng minh điều gì?

Ở trường hợp hàng đợi, ba lớp bằng chứng kết nối được với nhau:

1. WAITING: worker đang chờ.
2. `ArrayBlockingQueue.take`: API đang đợi phần tử.
3. `StackWaitDemo.awaitJob`: phương thức ứng dụng gọi API đó.

Trong trường hợp monitor, điểm chờ nằm ở `enterMonitor`. Không cần một frame `LockSupport.park` để giải thích việc chờ monitor nội tại.

Cả hai trường hợp đều là chờ được main chủ động tạo ra. Main giữ nguyên điều kiện cần thiết trong quá trình chụp rồi dọn dẹp: ngắt consumer hoặc nhả monitor trước khi join.

### 6.2. Vì sao không chỉ sleep rồi lấy stack một lần?

Một khoảng sleep của main không bảo đảm worker đã đến đúng điểm. Nó có thể chưa được CPU, vẫn đang tải lớp hoặc đã chạy qua đoạn quan tâm.

Ví dụ dùng latch để xác nhận worker đã đến mốc ban đầu, sau đó tìm mẫu có thời hạn. Việc đọc state trước và sau stack giúp loại một số mẫu chuyển tiếp, nhưng **không biến các lần đọc thành một ảnh chụp nguyên tử toàn hệ thống**. Điều giúp thí nghiệm rõ ràng là main giữ hàng đợi trống hoặc giữ monitor cho đến khi lấy mẫu xong.

Trong ứng dụng thật, không dùng hàm `awaitSample` để điều phối nghiệp vụ. Nó chỉ là công cụ quan sát của bài thực hành.

### 6.3. Vì sao chương trình có thể báo không lấy được mẫu?

API lấy stack có giới hạn: luồng có thể kết thúc, frame có thể không đầy đủ hoặc môi trường không tiến triển trong ngân sách lấy mẫu. Đừng coi một mảng rỗng hoặc thiếu frame là bằng chứng chắc chắn rằng phương thức chưa từng chạy.

`Thread.getStackTrace()` cung cấp ảnh stack phục vụ quan sát; giới hạn và thời điểm lấy mẫu phải được tính đến khi kết luận. [Tài liệu Thread](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Thread.html)

## 7. Thu thập stack ngoài tiến trình bằng jcmd

Khi cần xem một JVM đang chạy, có thể dùng `jcmd` thuộc JDK phù hợp. Trước hết xác định đúng tiến trình và xem lệnh mà chính JVM đó hỗ trợ.

Ví dụ sau dùng PID giả định là 12345; khi thực hành, thay bằng PID vừa xác minh:

```shell
jcmd -l
jcmd 12345 help Thread.print
jcmd 12345 Thread.print -l
```

`Thread.print` in thông tin luồng và stack; tùy chọn `-l` bổ sung thông tin các khóa của `java.util.concurrent`. Khả năng attach phụ thuộc môi trường, cùng máy, tài khoản/quyền tương ứng và cấu hình JVM. Xem `help` trên tiến trình đích để tránh áp dụng tùy chọn của JDK khác.

Với JDK hỗ trợ công cụ dump mới và ứng dụng dùng virtual thread, kiểm tra thêm:

```shell
jcmd 12345 help Thread.dump_to_file
```

Chọn công cụ có phạm vi hỗ trợ đúng loại luồng, thay vì giả định một bản dump truyền thống luôn bao quát mọi virtual thread. Cú pháp và tùy chọn phải theo JDK đích. [Tài liệu jcmd](https://docs.oracle.com/en/java/javase/25/docs/specs/man/jcmd.html)

Lấy mẫu vừa đủ để so sánh tiến triển. Chụp stack có chi phí phụ thuộc số luồng và cơ chế chẩn đoán; không tạo vòng gọi liên tục chỉ để thay thế một profiler hoặc cơ chế giám sát phù hợp.

## 8. Từ một luồng chờ sang chuỗi phụ thuộc

Xác định vị trí chờ là bước đầu, không phải luôn là nguyên nhân gốc.

### 8.1. Chờ future: tìm nơi tạo kết quả

Giả sử stack cho thấy:

```text
java.util.concurrent.FutureTask.get
demo.ReportService.waitForPrice
demo.ReportService.buildReport
```

Đây là bằng chứng `buildReport` chưa có kết quả giá. Bước tiếp theo là tìm tác vụ tính giá:

- Đã được gửi chưa?
- Có đang nằm trong hàng đợi không?
- Các worker có đang bị chính những tác vụ cha chiếm hết rồi cùng chờ con không?
- Tác vụ con có chờ hệ thống ngoài mà không có thời hạn không?
- Ngoại lệ đã được xử lý theo cách nào?

Không sửa bằng cách bỏ `get()` nếu kết quả vẫn là điều kiện bắt buộc của báo cáo. Cần xác định hợp đồng phụ thuộc và khả năng tiến triển của các tác vụ.

### 8.2. Chờ monitor: đi tiếp tới người giữ

Nếu A chờ monitor M do B giữ, đọc stack của B. B có thể đang thực hiện một lời gọi mạng chậm khi vẫn giữ M, hoặc đang chờ một tài nguyên khác.

Có thể lập sơ đồ nhỏ:

```text
A → chờ monitor M → B đang giữ M → B chờ kết quả C
```

Muốn kết luận deadlock cần thấy chuỗi quay lại một tài nguyên/luồng đã nằm trong vòng và không có đường tiến triển phù hợp. Chỉ một mũi tên chờ không đủ.

### 8.3. Chờ hàng đợi: xác định chiều và điều kiện

`take()` trên hàng đợi trống và `put()` trên hàng đợi đầy đều là chờ nhưng có ý nghĩa ngược nhau.

Nếu mọi consumer chờ take và không còn producer, cần xem công việc đã kết thúc đúng thiết kế hay producer chết mà giao thức dừng chưa được truyền xuống. Nếu producer chờ put trong khi consumer đang đợi chính producer hoàn thành, có thể đang có vòng phụ thuộc ở cấp tác vụ.

Frame ứng dụng và cấu hình hàng đợi giúp phân biệt các tình huống, trong khi tên primitive park ở đầu stack không đủ thông tin.

## 9. So sánh nhiều ảnh chụp để kiểm tra tiến triển

Một stack đứng ở cùng phương thức trong vài lần chụp có thể gợi ý chờ kéo dài, nhưng chưa chứng minh cùng một lần gọi không tiến triển. Worker có thể xử lý nhiều việc nhanh rồi quay lại cùng thao tác lấy hàng đợi trước mỗi lần lấy mẫu.

Kết hợp thêm:

- Mã yêu cầu hoặc mã tác vụ khi có.
- Bộ đếm công việc đã hoàn thành.
- Độ dài hàng đợi theo thời gian.
- Thời gian CPU và thời gian trôi qua.
- Log bắt đầu/kết thúc hoặc dấu vết truy vết của cùng thao tác.

Ví dụ, ba stack đều ở `queue.take` cùng bộ đếm hoàn thành tăng có ý nghĩa khác với ba stack ở `Future.get` của cùng mã yêu cầu và không có tác vụ tạo kết quả nào đang chạy.

Tương tự, một stack RUNNABLE lặp lại không tự chứng minh vòng lặp vô hạn. Cần số đo CPU và bằng chứng rằng dữ liệu/điểm xử lý không tiến triển.

## 10. Những lỗi đọc stack thường gặp

| Cách đọc sai | Vì sao chưa đủ? | Hướng đọc đúng |
| --- | --- | --- |
| Thấy Unsafe.park rồi kết luận JVM bị lỗi | Nhiều primitive hợp lệ hội tụ về đây | Tìm API cấp cao và frame ứng dụng |
| Thấy WAITING rồi kết luận deadlock | Worker nhàn cũng có thể WAITING | Xây chuỗi phụ thuộc và xem tiến triển |
| Chỉ đọc dòng ứng dụng đầu tiên | Có thể chỉ là hàm tiện ích chung | Đọc tiếp tới ngữ cảnh nghiệp vụ |
| Dùng số dòng của mã nguồn mới nhất | Bản chạy có thể khác phiên bản | Đối chiếu đúng bản build đang chạy |
| Thấy cùng tên khóa rồi cho là cùng đối tượng | Tên/lớp không xác định danh tính monitor | Đối chiếu thông tin đối tượng và owner |
| Cho rằng RUNNABLE luôn dùng CPU | Có thể đang trong native/I/O | Kết hợp stack và số đo CPU |
| Mẫu stack không đổi nghĩa là không xử lý việc | Có thể quay lại cùng điểm giữa các công việc | Kết hợp bộ đếm và mã tác vụ |
| Tìm mọi nguyên nhân trong stack người chờ | Nguyên nhân có thể ở người giữ hoặc tác vụ tạo kết quả | Lần theo phụ thuộc sang các luồng khác |
| Tự notify/unpark để làm luồng chạy tiếp | Có thể phá giao thức điều kiện hoặc không giải quyết nguyên nhân | Hiểu điều kiện thật và đường cập nhật nó |

Đặc biệt, không dùng một ảnh stack làm căn cứ cho việc nhả khóa thay luồng sở hữu hoặc dừng cưỡng bức luồng. Việc khôi phục phải tôn trọng giao thức tài nguyên và trạng thái dữ liệu của ứng dụng.

## 11. Một cách ghi nhận kết luận có thể kiểm chứng

Một báo cáo chẩn đoán ngắn có thể viết:

> Consumer queue-consumer đang WAITING. Stack đi qua ArrayBlockingQueue.take và phương thức ứng dụng awaitJob, phù hợp với việc hàng đợi chưa có phần tử. Chưa có bằng chứng deadlock. Bước xác minh tiếp theo là kiểm tra producer và số phần tử/công việc hoàn thành trong cùng khoảng thời gian.

Hoặc:

> monitor-contender đang BLOCKED tại enterMonitor. Main đang giữ monitor cần thiết trong thí nghiệm. Khi main rời vùng synchronized, contender nhận monitor và kết thúc; vị trí chờ đã được xác định và giải thích bằng quan hệ sở hữu.

Cấu trúc này tách bằng chứng quan sát, cách diễn giải và điều còn phải kiểm tra. Nó hữu ích hơn kết luận chung “thread bị treo ở Java concurrent”.

## 12. Bài tập thực hành

1. Chạy `StackWaitDemo full`. Đánh dấu ba lớp: primitive chờ, API thư viện và frame ứng dụng. Đối chiếu frame thực tế với bản rút gọn trong bài.
2. Thay hàng đợi trống bằng hàng đợi có một phần tử trước khi start consumer. Giải thích vì sao mẫu WAITING có thể không xuất hiện và chương trình quan sát phải báo không đạt kỳ vọng.
3. Tạo một producer chờ `put()` vào hàng đợi đầy. So sánh stack với consumer chờ `take()`, rồi chỉ rõ bên nào cần làm gì để tạo tiến triển.
4. Đặt một phương thức ứng dụng bao quanh `Future.get()`. Xác định frame chờ và ngữ cảnh gọi; giải thích vì sao phải tìm tiếp tác vụ tạo kết quả.
5. Trong thí nghiệm monitor, thay phần việc của người giữ bằng một lời gọi chậm có kiểm soát. Dựng chuỗi “người chờ → tài nguyên → người giữ → thao tác chậm”.
6. Thu hai ảnh chụp của worker ở cùng `take()` nhưng có bộ đếm hoàn thành tăng giữa hai lần. Viết kết luận phân biệt “cùng vị trí chờ” với “cùng công việc không tiến triển”.

Một lần đọc stack đạt mục tiêu khi có thể nối được vị trí chờ với điều kiện cần thay đổi và thành phần chịu trách nhiệm tạo thay đổi đó. Tên frame chỉ là dấu vết để dựng lại quan hệ ấy.
